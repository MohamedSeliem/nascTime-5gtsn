#!/bin/bash
# M2-S7.1: dedicated gPTP QoS, residence-time monitoring, Follow_Up lag (migration/m2-s7.1-design.md
# revision 3). Builds libnasctime_m2 and runs the M2-S7.1 configs of simulations/m2/omnetpp.ini on
# unmodified OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0 (rule B-1).
#   ./m2s71.sh M0          gate M0 (monitor non-perturbation)             -> results/M2-S7.1/gate-M0.txt
#   ./m2s71.sh phase1      phase-1 matrix (9 options x idle/load/frag x 5/16 HARQ), 12 s
#   ./m2s71.sh accuracy    Q4 accuracy configs (GM drift: M2-S6 C-a, B-p100), 12 s
#   ./m2s71.sh extra       Q3 bound variants, controls, MAC trace runs (Q6)
#   ./m2s71.sh twins       P0: the same configs at a 10 s limit (seed 0), and M2-S6 C-a/B-p100 regenerated
#   ./m2s71.sh h0          H0: seed 0 of every 12 s config at a 20 s limit (plus runs listed in h0-extra.txt)
#   ./m2s71.sh gates       gates P0, C0, C1, Q0a, Q0b                       -> gate-P0.txt, gate-Q0b.txt
#   ./m2s71.sh check1      phase-1 check (needs the gate records)           -> phase1-check.txt, phase1-report.txt
#   ./m2s71.sh phase2 A B  phase 2: sustained load for Q-0, option A (non-experimental), option B (experimental)
#   ./m2s71.sh review      exploratory sustained-load runs (Q-0, Q-a, Q-d (UM)) not already run by phase 2
#   ./m2s71.sh seeds       seed-invariance diagnostic                       -> diagnostics/seeds.txt
#   ./m2s71.sh check2      phase-2 check                                    -> phase2-check.txt
#   ./m2s71.sh check       final check over everything present              -> check.txt, report.txt
#   ./m2s71.sh configs     run the "config reps" lines read from stdin into runs/
#   ./m2s71.sh all         everything from scratch, in the design's order (phase 2 options from phase 1)
# Requires OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (or the defaults below) and, for M0 and P0(ii), the
# committed results/M2-S5/raw-outputs.sha256 and results/M2-S6/raw-outputs.sha256.
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
JOBS=${JOBS:-2}
MODE=${1:-all}
OUT=$HERE/results/M2-S7.1
CHK=$HERE/check
mkdir -p "$OUT"
"$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/build.log" 2>&1 || { echo "ERROR: build failed, see $OUT/build.log" >&2; exit 1; }
source "$OMNETPP_ROOT/setenv" -f >/dev/null
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "compiler: $(clang++ --version 2>/dev/null | head -1)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 simulations/m2 src/nasctime ':!simulations/m1/results' ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1, simulations/m2 or src/nasctime)')"
  echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -d' ' -f1)"
  echo "python: $(python3 --version 2>&1)"
  echo "os: $(uname -srm)"
} > "$OUT/env-$MODE.txt"

# run <config> <repetitions> <root dir under OUT> [extra opp_run arguments...]
run() {
  local cfg=$1 reps=$2 root=$3; shift 3
  if [ -n "$REUSE" ] && [ -d "$OUT/$root/$cfg" ]; then return 0; fi   # twins/h0: keep runs already present
  rm -rf "$OUT/$root/$cfg"
  mkdir -p "$OUT/$root"
  local express=--cmdenv-express-mode=true
  case "$cfg" in M2S71-T-*) express=--cmdenv-express-mode=false ;; esac   # Q6 MAC debug traces
  (cd "$HERE" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$cfg" --repeat=10 -r "$reps" --result-dir="$OUT/$root/$cfg" \
     "$express" "$@" > "$OUT/$root/run-$cfg.log" 2>&1) \
  || { echo "ERROR: $cfg failed, see $OUT/$root/run-$cfg.log" >&2; return 1; }
}
runline() { local root=$1 cfg=$2 reps=$3; shift 3; run "$cfg" "$reps" "$root" "$@"; }
export -f run runline
export HERE NASCTIME SIMU5G_ROOT OUT REUSE

OPTS="q0 q0p qa qb qc qc2 qdu qda qd2"
phase1_configs() {
  for o in $OPTS; do for h in "" -h16; do
    echo "M2S71-$o-idle$h 0..9"; echo "M2S71-$o-load$h 0..4"; echo "M2S71-$o-frag$h 0"
  done; done
}
accuracy_configs() { for o in $OPTS; do echo "M2S71-$o-Ca 0..4"; echo "M2S71-$o-Bp100 0..4"; done; }
phase2_configs() { for o in q0 "$@"; do for h in "" -h16; do echo "M2S71-$o-sus$h 0..4"; done; echo "M2S71-$o-Ca-sus 0..4"; done; }
# seed-invariance diagnostic (review 2026-10-22, item 5): RNG draws per module group, and one RNG varied at a time
seeds_configs() {
  for b in q0-idle q0-load qdu-idle qdu-load; do echo "M2S71-R-$b 0..4"; for k in 0 2 3 5 7; do echo "M2S71-R-$b-v$k 0..4"; done; done
}
seeds() {
  seeds_configs | runlist runs
  mkdir -p "$OUT/diagnostics"
  python3 "$CHK/diag_m2s71_seeds.py" "$OUT" > "$OUT/diagnostics/seeds.txt"
  # draws by call site (gdb), 2 s of Q-0 idle (MAXCI) and Q-d (UM) idle (QOS_PF), seed 0
  local c
  for c in M2S71-q0-idle M2S71-qdu-idle; do
    (cd "$HERE" && gdb -q -batch -ex "python OUTF='$OUT/diagnostics/rng-callsites-$c.txt'" -ex "source $CHK/diag_m2s71_rng_gdb.py" -ex run \
       --args "$(command -v opp_run)" -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
       -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes -u Cmdenv -f omnetpp.ini \
       -c "$c" -r 0 --sim-time-limit=2s --result-dir="$OUT/runs-gdb" --cmdenv-express-mode=true > "$OUT/runs-gdb-$c.log" 2>&1)
  done
}
# exploratory sustained-load comparison (review 2026-10-22, item 3): Q-0, Q-a and Q-d (UM) under sustained load,
# same configs and seeds as phase 2; only those not already run by the formal phase 2
review_configs() {
  local A B; read -r A B < "$OUT/phase2-options.txt"
  for o in q0 qa qdu; do case " q0 $A $B " in *" $o "*) ;; *) phase2_configs_one "$o" ;; esac; done
}
phase2_configs_one() { for h in "" -h16; do echo "M2S71-$1-sus$h 0..4"; done; echo "M2S71-$1-Ca-sus 0..4"; }
# runs a list of lines "config reps [extra opp_run args]" read from stdin into root dir $1; $2... are
# extra opp_run arguments for every line
runlist() { local root=$1; shift; xargs -P "$JOBS" -L 1 bash -c 'runline "'"$root"'" "$@" '"$*" _; }

m0() {
  printf '%s\n' "M2S71-M0-m2s5 0..9" "M2S71-M0-hold 0" "M2S71-M0-Ca 0..9" "M2S71-qdu-idle 0" "M2S71-M0-qdu-off 0" | runlist runs-m0
  # event fingerprints (seed 0): monitor present vs absent, and N-monitor
  printf '%s\n' "M2S5 0" "M2S71-M0-m2s5 0" "M2S5U-hold 0" "M2S71-M0-hold 0" "M2S6-C-a 0" "M2S71-M0-Ca 0" \
                "M2S71-qdu-idle 0" "M2S71-M0-qdu-off 0" "M2S71-N-monitor 0" | runlist runs-m0fp --fingerprint=0000-0000/tplx
  python3 "$CHK/gate_m2s71.py" m0 "$OUT" "$HERE/results" | tee "$OUT/gate-M0.txt"
}
extra() {
  printf '%s\n' "M2S71-qa-idle-B5 0" "M2S71-qa-idle-B6 0" "M2S71-q0-idle-B10 0" "M2S71-N-noRule 0..9" "M2S71-N-swap 0" \
                "M2S71-N-noHold 0" "M2S71-N-prio 0..4" "M2S71-H-hold 0..4" "M2S71-H-noHold 0..4" | runlist runs
  # N-bound: bound = the residence of the first corrected Follow_Up of M2S71-qa-idle seed 0 (exact equality exercised)
  local b; b=$(python3 "$CHK/m2s71_tools.py" first-res "$OUT/runs/M2S71-qa-idle/m2log/M2S71-qa-idle-0")
  echo "M2S71-N-bound 0 --*.dsTt.eth[1].trafficConditionerLayer.monitor.residenceBound=${b}" | runlist runs
  echo "$b" > "$OUT/runs/M2S71-N-bound.bound"
  # N-drop: threshold = p99 of the monitor lag of M2S71-q0-idle seed 0
  local t; t=$(python3 "$CHK/m2s71_tools.py" p99-lag "$OUT/runs/M2S71-q0-idle/m2log/M2S71-q0-idle-0")
  echo "M2S71-N-drop 0 --*.dsTt.eth[1].trafficConditionerLayer.syncOut.egressTest=\\\"dropLag:${t}\\\"" | runlist runs
  echo "$t" > "$OUT/runs/M2S71-N-drop.threshold"
  # Q6: MAC debug traces (seed 0) of every option under the 0.6 s load burst, 5 and 16 HARQ processes
  for o in $OPTS; do echo "M2S71-T-$o-load 0"; echo "M2S71-T-$o-load-h16 0"; done | runlist runs-trace
}
twins() {
  { phase1_configs | sed 's/ 0\.\.[0-9]*$/ 0/'; for o in $OPTS; do echo "M2S71-$o-Ca 0"; echo "M2S71-$o-Bp100 0"; done
    if [ -f "$OUT/phase2-options.txt" ]; then { phase2_configs $(cat "$OUT/phase2-options.txt"); review_configs; } | sed 's/ 0\.\.[0-9]*$/ 0/'; fi; } \
    | runlist runs-10s --sim-time-limit=10s
  printf '%s\n' "M2S6-C-a 0..4" "M2S6-B-p100 0..4" | runlist runs-m2s6ref
}
h0() {
  { phase1_configs | sed 's/ 0\.\.[0-9]*$/ 0/'
    if [ -f "$OUT/phase2-options.txt" ]; then { phase2_configs $(cat "$OUT/phase2-options.txt"); review_configs; } | sed 's/ 0\.\.[0-9]*$/ 0/'; fi
    if [ -f "$OUT/h0-extra.txt" ]; then cat "$OUT/h0-extra.txt"; fi; } | sort -u | runlist runs-20s --sim-time-limit=20s
}

case "$MODE" in
  M0) m0 ;;
  phase1) phase1_configs | runlist runs ;;
  accuracy) accuracy_configs | runlist runs ;;
  extra) extra ;;
  twins) REUSE=1; twins ;;
  h0) REUSE=1; h0 ;;
  configs) runlist runs ;;   # lines "config reps" from stdin (e.g. to rerun configs)
  gates) python3 "$CHK/gate_m2s71.py" gates "$OUT" "$HERE/results" | tee "$OUT/gate-P0.txt" ;;
  check1) python3 "$CHK/check_m2s71.py" phase1 "$OUT" | tee "$OUT/phase1-check.txt" ;;
  phase2) shift; [ $# -eq 2 ] || { echo "usage: m2s71.sh phase2 <non-experimental option> <experimental option>" >&2; exit 2; }
          echo "$1 $2" > "$OUT/phase2-options.txt"; phase2_configs "$1" "$2" | runlist runs ;;
  review) review_configs | runlist runs ;;
  seeds) seeds ;;
  check2) python3 "$CHK/check_m2s71.py" phase2 "$OUT" | tee "$OUT/phase2-check.txt" ;;
  check) python3 "$CHK/check_m2s71.py" final "$OUT" | tee "$OUT/check.txt" ;;
  # all = all1 all2 all3 all4 (stages, so that each fits a bounded session; same steps, same order)
  all1)
    rm -rf "$OUT"/runs* "$OUT/phase2-options.txt" "$OUT/h0-extra.txt"
    m0 > /dev/null || true
    phase1_configs | runlist runs ;;
  all2)
    accuracy_configs | runlist runs
    extra
    REUSE=1 twins
    REUSE=1 h0                              # phase-1 H0 runs: H0 is an eligibility row of the phase-1 selection
    python3 "$CHK/gate_m2s71.py" gates "$OUT" "$HERE/results" > "$OUT/gate-P0.txt" || true
    python3 "$CHK/check_m2s71.py" phase1 "$OUT" > "$OUT/phase1-check.txt" || true ;;
  all3)
    read -r A B < "$OUT/phase2-options.txt"
    phase2_configs "$A" "$B" | runlist runs
    review_configs | runlist runs           # exploratory: Q-d (UM) under sustained load (not part of the selection)
    REUSE=1 twins
    REUSE=1 h0 ;;
  all4)
    seeds                                   # seed-invariance diagnostic (needs the primary runs for its section 3)
    python3 "$CHK/gate_m2s71.py" gates "$OUT" "$HERE/results" > "$OUT/gate-P0.txt" || true   # gates over the phase-2 runs too
    python3 "$CHK/check_m2s71.py" final "$OUT" > "$OUT/check.txt" || true
    REUSE=1 h0                              # second pass: runs listed in h0-extra.txt by the check
    python3 "$CHK/check_m2s71.py" final "$OUT" > "$OUT/check.txt" || true
    (cd "$OUT" && find runs* -type f \( -name '*.pcapng' -o -name '*.csv' -o -name '*.sca' -o -name '*.vec' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
    grep -m1 OVERALL "$OUT/check.txt" ;;
  all) for s in all1 all2 all3 all4; do "$0" "$s" || exit $?; done ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
