"""acks: the two Acknowledge routes (05 plan A11, test S9), the other write routes besides kitten's report. Both
write only perch's own database, and all either can do is stop one litter's repeats."""

from __future__ import annotations

from collections import deque
from datetime import datetime, timedelta
from urllib.parse import parse_qs, urlsplit

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse

from .. import ack as ackTokens
from .sill import Sill

PUSH_LIMIT = 10  # acknowledge links a minute, from anywhere (the Traefik router allows the same)


def sameOrigin(request: Request) -> bool:
    """The request came from a page on perch's own address (ADR 0005). Browsers send Sec-Fetch-Site and Origin on
    every POST; a request with neither can't prove where it came from and is refused."""
    site = request.headers.get("sec-fetch-site")
    origin = request.headers.get("origin")
    if site is not None and site != "same-origin":
        return False
    if origin is not None:
        return urlsplit(origin).netloc == request.headers.get("host", "-")
    return site == "same-origin"


def installAcks(app: FastAPI, sill: Sill) -> None:
    """Register the routes on ``app`` itself, not through an APIRouter: FastAPI hides an included router's
    routes from ``app.routes``, and test S7 must see every one of them."""
    store, meow = sill.store, sill.meow

    @app.post("/ack/{litterId}")
    async def ackFromPage(request: Request, litterId: str):
        """Acknowledge from the page: behind Authelia like every page, with the same-origin check and the form's
        CSRF token."""
        if not sameOrigin(request):
            raise HTTPException(403, "cross-site")
        raw = await request.body()
        form = parse_qs(raw[:4096].decode("utf-8", errors="ignore"))
        if not ackTokens.csrfOk(sill.csrfKey, litterId, (form.get("csrf") or [""])[0], sill.clock()):
            raise HTTPException(403, "bad form token")
        found = store.get(litterId)
        if found is None or not found.isOpen:
            raise HTTPException(404, "no such litter")
        now = sill.clock()
        store.acknowledge(litterId, "from the page", now)
        if found.ackedAt is None:
            meow.acknowledged(found, "from the page", now)
        if request.headers.get("hx-request"):
            when = f"{now.astimezone(sill.tz):%H:%M}"
            # tabindex and autofocus: the button that had focus is gone, htmx moves focus to the line that replaced it
            return HTMLResponse(
                f'<span class="acked small" tabindex="-1" autofocus>Acknowledged at {when}</span>'
                f'<div id="announce" hx-swap-oob="innerHTML">Acknowledged {found.name} at {when}.</div>'
            )
        return RedirectResponse("/", status_code=303)

    pushHits: deque[datetime] = deque()

    @app.post("/ack/t/{token}")
    async def ackFromPush(token: str):
        """Acknowledge from a push's button. No login: the signed, single-use token is the whole authority. 10
        requests a minute on this path; every refusal looks the same, so a token can't be probed."""
        now = sill.clock()
        while pushHits and now - pushHits[0] > timedelta(minutes=1):
            pushHits.popleft()
        if len(pushHits) >= PUSH_LIMIT:
            return JSONResponse({"ok": False}, status_code=429, headers={"Retry-After": "60"})
        pushHits.append(now)
        refused = JSONResponse({"ok": False}, status_code=403)
        checked = ackTokens.verify(sill.settings.ackSecret, token, now)
        if checked is None:
            return refused
        found = store.get(checked.litterId)
        if found is None or not found.isOpen or not store.spend(checked.tokenId, found.litterId, now):
            return refused
        store.acknowledge(found.litterId, "from the push", now)
        if found.ackedAt is None:
            meow.acknowledged(found, "from the push", now)
        return {"ok": True}

