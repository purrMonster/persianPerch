# ADR 0012 - M6: how perch and kitten reach the fleet (labels, a pinned git build, kitten by pull)

- Status: accepted - 2026-10-03 - M6 (prepare only)
- Context: 05 plan C1, C6, C9, C13, A5, A8, A10, A11 and the M6 section; the fleet's `stacks/README.md` ("Adding an app",
  "Ingress") and its delivery rule ("commit and push changes to Git, then pull them on the nodes; do not copy configuration or
  code directly to servers"). Nothing is applied by the agent: everything is a file in `integration/` for the owner.

## Decisions

**1. The three Traefik routers are compose labels, not cellar's `dynamic.yml.template`.** Every cellar app routes by labels, the
node IP list for the kitten router is `fleet.env` variables (compose interpolates them; a rendered template would need them in
`.env.local`), and it keeps the whole change inside one new folder instead of editing a file every cellar route depends on. The
fleet's `dns-records.py` reads Host rules from compose labels, which its tests exercise; ours is checked against that same
generator. [Editing `dynamic.yml.template`: the plan's first wording (05 plan M6); one more fleet file to patch and re-render.]
The kitten router also admits `/healthz`, so Gatus on sieve (one of the six addresses) can read perch's health without Authelia;
the page itself stays behind it, and Gatus checks that too (a `302`/`401`, never a `200`).

**2. The image is built on cellar from the public persianPerch repo at a pinned ref** (`build.context` is a git URL with
`#${PERSIAN_PERCH_REF}`, asked for in `.env.local`, refused when unset). No registry to publish to, no image to trust that is not
built from a commit the owner chose, and the fleet's rule "pin your images" holds as a tag or full commit.
[A published image on ghcr.io: a second thing to publish, sign and keep in step. `:main`: a floating tag, which the fleet forbids
without a written reason.]

**3. kitten is delivered by pull, not copy.** The fleet's delivery rule forbids copying code to servers, and the dev plan's M6
line ("rolled out by `_lib`/`init`") would put a second copy of kitten's source in the fleet repo. Instead each node clones the
public persianPerch repo at the same pinned ref, builds the zipapp itself as the ops user (standard library only: `python3 -m
kitten.build`), and runs `install-kitten.sh` as root, which installs it root-owned in `/opt/kitten`, creates the `kitten` user,
writes `/etc/purrbrews/kitten.env` (root, 0600; the token is typed at a hidden prompt, never an argument) and starts the unit.
roastery does the same with `scripts\buildKitten.ps1` and a Scheduled Task. The installer reports, never fixes, a folder the
`kitten` user cannot list (A10). [Committing `kitten.pyz` into the fleet repo: a binary in a text repo, no review possible.
Copying the file with `scp`: against the delivery rule and unauditable. Source in the fleet's `_lib/`: two copies that drift.]

**4. The ntfy user is not a fleet file change** (C14). It goes in the node-local `secrets.env.local` lists the fleet's own
`secrets.hook` already builds the users from; ROLLOUT.md gives the exact block, and a test runs that block, from the document
itself, against the pinned fleet's helpers.

**5. What the fleet's own tests prove.** `integration/apply.sh` applies everything to a fresh clone (it refuses a dirty clone, an
old pin that no longer fits, and applying twice) and the fleet's `python3 -m unittest discover -s tests` runs on the result, once
unprivileged (their Secrets, Render and Firewall classes skip themselves as root) and once as root (their real-backup test).
`scripts/test.ps1` does this on every run.

## Consequences

- The owner reviews one new folder, eight small patches and a copy of `groom-record.py` in a pull request; nothing on a node
  changes until he runs the steps in `integration/ROLLOUT.md`.
- Updating perch or kitten is changing one ref and running the same commands again.
- The traffic from cellar's own kitten to `perch.${DOMAIN}` must arrive at Traefik with cellar's LAN address as its source; if
  Docker presents the bridge gateway instead, the nodes router answers 403 and ROLLOUT.md says what to do.
