#!/usr/bin/env bash
# All non-Docker procedure tests (runbook rev. 4, 14). TEST ONLY; no evidence. Needs NASCTIME_SRC and SIMU5G_SRC.
set -u -o pipefail
d=$(cd "$(dirname "$0")" && pwd); rc=0
for t in test-extract.sh test-g0ro-compare.sh test-approvals.sh test-stage6.sh; do
  bash "$d/$t" | tail -n 1 | sed "s/^/[$t] /"; [ "${PIPESTATUS[0]}" -eq 0 ] || rc=1
done
echo "run-all: $([ $rc -eq 0 ] && echo ALL PASS || echo FAILURES)"; exit $rc
