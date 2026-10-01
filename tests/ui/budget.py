"""Budget and real-socket drill (05 plan 4 step 9): perch with purr really running, over HTTP.

Starts a small HTTP server that speaks Komodo's /read API (the fake from tests/komodoFake.py),
runs `python -m perch` pointed at it with a short rhythm, loads the pages, stops n8n in the fake
and waits for the overview to hiss, restores it and waits for slowBlink. Then prints perch's own
memory (VmRSS and its peak, from /proc) against the 300 MB budget of design plan 2.1.

This is the M1 gate's drill with a real socket and a real clock instead of a fake one. Run in the
perch image (see the runbook, M1 entry); exits non-zero if a drill step or the budget fails.
"""

import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.request
from datetime import UTC, datetime

import httpx2
from komodoFake import KEY, SECRET, FleetFake

from perch.catTree import CatTree

BUDGET_MB = 300
PORT, PERCH_PORT = 9120, 8080
REPO = os.environ.get("PERCH_REPO_DIR", "/fleet")


class Clock:
    def __call__(self):
        return datetime.now(UTC)


fake = FleetFake(CatTree(REPO).fleet(), Clock())
lock = threading.Lock()
seen = {"requests": 0, "badAuth": 0}


class Komodo(http.server.BaseHTTPRequestHandler):
    def do_POST(self):
        body = self.rfile.read(int(self.headers.get("content-length", 0)))
        with lock:
            seen["requests"] += 1
            keyed = self.headers.get("x-api-key") == KEY and self.headers.get("x-api-secret") == SECRET
            if self.path != "/read" or not keyed:
                seen["badAuth"] += 1
            answer = fake(httpx2.Request("POST", f"http://komodo-core:9120{self.path}", content=body))
        self.send_response(answer.status_code)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(answer.content)

    def log_message(self, *_):
        pass


def get(path):
    with urllib.request.urlopen(f"http://127.0.0.1:{PERCH_PORT}{path}", timeout=10) as response:
        return response.read().decode()


def waitFor(label, check, seconds=40):
    deadline = time.monotonic() + seconds
    last = "not yet"
    while time.monotonic() < deadline:
        try:
            if check():
                print(f"ok    {label}")
                return True
        except OSError as exc:  # perch may still be starting
            last = str(exc)
        time.sleep(0.5)
    print(f"FAIL  {label} (waited {seconds} s; last error: {last})")
    return False


def memory(pid):
    out = {}
    for line in open(f"/proc/{pid}/status", encoding="ascii"):
        if line.startswith(("VmRSS", "VmHWM")):
            key, value = line.split(":")
            out[key] = int(value.split()[0]) / 1024  # kB -> MB
    return out


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Komodo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    env = {
        **os.environ,
        "PERCH_PURR_URL": f"http://127.0.0.1:{PORT}",
        "PERCH_PURR_KEY": KEY,
        "PERCH_PURR_SECRET": SECRET,
        "PERCH_PURR_EVERY": "2s",
        "PERCH_REPO_DIR": REPO,
        "PERCH_TRAIL_DB": "/tmp/budget-scentTrail.db",
        "PERCH_PORT": str(PERCH_PORT),
        "PERCH_TZ": "Asia/Kolkata",
    }
    perch = subprocess.Popen([sys.executable, "-m", "perch"], env=env)  # noqa: S603
    failed = 0
    try:
        failed += not waitFor("perch is up, purr has looked: slowBlink", lambda: "fleet: slowBlink" in get("/"))
        with lock:
            fake.exit("grinder", "n8n", 137)
        failed += not waitFor("n8n stopped: the overview hisses (two cycles)", lambda: "fleet: hiss" in get("/"))
        page = get("/tree/grinder/n8n")
        failed += "exited (code 137" not in page
        with lock:
            fake.start("grinder", "n8n")
        failed += not waitFor("n8n back: the overview is slowBlink again", lambda: "fleet: slowBlink" in get("/"))
        with lock:
            fake.nodeDown("grinder")
        failed += not waitFor("grinder not answering: hiss", lambda: "isn&#39;t answering" in get("/"))
        with lock:
            fake.nodeUp("grinder")
        failed += not waitFor("grinder back: slowBlink", lambda: "fleet: slowBlink" in get("/"))
        for _ in range(80):  # page loads, as M0's budget check did
            for path in ("/", "/tree", "/tree/grinder", "/tree/grinder/n8n", "/trail"):
                get(path)
        time.sleep(4)
        health = json.loads(get("/healthz"))
        mem = memory(perch.pid)
        print(f"purr: {health['collectors']['purr']}")
        print(f"komodo requests served: {seen['requests']}, with a wrong path or key: {seen['badAuth']}")
        print(f"perch memory: VmRSS {mem['VmRSS']:.1f} MB, peak {mem['VmHWM']:.1f} MB (budget {BUDGET_MB} MB)")
        purrLevel = health["collectors"]["purr"]["level"]
        failed += seen["badAuth"] != 0 or mem["VmHWM"] > BUDGET_MB or purrLevel != "slowBlink"
    finally:
        perch.terminate()
        perch.wait(timeout=15)
        server.shutdown()
    print("budget and drill: " + ("FAILED" if failed else "ok"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
