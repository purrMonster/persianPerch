# persianPerch — Design System (windowsill)

> 2026-10-01 · the single source for how persianPerch looks. The code is
> [`perch/windowsill/static/perch.css`](../perch/windowsill/static/perch.css); the four
> [mockups](../mockups/index.html) link that same file, so the spec and the app can't drift.
> Built from three skills: **design-analysis** (the visual language), **design-taste-frontend**
> (anti-default discipline), **web-design-guidelines** (Vercel's Web Interface Guidelines, the
> review checklist). Where they disagree, §2 says who wins and why.

## 1. Design read

**A private, read-only ops dashboard for one owner, in a calm editorial language, on the
design-analysis tokens.** One person opens it to answer "is purrBrews OK, and if not, what
changed?", mostly at a glance, sometimes on a phone.

| Dial (design-taste-frontend) | Value | Why |
|---|---|---|
| Design variance | 3 | Predictable grid: the eye has to find a hiss fast, every visit, in the same place |
| Motion intensity | 2 | Only state changes move (hover, press, a new event); nothing loops |
| Visual density | 6 | A daily tool: tables and trees, but with room to breathe |

## 2. How the three skills were reconciled

| Tension | Decision |
|---|---|
| design-taste-frontend discourages serif and warm cream as defaults, and serif for dashboards | Its own override applies: the brief names a brand system (design-analysis). The serif stays for **page titles and the wordmark only**. Everything you read or compare is sans. |
| design-analysis puts coral on every primary CTA | persianPerch is read-only: almost nothing to click. Coral also sits between tailFlick amber and hiss red, so a coral button reads as a third alarm. **Coral is limited to** the brand mark, the active-nav bar and the one action perch will have (M3's Ack button, `--accent-fill`). Links are ink, not coral. **On this page, colour means state.** |
| design-analysis' dark product surfaces | Given a real job: **anything quoted from the fleet's repo** (README, compose, `backup` lines; later log tails) sits in a dark code window, in both themes. "The repo says" never looks like "perch says". |
| Serif numerals | Iowan Old Style/Charter draw old-style figures that bob in a column. **Counts are tabular sans**, weight 500. |
| design-taste-frontend is written for landing pages | Its hero, bento, marquee and eyebrow rules don't apply. What does: one accent, one radius scale, full loading/empty/error states, mandatory contrast, the copy audit, no glass on dashboards. Status dots are allowed because each carries real state. |
| design-analysis is Anthropic's own brand | We borrow its logic (tokens, type split, surfaces). We never use the Anthropic spike mark, the Claude wordmark or Anthropic's licensed fonts (Copernicus, StyreneB); system substitutes below. persianPerch's mark is its own cat on a perch. |
| design-analysis is light-only | Both themes, following `prefers-color-scheme`; dark mode uses the system's dark surfaces as the page. |

## 3. Tokens

All colours are CSS variables on `:root`; dark mode redefines them under
`@media (prefers-color-scheme: dark)`. Never write a hex value outside the token block.

| Token | Light | Dark | Use |
|---|---|---|---|
| `--bg` | `#faf9f5` | `#181715` | page canvas |
| `--panel` | `#f5f0e8` | `#1f1e1b` | cards |
| `--panel2` | `#ebe4d8` | `#2a2824` | active/selected states |
| `--line` | `#e0d8cb` | `#37342f` | hairlines that only **group** (cards, table rows) |
| `--control` | `#8a8377` | `#77726a` | the edge of anything you can operate (inputs, filter chips): ≥ 3:1 |
| `--text` | `#141413` | `#faf9f5` | headings, strong text |
| `--body` | `#3d3d3a` | `#e2ded5` | running text |
| `--muted` | `#5f5d57` | `#aeaaa1` | secondary text |
| `--faint` | `#65625a` | `#949087` | tertiary text (still AA) |
| `--accent` | `#cc785c` | `#cc785c` | coral, **never behind or as text** |
| `--accent-fill` / `--on-accent` | `#b05a3e` / white | `#cc785c` / `#181715` | the one action button |
| `--code-bg` / `--code-text` / `--code-muted` | `#181715` / `#faf9f5` / `#b3afa7` | `#1f1e1b` / same / same | code windows |
| `--slowBlink` `--earTwitch` `--unknown` `--tailFlick` `--hiss` | `#256b3c` `#2a5a88` `#625e56` `#7a5000` `#ad1f3a` | `#6cc283` `#7fa9d6` `#9d998f` `#e5ad5f` `#f26b86` | bodyLanguage only |

**Radius (one scale, shape lock):** 6 px small (tree highlight), 8 px controls and buttons,
12 px cards, pill for badges and chips. Nothing else.

**Spacing:** 4 px base; 16 px between cards, 24 px between columns, 20 px card padding.

## 4. Contrast (measured, WCAG 2.2)

Checked with the WCAG relative-luminance formula on 2026-10-01; recheck when a token changes.

| Pair | Light | Dark | Needs |
|---|---|---|---|
| `--body` on `--bg` / `--panel` / `--panel2` | 10.3 / 9.6 / 8.6 | 13.3 / 12.4 / 11.0 | 4.5 |
| `--muted` on the same | 6.3 / 5.8 / 5.2 | 7.7 / 7.2 / 6.4 | 4.5 |
| `--faint` on the same | 5.8 / 5.4 / 4.8 | 5.6 / 5.2 / 4.6 | 4.5 |
| button text on `--accent-fill` | 4.8 | 5.5 | 4.5 |
| `--control` edge on `--bg` / `--panel` | 3.6 / 3.3 | 3.8 / 3.5 | 3 (1.4.11) |
| each bodyLanguage colour on its 10 % badge tint | 5.0–5.9 | 5.0–7.5 | 4.5 |
| `--code-text` / `--code-muted` on `--code-bg` | 17.0 / 8.2 | 15.8 / 7.6 | 4.5 |

Fixed in the 2026-10-01 rework (were failing): white on coral 3.28 → `--accent-fill` 4.8;
control edges on `--line` 1.34 → `--control` 3.6; `--faint` on `--panel2` 4.21 → 4.8.

## 5. Type

| Role | Face | Size / weight | Notes |
|---|---|---|---|
| Page title (`h1`), wordmark | `--font-display`: Iowan Old Style, Charter, Sitka Text, Cambria, Georgia | 30 px / 400, −0.4 px | serif only here; `text-wrap: balance` |
| Section title (`h2`) | `--font-sans`: system-ui stack | 16 px / 500 | |
| Body | sans | 14 px / 400, line-height 1.55 | |
| Small, badges, chips | sans | 12–12.5 px / 500 | |
| Counts (`.strip .n`, `.tile .n`) | sans, tabular | 26–30 px / 500 | never serif (old-style figures) |
| Identifiers, paths, code | `--font-mono`: ui-monospace, JetBrains Mono, Cascadia Code, Consolas | 12.5 px | `translate="no"` |

No web fonts: the page is self-contained, loads fast on the LAN and over Tailscale, and
renders the same with no network.

## 6. Components

- **Header:** solid `--bg` (no glass: no blur on a dashboard, no transparency fallback
  needed), 64 px, wordmark, four nav items, the fleet badge. The active nav item gets the
  coral 2 px bar.
- **Badge (bodyLanguage):** icon + word + colour, always all three; tinted 10 % background,
  30 % border. The fleet badge reads `fleet: hiss`.
- **Dot:** state only, with `role="img"` and an `aria-label`. Never decorative.
- **Card:** `--panel`, `--line` hairline, 12 px radius, 20 px padding. Use cards only when
  they group; otherwise hairlines or space.
- **Strip:** the overview's counts in one band divided by hairlines, not four cards.
- **Code window (`.card.codewin`):** repo content in a dark surface in both themes; its
  `h2` is the file name in mono; focus ring and selection adapt to the dark.
- **Chip:** static labels keep `--line`; anything pressable (`a.chip`, `label.chip`,
  `button.chip`) gets `--control`; checked filters fill with `--panel2` and an ink edge.
- **Tabs:** real links only. A view that doesn't exist yet is a sentence, not a disabled tab.
- **Event row (scentTrail):** time (mono, tabular), a 3 px state stripe, badge, sense chip,
  subject link, title.

## 7. Rules for every change (the checklist)

From web-design-guidelines, applied to this product; a reviewer checks these.

1. Every new colour pair is added to §4 with its measured ratio, both themes.
2. Severity is never colour alone: icon + word + colour.
3. Focus: `:focus-visible` ring, never removed without a replacement; skip link stays.
4. Semantics before ARIA: `<a>` navigates, `<button>` acts, breadcrumbs are
   `<nav aria-label="Breadcrumb">`, headings don't skip levels.
5. Decorative glyphs (`↗`, `▸`) are `aria-hidden="true"`.
6. Transitions list their properties (never `transition: all`); everything stops under
   `prefers-reduced-motion`.
7. Numbers that compare are `tabular-nums`; identifiers are `translate="no"`.
8. Native `<select>` and inputs set `background-color` and `color` explicitly.
9. Filters live in the URL (GET form), so every view of the trail is a link.
10. Buttons say what they do in Title Case (`Apply Filters`, later `Acknowledge`).
11. Copy: active voice, numerals for counts, the middle dot at most once per line, `…` not `...`.
12. Empty states say what will fill them and when; long text wraps (`overflow-wrap: anywhere`),
    flex children get `min-width: 0`.
13. No hex outside the token block; no new radius; no second accent.
14. Before a milestone gate: `scripts\test.ps1` passes, including the Playwright layout check
    at 1400 px dark/light and 390 px (no horizontal scroll, no console errors).
