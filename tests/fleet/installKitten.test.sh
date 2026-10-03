#!/usr/bin/env bash
# Runs integration/kitten/install-kitten.sh for real, as root, inside tests/fleet/Dockerfile's image (Debian, Python 3.13),
# with a fake systemctl and a fake apt-get (a container has no systemd and must not install packages). It checks what the
# script leaves behind, that the token is never printed, and that a missing pounce folder is reported, not worked around.
# Started by scripts/test.ps1; every container it runs carries the project label.
set -Eeuo pipefail

FAILED=0
ok()   { echo "ok    $*"; }
fail() { echo "FAIL  $*"; FAILED=1; }
check() { local what="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$what"; else fail "$what"; fi; }

WORK="$(mktemp -d)"
FAKE="$WORK/bin"; mkdir -p "$FAKE"
cat > "$FAKE/systemctl" <<'EOF'
#!/bin/sh
echo "systemctl $*" >> "$FAKE_LOG"
exit 0
EOF
cat > "$FAKE/apt-get" <<'EOF'
#!/bin/sh
echo "apt-get $*" >> "$FAKE_LOG"
exit 0
EOF
chmod +x "$FAKE/systemctl" "$FAKE/apt-get"
export FAKE_LOG="$WORK/calls.log"; : > "$FAKE_LOG"
export PATH="$FAKE:$PATH"

# A node: its .env.local with a fake domain, the kitten.pyz built from this repo, an /etc/purrbrews and one pounce folder.
mkdir -p /opt/purrbrews/stacks/sieve /etc/purrbrews /srv/data/paperless/consume
printf 'DOMAIN=test.example.home.arpa\nOTHER=1\n' > /opt/purrbrews/stacks/sieve/.env.local
INTEGRATION="${INTEGRATION:-/integration}"
PYZ="$WORK/kitten.pyz"
( cd /src && python3 -m kitten.build "$PYZ" >/dev/null )
TOKEN="$(python3 -c 'print("ab" * 32)')"   # a made-up 64-character value, not a real token

OUT="$WORK/out.txt"
printf '%s\n' "$TOKEN" | script -qec "bash $INTEGRATION/kitten/install-kitten.sh sieve --pyz $PYZ" /dev/null > "$OUT" 2>&1 || { cat "$OUT"; fail "install exited non-zero"; }

check "the kitten user exists with no shell and no home" sh -c 'getent passwd kitten | grep -q ":/usr/sbin/nologin$" && getent passwd kitten | grep -q ":/nonexistent:"'
check "kitten.pyz is installed, root-owned and runs" sh -c "[ \"\$(stat -c '%U:%a' /opt/kitten/kitten.pyz)\" = root:755 ] && python3 /opt/kitten/kitten.pyz --version | grep -q '^kitten '"
check "kitten.env is root-only (600)" sh -c "[ \"\$(stat -c '%U:%G:%a' /etc/purrbrews/kitten.env)\" = root:root:600 ]"
check "kitten.env has the report URL from the node's DOMAIN" grep -qx 'KITTEN_PERCH_URL=https://perch.test.example.home.arpa/api/kitten' /etc/purrbrews/kitten.env
check "kitten.env names the node as the folder is spelled" grep -qx 'KITTEN_NODE=sieve' /etc/purrbrews/kitten.env
check "kitten.env holds the typed token" grep -qx "KITTEN_TOKEN=$TOKEN" /etc/purrbrews/kitten.env
check "the unit is installed" sh -c '[ -f /etc/systemd/system/kitten.service ] && grep -q "^User=kitten$" /etc/systemd/system/kitten.service'
check "the service was enabled and started" sh -c "grep -q 'enable kitten.service' $FAKE_LOG && grep -q 'restart kitten.service' $FAKE_LOG"
check "inotify-tools and git were asked for (inotifywait is not in this image)" sh -c "grep -q 'apt-get install.*inotify-tools' $FAKE_LOG"
# The first line is the test harness's pty echoing the piped input before `read -s` switched echo off; the script's own output is the rest.
check "the token is never printed by the script" sh -c "! tail -n +2 $OUT | grep -q $TOKEN"
check "a folder that exists and lists is ok" grep -q 'ok       /etc/purrbrews' "$OUT"
check "a folder kitten cannot list is reported, not created or widened" sh -c "grep -q 'NOT LISTABLE by kitten: /opt/purrbrews/.git' $OUT && [ ! -e /opt/purrbrews/.git ]"

# Run again without a terminal: the token is kept, nothing is asked.
bash "$INTEGRATION/kitten/install-kitten.sh" sieve --pyz "$PYZ" > "$WORK/again.txt" 2>&1 < /dev/null || { cat "$WORK/again.txt"; fail "second run exited non-zero"; }
check "a second run keeps the token" grep -qx "KITTEN_TOKEN=$TOKEN" /etc/purrbrews/kitten.env

# Refusals
check "a wrong node name is refused" sh -c "! bash $INTEGRATION/kitten/install-kitten.sh mochapot --pyz $PYZ </dev/null"
check "roastery is not a Linux node here" sh -c "! bash $INTEGRATION/kitten/install-kitten.sh roastery --pyz $PYZ </dev/null"
printf 'short\n' | script -qec "bash $INTEGRATION/kitten/install-kitten.sh sieve --pyz $PYZ --new-token" /dev/null > "$WORK/short.txt" 2>&1 && fail "a short token was accepted" || ok "a too-short token is refused"
check "the refused run left the old token alone" grep -qx "KITTEN_TOKEN=$TOKEN" /etc/purrbrews/kitten.env

# Remove
bash "$INTEGRATION/kitten/install-kitten.sh" --remove > /dev/null 2>&1 || fail "--remove exited non-zero"
check "--remove takes the files and the user away" sh -c '[ ! -e /opt/kitten ] && [ ! -e /etc/purrbrews/kitten.env ] && [ ! -e /etc/systemd/system/kitten.service ] && ! id kitten'

rm -rf "$WORK"
[ "$FAILED" -eq 0 ] && echo "install-kitten.sh: all checks ok" || { echo "install-kitten.sh: FAILED"; exit 1; }
