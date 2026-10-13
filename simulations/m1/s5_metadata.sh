#!/bin/bash
# M1-S5: timing metadata across the Ethernet - 5G - Ethernet bridge (Config S5,
# S5-nomeas, S5-pcap). Requires S4 results (results/S4/seeds.csv) for the control.
# Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0; OMNETPP_ROOT, INET_ROOT,
# SIMU5G_ROOT set (or the defaults below). NED path as for S1-S4.
# Output: simulations/m1/results/S5/
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
SEEDS=${SEEDS:-0..9}
REPEAT=${REPEAT:-10}
OUT=$HERE/results/S5
[ -f "$HERE/results/S4/seeds.csv" ] || { echo "ERROR: results/S4/seeds.csv missing; run s4_gptp_transport.sh first" >&2; exit 1; }
rm -rf "$OUT/seeds" "$OUT/nomeas" "$OUT/pcaprun"
mkdir -p "$OUT"
source "$OMNETPP_ROOT/setenv" -f >/dev/null
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 src/nasctime/tt ':!simulations/m1/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1 or src/nasctime/tt)')"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"
run() {  # $1 config, $2 runs, $3 result subdir, $4 log
  (cd "$HERE" && opp_run -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat="$REPEAT" -r "$2" --result-dir="$OUT/$3" \
     --cmdenv-express-mode=true > "$OUT/$4" 2>&1) \
  || { echo "ERROR: $1 run failed, see $OUT/$4" >&2; exit 1; }
}
run S5 "$SEEDS" seeds run-S5-seeds.log
run S5-nomeas 0 nomeas run-S5-nomeas.log
run S5-pcap 0 pcaprun run-S5-pcap.log
for d in seeds nomeas pcaprun; do
  opp_scavetool export -o "$OUT/$d.csv" -F CSV-R "$OUT/$d"/*/*.sca "$OUT/$d"/*/*.vec >/dev/null
done
python3 "$HERE/check/check_s5.py" "$HERE/results" | tee "$OUT/check.txt"
