#!/usr/bin/env python3
"""M2-R181b diagnostic (no verdict): R2b attribution over all seeds.

    diag_r2b_all.py <runs root containing M2S4/, M2S4-ctl-nopdelay/, M2S4-load/, M2S4-ctl-nopdelay-load/>

For each (M2S4 seed r, control seed r): end-to-end application-frame latencies as in check_m2s4 R2b
(talker / listener PCAP, etherType != 0x88F7, key = etherType, PCP, VID, payload hash). For each differing frame:
- the talker-egress gap before it in M2S4 (start of this frame - end of the previous frame sent by the talker),
  and the type of that previous frame;
- the talker-egress send time in M2S4 and in the control.
Independently: every talker-egress application frame in M2S4 that starts within one IFG of the end of a talker
Pdelay_Req ("queued behind a Pdelay_Req"), and whether it is in the differing set.
Also: the talker's Pdelay_Req send times (first 5) per run, to show the scheduling phase.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../m2/check"))
import pcapng  # noqa: E402

ROOT = sys.argv[1]
PS_PER_BYTE = 8000  # 1 Gb/s
IFG_PS = 12 * PS_PER_BYTE


def frames(path):
    out, occ = [], Counter()
    for p in pcapng.read(path):
        f = pcapng.ethernet(p["data"])
        k = (f["etherType"], f["pcp"], f["vid"], pcapng.fnv1a64(f["payload"]))
        occ[(k, p["dir"])] += 1
        mt = (f["payload"][0] & 15) if f["etherType"] == 0x88F7 and f["payload"] else None
        L = len(p["data"])
        out.append({"end": p["t_ps"], "start": p["t_ps"] - (L + 8) * PS_PER_BYTE, "L": L, "dir": p["dir"],
                    "et": f["etherType"], "mt": mt, "key": k + (occ[(k, p["dir"])],)})
    return out


def lat(src, dst):
    tx = {f["key"]: f["end"] for f in src if f["dir"] == 2 and f["et"] != 0x88F7}
    return {f["key"]: f["end"] - tx[f["key"]] for f in dst if f["dir"] == 1 and f["et"] != 0x88F7 and f["key"] in tx}


tot_cmp = tot_diff = tot_behind = tot_behind_diff = 0
for cfg, ctl, reps in (("M2S4", "M2S4-ctl-nopdelay", range(10)), ("M2S4-load", "M2S4-ctl-nopdelay-load", [0])):
    for r in reps:
        pa = os.path.join(ROOT, cfg, "pcap", f"{cfg}-{r}")
        pc = os.path.join(ROOT, ctl, "pcap", f"{ctl}-{r}")
        if not os.path.isdir(pa) or not os.path.isdir(pc):
            print(f"{cfg}#{r}: runs missing")
            continue
        ta, la = frames(os.path.join(pa, "M1Bridge.talker.pcapRecorder[0].pcapng")), frames(os.path.join(pa, "M1Bridge.listener.pcapRecorder[0].pcapng"))
        tc, lc = frames(os.path.join(pc, "M1Bridge.talker.pcapRecorder[0].pcapng")), frames(os.path.join(pc, "M1Bridge.listener.pcapRecorder[0].pcapng"))
        res = {}
        for dirn, (sa, da, sc, dc) in (("UL", (ta, la, tc, lc)), ("DL", (la, ta, lc, tc))):
            A, C = lat(sa, da), lat(sc, dc)
            d = {k: A[k] - C[k] for k in A if k in C and A[k] != C[k]}
            res[dirn] = (len(A), d)
            tot_cmp += len(A)
            tot_diff += len(d)
        # UL: talker egress queueing behind its own Pdelay_Req
        tx = [f for f in ta if f["dir"] == 2]
        txc = {f["key"]: f for f in tc if f["dir"] == 2}
        behind = []
        for i in range(1, len(tx)):
            prev, f = tx[i - 1], tx[i]
            if f["et"] != 0x88F7 and prev["mt"] == 2 and f["start"] - prev["end"] <= IFG_PS:
                behind.append(f)
        dul = res["UL"][1]
        bd = sum(1 for f in behind if f["key"] in dul)
        tot_behind += len(behind)
        tot_behind_diff += bd
        pdreq = [f["start"] / 1e12 for f in tx if f["mt"] == 2][:3]
        print(f"{cfg}#{r}: UL {res['UL'][0]} compared, {len(dul)} differ {sorted(set(dul.values()))}; DL {res['DL'][0]} compared, "
              f"{len(res['DL'][1])} differ; talker app frames queued behind its Pdelay_Req: {len(behind)}, of which differing {bd}; "
              f"differing not behind a Pdelay_Req: {len([k for k in dul if k not in {f['key'] for f in behind}])}; "
              f"first Pdelay_Req starts {['%.9f' % x for x in pdreq]}")
        for f in behind:
            c = txc.get(f["key"])
            print(f"    behind Pdelay_Req: app frame end {f['end'] / 1e12:.9f} (ctl {c['end'] / 1e12 if c else float('nan'):.9f}), "
                  f"latency change {dul.get(f['key'], 0) / 1000:.0f} ns")
print(f"TOTAL: {tot_cmp} application frames compared, {tot_diff} differ; {tot_behind} talker app frames queued behind a "
      f"Pdelay_Req, of which {tot_behind_diff} differ")
