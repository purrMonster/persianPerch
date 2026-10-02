"""groom: did every backup run, and where are the copies? (design plan 4.2, 05 plan M2)

Every backup job writes a record when it ends (``integration/groom/groom-record.py``, run by the
unit's ``ExecStopPost=``). kitten ships the records to ``POST /api/kitten``; cellar's own are read
from ``PERCH_GROOM_DIR``. This module judges them against the rhythms the fleet repo itself declares
(05 plan C4: the ``OnCalendar`` of each timer, never hard-coded), because silence is a signal:

- a night with a good record is slowBlink (earTwitch when the job ran later than its late limit);
- a night with a failed record is hiss;
- a night with **no** record is slowBlink until the late limit, tailFlick after it and hiss once
  the job is missing (design plan 3.4: nightly +45 min / +3 h, Drive sync +2 h / +8 h; the other
  jobs are listed in ``THRESHOLDS`` with the reason).

A *cell* is one job on one night. The same judge draws the grooming grid and writes the state
(``groom:<node>/<job>``) that rolls up into the node and the fleet.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from ..bodyLanguage import BodyLanguage as B
from ..catTree import CatTree, CatTreeError, Fleet
from ..rhythms import OnCalendar, Rhythm, SleepWindow, sleepWindowFromRepo
from ..scentTrail import GroomRun, ScentTrail, State, isoUtc, parseUtc
from ..words import duration

log = logging.getLogger("perch.groom")

RECORD_SCHEMA = 1
LOG_TAIL_LIMIT = 16 * 1024  # design plan 3.2: a log tail is at most 16 KB
NIGHTLY_TIMER = "stacks/_lib/systemd/purrbrews-backup@.timer"

# Job id -> what it is. The ids are the directory names under /var/lib/purrbrews/groom/.
LABELS = {
    "nightly": "nightly backup",
    "wake": "wake roastery",
    "store": "dump store backup",
    "drive": "Drive copy",
    "check": "morning check",
    "prune": "restic prune",
    "verify": "restore check",
}
JOB_ORDER = tuple(LABELS)
# The timer files in stacks/cellar/restic/ that make each cellar job (05 plan C3).
TIMER_JOBS = {
    "purrbrews-wake-roastery.timer": "wake",
    "purrbrews-backup-store.timer": "store",
    "drive-sync.timer": "drive",
    "purrbrews-backup-check.timer": "check",
    "restic-prune.timer": "prune",
    "purrbrews-backup-verify.timer": "verify",
}
_MIN = timedelta(minutes=1)
_HOUR = timedelta(hours=1)
# (late -> tailFlick, missing -> hiss), after the job's expected start. Nightly, store and Drive are
# design plan 3.4. The rest are this build's call, recorded in the runbook (2026-10-02, M2): wake
# is as strict as the nightly it serves; the morning check is quick; prune and verify read the whole
# repository, so they get hours.
THRESHOLDS = {
    "nightly": (45 * _MIN, 3 * _HOUR),
    "store": (45 * _MIN, 3 * _HOUR),
    "drive": (2 * _HOUR, 8 * _HOUR),
    "wake": (45 * _MIN, 3 * _HOUR),
    "check": (_HOUR, 3 * _HOUR),
    "prune": (3 * _HOUR, 12 * _HOUR),
    "verify": (3 * _HOUR, 12 * _HOUR),
}
SKEW = timedelta(minutes=15)  # a run that starts a little before its slot (clock skew) still counts for it
CREDIT = timedelta(hours=12)  # ...and one that starts later than this after a slot is a manual run, not that night's
UNSEEN_AFTER = 72 * _HOUR  # kitten re-sends a record until acknowledged, but only this recent
_DUMP_LINE = re.compile(r"^\s*(pg|mongo|sqlite)\s")
_ON_CALENDAR_LINE = re.compile(r"^OnCalendar=(?P<value>.+)$", re.MULTILINE)
_NAME = re.compile(r"^[A-Za-z0-9_.:@-]{0,128}$")
_RESULT = re.compile(r"^[a-z][a-z-]{0,31}$")
STAMP_NAME = re.compile(r"^[A-Za-z0-9_.-]{1,64}\.ok$")


class RecordError(ValueError):
    """A record kitten (or the recorder) sent that isn't a valid schema-1 groom record."""


# -- the record ---------------------------------------------------------------------------------


def _moment(value: object, field: str) -> datetime:
    if not isinstance(value, str):
        raise RecordError(f"{field} must be an ISO 8601 UTC time")
    try:
        moment = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError as exc:
        raise RecordError(f"{field} is not an ISO 8601 time") from exc
    if moment.tzinfo is None:
        raise RecordError(f"{field} has no time zone")
    return moment.astimezone(UTC)


def parseRecord(data: object) -> GroomRun:
    """A schema-1 record -> ``GroomRun``. Strict about shape and size, because it comes off the wire.

    ``{"schema": 1, "job": "nightly", "node": "grinder", "unit": "purrbrews-backup@grinder.service",
    "start": "2026-09-29T01:30:12Z", "end": "2026-09-29T01:52:36Z", "result": "success",
    "exitStatus": "0", "logTail": "..."}``
    """
    if not isinstance(data, dict):
        raise RecordError("a record is a JSON object")
    if data.get("schema") != RECORD_SCHEMA:
        raise RecordError(f"unsupported record schema {data.get('schema')!r}")
    job, node = data.get("job"), data.get("node")
    if job not in LABELS:
        raise RecordError(f"unknown job {job!r}")
    if not isinstance(node, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,40}", node):
        raise RecordError("node must be a short name")
    result = data.get("result")
    if not isinstance(result, str) or not _RESULT.match(result):
        raise RecordError("result must be systemd's $SERVICE_RESULT, e.g. success or exit-code")
    unit = data.get("unit", "")
    exitStatus = str(data.get("exitStatus", ""))[:32]
    if not isinstance(unit, str) or not _NAME.match(unit):
        raise RecordError("unit is not a unit name")
    tail = data.get("logTail", "")
    if not isinstance(tail, str):
        raise RecordError("logTail must be text")
    start = _moment(data.get("start"), "start")
    end = _moment(data["end"], "end") if data.get("end") else None
    if end is not None and end < start:
        raise RecordError("end is before start")
    return GroomRun(
        node=node,
        job=job,
        start=start,
        end=end,
        result=result,
        exitStatus=exitStatus,
        unit=unit,
        logTail=tail[-LOG_TAIL_LIMIT:],
    )


# -- what the repo says should happen -----------------------------------------------------------


@dataclass(frozen=True)
class Job:
    """One scheduled thing: a node's nightly backup, or one of cellar's jobs."""

    node: str
    name: str
    calendar: OnCalendar
    late: timedelta
    missing: timedelta
    source: str  # the repo file the schedule was read from
    dumps: bool = False  # the node also dumps databases (a pg, mongo or sqlite line in a backup file)

    @property
    def key(self) -> str:
        return f"{self.node}/{self.name}"

    @property
    def subject(self) -> str:
        return f"groom:{self.key}"

    @property
    def label(self) -> str:
        return LABELS[self.name]

    def slotOn(self, day: date, tz: ZoneInfo) -> datetime | None:
        """When the job should start on a local day; None when its timer doesn't fire that day."""
        if not self.calendar.matches(day):
            return None
        return datetime.combine(day, self.calendar.time, tzinfo=tz)

    def latestSlot(self, moment: datetime, tz: ZoneInfo) -> datetime | None:
        """The latest expected start at or before ``moment`` (looks back 70 days: a monthly job)."""
        local = moment.astimezone(tz)
        for back in range(71):
            slot = self.slotOn(local.date() - timedelta(days=back), tz)
            if slot is not None and slot <= moment:
                return slot
        return None


def _onCalendar(text: str) -> OnCalendar:
    found = _ON_CALENDAR_LINE.search(text)
    if not found:
        raise ValueError("no OnCalendar line")
    return OnCalendar.parse(found["value"])


def expectedJobs(tree: CatTree, fleet: Fleet) -> list[Job]:
    """The jobs the repo says exist, with their schedules read from its timers (05 plan C4).

    Backup nodes are those with any ``<app>/backup`` file, dump nodes those with a pg, mongo or
    sqlite line in one: the rule ``check-freshness.sh`` uses, so a new node's backup appears on the
    grid the day its first backup file lands. A timer that can't be read or parsed is left out (the
    grid says which): perch never guesses a schedule.
    """

    def read(path: str) -> str:
        try:
            return tree.read(path, fleet) if path in fleet.files else ""
        except CatTreeError:
            return ""

    jobs: list[Job] = []
    try:
        nightly = _onCalendar(read(NIGHTLY_TIMER))
    except ValueError as exc:
        log.warning("no nightly schedule: %s: %s", NIGHTLY_TIMER, exc)
        nightly = None
    for node in fleet.nodes:
        lines = [line for app in (*node.apps, *node.extras) for line in app.backup]
        if nightly is not None and any(app.backup for app in (*node.apps, *node.extras)):
            late, missing = THRESHOLDS["nightly"]
            dumps = any(_DUMP_LINE.match(line) for line in lines)
            jobs.append(Job(node.name, "nightly", nightly, late, missing, NIGHTLY_TIMER, dumps))
        for path in sorted(fleet.files):
            parts = path.split("/")
            if len(parts) == 4 and parts[1] == node.name and parts[2] == "restic" and parts[3] in TIMER_JOBS:
                name = TIMER_JOBS[parts[3]]
                try:
                    calendar = _onCalendar(read(path))
                except ValueError as exc:
                    log.warning("no schedule for %s: %s: %s", name, path, exc)
                    continue
                late, missing = THRESHOLDS[name]
                jobs.append(Job(node.name, name, calendar, late, missing, path))
    order = {n.name: i for i, n in enumerate(fleet.nodes)}
    return sorted(jobs, key=lambda j: (order.get(j.node, 99), JOB_ORDER.index(j.name)))


# -- judging a night ----------------------------------------------------------------------------


@dataclass(frozen=True)
class Cell:
    """One job on one night. ``level`` None means there is nothing to judge: not due yet, the
    timer doesn't fire that day, or the night is from before perch was watching."""

    level: B | None
    text: str
    slot: datetime | None = None
    run: GroomRun | None = None
    runs: int = 0


def slotOfRun(job: Job, run: GroomRun, tz: ZoneInfo) -> datetime | None:
    """Which night a run counts for: the latest slot it started at or after (give or take clock skew),
    within ``CREDIT`` of it. A run at 14:00 isn't last night's backup."""
    slot = job.latestSlot(run.start + SKEW, tz)
    return slot if slot is not None and run.start - slot <= CREDIT else None


def clockTime(moment: datetime, tz: ZoneInfo) -> str:
    return moment.astimezone(tz).strftime("%H:%M")


def judge(  # noqa: PLR0911 - one return per outcome reads better than a table
    job: Job, slot: datetime, runs: list[GroomRun], *, now: datetime, tz: ZoneInfo, watchedSince: datetime | None
) -> Cell:
    """The state of one night of one job. ``runs`` are the runs credited to ``slot``, oldest first."""
    if runs:
        last = runs[-1]
        if last.result != "success":
            code = f", exit {last.exitStatus}" if last.exitStatus not in ("", "0") else ""
            return Cell(B.hiss, f"failed ({last.result}{code})", slot, last, len(runs))
        lateBy = last.start - slot
        if lateBy >= job.late:
            return Cell(B.earTwitch, f"ran {duration(lateBy.total_seconds())} late", slot, last, len(runs))
        took = f", {duration((last.end - last.start).total_seconds())}" if last.end else ""
        retried = f", after {len(runs) - 1} failed {'try' if len(runs) == 2 else 'tries'}" if len(runs) > 1 else ""
        return Cell(B.slowBlink, f"ok{took}{retried}", slot, last, len(runs))
    elapsed = now - slot
    if elapsed < timedelta(0):
        return Cell(None, "not due yet", slot)
    if watchedSince is not None and slot < watchedSince - _HOUR:
        return Cell(None, "from before perch was watching", slot)
    due = clockTime(slot, tz)
    if elapsed >= job.missing:
        return Cell(B.hiss, f"missing: no record {duration(elapsed.total_seconds())} after {due}", slot)
    if elapsed >= job.late:
        return Cell(B.tailFlick, f"late: no record {duration(elapsed.total_seconds())} after {due}", slot)
    return Cell(B.slowBlink, f"due at {due}, not seen yet", slot)


# -- kitten's heartbeat -------------------------------------------------------------------------

HEARTBEAT = Rhythm(every=60, late=3, missing=10)  # design plan 3.4: late after 3 min, missing after 10


def heartbeatLevel(heardAt: datetime, now: datetime) -> B:
    silent = (now - heardAt).total_seconds()
    if silent >= HEARTBEAT.missing * HEARTBEAT.every:
        return B.hiss
    if silent >= HEARTBEAT.late * HEARTBEAT.every:
        return B.tailFlick
    return B.slowBlink


# -- the sense ----------------------------------------------------------------------------------


class Groom:
    """groom as a collector: every minute it reads cellar's own records, judges every watched job's
    latest night and every kitten's heartbeat, and writes the states and events. ``ingest`` is the
    other way in: what kitten sent, judged at once so the page doesn't wait for the next minute."""

    name = "groom"
    rhythm = Rhythm(every=60)

    def __init__(
        self,
        trail: ScentTrail,
        tree: CatTree,
        *,
        clock: Callable[[], datetime],
        tz: ZoneInfo,
        watched: Iterable[str] = (),
        groomDir: "Path | None" = None,
        sleepers: Iterable[str] = ("roastery",),
    ) -> None:
        self.trail = trail
        self.tree = tree
        self.clock = clock
        self.tz = tz
        self.watched = set(watched)
        self.groomDir = groomDir
        self.sleepers = set(sleepers)
        self._jobs: tuple[str, list[Job]] | None = None
        self._window: tuple[str, SleepWindow] | None = None
        self._read: dict[str, float] = {}

    # -- what is expected -------------------------------------------------------------------

    def jobs(self, fleet: "Fleet | None" = None) -> list[Job]:
        fleet = fleet or self.tree.fleet()
        if self._jobs is None or self._jobs[0] != fleet.commit:
            self._jobs = (fleet.commit, expectedJobs(self.tree, fleet))
        return self._jobs[1]

    def watchedNodes(self) -> set[str]:
        """Nodes whose records and heartbeat perch can receive: those with a kitten token, and cellar when
        its own records are mounted. Everything else isn't judged, so a node that isn't deployed yet
        doesn't hiss for ever."""
        nodes = set(self.watched)
        if self.groomDir is not None and self.groomDir.is_dir():
            nodes.add("cellar")
        return nodes

    def startedAt(self) -> datetime:
        """When groom first looked: nights before it aren't judged (a new deploy has no history)."""
        return parseUtc(self.trail.setMetaOnce("groomStartedAt", isoUtc(self.clock())))

    def sleepWindow(self, fleet: Fleet) -> SleepWindow:
        if self._window is None or self._window[0] != fleet.commit:
            self._window = (fleet.commit, sleepWindowFromRepo(self.tree, fleet, self.tz))
        return self._window[1]

    # -- the grid ---------------------------------------------------------------------------

    def cellFor(self, job: Job, slot: datetime, runs: list[GroomRun], now: datetime) -> Cell:
        credited = [r for r in runs if r.node == job.node and r.job == job.name and slotOfRun(job, r, self.tz) == slot]
        return judge(job, slot, credited, now=now, tz=self.tz, watchedSince=self.startedAt())

    def grid(self, nights: int, now: datetime) -> tuple[list[date], list[tuple[Job, list[Cell | None]]]]:
        """Days (oldest first, today last) and, per job, one cell per day (None: the timer doesn't fire)."""
        today = now.astimezone(self.tz).date()
        days = [today - timedelta(days=n) for n in range(nights - 1, -1, -1)]
        runs = self.trail.runs(since=datetime.combine(days[0], time(0), tzinfo=self.tz) - _HOUR * 12)
        rows = []
        for job in self.jobs():
            mine = [r for r in runs if r.node == job.node and r.job == job.name]
            cells: list[Cell | None] = []
            for day in days:
                slot = job.slotOn(day, self.tz)
                cells.append(self.cellFor(job, slot, mine, now) if slot else None)
            rows.append((job, cells))
        return days, rows

    def latest(self, job: Job, now: datetime) -> Cell | None:
        """The job's latest due night (or the one under way)."""
        slot = job.latestSlot(now, self.tz)
        if slot is None:
            return None
        runs = self.trail.runs(since=slot - _HOUR, node=job.node, job=job.name)
        return self.cellFor(job, slot, runs, now)

    # -- coming in --------------------------------------------------------------------------

    async def cycle(self) -> None:
        await asyncio.to_thread(self.step)

    async def aclose(self) -> None:
        return None

    def step(self) -> None:
        now = self.clock()
        self.startedAt()
        self.readDir()
        self.evaluate(now)

    def readDir(self) -> int:
        """Cellar's own records, read straight from ``PERCH_GROOM_DIR`` (design plan 4.2)."""
        if self.groomDir is None or not self.groomDir.is_dir():
            return 0
        stored = 0
        cutoff = self.clock().timestamp() - UNSEEN_AFTER.total_seconds()
        for path in sorted(self.groomDir.glob("*/*.json")):
            try:
                mtime = path.stat().st_mtime
                if mtime < cutoff or self._read.get(str(path)) == mtime:
                    continue
                self._read[str(path)] = mtime
                run = parseRecord(json.loads(path.read_text(encoding="utf-8")))
            except (OSError, ValueError) as exc:  # JSONDecodeError is a ValueError, as is RecordError
                log.warning("groom record %s/%s skipped: %s", path.parent.name, path.name, exc)
                continue
            stored += self.trail.addRun(run)
        return stored

    def ingest(self, node: str, heartbeat: dict | None, runs: list[GroomRun]) -> list[str]:
        """What a node's kitten sent. Returns the ``start`` of every run now stored (kitten stops
        re-sending those). Judged straight away."""
        now = self.clock()
        stored = []
        for run in runs:
            self.trail.addRun(run)
            stored.append(isoUtc(run.start))
        if heartbeat is not None:
            stamps = heartbeat.get("stamps") if isinstance(heartbeat.get("stamps"), dict) else {}
            clean = {k: int(v) for k, v in stamps.items() if STAMP_NAME.match(str(k)) and isinstance(v, int)}
            subject = f"kitten:{node}"
            before = self.trail.states().get(subject)
            self.trail.setState(
                subject,
                before.bodyLanguage if before else B.unknown,  # judged just below, against what it was
                title=before.title if before else None,
                seenAt=now,
                expectedRhythm=HEARTBEAT.every,
                detail={
                    "heardAt": isoUtc(now),
                    "version": str(heartbeat.get("version", ""))[:32],
                    "sentAt": str(heartbeat.get("sentAt", ""))[:32],
                    "stamps": dict(list(clean.items())[:10]),
                },
            )
            self._judgeKitten(self.tree.fleet(), node, self.trail.states()[subject], now, was=before)
        self.startedAt()
        self.evaluate(now)
        return stored

    # -- judging ----------------------------------------------------------------------------

    def evaluate(self, now: datetime) -> None:
        fleet = self.tree.fleet()
        watched = self.watchedNodes()
        states = self.trail.states()
        for job in self.jobs(fleet):
            if job.node in watched:
                self._judgeJob(job, states.get(job.subject), now)
        for node in sorted(watched):
            self._judgeKitten(fleet, node, states.get(f"kitten:{node}"), now)

    def _judgeJob(self, job: Job, before: State | None, now: datetime) -> None:
        cell = self.latest(job, now)
        if cell is None or cell.level is None:
            return
        stateTitle = f"{job.label}: {cell.text}"
        title = f"{job.node} {stateTitle}"
        self.trail.setState(
            job.subject,
            cell.level,
            title=stateTitle,
            seenAt=now,
            detail={"slot": isoUtc(cell.slot) if cell.slot else None, "job": job.name, "node": job.node},
        )
        if before is not None and before.bodyLanguage is cell.level:
            return
        slot = cell.slot.astimezone(self.tz).strftime("%Y-%m-%d") if cell.slot else ""
        if cell.level.rank >= B.tailFlick.rank:
            tail = cell.run.logTail if cell.run else None
            self.trail.addEvent(
                "groom", job.subject, cell.level, title, logTail=tail, litterId=f"{job.subject}@{slot}", seenAt=now
            )
        elif before is not None and before.bodyLanguage.rank >= B.tailFlick.rank:
            self.trail.addEvent(
                "groom", job.subject, cell.level, f"{title} (was {before.bodyLanguage.value})", seenAt=now
            )

    def _judgeKitten(
        self, fleet: Fleet, node: str, state: State | None, now: datetime, was: State | None = None
    ) -> None:
        subject = f"kitten:{node}"
        detail = dict((state.detail or {}) if state else {})
        detail.pop("mode", None)  # only set again below, while it is asleep
        heard = parseUtc(detail["heardAt"]) if detail.get("heardAt") else None
        if heard is None:
            level, title = B.unknown, "no heartbeat from kitten yet"
        else:
            level = heartbeatLevel(heard, now)
            silent = duration((now - heard).total_seconds())
            title = {
                B.hiss: f"kitten is silent: nothing for {silent}",
                B.tailFlick: f"kitten is late: nothing for {silent}",
            }.get(level, f"heard {silent} ago")
            if level.rank >= B.tailFlick.rank and node in self.sleepers:
                window = self.sleepWindow(fleet)
                if not window.mustAnswer(now):
                    level = B.slowBlink
                    title = f"asleep, as expected (wakes {window.nextWake(now).astimezone(self.tz).strftime('%H:%M')})"
                    detail["mode"] = "asleep"
        self.trail.setState(
            subject, level, title=title, seenAt=now, expectedRhythm=HEARTBEAT.every, detail=detail or None
        )
        state = was or state  # a heartbeat just written is judged against the level it replaced
        if state is not None and state.bodyLanguage is level:
            return
        if level.rank >= B.tailFlick.rank:
            self.trail.addEvent("perch", subject, level, f"{node}: {title}", seenAt=now)
        elif state is not None and state.bodyLanguage.rank >= B.tailFlick.rank:
            self.trail.addEvent(
                "perch", subject, level, f"{node}: kitten is back (was {state.bodyLanguage.value})", seenAt=now
            )
