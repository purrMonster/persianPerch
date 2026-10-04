# persianPerch — Development Plan

> Status: **draft for review** · 2026-09-29 · implements [02-design-plan.md](02-design-plan.md)

---

## 1. Stack

| Layer | Choice | Why |
|---|---|---|
| Language | **Python 3.12** | the fleet repo's tooling is already Python + bash; one language for perch and kitten |
| Web | **FastAPI** + **Jinja2** + **htmx** + SSE | server-rendered, no JS build step, fast on a phone |
| Store | **SQLite** (WAL, stdlib `sqlite3` behind a lock) | one file, backed up by groom like any app; enough for 90 days of events. *2026-09-30 (M0): `aiosqlite` dropped: a few writes per second don't need an async driver (runbook).* |
| Scheduling | `asyncio` tasks per sense with jittered rhythms | no Celery/cron inside the container |
| HTTP clients | `httpx2` (async) | Komodo, Gatus, Scrutiny, HA REST. *2026-10-01 (M1): was `httpx`, which the test image doesn't have and starlette deprecates for tests ([ADR 0002](adr/0002-httpx2-for-the-senses.md)).* |
| HA | `websockets` | whiskers' `state_changed` subscription |
| Files (kitten) | `inotifywait` (Debian `inotify-tools`) on Linux, polling on Windows; kitten is stdlib-only | *2026-09-30: was `watchfiles`, a compiled extension a zipapp can't carry ([ADR 0001](adr/0001-kitten-stdlib-zipapp.md), 05 plan C11, A5).* |
| Packaging | one container image for perch; kitten as a zipapp + systemd unit | kitten needs no Docker, so it runs on roastery-style hosts too |
| Tests | `pytest`, FastAPI's `TestClient` (`httpx2`), `respx`-style HTTP fakes, recorded fixtures shaped from public API docs; Playwright for the UI; all in containers (`scripts/test.ps1`) | every sense testable offline |

## 2. Repository layout (`persianPerch/`)

```
persianPerch/
├── docs/                      ideation, design plan, this plan, ADRs
├── mockups/                   static HTML mockups (this folder, today)
├── perch/                     the core service
│   ├── senses/
│   │   ├── purr.py            Komodo read API → container/node state
│   │   ├── glare.py           Gatus statuses → endpoint state
│   │   ├── binocs.py          tunnel, speedtest, upstream releases
│   │   ├── whiskers.py        Home Assistant WebSocket
│   │   ├── groom.py           backup records, copy ages
│   │   └── pounce.py          receives kitten events
│   ├── catTree.py             repo → fleet tree (git ls-files, node.conf, backup files)
│   ├── scentTrail.py          event store, state, rollups, retention
│   ├── rhythms.py             expected cadences, late/missing detection
│   ├── bodyLanguage.py        severity enum, worst-of rollup, icons/colours
│   ├── meow.py                alert routing, litters, quiet hours, ntfy/email
│   ├── nineLives.py           outside heartbeat
│   ├── scrub.py               secret scrubbing for log tails
│   ├── windowsill/            routes, templates, static (css, htmx)
│   └── settings.py            PERCH_* settings
├── kitten/                    the node agent
│   ├── kitten.py              pounce watchers, groom record shipping, heartbeat
│   └── kitten.service         systemd unit
├── tests/
├── Dockerfile
└── compose.example.yml        how purrbrews-containers will run it
```

## 3. Settings (`PERCH_*`)

| Variable | Default | Meaning |
|---|---|---|
| `PERCH_REPO_DIR` | `/opt/purrbrews` | read-only mount of the fleet repo checkout |
| `PERCH_TRAIL_DB` | `/data/scentTrail.db` | SQLite file |
| `PERCH_TRAIL_DAYS` | `90` | event retention; daily rollups kept 400 days |
| `PERCH_PURR_URL` / `_KEY` / `_SECRET` | — | Komodo Core read API |
| `PERCH_PURR_EVERY` | `30s` | purr rhythm |
| `PERCH_SLEEPERS` | `roastery` | nodes that sleep between their wake windows: unreachable outside the window is slowBlink, not hiss (05 plan C5; the window itself is read from the fleet repo) |
| `PERCH_GLARE_URL` / `_USER` / `_PASSWORD` | `https://gatus-api.${DOMAIN}` | Gatus on sieve through a `gatus-api` router with `forward-auth-basic` (05 plan Q12 = A); LLDAP service account `perch-svc` |
| `PERCH_WHISKERS_URL` / `_TOKEN` | — | Home Assistant on mochaPot, read-only user |
| `PERCH_WHISKERS_ENTITIES` | `whiskers.yml` | entity allow-list → bodyLanguage map |
| `PERCH_KITTEN_TOKEN_<NODE>` | — | one push token per node, roastery included (05 plan C10, A5); replaces `PERCH_KITTEN_TOKENS` |
| `PERCH_MEOW_NTFY_URL` / `_TOKEN` | — | ntfy topic on sieve |
| `PERCH_MEOW_QUIET` | `23:00-07:00` | quiet hours (hiss ignores them) |
| `PERCH_NINELIVES_URL` | — | healthchecks.io ping URL |
| `PERCH_ROLLUP_DAYS` | `400` | days of daily rollups (05 plan C10) |
| `PERCH_TZ` | `${TZ}` from `fleet.env` | how times are shown (05 plan C10) |
| `PERCH_DISKS_URL` | `http://scrutiny:8080` | Scrutiny on `cellar_net` (05 plan C6) |
| `PERCH_BINOCS_SPEEDTEST_URL` / `_TOKEN` | — | speedtest-tracker on grinder (05 plan C8) |
| `PERCH_BINOCS_RELEASES_EVERY` | `7d` | upstream release check |
| `PERCH_GROOM_DIR` | `/var/lib/purrbrews/groom` | cellar's own groom records, read-only (05 plan A10) |
| `PERCH_MEOW_CRITICAL_URL` | — | public ntfy.sh critical topic, hiss only (05 plan A7) |
| `PERCH_ACK_SECRET` | — | HMAC key for one-time acknowledge links (05 plan A11) |

The full list, with where each value comes from, is [`../secrets.env`](../secrets.env) (names only).

Kitten: `KITTEN_PERCH_URL`, `KITTEN_TOKEN`, `KITTEN_POUNCE_PATHS` (several separated by `;`, since Windows paths contain `:`), `KITTEN_GROOM_DIR`, `KITTEN_NODE` (defaults to the host name).

## 4. Milestones

Each milestone ends with something usable on the real fleet and a runbook entry.

### M0 — Litter (foundations) · ~2 days
- [ ] repo scaffolding, CI (lint, tests), Dockerfile, `compose.example.yml`
- [ ] `bodyLanguage`, `scentTrail` schema + migrations, retention job
- [ ] `catTree` from a copy of `purrbrews-containers` (fixture) — nodes, apps, docs
- [ ] windowsill skeleton: layout, nav, severity legend, dark/light
- **Done when:** the catTree renders every node and app from the repo, with no live data.

### M1 — First purr · ~3 days
- [ ] purr against Komodo's read API (recorded fixtures first, then the real one)
- [ ] rollup worst-of: app → node → fleet
- [ ] perch overview (mockup 01) and catTree app pages (mockup 02) with live state
- [ ] rhythms for purr; perch's own "collector late" events
- **Done when:** stopping a container on grinder turns its page, grinder and the fleet
  to hiss within 60 s, and starting it returns them to slowBlink.

### M2 — Grooming · ~3 days
- [ ] groom record format + a patch proposal for `purrbrews-containers` backup scripts
  (the only change the fleet repo needs for this milestone)
- [ ] kitten v0: ships groom records + heartbeat
- [ ] the grooming grid, copies panel, run details (mockup 03)
- [ ] rhythms for every backup job, derived from the repo
- **Done when:** a night with one node's backup disabled shows exactly that cell as hiss
  by 04:30, and nothing else.

### M3 — meow + nineLives · ~2 days
- [ ] ntfy routing, litters, dedupe, quiet hours, recovery messages, acknowledge
- [ ] nineLives to healthchecks.io
- **Done when:** unplugging grinder produces **one** push, and a recovery push after;
  stopping perch produces an outside alert within 10 min.

### M4 — glare + binocs + disks · ~2 days
- [ ] Gatus statuses into glare; Scrutiny summary into node pages (with the SanDisk
  hours quirk handled: prefer attribute 9 over the summary)
- [ ] binocs: tunnel, speedtest, upstream image releases
- **Done when:** the perch overview replaces opening Gatus and Scrutiny for a daily check.

### M5 — pounce + whiskers · ~3 days
- [ ] kitten pounce with the owner's path list, debounce, storm control
- [ ] whiskers over HA WebSocket with the entity map; reconnect/backoff
- [ ] scentTrail view with filters (mockup 04)
- **Done when:** dropping a PDF into Paperless' consume folder and opening a door sensor
  both show up in the trail within 5 s, with the right body language.

### M6 — Into the fleet · ~2 days
- [ ] `stacks/cellar/persian-perch/` in `purrbrews-containers`: compose, `secrets.conf`,
  `backup`, `firewall`, `data-dirs`, README; Authelia admin rule; Homepage tile
- [ ] kitten unit rolled out by `_lib`/`init` to every node *(as prepared: each node pulls the persianPerch repo and runs
  `integration/kitten/install-kitten.sh`; ADR 0012)*
- [ ] runbook entry; MAP updated
- **Done when:** it has run a full week on the fleet with no false hiss.

**Total:** roughly 17 working days of focused work, spread over as many weeks as it takes.
Each milestone is useful on its own; M0–M3 alone already answer "did everything run?".

## 5. Testing

| Level | What | How |
|---|---|---|
| Unit | rollups, rhythms, meow dedupe, scrub | pure functions, table-driven |
| Sense contract | each sense against recorded real responses | fixtures captured once from the fleet, values scrubbed |
| catTree | against a pinned copy of `purrbrews-containers` | asserts every `node.conf` app appears, no secret file is ever listed |
| UI | page renders, no JS errors, readable at 360 px | Playwright (Chromium is preinstalled in the build box) |
| Fleet drills | the "Done when" of each milestone | run by hand, written into the runbook |

**Security tests** that must always pass: catTree never lists `*.env.local` /
`secrets.env.local`; scrubbed log tails never contain a value from a fixture secrets file;
kitten push without a token → 401; from a non-fleet IP → blocked at the firewall.

## 6. Risks

| Risk | Mitigation |
|---|---|
| Komodo's API changes between versions | purr isolated behind one adapter; contract tests on the pinned Komodo version |
| Alert fatigue | tailFlick batched, quiet hours, litters; M6 requires a week without false hiss |
| perch becomes another thing to babysit | one container, SQLite, nineLives from outside, backed up by groom |
| Secrets leak into the UI | tracked-files-only catTree, deny-list, scrubber, tests |
| Scope creep into "actions" | parked in ideation §7; v1 has no write paths at all |

## 7. Decisions needed from the owner before M0

1. **Host:** cellar (recommended) or percolator.
2. **Hostname:** `perch.${DOMAIN}` — or another name.
3. **pounce paths:** confirm or edit the list in design plan §4.4.
4. **whiskers entities:** which HA entities matter, and which of them are hiss.
5. **Retention:** 90 days of events / 400 days of rollups — OK?
