#!/usr/bin/env bash
# Runs the one ROLLOUT.md block that edits a secrets file (A3: perch's ntfy user), taken from the document itself, against a copy of
# the pinned fleet repo's real _lib helpers and sieve folder, with a fake sudo and a fake docker (the hash is made up). It checks that
# the three lists get perch appended without losing what was there, that the file stays mode 600, that the hash survives the fleet's
# quoting, that nothing secret is printed, and that a second run refuses. Runs as root in tests/fleet's image; started by scripts/test.ps1.
set -Eeuo pipefail

FAILED=0
ok()   { echo "ok    $*"; }
fail() { echo "FAIL  $*"; FAILED=1; }
check() { local what="$1"; shift; if "$@" >/dev/null 2>&1; then ok "$what"; else fail "$what"; fi; }

WORK="$(mktemp -d)"
mkdir -p "$WORK/bin" /opt/purrbrews
cp -r /scratch/stacks /opt/purrbrews/stacks
cat > "$WORK/bin/sudo" <<'EOF'
#!/bin/sh
exec "$@"
EOF
# a docker that answers `run ... ntfy user hash` the way the real one does: reads the password twice, prints a bcrypt-shaped hash
cat > "$WORK/bin/docker" <<'EOF'
#!/bin/sh
cat >/dev/null
printf 'Hash: $2a$10$%s\n' "$(printf 'a%.0s' $(seq 1 53))"
EOF
chmod +x "$WORK/bin/sudo" "$WORK/bin/docker"
export PATH="$WORK/bin:$PATH"

F=/opt/purrbrews/stacks/sieve/ntfy/secrets.env.local
mkdir -p "$(dirname "$F")"
printf "NTFY_EXTRA_USERS='barista2:\$2a\$10\$xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx:user'\nNTFY_EXTRA_ACCESS=barista2:other:ro\nNTFY_EXTRA_TOKENS=\n" > "$F"
chmod 600 "$F"

# the block, from the marker comment to the line that closes the subshell
awk '/^# --- perch.s ntfy user/ {on=1} on {print} on && /^\)$/ {exit}' /src/integration/ROLLOUT.md > "$WORK/snippet.sh"
[ "$(wc -l < "$WORK/snippet.sh")" -gt 8 ] && ok "the block was found in ROLLOUT.md" || fail "the block was not found in ROLLOUT.md"

OUT="$WORK/out.txt"
bash "$WORK/snippet.sh" > "$OUT" 2>&1 || { cat "$OUT"; fail "the block exited non-zero"; }
. /opt/purrbrews/stacks/_lib/common.sh
USERS="$(env_get "$F" NTFY_EXTRA_USERS)"; ACCESS="$(env_get "$F" NTFY_EXTRA_ACCESS)"; TOKENS="$(env_get "$F" NTFY_EXTRA_TOKENS)"
case "$USERS"  in barista2:*,perch:\$2a\$10\$*:user) ok "perch appended to the users, the existing one kept" ;; *) fail "users: $USERS" ;; esac
[ "$ACCESS" = "barista2:other:ro,perch:purrbrews-alerts:wo" ] && ok "perch is write-only on purrbrews-alerts, the existing rule kept" || fail "access: $ACCESS"
echo "$TOKENS" | grep -qE '^perch:tk_[0-9a-f]{29}:perch$' && ok "the token is tk_ and 29 characters, labelled perch (32 in all, as ntfy wants)" || fail "tokens: shape"
[ "$(stat -c %a "$F")" = 600 ] && ok "the file is still mode 600" || fail "mode of $F"
HASHPART="${USERS##*perch:}"; HASHPART="${HASHPART%:user}"
[ "${#HASHPART}" = 60 ] && ok "the bcrypt hash came through the fleet's quoting whole (60 characters)" || fail "hash length ${#HASHPART}"
TOKEN="$(echo "$TOKENS" | sed -n 's/^perch:\(tk_[0-9a-f]*\):perch$/\1/p')"
! grep -q "$TOKEN" "$OUT" && ok "the token is not printed" || fail "the token was printed"
! grep -q 'a\{53\}' "$OUT" && ok "the hash is not printed" || fail "the hash was printed"

if bash "$WORK/snippet.sh" > "$WORK/second.txt" 2>&1; then fail "a second run was accepted"; else grep -q "already in the ntfy lists" "$WORK/second.txt" && ok "a second run refuses and changes nothing" || fail "second run: wrong refusal"; fi
[ "$(env_get "$F" NTFY_EXTRA_TOKENS)" = "$TOKENS" ] && ok "the lists are unchanged by the refused run" || fail "lists changed"

rm -rf "$WORK" /opt/purrbrews
[ "$FAILED" -eq 0 ] && echo "rollout snippets: all checks ok" || { echo "rollout snippets: FAILED"; exit 1; }
