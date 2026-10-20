# integration/: what the owner applies to the fleet

What persianPerch puts on the nodes and roastery, **prepared as files and applied by the owner**. The agent that wrote
it never touched the fleet (AGENTS.md section 2.2). Its part of `purrbrews-containers` (perch's app folder, the routers,
Gatus checks, Authelia rules, the backup recorder) was merged there in October 2026; the copies and patches that used to
live here were removed on 2026-10-14 (runbook), so there is one copy of each file.

Start with **[ROLLOUT.md](ROLLOUT.md)**: the credentials to create, the order of the deploy, the checks, the drills, the alerts to
retire after the first week, and the last step (roastery's sleep setting).

| | |
|---|---|
| [ROLLOUT.md](ROLLOUT.md) | the owner's deploy guide, step by step |
| [groom/](groom/README.md) | the systemd drop-ins that run the fleet's backup recorder (M2) |
| [kitten/](kitten/) | the systemd unit and the installer for the Linux nodes |
| [roastery/](roastery/) | the Scheduled Task installer and launcher (ASCII-only PowerShell) |

[ADR 0012](../docs/adr/0012-m6-how-perch-reaches-the-fleet.md) says why it is shaped this way. The tests:
`tests/test_fleetStack.py` (perch's app folder in the pinned fleet repo against perch's own settings, and ROLLOUT.md against
both), `tests/test_integrationGroom.py` and, in `scripts/test.ps1`, `install-kitten.sh` run for real in a Debian container,
ROLLOUT.md's ntfy block run from the document, and the roastery scripts' dry run.
