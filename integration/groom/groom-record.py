#!/usr/bin/env python3
"""groom-record: write one record when a backup job's unit stops (persianPerch, M2).

Prepared in persianPerch's integration/groom/ and applied by the owner: it lands in the fleet repo
as stacks/_lib/groom-record.py and runs from each backup unit's ``ExecStopPost=`` (see the drop-ins
in units/). backup.sh and cellar's scripts stay untouched (05 plan A8, Q13 = A).

    groom-record.py <job> <node> <unit>

    job   nightly | wake | store | drive | check | prune | verify
    node  the node's folder in stacks/ (sieve, percolator, cellar, mochaPot, grinder)
    unit  the unit's name, systemd's %n

systemd sets $SERVICE_RESULT, $EXIT_CODE and $EXIT_STATUS for ExecStopPost=. The record is
``/var/lib/purrbrews/groom/<job>/<start>.json``: schema 1 (perch/senses/groom.py parseRecord is
its definition), written 0644 in a 0755 directory so kitten, an unprivileged user, can read it
(05 plan A10). Standard library only. It never fails the job: any problem is printed to stderr
and the exit code is 0, and the drop-ins run it with the ``-`` prefix besides.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

SCHEMA = 1
JOBS = ("nightly", "wake", "store", "drive", "check", "prune", "verify")
LOG_LINES = 40
LOG_LIMIT = 16 * 1024


def utc(moment: datetime) -> str:
    return moment.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def startedAt(unit: str, now: datetime) -> datetime:
    """When the unit's main process started, from systemd; ``$GROOM_START`` (epoch seconds) overrides it.
    Falls back to now: a record with the wrong start is better than no record."""
    override = os.environ.get("GROOM_START")
    if override:
        return datetime.fromtimestamp(int(override), UTC)
    try:
        out = subprocess.run(
            ["systemctl", "show", unit, "-p", "ExecMainStartTimestamp", "--value", "--timestamp=unix"],
            capture_output=True,
            text=True,
            timeout=15,
            check=True,
        ).stdout.strip()
        return datetime.fromtimestamp(int(out.lstrip("@")), UTC)
    except (OSError, subprocess.SubprocessError, ValueError):
        return now


def logTail(unit: str, start: datetime) -> str:
    """The last lines the unit logged since it started. The scrubbing of secrets is perch's job."""
    try:
        out = subprocess.run(
            [
                "journalctl",
                "-u",
                unit,
                "--since",
                f"@{int(start.timestamp())}",
                "-n",
                str(LOG_LINES),
                "-o",
                "cat",
                "--no-pager",
            ],
            capture_output=True,
            timeout=30,
            check=True,
        ).stdout
    except (OSError, subprocess.SubprocessError):
        return ""
    return out.decode("utf-8", errors="replace")[-LOG_LIMIT:]


def write(root: Path, job: str, start: datetime, record: dict) -> Path:
    """Atomically, with the modes kitten needs: a 0755 directory and a 0644 file."""
    folder = root / job
    for directory in (root, folder):
        directory.mkdir(mode=0o755, exist_ok=True)
        directory.chmod(0o755)
    target = folder / f"{start.strftime('%Y%m%dT%H%M%SZ')}.json"
    temporary = folder / f".{target.name}.tmp"  # kitten reads *.json only, so it never sees this
    temporary.write_text(json.dumps(record, indent=2) + "\n", encoding="utf-8")
    temporary.chmod(0o644)
    os.replace(temporary, target)
    return target


def main(argv: list[str]) -> int:
    if len(argv) != 3 or argv[0] not in JOBS:
        print(f"usage: groom-record.py <{'|'.join(JOBS)}> <node> <unit>", file=sys.stderr)
        return 0
    job, node, unit = argv
    now = datetime.now(UTC)
    start = startedAt(unit, now)
    record = {
        "schema": SCHEMA,
        "job": job,
        "node": node,
        "unit": unit,
        "start": utc(start),
        "end": utc(now),
        "result": os.environ.get("SERVICE_RESULT", "") or "unknown",
        "exitStatus": os.environ.get("EXIT_STATUS", ""),
        "logTail": logTail(unit, start),
    }
    root = Path(os.environ.get("GROOM_DIR", "/var/lib/purrbrews/groom"))
    try:
        path = write(root, job, start, record)
    except OSError as exc:
        print(f"groom-record: could not write the record for {unit}: {exc}", file=sys.stderr)
        return 0
    print(f"groom-record: {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
