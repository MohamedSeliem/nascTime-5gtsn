#!/usr/bin/env bash
# The approved pre-flight configuration query and exactly ONE authorised simulation of the experiment's configuration
# (e3a: M2S4U, e3b: M2S5; run 0 of --repeat=10), each in its own
# guarded opp_env session started in tier-1's controlled directory, with lock gates, repository snapshots and a
# modification scan around them. Runs only if every earlier step (tier-1 C-1 .. C-12 prerequisites) succeeded.
. "$(dirname "$0")/../lib/t2common.sh"
case "$T2_EXPERIMENT" in e3a) want=M2S4U ;; e3b) want=M2S5 ;; *) want="" ;; esac
[[ -n "$want" && "$SIM_CONFIG" == "$want" && "$SIM_RUN" == 0 && "$SIM_REPEAT" == 10 && "$SIM_MAX_RUNS" == 1 ]] \
  || { echo "::error::pins do not authorise exactly $want run 0 of --repeat=10 for $T2_EXPERIMENT"; exit 1; }
[[ ! -e "$RAW" ]] || { echo "::error::raw output directory already exists"; exit 1; }
mkdir -p "$RAW"
git -C "$REPO" status --porcelain=v1 --untracked-files=all --ignored=matching > "$REC/git-status-before.txt"
touch "$REC/presim.marker"; sleep 1
"$T1_LIB/diskgate.sh" "before t2"
SESSION_ARGS="$T2_EXPERIMENT $REPO $WS $RAW $REC $EV $SIM_WALL_CAP_S $SIM_WATCHDOG_LIMIT_B $SIM_WATCHDOG_POLL_S $SIM_WATCHDOG_MEASURE_TIMEOUT_S"
rc=0
STAGE_CAP_S=$CAP_T2_RUNCONFIG_S oe_session t2-runconfig run -w "$WS" --build-modes release $PROJECTS \
  -c "bash $T2_DIR/session/run-sim.sh preflight $SESSION_ARGS" || rc=$?
"$T1_LIB/lockcheck.sh" after-t2-runconfig "$EV/t2-runconfig.log" || { (( rc )) || rc=1; }
cat "$REC/sim-control-preflight.txt" 2>/dev/null || true
grep -E '^(Config:|Run [0-9]+:)' "$RAW/effective-config.txt" 2>/dev/null || true
if (( rc == 0 )); then
  STAGE_CAP_S=$CAP_T2_SIM_S oe_session t2-sim run -w "$WS" --build-modes release $PROJECTS \
    -c "bash $T2_DIR/session/run-sim.sh sim $SESSION_ARGS" || rc=$?
  "$T1_LIB/lockcheck.sh" after-t2-sim "$EV/t2-sim.log" || { (( rc )) || rc=1; }
else
  echo "::error::pre-flight failed (exit $rc); the simulation is not started"
fi
# Modification scan: nothing in the repository (outside .git) or in the three project trees may change. opp_env's own
# per-project state directories (.opp_env/) are excluded and listed separately.
find "$REPO" "$WS/omnetpp-6.5.0" "$WS/inet-4.7.0" "$WS/simu5g-1.8.1" -newer "$REC/presim.marker" -type f \
  ! -path "$REPO/.git/*" ! -path "$WS/*/.opp_env/*" > "$REC/modified-during-sim.txt"
find "$WS" -newer "$REC/presim.marker" -type f -path "$WS/*/.opp_env/*" > "$REC/opp_env-state-changed.txt"
git -C "$REPO" status --porcelain=v1 --untracked-files=all --ignored=matching > "$REC/git-status-after.txt"
cat "$REC/sim-control-sim.txt" 2>/dev/null || true
if [[ -f "$RAW/run-$SIM_CONFIG.log" ]]; then
  tail -n 25 "$RAW/run-$SIM_CONFIG.log" > "$E3/run-tail.txt"; screened_cat "$E3/run-tail.txt"
fi
exit "$rc"
