#!/usr/bin/env bash
# Seal the raw simulation evidence BEFORE any evaluation: SHA-256 manifest of every file, tree made read-only.
. "$(dirname "$0")/../lib/t2common.sh"
/usr/bin/python3 -I "$T2PY/seal.py" create "$RAW" "$E3/raw-manifest.sha256" "$REC/seal.txt"
rc=$?
cat "$REC/seal.txt"
exit "$rc"
