#!/usr/bin/env bash
# Disk guard. Samples free space on / and on $RUNNER_TEMP's filesystem, plus MemAvailable, every
# GUARD_INTERVAL_S seconds and writes a heartbeat. On a breach it declares STOP (atomically) and stops
# the Nix daemon. While STOP exists it kills any registered guarded process group on every iteration,
# which also covers a group registered after STOP was declared. Exits when guard.off appears.
set -u
echo "$$" > "$EV/guard.pid"
limit=$(( STOP_FREE_GIB * 1073741824 ))
printf 'utc\tpath\tavail_B\tused_B\tmem_avail_kib\n' > "$EV/disk.tsv"
kill_target() {
  local pg
  pg=$(cat "$EV/guard.target" 2>/dev/null)
  [[ -n "$pg" ]] || return 0
  kill -TERM -- "-$pg" 2>/dev/null || return 0
  echo "$(date -u +%FT%TZ) TERM sent to process group $pg" >> "$EV/guard-actions.txt"
  sleep 5
  kill -KILL -- "-$pg" 2>/dev/null && echo "$(date -u +%FT%TZ) KILL sent to process group $pg" >> "$EV/guard-actions.txt"
  return 0
}
while [[ ! -e "$EV/guard.off" ]]; do
  date +%s > "$EV/guard.heartbeat.tmp" && mv -f "$EV/guard.heartbeat.tmp" "$EV/guard.heartbeat"
  mem=$(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)
  for p in / "$RUNNER_TEMP"; do
    read -r avail used < <(df -B1 --output=avail,used "$p" | tail -1)
    printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$p" "$avail" "$used" "$mem" >> "$EV/disk.tsv"
    if (( avail < limit )) && [[ ! -e "$EV/STOP" ]]; then
      echo "disk guard: free $avail B on $p < $STOP_FREE_GIB GiB" > "$EV/STOP.tmp" && mv -f "$EV/STOP.tmp" "$EV/STOP"
      echo "$(date -u +%FT%TZ) STOP declared" >> "$EV/guard-actions.txt"
      sudo systemctl stop nix-daemon.socket nix-daemon.service 2>/dev/null || true
    fi
  done
  [[ -e "$EV/STOP" ]] && kill_target
  sleep "$GUARD_INTERVAL_S"
done
date -u +%FT%TZ > "$EV/guard.exited"
