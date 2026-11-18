#!/usr/bin/env bash
# Tier-2 experiment verdict (E-8 completed with the publication outcomes), written to the job summary and the diagnostic artifact.
. "$(dirname "$0")/../lib/t2common.sh"
set +e
/usr/bin/python3 -I "$T2PY/final_t2.py"
rc=$?
if [[ -f "$CI/publish/$T2_EXPERIMENT-verdict.md" ]] && ! /usr/bin/python3 -I "$T1_LIB/screen.py" "$CI/publish/$T2_EXPERIMENT-verdict.md"; then
  rm -f "$CI/publish/$T2_EXPERIMENT-verdict.md"; echo "::error::verdict withheld by screening"; rc=1
fi
exit "$rc"
