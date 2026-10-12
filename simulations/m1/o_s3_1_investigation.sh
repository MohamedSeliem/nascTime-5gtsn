#!/bin/bash
# Investigation of open observation O-S3-1: frames accepted by RLC TX but never
# delivered by RLC RX under saturating load (Config S3-load). Tests four candidate
# causes -- end-of-run in flight, queue overflow, radio loss, a discard that no
# statistic records -- with configuration and Simu5G's own debug log only.
# check/check_o_s3_1.py states each criterion.
#
# Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0; OMNETPP_ROOT, INET_ROOT,
# SIMU5G_ROOT set (or the defaults below). About 10 min.
# Output: simulations/m1/results/O-S3-1/
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
SEEDS=${SEEDS:-0..4}
OUT=$HERE/results/O-S3-1
rm -rf "$OUT/runs" && mkdir -p "$OUT/runs"
source "$OMNETPP_ROOT/setenv" -f >/dev/null
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 src/nasctime/tt ':!simulations/m1/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1 or src/nasctime/tt)')"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"

opp() {  # $1 config, $2 runs, $3 result dir; output on stdout
  (cd "$HERE" && opp_run -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$3" "${@:4}")
}
for c in O1-drain O1-harq16; do
  opp "$c" "$SEEDS" "$OUT/runs/$c" --cmdenv-express-mode=true > "$OUT/run-$c.log" 2>&1 \
    || { echo "ERROR: $c failed, see $OUT/run-$c.log" >&2; exit 1; }
  opp_scavetool export -o "$OUT/$c.csv" -F CSV-R "$OUT/runs/$c"/*/*.sca "$OUT/runs/$c"/*/*.vec >/dev/null
done
# Traces: keep only the gNB/UE MAC lines the checker reads (the full log is ~1 GB)
for c in O1-drain-trace O1-harq16-trace; do
  { opp "$c" 0 "$OUT/runs/$c" 2>&1; echo "EXIT=$?"; } \
    | grep -E '^EXIT=|<!> Error|^[0-9.e-]+ (mac|nrMac) [^|]*\| .*(created PDU|no available process|Using buffer for|extracted SDU|new pdu \(id|feedback received for process)' \
    > "$OUT/runs/trace-$c.log" || true
  grep -q "^EXIT=0$" "$OUT/runs/trace-$c.log" && ! grep -q "<!> Error" "$OUT/runs/trace-$c.log" \
    || { echo "ERROR: $c failed, see $OUT/runs/trace-$c.log" >&2; exit 1; }
  opp_scavetool export -o "$OUT/$c.csv" -F CSV-R "$OUT/runs/$c"/*/*.sca "$OUT/runs/$c"/*/*.vec >/dev/null
done
python3 "$HERE/check/check_o_s3_1.py" "$HERE/results" | tee "$OUT/check.txt"
