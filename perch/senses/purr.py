"""purr: containers and node vitals, from Komodo (design plan 4.1, 05 plan M1).

One ``cycle`` reads Komodo (``komodo.py``), compares what it sees with the fleet repo
(catTree: which nodes, which apps, which containers each app should have) and writes
scentTrail: a state for every container, app and node, and an event whenever something a
person should know about changes. The rollup to node and fleet is ``rollup.py``.

Rules (design plan 4.1), and the decisions the plan leaves open (runbook 2026-10-01):

- exited, dead, unhealthy or missing container -> hiss; restarting, created, paused ->
  tailFlick; restarted -> tailFlick, three restarts in 15 minutes -> hiss;
- disk over 85 % -> tailFlick, over 95 % -> hiss; a node Komodo can't reach -> hiss,
  except roastery outside its wake window, which is asleep, as expected (05 plan C5);
- **a hiss must be seen on two consecutive cycles** (60 s at the default rhythm) before
  it is written: a redeploy or a Komodo blip must not page anyone ("no false hiss", dev
  plan M6). A restart loop is already confirmed by its count and isn't held back;
- Komodo itself unreachable (after two failed cycles) makes everything ``unknown``, never
  hiss: perch can't see, which isn't the same as the fleet being down (design plan 8).
"""

from __future__ import annotations

import asyncio
from collections import deque
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from ..bodyLanguage import BodyLanguage as B
from ..bodyLanguage import worstOf
from ..catTree import App, CatTree, Fleet, Node
from ..rhythms import Rhythm, SleepWindow, sleepWindowFromRepo
from ..rollup import Status
from ..scentTrail import ScentTrail, State
from ..words import duration, ordinal
from .dockerStatus import EXIT_MEANINGS, DockerStatus, parseStatus
from .komodo import KomodoContainer, KomodoError, KomodoServer, KomodoSnapshot

CONFIRM = 2  # consecutive bad cycles before a hiss is written
RESTART_WINDOW = timedelta(minutes=15)
RESTART_STORM = 3  # restarts inside the window that make a hiss
DISK_WARN, DISK_CRIT = 85.0, 95.0
PROJECT_LABEL = "com.docker.compose.project"  # compose names the project after the app's folder


@dataclass
class _Cycle:
    """What every step of one cycle needs: when it is, what Komodo said, and what scentTrail
    held before the cycle began (so a state's previous level is never the one just written)."""

    now: datetime
    snap: KomodoSnapshot
    window: SleepWindow
    prev: dict[str, State]


@dataclass
class _Seen:
    """What one container looked like last cycle: enough to tell a restart from a redeploy."""

    id: str | None = None
    state: str = ""
    uptime: int | None = None
    at: datetime | None = None


@dataclass
class _Entry:
    """A container's place in its app's rollup this cycle (level None: held back, not known yet)."""

    name: str
    level: B | None
    title: str
    label: str


def _lookRunning(status: DockerStatus) -> tuple[B, str, str]:
    if status.health == "unhealthy":
        return B.hiss, "unhealthy", "is running but unhealthy"
    if status.health == "starting":
        return B.earTwitch, "starting", "is starting (health check pending)"
    return B.slowBlink, status.health or "running", status.health or "running"


def _lookStopped(state: str, status: DockerStatus) -> tuple[B, str, str]:
    code = status.exitCode
    if code is None:
        return B.hiss, state, state
    meaning = EXIT_MEANINGS.get(code)
    return B.hiss, f"exited ({code})", f"{state} (code {code}{': ' + meaning if meaning else ''})"


_LOOK_BY_STATE = {
    "created": (B.tailFlick, "created", "was created but never started"),
    "stopping": (B.tailFlick, "stopping", "is stopping"),
    "removing": (B.tailFlick, "removing", "is being removed"),
}


def _look(c: KomodoContainer, status: DockerStatus) -> tuple[B, str, str]:
    """(level, short label, sentence) for one container, from its state and Docker's words."""
    if c.state == "paused" or status.paused:
        return B.tailFlick, "paused", "is paused"
    if c.state == "running":
        return _lookRunning(status)
    if c.state == "restarting":
        last = f" (last exit code {status.exitCode})" if status.exitCode is not None else ""
        return B.tailFlick, "restarting", f"is restarting{last}"
    if c.state in ("exited", "dead"):
        return _lookStopped(c.state, status)
    return _LOOK_BY_STATE.get(c.state, (B.unknown, "unknown", "has a state Komodo doesn't report"))


class Purr:
    name = "purr"

    def __init__(
        self,
        komodo: Any,
        trail: ScentTrail,
        tree: CatTree,
        *,
        clock,
        every: int = 30,
        sleepers: tuple[str, ...] = ("roastery",),
        tz: ZoneInfo,
    ) -> None:
        self.komodo = komodo
        self.trail = trail
        self.tree = tree
        self.clock = clock
        self.rhythm = Rhythm(every=every)
        self.sleepers = {s.lower() for s in sleepers}
        self.tz = tz
        self._streaks: dict[str, int] = {}
        self._seen: dict[str, _Seen] = {}
        self._restarts: dict[str, deque[datetime]] = {}
        self._blind = 0
        self._window: SleepWindow | None = None
        self._windowCommit: str | None = None

    async def aclose(self) -> None:
        await self.komodo.aclose()

    # -- one cycle ----------------------------------------------------------------------

    async def cycle(self) -> None:
        now = self.clock()
        fleet, window = await asyncio.to_thread(self._fleetAndWindow)
        try:
            snap = await self.komodo.snapshot(now)
        except KomodoError:
            self._goBlind(now)
            raise
        self._blind = 0
        cy = _Cycle(now=now, snap=snap, window=window, prev=self.trail.states())
        servers = {s.name.lower(): s for s in snap.servers}
        for node in fleet.nodes:
            self._node(node, servers.get(node.name.lower()), cy)

    def _fleetAndWindow(self) -> tuple[Fleet, SleepWindow]:
        fleet = self.tree.fleet()
        if self._window is None or fleet.commit != self._windowCommit:
            self._window = sleepWindowFromRepo(self.tree, fleet, self.tz)
            self._windowCommit = fleet.commit
        return fleet, self._window

    def _goBlind(self, now: datetime) -> None:
        """Komodo can't be read. Two failed cycles in a row and everything purr knows turns
        ``unknown``: stale green is worse than grey. No events: the collector's own rhythm
        (collectors.py) raises "purr is late" with the reason."""
        self._blind += 1
        if self._blind < CONFIRM:
            return
        for subject, state in self.trail.states().items():
            if subject.startswith(("app:", "node:", "container:")) and state.bodyLanguage is not B.unknown:
                self.trail.setState(subject, B.unknown, title="Komodo isn't answering", detail=state.detail, seenAt=now)

    # -- helpers ------------------------------------------------------------------------

    def _streak(self, key: str, bad: bool) -> int:
        """Consecutive bad readings of ``key``; a good one resets it."""
        if not bad:
            self._streaks.pop(key, None)
            return 0
        self._streaks[key] = self._streaks.get(key, 0) + 1
        return self._streaks[key]

    def _write(self, subject: str, level: B, title: str | None, detail: dict | None, cy: _Cycle) -> None:
        self.trail.setState(subject, level, title=title, detail=detail, seenAt=cy.now)

    def _announce(
        self,
        subject: str,
        name: str,
        level: B,
        title: str,
        *,
        cy: _Cycle,
        detail: dict | None = None,
        more: bool = False,
    ) -> None:
        """An event when something changed that a person should see: it got worse (or, for a
        restart, there was another one), or it was bad and is fine again. ``subject`` is
        looked up in what scentTrail held before this cycle."""
        before = cy.prev.get(subject)
        add = self.trail.addEvent
        if level.rank >= B.tailFlick.rank and (before is None or before.bodyLanguage is not level or more):
            add("purr", subject, level, title, detail=detail, seenAt=cy.now)
        elif level is B.slowBlink and before and before.bodyLanguage.rank >= B.tailFlick.rank:
            lasted = duration((cy.now - before.since).total_seconds())
            text = f"{name} is back (was {before.bodyLanguage.value} for {lasted})"
            add("purr", subject, B.slowBlink, text, detail=detail, seenAt=cy.now)

    # -- a node -------------------------------------------------------------------------

    def _node(self, node: Node, server: KomodoServer | None, cy: _Cycle) -> None:
        watched = [a for a in node.apps if Status.watched(a)]
        key = f"node:{node.name}"
        if server is None or server.state in ("disabled", "unknown"):
            why = (
                f"Komodo has no server called {node.name}"
                if server is None
                else "disabled in Komodo"
                if server.state == "disabled"
                else "Komodo reports a state purr doesn't know"
            )
            self._streak(key, False)
            self._unseen(node, watched, cy, nodeAs=(B.unknown, why), appsAs=(B.unknown, why))
            return

        if server.state == "notok":
            sleeper = node.name.lower() in self.sleepers
            if sleeper and not cy.window.mustAnswer(cy.now):
                self._streak(key, False)
                self._asleep(node, watched, cy)
                return
            if self._streak(key, True) < CONFIRM:
                return  # a first bad look is only a look
            where = " inside its wake window" if sleeper else ""
            title = f"{node.name} isn't answering{where}: {server.err or 'not connected'}"
            self._announce(node.id, node.name, B.hiss, title, cy=cy)
            self._unseen(node, watched, cy, nodeAs=(B.hiss, title), appsAs=(B.unknown, f"{node.name} isn't reporting"))
            return

        self._streak(key, False)
        self._vitals(node, server, cy)
        if server.name in cy.snap.errors:
            if self._streak(f"read:{node.name}", True) < CONFIRM:
                return
            why = f"can't read containers: {cy.snap.errors[server.name]}"
            self._unseen(node, watched, cy, nodeAs=None, appsAs=(B.unknown, why))
            return
        self._streak(f"read:{node.name}", False)
        self._containers(node, watched, cy.snap.containers.get(server.name, []), cy)

    def _vitals(self, node: Node, server: KomodoServer, cy: _Cycle) -> None:
        stats = server.stats
        detail: dict[str, Any] = {"mode": "ok", "version": server.version}
        level, title = B.slowBlink, None
        if stats:
            detail |= {
                "cpu": round(stats.cpuPerc, 1),
                "mem": round(stats.memPerc, 1),
                "disk": round(stats.diskPerc, 1),
                "memUsedGb": round(stats.memUsedGb, 1),
                "memTotalGb": round(stats.memTotalGb, 1),
                "diskUsedGb": round(stats.diskUsedGb, 1),
                "diskTotalGb": round(stats.diskTotalGb, 1),
            }
            if stats.diskPerc >= DISK_CRIT:
                level, title = B.hiss, f"disk {stats.diskPerc:.0f} % full"
            elif stats.diskPerc >= DISK_WARN:
                level, title = B.tailFlick, f"disk {stats.diskPerc:.0f} % full"
        self._announce(node.id, node.name, level, f"{node.name}: {title}", cy=cy, detail=detail)
        self._write(node.id, level, title, detail, cy)

    def _asleep(self, node: Node, watched: list[App], cy: _Cycle) -> None:
        wakes = cy.window.nextWake(cy.now).astimezone(self.tz)
        title = (
            "waking up for the nightly backups"
            if cy.window.expectedUp(cy.now)
            else f"asleep, as expected (wakes {wakes:%H:%M})"
        )
        self._announce(node.id, node.name, B.slowBlink, "", cy=cy)
        self._write(node.id, B.slowBlink, title, {"mode": "asleep", "nextWake": wakes.isoformat()}, cy)
        for app in watched:
            self._write(app.id, B.slowBlink, f"{node.name} is asleep (expected)", None, cy)
        self._blindContainers(node, "can't see: " + title, cy)

    def _unseen(
        self,
        node: Node,
        watched: list[App],
        cy: _Cycle,
        *,
        nodeAs: tuple[B, str] | None,
        appsAs: tuple[B, str],
    ) -> None:
        """The node, or its containers, can't be seen: it and its apps and containers turn what
        they are told (``nodeAs`` None leaves the node's own state alone)."""
        if nodeAs is not None:
            self._write(node.id, nodeAs[0], nodeAs[1], None, cy)
        for app in watched:
            self._write(app.id, appsAs[0], appsAs[1], None, cy)
        self._blindContainers(node, appsAs[1], cy)

    def _blindContainers(self, node: Node, title: str, cy: _Cycle) -> None:
        prefix = f"container:{node.name}/"
        for subject, state in cy.prev.items():
            if subject.startswith(prefix) and state.bodyLanguage is not B.unknown:
                self._write(subject, B.unknown, title, state.detail, cy)

    # -- the containers of a node ----------------------------------------------------------

    def _containers(self, node: Node, watched: list[App], containers: list[KomodoContainer], cy: _Cycle) -> None:
        byProject = {a.name.lower(): a for a in node.apps}
        byName = {name: a for a in node.apps for name in a.containers}
        entries: dict[str, list[_Entry]] = {a.name: [] for a in watched}
        subjects = {f"container:{node.name}/{c.name}" for c in containers}
        present = {c.name for c in containers}

        for c in containers:
            owner = byProject.get(c.labels.get(PROJECT_LABEL, "").lower()) or byName.get(c.name)
            entry = self._container(node, c, owner, cy)
            if entry and owner and owner.name in entries:
                entries[owner.name].append(entry)
        for app in watched:  # containers the compose file names that Komodo doesn't list
            expected = app.containers or ([app.name] if app.images and not entries[app.name] else [])
            for name in expected:
                if name not in present:
                    subjects.add(f"container:{node.name}/{name}")
                    entries[app.name].append(self._missing(node, app, name, cy))
        for app in watched:
            self._app(app, entries[app.name], cy)

        gone = [s for s in cy.prev if s.startswith(f"container:{node.name}/") and s not in subjects]
        self.trail.forget(gone)
        for subject in gone:
            for memory in (self._seen, self._restarts, self._streaks):
                memory.pop(subject, None)

    def _container(self, node: Node, c: KomodoContainer, owner: App | None, cy: _Cycle) -> _Entry | None:
        subject = f"container:{node.name}/{c.name}"
        before = cy.prev.get(subject)
        level, label, title, detail = self._classify(subject, c, owner, cy.now)
        if owner is None:  # not in node.conf: shown on the node page, never rolled up or announced
            self._write(subject, level, title, detail, cy)
            return None
        bad = level is B.hiss and not detail["sure"]
        if self._streak(subject, bad) < CONFIRM and bad:
            # held: the page keeps the previous reading for one more cycle
            return _Entry(
                c.name, before.bodyLanguage if before else None, (before.title if before else "") or "", label
            )
        restarted = detail["restarts15m"] > ((before.detail or {}).get("restarts15m", 0) if before else 0)
        self._announce(
            f"app:{node.name}/{owner.name}", c.name, level, f"{c.name} {title}", cy=cy, detail=detail, more=restarted
        )
        self._write(subject, level, title, detail, cy)
        return _Entry(c.name, level, title, label)

    def _missing(self, node: Node, app: App, name: str, cy: _Cycle) -> _Entry:
        subject = f"container:{node.name}/{name}"
        before = cy.prev.get(subject)
        title = f"not found on {node.name}"
        if self._streak(subject, True) < CONFIRM:
            return _Entry(
                name, before.bodyLanguage if before else None, (before.title if before else "") or "", "missing"
            )
        detail = {"app": app.name, "stray": False, "state": "missing", "label": "missing", "restarts15m": 0}
        self._announce(f"app:{node.name}/{app.name}", name, B.hiss, f"{name} {title}", cy=cy, detail=detail)
        self._write(subject, B.hiss, title, detail, cy)
        return _Entry(name, B.hiss, title, "missing")

    def _app(self, app: App, entries: list[_Entry], cy: _Cycle) -> None:
        known = [e for e in entries if e.level is not None]
        if not known:
            self._write(app.id, B.unknown, "waiting for a second look", None, cy)
            return
        level = worstOf(e.level for e in known)
        worst = next(e for e in known if e.level is level)
        if level is B.slowBlink:
            title = worst.label if len(entries) == 1 else f"{len(entries)} containers up"
        elif len(entries) == 1 and worst.name == app.name:
            title = worst.title
        else:
            title = f"{worst.name} {worst.title}"
        up = sum(1 for e in known if e.level.rank <= B.earTwitch.rank)
        self._write(app.id, level, title, {"containers": len(entries), "up": up, "worst": worst.name}, cy)

    # -- one container ------------------------------------------------------------------------

    def _classify(
        self, subject: str, c: KomodoContainer, owner: App | None, now: datetime
    ) -> tuple[B, str, str, dict[str, Any]]:
        status = parseStatus(c.status)
        restarts = self._countRestarts(subject, c, status.uptime, now)
        level, label, title = _look(c, status)
        sure = False
        if restarts >= RESTART_STORM:
            level, sure, label = B.hiss, True, "restart loop"
            title = f"is restarting in a loop ({restarts} restarts in 15 min)"
        elif restarts and level.rank < B.tailFlick.rank:
            level, label = B.tailFlick, "restarted"
            title = f"restarted ({ordinal(restarts)} in 15 min)"
        detail = {
            "app": owner.name if owner else None,
            "stray": owner is None,
            "image": c.image,
            "state": c.state,
            "status": c.status,
            "label": label,
            "uptimeSeconds": status.uptime,
            "exitCode": status.exitCode,
            "health": status.health,
            "restarts15m": restarts,
            "sure": sure,
        }
        return level, label, title, detail

    def _countRestarts(self, key: str, c: KomodoContainer, uptime: int | None, now: datetime) -> int:
        """Restarts of this container in the last 15 minutes. Docker's rounded uptime only goes
        down when the process restarted, and then the new uptime is short: no longer than the
        time since the last look (plus a minute, as Docker rounds). Both must hold: go-units
        prints "1 years" after "24 months" for half an hour at the 2-year mark, a drop that
        is not a restart. A new container id is a redeploy and is not counted either."""
        last = self._seen.get(key)
        window = self._restarts.setdefault(key, deque())
        if last is not None and last.id == c.id:
            lowerAndShort = (
                c.state == "running"
                and uptime is not None
                and last.uptime is not None
                and last.at is not None
                and uptime < last.uptime
                and uptime <= (now - last.at).total_seconds() + 60
            )
            if lowerAndShort or (c.state == "restarting" and last.state != "restarting"):
                window.append(now)
        elif last is not None:
            window.clear()  # a new container under the old name: a redeploy, a fresh start
        self._seen[key] = _Seen(id=c.id, state=c.state, uptime=uptime if c.state == "running" else None, at=now)
        while window and now - window[0] > RESTART_WINDOW:
            window.popleft()
        return len(window)
