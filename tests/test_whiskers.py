"""whiskers (05 plan M5, design plan 4.5, Q14, test S4): Home Assistant over a WebSocket, against a fake
Home Assistant on loopback (tests/haFake.py). No real Home Assistant request is ever made."""

import ast
import asyncio
import json
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from haFake import TOKEN, HAFake

from perch.bodyLanguage import BodyLanguage as B
from perch.collectors import Runner, buildCollectors
from perch.meow import findProblems
from perch.rollup import Status
from perch.scentTrail import ScentTrail
from perch.scrub import scrub
from perch.senses import whiskers as module
from perch.senses.whiskers import (
    ALLOWED_TYPES,
    ConfigError,
    ForbiddenMessage,
    Whiskers,
    WhiskersError,
    loadConfig,
    parseConfig,
    socketUrl,
)
from perch.settings import Settings

ROOT = Path(__file__).resolve().parents[1]
CONFIG = """
entities:
  binary_sensor.front_door:
    name: Front door
    states: {"on": earTwitch}
    words: {"on": open, "off": closed}
  binary_sensor.kitchen_leak:
    name: Kitchen leak sensor
    states: {"on": hiss}
    words: {"on": wet, "off": dry}
  sensor.ups_status:
    name: UPS
    states: {"On Battery": tailFlick, "Online": slowBlink}
    default: earTwitch
  binary_sensor.hall_smoke:
    name: Hall smoke alarm
    states: {"on": hiss}
"""


@pytest.fixture(autouse=True)
def quickBackoff(monkeypatch):
    monkeypatch.setattr(module, "BACKOFF", (0.05, 0.2))


class Rig:
    """One event loop that runs the fake Home Assistant and whiskers together."""

    def __init__(self, tmp_path, clock, config=CONFIG, token=TOKEN):
        self.clock = clock
        self.loop = asyncio.new_event_loop()
        self.ha = HAFake()
        self.ha.set("binary_sensor.front_door", "off")
        self.ha.set("binary_sensor.kitchen_leak", "off")
        self.ha.set("sensor.ups_status", "Online")
        self.ha.set("binary_sensor.hall_smoke", "off")
        self.ha.set("light.kitchen", "on")  # not on the list
        self.trail = ScentTrail(tmp_path / "w.db", clock=clock)
        self.entities = parseConfig(config)
        self.token = token
        self.whiskers = None
        self.run(self.ha.start())

    def make(self):
        self.whiskers = Whiskers(self.ha.url, self.token, self.entities, self.trail, clock=self.clock)
        return self.whiskers

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def cycle(self):
        error = None
        try:
            self.run(self.whiskers.cycle())
        except WhiskersError as exc:
            error = exc
        return error

    def settle(self, seconds=0.3):
        self.run(asyncio.sleep(seconds))

    def change(self, entity, state):
        self.clock.advance(seconds=1)  # events a millisecond apart would sort by their random ids
        self.run(self.ha.change(entity, state))
        self.settle(0.15)

    def state(self, entity):
        return self.trail.states()[f"whiskers:{entity}"]

    def events(self):
        return list(reversed(self.trail.events(senses=["whiskers"])))

    def close(self):
        if self.whiskers:
            self.run(self.whiskers.aclose())
        self.run(self.ha.stop())
        leftovers = [t for t in asyncio.all_tasks(self.loop) if not t.done()]
        for task in leftovers:
            task.cancel()

        async def reap():
            await asyncio.gather(*leftovers, return_exceptions=True)

        self.run(reap())
        self.run(self.loop.shutdown_asyncgens())
        self.loop.close()
        self.trail.close()


@pytest.fixture
def rig(tmp_path, clock):
    r = Rig(tmp_path, clock)
    r.make()
    yield r
    r.close()


# -- the entity list -------------------------------------------------------------------------------------


def test_the_shipped_example_parses_with_generic_entities_and_every_kind_04_asks_for():
    found = loadConfig(ROOT / "whiskers.example.yml")
    ids = " ".join(found)
    for word in ("door", "window", "feeder", "fountain", "leak", "smoke", "ups"):
        assert word in ids
    assert found["binary_sensor.kitchen_water_leak"].levels == {"on": B.hiss}
    assert found["binary_sensor.hall_smoke"].levels["unavailable"] is B.tailFlick
    assert found["binary_sensor.front_door"].levels == {"on": B.earTwitch}  # `"on"` quoted, a word not a boolean
    assert found["binary_sensor.front_door"].words == {"on": "open", "off": "closed"}


def test_a_bare_on_and_off_in_yaml_still_mean_the_words():
    found = parseConfig("entities:\n  switch.x:\n    states: {on: hiss}\n    words: {off: closed}\n")
    assert found["switch.x"].levels == {"on": B.hiss} and found["switch.x"].words == {"off": "closed"}


@pytest.mark.parametrize(
    ("text", "fragment"),
    [
        ("", "entities"),
        ("entities: {}", "entities"),
        ("entities: [a]", "entities"),
        ("entities:\n  front door: {}", "an entity id looks like"),
        ("entities:\n  a.b:\n    states: {on: loud}", "isn't a level"),
        ("entities:\n  a.b:\n    default: red", "isn't a level"),
        ("entities:\n  a.b: [1]", "needs `name`"),
        ("entities: [unclosed", "not valid YAML"),
    ],
)
def test_a_bad_entity_list_says_which_entity_and_what_is_wrong(text, fragment):
    with pytest.raises(ConfigError, match=fragment):
        parseConfig(text)


def test_an_unreadable_file_is_a_config_error_not_a_crash(tmp_path):
    with pytest.raises(ConfigError, match="can't read"):
        loadConfig(tmp_path / "nope.yml")


@pytest.mark.parametrize(
    ("given", "wanted"),
    [
        ("http://192.0.2.13:8123", "ws://192.0.2.13:8123/api/websocket"),
        ("https://ha.example.home.arpa", "wss://ha.example.home.arpa/api/websocket"),
        ("ws://192.0.2.13:8123/api/websocket", "ws://192.0.2.13:8123/api/websocket"),
        ("http://192.0.2.13:8123/", "ws://192.0.2.13:8123/api/websocket"),
    ],
)
def test_the_url_becomes_the_websocket_address(given, wanted):
    assert socketUrl(given) == wanted


@pytest.mark.parametrize("bad", ["", "ftp://x", "192.0.2.13:8123", "http://"])
def test_a_url_that_is_not_an_address_is_refused(bad):
    with pytest.raises(ValueError, match="PERCH_WHISKERS_URL"):
        socketUrl(bad)


# -- S4: what perch may say -------------------------------------------------------------------------------


def test_S4_perch_sends_only_auth_subscribe_events_and_get_states_in_that_order(rig):
    assert rig.cycle() is None
    rig.change("binary_sensor.front_door", "on")
    rig.change("light.kitchen", "off")
    rig.cycle()
    assert rig.ha.types() == ["auth", "subscribe_events", "get_states"]
    assert set(rig.ha.types()) <= ALLOWED_TYPES
    sub = rig.ha.received[1]
    assert sub["event_type"] == "state_changed" and isinstance(sub["id"], int)
    assert rig.ha.received[0]["access_token"] == TOKEN
    assert "access_token" not in json.dumps(rig.ha.received[1:])  # the token is sent once, in auth


def test_S4_through_every_reconnect_too(rig):
    rig.cycle()
    for _ in range(3):
        rig.run(rig.ha.drop())
        rig.settle(0.6)
    assert rig.ha.connects >= 3
    assert set(rig.ha.types()) <= ALLOWED_TYPES


@pytest.mark.parametrize(
    "message",
    [
        {"id": 5, "type": "call_service", "domain": "light", "service": "turn_off"},
        {"id": 5, "type": "ping"},
        {"id": 5, "type": "subscribe_entities"},
        {"id": 5, "type": "config/auth/list"},
        {"id": 5, "type": "subscribe_events", "event_type": "call_service"},
        {"id": 5, "type": "subscribe_events"},
        {"type": ""},
        {},
    ],
)
def test_S4_the_one_send_function_refuses_everything_else_and_sends_nothing(rig, message):
    rig.cycle()
    sent = len(rig.ha.received)

    class Wire:
        async def send(self, text):
            raise AssertionError("it was sent")

    with pytest.raises(ForbiddenMessage):
        rig.run(rig.whiskers._send(Wire(), message))
    assert len(rig.ha.received) == sent


def test_S4_in_the_source_there_is_exactly_one_place_that_writes_to_the_socket():
    source = Path(module.__file__).read_text(encoding="utf-8")
    tree = ast.parse(source)
    sends = [n for n in ast.walk(tree) if isinstance(n, ast.Call) and getattr(n.func, "attr", "") == "send"]
    assert len(sends) == 1
    for word in ("call_service", "turn_on", "turn_off", "fire_event", "subscribe_entities", '"ping"'):
        assert word not in source.replace("never calls a service", "")


# -- what whiskers keeps ----------------------------------------------------------------------------------


def test_the_snapshot_judges_the_listed_entities_and_drops_the_rest(rig):
    assert rig.cycle() is None
    states = {s: v for s, v in rig.trail.states().items() if s.startswith("whiskers:")}
    assert sorted(states) == [
        "whiskers:binary_sensor.front_door",
        "whiskers:binary_sensor.hall_smoke",
        "whiskers:binary_sensor.kitchen_leak",
        "whiskers:sensor.ups_status",
    ]
    assert all(v.bodyLanguage is B.slowBlink for v in states.values())
    assert rig.state("binary_sensor.front_door").title == "Front door: closed"
    assert rig.events() == []  # a normal morning is silent
    assert not [s for s in rig.trail.states() if "light.kitchen" in s]


def test_an_entity_home_assistant_does_not_list_is_unknown_with_its_reason(rig):
    del rig.ha.states["binary_sensor.hall_smoke"]
    rig.cycle()
    state = rig.state("binary_sensor.hall_smoke")
    assert state.bodyLanguage is B.unknown and "doesn't list it" in state.title
    assert rig.events() == []


def test_a_door_opening_is_an_earTwitch_event_and_closing_says_how_long(rig):
    rig.cycle()
    rig.change("binary_sensor.front_door", "on")
    rig.clock.advance(minutes=3)
    rig.change("binary_sensor.front_door", "off")
    first, second = rig.events()
    assert (first.bodyLanguage, first.title) == (B.earTwitch, "Front door: open")
    assert second.bodyLanguage is B.slowBlink and second.title.startswith("Front door: closed (was earTwitch for")
    assert first.subject == "whiskers:binary_sensor.front_door"
    assert rig.state("binary_sensor.front_door").bodyLanguage is B.slowBlink


def test_a_leak_is_a_hiss_that_moves_the_fleet_and_meow_pushes_it_but_a_door_is_not_pushed(rig, fleetTree):
    rig.cycle()
    rig.change("binary_sensor.front_door", "on")
    rig.change("binary_sensor.kitchen_leak", "on")
    leak = rig.events()[-1]
    assert (leak.bodyLanguage, leak.title) == (B.hiss, "Kitchen leak sensor: wet")
    fleet = fleetTree.fleet()
    status = Status(fleet, rig.trail)
    assert status.fleetLevel() is B.hiss
    assert [a.title for a in status.attention() if a.subject.startswith("whiskers:")] == ["Kitchen leak sensor: wet"]
    problems = findProblems(rig.trail.states(), fleet).problems
    assert [(p.level, p.title) for p in problems if "whiskers" in p.key] == [(B.hiss, "Kitchen leak sensor: wet")]


def test_a_door_open_does_not_move_the_fleet(rig, fleetTree):
    rig.cycle()
    rig.change("binary_sensor.front_door", "on")
    status = Status(fleetTree.fleet(), rig.trail)
    assert status.whiskers()[0].bodyLanguage is B.earTwitch
    assert status.fleetLevel() is not B.earTwitch or status.fleetLevel().rank <= B.unknown.rank


def test_an_ups_state_outside_the_list_takes_the_default(rig):
    rig.cycle()
    rig.change("sensor.ups_status", "Charging")
    assert rig.state("sensor.ups_status").bodyLanguage is B.earTwitch
    rig.change("sensor.ups_status", "On Battery")
    assert rig.state("sensor.ups_status").bodyLanguage is B.tailFlick


def test_everything_not_on_the_list_is_dropped_before_it_is_stored(rig):
    rig.cycle()
    before = rig.trail.counts()
    for i in range(200):
        rig.run(rig.ha.change(f"sensor.power_{i % 7}", str(i)))
    rig.run(rig.ha.change("light.kitchen", "off"))
    rig.settle(0.3)
    after = rig.trail.counts()
    assert after["events"] == before["events"] and after["state"] == before["state"]
    assert not [s for s in rig.trail.states() if "power_" in s or "light" in s]


def test_an_unavailable_device_is_unknown_and_makes_no_event(rig):
    rig.cycle()
    rig.change("binary_sensor.front_door", "unavailable")
    assert rig.state("binary_sensor.front_door").bodyLanguage is B.unknown
    assert rig.events() == []


# -- Home Assistant goes away -----------------------------------------------------------------------------


def test_GATE_home_assistant_unreachable_is_one_tailFlick_and_unknown_never_a_hiss_per_entity(
    tmp_path, clock, fleetTree
):
    r = Rig(tmp_path, clock)
    whiskers = r.make()
    runner = Runner(r.trail, [whiskers], clock=clock)
    try:
        r.run(runner.runOnce(whiskers))
        assert r.state("binary_sensor.front_door").bodyLanguage is B.slowBlink
        r.run(r.ha.stop())
        r.settle(0.3)
        for _ in range(6):  # three minutes of 30 s collector cycles with Home Assistant gone
            clock.advance(seconds=30)
            r.run(runner.runOnce(whiskers))
        states = {s: v for s, v in r.trail.states().items() if s.startswith("whiskers:")}
        assert states and all(v.bodyLanguage is B.unknown for v in states.values())
        assert all("isn't answering" in v.title for v in states.values())
        trailEvents = r.trail.events()
        assert [e for e in trailEvents if e.sense == "whiskers"] == []  # no event per entity
        flicks = [e for e in trailEvents if e.bodyLanguage in (B.tailFlick, B.hiss)]
        assert [(e.sense, e.subject, e.bodyLanguage) for e in flicks] == [("perch", "collector:whiskers", B.tailFlick)]
        assert "whiskers is late" in flicks[0].title
        assert not any(p.level is B.hiss for p in findProblems(r.trail.states(), fleetTree.fleet()).problems)
        # five minutes in, the collector's own rhythm escalates (one hiss about whiskers itself, M1's rule);
        # still nothing per entity
        for _ in range(8):
            clock.advance(seconds=30)
            r.run(runner.runOnce(whiskers))
        assert [e.bodyLanguage for e in r.trail.events(senses=["perch"]) if e.subject == "collector:whiskers"] == [
            B.hiss,
            B.tailFlick,
        ]
        assert [e for e in r.trail.events() if e.sense == "whiskers"] == []
        # and it comes back by itself
        r.run(r.ha.start())
        for _ in range(8):
            clock.advance(seconds=30)
            r.run(runner.runOnce(whiskers))
            r.settle(0.3)
        assert r.state("binary_sensor.front_door").bodyLanguage is B.slowBlink
        assert any(e.title.startswith("whiskers is back") for e in r.trail.events(senses=["perch"]))
    finally:
        r.close()


def test_a_dropped_connection_comes_back_by_itself_and_a_change_during_the_gap_is_not_lost(rig):
    rig.cycle()
    rig.run(rig.ha.stop())
    rig.settle(0.3)
    rig.ha.set("binary_sensor.front_door", "on")  # opened while perch was blind
    rig.run(rig.ha.start())
    rig.settle(0.8)
    assert rig.cycle() is None
    assert rig.state("binary_sensor.front_door").bodyLanguage is B.earTwitch
    assert [e.title for e in rig.events()] == ["Front door: open"]


def test_the_same_state_after_a_reconnect_is_not_a_new_event(rig):
    rig.cycle()
    rig.change("binary_sensor.kitchen_leak", "on")
    assert len(rig.events()) == 1
    rig.run(rig.ha.drop())
    rig.settle(0.8)
    rig.cycle()
    assert len(rig.events()) == 1  # still wet, still one hiss


def test_a_refused_token_is_said_without_the_token(tmp_path, clock, caplog):
    r = Rig(tmp_path, clock)
    r.ha.refuseToken = True
    whiskers = r.make()
    try:
        with caplog.at_level(logging.DEBUG):
            error = r.cycle()
            r.settle(0.3)
        assert isinstance(error, WhiskersError) and "refused the token" in str(error)
        assert TOKEN not in str(error) and TOKEN not in caplog.text and TOKEN not in repr(vars(whiskers).get("url"))
        assert not [s for s in r.trail.states() if s.startswith("whiskers:")]
    finally:
        r.close()


def test_the_token_never_reaches_the_trail_the_logs_or_a_scrubbed_message(rig, caplog):
    with caplog.at_level(logging.DEBUG):
        rig.cycle()
        rig.change("binary_sensor.front_door", "on")
        rig.run(rig.ha.stop())
        rig.settle(0.3)
        rig.cycle()
        rig.cycle()
    dump = json.dumps([[e.title, e.detail, e.logTail] for e in rig.trail.events(limit=500)], default=str)
    dump += json.dumps({k: [s.title, s.detail] for k, s in rig.trail.states().items()}, default=str)
    assert TOKEN not in dump and TOKEN not in caplog.text
    # a JWT's shape is masked even when perch doesn't know that token
    assert scrub(f"login failed with {TOKEN} for x") == "login failed with •••• for x"


def test_a_whiskers_with_no_token_does_not_start(tmp_path, clock):
    with pytest.raises(ValueError, match="PERCH_WHISKERS_TOKEN"):
        Whiskers("ws://127.0.0.1:1/api/websocket", "", parseConfig(CONFIG), ScentTrail(tmp_path / "x.db"), clock=clock)


def test_something_that_is_not_home_assistant_is_said_plainly(tmp_path, clock):
    async def noise(ws):
        await ws.send("hello")
        await ws.wait_closed()

    from websockets.asyncio.server import serve

    async def listen():
        return await serve(noise, "127.0.0.1", 0)

    r = Rig(tmp_path, clock)
    server = r.run(listen())
    port = server.sockets[0].getsockname()[1]
    whiskers = Whiskers(f"ws://127.0.0.1:{port}", TOKEN, r.entities, r.trail, clock=clock)
    r.whiskers = whiskers
    try:
        error = r.cycle()
        assert isinstance(error, WhiskersError)
    finally:
        server.close()
        r.run(server.wait_closed())
        r.close()


# -- wiring -----------------------------------------------------------------------------------------------


def test_buildCollectors_starts_whiskers_from_its_settings_and_a_missing_list_is_one_tailFlick(
    fleetRepo, fleetTree, tmp_path, clock
):
    entities = tmp_path / "whiskers.yml"
    entities.write_text(CONFIG, encoding="utf-8")
    trail = ScentTrail(tmp_path / "b.db", clock=clock)
    settings = Settings(
        repoDir=fleetRepo,
        whiskersUrl="http://192.0.2.13:8123",
        whiskersToken=TOKEN,
        whiskersEntities=entities,
    )
    assert [c.name for c in buildCollectors(settings, trail, fleetTree, clock)] == ["whiskers"]
    missing = Settings(repoDir=fleetRepo, whiskersUrl="http://192.0.2.13:8123", whiskersToken=TOKEN,
                       whiskersEntities=tmp_path / "none.yml")  # fmt: skip
    assert buildCollectors(missing, trail, fleetTree, clock) == []
    [event] = trail.events(senses=["perch"])
    assert event.bodyLanguage is B.tailFlick and "whiskers is switched off" in event.title
    assert TOKEN not in event.title
    nothing = Settings(repoDir=fleetRepo)
    assert buildCollectors(nothing, trail, fleetTree, clock) == []
    trail.close()


def test_the_overview_shows_the_home_card_and_a_leak_in_needs_a_look(fleetRepo, fleetTree, tmp_path, clock):
    from perch.windowsill.app import createApp

    trail = ScentTrail(tmp_path / "p.db", clock=clock)
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "p.db")

    class Stub:
        name = "whiskers"
        rhythm = module.Rhythm(every=30)

        async def cycle(self):
            return None

        async def aclose(self):
            return None

    trail.setState("collector:whiskers", B.slowBlink, title="on time", seenAt=clock())
    trail.setState(
        "whiskers:binary_sensor.kitchen_leak", B.hiss, title="Kitchen leak sensor: wet",
        detail={"name": "Kitchen leak sensor", "word": "wet", "state": "on", "level": "hiss"},
    )  # fmt: skip
    trail.setState(
        "whiskers:binary_sensor.front_door", B.slowBlink, title="Front door: closed",
        detail={"name": "Front door", "word": "closed", "state": "off", "level": "slowBlink"},
    )  # fmt: skip
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[Stub()])
    with TestClient(app) as c:
        page = c.get("/").text
        assert 'id="whiskers"' in page and "2 sensors watched" in page
        assert "Kitchen leak sensor" in page and "wet" in page
        assert "Everything on the list is in its usual state" not in page
    off = ScentTrail(tmp_path / "q.db", clock=clock)
    plain = Settings(repoDir=fleetRepo, trailDb=tmp_path / "q.db")
    bare = createApp(plain, trail=off, tree=fleetTree, clock=clock, collectors=[])
    with TestClient(bare) as c:
        assert "whiskers isn't watching" in c.get("/").text
    trail.close()
    off.close()
