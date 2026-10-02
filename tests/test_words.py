import pytest

from perch.words import duration, ordinal


@pytest.mark.parametrize(
    ("seconds", "text"),
    [
        (0, "0 s"),
        (45, "45 s"),
        (59.9, "59 s"),
        (60, "1 min"),
        (4 * 60 + 20, "4 min"),
        (3600, "1 h"),
        (3600 + 600, "1 h 10 min"),
        (86400 - 1, "23 h 59 min"),
        (86400, "1 d"),
        (6 * 86400 + 4 * 3600 + 1800, "6 d 4 h"),
        (-5, "0 s"),  # a clock that stepped back is not a negative duration
    ],
)
def test_duration(seconds, text):
    assert duration(seconds) == text


@pytest.mark.parametrize(
    ("n", "text"),
    [
        (1, "1st"),
        (2, "2nd"),
        (3, "3rd"),
        (4, "4th"),
        (11, "11th"),
        (12, "12th"),
        (13, "13th"),
        (21, "21st"),
        (112, "112th"),
    ],
)
def test_ordinal(n, text):
    assert ordinal(n) == text
