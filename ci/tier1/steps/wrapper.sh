#!/usr/bin/env bash
# C-13: the existing A2-V1 wrapper regression suite, in-session, with the real simulator behind the audit shim.
# Evidence class: real configuration queries + synthetic lifecycle tests (level 2). No simulation is executed.
. "$(dirname "$0")/../lib/common.sh"
export STAGE_CAP_S=$CAP_WRAPPER_S
set +e
oe_session wrapper-suite run -w "$WS" --build-modes release $PROJECTS \
  -c "bash $T1_DIR/wrapper/run-suite.sh $T1_DIR $REPO $EV $CI/wrapper"
grc=$?
"$T1_LIB/lockcheck.sh" after-wrapper "$EV/wrapper-suite.log"
lrc=$?
/usr/bin/python3 -I "$PY/wrapper_check.py" "$EV" "$WRAPPER_EXPECTED_LINE" "$WRAPPER_EXPECTED_TESTS" "$grc"
wrc=$?
{
  echo "### Tier-1 A2-V1 wrapper regression suite (screened)"
  echo
  echo '```'
  cat "$EV/wrapper-result.txt" 2>/dev/null
  echo "--- tests"
  tail -n +2 "$EV/wrapper-results.tsv" 2>/dev/null
  echo "--- real simulator calls (seq, decision, kind, working directory, exit)"
  tail -n +2 "$EV/opp_run-audit.tsv" 2>/dev/null | cut -f1,3,4,5,7
  echo '```'
} > "$CI/wrapper-summary.md"
if /usr/bin/python3 -I "$T1_LIB/screen.py" "$CI/wrapper-summary.md" > /dev/null; then
  tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}" < "$CI/wrapper-summary.md"
else
  echo "wrapper summary withheld by screening" | tee -a "${GITHUB_STEP_SUMMARY:-/dev/null}"
fi
exit $(( grc != 0 || lrc != 0 || wrc != 0 ))
