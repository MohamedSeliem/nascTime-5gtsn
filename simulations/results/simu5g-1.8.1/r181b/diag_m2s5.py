#!/usr/bin/env python3
"""M2-R181b diagnostic (no verdict): M2-S5 on 1.8.1, C8 FAIL and the four control FAILs.

    diag_m2s5.py <M2-S5 dir (runs/)> <scratch root with 1.8.1/M2S4, 1.8.1/M2S5, 1.8.0/M2S4, 1.8.0/M2S5 seed-0 runs>

(1) the unchanged check_m2s5.rows_5gs() for M2S5, M2S5-nc-noFcsNw and M2S5-nc-tseSlot (seed 0), with M2S4 seed 0 of the
    scratch root as R4 (the M2-S4 runs of the campaign were deleted after m2s5, as planned);
(2) DS-TT eth[1] M2-S0 egress counters (scalars) and DS-TT eth[1] gPTP output by message type, Pdelay_Req arrival times;
(3) DS-TT Sync egress time TSe minus the Sync's slot time (sync log), per version.
"""
import collections
import csv
import glob
import os
import sys

S5, SC = sys.argv[1], sys.argv[2]
HERE = os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../m2/check")
sys.path.insert(0, HERE)
sys.argv = ["check_m2s5.py", S5, os.path.join(SC, "1.8.1"), "/dev/null"]
import check_m2s5 as C  # noqa: E402
import pcapng  # noqa: E402

R40 = C.Run(os.path.join(SC, "1.8.1"), "M2S4", 0)
print("(1) check_m2s5.rows_5gs, seed 0, R4 = M2S4 seed 0 (1.8.1)")
for cfg in ("M2S5", "M2S5-nc-noFcsNw", "M2S5-nc-tseSlot"):
    res = C.rows_5gs(C.Run(os.path.join(S5, "runs"), cfg, 0), R40)
    print(f"  {cfg}: failing {[k for k, v in res.items() if not k.startswith("_") and not v[0]]}")
    for k in ("C8", "S3"):
        print(f"      {k}: {res[k][1][:260]}")
print("(2) DS-TT eth[1]: M2-S0 egress counters; gPTP sent towards the slave by type; Pdelay_Req received")
for v in ("1.8.1", "1.8.0"):
    for c in ("M2S4", "M2S5"):
        sca = glob.glob(f"{SC}/{v}/{c}/**/*.sca", recursive=True)[0]
        cnt = {}
        for line in open(sca):
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar" and p[1].endswith("dsTt.eth[1].measurementLayer.egress") and p[2] in (
                    "framesRecovered", "framesInvalidTag", "framesUntaggedAtEgress", "framesStripped"):
                cnt[p[2]] = int(float(p[3]))
        d = glob.glob(f"{SC}/{v}/{c}/pcap/*-0")[0]
        out, req = collections.Counter(), []
        for p in pcapng.read(d + "/M1Bridge.dsTt.pcapRecorder[1].pcapng"):
            f = pcapng.ethernet(p["data"])
            if f["etherType"] == 0x88F7:
                mt = f["payload"][0] & 15
                if p["dir"] == 2:
                    out[mt] += 1
                if p["dir"] == 1 and mt == 2:
                    req.append(round(p["t_ps"] / 1e12, 6))
        print(f"  {v} {c}: {cnt}; out by type {dict(sorted(out.items()))} (3 = Pdelay_Resp, 10 = Resp_Follow_Up); Pdelay_Req at {req}")
print("(3) M2S5 DS-TT Sync egress TSe - Sync slot time (ps): value: count")
for v in ("1.8.1", "1.8.0"):
    f = glob.glob(f"{SC}/{v}/M2S5/m2log/M2S5-0/*dsTt.eth?1?.trafficConditionerLayer.syncOut.sync.csv")[0]
    rows = list(csv.DictReader(open(f)))
    slot = {r["seq"]: int(r["t"]) for r in rows if r["event"] == "syncSlot"}
    d = collections.Counter(int(float(r["TSe"])) - slot[r["seq"]] for r in rows if r["TSe"] and r["seq"] in slot)
    print(f"  {v}: {dict(sorted(d.items()))}")
