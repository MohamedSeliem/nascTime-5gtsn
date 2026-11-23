# WP-A1 validation procedure tests (runbook revision 4, section 14): shared fixtures. Sourced by the test scripts.
# TEST ONLY: every key, statement, record and archive made here is a dummy. No genuine evidence is used or needed.
# Environment: NASCTIME_SRC  a full clone of the repository (holds the reviewed commit C)
#              SIMU5G_SRC    a Simu5G clone holding tag v1.8.1 (7477d266)
set -u -o pipefail
T_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)
S_DIR=$(cd "$T_DIR/.." && pwd)
C_REV=f3f68be696777e42b0717f949625855ddb475435
: "${NASCTIME_SRC:?set NASCTIME_SRC to a full clone of the repository}"
: "${SIMU5G_SRC:?set SIMU5G_SRC to a Simu5G clone with tag v1.8.1}"
PASSED=0; FAILED=0
ok()   { echo "PASS  $1"; PASSED=$((PASSED + 1)); }
bad()  { echo "FAIL  $1"; FAILED=$((FAILED + 1)); }
check() { if eval "$2"; then ok "$1"; else bad "$1  [$2]"; fi; }
summary() { echo "$1: $PASSED PASS, $FAILED FAIL"; [ "$FAILED" -eq 0 ]; }

# new_z: a fresh work dir with the scripts, a worktree-equivalent checkout at C, Simu5G at its pin and a vars.env whose
# X and REL lie outside Z (they need not exist). Prints the path.
new_z() {
  local base; base=$(mktemp -d "${TMPDIR:-/tmp}/wpa1-test.XXXXXX")
  local z="$base/z"; mkdir -p "$z"
  cp -r "$S_DIR" "$z/scripts"
  git clone -q --no-checkout "$NASCTIME_SRC" "$z/wpa1-validate" && git -C "$z/wpa1-validate" -c advice.detachedHead=false checkout -q "$C_REV" \
    || { echo "fixture: checkout of C failed" >&2; return 1; }
  git clone -q --branch v1.8.1 "$SIMU5G_SRC" "$z/simu5g-1.8.1" 2>/dev/null || { echo "fixture: Simu5G clone failed" >&2; return 1; }
  cat > "$z/vars.env" <<EOF
W="\$Z/wpa1-validate"
C=$C_REV
R=/mnt/nasctime-results
X=$base/x
E="\$Z/evidence-wpa1"
REL=$base/rel
export SIMU5G_ROOT="\$Z/simu5g-1.8.1"
CHK="\$W/simulations/m2/check"
PY="python3 -I -B"
EOF
  echo "$z"
}

# test_key <dir>: a throwaway ed25519 key (TEST ONLY) and an allowed_signers file for principal wpa1-maintainer
test_key() {
  mkdir -p "$1"; ssh-keygen -q -t ed25519 -N '' -C "TEST ONLY wpa1 approval key" -f "$1/test-key" >/dev/null
  printf 'wpa1-maintainer %s\n' "$(cut -d' ' -f1,2 "$1/test-key.pub")" > "$1/allowed_signers"
}
# sign <key> <statement>: a detached signature <statement>.sig in the wpa1-approval namespace
sign() { rm -f "$2.sig"; ssh-keygen -q -Y sign -f "$1" -n wpa1-approval "$2" >/dev/null 2>&1; }

# gate_a_statement <file> <docs commit> <release sums sha256> <archive names...>
gate_a_statement() {
  local f=$1 d=$2 rs=$3; shift 3
  { echo "format=wpa1-approval/1"; echo "gate=A"; echo "decision=APPROVED"; echo "executor=TEST ONLY executor"
    echo "reviewed_commit=$C_REV"; echo "docs_commit=$d"
    echo "vn1_sha256=b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b"
    echo "vn2_sha256=5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3"
    echo "vv1_sha256=fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d"
    echo "registry_sha256=2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae"
    echo "release_sums_sha256=$rs"; for a in "$@"; do echo "archive=$a"; done
    echo "rules=approved"; echo "access=authorised"; echo "date=2026-11-23"; } > "$f"
}
# subject_statement <file> <gate> <docs commit> <record file in records/> <records dir> [image digest]
subject_statement() {
  { echo "format=wpa1-approval/1"; echo "gate=$2"; echo "decision=APPROVED"; echo "docs_commit=$3"
    echo "subject=TEST ONLY record"; echo "subject_file=$4"; echo "subject_sha256=$(sha256sum "$5/$4" | cut -d' ' -f1)"
    [ -n "${6:-}" ] && echo "image_digest=$6"; echo "date=2026-11-23"; } > "$1"
}
