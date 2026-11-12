#!/bin/bash
# M2-R181c diagnostic: M2S4-load and M2S5-load on accepted 1.8.0 (unmodified), C8-v detail, manifest, delete runs.
set -o pipefail
ROOT=$1; HERE=$(cd "$(dirname "$0")" && pwd); NASCTIME=$(cd "$HERE/../../../.." && pwd); S=$NASCTIME/simulations
SIMU5G_ROOT=/root/stack/simu5g-1.8.0; OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}; INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
[ "$(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -d' ' -f1)" = 203cf231e6605188662769b439e403d832f516d2e08c8a0c5a9e8f55f4305cf6 ] || exit 1
[ -e "$ROOT" ] && { echo "ERROR: $ROOT exists" >&2; exit 1; }
mkdir -p "$ROOT/runs"; LOG=$ROOT/steps.txt
source "$OMNETPP_ROOT/setenv" -f >/dev/null
"$NASCTIME/src/nasctime/m2/build.sh" > "$ROOT/build.log" 2>&1
for c in M2S4-load M2S5-load; do
  (cd "$S/m2" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$c" --repeat=10 -r 0 --result-dir="$ROOT/runs/$c" --cmdenv-express-mode=true > "$ROOT/runs/run-$c.log" 2>&1)
  echo "$c rc=$?" >> "$LOG"
done
python3 "$HERE/diag_c8v_load.py" "$ROOT/runs" > "$ROOT/diag-c8v-load-1.8.0.txt" 2>&1; echo "diag rc=$?" >> "$LOG"
rm -rf "$S/m2/check/__pycache__"
"$HERE/../r181b/manifest.sh" "$ROOT/runs" "$ROOT/runs-manifest" >> "$LOG"
rm -rf "$ROOT/runs"; echo "runs deleted after manifest" >> "$LOG"; cat "$LOG" "$ROOT/diag-c8v-load-1.8.0.txt"
