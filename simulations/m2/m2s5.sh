#!/bin/bash
# M2-S5: online downlink two-step gPTP correction (migration/m2-s5-design.md rev. 2.1).
# Builds libnasctime_m2 and runs the M2-S5 configs of simulations/m2/omnetpp.ini.
#   ./m2s5.sh gate   gate G0 only (passive TtPtpPort vs M2-S4); writes results/M2-S5/gate-G0.txt
#   ./m2s5.sh        everything + check_m2s5.py (written in a later step)
# M2-S4 is the timing baseline: needs results/M2-S4/runs (./m2s4.sh, which needs
# results/M2-S1/runs from ./m2s1.sh). Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0
# (built); OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT set (or the defaults below).
# Output: results/M2-S5/ (raw runs under runs/, not committed).
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
JOBS=${JOBS:-2}
MODE=${1:-all}
OUT=$HERE/results/M2-S5
[ -d "$HERE/results/M2-S4/runs/M2S4" ] || { echo "ERROR: results/M2-S4/runs missing; run ./m2s1.sh and ./m2s4.sh first" >&2; exit 1; }
rm -rf "$OUT/runs"
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
} > "$OUT/env.txt"

run() {  # $1 config, $2 runs
  (cd "$HERE" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$OUT/runs/$1" \
     --cmdenv-express-mode=true > "$OUT/runs/run-$1.log" 2>&1) \
  || { echo "ERROR: $1 failed, see $OUT/runs/run-$1.log" >&2; return 1; }
}
export -f run
export HERE NASCTIME SIMU5G_ROOT OUT

gate_configs() {
  printf '%s\n' "M2S5-passive-load 0" "M2S5-passive-load-harq16 0" "M2S5-passive 0..9" "M2S5-passive-frag 0" \
    "M2S5U-base 0" "M2S5U-passive 0"
}

if [ "$MODE" = gate ]; then
  gate_configs | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'
  python3 "$HERE/check/gate_m2s5.py" "$OUT/runs" "$HERE/results/M2-S4/runs" | tee "$OUT/gate-G0.txt"
  exit "${PIPESTATUS[0]}"
fi
echo "ERROR: only './m2s5.sh gate' exists at this step" >&2
exit 1
