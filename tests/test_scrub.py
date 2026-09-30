"""S2: scrubbed log tails never contain a value from tests/fixtures/secrets.fake.env."""

from pathlib import Path

import pytest

from perch.scrub import LOG_TAIL_LIMIT, MASK, scrub

FAKE = Path(__file__).parent / "fixtures" / "secrets.fake.env"


def fakeSecrets() -> dict[str, str]:
    pairs = {}
    for line in FAKE.read_text(encoding="utf-8").splitlines():
        if line and not line.startswith("#") and "=" in line:
            key, value = line.split("=", 1)
            pairs[key] = value
    return pairs


SECRETS = fakeSecrets()


def test_fixture_has_secrets():
    assert len(SECRETS) >= 5 and all(SECRETS.values())


@pytest.mark.parametrize("key", sorted(SECRETS))
def test_known_values_are_removed(key):
    value = SECRETS[key]
    log = f"starting\nusing {value} for auth\n{key}={value}\nconnecting with '{value}'\n"
    out = scrub(log, SECRETS.values())
    assert value not in out
    assert "starting" in out and MASK in out


@pytest.mark.parametrize("key", sorted(SECRETS))
def test_named_values_are_removed_even_when_unknown(key):
    """A secret perch wasn't told about is still masked when it follows its name."""
    value = SECRETS[key]
    out = scrub(f"env: {key}={value} other=1\n{key.lower()}: {value}\n")
    assert value not in out


@pytest.mark.parametrize(
    "line",
    [
        "Authorization: Bearer eyJhbGciOiJIUzI1NiJ9.fakefakefake",
        "curl -H 'Authorization: Basic ZmFrZTpmYWtlZmFrZQ=='",
        "ntfy token tk_fakefakefakefakefakefakefak used",
        "https://restic:fakepassword99@example.home.arpa/repo",
        'RESTIC_PASSWORD="fake pass phrase"',
        "db_password: fakeDbPass42",
    ],
)
def test_credential_shapes_are_removed(line):
    out = scrub(line)
    for secret in ("eyJhbGciOiJIUzI1NiJ9", "ZmFrZTpmYWtl", "tk_fake", "fakepassword99", "fake pass", "fakeDbPass42"):
        assert secret not in out


def test_tail_keeps_newest_16kb():
    log = "\n".join(f"line {i:06d}" for i in range(5000))
    out = scrub(log)
    assert len(out.encode()) <= LOG_TAIL_LIMIT
    assert out.endswith("line 004999") and not out.startswith("line 000000")


def test_ordinary_text_survives():
    text = "backup finished: 214 MB added, snapshot 5c1e9a07, keys checked"
    assert scrub(text) == text
