"""kitten's tests: stdlib unittest only, run on Python 3.13 and 3.14 (test S8).

python -m unittest discover -s tests/kitten
"""

import ast
import json
import os
import subprocess
import sys
import tempfile
import threading
import time
import unittest
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

from kitten.build import build
from kitten.kitten import Kitten, KittenConfig, postJson

KITTEN_DIR = Path(__file__).resolve().parents[2] / "kitten"


class ConfigTest(unittest.TestCase):
    def test_reads_settings(self):
        cfg = KittenConfig.fromEnv(
            {
                "KITTEN_PERCH_URL": "https://perch.example.home.arpa/api/kitten",
                "KITTEN_TOKEN": "fake-token-not-real",
                "KITTEN_POUNCE_PATHS": r"C:\purrbrews\restic\snapshots; /srv/dumps ;",
                "KITTEN_NODE": "roastery",
            }
        )
        self.assertEqual(cfg.pouncePaths, (r"C:\purrbrews\restic\snapshots", "/srv/dumps"))
        self.assertEqual(cfg.node, "roastery")
        self.assertEqual(cfg.problems(), [])

    def test_token_never_in_repr(self):
        cfg = KittenConfig.fromEnv({"KITTEN_TOKEN": "fake-token-not-real"})
        self.assertNotIn("fake-token-not-real", repr(cfg))
        self.assertNotIn("fake-token-not-real", str(cfg))

    def test_problems_when_unset(self):
        problems = KittenConfig.fromEnv({"KITTEN_PERCH_URL": "http://perch"}).problems()
        self.assertEqual(len(problems), 2)


class FakePerch:
    """A real socket speaking just enough of perch's /api/kitten: it records what it was sent."""

    def __init__(self, status=200, body=None):
        self.requests = []
        self.status, self.body = status, body
        outer = self

        class Handler(BaseHTTPRequestHandler):
            def do_POST(self):
                raw = self.rfile.read(int(self.headers.get("Content-Length", 0)))
                outer.requests.append((self.path, dict(self.headers), json.loads(raw)))
                payload = json.dumps(outer.body if outer.body is not None else {"ok": True}).encode()
                self.send_response(outer.status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

            def log_message(self, *args):
                pass

        self.server = HTTPServer(("127.0.0.1", 0), Handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/api/kitten"
        threading.Thread(target=self.server.serve_forever, daemon=True).start()

    def close(self):
        self.server.shutdown()
        self.server.server_close()


class KittenTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.groom = Path(self.tmp.name) / "groom"
        self.state = Path(self.tmp.name) / "state"
        (self.groom / "nightly").mkdir(parents=True)
        self.state.mkdir()
        self.logged = []
        self.perch = FakePerch()
        self.addCleanup(self.perch.close)

    def kitten(self, perch=None):
        config = KittenConfig(
            perchUrl=(perch or self.perch).url,
            token="fake-token-not-real",
            groomDir=str(self.groom),
            stateDir=str(self.state),
            node="grinder",
        )
        return Kitten(config, log=self.logged.append)

    def record(self, name="20260929T013012Z", **more):
        data = {
            "schema": 1,
            "job": "nightly",
            "node": "grinder",
            "start": "2026-09-29T01:30:12Z",
            "result": "success",
            **more,
        }
        path = self.groom / "nightly" / f"{name}.json"
        path.write_text(json.dumps(data), encoding="utf-8")
        return path

    def test_a_report_carries_the_bearer_token_a_heartbeat_and_the_records(self):
        self.record()
        (self.state / "drive-sync.ok").write_text("")
        (self.state / "notes.txt").write_text("not a stamp")
        self.assertTrue(self.kitten().cycle())
        path, headers, body = self.perch.requests[0]
        self.assertEqual(path, "/api/kitten")
        self.assertEqual(headers["Authorization"], "Bearer fake-token-not-real")
        self.assertEqual(body["node"], "grinder")
        self.assertEqual(body["heartbeat"]["version"], "0.2.0")
        self.assertEqual(list(body["heartbeat"]["stamps"]), ["drive-sync.ok"])
        self.assertEqual([r["job"] for r in body["records"]], ["nightly"])

    def test_a_record_is_sent_until_perch_accepts_it_and_never_again(self):
        self.record()
        kitten = self.kitten()
        kitten.cycle()
        kitten.cycle()
        self.assertEqual(len(self.perch.requests[0][2]["records"]), 1)
        self.assertNotIn("records", self.perch.requests[1][2])  # a heartbeat alone
        self.record("20260930T013000Z", start="2026-09-30T01:30:00Z")
        kitten.cycle()
        self.assertEqual(len(self.perch.requests[2][2]["records"]), 1)

    def test_a_record_stays_pending_while_perch_is_refusing_us(self):
        self.record()
        self.perch.status, self.perch.body = 500, {"error": "boom"}
        kitten = self.kitten()
        self.assertFalse(kitten.cycle())
        self.perch.status, self.perch.body = 200, None
        self.assertTrue(kitten.cycle())
        self.assertEqual(len(self.perch.requests[-1][2]["records"]), 1)  # sent again, now accepted

    def test_an_outage_is_said_once_not_every_minute(self):
        kitten = self.kitten()
        self.perch.status, self.perch.body = 401, {"error": "a bearer token is required"}
        for _ in range(4):
            self.assertFalse(kitten.cycle())
        self.assertEqual(len(self.logged), 1)
        self.assertNotIn("fake-token-not-real", " ".join(self.logged))

    def test_a_batch_perch_cannot_read_is_set_aside_and_the_heartbeat_goes_on(self):
        self.record()
        self.perch.status, self.perch.body = 422, {"error": "record 0: unknown job"}
        kitten = self.kitten()
        kitten.cycle()
        self.assertTrue(any("refused 1 record" in line for line in self.logged))
        self.perch.status, self.perch.body = 200, None
        self.assertTrue(kitten.cycle())
        self.assertNotIn("records", self.perch.requests[-1][2])  # not retried for ever

    def test_an_unreachable_perch_is_a_false_not_a_crash(self):
        dead = FakePerch()
        dead.close()
        self.assertFalse(self.kitten(perch=dead).cycle())
        self.assertTrue(self.logged and "unreachable" in self.logged[0])

    def test_old_and_unreadable_records_are_skipped(self):
        old = self.record("20260101T013000Z", start="2026-01-01T01:30:00Z")
        past = time.time() - 4 * 86400
        os.utime(old, (past, past))
        (self.groom / "nightly" / "half-written.json").write_text("{not json")
        (self.groom / "nightly" / "list.json").write_text("[]")
        self.assertEqual(self.kitten().records(), [])

    def test_no_groom_directory_is_a_heartbeat_only_node_like_roastery(self):
        config = KittenConfig(
            perchUrl=self.perch.url,
            token="t",
            groomDir=str(Path(self.tmp.name) / "none"),
            stateDir="",
            node="roastery",
        )
        self.assertTrue(Kitten(config, log=self.logged.append).cycle())
        body = self.perch.requests[0][2]
        self.assertEqual((body["node"], body["heartbeat"]["stamps"]), ("roastery", {}))
        self.assertNotIn("records", body)

    def test_postjson_returns_refusals_as_results(self):
        self.perch.status, self.perch.body = 403, {"ok": False, "error": "another node"}
        self.assertEqual(postJson(self.perch.url, "t", {}), (403, {"ok": False, "error": "another node"}))


class ZipappTest(unittest.TestCase):
    """kitten ships as one file that runs on the node's own Python, installing nothing."""

    def test_the_zipapp_builds_and_runs(self):
        with tempfile.TemporaryDirectory() as tmp:
            target = build(Path(tmp) / "kitten.pyz")
            run = subprocess.run(
                [sys.executable, str(target), "--version"], capture_output=True, text=True, timeout=60, check=False
            )
            self.assertEqual((run.returncode, run.stdout.strip()), (0, "kitten 0.2.0"), run.stderr)
            env = {k: v for k, v in os.environ.items() if not k.startswith("KITTEN_")}
            env["KITTEN_TOKEN"] = "fake-token-not-real"
            bad = subprocess.run(
                [sys.executable, str(target), "--once"],
                capture_output=True,
                text=True,
                timeout=60,
                env=env,
                check=False,
            )
            self.assertEqual(bad.returncode, 2)
            self.assertIn("https://", bad.stderr)
            self.assertNotIn("fake-token-not-real", bad.stderr + bad.stdout)


class StdlibOnlyTest(unittest.TestCase):
    """kitten ships as a zipapp: it may import nothing outside the standard library."""

    def test_imports_are_stdlib(self):
        allowed = set(sys.stdlib_module_names) | {"kitten", "__future__"}
        for source in KITTEN_DIR.glob("*.py"):
            tree = ast.parse(source.read_text(encoding="utf-8"))
            for node in ast.walk(tree):
                if isinstance(node, ast.Import):
                    names = [alias.name for alias in node.names]
                elif isinstance(node, ast.ImportFrom) and node.level == 0:
                    names = [node.module or ""]
                else:
                    continue
                for name in names:
                    self.assertIn(name.split(".")[0], allowed, f"{source.name} imports {name}")


if __name__ == "__main__":
    unittest.main()
