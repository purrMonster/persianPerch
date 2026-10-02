"""vitals: a node's CPU, RAM and root-disk history (design plan 3.5, 05 plan A13, M4).

purr already reads every node's stats each cycle (30 s). Samples are averaged **in memory**; one row per
node per 5 minutes goes into ``vitals5m`` (kept 7 days), and an hourly job rolls completed hours up into
``vitalsHour`` (kept 400 days, the same as event rollups). No raw 30 s rows are ever stored: at 6 nodes
that is at most 12,096 + 57,600 rows, a few MB, still one SQLite file (design plan 2.3).

A bucket is ``[start, start + 5 min)``; its row is written when the first sample of the next bucket
arrives, so the bucket still open when perch stops is lost (at most 5 minutes). A gap in the rows is a
gap in the history and is drawn as one (``windowsill/spark.py``); nothing is ever filled in.

Retention (``maintain``) runs once an hour on the first sample of the hour, after the previous bucket
was written: first the completed hours are rolled up, then 5-minute rows older than 7 days (bucket start
before ``now - 7 d``) and hourly rows older than 400 days go. Rolling up first means an hour is never
deleted before it is summed.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from .scentTrail import ScentTrail, isoUtc, parseUtc

BUCKET_SECONDS = 300
KEEP_5M = timedelta(days=7)
KEEP_HOUR = timedelta(days=400)
METRICS = ("cpu", "mem", "disk")


def bucketStart(moment: datetime, seconds: int = BUCKET_SECONDS) -> datetime:
    epoch = int(moment.astimezone(UTC).timestamp())
    return datetime.fromtimestamp(epoch - epoch % seconds, UTC)


@dataclass
class _Bucket:
    start: datetime
    n: int = 0
    sums: tuple[float, float, float] = (0.0, 0.0, 0.0)
    highs: tuple[float, float, float] = (0.0, 0.0, 0.0)

    def add(self, cpu: float, mem: float, disk: float) -> None:
        values = (cpu, mem, disk)
        self.highs = tuple(max(h, v) for h, v in zip(self.highs, values, strict=True)) if self.n else values
        self.sums = tuple(s + v for s, v in zip(self.sums, values, strict=True))
        self.n += 1


@dataclass(frozen=True)
class Row:
    """One stored bucket: the averages, the highest readings, and how many samples made it."""

    at: datetime
    cpu: float
    mem: float
    disk: float
    cpuMax: float
    memMax: float
    diskMax: float
    n: int


class Vitals:
    def __init__(self, trail: ScentTrail, clock: Callable[[], datetime]) -> None:
        self.trail = trail
        self.clock = clock
        self._open: dict[str, _Bucket] = {}
        self._maintained: datetime | None = None  # the hour the last maintenance ran in

    # -- writing ------------------------------------------------------------------------

    def add(self, node: str, now: datetime, cpu: float, mem: float, disk: float) -> None:
        """One 30-second sample. Closing a bucket writes its row; the first sample of a new hour
        also rolls the finished hours up and ages out what is old."""
        start = bucketStart(now)
        bucket = self._open.get(node)
        if bucket is not None and bucket.start != start:
            self._write(node, bucket)
            bucket = None
        if bucket is None:
            bucket = self._open[node] = _Bucket(start)
        bucket.add(cpu, mem, disk)
        hour = bucketStart(now, 3600)
        if self._maintained != hour:
            self.maintain(now)
            self._maintained = hour

    def _write(self, node: str, bucket: _Bucket) -> None:
        (cpu, mem, disk), (cpuMax, memMax, diskMax) = (s / bucket.n for s in bucket.sums), bucket.highs
        self.trail.execute(
            "INSERT OR REPLACE INTO vitals5m (node, at, cpu, mem, disk, cpuMax, memMax, diskMax, n) "
            "VALUES (?,?,?,?,?,?,?,?,?)",
            (node, isoUtc(bucket.start), cpu, mem, disk, cpuMax, memMax, diskMax, bucket.n),
        )

    def maintain(self, now: datetime) -> None:
        """Roll every completed hour up, then drop what has aged out. Safe to run any time, twice."""
        hourStart = bucketStart(now, 3600)
        due = self.trail.fetch(
            "SELECT node, at, cpu, mem, disk, cpuMax, memMax, diskMax, n FROM vitals5m AS f WHERE at < ? "
            "AND NOT EXISTS (SELECT 1 FROM vitalsHour h WHERE h.node = f.node "
            "AND h.at = substr(f.at, 1, 13) || ':00:00.000Z') ORDER BY node, at",
            (isoUtc(hourStart),),
        )
        hours: dict[tuple[str, str], list] = {}
        for r in due:
            hours.setdefault((r["node"], r["at"][:13] + ":00:00.000Z"), []).append(r)
        for (node, at), rows in hours.items():
            n = sum(r["n"] for r in rows)
            mean = [sum(r[m] * r["n"] for r in rows) / n for m in METRICS]
            high = [max(r[m + "Max"] for r in rows) for m in METRICS]
            self.trail.execute(
                "INSERT OR IGNORE INTO vitalsHour (node, at, cpu, mem, disk, cpuMax, memMax, diskMax, n) "
                "VALUES (?,?,?,?,?,?,?,?,?)",
                (node, at, *mean, *high, n),
            )
        self.trail.execute("DELETE FROM vitals5m WHERE at < ?", (isoUtc(now - KEEP_5M),))
        self.trail.execute("DELETE FROM vitalsHour WHERE at < ?", (isoUtc(now - KEEP_HOUR),))

    # -- reading ------------------------------------------------------------------------

    def rows(self, node: str, *, table: str, since: datetime, until: datetime | None = None) -> list[Row]:
        """Stored buckets of a node, oldest first, whose start is in ``[since, until]``. ``table`` is
        ``"5m"`` or ``"hour"``; anything else is a programming error."""
        name = {"5m": "vitals5m", "hour": "vitalsHour"}[table]
        until = until or self.clock()
        found = self.trail.fetch(
            f"SELECT * FROM {name} WHERE node = ? AND at >= ? AND at <= ? ORDER BY at",  # noqa: S608 - fixed names
            (node, isoUtc(since), isoUtc(until)),
        )
        return [
            Row(parseUtc(r["at"]), r["cpu"], r["mem"], r["disk"], r["cpuMax"], r["memMax"], r["diskMax"], r["n"])
            for r in found
        ]

    def counts(self) -> dict[str, int]:
        return {t: self.trail.fetch(f"SELECT COUNT(*) AS c FROM {t}")[0]["c"] for t in ("vitals5m", "vitalsHour")}  # noqa: S608
