"""reports: ``POST /api/kitten``, kitten's report. One of the three write routes (05 plan A11, test S7); it writes
only perch's own database."""

from __future__ import annotations

import asyncio
import hmac
import json

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from ..senses.groom import RecordError, parseRecord
from ..senses.pounce import MAX_EVENTS, parseEvent
from .sill import Sill

MAX_KITTEN_BODY = 1024 * 1024
MAX_KITTEN_RECORDS = 100


def kittenError(status: int, message: str) -> JSONResponse:
    headers = {"WWW-Authenticate": "Bearer"} if status == 401 else None
    return JSONResponse({"ok": False, "error": message}, status_code=status, headers=headers)


def tokenNode(header: str, tokens: dict[str, str]) -> str | None:
    """The node a bearer token belongs to. Every token is compared, in constant time, so the answer doesn't depend
    on which one matched."""
    scheme, _, token = header.partition(" ")
    if scheme.lower() != "bearer" or not token.strip():
        return None
    found = None
    for node, expected in tokens.items():
        if hmac.compare_digest(token.strip().encode(), expected.encode()):
            found = node
    return found


def installReports(app: FastAPI, sill: Sill) -> None:
    """Register the routes on ``app`` itself, not through an APIRouter: FastAPI hides an included router's
    routes from ``app.routes``, and test S7 must see every one of them."""

    def readReport(body: dict, node: str) -> "tuple[dict | None, list, list] | JSONResponse":  # noqa: PLR0911
        """The heartbeat, the groom runs and the pounce events of a report, checked; or the refusal."""
        heartbeat, records, events = body.get("heartbeat"), body.get("records", []), body.get("events", [])
        if heartbeat is not None and not isinstance(heartbeat, dict):
            return kittenError(422, "heartbeat must be an object")
        if not isinstance(records, list) or len(records) > MAX_KITTEN_RECORDS:
            return kittenError(422, f"records must be a list of at most {MAX_KITTEN_RECORDS}")
        if not isinstance(events, list) or len(events) > MAX_EVENTS:
            return kittenError(422, f"events must be a list of at most {MAX_EVENTS}")
        if heartbeat is None and not records and not events:
            return kittenError(422, "send a heartbeat, records or events")
        runs, seen = [], []
        for index, record in enumerate(records):
            try:
                run = parseRecord(record)
            except RecordError as exc:
                return kittenError(422, f"record {index}: {exc}")
            if run.node != node:
                return kittenError(403, f"record {index} is for another node")
            runs.append(run)
        for index, event in enumerate(events):
            try:
                seen.append(parseEvent(event, sill.clock()))
            except RecordError as exc:
                return kittenError(422, f"event {index}: {exc}")
        return heartbeat, runs, seen

    @app.post("/api/kitten")
    async def kittenApi(request: Request):  # noqa: PLR0911 - one early return per way to refuse
        """kitten's report: a heartbeat, the groom records and the pounce events it hasn't had acknowledged.
        401 without a token the node list knows, 403 with another node's token (test S3)."""
        node = tokenNode(request.headers.get("authorization", ""), sill.settings.kittenTokens)
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
        parsed = readReport(body, node)
        if isinstance(parsed, JSONResponse):
            return parsed
        heartbeat, runs, seen = parsed
        stored = await asyncio.to_thread(sill.groomer.ingest, node, heartbeat, runs)
        answer: dict = {"ok": True, "stored": stored}
        if seen:
            answer["events"] = await asyncio.to_thread(sill.pouncer.ingest, node, seen)
        return answer

