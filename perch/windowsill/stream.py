"""stream: the live scentTrail (M5, ADR 0011), server-sent events behind ``/trail``. A GET that reads: S7 is
untouched."""

from __future__ import annotations

import asyncio

from fastapi import FastAPI, Query, Request
from fastapi.responses import StreamingResponse

from ..bodyLanguage import BodyLanguage
from ..catTree import Fleet
from .sill import Sill, trailFilters

LIVE_ROWS = 50  # how many new events the open trail lists before it says "and N more"
KEEP_ALIVE = 15.0  # seconds of silence after which the stream sends a comment, so a proxy keeps it open


def hissSentence(hisses: list) -> str:
    if len(hisses) == 1:
        return f"New hiss: {hisses[0].title}."
    return f"{len(hisses)} new hisses, the latest: {hisses[-1].title}."


def installStream(app: FastAPI, sill: Sill) -> None:
    """Register the routes on ``app`` itself, not through an APIRouter: FastAPI hides an included router's
    routes from ``app.routes``, and test S7 must see every one of them."""

    def liveTrail(rows: list, total: int, fleet: Fleet, announce: str | None) -> str:
        return sill.templates.get_template("live/trailNew.html").render(
            rows=rows, more=max(0, total - len(rows)), fleet=fleet, announce=announce
        )

    @app.get("/trail/stream")
    async def trailStream(
        request: Request,
        sense: list[str] = Query(default=[]),
        level: list[str] = Query(default=[]),
        after: int = Query(default=0, ge=0),
    ):
        """Server-sent events carrying the list of events stored since the page was built (``after``), through
        the same filters as the page. Every message is the whole list, so a reconnect can never list a row twice.
        A hiss that arrives while the stream is open is also said once, in a sentence for the polite live region.
        A comment goes out every 15 s so a proxy doesn't close it."""
        senses, levels = trailFilters(sense, level)
        fleet = sill.fleetOr503()
        trail = sill.trail
        state = request.app.state
        header = request.headers.get("last-event-id", "")
        loop = asyncio.get_running_loop()

        async def frames():
            yield "retry: 3000\n\n"
            heard = int(header) if header.isdigit() else await asyncio.to_thread(trail.lastRowid)
            shown: tuple[int, int] | None = None
            quiet = loop.time()
            while not state.stopping and not await request.is_disconnected():
                newest = await asyncio.to_thread(trail.lastRowid)
                rows, total = await asyncio.to_thread(
                    trail.eventsSince, after, senses=senses, levels=levels, limit=LIVE_ROWS
                )
                key = (rows[-1][0], total) if rows else None
                if key is not None and key != shown:
                    shown = key
                    hisses = [s for rid, s in rows if rid > heard and s.bodyLanguage is BodyLanguage.hiss]
                    html = liveTrail([s for _rid, s in rows], total, fleet, hissSentence(hisses) if hisses else None)
                    data = "".join(f"data: {line}\n" for line in html.splitlines() or [""])
                    yield f"event: new\nid: {newest}\n{data}\n"
                    quiet = loop.time()
                heard = max(heard, newest)
                if loop.time() - quiet >= KEEP_ALIVE:
                    yield ": keep-alive\n\n"
                    quiet = loop.time()
                await asyncio.sleep(state.streamPoll)

        return StreamingResponse(
            frames(),
            media_type="text/event-stream",
            headers={"Cache-Control": "no-cache, no-transform", "X-Accel-Buffering": "no"},
        )

