"""Render the seeded incident's pages to HTML files, for a person (or a reviewer) to read.

Run in the perch image after seeding (see the runbook, M1 entry):
    python seed.py && python dump.py /out
Writes one file per page, named like the screenshots (perch.html, catTree-app-hiss.html ...).
"""

import sys
from pathlib import Path

from fastapi.testclient import TestClient

from perch.settings import Settings
from perch.windowsill.app import createApp

PAGES = {
    "perch": "/",
    "catTree": "/tree",
    "catTree-node-hiss": "/tree/grinder",
    "catTree-node-roastery": "/tree/roastery",
    "catTree-app-hiss": "/tree/grinder/n8n",
    "catTree-app-karakeep": "/tree/grinder/karakeep",
    "catTree-app": "/tree/percolator/authelia",
    "groom": "/groom",
    "scentTrail": "/trail",
}

out = Path(sys.argv[1] if len(sys.argv) > 1 else "/out")
out.mkdir(parents=True, exist_ok=True)
with TestClient(createApp(Settings.fromEnv(), collectors=[])) as client:
    for name, path in PAGES.items():
        response = client.get(path)
        (out / f"{name}.html").write_text(response.text, encoding="utf-8")
        print(f"{response.status_code} {path} -> {name}.html ({len(response.text)} bytes)")
