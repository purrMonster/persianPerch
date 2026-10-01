"""rhythms: collector misses (design plan 3.4), roastery's sleep window (05 plan C5) and
the timers' OnCalendar lines (C4), against the pinned fleet repo."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import pytest

from perch.bodyLanguage import BodyLanguage as B
from perch.rhythms import (
    ROASTERY_STAY_UP_DEFAULT,
    ROASTERY_WAKE_DEFAULT,
    OnCalendar,
    Rhythm,
    SleepWindow,
    sleepWindowFromRepo,
)

IST = ZoneInfo("Asia/Kolkata")
T0 = datetime(2026, 9, 29, 12, 0, tzinfo=UTC)


# -- collector rhythm ---------------------------------------------------------


@pytest.mark.parametrize(
    ("elapsed", "misses", "level"),
    [
        (0, 0, B.slowBlink),
        (30, 0, B.slowBlink),  # due now: the cycle in flight is not a miss
        (39, 0, B.slowBlink),  # inside the grace (every / 3 = 10 s)
        (40, 1, B.slowBlink),
        (99, 2, B.slowBlink),
        (100, 3, B.tailFlick),  # 3 misses: late
        (309, 9, B.tailFlick),
        (310, 10, B.hiss),  # 10 misses: missing
        (3600, 119, B.hiss),
    ],
)
def test_purr_rhythm_levels(elapsed, misses, level):
    rhythm = Rhythm(every=30, late=3, missing=10)
    now = T0 + timedelta(seconds=elapsed)
    assert rhythm.misses(T0, now) == misses
    assert rhythm.level(T0, now) is level


def test_a_clock_that_runs_backwards_is_no_miss():
    assert Rhythm(every=30).misses(T0, T0 - timedelta(seconds=5)) == 0


def test_rhythm_scales_with_its_period():
    kitten = Rhythm(every=60, late=3, missing=10)  # design plan 3.4: late 3 min, missing 10 min
    assert kitten.level(T0, T0 + timedelta(seconds=160)) is B.slowBlink
    assert kitten.level(T0, T0 + timedelta(seconds=200)) is B.tailFlick
    assert kitten.level(T0, T0 + timedelta(seconds=620)) is B.hiss


# -- OnCalendar ---------------------------------------------------------------


@pytest.mark.parametrize(
    ("text", "at", "matches"),
    [
        ("*-*-* 01:25:00", datetime(2026, 9, 29), True),
        ("*-*-* 01:25", datetime(2026, 9, 29), True),
        ("Sun *-*-* 03:00:00", datetime(2026, 9, 27), True),  # a Sunday
        ("Sun *-*-* 03:00:00", datetime(2026, 9, 28), False),
        ("*-*-01 04:30:00", datetime(2026, 10, 1), True),
        ("*-*-01 04:30:00", datetime(2026, 10, 2), False),
    ],
)
def test_on_calendar_forms_in_the_repo(text, at, matches):
    cal = OnCalendar.parse(text)
    assert cal.matches(at.date()) is matches


def test_on_calendar_time_and_unsupported_forms():
    assert OnCalendar.parse("*-*-* 01:25:00").time == time(1, 25)
    for bad in ("hourly", "Mon..Fri *-*-* 09:00", "*-*-* *:00:00", "2026-10-01 04:30", ""):
        with pytest.raises(ValueError, match="OnCalendar"):
            OnCalendar.parse(bad)


def test_every_timer_in_the_pinned_repo_parses(fleetRepo):
    seen = {}
    for timer in sorted((fleetRepo / "stacks").rglob("*.timer")):
        for line in timer.read_text(encoding="utf-8").splitlines():
            if line.startswith("OnCalendar="):
                seen[timer.name] = OnCalendar.parse(line.split("=", 1)[1].strip())
    # an exact set: a timer that appears with a form we don't parse must fail here, not at M2
    assert set(seen) == {
        "purrbrews-backup@.timer",  # nightly, every node, 01:30 (+ up to 5 min)
        "purrbrews-wake-roastery.timer",  # 01:25
        "purrbrews-backup-store.timer",  # 02:30
        "drive-sync.timer",  # 03:30
        "restic-prune.timer",  # Sundays 03:00
        "purrbrews-backup-verify.timer",  # 1st of the month 04:30
        "purrbrews-backup-check.timer",  # 06:00
    }
    assert seen["purrbrews-wake-roastery.timer"].time == time(1, 25)
    assert seen["purrbrews-backup-verify.timer"].day == 1


# -- roastery's sleep window --------------------------------------------------


def window(**kw):
    return SleepWindow(
        wake=kw.get("wake", time(1, 25)),
        stayUp=kw.get("stayUp", timedelta(hours=3)),
        settle=kw.get("settle", timedelta(minutes=10)),
        tz=IST,
    )


def ist(h, m, s=0, day=29):
    return datetime(2026, 9, day, h, m, s, tzinfo=IST)


@pytest.mark.parametrize(
    ("when", "awake", "mustAnswer"),
    [
        (ist(1, 24, 59), False, False),
        (ist(1, 25), True, False),  # woken, may still be coming up
        (ist(1, 34, 59), True, False),
        (ist(1, 35), True, True),  # 10 minutes later it must answer (the nightly waits up to 10)
        (ist(4, 24, 59), True, True),
        (ist(4, 25), False, False),  # 01:25 + 3 h: Windows' unattended-sleep timeout
        (ist(14, 0), False, False),
    ],
)
def test_sleep_window(when, awake, mustAnswer):
    w = window()
    assert w.expectedUp(when) is awake  # may be asleep outside; this is "expected awake"
    assert w.mustAnswer(when) is mustAnswer


def test_window_works_on_utc_instants_and_across_midnight():
    w = window()
    assert w.expectedUp(datetime(2026, 9, 28, 20, 0, tzinfo=UTC))  # 01:30 IST
    assert not w.expectedUp(datetime(2026, 9, 28, 19, 50, tzinfo=UTC))  # 01:20 IST
    late = window(wake=time(23, 0))
    assert late.expectedUp(ist(0, 30)) and late.expectedUp(ist(1, 59)) and not late.expectedUp(ist(2, 0))


def test_next_wake():
    w = window()
    assert w.nextWake(ist(14, 0)) == ist(1, 25, day=30)
    assert w.nextWake(ist(0, 10)) == ist(1, 25)
    assert w.nextWake(ist(2, 0)) == ist(1, 25, day=30)  # already awake today: the next one is tomorrow's


def test_window_from_the_pinned_repo(fleetRepo):
    from perch.catTree import CatTree

    tree = CatTree(fleetRepo)
    found = sleepWindowFromRepo(tree, tree.fleet(), IST)
    assert found.wake == time(1, 25) and found.stayUp == timedelta(minutes=180)
    assert found.source == "repo"


def test_window_defaults_when_the_repo_is_silent(tmp_path):
    from conftest import makeRepo

    from perch.catTree import CatTree

    repo = makeRepo(tmp_path / "r", {"stacks/sieve/node.conf": "APPS=(a)\n", "stacks/sieve/a/README.md": "x"})
    tree = CatTree(repo)
    found = sleepWindowFromRepo(tree, tree.fleet(), IST)
    assert (found.wake, found.stayUp, found.source) == (ROASTERY_WAKE_DEFAULT, ROASTERY_STAY_UP_DEFAULT, "default")


def test_window_ignores_a_timer_it_cannot_read(tmp_path):
    from conftest import makeRepo

    from perch.catTree import CatTree

    repo = makeRepo(
        tmp_path / "r",
        {
            "stacks/sieve/node.conf": "APPS=(a)\n",
            "stacks/cellar/node.conf": "APPS=()\n",
            "stacks/cellar/restic/purrbrews-wake-roastery.timer": "[Timer]\nOnCalendar=hourly\n",
            "stacks/roastery/node.conf": "APPS=()\n",
            "stacks/roastery/backup-target/setup.ps1": "param([int]$UnattendedSleepMinutes = 45,)\n",
        },
    )
    tree = CatTree(repo)
    found = sleepWindowFromRepo(tree, tree.fleet(), IST)
    # a timer it can't parse falls back to the default wake; the readable length is still used
    assert found.wake == ROASTERY_WAKE_DEFAULT and found.stayUp == timedelta(minutes=45)
    assert found.source == "repo+default"
