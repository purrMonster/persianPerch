# persianPerch Runbook

Dated decisions and changes for persianPerch, newest first. Each entry records *why*, so
changes can be made later without re-deriving the reasoning. How to write entries:
[AGENTS.md §4](AGENTS.md#4-the-runbook-runbookmd).

## In progress

- (nobody)

## Backlog / open items

- [x] Owner decisions before M0 (dev plan §7): host, hostname, pounce paths, whiskers entities, retention. Defaults in `docs/04-build-prompt.md` §4, pounce paths corrected by `docs/05-autonomous-build-plan.md` C2 (2026-09-30 entry)
- [x] Repo: public GitHub `purrMonster/persianPerch`, secret scanning and push protection on (owner); the agent pushes after each green milestone, then stops for the owner's go-ahead (05 plan A2, 2026-09-30 entry)
- [x] Build-plan questions Q1–Q16 answered by the owner in chat (05 plan §1, 2026-09-30)
- [ ] The build (Cowork): baseline commit (05 plan A1), pre-flight incl. A3, then M0
- [ ] Restore roastery's sleep setting after M6-prep (owner; 05 plan A4)
- [ ] M0 Litter: scaffolding, scentTrail, catTree, windowsill skeleton
- [ ] M1 First purr: containers and vitals via Komodo's read API (faked), rollups, overview and catTree pages
- [ ] M2 Grooming: groom records, kitten v0, the backup grid; fleet-script change prepared in `integration/`
- [ ] M3 meow + nineLives: alerts, litters, quiet hours, outside heartbeat
- [ ] M4 glare + binocs + disks: Gatus, Scrutiny, tunnel, speedtest, upstream releases
- [ ] M5 pounce + whiskers: kitten file events, Home Assistant, the scentTrail view
- [ ] M6 Into the fleet: prepared in `integration/` with `ROLLOUT.md`; deployed by the owner

---

## 2026-09-30 — Autonomous build plan, owner's answers, secrets.env

**Context.** The owner asked for a foolproof plan to build persianPerch autonomously, every
question asked up front, commands for any value that lives in a node's env, a `secrets.env`
for every value the build needs from the fleet, and links (not copies) for anything in
`purrbrews-containers`.

**Decided.**
- **`docs/05-autonomous-build-plan.md`** now sits above `04-build-prompt.md` for the build.
  It holds the owner's answers (§1, Q1–Q16), what they change (§1a, A1–A11), fifteen
  corrections to the spec found by reading the fleet repo at `f94efdfb` (§2, C1–C15), the
  environment, the session protocol, a fixtures-based gate per milestone and the tests that
  must always pass (S1–S9).
- **Owner's answers:** baseline commit yes; the agent pushes after each green milestone and
  stops for a go-ahead (secret scanning + push protection confirmed on); Cowork builds;
  containers-only toolchain; roastery kept awake during the build; acknowledge from the page
  **and** from an ntfy button via signed single-use links (A11, chosen after the trade-offs
  were explained); a Windows kitten on roastery (A5); meow pushes everything, and only the
  duplicate alerts are retired after M6's week, never Gatus's critical layer or sieve's
  heartbeat (A6); hiss also to ntfy.sh; Gatus via the ollama Basic-auth pattern; groom
  records from an `ExecStopPost=` recorder; a non-admin HA user with a test that perch never
  sends a control command. Nodes: Python 3.13.5 on Debian 13.7. cellar's
  `/var/lib/purrbrews/` holds only `drive-sync.ok`, so every groom record is new.
- **`secrets.env`** lists every setting with its source, its `secrets.conf` verb and how to
  get the value, but **no values**: this repo is public, and the fleet's own
  `setup-secrets.sh` enters them on cellar at deploy time. Test S5 keeps it empty.
- Why corrections instead of new questions: each fixes a spec detail that would have failed
  silently (kitten push blocked by Authelia, Gatus refusing Basic auth, `.git/HEAD` never
  changing on a pull, four backup timers with no rhythm) and has one obvious fix.

**Done.** Added `docs/05-autonomous-build-plan.md` and `secrets.env`; Backlog updated
above. Nothing committed: the baseline commit is the build's first step (A1), and
`README.md`, `docs/04-build-prompt.md`, `AGENTS.md`, `CLAUDE.md` and this file were
already uncommitted.

**Verified.**
- The fleet repo was read at `f94efdfb1995d7217ec2be33e45b33720a0a0b3b` (2026-09-30); all
  links in the plan point at files that exist there.
- `secrets.env`: 36 keys, every value empty, ASCII-only (checked with grep before writing).
- Project state read with `git status`: branch `main` tracking `origin/main`, one commit
  `2f6fafc first push`; Python 3.14.7 and Docker 29.7.2 on roastery.

**Not done / next.**
- [ ] Cowork: read 05, run the pre-flight (A3: `docker info`, `git ls-remote origin`), make
  the baseline commit, then M0 (agent)
- [ ] After M6-prep: restore roastery's sleep setting (owner)

— Claude (chat, Opus 5.5), for the owner

## 2026-09-29 — Project started: plans, mockups, agent rules

**Context.** While setting up the fleet's backups, the owner asked for a page to see backup
runs and their history, then widened it: every service's status, in a pretty, private,
repo-shaped directory view. He made it its own project, **persianPerch**, the "Unified
Watcher" in the purrBrews taxonomy (Breed + Feline Behavior), with the senses **purr,
pounce, whiskers, glare/binocs** and body-language severity **slowBlink, earTwitch,
tailFlick, hiss** already defined. Work on it lives only in this folder.

**Decided.**
- **Watch, don't drive:** v1 is read-only. Actions are parked (ideation §7): they need
  their own safety design.
- **Repo-shaped:** the fleet's structure is read from `purrbrews-containers` itself, so
  there's no second inventory to keep in sync.
- **Read through existing doors:** Komodo's read API, Gatus, Scrutiny, Home Assistant with a
  read-only user. No docker group, root or SSH on the nodes.
- **Boring stack:** one Python container (FastAPI, Jinja2 + htmx, SSE), SQLite. Not
  Prometheus + Grafana + Loki: four services and dashboards that don't know the repo.
- **Runs on cellar** (proposed), behind Traefik + Authelia (admins), `perch.${DOMAIN}`.
- **Watch the watcher:** nineLives pings healthchecks.io from inside, so an outside service
  notices if perch or cellar goes quiet.
- Names added in the same style: perch, windowsill, catTree, scentTrail, groom, kitten,
  meow, litter, nineLives.

**Done.** `README.md`, `CLAUDE.md` (project context), `AGENTS.md` (rules for every agent),
this runbook, `docs/01-ideation.md`, `docs/02-design-plan.md`, `docs/03-dev-plan.md`,
`docs/04-build-prompt.md` (brief for an autonomous build), and `mockups/` (index + four
views: perch overview, catTree, groom, scentTrail).

**Verified.** Mockups rendered in Chromium at 1400 px (dark and light) and 390 px: no page
wider than the viewport, no script errors.

**Not done / next.**
- [ ] The owner's decisions in the Backlog (host, hostname, paths, entities, retention; repo)
- [ ] The build, M0 → M5, then M6 prepared (an agent, following `docs/04-build-prompt.md`)

— Claude (Cowork), for the owner
