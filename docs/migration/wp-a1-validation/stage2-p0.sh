#!/usr/bin/env bash
# WP-A1 validation, Stage 2 (runbook revision 3): P-0 (design 8.1, corrected by C-1) and gate B.
# Runs in a network-less container in which the genuine evidence is NOT mounted (checked). Only exit 0 is GO.
STAGE=stage2-p0
. "$(dirname "$0")/common.sh"
load_vars
no_evidence_visible

test "$(git -C "$W" rev-parse HEAD)" = "$C" && echo "P-0 commit OK" || stop "worktree HEAD is not C"              # B-2
test -z "$(git -C "$W" status --porcelain --untracked-files=all)" || stop "worktree not clean"
test "$(git -C "$SIMU5G_ROOT" rev-parse HEAD)" = "$SIMU5G_HEAD" && echo "P-0 Simu5G OK" || stop "Simu5G HEAD"
test -z "$(git -C "$SIMU5G_ROOT" status --porcelain --untracked-files=all)" || stop "Simu5G tree not clean"
(cd "$CHK" && sha256sum -c --strict --quiet) <<'EOF' || stop "expectation files or registry differ from the runbook"   # B-3
b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b  expect/vn1.expect.json
5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3  expect/vn2.expect.json
fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d  expect/vv1.expect.json
2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae  m2s72_fgo_registry.json
EOF
# gate A: the signed statements A (A-1, A-2, A-3, A-6), A-4 and A-5, with the approved DR-13 and G0-RO records
gate_a; gate_a45
[ "${IMG_DIGEST:-}" = "$(aval a5-g0ro.txt image_digest)" ] \
  || stop "this container's image digest (IMG_DIGEST, from the host) is not the one the G0-RO record covers"
test ! -e "$E" && mkdir "$E" && echo "P-0 fresh evidence dir" || stop "E exists or cannot be created"           # B-6
mkdir "$E/p0" "$E/environment" "$E/gate" || stop "cannot create E subdirectories"

{ python3 -c 'import sys; print("python", sys.version.replace("\n", " ")); print("executable", sys.executable)'      # B-1
  echo "python binary sha256 $(sha256sum "$(readlink -f "$(command -v python3)")" | cut -d' ' -f1)"
  echo "container image digest sha256:$IMG_DIGEST"
  echo "uname $(uname -srm)"; cat /etc/os-release
  if command -v cc >/dev/null; then cc --version | head -1; else echo "cc not installed"; fi
  if command -v opp_run >/dev/null; then opp_run -v 2>&1 | head -3; else echo "OMNeT++ not installed (not used by these evaluations)"; fi
  echo "INET not installed (not used by these evaluations)"
  echo "simu5g HEAD $(git -C "$SIMU5G_ROOT" rev-parse HEAD) tag $(git -C "$SIMU5G_ROOT" describe --tags --exact-match 2>/dev/null)"
  git --version; sha256sum --version | head -1
  echo "nascTime commit $C"; (cd "$CHK" && sha256sum expect/vn1.expect.json expect/vn2.expect.json expect/vv1.expect.json m2s72_fgo_registry.json)
} > "$E/environment/identity.txt" 2>&1 || stop "identity record"
cp -rp "$APPROVALS" "$E/environment/approvals" && cp -rp "$Z/records" "$E/environment/records" || stop "approval copies"
ssh-keygen -lf <(cut -d' ' -f2- "$APPROVALS/allowed_signers") > "$E/environment/approver-key-fingerprint.txt" 2>&1 || stop "key fingerprint"

suite() {   # <suite> <expected final line> <isolated|plain>: real exit code, non-empty output, exact final line   # B-5
  local t=$1 exp=$2 mode=$3 out="$E/p0/$1.out" err="$E/p0/$1.err" rc last
  if [ "$mode" = isolated ]; then (cd "$Z" && $PY "$CHK/$t") >"$out" 2>"$err"; rc=$?
  else (cd "$CHK" && python3 -B "$t") >"$out" 2>"$err"; rc=$?; fi
  echo "$rc" > "$E/p0/$t.rc"
  [ "$rc" -eq 0 ] || stop "$t exit code $rc"
  [ -s "$out" ] || stop "$t produced no output (missing result)"
  last=$(tail -n 1 "$out")
  [ "$last" = "$exp" ] || stop "$t final line '$last' is not '$exp'"
  echo "P-0 PASS $t rc=0 '$last'"
}
suite test_m2s72_e0vn21.py      "WP-A1 e0vn21 tests: 52 / 52 PASS, 0 FAIL" isolated
suite test_m2s72_a2.py          "A-2 tests: 18 / 18 PASS" plain
suite test_m2s72_a2probe.py     "A-2 probe tests: 11 / 11 PASS" plain
suite test_m2s72_a2v1.py        "10 / 10 PASS" plain
suite test_m2s72_gen.py         "generator negative tests: 67 PASS, 0 FAIL" plain
suite test_m2s72s5.py           "S5-1 tests: 38 / 38 PASS" plain
suite test_m2s72s5_2.py         "S5-2 tests: 28 / 28 PASS" plain
suite test_m2s72s5_n2.py        "S5 N = 2 tests: 19 / 19 PASS" plain
suite test_m2s72s5_smoke.py     "S5 smoke contract tests: 9 / 9 PASS" plain
suite test_m2s72_a21.py         "A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL" plain
suite test_m2s72_a21_fixture.py "A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL" plain
test "$(ls "$E"/p0/*.rc | wc -l)" -eq 11 || stop "not exactly 11 suite results"
test -z "$(git -C "$W" status --porcelain --untracked-files=all)" || stop "the suites modified the worktree"
test -z "$(git -C "$SIMU5G_ROOT" status --porcelain --untracked-files=all)" || stop "the suites modified Simu5G"

echo "GATE B: GO (B-1 ... B-6 met)" | tee "$E/gate/gate-b.txt"
exit 0
