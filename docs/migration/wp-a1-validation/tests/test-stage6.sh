#!/usr/bin/env bash
# Stage 6 finalisation: integrity failures are explicit, preserved and never acceptance-eligible (runbook rev. 4, 14).
# TEST ONLY: synthetic evidence directories; the worktree and Simu5G are real public checkouts.
. "$(dirname "$0")/lib.sh"

# eligible_e <Z>: a synthetic evidence directory that would be acceptance-eligible if every integrity check passes
eligible_e() {
  local E="$1/evidence-wpa1" d
  mkdir -p "$E"/{gate,environment/approvals,release,x2a,vv1/fx-before,vv1/fx-after,vn1,vn2,p0}
  echo "GATE B: GO (B-1 ... B-6 met)" > "$E/gate/gate-b.txt"; echo "stage5-validate complete" > "$E/gate/stage5-validate.done"
  printf 'V-N1 hrq rc 0: ALL EXPECTATIONS MET\nStage 5: all three completed; every hrq --expect exit 0\n' > "$E/stage5-summary.txt"
  for f in identity.txt approvals/gate-a.txt approvals/a4-dr13.txt approvals/a5-g0ro.txt; do echo "TEST ONLY" > "$E/environment/$f"; done
  for f in release/selected.sha256 release/verify-after.txt x2a/method.txt x2a/mount.txt; do echo "TEST ONLY" > "$E/$f"; done
  for d in fx-before fx-after; do echo "fixture TEST ONLY" > "$E/vv1/$d/a2v1-first-chain.log.gz"; (cd "$E/vv1/$d" && sha256sum a2v1-first-chain.log.gz > SHA256SUMS); done
  echo "transcript TEST ONLY" > "$1/console.log"
}
run6() { (cd "$1" && Z="$1" bash "$1/scripts/stage6-finalise.sh" > "$1/stage6.out" 2>&1); echo $?; }
preserved() { local E="$1/evidence-wpa1"
  [ -f "$E/SHA256SUMS.final" ] && (cd "$E" && sha256sum -c --strict --quiet SHA256SUMS.final && sha256sum -c --strict --quiet SHA256SUMS) >/dev/null 2>&1; }
res() { grep -qx "$2" "$1/evidence-wpa1/RESULT.txt"; }

unset S5N_ADAPTER_VALIDATED
z=$(new_z) || exit 2; eligible_e "$z"; rc=$(run6 "$z")
check "S6-1 clean complete run: exit 0" '[ "$rc" = 0 ]'
check "S6-1 integrity PASS, acceptance_eligible YES" 'res "$z" "integrity: PASS" && res "$z" "acceptance_eligible: YES"'
check "S6-1 preserved: SHA256SUMS.final and SHA256SUMS verify" 'preserved "$z"'
check "S6-1 RESULT.txt and nested sums are inventoried" 'grep -q "  ./RESULT.txt$" "$z/evidence-wpa1/SHA256SUMS" && grep -q "  ./vv1/fx-after/SHA256SUMS$" "$z/evidence-wpa1/SHA256SUMS"'
rc=$(run6 "$z"); check "S6-2 a second finalisation is refused (exit 1)" '[ "$rc" = 1 ]'

z=$(new_z) || exit 2; eligible_e "$z"; echo " " >> "$z/wpa1-validate/simulations/m2/check/expect/vn1.expect.json"; rc=$(run6 "$z")
check "S6-3 changed expectation file: exit 4" '[ "$rc" = 4 ]'
check "S6-3 integrity FAILED with I-1, acceptance_eligible NO" 'res "$z" "integrity: FAILED" && grep -q "^integrity_failure: I-1" "$z/evidence-wpa1/RESULT.txt" && res "$z" "acceptance_eligible: NO"'
check "S6-3 failed evidence is preserved" 'preserved "$z"'

z=$(new_z) || exit 2; eligible_e "$z"; echo x > "$z/wpa1-validate/stray-file"; rc=$(run6 "$z")
check "S6-4 dirty worktree (untracked file): exit 4, I-3, not eligible, preserved" \
  '[ "$rc" = 4 ] && grep -q "^integrity_failure: I-3" "$z/evidence-wpa1/RESULT.txt" && res "$z" "acceptance_eligible: NO" && preserved "$z"'

z=$(new_z) || exit 2; eligible_e "$z"; echo "# x" >> "$z/wpa1-validate/simulations/m2/check/m2s72_e0vn21.py"; rc=$(run6 "$z")
check "S6-5 modified tracked evaluator file: exit 4, I-3" '[ "$rc" = 4 ] && grep -q "^integrity_failure: I-3" "$z/evidence-wpa1/RESULT.txt"'

z=$(new_z) || exit 2; eligible_e "$z"; git -C "$z/wpa1-validate" -c advice.detachedHead=false checkout -q "$C_REV^"; rc=$(run6 "$z")
check "S6-6 worktree moved off the reviewed commit: exit 4, I-2" '[ "$rc" = 4 ] && grep -q "^integrity_failure: I-2" "$z/evidence-wpa1/RESULT.txt"'

z=$(new_z) || exit 2; eligible_e "$z"; echo x > "$z/simu5g-1.8.1/stray"; rc=$(run6 "$z")
check "S6-7 dirty Simu5G tree: exit 4, I-4" '[ "$rc" = 4 ] && grep -q "^integrity_failure: I-4" "$z/evidence-wpa1/RESULT.txt"'

z=$(new_z) || exit 2; eligible_e "$z"; ln -s /etc/hostname "$z/evidence-wpa1/link"; rc=$(run6 "$z")
check "S6-8 symlink in the evidence: exit 4, I-5, not inventoried, preserved" \
  '[ "$rc" = 4 ] && grep -q "^integrity_failure: I-5" "$z/evidence-wpa1/RESULT.txt" && ! grep -q "  ./link$" "$z/evidence-wpa1/SHA256SUMS" && preserved "$z"'

z=$(new_z) || exit 2; eligible_e "$z"; echo "corrupted" >> "$z/evidence-wpa1/vv1/fx-before/a2v1-first-chain.log.gz"; rc=$(run6 "$z")
check "S6-9 nested SHA256SUMS no longer verifies: exit 4, F-7 FAILED recorded and covered by the final record" \
  '[ "$rc" = 4 ] && grep -q "^F-7 inventory verification: FAILED" "$z/evidence-wpa1/F7-verification.txt" && grep -q "  F7-verification.txt$" "$z/evidence-wpa1/SHA256SUMS.final"'

z=$(new_z) || exit 2; eligible_e "$z"; echo "- vn1: finding" > "$z/evidence-wpa1/vn1/findings.md"
printf 'Stage 5: all three completed WITH FINDINGS (see */findings.md)\n' > "$z/evidence-wpa1/stage5-summary.txt"; rc=$(run6 "$z")
check "S6-10 findings: exit 5, integrity PASS, not eligible" '[ "$rc" = 5 ] && res "$z" "integrity: PASS" && res "$z" "acceptance_eligible: NO"'

z=$(new_z) || exit 2; mkdir -p "$z/evidence-wpa1/p0"; echo "suite out" > "$z/evidence-wpa1/p0/x.out"; echo "t" > "$z/console.log"; rc=$(run6 "$z")
check "S6-11 NO-GO record (no gate B): exit 5, preserved" '[ "$rc" = 5 ] && grep -q "^not_eligible: gate B is not GO" "$z/evidence-wpa1/RESULT.txt" && preserved "$z"'

z=$(new_z) || exit 2; eligible_e "$z"; rm "$z/console.log"; rc=$(run6 "$z")
check "S6-12 missing console transcript: exit 4 (F-3), preserved" '[ "$rc" = 4 ] && grep -q "^integrity_failure: F-3 the console" "$z/evidence-wpa1/RESULT.txt" && preserved "$z"'

summary test-stage6
