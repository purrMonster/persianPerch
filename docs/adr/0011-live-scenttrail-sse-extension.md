# ADR 0011 - the live scentTrail: htmx-ext-sse 2.2.4, vendored, over a stream that always carries the whole list

- Status: accepted - 2026-10-03 - M5
- Context: ADR 0003 (htmx vendored; "SSE waits for M5"), 05 plan A12 and M5, design plan 6, docs/06 rule 20.

## Context

The overview, node and app pages refresh by polling (ADR 0003). The scentTrail is different: it is the page a person
opens to watch things happen, and a 30 s poll that replaces a list of 500 rows is the wrong shape for it. M5's gate
asks for an open `/trail` to show a new event within 5 s, without a reload, keeping focus and scroll and respecting
its filters.

Facts verified 2026-10-03: npm `htmx-ext-sse` latest is **2.2.4**, depends on `htmx.org ^2.0.2`, its `LICENSE` is
BSD Zero Clause (the same family as htmx's 0BSD), the tarball's sha512 matched npm's `integrity`, and inside it
`dist/sse.min.js` is 2,853 bytes with **SHA-256 `98a46496de0c3605fbffdce9167ba427bdd9553184f83f149c261891a92c0136`**.
The extension is the browser's own `EventSource` plus a swap; it needs no `eval` and no `hx-on`, so ADR 0003's
htmx configuration (`allowEval: false`, no script tags) holds.

## Options

| Option | For | Against |
|---|---|---|
| **A. `htmx-ext-sse` 2.2.4, vendored** | the plan's own stack; 2.8 KB; same vendoring and hash test as htmx; the browser reconnects by itself | a second third-party file (0BSD family: allowed) |
| B. poll `/live/trail` every few seconds | nothing new | whole-list swaps; latency of the interval; a request per interval per open tab for ever |
| C. our own `EventSource` code | no dependency | the one page with JavaScript of our own, for a thing the extension does in 2.8 KB |
| D. WebSocket | two-way | perch's pages never talk back; a second protocol through Traefik and Authelia |

## Decision

**A.** `perch/windowsill/static/vendor/htmx-ext-sse-2.2.4.min.js` byte for byte from the npm tarball, its licence
beside it as `htmx-ext-sse-2.2.4.LICENSE`, loaded only by `/trail`. `tests/test_trailStream.py` pins its size and
SHA-256 and that it holds no `eval` or `hx-on`; `.gitattributes` keeps `vendor/*` as `-text`.

**The stream (`GET /trail/stream`, a read: S7 is unchanged).**
- It takes the page's own filters (`sense`, `level`) and `after`, the newest event the page was built with. Every
  message (`event: new`) is **the whole list of matching events stored after `after`** (the newest 50, then "and N
  more"), not one row. A reconnect, by the browser's `EventSource` or by the extension making a new one, can therefore
  never list a row twice, and perch keeps no per-client state. [One row per message: needs duplicate handling in the
  browser, which means JavaScript of our own.] The rows carry stable ids on their links, so htmx keeps focus through the
  swap (ADR 0003's rule, docs/06 rule 20).
- The cursor is SQLite's row number, not `seenAt`: a node's pounce event can carry a time in the past.
- A hiss that arrives **while the stream is open** adds one out-of-band sentence for the polite live region
  (`New hiss: ...`); an event that was already there when the stream connected is not announced, and neither is any
  other level. [Announcing every event: noise.]
- A `: keep-alive` comment goes out after 15 s of silence; `retry: 3000`; `Cache-Control: no-cache, no-transform`
  and `X-Accel-Buffering: no`. perch polls its own database once a second per open stream (a single-owner watcher).
- uvicorn waits for open connections at shutdown, so `__main__` sets `timeout_graceful_shutdown=5` and the lifespan
  sets a flag that ends every stream.
- **One small script of our own** (`static/trail-live.js`, 10 lines, no eval, loaded only by `/trail`): leaving the
  page aborts the stream and htmx logs every aborted stream as a console error (`[object Event]`, measured), so on
  `beforeunload` it closes the `EventSource` the extension keeps in the element's `htmx-internal-data`. Measured:
  `htmx.remove()` does not close it; closing it directly leaves the console empty. It depends on two pinned files'
  internals; if they move, the only effect is that the console message comes back, and Playwright's "no console
  errors" check says so. [Accepting the message: noise in every DevTools session; filtering it in the test:
  hides the same noise from the gate.] docs/06 section 2 ("no JavaScript on the page") gains this one exception.
- With JavaScript off, the page is the list as of load; the "Since you opened this page" section is hidden by a
  `<noscript>` rule. Nothing animates.

## Consequences

- **M6 (ROLLOUT.md): the Traefik router for perch must not buffer or compress the `text/event-stream` response**
  (`/trail/stream`), and Authelia's session cookie must reach it (it is a same-origin GET).
- Upgrading the extension is a new ADR or an amendment here, with the new file's hash.
