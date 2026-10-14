"""windowsill: perch's web UI (server-rendered Jinja2). A page shows the state as of the moment
it was rendered, with how old purr's last look is. The overview, node and app pages also refresh
their state region every 30 s with htmx (ADR 0003); ``/trail`` stays live over SSE (ADR 0011).

``createApp`` builds perch's parts and the shared :class:`~.sill.Sill`, then mounts the routes:
``pages`` (everything a person reads), ``stream`` (the live trail), ``reports`` (kitten's report)
and ``acks`` (the two Acknowledge routes). Split out of one closure on 2026-10-14; the route table
is unchanged.

Read-only by design (04 rule 4, amended by 05 A11): the only write routes perch will
ever have are ``POST /api/kitten``, ``POST /ack/{litterId}`` and ``POST /ack/t/{token}``;
test S7 checks the route table. The fragments are GET only.
"""

from __future__ import annotations

import asyncio
import contextlib
from collections.abc import Callable
from contextlib import asynccontextmanager
from datetime import datetime
from zoneinfo import ZoneInfo

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ..bodyLanguage import BodyLanguage
from ..catTree import CatTree, CatTreeError
from ..collectors import Runner, buildCollectors
from ..meow import Meow, buildMeow
from ..nineLives import NineLives
from ..scentTrail import ScentTrail, utcNow
from ..senses.groom import Groom
from ..settings import Settings
from .acks import installAcks
from .pages import installErrorPage, installPages
from .reports import installReports
from .sill import HERE, Sill
from .stream import installStream


def createApp(
    settings: "Settings | None" = None,
    *,
    trail: "ScentTrail | None" = None,
    tree: "CatTree | None" = None,
    clock: Callable[[], datetime] = utcNow,
    collectors: "list | None" = None,
    meow: "Meow | None" = None,
    nineLives: "NineLives | None" = None,
) -> FastAPI:
    settings = settings or Settings.fromEnv()
    ownTrail = trail is None  # one perch opens itself is closed at shutdown; a given one belongs to the caller
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
    meow = meow or buildMeow(settings, trail, tree, clock, tz)
    if collectors is None:
        collectors = buildCollectors(settings, trail, tree, clock)
        if groomer.watchedNodes():
            collectors.append(groomer)
        if meow.configured:  # a meow with nowhere to push has nothing to run
            collectors.append(meow)
    runner = Runner(trail, collectors, clock=clock, secrets=settings.secretValues())
    if nineLives is None and settings.nineLivesUrl:
        try:
            nineLives = NineLives(settings.nineLivesUrl, runner, trail, clock=clock)
        except ValueError as exc:
            trail.addEvent("perch", "ninelives", BodyLanguage.tailFlick, f"nineLives is switched off: {exc}")
    sill = Sill(settings, trail, tree, clock, tz, groomer, meow, runner, nineLives)

    @asynccontextmanager
    async def lifespan(_app: FastAPI):
        task = asyncio.create_task(runner.run()) if collectors else None
        beat = asyncio.create_task(nineLives.run()) if nineLives else None
        try:
            yield
        finally:
            app.state.stopping = True
            for running in (task, beat):
                if running:
                    running.cancel()
                    await asyncio.gather(running, return_exceptions=True)
            for collector in collectors:
                with contextlib.suppress(Exception):
                    await collector.aclose()
            if nineLives:
                with contextlib.suppress(Exception):
                    await nineLives.aclose()
            if ownTrail:
                trail.close()  # left to the garbage collector it was an unclosed database (Python 3.13 warns)

    app = FastAPI(title="persianPerch", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan)
    app.state.settings = settings
    app.state.stopping = False  # set at shutdown so open streams end instead of holding the server up
    app.state.streamPoll = 1.0  # seconds between looks at the trail for the live stream (tests make it shorter)
    app.state.trail = trail
    app.state.tree = tree
    app.state.runner = runner
    app.state.groom = groomer
    app.state.meow = meow
    app.state.nineLives = nineLives
    app.state.sill = sill
    app.mount("/static", StaticFiles(directory=HERE / "static"), name="static")
    installErrorPage(app, sill)
    for install in (installPages, installStream, installReports, installAcks):
        install(app, sill)

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
