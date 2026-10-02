"""The container-safety rule (AGENTS.md 2.8, owner's decision after M3's incident): roastery runs
fleet services next to the build, so no tracked script may select all or unnamed containers,
images, volumes or networks to stop, kill, remove or prune them."""

import re
from pathlib import Path

import pytest
from conftest import ROOT, git

LABEL = "com.purrbrews.project=persianperch"
SCRIPT_SUFFIXES = {".ps1", ".sh", ".bash", ".yml", ".yaml", ".py", ".bat", ".cmd", ".service"}
THIS_FILE = Path(__file__).resolve()

ACT = r"docker\s+(?:container\s+)?(?:kill|rm|stop|restart|pause)\b"
FORBIDDEN = {
    "an action on a command-substitution list (docker kill $(docker ps -q))": re.compile(
        ACT + r".*(?:\$\(|`|\(\s*docker\s)"
    ),
    "docker's list piped into xargs": re.compile(
        r"docker\s+(?:ps|container\s+ls|images?|volume\s+ls|network\s+ls)\b.*\|\s*xargs"
    ),
    "xargs feeding docker an action": re.compile(
        r"xargs\b.*\bdocker\s+(?:container\s+)?(?:kill|rm|stop|restart|pause|rmi)\b"
    ),
    "docker's list piped into a PowerShell loop": re.compile(
        r"docker\s+(?:ps|container\s+ls)\b.*\|\s*(?:ForEach-Object|foreach|%)"
    ),
    "docker rmi/rm of an unnamed list": re.compile(
        r"docker\s+(?:rmi|image\s+rm|volume\s+rm|network\s+rm)\b.*(?:\$\(|`|\(\s*docker\s)"
    ),
}
PRUNE = re.compile(r"docker\s+(?:system|container|image|volume|network|builder)\s+prune\b")


def logicalLines(text: str) -> list[str]:
    """Join backslash and backtick continuations so a flag on the next line still counts."""
    out, buf = [], ""
    for raw in text.splitlines():
        line = raw.rstrip()
        if line.endswith(("\\", "`")):
            buf += line[:-1] + " "
            continue
        out.append(buf + line)
        buf = ""
    if buf:
        out.append(buf)
    return out


def violations(text: str) -> list[str]:
    found = []
    for line in logicalLines(text):
        if line.lstrip().startswith("#"):
            continue
        for why, rx in FORBIDDEN.items():
            if rx.search(line):
                found.append(f"{why}: {line.strip()}")
        if PRUNE.search(line) and LABEL not in line.replace('"', "").replace("'", ""):
            found.append(f"prune without the project label: {line.strip()}")
    return found


def trackedScripts() -> list[Path]:
    if not (ROOT / ".git").exists():
        pytest.fail("the container-safety test needs the project's git checkout (tracked files)")
    files = [ROOT / p for p in git(ROOT, "ls-files", "-z").split("\0") if p]
    return [
        f
        for f in files
        if (f.suffix in SCRIPT_SUFFIXES or f.name.startswith("Dockerfile")) and f.resolve() != THIS_FILE
    ]


@pytest.mark.parametrize(
    "line",
    [
        "docker ps -q | xargs docker kill",
        "docker kill $(docker ps -q)",
        "docker rm -f $(docker ps -aq)",
        "docker stop $(docker ps -q)",
        "docker ps -aq | xargs -r docker rm -f",
        "docker container ls -q | xargs docker stop",
        "docker ps -q | ForEach-Object { docker kill $_ }",
        "docker kill (docker ps -q)",
        "docker system prune -af",
        "docker volume prune -f",
        "docker image prune --all",
        "docker container prune --force",
        "docker rmi $(docker images -q)",
        "docker ps -q |\\\n  xargs docker kill",
    ],
)
def test_the_forbidden_patterns_are_caught(line):
    assert violations(line), line


@pytest.mark.parametrize(
    "line",
    [
        "docker compose -f tests/ui/compose.yml down --volumes --remove-orphans",
        "docker compose -p persian-perch-ui down",
        f"docker container prune --force --filter label={LABEL}",
        f'docker system prune -f --filter "label={LABEL}"',
        "docker run --rm -v x:/src python:3.12-slim sh -c 'pytest'",
        "docker stop persian-perch-ui-perch-1",
        "# docker kill $(docker ps -q) is forbidden",
    ],
)
def test_the_safe_forms_are_not_flagged(line):
    assert violations(line) == []


def test_no_tracked_script_selects_all_or_unnamed_containers():
    bad = {}
    for f in trackedScripts():
        found = violations(f.read_text(encoding="utf-8", errors="replace"))
        if found:
            bad[str(f.relative_to(ROOT))] = found
    assert not bad, bad


def test_every_container_the_test_script_starts_carries_the_project_label():
    text = (ROOT / "scripts" / "test.ps1").read_text(encoding="ascii")
    assert f"$label = '{LABEL}'" in text
    for line in logicalLines(text):
        if re.search(r"\bdocker\s+(run|build)\b", line) and not line.lstrip().startswith("#"):
            assert "--label $label" in line, line
    compose = (ROOT / "tests" / "ui" / "compose.yml").read_text(encoding="utf-8")
    assert compose.count("com.purrbrews.project: persianperch") == compose.count("    image: ")
