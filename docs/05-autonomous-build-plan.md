# persianPerch — Autonomous Build Plan

> Status: **all questions answered (2026-09-30); ready for the build** · 2026-09-30 · executes
> [04-build-prompt.md](04-build-prompt.md) on the spec in [01](01-ideation.md),
> [02](02-design-plan.md), [03](03-dev-plan.md) and [../mockups/](../mockups/index.html).
>
> Fleet references are links to [`purrbrews-containers`](https://github.com/purrMonster/purrbrews-containers)
> `main`, never copies. Tests pin commit `f94efdfb1995d7217ec2be33e45b33720a0a0b3b`
> (2026-09-30). Every setting perch and kitten need is listed in [`../secrets.env`](../secrets.env).


## 0. How to use this document

- **Authority, highest first:** owner answers (§1) → corrections (§2) → `04-build-prompt.md`
  → `03-dev-plan.md` → `02-design-plan.md` → `01-ideation.md`. When §2 corrects a spec doc,
  the agent fixes that doc in the first commit that touches the area and says so in the
  runbook (AGENTS.md §3).
- **The build doesn't start** until every row in §1 has an answer. An empty row is a stop.
- **No real values anywhere in this repo.** It is public (`github.com/purrMonster/persianPerch`).
  `secrets.env` names every setting and where its value comes from; the values are entered
  on cellar at deploy time by the fleet's own `setup-secrets.sh` (C13).

## 1. Questions for the owner

Answer in the last column (`A`, `yes`, or pasted output). ★ = recommended.

| # | Question | Options | Answer |
|---|---|---|---|
| Q1 | `README.md` and `docs/04-build-prompt.md` are modified; `AGENTS.md`, `CLAUDE.md`, `runbook.md` are untracked since `2f6fafc first push`. Commit them, this plan and `secrets.env` as the baseline before M0? | ★yes / no | yes |
| Q2 | `origin` is the **public** `github.com/purrMonster/persianPerch`; build prompt rule 5 forbids pushing. | ★A local commits only, you push after reviewing · B agent pushes after each green milestone (needs Q3 = yes) | B |
| Q3 | Only if Q2 = B: Secret scanning and Push protection on for persianPerch? Check: GitHub → persianPerch → Settings → Advanced Security. | yes / no | yes |
| Q4 | Who runs the build? | ★A Claude Code on roastery, working dir = this folder · B Cowork | A (Claude Code; changed from B on 2026-09-30) |
| Q5 | Toolchain in containers only: Python 3.12 (perch), Python 3.13 (kitten, = the nodes) and Playwright as Docker Desktop containers; nothing installed on roastery (it has Python 3.14). | ★yes · no (say which Python to install) | yes |
| Q6 | Pace. | A straight through M0→M5 + M6-prep · ★B stop after each green milestone for your go-ahead | B |
| Q7 | roastery sleeps (cellar wakes it at 01:25 for backups). During the build: | ★A you set Sleep = Never (plugged in) until it ends · B leave it; the agent works only in sessions you start | A |
| Q8 | Acknowledge conflicts with "no write endpoints" (04 rule 4), and an ntfy action button can't pass Authelia. | ★A page-only `POST /ack` behind Authelia, writes only perch's own DB; no ntfy button in v1 · B page + ntfy button via a signed one-time URL on an Authelia-bypassed path · C no acknowledge in v1 | B |
| Q9 | kitten on roastery (Windows: no systemd, no `/opt/purrbrews`, no backup jobs of its own). | ★A none: purr watches it through its [Komodo periphery][FC-rp] with a sleep window · B a Windows kitten (Scheduled Task, ASCII PowerShell) | B |
| Q10 | Alerts that already exist: [Gatus → ntfy][FC-gatus], [`backup.sh` notify][FC-backup], [`check-freshness.sh`][FC-fresh] at 06:00. | ★A v1 meow pushes only what nothing pushes today (containers, kitten silence, missed rhythms, disks, whiskers); glare/groom failures show on the page only · B meow pushes everything; you retire the old alerts after M6's week | B (see A6) |
| Q11 | hiss when sieve's ntfy itself is down. | A ntfy only · ★B hiss also to the public ntfy.sh critical topic Gatus already uses · C SMTP email (needs an SMTP account) | B |
| Q12 | Reading Gatus: its route uses the cookie-only `authelia` middleware ([sieve.yml][FC-sieveyml]), so Basic auth can't pass. | ★A the ollama pattern: a `gatus-api` router with `forward-auth-basic`, LLDAP group `perch_api_group`, a `one_factor` rule ([Authelia template][FC-authelia]); prepared in `integration/` · B publish Gatus :8080 on sieve, UFW-limited to cellar, no Authelia | A |
| Q13 | groom records need a fleet change either way. | ★A a recorder run by each backup unit's `ExecStopPost=` (JSON from `$SERVICE_RESULT`, `$EXIT_STATUS`, journal tail); `backup.sh` untouched · B patch `backup.sh` and cellar's scripts to write the JSON. Either is prepared in `integration/` only | A |
| Q14 | Home Assistant has no read-only role; a non-admin user can still switch things. Accept a non-admin `perch` user whose token perch uses only for `auth`, `subscribe_events`, `get_states` (enforced by test S4)? | ★yes · no (whiskers leaves v1) | yes |
| Q15 | kitten's Python target. On any Linux node, paste: `python3 --version; cat /etc/debian_version` | expected 3.13 / 13.x | `Python 3.13.5` / `13.7` |
| Q16 | groom's existing state on cellar. On cellar, paste (names and dates only): `sudo ls -la /var/lib/purrbrews/` | | only `drive-sync.ok` (0 B, root, 2026-09-30 03:31); dir `root:root 755` |

### 1a. What the answers change (binding for the build)

| # | Change |
|---|---|
| A1 (Q1) | First commit of the build: the baseline (`README.md`, `docs/04-build-prompt.md`, `AGENTS.md`, `CLAUDE.md`, `runbook.md`, this plan, `secrets.env`), added by name, before any M0 code. |
| A2 (Q2, Q3, Q6) | At each milestone, on its own branch: gate green → AGENTS.md §5 pre-push checks (author/committer emails, the diff read through for domain/secrets, tests) → runbook entry → **push the branch and open a pull request into `main`** → **stop and wait for the owner**, who merges with a merge commit and gives the next go-ahead. Never push to `main`, never force-push. *(Amended 2026-10-02: was "`git push origin main`"; the owner switched to pull requests during M1.)* 04 rule 5 is amended accordingly. |
| A3 (Q4, Q5) | The builder is **Claude Code on roastery** (PowerShell, working dir = this folder, so `CLAUDE.md` loads automatically). Pre-flight adds two checks that must pass before M0, else stop and report (never work around them): `docker info` works (the toolchain is containers only), and `git ls-remote origin` works (push access over SSH). The agent never asks for, creates or copies SSH keys or tokens, never runs with permission prompts skipped, and asks before any command outside this folder (AGENTS.md rule 1). |
| A4 (Q7) | roastery doesn't sleep during the build; the 01:20–04:00 quiet hours for heavy work still apply. The owner restores sleep after M6-prep (a Backlog item). |
| A5 (Q9) | **A Windows kitten on roastery**, same zipapp as the Linux one, run by roastery's existing Python (3.14; no install) as a Scheduled Task at startup, restarted on wake. The kitten code is stdlib-only and must pass its tests on 3.13 **and** 3.14. On Windows, file events are polled (few paths, 10 s), not `inotifywait`. Heartbeat is sleep-aware (C5): silent outside the wake window = slowBlink. Default roastery pounce path: `C:\purrbrews\restic\snapshots` (a new snapshot arrived → earTwitch), not the whole repository (restic writes thousands of files). Install and task scripts are ASCII-only PowerShell, in `integration/roastery/`, following [roastery's scripts][FC-roastery]. Its token comes from roastery's own secrets flow ([setup-secrets.ps1][FC-rsecrets]). roastery's IP (`ROASTERY_LAN_IP` in fleet.env) joins the kitten router's allow-list (C1); fleet.env notes it has no DHCP reservation yet, so ROLLOUT.md checks it. |
| A6 (Q10) | meow pushes everything. For M6's week, old and new alerts run side by side (meow titles start with `perch:` to tell them apart). After that, ROLLOUT.md lists what the owner may retire: Gatus's layer-1 ntfy alerts, `backup.sh`'s failure notify, `check-freshness.sh`'s notify. It **must keep** Gatus's critical checks (ntfy.sh) and sieve's healthchecks.io heartbeat: they watch the path perch's own alerts travel through, which perch can't watch. |
| A7 (Q11) | hiss goes to ntfy and to the ntfy.sh critical topic (`PERCH_MEOW_CRITICAL_URL`). |
| A8 (Q12, Q13, Q14) | As recommended: the ollama pattern for Gatus; the `ExecStopPost=` recorder; a non-admin HA user with test S4. |
| A9 (Q15) | kitten targets Python 3.13 on Debian 13.7 (C11 confirmed). |
| A10 (Q16) | `/var/lib/purrbrews/` holds only `drive-sync.ok`, so every groom record is new. The recorder (root) writes `/var/lib/purrbrews/groom/<job>/<start>.json` as `0644` in a `0755` directory, so kitten runs as an unprivileged `kitten` user with read access only. |
| A11 (Q8) | **Acknowledge from the page and from the push.** Page: `POST /ack/{litterId}` behind Authelia, with a CSRF token. Push: meow adds an ntfy `http` action button that calls `POST /ack/t/{token}` on a separate Traefik router that bypasses Authelia for that one path only. The token is an HMAC-SHA256 (key `PERCH_ACK_SECRET`) over litterId + expiry; it is **single-use** (spent tokens stored in scentTrail), expires after 24 h or when its litter clears, and can do exactly one thing: mark that litter acknowledged (stop repeats). A new hiss still alerts. Rate limit on the path: 10 requests/min. The button goes only on pushes through the self-hosted ntfy, never on the ntfy.sh critical copy (a third party would see the link). It works only where the phone reaches `perch.${DOMAIN}`: on the LAN, or on the tailnet once the phone joins it (a fleet Backlog item; ROLLOUT.md says so). Amends 04 rule 4: the only write endpoints are `/api/kitten`, `POST /ack/{litterId}` and `POST /ack/t/{token}`, all writing to perch's own DB only. |
| A12 (owner, 2026-10-02) | **htmx 2.0.11, vendored, as M2's first task** ([ADR 0003](adr/0003-htmx-vendored.md)). Served by perch from `perch/windowsill/static/vendor/htmx-2.0.11.min.js`, never a CDN; a test checks its SHA-256. Pages poll at purr's rhythm (30 s) with `hx-trigger="every 30s"` on the state regions, not whole-page reloads. The SSE extension came with M5 ([ADR 0011](adr/0011-live-scenttrail-sse-extension.md)). Not htmx 4: npm still tags it `next`. |
| A13 (owner, 2026-10-02) | **Vitals history and sparklines in M4**, with the disks (design plan §3.5): one `vitals` table, 5-minute averages for 7 days and hourly for 400 days; server-rendered inline SVG, no chart library. Until M4, the overview mockup's sparklines are spec for M4, not M2/M3 work. |

## 2. Corrections to the spec (apply without asking; record each)

| # | Finding | Fix |
|---|---|---|
| C1 | kitten's push can't pass Authelia's `forward-auth` (no browser session). | A second router on cellar's Traefik for ``PathPrefix(`/api/kitten`)``: `ipAllowList` = the node IPs from [fleet.env][FC-fleetenv] (roastery included, A5), no Authelia; perch still requires the per-node bearer token. Everything else on `perch.${DOMAIN}` stays behind Authelia ([cellar dynamic.yml][FC-cellardyn]). |
| C2 | Design §4.4 watches `/opt/purrbrews/.git/HEAD`, which never changes on a pull (it holds `ref: refs/heads/main`). | Watch `/opt/purrbrews/.git/refs/heads/main` and `/opt/purrbrews/.git/packed-refs`; the event carries the new commit subject. |
| C3 | Design §3.4 lists only nightly, store and Drive rhythms. | Add from the repo's timers: [wake-roastery][FC-wake] 01:25, [backup-check][FC-check] 06:00, [restic-prune][FC-prune] Sun 03:00, [backup-verify][FC-verify] 1st of month 04:30. The nightly has `RandomizedDelaySec=5min` and waits up to 10 min for roastery ([timer][FC-nightly]); late threshold stays +45 min. |
| C4 | Rhythms must not be hard-coded. | Read `OnCalendar` from [`_lib/systemd/purrbrews-backup@.timer`][FC-nightly] and [`stacks/cellar/restic/*.timer`][FC-restic]; backup nodes = nodes with any `<app>/backup` file, dump nodes = those with `pg`/`mongo`/`sqlite` lines — the same rule as [check-freshness.sh][FC-fresh]. |
| C5 | "Sleeps" is defined for purr only. | roastery's sleep window (from [wake-roastery.timer][FC-wake]) applies to purr and to every rhythm that depends on roastery. Asleep outside the window = slowBlink; unreachable inside it = hiss. |
| C6 | perch runs on cellar next to Komodo and Scrutiny. | perch joins `cellar_net` ([node.conf][FC-cellarconf]): Komodo at `http://komodo-core:9120` ([compose][FC-komodo], v2.3.2), Scrutiny at `http://scrutiny:8080` ([compose][FC-scrutiny]). New setting `PERCH_DISKS_URL`. |
| C7 | cloudflared's metrics aren't reachable from cellar (only on `sieve_edge`, [compose][FC-cfd]). | binocs takes the tunnel's state from Gatus's existing tunnel `/ready` check; no new access. |
| C8 | speedtest-tracker is on grinder, host port 8765 ([compose][FC-speed]); its API needs a token. | `PERCH_BINOCS_SPEEDTEST_URL` / `_TOKEN`. |
| C9 | perch's own SQLite in WAL can't be file-copied live. | Its `backup` file uses a `sqlite` line (a consistent `.dump`), never `path` for the live DB ([stacks README → backup][FC-stacks]). |
| C10 | Missing settings. | Add `PERCH_TZ` (default `${TZ}` from fleet.env), `PERCH_ROLLUP_DAYS=400`, `PERCH_DISKS_URL`, `PERCH_BINOCS_*`, `PERCH_ACK_SECRET` (A11), `PERCH_MEOW_CRITICAL_URL` (A7), per-node `PERCH_KITTEN_TOKEN_<NODE>`; update dev plan §3. |
| C11 | Nodes run **Debian 13** ([README][FC-readme]), not 12 as 04 §4 says; `watchfiles` is a compiled dependency a zipapp can't carry. | kitten = stdlib-only Python zipapp (target from Q15); file events via `inotifywait` (Debian package `inotify-tools`, installed at M6). ADR 0001 records the alternatives (watchfiles in a venv; polling). |
| C12 | The dev plan's "Done when" lines are real-fleet drills; the build is fixtures-only. | Each milestone is ticked on its **build gate** (§5). The drills become post-deploy Backlog items for the owner in `integration/ROLLOUT.md`. |
| C13 | The fleet already has a secrets mechanism ([secrets.conf format][FC-stacks]). | M6 prepares `stacks/cellar/persian-perch/secrets.conf` from `secrets.env` (each line's verb is noted there); the owner runs `./setup-secrets.sh` on cellar, which writes `secrets.env.local`. This repo never holds a value (test S5). |
| C14 | ntfy users and tokens are built from lists on sieve ([ntfy secrets.conf][FC-ntfy], [secrets.hook][FC-ntfyhook]). | perch gets its own ntfy user + token via `NTFY_EXTRA_USERS/ACCESS/TOKENS` on sieve, write-only on `purrbrews-alerts`; no ntfy file changes. |
| C15 | catTree needs a stable fixture. | Clone the fleet repo into `.cache/purrbrews-containers` at the pinned commit; the catTree test asserts every `APPS` entry of every `node.conf` appears and no deny-listed file is listed. |

## 3. Environment

Every command runs in the project folder on roastery, in PowerShell. M0 turns the test
commands into `scripts/test.ps1` (ASCII-only).

**Pre-flight, at the start of every session** (any failure → stop and record it):

```powershell
docker info --format '{{.ServerVersion}}'     # Docker Desktop is running
git status --short --branch; git log --oneline -5
git config user.email                         # must be jyotirmoy.github@jyotirmoy.cc
git ls-remote origin                          # push access (A3)
```

**Pin the fleet repo** (once; `.cache/` is gitignored):

```powershell
git clone https://github.com/purrMonster/purrbrews-containers .cache/purrbrews-containers
git -C .cache/purrbrews-containers checkout f94efdfb1995d7217ec2be33e45b33720a0a0b3b
```

**Tests** (images pinned by tag and digest in M0; the digests go in the runbook). *Since M0
(2026-09-30) these run as `scripts/test.ps1`; perch's step uses a test image built from
`tests/Dockerfile` (the 3.12 base plus `git`, which catTree and S5/S6/S8 need), so the first
line below became `docker build -f tests/Dockerfile ...` + `docker run ... ruff check . && pytest -q`.*

```powershell
docker run --rm -v "${PWD}:/src" -w /src python:3.12-slim sh -c "pip install -q -r requirements-dev.txt && ruff check . && pytest -q"
docker run --rm -v "${PWD}:/src" -w /src python:3.13-slim sh -c "python -m unittest discover -s tests/kitten"
docker run --rm -v "${PWD}:/src" -w /src python:3.14-slim sh -c "python -m unittest discover -s tests/kitten"
docker compose -f tests/ui/compose.yml up --abort-on-container-exit --exit-code-from playwright
```

**Quiet hours for the build machine:** no image builds or long test runs 01:20–04:00 IST
(roastery holds the restic repository and cellar wakes it for the nightly backups).

## 4. Execution protocol (every session)

1. Read `CLAUDE.md`, `AGENTS.md`, the runbook's Backlog and newest three entries, and §1–§2 here.
2. Run the pre-flight (§3).
3. Claim under **In progress** in `runbook.md`.
4. Take the first unchecked task of the current milestone (§5). Write the failing test, then
   the code, then run the **whole** suite and `ruff`.
5. Commit only when green: `<area>: <what>`, a why line, the `Co-Authored-By` trailer.
   Never commit red. Never `git add -A`: add the files you changed by name.
6. At each milestone gate and each decision: a runbook entry with the real command output.
7. At a green gate: A2 (pre-push checks, push the branch, open the pull request, report,
   stop for the owner). If the
   milestone touched `perch/windowsill/` or `mockups/`, the gate also needs the
   web-design-guidelines review of every changed UI file, pasted into the runbook entry
   with each finding fixed or explained (AGENTS.md §3.1, `docs/06-design-system.md` §7).
8. Before stopping (session end, context running low, a stop case): commit green work,
   write the handoff entry (AGENTS.md §6), remove the claim, commit.
9. At each gate, check the budget: `docker stats --no-stream` shows perch ≤ 300 MB.

## 5. Milestones and build gates

Each gate is proved by command output pasted into the runbook. Fixtures are shaped from
each tool's public API docs and the pinned versions in the fleet repo.

**M0 Litter.** `.gitignore` (`.cache/`, `*.env.local`, `secrets.env.local`, `__pycache__/`,
`screenshots/`), scaffolding per dev plan §2, `requirements*.txt` pinned, Dockerfile,
`compose.example.yml`, CI file, `bodyLanguage`, `scentTrail` (WAL, migrations, retention:
90 days of events, 400 days of rollups), `catTree` from `git ls-files` with the deny-list,
windowsill skeleton from the mockups' CSS, `scripts/test.ps1`, ADR 0001 (C11).
*Gate:* tests green including S1, S5, S6, S7, S8; `/tree` lists every node and app of the
pinned repo; screenshots at 1400 px dark/light and 390 px, no horizontal scroll, no console
errors.

**M1 First purr.** Komodo adapter in one module (v2.3.2 `/read` API), fixtures, rollups
app → node → fleet, overview and catTree app pages with live state, rhythms for collectors,
"collector late", roastery's sleep window (C5).
*Gate:* in a test with a fake clock, `grinder/n8n` exited → app, grinder and fleet hiss
within two purr cycles; restored → slowBlink; roastery asleep outside its window → slowBlink.

**M2 Grooming.** *First:* htmx 2.0.11 vendored per A12 and ADR 0003 (the file, its SHA-256
test, 30 s polling on the overview, node and app pages; the web-design-guidelines review
covers it). Then: groom record schema (design §4.2 + C3), the recorder per A8 in
`integration/groom/`, kitten v0 (heartbeat, record shipping, per-node token; Linux and
Windows per A5), `/api/kitten` (S3), the grooming grid, copies panel (Drive copy age from
`drive-sync.ok`, morning check, verify), rhythms from the repo (C4).
*Gate:* a fixture night with one node's record missing → only that cell hisses at 04:30
fake time; every other cell slowBlink. And: the vendored htmx matches its pinned SHA-256,
and in Playwright a state change appears on an open overview within 35 s without a full
page reload (focus and scroll position kept).

**M3 meow + nineLives.** Routing per A6 and A7, litters, dedupe, quiet hours
(23:00–07:00, hiss exempt), recovery messages, acknowledge per A11 (page and signed push
button), rate limit 10 pushes / 10 min, nineLives pinging only when every collector is on
time.
*Gate:* fake grinder down → exactly one push, then one recovery push; the push's ack button
acknowledges once, and a replayed, expired or tampered token gets 403 (S9); perch stopped →
the fake healthchecks endpoint receives no ping; a 50-event storm → ≤ 10 pushes.

**M4 glare + binocs + disks + vitals.** Gatus statuses (auth per A8), Scrutiny summary with SMART
attribute 9 preferred over the summary's power-on hours, binocs: tunnel via Gatus (C7),
speedtest (C8), upstream releases weekly (earTwitch only). Vitals history per A13 and design
plan §3.5: the `vitals` table, its downsampling and retention, and the overview and node
sparklines as server-rendered inline SVG (CPU, RAM, disk).
*Gate:* the overview shows glare and disk state from fixtures; a test proves attribute 9
wins when the summary disagrees. And: with a fake clock, 8 days of 30 s samples leave
exactly 7 days of 5-minute rows plus hourly rows; the database stays under 20 MB at 400
days of 6 nodes; sparklines render with no console errors and have a text alternative.

**M5 pounce + whiskers.** kitten pounce via `inotifywait` on Linux and polling on Windows
(A5), 2 s debounce, 60 events/min per path then one storm tailFlick; default paths = design
§4.4 with C2; whiskers over a fake HA WebSocket (auth handshake, `subscribe_events`,
reconnect with backoff, S4), `whiskers.example.yml` per 04 §4; the scentTrail view with
filters and SSE.
*Gate:* an integration test drops a file in a watched fake path and sends a door event;
both appear in the trail within 5 s with the right body language.

**M6 prepare only.** In `integration/`, each file with the link to where it lands:

- `stacks/cellar/persian-perch/`: `docker-compose.yml` (joins `cellar_net`),
  `secrets.conf` (C13), `backup` (C9), `firewall`, `data-dirs`, `README.md`; the `APPS`
  line for [cellar's node.conf][FC-cellarconf].
- cellar Traefik: the perch router, the kitten router (C1) and the signed-ack router (A11)
  for [dynamic.yml][FC-cellardyn].
- Authelia: `perch.${DOMAIN}` in `admin_hosts`, plus the `perch_api_group` rule (A8)
  for the [template][FC-authelia]; sieve's `gatus-api` router for [sieve.yml][FC-sieveyml].
- ntfy extras for sieve (C14); a Gatus check for perch in [config.yaml][FC-gatuscfg];
  a Homepage tile in [services.yaml][FC-homepage].
- kitten: zipapp, systemd unit, install script, default pounce config per node; roastery's
  Scheduled Task and ASCII install script in `integration/roastery/` (A5).
- groom: the recorder and unit drop-ins (A8).
- `ROLLOUT.md`: every credential in `secrets.env` with where to create it, step-by-step
  deploy, the alerts to retire after the first week (A6), and the dev plan's "Done when"
  drills as the owner's post-deploy checklist (C12).

*Gate:* copy the pinned clone to `.cache/fleet-scratch`, apply `integration/` to it, and its
own `python3 -m unittest discover -s tests` passes (catches an unset variable, an
un-ignored template, an app missing from `node.conf`).

## 6. Tests that must always pass

| # | Test |
|---|---|
| S1 | catTree never lists `*.env.local`, `secrets.env.local`, `*.key`, `authorized_keys`, even when tracked in a fixture |
| S2 | scrubbed log tails never contain a value from `tests/fixtures/secrets.fake.env` |
| S3 | kitten push without a token → 401; another node's token → 403 |
| S4 | whiskers never sends any message type other than `auth`, `subscribe_events`, `get_states` |
| S5 | every `KEY=` line in `secrets.env` has an empty value |
| S6 | no hostname in tracked files outside an allow-list (`${DOMAIN}`, `example.home.arpa`, `github.com`, `hc-ping.com`, `ntfy.sh`, docs hosts) |
| S7 | the route table has no write endpoint except `/api/kitten`, `POST /ack/{litterId}` and `POST /ack/t/{token}` (A11) |
| S8 | every `.ps1` file is ASCII-only; kitten's tests pass on Python 3.13 and 3.14 |
| S9 | signed ack: a tampered, expired, reused or other-litter token → 403 and no state change; the page ack without a CSRF token → 403; ntfy.sh pushes never carry the button |

## 7. Stop and ask (only these)

04 §7's cases, plus: an unanswered §1 row; a failed A3 pre-flight check; needing any real
credential or the real domain; the M6 gate failing in a way that needs a fleet change
outside `integration/`.

## 8. Finish

As 04 §8, plus: the post-deploy drill list in `ROLLOUT.md`, and every §2 correction
confirmed in the docs it changed.

[FC-rp]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/roastery/komodo-periphery/docker-compose.yml
[FC-gatus]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/sieve/gatus/README.md
[FC-gatuscfg]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/sieve/gatus/config/config.yaml
[FC-backup]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/_lib/backup.sh
[FC-fresh]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/restic/check-freshness.sh
[FC-sieveyml]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/sieve/traefik/dynamic/sieve.yml
[FC-authelia]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/percolator/authelia/config/configuration.yml.template
[FC-fleetenv]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/fleet.env
[FC-cellardyn]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/traefik/config/dynamic.yml.template
[FC-cellarconf]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/node.conf
[FC-wake]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/restic/purrbrews-wake-roastery.timer
[FC-check]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/restic/purrbrews-backup-check.timer
[FC-prune]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/restic/restic-prune.timer
[FC-verify]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/restic/purrbrews-backup-verify.timer
[FC-nightly]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/_lib/systemd/purrbrews-backup@.timer
[FC-restic]: https://github.com/purrMonster/purrbrews-containers/tree/main/stacks/cellar/restic
[FC-komodo]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/komodo/docker-compose.yml
[FC-scrutiny]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/cellar/scrutiny/docker-compose.yml
[FC-cfd]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/sieve/cloudflared/docker-compose.yml
[FC-speed]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/grinder/speedtest-tracker/docker-compose.yml
[FC-stacks]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/README.md
[FC-readme]: https://github.com/purrMonster/purrbrews-containers/blob/main/README.md
[FC-ntfy]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/sieve/ntfy/secrets.conf
[FC-ntfyhook]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/sieve/ntfy/secrets.hook
[FC-homepage]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/percolator/homepage/dashboard/services.yaml
[FC-roastery]: https://github.com/purrMonster/purrbrews-containers/tree/main/stacks/roastery
[FC-rsecrets]: https://github.com/purrMonster/purrbrews-containers/blob/main/stacks/roastery/setup-secrets.ps1
