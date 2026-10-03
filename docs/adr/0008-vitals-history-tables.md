# ADR 0008 - vitals history: two small tables, averaged in memory, rolled up by the hour

- Status: accepted - 2026-10-03 - M4 (the owner decided on history and sparklines in A13; the shape is the agent's)
- Context: design plan 3.5, 05 plan A13.

## Decision

scentTrail migration 5 adds `vitals5m` (kept 7 days) and `vitalsHour` (kept 400 days), both `WITHOUT ROWID` with the
key `(node, at)`; each row holds the average CPU, RAM and root-disk percentages, the highest reading of each, and how
many samples made it (`n`). purr's 30-second samples are **averaged in memory** and one row per node is written when
the next 5-minute bucket starts; nothing raw is ever stored. `maintain` runs on the first sample of each hour: it
rolls the completed hours up (a mean weighted by `n`, the highest of the highs) and only then deletes 5-minute rows
older than 7 days and hourly rows older than 400 days, so an hour is never deleted before it was summed. Rolling up is
idempotent (`INSERT OR IGNORE`). The retention windows are "bucket start at or after now minus 7 days (400 days)".

## Alternatives

- **One `vitals` table with a `resolution` column** (the 05 plan A13 wording): one scan for both, but the 5-minute rows
  and the hourly rows have different keys and lifetimes, so every delete and every read needs the column. Two tables are
  simpler to age out and to size.
- **Keep the raw 30-second rows for a day**: 2,880 rows a node a day for no view that uses them.
- **A time-series database**: design plan 2.3 already said no.

## Deviation from design plan 3.5

The plan kept the highest reading only for the disk in `vitals5m`. Both tables keep it for CPU, RAM and disk: it costs
three REAL columns, and the hour's true peak (not the peak of 5-minute averages) is what a later "sustained" rule needs.

## Consequences

Measured (tests): 8 days of 30-second samples leave exactly 2,016 five-minute rows and 192 hourly rows for a node;
at 400 days of 6 nodes the database is 7.4 MB. A gap (Komodo unreachable, perch stopped) is a missing row, and the
sparkline breaks its line there.
