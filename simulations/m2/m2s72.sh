#!/bin/bash
# M2-S7.2a: several UEs and DS-TTs, downlink, static roles (migration/m2-s7.2a-design.md revision 2).
# Stages 1-3 (Checkpoint 1): configuration regeneration, gate F0 (feasibility) and gate T0 (numUe = 1
# equivalence). Builds libnasctime_m2 and runs m2s72.ini (generated, includes omnetpp.ini) and, for the T0
# references, omnetpp.ini, on unmodified OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0.
#   ./m2s72.sh regen    regeneration check of m2s72.ini + flattening vs OMNeT++ runconfig -> results/M2-S7.2a-cp1r2/regen.txt
#   ./m2s72.sh f0       F0 census runs (+ eventlog and no-learning-recorder twins) and F0-6 negative controls,
#                       F0 check (check_m2s72_f0r2.py, design rev. 2.1) -> f0-check.txt,
#                       comparator canaries -> comparator-canaries.txt   (f0check: the checks only)
#   ./m2s72.sh t0       T0 runs (M2S72-T0-*) and their M1Bridge references, T0 check     -> t0-check.txt (t0check: check only)
#   ./m2s72.sh hashes   sha256 of every PCAP and log of the runs                             -> raw-outputs.sha256
#   ./m2s72.sh all      regen f0 t0 hashes                                           (Checkpoint 1 rev. 2)
#   ./m2s72.sh b        stage 4 Block B runs and check (check_m2s72_b.py) -> results/M2-S7.2a-cp2/b-check.txt
#   ./m2s72.sh cp2      regen, b, hashes into results/M2-S7.2a-cp2                        (Checkpoint 2)
#   ./m2s72.sh b2       Checkpoint 2 rev. 2 runs (Block B, Block H, controls) and check -> results/M2-S7.2a-cp2r2/b-check.txt
#   ./m2s72.sh cp2r2    regen, b2, hashes into results/M2-S7.2a-cp2r2                     (Checkpoint 2 revision 2)
# Requires OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (or the defaults below); T0 also needs the committed
# results/M2-S7.1/raw-outputs.sha256 and results/M2-S6/raw-outputs.sha256.
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
JOBS=${JOBS:-2}
MODE=${1:-all}
# Checkpoint 1 revision 2 (design rev. 2.1): records go to results/M2-S7.2a-cp1r2; the Checkpoint 1 record
# (results/M2-S7.2a, produced at dfedb52) is kept unchanged.
OUT=$HERE/results/M2-S7.2a-cp1r2
# Checkpoint 2 (stage 4, Block B): records go to results/M2-S7.2a-cp2
case "$MODE" in b|bcheck|cp2|cp2regen|cp2hashes) OUT=$HERE/results/M2-S7.2a-cp2 ;; esac
# Checkpoint 2 revision 2 (corrective round): results/M2-S7.2a-cp2r2; the Checkpoint 2 record is kept unchanged
case "$MODE" in b2|b2check|cp2r2|cp2r2regen|cp2r2hashes) OUT=$HERE/results/M2-S7.2a-cp2r2 ;; esac
CHK=$HERE/check
mkdir -p "$OUT"
"$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/build.log" 2>&1 || { echo "ERROR: build failed, see $OUT/build.log" >&2; exit 1; }
source "$OMNETPP_ROOT/setenv" -f >/dev/null
{
  echo "date_utc: $(date -u +%FT%TZ)"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
  echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version" 2>/dev/null || echo n/a)"
  echo "compiler: $(clang++ --version 2>/dev/null | head -1)"
  echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m1 simulations/m2 src/nasctime ':!simulations/m1/results' ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted/untracked changes in simulations/m1, simulations/m2 or src/nasctime)')"
  echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -d' ' -f1)"
  echo "m2s72_ini_sha256: $(sha256sum "$HERE/m2s72.ini" | cut -d' ' -f1)"
  echo "python: $(python3 --version 2>&1)"
  echo "os: $(uname -srm)"
} > "$OUT/env-$MODE.txt"

OPP=(opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes -u Cmdenv)

# run <ini> <config> <repetitions> <root dir under OUT> [extra opp_run arguments...]
run() {
  local ini=$1 cfg=$2 reps=$3 root=$4; shift 4
  rm -rf "$OUT/$root/$cfg"
  mkdir -p "$OUT/$root"
  local express=--cmdenv-express-mode=true
  case "$cfg" in *-ev|M2S72-B-*|M2S72-BN-*|M2S72-H-*) express=--cmdenv-express-mode=false ;; esac   # eventlog (M2S72-ev): UPF MAC-table log lines
  (cd "$HERE" && opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
     -u Cmdenv -f "$ini" -c "$cfg" --repeat=10 -r "$reps" --result-dir="$OUT/$root/$cfg" \
     "$express" "$@" > "$OUT/$root/run-$cfg.log" 2>&1) \
  || { echo "ERROR: $cfg failed, see $OUT/$root/run-$cfg.log" >&2; return 1; }
}
runline() { local root=$1 ini=$2 cfg=$3 reps=$4; shift 4; run "$ini" "$cfg" "$reps" "$root" "$@"; }
export -f run runline
export HERE NASCTIME SIMU5G_ROOT OUT
# lines "ini config reps [extra opp_run args]" from stdin into root dir $1
runlist() { local root=$1; shift; xargs -P "$JOBS" -L 1 bash -c 'runline "'"$root"'" "$@"' _; }

regen() {
  {
    echo "M2-S7.2a configuration regeneration record (design rev. 2, 1.4, D-2 (a))"
    echo "m2s72.ini sha256 $(sha256sum "$HERE/m2s72.ini" | cut -d' ' -f1)"
    echo "omnetpp.ini sha256 $(sha256sum "$HERE/omnetpp.ini" | cut -d' ' -f1)"
    echo "../m1/omnetpp.ini sha256 $(sha256sum "$HERE/../m1/omnetpp.ini" | cut -d' ' -f1)"
    echo "tools/m2s72_gen.py sha256 $(sha256sum "$HERE/tools/m2s72_gen.py" | cut -d' ' -f1)"
    echo; echo "== python3 tools/m2s72_gen.py check (regenerate in memory, compare byte for byte)"
    (cd "$HERE" && python3 tools/m2s72_gen.py check) && echo "check rc 0" || echo "check rc $?"
    echo; echo "== python3 tools/m2s72_gen.py verify (flattening vs opp_run -q runconfig)"
    (cd "$HERE" && python3 tools/m2s72_gen.py verify "${OPP[@]}" -f omnetpp.ini) && echo "verify rc 0" || echo "verify rc $?"
    echo; echo "== generator negative tests (each must stop with an error and write nothing)"
    python3 "$CHK/test_m2s72_gen.py"
  } > "$OUT/regen.txt" 2>&1
  cat "$OUT/regen.txt"
}

f0_configs() {
  for o in q0 qdu; do for n in 1 2 4 8; do
    for s in "" -ev -norec; do echo "m2s72.ini M2S72-F0-$o-n$n$s 0 --fingerprint=0000-0000/tplx"; done
  done; done
  for c in missing vlan age port; do for s in "" -ev; do echo "m2s72.ini M2S72-F0N-$c$s 0 --fingerprint=0000-0000/tplx"; done; done
}
b_configs() {
  for o in q0 qdu; do for c in ideal Ca Eall; do for n in 1 2 4; do
    echo "m2s72.ini M2S72-B-$o-$c-n$n 0..4 --fingerprint=0000-0000/tplx"
  done; done; done
  echo "m2s72.ini M2S72-BN-theta1 0 --fingerprint=0000-0000/tplx"
}
b2_configs() {
  b_configs
  for o in q0 qdu; do for n in 2 4; do echo "m2s72.ini M2S72-H-$o-Ca-n$n 0..4 --fingerprint=0000-0000/tplx"; done; done
  echo "m2s72.ini M2S72-BN-rng 0 --fingerprint=0000-0000/tplx"
}
t0_configs() {
  for s in q0-idle qdu-idle q0-load C-a E-all; do echo "m2s72.ini M2S72-T0-$s 0"; done
}
t0_refs() {
  for c in M2S71-q0-idle M2S71-qdu-idle M2S71-q0-load M2S6-C-a M2S6-E-all; do echo "omnetpp.ini $c 0"; done
}

case "$MODE" in
  regen) regen ;;
  f0) f0_configs | runlist runs
      python3 "$CHK/check_m2s72_f0r2.py" "$OUT" > "$OUT/f0-check.txt" || true
      python3 "$CHK/test_m2s72_compare.py" "$OUT" M2S72-F0-q0-n2 > "$OUT/comparator-canaries.txt" 2>&1 || true
      tail -1 "$OUT/comparator-canaries.txt"
      tail -3 "$OUT/f0-check.txt" ;;
  f0check) python3 "$CHK/check_m2s72_f0r2.py" "$OUT" > "$OUT/f0-check.txt" || true
      python3 "$CHK/test_m2s72_compare.py" "$OUT" M2S72-F0-q0-n2 > "$OUT/comparator-canaries.txt" 2>&1 || true
      tail -1 "$OUT/comparator-canaries.txt"
      tail -3 "$OUT/f0-check.txt" ;;
  t0check) python3 "$CHK/check_m2s72_t0.py" "$OUT" "$HERE/results" > "$OUT/t0-check.txt" || true
      tail -2 "$OUT/t0-check.txt" ;;
  t0) t0_configs | runlist runs
      t0_refs | runlist ref
      python3 "$CHK/check_m2s72_t0.py" "$OUT" "$HERE/results" > "$OUT/t0-check.txt" || true
      tail -2 "$OUT/t0-check.txt" ;;
  b) b_configs | runlist runs
     python3 "$CHK/check_m2s72_b.py" "$OUT" > "$OUT/b-check.txt" || true
     tail -2 "$OUT/b-check.txt" ;;
  bcheck) python3 "$CHK/check_m2s72_b.py" "$OUT" > "$OUT/b-check.txt" || true
     tail -2 "$OUT/b-check.txt" ;;
  cp2regen) regen ;;
  cp2hashes) (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  cp2) for s in cp2regen b cp2hashes; do "$0" "$s" || exit $?; done ;;
  b2) b2_configs | runlist runs
     python3 "$CHK/check_m2s72_b.py" "$OUT" > "$OUT/b-check.txt" || true
     tail -2 "$OUT/b-check.txt" ;;
  b2check) python3 "$CHK/check_m2s72_b.py" "$OUT" > "$OUT/b-check.txt" || true
     tail -2 "$OUT/b-check.txt" ;;
  cp2r2regen) regen ;;
  cp2r2hashes) (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  cp2r2) for s in cp2r2regen b2 cp2r2hashes; do "$0" "$s" || exit $?; done ;;
  hashes) (cd "$OUT" && find runs ref -type f \( -name '*.pcapng' -o -name '*.csv' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  all) for s in regen f0 t0 hashes; do "$0" "$s" || exit $?; done ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
