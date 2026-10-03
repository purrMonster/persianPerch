# ADR 0010 - pounce reports names and change types only, over the kitten report

- Status: accepted - 2026-10-03 - M5
- Context: design plan 4.4, 05 plan A5, C2, C11, ADR 0001; ideation (perch never opens anything under `/etc/purrbrews`).

## Context

pounce is kitten's filesystem sense: a dump arrived, a document dropped, settings changed, the node pulled a new
commit. Four choices were real.

## Decisions

**1. What an event holds: a watched path, a name, a change (created, modified, deleted), a level and a reason. Never contents.**
kitten never opens, reads or hashes a file it watches. Under `/etc/purrbrews` there can be secrets, and the
point of the sense is that something changed, not what is in it.
[Hashing to tell a real change from a touch: needs a read of every watched file, which is the thing the rule forbids.]
A test (`tests/kitten/test_pounce.py`) installs an audit hook that fails on any `open` of a watched path while pounce
sees files change, and scans pounce's syntax tree for `open`, `read*` and hash calls.

**2. The new commit's subject comes from `git`, not from the ref file.** C2 says the pull event carries the subject.
kitten asks `git -c safe.directory=<repo> log -1 --format="%H %s" HEAD` (a subprocess; the kitten user needs read
access to the checkout, which ROLLOUT.md lists) and never opens `refs/heads/main` or `packed-refs` itself. The hash
is remembered so a `git gc` that only rewrites `packed-refs` is not reported as a pull.
[Reading the ref and the object ourselves: a second implementation of git's object format, and a read of a watched file.]

**3. Events travel in the existing report** (`POST /api/kitten`, an `events` list beside `heartbeat` and `records`), sent
as soon as they are debounced, not on the minute. S3 and S7 are untouched: one write endpoint, the same per-node
token, no new route. Each event has a random id so a resend (kitten didn't hear the answer) is stored once; perch
remembers the last 4000 ids in memory (a perch restart in the middle of a resend can store one twice, which is
harmless). [A second endpoint: a new write route for S7 to allow and S3 to cover again.]

**4. An event is an event, not a state.** A file that was dropped has no "now" to keep, so pounce adds no subject to
the rollup and meow, which reads states, does not push it. Level is clamped to tailFlick on perch's side.
**Decided by the owner, 2026-10-03:** a change under `/etc/purrbrews` (design plan 4.4: tailFlick) is a line in the
**07:30 morning digest** and stays on the page and the trail, **never an immediate push**. Only the owner changes those
settings and perch can't tell a deploy from an unexpected change. meow's digest reads the pounce events of
`/etc/purrbrews` since the last digest (one line per node, names only, at most three) beside the litters it already
carries; no state with an expiry was needed. [An immediate tailFlick push: noise on every deploy. A state with an
expiry: more machinery for something the owner has ruled out.]

## Mechanics (from the owner's brief)

- Linux: one `inotifywait -m` per watch, driven by kitten's stdlib code (ADR 0001), restarted with a growing pause
  when it ends, so a directory that appears later, or a package installed after kitten, starts working by itself. A
  path the unprivileged `kitten` user can't list is said once in kitten's log and is **not** worked around (A10);
  ROLLOUT.md lists them. A single file (a ref) is watched through its directory: git replaces a ref by renaming a
  lock file over it, which ends an inotify watch placed on the file itself.
- Windows (roastery): list the folder every 10 s and compare names, sizes and times; the first look is the baseline.
  Default `C:\purrbrews\restic\snapshots` (a new snapshot is an earTwitch), never the whole repository.
- 2 s debounce per path (a file being written is one event; a path that never goes quiet is reported after 10 s);
  at most 60 events a minute per watched path, then one storm tailFlick, ended by a quiet minute.
- Settings: `KITTEN_POUNCE_PATHS` is `path|level|why` entries separated by `;`; unset means the node's defaults
  (design plan 4.4 with C2); `none` switches pounce off.
