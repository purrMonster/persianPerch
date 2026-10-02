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
- [ ] M2 Grooming: **htmx first** (A12), then groom records, kitten v0, the backup grid; fleet-script change prepared in `integration/`
- [ ] M3 meow + nineLives: alerts, litters, quiet hours, outside heartbeat
- [ ] M4 glare + binocs + disks + vitals: Gatus, Scrutiny, tunnel, speedtest, upstream releases, vitals history and sparklines (A13)
- [ ] M5 pounce + whiskers: kitten file events, Home Assistant, the scentTrail view
- [ ] M6 Into the fleet: prepared in `integration/` with `ROLLOUT.md`; deployed by the owner

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
