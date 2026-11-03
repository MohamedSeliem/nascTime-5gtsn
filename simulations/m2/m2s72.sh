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
#   ./m2s72.sh r2       Checkpoint 2 revision 2 complete campaign (review 2026-11-02 16:58): regen, Block B, BN controls,
#                       Block H16 (Q-0 correctness, Q-d diagnostic), I-2H controls, check (check_m2s72_cp2r2.py), hashes
#                       -> results/M2-S7.2a-cp2r2 (must not exist before; r2check: check only)
#   ./m2s72.sh i2h      I-2H focused validation: regen, Block H + HARQ16 runs, I-5 references, I-2H controls,
#                       check (check_m2s72_i2h.py focused), hashes -> results/M2-S7.2a-i2h       (i2hcheck: check only)
#   ./m2s72.sh e0       Stage 5 E0 capacity calibration (authorisation 2026-11-03 11:35; protocol
#                       results/M2-S7.2a-e0-protocol.md): regen, the E0 runs one at a time in increasing DL load factor
#                       with the declared stop conditions (free space, run time, escalation stop), the MAC-log twin, hashes,
#                       check (check_m2s72_e0.py) -> results/M2-S7.2a-e0 (must not exist before; e0check: check only)
#   ./m2s72.sh e0r2     E0 revision 2 (decision 2026-11-03 13:27): NO simulation. Verifies the E0 raw outputs against the
#                       committed results/M2-S7.2a-e0/raw-outputs.sha256, then reruns the E0 check with the corrected positive
#                       control (check_m2s72_e0.py r2) -> results/M2-S7.2a-e0r2 (must not exist before)
#   SIMU5G_ROOT=<isolated candidate build> ./m2s72.sh cfqd
#                       Q-d uplink scheduler counterfactual (decision 2026-11-03 14:01): refuses the accepted /root/stack
#                       Simu5G and any build whose LteSchedulerEnb.cc differs from 1.8.0 by other than the committed
#                       results/M2-S7.2a-cfqd-candidate-fix.patch; runs M2S72-E0-q0-f1 and M2S72-E0-qdu-f1 on it, hashes,
#                       check (check_m2s72_cfqd.py, E0 outputs re-used as the original-build side) -> results/M2-S7.2a-cfqd
#   M2S72_E2_AUTH="<decision reference>" ./m2s72.sh e2rb
#                       Stage 5 E2 step 0, DL-only re-baseline (PREPARED 2026-11-03 20:05, NOT authorised to run): refuses
#                       to start without M2S72_E2_AUTH, with any Simu5G other than the accepted 1.8.0 library, or with an
#                       existing results/M2-S7.2a-e2rb; regen, the 4 runs M2S72-E2-<q0|qdu>-one0-n1-f<1|2> with the E0 stop
#                       conditions, hashes, check (check_m2s72_e2.py rebaseline: the acceptance checkpoint of
#                       results/M2-S7.2a-e2-protocol.md section 4) -> results/M2-S7.2a-e2rb       (e2rbcheck: check only)
#                       Revision 2.1: the SG-403 safeguard (diag_m2s72_dl_active.py --classify) after every run; a
#                       CONFIRMED-403 or UNEXPLAINED TTI stops the batch for review; no raw output is ever deleted
# Requires OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (or the defaults below); T0 also needs the committed
# results/M2-S7.1/raw-outputs.sha256 and results/M2-S6/raw-outputs.sha256.
set -eo pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
export OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}
export INET_ROOT=${INET_ROOT:-/root/stack/inet-4.7.0}
SIMU5G_ROOT=${SIMU5G_ROOT:-/root/stack/simu5g-1.8.0}
ACCEPTED_LIBSIMU5G_SHA256=203cf231e6605188662769b439e403d832f516d2e08c8a0c5a9e8f55f4305cf6
JOBS=${JOBS:-2}
MODE=${1:-all}
# Checkpoint 1 revision 2 (design rev. 2.1): records go to results/M2-S7.2a-cp1r2; the Checkpoint 1 record
# (results/M2-S7.2a, produced at dfedb52) is kept unchanged.
OUT=$HERE/results/M2-S7.2a-cp1r2
# Checkpoint 2 (stage 4, Block B): records go to results/M2-S7.2a-cp2
case "$MODE" in b|bcheck|cp2|cp2regen|cp2hashes) OUT=$HERE/results/M2-S7.2a-cp2 ;; esac
# Checkpoint 2 revision 2 (corrective round): results/M2-S7.2a-cp2r2; the Checkpoint 2 record is kept unchanged
case "$MODE" in b2|b2check|cp2r2|cp2r2regen|cp2r2hashes) OUT=$HERE/results/M2-S7.2a-cp2r2 ;; esac
# I-2H focused validation (review 2026-11-02 16:12): results/M2-S7.2a-i2h
case "$MODE" in i2h|i2hrun|i2hcheck|i2hregen|i2hhashes) OUT=$HERE/results/M2-S7.2a-i2h ;; esac
# Checkpoint 2 revision 2 complete campaign: results/M2-S7.2a-cp2r2 (empty at the start; r2 refuses an existing one)
case "$MODE" in r2|r2run|r2check|r2regen|r2hashes) OUT=$HERE/results/M2-S7.2a-cp2r2 ;; esac
if [ "$MODE" = r2 ] && [ -e "$OUT" ]; then echo "ERROR: $OUT exists; the campaign starts from an empty directory" >&2; exit 1; fi
# Stage 5 E0: results/M2-S7.2a-e0 (empty at the start; e0 refuses an existing one)
case "$MODE" in e0|e0run|e0check|e0regen|e0hashes) OUT=$HERE/results/M2-S7.2a-e0 ;; esac
if [ "$MODE" = e0 ] && [ -e "$OUT" ]; then echo "ERROR: $OUT exists; E0 starts from an empty directory" >&2; exit 1; fi
case "$MODE" in e0r2) OUT=$HERE/results/M2-S7.2a-e0r2; E0OUT=$HERE/results/M2-S7.2a-e0 ;; esac
if [ "$MODE" = cfqd ]; then
  OUT=$HERE/results/M2-S7.2a-cfqd; E0OUT=$HERE/results/M2-S7.2a-e0
  [ -e "$OUT" ] && { echo "ERROR: $OUT exists" >&2; exit 1; }
  ACCEPTED=/root/stack/simu5g-1.8.0
  [ "$(cd "$SIMU5G_ROOT" && pwd -P)" = "$(cd "$ACCEPTED" && pwd -P)" ] && { echo "ERROR: cfqd must not use the accepted Simu5G $ACCEPTED" >&2; exit 1; }
  F=src/simu5g/stack/mac/scheduler/LteSchedulerEnb.cc
  diff -u "$ACCEPTED/$F" "$SIMU5G_ROOT/$F" | tail -n +3 > /tmp/cfqd-actual.patch || true
  tail -n +3 "$HERE/results/M2-S7.2a-cfqd-candidate-fix.patch" | cmp -s - /tmp/cfqd-actual.patch \
    || { echo "ERROR: the candidate build's $F differs from 1.8.0 by other than the committed patch" >&2; exit 1; }
  (cd "$SIMU5G_ROOT/src" && diff -rq --exclude='*.o' --exclude='*.so' --exclude='*.d' --exclude='*_m.cc' --exclude='*_m.h' \
     --exclude=Makefile --exclude=features.h --exclude=out "$ACCEPTED/src" . | grep -v "^Files .*$F and" ) \
    && { echo "ERROR: the candidate build differs from 1.8.0 in other source files" >&2; exit 1; } || true
fi
case "$MODE" in e2rb|e2rbcheck) OUT=$HERE/results/M2-S7.2a-e2rb; E0OUT=$HERE/results/M2-S7.2a-e0 ;; esac
if [ "$MODE" = e2rb ]; then
  [ -n "$M2S72_E2_AUTH" ] || { echo "ERROR: e2rb is not authorised (set M2S72_E2_AUTH to the decision reference)" >&2; exit 1; }
  [ -e "$OUT" ] && { echo "ERROR: $OUT exists; the re-baseline starts from an empty directory" >&2; exit 1; }
  [ "$(cd "$SIMU5G_ROOT" && pwd -P)" = "$(cd /root/stack/simu5g-1.8.0 && pwd -P)" ] \
    || { echo "ERROR: e2rb runs only on the accepted Simu5G 1.8.0 (/root/stack/simu5g-1.8.0)" >&2; exit 1; }
  [ "$(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -d' ' -f1)" = "$ACCEPTED_LIBSIMU5G_SHA256" ] \
    || { echo "ERROR: libsimu5g.so differs from the accepted library" >&2; exit 1; }
  # rev. 2.1: the >= 20 GB start rule is checked before anything is built or created
  fr0=$(df -B1G --output=avail "$HERE" | tail -1 | tr -d ' ')
  [ "$fr0" -ge 20 ] || { echo "STOP: free $fr0 GB < 20 GB (start rule); nothing created" >&2; exit 3; }
fi
if [ "$MODE" = e0r2 ] && [ -e "$OUT" ]; then echo "ERROR: $OUT exists; revision 2 starts from an empty directory" >&2; exit 1; fi
E0_MIN_FREE_START_GB=20     # declared stop conditions (protocol §7)
E0_MIN_FREE_RUN_GB=10
declare -A E0_EST_MIN=([1]=4 [2]=6 [4]=10 [8]=18)   # run-time estimate (min) per DL factor; a run is stopped at 3 x
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
  case "$cfg" in *-ev|M2S72-B-*|M2S72-BN-*|M2S72-H-*|M2S72-H16*) express=--cmdenv-express-mode=false ;; esac   # eventlog (M2S72-ev): UPF MAC-table log lines
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
i2h_configs() {
  for o in q0 qdu; do echo "m2s72.ini M2S72-B-$o-Ca-n1 0..4 --fingerprint=0000-0000/tplx"; done
  for n in 2 4; do echo "m2s72.ini M2S72-H16-q0-Ca-n$n 0..4 --fingerprint=0000-0000/tplx"; done
  echo "m2s72.ini M2S72-H16-qdu-Ca-n2 0..4 --fingerprint=0000-0000/tplx"
  for c in nohold hto; do echo "m2s72.ini M2S72-H16N-$c 0 --fingerprint=0000-0000/tplx"; done
}
r2_configs() {
  b_configs
  echo "m2s72.ini M2S72-BN-rng 0 --fingerprint=0000-0000/tplx"
  for n in 2 4; do echo "m2s72.ini M2S72-H16-q0-Ca-n$n 0..4 --fingerprint=0000-0000/tplx"; done
  echo "m2s72.ini M2S72-H16-qdu-Ca-n2 0..4 --fingerprint=0000-0000/tplx"
  for c in nohold hto; do echo "m2s72.ini M2S72-H16N-$c 0 --fingerprint=0000-0000/tplx"; done
}
t0_configs() {
  for s in q0-idle qdu-idle q0-load C-a E-all; do echo "m2s72.ini M2S72-T0-$s 0"; done
}
t0_refs() {
  for c in M2S71-q0-idle M2S71-qdu-idle M2S71-q0-load M2S6-C-a M2S6-E-all; do echo "omnetpp.ini $c 0"; done
}

free_gb() { df -B1G --output=avail "$1" | tail -1 | tr -d ' '; }
# e0one <config> <factor>: one E0 run (non-express, stdout = MAC log, gzip), with the stop conditions; appends to e0-runs.txt
e0one() {
  local cfg=$1 f=$2 fr t0 rc lim
  fr=$(free_gb "$OUT")
  if [ "$fr" -lt "$E0_MIN_FREE_RUN_GB" ]; then echo "STOP before $cfg: free $fr GB < $E0_MIN_FREE_RUN_GB GB" | tee -a "$OUT/e0-runs.txt"; return 3; fi
  lim=$(( ${E0_EST_MIN[$f]} * 3 * 60 ))
  rm -rf "$OUT/runs/$cfg"; mkdir -p "$OUT/runs"
  t0=$(date +%s)
  set +e
  (cd "$HERE" && timeout "$lim" "${OPP[@]}" -f m2s72.ini -c "$cfg" --repeat=10 -r 0 --result-dir="$OUT/runs/$cfg" \
     --cmdenv-express-mode=false --fingerprint=0000-0000/tplx 2>&1 | gzip -n -1 > "$OUT/runs/run-$cfg.log.gz"; exit "${PIPESTATUS[0]}")
  rc=$?
  set -e
  echo "$cfg | factor $f | rc $rc | wall $(( $(date +%s) - t0 )) s (limit $lim s) | raw $(du -sb "$OUT/runs/$cfg" | cut -f1) B + log $(stat -c %s "$OUT/runs/run-$cfg.log.gz") B | free before $fr GB, after $(free_gb "$OUT") GB" | tee -a "$OUT/e0-runs.txt"
  if [ "$rc" -ne 0 ]; then echo "STOP: $cfg rc $rc ($( [ "$rc" = 124 ] && echo 'run time > 3 x estimate' || echo 'simulator error'))" | tee -a "$OUT/e0-runs.txt"; return 4; fi
}
e0run() {
  local fr f o top=0 frac stop
  fr=$(free_gb "$OUT")
  echo "E0 batch start $(date -u +%FT%TZ): free $fr GB (required >= $E0_MIN_FREE_START_GB GB)" | tee "$OUT/e0-runs.txt"
  if [ "$fr" -lt "$E0_MIN_FREE_START_GB" ]; then echo "STOP: free space below the batch-start requirement" | tee -a "$OUT/e0-runs.txt"; return 3; fi
  for f in 1 2 4 8; do
    stop=1
    for o in q0 qdu; do
      e0one "M2S72-E0-$o-f$f" "$f" || return $?
      frac=$(cd "$CHK" && python3 check_m2s72_e0.py quick "$OUT/runs" "M2S72-E0-$o-f$f" | tee -a "$OUT/e0-runs.txt" | sed 's/.*(\([0-9.]*\))$/\1/')
      python3 -c "import sys; sys.exit(0 if float('$frac') > 0.5 else 1)" || stop=0
    done
    top=$f
    if [ "$stop" = 1 ] && [ "$f" != 8 ]; then echo "escalation stop after factor $f: cohort Syncs not received by T_end > 50 % in Q-0 and Q-d (declared rule)" | tee -a "$OUT/e0-runs.txt"; break; fi
  done
  e0one "M2S72-E0NL-q0-f$top" "$top" || return $?
  echo "E0 batch end $(date -u +%FT%TZ)" | tee -a "$OUT/e0-runs.txt"
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
  i2hregen) regen ;;
  i2hrun) i2h_configs | runlist runs ;;
  i2hcheck) python3 "$CHK/check_m2s72_i2h.py" focused "$OUT" > "$OUT/i2h-check.txt" 2>&1 || true
     tail -2 "$OUT/i2h-check.txt" ;;
  i2hhashes) (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  i2h) for s in i2hregen i2hrun i2hcheck i2hhashes; do "$0" "$s" || exit $?; done ;;
  r2regen) regen ;;
  r2run) r2_configs | runlist runs ;;
  r2check) python3 "$CHK/check_m2s72_cp2r2.py" "$OUT" > "$OUT/cp2r2-check.txt" 2>&1 || true
     tail -2 "$OUT/cp2r2-check.txt" ;;
  r2hashes) (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  r2) for s in r2regen r2run r2hashes r2check; do "$0" "$s" || exit $?; done ;;
  e0regen) regen ;;
  e0run) e0run ;;
  e0hashes) (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' -o -name '*.log.gz' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  e0check) python3 "$CHK/check_m2s72_e0.py" "$OUT" > "$OUT/e0-check.txt" 2>&1 || true
          tail -3 "$OUT/e0-check.txt" ;;
  e0) for s in e0regen e0run e0hashes e0check; do "$0" "$s" || exit $?; done ;;
  cfqd) {
          echo "candidate Simu5G build: $SIMU5G_ROOT"
          echo "candidate libsimu5g.so sha256: $(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -d' ' -f1)"
          echo "accepted libsimu5g.so sha256 (unchanged, not used): $(sha256sum /root/stack/simu5g-1.8.0/src/libsimu5g.so | cut -d' ' -f1)"
          echo "source difference vs 1.8.0 (= results/M2-S7.2a-cfqd-candidate-fix.patch):"; cat /tmp/cfqd-actual.patch
        } > "$OUT/build-provenance.txt"
        fr=$(free_gb "$OUT"); echo "cfqd start $(date -u +%FT%TZ): free $fr GB" | tee "$OUT/e0-runs.txt"
        for c in M2S72-E0-q0-f1 M2S72-E0-qdu-f1; do e0one "$c" 1 || exit $?; done
        (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' -o -name '*.log.gz' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
        python3 "$CHK/check_m2s72_cfqd.py" "$OUT" "$E0OUT" > "$OUT/cfqd-check.txt" 2>&1 || true
        tail -3 "$OUT/cfqd-check.txt" ;;
  e2rb) echo "authorisation: $M2S72_E2_AUTH" > "$OUT/authorisation.txt"
        regen > /dev/null
        fr=$(free_gb "$OUT"); echo "E2 step-0 start $(date -u +%FT%TZ): free $fr GB (required >= $E0_MIN_FREE_START_GB GB)" | tee "$OUT/e0-runs.txt"
        [ "$fr" -lt "$E0_MIN_FREE_START_GB" ] && { echo "STOP: free space below the batch-start requirement" | tee -a "$OUT/e0-runs.txt"; exit 3; }
        for f in 1 2; do for o in q0 qdu; do
          e0one "M2S72-E2-$o-one0-n1-f$f" "$f" || exit $?
          # protocol rev. 2.1 safeguard after every run: CONFIRMED-403 or UNEXPLAINED -> STOP for review (raw retained)
          sgrc=0; python3 "$CHK/diag_m2s72_dl_active.py" "$OUT/runs" --classify "M2S72-E2-$o-one0-n1-f$f" > "$OUT/sg403-$o-f$f.txt" 2>&1 || sgrc=$?
          tail -1 "$OUT/sg403-$o-f$f.txt" | tee -a "$OUT/e0-runs.txt"
          [ "$sgrc" = 0 ] || { echo "STOP FOR REVIEW after M2S72-E2-$o-one0-n1-f$f: SG-403 safeguard (rev. 2.1), rc $sgrc" | tee -a "$OUT/e0-runs.txt"; exit 5; }
        done; done
        (cd "$OUT" && find runs -type f \( -name '*.pcapng' -o -name '*.csv' -o -name '*.log.gz' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
        python3 "$CHK/check_m2s72_e2.py" rebaseline "$OUT" "$E0OUT" > "$OUT/e2rb-check.txt" 2>&1 || true
        tail -2 "$OUT/e2rb-check.txt" ;;
  e2rbcheck) python3 "$CHK/check_m2s72_e2.py" rebaseline "$OUT" "$E0OUT" > "$OUT/e2rb-check.txt" 2>&1 || true
        tail -2 "$OUT/e2rb-check.txt" ;;
  e0r2) (cd "$E0OUT" && sha256sum -c --quiet raw-outputs.sha256) > "$OUT/raw-verify.txt" 2>&1 \
          && echo "all $(wc -l < "$E0OUT/raw-outputs.sha256") committed raw-output hashes of $E0OUT verified" >> "$OUT/raw-verify.txt" \
          || { echo "ERROR: E0 raw outputs differ from the committed hashes, see $OUT/raw-verify.txt" >&2; exit 1; }
        tail -1 "$OUT/raw-verify.txt"
        python3 "$CHK/check_m2s72_e0.py" r2 "$E0OUT" "$OUT" > "$OUT/e0r2-check.txt" 2>&1 || true
        tail -4 "$OUT/e0r2-check.txt" ;;
  hashes) (cd "$OUT" && find runs ref -type f \( -name '*.pcapng' -o -name '*.csv' \) | LC_ALL=C sort | xargs sha256sum > raw-outputs.sha256)
          wc -l < "$OUT/raw-outputs.sha256" ;;
  all) for s in regen f0 t0 hashes; do "$0" "$s" || exit $?; done ;;
  *) echo "unknown mode $MODE" >&2; exit 2 ;;
esac
