#!/bin/bash
# M1-S1: nascTime's own copy of the reference scenario (Config S1 in omnetpp.ini),
# compared against S0's upstream Ethernet-Bridge run, seed by seed.
#
# Requires S0 results (results/S0/seeds.csv); run s0_vanilla_reference.sh first.
# Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0 built; OMNETPP_ROOT, INET_ROOT,
# SIMU5G_ROOT set (or the defaults below). Does not load libnasctime: M1 uses only
# unmodified Simu5G and INET modules.
# NED path: nascTime simulations/ and src/ (for nasctime.tt, used by S2); the legacy
# package nasctime.nodes is excluded (-x) because its NED does not load on Simu5G 1.8.0.
# Output: simulations/m1/results/S1/
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
SEEDS=${SEEDS:-0..9}
REPEAT=${REPEAT:-10}
OUT=$HERE/results/S1
[ -f "$HERE/results/S0/seeds.csv" ] || { echo "ERROR: results/S0/seeds.csv missing; run s0_vanilla_reference.sh first" >&2; exit 1; }
mkdir -p "$OUT"
source "$OMNETPP_ROOT/setenv" -f >/dev/null

{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1)')"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"

cd "$HERE"
opp_run -l "$SIMU5G_ROOT/src/simu5g" -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
  -u Cmdenv -f omnetpp.ini -c S1 --repeat="$REPEAT" -r "$SEEDS" --result-dir="$OUT/seeds" \
  --cmdenv-express-mode=true > "$OUT/run-S1-seeds.log" 2>&1 \
  || { echo "ERROR: S1 run failed, see $OUT/run-S1-seeds.log" >&2; exit 1; }
opp_scavetool export -o "$OUT/seeds.csv" -F CSV-R "$OUT"/seeds/*/*.sca "$OUT"/seeds/*/*.vec >/dev/null
python3 "$HERE/check/check_s1.py" "$HERE/results" | tee "$OUT/check.txt"
