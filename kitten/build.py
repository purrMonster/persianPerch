"""Build kitten's zipapp: ``python -m kitten.build kitten.pyz`` from the project root.

The archive holds the ``kitten`` package and a ``__main__.py`` that calls ``main()``; run it with
``python3 kitten.pyz`` (Python 3.13 on the nodes, 3.14 on roastery). Standard library only.
"""

from __future__ import annotations

import shutil
import sys
import tempfile
import zipapp
from pathlib import Path

PACKAGE = Path(__file__).resolve().parent
MAIN = "import sys\nfrom kitten.kitten import main\n\nsys.exit(main())\n"


def build(target: "str | Path") -> Path:
    target = Path(target)
    with tempfile.TemporaryDirectory() as staging:
        stage = Path(staging)
        package = stage / "kitten"
        package.mkdir()
        for source in PACKAGE.glob("*.py"):
            if source.name != "build.py":
                shutil.copy(source, package / source.name)
        (stage / "__main__.py").write_text(MAIN, encoding="utf-8")
        zipapp.create_archive(stage, target, interpreter="/usr/bin/env python3", compressed=True)
    return target


if __name__ == "__main__":
    out = build(sys.argv[1] if len(sys.argv) > 1 else "kitten.pyz")
    print(f"built {out} ({out.stat().st_size} bytes)")
