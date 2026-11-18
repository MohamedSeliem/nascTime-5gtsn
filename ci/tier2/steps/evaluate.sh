#!/usr/bin/env bash
# Verify the seal (evaluation must not have changed the raw evidence), take the final repository snapshot, render the
# recorded argument vectors as text, and evaluate E-1 .. E-9 (separate tier-2 evaluator).
. "$(dirname "$0")/../lib/t2common.sh"
set +e
mkdir -p "$REC"
/usr/bin/python3 -I "$T2PY/seal.py" verify "$RAW" "$E3/raw-manifest.sha256" "$REC/seal-verify.txt"
cat "$REC/seal-verify.txt"
git -C "$REPO" status --porcelain=v1 --untracked-files=all --ignored=matching > "$REC/git-status-final.txt"
for f in "$REC"/*.nul; do
  [[ -f "$f" ]] && /usr/bin/python3 -I -c 'import sys
d = open(sys.argv[1], "rb").read().split(b"\0")[:-1]
open(sys.argv[2], "w").write("".join(repr(x.decode("utf-8", "replace")) + "\n" for x in d))' "$f" "${f%.nul}.txt"
done
/usr/bin/python3 -I "$T2PY/evaluate_t2.py"
exit 0
