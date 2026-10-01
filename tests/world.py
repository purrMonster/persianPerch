"""A small world for scenario tests: a fake Komodo built from the pinned fleet repo, a fake
clock, purr, and a scentTrail, with helpers to step time and read what purr wrote."""

import asyncio
from datetime import UTC, datetime
from zoneinfo import ZoneInfo

from komodoFake import FleetFake

from perch.rollup import Status
from perch.scentTrail import ScentTrail
from perch.senses.komodo import KomodoError
from perch.senses.purr import Purr

IST = ZoneInfo("Asia/Kolkata")
# conftest's clock starts at 07:00 IST: outside roastery's 01:25-04:25 wake window
IN_WINDOW_WAKE = datetime(2026, 9, 28, 19, 55, tzinfo=UTC)  # 01:25 IST on the 29th


class World:
    def __init__(self, fleetTree, tmp_path, clock):
        self.clock = clock
        self.fleet = fleetTree.fleet()
        self.fake = FleetFake(self.fleet, clock)
        self.trail = ScentTrail(tmp_path / "t.db", clock=clock)
        self.purr = Purr(self.fake.client(), self.trail, fleetTree, clock=clock, every=30, tz=IST)
        self.loop = asyncio.new_event_loop()

    def cycle(self, n=1):
        """n purr cycles, 30 s apart. Returns the error of the last one, if Komodo couldn't be read."""
        error = None
        for _ in range(n):
            error = None
            try:
                self.loop.run_until_complete(self.purr.cycle())
            except KomodoError as exc:
                error = exc
            self.clock.advance(seconds=30)
        return error

    def status(self):
        return Status(self.fleet, self.trail)

    def state(self, subject):
        return self.trail.states()[subject]

    def events(self, subject=None):
        found = self.trail.events(subjectPrefix=subject) if subject else self.trail.events()
        return list(reversed(found))  # oldest first

    def close(self):
        self.loop.run_until_complete(self.purr.aclose())
        self.loop.close()
        self.trail.close()
