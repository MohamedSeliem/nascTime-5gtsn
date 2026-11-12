#!/bin/bash
# M2-R181c 1.8.0 evidence for C8-v and the replacement controls (plan §3), accepted Simu5G 1.8.0 build, unmodified.
#   run_r181c_ctl180.sh <new root (absolute)>
set -o pipefail
ROOT=$1
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../../../.." && pwd)
S=$NASCTIME/simulations; SIMU5G_ROOT=/root/stack/simu5g-1.8.0
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}; INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
[ "$(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -d' ' -f1)" = 203cf231e6605188662769b439e403d832f516d2e08c8a0c5a9e8f55f4305cf6 ] || exit 1
[ -e "$ROOT" ] && { echo "ERROR: $ROOT exists" >&2; exit 1; }
mkdir -p "$ROOT/runs"; LOG=$ROOT/steps.txt
source "$OMNETPP_ROOT/setenv" -f >/dev/null
"$NASCTIME/src/nasctime/m2/build.sh" > "$ROOT/build.log" 2>&1
for x in "omnetpp.ini M2S4" "omnetpp.ini M2S5" "omnetpp.ini M2S4-load" "omnetpp.ini M2S5-load" "omnetpp.ini M2S5-offset" \
         "m2s5r181c.ini M2S4R-offset" "m2s5r181c.ini M2S5R-nc-tseSlot-load" "m2s5r181c.ini M2S5R-nc-noFcsNw-offset"; do
  set -- $x
  (cd "$S/m2" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f "$1" -c "$2" --repeat=10 -r 0 --result-dir="$ROOT/runs/$2" --cmdenv-express-mode=true > "$ROOT/runs/run-$2.log" 2>&1)
  echo "$2 rc=$?" >> "$LOG"
done
C=$S/m2/check/check_v181c_m2s5.py
python3 "$C" c8demo "$ROOT/runs" "$ROOT/runs" > "$ROOT/c8demo-on-1.8.0.txt" 2>&1; echo "c8demo on 1.8.0: $(grep '^OVERALL' "$ROOT/c8demo-on-1.8.0.txt")" >> "$LOG"
python3 "$C" controls "$ROOT/runs" "$ROOT/runs" "$ROOT/runs" > "$ROOT/controls-on-1.8.0.txt" 2>&1; echo "controls on 1.8.0: $(grep '^OVERALL' "$ROOT/controls-on-1.8.0.txt")" >> "$LOG"
rm -rf "$S/m2/check/__pycache__"
"$HERE/../r181b/manifest.sh" "$ROOT/runs" "$ROOT/runs-manifest" >> "$LOG"
rm -rf "$ROOT/runs"; echo "runs deleted after manifest" >> "$LOG"
cat "$LOG"
