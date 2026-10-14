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


# -- S10: no credential shape in any tracked file (public repo review, 2026-10-14) --------------------------------
# The shapes gitleaks and perch's own scrub know, applied to every tracked file. A fixture that needs a fake value
# in one of these shapes is listed with the exact fake, so a real one next to it still fails.
CREDENTIAL_SHAPES = {
    "private key": re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    "GitHub token": re.compile(r"\b(?:ghp|gho|ghu|ghs|ghr)_[A-Za-z0-9]{36}\b|\bgithub_pat_[A-Za-z0-9_]{60,}\b"),
    "ntfy token": re.compile(r"\btk_[a-z0-9]{29}\b"),
    "JWT": re.compile(r"\beyJ[A-Za-z0-9_-]{10,}\.eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),
    "Google OAuth token": re.compile(r"\bya29\.[A-Za-z0-9_-]{20,}"),
    "healthchecks.io ping URL": re.compile(r"hc-ping\.com/[0-9a-f]{8}-[0-9a-f]{4}-"),
    "ntfy.sh topic": re.compile(r"ntfy\.sh/(?!publish\b|topic\b|<)[A-Za-z0-9_-]{6,}"),
    "Tailscale auth key": re.compile(r"\btskey-[a-z]+-[A-Za-z0-9]{10,}"),
    "Cloudflare tunnel token": re.compile(r"\beyJhIjoi[A-Za-z0-9+/=]{40,}"),
}
FAKE_CREDENTIALS = {
    # whiskers' fake Home Assistant token: header {"alg":"HS256"}, payload {"iss":"fake-ha-not-real"}
    "eyJhbGciOiJIUzI1NiJ9.eyJpc3MiOiJmYWtlLWhhLW5vdC1yZWFsIn0.fake-signature-not-real-0123456789abcdef",
}


def credentialsIn(text: str) -> list[tuple[str, str]]:
    for fake in FAKE_CREDENTIALS:
        text = text.replace(fake, "")
    return [
        (name, m.group(0)[:24])
        for name, rx in CREDENTIAL_SHAPES.items()
        for m in rx.finditer(text)
        if "fake" not in m.group(0).lower()  # the scrub tests' fakes say so in the value itself
    ]


def test_S10_no_credential_shape_in_tracked_files():
    found = {}
    for path in trackedFiles():
        try:
            text = path.read_text(encoding="utf-8")
        except (UnicodeDecodeError, IsADirectoryError, FileNotFoundError):
            continue
        hits = credentialsIn(text)
        if hits:
            found[str(path.relative_to(ROOT))] = hits
    assert found == {}, found


@pytest.mark.parametrize(
    ("text", "bad"),
    [
        # assembled at run time, so this file never holds the shapes it tests for
        ("token: tk" + "_abcdefghijklmnopqrstuvwxyz123", True),
        ("PERCH_NINELIVES_URL=https://hc-ping" + ".com/1a2b3c4d-1111-2222-3333-444455556666", True),
        ("-----BEGIN OPENSSH PRIVATE" + " KEY-----", True),
        ("curl -d hi https://ntfy" + ".sh/purrbrews-critical-x7", True),
        ("token ya29" + ".a0AfakeFAKEfakeFAKEfake123", False),  # says it is fake
        ("https://ntfy.sh/<that topic>", False),
        ("PERCH_NINELIVES_URL=https://hc-ping.com/<uuid>", False),
        ("TOKEN = tk_ + 29 characters", False),
    ],
)
def test_S10_detector(text, bad):
    assert bool(credentialsIn(text)) is bad
