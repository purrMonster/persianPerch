# Changelog

Releases of persianPerch. Each one is an image, `ghcr.io/purrmonster/persian-perch:<version>`, published by
`.github/workflows/release.yml` from a `v<version>` tag; the fleet pins it by tag and digest. The reasons behind
every change are in [runbook.md](runbook.md), by date.

## [0.1.0] - 2026-10-14

The first release: everything built in M0–M6, ready for its first deployment on cellar. It has not met the live
fleet yet. 0.x until `integration/ROLLOUT.md`'s drills pass; 1.0.0 after a week with no false hiss.

### What it does

- **perch** watches the purrBrews fleet and never changes it: one page shaped like the fleet repo (catTree), live
  state and history (scentTrail), body-language severity rolled up app → node → fleet.
- **Senses:** purr (Komodo: containers, node vitals, vitals history), groom (backups, from the recorder's records),
  glare (Gatus), disks (Scrutiny), binocs (the tunnel, speedtest-tracker, newer releases of pinned images), pounce
  (file names on the nodes, from kitten), whiskers (Home Assistant over a WebSocket, read only).
- **meow** pushes to ntfy (a hiss also to ntfy.sh), one push per incident (litter), quiet hours and a morning
  digest; Acknowledge from the page or from a push's signed, single-use link. **nineLives** pings healthchecks.io.
- **kitten**, the per-node agent (Linux systemd unit, roastery Scheduled Task): heartbeat, backup records, pounce.

### Changed since the last commit before the release (2026-10-14 repass)

- Follows the rebuilt fleet (`72e3f7b`): binocs compares `tag@digest` pins, pounce sees reviewed deploys
  (`.git/HEAD`), the Gatus account is `sphynx`, `integration/` keeps only what goes on the nodes.
- A Scrutiny threshold failure with SMART passing is a tailFlick, not a hiss.
- scrub masks quoted values whole, JSON-style keys and Google OAuth tokens in log tails.
- windowsill's app is split into modules; no route or page changed.
- `/healthz` reports the release (`version`).
- CI on every push and pull request: ruff, pytest, kitten on 3.13 and 3.14, gitleaks over every commit, the image
  built and started.
