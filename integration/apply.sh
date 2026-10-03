#!/usr/bin/env bash
#
# apply.sh: put persianPerch's integration/ into a clone of purrbrews-containers.
#
#   integration/apply.sh /path/to/purrbrews-containers          apply (new files, then the patches)
#   integration/apply.sh --check /path/to/purrbrews-containers  only say whether everything would apply
#
# Run it on a fresh branch of YOUR clone, then read `git diff` and `git status`, commit, and open
# the pull request in your own process. This script never commits, never pushes and never talks
# to a node. It needs bash and git. It refuses a clone with uncommitted changes, so the diff you
# review afterwards is only persianPerch's.
#
# What it does:
#   1. copies integration/stacks/ into <clone>/stacks/ (the new cellar/persian-perch/ app folder);
#   2. copies integration/groom/groom-record.py to <clone>/stacks/_lib/groom-record.py (executable);
#   3. applies integration/patches/*.patch, one per existing file it edits.
# The patches were made against the commit named in integration/PIN. If the fleet's main has moved
# and a patch no longer applies, it stops before changing anything and says which one.
set -Eeuo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECK=0
if [[ "${1:-}" == --check ]]; then CHECK=1; shift; fi
CLONE="${1:?usage: apply.sh [--check] /path/to/purrbrews-containers}"

die() { echo "apply.sh: $*" >&2; exit 1; }

[[ -d "$CLONE/.git" || -f "$CLONE/.git" ]] || die "$CLONE is not a git clone"
[[ -d "$CLONE/stacks/cellar" ]] || die "$CLONE has no stacks/cellar: is it purrbrews-containers?"
[[ -z "$(git -C "$CLONE" status --porcelain)" ]] || die "$CLONE has uncommitted changes; start from a clean branch"

PIN="$(tr -d '[:space:]' < "$HERE/PIN")"
HEAD_NOW="$(git -C "$CLONE" rev-parse HEAD)"
if [[ "$HEAD_NOW" != "$PIN" ]]; then
  echo "note: the patches were made against ${PIN:0:7}; this clone is at ${HEAD_NOW:0:7}."
  echo "      If a patch fails, the file changed upstream: tell the agent, or edit by hand from the patch."
fi

shopt -s nullglob
patches=("$HERE"/patches/*.patch)
[[ ${#patches[@]} -gt 0 ]] || die "no patches found beside this script"

# Everything is checked before anything is written.
for patch in "${patches[@]}"; do
  git -C "$CLONE" apply --check "$patch" || die "$(basename "$patch") does not apply to this clone"
done
for existing in $(cd "$HERE/stacks" && find . -type f | sed 's#^\./##'); do
  [[ ! -e "$CLONE/stacks/$existing" ]] || die "stacks/$existing already exists in the clone"
done
[[ ! -e "$CLONE/stacks/_lib/groom-record.py" ]] || die "stacks/_lib/groom-record.py already exists in the clone"

if [[ $CHECK -eq 1 ]]; then
  echo "ok: everything applies to $CLONE"
  exit 0
fi

cp -R "$HERE/stacks/." "$CLONE/stacks/"
install -m 755 "$HERE/groom/groom-record.py" "$CLONE/stacks/_lib/groom-record.py"
for patch in "${patches[@]}"; do
  git -C "$CLONE" apply "$patch"
  echo "applied $(basename "$patch")"
done
echo
echo "Done. Nothing is committed. Next: git -C \"$CLONE\" status, read git diff, then"
echo "      python3 -m unittest discover -s tests   (from the clone)"
