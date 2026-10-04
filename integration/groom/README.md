# integration/groom: the backup recorder (prepared, not applied)

> Status: **prepared in M2, applied by the owner** (05 plan A8, Q13 = A, A10). Nothing here has
> touched a node. persianPerch's tests check these files against the pinned fleet repo
> (`tests/test_integrationGroom.py`), including the whole chain recorder → kitten → perch.

groom needs to know when each backup job ran and how it ended. The fleet's scripts don't say, and
`backup.sh` stays untouched: instead, systemd runs a small recorder when a backup unit stops, with
`ExecStopPost=`. It gets the unit's result from systemd itself (`$SERVICE_RESULT`, `$EXIT_STATUS`)
and the last 40 log lines from the journal, and writes one file per run.

## What lands where

| Here | Lands in `purrbrews-containers` as | Then |
|---|---|---|
| `groom-record.py` | `stacks/_lib/groom-record.py` (executable) | every node pulls `main` daily, so it arrives everywhere |
| `units/purrbrews-backup@.service.d/groom.conf` | installed beside the template unit: `/etc/systemd/system/purrbrews-backup@.service.d/groom.conf` on **every backup node** (sieve, percolator, cellar, mochaPot, grinder) | `sudo systemctl daemon-reload` |
| `units/<service>.d/groom.conf` for `purrbrews-wake-roastery`, `purrbrews-backup-store`, `drive-sync`, `purrbrews-backup-check`, `restic-prune`, `purrbrews-backup-verify` | `/etc/systemd/system/<service>.d/groom.conf` on **cellar only** | `sudo systemctl daemon-reload` |

The fleet installs its units by hand, as the header of `purrbrews-backup@.service` says
(`sudo cp ... /etc/systemd/system/`, then `daemon-reload`); the drop-ins are installed the same
way. M6's `ROLLOUT.md` will carry the exact commands per node.

## The record

`/var/lib/purrbrews/groom/<job>/<start>.json`, mode `0644` in `0755` directories (A10: `kitten`
is an unprivileged user that only reads). Schema 1, defined by `parseRecord` in
`perch/senses/groom.py`:

```json
{
  "schema": 1,
  "job": "nightly",
  "node": "grinder",
  "unit": "purrbrews-backup@grinder.service",
  "start": "2026-09-29T01:30:12Z",
  "end": "2026-09-29T01:52:36Z",
  "result": "success",
  "exitStatus": "0",
  "logTail": "last 40 lines, at most 16 KB"
}
```

`job` is one of `nightly`, `wake`, `store`, `drive`, `check`, `prune`, `verify`. `result` is
systemd's `$SERVICE_RESULT` (`success`, `exit-code`, `signal`, `timeout`, ...). The log tail may
hold anything the job printed: perch scrubs the secrets it knows before storing it.

## Safety

- `ExecStopPost=-...`: the leading `-` means a recorder problem can never fail a backup. The
  recorder also exits 0 on every error and prints what went wrong to the journal.
- It writes only under `/var/lib/purrbrews/groom/` and reads only the journal. No network.
- It runs as root (the unit does), so the files are root-owned; `kitten` reads them through the
  modes above.

## What the owner still decides

- When to apply it (it changes nothing about the jobs, but it is a change to every backup node).
- Kitten itself (zipapp, unit, user) is `integration/kitten/` (M6, [ADR 0012](../../docs/adr/0012-m6-how-perch-reaches-the-fleet.md));
  until it runs on a node, nothing ships that node's records, and perch shows it as "not watched yet".
- The exact commands, per node, are in [ROLLOUT.md](../ROLLOUT.md) step E. `apply.sh` copies `groom-record.py` into the fleet repo
  with everything else, so the recorder is not prepared twice.
