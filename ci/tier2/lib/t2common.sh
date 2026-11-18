#!/usr/bin/env bash
# Sourced by every ci/tier2/steps/*.sh. Reuses the integrated tier-1 environment unchanged (pins, test-override refusal,
# directories, guarded opp_env sessions), then loads the E3a pins and defines the tier-2 directories.
# shellcheck source=../../tier1/lib/common.sh
. "$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)/tier1/lib/common.sh"
T2_DIR=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)
set -a
# shellcheck source=../pins-tier2.env
. "$T2_DIR/pins-tier2.env"
set +a
E3=$RUNNER_TEMP/e3a              # outside the repository and outside the tier-1 work directory
RAW=$E3/raw                      # raw simulation evidence (sealed before evaluation)
REC=$E3/records                  # execution, identity and resource records
T2PY=$T2_DIR/py
export T2_DIR E3 RAW REC T2PY
