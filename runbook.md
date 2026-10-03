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
- [x] The build (Cowork): pre-flight incl. A3 and the baseline commit `4c02312` (05 plan A1) (2026-09-30, M0 entry)
- [ ] Restore roastery's sleep setting after M6-prep (owner; 05 plan A4)
- [x] M0 Litter: scaffolding, scentTrail, catTree, windowsill skeleton (2026-09-30, gate green on roastery, M0 entry)
- [x] Owner's go-ahead for M1 (05 plan A2): given in chat 2026-10-01, after approving the design rework's screenshots and mockups
- [ ] CI: `ci/github-actions-ci.yml` is ready but inactive; move it to `.github/workflows/ci.yml` if you want GitHub Actions on the public repo (owner; M0 entry)
- [x] M1 First purr: containers and vitals via Komodo's read API (faked), rollups, overview and catTree pages (2026-10-02, gate green on roastery, M1 entry; pull request open)
- [x] Owner: review and merge the M1 pull request, then `git pull` the main checkout (M1 entry): PR #1 merged 2026-10-02 as merge commit `ad87ef5` (hashes kept); main checkout pulled, fast-forward
- [x] Owner: decide on vendoring htmx for live refresh: **yes, htmx 2.0.11, vendored, M2's first task** (2026-10-02; 05 plan A12, ADR 0003)
- [x] Vitals history and sparklines (mockup 01): **yes, in M4** with the disks (2026-10-02; 05 plan A13, design plan §3.5)
- [x] Agents open pull requests instead of pushing to `main`; the owner merges with a merge commit (2026-10-02; AGENTS.md §5, 05 plan A2)
- [x] Owner's go-ahead for M2 (2026-10-02), effective once the pull request with these decisions is merged
- [x] Owner: is the domain of the commit email (`jyotirmoy.github@jyotirmoy.cc`) also the fleet's real domain? **No**: it is the owner's personal domain, not the fleet's (owner, 2026-10-02). Nothing is exposed; the commit identity stays as it is. S6 keeps allowing only the full address, never the bare domain, so the rule "no domains in files" stays simple.
- [ ] M6 `ROLLOUT.md` drills: stop a container on grinder, hiss within 60 s; `ListServers {}` and `ServerState` spelling against the real Komodo 2.3.2; roastery in and out of its window (M1 entry)
- [x] M2 Grooming: htmx 2.0.11 vendored with 30 s live regions, groom records and grid, kitten v0, `/api/kitten`, the recorder prepared in `integration/groom/` (2026-10-02, gate green on roastery, M2 entry; pull request to open)
- [ ] Owner: review and merge the M2 pull request (merge commit), then `git pull` the main checkout (M2 entry)
- [ ] M6: apply `integration/groom/` and install kitten on the nodes; `KITTEN_NODE` spelling per node (M2 entry)
- [x] M3 meow + nineLives: alerts, litters, quiet hours, Acknowledge (page and push), outside heartbeat (2026-10-02, gate green on roastery, M3 entry; pull request to open)
- [ ] Owner: review and merge the M3 pull request (merge commit), then `git pull` the main checkout (M3 entry)
- [ ] M6: Traefik router for `/ack/t/` only, around Authelia; `PERCH_PUBLIC_URL`, `PERCH_ACK_SECRET`, the ntfy token, the critical URL and the ping URL entered on cellar (M3 entry)
- [x] M4 glare + binocs + disks + vitals: Gatus, Scrutiny, tunnel, speedtest, upstream releases, vitals history and sparklines (2026-10-03, gate green on roastery, M4 entry; pull request to open)
- [ ] Owner: review and merge the M4 pull request (merge commit), then `git pull` the main checkout (M4 entry)
- [ ] M6: Gatus router and Authelia rule for perch-svc; `PERCH_GLARE_*`, `PERCH_DISKS_URL`, `PERCH_BINOCS_SPEEDTEST_*` and `PERCH_BINOCS_RELEASES_EVERY=7d` entered on cellar (M4 entry)
- [ ] Owner: should glare and disks stop nineLives' ping when late? (M4 entry, Notes)
- [ ] M5 pounce + whiskers: kitten file events, Home Assistant, the scentTrail view
- [ ] M6 Into the fleet: prepared in `integration/` with `ROLLOUT.md`; deployed by the owner

---

## 2026-10-03 — M4 glare + binocs + disks + vitals: Gatus, Scrutiny, tunnel, speedtest, releases, vitals history; gate green

**Context.** The owner gave M4 its go-ahead and a first task: make the M3 container incident impossible to repeat.
Claude Code (Sonnet 5.5), branch `claude/m4-glare-binocs-disks-vitals-1a383e`, started 2026-10-03 00:40 IST. Pre-flight passed
(Docker 29.7.2, `main` at M3's merge `47dad4a`, clean, identity right, origin answered, the three skills present).
Running on roastery at the start: `purrbrews-bootstrap`, `komodo-periphery`, `immich-machine-learning`; I touched none.

**Decided** (reasons; losing alternatives in brackets).
- **Container safety (AGENTS 2.8).** Only objects this project created may be stopped, killed, removed or pruned, identified by the label
  `com.purrbrews.project=persianperch` or the compose project; commands that select all or unnamed objects are forbidden.
  Every container and image `scripts/test.ps1` and `tests/ui/compose.yml` start carries the label; `tests/test_containerSafety.py` greps
  tracked scripts (14 forbidden forms caught, 7 safe forms pass). Pointer added to CLAUDE.md.
- **Gatus read at v5.36.0 (source, tag v5.36.0):** `GET /api/v1/endpoints/statuses?page=&pageSize=` returns a JSON array; page and pageSize
  page each endpoint's *results* (default 50). Fields: `name`, `group`, `key`, `results[]` (`success`, `timestamp`, `duration` in ns,
  `status`, `errors`, `conditionResults`), `events`. **Uptime is `json:"-"`**, so it is not in that JSON (separate plain-text routes
  `/uptimes/{1h,24h,7d,30d}`); glare judges the newest results itself, one request for everything [calling the uptime route per endpoint:
  N more requests for a number the results already give]. Rules: 2 failed checks in a row tailFlick, 5 hiss, 0 or 1 slowBlink (the title says
  "last check failed"); no result for 3 of its own intervals (min 5 min) unknown; Gatus unreachable: after 2 failed cycles every endpoint
  unknown, no per-endpoint event, one tailFlick from the collector rhythm ("glare is late ... can't see Gatus"). A refused login
  (302, 401, 403) has its own message; the password is never in a message.
- **Scrutiny read at v0.9.3 (source):** `GET /api/summary` (`data.summary` keyed by wwn: `device` with `device_status` bit flag 1 failed SMART,
  2 failed Scrutiny's thresholds, `host_id`, `device_name`, `model_name`; `smart` with `collector_date`, `temp`, `power_on_hours`) and
  `GET /api/device/<scrutiny_uuid>/details?duration_key=week` (`smart_results` newest first, `attrs` keyed by id as text, attribute `status` bit
  flag 1 failed SMART, 2 warning, 4 failed Scrutiny; `metadata` with `display_name`). **Mapping:** device_status not 0 is hiss; no device failure
  but an attribute in Scrutiny's warning band is tailFlick; no SMART report for 3 days is tailFlick; else slowBlink. **Power-on hours: attribute 9
  (`raw_value`; NVMe `power_on_hours`, `value`) beats the summary's**; the page shows the summary's figure in small type when they disagree. A drive
  counts toward the node named by its `host_id` (case-insensitive), else toward the fleet. Disk events use sense `purr` ("node vitals, drive health"):
  no new sense name [a new sense `disks`: touches the trail filter, the SENSES tuple and two docs for no gain].
- **speedtest-tracker read at v1.15.0 (source; the fleet runs the linuxserver `v1.15.0-ls170` build):** `GET /api/v1/results/latest`, Bearer
  token with `results:read`, `{"data": {...}}`, 404 when empty; `download_bits` and `upload_bits` in bits/s, `ping` in ms, `healthy`, `status`,
  `created_at` as `YYYY-MM-DD HH:MM:SS` in the app timezone (taken as `PERCH_TZ`). Failed, unhealthy or older than 6 h is earTwitch;
  unreachable, forbidden or empty is unknown.
- **Registries (ADR 0007).** Read: Docker's published OpenAPI (tag listing there is bearer-authenticated, no `ordering` for tags), the OCI distribution
  spec (`tags/list?n=`, `Link rel=next`, lexical order), Docker's rate-limit docs (429 and Retry-After). **So Docker Hub is read through its
  registry (`registry-1.docker.io` with the anonymous token from `auth.docker.io`), the same code as ghcr.io; lscr.io is ghcr.io/linuxserver.** One list
  per repository, a pause between, a 429 stops the run and it resumes after Retry-After. Only `[v]X.Y.Z[-flavour]` pins compare; `-lsNNN` is ignored;
  line pins and moving tags are counted as "can't be compared". **Off unless `PERCH_BINOCS_RELEASES_EVERY` is set** (the default was 7 d), so no
  development run ever touches a registry. S6 allow-list: `ghcr.io` and `lscr.io` (one-line reasons in `test_repoHygiene.py`; `*.docker.io` was already there).
- **Tunnel (C7):** Gatus's `cloudflare tunnel` check (key `network_cloudflare-tunnel`), shown from the glare state; binocs makes no request and
  writes no state for it. **binocs states never count toward the fleet level or "Needs a look"** (earTwitch ranks above slowBlink, so a weekly notice
  would turn the badge); glare and disks do.
- **Vitals (ADR 0008):** two tables, both keep the highest reading of all three metrics (the plan said disk only); written from purr's stats.
- **Sparklines:** fixed 0 to 100 % scale, `--muted`, gaps break the line, `role="img"` with `RAM 24 h: 41-63 %, now 58 %`; docs/06 sections 4 and 6.
- New settings `PERCH_GLARE_EVERY`, `PERCH_DISKS_EVERY`, `PERCH_BINOCS_EVERY` (empty keys in `secrets.env`) so the drill can run on a 2 s rhythm.

**Done.** `perch/vitals.py`, scentTrail migration 5, `senses/{gatus,glare,scrutiny,disks,speedtest,registries,binocs}.py`, `windowsill/spark.py`,
rollup, meow, collectors and settings wiring, the Endpoints, Disks and Outside cards and the sparklines (templates, CSS), fakes in `tests/outsideFakes.py`,
seed, live, shoot and budget extended, `scripts/test.ps1` gets the drill step and labels, ADRs 0007 and 0008, docs 02 and 06.

**Verified** (roastery, 2026-10-03; the quiet-hours rule was lifted for this run by the owner in chat, so `scripts\test.ps1 -Force`):
```
=== perch: ruff + pytest (3.12)  All checks passed!   585 passed in 367.93s
=== kitten: unittest (3.13) and (3.14)               ok, ok
=== windowsill: Playwright       33 passed, 0 failed ; live: all ok
=== real-socket drill            budget, drill and leak check: ok
=== summary                      ok x7 (fleet repo pinned, build test image, pytest, kitten 3.13, 3.14, Playwright, drill)
```
The first full run failed twice and I fixed both: S6 flagged a made-up image on a registry not in its allow-list in a test and a host spelled through an f-string in the registry fake
(both replaced by `example.home.arpa`); and the drill expected "grinder back" as its own push while meow, correctly, sent grinder's and pihole's recoveries as one
("perch: 2 things are back"), so the drill now accepts exactly one recovery push, either form.
- **Gate, by test:** `test_GATE_smart_attribute_9_wins_when_the_summary_disagrees` (20000 h beats 3 h); `test_GATE_8_days_of_30_second_samples_leave_exactly_7_days_of_5_minute_rows_plus_hourly_rows`
  (2016 and 192); `test_GATE_the_database_stays_under_20_MB_at_400_days_of_6_nodes` (**7.43 MB**); `test_GATE_gatus_unreachable_is_one_tailFlick_and_unknown_never_a_hiss_per_endpoint`
  (exactly one tailFlick event, no hiss, no per-endpoint event); `test_the_overview_shows_glare_from_the_fixture_and_the_placeholder_is_gone`;
  `tests/test_containerSafety.py` (14 forbidden forms caught, 7 safe forms pass, every `docker run` and `build` in `test.ps1` carries the label, no tracked script has a forbidden form).
- **Playwright (`tests/ui/live.py`), 1400 dark, 1400 light, 390 px:** the overview has 15 sparklines (5 nodes with vitals), grinder's and cellar's node pages 6 each (7 days and 90 days); every one drawn with data,
  `role="img"` with a text alternative (e.g. "CPU 24 h: 10-36 %, now 20 % | RAM 24 h: 31-40 %, now 40 % | disk 24 h: 50-61 %, now 50 %"), the line's computed stroke equal to `--muted`
  (never a state colour), no horizontal scroll, **no console errors**; cellar's seeded 4-hour gap reads "with gaps"; the overview shows Endpoints, Disks and Outside, and "833 d powered on"
  (attribute 9), not the summary's 3 h.
- **The real-socket drill** (`tests/ui/budget.py`, now a step of `test.ps1`; loopback fakes of Komodo, ntfy, Gatus with Basic auth, Scrutiny and speedtest-tracker):
  ```
  ok    glare read the fake Gatus: 3 of 3 answering
  ok    disks read the fake Scrutiny; SMART attribute 9 (20000 h) beat the summary (3 h)
  ok    binocs read the fake speedtest-tracker
  ok    five failed Gatus checks: pihole is a hiss on the overview
  ok    meow pushed the failing endpoint by its name
  ok    pihole answers again: 3 of 3 answering
  perch memory: VmRSS 61.2 MB, peak 61.2 MB (budget 300 MB)
  leak check: looked in 12 places (4354 KB): nothing found    <- now also the Gatus password and its Basic credential, and the speedtest token
  ```
- **Screenshots looked at by eye** (`overview-m4-*`, `cellar-m4-*`, `catTree-node-disks-*`; both themes and 390 px): the sparklines sit under the three meters and keep their shape; the 7-day line on
  cellar breaks where perch saw nothing; the 90-day line shows only the eight seeded days; the three new cards read well and wrap on a phone. Nothing to fix by eye. Because the scale is fixed 0 to 100 %,
  a node idling at 5 % draws a flat line near the bottom: intended (docs/06 section 6), say so if you would rather autoscale.

**web-design-guidelines review** (AGENTS 3.1; guidelines fetched fresh 2026-10-03 from the skill's source URL; **one pass, no sub-agents**, over `_macros.html` (sparkRow, glareCard, disksCard, binocsCard),
`live/overview.html`, `live/node.html`, `perch.css`, `windowsill/spark.py`'s output). Findings and what happened:
- Content handling: long endpoint or drive names in the `.feed` rows and long text in `.kv dd` could overflow a phone-width card -> **fixed**: `min-width:0; overflow-wrap:anywhere` on both.
- Passed: the sparkline is `role="img"` with an `aria-label` and `focusable="false"`, its paths carry no meaning of their own; headings in order (the node page's History is an `h3` under the `h2`);
  `translate="no"` on endpoint names, hosts and devices; marks (glyph plus label) instead of bare dots; no `transition`; nothing new to focus; `tabular-nums` through the existing `.num`; empty and
  not-configured states are sentences; the link in the Disks card is a real `<a>`; no hex outside the token block (the sparkline uses `currentColor` and `var(--line)`).
- Not applied, with reasons: *non-breaking space inside "312.4 Mbit/s"* (stored titles keep plain spaces so they stay searchable, docs/06 rule 18); *`Intl` numbers* (docs/06 section 2: no JavaScript on the page).

**Pre-push checks** (2026-10-03, before the push):
```
$ git log origin/main..HEAD --format="%ae %ce" | sort | uniq -c
      4 jyotirmoy.github@jyotirmoy.cc jyotirmoy.github@jyotirmoy.cc     (the commit holding this entry is the next, same identity)
$ git diff origin/main | grep '^+' | grep -ciE 'C:\\Users|jyotirmoyc|192\.168\.[0-9]|@[a-z0-9-]+\.(cc|com|io|net)|tk_[A-Za-z0-9]{20,}|BEGIN .*KEY'
0
```
No domain, secret, token, local path or LAN address in the diff; the only made-up credentials are `fake-gatus-password-not-real`, `fake-speedtest-token-not-real`, `fake-anon-token`
and addresses in `192.0.2.x` and `example.home.arpa`. Tests S5 (empty `secrets.env`), S6 (hostnames) and S8 (ASCII PowerShell) passed in the 585. No real Gatus, Scrutiny, speedtest-tracker or registry
request was ever made; the only network reads were public documentation and source (Gatus, Scrutiny, speedtest-tracker, Docker, the OCI spec, the guidelines).

**Not done / next.**
- [ ] Owner: open the pull request, verify it, merge with a merge commit, then `git pull` the main checkout (owner)
- [ ] M5 pounce + whiskers, on the owner's go-ahead (agent)
- [ ] M6 `ROLLOUT.md` additions (owner): the Gatus `gatus-api` router and the `perch-svc` Authelia rule (A8), `PERCH_GLARE_URL/_USER/_PASSWORD`, `PERCH_DISKS_URL=http://scrutiny:8080`,
  `PERCH_BINOCS_SPEEDTEST_URL/_TOKEN` (a `results:read` token), `PERCH_BINOCS_RELEASES_EVERY=7d`; check the real Gatus key of the tunnel check is `network_cloudflare-tunnel`, and that
  Scrutiny's collectors report `host_id` as the node names
- [ ] Owner decision: glare and disks late stopping nineLives' ping (see Notes below)

**Notes for the next agent.**
- `ScentTrail.retention()` is not called by perch itself (only by tests); vitals retention runs inside `Vitals.maintain`. Events and rollups retention is an M0 gap worth a look.
- nineLives holds its ping back while any collector is late, so a Gatus or Scrutiny outage of 3 cycles stops the outside heartbeat (M3's rule, now reached by glare
  and disks). Owner decision: keep, or exempt glare and disks.
- `ruff format .` reformats files this project never formatted (`tests/test_groomPage.py`, `tests/ui/budget.py`); format only the files you touch.

— Claude (Claude Code, Sonnet 5.5)

---

## 2026-10-02 — M3 meow + nineLives: litters, pushes, Acknowledge, the outside heartbeat; gate green

**Context.** The owner gave M3 its go-ahead (see the M2 entry's "next"), plus a first task: the grooming grid
relied on colour alone (his M2 check). Built by Claude Code (Sonnet 5.5) on roastery in a git worktree (branch
`claude/m3-meow-ninelives-cb0aa7`), 2026-10-02 20:25 to 23:15 IST, outside the quiet hours.

**Pre-flight (05 plan 3, A3), 20:25 IST, all passed:** `docker info` 29.7.2; `main` at `5e9d681` (M2's merge),
clean; `user.email` `jyotirmoy.github@jyotirmoy.cc`; `git ls-remote origin` answered; the three design skills in the
session's list and in `.claude/skills/`. The worktree had no `.cache`; I cloned the pinned fleet repo from the main
checkout's local copy (no network) and checked out `f94efdfb`.

**Docs read fresh before the code (2026-10-02).** ntfy (docs.ntfy.sh/publish; the fleet runs v2.28.0, the docs are
current): `Authorization: Bearer tk_...`; JSON publishing (`topic`, `title`, `message`, `priority` 1 to 5, `tags`,
`actions`); an `http` action has `label`, `url`, `method` (default POST), `headers`, `body`, `clear`, up to three per
message. That is enough for A11 (a POST with the token in the path), so no stop was needed. healthchecks.io
(healthchecks.io/docs/http_api, configuring_checks): a GET (also HEAD/POST) to the ping URL answers `200 OK`;
`/fail` and `/start` exist (not used); a missed ping makes the check "late" after its period and an alert after its
grace time; more than 5 pings a minute may be rate limited. Everything is tested against fakes
(`tests/pushFakes.py`: fake ntfy, fake critical topic, fake healthchecks); the real services were never contacted.

**Decided** (reasons; losing alternatives in brackets). Choices between alternatives are ADRs
[0004](docs/adr/0004-litters-and-node-absorption.md), [0005](docs/adr/0005-page-acknowledge-csrf.md),
[0006](docs/adr/0006-push-ack-token.md).
- **Task 1, colour alone.** Each grid cell is a 22 px disc with the badge glyph on it (`--bg` on the fill: 6.1 to 8.9:1,
  measured with the WCAG formula and added to docs/06 section 4); the glyph is `aria-hidden`, the label keeps all the
  words. [a coloured glyph with no fill: loses the red-at-a-glance a failed night should have; kept for lists.] The
  audit found five places where a state was a bare dot with no level word (tree, tree sidebar, node page app rows,
  overview last-night rows, copies panel): they use a new `.mark` (coloured glyph, no fill, 5.1 to 8.9:1). A dot beside
  a word (strip, chips, notes, header pill, footer) stays. docs/06 section 6 (Dot, Mark, grid) and section 7 rule 2
  updated.
- **meow reads states, not events** and keeps **litters** in scentTrail's database (migration 4: `litters`, `pushes`,
  `ackSpent`), so a restart forgets nothing and what is due, held or acknowledged is derived every cycle (ADR 0004).
  A node purr marks unreachable (`detail.mode = "unreachable"`, a one-line change in `purr.py`) is one litter that
  absorbs its apps, backups and kitten. purr leaves a dead node's apps `unknown`, not `hiss` (M1's rule: perch not
  seeing is not the thing being down), so "12 apps affected" counts the node's watched apps.
- **A subject that turns `unknown` keeps its litter**: Komodo going blind is not a recovery.
- **Routing as the plan says:** hiss to ntfy and the critical topic, both priority 4 (the design says "high" and leaves the
  critical topic's priority open), at once, repeated every 30 min until acknowledged, quiet hours ignored; tailFlick to
  ntfy only, held 5 min and batched (several at once are one push without a button), reminded at most every 6 h while
  open; earTwitch only in the 07:30 digest; every title starts `perch:`. A digest goes only in the 4 hours after 07:30, so
  a perch that was down in the morning doesn't send it at midnight. Recoveries of tailFlicks wait out quiet hours;
  hiss recoveries don't; several recoveries at once are one push.
- **Rate limit:** per channel, 10 per 10 min counted from a `pushes` table. A hiss may use 9, everything else 7, the 10th
  is the "N alerts held back" summary. What is held keeps `heldAt`, stays a litter, stays on the page and goes out as the
  limit allows; each held litter gets one event. [dropping or merging the overflow: breaks "never silently dropped".]
- **Acknowledge, page** (ADR 0005): same-origin check (`Sec-Fetch-Site` / `Origin` against `Host`; neither header means
  refuse) plus an HMAC form token bound to the litter, 6 h, key `PERCH_ACK_SECRET` (random per process when unset).
  [a session cookie: new state for one button; Origin alone: one check is the whole defence.] Parsed without
  python-multipart (`parse_qs`), so no new dependency. **Push** (ADR 0006): the token is signed over litter id and expiry,
  single use (`ackSpent`, `INSERT OR IGNORE`), 24 h or until the litter clears, 10 requests a minute on the path, one
  identical 403 for every refusal, the button only on the self-hosted copy and only on a push about one litter. All token
  routes are under `/ack/t/`.
- **nineLives** pings (GET) every 5 min only while every collector is on time (the runner's own levels, re-checked at
  each look), never `/fail`. A late or still-starting collector holds the ping back; its state `ninelives` (not rolled up
  into the fleet) feeds the footer: "nineLives pinged 2 min ago" or "holding its ping back: purr not on time" or "off".
- **Secrets:** `PERCH_MEOW_NTFY_URL` and `PERCH_PUBLIC_URL` are now treated as secret values (they carry the domain), so
  `scrub.py` masks them; it also masks the shape of an ack token, `/ack/t/...` links and hc-ping URLs. New settings
  `PERCH_MEOW_DIGEST` and `PERCH_PUBLIC_URL` are in `secrets.env` as empty keys (S5). No new dependency.

**Done.** `perch/{ack,litters,meow,ntfy,nineLives}.py`, scentTrail migration 4, `settings.py`, `scrub.py`,
`senses/purr.py` (one detail), `windowsill/app.py` (the two ack routes, the Alerts view, the footer line),
templates (`mark`, `ackForm`, the Alerts card, grid glyphs), `perch.css`, docs 02 section 5 and 06, ADRs 0004 to 0006,
`secrets.env`, CLAUDE.md status. Tests: `test_ack` (7), `test_meow` (28), `test_nineLives` (8), `test_ackRoutes` (29),
more in `test_scrub`, `test_groomPage`; `tests/ui/{seed,live,budget}.py` extended.

**Verified** (roastery, 2026-10-02 22:50 to 23:10, `powershell -ExecutionPolicy Bypass -File scripts\test.ps1`, after
the last code change, then pytest and the drill once more after renaming the fake tokens):
```
=== perch: ruff + pytest (3.12)  All checks passed!   479 passed in 174.99s
=== kitten: unittest (3.13)      Ran 14 tests ... OK
=== kitten: unittest (3.14)      Ran 14 tests ... OK
=== windowsill: Playwright       30 passed, 0 failed ; live: all ok
=== summary                      ok x6
```
- **Gate, in `tests/test_meow.py`:** `test_GATE_grinder_down_is_one_push_per_channel_then_one_recovery` (one push on the
  fake ntfy and one on the fake critical topic, "perch: grinder unreachable: 12 apps affected", priority 4; ten more minutes
  of outage send nothing; recovery is exactly one more push each, "grinder back, was down ..."; an hour later nothing
  else); `test_the_hiss_repeats_every_30_minutes_until_acknowledged`; `test_GATE_a_50_event_storm_...` (50 hisses in one
  tick: 10 pushes per channel, 9 hisses and the summary "41 alerts held back"; 9 pushed + 41 held = 50 open litters;
  no 10-minute window ever holds more than 10 per channel; after 90 more minutes every one of the 50 has been pushed at
  least once); `test_a_hiss_is_never_held_while_a_lower_level_could_be`.
- **S9, in `tests/test_ackRoutes.py`:** a tampered, expired, replayed, wrong-secret, closed-litter or never-existed push
  token is 403 and changes nothing (also `ackSpent` stays empty for tampered ones); a page ack without a CSRF token,
  with another litter's, an expired or a forged one, or without provable same origin (7 header cases) is 403; the 11th
  request a minute on `/ack/t/` is 429; `test_the_button_is_on_the_self_hosted_push_only_and_is_a_signed_post`: the
  critical copy has no actions. S7 (`test_windowsill`) still passes with exactly `/api/kitten`, `POST /ack/{litterId}`,
  `POST /ack/t/{token}`.
- **perch stopped, nobody pings:** `test_GATE_perch_stopped_means_the_endpoint_hears_nothing` and
  `test_GATE_a_late_collector_stops_the_pings_and_a_recovery_resumes_them` (`tests/test_nineLives.py`).
- **Task 1 in a real browser (`tests/ui/live.py`)**, 1400 dark, 1400 light, 390: "every judged cell has a visible glyph
  (shape, not only colour)" and "each glyph is at least 4.5:1 against its fill (lowest 6.2 / 6.6 / 6.2)", measured from
  computed styles. Also: the Alerts card's Acknowledge button clicked in Chromium: replaced by one line without a reload,
  one litter fewer waiting, acknowledged after a reload (htmx, CSRF token and same-origin headers all really worked).
- **The real-socket drill** (`tests/ui/budget.py` in `persian-perch:ui-test`, now with a fake ntfy, a fake critical topic
  and a fake healthchecks endpoint on loopback, `PERCH_ACK_SECRET`, `PERCH_PUBLIC_URL`):
  ```
  ok    grinder not answering: hiss
  ok    meow pushed grinder unreachable to the fake ntfy and the fake critical topic
  ok    the ntfy push carries one Acknowledge button (POST)
  ok    the critical copy carries none
  ok    tampered 403, button 200, replay 403 (want 403 200 403)
  ok    nineLives pinged the fake healthchecks endpoint
  ok    meow announced the recovery once
  perch memory: VmRSS 60.0 MB, peak 60.0 MB (budget 300 MB)
  leak check: looked in 12 places (4291 KB): nothing found      <- now also the ack token and secret, the ntfy token,
  budget, drill and leak check: ok                                 both topic URLs and the ping id
  ```
- **Screenshots looked at by eye**, both themes and 390 px: the Alerts card (coral Acknowledge buttons, 3 litters, the
  "not pushing yet" note), the groom grid with a "!" on a red disc and the "?" marks in Copies, the phone overview. Looking
  found nothing to fix beyond the review below.

**web-design-guidelines review** (AGENTS 3.1; guidelines fetched fresh 2026-10-02; **one pass, no sub-agents**, over
`_macros.html`, `base.html`, `groom.html`, `live/overview.html`, `live/node.html`, `tree.html`, `_treeNav.html`,
`perch.css`, and the two ack responses). Findings and what happened:
- `perch.css` `button.primary`: no `touch-action` → **fixed**: `touch-action: manipulation`.
- ack response: after the swap the focused button is gone and nothing announces it → **fixed**: the replacing line has
  `tabindex="-1" autofocus` (htmx focuses it) and an out-of-band sentence for the polite live region `#announce`.
- `.alerts` rows: long titles could overflow → **fixed**: `overflow-wrap: anywhere`.
- Passed: `<button>` for the action (not a link), `aria-label` starts with the visible word, hover and active states,
  decorative glyphs `aria-hidden`, the marks `role="img"` with a label, empty states (not configured, nothing pushed),
  `translate="no"` on identifiers, no `transition: all`, headings in order, no hex outside the token block, error pages for
  a refused ack. Title Case on the button ("Acknowledge").
- Not applied, with reasons: *confirm destructive actions* (acknowledging only stops repeats of an alert the owner has
  seen; reversible by the next hiss); *disable the button during the request* (one local POST, then the button is
  replaced; `includeIndicatorStyles` is off by ADR 0003); *`Intl` dates and curly quotes* (docs/06 section 2);
  *sticky header and focus* (existing; `scroll-margin-top` not needed on this page's controls).

**Pre-push checks** (run before the push, 2026-10-02):
```
$ git log origin/main..HEAD --format="%ae %ce" | sort | uniq -c
      3 jyotirmoy.github@jyotirmoy.cc jyotirmoy.github@jyotirmoy.cc
      (the commit holding this entry is the fourth, same identity; git config user.email = jyotirmoy.github@jyotirmoy.cc)
$ git diff origin/main | grep '^+' | grep -ciE 'C:\Users|jyotirmoyc|192\.168\.[0-9]|@[a-z0-9-]+\.(cc|com|io|net)|tk_[A-Za-z0-9]{20,}|BEGIN .*KEY'
1       <- the owner's allowed commit address, quoted in the pre-flight line above (S6 allows the full address only)
```
No domain, secret, token, local path or LAN address in the diff: the only token-like strings are made up
(`tk_fakefakefake`, `fake-ack-secret-not-real-...`, `fake-*` topics, `example.home.arpa`, `192.0.2.x`). Runtime files
were re-read as I wrote them; the tests include S5 (secrets.env empty), S6 (no hostnames), S8 (ASCII-only .ps1).
pytest in the full run: 479 passed (output above).

**Surprises for the next agent.**
- **I stopped every running container by mistake** while killing a hung test run (`docker ps -q | xargs docker kill`
  hit three unrelated containers: `purrbrews-bootstrap`, `komodo-periphery` (roastery's, a fleet service) and
  `immich-machine-learning`). I started the same three again within about 30 seconds (`docker start`); all were
  `Up` afterwards (they have `restart: unless-stopped`). Komodo may have seen roastery's periphery blink once. Lesson:
  kill by container id from the run I started, never all.
- The Bash tool fails to parse heredocs that contain apostrophes; Python edit scripts went through the Write tool.
- A long scenario test is slow on a purr-per-step world (about 80 ms a step); `MeowWorld.wait` steps only meow when the
  fleet isn't changing.
- Setting a unit-test fake clock backwards works because meow keeps no in-memory time.
- The ntfy fake token is shorter than a real one (`tk_` + 12) so a secret scanner won't mistake it for one.
- Not built: Gatus-side or healthchecks-side setup (owner, M6); the Traefik router for `/ack/t/` (M6-prep); a
  "meow's own events" filter on the scentTrail page (the trail already lists them under sense `perch`).

**Not done / next.**
- [ ] Owner: open the pull request from the link below, verify it, merge with a merge commit, then `git pull` the main
  checkout (owner)
- [ ] M4 glare + binocs + disks + vitals, on the owner's go-ahead (agent)
- [ ] M6 `ROLLOUT.md` (owner): create the ntfy user and token for perch, enter `PERCH_MEOW_NTFY_URL`, `_TOKEN`,
  `PERCH_MEOW_CRITICAL_URL`, `PERCH_ACK_SECRET`, `PERCH_PUBLIC_URL`, `PERCH_NINELIVES_URL` on cellar; a Traefik router for
  the `/ack/t/` prefix only, bypassing Authelia; the healthchecks.io check (period 5 min, grace 10 min); run old and new
  alerts side by side for a week (A6); the phone must reach `perch.${DOMAIN}` for the button (LAN or tailnet)
- [ ] Owner decisions M3 left open (all with a default in ADR 0004): critical topic priority (4 now), the 6 h reading
  of "once per litter per 6 h" (reminder), no acknowledge button on a batched tailFlick push

— Claude (Claude Code, Sonnet 5.5); the whole of M3 by the agent, decisions as the owner's earlier ones allowed

---

## 2026-10-02 — M2 Grooming: htmx live regions, groom, kitten v0, the grid; gate green

**Context.** The owner gave M2 its go-ahead (2026-10-02) and asked for htmx first (A12, ADR 0003), then the
rest of 05 plan §5's M2: groom records, the recorder (prepared only), kitten v0, `/api/kitten`, rhythms
from the repo, the grid and the copies panel. Built by Claude Code on roastery in a git worktree (branch
`claude/m2-grooming-htmx-bdeb90`), 2026-10-02 17:30 to about 18:30 IST, outside the quiet hours.

**Pre-flight (05 plan §3, A3), 17:30 IST, all passed:** `docker info` 29.7.2; `main` at `86c65dc`, clean;
`user.email` `jyotirmoy.github@jyotirmoy.cc`; `git ls-remote origin` answered; the three design skills in the
session's skill list and in `.claude/skills/`.

**Decided** (reasons; losing alternatives in brackets).
- **htmx, byte-exact.** The npm tarball's sha512 matched npm's `integrity` before extracting; `dist/htmx.min.js`
  is 52,182 bytes with SHA-256 `d6fdc75f…f717`; the blob committed in git hashes the same
  (`git cat-file blob`). `.gitattributes` marks `static/vendor/*` as `-text` so no line-ending conversion can
  change it. A test pins hash and size.
- **One poller per page, on a region, not the body.** `#live` does `hx-get` + `every 30s` + `hx-include="#seen"`
  against `GET /live/overview`, `/live/node/{n}`, `/live/app/{n}/{a}`. The fragment is the region plus the
  header's purr pill and fleet badge (out-of-band swaps). The page's HTML and the fragment's are the same
  template, so JavaScript off shows the state as of load. No new write endpoint: S7 passes unchanged.
- **"Announced once" without any JavaScript of our own.** The region carries a hidden `seen` (a 12-character
  digest of the levels a person would be told about). The poll sends it back; only if it differs does the
  fragment include one sentence for the polite live region `#announce` (`hx-swap-oob="innerHTML"`, so the
  live-region node itself is never replaced). A quiet poll sends no sentence. [announce on every swap: re-reads
  the page every 30 s; client-side diffing: needs our own JS; `204` on "unchanged": would freeze the ages.]
- **htmx configured for a read-only watcher:** `allowEval:false`, `allowScriptTags:false`,
  `includeIndicatorStyles:false`, `historyEnabled:false`, via a `<meta name="htmx-config">`. A consequence:
  no `hx-on` and no trigger filters like `[!document.hidden]`, so a hidden tab keeps polling (one small GET
  per 30 s; accepted). A failed poll leaves the old state on screen; every region says "State as of
  HH:MM:SS" so a stalled page shows its age.
- **Focus survives the swap by `id`.** htmx restores focus to a replaced element with an `id`; node cards,
  attention links, app links and the "All nights" / "Everything" links have stable ids (Playwright proves it).
- **groom judges a night with one function** (`judge` in `perch/senses/groom.py`) used by the grid and by the
  state it writes (`groom:<node>/<job>`): a good run is slowBlink; a good run that started later than the late
  limit is earTwitch ("ran 52 min late", the mockup's own example); a failed run is hiss; no record is slowBlink
  until the late limit, tailFlick after it, hiss at the missing limit. Design §3.4 gives nightly +45 min/+3 h,
  store +45 min/+3 h, Drive +2 h/+8 h. **My own calls for the jobs the plan didn't list** (C3): wake-roastery
  45 min/3 h (as strict as the nightly it serves), morning check 1 h/3 h, prune and restore check 3 h/12 h
  (they read the whole repository). Marked as an addendum in design §3.4.
- **Schedules come from the repo (C4).** `OnCalendar` of `purrbrews-backup@.timer` and cellar's six restic
  timers, parsed with the M1 parser; backup nodes = nodes with any `<app>/backup` file (cellar, grinder, mochaPot,
  percolator, sieve; roastery has none). A timer that can't be parsed means no expectation, never a guess.
- **A run counts for the latest slot it started at or after, give or take 15 min of clock skew, within 12 h.** An
  afternoon manual run isn't last night's backup; a `Persistent=true` run at boot still is. [nearest slot: a run
  at 14:00 would silently satisfy tomorrow's.]
- **No false hiss on a fresh deploy:** nights before perch first looked (`meta.groomStartedAt`) aren't judged,
  and **a node is judged only once it has a kitten token** (or, for cellar, when its records are mounted). The grid
  shows a faint dash and says why. [judge everything from day one: the first night after deploy would hiss five
  nodes.]
- **Groom and kitten states roll up** into the node and the fleet (and into "Needs a look"): a backup that
  didn't run, or an agent that went quiet, is a problem the node has. Kitten heartbeat: late 3 min, missing
  10 min; **roastery asleep outside its window is slowBlink** (the M1 `SleepWindow`, C5). A node with a token
  that never spoke is `unknown`, not ok.
- **`/api/kitten`:** bearer token compared against every node's token in constant time; none or unknown 401;
  another node's token, or a record for another node, 403 (S3); malformed 422; over 1 MiB 413; at most 100
  records. Records stored idempotently (`INSERT OR IGNORE`), log tail scrubbed, judged at once (so a failed
  backup shows on the next 30 s poll). The one write endpoint; S7 still passes.
- **Drive copy age from `drive-sync.ok`:** kitten sends the mtimes of `*.ok` files in `KITTEN_STATE_DIR` in its
  heartbeat; perch reads `drive-sync.ok` from cellar's. Without it, cellar's `drive` record stands in.
- **The recorder is Python, not shell** (`integration/groom/groom-record.py`, stdlib): JSON from bash is easy to
  get wrong, and every node has python3. It never fails the job (exits 0, drop-ins use `ExecStopPost=-`), writes
  atomically, 0644 in 0755. [patch `backup.sh` (Q13 = B): the owner chose A.] Drop-ins for the template and cellar's
  six units; a test cross-checks them against every job the pinned repo schedules.
- **kitten v0:** report every 60 s (jittered); a record is re-sent until a 200, ignored once older than 72 h; a
  422 sets that batch aside (logged) and keeps the heartbeat going; an outage is logged once, not every minute.
  Zipapp built by `kitten/build.py`; a test builds it and runs it on 3.13 and 3.14. New settings
  `KITTEN_STATE_DIR` and `KITTEN_NODE` added to `secrets.env` as empty keys (S5).
- **No new dependency.**

**Done.** `perch/windowsill/static/vendor/htmx-2.0.11.{min.js,LICENSE}`, `templates/live/*`, `app.py` (fragments,
`/api/kitten`, grid route), `perch/senses/groom.py`, scentTrail migration 3 (`groomRuns`, `meta`), `rollup.py`,
`groom.html`, `kitten/{kitten,build}.py`, `integration/groom/` (recorder, 7 drop-ins, README), docs 02 §3.4/§4.2,
docs 06 §6/§7, `secrets.env`, README and CLAUDE.md status. Tests: `test_htmx` (29), `test_groom` (33),
`test_kittenApi` (18), `test_groomPage` (16), `test_integrationGroom` (10), kitten 14 on each Python,
`tests/ui/live.py`.

**Verified** (roastery, 2026-10-02, `powershell -ExecutionPolicy Bypass -File scripts\test.ps1`, last run after the
final UI fix):
```
=== perch: ruff + pytest (3.12)  All checks passed!   402 passed
=== kitten: unittest (3.13)      Ran 14 tests ... OK
=== kitten: unittest (3.14)      Ran 14 tests ... OK
=== windowsill: Playwright       30 passed, 0 failed  (shoot.py) ; live: all ok (live.py)
=== summary                      ok x6
```
- **The gate, in `tests/test_groom.py`:** `test_GATE_a_missing_record_hisses_only_its_own_cell_at_0430` (a fixture
  night, grinder's record missing, clock 04:30 IST: `groom:grinder/nightly` hiss, the seven other judged cells
  slowBlink, grinder and the fleet hiss, sieve doesn't) and
  `test_the_cell_is_tailFlick_until_0430_exactly_then_hiss` (slowBlink at +44 min, tailFlick at +45 min and at
  04:29:59, hiss at 04:30:00).
- **The vendored htmx:** `test_the_vendored_htmx_is_exactly_the_pinned_file` (SHA-256 and 52,182 bytes) and
  `git cat-file blob HEAD:perch/windowsill/static/vendor/htmx-2.0.11.min.js | sha256sum` =
  `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`, 52182 bytes.
- **Playwright, a real browser (`tests/ui/live.py`), `ok` on every line:** htmx 2.0.11 loaded from perch; the
  overview refreshed on its own within 35 s, without a full reload (a `window` variable survived), by asking
  `/live/overview`, **keeping focus** (the focused node card) **and scroll position**; nothing announced while
  nothing changed; **a failed backup posted through `/api/kitten` showed on the open overview within 35 s, without
  a reload, announced through the live region**, and a later quiet poll said nothing new; under
  `prefers-reduced-motion` no element animates; no console errors; the grooming grid at 1400 dark, 1400 light and
  390 px has no horizontal scroll and no console errors.
- **The real-socket drill** (`tests/ui/budget.py` in `persian-perch:ui-test`): every step ok, **perch VmRSS 59.6 MB
  of 300**, leak check "looked in 11 places (4238 KB): nothing found", exit 0. Kitten tokens are never in a
  response, page or `/healthz` (`test_the_tokens_are_never_in_a_response_or_a_page`).
- **Screenshots looked at by eye**, both themes and at 390 px. Looking found two real problems the layout check
  passed: (1) the "Not watched yet" note broke into flex columns, and the lower grid squeezed to a narrow column at
  390 px; (2) after fixing that, **today's column was pushed off the right edge at 390 px**, hidden behind the table's
  horizontal scroll. Fixed (one text span; `cols-groom` collapses at 1000 px; the phone shows the last 5 nights;
  minimum column width only on wide screens), looked at again.
- **Pre-push checks:** see below.

**web-design-guidelines review** (AGENTS §3.1; guidelines fetched fresh 2026-10-02; **one pass, no sub-agents**,
over `base.html`, `_macros.html`, `overview/node/app/groom.html`, `live/*`, `perch.css`, and the htmx wiring).
Findings and what happened:
- `groom.html:` a "no data" dash was a `<span aria-label>` with no role (an `aria-label` on a generic element is
  ignored) → **fixed**: `role="img"`.
- `perch.css`: the grid's dot links had no `touch-action` → **fixed**: `touch-action: manipulation`.
- Passed: async updates use `aria-live="polite"` (and only for a change); decorative glyphs `aria-hidden`; real `<a>`
  for navigation; `:focus-visible` kept, hover state on the cells; reduced motion honoured (and tested); no
  `transition: all`; numerals and `tabular-nums`; empty states for every new view; long text wraps; filters
  (nights, selected run) live in the URL; `translate="no"` on identifiers; no hard-coded formats beyond the
  server-side ones; headings in order.
- Not applied, with reasons: *Title Case headings* (docs/06 §2: sentence case); *curly quotes / `Intl`* (docs/06
  §2 and the M1 entry: server-rendered, searchable straight text); *the selected cell's ring looks like the focus
  ring* (offset differs by 4 px and it is also `aria-current`; left, worth a look when someone uses the page by
  keyboard); *polling while the tab is hidden* (needs `allowEval`; see Decided).

**Surprises for the next agent.**
- Shell here: the Bash tool choked on some heredocs containing apostrophes; Python written from PowerShell/bash in
  text mode on Windows produced **CRLF** files (git warned; I normalised to LF before each commit). Use the Write
  tool or `newline=''`.
- Two tests failed for the same reason, worth knowing: events written in the same millisecond order randomly by
  ULID; tests that read "the newest event" must advance the fake clock first.
- A FastAPI route named `groom` shadowed a variable of the same name inside `createApp`; the route is now
  `groomView`, the object `groomer`.
- `kitten` on Windows: `KITTEN_STATE_DIR` defaults to empty there; the recorder is Linux only. Nothing of
  Windows kitten's Scheduled Task is built (M6, `integration/roastery/`).
- The copies panel has no roastery-repository size, snapshot age per host, or offline copy: they need restic data
  kitten doesn't read. Mockup 03's "Repository size" and "Restore tests from Drive" panels are not built.
- `/groom` is as-of-load (no polling): ADR 0003 names only the overview, node and app pages.
- Nothing was applied to any node and no secret was read; the only token-shaped values are made-up test strings
  (`fake-token-*`, `fake-ui-token-sieve-not-real`).

**Not done / next.**
- [ ] Owner: open the pull request from the link below, verify it, merge with a merge commit, then `git pull` the
  main checkout (owner)
- [ ] M3 meow + nineLives, on the owner's go-ahead (agent)
- [ ] M6 `ROLLOUT.md`: apply `integration/groom/` (recorder at `stacks/_lib/groom-record.py`, drop-ins), install
  kitten (zipapp, unit, `kitten` user, tokens), check `KITTEN_NODE` spelling per node, roastery's task (owner)
- [ ] Optional: restic data for the copies panel (snapshot age per host, repository size) via kitten or a read of
  the repository (owner decides)

— Claude (Claude Code, Sonnet 5.5); the whole of M2 by the agent, decisions as the owner's earlier ones allowed

---

## 2026-10-02 — Owner's decisions after M1: pull requests, htmx in M2, vitals in M4

**Context.** M1's pull request (#1) was verified independently before the owner merged it, and
left decisions for the owner. The owner asked what Claude would decide, then approved the
recommendations below ("your decisions look good") after merging #1.

**Verified before the merge** (Claude in chat, 2026-10-02, independent of the M1 entry's own
evidence):
- `scripts\test.ps1` on `ab311b0` in a separate clean checkout (`git worktree`, since removed):
  ruff clean, **296 passed**, kitten 4 + 4 OK (3.13, 3.14), Playwright **30 passed, 0 failed**,
  summary ok × 6. The real-socket drill (`tests/ui/budget.py` in `persian-perch:ui-test`): every
  step ok, VmRSS 59.1 MB of 300, leak check "nothing found" in 11 places, exit 0.
- gitleaks 8.30.1 (an independent scanner) over the PR's 17 commits: **no leaks**. Over the full
  history and tree: one hit, a false positive: `tests/test_scrub.py` line 49, the scrubber's
  deliberate fake `Authorization: Basic` value (decodes to `fake:fakefake`).
- All 17 commits, as on GitHub: author and committer `jyotirmoy.github@jyotirmoy.cc`.
- Komodo v2.3.2's own source (`moghtech/komodo`, tag `v2.3.2`): `ListContainers`,
  `ListAllContainers` and `ListServers` exist, `ListDockerContainers` doesn't: the adapter's
  reading is right. `httpx2` (ADR 0002) checked on PyPI and GitHub: `pydantic/httpx2`, Tom
  Christie, ~200 M downloads a month.

**Decided** (the owner's decisions, Claude's reasons).
- **Merge with a merge commit, never squash or rebase.** Runbook entries cite commit hashes as
  evidence (`4c02312`, `4ec6fb6`, `5342c65`, ...); both other methods rewrite them. The owner
  merged #1 that way (`ad87ef5`).
- **Pull requests are the rule** (AGENTS.md §5, 05 plan A2, step 7). The owner switched M1 to a
  PR mid-run, but A2 still said `git push origin main`, so the next builder would have pushed to
  `main`. Now: branch → gate → pre-push checks → push the branch → PR → stop; only the owner
  merges. This change itself goes in by PR.
- **htmx 2.0.11, vendored, as M2's first task** ([ADR 0003](docs/adr/0003-htmx-vendored.md),
  05 plan A12). 0BSD, so it may be committed to the public repo; served by perch, never a CDN;
  pinned by SHA-256 `d6fdc75f…f717` (checked against npm's integrity hash); 30 s polling of the
  state regions; SSE waits for M5. Not 4.0: npm tags it `next`.
- **Vitals history and sparklines in M4** with the disks (design plan §3.5 addendum, 05 plan
  A13): `vitals5m` for 7 days, `vitalsHour` for 400; inline SVG drawn on the server, in
  `--muted` (colour still means state). M4's gate grows to prove downsampling, retention and size.
- **Komodo's unverified details** (`ListServers {}`, `ServerState` spelling) stay M6 drill items:
  only the real Komodo can settle them, and a failure there shows `unknown`, never a false hiss.
- **M2's go-ahead** is given, effective once this pull request is merged.

**Done.** `AGENTS.md` §5; `docs/05-autonomous-build-plan.md` A2, A12, A13, §4 step 7, the M2 and
M4 scope and gates; `docs/02-design-plan.md` §3.5; `docs/adr/0003-htmx-vendored.md`; this entry
and the Backlog. On branch `docs/owner-decisions-m2`.

**Verified (this change).** `scripts\test.ps1` on roastery, 2026-10-02: the first run failed
S6 (`test_S6_no_unlisted_hostnames_in_tracked_files`) on this entry's own text, which named the
commit email's bare domain; reworded to the full allowed address, not by loosening the test.
Second run: ruff clean, 296 passed, kitten OK × 2, Playwright 30 passed, summary ok × 6.

**Not done / next.**
- [ ] Owner: merge the pull request for `docs/owner-decisions-m2` (merge commit) (owner)
- [ ] Builder: M2, starting with htmx per ADR 0003, on its own branch (agent)
- [x] Owner: the commit-email domain question in the Backlog: answered, it's the owner's personal domain (owner)

— Claude (chat, Opus 5.5), for the owner

---

## 2026-10-02 — M1 First purr: purr, rollups, live overview and catTree pages; gate green

**Context.** The owner gave the go-ahead for M1 (entry below, 2026-10-01) and asked Claude Code to
run the pre-flight incl. the A3 checks, claim M1, build it to its 05 plan §5 gate, review every
changed UI file with web-design-guidelines and put the findings here, then do A2. Midway the owner
changed the last step: **open a pull request instead of pushing to `main`**, and asked for an extra
pass to confirm nothing leaks a secret. Built on roastery in a git worktree (branch
`claude/m1-autonomous-build-788b18`, made by the desktop app), 2026-10-01 14:00 to 2026-10-02, outside
the 01:20-04:00 quiet hours, with three usage-limit pauses (the UI review workflow was resumed twice).

**Pre-flight (05 plan §3, A3), 2026-10-01 14:00 IST, all passed:**
```
docker info --format '{{.ServerVersion}}'  -> 29.7.2
git status --short --branch                -> ## claude/m1-autonomous-build-788b18   (clean)
git log --oneline -5                       -> da32ada agents: UI work follows the three design skills ...
git config user.email                      -> jyotirmoy.github@jyotirmoy.cc
git ls-remote origin                       -> 82a01bc7...  HEAD / refs/heads/main   (exit 0)
.claude/skills/                            -> design-analysis, design-taste-frontend, web-design-guidelines
```
`/skills` isn't available in the desktop app: the three skills are in the session's skill list and on
disk, and were read in full before any UI work. The pinned fleet repo was cloned at `f94efdf`.

**Decided** (the reasons; alternatives that lost in brackets).
- **The Komodo API, read from v2.3.2's own source** (`moghtech/komodo`, tag `v2.3.2`), not from memory:
  `POST /read {"type","params"}` with `x-api-key` / `x-api-secret`; `ListServers` (state, and CPU, RAM and
  disk already in `info.stats`) and **one `ListContainers` per Ok server**. Two traps found: v2.3.0
  renamed `ListDockerContainers` to `ListContainers`, and `ListAllContainers` pages at 30 by default, which
  would silently drop containers on a 60-container fleet [`ListAllContainers limit:0`: one call, but one
  node's failure hides the rest]. The adapter is one module (`perch/senses/komodo.py`) and can only send
  those two read types.
- **`httpx2` is the runtime HTTP client** ([ADR 0002](docs/adr/0002-httpx2-for-the-senses.md)); `httpx`
  isn't in the test image and starlette deprecates it for tests [stdlib `urllib` in threads: no transport to fake].
- **A hiss must be seen on two consecutive cycles (60 s) before it is written**: "no false hiss for a
  week" (dev plan M6) matters more than 30 s. A restart loop (3 in 15 min) is already confirmed and isn't held
  back; recovery is immediate. **Komodo unreachable turns everything `unknown`, never hiss** (design §8),
  after two failed cycles.
- **A restart = Docker's rounded uptime goes *down* and is *short* for the same container id**; a new id is
  a redeploy (a daily `git pull` must not make every app tailFlick). A property test over 1 s to 2 years found
  a real go-units quirk: for 30 minutes at the 2-year mark Docker prints "1 years" after "24 months". The
  "short" guard handles it; its regression test fails without the guard.
- **roastery's window comes from the repo**: wake from `purrbrews-wake-roastery.timer` (01:25), stay-up from
  roastery's `setup.ps1` (180 min), so 01:25-04:25; plus a **10-minute settle** (the nightly waits up to 10 min
  for roastery, 05 plan C3) before silence is a hiss. Outside the window it is slowBlink, "asleep, as
  expected". New setting `PERCH_SLEEPERS` (default `roastery`).
- **Only disk has thresholds** (85 / 95 %): that is all design 4.1 lists. CPU and RAM show as plain bars;
  a sustained-RAM rule needs history first.
- **Pages show state at load time**, with the age of purr's last look in the header ("purr 12 s ago"). **No
  htmx and no live refresh in M1**: vendoring htmx means downloading a third-party file, which needs the owner's
  yes (Backlog). **No sparklines**: scentTrail has no metrics store (design plan §3).
- **Apps with nothing to watch stay out of the rollup** (they'd hold the fleet at `unknown` for ever);
  **collector states count toward the fleet** ("a watcher that has gone quiet is a problem the fleet has").
- **What purr stores from Komodo is a short list**: app, image, state, Docker's status text, a label, up time,
  exit code, health, restarts: never labels, env, commands or mounts. State and event text is scrubbed anyway.
- The 10-line fix to test infra: in a git worktree `.git` is a file with a host path, so S6 and S8 failed
  with exit 128 in the test container; `scripts/test.ps1` mounts the main `.git` read-only and sets
  `PERCH_TEST_GIT_DIR`, which `tests/conftest.py` applies to this project's repo only.

**Done.** `perch/senses/{komodo,purr,dockerStatus}.py`, `perch/{rhythms,collectors,rollup,words}.py`;
`catTree` knows each app's `container_name`s; scentTrail migration 2 (`state.detail`) and `forget()`;
windowsill: overview (attention list, node vitals, apps-up, one line about what is off), node pages
(vitals, per-app state, containers no app owns), app pages (containers), a live header pill, error
pages; `docs/06` extended; tests: a fake Komodo built from the pinned fleet (`tests/komodoFake.py`),
fixtures shaped from the real structs, `tests/ui/{seed,budget,dump}.py`.

**Verified** (roastery, 2026-10-02, `powershell -ExecutionPolicy Bypass -File scripts\test.ps1`):
```
=== perch: ruff + pytest (3.12)  All checks passed!   296 passed in 56.84s
=== kitten: unittest (3.13)      Ran 4 tests ... OK
=== kitten: unittest (3.14)      Ran 4 tests ... OK
=== windowsill: Playwright       30 passed, 0 failed  (10 pages x 1400 dark, 1400 light, 390 dark;
                                 scrollWidth never above the viewport; no console errors)
=== summary                      ok x6
```
- **The M1 gate** (05 plan §5), in `tests/test_purr.py` with a fake clock:
  `test_GATE_n8n_exited_hisses_app_node_and_fleet_within_two_cycles_and_recovers` (n8n exited: held on
  the 1st look, `app:grinder/n8n`, grinder and the fleet hiss on the 2nd, 60 s; restored: all slowBlink;
  exactly one hiss event and one recovery event) and
  `test_GATE_roastery_asleep_outside_its_window_is_slowBlink_not_hiss` (plus: inside the window it is hiss
  once past the 10-minute settle). 25 more scenario tests cover the rules.
- **The same drill over a real socket and a real clock**: `docker run ... persian-perch:ui-test python
  budget.py` (an HTTP server speaking Komodo's API, `python -m perch` pointed at it, 2 s rhythm):
  ```
  ok    perch is up, purr has looked: slowBlink
  ok    n8n stopped: the overview hisses (two cycles)
  ok    n8n back: the overview is slowBlink again
  ok    grinder not answering: hiss          ok    grinder back: slowBlink
  ok    Komodo errors with the credentials in its body: purr is late
  ok    Komodo answers again: purr is back
  komodo requests served: 120, with a wrong path or key: 0
  perch memory: VmRSS 60.1 MB, peak 60.1 MB (budget 300 MB)        <- M0 alone: 39 MB
  control: the 500 body reached the overview and was masked: True
  leak check: looked in 11 places (4231 KB): nothing found
  budget, drill and leak check: ok
  ```
- Screenshots (gitignored) in `screenshots/` for every page; looked at by eye in both themes and at
  390 px. Looking found a real bug the layout check didn't: the node page's Apps table was squeezed to
  half width by its new column. Fixed, looked at again.
- **No secret leaks (the extra pass the owner asked for), seven checks:** (1) credential patterns
  (private keys, AWS/GitHub/Slack tokens, JWTs, ntfy `tk_`, passwords in URLs, long literals) over all
  tracked files: none outside `tests/`, and inside it only the deliberate `tk_fakefake...` fixture; (2) the
  same patterns over **every commit's diff on the branch** (all 17, added and removed lines, re-run on the final range with an extra
  "long literal assigned to a secret-named key" pattern): only the three deliberate fakes
  (`K-fake-key-...`, `S-fake-secret-...`, the bearer-shaped test string); (3) no tracked
  `*.env.local`, `*.key`, `authorized_keys`, `*.pem`, settings or browser-tool files; (4) the real domain
  appears nowhere (S6, and a grep: only the git identity); (5) no local path, username, temp dir or LAN
  address in anything added; (6) long hex/base64 blobs added: only the fake sequential ids in the Komodo
  fixture; (7) the runtime drill above, with Komodo echoing the key, the secret and a bearer token: none in
  perch's stdout/stderr, six pages, `/healthz`, or the SQLite db, wal and shm files. Plus tests: pages and
  `/healthz` never hold the key or secret, perch's log is scrubbed, `Settings` never prints them.
  `.playwright-mcp/` (browser-tool output, untracked) is now gitignored.

**web-design-guidelines review** (AGENTS §3.1; guidelines fetched fresh 2026-10-01). Seven independent
read-only lenses over `_macros`, `base`, `overview`, `node`, `app`, `perch.css` and the view helpers in
`app.py`, then a skeptical verifier per finding: the guidelines on markup, on node+app, on CSS; the design
system (docs/06 §3-§7); the taste pre-flight; accessibility of the **rendered** pages; a copy audit.
**113 findings: 70 real, 31 not applicable, 3 false positives, 9 copy-audit findings the verifiers never
reached (usage limit), which I judged by hand.** Every real finding was fixed (commits `4ec6fb6`,
`5342c65`; list in the second one). The ones not applied, with reasons (also in docs/06 §2):
- *Title Case for headings*: headings in the approved mockups are sentence case; Title Case is for buttons.
- *Curly apostrophes*: perch's copy and the event text it stores stay straight, so they can be searched,
  quoted and grepped; typographic quotes are used where perch quotes the repo.
- *`Intl.DateTimeFormat`*: there is no JavaScript; times are formatted on the server in `PERCH_TZ`.
- *"6 nodes" vs roastery's own role text "not a fleet node"* (unverified): that text is the fleet repo's;
  catTree lists every `stacks/<node>` with a `node.conf`.
- *"disk 88 % full" can wrap at the %*: event text is stored with plain spaces; the UI filters glue
  numbers and units, the stored sentence doesn't.
- The 31 not-applicable and 3 false positives were refuted by their verifiers with reasons (kept in the
  workflow journal, not in the repo); I spot-checked the ones on focus, motion and reduced motion.
Two M0 bugs came out of it: the "Good afternoon" greeting from 00:00 to 04:59, and an `unknown` tooltip
that read "unknown: unknown: no data yet".

**Surprises for the next agent.**
- Komodo's API was read from source and fixtures, **never run against a real Komodo 2.3.2**. Unverified:
  `ListServers` with `params: {}` (it relies on server-side defaults), and the JSON spelling of `ServerState`
  (the adapter accepts `Ok`/`NotOk` and `ok`/`not-ok`). Both go on the M6 drill list.
- In a worktree, tests need `PERCH_TEST_GIT_DIR` (`scripts\test.ps1` sets it). Docker Desktop's bind mount
  is slow (~55 s suite); the test image can vanish after a Docker restart: the script rebuilds it.
- A usage-limit pause killed agents in the middle of the review workflow: the run is resumable
  (`resumeFromRunId`), completed agents are cached, but check the failure list before trusting a count.
- `.claude/skills/` stays local and gitignored (third-party texts); a fresh checkout has none.
- This PR carries the owner's four earlier local commits (design rework, docs), not yet on `origin/main`.
  After it merges, the main checkout's local `main` needs `git pull`.

**Not done / next.**
- [ ] Owner: review and merge the M1 pull request (the owner asked for a PR, not a push to `main`)
- [ ] Owner: decide on vendoring htmx for live refresh (a third-party file; needed by M3's Ack and M5's SSE)
- [ ] Owner / agent: vitals history and sparklines (mockup 01) need a metrics table the design plan lacks
- [ ] M6 drills for `integration/ROLLOUT.md` (05 plan C12): stop a container on grinder -> hiss within 60 s
  and back to slowBlink; check `ListServers {}` and the `ServerState` spelling against the real Komodo 2.3.2;
  roastery inside and outside its 01:25-04:25 window
- [ ] Optional: sustained CPU/RAM rules once there is history (design 4.1 has only disk)
- [ ] Agent: M2 Grooming, on the owner's go-ahead after this PR

— Claude (Claude Code, Sonnet 5.5); pre-flight, M1 build, UI review, verification and leak pass by the agent

---

## 2026-10-01 — The three design skills become a rule for every UI change

**Context.** The owner asked that the builder (Claude Code, from M1) be held to the three
skills the design rework used. Claude Code on roastery didn't have them: its only skills
were the official marketplace plugins.

**Decided.**
- **Installed as Claude Code project skills** in `.claude/skills/<name>/SKILL.md`, which
  Claude Code loads for this folder. Each file is byte-identical to the copy the rework
  used (SHA-256 checked):
  - `design-taste-frontend`, from `github.com/Leonxlnx/taste-skill`
    (`skills/taste-skill/SKILL.md`), `aa194351…`;
  - `web-design-guidelines`, from `github.com/vercel-labs/agent-skills`
    (`skills/web-design-guidelines/SKILL.md`), `f4647ca8…`;
  - `design-analysis`, carried over from the chat session (no public source found),
    `26fac9ce…`.
- **Gitignored** (`.claude/skills/`, plus `.claude/settings.local.json`): third-party texts
  whose licences aren't ours to redistribute, in a public repo. The copies live on roastery
  only. `design-analysis` has no public source; if roastery loses it, ask the owner to
  re-provide it.
- **The rule** is AGENTS.md §3.1 (with a short form as CLAUDE.md rule 8): every change to
  `perch/windowsill/` or `mockups/` follows all three, under `docs/06-design-system.md`,
  which wins where they disagree (it records where the skills were overruled and why).
  `design-taste-frontend`'s stack defaults (React, Tailwind, Motion, icon libraries, web
  fonts) never apply. A missing skill is a stop, not a guess.
- **Enforced at the gate:** the 05 plan §4 step 7 now requires the web-design-guidelines
  review of every changed UI file, pasted into the milestone's runbook entry.

**Done.** `.claude/skills/` (3 files, local), `.gitignore`, `AGENTS.md` §3.1, `CLAUDE.md`
rule 8, `docs/05-autonomous-build-plan.md` §4 step 7.

**Verified.** SHA-256 of all three installed files matched (PowerShell `Get-FileHash`,
roastery, 2026-10-01); `git status` shows `.claude/` untracked-and-ignored, not listed.

**Not done / next.**
- [ ] Claude Code: confirm at session start that it lists the three skills (`/skills`) before
  any UI work in M1 (agent)

— Claude (chat, Opus 5.5), for the owner

---

## 2026-10-01 — Design rework: design-analysis look, taste discipline, Web Interface Guidelines

**Context.** The owner asked for the design to be reworked with three skills:
design-analysis (the visual language), design-taste-frontend (anti-default discipline) and
web-design-guidelines (Vercel's Web Interface Guidelines, fetched fresh 2026-10-01). The
owner had already started on 2026-09-30 18:46 (uncommitted: `perch.css` and seven
templates, moving to cream canvas, coral and a serif display face; it pointed to a
`docs/06-design-system.md` that didn't exist yet). The owner confirmed it was theirs and to
build on it.

**Decided** (full reasoning in [docs/06-design-system.md](docs/06-design-system.md) §2).
- **Design read:** a private, read-only ops dashboard for one owner, calm editorial
  language, design-analysis tokens. Dials: variance 3, motion 2, density 6.
- **Serif only for page titles and the wordmark.** design-taste-frontend discourages serif
  for dashboards; its own override applies because the owner named design-analysis.
  **Counts are tabular sans**: the serif's old-style figures bob in a column.
- **Coral is scarce: on this page colour means state.** persianPerch is read-only, and coral
  sits between tailFlick amber and hiss red, so it reads as a third alarm. It stays on the
  brand mark, the active-nav bar and the one future action (M3's Ack, `--accent-fill`).
  Links are ink.
- **Repo content in a dark code window** (design-analysis' dark product surface), in both
  themes: READMEs and repo files. "The repo says" never looks like "perch says".
- **No glass:** solid header (taste: no glassmorphism on dashboards; no transparency
  fallback needed).
- design-analysis is Anthropic's own brand: its logic is borrowed, never the spike mark, the
  Claude wordmark or the licensed fonts.

**Done.**
- `perch.css`: new tokens `--control` (3:1 edges), `--accent-fill`, `--code-*`; `--faint`
  darkened; ink links; solid header; coral active-nav bar; sans tabular counts; `.codewin`;
  pressable chips and inputs on `--control`; `.dayhead`, `h1.path`; tab rule scoped to
  direct children.
- Templates: fleet badge `fleet: <level>` (one middle dot per line); trail day headings
  `h2` (were `h3` under `h1`), `Apply Filters`, `<select>` styled by CSS instead of a
  transparent inline style; app page's inert ARIA "tabs" replaced by a sentence; README and
  doc pages in `.codewin`; doc page breadcrumb is a `<nav>`, `↗` hidden from screen readers.
- `tests/test_windowsill.py`: the two assertions on the badge text follow the copy change.
- Mockups: each one's own `<style>` (identical in all five) replaced by a link to
  `perch.css` plus the mockup-only `.mockflag` rule; every `var()` they use is defined.
- `docs/06-design-system.md`: design read, the reconciliation, tokens, measured contrast,
  type, components and a 14-point checklist for future changes.

**Verified.**
- Contrast measured with the WCAG formula, both themes (table in docs/06 §4). Three
  light-mode failures fixed: white on coral 3.28 → 4.8 (`--accent-fill`), control edges
  1.34 → 3.6 (`--control`), `--faint` on `--panel2` 4.21 → 4.8.
- `scripts\test.ps1` on roastery, 2026-10-01 13:14: ruff all checks passed; pytest 86
  passed; kitten 4 + 4 OK (3.13, 3.14); Playwright 21 passed, 0 failed (7 pages × 1400 dark,
  1400 light, 390 dark; no horizontal scroll, no console errors). Summary ok × 6.
- Screenshots of the overview and an app page (1400, light) looked at by eye.
- `git diff --check` clean; changed files stay LF.

**Not done / next.**
- [x] Owner: looked at the screenshots and mockups; "they look perfect" (2026-10-01)
- [ ] Builder (M1 onward): follow docs/06 §7 for every UI change (agent)

— Claude (chat, Opus 5.5), with the owner's 2026-09-30 rework as the base

---

## 2026-09-30 — Builder changes from Cowork to Claude Code, from M1

**Context.** After M0 was built, pushed (`82a01bc`) and stopped at its gate, the owner
changed the builder for the rest of the build (05 plan Q4).

**Decided.**
- **Claude Code on roastery builds M1 onward** (05 plan Q4 = A, A3 rewritten): PowerShell,
  working directory = this folder, so `CLAUDE.md` loads by itself. Everything else in the
  05 plan stands: pre-flight with the A3 checks every session, A2 (push at a green gate,
  then stop for the go-ahead), containers-only tests via `scripts\test.ps1`, quiet hours.
- Claude Code never runs with permission prompts skipped, and asks before any command
  outside this folder (AGENTS.md rule 1).
- M0 stays as Cowork built it; nothing is redone. The CI Backlog item stays the owner's
  call: `.github/` was only blocked for Cowork's file tools, but switching Actions on for
  a public repo is still a decision for the owner, not the builder.

**Done.** `docs/05-autonomous-build-plan.md`: Q4 answer and A3 row (2 lines; checked with
`git diff`, no other change to the file).

**Verified.** `git status`: `main` level with `origin/main` at `82a01bc`; the only change is
the 05 plan's two lines plus this entry.

**Not done / next.**
- [ ] Owner's go-ahead for M1, then Claude Code runs the pre-flight and starts M1 (owner, agent)

— Claude (chat, Opus 5.5), for the owner

---

## 2026-09-30 — M0 Litter: catTree, scentTrail, windowsill skeleton; gate green

**Context.** The owner asked Cowork to build persianPerch: read the rules and the spec, run
the 05 plan's pre-flight including the A3 checks, make the A1 baseline commit, then build
M0 and stop at its gate (A2). Session on roastery, 17:35–18:30 IST (outside the
01:20–04:00 quiet hours).

**Pre-flight (05 plan §3, A3), all passed** (roastery, PowerShell, 17:35):
```
docker info --format '{{.ServerVersion}}'   -> 29.7.2
git status --short --branch                 -> ## main...origin/main, README.md and docs/04 modified,
                                               AGENTS.md CLAUDE.md runbook.md docs/05 secrets.env untracked
git log --oneline -5                        -> 2f6fafc first push
git config user.email                       -> jyotirmoy.github@jyotirmoy.cc
git ls-remote origin                        -> 2f6fafcb...  HEAD / refs/heads/main   (exit 0)
secrets.env                                 -> 36 keys, 0 with a value, 0 non-ASCII bytes
```
The uncommitted files were the owner's planning work; A1 says to commit them, so they went
into the baseline **`4c02312` docs: baseline of plans, agent rules, runbook and
secrets.env**, added by name, before any M0 code.

**Decided.**
- **`unknown` is a fifth display state**, ranked `slowBlink < earTwitch < unknown <
  tailFlick < hiss`, icon `?`, grey `#6d6259` (the mockups' `--unknown`). Design §8 already
  shows purr as "unknown (grey)" when Komodo is down; with no sense running yet, every app
  is unknown, and the fleet badge says so instead of a false slowBlink. It outranks
  earTwitch so a notice never hides that perch can't see something, and never masks a
  tailFlick or hiss.
- **scentTrail uses stdlib `sqlite3` behind a lock, not `aiosqlite`** (dev plan §1 said
  aiosqlite). perch writes a few rows per second at most; FastAPI runs sync routes in a
  thread pool; one dependency fewer. Dev plan §1 updated. Migrations are numbered and
  tracked in `PRAGMA user_version`.
- **A damaged scentTrail is moved aside, never deleted** (`scentTrail.db.corrupt-<time>`),
  and perch starts empty with a hiss event saying so (design §8).
- **catTree reads only tracked files and never follows a symlink.** Beyond `git ls-files`
  and the deny-list, `read()` refuses untracked paths, symlinks and anything resolving
  outside the checkout: a tracked symlink `docker-compose.yml -> secrets.env.local` would
  otherwise have leaked through the deny-list. git runs with `-c safe.directory=*` because
  the checkout is mounted read-only and owned by another user. The deny-list stays exactly
  the spec's (`*.env.local`, `secrets.env.local`, `*.key`, `authorized_keys`), so the fleet's
  `authorized_keys.example` template is listed.
- **catTree shape:** nodes are `stacks/<node>/` folders with a tracked `node.conf`, in
  `fleet.env`'s `*_LAN_IP` order; apps are `APPS=(...)` in order; other folders (cellar's
  `restic`, `nfs`, roastery's `flask`, …) are listed as "also in the repo, not in
  node.conf". A node's role is the first sentence of `node.conf`'s header comment. The
  tree is rebuilt only when the checkout's HEAD moves.
- **Tests run in a small test image** (`tests/Dockerfile`: the pinned `python:3.12-slim`
  plus `git`), not bare `python:3.12-slim` as 05 §3 wrote: catTree and S5/S6/S8 need git.
  05 §3 annotated. **The UI check builds `tests/ui/Dockerfile`** (the pinned Playwright
  image plus `playwright==1.56.0`): Microsoft's image carries the browsers but not the
  Python package (the first run failed with `ModuleNotFoundError: playwright`).
- **Pinned images (tag @ digest)**, pulled on roastery 2026-09-30:
  - `python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f`
  - `python:3.13-slim@sha256:7c61056e61ac89e852de05f3dc6fa51a6dd2181797bceed46aa725dd7cb2cd3b`
  - `python:3.14-slim@sha256:51dafde81dbdb6ebde285137a295cf18a47ca95234fe388a343719cb97305b3d`
  - `mcr.microsoft.com/playwright/python:v1.56.0-noble@sha256:a7f6cf3ae520c9d670ad956572c13747ed5abdbba5123a01526f873ed1662528`
- **Dependencies** (pinned in `requirements*.txt`): fastapi 0.142.2, starlette 1.7.0,
  uvicorn 0.54.0, jinja2 3.1.6, tzdata 2026.4 (zoneinfo data inside a slim image, for
  `PERCH_TZ`); dev: pytest 9.1.1, ruff 0.16.9, **httpx2** 2.13.1 (starlette 1.7 deprecates
  `httpx` for its TestClient and the suite turns warnings into errors).
- **The fleet clone is made with `core.autocrlf=false`** so the fixtures have LF endings,
  exactly as the Debian nodes see them (roastery's git has `autocrlf=true`).
  `.gitattributes` keeps this repo LF, with CRLF only for `*.ps1`.
- **S6 (hostnames)**: URLs are checked whatever their TLD; bare names only on TLDs that
  don't collide with code (`node.app`, `backup.sh`). Allow-list in
  `tests/test_repoHygiene.py`. One exact string is allowed although it holds a host: the
  git identity `jyotirmoy.github@jyotirmoy.cc` that AGENTS.md requires (already public in
  every commit). If that domain is also the fleet's real domain, the owner may want it out
  of AGENTS.md/CLAUDE.md; the commits carry it regardless.
- **kitten** (ADR 0001, C11): stdlib-only; M0 holds only its settings and a test that fails
  if a kitten module imports anything outside the standard library. `KITTEN_POUNCE_PATHS`
  separates paths with `;` (Windows paths contain `:`); new `KITTEN_NODE` (defaults to the
  host name). Dev plan §3 updated.
- **CI file not active.** `.github/` is a protected path for Cowork's file tools, and
  switching GitHub Actions on for a public repo is the owner's call, so the workflow sits
  in `ci/github-actions-ci.yml` (same checks as `scripts/test.ps1`). Backlog item added.

**Done.**
- `.gitignore` (05 M0 list + caches), `.gitattributes`, `.dockerignore`, `pyproject.toml`
  (ruff + pytest settings), `requirements.txt`, `requirements-dev.txt`.
- `perch/`: `bodyLanguage.py` (levels, icons, colours, `worstOf`), `settings.py` (every
  `PERCH_*` from `secrets.env`; secrets never in `repr`), `scrub.py` (known values, `*_PASSWORD
  /TOKEN/SECRET/KEY=` values, bearer/basic/ntfy tokens, URL passwords; 16 KB tail),
  `scentTrail.py` (WAL, migrations, events/state/rollups, retention 90 d / 400 d, ULIDs),
  `catTree.py`, `windowsill/` (FastAPI app, Jinja2 templates, `perch.css` = the mockups'
  CSS plus a small additions block). Pages: `/` perch overview, `/tree`, `/tree/{node}`,
  `/tree/{node}/{app}`, `/tree/docs/{path}`, `/groom` and `/trail` (placeholders until their
  senses), `/healthz`. GET only.
- `kitten/kitten.py` (settings only), `Dockerfile` (non-root uid 10001, healthcheck),
  `compose.example.yml`, `scripts/test.ps1` (ASCII; quiet-hours guard; pins the fleet
  repo; runs every step and a summary), `tests/` (86 pytest + 4 kitten unittest + the
  Playwright check), `docs/adr/0001-kitten-stdlib-zipapp.md`.
- Spec fixes (05 §0 says fix a doc in the first commit that touches its area): dev plan §1
  (store, kitten files, tests) and §3 (C10 settings, per-node kitten tokens, glare URL per
  Q12), 04 §4 "Debian 12" → Debian 13 (C11), 05 §3 test commands annotated, README status.

**Verified** (roastery, `powershell -ExecutionPolicy Bypass -File scripts\test.ps1`, 18:25):
```
=== fleet repo pinned            fleet repo at f94efdfb1995d7217ec2be33e45b33720a0a0b3b
=== perch: ruff + pytest (3.12)  All checks passed!   86 passed in 54.47s
=== kitten: unittest (3.13)      Ran 4 tests in 0.007s  OK
=== kitten: unittest (3.14)      Ran 4 tests in 0.007s  OK
=== windowsill: Playwright       21 passed, 0 failed   (7 pages x 1400 dark, 1400 light, 390 dark;
                                 scrollWidth never above the viewport; no console errors)
=== summary                      ok x6
```
- Gate items: S1 (`test_catTree.py::test_S1_*`, `test_windowsill.py::test_S1_*`), S5, S6, S8
  (`test_repoHygiene.py`), S7 (`test_windowsill.py::test_S7_*`: no non-GET route; POST/PUT/
  PATCH/DELETE → 405); `/tree` lists every node and all 48 apps of the pinned repo
  (`test_tree_lists_every_node_and_app`, each app page 200); C15 (`test_every_node_and_every_app_appears`
  parses every `node.conf` independently).
- Screenshots: `screenshots/{perch,catTree,catTree-node,catTree-app,catTree-doc,groom,scentTrail}-{1400-dark,1400-light,390-dark}.png`
  (gitignored; sample events from `tests/ui/seed.py`).
- Budget (05 §4 step 9): the image run alone, 80 page loads, then
  `docker stats --no-stream` → `perch-budget mem=39.22MiB cpu=0.09%`; healthcheck `healthy`;
  `/healthz` → `{"ok":true,"schemaVersion":1,"journalMode":"wal","commit":"f94efdfb1995"}`.

**Pushed (A2), 18:40.** Pre-push checks on `4c02312..42c97fe`: `git log origin/main..HEAD
--format='%ae %ce'` → only `jyotirmoy.github@jyotirmoy.cc` (both commits); the diff read
through, plus a scan of its 3,736 added lines → no host outside the S6 allow-list, and the
only secret-shaped strings are the deliberate fakes in `tests/` (`tk_fakefake…`,
`Bearer abcdefghijklmnop`, a JWT header); tests green (above, and `86 passed` again with
everything staged). `git push origin main` → `2f6fafc..42c97fe  main -> main`;
`git ls-remote origin refs/heads/main` → `42c97fe4…`. This note is the follow-up commit.

**Surprises for the next agent.**
- **Cowork's file bridge stamps a C2PA provenance manifest into SVG files it writes**
  (`perch.svg` arrived as 8 KB with a C2PA metadata block). It was rewritten byte-exact from
  base64 in PowerShell and checked by MD5; every other file was checked by MD5 against the
  source too. Test S6 would have caught it once tracked. Write SVGs as bytes, then verify.
- Windows PowerShell 5 turns a native tool's stderr into error records; `scripts/test.ps1`
  judges each step by its exit code only. The bind-mounted suite takes ~55 s on roastery
  (~2 s natively): Docker Desktop's Windows mounts are slow, not the tests.

**Not done / next.**
- [ ] Owner: go-ahead for M1 (A2). M1 = purr against a faked Komodo v2.3.2 `/read` API,
  rollups, live overview and app pages, collector rhythms, roastery's sleep window (C5).
- [ ] Owner, optional: enable CI by moving `ci/github-actions-ci.yml` to `.github/workflows/ci.yml`.
- htmx and SSE are not in the page yet: nothing refreshes live until M1 brings live data.

— Claude (Cowork, Opus 5.5); pre-flight, baseline commit, M0 build and verification by the agent

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
