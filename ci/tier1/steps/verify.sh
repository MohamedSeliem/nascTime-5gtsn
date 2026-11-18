#!/usr/bin/env bash
# In-session toolchain and configure.user identity probe (no build), lock gate, independent manifest verification of
# the installed trees, and recipe-consistency screening of the opp_env adaptations (C-1, C-2, C-3 before the build).
. "$(dirname "$0")/../lib/common.sh"
export STAGE_CAP_S=$CAP_BOOTSTRAP_S
oe_session probe run -w "$WS" $PROJECTS -c "bash $T1_DIR/session/toolchain-probe.sh $EV/probe.txt"
screened_cat "$EV/probe.txt"
"$T1_LIB/lockcheck.sh" after-probe "$EV/realise.log" "$EV/probe.log"
# Independent sha1sum -c of the opp_env postdownload manifests, and no files added after the download.
: > "$EV/postdownload-verify.txt"
rc=0
for p in omnetpp inet simu5g; do
  r=$(sed -n "s/^${p}_root: //p" "$EV/probe.txt")
  n=$(wc -l < "$r/.opp_env/postdownload.sha")
  if (cd "$r" && sha1sum -c --quiet --strict .opp_env/postdownload.sha) > "$UNPUB/verify-$p.txt" 2>&1; then
    { echo "$p postdownload_manifest_entries: $n"; echo "$p sha1sum_check: PASS"; } >> "$EV/postdownload-verify.txt"
  else
    echo "$p sha1sum_check: FAIL ($(grep -c -E ': (FAILED|FAILED open or read)$' "$UNPUB/verify-$p.txt") files)" >> "$EV/postdownload-verify.txt"
    rc=1
  fi
  extra=$(cd "$r" && comm -13 <(cut -d' ' -f3- .opp_env/postdownload.sha | sort -u) \
            <(find . \( -path ./.opp_env -o -path ./ide \) -prune -o -type f -print | sort -u) | wc -l)
  echo "$p files_added_after_download: $extra" >> "$EV/postdownload-verify.txt"
  (( extra == 0 )) || rc=1
  # The manifests themselves are not published (size); their hashes are.
  echo "$p prepatch_manifest_sha256: $(sha256sum "$r/.opp_env/prepatch.sha" | cut -c1-64)" >> "$EV/source-identity.txt"
  echo "$p postdownload_manifest_sha256: $(sha256sum "$r/.opp_env/postdownload.sha" | cut -c1-64)" >> "$EV/source-identity.txt"
done
# C4: no stable, pinned reference of the E2b.3-R1 manifests is available to this workflow, so source equivalence with
# that run (or with the VM) is NOT EVALUATED here; the manifest hashes above make later comparison possible.
echo "reference_manifest_comparison: NOT EVALUATED (no pinned reference manifest; equivalence is not inferred)" >> "$EV/source-identity.txt"
cat "$EV/postdownload-verify.txt"
/usr/bin/python3 -I "$PY/adapt.py"
exit "$rc"
