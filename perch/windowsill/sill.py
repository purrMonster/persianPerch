"""sill: what every windowsill route shares (the refactor of 2026-10-14). One ``Sill`` per app holds perch's
parts (the trail, catTree, groom, meow, the litters), the templates, and the helpers that turn them into what a
page shows. The routes live in ``pages``, ``stream``, ``reports`` and ``acks``; ``app.createApp`` builds the Sill
and wires everything. Nothing here writes: the three write routes are in ``reports`` and ``acks`` (test S7).
"""

from __future__ import annotations

import hashlib
import secrets
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates

from .. import ack as ackTokens
from ..bodyLanguage import LEVELS, BodyLanguage, worstOf
from ..catTree import CatTree, CatTreeError, Fleet
from ..collectors import Runner
from ..litters import Litters
from ..meow import Meow
from ..nineLives import NineLives, footerLine
from ..rollup import Status
from ..scentTrail import SENSES, ScentTrail, parseUtc
from ..senses.binocs import releasesSummary
from ..senses.groom import Groom
from ..senses.pounce import Pounce
from ..senses.purr import DISK_CRIT, DISK_WARN
from ..settings import Settings
from ..vitals import Vitals
from ..words import duration
from .spark import sparkline

HERE = Path(__file__).parent
VITALS = (("cpu", "CPU"), ("mem", "RAM"), ("disk", "disk"))

SENSE_MEANING = {
    "purr": "containers, node vitals, drive health",
    "pounce": "filesystem drops",
    "whiskers": "smart-home events",
    "glare": "endpoints",
    "binocs": "the outside web",
    "groom": "backups",
    "perch": "perch itself",
}

Built = tuple[dict, str, str]  # a live region's context, its signature, and the sentence it would announce


def glue(text: str) -> str:
    """Keep a number with its unit ("36 s", "1 h 10 min"): no line break inside it."""
    return text.replace(" ", " ")


def digest(parts: list[str]) -> str:
    """What a client last saw, in 12 characters: the levels a person would be told about."""
    return hashlib.blake2b("|".join(parts).encode(), digest_size=6).hexdigest()


def trailFilters(sense: list[str], level: list[str]) -> tuple[list[str], list[str]]:
    """The trail's filters, from the address: the page and its live stream read them the same way."""
    senses = [s for s in sense if s in SENSES] or list(SENSES)
    levels = [lv for lv in level if lv in BodyLanguage.__members__] or [lv.value for lv in LEVELS]
    return senses, levels


@dataclass
class Sill:
    settings: Settings
    trail: ScentTrail
    tree: CatTree
    clock: Callable[[], datetime]
    tz: ZoneInfo
    groomer: Groom
    meow: Meow
    runner: Runner
    nineLives: NineLives | None
    store: Litters = field(init=False)
    pouncer: Pounce = field(init=False)
    history: Vitals = field(init=False)
    templates: Jinja2Templates = field(init=False)
    csrfKey: str = field(init=False)

    def __post_init__(self) -> None:
        self.store = Litters(self.trail)
        self.pouncer = Pounce(self.trail)
        self.history = Vitals(self.trail, self.clock)  # reads only: purr's own instance writes
        # the page's CSRF key (ADR 0005); per process if unset
        self.csrfKey = self.settings.ackSecret or secrets.token_hex(32)
        self.templates = Jinja2Templates(directory=HERE / "templates")
        env = self.templates.env
        env.globals.update(BodyLanguage=BodyLanguage, LEVELS=LEVELS, SENSES=SENSES, SENSE_MEANING=SENSE_MEANING)
        env.globals.update(
            purrPill=self.purrPill,
            unknownNote=self.unknownNote,
            diskLevel=self.diskLevel,
            nineLivesLine=self.nineLivesLine,
        )
        env.filters["local"] = lambda moment, fmt="%H:%M": moment.astimezone(self.tz).strftime(fmt) if moment else "-"
        env.filters["bl"] = BodyLanguage.parse
        env.filters["ago"] = (
            lambda moment: glue(duration((self.clock() - moment).total_seconds())) if moment else "never"
        )
        env.filters["span"] = lambda seconds: glue(duration(seconds)) if seconds is not None else "-"

    # -- reading the fleet ----------------------------------------------------------------------------------------

    def fleetOr503(self) -> Fleet:
        try:
            return self.tree.fleet()
        except CatTreeError as exc:
            raise HTTPException(503, f"catTree can't read the fleet repo: {exc}") from exc

    def look(self) -> tuple[Fleet, Status]:
        """The fleet and its state, as of now: what almost every page starts from."""
        fleet = self.fleetOr503()
        return fleet, Status(fleet, self.trail)

    def readTracked(self, fleet: Fleet, path: str) -> str:
        if path not in fleet.files:
            return ""
        try:
            return self.tree.read(path, fleet)
        except CatTreeError:
            return ""

    # -- rendering ------------------------------------------------------------------------------------------------

    def render(self, request: Request, name: str, page: str, **context) -> HTMLResponse:
        fleet = context.get("fleet") or self.fleetOr503()
        status = context.get("status") or Status(fleet, self.trail)
        context.update(fleet=fleet, status=status, page=page, now=self.clock())
        return self.templates.TemplateResponse(request, name, context)

    def liveFragment(self, request: Request, kind: str, status: Status, built: Built, seen: str) -> HTMLResponse:
        """The region, the header's live bits, and one sentence when the client's last-seen state is stale."""
        context, signature, said = built
        context.update(
            fleet=status.fleet,
            status=status,
            now=self.clock(),
            signature=signature,
            region=f"live/{kind}.html",
            announce=said if seen and seen != signature else None,
        )
        return self.templates.TemplateResponse(request, "live/fragment.html", context)

    # -- what the header, the footer and the cards say ------------------------------------------------------------

    def sparks(self, nodeName: str, live: dict | None, *, span: str, table: str, delta: timedelta, cols: int) -> dict:
        """CPU, RAM and disk of a node as three sparklines over the last ``delta`` (docs/06 6): from the
        5-minute rows (``table="5m"``) or the hourly ones. ``live`` carries the latest readings for "now"."""
        end = self.clock()
        rows = self.history.rows(nodeName, table=table, since=end - delta, until=end)
        live = live or {}
        drawn = {
            key: sparkline(
                [(r.at, getattr(r, key)) for r in rows],
                start=end - delta,
                end=end,
                cols=cols,
                label=label,
                span=span,
                now=live.get(key),
            )
            for key, label in VITALS
        }
        return {**drawn, "any": any("<svg" in str(v) for v in drawn.values())}

    def releasesInfo(self) -> dict | None:
        found = releasesSummary(self.trail)
        if not found:
            return None
        try:
            return {**found, "at": parseUtc(found["checkedAt"])}
        except (KeyError, ValueError):
            return None

    def purrPill(self, status: Status) -> dict:
        """The header's "purr 12 s ago": what purr is doing, how stale its last look is, and a
        sentence for the overview. Words carry the severity; the dot only repeats it."""
        state = status.collectors().get("purr")
        if state is None:
            why = "PERCH_PURR_URL, PERCH_PURR_KEY and PERCH_PURR_SECRET aren't all set"
            return {
                "level": BodyLanguage.unknown,
                "text": "purr off",
                "title": f"purr isn't watching: {why}",
                "summary": "purr isn't watching yet",
            }
        last = (state.detail or {}).get("lastOkAt")
        if not last and state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
            word = "missing" if state.bodyLanguage is BodyLanguage.hiss else "late"
            return {
                "level": state.bodyLanguage,
                "text": f"purr {word}, no answer yet",
                "title": state.title or "",
                "summary": "purr hasn't had an answer from Komodo yet",
            }
        if not last:
            return {
                "level": state.bodyLanguage,
                "text": "purr starting",
                "title": "waiting for purr's first look at Komodo",
                "summary": "waiting for purr's first look",
            }
        age = glue(duration((self.clock() - parseUtc(last)).total_seconds()))
        word = {BodyLanguage.tailFlick: "late, ", BodyLanguage.hiss: "missing, "}.get(state.bodyLanguage, "")
        return {
            "level": state.bodyLanguage,
            "text": f"purr {word}{age} ago",
            "title": state.title or "",
            "summary": f"purr looked {age} ago",
        }

    def unknownNote(self, status: Status, unknown: int) -> str | None:
        """Why some apps are grey, in a sentence; None when none are."""
        if not unknown:
            return None
        pill = self.purrPill(status)
        state = status.collectors().get("purr")
        many = unknown != 1
        head = f"{unknown} {'apps' if many else 'app'} unknown"
        if state is None:
            return f"{head}: purr isn't configured (set PERCH_PURR_URL, PERCH_PURR_KEY and PERCH_PURR_SECRET)."
        if pill["text"] == "purr starting":
            return f"{head}: waiting for purr's first look."
        if state.bodyLanguage.rank >= BodyLanguage.tailFlick.rank:
            return f"{head}: purr can't see {'them' if many else 'it'}. {state.title}"
        return f"{head}: Komodo doesn't list {'their' if many else 'its'} containers."

    @staticmethod
    def diskLevel(disk: float) -> BodyLanguage | None:
        """The level a full disk earns (purr's own thresholds), for tinting its bar."""
        return BodyLanguage.hiss if disk >= DISK_CRIT else BodyLanguage.tailFlick if disk >= DISK_WARN else None

    def nineLivesLine(self, status: Status | None) -> dict:
        """The footer's "nineLives pinged 2 min ago": words first, the dot only repeats them."""
        state = status.states.get("ninelives") if status else None
        level, text = footerLine(state, self.clock(), configured=self.nineLives is not None)
        return {"level": level, "text": text}

    def alertsView(self, now: datetime) -> dict:
        """The overview's Alerts card: what meow is telling the owner about, and what it is holding."""
        items = []
        for lt in sorted(self.store.open(), key=lambda x: (-x.level.rank, x.openedAt)):
            if lt.level.rank < BodyLanguage.tailFlick.rank:
                continue
            if lt.ackedAt:
                how = f"acknowledged {lt.ackedAt.astimezone(self.tz):%H:%M} {lt.ackedVia or ''}".strip()
            elif lt.heldAt:
                how = "held back by the rate limit; it goes out as the limit allows"
            elif lt.digest and not lt.digestedAt:
                how = f"waiting for the {self.meow.digestAt:%H:%M} digest (quiet hours)"
            elif lt.pushes and lt.lastPushAt:
                ago = glue(duration((now - lt.lastPushAt).total_seconds()))
                how = f"pushed {lt.pushes} {'time' if lt.pushes == 1 else 'times'}, last {ago} ago"
            else:
                how = "not pushed yet"
            csrf = None if lt.ackedAt else ackTokens.csrfMint(self.csrfKey, lt.litterId, now)
            items.append({"litter": lt, "how": how, "csrf": csrf})
        return {
            "configured": self.meow.configured,
            "items": items,
            "held": len(self.store.held()),
            "digest": len(self.store.pendingDigest()),
            "quiet": f"{self.meow.quiet[0]:%H:%M} to {self.meow.quiet[1]:%H:%M}",
        }

    def lastNightSummary(self, now: datetime) -> dict:
        """Last night's backups, for the overview and the groom page: the cells, their worst level, how many were
        fine."""
        lastNight = self.groomer.lastNight(now)
        return {
            "lastNight": lastNight,
            "lastLevel": worstOf(c.level for _j, c in lastNight) if lastNight else BodyLanguage.unknown,
            "lastOk": sum(1 for _j, c in lastNight if c.level.rank <= BodyLanguage.earTwitch.rank),
        }

    # -- the three live regions: their context, their signature and their sentence ----------------------------------

    def overviewContext(self, fleet: Fleet, status: Status) -> Built:
        now = self.clock().astimezone(self.tz)
        hour = now.hour
        greeting = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17 else "Good evening"
        attention = status.attention()
        level = status.fleetLevel()
        signature = digest(
            [
                level.value,
                *(f"{n.name}={status.node(n.name).value}" for n in fleet.nodes),
                *(f"{a.subject}={a.level.value}" for a in attention),
            ]
        )
        count = len(attention)
        things = "thing needs" if count == 1 else "things need"
        needs = f"{count} {things} a look." if count else "Nothing needs a look."
        watchers = (*status.glare(), *status.disks(), *status.whiskers())
        notices = [s for s in watchers if s.bodyLanguage.rank >= BodyLanguage.tailFlick.rank]
        signature = digest([signature, *(f"{s.subject}={s.bodyLanguage.value}" for s in notices)])
        on = status.collectors()
        context = {
            "sparks": {
                n.name: self.sparks(
                    n.name, status.vitals(n.name), span="24 h", table="5m", delta=timedelta(hours=24), cols=96
                )
                for n in fleet.nodes
            },
            "glareOn": "glare" in on,
            "disksOn": "disks" in on,
            "whiskersOn": "whiskers" in on,
            "binocsOn": "binocs" in on,
            "releases": self.releasesInfo(),
            "greeting": greeting,
            "local": now,
            "recent": self.trail.events(limit=8),
            "alerts": self.alertsView(self.clock()),
            **self.lastNightSummary(self.clock()),
        }
        return context, signature, f"Fleet is {level.value}. {needs}"

    def nodeContext(self, fleet: Fleet, status: Status, nodeName: str) -> Built:
        node = fleet.node(nodeName)
        if node is None:
            raise HTTPException(404, "no such node")
        level = status.node(nodeName)
        parts = [level.value, *(f"{a.name}={status.app(nodeName, a.name).value}" for a in node.apps)]
        parts += [f"{s.subject}={s.bodyLanguage.value}" for s in status.strays(nodeName)]
        parts += [f"{s.subject}={s.bodyLanguage.value}" for s in status.disks(nodeName)]
        live = status.vitals(nodeName)
        context = {
            "node": node,
            "week": self.sparks(nodeName, live, span="7 days", table="5m", delta=timedelta(days=7), cols=168),
            "quarter": self.sparks(nodeName, live, span="90 days", table="hour", delta=timedelta(days=90), cols=90),
        }
        return context, digest(parts), f"{nodeName} is {level.value}."

    def appContext(self, fleet: Fleet, status: Status, nodeName: str, appName: str) -> Built:
        node = fleet.node(nodeName)
        found = node.app(appName) if node else None
        if node is None or found is None:
            raise HTTPException(404, "no such app")
        level = status.app(nodeName, appName)
        parts = [level.value, *(f"{c.subject}={c.bodyLanguage.value}" for c in status.containers(nodeName, found))]
        nightly = self.groomer.nightlyFor(nodeName, self.clock())
        if nightly is not None and nightly[1].level is not None:
            parts.append(f"nightly={nightly[1].level.value}")
        return (
            {"node": node, "app": found, "nightly": nightly},
            digest(parts),
            f"{nodeName}/{appName} is {level.value}.",
        )
