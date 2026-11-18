#!/usr/bin/env bash
# Sourced by every ci/tier2/steps/*.sh. Reuses the integrated tier-1 environment unchanged (pins, test-override refusal,
# directories, guarded opp_env sessions), then loads the pins of the experiment named by T2_EXPERIMENT (e3a: the accepted
# M2S4U experiment, pins-tier2.env, the default; e3b: the M2S5 bridge experiment, pins-e3b.env) and defines its directories.
# shellcheck source=../../tier1/lib/common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/tier1/lib/common.sh"
T2_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
T2_EXPERIMENT=${T2_EXPERIMENT:-e3a}
case "$T2_EXPERIMENT" in
  e3a) T2_PINS=$T2_DIR/pins-tier2.env ;;
  e3b) T2_PINS=$T2_DIR/pins-e3b.env ;;
  *) echo "::error::unknown tier-2 experiment '$T2_EXPERIMENT'"; exit 3 ;;
esac
set -a
# shellcheck source=../pins-tier2.env
. "$T2_PINS"
set +a
if [[ "$T2_EXPERIMENT" == e3a ]]; then   # the accepted E3a pins use E3A_* names; map them to the generic names
  EXP_ID=e3a; EXP_BRANCH=$E3A_BRANCH; EXP_PARENT=$E3A_BASELINE; EXP_BASELINE=$E3A_BASELINE
  EXP_WORKFLOW=.github/workflows/e3a-functional-smoke.yml; EXP_SCOPE=ci/tier2/; EXP_ALLOW_MODIFIED=no; EXP_FROZEN=""
  ORACLE=u1
  export EXP_ID EXP_BRANCH EXP_PARENT EXP_BASELINE EXP_WORKFLOW EXP_SCOPE EXP_ALLOW_MODIFIED EXP_FROZEN ORACLE
fi
[[ "$EXP_ID" == "$T2_EXPERIMENT" ]] || { echo "::error::pins of '$EXP_ID' loaded for experiment '$T2_EXPERIMENT'"; exit 3; }
E3=$RUNNER_TEMP/$T2_EXPERIMENT   # outside the repository and outside the tier-1 work directory
RAW=$E3/raw                      # raw simulation evidence (sealed before evaluation)
REC=$E3/records                  # execution, identity and resource records
T2PY=$T2_DIR/py
export T2_DIR T2_EXPERIMENT E3 RAW REC T2PY
