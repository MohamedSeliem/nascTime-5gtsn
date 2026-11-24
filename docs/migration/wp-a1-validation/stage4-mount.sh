#!/usr/bin/env bash
# WP-A1 validation, Stage 4 (runbook revision 3): DR-13 method (a), the read-only mount of X at R, checked without
# creating anything. Runs in the network-less evaluation container (X and R read-only).
STAGE=stage4-mount
. "$(dirname "$0")/common.sh"
load_vars
gate_b_go
need_done stage3-x2a
ro_path "$R"
ro_path "$X"
O="$E/x2a"
[ ! -e "$O/mount.txt" ] || stop "$O/mount.txt exists (single attempt)"
# the mount shows exactly the extraction: same relative paths, sizes and types
diff <(cd "$R" && find . -printf '%y %s %p\n' | LC_ALL=C sort) <(cd "$X" && find . -printf '%y %s %p\n' | LC_ALL=C sort) \
  > "$O/mount-vs-x.txt" || stop "the mount at $R does not show the extraction X (see $O/mount-vs-x.txt)"
{ echo "DR-13 method (a): read-only mount of $X at $R, for evaluation"; findmnt --target "$R"; findmnt --target "$X"; } > "$O/mount.txt"
done_mark stage4-mount
echo "Stage 4: read-only mount verified"
exit 0
