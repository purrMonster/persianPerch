"""pounce, perch's half (design plan 4.4, 05 plan M5): what kitten's filesystem watching reports.

kitten sends facts (a watched path, a name, a change, the level its watch is worth and why); perch decides
what is believable and writes the words. Names and change types only: there is nowhere in an event for a
file's contents, and a name is scrubbed like any title.

- the level is clamped to **tailFlick**: a changed file is never a hiss (design plan 4.4 gives earTwitch and
  tailFlick only);
- an event is an *event*, not a state: a file dropped has no "now" to keep, so pounce adds no subject to the
  rollup and meow, which reads states, does not push it. A change under ``/etc/purrbrews`` is a line in meow's
  07:30 digest and never a push (owner, 2026-10-03, ADR 0010);
- a resent event (kitten asks again when it didn't hear the answer) is stored once: perch remembers the last
  few thousand event ids per node, in memory.
"""

from __future__ import annotations

import re
from collections import OrderedDict
from datetime import UTC, datetime, timedelta

from ..bodyLanguage import BodyLanguage as B
from ..scentTrail import ScentTrail
from .groom import RecordError

CHANGES = {"created": "appeared", "modified": "changed", "deleted": "was removed", "storm": "storm"}
LEVELS = {"slowBlink": B.slowBlink, "earTwitch": B.earTwitch, "tailFlick": B.tailFlick}
MAX_EVENTS = 100
ID = re.compile(r"^[0-9a-f]{6,32}$")
REMEMBER = 4000


def _text(event: dict, key: str, limit: int, *, required: bool = False) -> str:
    value = event.get(key, "")
    if value is None:
        value = ""
    if not isinstance(value, str):
        raise RecordError(f"{key} must be text")
    if required and not value.strip():
        raise RecordError(f"{key} is missing")
    return value.replace("\n", " ").replace("\r", " ")[:limit]


def parseEvent(event: object, now: datetime) -> dict:
    """Check one event from kitten; the cleaned fields, or ``RecordError`` saying what is wrong."""
    if not isinstance(event, dict):
        raise RecordError("an event must be an object")
    eventId = _text(event, "id", 32, required=True)
    if not ID.match(eventId):
        raise RecordError("id must be hex")
    change = _text(event, "change", 12, required=True)
    if change not in CHANGES:
        raise RecordError(f"unknown change {change!r}")
    level = LEVELS.get(_text(event, "level", 12) or "earTwitch")
    if level is None:
        raise RecordError("unknown level")
    try:
        at = datetime.strptime(_text(event, "at", 24, required=True), "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        raise RecordError("at must be YYYY-MM-DDTHH:MM:SSZ") from exc
    if not now - timedelta(days=2) <= at <= now + timedelta(minutes=5):
        at = now  # a node whose clock is off still gets its event, at the time perch heard it
    return {
        "id": eventId,
        "at": at,
        "path": _text(event, "path", 300, required=True),
        "name": _text(event, "name", 300),
        "change": change,
        "level": level,
        "why": _text(event, "why", 80) or "changed",
        "commit": _text(event, "commit", 200),
    }


def title(event: dict) -> str:
    """The sentence the trail shows. Typographic quotes only around the commit subject, which perch quotes."""
    if event["change"] == "storm":
        return f"{event['path']}: more than 60 changes in a minute; the rest are not listed until it calms down"
    if event["commit"] or event["why"] == "the node pulled":
        subject = f": “{event['commit']}”" if event["commit"] else ""
        return f"{event['why']}{subject}"
    return f"{event['why']}: {event['name'] or event['path']} {CHANGES[event['change']]}"


class Pounce:
    """Stores what kitten reports. One instance per perch."""

    def __init__(self, trail: ScentTrail) -> None:
        self.trail = trail
        self._seen: OrderedDict[tuple[str, str], None] = OrderedDict()

    def ingest(self, node: str, events: list[dict]) -> list[str]:
        """Store events; returns the ids now stored (kitten stops resending those). The subject of an event is
        ``pounce:<node>/<watched path>``."""
        stored = []
        for event in events:
            key = (node, event["id"])
            if key in self._seen:
                stored.append(event["id"])
                continue
            level = event["level"] if event["level"].rank <= B.tailFlick.rank else B.tailFlick
            if event["change"] == "storm":
                level = B.tailFlick
            self.trail.addEvent(
                "pounce",
                f"pounce:{node}/{event['path']}",
                level,
                title(event),
                detail={
                    "node": node,
                    "path": event["path"],
                    "name": event["name"],
                    "change": event["change"],
                    **({"commit": event["commit"]} if event["commit"] else {}),
                },
                seenAt=event["at"],
            )
            self._seen[key] = None
            while len(self._seen) > REMEMBER:
                self._seen.popitem(last=False)
            stored.append(event["id"])
        return stored
