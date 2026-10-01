"""Worst-of rollup, app -> node -> fleet (design plan 3.3), against the pinned fleet repo."""

import pytest

from perch.bodyLanguage import BodyLanguage as B
from perch.catTree import CatTree
from perch.rollup import Status
from perch.scentTrail import ScentTrail


@pytest.fixture
def fleet(fleetTree):
    return fleetTree.fleet()


@pytest.fixture
def trail(tmp_path, clock):
    t = ScentTrail(tmp_path / "t.db", clock=clock)
    yield t
    t.close()


def everythingOk(fleet, trail, level=B.slowBlink):
    for node in fleet.nodes:
        for app in node.apps:
            trail.setState(app.id, level)
        trail.setState(node.id, level)


def test_no_data_is_unknown_everywhere_never_ok(fleet, trail):
    status = Status(fleet, trail)
    assert status.app("grinder", "n8n") is B.unknown
    assert status.node("grinder") is B.unknown
    assert status.fleetLevel() is B.unknown
    assert status.counts()[B.unknown] == fleet.appCount


def test_all_ok_is_slowBlink(fleet, trail):
    everythingOk(fleet, trail)
    status = Status(fleet, trail)
    assert status.fleetLevel() is B.slowBlink and status.node("grinder") is B.slowBlink
    assert status.counts()[B.slowBlink] == fleet.appCount


def test_one_hissing_app_hisses_its_node_and_the_fleet_only(fleet, trail):
    everythingOk(fleet, trail)
    trail.setState("app:grinder/n8n", B.hiss, title="exited")
    status = Status(fleet, trail)
    assert status.app("grinder", "n8n") is B.hiss
    assert status.node("grinder") is B.hiss and status.fleetLevel() is B.hiss
    for other in ("sieve", "percolator", "cellar", "mochaPot", "roastery"):
        assert status.node(other) is B.slowBlink, other
    assert status.app("grinder", "traefik") is B.slowBlink


def test_a_nodes_own_state_joins_its_apps(fleet, trail):
    everythingOk(fleet, trail)
    trail.setState("node:cellar", B.tailFlick, title="disk 88 % full")
    status = Status(fleet, trail)
    assert status.node("cellar") is B.tailFlick and status.fleetLevel() is B.tailFlick
    assert status.app("cellar", "komodo") is B.slowBlink


def test_unknown_sits_between_notice_and_warning(fleet, trail):
    everythingOk(fleet, trail)
    trail.setState("app:sieve/pihole", B.earTwitch)
    assert Status(fleet, trail).fleetLevel() is B.earTwitch
    trail.setState("app:sieve/ntfy", B.unknown)
    assert Status(fleet, trail).fleetLevel() is B.unknown  # a notice never hides that perch can't see
    trail.setState("app:sieve/unbound", B.tailFlick)
    assert Status(fleet, trail).fleetLevel() is B.tailFlick  # and unknown never masks a warning


def test_collectors_count_toward_the_fleet_but_no_node(fleet, trail):
    everythingOk(fleet, trail)
    trail.setState("collector:purr", B.hiss, title="purr is missing")
    status = Status(fleet, trail)
    assert status.fleetLevel() is B.hiss
    assert all(status.node(n.name) is B.slowBlink for n in fleet.nodes)
    assert list(status.collectors()) == ["purr"]


def test_up_counts_are_apps_that_are_not_failing(fleet, trail):
    everythingOk(fleet, trail)
    trail.setState("app:grinder/n8n", B.hiss)
    trail.setState("app:grinder/traccar", B.tailFlick)
    trail.setState("app:grinder/esphome", B.earTwitch)
    trail.setState("app:grinder/openwebui", B.unknown)
    total = len(fleet.node("grinder").apps)
    assert Status(fleet, trail).upCount("grinder") == (total - 3, total)  # earTwitch is still up


def test_attention_lists_what_needs_a_look_worst_first(fleet, trail, clock):
    everythingOk(fleet, trail)
    trail.setState("app:grinder/traccar", B.tailFlick, title="restarting")
    clock.advance(minutes=5)
    trail.setState("app:grinder/n8n", B.hiss, title="exited (137)")
    trail.setState("node:cellar", B.tailFlick, title="disk 88 % full")
    trail.setState("app:sieve/pihole", B.earTwitch)  # a notice is not attention
    trail.setState("app:sieve/ntfy", B.unknown)  # nor is not knowing
    items = Status(fleet, trail).attention()
    assert [(i.label, i.level) for i in items] == [
        ("grinder/n8n", B.hiss),
        ("grinder/traccar", B.tailFlick),
        ("cellar", B.tailFlick),
    ]
    assert items[0].href == "/tree/grinder/n8n" and items[2].href == "/tree/cellar"
    assert items[0].title == "exited (137)" and items[0].since == clock()


def test_node_note_is_the_one_line_a_node_card_shows(fleet, trail):
    everythingOk(fleet, trail)
    assert Status(fleet, trail).nodeNote("grinder") is None  # all well: nothing to say
    trail.setState("app:grinder/traccar", B.tailFlick, title="is restarting (last exit code 1)")
    assert Status(fleet, trail).nodeNote("grinder") == (B.tailFlick, "traccar: is restarting (last exit code 1)")
    trail.setState("app:grinder/n8n", B.hiss, title="exited (code 137)")
    assert Status(fleet, trail).nodeNote("grinder") == (B.hiss, "n8n: exited (code 137)")
    trail.setState("node:grinder", B.tailFlick, title="grinder: disk 88 % full")
    assert Status(fleet, trail).nodeNote("grinder")[0] is B.hiss  # the worst wins
    trail.setState("node:grinder", B.hiss, title="grinder isn't answering")
    assert Status(fleet, trail).nodeNote("grinder") == (B.hiss, "grinder isn't answering")  # the node itself first


def test_a_sleeping_node_says_so_in_its_note(fleet, trail):
    everythingOk(fleet, trail)
    trail.setState("node:roastery", B.slowBlink, title="asleep, as expected (wakes 01:25)", detail={"mode": "asleep"})
    assert Status(fleet, trail).nodeNote("roastery") == (B.slowBlink, "asleep, as expected (wakes 01:25)")


def test_containers_of_an_app_and_strays(fleet, trail):
    trail.setState("container:grinder/karakeep", B.slowBlink, detail={"app": "karakeep"})
    trail.setState("container:grinder/karakeep-chrome", B.hiss, detail={"app": "karakeep"})
    trail.setState("container:grinder/n8n", B.slowBlink, detail={"app": "n8n"})
    trail.setState("container:grinder/stray-test", B.slowBlink, detail={"stray": True})
    status = Status(fleet, trail)
    app = fleet.node("grinder").app("karakeep")
    assert [s.subject for s in status.containers("grinder", app)] == [
        "container:grinder/karakeep",
        "container:grinder/karakeep-chrome",
    ]  # in compose order, and only this app's
    assert [s.subject for s in status.strays("grinder")] == ["container:grinder/stray-test"]


def test_an_app_without_a_compose_file_is_not_watched(tmp_path, clock):
    from conftest import makeRepo

    repo = makeRepo(
        tmp_path / "r",
        {
            "stacks/sieve/node.conf": "APPS=(web notes)\n",
            "stacks/sieve/web/docker-compose.yml": "services:\n  web:\n    image: x/web:1\n    container_name: web\n",
            "stacks/sieve/notes/README.md": "just notes, no containers\n",
        },
    )
    fleet = CatTree(repo).fleet()
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    try:
        trail.setState("app:sieve/web", B.slowBlink)
        status = Status(fleet, trail)
        assert status.watched(fleet.node("sieve").app("notes")) is False
        assert status.node("sieve") is B.slowBlink  # the unwatched app doesn't make the node unknown
        assert status.counts()[B.unknown] == 0 and status.upCount("sieve") == (1, 1)
    finally:
        trail.close()
