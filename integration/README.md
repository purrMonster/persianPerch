# integration/: what the owner applies to the fleet

Everything persianPerch needs from `purrbrews-containers`, the nodes and roastery, **prepared as files and applied by the owner**.
The agent that wrote it never touched the fleet (AGENTS.md section 2.2).

Start with **[ROLLOUT.md](ROLLOUT.md)**: the credentials to create, the order of the deploy, the checks, the drills, the alerts to
retire after the first week, and the last step (roastery's sleep setting).

| | |
|---|---|
| [ROLLOUT.md](ROLLOUT.md) | the owner's deploy guide, step by step |
| [apply.sh](apply.sh) | puts `stacks/`, `groom/groom-record.py` and `patches/` into a clone of `purrbrews-containers` (`--check` first; never commits) |
| [PIN](PIN) | the fleet commit the patches were made against |
| [stacks/cellar/persian-perch/](stacks/cellar/persian-perch/) | the new app folder: compose (with the three Traefik routers), `secrets.conf`, `backup`, `firewall`, `data-dirs`, `README.md`, `config/whiskers.yml` |
| [patches/](patches/) | one patch per existing fleet file: cellar's `node.conf` APPS line, `local.env.example`, README; sieve's `gatus-api` router and Gatus checks; Authelia's rules; Homepage's tile; roastery's `local.env.example` |
| [groom/](groom/README.md) | the backup recorder and the systemd drop-ins (M2) |
| [kitten/](kitten/) | the systemd unit and the installer for the Linux nodes |
| [roastery/](roastery/) | the Scheduled Task installer and launcher (ASCII-only PowerShell) |

[ADR 0012](../docs/adr/0012-m6-how-perch-reaches-the-fleet.md) says why it is shaped this way. The tests:
`tests/test_integrationM6.py` (pytest) and, in `scripts/test.ps1`, the fleet's own test suite on a copy with all of this applied,
`install-kitten.sh` run for real in a Debian container, ROLLOUT.md's ntfy block run from the document, and the roastery scripts' dry run.
