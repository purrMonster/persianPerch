"""glare (05 plan M4, A8, design plan 4.3): Gatus's endpoints, read with a fixture shaped from Gatus v5.36.0.
The real Gatus is never contacted."""

import asyncio

import pytest
from outsideFakes import GATUS_PASSWORD, GatusFake

from perch.bodyLanguage import BodyLanguage as B
from perch.collectors import Runner
from perch.meow import findProblems
from perch.scentTrail import ScentTrail
from perch.senses.gatus import GatusClient, GatusError
from perch.senses.glare import Glare

TUNNEL = "network_cloudflare-tunnel"


class Rig:
    def __init__(self, tmp_path, clock):
        self.clock = clock
        self.fake = GatusFake(clock)
        self.trail = ScentTrail(tmp_path / "g.db", clock=clock)
        self.glare = Glare(self.fake.client(), self.trail, clock=clock)
        self.loop = asyncio.new_event_loop()
        self.fake.add("cloudflare tunnel", "network")
        self.fake.add("pihole", "network")
        self.fake.add("authelia", "identity")

    def cycle(self, n=1, seconds=60):
        error = None
        for _ in range(n):
            self.fake.tick(seconds)
            error = None
            try:
                self.loop.run_until_complete(self.glare.cycle())
            except GatusError as exc:
                error = exc
        return error

    def state(self, key):
        return self.trail.states()[f"glare:{key}"]

    def events(self):
        return list(reversed(self.trail.events(senses=["glare"])))

    def close(self):
        self.loop.run_until_complete(self.glare.aclose())
        self.loop.close()
        self.trail.close()


@pytest.fixture
def rig(tmp_path, clock):
    r = Rig(tmp_path, clock)
    yield r
    r.close()


def test_every_endpoint_gets_a_state_and_all_up_is_slowBlink(rig):
    rig.cycle(3)
    states = {s: st for s, st in rig.trail.states().items() if s.startswith("glare:")}
    assert set(states) == {f"glare:{TUNNEL}", "glare:network_pihole", "glare:identity_authelia"}
    assert all(st.bodyLanguage is B.slowBlink for st in states.values())
    assert states[f"glare:{TUNNEL}"].title == "up, 12 ms"
    assert states[f"glare:{TUNNEL}"].detail["name"] == "cloudflare tunnel"
    assert rig.events() == []


def test_the_rhythm_one_failure_is_a_blip_two_are_late_five_are_missing(rig):
    rig.cycle(3)
    rig.fake.check("network_pihole", up=False, why="dial tcp: connection refused")
    rig.loop.run_until_complete(rig.glare.cycle())
    one = rig.state("network_pihole")
    assert one.bodyLanguage is B.slowBlink and "last check failed" in one.title and rig.events() == []
    levels = []
    for _ in range(5):
        rig.clock.advance(seconds=60)
        rig.fake.check("network_pihole")
        rig.loop.run_until_complete(rig.glare.cycle())
        levels.append(rig.state("network_pihole").bodyLanguage)
    assert levels == [B.tailFlick, B.tailFlick, B.tailFlick, B.hiss, B.hiss]  # the 2nd to the 6th failure in a row
    events = rig.events()
    assert [e.bodyLanguage for e in events] == [B.tailFlick, B.hiss]
    assert events[0].title.startswith("pihole (network): failed 2 checks in a row")
    assert events[1].title.startswith("pihole (network): failed 5 checks in a row")


def test_recovery_says_how_long_it_was_bad(rig):
    rig.cycle(2)
    rig.fake.check("network_pihole", up=False, why="boom")
    for _ in range(3):
        rig.clock.advance(seconds=60)
        rig.fake.check("network_pihole")
        rig.loop.run_until_complete(rig.glare.cycle())
    rig.clock.advance(seconds=60)
    rig.fake.check("network_pihole", up=True)
    rig.loop.run_until_complete(rig.glare.cycle())
    assert rig.state("network_pihole").bodyLanguage is B.slowBlink
    last = rig.events()[-1]
    assert last.bodyLanguage is B.slowBlink and last.title.startswith("pihole (network) is back (was tailFlick for")


def test_an_endpoint_gatus_stopped_checking_is_unknown_not_up(rig):
    rig.cycle(3)
    rig.clock.advance(minutes=20)  # no new results for 20 minutes against a 1 minute rhythm
    rig.loop.run_until_complete(rig.glare.cycle())
    st = rig.state("identity_authelia")
    assert st.bodyLanguage is B.unknown and "hasn't recorded a check for 21 min" in st.title


def test_a_removed_endpoint_is_forgotten_and_its_history_stays(rig):
    rig.cycle(3)
    rig.fake.check("network_pihole", up=False)
    rig.cycle(3)
    del rig.fake.endpoints["network_pihole"]
    rig.cycle(1)
    assert "glare:network_pihole" not in rig.trail.states()
    assert rig.events()  # what it said while it existed is still true


def test_GATE_gatus_unreachable_is_one_tailFlick_and_unknown_never_a_hiss_per_endpoint(rig):
    rig.cycle(3)
    runner = Runner(rig.trail, [rig.glare], clock=rig.clock, pause=lambda c: 0.01)
    rig.fake.down = True
    for _ in range(6):
        rig.clock.advance(seconds=60)
        rig.loop.run_until_complete(runner.runOnce(rig.glare))
    states = [st for s, st in rig.trail.states().items() if s.startswith("glare:")]
    assert states and all(st.bodyLanguage is B.unknown for st in states)
    assert rig.events() == []  # not one event per endpoint
    collector = rig.trail.states()["collector:glare"]
    assert collector.bodyLanguage is B.tailFlick and "can't see Gatus" in collector.title
    flicks = [e for e in rig.trail.events() if e.subject == "collector:glare"]
    assert [e.bodyLanguage for e in flicks] == [B.tailFlick]  # exactly one
    assert not [e for e in rig.trail.events() if e.bodyLanguage is B.hiss]
    # and it comes back by itself
    rig.fake.down = False
    rig.clock.advance(seconds=60)
    rig.fake.tick()
    rig.loop.run_until_complete(runner.runOnce(rig.glare))
    assert rig.state(TUNNEL).bodyLanguage is B.slowBlink
    assert rig.trail.states()["collector:glare"].bodyLanguage is B.slowBlink


def test_a_refused_login_says_so_and_never_shows_the_password(rig):
    for status in (401, 403, 302):
        rig.fake.refuse = status
        error = rig.cycle(1)
        assert error and "login was refused" in str(error) and "PERCH_GLARE_PASSWORD" in str(error)
        assert GATUS_PASSWORD not in str(error)
    rig.fake.refuse = None
    rig.fake.notJson = True
    assert "not JSON" in str(rig.cycle(1))


def test_a_failed_check_flows_through_meow_like_everything_else(rig, fleetTree):
    rig.cycle(2)
    rig.fake.check("network_pihole", up=False, why="boom")
    for _ in range(5):
        rig.clock.advance(seconds=60)
        rig.fake.check("network_pihole")
        rig.loop.run_until_complete(rig.glare.cycle())
    found = findProblems(rig.trail.states(), fleetTree.fleet())
    (problem,) = [p for p in found.problems if p.key == "glare:network_pihole"]
    assert problem.level is B.hiss and problem.title.startswith("pihole: failed 6 checks in a row")


def test_glare_only_ever_sends_the_one_get(rig):
    rig.cycle(3)
    assert {(r.method, r.url.path) for r in rig.fake.requests} == {("GET", "/api/v1/endpoints/statuses")}
    assert all(r.url.params["pageSize"] == "20" for r in rig.fake.requests)


def test_the_client_needs_all_three_settings():
    with pytest.raises(ValueError, match="PERCH_GLARE_PASSWORD"):
        GatusClient("http://gatus.example.home.arpa", "perch-svc", "")


def test_a_result_in_another_shape_is_an_error_not_a_guess(rig):
    rig.fake.endpoints[TUNNEL].results.append({"success": "yes", "timestamp": "last tuesday"})
    error = rig.cycle(1)
    assert error and "not in the shape Gatus v5.36.0 sends" in str(error)
