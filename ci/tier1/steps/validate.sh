#!/usr/bin/env bash
# C-10..C-12: binaries, opp_run -v identity, linkage, single C++ runtime, unexpected resolutions, RUNPATH classes.
# Static inspection plus the approved `opp_run -v`; every component runs and is recorded even if another fails.
. "$(dirname "$0")/../lib/common.sh"
export STAGE_CAP_S=$CAP_VALIDATE_S
set +e
oe_session validate run -w "$WS" --build-modes release $PROJECTS -c "bash $T1_DIR/session/validate.sh $EV $WS $REPO"
vrc=$?
"$T1_LIB/lockcheck.sh" after-validation "$EV/validate.log"
lrc=$?
{
  echo "### Tier-1 validation (screened)"
  echo
  echo '```'
  cat "$EV/validate-result.txt" 2>/dev/null || echo "validate-result.txt: absent"
  echo "guarded validate exit: $vrc"
  echo "lock gate after-validation exit: $lrc"
  grep -h '^opp_run_v_exit' "$EV/opp_run-version.txt" 2>/dev/null || echo "opp_run_v_exit: absent"
  echo "--- unresolved dynamic dependencies"
  if [[ -s "$EV/unresolved.txt" ]]; then cat "$EV/unresolved.txt"; else echo "none"; fi
  echo "--- per-file results (path, elf, unresolved, libc++ violation, libunwind, libstdc++ resolved, unexpected resolution)"
  cut -f3,6,10-14 "$EV/binaries.tsv" 2>/dev/null
  echo "--- non-store RUNPATH entries (count, entry, class)"
  sed 's/^[^:]*: non-store RUNPATH entry //' "$EV/runpath-observation-validate.txt" 2>/dev/null | sort | uniq -c
  echo '```'
} > "$CI/validation-summary.md"
if /usr/bin/python3 -I "$T1_LIB/screen.py" "$CI/validation-summary.md" > /dev/null; then
  tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}" < "$CI/validation-summary.md"
else
  echo "validation summary withheld by screening" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
fi
exit $(( vrc != 0 || lrc != 0 ))
