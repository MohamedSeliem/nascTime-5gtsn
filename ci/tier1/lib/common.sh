#!/usr/bin/env bash
# Sourced by every ci/tier1/steps/*.sh. Loads the reviewed pins, refuses test overrides (C5), defines the controlled
# directories and helpers. Production never honours mocking or test-hook variables.
set -euo pipefail
T1_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
T1_LIB=$T1_DIR/lib
REPO=$(cd "$T1_DIR/../.." && pwd)
# C5: any test/mocking/override variable in the production environment is a hard failure.
for v in $(compgen -e); do
  case "$v" in
    TIER1_TEST_*|E2B3_TEST_*|A2V1_TEST_*|A2V1_STUB_*|A2V1_RESULTS_ROOT|A2V1_COMMIT)
      echo "::error::test/override variable '$v' is set in the production environment; refusing to run"; exit 3 ;;
  esac
done
set -a
# shellcheck source=../pins.env
. "$T1_DIR/pins.env"
set +a
: "${RUNNER_TEMP:?RUNNER_TEMP is not set}"
CI=$RUNNER_TEMP/tier1
EV=$CI/evidence; DL=$CI/dl; WS=$CI/ws; VENV=$CI/venv; UNPUB=$CI/unpublished; PROBES=$CI/probes; PY=$T1_DIR/py
EXEC=$CI/exec            # the single, initially empty directory every opp_env session starts in (C2)
E2B=$CI                  # scratch location used by the ported helpers (tail.tmp)
OE=$VENV/bin/opp_env
export T1_DIR T1_LIB REPO CI EV DL WS VENV UNPUB PROBES EXEC E2B OE PY
export PATH="/nix/var/nix/profiles/default/bin:$PATH"
[[ -f "$CI/job-start" ]] && JOB_START=$(cat "$CI/job-start") && export JOB_START

# exec_check <checkpoint>: relative-RUNPATH hazards around every opp_env session (C2). Every session starts in the
# controlled directory $EXEC, which must stay empty (it is what a relative RUNPATH entry such as "." and the Nix shell's
# default output directory resolve against); the absent absolute RUNPATH entries must stay absent.
exec_check() {
  local cp=$1 bad="" d
  [[ -d "$EXEC" ]] || bad="$bad controlled directory missing;"
  [[ -z "$(find "$EXEC" -mindepth 1 -maxdepth 1 -printf x 2>/dev/null)" ]] || bad="$bad controlled directory not empty;"
  for d in "$EXEC/outputs" "$REPO/outputs" "$WS/omnetpp-6.5.0/tools/linux.x86_64/lib"; do
    [[ ! -e "$d" ]] || bad="$bad ${d#"$CI"/} exists;"
  done
  if [[ -n "$bad" ]]; then
    echo "$(date -u +%FT%TZ) [$cp] FAIL$bad" >> "$EV/exec-checks.txt"
    echo "::error::execution-safety check failed at $cp:$bad"; return 1
  fi
  echo "$(date -u +%FT%TZ) [$cp] ok" >> "$EV/exec-checks.txt"
}

# oe_session <label> <opp_env arguments...>: guarded opp_env session started in the controlled directory.
oe_session() {
  local label=$1 rc=0; shift
  exec_check "before $label" || return 1
  (cd "$EXEC" && "$T1_LIB/guarded.sh" "$label" "$OE" "$@") || rc=$?
  exec_check "after $label" || return 1
  return "$rc"
}

# screened_cat <file>: print a file to the public log only if it passes the sensitive-content screen.
screened_cat() {
  if /usr/bin/python3 -I "$T1_LIB/screen.py" "$1" > /dev/null; then cat "$1"; else echo "$(basename "$1") withheld from the console by screening"; fi
}
