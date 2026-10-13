#!/bin/bash
# Runs the three Simu5G issue reproductions (issues.ini) against Simu5G 1.8.0 only: a
# scratch copy of Simu5G's simulations/nr/ethernet directory, NED path Simu5G + INET (no
# nascTime), seed 0. Then check_issues.py prints the evidence. About 3 min.
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
OUT=${OUT:-$HERE/../results/upstream-issues}
WORK=$(mktemp -d)
trap 'rm -rf "$WORK"' EXIT
source "$OMNETPP_ROOT/setenv" -f >/dev/null
mkdir -p "$OUT"
cp -r "$SIMU5G_ROOT/simulations" "$WORK/"           # 5.5 MB; upstream tree stays untouched
rm -rf "$WORK/simulations/nr/ethernet/results"
cp "$HERE/issues.ini" "$WORK/simulations/nr/ethernet/"
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_ethernet_example_sha256: $(sha256sum "$SIMU5G_ROOT/simulations/nr/ethernet/omnetpp.ini" "$SIMU5G_ROOT/simulations/nr/ethernet/EthernetSessions.ned" | awk '{print $1}' | tr '\n' ' ')"
  echo "issues_ini_sha256: $(sha256sum "$HERE/issues.ini" | awk '{print $1}')"
  echo "nascTime_commit: $(git -C "$HERE" rev-parse HEAD 2>/dev/null || echo n/a)"
} > "$OUT/env.txt"
run() {
  (cd "$WORK/simulations/nr/ethernet" && opp_run -l "$SIMU5G_ROOT/src/simu5g" -n "$WORK/simulations:$SIMU5G_ROOT/src:$INET_ROOT/src" \
     -u Cmdenv -f issues.ini -c "$1" -r 0 --result-dir="$OUT/runs" "${@:2}")
}
for c in Issue1-HarqDiscard Issue1-HarqDiscard-16proc Issue2-DlTailLag Issue2-DlTailLag-apart Issue3-RegionTags; do
  run "$c" --cmdenv-express-mode=true > "$OUT/run-$c.log" 2>&1 || { echo "ERROR: $c failed, see $OUT/run-$c.log" >&2; exit 1; }
  opp_scavetool export -o "$OUT/$c.csv" -F CSV-R "$OUT/runs/$c"/*.sca "$OUT/runs/$c"/*.vec >/dev/null
done
{ run Issue1-HarqDiscard-trace 2>&1; echo "EXIT=$?"; } \
  | grep -E '^EXIT=|<!> Error|(mac|nrMac) \| .*(created PDU|no available process|Using buffer for|extracted SDU)' > "$OUT/trace-Issue1.log" || true
grep -q "^EXIT=0$" "$OUT/trace-Issue1.log" || { echo "ERROR: trace run failed" >&2; exit 1; }
python3 "$HERE/check_issues.py" "$OUT" | tee "$OUT/check.txt"
