#!/bin/bash
# M2-S6: non-ideal clocks (migration/m2-s6-design.md rev. 2). Builds libnasctime_m2 and runs the
# M2-S6 configs of simulations/m2/omnetpp.ini by stage:
#   ./m2s6.sh gate        gate D0 (RNG policy, 0 ppm / 1 ps oscillator, tick-reset probe); writes results/M2-S6/gate-D0.txt
#   ./m2s6.sh A|B|C|D|E|F runs one stage (raw runs under results/M2-S6/runs/<config>)
#   ./m2s6.sh E0b         gate E0b (zero-parameter TT clocks = M2-S5); writes results/M2-S6/gate-E0b.txt
#   ./m2s6.sh check       check_m2s6.py over the runs present; writes results/M2-S6/check.txt
#   ./m2s6.sh             everything + check
# Gate D0 compares with the committed results/M2-S5/raw-outputs.sha256 and, for the D0c vector rows,
# with results/M2-S5/runs (./m2s5.sh). Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0 (built);
# OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT set (or the defaults below).
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
JOBS=${JOBS:-2}
MODE=${1:-all}
OUT=$HERE/results/M2-S6
mkdir -p "$OUT/runs"
"$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/runs/build.log" 2>&1 \
  || { echo "ERROR: build failed, see $OUT/runs/build.log" >&2; exit 1; }
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

run() {  # $1 config, $2 runs
  rm -rf "$OUT/runs/$1"
  (cd "$HERE" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$OUT/runs/$1" \
     --cmdenv-express-mode=true > "$OUT/runs/run-$1.log" 2>&1) \
  || { echo "ERROR: $1 failed, see $OUT/runs/run-$1.log" >&2; return 1; }
}
export -f run
export HERE NASCTIME SIMU5G_ROOT OUT

stage_configs() {
  case "$1" in
    gate) printf '%s\n' "M2S6-d0-rng 0..9" "M2S6-d0-rngUnpinned 1" "M2S6-d0-osc0 0" "M2S6U-d0-osc0 0" "M2S6U-Q10 0" ;;
    A) printf '%s\n' "M2S6U-A1 0" "M2S6U-A2 0" "M2S6U-A3 0" "M2S6U-A4 0..2" "M2S6U-A5 0" ;;
    B) printf '%s\n' "M2S6U-B-m100 0" "M2S6U-B-m10 0" "M2S6U-B-m1 0" "M2S6U-B-p1 0" "M2S6U-B-p10 0" "M2S6U-B-p100 0" \
         "M2S6-B-p100 0..9" "M2S6-B-m100 0" "M2S6-B-p10 0" ;;
    C) printf '%s\n' "M2S6U-C-sp100 0" "M2S6U-C-sm100 0" "M2S6U-C-a 0" "M2S6U-C-b 0" "M2S6U-C-r001 0" "M2S6U-C-r01 0" \
         "M2S6U-C-r1 0" "M2S6U-C-rs1 0" "M2S6U-C-off 0" "M2S6U-C-1ps 0" "M2S6U-C-1psr 0" \
         "M2S6-C-a 0..9" "M2S6-C-off 0" "M2S6-C-r1 0" "M2S6-C-FS1 0" "M2S6-C-FS2 0" "M2S6-C-FD1 0" "M2S6-C-FD2 0" ;;
    D) printf '%s\n' "M2S6-D-frag 0" "M2S6-D-load 0" "M2S6-D-load-harq16 0" "M2S6-D-nwpd025 0" "M2S6-D-nwpd8 0" \
         "M2S6-D-slpd0125 0" "M2S6-D-FS2late 0" "M2S6-D-FD1late 0" ;;
    E) printf '%s\n' "M2S6U-E-th10 0" "M2S6U-E-th100 0" "M2S6U-E-th1000 0" "M2S6U-E-y 0" "M2S6U-E-yfree 0" "M2S6U-E-D 0" \
         "M2S6U-E-sig1 0..4" "M2S6U-E-sig10 0..4" "M2S6U-E-sig100 0..4" "M2S6U-E-L8 0" "M2S6-E-all 0..2" "M2S6-E-all-load 0" ;;
    F) printf '%s\n' "M2S6U-F-rrIgnore 0" "M2S6-F-rrIgnore 0" "M2S6U-F-rrTwice 0" "M2S6U-F-nrrInvert 0" "M2S6U-F-nrrStale 0" \
         "M2S6U-F-lupLocal 0" "M2S6U-F-domain 0" "M2S6U-F-servoNoRate 0" "M2S6U-F-servoNegRate 0" ;;
    *) echo "unknown stage $1" >&2; return 1 ;;
  esac
}

if [ "$MODE" = gate ]; then
  stage_configs gate | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'
  python3 "$HERE/check/gate_m2s6.py" "$OUT/runs" "$HERE/results/M2-S5/raw-outputs.sha256" "$HERE/results/M2-S5/runs" | tee "$OUT/gate-D0.txt"
  exit "${PIPESTATUS[0]}"
fi
if [ "$MODE" = E0b ]; then
  printf '%s\n' "M2S6-E0b 0..9" "M2S6U-E0b 0" | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'
  python3 "$HERE/check/gate_m2s6.py" --e0b "$OUT/runs" "$HERE/results/M2-S5/raw-outputs.sha256" | tee "$OUT/gate-E0b.txt"
  exit "${PIPESTATUS[0]}"
fi
if [ "$MODE" = check ]; then
  python3 "$HERE/check/check_m2s6.py" "$OUT/runs" --report="$OUT/report.txt" | tee "$OUT/check.txt"
  exit "${PIPESTATUS[0]}"
fi
if [ "$MODE" = all ]; then
  for st in gate A B C D E F; do stage_configs "$st"; done | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'
  python3 "$HERE/check/gate_m2s6.py" "$OUT/runs" "$HERE/results/M2-S5/raw-outputs.sha256" "$HERE/results/M2-S5/runs" | tee "$OUT/gate-D0.txt"
  python3 "$HERE/check/check_m2s6.py" "$OUT/runs" --report="$OUT/report.txt" | tee "$OUT/check.txt"
  exit 0
fi
stage_configs "$MODE" | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'
