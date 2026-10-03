# ADR 0009 - whiskers adds two dependencies: `websockets` and `PyYAML`

- Status: accepted - 2026-10-03 - M5
- Context: design plan 4.5, 05 plan Q14 and test S4, 04 build prompt section 4 (`whiskers.example.yml`), AGENTS.md section 3 ("no new dependency unless unavoidable, justified").

## Context

Home Assistant offers its live state only over a WebSocket (`/api/websocket`), and the build prompt asks for a YAML
entity list. Nothing in perch's stack (FastAPI, Jinja2, httpx2, SQLite) speaks WebSocket client or reads YAML.
uvicorn is installed without its optional WebSocket library.

## Options

| For the WebSocket | For | Against |
|---|---|---|
| **A. `websockets` 17.1** | BSD-3-Clause; the library uvicorn itself uses for WebSockets; asyncio client and server (the fake Home Assistant in the tests is a real one on loopback); keep-alive ping frames built in; pure Python fallback, wheels for 3.12 | one more package |
| B. a hand-written RFC 6455 client | no dependency | frame masking, fragmentation, ping/pong and close are exactly what a watcher must not get subtly wrong; and the tests would need a hand-written server too |
| C. `aiohttp` | also has a WebSocket client | a whole second HTTP stack beside httpx2 |
| D. Home Assistant's REST API polled | no WebSocket | `GET /api/states` every few seconds is the wrong shape for events, and S4's three allowed message types are the WebSocket API's |

| For the entity list | For | Against |
|---|---|---|
| **A. `PyYAML` 6.0.3, `safe_load` only** | MIT; the format 04 section 4 names; every Home Assistant owner already writes YAML | one more package; YAML 1.1 reads a bare `on` or `off` as a boolean (perch maps both back to the words, and the example quotes them) |
| B. TOML (`tomllib`, standard library) | no dependency | not what 04 asks for; the owner edits Home Assistant's YAML all day |
| C. a hand-parsed YAML subset | no dependency | a parser nobody can trust for a file that decides what pages the owner |

## Decision

**A and A**, pinned in `requirements.txt` (`websockets==17.1`, `PyYAML==6.0.3`). Checked 2026-10-03 on PyPI: both
current, licences BSD-3-Clause and MIT, `websockets` needs Python 3.11 or newer. `yaml.safe_load` only: the file can
never construct an object. Neither is imported unless whiskers is configured (`websockets` is imported inside
`connectDefault`; `yaml` is read only when an entity list is loaded).

## Consequences

- The test image and perch's image gain two small packages; kitten is unchanged (ADR 0001: stdlib only).
- whiskers never sends anything but `auth`, `subscribe_events` and `get_states` (S4): one function writes to the
  socket and refuses everything else, and the test fake records what it receives. The WebSocket protocol's own ping
  frames keep the connection honest; they are not Home Assistant messages.
- The Home Assistant token is never in a log, a page, an event or an error: `scrub.py` masks the exact value and the
  shape of any JWT, and the real-socket drill's leak check looks for it.
