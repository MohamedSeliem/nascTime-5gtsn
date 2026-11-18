#!/bin/bash
# Tier-1 audit shim installed as <audit root>/bin/opp_run for the A2-V1 wrapper regression suite (C1, C2).
# It forwards to the real OMNeT++ opp_run ONLY an exactly approved argument vector, from an approved working
# directory, after the working-directory library-search hazards have been inspected; everything else is refused with
# exit 97. Every call (forwarded or refused) is logged with its argument vector, actual working directory and exit
# status. On success it prints nothing itself (the callers capture the simulator's output byte for byte).
# This is a REGRESSION SAFEGUARD for the existing suite, not a security boundary: the suite and this shim are
# PR-controlled code running on a disposable hosted runner.
set -u
A=$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd -P)
# shellcheck source=/dev/null
. "$A/audit.conf"
seq=$(( $(wc -l < "$AUDIT_LOG") ))
cwd=$(pwd -P)
argv=("$@")
joined=$(printf '%s\x1f' "${argv[@]}")
# The only approved argument vectors: the two configuration queries the suite and the wrapper make (exact order, no
# additional, duplicate or alternative mode/query arguments) and the bare identity query.
BASE_Q=$'-u\x1fCmdenv\x1f-f\x1fm2s72s5.ini\x1f-c\x1fM2S72-E0vN-q0-one0-n2-f1\x1f-r\x1f0\x1f-q\x1frunconfig\x1f'
A2V1_Q=$'-u\x1fCmdenv\x1f-f\x1fm2s72a2v.ini\x1f-c\x1fM2S72-E0vN-q0-one0-n2-f1_A2V1\x1f-r\x1f0\x1f-q\x1frunconfig\x1f'
kind=""
if [[ ${#argv[@]} == 10 && "$joined" == "$BASE_Q" ]]; then kind=runconfig-base
elif [[ ${#argv[@]} == 10 && "$joined" == "$A2V1_Q" ]]; then kind=runconfig-a2v1
elif [[ ${#argv[@]} == 1 && "${argv[0]}" == -v ]]; then kind=identity
fi
show() { local s=$1; s=${s//"$AUDIT_TMPROOT"/<suite-tmp>}; s=${s//"$AUDIT_REPO"/<repo>}; printf '%s' "$s"; }
log() {  # decision kind exit reason
  printf '%s\t%s\t%s\t%s\t%s\t%s\t%s\t%s\n' "$seq" "$(date -u +%FT%TZ)" "$1" "$2" "$(show "$cwd")" \
    "$(show "${argv[*]}")" "$3" "$4" >> "$AUDIT_LOG"
}
refuse() {
  log REFUSED "${kind:-unapproved}" 97 "$1"
  echo "$(date -u +%FT%TZ) seq=$seq $1" >> "$A/UNAUTHORISED"
  echo "tier-1 audit: opp_run call refused: $1" >&2
  exit 97
}
[[ -n "$kind" ]] || refuse "argument vector is not one of the approved configuration-query or identity calls"
# Approved working directories: the repository's simulations/m2, or simulations/m2 of a suite clone directly under
# the suite's private temporary root.
cwd_ok=no
if [[ "$cwd" == "$AUDIT_REPO/simulations/m2" ]]; then cwd_ok=yes
elif [[ "$cwd" == "$AUDIT_TMPROOT"/* ]]; then
  IFS=/ read -r -a parts <<< "${cwd#"$AUDIT_TMPROOT"/}"
  [[ ${#parts[@]} == 4 && -n "${parts[0]}" && "${parts[1]}/${parts[2]}/${parts[3]}" == repo/simulations/m2 ]] && cwd_ok=yes
fi
[[ "$cwd_ok" == yes ]] || refuse "working directory not approved"
# The real binary: verified absolute path outside the audit root, unchanged since validation (no PATH lookup, no recursion).
[[ "$AUDIT_REAL" == /* && "$AUDIT_REAL" != "$A"/* && -x "$AUDIT_REAL" ]] || refuse "real opp_run path invalid"
[[ "$(sha256sum "$AUDIT_REAL" | cut -c1-64)" == "$AUDIT_REAL_SHA256" ]] || refuse "real opp_run changed since validation"
# Working-directory hazards (C2): relative RUNPATH entries resolve against this directory and must supply no shared
# library; absent absolute non-store entries must still be absent; and the loader's resolution of opp_run from this
# directory must use only /nix/store and the OMNeT++ project library directory.
hz=""
for e in $AUDIT_RELATIVE_RUNPATH; do
  libs=$(find "$cwd/$e" -maxdepth 1 \( -name '*.so' -o -name '*.so.*' \) 2>/dev/null | head -5 | paste -sd ',')
  [[ -z "$libs" ]] || hz="$hz shared libraries in relative RUNPATH entry '$e': $(show "$libs");"
done
for d in $AUDIT_ABSENT_RUNPATH; do
  [[ ! -e "$d" ]] || hz="$hz RUNPATH entry $(show "$d") now exists;"
done
lst=$("$AUDIT_INTERP" --list "$AUDIT_REAL" 2>&1) || hz="$hz loader listing failed;"
bad=$(sed -n 's/^[[:space:]]*[^ ]* => \(.*\) (0x[0-9a-f]*)$/\1/p' <<< "$lst" | grep -v -E "^(/nix/store/|$AUDIT_PROJECT_LIB/)" | paste -sd ',')
[[ -z "$bad" ]] || hz="$hz unexpected resolution: $(show "$bad");"
! grep -q 'not found' <<< "$lst" || hz="$hz unresolved dependency;"
[[ -z "$hz" ]] || refuse "working-directory hazard:$hz"
"$AUDIT_REAL" "$@"
rc=$?
log FORWARDED "$kind" "$rc" "hazards none"
exit "$rc"
