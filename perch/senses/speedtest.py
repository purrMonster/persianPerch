"""speedtest: the one module that knows speedtest-tracker's API (05 plan M4, C8; v1.15.0, the fleet's pin).

Read from the v1.15.0 source (``routes/api/v1/routes.php``, ``app/Http/Controllers/Api/V1`` and
``app/Http/Resources/V1/ResultResource.php`` in github.com/alexjustesen/speedtest-tracker; the fleet runs
LinuxServer's ``v1.15.0-ls170`` build of it on grinder, which hosts it on port 8765):

- ``GET /api/v1/results/latest`` with ``Authorization: Bearer <token>`` and ``Accept: application/json`` (the
  token needs the ``results:read`` ability; without it the answer is 403) -> ``{"data": {...}, "message": "ok"}``;
  with no result at all the answer is 404. ``?filter[status]=completed`` would give the last good one; glare
  takes the newest of any status, because a failed test is the thing to notice.
- ``data``: ``id``, ``status`` (``completed``, ``failed``, ``started``, ``running``, ``benchmarking``,
  ``checking``, ``waiting``, ``skipped``), ``healthy`` (true, false or null: whether it met the thresholds set
  in speedtest-tracker), ``ping`` (ms), ``download`` and ``upload`` (bytes per second) with ``download_bits``
  and ``upload_bits`` (bits per second), ``scheduled``, ``created_at`` (``YYYY-MM-DD HH:MM:SS`` in the app's
  timezone, which the fleet sets to the same ``TZ`` as perch).

Read-only (04 rule 4): the one request this module can send is that GET.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any
from zoneinfo import ZoneInfo

import httpx2

from ..scrub import scrub


class SpeedtestError(RuntimeError):
    """speedtest-tracker can't be read; never carries the token."""


@dataclass(frozen=True)
class Speedtest:
    id: int | None
    status: str
    healthy: bool | None
    pingMs: float | None
    downMbit: float | None
    upMbit: float | None
    at: datetime


def _reason(exc: Exception) -> str:
    if isinstance(exc, httpx2.TimeoutException):
        return "it timed out"
    if isinstance(exc, httpx2.ConnectError):
        return "connection refused or no route to it"
    return type(exc).__name__


class SpeedtestClient:
    def __init__(
        self,
        url: str,
        token: str,
        *,
        tz: ZoneInfo,
        transport: "httpx2.AsyncBaseTransport | None" = None,
        timeout: float = 10.0,
    ) -> None:
        if not (url and token):
            raise ValueError("the speedtest check needs PERCH_BINOCS_SPEEDTEST_URL and PERCH_BINOCS_SPEEDTEST_TOKEN")
        self._secrets = [token]
        self._tz = tz
        self._http = httpx2.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"authorization": f"Bearer {token}", "accept": "application/json"},
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def latest(self) -> Speedtest | None:
        """The newest result of any status, or None when speedtest-tracker has none yet."""
        try:
            response = await self._http.get("/api/v1/results/latest")
        except httpx2.HTTPError as exc:
            raise SpeedtestError(
                f"can't see speedtest-tracker: {_reason(exc)}. Check PERCH_BINOCS_SPEEDTEST_URL."
            ) from None
        if response.status_code == 404:
            return None
        if response.status_code in (401, 403):
            raise SpeedtestError(
                f"speedtest-tracker refused the token (HTTP {response.status_code}). "
                "Check PERCH_BINOCS_SPEEDTEST_TOKEN has the results:read ability."
            )
        if response.status_code >= 300:
            raise SpeedtestError(scrub(f"speedtest-tracker answered HTTP {response.status_code}", self._secrets, 200))
        try:
            data = response.json()["data"]
            return self._parse(data)
        except (ValueError, KeyError, TypeError, AttributeError):
            raise SpeedtestError(
                "unexpected answer from speedtest-tracker: not the v1.15.0 result shape. Check the URL."
            ) from None

    def _parse(self, data: dict[str, Any]) -> Speedtest:
        def mbit(key: str) -> float | None:
            value = data.get(key)
            return round(float(value) / 1e6, 1) if isinstance(value, int | float) else None

        ping = data.get("ping")
        healthy = data.get("healthy")
        at = datetime.strptime(str(data["created_at"]), "%Y-%m-%d %H:%M:%S").replace(tzinfo=self._tz)
        return Speedtest(
            id=data.get("id") if isinstance(data.get("id"), int) else None,
            status=str(data["status"]),
            healthy=healthy if isinstance(healthy, bool) else None,
            pingMs=round(float(ping), 1) if isinstance(ping, int | float) else None,
            downMbit=mbit("download_bits"),
            upMbit=mbit("upload_bits"),
            at=at.astimezone(UTC),
        )
