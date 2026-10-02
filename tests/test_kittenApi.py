"""POST /api/kitten: what each node's kitten sends (S3), what perch does with it, and what it never does."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from conftest import FakeClock
from fastapi.testclient import TestClient

from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import ScentTrail
from perch.settings import Settings
from perch.windowsill.app import createApp

IST = ZoneInfo("Asia/Kolkata")
TOKENS = {"sieve": "fake-token-sieve-not-real", "grinder": "fake-token-grinder-not-real"}


def stamp(hour, minute=0, day=29):
    return datetime(2026, 9, day, hour, minute, tzinfo=IST).astimezone(UTC)


def record(node="grinder", job="nightly", start=None, result="success", **more):
    start = start or stamp(1, 30)
    return {
        "schema": 1,
        "job": job,
        "node": node,
        "unit": f"purrbrews-backup@{node}.service",
        "start": start.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "end": (start + timedelta(minutes=20)).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "result": result,
        "exitStatus": "0" if result == "success" else "1",
        "logTail": "",
        **more,
    }


@pytest.fixture
def client(fleetRepo, fleetTree, tmp_path):
    clock = FakeClock(stamp(2, 0))
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db", kittenTokens=TOKENS)
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock, collectors=[])
    with TestClient(app) as c:
        c.trail, c.clock = trail, clock
        yield c
    trail.close()


def post(client, body, token=TOKENS["grinder"], **kw):
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    return client.post("/api/kitten", json=body, headers=headers, **kw)


# -- S3: who may speak ----------------------------------------------------------------------


def test_S3_no_token_is_401(client):
    r = post(client, {"node": "grinder", "heartbeat": {}}, token=None)
    assert r.status_code == 401 and r.headers["www-authenticate"] == "Bearer"
    assert client.post("/api/kitten", json={}, headers={"Authorization": "Basic abc"}).status_code == 401
    assert client.post("/api/kitten", json={}, headers={"Authorization": "Bearer "}).status_code == 401


def test_S3_a_token_nobody_has_is_401(client):
    assert post(client, {"node": "grinder", "heartbeat": {}}, token="fake-token-nobody").status_code == 401


def test_S3_another_nodes_token_is_403_and_changes_nothing(client):
    r = post(client, {"node": "grinder", "heartbeat": {}, "records": [record()]}, token=TOKENS["sieve"])
    assert r.status_code == 403
    assert client.trail.runs() == [] and "kitten:grinder" not in client.trail.states()


def test_S3_a_record_for_another_node_inside_my_own_report_is_403(client):
    r = post(client, {"node": "grinder", "records": [record(node="sieve")]})
    assert r.status_code == 403 and client.trail.runs() == []


def test_with_no_tokens_configured_nobody_gets_in(fleetRepo, fleetTree, tmp_path):
    app = createApp(
        Settings(repoDir=fleetRepo, trailDb=tmp_path / "x.db"), tree=fleetTree, clock=lambda: stamp(2), collectors=[]
    )
    with TestClient(app) as c:
        assert c.post("/api/kitten", json={"node": "grinder", "heartbeat": {}}).status_code == 401
        assert (
            c.post(
                "/api/kitten", json={"node": "grinder", "heartbeat": {}}, headers={"Authorization": "Bearer "}
            ).status_code
            == 401
        )


# -- what it does with a good report ------------------------------------------------------------


def test_a_heartbeat_makes_the_node_heard_and_a_record_is_stored_and_judged(client):
    r = post(client, {"node": "grinder", "heartbeat": {"version": "0.1.0", "stamps": {}}, "records": [record()]})
    assert r.status_code == 200 and r.json() == {"ok": True, "stored": ["2026-09-28T20:00:00.000Z"]}
    states = client.trail.states()
    assert states["kitten:grinder"].bodyLanguage is B.slowBlink
    assert states["kitten:grinder"].detail["version"] == "0.1.0"
    assert states["groom:grinder/nightly"].bodyLanguage is B.slowBlink
    assert len(client.trail.runs()) == 1


def test_the_same_report_again_is_fine_and_stores_nothing_new(client):
    body = {"node": "grinder", "heartbeat": {"version": "0.1.0"}, "records": [record()]}
    assert post(client, body).json() == post(client, body).json()
    assert len(client.trail.runs()) == 1


def test_a_failed_record_reaches_the_page_at_once(client):
    post(client, {"node": "sieve", "records": [record("sieve", result="exit-code")]}, token=TOKENS["sieve"])
    assert client.trail.states()["groom:sieve/nightly"].bodyLanguage is B.hiss
    html = client.get("/").text
    assert "Needs a look" in html and "failed (exit-code, exit 1)" in html


# -- what it refuses ------------------------------------------------------------------------


@pytest.mark.parametrize(
    "body",
    [
        [],
        {"node": "grinder"},
        {"node": "grinder", "heartbeat": "up"},
        {"node": "grinder", "records": "x"},
        {"node": "grinder", "records": [{"schema": 9}]},
        {"node": "grinder", "records": [record(job="../x")]},
        {"node": "grinder", "records": [record()] * 101},
    ],
)
def test_a_malformed_report_is_422_and_stores_nothing(client, body):
    r = post(client, body)
    assert r.status_code == 422 and r.json()["ok"] is False
    assert client.trail.runs() == []


def test_not_json_is_422_and_a_huge_body_is_413(client):
    headers = {"Authorization": f"Bearer {TOKENS['grinder']}"}
    assert client.post("/api/kitten", content=b"{nope", headers=headers).status_code == 422
    big = b'{"node":"grinder","records":[],"pad":"' + b"a" * (1024 * 1024) + b'"}'
    assert client.post("/api/kitten", content=big, headers=headers).status_code == 413


def test_the_tokens_are_never_in_a_response_or_a_page(client):
    r = post(client, {"node": "grinder", "heartbeat": {"version": "0.1.0"}}, token=TOKENS["sieve"])
    pages = [r.text, client.get("/").text, client.get("/groom").text, client.get("/healthz").text]
    for text in pages:
        for token in TOKENS.values():
            assert token not in text


def test_a_log_tail_with_a_known_secret_is_scrubbed(fleetRepo, fleetTree, tmp_path):
    clock = FakeClock(stamp(2, 0))
    trail = ScentTrail(tmp_path / "t.db", clock=clock, secrets=["fake-restic-password-xyz"])
    app = createApp(
        Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db", kittenTokens=TOKENS),
        trail=trail,
        tree=fleetTree,
        clock=clock,
        collectors=[],
    )
    with TestClient(app) as c:
        post(
            c,
            {
                "node": "grinder",
                "records": [record(result="exit-code", logTail="RESTIC_PASSWORD=fake-restic-password-xyz")],
            },
        )
        assert all("fake-restic-password-xyz" not in (r.logTail or "") for r in trail.runs())
        assert all("fake-restic-password-xyz" not in (e.logTail or "") for e in trail.events())
    trail.close()
