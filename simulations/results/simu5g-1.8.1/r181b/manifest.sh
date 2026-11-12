#!/bin/bash
# M2-R181b manifest of a runs directory, written BEFORE any of its raw data is deleted.
#   manifest.sh <runs dir> <out prefix>
# <out prefix>-files.sha256 : sha256 of every raw file (all types), paths relative to the runs dir, sorted
# <out prefix>-manifest.txt : per configuration (top-level directory): files, bytes, sha256 of its file list
#                             (the sha256 of its lines in -files.sha256), and its run log's last line
set -eo pipefail
R=$1; P=$2
[ -d "$R" ] || { echo "ERROR: $R missing" >&2; exit 1; }
(cd "$R" && find . -type f | LC_ALL=C sort | sed 's|^\./||' | xargs -d '\n' sha256sum) > "$P-files.sha256"
{
  echo "# manifest of $R ($(date -u +%FT%TZ)); per configuration: files | bytes | sha256 of its hash lines | run log last line"
  for d in $(cd "$R" && find . -mindepth 1 -maxdepth 1 -type d | LC_ALL=C sort | sed 's|^\./||'); do
    n=$(grep -c "  $d/" "$P-files.sha256" || true)
    b=$(du -sb "$R/$d" | cut -f1)
    h=$(grep "  $d/" "$P-files.sha256" | sha256sum | cut -c1-16)
    l=$(tail -1 "$R/run-$d.log" 2>/dev/null | tr -d '\r' | cut -c1-120)
    echo "$d | $n | $b | $h | ${l:-no run log}"
  done
} > "$P-manifest.txt"
echo "manifest: $(grep -vc '^#' "$P-manifest.txt") configurations, $(wc -l < "$P-files.sha256") files"
