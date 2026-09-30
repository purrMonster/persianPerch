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
    "catTree-doc": "/tree/docs/README.md",
    "groom": "/groom",
    "scentTrail": "/trail",
}
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
                scroll = page.evaluate("[document.documentElement.scrollWidth, window.innerWidth]")
                file = f"{OUT}/{name}-{view}.png"
                page.screenshot(path=file, full_page=True)
                problems = []
                if status != 200:
                    problems.append(f"HTTP {status}")
                if scroll[0] > scroll[1]:
                    problems.append(f"horizontal scroll {scroll[0]} > {scroll[1]}")
                if errors:
                    problems.append(f"console errors: {errors}")
                line = f"{'FAIL' if problems else 'ok  '} {view:10} {path:28} scrollWidth={scroll[0]} -> {file}"
                print(line + (f"  {problems}" if problems else ""))
                if problems:
                    failures.append(line)
            context.close()
        browser.close()
    print(f"{len(PAGES) * len(VIEWS) - len(failures)} passed, {len(failures)} failed")
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
