#!/bin/bash
# M2-R181: m2s5 then m2s6 on 1.8.1 (continuation of run_m2_family_lowdisk.sh after attempt 2 ran out of disk).
set -o pipefail
ROOT=$1
HERE=$(cd "$(dirname "$0")" && pwd); NASCTIME=$(cd "$HERE/../../.." && pwd); S=$NASCTIME/simulations
export SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.1} NASCTIME_RESULTS_ROOT=$ROOT
mkdir -p "$ROOT"; LOG=$ROOT/m2r181-runs.txt
step() { local l=$1; shift; local t0; t0=$(date +%s); "$@" > "$ROOT/console-$l.txt" 2>&1; local rc=$?
  echo "$(date -u +%FT%TZ) $l rc=$rc $(( $(date +%s) - t0 ))s free=$(df -B1G --output=avail / | tail -1 | tr -d ' ')G" | tee -a "$LOG"; }
drop() { local d=$ROOT/m2/$1; [ -d "$d/runs" ] || return 0
  (cd "$d" && find runs -type f | LC_ALL=C sort | xargs sha256sum > raw-outputs-all-runs.sha256)
  rm -rf "$d/runs"; echo "$(date -u +%FT%TZ) deleted $1/runs after hashing (raw-outputs-all-runs.sha256)" | tee -a "$LOG" "$ROOT/deleted-raw.txt"; }
step m2s5 "$S/m2/m2s5.sh"; drop M2-S4
step m2s6 "$S/m2/m2s6.sh"; drop M2-S5
echo "DONE g0m2" | tee -a "$LOG"
