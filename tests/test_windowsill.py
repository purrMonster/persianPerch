"""windowsill pages against the pinned fleet repo, the leaky fixture (S1) and the route table (S7)."""

import re

import pytest
from fastapi.testclient import TestClient
from starlette.routing import Mount

from perch.bodyLanguage import BodyLanguage as B
from perch.catTree import CatTree
from perch.scentTrail import ScentTrail
from perch.settings import Settings
from perch.windowsill.app import createApp

# 05 plan A11 amends 04 rule 4: these are the only write endpoints perch may ever have.
ALLOWED_WRITES = {("POST", "/api/kitten"), ("POST", "/ack/{litterId}"), ("POST", "/ack/t/{token}")}


@pytest.fixture
def client(fleetRepo, fleetTree, tmp_path, clock):
    settings = Settings(repoDir=fleetRepo, trailDb=tmp_path / "trail.db")
    trail = ScentTrail(settings.trailDb, clock=clock)
    app = createApp(settings, trail=trail, tree=fleetTree, clock=clock)
    with TestClient(app) as c:
        c.trail = trail
        yield c
    trail.close()


PAGES = ["/", "/tree", "/tree/percolator", "/tree/percolator/authelia", "/tree/docs/runbook.md", "/groom", "/trail"]


@pytest.mark.parametrize("url", PAGES)
def test_pages_render(client, url):
    r = client.get(url)
    assert r.status_code == 200
    assert r.headers["content-type"].startswith("text/html")
    assert "persianPerch" in r.text and "/static/perch.css" in r.text


def test_tree_lists_every_node_and_app(client, fleetRepo):
    """M0 gate: /tree lists every node and app of the pinned repo."""
    fleet = CatTree(fleetRepo).fleet()
    html = client.get("/tree").text
    for node in fleet.nodes:
        assert f'href="/tree/{node.name}"' in html, node.name
        for app in node.apps:
            assert f'href="/tree/{node.name}/{app.name}"' in html, app.id
            assert client.get(f"/tree/{node.name}/{app.name}").status_code == 200


def test_no_data_yet_means_unknown_not_ok(client):
    html = client.get("/").text
    assert "bl-unknown" in html
    assert "fleet: slowBlink" not in html


def test_state_rolls_up_to_node_and_fleet(client):
    client.trail.setState("app:grinder/n8n", B.hiss, title="exited")
    html = client.get("/tree/grinder").text
    assert 'title="hiss: critical: needs barista"' in html
    assert "fleet: hiss" in client.get("/").text


def test_events_show_on_trail_and_app_page(client):
    client.trail.addEvent("purr", "app:grinder/n8n", B.tailFlick, "restarted (exit 137)", litterId="L7")
    trail = client.get("/trail").text
    assert "restarted (exit 137)" in trail and 'href="/tree/grinder/n8n"' in trail
    assert "restarted (exit 137)" in client.get("/tree/grinder/n8n").text
    assert "restarted (exit 137)" not in client.get("/trail?sense=groom").text
    assert "restarted (exit 137)" not in client.get("/trail?level=hiss").text


def test_unknown_things_are_404(client):
    for url in ("/tree/nosuchnode", "/tree/grinder/nosuchapp", "/tree/docs/stacks/fleet.env", "/tree/docs/../x"):
        assert client.get(url).status_code == 404, url


def test_healthz(client):
    body = client.get("/healthz").json()
    assert body["ok"] and body["journalMode"] == "wal" and len(body["commit"]) == 12


def test_page_escapes_html(client):
    client.trail.addEvent("purr", "app:grinder/n8n", B.hiss, "<script>alert(1)</script>")
    html = client.get("/trail").text
    assert "<script>alert(1)</script>" not in html and "&lt;script&gt;" in html


def test_S1_pages_never_show_secret_files(tmp_path, clock):
    from conftest import makeRepo

    secret = "fake-secret-in-a-tracked-file"
    repo = makeRepo(
        tmp_path / "leaky",
        {
            "README.md": "# fleet\n",
            "stacks/sieve/node.conf": "# sieve: the network node.\nAPPS=(ntfy)\n",
            "stacks/sieve/ntfy/secrets.conf": "NTFY_TOKEN prompt\n",
            "stacks/sieve/ntfy/secrets.env.local": f"NTFY_TOKEN={secret}\n",
            "stacks/sieve/ntfy/tls.key": secret,
            "stacks/sieve/authorized_keys": secret,
            "docs/leak.env.local.md": "fine, a doc",
        },
    )
    app = createApp(Settings(repoDir=repo, trailDb=tmp_path / "t.db"), clock=clock)
    with TestClient(app) as c:
        pages = [c.get(u).text for u in ("/", "/tree", "/tree/sieve", "/tree/sieve/ntfy", "/trail")]
        for url in ("/tree/docs/stacks/sieve/ntfy/secrets.env.local", "/tree/sieve/ntfy/secrets.env.local"):
            assert c.get(url).status_code == 404
    for html in pages:
        assert secret not in html
        assert "tls.key" not in html and "authorized_keys" not in html
    # the only mention of secrets.env.local is the fixed "never read" hint row
    ntfy = pages[3]
    assert len(re.findall(r"secrets\.env\.local", ntfy)) == 1 and "never read" in ntfy


def test_S7_no_write_endpoints_beyond_the_allowed(client):
    writes = set()
    for route in client.app.routes:
        if isinstance(route, Mount):
            continue
        for method in getattr(route, "methods", set()) or set():
            if method not in {"GET", "HEAD"}:
                writes.add((method, route.path))
    assert writes <= ALLOWED_WRITES, writes - ALLOWED_WRITES


def test_S7_write_methods_are_refused(client):
    for url in ("/", "/tree", "/trail", "/healthz"):
        for method in ("post", "put", "patch", "delete"):
            assert getattr(client, method)(url).status_code == 405, (method, url)
