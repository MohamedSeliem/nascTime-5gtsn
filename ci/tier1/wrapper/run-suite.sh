#!/usr/bin/env bash
# usage: bash run-suite.sh <tier-1 dir> <repo> <evidence dir> <suite work dir>. Runs INSIDE the opp_env session.
# Runs the existing A2-V1 wrapper regression suite (simulations/m2/check/test_m2s72a2v1_wrapper.py) unchanged, with the
# real OMNeT++ reachable only through the audit shim (C1/C2). Nothing in the repository, the suite, the wrapper or the
# configurations is modified. The suite's own temporary directories live under <suite work dir>/tmp.
set -uo pipefail
T1=$1; REPO=$2; EVD=$3; W=$4
fail() { echo "suite_setup: FAIL ($*)" >> "$EVD/wrapper-setup.txt"; echo "::error::wrapper suite setup: $*"; exit 3; }
: > "$EVD/wrapper-setup.txt"
REAL_ROOT=${OMNETPP_ROOT:-}
[[ -n "$REAL_ROOT" && -f "$REAL_ROOT/setenv" && -x "$REAL_ROOT/bin/opp_run" ]] || fail "real OMNeT++ not found in the session"
[[ -d "${SIMU5G_ROOT:-}/src/simu5g" ]] || fail "SIMU5G_ROOT has no src/simu5g source tree"
REAL=$(realpath "$REAL_ROOT/bin/opp_run")
SHA=$(sha256sum "$REAL" | cut -c1-64)
# The binary must be the one validated by C-10 (binaries.tsv row omnetpp/executable/.../bin/opp_run).
VSHA=$(awk -F'\t' '$1=="omnetpp" && $3 ~ /\/bin\/opp_run$/ {print $5}' "$EVD/binaries.tsv")
[[ -n "$VSHA" && "$SHA" == "$VSHA" ]] || fail "opp_run differs from the validated binary"
INTERP=$(patchelf --print-interpreter "$REAL" 2>/dev/null) && [[ -x "$INTERP" ]] || fail "ELF interpreter unavailable"
RD=$(command -v readelf || command -v llvm-readelf) || fail "readelf unavailable"
# RUNPATH entries of opp_run and the OMNeT++ libraries it loads: relative entries are inspected in every approved
# working directory; absolute non-store entries that do not exist now must still not exist at every call.
rel=(); absent=()
for f in "$REAL" "$REAL_ROOT"/lib/*.so; do
  for d in $("$RD" -d "$f" 2>/dev/null | sed -n 's/.*(\(RUNPATH\|RPATH\)).*\[\(.*\)\]/\2/p' | tr ':' ' '); do
    case "$d" in
      /nix/store/*) ;;
      /*) [[ -e "$d" ]] || absent+=("$d") ;;
      *) rel+=("$d") ;;
    esac
  done
done
mapfile -t rel < <(printf '%s\n' "${rel[@]}" | sed '/^$/d' | sort -u)
mapfile -t absent < <(printf '%s\n' "${absent[@]}" | sed '/^$/d' | sort -u)
for d in "${absent[@]}"; do [[ "$d" != *" "* ]] || fail "RUNPATH entry with a space"; done
A="$W/audit-omnetpp"; TMPROOT="$W/tmp"
rm -rf "$A" "$TMPROOT"; mkdir -p "$A/bin" "$TMPROOT"
install -m 0555 "$T1/wrapper/opp_run-audit.sh" "$A/bin/opp_run"
install -m 0444 "$T1/wrapper/setenv-audit.sh" "$A/setenv"
LOG="$EVD/opp_run-audit.tsv"
printf 'seq\tutc\tdecision\tkind\tcwd\targv\texit\tdetail\n' > "$LOG"
{
  printf 'AUDIT_REAL=%q\nAUDIT_REAL_SHA256=%q\nAUDIT_REAL_ROOT=%q\nAUDIT_INTERP=%q\n' "$REAL" "$SHA" "$REAL_ROOT" "$INTERP"
  printf 'AUDIT_PROJECT_LIB=%q\nAUDIT_REPO=%q\nAUDIT_TMPROOT=%q\nAUDIT_LOG=%q\n' "$(realpath "$REAL_ROOT/lib")" "$(realpath "$REPO")" "$(realpath "$TMPROOT")" "$LOG"
  printf 'AUDIT_RELATIVE_RUNPATH=%q\nAUDIT_ABSENT_RUNPATH=%q\n' "${rel[*]}" "${absent[*]}"
} > "$A/audit.conf"
chmod 0444 "$A/audit.conf"
{
  echo "suite: simulations/m2/check/test_m2s72a2v1_wrapper.py (unchanged)"
  echo "suite_sha256: $(sha256sum "$REPO/simulations/m2/check/test_m2s72a2v1_wrapper.py" | cut -c1-64)"
  echo "wrapper_sha256: $(sha256sum "$REPO/simulations/m2/m2s72a2v1.sh" | cut -c1-64)"
  echo "real_opp_run_sha256: $SHA (equals the validated binary)"
  echo "relative_runpath_entries_inspected: ${rel[*]:-none}"
  echo "absent_runpath_entries_watched: $(printf '%s\n' "${absent[@]}" | sed "s#^$W#<suite-work>#" | paste -sd ' ')"
  echo "python: $(command -v python3) | $(python3 -V 2>&1)"
  echo "simu5g_source_tree: SIMU5G_ROOT/src/simu5g of the compiled opp_env Simu5G 1.8.1 tree"
  echo "results_root_env: ${A2V1_RESULTS_ROOT:-<unset>}"
  echo "vm_results_root_present_before: $([[ -e /mnt/nasctime-results ]] && echo yes || echo no)"
  echo "suite_setup: PASS"
} >> "$EVD/wrapper-setup.txt"
[[ -z "${A2V1_RESULTS_ROOT:-}" ]] || fail "A2V1_RESULTS_ROOT is set"
git -C "$REPO" status --porcelain=v1 --untracked-files=all --ignored=matching > "$W/git-status-before.txt" || fail "git status"
cd "$REPO/simulations/m2/check" || fail "suite directory"
set +e
env -u A2V1_RESULTS_ROOT -u A2V1_COMMIT OMNETPP_ROOT="$A" TMPDIR="$TMPROOT" PYTHONDONTWRITEBYTECODE=1 \
  python3 -B test_m2s72a2v1_wrapper.py > "$EVD/wrapper-suite.txt" 2>&1
rc=$?

echo "suite_exit: $rc" >> "$EVD/wrapper-setup.txt"
echo "vm_results_root_present_after: $([[ -e /mnt/nasctime-results ]] && echo yes || echo no)" >> "$EVD/wrapper-setup.txt"
echo "unauthorised_marker: $([[ -e "$A/UNAUTHORISED" ]] && echo present || echo absent)" >> "$EVD/wrapper-setup.txt"
git -C "$REPO" status --porcelain=v1 --untracked-files=all --ignored=matching > "$W/git-status-after.txt" || fail "git status"
cp "$W/git-status-before.txt" "$EVD/wrapper-git-status-before.txt"; cp "$W/git-status-after.txt" "$EVD/wrapper-git-status-after.txt"
exit 0
