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

import asyncio
import base64
import http.server
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
from datetime import UTC, datetime, timedelta
from pathlib import Path

import httpx2
from haFake import TOKEN as HA_TOKEN
from haFake import HAFake
from komodoFake import KEY, SECRET, FleetFake
from outsideFakes import GATUS_PASSWORD, GATUS_USER, SPEEDTEST_TOKEN, ScrutinyFake, SpeedtestFake, gatusKey, stamp

from perch.catTree import CatTree

BUDGET_MB = 300
PORT, PERCH_PORT = 9120, 8080
REPO = os.environ.get("PERCH_REPO_DIR", "/fleet")
DB = "/tmp/budget-scentTrail.db"
BEARER = "abcdefghijklmnopqrstuvwx"  # a token-shaped string nobody configured: the scrubber must catch its shape
LEAKY = {"on": False}  # Komodo answering 500 with the credentials in the body

# M3: fake ntfy (self-hosted), a fake critical topic, a fake healthchecks endpoint, on loopback ports
NTFY_PORT, CRIT_PORT, HC_PORT = 9201, 9202, 9203
NTFY_TOKEN = "tk_budgetfake1234"
ACK_SECRET = "fake-budget-ack-secret-not-real-0123456789"
NTFY_TOPIC, CRIT_TOPIC, PING_ID = "budget-fake-topic", "budget-fake-critical", "00000000-budget-fake-uuid"
# M4: fake Gatus (Basic auth), fake Scrutiny and fake speedtest-tracker on loopback ports; no real service is ever asked
GATUS_PORT, SCRUTINY_PORT, SPEED_PORT = 9204, 9205, 9206
FAILS = {"network_pihole": 0}  # how many of pihole's newest Gatus results fail
ENDPOINTS = (("cloudflare tunnel", "network"), ("pihole", "network"), ("authelia", "identity"))
# M5: a fake Home Assistant (WebSocket) on a loopback port; perch's whiskers talks to it, no real one is ever asked
HA_PORT = 9207
HA_ENTITIES = """
entities:
  binary_sensor.front_door:
    name: Front door
    states: {"on": earTwitch}
    words: {"on": open, "off": closed}
  binary_sensor.kitchen_water_leak:
    name: Kitchen leak sensor
    states: {"on": hiss}
    words: {"on": wet, "off": dry}
"""
HA_FILE = "/tmp/budget-whiskers.yml"
pushes = {"ntfy": [], "critical": []}
pings: list[str] = []


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


class Gatus(http.server.BaseHTTPRequestHandler):
    """Gatus v5.36.0's statuses, behind Basic auth as Authelia's forward-auth-basic would have it."""

    def do_GET(self):
        want = "Basic " + base64.b64encode(f"{GATUS_USER}:{GATUS_PASSWORD}".encode()).decode()
        if self.headers.get("authorization") != want or not self.path.startswith("/api/v1/endpoints/statuses"):
            self.send_response(401)
            self.end_headers()
            return
        now, body = datetime.now(UTC), []
        for name, group in ENDPOINTS:
            key = gatusKey(group, name)
            bad = FAILS.get(key, 0)
            results = [
                {
                    "status": 200 if i >= bad else 503,
                    "duration": 9_000_000,
                    "success": i >= bad,
                    "conditionResults": [{"condition": "[STATUS] == 200", "success": i >= bad}],
                    "timestamp": stamp(now - timedelta(seconds=60 * i)),
                    **({} if i >= bad else {"errors": ["HTTP 503"]}),
                }
                for i in range(9, -1, -1)  # i = 0 is the newest; the newest `bad` ones fail
            ]
            body.append({"name": name, "group": group, "key": key, "results": results})
        self.send_response(200)
        self.send_header("content-type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(body).encode())

    def log_message(self, *_):
        pass


def fakeServer(fake, port):
    """An httpx2 MockTransport fake (Scrutiny, speedtest-tracker) behind a real loopback socket."""

    class Handler(http.server.BaseHTTPRequestHandler):
        def do_GET(self):
            url = "http://192.0.2.1" + self.path
            answer = fake(httpx2.Request("GET", url, headers={k: v for k, v in self.headers.items()}))
            self.send_response(answer.status_code)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(answer.content)

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


def pushServer(channel, port, token=""):
    class Handler(http.server.BaseHTTPRequestHandler):
        def do_POST(self):
            body = self.rfile.read(int(self.headers.get("content-length", 0)))
            if token and self.headers.get("authorization") != f"Bearer {token}":
                self.send_response(401)
                self.end_headers()
                return
            with lock:
                pushes[channel].append(json.loads(body))
            self.send_response(200)
            self.send_header("content-type", "application/json")
            self.end_headers()
            self.wfile.write(b"{}")

        def log_message(self, *_):
            pass

    server = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server


class Healthchecks(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        with lock:
            pings.append(self.path)
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")

    def log_message(self, *_):
        pass


def post(path):
    """A POST with no body to perch over a real socket, as an ntfy button sends it: the status code."""
    request = urllib.request.Request(f"http://127.0.0.1:{PERCH_PORT}{path}", data=b"", method="POST")  # noqa: S310
    try:
        with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
            return response.status
    except urllib.error.HTTPError as exc:
        return exc.code


def titles(channel):
    with lock:
        return [p["title"] for p in pushes[channel]]


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


def leaks(places, extra=()):
    """Which of the secrets turned up in which place."""
    found = []
    for place, content in places.items():
        for name, needle in (("API key", KEY), ("API secret", SECRET), ("bearer token", BEARER), *extra):
            if needle.encode() in content:
                found.append(f"{name} in {place}")
    return found


def main() -> int:
    server = http.server.ThreadingHTTPServer(("127.0.0.1", PORT), Komodo)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    others = [
        pushServer("ntfy", NTFY_PORT, NTFY_TOKEN),
        pushServer("critical", CRIT_PORT),
        http.server.ThreadingHTTPServer(("127.0.0.1", HC_PORT), Healthchecks),
    ]
    threading.Thread(target=others[2].serve_forever, daemon=True).start()
    gatus = http.server.ThreadingHTTPServer(("127.0.0.1", GATUS_PORT), Gatus)
    threading.Thread(target=gatus.serve_forever, daemon=True).start()
    scrutiny, speed = ScrutinyFake(Clock()), SpeedtestFake(Clock())
    scrutiny.add(
        "0x5000cca000000001", "sda", "cellar", "WDC WD40EFRX", summaryHours=3, attrs={"9": scrutiny.attr(9, 20000)}
    )
    others += [gatus, fakeServer(scrutiny, SCRUTINY_PORT), fakeServer(speed, SPEED_PORT)]
    ha, haLoop = HAFake(), asyncio.new_event_loop()
    ha.port = HA_PORT
    ha.set("binary_sensor.front_door", "off")
    ha.set("binary_sensor.kitchen_water_leak", "off")
    ha.set("light.kitchen", "on")  # not on perch's list
    threading.Thread(target=haLoop.run_forever, daemon=True).start()

    def onHa(coro):
        return asyncio.run_coroutine_threadsafe(coro, haLoop).result(10)

    onHa(ha.start())
    Path(HA_FILE).write_text(HA_ENTITIES, encoding="utf-8")
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
        "PERCH_MEOW_NTFY_URL": f"http://127.0.0.1:{NTFY_PORT}/{NTFY_TOPIC}",
        "PERCH_MEOW_NTFY_TOKEN": NTFY_TOKEN,
        "PERCH_MEOW_CRITICAL_URL": f"http://127.0.0.1:{CRIT_PORT}/{CRIT_TOPIC}",
        "PERCH_ACK_SECRET": ACK_SECRET,
        "PERCH_PUBLIC_URL": f"http://127.0.0.1:{PERCH_PORT}",
        "PERCH_NINELIVES_URL": f"http://127.0.0.1:{HC_PORT}/{PING_ID}",
        "PERCH_GLARE_URL": f"http://127.0.0.1:{GATUS_PORT}",
        "PERCH_GLARE_USER": GATUS_USER,
        "PERCH_GLARE_PASSWORD": GATUS_PASSWORD,
        "PERCH_GLARE_EVERY": "2s",
        "PERCH_DISKS_URL": f"http://127.0.0.1:{SCRUTINY_PORT}",
        "PERCH_DISKS_EVERY": "2s",
        "PERCH_BINOCS_SPEEDTEST_URL": f"http://127.0.0.1:{SPEED_PORT}",
        "PERCH_BINOCS_SPEEDTEST_TOKEN": SPEEDTEST_TOKEN,
        "PERCH_BINOCS_EVERY": "2s",
        "PERCH_WHISKERS_URL": f"http://127.0.0.1:{HA_PORT}",
        "PERCH_WHISKERS_TOKEN": HA_TOKEN,
        "PERCH_WHISKERS_ENTITIES": HA_FILE,
        "PERCH_WHISKERS_EVERY": "2s",
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

        # M3: meow pushes it once to each channel, the button acknowledges once, a replay is refused
        failed += not waitFor(
            "meow pushed grinder unreachable to the fake ntfy and the fake critical topic",
            lambda: (
                any("grinder unreachable" in t for t in titles("ntfy"))
                and any("grinder unreachable" in t for t in titles("critical"))
            ),
            seconds=90,
        )
        with lock:
            down = next(p for p in pushes["ntfy"] if "grinder unreachable" in p["title"])
            downCritical = next(p for p in pushes["critical"] if "grinder unreachable" in p["title"])
        buttons = down.get("actions", [])
        buttonOk = len(buttons) == 1 and buttons[0]["label"] == "Acknowledge" and buttons[0]["method"] == "POST"
        failed += not buttonOk
        failed += bool(downCritical.get("actions"))  # never a button on the third-party copy
        print(f"{'ok  ' if buttonOk else 'FAIL'}  the ntfy push carries one Acknowledge button (POST)")
        print(f"{'ok  ' if not downCritical.get('actions') else 'FAIL'}  the critical copy carries none")
        ackPath = buttons[0]["url"].removeprefix(f"http://127.0.0.1:{PERCH_PORT}") if buttons else "/ack/t/none"
        tampered = post(ackPath[:-3] + "AAA")
        first, replay = post(ackPath), post(ackPath)
        good = (tampered, first, replay) == (403, 200, 403)
        print(f"{'ok  ' if good else 'FAIL'}  tampered {tampered}, button {first}, replay {replay} (want 403 200 403)")
        failed += not good
        failed += not waitFor("nineLives pinged the fake healthchecks endpoint", lambda: bool(pings), seconds=90)

        # M4: glare, disks and binocs read their fakes over real sockets; a failing endpoint hisses and is pushed
        failed += not waitFor("glare read the fake Gatus: 3 of 3 answering", lambda: "3 of 3 answering" in get("/"))
        failed += not waitFor(
            "disks read the fake Scrutiny; SMART attribute 9 (20000 h) beat the summary (3 h)",
            lambda: "833 d powered on" in get("/") and "3 h powered on" not in get("/"),
        )
        failed += not waitFor(
            "binocs read the fake speedtest-tracker", lambda: "down 312.4 Mbit/s" in get("/"), seconds=20
        )
        FAILS["network_pihole"] = 5
        failed += not waitFor(
            "five failed Gatus checks: pihole is a hiss on the overview",
            lambda: "failed 5 checks in a row" in get("/") and "2 of 3 answering" in get("/"),
        )
        failed += not waitFor(
            "meow pushed the failing endpoint by its name",
            lambda: any("pihole: failed 5 checks in a row" in t for t in titles("ntfy")),
            seconds=90,
        )
        FAILS["network_pihole"] = 0
        failed += not waitFor("pihole answers again: 3 of 3 answering", lambda: "3 of 3 answering" in get("/"))
        # M5: whiskers reads the fake Home Assistant over a real WebSocket; a leak hisses and is pushed
        failed += not waitFor(
            "whiskers read the fake Home Assistant: 2 sensors watched", lambda: "2 sensors watched" in get("/")
        )
        onHa(ha.change("light.kitchen", "off"))  # not on the list: dropped
        onHa(ha.change("binary_sensor.front_door", "on"))
        onHa(ha.change("binary_sensor.kitchen_water_leak", "on"))
        failed += not waitFor(
            "a leak is a hiss on the overview, a door is not",
            lambda: "Kitchen leak sensor" in get("/") and "fleet: hiss" in get("/") and "light.kitchen" not in get("/"),
        )
        failed += not waitFor(
            "meow pushed the leak",
            lambda: any("Kitchen leak sensor: wet" in t for t in titles("ntfy")),
            seconds=90,
        )
        onHa(ha.change("binary_sensor.kitchen_water_leak", "off"))
        onHa(ha.change("binary_sensor.front_door", "off"))
        failed += not waitFor(
            "the leak dried: 2 sensors, none out of place",
            lambda: "Everything on the list is in its usual state" in get("/"),
        )
        sent = set(ha.types())
        allowed = sent <= {"auth", "subscribe_events", "get_states"}
        mark = "ok  " if allowed else "FAIL"
        print(f"{mark}  S4 over a real socket: perch said only {sorted(sent)} to Home Assistant")
        failed += not allowed
        with lock:
            fake.nodeUp("grinder")
        failed += not waitFor("grinder back: slowBlink", lambda: "fleet: slowBlink" in get("/"))
        recovered = waitFor(
            "meow announced the recovery once",
            # grinder and pihole recovered close together: meow sends the two as one push (design plan 5)
            lambda: sum("grinder back" in t or "things are back" in t for t in titles("ntfy")) == 1,
            seconds=90,
        )
        if not recovered:
            print("      ntfy titles:", titles("ntfy"))
        failed += not recovered

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
        places["page /trail (meow events)"] = get("/trail?hours=1").encode()
        extra = (
            ("ack secret", ACK_SECRET),
            ("ntfy token", NTFY_TOKEN),
            ("ack token", ackPath.rsplit("/", 1)[-1]),
            ("ntfy topic", NTFY_TOPIC),
            ("critical topic", CRIT_TOPIC),
            ("healthchecks ping id", PING_ID),
            ("Gatus password", GATUS_PASSWORD),
            ("Gatus Basic credential", base64.b64encode(f"{GATUS_USER}:{GATUS_PASSWORD}".encode()).decode()),
            ("speedtest-tracker token", SPEEDTEST_TOKEN),
            ("Home Assistant token", HA_TOKEN),
            ("Home Assistant token (its signature)", HA_TOKEN.rsplit(".", 1)[-1]),
        )
        found = leaks(places, extra)
        print(
            f"leak check: looked in {len(places)} places ({sum(len(c) for c in places.values()) // 1024} KB): "
            + ("LEAKED " + "; ".join(found) if found else "nothing found")
        )
        failed += bool(found)
    finally:
        perch.terminate()
        perch.wait(timeout=15)
        server.shutdown()
        for other in others:
            other.shutdown()
        onHa(ha.stop())
        haLoop.call_soon_threadsafe(haLoop.stop)
    print("budget, drill and leak check: " + ("FAILED" if failed else "ok"))
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
