"""meow: alerts (design plan 5, 05 plan M3, ADR 0004).

meow reads what purr, groom, kitten and the collectors already wrote (the current state of every
subject), turns it into **litters** (one problem, told once), and decides what to push, when and where.
It runs as a collector on a 30 s rhythm, so a hung meow is noticed like any other.

Routing (05 plan A6, A7; every title starts ``perch:`` so old and new alerts run side by side):

========== ================================ ============================ =========================
level      channel                          timing                       repeat
========== ================================ ============================ =========================
hiss       ntfy (high) and the critical     at once, quiet hours ignored every 30 min until
           ntfy.sh topic                                                 acknowledged or cleared
tailFlick  ntfy                             batched for 5 min            at most once per 6 h
earTwitch  none: the 07:30 morning digest
slowBlink  none
========== ================================ ============================ =========================

A node that doesn't answer is one litter that absorbs its apps ("grinder unreachable: 12 apps
affected"); recovery is announced once; at most 10 pushes per 10 minutes per channel, and what the
limit holds back is never dropped: it stays a litter, visible on the page, and one summary push says
how many (a hiss is never the one held while a lower level could be). Everything meow does is a
scentTrail event.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from datetime import datetime, time, timedelta
from typing import Any
from zoneinfo import ZoneInfo

from . import ack
from .bodyLanguage import BodyLanguage as B
from .catTree import CatTree, Fleet
from .litters import Litter, Litters, label
from .ntfy import Ntfy, PushError
from .rhythms import Rhythm
from .rollup import Status
from .scentTrail import ScentTrail, State
from .scrub import scrub
from .words import duration

log = logging.getLogger("perch.meow")

REPEAT_HISS = timedelta(minutes=30)
BATCH = timedelta(minutes=5)
REPEAT_TAILFLICK = timedelta(hours=6)
WINDOW = timedelta(minutes=10)
LIMIT = 10  # pushes per channel per WINDOW
HISS_CAP = 9  # a hiss may use all but the last slot, which is the summary's
OTHER_CAP = 7  # everything else leaves three: a hiss is never the one held while a lower level could be
DIGEST_LINES = 12
DIGEST_WINDOW = timedelta(hours=4)  # how late in the morning a missed digest may still go
SUBJECT_KINDS = ("app", "node", "groom", "kitten", "collector")
CHANNELS = ("ntfy", "critical")


def parseQuiet(text: str) -> tuple[time, time]:
    """'23:00-07:00' -> (23:00, 07:00). ValueError when it isn't that."""
    start, _, end = text.partition("-")
    return time.fromisoformat(start.strip()), time.fromisoformat(end.strip())


def inQuiet(local: time, quiet: tuple[time, time]) -> bool:
    start, end = quiet
    if start == end:
        return False
    return start <= local < end if start < end else local >= start or local < end


@dataclass(frozen=True)
class Problem:
    key: str
    kind: str
    level: B
    title: str
    members: int = 1


@dataclass
class Found:
    problems: list[Problem] = field(default_factory=list)
    keepOpen: set[str] = field(default_factory=set)  # can't see right now: neither new nor cleared
    absorbed: set[str] = field(default_factory=set)  # folded into a node's litter


def _owner(subject: str) -> str | None:
    kind, _, rest = subject.partition(":")
    if kind in ("app", "groom"):
        return rest.partition("/")[0]
    return rest if kind in ("node", "kitten") else None


def findProblems(states: dict[str, State], fleet: Fleet) -> Found:
    """What is wrong right now, as litters. A node purr marks unreachable is one litter that absorbs
    every subject of that node (its apps, backups and kitten); a subject whose state is ``unknown``
    keeps whatever litter it has (perch can't see: that isn't recovery)."""
    found = Found()
    down: set[str] = set()
    for node in fleet.nodes:
        state = states.get(f"node:{node.name}")
        if state and state.bodyLanguage is B.hiss and (state.detail or {}).get("mode") == "unreachable":
            down.add(node.name)
            apps = sum(1 for a in node.apps if Status.watched(a))
            what = f"{apps} app{'s' if apps != 1 else ''} affected"
            title = f"{node.name} unreachable: {what}"
            found.problems.append(Problem(f"down:{node.name}", "down", B.hiss, title, apps))
    for subject in sorted(states):
        state = states[subject]
        kind, _, rest = subject.partition(":")
        if kind not in SUBJECT_KINDS:
            continue
        if _owner(subject) in down:
            found.absorbed.add(subject)
            continue
        level = state.bodyLanguage
        if level is B.unknown:
            found.keepOpen.add(subject)
        elif level.rank >= B.tailFlick.rank or level is B.earTwitch:
            name = f"{rest} kitten" if kind == "kitten" else "" if kind == "collector" else rest
            title = f"{name}: {state.title}" if name and state.title else (state.title or name or subject)
            found.problems.append(Problem(subject, "state", level, title))
    return found


@dataclass
class Out:
    """One message meow wants to send."""

    rank: int  # 0 hiss, 1 hiss recovery, 2 tailFlick, 3 recovery, 4 digest: the order of importance
    kind: str
    litters: list[Litter]
    title: str
    message: str
    priority: int
    tags: tuple[str, ...]
    channels: tuple[str, ...]
    button: Litter | None = None  # the one litter an acknowledge button on the ntfy copy would stop
    repeat: bool = False


class Meow:
    name = "meow"

    def __init__(
        self,
        trail: ScentTrail,
        tree: CatTree,
        *,
        clock,
        tz: ZoneInfo,
        ntfy: Ntfy | None = None,
        critical: Ntfy | None = None,
        ackSecret: str = "",
        publicUrl: str = "",
        quiet: str = "23:00-07:00",
        digestAt: str = "07:30",
        every: int = 30,
        secrets: tuple[str, ...] = (),
    ) -> None:
        self.trail = trail
        self.tree = tree
        self.clock = clock
        self.tz = tz
        self.store = Litters(trail)
        self.clients: dict[str, Ntfy] = {k: c for k, c in (("ntfy", ntfy), ("critical", critical)) if c is not None}
        self.ackSecret = ackSecret
        self.publicUrl = publicUrl.rstrip("/")
        self.rhythm = Rhythm(every=every)
        self._secrets = [s for s in secrets if s]
        try:
            self.quiet = parseQuiet(quiet)
        except ValueError:
            log.warning("PERCH_MEOW_QUIET isn't HH:MM-HH:MM; using 23:00-07:00")
            self.quiet = (time(23), time(7))
        try:
            self.digestAt = time.fromisoformat(digestAt)
        except ValueError:
            log.warning("PERCH_MEOW_DIGEST isn't HH:MM; using 07:30")
            self.digestAt = time(7, 30)
        self._failing: dict[str, str] = {}  # channel -> why, while its pushes fail

    @property
    def configured(self) -> bool:
        return bool(self.clients)

    async def aclose(self) -> None:
        for client in self.clients.values():
            await client.aclose()

    def isQuiet(self, moment: datetime) -> bool:
        return inQuiet(moment.astimezone(self.tz).time(), self.quiet)

    # -- one cycle -----------------------------------------------------------------------------

    async def cycle(self) -> None:
        now = self.clock()
        fleet = await asyncio.to_thread(self.tree.fleet)
        self.reconcile(now, findProblems(self.trail.states(), fleet))
        await self.deliver(now, self.plan(now))

    # -- litters follow the states ---------------------------------------------------------------

    def reconcile(self, now: datetime, found: Found) -> None:
        store = self.store
        open_ = {lt.key: lt for lt in store.open()}
        for problem in found.problems:
            lt = open_.pop(problem.key, None)
            if lt is None:
                store.create(
                    problem.key, problem.kind, problem.level, problem.title, problem.members,
                    now=now, digest=problem.level is B.earTwitch,
                )  # fmt: skip
                continue
            changes: dict[str, Any] = {"title": problem.title, "members": problem.members}
            if problem.level is not lt.level:
                changes.update(level=problem.level, levelAt=now, peak=max(lt.peak, problem.level, key=lambda x: x.rank))
                if problem.level is B.hiss:  # a worse problem is news again, acknowledged or not
                    changes.update(lastPushAt=None, ackedAt=None, ackedVia=None, heldAt=None)
                if problem.level is B.earTwitch:
                    changes["digest"] = True
                elif lt.level is B.earTwitch:
                    changes.update(digest=self.isQuiet(now), digestedAt=None)
            store.update(lt.litterId, **changes)
        for lt in open_.values():
            if lt.key in found.keepOpen:
                continue
            if lt.key in found.absorbed:  # folded into its node's litter: no recovery of its own
                store.update(lt.litterId, closedAt=now, recoveredAt=now)
                self._event(lt, B.slowBlink, f"folded into its node's litter: {lt.title}", now)
                continue
            store.update(lt.litterId, closedAt=now)
            if lt.pushes == 0 and lt.peak.rank >= B.tailFlick.rank:
                self._event(lt, B.slowBlink, f"cleared before meow sent anything: {lt.title}", now)
            if lt.pushes == 0:
                store.update(lt.litterId, recoveredAt=now)  # nothing was announced, so nothing to take back

    # -- what to send ------------------------------------------------------------------------------

    def plan(self, now: datetime) -> list[Out]:
        outs: list[Out] = []
        due: list[Litter] = []
        for lt in self.store.open():
            if lt.ackedAt or lt.level.rank < B.tailFlick.rank or lt.level is B.unknown:
                continue
            if lt.level is B.hiss:
                if lt.lastPushAt is None or now - lt.lastPushAt >= REPEAT_HISS:
                    outs.append(self._hiss(lt, now))
                continue
            first = lt.lastPushAt is None
            ready = (now - lt.levelAt >= BATCH) if first else (now - lt.lastPushAt >= REPEAT_TAILFLICK)  # type: ignore[operator]
            if self.isQuiet(lt.levelAt) if first else (ready and self.isQuiet(now)):
                if not lt.digest:  # waits for the morning digest, which says it was held
                    self.store.update(lt.litterId, digest=True, digestedAt=None)
                    self._event(lt, B.earTwitch, f"held for the morning digest (quiet hours): {lt.title}", now)
                continue
            if lt.digest and lt.digestedAt is None:
                continue  # held in quiet hours: the digest carries it, even after 07:00
            if ready:
                due.append(lt)
        if len(due) == 1:
            outs.append(self._tail(due[0], now))
        elif due:
            outs.append(self._batch(due, now))
        outs.extend(self._recoveries(now))
        digest = self._digest(now)
        if digest:
            outs.append(digest)
        return outs

    def _hiss(self, lt: Litter, now: datetime) -> Out:
        repeat = lt.pushes > 0
        up = duration((now - lt.openedAt).total_seconds())
        title = f"perch: still unacknowledged: {lt.title}" if repeat else f"perch: {lt.title}"
        message = f"hiss for {up}. " + (f"Pushed {lt.pushes} time{'s' if lt.pushes != 1 else ''}. " if repeat else "")
        message += "Acknowledge it on the page or with the button to stop the repeats."
        kind = "repeat" if repeat else "hiss"
        return Out(0, kind, [lt], title, message, 4, ("rotating_light",), CHANNELS, lt, repeat)

    def _tail(self, lt: Litter, now: datetime) -> Out:
        repeat = lt.pushes > 0
        title = f"perch: still: {lt.title}" if repeat else f"perch: {lt.title}"
        message = f"tailFlick for {duration((now - lt.openedAt).total_seconds())}."
        return Out(2, "tailFlick", [lt], title, message, 3, ("warning",), ("ntfy",), lt, repeat)

    def _batch(self, litters: list[Litter], now: datetime) -> Out:
        lines = [f"{lt.title}" for lt in litters[:DIGEST_LINES]]
        if len(litters) > DIGEST_LINES:
            lines.append(f"and {len(litters) - DIGEST_LINES} more")
        title = f"perch: {len(litters)} things need a look"
        return Out(2, "batch", litters, title, "\n".join(lines), 3, ("warning",), ("ntfy",))

    def _recoveries(self, now: datetime) -> list[Out]:
        ready: dict[bool, list[Litter]] = {True: [], False: []}  # by "peaked at hiss"
        for lt in self.store.pendingRecovery():
            hissed = lt.peak is B.hiss
            if hissed or not self.isQuiet(now):  # a tailFlick's good news can wait for the morning
                ready[hissed].append(lt)
        outs = []
        for hissed, items in ready.items():
            if not items:
                continue
            channels = tuple(c for c in CHANNELS if c in {ch for lt in items for ch in lt.channels}) or ("ntfy",)
            if len(items) == 1:
                lt = items[0]
                took = duration(((lt.closedAt or now) - lt.openedAt).total_seconds())
                was = "down" if lt.kind == "down" else lt.peak.value
                title = f"perch: {lt.name} back, was {was} for {took}"
                message = f"{lt.title}. It has cleared."
            else:
                title = f"perch: {len(items)} things are back"
                message = "\n".join(f"{lt.name}: was {lt.peak.value}" for lt in items[:DIGEST_LINES])
            outs.append(Out(1 if hissed else 3, "recovery", items, title, message, 3, ("white_check_mark",), channels))
        return outs

    def _digest(self, now: datetime) -> Out | None:
        local = now.astimezone(self.tz)
        today = local.date().isoformat()
        start = datetime.combine(local.date(), self.digestAt, tzinfo=self.tz)
        if not start <= local < start + DIGEST_WINDOW or self.store.meta("meow.digestDay") == today:
            return None  # it is a morning thing: a perch that was down at 07:30 doesn't send it at midnight
        items = self.store.pendingDigest()
        if not items:
            self.store.setMeta("meow.digestDay", today)  # nothing overnight: no push, and not asked again today
            return None
        lines = [f"{lt.peak.value}: {lt.title}" + ("" if lt.isOpen else " (cleared)") for lt in items[:DIGEST_LINES]]
        if len(items) > DIGEST_LINES:
            lines.append(f"and {len(items) - DIGEST_LINES} more")
        title = f"perch: morning digest, {len(items)} thing{'s' if len(items) != 1 else ''} overnight"
        return Out(4, "digest", items, title, "\n".join(lines), 3, ("coffee",), ("ntfy",))

    # -- sending -----------------------------------------------------------------------------------

    def _actions(self, out: Out, channel: str, now: datetime) -> tuple[dict[str, Any], ...]:
        """The acknowledge button: only on the self-hosted ntfy (a third party would see the link), only
        on a push about exactly one litter, only when perch knows its own address and has a secret."""
        if channel != "ntfy" or out.button is None or not self.ackSecret or not self.publicUrl:
            return ()
        token = ack.mint(self.ackSecret, out.button.litterId, now)
        url = f"{self.publicUrl}/ack/t/{token}"
        return ({"action": "http", "label": "Acknowledge", "url": url, "method": "POST", "clear": True},)

    async def deliver(self, now: datetime, outs: list[Out]) -> None:
        if not self.clients or not outs:
            return
        outs.sort(key=lambda o: (o.rank, o.repeat, min(lt.openedAt for lt in o.litters)))
        heldOn: set[str] = set()
        for out in outs:
            sent: list[str] = []
            blocked = 0
            for channel in out.channels:
                client = self.clients.get(channel)
                if client is None:
                    continue
                cap = HISS_CAP if out.rank <= 1 else OTHER_CAP
                if self.store.pushCount(channel, now, WINDOW) >= cap:
                    blocked += 1
                    heldOn.add(channel)
                    continue
                if await self._send(channel, client, out, now):
                    sent.append(channel)
            if sent:
                self._sent(out, sent, now)
            elif blocked:
                self._held(out, now)
        for channel in sorted(heldOn):
            await self._summary(channel, now)

    async def _send(self, channel: str, client: Ntfy, out: Out, now: datetime) -> bool:
        try:
            await client.send(
                title=out.title, message=out.message, priority=out.priority, tags=out.tags,
                actions=self._actions(out, channel, now),
            )  # fmt: skip
        except PushError as exc:
            why = scrub(str(exc), self._secrets, limit=100)
            if channel not in self._failing:  # said once per outage
                log.warning("meow can't push to %s: %s", channel, why)
                self.trail.addEvent(
                    "perch", f"meow:{channel}", B.tailFlick,
                    f"meow can't reach {channel}: {why}; the alerts are kept and tried again", seenAt=now,
                )  # fmt: skip
            self._failing[channel] = why
            return False
        if channel in self._failing:
            del self._failing[channel]
            self.trail.addEvent("perch", f"meow:{channel}", B.slowBlink, f"meow reaches {channel} again", seenAt=now)
        self.store.recordPush(channel, out.litters[0].litterId if len(out.litters) == 1 else None, out.kind, now)
        return True

    def _sent(self, out: Out, channels: list[str], now: datetime) -> None:
        where = " and ".join(channels)
        for lt in out.litters:
            merged = ",".join(dict.fromkeys([*lt.channels, *channels]))
            if out.kind == "recovery":
                self.store.update(lt.litterId, recoveredAt=now)
                said = out.title.removeprefix("perch: ")
                self._event(lt, B.slowBlink, f"meow announced recovery on {where}: {said}", now)
            elif out.kind == "digest":
                changes: dict[str, Any] = {"digestedAt": now}
                if lt.isOpen and lt.level is not B.earTwitch:  # the digest told them: the 6 h clock starts
                    changes.update(lastPushAt=now, pushes=lt.pushes + 1, channels=merged)
                self.store.update(lt.litterId, **changes)
            else:
                self.store.update(
                    lt.litterId, lastPushAt=now, pushes=lt.pushes + 1, channels=merged, heldAt=None
                )  # fmt: skip
                what = {"repeat": "repeated", "batch": "batched into one push"}.get(out.kind, "pushed")
                self._event(lt, lt.level, f"meow {what} ({lt.level.value}) on {where}: {lt.title}", now)
        if out.kind == "digest":
            day = now.astimezone(self.tz).date().isoformat()
            self.store.setMeta("meow.digestDay", day)
            text = f"meow sent the morning digest: {len(out.litters)} items"
            self.trail.addEvent("perch", "meow:digest", B.earTwitch, text, seenAt=now)

    def _held(self, out: Out, now: datetime) -> None:
        for lt in out.litters:
            if out.kind == "recovery" or lt.heldAt is not None or out.kind == "digest":
                continue
            self.store.update(lt.litterId, heldAt=now)
            self._event(lt, B.earTwitch, f"held back by the rate limit (10 pushes per 10 min): {lt.title}", now)

    async def _summary(self, channel: str, now: datetime) -> None:
        if self.store.summaryIn(channel, now, WINDOW) or self.store.pushCount(channel, now, WINDOW) >= LIMIT:
            return
        count = len(self.store.held())
        if not count:
            return
        client = self.clients[channel]
        try:
            await client.send(
                title=f"perch: {count} alert{'s' if count != 1 else ''} held back",
                message=f"Over {LIMIT} pushes in {int(WINDOW.total_seconds() // 60)} minutes. "
                "Nothing is dropped: they are listed on the perch page and go out as the limit allows.",
                priority=3, tags=("hourglass_flowing_sand",),
            )  # fmt: skip
        except PushError:
            return
        self.store.recordPush(channel, None, "summary", now)
        text = f"meow said {count} alerts are held on {channel}"
        self.trail.addEvent("perch", "meow:summary", B.earTwitch, text, seenAt=now)

    # -- events ------------------------------------------------------------------------------------

    def _event(self, lt: Litter, level: B, text: str, now: datetime) -> None:
        self.trail.addEvent("perch", lt.subject, level, text, litterId=lt.litterId, seenAt=now)

    # -- for the pages -----------------------------------------------------------------------------

    def acknowledged(self, lt: Litter, via: str, now: datetime) -> None:
        self._event(lt, B.slowBlink, f"acknowledged {via}: {lt.title}", now)


def buildMeow(settings: Any, trail: ScentTrail, tree: CatTree, clock: Any, tz: ZoneInfo) -> Meow:
    """meow from the settings. A push URL that can't be used is said once on the trail and left out; it
    never stops perch (nor puts the URL in the message)."""
    clients: dict[str, Ntfy | None] = {"ntfy": None, "critical": None}
    for channel, url, token in (
        ("ntfy", settings.meowNtfyUrl, settings.meowNtfyToken),
        ("critical", settings.meowCriticalUrl, ""),
    ):
        if not url:
            continue
        try:
            clients[channel] = Ntfy(url, token)
        except ValueError:
            log.warning("meow's %s URL isn't usable: it must look like https://host/topic", channel)
            trail.addEvent("perch", f"meow:{channel}", B.tailFlick, f"meow's {channel} URL isn't usable (https://host/topic)")
    return Meow(
        trail, tree, clock=clock, tz=tz, ntfy=clients["ntfy"], critical=clients["critical"],
        ackSecret=settings.ackSecret, publicUrl=settings.publicUrl, quiet=settings.meowQuiet,
        digestAt=settings.meowDigest, secrets=tuple(settings.secretValues()),
    )  # fmt: skip


__all__ = ["Found", "Meow", "Out", "Problem", "buildMeow", "findProblems", "inQuiet", "label", "parseQuiet"]
