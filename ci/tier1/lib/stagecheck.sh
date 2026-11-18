#!/usr/bin/env bash
# usage: stagecheck.sh <stage>. Fail-fast existence check of the stage's principal release outputs.
set -u
case "$1" in
  omnetpp) files="$WS/omnetpp-6.5.0/bin/opp_run $WS/omnetpp-6.5.0/lib/liboppsim.so $WS/omnetpp-6.5.0/lib/liboppenvir.so $WS/omnetpp-6.5.0/lib/liboppcmdenv.so" ;;
  inet) files="$WS/inet-4.7.0/src/libINET.so" ;;
  simu5g) files="$WS/simu5g-1.8.1/src/libsimu5g.so" ;;
  nasctime) files="$REPO/src/nasctime/m2/libnasctime_m2.so" ;;
  *) echo "unknown stage $1"; exit 2 ;;
esac
rc=0
for f in $files; do
  if [[ -f "$f" ]]; then echo "$1 output present: ${f##*/} ($(stat -c %s "$f") B)"; else echo "::error::$1 output missing: ${f##*/}"; rc=1; fi
done
echo "$1 tree_bytes_after_build: $(du -sb "$( [[ $1 == nasctime ]] && echo "$REPO/src/nasctime/m2" || echo "$WS/$(cd "$WS" && ls -d "$1"-*)" )" | cut -f1)" >> "$EV/sizes.txt"
exit "$rc"
