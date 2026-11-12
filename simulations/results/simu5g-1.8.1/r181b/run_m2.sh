#!/bin/bash
# M2-R181b M2 family on unmodified Simu5G 1.8.1, isolated mode, checkpointed (plan §4.2).
#   run_m2.sh <new results root (absolute)>
# Order: m2s0 -> A7-v -> m2s1 -> C10-v -> m2s4 -> R2b-v -> dependency gate -> m2s5 -> m2s6. M2-S3 is not rerun
# (24/24 PASS in M2-R181; it reads M2-S1 runs only). After each runner: manifest of its runs (manifest.sh), then the
# new rows, then deletion of the raw data no later step reads (logged in deleted-raw.txt). A disk guard stops a running
# step below 300 MB free (recorded as STOPPED-DISK, never as a result). Stops at the first unexpected outcome.
set -o pipefail
ROOT=$1
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../../.." && pwd)
S=$NASCTIME/simulations
export SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.1}
export NASCTIME_RESULTS_ROOT=$ROOT
[ "$(cat "$SIMU5G_ROOT/Version")" = 1.8.1 ] || { echo "ERROR: $SIMU5G_ROOT is not Simu5G 1.8.1" >&2; exit 1; }
[ -e "$ROOT" ] && { echo "ERROR: $ROOT exists" >&2; exit 1; }
mkdir -p "$ROOT"
M=$ROOT/m2; LOG=$ROOT/steps.txt; DEL=$ROOT/deleted-raw.txt
free_mb() { df -B1M --output=avail / | tail -1 | tr -d ' '; }
note() { echo "$(date -u +%FT%TZ) $* free=$(free_mb)M" | tee -a "$LOG"; }
step() {  # $1 label, rest: command (disk-guarded)
  local l=$1; shift; local t0; t0=$(date +%s)
  "$@" > "$ROOT/console-$l.txt" 2>&1 & local p=$!
  while kill -0 $p 2>/dev/null; do
    if [ "$(free_mb)" -lt 300 ]; then pkill -P $p; pkill -f "result-dir=$ROOT"; kill $p; wait $p; note "$l STOPPED-DISK"; return 99; fi
    sleep 5; done
  wait $p; local rc=$?; note "$l rc=$rc $(( $(date +%s) - t0 ))s"; return $rc
}
drop() { rm -rf "$1"; note "deleted $(echo "$1" | sed "s|$ROOT/||")"; echo "$(date -u +%FT%TZ) deleted after manifest: ${1#$ROOT/}" >> "$DEL"; }
row() {  # $1 mode, $2 runs dir, $3 record dir
  python3 "$S/m2/check/check_v181b_m2.py" "$1" "$2" > "$3/$1-v-check.txt" 2>&1
  python3 "$S/m2/check/check_v181b_m2.py" "$1" "$2" --mutate > "$3/$1-v-mutation-check.txt" 2>&1
  note "row $1-v: $(grep '^OVERALL' "$3/$1-v-check.txt"); mutation: $(grep '^OVERALL' "$3/$1-v-mutation-check.txt")"
}
stop() { note "STOP: $*"; exit 1; }

# 1. M2-S0 (expected: runner completes, A7 FAIL only)
step m2s0 "$S/m2/m2s0.sh"; rc=$?
[ -f "$M/M2-S0/raw-outputs.sha256" ] || stop "M2-S0 raw-outputs.sha256 not written (rc $rc)"
"$HERE/manifest.sh" "$M/M2-S0/runs" "$M/M2-S0/r181b" >> "$LOG"
row a7 "$M/M2-S0/runs" "$M/M2-S0"
drop "$M/M2-S0/runs"
# 2. M2-S1 (expected: C10 FAIL only); runs kept for m2s4
step m2s1 "$S/m2/m2s1.sh"; rc=$?
[ -f "$M/M2-S1/raw-outputs.sha256" ] || stop "M2-S1 raw-outputs.sha256 not written (rc $rc)"
"$HERE/manifest.sh" "$M/M2-S1/runs" "$M/M2-S1/r181b" >> "$LOG"
row c10 "$M/M2-S1/runs" "$M/M2-S1"
# 3. M2-S4 (expected: R2b FAIL only; m2s4.sh stops before writing raw-outputs.sha256)
step m2s4 "$S/m2/m2s4.sh"; rc=$?
[ -f "$M/M2-S4/check.txt" ] || stop "M2-S4 check.txt missing (rc $rc)"
"$HERE/manifest.sh" "$M/M2-S4/runs" "$M/M2-S4/r181b" >> "$LOG"
row r2b "$M/M2-S4/runs" "$M/M2-S4"
drop "$M/M2-S1/runs"
if [ -f "$M/M2-S4/raw-outputs.sha256" ]; then note "m2s4.sh wrote raw-outputs.sha256 itself (check passed); no gate needed"
else "$HERE/m2s4_dependency_gate.sh" "$M/M2-S4" >> "$LOG" || stop "dependency gate M2-S4 -> M2-S5 closed"; fi
for d in "$M/M2-S4/runs"/*/; do c=$(basename "$d"); case "$c" in M2S4|M2S4-frag|M2S4-load|M2S4-load-harq16) ;; *) drop "$d" ;; esac; done
# 4. M2-S5 (no row-level prediction on 1.8.1; any FAIL is reported, not reclassified)
step m2s5 "$S/m2/m2s5.sh"; rc=$?
"$HERE/manifest.sh" "$M/M2-S5/runs" "$M/M2-S5/r181b" >> "$LOG"
drop "$M/M2-S4/runs"
[ -f "$M/M2-S5/raw-outputs.sha256" ] || stop "M2-S5 raw-outputs.sha256 not written (rc $rc): M2-S6 not run"
# 5. M2-S6
step m2s6 "$S/m2/m2s6.sh"; rc=$?
[ -d "$M/M2-S6/runs" ] && "$HERE/manifest.sh" "$M/M2-S6/runs" "$M/M2-S6/r181b" >> "$LOG"
drop "$M/M2-S5/runs"; drop "$M/M2-S6/runs"
note "DONE m2 (m2s6 rc $rc)"
