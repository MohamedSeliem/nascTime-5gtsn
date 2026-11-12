#!/bin/bash
# M2-R181b 1.8.0 controls of the new rows (plan §3, §4.5), isolated root, Simu5G 1.8.0 (accepted build, unmodified).
#   run_controls_180.sh <new results root (absolute)>
# M1: s4_gptp_transport.sh, s5_metadata.sh, o_tail_investigation.sh (isolated mode, 1.8.0), then
#     check_v181b.py s5e / s5i, and check_o_tail_v181.py (must reproduce the committed 1.8.0 O-tail/check.txt byte
#     for byte: the copy changes no verdict logic).
# M2: the configurations the rows read, with the runners' own opp_run command (m2s0.sh / m2s1.sh / m2s4.sh run()):
#     M2S0-load, M2S0-load-harq16, M2S1-load, M2S1-load-harq16 (seed 0), M2S4 and M2S4-ctl-nopdelay (seeds 0-9),
#     M2S4-load and M2S4-ctl-nopdelay-load (seed 0); then check_v181b_m2.py a7 / c10 / r2b.
# All raw outputs: manifest, then deleted.
set -o pipefail
ROOT=$1
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../../.." && pwd)
S=$NASCTIME/simulations
export SIMU5G_ROOT=/root/stack/simu5g-1.8.0
export NASCTIME_RESULTS_ROOT=$ROOT
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}; INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
[ "$(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -d' ' -f1)" = 203cf231e6605188662769b439e403d832f516d2e08c8a0c5a9e8f55f4305cf6 ] \
  || { echo "ERROR: not the accepted Simu5G 1.8.0 library" >&2; exit 1; }
[ -e "$ROOT" ] && { echo "ERROR: $ROOT exists" >&2; exit 1; }
mkdir -p "$ROOT"; LOG=$ROOT/steps.txt
note() { echo "$(date -u +%FT%TZ) $* free=$(df -B1M --output=avail / | tail -1 | tr -d ' ')M" | tee -a "$LOG"; }
for r in s4_gptp_transport s5_metadata o_tail_investigation; do
  "$S/m1/$r.sh" > "$ROOT/console-$r.txt" 2>&1; note "m1/$r rc=$?"
done
R1=$ROOT/m1
for m in s5e s5i; do
  python3 "$S/m1/check/check_v181b.py" $m "$R1" > "$R1/v181b-$m-on-1.8.0.txt" 2>&1; note "$m on 1.8.0: $(grep '^OVERALL' "$R1/v181b-$m-on-1.8.0.txt")"
done
python3 "$S/m1/check/check_o_tail_v181.py" "$R1" > "$R1/O-tail/check-v181copy.txt" 2>&1
cmp -s "$R1/O-tail/check-v181copy.txt" "$S/m1/results/O-tail/check.txt" && r=IDENTICAL || r=DIFFERENT
cmp -s "$R1/O-tail/check.txt" "$S/m1/results/O-tail/check.txt" && r0=IDENTICAL || r0=DIFFERENT
note "check_o_tail_v181.py on 1.8.0 vs committed O-tail/check.txt: $r (historical checker on the same outputs: $r0)"
source "$OMNETPP_ROOT/setenv" -f >/dev/null
"$NASCTIME/src/nasctime/m2/build.sh" > "$ROOT/build.log" 2>&1 || { note "build failed"; exit 1; }
RUNS=$ROOT/m2runs; mkdir -p "$RUNS"
run() { (cd "$S/m2" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$RUNS/$1" --cmdenv-express-mode=true > "$RUNS/run-$1.log" 2>&1); echo "$1 rc=$?"; }
export -f run; export S NASCTIME SIMU5G_ROOT INET_ROOT RUNS
printf '%s\n' "M2S0-load 0" "M2S0-load-harq16 0" "M2S1-load 0" "M2S1-load-harq16 0" "M2S4 0..9" "M2S4-ctl-nopdelay 0..9" \
  "M2S4-load 0" "M2S4-ctl-nopdelay-load 0" | xargs -P 3 -L 1 bash -c 'run "$0" "$1"' >> "$LOG"
for m in a7 c10 r2b; do
  python3 "$S/m2/check/check_v181b_m2.py" $m "$RUNS" > "$ROOT/v181b-$m-on-1.8.0.txt" 2>&1; note "$m on 1.8.0: $(grep '^OVERALL' "$ROOT/v181b-$m-on-1.8.0.txt")"
done
"$HERE/manifest.sh" "$RUNS" "$ROOT/m2runs" >> "$LOG"
rm -rf "$RUNS"; note "deleted m2runs after manifest"
for d in S4/seeds S5/seeds S5/nomeas S5/pcaprun O-tail/runs; do
  [ -d "$R1/$d" ] && { (cd "$R1" && find "$d" -type f | LC_ALL=C sort | xargs sha256sum) >> "$ROOT/m1-deleted.sha256"; rm -rf "$R1/$d"; note "deleted m1/$d after hashing"; }
done
note DONE
