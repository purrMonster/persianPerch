"""A Komodo Core for scenario tests, built from the pinned fleet repo: every node is a
server, every ``container_name`` of every app a container, all healthy at the start.

It answers ``POST /read`` with the shapes in ``tests/fixtures/komodo`` and renders each
container's ``status`` the way Docker does ("Up 3 hours (healthy)"), so purr reads the same
words it will read on the real fleet. Drive it with the methods below and a FakeClock.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timedelta

import httpx2

from perch.catTree import Fleet
from perch.senses.komodo import KomodoClient

KEY, SECRET = "K-fake-key-for-tests", "S-fake-secret-for-tests"


def humanDuration(seconds: float) -> str:  # noqa: PLR0911 - go-units' own if-chain
    """go-units' HumanDuration, which Docker uses for "Up ..." and "Exited ... ago"."""
    s = int(seconds)
    if s < 1:
        return "Less than a second"
    if s == 1:
        return "1 second"
    if s < 60:
        return f"{s} seconds"
    minutes = s // 60
    if minutes == 1:
        return "About a minute"
    if minutes < 60:
        return f"{minutes} minutes"
    hours = int(s / 3600 + 0.5)
    if hours == 1:
        return "About an hour"
    if hours < 48:
        return f"{hours} hours"
    if hours < 24 * 7 * 2:
        return f"{hours // 24} days"
    if hours < 24 * 30 * 2:
        return f"{hours // 24 // 7} weeks"
    if hours < 24 * 365 * 2:
        return f"{hours // 24 // 30} months"
    return f"{s // 3600 // 24 // 365} years"


@dataclass
class Box:
    name: str
    project: str | None
    id: str
    state: str = "running"  # Docker's states
    health: str | None = "healthy"
    exitCode: int = 0
    since: datetime | None = None  # when it started, or when it stopped


class FleetFake:
    def __init__(self, fleet: Fleet, clock) -> None:
        self.clock = clock
        self.requests: list[dict] = []
        self.servers: dict[str, dict] = {}
        self.boxes: dict[str, dict[str, Box]] = {}
        self.komodoDown = False
        self.unreadable: set[str] = set()  # nodes whose ListContainers fails
        self.spelling: dict[str, str] = {}  # node -> how Komodo spells its server's name
        self._ids = 0
        for node in fleet.nodes:
            self.servers[node.name] = {"state": "Ok", "cpu": 20.0, "mem": 40.0, "disk": 50.0}
            self.boxes[node.name] = {}
            for app in node.apps:
                for name in app.containers:
                    self.add(node.name, name, project=app.name)

    # -- the world -------------------------------------------------------------------

    def _newId(self) -> str:
        self._ids += 1
        return f"{self._ids:064x}"

    def add(self, node: str, name: str, project: str | None = None) -> Box:
        box = Box(name, project, self._newId(), since=self.clock() - timedelta(days=2))
        self.boxes[node][name] = box
        return box

    def box(self, node: str, name: str) -> Box:
        return self.boxes[node][name]

    def exit(self, node: str, name: str, code: int = 137) -> None:
        box = self.box(node, name)
        box.state, box.exitCode, box.since = "exited", code, self.clock()

    def start(self, node: str, name: str) -> None:
        box = self.box(node, name)
        box.state, box.health, box.since = "running", "healthy", self.clock()

    def restart(self, node: str, name: str) -> None:
        """A crash and restart: the same container, uptime back to zero."""
        box = self.box(node, name)
        box.state, box.since = "running", self.clock()

    def recreate(self, node: str, name: str) -> None:
        """A redeploy: a new container under the same name."""
        box = self.box(node, name)
        box.id, box.state, box.health, box.since = self._newId(), "running", "healthy", self.clock()

    def crashloop(self, node: str, name: str, code: int = 1) -> None:
        box = self.box(node, name)
        box.state, box.exitCode, box.since = "restarting", code, self.clock()

    def setHealth(self, node: str, name: str, health: str | None) -> None:
        self.box(node, name).health = health

    def remove(self, node: str, name: str) -> None:
        del self.boxes[node][name]

    def nodeDown(self, node: str) -> None:
        self.servers[node]["state"] = "NotOk"

    def nodeUp(self, node: str) -> None:
        self.servers[node]["state"] = "Ok"

    def vitals(self, node: str, **kw: float) -> None:
        self.servers[node].update(kw)

    # -- Komodo ------------------------------------------------------------------------

    def _status(self, box: Box) -> str:
        age = (self.clock() - (box.since or self.clock())).total_seconds()
        if box.state == "running":
            health = f" ({box.health})" if box.health else ""
            return f"Up {humanDuration(age)}{health}"
        if box.state == "exited":
            return f"Exited ({box.exitCode}) {humanDuration(age)} ago"
        if box.state == "restarting":
            return f"Restarting ({box.exitCode}) {humanDuration(age)} ago"
        return box.state.capitalize()

    def _container(self, node: str, box: Box) -> dict:
        return {
            "server_name": node,
            "name": box.name,
            "id": box.id,
            "image": f"example/{box.name}:1",
            "created": 1789900000,
            "state": box.state,
            "status": self._status(box),
            "networks": [],
            "ports": [],
            "volumes": [],
            "stats": None,
            "labels": {"com.docker.compose.project": box.project} if box.project else {},
        }

    def _server(self, name: str, info: dict) -> dict:
        ok = info["state"] == "Ok"
        stats = (
            {
                "cpu_perc": info["cpu"],
                "mem_used_gb": 16.0 * info["mem"] / 100,
                "mem_total_gb": 16.0,
                "disk_used_gb": 500.0 * info["disk"] / 100,
                "disk_total_gb": 500.0,
            }
            if ok
            else None
        )
        err = None if ok else {"error": "Periphery is not connected", "trace": []}
        return {
            "id": f"srv-{name}",
            "type": "Server",
            "name": self.spelling.get(name, name),
            "template": False,
            "tags": [],
            "info": {"state": info["state"], "err": err, "stats": stats, "version": "2.3.2"},
        }

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        body = json.loads(request.content)
        self.requests.append({"path": request.url.path, **body})
        if self.komodoDown:
            raise httpx2.ConnectError("connection refused")
        if body["type"] == "ListServers":
            return httpx2.Response(200, json=[self._server(n, i) for n, i in self.servers.items()])
        if body["type"] == "ListContainers":
            asked = body["params"]["server"]
            node = next((n for n in self.servers if self.spelling.get(n, n) == asked), asked)
            if node in self.unreadable:
                return httpx2.Response(500, text="periphery went away")
            return httpx2.Response(200, json=[self._container(node, b) for b in self.boxes[node].values()])
        return httpx2.Response(400, text="unknown request")

    def client(self) -> KomodoClient:
        return KomodoClient("http://komodo-core:9120", KEY, SECRET, transport=httpx2.MockTransport(self))
