"""The Komodo adapter against payloads shaped from the v2.3.2 source (tests/fixtures/komodo):
what it sends, how it parses, how it fails, and that it can only ever read."""

import asyncio
import json
from datetime import UTC, datetime
from pathlib import Path

import httpx2
import pytest

from perch.senses.komodo import KomodoClient, KomodoError, serverState

FIXTURES = Path(__file__).parent / "fixtures" / "komodo"
KEY, SECRET = "K-fake-key-for-tests", "S-fake-secret-for-tests"
NOW = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


def load(name):
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


class FakeKomodo:
    """A Komodo Core that answers /read from the fixtures and records every request."""

    def __init__(self):
        self.requests: list[httpx2.Request] = []
        self.servers = load("list_servers.json")
        self.containers = {"grinder": load("list_containers_grinder.json"), "cellar": []}
        self.failContainersFor: set[str] = set()
        self.status = 200
        self.raw: bytes | None = None

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.status != 200:
            return httpx2.Response(self.status, text=f"denied for key {KEY}: no")
        if self.raw is not None:
            return httpx2.Response(200, content=self.raw)
        body = json.loads(request.content)
        if body["type"] == "ListServers":
            return httpx2.Response(200, json=self.servers)
        if body["type"] == "ListContainers":
            server = body["params"]["server"]
            if server in self.failContainersFor:
                return httpx2.Response(500, text="periphery went away")
            return httpx2.Response(200, json=self.containers[server])
        return httpx2.Response(400, text="unknown request")

    def client(self) -> KomodoClient:
        return KomodoClient("http://komodo-core:9120", KEY, SECRET, transport=httpx2.MockTransport(self))

    def bodies(self):
        return [json.loads(r.content) for r in self.requests]


@pytest.fixture
def komodo():
    return FakeKomodo()


def snapshot(komodo):
    async def go():
        client = komodo.client()
        try:
            return await client.snapshot(NOW)
        finally:
            await client.aclose()

    return asyncio.run(go())


# -- what it sends --------------------------------------------------------------


def test_sends_only_read_requests_to_read_with_the_key_in_headers(komodo):
    snapshot(komodo)
    assert [(r.method, r.url.path) for r in komodo.requests] == [("POST", "/read")] * len(komodo.requests)
    assert komodo.bodies()[0] == {"type": "ListServers", "params": {}}
    for request in komodo.requests:
        assert request.headers["x-api-key"] == KEY and request.headers["x-api-secret"] == SECRET
        assert KEY not in str(request.url) and KEY not in request.content.decode()
        assert SECRET not in str(request.url) and SECRET not in request.content.decode()
    assert {b["type"] for b in komodo.bodies()} == {"ListServers", "ListContainers"}


def test_lists_containers_only_for_servers_that_are_ok(komodo):
    snapshot(komodo)
    asked = [b["params"]["server"] for b in komodo.bodies() if b["type"] == "ListContainers"]
    assert sorted(asked) == ["cellar", "grinder"]  # not roastery (NotOk), not spare (Disabled)


def test_it_cannot_send_a_write_or_execute_request(komodo):
    client = komodo.client()
    for kind in ("DeleteServer", "RestartContainer", "StopContainer", "CreateServer", "PruneContainers", "listservers"):
        with pytest.raises(ValueError, match="read-only"):
            asyncio.run(client._read(kind, {}))
    assert komodo.requests == []


def test_it_refuses_to_start_without_credentials():
    for url, key, secret in (("", KEY, SECRET), ("http://komodo-core:9120", "", SECRET), ("http://x:1", KEY, "")):
        with pytest.raises(ValueError, match="needs"):
            KomodoClient(url, key, secret)


# -- what it makes of the answers -----------------------------------------------


def test_servers_are_parsed_with_state_vitals_and_the_reason(komodo):
    snap = snapshot(komodo)
    byName = {s.name: s for s in snap.servers}
    assert list(byName) == ["grinder", "cellar", "roastery", "spare"]
    assert [byName[n].state for n in byName] == ["ok", "ok", "notok", "disabled"]
    grinder = byName["grinder"]
    assert grinder.version == "2.3.2" and grinder.stats is not None
    assert (grinder.stats.cpuPerc, round(grinder.stats.memPerc), round(grinder.stats.diskPerc)) == (63.4, 91, 58)
    assert byName["roastery"].stats is None and byName["roastery"].err == "Periphery is not connected"
    assert byName["spare"].err is None


def test_containers_are_parsed_with_state_status_image_and_labels(komodo):
    snap = snapshot(komodo)
    by = {c.name: c for c in snap.containers["grinder"]}
    assert snap.containers["cellar"] == [] and "roastery" not in snap.containers
    n8n = by["n8n"]
    assert (n8n.state, n8n.status, n8n.image) == ("running", "Up 3 hours (healthy)", "n8nio/n8n:1.80.0")
    assert n8n.labels["com.docker.compose.project"] == "n8n" and n8n.createdAt == 1789900000
    assert by["embedding-worker"].state == "exited" and by["traccar"].state == "restarting"
    assert by["stray-test"].labels == {} and by["stray-test"].server == "grinder"
    assert snap.fetchedAt == NOW and snap.errors == {}


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("Ok", "ok"),
        ("ok", "ok"),
        ("NotOk", "notok"),
        ("not-ok", "notok"),
        ("Disabled", "disabled"),
        ("weird", "unknown"),
    ],
)
def test_server_state_spellings(raw, expected):
    # serde writes the variant name ("NotOk"); strum's Display writes "not-ok": accept both
    assert serverState(raw) == expected


def test_one_server_failing_does_not_fail_the_snapshot(komodo):
    komodo.failContainersFor = {"grinder"}
    snap = snapshot(komodo)
    assert "grinder" not in snap.containers and snap.containers["cellar"] == []
    assert "grinder" in snap.errors and "HTTP 500" in snap.errors["grinder"]
    assert {s.name for s in snap.servers} == {"grinder", "cellar", "roastery", "spare"}


# -- how it fails -----------------------------------------------------------------


@pytest.mark.parametrize(
    ("status", "words"), [(401, "refused"), (403, "refused"), (404, "HTTP 404"), (500, "HTTP 500")]
)
def test_http_errors_are_komodo_errors_without_the_secret(komodo, status, words):
    komodo.status = status
    with pytest.raises(KomodoError, match=words) as caught:
        snapshot(komodo)
    assert KEY not in str(caught.value) and SECRET not in str(caught.value)


@pytest.mark.parametrize("raw", [b"not json", b"{}", b'{"servers": []}', b'[{"nope": 1}]', b'["x"]'])
def test_an_unexpected_answer_is_a_komodo_error(komodo, raw):
    komodo.raw = raw
    with pytest.raises(KomodoError, match="unexpected"):
        snapshot(komodo)


@pytest.mark.parametrize(
    "error", [httpx2.ConnectError("refused"), httpx2.ReadTimeout("slow"), httpx2.RemoteProtocolError("bad")]
)
def test_network_errors_are_komodo_errors(error):
    def boom(request):
        raise error

    client = KomodoClient("http://komodo-core:9120", KEY, SECRET, transport=httpx2.MockTransport(boom))
    with pytest.raises(KomodoError, match="can't reach Komodo"):
        asyncio.run(client.snapshot(NOW))
