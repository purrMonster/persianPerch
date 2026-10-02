# ADR 0003 - htmx 2.0.11, vendored and served by perch

- Status: accepted - 2026-10-02 - owner's decision; built as M2's first task
- Context: dev plan 1 and AGENTS.md 3 ("Jinja2 + htmx"); M1 runbook entry (2026-10-02), which
  shipped pages without htmx because vendoring a third-party file needed the owner's yes.

## Context

M1's pages show state as it was when the page loaded, with the age of purr's last look in the
header. A watcher that only updates on reload is half a watcher, and two later milestones need
htmx anyway: M3's Ack button (a POST that swaps a fragment) and M5's live scentTrail (SSE).

Facts checked 2026-10-02 against the npm registry:

- `htmx.org` dist-tags: `latest` = **2.0.11** (published 2026-09-22), `next` = 4.0.0 (2026-08-28).
- Licence: **0BSD** (Zero-Clause BSD, in the package's `LICENSE`): use, copy and redistribute
  with no conditions, so unlike the design skills (gitignored) it can be committed to this
  public repo.
- The package tarball matched npm's published `integrity` (sha512); inside it,
  `dist/htmx.min.js` is 52,182 bytes with
  **SHA-256 `d6fdc75f204e6bdefa99b69bf1e6d4ac69b8a364f77929f45c13476b4000f717`**.

## Options

| Option | For | Against |
|---|---|---|
| **A. htmx 2.0.11, vendored** | the plan's own stack; one 52 KB file perch serves itself; works on the LAN and over Tailscale with no internet; pinned by hash | a third-party file in the repo (0BSD: allowed) |
| B. htmx from a CDN | nothing to commit | perch would depend on the internet and a third party for its own pages; a CDN can change what it serves |
| C. htmx 4.0 | the future line | npm still tags it `next`; htmx plans to make it `latest` around early 2027. A watcher shouldn't ride a month-old major |
| D. `<meta http-equiv="refresh">` | no JavaScript at all | reloads the whole page: loses scroll and focus, re-announces the page to screen readers, flashes |
| E. ~20 lines of own `fetch()` code | no dependency | re-implements htmx badly by M3 (Ack) and M5 (SSE) |

## Decision

**A.** `perch/windowsill/static/vendor/htmx-2.0.11.min.js`, copied byte-for-byte from the npm
tarball `htmx.org-2.0.11.tgz` (`dist/htmx.min.js`), with its `LICENSE` beside it as
`htmx-2.0.11.LICENSE`. Loaded with `<script src="/static/vendor/htmx-2.0.11.min.js" defer>`.

- **Polling, not SSE, for now:** the overview, node and app pages refresh their state regions
  with `hx-get` + `hx-trigger="every 30s"` (purr's rhythm) and `hx-swap` of that region only.
  The page itself never reloads. SSE (`htmx-ext-sse`, vendored the same way) waits for M5.
- **Accessibility:** the swapped region keeps focus and scroll; a changed state is announced
  once through a polite live region, never every 30 s; nothing animates under
  `prefers-reduced-motion`.
- **Pages still work without JavaScript** (state as of load), as in M1.

## Consequences

- A test hashes the vendored file and fails unless it is exactly the SHA-256 above. Upgrading
  htmx is a new ADR (or an amendment here) with the new version's hash, never a silent swap.
- `docs/05-autonomous-build-plan.md` A12 and the M2 gate (Playwright: a state change shows on
  an open overview within 35 s without a full reload) hold the build to this.
- The M2 web-design-guidelines review covers the new behaviour (live regions, focus, motion).
