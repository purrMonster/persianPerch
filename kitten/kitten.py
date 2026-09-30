"""kitten: the small agent on each node (sieve, percolator, cellar, mochaPot, grinder,
roastery). Ships groom records and pounce events to perch, with a heartbeat.

Standard library only, so it runs as a zipapp on the nodes' own Python 3.13
(Debian 13) and on roastery's Python 3.14 without installing anything (05 plan C11,
A5; ADR 0001). Test S8 runs its tests on both versions.

M0 holds only its settings; the agent loop arrives in M2 (groom) and M5 (pounce).
"""

from __future__ import annotations

import os
import platform
from dataclasses import dataclass, field

VERSION = "0.0.1"

# Several pounce paths in one setting are separated by ';' on every OS: Windows
# paths contain ':' (C:\...), so os.pathsep-style ':' can't be the separator there.
PATH_SEPARATOR = ";"


@dataclass(frozen=True)
class KittenConfig:
    perchUrl: str = ""
    token: str = field(default="", repr=False)
    pouncePaths: tuple[str, ...] = ()
    groomDir: str = "/var/lib/purrbrews/groom"
    node: str = ""

    def __repr__(self) -> str:  # never print the token
        token = "<set>" if self.token else "''"
        return (
            f"KittenConfig(perchUrl={self.perchUrl!r}, token={token}, pouncePaths={self.pouncePaths!r}, "
            f"groomDir={self.groomDir!r}, node={self.node!r})"
        )

    @classmethod
    def fromEnv(cls, env: "dict[str, str] | None" = None) -> "KittenConfig":
        env = dict(os.environ if env is None else env)
        paths = tuple(p.strip() for p in env.get("KITTEN_POUNCE_PATHS", "").split(PATH_SEPARATOR) if p.strip())
        return cls(
            perchUrl=env.get("KITTEN_PERCH_URL", "").strip(),
            token=env.get("KITTEN_TOKEN", "").strip(),
            pouncePaths=paths,
            groomDir=env.get("KITTEN_GROOM_DIR", "").strip() or "/var/lib/purrbrews/groom",
            node=env.get("KITTEN_NODE", "").strip() or platform.node().split(".")[0],
        )

    def problems(self) -> list[str]:
        """What's missing before kitten can push; empty when it's ready."""
        found = []
        if not self.perchUrl.startswith("https://"):
            found.append("KITTEN_PERCH_URL must be an https:// URL")
        if not self.token:
            found.append("KITTEN_TOKEN is not set")
        return found
