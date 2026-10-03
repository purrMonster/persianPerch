"""scrub: remove secrets from log tails before they reach scentTrail (design plan 7).

Three layers, applied in order:

1. exact values perch knows are secret (its own settings, fixture secrets in tests);
2. the value of any ``NAME=value`` / ``NAME: value`` whose name ends in
   PASSWORD, TOKEN, SECRET or KEY (case-insensitive);
3. anything shaped like a credential: ``Bearer <x>``, ``Authorization: <x>``,
   ntfy tokens (``tk_...``), ``user:password@`` in URLs, an acknowledge link or token (M3), a
   healthchecks.io ping URL and a JWT (a Home Assistant long-lived access token is one, M5).

The result is capped at 16 KB (the newest lines are kept).
"""

from __future__ import annotations

import re
from collections.abc import Iterable

MASK = "••••"  # ••••
LOG_TAIL_LIMIT = 16 * 1024

_NAMED = re.compile(
    r"(?P<name>\b[A-Za-z0-9_.-]*(?:PASSWORD|PASSWD|TOKEN|SECRET|KEY)[A-Za-z0-9_]*)"
    r"(?P<sep>\s*[=:]\s*)"
    r"(?P<quote>[\"']?)(?P<value>[^\s\"',;]+)",
    re.IGNORECASE,
)
_BEARER = re.compile(r"(?P<head>\b(?:Bearer|Basic|Token)\s+)[A-Za-z0-9._~+/=-]{8,}", re.IGNORECASE)
_AUTH_HEADER = re.compile(r"(?P<head>\bAuthorization\s*:\s*)(?!Bearer\b|Basic\b|Token\b)\S+", re.IGNORECASE)
_NTFY = re.compile(r"\btk_[A-Za-z0-9]{8,}\b")
_ACK_LINK = re.compile(r"(?P<head>/ack/t/)[^\s\"'<>?#]+")
_ACK_TOKEN = re.compile(r"(?<![A-Za-z0-9_-])[A-Za-z0-9_-]{4,}\.\d{9,11}\.[A-Za-z0-9_-]{40,}(?![A-Za-z0-9_-])")
_JWT = re.compile(r"\beyJ[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}")
_PING = re.compile(r"(?P<head>\bhc-ping\.com/)[^\s\"'<>?#]+", re.IGNORECASE)
_URL_CREDS = re.compile(r"(?P<head>[a-z][a-z0-9+.-]*://[^/\s:@]+:)[^/\s@]+(?=@)", re.IGNORECASE)


def scrub(text: str, secrets: Iterable[str] = (), limit: int = LOG_TAIL_LIMIT) -> str:
    if not text:
        return ""
    # Longest first, so a secret that contains another is removed whole.
    for value in sorted({s for s in secrets if s and len(s) >= 4}, key=len, reverse=True):
        text = text.replace(value, MASK)
    text = _NAMED.sub(lambda m: f"{m['name']}{m['sep']}{m['quote']}{MASK}", text)
    text = _BEARER.sub(lambda m: f"{m['head']}{MASK}", text)
    text = _AUTH_HEADER.sub(lambda m: f"{m['head']}{MASK}", text)
    text = _NTFY.sub(MASK, text)
    text = _ACK_LINK.sub(lambda m: f"{m['head']}{MASK}", text)  # the shape of an acknowledge token (ack.py)
    text = _ACK_TOKEN.sub(MASK, text)
    text = _JWT.sub(MASK, text)  # whiskers' Home Assistant token
    text = _PING.sub(lambda m: f"{m['head']}{MASK}", text)  # nineLives' ping URL is its secret
    text = _URL_CREDS.sub(lambda m: f"{m['head']}{MASK}", text)
    return tail(text, limit)


def tail(text: str, limit: int = LOG_TAIL_LIMIT) -> str:
    """Keep the last ``limit`` bytes (UTF-8), cut at a line start when possible."""
    data = text.encode("utf-8")
    if len(data) <= limit:
        return text
    cut = data[-limit:]
    newline = cut.find(b"\n")
    if 0 <= newline < len(cut) - 1:
        cut = cut[newline + 1 :]
    return cut.decode("utf-8", errors="ignore")
