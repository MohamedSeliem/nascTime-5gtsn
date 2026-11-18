#!/usr/bin/env bash
# Final lock gate including the tier-2 session logs (tier-1's own final gate runs separately and unchanged).
. "$(dirname "$0")/../lib/t2common.sh"
logs=()
for l in t2-runconfig t2-sim; do [[ -f "$EV/$l.log" ]] && logs+=("$EV/$l.log"); done
"$T1_LIB/lockcheck.sh" final-t2 "${logs[@]}"
