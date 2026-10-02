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

from perch.bodyLanguage import BodyLanguage as B
from perch.catTree import CatTree
from perch.collectors import Runner
from perch.meow import Meow, findProblems
from perch.scentTrail import ScentTrail
from perch.senses.purr import Purr
from perch.settings import Settings

settings = Settings.fromEnv()
trail = ScentTrail(settings.trailDb)
now = datetime.now(UTC)

# events from senses that arrive in later milestones (the trail page needs rows to show)
samples = [
    (0.4, "pounce", "app:percolator/paperless", B.earTwitch, "2 files dropped into consume/", None),
    (0.9, "whiskers", "app:mochaPot/homeassistant", B.earTwitch, 'automation "morning lights" ran', None),
    (3.0, "groom", "app:cellar/komodo", B.slowBlink, "freshness: every copy under 26 h", None),
    (5.5, "glare", "app:percolator/vaultwarden", B.slowBlink, "back: 200 · was down 3 min 30 s", "L6"),
    (5.6, "glare", "app:percolator/vaultwarden", B.hiss, "502 for 3 checks", "L6"),
    (26.0, "binocs", "node:sieve", B.earTwitch, "new upstream release: an image pinned in the repo", None),
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


clock = Clock(now - timedelta(minutes=8))
tree = CatTree(settings.repoDir)
fake = FleetFake(tree.fleet(), clock)
purr = Purr(fake.client(), trail, tree, clock=clock, every=30, tz=ZoneInfo(settings.tz))
runner = Runner(trail, [purr], clock=clock)
loop = asyncio.new_event_loop()


def look(cycles):
    for _ in range(cycles):
        loop.run_until_complete(runner.runOnce(purr))
        clock.advance(seconds=30)


look(8)  # four quiet minutes
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
loop.run_until_complete(purr.aclose())
loop.close()
trail.close()
print(f"seeded {len(samples)} sample events and 16 purr cycles into {settings.trailDb}")
