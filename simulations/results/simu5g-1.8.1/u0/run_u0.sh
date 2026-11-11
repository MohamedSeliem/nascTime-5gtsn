#!/bin/bash
# U0: Simu5G 1.8.1's seven new module tests, run on the unmodified build from a scratch copy of tests/module (the
# upstream tree gets no work/ directory).
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
export SIMU5G_ROOT=/root/stack/simu5g-1.8.1 INET_ROOT=/root/stack/inet-4.7.0
source /root/stack/omnetpp-6.4.0/setenv -f >/dev/null
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp -r "$SIMU5G_ROOT/tests/module" "$W/"; cd "$W/module"
T="SaturatedNrTrafficNoMacLoss.test FewHarqProcessesLteDlNoMacLoss.test FewHarqProcessesLteUlNoMacLoss.test SlowHarqFeedbackNrUlGrants.test DlCappedGrantKeepsBacklog.test DlGrantCoversEverySduHeader.test EthernetSessionFlowMeasurement.test"
./runtest $T > "$HERE/runtest.log" 2>&1; echo "runtest rc=$?" >> "$HERE/runtest.log"
grep -E "PASS|FAIL|ERROR|Aggregate|tests:" "$HERE/runtest.log" | tail -20
