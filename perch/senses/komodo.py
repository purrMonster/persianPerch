"""komodo: the one module that knows Komodo Core's read API (05 plan M1, v2.3.2).

Everything Komodo-specific lives here: the request envelope, the field names, the
spellings of its enums. purr (``purr.py``) only sees the small dataclasses below, so a
Komodo upgrade is a change to this file and ``tests/fixtures/komodo`` and nothing else
(dev plan 6: "purr isolated behind one adapter").

The API, as read from the v2.3.2 source (``client/core/rs`` in moghtech/komodo):

- ``POST {url}/read`` with ``{"type": <request>, "params": {...}}``; the key and secret
  go in the ``x-api-key`` and ``x-api-secret`` headers.
- ``ListServers`` -> ``[ServerListItem]``: ``info.state`` is ``Ok``, ``NotOk`` or
  ``Disabled``, and ``info.stats`` already carries CPU, memory and disk totals.
- ``ListContainers {"server": <name or id>}`` -> ``[ContainerListItem]``: ``state`` is
  lower-case (``running``, ``exited``, ``restarting`` ...), ``status`` is Docker's own
  text ("Up 3 hours (healthy)") and ``labels`` has the compose project.
- Not ``ListAllContainers``: it paginates (30 by default, ``limit: 0`` for all) and an
  unpaged call would silently drop containers on a fleet this size. One
  ``ListContainers`` per server also keeps one node's failure from hiding the others.

This is a read-only product (04 rule 4): ``_read`` refuses anything but the two request
types below, so no write or execute request can be sent from here by accident.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import httpx2

from ..scrub import scrub

READ_TYPES = frozenset({"ListServers", "ListContainers"})
CONTAINER_STATES = frozenset({"running", "created", "restarting", "stopping", "removing", "paused", "exited", "dead"})


class KomodoError(RuntimeError):
    """Komodo can't be read right now. The message is safe to show: it never holds a key."""


@dataclass(frozen=True)
class ServerStats:
    cpuPerc: float
    memUsedGb: float
    memTotalGb: float
    diskUsedGb: float
    diskTotalGb: float

    @property
    def memPerc(self) -> float:
        return 100.0 * self.memUsedGb / self.memTotalGb if self.memTotalGb > 0 else 0.0

    @property
    def diskPerc(self) -> float:
        return 100.0 * self.diskUsedGb / self.diskTotalGb if self.diskTotalGb > 0 else 0.0


@dataclass(frozen=True)
class KomodoServer:
    id: str
    name: str  # Komodo names its servers after the fleet's nodes (PERIPHERY_CONNECT_AS)
    state: str  # "ok", "notok", "disabled" or "unknown"
    err: str | None = None
    version: str | None = None
    stats: ServerStats | None = None


@dataclass(frozen=True)
class KomodoContainer:
    server: str
    name: str
    state: str  # "running", "exited" ... or "" when Komodo doesn't say
    status: str  # Docker's text: "Up 3 hours (healthy)", "Exited (137) 3 minutes ago"
    image: str | None = None
    id: str | None = None
    createdAt: int | None = None
    labels: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class KomodoSnapshot:
    servers: list[KomodoServer]
    containers: dict[str, list[KomodoContainer]]  # by server name; only servers that answered
    errors: dict[str, str]  # servers that were Ok but whose container list couldn't be read
    fetchedAt: datetime


def serverState(raw: Any) -> str:
    """serde writes ``NotOk``, strum's Display writes ``not-ok``: both mean "notok"."""
    word = "".join(ch for ch in str(raw).lower() if ch.isalpha())
    return word if word in {"ok", "notok", "disabled"} else "unknown"


class KomodoClient:
    def __init__(
        self,
        url: str,
        key: str,
        secret: str,
        *,
        transport: "httpx2.AsyncBaseTransport | None" = None,
        timeout: float = 10.0,
    ) -> None:
        if not (url and key and secret):
            raise ValueError("purr needs PERCH_PURR_URL, PERCH_PURR_KEY and PERCH_PURR_SECRET")
        self._secrets = [key, secret]
        self._http = httpx2.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"x-api-key": key, "x-api-secret": secret, "content-type": "application/json"},
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    # -- the one door -----------------------------------------------------------

    async def _read(self, kind: str, params: dict[str, Any]) -> list[Any]:
        if kind not in READ_TYPES:
            raise ValueError(f"purr is read-only: {kind!r} is not a request it may send")
        try:
            response = await self._http.post("/read", json={"type": kind, "params": params})
        except httpx2.HTTPError as exc:
            raise KomodoError(self._safe(f"can't reach Komodo ({type(exc).__name__}: {exc})")) from None
        if response.status_code in (401, 403):
            raise KomodoError(f"Komodo refused the API key (HTTP {response.status_code})")
        if response.status_code >= 400:
            raise KomodoError(self._safe(f"Komodo answered HTTP {response.status_code}: {response.text[:200]}"))
        try:
            answer = response.json()
        except ValueError:
            raise KomodoError("unexpected answer from Komodo: not JSON") from None
        if not isinstance(answer, list):
            raise KomodoError(f"unexpected answer from Komodo: {kind} did not return a list")
        return answer

    def _safe(self, text: str) -> str:
        return scrub(text, self._secrets, limit=400)

    # -- what purr asks ---------------------------------------------------------

    async def snapshot(self, now: datetime) -> KomodoSnapshot:
        """Every server, and the containers of each server that is Ok. Raises KomodoError
        when the server list itself can't be read; a single server's container list that
        fails is recorded in ``errors`` and the others carry on."""
        servers = [_server(item) for item in await self._read("ListServers", {})]
        ok = [s for s in servers if s.state == "ok"]
        answers = await asyncio.gather(*(self._containers(s.name) for s in ok), return_exceptions=True)
        containers: dict[str, list[KomodoContainer]] = {}
        errors: dict[str, str] = {}
        for server, answer in zip(ok, answers, strict=True):
            if isinstance(answer, KomodoError):
                errors[server.name] = str(answer)
            elif isinstance(answer, BaseException):
                raise answer
            else:
                containers[server.name] = answer
        return KomodoSnapshot(servers=servers, containers=containers, errors=errors, fetchedAt=now)

    async def _containers(self, server: str) -> list[KomodoContainer]:
        return [_container(server, item) for item in await self._read("ListContainers", {"server": server})]


# -- parsing: anything that isn't the shape above is a KomodoError, never a guess ----


def _unexpected(what: str) -> KomodoError:
    return KomodoError(f"unexpected answer from Komodo: {what}")


def _server(item: Any) -> KomodoServer:
    try:
        info = item.get("info") or {}
        err = info.get("err")
        stats = info.get("stats")
        return KomodoServer(
            id=str(item.get("id", "")),
            name=str(item["name"]),
            state=serverState(info.get("state")),
            err=(err.get("error") if isinstance(err, dict) else str(err)) if err else None,
            version=info.get("version"),
            stats=_stats(stats) if isinstance(stats, dict) else None,
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _unexpected("a server without a name") from None


def _stats(stats: dict[str, Any]) -> ServerStats:
    return ServerStats(
        cpuPerc=float(stats.get("cpu_perc", 0.0)),
        memUsedGb=float(stats.get("mem_used_gb", 0.0)),
        memTotalGb=float(stats.get("mem_total_gb", 0.0)),
        diskUsedGb=float(stats.get("disk_used_gb", 0.0)),
        diskTotalGb=float(stats.get("disk_total_gb", 0.0)),
    )


def _container(server: str, item: Any) -> KomodoContainer:
    try:
        state = str(item.get("state") or "").lower()
        labels = item.get("labels") or {}
        return KomodoContainer(
            server=server,
            name=str(item["name"]).lstrip("/"),
            state=state if state in CONTAINER_STATES else "",
            status=str(item.get("status") or ""),
            image=item.get("image"),
            id=item.get("id"),
            createdAt=item.get("created"),
            labels={str(k): str(v) for k, v in labels.items()},
        )
    except (KeyError, TypeError, ValueError, AttributeError):
        raise _unexpected("a container without a name") from None
