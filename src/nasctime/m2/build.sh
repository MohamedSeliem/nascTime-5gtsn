#!/bin/bash
# Builds libnasctime_m2 (M2 code only; depends on INET 4.7.0, not on Simu5G, not on the
# legacy nascTime library). Requires OMNETPP_ROOT and INET_ROOT (or the defaults below);
# INET must be built (release: libINET.so in $INET_ROOT/src).
# Result: src/nasctime/m2/libnasctime_m2.so ; load it with
#   opp_run -l <nascTime>/src/nasctime/m2/nasctime_m2 ...
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
source "$OMNETPP_ROOT/setenv" -f >/dev/null
cd "$HERE"
opp_makemake -f --make-so -o nasctime_m2 -O out \
    -I"$INET_ROOT/src" -L"$INET_ROOT/src" -lINET -DINET_IMPORT >/dev/null
make MODE=release -j"$(nproc)"
