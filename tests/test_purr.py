"""purr against a fake Komodo built from the pinned fleet repo, with a fake clock: the M1
gate (05 plan 5) and the rules of design plan 4.1."""

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from komodoFake import FleetFake

from perch.bodyLanguage import BodyLanguage as B
from perch.rollup import Status
from perch.scentTrail import ScentTrail
from perch.senses.komodo import KomodoError
from perch.senses.purr import Purr

IST = ZoneInfo("Asia/Kolkata")
# conftest's clock starts at 07:00 IST: outside roastery's 01:25-04:25 wake window
IN_WINDOW_WAKE = datetime(2026, 9, 28, 19, 55, tzinfo=UTC)  # 01:25 IST on the 29th


class World:
    def __init__(self, fleetTree, tmp_path, clock):
        self.clock = clock
        self.fleet = fleetTree.fleet()
        self.fake = FleetFake(self.fleet, clock)
        self.trail = ScentTrail(tmp_path / "t.db", clock=clock)
        self.purr = Purr(self.fake.client(), self.trail, fleetTree, clock=clock, every=30, tz=IST)
        self.loop = asyncio.new_event_loop()

    def cycle(self, n=1):
        """n purr cycles, 30 s apart. Returns the error of the last one, if Komodo couldn't be read."""
        error = None
        for _ in range(n):
            error = None
            try:
                self.loop.run_until_complete(self.purr.cycle())
            except KomodoError as exc:
                error = exc
            self.clock.advance(seconds=30)
        return error

    def status(self):
        return Status(self.fleet, self.trail)

    def state(self, subject):
        return self.trail.states()[subject]

    def events(self, subject=None):
        found = self.trail.events(subjectPrefix=subject) if subject else self.trail.events()
        return list(reversed(found))  # oldest first

    def close(self):
        self.loop.run_until_complete(self.purr.aclose())
        self.loop.close()
        self.trail.close()


@pytest.fixture
def w(fleetTree, tmp_path, clock):
    world = World(fleetTree, tmp_path, clock)
    yield world
    world.close()


# -- a quiet fleet ------------------------------------------------------------------------


def test_a_healthy_fleet_is_slowBlink_everywhere_and_says_nothing(w):
    w.cycle()
    status = w.status()
    assert status.fleetLevel() is B.slowBlink
    assert status.counts()[B.slowBlink] == w.fleet.appCount
    assert w.trail.events() == []
    n8n = w.state("container:grinder/n8n")
    assert n8n.bodyLanguage is B.slowBlink
    assert (n8n.detail["image"], n8n.detail["app"], n8n.detail["label"]) == ("example/n8n:1", "n8n", "healthy")
    assert w.state("app:grinder/n8n").title == "healthy"
    vitals = w.state("node:grinder").detail
    assert (vitals["cpu"], vitals["mem"], vitals["disk"]) == (20.0, 40.0, 50.0)


def test_purr_only_reads(w):
    w.cycle(3)
    assert {r["type"] for r in w.fake.requests} == {"ListServers", "ListContainers"}
    assert {r["path"] for r in w.fake.requests} == {"/read"}


# -- the M1 gate ----------------------------------------------------------------------------


def test_GATE_n8n_exited_hisses_app_node_and_fleet_within_two_cycles_and_recovers(w):
    w.cycle(2)
    assert w.status().fleetLevel() is B.slowBlink
    w.fake.exit("grinder", "n8n", 137)
    w.cycle()  # the first look: held, nobody is paged for a blip
    assert w.status().app("grinder", "n8n") is B.slowBlink
    w.cycle()  # the second: confirmed, 60 s after it stopped
    status = w.status()
    assert status.app("grinder", "n8n") is B.hiss
    assert status.node("grinder") is B.hiss
    assert status.fleetLevel() is B.hiss
    for other in ("sieve", "percolator", "cellar", "mochaPot", "roastery"):
        assert status.node(other) is B.slowBlink, other
    assert w.state("app:grinder/n8n").title == "exited (code 137: killed, often out of memory)"
    assert w.state("container:grinder/n8n").detail["exitCode"] == 137
    (event,) = w.events()
    assert (event.sense, event.subject, event.bodyLanguage) == ("purr", "app:grinder/n8n", B.hiss)
    assert event.title == "n8n exited (code 137: killed, often out of memory)"

    w.fake.start("grinder", "n8n")
    w.cycle()  # recovery is not held back
    status = w.status()
    assert status.app("grinder", "n8n") is B.slowBlink
    assert status.node("grinder") is B.slowBlink and status.fleetLevel() is B.slowBlink
    recovery = w.events()[-1]
    assert recovery.bodyLanguage is B.slowBlink and recovery.title.startswith("n8n is back (was hiss for ")
    assert len(w.events()) == 2  # one hiss, one recovery: no more


def test_GATE_roastery_asleep_outside_its_window_is_slowBlink_not_hiss(w):
    w.cycle(2)
    w.fake.nodeDown("roastery")
    w.cycle(4)
    status = w.status()
    assert status.node("roastery") is B.slowBlink
    assert status.app("roastery", "immich-ml") is B.slowBlink
    assert status.fleetLevel() is B.slowBlink
    node = w.state("node:roastery")
    assert node.title == "asleep, as expected (wakes 01:25)" and node.detail["mode"] == "asleep"
    assert w.state("container:roastery/immich-machine-learning").bodyLanguage is B.unknown  # can't see it, and says so
    assert w.events() == []


def test_roastery_unreachable_inside_its_wake_window_is_hiss_once_it_had_time_to_wake(w, clock):
    clock.now = IN_WINDOW_WAKE
    w.cycle(2)  # 01:25: up
    w.fake.nodeDown("roastery")
    w.cycle(2)  # 01:26-01:27, inside the 10-minute settle: still waking
    assert w.status().node("roastery") is B.slowBlink
    assert w.state("node:roastery").title == "waking up for the nightly backups"
    clock.advance(minutes=10)  # 01:37: it must answer by now
    w.cycle(2)
    status = w.status()
    assert status.node("roastery") is B.hiss and status.fleetLevel() is B.hiss
    assert status.app("roastery", "immich-ml") is B.unknown  # can't see it, which isn't "down"
    assert w.state("node:roastery").title.startswith("roastery isn't answering inside its wake window")
    (event,) = w.events()
    assert event.subject == "node:roastery" and event.bodyLanguage is B.hiss


def test_roastery_back_after_a_hiss_is_announced_once(w, clock):
    clock.now = IN_WINDOW_WAKE
    clock.advance(minutes=15)
    w.cycle(2)
    w.fake.nodeDown("roastery")
    w.cycle(2)
    w.fake.nodeUp("roastery")
    w.cycle(2)
    assert w.status().fleetLevel() is B.slowBlink
    assert [e.bodyLanguage for e in w.events("node:roastery")] == [B.hiss, B.slowBlink]
    assert w.events("node:roastery")[1].title.startswith("roastery is back (was hiss for ")


def test_a_non_sleeping_node_that_stops_answering_is_hiss_at_any_hour(w):
    w.cycle(2)
    w.fake.nodeDown("grinder")
    w.cycle()
    assert w.status().node("grinder") is B.slowBlink  # held once
    w.cycle()
    status = w.status()
    assert status.node("grinder") is B.hiss and status.fleetLevel() is B.hiss
    assert status.app("grinder", "n8n") is B.unknown  # unknown, not 12 separate hisses
    assert w.state("node:grinder").title == "grinder isn't answering: Periphery is not connected"
    assert [e.subject for e in w.events()] == ["node:grinder"]  # one event for the node, none per app


# -- the rules (design plan 4.1) ---------------------------------------------------------------


def test_a_one_cycle_blip_never_becomes_a_hiss(w):
    w.cycle(2)
    w.fake.exit("grinder", "n8n")
    w.cycle()
    w.fake.start("grinder", "n8n")
    w.cycle(3)
    assert w.status().fleetLevel() is B.slowBlink
    assert w.events() == []


def test_an_unhealthy_container_is_hiss_after_two_looks(w):
    w.cycle(2)
    w.fake.setHealth("grinder", "openwebui", "unhealthy")
    w.cycle(2)
    assert w.status().app("grinder", "openwebui") is B.hiss
    assert w.state("app:grinder/openwebui").title == "is running but unhealthy"
    w.fake.setHealth("grinder", "openwebui", "healthy")
    w.cycle()
    assert w.status().app("grinder", "openwebui") is B.slowBlink


def test_a_container_still_starting_is_a_notice(w):
    w.cycle(2)
    w.fake.setHealth("grinder", "n8n", "health: starting")
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.earTwitch and w.status().fleetLevel() is B.earTwitch
    assert w.events() == []


def test_a_restart_is_a_tailFlick_for_15_minutes(w):
    w.cycle(2)
    w.clock.advance(minutes=5)
    w.fake.restart("grinder", "n8n")  # a crash and restart: same container, uptime back to zero
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.tailFlick  # at once: a restart needs no second look
    assert w.state("app:grinder/n8n").title == "restarted (1st in 15 min)"
    (event,) = w.events()
    assert event.bodyLanguage is B.tailFlick and event.title == "n8n restarted (1st in 15 min)"
    w.clock.advance(minutes=14)
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.tailFlick
    w.clock.advance(minutes=2)
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.slowBlink  # the window slid past it
    assert w.events()[-1].title.startswith("n8n is back")


def test_three_restarts_in_15_minutes_is_a_hiss_without_waiting_for_a_second_look(w):
    w.cycle(2)
    for _ in range(3):
        w.cycle(4)  # two minutes of ordinary 30-second samples, uptime growing, then it crashes again
        w.fake.restart("grinder", "n8n")
        w.cycle()
    assert w.status().app("grinder", "n8n") is B.hiss
    assert w.state("app:grinder/n8n").title == "is restarting in a loop (3 restarts in 15 min)"
    assert [e.bodyLanguage for e in w.events()] == [B.tailFlick, B.tailFlick, B.hiss]
    assert [e.title for e in w.events()][:2] == ["n8n restarted (1st in 15 min)", "n8n restarted (2nd in 15 min)"]


def test_the_two_year_uptime_quirk_is_not_a_restart(w):
    """go-units prints "1 years" after "24 months" for half an hour at the 2-year mark."""
    w.cycle(2)
    w.fake.box("grinder", "n8n").since = w.clock() - timedelta(seconds=63_070_190)
    w.cycle()  # Up 24 months
    assert "Up 24 months" in w.state("container:grinder/n8n").detail["status"]
    w.cycle()  # 30 s later: Up 1 years, a lower number with no restart behind it
    assert "Up 1 years" in w.state("container:grinder/n8n").detail["status"]
    assert w.status().fleetLevel() is B.slowBlink and w.events() == []


def test_a_redeploy_is_not_a_restart(w):
    w.cycle(2)
    w.clock.advance(minutes=5)
    w.fake.recreate("grinder", "n8n")  # a new container under the same name
    w.cycle(2)
    assert w.status().fleetLevel() is B.slowBlink and w.events() == []


def test_a_container_that_keeps_restarting_is_a_tailFlick_while_it_does(w):
    w.cycle(2)
    w.fake.crashloop("grinder", "traccar", code=1)
    w.cycle(3)
    assert w.status().app("grinder", "traccar") is B.tailFlick
    assert w.state("app:grinder/traccar").title == "is restarting (last exit code 1)"
    assert w.status().node("grinder") is B.tailFlick


def test_a_removed_container_is_a_hiss_and_names_what_is_missing(w):
    w.cycle(2)
    w.fake.remove("grinder", "karakeep-chrome")  # the app has three containers; one is gone
    w.cycle()
    assert w.status().app("grinder", "karakeep") is B.slowBlink
    w.cycle()
    assert w.status().app("grinder", "karakeep") is B.hiss
    assert w.state("app:grinder/karakeep").title == "karakeep-chrome not found on grinder"
    assert w.state("container:grinder/karakeep").bodyLanguage is B.slowBlink  # the others are fine
    (event,) = w.events()
    assert event.subject == "app:grinder/karakeep" and event.title == "karakeep-chrome not found on grinder"
    w.fake.add("grinder", "karakeep-chrome", project="karakeep")
    w.cycle()
    assert w.status().app("grinder", "karakeep") is B.slowBlink


@pytest.mark.parametrize(
    ("disk", "level"), [(84.9, B.slowBlink), (85.0, B.tailFlick), (94.9, B.tailFlick), (95.0, B.hiss)]
)
def test_disk_thresholds(w, disk, level):
    w.fake.vitals("cellar", disk=disk)
    w.cycle()
    assert w.state("node:cellar").bodyLanguage is level
    assert w.status().node("cellar") is level


def test_disk_warning_event_and_recovery(w):
    w.cycle()
    w.fake.vitals("cellar", disk=88.0)
    w.cycle()
    w.fake.vitals("cellar", disk=60.0)
    w.cycle()
    first, second = w.events("node:cellar")
    assert (first.bodyLanguage, first.title) == (B.tailFlick, "cellar: disk 88 % full")
    assert second.bodyLanguage is B.slowBlink and second.title.startswith("cellar is back")


def test_containers_nobody_owns_are_shown_but_never_rolled_up(w):
    w.fake.add("grinder", "stray-test", project=None)
    w.fake.exit("grinder", "stray-test")
    w.cycle(3)
    stray = w.state("container:grinder/stray-test")
    assert stray.bodyLanguage is B.hiss and stray.detail["stray"] is True
    assert w.status().fleetLevel() is B.slowBlink and w.events() == []
    assert [s.subject for s in w.status().strays("grinder")] == ["container:grinder/stray-test"]
    w.fake.remove("grinder", "stray-test")
    w.cycle()
    assert "container:grinder/stray-test" not in w.trail.states()  # gone is gone


def test_a_container_is_matched_to_its_app_by_compose_project_or_by_name(w):
    w.fake.add("grinder", "n8n-worker", project="n8n")  # an extra container of n8n's compose project
    w.fake.exit("grinder", "n8n-worker")
    w.cycle(2)
    assert w.status().app("grinder", "n8n") is B.hiss
    assert w.state("app:grinder/n8n").title == "n8n-worker exited (code 137: killed, often out of memory)"
    w.fake.box("grinder", "embedding-worker").project = None  # no label: matched by its name
    w.fake.exit("grinder", "embedding-worker", 1)
    w.cycle(2)
    assert w.status().app("grinder", "embedding-worker") is B.hiss


def test_komodo_spelling_a_server_name_in_another_case_still_matches(w):
    w.fake.spelling["mochaPot"] = "mochapot"
    w.cycle()
    assert w.status().node("mochaPot") is B.slowBlink and w.status().app("mochaPot", "homeassistant") is B.slowBlink


def test_a_node_komodo_doesnt_know_or_has_disabled_is_unknown_not_hiss(w):
    w.cycle()
    del w.fake.servers["cellar"]
    w.fake.servers["sieve"]["state"] = "Disabled"
    w.fake.boxes.pop("cellar")
    w.cycle()
    status = w.status()
    assert status.node("cellar") is B.unknown and status.node("sieve") is B.unknown
    assert w.state("node:cellar").title == "Komodo has no server called cellar"
    assert w.state("node:sieve").title == "disabled in Komodo"
    assert status.fleetLevel() is B.unknown and w.events() == []


# -- when purr can't see ----------------------------------------------------------------------------


def test_komodo_down_turns_everything_unknown_after_two_cycles_never_hiss(w):
    w.cycle(2)
    w.fake.komodoDown = True
    assert isinstance(w.cycle(), KomodoError)
    assert w.status().fleetLevel() is B.slowBlink  # one miss is not enough to say anything
    assert isinstance(w.cycle(), KomodoError)
    status = w.status()
    assert status.fleetLevel() is B.unknown and status.app("grinder", "n8n") is B.unknown
    assert w.state("app:grinder/n8n").title == "Komodo isn't answering"
    assert w.state("node:grinder").detail["cpu"] == 20.0  # what it last knew is kept, greyed out
    assert w.events() == []
    w.fake.komodoDown = False
    assert w.cycle() is None
    assert w.status().fleetLevel() is B.slowBlink and w.events() == []


def test_one_node_whose_containers_cant_be_read_goes_unknown_after_two_cycles(w):
    w.cycle(2)
    w.fake.unreadable.add("grinder")
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.slowBlink
    w.cycle()
    status = w.status()
    assert status.app("grinder", "n8n") is B.unknown and status.node("grinder") is B.unknown
    assert status.node("sieve") is B.slowBlink  # the others carry on
    assert "can't read containers" in w.state("app:grinder/n8n").title
    assert w.state("node:grinder").detail["cpu"] == 20.0  # vitals still came from ListServers


def test_a_confirmed_hiss_survives_a_perch_restart_and_is_not_announced_twice(w, fleetTree):
    w.cycle(2)
    w.fake.exit("grinder", "n8n")
    w.cycle(2)
    assert len(w.events()) == 1
    again = Purr(w.fake.client(), w.trail, fleetTree, clock=w.clock, every=30, tz=IST)
    w.loop.run_until_complete(again.cycle())  # a fresh process: no memory, only scentTrail
    assert w.status().app("grinder", "n8n") is B.hiss  # its first look is held back: the old state stays
    w.clock.advance(seconds=30)
    w.loop.run_until_complete(again.cycle())
    assert w.status().app("grinder", "n8n") is B.hiss
    assert len(w.events()) == 1  # still the one event: hiss -> hiss is no news
    w.loop.run_until_complete(again.aclose())


def test_a_hiss_found_on_the_first_cycle_after_a_restart_is_confirmed_by_the_second(w):
    w.fake.exit("grinder", "n8n")
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.unknown  # nothing known yet, and not guessing
    w.cycle()
    assert w.status().app("grinder", "n8n") is B.hiss
    (event,) = w.events()
    assert event.bodyLanguage is B.hiss


def test_states_never_hold_the_komodo_key_or_secret(w):
    w.fake.exit("grinder", "n8n")
    w.cycle(3)
    dump = repr(w.trail.states()) + repr(w.trail.events(limit=500))
    assert "K-fake-key-for-tests" not in dump and "S-fake-secret-for-tests" not in dump
