"""dockerStatus: what Docker's own status text says.

Komodo's container list has ``state`` (running, exited ...) as a field but passes health,
uptime and the exit code only inside Docker's human-readable ``status`` ("Up 3 hours
(healthy)", "Exited (137) 3 minutes ago"). The words come from go-units' HumanDuration,
which rounds, so an uptime is only good for comparing with an earlier one of the same
process: it never goes down unless the container restarted (purr relies on that).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

_UP = re.compile(r"^Up\s+(?P<duration>[^()]+?)\s*(?:\((?P<note>[^)]*)\))?\s*$")
_EXIT = re.compile(r"^(?:Exited|Restarting)\s+\((?P<code>-?\d+)\)")
_DURATION = re.compile(r"^(?P<n>\d+)\s+(?P<unit>second|minute|hour|day|week|month|year)s?$")
_UNIT_SECONDS = {
    "second": 1,
    "minute": 60,
    "hour": 3600,
    "day": 86400,
    "week": 7 * 86400,
    "month": 30 * 86400,
    "year": 365 * 86400,
}

EXIT_MEANINGS = {
    0: "stopped cleanly",
    1: "the app reported an error",
    2: "the command was misused",
    125: "Docker couldn't run it",
    126: "the command can't be run",
    127: "the command wasn't found",
    137: "killed, often out of memory",
    139: "crashed (segmentation fault)",
    143: "terminated",
}


@dataclass(frozen=True)
class DockerStatus:
    uptime: int | None = None  # seconds, as Docker words it (rounded)
    health: str | None = None  # "healthy", "unhealthy" or "starting"
    paused: bool = False
    exitCode: int | None = None


def _seconds(words: str) -> int | None:
    words = words.strip()
    if words == "Less than a second":
        return 0
    if words == "About a minute":
        return 60
    if words == "About an hour":
        return 3600
    match = _DURATION.match(words)
    return int(match["n"]) * _UNIT_SECONDS[match["unit"]] if match else None


def parseStatus(text: str | None) -> DockerStatus:
    text = (text or "").strip()
    up = _UP.match(text)
    if up:
        uptime = _seconds(up["duration"])
        note = (up["note"] or "").strip().lower()
        if uptime is None:
            return DockerStatus()
        if note == "paused":
            return DockerStatus(uptime=uptime, paused=True)
        health = {"healthy": "healthy", "unhealthy": "unhealthy", "health: starting": "starting"}.get(note)
        return DockerStatus(uptime=uptime, health=health)
    exited = _EXIT.match(text)
    return DockerStatus(exitCode=int(exited["code"])) if exited else DockerStatus()


def exitMeaning(code: int | None) -> str:
    if code is None:
        return ""
    return EXIT_MEANINGS.get(code, f"exit code {code}")
