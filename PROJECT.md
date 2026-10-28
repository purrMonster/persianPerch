---
project: persianPerch
status: active
status_reason: v0.1.0 is released and the fleet pins its image; nothing has been deployed yet, the next step is the owner's rollout
resume_trigger: n/a
last_activity: 2026-10-21
last_reviewed: 2026-10-23
repo: https://github.com/purrMonster/persianPerch
related: ["[[purrbrews-containers]]"]
tags: [project]
---

# persianPerch

## What it is
The read-only **unified watcher** of the purrBrews fleet: one private page, shaped like the fleet repo (catTree),
that shows containers and vitals (purr), backups (groom), endpoints and disks (glare), the outside web (binocs),
file drops (pounce) and smart-home events (whiskers), live and with history (scentTrail), plus alerts (meow).
It is for the owner only, and it never changes the fleet.
Stack: Python 3.12, FastAPI, Jinja2 + vendored htmx, SQLite, one container on cellar, and a stdlib agent (kitten) on each node.

## Current state
| Area | State | Evidence |
|---|---|---|
| Code | built: M0–M6 merged (M6 = fleet integration prepared as files, applied by the owner) | [runbook.md](runbook.md) Backlog; merge `0b34d4c` (PR #13) |
| Release | v0.1.0, image `ghcr.io/purrmonster/persian-perch:0.1.0@sha256:c1bce82d…` | tag `v0.1.0` → `68d802b`; GitHub release v0.1.0; [CHANGELOG.md](CHANGELOG.md) |
| Deployment | not deployed. Fleet #65 pins the image in cellar's compose, but that is configuration, not a run | [runbook.md](runbook.md) 2026-10-21 "After fleet #65": "Where we stopped: perch bring-up, step A1" |
| Tests / CI | passing: ci.yml run #7 on `main` @ `0b34d4c`, 2026-10-20; nothing has been tested against the live fleet | [.github/workflows/ci.yml](.github/workflows/ci.yml); [README.md](README.md) status |

## Open points
1. Owner: the rollout, starting from [ROLLOUT.md](integration/ROLLOUT.md) step A1 (Komodo's read-only key), then A–K. It includes the J drills: a hiss within 60 s, Komodo 2.3.2 spellings, and roastery in and out of its window. ([runbook.md](runbook.md) 2026-10-21)
2. Owner: open decision from M4: should glare and disks stop nineLives' ping when they are late? (Backlog)
3. Owner, before rollout step K: check roastery's sleep setting, since it was formatted on 2026-10-07. (Backlog)
4. Owner, GitHub settings: private vulnerability reporting on, e-mail privacy for web merges ([runbook.md](runbook.md) 2026-10-14 "Public-repo review")
5. Owner, fleet: should `PERCH_TRUSTED_PROXIES: "*"` name Traefik only? (same entry)
6. Owner, cleanup: delete the stray `latest` tag on GHCR, and the unused `PERSIAN_PERCH_REF=` line in cellar's `.env.local` ([runbook.md](runbook.md) 2026-10-21)
7. Release 1.0.0 comes after the drills pass and a week passes with no false hiss ([CHANGELOG.md](CHANGELOG.md))

## Branches
- `claude/readme-badges`: README badges. It was merged as PR #12 (`268e062`, 2026-10-15) and is stale, so it can be deleted (owner's call).

## Key decisions
- 2026-09-30 · kitten is a stdlib-only zipapp (inotifywait on Linux, polling on Windows) · [ADR 0001](docs/adr/0001-kitten-stdlib-zipapp.md)
- 2026-10-02 · htmx 2.0.11 vendored for live regions · [ADR 0003](docs/adr/0003-htmx-vendored.md)
- 2026-10-02 · agents open PRs; only the owner merges, with merge commits · [AGENTS.md §5](AGENTS.md); [runbook.md](runbook.md) 2026-10-02 "Owner's decisions after M1"
- 2026-10-02 · litters: one push per incident; a node that is down absorbs its apps · [ADR 0004](docs/adr/0004-litters-and-node-absorption.md)
- 2026-10-02 · acknowledge from a push via a signed, single-use token · [ADR 0006](docs/adr/0006-push-ack-token.md)
- 2026-10-03 · pounce reports file names and change types only, never contents · [ADR 0010](docs/adr/0010-pounce-names-only-events-over-the-kitten-report.md)
- 2026-10-03 · how perch and kitten reach the fleet (labels; kitten delivered by pull) · [ADR 0012](docs/adr/0012-m6-how-perch-reaches-the-fleet.md)
- 2026-10-03 · `/etc/purrbrews` changes go to the digest only; whiskers never hisses about itself · [ROLLOUT.md](integration/ROLLOUT.md) "The decisions this rollout rests on"
- 2026-10-14 · releases are images published from `v*` tags only; the fleet pins tag@digest · [runbook.md](runbook.md) 2026-10-14 "Release 0.1.0 prepared"
- 2026-10-21 · no `latest` tag (`flavor: latest=false`); the GHCR patch is retired · [runbook.md](runbook.md) 2026-10-21

## How to resume
1. Orient: [AGENTS.md](AGENTS.md), [CLAUDE.md](CLAUDE.md), the Backlog and the newest three entries in [runbook.md](runbook.md), `git pull`, `git log -10`.
2. Owner: work through [ROLLOUT.md](integration/ROLLOUT.md) from step A1, on the nodes, in order.
3. Agent: support the rollout from fixtures only (no SSH or API calls without a go-ahead), and record each drill's result as a dated runbook entry.
4. Once the drills pass: decide on open point 2, then plan 1.0.0.

## Decisions to remake
- **groom's backup model.** groom and ROLLOUT E assume restic on roastery plus the Drive copy. If the fleet's backup chain changes, groom's records, the recorder drop-ins and the drills need re-checking before step E. (Not confirmed from this repo: see Questions.)
- **The test pin.** Tests pin the fleet at `97f56ce`. If the fleet moved again, re-pin and re-run CI before the deploy, as the 2026-10-14 repass did.

## Questions for Roastmaster
- Is persianPerch paused right now, waiting on the purrBrews freeze or the weekly-only rhythm, or is the rollout next? This card says `active` because the repo shows no pause.
- Is the restic-on-roastery + Drive backup chain still the plan? If not, groom and ROLLOUT E need rework before the deploy.
- Has any rollout step (A1 onward) been done on the nodes since 2026-10-21? The runbook has no entry for one.
- Were the GitHub settings (private vulnerability reporting, e-mail privacy) changed? The repo can't show this.
- Delete the merged `claude/readme-badges` branch?

## Card history
- 2026-10-23 · created by Claude (Opus 5.5, cloud session via roastery), from `origin/main` @ `0b34d4c`
