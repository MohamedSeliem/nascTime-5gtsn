#!/bin/bash
# M2-R181 R-4 under the disk allowance: the 16 G0 runners in LEGACY mode on Simu5G 1.8.0, in a worktree of the
# runner commit (never in the main tree), in the M2-S7.1 G0 order. Raw run directories of the worktree (scratch
# duplicates of committed hashes) are deleted as soon as no later runner reads them. The version-neutral rows are
# run on the 1.8.0 M1 outputs (controls, plan §3.2(b)) before their raw outputs are deleted.
set -o pipefail
WT=$1; LOG=$2; MAIN=$3
cd "$WT/simulations"; unset NASCTIME_RESULTS_ROOT SIMU5G_ROOT
: > "$LOG"
step() { local r=$1; local t0; t0=$(date +%s); ./$r > "$LOG.$(basename $r).out" 2>&1; local rc=$?
  echo "$(date -u +%FT%TZ) $r rc=$rc $(( $(date +%s) - t0 ))s free=$(df -B1G --output=avail / | tail -1 | tr -d ' ')G" >> "$LOG"; }
drop() { rm -rf "$WT/simulations/$1"; echo "$(date -u +%FT%TZ) deleted $1" >> "$LOG"; }
step m2/m2s1.sh; step m2/m2s3.sh; step m2/m2s0.sh; drop m2/results/M2-S0/runs; step m2/m2s4.sh; drop m2/results/M2-S1/runs
step m2/m2s5.sh; drop m2/results/M2-S4/runs
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
step m2/m2s6.sh
echo DONE >> "$LOG"
