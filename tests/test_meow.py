"""meow (05 plan M3, design plan 5, ADR 0004), against a fake Komodo, a fake ntfy, a fake critical
topic and a fake clock. The real ntfy is never contacted."""

from datetime import UTC, datetime, timedelta

import pytest
from pushFakes import CRITICAL_URL, NTFY_TOKEN, NTFY_URL, NtfyFake
from world import IST, World

from perch import ack
from perch.bodyLanguage import BodyLanguage as B
from perch.litters import Litters
from perch.meow import Meow, inQuiet, parseQuiet
from perch.rollup import Status

SECRET = "fake-ack-secret-not-real-0123456789abcdef"
PUBLIC = "https://perch.example.home.arpa"


class MeowWorld(World):
    def __init__(self, fleetTree, tmp_path, clock, **meowArgs):
        super().__init__(fleetTree, tmp_path, clock)
        self.tree = fleetTree
        self.ntfy, self.critical = NtfyFake(token=NTFY_TOKEN), NtfyFake()
        args = {"ackSecret": SECRET, "publicUrl": PUBLIC} | meowArgs
        self.meow = self.makeMeow(**args)
        self.litters = Litters(self.trail)

    def makeMeow(self, **args):
        return Meow(
            self.trail,
            self.tree,
            clock=self.clock,
            tz=IST,
            ntfy=self.ntfy.client(NTFY_URL, NTFY_TOKEN),
            critical=self.critical.client(CRITICAL_URL),
            **args,
        )

    def step(self, n=1, every=30):
        """purr, then meow, n times, ``every`` seconds apart."""
        for _ in range(n):
            self.cycle()
            self.loop.run_until_complete(self.meow.cycle())
            self.clock.advance(seconds=every - 30)

    def wait(self, n):
        """n minutes of nothing happening to the fleet: only meow looks, once a minute."""
        for _ in range(int(n)):
            self.meowOnly(seconds=60)

    def meowOnly(self, seconds=30):
        self.loop.run_until_complete(self.meow.cycle())
        self.clock.advance(seconds=seconds)

    def close(self):
        self.loop.run_until_complete(self.meow.aclose())
        super().close()


@pytest.fixture
def w(fleetTree, tmp_path, clock):
    world = MeowWorld(fleetTree, tmp_path, clock)
    yield world
    world.close()


def at(hour, minute=0, day=29):
    """Local (IST) time on the test day, as the UTC instant the fake clock carries."""
    return datetime(2026, 9, day, hour, minute, tzinfo=IST).astimezone(UTC)


# -- the pure parts -----------------------------------------------------------------------------


def test_quiet_hours_wrap_midnight_and_end_is_exclusive():
    from datetime import time

    quiet = parseQuiet("23:00-07:00")
    assert inQuiet(time(23, 0), quiet) and inQuiet(time(3, 0), quiet) and inQuiet(time(6, 59), quiet)
    assert not inQuiet(time(7, 0), quiet) and not inQuiet(time(12, 0), quiet) and not inQuiet(time(22, 59), quiet)
    assert inQuiet(time(13, 0), parseQuiet("12:00-14:00")) and not inQuiet(time(15, 0), parseQuiet("12:00-14:00"))
    with pytest.raises(ValueError):
        parseQuiet("night")


# -- the gate: a node goes down ------------------------------------------------------------------


def test_GATE_grinder_down_is_one_push_per_channel_then_one_recovery(w):
    apps = sum(1 for a in w.fleet.node("grinder").apps if Status.watched(a))
    assert apps > 3
    w.step(2)
    assert w.ntfy.sent == [] and w.critical.sent == []  # nothing yet: all fine
    w.fake.nodeDown("grinder")
    w.step(6)  # purr confirms on its second look; the apps turn unknown, the node hisses
    assert w.status().node("grinder") is B.hiss
    assert len(w.ntfy.sent) == 1 and len(w.critical.sent) == 1, (w.ntfy.titles(), w.critical.titles())
    push = w.ntfy.sent[0]
    assert push.title == f"perch: grinder unreachable: {apps} apps affected"
    assert push.priority == 4 and push.topic == "fake-alerts-topic"
    assert push.auth == f"Bearer {NTFY_TOKEN}"
    assert w.critical.sent[0].title == push.title and w.critical.sent[0].priority == 4
    w.step(20)  # ten more minutes of the same outage: still the one push, not one per app
    assert len(w.ntfy.sent) == 1 and len(w.critical.sent) == 1
    w.fake.nodeUp("grinder")
    w.step(6)
    assert len(w.ntfy.sent) == 2 and len(w.critical.sent) == 2
    back = w.ntfy.sent[1]
    assert back.title.startswith("perch: grinder back, was down ") and back.priority == 3
    w.step(80)  # an hour more: nothing else, and no repeat of the hiss
    assert len(w.ntfy.sent) == 2 and len(w.critical.sent) == 2


def test_the_hiss_repeats_every_30_minutes_until_acknowledged(w):
    w.fake.nodeDown("grinder")
    w.step(4)
    assert len(w.ntfy.sent) == 1
    w.wait(27)  # about 29 minutes after the first push
    assert len(w.ntfy.sent) == 1
    w.wait(4)
    assert len(w.ntfy.sent) == 2 and w.ntfy.sent[1].title.startswith("perch: still unacknowledged: grinder unreachable")
    litter = w.litters.open()[0]
    assert w.litters.acknowledge(litter.litterId, "the page", w.clock())
    w.wait(120)
    assert len(w.ntfy.sent) == 2 and len(w.critical.sent) == 2  # acknowledged: the repeats stop


def test_a_new_hiss_alerts_even_after_an_acknowledgement(w):
    w.fake.nodeDown("grinder")
    w.step(4)
    w.litters.acknowledge(w.litters.open()[0].litterId, "the page", w.clock())
    w.fake.exit("cellar", "scrutiny", 1)
    w.step(4)
    titles = w.ntfy.titles()
    assert len(titles) == 2 and "cellar" in titles[1]


def test_a_node_litter_absorbs_the_apps_litters_it_already_had(w):
    w.fake.exit("grinder", "n8n", 137)
    w.step(4)
    assert [lt.key for lt in w.litters.open()] == ["app:grinder/n8n"]
    w.fake.nodeDown("grinder")
    w.step(6)
    assert [lt.key for lt in w.litters.open()] == ["down:grinder"]
    w.fake.nodeUp("grinder")
    w.fake.restart("grinder", "n8n")
    w.step(6)
    titles = w.ntfy.titles()
    assert sum("back" in t for t in titles) == 1, titles  # the node's recovery; the absorbed app has none of its own


def test_perch_going_blind_is_not_a_recovery(w):
    w.fake.exit("grinder", "n8n", 137)
    w.step(4)
    assert len(w.ntfy.sent) == 1
    w.fake.komodoDown = True
    w.step(8)  # every state turns unknown: perch can't see, which is not the problem being fixed
    assert [lt.key for lt in w.litters.open()] == ["app:grinder/n8n"]
    assert len(w.ntfy.sent) == 1


# -- tailFlick, earTwitch, quiet hours, the digest --------------------------------------------------------


def test_a_tailFlick_waits_5_minutes_goes_to_ntfy_only_and_is_pushed_once_per_6_hours(w):
    w.fake.vitals("cellar", disk=88.0)
    w.step(8)  # 4 minutes
    assert w.ntfy.sent == []
    w.step(4)  # past 5 minutes
    assert len(w.ntfy.sent) == 1 and w.critical.sent == []
    push = w.ntfy.sent[0]
    assert push.priority == 3 and "cellar" in push.title and push.title.startswith("perch: ")
    w.wait(300)  # five hours: no repeat
    assert len(w.ntfy.sent) == 1
    w.wait(70)  # past six
    assert len(w.ntfy.sent) == 2 and w.ntfy.sent[1].title.startswith("perch: still: ")


def test_tailFlicks_that_arrive_together_are_one_push(w):
    w.fake.vitals("cellar", disk=88.0)
    w.fake.vitals("sieve", disk=87.0)
    w.fake.vitals("grinder", disk=86.0)
    w.step(14)
    assert len(w.ntfy.sent) == 1
    assert w.ntfy.sent[0].title == "perch: 3 things need a look" and w.ntfy.sent[0].actions == []


def test_an_earTwitch_never_pushes_and_the_digest_carries_it_at_0730(w):
    w.fake.setHealth("cellar", "scrutiny", "health: starting")  # earTwitch: "is starting"
    w.step(4)
    assert w.status().app("cellar", "scrutiny") is B.earTwitch
    w.wait(25)  # to 07:27
    assert w.ntfy.sent == []
    w.wait(5)
    assert len(w.ntfy.sent) == 1
    digest = w.ntfy.sent[0]
    assert digest.title.startswith("perch: morning digest, 1 thing overnight") and "scrutiny" in digest.message
    assert w.critical.sent == []
    for _ in range(144):  # a day, ten minutes at a time: Komodo isn't asked, only meow looks
        w.meowOnly(seconds=600)
    assert sum("morning digest" in t for t in w.ntfy.titles()) == 1  # once: tomorrow has nothing new to say


def test_a_quiet_night_sends_no_digest(w):
    w.wait(60)
    assert w.ntfy.sent == []


def test_quiet_hours_hold_a_tailFlick_for_the_digest_but_never_a_hiss(w):
    w.clock.now = at(23, 30, day=28)
    w.fake.vitals("cellar", disk=88.0)  # a tailFlick, in quiet hours
    w.step(2)
    w.fake.exit("grinder", "n8n", 137)  # a hiss, in quiet hours
    w.step(8)
    assert len(w.ntfy.sent) == 1 and "n8n" in w.ntfy.sent[0].title, w.ntfy.titles()  # the hiss went at once
    assert len(w.critical.sent) == 1
    w.clock.now = at(6, 55)  # still quiet, hours later (the hiss repeats are not under test)
    w.litters.acknowledge(w.litters.open()[0].litterId, "the page", w.clock())
    w.fake.restart("grinder", "n8n")
    sentBefore = len(w.ntfy.sent)
    w.step(20)  # 06:55 to 07:05: quiet ends at 07:00 but the digest is at 07:30
    # quiet hours end at 07:00 but the digest is at 07:30; only the hiss's recovery (it ignores quiet hours) went
    assert [t for t in w.ntfy.titles()[sentBefore:] if " back, was " not in t] == []
    w.wait(30)
    digest = [s for s in w.ntfy.sent if "morning digest" in s.title]
    assert len(digest) == 1 and "disk" in digest[0].message


def test_a_tailFlick_that_clears_in_the_quiet_hours_still_reaches_the_digest(w):
    w.clock.now = at(23, 30, day=28)
    w.fake.vitals("cellar", disk=88.0)
    w.step(8)
    w.fake.vitals("cellar", disk=50.0)
    w.step(8)
    assert w.ntfy.sent == []
    w.clock.now = at(7, 29)
    w.step(4)
    digest = [s for s in w.ntfy.sent if "morning digest" in s.title]
    assert len(digest) == 1 and "(cleared)" in digest[0].message


def test_a_tailFlick_recovery_waits_for_the_morning_but_a_hiss_recovery_does_not(w):
    w.fake.vitals("cellar", disk=88.0)
    w.step(12)  # pushed at 07:05
    assert len(w.ntfy.sent) == 1
    w.clock.now = at(23, 30)
    w.fake.vitals("cellar", disk=50.0)
    w.step(4)
    assert len(w.ntfy.sent) == 1  # quiet hours: the good news waits
    w.clock.now = at(7, 5, day=30)
    w.step(2)
    assert any("cellar back" in t for t in w.ntfy.titles())


def test_recovery_is_announced_exactly_once(w):
    w.fake.exit("grinder", "n8n", 137)
    w.step(4)
    w.fake.restart("grinder", "n8n")
    w.step(10)
    backs = [t for t in w.ntfy.titles() if "back" in t]
    assert len(backs) == 1 and "was hiss for" in backs[0]
    assert len([t for t in w.critical.titles() if "back" in t]) == 1  # the critical copy gets the good news too


def test_a_tailFlick_that_clears_before_the_batch_is_never_pushed_and_says_so_on_the_trail(w):
    w.fake.vitals("cellar", disk=88.0)
    w.step(4)
    w.fake.vitals("cellar", disk=50.0)
    w.step(20)
    assert w.ntfy.sent == []
    assert any("cleared before meow sent anything" in e.title for e in w.trail.events())


# -- rate limit: a storm ------------------------------------------------------------------------------


def stormOf(w, n, level=B.hiss):
    for i in range(n):
        w.trail.setState(f"app:grinder/storm{i}", level, title=f"storm {i} is down", seenAt=w.clock())


def test_GATE_a_50_event_storm_is_at_most_10_pushes_per_channel_and_nothing_is_dropped(w):
    stormOf(w, 50)
    w.meowOnly()
    assert len(w.ntfy.sent) <= 10 and len(w.critical.sent) <= 10
    assert len(w.ntfy.sent) == 10 and len(w.critical.sent) == 10  # 9 hisses and the one summary
    assert "held back" in w.ntfy.sent[-1].title and w.ntfy.sent[-1].title == "perch: 41 alerts held back"
    pushed = {lt.litterId for lt in w.litters.open() if lt.pushes}
    held = {lt.litterId for lt in w.litters.held()}
    assert len(pushed) == 9 and len(held) == 41 and not (pushed & held)  # every litter is one or the other
    assert len(w.litters.open()) == 50
    # ... and for as long as the storm lasts, never more than 10 in any 10 minutes
    for _ in range(30):
        w.meowOnly(seconds=60)
    from perch.scentTrail import parseUtc

    times = {"ntfy": [], "critical": []}
    for row in w.trail.fetch("SELECT at, channel FROM pushes ORDER BY at"):
        times[row["channel"]].append(parseUtc(row["at"]))
    for channel, stamps in times.items():
        for stamp in stamps:
            inWindow = [t for t in stamps if stamp - timedelta(minutes=10) < t <= stamp]
            assert len(inWindow) <= 10, (channel, stamp, len(inWindow))
    # everything eventually gets said: the held ones go out as the limit allows
    for _ in range(90):
        w.meowOnly(seconds=60)
    # (a storm that never ends keeps some 30-minute repeats waiting too; what matters is that every litter,
    # all fifty, was said at least once, and none was ever dropped)
    assert len(w.litters.open()) == 50 and all(lt.pushes >= 1 for lt in w.litters.open())


def test_a_hiss_is_never_held_while_a_lower_level_could_be(w):
    stormOf(w, 20, B.tailFlick)
    w.clock.advance(minutes=6)
    w.trail.setState("app:grinder/the-hiss", B.hiss, title="down", seenAt=w.clock())
    w.meowOnly()
    assert any("the-hiss" in t for t in w.ntfy.titles()), "the hiss must go out"
    assert any("the-hiss" in t for t in w.critical.titles())
    tail = [s for s in w.ntfy.sent if "storm" in s.title or "things need" in s.title]
    assert len(tail) <= 1  # the twenty tailFlicks are one batch, and the rest of the window is the hiss's


def test_held_alerts_get_one_event_each_and_the_summary_has_one(w):
    stormOf(w, 30)
    w.meowOnly()
    held = [e for e in w.trail.events(limit=500) if "held back by the rate limit" in e.title]
    assert len(held) == 21 and all(e.litterId for e in held)
    w.meowOnly()
    w.meowOnly()
    assert len([e for e in w.trail.events(limit=500) if "held back by the rate limit" in e.title]) == 21


# -- the trail shows what meow did and why -----------------------------------------------------------


def test_every_push_is_a_scentTrail_event(w):
    w.fake.nodeDown("grinder")
    w.step(4)
    w.fake.nodeUp("grinder")
    w.step(4)
    texts = [e.title for e in w.trail.events(limit=100) if e.sense == "perch"]
    assert any(t.startswith("meow pushed (hiss) on ntfy and critical") for t in texts)
    assert any(t.startswith("meow announced recovery on ntfy and critical") for t in texts)
    events = [e for e in w.trail.events(limit=100) if e.title.startswith("meow ")]
    assert events and all(e.litterId and e.litterId.startswith("down.grinder@") for e in events)


def test_every_title_starts_with_perch_and_no_secret_is_in_a_push_or_an_event(w):
    w.fake.nodeDown("grinder")
    w.fake.vitals("cellar", disk=88.0)
    w.fake.setHealth("cellar", "scrutiny", "health: starting")
    w.step(20)
    for s in [*w.ntfy.sent, *w.critical.sent]:
        assert s.title.startswith("perch: ")
    blob = repr([(s.title, s.message, s.tags) for s in w.critical.sent]) + repr(
        [(e.title, e.detail, e.logTail) for e in w.trail.events(limit=500)]
    )
    for secret in (NTFY_TOKEN, SECRET, "fake-critical-topic-not-real", "fake-alerts-topic", "example.home.arpa"):
        assert secret not in blob, secret


# -- the acknowledge button on a push ------------------------------------------------------------------


def test_the_button_is_on_the_self_hosted_push_only_and_is_a_signed_post(w):
    w.fake.nodeDown("grinder")
    w.step(4)
    (button,) = w.ntfy.sent[0].actions
    shape = (button["action"], button["label"], button["method"], button["clear"])
    assert shape == ("http", "Acknowledge", "POST", True)
    assert button["url"].startswith(f"{PUBLIC}/ack/t/")
    litter = w.litters.open()[0]
    checked = ack.verify(SECRET, button["url"].rsplit("/", 1)[1], w.clock())
    assert checked is not None and checked.litterId == litter.litterId
    assert w.critical.sent[0].actions == []  # never on the ntfy.sh copy: a third party would see the link


@pytest.mark.parametrize("args", [{"publicUrl": ""}, {"ackSecret": ""}], ids=["no-address", "no-secret"])
def test_no_button_without_an_address_or_a_secret(fleetTree, tmp_path, clock, args):
    w = MeowWorld(fleetTree, tmp_path, clock, **args)
    try:
        w.fake.nodeDown("grinder")
        w.step(4)
        assert w.ntfy.sent, w.litters.open()
        assert w.ntfy.sent[0].actions == []
    finally:
        w.close()


# -- outages and restarts ---------------------------------------------------------------------------


def test_when_ntfy_is_down_the_critical_copy_still_goes_and_the_outage_is_said_once(w):
    w.ntfy.down = True
    w.fake.nodeDown("grinder")
    w.step(6)
    assert len(w.critical.sent) == 1 and w.ntfy.sent == []
    said = [e for e in w.trail.events(limit=100) if "can't reach ntfy" in e.title]
    assert len(said) == 1
    w.ntfy.down = False
    w.wait(31)  # the next repeat reaches ntfy again
    assert len(w.ntfy.sent) == 1
    assert any("reaches ntfy again" in e.title for e in w.trail.events(limit=100))


def test_a_restart_remembers_what_it_pushed(w):
    w.fake.nodeDown("grinder")
    w.step(4)
    assert len(w.ntfy.sent) == 1
    w.meow = w.makeMeow(ackSecret=SECRET, publicUrl=PUBLIC)  # perch restarted
    w.wait(10)
    assert len(w.ntfy.sent) == 1
    w.wait(25)
    assert len(w.ntfy.sent) == 2  # the 30 minute repeat still comes on time


def test_nothing_is_sent_when_no_channel_is_configured(fleetTree, tmp_path, clock):
    w = MeowWorld(fleetTree, tmp_path, clock)
    w.meow = Meow(w.trail, fleetTree, clock=clock, tz=IST)
    try:
        assert not w.meow.configured
        w.fake.nodeDown("grinder")
        w.step(6)
        assert [lt.key for lt in w.litters.open()] == ["down:grinder"] and w.ntfy.sent == []
    finally:
        w.close()


def test_the_litter_id_is_a_single_path_segment(w):
    w.fake.exit("grinder", "n8n", 137)
    w.step(4)
    (lt,) = w.litters.open()
    assert lt.litterId.startswith("app.grinder.n8n@") and "/" not in lt.litterId
    assert w.clock() - lt.openedAt < timedelta(minutes=5)
