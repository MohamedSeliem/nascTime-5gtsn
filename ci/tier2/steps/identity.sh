#!/usr/bin/env bash
# E-1: authorised trigger and commit identity (push of the authorised branch, attempt 1, one new-files-only commit on the
# authorised baseline). Creates the fresh E3a work directory outside the repository.
. "$(dirname "$0")/../lib/t2common.sh"
[[ ! -e "$E3" ]] || { echo "::error::E3a work directory already exists"; exit 1; }
mkdir -p "$REC"
/usr/bin/python3 -I "$T2PY/identity.py" "$REPO" "$REC/identity.txt"
