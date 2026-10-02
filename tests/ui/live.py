"""The M2 live-refresh gate (05 plan section 5, ADR 0003), in a real browser against the real image:

- the overview refreshes its state region within 35 s **without a full page reload** (a variable set
  on `window` survives; a reload would clear it);
- **focus and scroll position are kept** across the swap (the focused node card is replaced, so it
  must get its focus back by its id);
- a **state change reaches an open overview** within 35 s: here a node's kitten reports a failed
  backup through the one write endpoint, `/api/kitten`, and the overview says so;
- the change is **announced once** through the polite live region, never again while nothing changes;
- with prefers-reduced-motion, nothing animates.

Runs in the Playwright image after shoot.py (tests/ui/compose.yml); exit code 0 only if all hold.
"""

import json
import os
import sys
import time
import urllib.request
from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PERCH_URL", "http://perch:8080")
TOKEN = os.environ.get("UI_KITTEN_TOKEN_SIEVE", "")
STATE_CHANGE = os.environ.get("UI_STATE_CHANGE") == "1"
WAIT_MS = 35_000
failures: list[str] = []


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def lastNightlySlot() -> datetime:
    """01:30 IST on the latest day that has already passed: the night sieve's backup is judged on."""
    tz = ZoneInfo("Asia/Kolkata")
    now = datetime.now(tz)
    slot = now.replace(hour=1, minute=30, second=0, microsecond=0)
    return slot if slot <= now else slot - timedelta(days=1)


def postKitten(body: dict) -> int:
    request = urllib.request.Request(  # noqa: S310 - the test perch, over http inside the compose network
        f"{BASE}/api/kitten",
        data=json.dumps(body).encode(),
        headers={"Authorization": f"Bearer {TOKEN}", "Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(request, timeout=10) as response:  # noqa: S310
        return response.status


def main() -> int:
    with sync_playwright() as p:
        browser = p.chromium.launch()
        context = browser.new_context(viewport={"width": 1400, "height": 500}, color_scheme="dark")
        page = context.new_page()
        errors: list[str] = []
        page.on("console", lambda m: errors.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e: errors.append(str(e)))
        polls: list[str] = []
        page.on("request", lambda r: polls.append(r.url) if "/live/" in r.url else None)

        page.goto(BASE + "/", wait_until="networkidle")
        check("htmx is loaded from perch", page.evaluate("typeof window.htmx === 'object' && htmx.version") == "2.0.11")
        page.evaluate("window.__sameDocument = 'yes'")
        asOf = page.locator("#live .asof").inner_text()
        page.locator("#node-grinder").focus()
        page.evaluate("window.scrollTo(0, 140)")
        scrollBefore = page.evaluate("window.scrollY")
        check("the page is scrolled for this test", scrollBefore > 0, f"scrollY={scrollBefore}")

        # 1. a refresh happens by itself, in the same document, with focus and scroll kept
        started = time.time()
        page.wait_for_function(
            "before => document.querySelector('#live .asof').innerText !== before", arg=asOf, timeout=WAIT_MS
        )
        took = time.time() - started
        check("the overview refreshed on its own within 35 s", took <= 35, f"{took:.0f} s")
        check("... without a full page reload", page.evaluate("window.__sameDocument") == "yes")
        check(
            "... by asking /live/overview", any(u.endswith("/live/overview") or "/live/overview?" in u for u in polls)
        )
        check(
            "... keeping focus", page.evaluate("document.activeElement && document.activeElement.id") == "node-grinder"
        )
        check("... keeping scroll position", page.evaluate("window.scrollY") == scrollBefore)
        check("nothing was announced while nothing changed", page.locator("#announce").inner_text().strip() == "")

        # 2. a state change reaches the open page: sieve's nightly backup failed
        if not STATE_CHANGE:
            print("skip the state-change check: UI_STATE_CHANGE is not set (kitten's endpoint comes later in M2)")
        elif not TOKEN:
            check("UI_KITTEN_TOKEN_SIEVE is set for the state-change check", False)
        else:
            slot = lastNightlySlot()
            before = page.locator("#fleet-badge").inner_text()
            status = postKitten(
                {
                    "node": "sieve",
                    "heartbeat": {"version": "0.1.0", "sentAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")},
                    "records": [
                        {
                            "schema": 1,
                            "job": "nightly",
                            "node": "sieve",
                            "unit": "purrbrews-backup@sieve.service",
                            "start": slot.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "end": (slot + timedelta(minutes=2)).astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                            "result": "exit-code",
                            "exitStatus": "1",
                            "logTail": "restic: repository unreachable (fake, for the UI check)",
                        }
                    ],
                }
            )
            check("kitten's report was accepted", status == 200, f"HTTP {status}")
            started = time.time()
            try:
                page.wait_for_function(
                    "() => document.querySelector('#live .attn') && "
                    "document.querySelector('#live .attn').innerText.includes('sieve')",
                    timeout=WAIT_MS,
                )
                seen = True
            except Exception:  # a timeout is the failure being reported
                seen = False
            check("the failed backup showed on the open overview within 35 s", seen, f"{time.time() - started:.0f} s")
            check("... without a full page reload", page.evaluate("window.__sameDocument") == "yes")
            said = page.locator("#announce").inner_text().strip()
            check(
                "the change was announced through the polite live region",
                "needs a look" in said or "things need" in said,
                said,
            )
            check(
                "the header followed (fleet badge present)",
                page.locator("#fleet-badge").inner_text().strip() != "",
                before,
            )
            page.wait_for_timeout(32_000)
            check(
                "a poll with nothing new says nothing new (same sentence, set once)",
                page.locator("#announce").inner_text().strip() == said,
            )

        # 3. reduced motion: nothing animates
        reduced = browser.new_context(viewport={"width": 1400, "height": 900}, reduced_motion="reduce")
        quiet = reduced.new_page()
        quiet.goto(BASE + "/", wait_until="networkidle")
        animated = quiet.evaluate(
            "[...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e);"
            " return (parseFloat(s.transitionDuration) > 0 && s.transitionProperty !== 'none') ||"
            " (parseFloat(s.animationDuration) > 0 && s.animationName !== 'none'); }).length"
        )
        check("under prefers-reduced-motion nothing animates", animated == 0, f"{animated} elements")
        reduced.close()

        check("no console errors", not errors, str(errors))
        browser.close()
    print(f"live: {'FAILED' if failures else 'all ok'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
