#!/bin/bash
# M2-S7.2a Stage 5, work package A3: the E0v-N batch runner (protocol results/M2-S7.2a-e0vn-protocol.md).
# A NEW runner. m2s72s5.sh, m2s72.sh and every accepted runner, generator, checker, configuration and record are
# unchanged. It writes nothing under simulations/m2/results, never runs in legacy mode, never sets
# S5N_ADAPTER_VALIDATED (it only compares it with the maintainer's decision record) and never writes the FGO registry.
#
#   m2s72s5n.sh plan <h16|h5>     no simulation, no decision needed: pins, the declared combinations and the exact
#                                 command of every first run -> $RESULTS/M2-S7.2a-e0vn-plan-<seg>/records/plan.txt
#   m2s72s5n.sh e0vn <h16|h5>     the E0v-N saturation bracket of one segment (HARQ16: 28 combinations; HARQ5: 21),
#                                 one simulation at a time, each evaluated by the WP-A1 wrapper (check_m2s72_s5n21.py
#                                 run) and classified by the accepted m2s72_e1sel rules
#   m2s72s5n.sh select            no simulation: f_E1 from the two committed bracket records (S-1 / S-2)
#   m2s72s5n.sh release <stage>   commit the records of pending runs of <stage>, verify them, delete their raw outputs
#
# Required (no defaults; machine paths are never assumed):
#   S5_E0VN_MODE           production | test (step 161-R1). Exactly one of the two, explicitly:
#     production  genuine execution. Refused while any test hook is set (any S5_TEST_* or STUB_* variable, even empty),
#                 unless the evaluator is the pinned WP-A1 wrapper itself, and unless the authorization gate AG-1 is
#                 approved (m2s72_e0vn_batch.py gate; at present it is NOT, so production e0vn / select is refused).
#                 The build always runs.
#     test        synthetic execution with stub tools (the A3 suite): every stage is named M2-S7.2a-e0vn-TEST-*,
#                 the records destination carries TEST, env / ledger say "TEST MODE: never evidence". Hooks allowed:
#                 S5_TEST_SKIP_BUILD=1, a stub S5_E0VN_EVALUATOR.
#   NASCTIME_RESULTS_ROOT  absolute isolated root (nt_results.sh); legacy mode is refused
#   OMNETPP_ROOT INET_ROOT SIMU5G_ROOT; $SIMU5G_ROOT/Version must read 1.8.1
#   e0vn, select:
#     S5_E0VN_DECISIONS     the maintainer's decision record (format nasctime-s5-e0vn-decisions/1; see
#                           check/m2s72_e0vn_batch.py): S5-2-D1 .. D6, AC-5 / AC-6 references, the exact values below
#     S5N_ADAPTER_VALIDATED exported by the executor from that record (S5-2-D2); must equal its adapter_validated
#     S5_E0VN_DECISIONS_SIG the record's detached signature (ssh-keygen -Y sign -n nasctime-s5-e0vn-approval)
#     S5_E0VN_ALLOWED_SIGNERS the maintainer's public key, one line for principal wpa1-maintainer, obtained out of band
#   e0vn:
#     S5_ENV_DECISION       the Stage 5 environment decision (RD-7, D-2); must equal the record's env_decision
#     S5_E0VN_EVALUATOR     the per-run evaluator, named explicitly: the WP-A1 wrapper check/check_m2s72_s5n21.py
#                           (production: exactly that file; test: a stub, recorded as a test hook)
#     S5_E0VN_RUN_BYTES     the per-run raw-size estimate (bytes) for the free-space rule, re-derived from the
#                           smoke-n2 record (protocol §5.3); integer > 0
#     S5_E0VN_RUN_LIMIT_S   the per-run wall-time limit (s), re-derived from the smoke-n2 record; integer > 0
#     h5 with S5-2-D5 approved: S5_E0VN_H16_BRACKET = the committed HARQ16 bracket.tsv (start factors)
#   select: S5_E0VN_H16_BRACKET, S5_E0VN_H5_BRACKET (the committed bracket records of both segments)
# Optional:
#   S5_RECORDS_REPO   a clean git worktree: records are copied to simulations/results/simu5g-1.8.1/s5/<batch>/ (which
#                     must not exist when the batch starts), committed, verified in HEAD, and only then raw outputs of
#                     tier-C runs are deleted. Without it, raw outputs stay (pending) and the free-space rule stops the batch.
# Test hooks (S5_E0VN_MODE=test only; refused in production): S5_TEST_SKIP_BUILD=1, a stub S5_E0VN_EVALUATOR.
#
# Per run: free-space rule -> simulation (the exact argument vector of m2s72_e0vn_batch.py cmd) -> outcome
#   OK / SIM-ABORT / TIMEOUT / ERROR (m2s72s5_lib.py classify) -> manifest -> WP-A1 wrapper `run` (one process per
#   run, records in records/<cfg>/) -> bracket outcome (ok / overloaded / starved / invalid) -> bracket.tsv -> tier.
# Exit codes: 0 segment complete; 1 refused (mode / hooks / authorization / inputs / decisions / pins); 3 free-space STOP; 5 non-OK simulation
#   outcome; 6 wrapper rc != 0 (1 FAIL, 2 REFUSED / ERROR, 3 HELD FOR REVIEW, 4 INCOMPLETE) or a record that cannot be
#   written; 7 release failure; 8 a bracket stopped for review (invalid, non-monotone, below the ladder) or f_E1 STOP.
set -o pipefail
HERE=$(cd "$(dirname "$0")" && pwd)
NASCTIME=$(cd "$HERE/../.." && pwd)
MODE=${1:-}
SEG=${2:-}
die() { echo "ERROR: $*" >&2; exit 1; }
[ -n "$MODE" ] || die "usage: m2s72s5n.sh plan <h16|h5> | e0vn <h16|h5> | select | release <stage>"
# ----------------------------------------------------- execution mode: test hooks never reach production (161-R1) -----
case "${S5_E0VN_MODE-}" in
  production) PROD=1 ;;
  test) PROD= ;;
  *) die "S5_E0VN_MODE must be exactly 'production' or 'test' (got '${S5_E0VN_MODE-<unset>}'); there is no default" ;;
esac
if [ -n "$PROD" ]; then
  hooks=$(compgen -e | grep -E '^(S5_TEST_|STUB_)' | tr '\n' ' ')
  [ -z "$hooks" ] || die "production refused: test hook variable(s) set: ${hooks}(unset them; test hooks belong to S5_E0VN_MODE=test)"
fi
for v in OMNETPP_ROOT INET_ROOT SIMU5G_ROOT NASCTIME_RESULTS_ROOT; do
  [ -n "${!v:-}" ] || die "$v must be set explicitly (Stage 5 never assumes machine paths)"
done
[ "$(cat "$SIMU5G_ROOT/Version" 2>/dev/null)" = 1.8.1 ] || die "$SIMU5G_ROOT/Version is not 1.8.1"
case "$MODE" in
  plan|e0vn) case "$SEG" in h16|h5) ;; *) die "$MODE needs a segment: h16 or h5" ;; esac ;;
  select) [ -z "$SEG" ] || die "select takes no argument" ;;
  release) [ -n "$SEG" ] || die "release <stage>" ;;
  *) die "unknown mode $MODE" ;;
esac
export OMNETPP_ROOT INET_ROOT SIMU5G_ROOT
source "$NASCTIME/simulations/nt_results.sh"
nt_results_init m2 nobaseline
[ -n "$NT_ISOLATED" ] || die "isolated mode required"
CHK=$HERE/check
LIB=(python3 -B "$CHK/m2s72s5_lib.py")
BAT=(python3 -I -B "$CHK/m2s72_e0vn_batch.py")
WRAPPER=$CHK/check_m2s72_s5n21.py
posint() { [[ "$1" =~ ^[1-9][0-9]*$ ]]; }

T=""; [ -z "$PROD" ] && T=TEST-
case "$MODE" in
  plan) STAGE=M2-S7.2a-e0vn-${T}plan-$SEG ;;
  e0vn) STAGE=M2-S7.2a-e0vn-${T}$SEG ;;
  select) STAGE=M2-S7.2a-e0vn-${T}select ;;
  release) STAGE=$SEG ;;
esac
OUT=$RESULTS/$STAGE
REC=$OUT/records
BATCH="$(basename "$(dirname "$RESULTS")")-$STAGE"
TEST=""; [ -z "$PROD" ] && TEST="TEST MODE: synthetic execution; never evidence"
[ -n "${S5_TEST_SKIP_BUILD:-}" ] && TEST="$TEST; TEST HOOK ACTIVE (skip build)"

# ------------------------------------------------------------------------------- preconditions (fail closed) -----
if [ "$MODE" = e0vn ]; then        # the evaluator first: a substitution is refused for what it is, before authorization
  [ -n "${S5_E0VN_EVALUATOR:-}" ] || die "S5_E0VN_EVALUATOR is not set: name the per-run evaluator explicitly (the WP-A1 wrapper)"
  [ -f "$S5_E0VN_EVALUATOR" ] || die "S5_E0VN_EVALUATOR $S5_E0VN_EVALUATOR does not exist"
  if [ "$(realpath "$S5_E0VN_EVALUATOR")" != "$(realpath "$WRAPPER")" ]; then
    [ -z "$PROD" ] || die "production refused: S5_E0VN_EVALUATOR ($S5_E0VN_EVALUATOR) is not the WP-A1 wrapper $WRAPPER (a substituted evaluator)"
    TEST="${TEST:+$TEST; }TEST HOOK ACTIVE (evaluator $S5_E0VN_EVALUATOR is not the WP-A1 wrapper)"
  fi
fi
if [ "$MODE" = e0vn ] || [ "$MODE" = select ]; then
  [ -n "${S5_E0VN_DECISIONS:-}" ] || die "S5_E0VN_DECISIONS is not set: no maintainer decision record (S5-2-D1 .. D6, AC-5, AC-6)"
  dmsg=$("${BAT[@]}" decisions "$S5_E0VN_DECISIONS" "$( [ "$MODE" = select ] && echo select || echo "$SEG")") || die "decision record refused: $dmsg"
  D5=$(sed -n 's/^[[:space:]]*S5-2-D5[[:space:]]*=[[:space:]]*\([a-z-]*\)[[:space:]]*$/\1/p' "$S5_E0VN_DECISIONS")
  # AG-1: the record's signature (a correctly formatted record alone is never enough), then the gate itself
  amsg=$("${BAT[@]}" authorize "$S5_E0VN_DECISIONS" "${S5_E0VN_DECISIONS_SIG:-}" "${S5_E0VN_ALLOWED_SIGNERS:-}") || die "authorization refused: $amsg"
  gmsg=$("${BAT[@]}" gate "$S5_E0VN_MODE") || die "$gmsg"
fi
if [ "$MODE" = e0vn ]; then
  [ -n "${S5_ENV_DECISION:-}" ] || die "S5_ENV_DECISION is not set: the Stage 5 environment is not confirmed (RD-7)"
  posint "${S5_E0VN_RUN_BYTES:-}" || die "S5_E0VN_RUN_BYTES must be a positive integer (re-derived from the smoke-n2 record)"
  posint "${S5_E0VN_RUN_LIMIT_S:-}" || die "S5_E0VN_RUN_LIMIT_S must be a positive integer (re-derived from the smoke-n2 record)"
  if [ "$SEG" = h5 ] && [ "$D5" = approved ]; then
    [ -f "${S5_E0VN_H16_BRACKET:-}" ] || die "S5-2-D5 approved: S5_E0VN_H16_BRACKET must name the committed HARQ16 bracket.tsv"
  fi
fi
if [ "$MODE" = select ]; then
  [ -f "${S5_E0VN_H16_BRACKET:-}" ] || die "S5_E0VN_H16_BRACKET must name the committed HARQ16 bracket.tsv"
  [ -f "${S5_E0VN_H5_BRACKET:-}" ] || die "S5_E0VN_H5_BRACKET must name the committed HARQ5 bracket.tsv"
fi
if [ "$MODE" != release ]; then
  pmsg=$("${BAT[@]}" pins "$HERE") || die "accepted identities not as pinned: $pmsg"
  if [ -n "${S5_RECORDS_REPO:-}" ]; then
    [ ! -e "$S5_RECORDS_REPO/simulations/results/simu5g-1.8.1/s5/$BATCH" ] || die "records destination $BATCH exists in $S5_RECORDS_REPO (never overwritten)"
    git -C "$S5_RECORDS_REPO" diff --cached --quiet || die "$S5_RECORDS_REPO has staged changes"
  fi
  nt_fresh_out "$OUT"
  mkdir -p "$REC" "$OUT/runs"
fi
note() { echo "$(date -u +%FT%TZ) $*" | tee -a "$REC/steps.txt"; }
ledger() { printf "%s\t%s\n" "$(date -u +%FT%TZ)" "$*" >> "$REC/ledger.tsv"; "${LIB[@]}" durable "$REC/ledger.tsv"; }
env_record() {
  {
    echo "date_utc: $(date -u +%FT%TZ)"
    echo "mode: $MODE   segment: ${SEG:-n/a}   stage: $STAGE   batch: $BATCH"
    echo "S5_ENV_DECISION: ${S5_ENV_DECISION:-n/a}"
    [ -n "${S5_E0VN_DECISIONS:-}" ] && echo "decision_record: $S5_E0VN_DECISIONS sha256 $(sha256sum "$S5_E0VN_DECISIONS" | cut -d' ' -f1)"
    [ -n "${S5_E0VN_DECISIONS:-}" ] && echo "S5N_ADAPTER_VALIDATED (inherited, verbatim): ${S5N_ADAPTER_VALIDATED:-}"
    echo "evaluator: ${S5_E0VN_EVALUATOR:-n/a} sha256 $( [ -f "${S5_E0VN_EVALUATOR:-}" ] && sha256sum "$S5_E0VN_EVALUATOR" | cut -d' ' -f1 || echo n/a)"
    echo "execution mode: $S5_E0VN_MODE"
    [ -n "${amsg:-}" ] && echo "$amsg"
    [ -n "${gmsg:-}" ] && echo "gate: $gmsg"
    [ -n "$TEST" ] && echo "$TEST"
    echo "run_bytes_estimate: ${S5_E0VN_RUN_BYTES:-n/a}   run_limit_s: ${S5_E0VN_RUN_LIMIT_S:-n/a}"
    echo "omnetpp: $(opp_run -v 2>/dev/null | grep -m1 -i 'version' || true)"
    echo "inet_version_file: $(cat "$INET_ROOT/Version" 2>/dev/null || echo n/a)"
    echo "simu5g_version_file: $(cat "$SIMU5G_ROOT/Version")"
    echo "libsimu5g_sha256: $(sha256sum "$SIMU5G_ROOT/src/libsimu5g.so" 2>/dev/null | cut -d' ' -f1)"
    echo "nascTime_commit: $(git -C "$NASCTIME" rev-parse HEAD 2>/dev/null || echo n/a)$( [ -z "$(git -C "$NASCTIME" status --porcelain -- simulations/m2 src/nasctime ':!simulations/m2/results' 2>/dev/null)" ] || echo ' (+ uncommitted changes)')"
    echo "libnasctime_m2_sha256: $(sha256sum "$NASCTIME/src/nasctime/m2/libnasctime_m2.so" 2>/dev/null | cut -d' ' -f1)"
    for f in m2s72.ini m2s72s5.ini check/m2s72_fgo_registry.json check/check_m2s72_s5n21.py check/m2s72_e1sel.py check/m2s72_e0vn_batch.py m2s72s5n.sh; do
      echo "sha256 $f: $(sha256sum "$HERE/$f" | cut -d' ' -f1)"
    done
    echo "pins: $pmsg"
    echo "python: $(python3 --version 2>&1)   os: $(uname -srm)"
  } > "$REC/env-$MODE.txt"
  "${LIB[@]}" durable "$REC/env-$MODE.txt"
}

# ------------------------------------------------------------------------------------------------ lifecycle -----
s5_manifest() {   # sets S5_MAN
  local cfg=$1 m
  m=$("${LIB[@]}" manifest "$REC/$cfg.manifest.sha256" "$OUT/runs/$cfg" "$OUT/runs/run-$cfg.log.gz") || { note "manifest of $cfg FAILED"; return 1; }
  S5_MAN=$(sha256sum "$REC/$cfg.manifest.sha256" | cut -d' ' -f1)
  note "$m"
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
s5_release() {    # commit every record (recursively), verify in HEAD, then delete the pending runs' raw outputs
  [ -s "$REC/pending-release.txt" ] || return 0
  if [ -z "${S5_RECORDS_REPO:-}" ]; then note "release: S5_RECORDS_REPO not set; pending raw outputs kept"; return 0; fi
  local repo=$S5_RECORDS_REPO rel dest cfg f r rp=() lf=()
  git -C "$repo" diff --cached --quiet || { note "release refused: $repo has staged changes"; return 1; }
  rel=simulations/results/simu5g-1.8.1/s5/$BATCH
  dest=$repo/$rel; mkdir -p "$dest"
  while IFS= read -r -d '' f; do
    r=${f#"$REC"/}
    mkdir -p "$dest/$(dirname "$r")"; cp "$f" "$dest/$r"; rp+=("$rel/$r"); lf+=("$f")
  done < <(find "$REC" -type f -print0 | sort -z)
  git -C "$repo" add -f -- "${rp[@]}" || { note "release: git add failed"; return 1; }
  git -C "$repo" diff --cached --quiet || git -C "$repo" commit -q -m "S5 E0v-N records: $BATCH ($(wc -l < "$REC/pending-release.txt") run(s) released)" -- "${rp[@]}" \
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
  for f in ledger.tsv steps.txt pending-release.txt; do cp "$REC/$f" "$dest/"; done
  git -C "$repo" add -f -- "$rel/ledger.tsv" "$rel/steps.txt" "$rel/pending-release.txt"
  git -C "$repo" diff --cached --quiet || git -C "$repo" commit -q -m "S5 E0v-N records: $BATCH ledger after release" -- "$rel/ledger.tsv" "$rel/steps.txt" "$rel/pending-release.txt"
}
stop_b() {        # <cfg> <exit> <reason>: keep the run (tier B), record, stop the batch
  s5_tier "$1" B "$3"
  for x in "$REC"/*.txt "$REC"/*.tsv; do [ -f "$x" ] && "${LIB[@]}" durable "$x"; done
  note "STOP: $1: $3 (raw outputs kept, tier B)"; exit "$2"
}
# one bracket run: <combo key> <start> <factor> <cfg>
e0vn_run() {
  local key=$1 st=$2 f=$3 cfg=$4 t0 rc out det raw wrc oc why dg argv=()
  "${LIB[@]}" space "$OUT" "$S5_E0VN_RUN_BYTES" 0 | tee -a "$REC/steps.txt"
  [ "${PIPESTATUS[0]}" = 0 ] || { note "STOP before $cfg: free-space rule"; exit 3; }
  mapfile -d '' argv < <("${BAT[@]}" cmd "$NASCTIME" "$SIMU5G_ROOT" "$INET_ROOT" "$cfg" "$OUT/runs/$cfg")
  [ "${#argv[@]}" -gt 0 ] && [ "${argv[0]}" = opp_run ] || { note "STOP: no command for $cfg"; exit 6; }
  printf '%s\t%s\n' "$cfg" "timeout $S5_E0VN_RUN_LIMIT_S ${argv[*]}" >> "$REC/commands.tsv"; "${LIB[@]}" durable "$REC/commands.tsv"
  t0=$(date +%s)
  (cd "$HERE" && timeout "$S5_E0VN_RUN_LIMIT_S" "${argv[@]}" 2>&1 | gzip -n -1 > "$OUT/runs/run-$cfg.log.gz"; exit "${PIPESTATUS[0]}")
  rc=$?
  out=$("${LIB[@]}" classify "$rc" "$OUT/runs/run-$cfg.log.gz")
  det=${out#*$'\t'}; out=${out%%$'\t'*}
  raw=$(du -sb "$OUT/runs/$cfg" 2>/dev/null | cut -f1)
  note "$cfg: outcome $out (rc $rc, wall $(( $(date +%s) - t0 )) s, limit $S5_E0VN_RUN_LIMIT_S s, raw ${raw:-0} B): $det"
  s5_manifest "$cfg" || { note "STOP: manifest of $cfg failed; raw outputs left as they are (not a result)"; exit 5; }
  local last="$cfg	0	$out	$rc	$(( $(date +%s) - t0 ))	${raw:-0}"
  if [ "$out" != OK ]; then
    printf "%s\t-\t%s\tB\t%s\n" "$last" "$S5_MAN" "$det" >> "$REC/runs.tsv"
    "${BAT[@]}" record "$REC/bracket.tsv" "$key" "$st" "$f" invalid "$cfg" - - >> "$REC/steps.txt" 2>&1
    stop_b "$cfg" 5 "simulation outcome $out (not a result)"
  fi
  python3 -I -B "$S5_E0VN_EVALUATOR" run "$OUT/runs" "$cfg" "$REC/$cfg" > "$REC/$cfg.console.txt" 2>&1; wrc=$?
  note "$cfg: WP-A1 wrapper rc $wrc: $(tail -1 "$REC/$cfg.console.txt")"
  [ -d "$REC/$cfg" ] && find "$REC/$cfg" -type f -exec "${LIB[@]}" durable {} +
  "${LIB[@]}" durable "$REC/$cfg.console.txt"
  if [ "$wrc" != 0 ]; then
    local what; case "$wrc" in 1) what=FAIL ;; 3) what="HELD FOR REVIEW" ;; 4) what=INCOMPLETE ;; *) what="REFUSED / EVALUATION ERROR" ;; esac
    printf "%s\twrapper rc %s (%s)\t%s\tB\t%s\n" "$last" "$wrc" "$what" "$S5_MAN" "$(tail -1 "$REC/$cfg.console.txt")" >> "$REC/runs.tsv"
    "${BAT[@]}" record "$REC/bracket.tsv" "$key" "$st" "$f" invalid "$cfg" "$wrc" - >> "$REC/steps.txt" 2>&1
    stop_b "$cfg" 6 "wrapper rc $wrc ($what)"
  fi
  dg=$(sha256sum "$REC/$cfg/$cfg.s5n21.digest.json" 2>/dev/null | cut -d' ' -f1)
  oc=$("${BAT[@]}" outcome "$REC/$cfg/$cfg.s5n21.digest.json" "$cfg" "$wrc" "$out") || { printf "%s\tPASS\t%s\tB\toutcome not derivable: %s\n" "$last" "$S5_MAN" "$oc" >> "$REC/runs.tsv"; stop_b "$cfg" 6 "bracket outcome not derivable: $oc"; }
  why=${oc#*$'\t'}; oc=${oc%%$'\t'*}
  "${BAT[@]}" record "$REC/bracket.tsv" "$key" "$st" "$f" "$oc" "$cfg" "$wrc" "$dg" | tee -a "$REC/steps.txt"
  [ "${PIPESTATUS[0]}" = 0 ] || stop_b "$cfg" 6 "bracket record refused"
  note "$cfg: bracket outcome $oc ($why)"
  printf "%s\tPASS (%s)\t%s\tC\t-\n" "$last" "$oc" "$S5_MAN" >> "$REC/runs.tsv"
  "${LIB[@]}" durable "$REC/runs.tsv"
  s5_tier "$cfg" C ""
}

# ---------------------------------------------------------------------------------------------------- modes -----
case "$MODE" in
  plan)
    source "$OMNETPP_ROOT/setenv" -f >/dev/null 2>&1 || true
    env_record
    {
      echo "M2-S7.2a E0v-N batch plan, segment $SEG (A3 protocol; no simulation; not a result)"
      echo "pins: $pmsg"
      echo "ladder: 0.5 0.8 1 1.25 1.6 2 (m2s72_e1sel.LADDER); start 1.0 (B-1; HARQ5 with S5-2-D5 approved: the HARQ16 f_lo)"
      echo
      "${BAT[@]}" combos "$SEG" | while IFS=$'\t' read -r key c1; do
        mapfile -d '' argv < <("${BAT[@]}" cmd "$NASCTIME" "$SIMU5G_ROOT" "$INET_ROOT" "$c1" "$OUT/runs/$c1")
        printf '%s\tfirst run %s\t%s\n' "$key" "$c1" "${argv[*]}"
      done
      echo
      echo "combinations: $("${BAT[@]}" combos "$SEG" | wc -l); configurations: $("${BAT[@]}" configs "$SEG" | wc -l)"
    } > "$REC/plan.txt"
    "${LIB[@]}" durable "$REC/plan.txt"
    tail -1 "$REC/plan.txt" ;;
  e0vn)
    if [ -n "$PROD" ] || [ -z "${S5_TEST_SKIP_BUILD:-}" ]; then          # production: the build always runs
      "$NASCTIME/src/nasctime/m2/build.sh" > "$OUT/build.log" 2>&1 || die "build failed, see $OUT/build.log"
    fi
    source "$OMNETPP_ROOT/setenv" -f >/dev/null
    env_record
    nt_stack_record "$REC"
    cp "$S5_E0VN_DECISIONS" "$REC/decision-record.txt"; cp "$S5_E0VN_DECISIONS_SIG" "$REC/decision-record.txt.sig"
    cp "$S5_E0VN_ALLOWED_SIGNERS" "$REC/allowed_signers"
    "${LIB[@]}" durable "$REC/decision-record.txt" "$REC/decision-record.txt.sig" "$REC/allowed_signers"
    [ -n "$TEST" ] && ledger "-	$TEST"
    printf "config\tseed\toutcome\trc\twall_s\traw_bytes\tcheck\tmanifest_sha256\ttier\tdetail\n" > "$REC/runs.tsv"
    note "E0v-N segment $SEG start (S5_ENV_DECISION ${S5_ENV_DECISION}; S5-2-D5 $D5)"
    while IFS=$'\t' read -r key c1; do
      st=$("${BAT[@]}" start "$key" "$D5" "${S5_E0VN_H16_BRACKET:-}") || { note "STOP: start factor of $key: $st"; exit 8; }
      note "$key: bracket start $st"
      while :; do
        nx=$("${BAT[@]}" next "$REC/bracket.tsv" "$key" "$st") || { note "STOP: bracket record of $key: $nx"; exit 6; }
        case "$nx" in
          RUN*) IFS=$'\t' read -r _ f cfg <<< "$nx"; e0vn_run "$key" "$st" "$f" "$cfg"; s5_release || exit 7 ;;
          DONE*) IFS=$'\t' read -r _ stop lo hi detail <<< "$nx"
                 note "$key: bracket $stop (f_lo $lo, f_hi $hi: $detail)"
                 case "$stop" in bracketed|top) break ;; *) note "STOP: $key bracket $stop: review required (no f_lo)"; exit 8 ;; esac ;;
          *) note "STOP: unexpected planner output for $key: $nx"; exit 6 ;;
        esac
      done
    done < <("${BAT[@]}" combos "$SEG")
    s5_release || exit 7
    note "E0v-N segment $SEG end: every combination bracketed (bracket.tsv)" ;;
  select)
    env_record
    "${BAT[@]}" select "$S5_E0VN_MODE" "$S5_E0VN_DECISIONS" "$S5_E0VN_DECISIONS_SIG" "$S5_E0VN_ALLOWED_SIGNERS" \
      "$S5_E0VN_H16_BRACKET" "$S5_E0VN_H5_BRACKET" "$REC/fE1-selection.txt" > "$REC/select.console.txt" 2>&1; src=$?
    cat "$REC/select.console.txt"
    "${LIB[@]}" durable "$REC/select.console.txt"
    [ "$src" = 0 ] || { note "f_E1 selection STOP (rc $src): review required; no fallback (RD-2)"; exit 8; }
    note "f_E1 selected (a candidate until the verification runs V-1 .. V-4 pass)" ;;
  release)
    case "$STAGE" in M2-S7.2a-e0vn-${T}h16|M2-S7.2a-e0vn-${T}h5) ;; *) die "release: only the E0v-N segment stages of this mode (${T:-production})" ;; esac
    [ -d "$REC" ] || die "$REC does not exist"
    s5_release ;;
esac
