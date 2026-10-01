from datetime import UTC, datetime, timedelta
from pathlib import Path

import pytest

from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import MIGRATIONS, ScentTrail, isoUtc, newScentId, parseUtc
from perch.scrub import MASK


@pytest.fixture
def trail(tmp_path, clock):
    t = ScentTrail(tmp_path / "scentTrail.db", clock=clock, secrets=["fake-secret-value-123"])
    yield t
    t.close()


def test_wal_and_migrations(trail, tmp_path, clock):
    assert trail.journalMode == "wal"
    assert trail.schemaVersion == len(MIGRATIONS)
    trail.addEvent("perch", "perch", B.slowBlink, "started")
    trail.close()
    again = ScentTrail(tmp_path / "scentTrail.db", clock=clock)  # reopening is idempotent
    assert again.schemaVersion == len(MIGRATIONS)
    assert again.counts()["events"] == 1
    again.close()


def test_scent_ids_sort_by_time():
    a = newScentId(datetime(2026, 9, 29, 1, 0, tzinfo=UTC))
    b = newScentId(datetime(2026, 9, 29, 1, 0, 1, tzinfo=UTC))
    assert len(a) == 26 and a < b


def test_times_are_utc():
    moment = datetime(2026, 9, 29, 7, 42, 18, 123000, tzinfo=UTC)
    assert isoUtc(moment) == "2026-09-29T07:42:18.123Z"
    assert parseUtc(isoUtc(moment)) == moment
    with pytest.raises(ValueError):
        isoUtc(datetime(2026, 9, 29))


def test_events_newest_first_and_filters(trail, clock):
    trail.addEvent("purr", "app:grinder/n8n", B.tailFlick, "n8n restarted", litterId="L7")
    clock.advance(minutes=1)
    trail.addEvent("pounce", "node:percolator", "earTwitch", "2 PDFs dropped")
    clock.advance(minutes=1)
    trail.addEvent("groom", "job:groom/cellar/store", B.slowBlink, "store OK")
    titles = [e.title for e in trail.events()]
    assert titles == ["store OK", "2 PDFs dropped", "n8n restarted"]
    assert [e.title for e in trail.events(senses=["purr"])] == ["n8n restarted"]
    assert [e.title for e in trail.events(levels=["earTwitch", "hiss"])] == ["2 PDFs dropped"]
    assert [e.title for e in trail.events(subjectPrefix="app:grinder/")] == ["n8n restarted"]
    assert trail.events(subjectPrefix="app:grinder/")[0].litterId == "L7"
    assert trail.events(since=clock() - timedelta(seconds=30))[0].title == "store OK"
    assert trail.events(senses=[]) == []


def test_unknown_sense_rejected(trail):
    with pytest.raises(ValueError):
        trail.addEvent("sniff", "x", B.hiss, "nope")


def test_log_tail_title_and_detail_are_scrubbed(trail):
    e = trail.addEvent(
        "groom",
        "job:groom/grinder/nightly",
        B.hiss,
        "failed with fake-secret-value-123",
        detail={"env": "RESTIC_PASSWORD=hunter2hunter2"},
        logTail="line1\nAuthorization: Bearer abcdefghijklmnop\nfake-secret-value-123\n",
    )
    stored = trail.events()[0]
    for text in (stored.title, str(stored.detail), stored.logTail, e.logTail):
        assert "fake-secret-value-123" not in text
        assert "hunter2hunter2" not in text
        assert "abcdefghijklmnop" not in text
    assert MASK in stored.logTail


def test_state_keeps_since_until_level_changes(trail, clock):
    first = trail.setState("app:grinder/n8n", B.slowBlink, expectedRhythm=30)
    clock.advance(seconds=30)
    same = trail.setState("app:grinder/n8n", B.slowBlink, expectedRhythm=30)
    assert same.since == first.since and same.lastSeenAt == clock()
    clock.advance(seconds=30)
    changed = trail.setState("app:grinder/n8n", B.hiss, title="exited")
    assert changed.since == clock()
    state = trail.states()["app:grinder/n8n"]
    assert state.bodyLanguage is B.hiss and state.title == "exited"
    assert state.nextExpectedAt is None


def test_state_detail_is_stored_scrubbed_and_replaced(trail, clock):
    trail.setState("container:grinder/n8n", B.slowBlink, detail={"image": "n8n:1", "uptimeSeconds": 90})
    assert trail.states()["container:grinder/n8n"].detail == {"image": "n8n:1", "uptimeSeconds": 90}
    trail.setState("container:grinder/n8n", B.slowBlink)  # no detail: the old one doesn't linger
    assert trail.states()["container:grinder/n8n"].detail is None
    trail.setState("node:grinder", B.slowBlink, detail={"env": "RESTIC_PASSWORD=hunter2hunter2 fake-secret-value-123"})
    stored = str(trail.states()["node:grinder"].detail)
    assert "hunter2hunter2" not in stored and "fake-secret-value-123" not in stored


def test_migration_2_adds_state_detail_to_a_version_1_database(tmp_path, clock):
    import sqlite3

    path = tmp_path / "old.db"
    db = sqlite3.connect(path)
    db.executescript(MIGRATIONS[0])
    db.execute("INSERT INTO state VALUES ('app:sieve/pihole','slowBlink','2026-09-29T00:00:00.000Z',"
               "'2026-09-29T00:00:00.000Z','ok',NULL,NULL)")
    db.execute("PRAGMA user_version=1")
    db.commit()
    db.close()
    trail = ScentTrail(path, clock=clock)
    try:
        assert trail.schemaVersion == len(MIGRATIONS) >= 2
        old = trail.states()["app:sieve/pihole"]
        assert old.bodyLanguage is B.slowBlink and old.detail is None  # nothing lost
        trail.setState("app:sieve/pihole", B.slowBlink, detail={"n": 1})
        assert trail.states()["app:sieve/pihole"].detail == {"n": 1}
    finally:
        trail.close()


def test_forget_drops_states_and_nothing_else(trail):
    trail.setState("container:grinder/a", B.slowBlink)
    trail.setState("container:grinder/b", B.hiss)
    trail.addEvent("purr", "container:grinder/b", B.hiss, "b exited")
    assert trail.forget(["container:grinder/b", "container:grinder/nope"]) == 1
    assert set(trail.states()) == {"container:grinder/a"}
    assert trail.counts()["events"] == 1  # history stays
    assert trail.forget([]) == 0


def test_daily_rollup_is_worst_of_the_day(trail, clock):
    trail.addEvent("purr", "app:grinder/n8n", B.slowBlink, "ok")
    trail.addEvent("purr", "app:grinder/n8n", B.hiss, "down")
    trail.addEvent("purr", "app:grinder/n8n", B.earTwitch, "notice")
    clock.advance(days=1)
    trail.addEvent("purr", "app:grinder/n8n", B.slowBlink, "ok")
    days = trail.rollups("app:grinder/n8n", days=7)
    assert list(days.values()) == [B.hiss, B.slowBlink]


def test_retention_90_days_of_events_400_of_rollups(trail, clock):
    start = clock()
    trail.addEvent("purr", "app:sieve/pihole", B.slowBlink, "old")
    clock.advance(days=91)
    trail.addEvent("purr", "app:sieve/pihole", B.slowBlink, "recent")
    assert trail.retention() == {"events": 1, "rollups": 0}
    assert [e.title for e in trail.events()] == ["recent"]
    assert trail.counts()["rollups"] == 2  # daily rollups outlive events
    clock.now = start + timedelta(days=401)
    assert trail.retention() == {"events": 1, "rollups": 1}
    assert trail.counts()["rollups"] == 1


def test_corrupt_file_is_moved_aside_and_says_so(tmp_path: Path, clock):
    db = tmp_path / "scentTrail.db"
    db.write_bytes(b"this is not a sqlite database, just crumbs" * 100)
    trail = ScentTrail(db, clock=clock)
    try:
        assert trail.recoveredFrom is not None and trail.recoveredFrom.exists()
        (event,) = trail.events()
        assert event.bodyLanguage is B.hiss and event.sense == "perch"
        assert trail.schemaVersion == len(MIGRATIONS)
    finally:
        trail.close()
