"""Seed a throwaway scentTrail with sample events so the screenshots show real rows.

Run inside the perch container before perch starts (tests/ui/compose.yml). Sample
data only: fake titles, no secrets, no hostnames.
"""

from datetime import UTC, datetime, timedelta

from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import ScentTrail
from perch.settings import Settings

settings = Settings.fromEnv()
trail = ScentTrail(settings.trailDb)
now = datetime.now(UTC)
samples = [
    (0.2, "purr", "app:grinder/n8n", B.tailFlick, "restarted (exit 137, out of memory) · 2nd in 15 min", "L7"),
    (0.4, "pounce", "app:percolator/paperless", B.earTwitch, "2 files dropped into consume/", None),
    (0.9, "whiskers", "app:mochaPot/homeassistant", B.earTwitch, 'automation "morning lights" ran', None),
    (3.0, "groom", "app:cellar/komodo", B.slowBlink, "freshness: every copy under 26 h", None),
    (5.5, "glare", "app:percolator/vaultwarden", B.slowBlink, "back: 200 · was down 3 min 30 s", "L6"),
    (5.6, "glare", "app:percolator/vaultwarden", B.hiss, "502 for 3 checks", "L6"),
    (26.0, "binocs", "node:sieve", B.earTwitch, "new upstream release: an image pinned in the repo", None),
]
for hoursAgo, sense, subject, level, title, litter in samples:
    trail.addEvent(sense, subject, level, title, litterId=litter, seenAt=now - timedelta(hours=hoursAgo))
trail.close()
print(f"seeded {len(samples)} sample events into {settings.trailDb}")
