#!/bin/bash
# M2-R181c continuation after addendum 1: re-evaluate C8-v on the same M2-S5 runs, gate, then steps 8-9 of run_r181c.sh.
set -o pipefail
ROOT=$1
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../../.." && pwd)
S=$NASCTIME/simulations; B=$HERE/../r181b
export SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.1} NASCTIME_RESULTS_ROOT=$ROOT JOBS=1
M=$ROOT/m2; LOG=$ROOT/steps.txt; DEL=$ROOT/deleted-raw.txt
free_mb() { df -B1M --output=avail / | tail -1 | tr -d ' '; }
note() { echo "$(date -u +%FT%TZ) $* free=$(free_mb)M" | tee -a "$LOG"; }
step() { local l=$1; shift; local t0; t0=$(date +%s); "$@" > "$ROOT/console-$l.txt" 2>&1 & local p=$!
  while kill -0 $p 2>/dev/null; do if [ "$(free_mb)" -lt 300 ]; then pkill -P $p; pkill -f "result-dir=$ROOT"; kill $p; wait $p; note "$l STOPPED-DISK"; return 99; fi; sleep 5; done
  wait $p; local rc=$?; note "$l rc=$rc $(( $(date +%s) - t0 ))s"; return $rc; }
drop() { rm -rf "$1"; note "deleted ${1#$ROOT/}"; echo "$(date -u +%FT%TZ) deleted after manifest: ${1#$ROOT/}" >> "$DEL"; }
stop() { note "STOP: $*"; exit 1; }
note "continuation after addendum 1 at $(git -C "$NASCTIME" rev-parse --short HEAD)"
python3 "$S/m2/check/check_v181c_m2s5.py" full "$M/M2-S5" "$M/M2-S4/runs" "$M/M2-S4/raw-outputs.sha256" > "$M/M2-S5/check-v181c.txt" 2>&1
note "C8-v check: $(grep '^OVERALL' "$M/M2-S5/check-v181c.txt")"; rm -rf "$S/m2/check/__pycache__"
"$HERE/m2s5_dependency_gate.sh" "$M/M2-S5" >> "$LOG" || stop "M2-S5 gate closed"
drop "$M/M2-S4/runs"; drop "$M/M2-S5-r181c/runs"
for d in "$M/M2-S5/runs"/*/; do c=$(basename "$d"); case "$c" in M2S5|M2S5U-hold) ;; *) drop "$d" ;; esac; done
step m2s6 "$S/m2/m2s6.sh"; rc=$?
[ -d "$M/M2-S6/runs" ] && "$B/manifest.sh" "$M/M2-S6/runs" "$M/M2-S6/r181c" >> "$LOG"
drop "$M/M2-S5/runs"; drop "$M/M2-S6/runs"
note "DONE (m2s6 rc $rc)"
