# ADR 0002 — perch reads other services with `httpx2`

- Status: accepted · 2026-10-01 · M1
- Context: dev plan 1 ("HTTP clients: `httpx` (async)"); runbook 2026-09-30 (M0 entry), which
  moved the tests to `httpx2` because starlette 1.7 deprecates `httpx` for its `TestClient`.

## Context

purr (Komodo) needs an HTTP client at runtime, and glare (Gatus), binocs (speedtest-tracker,
GitHub releases) and meow (ntfy) will follow. The dev plan named `httpx`. Since then
`httpx2` (package metadata: "The next generation HTTP client", home page
`github.com/pydantic/httpx2`, author Tom Christie, who also wrote `httpx`) is what starlette's
`TestClient` now uses, so the test image already installs it and `httpx` itself is not
installed (checked in the test image, 2026-10-01).

## Options

| Option | For | Against |
|---|---|---|
| **A. `httpx2` (pinned 2.13.1)** | async, timeouts, `MockTransport` for fakes; the very version the tests already pin and starlette needs, so the test fakes exercise the production client; no second HTTP library | a newer package than `httpx`; adds `httpcore2`, `truststore` and `anyio` (already there via starlette) |
| B. `httpx` | what the dev plan said | not installed; starlette deprecates it for tests, so both libraries would be pinned side by side |
| C. stdlib `urllib` in worker threads | no dependency | no async, no connection reuse, timeouts and error mapping by hand, and no transport to fake: every sense test would need a real socket |

## Decision

**A.** `httpx2==2.13.1` moves from `requirements-dev.txt` to `requirements.txt` (the dev
file inherits it with `-r`). The senses take an optional `transport` so tests hand them an
`httpx2.MockTransport` serving fixtures; nothing in the tests opens a socket.

## Consequences

- The Docker image gains httpx2 and its dependencies `httpcore2`, `idna`, `truststore` (and
  `anyio`, which starlette already brings). Size is measured at the gate (the image's
  memory is what the 300 MB budget cares about; the runbook records it).
- Dev plan 1 reads `httpx2` where it said `httpx`.
- The Komodo adapter is the only module that builds a Komodo request (`perch/senses/komodo.py`);
  each later sense gets the same shape: one adapter module, one fixture folder.
