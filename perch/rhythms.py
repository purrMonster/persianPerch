"""rhythms: when each watched thing is next expected, and what silence means.

"Silence is a signal" (design plan 3.4). Three small pieces, all pure so a fake clock
can drive them:

- ``Rhythm``: a collector's cadence. Missed cycles become tailFlick (late) and then
  hiss (missing).
- ``OnCalendar``: the few systemd timer forms the fleet's timers use (05 plan C4).
- ``SleepWindow``: roastery sleeps; cellar wakes it nightly (05 plan C5). Unreachable
  outside the window is slowBlink, unreachable inside it is hiss.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from .bodyLanguage import BodyLanguage
from .catTree import CatTree, CatTreeError, Fleet

# -- a collector's rhythm -------------------------------------------------------


@dataclass(frozen=True)
class Rhythm:
    """``every`` seconds. ``late`` missed cycles are a tailFlick, ``missing`` a hiss
    (design plan 3.4: purr every 30 s, late after 3 misses, missing after 10)."""

    every: int
    late: int = 3
    missing: int = 10

    @property
    def grace(self) -> int:
        """A cycle in flight isn't a miss: it may take a third of the period to finish."""
        return max(1, self.every // 3)

    def misses(self, since: datetime, now: datetime) -> int:
        """Whole cycles that should have succeeded since ``since`` (the last success)."""
        elapsed = (now - since).total_seconds() - self.grace
        return int(elapsed // self.every) if elapsed > 0 else 0

    def level(self, since: datetime, now: datetime) -> BodyLanguage:
        missed = self.misses(since, now)
        if missed >= self.missing:
            return BodyLanguage.hiss
        if missed >= self.late:
            return BodyLanguage.tailFlick
        return BodyLanguage.slowBlink


# -- systemd OnCalendar ---------------------------------------------------------

_WEEKDAYS = ("Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun")
_ON_CALENDAR = re.compile(
    rf"^(?:(?P<dow>{'|'.join(_WEEKDAYS)})\s+)?\*-\*-(?P<day>\*|\d{{1,2}})\s+"
    r"(?P<h>\d{1,2}):(?P<m>\d{2})(?::(?P<s>\d{2}))?$"
)


@dataclass(frozen=True)
class OnCalendar:
    """``*-*-* 01:25:00``, ``Sun *-*-* 03:00:00`` or ``*-*-01 04:30:00``: every form the
    fleet's timers use. Anything else is refused loudly rather than guessed."""

    time: time
    weekday: int | None = None  # 0 = Monday
    day: int | None = None  # day of the month

    @classmethod
    def parse(cls, text: str) -> OnCalendar:
        match = _ON_CALENDAR.match(text.strip())
        if not match:
            raise ValueError(f"unsupported OnCalendar {text!r}")
        try:
            at = time(int(match["h"]), int(match["m"]), int(match["s"] or 0))
        except ValueError as exc:
            raise ValueError(f"unsupported OnCalendar {text!r}: {exc}") from exc
        return cls(
            time=at,
            weekday=_WEEKDAYS.index(match["dow"]) if match["dow"] else None,
            day=None if match["day"] == "*" else int(match["day"]),
        )

    def matches(self, day: date) -> bool:
        return (self.weekday is None or day.weekday() == self.weekday) and (self.day is None or day.day == self.day)


# -- roastery's sleep window ----------------------------------------------------

WAKE_TIMER = "stacks/cellar/restic/purrbrews-wake-roastery.timer"
WAKE_SETUP = "stacks/roastery/backup-target/setup.ps1"
ROASTERY_WAKE_DEFAULT = time(1, 25)
ROASTERY_STAY_UP_DEFAULT = timedelta(minutes=180)
ROASTERY_SETTLE_DEFAULT = timedelta(minutes=10)

_ON_CALENDAR_LINE = re.compile(r"^OnCalendar=(?P<value>.+)$", re.MULTILINE)
_UNATTENDED = re.compile(r"\$UnattendedSleepMinutes\s*=\s*(?P<minutes>\d+)")


@dataclass(frozen=True)
class SleepWindow:
    """cellar wakes roastery at ``wake`` (local time); a machine woken with nobody at it
    stays up ``stayUp`` (Windows' unattended-sleep timeout) and may take ``settle`` to
    answer after the wake (the nightly backup waits up to 10 minutes for it, 05 plan C3)."""

    wake: time
    stayUp: timedelta
    settle: timedelta
    tz: ZoneInfo
    source: str = "default"  # "repo", "repo+default" or "default": where wake and stayUp came from

    def _starts(self, local: datetime) -> list[datetime]:
        return [
            datetime.combine(local.date() + timedelta(days=offset), self.wake, tzinfo=self.tz) for offset in (-1, 0, 1)
        ]

    def expectedUp(self, now: datetime) -> bool:
        """Inside a wake window: roastery may be up."""
        local = now.astimezone(self.tz)
        return any(start <= local < start + self.stayUp for start in self._starts(local))

    def mustAnswer(self, now: datetime) -> bool:
        """Inside a window and past the settling time: roastery is expected to answer, so
        silence is a hiss. Outside it, silence is just sleep."""
        local = now.astimezone(self.tz)
        return any(start + self.settle <= local < start + self.stayUp for start in self._starts(local))

    def nextWake(self, now: datetime) -> datetime:
        local = now.astimezone(self.tz)
        return min(start for start in self._starts(local) if start > local)


def sleepWindowFromRepo(tree: CatTree, fleet: Fleet, tz: ZoneInfo) -> SleepWindow:
    """Roastery's window from the fleet repo itself, so it can't drift from the timers:
    the wake time is cellar's wake-roastery timer, the stay-up time is the unattended
    sleep timeout roastery's backup-target setup configures. Falls back to the values
    the repo has today (01:25, three hours) when a file can't be read."""
    wake, stayUp = None, None
    try:
        timer = _ON_CALENDAR_LINE.search(tree.read(WAKE_TIMER, fleet))
        if timer:
            wake = OnCalendar.parse(timer["value"]).time
    except (CatTreeError, ValueError):
        pass
    try:
        found = _UNATTENDED.search(tree.read(WAKE_SETUP, fleet))
        if found:
            stayUp = timedelta(minutes=int(found["minutes"]))
    except CatTreeError:
        pass
    fromRepo = [x is not None for x in (wake, stayUp)]
    source = "repo" if all(fromRepo) else "repo+default" if any(fromRepo) else "default"
    return SleepWindow(
        wake=wake or ROASTERY_WAKE_DEFAULT,
        stayUp=stayUp or ROASTERY_STAY_UP_DEFAULT,
        settle=ROASTERY_SETTLE_DEFAULT,
        tz=tz,
        source=source,
    )
