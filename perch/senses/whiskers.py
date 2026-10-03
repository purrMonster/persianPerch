"""whiskers: the smart home, from Home Assistant's WebSocket API (design plan 4.5, 05 plan Q14 and test S4, ADR 0009).

Read at 2026-10-03 from developers.home-assistant.io/docs/api/websocket: the server speaks first with
``{"type": "auth_required"}``; the client answers ``{"type": "auth", "access_token": ...}`` and gets
``auth_ok`` or ``auth_invalid``; after that every message carries an integer ``id``; ``subscribe_events``
with ``event_type: "state_changed"`` is acknowledged by a ``result`` and then ``event`` messages carry
``event.data.entity_id``, ``old_state`` and ``new_state``; ``get_states`` answers with a ``result`` holding
every state.

**What perch may say to Home Assistant** is three message types, ``auth``, ``subscribe_events`` and
``get_states`` (S4). There is one function that writes to the socket, ``Whiskers._send``, and it refuses
anything else: perch never calls a service, never pings with a message, never subscribes to anything but
``state_changed``. (The connection is kept alive by the WebSocket protocol's own ping frames, which are not
Home Assistant messages.) The token belongs to a non-admin Home Assistant user (Q14), is sent once per
connection and is never logged or shown (``scrub.py`` masks it, the leak check looks for it).

Only the entities in the owner's list are kept (``whiskers.example.yml``): every other state change is dropped
before it is judged or stored. Each listed entity is a state ``whiskers:<entity_id>`` whose level comes from
the list (a leak sensor ``on`` is a hiss, a door ``on`` an earTwitch); a change worth knowing is an event.

**Home Assistant unreachable** is never a hiss per entity. The listener reconnects with a growing pause; after
two failed collector cycles every entity turns ``unknown`` and no entity event is written; the collector's
own rhythm (collectors.py) says "whiskers is late: ..." once, as a tailFlick.
"""

from __future__ import annotations

import asyncio
import contextlib
import json
import logging
import random
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import yaml

from ..bodyLanguage import BodyLanguage as B
from ..rhythms import Rhythm
from ..scentTrail import ScentTrail
from ..words import duration

log = logging.getLogger("perch.whiskers")

PREFIX = "whiskers:"
ALLOWED_TYPES = frozenset({"auth", "subscribe_events", "get_states"})  # S4
EVENT_TYPE = "state_changed"
CONFIRM = 2  # failed collector cycles in a row before every entity is shown as unknown
BACKOFF = (1.0, 60.0)  # the reconnect pause grows from the first to the second
MAX_MESSAGE = 32 * 1024 * 1024  # get_states of a big house is a few MB
LEVEL_NAMES = {lv.value: lv for lv in B}
NOISY = (B.earTwitch, B.tailFlick, B.hiss)  # the levels that are worth an event


class WhiskersError(Exception):
    """Home Assistant can't be used right now; the message is safe to show (it never holds the token)."""


class ConfigError(ValueError):
    """The entity list isn't usable; says which entity and what is wrong."""


class ForbiddenMessage(Exception):  # noqa: N818 - a refusal, not an error to handle
    """perch tried to send Home Assistant something it is never allowed to send (S4)."""


@dataclass(frozen=True)
class Entity:
    id: str
    name: str
    levels: dict[str, B] = field(default_factory=dict)  # HA state -> level
    default: B = B.slowBlink  # any listed state not in ``levels``
    words: dict[str, str] = field(default_factory=dict)  # HA state -> what the page says ("on" -> "open")


def _key(value: Any) -> str:
    """YAML 1.1 reads a bare ``on`` and ``off`` as booleans; Home Assistant's states are the words."""
    if isinstance(value, bool):
        return "on" if value else "off"
    return str(value)


def _level(value: Any, where: str) -> B:
    found = LEVEL_NAMES.get(str(value))
    if found is None:
        raise ConfigError(f"{where}: {value!r} isn't a level (slowBlink, earTwitch, tailFlick, hiss or unknown)")
    return found


def parseConfig(text: str) -> dict[str, Entity]:
    """``whiskers.yml`` -> the allow-list. Anything not in it is dropped before it is stored."""
    try:
        data = yaml.safe_load(text) or {}
    except yaml.YAMLError as exc:
        raise ConfigError(f"not valid YAML: {str(exc).splitlines()[0] if str(exc) else 'unreadable'}") from exc
    entities = data.get("entities") if isinstance(data, dict) else None
    if not isinstance(entities, dict) or not entities:
        raise ConfigError("the file needs an `entities:` list with at least one entity")
    found: dict[str, Entity] = {}
    for raw, given in entities.items():
        eid = str(raw)
        if "." not in eid or " " in eid:
            raise ConfigError(f"{eid}: an entity id looks like `binary_sensor.front_door`")
        body = given or {}
        if not isinstance(body, dict):
            raise ConfigError(f"{eid}: needs `name`, `states` and optionally `default` and `words`")
        states = body.get("states") or {}
        words = body.get("words") or {}
        if not isinstance(states, dict) or not isinstance(words, dict):
            raise ConfigError(f"{eid}: `states` and `words` are maps from a Home Assistant state to a value")
        found[eid] = Entity(
            id=eid,
            name=str(body.get("name") or eid)[:80],
            levels={_key(k): _level(v, f"{eid}.states.{_key(k)}") for k, v in states.items()},
            default=_level(body.get("default", "slowBlink"), f"{eid}.default"),
            words={_key(k): str(v)[:40] for k, v in words.items()},
        )
    return found


def loadConfig(path: "str | Path") -> dict[str, Entity]:
    try:
        text = Path(path).read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"can't read the entity list ({exc.strerror or exc})") from exc
    return parseConfig(text)


def socketUrl(url: str) -> str:
    """``http://host:8123`` -> ``ws://host:8123/api/websocket`` (https -> wss); a ws(s) URL keeps its path."""
    parts = urlsplit(url.strip())
    scheme = {"http": "ws", "https": "wss"}.get(parts.scheme, parts.scheme)
    if scheme not in ("ws", "wss") or not parts.netloc:
        raise ValueError("PERCH_WHISKERS_URL must be an http(s):// or ws(s):// address")
    path = parts.path if parts.path.strip("/") else "/api/websocket"
    return urlunsplit((scheme, parts.netloc, path, "", ""))


def connectDefault(url: str):
    """The real WebSocket client (ADR 0009). Imported here so a perch with no whiskers never loads it."""
    from websockets.asyncio.client import connect

    return connect(url, max_size=MAX_MESSAGE, open_timeout=10, ping_interval=20, ping_timeout=20)


class Whiskers:
    name = "whiskers"

    def __init__(
        self,
        url: str,
        token: str,
        entities: dict[str, Entity],
        trail: ScentTrail,
        *,
        clock: Callable[[], datetime],
        every: int = 30,
        connect: Callable[[str], Any] = connectDefault,
    ) -> None:
        if not token:
            raise ValueError("PERCH_WHISKERS_TOKEN is not set")
        self.url = socketUrl(url)
        self._token = token
        self.entities = entities
        self.trail = trail
        self.clock = clock
        self.rhythm = Rhythm(every=every)
        self._connect = connect
        self._task: asyncio.Task | None = None
        self._ready = asyncio.Event()
        self._why = "not connected yet"
        self._blind = 0
        self._ids = 0
        self._known: dict[str, tuple[str | None, B]] = {}  # entity -> (last real HA state, its level)

    # -- the collector's side -------------------------------------------------------------------

    async def aclose(self) -> None:
        task, self._task = self._task, None
        if task:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def cycle(self) -> None:
        """Is the listener connected and up to date? The first cycle waits a few seconds for it."""
        if self._task is None or self._task.done():
            self._task = asyncio.create_task(self._listen())
            with contextlib.suppress(TimeoutError):
                await asyncio.wait_for(self._ready.wait(), 5)
        if self._ready.is_set():
            self._blind = 0
            return
        self._goBlind(self.clock())
        raise WhiskersError(self._why)

    def _goBlind(self, now: datetime) -> None:
        """Two failed cycles in a row and every entity turns ``unknown`` (stale green is worse than grey). No
        events: the collector's rhythm raises the one tailFlick."""
        self._blind += 1
        if self._blind < CONFIRM:
            return
        for subject, state in self.trail.states().items():
            if subject.startswith(PREFIX) and state.bodyLanguage is not B.unknown:
                self.trail.setState(
                    subject, B.unknown, title="Home Assistant isn't answering", detail=state.detail, seenAt=now
                )

    # -- the one way to talk to Home Assistant ----------------------------------------------------

    async def _send(self, ws: Any, message: dict) -> None:
        """Every message perch sends goes through here, and only three kinds may (S4)."""
        kind = message.get("type")
        if kind not in ALLOWED_TYPES:
            raise ForbiddenMessage(f"perch never sends {kind!r} to Home Assistant")
        if kind == "subscribe_events" and message.get("event_type") != EVENT_TYPE:
            raise ForbiddenMessage("perch only subscribes to state_changed")
        await ws.send(json.dumps(message))

    def _next(self) -> int:
        self._ids += 1
        return self._ids

    async def _recv(self, ws: Any, timeout: float = 15) -> dict:
        raw = await asyncio.wait_for(ws.recv(), timeout)
        try:
            message = json.loads(raw)
        except ValueError as exc:
            raise WhiskersError("Home Assistant sent something that isn't JSON") from exc
        if not isinstance(message, dict):
            raise WhiskersError("Home Assistant sent something unexpected")
        return message

    # -- one connection ---------------------------------------------------------------------------

    async def _listen(self) -> None:
        pause = BACKOFF[0]
        self._known = self._loadKnown()
        while True:
            try:
                async with self._connect(self.url) as ws:
                    await self._session(ws)
                    pause = BACKOFF[0]
                self._lost("Home Assistant closed the connection")
            except asyncio.CancelledError:
                raise
            except WhiskersError as exc:
                self._lost(str(exc))
            except ForbiddenMessage:
                raise  # a bug: never retried, never hidden (the task ends, the cycle says so)
            except Exception as exc:  # a refused or dropped connection, a timeout: say what kind, not where
                self._lost(f"{type(exc).__name__}: can't reach Home Assistant")
            self._ready.clear()
            await asyncio.sleep(pause * random.uniform(0.8, 1.2))  # noqa: S311 - spreading retries
            pause = min(pause * 2, BACKOFF[1])

    def _lost(self, why: str) -> None:
        if why != self._why:
            log.warning("whiskers: %s", why)
        self._why = why

    async def _session(self, ws: Any) -> None:
        hello = await self._recv(ws)
        if hello.get("type") != "auth_required":
            raise WhiskersError("that isn't Home Assistant's WebSocket (no auth_required)")
        await self._send(ws, {"type": "auth", "access_token": self._token})
        answer = await self._recv(ws)
        if answer.get("type") == "auth_invalid":
            raise WhiskersError("Home Assistant refused the token (PERCH_WHISKERS_TOKEN)")
        if answer.get("type") != "auth_ok":
            raise WhiskersError("Home Assistant's answer to the token wasn't auth_ok")
        # subscribe first, then ask for every state: a change between the two is seen twice, never missed
        subscribe = self._next()
        await self._send(ws, {"id": subscribe, "type": "subscribe_events", "event_type": EVENT_TYPE})
        await self._expect(ws, subscribe)
        snapshot = self._next()
        await self._send(ws, {"id": snapshot, "type": "get_states"})
        states = await self._expect(ws, snapshot)
        self._snapshot(states if isinstance(states, list) else [], self.clock())
        self._why = "connected"
        self._ready.set()
        while True:
            message = await self._recv(ws, timeout=3600)
            if message.get("type") == "event":
                self._event(message)

    async def _expect(self, ws: Any, wanted: int) -> Any:
        """The ``result`` for message ``wanted``; events that arrive meanwhile are handled as they come."""
        while True:
            message = await self._recv(ws)
            if message.get("type") == "event":
                self._event(message)
            elif message.get("type") == "result" and message.get("id") == wanted:
                if not message.get("success"):
                    raise WhiskersError("Home Assistant refused a request (is the user allowed to read states?)")
                return message.get("result")

    # -- judging ----------------------------------------------------------------------------------

    def _loadKnown(self) -> dict[str, tuple[str | None, B]]:
        known: dict[str, tuple[str | None, B]] = {}
        for subject, state in self.trail.states().items():
            if subject.startswith(PREFIX):
                detail = state.detail or {}
                level = B(detail["level"]) if detail.get("level") in LEVEL_NAMES else state.bodyLanguage
                known[subject[len(PREFIX) :]] = (detail.get("state"), level)
        return known

    def _snapshot(self, states: list, now: datetime) -> None:
        listed = {s.get("entity_id"): s.get("state") for s in states if isinstance(s, dict)}
        for entity in self.entities.values():
            self._apply(entity, listed.get(entity.id), now, present=entity.id in listed)
        gone = [s for s in self.trail.states() if s.startswith(PREFIX) and s[len(PREFIX) :] not in self.entities]
        self.trail.forget(gone)

    def _event(self, message: dict) -> None:
        """One ``state_changed``. Everything not on the owner's list is dropped here, unread."""
        data = (message.get("event") or {}).get("data")
        entity = self.entities.get(data.get("entity_id")) if isinstance(data, dict) else None
        if entity is None:
            return
        new = data.get("new_state")
        self._apply(entity, new.get("state") if isinstance(new, dict) else None, self.clock(), present=new is not None)

    def judge(self, entity: Entity, state: str | None, present: bool) -> tuple[B, str]:
        if not present or state is None:
            return B.unknown, "Home Assistant doesn't list it"
        level = entity.levels.get(state)
        if level is None:
            level = B.unknown if state in ("unavailable", "unknown") else entity.default
        return level, entity.words.get(state, state)

    def _apply(self, entity: Entity, state: str | None, now: datetime, *, present: bool = True) -> None:
        level, word = self.judge(entity, state, present)
        subject = PREFIX + entity.id
        before = self.trail.states().get(subject)
        title = f"{entity.name}: {word}"
        self.trail.setState(
            subject,
            level,
            title=title,
            detail={"entity": entity.id, "name": entity.name, "state": state, "word": word, "level": level.value},
            seenAt=now,
        )
        lastState, lastLevel = self._known.get(entity.id, (None, B.slowBlink))
        self._known[entity.id] = (state, level)
        if state == lastState or level is B.unknown:
            return
        if level in NOISY:
            detail = {"entity": entity.id, "state": state}
            self.trail.addEvent("whiskers", subject, level, title, detail=detail, seenAt=now)
        elif lastLevel in NOISY and before is not None:
            lasted = duration((now - before.since).total_seconds()) if before.bodyLanguage is lastLevel else "a while"
            self.trail.addEvent(
                "whiskers", subject, level, f"{title} (was {lastLevel.value} for {lasted})",
                detail={"entity": entity.id, "state": state}, seenAt=now,
            )  # fmt: skip

