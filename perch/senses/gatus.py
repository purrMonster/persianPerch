"""gatus: the one module that knows Gatus's API (05 plan M4, A8; Gatus v5.36.0, the fleet's pin).

Read from the v5.36.0 source (``api/api.go``, ``api/endpoint_status.go``, ``config/endpoint`` in
github.com/TwiN/gatus):

- ``GET /api/v1/endpoints/statuses?page=1&pageSize=N`` -> a JSON **array** of endpoint statuses. ``page`` and
  ``pageSize`` page the *results of each endpoint* (default 50 per endpoint, newest page first), not the
  endpoints. Each item: ``name``, ``group``, ``key`` (``<group>_<name>``, lower-cased, ``/ _ . , space # + &``
  turned into ``-``), ``results`` and ``events`` (``type`` START, HEALTHY or UNHEALTHY).
- A result: ``success`` (bool), ``timestamp`` (RFC 3339), ``duration`` (**nanoseconds**), ``status`` (the HTTP
  status, when there was one), ``errors`` and ``conditionResults`` (``condition`` and ``success``).
- **Uptime is not in that JSON** (``Uptime`` is ``json:"-"``); it has its own plain-text routes
  (``/api/v1/endpoints/:key/uptimes/{1h,24h,7d,30d}``). glare doesn't call them: it judges the newest results
  itself, so one request answers for every endpoint.
- Gatus publishes no port: it sits behind sieve's Traefik and Authelia, so perch signs in with HTTP Basic as the
  LLDAP service account ``ocicat`` (``forward-auth-basic``, A8). Authelia answers a refused or missing
  login with a redirect or 401: both are "refused", never followed.

Read-only (04 rule 4): the only request this module can send is that one GET.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any

import httpx2

from ..scrub import scrub

PAGE_SIZE = 20  # results per endpoint: enough to count a streak of failures and to see the check's own rhythm


class GatusError(RuntimeError):
    """Gatus can't be read; the message says what to check and never carries a credential."""


@dataclass(frozen=True)
class GatusResult:
    success: bool
    at: datetime
    ms: float
    status: int | None
    errors: tuple[str, ...]
    failed: tuple[str, ...]  # the conditions that were not met


@dataclass(frozen=True)
class GatusEndpoint:
    key: str
    name: str
    group: str
    results: tuple[GatusResult, ...]  # oldest first


def _reason(exc: Exception) -> str:
    if isinstance(exc, httpx2.TimeoutException):
        return "it timed out"
    if isinstance(exc, httpx2.ConnectError):
        return "connection refused or no route to it"
    return type(exc).__name__


def _unexpected(what: str) -> GatusError:
    return GatusError(f"Unexpected answer from Gatus: {what}.")


class GatusClient:
    def __init__(
        self,
        url: str,
        user: str,
        password: str,
        *,
        transport: "httpx2.AsyncBaseTransport | None" = None,
        timeout: float = 10.0,
    ) -> None:
        if not (url and user and password):
            raise ValueError("glare needs PERCH_GLARE_URL, PERCH_GLARE_USER and PERCH_GLARE_PASSWORD")
        self._secrets = [password]
        self._http = httpx2.AsyncClient(
            base_url=url.rstrip("/"),
            auth=httpx2.BasicAuth(user, password),
            headers={"accept": "application/json"},
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def statuses(self) -> list[GatusEndpoint]:
        try:
            response = await self._http.get("/api/v1/endpoints/statuses", params={"page": 1, "pageSize": PAGE_SIZE})
        except httpx2.HTTPError as exc:
            raise GatusError(
                f"can't see Gatus: {_reason(exc)}. Check PERCH_GLARE_URL and that Gatus and sieve's Traefik run."
            ) from None
        if response.status_code in (301, 302, 303, 307, 308, 401, 403):
            raise GatusError(
                f"can't see Gatus: the login was refused (HTTP {response.status_code}). "
                "Check PERCH_GLARE_USER and PERCH_GLARE_PASSWORD and the ocicat rule in Authelia."
            )
        if response.status_code >= 400:
            raise GatusError(
                scrub(f"can't see Gatus: it answered HTTP {response.status_code}", self._secrets, limit=300)
            )
        try:
            answer = response.json()
        except ValueError:
            raise GatusError(
                "can't see Gatus: the answer was not JSON. Check that PERCH_GLARE_URL reaches Gatus, not a login page."
            ) from None
        if not isinstance(answer, list):
            raise _unexpected("the statuses were not a list")
        return [_endpoint(item) for item in answer]


def _endpoint(item: Any) -> GatusEndpoint:
    if not isinstance(item, dict) or not isinstance(item.get("key"), str) or not isinstance(item.get("name"), str):
        raise _unexpected("an endpoint has no key or name")
    raw = item.get("results") or []
    if not isinstance(raw, list):
        raise _unexpected(f"{item['key']}: results is not a list")
    results = sorted((_result(item["key"], r) for r in raw), key=lambda r: r.at)
    return GatusEndpoint(key=item["key"], name=item["name"], group=item.get("group") or "", results=tuple(results))


def _result(key: str, raw: Any) -> GatusResult:
    try:
        at = datetime.fromisoformat(str(raw["timestamp"]).replace("Z", "+00:00"))
        if at.tzinfo is None:
            raise ValueError("no time zone")
        failed = tuple(
            str(c.get("condition", "")) for c in raw.get("conditionResults") or [] if not c.get("success", True)
        )
        status = raw.get("status")
        return GatusResult(
            success=bool(raw["success"]),
            at=at,
            ms=float(raw.get("duration") or 0) / 1e6,
            status=status if isinstance(status, int) else None,
            errors=tuple(str(e) for e in raw.get("errors") or []),
            failed=failed,
        )
    except (KeyError, ValueError, TypeError, AttributeError):
        raise _unexpected(f"{key}: a result is not in the shape Gatus v5.36.0 sends") from None
