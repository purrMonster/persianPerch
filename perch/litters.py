"""litters: the store behind meow (ADR 0004). A litter is one problem meow tells the owner about once.

The rows live in scentTrail's database (migration 4) so a restart forgets nothing: what is due, held,
acknowledged or recovered is read from them, never kept only in memory. Everything meow decides
(``meow.py``) and everything the pages show (``windowsill``) goes through this class.
"""

from __future__ import annotations

import re
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timedelta

from .bodyLanguage import BodyLanguage
from .scentTrail import ScentTrail, isoUtc, parseUtc

_EDITABLE = {
    "kind", "level", "peak", "title", "members", "levelAt", "closedAt", "ackedAt", "ackedVia",
    "lastPushAt", "pushes", "channels", "digest", "digestedAt", "heldAt", "recoveredAt",
}  # fmt: skip


def slug(key: str) -> str:
    """A subject key as a path-safe word: ``app:grinder/n8n`` -> ``app.grinder.n8n`` (no slash, so
    ``/ack/{litterId}`` stays one path segment)."""
    return re.sub(r"[^A-Za-z0-9_-]+", ".", key).strip(".")


def label(key: str) -> str:
    """What a person calls it: ``app:grinder/n8n`` -> ``grinder/n8n``, ``down:grinder`` -> ``grinder``."""
    return key.partition(":")[2] or key


def subjectOf(key: str) -> str:
    """The scentTrail subject a litter's events carry (``down:grinder`` is the node's own)."""
    return "node:" + label(key) if key.startswith("down:") else key


@dataclass(frozen=True)
class Litter:
    litterId: str
    key: str
    kind: str  # "down" (a node that doesn't answer, absorbing its apps) or "state"
    level: BodyLanguage
    peak: BodyLanguage
    title: str
    members: int
    openedAt: datetime
    levelAt: datetime
    closedAt: datetime | None
    ackedAt: datetime | None
    ackedVia: str | None
    lastPushAt: datetime | None
    pushes: int
    channels: tuple[str, ...]
    digest: bool
    digestedAt: datetime | None
    heldAt: datetime | None
    recoveredAt: datetime | None

    @property
    def isOpen(self) -> bool:
        return self.closedAt is None

    @property
    def name(self) -> str:
        return label(self.key)

    @property
    def subject(self) -> str:
        return subjectOf(self.key)


def _t(text: str | None) -> datetime | None:
    return parseUtc(text) if text else None


def _litter(row: sqlite3.Row) -> Litter:
    return Litter(
        litterId=row["litterId"],
        key=row["key"],
        kind=row["kind"],
        level=BodyLanguage(row["level"]),
        peak=BodyLanguage(row["peak"]),
        title=row["title"],
        members=row["members"],
        openedAt=parseUtc(row["openedAt"]),
        levelAt=parseUtc(row["levelAt"]),
        closedAt=_t(row["closedAt"]),
        ackedAt=_t(row["ackedAt"]),
        ackedVia=row["ackedVia"],
        lastPushAt=_t(row["lastPushAt"]),
        pushes=row["pushes"],
        channels=tuple(c for c in row["channels"].split(",") if c),
        digest=bool(row["digest"]),
        digestedAt=_t(row["digestedAt"]),
        heldAt=_t(row["heldAt"]),
        recoveredAt=_t(row["recoveredAt"]),
    )


class Litters:
    def __init__(self, trail: ScentTrail) -> None:
        self.trail = trail

    # -- reading ---------------------------------------------------------------------------

    def _select(self, where: str, args: tuple = (), order: str = "openedAt") -> list[Litter]:
        sql = f"SELECT * FROM litters WHERE {where} ORDER BY {order}"  # noqa: S608 - fixed clauses from this file
        return [_litter(r) for r in self.trail.fetch(sql, args)]

    def get(self, litterId: str) -> Litter | None:
        found = self._select("litterId = ?", (litterId,))
        return found[0] if found else None

    def open(self) -> list[Litter]:
        return self._select("closedAt IS NULL")

    def pendingRecovery(self) -> list[Litter]:
        """Closed litters that were pushed and whose recovery hasn't been announced yet."""
        return self._select("closedAt IS NOT NULL AND pushes > 0 AND recoveredAt IS NULL", order="closedAt")

    def pendingDigest(self) -> list[Litter]:
        return self._select("digest = 1 AND digestedAt IS NULL", order="openedAt")

    def held(self) -> list[Litter]:
        return self._select("closedAt IS NULL AND heldAt IS NOT NULL", order="openedAt")

    def recentClosed(self, since: datetime, limit: int = 20) -> list[Litter]:
        sql = "SELECT * FROM litters WHERE closedAt IS NOT NULL AND closedAt >= ? ORDER BY closedAt DESC LIMIT ?"
        return [_litter(r) for r in self.trail.fetch(sql, (isoUtc(since), limit))]

    # -- writing ---------------------------------------------------------------------------

    def create(
        self, key: str, kind: str, level: BodyLanguage, title: str, members: int, *, now: datetime, digest: bool = False
    ) -> Litter:
        stamp = now.strftime("%Y%m%dT%H%M%SZ")
        litterId = f"{slug(key)}@{stamp}"
        self.trail.execute(
            "INSERT INTO litters (litterId, key, kind, level, peak, title, members, openedAt, levelAt, digest) "
            "VALUES (?,?,?,?,?,?,?,?,?,?)",
            (litterId, key, kind, level.value, level.value, title, members, isoUtc(now), isoUtc(now), int(digest)),
        )
        return self._select("litterId = ?", (litterId,))[0]

    def update(self, litterId: str, **changes: object) -> None:
        sets, args = [], []
        for column, value in changes.items():
            if column not in _EDITABLE:
                raise ValueError(f"not an editable litter column: {column}")
            sets.append(f"{column} = ?")
            if isinstance(value, BodyLanguage):
                args.append(value.value)
            elif isinstance(value, datetime):
                args.append(isoUtc(value))
            elif isinstance(value, bool):
                args.append(int(value))
            else:
                args.append(value)
        if sets:
            self.trail.execute(f"UPDATE litters SET {', '.join(sets)} WHERE litterId = ?", (*args, litterId))  # noqa: S608

    def acknowledge(self, litterId: str, via: str, now: datetime) -> bool:
        """Stop the repeats of an open litter. False when there is no such open litter. Acknowledging
        twice is harmless (the first time stands)."""
        found = self.get(litterId)
        if found is None or not found.isOpen:
            return False
        if found.ackedAt is None:
            self.update(litterId, ackedAt=now, ackedVia=via)
        return True

    def spend(self, tokenId: str, litterId: str, now: datetime) -> bool:
        """Record a push token as used; False when it already was. The primary key makes this atomic."""
        return (
            self.trail.execute(
                "INSERT OR IGNORE INTO ackSpent (tokenId, litterId, spentAt) VALUES (?,?,?)",
                (tokenId, litterId, isoUtc(now)),
            )
            > 0
        )

    # -- pushes, for the rate limit ----------------------------------------------------------

    def recordPush(self, channel: str, litterId: str | None, kind: str, now: datetime) -> None:
        self.trail.execute(
            "INSERT INTO pushes (at, channel, litterId, kind) VALUES (?,?,?,?)", (isoUtc(now), channel, litterId, kind)
        )

    def pushCount(self, channel: str, now: datetime, window: timedelta) -> int:
        row = self.trail.fetch(
            "SELECT COUNT(*) AS n FROM pushes WHERE channel = ? AND at > ?", (channel, isoUtc(now - window))
        )[0]
        return row["n"]

    def summaryIn(self, channel: str, now: datetime, window: timedelta) -> bool:
        row = self.trail.fetch(
            "SELECT COUNT(*) AS n FROM pushes WHERE channel = ? AND kind = 'summary' AND at > ?",
            (channel, isoUtc(now - window)),
        )[0]
        return row["n"] > 0

    # -- facts about meow itself -------------------------------------------------------------

    def meta(self, key: str) -> str | None:
        return self.trail.meta(key)

    def setMeta(self, key: str, value: str) -> None:
        self.trail.execute("INSERT OR REPLACE INTO meta (key, value) VALUES (?,?)", (key, value))
