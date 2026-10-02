"""The pages with live state: purr and the collector runner write scentTrail through a fake
Komodo, windowsill renders it. Covers what a person reads (the attention list, node vitals,
a container's state, how stale purr is) and what must never leak or break."""

import html as htmllib
import re
from datetime import UTC, datetime

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
    """A page's HTML with entities decoded and non-breaking spaces made plain, so copy compares as written."""
    return htmllib.unescape(client.get(url).text).replace(" ", " ")


def plain(html: str) -> str:
    """Just the words: tags removed, so a sentence with a code span in it reads as one."""
    return re.sub(r"<[^>]+>", "", html)


def withoutReadme(html: str) -> str:
    """The page without text quoted from the fleet repo (READMEs, backup lines), which perch doesn't write."""
    return re.sub(r'<pre class="readme"[^>]*>.*?</pre>', "", html, flags=re.S)


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


def test_a_number_and_its_unit_never_split_across_lines(live):
    live.look(3)
    raw = live.get("/").text
    assert "purr " not in raw  # only the age is glued: "30 s", not "purr 30"
    assert "30 s" in raw  # the pill and the header sentence


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
    assert "for 30 s" in html  # how long, in the same words as the app page's "hiss for ..."
    assert "11/12" in html  # grinder: one of twelve apps is down
    assert "Nothing needs a look" not in html
    assert '<ul class="attn" role="list">' in html and '<ul class="strip" role="list"' in html


def test_the_app_page_lists_its_containers_with_their_state(live):
    live.look(2)
    live.w.fake.exit("grinder", "n8n", 137)
    live.look(2)
    html = page(live, "/tree/grinder/n8n")
    assert "hiss for 30 s" in html  # the header badge: since when
    assert "exited (137)" in html  # the container's own state, in words
    assert "example/n8n:1" in html
    assert "exited (code 137: killed, often out of memory)" in html  # the one line about what is off
    assert "purr looked 30 s ago" in html
    assert "n8n exited (code 137" in html  # and it is on this app's own scentTrail
    assert '<th scope="row" class="mono">n8n</th>' in html  # a row header: the cells say whose they are


def test_a_badge_with_its_own_label_still_names_its_level_to_a_screen_reader(live):
    live.look(2)
    live.w.fake.exit("grinder", "n8n", 137)
    live.look(2)
    html = page(live, "/tree/grinder/n8n")
    assert '<span class="sr">hiss: </span>exited (137)' in html


def test_a_healthy_app_page_shows_up_time_and_health(live):
    live.look(2)
    html = page(live, "/tree/grinder/n8n")
    assert "healthy" in html and "2 d" in html  # the fake's containers have been up two days
    assert "Needs a look" not in html
    assert "Nothing has happened to this app since perch started watching." in html  # an empty trail says so


def test_a_missing_container_is_a_row_not_a_silent_gap(live):
    live.look(2)
    live.w.fake.remove("grinder", "karakeep-chrome")
    live.look(2)
    html = page(live, "/tree/grinder/karakeep")
    assert "karakeep-chrome not found on grinder" in html  # the app's one line about what is off
    assert re.search(
        r'karakeep-chrome</th><td><span class="badge bl-hiss"[^>]*><i[^>]*>!</i><span class="sr">hiss: </span>missing<',
        html,
    )


def test_a_node_page_has_vitals_and_other_containers(live):
    live.w.fake.add("grinder", "stray-test", project=None)
    live.look(3)
    html = page(live, "/tree/grinder")
    assert "Vitals" in html and "6.4 of 16.0 GB" in html  # 40 % of the fake's 16 GB
    assert "250.0 of 500.0 GB" in html and "2.3.2" in html and "Komodo Periphery" in html
    assert "Other containers" in html and "stray-test" in html and "don't count toward the node" in html
    assert "karakeep" in html and "healthy" in html  # live state per app in the apps table
    assert '<th scope="row" class="mono"><a href="/tree/grinder/n8n">n8n/</a></th>' in html


def test_a_sleeping_node_says_so_once_instead_of_showing_a_hiss(live):
    live.look(2)
    live.w.fake.nodeDown("roastery")
    live.look(3)
    node = page(live, "/tree/roastery")
    assert "Vitals return when it wakes." in node
    assert node.count("asleep, as expected (wakes 01:25)") == 1  # in the note, not repeated in the empty state
    overview = page(live, "/")
    assert "fleet: slowBlink" in overview and "asleep, as expected" in overview and "Needs a look" not in overview
    assert "2 apps, not visible while it sleeps" in overview  # not "2/2 apps up" for apps nobody can see


def test_a_node_purr_cannot_see_says_why_instead_of_a_bare_empty_state(live):
    live.look(2)
    live.w.fake.nodeDown("grinder")
    live.look(3)
    node = page(live, "/tree/grinder")
    assert "No vitals until purr can see grinder." in plain(node)
    assert node.count("grinder isn't answering") == 1  # the reason is the note's, not repeated


# -- when purr can't see ------------------------------------------------------------------------------


def test_purr_that_stopped_answering_is_late_and_the_page_says_how_late(live):
    live.look(2)
    live.w.fake.komodoDown = True
    live.look(6)
    html = page(live, "/")
    assert "purr is late: no successful cycle for" in html
    assert "Can't reach Komodo (connection refused or no route to it). Check PERCH_PURR_URL" in html  # and what to do
    assert re.search(r"purr late, \d+ (s|min) ago", html)  # the pill: severity in words
    assert "apps unknown: purr can't see them." in html
    assert "fleet: tailFlick" in html or "fleet: unknown" in html
    attention = html.split("Needs a look")[1].split("</section>")[0]
    assert "grinder/n8n" not in attention  # no false blame on any app


def test_purr_that_never_answered_is_not_called_starting(live):
    live.w.fake.komodoDown = True
    live.look(8)  # four minutes without one good look
    html = page(live, "/")
    assert "purr late, no answer yet" in html and "purr starting" not in html
    assert "purr hasn't had an answer from Komodo yet" in html


def test_one_unknown_app_is_not_called_apps(live):
    live.look(2)
    live.w.trail.setState("app:grinder/n8n", "unknown", title="no data")
    # a single app grey while purr is healthy: Komodo simply doesn't list it
    html = page(live, "/")
    assert "1 app unknown: Komodo doesn't list its containers." in html
    assert "1 apps" not in html


def test_purr_not_configured_is_said_plainly(fleetRepo, fleetTree, tmp_path, clock):
    cfg = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db")
    trail = ScentTrail(cfg.trailDb, clock=clock)
    with TestClient(createApp(cfg, trail=trail, tree=fleetTree, clock=clock, collectors=[])) as client:
        html = page(client, "/")
        assert "purr off" in html and "purr isn't watching yet" in html
        assert (
            "48 apps unknown: purr isn't configured (set PERCH_PURR_URL, PERCH_PURR_KEY and PERCH_PURR_SECRET)." in html
        )
        assert "Nothing needs a look" not in html  # it can't say that when it can't see
        assert "no data yet" in html and "apps, no live data" in html  # not "0/9 apps up"
        assert "purr hasn't seen this app's containers yet" in page(client, "/tree/grinder/n8n")
    trail.close()


# -- the greeting, the error pages, the privacy of the links -----------------------------------------


@pytest.mark.parametrize(
    ("hourIst", "greeting"),
    [
        (0, "Good evening"),
        (2, "Good evening"),
        (4, "Good evening"),
        (5, "Good morning"),
        (11, "Good morning"),
        (12, "Good afternoon"),
        (16, "Good afternoon"),
        (17, "Good evening"),
        (23, "Good evening"),
    ],
)
def test_the_greeting_fits_the_hour(live, hourIst, greeting):
    # Asia/Kolkata is UTC+5:30, so 00:15 IST is 18:45 UTC the day before
    utc = (hourIst * 60 + 15 - 330) % (24 * 60)
    live.w.clock.now = datetime(2026, 9, 29, utc // 60, utc % 60, tzinfo=UTC)
    assert f"{greeting}, barista" in page(live, "/")


def test_a_wrong_address_gets_a_page_not_json(live):
    response = live.get("/tree/nosuchnode")
    assert response.status_code == 404 and response.headers["content-type"].startswith("text/html")
    html = htmllib.unescape(response.text)
    assert "<h1>Not found</h1>" in html and "perch doesn't know a node with that name." in html
    assert 'href="/tree"' in html and 'href="/"' in html  # and a way on
    assert '"detail"' not in html
    assert "fleet: " in html  # the full page chrome, since the fleet is readable


def test_the_error_page_works_when_the_fleet_repo_cannot_be_read(fleetTree, tmp_path, clock):
    cfg = Settings(repoDir=tmp_path / "nothing", trailDb=tmp_path / "t.db")
    trail = ScentTrail(cfg.trailDb, clock=clock)
    with TestClient(createApp(cfg, trail=trail, clock=clock, collectors=[])) as client:
        response = client.get("/tree")
        html = htmllib.unescape(response.text)
        assert response.status_code == 503 and response.headers["content-type"].startswith("text/html")
        assert "perch can't read its source" in html and "PERCH_REPO_DIR" in html
        assert "can't read the fleet repo" in html  # the footer says it too
        health = client.get("/healthz")  # machines still get JSON
        assert health.status_code == 503 and health.json()["ok"] is False
    trail.close()


@pytest.mark.parametrize(
    "url", ["/", "/tree", "/tree/grinder", "/tree/grinder/n8n", "/tree/docs/README.md", "/trail", "/groom"]
)
def test_external_links_do_not_tell_github_where_the_dashboard_lives(live, url):
    live.look(1)
    assert '<meta name="referrer" content="same-origin">' in live.get(url).text


def test_events_are_lists_and_the_trail_groups_them_by_day(live):
    live.look(2)
    live.w.fake.exit("grinder", "n8n")
    live.look(2)
    html = live.get("/trail").text
    assert '<h2 class="dayhead">' in html and '<ul class="feed" role="list"><li class="row event' in html
    assert html.count("<ul") == html.count("</ul>")
    assert len(re.findall(r"<li[ >]", html)) == html.count("</li>")


# -- what must never break ------------------------------------------------------------------------------


def test_names_from_komodo_are_escaped(live):
    live.w.fake.add("grinder", "<script>alert(1)</script>", project=None)
    live.look(3)
    for url in ("/tree/grinder", "/"):
        assert "<script>alert(1)</script>" not in live.get(url).text
    assert "&lt;script&gt;alert(1)&lt;/script&gt;" in live.get("/tree/grinder").text


@pytest.mark.parametrize(
    "url",
    ["/", "/tree", "/tree/grinder", "/tree/grinder/n8n", "/tree/roastery", "/trail", "/groom", "/tree/nosuchnode"],
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
    live.w.fake.komodoDown = True
    live.look(6)  # the failure messages are on the page now: they must not carry the key or secret either
    for url in ("/", "/tree/grinder", "/healthz", "/trail", "/tree/nosuchnode"):
        body = live.get(url).text
        assert "K-fake-key-for-tests" not in body and "S-fake-secret-for-tests" not in body
