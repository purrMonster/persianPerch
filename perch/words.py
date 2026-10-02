"""words: small phrases for events and pages ("4 min", "6 d 4 h", "2nd")."""

from __future__ import annotations


def duration(seconds: float) -> str:
    """'45 s', '4 min', '1 h 10 min', '6 d 4 h': the two biggest units, never more."""
    s = max(0, int(seconds))
    if s < 60:
        return f"{s} s"
    if s < 3600:
        return f"{s // 60} min"
    if s < 86400:
        hours, minutes = s // 3600, s % 3600 // 60
        return f"{hours} h {minutes} min" if minutes else f"{hours} h"
    days, hours = s // 86400, s % 86400 // 3600
    return f"{days} d {hours} h" if hours else f"{days} d"


def ordinal(n: int) -> str:
    suffix = "th" if 10 <= n % 100 <= 20 else {1: "st", 2: "nd", 3: "rd"}.get(n % 10, "th")
    return f"{n}{suffix}"
