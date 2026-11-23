#!/usr/bin/env bash
# WP-A1: G0-RO environment-equivalence run (runbook revision 3, section 4.3). Runs in the 'mounted' profile of the
# container image the record will cover. It re-runs, unchanged and with the D-2 invocation, accepted read-only
# evaluators whose D-2 results are recorded, and compares verdicts and exact counts (g0ro_compare.py). No WP-A1 code
# is used for the comparison: the 11 suites (G0RO-P) are a precondition only, never equivalence evidence by themselves.
# Output: $Z/g0ro/ (fresh). Exit 0 only if G0RO-P and every G0RO-V / G0RO-C item pass.
STAGE=g0ro-run
. "$(dirname "$0")/common.sh"
load_vars
gate_a                                                        # an authorised executor, the approved procedure
ro_path "$R"; ro_path "$X"
G="$Z/g0ro"; [ ! -e "$G" ] || stop "$G exists (single attempt)"; mkdir "$G" "$G/p0"
note() { echo "$*" | tee -a "$G/runs.txt"; }

# G0RO-I identity (recorded, compared in the record against the G0 record's D-2 column; not a pass criterion)
{ python3 -c 'import sys; print("python", sys.version.replace("\n", " "))'; echo "image sha256:${IMG_DIGEST:-unknown}"
  uname -srm; grep PRETTY_NAME /etc/os-release; echo "simu5g $(git -C "$SIMU5G_ROOT" rev-parse HEAD)"; echo "nascTime $C"; } > "$G/identity.txt"

# G0RO-P precondition: the 11 suites with their exact lines (same checks as P-0)
p0() { local t=$1 exp=$2 mode=$3 out="$G/p0/$1.out" rc
  if [ "$mode" = isolated ]; then (cd "$Z" && $PY "$CHK/$t") >"$out" 2>"$G/p0/$t.err"; rc=$?
  else (cd "$CHK" && python3 -B "$t") >"$out" 2>"$G/p0/$t.err"; rc=$?; fi
  [ "$rc" -eq 0 ] && [ -s "$out" ] && [ "$(tail -n 1 "$out")" = "$exp" ] || stop "G0RO-P $t (rc $rc)"; note "G0RO-P PASS $t"; }
p0 test_m2s72_e0vn21.py      "WP-A1 e0vn21 tests: 52 / 52 PASS, 0 FAIL" isolated
p0 test_m2s72_a2.py          "A-2 tests: 18 / 18 PASS" plain
p0 test_m2s72_a2probe.py     "A-2 probe tests: 11 / 11 PASS" plain
p0 test_m2s72_a2v1.py        "10 / 10 PASS" plain
p0 test_m2s72_gen.py         "generator negative tests: 67 PASS, 0 FAIL" plain
p0 test_m2s72s5.py           "S5-1 tests: 38 / 38 PASS" plain
p0 test_m2s72s5_2.py         "S5-2 tests: 28 / 28 PASS" plain
p0 test_m2s72s5_n2.py        "S5 N = 2 tests: 19 / 19 PASS" plain
p0 test_m2s72s5_smoke.py     "S5 smoke contract tests: 9 / 9 PASS" plain
p0 test_m2s72_a21.py         "A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL" plain
p0 test_m2s72_a21_fixture.py "A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL" plain

# G0RO-1: A2-V1-S1, the D-2 commands of M2-S7.2a-a21-s1-protocol.md (E-1, E-2, E-3), unchanged code (d920125 = C)
RUNS="$R/a2-nack-1/runs"; CFG=M2S72-E0vN-q0-one0-n2-f1_A2V1
(cd "$CHK" && python3 -B check_m2s72_a21.py a21 "$RUNS" "$CFG" "$G/s1-full" --contract full) > "$G/s1-full.console.txt" 2>&1; echo $? > "$G/s1-full.rc"
(cd "$CHK" && python3 -B check_m2s72_a21.py a21 "$RUNS" "$CFG" "$G/s1-f1di" --contract f1d-i) > "$G/s1-f1di.console.txt" 2>&1; echo $? > "$G/s1-f1di.rc"
(cd "$CHK" && python3 -B check_m2s72_a21.py a21-controls "$RUNS" "$CFG" "$G/s1-controls") > "$G/s1-controls.console.txt" 2>&1; echo $? > "$G/s1-controls.rc"
# G0RO-2: the UE-side reference XA on the N = 1 and N = 2 smokes, the D-2 command of M2-S7.2a-s5-n2-protocol.md
N1="$R/s5-smoke-1/m2/M2-S7.2a-s5smoke/runs"; N2="$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2/runs"
(cd "$CHK/.." && python3 -B check/check_m2s72_s5n2.py xa "$N1" M2S72-E0v-q0-f1 "$G/xa-n1") > "$G/xa-n1.console.txt" 2>&1; echo $? > "$G/xa-n1.rc"
(cd "$CHK/.." && python3 -B check/check_m2s72_s5n2.py xa "$N2" M2S72-E0vN-q0-one0-n2-f1 "$G/xa-n2") > "$G/xa-n2.console.txt" 2>&1; echo $? > "$G/xa-n2.rc"

python3 -I -B "$Z/scripts/g0ro_compare.py" "$G" > "$G/compare.txt" 2>&1; rc=$?
cat "$G/compare.txt"
(cd "$G" && find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > "$G/SHA256SUMS"
echo "G0RO SHA256SUMS sha256 $(sha256sum "$G/SHA256SUMS" | cut -d' ' -f1)"
[ "$rc" -eq 0 ] || stop "G0-RO comparison: NOT EQUIVALENT (see $G/compare.txt)"
echo "G0-RO: verdict and count equivalence with D-2 on every compared item (for the maintainer's approval)"
exit 0
