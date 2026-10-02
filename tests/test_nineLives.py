"""nineLives (05 plan M3): the outside ping goes out every 5 minutes only while every collector is on
time, never as a /fail, and never carries or leaks its URL. Tested against a fake healthchecks server."""

import asyncio
from datetime import UTC, datetime

import pytest
from pushFakes import PING_URL, HealthchecksFake

from perch.bodyLanguage import BodyLanguage as B
from perch.collectors import Runner
from perch.nineLives import NineLives, footerLine
from perch.rhythms import Rhythm
from perch.scentTrail import ScentTrail


class Fake:
    rhythm = Rhythm(every=30)

    def __init__(self, name):
        self.name = name
        self.fails = False

    async def cycle(self):
        if self.fails:
            raise RuntimeError("down")

    async def aclose(self):
        pass


class Rig:
    def __init__(self, tmp_path, clock, names=("purr", "groom")):
        self.clock = clock
        self.trail = ScentTrail(tmp_path / "t.db", clock=clock)
        self.collectors = [Fake(n) for n in names]
        self.runner = Runner(self.trail, self.collectors, clock=clock)
        self.hc = HealthchecksFake()
        self.nine = NineLives(PING_URL, self.runner, self.trail, clock=clock, transport=self.hc.transport())
        self.loop = asyncio.new_event_loop()

    def tick(self, seconds=30, collectors=True, look=True):
        if collectors:
            for c in self.collectors:
                self.loop.run_until_complete(self.runner.runOnce(c))
        if look:
            self.loop.run_until_complete(self.nine.step())
        self.clock.advance(seconds=seconds)

    def minutes(self, n, **kw):
        for _ in range(n * 2):
            self.tick(**kw)

    def close(self):
        self.loop.run_until_complete(self.nine.aclose())
        self.loop.close()
        self.trail.close()


@pytest.fixture
def rig(tmp_path, clock):
    r = Rig(tmp_path, clock)
    yield r
    r.close()


def test_no_ping_until_every_collector_has_finished_a_cycle(rig):
    rig.tick(collectors=False)
    assert rig.hc.pings == []
    assert rig.trail.states()["ninelives"].bodyLanguage is B.unknown
    rig.tick()
    assert len(rig.hc.pings) == 1


def test_it_pings_every_5_minutes_with_a_plain_get_and_never_fails_the_check(rig):
    rig.minutes(30)
    assert 5 <= len(rig.hc.pings) <= 7  # one at the start, then one per 5 minutes
    assert {m for m, _ in rig.hc.pings} == {"GET"}
    assert all(not path.endswith(("/fail", "/start")) for _, path in rig.hc.pings)


def test_GATE_a_late_collector_stops_the_pings_and_a_recovery_resumes_them(rig):
    rig.minutes(10)
    before = len(rig.hc.pings)
    assert before >= 2
    rig.collectors[0].fails = True  # purr keeps failing: late after 3 missed cycles, missing after 10
    rig.minutes(30)
    mid = len(rig.hc.pings)
    assert mid <= before + 1  # at most the one already due before it was late
    rig.minutes(30)
    assert len(rig.hc.pings) == mid  # silence: healthchecks.io alerts from outside
    state = rig.trail.states()["ninelives"]
    assert state.bodyLanguage is B.tailFlick and "purr" in state.title
    rig.collectors[0].fails = False
    rig.minutes(6)
    assert len(rig.hc.pings) > mid
    assert rig.trail.states()["ninelives"].bodyLanguage is B.slowBlink


def test_GATE_perch_stopped_means_the_endpoint_hears_nothing(rig):
    rig.minutes(10)
    heard = len(rig.hc.pings)
    rig.minutes(60, collectors=False, look=False)  # the whole process is stopped: nothing runs at all
    assert len(rig.hc.pings) == heard


def test_perch_alive_but_its_collectors_not_running_is_silence_too(rig):
    rig.minutes(10)
    heard = len(rig.hc.pings)
    rig.minutes(60, collectors=False)  # nineLives still looks, nothing feeds the collectors
    assert len(rig.hc.pings) <= heard + 1


def test_an_unreachable_endpoint_is_said_once_and_never_crashes_or_leaks_the_url(rig):
    rig.hc.down = True
    rig.minutes(15)
    state = rig.trail.states()["ninelives"]
    assert state.bodyLanguage is B.tailFlick and "can't reach its endpoint" in state.title
    said = [e for e in rig.trail.events() if e.subject == "ninelives"]
    assert len(said) == 1
    rig.hc.down = False
    rig.minutes(6)
    assert rig.trail.states()["ninelives"].bodyLanguage is B.slowBlink
    blob = repr(rig.trail.events(limit=100)) + repr(rig.trail.states())
    assert "hc-ping" not in blob and "00000000-fake-uuid" not in blob


def test_the_footer_says_it_in_words():
    now = datetime(2026, 9, 29, tzinfo=UTC)
    assert footerLine(None, now, configured=False) == (B.unknown, "nineLives off (no ping URL set)")
    assert footerLine(None, now, configured=True) == (B.unknown, "nineLives not yet")


def test_a_url_that_is_not_http_is_refused(tmp_path, clock):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    with pytest.raises(ValueError):
        NineLives("not a url", Runner(trail, [], clock=clock), trail, clock=clock)
    trail.close()
