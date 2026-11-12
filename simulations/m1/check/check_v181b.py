#!/usr/bin/env python3
"""M2-R181b row S5-R-egress-v2, alongside S5-R-egress-v (check_v181.py, unchanged; it keeps its FAIL).

    check_v181b.py s5e <M1 results root> [--mutate]     S5-R-egress-v2
    check_v181b.py s5i <M1 results root> [--mutate]     S5-R-ingress-v

S5-R-egress-v declared each INET flow-measurement sample (transit5gs:meanBitElapsedTimePerPacket at the far
translator's 5G-side measurement layer) equal to its frame's PCAP transit within the frame's serialisation time
(+1 ns). M2-R181b (diagnostic r181b/s5-egress-per-frame.csv) established the exact relation, which the declared
bound did not model: the measurement starts in the near translator's eth[0] MeasurementLayer, BEFORE that port's
MAC queue, and ends at the far translator on reception; the PCAP stamps are frame ends on the translators' eth[0].
So, per sample, exactly:

    sample = PCAP transit + own serialisation time + near-port egress wait

with the egress wait computed from PCAP alone, from the station's transmit end (the frame's arrival at the near
translator is the station's transmit end + 50 ns: INET EthernetLink default length 10 m / 2e8 m/s; store and
forward, zero bridging time): wait = near eth[0] transmit start - (station transmit end + 50 ns) >= 0.

Rows (seed 0 PCAP run S5-pcap; counts over all seeds as in S5-R-egress-v):
  - counts: recorder samples = frames that crossed (incomingPackets:count), per seed and direction;
  - every sample matched to its frame; |sample - (transit + ser + wait)| <= 1 ns; wait >= 0;
  - reported: the distinct non-zero waits and the frames they belong to.
Mutation: one DL sample + 2 ns -> FAIL.

S5-R-ingress-v, alongside check_s5.py R-ingress (unchanged). R-ingress counts the tagged frames passing the last
INET module before the 5G system (UPF bridge fcsInserter for DL, UE Ethernet fcsInserter for UL) and requires that
count to equal the frames tagged at the near translator. That module carries both directions; on 1.8.0 the frames of
the opposite direction arrived untagged (tags lost in the 5G system), so only one direction was counted. Version-
appropriate form, per seed:
    tagged at UPF bridge fcsInserter = started at nwTt (DL) + transit samples recorded at nwTt (UL frames that crossed tagged)
    tagged at UE fcsInserter         = started at dsTt (UL) + transit samples recorded at dsTt (DL frames that crossed tagged)
and the started counts > 0. On 1.8.0 the recorded counts are 0 and this reduces to the historical row.
Mutation: one started DL count + 1 -> FAIL.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
MODE = sys.argv[1]
if MODE not in ("s5e", "s5i"):
    sys.exit(f"unknown mode {MODE}")
sys.argv[1] = "s5"   # the shared helpers of check_v181.py read MODE/RES at import
src = open(os.path.join(HERE, "check_v181.py")).read().rsplit('\n{"s5": s5', 1)[0]
g = {"__name__": "check_v181_helpers", "__file__": os.path.join(HERE, "check_v181.py")}
exec(compile(src, "check_v181.py", "exec"), g)
load, vec, scalar, read_pcap, ident, add, finish, MUTATE, NS = (g[k] for k in (
    "load", "vec", "scalar", "read_pcap", "ident", "add", "finish", "MUTATE", "NS"))
RES = g["RES"]
PROP = 50 * NS

OUT = os.path.join(RES, "S5")
s5d = load(os.path.join(OUT, "seeds.csv"))
if MODE == "s5i":
    FL = "transit5gs:flowOutgoingPacketLengths:vector"
    REC = "transit5gs:meanBitElapsedTimePerPacket:vector"
    n = lambda s, m, name: len(vec(s5d, s, m, name))
    bad, det = [], []
    for s in sorted(int(x) for x in s5d.seed.unique()):
        st = {"DL": n(s, "nwTt.eth[0].measurementLayer.measurementStarter", FL), "UL": n(s, "dsTt.eth[0].measurementLayer.measurementStarter", FL)}
        if MUTATE and s == 0:
            st["DL"] += 1
        rec = {"DL": n(s, "dsTt.eth[0].measurementLayer.measurementRecorder", REC), "UL": n(s, "nwTt.eth[0].measurementLayer.measurementRecorder", REC)}
        core = {"DL": n(s, "upf.ethBridge.ethernet.fcsInserter", FL), "UL": n(s, "ue[0].ethernet.fcsInserter", FL)}
        exp = {"DL": st["DL"] + rec["UL"], "UL": st["UL"] + rec["DL"]}
        if s == 0:
            det.append(f"seed 0: started {st}, recorded at the far translator {rec}, tagged at UPF bridge (DL) / UE Ethernet (UL) {core}, "
                       f"expected {exp}")
        if core != exp or min(st.values()) <= 0:
            bad.append((s, core, exp))
    add("S5-R-ingress-v: tagged frames at the last INET module before the 5G system = frames tagged at the near translator "
        "+ frames of the other direction that crossed the 5G system tagged (seeds 0..9)",
        "; ".join(det) + f"; seeds not matching: {len(bad)}{' ' + str(bad[:3]) if bad else ''}", not bad)
    finish("M2-R181b row S5-R-ingress-v")
    sys.exit(0)
pr = load(os.path.join(OUT, "pcaprun.csv"))
PC = lambda n: os.path.join(OUT, "pcaprun", "pcap", f"M1Bridge.{n}.pcap")
ds, nw = read_pcap(PC("dsTt.pcapRecorder[0]")), read_pcap(PC("nwTt.pcapRecorder[0]"))
tk, ls = read_pcap(PC("talker.pcapRecorder[0]")), read_pcap(PC("listener.pcapRecorder[0]"))
GM = next(f[6:12].hex() for _, f in ls if ident(f)[0] == "gptp" and ident(f)[2] == 0)
SL = next(f[6:12].hex() for _, f in tk if ident(f)[0] == "gptp" and ident(f)[2] == 2)
ser = lambda f: (len(f) + 8) * 8 * NS
REC = "transit5gs:meanBitElapsedTimePerPacket:vector"

cnt_bad, cnt_det = [], []
for s in sorted(int(x) for x in s5d.seed.unique()):
    for dirn, tt in (("DL", "dsTt"), ("UL", "nwTt")):
        mod = f"{tt}.eth[0].measurementLayer.measurementRecorder"
        n = len(vec(s5d, s, mod, REC))
        crossed = scalar(s5d, s, mod, "incomingPackets:count")
        if s == 0:
            cnt_det.append(f"{dirn} {n} samples / {int(crossed) if crossed == crossed else 'n/a'} frames")
        if not (crossed == crossed and crossed > 0 and n == crossed):
            cnt_bad.append((s, dirn, n, crossed))

bad, matched, waits, det = [], 0, {}, []
for dirn, near, far, station, src, tt in (("DL", nw, ds, ls, GM, "dsTt"), ("UL", ds, nw, tk, SL, "nwTt")):
    st = {ident(f): t for t, f in station if f[6:12].hex() == src}
    fin = {ident(f): (t, f) for t, f in near if f[6:12].hex() == src}
    outs = [(t, f, fin[ident(f)][0]) for t, f in far if f[6:12].hex() == src and ident(f) in fin]
    samples = vec(pr, 0, f"{tt}.eth[0].measurementLayer.measurementRecorder", REC)
    if MUTATE and dirn == "DL" and samples:
        t, v = samples[10]
        samples[10] = (t, v + 2 * NS)
    j = 0
    for ts, val in samples:
        while j < len(outs) and outs[j][0] < ts - 20e-6:
            j += 1
        cands = [o for o in outs[j:j + 4] if abs(o[0] - ts) <= ser(o[1]) + NS]
        if not cands:
            bad.append((dirn, round(ts, 9), "no frame"))
            continue
        t_out, f, t_in = min(cands, key=lambda o: abs(o[0] - ts))
        k = ident(f)
        if k not in st:
            bad.append((dirn, round(ts, 9), "frame not seen at the station"))
            continue
        wait = (t_in - ser(f)) - (st[k] + PROP)
        exp = (t_out - t_in) + ser(f) + wait
        if abs(val - exp) > NS or wait < -NS:
            bad.append((dirn, round(ts, 9), round((val - exp) / NS, 3), round(wait / NS, 3)))
        else:
            matched += 1
            if round(wait / NS) != 0:
                key = (dirn, k[0], k[2], len(f), round(wait / NS))
                waits[key] = waits.get(key, 0) + 1
add("S5-R-egress-v2: recorder samples = frames that crossed, per seed and direction; each sample = its frame's PCAP "
    "transit + own serialisation time + near-translator egress wait (PCAP), to 1 ns",
    f"seed 0: {'; '.join(cnt_det)}; count mismatches over seeds: {len(cnt_bad)}{' ' + str(cnt_bad[:3]) if cnt_bad else ''}; "
    f"PCAP run: {matched} samples exact, mismatches {len(bad)}{' ' + str(bad[:3]) if bad else ''}; non-zero egress waits "
    f"(dir, kind, type/pcp, L, wait ns): count {waits}",
    not cnt_bad and not bad and matched > 0)
finish("M2-R181b row S5-R-egress-v2")
