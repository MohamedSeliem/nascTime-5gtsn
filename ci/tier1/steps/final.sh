#!/usr/bin/env bash
# C-15 and the overall verdict (written to the job summary and to verdict.md in the publication directory).
. "$(dirname "$0")/../lib/common.sh"
set +e
/usr/bin/python3 -I "$PY/final.py"
rc=$?
if [[ -f "$CI/publish/verdict.md" ]] && ! /usr/bin/python3 -I "$T1_LIB/screen.py" "$CI/publish/verdict.md"; then
  rm -f "$CI/publish/verdict.md"; echo "::error::verdict.md withheld by screening"; rc=1
fi
exit "$rc"
