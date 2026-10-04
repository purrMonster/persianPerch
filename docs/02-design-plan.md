# persianPerch — Design Plan

> Status: **draft for review** · 2026-09-29 · reads with [01-ideation.md](01-ideation.md)
> and [03-dev-plan.md](03-dev-plan.md). Mockups: [../mockups/index.html](../mockups/index.html).

---

## 1. Scope

**v1 watches:** containers and node vitals (purr), backups (groom), endpoints (glare),
disks (via Scrutiny), filesystem drops on chosen paths (pounce), Home Assistant state
changes (whiskers). It **shows** all of it in a repo-shaped UI (windowsill / catTree),
keeps 90 days of history (scentTrail), and **alerts** through ntfy (meow).

**v1 does not:** act on anything, ship full logs, replace Komodo/Gatus/Scrutiny (it reads
them), or expose anything outside Authelia.

## 2. Architecture

```
            ┌──────────────────────── cellar (192.168.0.12) ────────────────────────┐
            │  perch  (one container)                                              │
            │                                                                      │
 Komodo ───►│  purr ─────┐                                                         │
 Gatus  ───►│  glare ────┤                                                         │
 Scrutiny ─►│  (disks) ──┤     ┌────────────┐    ┌───────────┐   ┌──────────────┐  │
 HA (WS) ──►│  whiskers ─┼───► │  rules /   │──► │ scentTrail│──►│ windowsill   │──┼─► Traefik + Authelia
 binocs ───►│  binocs ───┤     │  rhythms   │    │ (SQLite)  │   │ (web UI+SSE) │  │   perch.${DOMAIN}
 groom ────►│  groom ────┤     └─────┬──────┘    └───────────┘   └──────────────┘  │
            │  pounce ◄──┘ (events   │                                             │
            │            from kitten)└──► meow ──► ntfy (sieve) / email           │
            │                                                                      │
            │  catTree ◄── git: /opt/purrbrews (tracked files only)                │
            │  nineLives ──► healthchecks.io (outside the house) every 5 min       │
            └──────────────────────────────────────────────────────────────────────┘
                 ▲ HTTPS POST (token), LAN only
   kitten on sieve · percolator · mochaPot · grinder · roastery   (pounce + groom records)
```

### 2.1 Where it runs

**cellar**: always on, already the ops hub (Komodo Core, Scrutiny hub, the dump store,
the backup timers), and on espressoLane once VLANs exist. perch is small: one Python
process, SQLite, a few MB of RAM per watched thing. Budget: **≤ 300 MB RAM, < 2 % CPU**
at rest on the i3-7100T.

### 2.2 Components

| Component | Name | Kind | Responsibility |
|---|---|---|---|
| Core service | **perch** | container on cellar | runs the collectors on their rhythms, evaluates rules, writes scentTrail, serves windowsill |
| Collectors | **purr / glare / binocs / whiskers / groom** | modules inside perch | each turns one source into normalized events and current state |
| Node agent | **kitten** | small systemd service per node | pounce (fsnotify) and groom records; pushes to perch |
| Event store | **scentTrail** | SQLite (WAL) in `/srv/data/persian-perch` | events, current state, rollups |
| Web UI | **windowsill** | server-rendered HTML + htmx + SSE | catTree, timelines, the grooming grid |
| Alerts | **meow** | module inside perch | severity → channel, dedupe, escalation, quiet hours |
| Heartbeat | **nineLives** | module inside perch | pings healthchecks.io only when every collector ran on time |

### 2.3 Why not Prometheus + Grafana + Loki

They'd do most of it, at the cost of four services, a query language and dashboards that
don't know the repo's shape. The unique value here is *repo-shaped* + *expected rhythms*
+ *one timeline*; that's a few thousand lines of focused code, not a stack. If metrics
ever outgrow SQLite, purr can export Prometheus format later without changing the UI.

## 3. Data model

### 3.1 The fleet tree (catTree)

Built on every refresh from the repo checkout at `/opt/purrbrews` (tracked files only):

```
fleet
├── node: sieve        ← stacks/sieve/node.conf  (APPS order, role line from README)
│   ├── app: pihole    ← stacks/sieve/pihole/    (docker-compose.yml, backup, firewall, data-dirs, README)
│   └── …
├── node: roastery     ← stacks/roastery/ (Windows; purr via Komodo periphery only)
├── docs               ← README.md, runbook.md, docs/*.md
└── groom              ← every node's `backup` files → the expected backup jobs
```

Every node/app has a stable id: `node:percolator`, `app:percolator/authelia`,
`job:groom/percolator/nightly`, `path:cellar:/srv/dumps`.

### 3.2 Events (scentTrail)

| Field | Type | Example |
|---|---|---|
| `scentId` | ULID | `01J9…` |
| `seenAt` | UTC timestamp | `2026-09-29T00:41:07Z` |
| `sense` | enum | `purr`, `pounce`, `whiskers`, `glare`, `binocs`, `groom`, `perch` |
| `subject` | id | `app:grinder/n8n` |
| `bodyLanguage` | enum | `slowBlink`, `earTwitch`, `tailFlick`, `hiss` |
| `title` | text | `n8n restarted (exit 137, OOM)` |
| `detail` | JSON | `{"restarts": 3, "memLimitMb": 1024}` |
| `logTail` | text, ≤ 16 KB | last lines, **secret-scrubbed** |
| `litterId` | text | groups events of one incident, for meow dedupe |

### 3.3 Current state

One row per subject: `bodyLanguage`, `since`, `lastSeenAt`, `expectedRhythm`,
`nextExpectedAt`. **Rolled up**: a node's state is the worst of its apps; the fleet's is
the worst of its nodes.

### 3.4 Rhythms (silence is a signal)

Every watched thing declares when it's next expected. Missing it is an event:

| Subject | Rhythm | Late → tailFlick | Missing → hiss |
|---|---|---|---|
| groom nightly per node | daily 01:30 | +45 min | +3 h |
| groom store (cellar) | daily 02:30 | +45 min | +3 h |
| groom Drive sync | daily 03:30 | +2 h | +8 h |
| groom wake-roastery, morning check, restic prune, restore check (M2 addendum) | from the repo's timers: 01:25, 06:00, Sun 03:00, the 1st 04:30 | +45 min, +1 h, +3 h, +3 h | +3 h, +3 h, +12 h, +12 h |
| purr collector | every 30 s | 3 misses | 10 misses |
| kitten heartbeat | every 60 s | 3 min | 10 min |
| glare check | per Gatus interval | 2 fails | 5 fails |

### 3.5 Vitals history (addendum, owner's decision 2026-10-02; built in M4)

The first plan had no metrics store, so the overview mockup's sparklines had nowhere to come
from (found in M1). It stays one SQLite file, not a time-series database (§2.3 still holds).

| Table | Row | Kept |
|---|---|---|
| `vitals5m` | node, 5-minute bucket start, CPU %, RAM %, root-disk % (each the bucket's average, plus max for disk) | 7 days |
| `vitalsHour` | node, hour start, the same averages and the hour's max | 400 days (same as event rollups) |

- **Written by purr** from the `ListServers` stats it already reads every 30 s: samples are
  averaged in memory and one row per node is written per 5 minutes; the hourly job rolls
  5-minute rows up and deletes what has aged out. No raw 30 s rows are stored.
- **Size:** at 6 nodes, at most ~12,100 five-minute rows and ~57,600 hourly rows: a few MB.
- **Shown as** sparklines on the overview's node cards (24 h, from `vitals5m`) and on node
  pages (7 days from `vitals5m`, 90 days from `vitalsHour`), drawn on the server as inline
  SVG in `--muted`, with a text alternative ("RAM 24 h: 41-63 %, now 58 %"). Colour still
  means state only (`docs/06-design-system.md` §2): a sparkline never turns red; a breached
  threshold shows as the usual badge.
- **Unlocks later:** "sustained" CPU/RAM rules (e.g. RAM > 90 % for 15 min), which M1 left
  out because there was no history. Not part of M4 unless the owner asks.
- A gap (Komodo down, perch stopped) is a gap in the line, never interpolated.
- *Built in M4 (2026-10-03, [ADR 0008](adr/0008-vitals-history-tables.md)):* both tables keep the highest reading of CPU,
  RAM and disk (the plan said disk only); the sparkline scale is fixed 0 to 100 %; the sparklines sit under the three
  meters (docs/06 6).

## 4. The senses in detail

### 4.1 purr (containers, node vitals)

- **Source:** Komodo Core read API (`/read`, a read-only API key/secret): servers, stacks,
  containers, their state/health/restart count, image and tag; server stats (CPU, RAM,
  disk, load).
- **Every 30 s.** No Docker socket, no docker group, no SSH.
- **Rules:** container `exited`/`unhealthy` → hiss; restart count up → tailFlick (3 in
  15 min → hiss); disk > 85 % → tailFlick, > 95 % → hiss; node not reporting → hiss.
- **roastery** is watched too (its periphery), but marked *sleeps*: unreachable between
  its wake windows is slowBlink, not hiss.

### 4.2 groom (backups)

- **Source:** each job writes a record at the end of its run
  (`/var/lib/purrbrews/groom/<job>/<start>.json`: times, result, restic summary, log tail).
  kitten sends it to perch; cellar's own jobs are read directly.
- **Record schema 1 (M2):** `{"schema":1,"job","node","unit","start","end","result","exitStatus","logTail"}`
  with `job` one of `nightly|wake|store|drive|check|prune|verify` and `result` systemd's
  `$SERVICE_RESULT`; defined by `parseRecord` in `perch/senses/groom.py`, written by
  `integration/groom/groom-record.py` from each unit's `ExecStopPost=` (the log tail is the journal's
  last 40 lines, at most 16 KB, scrubbed by perch). A run counts for the latest expected start it
  began at or after (15 min of clock skew allowed) within 12 h, so an afternoon manual run is not
  last night's backup; a good run later than the late limit is earTwitch, a failed one hiss.
  Nights from before perch first looked, and nodes whose kitten has no token, aren't judged: no
  false hiss on a fresh deploy.
- **kitten's report (M2):** `POST /api/kitten` every 60 s with the node's bearer token: a heartbeat
  (`version`, `sentAt`, and the mtimes of `*.ok` stamp files such as `drive-sync.ok`) and the
  records it hasn't had acknowledged. The Drive copy's age comes from that stamp.
- Expected jobs come from the repo (`backup` files + cellar's timers), so a new app's
  backup appears on the grid without configuration.
- Also tracks the **copies**: newest snapshot per host, repo size, Drive copy age
  (`drive-sync.ok`), last restore test, offline HDD's last sync, flask's last `-Check`.

### 4.3 glare (endpoints)

- **v1:** reads Gatus' `/api/v1/endpoints/statuses` from sieve, so there's one source of
  truth for uptime. Gatus publishes no port (it's behind sieve's Traefik and Authelia), so
  perch signs in as an LLDAP service account through Authelia's existing basic-auth
  endpoint (`forward-auth-basic`), read-only by what Gatus exposes. **Later:** own checks for TLS expiry and response time.
- *Built in M4 (2026-10-03):* one `GET /api/v1/endpoints/statuses?page=1&pageSize=20` a minute (Gatus v5.36.0; `page` and
  `pageSize` page each endpoint's *results*). Uptime is not in that JSON, so glare judges the newest results itself: a
  failure streak of 2 is tailFlick, 5 is hiss, an endpoint Gatus stopped checking is unknown, and Gatus unreachable is
  unknown plus one tailFlick ("glare is late: can't see Gatus"), never a hiss per endpoint.

### 4.4 pounce (filesystem)

- **kitten** runs `fsnotify` on a short, explicit list per node (owner to confirm):

| Node | Path | Why | Event |
|---|---|---|---|
| cellar | `/srv/dumps/*/` | a node's dumps arrived | earTwitch; none by 03:00 → handled by groom |
| percolator | `/srv/data/paperless/consume/` | a document dropped | earTwitch |
| every node | `/etc/purrbrews/` | settings changed | tailFlick on the page and trail; **morning digest only, never an immediate push** (owner, 2026-10-03: only he changes these files, and perch can't tell a deploy from a surprise) |
| every node | `/opt/purrbrews/.git/HEAD` | the node pulled a new commit | earTwitch, with the commit subject |

- Debounced (2 s), rate-limited (max 60 events/min per path, then one "storm" tailFlick).

**M5 addendum (2026-10-03; 05 plan A5 and C2 win where they differ).** The last row watches the branch's ref
(`.git/refs/heads/main`) and `packed-refs`, not `.git/HEAD` (C2). roastery polls `C:\purrbrews\restic\snapshots`
every 10 s. kitten reports names and change types only and never opens a watched file; the pull event's commit
subject is asked of `git`. Events travel in the kitten report, as events (not states), so meow does not push them
yet. Details and the one open owner question: [ADR 0010](adr/0010-pounce-names-only-events-over-the-kitten-report.md).

### 4.5 whiskers (smart-home)

- **Source:** Home Assistant WebSocket API on mochaPot, a dedicated **read-only HA user**
  with a long-lived token. Subscribes to `state_changed` for an allow-list of entities
  (door sensors, feeders, water, smoke/leak, UPS if any).
- Entity → severity map in config (a leak sensor `on` is hiss; a door opening is earTwitch).
- Later: MQTT on catnipCorner, if a broker is added.

**M5 addendum (2026-10-03).** The map lives in `whiskers.example.yml` (`states` and `words` per entity, a `default`
level, an allow-list: everything else is dropped before it is stored). Each listed entity is a state
`whiskers:<entity_id>`; a change worth knowing is an event; a hiss or tailFlick from the house moves the fleet and
meow pushes it, a notice (a door) is for the trail only. Home Assistant unreachable is one tailFlick from
the collector's rhythm and every entity `unknown`, never a hiss per entity, **and whiskers itself never hisses
(owner, 2026-10-03)**: purr (its container) and glare (its endpoint) already hiss when Home Assistant is down, so a third
hiss would double-alert one outage. perch sends only `auth`,
`subscribe_events` and `get_states` (S4). [ADR 0009](adr/0009-whiskers-websockets-and-pyyaml.md).

### 4.6 binocs (far away)

- Cloudflare tunnel health (from cloudflared metrics), speedtest-tracker's last result,
  new upstream releases of pinned images (weekly; earTwitch, never hiss).
- *As built in M4 (2026-10-03):* the tunnel is Gatus's own `/ready` check (05 plan C7), shown from the glare state;
  speedtest is the newest result of speedtest-tracker v1.15.0 (earTwitch at most); releases go through the registries'
  OCI API, only when `PERCH_BINOCS_RELEASES_EVERY` is set ([ADR 0007](adr/0007-binocs-releases-through-the-oci-registry-api.md)).

## 5. meow (alerts)

| bodyLanguage | Channel | Timing | Repeat |
|---|---|---|---|
| hiss | ntfy, priority high (+ email) | immediately | every 30 min until acknowledged or cleared |
| tailFlick | ntfy, default | batched for 5 min | once per litter per 6 h |
| earTwitch | none; morning digest (optional) | 07:30 | — |
| slowBlink | none | — | — |

- **Dedupe by litter:** a dead node makes its 12 containers hiss; meow sends **one**
  push ("grinder unreachable — 12 apps affected").
- **Quiet hours** (23:00–07:00): tailFlick waits for the digest; hiss always goes through.
- **Recovery** is announced once ("grinder back — was down 14 min").
- Acknowledge from the page or by replying via ntfy action button.

**M3 addendum (2026-10-02; the 05 plan's answers win where they differ).** There is no email channel: hiss
goes to the self-hosted ntfy (priority high) **and** the ntfy.sh critical topic (A7). "Replying via ntfy
action button" is A11's signed, single-use `POST /ack/t/{token}` button, on the self-hosted copy only
([ADR 0006](adr/0006-push-ack-token.md)); the page's Acknowledge has CSRF protection
([ADR 0005](adr/0005-page-acknowledge-csrf.md)). Litters, absorption of a down node's apps, the digest, the
6 h reminder reading and the rate-limit reservation (a hiss may use 9 of the 10 slots, everything else 7, the
10th is the "N alerts held back" summary) are in [ADR 0004](adr/0004-litters-and-node-absorption.md). Every
meow title starts `perch:` (A6). nineLives pings only while every collector is on time (section 8).

## 6. windowsill (UI)

Server-rendered pages (fast on a phone, no build step), htmx for partial refresh, SSE for
the live scentTrail. Four primary views, each with a mockup:

| View | Route | Mockup | Answers |
|---|---|---|---|
| **perch** (overview) | `/` | `01-perch-overview.html` | Is anything hissing? What happened overnight? |
| **catTree** | `/tree/{node}/{app}` | `02-cat-tree.html` | What is this thing, how is it, where's its config? |
| **groom** | `/groom` | `03-groom-backups.html` | Did every backup run, and where are the copies? |
| **scentTrail** | `/trail` | `04-scent-trail.html` | What happened, in order, filterable by sense/severity? |

### 6.1 Visual language

- **Palette:** espresso (#2b1d16) and crema (#f4ead9) surfaces; severity colours mapped
  to body language: slowBlink = sage `#6fa287`, earTwitch = steamed-milk blue `#6b8fb3`,
  tailFlick = caramel `#d9953b`, hiss = cherry `#c8453b`. Dark by default, light follows
  the system.
- **Severity is never colour alone:** each level has an icon and a word
  (· slowBlink, ◦ earTwitch, ~ tailFlick, ! hiss).
- **Density:** built for a laptop glance and a phone check; every table collapses to cards
  under 700 px.
- **Words:** the purrBrews names are used in navigation and badges, with the plain meaning
  on hover and in the legend, so the page stays readable to someone new.

## 7. Security

- **Access:** Traefik on cellar → Authelia `forward-auth`, group `admins`. Over Tailscale
  away from home. No public route (not on the Cloudflare tunnel).
- **Credentials perch holds** (in `secrets.env.local`, never in the repo): Komodo read
  key/secret, HA read-only token, kitten push tokens (one per node), ntfy token,
  healthchecks.io ping URL. Each is **read-only** at its source.
- **catTree never reads secrets:** file listing comes from `git ls-files`; a deny-list
  (`*.env.local`, `secrets.env.local`, `*.key`, `authorized_keys`) is enforced even if
  such a file were ever tracked.
- **Log tails are scrubbed** before storage: values of known secret keys (by name pattern
  `*_PASSWORD`, `*_TOKEN`, `*_SECRET`, `*_KEY`) and anything that looks like a bearer token.
- **kitten → perch:** HTTPS to cellar's Traefik on the LAN, per-node bearer token,
  firewall: only the node IPs (from `fleet.env`) may reach the push endpoint.

## 8. Failure modes

| If… | Then… |
|---|---|
| Komodo Core is down | purr shows *unknown* (grey), one tailFlick "purr can't see containers"; other senses continue |
| a kitten dies | its heartbeat goes late → tailFlick → hiss after 10 min |
| perch dies or cellar dies | nineLives stops pinging → healthchecks.io emails/pushes from outside |
| SQLite corrupts | perch starts with an empty trail and says so (hiss); scentTrail is backed up nightly by groom like any app |
| an alert storm | meow's litter grouping + per-channel rate limit (max 10 pushes / 10 min) |

## 9. Fit with purrbrews-containers

persianPerch is its **own repo**. It lands in the fleet the usual way later:
`stacks/cellar/persian-perch/` (compose, `secrets.conf`, `backup`, `firewall`,
`data-dirs`) and a `kitten` unit shipped by `init`/`_lib`. Nothing in this plan requires
changing the fleet repo until the dev plan's integration phase.
