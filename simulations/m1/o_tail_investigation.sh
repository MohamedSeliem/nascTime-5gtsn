#!/bin/bash
# Investigation of O-S4-1 (late Follow_Ups) and O-S3-2 (stranded last DL SDU): replay
# of the gNB's DRB 1 RLC from recorded statistics, plus two counterfactuals.
# check/check_o_tail.py states each criterion. Seed 0 only. About 2 min.
# Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0; OMNETPP_ROOT, INET_ROOT,
# SIMU5G_ROOT set (or the defaults below).
# Output: simulations/m1/results/O-tail/
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
OUT=$HERE/results/O-tail
rm -rf "$OUT" && mkdir -p "$OUT/runs"
source "$OMNETPP_ROOT/setenv" -f >/dev/null
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 src/nasctime/tt ':!simulations/m1/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1 or src/nasctime/tt)')"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"
for c in O2-s4 O2-s4-nodl O1-harq16 O2-flush; do
  (cd "$HERE" && opp_run -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$c" --repeat=10 -r 0 --result-dir="$OUT/runs" \
     --cmdenv-express-mode=true > "$OUT/run-$c.log" 2>&1) \
  || { echo "ERROR: $c failed, see $OUT/run-$c.log" >&2; exit 1; }
  opp_scavetool export -o "$OUT/$c.csv" -F CSV-R "$OUT/runs/$c"/*.sca "$OUT/runs/$c"/*.vec >/dev/null
done
python3 "$HERE/check/check_o_tail.py" "$HERE/results" | tee "$OUT/check.txt"
