#!/usr/bin/env bash
# g0ro_compare.py on synthetic outputs shaped like the tools' JSON (runbook rev. 4, 7 and 14). TEST ONLY.
set -u -o pipefail
T_DIR=$(cd "$(dirname "$0")" && pwd); GC="$T_DIR/../g0ro_compare.py"
PASSED=0; FAILED=0
check() { if eval "$2"; then echo "PASS  $1"; PASSED=$((PASSED + 1)); else echo "FAIL  $1  [$2]"; FAILED=$((FAILED + 1)); fi; }
mk() { rm -rf "$1"; python3 -I - "$1" <<'EOF'
import json, os, sys
g = sys.argv[1]; V = "M2S72-E0vN-q0-one0-n2-f1_A2V1"
rows = [[r, "run", "NOT EVALUATED" if r == "A2-4c" else "PASS", ""] for r in
        ["A2-0","A2-0s","A2-1","A2-2","A2-3","A2-4a","A2-4b","A2-4c","A2-5","A2-6","A2-7","A2-8","A2-9"]]
per = {"2049": dict(inserts=11702, transmissions=11702, feedback=11697, ack=11697, nack=0, discarded=0, lines_by_class={}),
       "2050": dict(inserts=1265, transmissions=1409, feedback=1408, ack=1264, nack=144, discarded=0, lines_by_class={})}
for sub, c, v, rc in (("s1-full", "full", "A-2.1 INCOMPLETE", 4), ("s1-f1di", "f1d-i", "A-2.1 VALID", 0)):
    os.makedirs(f"{g}/{sub}")
    json.dump({"contract": c, "verdict": v, "rows": rows, "per_ue": per, "window_ps": [2000000000000, 12001000000000],
               "handles": {str(i): {"lc": 1, "st": "retired"} for i in range(129)}, "unresolved": [],
               "end_states": {"censored: awaiting feedback": 6}}, open(f"{g}/{sub}/a21-{V}.json", "w"))
    open(f"{g}/{sub}.rc", "w").write(f"{rc}\n")
os.makedirs(f"{g}/s1-controls"); json.dump({"controls": [{"status": "AS DECLARED"}] * 22}, open(f"{g}/s1-controls/a21-controls-{V}.json", "w"))
open(f"{g}/s1-controls.rc", "w").write("0\n")
for sub, cfg, a1, x6, d in (("xa-n1", "M2S72-E0v-q0-f1", dict(a1a=11697, a1b=0, ambiguous=0, orphan=0, reinsert=0), "PASS", 1000000000),
                            ("xa-n2", "M2S72-E0vN-q0-one0-n2-f1", dict(a1a=9718, a1b=2476, ambiguous=768, orphan=0, reinsert=768), "NOT EVALUATED", 7)):
    os.makedirs(f"{g}/{sub}")
    r = [[f"XA-{x}", "run", "PASS", ""] for x in ("pre", "0", "1", "2", "3", "4", "5")] + [["XA-6", "run", x6, ""]]
    json.dump({"rows": r, "report": {"a1_summary": a1, "delta_ps": d, "nack_ue_sent": 0, "retransmitted_pdus": 0}}, open(f"{g}/{sub}/xa-{cfg}.json", "w"))
    open(f"{g}/{sub}.rc", "w").write("0\n")
EOF
}
B=$(mktemp -d "${TMPDIR:-/tmp}/wpa1-g0.XXXXXX"); G=$B/g
run() { python3 -I -B "$GC" "$G" > "$B/out.txt" 2>&1; echo $?; }
mk "$G"; check "GC-1 all recorded values met: EQUIVALENT, exit 0" '[ "$(run)" = 0 ] && grep -q "; EQUIVALENT$" "$B/out.txt"'
check "GC-2 the coverage record (not-compared fields) is printed" 'grep -q "^Not compared (coverage record):" "$B/out.txt" && grep -q "lines_by_class" "$B/out.txt"'
check "GC-3 every item carries its source class" '! grep -E "^(PASS|FAIL|INFO-PASS|INFO-FAIL) " "$B/out.txt" | grep -vqE "^[A-Z-]+ +\| [RDP] \|"'
mk "$G"; sed -i 's/"nack": 144/"nack": 143/' "$G"/s1-f1di/a21-*.json
check "GC-4 one recorded (R) count differs: NOT EQUIVALENT, exit 1" '[ "$(run)" = 1 ] && grep -q "^FAIL .* | R | s1-f1di node 2050 accounting" "$B/out.txt"'
mk "$G"; sed -i 's/"delta_ps": 1000000000/"delta_ps": 5/' "$G"/xa-n1/xa-*.json
check "GC-5 a declared-only (P) value differs: information, still EQUIVALENT" '[ "$(run)" = 0 ] && grep -q "^INFO-FAIL | P | xa-n1 delta" "$B/out.txt"'
mk "$G"; echo 1 > "$G/xa-n2.rc"
check "GC-6 a derived (D) exit code differs: NOT EQUIVALENT" '[ "$(run)" = 1 ]'
mk "$G"; sed -i 's/12001000000000/12002000000000/' "$G"/s1-full/a21-*.json
check "GC-7 the recorded window differs: NOT EQUIVALENT" '[ "$(run)" = 1 ]'
mk "$G"; rm "$G"/xa-n2/*.json
check "GC-8 a missing output: NOT EQUIVALENT" '[ "$(run)" = 1 ]'
rm -rf "$B"
echo "test-g0ro-compare: $PASSED PASS, $FAILED FAIL"; [ "$FAILED" -eq 0 ]
