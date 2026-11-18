#!/usr/bin/env bash
# usage: guard-alive.sh <checkpoint>. Exit 91 (infrastructure failure) unless the guard process exists
# and its heartbeat is fresh.
set -u
cp=$1
now=$(date +%s)
pid=$(cat "$EV/guard.pid" 2>/dev/null || true)
hb=$(cat "$EV/guard.heartbeat" 2>/dev/null || echo 0)
age=$(( now - hb ))
state=$(ps -o stat= -p "${pid:-0}" 2>/dev/null | tr -d ' ')
if [[ -n "$pid" && -n "$state" && "$state" != Z* ]] && (( age <= GUARD_STALE_S )); then
  echo "$(date -u +%FT%TZ) ok [$cp] pid=$pid heartbeat_age_s=$age" >> "$EV/guard-checks.txt"
  exit 0
fi
echo "$(date -u +%FT%TZ) FAIL [$cp] pid=${pid:-none} heartbeat_age_s=$age" >> "$EV/guard-checks.txt"
echo "disk guard not alive at checkpoint: $cp" > "$EV/GUARD_FAILURE"
echo "::error::INFRASTRUCTURE FAILURE: disk guard not alive at checkpoint: $cp"
exit 91
