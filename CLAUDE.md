# persianPerch — project context

**persianPerch** (Breed + Feline Behavior) is the **unified watcher** of **purrBrews**, the
owner's self-built home tech ecosystem. It's one private web page, shaped like the fleet's
repo, that shows everything the fleet does, live and with history: containers and node
vitals, backups, disks, endpoints, filesystem drops and smart-home events. It only watches;
it never changes anything.

## The owner

- Jyotirmoy, called **barista** in the fleet (also the ops user on every node).
- Comfortable with Docker and configs, learning as he goes on code and hardware.
- Wants detailed answers with reasoning, a dated record of every decision, and to stay
  in control: nothing happens to the fleet without his go-ahead.

## The fleet it watches

| Node | IP | Role |
|---|---|---|
| sieve | 192.168.0.10 | network: Pi-hole, Unbound, cloudflared, ntfy, Gatus, NetAlertX |
| percolator | 192.168.0.11 | ingress + identity (Traefik, Authelia, LLDAP) and daily apps |
| cellar | 192.168.0.12 | ops hub: Komodo Core, Scrutiny hub, restic dump store, backup timers; **persianPerch will run here** |
| mochaPot | 192.168.0.13 | Home Assistant, Music Assistant, second Pi-hole |
| grinder | 192.168.0.14 | automation and AI indexing (n8n, pgvector, Open WebUI, …) |
| roastery | 192.168.0.15 | Windows workstation (Docker Desktop); holds the restic repository; sleeps, woken nightly |

- Defined in **purrbrews-containers** (public: `github.com/purrMonster/purrbrews-containers`):
  `stacks/<node>/node.conf`, each app's `docker-compose.yml`, `backup`, `firewall`,
  `README.md`, and `stacks/fleet.env`. Each node pulls `main` daily. Its dated
  `runbook.md` is the fleet's decision log.
- Every node runs its own Traefik; **Authelia** on percolator is the single login.
- Backups: every node dumps its databases and backs up files nightly into **restic** on
  roastery (via cellar), then cellar copies the repository to **Google Drive**
  (encrypted). Alerts go to **ntfy** on sieve. Remote access is over **Tailscale**.

## Names (purrBrews taxonomy)

- Custom apps: `[Cat Breed/Coat] + [Function or Coffee Drink]`, alliterative camelCase:
  **tabbyTally** (finance), **caliCortado** (second brain), **persianPerch** (watcher).
- persianPerch senses: **purr** (containers, vitals), **pounce** (filesystem), **whiskers**
  (smart-home), **glare** (endpoints), **binocs** (external web/APIs), **groom** (backups).
- Its parts: **perch** (core), **windowsill** (web UI), **catTree** (repo-shaped view),
  **scentTrail** (events + timeline), **kitten** (per-node agent), **meow** (alerts),
  **litter** (one incident's events), **nineLives** (outside heartbeat).
- Severity is body language: **slowBlink** (OK), **earTwitch** (notice), **tailFlick**
  (warn), **hiss** (critical). Worst-of rollup: app → node → fleet.
- Networks (future): **espressoLane** (core), **catnipCorner** (IoT), **decaf** (guest).

## Where things are

- This folder: `C:\Users\jyotirmoyc\Desktop\Projects\persianPerch` on roastery.
- The spec: `docs/01-ideation.md`, `docs/02-design-plan.md`, `docs/03-dev-plan.md`,
  `mockups/` (four HTML views). The build brief: `docs/04-build-prompt.md`.
- Decisions and progress: [`runbook.md`](runbook.md) (dated, newest first) and
  `docs/adr/` for choices between real alternatives.
- **Rules for every agent, including how to update the runbook: [`AGENTS.md`](AGENTS.md).**

## Ground rules (in short; the full set is in AGENTS.md)

1. **Write only inside this folder** unless the owner explicitly says otherwise.
2. **Don't touch the fleet** (no SSH, API calls, deploys) without the owner's go-ahead;
   build against fakes and fixtures. Integration with purrbrews-containers is prepared as
   files in `integration/`, never applied directly.
3. **No secrets and no real domain in any file.** Use `${DOMAIN}`; fixtures use fake values.
   Never read or display `.env.local`, `secrets.env.local`, keys or tokens; never ask the
   owner to paste a secret into a chat.
4. **Read-only product** in v1: no actions on the fleet from the UI.
5. **Keep it boring:** one container, SQLite, server-rendered HTML with htmx; Python.
6. **Record every decision** with its reason, dated, and tick things off only on evidence
   (a test run, a command's output, a screenshot).
7. Git: commits as `jyotirmoyc <jyotirmoy.github@jyotirmoy.cc>`; no history rewrites or
   force-pushes without the owner's go-ahead. PowerShell files stay ASCII-only.

## Status

2026-09-29: planning done (ideation, design plan, dev plan, mockups, build prompt, agent
rules, runbook). No code yet. Next: the build (milestones M0–M5), then M6 prepared for the
owner to deploy. The runbook's Backlog is the live status.
