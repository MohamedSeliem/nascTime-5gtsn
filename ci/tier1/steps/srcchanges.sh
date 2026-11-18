#!/usr/bin/env bash
# C-3 after the build: classification of build-induced changes in the three trees; nascTime tracked files unchanged.
. "$(dirname "$0")/../lib/common.sh"
"$T1_LIB/guard-alive.sh" "srcchanges"
/usr/bin/python3 -I "$PY/srcchanges.py"
