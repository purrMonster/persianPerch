"""The pages with live state: purr and the collector runner write scentTrail through a fake
Komodo, windowsill renders it. Covers what a person reads (the attention list, node vitals,
a container's state, how stale purr is) and what must never leak or break."""

import html as htmllib
import re

import pytest
from fastapi.testclient import TestClient
from world import World

from perch.collectors import Runner
from perch.scentTrail import ScentTrail
from perch.settings import Settings
from perch.windowsill.app import createApp


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


def page(client, url: str) -> str:
    """A page's HTML with entities decoded, so copy with an apostrophe compares as written."""
    return htmllib.unescape(client.get(url).text)


def withoutReadme(html: str) -> str:
    """The page without the fleet's own README, which perch quotes but doesn't write."""
    return re.sub(r'<pre class="readme">.*?</pre>', "", html, flags=re.S)


# -- a quiet fleet ------------------------------------------------------------------------------


def test_a_healthy_overview_says_so_and_shows_every_nodes_vitals(live):
    live.look(3)
    html = page(live, "/")
    assert "Nothing needs a look." in html and "Needs a look" not in html
    assert "fleet: slowBlink" in html
    assert "purr 30 s ago" in html  # the header pill: when purr last looked
    assert "purr looked 30 s ago" in html
    assert html.count('role="group" aria-label="grinder vitals"') == 1
    assert "20 %" in html and "40 %" in html and "50 %" in html  # cpu, ram, disk from the fake
    assert "12/12" in html  # grinder's apps up
    assert 'class="note muted small"' not in html and "blindnote" not in html  # nothing on the page is grey


def test_the_vitals_bars_are_shape_only_and_the_number_is_the_information(live):
    live.look(2)
    assert '<div class="bar" aria-hidden="true"><b style="width:20%"></b></div>' in page(live, "/")
    live.w.fake.vitals("cellar", disk=91.0)
    live.look(1)
    assert '<div class="bar bl-tailFlick" aria-hidden="true"><b style="width:91%"></b></div>' in page(live, "/")


# -- trouble -----------------------------------------------------------------------------------------


def test_an_exited_app_is_the_first_thing_on_the_overview(live):
    live.look(2)
    live.w.fake.exit("grinder", "n8n", 137)
    live.look(2)
    html = page(live, "/")
    assert "fleet: hiss" in html and "Needs a look" in html
    assert 'class="card attention bl-hiss"' in html
    assert 'href="/tree/grinder/n8n"' in html
    assert html.count("exited (code 137: killed, often out of memory)") >= 2  # the list and grinder's own card
    assert "since 30 s" in html
    assert "11/12" in html  # grinder: one of twelve apps is down
    assert "Nothing needs a look" not in html


def test_the_app_page_lists_its_containers_with_their_state(live):
    live.look(2)
    live.w.fake.exit("grinder", "n8n", 137)
    live.look(2)
    html = page(live, "/tree/grinder/n8n")
    assert "hiss for 30 s" in html  # the header badge: since when
    assert "exited (137)" in html  # the container's own state, in words
    assert "example/n8n:1" in html
    assert "exited (code 137: killed, often out of memory)" in html  # the one line about what is off
    assert "Seen by purr 30 s ago" in html
    assert "n8n exited (code 137" in html  # and it is on this app's own scentTrail


def test_a_healthy_app_page_shows_up_time_and_health(live):
    live.look(2)
    html = page(live, "/tree/grinder/n8n")
    assert "healthy" in html and "2 d" in html  # the fake's containers have been up two days
    assert "Needs a look" not in html


def test_a_missing_container_is_a_row_not_a_silent_gap(live):
    live.look(2)
    live.w.fake.remove("grinder", "karakeep-chrome")
    live.look(2)
    html = page(live, "/tree/grinder/karakeep")
    assert "karakeep-chrome not found on grinder" in html  # the app's one line about what is off
    assert re.search(r'karakeep-chrome</td><td><span class="badge bl-hiss"[^>]*><i[^>]*>!</i>missing<', html)


def test_a_node_page_has_vitals_and_other_containers(live):
    live.w.fake.add("grinder", "stray-test", project=None)
    live.look(3)
    html = page(live, "/tree/grinder")
    assert "Vitals" in html and "6.4 of 16.0 GB" in html  # 40 % of the fake's 16 GB
    assert "250.0 of 500.0 GB" in html and "2.3.2" in html
    assert "Other containers" in html and "stray-test" in html and "don't count toward the node" in html
    assert "karakeep" in html and "healthy" in html  # live state per app in the apps table


def test_a_sleeping_node_says_so_instead_of_showing_a_hiss(live):
    live.look(2)
    live.w.fake.nodeDown("roastery")
    live.look(3)
    node = page(live, "/tree/roastery")
    assert "asleep, as expected (wakes 01:25)" in node and "Vitals return when it wakes" in node
    overview = page(live, "/")
    assert "fleet: slowBlink" in overview and "asleep, as expected" in overview and "Needs a look" not in overview


# -- when purr can't see ------------------------------------------------------------------------------


def test_purr_that_stopped_answering_is_late_and_the_page_says_how_late(live):
    live.look(2)
    live.w.fake.komodoDown = True
    live.look(6)
    html = page(live, "/")
    assert "purr is late: no successful cycle for" in html
    assert re.search(r"purr late, \d+ (s|min) ago", html)  # the pill: severity in words
    assert "apps unknown: purr can't see them." in html
    assert "fleet: tailFlick" in html or "fleet: unknown" in html
    attention = html.split("Needs a look")[1].split("</section>")[0]
    assert "grinder/n8n" not in attention  # no false blame on any app


def test_purr_not_configured_is_said_plainly(fleetRepo, fleetTree, tmp_path, clock):
    cfg = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db")
    trail = ScentTrail(cfg.trailDb, clock=clock)
    with TestClient(createApp(cfg, trail=trail, tree=fleetTree, clock=clock, collectors=[])) as client:
        html = page(client, "/")
        assert "purr off" in html and "purr isn't watching yet" in html
        assert "apps unknown: purr isn't configured (set PERCH_PURR_URL)." in html
        assert "Nothing needs a look" not in html  # it can't say that when it can't see
        assert "no data yet" in html
        assert "purr hasn't seen this app's containers yet" in page(client, "/tree/grinder/n8n")
    trail.close()


# -- what must never break ------------------------------------------------------------------------------


def test_names_from_komodo_are_escaped(live):
    live.w.fake.add("grinder", "<script>alert(1)</script>", project=None)
    live.look(3)
    for url in ("/tree/grinder", "/"):
        assert "<script>alert(1)</script>" not in live.get(url).text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in live.get("/tree/grinder").text


@pytest.mark.parametrize(
    "url", ["/", "/tree", "/tree/grinder", "/tree/grinder/n8n", "/tree/roastery", "/trail", "/groom"]
)
def test_no_em_dashes_in_perchs_own_copy(live, url):
    live.look(2)
    live.w.fake.exit("grinder", "n8n")
    live.w.fake.nodeDown("roastery")
    live.look(3)
    html = withoutReadme(live.get(url).text)
    assert "—" not in html and "–" not in html


def test_pages_show_no_secret_from_komodo_settings(live):
    live.look(3)
    for url in ("/", "/tree/grinder", "/healthz"):
        body = live.get(url).text
        assert "K-fake-key-for-tests" not in body and "S-fake-secret-for-tests" not in body
