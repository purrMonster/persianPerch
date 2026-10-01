"""The collector runner: silence is a signal (design plan 3.4). A collector that stops
succeeding is late after 3 missed cycles and missing after 10, whatever the cause (the
source is down, or the collector hung), and perch says so with its own events."""

import asyncio
import time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

from perch.bodyLanguage import BodyLanguage as B
from perch.collectors import Runner, buildCollectors
from perch.rhythms import Rhythm
from perch.scentTrail import ScentTrail
from perch.senses.komodo import KomodoError
from perch.senses.purr import Purr
from perch.settings import Settings
from perch.windowsill.app import createApp


class Fake:
    name = "fake"

    def __init__(self, every=30):
        self.rhythm = Rhythm(every=every)
        self.fail: Exception | None = None
        self.hang = False
        self.cycles = 0
        self.closed = False

    async def cycle(self):
        self.cycles += 1
        if self.hang:
            await asyncio.sleep(3600)
        if self.fail:
            raise self.fail

    async def aclose(self):
        self.closed = True


class Rig:
    def __init__(self, tmp_path, clock, **kw):
        self.clock = clock
        self.trail = ScentTrail(tmp_path / "t.db", clock=clock)
        self.fake = Fake()
        self.runner = Runner(self.trail, [self.fake], clock=clock, **kw)
        self.loop = asyncio.new_event_loop()

    def step(self, seconds=30):
        """One scheduled run of the collector, then time passes."""
        self.loop.run_until_complete(self.runner.runOnce(self.fake))
        self.clock.advance(seconds=seconds)

    def state(self):
        return self.trail.states()["collector:fake"]

    def events(self):
        return list(reversed(self.trail.events()))

    def close(self):
        self.loop.close()
        self.trail.close()


@pytest.fixture
def rig(tmp_path, clock):
    r = Rig(tmp_path, clock)
    yield r
    r.close()


# -- late, missing, back ---------------------------------------------------------------------


def test_before_the_first_cycle_it_is_unknown_not_ok(rig):
    rig.runner.check()
    assert rig.state().bodyLanguage is B.unknown and rig.state().title == "waiting for the first cycle"
    rig.step()
    assert rig.state().bodyLanguage is B.slowBlink and rig.state().expectedRhythm == 30
    assert rig.events() == []


def test_late_after_three_missed_cycles_missing_after_ten_and_back(rig):
    rig.step()  # t+0: fine
    rig.fake.fail = KomodoError("Komodo isn't answering")
    for _ in range(3):  # t+30, t+60, t+90: misses 0, 0, 2
        rig.step()
    assert rig.state().bodyLanguage is B.slowBlink and rig.events() == []
    rig.step()  # t+120: the third missed cycle
    assert rig.state().bodyLanguage is B.tailFlick
    (late,) = rig.events()
    assert (late.sense, late.subject, late.bodyLanguage) == ("perch", "collector:fake", B.tailFlick)
    assert late.title == "fake is late: no successful cycle for 2 min (Komodo isn't answering)"
    for _ in range(6):  # still late, nothing new to say
        rig.step()
    assert len(rig.events()) == 1 and rig.state().bodyLanguage is B.tailFlick
    for _ in range(5):  # on to ten missed cycles
        rig.step()
    assert rig.state().bodyLanguage is B.hiss
    assert [e.bodyLanguage for e in rig.events()] == [B.tailFlick, B.hiss]
    assert rig.events()[1].title.startswith("fake is missing: no successful cycle for 5 min")
    rig.fake.fail = None
    rig.step()
    assert rig.state().bodyLanguage is B.slowBlink
    back = rig.events()[-1]
    assert back.bodyLanguage is B.slowBlink and back.title.startswith("fake is back (was hiss for ")
    assert len(rig.events()) == 3


def test_the_watchdog_needs_no_cycle_to_notice_a_collector_that_stopped_running(rig):
    rig.step()
    rig.clock.advance(minutes=6)  # nothing runs at all: a hung loop, a dead task
    rig.runner.check()
    assert rig.state().bodyLanguage is B.hiss
    assert rig.events()[-1].title.startswith("fake is missing: no successful cycle for 6 min")


def test_a_hung_cycle_is_cut_off_and_counted_as_a_miss(tmp_path, clock):
    r = Rig(tmp_path, clock, timeout=0.05)
    try:
        r.step()
        r.fake.hang = True
        r.step()
        assert r.runner.report()["fake"]["lastError"] == "the cycle took longer than 0.05 s"
        r.fake.hang = False
        r.step()
        assert r.runner.report()["fake"]["lastError"] is None
    finally:
        r.close()


def test_errors_are_scrubbed_before_they_reach_scentTrail(tmp_path, clock):
    r = Rig(tmp_path, clock, secrets=["SECRET-VALUE-1234"])
    try:
        r.step()
        r.fake.fail = RuntimeError("it broke with SECRET-VALUE-1234 and Authorization: Bearer abcdefghijklmnop")
        for _ in range(5):
            r.step()
        dump = repr(r.trail.states()) + repr(r.trail.events())
        assert "SECRET-VALUE-1234" not in dump and "abcdefghijklmnop" not in dump
        assert "it broke with" in dump
    finally:
        r.close()


def test_report_for_healthz(rig):
    rig.step()
    report = rig.runner.report()["fake"]
    assert report["level"] == "slowBlink" and report["lastOkAt"].endswith("Z") and report["every"] == 30


# -- the real loop ------------------------------------------------------------------------------


def test_the_loop_runs_every_collector_and_stops_cleanly(tmp_path, clock):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    fake = Fake()
    runner = Runner(trail, [fake], clock=clock, pause=lambda c: 0.01)

    async def go():
        task = asyncio.create_task(runner.run())
        deadline = time.monotonic() + 5
        while fake.cycles < 3 and time.monotonic() < deadline:
            await asyncio.sleep(0.01)
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)

    asyncio.run(go())
    assert fake.cycles >= 3 and trail.states()["collector:fake"].bodyLanguage is B.slowBlink
    trail.close()


# -- what perch starts from its settings -----------------------------------------------------------


def settings(tmp_path, **kw):
    return Settings(repoDir=tmp_path, trailDb=tmp_path / "t.db", **kw)


def test_nothing_configured_starts_no_collector(tmp_path, fleetTree, clock):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    assert buildCollectors(settings(tmp_path), trail, fleetTree, clock) == []
    assert trail.events() == []  # purr simply isn't watching: every app stays unknown
    trail.close()


def test_purr_without_its_key_is_off_and_says_so_once(tmp_path, fleetTree, clock):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    assert buildCollectors(settings(tmp_path, purrUrl="http://komodo-core:9120"), trail, fleetTree, clock) == []
    (event,) = trail.events()
    assert event.bodyLanguage is B.tailFlick and event.title.startswith("purr is switched off")
    assert "PERCH_PURR_KEY" in event.title
    trail.close()


def test_purr_is_built_from_its_settings(tmp_path, fleetTree, clock):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    cfg = settings(
        tmp_path,
        purrUrl="http://komodo-core:9120",
        purrKey="K-fake",
        purrSecret="S-fake",
        purrEvery=45,
        sleepers=("roastery", "spare"),
        tz="Asia/Kolkata",
    )
    (purr,) = buildCollectors(cfg, trail, fleetTree, clock)
    assert isinstance(purr, Purr) and purr.rhythm == Rhythm(every=45)
    assert purr.sleepers == {"roastery", "spare"} and purr.tz == ZoneInfo("Asia/Kolkata")
    asyncio.run(purr.aclose())
    trail.close()


def test_settings_sleepers_and_secrets():
    assert Settings.fromEnv({}).sleepers == ("roastery",)
    assert Settings.fromEnv({"PERCH_SLEEPERS": " roastery , spare ,"}).sleepers == ("roastery", "spare")
    assert Settings.fromEnv({"PERCH_SLEEPERS": ""}).sleepers == ("roastery",)
    shown = repr(Settings(purrKey="K-fake-key-123", purrSecret="S-fake-secret-123"))
    assert "K-fake-key-123" not in shown and "S-fake-secret-123" not in shown and "<set>" in shown


# -- wired into the app ---------------------------------------------------------------------------


def test_the_app_starts_and_stops_its_collectors_and_healthz_reports_them(tmp_path, fleetRepo, fleetTree, clock):
    cfg = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db")
    trail = ScentTrail(cfg.trailDb, clock=clock)
    fake = Fake()
    app = createApp(cfg, trail=trail, tree=fleetTree, clock=clock, collectors=[fake])
    with TestClient(app) as client:
        deadline = time.monotonic() + 5
        while fake.cycles < 1 and time.monotonic() < deadline:
            time.sleep(0.01)
        assert fake.cycles >= 1
        body = client.get("/healthz").json()
        assert body["ok"] and body["collectors"]["fake"]["level"] == "slowBlink"
    assert fake.closed
    trail.close()
