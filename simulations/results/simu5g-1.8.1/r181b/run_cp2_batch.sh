#!/bin/bash
# M2-R181b S7.2a Checkpoint 2 revision 2 + I-2H on unmodified Simu5G 1.8.1, in two batches (plan §4.4).
#   run_cp2_batch.sh <results root> Q|D
# Each configuration is run with exactly the opp_run command of m2s72.sh run() (same ini, config, repetitions, express
# flag, fingerprint option), into <root>/m2/M2-S7.2a-cp2r2-<batch>/runs. Then: manifest (manifest.sh), the unchanged
# checkers on that batch directory (check_m2s72_cp2r2.py; batch Q also check_m2s72_i2h.py focused), and deletion of
# the raw runs no later batch reads. Disk guard: no configuration starts below 2 GB free; a running one is stopped
# below 300 MB (STOPPED-DISK, never a result).
#   Q: B-q0-{ideal,Ca,Eall}-n{1,2,4}, B-qdu-Ca-n1, H16-q0-Ca-n{2,4}, H16-qdu-Ca-n2, H16N-{nohold,hto}, BN-rng, BN-theta1
#   D: B-qdu-{ideal,Eall}-n{1,2,4}, B-qdu-Ca-n{2,4}; B-qdu-Ca-n1 (the N = 1 reference of the qdu Ca rows) is kept from Q
set -o pipefail
ROOT=$1; B=$2
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../../.." && pwd)
M2=$NASCTIME/simulations/m2
export SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.1}
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}; INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
[ "$(cat "$SIMU5G_ROOT/Version")" = 1.8.1 ] || { echo "ERROR: $SIMU5G_ROOT is not Simu5G 1.8.1" >&2; exit 1; }
OUT=$ROOT/m2/M2-S7.2a-cp2r2-$B
[ -e "$OUT" ] && { echo "ERROR: $OUT exists" >&2; exit 1; }
mkdir -p "$OUT/runs"; LOG=$OUT/batch.txt
free_mb() { df -B1M --output=avail / | tail -1 | tr -d ' '; }
note() { echo "$(date -u +%FT%TZ) $* free=$(free_mb)M" | tee -a "$LOG"; }
source "$OMNETPP_ROOT/setenv" -f >/dev/null
"$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/build.log" 2>&1 || { note "build failed"; exit 1; }
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version")"
  echo "libsimu5g_sha256: $(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -d' ' -f1)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 simulations/m2 src/nasctime ':!simulations/m1/results' ':!simulations/m2/results')" ] || echo ' (+ uncommitted changes)')"
  echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -d' ' -f1)"
  echo "m2s72_ini_sha256: $(sha256sum "$M2/m2s72.ini" | cut -d' ' -f1)"
} > "$OUT/env.txt"
case "$B" in
  Q) CFGS="$(for c in ideal Ca Eall; do for n in 1 2 4; do echo "M2S72-B-q0-$c-n$n 0..4"; done; done)
M2S72-B-qdu-Ca-n1 0..4
M2S72-H16-q0-Ca-n2 0..4
M2S72-H16-q0-Ca-n4 0..4
M2S72-H16-qdu-Ca-n2 0..4
M2S72-H16N-nohold 0
M2S72-H16N-hto 0
M2S72-BN-rng 0
M2S72-BN-theta1 0" ;;
  D) CFGS="$(for c in ideal Eall; do for n in 1 2 4; do echo "M2S72-B-qdu-$c-n$n 0..4"; done; done)
M2S72-B-qdu-Ca-n2 0..4
M2S72-B-qdu-Ca-n4 0..4"
     [ -d "$ROOT/m2/M2-S7.2a-cp2r2-Q/runs/M2S72-B-qdu-Ca-n1" ] || { note "B-qdu-Ca-n1 (from batch Q) missing"; exit 1; }
     mv "$ROOT/m2/M2-S7.2a-cp2r2-Q/runs/M2S72-B-qdu-Ca-n1" "$ROOT/m2/M2-S7.2a-cp2r2-Q/runs/run-M2S72-B-qdu-Ca-n1.log" "$OUT/runs/"
     note "moved M2S72-B-qdu-Ca-n1 (batch Q run, manifest in batch Q) into batch D as the N = 1 reference" ;;
  *) echo "batch Q or D" >&2; exit 1 ;;
esac
echo "$CFGS" > "$OUT/configs.txt"
runone() {  # identical to m2s72.sh run() for these configs (express=false for B/BN/H/H16; fingerprint option)
  local cfg=$1 reps=$2
  (cd "$M2" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f m2s72.ini -c "$cfg" --repeat=10 -r "$reps" --result-dir="$OUT/runs/$cfg" \
     --cmdenv-express-mode=false --fingerprint=0000-0000/tplx > "$OUT/runs/run-$cfg.log" 2>&1)
}
JOBS=${JOBS:-2}
running=()
while read -r cfg reps; do
  while [ "$(jobs -rp | wc -l)" -ge "$JOBS" ]; do
    [ "$(free_mb)" -lt 300 ] && { pkill -f "result-dir=$OUT"; note "STOPPED-DISK during the batch"; wait; exit 99; }
    sleep 5; done
  if [ "$(free_mb)" -lt 2048 ]; then wait; [ "$(free_mb)" -lt 2048 ] && { note "STOP before $cfg: free < 2 GB"; exit 98; }; fi
  t0=$(date +%s); ( runone "$cfg" "$reps"; echo "$(date -u +%FT%TZ) $cfg rc=$? $(( $(date +%s) - t0 ))s" >> "$LOG" ) &
done <<< "$CFGS"
while [ "$(jobs -rp | wc -l)" -gt 0 ]; do
  [ "$(free_mb)" -lt 300 ] && { pkill -f "result-dir=$OUT"; note "STOPPED-DISK during the batch"; wait; exit 99; }
  sleep 5; done
note "runs done: $(grep -c 'rc=0' "$LOG") rc=0, $(grep -c ' rc=[1-9]' "$LOG") failed"
"$HERE/manifest.sh" "$OUT/runs" "$OUT/r181b" | tee -a "$LOG"
# the unchanged check_m2s72_cp2r2.py main() stops with an exception on a partial matrix (missing control and I-4
# configurations); the batch evaluation calls its row functions unchanged on the configurations present (plan §4.4)
REFONLY=; [ "$B" = D ] && REFONLY=M2S72-B-qdu-Ca-n1
python3 "$HERE/cp2r2_batch_eval.py" eval "$OUT" $REFONLY > "$OUT/cp2r2-batch-eval.txt" 2>&1; note "cp2r2 batch eval rc=$? rows $(grep -c ' | PASS | \| | FAIL | ' "$OUT/cp2r2-batch-eval.txt")"
if [ "$B" = Q ]; then
  python3 "$M2/check/check_m2s72_i2h.py" focused "$OUT" > "$OUT/i2h-check.txt" 2>&1; note "i2h check rc=$? $(tail -1 "$OUT/i2h-check.txt")"
  for d in "$OUT/runs"/*/; do c=$(basename "$d"); [ "$c" = M2S72-B-qdu-Ca-n1 ] && continue
    rm -rf "$d"; echo "$(date -u +%FT%TZ) deleted after manifest and checks: ${d#$ROOT/}" >> "$ROOT/deleted-raw.txt"; done
  note "batch Q raw deleted except M2S72-B-qdu-Ca-n1 (kept for batch D)"
else
  rm -rf "$OUT/runs"/*/; echo "$(date -u +%FT%TZ) deleted after manifest and checks: ${OUT#$ROOT/}/runs/*" >> "$ROOT/deleted-raw.txt"
  note "batch D raw deleted"
fi
note "DONE batch $B"
