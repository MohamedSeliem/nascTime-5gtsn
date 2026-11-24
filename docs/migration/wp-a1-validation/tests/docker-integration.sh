#!/usr/bin/env bash
# WP-A1 Docker integration test of the complete host / container stage sequence (runbook rev. 4, section 14).
# TEST ONLY: dummy archives with the real layout, a throwaway signing key, dummy DR-13 / G0-RO records. NEVER genuine
# archives. Every container runs through host-stage.sh (network-less, pinned image, per-stage mounts, script -e).
# usage: docker-integration.sh <procedure commit D: holds docs/migration/wp-a1-validation>
# Environment: NASCTIME_SRC (full clone; used in place of GitHub), SIMU5G_SRC (clone with tag v1.8.1, used in place of
# GitHub), IMG (<image>@sha256:<digest>, present locally), TMPDIR (work area).
# Expected outcomes on dummy data are asserted, including the stops dummy data must cause (real hashes cannot match).
set -u -o pipefail
[ $# -eq 1 ] || { echo "usage: docker-integration.sh <D>"; exit 2; }
D=$1
: "${NASCTIME_SRC:?}"; : "${SIMU5G_SRC:?}"; : "${IMG:?}"
C_REV=f3f68be696777e42b0717f949625855ddb475435
. "$(dirname "$0")/lib.sh"
B=$(mktemp -d "${TMPDIR:-/tmp}/wpa1-docker.XXXXXX"); echo "work area $B"
DIG=${IMG##*@sha256:}
expect_rc() { local want=$1 name=$2; shift 2; "$@" > "$B/last.out" 2>&1; local rc=$?
  if [ "$rc" = "$want" ]; then ok "$name (exit $rc)"; else bad "$name: exit $rc, expected $want"; tail -n 5 "$B/last.out" | sed 's/^/      /'; fi; }

# ---- dummy archives (TEST ONLY) with the real relative layout and absolute-prefix manifests --------------------------
mkdir -p "$B/build" "$B/rel"
(cd "$B/build" && python3 -I - <<'EOF'
import os, hashlib, gzip
RR = "/mnt/nasctime-results"
def w(rel, d):
    p = os.path.join("t", rel); os.makedirs(os.path.dirname(p), exist_ok=True); open(p, "wb").write(d); return rel
def run(runs, cfg, n):
    fs = [w(f"{runs}/run-{cfg}.log.gz", gzip.compress(b"TEST ONLY dummy log\n", mtime=0))]; b = f"{runs}/{cfg}"
    fs.append(w(f"{b}/{cfg}/0.sca", "".join(f"par M2S72Bridge.ue[{k}].cellularNic.nrMac macNodeId {2049 + k}\n" for k in range(n)).encode()))
    for f in ["listener.pcapRecorder[0]", "nwTt.pcapRecorder[0]", "nwTt.pcapRecorder[1]", "upf.pcapRecorder[0]", "upf.pcapRecorder[1]"] + \
             [f"{x}[{k}].pcapRecorder[0]" for k in range(n) for x in ("dsTt", "talker", "ue")]:
        fs.append(w(f"{b}/pcap/{cfg}-0/M2S72Bridge.{f}.pcapng", b"TEST ONLY"))
    for f in ("syncIn.sync.csv", "engine.pdelay.csv"):
        fs.append(w(f"{b}/m2log/{cfg}-0/M2S72Bridge.nwTt.eth[1].trafficConditionerLayer.{f}", b"t,v\n"))
    return fs
def man(rel, fs):
    w(rel, "".join(f"{hashlib.sha256(open('t/' + f, 'rb').read()).hexdigest()}  {os.path.getsize('t/' + f)}  {RR}/{f}\n" for f in sorted(fs)).encode())
man("s5-smoke-1/m2/M2-S7.2a-s5smoke/records/M2S72-E0v-q0-f1.manifest.sha256", run("s5-smoke-1/m2/M2-S7.2a-s5smoke/runs", "M2S72-E0v-q0-f1", 1))
man("s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256", run("s5-n2-1/m2/M2-S7.2a-s5smoke-n2/runs", "M2S72-E0vN-q0-one0-n2-f1", 2))
V = "M2S72-E0vN-q0-one0-n2-f1_A2V1"; man(f"a2-nack-1/records/{V}.manifest.sha256", run("a2-nack-1/runs", V, 2))
sealed = [f"a2-nack-1/records/{V}.manifest.sha256"] + [w(f"a2-nack-1/{d}/r{i}.txt", b"TEST ONLY %d" % i)
          for i, d in zip(range(32), ["p0"] * 4 + ["records"] * 20 + ["eval"] * 8)]
w("a2-nack-1-evidence.sha256", "".join(f"{hashlib.sha256(open('t/' + f, 'rb').read()).hexdigest()}  {f}\n" for f in sorted(sealed)).encode())
EOF
) || { echo "dummy build failed"; exit 2; }
(cd "$B/build/t" && tar -czf "$B/rel/n1-smoke.tar.gz" s5-smoke-1 && tar -czf "$B/rel/n2-smoke.tar.gz" s5-n2-1 \
  && tar -czf "$B/rel/a2v1.tar.gz" a2-nack-1 a2-nack-1-evidence.sha256) && (cd "$B/rel" && sha256sum *.tar.gz > SHA256SUMS)
RS=$(sha256sum "$B/rel/SHA256SUMS" | cut -d' ' -f1)
test_key "$B/key"                                                   # TEST ONLY stand-in for the maintainer's key

session() {  # session <name>: a fresh Z / X with the clone, vars.env and the signed gate-A statement; then H-1
  local z="$B/$1/z"; mkdir -p "$z/approvals" "$z/records"
  git clone -q "$NASCTIME_SRC" "$z/nasctime-src"
  sed -e "s#<absolute extraction root[^>]*>#$B/$1/x#" -e "s#<absolute directory holding[^>]*>#$B/rel#" \
      <(git -C "$z/nasctime-src" show "$D:docs/migration/wp-a1-validation/vars.env.template") > "$z/vars.env"
  cp "$B/key/allowed_signers" "$z/approvals/"
  gate_a_statement "$z/approvals/gate-a.txt" "$D" "$RS" n1-smoke.tar.gz n2-smoke.tar.gz a2v1.tar.gz; sign "$B/key/test-key" "$z/approvals/gate-a.txt"
  git -C "$z/nasctime-src" show "$D:docs/migration/wp-a1-validation/h1-setup.sh" > "$z/h1-setup.sh"
  echo "$z"
}
hs() { Z="$1" bash "$1/scripts/host-stage.sh" "${@:2}"; }

# ======== session Q (qualification) ===================================================================================
ZQ=$(session q)
expect_rc 0 "Q H-1 set-up (gate A signed; scripts from D)" env Z="$ZQ" SIMU5G_URL="$SIMU5G_SRC" bash "$ZQ/h1-setup.sh" "$D"
expect_rc 0 "Q H-3 qualification: release verified, dummy archives extracted" hs "$ZQ" h3-release.sh release "$ZQ/console.log" qualification
check "Q H-3 extraction recorded (files counted, archives re-verified)" 'grep -q "^X files 78$" "$ZQ/release-record/summary.txt" && [ -s "$ZQ/release-record/verify-after.txt" ]'
expect_rc 0 "Q DR-13-V method (b) (mapped profile; no mount at R)" hs "$ZQ" dr13-validate.sh mapped "$ZQ/console.log" b
check "Q DR-13-V (b): DV-b1, b2, b3 and X unchanged" '[ "$(grep -c "^PASS DV-b" "$ZQ/dr13-validation/mode-b/results.txt")" = 4 ]'
expect_rc 1 "Q DR-13-V method (a): stops at DV-a3 (dummy seal cannot match) after DV-a1 / a2 PASS" hs "$ZQ" dr13-validate.sh mounted "$ZQ/console.log" a
check "Q DR-13-V (a): DV-a1 and DV-a2 passed in the container" '[ "$(grep -c "^PASS DV-a[12]" "$ZQ/dr13-validation/mode-a/results.txt")" = 2 ]'
expect_rc 1 "Q G0-RO: NOT EQUIVALENT on dummy data (as it must be)" hs "$ZQ" g0ro-run.sh mounted "$ZQ/console.log"
check "Q G0-RO: all 11 suites passed inside the pinned image (G0RO-P)" '[ "$(grep -c "^G0RO-P PASS" "$ZQ/g0ro/runs.txt")" = 11 ]'
check "Q G0-RO: the comparison ran and recorded its coverage" 'grep -q "^Not compared (coverage record):" "$ZQ/g0ro/compare.txt"'
check "Q transcript records the exit code of each of the 4 host-stage calls" '[ "$(grep -c "^host-stage: .* exit [0-9]*$" "$ZQ/console.log")" = 4 ]'

# ======== session V (validation), with TEST ONLY approved records ====================================================
ZV=$(session v)
echo "TEST ONLY DR-13 record" > "$ZV/records/dr13-validation-record.md"; echo "TEST ONLY G0-RO record" > "$ZV/records/g0ro-record.md"
subject_statement "$ZV/approvals/a4-dr13.txt" A-4 "$D" dr13-validation-record.md "$ZV/records"; sign "$B/key/test-key" "$ZV/approvals/a4-dr13.txt"
subject_statement "$ZV/approvals/a5-g0ro.txt" A-5 "$D" g0ro-record.md "$ZV/records" "$DIG"; sign "$B/key/test-key" "$ZV/approvals/a5-g0ro.txt"
expect_rc 0 "V H-1 set-up" env Z="$ZV" SIMU5G_URL="$SIMU5G_SRC" bash "$ZV/h1-setup.sh" "$D"
expect_rc 1 "V H-3 validation before gate B is refused" hs "$ZV" h3-release.sh release "$ZV/console.log" validation
check "V nothing extracted before gate B" '[ ! -e "$B/v/x" ]'
cp "$ZV/approvals/a5-g0ro.txt" "$B/a5.bak"; echo "note=added" >> "$ZV/approvals/a5-g0ro.txt"
expect_rc 1 "V Stage 2 NO-GO on an altered A-5 statement" hs "$ZV" stage2-p0.sh p0 "$ZV/console.log"
check "V no evidence directory after the gate-A refusal" '[ ! -e "$ZV/evidence-wpa1" ]'
cp "$B/a5.bak" "$ZV/approvals/a5-g0ro.txt"
expect_rc 0 "V Stage 2 P-0: GO in the pinned image (11 suites, signed gates, image digest)" hs "$ZV" stage2-p0.sh p0 "$ZV/console.log"
expect_rc 0 "V H-3 validation after gate B" hs "$ZV" h3-release.sh release "$ZV/console.log" validation
expect_rc 1 "V Stage 3: stops at the A2-V1 public pins (dummy data)" hs "$ZV" stage3-x2a.sh mapped "$ZV/console.log"
check "V Stage 3: manifests verified by mapping before the stop" '[ "$(grep -lx "manifest verified" "$ZV"/evidence-wpa1/x2a/*.verify.txt | wc -l)" = 3 ]'
# TEST ONLY: to drive Stages 4 - 6 on dummy data, a copy of Stage 3 without the two real-hash comparisons replaces it in
# this session's script directory (never in the repository); its first attempt's outputs are removed.
python3 -I - "$ZV/scripts/stage3-x2a.sh" <<'EOF'
import re, sys; p = sys.argv[1]; s = open(p).read()
a = s.index("# public pins of the A2-V1 run"); b = s.index("# the A2-V1 seal:")
s = s[:a] + "# TEST ONLY (docker-integration.sh): public-pin block removed for dummy data\n" + s[b:]
s = re.sub(r'\[ "\$\(sha256sum "\$X/a2-nack-1-evidence.sha256".*?\|\| stop "A2-V1 seal identity"\n', "# TEST ONLY: seal identity removed\n", s, flags=re.S)
open(p, "w").write(s)
EOF
rm -rf "$ZV/evidence-wpa1/x2a" "$ZV/evidence-wpa1/release"
expect_rc 0 "V Stage 3 (TEST-ONLY copy): seal set, smoke seals, Run72 readiness" hs "$ZV" stage3-x2a.sh mapped "$ZV/console.log"
expect_rc 0 "V Stage 4: read-only mount at /mnt/nasctime-results equals X" hs "$ZV" stage4-mount.sh mounted "$ZV/console.log"
expect_rc 1 "V Stage 5: V-N1 / V-N2 findings (exit 5), V-V1 stops at P-1 (dummy seal)" hs "$ZV" stage5-validate.sh mounted "$ZV/console.log"
check "V Stage 5: hrq ran in the container, mismatch recorded as findings, P-3 identical" \
  'grep -q "^V-N1 hrq rc=5$" "$ZV/evidence-wpa1/stage5-summary.txt" && grep -q "^V-N2 P-3 identical$" "$ZV/evidence-wpa1/stage5-summary.txt" && [ -f "$ZV/evidence-wpa1/vn1/findings.md" ]'
check "V Stage 5: V-V1 not evaluated after the P-1 stop" '[ ! -e "$ZV/evidence-wpa1/vv1/hrq" ]'
expect_rc 5 "V Stage 6: finalised; integrity PASS; not acceptance-eligible" hs "$ZV" stage6-finalise.sh final "$ZV/finalisation.log"
check "V Stage 6: final record and inventory verify" '(cd "$ZV/evidence-wpa1" && sha256sum -c --strict --quiet SHA256SUMS.final && sha256sum -c --strict --quiet SHA256SUMS)'
check "V Stage 6: approvals, records and the TEST-ONLY script copy preserved in the evidence" \
  '[ -f "$ZV/evidence-wpa1/environment/approvals/a5-g0ro.txt.sig" ] && grep -q "TEST ONLY (docker-integration.sh)" "$ZV/evidence-wpa1/procedure/scripts/stage3-x2a.sh"'

# ======== the procedure tests inside the pinned image ===============================================================
expect_rc 0 "run-all.sh inside the pinned image (network-less)" docker run --rm --network none -e HOME=/tmp -e TMPDIR=/tmp \
  -e NASCTIME_SRC=/src/nasctime -e SIMU5G_SRC=/src/simu5g \
  --mount "type=bind,source=$NASCTIME_SRC,target=/src/nasctime,readonly" --mount "type=bind,source=$SIMU5G_SRC,target=/src/simu5g,readonly" \
  --mount "type=bind,source=$ZQ/scripts,target=/t,readonly" "$IMG" bash /t/tests/run-all.sh
summary docker-integration
