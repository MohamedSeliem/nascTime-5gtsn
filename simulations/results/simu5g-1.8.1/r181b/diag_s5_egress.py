#!/usr/bin/env python3
"""M2-R181b diagnostic (no verdict): per-frame breakdown of S5-R-egress-v (M1 S5-pcap run, seed 0).

    diag_s5_egress.py <M1 results root containing S5/>  [csv out]

For every recorder sample at the far translator (DL: dsTt, UL: nwTt), matched to its frame by egress time
(PCAP on the translators' 5G-side eth[0], end-of-frame stamps, as in check_v181.py):
  val           INET meanBitElapsedTime sample
  transit       PCAP: far translator eth[0] receive end - near translator eth[0] transmit end
  ser           the frame's own serialisation time at 1 Gb/s ((L + 8) * 8 ns)
  excess        val - transit - ser
  wait          near-translator egress wait from PCAP alone: transmit start on near eth[0] - (station transmit end
                + the station-to-translator constant), the constant being the minimum over all frames of that
                direction (the frame's arrival at the translator, store and forward, zero processing time)
  prev_gap      transmit start on near eth[0] - end of the previous frame on that port (any source)
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.argv = [sys.argv[0], "s5", sys.argv[1]] + sys.argv[2:]
src = open(os.path.join(HERE, "../../../m1/check/check_v181.py")).read().rsplit("\n{\"s5\": s5", 1)[0]
cv = {"__name__": "cv", "__file__": os.path.join(HERE, "../../../m1/check/check_v181.py")}
exec(compile(src, "check_v181", "exec"), cv)
NS = 1e-9
OUT = os.path.join(sys.argv[2], "S5")
CSV = sys.argv[3] if len(sys.argv) > 3 else None
pr = cv["load"](os.path.join(OUT, "pcaprun.csv"))
PC = lambda n: os.path.join(OUT, "pcaprun", "pcap", f"M1Bridge.{n}.pcap")
rp, ident, vec = cv["read_pcap"], cv["ident"], cv["vec"]
ds, nw, tk, ls = rp(PC("dsTt.pcapRecorder[0]")), rp(PC("nwTt.pcapRecorder[0]")), rp(PC("talker.pcapRecorder[0]")), rp(PC("listener.pcapRecorder[0]"))
GM = next(f[6:12].hex() for _, f in ls if ident(f)[0] == "gptp" and ident(f)[2] == 0)
SL = next(f[6:12].hex() for _, f in tk if ident(f)[0] == "gptp" and ident(f)[2] == 2)
ser = lambda f: (len(f) + 8) * 8 * NS
rows, summary = [], []
R = lambda x: "nan" if x != x else round(x / NS)
for dirn, near, far, station, srcmac, tt in (("DL", nw, ds, ls, GM, "dsTt"), ("UL", ds, nw, tk, SL, "nwTt")):
    st = {ident(f): t for t, f in station if f[6:12].hex() == srcmac}
    near_tx = sorted((t, f) for t, f in near)  # every frame on the near port (both directions are in one file)
    fin = {ident(f): (t, f) for t, f in near if f[6:12].hex() == srcmac}
    outs = [(t, f, fin[ident(f)][0]) for t, f in far if f[6:12].hex() == srcmac and ident(f) in fin]
    # arrival constant: min over frames of (near tx start - station tx end)
    pre = {}
    for k, (t, f) in fin.items():
        if k in st:
            pre[k] = (t - ser(f)) - st[k]
    c0 = min(pre.values())
    samples = vec(pr, 0, f"{tt}.eth[0].measurementLayer.measurementRecorder", "transit5gs:meanBitElapsedTimePerPacket:vector")
    j, bad = 0, 0
    for ts, val in samples:
        while j < len(outs) and outs[j][0] < ts - 20e-6:
            j += 1
        cands = [o for o in outs[j:j + 4] if abs(o[0] - ts) <= ser(o[1]) + NS]
        if not cands:
            rows.append((dirn, ts, "nomatch"))
            continue
        t_out, f, t_in = min(cands, key=lambda o: abs(o[0] - ts))
        k = ident(f)
        wait = pre.get(k, float("nan")) - c0
        prev = [t for t, g in near_tx if t < t_in - ser(f) + 1e-12]
        prev_gap = (t_in - ser(f)) - prev[-1] if prev else float("nan")
        excess = val - (t_out - t_in) - ser(f)
        flag = not (abs(val - (t_out - t_in)) <= ser(f) + NS)
        bad += flag
        rows.append((dirn, ts, k[0], k[2], len(f), round(val / NS), round((t_out - t_in) / NS), round(ser(f) / NS),
                     R(excess), R(wait), R(prev_gap), int(flag)))
    ex = [r for r in rows if r[0] == dirn and len(r) > 3]
    summary.append(f"{dirn}: {len(samples)} samples; outside the declared bound {bad}; "
                   f"excess == wait (to 1 ns) for {sum(1 for r in ex if r[9] != "nan" and abs(r[8] - r[9]) <= 1)} of {len(ex)}; "
                   f"distinct (excess, wait, frame type, L) of the out-of-bound samples: "
                   f"{sorted(set((r[8], r[9], r[2], r[3], r[4]) for r in ex if r[11]))}")
print("\n".join(summary))
if CSV:
    with open(CSV, "w") as fh:
        fh.write("dir,sample_t,kind,type_or_pcp,L,val_ns,pcap_transit_ns,ser_ns,excess_ns,egress_wait_ns,prev_gap_ns,out_of_bound\n")
        for r in rows:
            fh.write(",".join(str(x) for x in r) + "\n")
