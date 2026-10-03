# ROLLOUT: putting persianPerch on the fleet

> For the owner (barista). **Nothing in this folder has been applied to anything.** Every step here is
> yours, in your terminal, on the node named in the step, in this order. The agent that wrote it never
> touched a node, never saw a credential and never made a change in `purrbrews-containers`.
> Written 2026-10-03 against the fleet repo at commit `922164af2449ee9c8899b9466d721ffc5a2ac4e6`
> (`integration/PIN`). If the fleet's `main` has moved since, `apply.sh --check` (step B2) tells you
> whether the patches still fit.

`${DOMAIN}` below is your real domain; it is never written in this repo. `<fleet>` is a clone of
`purrbrews-containers` on the machine you work from. `<node>` is a node's folder name in `stacks/`,
spelled exactly like it (`mochaPot`, not `mochapot`).

**Shell note.** Commands below use `${DOMAIN}` and the node addresses (`${SIEVE_LAN_IP}`, ...). On a node, load them first so the commands run as written (this only sets variables in your shell):

```bash
cd /opt/purrbrews/stacks/<node> && set -a && . ../fleet.env && . ./.env.local && set +a
```

## What goes where

| Here (`integration/`) | Lands in | Step |
|---|---|---|
| `stacks/cellar/persian-perch/` (compose, `secrets.conf`, `backup`, `firewall`, `data-dirs`, `README.md`, `config/whiskers.yml`) | `purrbrews-containers` `stacks/cellar/persian-perch/` | B |
| `patches/cellar-node-conf.patch`, `cellar-local-env.patch`, `cellar-readme.patch` | cellar's `node.conf` (the `APPS` line), `local.env.example`, `README.md` | B |
| `patches/sieve-gatus-api-router.patch` | `stacks/sieve/traefik/dynamic/sieve.yml` (the `gatus-api` router, the `authelia-basic` middleware) | B, D |
| `patches/sieve-gatus-checks.patch` | `stacks/sieve/gatus/config/config.yaml` (two checks on perch) | B, H |
| `patches/percolator-authelia-rules.patch` | Authelia's template: `perch.${DOMAIN}` and `gatus-api.${DOMAIN}` among the admin hosts, the `perch_api_group` rule | B, D |
| `patches/percolator-homepage-tile.patch` | Homepage's `services.yaml` | B, D |
| `patches/roastery-local-env.patch` | `stacks/roastery/local.env.example` (the kitten token, asked by `setup-secrets.ps1`) | B, G |
| `groom/groom-record.py` | `stacks/_lib/groom-record.py` (copied by `apply.sh`) | B |
| `groom/units/*.d/groom.conf` | `/etc/systemd/system/<unit>.d/groom.conf` on the nodes (not in the fleet repo: node-local, like the fleet's own units) | E |
| `kitten/` (`install-kitten.sh`, `kitten.service`) | each Linux node, run from a persianPerch checkout | F |
| `roastery/` (`install-kitten.ps1`, `run-kitten.ps1`) | roastery's Scheduled Task | G |

Ntfy needs **no file change** (plan C14): perch's user goes into the node-local `secrets.env.local` (step A3).

## The decisions this rollout rests on

- **perch runs on cellar**, no published port; three Traefik routers on `perch.${DOMAIN}`: the page (Authelia),
  the nodes' reports and `/healthz` (the six fleet addresses only), and the acknowledge links `/ack/t/` (10 a minute).
  They are compose labels, because every cellar app routes that way and the address list comes straight from `fleet.env`.
- **kitten is delivered by pull, not copy** (the fleet's delivery rule): each node clones the public persianPerch repo
  at a pinned ref, builds the zipapp itself as you, and installs it. Nothing is `scp`'d. Updating is the same four lines.
- **Morning digest only** for a change under `/etc/purrbrews` (you decided 2026-10-03): it is a trail row and a
  line in the 07:30 digest, never an immediate push. Only you change those files and perch can't tell a deploy
  from a surprise.
- **whiskers never hisses about itself** (you decided 2026-10-03): if Home Assistant is down, purr (its container)
  and glare (its endpoint) already hiss, so a third hiss would double-alert one outage.
  **The cost:** while whiskers is down, perch cannot see leak or smoke sensors, so
  **Home Assistant's own alerts (its notifications to your phone) must cover leak and smoke.** Check that they do
  (step J, "Home Assistant's own leak alert") before you rely on perch for them.
- **roastery's sleep:** it stays awake for the whole rollout; the last step (K) puts its sleep setting back.

---

## A. Create the credentials (before cellar's `setup-secrets.sh`)

Every value is entered **only** at a prompt of the fleet's own `./setup-secrets.sh` (or `.\setup-secrets.ps1` on
roastery) on the node that needs it, hidden. Never in a file in a repo, a chat, a commit or a command line. When a step says
"read it", that means print it in your own terminal and type it into the next prompt.

The list of every setting, in `secrets.env`, and where each ends up:

| Key (`secrets.env`) | Kind | Made or found | Entered at |
|---|---|---|---|
| `PERCH_REPO_DIR`, `PERCH_TRAIL_DB`, `PERCH_TRAIL_DAYS`, `PERCH_ROLLUP_DAYS`, `PERCH_TZ` | not secret | defaults in `secrets.conf` / compose (`TZ` comes from `fleet.env`) | nothing to type |
| `PERCH_PURR_URL`, `PERCH_PURR_EVERY` | not secret | defaults | nothing to type |
| `PERCH_PURR_KEY`, `PERCH_PURR_SECRET` | **secret** | A1: Komodo, on cellar | cellar's prompt |
| `PERCH_GLARE_URL` | not secret | `https://gatus-api.${DOMAIN}`, built in compose | nothing to type |
| `PERCH_GLARE_USER` | not secret | `perch-svc` (the LLDAP account of A2) | nothing to type |
| `PERCH_GLARE_PASSWORD` | **secret** | A2: LLDAP, on percolator | cellar's prompt |
| `PERCH_GLARE_EVERY`, `PERCH_DISKS_URL`, `PERCH_DISKS_EVERY` | not secret | defaults (`http://scrutiny:8080`) | nothing to type |
| `PERCH_WHISKERS_URL` | not secret | `ws://${MOCHAPOT_LAN_IP}:8123/api/websocket`, built in compose | nothing to type |
| `PERCH_WHISKERS_TOKEN` | **secret** | A6: Home Assistant, on mochaPot | cellar's prompt (optional: blank leaves whiskers off) |
| `PERCH_WHISKERS_ENTITIES`, `PERCH_WHISKERS_EVERY` | not secret | `/config/whiskers.yml`, mounted from `config/whiskers.yml` (step B3) | edit the file |
| `PERCH_BINOCS_SPEEDTEST_URL` | not secret | `http://${GRINDER_LAN_IP}:8765`, built in compose | nothing to type |
| `PERCH_BINOCS_SPEEDTEST_TOKEN` | **secret** | A7: speedtest-tracker, on grinder | cellar's prompt (optional) |
| `PERCH_BINOCS_RELEASES_EVERY`, `PERCH_BINOCS_EVERY` | not secret | `7d`, `15m` (releases are off in perch until this is set) | nothing to type |
| `PERCH_GROOM_DIR` | not secret | `/var/lib/purrbrews/groom` | nothing to type |
| `PERCH_KITTEN_TOKEN_SIEVE`, `_PERCOLATOR`, `_CELLAR`, `_MOCHAPOT`, `_GRINDER`, `_ROASTERY` (six) | **secret** | generated by `setup-secrets.sh` on cellar | read on cellar (F, G), typed into each node's install prompt |
| `PERCH_MEOW_NTFY_URL` | not secret | `https://ntfy.${DOMAIN}/purrbrews-alerts`, built in compose | nothing to type |
| `PERCH_MEOW_NTFY_TOKEN` | **secret** | A3: ntfy, on sieve | cellar's prompt |
| `PERCH_MEOW_QUIET`, `PERCH_MEOW_DIGEST` | not secret | `23:00-07:00`, `07:30` | nothing to type |
| `PERCH_MEOW_CRITICAL_URL` | **secret** | A5: already on sieve | cellar's prompt |
| `PERCH_ACK_SECRET` | **secret** | generated by `setup-secrets.sh` on cellar | never typed |
| `PERCH_PUBLIC_URL` | not secret | `https://perch.${DOMAIN}`, built in compose | nothing to type |
| `PERCH_NINELIVES_URL` | **secret** | A4: healthchecks.io | cellar's prompt |
| `KITTEN_PERCH_URL` | not secret | built by the installer from the node's `DOMAIN` | nothing to type |
| `KITTEN_TOKEN` | **secret** | the node's `PERCH_KITTEN_TOKEN_<NODE>` from cellar | the installer's prompt (Linux); roastery's `setup-secrets.ps1` prompt |
| `KITTEN_POUNCE_PATHS` | not secret | the node's defaults (section F's table); set only to change them | `--pounce` / `.env.local` |
| `KITTEN_GROOM_DIR`, `KITTEN_STATE_DIR` | not secret | kitten's own defaults (`/var/lib/purrbrews/groom`, `/var/lib/purrbrews`) | nothing to type |
| `KITTEN_NODE` | not secret | the installer sets it to the folder name you give it | nothing to type |

(`PERSIAN_PERCH_REF`, the persianPerch tag or commit cellar builds, is a new setting of the fleet side, not in `secrets.env`: `.env.local` on cellar.)

### A1. Komodo: a read-only service user, on cellar (`PERCH_PURR_KEY`, `PERCH_PURR_SECRET`)

1. Open `https://komodo.${DOMAIN}` (or `http://${CELLAR_LAN_IP}:9120`), log in as `barista`.
2. **Settings -> Users -> New service user**, name `perch`. Give it **Read** on every server and every stack and nothing else
   (not Execute, Write or Admin). The wording of the buttons can differ a little in Komodo 2.3.2; the point is a non-admin service user with read-only access.
3. Open the user, **API keys -> Create**. Komodo shows the key and the secret **once**. Keep that tab open: you will paste both into
   cellar's prompts in step D3 (then close it).

*Check:* the user's permissions page shows Read only; there is no key you did not create.

### A2. LLDAP: the `perch-svc` account, on percolator (`PERCH_GLARE_PASSWORD`)

perch reads Gatus's API with a password (a service account, the ollama pattern). It has no browser session.

1. In your own terminal on any node: `openssl rand -hex 32` and keep the output on screen (hex, like every generated secret of the fleet).
2. `https://lldap.${DOMAIN}`, log in as `admin` (`LLDAP_ADMIN_PASSWORD` in `percolator/lldap/secrets.env.local`).
3. **Groups -> New group** `perch_api_group`.
4. **Users -> New user** `perch-svc`, password = the value from step 1. LLDAP's form asks for an email: any address of yours; Authelia sends nothing to it.
5. Put `perch-svc` in **`perch_api_group` only** (not in `purrbrews_admins` or `purrbrews_household`).
6. You will paste the same password into cellar's prompt (D3).

*Check:* the group has exactly one member; the account is in no other group. (Without a human group the account can reach nothing else: Authelia's default is deny.)

### A3. ntfy: perch's own write-only user, on sieve (`PERCH_MEOW_NTFY_TOKEN`)

perch may publish to `purrbrews-alerts` and read nothing. The fleet's ntfy builds its users from the `NTFY_EXTRA_*` lists in
`ntfy/secrets.env.local` (node-local, gitignored, mode 600). This block makes the password and the token, hashes the password with
ntfy's own image, appends `perch` to the three lists (keeping what is already there) and prints nothing secret. The password is never
shown or needed again; the token is read in A3's last command.

```bash
# --- perch's ntfy user (tested by tests/fleet/rolloutSnippets.test.sh)
(
  set -euo pipefail
  cd /opt/purrbrews/stacks/sieve
  source ../_lib/common.sh                 # env_get / env_put: they quote a bcrypt hash the way the fleet's setup expects
  F=ntfy/secrets.env.local
  case "$(env_get "$F" NTFY_EXTRA_USERS)" in *perch:*) echo "perch is already in the ntfy lists; nothing changed" >&2; exit 1 ;; esac
  add() { local cur; cur="$(env_get "$F" "$1")"; env_put "$F" "$1" "${cur:+$cur,}$2"; }
  IMAGE="$(grep -hoE 'binwiederhier/ntfy:[^ "#]+' ntfy/docker-compose.yml | head -n1)"
  PW="$(openssl rand -hex 32)"
  HASH="$(printf '%s\n%s\n' "$PW" "$PW" | sudo docker run --rm -i "$IMAGE" user hash | grep -oE '\$2[aby]\$[0-9]{2}\$[./A-Za-z0-9]{53}' | head -n1 || true)"
  [ -n "$HASH" ] || { echo "hashing failed; nothing was changed" >&2; exit 1; }
  TOKEN="tk_$(openssl rand -hex 15 | cut -c1-29)"
  add NTFY_EXTRA_USERS  "perch:${HASH}:user"
  add NTFY_EXTRA_ACCESS "perch:purrbrews-alerts:wo"
  add NTFY_EXTRA_TOKENS "perch:${TOKEN}:perch"
  echo "perch added to the ntfy lists (write-only on purrbrews-alerts)."
)
cd /opt/purrbrews/stacks/sieve && ./setup-secrets.sh && ./compose.sh ntfy up -d
```

Then read the token in your terminal and keep it for D3 (do not paste it anywhere else):

```bash
grep -o 'perch:tk_[A-Za-z0-9]*' /opt/purrbrews/stacks/sieve/ntfy/secrets.env.local | cut -d: -f2
```

*Check (from sieve; type the token when it asks, so it is not in your history):*

```bash
read -r -s -p "perch token: " T; echo
curl -s -o /dev/null -w 'publish: %{http_code}\n' -H "Authorization: Bearer $T" -d "perch test, ignore" "https://ntfy.${DOMAIN}/purrbrews-alerts"   # 200
curl -s -o /dev/null -w 'read:    %{http_code}\n' -H "Authorization: Bearer $T" "https://ntfy.${DOMAIN}/purrbrews-alerts/json?poll=1"                  # 403
unset T
```

A phone subscribed to `purrbrews-alerts` shows "perch test, ignore". Publish 200 and read 403 is the whole point.

### A4. healthchecks.io: the check for perch's own heartbeat (`PERCH_NINELIVES_URL`)

Same account as sieve's check. **Add Check** -> name `perch`, **period 5 minutes, grace 10 minutes**, add your email/ntfy integration like sieve's. Copy the ping URL
(`https://hc-ping.com/<uuid>`) for D3. It stays a separate check on purpose: `sieve`'s heartbeat watches sieve and Gatus; `perch`'s watches perch.

### A5. The public critical topic (`PERCH_MEOW_CRITICAL_URL`)

The `NTFY_CRITICAL_TOPIC` line of `stacks/sieve/gatus/secrets.env.local` on sieve names the public ntfy.sh topic Gatus already uses for "the self-hosted path is broken".
Read it in your own terminal (`grep '^NTFY_CRITICAL_TOPIC=' /opt/purrbrews/stacks/sieve/gatus/secrets.env.local`); the URL perch wants is `https://ntfy.sh/<that topic>`. Type it into D3's prompt.
A hiss goes to this topic as well, **without** the acknowledge button (a third party would see the link).

### A6. Home Assistant: a non-admin `perch` user and its token, on mochaPot (`PERCH_WHISKERS_TOKEN`)

1. Home Assistant (`https://homeassistant.${DOMAIN}`) as an admin -> **Settings -> People -> Users -> Add user** `perch`. **Administrator off.** ("Can only log in from the local network" can stay on: cellar is on the LAN.)
2. Log in as `perch` (a private window) -> your profile -> **Security -> Long-lived access tokens -> Create**. Home Assistant shows it once; keep the tab for D3.
3. Real entity ids: **Settings -> Devices & services -> Entities**. Collect the ids of your leak and smoke sensors, doors, the pet feeder and fountain, the UPS. They go into `config/whiskers.yml` in step B3. They are not secrets.

The token can do whatever a non-admin Home Assistant user can, including switch things. perch only ever sends `auth`, `subscribe_events` and `get_states`; the tests and the real-socket drill prove it, and the first drill below checks it once more on the real thing.

### A7. speedtest-tracker: a read-only token, on grinder (`PERCH_BINOCS_SPEEDTEST_TOKEN`)

speedtest-tracker's UI on grinder (`http://${GRINDER_LAN_IP}:8765`) -> **API Tokens -> Create**, ability **read only** (`results:read`). Keep it for D3. Blank = no speedtest on perch.

### A8. Nothing to create

`PERCH_ACK_SECRET` and the six `PERCH_KITTEN_TOKEN_*` are generated by `setup-secrets.sh` on cellar (D3).

---

## B. Put the files into the fleet repo (your branch, your pull request)

The agent only prepared files. You apply them in your own process.

**B1.** In your clone `<fleet>` (kept at, or merged up to, a recent `main`):

```bash
git -C <fleet> switch -c persian-perch
```

**B2.** Check, then apply (from your persianPerch checkout; needs bash and git; this is the part that touches `<fleet>`'s working tree and nothing else):

```bash
integration/apply.sh --check <fleet>        # prints "ok: everything applies" or names the patch that does not
integration/apply.sh <fleet>
git -C <fleet> status                       # new: stacks/cellar/persian-perch/, stacks/_lib/groom-record.py; modified: eight files
git -C <fleet> diff                         # read it
```

**B3.** Put your real entity ids into `<fleet>/stacks/cellar/persian-perch/config/whiskers.yml` (every placeholder contains `change_me`; delete the entries you don't want). Entity ids aren't secrets. Leave it as it is and whiskers watches nothing: silently.

**B4.** Run the fleet's own tests on the result (on a machine with python3 and git; they need no Docker or node):

```bash
cd <fleet> && python3 -m unittest discover -s tests       # expect: OK (a few skipped)
```

**B5.** Commit, push the branch and open the pull request. Merge it with a merge commit, your usual way. Nodes then pull `main` daily (or `git -C /opt/purrbrews pull --ff-only` on a node to get it now).

---

## C. Order of the deploy

Do the steps below in this order; each one has a *Check* before the next. Nothing here needs the 01:25-04:25 window; **don't deploy then** (cellar wakes roastery and runs the nightly backups).

| # | Where | What | Step |
|---|---|---|---|
| 1 | percolator | Authelia: the new rules | D1 |
| 2 | sieve | Traefik's `gatus-api` route; DNS records | D2 |
| 3 | mochaPot | the second Pi-hole learns the same names | D2 |
| 4 | each backup node | the groom recorder (systemd drop-ins) | E |
| 5 | cellar | `setup-secrets.sh`, build and start perch | D3 |
| 6 | sieve | Gatus's checks on perch | D4 |
| 7 | percolator | Homepage's tile | D4 |
| 8 | each Linux node, then roastery | kitten | F, G |
| 9 | phone, Home Assistant | acknowledge button, whiskers, drills | I, J |

## D. The deploy, step by step

### D1. percolator: Authelia

After the node has pulled (B5):

```bash
cd /opt/purrbrews/stacks/percolator
./render-configs.sh
./compose.sh authelia up -d --force-recreate
./compose.sh authelia logs --tail 20            # no errors; "Startup complete"
```

*Check:* `https://gatus.${DOMAIN}` still asks for your Authelia login and lets you in (the rules above it were not disturbed).

### D2. sieve and mochaPot: Traefik route and DNS

On **sieve** (Traefik picks up `dynamic/sieve.yml` by itself):

```bash
cd /opt/purrbrews/stacks/sieve
./setup-secrets.sh                     # regenerates the Pi-hole records from every node's routes (perch.${DOMAIN} -> cellar, gatus-api.${DOMAIN} -> sieve)
./compose.sh pihole up -d
dig @${SIEVE_LAN_IP} perch.${DOMAIN} +short          # cellar's address
dig @${SIEVE_LAN_IP} gatus-api.${DOMAIN} +short      # sieve's address
```

On **mochaPot**, the same two commands with its own folder (`/opt/purrbrews/stacks/mochaPot`) and `dig @${MOCHAPOT_LAN_IP} ...`.

*Check, from sieve* (type perch-svc's password when asked; it is not stored):

```bash
curl -s -o /dev/null -w '%{http_code}\n' -u perch-svc "https://gatus-api.${DOMAIN}/api/v1/endpoints/statuses"   # 200
curl -s -o /dev/null -w '%{http_code}\n' "https://gatus-api.${DOMAIN}/api/v1/endpoints/statuses"                  # 401 (no password)
curl -s -o /dev/null -w '%{http_code}\n' -u perch-svc "https://gatus-api.${DOMAIN}/"                                # 404 or 401: only /api/v1/ is routed
```

(The Authelia rule needs a minute to take effect after D1. A `200` for the first, `401` for the second and a refusal for the third is the right shape.)

### D3. cellar: settings, build, start

```bash
cd /opt/purrbrews/stacks/cellar
./setup-secrets.sh
```

It asks for, in this order (each hidden): `PERSIAN_PERCH_REF` (in `.env.local`, not hidden: a persianPerch **tag or full commit** you have chosen; not a branch name), then the Komodo key and secret (A1), `perch-svc`'s password (A2), perch's ntfy
token (A3), the critical topic URL (A5), the healthchecks.io URL (A4), then the two optional ones (A6 token, A7 token; Enter leaves each blank). It generates the six kitten tokens and the acknowledge secret by itself.
Then:

```bash
sudo ./firewall.sh --dry-run | grep -i perch || echo "no perch rule (correct: it publishes nothing)"
./compose.sh persian-perch up -d --build
./compose.sh persian-perch ps                     # healthy after ~30 s
sudo docker logs persian-perch --tail 30          # no traceback
```

Traefik requests a certificate for `perch.${DOMAIN}` (Cloudflare DNS-01): `./compose.sh traefik logs --tail 30` shows no "unable to obtain ACME certificate".
Work through the app's own checklist: `stacks/cellar/persian-perch/README.md` ("Is it working?").

*Check:* `https://perch.${DOMAIN}` asks for Authelia, then shows the overview. Nodes show their state from Komodo; kittens are still "not reporting" (that is step F).
**If every node is `unknown`** and the trail has a row saying purr could not read Komodo's answer, that is the unverified `ListServers {}` / `ServerState` spelling (drill J1): tell the agent; a one-line fix.

### D4. sieve (Gatus) and percolator (Homepage)

Only now, because the new Gatus checks fail until perch answers (and would alert after three failures):

```bash
cd /opt/purrbrews/stacks/sieve && ./compose.sh gatus up -d --force-recreate
cd /opt/purrbrews/stacks/percolator && ./compose.sh homepage up -d
```

*Check:* `https://gatus.${DOMAIN}` lists `perch` and `perch page is behind sso` under *fleet*, both green. Homepage shows the *persianPerch* tile under Admin.

---

## E. The groom recorder, on the backup nodes

`groom/groom-record.py` already arrived with B (it lands at `stacks/_lib/groom-record.py`). The systemd drop-ins are node-local files, installed the way the fleet installs its own units. From a persianPerch checkout on the node (clone it first: step F1):

On **every backup node** (sieve, percolator, cellar, mochaPot, grinder):

```bash
sudo install -D -m 644 ~/persianPerch/integration/groom/units/purrbrews-backup@.service.d/groom.conf /etc/systemd/system/purrbrews-backup@.service.d/groom.conf
sudo systemctl daemon-reload
systemctl cat purrbrews-backup@<node>.service | grep ExecStopPost       # the recorder line is there
```

On **cellar only**, also the six drop-ins of cellar's own jobs:

```bash
for unit in purrbrews-wake-roastery purrbrews-backup-store drive-sync purrbrews-backup-check restic-prune purrbrews-backup-verify; do
  sudo install -D -m 644 ~/persianPerch/integration/groom/units/$unit.service.d/groom.conf /etc/systemd/system/$unit.service.d/groom.conf
done
sudo systemctl daemon-reload
```

The recorder runs only when a backup unit **stops** (after the next nightly run). Nothing changes about the jobs: a leading `-` means a recorder problem can never fail one.
*Check (the morning after):* `sudo ls /var/lib/purrbrews/groom/nightly/` on a node shows a `.json` per run, and perch's `/groom` grid fills in. Details: `integration/groom/README.md`.

---

## F. kitten on the Linux nodes (sieve, percolator, cellar, mochaPot, grinder)

kitten is persianPerch's small agent: every minute it tells perch the node is alive and hands over backup records; with pounce it also reports the **names** (never contents) of files that appear in a few folders. It runs as a system user `kitten`, no shell, and only **reads**.

### F1. Once per node: the persianPerch checkout

```bash
git clone https://github.com/purrMonster/persianPerch.git ~/persianPerch
```

### F2. Per node, in this order: cellar first (it makes the tokens), then the rest

On **cellar**, read that node's token in your terminal (do not copy it anywhere but the next prompt):

```bash
grep '^PERCH_KITTEN_TOKEN_GRINDER=' /opt/purrbrews/stacks/cellar/persian-perch/secrets.env.local | cut -d= -f2
```

(`..._SIEVE`, `_PERCOLATOR`, `_CELLAR`, `_MOCHAPOT`, `_GRINDER`; roastery's is step G.)

On the node (cellar included; the same four commands each time; `<ref>` is the persianPerch tag or commit you chose in D3):

```bash
git -C ~/persianPerch fetch --tags && git -C ~/persianPerch checkout <ref>
cd ~/persianPerch && python3 -m kitten.build /tmp/kitten.pyz            # as yourself, not root; standard library only
cd integration/kitten && sudo ./install-kitten.sh <node> --pyz /tmp/kitten.pyz      # asks for the token (hidden)
```

The installer installs `inotify-tools` and `git` if they are missing (the only system change besides its own files), makes the `kitten` user, puts `kitten.pyz` in `/opt/kitten` (root-owned), writes
`/etc/purrbrews/kitten.env` (root, 0600, with the report URL built from the node's own `DOMAIN`), installs `kitten.service`, starts it, and prints which of pounce's folders the `kitten` user can list.
Pounce will say "settings changed: kitten.env" once, on the trail: that is the sense working (and a morning-digest line).

*Check:* `sudo journalctl -u kitten -n 20 --no-pager` has no "unreachable" or 401/403; within two minutes perch's overview shows that node's kitten as reporting.
If **cellar's own** kitten is refused with `403`, Traefik is seeing Docker's bridge address instead of cellar's LAN address for traffic from the node to itself: tell the agent (the fix is one more address in the nodes router's allow-list).
Remove it again: `sudo ./install-kitten.sh --remove`.

### Which of pounce's folders the `kitten` user can list (A10: reported, not worked around)

| Node | Folder | Listable by default? |
|---|---|---|
| every Linux node | `/etc/purrbrews` | **yes** (mode 755; the files inside are private but their names are listed) |
| every Linux node | `/opt/purrbrews/.git` and `/opt/purrbrews/.git/refs/heads` (the node pulled) | **yes**, if the checkout's permissions are the defaults. perch asks `git` itself for the commit subject, with `safe.directory` set for that run |
| cellar | `/srv/dumps` | **only the top level.** Each `<node>` folder inside it is mode 700 for the `dumps` user, and cellar's own is 700 root; `inotifywait` skips them silently. pounce sees a folder appear, **not the dump files inside**. groom (the records) is what says whether the dumps happened |
| percolator | `/srv/data/paperless/consume` | **yes** (mode 2775: others can read and enter) |
| roastery | `C:\purrbrews\restic\snapshots` | **depends on the folder's ACL** (step G): `setup.ps1` replaced `C:\purrbrews`'s permissions. The task runs as you with administrator rights; if kitten's log says "can't list ... Access is denied", the folder is not listable |

If a folder says NOT LISTABLE you decide whether to widen it. The agent did not: giving a watcher more access is yours to decide. To switch a path off or change the list on a node: re-run the installer with `--pounce 'path|level|why;...'` (or `--pounce none`).

---

## G. kitten on roastery (Scheduled Task)

roastery sleeps; kitten runs while it is awake, and perch knows roastery's wake window, so silence outside it is not a problem.

1. In the fleet clone on roastery (after B5's pull): `cd <fleet>\stacks\roastery`, then `.\setup-secrets.ps1`. It asks for `KITTEN_TOKEN` (a new key of `local.env.example`): paste roastery's token, read on cellar as in F2 (`PERCH_KITTEN_TOKEN_ROASTERY`). It stays in roastery's own `.env.local`.
2. A persianPerch checkout and the build (roastery has Git, Docker Desktop and Python 3.14): `git clone https://github.com/purrMonster/persianPerch.git`, `git checkout <ref>`, then
   `powershell -ExecutionPolicy Bypass -File scripts\buildKitten.ps1` (a container builds `dist\kitten.pyz`; nothing is installed on roastery).
3. From an **elevated** PowerShell in `persianPerch\integration\roastery`:

```powershell
.\install-kitten.ps1 -FleetRoot <fleet> -DryRun        # says what it would do and checks your settings; changes nothing
.\install-kitten.ps1 -FleetRoot <fleet>                # installs and starts it
```

   It copies the program and `run-kitten.ps1` to `C:\ProgramData\purrbrews\kitten` (not under `C:\purrbrews`, the restic chroot), registers the task **purrBrews kitten** (at startup and when roastery resumes from sleep; one copy at a time; restarts itself),
   running as you with administrator rights **without storing a password**, and starts it. The token is read by `run-kitten.ps1` from `.env.local` when the task starts; it is not in the task's definition.
4. *Check:* `Get-Content -Tail 20 C:\ProgramData\purrbrews\kitten\kitten.log` has no "perch unreachable" and no "refused"; perch shows roastery reporting. If the log says `pounce can't list C:\purrbrews\restic\snapshots: Access is denied`, see the table above.
   Roastery's IP is in `ROASTERY_LAN_IP` and **has no DHCP reservation yet** (the fleet's own backlog): check `Get-NetIPAddress` still shows that address, and fix the reservation before relying on the allow-list.
   Remove: `.\install-kitten.ps1 -Remove`.

---

## H. Gatus layer-1 alerts: the week of both, then retire (A6)

For the first full week (**until you decide**), old and new alerts run side by side. perch's titles start with `perch:` so you can tell them apart. In that week watch for **false hisses**: that is the real test of M6.

After the week, if perch's alerts have covered everything the old ones did (compare the phone's history), you may retire the duplicates. Each is a change to a fleet file or a node-local setting, made the usual way:

1. **Gatus's `ntfy`-type alerts.** In `stacks/sieve/gatus/config/config.yaml` remove the `type: ntfy` alert from each endpoint **except the two perch checks** (`perch` and `perch page is behind sso`: perch can't alert on its own death). **Keep every `type: custom` alert** (the tunnel, ntfy, ntfy public: they go to ntfy.sh and watch the path perch's own alerts travel through). Keep the `alerting:` section and the `healthchecks.io heartbeat` endpoint. Then `./compose.sh gatus up -d --force-recreate` on sieve.
   *Check:* `grep -n 'type: ntfy' stacks/sieve/gatus/config/config.yaml` lists only the two perch checks; `grep -c 'type: custom'` is still 3.
2. **`backup.sh`'s failure notify and `check-freshness.sh`'s notify.** Both use `NTFY_URL` in `stacks/<node>/restic/secrets.env.local` (cellar's covers its own jobs and the 06:00 morning check). On each node: delete the `NTFY_URL=` line, run `./setup-secrets.sh`, press Enter at that optional prompt. Blank means no alerts (the fleet's own convention).
   *Check:* on a node, `grep NTFY_URL stacks/<node>/restic/secrets.env.local` shows an empty value.
3. **Keep, always:** Gatus's critical checks (they go to ntfy.sh) and **sieve's healthchecks.io heartbeat**. perch cannot watch the path its own alerts take, and nothing on sieve can report sieve being down.

Before this you can still go back: put the lines back and recreate Gatus.

---

## I. The acknowledge button and the phone

The button on a push opens `https://perch.${DOMAIN}/ack/t/<token>`: the phone must reach `perch.${DOMAIN}`. **On the LAN (home Wi-Fi) it works.** Away from home it works only once the phone joins the tailnet (a fleet backlog item), because the name resolves to cellar's LAN address. The button is on pushes through your own ntfy only, never on the ntfy.sh copy.

---

## J. Post-deploy drills (your checklist; C12)

Tick each only when you saw it. Record anything surprising in the fleet's runbook and tell the agent.

### Made once, at the start

- [ ] **J1. Komodo's `ListServers {}` and `ServerState` spelling against the real Komodo 2.3.2.** perch's overview shows each node with its CPU/RAM/disk and a state that is not `unknown`; `sudo docker logs persian-perch` has no row about an answer purr could not read. (Built from source and fixtures only; this is the first time it meets the real thing.)
- [ ] **J2. Gatus's real key for the tunnel check.** `curl -s -u perch-svc "https://gatus-api.${DOMAIN}/api/v1/endpoints/statuses" | grep -o '"key":"[^"]*"' | sort` lists `network_cloudflare-tunnel`; perch's overview shows the tunnel.
- [ ] **J3. Scrutiny's collectors report `host_id` as the node names.** On cellar: `curl -s http://127.0.0.1:8080/api/summary | grep -o '"host_id":"[^"]*"' | sort -u` lists `sieve`, `percolator`, `cellar`, `mochaPot`, `grinder` spelled like the folders (else the disks panel can't match a disk to a node).
- [ ] **J4. The kitten user's access.** On every node `sudo journalctl -u kitten --no-pager | grep -i "can't"` shows only the folders the table in F says are not listable, and nothing else. roastery: the same in `kitten.log`.
- [ ] **J5. Non-admin Home Assistant user.** perch's Home card says "N sensors watched" with the real count; in Home Assistant the `perch` user is not an administrator; nothing in Home Assistant's logbook was changed by `perch`.

### The dev plan's "Done when", one per milestone

- [ ] **M0:** `https://perch.${DOMAIN}/tree` lists every node and app of the fleet repo.
- [ ] **M1: stop a container on grinder, then start it.** On grinder, a container you can spare for a few minutes: `./compose.sh <app> stop`. Within **60 seconds** the app's page, grinder and the fleet turn hiss on perch; `./compose.sh <app> start` brings them back to slowBlink. (Exactly **one** push and one recovery push, M3.)
- [ ] **M1: roastery in and out of its window.** Asleep outside 01:25-04:25: slowBlink, not hiss. Awake and unreachable inside the window: hiss (leave this one to a night when you are looking; or read perch's trail the morning after).
- [ ] **M2: a night with one node's backup disabled.** On a node you don't mind skipping once: `sudo systemctl disable --now purrbrews-backup@<node>.timer`. In the morning exactly that cell of `/groom` shows hiss (by 04:30) and nothing else. Then `sudo systemctl enable --now purrbrews-backup@<node>.timer`. (The old alerts will also fire: that is the side-by-side week.)
- [ ] **M3: unplug grinder** (the network cable, for a few minutes). **One** push ("grinder unreachable: N apps affected", to ntfy and the ntfy.sh topic), then **one** recovery push. The acknowledge button on the first one stops the repeats (I).
- [ ] **M3: stop perch.** `./compose.sh persian-perch stop` on cellar: healthchecks.io alerts you within **10 minutes** (A4's check goes late); Gatus's `perch` check alerts too. `./compose.sh persian-perch start` after.
- [ ] **M4:** you reach for perch's overview instead of Gatus and Scrutiny for the daily look, for a week.
- [ ] **M5:** copy a PDF you don't mind Paperless importing into `/srv/data/paperless/consume` on percolator, **and** open a door sensor: both show on `/trail` within **5 seconds**, with the right body language (the file `earTwitch`, the door `earTwitch`). Delete the imported document afterwards.
- [ ] **M6:** it has run a full week on the fleet with **no false hiss**.

### Left for the real fleet by the milestones' entries

- [ ] **A real leak-sensor test.** With the household warned (this sends a real critical push): trip your leak sensor for real (its test button, or a damp cloth). The `perch` page shows a hiss within seconds, a push arrives on the phone **with the Acknowledge button**, a critical copy reaches the ntfy.sh topic **without** one; acknowledge from the phone; dry the sensor: a recovery push follows.
- [ ] **Home Assistant's own leak alert.** In Home Assistant, confirm the leak and smoke sensors also notify your phone on their own (an automation or the companion app's notification). **This is what covers you while whiskers is down** (see "The decisions").
- [ ] **whiskers when Home Assistant is down is a tailFlick, never a hiss.** Stop Home Assistant for a few minutes on mochaPot: purr and glare hiss (container, endpoint); whiskers' own collector shows a tailFlick ("whiskers is late"), never a hiss; every entity shows unknown, none a hiss. Start it again: everything returns to slowBlink.
- [ ] **A change under `/etc/purrbrews` is the digest, never a push.** On a node: `sudo touch /etc/purrbrews/perch-drill`. Within seconds `/trail` shows "settings changed: perch-drill appeared" as a tailFlick; **no push arrives**. The next 07:30 digest carries a line for that node. `sudo rm /etc/purrbrews/perch-drill` afterwards.
- [ ] **The acknowledge button from the phone on the LAN.** Press it on a push: the litter shows "acknowledged from the push"; pressing the same push again fails (single use). Away from home: only after the phone joins the tailnet.
- [ ] **`/trail/stream` stays live behind Traefik.** Open `/trail`, leave it for 5 minutes, then cause an event (the `touch` above): the row appears **without a reload**. In the browser's network panel the stream is `text/event-stream`, with no `content-encoding`. If it only appears after a reload, something buffers or compresses it: look at the router labels first.
- [ ] **A kitten report only from a node.** From a laptop on Wi-Fi: `curl -s -o /dev/null -w '%{http_code}\n' -X POST https://perch.${DOMAIN}/api/kitten` prints `403`; from a node, the same prints `401` (reached perch, no token).
- [ ] **roastery's task survives sleep.** After a night, `kitten.log` shows kitten running after the 01:25 wake, and perch's roastery card is not a hiss outside the window.
- [ ] **Everything else's silence is quiet.** After a quiet day the 07:30 digest either arrives with real lines or does not arrive (nothing overnight is no push).

---

## K. Last step: put roastery's sleep setting back (A4)

roastery was kept awake for the build and the rollout. When the drills above no longer need it awake: **Settings -> System -> Power -> Screen and sleep** on roastery, set "sleep after" back to what it was before (the nightly wake at 01:25 depends on it sleeping in between). Then tick the runbook's backlog line.

## Undoing it

- perch: `./compose.sh persian-perch down` on cellar. Nothing else depends on it; the page, the pushes and the Gatus checks on perch simply go away.
- kitten: `sudo ./install-kitten.sh --remove` on each node; `.\install-kitten.ps1 -Remove` on roastery.
- groom recorder: delete the `groom.conf` drop-ins and `systemctl daemon-reload`; the jobs never depended on it.
- the fleet repo: revert the pull request.
