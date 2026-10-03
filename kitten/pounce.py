"""pounce: kitten's filesystem watching (design plan 4.4, 05 plan A5 and C2, ADR 0001, ADR 0010).

kitten reports **names and change types, never contents**. Nothing in this module opens, reads or hashes a
file it watches: under ``/etc/purrbrews`` there can be secrets, and perch never looks there (ideation, the
rule for kitten). The only things it does with the disk are to *list* a directory (the Windows poll:
``os.scandir`` and its ``stat``, which read a directory entry, not the file) and to run
``inotifywait`` (Linux), which prints event names. The one thing it asks of a file's content is the new
commit's subject for the checkout's refs, and it asks **git** for that (a subprocess), never the ref file.
``tests/kitten/test_pounce.py`` proves it with an audit hook that fails on any ``open`` of a watched path,
and with a scan of this file's syntax tree.

Pieces, each testable alone:

- ``Watch``: one watched path, its level (what a change is worth) and its reason, parsed from
  ``KITTEN_POUNCE_PATHS`` (``path|level|why``, entries separated by ``;``) or the node's defaults.
- ``InotifySource`` (Linux) and ``PollSource`` (Windows, every 10 s, 05 plan A5): they turn the disk into
  raw ``(change, path)`` facts and know nothing else.
- ``Pouncer``: the rules. A 2 s debounce per path (a file being written is one event), at most 60 events a
  minute per watched path and then **one** "storm" tailFlick, and the commit subject for git refs.
  ``feed`` takes raw facts, ``tick(now)`` returns the events that are ready, so a fake clock drives it.
"""

from __future__ import annotations

import os
import subprocess
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime

DEBOUNCE = 2.0  # seconds a path must be quiet before its event goes out
HOLD_MAX = 10.0  # a path that never goes quiet is reported anyway after this
RATE = 60  # events a minute per watched path before the storm
WINDOW = 60.0
POLL_EVERY = 10.0  # Windows: how often a directory is listed (05 plan A5)
RETRY = (5.0, 60.0)  # inotifywait restarts: first and longest wait
MAX_LISTED = 5000  # a polled directory with more entries than this is read no further
LEVELS = ("slowBlink", "earTwitch", "tailFlick")  # what a watch may be worth; perch never takes a hiss from here
CHANGES = ("created", "modified", "deleted", "storm")

REFS = "refs/heads/main"
PACKED = "packed-refs"


@dataclass(frozen=True)
class Watch:
    """One watched path. ``kind`` is ``files`` (a directory or file, changes are listed) or ``git`` (a ref file
    of the node's checkout: one event carrying the new commit's subject)."""

    path: str
    level: str = "earTwitch"
    why: str = "changed"
    kind: str = "files"

    @property
    def repo(self) -> str:
        """The checkout a git ref belongs to: everything before ``/.git/``."""
        return self.path.partition("/.git/")[0] if "/.git/" in self.path else self.path

    @property
    def target(self) -> str:
        """What inotifywait watches. A single file is watched through its directory: git replaces a ref by
        renaming a lock file over it, which would end a watch placed on the file itself."""
        return os.path.dirname(self.path) or "." if self.kind == "git" else self.path

    @property
    def only(self) -> str | None:
        """For a git ref: the one file name in the directory that counts."""
        return os.path.basename(self.path) if self.kind == "git" else None


def parseWatch(text: str) -> Watch:
    """``/etc/purrbrews|tailFlick|settings changed`` (level and reason optional; a fourth field ``git``)."""
    parts = [p.strip() for p in text.split("|")]
    path = parts[0]
    level = parts[1] if len(parts) > 1 and parts[1] else "earTwitch"
    if level not in LEVELS:
        level = "earTwitch"
    why = parts[2] if len(parts) > 2 and parts[2] else "changed"
    kind = "git" if len(parts) > 3 and parts[3] == "git" else "files"
    return Watch(path, level, why, kind)


# Design plan 4.4 with 05 plan C2: .git/HEAD never changes on a pull (it holds "ref: refs/heads/main"), the
# branch's ref and packed-refs do. Paths a node's kitten user can't list are not worked around (A10): they
# are said once and listed for ROLLOUT.md.
EVERY_LINUX = (
    Watch("/etc/purrbrews", "tailFlick", "settings changed"),
    Watch(f"/opt/purrbrews/.git/{REFS}", "earTwitch", "the node pulled", "git"),
    Watch(f"/opt/purrbrews/.git/{PACKED}", "earTwitch", "the node pulled", "git"),
)
BY_NODE = {
    "cellar": (Watch("/srv/dumps", "earTwitch", "a dump arrived"),),
    "percolator": (Watch("/srv/data/paperless/consume", "earTwitch", "a document dropped"),),
}
ROASTERY = (Watch("C:\\purrbrews\\restic\\snapshots", "earTwitch", "a new snapshot arrived"),)


def defaultWatches(node: str, windows: bool) -> tuple[Watch, ...]:
    """roastery watches its snapshots folder only, never the whole restic repository (05 plan A5)."""
    if windows:
        return ROASTERY
    return (*BY_NODE.get(node, ()), *EVERY_LINUX)


def utcIso(moment: float) -> str:
    return datetime.fromtimestamp(moment, UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def gitSubject(repo: str, timeout: float = 5.0) -> tuple[str, str]:
    """``(hash, subject)`` of the checkout's HEAD, asked of git itself. kitten never opens a ref file. Empty
    strings when git can't say (not installed, not readable by the kitten user)."""
    try:
        run = subprocess.run(  # noqa: S603 - fixed arguments; ``repo`` is a path from kitten's own settings
            ["git", "-c", f"safe.directory={repo}", "-C", repo, "log", "-1", "--format=%H %s", "HEAD"],  # noqa: S607
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return "", ""
    first, _, subject = run.stdout.strip().partition(" ")
    return (first, subject[:200]) if run.returncode == 0 else ("", "")


@dataclass
class _Pending:
    watch: Watch
    name: str
    change: str
    first: float
    last: float


@dataclass
class _Rate:
    sent: deque = field(default_factory=deque)  # monotonic times of events sent in the last minute
    stormed: bool = False


class Pouncer:
    """The pounce rules, with no disk and no threads of its own: ``feed`` raw facts, ``tick(now)`` for what is ready."""

    def __init__(
        self,
        watches: "tuple[Watch, ...] | list[Watch]",
        *,
        wall: Callable[[], float] = time.time,
        subjectOf: Callable[[str], tuple[str, str]] = gitSubject,
        log: Callable[[str], None] = lambda text: None,
    ) -> None:
        self.watches = list(watches)
        self._wall = wall
        self._subjectOf = subjectOf
        self._log = log
        self._lock = threading.Lock()
        self._pending: dict[tuple[str, str], _Pending] = {}
        self._rates: dict[str, _Rate] = {}
        self._lastCommit: dict[str, str] = {}

    # -- facts in ------------------------------------------------------------------------------

    def feed(self, watch: Watch, change: str, name: str, now: float) -> None:
        """One raw fact: ``change`` happened to ``name`` (relative to the watch). Thread-safe."""
        if watch.kind == "git":
            if name != watch.only:
                return  # the other files of .git are none of our business
            key = ("git", watch.repo)  # refs/heads/main and packed-refs move together: one event
            name = ""
        else:
            key = (watch.path, name)
        with self._lock:
            found = self._pending.get(key)
            if found is None:
                self._pending[key] = _Pending(watch, name, change, now, now)
                return
            found.last = now
            found.change = _merge(found.change, change)

    # -- events out ----------------------------------------------------------------------------

    def tick(self, now: float) -> list[dict]:
        """The events whose path has been quiet for the debounce (or has been busy for ``HOLD_MAX``)."""
        with self._lock:
            ready = [
                key
                for key, p in self._pending.items()
                if now - p.last >= DEBOUNCE or now - p.first >= HOLD_MAX
            ]
            batch = [self._pending.pop(key) for key in sorted(ready, key=lambda k: self._pending[k].first)]
        events: list[dict] = []
        for pending in batch:
            events.extend(self._emit(pending, now))
        return events

    def _emit(self, pending: _Pending, now: float) -> list[dict]:
        watch = pending.watch
        rate = self._rates.setdefault(watch.path if watch.kind != "git" else f"git:{watch.repo}", _Rate())
        while rate.sent and now - rate.sent[0] > WINDOW:
            rate.sent.popleft()
        if not rate.sent:
            rate.stormed = False  # a quiet minute ends a storm
        if len(rate.sent) >= RATE:
            if rate.stormed:
                return []
            rate.stormed = True
            return [self._event(watch, "", "storm", level="tailFlick")]
        extra: dict = {}
        if watch.kind == "git":
            digest, subject = self._subjectOf(watch.repo)
            if digest and digest == self._lastCommit.get(watch.repo):
                return []  # packed-refs rewritten by a gc: the checkout did not move
            if digest:
                self._lastCommit[watch.repo] = digest
            extra["commit"] = subject
        rate.sent.append(now)
        return [self._event(watch, pending.name, pending.change, **extra)]

    def _event(self, watch: Watch, name: str, change: str, *, level: str | None = None, **extra) -> dict:
        return {
            "id": uuid.uuid4().hex[:12],
            "at": utcIso(self._wall()),
            "path": watch.path,
            "name": name[:300],
            "change": change,
            "level": level or watch.level,
            "why": watch.why,
            **extra,
        }


def _merge(old: str, new: str) -> str:
    """A file being written is created, then modified several times: that is one *created*. Deleted and
    created again within the debounce is a *modified*."""
    if new == "deleted":
        return "deleted"
    if old == "created":
        return "created"
    if old == "deleted":
        return "modified"
    return new


# -- the disk, as raw facts ------------------------------------------------------------------------

INOTIFY_CHANGES = {
    "CREATE": "created",
    "MOVED_TO": "created",
    "CLOSE_WRITE": "modified",
    "DELETE": "deleted",
    "MOVED_FROM": "deleted",
}
INOTIFY_EVENTS = ("create", "close_write", "moved_to", "moved_from", "delete")


def parseInotifyLine(line: str, watch: Watch) -> tuple[str, str] | None:
    """One line of ``inotifywait --format '%e|%w%f'`` -> ``(change, name relative to the watch)``, or None.
    Anything that isn't one of our events (including a file name that breaks the format) is dropped."""
    events, sep, full = line.rstrip("\n").partition("|")
    if not sep or not full:
        return None
    flags = events.split(",")
    change = next((INOTIFY_CHANGES[f] for f in flags if f in INOTIFY_CHANGES), None)
    if change is None:
        return None
    base = watch.target.rstrip("/\\")
    name = full[len(base) :].lstrip("/\\") if full.startswith(base) else full
    if "ISDIR" in flags and name:
        name += "/"
    return change, name


class InotifySource:
    """Linux: one ``inotifywait -m`` per watch (ADR 0001), restarted with a pause when it ends, so a directory
    that appears later, or a node where the package arrives after kitten, starts working by itself."""

    def __init__(
        self,
        watch: Watch,
        *,
        binary: str = "inotifywait",
        spawn: Callable[..., "subprocess.Popen[str]"] = subprocess.Popen,
        log: Callable[[str], None] = lambda text: None,
        retry: tuple[float, float] = RETRY,
    ) -> None:
        self.watch = watch
        self.binary = binary
        self._spawn = spawn
        self._log = log
        self._retry = retry
        self._proc: "subprocess.Popen[str] | None" = None
        self._said: str | None = None

    def command(self) -> list[str]:
        cmd = [self.binary, "-m", "-q"]
        if self.watch.kind == "files":
            cmd.append("-r")
        for event in INOTIFY_EVENTS:
            cmd += ["-e", event]
        return [*cmd, "--format", "%e|%w%f", self.watch.target]

    def run(self, feed: Callable[[Watch, str, str, float], None], stop: threading.Event) -> None:
        wait = self._retry[0]
        while not stop.is_set():
            try:
                self._proc = self._spawn(  # noqa: S603 - fixed arguments
                    self.command(), stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, bufsize=1
                )
            except OSError as exc:
                self._say(f"pounce can't run {self.binary} for {self.watch.path}: {exc}")
                stop.wait(wait)
                wait = min(wait * 2, self._retry[1])
                continue
            for line in self._proc.stdout or ():
                if stop.is_set():
                    break
                found = parseInotifyLine(line, self.watch)
                if found:
                    wait = self._retry[0]
                    feed(self.watch, found[0], found[1], time.monotonic())
            code, why = self._finish()
            if not stop.is_set():
                detail = f": {why}" if why else ""
                self._say(f"pounce can't watch {self.watch.path} (inotifywait stopped, exit {code}){detail}")
                stop.wait(wait)
                wait = min(wait * 2, self._retry[1])

    def _finish(self) -> tuple[int | None, str]:
        """End the process, close its pipes, and return its exit code and the first line it complained with."""
        proc, self._proc = self._proc, None
        if proc is None:
            return None, ""
        try:
            proc.terminate()
        except OSError:
            pass
        try:
            _out, err = proc.communicate(timeout=5)
        except subprocess.SubprocessError:
            return None, ""
        lines = (err or "").strip().splitlines()
        return proc.returncode, lines[0][:200] if lines else ""

    def close(self) -> None:
        proc = self._proc
        if proc is not None:
            try:
                proc.terminate()
            except OSError:
                pass

    def _say(self, text: str) -> None:
        if text != self._said:  # an outage is said once, not at every retry
            self._said = text
            self._log(text)


class PollSource:
    """Windows (roastery): list the directory every ``every`` seconds and compare names, sizes and times of the
    entries. It reads the directory, never a file (``scandir`` and its ``stat``). The first look is the
    baseline: what is already there is not news."""

    def __init__(
        self,
        watch: Watch,
        *,
        every: float = POLL_EVERY,
        log: Callable[[str], None] = lambda text: None,
    ) -> None:
        self.watch = watch
        self.every = every
        self._log = log
        self._before: dict[str, tuple[int, int]] | None = None
        self._said: str | None = None

    def snapshot(self) -> dict[str, tuple[int, int]]:
        found: dict[str, tuple[int, int]] = {}
        stack = [""]
        while stack and len(found) < MAX_LISTED:
            rel = stack.pop()
            with os.scandir(os.path.join(self.watch.path, rel) if rel else self.watch.path) as entries:
                for entry in entries:
                    name = os.path.join(rel, entry.name) if rel else entry.name
                    info = entry.stat(follow_symlinks=False)
                    if entry.is_dir(follow_symlinks=False):
                        found[name + "/"] = (0, 0)
                        stack.append(name)
                    else:
                        found[name] = (info.st_mtime_ns, info.st_size)
                    if len(found) >= MAX_LISTED:
                        break
        return found

    def poll(self, feed: Callable[[Watch, str, str, float], None], now: float) -> None:
        try:
            current = self.snapshot()
        except OSError as exc:
            self._say(f"pounce can't list {self.watch.path}: {exc.strerror or exc}")
            return
        self._said = None
        before, self._before = self._before, current
        if before is None:
            return
        for name in sorted(current.keys() - before.keys()):
            feed(self.watch, "created", name, now)
        for name in sorted(before.keys() - current.keys()):
            feed(self.watch, "deleted", name, now)
        for name in sorted(n for n in current.keys() & before.keys() if current[n] != before[n]):
            feed(self.watch, "modified", name, now)

    def run(self, feed: Callable[[Watch, str, str, float], None], stop: threading.Event) -> None:
        while not stop.is_set():
            self.poll(feed, time.monotonic())
            stop.wait(self.every)

    def close(self) -> None:
        pass

    def _say(self, text: str) -> None:
        if text != self._said:
            self._said = text
            self._log(text)


class Pounce:
    """The running thing: one thread per watch feeds a ``Pouncer``, one more calls ``tick`` twice a second and
    hands whatever is ready to ``onReady`` (kitten sends it at once, so an event reaches the trail in seconds)."""

    def __init__(
        self,
        pouncer: Pouncer,
        sources: list,
        onReady: Callable[[list[dict]], None],
        *,
        interval: float = 0.5,
    ) -> None:
        self.pouncer = pouncer
        self.sources = sources
        self.onReady = onReady
        self.interval = interval
        self._stop = threading.Event()
        self._threads: list[threading.Thread] = []

    def start(self) -> None:
        for source in self.sources:
            thread = threading.Thread(
                target=source.run, args=(self.pouncer.feed, self._stop), name=f"pounce-{source.watch.path}", daemon=True
            )
            thread.start()
            self._threads.append(thread)
        pump = threading.Thread(target=self._pump, name="pounce-pump", daemon=True)
        pump.start()
        self._threads.append(pump)

    def _pump(self) -> None:
        while not self._stop.wait(self.interval):
            events = self.pouncer.tick(time.monotonic())
            if events:
                self.onReady(events)

    def stop(self) -> None:
        self._stop.set()
        for source in self.sources:
            source.close()


def buildPounce(
    watches: "tuple[Watch, ...] | list[Watch]",
    onReady: Callable[[list[dict]], None],
    *,
    windows: bool,
    log: Callable[[str], None],
) -> Pounce | None:
    """The sources for this platform: polling on Windows, ``inotifywait`` elsewhere (ADR 0001, 05 plan A5)."""
    if not watches:
        return None
    sources: list = [PollSource(w, log=log) if windows else InotifySource(w, log=log) for w in watches]
    return Pounce(Pouncer(watches, log=log), sources, onReady)
