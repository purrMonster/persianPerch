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
| purr collector | every 30 s | 3 misses | 10 misses |
| kitten heartbeat | every 60 s | 3 min | 10 min |
| glare check | per Gatus interval | 2 fails | 5 fails |

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
- Expected jobs come from the repo (`backup` files + cellar's timers), so a new app's
  backup appears on the grid without configuration.
- Also tracks the **copies**: newest snapshot per host, repo size, Drive copy age
  (`drive-sync.ok`), last restore test, offline HDD's last sync, flask's last `-Check`.

### 4.3 glare (endpoints)

- **v1:** reads Gatus' `/api/v1/endpoints/statuses` from sieve, so there's one source of
  truth for uptime. Gatus publishes no port (it's behind sieve's Traefik and Authelia), so
  perch signs in as an LLDAP service account through Authelia's existing basic-auth
  endpoint (`forward-auth-basic`), read-only by what Gatus exposes. **Later:** own checks for TLS expiry and response time.

### 4.4 pounce (filesystem)

- **kitten** runs `fsnotify` on a short, explicit list per node (owner to confirm):

| Node | Path | Why | Event |
|---|---|---|---|
| cellar | `/srv/dumps/*/` | a node's dumps arrived | earTwitch; none by 03:00 → handled by groom |
| percolator | `/srv/data/paperless/consume/` | a document dropped | earTwitch |
| every node | `/etc/purrbrews/` | settings changed | tailFlick (unexpected outside a deploy) |
| every node | `/opt/purrbrews/.git/HEAD` | the node pulled a new commit | earTwitch, with the commit subject |

- Debounced (2 s), rate-limited (max 60 events/min per path, then one "storm" tailFlick).

### 4.5 whiskers (smart-home)

- **Source:** Home Assistant WebSocket API on mochaPot, a dedicated **read-only HA user**
  with a long-lived token. Subscribes to `state_changed` for an allow-list of entities
  (door sensors, feeders, water, smoke/leak, UPS if any).
- Entity → severity map in config (a leak sensor `on` is hiss; a door opening is earTwitch).
- Later: MQTT on catnipCorner, if a broker is added.

### 4.6 binocs (far away)

- Cloudflare tunnel health (from cloudflared metrics), speedtest-tracker's last result,
  new upstream releases of pinned images (weekly; earTwitch, never hiss).

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
