"""groom: the jobs the repo declares, the records that arrive, and what silence means (M2 gate)."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeClock

from perch.bodyLanguage import BodyLanguage as B
from perch.rollup import Status
from perch.scentTrail import GroomRun, ScentTrail
from perch.senses.groom import (
    Groom,
    RecordError,
    expectedJobs,
    parseRecord,
    slotOfRun,
)

IST = ZoneInfo("Asia/Kolkata")
BACKUP_NODES = ["sieve", "percolator", "cellar", "mochaPot", "grinder"]  # nodes with a <app>/backup file


def at(hour: int, minute: int = 0, day: int = 29, month: int = 9) -> datetime:
    return datetime(2026, month, day, hour, minute, tzinfo=IST).astimezone(UTC)


def run(node, job, start, minutes=20, result="success", exitStatus="0", tail="") -> GroomRun:  # noqa: PLR0917
    return GroomRun(node, job, start, start + timedelta(minutes=minutes), result, exitStatus, f"{job}.service", tail)


@pytest.fixture
def jobs(fleetTree):
    return {j.key: j for j in expectedJobs(fleetTree, fleetTree.fleet())}


@pytest.fixture
def world(fleetTree, tmp_path):
    clock = FakeClock(at(18, 0, day=28))  # perch started watching the evening before the night under test
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    groom = Groom(trail, fleetTree, clock=clock, tz=IST, watched=BACKUP_NODES)
    groom.step()
    yield groom
    trail.close()


def night(groom, *, skip=()):
    """A good night: every node's nightly, then cellar's wake, store and Drive, as the timers fire them."""
    for node in BACKUP_NODES:
        if node not in skip:
            groom.ingest(node, None, [run(node, "nightly", at(1, 30, 29) + timedelta(seconds=40), minutes=22)])
    groom.ingest(
        "cellar",
        None,
        [
            run("cellar", "wake", at(1, 25), minutes=1),
            run("cellar", "store", at(2, 30), minutes=6),
            run("cellar", "drive", at(3, 30), minutes=25),
        ],
    )


def levels(groom) -> dict[str, B]:
    return {s.subject: s.bodyLanguage for s in groom.trail.states().values() if s.subject.startswith("groom:")}


# -- the repo says what should happen (05 plan C4) -------------------------------------------


def test_jobs_come_from_the_repos_timers_not_from_the_code(jobs):
    nightly = jobs["grinder/nightly"]
    assert nightly.calendar.time == time(1, 30) and nightly.source == "stacks/_lib/systemd/purrbrews-backup@.timer"
    assert (nightly.late, nightly.missing) == (timedelta(minutes=45), timedelta(hours=3))  # design plan 3.4
    assert jobs["cellar/store"].calendar.time == time(2, 30)
    assert jobs["cellar/drive"].calendar.time == time(3, 30)
    assert (jobs["cellar/drive"].late, jobs["cellar/drive"].missing) == (timedelta(hours=2), timedelta(hours=8))
    assert jobs["cellar/wake"].calendar.time == time(1, 25) and jobs["cellar/check"].calendar.time == time(6, 0)
    assert (
        jobs["cellar/prune"].calendar.weekday == 6 and jobs["cellar/verify"].calendar.day == 1
    )  # Sun 03:00, 1st 04:30
    assert jobs["cellar/prune"].calendar.time == time(3, 0) and jobs["cellar/verify"].calendar.time == time(4, 30)


def test_backup_nodes_are_the_nodes_with_backup_files_and_roastery_has_none(jobs):
    nightly = sorted(k.split("/")[0] for k in jobs if k.endswith("/nightly"))
    assert nightly == sorted(BACKUP_NODES)
    assert not [k for k in jobs if k.startswith("roastery/")]  # no groom jobs there (A5)
    assert jobs["grinder/nightly"].dumps  # grinder's postgres and n8n lines: dumps are taken there too
    assert {k for k in jobs if "/" in k and not k.endswith("/nightly")} == {
        f"cellar/{j}" for j in ("wake", "store", "drive", "check", "prune", "verify")
    }


def test_a_changed_timer_in_the_repo_moves_the_expectation(tmp_path, fleetRepo):
    from conftest import makeRepo

    from perch.catTree import CatTree

    repo = makeRepo(
        tmp_path / "r",
        {
            "stacks/fleet.env": "SIEVE_LAN_IP=192.0.2.10\n",
            "stacks/sieve/node.conf": "# sieve: net.\nAPPS=(ntfy)\n",
            "stacks/sieve/ntfy/backup": "path /var/lib/ntfy\n",
            "stacks/_lib/systemd/purrbrews-backup@.timer": "[Timer]\nOnCalendar=*-*-* 02:10:00\n",
        },
    )
    tree = CatTree(repo)
    (job,) = expectedJobs(tree, tree.fleet())
    assert job.key == "sieve/nightly" and job.calendar.time == time(2, 10) and not job.dumps


def test_an_unreadable_timer_means_no_expectation_never_a_guess(tmp_path):
    from conftest import makeRepo

    from perch.catTree import CatTree

    repo = makeRepo(
        tmp_path / "r",
        {
            "stacks/sieve/node.conf": "# sieve: net.\nAPPS=(ntfy)\n",
            "stacks/sieve/ntfy/backup": "path /var/lib/ntfy\n",
            "stacks/_lib/systemd/purrbrews-backup@.timer": "[Timer]\nOnCalendar=weekly\n",
        },
    )
    tree = CatTree(repo)
    assert expectedJobs(tree, tree.fleet()) == []


# -- the gate: a fixture night with one node's record missing ------------------------------------


def test_GATE_a_missing_record_hisses_only_its_own_cell_at_0430(world):
    world.clock.now = at(4, 30)
    night(world, skip=("grinder",))
    world.evaluate(world.clock())
    found = levels(world)
    assert found["groom:grinder/nightly"] is B.hiss
    assert {k: v for k, v in found.items() if k != "groom:grinder/nightly"} == {
        "groom:sieve/nightly": B.slowBlink,
        "groom:percolator/nightly": B.slowBlink,
        "groom:cellar/nightly": B.slowBlink,
        "groom:mochaPot/nightly": B.slowBlink,
        "groom:cellar/wake": B.slowBlink,
        "groom:cellar/store": B.slowBlink,
        "groom:cellar/drive": B.slowBlink,
    }
    state = world.trail.states()["groom:grinder/nightly"]
    assert state.title == "nightly backup: missing: no record 3 h after 01:30"
    # ... and it rolls up: the node and the fleet hiss, the other nodes don't
    status = Status(world.tree.fleet(), world.trail)
    assert status.node("grinder") is B.hiss and status.fleetLevel() is B.hiss
    assert status.node("sieve") is not B.hiss


def test_the_cell_is_tailFlick_until_0430_exactly_then_hiss(world):
    night(world, skip=("grinder",))
    world.clock.now = at(1, 30) + timedelta(minutes=44)
    world.evaluate(world.clock())
    assert levels(world)["groom:grinder/nightly"] is B.slowBlink  # due, not late yet
    world.clock.now = at(2, 15)
    world.evaluate(world.clock())
    assert levels(world)["groom:grinder/nightly"] is B.tailFlick  # +45 min
    world.clock.now = at(4, 29) + timedelta(seconds=59)
    world.evaluate(world.clock())
    assert levels(world)["groom:grinder/nightly"] is B.tailFlick
    world.clock.now = at(4, 30)
    world.evaluate(world.clock())
    assert levels(world)["groom:grinder/nightly"] is B.hiss  # +3 h


def test_it_says_so_once_and_says_when_it_is_back(world):
    night(world, skip=("grinder",))
    for minute in (0, 1, 2):
        world.clock.now = at(4, 30) + timedelta(minutes=minute)
        world.evaluate(world.clock())
    said = [e for e in world.trail.events(subjectPrefix="groom:grinder") if e.bodyLanguage is B.hiss]
    assert len(said) == 1 and said[0].sense == "groom" and "missing" in said[0].title
    world.clock.advance(minutes=11)
    world.ingest("grinder", None, [run("grinder", "nightly", at(4, 40), minutes=20)])  # it ran after all, 3 h 10 late
    assert levels(world)["groom:grinder/nightly"] is B.earTwitch
    assert "ran 3 h 10 min late" in world.trail.states()["groom:grinder/nightly"].title
    assert "was hiss" in world.trail.events(subjectPrefix="groom:grinder")[0].title


def test_a_run_that_starts_late_but_succeeds_is_a_notice_not_a_problem(world):
    world.clock.now = at(3, 0)
    world.ingest("grinder", None, [run("grinder", "nightly", at(1, 30) + timedelta(minutes=52), minutes=20)])
    assert levels(world)["groom:grinder/nightly"] is B.earTwitch
    assert "ran 52 min late" in world.trail.states()["groom:grinder/nightly"].title


def test_a_failed_run_hisses_at_once_with_its_log_and_a_retry_that_works_clears_it(world):
    world.clock.now = at(2, 0)
    world.ingest(
        "mochaPot",
        None,
        [run("mochaPot", "nightly", at(1, 30), result="exit-code", exitStatus="1", tail="restic: unreachable")],
    )
    assert levels(world)["groom:mochaPot/nightly"] is B.hiss
    event = [e for e in world.trail.events(subjectPrefix="groom:mochaPot") if e.bodyLanguage is B.hiss][0]
    assert "failed (exit-code, exit 1)" in event.title and event.logTail == "restic: unreachable"
    world.clock.advance(minutes=10)
    world.ingest("mochaPot", None, [run("mochaPot", "nightly", at(1, 40), minutes=20)])
    assert levels(world)["groom:mochaPot/nightly"] is B.slowBlink
    assert "after 1 failed try" in world.trail.states()["groom:mochaPot/nightly"].title
    assert "was hiss" in world.trail.events(subjectPrefix="groom:mochaPot")[0].title


def test_a_manual_run_in_the_afternoon_does_not_stand_in_for_last_nights_backup(jobs):
    job = jobs["grinder/nightly"]
    assert slotOfRun(job, run("grinder", "nightly", at(14, 0)), IST) is None
    assert slotOfRun(job, run("grinder", "nightly", at(1, 29)), IST) == at(1, 30)  # a minute early: clock skew
    assert slotOfRun(job, run("grinder", "nightly", at(9, 0)), IST) == at(1, 30)  # a Persistent=true run at boot


def test_a_new_deploy_does_not_hiss_for_nights_before_it_was_watching(fleetTree, tmp_path):
    clock = FakeClock(at(5, 0))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    groom = Groom(trail, fleetTree, clock=clock, tz=IST, watched=BACKUP_NODES)
    groom.step()  # first ever look, at 05:00: last night is history perch never saw
    assert levels(groom) == {}
    clock.now = at(5, 0, day=30)  # a whole day later, still no records: now it is a hiss
    groom.step()
    assert levels(groom)["groom:grinder/nightly"] is B.hiss
    trail.close()


def test_nodes_without_a_kitten_token_are_not_judged(fleetTree, tmp_path):
    clock = FakeClock(at(18, 0, day=28))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    groom = Groom(trail, fleetTree, clock=clock, tz=IST, watched=["sieve"])
    groom.step()
    clock.now = at(23, 0, day=29)
    groom.step()
    assert set(levels(groom)) == {"groom:sieve/nightly"}
    trail.close()


def test_weekly_and_monthly_jobs_have_no_cell_on_other_days(world):
    world.clock.now = at(7, 0, day=29)  # a Tuesday, not the 1st
    days, rows = world.grid(3, world.clock())
    byKey = {job.key: cells for job, cells in rows}
    assert [d.day for d in days] == [27, 28, 29]
    assert byKey["cellar/verify"] == [None, None, None]
    assert [c is not None for c in byKey["cellar/prune"]] == [True, False, False]  # Sunday the 27th only
    assert byKey["cellar/prune"][0].level is None  # ...and that was before perch was watching
    assert all(cell is not None for cell in byKey["grinder/nightly"])


def test_the_grid_shows_old_nights_from_their_records(world):
    for day in (27, 28):
        world.clock.now = at(8, 0, day=day)
        world.ingest("sieve", None, [run("sieve", "nightly", at(1, 30, day) + timedelta(seconds=30))])
    world.clock.now = at(8, 0, day=29)
    _days, rows = world.grid(3, world.clock())
    cells = {job.key: cells for job, cells in rows}["sieve/nightly"]
    assert [c.level for c in cells] == [B.slowBlink, B.slowBlink, B.hiss]  # 27, 28 recorded; today's is missing


# -- kitten's heartbeat --------------------------------------------------------------------------


def beat(world, node="sieve", **extra):
    world.ingest(node, {"version": "0.1.0", "sentAt": "2026-09-28T12:30:00Z", **extra}, [])


def test_a_node_that_never_spoke_is_unknown_not_ok(world):
    assert world.trail.states()["kitten:sieve"].bodyLanguage is B.unknown


def test_heartbeat_late_after_3_minutes_and_missing_after_10(world):
    beat(world)
    state = lambda: world.trail.states()["kitten:sieve"]  # noqa: E731
    assert state().bodyLanguage is B.slowBlink
    for minutes, expected in ((2, B.slowBlink), (3, B.tailFlick), (9, B.tailFlick), (10, B.hiss)):
        world.clock.now = at(18, 0, day=28) + timedelta(minutes=minutes)
        world.evaluate(world.clock())
        assert state().bodyLanguage is expected, minutes
    assert "silent" in state().title
    world.clock.advance(seconds=1)
    beat(world)
    assert state().bodyLanguage is B.slowBlink
    assert "kitten is back (was hiss)" in world.trail.events(subjectPrefix="kitten:sieve")[0].title


def test_roastery_sleeping_outside_its_window_is_slowBlink_and_inside_it_is_not(fleetTree, tmp_path):
    clock = FakeClock(at(18, 0, day=28))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    groom = Groom(trail, fleetTree, clock=clock, tz=IST, watched=["roastery"])
    groom.step()
    groom.ingest("roastery", {"version": "0.1.0"}, [])
    clock.now = at(23, 0, day=28)  # five hours of silence, asleep
    groom.evaluate(clock())
    asleep = trail.states()["kitten:roastery"]
    assert asleep.bodyLanguage is B.slowBlink and "asleep, as expected (wakes 01:25)" in asleep.title
    clock.now = at(1, 30)  # in the window but inside its 10-minute settle
    groom.evaluate(clock())
    assert trail.states()["kitten:roastery"].bodyLanguage is B.slowBlink
    clock.now = at(1, 40)  # window open, settled, still nothing from it
    groom.evaluate(clock())
    assert trail.states()["kitten:roastery"].bodyLanguage is B.hiss
    trail.close()


def test_the_heartbeat_carries_the_drive_stamp_and_only_ok_files(world):
    beat(world, "cellar", stamps={"drive-sync.ok": 1759000000, "../evil": 5, "notes.txt": 3, "big.ok": "x"})
    assert world.trail.states()["kitten:cellar"].detail["stamps"] == {"drive-sync.ok": 1759000000}


# -- records off the wire --------------------------------------------------------------------


GOOD = {
    "schema": 1,
    "job": "nightly",
    "node": "grinder",
    "unit": "purrbrews-backup@grinder.service",
    "start": "2026-09-29T01:30:12Z",
    "end": "2026-09-29T01:52:36Z",
    "result": "success",
    "exitStatus": "0",
    "logTail": "done",
}


def test_a_good_record_parses_to_utc():
    parsed = parseRecord(GOOD)
    assert parsed.job == "nightly" and parsed.start == datetime(2026, 9, 29, 1, 30, 12, tzinfo=UTC)
    assert parsed.end - parsed.start == timedelta(minutes=22, seconds=24)


@pytest.mark.parametrize(
    "change",
    [
        {"schema": 2},
        {"job": "../etc"},
        {"job": "backup"},
        {"node": "a b"},
        {"result": "Success!"},
        {"start": "yesterday"},
        {"start": "2026-09-29T01:30:12"},  # no time zone
        {"end": "2026-09-29T01:00:00Z"},
        {"unit": "x" * 300},
        {"logTail": 5},
    ],
)
def test_a_malformed_record_is_refused(change):
    with pytest.raises(RecordError):
        parseRecord({**GOOD, **change})


def test_a_record_that_is_not_an_object_is_refused():
    for bad in (None, [], "x", 3):
        with pytest.raises(RecordError):
            parseRecord(bad)


def test_a_huge_log_tail_is_cut_to_16_kb_keeping_the_end():
    parsed = parseRecord({**GOOD, "logTail": "a" * 40000 + "THE END"})
    assert len(parsed.logTail) == 16 * 1024 and parsed.logTail.endswith("THE END")


def test_the_same_record_twice_is_stored_once_and_the_log_is_scrubbed(fleetTree, tmp_path):
    clock = FakeClock(at(18, 0, day=28))
    trail = ScentTrail(tmp_path / "t.db", clock=clock, secrets=["fake-secret-value"])
    groom = Groom(trail, fleetTree, clock=clock, tz=IST, watched=["sieve"])
    record = run("sieve", "nightly", at(1, 30), tail="token=fake-secret-value done")
    assert groom.ingest("sieve", None, [record]) == groom.ingest("sieve", None, [record])
    stored = trail.runs()
    assert len(stored) == 1 and "fake-secret-value" not in stored[0].logTail
    trail.close()


def test_cellars_own_records_are_read_from_the_mounted_directory(fleetTree, tmp_path):
    import json

    clock = FakeClock(at(18, 0, day=28))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    directory = tmp_path / "groom"
    (directory / "store").mkdir(parents=True)
    path = directory / "store" / "20260929T023000Z.json"
    path.write_text(json.dumps({**GOOD, "job": "store", "node": "cellar", "start": "2026-09-28T21:00:00Z"}))
    (directory / "store" / "garbage.json").write_text("{not json")
    groom = Groom(trail, fleetTree, clock=clock, tz=IST, groomDir=directory)
    clock.now = datetime(2026, 9, 28, 23, 0, tzinfo=UTC)
    import os

    os.utime(path, (clock.now.timestamp(), clock.now.timestamp()))
    assert groom.readDir() == 1 and groom.readDir() == 0  # read once; the garbage file is skipped, not fatal
    assert [r.job for r in trail.runs()] == ["store"]
    assert "cellar" in groom.watchedNodes()
    trail.close()
