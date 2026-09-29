# Build persianPerch, autonomously

You are building **persianPerch**, the purrBrews fleet's unified watcher, from its approved
plans to a working, tested v1. Work autonomously: make reasonable decisions, record them,
and keep going. Stop and ask only for the cases listed under "When to stop".

## 1. Where everything is

- **Project folder (your only write location):**
  `C:\Users\jyotirmoyc\Desktop\Projects\persianPerch` on the Windows workstation
  **roastery**. It already contains:
  - `README.md`: names at a glance
  - `docs/01-ideation.md`: purpose, senses, names, principles, parked ideas
  - `docs/02-design-plan.md`: architecture, data model, each sense, alerts, UI, security
  - `docs/03-dev-plan.md`: stack, layout, `PERCH_*` settings, milestones M0–M6, tests, risks
  - `mockups/*.html`: four UI mockups (perch overview, catTree, groom, scentTrail) + index

  **Read all of them before writing any code.** They are the spec. Where they're silent,
  decide, and write the decision down (see §6).
- **The fleet repo (read-only reference):** `purrbrews-containers`, public at
  `https://github.com/purrMonster/purrbrews-containers`. It defines the fleet's shape
  (`stacks/<node>/node.conf`, each app's `docker-compose.yml`, `backup`, `firewall`,
  `README.md`, `stacks/fleet.env`) that catTree must read. Clone it into a gitignored cache
  inside the project (e.g. `.cache/purrbrews-containers`) at a pinned commit for tests.
  Never modify it, never open a pull request against it.

## 2. Hard rules

1. **Write only inside the persianPerch folder.** Don't create, edit or delete files
   anywhere else on roastery (not the purrbrews-containers checkout, not other projects).
   Scratch files go in the project's gitignored `.cache/` or the OS temp dir.
2. **Don't touch the fleet.** No SSH to any node (sieve .10, percolator .11, cellar .12,
   mochaPot .13, grinder .14), no calls to Komodo, Gatus, Scrutiny, Home Assistant, ntfy or
   healthchecks.io, no deploys. Everything is built and tested against **fakes and recorded
   fixtures** shaped from each tool's public API docs. Wiring to the real fleet is the
   owner's M6 step, done later.
3. **No secrets, ever.** No real tokens, passwords, keys or the owner's real domain in any
   file. Use `${DOMAIN}` / `example.home.arpa` and obviously fake values in fixtures.
   catTree must never read `*.env.local`, `secrets.env.local`, keys or `authorized_keys`,
   even if one were tracked.
4. **Read-only product.** v1 never restarts, deletes or changes anything on the fleet
   ("actions" are parked in ideation §7). No write endpoints except kitten's event push.
5. **Git, locally.** `git init` the project folder if it isn't a repo yet, branch `main`.
   Commit in small, working steps with author `jyotirmoyc <jyotirmoy.github@jyotirmoy.cc>`.
   **Don't add a remote and don't push.** End every commit message with:
   ```
   Co-Authored-By: Claude <noreply@anthropic.com>
   ```
6. **Every PowerShell file is ASCII-only** (PowerShell 5 misreads UTF-8 without a BOM).
   Python and HTML may use UTF-8.

## 3. purrBrews taxonomy (use it for names, variables, headers, UI copy)

- App name: **persianPerch** (Breed + Feline Behavior). Folder and image: `persian-perch`.
- Watcher modules (senses): **purr** (containers, node vitals), **pounce** (filesystem
  events), **whiskers** (smart-home: Home Assistant WebSocket / MQTT), **glare** (endpoint
  uptime, TLS), **binocs** (far away: tunnel, speedtest, upstream releases).
- Added in the plans, same style: **perch** (core service), **windowsill** (web UI),
  **catTree** (repo-shaped directory view), **scentTrail** (event store + timeline),
  **groom** (backups), **kitten** (per-node agent), **meow** (alerts), **litter** (the events
  of one incident, alerted once), **nineLives** (outside heartbeat / dead-man's switch).
- Severity, "body language": **slowBlink** (OK/INFO), **earTwitch** (NOTICE), **tailFlick**
  (WARN), **hiss** (CRITICAL/ERROR). Worst-of rollup app → node → fleet. Each level has a
  colour *and* an icon and word (never colour alone): `·` sage `#6fa287`, `◦` blue
  `#6b8fb3`, `~` caramel `#d9953b`, `!` cherry `#c8453b`.
- Fleet names: nodes **sieve, percolator, cellar, mochaPot, grinder**, workstation
  **roastery**; the ops user is **barista**. VLANs (reference only): **espressoLane**,
  **catnipCorner**, **decaf**.
- Code style: Python modules and identifiers in camelCase where they name a purrBrews
  concept (`catTree.py`, `scentTrail.py`, `bodyLanguage.py`, `scentId`, `litterId`,
  `seenAt`); settings are `PERCH_*` / `KITTEN_*` env vars as in dev plan §3.

## 4. Decisions already made (don't ask about these)

The dev plan ends with five open questions. Use these answers:

1. **Host:** cellar (Debian 12, i3-7100T, 8 GB). Budget ≤ 300 MB RAM, < 2 % CPU at rest.
2. **Hostname:** `perch.${DOMAIN}`, behind Traefik + Authelia (group `admins`).
3. **pounce paths:** exactly the table in design plan §4.4, as the default config.
4. **whiskers:** ship `whiskers.example.yml` with generic entities (door/window sensors,
   water leak, smoke, pet feeder, water fountain level, UPS) and a sensible severity map
   (leak/smoke `on` → hiss; UPS on battery → tailFlick; doors, feeders → earTwitch).
5. **Retention:** 90 days of events, 400 days of daily rollups.

## 5. What to build

Follow **dev plan §4, milestones M0 → M5**, in order, each ending green before the next:

- **M0 Litter:** scaffolding, CI config (lint + tests; a GitHub Actions file is fine even
  without a remote), Dockerfile, `compose.example.yml`, `bodyLanguage`, `scentTrail`
  (SQLite WAL, migrations, retention), `catTree` from the pinned fleet repo, windowsill
  skeleton matching the mockups' look (dark default, light via `prefers-color-scheme`,
  single column under 700 px).
- **M1 First purr:** purr against a faked Komodo read API (model it on Komodo's documented
  `/read` endpoints; keep the adapter in one module), rollups, the overview and catTree app
  pages with live state, rhythms for collectors.
- **M2 Grooming:** the groom record format (JSON; fields in design plan §4.2), kitten v0
  (ships records + heartbeat to perch over HTTPS with a per-node bearer token), the
  groom grid, run details and copies panel, rhythms derived from the fleet repo's `backup`
  files and cellar's timers. Also write, but **don't apply**, the change the fleet's backup
  scripts would need to emit groom records: put it in `integration/` as a patch plus a
  short README (see M6 below).
- **M3 meow + nineLives:** ntfy routing (faked), litters, dedupe, quiet hours, recovery
  messages, acknowledge; nineLives pinging a faked healthchecks endpoint only when every
  collector is on time.
- **M4 glare + binocs + disks:** Gatus statuses (behind Authelia basic auth), Scrutiny
  summary (prefer SMART attribute 9 over the summary's power-on hours: the real fleet has a
  disk where the summary is wrong), binocs sources.
- **M5 pounce + whiskers:** kitten pounce with debounce and storm control; whiskers over a
  faked HA WebSocket (auth handshake, `subscribe_events`, reconnect with backoff); the
  scentTrail view with filters.
- **M6 Into the fleet: prepare only.** Don't deploy. In `integration/`, write what the owner
  would add to `purrbrews-containers` (`stacks/cellar/persian-perch/`: `docker-compose.yml`,
  `secrets.conf`, `backup`, `firewall`, `data-dirs`, `README.md`; the kitten systemd unit;
  the Authelia admin rule; a Homepage tile), following that repo's existing conventions,
  plus a step-by-step `integration/ROLLOUT.md` for the owner.

The UI must match the mockups' structure and visual language closely. Use the mockups' CSS
as the starting stylesheet.

## 6. How to work

- **Tests first where it's cheap.** Everything in dev plan §5, including the security
  tests: catTree never lists secret files; scrubbed log tails never contain a fixture
  secret; kitten push without a token → 401. Playwright screenshots of each page at
  1400 px (dark and light) and 390 px, with no horizontal scroll and no console errors.
- **Run everything.** Don't claim a milestone is done until its tests pass and you've
  started perch locally (Docker Desktop on roastery, or plain Python 3.12+) and loaded the
  pages. Paste real command output into the progress log, not a summary of it.
- **Keep a progress log** at `docs/progress.md`: dated entries, newest first, per
  milestone: what was built, what was verified and how, what's left, decisions made and
  why. This is the owner's runbook for this project.
- **Record design decisions** as short ADRs in `docs/adr/NNNN-title.md` when you choose
  between real alternatives (library, schema, protocol).
- **Update the plans** when reality differs: if the design plan is wrong, fix the doc in
  the same commit as the code and say so in the progress log.
- **Keep it boring:** one perch container, SQLite, no message broker, no Prometheus stack,
  no JS build step (htmx + SSE, server-rendered Jinja2).

## 7. When to stop and ask

Only stop for:

- something that would need writing outside the persianPerch folder, touching the fleet,
  a real credential, or pushing anywhere;
- a contradiction in the plans that changes the architecture (not a detail);
- a dependency that can't be installed on roastery at all.

Otherwise decide, record it, and continue.

## 8. When you finish

Finish with M5 green and M6 prepared, then report in `docs/progress.md` and in your final
message:

1. what works, per milestone, with the test counts and the commands that proved it;
2. screenshots' paths for each page;
3. anything stubbed, skipped or known to be weak;
4. exactly what the owner must do to deploy it (pointing at `integration/ROLLOUT.md`),
   including every credential they'll need to create and at which source.
