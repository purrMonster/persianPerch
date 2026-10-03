"""UI check (04 build prompt 6): every page at 1400 px dark and light and at 390 px,
with no horizontal scroll and no console errors. Screenshots go to /out.

Runs in the Playwright image (tests/ui/compose.yml); plain script, no pytest.
Exit code 0 only if every page passes.
"""

import os
import sys

from playwright.sync_api import sync_playwright

BASE = os.environ.get("PERCH_URL", "http://perch:8080")
OUT = os.environ.get("OUT_DIR", "/out")
PAGES = {
    "perch": "/",
    "catTree": "/tree",
    "catTree-node": "/tree/percolator",
    "catTree-app": "/tree/percolator/authelia",
    "catTree-app-hiss": "/tree/grinder/n8n",
    "catTree-node-hiss": "/tree/grinder",
    "catTree-node-disks": "/tree/cellar",
    "catTree-node-roastery": "/tree/roastery",
    "catTree-doc": "/tree/docs/README.md",
    "groom": "/groom",
    "scentTrail": "/trail",
}
# Fonts differ (Linux fallbacks here, whatever a phone has): a page must not scroll sideways at the width its
# fonts happen to give, so every page is measured twice, the second time with every glyph about 5 % wider
# (M5 task 0: the overview's rows ended 3 px past a 390 px viewport with slightly wider fonts).
WIDER = "body *{letter-spacing:.05em !important}"
MEASURE = """() => {
  const limit = document.documentElement.clientWidth;
  const over = [...document.querySelectorAll('body *')].filter(e => e.getBoundingClientRect().right > limit + 0.5
    && e.offsetParent !== null && !e.closest('.tablewrap, nav.main'))
    .slice(0, 4).map(e => (e.tagName + '.' + e.className).slice(0, 40) + ' '
      + Math.round(e.getBoundingClientRect().right));
  return [document.documentElement.scrollWidth, limit, over];
}"""
VIEWS = [("1400-dark", 1400, "dark"), ("1400-light", 1400, "light"), ("390-dark", 390, "dark")]


def main() -> int:
    os.makedirs(OUT, exist_ok=True)
    failures = []
    with sync_playwright() as p:
        browser = p.chromium.launch()
        for view, width, scheme in VIEWS:
            context = browser.new_context(viewport={"width": width, "height": 900}, color_scheme=scheme)
            page = context.new_page()
            errors = []
            page.on("console", lambda m, errors=errors: errors.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e, errors=errors: errors.append(str(e)))
            for name, path in PAGES.items():
                errors.clear()
                response = page.goto(BASE + path, wait_until="networkidle")
                status = response.status if response else 0
                scroll = page.evaluate(MEASURE)
                file = f"{OUT}/{name}-{view}.png"
                page.screenshot(path=file, full_page=True)
                page.add_style_tag(content=WIDER)
                wide = page.evaluate(MEASURE)
                problems = []
                if status != 200:
                    problems.append(f"HTTP {status}")
                if scroll[0] > scroll[1]:
                    problems.append(f"horizontal scroll {scroll[0]} > {scroll[1]} {scroll[2]}")
                if wide[0] > wide[1]:
                    problems.append(f"horizontal scroll with wider fonts {wide[0]} > {wide[1]} {wide[2]}")
                if errors:
                    problems.append(f"console errors: {errors}")
                mark = "FAIL" if problems else "ok  "
                line = f"{mark} {view:10} {path:28} scrollWidth={scroll[0]}/{wide[0]} -> {file}"
                print(line + (f"  {problems}" if problems else ""))
                if problems:
                    failures.append(line)
            context.close()
        browser.close()
    print(f"{len(PAGES) * len(VIEWS) - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
