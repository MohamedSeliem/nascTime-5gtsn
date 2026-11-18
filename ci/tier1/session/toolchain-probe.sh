#!/usr/bin/env bash
# usage: bash probe.sh <output file>. Required probes fail the step; optional ones report NOT AVAILABLE.
out=$1; fail=0
{
  echo "opp_env_version_in_shell: ${OPP_ENV_VERSION:-<unset>}"
  echo "omnetpp_root: $OMNETPP_ROOT"
  echo "inet_root: $INET_ROOT"
  echo "simu5g_root: $SIMU5G_ROOT"
  echo "build_modes_session: ${BUILD_MODES:-<unset>}"
  for t in clang++ g++ make python3; do
    if ! p=$(command -v "$t"); then echo "required $t: MISSING"; fail=1; continue; fi
    if v=$("$t" --version 2>&1); then echo "tool $t: $p | $(head -1 <<< "$v")"; else echo "required $t: VERSION COMMAND FAILED"; fail=1; fi
  done
  for t in cc c++ clang gcc ld ld.lld bison flex perl pkg-config ccache lldb patchelf qmake z3; do
    if p=$(command -v "$t") && v=$("$t" --version 2>&1); then echo "tool $t: $p | $(head -1 <<< "$v")"
    else echo "tool $t: NOT AVAILABLE"; fi
  done
  python3 -c 'import numpy, scipy, pandas, matplotlib; print("python_modules:", numpy.__version__, scipy.__version__, pandas.__version__, matplotlib.__version__)' 2>/dev/null \
    || echo "python_modules: NOT AVAILABLE"
  if v=$(cat "$OMNETPP_ROOT/Version"); then echo "omnetpp_version_file: $v"; else echo "required omnetpp Version: FAILED"; fail=1; fi
  if v=$(cat "$SIMU5G_ROOT/Version"); then echo "simu5g_version_file: $v"; else echo "required simu5g Version: FAILED"; fail=1; fi
  if c=$(grep -E '^(WITH_|PREFER_|USE_)' "$OMNETPP_ROOT/configure.user"); then
    sed 's/^/configure.user /; s/=/: /' <<< "$c"
  else
    echo "required configure.user: FAILED"; fail=1
  fi
  echo "probe_result: $([ "$fail" = 0 ] && echo PASS || echo FAIL)"
} > "$out" 2>&1
exit "$fail"
