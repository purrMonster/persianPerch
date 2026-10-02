"""The grooming grid, the copies panel, and groom's bits on the overview and app pages."""

import html as htmllib
import re
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeClock
from fastapi.testclient import TestClient

from perch.scentTrail import ScentTrail
from perch.settings import Settings
from perch.windowsill.app import createApp

IST = ZoneInfo("Asia/Kolkata")
NODES = ["sieve", "percolator", "cellar", "mochaPot", "grinder"]
TOKENS = {n: f"fake-token-{n}-not-real" for n in NODES}


def at(hour, minute=0, day=29):
    return datetime(2026, 9, day, hour, minute, tzinfo=IST).astimezone(UTC)


def iso(moment):
    return moment.strftime("%Y-%m-%dT%H:%M:%SZ")


def record(node, job, start, minutes=20, result="success", tail=""):  # noqa: PLR0917
    return {
        "schema": 1,
        "job": job,
        "node": node,
        "unit": f"{job}.service",
        "start": iso(start),
        "end": iso(start + timedelta(minutes=minutes)),
        "result": result,
        "exitStatus": "0" if result == "success" else "1",
        "logTail": tail,
    }


@pytest.fixture
def groom(fleetRepo, fleetTree, tmp_path):
    clock = FakeClock(at(18, 0, day=28))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db", kittenTokens=TOKENS)
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[])
    with TestClient(app) as client:
        app.state.groom.step()  # perch starts watching the evening before

        def send(node, records=(), heartbeat=None):
            body = {"node": node, "records": list(records)}
            if heartbeat is not None:
                body["heartbeat"] = heartbeat
            r = client.post("/api/kitten", json=body, headers={"Authorization": f"Bearer {TOKENS[node]}"})
            assert r.status_code == 200, r.text

        def goodNight(skip=()):
            for node in NODES:
                if node not in skip:
                    send(node, [record(node, "nightly", at(1, 30) + timedelta(seconds=30), 22)], {"version": "0.1.0"})
            send(
                "cellar",
                [
                    record("cellar", "wake", at(1, 25), 1),
                    record("cellar", "store", at(2, 30), 6),
                    record("cellar", "drive", at(3, 30), 25),
                ],
                {"version": "0.1.0", "stamps": {"drive-sync.ok": int(at(3, 55).timestamp())}},
            )

        client.kitten, client.goodNight, client.clock, client.trail = send, goodNight, clock, trail
        yield client
    trail.close()


def page(client, url):
    return htmllib.unescape(client.get(url).text)


def copyRow(html, name):
    """The <li> of the copies panel that names `name`."""
    return re.search(r"<li[^>]*>(?:(?!</li>).)*" + name + r"(?:(?!</li>).)*</li>", html, re.S)[0]


def plain(html):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", html))


def cells(html):
    """{(node, job, day): level} for every dot in the grid."""
    found = {}
    for href, level in re.findall(
        r'<a class="cell" href="[^"]*cell=([^"#]+)[^>]*><span class="dot big bl-(\w+)"', html
    ):
        key, _, day = href.partition("@")
        node, _, job = key.partition("/")
        found[(node, job, day)] = level
    return found


# -- the grid -------------------------------------------------------------------------------------


def test_with_nothing_watched_the_page_says_why_and_never_shows_a_false_hiss(fleetRepo, fleetTree, tmp_path):
    clock = FakeClock(at(8, 0))
    app = createApp(Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db"), tree=fleetTree, clock=clock, collectors=[])
    with TestClient(app) as c:
        html = page(c, "/groom")
        assert "Not watched yet:" in html and "no kitten token" in html
        assert 'class="cell"' not in html and "bl-hiss" not in html.split("<footer")[0].split("</header>")[1]
        assert "No run to show yet" in html


def test_a_good_night_is_all_slowBlink_and_the_page_says_so(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight()
    html = page(groom, "/groom")
    found = cells(html)
    today = {k: v for k, v in found.items() if k[2] == "2026-09-29"}
    assert len(today) == 8 and set(today.values()) == {"slowBlink"}  # 5 nightly + wake, store, drive
    assert "last night: 5 of 5" in html and "No night in this range needed a look." in html


def test_the_missing_record_is_the_only_red_dot_and_the_page_says_which(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight(skip=("grinder",))
    html = page(groom, "/groom")
    red = {k for k, v in cells(html).items() if v == "hiss"}
    assert red == {("grinder", "nightly", "2026-09-29")}
    assert "29 Sep: grinder nightly backup missing: no record 3 h after 01:30" in plain(html)
    assert "last night: 4 of 5" in html


def test_the_grid_is_accessible_each_dot_names_its_job_night_and_state(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight(skip=("grinder",))
    html = page(groom, "/groom")
    assert 'aria-label="hiss: grinder nightly backup, 29 Sep, missing: no record 3 h after 01:30"' in html
    assert "<caption" in html and 'scope="col"' in html and 'scope="row"' in html


def test_a_judged_cell_is_a_link_so_the_run_can_be_opened(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight(skip=("grinder",))
    assert "grinder/nightly@2026-09-29" in page(groom, "/groom")


def test_a_selected_run_shows_its_details_and_its_log_escaped(groom):
    groom.clock.now = at(2, 0)
    groom.kitten(
        "sieve", [record("sieve", "nightly", at(1, 30), result="exit-code", tail="restic: <b>unreachable</b>")]
    )
    html = groom.get("/groom?cell=sieve/nightly@2026-09-29").text
    assert "failed (exit-code, exit 1)" in htmllib.unescape(html)
    assert "restic: &lt;b&gt;unreachable&lt;/b&gt;" in html and "<b>unreachable</b>" not in html
    assert 'aria-current="true"' in html and "log tail" in html
    assert "01:30:00" in html and 'exit <span class="mono">1</span>' in html


def test_a_nights_choice_changes_the_columns_and_a_bad_one_is_14(groom):
    groom.clock.now = at(8, 0)
    groom.goodNight()
    for query, columns in (("?nights=7", 7), ("?nights=30", 30), ("?nights=999", 14), ("?nights=x", 14), ("", 14)):
        r = groom.get("/groom" + query)
        assert r.status_code == 200, query
        assert len(re.findall(r'<th scope="col"', r.text.split("<tbody")[0])) == columns + 1, query


def test_a_bad_cell_parameter_is_ignored_not_an_error(groom):
    groom.clock.now = at(8, 0)
    for cell in ("x", "a/b@c", "grinder/nightly@9999-01-01", "../../etc@2026-09-29", "@", "%00"):
        assert groom.get("/groom", params={"cell": cell}).status_code == 200, cell


# -- the copies panel -------------------------------------------------------------------------


def test_the_copies_panel_reads_the_drive_age_from_drive_sync_ok(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight()
    html = page(groom, "/groom")
    assert "Google Drive copy" in html and "synced 03:55, 35 min old" in html
    assert "Dump store" in html and "Morning check" in html and "Restore check" in html
    assert "never run, due on the 1st" in html  # nothing to judge before perch had watched a 1st


def test_a_drive_copy_that_has_gone_stale_is_a_warning_then_a_hiss(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight()
    old = int((at(3, 55) - timedelta(days=2)).timestamp())
    groom.kitten("cellar", [], {"version": "0.1.0", "stamps": {"drive-sync.ok": old}})
    groom.clock.now = at(3, 30) + timedelta(hours=3)  # 3 h after its slot: past the 2 h late limit
    row = copyRow(page(groom, "/groom"), "Google Drive copy")
    assert "last sync 2 d" in row and 'aria-label="tailFlick"' in row
    groom.clock.now = at(3, 30) + timedelta(hours=9)
    row = copyRow(page(groom, "/groom"), "Google Drive copy")
    assert 'aria-label="hiss"' in row


def test_without_a_stamp_the_drive_copy_falls_back_to_cellars_drive_record_or_says_unknown(groom):
    groom.clock.now = at(5, 0)
    assert "due at 03:30, not seen yet" in copyRow(page(groom, "/groom"), "Google Drive copy")
    groom.kitten("cellar", [record("cellar", "drive", at(3, 30), 25)], {"version": "0.1.0"})
    assert "ok, 25 min" in copyRow(page(groom, "/groom"), "Google Drive copy")


# -- elsewhere ----------------------------------------------------------------------------------


def test_the_overview_says_how_last_night_went_and_what_didnt_run(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight(skip=("grinder",))
    html = page(groom, "/")
    assert "last night: 4 of 5" in html and "nightly backup: missing: no record 3 h after 01:30" in html
    assert "Needs a look" in html and "fleet: hiss" in html
    assert html.count("Nothing to judge yet") == 0


def test_the_overview_before_any_kitten_has_a_token_says_what_to_set(fleetRepo, fleetTree, tmp_path):
    app = createApp(
        Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db"), tree=fleetTree, clock=FakeClock(at(8, 0)), collectors=[]
    )
    with TestClient(app) as c:
        assert "Nothing to judge yet" in c.get("/").text


def test_an_app_with_a_backup_file_shows_its_nodes_nightly_and_one_without_says_so(groom):
    groom.clock.now = at(4, 30)
    groom.goodNight(skip=("grinder",))
    html = page(groom, "/tree/grinder/n8n")
    assert "missing: no record 3 h after 01:30" in html and "the whole node's nightly" in html
    ok = page(groom, "/tree/percolator/vaultwarden")
    assert "ok, 22 min" in ok


def test_a_node_whose_backup_failed_hisses_on_its_node_page_and_the_fleet_badge(groom):
    groom.clock.now = at(2, 0)
    groom.kitten("mochaPot", [record("mochaPot", "nightly", at(1, 30), result="exit-code")])
    node = page(groom, "/tree/mochaPot")
    assert "failed (exit-code, exit 1)" in node and "fleet: hiss" in page(groom, "/")
    assert 'href="/groom"' in page(groom, "/")


def test_the_nav_item_for_groom_is_active_on_its_page(groom):
    assert re.search(r'<a href="/groom"[^>]*class="on"[^>]*aria-current="page"', groom.get("/groom").text)
