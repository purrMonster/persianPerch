"""binocs (05 plan M4, C7, C8, design plan 4.6): the tunnel (from Gatus), speedtest-tracker's last result and the
weekly look at upstream releases of every image the fleet pins. Everything runs against fakes: **no real Gatus,
speedtest-tracker or registry request is ever made**."""

import asyncio
from datetime import timedelta

import pytest
from outsideFakes import SPEEDTEST_TOKEN, GatusFake, RegistryFake, SpeedtestFake

from perch.bodyLanguage import BodyLanguage as B
from perch.collectors import buildCollectors
from perch.rollup import Status
from perch.scentTrail import ScentTrail
from perch.senses.binocs import TUNNEL_KEY, Binocs, releasesSummary
from perch.senses.glare import Glare
from perch.senses.registries import newestRelease, parseImage, parseTag
from perch.senses.speedtest import SpeedtestError
from perch.settings import Settings

# -- reading an image reference ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ref", "registry", "repo", "tag"),
    [
        ("traefik:v3.7.13", "registry-1.docker.io", "library/traefik", "v3.7.13"),
        ("n8nio/n8n:2.39.7", "registry-1.docker.io", "n8nio/n8n", "2.39.7"),
        ("redis:8.8.2-alpine", "registry-1.docker.io", "library/redis", "8.8.2-alpine"),
        ("ghcr.io/moghtech/komodo-core:2.3.2", "ghcr.io", "moghtech/komodo-core", "2.3.2"),
        (
            "lscr.io/linuxserver/speedtest-tracker:v1.15.0-ls170",
            "ghcr.io",
            "linuxserver/speedtest-tracker",
            "v1.15.0-ls170",
        ),
        ("docker.io/library/mongo:7.0.14", "registry-1.docker.io", "library/mongo", "7.0.14"),
    ],
)
def test_a_pinned_release_is_read_as_a_registry_repository_and_tag(ref, registry, repo, tag):
    image = parseImage(ref)
    assert image and (image.registry, image.repo, image.tag) == (registry, repo, tag)


@pytest.mark.parametrize(
    "ref",
    [
        "ghcr.io/open-webui/open-webui:main@sha256:1a6399d237dc392a2313e0ca826020b3fd5d22536357840eb63393d18dc8b924",
        "postgres:16",  # a line, not a release
        "mongo:7.0",
        "getmeili/meilisearch:v1.10",
        "ghcr.io/home-assistant/home-assistant:stable",  # a moving tag
        "klutchell/unbound:main",
        "purrbrews/embedding-worker:local",
        "pgvector/pgvector:pg16",
        "quay.io/example/thing:1.2.3",  # a registry perch doesn't read
        "nginx",  # no tag at all
    ],
)
def test_what_cannot_be_compared_is_skipped_never_guessed(ref):
    assert parseImage(ref) is None


def test_a_newer_release_has_the_same_flavour_and_more_than_the_pin_in_number_order():
    pin = parseTag("2.3.2")
    tags = ["2.3.2", "2.4.0", "2.10.0", "2.9.9", "2.11.0-rc1", "3.0", "latest", "2.12.0-alpine", "v2.2.9"]
    assert newestRelease(pin, tags).text() == "2.10.0"  # 2.10 is newer than 2.9: numbers, not text
    assert newestRelease(pin, ["2.3.2", "2.3.1", "main"]) is None
    assert newestRelease(parseTag("8.8.2-alpine"), ["8.8.3", "8.9.0-alpine", "8.8.3-alpine"]).text() == "8.9.0-alpine"
    # a LinuxServer rebuild counter is not a release
    assert newestRelease(parseTag("v1.15.0-ls170"), ["v1.15.0-ls171", "v1.15.0-ls172"]) is None
    assert newestRelease(parseTag("v1.15.0-ls170"), ["v1.16.0-ls3"]).text() == "1.16.0"


# -- the registries: anonymous, paged, careful --------------------------------------------------------


def run(coro):
    return asyncio.run(coro)


def test_tags_are_read_anonymously_through_the_token_challenge_and_every_page():
    fake = RegistryFake()
    fake.tags["ghcr.io/moghtech/komodo-core"] = ["2.3.0", "2.3.1", "2.3.2", "2.4.0", "latest"]
    fake.pageSize = 2
    client = fake.client()
    image = parseImage("ghcr.io/moghtech/komodo-core:2.3.2")
    tags = run(client.tags(image))
    assert sorted(tags) == ["2.3.0", "2.3.1", "2.3.2", "2.4.0", "latest"]
    paths = [(r.url.host, r.url.path) for r in fake.requests]
    assert paths[0] == ("ghcr.io", "/v2/moghtech/komodo-core/tags/list")
    assert ("ghcr.io", "/token") in paths
    assert all(r.method == "GET" for r in fake.requests)
    run(client.aclose())


def test_docker_hub_is_read_through_its_registry_and_token_service():
    fake = RegistryFake()
    fake.tags["registry-1.docker.io/library/traefik"] = ["v3.7.13", "v3.8.0"]
    client = fake.client()
    assert run(client.tags(parseImage("traefik:v3.7.13"))) == ["v3.7.13", "v3.8.0"]
    assert {r.url.host for r in fake.requests} == {"registry-1.docker.io", "auth.docker.io"}
    run(client.aclose())


def test_a_token_challenge_for_another_host_is_refused_not_followed():
    from perch.senses.registries import RegistryError

    fake = RegistryFake()
    fake.tags["ghcr.io/moghtech/komodo-core"] = ["2.3.2"]
    fake.evilRealm = True
    client = fake.client()
    with pytest.raises(RegistryError, match="another host"):
        run(client.tags(parseImage("ghcr.io/moghtech/komodo-core:2.3.2")))
    assert {r.url.host for r in fake.requests} == {"ghcr.io"}  # perch never went to the other host
    run(client.aclose())


# -- the weekly look at upstream releases ------------------------------------------------------------


class Rig:
    def __init__(self, tmp_path, clock, fleetTree, **kw):
        self.clock = clock
        self.tree = fleetTree
        self.trail = ScentTrail(tmp_path / "b.db", clock=clock)
        self.registry = RegistryFake()
        self.speed = SpeedtestFake(clock)
        self.gatus = GatusFake(clock)
        self.paused = 0

        async def pause():
            self.paused += 1

        args = {
            "speedtest": self.speed.client(),
            "registries": self.registry.client(),
            "releasesEvery": 7 * 86400,
            "pause": pause,
        } | kw
        self.binocs = Binocs(self.trail, fleetTree, clock=clock, **args)
        self.loop = asyncio.new_event_loop()
        # every comparable pin is current, until a test says otherwise
        for node in fleetTree.fleet().nodes:
            for app in node.apps:
                for ref in app.images:
                    image = parseImage(ref)
                    if image:
                        self.registry.tags.setdefault(image.key, []).append(image.tag)

    def cycle(self, n=1, **advance):
        for _ in range(n):
            self.loop.run_until_complete(self.binocs.cycle())
            self.clock.advance(**(advance or {"minutes": 15}))

    def state(self, subject):
        return self.trail.states()[subject]

    def releaseStates(self):
        return {s: st for s, st in self.trail.states().items() if s.startswith("binocs:release/")}

    def close(self):
        self.loop.run_until_complete(self.binocs.aclose())
        self.loop.close()
        self.trail.close()


@pytest.fixture
def rig(tmp_path, clock, fleetTree):
    r = Rig(tmp_path, clock, fleetTree)
    yield r
    r.close()


def test_a_newer_release_is_earTwitch_once_with_an_event_and_never_hiss(rig):
    rig.registry.tags["registry-1.docker.io/n8nio/n8n"].append("2.40.0")
    rig.registry.tags["ghcr.io/moghtech/komodo-core"].append("2.4.0")
    rig.cycle()
    found = rig.releaseStates()
    assert set(found) == {"binocs:release/n8nio/n8n", "binocs:release/moghtech/komodo-core"}
    assert all(st.bodyLanguage is B.earTwitch for st in found.values())
    n8n = found["binocs:release/n8nio/n8n"]
    assert n8n.title == "n8nio/n8n 2.39.7 is pinned, 2.40.0 is out"
    assert n8n.detail["usedBy"] and all("/" in u for u in n8n.detail["usedBy"])
    events = rig.trail.events(senses=["binocs"])
    assert len(events) == 2 and all(e.bodyLanguage is B.earTwitch for e in events)
    summary = releasesSummary(rig.trail)
    assert summary["newer"] == 2 and summary["images"] > 20 and summary["skipped"] > 5 and summary["failed"] == 0
    # nothing binocs writes is ever worse than earTwitch
    assert not [s for s in rig.trail.states().values() if s.subject.startswith("binocs:") and s.bodyLanguage.rank > 2]


def test_it_looks_weekly_and_only_weekly(rig):
    rig.cycle()
    first = len(rig.registry.requests)
    assert first > 0
    rig.cycle(5, hours=24)  # five more days
    assert len(rig.registry.requests) == first
    rig.cycle(3, hours=24)  # now more than 7 days since the look
    assert len(rig.registry.requests) > first


def test_a_pin_that_caught_up_is_forgotten_at_the_next_look(rig):
    rig.registry.tags["registry-1.docker.io/n8nio/n8n"].append("2.40.0")
    rig.cycle(1, days=8)
    assert rig.releaseStates()
    rig.registry.tags["registry-1.docker.io/n8nio/n8n"].remove("2.40.0")  # (stands in for the owner bumping the pin)
    rig.cycle(1, days=8)
    assert rig.releaseStates() == {}


def test_a_rate_limit_stops_the_run_keeps_what_was_found_and_retries_after_the_wait(rig):
    rig.registry.tags["ghcr.io/moghtech/komodo-core"].append("2.4.0")
    rig.registry.limit["registry-1.docker.io"] = 7200  # Docker Hub answers 429, Retry-After 2 hours
    rig.cycle(1, minutes=15)
    summary = releasesSummary(rig.trail)
    assert summary["stopped"] == "registry-1.docker.io is rate limiting perch" and summary["failed"] >= 1
    before = len(rig.registry.requests)
    rig.cycle(4, minutes=15)  # the next hour: nothing more is asked of any registry
    assert len(rig.registry.requests) == before
    del rig.registry.limit["registry-1.docker.io"]
    rig.cycle(2, hours=2)  # the second look is past the Retry-After
    assert len(rig.registry.requests) > before
    assert releasesSummary(rig.trail)["stopped"] is None
    assert "binocs:release/moghtech/komodo-core" in rig.releaseStates()


def test_one_image_failing_does_not_stop_the_others(rig):
    del rig.registry.tags["ghcr.io/moghtech/komodo-core"]  # a 404 for that repository
    rig.registry.tags["registry-1.docker.io/n8nio/n8n"].append("2.40.0")
    rig.cycle()
    assert "binocs:release/n8nio/n8n" in rig.releaseStates()
    assert releasesSummary(rig.trail)["failed"] >= 1


def test_registries_are_asked_with_no_credential_and_only_for_tags(rig):
    rig.cycle()
    assert rig.registry.requests
    assert all(r.method == "GET" for r in rig.registry.requests)
    for r in rig.registry.requests:
        assert r.url.path == "/token" or r.url.path.endswith("/tags/list")
        assert r.headers.get("authorization", "Bearer fake-anon-token") == "Bearer fake-anon-token"


# -- speedtest ---------------------------------------------------------------------------------------


def test_a_good_speedtest_is_slowBlink_with_its_numbers(rig):
    rig.cycle()
    st = rig.state("binocs:speedtest")
    assert st.bodyLanguage is B.slowBlink
    assert st.title == "down 312.4 Mbit/s, up 41.2 Mbit/s, ping 9.4 ms"
    assert st.detail["status"] == "completed" and st.detail["healthy"] is True


@pytest.mark.parametrize(
    ("change", "words"),
    [
        ({"status": "failed"}, "the last speedtest failed"),
        ({"healthy": False}, "below the thresholds speedtest-tracker is set to"),
    ],
)
def test_a_failed_or_unhealthy_speedtest_is_earTwitch_not_more(rig, change, words):
    for key, value in change.items():
        setattr(rig.speed, key, value)
    rig.cycle()
    st = rig.state("binocs:speedtest")
    assert st.bodyLanguage is B.earTwitch and words in st.title
    (event,) = rig.trail.events(senses=["binocs"])
    assert event.subject == "binocs:speedtest" and event.bodyLanguage is B.earTwitch


def test_no_speedtest_for_six_hours_is_earTwitch(rig):
    rig.speed.at = rig.clock() - timedelta(hours=7)
    rig.cycle()
    assert rig.state("binocs:speedtest").bodyLanguage is B.earTwitch
    assert "no new speedtest for 7 h" in rig.state("binocs:speedtest").title


def test_speedtest_unreachable_forbidden_or_empty_is_unknown_never_an_alarm(rig):
    rig.speed.down = True
    rig.cycle()
    assert rig.state("binocs:speedtest").bodyLanguage is B.unknown
    assert "can't see speedtest-tracker" in rig.state("binocs:speedtest").title
    rig.speed.down, rig.speed.forbidden = False, True
    rig.cycle()
    title = rig.state("binocs:speedtest").title
    assert "refused the token" in title and SPEEDTEST_TOKEN not in title
    rig.speed.forbidden, rig.speed.noResults = False, True
    rig.cycle()
    assert rig.state("binocs:speedtest").title == "speedtest-tracker has no result yet"
    assert rig.trail.events() == []


def test_speedtest_sends_only_the_one_get_with_a_bearer_token(rig):
    rig.cycle(2)
    assert {(r.method, r.url.path) for r in rig.speed.requests} == {("GET", "/api/v1/results/latest")}
    assert all(r.headers["authorization"] == f"Bearer {SPEEDTEST_TOKEN}" for r in rig.speed.requests)


def test_a_result_in_another_shape_is_an_error_not_a_guess():
    import httpx2
    from outsideFakes import IST, SPEEDTEST_URL

    from perch.senses.speedtest import SpeedtestClient

    def odd(request):
        return httpx2.Response(200, json={"data": {"status": "completed", "created_at": "yesterday"}})

    client = SpeedtestClient(SPEEDTEST_URL, SPEEDTEST_TOKEN, tz=IST, transport=httpx2.MockTransport(odd))
    with pytest.raises(SpeedtestError, match="not the v1.15.0 result shape"):
        run(client.latest())
    run(client.aclose())


# -- the tunnel (C7) and what starts from settings -------------------------------------------------------


def test_the_tunnel_is_what_gatus_says_about_it_with_no_request_of_binocs_own(tmp_path, clock, fleetTree):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    gatus = GatusFake(clock)
    gatus.add("cloudflare tunnel", "network")
    loop = asyncio.new_event_loop()
    glare = Glare(gatus.client(), trail, clock=clock)
    status = lambda: Status(fleetTree.fleet(), trail)  # noqa: E731
    assert status().tunnel() is None  # no Gatus read yet
    gatus.tick()
    loop.run_until_complete(glare.cycle())
    assert TUNNEL_KEY == "network_cloudflare-tunnel"
    assert status().tunnel().bodyLanguage is B.slowBlink
    for _ in range(5):
        gatus.check(TUNNEL_KEY, up=False, why="HTTP 503 from cloudflared /ready")
        clock.advance(seconds=60)
        loop.run_until_complete(glare.cycle())
    tunnel = status().tunnel()
    assert tunnel.bodyLanguage is B.hiss and "HTTP 503 from cloudflared /ready" in tunnel.title
    assert not [s for s in trail.states() if s.startswith("binocs:")]  # nothing written under binocs for it
    loop.run_until_complete(glare.aclose())
    loop.close()
    trail.close()


def test_the_fleet_level_counts_glare_but_never_a_binocs_notice(rig, fleetTree):
    rig.registry.tags["registry-1.docker.io/n8nio/n8n"].append("2.40.0")
    rig.speed.healthy = False
    rig.cycle()
    status = Status(fleetTree.fleet(), rig.trail)
    assert len(status.binocs()) == 2 and all(s.bodyLanguage is B.earTwitch for s in status.binocs())
    withNotices = status.fleetLevel()
    rig.trail.forget([s.subject for s in status.binocs()])
    assert Status(fleetTree.fleet(), rig.trail).fleetLevel() is withNotices  # the notices changed nothing
    assert all(a.level.rank >= B.tailFlick.rank for a in status.attention())


def test_nothing_reaches_a_registry_unless_the_weekly_look_is_switched_on(tmp_path, clock, fleetTree):
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    base = {"repoDir": tmp_path, "trailDb": tmp_path / "t.db"}
    assert buildCollectors(Settings(**base), trail, fleetTree, clock) == []
    assert Settings.fromEnv({}).binocsReleasesEvery == 0
    (only,) = buildCollectors(Settings(**base, binocsReleasesEvery=7 * 86400), trail, fleetTree, clock)
    assert isinstance(only, Binocs) and only.registries is not None and only.speedtest is None
    both = buildCollectors(
        Settings(**base, binocsSpeedtestUrl="http://192.0.2.14:8765", binocsSpeedtestToken="fake-token-not-real"),
        trail, fleetTree, clock,
    )  # fmt: skip
    (b,) = both
    assert b.speedtest is not None and b.registries is None and b.releasesEvery == 0
    asyncio.run(b.aclose())
    asyncio.run(only.aclose())
    trail.close()


def test_glare_and_disks_start_only_from_their_settings_and_half_set_ones_say_so(tmp_path, clock, fleetTree):
    from perch.senses.disks import Disks

    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    base = {"repoDir": tmp_path, "trailDb": tmp_path / "t.db"}
    made = buildCollectors(
        Settings(
            **base,
            glareUrl="http://gatus.example.home.arpa",
            glareUser="perch-svc",
            glarePassword="fake-pw-not-real",
            disksUrl="http://scrutiny:8080",
        ),
        trail, fleetTree, clock,
    )  # fmt: skip
    assert [type(c).__name__ for c in made] == ["Glare", "Disks"] and isinstance(made[1], Disks)
    for c in made:
        asyncio.run(c.aclose())
    assert buildCollectors(Settings(**base, glareUrl="http://gatus.example.home.arpa"), trail, fleetTree, clock) == []
    (event,) = trail.events()
    assert event.bodyLanguage is B.tailFlick and "PERCH_GLARE_USER" in event.title
    trail.close()
