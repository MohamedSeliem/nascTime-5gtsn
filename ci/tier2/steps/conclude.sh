#!/usr/bin/env bash
# The job succeeds only with E3a PASS and BOTH artifacts uploaded (a publication failure never leaves a successful run).
set -uo pipefail
v=$(cat "$RUNNER_TEMP/e3a/verdict.txt" 2>/dev/null || echo "no verdict")
echo "verdict: $v"
echo "diagnostic artifact upload: ${UPLOAD_DIAG_OUTCOME:-not run}"
echo "raw evidence artifact upload: ${UPLOAD_RAW_OUTCOME:-not run}"
[[ "$v" == "E3a PASS" ]] || { echo "::error::E3a verdict: $v"; exit 1; }
[[ "${UPLOAD_DIAG_OUTCOME:-}" == success && "${UPLOAD_RAW_OUTCOME:-}" == success ]] \
  || { echo "::error::an evidence artifact was not published"; exit 1; }
