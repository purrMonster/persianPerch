"""Acknowledge (05 plan A11) and test S9: the page route with its CSRF protection, the push route with its
signed single-use token, and the Alerts card. Writes only perch's own database; nothing here leaves it."""

import re

import pytest
from conftest import FakeClock
from fastapi.testclient import TestClient
from world import IST

from perch import ack
from perch.bodyLanguage import BodyLanguage as B
from perch.litters import Litters
from perch.meow import Meow
from perch.scentTrail import ScentTrail
from perch.settings import Settings
from perch.windowsill.app import createApp

SECRET = "fake-ack-secret-not-real-0123456789abcdef"
SAME = {"Origin": "http://testserver", "Sec-Fetch-Site": "same-origin"}


@pytest.fixture
def rig(fleetRepo, fleetTree, tmp_path):
    from datetime import UTC, datetime

    clock = FakeClock(datetime(2026, 9, 29, 7, 0, tzinfo=IST).astimezone(UTC))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db", ackSecret=SECRET)
    meow = Meow(trail, fleetTree, clock=clock, tz=IST, ackSecret=SECRET)
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[], meow=meow)
    store = Litters(trail)
    with TestClient(app) as client:
        client.clock, client.trail, client.store = clock, trail, store
        yield client
    trail.close()


def hiss(rig, key="app:grinder/n8n", title="n8n exited"):
    return rig.store.create(key, "state", B.hiss, f"{key.partition(':')[2]}: {title}", 1, now=rig.clock())


def form(rig, litter):
    """The Acknowledge form the overview shows for a litter, as a browser would submit it."""
    html = rig.get("/").text
    pattern = rf'<form class="ack"[^>]*action="/ack/{re.escape(litter.litterId)}".*?name="csrf" value="([^"]+)"'
    match = re.search(pattern, html, re.S)
    assert match, "the overview has no Acknowledge form for this litter"
    return {"csrf": match[1]}


def acked(rig, litter):
    return rig.store.get(litter.litterId).ackedAt is not None


def events(rig):
    return [e.title for e in rig.trail.events(limit=100) if e.title.startswith("acknowledged")]


# -- the page --------------------------------------------------------------------------------------


def test_the_overview_shows_an_acknowledge_button_for_a_hiss(rig):
    lt = hiss(rig)
    html = rig.get("/").text
    assert 'id="alerts"' in html and "Acknowledge</button>" in html
    assert lt.litterId in html and "not pushed yet" in html
    assert "hx-post=" in html and "hx-on" not in html  # ADR 0003: no hx-on, no eval


def test_the_page_acknowledges_with_its_csrf_token_and_a_same_origin_post(rig):
    lt = hiss(rig)
    r = rig.post(f"/ack/{lt.litterId}", data=form(rig, lt), headers=SAME, follow_redirects=False)
    assert r.status_code == 303 and r.headers["location"] == "/"
    found = rig.store.get(lt.litterId)
    assert found.ackedAt is not None and found.ackedVia == "from the page"
    assert events(rig) == ["acknowledged from the page: grinder/n8n: n8n exited"]
    assert "acknowledged" in rig.get("/").text and "Acknowledge</button>" not in rig.get("/").text


def test_with_htmx_the_answer_is_one_line_not_a_page(rig):
    lt = hiss(rig)
    r = rig.post(f"/ack/{lt.litterId}", data=form(rig, lt), headers={**SAME, "HX-Request": "true"})
    assert r.status_code == 200 and 'hx-swap-oob="innerHTML"' in r.text
    assert r.text.startswith('<span class="acked small" tabindex="-1" autofocus>Acknowledged at 07:00')


def test_acknowledging_twice_is_harmless_and_said_once(rig):
    lt = hiss(rig)
    data = form(rig, lt)
    assert rig.post(f"/ack/{lt.litterId}", data=data, headers=SAME, follow_redirects=False).status_code == 303
    first = rig.store.get(lt.litterId).ackedAt
    rig.clock.advance(minutes=5)
    assert rig.post(f"/ack/{lt.litterId}", data=data, headers=SAME, follow_redirects=False).status_code == 303
    assert rig.store.get(lt.litterId).ackedAt == first and len(events(rig)) == 1


def test_S9_a_page_ack_without_its_csrf_token_is_403_and_changes_nothing(rig):
    lt = hiss(rig)
    for data in ({}, {"csrf": ""}, {"csrf": "garbage"}, {"other": "x"}):
        r = rig.post(f"/ack/{lt.litterId}", data=data, headers=SAME)
        assert r.status_code == 403, data
    assert not acked(rig, lt) and events(rig) == []


def test_S9_a_csrf_token_for_another_litter_or_an_expired_one_is_403(rig):
    a, b = hiss(rig), hiss(rig, "app:grinder/traccar", "down")
    token = form(rig, a)
    assert rig.post(f"/ack/{b.litterId}", data=token, headers=SAME).status_code == 403
    assert not acked(rig, b)
    rig.clock.advance(hours=7)
    assert rig.post(f"/ack/{a.litterId}", data=token, headers=SAME).status_code == 403
    assert not acked(rig, a)


def test_S9_a_forged_csrf_token_signed_with_another_key_is_403(rig):
    lt = hiss(rig)
    forged = ack.csrfMint("fake-some-other-key-not-real-0123456789", lt.litterId, rig.clock())
    assert rig.post(f"/ack/{lt.litterId}", data={"csrf": forged}, headers=SAME).status_code == 403
    assert not acked(rig, lt)


@pytest.mark.parametrize(
    "headers",
    [
        {"Origin": "https://evil.example.home.arpa", "Sec-Fetch-Site": "same-origin"},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "cross-site"},
        {"Origin": "http://testserver", "Sec-Fetch-Site": "same-site"},
        {"Sec-Fetch-Site": "none"},
        {"Origin": "null"},
        {"Origin": "https://evil.example.home.arpa"},
        {},  # neither header: can't prove where it came from
    ],
    ids=["other-origin", "cross-site", "same-site", "none", "null-origin", "origin-only-wrong", "no-headers"],
)
def test_S9_a_post_that_is_not_provably_same_origin_is_403_even_with_a_valid_token(rig, headers):
    lt = hiss(rig)
    r = rig.post(f"/ack/{lt.litterId}", data=form(rig, lt), headers=headers)
    assert r.status_code == 403
    assert not acked(rig, lt)
    assert "Not allowed" in r.text and "text/html" in r.headers["content-type"]  # an error is a page (docs/06 rule 19)


def test_an_origin_alone_that_matches_is_enough_and_a_sec_fetch_site_alone_too(rig):
    lt = hiss(rig)
    data = form(rig, lt)
    assert rig.post(f"/ack/{lt.litterId}", data=data, headers={"Origin": "http://testserver"}).status_code == 200
    other = hiss(rig, "app:grinder/traccar", "down")
    data = form(rig, other)
    r = rig.post(f"/ack/{other.litterId}", data=data, headers={"Sec-Fetch-Site": "same-origin"})
    assert r.status_code == 200


def test_a_litter_that_is_gone_is_a_404_page(rig):
    lt = hiss(rig)
    data = form(rig, lt)
    rig.store.update(lt.litterId, closedAt=rig.clock())
    assert rig.post(f"/ack/{lt.litterId}", data=data, headers=SAME).status_code == 404
    assert rig.post("/ack/nothing.here@1", data=data, headers=SAME).status_code == 403  # a token for no litter


def test_the_get_of_an_ack_route_is_not_allowed(rig):
    lt = hiss(rig)
    assert rig.get(f"/ack/{lt.litterId}").status_code == 405
    assert rig.get("/ack/t/anything").status_code == 405


# -- the push ---------------------------------------------------------------------------------------


def token(rig, lt, life=ack.TOKEN_LIFE):
    return ack.mint(SECRET, lt.litterId, rig.clock(), life)


def test_a_push_token_acknowledges_once(rig):
    lt = hiss(rig)
    t = token(rig, lt)
    r = rig.post(f"/ack/t/{t}")
    assert r.status_code == 200 and r.json() == {"ok": True}
    assert rig.store.get(lt.litterId).ackedVia == "from the push"
    assert events(rig) == ["acknowledged from the push: grinder/n8n: n8n exited"]
    assert t not in r.text and t not in repr(rig.trail.events(limit=50))


def test_S9_a_replayed_token_is_403_and_changes_nothing(rig):
    lt = hiss(rig)
    t = token(rig, lt)
    assert rig.post(f"/ack/t/{t}").status_code == 200
    rig.store.update(lt.litterId, ackedAt=None, ackedVia=None)  # as if it had never been acknowledged
    assert rig.post(f"/ack/t/{t}").status_code == 403
    assert not acked(rig, lt)


def test_S9_an_expired_token_is_403_and_changes_nothing(rig):
    lt = hiss(rig)
    t = token(rig, lt)
    rig.clock.advance(hours=24, seconds=1)
    assert rig.post(f"/ack/t/{t}").status_code == 403
    assert not acked(rig, lt)


def test_S9_a_tampered_token_is_403_and_changes_nothing(rig):
    lt = hiss(rig)
    head, expires, sig = token(rig, lt).split(".")
    longer = f"{head}.{int(expires) + 3600}.{sig}"
    reversed_ = f"{head}.{expires}.{sig[::-1]}"
    renamed = f"{head}x.{expires}.{sig}"
    for bad in (longer, reversed_, renamed, "a.b.c"):
        assert rig.post(f"/ack/t/{bad}").status_code == 403, bad
    assert not acked(rig, lt) and rig.trail.fetch("SELECT * FROM ackSpent") == []


def test_S9_a_token_for_another_litter_only_ever_touches_that_litter(rig):
    a, b = hiss(rig), hiss(rig, "app:grinder/traccar", "down")
    assert rig.post(f"/ack/t/{token(rig, a)}").status_code == 200
    assert acked(rig, a) and not acked(rig, b)
    # a token for a litter that has cleared, or never existed, does nothing
    rig.store.update(b.litterId, closedAt=rig.clock())
    assert rig.post(f"/ack/t/{token(rig, b)}").status_code == 403
    ghost = ack.mint(SECRET, "app.nowhere.none@20260101T000000Z", rig.clock())
    assert rig.post(f"/ack/t/{ghost}").status_code == 403
    assert not acked(rig, b)


def test_a_token_dies_with_its_litter(rig):
    lt = hiss(rig)
    t = token(rig, lt)
    rig.store.update(lt.litterId, closedAt=rig.clock())
    assert rig.post(f"/ack/t/{t}").status_code == 403


def test_a_token_signed_with_another_secret_is_403(rig):
    lt = hiss(rig)
    other = ack.mint("fake-some-other-key-not-real-0123456789", lt.litterId, rig.clock())
    assert rig.post(f"/ack/t/{other}").status_code == 403 and not acked(rig, lt)


def test_the_push_route_is_limited_to_10_a_minute_whatever_the_token(rig):
    lt = hiss(rig)
    codes = [rig.post(f"/ack/t/bad{i}").status_code for i in range(12)]
    assert codes[:10] == [403] * 10 and codes[10:] == [429, 429]
    assert rig.post(f"/ack/t/{token(rig, lt)}").status_code == 429  # even a good one waits its turn
    rig.clock.advance(seconds=61)
    assert rig.post(f"/ack/t/{token(rig, lt)}").status_code == 200


def test_without_a_secret_the_push_route_refuses_everything(fleetRepo, fleetTree, tmp_path, clock):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db")
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[])
    lt = Litters(trail).create("app:grinder/n8n", "state", B.hiss, "n8n down", 1, now=clock())
    with TestClient(app) as c:
        t = ack.mint(SECRET, lt.litterId, clock())
        assert c.post(f"/ack/t/{t}").status_code == 403
    assert Litters(trail).get(lt.litterId).ackedAt is None
    trail.close()


# -- the card -------------------------------------------------------------------------------------------


def test_the_alerts_card_says_what_meow_is_holding_and_what_waits_for_the_digest(rig):
    held = hiss(rig)
    rig.store.update(held.litterId, heldAt=rig.clock())
    now = rig.clock()
    waiting = rig.store.create("node:cellar", "state", B.tailFlick, "cellar: disk 88 % full", 1, now=now, digest=True)
    ear = rig.store.create("app:cellar/scrutiny", "state", B.earTwitch, "starting", 1, now=now, digest=True)
    html = rig.get("/").text
    assert "held back by the rate limit; it goes out as the limit allows" in html
    assert "waiting for the 07:30 digest (quiet hours)" in html
    assert "1 alert is held back" in html and "2 notices wait for the morning digest" in html
    assert ear.litterId not in html and waiting.litterId in html  # an earTwitch is never listed or acknowledged
    assert "Quiet hours are 23:00 to 07:00; hiss ignores them." in html


def test_the_card_without_a_meow_that_can_push_says_what_is_missing(rig):
    html = rig.get("/").text
    assert "Nothing is being pushed." in html or "meow isn't pushing yet" in html


def test_the_live_fragment_carries_the_card_too(rig):
    lt = hiss(rig)
    assert lt.litterId in rig.get("/live/overview").text
