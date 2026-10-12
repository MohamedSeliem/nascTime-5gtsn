#!/bin/bash
# M1-S4: gPTP through the non-time-aware 5G bridge (Config S4, Config S4-pcap).
# Two separate checks: transport (check_s4.py transport) and clock behaviour
# (check_s4.py clock, model consistency + recorded baseline, no accuracy claim).
#
# Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0; OMNETPP_ROOT, INET_ROOT,
# SIMU5G_ROOT set (or the defaults below). NED path as for S1-S3.
# Output: simulations/m1/results/S4/
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
SEEDS=${SEEDS:-0..9}
REPEAT=${REPEAT:-10}
OUT=$HERE/results/S4
rm -rf "$OUT/seeds" "$OUT/pcaprun"
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
run S4 "$SEEDS" seeds run-S4-seeds.log
run S4-pcap 0 pcaprun run-S4-pcap.log
opp_scavetool export -o "$OUT/seeds.csv" -F CSV-R "$OUT"/seeds/*/*.sca "$OUT"/seeds/*/*.vec >/dev/null
opp_scavetool export -o "$OUT/pcaprun.csv" -F CSV-R "$OUT"/pcaprun/*/*.sca "$OUT"/pcaprun/*/*.vec >/dev/null
python3 "$HERE/check/check_s4.py" transport "$HERE/results" | tee "$OUT/transport-check.txt"
python3 "$HERE/check/check_s4.py" clock "$HERE/results" | tee "$OUT/clock-check.txt"
