# ADR 0004 - Litters: one push per problem, and a node that is down absorbs its apps

- Status: accepted - 2026-10-02 - M3 (meow); the owner asked for the choice to be recorded
- Context: design plan 5 ("dedupe by litter"), 05 plan M3 gate ("fake grinder down: exactly one push,
  then one recovery push"), scentTrail's `litterId`.

## Context

A node that dies makes every one of its apps unreadable. Paging once per app would be a storm of 12
messages about one cause. scentTrail already has a `litterId` on events, and groom sets it
(`subject@slot`), but events are history, not "what is wrong now": a litter needs a start, an end,
an acknowledgement and a record of what was pushed, and it has to survive a restart.

What purr writes when a node doesn't answer: the node's state is `hiss` (`detail.mode =
"unreachable"`), its apps and containers turn `unknown` ("perch can't see them"), not `hiss`. That is
deliberate (M1: perch not seeing is not the same as the thing being down). Backups of that node and its
kitten then go late and hiss on their own timers.

## Options

| Option | For | Against |
|---|---|---|
| A. Group events by `litterId` as written | no new storage | events are written once, by many senses, with no common cause; nothing says when a litter ends |
| B. meow keeps litters in memory, keyed by subject | simple | a restart forgets what was pushed, acknowledged or held, so every hiss re-pushes |
| C. **meow reads the current states into litters stored in scentTrail's database; a node that purr marks unreachable is one litter that absorbs every subject of that node** | one cause, one push; survives restarts; acknowledgement, held and recovery are rows, so the page shows them | a table and a migration (4) |
| D. Absorb by time window ("all hisses within 60 s of a node hiss") | no cause needed | guesses; hides a real app problem that happens to coincide |

## Decision

**C.**
- A **litter** is one problem: a key (`app:grinder/n8n`, `node:cellar`, `groom:sieve/nightly`,
  `kitten:grinder`, `collector:purr`, or `down:grinder`), a level, an id of the form
  `<key with / and : as dots>@<UTC start>`, and what meow did about it. It opens when the state reaches
  earTwitch or worse, closes when it is slowBlink again.
- **Absorption:** when `node:X` is hiss with mode `unreachable`, one litter `down:X` ("grinder
  unreachable: 12 apps affected", the count of watched apps) replaces every litter of that node's `app:`,
  `groom:`, `kitten:` and own `node:` subjects. A litter that already existed for one of those closes
  quietly (`folded into its node's litter`) and gets no recovery of its own; the node's recovery is the one
  message.
- **Unknown is not recovery:** a subject whose state is `unknown` keeps its litter as it is. When purr goes
  blind (Komodo down) nothing is "back".
- A worse level on an open litter is news again: a hiss clears the acknowledgement and is pushed at once.
  A new litter for the same key later gets a new id, so an old push's button can't acknowledge it.
- **Recovery** is announced once per litter that was pushed, to the channels it was pushed to; several
  recoveries at once are one message. A tailFlick's recovery waits out quiet hours; a hiss's does not.
- **Held and digest are columns, not a queue:** `heldAt` (the rate limit kept it back), `digest` /
  `digestedAt` (it waits for, or went out in, the 07:30 digest). Everything due is derived from the rows on
  every cycle, so nothing can be lost between cycles or by a restart.
- tailFlicks that fall due together are one push (no acknowledge button: it would name several litters).
  "Once per litter per 6 h" is read as: pushed once, reminded at most every 6 h while it stays open.
- Both hiss channels get priority 4 (high); the design says "high" and leaves the critical topic's
  priority open, so it is not raised.

## Consequences

- The Alerts card on the overview is a view of the `litters` table.
- If purr never marks a node `unreachable` (Komodo cannot tell), the apps' own litters stand as they are.
- `retention` deletes closed litters, pushes and spent tokens at the events' age (90 days).
