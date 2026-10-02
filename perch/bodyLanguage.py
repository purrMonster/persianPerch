"""bodyLanguage: persianPerch's severity levels and the worst-of rollup.

Four levels from the spec (design plan 6.1), plus ``unknown`` for "no data yet /
source unreachable" (design plan 8: purr shows unknown, grey, when Komodo is down).

Rollup order, best to worst (runbook 2026-09-30, M0 entry):

    slowBlink < earTwitch < unknown < tailFlick < hiss

``unknown`` outranks earTwitch so that a routine notice never hides the fact that
perch can't see something, and ranks below tailFlick/hiss so it never masks a
real problem.
"""

from __future__ import annotations

from collections.abc import Iterable
from dataclasses import dataclass
from enum import StrEnum


@dataclass(frozen=True)
class _Look:
    rank: int
    icon: str
    colour: str
    standard: str
    meaning: str


class BodyLanguage(StrEnum):
    slowBlink = "slowBlink"
    earTwitch = "earTwitch"
    unknown = "unknown"
    tailFlick = "tailFlick"
    hiss = "hiss"

    @property
    def look(self) -> _Look:
        return _LOOKS[self]

    @property
    def rank(self) -> int:
        return self.look.rank

    @property
    def icon(self) -> str:
        return self.look.icon

    @property
    def colour(self) -> str:
        return self.look.colour

    @property
    def meaning(self) -> str:
        return self.look.meaning

    @property
    def standard(self) -> str:
        return self.look.standard

    @classmethod
    def parse(cls, value: "str | BodyLanguage") -> "BodyLanguage":
        if isinstance(value, BodyLanguage):
            return value
        try:
            return cls(value)
        except ValueError as exc:
            raise ValueError(f"not a bodyLanguage level: {value!r}") from exc


_LOOKS: dict[BodyLanguage, _Look] = {
    BodyLanguage.slowBlink: _Look(0, "·", "#6fa287", "OK / info", "OK / info"),
    BodyLanguage.earTwitch: _Look(1, "◦", "#6b8fb3", "notice", "notice: expected event"),
    BodyLanguage.unknown: _Look(2, "?", "#6d6259", "unknown", "no data yet"),
    BodyLanguage.tailFlick: _Look(3, "~", "#d9953b", "warn", "warn: degraded, late, retrying"),
    BodyLanguage.hiss: _Look(4, "!", "#c8453b", "critical", "critical: needs barista"),
}

# The four spec levels, in legend order (unknown is a display state, not a level).
LEVELS: tuple[BodyLanguage, ...] = (
    BodyLanguage.slowBlink,
    BodyLanguage.earTwitch,
    BodyLanguage.tailFlick,
    BodyLanguage.hiss,
)


def worstOf(levels: Iterable["str | BodyLanguage"], empty: BodyLanguage = BodyLanguage.unknown) -> BodyLanguage:
    """The worst level among ``levels``; ``empty`` when there are none."""
    worst: BodyLanguage | None = None
    for value in levels:
        level = BodyLanguage.parse(value)
        if worst is None or level.rank > worst.rank:
            worst = level
    return worst if worst is not None else empty
