#!/bin/bash
# M2-R181c explicit M2-S5 -> M2-S6 dependency gate (plan §3 step 7). The historical M2-S5 check.txt keeps its verdict;
# m2s5.sh's fail-stop (no raw-outputs.sha256 after a failing check) is recorded as such. Opens only if:
#   G1 historical check.txt fails only {C8, N-tseSlot, N-noFcsNw, N-noStrip, N-fwdPdelay}
#   G2 check-v181c.txt (check_m2s5 with C8-v) fails only {N-tseSlot, N-noFcsNw} (historical, superseded)
#   G3 controls-v181c.txt OVERALL PASS (N-tseSlot-v, N-noFcsNw-v)
#   G4 c8demo-v181c.txt OVERALL PASS
# then writes raw-outputs.sha256 with m2s5.sh's own hash command over these runs (never edited) and DEPENDENCY-GATE.txt.
set -o pipefail
S5=$1
REC=$S5/DEPENDENCY-GATE.txt
fail() { { echo "M2-R181c dependency gate M2-S5 -> M2-S6: CLOSED"; echo "reason: $1"; date -u +%FT%TZ; } > "$REC"; echo "GATE CLOSED: $1"; exit 1; }
[ ! -e "$S5/raw-outputs.sha256" ] || fail "raw-outputs.sha256 already exists"
fails() { grep '^FAIL  ' "$1" | sed 's/^FAIL  //; s/ .*//' | LC_ALL=C sort | tr '\n' ' ' | sed 's/ $//'; }
g1=$(fails "$S5/check.txt"); g2=$(fails "$S5/check-v181c.txt")
[ "$g1" = "C8 N-fwdPdelay N-noFcsNw N-noStrip N-tseSlot" ] || fail "G1: historical failures [$g1]"
[ "$g2" = "N-noFcsNw N-tseSlot" ] || fail "G2: C8-v check failures [$g2]"
grep -q '^OVERALL: PASS' "$S5/controls-v181c.txt" || fail "G3: replacement controls not PASS"
grep -q '^OVERALL: PASS' "$S5/c8demo-v181c.txt" || fail "G4: C8-v demonstration not PASS"
(cd "$S5/runs" && find . -type f \( -name '*.sca' -o -name '*.vec' -o -name '*.pcapng' -o -name '*.csv' \) \
   ! -name '*.vci' | LC_ALL=C sort | xargs sha256sum) > "$S5/raw-outputs.sha256"
{
  echo "M2-R181c dependency gate M2-S5 -> M2-S6: OPEN ($(date -u +%FT%TZ))"
  echo "G1: historical M2-S5 check fails only [$g1] (verdict unchanged: $(grep '^OVERALL' "$S5/check.txt"))"
  echo "G2: check_m2s5 with C8-v fails only [$g2] (historical controls superseded by N-tseSlot-v / N-noFcsNw-v); $(grep '^OVERALL' "$S5/check-v181c.txt")"
  echo "G3: $(grep '^OVERALL' "$S5/controls-v181c.txt") (replacement controls)"
  echo "G4: $(grep '^OVERALL' "$S5/c8demo-v181c.txt") (C8-v unmodified PASS, mutations FAIL)"
  echo "raw-outputs.sha256 by the m2s5.sh hash command over these runs: $(wc -l < "$S5/raw-outputs.sha256") files, sha256 $(sha256sum "$S5/raw-outputs.sha256" | cut -c1-16)"
} > "$REC"
cat "$REC"
