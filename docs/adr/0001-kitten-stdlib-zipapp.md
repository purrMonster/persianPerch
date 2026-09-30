# ADR 0001 — kitten is a stdlib-only zipapp; file events from inotifywait (Linux) and polling (Windows)

- Status: accepted · 2026-09-30 · M0
- Context: 05 plan C11 and A5; dev plan 1 (which proposed `watchfiles`).

## Context

kitten runs on every node: five Debian 13.7 hosts with Python 3.13.5 (owner's answer
Q15) and roastery, a Windows workstation with Python 3.14 (A5). It must install nothing
into the system Python, carry its own code as one file, and be simple to roll out with
the fleet's `init`/`_lib` scripts. The dev plan picked `watchfiles` for pounce
(filesystem events). `watchfiles` is a compiled extension (Rust `notify`): a zipapp can't
carry it, because Python can't import native extensions from inside a zip.

## Options

| Option | For | Against |
|---|---|---|
| **A. stdlib-only zipapp; `inotifywait` (Debian `inotify-tools`) on Linux, polling on Windows** | one file, no pip, no venv; `inotify-tools` is a small, stable Debian package; polling is fine for roastery's few paths | a subprocess to parse on Linux; polling on Windows (10 s) is slower than real events |
| B. `watchfiles` in a venv per node | real events on every OS, one code path | a venv and pip on every node and on roastery; compiled wheels per Python version and arch; more to update |
| C. polling everywhere | stdlib only, identical everywhere | 2 s debounce and a 5 s end-to-end target (M5 gate) mean polling every 1–2 s on busy paths like `/srv/dumps`: needless disk wake-ups on the nodes |

## Decision

**A.** kitten is a `python -m zipapp` of standard-library code only, targeting Python 3.13
and tested on 3.13 and 3.14 (test S8; `tests/kitten/test_kitten.py` also fails if any
kitten module imports outside the standard library). On Linux, pounce reads
`inotifywait -m -r --format ...` output (the package is installed at M6 by the fleet's own
scripts, prepared in `integration/`). On Windows it polls its few paths every 10 s
(roastery: `C:\purrbrews\restic\snapshots`).

## Consequences

- The dev plan's stack table no longer lists `watchfiles` (updated in the same commit).
- M6 adds `inotify-tools` to what the fleet installs on each Linux node.
- If kitten ever needs a non-stdlib library, this ADR is revisited, not worked around.
