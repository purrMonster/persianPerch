"""pages: every page a person reads (GET only), their live regions, and the error page. The overview, node and app
pages refresh their state region every 30 s with htmx (ADR 0003): ``GET /live/...`` returns just that region."""

from __future__ import annotations

from datetime import timedelta
from urllib.parse import urlencode

from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.exception_handlers import http_exception_handler
from fastapi.responses import HTMLResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from ..bodyLanguage import BodyLanguage
from ..catTree import CatTreeError
from ..rollup import Status
from .sill import Sill, trailFilters

GROOM_NIGHTS = (7, 14, 30, 90)

ERRORS = {
    404: ("Not found", "Check the address, or find it from the overview or catTree."),
    405: ("Not allowed", "perch only watches: no page here changes anything."),
    403: ("Not allowed", "That request didn't come from perch's own page. Reload the page and try again."),
    503: (
        "perch can't read its source",
        "Check that PERCH_REPO_DIR points at the fleet repo checkout and that git can read it, then reload.",
    ),
}
ERROR_DETAIL = {
    "no such node": "perch doesn't know a node with that name.",
    "no such app": "That node has no app with that name.",
    "no such doc": "That document isn't in the fleet repo's docs.",
    "no such litter": "That alert has already cleared, or never existed.",
    "cross-site": "A page on another address can't acknowledge an alert for you.",
    "bad form token": "The form is too old or isn't perch's. Reload the page to get a fresh one.",
}


def installErrorPage(app: FastAPI, sill: Sill) -> None:
    @app.exception_handler(StarletteHTTPException)
    async def errorPage(request: Request, exc: StarletteHTTPException):
        """A person asked for a page, so a person gets a page (JSON stays for /healthz and /static)."""
        if request.url.path.startswith(("/static", "/healthz", "/api")):
            return await http_exception_handler(request, exc)
        fallback = ("Something went wrong", "Try again, or go back to the overview.")
        heading, nextStep = ERRORS.get(exc.status_code, fallback)
        try:
            fleet = sill.tree.fleet()
            status = Status(fleet, sill.trail)
        except CatTreeError:
            fleet = status = None  # the page can still say what is wrong without the fleet
        context = {
            "fleet": fleet,
            "status": status,
            "page": "",
            "now": sill.clock(),
            "code": exc.status_code,
            "heading": heading,
            "detail": ERROR_DETAIL.get(str(exc.detail), str(exc.detail)),
            "nextStep": nextStep,
        }
        return sill.templates.TemplateResponse(request, "error.html", context, status_code=exc.status_code)


def installPages(app: FastAPI, sill: Sill) -> None:
    """Register the routes on ``app`` itself, not through an APIRouter: FastAPI hides an included router's
    routes from ``app.routes``, and test S7 must see every one of them."""

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        fleet, status = sill.look()
        context, signature, _ = sill.overviewContext(fleet, status)
        return sill.render(
            request, "overview.html", "perch", fleet=fleet, status=status, signature=signature, **context
        )

    @app.get("/live/overview", response_class=HTMLResponse)
    def liveOverview(request: Request, seen: str = Query(default="", max_length=64)):
        fleet, status = sill.look()
        return sill.liveFragment(request, "overview", status, sill.overviewContext(fleet, status), seen)

    @app.get("/tree", response_class=HTMLResponse)
    def treeIndex(request: Request):
        return sill.render(request, "tree.html", "catTree")

    # before /tree/{nodeName}: "docs" is a path here, not a node
    @app.get("/tree/docs/{path:path}", response_class=HTMLResponse)
    def treeDoc(request: Request, path: str):
        fleet = sill.fleetOr503()
        if path not in fleet.docs:
            raise HTTPException(404, "no such doc")
        try:
            text = sill.tree.read(path, fleet)
        except CatTreeError as exc:
            raise HTTPException(404, "no such doc") from exc
        return sill.render(request, "doc.html", "catTree", fleet=fleet, path=path, text=text)

    @app.get("/tree/{nodeName}", response_class=HTMLResponse)
    def treeNode(request: Request, nodeName: str):
        fleet, status = sill.look()
        context, signature, _ = sill.nodeContext(fleet, status, nodeName)
        readme = sill.readTracked(fleet, f"{context['node'].path}/README.md")
        return sill.render(
            request, "node.html", "catTree", fleet=fleet, status=status, signature=signature, readme=readme, **context
        )

    @app.get("/live/node/{nodeName}", response_class=HTMLResponse)
    def liveNode(request: Request, nodeName: str, seen: str = Query(default="", max_length=64)):
        fleet, status = sill.look()
        return sill.liveFragment(request, "node", status, sill.nodeContext(fleet, status, nodeName), seen)

    @app.get("/tree/{nodeName}/{appName}", response_class=HTMLResponse)
    def treeApp(request: Request, nodeName: str, appName: str):
        fleet, status = sill.look()
        context, signature, _ = sill.appContext(fleet, status, nodeName, appName)
        found = context["app"]
        return sill.render(
            request,
            "app.html",
            "catTree",
            fleet=fleet,
            status=status,
            signature=signature,
            readme=sill.readTracked(fleet, f"{found.path}/README.md"),
            events=sill.trail.events(subjectPrefix=found.id, limit=20),
            **context,
        )

    @app.get("/live/app/{nodeName}/{appName}", response_class=HTMLResponse)
    def liveApp(request: Request, nodeName: str, appName: str, seen: str = Query(default="", max_length=64)):
        fleet, status = sill.look()
        return sill.liveFragment(request, "app", status, sill.appContext(fleet, status, nodeName, appName), seen)

    @app.get("/groom", response_class=HTMLResponse)
    def groomView(
        request: Request, nights: str = Query(default="14", max_length=4), cell: str = Query(default="", max_length=80)
    ):
        fleet, status = sill.look()
        groomer = sill.groomer
        now = sill.clock()
        nights = int(nights) if nights.isdigit() and int(nights) in GROOM_NIGHTS else 14
        days, rows = groomer.grid(nights, now)
        picked = None
        key, _, day = cell.partition("@")
        for job, cells in rows:
            for when, found in zip(days, cells, strict=True):
                if found is None or found.run is None:
                    continue
                if (job.key, when.isoformat()) == (key, day):
                    picked = (job, when, found)
                    break
                if not cell and (picked is None or found.run.start > picked[2].run.start):
                    picked = (job, when, found)
        problems = sorted(
            (
                (found.slot, job, found)
                for job, cells in rows
                for found in cells
                if found is not None and found.level is not None and found.level.rank >= BodyLanguage.earTwitch.rank
            ),
            key=lambda item: item[0],
            reverse=True,
        )[:10]
        jobs = groomer.jobs(fleet)
        return sill.render(
            request,
            "groom.html",
            "groom",
            fleet=fleet,
            status=status,
            nights=nights,
            nightChoices=GROOM_NIGHTS,
            days=days,
            rows=rows,
            picked=picked,
            problems=problems,
            copies=groomer.copies(now),
            unwatched=sorted({j.node for j in jobs} - groomer.watchedNodes()),
            noJobs=not jobs,
            **sill.lastNightSummary(now),
        )

    @app.get("/trail", response_class=HTMLResponse)
    def scentTrailView(
        request: Request,
        sense: list[str] = Query(default=[]),
        level: list[str] = Query(default=[]),
        hours: int = Query(default=48, ge=1, le=24 * 90),
    ):
        senses, levels = trailFilters(sense, level)
        trail = sill.trail
        cursor = trail.lastRowid()  # read first: an event stored while the page is built is listed twice at worst
        events = trail.events(since=sill.clock() - timedelta(hours=hours), senses=senses, levels=levels, limit=500)
        stream = urlencode([("sense", s) for s in senses] + [("level", lv) for lv in levels] + [("after", cursor)])
        return sill.render(
            request,
            "trail.html",
            "scentTrail",
            events=events,
            senses=senses,
            levels=levels,
            hours=hours,
            streamUrl=f"/trail/stream?{stream}",
        )

