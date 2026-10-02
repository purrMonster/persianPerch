"""ack: the two signed tokens behind "Acknowledge" (05 plan A11, ADRs 0005 and 0006).

*The push token* rides in an ntfy ``http`` action button: ``<litterId>.<expiry>.<signature>``, the
signature an HMAC-SHA256 (key ``PERCH_ACK_SECRET``) over the litter id and the expiry. It can do one
thing, mark that one litter acknowledged, and only once (the spent ones are stored in scentTrail), for
24 hours or until the litter clears. perch never logs or displays one (scrub.py knows its shape).

*The form token* is the page's CSRF token: ``<expiry>.<signature>`` over a different prefix, so neither
can stand in for the other. perch has no session of its own (Authelia is the login), so the token is
stateless: bound to the litter and an expiry, signed with the same key.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

TOKEN_LIFE = timedelta(hours=24)
FORM_LIFE = timedelta(hours=6)


def b64(text: str) -> str:
    return base64.urlsafe_b64encode(text.encode()).rstrip(b"=").decode()


def _unb64(text: str) -> str | None:
    try:
        return base64.urlsafe_b64decode(text + "=" * (-len(text) % 4)).decode()
    except ValueError:
        return None


def _sign(secret: str, prefix: str, litterId: str, expires: int) -> str:
    digest = hmac.new(secret.encode(), f"{prefix}\n{litterId}\n{expires}".encode(), hashlib.sha256).digest()
    return base64.urlsafe_b64encode(digest).rstrip(b"=").decode()


def _epoch(moment: datetime) -> int:
    return int(moment.astimezone(UTC).timestamp())


@dataclass(frozen=True)
class Checked:
    litterId: str
    expires: datetime
    tokenId: str  # the signature: one per litter and expiry, and what "spent" is recorded under


def mint(secret: str, litterId: str, now: datetime, life: timedelta = TOKEN_LIFE) -> str:
    if not secret:
        raise ValueError("PERCH_ACK_SECRET isn't set")
    expires = _epoch(now + life)
    return f"{b64(litterId)}.{expires}.{_sign(secret, 'ack1', litterId, expires)}"


def verify(secret: str, token: str, now: datetime) -> Checked | None:
    """The litter a push token names, or None: wrong shape, wrong signature, or expired. Whether the
    litter is still open and the token unspent is the caller's business (it needs the database)."""
    if not secret or not isinstance(token, str) or len(token) > 400:
        return None
    parts = token.split(".")
    if len(parts) != 3:
        return None
    name, expiry, sig = parts
    litterId = _unb64(name)
    if litterId is None or not expiry.isdigit() or not sig:
        return None
    expires = int(expiry)
    if not hmac.compare_digest(sig.encode(), _sign(secret, "ack1", litterId, expires).encode()):
        return None
    if expires < _epoch(now):
        return None
    return Checked(litterId, datetime.fromtimestamp(expires, UTC), sig)


def csrfMint(secret: str, litterId: str, now: datetime) -> str:
    expires = _epoch(now + FORM_LIFE)
    return f"{expires}.{_sign(secret, 'csrf1', litterId, expires)}"


def csrfOk(secret: str, litterId: str, token: str, now: datetime) -> bool:
    if not secret or not isinstance(token, str) or len(token) > 200:
        return False
    parts = token.split(".")
    if len(parts) != 2 or not parts[0].isdigit() or not parts[1]:
        return False
    expires = int(parts[0])
    good = hmac.compare_digest(parts[1].encode(), _sign(secret, "csrf1", litterId, expires).encode())
    return good and expires >= _epoch(now)
