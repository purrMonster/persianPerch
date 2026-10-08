# persianPerch

The fleet's watcher: one private page, shaped like this repo, that shows what the fleet does,
live and with history. Containers and node vitals (**purr**), backups (**groom**), disks,
endpoints (**glare**), files dropped on the nodes (**pounce**), the house (**whiskers**) and the
world outside (**binocs**). Alerts (**meow**) go to ntfy. It only watches: nothing in it changes
anything on the fleet. Source, design and decisions:
[github.com/purrMonster/persianPerch](https://github.com/purrMonster/persianPerch).

| | |
|---|---|
| Image | built on cellar from the public persianPerch repo at `PERSIAN_PERCH_REF` (a tag or full commit) |
| URL | `https://perch.${DOMAIN}` (admins, behind Authelia). Two paths skip Authelia, see below |
| Ports | none published: Traefik reaches it over `cellar_net` |
| Data | `/srv/data/persian-perch` (scentTrail, SQLite in WAL mode); 300 MB memory limit |
| Reads | Komodo (`komodo-core:9120`) and Scrutiny (`scrutiny:8080`) by name; Gatus, ntfy, Home Assistant and speedtest-tracker over the LAN; `/opt/purrbrews` (read-only) and `/var/lib/purrbrews` (read-only) on this node |
| Secrets | the prompts and the generated values in [`secrets.conf`](secrets.conf); each is explained in persianPerch's `secrets.env` |

## Three routes on one name

All three are Traefik labels in [`docker-compose.yml`](docker-compose.yml), because every cellar
app routes that way and perch's own address list comes straight from `fleet.env`.

| Route | Who can reach it | Why it is that way |
|---|---|---|
| `perch.${DOMAIN}` (everything else) | signed-in admins (Authelia) | the page |
| `/api/kitten` and `/healthz` | only the six fleet addresses (`SIEVE_LAN_IP` ... `ROASTERY_LAN_IP`), and a kitten still needs its node's own bearer token | a kitten has no browser session. Gatus on sieve reads `/healthz` here |
| `/ack/t/` (prefix only) | anyone, 10 requests a minute | the Acknowledge button on a push: a signed, single-use link that can only stop one alert repeating |

`/trail/stream` is a live `text/event-stream`. No router has a compress or buffering middleware
and the service flushes at once; if the live trail ever stops moving behind Traefik, look there first.

## Bring up

Read persianPerch's `integration/ROLLOUT.md` first: the Komodo key, the `ocicat` account, perch's
ntfy token and the healthchecks.io check have to exist before this starts, and the order matters.

```bash
./setup-secrets.sh            # asks PERSIAN_PERCH_REF (.env.local) and the prompts in secrets.conf
./compose.sh persian-perch up -d --build
```

`config/whiskers.yml` is tracked: put the real entity ids in it in the repo (a branch, like any change) before
the node pulls it, not by hand on cellar, or the next daily pull collides with the edit.

`PERSIAN_PERCH_REF` is a persianPerch tag or full commit. To update, change it in `.env.local` and run
`./compose.sh persian-perch up -d --build`.

## Is it working?

- [ ] `./compose.sh persian-perch ps` shows `healthy`; `sudo docker logs persian-perch` has no traceback
- [ ] `https://perch.${DOMAIN}` asks for an Authelia login, then shows the overview (a slowBlink fleet once every sense has looked)
- [ ] Every node's card on the overview says its kitten reported in the last few minutes (after the kittens are installed)
- [ ] `/trail` keeps getting new rows without a reload (the stream is not buffered)
- [ ] From a fleet node (not from a laptop on Wi-Fi): `curl -s -o /dev/null -w '%{http_code}\n' https://perch.${DOMAIN}/healthz` prints `200`; from anywhere else on the LAN the same request prints `403`
- [ ] `https://perch.${DOMAIN}/ack/t/not-a-token` answers `403` without a login (and `/ack/anything` still asks for one)
- [ ] An ntfy test push from perch's user arrives (ROLLOUT.md, step "ntfy")
- [ ] `sudo ./backup.sh plan` lists `persian-perch.sql.gz` under cellar's dumps

## Gotchas

- **No default account.** perch has no login of its own; Authelia is the only gate. That is why no port is published.
- **The domain and the addresses are not in persianPerch's repo.** `${DOMAIN}` and the node addresses come from `.env.local` and `fleet.env` here, like every other app.
- **A placeholder `whiskers.yml` is silent, not broken.** Until the entity ids are real, whiskers watches nothing, so a leak sensor would not be seen. Edit it before relying on the house.
- **While whiskers is down perch cannot see leak or smoke sensors.** Home Assistant's own alerts must cover them (persianPerch decided that a Home Assistant outage is a tailFlick for whiskers, not a hiss, because purr and glare already hiss for the same outage).
- **Pull the checkout before an update.** perch lists `/opt/purrbrews` (tracked files only); it shows what this node last pulled.
- **Recovery.** Lose the container and nothing is lost but history: `./compose.sh persian-perch up -d --build` rebuilds it, and the nightly dump of scentTrail is in restic if you want the history back.
