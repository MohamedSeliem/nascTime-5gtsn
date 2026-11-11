#!/usr/bin/env python3
"""M2-R181 version-neutral rows (simulations/results/simu5g-1.8.1/M2-R181-plan.md §2, §3; predictions
M2-R181-predictions.md). They verify behaviour from raw evidence; they are added alongside the historical
checkers, which are unchanged. Each row is run on 1.8.1 outputs, on 1.8.0 outputs (control: must FAIL where 1.8.0
has the defect) and on a declared in-memory mutation (control: must FAIL).

    check_v181.py s5     <M1 results root>  [--mutate]     S5-R-egress-v, S5-W-identity-v
    check_v181.py o1     <M1 results root>  [--mutate]     O1-cons (O-S3-1 configs O1-drain, O1-harq16)
    check_v181.py otail  <M1 results root>  [--mutate]     OT-strand (O-tail configs)

Header model of the RLC replay (NR UM, 12-bit SN, as check_o_tail.py): complete SDU 1 B, first segment 2 B, later
segment 4 B. The replay uses recorded SDU arrivals and PDU sizes only, never the scheduler code.
"""
import os
import re
import struct
import sys
from collections import Counter, defaultdict

import pandas as pd

MODE, RES = sys.argv[1], sys.argv[2]
MUTATE = "--mutate" in sys.argv
NS, MS = 1e-9, 1e-3
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def finish(title):
    print(title + (" [MUTATION CONTROL]" if MUTATE else ""))
    w = max(len(r[0]) for r in rows)
    for c, d, v in rows:
        print(f"{v:4}  {c:<{w}}  {d}")
    print()
    print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")


def load(path, seed=None):
    d = pd.read_csv(path, low_memory=False)
    d = d[d.run.notna()].copy()
    d["seed"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
    d["mod"] = d.module.fillna("").str.replace("M1Bridge.", "", regex=False)
    if seed is not None:
        d = d[d.seed == seed]
    return d


def vec(d, seed, mod, name):
    r = d[(d.seed == seed) & (d.type == "vector") & (d["mod"] == mod) & (d.name == name)]
    if len(r) != 1 or not isinstance(r.vectime.iloc[0], str):
        return []
    return list(zip(map(float, r.vectime.iloc[0].split()), map(float, r.vecvalue.iloc[0].split())))


def vecs(d, seed, pred, name):
    r = d[(d.seed == seed) & (d.type == "vector") & (d.name == name) & d["mod"].map(pred)]
    return {m: (list(zip(map(float, t.split()), map(float, v.split()))) if isinstance(t, str) else [])
            for m, t, v in zip(r["mod"], r.vectime, r.vecvalue)}


def scalar(d, seed, mod, name):
    r = d[(d.seed == seed) & (d.type == "scalar") & (d["mod"] == mod) & (d.name == name)].value
    return float(r.iloc[0]) if len(r) == 1 else float("nan")


def replay(sdus, pdus):
    """byte-level NR UM TX replay: returns completed [(arrival, size, t_last)], left [{arr,size,sent}], and per-slot
    residual after each PDU time [(t, bytes left, next arrival or None)]"""
    queue, i, done, after = [], 0, [], []
    k = 0
    while k < len(pdus):
        t = pdus[k][0]
        while i < len(sdus) and sdus[i][0] <= t:
            queue.append({"arr": sdus[i][0], "size": int(sdus[i][1]), "sent": 0})
            i += 1
        while k < len(pdus) and pdus[k][0] == t:
            s = int(pdus[k][1])
            if not queue:
                raise ValueError(f"PDU at {t} with an empty replayed queue")
            h = queue[0]
            pay = (h["size"] if s == h["size"] + 1 else s - 2) if h["sent"] == 0 else s - 4
            h["sent"] += pay
            if h["sent"] >= h["size"]:
                done.append((h["arr"], h["size"], t))
                queue.pop(0)
            k += 1
        left = sum(q["size"] - q["sent"] for q in queue)
        after.append((t, left, sdus[i][0] if i < len(sdus) else None))
    while i < len(sdus):
        queue.append({"arr": sdus[i][0], "size": int(sdus[i][1]), "sent": 0})
        i += 1
    return done, queue, after


# ------------------------------------------------------------------------------------------------ S5 -----
def read_pcap(path):
    b = open(path, "rb").read()
    scale = 1e-9 if struct.unpack("<I", b[:4])[0] == 0xA1B23C4D else 1e-6
    off, out = 24, []
    while off < len(b):
        sec, frac, incl, _ = struct.unpack("<IIII", b[off:off + 16])
        off += 16
        out.append((sec + frac * scale, b[off:off + incl]))
        off += incl
    return out


def ident(f):
    if f[12:14] == b"\x81\x00" and f[16:18] == b"\x86\xf0":
        return ("app", f[6:12].hex(), f[14] >> 5, int.from_bytes(f[22:26], "big"))
    if f[12:14] == b"\x88\xf7":
        return ("gptp", f[6:12].hex(), f[14] & 0xF, int.from_bytes(f[44:46], "big"))
    return ("other", f[6:12].hex(), f[12:14].hex(), None)


def s5():
    OUT = os.path.join(RES, "S5")
    END = 5.0
    s5d = load(os.path.join(OUT, "seeds.csv"))
    pr = load(os.path.join(OUT, "pcaprun.csv"))
    PC = lambda n: os.path.join(OUT, "pcaprun", "pcap", f"M1Bridge.{n}.pcap")
    ds, nw = read_pcap(PC("dsTt.pcapRecorder[0]")), read_pcap(PC("nwTt.pcapRecorder[0]"))
    tk, ls = read_pcap(PC("talker.pcapRecorder[0]")), read_pcap(PC("listener.pcapRecorder[0]"))
    if MUTATE:                                              # identity control: alter one byte of one DL frame leaving dsTt
        t, f = ds[50]
        ds[50] = (t, f[:30] + bytes([f[30] ^ 0xFF]) + f[31:])
    GM = next(f[6:12].hex() for _, f in ls if ident(f)[0] == "gptp" and ident(f)[2] == 0)
    SL = next(f[6:12].hex() for _, f in tk if ident(f)[0] == "gptp" and ident(f)[2] == 2)
    seeds = sorted(int(x) for x in s5d.seed.unique())
    REC = "transit5gs:meanBitElapsedTimePerPacket:vector"
    det, ok_all, frames_out = [], True, {}
    for name, enter, leave, src in (("DL", nw, ds, GM), ("UL", ds, nw, SL)):
        fin = {ident(f): (t, f) for t, f in enter if f[6:12].hex() == src}
        fout = [(t, f) for t, f in leave if f[6:12].hex() == src]
        keys = [ident(f) for _, f in fout]
        dup = len(keys) != len(set(keys))
        unknown = [k for k in keys if k not in fin or k[0] == "other"]
        changed = [k for t, f in fout for k in [ident(f)] if k in fin and fin[k][1] != f]
        last, order_bad = {}, 0
        for k in keys:
            if k[:3] in last and k[3] <= last[k[:3]]:
                order_bad += 1
            last[k[:3]] = k[3]
        missing = [k for k in fin if k not in set(keys)]
        late_only = all(fin[k][0] > END - 0.100 for k in missing)
        ok = not dup and not unknown and not changed and not order_bad and late_only and bool(keys)
        ok_all &= ok
        frames_out[name] = [(t, f, fin[ident(f)][0]) for t, f in fout if ident(f) in fin]
        det.append(f"{name}: {len(fin)} in, {len(fout)} out; unknown {len(unknown)}, altered {len(changed)}, duplicated {dup}, "
                   f"out of order {order_bad}, still inside {len(missing)} (all entered in the last 100 ms: {late_only})")
    add("S5-W-identity-v: frames leave the 5G system with the identity and bytes they entered with, once, in order (PCAP, seed 0)",
        " | ".join(det), ok_all)

    # counts per seed and direction: recorder samples = frames that reached the far translator's measurement layer
    cnt_bad, cnt_det = [], []
    for s in seeds:
        for dirn, tt in (("DL", "dsTt"), ("UL", "nwTt")):
            mod = f"{tt}.eth[0].measurementLayer.measurementRecorder"
            n = len(vec(s5d, s, mod, REC))
            crossed = scalar(s5d, s, mod, "incomingPackets:count")
            if s == 0:
                cnt_det.append(f"{dirn} {n} samples / {int(crossed) if crossed == crossed else 'n/a'} frames")
            if not (crossed == crossed and crossed > 0 and n == crossed):
                cnt_bad.append((s, dirn, n, crossed))
    # per sample (seed 0, PCAP run): elapsed = PCAP transit within the frame's serialisation time at 1 Gb/s (+1 ns)
    sam_bad, matched = [], 0
    for dirn, tt in (("DL", "dsTt"), ("UL", "nwTt")):
        samples = vec(pr, 0, f"{tt}.eth[0].measurementLayer.measurementRecorder", REC)
        if MUTATE and dirn == "DL" and samples:
            t, v = samples[10]
            samples[10] = (t, v + (len(frames_out["DL"][10][1]) + 8) * 8 * NS + 2 * NS)
        outs = frames_out[dirn]
        j = 0
        for ts, val in samples:
            while j < len(outs) and outs[j][0] < ts - 20e-6:
                j += 1
            cands = [o for o in outs[j:j + 4] if abs(o[0] - ts) <= (len(o[1]) + 8) * 8 * NS + NS]
            if not cands:
                sam_bad.append((dirn, ts, "no frame"))
                continue
            t_out, f, t_in = min(cands, key=lambda o: abs(o[0] - ts))
            ser = (len(f) + 8) * 8 * NS
            if not (t_out - t_in - ser - NS <= val <= t_out - t_in + ser + NS):
                sam_bad.append((dirn, ts, val, t_out - t_in))
            else:
                matched += 1
    add("S5-R-egress-v: INET flow-measurement samples at the far translator, one per frame that crossed, each = its PCAP transit",
        f"seed 0: {'; '.join(cnt_det)}; count mismatches over seeds {seeds}: {len(cnt_bad)}{' ' + str(cnt_bad[:3]) if cnt_bad else ''}; "
        f"PCAP run: {matched} samples matched to their frame within the serialisation time, mismatches {len(sam_bad)}"
        f"{' ' + str(sam_bad[:3]) if sam_bad else ''}",
        not cnt_bad and not sam_bad and matched > 0)
    finish("M2-R181 version-neutral S5 rows")


# ------------------------------------------------------------------------------------------------ O1 -----
FLOWS = {f"pcp{p}": (100 + 20 * p, True) for p in range(8)}
FLOWS["untagged"] = (300, False)
FLOWS["bg"] = (1400, True)
APP = {f: i for i, f in enumerate(list(FLOWS)[:9])}
APP["bg"] = 10
FRAME = {f: 14 + (4 if t else 0) + pl for f, (pl, t) in FLOWS.items()}
SINKLEN = {f: pl + (4 if t else 0) for f, (pl, t) in FLOWS.items()}
DIRS = {"UL": ("talker", "listener", "ue[0]", "gnb1"), "DL": ("listener", "talker", "gnb1", "ue[0]")}
W_ETH = 1 * MS            # declared bound on source -> RLC TX and RLC RX -> sink (Ethernet / bridge path, light queues)
W_HARQ = 25 * MS          # declared: 4 transmissions x (5-slot feedback + 1) + 1 slot


def flow_of(size):
    for f, L in FRAME.items():
        if L <= size <= L + 3:
            return f
    return None


def o1():
    OUT = os.path.join(RES, "O-S3-1")
    END = 5.0
    for cfg in ("O1-drain", "O1-harq16"):
        d = load(os.path.join(OUT, cfg + ".csv"))
        seeds = sorted(int(x) for x in d.seed.unique())
        bad, det, tot = [], Counter(), Counter()
        for s in seeds:
            for dirn, (src, snk, txn, rxn) in DIRS.items():
                txs = vecs(d, s, lambda m, n=txn: m.startswith(n + ".cellularNic.") and "-um-" in m and m.endswith(".tx"),
                           "receivedPacketFromUpperLayer:vector(packetBytes)")
                tx_by_flow, rx_by_flow, rx_recent = Counter(), Counter(), Counter()
                for m, sd in sorted(txs.items()):
                    drb = m.rsplit("-", 1)[1].split(".")[0]
                    pdus = vecs(d, s, lambda x, m=m: x == m, "sentPduSize:vector").get(m, [])
                    rxm = [x for x in vecs(d, s, lambda x, n=rxn: x.startswith(n + ".cellularNic.") and "-um-" in x and x.endswith(".rx"),
                                             "sentPacketToUpperLayer:vector(packetBytes)") if x.rsplit("-", 1)[1].split(".")[0] == drb]
                    rx = vecs(d, s, lambda x, r=rxm: x in r, "sentPacketToUpperLayer:vector(packetBytes)").get(rxm[0], []) if rxm else []
                    if MUTATE and s == 0 and dirn == "DL" and rx:
                        rx = rx[:len(rx) // 2] + rx[len(rx) // 2 + 1:]
                    try:
                        done, left, _ = replay(sd, pdus)
                    except ValueError as ex:
                        bad.append((s, dirn, m, str(ex)))
                        continue
                    queued = sum(1 for q in left if q["sent"] == 0)
                    segm = sum(1 for q in left if q["sent"] > 0)
                    in_harq = len(done) - len(rx)
                    # delivered SDUs are the replay's completed SDUs, in order and size (UM in-order delivery, no loss)
                    order_ok = all(int(v) == done[k][1] for k, (_, v) in enumerate(rx)) if 0 <= in_harq else False
                    late_ok = in_harq >= 0 and all(t_last > END - W_HARQ for _, _, t_last in done[len(rx):])
                    unexplained = 0 if (order_ok and late_ok) else max(1, abs(in_harq))
                    tot.update({f"{dirn} sdus": len(sd), f"{dirn} delivered": len(rx), f"{dirn} queued": queued,
                                f"{dirn} segmented": segm, f"{dirn} in-HARQ": max(in_harq, 0), f"{dirn} UNEXPLAINED": unexplained})
                    if unexplained:
                        bad.append((s, dirn, m, f"completed {len(done)}, delivered {len(rx)}, order {order_ok}, late {late_ok}"))
                    tx_by_flow.update(flow_of(int(v)) for _, v in sd)
                    rx_by_flow.update(flow_of(int(v)) for _, v in rx)
                    rx_recent.update(flow_of(int(v)) for t, v in rx if t > END - W_ETH)
                # application boundaries: source -> RLC TX, RLC RX -> sink
                sink = vecs(d, s, lambda m, x=snk: m == f"{x}.app[9].sink", "packetLengths:vector").get(f"{snk}.app[9].sink", [])
                recv = Counter()
                for t, v in sink:
                    recv.update(f for f in FLOWS if SINKLEN[f] == int(v) // 8)
                for f in FLOWS:
                    m = f"{src}.app[{APP[f]}].io"
                    sv = vecs(d, s, lambda x, m=m: x == m, "packetSent:vector(packetBytes)").get(m, [])
                    before = len(sv) - tx_by_flow[f]
                    recent = sum(1 for t, _ in sv if t > END - W_ETH)
                    after = rx_by_flow[f] - recv[f]
                    tot.update({f"{dirn} before-RLC": max(before, 0), f"{dirn} RLC-to-sink": max(after, 0)})
                    if not (0 <= before <= recent and 0 <= after <= rx_recent[f]):
                        bad.append((s, dirn, f, f"sent {len(sv)}, RLC in {tx_by_flow[f]}, RLC out {rx_by_flow[f]}, sink {recv[f]}"))
        # MAC deletions: the 1.8.0 log pattern in the trace runs (1.8.1 raises an error instead; the run must complete)
        dele = 0
        tr = os.path.join(OUT, "runs", f"trace-{cfg}-trace.log")
        trace_ok = os.path.exists(tr) and "EXIT=0" in open(tr).read()
        if os.path.exists(tr):
            dele = sum(1 for l in open(tr) if "no available process for this MAC PDU" in l)
        ml = d[(d.type == "scalar") & d.name.fillna("").str.startswith("macPacketLoss")].value.astype(float)
        harq_err = float(ml[ml == ml].sum())
        ok = not bad and dele == 0 and trace_ok and harq_err == 0
        add(f"O1-cons {cfg}: sent = delivered + before-RLC + queued + segmented + in-HARQ + attributed loss, UNEXPLAINED 0 (seeds {seeds})",
            f"totals {dict(tot)}; MAC PDU deletions in the seed-0 trace {dele} (trace run completed: {trace_ok}); "
            f"MAC loss statistics sum {harq_err:g}; violations {len(bad)}{' ' + str(bad[:3]) if bad else ''}", ok)
    finish("M2-R181 version-neutral O-S3-1 rows")


# --------------------------------------------------------------------------------------------- O-tail -----
def otail():
    OUT = os.path.join(RES, "O-tail")
    TX, RX = "gnb1.cellularNic.rlc-um-2049-1.tx", "ue[0].cellularNic.nrRlc-um-1-1.rx"
    END = 5.0
    for cfg in ("O2-s4", "O2-s4-nodl", "O1-harq16", "O2-flush"):
        d = load(os.path.join(OUT, cfg + ".csv"), seed=0)
        sd = vec(d, 0, TX, "receivedPacketFromUpperLayer:vector(packetBytes)")
        pdus = vec(d, 0, TX, "sentPduSize:vector")
        if MUTATE and cfg == "O2-s4":                  # delay one PDU past the next SDU arrival by 3 slots
            k = len(pdus) // 2
            nxt = next((a for a, _ in sd if a > pdus[k][0]), pdus[k][0])
            pdus = sorted(pdus[:k] + [(nxt + 3 * MS, pdus[k][1])] + pdus[k + 1:])
        done, left, after = replay(sd, pdus)
        light = cfg in ("O2-s4", "O2-s4-nodl")
        strand = []
        if light:
            times = [t for t, _, _ in after]
            for j, (t, rem, nxt_arr) in enumerate(after):
                if rem > 0 and j + 1 < len(after):
                    t2 = times[j + 1]
                    if t2 - t >= 2 * MS - 1e-9 and nxt_arr is not None and t2 >= nxt_arr:
                        strand.append((round(t, 6), rem))
        waits = [t_last - a for a, _, t_last in done]
        wmax = max(waits) if waits else 0.0
        left_end = [(round(q["arr"], 6), q["size"], q["size"] - q["sent"]) for q in left]
        if light:
            ok = not strand and wmax <= 2 * MS + 1e-9
            det = f"stranding events {len(strand)}{' ' + str(strand[:3]) if strand else ''}; max gNB wait {wmax * 1e3:.3f} ms over {len(done)} SDUs"
        else:
            ok = not left_end
            det = f"sources stop at 3 s (O2-flush: one frame at 3.5 s), run to {END:g} s; left in RLC at the end {left_end}"
        add(f"OT-strand {cfg}: " + ("no SDU remainder waits for a later SDU; every SDU leaves within 2 slots" if light
                                    else "nothing left in the gNB DRB 1 RLC after the drain"), det, ok)
    finish("M2-R181 version-neutral O-tail rows")


{"s5": s5, "o1": o1, "otail": otail}[MODE]()
