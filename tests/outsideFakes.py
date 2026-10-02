"""Fakes for M4's senses, shaped from the v5.36.0 (Gatus), v0.9.3 (Scrutiny) and v1.15.0 (speedtest-tracker)
sources and the OCI distribution spec. httpx2 MockTransports that record what they were asked and can be told to
fail, like tests/komodoFake.py. **No real Gatus, Scrutiny, speedtest-tracker or registry is ever contacted.**"""

from __future__ import annotations

import base64
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from typing import Any
from zoneinfo import ZoneInfo

import httpx2

from perch.senses.gatus import GatusClient
from perch.senses.registries import Registries
from perch.senses.scrutiny import ScrutinyClient
from perch.senses.speedtest import SpeedtestClient

GATUS_URL = "http://gatus.example.home.arpa"
GATUS_USER, GATUS_PASSWORD = "perch-svc", "fake-gatus-password-not-real"
SCRUTINY_URL = "http://scrutiny:8080"
SPEEDTEST_URL = "http://192.0.2.14:8765"
SPEEDTEST_TOKEN = "fake-speedtest-token-not-real"
IST = ZoneInfo("Asia/Kolkata")


def gatusKey(group: str, name: str) -> str:
    """Gatus's own key (config/key in v5.36.0): lower-case, a few characters turned into a hyphen."""
    out = []
    for part in (group, name):
        s = part.strip().lower()
        for ch in "/_., #+&":
            s = s.replace(ch, "-")
        out.append(s)
    return "_".join(out)


def stamp(moment: datetime) -> str:
    return moment.strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"


# -- Gatus ------------------------------------------------------------------------------------


@dataclass
class Endpoint:
    name: str
    group: str
    every: int = 60
    up: bool = True
    why: list[str] = field(default_factory=list)
    results: list[dict[str, Any]] = field(default_factory=list)

    @property
    def key(self) -> str:
        return gatusKey(self.group, self.name)


class GatusFake:
    def __init__(self, clock) -> None:
        self.clock = clock
        self.endpoints: dict[str, Endpoint] = {}
        self.down = False
        self.refuse: int | None = None  # answer this status instead (302 is Authelia's redirect to its login)
        self.notJson = False
        self.requests: list[httpx2.Request] = []

    def add(self, name: str, group: str = "", every: int = 60) -> Endpoint:
        e = Endpoint(name, group, every)
        self.endpoints[e.key] = e
        return e

    def check(self, key: str, *, up: bool | None = None, why: str | None = None) -> None:
        """One more check result for an endpoint, now."""
        e = self.endpoints[key]
        if up is not None:
            e.up = up
        ok = e.up
        e.results.append(
            {
                "status": 200 if ok else 503,
                "hostname": "svc.example.home.arpa",
                "duration": 12_345_678,
                "conditionResults": [{"condition": "[STATUS] == 200", "success": ok}],
                "success": ok,
                "timestamp": stamp(self.clock()),
                **({} if ok else {"errors": [why]} if why else {}),
            }
        )

    def tick(self, seconds: int = 60) -> None:
        """Every endpoint is checked, then time passes."""
        for key in self.endpoints:
            self.check(key)
        self.clock.advance(seconds=seconds)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.down:
            raise httpx2.ConnectError("connection refused")
        want = "Basic " + base64.b64encode(f"{GATUS_USER}:{GATUS_PASSWORD}".encode()).decode()
        if self.refuse or request.headers.get("authorization") != want:
            status = self.refuse or 401
            headers = {"location": "https://auth.example.home.arpa/?rd=x"} if status == 302 else {}
            return httpx2.Response(status, headers=headers, text="no")
        if self.notJson:
            return httpx2.Response(200, text="<html>Authelia login</html>")
        assert request.method == "GET" and request.url.path == "/api/v1/endpoints/statuses"
        size = int(request.url.params.get("pageSize", "50"))
        body = [
            {"name": e.name, "group": e.group, "key": e.key, "results": e.results[-size:]}
            for e in self.endpoints.values()
        ]
        return httpx2.Response(200, json=body)

    def client(self) -> GatusClient:
        return GatusClient(GATUS_URL, GATUS_USER, GATUS_PASSWORD, transport=httpx2.MockTransport(self))


# -- Scrutiny ---------------------------------------------------------------------------------


@dataclass
class Drive:
    wwn: str
    name: str
    host: str
    model: str
    protocol: str = "ATA"
    status: int = 0
    collected: datetime | None = None
    temp: int = 34
    summaryHours: int = 12000
    attrs: dict[str, dict[str, Any]] = field(default_factory=dict)  # as ``attrs`` in a smart result
    capacity: int = 4_000_787_030_016
    archived: bool = False
    noDetails: bool = False

    @property
    def uuid(self) -> str:
        return f"00000000-0000-4000-8000-{self.wwn[-12:].rjust(12, '0')}"


class ScrutinyFake:
    def __init__(self, clock) -> None:
        self.clock = clock
        self.drives: dict[str, Drive] = {}
        self.down = False
        self.requests: list[httpx2.Request] = []

    def add(self, wwn: str, name: str, host: str, model: str, **kw: Any) -> Drive:
        d = Drive(wwn, name, host, model, **kw)
        d.collected = d.collected or self.clock()
        self.drives[wwn] = d
        return d

    @staticmethod
    def attr(attrId: int, raw: int, *, status: int = 0, value: int = 100) -> dict[str, Any]:
        return {
            "attribute_id": attrId,
            "value": value,
            "thresh": 0,
            "worst": value,
            "raw_value": raw,
            "raw_string": str(raw),
            "when_failed": "",
            "transformed_value": 0,
            "status": status,
        }

    def _device(self, d: Drive) -> dict[str, Any]:
        return {
            "wwn": d.wwn,
            "device_name": d.name,
            "device_uuid": "",
            "host_id": d.host,
            "model_name": d.model,
            "serial_number": "FAKE-" + d.wwn[-4:],
            "device_protocol": d.protocol,
            "capacity": d.capacity,
            "archived": d.archived,
            "device_status": d.status,
            "scrutiny_uuid": d.uuid,
        }

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.down:
            raise httpx2.ConnectError("connection refused")
        assert request.method == "GET"
        path = request.url.path
        if path == "/api/summary":
            summary = {
                d.wwn: {
                    "device": self._device(d),
                    "smart": {"collector_date": stamp(d.collected), "temp": d.temp, "power_on_hours": d.summaryHours},
                }
                for d in self.drives.values()
            }
            return httpx2.Response(200, json={"success": True, "data": {"summary": summary}})
        for d in self.drives.values():
            if path == f"/api/device/{d.uuid}/details":
                if d.noDetails:
                    return httpx2.Response(500, json={"success": False})
                assert request.url.params.get("duration_key") == "week"
                results = [{"date": stamp(d.collected), "power_on_hours": d.summaryHours, "attrs": d.attrs}]
                meta = {"9": {"display_name": "Power-On Hours"}, "5": {"display_name": "Reallocated Sectors Count"}}
                return httpx2.Response(
                    200,
                    json={
                        "success": True,
                        "data": {"device": self._device(d), "smart_results": results},
                        "metadata": meta,
                    },
                )
        return httpx2.Response(404, json={"success": False})

    def client(self) -> ScrutinyClient:
        return ScrutinyClient(SCRUTINY_URL, transport=httpx2.MockTransport(self))


# -- speedtest-tracker --------------------------------------------------------------------------


class SpeedtestFake:
    def __init__(self, clock) -> None:
        self.clock = clock
        self.down = False
        self.status = "completed"
        self.healthy: bool | None = True
        self.noResults = False
        self.forbidden = False
        self.at: datetime | None = None
        self.downBits, self.upBits, self.ping = 312_400_000, 41_200_000, 9.4
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        if self.down:
            raise httpx2.ConnectError("connection refused")
        if request.headers.get("authorization") != f"Bearer {SPEEDTEST_TOKEN}" or self.forbidden:
            return httpx2.Response(403, json={"message": "You do not have permission to view results."})
        assert request.method == "GET" and request.url.path == "/api/v1/results/latest"
        if self.noResults:
            return httpx2.Response(404, json={"message": "No query results"})
        at = (self.at or self.clock()).astimezone(IST)
        data = {
            "id": 77,
            "service": "ookla",
            "ping": self.ping,
            "download": self.downBits // 8,
            "upload": self.upBits // 8,
            "download_bits": self.downBits,
            "upload_bits": self.upBits,
            "healthy": self.healthy,
            "status": self.status,
            "scheduled": True,
            "created_at": at.strftime("%Y-%m-%d %H:%M:%S"),
            "updated_at": at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        return httpx2.Response(200, json={"data": data, "message": "ok"})

    def client(self) -> SpeedtestClient:
        return SpeedtestClient(SPEEDTEST_URL, SPEEDTEST_TOKEN, tz=IST, transport=httpx2.MockTransport(self))


# -- the registries (OCI distribution: Docker's registry and ghcr.io) ---------------------------


class RegistryFake:
    """Both registries answer ``/v2/<repo>/tags/list`` after the anonymous token challenge. ``tags`` maps
    ``"<host>/<repo>"`` to its tag list; ``limit`` makes a host answer 429; ``pageSize`` forces Link paging."""

    TOKEN_HOSTS = {"registry-1.docker.io": "auth.docker.io", "ghcr.io": "ghcr.io"}

    def __init__(self) -> None:
        self.tags: dict[str, list[str]] = {}
        self.limit: dict[str, int] = {}  # host -> Retry-After seconds
        self.pageSize = 1000
        self.evilRealm = False
        self.requests: list[httpx2.Request] = []

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        self.requests.append(request)
        host, path = request.url.host, request.url.path
        assert request.method == "GET"
        if host in self.limit:
            return httpx2.Response(429, headers={"retry-after": str(self.limit[host])}, text="slow down")
        if host in self.TOKEN_HOSTS.values() and path == "/token":
            assert "authorization" not in request.headers  # anonymous: no credential is ever sent
            return httpx2.Response(200, json={"token": "fake-anon-token", "expires_in": 300})
        assert host in self.TOKEN_HOSTS, f"unexpected host {host}"
        if request.headers.get("authorization") != "Bearer fake-anon-token":
            realm = (
                "https://evil.example.home.arpa/token" if self.evilRealm else f"https://{self.TOKEN_HOSTS[host]}/token"
            )
            scope = path.removeprefix("/v2/").removesuffix("/tags/list")
            challenge = f'Bearer realm="{realm}",service="{host}",scope="repository:{scope}:pull"'
            return httpx2.Response(401, headers={"www-authenticate": challenge})
        repo = path.removeprefix("/v2/").removesuffix("/tags/list")
        every = sorted(self.tags.get(f"{host}/{repo}", []))
        if not every and f"{host}/{repo}" not in self.tags:
            return httpx2.Response(404, json={"errors": [{"code": "NAME_UNKNOWN"}]})
        last = request.url.params.get("last", "")
        rest = [t for t in every if t > last]
        page, more = rest[: self.pageSize], len(rest) > self.pageSize
        headers = {}
        if more:
            headers["link"] = f'</v2/{repo}/tags/list?last={page[-1]}&n={self.pageSize}>; rel="next"'
        return httpx2.Response(200, headers=headers, json={"name": repo, "tags": page})

    def client(self) -> Registries:
        return Registries(transport=httpx2.MockTransport(self))


def later(moment: datetime, **delta: float) -> datetime:
    return moment + timedelta(**delta)
