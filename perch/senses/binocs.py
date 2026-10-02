"""binocs: the outside web (design plan 4.6, 05 plan M4, C7, C8).

Three things, and **none of them is ever worse than earTwitch**: they are things to know, not things on fire.
(An actual tunnel outage is glare's: the tunnel is a Gatus check, so a down tunnel is a hiss there.)

- **tunnel** (C7): not a request. cloudflared's metrics aren't reachable from cellar, so binocs shows what
  Gatus's own ``/ready`` check for the tunnel says: the glare state ``glare:network_cloudflare-tunnel``
  (``TUNNEL_KEY``, the key of the fleet's Gatus endpoint ``cloudflare tunnel`` in group ``network``).
  The page reads it (``Status.tunnel``); binocs writes nothing for it.
- **speedtest** (C8): the newest result of speedtest-tracker on grinder, every cycle (15 min). A failed test, a
  result the tracker itself calls unhealthy, or no test for 6 hours is earTwitch; unreachable is ``unknown``.
- **releases** (weekly, ``PERCH_BINOCS_RELEASES_EVERY``; **off unless that is set**, so nothing reaches a public
  registry by accident): for every image pinned in the fleet repo's compose files, is a newer release out?
  A newer one is an earTwitch state ``binocs:release/<repo>`` that meow lists in the morning digest; once the
  pin catches up the state is forgotten. Which images could be compared, how many, when, and why not (a line
  pin, a moving tag, a rate limit) is kept as one summary in scentTrail's ``meta`` for the page.

A rate limit (HTTP 429) stops the run and retries after the registry's ``Retry-After``; the images already
read keep their answers. One image failing doesn't stop the others.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from datetime import datetime, timedelta
from typing import Any

from ..bodyLanguage import BodyLanguage as B
from ..catTree import CatTree
from ..rhythms import Rhythm
from ..scentTrail import ScentTrail, isoUtc, parseUtc
from ..words import duration
from .registries import Image, RegistryError, newestRelease, parseImage, parseTag
from .speedtest import SpeedtestError

TUNNEL_KEY = "network_cloudflare-tunnel"
SPEEDTEST_STALE = timedelta(hours=6)
RELEASE_PREFIX = "binocs:release/"
META_RELEASES = "binocs.releases"
META_RETRY = "binocs.releases.retryAt"


class Binocs:
    name = "binocs"

    def __init__(
        self,
        trail: ScentTrail,
        tree: CatTree,
        *,
        clock: Callable[[], datetime],
        speedtest: Any = None,
        registries: Any = None,
        releasesEvery: int = 0,
        every: int = 900,
        pause: Callable[[], Awaitable[None]] | None = None,
    ) -> None:
        self.trail = trail
        self.tree = tree
        self.clock = clock
        self.speedtest = speedtest
        self.registries = registries
        self.releasesEvery = releasesEvery
        self.rhythm = Rhythm(every=every)
        self._pause = pause or (lambda: asyncio.sleep(1.0))

    async def aclose(self) -> None:
        for client in (self.speedtest, self.registries):
            if client is not None:
                await client.aclose()

    async def cycle(self) -> None:
        now = self.clock()
        if self.speedtest is not None:
            await self._speedtest(now)
        if self.registries is not None and self.releasesEvery > 0 and self._due(now):
            await self._releases(now)

    # -- speedtest -----------------------------------------------------------------------

    async def _speedtest(self, now: datetime) -> None:
        subject = "binocs:speedtest"
        try:
            result = await self.speedtest.latest()
        except SpeedtestError as exc:
            self.trail.setState(subject, B.unknown, title=str(exc), seenAt=now)
            return
        before = self.trail.states().get(subject)
        if result is None:
            level, title, detail = B.unknown, "speedtest-tracker has no result yet", {}
        else:
            detail = {
                "status": result.status,
                "healthy": result.healthy,
                "pingMs": result.pingMs,
                "downMbit": result.downMbit,
                "upMbit": result.upMbit,
                "at": isoUtc(result.at),
            }
            age = now - result.at
            if result.status == "failed":
                level, title = B.earTwitch, "the last speedtest failed"
            elif result.status != "completed" and age > SPEEDTEST_STALE:
                level, title = B.earTwitch, f"no finished speedtest for {duration(age.total_seconds())}"
            elif age > SPEEDTEST_STALE:
                level, title = B.earTwitch, f"no new speedtest for {duration(age.total_seconds())}"
            elif result.healthy is False:
                level, title = B.earTwitch, self._line(result) + ", below the thresholds speedtest-tracker is set to"
            else:
                level, title = B.slowBlink, self._line(result)
        self.trail.setState(subject, level, title=title, detail=detail, seenAt=now)
        if level is B.earTwitch and (before is None or before.bodyLanguage is not B.earTwitch):
            self.trail.addEvent("binocs", subject, level, f"speedtest: {title}", detail=detail, seenAt=now)

    @staticmethod
    def _line(result) -> str:
        down = f"{result.downMbit:g}" if result.downMbit is not None else "?"
        up = f"{result.upMbit:g}" if result.upMbit is not None else "?"
        ping = f"{result.pingMs:g}" if result.pingMs is not None else "?"
        return f"down {down} Mbit/s, up {up} Mbit/s, ping {ping} ms"

    # -- releases ------------------------------------------------------------------------

    def _due(self, now: datetime) -> bool:
        retry = self.trail.meta(META_RETRY)
        if retry:  # a registry said wait: not before then, and then at once, not a week later
            return parseUtc(retry) <= now
        last = self.trail.meta(META_RELEASES)
        if not last:
            return True
        try:
            at = parseUtc(json.loads(last)["checkedAt"])
        except (ValueError, KeyError):
            return True
        return now - at >= timedelta(seconds=self.releasesEvery)

    def _pinned(self) -> tuple[dict[str, list[Image]], list[str]]:
        """Every comparable pin of the fleet, by repository; and the refs that can't be compared."""
        byRepo: dict[str, list[Image]] = {}
        skipped: list[str] = []
        seen: set[str] = set()
        for node in self.tree.fleet().nodes:
            for app in node.apps:
                for ref in app.images:
                    if ref in seen:
                        continue
                    seen.add(ref)
                    image = parseImage(ref)
                    if image is None:
                        skipped.append(ref)
                    else:
                        byRepo.setdefault(image.key, []).append(image)
        return byRepo, skipped

    def _usedBy(self, ref: str) -> list[str]:
        return sorted(
            f"{node.name}/{app.name}" for node in self.tree.fleet().nodes for app in node.apps if ref in app.images
        )

    async def _releases(self, now: datetime) -> None:
        byRepo, skipped = self._pinned()
        before = {s for s in self.trail.states() if s.startswith(RELEASE_PREFIX)}
        keep: set[str] = set()
        checked = current = failed = 0
        stoppedBy: str | None = None
        retryAfter = 0
        for _repo, images in sorted(byRepo.items()):
            try:
                tags = await self.registries.tags(images[0])
            except RegistryError as exc:
                failed += len(images)
                if exc.retryAfter is not None:
                    stoppedBy, retryAfter = str(exc), exc.retryAfter
                    break
                continue
            for image in images:
                checked += 1
                pinned = parseTag(image.tag)
                newest = newestRelease(pinned, tags) if pinned else None
                if newest is None:
                    current += 1
                    continue
                subject = (
                    RELEASE_PREFIX
                    + image.repo.removeprefix("library/")
                    + (f"-{pinned.flavour}" if pinned.flavour else "")
                )
                keep.add(subject)
                detail = {
                    "image": image.ref,
                    "pinned": pinned.text(),
                    "newest": newest.text(),
                    "usedBy": self._usedBy(image.ref),
                }
                name = image.ref.rpartition(":")[0].removeprefix("lscr.io/")
                title = f"{name} {pinned.text()} is pinned, {newest.text()} is out"
                if subject not in before:
                    self.trail.addEvent("binocs", subject, B.earTwitch, title, detail=detail, seenAt=now)
                self.trail.setState(subject, B.earTwitch, title=title, detail=detail, seenAt=now)
            await self._pause()
        if stoppedBy is None:  # a finished run knows which pins caught up; an interrupted one doesn't
            self.trail.forget(before - keep)
        summary = {
            "checkedAt": isoUtc(now),
            "images": checked,
            "current": current,
            "newer": len(keep),
            "skipped": len(skipped),
            "failed": failed,
            "stopped": stoppedBy,
        }
        self.trail.execute("INSERT OR REPLACE INTO meta VALUES (?,?)", (META_RELEASES, json.dumps(summary)))
        if stoppedBy is not None:
            self.trail.execute(
                "INSERT OR REPLACE INTO meta VALUES (?,?)", (META_RETRY, isoUtc(now + timedelta(seconds=retryAfter)))
            )
        else:
            self.trail.execute("DELETE FROM meta WHERE key = ?", (META_RETRY,))

    # -- for the page ---------------------------------------------------------------------

    def releasesSummary(self) -> dict[str, Any] | None:
        return releasesSummary(self.trail)


def releasesSummary(trail: ScentTrail) -> dict[str, Any] | None:
    raw = trail.meta(META_RELEASES)
    try:
        return json.loads(raw) if raw else None
    except ValueError:
        return None
