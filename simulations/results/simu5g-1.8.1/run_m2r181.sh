#!/bin/bash
# M2-R181: the validation runs on Simu5G 1.8.1 (plan §5 step 6), isolated mode only.
#   run_m2r181.sh <results root (new, absolute)> [g0m1|g0m2|s72|all]
# g0m1: the 10 M1 G0 runners (gate order), then the version-neutral rows (check_v181.py); g0m2: the 6 M2 G0 runners
# s72: S7.2a CP1 (m2s72.sh all, f0check, t0check) and CP2 revision 2 (m2s72.sh r2)
# Requires the unmodified Simu5G 1.8.1 build at /root/stack/simu5g-1.8.1 (or SIMU5G_ROOT).
set -o pipefail
ROOT=$1; WHAT=${2:-all}
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../.." && pwd)
export SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.1}
export NASCTIME_RESULTS_ROOT=$ROOT
[ "$(cat "$SIMU5G_ROOT/Version")" = 1.8.1 ] || { echo "ERROR: $SIMU5G_ROOT is not Simu5G 1.8.1" >&2; exit 1; }
mkdir -p "$ROOT"
LOG=$ROOT/m2r181-runs.txt
step() {  # $1 label, rest: command
  local l=$1; shift; local t0; t0=$(date +%s)
  "$@" > "$ROOT/console-$l.txt" 2>&1; local rc=$?
  echo "$(date -u +%FT%TZ) $l rc=$rc $(( $(date +%s) - t0 ))s free=$(df -B1G --output=avail / | tail -1 | tr -d ' ')G" | tee -a "$LOG"
  return 0
}
S=$NASCTIME/simulations
if [ "$WHAT" = g0m1 ] || [ "$WHAT" = all ]; then
  for r in m1/s0_vanilla_reference.sh m1/s1_owned_scenario.sh m1/s2_passthrough_tts.sh m1/s2_phase_offset.sh m1/s3_qfi_drb.sh \
           m1/o_s3_1_investigation.sh m1/s4_gptp_transport.sh m1/o_tail_investigation.sh m1/s5_metadata.sh m1/upstream-issues/run_issues.sh; do
    step "$(basename "$r" .sh)" "$S/$r"
  done
  for m in s5 o1 otail; do
    step "v181-$m" python3 "$S/m1/check/check_v181.py" "$m" "$ROOT/m1"
    cp "$ROOT/console-v181-$m.txt" "$ROOT/m1/v181-$m-check.txt"
    step "v181-$m-mutate" python3 "$S/m1/check/check_v181.py" "$m" "$ROOT/m1" --mutate
    cp "$ROOT/console-v181-$m-mutate.txt" "$ROOT/m1/v181-$m-mutation-check.txt"
  done
fi
if [ "$WHAT" = g0m2 ] || [ "$WHAT" = all ]; then
  for r in m2/m2s1.sh m2/m2s3.sh m2/m2s0.sh m2/m2s4.sh m2/m2s5.sh m2/m2s6.sh; do step "$(basename "$r" .sh)" "$S/$r"; done
fi
if [ "$WHAT" = s72 ] || [ "$WHAT" = all ]; then
  step m2s72-cp1 "$S/m2/m2s72.sh" all
  step m2s72-f0check "$S/m2/m2s72.sh" f0check
  step m2s72-t0check "$S/m2/m2s72.sh" t0check
  step m2s72-cp2r2 "$S/m2/m2s72.sh" r2
fi
echo "DONE $WHAT" | tee -a "$LOG"
