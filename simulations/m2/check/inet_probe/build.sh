#!/bin/bash
# Builds gptp_serializer_probe against the unmodified INET 4.7.0 library (release build).
# Requires OMNETPP_ROOT and INET_ROOT (or the defaults below). Output: ./gptp_serializer_probe
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
source "$OMNETPP_ROOT/setenv" -f >/dev/null
CXX=$(opp_configfilepath >/dev/null 2>&1; grep -m1 '^CXX *=' "$OMNETPP_ROOT/Makefile.inc" | sed 's/^CXX *= *//')
${CXX:-g++} -std=c++17 -O2 -DINET_IMPORT -I"$INET_ROOT/src" -I"$OMNETPP_ROOT/include" \
  "$HERE/gptp_serializer_probe.cc" -o "$HERE/gptp_serializer_probe" \
  -L"$INET_ROOT/src" -lINET -L"$OMNETPP_ROOT/lib" -loppenvir -loppsim -loppcommon \
  -Wl,-rpath,"$INET_ROOT/src" -Wl,-rpath,"$OMNETPP_ROOT/lib"
