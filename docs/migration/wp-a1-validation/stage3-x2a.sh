#!/usr/bin/env bash
# WP-A1 validation, Stage 3 (runbook revision 3): X-2a integrity of the extraction by DR-13 method (b), in-memory prefix
# mapping, with no manifest written. Runs in a network-less container with X read-only and WITHOUT the mount at R
# (checked), so nothing here can resolve a path through method (a).
STAGE=stage3-x2a
. "$(dirname "$0")/common.sh"
load_vars
gate_b_go
[ -f "$Z/release-record/h3.done" ] && grep -q "(validation)" "$Z/release-record/h3.done" || stop "H-3 (validation) has not completed"
[ ! -e "$R" ] || stop "$R is visible: Stage 3 (method b) must run without the read-only mount"
ro_path "$X"
[ ! -e "$E/x2a" ] || stop "$E/x2a exists (single attempt)"
mkdir "$E/x2a" || stop "cannot create $E/x2a"
[ ! -e "$E/release" ] && cp -rp "$Z/release-record" "$E/release" || stop "release record copy into E"
O="$E/x2a"
echo "DR-13 method (b): in-memory prefix mapping $R -> $X, integrity verification only; no manifest written" > "$O/method.txt"

MANIFESTS=(s5-smoke-1/m2/M2-S7.2a-s5smoke/records/M2S72-E0v-q0-f1.manifest.sha256
           s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256
           a2-nack-1/records/M2S72-E0vN-q0-one0-n2-f1_A2V1.manifest.sha256)
map() { awk -v a="  $R/" -v b="  $X/" '{ i = index($0, a); print substr($0, 1, i - 1) b substr($0, i + length(a)) }' "$1"; }

for m in "${MANIFESTS[@]}"; do
  f="$X/$m"; tag=$(basename "$m" .manifest.sha256)
  [ -f "$f" ] && [ ! -L "$f" ] || stop "manifest $m missing in the extraction"
  # every line: '<sha256>  <size>  /mnt/nasctime-results/<relative path without ..>'
  awk -v p="$R/" 'BEGIN { bad = 0 }
       { if ($0 !~ /^[0-9a-f]{64}  [0-9]+  \//) bad++; i = index($0, "  " p); if (i == 0) bad++;
         if ($0 ~ /\/\.\.(\/|$)/) bad++ } END { exit bad > 0 }' "$f" || stop "$m: a line is malformed or outside $R/"
  n=$(wc -l < "$f"); [ "$n" -gt 0 ] || stop "$m is empty"
  echo "$m entries $n sha256 $(sha256sum "$f" | cut -d' ' -f1)" >> "$O/manifests.txt"
  # strict presence: each entry exists at its exact original name as a regular file of the recorded size.
  # (The accepted verify-manifest also accepts a '.gz' copy; Run72 and the extractor do not, so that is refused here.)
  map "$f" | while IFS= read -r line; do
    sz=${line#*  }; sz=${sz%%  *}; p=${line#*  *  }
    [ -f "$p" ] && [ ! -L "$p" ] || { echo "missing at its exact name: $p"; exit 1; }
    [ "$(stat -c %s "$p")" = "$sz" ] || { echo "size differs: $p"; exit 1; }
  done > "$O/$tag.presence.txt" 2>&1 || stop "$m: strict presence failed (see $O/$tag.presence.txt)"
  # hash and size of every entry, by the accepted tool on the mapped stream (process substitution; nothing written)
  $PY "$CHK/m2s72s5_lib.py" verify-manifest <(map "$f") > "$O/$tag.verify.txt" 2>&1 \
    || stop "$m: verify-manifest failed (see $O/$tag.verify.txt)"
  grep -qx "manifest verified" "$O/$tag.verify.txt" || stop "$m: verify-manifest did not report 'manifest verified'"
done

# public pins of the A2-V1 run (committed in simulations/m2/check/fixtures/a2v1-first-chain.meta.json at C)
V=a2-nack-1; VC=M2S72-E0vN-q0-one0-n2-f1_A2V1
(cd "$X" && sha256sum -c --strict) > "$O/a2v1-public-pins.txt" 2>&1 <<EOF || stop "A2-V1 files differ from the public pins"
3e7a78f5cb7dad49c9ea81aa42407d5bf286f1a956977c03951fb053711e3f41  $V/records/$VC.manifest.sha256
84320fb577cdb780cee1e8f8242d383120156a3b8ce78d65575b0c3cc3c33873  $V/runs/run-$VC.log.gz
3bdcc9fc5114f9d46bc4466de3362831ba7e785ddb24a6c610404be7e9327db1  $V/runs/$VC/$VC/0.sca
EOF

# the A2-V1 seal: identity, every entry, and exactly the sealed files under a2-nack-1/{p0,records,eval} (as E-2)
[ "$(sha256sum "$X/a2-nack-1-evidence.sha256" | cut -d' ' -f1)" = 3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0 ] \
  || stop "A2-V1 seal identity"
(cd "$X" && sha256sum -c --strict a2-nack-1-evidence.sha256) > "$O/a2v1-seal.txt" 2>&1 || stop "A2-V1 seal entries do not verify"
diff <(sed 's/^[0-9a-f]\{64\}  //' "$X/a2-nack-1-evidence.sha256" | LC_ALL=C sort) \
     <(cd "$X" && find a2-nack-1/p0 a2-nack-1/records a2-nack-1/eval -type f 2>/dev/null | LC_ALL=C sort) > "$O/a2v1-seal-set.txt" \
  || stop "files under a2-nack-1/{p0,records,eval} are not exactly the sealed ones (see $O/a2v1-seal-set.txt)"
[ "$(wc -l < "$X/a2-nack-1-evidence.sha256")" -eq 33 ] || stop "the A2-V1 seal does not list 33 records"

# the smoke evidence seals, when archived (accepted procedures verify them; recorded either way)
for s in s5-smoke-1-evidence.sha256 s5-n2-1-evidence.sha256; do
  if [ -f "$X/$s" ]; then (cd "$X" && sha256sum -c --strict "$s") > "$O/$s.verify.txt" 2>&1 || stop "$s does not verify"
  else echo "$s not archived" > "$O/$s.verify.txt"; fi
done

# readiness of the files Run72 opens to derive the node ids (m2s72_runs.Run72.__init__ at C): the log, the .sca with
# one nrMac macNodeId per UE, the PCAP directory and the two NW-TT CSV logs. No evaluator is run here.
ready() {  # <runs dir relative to X> <cfg> <number of UEs>
  local b="$X/$1/$2" k
  [ -f "$X/$1/run-$2.log.gz" ] || stop "$2: run log missing"
  [ -f "$b/$2/0.sca" ] || stop "$2: 0.sca missing"
  [ "$(grep -c -E "^par M2S72Bridge\.ue\[[0-9]+\]\.cellularNic\.nrMac macNodeId " "$b/$2/0.sca")" -eq "$3" ] || stop "$2: not $3 macNodeId records"
  for f in "listener.pcapRecorder[0]" "nwTt.pcapRecorder[0]" "nwTt.pcapRecorder[1]" "upf.pcapRecorder[1]"; do
    [ -f "$b/pcap/$2-0/M2S72Bridge.$f.pcapng" ] || stop "$2: PCAP $f missing"; done
  for ((k = 0; k < $3; k++)); do for f in "dsTt[$k]" "talker[$k]" "ue[$k]"; do
    [ -f "$b/pcap/$2-0/M2S72Bridge.$f.pcapRecorder[0].pcapng" ] || stop "$2: PCAP $f missing"; done; done
  for f in syncIn.sync.csv engine.pdelay.csv; do
    [ -f "$b/m2log/$2-0/M2S72Bridge.nwTt.eth[1].trafficConditionerLayer.$f" ] || stop "$2: NW-TT $f missing"; done
  echo "$2: Run72 inputs present ($3 UE)" >> "$O/run72-readiness.txt"
}
ready s5-smoke-1/m2/M2-S7.2a-s5smoke/runs M2S72-E0v-q0-f1 1
ready s5-n2-1/m2/M2-S7.2a-s5smoke-n2/runs M2S72-E0vN-q0-one0-n2-f1 2
ready a2-nack-1/runs M2S72-E0vN-q0-one0-n2-f1_A2V1 2

done_mark stage3-x2a
echo "Stage 3: X-2a PASS (method b)"
exit 0
