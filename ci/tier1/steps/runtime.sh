#!/usr/bin/env bash
# C-4 host C++ runtime. An in-session link probe (no framework code; probe binaries are never executed) decides:
#   case A  `-lc++` links: the provenance gate must establish the host-contamination chain; then the verified host
#           libc++ development packages are removed (hostfix.sh) and the probes are repeated;
#   case B  `-lc++` already fails exactly with 'unable to find library -lc++': clean host, nothing is removed;
#   other   fail closed.
# In both cases the negative control and the positive GNU-runtime controls must pass before any framework build.
. "$(dirname "$0")/../lib/common.sh"
export STAGE_CAP_S=$CAP_RUNTIME_S
dpkg-query -W -f '${Package}\t${Version}\t${Status}\n' | sort > "$EV/host-packages-before.tsv"
grep -E '^(libc\+\+|libunwind|clang|lld|llvm)' "$EV/host-packages-before.tsv" > "$EV/host-cxx-packages-before.tsv" || true
cat "$EV/host-cxx-packages-before.tsv"
oe_session probe-runtime-before run -w "$WS" --build-modes release $PROJECTS \
  -c "bash $T1_DIR/session/runtime-probe.sh $EV/runtime-probe-before.txt before $PROBES/before"
"$T1_LIB/lockcheck.sh" after-runtime-probe-before "$EV/probe-runtime-before.log"
screened_cat "$EV/runtime-probe-before.txt"
/usr/bin/python3 -I "$PY/runtime_gates.py" runpath "$EV/runtime-probe-before.txt" before "$EV/runpath-observation.txt"
if ! c=$(/usr/bin/python3 -I "$PY/runtime_gates.py" case "$EV/runtime-probe-before.txt"); then
  echo "c4_case: INVALID" > "$EV/c4-case.txt"
  echo "before-probe neither links libc++ nor fails with 'unable to find library -lc++'" > "$EV/HYPOTHESIS_NOT_CONFIRMED"
  echo "::error::C-4: unexpected runtime-probe outcome; failing closed before any change or build"; exit 1
fi
echo "c4_case: $c" | tee "$EV/c4-case.txt"
if [[ "$c" == B ]]; then
  echo "case B: the host offers no libc++ to the Nix toolchain; nothing is removed"
  /usr/bin/python3 -I "$PY/runtime_gates.py" gates "$EV/runtime-probe-before.txt" "$EV/runtime-gates.txt" B \
    || { echo "::error::C-4 (case B): GNU-runtime controls failed; no framework build started"; exit 1; }
  exit 0
fi
if ! /usr/bin/python3 -I "$PY/provenance.py" "$EV/runtime-probe-before.txt" "$EV/host-libcxx.txt"; then
  grep '^problem: ' "$EV/host-libcxx.txt" | sed 's/^problem: //' | paste -sd ';' > "$EV/HYPOTHESIS_NOT_CONFIRMED"
  echo "::error::C-4 (case A): host-contamination chain NOT established; nothing removed, no build"; exit 1
fi
bash "$T1_DIR/steps/hostfix.sh"
oe_session probe-runtime-after run -w "$WS" --build-modes release $PROJECTS \
  -c "bash $T1_DIR/session/runtime-probe.sh $EV/runtime-probe-after.txt after $PROBES/after"
"$T1_LIB/lockcheck.sh" after-runtime-probe-after "$EV/probe-runtime-after.log"
screened_cat "$EV/runtime-probe-after.txt"
/usr/bin/python3 -I "$PY/runtime_gates.py" runpath "$EV/runtime-probe-after.txt" after "$EV/runpath-observation.txt"
/usr/bin/python3 -I "$PY/runtime_gates.py" gates "$EV/runtime-probe-after.txt" "$EV/runtime-gates.txt" A \
  || { echo "::error::C-4 (case A): post-correction probes failed; no framework build started"; exit 1; }
