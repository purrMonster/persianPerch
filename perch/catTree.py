"""catTree: the fleet, in the shape of the purrbrews-containers repo.

fleet -> node -> app, plus the docs, built from the repo checkout (design plan 3.1).

Security (design plan 7, test S1):
- the file list comes only from ``git ls-files``: untracked files (every
  ``secrets.env.local`` on a node) are invisible by construction;
- a deny-list is enforced on top, so a secret file is never listed or read even if
  one were ever tracked by mistake;
- a file is read only if it is tracked, not denied, not a symlink and inside the
  checkout.
"""

from __future__ import annotations

import fnmatch
import re
import subprocess
import threading
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath

DENY_PATTERNS: tuple[str, ...] = ("*.env.local", "secrets.env.local", "*.key", "authorized_keys")
READ_LIMIT = 256 * 1024

_APPS = re.compile(r"^\s*APPS=\((?P<apps>[^)]*)\)", re.MULTILINE)
_IMAGE = re.compile(r"^\s*image:\s*[\"']?(?P<image>[^\s\"'#]+)", re.MULTILINE)
_LAN_IP = re.compile(r"^(?P<node>[A-Z0-9_]+)_LAN_IP=(?P<ip>[0-9.]+)\s*$", re.MULTILINE)


def isDenied(path: str) -> bool:
    """True for any path whose file name matches the deny-list (case-insensitive)."""
    name = PurePosixPath(path).name.lower()
    return any(fnmatch.fnmatchcase(name, pattern) for pattern in DENY_PATTERNS)


class CatTreeError(RuntimeError):
    pass


def _git(repoDir: Path, *args: str) -> str:
    # safe.directory: the checkout is mounted read-only and owned by another user.
    cmd = ["git", "-c", "safe.directory=*", "-C", str(repoDir), *args]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=30, check=True)
    except FileNotFoundError as exc:
        raise CatTreeError("git is not installed") from exc
    except subprocess.CalledProcessError as exc:
        raise CatTreeError(f"git {' '.join(args)} failed: {exc.stderr.strip()[:200]}") from exc
    return result.stdout


def trackedFiles(repoDir: Path) -> list[str]:
    """Git-tracked files, deny-list applied, POSIX paths relative to the repo."""
    out = _git(repoDir, "ls-files", "-z")
    return sorted(p for p in out.split("\0") if p and not isDenied(p))


@dataclass
class App:
    node: str
    name: str
    inApps: bool
    files: list[str] = field(default_factory=list)
    summary: str = ""
    images: list[str] = field(default_factory=list)
    backup: list[str] = field(default_factory=list)
    hasSecretsConf: bool = False

    @property
    def id(self) -> str:
        return f"app:{self.node}/{self.name}"

    @property
    def path(self) -> str:
        return f"stacks/{self.node}/{self.name}"


@dataclass
class Node:
    name: str
    role: str = ""
    ip: str = ""
    apps: list[App] = field(default_factory=list)
    extras: list[App] = field(default_factory=list)
    files: list[str] = field(default_factory=list)

    @property
    def id(self) -> str:
        return f"node:{self.name}"

    @property
    def path(self) -> str:
        return f"stacks/{self.name}"

    def app(self, name: str) -> "App | None":
        for app in self.apps + self.extras:
            if app.name == name:
                return app
        return None


@dataclass
class Fleet:
    nodes: list[Node]
    docs: list[str]
    commit: str
    subject: str
    files: frozenset[str]

    def node(self, name: str) -> "Node | None":
        for node in self.nodes:
            if node.name == name:
                return node
        return None

    @property
    def appCount(self) -> int:
        return sum(len(n.apps) for n in self.nodes)


class CatTree:
    """Builds the Fleet from a checkout and rebuilds it when HEAD moves."""

    def __init__(self, repoDir: "str | Path") -> None:
        self.repoDir = Path(repoDir)
        self._lock = threading.Lock()
        self._fleet: Fleet | None = None
        self._head: str | None = None

    def fleet(self) -> Fleet:
        head = _git(self.repoDir, "rev-parse", "HEAD").strip()
        with self._lock:
            if self._fleet is None or head != self._head:
                self._fleet = self._build(head)
                self._head = head
            return self._fleet

    def read(self, path: str, fleet: "Fleet | None" = None) -> str:
        """Text of one tracked, non-denied file, or CatTreeError."""
        fleet = fleet or self.fleet()
        if isDenied(path) or path not in fleet.files:
            raise CatTreeError(f"not readable: {path}")
        root = self.repoDir.resolve()
        full = self.repoDir / path
        if full.is_symlink():
            raise CatTreeError(f"symlink, not read: {path}")
        resolved = full.resolve()
        if root not in resolved.parents or not resolved.is_file():
            raise CatTreeError(f"outside the checkout: {path}")
        with open(resolved, "rb") as handle:
            data = handle.read(READ_LIMIT)
        return data.decode("utf-8", errors="replace")

    # -- building -------------------------------------------------------------

    def _build(self, head: str) -> Fleet:
        files = trackedFiles(self.repoDir)
        fileSet = frozenset(files)
        subject = _git(self.repoDir, "log", "-1", "--format=%s").strip()
        probe = Fleet([], [], head, subject, fileSet)

        def text(path: str) -> str:
            try:
                return self.read(path, probe) if path in fileSet else ""
            except CatTreeError:
                return ""

        ips: dict[str, str] = {}
        order: list[str] = []
        for match in _LAN_IP.finditer(text("stacks/fleet.env")):
            ips[match["node"]] = match["ip"]
            order.append(match["node"])

        byNode: dict[str, list[str]] = {}
        for path in files:
            parts = path.split("/")
            if len(parts) >= 3 and parts[0] == "stacks":
                byNode.setdefault(parts[1], []).append("/".join(parts[2:]))

        nodes: list[Node] = []
        for name, nodeFiles in byNode.items():
            if "node.conf" not in nodeFiles:
                continue
            conf = text(f"stacks/{name}/node.conf")
            node = Node(name=name, role=_role(conf, name), ip=ips.get(name.upper(), ""))
            node.files = sorted(f for f in nodeFiles if "/" not in f)
            appsLine = _APPS.search(conf)
            listed = appsLine["apps"].split() if appsLine else []
            dirs: dict[str, list[str]] = {}
            for f in nodeFiles:
                if "/" in f:
                    top, rest = f.split("/", 1)
                    dirs.setdefault(top, []).append(rest)
            for appName in listed:
                node.apps.append(self._app(name, appName, True, dirs.get(appName, []), text))
            for appName in sorted(set(dirs) - set(listed), key=str.lower):
                node.extras.append(self._app(name, appName, False, dirs[appName], text))
            nodes.append(node)

        rank = {n: i for i, n in enumerate(order)}
        nodes.sort(key=lambda n: (rank.get(n.name.upper(), len(rank)), n.name.lower()))

        docs = [
            p
            for p in files
            if p.lower().endswith(".md") and ("/" not in p or p.startswith("docs/") or p == "stacks/README.md")
        ]
        return Fleet(nodes=nodes, docs=docs, commit=head, subject=subject, files=fileSet)

    @staticmethod
    def _app(node: str, name: str, inApps: bool, files: list[str], text) -> App:
        base = f"stacks/{node}/{name}"
        app = App(node=node, name=name, inApps=inApps, files=sorted(files))
        app.summary = _summary(text(f"{base}/README.md"))
        app.images = _IMAGE.findall(text(f"{base}/docker-compose.yml"))
        app.backup = [
            line.strip()
            for line in text(f"{base}/backup").splitlines()
            if line.strip() and not line.lstrip().startswith("#")
        ]
        app.hasSecretsConf = "secrets.conf" in files
        return app


def _role(conf: str, name: str) -> str:
    """The node's role from node.conf's first comment: '# cellar: backups, ...'."""
    lines = []
    for line in conf.splitlines():
        if not line.startswith("#"):
            break
        lines.append(line.lstrip("#").strip())
    first = " ".join(lines).split(". ")[0].strip()
    prefix = f"{name}:"
    if first.lower().startswith(prefix.lower()):
        first = first[len(prefix) :].strip()
    return first.rstrip(".")


def _summary(readme: str) -> str:
    """The first prose paragraph of a README (no headings, tables, quotes or code)."""
    paragraph: list[str] = []
    inCode = False
    for raw in readme.splitlines():
        line = raw.strip()
        if line.startswith("```"):
            inCode = not inCode
            continue
        if inCode:
            continue
        if not line:
            if paragraph:
                break
            continue
        if line.startswith(("#", "|", ">", "<", "-", "*", "![")) and not paragraph:
            continue
        paragraph.append(line)
    text = " ".join(paragraph)
    text = re.sub(r"\[([^\]]+)\]\([^)]+\)", r"\1", text)
    text = text.replace("**", "").replace("`", "")
    return text[:400]
