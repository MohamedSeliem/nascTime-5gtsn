#!/usr/bin/env python3
"""M2-R181c diagnostic: C8-v detail on a base load run (M2S5-load vs M2S4-load, seed 0).
   diag_c8v_load.py <runs dir holding M2S5-load and M2S4-load>
Explains the 1.8.0 'base fails [C8]' of N-tseSlot-v (controls-on-1.8.0.txt). Read-only; uses check_v181c_m2s5.c8v."""
import os, sys
RUNS = sys.argv[1]
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../m2/check"))
sys.argv = [sys.argv[0], "c8demo", RUNS, RUNS]
import check_v181c_m2s5 as V  # noqa: E402
C = V.C
R, R4 = C.Run(RUNS, "M2S5-load", 0), C.Run(RUNS, "M2S4-load", 0)
for name, r4 in (("M2S5-load vs M2S4-load", R4), ("M2S5-load alone (no (e))", None)):
    ok, det = V.c8v(R, r4)
    print(f"{'PASS' if ok else 'FAIL'}  C8-v {name}\n      {det}")
eg, ing, eng, nweng = V.c8v_data(R)
rec = {r["frameId"] for r in eg if r["event"] == "recover"}
lost = [r for r in ing if r["frameId"] not in rec and "GptpPdelay" not in r["signature"]]
import collections, re
print("not recovered, non-Pdelay, by kind:", collections.Counter(re.sub(r".*data=\d+B: ", "", r["signature"])[:40] for r in lost).most_common(8))
print("Sync / Follow_Up delivered to slave:", len(C.sel(R.sl, 1, C.SYNC)) if hasattr(C, "SYNC") else "?", len(C.sel(R.sl, 1, C.FU)))
