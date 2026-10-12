#!/bin/bash
# M1-S2 addendum: phase-offset test of the slot-alignment explanation of S2's +1090 ns.
# See check/s2_phase.py for the method. Uses Config S1 and Config S2 unchanged; the
# phase is applied as a command-line override of initialProductionOffset.
# Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0; OMNETPP_ROOT, INET_ROOT,
# SIMU5G_ROOT set (or the defaults below).
# Output: simulations/m1/results/S2-phase/
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
OUT=$HERE/results/S2-phase
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
rm -rf "$OUT/runs" && mkdir -p "$OUT/runs"
export HERE NASCTIME INET_ROOT SIMU5G_ROOT
python3 "$HERE/check/s2_phase.py" run "$OUT/runs"
cp "$OUT/runs/phase.json" "$OUT/phase.json"
python3 "$HERE/check/s2_phase.py" check "$OUT/runs" | tee "$OUT/check.txt"
