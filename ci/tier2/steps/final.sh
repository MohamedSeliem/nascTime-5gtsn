#!/usr/bin/env bash
# E3a verdict (E-8 completed with the publication outcomes), written to the job summary and the diagnostic artifact.
. "$(dirname "$0")/../lib/t2common.sh"
set +e
/usr/bin/python3 -I "$T2PY/final_t2.py"
rc=$?
if [[ -f "$CI/publish/e3a-verdict.md" ]] && ! /usr/bin/python3 -I "$T1_LIB/screen.py" "$CI/publish/e3a-verdict.md"; then
  rm -f "$CI/publish/e3a-verdict.md"; echo "::error::verdict withheld by screening"; rc=1
fi
exit "$rc"
