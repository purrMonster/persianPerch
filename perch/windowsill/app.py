"""windowsill: perch's web UI (server-rendered Jinja2; htmx and SSE arrive with live data).

Read-only by design (04 rule 4, amended by 05 A11): the only write routes perch will
ever have are ``POST /api/kitten``, ``POST /ack/{litterId}`` and ``POST /ack/t/{token}``;
test S7 checks the route table. M0 has none.
"""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from ..bodyLanguage import LEVELS, BodyLanguage, worstOf
from ..catTree import CatTree, CatTreeError, Fleet
from ..scentTrail import SENSES, ScentTrail, utcNow
from ..settings import Settings

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


class Status:
    """Current bodyLanguage per subject, rolled up worst-of: app -> node -> fleet."""

    def __init__(self, fleet: Fleet, trail: ScentTrail) -> None:
        self.fleet = fleet
        self.states = trail.states()

    def app(self, node: str, app: str) -> BodyLanguage:
        state = self.states.get(f"app:{node}/{app}")
        return state.bodyLanguage if state else BodyLanguage.unknown

    def node(self, name: str) -> BodyLanguage:
        node = self.fleet.node(name)
        own = self.states.get(f"node:{name}")
        levels = [self.app(name, a.name) for a in (node.apps if node else [])]
        if own:
            levels.append(own.bodyLanguage)
        return worstOf(levels)

    def fleetLevel(self) -> BodyLanguage:
        return worstOf(self.node(n.name) for n in self.fleet.nodes)

    def counts(self) -> dict[BodyLanguage, int]:
        counts = {level: 0 for level in (*LEVELS, BodyLanguage.unknown)}
        for node in self.fleet.nodes:
            for app in node.apps:
                counts[self.app(node.name, app.name)] += 1
        return counts


def createApp(
    settings: "Settings | None" = None,
    *,
    trail: "ScentTrail | None" = None,
    tree: "CatTree | None" = None,
    clock: Callable[[], datetime] = utcNow,
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

    app = FastAPI(title="persianPerch", docs_url=None, redoc_url=None, openapi_url=None)
    app.state.settings = settings
    app.state.trail = trail
    app.state.tree = tree
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")

    templates = Jinja2Templates(directory=HERE / "templates")
    env = templates.env
    env.globals.update(BodyLanguage=BodyLanguage, LEVELS=LEVELS, SENSES=SENSES, SENSE_MEANING=SENSE_MEANING)
    env.filters["local"] = lambda moment, fmt="%H:%M": moment.astimezone(tz).strftime(fmt) if moment else "—"
    env.filters["bl"] = BodyLanguage.parse

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

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        now = clock().astimezone(tz)
        hour = now.hour
        greeting = "Good morning" if 5 <= hour < 12 else "Good afternoon" if hour < 17 else "Good evening"
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
        body = {"ok": True, "schemaVersion": trail.schemaVersion, "journalMode": trail.journalMode}
        try:
            body["commit"] = tree.fleet().commit[:12]
        except CatTreeError as exc:
            body.update(ok=False, catTree=str(exc)[:200])
        return JSONResponse(body, status_code=200 if body["ok"] else 503)

    return app
