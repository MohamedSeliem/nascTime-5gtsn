#!/usr/bin/env bash
# usage: run-sim.sh <preflight|sim> <experiment> <repo> <ws> <raw> <rec> <ev> <wall_cap_s> <watchdog_limit_B> <poll_s> <measure_timeout_s>
# Runs INSIDE the opp_env session (OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1 built and validated by tier-1).
#   preflight  the approved configuration query (-q runconfig) of the experiment's authorised configuration; no simulation
#   sim        exactly ONE simulation of the experiment's authorised configuration, run 0 of --repeat=10, with the
#              reviewed command of simulations/m2/m2s4.sh / m2s5.sh run() (identical apart from -c), an output-size /
#              wall-time / STOP watchdog and evidence.
# Each experiment authorises exactly one configuration (e3a: M2S4U; e3b: M2S5); the table below is fixed and nothing can
# be passed in to change the argument vector. Every refusal exits 3 before anything is started; a watchdog
# termination exits 4.
set -uo pipefail
[[ $# == 11 ]] || { echo "run-sim: expected 11 arguments, got $#" >&2; exit 3; }
mode=$1 EXP=$2 REPO=$3 WSD=$4 RAW=$5 REC=$6 EVD=$7 CAP=$8 LIMIT=$9 POLL=${10} MT=${11}
CTL="$REC/sim-control-$mode.txt"
die() { echo "refused: $*" >> "$CTL"; echo "run-sim ($mode) refused: $*" >&2; exit 3; }
mkdir -p "$REC" || exit 3
: >> "$CTL"
case "$mode" in preflight|sim) ;; *) die "unknown mode '$mode'" ;; esac
case "$EXP" in   # the only authorised configuration of each experiment (fixed)
  e3a) CFG=M2S4U ;;
  e3b) CFG=M2S5 ;;
  *) die "unknown experiment '$EXP'" ;;
esac
echo "experiment: $EXP authorised_configuration: $CFG" >> "$CTL"
for v in "$CAP" "$LIMIT" "$POLL" "$MT"; do [[ "$v" =~ ^[0-9]+$ && "$v" -gt 0 ]] || die "invalid limit '$v'"; done
# --- the session's stack must be the tier-1 workspace
[[ "${OMNETPP_ROOT:-}" == "$WSD/omnetpp-6.5.0" ]] || die "OMNETPP_ROOT=${OMNETPP_ROOT:-unset}"
[[ "${INET_ROOT:-}" == "$WSD/inet-4.7.0" ]] || die "INET_ROOT=${INET_ROOT:-unset}"
[[ "${SIMU5G_ROOT:-}" == "$WSD/simu5g-1.8.1" ]] || die "SIMU5G_ROOT=${SIMU5G_ROOT:-unset}"
OPP=$OMNETPP_ROOT/bin/opp_run
[[ -x "$OPP" && "$(command -v opp_run)" == "$OPP" ]] || die "opp_run is not $OPP"
M2=$REPO/simulations/m2
[[ -f "$M2/omnetpp.ini" ]] || die "configuration missing"
case "$(realpath -m "$RAW")/" in "$(realpath "$REPO")"/*) die "output directory inside the repository" ;; esac
# --- the reviewed command (simulations/m2/m2s4.sh and m2s5.sh run(), the authorised configuration, run 0 of --repeat=10)
ARGV=(-l "$REPO/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"
      -n "$REPO/simulations:$REPO/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes
      -u Cmdenv -f omnetpp.ini -c "$CFG" --repeat=10 -r 0)
LIBS=("$REPO/src/nasctime/m2/libnasctime_m2.so" "$SIMU5G_ROOT/src/libsimu5g.so" "$INET_ROOT/src/libINET.so")
# --- identities of the simulator and the libraries it is told to load
{
  printf 'role\tpath\tsha256\tbytes\n'
  for f in "$OPP" "${LIBS[@]}"; do
    [[ -f "$f" ]] || die "missing $f"
    printf '%s\t%s\t%s\t%s\n' "$(basename "$f")" "$(realpath "$f")" "$(sha256sum "$f" | cut -c1-64)" "$(stat -c %s "$f")"
  done
} > "$REC/binary-identity-$mode.tsv"
# --- working-directory and RUNPATH hazards (as tier-1 C2): relative RUNPATH entries resolve against the actual working
# directory, which must hold no shared library; absent absolute entries must still be absent; the loader resolves the
# simulator and the libraries only from /nix/store and the project library directories.
RD=$(command -v readelf || command -v llvm-readelf) || die "readelf unavailable"
INTERP=$(patchelf --print-interpreter "$OPP" 2>/dev/null) && [[ -x "$INTERP" ]] || die "ELF interpreter unavailable"
ALLOW="^(/nix/store/|$OMNETPP_ROOT/lib/|$INET_ROOT/src/|$SIMU5G_ROOT/src/|$REPO/src/nasctime/m2/)"
hz=""; rel=(); absent=()
for f in "$OPP" "${LIBS[@]}" "$OMNETPP_ROOT"/lib/*.so; do
  for d in $("$RD" -d "$f" 2>/dev/null | sed -n 's/.*(\(RUNPATH\|RPATH\)).*\[\(.*\)\]/\2/p' | tr ':' ' '); do
    case "$d" in /nix/store/*) ;; /*) [[ -e "$d" ]] || absent+=("$d") ;; *) rel+=("$d") ;; esac
  done
done
{
  echo "working_directory: $(realpath "$M2")"
  echo "relative_runpath_entries: $(printf '%s\n' "${rel[@]}" | sort -u | paste -sd ' ')"
  echo "absent_runpath_entries: $(printf '%s\n' "${absent[@]}" | sort -u | paste -sd ' ')"
  for e in $(printf '%s\n' "${rel[@]}" | sort -u); do
    l=$(find "$M2/$e" -maxdepth 1 \( -name '*.so' -o -name '*.so.*' \) 2>/dev/null | head -5 | paste -sd ',')
    [[ -z "$l" ]] || { echo "hazard: shared libraries reachable through relative RUNPATH '$e': $l"; hz=1; }
  done
  for e in $(printf '%s\n' "${absent[@]}" | sort -u); do
    [[ ! -e "$e" ]] || { echo "hazard: RUNPATH entry $e now exists"; hz=1; }
  done
  for f in "$OPP" "${LIBS[@]}"; do
    lst=$(cd "$M2" && "$INTERP" --list "$f" 2>&1) || { echo "hazard: loader listing of $(basename "$f") failed"; hz=1; }
    bad=$(sed -n 's/^[[:space:]]*[^ ]* => \(\/[^ ]*\).*/\1/p' <<< "$lst" | grep -v -E "$ALLOW" | paste -sd ',')
    [[ -z "$bad" ]] || { echo "hazard: $(basename "$f") resolves $bad"; hz=1; }
    ! grep -q 'not found' <<< "$lst" || { echo "hazard: $(basename "$f") has an unresolved dependency"; hz=1; }
  done
  echo "hazards: $([[ -z "$hz" ]] && echo none || echo FOUND)"
} > "$REC/hazards-$mode.txt"
grep -qx 'hazards: none' "$REC/hazards-$mode.txt" || die "working-directory or loader hazard (see hazards-$mode.txt)"

if [[ "$mode" == preflight ]]; then
  printf '%s\0' "$OPP" "${ARGV[@]}" -q runconfig > "$REC/argv-preflight.nul"
  echo "cwd: $(realpath "$M2")" > "$REC/cwd-preflight.txt"
  (cd "$M2" && "$OPP" "${ARGV[@]}" -q runconfig) > "$RAW/effective-config.txt" 2> "$REC/runconfig-stderr.txt"
  rc=$?
  echo "preflight_exit: $rc" >> "$CTL"
  echo "effective_config_sha256: $(sha256sum "$RAW/effective-config.txt" | cut -c1-64)" >> "$CTL"
  exit "$rc"
fi

# ----------------------------------------------------------------------------------------------- sim: exactly one run
[[ -s "$RAW/effective-config.txt" ]] || die "pre-flight configuration dump missing"
grep -qx 'preflight_exit: 0' "$REC/sim-control-preflight.txt" 2>/dev/null || die "pre-flight did not succeed"
[[ ! -e "$RAW/runs" ]] || die "duplicate invocation: output directory exists"
( set -o noclobber; : > "$REC/sim.started" ) 2>/dev/null || die "duplicate invocation: a simulation was already started"
mkdir "$RAW/runs" || die "cannot create the output directory"
RESDIR="$RAW/runs/$CFG"
FULL=("$OPP" "${ARGV[@]}" --result-dir="$RESDIR" --cmdenv-express-mode=true)
printf '%s\0' "${FULL[@]}" > "$REC/argv-sim.nul"
REALOPP=$(realpath "$OPP")
kill_tree() {  # $1 pid, $2 reason: TERM, then KILL, the process and all its descendants
  local pids=("$1") i=0 c
  while (( i < ${#pids[@]} )); do
    for c in $(ps -o pid= --ppid "${pids[$i]}" 2>/dev/null); do pids+=("$c"); done
    i=$((i + 1))
  done
  echo "watchdog_termination: $2 (processes: ${pids[*]})" >> "$CTL"
  kill -TERM "${pids[@]}" 2>/dev/null
  for _ in 1 2 3 4 5 6 7 8 9 10; do
    alive=0; for c in "${pids[@]}"; do kill -0 "$c" 2>/dev/null && [[ "$(ps -o stat= -p "$c" 2>/dev/null)" != Z* ]] && alive=1; done
    (( alive )) || break; sleep 0.5
  done
  kill -KILL "${pids[@]}" 2>/dev/null
}
running() { local st; st=$(ps -o stat= -p "$1" 2>/dev/null | tr -d ' '); [[ -n "$st" && "$st" != Z* ]]; }
measure() {  # prints the apparent output size in bytes, or nothing on failure
  timeout "$MT" du -s --apparent-size -B1 "$RAW/runs" 2>/dev/null | cut -f1
}
numeric() { if [[ "$1" =~ ^[0-9]+$ ]]; then echo "$1"; else echo "NOT NUMERIC"; fi; }   # never record a raw non-numeric reading as a value
hwm_of() { awk '/^VmHWM:/ {print $2}' "/proc/$1/status" 2>/dev/null; }
capture() {  # observed identity of the running process (once it is opp_run): executable, argument vector, cwd
  [[ -s "$REC/observed-cmdline.nul" ]] && return 0
  if [[ "$(readlink "/proc/$SIM/exe" 2>/dev/null)" == "$REALOPP" ]]; then
    cat "/proc/$SIM/cmdline" > "$REC/observed-cmdline.nul" 2>/dev/null
    readlink "/proc/$SIM/cwd" > "$REC/observed-cwd.txt" 2>/dev/null
  fi
}
printf 'utc\telapsed_s\tkind\toutput_bytes\tvmhwm_kib\tprocess_alive\n' > "$REC/watchdog.tsv"
reason=""; insamples=0; maxb=""; hwm=""
sample() {  # $1 kind (initial | in-run); a failed or non-numeric measurement while the process is alive terminates it
  local alive_before b h el alive_after
  alive_before=no; running "$SIM" && alive_before=yes
  b=$(measure)
  h=$(hwm_of "$SIM")
  alive_after=no; running "$SIM" && alive_after=yes
  el=$(awk -v a="$(date +%s.%N)" -v b="$t0" 'BEGIN{printf "%.3f", a-b}')
  printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$el" "$1" "${b:-ERR}" "${h:-}" "$alive_before/$alive_after" >> "$REC/watchdog.tsv"
  [[ "$1" == initial ]] && echo "initial_output_bytes: $(numeric "$b")" >> "$CTL"
  if [[ "$alive_before" == yes ]]; then
    if [[ "$b" =~ ^[0-9]+$ ]]; then
      insamples=$((insamples + 1))
      [[ -z "$maxb" ]] || (( b > maxb )) || b=$maxb
      maxb=$b
    elif [[ "$alive_after" == yes ]]; then
      reason="output measurement failed or non-numeric ('${b:-empty}') while the simulation was running"; return 1
    else
      echo "measurement_note: a measurement failed while the simulation ended (not a monitoring failure)" >> "$CTL"
    fi
    if [[ "$h" =~ ^[0-9]+$ ]] && { [[ -z "$hwm" ]] || (( h > hwm )); }; then hwm=$h; fi
  fi
  if [[ "$b" =~ ^[0-9]+$ ]] && (( b > LIMIT )); then reason="output ${b} B exceeds the watchdog limit ${LIMIT} B"; return 1; fi
  return 0
}
t0=$(date +%s.%N)
(cd "$M2" && exec env LD_DEBUG=files LD_DEBUG_OUTPUT="$REC/lddebug" "${FULL[@]}") > "$RAW/run-$CFG.log" 2>&1 &
SIM=$!
echo "simulation_started: 1 pid=$SIM t0=$t0" >> "$CTL"
# immediate initial measurement (before any wait), then a short identity capture, then the regular watchdog loop
if ! sample initial; then kill_tree "$SIM" "$reason"; fi
for _ in $(seq 1 100); do
  [[ -n "$reason" ]] && break
  capture; [[ -s "$REC/observed-cmdline.nul" ]] && break
  running "$SIM" || break
  sleep 0.02
done
while [[ -z "$reason" ]] && running "$SIM"; do
  capture
  el=$(awk -v a="$(date +%s.%N)" -v b="$t0" 'BEGIN{printf "%.1f", a-b}')
  if awk -v e="$el" -v c="$CAP" 'BEGIN{exit !(e > c)}'; then reason="wall time ${el} s exceeds the cap ${CAP} s"
  elif [[ -e "$EVD/STOP" ]]; then reason="STOP declared: $(cat "$EVD/STOP" 2>/dev/null)"
  else sample in-run || true
  fi
  if [[ -n "$reason" ]]; then kill_tree "$SIM" "$reason"; break; fi
  date +%s > "$REC/watchdog.heartbeat"
  sleep "$POLL"
done
wait "$SIM"; rc=$?
t1=$(date +%s.%N)
fb=$(measure)
printf '%s\t%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$(awk -v a="$t1" -v b="$t0" 'BEGIN{printf "%.3f", a-b}')" final "${fb:-ERR}" "" "no/no" >> "$REC/watchdog.tsv"
{
  echo "simulation_exit: $rc"
  echo "wall_s: $(awk -v a="$t1" -v b="$t0" 'BEGIN{printf "%.3f", a-b}')"
  echo "final_output_bytes: $(numeric "$fb")"
  echo "in_run_samples: $insamples"
  echo "sampled_max_output_bytes: ${maxb:-NOT MEASURED}"
  echo "sampled_peak_vmhwm_kib: ${hwm:-NOT MEASURED}"
  echo "observed_identity_captured: $([[ -s "$REC/observed-cmdline.nul" ]] && echo yes || echo no)"
  echo "watchdog_terminated: ${reason:-no}"
} >> "$CTL"
[[ -z "$reason" ]] || exit 4
exit "$rc"
