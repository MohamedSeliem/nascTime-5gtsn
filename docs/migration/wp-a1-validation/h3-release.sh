#!/usr/bin/env bash
# WP-A1 validation, phase H-3 (runbook revision 3): release SHA-256 verification and fail-closed extraction into X.
# usage: h3-release.sh qualification | validation
#   qualification: the session that produces the DR-13 and G0-RO records (no WP-A1 validation; E must not exist)
#   validation:    the WP-A1 validation session; only after gate B is GO (R1: no evidence access before P-0 passed)
# Runs in the network-less container with REL mounted read-only and the parent of X read-write.
# Never modifies an archive: REL is read-only, every archive is re-verified after the extraction.
STAGE=h3-release
. "$(dirname "$0")/common.sh"
load_vars
case "${1:-}" in
  qualification) [ ! -e "$E" ] || stop "qualification session: E must not exist" ;;
  validation) gate_b_go ;;
  *) stop "usage: h3-release.sh qualification|validation" ;;
esac
gate_a
ro_path "$REL"
O="$Z/release-record"
[ ! -e "$O" ] || stop "$O exists (single attempt)"
mkdir "$O" || stop "cannot create $O"

# 1. the release checksum list is the approved one (its sha256 comes from the maintainer's approval record, out of band)
want=$(aval gate-a.txt release_sums_sha256); is_hex64 "$want" || stop "release_sums_sha256 is not 64 hex digits"
[ -f "$REL/SHA256SUMS" ] || stop "$REL/SHA256SUMS missing"
got=$(sha256sum "$REL/SHA256SUMS" | cut -d' ' -f1)
echo "SHA256SUMS sha256 $got (approved $want)" | tee "$O/sums-identity.txt"
[ "$got" = "$want" ] || stop "SHA256SUMS is not the approved one"

# 2. exactly the three approved archives; each listed exactly once; verified without --ignore-missing
mapfile -t ARCH < <(grep '^archive=' "$APPROVALS/gate-a.txt" | cut -d= -f2-)
[ "${#ARCH[@]}" -eq 3 ] || stop "the signed gate-A statement must name exactly 3 archives, names ${#ARCH[@]}"
: > "$O/selected.sha256"
for a in "${ARCH[@]}"; do
  case "$a" in */*|.*|"") stop "archive name '$a' is not a plain file name";; esac
  n=$(awk -v f="$a" '{ x = $0; sub(/^[0-9a-f]{64} [ *]/, "", x); if (x == f) c++ } END { print c + 0 }' "$REL/SHA256SUMS")
  [ "$n" = 1 ] || stop "$a is listed $n times in SHA256SUMS"
  awk -v f="$a" '{ x = $0; sub(/^[0-9a-f]{64} [ *]/, "", x); if (x == f) print }' "$REL/SHA256SUMS" >> "$O/selected.sha256"
  [ -f "$REL/$a" ] && [ ! -L "$REL/$a" ] || stop "$REL/$a is not a regular file"
done
(cd "$REL" && sha256sum -c --strict "$O/selected.sha256") > "$O/verify-before.txt" 2>&1 || stop "release SHA-256 verification failed (see $O/verify-before.txt)"

# 3. extraction into a fresh X, archive by archive; no member may overwrite another
[ ! -e "$X" ] || stop "X $X exists (it must be created fresh by this stage)"
mkdir "$X" || stop "cannot create X"
for a in "${ARCH[@]}"; do
  $PY "$Z/scripts/extract_checked.py" "$REL/$a" "$X" "$O/members-$a.txt" > "$O/extract-$a.txt" 2>&1 \
    || stop "extraction of $a refused (see $O/extract-$a.txt); X is left as found"
done

# 4. the archives are unchanged after the extraction; X becomes read-only
(cd "$REL" && sha256sum -c --strict "$O/selected.sha256") > "$O/verify-after.txt" 2>&1 || stop "an archive changed during the extraction"
chmod -R a-w "$X" || stop "cannot make X read-only"
[ -z "$(find "$X" ! -type f ! -type d)" ] || stop "X holds something other than regular files and directories"
(cd "$X" && find . -type f | LC_ALL=C sort) > "$O/x-files.txt"
echo "X files $(wc -l < "$O/x-files.txt")" | tee "$O/summary.txt"
echo "h3-release ($1) complete" > "$O/h3.done"
echo "H-3: release verified and extracted (no evidence evaluated)"
exit 0
