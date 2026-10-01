"""Shared fixtures. The pinned fleet repo lives in .cache/purrbrews-containers (05 plan 3)."""

from __future__ import annotations

import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
FLEET_COMMIT = "f94efdfb1995d7217ec2be33e45b33720a0a0b3b"


def git(repo: Path, *args: str) -> str:
    cmd = ["git", "-c", "safe.directory=*"]
    projectGitDir = os.environ.get("PERCH_TEST_GIT_DIR")
    if projectGitDir and Path(repo).resolve() == ROOT:
        # Only this project's own repo: scripts/test.ps1 sets it when the checkout is a git
        # worktree, whose .git file points at a host path the container can't see. Every
        # other repo (the fleet clone, the tests' temporary ones) is found the normal way.
        cmd += ["--git-dir", projectGitDir, "--work-tree", str(ROOT)]
    return subprocess.run([*cmd, "-C", str(repo), *args], check=True, capture_output=True, text=True).stdout


@pytest.fixture(scope="session")
def fleetRepo() -> Path:
    """The pinned clone of purrbrews-containers (never modified by tests)."""
    repo = Path(os.environ.get("PERCH_TEST_FLEET_REPO", ROOT / ".cache" / "purrbrews-containers"))
    if not (repo / ".git").exists():
        pytest.fail(
            f"pinned fleet repo missing at {repo}; clone it (05 plan 3): "
            f"git clone https://github.com/purrMonster/purrbrews-containers {repo} && "
            f"git -C {repo} checkout {FLEET_COMMIT}"
        )
    head = git(repo, "rev-parse", "HEAD").strip()
    assert head == FLEET_COMMIT, f"fleet repo at {head}, tests pin {FLEET_COMMIT}"
    return repo


class FakeClock:
    def __init__(self, start: datetime) -> None:
        self.now = start

    def __call__(self) -> datetime:
        return self.now

    def advance(self, **delta) -> None:
        from datetime import timedelta

        self.now += timedelta(**delta)


@pytest.fixture
def clock() -> FakeClock:
    return FakeClock(datetime(2026, 9, 29, 1, 30, tzinfo=UTC))


def makeRepo(root: Path, files: dict[str, str], symlinks: dict[str, str] | None = None) -> Path:
    """A small git repo with every given file tracked (force-added, even if ignored)."""
    root.mkdir(parents=True, exist_ok=True)
    git(root, "init", "-q", "-b", "main")
    for rel, text in files.items():
        path = root / rel
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
    for rel, target in (symlinks or {}).items():
        (root / rel).parent.mkdir(parents=True, exist_ok=True)
        os.symlink(target, root / rel)
    git(root, "add", "-f", "-A")
    git(root, "-c", "user.name=t", "-c", "user.email=t@example.home.arpa", "commit", "-q", "-m", "fixture")
    return root
