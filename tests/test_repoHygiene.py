"""Repository rules that must always hold: S5 (secrets.env has no values), S6 (no
hostname outside an allow-list), S8 (PowerShell files are ASCII-only)."""

import re
from pathlib import Path

import pytest
from conftest import ROOT, git

# S6: hosts that may appear in tracked files. Everything else is a stop: the real
# domain or a private hostname must never be committed (AGENTS.md 2.3).
ALLOWED_HOSTS = {
    "example.home.arpa",  # fixtures and docs
    "github.com",  # the two public repos
    "hc-ping.com",  # healthchecks.io ping host
    "healthchecks.io",
    "ntfy.sh",  # public ntfy, hiss copy (05 plan A7)
    "anthropic.com",  # commit attribution address in AGENTS.md
    "docs.python.org",
    "fastapi.tiangolo.com",
    "playwright.dev",
    "komo.do",
    "gatus.io",
    "home-assistant.io",
    "developers.home-assistant.io",
    "mcr.microsoft.com",  # the Playwright test image
    "docker.io",
    "pypi.org",
    "htmx.org",
    "w3.org",  # SVG namespace
    "ghcr.io",  # binocs: GitHub's container registry, read anonymously for newer releases of pinned images (M4)
    "lscr.io",  # LinuxServer's name for images that live on ghcr.io (the fleet pins speedtest-tracker by it)
}
# Exact strings allowed even though they contain a host: the git identity AGENTS.md
# requires for every commit (public in every commit already; runbook 2026-09-30, M0).
ALLOWED_STRINGS = {"jyotirmoy.github@jyotirmoy.cc"}

# Bare names are matched only on TLDs that don't collide with code (``node.app``,
# ``backup.sh``); anything written as a URL is checked whatever its TLD.
TLDS = "com|net|org|io|cc|dev|xyz|cloud|arpa|lan|internal|ts\\.net"
URL_HOST = re.compile(r"\b[a-z][a-z0-9+.-]*://([^/\s:\"'<>)\]`|]+)", re.I)
BARE_HOST = re.compile(rf"(?<![\w.-])((?:[a-z0-9-]+\.)+(?:{TLDS}))(?![\w-])", re.I)
IP = re.compile(r"^\d+\.\d+\.\d+\.\d+$")


def trackedFiles() -> list[Path]:
    if not (ROOT / ".git").exists():
        pytest.fail("S5/S6/S8 need the project's git checkout (tracked files)")
    return [ROOT / p for p in git(ROOT, "ls-files", "-z").split("\0") if p]


def allowedHost(host: str) -> bool:
    host = host.lower().rstrip(".")
    if "${" in host or "$" in host or "{{" in host or "." not in host or IP.match(host):
        return True  # a template, a container name, or a LAN address
    return any(host == a or host.endswith("." + a) for a in ALLOWED_HOSTS)


def hostsIn(text: str) -> set[str]:
    for allowed in ALLOWED_STRINGS:
        text = text.replace(allowed, "")
    found = {m.group(1) for m in URL_HOST.finditer(text)}
    found |= {m.group(1) for m in BARE_HOST.finditer(text)}
    return {h for h in found if not allowedHost(h)}


def test_S5_secrets_env_holds_no_values():
    lines = (ROOT / "secrets.env").read_text(encoding="ascii").splitlines()
    keys = [line for line in lines if re.match(r"^[A-Z0-9_]+=", line)]
    assert len(keys) >= 30
    filled = [line.split("=", 1)[0] for line in keys if line.split("=", 1)[1].strip()]
    assert filled == [], f"secrets.env must stay empty; values found for {filled}"


def test_S6_no_unlisted_hostnames_in_tracked_files():
    offenders = {}
    for path in trackedFiles():
        if not path.is_file() or path.suffix in {".png", ".ico", ".db"}:
            continue
        try:
            text = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        hosts = hostsIn(text)
        if hosts:
            offenders[str(path.relative_to(ROOT))] = sorted(hosts)
    assert offenders == {}


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        ("see https://perch.${DOMAIN}/tree", set()),
        ("ping https://hc-ping.com/uuid and ntfy.sh/topic", set()),
        ("http://komodo-core:9120 and 192.168.0.12", set()),
        ("run backup.sh and check-freshness.sh", set()),
        # split with "+" so this file doesn't trip its own scan
        ("open https:/" + "/perch.purrbrews-real" + ".net", {"perch.purrbrews-real" + ".net"}),
        ("mail barista@some-house" + ".dev now", {"some-house" + ".dev"}),
        ("node sieve.tail1234.ts" + ".net", {"sieve.tail1234.ts" + ".net"}),
    ],
)
def test_S6_detector(text, bad):
    assert hostsIn(text) == bad


def test_S8_powershell_is_ascii_only():
    for path in trackedFiles():
        if path.suffix.lower() in {".ps1", ".psm1", ".psd1"}:
            data = path.read_bytes()
            assert all(b < 128 for b in data), f"{path.name} has non-ASCII bytes"
            assert not data.startswith(b"\xef\xbb\xbf"), f"{path.name} has a BOM"
