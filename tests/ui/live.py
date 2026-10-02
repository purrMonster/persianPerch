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
OUT = os.environ.get("OUT_DIR", "/out")
TOKEN = os.environ.get("UI_KITTEN_TOKEN_SIEVE", "")
STATE_CHANGE = os.environ.get("UI_STATE_CHANGE") == "1"
WAIT_MS = 35_000
failures: list[str] = []


# In the page: for each judged cell in the grid, is its glyph really drawn (text, size, shown), and how
# does its colour compare with the disc it sits on (the WCAG relative-luminance formula)?
GLYPH_CHECK = r"""() => {
  const rgb = c => c.match(/[\d.]+/g).slice(0, 3).map(Number);
  const lum = c => { const [r, g, b] = rgb(c).map(v => {
      v /= 255; return v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4; });
    return 0.2126 * r + 0.7152 * g + 0.0722 * b; };
  const ratio = (a, b) => { const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p); return (x + 0.05) / (y + 0.05); };
  const hidden = []; let lowest = 99;
  const cells = [...document.querySelectorAll('table.nights a.cell')].filter(a => a.offsetParent !== null);
  for (const a of cells) {
    const disc = a.querySelector('.dot'), glyph = a.querySelector('.dot i');
    const box = glyph ? glyph.getBoundingClientRect() : null;
    const shown = glyph && glyph.textContent.trim() !== '' && glyph.getAttribute('aria-hidden') === 'true'
      && box.width >= 4 && box.height >= 8 && getComputedStyle(glyph).visibility === 'visible'
      && getComputedStyle(glyph).opacity !== '0';
    if (!shown) { hidden.push(a.getAttribute('title')); continue; }
    lowest = Math.min(lowest, ratio(getComputedStyle(glyph).color, getComputedStyle(disc).backgroundColor));
  }
  return { cells: cells.length, hidden, lowest: Math.round(lowest * 10) / 10 };
}"""


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
            check("the state-change check is switched on (UI_STATE_CHANGE=1 in compose.yml)", False)
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

        # 4. the grooming grid with a failed run selected: both themes, and a phone, no sideways scroll
        if STATE_CHANGE and TOKEN:
            night = lastNightlySlot().date().isoformat()
            for view, width, scheme in (
                ("1400-dark", 1400, "dark"),
                ("1400-light", 1400, "light"),
                ("390-dark", 390, "dark"),
            ):
                shot = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
                groomPage = shot.new_page()
                problems: list[str] = []
                groomPage.on(
                    "console", lambda m, problems=problems: problems.append(m.text) if m.type == "error" else None
                )
                groomPage.goto(f"{BASE}/groom?cell=sieve/nightly@{night}", wait_until="networkidle")
                widths = groomPage.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                groomPage.screenshot(path=f"{OUT}/groom-run-{view}.png", full_page=True)
                check(f"groom grid at {view}: no horizontal scroll", widths[0] <= widths[1], str(widths))
                check(
                    f"groom grid at {view}: the failed run is shown",
                    "restic: repository unreachable" in groomPage.content(),
                )
                check(f"groom grid at {view}: no console errors", not problems, str(problems))
                glyphs = groomPage.evaluate(GLYPH_CHECK)
                check(f"groom grid at {view}: there are judged cells to check", glyphs["cells"] > 0, str(glyphs))
                check(
                    f"groom grid at {view}: every judged cell has a visible glyph (shape, not only colour)",
                    glyphs["cells"] > 0 and not glyphs["hidden"],
                    str(glyphs["hidden"]),
                )
                check(
                    f"groom grid at {view}: each glyph is at least 4.5:1 against its fill (lowest {glyphs['lowest']})",
                    glyphs["cells"] > 0 and glyphs["lowest"] >= 4.5,
                    str(glyphs["lowest"]),
                )
                shot.close()
        browser.close()
    print(f"live: {'FAILED' if failures else 'all ok'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
