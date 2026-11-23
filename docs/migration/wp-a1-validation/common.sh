# WP-A1 independent validation (runbook revision 3): sourced by every stage script; never executed directly.
# Fail closed: every check that cannot be completed stops the stage with exit 1.
set -u -o pipefail
STAGE=${STAGE:-unknown}
stop() { echo "STOP [$STAGE]: $*" >&2; exit 1; }
is_hex64() { [[ $1 =~ ^[0-9a-f]{64}$ ]]; }
inside() { case "$1/" in "$2"/*) return 0 ;; esac; return 1; }   # inside <path> <dir>: path is dir or below it

REVIEWED_C=f3f68be696777e42b0717f949625855ddb475435
SIMU5G_HEAD=7477d2663644bbf78604267cba4fc113b4871ede
RESULTS_PREFIX=/mnt/nasctime-results

load_vars() {
  [ -n "${Z:-}" ] || stop "Z is not set"
  [ -f "$Z/vars.env" ] || stop "$Z/vars.env missing"
  ! grep -q '[<>]' "$Z/vars.env" || stop "vars.env still contains a placeholder (< or >)"
  # shellcheck disable=SC1091
  . "$Z/vars.env" || stop "vars.env does not load"
  local v
  for v in W C R X E REL SIMU5G_ROOT CHK PY; do [ -n "${!v:-}" ] || stop "vars.env: $v is empty"; done
  for v in Z W R X E REL SIMU5G_ROOT; do case "${!v}" in /*) ;; *) stop "vars.env: $v is not absolute";; esac; done
  [ "$C" = "$REVIEWED_C" ] || stop "C is not the reviewed commit"
  [ "$R" = "$RESULTS_PREFIX" ] || stop "R must be $RESULTS_PREFIX"
  [ "$CHK" = "$W/simulations/m2/check" ] || stop "CHK must be \$W/simulations/m2/check"
  [ "$PY" = "python3 -I -B" ] || stop "PY must be 'python3 -I -B'"
  [ "$W" = "$Z/wpa1-validate" ] || stop "W must be \$Z/wpa1-validate"
  [ "$E" = "$Z/evidence-wpa1" ] || stop "E must be \$Z/evidence-wpa1"
  # writable work tree and evidence locations never overlap: X and REL are outside Z (Z is mounted read-write)
  inside "$X" "$Z" && stop "X is inside Z"; inside "$Z" "$X" && stop "Z is inside X"
  inside "$REL" "$Z" && stop "REL is inside Z"; inside "$Z" "$REL" && stop "Z is inside REL"
  inside "$X" "$REL" && stop "X is inside REL"; inside "$REL" "$X" && stop "REL is inside X"
  inside "$X" "$R" && stop "X is inside R"; inside "$Z" "$R" && stop "Z is inside R"
  export SIMU5G_ROOT
  test -z "${S5N_ADAPTER_VALIDATED+x}" || stop "S5N_ADAPTER_VALIDATED is set"
}

# ---- gate-A approvals (runbook revision 4, section 3) ----------------------------------------------------------
# An approval is a statement file signed by the maintainer with an SSH key (ssh-keygen -Y sign -n wpa1-approval) and
# verified here against $Z/approvals/allowed_signers (principal wpa1-maintainer; the public key is obtained by the
# executor out of band). A statement that is unsigned, signed by another key, altered, malformed or not APPROVED is
# refused; for A-4 / A-5 the approved record itself must be present in $Z/records with the stated sha256. A populated
# text file is never enough. The development agent never holds the signing key.
APPROVALS=${APPROVALS:-$Z/approvals}
EXPECT_SHA=(vn1:b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b
            vn2:5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3
            vv1:fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d
            registry:2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae)
stmt_ok() {   # stmt_ok <statement name> <gate>: returns 0 or prints the reason and returns 1 (no exit: testable)
  local f="$APPROVALS/$1" g=$2 k n
  [ -f "$APPROVALS/allowed_signers" ] || { echo "no allowed_signers"; return 1; }
  [ -f "$f" ] && [ -f "$f.sig" ] || { echo "$1 or its signature missing"; return 1; }
  ssh-keygen -Y verify -f "$APPROVALS/allowed_signers" -I wpa1-maintainer -n wpa1-approval -s "$f.sig" < "$f" >/dev/null 2>&1 \
    || { echo "$1: signature does not verify for wpa1-maintainer / wpa1-approval"; return 1; }
  [ "$(head -n 1 "$f")" = "format=wpa1-approval/1" ] || { echo "$1: format line"; return 1; }
  ! grep -qv '^[a-z0-9_][a-z0-9_]*=[^=]' "$f" || { echo "$1: a line is not key=value"; return 1; }
  for k in $(cut -d= -f1 "$f" | sort | uniq -d); do [ "$k" = archive ] || { echo "$1: duplicate key $k"; return 1; }; done
  [ "$(grep -c "^gate=$g\$" "$f")" = 1 ] || { echo "$1: not a gate $g statement"; return 1; }
  [ "$(grep -c '^decision=APPROVED$' "$f")" = 1 ] || { echo "$1: decision is not APPROVED"; return 1; }
  for k in docs_commit date; do n=$(grep -c "^$k=" "$f"); [ "$n" = 1 ] || { echo "$1: $k missing"; return 1; }; done
  if [ "$g" != A ]; then
    local sf ss
    sf=$(grep '^subject_file=' "$f" | cut -d= -f2-); ss=$(grep '^subject_sha256=' "$f" | cut -d= -f2-)
    case "$sf" in ""|*/*|.*) echo "$1: subject_file is not a plain file name"; return 1;; esac
    is_hex64 "$ss" || { echo "$1: subject_sha256"; return 1; }
    [ -f "$Z/records/$sf" ] || { echo "$1: the approved record $sf is not in $Z/records"; return 1; }
    [ "$(sha256sum "$Z/records/$sf" | cut -d' ' -f1)" = "$ss" ] || { echo "$1: $sf differs from the approved record"; return 1; }
  fi
  return 0
}
need_approval() { local why; why=$(stmt_ok "$1" "$2") || stop "approval $1 (gate $2) refused: $why"; }
aval() {      # aval <statement name> <key>: the single value of key in a statement already accepted by need_approval
  local n; n=$(grep -c "^$2=" "$APPROVALS/$1") || true
  [ "$n" = 1 ] || stop "$1: expected exactly one '$2=' line, found $n"
  grep "^$2=" "$APPROVALS/$1" | cut -d= -f2-
}
gate_a() {    # gate A-1 / A-2 / A-3 / A-6, signed; consistent with the fixed identities
  need_approval gate-a.txt A
  [ "$(aval gate-a.txt reviewed_commit)" = "$REVIEWED_C" ] || stop "gate A: reviewed_commit is not $REVIEWED_C"
  local e k v
  for e in "${EXPECT_SHA[@]}"; do k=${e%%:*}; v=${e#*:}
    [ "$(aval gate-a.txt "${k}_sha256")" = "$v" ] || stop "gate A: ${k}_sha256 differs from the reviewed value"; done
  [ "$(aval gate-a.txt rules)" = approved ] && [ "$(aval gate-a.txt access)" = authorised ] || stop "gate A: rules / access not approved"
  [ -n "$(aval gate-a.txt executor)" ] || stop "gate A: no executor"
}
gate_a45() {  # gates A-4 (DR-13 record) and A-5 (G0-RO record), signed, records present, same procedure commit
  local d; d=$(aval gate-a.txt docs_commit)
  need_approval a4-dr13.txt A-4; need_approval a5-g0ro.txt A-5
  [ "$(aval a4-dr13.txt docs_commit)" = "$d" ] && [ "$(aval a5-g0ro.txt docs_commit)" = "$d" ] || stop "A-4 / A-5 approve another procedure commit"
  is_hex64 "$(aval a5-g0ro.txt image_digest)" || stop "A-5: image_digest"
}

gate_b_go() { grep -qx "GATE B: GO (B-1 ... B-6 met)" "$E/gate/gate-b.txt" 2>/dev/null || stop "gate B is not GO"; }
done_mark() { echo "$1 complete" > "$E/gate/$1.done"; }
need_done() { [ -f "$E/gate/$1.done" ] || stop "$1 has not completed"; }

# no_evidence_visible: used where the genuine evidence must not be reachable at all (P-0)
no_evidence_visible() {
  [ ! -e "$R" ] || stop "$R is visible in this container; P-0 must run without evidence"
  [ ! -e "$X" ] || stop "$X is visible in this container; P-0 must run without evidence"
  [ ! -e "$REL" ] || stop "$REL is visible in this container; P-0 must run without evidence"
}

# ro_path <path>: mounted read-only and not writable; never creates anything
ro_path() {
  [ -d "$1" ] || stop "$1 is not a directory"
  findmnt -no OPTIONS --target "$1" | tr ',' '\n' | grep -qx ro || stop "$1 is not on a read-only mount"
  [ ! -w "$1" ] || stop "$1 is writable"
}
