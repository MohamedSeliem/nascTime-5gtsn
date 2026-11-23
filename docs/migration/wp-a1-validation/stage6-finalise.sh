#!/usr/bin/env bash
# WP-A1 validation, Stage 6 (runbook revision 3): evidence finalisation F-2 ... F-9 (corrected P-4). Runs after Stage 5,
# or after any stop from Stage 2 on, in a network-less container WITHOUT evidence mounts, under the separate
# finalisation transcript. Prints the SHA256SUMS.final line, which the executor records at once (F-10).
STAGE=stage6-finalise
. "$(dirname "$0")/common.sh"
load_vars
[ -d "$E" ] || stop "no evidence directory: nothing to finalise"
[ ! -e "$E/SHA256SUMS" ] && [ ! -e "$E/SHA256SUMS.final" ] || stop "already finalised"

# F-2 expectation files, registry and worktree unchanged after the run
mkdir -p "$E/supplementary"
{ (cd "$CHK" && sha256sum -c --strict) <<'EOF'
b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b  expect/vn1.expect.json
5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3  expect/vn2.expect.json
fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d  expect/vv1.expect.json
2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae  m2s72_fgo_registry.json
EOF
  echo "expectation/registry check rc=$?"
  echo "worktree status: '$(git -C "$W" status --porcelain --untracked-files=all)'"
} > "$E/supplementary/post-checks.txt" 2>&1
grep -qx "expectation/registry check rc=0" "$E/supplementary/post-checks.txt" || echo "WARNING: expectation files or registry changed (recorded)"

# F-3 procedure, references and the console transcript (never overwritten)
[ ! -e "$E/procedure" ] || stop "$E/procedure exists"
mkdir "$E/procedure" && cp -p "$Z/vars.env" "$Z/refs/"* "$E/procedure/" && cp -rp "$Z/scripts" "$E/procedure/scripts" || stop "procedure copy"
[ -f "$Z/console.log" ] || stop "console transcript $Z/console.log missing"
[ ! -e "$E/console.log" ] || stop "$E/console.log exists"
cp -p "$Z/console.log" "$E/console.log" || stop "console copy"

# F-4 preconditions
[ -z "$(find "$E" ! -type f ! -type d)" ] || stop "E holds something other than regular files and directories"

# F-5 the inventory: every file except the two top-level checksum records (nested SHA256SUMS included)
(cd "$E" && find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.final -print0 | LC_ALL=C sort -z | xargs -0 -r sha256sum) > "$E/SHA256SUMS" \
  || stop "inventory failed"

# F-6 completeness
want=$(cd "$E" && find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.final | wc -l)
[ "$(wc -l < "$E/SHA256SUMS")" -eq "$want" ] || stop "inventory count differs from the file count"
need() { grep -q "  \./$1\$" "$E/SHA256SUMS" || stop "inventory lacks ./$1"; }
need console.log; need procedure/vars.env; need supplementary/post-checks.txt
[ -d "$E/gate" ] && need environment/identity.txt && need environment/equivalence-ref.txt && need environment/dr13-ref.txt
[ -f "$E/gate/gate-b.txt" ] && need gate/gate-b.txt
[ -d "$E/release" ] && need release/selected.sha256 && need release/verify-after.txt
[ -d "$E/x2a" ] && need x2a/method.txt
[ -f "$E/gate/stage4-mount.done" ] && need x2a/mount.txt
for d in fx-before fx-after; do [ -f "$E/vv1/$d/SHA256SUMS" ] && need "vv1/$d/SHA256SUMS"; done
true

# F-7 verification, top level and nested
(cd "$E" && sha256sum -c --strict --quiet SHA256SUMS) || stop "inventory does not verify"
for d in fx-before fx-after; do
  [ -f "$E/vv1/$d/SHA256SUMS" ] && { (cd "$E/vv1/$d" && sha256sum -c --strict --quiet SHA256SUMS) || stop "nested $d/SHA256SUMS does not verify"; }
done

# F-8 the final checksum record, covering SHA256SUMS (which covers every other file)
(cd "$E" && sha256sum SHA256SUMS) > "$E/SHA256SUMS.final" || stop "final record"
# F-9 seal locally
chmod -R a-w "$E" || stop "chmod"
echo "F-10: record now, outside \$E: $(cat "$E/SHA256SUMS.final")"
exit 0
