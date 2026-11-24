#!/usr/bin/env bash
# WP-A1 validation, Stage 6 (runbook revision 4): evidence finalisation (corrected P-4) with an explicit integrity and
# acceptance-eligibility result. Runs after Stage 5, or after any stop from Stage 2 on, in a network-less container
# WITHOUT evidence mounts, under the separate finalisation transcript.
#
# Every outcome is finalised and preserved: a failed check never prevents the inventory and the final record; it makes
# the evidence NOT acceptance-eligible, recorded in $E/RESULT.txt (inside the inventory) and, for the inventory
# verification itself, in $E/F7-verification.txt (covered by SHA256SUMS.final).
# Exit: 0  finalised; integrity PASS; acceptance-eligible YES (a candidate for VG-1 / VG-3, not an acceptance)
#       4  finalised; integrity FAILED; acceptance-eligible NO (preserved as failed evidence)
#       5  finalised; integrity PASS; acceptance-eligible NO (NO-GO, stop, incomplete or findings)
#       1  not finalised (no evidence directory, already finalised, or the records cannot be written)
STAGE=stage6-finalise
. "$(dirname "$0")/common.sh"
load_vars
[ -d "$E" ] || stop "no evidence directory: nothing to finalise"
[ ! -e "$E/SHA256SUMS" ] && [ ! -e "$E/SHA256SUMS.final" ] && [ ! -e "$E/RESULT.txt" ] || stop "already finalised"
fail=()        # integrity failures: the evidence or the procedure inputs cannot be trusted
incomplete=()  # completeness: the run did not produce an acceptance-eligible result

# ---- F-2 post-run integrity of the procedure inputs (each failure recorded; nothing stops) --------------------------
mkdir -p "$E/supplementary" || stop "cannot write $E/supplementary"
P="$E/supplementary/post-checks.txt"
{
  (cd "$CHK" && sha256sum -c --strict) <<'EOF'
b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b  expect/vn1.expect.json
5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3  expect/vn2.expect.json
fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d  expect/vv1.expect.json
2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae  m2s72_fgo_registry.json
EOF
  echo "I-1 expectation/registry rc=$?"
  echo "I-2 worktree HEAD $(git -C "$W" rev-parse HEAD 2>&1)"
  echo "I-3 worktree status <<$(git -C "$W" status --porcelain --untracked-files=all 2>&1)>>"
  echo "I-4 simu5g HEAD $(git -C "$SIMU5G_ROOT" rev-parse HEAD 2>&1) status <<$(git -C "$SIMU5G_ROOT" status --porcelain --untracked-files=all 2>&1)>>"
} > "$P" 2>&1 || stop "cannot write $P"
grep -qx "I-1 expectation/registry rc=0" "$P" || fail+=("I-1 expectation files or registry differ from the reviewed values")
[ "$(git -C "$W" rev-parse HEAD 2>/dev/null)" = "$C" ] || fail+=("I-2 the worktree is not at the reviewed commit")
[ -z "$(git -C "$W" status --porcelain --untracked-files=all 2>&1)" ] || fail+=("I-3 the worktree is not clean")
[ "$(git -C "$SIMU5G_ROOT" rev-parse HEAD 2>/dev/null)" = "$SIMU5G_HEAD" ] && [ -z "$(git -C "$SIMU5G_ROOT" status --porcelain --untracked-files=all 2>&1)" ] \
  || fail+=("I-4 the Simu5G tree is not the clean pinned tree")
odd=$(find "$E" ! -type f ! -type d 2>&1)
[ -z "$odd" ] || { fail+=("I-5 the evidence directory holds non-regular entries (listed; not followed, not inventoried)"); printf '%s\n' "$odd" > "$E/supplementary/non-regular-entries.txt"; }

# ---- F-3 procedure, approvals and the console transcript (never overwritten; a failure is recorded) ----------------
if [ ! -e "$E/procedure" ] && mkdir "$E/procedure" && cp -p "$Z/vars.env" "$E/procedure/" && cp -rp "$Z/scripts" "$E/procedure/scripts" \
   && { [ ! -d "$APPROVALS" ] || cp -rp "$APPROVALS" "$E/procedure/approvals"; }; then :; else fail+=("F-3 the procedure copy failed"); fi
if [ -f "$Z/console.log" ] && [ ! -e "$E/console.log" ] && cp -p "$Z/console.log" "$E/console.log"; then :; else fail+=("F-3 the console transcript is missing or could not be copied"); fi

# ---- completeness and acceptance eligibility (VG-0 / VG-1 preconditions; never an acceptance) ----------------------
grep -qx "GATE B: GO (B-1 ... B-6 met)" "$E/gate/gate-b.txt" 2>/dev/null || incomplete+=("gate B is not GO (NO-GO record)")
[ -f "$E/gate/stage5-validate.done" ] || incomplete+=("Stage 5 did not complete (stopped)")
[ "$(tail -n 1 "$E/stage5-summary.txt" 2>/dev/null)" = "Stage 5: all three completed; every hrq --expect exit 0" ] \
  || incomplete+=("Stage 5 did not end with every hrq --expect exit 0")
f=$(cd "$E" && find . -name findings.md 2>/dev/null | LC_ALL=C sort | tr '\n' ' ')
[ -z "$f" ] || incomplete+=("findings recorded: $f")
for r in environment/identity.txt environment/approvals/gate-a.txt environment/approvals/a4-dr13.txt environment/approvals/a5-g0ro.txt \
         release/selected.sha256 release/verify-after.txt x2a/method.txt x2a/mount.txt vv1/fx-before/SHA256SUMS vv1/fx-after/SHA256SUMS; do
  [ -f "$E/$r" ] || incomplete+=("missing $r")
done

integrity=PASS; [ ${#fail[@]} -eq 0 ] || integrity=FAILED
eligible=YES;  { [ "$integrity" = PASS ] && [ ${#incomplete[@]} -eq 0 ]; } || eligible=NO
{
  echo "WP-A1 validation result (runbook revision 4, Stage 6)"
  echo "integrity: $integrity"
  for x in "${fail[@]}"; do echo "integrity_failure: $x"; done
  for x in "${incomplete[@]}"; do echo "not_eligible: $x"; done
  echo "acceptance_eligible: $eligible"
  echo "note: acceptance_eligible YES is a precondition of VG-1 ... VG-3, never an acceptance; NO is final for this evidence"
} > "$E/RESULT.txt" || stop "cannot write RESULT.txt"

# ---- F-5 inventory (every regular file except the top-level records; nested SHA256SUMS included) -------------------
(cd "$E" && find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.final ! -path ./F7-verification.txt -print0 \
   | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$E/SHA256SUMS" || stop "inventory could not be written"
# ---- F-6 / F-7 completeness of the inventory and verification, top level and nested -------------------------------
f7=PASS
n=$(cd "$E" && find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.final ! -path ./F7-verification.txt | wc -l)
[ "$(wc -l < "$E/SHA256SUMS")" -eq "$n" ] || f7="FAILED (inventory count differs from the file count)"
grep -q '  \./RESULT\.txt$' "$E/SHA256SUMS" || f7="FAILED (RESULT.txt not inventoried)"
(cd "$E" && sha256sum -c --strict --quiet SHA256SUMS) >/dev/null 2>&1 || f7="FAILED (the inventory does not verify)"
for d in fx-before fx-after; do
  [ -f "$E/vv1/$d/SHA256SUMS" ] && { (cd "$E/vv1/$d" && sha256sum -c --strict --quiet SHA256SUMS) >/dev/null 2>&1 || f7="FAILED (nested $d/SHA256SUMS does not verify)"; }
done
{ echo "F-7 inventory verification: $f7"
  [ "$f7" = PASS ] || echo "acceptance_eligible: NO (overrides RESULT.txt)"; } > "$E/F7-verification.txt" || stop "cannot write F7-verification.txt"
# ---- F-8 final record: covers SHA256SUMS (which covers RESULT.txt and every other file) and the F-7 result ----------
(cd "$E" && sha256sum SHA256SUMS F7-verification.txt) > "$E/SHA256SUMS.final" || stop "final record could not be written"
# ---- F-9 local seal (effective for the non-root container user) ----------------------------------------------------
chmod -R a-w "$E" 2>/dev/null || true
[ "$f7" = PASS ] || { integrity=FAILED; eligible=NO; }
cat "$E/RESULT.txt"; cat "$E/F7-verification.txt"
echo "F-10: record now, outside \$E:"; cat "$E/SHA256SUMS.final"
if [ "$integrity" = FAILED ]; then echo "STAGE 6: finalised as FAILED-INTEGRITY evidence (preserved; not acceptance-eligible)"; exit 4; fi
if [ "$eligible" = NO ]; then echo "STAGE 6: finalised; integrity PASS; not acceptance-eligible"; exit 5; fi
echo "STAGE 6: finalised; integrity PASS; acceptance-eligible (subject to VG-1 ... VG-3)"
exit 0
