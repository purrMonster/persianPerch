"""scrutiny: the one module that knows Scrutiny's API (05 plan M4, C6; Scrutiny v0.9.3, the fleet's pin).

Read from the v0.9.3 source (``webapp/backend`` in github.com/AnalogJ/scrutiny), no credential (Scrutiny has
none; perch reaches it on ``cellar_net``):

- ``GET /api/summary`` -> ``{"success": true, "data": {"summary": {<wwn>: {"device": {...}, "smart":
  {"collector_date", "temp", "power_on_hours"}}}}}``. ``device`` carries ``wwn``, ``device_name`` (``sda``),
  ``host_id``, ``model_name``, ``serial_number``, ``device_protocol`` (``ATA``, ``NVMe``, ``SCSI``),
  ``capacity``, ``archived`` and ``device_status``: a bit flag, 0 passed, 1 failed by SMART itself, 2 failed
  Scrutiny's own thresholds. ``smart`` is absent for a device that has never reported.
- ``GET /api/device/<scrutiny_uuid>/details?duration_key=week`` -> ``{"success": true, "data": {"device":
  {...}, "smart_results": [newest first, ...]}, "metadata": {<attribute id>: {"display_name", ...}}}``. Each
  result has ``power_on_hours`` (what the summary shows) and ``attrs``: for ATA a map keyed by the attribute id
  as text (``"9"`` is power-on hours: ``raw_value``, ``value``, ``thresh``, ``status``), for NVMe keyed by name
  (``"power_on_hours"``). An attribute's ``status`` is a bit flag: 1 failed SMART, 2 **warning** by Scrutiny's
  thresholds, 4 failed Scrutiny's thresholds.
- The summary's ``power_on_hours`` comes from smartctl's own total, which is wrong on some disks (the fleet has
  one). The attribute is the source perch prefers: ``powerOnHours`` below.

Read-only (04 rule 4): only the two GETs above can be sent.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

import httpx2

from ..scrub import scrub

DEVICE_FAILED_SMART = 1
DEVICE_FAILED_SCRUTINY = 2
ATTR_FAILED_SMART, ATTR_WARNING, ATTR_FAILED_SCRUTINY = 1, 2, 4
POWER_ON_ATA = "9"
POWER_ON_NVME = "power_on_hours"


class ScrutinyError(RuntimeError):
    """Scrutiny can't be read; the message says what to check."""


@dataclass(frozen=True)
class Attribute:
    id: str
    name: str
    status: int


@dataclass(frozen=True)
class Disk:
    wwn: str
    uuid: str
    name: str  # sda
    host: str
    model: str
    protocol: str
    capacityBytes: int
    deviceStatus: int
    collectedAt: datetime | None
    tempC: int | None
    summaryHours: int | None  # what the summary says
    attributeHours: int | None  # SMART attribute 9 (NVMe: power_on_hours), when the details carry it
    warnings: tuple[Attribute, ...] = field(default_factory=tuple)
    failures: tuple[Attribute, ...] = field(default_factory=tuple)

    @property
    def powerOnHours(self) -> int | None:
        """The attribute wins over the summary when both exist (they disagree on some disks)."""
        return self.attributeHours if self.attributeHours is not None else self.summaryHours


def _reason(exc: Exception) -> str:
    if isinstance(exc, httpx2.TimeoutException):
        return "it timed out"
    if isinstance(exc, httpx2.ConnectError):
        return "connection refused or no route to it"
    return type(exc).__name__


def _unexpected(what: str) -> ScrutinyError:
    return ScrutinyError(f"Unexpected answer from Scrutiny: {what}.")


class ScrutinyClient:
    def __init__(
        self, url: str, *, transport: "httpx2.AsyncBaseTransport | None" = None, timeout: float = 10.0
    ) -> None:
        if not url:
            raise ValueError("disks needs PERCH_DISKS_URL")
        self._http = httpx2.AsyncClient(
            base_url=url.rstrip("/"),
            headers={"accept": "application/json"},
            timeout=httpx2.Timeout(timeout, connect=min(timeout, 5.0)),
            transport=transport,
            follow_redirects=False,
        )

    async def aclose(self) -> None:
        await self._http.aclose()

    async def _get(self, path: str, params: dict[str, str] | None = None) -> dict[str, Any]:
        try:
            response = await self._http.get(path, params=params)
        except httpx2.HTTPError as exc:
            raise ScrutinyError(
                f"can't see Scrutiny: {_reason(exc)}. Check PERCH_DISKS_URL and that Scrutiny is running."
            ) from None
        if response.status_code >= 300:
            raise ScrutinyError(scrub(f"can't see Scrutiny: {path} answered HTTP {response.status_code}", limit=200))
        try:
            answer = response.json()
        except ValueError:
            raise ScrutinyError("can't see Scrutiny: the answer was not JSON. Check PERCH_DISKS_URL.") from None
        if not isinstance(answer, dict) or answer.get("success") is not True:
            raise _unexpected(f"{path} did not say success")
        return answer

    async def disks(self) -> list[Disk]:
        """Every device in the summary; one details request each for the SMART attributes. A device whose
        details can't be read keeps what the summary says (no attribute, no warnings)."""
        summary = (await self._get("/api/summary")).get("data", {}).get("summary")
        if not isinstance(summary, dict):
            raise _unexpected("the summary has no devices map")
        found: list[Disk] = []
        for key, item in summary.items():
            device = (item or {}).get("device") if isinstance(item, dict) else None
            if not isinstance(device, dict) or device.get("archived"):
                continue
            details = None
            if device.get("scrutiny_uuid"):
                try:
                    details = await self._get(
                        f"/api/device/{device['scrutiny_uuid']}/details", {"duration_key": "week"}
                    )
                except ScrutinyError:
                    details = None
            found.append(_disk(str(key), item, details))
        return found


def _int(value: Any) -> int | None:
    return value if isinstance(value, int) and not isinstance(value, bool) else None


def _when(text: Any) -> datetime | None:
    try:
        moment = datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    except ValueError:
        return None
    return moment if moment.tzinfo else moment.replace(tzinfo=UTC)


def _disk(key: str, item: dict[str, Any], details: dict[str, Any] | None) -> Disk:
    device = item["device"]
    smart = item.get("smart") or {}
    attrs: dict[str, Any] = {}
    names: dict[str, Any] = {}
    if details:
        results = (details.get("data") or {}).get("smart_results") or []
        if results and isinstance(results[0], dict):
            attrs = results[0].get("attrs") or {}
        names = details.get("metadata") or {}
    protocol = str(device.get("device_protocol") or "")
    hoursKey = POWER_ON_NVME if protocol.lower() == "nvme" else POWER_ON_ATA
    hoursAttr = attrs.get(hoursKey) if isinstance(attrs, dict) else None
    attributeHours = None
    if isinstance(hoursAttr, dict):
        # ATA keeps the figure in raw_value; NVMe's power_on_hours has it in value
        attributeHours = _int(hoursAttr.get("raw_value" if hoursKey == POWER_ON_ATA else "value"))
    warnings, failures = [], []
    for attrId, attr in attrs.items() if isinstance(attrs, dict) else []:
        status = _int(attr.get("status")) if isinstance(attr, dict) else None
        if not status:
            continue
        meta = names.get(attrId) if isinstance(names, dict) else None
        name = str((meta or {}).get("display_name") or attr.get("attribute_id") or attrId)
        found = Attribute(str(attrId), name, status)
        if status & (ATTR_FAILED_SMART | ATTR_FAILED_SCRUTINY):
            failures.append(found)
        elif status & ATTR_WARNING:
            warnings.append(found)
    return Disk(
        wwn=str(device.get("wwn") or key),
        uuid=str(device.get("scrutiny_uuid") or ""),
        name=str(device.get("device_name") or key),
        host=str(device.get("host_id") or ""),
        model=str(device.get("model_name") or ""),
        protocol=protocol,
        capacityBytes=_int(device.get("capacity")) or 0,
        deviceStatus=_int(device.get("device_status")) or 0,
        collectedAt=_when(smart.get("collector_date")) if smart.get("collector_date") else None,
        tempC=_int(smart.get("temp")),
        summaryHours=_int(smart.get("power_on_hours")),
        attributeHours=attributeHours,
        warnings=tuple(warnings),
        failures=tuple(failures),
    )
