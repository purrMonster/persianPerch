"""scentTrail: the event store, current state, daily rollups and retention.

One SQLite file in WAL mode (design plan 3, dev plan 1). Stdlib ``sqlite3`` behind a
lock: perch's writes are a few per second at most, so an async driver buys nothing
(runbook 2026-09-30, M0 entry).

Schema changes are numbered migrations tracked in ``PRAGMA user_version``; never edit
a shipped migration, add a new one.
"""

from __future__ import annotations

import contextlib
import json
import os
import secrets as _random
import sqlite3
import threading
import time
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

from .bodyLanguage import BodyLanguage, worstOf
from .scrub import scrub

SENSES = ("purr", "pounce", "whiskers", "glare", "binocs", "groom", "perch")

MIGRATIONS: tuple[str, ...] = (
    # 1: events, current state, daily rollups
    """
    CREATE TABLE events (
        scentId      TEXT PRIMARY KEY,
        seenAt       TEXT NOT NULL,
        sense        TEXT NOT NULL,
        subject      TEXT NOT NULL,
        bodyLanguage TEXT NOT NULL,
        title        TEXT NOT NULL,
        detail       TEXT,
        logTail      TEXT,
        litterId     TEXT
    );
    CREATE INDEX events_seenAt ON events (seenAt);
    CREATE INDEX events_subject ON events (subject, seenAt);
    CREATE INDEX events_litter ON events (litterId);

    CREATE TABLE state (
        subject        TEXT PRIMARY KEY,
        bodyLanguage   TEXT NOT NULL,
        since          TEXT NOT NULL,
        lastSeenAt     TEXT NOT NULL,
        title          TEXT,
        expectedRhythm INTEGER,
        nextExpectedAt TEXT
    );

    CREATE TABLE rollups (
        day      TEXT NOT NULL,
        subject  TEXT NOT NULL,
        worst    TEXT NOT NULL,
        events   INTEGER NOT NULL,
        PRIMARY KEY (day, subject)
    );
    """,
)

_CROCKFORD = "0123456789ABCDEFGHJKMNPQRSTVWXYZ"


def newScentId(now: "datetime | None" = None) -> str:
    """A ULID: 48-bit millisecond time + 80 random bits, Crockford base32 (26 chars)."""
    ms = int((now or datetime.now(UTC)).timestamp() * 1000)
    value = (ms << 80) | _random.randbits(80)
    chars = []
    for _ in range(26):
        chars.append(_CROCKFORD[value & 31])
        value >>= 5
    return "".join(reversed(chars))


def isoUtc(moment: datetime) -> str:
    if moment.tzinfo is None:
        raise ValueError("naive datetime; scentTrail stores UTC only")
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


def parseUtc(text: str) -> datetime:
    return datetime.strptime(text, "%Y-%m-%dT%H:%M:%S.%fZ").replace(tzinfo=UTC)


def utcNow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class Scent:
    scentId: str
    seenAt: datetime
    sense: str
    subject: str
    bodyLanguage: BodyLanguage
    title: str
    detail: dict[str, Any] | None
    logTail: str | None
    litterId: str | None


@dataclass(frozen=True)
class State:
    subject: str
    bodyLanguage: BodyLanguage
    since: datetime
    lastSeenAt: datetime
    title: str | None
    expectedRhythm: int | None
    nextExpectedAt: datetime | None


class ScentTrail:
    def __init__(
        self,
        path: "str | Path",
        *,
        secrets: Iterable[str] = (),
        clock: Callable[[], datetime] = utcNow,
        trailDays: int = 90,
        rollupDays: int = 400,
    ) -> None:
        self.path = Path(path)
        self.clock = clock
        self.trailDays = trailDays
        self.rollupDays = rollupDays
        self._secrets = [s for s in secrets if s]
        self._lock = threading.RLock()
        self.recoveredFrom: Path | None = None
        self._db = self._open()

    # -- opening, migrations -------------------------------------------------

    def _connect(self) -> sqlite3.Connection:
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        db = sqlite3.connect(str(self.path), check_same_thread=False, isolation_level=None)
        db.row_factory = sqlite3.Row
        db.execute("PRAGMA journal_mode=WAL")
        db.execute("PRAGMA synchronous=NORMAL")
        db.execute("PRAGMA foreign_keys=ON")
        db.execute("PRAGMA busy_timeout=5000")
        return db

    def _open(self) -> sqlite3.Connection:
        try:
            db = self._connect()
            ok = db.execute("PRAGMA quick_check").fetchone()[0]
            if ok != "ok":
                raise sqlite3.DatabaseError(f"quick_check: {ok}")
        except sqlite3.DatabaseError:
            # Design plan 8: start with an empty trail and say so. The damaged file is
            # moved aside, never deleted, so it can still be inspected or restored.
            with contextlib.suppress(Exception):
                db.close()  # type: ignore[possibly-undefined]
            stamp = time.strftime("%Y%m%dT%H%M%S")
            aside = self.path.with_name(f"{self.path.name}.corrupt-{stamp}")
            for suffix in ("", "-wal", "-shm"):
                src = Path(str(self.path) + suffix)
                if src.exists():
                    os.replace(src, Path(str(aside) + suffix))
            self.recoveredFrom = aside
            db = self._connect()
        self._migrate(db)
        if self.recoveredFrom is not None:
            self._db = db
            self.addEvent(
                "perch",
                "perch",
                BodyLanguage.hiss,
                "scentTrail was damaged; started empty",
                detail={"movedAside": self.recoveredFrom.name},
            )
        return db

    @staticmethod
    def _migrate(db: sqlite3.Connection) -> None:
        version = db.execute("PRAGMA user_version").fetchone()[0]
        for number, script in enumerate(MIGRATIONS, start=1):
            if number <= version:
                continue
            db.execute("BEGIN")
            try:
                for statement in script.split(";"):
                    if statement.strip():
                        db.execute(statement)
                db.execute(f"PRAGMA user_version={number}")
                db.execute("COMMIT")
            except Exception:
                db.execute("ROLLBACK")
                raise

    @property
    def schemaVersion(self) -> int:
        with self._lock:
            return self._db.execute("PRAGMA user_version").fetchone()[0]

    @property
    def journalMode(self) -> str:
        with self._lock:
            return self._db.execute("PRAGMA journal_mode").fetchone()[0]

    def close(self) -> None:
        with self._lock:
            self._db.close()

    # -- events ---------------------------------------------------------------

    def addEvent(
        self,
        sense: str,
        subject: str,
        bodyLanguage: "str | BodyLanguage",
        title: str,
        *,
        detail: "dict[str, Any] | None" = None,
        logTail: "str | None" = None,
        litterId: "str | None" = None,
        seenAt: "datetime | None" = None,
    ) -> Scent:
        if sense not in SENSES:
            raise ValueError(f"unknown sense {sense!r}")
        level = BodyLanguage.parse(bodyLanguage)
        seenAt = seenAt or self.clock()
        scent = Scent(
            scentId=newScentId(seenAt),
            seenAt=seenAt,
            sense=sense,
            subject=subject,
            bodyLanguage=level,
            title=scrub(title, self._secrets, limit=1024),
            detail=json.loads(scrub(json.dumps(detail), self._secrets)) if detail else None,
            logTail=scrub(logTail, self._secrets) if logTail else None,
            litterId=litterId,
        )
        day = seenAt.astimezone(UTC).strftime("%Y-%m-%d")
        with self._lock:
            self._db.execute("BEGIN")
            try:
                self._db.execute(
                    "INSERT INTO events VALUES (?,?,?,?,?,?,?,?,?)",
                    (
                        scent.scentId,
                        isoUtc(seenAt),
                        sense,
                        subject,
                        level.value,
                        scent.title,
                        json.dumps(scent.detail) if scent.detail else None,
                        scent.logTail,
                        litterId,
                    ),
                )
                row = self._db.execute("SELECT worst FROM rollups WHERE day=? AND subject=?", (day, subject)).fetchone()
                worst = worstOf([row["worst"], level]) if row else level
                self._db.execute(
                    "INSERT INTO rollups (day, subject, worst, events) VALUES (?,?,?,1) "
                    "ON CONFLICT(day, subject) DO UPDATE SET worst=excluded.worst, events=events+1",
                    (day, subject, worst.value),
                )
                self._db.execute("COMMIT")
            except Exception:
                self._db.execute("ROLLBACK")
                raise
        return scent

    def events(
        self,
        *,
        since: "datetime | None" = None,
        senses: "Iterable[str] | None" = None,
        levels: "Iterable[str | BodyLanguage] | None" = None,
        subjectPrefix: "str | None" = None,
        limit: int = 200,
    ) -> list[Scent]:
        where, args = [], []
        if since is not None:
            where.append("seenAt >= ?")
            args.append(isoUtc(since))
        if senses is not None:
            senses = list(senses)
            where.append(f"sense IN ({','.join('?' * len(senses))})" if senses else "0")
            args.extend(senses)
        if levels is not None:
            names = [BodyLanguage.parse(v).value for v in levels]
            where.append(f"bodyLanguage IN ({','.join('?' * len(names))})" if names else "0")
            args.extend(names)
        if subjectPrefix:
            where.append("subject LIKE ? ESCAPE '\\'")
            args.append(subjectPrefix.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%")
        sql = "SELECT * FROM events"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY seenAt DESC, scentId DESC LIMIT ?"
        args.append(int(limit))
        with self._lock:
            rows = self._db.execute(sql, args).fetchall()
        return [self._scent(r) for r in rows]

    @staticmethod
    def _scent(row: sqlite3.Row) -> Scent:
        return Scent(
            scentId=row["scentId"],
            seenAt=parseUtc(row["seenAt"]),
            sense=row["sense"],
            subject=row["subject"],
            bodyLanguage=BodyLanguage(row["bodyLanguage"]),
            title=row["title"],
            detail=json.loads(row["detail"]) if row["detail"] else None,
            logTail=row["logTail"],
            litterId=row["litterId"],
        )

    # -- current state -------------------------------------------------------

    def setState(
        self,
        subject: str,
        bodyLanguage: "str | BodyLanguage",
        *,
        title: "str | None" = None,
        seenAt: "datetime | None" = None,
        expectedRhythm: "int | None" = None,
    ) -> State:
        level = BodyLanguage.parse(bodyLanguage)
        seenAt = seenAt or self.clock()
        nextExpected = seenAt + timedelta(seconds=expectedRhythm) if expectedRhythm else None
        with self._lock:
            row = self._db.execute("SELECT * FROM state WHERE subject=?", (subject,)).fetchone()
            since = seenAt if row is None or row["bodyLanguage"] != level.value else parseUtc(row["since"])
            self._db.execute(
                "INSERT INTO state VALUES (?,?,?,?,?,?,?) ON CONFLICT(subject) DO UPDATE SET "
                "bodyLanguage=excluded.bodyLanguage, since=excluded.since, lastSeenAt=excluded.lastSeenAt, "
                "title=excluded.title, expectedRhythm=excluded.expectedRhythm, nextExpectedAt=excluded.nextExpectedAt",
                (
                    subject,
                    level.value,
                    isoUtc(since),
                    isoUtc(seenAt),
                    scrub(title, self._secrets, limit=1024) if title else None,
                    expectedRhythm,
                    isoUtc(nextExpected) if nextExpected else None,
                ),
            )
        return State(subject, level, since, seenAt, title, expectedRhythm, nextExpected)

    def states(self) -> dict[str, State]:
        with self._lock:
            rows = self._db.execute("SELECT * FROM state").fetchall()
        return {
            r["subject"]: State(
                subject=r["subject"],
                bodyLanguage=BodyLanguage(r["bodyLanguage"]),
                since=parseUtc(r["since"]),
                lastSeenAt=parseUtc(r["lastSeenAt"]),
                title=r["title"],
                expectedRhythm=r["expectedRhythm"],
                nextExpectedAt=parseUtc(r["nextExpectedAt"]) if r["nextExpectedAt"] else None,
            )
            for r in rows
        }

    # -- rollups, retention ---------------------------------------------------

    def rollups(self, subject: str, days: int = 7) -> dict[str, BodyLanguage]:
        first = (self.clock() - timedelta(days=days - 1)).astimezone(UTC).strftime("%Y-%m-%d")
        with self._lock:
            rows = self._db.execute(
                "SELECT day, worst FROM rollups WHERE subject=? AND day>=? ORDER BY day", (subject, first)
            ).fetchall()
        return {r["day"]: BodyLanguage(r["worst"]) for r in rows}

    def retention(self, now: "datetime | None" = None) -> dict[str, int]:
        """Drop events older than trailDays and rollups older than rollupDays."""
        now = now or self.clock()
        eventCut = isoUtc(now - timedelta(days=self.trailDays))
        rollupCut = (now - timedelta(days=self.rollupDays)).astimezone(UTC).strftime("%Y-%m-%d")
        with self._lock:
            events = self._db.execute("DELETE FROM events WHERE seenAt < ?", (eventCut,)).rowcount
            rollups = self._db.execute("DELETE FROM rollups WHERE day < ?", (rollupCut,)).rowcount
        return {"events": events, "rollups": rollups}

    def counts(self) -> dict[str, int]:
        with self._lock:
            return {
                table: self._db.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]  # noqa: S608 - fixed names
                for table in ("events", "state", "rollups")
            }
