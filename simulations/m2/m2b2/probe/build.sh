#!/bin/bash
# M2B-2 TEST-ONLY: builds the TtGateClockProbe library (step 148) into an output directory OUTSIDE the repository.
#   probe/build.sh <release|debug> <outdir>     ->  <outdir>/libm2b2probe.so (release) or libm2b2probe_dbg.so (debug)
# Requires OMNETPP_ROOT and INET_ROOT (INET built in the same mode). Not part of libnasctime_m2 or of any accepted
# configuration.
set -eo pipefail
MODE=${1:?release|debug}; OUT=${2:?output directory}
HERE=$(cd "$(dirname "$0")" && pwd)
source "$OMNETPP_ROOT/setenv" -f >/dev/null
mkdir -p "$OUT"
cp "$HERE/TtGateClockProbe.cc" "$OUT/"
cd "$OUT"
opp_makemake -f --make-so -o m2b2probe -O out -I"$INET_ROOT/src" -L"$INET_ROOT/src" -lINET\$\(D\) -DINET_IMPORT >/dev/null
make MODE="$MODE" -j"$(nproc)" >/dev/null
