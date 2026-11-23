#!/usr/bin/env bash
# Gate-A approvals: only statements signed with the maintainer's key, unaltered, APPROVED, and (A-4 / A-5) matching the
# approved record are accepted (runbook rev. 4, 3 and 14). TEST ONLY: a throwaway key stands in for the maintainer's.
. "$(dirname "$0")/lib.sh"
B=$(mktemp -d "${TMPDIR:-/tmp}/wpa1-appr.XXXXXX"); Z=$B/z; A=$Z/approvals; mkdir -p "$A" "$Z/records"
test_key "$B/k"; cp "$B/k/allowed_signers" "$A/"; test_key "$B/other"
D=0123456789abcdef0123456789abcdef01234567
stmt() { (export Z APPROVALS="$A"; . "$S_DIR/common.sh"; stmt_ok "$1" "$2") > /dev/null; }
gate() { (export Z APPROVALS="$A"; . "$S_DIR/common.sh"; STAGE=test; "$@") > /dev/null 2>&1; }
fresh_a() { gate_a_statement "$A/gate-a.txt" "$D" "$(printf r | sha256sum | cut -d' ' -f1)" a.tar b.tar c.tar; sign "$B/k/test-key" "$A/gate-a.txt"; }

fresh_a
check "AP-1 valid signed gate-A statement accepted" 'stmt gate-a.txt A'
check "AP-1 gate_a accepts it" 'gate gate_a'
echo "executor=someone else" >> "$A/gate-a.txt"
check "AP-2 statement altered after signing refused" '! stmt gate-a.txt A'
fresh_a; sign "$B/other/test-key" "$A/gate-a.txt"
check "AP-3 statement signed by a key not in allowed_signers refused" '! stmt gate-a.txt A'
fresh_a; rm -f "$A/gate-a.txt.sig"; ssh-keygen -q -Y sign -f "$B/k/test-key" -n file "$A/gate-a.txt" >/dev/null 2>&1
check "AP-4 signature in another namespace refused" '! stmt gate-a.txt A'
fresh_a; rm -f "$A/gate-a.txt.sig"
check "AP-5 unsigned statement (a populated text file) refused" '! stmt gate-a.txt A'
fresh_a; sed -i 's/^decision=APPROVED$/decision=REJECTED/' "$A/gate-a.txt"; sign "$B/k/test-key" "$A/gate-a.txt"
check "AP-6 signed but not APPROVED refused" '! stmt gate-a.txt A'
fresh_a; echo "docs_commit=$D" >> "$A/gate-a.txt"; sign "$B/k/test-key" "$A/gate-a.txt"
check "AP-7 duplicate key refused" '! stmt gate-a.txt A'
fresh_a; check "AP-8 statement for another gate refused" '! stmt gate-a.txt A-4'
fresh_a; echo "=x" >> "$A/gate-a.txt"; sign "$B/k/test-key" "$A/gate-a.txt"
check "AP-9 malformed line refused" '! stmt gate-a.txt A'
fresh_a; sed -i "s/^reviewed_commit=.*/reviewed_commit=$D/" "$A/gate-a.txt"; sign "$B/k/test-key" "$A/gate-a.txt"
check "AP-10 signed statement for another reviewed commit refused by gate_a" '! gate gate_a'
fresh_a; sed -i 's/^vn1_sha256=b/vn1_sha256=c/' "$A/gate-a.txt"; sign "$B/k/test-key" "$A/gate-a.txt"
check "AP-11 signed statement with another expectation hash refused by gate_a" '! gate gate_a'
fresh_a; mv "$A/allowed_signers" "$B/as.bak"
check "AP-12 no allowed_signers: refused" '! stmt gate-a.txt A'
mv "$B/as.bak" "$A/allowed_signers"

fresh_a; echo "DR-13 record TEST ONLY" > "$Z/records/dr13.md"; echo "G0-RO record TEST ONLY" > "$Z/records/g0ro.md"
subject_statement "$A/a4-dr13.txt" A-4 "$D" dr13.md "$Z/records"; sign "$B/k/test-key" "$A/a4-dr13.txt"
subject_statement "$A/a5-g0ro.txt" A-5 "$D" g0ro.md "$Z/records" "$(printf i | sha256sum | cut -d' ' -f1)"; sign "$B/k/test-key" "$A/a5-g0ro.txt"
check "AP-13 valid A-4 / A-5 statements with their records accepted" 'stmt a4-dr13.txt A-4 && stmt a5-g0ro.txt A-5 && gate gate_a45'
echo "edited" >> "$Z/records/dr13.md"
check "AP-14 approved record changed after approval refused" '! stmt a4-dr13.txt A-4'
rm "$Z/records/dr13.md"
check "AP-15 approved record absent refused" '! stmt a4-dr13.txt A-4'
echo "DR-13 record TEST ONLY" > "$Z/records/dr13.md"
subject_statement "$A/a4-dr13.txt" A-4 "fedcba9876543210fedcba9876543210fedcba98" dr13.md "$Z/records"; sign "$B/k/test-key" "$A/a4-dr13.txt"
check "AP-16 A-4 approving another procedure commit refused by gate_a45" '! gate gate_a45'
summary test-approvals
