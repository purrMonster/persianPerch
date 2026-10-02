"""windowsill: perch's web UI (server-rendered Jinja2). A page shows the state as of the moment
it was rendered, with how old purr's last look is. The overview, node and app pages also refresh
their state region every 30 s with htmx (ADR 0003): ``GET /live/...`` returns just that region,
the header's two live bits and, when the state changed since the page last looked, one sentence
for a polite live region. SSE comes with M5.

Read-only by design (04 rule 4, amended by 05 A11): the only write routes perch will
ever have are ``POST /api/kitten``, ``POST /ack/{litterId}`` and ``POST /ack/t/{token}``;
test S7 checks the route table. The fragments are GET only.
"""

from __future__ import annotations

import asyncio
import contextlib
import hashlib
import hmac
import json
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

from ..bodyLanguage import LEVELS, BodyLanguage, worstOf
from ..catTree import CatTree, CatTreeError, Fleet
from ..collectors import Runner, buildCollectors
from ..rollup import Status
from ..scentTrail import SENSES, ScentTrail, parseUtc, utcNow
from ..senses.groom import Groom, RecordError, parseRecord
from ..senses.purr import DISK_CRIT, DISK_WARN
from ..settings import Settings
from ..words import duration

HERE = Path(__file__).parent
GROOM_NIGHTS = (7, 14, 30, 90)

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
    groomer = Groom(
        trail,
        tree,
        clock=clock,
        tz=tz,
        watched=settings.kittenTokens,
        groomDir=settings.groomDir,
        sleepers=settings.sleepers,
    )
    if collectors is None:
        collectors = buildCollectors(settings, trail, tree, clock)
        if groomer.watchedNodes():
            collectors.append(groomer)
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
    app.state.groom = groomer
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
        if request.url.path.startswith(("/static", "/healthz", "/api")):
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

    def digest(parts: list[str]) -> str:
        """What a client last saw, in 12 characters: the levels a person would be told about."""
        return hashlib.blake2b("|".join(parts).encode(), digest_size=6).hexdigest()

    def overviewContext(fleet: Fleet, status: Status) -> tuple[dict, str, str]:
        now = clock().astimezone(tz)
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
        lastNight = groomer.lastNight(clock())
        context = {
            "greeting": greeting,
            "local": now,
            "recent": trail.events(limit=8),
            "lastNight": lastNight,
            "lastLevel": worstOf(c.level for _j, c in lastNight) if lastNight else BodyLanguage.unknown,
            "lastOk": sum(1 for _j, c in lastNight if c.level.rank <= BodyLanguage.earTwitch.rank),
        }
        return context, signature, f"Fleet is {level.value}. {needs}"

    def nodeContext(fleet: Fleet, status: Status, nodeName: str) -> tuple[dict, str, str]:
        node = fleet.node(nodeName)
        if node is None:
            raise HTTPException(404, "no such node")
        level = status.node(nodeName)
        parts = [level.value, *(f"{a.name}={status.app(nodeName, a.name).value}" for a in node.apps)]
        parts += [f"{s.subject}={s.bodyLanguage.value}" for s in status.strays(nodeName)]
        return {"node": node}, digest(parts), f"{nodeName} is {level.value}."

    def appContext(fleet: Fleet, status: Status, nodeName: str, appName: str) -> tuple[dict, str, str]:
        node = fleet.node(nodeName)
        found = node.app(appName) if node else None
        if node is None or found is None:
            raise HTTPException(404, "no such app")
        level = status.app(nodeName, appName)
        parts = [level.value, *(f"{c.subject}={c.bodyLanguage.value}" for c in status.containers(nodeName, found))]
        nightly = groomer.nightlyFor(nodeName, clock())
        if nightly is not None and nightly[1].level is not None:
            parts.append(f"nightly={nightly[1].level.value}")
        return (
            {"node": node, "app": found, "nightly": nightly},
            digest(parts),
            f"{nodeName}/{appName} is {level.value}.",
        )

    def liveFragment(request: Request, kind: str, status: Status, built: tuple[dict, str, str], seen: str):
        """The region, the header's live bits, and one sentence when the client's last-seen state is stale."""
        context, signature, said = built
        context.update(
            fleet=status.fleet,
            status=status,
            now=clock(),
            signature=signature,
            region=f"live/{kind}.html",
            announce=said if seen and seen != signature else None,
        )
        return templates.TemplateResponse(request, "live/fragment.html", context)

    @app.get("/", response_class=HTMLResponse)
    def overview(request: Request):
        fleet = fleetOr503()
        status = Status(fleet, trail)
        context, signature, _ = overviewContext(fleet, status)
        return render(request, "overview.html", "perch", fleet=fleet, status=status, signature=signature, **context)

    @app.get("/live/overview", response_class=HTMLResponse)
    def liveOverview(request: Request, seen: str = Query(default="", max_length=64)):
        fleet = fleetOr503()
        status = Status(fleet, trail)
        return liveFragment(request, "overview", status, overviewContext(fleet, status), seen)

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
        status = Status(fleet, trail)
        context, signature, _ = nodeContext(fleet, status, nodeName)
        readme = readTracked(fleet, f"{context['node'].path}/README.md")
        return render(
            request, "node.html", "catTree", fleet=fleet, status=status, signature=signature, readme=readme, **context
        )

    @app.get("/live/node/{nodeName}", response_class=HTMLResponse)
    def liveNode(request: Request, nodeName: str, seen: str = Query(default="", max_length=64)):
        fleet = fleetOr503()
        status = Status(fleet, trail)
        return liveFragment(request, "node", status, nodeContext(fleet, status, nodeName), seen)

    @app.get("/tree/{nodeName}/{appName}", response_class=HTMLResponse)
    def treeApp(request: Request, nodeName: str, appName: str):
        fleet = fleetOr503()
        status = Status(fleet, trail)
        context, signature, _ = appContext(fleet, status, nodeName, appName)
        found = context["app"]
        return render(
            request,
            "app.html",
            "catTree",
            fleet=fleet,
            status=status,
            signature=signature,
            readme=readTracked(fleet, f"{found.path}/README.md"),
            events=trail.events(subjectPrefix=found.id, limit=20),
            **context,
        )

    @app.get("/live/app/{nodeName}/{appName}", response_class=HTMLResponse)
    def liveApp(request: Request, nodeName: str, appName: str, seen: str = Query(default="", max_length=64)):
        fleet = fleetOr503()
        status = Status(fleet, trail)
        return liveFragment(request, "app", status, appContext(fleet, status, nodeName, appName), seen)

    @app.get("/groom", response_class=HTMLResponse)
    def groomView(
        request: Request, nights: str = Query(default="14", max_length=4), cell: str = Query(default="", max_length=80)
    ):
        fleet = fleetOr503()
        status = Status(fleet, trail)
        now = clock()
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
        lastNight = groomer.lastNight(now)
        return render(
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
            lastNight=lastNight,
            lastLevel=worstOf(c.level for _j, c in lastNight) if lastNight else BodyLanguage.unknown,
            lastOk=sum(1 for _j, c in lastNight if c.level.rank <= BodyLanguage.earTwitch.rank),
            unwatched=sorted({j.node for j in jobs} - groomer.watchedNodes()),
            noJobs=not jobs,
        )

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

    MAX_KITTEN_BODY = 1024 * 1024
    MAX_KITTEN_RECORDS = 100

    def kittenError(status: int, message: str) -> JSONResponse:
        headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
        return JSONResponse({"ok": False, "error": message}, status_code=status, headers=headers)

    def kittenNode(request: Request) -> str | None:
        """The node a bearer token belongs to. Every token is compared, in constant time, so the answer
        doesn't depend on which one matched."""
        header = request.headers.get("authorization", "")
        scheme, _, token = header.partition(" ")
        if scheme.lower() != "bearer" or not token.strip():
            return None
        found = None
        for node, expected in settings.kittenTokens.items():
            if hmac.compare_digest(token.strip().encode(), expected.encode()):
                found = node
        return found

    @app.post("/api/kitten")
    async def kittenApi(request: Request):  # noqa: PLR0911 - one early return per way to refuse
        """kitten's report: a heartbeat and the groom records it hasn't had acknowledged. The one write
        endpoint besides the acknowledgements (05 plan A11, test S7); it writes only perch's own database.
        401 without a token the node list knows, 403 with another node's token (test S3)."""
        node = kittenNode(request)
        if node is None:
            return kittenError(401, "a bearer token is required")
        if int(request.headers.get("content-length") or 0) > MAX_KITTEN_BODY:
            return kittenError(413, "report too large")
        raw = await request.body()
        if len(raw) > MAX_KITTEN_BODY:
            return kittenError(413, "report too large")
        try:
            body = json.loads(raw)
        except ValueError:
            return kittenError(422, "the body must be JSON")
        if not isinstance(body, dict):
            return kittenError(422, "the body must be a JSON object")
        if body.get("node") != node:
            return kittenError(403, "this token belongs to another node")
        heartbeat, records = body.get("heartbeat"), body.get("records", [])
        if heartbeat is not None and not isinstance(heartbeat, dict):
            return kittenError(422, "heartbeat must be an object")
        if not isinstance(records, list) or len(records) > MAX_KITTEN_RECORDS:
            return kittenError(422, f"records must be a list of at most {MAX_KITTEN_RECORDS}")
        if heartbeat is None and not records:
            return kittenError(422, "send a heartbeat, records, or both")
        runs = []
        for index, record in enumerate(records):
            try:
                run = parseRecord(record)
            except RecordError as exc:
                return kittenError(422, f"record {index}: {exc}")
            if run.node != node:
                return kittenError(403, f"record {index} is for another node")
            runs.append(run)
        stored = await asyncio.to_thread(groomer.ingest, node, heartbeat, runs)
        return {"ok": True, "stored": stored}

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
