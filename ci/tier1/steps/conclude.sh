#!/usr/bin/env bash
# The job succeeds only with TIER-1 PASS and a successful artifact upload (C6: a publication failure can never leave a
# successful CI outcome).
set -uo pipefail
v=$(cat "$RUNNER_TEMP/tier1/verdict.txt" 2>/dev/null || echo "no verdict")
echo "verdict: $v"
echo "artifact upload: ${UPLOAD_OUTCOME:-not run}"
[[ "$v" == "TIER-1 PASS" ]] || { echo "::error::tier-1 verdict: $v"; exit 1; }
[[ "${UPLOAD_OUTCOME:-}" == success ]] || { echo "::error::diagnostic artifact was not published"; exit 1; }
