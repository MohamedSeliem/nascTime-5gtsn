#!/usr/bin/env bash
# E-6: the existing, reviewed U1 oracle of check_m2s4.py (unchanged) on the sealed raw outputs.
. "$(dirname "$0")/../lib/t2common.sh"
"$T1_LIB/guard-alive.sh" "oracle"
/usr/bin/python3 -I -B "$T2PY/u1_oracle.py" "$RAW" "$REPO/simulations/m2/check" "$REC/u1-oracle.json" "$REC/u1-oracle.txt" \
  "$U1_REF_D_PS" "$U1_MIN_EXCHANGES"
