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

# ref <file> <key>: the value of key=<64 hex> in a reference file written from an approved record (exactly one line)
ref() {
  [ -f "$1" ] || stop "reference file $1 missing"
  local n val
  n=$(grep -c "^$2=" "$1") || true
  [ "$n" = 1 ] || stop "$1: expected exactly one '$2=' line, found $n"
  val=$(grep "^$2=" "$1" | cut -d= -f2-)
  printf '%s' "$val"
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
