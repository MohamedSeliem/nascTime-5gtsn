#!/bin/bash
# M2-S7.2a A2-V1: fail-closed wrapper of the SINGLE real-NACK validation run (protocol
# results/M2-S7.2a-a2d2-protocol-r1.md, which supersedes §8 of results/M2-S7.2a-a2d2-design-review.md).
# The experiment (m2s72a2v.ini, the frozen A-2, the evaluator, the acceptance rows) is unchanged; this file only adds
# the execution safety: every gate fails closed, nothing is ever deleted, nothing is ever retried.
#
#   m2s72a2v1.sh gate   all G-0 checks and the build, into a fresh $A2V1_RESULTS_ROOT/a2-nack-gate-<UTC>; NO simulation
#   m2s72a2v1.sh run    the same G-0 checks and build into $A2V1_RESULTS_ROOT/a2-nack-1, then exactly ONE simulation,
#                       lifecycle rows L-1..L-4, read-only evaluation, integrity after
#
# Required (no defaults): OMNETPP_ROOT INET_ROOT SIMU5G_ROOT A2V1_RESULTS_ROOT (the VM's /mnt/nasctime-results)
#                         A2V1_COMMIT (the full 40-hex commit authorised for the run; HEAD must equal it)
# Exit: 0 gate passed (gate) / lifecycle complete and evaluated, integrity intact (run; the scientific verdict is in
#       eval/, a2v1 rc 0 = ACCEPTED); 10 a G-0 gate failed (no simulation); 11 build failed (no simulation);
#       20 lifecycle failure (the single simulation ran but did not complete validly; raw outputs kept read-only, no
#       evaluation); 21 an evaluation tool errored (rc 2); 30 preserved evidence changed during the run; 2 usage.
# Test hooks (tests only; honoured only with A2V1_TEST_HOOKS=1, and then recorded as TEST in every record):
#   A2V1_TEST_SKIP_SUITES=1, A2V1_TEST_SUITE_CMD, A2V1_TEST_BUILD_CMD, A2V1_TEST_FREE_BYTES, A2V1_TEST_WALL_S,
#   A2V1_TEST_POLL_S, A2V1_TEST_SIZE_CMD (replaces the storage measurement command, to test its failure).
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
MODE=${1:-}
FROZEN=fbee2028b9c6ba5a992c0f14f85ef3729e2db107
BASE=M2S72-E0vN-q0-one0-n2-f1
CFG=M2S72-E0vN-q0-one0-n2-f1_A2V1
WALL_S=1800                       # L-2 (the N = 2 smoke: 195 s)
POLL_S=5                          # storage watchdog period
GIB=$((1 << 30))
usage() { echo "usage: m2s72a2v1.sh gate | run   (see the header)" >&2; exit 2; }
case "$MODE" in gate|run) ;; *) usage ;; esac

TEST=""
if [ "${A2V1_TEST_HOOKS:-}" = 1 ]; then
  TEST="TEST HOOKS ACTIVE: skip suites ${A2V1_TEST_SKIP_SUITES:-no}; suite cmd ${A2V1_TEST_SUITE_CMD:-default}; build cmd ${A2V1_TEST_BUILD_CMD:-default}; free ${A2V1_TEST_FREE_BYTES:-measured}; wall ${A2V1_TEST_WALL_S:-$WALL_S}; poll ${A2V1_TEST_POLL_S:-$POLL_S}"
  TEST="$TEST; size cmd ${A2V1_TEST_SIZE_CMD:-default}"
  WALL_S=${A2V1_TEST_WALL_S:-$WALL_S}; POLL_S=${A2V1_TEST_POLL_S:-$POLL_S}
fi

# ---------------------------------------------------------------------------------------- output root (fresh) ----
for v in OMNETPP_ROOT INET_ROOT SIMU5G_ROOT A2V1_RESULTS_ROOT A2V1_COMMIT; do
  [ -n "${!v:-}" ] || { echo "GATE FAIL G0-env: $v is not set (nothing written)" >&2; exit 10; }
done
R=$A2V1_RESULTS_ROOT
[ -d "$R" ] || { echo "GATE FAIL G0-env: results root $R is not a directory (nothing written)" >&2; exit 10; }
if [ "$MODE" = run ]; then OUT=$R/a2-nack-1; else OUT=$R/a2-nack-gate-$(date -u +%Y%m%dT%H%M%SZ); fi
# the single-run rule: an existing root (from any earlier attempt, failed or not) is never reused or written
[ -e "$OUT" ] && { echo "GATE FAIL G0-fresh: $OUT exists (an earlier attempt; never reused, never overwritten; a new attempt needs a new decision)" >&2; exit 10; }
mkdir -p "$OUT/p0" "$OUT/records" "$OUT/runs" "$OUT/eval" || { echo "GATE FAIL G0-fresh: cannot create $OUT" >&2; exit 10; }
REC=$OUT/records; RUNS=$OUT/runs
note() { echo "$(date -u +%FT%TZ) $*" | tee -a "$REC/steps.txt"; }
verdict() { echo "$*" > "$REC/wrapper-verdict.txt"; note "WRAPPER VERDICT: $*"; }
gate_fail() { echo "$1: $2" >> "$REC/gate.txt"; note "GATE FAIL $1: $2"; verdict "GATE FAILED ($1); no simulation; every output kept in $OUT"; exit 10; }
gate_ok() { echo "$1: PASS $2" >> "$REC/gate.txt"; note "G-0 $1 PASS: $2"; }
GATE=(python3 -B "$HERE/check/m2s72a2v1_gate.py")
LIB=(python3 -B "$HERE/check/m2s72s5_lib.py")
note "mode $MODE, output root $OUT, wrapper $(sha256sum "$0" | cut -c1-64)"
[ -n "$TEST" ] && note "$TEST"

# ------------------------------------------------------------------------------------------------- G-0 ---------
# G0-env: the stack named by the environment exists and is the declared one
for f in "$OMNETPP_ROOT/setenv" "$INET_ROOT/Version" "$SIMU5G_ROOT/Version" "$SIMU5G_ROOT/src/libsimu5g.so"; do
  [ -f "$f" ] || gate_fail G0-env "$f missing"
done
[ "$(cat "$SIMU5G_ROOT/Version")" = 1.8.1 ] || gate_fail G0-env "$SIMU5G_ROOT/Version is not 1.8.1"
gate_ok G0-env "stack files present, Simu5G 1.8.1"

# G0-commit: exactly the authorised commit, clean, descending from the frozen A-2
[[ "$A2V1_COMMIT" =~ ^[0-9a-f]{40}$ ]] || gate_fail G0-commit "A2V1_COMMIT is not a full 40-hex commit id: $A2V1_COMMIT"
head=$(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null) || gate_fail G0-commit "not a git worktree: $NASCTIME"
[ "$head" = "$A2V1_COMMIT" ] || gate_fail G0-commit "HEAD $head != authorised $A2V1_COMMIT"
dirty=$(git -C "$NASCTIME" status --porcelain -- simulations src 2>&1) || gate_fail G0-commit "git status failed"
[ -z "$dirty" ] || gate_fail G0-commit "worktree not clean: $(echo "$dirty" | head -3 | tr '\n' ';')"
git -C "$NASCTIME" merge-base --is-ancestor "$FROZEN" HEAD 2>/dev/null || gate_fail G0-commit "HEAD does not descend from $FROZEN"
gate_ok G0-commit "HEAD = $head, clean, descends from the frozen A-2"

# G0-frozen: A-2, its references, the accepted configurations and lifecycle library are those of fbee202; the A2-V1
# configuration is the reviewed one (pinned hashes)
git -C "$NASCTIME" diff --quiet "$FROZEN" HEAD -- simulations/m2/check/m2s72_a2.py simulations/m2/check/check_m2s72_a2.py \
  simulations/m2/check/m2s72_harqx.py simulations/m2/check/m2s72_a2probe.py simulations/m2/check/m2s72_peru.py \
  simulations/m2/check/m2s72s5_lib.py simulations/m2/m2s72s5.ini simulations/m2/m2s72.ini simulations/m2/m2s72s5.sh \
  || gate_fail G0-frozen "A-2 / accepted files differ from $FROZEN"
out=$("${GATE[@]}" pins "$HERE") || gate_fail G0-frozen "$out"
gate_ok G0-frozen "A-2 and accepted files = $FROZEN; $out"

# G0-evidence: preserved evidence intact; snapshot of the prior A-2 outputs (compared again after the run)
for e in s5-smoke-1-evidence.sha256 s5-n2-1-evidence.sha256 a2-p0-evidence.sha256 a2-v3-evidence.sha256; do
  [ -s "$R/$e" ] || gate_fail G0-evidence "$R/$e missing or empty"
  (cd "$R" && sha256sum -c "$e" --quiet) > "$REC/evidence-$e.txt" 2>&1 || gate_fail G0-evidence "$e does not verify (see $REC/evidence-$e.txt)"
done
for d in a2-v1 a2-v3 a2-env-check; do [ -d "$R/$d" ] || gate_fail G0-evidence "$R/$d missing"; done
(cd "$R" && find a2-v1 a2-v3 a2-env-check -type f | LC_ALL=C sort | xargs -r sha256sum) > "$REC/prior-before.sha256" \
  || gate_fail G0-evidence "snapshot of a2-v1 / a2-v3 / a2-env-check failed"
[ -s "$REC/prior-before.sha256" ] || gate_fail G0-evidence "a2-v1 / a2-v3 / a2-env-check hold no file"
gate_ok G0-evidence "4 evidence files verify; prior A-2 outputs snapshot $(wc -l < "$REC/prior-before.sha256") files"

# G0-stack: the same Simu5G binary and versions as the baseline N = 2 smoke; A-2's Simu5G texts present (A2-0s)
N2REC=$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records
N2=$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2/runs
out=$("${GATE[@]}" stack "$N2REC/env-smoke-n2.txt" "$SIMU5G_ROOT/src/libsimu5g.so" "$INET_ROOT/Version" "$SIMU5G_ROOT/Version") \
  || gate_fail G0-stack "$out"
gate_ok G0-stack "$out"
out=$("${GATE[@]}" source "$SIMU5G_ROOT") || gate_fail G0-source "$out"
gate_ok G0-source "$out"

# G0-suites: the evaluator and A-2 test suites pass in this tree
if [ "${A2V1_TEST_HOOKS:-}" = 1 ] && [ -n "${A2V1_TEST_SKIP_SUITES:-}" ]; then
  note "G-0 G0-suites SKIPPED (test hook)"
else
  suites=("python3 -B check/test_m2s72_a2v1.py" "python3 -B check/test_m2s72_a2.py")
  [ "${A2V1_TEST_HOOKS:-}" = 1 ] && [ -n "${A2V1_TEST_SUITE_CMD:-}" ] && suites=("$A2V1_TEST_SUITE_CMD")
  for s in "${suites[@]}"; do
    (cd "$HERE" && bash -c "$s") > "$REC/suite-$(echo "$s" | tr -c 'A-Za-z0-9_' '_').txt" 2>&1 || gate_fail G0-suites "'$s' failed"
  done
  gate_ok G0-suites "${#suites[@]} suites pass"
fi

# G0-config: the effective configuration differs from the baseline by EXACTLY the declared lines
source "$OMNETPP_ROOT/setenv" -f >/dev/null 2>&1 || gate_fail G0-config "cannot source $OMNETPP_ROOT/setenv"
(cd "$HERE" && opp_run -u Cmdenv -f m2s72s5.ini -c "$BASE" -r 0 -q runconfig) > "$OUT/p0/rc-base.txt" 2>&1 \
  || gate_fail G0-config "runconfig of $BASE failed (see p0/rc-base.txt)"
(cd "$HERE" && opp_run -u Cmdenv -f m2s72a2v.ini -c "$CFG" -r 0 -q runconfig) > "$OUT/p0/rc-a2v1.txt" 2>&1 \
  || gate_fail G0-config "runconfig of $CFG failed (see p0/rc-a2v1.txt)"
out=$("${GATE[@]}" config-diff "$OUT/p0/rc-base.txt" "$OUT/p0/rc-a2v1.txt") || gate_fail G0-config "$out"
gate_ok G0-config "$out"

# G0-baseline: baseline raw size (manifest = disk) -> storage limit; P0 facts; NC-V-baseline
out=$("${GATE[@]}" baseline-size "$N2REC/$BASE.manifest.sha256" "$N2/$BASE" "$N2/run-$BASE.log.gz") \
  || gate_fail G0-baseline "$out"
BASE_B=$(echo "$out" | tail -1); LIMIT_B=$((2 * BASE_B))
gate_ok G0-baseline "$(echo "$out" | head -1); storage limit L-3 = 2 x = $LIMIT_B B"
[ -s "$R/a2-v3/a2-$BASE.json" ] || gate_fail G0-baseline "$R/a2-v3/a2-$BASE.json missing (N1 for the predictions)"
python3 -B - "$R/a2-v3/a2-$BASE.json" > "$OUT/p0/p0.txt" 2>&1 <<'EOF' || gate_fail G0-baseline "P0 read of the accepted N = 2 A-2 output failed"
import json, sys
j = json.load(open(sys.argv[1]))
print("baseline per UE (node: inserts, feedback, NACK):", {n: (o["inserts"], o["feedback"], o["nack"]) for n, o in j["per_ue"].items()})
EOF
grep -E "nrMac macNodeId|averageCqiDl:mean|rcvdSinrDl:mean" "$N2/$BASE/$BASE/0.sca" >> "$OUT/p0/p0.txt" 2>&1
echo "baseline raw bytes $BASE_B; storage limit $LIMIT_B" >> "$OUT/p0/p0.txt"
python3 -B "$HERE/check/check_m2s72_a2v1.py" v1 "$N2" "$BASE" "$OUT/p0/nc-v-baseline" > "$OUT/p0/nc-v-baseline.console.txt" 2>&1
ncrc=$?
out=$("${GATE[@]}" nc-baseline "$ncrc" "$OUT/p0/nc-v-baseline/a2v1-$BASE.txt") || gate_fail G0-ncbase "$out"
gate_ok G0-ncbase "$out"

# G0-space: free space for the capped run plus margin
if [ "${A2V1_TEST_HOOKS:-}" = 1 ] && [ -n "${A2V1_TEST_FREE_BYTES:-}" ]; then free=$A2V1_TEST_FREE_BYTES
else free=$(( $(df -B1 --output=avail "$R" | tail -1) )); fi
need=$((LIMIT_B + 4 * GIB)); [ "$need" -lt $((10 * GIB)) ] && need=$((10 * GIB))
[ "$free" -ge "$need" ] || gate_fail G0-space "free $free B < required $need B (max(10 GiB, storage limit + 4 GiB))"
gate_ok G0-space "free $free B >= $need B"

# build (hard stop)
if [ "${A2V1_TEST_HOOKS:-}" = 1 ] && [ -n "${A2V1_TEST_BUILD_CMD:-}" ]; then bcmd=$A2V1_TEST_BUILD_CMD
else bcmd="$NASCTIME/src/nasctime/m2/build.sh"; fi
if ! bash -c "$bcmd" > "$REC/build.log" 2>&1; then
  note "BUILD FAILED (see $REC/build.log)"; verdict "BUILD FAILED; no simulation; every output kept in $OUT"; exit 11
fi
[ -f "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" ] || { note "BUILD FAILED: libnasctime_m2.so absent"; verdict "BUILD FAILED; no simulation"; exit 11; }
note "build OK: libnasctime_m2.so $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -c1-64) (recorded, not compared: builds need not be bit-identical)"

if [ "$MODE" = gate ]; then verdict "GATE PASSED; no simulation (gate mode)"; exit 0; fi

# --------------------------------------------------------------------------------------- the single run ---------
{ echo "date_utc: $(date -u +%FT%TZ)"; echo "config: $CFG (seed 0, repetition 0)"; [ -n "$TEST" ] && echo "$TEST"
  echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i version)"; echo "inet_version_file: $(cat "$INET_ROOT/Version")"
  echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version")"; echo "libsimu5g_sha256: $(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" | cut -c1-64)"
  echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" | cut -c1-64)"
  echo "nascTime_commit: $head"; for f in m2s72a2v.ini m2s72s5.ini m2s72.ini; do echo "${f}_sha256: $(sha256sum "$HERE/$f" | cut -c1-64)"; done
  echo "wall_limit_s: $WALL_S"; echo "storage_limit_bytes: $LIMIT_B (2 x baseline $BASE_B)"; echo "fingerprint: not requested"
  echo "python: $(python3 --version 2>&1)   os: $(uname -srm)"; } > "$REC/env.txt"
LOG=$RUNS/run-$CFG.log.gz
FIFO=$(mktemp -u "${TMPDIR:-/tmp}/a2v1-fifo.XXXXXX"); mkfifo "$FIFO" || { verdict "LIFECYCLE FAILURE: cannot create the log pipe; no simulation started"; exit 20; }
gzip -n -1 < "$FIFO" > "$LOG" & gzpid=$!
note "simulation start (the only one): wall limit $WALL_S s, storage limit $LIMIT_B B"
t0=$(date +%s)
( cd "$HERE" && exec timeout "$WALL_S" opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
    -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes -u Cmdenv \
    -f m2s72a2v.ini -c "$CFG" --repeat=1 -r 0 --result-dir="$RUNS/$CFG" --cmdenv-express-mode=false ) > "$FIFO" 2>&1 &
simpid=$!
# storage measurement, fail-closed: a failed or non-numeric measurement is never read as a size
measure() {
  local v
  if [ "${A2V1_TEST_HOOKS:-}" = 1 ] && [ -n "${A2V1_TEST_SIZE_CMD:-}" ]; then v=$(bash -c "$A2V1_TEST_SIZE_CMD" 2>>"$REC/storage-monitor.txt")
  else v=$("${GATE[@]}" size "$RUNS" 2>>"$REC/storage-monitor.txt"); fi || { echo "measurement failed (rc $?, output '${v:0:80}')"; return 1; }
  [[ "$v" =~ ^[0-9]+$ ]] || { echo "measurement not numeric: '${v:0:80}'"; return 1; }
  echo "$v"
}
breach=""; monerr=""
while kill -0 "$simpid" 2>/dev/null; do
  if ! sz=$(measure); then
    monerr="$sz at $(( $(date +%s) - t0 )) s"
    echo "$monerr" >> "$REC/storage-monitor.txt"; note "STORAGE-MONITOR-ERROR: $monerr; terminating the simulation (no retry)"
    kill -TERM "$simpid" 2>/dev/null; break
  fi
  if [ "$sz" -gt "$LIMIT_B" ]; then
    breach="raw $sz B > limit $LIMIT_B B at $(( $(date +%s) - t0 )) s"
    echo "$breach" > "$REC/storage-limit.txt"; note "STORAGE LIMIT: $breach; terminating the simulation (no retry)"
    kill -TERM "$simpid" 2>/dev/null; break
  fi
  sleep "$POLL_S"
done
wait "$simpid"; rc=$?
wait "$gzpid"; rm -f "$FIFO"
wall=$(( $(date +%s) - t0 ))
if ! raw=$(measure); then
  monerr="${monerr:+$monerr; }after the run: $raw"; echo "after the run: $raw" >> "$REC/storage-monitor.txt"; raw=unmeasured
fi
cls=$("${LIB[@]}" classify "$rc" "$LOG" 2>&1); outcome=${cls%%$'\t'*}
[ -n "$breach" ] && outcome=STORAGE-LIMIT
[ -n "$monerr" ] && outcome=STORAGE-MONITOR-ERROR
note "simulation end: rc $rc, wall $wall s, raw $raw B, outcome $outcome ($cls)"

# L-4 first (always, on any outcome): manifest, verification, read-only
"${LIB[@]}" manifest "$REC/$CFG.manifest.sha256" "$RUNS/$CFG" "$LOG" > "$REC/manifest.console.txt" 2>&1; mrc=$?
"${LIB[@]}" verify-manifest "$REC/$CFG.manifest.sha256" >> "$REC/manifest.console.txt" 2>&1; vrc=$?
chmod -R a-w "$RUNS"; crc=$?
L1=$([ "$outcome" = OK ] && [ "$rc" = 0 ] && echo PASS || echo FAIL)
L2=$([ "$wall" -le "$WALL_S" ] && [ "$rc" != 124 ] && echo PASS || echo FAIL)
L3=$([ -z "$breach" ] && [ -z "$monerr" ] && [[ "$raw" =~ ^[0-9]+$ ]] && [ "$raw" -le "$LIMIT_B" ] && echo PASS || echo FAIL)
L4=$([ "$mrc" = 0 ] && [ "$vrc" = 0 ] && [ "$crc" = 0 ] && echo PASS || echo FAIL)
printf "L-1 outcome OK (rc 0, classifier OK): %s (rc %s, %s)\nL-2 wall <= %s s: %s (%s s)\nL-3 raw <= %s B: %s (%s B%s)\nL-4 manifest written, verified, raw read-only: %s (manifest rc %s, verify rc %s, chmod rc %s)\n" \
  "$L1" "$rc" "$cls" "$WALL_S" "$L2" "$wall" "$LIMIT_B" "$L3" "$raw" "${breach:+; $breach}${monerr:+; STORAGE-MONITOR-ERROR: $monerr}" "$L4" "$mrc" "$vrc" "$crc" | tee "$REC/lifecycle.txt"

integrity_after() {
  local ok=0
  (cd "$R" && for e in s5-smoke-1-evidence.sha256 s5-n2-1-evidence.sha256 a2-p0-evidence.sha256 a2-v3-evidence.sha256; do
     sha256sum -c "$e" --quiet || exit 1; done) > "$REC/evidence-after.txt" 2>&1 || ok=1
  (cd "$R" && find a2-v1 a2-v3 a2-env-check -type f | LC_ALL=C sort | xargs -r sha256sum) > "$REC/prior-after.sha256" 2>&1
  cmp -s "$REC/prior-before.sha256" "$REC/prior-after.sha256" || ok=1
  return $ok
}
seal() {   # the last write of every post-simulation path: hashes of the records (raw outputs: the manifest)
  (cd "$R" && find "$(basename "$OUT")/p0" "$(basename "$OUT")/records" "$(basename "$OUT")/eval" -type f \
     | LC_ALL=C sort | xargs -r sha256sum) > "$R/$(basename "$OUT")-evidence.sha256"
}

if [ "$L1$L2$L3$L4" != PASSPASSPASSPASS ]; then
  integrity_after || note "INTEGRITY AFTER: preserved evidence changed"
  verdict "LIFECYCLE FAILURE (L-1 $L1, L-2 $L2, L-3 $L3, L-4 $L4); no evaluation, no retry; raw outputs kept read-only in $RUNS"
  seal; exit 20
fi

# ------------------------------------------------------------------------------ evaluation (read-only) ---------
cd "$HERE" || { verdict "LIFECYCLE FAILURE: cannot enter $HERE"; seal; exit 20; }
python3 -B check/check_m2s72_a2.py a2 "$RUNS" "$CFG" "$OUT/eval" > "$OUT/eval/a2.console.txt" 2>&1; arc=$?
python3 -B check/check_m2s72_a2.py a2-controls "$RUNS" "$CFG" "$OUT/eval" > "$OUT/eval/a2-controls.console.txt" 2>&1; crc2=$?
python3 -B check/check_m2s72_a2v1.py v1 "$RUNS" "$CFG" "$OUT/eval" --a2-json "$OUT/eval/a2-$CFG.json" > "$OUT/eval/a2v1.console.txt" 2>&1; vrc2=$?
note "evaluation: a2 rc $arc, a2-controls rc $crc2, a2v1 rc $vrc2 ($(tail -1 "$OUT/eval/a2v1.console.txt" 2>/dev/null))"
if ! integrity_after; then verdict "PRESERVED EVIDENCE CHANGED during the run (see $REC/evidence-after.txt, prior-after.sha256)"; seal; exit 30; fi
if [ "$arc" = 2 ] || [ "$crc2" = 2 ] || [ "$vrc2" = 2 ]; then
  verdict "LIFECYCLE COMPLETE; EVALUATION ERROR (a2 $arc, a2-controls $crc2, a2v1 $vrc2): no scientific verdict"; seal; exit 21
fi
verdict "LIFECYCLE COMPLETE (L-1..L-4 PASS); scientific verdict: a2 rc $arc, a2-controls rc $crc2, a2v1 rc $vrc2 ($(tail -1 "$OUT/eval/a2v1.console.txt"))"
seal; exit 0
