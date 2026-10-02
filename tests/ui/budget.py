"""Budget, real-socket drill and leak check (05 plan 4 step 9, test S2's spirit): perch with purr
really running, over HTTP.

Starts a small HTTP server that speaks Komodo's /read API (the fake from tests/komodoFake.py),
runs `python -m perch` pointed at it with a short rhythm, loads the pages, stops n8n in the fake
and waits for the overview to hiss, restores it and waits for slowBlink. It also makes Komodo
fail the worst way for secrets (HTTP 500 whose body echoes the API key, the secret and a bearer
token) and checks that none of them reach perch's own output, any page, /healthz, or the
scentTrail database files. Last it prints perch's own memory (VmRSS and its peak, from /proc)
against the 300 MB budget of design plan 2.1.

This is the M1 gate's drill with a real socket and a real clock instead of a fake one. Run in the
perch image (see the runbook, M1 entry); exits non-zero if a drill step, a leak or the budget fails.
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
from pathlib import Path

import httpx2
from komodoFake import KEY, SECRET, FleetFake

from perch.catTree import CatTree

BUDGET_MB = 300
PORT, PERCH_PORT = 9120, 8080
REPO = os.environ.get("PERCH_REPO_DIR", "/fleet")
DB = "/tmp/budget-scentTrail.db"
BEARER = "abcdefghijklmnopqrstuvwx"  # a token-shaped string nobody configured: the scrubber must catch its shape
LEAKY = {"on": False}  # Komodo answering 500 with the credentials in the body


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
            if LEAKY["on"]:
                text = f"denied for key {KEY} secret {SECRET} Authorization: Bearer {BEARER}"
                self.send_response(500)
                self.send_header("content-type", "text/plain")
                self.end_headers()
                self.wfile.write(text.encode())
                return
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


def leaks(places):
    """Which of the secrets turned up in which place."""
    found = []
    for place, content in places.items():
        for name, needle in (("API key", KEY), ("API secret", SECRET), ("bearer token", BEARER)):
            if needle.encode() in content:
                found.append(f"{name} in {place}")
    return found


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
        "PERCH_TRAIL_DB": DB,
        "PERCH_PORT": str(PERCH_PORT),
        "PERCH_TZ": "Asia/Kolkata",
    }
    perch = subprocess.Popen(  # noqa: S603
        [sys.executable, "-m", "perch"], env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT
    )
    output = bytearray()  # everything perch prints, for the leak check

    def drain():
        for chunk in iter(lambda: perch.stdout.read1(4096), b""):
            output.extend(chunk)

    threading.Thread(target=drain, daemon=True).start()
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

        LEAKY["on"] = True  # Komodo now answers 500 and echoes the credentials back
        failed += not waitFor(
            "Komodo errors with the credentials in its body: purr is late", lambda: "purr is late" in get("/")
        )
        pages = {p: get(p).encode() for p in ("/", "/tree", "/tree/grinder", "/tree/grinder/n8n", "/trail", "/healthz")}
        LEAKY["on"] = False
        failed += not waitFor("Komodo answers again: purr is back", lambda: "purr is back" in get("/trail"))

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

        # leak check: the pages while Komodo was echoing credentials, perch's own output, the database files
        # control: the poisoned body really reached the page, and only in masked form (else the check proves nothing)
        control = "••••".encode() in pages["/"] and b"Komodo answered HTTP 500" in pages["/"]
        print(f"control: the 500 body reached the overview and was masked: {control}")
        failed += not control
        places = {f"page {p}": body for p, body in pages.items()}
        places["perch stdout/stderr"] = bytes(output)
        places["page /trail (after)"] = get("/trail").encode()
        for suffix in ("", "-wal", "-shm"):
            if Path(DB + suffix).exists():
                places[f"scentTrail {DB + suffix}"] = Path(DB + suffix).read_bytes()
        found = leaks(places)
        print(
            f"leak check: looked in {len(places)} places ({sum(len(c) for c in places.values()) // 1024} KB): "
            + ("LEAKED " + "; ".join(found) if found else "nothing found")
        )
        failed += bool(found)
    finally:
        perch.terminate()
        perch.wait(timeout=15)
        server.shutdown()
    print("budget, drill and leak check: " + ("FAILED" if failed else "ok"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
