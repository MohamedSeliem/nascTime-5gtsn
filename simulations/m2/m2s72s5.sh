#!/bin/bash
# M2-S7.2a Stage 5 on Simu5G 1.8.1, increment S5-1: isolated runner with a per-run evidence lifecycle
# (plan rev. 1 on plan/m2-s7.2a-stage5: §4, RD-5, RD-7; protocol results/M2-S7.2a-e0v-protocol.md).
# m2s72.sh and every accepted runner, checker and record are unchanged; this runner writes nothing under
# simulations/m2/results and never runs in legacy mode.
#
#   m2s72s5.sh regen              no simulation: accepted generator check, m2s72s5.ini check / verify / RD-4 diff,
#                                 effective-entry check of the accepted sources (G0-R1), S5-1 tests
#                                 -> $RESULTS/M2-S7.2a-s5regen/regen.txt
#   m2s72s5.sh smoke              the single E0v-q0-f1 smoke run (protocol §9): run, per-run check, E0 quick proxy,
#                                 controls-q8, manifest; raw outputs held uncompressed and read-only (never deleted,
#                                 never released); not an E0v result
#   m2s72s5.sh e0v                E0v core [A -> 1.8.1]: E0's ascending factors and escalation stop, the MAC-log twin
#   m2s72s5.sh e0vp               E0v-p: Q-0p and Q-de (D-1) at DL factor 1, 2
#   m2s72s5.sh e0vh5              E0v-H5: 5 H-ARQ processes at DL factor 1, 2 and the H5 twin
#   m2s72s5.sh release <stage>    commit the records of pending runs of <stage> and delete their raw outputs
#
# Required (no defaults: machine paths are never assumed):
#   NASCTIME_RESULTS_ROOT  absolute isolated root (nt_results.sh); legacy mode is refused
#   OMNETPP_ROOT INET_ROOT SIMU5G_ROOT; $SIMU5G_ROOT/Version must read 1.8.1
#   simulation modes: S5_ENV_DECISION="<reference of the decision that confirmed the Stage 5 environment>" (RD-7)
# Optional:
#   S5_RECORDS_REPO   a clean git worktree of this repository: after each run's records are written, they are copied to
#                     simulations/results/simu5g-1.8.1/s5/<batch>/ there, committed, verified in HEAD, and only then the
#                     run's raw outputs are deleted (tier C). Without it, raw outputs stay (pending) and the batch stops
#                     when the per-run free-space rule fails.
# Per run (one simulation at a time): free-space rule -> simulation (non-express; stdout = MAC logs, gzip -n) ->
#   outcome OK / SIM-ABORT / TIMEOUT / ERROR -> per-run check (check_m2s72_s5v.py) -> manifest (sha256 of every raw
#   file) -> durable records + ledger -> tier: B (kept, gzip -n, verified) for a non-OK outcome, a failed check or a
#   declared retention reason; C (deleted only after the records are committed) otherwise.
# Test hooks (tests only; recorded as TEST in env and ledger): S5_TEST_SKIP_BUILD=1, S5_TEST_CHECKER=<script>.
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
MODE=${1:-}
die() { echo "ERROR: $*" >&2; exit 1; }
[ -n "$MODE" ] || die "usage: m2s72s5.sh regen | smoke | e0v | e0vp | e0vh5 | release <stage>"
for v in OMNETPP_ROOT INET_ROOT SIMU5G_ROOT NASCTIME_RESULTS_ROOT; do
  [ -n "${!v:-}" ] || die "$v must be set explicitly (Stage 5 never assumes machine paths)"
done
[ "$(cat "$SIMU5G_ROOT/Version" 2>/dev/null)" = 1.8.1 ] || die "$SIMU5G_ROOT/Version is not 1.8.1"
export OMNETPP_ROOT INET_ROOT SIMU5G_ROOT
source "$NASCTIME/simulations/nt_results.sh"
nt_results_init m2 nobaseline
[ -n "$NT_ISOLATED" ] || die "isolated mode required"
CHK=$HERE/check
LIB=(python3 "$CHK/m2s72s5_lib.py")
CHECKER=${S5_TEST_CHECKER:-$CHK/check_m2s72_s5v.py}
TEST=""; [ -n "${S5_TEST_SKIP_BUILD:-}${S5_TEST_CHECKER:-}" ] && TEST="TEST HOOKS ACTIVE (skip build: ${S5_TEST_SKIP_BUILD:-no}; checker: $CHECKER)"
GB=$((1 << 30))
declare -A EST_MIN=([1]=4 [2]=6 [4]=10 [8]=18)                  # E0 [A] run-time estimate (min); limit 3 x
declare -A EST_B=([1]=$((9 * GB / 10)) [2]=$((6 * GB / 5)) [4]=$((17 * GB / 10)) [8]=$((27 * GB / 10)))   # E0 sizes x 1.2 + logs

case "$MODE" in
  regen) STAGE=M2-S7.2a-s5regen ;;
  smoke) STAGE=M2-S7.2a-s5smoke ;;
  e0v) STAGE=M2-S7.2a-e0v ;;
  e0vp) STAGE=M2-S7.2a-e0vp ;;
  e0vh5) STAGE=M2-S7.2a-e0vh5 ;;
  release) STAGE=${2:-}; [ -n "$STAGE" ] || die "release <stage>" ;;
  *) die "unknown mode $MODE" ;;
esac
OUT=$RESULTS/$STAGE
REC=$OUT/records
BATCH="$(basename "$(dirname "$RESULTS")")-$STAGE"

if [ "$MODE" != release ]; then
  case "$MODE" in
    regen) ;;
    *) [ -n "${S5_ENV_DECISION:-}" ] || die "S5_ENV_DECISION is not set: the Stage 5 environment is not confirmed (RD-7); no simulation runs" ;;
  esac
  nt_fresh_out "$OUT"
  mkdir -p "$REC" "$OUT/runs"
  if [ -z "${S5_TEST_SKIP_BUILD:-}" ]; then
    "$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/build.log" 2>&1 || die "build failed, see $OUT/build.log"
  fi
  source "$OMNETPP_ROOT/setenv" -f >/dev/null
  {
    echo "date_utc: $(date -u +%FT%TZ)"
    echo "mode: $MODE   stage: $STAGE   batch: $BATCH"
    echo "S5_ENV_DECISION: ${S5_ENV_DECISION:-n/a}"
    [ -n "$TEST" ] && echo "$TEST"
    echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
    echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
    echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version")"
    echo "libsimu5g_sha256: $(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" 2>/dev/null | cut -d' ' -f1)"
    echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m2 src/nasctime ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted changes)')"
    echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" 2>/dev/null | cut -d' ' -f1)"
    echo "m2s72_ini_sha256: $(sha256sum "$HERE/m2s72.ini" | cut -d' ' -f1)"
    echo "m2s72s5_ini_sha256: $(sha256sum "$HERE/m2s72s5.ini" | cut -d' ' -f1)"
    echo "python: $(python3 --version 2>&1)   os: $(uname -srm)"
  } > "$REC/env-$MODE.txt"
  nt_stack_record "$REC"
  printf "config\tseed\toutcome\trc\twall_s\traw_bytes\tcheck\tmanifest_sha256\ttier\tdetail\n" > "$REC/runs.tsv"
fi
OPP=(opp_run -l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"
     -n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes -u Cmdenv)
note() { echo "$(date -u +%FT%TZ) $*" | tee -a "$REC/steps.txt"; }
ledger() { printf "%s\t%s\n" "$(date -u +%FT%TZ)" "$*" >> "$REC/ledger.tsv"; "${LIB[@]}" durable "$REC/ledger.tsv"; }

# ------------------------------------------------------------------------------------------------ lifecycle -----
# s5_run <cfg> <factor> <twin bytes> [<limit s>] : one simulation, classified; returns 0 OK, 3 space STOP, 5 non-OK
s5_run() {
  local cfg=$1 f=$2 twinb=$3 t0 rc lim out det raw
  "${LIB[@]}" space "$OUT" "${EST_B[$f]}" "$twinb" | tee -a "$REC/steps.txt"
  [ "${PIPESTATUS[0]}" = 0 ] || { note "STOP before $cfg: free-space rule"; return 3; }
  lim=${4:-$(( ${EST_MIN[$f]} * 3 * 60 ))}
  t0=$(date +%s)
  (cd "$HERE" && timeout "$lim" "${OPP[@]}" -f m2s72s5.ini -c "$cfg" --repeat=1 -r 0 --result-dir="$OUT/runs/$cfg" \
     --cmdenv-express-mode=false --fingerprint=0000-0000/tplx 2>&1 | gzip -n -1 > "$OUT/runs/run-$cfg.log.gz"; exit "${PIPESTATUS[0]}")
  rc=$?
  out=$("${LIB[@]}" classify "$rc" "$OUT/runs/run-$cfg.log.gz")
  det=${out#*$'\t'}; out=${out%%$'\t'*}
  raw=$(du -sb "$OUT/runs/$cfg" 2>/dev/null | cut -f1)
  S5_LAST="$cfg	0	$out	$rc	$(( $(date +%s) - t0 ))	${raw:-0}"
  note "$cfg: outcome $out (rc $rc, wall $(( $(date +%s) - t0 )) s, limit $lim s, raw ${raw:-0} B): $det"
  if [ "$out" != OK ]; then
    s5_manifest "$cfg" && s5_tier "$cfg" "B" "outcome $out"
    printf "%s\t-\t%s\tB\t%s\n" "$S5_LAST" "$S5_MAN" "$det" >> "$REC/runs.tsv"
    note "STOP: $cfg outcome $out (not a result; raw outputs kept, tier B)"; return 5
  fi
  return 0
}
s5_manifest() {   # sets S5_MAN
  local cfg=$1 m
  m=$("${LIB[@]}" manifest "$REC/$cfg.manifest.sha256" "$OUT/runs/$cfg" "$OUT/runs/run-$cfg.log.gz") || { note "manifest of $cfg FAILED"; return 1; }
  S5_MAN=$(sha256sum "$REC/$cfg.manifest.sha256" | cut -d' ' -f1)
  note "$m"
}
s5_check() {      # per-run check; returns its rc (0 PASS, 1 FAIL, 2 error)
  local cfg=$1 rc
  python3 "$CHECKER" run "$OUT/runs" "$cfg" "$REC" > "$REC/$cfg.console.txt" 2>&1; rc=$?
  note "$cfg: per-run check rc $rc: $(tail -1 "$REC/$cfg.console.txt")"
  return $rc
}
s5_tier() {       # <cfg> <B|C> <reason>
  local cfg=$1 t=$2 why=$3
  if [ "$t" = B ]; then
    "${LIB[@]}" retain "$REC/$cfg.manifest.sha256" | tee -a "$REC/steps.txt"
    ledger "$cfg	tier B (kept, gzip -n, verified against the manifest): $why"
  else
    echo "$cfg" >> "$REC/pending-release.txt"; "${LIB[@]}" durable "$REC/pending-release.txt"
    ledger "$cfg	tier C pending release (records first committed, then raw deleted)"
  fi
}
# s5_full <cfg> <factor> <twin bytes> <hold reason or ''> : run, check, manifest, tier; returns 0 / 3 / 5 / 6 (check)
s5_full() {
  local cfg=$1 f=$2 twinb=$3 hold=$4 crc
  s5_run "$cfg" "$f" "$twinb" || return $?
  s5_check "$cfg"; crc=$?
  s5_manifest "$cfg" || return 5
  for x in "$REC/$cfg.check.txt" "$REC/$cfg.digest.json"; do [ -f "$x" ] && "${LIB[@]}" durable "$x"; done
  if [ "$crc" != 0 ]; then
    s5_tier "$cfg" B "per-run check rc $crc"
    printf "%s\trc %s\t%s\tB\tper-run check failed\n" "$S5_LAST" "$crc" "$S5_MAN" >> "$REC/runs.tsv"
    note "STOP: $cfg per-run check rc $crc (raw kept, tier B)"; return 6
  fi
  if [ -n "$hold" ]; then
    ledger "$cfg	held (raw kept until: $hold)"
    printf "%s\tPASS\t%s\theld\t%s\n" "$S5_LAST" "$S5_MAN" "$hold" >> "$REC/runs.tsv"
  else
    s5_tier "$cfg" C ""
    printf "%s\tPASS\t%s\tC\t-\n" "$S5_LAST" "$S5_MAN" >> "$REC/runs.tsv"
  fi
  return 0
}
# s5_release : commit the records of every pending run, verify them in HEAD, then delete those runs' raw outputs
s5_release() {
  [ -s "$REC/pending-release.txt" ] || return 0
  if [ -z "${S5_RECORDS_REPO:-}" ]; then note "release: S5_RECORDS_REPO not set; pending raw outputs kept"; return 0; fi
  local repo=$S5_RECORDS_REPO dest rel cfg files=() rp=() lf=() f
  git -C "$repo" diff --cached --quiet || { note "release refused: $repo has staged changes"; return 1; }
  rel=simulations/results/simu5g-1.8.1/s5/$BATCH
  dest=$repo/$rel; mkdir -p "$dest"
  for f in "$REC"/*; do [ -f "$f" ] || continue; case "$f" in *.console.txt|*.check.txt|*.digest.json|*.manifest.sha256|*.txt|*.tsv) ;; *) continue ;; esac
    cp "$f" "$dest/"; rp+=("$rel/$(basename "$f")"); lf+=("$f"); done
  git -C "$repo" add -f -- "${rp[@]}" || { note "release: git add failed"; return 1; }
  git -C "$repo" diff --cached --quiet || git -C "$repo" commit -q -m "S5 records: $BATCH ($(wc -l < "$REC/pending-release.txt") run(s) released)" -- "${rp[@]}" \
    || { note "release: git commit failed"; return 1; }
  "${LIB[@]}" committed "$repo" "${rp[@]}" -- "${lf[@]}" | tee -a "$REC/steps.txt"
  [ "${PIPESTATUS[0]}" = 0 ] || { note "release: records not verified in HEAD; raw outputs kept"; return 1; }
  while read -r cfg; do
    [ -n "$cfg" ] || continue
    "${LIB[@]}" verify-manifest "$REC/$cfg.manifest.sha256" > /dev/null || { note "release: $cfg raw outputs differ from their manifest; kept"; return 1; }
    rm -rf "${OUT:?}/runs/$cfg" "$OUT/runs/run-$cfg.log.gz"
    ledger "$cfg	raw deleted after its manifest and records were committed ($(git -C "$repo" rev-parse --short HEAD))"
  done < "$REC/pending-release.txt"
  : > "$REC/pending-release.txt"
  # the deletion entries of the ledger (records only; no raw output depends on this second commit)
  for f in ledger.tsv steps.txt pending-release.txt; do cp "$REC/$f" "$dest/"; done
  git -C "$repo" add -f -- "$rel/ledger.tsv" "$rel/steps.txt" "$rel/pending-release.txt"
  git -C "$repo" diff --cached --quiet || git -C "$repo" commit -q -m "S5 records: $BATCH ledger after release" -- "$rel/ledger.tsv" "$rel/steps.txt" "$rel/pending-release.txt"
}
held_release() {  # move a held run to tier C
  s5_tier "$1" C "hold ended: $2"
}

# ---------------------------------------------------------------------------------------------------- modes -----
case "$MODE" in
  regen)
    {
      echo "M2-S7.2a S5-1 regeneration and configuration record (no simulation)"
      echo; echo "== accepted generator: python3 tools/m2s72_gen.py check (m2s72.ini byte for byte)"
      (cd "$HERE" && python3 tools/m2s72_gen.py check | tail -1); echo "rc ${PIPESTATUS[0]}"
      echo; echo "== python3 tools/m2s72s5_gen.py check"; (cd "$HERE" && python3 tools/m2s72s5_gen.py check | tail -1)
      echo; echo "== python3 tools/m2s72s5_gen.py verify (OMNeT++ runconfig)"; (cd "$HERE" && python3 tools/m2s72s5_gen.py verify "${OPP[@]}")
      echo "verify rc $?"
      echo; echo "== python3 tools/m2s72s5_gen.py diff (RD-4)"; (cd "$HERE" && python3 tools/m2s72s5_gen.py diff "${OPP[@]}")
      echo "diff rc $?"
      echo; echo "== python3 tools/m2s72_verify_eff.py check / control (G0-R1: effective entries of the accepted m2s72.ini sources)"
      (cd "$HERE" && python3 tools/m2s72_verify_eff.py check "${OPP[@]}" -f omnetpp.ini); echo "verify-eff rc $?"
      (cd "$HERE" && python3 tools/m2s72_verify_eff.py control "${OPP[@]}" -f omnetpp.ini); echo "verify-eff controls rc $?"
      echo; echo "== S5-1 tests"; python3 "$CHK/test_m2s72s5.py"; echo "tests rc $?"
    } > "$REC/regen.txt" 2>&1
    tail -20 "$REC/regen.txt" ;;
  e0v)
    note "E0v batch start (S5_ENV_DECISION ${S5_ENV_DECISION})"
    top=0; held=""
    for f in 1 2 4 8; do
      stop=1
      for o in q0 qdu; do
        cfg=M2S72-E0v-$o-f$f
        hold=""; [ "$o" = q0 ] && hold="twin of the highest Q-0 factor"
        [ "$cfg" = M2S72-E0v-q0-f1 ] && hold="controls-q8; twin of the highest Q-0 factor"
        [ "$cfg" = M2S72-E0v-qdu-f2 ] && hold="controls-sg"
        s5_full "$cfg" "$f" "${EST_B[$f]}" "$hold" || exit $?
        frac=$(python3 "$CHECKER" quick "$OUT/runs" "$cfg" | tee -a "$REC/steps.txt" | sed -n 's/.*(\([0-9.]*\))$/\1/p')
        [ -n "$frac" ] || { note "STOP: escalation proxy (E0 quick) gave no value for $cfg"; exit 6; }
        python3 -c "import sys; sys.exit(0 if float('$frac') > 0.5 else 1)" || stop=0
        if [ "$cfg" = M2S72-E0v-q0-f1 ]; then
          python3 "$CHECKER" controls-q8 "$OUT/runs" "$cfg" "$REC" >> "$REC/steps.txt" 2>&1 || { note "STOP: controls-q8 not as declared"; exit 6; }
        fi
        if [ "$cfg" = M2S72-E0v-qdu-f2 ]; then
          python3 "$CHECKER" controls-sg "$OUT/runs" "$cfg" "$REC" >> "$REC/steps.txt" 2>&1 || { note "STOP: controls-sg not as declared"; exit 6; }
          held_release "$cfg" "controls-sg done"
        fi
        if [ "$o" = q0 ]; then
          [ -n "$held" ] && held_release "$held" "a higher Q-0 factor completed"
          held=$cfg
        fi
        s5_release || exit 7
      done
      top=$f
      if [ "$stop" = 1 ] && [ "$f" != 8 ]; then note "escalation stop after factor $f (E0 [A] rule: cohort Syncs not received by T_end > 50 % in Q-0 and Q-d)"; break; fi
    done
    tw=M2S72-E0vNL-q0-f$top
    s5_run "$tw" "$top" 0 || exit $?
    python3 "$CHECKER" nonpert "$OUT/runs" "M2S72-E0v-q0-f$top" "$tw" "$REC" >> "$REC/steps.txt" 2>&1; nrc=$?
    s5_manifest "$tw" || exit 5
    if [ "$nrc" != 0 ]; then
      s5_tier "$tw" B "non-perturbation not shown"; s5_tier "$held" B "non-perturbation not shown"
      note "STOP: MAC-log non-perturbation not shown"; exit 6
    fi
    printf "%s\tnonpert PASS\t%s\tC\t-\n" "$S5_LAST" "$S5_MAN" >> "$REC/runs.tsv"
    s5_tier "$tw" C ""; held_release "$held" "twin compared"
    s5_release || exit 7
    note "E0v batch end" ;;
  e0vp)
    for f in 1 2; do for o in q0p qde; do s5_full "M2S72-E0v-$o-f$f" "$f" 0 "" || exit $?; s5_release || exit 7; done; done
    note "E0v-p batch end" ;;
  e0vh5)
    s5_full M2S72-E0vH5-q0-f1 1 "${EST_B[1]}" "H5 twin" || exit $?
    s5_run M2S72-E0vH5NL-q0-f1 1 0 || exit $?
    python3 "$CHECKER" nonpert "$OUT/runs" M2S72-E0vH5-q0-f1 M2S72-E0vH5NL-q0-f1 "$REC" >> "$REC/steps.txt" 2>&1 || { s5_manifest M2S72-E0vH5NL-q0-f1; s5_tier M2S72-E0vH5NL-q0-f1 B "non-perturbation not shown"; s5_tier M2S72-E0vH5-q0-f1 B "non-perturbation not shown"; note "STOP: H5 non-perturbation not shown"; exit 6; }
    s5_manifest M2S72-E0vH5NL-q0-f1 || exit 5
    printf "%s\tnonpert PASS\t%s\tC\t-\n" "$S5_LAST" "$S5_MAN" >> "$REC/runs.tsv"
    s5_tier M2S72-E0vH5NL-q0-f1 C ""; held_release M2S72-E0vH5-q0-f1 "twin compared"
    s5_release || exit 7
    for cfg in M2S72-E0vH5-qdu-f1 M2S72-E0vH5-q0-f2 M2S72-E0vH5-qdu-f2; do
      s5_full "$cfg" "${cfg##*-f}" 0 "" || exit $?; s5_release || exit 7
    done
    note "E0v-H5 batch end" ;;
  smoke)
    # protocol §9: one run, everything kept. Its purpose is the review of the 1.8.1 MAC-log grammar (MG-1 census),
    # the run's size and wall time in this environment, and the lifecycle steps; it is not an E0v result and is not
    # repeated inside e0v. The wall-time limit is a fixed 60 min (the E0v limits are re-derived from this run).
    cfg=M2S72-E0v-q0-f1
    note "smoke start (S5_ENV_DECISION ${S5_ENV_DECISION}); raw outputs are held, never released or deleted"
    s5_run "$cfg" 1 0 3600 || exit $?
    s5_check "$cfg"; crc=$?
    s5_manifest "$cfg" || exit 5
    for x in "$REC/$cfg.check.txt" "$REC/$cfg.digest.json"; do [ -f "$x" ] && "${LIB[@]}" durable "$x"; done
    python3 "$CHECKER" quick "$OUT/runs" "$cfg" >> "$REC/steps.txt" 2>&1; qrc=$?
    note "$cfg: E0 quick proxy rc $qrc: $(tail -1 "$REC/steps.txt")"
    python3 "$CHECKER" controls-q8 "$OUT/runs" "$cfg" "$REC" >> "$REC/steps.txt" 2>&1; ctrc=$?
    note "$cfg: controls-q8 rc $ctrc (in memory; the raw outputs are read only)"
    chmod -R a-w "$OUT/runs/$cfg" "$OUT/runs/run-$cfg.log.gz"
    "${LIB[@]}" verify-manifest "$REC/$cfg.manifest.sha256" | tee -a "$REC/steps.txt"; vrc=${PIPESTATUS[0]}
    ledger "$cfg	held (smoke review; uncompressed, read-only, never released by this runner)"
    printf "%s\t%s\t%s\theld\tsmoke review; quick rc %s, controls-q8 rc %s, manifest re-verified rc %s\n" \
      "$S5_LAST" "$( [ "$crc" = 0 ] && echo PASS || echo "rc $crc")" "$S5_MAN" "$qrc" "$ctrc" "$vrc" >> "$REC/runs.tsv"
    du -sb "$OUT/runs/$cfg" "$OUT/runs/run-$cfg.log.gz" | tee -a "$REC/steps.txt"
    for x in "$REC"/*; do "${LIB[@]}" durable "$x"; done
    if [ "$crc$qrc$ctrc$vrc" != 0000 ]; then note "smoke end: NOT CLEAN (check $crc, quick $qrc, controls $ctrc, manifest $vrc)"; exit 6; fi
    note "smoke end: clean (check PASS, quick, controls-q8 as declared, manifest re-verified)" ;;
  release)
    [ "$STAGE" = M2-S7.2a-s5smoke ] && die "the smoke stage is never released by this runner (protocol §9)"
    [ -d "$REC" ] || die "$REC does not exist"
    s5_release ;;
esac
