"""The M2 live-refresh gate (05 plan section 5, ADR 0003), in a real browser against the real image:

- the overview refreshes its state region within 35 s **without a full page reload** (a variable set
  on `window` survives; a reload would clear it);
- **focus and scroll position are kept** across the swap (the focused node card is replaced, so it
  must get its focus back by its id);
- a **state change reaches an open overview** within 35 s: here a node's kitten reports a failed
  backup through the one write endpoint, `/api/kitten`, and the overview says so;
- the change is **announced once** through the polite live region, never again while nothing changes;
- with prefers-reduced-motion, nothing animates.

M5 adds the live scentTrail: an open /trail shows a new event within 5 s without a reload, keeps focus and
scroll, respects its filters, and says a new hiss once through the polite live region.

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


# In the page (M4): every sparkline is drawn (a path with data), has a text alternative, and is the muted
# colour: its stroke is the colour the svg inherits from --muted, never a bodyLanguage colour.
SPARK_CHECK = r"""() => {
  const out = { count: 0, undrawn: [], unlabelled: [], recoloured: [], labels: [], tall: 0 };
  for (const svg of document.querySelectorAll('svg.spark')) {
    out.count++;
    const label = svg.getAttribute('aria-label') || '';
    out.labels.push(label);
    const wordsOk = /^(CPU|RAM|disk) [\d.]+ (h|days): /.test(label);
    if (svg.getAttribute('role') !== 'img' || !wordsOk) out.unlabelled.push(label);
    const line = svg.querySelector('path.line');
    const box = svg.getBoundingClientRect();
    const d = line ? (line.getAttribute('d') || '') : '';
    if (!d.startsWith('M') || box.width < 30 || box.height < 20) out.undrawn.push(label);
    if (line && getComputedStyle(line).stroke !== getComputedStyle(svg).color) out.recoloured.push(label);
    if (box.height > 40) out.tall++;
  }
  const muted = getComputedStyle(document.documentElement).getPropertyValue('--muted').trim();
  out.muted = muted;
  return out;
}"""


SIDEWAYS = "[document.documentElement.scrollWidth, document.documentElement.clientWidth]"


def openPage(page, path: str) -> None:
    """goto, then wait until the page is quiet. The trail keeps its event stream open for ever, so there the
    network is never idle: wait for the stream request to have been made, and give it a moment to connect."""
    if path.startswith("/trail"):
        seen: list[str] = []
        page.on("request", lambda r: seen.append(r.url) if "/trail/stream" in r.url else None)
        page.goto(BASE + path, wait_until="load")
        end = time.time() + 5
        while not seen and time.time() < end:
            page.wait_for_timeout(100)
        page.wait_for_timeout(600)
    else:
        page.goto(BASE + path, wait_until="networkidle")


def check(name: str, ok: bool, detail: str = "") -> None:
    print(f"{'ok  ' if ok else 'FAIL'} {name}{'  ' + detail if detail and not ok else ''}")
    if not ok:
        failures.append(name)


def pounceEvent(name: str, level: str = "tailFlick") -> None:
    """sieve's kitten reports one filesystem event through the one write endpoint."""
    eventId = os.urandom(6).hex()
    status = postKitten(
        {
            "node": "sieve",
            "events": [
                {
                    "id": eventId,
                    "at": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "path": "/etc/purrbrews",
                    "name": name,
                    "change": "modified",
                    "level": level,
                    "why": "settings changed",
                }
            ],
        }
    )
    if status != 200:
        failures.append(f"pounce event {name} was refused: HTTP {status}")


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


def liveTrail(browser) -> None:  # noqa: PLR0915
    """M5 gate, in a real browser: an open /trail shows a new event within 5 s without a reload, keeps focus
    and scroll, and respects its filters."""
    if not TOKEN:
        check("UI_KITTEN_TOKEN_SIEVE is set for the live trail check", False)
        return
    for view, width, scheme in (("1400-dark", 1400, "dark"), ("1400-light", 1400, "light"), ("390-dark", 390, "dark")):
        ctx = browser.new_context(viewport={"width": width, "height": 700}, color_scheme=scheme)
        page, other = ctx.new_page(), ctx.new_page()
        problems: list[str] = []
        page.on("console", lambda m, problems=problems: problems.append(m.text) if m.type == "error" else None)
        page.on("pageerror", lambda e, problems=problems: problems.append(str(e)))
        openPage(page, "/trail?sense=pounce&sense=whiskers")
        openPage(other, "/trail?sense=glare")
        check(
            f"the trail at {view} loaded the pinned SSE extension",
            page.evaluate("typeof htmx === 'object' && typeof htmx.createEventSource === 'function'"),
        )
        page.evaluate("window.__sameDocument = 'yes'")
        page.evaluate("window.scrollTo(0, 60)")
        scroll = page.evaluate("window.scrollY")
        first = f"first-{view}.env"
        started = time.time()
        pounceEvent(first)
        try:
            page.wait_for_function(
                "t => document.querySelector('#new-events').innerText.includes(t)", arg=first, timeout=5_000
            )
            took = time.time() - started
        except Exception:  # a timeout is the failure being reported
            took = 99.0
        check(f"a new event showed on the open trail at {view} within 5 s ({took:.1f} s)", took <= 5.0)
        check("... without a reload", page.evaluate("window.__sameDocument") == "yes")
        check("... without moving the scroll position", page.evaluate("window.scrollY") == scroll)
        check("... and without announcing a tailFlick", page.locator("#announce").inner_text().strip() == "")
        check(
            "the new row has the tailFlick body language",
            page.locator("#new-events li.event.bl-tailFlick").count() >= 1,
        )
        # focus: put it on the new row's link, send another event, the swap must not take it away
        link = page.locator("#new-events li.event a").first
        linkId = link.get_attribute("id")
        link.focus()
        check("the new row's link has a stable id", bool(linkId), str(linkId))
        pounceEvent(f"second-{view}.env")
        page.wait_for_function(
            "t => document.querySelector('#new-events').innerText.includes(t)", arg=f"second-{view}.env", timeout=5_000
        )
        check(
            "a second event arrived and the focused link kept focus through the swap",
            page.evaluate("document.activeElement && document.activeElement.id") == linkId,
            str(page.evaluate("document.activeElement && document.activeElement.id")),
        )
        check(
            "... and the list has both events, each once",
            page.locator("#new-events li.event").count() == 2,
            str(page.locator("#new-events li.event").count()),
        )
        page.wait_for_timeout(3_500)  # past the filter-free window: the glare-only page must have shown nothing
        check(
            "a trail filtered to glare did not list the pounce events",
            other.locator("#new-events li.event").count() == 0 and "Nothing new yet" in other.inner_text("#new-events"),
        )
        widths = page.evaluate(SIDEWAYS)
        check(f"the live trail at {view}: no horizontal scroll", widths[0] <= widths[1], str(widths))
        page.screenshot(path=f"{OUT}/trail-live-{view}.png", full_page=True)
        check(f"no console errors on the live trail at {view}", not problems, str(problems))
        ctx.close()
    reduced = browser.new_context(viewport={"width": 1400, "height": 700}, reduced_motion="reduce")
    quiet = reduced.new_page()
    openPage(quiet, "/trail")
    moving = quiet.evaluate(
        "[...document.querySelectorAll('body *')].filter(e => { const s = getComputedStyle(e);"
        " return (parseFloat(s.transitionDuration) > 0 && s.transitionProperty !== 'none') ||"
        " (parseFloat(s.animationDuration) > 0 && s.animationName !== 'none'); }).length"
    )
    check("under prefers-reduced-motion nothing animates on the live trail", moving == 0, f"{moving} elements")
    reduced.close()
    off = browser.new_context(viewport={"width": 1400, "height": 700}, java_script_enabled=False)
    plain = off.new_page()
    plain.goto(BASE + "/trail", wait_until="load")
    check(
        "with JavaScript off the trail still lists events as of load and hides the live section",
        plain.locator("#main li.event").count() > 3 and not plain.locator("#new-h").is_visible(),
    )
    off.close()


def main() -> int:  # noqa: PLR0912 - one long scripted walk through the pages
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
            watching = context.new_page()  # an open trail while the failed backup is reported (M5)
            openPage(watching, "/trail")
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
            # the open trail got the hiss without a reload, and said it once through the polite live region
            watching.wait_for_selector("#new-events .feed", timeout=5_000)
            rows = watching.locator("#new-events li.event.bl-hiss").count()
            spoken = watching.locator("#announce").inner_text().strip()
            check("the open trail listed the failed backup as a hiss row", rows >= 1, f"{rows} rows")
            check(
                "... and said one new hiss through the polite live region",
                spoken.startswith("New hiss:") and spoken.count("New hiss") == 1,
                spoken,
            )
            watching.close()

        # 2b. Acknowledge, in a real browser: htmx posts the form (CSRF token, same-origin headers) and the
        # button is replaced by one line; a reload shows the litter acknowledged
        page.goto(BASE + "/", wait_until="networkidle")
        button = page.locator("#alerts form.ack button")
        check("the Alerts card has an Acknowledge button for the seeded hiss", button.count() >= 1)
        if button.count():
            shape = page.evaluate(
                "() => { const b = document.querySelector('#alerts form.ack button'); const s = getComputedStyle(b);"
                " return [b.textContent.trim(), s.backgroundColor, b.getBoundingClientRect().height]; }"
            )
            ok = shape[0] == "Acknowledge" and shape[2] >= 24
            check("the button says Acknowledge and is at least 24 px tall", ok, str(shape))
            page.screenshot(path=f"{OUT}/alerts-card-1400-dark.png", full_page=True)
            before = button.count()
            page.evaluate("window.__sameDocument = 'yes'")
            button.first.click()
            try:
                page.wait_for_selector("#alerts .acked", timeout=10_000)
                done = True
            except Exception:
                done = False
            same = page.evaluate("window.__sameDocument") == "yes"
            check("clicking Acknowledge replaced the button with a line, without a reload", done and same)
            left = page.locator("#alerts form.ack button").count()
            check("one litter fewer is waiting to be acknowledged", left == before - 1)
            page.reload(wait_until="networkidle")
            alerts = page.locator("#alerts").inner_text()
            check("after a reload the litter shows as acknowledged", "acknowledged" in alerts)

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

        # 4. M4: the vitals sparklines, and the glare, disks and binocs cards, in both themes and on a phone
        for view, width, scheme in (
            ("1400-dark", 1400, "dark"),
            ("1400-light", 1400, "light"),
            ("390-dark", 390, "dark"),
        ):
            ctx = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
            outside = ctx.new_page()
            seen: list[str] = []
            outside.on("console", lambda m, seen=seen: seen.append(m.text) if m.type == "error" else None)
            outside.on("pageerror", lambda e, seen=seen: seen.append(str(e)))
            for path, expected in (("/", 15), ("/tree/grinder", 6), ("/tree/cellar", 6)):
                outside.goto(BASE + path, wait_until="networkidle")
                found = outside.evaluate(SPARK_CHECK)
                where = f"{path} at {view}"
                check(f"sparklines on {where}: {expected} are drawn", found["count"] == expected, str(found["count"]))
                check(
                    f"sparklines on {where}: every one is drawn with data", not found["undrawn"], str(found["undrawn"])
                )
                check(
                    f"sparklines on {where}: every one has a text alternative",
                    not found["unlabelled"],
                    str(found["unlabelled"]),
                )
                check(
                    f"sparklines on {where}: the line is the muted colour, never a state colour",
                    not found["recoloured"],
                    str(found["recoloured"]),
                )
                widths = outside.evaluate(SIDEWAYS)
                check(f"sparklines on {where}: no horizontal scroll", widths[0] <= widths[1], str(widths))
            # M5 task 0: the longest seeded subjects (no break points) on every list that shows subjects, at the
            # page's own font width and with every glyph 5 % and 12 % wider (a phone's fonts are not ours)
            for path in ("/", "/trail", "/tree/cellar", "/tree/percolator/vaultwarden"):
                openPage(outside, path)
                if path in ("/", "/trail"):
                    body = outside.inner_text("main")
                    check(
                        f"the longest seeded names are on {path} at {view}",
                        "an-image-name-with-no-break-points" in body and "a-deliberately-long-endpoint-name" in body,
                    )
                for extra in (0, 0.05, 0.12):
                    if extra:
                        outside.add_style_tag(content=f"body *{{letter-spacing:{extra}em !important}}")
                    widths = outside.evaluate(SIDEWAYS)
                    check(
                        f"{path} at {view} with fonts {int(extra * 100)} % wider: scrollWidth <= clientWidth",
                        widths[0] <= widths[1],
                        str(widths),
                    )
            outside.goto(BASE + "/", wait_until="networkidle")
            outside.screenshot(path=f"{OUT}/overview-m4-{view}.png", full_page=True)
            text = outside.inner_text("main")
            check(
                f"the overview at {view} shows glare, disks and binocs",
                all(w in text for w in ("Endpoints", "Disks", "Outside", "5 of 7 answering")),
                text[:200],
            )
            check(
                f"the overview at {view} says SMART attribute 9 hours, not the summary's 3 h",
                "833 d powered on" in text and "3 h powered on" not in text,
            )
            check(f"no console errors on the M4 pages at {view}", not seen, str(seen))
            if view == "1400-dark":
                labels = outside.evaluate(SPARK_CHECK)["labels"]
                print("     e.g.", labels[0], "|", labels[1], "|", labels[2])
                outside.goto(BASE + "/tree/cellar", wait_until="networkidle")
                gapped = [x for x in outside.evaluate(SPARK_CHECK)["labels"] if "with gaps" in x]
                check(
                    "cellar's 4-hour gap is a gap, said in words (a sparkline that is 'with gaps')",
                    bool(gapped),
                    str(gapped),
                )
            outside.goto(BASE + "/tree/cellar", wait_until="networkidle")
            outside.screenshot(path=f"{OUT}/cellar-m4-{view}.png", full_page=True)
            ctx.close()

        # 5. the grooming grid with a failed run selected: both themes, and a phone, no sideways scroll
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
                widths = groomPage.evaluate(SIDEWAYS)
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
        liveTrail(browser)
        browser.close()
    print(f"live: {'FAILED' if failures else 'all ok'}")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
