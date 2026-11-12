#!/usr/bin/env python3
"""M2-R181b diagnostic (no verdict): per-recorder comparison of M2S4 vs M2S4-ctl-nopdelay, one seed.

    diag_r2b.py <run dir M2S4> <run dir ctl> <seed>

For every PCAP recorder present in both runs, the application frames (etherType != 0x88F7) are matched by
(etherType, PCP, VID, payload hash, occurrence) and their timestamps compared. For each frame whose end-to-end
latency differs, every recorder's timestamps are printed, plus the frames on the same recorder/direction in a
+-5 us window around it (all etherTypes), in both runs.
"""
import os
import sys
from collections import Counter

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../m2/check"))
import pcapng  # noqa: E402

A, C, SEED = sys.argv[1], sys.argv[2], sys.argv[3]


def load(run, cfg):
    d = os.path.join(run, "pcap", f"{cfg}-{SEED}")
    out = {}
    for fn in sorted(os.listdir(d)):
        if not fn.endswith(".pcapng"):
            continue
        fr, occ = [], Counter()
        for p in pcapng.read(os.path.join(d, fn)):
            f = pcapng.ethernet(p["data"])
            k = (f["etherType"], f["pcp"], f["vid"], pcapng.fnv1a64(f["payload"]), p["dir"])
            occ[k] += 1
            mt = (f["payload"][0] & 15) if f["etherType"] == 0x88F7 and f["payload"] else None
            fr.append({"t": p["t_ps"], "L": len(p["data"]), "dir": p["dir"], "et": f["etherType"], "pcp": f["pcp"],
                       "mt": mt, "key": k + (occ[k],)})
        out[fn.replace(".pcapng", "").replace("M1Bridge.", "")] = fr
    return out


a = load(A, os.path.basename(A.rstrip("/")))
c = load(C, os.path.basename(C.rstrip("/")))
ta, tc = a["talker.pcapRecorder[0]"], c["talker.pcapRecorder[0]"]
la, lc = a["listener.pcapRecorder[0]"], c["listener.pcapRecorder[0]"]


def lat(src, dst):
    tx = {f["key"][:4] + (f["key"][5],): f["t"] for f in src if f["dir"] == 2 and f["et"] != 0x88F7}
    return {f["key"][:4] + (f["key"][5],): f["t"] - tx[f["key"][:4] + (f["key"][5],)] for f in dst
            if f["dir"] == 1 and f["et"] != 0x88F7 and f["key"][:4] + (f["key"][5],) in tx}


ul_a, ul_c = lat(ta, la), lat(tc, lc)
diff = sorted(k for k in ul_a if k in ul_c and ul_a[k] != ul_c[k])
print(f"UL application frames: {len(ul_a)} vs {len(ul_c)}; latency differs for {len(diff)}")


def fmt(t):
    return f"{t / 1e12:.9f}"


for k in diff:
    sent = next(f["t"] for f in ta if f["dir"] == 2 and f["key"][:4] + (f["key"][5],) == k)
    print(f"\n=== frame etherType {k[0]:#06x} pcp {k[1]} vid {k[2]} occ {k[4]}: sent {fmt(sent)}; M2S4 - ctl latency "
          f"{(ul_a[k] - ul_c[k]) / 1000:.3f} ns")
    for rec in sorted(set(a) & set(c)):
        xa = [f for f in a[rec] if f["key"][:4] + (f["key"][5],) == k]
        xc = [f for f in c[rec] if f["key"][:4] + (f["key"][5],) == k]
        if not xa and not xc:
            continue
        print(f"  {rec:30s} " + "; ".join(f"dir {f['dir']} {fmt(f['t'])}" for f in xa) + "   |ctl| " +
              "; ".join(f"dir {f['dir']} {fmt(f['t'])}" for f in xc) +
              ("   SAME" if [f['t'] for f in xa] == [f['t'] for f in xc] else "   DIFF"))
        if [f['t'] for f in xa] != [f['t'] for f in xc]:
            for name, run, xs in (("M2S4", a, xa), ("ctl ", c, xc)):
                for f0 in xs:
                    win = [f for f in run[rec] if f["dir"] == f0["dir"] and abs(f["t"] - f0["t"]) <= 5_000_000]
                    print(f"      {name} window dir {f0['dir']}: " + ", ".join(
                        f"{fmt(f['t'])} L{f['L']} et{f['et']:#06x}{'' if f['mt'] is None else ' mt' + str(f['mt'])} pcp{f['pcp']}"
                        + (" <==" if f is f0 else "") for f in win))
