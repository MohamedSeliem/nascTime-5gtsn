#!/bin/bash
# M2-R181 R-4, continuation of g0_legacy_lowdisk.sh after its stop at m1/s0 (2026-11-11 16:54Z).
# Same runners, same legacy mode, same worktree; the order is changed only between the independent M1 and M2
# families: m2s6 (needs the 6.6 GB of worktree M2-S5 runs) runs first, then those runs are dropped, then M1.
# A disk guard stops a runner if free space falls below 300 MB (recorded as such, never as a result).
set -o pipefail
WT=$1; LOG=$2; MAIN=$3
cd "$WT/simulations"; unset NASCTIME_RESULTS_ROOT SIMU5G_ROOT
step() { local r=$1; local t0; t0=$(date +%s); ./$r > "$LOG.$(basename $r).out" 2>&1 & local p=$!
  while kill -0 $p 2>/dev/null; do
    if [ "$(df -B1M --output=avail / | tail -1 | tr -d ' ')" -lt 300 ]; then
      pkill -P $p; pkill -f "result-dir=$WT"; kill $p; echo "$(date -u +%FT%TZ) $r STOPPED-DISK" >> "$LOG"; wait $p; return; fi
    sleep 5; done
  wait $p; local rc=$?
  echo "$(date -u +%FT%TZ) $r rc=$rc $(( $(date +%s) - t0 ))s free=$(df -B1G --output=avail / | tail -1 | tr -d ' ')G" >> "$LOG"; }
drop() { rm -rf "$WT/simulations/$1"; echo "$(date -u +%FT%TZ) deleted $1" >> "$LOG"; }
step m2/m2s6.sh; drop m2/results/M2-S5/runs; drop m2/results/M2-S6/runs
for r in m1/s0_vanilla_reference.sh m1/s1_owned_scenario.sh m1/s2_passthrough_tts.sh m1/s2_phase_offset.sh m1/s3_qfi_drb.sh; do step $r; done
drop m1/results/S3/load; drop m1/results/S3/seeds
step m1/o_s3_1_investigation.sh; step m1/s4_gptp_transport.sh; step m1/o_tail_investigation.sh; step m1/s5_metadata.sh
for m in s5 o1 otail; do
  python3 "$MAIN/simulations/m1/check/check_v181.py" $m "$WT/simulations/m1/results" > "$LOG.v181-$m-on-1.8.0.txt" 2>&1
  echo "$(date -u +%FT%TZ) v181 $m on 1.8.0 rc=$?" >> "$LOG"
done
drop m1/results/O-S3-1/runs
drop m1/results/O-tail/runs
step m1/upstream-issues/run_issues.sh; drop m1/results/upstream-issues/runs
echo DONE >> "$LOG"
