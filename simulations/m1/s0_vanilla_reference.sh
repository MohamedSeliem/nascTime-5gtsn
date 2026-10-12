#!/bin/bash
# M1-S0: vanilla reference. Runs Simu5G 1.8.0's own Ethernet-session example and its
# fingerprint rows, unmodified. No nascTime code is involved.
#
# Requires: OMNeT++ 6.4.0, INET 4.7.0 and Simu5G 1.8.0 built, with OMNETPP_ROOT,
# INET_ROOT and SIMU5G_ROOT set (or the defaults below).
# Output: simulations/m1/results/S0/ (fingerprint log, .sca/.vec, CSV exports, env record)
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
SEEDS=${SEEDS:-0..9}
OUT=$HERE/results/S0
mkdir -p "$OUT"

source "$OMNETPP_ROOT/setenv" -f >/dev/null
(cd "$INET_ROOT" && source setenv -f >/dev/null)
export INET_ROOT SIMU5G_ROOT
export PATH="$SIMU5G_ROOT/bin:$INET_ROOT/bin:$PATH"

{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/.version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "compiler: $(${CXX:-clang++} --version | head -1)"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"

# 1. Upstream's own fingerprint rows for the Ethernet example (proves this build
#    reproduces upstream's reference build). -m takes one regex.
(cd "$SIMU5G_ROOT/tests/fingerprint" && ./fingerprints simulations.csv -m '/nr/ethernet/') \
  > "$OUT/fingerprints.log" 2>&1 || true

# 2. The four example configs, seed 0, with result files kept.
cd "$SIMU5G_ROOT/simulations/nr/ethernet"
for c in Ethernet-Hosts Ethernet-Bridge Ethernet-Handover Ethernet-Mixed; do
  simu5g -u Cmdenv -f omnetpp.ini -c "$c" -r 0 --result-dir="$OUT/runs" \
    --cmdenv-express-mode=true > "$OUT/run-$c.log" 2>&1 || echo "RUN FAILED: $c" >> "$OUT/failures.txt"
done

# 3. Ethernet-Bridge over several seeds: the reference delay distribution for S1.
simu5g -u Cmdenv -f omnetpp.ini -c Ethernet-Bridge --repeat=${REPEAT:-10} -r "$SEEDS" --result-dir="$OUT/seeds" \
  --cmdenv-express-mode=true > "$OUT/run-Ethernet-Bridge-seeds.log" 2>&1 \
  || echo "RUN FAILED: Ethernet-Bridge seeds" >> "$OUT/failures.txt"

# 4. Exports for the checker.
opp_scavetool export -o "$OUT/runs.csv" -F CSV-R "$OUT"/runs/*/*.sca "$OUT"/runs/*/*.vec >/dev/null
opp_scavetool export -o "$OUT/seeds.csv" -F CSV-R "$OUT"/seeds/*/*.sca "$OUT"/seeds/*/*.vec >/dev/null
python3 "$HERE/check/check_s0.py" "$OUT" | tee "$OUT/check.txt"
