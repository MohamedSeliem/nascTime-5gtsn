#!/usr/bin/env bash
# The job succeeds only with "<EXPERIMENT> PASS" and BOTH artifacts uploaded (a publication failure never leaves a
# successful run). T2_EXPERIMENT (e3a default, e3b) selects the experiment.
set -uo pipefail
X=${T2_EXPERIMENT:-e3a}
case "$X" in e3a|e3b) ;; *) echo "::error::unknown experiment $X"; exit 1 ;; esac
v=$(cat "$RUNNER_TEMP/$X/verdict.txt" 2>/dev/null || echo "no verdict")
echo "verdict: $v"
echo "diagnostic artifact upload: ${UPLOAD_DIAG_OUTCOME:-not run}"
echo "raw evidence artifact upload: ${UPLOAD_RAW_OUTCOME:-not run}"
[[ "$v" == "${X^} PASS" ]] || { echo "::error::${X^} verdict: $v"; exit 1; }
[[ "${UPLOAD_DIAG_OUTCOME:-}" == success && "${UPLOAD_RAW_OUTCOME:-}" == success ]] \
  || { echo "::error::an evidence artifact was not published"; exit 1; }
