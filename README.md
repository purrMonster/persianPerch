# persianPerch

> **Breed + Feline Behavior** · *Unified Watcher* · a purrBrews custom application

One private place that shows the whole purrBrews fleet in the shape of its repo, with live
state and history: containers and node vitals (**purr**), filesystem drops (**pounce**),
smart-home events (**whiskers**), endpoints and the outside web (**glare** / **binocs**),
and every backup (**groom**). Severity speaks body language: **slowBlink**, **earTwitch**,
**tailFlick**, **hiss**.

Status: **planning** (2026-09-29). Nothing here runs yet.

| Doc | What it's for |
|---|---|
| [docs/01-ideation.md](docs/01-ideation.md) | Why it exists, the senses, the names, principles, parked ideas, open questions |
| [docs/02-design-plan.md](docs/02-design-plan.md) | Architecture, data model, each sense in detail, alerts, UI, security, failure modes |
| [docs/03-dev-plan.md](docs/03-dev-plan.md) | Stack, layout, `PERCH_*` settings, milestones M0–M6, tests, risks, decisions needed |
| [docs/04-build-prompt.md](docs/04-build-prompt.md) | The prompt for a separate session to build v1 autonomously |
| [mockups/index.html](mockups/index.html) | Four UI mockups: perch overview, catTree, groom, scentTrail |

## Names at a glance

| Name | What |
|---|---|
| **perch** | the core service (on cellar) |
| **windowsill** | its web UI |
| **catTree** | the repo-shaped directory view: fleet → node → app |
| **scentTrail** | the event store and timeline |
| **purr · pounce · whiskers · glare · binocs · groom** | the senses (watcher modules) |
| **kitten** | the small agent on each node |
| **meow** | alerts (ntfy, email) |
| **litter** | the events of one incident, alerted once |
| **nineLives** | the outside heartbeat that watches the watcher |
