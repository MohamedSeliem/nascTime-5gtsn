#!/usr/bin/env bash
# usage: build.sh omnetpp|inet|simu5g|nasctime. One release-only build stage (C-6..C-9): disk gate, guarded opp_env
# session, lock gate, output check; after OMNeT++ the SYS_LIBS gate (C-5) runs before anything else is built.
. "$(dirname "$0")/../lib/common.sh"
stage=$1
case "$stage" in
  omnetpp) cap=$CAP_OMNETPP_S; cmd="build_omnetpp release" ;;
  inet) cap=$CAP_INET_S; cmd="build_inet release" ;;
  simu5g) cap=$CAP_SIMU5G_S; cmd="build_simu5g release" ;;
  nasctime) cap=$CAP_NASCTIME_S; cmd="bash $T1_DIR/session/build-m2.sh $REPO $WS" ;;
  *) echo "::error::unknown stage $stage"; exit 2 ;;
esac
export STAGE_CAP_S=$cap
"$T1_LIB/diskgate.sh" "before $stage"
oe_session "build-$stage" run -w "$WS" --build-modes release $PROJECTS -c "$cmd"
"$T1_LIB/lockcheck.sh" "after-$stage" "$EV/build-$stage.log"
"$T1_LIB/stagecheck.sh" "$stage"
if [[ "$stage" == omnetpp ]]; then
  /usr/bin/python3 -I "$PY/sys_libs.py" "$WS/omnetpp-6.5.0/Makefile.inc" "$VM_SYS_LIBS" "$EV/sys-libs.txt" \
    || { echo "::error::C-5 SYS_LIBS gate failed; stopping before INET"; exit 1; }
fi
"$T1_LIB/diskgate.sh" "after $stage"
