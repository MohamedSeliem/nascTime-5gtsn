#!/usr/bin/env bash
# E-6: the experiment's existing, reviewed oracle, unchanged, on the sealed raw outputs:
#   e3a: U1 of check_m2s4.py (eval_unit("M2S4U", L_REF));  e3b: check_m2s5.rows_5gs(Run(RUNS, "M2S5", 0), None, exp_missing=0)
. "$(dirname "$0")/../lib/t2common.sh"
"$T1_LIB/guard-alive.sh" "oracle"
case "$ORACLE" in
  u1) /usr/bin/python3 -I -B "$T2PY/u1_oracle.py" "$RAW" "$REPO/simulations/m2/check" "$REC/oracle.json" "$REC/oracle.txt" \
        "$U1_REF_D_PS" "$U1_MIN_EXCHANGES" ;;
  m2s5) /usr/bin/python3 -I -B "$T2PY/m2s5_oracle.py" "$RAW" "$REPO/simulations/m2/check" "$REC/oracle.json" "$REC/oracle.txt" ;;
  *) echo "::error::unknown oracle '$ORACLE'"; exit 1 ;;
esac
