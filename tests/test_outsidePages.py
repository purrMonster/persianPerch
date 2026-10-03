"""What a person reads for M4: the Endpoints (glare), Disks and Outside (binocs) cards, and the vitals
sparklines (docs/06 6). The senses run against fakes; windowsill renders what they wrote."""

import asyncio
import html as htmllib
import re
from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from outsideFakes import GatusFake, RegistryFake, ScrutinyFake, SpeedtestFake

from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import ScentTrail
from perch.senses.binocs import Binocs
from perch.senses.disks import Disks
from perch.senses.glare import Glare
from perch.senses.registries import parseImage
from perch.settings import Settings
from perch.vitals import Vitals
from perch.windowsill.app import createApp
from perch.windowsill.spark import altText, columns, path, sparkline


class Site:
    def __init__(self, client, trail, clock, tree):
        self.client, self.trail, self.clock, self.tree = client, trail, clock, tree
        self.loop = asyncio.new_event_loop()
        self.gatus, self.scrutiny, self.speed, self.registry = GatusFake(clock), ScrutinyFake(clock), None, None
        self.vitals = Vitals(trail, clock)

    def run(self, coro):
        return self.loop.run_until_complete(coro)

    def page(self, url):
        return htmllib.unescape(self.client.get(url).text).replace(" ", " ")

    def on(self, *names):
        for n in names:
            self.trail.setState(f"collector:{n}", B.slowBlink, title="on time", seenAt=self.clock())


@pytest.fixture
def site(fleetRepo, fleetTree, tmp_path, clock):
    trail = ScentTrail(tmp_path / "p.db", clock=clock)
    cfg = Settings(repoDir=fleetRepo, trailDb=tmp_path / "p.db")
    app = createApp(cfg, trail=trail, tree=fleetTree, clock=clock, collectors=[])
    with TestClient(app) as client:
        s = Site(client, trail, clock, fleetTree)
        yield s
        s.loop.close()
    trail.close()


# -- glare ---------------------------------------------------------------------------------------


def test_the_overview_shows_glare_from_the_fixture_and_the_placeholder_is_gone(site):
    site.gatus.add("cloudflare tunnel", "network")
    site.gatus.add("pihole", "network")
    site.gatus.add("authelia", "identity")
    glare = Glare(site.gatus.client(), site.trail, clock=site.clock)
    for _ in range(2):
        site.gatus.tick()
        site.run(glare.cycle())
    site.on("glare")
    html = site.page("/")
    assert "starts watching in M4" not in html
    assert "3 of 3 answering" in html and "Every endpoint passed its last check." in html
    # now the tunnel goes down for 5 checks
    for _ in range(5):
        site.gatus.check("network_cloudflare-tunnel", up=False, why="HTTP 503 from /ready")
        site.clock.advance(seconds=60)
        site.run(glare.cycle())
    html = site.page("/")
    assert "2 of 3 answering" in html
    assert "cloudflare tunnel" in html and "failed 5 checks in a row: HTTP 503 from /ready" in html
    assert "fleet: hiss" in html  # a glare hiss is the fleet's
    attention = html[html.index('id="h-attention"') : html.index('class="strip"')]
    assert "cloudflare tunnel" in attention and "hiss" in attention
    site.run(glare.aclose())


def test_glare_off_and_glare_waiting_are_each_said_in_words(site):
    assert "glare isn't watching: it needs PERCH_GLARE_URL" in re.sub(r"<[^>]+>", "", site.page("/"))
    site.on("glare")
    assert "glare is waiting for its first look at Gatus." in site.page("/")


# -- disks ---------------------------------------------------------------------------------------


def test_disks_show_on_the_overview_and_on_their_nodes_page_with_attribute_9_hours(site):
    site.scrutiny.add(
        "0x5000cca000000001", "sda", "cellar", "WDC WD40EFRX", summaryHours=3, attrs={"9": site.scrutiny.attr(9, 20000)}
    )
    site.scrutiny.add("0x5000cca000000002", "sdb", "cellar", "Old Disk", status=1)
    disks = Disks(site.scrutiny.client(), site.trail, clock=site.clock)
    site.run(disks.cycle())
    site.on("disks")
    html = site.page("/")
    assert "Disks" in html and "WDC WD40EFRX" in html and "833 d powered on" in html
    assert "SMART reports the drive failing" in html
    node = site.page("/tree/cellar")
    assert "WDC WD40EFRX" in node and "20000 h" in node and "summary: 3 h" in node
    assert "SMART reports the drive failing" in node
    assert "fleet: hiss" in html
    site.run(disks.aclose())


def test_a_disk_in_trouble_is_in_needs_a_look_with_a_link_to_its_node(site):
    site.scrutiny.add(
        "0x5000cca000000003", "sdc", "cellar", "Warm Disk", attrs={"5": site.scrutiny.attr(5, 9, status=2)}
    )
    site.run(Disks(site.scrutiny.client(), site.trail, clock=site.clock).cycle())
    html = site.page("/")
    attention = html[html.index('id="h-attention"') : html.index('class="strip"')]
    assert 'href="/tree/cellar"' in attention and "sdc Warm Disk" in attention and "Scrutiny warns about" in attention


# -- binocs --------------------------------------------------------------------------------------


def test_the_outside_card_shows_tunnel_speedtest_and_releases(site):
    site.gatus.add("cloudflare tunnel", "network")
    glare = Glare(site.gatus.client(), site.trail, clock=site.clock)
    site.gatus.tick()
    site.run(glare.cycle())
    site.speed = SpeedtestFake(site.clock)
    site.registry = RegistryFake()
    for node in site.tree.fleet().nodes:
        for app in node.apps:
            for ref in app.images:
                image = parseImage(ref)
                if image:
                    site.registry.tags.setdefault(image.key, []).append(image.tag)
    site.registry.tags["registry-1.docker.io/n8nio/n8n"].append("2.40.0")

    async def nap():
        return None

    binocs = Binocs(
        site.trail,
        site.tree,
        clock=site.clock,
        speedtest=site.speed.client(),
        registries=site.registry.client(),
        releasesEvery=7 * 86400,
        pause=nap,
    )
    site.run(binocs.cycle())
    site.on("binocs")
    html = site.page("/")
    card = html[html.index('id="binocs"') :]
    assert "up, 12 ms" in card  # the tunnel is Gatus's own check
    assert "down 312.4 Mbit/s, up 41.2 Mbit/s, ping 9.4 ms" in card
    assert "with a newer release" in card and "n8nio/n8n 2.39.7 is pinned, 2.40.0 is out" in card
    assert "Checked 0 s ago" in card
    assert "fleet: slowBlink" in html or "fleet: unknown" in html  # a notice never moves the fleet to earTwitch
    assert "fleet: earTwitch" not in html
    site.run(binocs.aclose())
    site.run(glare.aclose())


def test_binocs_off_says_what_to_set(site):
    html = site.page("/")
    card = html[html.index('id="binocs"') :]
    assert "PERCH_BINOCS_SPEEDTEST_URL" in card and "PERCH_BINOCS_RELEASES_EVERY" in card
    assert "Gatus has no check named cloudflare tunnel yet" in card


# -- sparklines ----------------------------------------------------------------------------------


def feedNode(site, node, hours, *, gapFrom=None, gapTo=None, cpu=lambda i: 40.0 + (i % 12), mem=58.0, disk=71.0):
    """purr's samples for ``hours`` hours up to now: every 30 s, minus an optional gap (hours ago)."""
    end = site.clock()
    start = end - timedelta(hours=hours)
    moment, i = start, 0
    while moment < end:
        ago = (end - moment).total_seconds() / 3600
        if not (gapFrom is not None and gapTo <= ago <= gapFrom):
            site.vitals.add(node, moment, cpu(i // 10), mem, disk)
        moment += timedelta(seconds=30)
        i += 1
    # what purr's last look says now: the live numbers the meters and the sparklines' "now" use
    site.trail.setState(
        f"node:{node}", B.slowBlink, detail={"mode": "ok", "cpu": 45.0, "mem": mem, "disk": disk}, seenAt=end
    )


def nodeCard(html, name):
    start = html.index(f'id="node-{name}"')
    end = html.find('id="node-', start + 10)
    return html[start : end if end > 0 else start + 20000]


def sparkLabels(html):
    return re.findall(r'<svg class="spark"[^>]*aria-label="([^"]+)"', html)


def test_overview_node_cards_carry_24_hour_sparklines_with_a_text_alternative(site):
    feedNode(site, "grinder", 30)
    html = site.page("/")
    card = nodeCard(html, "grinder")
    labels = sparkLabels(card)
    assert len(labels) == 3
    assert re.fullmatch(r"CPU 24 h: \d+-\d+ %, now 45 %", labels[0]) and labels[1] == "RAM 24 h: 58-58 %, now 58 %"
    assert labels[2].startswith("disk 24 h: 71-71 %")
    assert "last 24 h: CPU, RAM, disk" in card
    other = nodeCard(html, "sieve")
    assert "svg" not in other and "History appears" not in other  # no vitals, no meters, no sparklines


def test_a_gap_is_a_gap_the_line_breaks_and_the_text_says_so(site):
    feedNode(site, "grinder", 30, gapFrom=14, gapTo=8)  # perch saw nothing between 14 and 8 hours ago
    html = site.page("/")
    card = nodeCard(html, "grinder")
    cpu = re.search(r'<svg class="spark"[^>]*aria-label="CPU[^"]*".*?</svg>', card, re.S).group(0)
    assert "with gaps" in cpu
    line = re.search(r'class="line" d="([^"]+)"', cpu).group(1)
    assert line.count("M") >= 2  # two runs, not one line across the gap


def test_the_node_page_has_7_day_and_90_day_sparklines(site):
    feedNode(site, "grinder", 30)
    html = site.page("/tree/grinder")
    labels = sparkLabels(html)
    assert [x.split(":")[0] for x in labels] == [
        "CPU 7 days",
        "RAM 7 days",
        "disk 7 days",
        "CPU 90 days",
        "RAM 90 days",
        "disk 90 days",
    ]
    assert "last 7 days: CPU, RAM, disk" in html and "last 90 days: CPU, RAM, disk" in html


def test_a_sparkline_is_muted_never_a_state_colour(site):
    css = (__import__("pathlib").Path(__file__).parents[1] / "perch/windowsill/static/perch.css").read_text(
        encoding="utf-8"
    )
    rule = re.search(r"\.spark\{[^}]*\}", css).group(0)
    assert "var(--muted)" in rule
    assert "bl-" not in rule and "--hiss" not in rule and "--tailFlick" not in rule
    feedNode(site, "grinder", 30, disk=99.0)  # a nearly full disk
    html = site.page("/")
    for svg in re.findall(r'<svg class="spark".*?</svg>', html, re.S):
        assert "bl-" not in svg and "style=" not in svg  # the breach is the badge's business


def test_no_history_says_so_in_words(site):
    site.trail.setState(
        "node:grinder", B.slowBlink, detail={"mode": "ok", "cpu": 10, "mem": 20, "disk": 30}, seenAt=site.clock()
    )
    html = site.page("/")
    assert "No 24 h history yet." in html
    node = site.page("/tree/grinder")
    assert "No 7 days history yet." in node and "No 90 days history yet." in node


# -- the drawing itself ----------------------------------------------------------------------------


def test_columns_average_what_falls_in_them_and_leave_gaps_empty(clock):
    start = clock()
    pts = [(start + timedelta(minutes=m), v) for m, v in ((1, 10.0), (2, 30.0), (31, 50.0))]
    assert columns(pts, start, start + timedelta(minutes=40), 4) == [20.0, None, None, 50.0]


def test_the_path_breaks_at_a_gap_and_draws_a_lone_column_as_a_dot():
    d = path([10.0, 20.0, None, 50.0, None, 90.0, 95.0])
    assert d.count("M") == 3 and "h0" in d  # [10, 20] a line, [50] a dot, [90, 95] a line
    assert path([None, None]) == ""


def test_the_text_alternative_reads_like_the_spec():
    assert altText("RAM", "24 h", [41.2, 50.0, 62.8], 58.0) == "RAM 24 h: 41-63 %, now 58 %"
    assert altText("RAM", "24 h", [41.2, None, 62.8], None) == "RAM 24 h: 41-63 %, now 63 %, with gaps"
    assert altText("CPU", "7 days", [None, None], None) == "CPU 7 days: no history yet"


def test_a_sparkline_with_no_data_is_a_sentence_not_an_empty_box(clock):
    out = sparkline([], start=clock(), end=clock() + timedelta(hours=1), cols=10, label="CPU", span="24 h")
    assert "<svg" not in str(out) and "CPU 24 h: no history yet" in str(out)
