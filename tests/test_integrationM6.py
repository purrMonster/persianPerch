"""integration/ (M6, prepare only): the files the owner applies to purrbrews-containers, checked against the
pinned fleet repo, against persianPerch's own settings (secrets.env, perch/settings.py, kitten) and against
ROLLOUT.md. Nothing here touches a node or the network. The fleet's own test suite on a copy with integration/
applied is a separate step of scripts/test.ps1 (it needs its own container); so are the install scripts."""

import importlib.util
import re
import subprocess
from pathlib import Path

import pytest
import yaml
from conftest import FLEET_COMMIT, ROOT

from kitten.pounce import ROASTERY, defaultWatches
from perch.senses.whiskers import parseConfig
from perch.settings import NODES

INTEG = ROOT / "integration"
APP = INTEG / "stacks" / "cellar" / "persian-perch"
COMPOSE = APP / "docker-compose.yml"
ROLLOUT = (INTEG / "ROLLOUT.md").read_text(encoding="utf-8")
NODE_FOLDERS = ["sieve", "percolator", "cellar", "mochaPot", "grinder"]


def secretsEnvEntries() -> dict[str, str]:
    """key -> the verb in the [brackets] of the comment above it in secrets.env."""
    found, verb = {}, ""
    for line in (ROOT / "secrets.env").read_text(encoding="ascii").splitlines():
        m = re.match(r"^#\s*\[([^\]]+)\]", line)
        if m:
            verb = m.group(1).strip()
        k = re.match(r"^([A-Z0-9_]+)=", line)
        if k:
            found[k.group(1)] = verb
            verb = ""
    return found


def secretsConf() -> dict[str, str]:
    """key -> the rest of its line in the prepared secrets.conf (kind and arguments)."""
    out = {}
    for line in (APP / "secrets.conf").read_text(encoding="utf-8").splitlines():
        if not line.strip() or line.startswith("#") or line.startswith("NOTE "):
            continue
        key, _, rest = line.partition(" ")
        out[key] = rest.strip()
    return out


def compose() -> dict:
    return yaml.safe_load(COMPOSE.read_text(encoding="utf-8"))


def labels() -> dict[str, str]:
    out = {}
    for item in compose()["services"]["persian-perch"]["labels"]:
        key, _, value = item.partition("=")
        out[key] = value
    return out


def fleetEnv(fleetRepo: Path) -> dict[str, str]:
    return dict(
        line.split("=", 1)
        for line in (fleetRepo / "stacks" / "fleet.env").read_text().splitlines()
        if re.match(r"^[A-Z_]+=", line)
    )


# -- the pin and the application ----------------------------------------------------------------------------


def test_the_patches_were_made_against_the_pinned_commit():
    assert (INTEG / "PIN").read_text().strip() == FLEET_COMMIT


def test_apply_sh_checks_clean_against_the_pinned_fleet_repo(fleetRepo):
    run = subprocess.run(
        ["bash", str(INTEG / "apply.sh"), "--check", str(fleetRepo)], capture_output=True, text=True, check=False
    )
    assert run.returncode == 0, run.stdout + run.stderr
    assert "everything applies" in run.stdout


def test_apply_sh_refuses_a_dirty_clone(tmp_path, fleetRepo):
    clone = tmp_path / "fleet"
    subprocess.run(["git", "clone", "-q", str(fleetRepo), str(clone)], check=True, capture_output=True)
    (clone / "stacks" / "cellar" / "stray.txt").write_text("not committed")
    run = subprocess.run(
        ["bash", str(INTEG / "apply.sh"), "--check", str(clone)], capture_output=True, text=True, check=False
    )
    assert run.returncode != 0 and "uncommitted changes" in run.stderr


def test_apply_sh_applies_everything_and_never_commits(tmp_path, fleetRepo):
    clone = tmp_path / "fleet"
    subprocess.run(["git", "clone", "-q", str(fleetRepo), str(clone)], check=True, capture_output=True)
    subprocess.run(
        ["git", "-C", str(clone), "-c", "advice.detachedHead=false", "checkout", "-q", FLEET_COMMIT], check=True
    )
    run = subprocess.run(["bash", str(INTEG / "apply.sh"), str(clone)], capture_output=True, text=True, check=False)
    assert run.returncode == 0, run.stdout + run.stderr
    head = subprocess.run(
        ["git", "-C", str(clone), "rev-parse", "HEAD"], capture_output=True, text=True, check=False
    ).stdout.strip()
    assert head == FLEET_COMMIT  # nothing committed
    status = subprocess.run(
        ["git", "-C", str(clone), "status", "--porcelain"], capture_output=True, text=True, check=False
    ).stdout
    assert "?? stacks/cellar/persian-perch/" in status and "?? stacks/_lib/groom-record.py" in status
    assert status.count(" M ") == 8
    nodeConf = (clone / "stacks" / "cellar" / "node.conf").read_text()
    assert "APPS=(komodo scrutiny traefik smb persian-perch)" in nodeConf
    for name in ("docker-compose.yml", "secrets.conf", "backup", "firewall", "data-dirs", "README.md"):
        assert (clone / "stacks" / "cellar" / "persian-perch" / name).is_file(), name
    again = subprocess.run(
        ["bash", str(INTEG / "apply.sh"), "--check", str(clone)], capture_output=True, text=True, check=False
    )
    assert again.returncode != 0  # applying twice is refused, not repeated


# -- secrets.conf is generated from secrets.env's verbs (05 plan C13) ----------------------------------------


def test_every_perch_setting_in_secrets_env_is_in_secrets_conf_or_built_by_compose():
    env = compose()["services"]["persian-perch"]["environment"]
    conf = secretsConf()
    for key in secretsEnvEntries():
        if not key.startswith("PERCH_"):
            continue  # KITTEN_* belong to the nodes
        assert key in conf or key in env, f"{key} is in secrets.env but neither in secrets.conf nor in compose"


def test_secrets_conf_has_no_key_secrets_env_does_not_know():
    known = secretsEnvEntries()
    assert set(secretsConf()) <= set(known)


def test_secrets_conf_verbs_are_the_ones_secrets_env_names():
    known = secretsEnvEntries()
    for key, rest in secretsConf().items():
        verb = known[key]
        kind = rest.split()[0]
        assert verb.split()[0] == kind, f"{key}: secrets.env says [{verb}], secrets.conf says {kind}"
        if kind == "hex":
            assert verb == f"hex {rest.split()[1]}", key
        if kind == "value" and "${" not in verb:
            assert verb == f"value {rest.partition(' ')[2]}", f"{key}: {verb!r} vs {rest!r}"


def test_values_with_a_variable_are_built_in_compose_not_in_secrets_conf():
    env = compose()["services"]["persian-perch"]["environment"]
    for key, verb in secretsEnvEntries().items():
        if key.startswith("PERCH_") and verb.startswith("value") and "${" in verb:
            assert key not in secretsConf(), key
            assert key in env and "${" in str(env[key]), f"{key} should be built from DOMAIN or fleet.env in compose"


def test_the_secrets_are_prompted_or_generated_never_written():
    secret_keys = {
        "PERCH_PURR_KEY", "PERCH_PURR_SECRET", "PERCH_GLARE_PASSWORD", "PERCH_WHISKERS_TOKEN",
        "PERCH_BINOCS_SPEEDTEST_TOKEN", "PERCH_MEOW_NTFY_TOKEN", "PERCH_MEOW_CRITICAL_URL",
        "PERCH_ACK_SECRET", "PERCH_NINELIVES_URL",
        *(f"PERCH_KITTEN_TOKEN_{n.upper()}" for n in NODES),
    }  # fmt: skip
    conf = secretsConf()
    for key in secret_keys:
        assert conf[key].split()[0] in ("prompt", "hex"), f"{key} must be asked for or generated"


def test_nothing_in_integration_holds_a_secret_a_real_domain_or_a_lan_address():
    patterns = {
        "token": re.compile(r"tk_[A-Za-z0-9]{20,}"),
        "long hex": re.compile(r"\b[0-9a-f]{40,}\b"),
        "jwt": re.compile(r"eyJ[A-Za-z0-9_-]{20,}"),
        "private key": re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"),
        "ip": re.compile(r"\b(?!127\.0\.0\.1\b)\d{1,3}\.\d{1,3}\.\d{1,3}\.\d{1,3}\b"),
        "windows profile": re.compile(r"C:\\Users\\", re.I),
        "bearer value": re.compile(r"Bearer [A-Za-z0-9._-]{20,}"),
    }
    for path in INTEG.rglob("*"):
        if not path.is_file() or "groom" in path.parts and path.suffix == ".py":
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for name, rx in patterns.items():
            for m in rx.finditer(text):
                if name == "long hex" and m.group(0) == FLEET_COMMIT:
                    continue
                pytest.fail(f"{path.relative_to(ROOT)} has a {name}: {m.group(0)[:40]}")


# -- the compose file ------------------------------------------------------------------------------------------


def test_compose_runs_perch_the_way_the_design_budgets_it():
    svc = compose()["services"]["persian-perch"]
    assert "ports" not in svc, "perch has no login of its own: nothing may be published"
    assert svc["read_only"] is True and svc["cap_drop"] == ["ALL"]
    assert "no-new-privileges:true" in svc["security_opt"]
    assert svc["mem_limit"] == "300m"
    assert "healthcheck" in svc and "/healthz" in " ".join(svc["healthcheck"]["test"])
    nets = compose()["networks"]["default"]
    assert nets == {"name": "cellar_net", "external": True}
    assert "networks" not in svc  # it joins the default network, which is cellar_net
    assert "/opt/purrbrews:/opt/purrbrews:ro" in svc["volumes"]
    assert "./config/whiskers.yml:/config/whiskers.yml:ro" in svc["volumes"]


def test_compose_builds_a_pinned_ref_of_the_public_repo_and_refuses_an_unset_one():
    build = compose()["services"]["persian-perch"]["build"]["context"]
    assert build.startswith("https://github.com/purrMonster/persianPerch.git#${PERSIAN_PERCH_REF:?")


def test_every_environment_name_is_one_perch_actually_reads():
    read = set()
    for source in (ROOT / "perch").rglob("*.py"):
        read |= set(re.findall(r"\bPERCH_[A-Z0-9_]+", source.read_text(encoding="utf-8")))
    env = compose()["services"]["persian-perch"]["environment"]
    for key in env:
        if key.startswith("PERCH_KITTEN_TOKEN_"):
            assert key.removeprefix("PERCH_KITTEN_TOKEN_").lower() in {n.lower() for n in NODES}, key
        elif key.startswith("PERCH_"):
            assert key in read, f"compose sets {key}, which perch never reads"


def test_every_compose_variable_is_defined_by_the_fleet(fleetRepo):
    defined = set(secretsConf()) | set(fleetEnv(fleetRepo)) | {"DOMAIN", "DATA_DIR", "TZ", "PERSIAN_PERCH_REF"}
    text = COMPOSE.read_text(encoding="utf-8")
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        for name in re.findall(r"\$\{([A-Za-z_][A-Za-z0-9_]*)", line):
            assert name in defined, f"{name} is used in compose but nothing defines it"


def test_three_routers_one_behind_authelia_and_two_that_say_why_they_are_not():
    lab = labels()
    host = "Host(`perch.${DOMAIN}`)"
    page, nodes, ack = (lab[f"traefik.http.routers.{r}.rule"] for r in ("perch", "perch-nodes", "perch-ack"))
    assert page == host
    assert nodes.startswith(host + " && ") and "Path(`/api/kitten`)" in nodes and "Path(`/healthz`)" in nodes
    assert ack == host + " && PathPrefix(`/ack/t/`)"
    assert lab["traefik.http.routers.perch.middlewares"] == "authelia-forwardauth@file"
    assert lab["traefik.http.routers.perch-nodes.middlewares"] == "perch-nodes"
    assert lab["traefik.http.routers.perch-ack.middlewares"] == "perch-ack-limit"
    # the narrower routers win over the page
    assert int(lab["traefik.http.routers.perch.priority"]) < int(lab["traefik.http.routers.perch-nodes.priority"])
    assert int(lab["traefik.http.routers.perch.priority"]) < int(lab["traefik.http.routers.perch-ack.priority"])
    # the only thing the ack router and the nodes router do is their own middleware
    for router in ("perch-nodes", "perch-ack"):
        assert "authelia" not in lab[f"traefik.http.routers.{router}.middlewares"]
    for router in ("perch", "perch-nodes", "perch-ack"):
        assert lab[f"traefik.http.routers.{router}.service"] == "perch"
        assert lab[f"traefik.http.routers.{router}.entrypoints"] == "websecure"
        assert lab[f"traefik.http.routers.{router}.tls.certresolver"] == "cloudflare"


def test_the_kitten_router_admits_exactly_the_fleet_nodes_including_roastery(fleetRepo):
    allow = labels()["traefik.http.middlewares.perch-nodes.ipallowlist.sourcerange"]
    used = re.findall(r"\$\{([A-Z_]+)\}", allow)
    assert sorted(used) == sorted(k for k in fleetEnv(fleetRepo) if k.endswith("_LAN_IP"))
    assert "ROASTERY_LAN_IP" in used and allow.count(",") == len(used) - 1


def test_the_ack_router_is_rate_limited_to_ten_a_minute():
    lab = labels()
    assert lab["traefik.http.middlewares.perch-ack-limit.ratelimit.average"] == "10"
    assert lab["traefik.http.middlewares.perch-ack-limit.ratelimit.period"] == "1m"


def test_nothing_buffers_or_compresses_the_live_trail():
    lines = COMPOSE.read_text(encoding="utf-8").splitlines()
    code = " ".join(x for x in lines if not x.lstrip().startswith("#")).lower()
    assert "compress" not in code and "buffering" not in code and "retry" not in code
    assert labels()["traefik.http.services.perch.loadbalancer.responseforwarding.flushinterval"] == "1ms"


def test_the_routes_become_dns_records_by_the_fleets_own_generator(fleetRepo):
    """The fleet's dns-records.py makes a record of each Host(...) rule line, and errors on one it can't read."""
    spec = importlib.util.spec_from_file_location("dnsRecords", fleetRepo / "stacks" / "_lib" / "dns-records.py")
    dns = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(dns)
    found = set()
    for line in COMPOSE.read_text(encoding="utf-8").splitlines():
        if dns.RULE.match(line):
            assert "Host(" not in line or dns.HOST.findall(line), f"unsupported Host rule: {line.strip()}"
            found |= set(dns.HOST.findall(line))
    assert found == {"perch"}
    sieve = (INTEG / "patches" / "sieve-gatus-api-router.patch").read_text()
    assert 'gatus-api.{{ env "DOMAIN" }}' in sieve


# -- the other files -------------------------------------------------------------------------------------------


def test_backup_uses_a_sqlite_line_and_never_the_live_file_as_a_path():
    lines = [x.split("#")[0].split() for x in (APP / "backup").read_text().splitlines() if x.split("#")[0].strip()]
    assert [x[0] for x in lines] == ["sqlite"]
    assert lines[0][2] == "persian-perch/scentTrail.db"


def test_data_dirs_make_the_folder_for_the_images_fixed_user():
    dockerfile = (ROOT / "Dockerfile").read_text()
    uid = re.search(r"useradd[^\n]*--uid (\d+)", dockerfile).group(1)
    assert f"persian-perch {uid}:{uid} 750" in (APP / "data-dirs").read_text()


def test_firewall_opens_nothing():
    rules = [x for x in (APP / "firewall").read_text().splitlines() if x.strip() and not x.lstrip().startswith("#")]
    assert rules == []


def test_whiskers_yml_parses_and_every_entity_is_still_a_placeholder():
    entities = parseConfig((APP / "config" / "whiskers.yml").read_text(encoding="utf-8"))
    assert entities and all("change_me" in eid for eid in entities)
    assert any(any(lvl.value == "hiss" for lvl in e.levels.values()) for e in entities.values())  # leak, smoke


def test_the_kitten_unit_runs_unprivileged_and_matches_the_installer():
    unit = (INTEG / "kitten" / "kitten.service").read_text()
    installer = (INTEG / "kitten" / "install-kitten.sh").read_text()
    assert re.search(r"^User=kitten$", unit, re.M) and "User=root" not in unit
    assert re.search(r"^NoNewPrivileges=yes$", unit, re.M)
    envFile = re.search(r"^ENV_FILE=(\S+)$", installer, re.M).group(1)
    assert f"EnvironmentFile={envFile}" in unit
    installDir = re.search(r"^INSTALL_DIR=(\S+)$", installer, re.M).group(1)
    assert f"ExecStart=/usr/bin/python3 {installDir}/kitten.pyz" in unit
    assert "inotify-tools" in installer and "git" in installer


def test_the_installer_reports_the_pounce_paths_kitten_really_watches():
    installer = (INTEG / "kitten" / "install-kitten.sh").read_text()
    for node in NODE_FOLDERS:
        for watch in defaultWatches(node, windows=False):
            folder = watch.target  # refs are watched through their folder
            assert folder in installer or folder.startswith("/opt/purrbrews/.git"), f"{node}: {folder}"
    assert "/opt/purrbrews/.git/refs/heads" in installer and "/srv/dumps" in installer
    assert "/srv/data/paperless/consume" in installer


def test_rollout_names_every_pounce_path_and_says_which_are_not_listable_by_default():
    for node in NODE_FOLDERS:
        for watch in defaultWatches(node, windows=False):
            assert watch.path.split("/.git")[0] in ROLLOUT, watch.path
    assert ROASTERY[0].path in ROLLOUT
    assert "NOT LISTABLE" in ROLLOUT or "not listable" in ROLLOUT
    assert "only the top level" in ROLLOUT  # cellar's /srv/dumps


# -- ROLLOUT.md walked against the repo -------------------------------------------------------------------------


def test_rollout_mentions_every_credential_in_secrets_env():
    tokens = [f"PERCH_KITTEN_TOKEN_{n.upper()}" for n in NODES]
    missing = [k for k in secretsEnvEntries() if k not in ROLLOUT and k not in tokens]
    assert missing == []
    assert "PERCH_KITTEN_TOKEN_SIEVE" in ROLLOUT and all(f"_{n.upper()}" in ROLLOUT for n in NODES)


def test_rollout_only_names_files_that_exist(fleetRepo):
    """A path in the document is in integration/, in the pinned fleet repo (a file a patch edits), or is the one
    new file apply.sh puts into the fleet repo's _lib."""
    rx = r"`((?:integration/)?(?:kitten|roastery|groom|patches|stacks)/[A-Za-z0-9_./@-]+)`"
    for rel in sorted(set(re.findall(rx, ROLLOUT))):
        if "<" in rel or "*" in rel:
            continue
        inIntegration = (ROOT / rel).exists() or (INTEG / rel).exists()
        inFleet = (fleetRepo / rel).exists()
        newInFleet = rel == "stacks/_lib/groom-record.py"
        nodeLocal = rel.endswith(".env.local")  # made on the node by setup-secrets, never in a repo
        assert inIntegration or inFleet or newInFleet or nodeLocal, f"ROLLOUT.md names {rel}, which exists nowhere"
    for rel in ("scripts/buildKitten.ps1", "integration/apply.sh", "integration/groom/README.md", "secrets.env"):
        assert (ROOT / rel).is_file()
    for needle in ("install-kitten.sh", "install-kitten.ps1", "run-kitten.ps1", "apply.sh", "buildKitten.ps1"):
        assert needle in ROLLOUT


def test_rollout_names_every_patch_and_every_drop_in():
    for patch in (INTEG / "patches").glob("*.patch"):
        assert patch.name in ROLLOUT, f"{patch.name} is not in ROLLOUT.md's table"
    for unit in (INTEG / "groom" / "units").iterdir():
        stem = unit.name.removesuffix(".service.d")
        assert stem in ROLLOUT, f"ROLLOUT.md never installs the {unit.name} drop-in"


def test_rollout_carries_the_owners_two_decisions_and_the_retirement_rules():
    flat = " ".join(ROLLOUT.split())
    assert "Morning digest only" in flat and "never an immediate push" in flat
    assert "whiskers never hisses about itself" in flat
    assert "cannot see leak or smoke sensors" in flat and "Home Assistant's own alerts" in flat
    assert "Keep every `type: custom` alert" in flat and "sieve's healthchecks.io heartbeat" in flat
    assert "`backup.sh`'s failure notify" in flat and "`check-freshness.sh`'s notify" in flat
    assert "restore roastery's sleep" in flat.lower() or "put roastery's sleep setting back" in flat.lower()


def test_rollout_drills_cover_every_milestone_and_what_the_entries_left():
    needles = [
        "ListServers", "ServerState", "network_cloudflare-tunnel", "host_id",
        "**M0:**", "**M1:", "**M2:", "**M3:", "**M4:**", "**M5:**", "**M6:**",
        "leak-sensor", "Acknowledge", "/trail/stream", "text/event-stream", "non-admin", "kitten user", "tailnet",
        "60 seconds", "5 seconds", "no false hiss", "01:25", "ntfy.sh",
    ]  # fmt: skip
    for needle in needles:
        assert needle in ROLLOUT, f"the drill list lacks {needle!r}"


def test_the_steps_run_in_the_order_the_document_promises():
    order = [ROLLOUT.index(f"\n## {s}. ") for s in "ABCDEFGHIJK"]
    assert order == sorted(order)
    assert ROLLOUT.rindex("## K. ") > ROLLOUT.index("## J. ")  # the sleep setting goes back last
