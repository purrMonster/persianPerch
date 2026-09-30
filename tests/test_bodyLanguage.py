import pytest

from perch.bodyLanguage import LEVELS, BodyLanguage, worstOf

B = BodyLanguage


def test_levels_in_legend_order():
    assert [lv.value for lv in LEVELS] == ["slowBlink", "earTwitch", "tailFlick", "hiss"]


@pytest.mark.parametrize(
    ("levels", "worst"),
    [
        ([B.slowBlink, B.slowBlink], B.slowBlink),
        ([B.slowBlink, B.earTwitch], B.earTwitch),
        (["earTwitch", "tailFlick", "slowBlink"], B.tailFlick),
        ([B.tailFlick, B.hiss, B.earTwitch], B.hiss),
        ([B.slowBlink, B.unknown], B.unknown),
        ([B.earTwitch, B.unknown], B.unknown),
        ([B.unknown, B.tailFlick], B.tailFlick),
        ([B.unknown, B.hiss], B.hiss),
    ],
)
def test_worst_of(levels, worst):
    assert worstOf(levels) is worst


def test_worst_of_nothing_is_unknown_or_given():
    assert worstOf([]) is B.unknown
    assert worstOf([], empty=B.slowBlink) is B.slowBlink


def test_never_colour_alone():
    looks = [(lv.icon, lv.value) for lv in B]
    assert len({icon for icon, _ in looks}) == len(looks), "each level needs its own icon"
    assert all(icon and word for icon, word in looks)
    assert B.hiss.colour == "#c8453b" and B.slowBlink.colour == "#6fa287"


def test_parse_rejects_nonsense():
    with pytest.raises(ValueError):
        BodyLanguage.parse("purring")
