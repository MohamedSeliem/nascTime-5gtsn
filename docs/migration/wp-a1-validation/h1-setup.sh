#!/usr/bin/env bash
# WP-A1 validation, phase H-1 (runbook revision 3): host set-up WITH network and WITHOUT evidence.
# usage (from the clone made by the executor, see runbook 4.1): bash "$Z/h1-setup.sh" <approved docs commit D>
# Requires: Z exported; $Z/nasctime-src (a full clone); $Z/refs/ holding gate-a.txt, release-ref.txt,
# equivalence-ref.txt and dr13-ref.txt, written by the executor from the approval records; $Z/vars.env from the template.
set -u -o pipefail
stop() { echo "STOP [h1-setup]: $*" >&2; exit 1; }
[ $# -eq 1 ] || stop "usage: h1-setup.sh <docs commit D>"
D=$1
[ -n "${Z:-}" ] && [ -d "$Z/nasctime-src/.git" ] || stop "Z / \$Z/nasctime-src missing"
S="$Z/nasctime-src"
[[ $D =~ ^[0-9a-f]{40}$ ]] || stop "D must be a full commit id"
[ "$(grep -c '^docs_commit=' "$Z/refs/gate-a.txt" 2>/dev/null)" = 1 ] && [ "$(grep '^docs_commit=' "$Z/refs/gate-a.txt" | cut -d= -f2)" = "$D" ] \
  || stop "D is not the docs commit approved in refs/gate-a.txt"
[ "$(git -C "$S" rev-parse --verify "$D^{commit}")" = "$D" ] || stop "D not in the clone"
[ ! -e "$Z/scripts" ] || stop "$Z/scripts exists"
mkdir "$Z/scripts" && git -C "$S" archive "$D" docs/migration/wp-a1-validation | tar -x -C "$Z/scripts" --strip-components=3 \
  || stop "scripts export"
. "$Z/scripts/common.sh"
STAGE=h1-setup
load_vars
[ ! -e "$W" ] || stop "W exists"
git -C "$S" rev-parse --verify "7bb0e3a^{commit}" >/dev/null && git -C "$S" rev-parse --verify "fbee202^{commit}" >/dev/null \
  && git -C "$S" rev-parse --verify "39a6434^{commit}" >/dev/null && git -C "$S" rev-parse --verify "d920125^{commit}" >/dev/null \
  && git -C "$S" rev-parse --verify "7e5c169^{commit}" >/dev/null || stop "the clone lacks the history the pin tests need"
git -C "$S" worktree add --detach "$W" "$C" || stop "worktree"
[ "$(git -C "$W" rev-parse HEAD)" = "$C" ] || stop "worktree HEAD"
[ ! -e "$SIMU5G_ROOT" ] || stop "SIMU5G_ROOT exists"
git clone --branch v1.8.1 https://github.com/Unipisa/Simu5G.git "$SIMU5G_ROOT" || stop "Simu5G clone"
[ "$(git -C "$SIMU5G_ROOT" rev-parse HEAD)" = "$SIMU5G_HEAD" ] || stop "Simu5G HEAD is not $SIMU5G_HEAD"
for f in release-ref.txt equivalence-ref.txt dr13-ref.txt; do [ -s "$Z/refs/$f" ] || stop "refs/$f missing"; done
echo "H-1 complete: scripts from $D, worktree at $C, Simu5G at $SIMU5G_HEAD"
