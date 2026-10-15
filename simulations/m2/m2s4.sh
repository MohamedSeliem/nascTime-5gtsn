#!/bin/bash
# M2-S4: link-local gPTP Pdelay termination at the translators' TSN ports
# (migration/m2-s4-design.md rev. 2). Builds libnasctime_m2, runs every M2-S4 config
# (simulations/m2/omnetpp.ini) and the checker. Needs the M2-S1 raw runs in
# results/M2-S1/runs (./m2s1.sh) for gate G0 and the end-to-end baseline; the checker
# verifies that the M2-S1 PCAP and logs it reads are hash-identical to
# results/M2-S1/raw-outputs.sha256. Requires OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0
# (built); OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT set (or the defaults below).
# Output: results/M2-S4/ (check.txt, env.txt, raw-outputs.sha256, tables; raw runs under
# runs/, not committed).
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
JOBS=${JOBS:-2}
OUT=$HERE/results/M2-S4
[ -d "$HERE/results/M2-S1/runs" ] || { echo "ERROR: results/M2-S1/runs missing; run ./m2s1.sh first" >&2; exit 1; }
rm -rf "$OUT/runs"
mkdir -p "$OUT/runs"
"$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/runs/build.log" 2>&1 \
  || { echo "ERROR: build failed, see $OUT/runs/build.log" >&2; exit 1; }
source "$OMNETPP_ROOT/setenv" -f >/dev/null
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 simulations/m2 src/nasctime ':!simulations/m1/results' ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1, simulations/m2 or src/nasctime)')"
  echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -d' ' -f1)"
  echo "python: $(python3 --version 2>&1)"
  echo "os: $(uname -srm)"
} > "$OUT/env.txt"

run() {  # $1 config, $2 runs
  (cd "$HERE" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$OUT/runs/$1" \
     --cmdenv-express-mode=true > "$OUT/runs/run-$1.log" 2>&1) \
  || { echo "ERROR: $1 failed, see $OUT/runs/run-$1.log" >&2; return 1; }
}
export -f run
export HERE NASCTIME SIMU5G_ROOT OUT
{
  printf '%s\n' "M2S4-load 0" "M2S4-load-harq16 0" "M2S4-passive-load 0" "M2S4-passive-load-harq16 0" \
    "M2S4 0..9" "M2S4-passive 0..9" "M2S4-frag 0" "M2S4-passive-frag 0" "M2S4-ctl-nopdelay 0..9" "M2S4-ctl-nopdelay-load 0"
  for c in fault-dropResp fault-dupResp fault-dupRespLate fault-dupFU fault-malformed \
           nc-pairing nc-t4end nc-t3end nc-t1t4end nc-units nc-nohalf nc-noturn nc-noTimeout nc-acceptLast nc-republishLate; do
    echo "M2S4-$c 0"; done
  for c in "" -73 -asym -wrap -F1 -F2 -F3 -F3L -F4 -F5 -F6 -F7 -F8 -F9a -F9b -F9c -F9d -F10 -F11 -F12 -nc-previousSeq; do
    echo "M2S4U$c 0"; done
} | xargs -P "$JOBS" -L 1 bash -c 'run "$0" "$1"'

python3 "$HERE/check/check_m2s4.py" "$OUT" "$HERE/results/M2-S1/runs" "$HERE/results/M2-S1/raw-outputs.sha256" | tee "$OUT/check.txt"
(cd "$OUT/runs" && find . -type f \( -name '*.sca' -o -name '*.vec' -o -name '*.pcapng' -o -name '*.csv' \) \
   ! -name '*.vci' | LC_ALL=C sort | xargs sha256sum) > "$OUT/raw-outputs.sha256"
