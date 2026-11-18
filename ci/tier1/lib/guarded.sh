#!/usr/bin/env bash
# usage: guarded.sh <label> <command...>
# Checks guard liveness, runs the command in its own session / process group (killable by the guard),
# logs to $EV/<label>.log (not streamed to the public console), records the wall time, re-checks the
# guard, and fails closed on STOP (90), guard failure (91) or exhausted time budget (92; 124 = timed out).
# Time limit = min(STAGE_CAP_S if set, job start + JOB_BUDGET_S - RESERVE_S - now). On a command failure
# it prints a screened log tail, or a suppression notice.
set -uo pipefail
label=$1; shift
"$T1_LIB/guard-alive.sh" "before $label" || exit 91
[[ ! -e "$EV/STOP" ]] || { echo "::error::STOP already declared: $(cat "$EV/STOP")"; exit 90; }
t0=$(date +%s)
remaining=$(( JOB_START + JOB_BUDGET_S - RESERVE_S - t0 ))
if (( remaining < 120 )); then
  printf '%s\t0\t92\t%s\t%s\n' "$label" "$t0" "$t0" >> "$EV/timings.tsv"
  echo "::error::$label not started: remaining job time budget ${remaining}s"; exit 92
fi
budget=$remaining
if [[ -n "${STAGE_CAP_S:-}" ]] && (( STAGE_CAP_S < budget )); then budget=$STAGE_CAP_S; fi
echo "$label: time limit ${budget}s"
setsid timeout -k 60 "$budget" "$@" > "$EV/$label.log" 2>&1 < /dev/null &
pid=$!
echo "$pid" > "$EV/guard.target"
pg=""
for _ in $(seq 1 50); do
  pg=$(ps -o pgid= -p "$pid" 2>/dev/null | tr -d ' ')
  [[ -z "$pg" || "$pg" == "$pid" ]] && break
  sleep 0.1
done
if [[ -n "$pg" && "$pg" != "$pid" ]]; then
  kill -KILL "$pid" 2>/dev/null
  echo "guarded process $pid is not its own process group" > "$EV/GUARD_FAILURE"
  echo "::error::INFRASTRUCTURE FAILURE: guarded process is not killable as a group"; exit 91
fi
# Race: STOP may have been declared just before registration. Kill here too; the guard also re-kills.
if [[ -e "$EV/STOP" ]]; then kill -TERM -- "-$pid" 2>/dev/null; sleep 2; kill -KILL -- "-$pid" 2>/dev/null; fi
wait "$pid"; rc=$?
kill -KILL -- "-$pid" 2>/dev/null   # no stragglers of the stage's process group survive it
: > "$EV/guard.target"
t1=$(date +%s)
printf '%s\t%s\t%s\t%s\t%s\n' "$label" "$(( t1 - t0 ))" "$rc" "$t0" "$t1" >> "$EV/timings.tsv"
[[ "$rc" != 124 ]] || echo "::error::$label exceeded its time limit (${budget}s)"
echo "$label: exit $rc after $(( $(date +%s) - t0 )) s"
if [[ "$rc" != 0 ]]; then
  tail -n 40 "$EV/$label.log" | sed 's/\x1b\[[0-9;?]*[A-Za-z]//g; s/\r/\n/g' > "$E2B/tail.tmp"
  if /usr/bin/python3 -I "$T1_LIB/screen.py" "$E2B/tail.tmp" > /dev/null; then
    echo "::group::$label log tail (screened)"; cat "$E2B/tail.tmp"; echo "::endgroup::"
  else
    echo "$label log tail suppressed: screening matched a sensitive-content pattern"
  fi
fi
"$T1_LIB/guard-alive.sh" "after $label" || exit 91
if [[ -e "$EV/STOP" ]]; then echo "::error::STOP: $(cat "$EV/STOP")"; exit 90; fi
exit "$rc"
