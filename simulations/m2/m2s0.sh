#!/bin/bash
# M2-S0: chunk-level timestamp tag across the Ethernet - 5G - Ethernet bridge.
# Builds libnasctime_m2, runs every M2-S0 config (simulations/m2/omnetpp.ini), exports
# the statistics and runs the checker. Requires OMNeT++ 6.4.0 / INET 4.7.0 /
# Simu5G 1.8.0 (built); OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT set (or the defaults below).
# Output: simulations/m2/results/M2-S0/ (check.txt, census.txt, env.txt, raw-outputs.sha256;
# raw run outputs under runs/, not committed).
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
JOBS=${JOBS:-2}
OUT=$HERE/results/M2-S0
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
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 simulations/m2 src/nasctime ':!simulations/m1/results' ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1, simulations/m2 or src/nasctime)')"
  echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -d' ' -f1)"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"

run() {  # $1 config, $2 runs
  (cd "$HERE" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$OUT/runs/$1" \
     --cmdenv-express-mode=true > "$OUT/runs/run-$1.log" 2>&1) \
  || { echo "ERROR: $1 failed, see $OUT/runs/run-$1.log" >&2; return 1; }
  opp_scavetool export -o "$OUT/runs/$1.csv" -F CSV-R "$OUT/runs/$1/$1"/*.sca "$OUT/runs/$1/$1"/*.vec >/dev/null
}
export -f run
export HERE NASCTIME SIMU5G_ROOT OUT
# config and runs; load configs first (longest)
printf '%s\n' \
  "M2S0-load 0" "M2S0-load-harq16 0" "M2S0-load-off 0" "M2S0-probe-load 0" \
  "M2S0 0..9" "M2S0-off 0" "M2S0-frag 0" "M2S0-probe 0" "M2S0-probe-frag 0" \
  "M2S0-nc-noingress 0" "M2S0-nc-offset 0" "M2S0-nc-id 0" "M2S0-nc-nostrip 0" \
  | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'

python3 "$HERE/check/check_m2s0.py" "$OUT" | tee "$OUT/check.txt"
(cd "$OUT/runs" && find . -type f \( -name '*.sca' -o -name '*.vec' -o -name '*.pcapng' -o -name '*.csv' \) \
   ! -name '*.vci' | LC_ALL=C sort | xargs sha256sum) > "$OUT/raw-outputs.sha256"
