"""Docker's own status text, as Komodo's container list passes it through."""

import pytest

from perch.senses.dockerStatus import DockerStatus, exitMeaning, parseStatus


@pytest.mark.parametrize(
    ("text", "uptime", "health"),
    [
        ("Up Less than a second", 0, None),
        ("Up 1 second", 1, None),
        ("Up 12 seconds", 12, None),
        ("Up About a minute", 60, None),
        ("Up 5 minutes (unhealthy)", 300, "unhealthy"),
        ("Up 2 minutes (health: starting)", 120, "starting"),
        ("Up About an hour", 3600, None),
        ("Up 3 hours (healthy)", 10800, "healthy"),
        ("Up 2 days", 172800, None),
        ("Up 3 weeks (healthy)", 1814400, "healthy"),
        ("Up 2 months", 5184000, None),
        ("Up 2 years", 63072000, None),
    ],
)
def test_up_statuses(text, uptime, health):
    assert parseStatus(text) == DockerStatus(uptime=uptime, health=health)


def test_paused_is_not_a_health_state():
    assert parseStatus("Up 3 hours (Paused)") == DockerStatus(uptime=10800, paused=True)


@pytest.mark.parametrize(
    ("text", "code"),
    [("Exited (137) 3 minutes ago", 137), ("Exited (0) 2 days ago", 0), ("Restarting (1) 12 seconds ago", 1)],
)
def test_exit_codes(text, code):
    assert parseStatus(text) == DockerStatus(exitCode=code)


@pytest.mark.parametrize("text", ["", "Created", "Dead", "Removal In Progress", "whatever Docker invents next", None])
def test_anything_else_says_nothing(text):
    assert parseStatus(text) == DockerStatus()


def test_exit_meanings():
    assert "out of memory" in exitMeaning(137)
    assert exitMeaning(0).startswith("stopped cleanly")
    assert "terminated" in exitMeaning(143)
    assert exitMeaning(42) == "exit code 42"
    assert exitMeaning(None) == ""


def test_docker_uptime_words_never_go_backwards_below_two_years():
    """purr tells a restart from a lower uptime than last cycle's. That works only if Docker's
    rounded words are monotone for a process that kept running: check them over everything
    from a second to just under two years, in the fake's copy of go-units' rules."""
    from komodoFake import humanDuration

    last = -1
    for seconds in [*range(0, 4000), *range(4000, 63_000_000, 997)]:
        uptime = parseStatus(f"Up {humanDuration(seconds)}").uptime
        assert uptime is not None and uptime >= last, (seconds, humanDuration(seconds))
        last = uptime


def test_go_units_quirk_at_two_years_is_real_and_is_why_purr_also_wants_a_short_uptime():
    from komodoFake import humanDuration

    before, after = 63_070_190, 63_070_220  # 30 s apart, straddling half an hour before the 2-year mark
    assert humanDuration(before) == "24 months" and humanDuration(after) == "1 years"
    assert parseStatus("Up 1 years").uptime < parseStatus("Up 24 months").uptime  # backwards, yet no restart
