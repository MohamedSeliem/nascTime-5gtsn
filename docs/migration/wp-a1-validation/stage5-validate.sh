#!/usr/bin/env bash
# WP-A1 validation, Stage 5 (runbook revision 3): V-N1, V-N2, V-V1. Every command has exactly the argument vector of
# design 8.2 - 8.4; only the exit-code capture and the stop rules of runbook 8 are added. Runs in the network-less
# evaluation container (X and R read-only).
# Exit: 0 all three completed, every hrq --expect exit 0 (VG-1 candidates); 3 all three completed with at least one
# expectation mismatch (exit 5, a finding); 1 stopped (runbook 8). Finalisation (stage 6) follows in every case.
STAGE=stage5-validate
. "$(dirname "$0")/common.sh"
load_vars
gate_b_go
need_done stage4-mount
ro_path "$R"; ro_path "$X"
[ ! -e "$E/vn1" ] && [ ! -e "$E/vn2" ] && [ ! -e "$E/vv1" ] || stop "a validation directory exists (single attempt)"
S="$E/stage5-summary.txt"
findings=0
note() { echo "$*" | tee -a "$S"; }
finding() { printf '%s\n' "- $1: $2 (reported as found; nothing re-run, adjusted or relabelled)" >> "$E/$1/findings.md"; findings=1; }
hrq_rule() {  # <v> <cfg> <rc>: 0 and the record says ALL EXPECTATIONS MET -> ok; 5 -> finding; anything else -> stop after P-3
  local f="$E/$1/hrq/hrq-$2.expect.txt"
  case "$3" in
    0) [ -f "$f" ] && [ "$(tail -n 1 "$f")" = "ALL EXPECTATIONS MET" ] || { note "$1 hrq rc 0 but $f does not end 'ALL EXPECTATIONS MET'"; return 2; }
       note "$1 hrq rc 0: ALL EXPECTATIONS MET"; return 0 ;;
    5) finding "$1" "hrq --expect exit 5, EXPECTATION MISMATCH; see hrq/hrq-$2.expect.txt"; note "$1 hrq rc 5 (finding)"; return 0 ;;
    *) note "$1 hrq rc $3: refused or evaluation error"; return 2 ;;
  esac
}

# ---- V-N1 (design 8.2) ------------------------------------------------------------------------------------------
N1="$R/s5-smoke-1/m2/M2-S7.2a-s5smoke"
mkdir "$E/vn1" || stop "mkdir vn1"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-before.txt"; rc=$?; note "V-N1 P-1 rc=$rc"
[ "$rc" -eq 0 ] || stop "V-N1 P-1 integrity failed: the run is not evaluated"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/hrq" --expect "$CHK/expect/vn1.expect.json"; hrq=$?; note "V-N1 hrq rc=$hrq"
hrq_rule vn1 M2S72-E0v-q0-f1 "$hrq"; hr=$?
$PY "$CHK/check_m2s72_s5n2.py" xa "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/xa"; rc=$?; note "V-N1 xa rc=$rc"
[ "$rc" -eq 0 ] || finding vn1 "xa exit $rc (non-gating reference)"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-after.txt"; rc=$?; note "V-N1 P-3 rc=$rc"
[ "$rc" -eq 0 ] || stop "V-N1 P-3 integrity failed"
cmp "$E/vn1/integrity-before.txt" "$E/vn1/integrity-after.txt" && note "V-N1 P-3 identical" || stop "V-N1 integrity before / after differ"
[ "$hr" -eq 0 ] || stop "V-N1 hrq rule: stop after P-3"

# ---- V-N2 (design 8.3) ------------------------------------------------------------------------------------------
N2="$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2"
mkdir "$E/vn2" || stop "mkdir vn2"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-before.txt"; rc=$?; note "V-N2 P-1 rc=$rc"
[ "$rc" -eq 0 ] || stop "V-N2 P-1 integrity failed: the run is not evaluated"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/hrq" --expect "$CHK/expect/vn2.expect.json"; hrq=$?; note "V-N2 hrq rc=$hrq"
hrq_rule vn2 M2S72-E0vN-q0-one0-n2-f1 "$hrq"; hr=$?
$PY "$CHK/check_m2s72_s5n2.py" xa "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/xa"; rc=$?; note "V-N2 xa rc=$rc"
[ "$rc" -eq 0 ] || finding vn2 "xa exit $rc (non-gating reference)"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-after.txt"; rc=$?; note "V-N2 P-3 rc=$rc"
[ "$rc" -eq 0 ] || stop "V-N2 P-3 integrity failed"
cmp "$E/vn2/integrity-before.txt" "$E/vn2/integrity-after.txt" && note "V-N2 P-3 identical" || stop "V-N2 integrity before / after differ"
[ "$hr" -eq 0 ] || stop "V-N2 hrq rule: stop after P-3"

# ---- V-V1 (design 8.4) ------------------------------------------------------------------------------------------
SEAL=3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0
FXSHA=cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b
mkdir "$E/vv1" || stop "mkdir vv1"
$PY "$CHK/m2s72_a21_fixture.py" extract --results-root "$R" --seal-sha256 "$SEAL" --out "$E/vv1/fx-before"; rc=$?; note "V-V1 P-1 extract rc=$rc"
[ "$rc" -eq 0 ] || stop "V-V1 P-1 extract failed: the run is not evaluated"
grep -q "^$FXSHA  a2v1-first-chain.log.gz$" "$E/vv1/fx-before/a2v1-first-chain.log.gz.sha256" && note "P-1 reproduces the F3 fixture" \
  || stop "V-V1 P-1 does not reproduce the F3 fixture: the run is not evaluated"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$R/a2-nack-1/runs" M2S72-E0vN-q0-one0-n2-f1_A2V1 "$E/vv1/hrq" --expect "$CHK/expect/vv1.expect.json"; hrq=$?; note "V-V1 hrq rc=$hrq"
hrq_rule vv1 M2S72-E0vN-q0-one0-n2-f1_A2V1 "$hrq"; hr=$?
$PY "$CHK/m2s72_a21_fixture.py" extract --results-root "$R" --seal-sha256 "$SEAL" --out "$E/vv1/fx-after"; rc=$?; note "V-V1 P-3 extract rc=$rc"
[ "$rc" -eq 0 ] || stop "V-V1 P-3 extract failed"
grep -q "^$FXSHA  a2v1-first-chain.log.gz$" "$E/vv1/fx-after/a2v1-first-chain.log.gz.sha256" && note "P-3 reproduces the F3 fixture" \
  || stop "V-V1 P-3 does not reproduce the F3 fixture"
[ "$hr" -eq 0 ] || stop "V-V1 hrq rule: stop after P-3"

done_mark stage5-validate
if [ "$findings" -eq 0 ]; then note "Stage 5: all three completed; every hrq --expect exit 0"; exit 0; fi
note "Stage 5: all three completed WITH FINDINGS (see */findings.md)"; exit 3
