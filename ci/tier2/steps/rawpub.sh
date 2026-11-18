#!/usr/bin/env bash
# Raw-evidence publication (separate artifact): sealed simulation outputs and text records, content-checked per type.
. "$(dirname "$0")/../lib/t2common.sh"
/usr/bin/python3 -I "$T2PY/seal.py" verify "$RAW" "$E3/raw-manifest.sha256" "$REC/seal-verify-publication.txt" \
  || { cat "$REC/seal-verify-publication.txt"; echo "::error::raw evidence changed after sealing"; exit 1; }
/usr/bin/python3 -I -B "$T2PY/rawpub.py" "$T2_EXPERIMENT" "$RAW" "$REC" "$E3" "$E3/publish-raw" "$T1_LIB/screen.py" \
  "$REPO/simulations/m2/check" "$RAW_PUBLICATION_LIMIT_B" "$REC/rawpub-check.txt"
