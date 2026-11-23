#!/usr/bin/env bash
# WP-A1: DR-13 path-resolution validation (runbook revision 3, section 6.3). NOT the WP-A1 validation: no WP-A1 code is
# run. It validates the two approved methods on the recovered archives before any independent evaluation.
#   dr13-validate.sh b   in the 'mapped' profile (X read-only, NO mount at R): method (b), in-memory prefix mapping
#   dr13-validate.sh a   in the 'mounted' profile (X read-only at X and at R): method (a), read-only mount
# Output: $Z/dr13-validation/ (fresh per mode). Exit 0 only if every DV check of the mode passes.
STAGE=dr13-validate
. "$(dirname "$0")/common.sh"
load_vars
[ $# -eq 1 ] && { [ "$1" = a ] || [ "$1" = b ]; } || stop "usage: dr13-validate.sh a|b"
mode=$1
[ -d "$X" ] || stop "X missing"
ro_path "$X"
DV="$Z/dr13-validation"; mkdir -p "$DV"; O="$DV/mode-$mode"
[ ! -e "$O" ] || stop "$O exists (single attempt)"
mkdir "$O"
MANIFESTS=(s5-smoke-1/m2/M2-S7.2a-s5smoke/records/M2S72-E0v-q0-f1.manifest.sha256
           s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256
           a2-nack-1/records/M2S72-E0vN-q0-one0-n2-f1_A2V1.manifest.sha256)
SEAL=3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0
FXSHA=cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b
snap() { (cd "$X" && find . -printf '%y %m %s %T@ %p\n' | LC_ALL=C sort); }
map() { awk -v a="  $R/" -v b="  $2/" '{ i = index($0, a); print substr($0, 1, i - 1) b substr($0, i + length(a)) }' "$1"; }
prefixed() { awk -v p="$R/" '$0 !~ /^[0-9a-f]{64}  [0-9]+  \// || index($0, "  " p) == 0 { bad++ } END { exit bad > 0 }' "$1"; }
pass() { echo "PASS $*" | tee -a "$O/results.txt"; }
snap > "$O/x-before.txt"

if [ "$mode" = b ]; then
  [ ! -e "$R" ] || stop "$R is visible: method (b) must be validated without the mount"
  # DV-b1: every original manifest verifies through the mapped stream (hash and size), nothing written
  for m in "${MANIFESTS[@]}"; do
    prefixed "$X/$m" || stop "DV-b1 $m: a line is malformed or not under $R/"
    out=$($PY "$CHK/m2s72s5_lib.py" verify-manifest <(map "$X/$m" "$X") 2>&1); rc=$?
    echo "$m rc=$rc $out" >> "$O/b1.txt"; [ "$rc" -eq 0 ] && [ "$out" = "manifest verified" ] || stop "DV-b1 $m"
  done; pass "DV-b1 three manifests verified by in-memory mapping"
  # DV-b2: negative control on a COPY - the smallest entry of the N = 1 manifest, copied to a scratch tree; the
  # unmodified copy verifies (0), a one-byte change is detected (1). The original is never touched; the copy is deleted.
  m="$X/${MANIFESTS[0]}"
  line=$(sort -t' ' -k3,3n "$m" | awk -F'  ' '$2 > 0' | head -n 1); [ -n "$line" ] || stop "DV-b2 no non-empty entry"
  rel=${line#*  *  }; rel=${rel#"$R"/}
  SC="$O/scratch"; mkdir -p "$SC/$(dirname "$rel")" && cp "$X/$rel" "$SC/$rel" && chmod u+w "$SC/$rel" || stop "DV-b2 copy"
  r1=$($PY "$CHK/m2s72s5_lib.py" verify-manifest <(printf '%s\n' "$line" | awk -v a="  $R/" -v b="  $SC/" '{ i = index($0, a); print substr($0, 1, i - 1) b substr($0, i + length(a)) }') 2>&1); c1=$?
  python3 -I -c 'import sys; p = sys.argv[1]; b = bytearray(open(p, "rb").read()); b[0] ^= 1; open(p, "wb").write(bytes(b))' "$SC/$rel" || stop "DV-b2 flip"
  r2=$($PY "$CHK/m2s72s5_lib.py" verify-manifest <(printf '%s\n' "$line" | awk -v a="  $R/" -v b="  $SC/" '{ i = index($0, a); print substr($0, 1, i - 1) b substr($0, i + length(a)) }') 2>&1); c2=$?
  echo "copy of $rel: unmodified rc=$c1 '$r1'; one byte changed rc=$c2 '$r2'" > "$O/b2.txt"; rm -rf "$SC"
  [ "$c1" -eq 0 ] && [ "$c2" -eq 1 ] || stop "DV-b2 negative control not as declared"
  pass "DV-b2 a changed copy is detected through the mapping"
  # DV-b3: a fail-closed tool refuses the mapped root: the extractor on --results-root X must NOT succeed (E-3: the
  # manifest entries lie under /mnt/nasctime-results, not under X). It is not weakened; method (a) is used for it.
  $PY "$CHK/m2s72_a21_fixture.py" extract --results-root "$X" --seal-sha256 "$SEAL" --out "$O/extract-mapped" > "$O/b3.txt" 2>&1; c3=$?
  echo "rc=$c3" >> "$O/b3.txt"; [ "$c3" -ne 0 ] || stop "DV-b3 the extractor accepted a mapped root"
  pass "DV-b3 the extractor refuses the mapped root (rc $c3)"
else
  ro_path "$R"
  # DV-a1: the mount shows exactly the extraction and is not writable (checked without creating anything)
  diff <(cd "$R" && find . -printf '%y %s %p\n' | LC_ALL=C sort) <(cd "$X" && find . -printf '%y %s %p\n' | LC_ALL=C sort) > "$O/a1.txt" \
    || stop "DV-a1 mount differs from X"
  pass "DV-a1 read-only mount at $R shows X"
  # DV-a2: the unchanged original manifests verify through the mount with the accepted tool
  for m in "${MANIFESTS[@]}"; do
    out=$($PY "$CHK/m2s72s5_lib.py" verify-manifest "$R/$m" 2>&1); rc=$?
    echo "$m rc=$rc $out" >> "$O/a2.txt"; [ "$rc" -eq 0 ] && [ "$out" = "manifest verified" ] || stop "DV-a2 $m"
  done; pass "DV-a2 three original manifests verified through the mount"
  # DV-a3: the accepted extractor (E-0 ... E-7) passes on the original prefix and reproduces the F3 fixture
  $PY "$CHK/m2s72_a21_fixture.py" extract --results-root "$R" --seal-sha256 "$SEAL" --out "$O/extract" > "$O/a3.txt" 2>&1 || stop "DV-a3 extractor"
  grep -q "^$FXSHA  a2v1-first-chain.log.gz$" "$O/extract/a2v1-first-chain.log.gz.sha256" || stop "DV-a3 fixture not reproduced"
  pass "DV-a3 extractor PASS on $R; F3 fixture reproduced"
fi
snap > "$O/x-after.txt"
cmp -s "$O/x-before.txt" "$O/x-after.txt" || stop "X changed during the validation (type, mode, size, mtime or path)"
pass "DV-$mode-x X unchanged (type, mode, size, mtime, path)"
(cd "$O" && find . -type f ! -name SHA256SUMS -print0 | LC_ALL=C sort -z | xargs -0 sha256sum) > "$O/SHA256SUMS"
echo "DR-13 method ($mode) validation PASS; record sha256 of $O/SHA256SUMS: $(sha256sum "$O/SHA256SUMS" | cut -d' ' -f1)"
exit 0
