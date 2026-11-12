#!/bin/bash
# M2-R181b explicit M2-S4 -> M2-S5 dependency gate (plan §4.3). NOT a runner change and NOT a relabelling: the historical
# M2-S4 check.txt keeps its R2b FAIL, and m2s4.sh's fail-stop (no raw-outputs.sha256 after a failing check) is
# recorded as such. This gate decides whether M2-S5 may read these M2-S4 runs, from evidence only:
#   G1  M2-S4/check.txt exists; every row PASS except exactly R2b (FAIL);
#   G2  r2b-v-check.txt (check_v181b_m2.py r2b on THESE runs) is PASS, and its mutation control FAILs;
#   G3  the hash file is computed from THESE raw outputs by the runner's own command (m2s4.sh, last line), never edited.
# If all hold: writes M2-S4/raw-outputs.sha256 and M2-S4/DEPENDENCY-GATE.txt; otherwise writes only the gate record
# with the failing condition and exits 1 (M2-S5 is then not run).
set -o pipefail
S4=$1   # <root>/m2/M2-S4
REC=$S4/DEPENDENCY-GATE.txt
fail() { { echo "M2-R181b dependency gate M2-S4 -> M2-S5: CLOSED"; echo "reason: $1"; date -u +%FT%TZ; } > "$REC"; echo "GATE CLOSED: $1"; exit 1; }
[ -f "$S4/check.txt" ] || fail "G1: M2-S4/check.txt missing"
[ ! -e "$S4/raw-outputs.sha256" ] || fail "raw-outputs.sha256 already exists (written by m2s4.sh?); nothing to decide"
nfail=$(grep -c '^FAIL' "$S4/check.txt"); npass=$(grep -c '^PASS' "$S4/check.txt")
r2b=$(grep -c '^FAIL  R2b ' "$S4/check.txt")
[ "$nfail" = 1 ] && [ "$r2b" = 1 ] || fail "G1: M2-S4 check has $nfail FAIL rows (R2b among them: $r2b); only R2b may fail"
grep -q '^OVERALL: PASS' "$S4/r2b-v-check.txt" 2>/dev/null || fail "G2: R2b-v not PASS on these runs"
grep -q '^OVERALL: FAIL' "$S4/r2b-v-mutation-check.txt" 2>/dev/null || fail "G2: R2b-v mutation control did not FAIL"
# G3: the runner's own hash command (m2s4.sh, last two lines), unchanged
(cd "$S4/runs" && find . -type f \( -name '*.sca' -o -name '*.vec' -o -name '*.pcapng' -o -name '*.csv' \) \
   ! -name '*.vci' | LC_ALL=C sort | xargs sha256sum) > "$S4/raw-outputs.sha256"
{
  echo "M2-R181b dependency gate M2-S4 -> M2-S5: OPEN ($(date -u +%FT%TZ))"
  echo "G1: M2-S4/check.txt $npass PASS, $nfail FAIL (R2b only); historical verdict unchanged: FAIL"
  echo "G2: $(grep -m1 '^PASS\|^FAIL' "$S4/r2b-v-check.txt" | cut -c1-120); mutation control: $(grep '^OVERALL' "$S4/r2b-v-mutation-check.txt")"
  echo "G3: raw-outputs.sha256 computed by the m2s4.sh hash command over these runs: $(wc -l < "$S4/raw-outputs.sha256") files, sha256 $(sha256sum "$S4/raw-outputs.sha256" | cut -c1-16)"
  echo "M2-S5 and M2-S6 results read through this gate are conditional on the acceptance of R2b-v (review)."
} > "$REC"
cat "$REC"
