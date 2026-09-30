"""PERCH_* settings (dev plan 3, extended by 05 plan C10).

Every setting has a safe default so perch starts with nothing configured: senses
without a URL simply stay ``unknown``. Secrets are read from the environment only
and never logged or rendered (``Settings.__repr__`` hides them).
"""

from __future__ import annotations

import os
import re
from dataclasses import dataclass, field, fields
from pathlib import Path

_DURATION = re.compile(r"^\s*(\d+)\s*([smhd]?)\s*$")
_UNIT_SECONDS = {"": 1, "s": 1, "m": 60, "h": 3600, "d": 86400}

NODES = ("sieve", "percolator", "cellar", "mochaPot", "grinder", "roastery")


def parseDuration(value: str) -> int:
    """'30s' -> 30, '5m' -> 300, '7d' -> 604800, '45' -> 45."""
    match = _DURATION.match(value or "")
    if not match:
        raise ValueError(f"not a duration: {value!r} (use e.g. 30s, 5m, 7d)")
    return int(match.group(1)) * _UNIT_SECONDS[match.group(2)]


def _secret(default: str = "") -> str:
    return field(default=default, metadata={"secret": True})


@dataclass(frozen=True)
class Settings:
    repoDir: Path = Path("/opt/purrbrews")
    trailDb: Path = Path("/data/scentTrail.db")
    trailDays: int = 90
    rollupDays: int = 400
    tz: str = "Asia/Kolkata"

    purrUrl: str = ""
    purrKey: str = _secret()
    purrSecret: str = _secret()
    purrEvery: int = 30

    glareUrl: str = ""
    glareUser: str = ""
    glarePassword: str = _secret()

    disksUrl: str = ""

    whiskersUrl: str = ""
    whiskersToken: str = _secret()
    whiskersEntities: Path = Path("/config/whiskers.yml")

    binocsSpeedtestUrl: str = ""
    binocsSpeedtestToken: str = _secret()
    binocsReleasesEvery: int = 7 * 86400

    groomDir: Path = Path("/var/lib/purrbrews/groom")

    kittenTokens: dict[str, str] = field(default_factory=dict, metadata={"secret": True})

    meowNtfyUrl: str = ""
    meowNtfyToken: str = _secret()
    meowQuiet: str = "23:00-07:00"
    meowCriticalUrl: str = _secret()
    ackSecret: str = _secret()

    nineLivesUrl: str = _secret()

    def __repr__(self) -> str:  # never print a secret
        parts = []
        for f in fields(self):
            value = getattr(self, f.name)
            if f.metadata.get("secret") and value:
                value = "<set>"
            parts.append(f"{f.name}={value!r}")
        return "Settings(" + ", ".join(parts) + ")"

    @classmethod
    def fromEnv(cls, env: "dict[str, str] | None" = None) -> "Settings":
        env = dict(os.environ if env is None else env)

        def get(key: str, default: str = "") -> str:
            value = env.get(key, "")
            return value if value != "" else default

        tokens = {
            node: get(f"PERCH_KITTEN_TOKEN_{node.upper()}")
            for node in NODES
            if get(f"PERCH_KITTEN_TOKEN_{node.upper()}")
        }
        return cls(
            repoDir=Path(get("PERCH_REPO_DIR", "/opt/purrbrews")),
            trailDb=Path(get("PERCH_TRAIL_DB", "/data/scentTrail.db")),
            trailDays=int(get("PERCH_TRAIL_DAYS", "90")),
            rollupDays=int(get("PERCH_ROLLUP_DAYS", "400")),
            tz=get("PERCH_TZ", get("TZ", "Asia/Kolkata")),
            purrUrl=get("PERCH_PURR_URL"),
            purrKey=get("PERCH_PURR_KEY"),
            purrSecret=get("PERCH_PURR_SECRET"),
            purrEvery=parseDuration(get("PERCH_PURR_EVERY", "30s")),
            glareUrl=get("PERCH_GLARE_URL"),
            glareUser=get("PERCH_GLARE_USER"),
            glarePassword=get("PERCH_GLARE_PASSWORD"),
            disksUrl=get("PERCH_DISKS_URL"),
            whiskersUrl=get("PERCH_WHISKERS_URL"),
            whiskersToken=get("PERCH_WHISKERS_TOKEN"),
            whiskersEntities=Path(get("PERCH_WHISKERS_ENTITIES", "/config/whiskers.yml")),
            binocsSpeedtestUrl=get("PERCH_BINOCS_SPEEDTEST_URL"),
            binocsSpeedtestToken=get("PERCH_BINOCS_SPEEDTEST_TOKEN"),
            binocsReleasesEvery=parseDuration(get("PERCH_BINOCS_RELEASES_EVERY", "7d")),
            groomDir=Path(get("PERCH_GROOM_DIR", "/var/lib/purrbrews/groom")),
            kittenTokens=tokens,
            meowNtfyUrl=get("PERCH_MEOW_NTFY_URL"),
            meowNtfyToken=get("PERCH_MEOW_NTFY_TOKEN"),
            meowQuiet=get("PERCH_MEOW_QUIET", "23:00-07:00"),
            meowCriticalUrl=get("PERCH_MEOW_CRITICAL_URL"),
            ackSecret=get("PERCH_ACK_SECRET"),
            nineLivesUrl=get("PERCH_NINELIVES_URL"),
        )

    def secretValues(self) -> list[str]:
        """Every secret value that is set; the scrubber removes these from log tails."""
        values: list[str] = []
        for f in fields(self):
            if not f.metadata.get("secret"):
                continue
            value = getattr(self, f.name)
            if isinstance(value, dict):
                values.extend(v for v in value.values() if v)
            elif value:
                values.append(value)
        return values
