"""windowsill: perch's web UI (server-rendered Jinja2). Pages show the state at the moment they
are loaded, with how old purr's last look is; live refresh (htmx, SSE) comes with the milestones
that need it (runbook 2026-10-01).

Read-only by design (04 rule 4, amended by 05 A11): the only write routes perch will
ever have are ``POST /api/kitten``, ``POST /ack/{litterId}`` and ``POST /ack/t/{token}``;
test S7 checks the route table. M1 has none.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..bodyLanguage import LEVELS, BodyLanguage
from ..catTree import CatTree, CatTreeError, Fleet
from ..collectors import Runner, buildCollectors
from ..rollup import Status
from ..scentTrail import SENSES, ScentTrail, parseUtc, utcNow
from ..senses.purr import DISK_CRIT, DISK_WARN
from ..settings import Settings
from ..words import duration

HERE = Path(__file__).parent

SENSE_MEANING = {
    "purr": "containers, node vitals",
    "pounce": "filesystem drops",
    "whiskers": "smart-home events",
    "glare": "endpoints",
    "binocs": "the outside web",
    "groom": "backups",
    "perch": "perch itself",
}


def createApp(
    settings: "Settings | None" = None,
    *,
    trail: "ScentTrail | None" = None,
    tree: "CatTree | None" = None,
    clock: Callable[[], datetime] = utcNow,
    collectors: "list | None" = None,
) -> FastAPI:
    settings = settings or Settings.fromEnv()
    trail = trail or ScentTrail(
        settings.trailDb,
        secrets=settings.secretValues(),
        clock=clock,
        trailDays=settings.trailDays,
        rollupDays=settings.rollupDays,
    )
    tree = tree or CatTree(settings.repoDir)
    tz = ZoneInfo(settings.tz)
    if collectors is None:
        collectors = buildCollectors(settings, trail, tree, clock)
    runner = Runner(trail, collectors, clock=clock, secrets=settings.secretValues())

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(runner.run()) if collectors else None
        try:
            yield
        finally:
            if task:
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
            for collector in collectors:
                with contextlib.suppress(Exception):
                    await collector.aclose()

    app = FastAPI(title="persianPerch", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.trail = trail
    app.state.tree = tree
    app.state.runner = runner
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    templates = Jinja2Templates(directory=HERE / "templates")
    env = templates.env
    env.globals.update(BodyLanguage=BodyLanguage, LEVELS=LEVELS, SENSES=SENSES, SENSE_MEANING=SENSE_MEANING)
    env.filters["local"] = lambda moment, fmt="%H:%M": moment.astimezone(tz).strftime(fmt) if moment else "-"
    env.filters["bl"] = BodyLanguage.parse

    def glue(text: str) -> str:
        """Keep a number with its unit ("36 s", "1 h 10 min"): no line break inside it."""
        return text.replace(" ", "\u00a0")

    env.filters["ago"] = lambda moment: glue(duration((clock() - moment).total_seconds())) if moment else "never"
    env.filters["span"] = lambda seconds: glue(duration(seconds)) if seconds is not None else "-"

    def purrPill(status: Status) -> dict:
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
        age = glue(duration((clock() - parseUtc(last)).total_seconds()))
        word = {BodyLanguage.tailFlick: "late, ", BodyLanguage.hiss: "missing, "}.get(state.bodyLanguage, "")
        return {
            "level": state.bodyLanguage,
            "text": f"purr {word}{age} ago",
            "title": state.title or "",
            "summary": f"purr looked {age} ago",
        }

    def unknownNote(status: Status, unknown: int) -> str | None:
        """Why some apps are grey, in a sentence; None when none are."""
        if not unknown:
            return None
        pill = purrPill(status)
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

    def diskLevel(disk: float) -> BodyLanguage | None:
        """The level a full disk earns (purr's own thresholds), for tinting its bar."""
        return BodyLanguage.hiss if disk >= DISK_CRIT else BodyLanguage.tailFlick if disk >= DISK_WARN else None

    env.globals.update(purrPill=purrPill, unknownNote=unknownNote, diskLevel=diskLevel)

    def fleetOr503() -> Fleet:
        try:
            return tree.fleet()
        except CatTreeError as exc:
            raise HTTPException(503, f"catTree can't read the fleet repo: {exc}") from exc

    def readTracked(fleet: Fleet, path: str) -> str:
        if path not in fleet.files:
            return ""
        try:
            return tree.read(path, fleet)
        except CatTreeError:
            return ""

    def render(request: Request, name: str, page: str, **context) -> HTMLResponse:
        fleet = context.get("fleet") or fleetOr503()
        status = context.get("status") or Status(fleet, trail)
        context.update(fleet=fleet, status=status, page=page, now=clock())
        return templates.TemplateResponse(request, name, context)

    errors = {
        404: ("Not found", "Check the address, or find it from the overview or catTree."),
        405: ("Not allowed", "perch only watches: no page here changes anything."),
        503: (
            "perch can't read its source",
            "Check that PERCH_REPO_DIR points at the fleet repo checkout and that git can read it, then reload.",
        ),
    }
    errorDetail = {
        "no such node": "perch doesn't know a node with that name.",
        "no such app": "That node has no app with that name.",
        "no such doc": "That document isn't in the fleet repo's docs.",
    }

    @app.exception_handler(StarletteHTTPException)
    async def errorPage(request: Request, exc: StarletteHTTPException):
        """A person asked for a page, so a person gets a page (JSON stays for /healthz and /static)."""
        if request.url.path.startswith(("/static", "/healthz")):
            return await http_exception_handler(request, exc)
        heading, nextStep = errors.get(
            exc.status_code, ("Something went wrong", "Try again, or go back to the overview.")
        )
        try:
            fleet = tree.fleet()
            status = Status(fleet, trail)
        except CatTreeError:
            fleet = status = None  # the page can still say what is wrong without the fleet
        context = {
            "fleet": fleet,
            "status": status,
            "page": "",
            "now": clock(),
            "code": exc.status_code,
            "heading": heading,
            "detail": errorDetail.get(str(exc.detail), str(exc.detail)),
            "nextStep": nextStep,
        }
        return templates.TemplateResponse(request, "error.html", context, status_code=exc.status_code)

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        now = clock().astimezone(tz)
        hour = now.hour
        greeting = "Good morning" if 5 <= hour < 12 else "Good afternoon" if 12 <= hour < 17 else "Good evening"
        recent = trail.events(limit=8)
        return render(request, "overview.html", "perch", greeting=greeting, local=now, recent=recent)

    @app.get("/tree", response_class=HTMLResponse)
    def treeIndex(request: Request):
        return render(request, "tree.html", "catTree")

    @app.get("/tree/docs/{path:path}", response_class=HTMLResponse)
    def treeDoc(request: Request, path: str):
        fleet = fleetOr503()
        if path not in fleet.docs:
            raise HTTPException(404, "no such doc")
        try:
            text = tree.read(path, fleet)
        except CatTreeError as exc:
            raise HTTPException(404, "no such doc") from exc
        return render(request, "doc.html", "catTree", fleet=fleet, path=path, text=text)

    @app.get("/tree/{nodeName}", response_class=HTMLResponse)
    def treeNode(request: Request, nodeName: str):
        fleet = fleetOr503()
        node = fleet.node(nodeName)
        if node is None:
            raise HTTPException(404, "no such node")
        readme = readTracked(fleet, f"{node.path}/README.md")
        return render(request, "node.html", "catTree", fleet=fleet, node=node, readme=readme)

    @app.get("/tree/{nodeName}/{appName}", response_class=HTMLResponse)
    def treeApp(request: Request, nodeName: str, appName: str):
        fleet = fleetOr503()
        node = fleet.node(nodeName)
        found = node.app(appName) if node else None
        if found is None:
            raise HTTPException(404, "no such app")
        readme = readTracked(fleet, f"{found.path}/README.md")
        events = trail.events(subjectPrefix=found.id, limit=20)
        return render(request, "app.html", "catTree", fleet=fleet, node=node, app=found, readme=readme, events=events)

    @app.get("/groom", response_class=HTMLResponse)
    def groom(request: Request):
        return render(request, "groom.html", "groom")

    @app.get("/trail", response_class=HTMLResponse)
    def scentTrailView(
        request: Request,
        sense: list[str] = Query(default=[]),
        level: list[str] = Query(default=[]),
        hours: int = Query(default=48, ge=1, le=24 * 90),
    ):
        senses = [s for s in sense if s in SENSES] or list(SENSES)
        levels = [lv for lv in level if lv in BodyLanguage.__members__] or [lv.value for lv in LEVELS]
        events = trail.events(since=clock() - timedelta(hours=hours), senses=senses, levels=levels, limit=500)
        return render(request, "trail.html", "scentTrail", events=events, senses=senses, levels=levels, hours=hours)

    @app.get("/healthz")
    def healthz():
        body = {
            "ok": True,
            "schemaVersion": trail.schemaVersion,
            "journalMode": trail.journalMode,
            "collectors": runner.report(),
        }
        try:
            body["commit"] = tree.fleet().commit[:12]
        except CatTreeError as exc:
            body.update(ok=False, catTree=str(exc)[:200])
        return JSONResponse(body, status_code=200 if body["ok"] else 503)

    return app
