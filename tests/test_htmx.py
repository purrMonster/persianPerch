"""htmx 2.0.11, vendored (ADR 0003, 05 plan A12): the file is exactly the pinned one, perch serves
it itself, the overview, node and app pages poll their state regions every 30 s from GET
fragments, and a changed state is announced once, never every 30 s."""

import hashlib
import re
from pathlib import Path

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount
from world import World

from perch.collectors import Runner
from perch.settings import Settings
from perch.windowsill.app import createApp

ROOT = Path(__file__).resolve().parents[1]
VENDOR = ROOT / "perch" / "windowsill" / "static" / "vendor"
HTMX = VENDOR / "htmx-2.0.11.min.js"
HTMX_SHA256 = "d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717"
HTMX_BYTES = 52182
SCRIPT = '<script src="/static/vendor/htmx-2.0.11.min.js" defer></script>'

STATE_PAGES = {
    "/": "/live/overview",
    "/tree/grinder": "/live/node/grinder",
    "/tree/grinder/n8n": "/live/app/grinder/n8n",
}


@pytest.fixture
def live(fleetRepo, fleetTree, tmp_path, clock):
    """A client over a world where purr runs through the real collector runner."""
    w = World(fleetTree, tmp_path, clock)
    runner = Runner(w.trail, [w.purr], clock=clock)
    cfg = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db")
    app = createApp(cfg, trail=w.trail, tree=fleetTree, clock=clock, collectors=[])

    def look(n=1):
        for _ in range(n):
            w.loop.run_until_complete(runner.runOnce(w.purr))
            clock.advance(seconds=30)

    with TestClient(app) as client:
        client.w, client.look = w, look
        yield client
    w.close()


def seen(html: str) -> str:
    return re.search(r'<input type="hidden" id="seen" name="seen" value="([0-9a-f]+)">', html)[1]


def announcement(html: str) -> str | None:
    found = re.search(r'<div id="announce" hx-swap-oob="innerHTML">(.*?)</div>', html, re.S)
    return found[1].strip() if found else None


# -- the vendored file ------------------------------------------------------------------------


def test_the_vendored_htmx_is_exactly_the_pinned_file():
    data = HTMX.read_bytes()
    assert len(data) == HTMX_BYTES
    assert hashlib.sha256(data).hexdigest() == HTMX_SHA256


def test_its_licence_is_committed_beside_it():
    assert "Zero-Clause BSD" in (VENDOR / "htmx-2.0.11.LICENSE").read_text(encoding="utf-8")


def test_perch_serves_it_byte_for_byte(live):
    r = live.get("/static/vendor/htmx-2.0.11.min.js")
    assert r.status_code == 200 and r.content == HTMX.read_bytes()
    assert "javascript" in r.headers["content-type"]


def test_git_keeps_the_vendored_files_byte_exact():
    attributes = (ROOT / ".gitattributes").read_text(encoding="utf-8")
    assert "perch/windowsill/static/vendor/* -text" in attributes


# -- how pages use it -------------------------------------------------------------------------


@pytest.mark.parametrize("url", ["/", "/tree", "/tree/grinder", "/tree/grinder/n8n", "/groom", "/trail"])
def test_every_page_loads_htmx_from_perch_with_defer_and_never_a_cdn(live, url):
    html = live.get(url).text
    assert html.count(SCRIPT) == 1
    assert not re.search(r'<script[^>]+src="(?:https?:)?//', html)
    assert 'id="announce"' in html and 'aria-live="polite"' in html  # the live region exists before anything changes


def test_htmx_is_configured_for_a_read_only_watcher(live):
    config = re.search(r'<meta name="htmx-config" content=\'([^\']+)\'>', live.get("/").text)[1]
    for setting in ("includeIndicatorStyles", "allowEval", "allowScriptTags", "historyEnabled"):
        assert f'"{setting}":false' in config


@pytest.mark.parametrize(("url", "fragment"), STATE_PAGES.items())
def test_state_pages_poll_their_own_region_every_30s(live, url, fragment):
    html = live.get(url).text
    assert html.count("hx-trigger=") == 1  # one poller per page, not the body, not every card
    assert f'id="live" hx-get="{fragment}" hx-trigger="every 30s" hx-include="#seen" hx-swap="innerHTML"' in html
    assert re.search(r'<input type="hidden" id="seen" name="seen" value="[0-9a-f]+">', html)
    assert "hx-post" not in html and "hx-put" not in html and "hx-delete" not in html


@pytest.mark.parametrize("url", ["/tree", "/groom", "/trail", "/tree/docs/README.md"])
def test_pages_without_a_state_region_do_not_poll(live, url):
    assert "hx-trigger" not in live.get(url).text


def test_a_page_says_when_its_state_is_from_and_that_javascript_off_means_as_of_load(live):
    live.look(3)
    html = live.get("/").text
    assert re.search(r"State as of \d\d:\d\d:\d\d\. It refreshes every 30 s when JavaScript is on\.", html)


# -- the fragments ----------------------------------------------------------------------------


@pytest.mark.parametrize(("url", "fragment"), STATE_PAGES.items())
def test_a_fragment_is_the_region_and_the_header_bits_not_a_page(live, url, fragment):
    live.look(3)
    r = live.get(fragment)
    assert r.status_code == 200 and r.headers["content-type"].startswith("text/html")
    assert "<html" not in r.text and "<body" not in r.text and '<nav class="main"' not in r.text
    assert '<span id="fleet-badge" hx-swap-oob="true">' in r.text  # the header follows the state
    assert '<span id="purr-pill" class="pill hide-sm" translate="no"' in r.text and 'hx-swap-oob="true"' in r.text
    assert seen(live.get(url).text) == seen(r.text)  # the page and its fragment agree on what "unchanged" means


def test_the_overview_fragment_is_what_the_page_shows(live):
    live.look(3)
    page = live.get("/").text
    fragment = live.get("/live/overview").text
    for sentence in ("Nothing needs a look.", "12/12", 'aria-label="grinder vitals"'):
        assert sentence in page and sentence in fragment


def test_a_change_is_announced_once_and_never_again_while_nothing_changes(live):
    live.look(3)
    token = seen(live.get("/").text)
    assert announcement(live.get(f"/live/overview?seen={token}").text) is None  # nothing changed: silent
    for _ in range(3):  # a 30 s poll with nothing new says nothing, however many times it runs
        live.look(1)
        assert announcement(live.get(f"/live/overview?seen={token}").text) is None
    live.w.fake.exit("grinder", "n8n", 137)
    live.look(2)  # two looks: the hiss is confirmed
    changed = live.get(f"/live/overview?seen={token}")
    said = announcement(changed.text)
    assert said and "hiss" in said and "1 thing needs a look" in said
    newToken = seen(changed.text)
    assert newToken != token
    live.look(1)
    assert announcement(live.get(f"/live/overview?seen={newToken}").text) is None  # said once
    live.w.fake.start("grinder", "n8n")
    live.look(2)
    back = announcement(live.get(f"/live/overview?seen={newToken}").text)
    assert back and "slowBlink" in back and "Nothing needs a look" in back


def test_a_fragment_asked_without_a_token_is_silent(live):
    live.look(3)
    assert announcement(live.get("/live/overview").text) is None


def test_node_and_app_fragments_announce_their_own_change(live):
    live.look(3)
    node = seen(live.get("/tree/grinder").text)
    app = seen(live.get("/tree/grinder/n8n").text)
    live.w.fake.exit("grinder", "n8n", 137)
    live.look(2)
    assert "grinder is hiss" in announcement(live.get(f"/live/node/grinder?seen={node}").text)
    assert "grinder/n8n is hiss" in announcement(live.get(f"/live/app/grinder/n8n?seen={app}").text)


def test_the_header_pill_in_a_fragment_carries_the_new_age(live):
    live.look(3)
    first = live.get("/live/overview").text
    live.w.clock.advance(minutes=2)
    later = live.get("/live/overview").text
    assert "purr 30 s ago" in first.replace("\u00a0", " ") and "purr 2 min ago" in later.replace("\u00a0", " ")


def test_unknown_things_have_no_fragment(live):
    for url in ("/live/node/nosuchnode", "/live/app/grinder/nosuchapp", "/live/app/nosuchnode/x", "/live/nothing"):
        assert live.get(url).status_code == 404, url


def test_fragments_are_read_only_like_every_page(live):
    for route in live.app.routes:
        if not isinstance(route, Mount) and route.path.startswith("/live/"):
            assert set(route.methods) <= {"GET", "HEAD"}, route.path
    assert live.post("/live/overview").status_code == 405
