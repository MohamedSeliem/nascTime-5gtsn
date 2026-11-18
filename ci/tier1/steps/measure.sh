#!/usr/bin/env bash
# Installed sizes and the local-build classification of the Nix store (non-gating evidence).
. "$(dirname "$0")/../lib/common.sh"
set +e
{
  [[ -d /nix/store ]] && echo "nix_store_bytes_final: $(du -sb /nix/store 2>/dev/null | cut -f1)"
  for d in "$WS"/*/; do [[ -d "$d" ]] && echo "tree_bytes_final $(basename "$d"): $(du -sb "$d" | cut -f1)"; done
  [[ -d "$WS" ]] && echo "workspace_bytes_total: $(du -sb "$WS" 2>/dev/null | cut -f1)"
  echo "root_avail_final_B: $(df -B1 --output=avail / | tail -1 | tr -d ' ')"
} | tee -a "$EV/sizes.txt"
df -B1 -T > "$EV/df-end.txt"
# shellcheck disable=SC2086
if command -v nix > /dev/null && nix $NIX_X path-info --all --json > "$UNPUB/path-info.json" 2>/dev/null; then pi=ok; else pi=failed; fi
/usr/bin/python3 -I "$PY/nixstore.py" "$UNPUB/path-info.json" "$EV/nix-store-summary.txt" "$pi"
cat "$EV/nix-store-summary.txt"
exit 0
