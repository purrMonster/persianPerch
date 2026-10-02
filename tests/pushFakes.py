"""Fake ntfy and fake healthchecks.io servers for M3 (the real ones are never contacted): httpx2
MockTransports that record what they were sent and can be told to fail, like tests/komodoFake.py."""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from typing import Any

import httpx2

from perch.ntfy import Ntfy

NTFY_URL = "https://ntfy.example.home.arpa/fake-alerts-topic"
NTFY_TOKEN = "tk_fakefakefake"
CRITICAL_URL = "https://ntfy.example.home.arpa/fake-critical-topic-not-real"  # stands in for ntfy.sh
PING_URL = "https://hc-ping.example.home.arpa/00000000-fake-uuid-not-real-000000000000"


@dataclass
class Sent:
    topic: str
    title: str
    message: str
    priority: int
    tags: list[str]
    actions: list[dict[str, Any]]
    auth: str


@dataclass
class NtfyFake:
    """One ntfy server. ``token`` set: a publish without it is a 401. ``down``: connection refused."""

    token: str = ""
    down: bool = False
    status: int = 200
    sent: list[Sent] = field(default_factory=list)

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if self.down:
            raise httpx2.ConnectError("connection refused")
        auth = request.headers.get("authorization", "")
        if self.token and auth != f"Bearer {self.token}":
            return httpx2.Response(401, json={"error": "unauthorized"})
        if self.status != 200:
            return httpx2.Response(self.status, text="nope")
        body = json.loads(request.content)
        self.sent.append(
            Sent(
                body["topic"],
                body["title"],
                body["message"],
                body.get("priority", 3),
                body.get("tags", []),
                body.get("actions", []),
                auth,
            )
        )
        return httpx2.Response(200, json={"id": f"fake{len(self.sent)}", "topic": body["topic"]})

    def client(self, url: str = NTFY_URL, token: str = "") -> Ntfy:
        return Ntfy(url, token, transport=httpx2.MockTransport(self))

    def titles(self) -> list[str]:
        return [s.title for s in self.sent]


@dataclass
class HealthchecksFake:
    pings: list[tuple[str, str]] = field(default_factory=list)  # (method, path)
    down: bool = False

    def __call__(self, request: httpx2.Request) -> httpx2.Response:
        if self.down:
            raise httpx2.ConnectError("connection refused")
        self.pings.append((request.method, request.url.path))
        return httpx2.Response(200, text="OK")

    def transport(self) -> httpx2.MockTransport:
        return httpx2.MockTransport(self)
