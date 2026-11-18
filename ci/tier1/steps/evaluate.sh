#!/usr/bin/env bash
# Terminates the disk guard (confirmed) and evaluates C-1 .. C-14.
. "$(dirname "$0")/../lib/common.sh"
set +e
mkdir -p "$EV"
[[ -x "$T1_LIB/guard-alive.sh" && -f "$EV/guard.pid" ]] && "$T1_LIB/guard-alive.sh" "evaluation"
touch "$EV/guard.off"
pid=$(cat "$EV/guard.pid" 2>/dev/null)
term=not-started
if [[ -n "$pid" ]]; then
  term=no
  for _ in $(seq 1 30); do
    st=$(ps -o stat= -p "$pid" 2>/dev/null | tr -d ' ')
    [[ -z "$st" || "$st" == Z* ]] && { term=yes; break; }
    sleep 1
  done
fi
{
  echo "guard_pid: ${pid:-none}"
  echo "guard_terminated: $term"
  echo "guard_exited_marker: $([[ -e "$EV/guard.exited" ]] && cat "$EV/guard.exited" || echo absent)"
  n=$(grep -c ' ok \[' "$EV/guard-checks.txt" 2>/dev/null); echo "liveness_checks_ok: ${n:-0}"
  n=$(grep -c ' FAIL \[' "$EV/guard-checks.txt" 2>/dev/null); echo "liveness_checks_failed: ${n:-0}"
} | tee "$EV/guard.txt"
/usr/bin/python3 -I "$PY/evaluate.py"
