#!/bin/bash
# M2-R181c M2-S4 -> M2-S5 -> M2-S6 on unmodified Simu5G 1.8.1 (plan §3). Isolated mode, JOBS=1, checkpointed.
#   run_r181c.sh <new results root (absolute)>
set -o pipefail
ROOT=$1
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../../.." && pwd)
S=$NASCTIME/simulations; B=$HERE/../r181b
export SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.1}
export NASCTIME_RESULTS_ROOT=$ROOT JOBS=1
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}; INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
[ "$(cat "$SIMU5G_ROOT/Version")" = 1.8.1 ] || { echo "ERROR: $SIMU5G_ROOT is not Simu5G 1.8.1" >&2; exit 1; }
[ -e "$ROOT" ] && { echo "ERROR: $ROOT exists" >&2; exit 1; }
mkdir -p "$ROOT"
M=$ROOT/m2; LOG=$ROOT/steps.txt; DEL=$ROOT/deleted-raw.txt
free_mb() { df -B1M --output=avail / | tail -1 | tr -d ' '; }
note() { echo "$(date -u +%FT%TZ) $* free=$(free_mb)M" | tee -a "$LOG"; }
step() {
  local l=$1; shift; local t0; t0=$(date +%s)
  "$@" > "$ROOT/console-$l.txt" 2>&1 & local p=$!
  while kill -0 $p 2>/dev/null; do
    if [ "$(free_mb)" -lt 300 ]; then pkill -P $p; pkill -f "result-dir=$ROOT"; kill $p; wait $p; note "$l STOPPED-DISK"; return 99; fi
    sleep 5; done
  wait $p; local rc=$?; note "$l rc=$rc $(( $(date +%s) - t0 ))s"; return $rc
}
drop() { rm -rf "$1"; note "deleted ${1#$ROOT/}"; echo "$(date -u +%FT%TZ) deleted after manifest: ${1#$ROOT/}" >> "$DEL"; }
stop() { note "STOP: $*"; exit 1; }
PY=python3
# 1-2
step m2s0 "$S/m2/m2s0.sh"; [ -f "$M/M2-S0/raw-outputs.sha256" ] || stop "M2-S0 hash file missing"
"$B/manifest.sh" "$M/M2-S0/runs" "$M/M2-S0/r181c" >> "$LOG"; drop "$M/M2-S0/runs"
step m2s1 "$S/m2/m2s1.sh"; [ -f "$M/M2-S1/raw-outputs.sha256" ] || stop "M2-S1 hash file missing"
"$B/manifest.sh" "$M/M2-S1/runs" "$M/M2-S1/r181c" >> "$LOG"
# 3
step m2s4 "$S/m2/m2s4.sh"; [ -f "$M/M2-S4/check.txt" ] || stop "M2-S4 check.txt missing"
"$B/manifest.sh" "$M/M2-S4/runs" "$M/M2-S4/r181c" >> "$LOG"
$PY "$S/m2/check/check_v181b_m2.py" r2b "$M/M2-S4/runs" > "$M/M2-S4/r2b-v-check.txt" 2>&1
$PY "$S/m2/check/check_v181b_m2.py" r2b "$M/M2-S4/runs" --mutate > "$M/M2-S4/r2b-v-mutation-check.txt" 2>&1
note "R2b-v: $(grep '^OVERALL' "$M/M2-S4/r2b-v-check.txt"); mutation $(grep '^OVERALL' "$M/M2-S4/r2b-v-mutation-check.txt")"
drop "$M/M2-S1/runs"
[ -f "$M/M2-S4/raw-outputs.sha256" ] || "$B/m2s4_dependency_gate.sh" "$M/M2-S4" >> "$LOG" || stop "M2-S4 gate closed"
for d in "$M/M2-S4/runs"/*/; do c=$(basename "$d"); case "$c" in M2S4|M2S4-frag|M2S4-load|M2S4-load-harq16) ;; *) drop "$d" ;; esac; done
# 4
step m2s5 "$S/m2/m2s5.sh"; [ -f "$M/M2-S5/check.txt" ] || stop "M2-S5 check.txt missing"
"$B/manifest.sh" "$M/M2-S5/runs" "$M/M2-S5/r181c" >> "$LOG"
# 5 the M2-R181c configs (m2s5.sh run() command, ini m2s5r181c.ini)
R5C=$M/M2-S5-r181c/runs; mkdir -p "$R5C"
source "$OMNETPP_ROOT/setenv" -f >/dev/null
for c in M2S4R-offset M2S5R-nc-tseSlot-load M2S5R-nc-noFcsNw-offset; do
  (cd "$S/m2" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f m2s5r181c.ini -c "$c" --repeat=10 -r 0 --result-dir="$R5C/$c" \
     --cmdenv-express-mode=true > "$R5C/run-$c.log" 2>&1); note "$c rc=$?"
done
"$B/manifest.sh" "$R5C" "$M/M2-S5-r181c/r181c" >> "$LOG"
# 6
C=$S/m2/check/check_v181c_m2s5.py
$PY "$C" full "$M/M2-S5" "$M/M2-S4/runs" "$M/M2-S4/raw-outputs.sha256" > "$M/M2-S5/check-v181c.txt" 2>&1; note "C8-v check: $(grep '^OVERALL' "$M/M2-S5/check-v181c.txt")"
$PY "$C" c8demo "$M/M2-S5/runs" "$M/M2-S4/runs" > "$M/M2-S5/c8demo-v181c.txt" 2>&1; note "c8demo: $(grep '^OVERALL' "$M/M2-S5/c8demo-v181c.txt")"
$PY "$C" controls "$M/M2-S5/runs" "$M/M2-S4/runs" "$R5C" > "$M/M2-S5/controls-v181c.txt" 2>&1; note "controls: $(grep '^OVERALL' "$M/M2-S5/controls-v181c.txt")"
rm -rf "$S/m2/check/__pycache__"
# 7
"$HERE/m2s5_dependency_gate.sh" "$M/M2-S5" >> "$LOG" || stop "M2-S5 gate closed"
# 8
drop "$M/M2-S4/runs"; drop "$R5C"
for d in "$M/M2-S5/runs"/*/; do c=$(basename "$d"); case "$c" in M2S5|M2S5U-hold) ;; *) drop "$d" ;; esac; done
# 9
step m2s6 "$S/m2/m2s6.sh"; rc=$?
[ -d "$M/M2-S6/runs" ] && "$B/manifest.sh" "$M/M2-S6/runs" "$M/M2-S6/r181c" >> "$LOG"
drop "$M/M2-S5/runs"; drop "$M/M2-S6/runs"
note "DONE (m2s6 rc $rc)"
