#!/usr/bin/env bash
# usage: bash build-m2.sh <repo> <workspace>. Runs inside the opp_env session. Verifies that
# src/nasctime/m2/build.sh will use the freshly installed stack (never its legacy fallback defaults), then
# runs it unchanged. The legacy top-level make is never invoked.
set -euo pipefail
REPO=$1; WSD=$2
bad() { echo "build-m2 precondition failed: $*"; exit 3; }
[[ "${OMNETPP_ROOT:-}" == "$WSD/omnetpp-6.5.0" ]] || bad "OMNETPP_ROOT=${OMNETPP_ROOT:-unset}"
[[ "${INET_ROOT:-}" == "$WSD/inet-4.7.0" ]] || bad "INET_ROOT=${INET_ROOT:-unset}"
[[ "${SIMU5G_ROOT:-}" == "$WSD/simu5g-1.8.1" ]] || bad "SIMU5G_ROOT=${SIMU5G_ROOT:-unset}"
[[ "${OMNETPP_VERSION:-}" == 6.5.0 && "${INET_VERSION:-}" == 4.7.0 && "${SIMU5G_VERSION:-}" == 1.8.1 ]] \
  || bad "opp_env project versions ${OMNETPP_VERSION:-?}/${INET_VERSION:-?}/${SIMU5G_VERSION:-?}"
[[ "$(cat "$OMNETPP_ROOT/Version")" == omnetpp-6.5.0 ]] || bad "OMNeT++ Version file"
[[ "$(cat "$SIMU5G_ROOT/Version")" == 1.8.1 ]] || bad "Simu5G Version file"
[[ -f "$INET_ROOT/src/libINET.so" ]] || bad "libINET.so missing"
[[ -f "$OMNETPP_ROOT/lib/liboppsim.so" ]] || bad "liboppsim.so missing"
S="$REPO/src/nasctime/m2/build.sh"
# build.sh only falls back to /root/stack/... when the variables are unset; require that exact form.
grep -qxF 'OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}' "$S" || bad "unexpected OMNETPP_ROOT handling in build.sh"
grep -qxF 'INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}' "$S" || bad "unexpected INET_ROOT handling in build.sh"
[[ "$(command -v opp_makemake)" == "$OMNETPP_ROOT/bin/opp_makemake" ]] || bad "opp_makemake not from OMNETPP_ROOT"
echo "build-m2: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT are the workspace trees (OMNeT++ $OMNETPP_VERSION, INET $INET_VERSION, Simu5G $SIMU5G_VERSION)"
export OMNETPP_ROOT INET_ROOT SIMU5G_ROOT
exec bash "$S"
