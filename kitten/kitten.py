"""kitten: the small agent on each node (sieve, percolator, cellar, mochaPot, grinder,
roastery). Every 60 s it sends perch a heartbeat and the groom records it hasn't had
acknowledged; pounce events join them in M5.

Standard library only, so it runs as a zipapp on the nodes' own Python 3.13
(Debian 13) and on roastery's Python 3.14 without installing anything (05 plan C11,
A5; ADR 0001). Test S8 runs its tests on both versions.

It runs as an unprivileged ``kitten`` user and only *reads*: the groom records the recorder
wrote (``/var/lib/purrbrews/groom/<job>/<start>.json``, 0644 in a 0755 directory, 05 plan A10) and
the ``*.ok`` stamp files beside them (``drive-sync.ok``: when the Drive copy last finished).
It never writes to a node and never runs anything. roastery has no groom jobs, so its kitten
only sends heartbeats; it simply isn't running while roastery sleeps, and perch knows roastery's
wake window (05 plan C5).
"""

from __future__ import annotations

import json
import os
import platform
import random
import sys
import threading
import time
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

VERSION = "0.1.0"

EVERY = 60  # seconds between reports (design plan 3.4: the heartbeat's rhythm)
RECENT = 72 * 3600  # records older than this are not (re)sent: perch long has them, or never will
BATCH = 50  # records per report (perch accepts 100)
TIMEOUT = 15

# Several pounce paths in one setting are separated by ';' on every OS: Windows
# paths contain ':' (C:\...), so os.pathsep-style ':' can't be the separator there.
PATH_SEPARATOR = ";"


@dataclass(frozen=True)
class KittenConfig:
    perchUrl: str = ""
    token: str = field(default="", repr=False)
    pouncePaths: tuple[str, ...] = ()
    groomDir: str = "/var/lib/purrbrews/groom"
    stateDir: str = "/var/lib/purrbrews"
    node: str = ""

    def __repr__(self) -> str:  # never print the token
        token = "<set>" if self.token else "''"
        return (
            f"KittenConfig(perchUrl={self.perchUrl!r}, token={token}, pouncePaths={self.pouncePaths!r}, "
            f"groomDir={self.groomDir!r}, stateDir={self.stateDir!r}, node={self.node!r})"
        )

    @classmethod
    def fromEnv(cls, env: "dict[str, str] | None" = None) -> "KittenConfig":
        env = dict(os.environ if env is None else env)
        paths = tuple(p.strip() for p in env.get("KITTEN_POUNCE_PATHS", "").split(PATH_SEPARATOR) if p.strip())
        return cls(
            perchUrl=env.get("KITTEN_PERCH_URL", "").strip(),
            token=env.get("KITTEN_TOKEN", "").strip(),
            pouncePaths=paths,
            groomDir=env.get("KITTEN_GROOM_DIR", "").strip() or "/var/lib/purrbrews/groom",
            stateDir=env.get("KITTEN_STATE_DIR", "").strip() or ("" if os.name == "nt" else "/var/lib/purrbrews"),
            node=env.get("KITTEN_NODE", "").strip() or platform.node().split(".")[0],
        )

    def problems(self) -> list[str]:
        """What's missing before kitten can push; empty when it's ready."""
        found = []
        if not self.perchUrl.startswith("https://"):
            found.append("KITTEN_PERCH_URL must be an https:// URL")
        if not self.token:
            found.append("KITTEN_TOKEN is not set")
        return found


def utcIso(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def postJson(url: str, token: str, body: dict, timeout: float = TIMEOUT) -> tuple[int, dict]:
    """POST JSON with the bearer token; returns (status, parsed body). A refusal (4xx) is a result,
    not an exception; an unreachable perch raises OSError. The token is never logged."""
    request = urllib.request.Request(  # noqa: S310 - https only: KittenConfig.problems() refuses anything else
        url,
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:  # noqa: S310
            status, raw = response.status, response.read()
    except urllib.error.HTTPError as exc:
        with exc:  # closes the connection: a refusal still holds a socket
            status, raw = exc.code, exc.read()
    try:
        parsed = json.loads(raw or b"{}")
    except ValueError:
        parsed = {}
    return status, parsed if isinstance(parsed, dict) else {}


class Kitten:
    """One node's agent. ``cycle()`` is one report; ``run()`` is the loop."""

    def __init__(
        self,
        config: KittenConfig,
        *,
        post: Callable[[str, str, dict], tuple[int, dict]] = postJson,
        clock: Callable[[], float] = time.time,
        log: Callable[[str], None] = lambda text: print(text, file=sys.stderr, flush=True),
    ) -> None:
        self.config = config
        self._post = post
        self._clock = clock
        self._log = log
        self._done: set[str] = set()  # records perch has acknowledged or refused: not sent again
        self._said: str | None = None  # the last problem logged, so an outage is said once

    # -- what it reads ------------------------------------------------------------------------

    def stamps(self) -> dict[str, int]:
        """``*.ok`` files in the state directory: name -> modification time (epoch seconds)."""
        found: dict[str, int] = {}
        if self.config.stateDir:
            try:
                for path in sorted(Path(self.config.stateDir).glob("*.ok"))[:10]:
                    found[path.name] = int(path.stat().st_mtime)
            except OSError:
                pass  # a directory it can't read is a node with no stamps
        return found

    def records(self) -> list[tuple[str, dict]]:
        """Recent records not yet acknowledged, oldest first: ``(path, record)``."""
        cutoff = self._clock() - RECENT
        found: list[tuple[float, str, dict]] = []
        try:
            paths = sorted(Path(self.config.groomDir).glob("*/*.json"))
        except OSError:
            return []
        for path in paths:
            try:
                mtime = path.stat().st_mtime
                if mtime < cutoff or str(path) in self._done:
                    continue
                data = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                continue  # unreadable or half-written: the next cycle looks again
            if isinstance(data, dict):
                found.append((mtime, str(path), data))
        found.sort(key=lambda item: item[0])
        return [(path, data) for _mtime, path, data in found[:BATCH]]

    # -- one report ---------------------------------------------------------------------------

    def _body(self, records: list[dict]) -> dict:
        sentAt = utcIso(datetime.fromtimestamp(self._clock(), UTC))
        body: dict = {
            "node": self.config.node,
            "heartbeat": {"version": VERSION, "sentAt": sentAt, "stamps": self.stamps()},
        }
        if records:
            body["records"] = records
        return body

    def cycle(self) -> bool:
        """Send one report. True when perch accepted it."""
        pending = self.records()
        try:
            status, answer = self._post(self.config.perchUrl, self.config.token, self._body([d for _p, d in pending]))
        except OSError as exc:
            self._say(f"perch unreachable: {exc}")
            return False
        if status == 422 and pending:
            # A record perch can't read would block every later one. Mark this batch as seen (it is
            # logged, and stays on the node for a person to look at) and keep the heartbeat going.
            self._log(f"perch refused {len(pending)} record(s): {str(answer.get('error', ''))[:200]}")
            self._done.update(path for path, _data in pending)
            return self._heartbeatOnly()
        if status != 200:
            self._say(f"perch answered {status}: {str(answer.get('error', ''))[:200]}")
            return False
        self._done.update(path for path, _data in pending)
        self._said = None
        return True

    def _heartbeatOnly(self) -> bool:
        try:
            status, _answer = self._post(self.config.perchUrl, self.config.token, self._body([]))
        except OSError:
            return False
        return status == 200

    def _say(self, text: str) -> None:
        if text != self._said:
            self._said = text
            self._log(text)

    def run(self, stop: threading.Event, every: float = EVERY) -> None:
        """Report until told to stop. A little jitter keeps six nodes from reporting in the same second."""
        while not stop.is_set():
            self.cycle()
            stop.wait(every * random.uniform(0.9, 1.1))  # noqa: S311 - spreading load, not security


def main(argv: "list[str] | None" = None) -> int:
    args = list(sys.argv[1:] if argv is None else argv)
    if "--version" in args:
        print(f"kitten {VERSION}")
        return 0
    config = KittenConfig.fromEnv()
    problems = config.problems()
    if problems:
        print("kitten can't start: " + "; ".join(problems), file=sys.stderr)
        return 2
    kitten = Kitten(config)
    if "--once" in args:
        return 0 if kitten.cycle() else 1
    stop = threading.Event()
    try:
        kitten.run(stop)
    except KeyboardInterrupt:
        stop.set()
    return 0
