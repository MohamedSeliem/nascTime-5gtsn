# nascTime results-root selection (M2-R181 plan rev. 2, R-1..R-3). Sourced by the M1 / M2 runners after HERE,
# NASCTIME and SIMU5G_ROOT are set. Bash only; no output in legacy mode.
#
#   legacy mode   (NASCTIME_RESULTS_ROOT unset): RESULTS = $HERE/results, exactly as before. Refuses to start
#                 unless $SIMU5G_ROOT/src/libsimu5g.so is the accepted Simu5G 1.8.0 library (the legacy trees hold
#                 the 1.8.0 baseline only). No new file is written.
#   isolated mode (NASCTIME_RESULTS_ROOT=/abs/root): RESULTS = $NASCTIME_RESULTS_ROOT/<m1|m2>. The root must be
#                 absolute and must not be, contain or lie inside simulations/m1/results or simulations/m2/results.
#                 A run mode never overwrites: nt_fresh_out refuses an existing stage directory. nt_stack_record
#                 writes stack.txt (versions, library hash) into the stage directory.

NT_ACCEPTED_LIBSIMU5G_SHA256=203cf231e6605188662769b439e403d832f516d2e08c8a0c5a9e8f55f4305cf6

nt_die() { echo "ERROR: $*" >&2; exit 1; }

nt_results_init() {  # $1 = m1 | m2 (results family); $2 = "nobaseline" to skip the legacy library check
  local fam=$1 lib legacy root
  [ -n "$NASCTIME" ] && [ -n "$SIMU5G_ROOT" ] || nt_die "nt_results_init: NASCTIME and SIMU5G_ROOT must be set"
  if [ -z "${NASCTIME_RESULTS_ROOT:-}" ]; then
    NT_ISOLATED=
    RESULTS=$HERE/results
    if [ "${2:-}" != nobaseline ]; then
      lib=$(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" 2>/dev/null | cut -d' ' -f1)
      [ "$lib" = "$NT_ACCEPTED_LIBSIMU5G_SHA256" ] || nt_die "legacy results ($RESULTS) hold the Simu5G 1.8.0 baseline only;" \
        "$SIMU5G_ROOT/src/libsimu5g.so is not the accepted library. Set NASCTIME_RESULTS_ROOT to an isolated root"
    fi
    return 0
  fi
  case "$NASCTIME_RESULTS_ROOT" in /*) ;; *) nt_die "NASCTIME_RESULTS_ROOT must be an absolute path" ;; esac
  root=$(realpath -m "$NASCTIME_RESULTS_ROOT")
  for legacy in "$NASCTIME/simulations/m1/results" "$NASCTIME/simulations/m2/results"; do
    legacy=$(realpath -m "$legacy")
    case "$root/" in "$legacy"/*) nt_die "NASCTIME_RESULTS_ROOT ($root) lies inside the legacy results tree $legacy" ;; esac
    case "$legacy/" in "$root"/*) nt_die "NASCTIME_RESULTS_ROOT ($root) contains the legacy results tree $legacy" ;; esac
  done
  NT_ISOLATED=1
  RESULTS=$root/$fam
  mkdir -p "$RESULTS"
}

nt_fresh_out() {  # $1 = stage directory a run mode is about to (re)create; isolated mode only
  [ -n "$NT_ISOLATED" ] || return 0
  local d
  d=$(realpath -m "$1")
  [ "${NT_OUT_CLAIMED:-}" = "$d" ] && return 0
  [ -e "$d" ] && nt_die "$d exists: isolated results are never overwritten (choose a new NASCTIME_RESULTS_ROOT)"
  mkdir -p "$d"
  export NT_OUT_CLAIMED=$d
}

nt_refuse_isolated() {  # $1 = mode name; for modes tied to the 1.8.0 record
  [ -z "$NT_ISOLATED" ] || nt_die "mode $1 belongs to the Simu5G 1.8.0 record and does not run in isolated mode"
}

nt_stack_record() {  # $1 = stage directory; isolated mode only
  [ -n "$NT_ISOLATED" ] || return 0
  mkdir -p "$1"
  {
    echo "results_root: $(dirname "$RESULTS")"
    echo "simu5g_root: $SIMU5G_ROOT"
    echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
    echo "libsimu5g_sha256: $(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" 2>/dev/null | cut -d' ' -f1)"
    echo "inet_version_file: $(cat "${INET_ROOT:-/root/stack/inet-4.7.0}/Version" 2>/dev/null || echo n/a)"
    echo "omnetpp_root: ${OMNETPP_ROOT:-n/a}"
    echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)"
  } > "$1/stack.txt"
}
