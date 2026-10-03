"""The live scentTrail (M5, ADR 0011) and the M5 gate: htmx-ext-sse is the pinned file, the stream carries new
events through the page's own filters, says a new hiss once, keeps alive and reconnects without listing a row twice;
and a dropped file and a door event, both really sent, reach an open trail within 5 seconds."""

import hashlib
import html
import re
import threading
import time
from datetime import UTC, datetime
from pathlib import Path

import pytest
from haFake import TOKEN, HAFake
from liveServer import LiveServer, OtherLoop, Stream

from kitten.kitten import Kitten, KittenConfig
from kitten.pounce import PollSource, Pounce, Pouncer, Watch
from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import ScentTrail
from perch.senses.whiskers import Whiskers, parseConfig
from perch.settings import Settings
from perch.windowsill import app as appModule
from perch.windowsill.app import createApp

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "perch" / "windowsill" / "static" / "vendor"
SSE = VENDOR / "htmx-ext-sse-2.2.4.min.js"
SSE_SHA256 = "98a46496de0c3605fbffdce9167ba427bdd9553184f83f149c261891a92c0136"
SSE_BYTES = 2853
TOKENS = {"cellar": "fake-token-cellar-not-real"}
DOOR = """
entities:
  binary_sensor.front_door:
    name: Front door
    states: {"on": earTwitch}
    words: {"on": open, "off": closed}
"""
FILE_ROW = "settings changed: pounce.env appeared"
DOOR_ROW = "Front door: open"


@pytest.fixture
def perch(fleetRepo, fleetTree, tmp_path):
    """A real perch on a loopback port with nothing running in it but the stream."""
    trail = ScentTrail(tmp_path / "s.db", clock=lambda: datetime.now(UTC))
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "s.db", kittenTokens=TOKENS)
    app = createApp(settings, trail=trail, tree=fleetTree, collectors=[])
    app.state.streamPoll = 0.05
    with LiveServer(app) as server:
        server.trail = trail
        yield server
    trail.close()


def streamPath(page: str) -> str:
    return html.unescape(re.search(r'sse-connect="([^"]+)"', page)[1])


def firstWith(stream: Stream, needle: str):
    for frame in stream.frames():
        if needle in frame.get("data", ""):
            return frame
    return None


# -- the vendored extension -------------------------------------------------------------------------------


def test_the_vendored_sse_extension_is_exactly_the_pinned_file():
    data = SSE.read_bytes()
    assert len(data) == SSE_BYTES
    assert hashlib.sha256(data).hexdigest() == SSE_SHA256


def test_its_licence_is_committed_beside_it_and_git_keeps_it_byte_exact():
    assert "BSD Zero Clause" in (VENDOR / "htmx-ext-sse-2.2.4.LICENSE").read_text(encoding="utf-8")
    assert "vendor/* -text" in (ROOT / ".gitattributes").read_text(encoding="utf-8")


def test_it_needs_no_eval_and_no_hx_on_so_adr_0003s_config_holds():
    source = SSE.read_text(encoding="utf-8")
    for word in ("eval(", "new Function", "hx-on", "setTimeout(\""):
        assert word not in source
    base = (ROOT / "perch" / "windowsill" / "templates" / "base.html").read_text(encoding="utf-8")
    assert '"allowEval":false' in base and '"allowScriptTags":false' in base


def test_perch_serves_it_byte_for_byte_and_only_the_trail_loads_it(perch):
    status, _ = perch.get("/static/vendor/htmx-ext-sse-2.2.4.min.js")
    assert status == 200
    assert "htmx-ext-sse-2.2.4.min.js" in perch.get("/trail")[1]
    for page in ("/", "/tree", "/groom"):
        assert "htmx-ext-sse" not in perch.get(page)[1]


def test_the_trail_page_connects_with_its_own_filters_and_has_a_no_script_fallback(perch):
    page = perch.get("/trail?sense=pounce&sense=whiskers&level=tailFlick&level=hiss")[1]
    path = streamPath(page)
    assert path.startswith("/trail/stream?")
    assert "sense=pounce" in path and "sense=whiskers" in path and "sense=purr" not in path
    assert "level=hiss" in path and "level=slowBlink" not in path and "after=" in path
    assert 'hx-ext="sse"' in page and 'sse-swap="new"' in page and 'class="needs-js"' in page
    assert "<noscript><style>.needs-js{display:none}</style></noscript>" in page
    assert "Nothing new yet." in page  # what is there with JavaScript off is only the list as of load


# -- the stream -------------------------------------------------------------------------------------------


def test_the_stream_is_an_event_stream_that_proxies_do_not_buffer(perch):
    stream = Stream(perch, "/trail/stream")
    try:
        assert stream.headers["content-type"].startswith("text/event-stream")
        assert "no-cache" in stream.headers["cache-control"] and stream.headers["x-accel-buffering"] == "no"
    finally:
        stream.close()


def test_a_new_event_reaches_an_open_stream_with_its_body_language_and_old_ones_do_not(perch):
    perch.trail.addEvent("purr", "node:sieve", B.tailFlick, "before the page was built")
    path = streamPath(perch.get("/trail")[1])
    stream = Stream(perch, path)
    try:
        time.sleep(0.3)
        perch.trail.addEvent("glare", "glare:x", B.earTwitch, "after the page was built")
        frame = firstWith(stream, "after the page was built")
    finally:
        stream.close()
    assert frame is not None and frame["event"] == "new"
    assert "before the page was built" not in frame["data"]
    assert 'class="row event bl-earTwitch"' in frame["data"]
    assert frame["id"].isdigit()
    assert "<div id=\"announce\"" not in frame["data"]  # an earTwitch is not announced


def test_the_stream_applies_the_filters_of_the_page(perch):
    path = streamPath(perch.get("/trail?sense=pounce")[1])
    stream = Stream(perch, path)
    try:
        time.sleep(0.3)
        perch.trail.addEvent("whiskers", "whiskers:a.b", B.earTwitch, "a door that the filters do not ask for")
        perch.trail.addEvent("pounce", "pounce:cellar//x", B.earTwitch, "a file that they do ask for")
        frame = firstWith(stream, "a file that they do ask for")
    finally:
        stream.close()
    assert frame is not None and "a door that the filters do not ask for" not in frame["data"]


def test_every_message_is_the_whole_list_so_a_reconnect_never_lists_a_row_twice(perch):
    path = streamPath(perch.get("/trail")[1])
    stream = Stream(perch, path)
    try:
        time.sleep(0.3)
        perch.trail.addEvent("glare", "glare:x", B.earTwitch, "first new one")
        firstWith(stream, "first new one")
    finally:
        stream.close()
    perch.trail.addEvent("glare", "glare:x", B.earTwitch, "second new one")
    again = Stream(perch, path, headers={"Last-Event-ID": "1"})  # a browser that lost the connection
    try:
        frame = firstWith(again, "second new one")
    finally:
        again.close()
    assert frame["data"].count("first new one") == 1 and frame["data"].count("second new one") == 1


def test_a_hiss_is_said_once_through_the_polite_live_region_and_nothing_else_is(perch):
    path = streamPath(perch.get("/trail")[1])
    stream = Stream(perch, path)
    try:
        time.sleep(0.3)
        perch.trail.addEvent("purr", "node:grinder", B.tailFlick, "a warning")
        perch.trail.addEvent("purr", "node:grinder", B.hiss, "grinder unreachable")
        frame = firstWith(stream, "grinder unreachable")
        assert frame is not None
        said = re.findall(r'<div id="announce" hx-swap-oob="innerHTML">(.*?)</div>', frame["data"])
        assert said == ["New hiss: grinder unreachable."]
        perch.trail.addEvent("purr", "node:grinder", B.earTwitch, "a notice")
        later = firstWith(stream, "a notice")
    finally:
        stream.close()
    assert 'id="announce"' not in later["data"]  # the hiss is not said again by the next message


def test_a_hiss_that_was_already_there_when_the_stream_reconnects_is_not_said_again(perch):
    path = streamPath(perch.get("/trail")[1])
    perch.trail.addEvent("purr", "node:grinder", B.hiss, "an old hiss")
    stream = Stream(perch, path)  # connects after it: the list shows it, nothing announces it
    try:
        frame = firstWith(stream, "an old hiss")
    finally:
        stream.close()
    assert frame is not None and 'id="announce"' not in frame["data"]


def test_a_keep_alive_comment_goes_out_when_nothing_happens(perch, monkeypatch):
    monkeypatch.setattr(appModule, "KEEP_ALIVE", 0.3)
    stream = Stream(perch, "/trail/stream", timeout=5)
    try:
        comments = []
        for frame in stream.frames():
            comments += frame["comment"]
            if "keep-alive" in comments:
                break
    finally:
        stream.close()
    assert "keep-alive" in comments


def test_more_than_fifty_new_events_are_a_count_not_a_wall(perch):
    path = streamPath(perch.get("/trail")[1])
    stream = Stream(perch, path)
    try:
        time.sleep(0.3)
        for i in range(60):
            perch.trail.addEvent("glare", f"glare:{i}", B.earTwitch, f"burst {i}")
        deadline = time.time() + 5
        frame = None
        while time.time() < deadline:
            frame = firstWith(stream, "burst 59")
            if frame:
                break
    finally:
        stream.close()
    assert frame is not None
    assert frame["data"].count('class="row event') == 50 and "and 10 more" in frame["data"]


def test_a_stream_that_is_open_does_not_hold_perch_up_at_shutdown(fleetRepo, fleetTree, tmp_path):
    trail = ScentTrail(tmp_path / "x.db")
    app = createApp(Settings(repoDir=fleetRepo, trailDb=tmp_path / "x.db"), trail=trail, tree=fleetTree, collectors=[])
    app.state.streamPoll = 0.05
    started = time.time()
    with LiveServer(app) as server:
        stream = Stream(server, "/trail/stream", timeout=10)
        time.sleep(0.3)
    stream.close()
    assert time.time() - started < 10
    trail.close()


def test_S7_the_stream_is_a_read(perch):
    from starlette.routing import Route

    routes = [r for r in perch.app.routes if isinstance(r, Route) and r.path == "/trail/stream"]
    assert len(routes) == 1 and routes[0].methods <= {"GET", "HEAD"}


# -- the M5 gate -----------------------------------------------------------------------------------------


def test_GATE_a_dropped_file_and_a_door_event_both_reach_an_open_trail_within_5_seconds(
    fleetRepo, fleetTree, tmp_path
):
    """kitten really watches a folder and really posts to perch; perch really talks WebSocket to a fake Home
    Assistant; a browser's stream is open on /trail. Nothing is stubbed between the file and the row."""
    ha = HAFake()
    other = OtherLoop()
    watched = tmp_path / "etc-purrbrews"
    watched.mkdir()
    (watched / "already-there.env").write_text("x")
    trail = ScentTrail(tmp_path / "g.db", clock=lambda: datetime.now(UTC))
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "g.db", kittenTokens=TOKENS)
    entities = parseConfig(DOOR)
    ha.set("binary_sensor.front_door", "off")
    other.run(ha.start())
    whiskers = Whiskers(ha.url, TOKEN, entities, trail, clock=lambda: datetime.now(UTC))
    app = createApp(settings, trail=trail, tree=fleetTree, collectors=[whiskers])
    app.state.streamPoll = 0.1
    watch = Watch(str(watched), "tailFlick", "settings changed")
    stop = threading.Event()
    runner = kitten = None
    try:
        with LiveServer(app) as perch:
            config = KittenConfig(
                perchUrl=perch.url + "/api/kitten", token=TOKENS["cellar"], node="cellar", stateDir="",
                pouncePaths=("none",),
            )  # fmt: skip
            kitten = Kitten(config, log=lambda text: None)
            kitten.pounce = Pounce(Pouncer([watch]), [PollSource(watch, every=0.2)], kitten.addEvents, interval=0.2)
            runner = threading.Thread(target=kitten.run, args=(stop, 30.0), daemon=True)
            runner.start()
            end = time.time() + 15  # whiskers connects and takes its snapshot; kitten takes its baseline
            while time.time() < end and "whiskers:binary_sensor.front_door" not in trail.states():
                time.sleep(0.1)
            assert "whiskers:binary_sensor.front_door" in trail.states(), "whiskers never connected"
            time.sleep(0.5)
            stream = Stream(perch, streamPath(perch.get("/trail")[1]), timeout=6)
            try:
                started = time.time()
                (watched / "pounce.env").write_text("SETTING=1")  # a file dropped into the watched folder
                other.run(ha.change("binary_sensor.front_door", "on"))  # a door event
                got: dict[str, float] = {}
                last = ""
                for frame in stream.frames():
                    last = frame.get("data", "")
                    for name, needle in (("file", FILE_ROW), ("door", DOOR_ROW)):
                        if needle in last and name not in got:
                            got[name] = time.time() - started
                    if len(got) == 2 or time.time() - started > 5.5:
                        break
            finally:
                stream.close()
            assert set(got) == {"file", "door"}, f"only {got} appeared in the open trail: {last[:300]}"
            assert max(got.values()) < 5.0, got
            print(f"\nGATE: door {got['door']:.2f} s, file {got['file']:.2f} s after they happened")
            shape = r'class="row event (bl-\w+)".*?<div class="title">(.*?)</div>'
            row = {title: level for level, title in re.findall(shape, last, re.S)}
            assert row[FILE_ROW] == "bl-tailFlick"
            assert row[DOOR_ROW] == "bl-earTwitch"
            page = perch.get("/trail")[1]  # and a reload lists both, in the list as of load
            assert FILE_ROW in page and DOOR_ROW in page
            events = {e.title: e for e in trail.events(senses=["pounce", "whiskers"])}
            assert events[FILE_ROW].bodyLanguage is B.tailFlick
            assert events[DOOR_ROW].bodyLanguage is B.earTwitch
            baseline = [e for e in trail.events(senses=["pounce"]) if "already-there" in e.title]
            assert baseline == []  # what was already in the folder is not news
    finally:
        stop.set()
        if runner:
            runner.join(10)
        if kitten:
            kitten.pounce.stop()
        other.run(ha.stop())
        other.close()
        trail.close()


def test_the_one_script_of_our_own_is_tiny_has_no_eval_and_only_the_trail_loads_it(perch):
    source = (ROOT / "perch" / "windowsill" / "static" / "trail-live.js").read_text(encoding="utf-8")
    assert len(source.splitlines()) <= 15
    for word in ("eval(", "new Function", "fetch(", "XMLHttpRequest", "innerHTML", "document.write"):
        assert word not in source
    assert "/static/trail-live.js" in perch.get("/trail")[1]
    for page in ("/", "/tree", "/groom"):
        assert "trail-live.js" not in perch.get(page)[1]
