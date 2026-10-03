"""pounce on perch's side (M5): what /api/kitten does with the events kitten sends."""

from datetime import UTC, datetime, timedelta

import pytest
from conftest import FakeClock
from fastapi.testclient import TestClient

from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import ScentTrail
from perch.settings import Settings
from perch.windowsill.app import createApp

TOKENS = {"cellar": "fake-token-cellar-not-real", "grinder": "fake-token-grinder-not-real"}
NOW = datetime(2026, 10, 3, 10, 0, 0, tzinfo=UTC)


@pytest.fixture
def client(fleetRepo, fleetTree, tmp_path):
    clock = FakeClock(NOW)
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db", kittenTokens=TOKENS)
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[])
    with TestClient(app) as c:
        c.trail, c.clock = trail, clock
        yield c
    trail.close()


def event(eventId="a1b2c3d4e5f6", **more):
    return {
        "id": eventId,
        "at": "2026-10-03T09:59:58Z",
        "path": "/srv/data/paperless/consume",
        "name": "invoice.pdf",
        "change": "created",
        "level": "earTwitch",
        "why": "a document dropped",
        **more,
    }


def send(client, events, node="cellar", **more):
    return client.post(
        "/api/kitten",
        json={"node": node, "events": events, **more},
        headers={"Authorization": f"Bearer {TOKENS[node]}"},
    )


def pounced(client):
    return client.trail.events(senses=["pounce"])


def test_an_event_alone_is_a_report_and_lands_on_the_trail_with_its_body_language(client):
    r = send(client, [event()])
    assert r.status_code == 200 and r.json()["events"] == ["a1b2c3d4e5f6"]
    [found] = pounced(client)
    assert found.bodyLanguage is B.earTwitch
    assert found.subject == "pounce:cellar//srv/data/paperless/consume"
    assert found.title == "a document dropped: invoice.pdf appeared"
    assert found.detail == {
        "node": "cellar",
        "path": "/srv/data/paperless/consume",
        "name": "invoice.pdf",
        "change": "created",
    }
    assert found.seenAt == datetime(2026, 10, 3, 9, 59, 58, tzinfo=UTC)


def test_a_settings_change_is_a_tailFlick_and_a_pull_carries_the_commit_subject(client):
    send(
        client,
        [
            event("aaaaaa000001", path="/etc/purrbrews", name="pounce.env", change="modified", level="tailFlick",
                  why="settings changed"),
            event("aaaaaa000002", path="/opt/purrbrews/.git/refs/heads/main", name="", level="earTwitch",
                  why="the node pulled", commit="compose: pin immich"),
        ],
    )  # fmt: skip
    by = {e.detail["path"]: e for e in pounced(client)}
    assert by["/etc/purrbrews"].bodyLanguage is B.tailFlick
    assert by["/etc/purrbrews"].title == "settings changed: pounce.env changed"
    assert by["/opt/purrbrews/.git/refs/heads/main"].title == "the node pulled: “compose: pin immich”"


def test_a_hiss_is_never_taken_from_a_changed_file(client):
    assert send(client, [event(level="hiss")]).status_code == 422
    assert pounced(client) == []


def test_a_storm_is_one_tailFlick(client):
    send(client, [event("bbbbbb000001", change="storm", name="", level="tailFlick")])
    [found] = pounced(client)
    assert found.bodyLanguage is B.tailFlick and "more than 60 changes" in found.title


def test_a_resent_event_is_stored_once(client):
    send(client, [event()])
    r = send(client, [event()])
    assert r.json()["events"] == ["a1b2c3d4e5f6"]  # acknowledged again, so kitten stops asking
    assert len(pounced(client)) == 1


def test_a_node_clock_that_is_wrong_gets_the_time_perch_heard_it(client):
    send(client, [event(at="2020-01-01T00:00:00Z")])
    assert pounced(client)[0].seenAt == NOW


@pytest.mark.parametrize(
    "bad",
    [
        {"id": "not hex!"},
        {"change": "exploded"},
        {"at": "yesterday"},
        {"path": ""},
        {"name": 5},
        {"level": "loud"},
    ],
)
def test_a_malformed_event_is_a_422_that_names_it_and_stores_nothing(client, bad):
    r = send(client, [event("cccccc000001"), event("cccccc000002", **bad)])
    assert r.status_code == 422 and r.json()["error"].startswith("event 1:")
    assert pounced(client) == []


def test_too_many_events_or_a_wrong_shape_is_a_422(client):
    assert send(client, [event(f"dddddd{i:06x}") for i in range(101)]).status_code == 422
    auth = {"Authorization": f"Bearer {TOKENS['cellar']}"}
    r = client.post("/api/kitten", json={"node": "cellar", "events": "no"}, headers=auth)
    assert r.status_code == 422
    assert send(client, ["no"]).status_code == 422


def test_S3_holds_for_events_too(client):
    r = client.post("/api/kitten", json={"node": "cellar", "events": [event()]})
    assert r.status_code == 401
    r = client.post(
        "/api/kitten",
        json={"node": "cellar", "events": [event()]},
        headers={"Authorization": f"Bearer {TOKENS['grinder']}"},
    )
    assert r.status_code == 403
    assert pounced(client) == []


def test_names_are_scrubbed_like_any_title(fleetRepo, fleetTree, tmp_path):
    clock = FakeClock(NOW)
    trail = ScentTrail(tmp_path / "s.db", clock=clock, secrets=["fake-secret-in-a-file-name"])
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "s.db", kittenTokens=TOKENS)
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[])
    with TestClient(app) as c:
        send(c, [event(name="fake-secret-in-a-file-name.txt")])
    [found] = trail.events(senses=["pounce"])
    assert "fake-secret-in-a-file-name" not in found.title
    assert "fake-secret-in-a-file-name" not in str(found.detail)
    trail.close()


def test_a_pounce_event_does_not_move_the_fleet(client):
    send(client, [event(level="tailFlick")])
    from perch.rollup import Status

    status = Status(client.app.state.tree.fleet(), client.trail)
    assert not [s for s in status.states if s.startswith("pounce")]
    assert abs(client.clock() - NOW) < timedelta(seconds=1)
