"""catTree against the pinned fleet repo (C15) and a synthetic repo for the deny-list (S1)."""

import re

import pytest
from conftest import git, makeRepo

from perch.catTree import DENY_PATTERNS, CatTree, CatTreeError, isDenied, trackedFiles


def nodeConfApps(fleetRepo):
    """Every node.conf's APPS, parsed independently of catTree."""
    found = {}
    for conf in sorted((fleetRepo / "stacks").glob("*/node.conf")):
        match = re.search(r"^APPS=\(([^)]*)\)", conf.read_text(encoding="utf-8"), re.M)
        found[conf.parent.name] = match.group(1).split() if match else []
    return found


def test_every_node_and_every_app_appears(fleetRepo):
    fleet = CatTree(fleetRepo).fleet()
    expected = nodeConfApps(fleetRepo)
    assert set(expected) == {n.name for n in fleet.nodes}
    for node in fleet.nodes:
        assert [a.name for a in node.apps] == expected[node.name], node.name
    assert fleet.appCount == sum(len(v) for v in expected.values())


def test_nodes_in_fleet_env_order_with_ips(fleetRepo):
    fleet = CatTree(fleetRepo).fleet()
    assert [n.name for n in fleet.nodes] == ["sieve", "percolator", "cellar", "mochaPot", "grinder", "roastery"]
    assert fleet.node("cellar").ip == "192.168.0.12"
    assert fleet.node("roastery").ip == "192.168.0.15"
    assert fleet.node("cellar").role.startswith("backups")


def test_app_details_from_the_repo(fleetRepo):
    fleet = CatTree(fleetRepo).fleet()
    authelia = fleet.node("percolator").app("authelia")
    assert authelia.id == "app:percolator/authelia"
    assert "Single sign-on" in authelia.summary
    assert any(img.startswith("authelia/authelia:") for img in authelia.images)
    assert any(line.startswith("sqlite") for line in authelia.backup)
    assert authelia.hasSecretsConf and "secrets.conf" in authelia.files
    restic = fleet.node("cellar").app("restic")
    assert restic is not None and not restic.inApps  # a folder node.conf doesn't list
    assert "runbook.md" in fleet.docs and "docs/MAP.md" in fleet.docs


def test_pinned_repo_lists_no_denied_file(fleetRepo):
    fleet = CatTree(fleetRepo).fleet()
    listed = list(fleet.files)
    for node in fleet.nodes:
        listed += node.files
        for app in node.apps + node.extras:
            listed += app.files
    assert listed and not [p for p in listed if isDenied(p)]


@pytest.mark.parametrize(
    ("path", "denied"),
    [
        ("stacks/sieve/ntfy/secrets.env.local", True),
        ("SECRETS.ENV.LOCAL", True),
        ("stacks/cellar/.env.local", True),
        ("stacks/x/local.env.local", True),
        ("keys/server.key", True),
        ("home/barista/.ssh/authorized_keys", True),
        ("stacks/cellar/local.env.example", False),
        ("stacks/roastery/backup-target/authorized_keys.example", False),
        ("stacks/sieve/ntfy/secrets.conf", False),
        ("docs/keyboard.md", False),
    ],
)
def test_deny_list(path, denied):
    assert isDenied(path) is denied


@pytest.fixture
def leakyRepo(tmp_path):
    """S1: a repo that (wrongly) tracks every kind of secret file, plus a sneaky symlink."""
    secret = "fake-secret-in-a-tracked-file"
    repo = makeRepo(
        tmp_path / "leaky",
        {
            "stacks/fleet.env": "SIEVE_LAN_IP=192.168.0.10\n",
            "stacks/sieve/node.conf": "# sieve: the network node.\nAPPS=(ntfy)\n",
            "stacks/sieve/ntfy/README.md": "# ntfy\n\nAlerts.\n",
            "stacks/sieve/ntfy/secrets.conf": "NTFY_TOKEN prompt\n",
            "stacks/sieve/ntfy/secrets.env.local": f"NTFY_TOKEN={secret}\n",
            "stacks/sieve/ntfy/.env.local": f"X={secret}\n",
            "stacks/sieve/ntfy/tls.key": secret,
            "stacks/sieve/authorized_keys": secret,
            "outside.txt": secret,
        },
        symlinks={"stacks/sieve/ntfy/docker-compose.yml": "secrets.env.local"},
    )
    return repo, secret


def test_S1_tracked_secret_files_are_never_listed(leakyRepo):
    repo, _ = leakyRepo
    tracked = git(repo, "ls-files").split()
    assert "stacks/sieve/ntfy/secrets.env.local" in tracked  # the fixture really tracks it
    files = trackedFiles(repo)
    assert not [f for f in files if isDenied(f)]
    fleet = CatTree(repo).fleet()
    ntfy = fleet.node("sieve").app("ntfy")
    for pattern in DENY_PATTERNS:
        assert not any(isDenied(f) for f in ntfy.files + fleet.node("sieve").files), pattern
    assert "secrets.env.local" not in ntfy.files and "tls.key" not in ntfy.files


def test_S1_secret_files_are_never_read(leakyRepo):
    repo, secret = leakyRepo
    tree = CatTree(repo)
    fleet = tree.fleet()
    for path in (
        "stacks/sieve/ntfy/secrets.env.local",
        "stacks/sieve/ntfy/.env.local",
        "stacks/sieve/ntfy/tls.key",
        "stacks/sieve/authorized_keys",
        "stacks/sieve/ntfy/docker-compose.yml",  # a symlink to the secret
        "../outside.txt",
        "not/tracked.md",
    ):
        with pytest.raises(CatTreeError):
            tree.read(path, fleet)
    assert ntfyImagesEmpty(fleet)
    assert "Alerts." in tree.read("stacks/sieve/ntfy/README.md", fleet)


def ntfyImagesEmpty(fleet):
    """The symlinked compose file was not followed, so no 'image' came from the secret."""
    return fleet.node("sieve").app("ntfy").images == []


def test_rebuilds_when_head_moves(tmp_path):
    repo = makeRepo(tmp_path / "r", {"stacks/sieve/node.conf": "APPS=(a)\n", "stacks/sieve/a/README.md": "x"})
    tree = CatTree(repo)
    assert [a.name for a in tree.fleet().node("sieve").apps] == ["a"]
    (repo / "stacks/sieve/node.conf").write_text("APPS=(a b)\n")
    (repo / "stacks/sieve/b").mkdir()
    (repo / "stacks/sieve/b/README.md").write_text("y")
    git(repo, "add", "-A")
    git(repo, "-c", "user.name=t", "-c", "user.email=t@example.home.arpa", "commit", "-q", "-m", "b")
    assert [a.name for a in tree.fleet().node("sieve").apps] == ["a", "b"]


def test_missing_repo_is_an_error(tmp_path):
    with pytest.raises(CatTreeError):
        CatTree(tmp_path / "nothing").fleet()
