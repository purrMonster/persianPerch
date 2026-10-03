"""kitten: the small agent on each node (sieve, percolator, cellar, mochaPot, grinder,
roastery). Every 60 s it sends perch a heartbeat and the groom records it hasn't had
acknowledged. Pounce (``pounce.py``, M5) adds filesystem events: names and change types only, sent as soon
as they are debounced, so a dropped file reaches the trail in seconds.

Standard library only, so it runs as a zipapp on the nodes' own Python 3.13
(Debian 13) and on roastery's Python 3.14 without installing anything (05 plan C11,
A5; ADR 0001). Test S8 runs its tests on both versions.

It runs as an unprivileged ``kitten`` user and only *reads*: the groom records the recorder
wrote (``/var/lib/purrbrews/groom/<job>/<start>.json``, 0644 in a 0755 directory, 05 plan A10) and
the ``*.ok`` stamp files beside them (``drive-sync.ok``: when the Drive copy last finished), and the
names (never the contents) of what pounce watches. It never writes to a node; the only programs it runs are
``inotifywait`` and ``git log`` (pounce.py). roastery has no groom jobs, so its kitten
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

from .pounce import Pounce, Watch, buildPounce, defaultWatches, parseWatch

VERSION = "0.2.0"

EVERY = 60  # seconds between reports (design plan 3.4: the heartbeat's rhythm)
RECENT = 72 * 3600  # records older than this are not (re)sent: perch long has them, or never will
BATCH = 50  # records per report (perch accepts 100)
EVENT_BATCH = 100  # pounce events per report (perch accepts 100)
EVENT_BACKLOG = 500  # events kept while perch can't be reached; the oldest go first
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

    def watches(self) -> tuple[Watch, ...]:
        """What pounce watches: ``KITTEN_POUNCE_PATHS`` when set (``none`` switches pounce off), else the
        node's defaults (design plan 4.4, 05 plan C2 and A5)."""
        if self.pouncePaths == ("none",):
            return ()
        if self.pouncePaths:
            return tuple(parseWatch(p) for p in self.pouncePaths)
        return defaultWatches(self.node, windows=os.name == "nt")

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
        self._events: list[dict] = []  # pounce events perch hasn't acknowledged
        self._eventLock = threading.Lock()
        self._wake = threading.Event()  # set when events are ready: send now, don't wait for the minute
        self.pounce: Pounce | None = None

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

    def addEvents(self, events: list[dict]) -> None:
        """Pounce hands over events that are ready; the loop sends them at once."""
        with self._eventLock:
            self._events.extend(events)
            del self._events[:-EVENT_BACKLOG]
        self._wake.set()

    def _takeEvents(self) -> list[dict]:
        with self._eventLock:
            return list(self._events[:EVENT_BATCH])

    def _dropEvents(self, sent: list[dict]) -> None:
        ids = {e["id"] for e in sent}
        with self._eventLock:
            self._events = [e for e in self._events if e["id"] not in ids]

    def _body(self, records: list[dict], events: "list[dict] | None" = None) -> dict:
        sentAt = utcIso(datetime.fromtimestamp(self._clock(), UTC))
        body: dict = {
            "node": self.config.node,
            "heartbeat": {"version": VERSION, "sentAt": sentAt, "stamps": self.stamps()},
        }
        if records:
            body["records"] = records
        if events:
            body["events"] = events
        return body

    def cycle(self) -> bool:
        """Send one report. True when perch accepted it."""
        pending = self.records()
        events = self._takeEvents()
        try:
            status, answer = self._post(
                self.config.perchUrl, self.config.token, self._body([d for _p, d in pending], events)
            )
        except OSError as exc:
            self._say(f"perch unreachable: {exc}")
            return False
        if status == 422 and (pending or events):
            # A record or event perch can't read would block every later one. Mark this batch as seen (it is
            # logged, and a record stays on the node for a person to look at) and keep the heartbeat going.
            self._log(
                f"perch refused {len(pending)} record(s) and {len(events)} event(s): "
                f"{str(answer.get('error', ''))[:200]}"
            )
            self._done.update(path for path, _data in pending)
            self._dropEvents(events)
            return self._heartbeatOnly()
        if status != 200:
            self._say(f"perch answered {status}: {str(answer.get('error', ''))[:200]}")
            return False
        self._done.update(path for path, _data in pending)
        self._dropEvents(events)
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
        """Report until told to stop. A little jitter keeps six nodes from reporting in the same second; a
        pounce event that is ready cuts the wait short (and a failing perch is not hammered: a woken cycle
        that fails waits out the rest of the minute)."""
        self.startPounce()
        try:
            while not stop.is_set():
                self._wake.clear()
                ok = self.cycle()
                deadline = time.monotonic() + every * random.uniform(0.9, 1.1)  # noqa: S311 - spreading load
                while not stop.is_set() and time.monotonic() < deadline:
                    if self._wake.wait(0.25):
                        if ok:
                            break
                        self._wake.clear()  # perch is refusing us: wait for the next minute, keep the events
        finally:
            if self.pounce:
                self.pounce.stop()

    def startPounce(self) -> None:
        if self.pounce is None:  # a test may have built its own
            self.pounce = buildPounce(self.config.watches(), self.addEvents, windows=os.name == "nt", log=self._log)
        if self.pounce:
            self.pounce.start()


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
