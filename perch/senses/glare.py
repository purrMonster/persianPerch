"""glare: endpoints, from Gatus (design plan 4.3, 05 plan M4, A8).

One ``cycle`` reads Gatus (``gatus.py``) and writes a state ``glare:<key>`` per endpoint, and an event when
something a person should know about changes. Gatus stays the single source of truth for uptime; glare only
reads what it recorded.

Rules (design plan 3.4: "glare check, per Gatus interval, 2 fails late, 5 fails missing"):

- the newest result is a success -> slowBlink; the newest ``k`` results in a row failed: 1 is still
  slowBlink (a blip; the title says so), 2 or more -> tailFlick (late), 5 or more -> hiss (missing);
- an endpoint whose newest result is older than three of its own intervals (at least 5 minutes) is
  ``unknown``: Gatus has stopped checking it, which is not the same as it being up or down;
- **Gatus itself unreachable** is not a hiss per endpoint. After two failed cycles every endpoint turns
  ``unknown`` and no endpoint event is written; the collector's own rhythm (collectors.py) says "glare is
  late: ... can't see Gatus" once, as a tailFlick (design plan 8: "other senses continue").
- an endpoint Gatus no longer lists is forgotten (its state is dropped; its events stay).

Everything is judged from Gatus's own timestamps and the fake-able clock, so tests drive it with a
fixture and a FakeClock.
"""

from __future__ import annotations

from datetime import datetime
from statistics import median
from typing import Any

from ..bodyLanguage import BodyLanguage as B
from ..rhythms import Rhythm
from ..scentTrail import ScentTrail, State
from ..words import duration
from .gatus import GatusEndpoint, GatusError, GatusResult

LATE_FAILS, MISSING_FAILS = 2, 5
CONFIRM = 2  # failed cycles in a row before every endpoint is shown as unknown
MIN_SILENCE = 300  # seconds: the shortest silence that makes a check "unknown"
PREFIX = "glare:"


def failStreak(results: tuple[GatusResult, ...]) -> int:
    n = 0
    for r in reversed(results):
        if r.success:
            break
        n += 1
    return n


def interval(results: tuple[GatusResult, ...]) -> float | None:
    """The check's own rhythm in seconds: the median gap between its newest results."""
    gaps = [(b.at - a.at).total_seconds() for a, b in zip(results[-8:], results[-7:], strict=False)]
    return median(gaps) if gaps else None


def why(result: GatusResult) -> str:
    """One short reason from the newest failed result: the first error, else the first unmet condition."""
    if result.errors:
        return result.errors[0][:120]
    if result.failed:
        shown = result.failed[0][:100]
        more = f" (+{len(result.failed) - 1} more)" if len(result.failed) > 1 else ""
        return f"{shown}{more}"
    return f"HTTP {result.status}" if result.status else "no reason given"


class Glare:
    name = "glare"

    def __init__(self, gatus: Any, trail: ScentTrail, *, clock, every: int = 60) -> None:
        self.gatus = gatus
        self.trail = trail
        self.clock = clock
        self.rhythm = Rhythm(every=every)
        self._blind = 0

    async def aclose(self) -> None:
        await self.gatus.aclose()

    async def cycle(self) -> None:
        now = self.clock()
        try:
            endpoints = await self.gatus.statuses()
        except GatusError:
            self._goBlind(now)
            raise
        self._blind = 0
        prev = {s: st for s, st in self.trail.states().items() if s.startswith(PREFIX)}
        seen = set()
        for endpoint in endpoints:
            seen.add(PREFIX + endpoint.key)
            self._endpoint(endpoint, prev.get(PREFIX + endpoint.key), now)
        self.trail.forget([s for s in prev if s not in seen])

    def _goBlind(self, now: datetime) -> None:
        """Gatus can't be read. Two failed cycles in a row and every endpoint turns ``unknown``
        (stale green is worse than grey). No events: the collector's rhythm raises the one tailFlick."""
        self._blind += 1
        if self._blind < CONFIRM:
            return
        for subject, state in self.trail.states().items():
            if subject.startswith(PREFIX) and state.bodyLanguage is not B.unknown:
                self.trail.setState(subject, B.unknown, title="Gatus isn't answering", detail=state.detail, seenAt=now)

    def _endpoint(self, endpoint: GatusEndpoint, before: State | None, now: datetime) -> None:
        subject = PREFIX + endpoint.key
        level, title, detail = self._judge(endpoint, now)
        self.trail.setState(subject, level, title=title, detail=detail, seenAt=now)
        label = endpoint.name if not endpoint.group else f"{endpoint.name} ({endpoint.group})"
        if level.rank >= B.tailFlick.rank and (before is None or before.bodyLanguage is not level):
            self.trail.addEvent("glare", subject, level, f"{label}: {title}", detail=detail, seenAt=now)
        elif level is B.slowBlink and before and before.bodyLanguage.rank >= B.tailFlick.rank:
            lasted = duration((now - before.since).total_seconds())
            self.trail.addEvent(
                "glare", subject, B.slowBlink, f"{label} is back (was {before.bodyLanguage.value} for {lasted})",
                detail=detail, seenAt=now,
            )  # fmt: skip

    def _judge(self, endpoint: GatusEndpoint, now: datetime) -> tuple[B, str, dict[str, Any]]:
        results = endpoint.results
        detail: dict[str, Any] = {"name": endpoint.name, "group": endpoint.group, "key": endpoint.key}
        if not results:
            return B.unknown, "Gatus has no result for it yet", detail
        last = results[-1]
        every = interval(results)
        detail |= {
            "lastAt": last.at.isoformat(),
            "ms": round(last.ms),
            "recent": len(results),
            "recentOk": sum(1 for r in results if r.success),
            "everySeconds": round(every) if every else None,
        }
        silent = (now - last.at).total_seconds()
        limit = max(MIN_SILENCE, 3 * every) if every else MIN_SILENCE * 2
        if silent > limit:
            return B.unknown, f"Gatus hasn't recorded a check for {duration(silent)}", detail
        streak = failStreak(results)
        detail["failStreak"] = streak
        if streak >= MISSING_FAILS:
            return B.hiss, f"failed {streak} checks in a row: {why(last)}", detail
        if streak >= LATE_FAILS:
            return B.tailFlick, f"failed {streak} checks in a row: {why(last)}", detail
        if streak == 1:
            return B.slowBlink, f"last check failed ({why(last)}); tailFlick if the next fails too", detail
        return B.slowBlink, f"up, {round(last.ms)} ms", detail
