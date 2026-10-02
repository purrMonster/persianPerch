"""The signed acknowledge token (05 plan A11) and the page's CSRF token (ADR 0005), as pure functions."""

from datetime import UTC, datetime, timedelta

from perch import ack

NOW = datetime(2026, 10, 2, 12, 0, tzinfo=UTC)
SECRET = "fake-ack-secret-not-real-0123456789abcdef"
LITTER = "app.grinder.n8n@20261002T115500Z"


def test_a_fresh_token_names_its_litter_and_expires_in_24_hours():
    token = ack.mint(SECRET, LITTER, NOW)
    checked = ack.verify(SECRET, token, NOW + timedelta(hours=23, minutes=59))
    assert checked is not None and checked.litterId == LITTER
    assert checked.expires == NOW + timedelta(hours=24)
    assert ack.verify(SECRET, token, NOW + timedelta(hours=24, seconds=1)) is None


def test_a_tampered_token_never_verifies():
    token = ack.mint(SECRET, LITTER, NOW)
    head, expires, sig = token.split(".")
    other = ack.mint(SECRET, "app.grinder.other@20261002T115500Z", NOW).split(".")[0]
    for bad in (
        f"{other}.{expires}.{sig}",  # another litter's name with this signature
        f"{head}.{int(expires) + 1}.{sig}",  # a longer life
        f"{head}.{expires}.{sig[:-1]}{'A' if sig[-1] != 'A' else 'B'}",  # one wrong character
        f"{head}.{expires}.",
        "",
        "x.y.z",
        token + ".extra",
        "....",
    ):
        assert ack.verify(SECRET, bad, NOW) is None, bad


def test_another_secret_never_verifies():
    token = ack.mint(SECRET, LITTER, NOW)
    assert ack.verify("fake-other-secret-not-real-0123456789", token, NOW) is None
    assert ack.verify("", token, NOW) is None


def test_the_token_id_is_the_signature_and_differs_per_litter_and_expiry():
    a = ack.verify(SECRET, ack.mint(SECRET, LITTER, NOW), NOW)
    b = ack.verify(SECRET, ack.mint(SECRET, LITTER, NOW + timedelta(seconds=5)), NOW)
    c = ack.verify(SECRET, ack.mint(SECRET, "other@1", NOW), NOW)
    assert len({a.tokenId, b.tokenId, c.tokenId}) == 3


def test_the_token_is_url_safe_and_short_enough_for_an_ntfy_button():
    token = ack.mint(SECRET, LITTER, NOW)
    assert all(ch.isalnum() or ch in "-_." for ch in token)
    assert len(token) < 200


def test_the_csrf_token_is_bound_to_the_litter_and_expires():
    token = ack.csrfMint(SECRET, LITTER, NOW)
    assert ack.csrfOk(SECRET, LITTER, token, NOW + timedelta(hours=5))
    assert not ack.csrfOk(SECRET, LITTER, token, NOW + timedelta(hours=7))
    assert not ack.csrfOk(SECRET, "app.grinder.other@20261002T115500Z", token, NOW)
    assert not ack.csrfOk("fake-other-secret-not-real-0123456789", LITTER, token, NOW)
    assert not ack.csrfOk(SECRET, LITTER, "", NOW)
    assert not ack.csrfOk(SECRET, LITTER, "1.2", NOW)
    assert not ack.csrfOk(SECRET, LITTER, token.replace(".", ":"), NOW)


def test_a_push_token_is_not_a_csrf_token_and_the_other_way_round():
    """The two are signed over different prefixes: one can never stand in for the other."""
    push = ack.mint(SECRET, LITTER, NOW)
    assert not ack.csrfOk(SECRET, LITTER, push.split(".", 1)[1], NOW)
    form = ack.csrfMint(SECRET, LITTER, NOW)
    assert ack.verify(SECRET, f"{ack.b64(LITTER)}.{form}", NOW) is None
