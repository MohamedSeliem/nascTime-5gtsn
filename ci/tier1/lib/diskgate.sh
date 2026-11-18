#!/usr/bin/env bash
# usage: diskgate.sh <checkpoint>. Free space on / must be >= START_MIN_FREE_GIB; otherwise STOP (90).
set -u
a=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
echo "$(date -u +%FT%TZ) [$1] root_avail_B=$a" >> "$EV/disk-gates.txt"
if (( a < START_MIN_FREE_GIB * 1073741824 )); then
  echo "disk gate at $1: free $a B < $START_MIN_FREE_GIB GiB" > "$EV/STOP.tmp" && mv -f "$EV/STOP.tmp" "$EV/STOP"
  echo "::error::STOP: $(cat "$EV/STOP")"; exit 90
fi
