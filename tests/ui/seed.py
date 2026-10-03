"""Seed a throwaway scentTrail so the screenshots show real pages: sample events from the senses
that don't exist yet, and the live state of a small incident that the real purr and collector
runner produce from a fake Komodo (tests/komodoFake.py).

Run inside the perch container before perch starts (tests/ui/compose.yml). Sample data only:
fake names, no secrets, no hostnames.
"""

import asyncio
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from komodoFake import FleetFake
from outsideFakes import GatusFake, RegistryFake, ScrutinyFake, SpeedtestFake

from perch.bodyLanguage import BodyLanguage as B
from perch.catTree import CatTree
from perch.collectors import Runner
from perch.meow import Meow, findProblems
from perch.scentTrail import ScentTrail
from perch.senses.binocs import Binocs
from perch.senses.disks import Disks
from perch.senses.glare import Glare
from perch.senses.purr import Purr
from perch.senses.registries import parseImage
from perch.settings import Settings
from perch.vitals import Vitals

HOUSE = (  # whiskers' entities as Home Assistant reports them: (entity, name, level, the word, the state)
    ("binary_sensor.front_door", "Front door", B.earTwitch, "open", "on"),
    ("binary_sensor.kitchen_water_leak", "Kitchen leak sensor", B.slowBlink, "dry", "off"),
    ("binary_sensor.pet_fountain_low_water", "Water fountain", B.slowBlink, "full enough", "off"),
    ("sensor.ups_status", "UPS", B.tailFlick, "On Battery", "On Battery"),
)

settings = Settings.fromEnv()
trail = ScentTrail(settings.trailDb)
now = datetime.now(UTC)

LONG_RELEASE = "release/ghcr.io/example-organisation/an-image-name-with-no-break-points-at-all-for-the-wrap-check"
LONG_ENDPOINT = "a-deliberately-long-endpoint-name-with-no-break-points-at-all-for-the-wrap-check"
LONG_ENDPOINT_KEY = f"apps_{LONG_ENDPOINT}"

# events from senses that arrive in later milestones (the trail page needs rows to show)
samples = [
    (0.4, "pounce", "app:percolator/paperless", B.earTwitch, "2 files dropped into consume/", None),
    (0.9, "whiskers", "app:mochaPot/homeassistant", B.earTwitch, 'automation "morning lights" ran', None),
    (3.0, "groom", "app:cellar/komodo", B.slowBlink, "freshness: every copy under 26 h", None),
    (5.5, "glare", "app:percolator/vaultwarden", B.slowBlink, "back: 200 · was down 3 min 30 s", "L6"),
    (5.6, "glare", "app:percolator/vaultwarden", B.hiss, "502 for 3 checks", "L6"),
    (26.0, "binocs", "node:sieve", B.earTwitch, "new upstream release: an image pinned in the repo", None),
    # the longest subjects perch can show: no break points at all, as real release and endpoint names are
    # (M5 task 0: a phone must not scroll sideways because of them, whatever the font is)
    (0.2, "binocs", LONG_RELEASE, B.earTwitch, "newer release: 10.20.30-flavour is out (pinned 10.19.2-flavour)", None),
]
for hoursAgo, sense, subject, level, title, litter in samples:
    trail.addEvent(sense, subject, level, title, litterId=litter, seenAt=now - timedelta(hours=hoursAgo))


class Clock:
    """Time that moves only when told, so eight minutes of purr cycles take no time at all."""

    def __init__(self, start):
        self.now = start

    def __call__(self):
        return self.now

    def advance(self, **delta):
        self.now += timedelta(**delta)


# A week of vitals history (M4): a daily rhythm per node, and a stretch where perch saw nothing at all
# (cellar, 30 to 26 hours ago), so the sparklines show a real shape and a real gap. Hourly rows come from the
# same code that rolls them up in production.
history = Vitals(trail, lambda: now)
BASE = {"sieve": (8, 31), "percolator": (22, 48), "cellar": (14, 55), "mochaPot": (11, 38), "grinder": (35, 52)}
for node, (cpu0, mem0) in BASE.items():
    moment = now - timedelta(days=8)
    while moment < now - timedelta(minutes=8):
        hoursAgo = (now - moment).total_seconds() / 3600
        if not (node == "cellar" and 26 <= hoursAgo <= 30):
            wave = ((moment.hour - 4) % 24) / 24  # busier in the evening
            history.add(node, moment, cpu0 + 25 * wave + (moment.minute % 7), mem0 + 8 * wave, 61 + hoursAgo / 200)
        moment += timedelta(minutes=5)

clock = Clock(now - timedelta(minutes=8))
tree = CatTree(settings.repoDir)
fake = FleetFake(tree.fleet(), clock)
purr = Purr(fake.client(), trail, tree, clock=clock, every=30, tz=ZoneInfo(settings.tz), vitals=Vitals(trail, clock))
runner = Runner(trail, [purr], clock=clock)
loop = asyncio.new_event_loop()


def look(cycles):
    for _ in range(cycles):
        loop.run_until_complete(runner.runOnce(purr))
        clock.advance(seconds=30)


look(8)  # four quiet minutes
outside = Clock(now - timedelta(minutes=30))  # glare, disks and binocs read fakes of Gatus, Scrutiny and the rest
fake.exit("grinder", "n8n", 137)  # the incident
fake.crashloop("grinder", "traccar")
fake.vitals("grinder", cpu=63.0, mem=91.0)
fake.vitals("cellar", disk=88.0)
fake.nodeDown("roastery")  # asleep, or a hiss, depending on the hour the check runs
fake.add("grinder", "stray-test", project=None)
look(8)
# meow reads what purr wrote into litters (no push channel is set here: the Alerts card still lists them)
meow = Meow(trail, tree, clock=clock, tz=ZoneInfo(settings.tz))
meow.reconcile(clock(), findProblems(trail.states(), tree.fleet()))
gatus = GatusFake(outside)
for name, group in (
    ("cloudflare tunnel", "network"),
    ("pihole", "network"),
    ("ntfy", "network"),
    ("authelia", "identity"),
    ("vaultwarden", "apps"),
    ("nextcloud", "apps"),
    (LONG_ENDPOINT, "apps"),
):
    gatus.add(name, group)
glare = Glare(gatus.client(), trail, clock=outside)
for _ in range(12):
    gatus.tick()
    loop.run_until_complete(glare.cycle())
for _ in range(2):  # vaultwarden and the long-named endpoint fail twice: tailFlick
    gatus.check("apps_vaultwarden", up=False, why="HTTP 502")
    gatus.check(LONG_ENDPOINT_KEY, up=False, why="HTTP 503: " + "no-break-points-in-this-reason-either-" * 2)
    outside.advance(seconds=60)
    loop.run_until_complete(glare.cycle())

scrutiny = ScrutinyFake(outside)
scrutiny.add(
    "0x5000cca000000001", "sda", "cellar", "WDC WD40EFRX", temp=36, summaryHours=3, attrs={"9": scrutiny.attr(9, 20000)}
)
scrutiny.add(
    "0x5000cca000000002",
    "sdb",
    "cellar",
    "Seagate IronWolf",
    temp=41,
    attrs={"9": scrutiny.attr(9, 31000), "5": scrutiny.attr(5, 9, status=2)},
)
scrutiny.add(
    "0x5002538000000003",
    "nvme0n1",
    "grinder",
    "Samsung 990 PRO",
    protocol="NVMe",
    temp=47,
    attrs={"power_on_hours": {"attribute_id": "power_on_hours", "value": 4321, "thresh": -1, "status": 0}},
)
disks = Disks(scrutiny.client(), trail, clock=outside)
loop.run_until_complete(disks.cycle())

speed, registry = SpeedtestFake(outside), RegistryFake()
for node in tree.fleet().nodes:
    for app in node.apps:
        for ref in app.images:
            image = parseImage(ref)
            if image:
                registry.tags.setdefault(image.key, []).append(image.tag)
registry.tags["registry-1.docker.io/n8nio/n8n"].append("2.40.0")
registry.tags["ghcr.io/moghtech/komodo-core"].append("2.4.0")


async def nap():
    return None


binocs = Binocs(
    trail,
    tree,
    clock=outside,
    speedtest=speed.client(),
    registries=registry.client(),
    releasesEvery=7 * 86400,
    pause=nap,
)
loop.run_until_complete(binocs.cycle())
for entity, name, level, word, state in HOUSE:  # what whiskers keeps from a Home Assistant (no real one is ever asked)
    trail.setState(
        f"whiskers:{entity}",
        level,
        title=f"{name}: {word}",
        seenAt=now,
        detail={"entity": entity, "name": name, "state": state, "word": word, "level": level.value},
    )
for name in ("glare", "disks", "binocs", "whiskers"):  # what the runner writes for a collector that is on time
    trail.setState(f"collector:{name}", B.slowBlink, title="on time", seenAt=now)
for closing in (glare, disks, binocs):
    loop.run_until_complete(closing.aclose())

loop.run_until_complete(purr.aclose())
loop.close()
trail.close()
print(
    f"seeded {len(samples)} sample events, 16 purr cycles, a week of vitals, glare, disks, binocs and whiskers "
    f"into {settings.trailDb}"
)
