#!/bin/bash
# U1: the upstream-example reproduction (results/M2-S7.2a-upstream-repro, unchanged) on unmodified Simu5G 1.8.1.
# Only the include path differs from repro.ini. Absolute result dir (the 1.8.0 run's relative one landed in the
# upstream tree). Runs in a scratch copy of this directory; outputs copied back.
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
S=/root/stack/simu5g-1.8.1; I=/root/stack/inet-4.7.0
source /root/stack/omnetpp-6.4.0/setenv -f >/dev/null
W=$(mktemp -d); trap 'rm -rf "$W"' EXIT
cp "$HERE/repro-1.8.1.ini" "$HERE/analyse.py" "$W/"; cd "$W"
for c in Repro-UL-QOSPF Repro-UL-MAXCI; do
  opp_run -l $S/src/simu5g -n $S/src:$S/simulations:$I/src -u Cmdenv -f repro-1.8.1.ini -c $c -r 0 \
    --result-dir="$W/results/simu5g-1.8.1" --cmdenv-express-mode=false --fingerprint=0000-0000/tplx 2>&1 \
    | gzip > "results-simu5g-1.8.1-$c.log.gz"
  zcat "results-simu5g-1.8.1-$c.log.gz" | grep -q "<!> Error" && { echo "ERROR in $c"; zcat "results-simu5g-1.8.1-$c.log.gz" | grep "<!>"; exit 1; }
done
python3 -I analyse.py | tee "$HERE/analysis.txt"
find results -name "*.sca" -o -name "*.vec" | sort | xargs sha256sum > "$HERE/raw-outputs.sha256"; sha256sum results-*.log.gz >> "$HERE/raw-outputs.sha256"
echo "libsimu5g_sha256 $(sha256sum $S/src/libsimu5g.so | cut -d' ' -f1)" > "$HERE/stack.txt"
