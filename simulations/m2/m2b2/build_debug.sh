#!/bin/bash
# M2B-2 step 148 (C2), TEST-ONLY: builds the DEBUG variant of libnasctime_m2 (src/nasctime/m2/libnasctime_m2_dbg.so,
# assertions on, linked with INET_dbg) for check/test_m2b2_ttgateclock.py with M2B2_MODE=debug. Requires OMNETPP_ROOT
# and INET_ROOT with OMNeT++ and INET built in debug mode (make MODE=debug). The release library is built by
# src/nasctime/m2/build.sh (unchanged); afterwards, re-run it to restore its Makefile.
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
source "$OMNETPP_ROOT/setenv" -f >/dev/null
cd "$HERE/../../../src/nasctime/m2"
opp_makemake -f --make-so -o nasctime_m2 -O out -I"$INET_ROOT/src" -L"$INET_ROOT/src" -lINET\$\(D\) -DINET_IMPORT >/dev/null
make MODE=debug -j"$(nproc)"
