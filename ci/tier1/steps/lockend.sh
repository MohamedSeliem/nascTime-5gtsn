#!/usr/bin/env bash
# C-2 final lock gate over every opp_env session log.
. "$(dirname "$0")/../lib/common.sh"
logs=()
for l in realise probe probe-runtime-before probe-runtime-after build-omnetpp build-inet build-simu5g build-nasctime validate wrapper-suite; do
  [[ -f "$EV/$l.log" ]] && logs+=("$EV/$l.log")
done
"$T1_LIB/lockcheck.sh" final "${logs[@]}"
