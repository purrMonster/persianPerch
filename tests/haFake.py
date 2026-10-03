"""A fake Home Assistant WebSocket server, on loopback (M5, whiskers). It speaks the protocol as the docs
describe it (developers.home-assistant.io/docs/api/websocket, read 2026-10-03): auth_required, auth,
auth_ok or auth_invalid, then ``subscribe_events`` and ``get_states`` with ``result`` messages, and
``event`` messages for ``state_changed``. It records every message the client sends, so a test can prove
perch said nothing else (S4). No real Home Assistant is ever contacted.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

from websockets.asyncio.server import serve

# JWT-shaped, like a real long-lived token, but made up
TOKEN = "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJmYWtlLWhhLW5vdC1yZWFsIn0.fake-signature-not-real-0123456789abcdef"


class HAFake:
    def __init__(self, token: str = TOKEN) -> None:
        self.token = token
        self.states: dict[str, str] = {}
        self.received: list[dict] = []
        self.connections: list[Any] = []
        self.subscribed: list[Any] = []
        self.port = 0
        self.refuseToken = False
        self._server = None
        self.connects = 0
        self._subscriptionId: dict[int, int] = {}

    @property
    def url(self) -> str:
        return f"ws://127.0.0.1:{self.port}/api/websocket"

    async def start(self) -> None:
        self._server = await serve(self._handler, "127.0.0.1", self.port)
        self.port = self._server.sockets[0].getsockname()[1]

    async def stop(self) -> None:
        """Home Assistant goes away: the listener closes and every connection drops."""
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            self._server = None
        for ws in list(self.connections):
            await ws.close()

    async def drop(self) -> None:
        """Only the connections end; the server still answers a new one."""
        for ws in list(self.connections):
            await ws.close()

    def set(self, entity: str, state: str) -> None:
        self.states[entity] = state

    async def change(self, entity: str, state: str) -> None:
        old = self.states.get(entity)
        self.states[entity] = state
        message = {
            "type": "event",
            "event": {
                "event_type": "state_changed",
                "data": {
                    "entity_id": entity,
                    "old_state": {"entity_id": entity, "state": old},
                    "new_state": {"entity_id": entity, "state": state, "attributes": {"friendly_name": "x"}},
                },
            },
        }
        for ws in list(self.subscribed):
            await ws.send(json.dumps({**message, "id": self._subscriptionId.get(id(ws), 1)}))

    def types(self) -> list[str]:
        return [m.get("type", "") for m in self.received]

    async def _handler(self, ws) -> None:
        self.connects += 1
        self.connections.append(ws)
        try:
            await ws.send(json.dumps({"type": "auth_required", "ha_version": "2026.10.0"}))
            hello = json.loads(await ws.recv())
            self.received.append(hello)
            if hello.get("type") != "auth" or hello.get("access_token") != self.token or self.refuseToken:
                await ws.send(json.dumps({"type": "auth_invalid", "message": "Invalid access token or password"}))
                return
            await ws.send(json.dumps({"type": "auth_ok", "ha_version": "2026.10.0"}))
            async for raw in ws:
                message = json.loads(raw)
                self.received.append(message)
                kind = message.get("type")
                if kind == "subscribe_events":
                    self.subscribed.append(ws)
                    self._subscriptionId[id(ws)] = message["id"]
                    await ws.send(json.dumps({"id": message["id"], "type": "result", "success": True, "result": None}))
                elif kind == "get_states":
                    found = [{"entity_id": e, "state": s, "attributes": {}} for e, s in self.states.items()]
                    await ws.send(json.dumps({"id": message["id"], "type": "result", "success": True, "result": found}))
                else:  # a real Home Assistant would run it; the fake only notes that it was asked
                    await ws.send(json.dumps({"id": message.get("id", 0), "type": "result", "success": True}))
        except Exception:  # noqa: S110 - a client that goes away mid-message is the point of some tests
            pass
        finally:
            if ws in self.connections:
                self.connections.remove(ws)
            if ws in self.subscribed:
                self.subscribed.remove(ws)


async def settle(seconds: float = 0.3) -> None:
    await asyncio.sleep(seconds)
