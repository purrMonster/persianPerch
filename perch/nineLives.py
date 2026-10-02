"""nineLives: the outside heartbeat (design plan 8, 05 plan M3).

Every 5 minutes, and **only while every collector is on time**, perch pings its healthchecks.io check
(``PERCH_NINELIVES_URL``). A collector that is late or missing, or perch itself stopping, means no ping,
so healthchecks.io alerts from outside once its grace time is up: it can see what perch can't, like
cellar being dead. There is no ``/fail`` ping on purpose: silence is the signal, and perch can't be
trusted to report its own death.

Built against healthchecks.io's pinging API (healthchecks.io/docs/http_api, read 2026-10-02): a GET to
``https://hc-ping.com/<uuid>`` answers ``200 OK``; the check's period and grace time decide when a missing
ping becomes an alert. The URL is a secret (anyone holding it can mark the check up): it is never
logged, shown or put in an event, and no message here repeats it.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any
from urllib.parse import urlsplit

import httpx2

from .bodyLanguage import BodyLanguage as B
from .scentTrail import ScentTrail, State, isoUtc, parseUtc
from .words import duration

log = logging.getLogger("perch.nineLives")

SUBJECT = "ninelives"  # not a collector: its own state never rolls up into the fleet's
EVERY = 300  # seconds between pings
LOOK = 30  # seconds between looks at the collectors


class NineLives:
    def __init__(
        self,
        url: str,
        runner: Any,
        trail: ScentTrail,
        *,
        clock: Callable[[], datetime],
        every: int = EVERY,
        transport: "httpx2.AsyncBaseTransport | None" = None,
        timeout: float = 10.0,
    ) -> None:
        parts = urlsplit(url)
        if parts.scheme not in ("http", "https") or not parts.netloc:
            raise ValueError("PERCH_NINELIVES_URL must be an http(s) URL")
        self._url = url
        self.runner = runner
        self.trail = trail
        self.clock = clock
        self.every = every
        self.lastPingAt: datetime | None = None
        self._level: B | None = None
        self._http = httpx2.AsyncClient(
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)), transport=transport, follow_redirects=False
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def run(self) -> None:
        while True:
            await self.step()
            await asyncio.sleep(LOOK)

    # -- one look ---------------------------------------------------------------------------------

    def notOnTime(self) -> list[str]:
        """Which collectors are not on time (late, missing, or have yet to finish a first cycle)."""
        self.runner.check()
        return sorted(name for name, health in self.runner.report().items() if health["level"] != B.slowBlink.value)

    async def step(self) -> None:
        now = self.clock()
        behind = self.notOnTime()
        if behind:
            self._say(now, *self._holdingBack(behind))
            return
        if self.lastPingAt is not None and (now - self.lastPingAt).total_seconds() < self.every:
            return
        try:
            response = await self._http.get(self._url)
        except httpx2.TimeoutException:
            self._say(now, B.tailFlick, "can't reach its endpoint: timed out")
            return
        except httpx2.HTTPError:
            self._say(now, B.tailFlick, "can't reach its endpoint")
            return
        if response.status_code != 200:
            self._say(now, B.tailFlick, f"its endpoint answered HTTP {response.status_code}")
            return
        self.lastPingAt = now
        self._say(now, B.slowBlink, "pinged just now")

    def _holdingBack(self, behind: list[str]) -> tuple[B, str]:
        report = self.runner.report()
        if all(report[n]["level"] in (None, B.unknown.value) for n in behind):
            return B.unknown, "waiting for the first cycle of " + ", ".join(behind)
        return B.tailFlick, "holding its ping back: " + ", ".join(behind) + " not on time"

    # -- what the footer says -------------------------------------------------------------------------

    def _say(self, now: datetime, level: B, title: str) -> None:
        self.trail.setState(
            SUBJECT,
            level,
            title=title,
            seenAt=now,
            detail={"lastPingAt": isoUtc(self.lastPingAt) if self.lastPingAt else None, "every": self.every},
        )
        if level is not self._level:
            if level.rank >= B.tailFlick.rank:
                self.trail.addEvent("perch", SUBJECT, level, f"nineLives {title}", seenAt=now)
            elif level is B.slowBlink and self._level is not None and self._level.rank >= B.tailFlick.rank:
                self.trail.addEvent("perch", SUBJECT, B.slowBlink, "nineLives is pinging again", seenAt=now)
            self._level = level


def footerLine(state: State | None, now: datetime, configured: bool) -> tuple[B, str]:
    """(level, words) for the page footer: "nineLives pinged 2 min ago", "nineLives off", ..."""
    if state is None:
        return B.unknown, "nineLives not yet" if configured else "nineLives off (no ping URL set)"
    last = (state.detail or {}).get("lastPingAt")
    if state.bodyLanguage is B.slowBlink and last:
        return B.slowBlink, f"nineLives pinged {duration((now - parseUtc(last)).total_seconds())} ago"
    return state.bodyLanguage, f"nineLives {state.title}"
