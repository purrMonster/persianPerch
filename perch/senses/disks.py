"""disks: drive health, from Scrutiny (05 plan M4, C6).

One ``cycle`` reads Scrutiny (``scrutiny.py``) and writes a state ``disk:<host>/<device>`` per drive and an
event when something a person should know about changes. Scrutiny's own verdicts are the rules (runbook
2026-10-03 records the mapping):

- the device failed (``device_status`` != 0: SMART itself says failing, or Scrutiny's thresholds do) -> **hiss**;
- the device passes but an attribute is in Scrutiny's warning band -> **tailFlick**;
- no SMART report for 3 days (Scrutiny's collector runs daily) -> tailFlick: a drive nobody is watching;
- otherwise slowBlink, with the temperature and the power-on hours in the title.

**Power-on hours come from SMART attribute 9** (NVMe: ``power_on_hours``) when the details carry it; the
summary's figure is used only when they don't. They disagree on at least one disk in the fleet.

Scrutiny unreachable: after two failed cycles every disk is ``unknown``; the collector rhythm raises the one
tailFlick ("disks is late: can't see Scrutiny ..."). A drive that disappears from Scrutiny is forgotten.
A drive's node is the host Scrutiny's collector reported it from (``host_id``); it counts toward that node
when the name is a node of the fleet, and toward the fleet otherwise.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from ..bodyLanguage import BodyLanguage as B
from ..rhythms import Rhythm
from ..scentTrail import ScentTrail, State
from ..words import duration
from .scrutiny import DEVICE_FAILED_SCRUTINY, DEVICE_FAILED_SMART, Disk, ScrutinyError

PREFIX = "disk:"
STALE = timedelta(days=3)
CONFIRM = 2


def subjectFor(disk: Disk, taken: set[str]) -> str:
    host = disk.host or "scrutiny"
    base = f"{PREFIX}{host}/{disk.name}"
    return base if base not in taken else f"{base}-{disk.wwn[-6:]}"


def hoursText(hours: int | None) -> str:
    if hours is None:
        return "power-on hours unknown"
    if hours < 1000:
        return f"{hours} h powered on"
    return f"{hours // 24} d powered on"


def sizeText(capacity: int) -> str:
    if capacity <= 0:
        return ""
    tb = capacity / 1e12
    return f"{tb:.1f} TB" if tb >= 1 else f"{capacity / 1e9:.0f} GB"


class Disks:
    name = "disks"

    def __init__(self, scrutiny: Any, trail: ScentTrail, *, clock, every: int = 900) -> None:
        self.scrutiny = scrutiny
        self.trail = trail
        self.clock = clock
        self.rhythm = Rhythm(every=every)
        self._blind = 0

    async def aclose(self) -> None:
        await self.scrutiny.aclose()

    async def cycle(self) -> None:
        now = self.clock()
        try:
            disks = await self.scrutiny.disks()
        except ScrutinyError:
            self._goBlind(now)
            raise
        self._blind = 0
        prev = {s: st for s, st in self.trail.states().items() if s.startswith(PREFIX)}
        taken: set[str] = set()
        for disk in disks:
            subject = subjectFor(disk, taken)
            taken.add(subject)
            self._disk(subject, disk, prev.get(subject), now)
        self.trail.forget([s for s in prev if s not in taken])

    def _goBlind(self, now: datetime) -> None:
        self._blind += 1
        if self._blind < CONFIRM:
            return
        for subject, state in self.trail.states().items():
            if subject.startswith(PREFIX) and state.bodyLanguage is not B.unknown:
                self.trail.setState(
                    subject, B.unknown, title="Scrutiny isn't answering", detail=state.detail, seenAt=now
                )

    def _disk(self, subject: str, disk: Disk, before: State | None, now: datetime) -> None:
        level, title = self._judge(disk, now)
        detail: dict[str, Any] = {
            "host": disk.host,
            "device": disk.name,
            "model": disk.model,
            "protocol": disk.protocol,
            "capacityBytes": disk.capacityBytes,
            "tempC": disk.tempC,
            "powerOnHours": disk.powerOnHours,
            "hoursSource": (
                "SMART attribute " + ("power_on_hours" if disk.protocol.lower() == "nvme" else "9")
                if disk.attributeHours is not None
                else "Scrutiny summary"
            ),
            "summaryHours": disk.summaryHours,
            "deviceStatus": disk.deviceStatus,
            "collectedAt": disk.collectedAt.isoformat() if disk.collectedAt else None,
            "warnings": [a.name for a in disk.warnings],
            "failures": [a.name for a in disk.failures],
        }
        self.trail.setState(subject, level, title=title, detail=detail, seenAt=now)
        label = f"{disk.model or disk.name} ({disk.name} on {disk.host or 'an unnamed host'})"
        if level.rank >= B.tailFlick.rank and (before is None or before.bodyLanguage is not level):
            self.trail.addEvent("purr", subject, level, f"{label}: {title}", detail=detail, seenAt=now)
        elif level is B.slowBlink and before and before.bodyLanguage.rank >= B.tailFlick.rank:
            lasted = duration((now - before.since).total_seconds())
            self.trail.addEvent(
                "purr",
                subject,
                B.slowBlink,
                f"{label} is back (was {before.bodyLanguage.value} for {lasted})",
                detail=detail,
                seenAt=now,
            )

    @staticmethod
    def _judge(disk: Disk, now: datetime) -> tuple[B, str]:
        if disk.deviceStatus:
            words = []
            if disk.deviceStatus & DEVICE_FAILED_SMART:
                words.append("SMART reports the drive failing")
            if disk.deviceStatus & DEVICE_FAILED_SCRUTINY:
                words.append("Scrutiny's thresholds failed")
            names = ", ".join(a.name for a in disk.failures[:3])
            return B.hiss, "; ".join(words) + (f" ({names})" if names else "")
        if disk.warnings:
            names = ", ".join(a.name for a in disk.warnings[:3])
            more = f" and {len(disk.warnings) - 3} more" if len(disk.warnings) > 3 else ""
            return B.tailFlick, f"Scrutiny warns about {names}{more}"
        if disk.collectedAt is None:
            return B.unknown, "Scrutiny has no SMART report for it yet"
        if now - disk.collectedAt > STALE:
            return B.tailFlick, f"no SMART report for {duration((now - disk.collectedAt).total_seconds())}"
        parts = [x for x in (sizeText(disk.capacityBytes), hoursText(disk.powerOnHours)) if x]
        if disk.tempC is not None:
            parts.insert(0, f"{disk.tempC} C")
        return B.slowBlink, "healthy, " + ", ".join(parts)
