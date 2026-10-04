#!/usr/bin/env bash
#
# install-kitten.sh: install persianPerch's kitten on one Linux node (sieve, percolator, cellar, mochaPot, grinder).
#
#   sudo ./install-kitten.sh <node> [--pyz /path/to/kitten.pyz] [--pounce 'path|level|why;...'] [--new-token]
#   sudo ./install-kitten.sh --remove
#
# <node> is the node's folder in stacks/, spelled exactly like it (mochaPot, not mochapot): perch checks that the
# name matches the token.
#
# Delivery follows the fleet's rule (pull, never copy): the node clones the public persianPerch repo at a pinned ref,
# builds the zipapp there AS ITSELF (the ops user, not root; standard library only), then runs this script as root:
#
#   git clone https://github.com/purrMonster/persianPerch.git ~/persianPerch      # once
#   git -C ~/persianPerch fetch --tags && git -C ~/persianPerch checkout <tag or full commit>
#   cd ~/persianPerch && python3 -m kitten.build /tmp/kitten.pyz
#   cd integration/kitten && sudo ./install-kitten.sh <node> --pyz /tmp/kitten.pyz
#
# Updating kitten later is the same four lines (the script keeps the token).
#
# What it does, and nothing else:
#   1. installs inotify-tools and git if they are missing (pounce needs them; the packages are the only system change);
#   2. makes a system user `kitten` with no shell and no home, if missing;
#   3. puts kitten.pyz in /opt/kitten (owned by root, so kitten cannot change its own code);
#   4. writes /etc/purrbrews/kitten.env (root, 0600): the report URL (from DOMAIN in the node's .env.local), the node
#      name, and the token you type (hidden). Nothing is read from a file or an argument, so the token never lands in
#      shell history or a process list;
#   5. installs and starts the systemd unit kitten.service (kitten.service, beside this script);
#   6. says, for each folder pounce will watch, whether the kitten user can list it. A folder it cannot list is
#      REPORTED, not worked around: widening permissions for a watcher is a decision for the owner (05 plan A10).
#
# It changes nothing else: no firewall, no existing file, no other service. Safe to run again: it keeps the token you
# already have unless you pass --new-token. kitten reads the node and writes nothing.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NODES="sieve percolator cellar mochaPot grinder"
ENV_FILE=/etc/purrbrews/kitten.env
UNIT=/etc/systemd/system/kitten.service
INSTALL_DIR=/opt/kitten

die()  { echo "install-kitten: $*" >&2; exit 1; }
note() { echo "  $*"; }

[[ $EUID -eq 0 ]] || die "run with sudo."

if [[ "${1:-}" == --remove ]]; then
  systemctl disable --now kitten.service 2>/dev/null || true
  rm -f "$UNIT" "$ENV_FILE"
  rm -rf "$INSTALL_DIR"
  systemctl daemon-reload
  userdel kitten 2>/dev/null || true
  echo "kitten removed (inotify-tools and git stay installed)."
  exit 0
fi

NODE="${1:-}"; shift || true
PYZ="/tmp/kitten.pyz"; POUNCE=""; NEW_TOKEN=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --pyz)       PYZ="${2:?--pyz needs a path}"; shift 2 ;;
    --pounce)    POUNCE="${2:?--pounce needs a value}"; shift 2 ;;
    --new-token) NEW_TOKEN=1; shift ;;
    *) die "unknown option $1" ;;
  esac
done
[[ " $NODES " == *" $NODE "* ]] || die "the first argument is the node's folder name: one of $NODES"
[[ -f "$PYZ" ]] || die "kitten.pyz not found at $PYZ: build it first (python3 -m kitten.build /tmp/kitten.pyz, in the persianPerch checkout, as yourself)"
# It is installed as root, so it must be a file only you (or root) could have written: /tmp is shared.
owner="$(stat -c %U "$PYZ")"
[[ "$owner" == root || "$owner" == "${SUDO_USER:-root}" ]] || die "$PYZ belongs to $owner, not to you: build it yourself and try again"
[[ -f "$HERE/kitten.service" ]] || die "kitten.service must sit beside this script"
command -v python3 >/dev/null || die "python3 is missing"
python3 -c 'import sys; sys.exit(0 if sys.version_info >= (3, 13) else 1)' || die "kitten needs Python 3.13 or newer (Debian 13 has it)"

# The report URL needs the domain, which lives only on the node.
ENV_LOCAL="/opt/purrbrews/stacks/$NODE/.env.local"
[[ -r "$ENV_LOCAL" ]] || die "$ENV_LOCAL is not readable: has ./setup-secrets.sh run on this node?"
DOMAIN="$(sed -n 's/^DOMAIN=//p' "$ENV_LOCAL" | head -n1 | tr -d "\"'[:space:]")"
[[ -n "$DOMAIN" && "$DOMAIN" != REPLACE_ME* ]] || die "DOMAIN is not set in $ENV_LOCAL"

echo "1. packages"
missing=()
command -v inotifywait >/dev/null || missing+=(inotify-tools)
command -v git >/dev/null || missing+=(git)
if [[ ${#missing[@]} -gt 0 ]]; then
  apt-get install -y --no-install-recommends "${missing[@]}" >/dev/null
  note "installed ${missing[*]}"
else
  note "inotify-tools and git are there"
fi

echo "2. the kitten user"
if id kitten >/dev/null 2>&1; then
  note "kitten exists"
else
  useradd --system --user-group --no-create-home --home-dir /nonexistent --shell /usr/sbin/nologin kitten
  note "created kitten (system user, no shell, no home)"
fi

echo "3. the program"
install -d -m 755 -o root -g root "$INSTALL_DIR"
install -m 755 -o root -g root "$PYZ" "$INSTALL_DIR/kitten.pyz"
note "$(python3 "$INSTALL_DIR/kitten.pyz" --version) in $INSTALL_DIR"

echo "4. the settings ($ENV_FILE)"
TOKEN=""
if [[ -f "$ENV_FILE" && $NEW_TOKEN -eq 0 ]]; then
  TOKEN="$(sed -n 's/^KITTEN_TOKEN=//p' "$ENV_FILE" | head -n1)"
fi
if [[ -z "$TOKEN" ]]; then
  [[ -t 0 ]] || die "the token is typed at a prompt; run this from a terminal"
  read -r -s -p "  Token for $NODE (PERCH_KITTEN_TOKEN_${NODE^^} on cellar; typing is hidden): " TOKEN
  echo
  TOKEN="$(printf '%s' "$TOKEN" | tr -d '[:space:]')"
fi
[[ ${#TOKEN} -ge 32 ]] || die "that token is too short to be one of perch's (64 hex characters)"
install -d -m 755 -o root -g root /etc/purrbrews
umask 077
{
  echo "# kitten's settings on $NODE. Root-only: systemd reads this file, the kitten user cannot."
  echo "KITTEN_PERCH_URL=https://perch.${DOMAIN}/api/kitten"
  echo "KITTEN_NODE=$NODE"
  echo "KITTEN_TOKEN=$TOKEN"
  [[ -z "$POUNCE" ]] || echo "KITTEN_POUNCE_PATHS=$POUNCE"
} > "$ENV_FILE.new"
chown root:root "$ENV_FILE.new"; chmod 600 "$ENV_FILE.new"; mv "$ENV_FILE.new" "$ENV_FILE"
unset TOKEN
note "written (mode 600). pounce will say 'settings changed: kitten.env' once: that is the sense working."

echo "5. the service"
install -m 644 -o root -g root "$HERE/kitten.service" "$UNIT"
systemctl daemon-reload
systemctl enable kitten.service >/dev/null 2>&1
systemctl restart kitten.service
sleep 3
if systemctl is-active --quiet kitten.service; then note "kitten.service is active"; else
  note "kitten.service is NOT active: sudo journalctl -u kitten -n 30"; fi

echo "6. what the kitten user can list (pounce's folders)"
if [[ -n "$POUNCE" ]]; then
  IFS=';' read -r -a entries <<< "$POUNCE"; paths=(); for e in "${entries[@]}"; do paths+=("${e%%|*}"); done
else
  paths=(/etc/purrbrews /opt/purrbrews/.git/refs/heads /opt/purrbrews/.git)  # git refs are watched through their folders
  [[ "$NODE" != cellar ]] || paths+=(/srv/dumps)
  [[ "$NODE" != percolator ]] || paths+=(/srv/data/paperless/consume)
fi
for p in "${paths[@]}"; do
  if runuser -u kitten -- test -r "$p" -a \( ! -d "$p" -o -x "$p" \) 2>/dev/null; then
    note "ok       $p"
  else
    note "NOT LISTABLE by kitten: $p   (kitten says so in its log, once; not worked around)"
  fi
done
case "$NODE" in
  cellar) note "note: /srv/dumps lists, but each <node> folder inside it is mode 700 for the dumps user, and cellar's own"
          note "      folder is 700 root: inotifywait skips those without a word, so pounce sees folders appear, not the dump"
          note "      files inside them. Not worked around (A10); the groom records say whether the dumps happened." ;;
esac
echo
echo "Check: sudo journalctl -u kitten -n 20 --no-pager ; then perch's overview should show $NODE's kitten as reporting."
