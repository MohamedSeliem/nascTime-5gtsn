#!/usr/bin/env bash
# usage: lockcheck.sh <phase> [log...]. Gate: both locks must equal their approved sha256, and no
# Nix lock-update message may appear in the given logs. Exit 1 on any failure.
set -uo pipefail
phase=$1; shift
A="$WS/.opp_env_workspace"; ok=1
a=$(sha256sum "$A/26.05/flake.lock" 2>/dev/null | cut -c1-64)
h=$(sha256sum "$A/22.11/flake.lock" 2>/dev/null | cut -c1-64)
echo "$phase approved_26.05: ${a:-missing}" >> "$EV/lock.txt"
echo "$phase helper_22.11: ${h:-missing}" >> "$EV/lock.txt"
[[ "$a" == "$LOCK_SHA256" ]] || ok=0
[[ "$h" == "$HELPER_LOCK_SHA256" ]] || ok=0
for log in "$@"; do
  if grep -qiE 'updating lock file|creating lock file|not writing (modified )?lock file|requires lock file changes' "$log"; then
    echo "$phase lock_update_message_in: $(basename "$log")" >> "$EV/lock.txt"; ok=0
  fi
done
if (( ok == 1 )); then echo "$phase result: PASS" >> "$EV/lock.txt"; exit 0; fi
echo "$phase result: FAIL" >> "$EV/lock.txt"
echo "::error::lock gate failed at $phase"; exit 1
