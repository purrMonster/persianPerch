"""disks (05 plan M4, C6): Scrutiny's drives, read with a fixture shaped from Scrutiny v0.9.3. SMART attribute 9
beats the summary's power-on hours. The real Scrutiny is never contacted."""

import asyncio

import pytest
from outsideFakes import ScrutinyFake

from perch.bodyLanguage import BodyLanguage as B
from perch.collectors import Runner
from perch.rollup import Status
from perch.scentTrail import ScentTrail
from perch.senses.disks import Disks
from perch.senses.scrutiny import ScrutinyError

FAILED_SMART, FAILED_SCRUTINY = 1, 2
WARN, FAIL_THRESHOLD = 2, 4


class Rig:
    def __init__(self, tmp_path, clock):
        self.clock = clock
        self.fake = ScrutinyFake(clock)
        self.trail = ScentTrail(tmp_path / "d.db", clock=clock)
        self.disks = Disks(self.fake.client(), self.trail, clock=clock)
        self.loop = asyncio.new_event_loop()

    def cycle(self, n=1, minutes=15):
        error = None
        for _ in range(n):
            error = None
            try:
                self.loop.run_until_complete(self.disks.cycle())
            except ScrutinyError as exc:
                error = exc
            self.clock.advance(minutes=minutes)
        return error

    def state(self, subject):
        return self.trail.states()[subject]

    def close(self):
        self.loop.run_until_complete(self.disks.aclose())
        self.loop.close()
        self.trail.close()


@pytest.fixture
def rig(tmp_path, clock):
    r = Rig(tmp_path, clock)
    yield r
    r.close()


def test_a_healthy_drive_is_slowBlink_with_what_a_person_wants_to_know(rig):
    rig.fake.add("0x5000cca000000001", "sda", "cellar", "WDC WD40EFRX", temp=36, attrs={"9": rig.fake.attr(9, 17520)})
    rig.cycle()
    st = rig.state("disk:cellar/sda")
    assert st.bodyLanguage is B.slowBlink
    assert st.title == "36 C, 4.0 TB, 730 d powered on".join(["healthy, ", ""])
    assert st.detail["model"] == "WDC WD40EFRX" and st.detail["host"] == "cellar"


def test_GATE_smart_attribute_9_wins_when_the_summary_disagrees(rig):
    # the summary says 3 hours (the fleet has a disk like this); the drive's own attribute 9 says 20000
    attrs = {"9": rig.fake.attr(9, 20000)}
    rig.fake.add("0x5001b44000000002", "sdb", "cellar", "SanDisk SSD", summaryHours=3, attrs=attrs)
    rig.cycle()
    st = rig.state("disk:cellar/sdb")
    assert st.detail["powerOnHours"] == 20000 and st.detail["summaryHours"] == 3
    assert st.detail["hoursSource"] == "SMART attribute 9"
    assert "833 d powered on" in st.title and "3 h" not in st.title


def test_the_summary_is_used_only_when_the_details_have_no_attribute_9(rig):
    rig.fake.add("0x5001b44000000003", "sdc", "cellar", "Disk", summaryHours=500, attrs={})
    rig.fake.add("0x5001b44000000004", "sdd", "cellar", "Disk 2", summaryHours=800, noDetails=True)
    rig.cycle()
    a, b = rig.state("disk:cellar/sdc"), rig.state("disk:cellar/sdd")
    assert (a.detail["powerOnHours"], a.detail["hoursSource"]) == (500, "Scrutiny summary")
    assert (b.detail["powerOnHours"], b.detail["hoursSource"]) == (800, "Scrutiny summary")
    assert "500 h powered on" in a.title


def test_nvme_keeps_its_hours_in_the_power_on_hours_attribute(rig):
    rig.fake.add(
        "0x5002538000000005", "nvme0n1", "grinder", "Samsung 990", protocol="NVMe", summaryHours=1,
        attrs={"power_on_hours": {"attribute_id": "power_on_hours", "value": 4321, "thresh": -1, "status": 0}},
    )  # fmt: skip
    rig.cycle()
    assert rig.state("disk:grinder/nvme0n1").detail["powerOnHours"] == 4321


def test_scrutiny_failed_is_hiss_and_names_why_with_an_event(rig):
    rig.fake.add(
        "0x5000cca000000006", "sde", "cellar", "Old Disk", status=FAILED_SMART | FAILED_SCRUTINY,
        attrs={"5": rig.fake.attr(5, 120, status=FAIL_THRESHOLD)},
    )  # fmt: skip
    rig.cycle()
    st = rig.state("disk:cellar/sde")
    assert st.bodyLanguage is B.hiss
    assert st.title == "SMART reports the drive failing; Scrutiny's thresholds failed (Reallocated Sectors Count)"
    (event,) = rig.trail.events(senses=["purr"])
    assert event.bodyLanguage is B.hiss and event.title.startswith("Old Disk (sde on cellar): SMART reports")


def test_scrutiny_warn_is_tailFlick_and_a_clean_run_later_says_it_is_back(rig):
    d = rig.fake.add("0x5000cca000000007", "sdf", "cellar", "Warm Disk", attrs={"5": rig.fake.attr(5, 8, status=WARN)})
    rig.cycle()
    st = rig.state("disk:cellar/sdf")
    assert st.bodyLanguage is B.tailFlick and st.title == "Scrutiny warns about Reallocated Sectors Count"
    d.attrs = {}
    rig.cycle()
    assert rig.state("disk:cellar/sdf").bodyLanguage is B.slowBlink
    assert rig.trail.events(senses=["purr"])[0].title.startswith("Warm Disk (sdf on cellar) is back (was tailFlick")


def test_a_drive_nobody_has_heard_from_for_three_days_is_tailFlick(rig):
    d = rig.fake.add("0x5000cca000000008", "sdg", "cellar", "Quiet Disk")
    rig.cycle()
    assert rig.state("disk:cellar/sdg").bodyLanguage is B.slowBlink
    rig.clock.advance(days=3, hours=1)
    rig.cycle()
    assert d.collected < rig.clock()
    st = rig.state("disk:cellar/sdg")
    assert st.bodyLanguage is B.tailFlick and st.title.startswith("no SMART report for 3 d")


def test_archived_drives_are_not_watched_and_a_removed_one_is_forgotten(rig):
    rig.fake.add("0x5000cca000000009", "sdh", "cellar", "Gone Disk")
    rig.fake.add("0x5000cca00000000a", "sdi", "cellar", "Shelved", archived=True)
    rig.cycle()
    assert "disk:cellar/sdh" in rig.trail.states() and "disk:cellar/sdi" not in rig.trail.states()
    del rig.fake.drives["0x5000cca000000009"]
    rig.cycle()
    assert not [s for s in rig.trail.states() if s.startswith("disk:")]


def test_scrutiny_unreachable_turns_drives_unknown_after_two_cycles_with_no_events(rig):
    rig.fake.add("0x5000cca00000000b", "sdj", "cellar", "Disk")
    rig.cycle()
    rig.fake.down = True
    error = rig.cycle()
    assert error and "can't see Scrutiny" in str(error)
    assert rig.state("disk:cellar/sdj").bodyLanguage is B.slowBlink  # one failed look is only a look
    rig.cycle()
    assert rig.state("disk:cellar/sdj").bodyLanguage is B.unknown
    assert rig.trail.events() == []
    runner = Runner(rig.trail, [rig.disks], clock=rig.clock, pause=lambda c: 0.01)
    for _ in range(5):  # 3 missed 15-minute cycles make it late
        rig.loop.run_until_complete(runner.runOnce(rig.disks))
        rig.clock.advance(minutes=15)
    assert rig.trail.states()["collector:disks"].bodyLanguage is B.tailFlick


def test_a_drive_counts_toward_its_node_when_the_host_is_a_node_and_toward_the_fleet_otherwise(rig, fleetTree):
    # Scrutiny spelled the host differently from the fleet's node name
    rig.fake.add("0x5000cca00000000c", "sdk", "Cellar", "Bad Disk", status=FAILED_SMART)
    rig.fake.add("0x5000cca00000000d", "sdl", "attic", "Odd Disk", status=FAILED_SMART)
    rig.cycle()
    status = Status(fleetTree.fleet(), rig.trail)
    assert [s.subject for s in status.disks("cellar")] == ["disk:Cellar/sdk"]
    assert status.node("cellar") is B.hiss
    assert [s.subject for s in status.looseDisks()] == ["disk:attic/sdl"]
    assert status.fleetLevel() is B.hiss
    labels = {a.subject: a.label for a in status.attention()}
    assert labels["disk:Cellar/sdk"] == "sdk Bad Disk" and labels["disk:attic/sdl"] == "sdl Odd Disk"
    note = status.nodeNote("cellar")
    assert note and note[0] is B.hiss and "Bad Disk" in note[1]


def test_disks_only_ever_send_the_two_gets(rig):
    rig.fake.add("0x5000cca00000000e", "sdm", "cellar", "Disk")
    rig.cycle(2)
    seen = {(r.method, "details" if "details" in r.url.path else r.url.path) for r in rig.fake.requests}
    assert seen == {("GET", "/api/summary"), ("GET", "details")}


def test_the_client_needs_its_url():
    from perch.senses.scrutiny import ScrutinyClient

    with pytest.raises(ValueError, match="PERCH_DISKS_URL"):
        ScrutinyClient("")
