# AGENTS.md — rules for every AI agent on persianPerch

These rules apply to **every** AI agent that works in this repository: Claude (chat,
Cowork, Claude Code), ChatGPT/Codex, a local model, or anything else. Read this file,
[`CLAUDE.md`](CLAUDE.md) (project context) and the top of [`runbook.md`](runbook.md) before
you change anything. If these rules and a request conflict, stop and ask the owner.

The owner is **Jyotirmoy (barista)**. He makes the calls; agents propose, build, verify
and record.

---

## 1. Before you start

1. Read `CLAUDE.md`, this file, and `runbook.md`: the **Backlog** and the **newest three
   entries** at least.
2. Check the **In progress** section of `runbook.md`. If another agent holds the area you
   were asked to work on, don't start: tell the owner who holds it and since when.
3. Run `git status` and `git log --oneline -5`. **Uncommitted changes you didn't make belong
   to someone else**: don't commit, stash, revert or overwrite them. Work around them, or
   ask.
4. Claim your work: add a line under **In progress** in `runbook.md`
   (`- <agent> · <what> · since <YYYY-MM-DD HH:MM>`), and remove it when you're done or stop.

## 2. Hard rules

1. **Stay in this folder.** Write only inside the persianPerch folder unless the owner
   explicitly names another place for a specific task.
2. **Don't touch the fleet** (sieve, percolator, cellar, mochaPot, grinder, roastery's
   services): no SSH, no API calls, no deploys, no changes to `purrbrews-containers`,
   unless the owner says so for that task. Build and test against fakes and fixtures.
   Anything meant for the fleet repo is prepared as files in `integration/` and applied by
   the owner.
3. **No secrets, ever.** No real tokens, passwords, keys, cookies or the owner's real domain
   in any file, commit, log, test fixture, screenshot or chat. Use `${DOMAIN}` and
   obviously fake values. Never open or print `.env.local`, `secrets.env.local`,
   `*.key`, `authorized_keys`. Never ask the owner to paste a secret into a chat; give him
   the command to run in his own terminal instead.
4. **Read-only product.** persianPerch v1 watches; it has no feature that changes the fleet.
   Don't add one without an approved design.
5. **No history rewrites** (`rebase` of pushed commits, `reset --hard` of others' work,
   `push --force`, deleting branches or tags) without the owner's explicit go-ahead for
   that specific operation. Only one agent at a time does history operations.
6. **Don't delete what you didn't create.** Move it to a `_to_delete/` folder and tell the
   owner, if something really has to go.
7. **Ask before anything irreversible or outside the task:** installing system-wide
   software, changing OS settings, creating accounts, spending money, sending messages.

## 3. How to work

- **Small, working steps.** Each commit leaves the project runnable and its tests green.
- **Tests first where cheap;** every bug fix gets a test that fails without the fix.
- **Verify, don't assume.** Run the tests, start the service, load the page. A task is done
  when you've seen it work, not when the code is written.
- **Match the spec.** `docs/01-ideation.md`, `docs/02-design-plan.md`,
  `docs/03-dev-plan.md` and `mockups/` are the spec. If reality disagrees, fix the doc in
  the same commit and record why in the runbook.
- **Keep it boring:** Python, FastAPI, Jinja2 + htmx, SQLite, one container. New
  dependencies need a reason in the runbook (and an ADR if there was a real alternative).
- **Use the purrBrews names** (see `CLAUDE.md`): senses, parts, severity levels, `PERCH_*` /
  `KITTEN_*` settings. Plain meanings go in docs and UI tooltips, not instead of the names.
- **PowerShell files are ASCII-only** (PowerShell 5 misreads BOM-less UTF-8). Shell and
  data files use LF line endings.

### 3.1 UI work: three design skills, every time

Any change to `perch/windowsill/` (templates, CSS, static files) or `mockups/` must follow
three skills. They are installed as Claude Code project skills in `.claude/skills/` on
roastery (gitignored: third-party texts, public repo); other agents read the same files.

| Skill | Use it for | Limits in this project |
|---|---|---|
| `design-analysis` | the visual language: tokens, the serif/sans split, surfaces, radius | Tokens live only in `perch.css`. Never the Anthropic spike mark, the Claude wordmark or Anthropic's licensed fonts. |
| `design-taste-frontend` | anti-default discipline: one accent, one radius scale, full loading/empty/error states, contrast, the copy audit | It is written for landing pages. **Never** take its stack defaults (React, Next.js, Tailwind, Motion, icon libraries, web fonts): this stays Jinja2 + htmx + one CSS file. Its hero, bento, marquee and eyebrow rules don't apply. |
| `web-design-guidelines` | the review: fetch the guidelines fresh from its source URL and check every changed file | Run it before every milestone gate that touched the UI. Fix each finding, or record in the runbook why it doesn't apply. |

**Order of authority:** `docs/06-design-system.md` (the project's decisions, including
where the skills were overruled and why) → the skills → the agent's own taste. If a skill
and docs/06 disagree, docs/06 wins; if you think docs/06 is wrong, say so in the runbook and
ask the owner, don't silently diverge. Every UI change also follows docs/06 §7's checklist.

If `.claude/skills/` is missing or a skill won't load, stop and tell the owner: don't build
UI from memory of what the skills say.

## 4. The runbook (`runbook.md`)

`runbook.md` is the project's memory: **every decision and every change of state goes in
it, dated, with the reason.** A future agent (or the owner in a year) must be able to
understand *why* things are the way they are without re-deriving it.

### 4.1 When to update it

- Before you start: claim the work (**In progress**).
- **At every step that changes something:** a decision, a milestone started or finished,
  a design doc changed, a dependency added, a bug found and fixed, a test that proved
  something, a problem you couldn't solve.
- When you stop, even unfinished: what's done, what's not, what the next agent needs to
  know. Remove your **In progress** line.
- In the same commit as the change it describes, never "later".

### 4.2 Shape

```markdown
# persianPerch Runbook

## In progress
- <agent> · <what> · since <YYYY-MM-DD HH:MM>

## Backlog / open items
- [ ] open item (owner / agent), with a pointer to the entry that explains it
- [x] done item (YYYY-MM-DD), with the evidence in its entry

---

## YYYY-MM-DD — Short title, newest first

**Context.** What was asked, by whom, and why.

**Decided.** What, and **why**; the alternatives and why they lost.

**Done.** What changed (files, behaviour).

**Verified.** The commands run and their real results (paste the relevant lines).

**Not done / next.**
- [ ] next step (who)

— <agent name, model if known>
```

### 4.3 Rules for entries

- **Newest first.** New dated entries go directly under the `---` after the Backlog.
- **Tick only on evidence.** `[x]` means you saw it work: a test run, a command's output,
  a screenshot. Otherwise it stays `[ ]`, with a note of what's missing.
- **Never rewrite history.** If an earlier entry was wrong, add a dated correction (to that
  entry as an indented bullet, or in a new entry) that says what was wrong and what's true.
  Don't silently edit the old text.
- **Who.** Sign every entry with the agent that wrote it. Say which steps were the owner's
  (`(owner)`) and which were yours.
- **Plain language.** Short sentences. Explain the purrBrews names on first use in an entry
  if the meaning matters.
- **No secrets** in the runbook either: names of keys yes, values never.

## 5. Git

- **Identity:** `jyotirmoyc <jyotirmoy.github@jyotirmoy.cc>` as author and committer.
- **Messages:** first line `<area>: <what changed>` (areas: `perch`, `kitten`, `catTree`,
  `scentTrail`, `purr`, `pounce`, `whiskers`, `glare`, `binocs`, `groom`, `meow`,
  `windowsill`, `docs`, `runbook`, `integration`, `ci`), then a short body saying why.
  End with an attribution trailer naming the agent, e.g.
  `Co-Authored-By: Claude <noreply@anthropic.com>`.
- **Branches and pull requests (owner's rule, 2026-10-02):** never commit or push to `main`.
  Work on a branch (`<agent>/<milestone-or-topic>`). At a green gate: run the pre-push
  checks below, push **the branch**, open a pull request into `main` (without the `gh` CLI,
  give the owner the `github.com/purrMonster/persianPerch/compare/main...<branch>` link),
  report, and stop. **Only the owner merges**, with a **merge commit**, never squash or
  rebase: runbook entries cite commit hashes as evidence, and both would rewrite them.
- **Before every push:**
  - `git log origin/main..HEAD --format='%ae %ce'` shows only
    `jyotirmoy.github@jyotirmoy.cc`;
  - no real domain, secret or private hostname in the diff
    (`git diff origin/main..HEAD` read through, not just grepped);
  - the tests pass.

## 6. Handing off

When you finish or stop, your last runbook entry must let the next agent continue
without asking you anything:

- what state things are in (what runs, what's tested, what's stubbed);
- the exact next step, and who owns it (owner or an agent);
- anything surprising you found (a wrong assumption in the docs, a flaky test, an API
  that behaves differently from its docs).

Then remove your **In progress** line and commit.

## 7. When to stop and ask the owner

- Anything under §2 that needs an exception.
- A contradiction in the spec that changes the architecture.
- Another agent's uncommitted work in the way.
- A test you can't make pass after an honest attempt: record what you tried in the
  runbook, then ask.
