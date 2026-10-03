"""collectors: runs perch's senses on their rhythms and notices when one goes quiet.

"Silence is a signal" (design plan 3.4). Each collector (today only purr) has a rhythm; the
runner calls its ``cycle`` on that rhythm with a little jitter, and records whether it
succeeded. A separate watchdog compares each collector's last success with its rhythm:
late after 3 missed cycles (tailFlick), missing after 10 (hiss), with perch's own events
saying which and why. The watchdog doesn't depend on the collector running, so a hung or
dead one is noticed too.

The state ``collector:<name>`` goes into scentTrail, where the rollup counts it toward the
fleet: a watcher that has gone quiet is a problem the fleet has (rollup.py).
"""

from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Callable, Iterable
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Protocol
from zoneinfo import ZoneInfo

from .bodyLanguage import BodyLanguage as B
from .catTree import CatTree
from .rhythms import Rhythm
from .scentTrail import ScentTrail, isoUtc
from .scrub import scrub
from .senses.binocs import Binocs
from .senses.disks import Disks
from .senses.gatus import GatusClient
from .senses.glare import Glare
from .senses.komodo import KomodoClient
from .senses.purr import Purr
from .senses.registries import Registries
from .senses.scrutiny import ScrutinyClient
from .senses.speedtest import SpeedtestClient
from .senses.whiskers import Whiskers, loadConfig
from .settings import Settings
from .vitals import Vitals
from .words import duration

log = logging.getLogger("perch.collectors")


class Collector(Protocol):
    name: str
    rhythm: Rhythm

    async def cycle(self) -> None: ...

    async def aclose(self) -> None: ...


@dataclass
class _Health:
    startedAt: datetime
    lastOkAt: datetime | None = None
    lastError: str | None = None
    level: B | None = None
    levelSince: datetime | None = None


class Runner:
    def __init__(
        self,
        trail: ScentTrail,
        collectors: Iterable[Collector],
        *,
        clock: Callable[[], datetime],
        secrets: Iterable[str] = (),
        timeout: float | None = None,
        pause: Callable[[Collector], float] | None = None,
    ) -> None:
        self.trail = trail
        self.collectors = list(collectors)
        self.clock = clock
        self._secrets = [s for s in secrets if s]
        self._timeout = timeout
        self._pause = pause or self._jittered
        started = clock()
        self._health = {c.name: _Health(startedAt=started) for c in self.collectors}

    @staticmethod
    def _jittered(collector: Collector) -> float:
        return collector.rhythm.every * random.uniform(0.9, 1.1)  # noqa: S311 - spreading load, not security

    def _timeoutFor(self, collector: Collector) -> float:
        return self._timeout if self._timeout is not None else max(5.0, collector.rhythm.every * 2.0)

    # -- running ------------------------------------------------------------------------

    async def run(self) -> None:
        """Run every collector on its rhythm, and the watchdog, until cancelled."""
        self.check()
        tasks = [asyncio.create_task(self._loop(c)) for c in self.collectors]
        tasks.append(asyncio.create_task(self._watchdog()))
        try:
            await asyncio.gather(*tasks)
        finally:
            for task in tasks:
                task.cancel()
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _loop(self, collector: Collector) -> None:
        while True:
            await self.runOnce(collector)
            await asyncio.sleep(self._pause(collector))

    async def _watchdog(self) -> None:
        if not self.collectors:
            return
        while True:
            await asyncio.sleep(max(1.0, min(c.rhythm.every for c in self.collectors) / 3))
            self.check()

    async def runOnce(self, collector: Collector) -> None:
        """One scheduled cycle: success or failure is recorded, then the rhythm is judged."""
        health = self._health[collector.name]
        timeout = self._timeoutFor(collector)
        try:
            await asyncio.wait_for(collector.cycle(), timeout=timeout)
        except TimeoutError:
            self._failed(collector, health, f"the cycle took longer than {timeout:g} s")
        except Exception as exc:  # a collector failing must never stop the others or the page
            self._failed(collector, health, scrub(str(exc) or type(exc).__name__, self._secrets, limit=300))
        else:
            if health.lastError:
                log.info("%s is answering again", collector.name)
            health.lastOkAt, health.lastError = self.clock(), None
        self.check()

    def _failed(self, collector: Collector, health: _Health, why: str) -> None:
        if health.lastError is None:  # said once per outage, not once per cycle
            log.warning("%s failed: %s", collector.name, why)
        health.lastError = why

    # -- the watchdog -------------------------------------------------------------------

    def check(self) -> None:
        """Judge every collector against its rhythm; write its state and say what changed."""
        now = self.clock()
        for collector in self.collectors:
            health = self._health[collector.name]
            since = health.lastOkAt or health.startedAt
            level = collector.rhythm.level(since, now)
            if health.lastOkAt is None and level is B.slowBlink:
                level = B.unknown
            title = self._title(collector, health, level, now)
            self.trail.setState(
                f"collector:{collector.name}",
                level,
                title=title,
                seenAt=now,
                expectedRhythm=collector.rhythm.every,
                detail={
                    "lastOkAt": isoUtc(health.lastOkAt) if health.lastOkAt else None,
                    "lastError": health.lastError,
                    "every": collector.rhythm.every,
                },
            )
            if level is not health.level:
                self._announce(collector, health, level, title, now)
                health.level, health.levelSince = level, now

    def _title(self, collector: Collector, health: _Health, level: B, now: datetime) -> str:
        silent = duration((now - (health.lastOkAt or health.startedAt)).total_seconds())
        why = f". {health.lastError.rstrip('.')}." if health.lastError else ""
        if level is B.hiss:
            return f"{collector.name} is missing: no successful cycle for {silent}{why}"
        if level is B.tailFlick:
            return f"{collector.name} is late: no successful cycle for {silent}{why}"
        if level is B.unknown:
            return "waiting for the first cycle"
        return "on time"

    def _announce(self, collector: Collector, health: _Health, level: B, title: str, now: datetime) -> None:
        subject = f"collector:{collector.name}"
        if level.rank >= B.tailFlick.rank:
            self.trail.addEvent("perch", subject, level, title, seenAt=now)
        elif level is B.slowBlink and health.level and health.level.rank >= B.tailFlick.rank:
            lasted = duration((now - (health.levelSince or now)).total_seconds())
            text = f"{collector.name} is back (was {health.level.value} for {lasted})"
            self.trail.addEvent("perch", subject, B.slowBlink, text, seenAt=now)

    def report(self) -> dict[str, dict[str, Any]]:
        """For /healthz: where each collector stands."""
        return {
            name: {
                "level": h.level.value if h.level else None,
                "lastOkAt": isoUtc(h.lastOkAt) if h.lastOkAt else None,
                "lastError": h.lastError,
                "every": next(c.rhythm.every for c in self.collectors if c.name == name),
            }
            for name, h in self._health.items()
        }


def buildCollectors(settings: Settings, trail: ScentTrail, tree: CatTree, clock: Callable[[], datetime]) -> list[Any]:
    """The senses perch can start from its settings. A sense without a URL is simply not
    watching (its apps stay unknown); one half-configured says so on the trail, once."""
    collectors: list[Any] = []
    if settings.purrUrl:
        try:
            komodo = KomodoClient(settings.purrUrl, settings.purrKey, settings.purrSecret)
        except ValueError as exc:
            log.warning("purr is off: %s", exc)
            trail.addEvent("perch", "collector:purr", B.tailFlick, f"purr is switched off: {exc}")
        else:
            collectors.append(
                Purr(
                    komodo,
                    trail,
                    tree,
                    clock=clock,
                    every=settings.purrEvery,
                    sleepers=settings.sleepers,
                    tz=ZoneInfo(settings.tz),
                    vitals=Vitals(trail, clock),
                )
            )
    collectors += _outsideSenses(settings, trail, tree, clock)
    return collectors


def _outsideSenses(settings: Settings, trail: ScentTrail, tree: CatTree, clock: Callable[[], datetime]) -> list[Any]:
    """glare (Gatus), disks (Scrutiny), whiskers (Home Assistant) and binocs (speedtest, upstream releases): each
    starts only when its setting is there; one that is half set says so on the trail, once, and the rest carry on."""
    found: list[Any] = []
    if settings.glareUrl:
        try:
            found.append(
                Glare(
                    GatusClient(settings.glareUrl, settings.glareUser, settings.glarePassword),
                    trail,
                    clock=clock,
                    every=settings.glareEvery,
                )
            )
        except ValueError as exc:
            log.warning("glare is off: %s", exc)
            trail.addEvent("perch", "collector:glare", B.tailFlick, f"glare is switched off: {exc}")
    if settings.disksUrl:
        found.append(Disks(ScrutinyClient(settings.disksUrl), trail, clock=clock, every=settings.disksEvery))
    if settings.whiskersUrl or settings.whiskersToken:
        try:
            found.append(
                Whiskers(
                    settings.whiskersUrl,
                    settings.whiskersToken,
                    loadConfig(settings.whiskersEntities),
                    trail,
                    clock=clock,
                    every=settings.whiskersEvery,
                )
            )
        except ValueError as exc:  # also the entity list's ConfigError
            log.warning("whiskers is off: %s", exc)
            trail.addEvent("perch", "collector:whiskers", B.tailFlick, f"whiskers is switched off: {exc}")
    speedtest = None
    if settings.binocsSpeedtestUrl or settings.binocsSpeedtestToken:
        try:
            speedtest = SpeedtestClient(
                settings.binocsSpeedtestUrl, settings.binocsSpeedtestToken, tz=ZoneInfo(settings.tz)
            )
        except ValueError as exc:
            log.warning("binocs: no speedtest: %s", exc)
            trail.addEvent("perch", "collector:binocs", B.tailFlick, f"binocs can't check speedtest: {exc}")
    releases = settings.binocsReleasesEvery > 0
    if speedtest is not None or releases:
        found.append(
            Binocs(
                trail,
                tree,
                clock=clock,
                speedtest=speedtest,
                registries=Registries() if releases else None,
                releasesEvery=settings.binocsReleasesEvery,
                every=settings.binocsEvery,
            )
        )
    return found
