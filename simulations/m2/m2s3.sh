#!/bin/bash
# M2-S3: offline gPTP correction oracle (migration/m2-s2-design.md rev. 2, section 6) on the
# recorded M2-S1 runs. Runs no simulation and modifies no packet. Builds the INET serializer
# probe (check/inet_probe, links the unmodified libINET), runs it, then runs the oracle.
# Requires the M2-S1 raw runs in results/M2-S1/runs (regenerate with ./m2s1.sh; the oracle
# checks that every PCAP and port log it reads is hash-identical to results/M2-S1/raw-outputs.sha256).
# Requires OMNeT++ 6.4.0 / INET 4.7.0 (built); OMNETPP_ROOT, INET_ROOT set (or the defaults below).
# Output: results/M2-S3/ (check.txt, census.txt, syncs.csv, slave-model.txt, vec.sha256,
# serializer-probe.txt, env.txt).
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
RUNS=$HERE/results/M2-S1/runs
OUT=$HERE/results/M2-S3
[ -d "$RUNS" ] || { echo "ERROR: $RUNS missing; run ./m2s1.sh first" >&2; exit 1; }
mkdir -p "$OUT"
"$HERE/check/inet_probe/build.sh" > "$OUT/probe-build.log" 2>&1 \
  || { echo "ERROR: probe build failed, see $OUT/probe-build.log" >&2; exit 1; }
rm -f "$OUT/probe-build.log"
"$HERE/check/inet_probe/gptp_serializer_probe" > "$OUT/serializer-probe.txt"
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "libINET_sha256: $(sha256sum "$INET_ROOT/src/libINET.so" | cut -d' ' -f1)"
  echo "python: $(python3 --version 2>&1)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m2 src/nasctime ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m2 or src/nasctime)')"
  echo "m2s1_runs_env: $(grep -h '^nascTime_commit\|^date_utc' "$HERE/results/M2-S1/env.txt" | tr '\n' ' ')"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"
python3 "$HERE/check/oracle_m2s3.py" "$RUNS" "$HERE/results/M2-S1/raw-outputs.sha256" \
  "$OUT/serializer-probe.txt" "$OUT" | tee "$OUT/check.txt"
