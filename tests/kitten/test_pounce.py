"""pounce's tests (M5, ADR 0010): stdlib unittest only, on Python 3.13 and 3.14 (test S8).

The rules run on a fake clock and fake raw facts; the polling path runs against a real temp directory; the
real ``inotifywait`` path runs wherever the package is installed (``scripts/test.ps1`` has a container with
inotify-tools and sets KITTEN_REQUIRE_INOTIFY=1, so there a missing binary is a failure, not a skip).
"""

import ast
import json
import os
import shutil
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path

from test_kitten import FakePerch  # the other test file's fake perch, same directory

from kitten import pounce
from kitten.kitten import Kitten, KittenConfig
from kitten.pounce import (
    DEBOUNCE,
    HOLD_MAX,
    RATE,
    InotifySource,
    PollSource,
    Pounce,
    Pouncer,
    Watch,
    defaultWatches,
    parseInotifyLine,
    parseWatch,
)

POUNCE_SOURCE = Path(pounce.__file__)
NEED_INOTIFY = os.environ.get("KITTEN_REQUIRE_INOTIFY") == "1"


def quietSubject(repo):
    return "", ""


class WatchTest(unittest.TestCase):
    def test_a_watch_has_a_level_a_reason_and_defaults(self):
        w = parseWatch("/etc/purrbrews|tailFlick|settings changed")
        self.assertEqual((w.path, w.level, w.why, w.kind), ("/etc/purrbrews", "tailFlick", "settings changed", "files"))
        plain = parseWatch("/srv/dumps")
        self.assertEqual((plain.level, plain.why), ("earTwitch", "changed"))
        self.assertEqual(parseWatch("/x|hiss|nope").level, "earTwitch")  # a path can't ask for more than tailFlick

    def test_the_defaults_follow_design_4_4_with_c2(self):
        paths = {w.path for w in defaultWatches("cellar", windows=False)}
        self.assertIn("/srv/dumps", paths)
        self.assertIn("/etc/purrbrews", paths)
        self.assertIn("/opt/purrbrews/.git/refs/heads/main", paths)  # C2: not .git/HEAD, which never changes on a pull
        self.assertIn("/opt/purrbrews/.git/packed-refs", paths)
        self.assertFalse(any(p.endswith(".git/HEAD") for p in paths))
        self.assertIn("/srv/data/paperless/consume", {w.path for w in defaultWatches("percolator", windows=False)})
        self.assertNotIn("/srv/dumps", {w.path for w in defaultWatches("grinder", windows=False)})
        level = {w.path: w.level for w in defaultWatches("sieve", windows=False)}
        self.assertEqual(level["/etc/purrbrews"], "tailFlick")

    def test_roastery_watches_its_snapshots_only_never_the_whole_repository(self):
        found = defaultWatches("roastery", windows=True)
        self.assertEqual([w.path for w in found], ["C:\\purrbrews\\restic\\snapshots"])
        self.assertEqual(found[0].level, "earTwitch")

    def test_config_paths_win_and_none_switches_pounce_off(self):
        env = {"KITTEN_NODE": "grinder", "KITTEN_POUNCE_PATHS": "/a|tailFlick|why;/b"}
        self.assertEqual([w.path for w in KittenConfig.fromEnv(env).watches()], ["/a", "/b"])
        self.assertEqual(KittenConfig.fromEnv({**env, "KITTEN_POUNCE_PATHS": "none"}).watches(), ())

    def test_a_ref_is_watched_through_its_directory(self):
        ref = Watch("/opt/purrbrews/.git/refs/heads/main", kind="git")
        self.assertEqual((ref.target, ref.only, ref.repo), ("/opt/purrbrews/.git/refs/heads", "main", "/opt/purrbrews"))


class RulesTest(unittest.TestCase):
    def setUp(self):
        self.watch = Watch("/srv/data/paperless/consume", "earTwitch", "a document dropped")
        self.p = Pouncer([self.watch], wall=lambda: 1_780_000_000.0, subjectOf=quietSubject)

    def test_a_file_being_written_is_one_event_after_two_quiet_seconds(self):
        self.p.feed(self.watch, "created", "invoice.pdf", 0.0)
        self.p.feed(self.watch, "modified", "invoice.pdf", 0.4)
        self.p.feed(self.watch, "modified", "invoice.pdf", 0.9)
        self.assertEqual(self.p.tick(DEBOUNCE - 0.2 + 0.9), [])  # 1.7 s after the last change: not yet
        events = self.p.tick(0.9 + DEBOUNCE + 0.01)
        self.assertEqual(len(events), 1)
        event = events[0]
        self.assertEqual(
            (event["name"], event["change"], event["level"], event["why"], event["path"]),
            ("invoice.pdf", "created", "earTwitch", "a document dropped", self.watch.path),
        )
        self.assertEqual(self.p.tick(60.0), [])  # said once

    def test_a_path_that_never_goes_quiet_is_reported_anyway(self):
        t = 0.0
        while t < HOLD_MAX:
            self.p.feed(self.watch, "modified", "big.log", t)
            t += 1.0
        self.assertEqual(len(self.p.tick(HOLD_MAX)), 1)

    def test_deleted_wins_and_a_replaced_file_is_modified(self):
        self.p.feed(self.watch, "created", "a", 0.0)
        self.p.feed(self.watch, "deleted", "a", 0.1)
        self.p.feed(self.watch, "deleted", "b", 0.0)
        self.p.feed(self.watch, "created", "b", 0.1)
        got = {e["name"]: e["change"] for e in self.p.tick(5.0)}
        self.assertEqual(got, {"a": "deleted", "b": "modified"})

    def test_sixty_events_a_minute_then_one_storm_tailFlick(self):
        for i in range(RATE + 40):
            self.p.feed(self.watch, "created", f"f{i}", i * 0.3)  # 100 files in 30 s
        events = []
        for step in range(0, 400):
            events += self.p.tick(step * 0.1)
        events += self.p.tick(60.0)
        listed = [e for e in events if e["change"] != "storm"]
        storms = [e for e in events if e["change"] == "storm"]
        self.assertEqual(len(listed), RATE)
        self.assertEqual(len(storms), 1)
        self.assertEqual(storms[0]["level"], "tailFlick")
        self.assertEqual(storms[0]["path"], self.watch.path)

    def test_a_quiet_minute_ends_the_storm(self):
        for i in range(RATE + 5):
            self.p.feed(self.watch, "created", f"f{i}", 0.0)
        first = self.p.tick(5.0)
        self.assertEqual(sum(1 for e in first if e["change"] == "storm"), 1)
        self.p.feed(self.watch, "created", "later", 200.0)
        later = self.p.tick(203.0)
        self.assertEqual([(e["name"], e["change"]) for e in later], [("later", "created")])

    def test_each_path_has_its_own_budget(self):
        other = Watch("/etc/purrbrews", "tailFlick", "settings changed")
        p = Pouncer([self.watch, other], wall=lambda: 1.0, subjectOf=quietSubject)
        for i in range(RATE + 5):
            p.feed(self.watch, "created", f"f{i}", 0.0)
        p.feed(other, "modified", "pounce.env", 0.0)
        events = p.tick(5.0)
        mine = [e for e in events if e["path"] == other.path]
        self.assertEqual([(e["change"], e["level"]) for e in mine], [("modified", "tailFlick")])

    def test_git_refs_are_one_event_with_the_commit_subject_and_a_gc_is_not_a_pull(self):
        commits = iter([("aaa", "compose: pin immich"), ("aaa", "compose: pin immich"), ("bbb", "docs: runbook")])
        ref = Watch("/opt/purrbrews/.git/refs/heads/main", "earTwitch", "the node pulled", "git")
        packed = Watch("/opt/purrbrews/.git/packed-refs", "earTwitch", "the node pulled", "git")
        p = Pouncer([ref, packed], wall=lambda: 1.0, subjectOf=lambda repo: next(commits))
        p.feed(ref, "created", "main.lock", 0.0)  # not the ref: ignored
        p.feed(ref, "created", "main", 0.0)
        p.feed(packed, "modified", "packed-refs", 0.2)
        events = p.tick(5.0)
        self.assertEqual(len(events), 1)
        self.assertEqual((events[0]["commit"], events[0]["why"]), ("compose: pin immich", "the node pulled"))
        p.feed(packed, "modified", "packed-refs", 10.0)  # a gc: same commit
        self.assertEqual(p.tick(20.0), [])
        p.feed(ref, "created", "main", 30.0)
        self.assertEqual(p.tick(40.0)[0]["commit"], "docs: runbook")


class InotifyLineTest(unittest.TestCase):
    watch = Watch("/srv/dumps", "earTwitch", "a dump arrived")

    def test_names_and_changes(self):
        found = parseInotifyLine("CREATE|/srv/dumps/sieve/a.sql.gz\n", self.watch)
        self.assertEqual(found, ("created", "sieve/a.sql.gz"))
        self.assertEqual(parseInotifyLine("MOVED_TO|/srv/dumps/a\n", self.watch), ("created", "a"))
        self.assertEqual(parseInotifyLine("CLOSE_WRITE,CLOSE|/srv/dumps/a\n", self.watch), ("modified", "a"))
        self.assertEqual(parseInotifyLine("DELETE|/srv/dumps/a\n", self.watch), ("deleted", "a"))
        self.assertEqual(parseInotifyLine("CREATE,ISDIR|/srv/dumps/new\n", self.watch), ("created", "new/"))

    def test_noise_is_dropped(self):
        self.assertIsNone(parseInotifyLine("ATTRIB|/srv/dumps/a\n", self.watch))
        self.assertIsNone(parseInotifyLine("garbage\n", self.watch))
        self.assertIsNone(parseInotifyLine("CREATE|\n", self.watch))

    def test_a_ref_is_named_by_its_file(self):
        ref = Watch("/opt/purrbrews/.git/refs/heads/main", kind="git")
        self.assertEqual(parseInotifyLine("MOVED_TO|/opt/purrbrews/.git/refs/heads/main\n", ref), ("created", "main"))

    def test_the_command_lists_events_and_never_asks_for_content(self):
        cmd = InotifySource(self.watch).command()
        self.assertEqual(cmd[0], "inotifywait")
        self.assertIn("-r", cmd)
        self.assertEqual(cmd[-1], "/srv/dumps")
        self.assertEqual(cmd[cmd.index("--format") + 1], "%e|%w%f")
        git = InotifySource(Watch("/opt/purrbrews/.git/packed-refs", kind="git")).command()
        self.assertNotIn("-r", git)
        self.assertEqual(git[-1], "/opt/purrbrews/.git")


class FakeProc:
    """What ``subprocess.Popen`` returns, for an inotifywait that printed some lines and ended."""

    def __init__(self, lines, code=0):
        self.stdout = iter(lines)
        self.code = code
        self.terminated = False

    def terminate(self):
        self.terminated = True

    def communicate(self, timeout=None):
        return "", "Couldn't watch /srv/dumps: No such file or directory"

    @property
    def returncode(self):
        return self.code


class InotifySourceTest(unittest.TestCase):
    def test_lines_become_facts_and_a_dead_watch_is_said_once_and_retried(self):
        said, got = [], []
        procs = [FakeProc(["CREATE|/srv/dumps/a\n"], code=1), FakeProc([], code=1), FakeProc([], code=1)]
        stop = threading.Event()

        def spawn(*args, **kwargs):
            if not procs:
                stop.set()
                raise OSError("no more")
            return procs.pop(0)

        source = InotifySource(Watch("/srv/dumps"), spawn=spawn, log=said.append, retry=(0.01, 0.02))
        source.run(lambda w, c, n, t: got.append((c, n)), stop)
        self.assertEqual(got, [("created", "a")])
        self.assertEqual(len([s for s in said if "can't watch" in s]), 1)  # not once per retry
        self.assertIn("No such file", said[0])  # what inotifywait itself said

    def test_a_missing_binary_is_said_once_and_does_not_crash(self):
        said = []
        stop = threading.Event()
        calls = []

        def spawn(*args, **kwargs):
            calls.append(1)
            if len(calls) == 3:
                stop.set()
            raise FileNotFoundError("inotifywait")

        source = InotifySource(Watch("/srv/dumps"), spawn=spawn, log=said.append, retry=(0.01, 0.02))
        source.run(lambda *a: None, stop)
        self.assertEqual(len(said), 1)
        self.assertIn("inotifywait", said[0])


class PollTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)
        self.got = []

    def feed(self, watch, change, name, now):
        self.got.append((change, name))

    def test_the_first_look_is_the_baseline_and_changes_are_names_and_types(self):
        (self.dir / "already.snap").write_text("x")
        source = PollSource(Watch(str(self.dir)))
        source.poll(self.feed, 0.0)
        self.assertEqual(self.got, [])
        (self.dir / "new.snap").write_text("x")
        (self.dir / "sub").mkdir()
        source.poll(self.feed, 10.0)
        self.assertEqual(sorted(self.got), [("created", "new.snap"), ("created", "sub/")])
        self.got.clear()
        later = time.time() + 5
        os.utime(self.dir / "already.snap", (later, later))
        (self.dir / "new.snap").unlink()
        source.poll(self.feed, 20.0)
        self.assertEqual(sorted(self.got), [("deleted", "new.snap"), ("modified", "already.snap")])

    def test_a_folder_that_isnt_there_is_said_once(self):
        said = []
        source = PollSource(Watch(str(self.dir / "missing")), log=said.append)
        for _ in range(3):
            source.poll(self.feed, 0.0)
        self.assertEqual(len(said), 1)
        self.assertEqual(self.got, [])

    def test_a_snapshot_dropped_in_reaches_perch_in_seconds_through_kitten(self):
        perch = FakePerch()
        self.addCleanup(perch.close)
        config = KittenConfig(
            perchUrl=perch.url, token="fake-token-not-real", node="roastery", stateDir="", pouncePaths=("none",)
        )
        kitten = Kitten(config, log=lambda text: None)
        watch = Watch(str(self.dir), "earTwitch", "a new snapshot arrived")
        source = PollSource(watch, every=0.1)
        kitten.pounce = Pounce(Pouncer([watch]), [source], kitten.addEvents, interval=0.1)
        stop = threading.Event()
        runner = threading.Thread(target=kitten.run, args=(stop, 30.0), daemon=True)
        runner.start()  # run() starts kitten.pounce
        self.addCleanup(runner.join, 5)
        self.addCleanup(stop.set)
        self.addCleanup(kitten.pounce.stop)
        time.sleep(0.5)  # the baseline
        started = time.time()
        (self.dir / "5d3c1f9a").write_text("snapshot")
        while time.time() - started < 8 and not any("events" in r[2] for r in perch.requests):
            time.sleep(0.1)
        took = time.time() - started
        sent = [r[2] for r in perch.requests if "events" in r[2]]
        self.assertTrue(sent, "no event reached perch")
        self.assertLess(took, 5.0)
        event = sent[0]["events"][0]
        self.assertEqual((event["name"], event["change"], event["level"]), ("5d3c1f9a", "created", "earTwitch"))
        self.assertEqual(sent[0]["node"], "roastery")


class NeverReadsTest(unittest.TestCase):
    """The rule: kitten never opens, reads or hashes a file it watches (above all under /etc/purrbrews)."""

    CANARY = "THIS-MUST-NEVER-BE-READ"

    def test_no_open_of_a_watched_file_while_pounce_sees_it_change(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "purrbrews"
            root.mkdir()
            (root / "settings.env").write_text(self.CANARY)
            opened = []

            def hook(event, args):
                if event == "open" and args and str(root) in str(args[0]):
                    opened.append(str(args[0]))

            sys.addaudithook(hook)
            watch = Watch(str(root), "tailFlick", "settings changed")
            p = Pouncer([watch], subjectOf=quietSubject)
            source = PollSource(watch)
            source.poll(p.feed, 0.0)
            (root / "settings.env").write_text(self.CANARY + "-changed")  # the test itself opens; not counted
            del opened[:]
            later = time.time() + 5
            os.utime(root / "settings.env", (later, later))
            (root / "secret.key").write_text("x")
            del opened[:]
            source.poll(p.feed, 10.0)
            events = p.tick(20.0)
            self.assertEqual(sorted(e["name"] for e in events), ["secret.key", "settings.env"])
            self.assertEqual(opened, [], "pounce opened a watched file")
            self.assertNotIn(self.CANARY, json.dumps(events))

    def test_the_pounce_module_has_no_call_that_reads_content(self):
        tree = ast.parse(POUNCE_SOURCE.read_text(encoding="utf-8"))
        forbidden = {"open", "read", "read_text", "read_bytes", "readline", "readlines"}
        forbidden |= {"sha1", "sha256", "md5", "file_digest"}
        calls = []
        for node in ast.walk(tree):
            if isinstance(node, ast.Call):
                name = node.func.id if isinstance(node.func, ast.Name) else getattr(node.func, "attr", "")
                if name in forbidden:
                    calls.append((name, node.lineno))
        self.assertEqual(calls, [])
        imported = {a.name for n in ast.walk(tree) if isinstance(n, ast.Import) for a in n.names}
        self.assertFalse(imported & {"hashlib", "mmap", "shutil", "tempfile", "io"})

    def test_the_commit_subject_comes_from_git_never_from_the_ref_file(self):
        source = POUNCE_SOURCE.read_text(encoding="utf-8")
        self.assertIn('"git"', source)
        self.assertIn("subprocess.run", source)


@unittest.skipUnless(shutil.which("inotifywait") or NEED_INOTIFY, "inotify-tools isn't installed here")
class RealInotifyTest(unittest.TestCase):
    """The real inotifywait, in a container that has inotify-tools (scripts/test.ps1)."""

    def setUp(self):
        self.assertTrue(shutil.which("inotifywait"), "KITTEN_REQUIRE_INOTIFY=1 but inotifywait is missing")
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.dir = Path(self.tmp.name)

    def watching(self, watch, perch=None):
        got = []
        stop = threading.Event()
        source = InotifySource(watch, retry=(0.2, 0.5))
        thread = threading.Thread(target=source.run, args=(lambda w, c, n, t: got.append((c, n)), stop), daemon=True)
        thread.start()
        self.addCleanup(thread.join, 5)
        self.addCleanup(stop.set)
        self.addCleanup(source.close)
        time.sleep(1.0)  # inotifywait needs a moment to set its watches
        return got

    def waitFor(self, got, want, seconds=5):
        end = time.time() + seconds
        while time.time() < end and want not in got:
            time.sleep(0.1)
        return want in got

    def test_a_dropped_file_and_a_new_directory_are_seen_by_name(self):
        got = self.watching(Watch(str(self.dir)))
        (self.dir / "invoice.pdf").write_text("x")
        (self.dir / "sub").mkdir()
        self.assertTrue(self.waitFor(got, ("created", "invoice.pdf")), got)
        self.assertTrue(self.waitFor(got, ("created", "sub/")), got)

    def test_a_ref_replaced_by_rename_is_still_seen(self):
        refs = self.dir / ".git" / "refs" / "heads"
        refs.mkdir(parents=True)
        (refs / "main").write_text("0" * 40)
        got = self.watching(Watch(str(refs / "main"), kind="git"))
        (refs / "main.lock").write_text("1" * 40)
        os.replace(refs / "main.lock", refs / "main")  # how git updates a ref
        self.assertTrue(self.waitFor(got, ("created", "main")), got)

    def test_the_whole_way_a_drop_reaches_perch_within_5_seconds(self):
        perch = FakePerch()
        self.addCleanup(perch.close)
        watch = Watch(str(self.dir), "earTwitch", "a document dropped")
        config = KittenConfig(perchUrl=perch.url, token="fake-token-not-real", node="percolator", pouncePaths=("none",))
        kitten = Kitten(config, log=lambda text: None)
        kitten.pounce = Pounce(Pouncer([watch]), [InotifySource(watch)], kitten.addEvents)
        stop = threading.Event()
        runner = threading.Thread(target=kitten.run, args=(stop, 30.0), daemon=True)
        runner.start()  # run() starts kitten.pounce
        self.addCleanup(runner.join, 5)
        self.addCleanup(stop.set)
        self.addCleanup(kitten.pounce.stop)
        time.sleep(1.0)
        started = time.time()
        (self.dir / "scan-001.pdf").write_text("x")
        while time.time() - started < 8 and not any("events" in r[2] for r in perch.requests):
            time.sleep(0.1)
        sent = [r[2] for r in perch.requests if "events" in r[2]]
        self.assertTrue(sent, "no event reached perch")
        self.assertLess(time.time() - started, 5.0)
        self.assertEqual(sent[0]["events"][0]["name"], "scan-001.pdf")


class KittenEventsTest(unittest.TestCase):
    def setUp(self):
        self.perch = FakePerch()
        self.addCleanup(self.perch.close)
        self.logged = []
        config = KittenConfig(perchUrl=self.perch.url, token="fake-token-not-real", node="grinder", stateDir="")
        self.kitten = Kitten(config, log=self.logged.append)

    def event(self, name):
        return {"id": name, "at": "2026-10-03T10:00:00Z", "path": "/x", "name": name, "change": "created",
                "level": "earTwitch", "why": "w"}  # fmt: skip

    def test_events_are_sent_until_perch_accepts_them_and_never_again(self):
        self.kitten.addEvents([self.event("a")])
        self.perch.status, self.perch.body = 500, {"error": "boom"}
        self.assertFalse(self.kitten.cycle())
        self.perch.status, self.perch.body = 200, None
        self.assertTrue(self.kitten.cycle())
        self.assertEqual([e["id"] for e in self.perch.requests[-1][2]["events"]], ["a"])
        self.kitten.cycle()
        self.assertNotIn("events", self.perch.requests[-1][2])

    def test_events_perch_cannot_read_are_dropped_and_the_heartbeat_goes_on(self):
        self.kitten.addEvents([self.event("a")])
        self.perch.status, self.perch.body = 422, {"error": "event 0: bad"}
        self.kitten.cycle()
        self.perch.status, self.perch.body = 200, None
        self.assertTrue(self.kitten.cycle())
        self.assertNotIn("events", self.perch.requests[-1][2])
        self.assertTrue(any("refused 0 record(s) and 1 event(s)" in line for line in self.logged))

    def test_the_backlog_is_capped_oldest_first(self):
        self.kitten.addEvents([self.event(f"e{i}") for i in range(700)])
        taken = self.kitten._takeEvents()
        self.assertEqual(len(taken), 100)
        self.assertEqual(taken[0]["id"], "e200")


if __name__ == "__main__":
    unittest.main()
