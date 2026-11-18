# shellcheck shell=bash
# Tier-1 audit setenv, installed as <audit root>/setenv. Sources the real OMNeT++ setenv (arguments such as -f are
# passed through) and then puts the audit shim first on PATH, so `opp_run` resolves to the shim.
_t1_audit_dir=$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)
# shellcheck source=/dev/null
. "$_t1_audit_dir/audit.conf"
# shellcheck source=/dev/null
source "$AUDIT_REAL_ROOT/setenv" "$@"
export PATH="$_t1_audit_dir/bin:$PATH"
unset _t1_audit_dir
