#!/bin/bash
# M2-R181: the M2 G0 family on 1.8.1 under the 11 GB disk allowance (plan §6). Same runners and dependencies as
# run_m2r181.sh g0m2; raw run directories are hashed (raw-outputs-all.sha256) and deleted as soon as no later
# runner reads them: M2-S0/runs after m2s0, M2-S1/runs after m2s4, M2-S4/runs after m2s5. Deletions are logged.
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
# m2s0 first: in a fresh root, m2s1's check reads M2-S0/raw-outputs.sha256 of the same root (attempt 1 failed on it)
step m2s0 "$S/m2/m2s0.sh"; drop M2-S0
step m2s1 "$S/m2/m2s1.sh"; step m2s3 "$S/m2/m2s3.sh"; step m2s4 "$S/m2/m2s4.sh"; drop M2-S1
step m2s5 "$S/m2/m2s5.sh"; drop M2-S4
step m2s6 "$S/m2/m2s6.sh"; drop M2-S5
echo "DONE g0m2" | tee -a "$LOG"
