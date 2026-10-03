"""Vitals history (M4, design plan 3.5, 05 plan A13): 5-minute averages for 7 days, hourly for 400,
written from purr's own samples, nothing raw kept."""

import os
from datetime import UTC, datetime, timedelta

import pytest

from perch.scentTrail import ScentTrail, isoUtc
from perch.vitals import Vitals, bucketStart

END = datetime(2026, 10, 3, 6, 0, tzinfo=UTC)  # on an hour: the gate's last sample starts a new hour


@pytest.fixture
def trail(tmp_path):
    t = ScentTrail(tmp_path / "v.db")
    yield t
    t.close()


def feed(vitals, node, start, end, *, step=30, value=lambda minutes: (minutes % 100, 50.0, 60.0)):
    """Samples every ``step`` seconds in [start, end]; the value is a function of minutes since start."""
    moment = start
    while moment <= end:
        cpu, mem, disk = value((moment - start).total_seconds() / 60)
        vitals.add(node, moment, cpu, mem, disk)
        moment += timedelta(seconds=step)


def test_a_bucket_is_the_average_of_its_samples_and_is_written_when_the_next_one_starts(trail):
    v = Vitals(trail, lambda: END)
    t0 = END - timedelta(hours=1)
    for i, cpu in enumerate((10, 20, 60)):
        v.add("grinder", t0 + timedelta(seconds=30 * i), cpu, 40.0, 70.0)
    assert v.rows("grinder", table="5m", since=t0 - timedelta(days=1), until=END) == []  # still open
    v.add("grinder", t0 + timedelta(minutes=5), 0.0, 40.0, 70.0)
    (row,) = v.rows("grinder", table="5m", since=t0 - timedelta(days=1), until=END)
    assert row.at == t0
    assert (row.cpu, row.cpuMax, row.mem, row.disk, row.n) == (30.0, 60.0, 40.0, 70.0, 3)


def test_nothing_is_written_per_sample(trail):
    v = Vitals(trail, lambda: END)
    feed(v, "cellar", END - timedelta(minutes=4), END - timedelta(seconds=1))  # 8 samples, one bucket
    assert v.counts() == {"vitals5m": 0, "vitalsHour": 0}


def test_a_gap_stays_a_gap(trail):
    v = Vitals(trail, lambda: END)
    t0 = END - timedelta(hours=2)
    v.add("sieve", t0, 1, 1, 1)
    v.add("sieve", t0 + timedelta(minutes=5), 1, 1, 1)
    v.add("sieve", t0 + timedelta(minutes=30), 1, 1, 1)  # perch was away for 25 minutes
    v.add("sieve", t0 + timedelta(minutes=35), 1, 1, 1)
    starts = [r.at for r in v.rows("sieve", table="5m", since=t0, until=END)]
    assert starts == [t0, t0 + timedelta(minutes=5), t0 + timedelta(minutes=30)]


def test_GATE_8_days_of_30_second_samples_leave_exactly_7_days_of_5_minute_rows_plus_hourly_rows(trail):
    v = Vitals(trail, lambda: END)
    start = END - timedelta(days=8)
    feed(v, "grinder", start, END)
    five = v.rows("grinder", table="5m", since=start, until=END)
    hours = v.rows("grinder", table="hour", since=start, until=END)
    assert len(five) == 7 * 24 * 12 == 2016
    assert five[0].at == END - timedelta(days=7)
    assert five[-1].at == END - timedelta(minutes=5)
    assert all(b.at - a.at == timedelta(minutes=5) for a, b in zip(five, five[1:], strict=False))
    assert len(hours) == 8 * 24 == 192  # every completed hour of the 8 days
    assert hours[0].at == start and hours[-1].at == END - timedelta(hours=1)
    assert v.counts() == {"vitals5m": 2016, "vitalsHour": 192}


def test_an_hour_is_the_weighted_mean_of_its_5_minute_rows_and_keeps_the_highest_reading(trail):
    v = Vitals(trail, lambda: END)
    start = END - timedelta(hours=3)
    feed(v, "cellar", start, END, value=lambda minutes: (minutes, 50.0, 60.0))  # cpu climbs 1 point a minute
    hour = v.rows("cellar", table="hour", since=start + timedelta(hours=1), until=start + timedelta(hours=1))[0]
    # samples of minutes 60 .. 119.5 every half minute: mean 89.75, highest 119.5
    assert hour.cpu == pytest.approx(89.75)
    assert hour.cpuMax == pytest.approx(119.5)
    assert hour.n == 120
    assert (hour.mem, hour.disk) == (50.0, 60.0)


def test_maintenance_twice_changes_nothing(trail):
    v = Vitals(trail, lambda: END)
    feed(v, "grinder", END - timedelta(days=2), END)
    before = v.counts()
    v.maintain(END)
    v.maintain(END)
    assert v.counts() == before


def test_hourly_rows_older_than_400_days_age_out(trail):
    v = Vitals(trail, lambda: END)
    old = END - timedelta(days=401)
    trail.execute(
        "INSERT INTO vitalsHour VALUES ('sieve', ?, 1, 1, 1, 1, 1, 1, 120)",
        (isoUtc(bucketStart(old, 3600)),),
    )
    keep = END - timedelta(days=399)
    trail.execute(
        "INSERT INTO vitalsHour VALUES ('sieve', ?, 1, 1, 1, 1, 1, 1, 120)",
        (isoUtc(bucketStart(keep, 3600)),),
    )
    v.maintain(END)
    assert [r.at for r in v.rows("sieve", table="hour", since=END - timedelta(days=500), until=END)] == [
        bucketStart(keep, 3600)
    ]


def test_GATE_the_database_stays_under_20_MB_at_400_days_of_6_nodes(tmp_path):
    path = tmp_path / "big.db"
    trail = ScentTrail(path)
    v = Vitals(trail, lambda: END)
    nodes = ("sieve", "percolator", "cellar", "mochaPot", "grinder", "roastery")
    # Steady state needs a 5-minute row for each of the last 7 days and an hourly row for each of 400
    # days: one sample an hour before that gives an hourly row per hour, 5-minute samples after it.
    begin = END - timedelta(days=400)
    lastWeek = END - timedelta(days=7)
    for node in nodes:
        moment = begin
        while moment < lastWeek:
            v.add(node, moment, 12.5, 43.2, 61.8)
            moment += timedelta(hours=1)
        while moment <= END:
            v.add(node, moment, 12.5, 43.2, 61.8)
            moment += timedelta(minutes=5)
    counts = v.counts()
    assert counts["vitals5m"] == 6 * 2016
    assert counts["vitalsHour"] >= 6 * (400 * 24 - 2)  # an hour is stored once its day has passed
    trail.execute("PRAGMA wal_checkpoint(TRUNCATE)")
    size = sum(os.path.getsize(p) for p in (path, f"{path}-wal") if os.path.exists(p))
    trail.close()
    assert size < 20 * 1024 * 1024, f"{size / 1e6:.1f} MB"
    print(f"vitals at 400 days of 6 nodes: {size / 1e6:.2f} MB")  # noqa: T201 - shown with pytest -s
