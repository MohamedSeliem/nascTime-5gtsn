#!/usr/bin/env bash
# Raw-evidence publication (separate artifact): sealed simulation outputs and text records, content-checked per type.
# The content-check report is also added to the screened diagnostics, so a refusal is diagnosable without the raw files.
. "$(dirname "$0")/../lib/t2common.sh"
/usr/bin/python3 -I "$T2PY/seal.py" verify "$RAW" "$E3/raw-manifest.sha256" "$REC/seal-verify-publication.txt" \
  || { cat "$REC/seal-verify-publication.txt"; echo "::error::raw evidence changed after sealing"; exit 1; }
rc=0
/usr/bin/python3 -I -B "$T2PY/rawpub.py" "$T2_EXPERIMENT" "$RAW" "$REC" "$E3" "$E3/publish-raw" "$T1_LIB/screen.py" \
  "$REPO/simulations/m2/check" "$RAW_PUBLICATION_LIMIT_B" "$REC/rawpub-check.txt" || rc=$?
# publication diagnostics (per-class N3 counts, address pairs, bounded examples) reach the screened diagnostic artifact
# whatever the outcome; withheld if the screen does not pass
if [[ -d "$CI/publish" && -f "$REC/rawpub-check.txt" ]]; then
  if /usr/bin/python3 -I "$T1_LIB/screen.py" "$REC/rawpub-check.txt" >/dev/null; then
    cp "$REC/rawpub-check.txt" "$CI/publish/$T2_EXPERIMENT-rawpub-check.txt"
  else
    echo "::warning::publication diagnostics withheld by screening"
  fi
fi
exit "$rc"
