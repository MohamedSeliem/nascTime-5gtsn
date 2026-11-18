#!/usr/bin/env bash
# Work directories, tested-commit identity (PR head, base and merge commit), runner capacity, start gate, disk guard,
# and the content check of the approved lock in the tested tree.
. "$(dirname "$0")/../lib/common.sh"
rm -rf "$CI"; mkdir -p "$EV" "$DL" "$UNPUB" "$EXEC" "$PROBES"
date +%s > "$CI/job-start"; JOB_START=$(cat "$CI/job-start"); export JOB_START
printf 'step\tseconds\texit\tstart_epoch\tend_epoch\n' > "$EV/timings.tsv"
: > "$EV/exec-checks.txt"
# Tested commits (C3). For pull_request events GITHUB_SHA is the merge commit GitHub created from the PR head and base.
head=$(git -C "$REPO" rev-parse HEAD)
p1=$(git -C "$REPO" rev-parse -q --verify HEAD^1 || echo none)
p2=$(git -C "$REPO" rev-parse -q --verify HEAD^2 || echo none)
{
  echo "event: ${GITHUB_EVENT_NAME:-unknown}"
  echo "pr_number: ${PR_NUMBER:-none}"
  echo "pr_head_sha: ${PR_HEAD_SHA:-none}"
  echo "pr_base_sha: ${PR_BASE_SHA:-none}"
  echo "pr_base_ref: ${PR_BASE_REF:-none}"
  echo "tested_merge_sha: $head"
  echo "github_sha: ${GITHUB_SHA:-none}"
  echo "merge_parent_1_base: $p1"
  echo "merge_parent_2_head: $p2"
  echo "merge_parent_1_equals_event_base: $([[ "$p1" == "${PR_BASE_SHA:-}" ]] && echo yes || echo "no (base advanced after the event or a different merge base)")"
  echo "run: ${GITHUB_RUN_ID:-local} attempt ${GITHUB_RUN_ATTEMPT:-1}"
  echo "pins_sha256: $(sha256sum "$T1_DIR/pins.env" | cut -c1-64)"
  echo "workflow_sha256: $(sha256sum "$REPO/.github/workflows/tier1-full-stack.yml" | cut -c1-64)"
} | tee "$EV/identity.txt"
[[ "$head" == "${GITHUB_SHA:-}" ]] || { echo "::error::checked-out commit $head is not GITHUB_SHA"; exit 1; }
if [[ "${GITHUB_EVENT_NAME:-}" == pull_request ]]; then
  [[ "$p2" == "${PR_HEAD_SHA:-}" ]] || { echo "::error::the tested merge commit does not contain the PR head as its second parent"; exit 1; }
  [[ "${PR_BASE_REF:-}" == m2/continuation ]] || { echo "::error::PR base is not m2/continuation"; exit 1; }
fi
# Runner capacity (measured) and the start gate.
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "image_os: ${ImageOS:-unknown}"
  echo "image_version: ${ImageVersion:-unknown}"
  echo "os_release: $(. /etc/os-release && echo "$PRETTY_NAME")"
  echo "kernel: $(uname -srm)"
  echo "nproc: $(nproc)"
  echo "cpu_model: $(lscpu | sed -n 's/^Model name:[[:space:]]*//p' | head -1)"
  echo "mem_total_kib: $(awk '/^MemTotal:/ {print $2}' /proc/meminfo)"
  echo "mem_available_start_kib: $(awk '/^MemAvailable:/ {print $2}' /proc/meminfo)"
  echo "swap_total_kib: $(awk '/^SwapTotal:/ {print $2}' /proc/meminfo)"
  echo "host_python: $(/usr/bin/python3 -V 2>&1)"
  echo "runner_temp_mount: $(df -B1 --output=target "$RUNNER_TEMP" | tail -1)"
  echo "root_avail_start_B: $(df -B1 --output=avail / | tail -1 | tr -d ' ')"
  echo "root_size_B: $(df -B1 --output=size / | tail -1 | tr -d ' ')"
} | tee "$EV/runner.txt"
df -B1 -T > "$EV/df-start.txt"
avail=$(df -B1 --output=avail / | tail -1 | tr -d ' ')
if (( avail < START_MIN_FREE_GIB * 1073741824 )); then
  echo "start gate: root free $avail B < $START_MIN_FREE_GIB GiB" > "$EV/STOP"
  echo "::error::STOP: $(cat "$EV/STOP")"; exit 1
fi
# Disk guard (runs until the evaluation step terminates it).
bash -c "nohup setsid \"$T1_LIB/guard.sh\" > \"$EV/guard-stderr.log\" 2>&1 < /dev/null &"
for _ in $(seq 1 20); do [[ -s "$EV/guard.heartbeat" ]] && break; sleep 0.5; done
"$T1_LIB/guard-alive.sh" "guard start"
echo "disk guard running, pid $(cat "$EV/guard.pid")"
# The approved lock in the tested tree (C-1/C-2): size, sha256 and content.
L="$REPO/$LOCK_FILE"
size=$(stat -c %s "$L"); sum=$(sha256sum "$L" | cut -c1-64)
echo "repository approved_26.05: $sum" > "$EV/lock.txt"
[[ "$size" == "$LOCK_SIZE" && "$sum" == "$LOCK_SHA256" ]] || { echo "::error::approved lock mismatch (size $size, sha256 $sum)"; exit 1; }
/usr/bin/python3 -I "$PY/lock_content.py" "$L"
