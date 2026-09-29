# persianPerch — Ideation

> **persianPerch** · Breed + Feline Behavior · *Unified Watcher*
> Observability across containers, filesystems, smart-home and web, for the purrBrews fleet.
>
> Status: **ideation** · 2026-09-29 · owner: barista (Jyotirmoy)

---

## 1. Why this exists

Today, knowing whether purrBrews is healthy means opening five different places, and the
most important question — *did everything that was supposed to happen actually happen?* —
has no answer anywhere:

| Question | Where the answer lives today | Pain |
|---|---|---|
| Is every container up? | Komodo (cellar) | An admin tool, organised by deployment, not by how the fleet is laid out |
| Does each app answer? | Gatus (sieve) | Up/down only, its own page |
| Are the disks OK? | Scrutiny (cellar) | Its own page; its summary even misreports a disk's hours |
| Did last night's backups run? | `journalctl` on each node, as root | barista can't read it; nobody looks until something breaks |
| What changed on disk? | nowhere | — |
| Did the house do what it should (lights, feeders, doors)? | Home Assistant (mochaPot) | Separate world, separate alerts |
| Is the repo's picture of the fleet still true? | the repo on GitHub | Public, so it can't show live state or anything private |

The cat on the perch sees the whole room at once. That is the product: **one private place
that shows the whole fleet, in the shape of the repo, with its live state and its history.**

## 2. The core idea

> *"Like a copy of the repo, but private — and alive."*

persianPerch is three things at once:

1. **catTree** — a browsable, repo-shaped directory of the fleet: `fleet → node → app`, plus
   the docs. Every folder in `purrbrews-containers` has a living page here.
2. **scentTrail** — one timeline of everything that happened: health changes, backups,
   file drops, house events, web checks. Every event carries a body-language severity.
3. **meow** — one voice for alerts: deduplicated, severity-aware, sent to ntfy, never five
   copies of the same problem.

It **watches, it doesn't drive.** It never restarts a container, runs a backup or changes a
file. (Actions are a later, separate question; see §7.)

## 3. The senses (watcher modules)

The fixed spec, with what each sense means for purrBrews in practice:

| Module | Sense | Watches | First sources |
|---|---|---|---|
| **purr** | contentment, health | containers, node vitals | Komodo API (every node's periphery), node CPU/RAM/disk/temps |
| **pounce** | reacting instantly | filesystem changes | `fsnotify` on chosen paths: `/srv/dumps`, Paperless consume/, the repo checkout, `/etc/purrbrews` |
| **whiskers** | feeling the room | smart-home and physical events | Home Assistant WebSocket API (mochaPot), MQTT if a broker appears |
| **glare** | a hard stare at one thing | endpoint uptime, TLS expiry | Gatus results (sieve) first, own checks later |
| **binocs** | looking far away | external web/APIs | Cloudflare tunnel status, ISP speed (speedtest-tracker), upstream releases of pinned images |

Additions this project proposes, in the same spirit:

| Name | Behavior | What it is |
|---|---|---|
| **groom** | the nightly self-care routine | backup telemetry: every job's start/end, restic summary, log tail, copy ages (roastery, Drive, offline HDD, flask) |
| **perch** | where the cat sits | the core: collectors, rules, the event store, the web UI |
| **catTree** | climbing structure | the repo-shaped directory view |
| **scentTrail** | what the cat leaves and follows | the event store and timeline |
| **meow** | asking for attention | the alert dispatcher (ntfy, email) |
| **kitten** | a small cat on each node | the per-node agent for things only the node can see (pounce, local logs) |
| **nineLives** | never quite dies | the dead-man's switch: perch's own heartbeat, watched from outside (healthchecks.io) |
| **windowsill** | where the cat looks out | the web UI itself |

## 4. Severity, as body language

| Level | Standard | Means | Default meow |
|---|---|---|---|
| **slowBlink** | OK / INFO | nominal; heartbeat confirmed | none (visible on the page) |
| **earTwitch** | NOTICE | expected event: file dropped, state toggled, routine ran | none, or daily digest |
| **tailFlick** | WARN | degraded, high draw, retrying, running late | ntfy, default priority, deduped for 6 h |
| **hiss** | CRITICAL / ERROR | node unreachable, crash, breach, missed backup | ntfy, high priority, immediately, repeats until acknowledged |

A thing's state is the **worst** of its children: an app hissing makes its node hiss, which
makes the fleet hiss. The page always answers "is anything hissing?" in the first glance.

## 5. Who and when

- **barista (the owner)**, mostly on a laptop at home or a phone over Tailscale.
  - Morning glance: *all slowBlink?* → done in 5 seconds.
  - Something hissed: open the thing, read what happened, see the log, fix it elsewhere.
  - Curiosity: browse the catTree, read a README, see a disk's history.
- **Other household members** (optional, later): a read-only "is the house OK" view —
  whiskers only, no fleet internals. A separate Authelia group.
- **Claude / other agents** (later): a read-only JSON API of the same data, so a session can
  ask "what hissed last night?" instead of SSHing into five nodes.

## 6. Principles

1. **Repo-shaped.** The fleet's structure comes from `purrbrews-containers` itself
   (`node.conf`, `backup` files, READMEs). No second inventory to keep in sync.
2. **Private by default, secrets never.** Behind Authelia (admins). Reads only git-tracked
   files; never opens `.env.local`, `secrets.env.local` or anything under `/etc/purrbrews`
   except what it's told is safe.
3. **Silence is a signal.** A job that didn't run is a hiss, not an absence. Every expected
   thing has an expected rhythm.
4. **Read-only.** Watches through existing, read-only doors (Komodo read key, Gatus,
   Scrutiny, HA long-lived token with a read-only user). No docker group, no root, no SSH.
5. **One alert per problem.** meow dedupes, groups and escalates; it never sends five
   pushes for one dead node.
6. **Watch the watcher.** nineLives pings outside the house; if perch goes quiet, you hear
   about it from somewhere perch doesn't run.
7. **Boring to run.** One container (+ a tiny agent), SQLite, no Kafka/Prometheus/Loki
   stack. It must be cheaper to run than the things it watches.

## 7. Parked ideas (not v1)

- **Actions ("paw")**: restart a container, re-run a backup, from the page. Needs a
  write path and its own safety design. Parked deliberately.
- **Grafana-style charts for everything**: only the few trends that matter (repo size, disk
  temp, node load) get sparklines in v1.
- **Log search across the fleet**: kitten could ship logs later; v1 keeps only log tails
  attached to events.
- **VLAN awareness** (espressoLane / catnipCorner / decaf): show which network a device is
  on, flag an IoT device seen on espressoLane. Useful once the VLANs exist.
- **Move-day mode**: when the fleet is moved or re-cabled, a checklist view that walks
  every node back to slowBlink.
- **caliCortado link**: write a daily "fleet diary" into the second brain.
- **tabbyTally link**: electricity cost per node from smart-plug readings (whiskers).

## 8. Names considered

| Thing | Chosen | Also considered | Why the choice |
|---|---|---|---|
| Directory view | catTree | litterMap, scratchPost | A cat tree *is* a tree you climb level by level |
| Event store | scentTrail | hairball, pawprints | Following a trail back = reading history |
| Alerts | meow | yowl, chirp | The one sound a cat makes *at you* |
| Node agent | kitten | whisker (taken), scout | Small, many, one per node |
| Dead-man switch | nineLives | lastLife | Survives the thing it watches |
| Backups | groom | lick, bath | Grooming is the nightly self-maintenance |

## 9. Open questions

1. Does perch live on **cellar** (always on, already the ops hub) or **percolator**
   (more RAM, but it's the identity node and should stay lean)? Leaning cellar.
2. Home Assistant access: a dedicated read-only HA user + long-lived token — acceptable?
3. pounce paths: which directories actually deserve instant reactions? (Proposal in the
   design plan; needs the owner's list.)
4. Should the household "house view" be in v1 or later?
5. Retention: 90 days of events, 1 year of daily rollups — enough?
