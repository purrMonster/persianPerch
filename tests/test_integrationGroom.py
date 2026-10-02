"""integration/groom: the recorder and the unit drop-ins the owner will apply to the fleet (05 plan A8),
checked against the pinned fleet repo and, end to end, against kitten and perch. Nothing here touches a node."""

import json
import os
import stat
import subprocess
import sys
from datetime import UTC, datetime
from pathlib import Path

import pytest
from conftest import FakeClock
from fastapi.testclient import TestClient

from kitten.kitten import Kitten, KittenConfig
from perch.bodyLanguage import BodyLanguage as B
from perch.scentTrail import ScentTrail
from perch.senses.groom import expectedJobs, parseRecord
from perch.settings import Settings
from perch.windowsill.app import createApp

ROOT = Path(__file__).resolve().parents[1]
RECORDER = ROOT / "integration" / "groom" / "groom-record.py"
UNITS = ROOT / "integration" / "groom" / "units"
# the unit each job's timer starts, in the pinned fleet repo
SERVICE_OF = {
    "wake": "purrbrews-wake-roastery.service",
    "store": "purrbrews-backup-store.service",
    "drive": "drive-sync.service",
    "check": "purrbrews-backup-check.service",
    "prune": "restic-prune.service",
    "verify": "purrbrews-backup-verify.service",
    "nightly": "purrbrews-backup@.service",
}


def record(tmp_path, job="nightly", node="grinder", unit="purrbrews-backup@grinder.service", **env):
    """Run the recorder as systemd would, minus systemd: its environment is given, not discovered."""
    full = {
        **{k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT")},
        "GROOM_DIR": str(tmp_path / "groom"),
        "GROOM_START": str(int(datetime(2026, 9, 28, 20, 0, 12, tzinfo=UTC).timestamp())),
        **env,
    }
    return subprocess.run(
        [sys.executable, str(RECORDER), job, node, unit], capture_output=True, text=True, env=full, check=False
    )


# -- the recorder ---------------------------------------------------------------------------


def test_a_failed_job_leaves_a_record_perch_can_parse(tmp_path):
    r = record(tmp_path, SERVICE_RESULT="exit-code", EXIT_CODE="exited", EXIT_STATUS="1")
    assert r.returncode == 0, r.stderr
    path = tmp_path / "groom" / "nightly" / "20260928T200012Z.json"
    run = parseRecord(json.loads(path.read_text()))
    assert (run.node, run.job, run.result, run.exitStatus) == ("grinder", "nightly", "exit-code", "1")
    assert run.unit == "purrbrews-backup@grinder.service"
    assert run.start == datetime(2026, 9, 28, 20, 0, 12, tzinfo=UTC) and run.end >= run.start


def test_a_good_job_says_success(tmp_path):
    record(tmp_path, SERVICE_RESULT="success", EXIT_CODE="exited", EXIT_STATUS="0")
    (path,) = (tmp_path / "groom" / "nightly").glob("*.json")
    assert json.loads(path.read_text())["result"] == "success"


def test_the_modes_are_what_an_unprivileged_kitten_needs(tmp_path):
    record(tmp_path, SERVICE_RESULT="success")
    root, folder = tmp_path / "groom", tmp_path / "groom" / "nightly"
    (file,) = folder.glob("*.json")
    assert stat.S_IMODE(root.stat().st_mode) == 0o755 and stat.S_IMODE(folder.stat().st_mode) == 0o755
    assert stat.S_IMODE(file.stat().st_mode) == 0o644
    assert not list(folder.glob(".*.tmp"))  # the temporary file was renamed away: kitten never sees half a record


def test_it_never_fails_the_job_it_records(tmp_path):
    blocked = tmp_path / "a-file"
    blocked.write_text("not a directory")
    r = record(tmp_path, GROOM_DIR=str(blocked / "groom"), SERVICE_RESULT="success")
    assert r.returncode == 0 and "could not write" in r.stderr
    wrong = subprocess.run([sys.executable, str(RECORDER), "backup", "x"], capture_output=True, text=True, check=False)
    assert wrong.returncode == 0 and "usage" in wrong.stderr


def test_without_systemd_it_still_writes_with_now_as_the_start(tmp_path):
    full = {k: v for k, v in os.environ.items() if k in ("PATH", "SYSTEMROOT")}
    full |= {"GROOM_DIR": str(tmp_path / "groom"), "SERVICE_RESULT": "success"}
    r = subprocess.run(
        [sys.executable, str(RECORDER), "check", "cellar", "x.service"], capture_output=True, env=full, check=False
    )
    assert r.returncode == 0 and len(list((tmp_path / "groom" / "check").glob("*.json"))) == 1


# -- the drop-ins, against the repo ------------------------------------------------------------


def test_every_job_the_repo_schedules_has_a_drop_in_for_its_unit(fleetTree):
    fleet = fleetTree.fleet()
    for job in expectedJobs(fleetTree, fleet):
        unit = SERVICE_OF[job.name]
        assert any(f.endswith("/" + unit) for f in fleet.files), f"{unit} is not in the pinned repo"
        conf = (UNITS / f"{unit}.d" / "groom.conf").read_text(encoding="utf-8")
        node = "%i" if job.name == "nightly" else job.node
        assert f"groom-record.py {job.name} {node} %n" in conf, job.key


def test_the_drop_ins_never_let_the_recorder_fail_the_job():
    confs = sorted(UNITS.glob("*.d/groom.conf"))
    assert len(confs) == 7
    for conf in confs:
        lines = [ln for ln in conf.read_text(encoding="utf-8").splitlines() if ln.startswith("ExecStopPost")]
        assert len(lines) == 1 and lines[0].startswith("ExecStopPost=-/usr/bin/python3 /opt/purrbrews/stacks/_lib/")


def test_nothing_in_integration_groom_names_a_real_domain_or_a_secret():
    for path in (ROOT / "integration" / "groom").rglob("*"):
        if path.is_file():
            text = path.read_text(encoding="utf-8")
            assert "password" not in text.lower() and "token=" not in text.lower(), path


# -- the whole chain: recorder -> file -> kitten -> perch -> the page ------------------------


def test_a_record_written_by_the_recorder_travels_through_kitten_to_the_grid(fleetRepo, fleetTree, tmp_path):
    token = "fake-token-grinder-not-real"
    clock = FakeClock(datetime(2026, 9, 28, 12, 30, tzinfo=UTC))  # 18:00 IST the evening before
    trail = ScentTrail(tmp_path / "t.db", clock=clock)
    app = createApp(
        Settings(repoDir=fleetRepo, trailDb=tmp_path / "t.db", kittenTokens={"grinder": token}),
        trail=trail,
        tree=fleetTree,
        clock=clock,
        collectors=[],
    )
    with TestClient(app) as perch:
        app.state.groom.step()
        # grinder's nightly fails at 01:30, the recorder runs as systemd's ExecStopPost=
        record(tmp_path, SERVICE_RESULT="exit-code", EXIT_STATUS="2")
        clock.now = datetime(2026, 9, 28, 20, 5, tzinfo=UTC)

        def post(url, tok, body):
            r = perch.post("/api/kitten", json=body, headers={"Authorization": f"Bearer {tok}"})
            return r.status_code, r.json()

        kitten = Kitten(
            KittenConfig(
                perchUrl="https://perch.example.home.arpa/api/kitten",
                token=token,
                groomDir=str(tmp_path / "groom"),
                stateDir="",
                node="grinder",
            ),
            post=post,
            clock=lambda: clock.now.timestamp(),  # noqa: PLW0108 - clock.now is reassigned
            log=lambda text: None,
        )
        (written,) = (tmp_path / "groom" / "nightly").glob("*.json")
        os.utime(written, (clock.now.timestamp(), clock.now.timestamp()))
        assert kitten.cycle() is True
        state = trail.states()["groom:grinder/nightly"]
        assert state.bodyLanguage is B.hiss and "failed (exit-code, exit 2)" in state.title
        assert trail.states()["kitten:grinder"].bodyLanguage is B.slowBlink
        html = perch.get("/groom?cell=grinder/nightly@2026-09-29").text
        assert "failed (exit-code, exit 2)" in html
    trail.close()


@pytest.mark.skipif(sys.platform == "win32", reason="the recorder is for Linux nodes")
def test_the_recorder_is_executable_python_with_a_shebang():
    assert RECORDER.read_text(encoding="utf-8").startswith("#!/usr/bin/env python3")
