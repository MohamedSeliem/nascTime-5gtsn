#!/usr/bin/env python3
"""M2-S1 checker: complete observed 5G-TSN bridge residence interval.
Usage: check_m2s1.py <results/M2-S1> <M2-S0 raw-outputs.sha256 (recorded at ad47a8a)>

Events (simulation events, see migration/m2-s1-design.md):
  t1  ingress: last bit received on TT_in's TSN port eth[1] (receiver receptionEnded = PCAP in)
  t2  TT_in eth[0] MAC FIFO entry (measurement-layer TX slot)
  t3  TT_in eth[0] MAC dequeue (macLayer.outboundEmitter packetSentToLower)
  t4  TT_in eth[0] transmissionStarted
  t5  TT_in eth[0] transmissionEnded (PCAP out)
  t6  5G-system ingress Ethernet port, last bit received (UPF dnEth DL / UE eth[0] UL; PCAP only)
  t7  5G-system egress Ethernet port, last bit sent (UE eth[0] DL / UPF dnEth UL; PCAP only)
  t8  TT_out eth[0] receptionEnded (PCAP in; the M2-S0 partial interval ends here)
  t9  TT_out eth[1] MAC FIFO entry (M2-S0 recovery callback)
  t10 TT_out eth[1] MAC dequeue, t11 transmissionStarted
  t12 final egress: last bit sent on TT_out's TSN port eth[1] (transmissionEnded = PCAP out)
Complete observed bridge residence interval R = t12 - t1. This is an observed interval
between two port events, not an IEEE 802.1AS residence-time correction.

Independent evidence: PCAP (pcapng, 1 ps) at the stations, both ports of both translators,
the UPF N6 port, the UE Ethernet port and N3; the exact PCAP-only port model
  tx end = max(arrival + P, previous tx end on the port + 96 ns) + (L + 8 B) * 8 ns
(L = captured length incl. FCS, 8 B PHY header, 1 Gb/s); recorded statistics; RLC replay.
The instrumentation's logs are joined to PCAP by payload identity (EtherType, PCP, VID,
FNV-1a 64 of the payload bytes, recomputed from the captured bytes). Integer ps, no tolerance.
"""
import csv
import hashlib
import os
import struct
import sys
from collections import Counter, defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcapng  # noqa: E402

OUT = sys.argv[1]
M2S0_HASHES = sys.argv[2]
RUNS = os.path.join(OUT, "runs")
NS = 1000
MS = 1000 * 1000 * NS
S = 1000 * MS
END = 5 * S
PROP = 50 * NS
IFG = 96 * NS
TT_ID = {"nwTt": 1, "dsTt": 2}
# direction: TT_in, TT_out, source station, destination station, 5G ingress port, 5G egress port
DIRS = {"DL": ("nwTt", "dsTt", "listener", "talker", ("upf", 1), ("ue[0]", 0)),
        "UL": ("dsTt", "nwTt", "talker", "listener", ("ue[0]", 0), ("upf", 1))}
ROWS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7")
rows = []


def add(check, detail, ok):
    rows.append({"check": check, "detail": detail, "ok": bool(ok)})


def ps(s):
    return pcapng.simtime_ps(s) if s not in ("", None) else None


def dur(length):
    return (length + 8) * 8 * NS


def fmt(p):
    return f"{p / NS:.3f} ns"


# ---------------------------------------------------------------------------------------
class Run:
    def __init__(self, config, rep=0):
        self.config, self.rep = config, rep
        base = os.path.join(RUNS, config)
        self.pdir = os.path.join(base, "pcap", f"{config}-{rep}")
        self.ldir = os.path.join(base, "m2log", f"{config}-{rep}")
        self._p = {}

    def pcap(self, node, idx):
        if (node, idx) not in self._p:
            self._p[(node, idx)] = pcapng.read(os.path.join(self.pdir, f"M1Bridge.{node}.pcapRecorder[{idx}].pcapng"))
        return self._p[(node, idx)]

    def eth(self, node, idx, direction):
        """[(t_ps, key, frame dict, captured length)] in capture order"""
        out = []
        for p in self.pcap(node, idx):
            if p["dir"] == direction:
                f = pcapng.ethernet(p["data"])
                out.append((p["t_ps"], ident(f), f, len(p["data"])))
        return out

    def log(self, node, port, role, port_log=False):
        path = os.path.join(self.ldir, f"M1Bridge.{node}.eth[{port}].measurementLayer.{role}{'.port' if port_log else ''}.csv")
        if not os.path.exists(path):
            return None
        with open(path) as fh:
            return [r for r in csv.DictReader(fh) if r["event"] != "selftest"]

    def selftest(self):
        out = []
        if os.path.isdir(self.ldir):
            for name in sorted(os.listdir(self.ldir)):
                with open(os.path.join(self.ldir, name)) as fh:
                    out += [(name, r["note"]) for r in csv.DictReader(fh) if r["event"] == "selftest"]
        return out


def ident(f):
    return (f["etherType"], f["pcp"], f["vid"], pcapng.fnv1a64(f["payload"]))


def lkey(r, hashcol):
    return (int(r["etherType"]), int(r["pcp"]), int(r["vid"]), r[hashcol])


def kind(key, f=None):
    if key[0] == 0x88F7:
        return "gptp-" + {0: "Sync", 2: "PdelayReq", 3: "PdelayResp", 8: "FollowUp", 10: "PdelayRespFollowUp"}.get(
            f["payload"][0] & 0x0F if f else -1, "other")
    return f"pcp{key[1]}" if key[1] >= 0 else "untagged"


_csv = {}


def stats(config):
    if config not in _csv:
        d = pd.read_csv(os.path.join(RUNS, config + ".csv"), low_memory=False)
        d = d[d.run.notna()].copy()
        d["rep"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
        d["mod"] = d.module.fillna("").str.replace("M1Bridge.", "", regex=False)
        _csv[config] = d
    return _csv[config]


def vec(config, rep, mod, name):
    d = stats(config)
    r = d[(d.type == "vector") & (d.rep == rep) & (d["mod"] == mod) & (d.name == name)]
    if len(r) != 1 or not isinstance(r.vectime.iloc[0], str):
        return []
    return list(zip(map(float, r.vectime.iloc[0].split()), map(float, r.vecvalue.iloc[0].split())))


def scalar(config, rep, mod, name):
    d = stats(config)
    r = d[(d.type == "scalar") & (d.rep == rep) & (d["mod"] == mod) & (d.name == name)].value
    return float(r.iloc[0]) if len(r) == 1 else float("nan")


# ---- RLC replay (method of check_o_tail.py / M2-S0) --------------------------------------
def replay(sdus, pdus):
    q, i, cut, done = [], 0, [], {}
    for t, s in pdus:
        while i < len(sdus) and sdus[i][0] <= t:
            q.append([i, int(sdus[i][1]), 0])
            i += 1
        if not q:
            return None
        h, s = q[0], int(s)
        if h[2] == 0:
            pay = h[1] if s == h[1] + 1 else s - 2
            if pay < h[1]:
                cut.append(h[0])
        else:
            pay = s - 4
        h[2] += pay
        if h[2] >= h[1]:
            q.pop(0)
            done[h[0]] = t
    return cut, done, [x[0] for x in q] + list(range(i, len(sdus)))


def rlc(config, rep, res_by_dir):
    d = stats(config)
    mods = sorted(set(d[(d.rep == rep) & d["mod"].str.contains("-um-") & d["mod"].str.endswith(".tx")]["mod"]))
    out = {}
    for m in mods:
        node = "DL" if m.startswith("gnb1.") else "UL"
        drb = int(m.split(".")[-2].rsplit("-", 1)[1])
        sdus = vec(config, rep, m, "receivedPacketFromUpperLayer:vector(packetBytes)")
        pdus = vec(config, rep, m, "sentPduSize:vector")
        r = replay(sdus, pdus)
        res = res_by_dir[node]
        on_drb = [k for k, _ in sorted(res["P"].items(), key=lambda x: x[1][0]) if (2 if k[1] == 5 else 1) == drb]
        sizes = Counter(int(s) - (len(res["P"][k][1]["payload"]) + (18 if k[1] >= 0 else 14)) for (t, s), k in zip(sdus, on_drb))
        if r is None or len(sizes) != 1 or len(sdus) > len(on_drb):
            out[(node, drb)] = {"ok": False}
            continue
        cut, done, left = r
        out[(node, drb)] = {"ok": True, "cut": [on_drb[j] for j in cut], "done": {on_drb[j]: t for j, t in done.items()},
                            "left": {on_drb[j] for j in left}, "mapped": set(on_drb[:len(sdus)])}
    return out


LOST_MAC = "left the TX RLC, never delivered (MAC/radio)"
AT_TT_OUT = "at TT_out, not completely transmitted at the end"
BENIGN = {"not yet at the TX RLC (entered in the last 10 ms)", "still in the TX RLC at the end",
          "left the TX RLC in the last 10 ms (in flight)", AT_TT_OUT}


def losses(res, v_by_drb):
    """Categories for frames tagged at ingress without a final egress (t12)."""
    cat = Counter()
    for k in res["P"]:
        if k in res["O1"]:
            continue
        if k in res["O0"]:
            cat[AT_TT_OUT if k in res["pending_out"] else "at TT_out, unaccounted"] += 1
            continue
        v = v_by_drb.get(2 if k[1] == 5 else 1)
        t_in = res["P"][k][0]
        if v is None or not v["ok"]:
            cat["unattributed"] += 1
        elif k not in v["mapped"]:
            cat["not yet at the TX RLC (entered in the last 10 ms)" if t_in >= END - 10 * MS else "never reached the TX RLC"] += 1
        elif k in v["left"]:
            cat["still in the TX RLC at the end"] += 1
        elif v["done"][k] * S >= END - 10 * MS:
            cat["left the TX RLC in the last 10 ms (in flight)"] += 1
        else:
            cat[LOST_MAC] += 1
    return cat


# ---------------------------------------------------------------------------------------
def port_model(arrivals, departures, proc):
    """PCAP-only model of one TT port. arrivals: key -> arrival time on the other port (PCAP);
    departures: [(t, key, f, L)] on this port in capture order; proc: key -> measured
    processing (None = unknown). Returns key -> dict(prev, idle, P_pcap, ok_model, Q, G, X)."""
    out, prev = {}, None
    for t, k, f, L in departures:
        a = arrivals.get(k)
        x = dur(L)
        rec = {"prev": prev, "X": x, "t": t, "a": a}
        if a is not None:
            idle = prev is None or prev + IFG <= a
            rec["idle"] = idle
            rec["P_pcap"] = t - x - a if idle else None
            p = proc.get(k)
            if p is not None:
                a2 = a + p
                start = a2 if prev is None else max(a2, prev + IFG)
                rec["ok_model"] = start + x == t
                # INET 4.7: the inter-frame gap is enforced by back-pressure (the gap inserter
                # refuses frames until previous end + 96 ns), so the MAC server dequeues at
                # the start of transmission: the gap is spent in the MAC FIFO (Q) and the
                # dequeue-to-start interval G is 0 (InterpacketGapInserter.cc:109-120).
                rec["Q"] = start - a2
                rec["G"] = 0
        out[k] = rec
        prev = t
    return out


def analyse(run, dname):
    tin, tout, src, dst, gin, gout = DIRS[dname]
    prob = {c: [] for c in ROWS}
    IN, OUTB = pcapng.INBOUND, pcapng.OUTBOUND
    SRC = run.eth(src, 0, OUTB)
    PIN = run.eth(tin, 1, IN)
    T0 = run.eth(tin, 0, OUTB)
    G6 = run.eth(gin[0], gin[1], IN)
    G7 = run.eth(gout[0], gout[1], OUTB)
    O0 = run.eth(tout, 0, IN)
    O1 = run.eth(tout, 1, OUTB)
    D = run.eth(dst, 0, IN)
    for name, lst in (("source station", SRC), ("TT_in eth[1]", PIN), ("TT_in eth[0]", T0), ("5GS ingress port", G6),
                      ("5GS egress port", G7), ("TT_out eth[0]", O0), ("TT_out eth[1]", O1), ("destination station", D)):
        keys = [k for _, k, _, _ in lst]
        if len(keys) != len(set(keys)):
            prob["C1"].append(f"ambiguous identity in {name} PCAP")
        if any(not f["fcs_ok"] for _, _, f, _ in lst):
            prob["C1"].append(f"bad FCS in {name} PCAP")
    m = lambda lst: {k: t for t, k, _, _ in lst}  # noqa: E731
    pSRC, pT0, p6, p7, pO0, pO1, pD = m(SRC), m(T0), m(G6), m(G7), m(O0), m(O1), m(D)
    P = {k: (t, f, L) for t, k, f, L in PIN}
    order = {k: i + 1 for i, (_, k, _, _) in enumerate(sorted(PIN, key=lambda x: x[0]))}
    length = {k: L for _, k, _, L in PIN}

    ING = run.log(tin, 1, "ingress") or []
    RXP = [r for r in (run.log(tin, 1, "ingress", True) or []) if r["event"] == "rx"]
    TX0 = run.log(tin, 0, "egress", True) or []
    RX0 = [r for r in (run.log(tout, 0, "ingress", True) or []) if r["event"] == "rx"]
    EGM = run.log(tout, 1, "egress") or []
    TX1 = run.log(tout, 1, "egress", True) or []

    def index(lst, hashcol, what, c="C1"):
        out = {}
        for r in lst:
            k = lkey(r, hashcol)
            if k in out:
                prob[c].append(f"duplicate identity in {what}")
            out[k] = r
        return out

    iING = index(ING, "payloadHash", "ingress log")
    iRXP = index(RXP, "hash", "TT_in eth[1] rx rows")
    tx0 = [r for r in TX0 if r["event"] == "tx"]
    iTX0 = index(tx0, "hash", "TT_in eth[0] tx rows")
    iRX0 = index(RX0, "hash", "TT_out eth[0] rx rows")
    iEGM = index(EGM, "payloadHash", "TT_out eth[1] egress log")
    tx1 = [r for r in TX1 if r["event"] == "tx"]
    iTX1 = index(tx1, "hash", "TT_out eth[1] tx rows")
    pending_out = {lkey(r, "hash") for r in TX1 if r["event"] == "pending"}

    # ---- C1 completeness and accounting
    def same(a, b, what):
        if set(a) != set(b):
            prob["C1"].append(f"{what}: {len(set(a) - set(b))} extra, {len(set(b) - set(a))} missing")
    same(iING, P, "ingress log vs TT_in eth[1] PCAP")
    if any(r["event"] != "tag" for r in ING):
        prob["C1"].append(f"{sum(r['event'] != 'tag' for r in ING)} frames not tagged at ingress")
    same(iRXP, P, "TT_in eth[1] rx rows vs PCAP")
    same(iTX0, pT0, "TT_in eth[0] tx rows vs PCAP")
    same(iRX0, pO0, "TT_out eth[0] rx rows vs PCAP")
    same(iEGM, pO0, "TT_out eth[1] egress log vs TT_out eth[0] PCAP")
    same(iTX1, pO1, "TT_out eth[1] tx rows vs PCAP")
    same(pD, pO1, "destination station PCAP vs TT_out eth[1] PCAP")
    if set(pO1) & pending_out or not pending_out <= set(pO0):
        prob["C1"].append("pending rows inconsistent with PCAP")
    for name, lst in (("TT_in eth[0] tx", tx0), ("TT_out eth[0] rx", RX0), ("TT_out eth[1] tx", tx1)):
        bad = [r for r in lst if r["tagged"] != "1" or lkey(r, "hash") not in iING
               or r["frameId"] != iING[lkey(r, "hash")]["frameId"]]
        if bad:
            prob["C1"].append(f"{len(bad)} {name} rows without the ingress identity")
    if set(pO1) - set(P):
        prob["C1"].append("frames transmitted on TT_out eth[1] that never entered TT_in")
    res = {"name": dname, "prob": prob, "P": P, "O0": pO0, "O1": pO1, "pending_out": pending_out,
           "n_in": len(P), "n_out": len(pO1), "n_pending": len(pending_out)}

    # ---- C2 ingress event
    dev2, dev3 = {}, {}
    pf = defaultdict(lambda: {c: True for c in ROWS})
    for k, r in iING.items():
        if k not in P:
            continue
        t1 = ps(r["ingressTime"]) if r["event"] == "tag" else None
        if t1 is not None:
            dev2[k] = t1 - P[k][0]
        if t1 is None or t1 != P[k][0]:
            prob["C2"].append(("ingressTime - PCAP in", (t1 - P[k][0]) if t1 is not None else "untagged"))
            pf[k]["C2"] = False
        x = iRXP.get(k)
        if x is None or ps(x["tRxEnd"]) != P[k][0] or ps(x["t"]) != P[k][0]:
            prob["C2"].append(("receptionEnded / slot - PCAP in", "missing" if x is None else ps(x["tRxEnd"]) - P[k][0]))
            pf[k]["C2"] = False
        elif x["tRxStart"] and ps(x["tRxEnd"]) - ps(x["tRxStart"]) != dur(length[k]):
            prob["C2"].append(("reception duration - (L+8)*8 ns", ps(x["tRxEnd"]) - ps(x["tRxStart"]) - dur(length[k])))
            pf[k]["C2"] = False
        if pSRC.get(k) is None or P[k][0] - pSRC[k] != PROP:
            prob["C2"].append(("PCAP in - station out", None if k not in pSRC else P[k][0] - pSRC[k]))
            pf[k]["C2"] = False
    if not any(r["event"] == "tag" for r in ING):
        prob["C2"].append(("no tagged frame", "-"))

    # ---- C3 final-egress event, C5 complete residence
    for r in tx1:
        k = lkey(r, "hash")
        t12 = ps(r["egressTime"])
        if k in pO1:
            dev3[k] = t12 - pO1[k]
        if k not in pO1 or t12 != pO1[k] or pD.get(k) is None or pD[k] - PROP != t12:
            prob["C3"].append(("egressTime - PCAP out", (t12 - pO1[k]) if k in pO1 else "no such frame"))
            pf[k]["C3"] = False
        ing = iING.get(k)
        t1 = ps(ing["ingressTime"]) if ing is not None and ing["event"] == "tag" else None
        resid = ps(r["residence"])
        if t1 is None or resid is None or resid != t12 - ps(r["ingressTime"]) or k not in pO1 or k not in P \
                or resid != pO1[k] - P[k][0]:
            prob["C5"].append(("residence - PCAP(out) + PCAP(in)", (resid - (pO1[k] - P[k][0])) if resid is not None and k in pO1 and k in P else "n/a"))
            pf[k]["C5"] = False
    if not tx1:
        for c in ("C3", "C5", "C4", "C6"):
            prob[c].append(("no final egress row", "-"))

    # ---- C4 pairing: rows in transmission order carry the identity of the PCAP frame in that position
    o1_order = [k for _, k, _, _ in O1]
    for i, r in enumerate(tx1):
        k = lkey(r, "hash")
        okp = i < len(o1_order) and o1_order[i] == k and r["txHash"] == r["hash"] and k in order \
            and int(r["frameId"] or -1) == order[k] and int(r["ingressTtId"] or -1) == TT_ID[tin]
        if not okp:
            prob["C4"].append(("row identity vs PCAP frame in the same transmission position", "mismatch"))
            pf[k]["C4"] = False

    # ---- C6 decomposition
    proc_in, proc_out = {}, {}
    for k, r in iTX0.items():
        if k in iING and iING[k]["event"] == "tag":
            proc_in[k] = ps(r["tSlot"]) - ps(iING[k]["ingressTime"])
    for k, r in iTX1.items():
        if k in iRX0:
            proc_out[k] = ps(r["tSlot"]) - ps(iRX0[k]["tRxEnd"])
    mi = port_model({k: v[0] for k, v in P.items()}, T0, proc_in)
    mo = port_model(pO0, O1, proc_out)
    sub = Counter()
    nq = 0
    res["idle_in"] = sum(1 for v in mi.values() if v.get("idle"))
    res["idle_out"] = sum(1 for v in mo.values() if v.get("idle"))
    for r in tx1:
        k = lkey(r, "hash")
        fails = []
        try:
            t1 = ps(iING[k]["ingressTime"])
            a, b = iTX0[k], iRX0[k]
            t2, t3, t4, t5 = ps(a["tSlot"]), ps(a["tDequeue"]), ps(a["tTxStart"]), ps(a["egressTime"])
            t8 = ps(b["tRxEnd"])
            t9, t10, t11, t12 = ps(r["tSlot"]), ps(r["tDequeue"]), ps(r["tTxStart"]), ps(r["egressTime"])
            vi, vo = mi[k], mo[k]
            Pin, Qin, Gin, Xin = t2 - t1, t3 - t2, t4 - t3, t5 - t4
            Pout, Qout, Gout, Xout = t9 - t8, t10 - t9, t11 - t10, t12 - t11
            B = t8 - t5
            Lin, Sg, Lout = p6[k] - pT0[k], p7[k] - p6[k], pO0[k] - p7[k]
            # processing: measured; independently, PCAP gives it exactly whenever the port was idle
            if vi["idle"] and vi["P_pcap"] != Pin:
                fails.append("P_in vs PCAP (idle port)")
            if vo["idle"] and vo["P_pcap"] != Pout:
                fails.append("P_out vs PCAP (idle port)")
            if Pin != 0 or Pout != 0:
                fails.append("processing not 0 in the pass-through configuration")
            if not vi.get("ok_model") or Qin != vi["Q"] or Gin != vi["G"]:
                fails.append("TT_in queue (incl. inter-frame gap) / dequeue-to-start vs PCAP model")
            if not vo.get("ok_model") or Qout != vo["Q"] or Gout != vo["G"]:
                fails.append("TT_out queue (incl. inter-frame gap) / dequeue-to-start vs PCAP model")
            if Xin != vi["X"] or t5 != pT0[k]:
                fails.append("TT_in transmission vs (L+8)*8 ns / PCAP")
            if Xout != vo["X"] or t12 != pO1[k]:
                fails.append("TT_out transmission vs (L+8)*8 ns / PCAP")
            if Lin != PROP or Lout != PROP:
                fails.append("5GS cables != 50 ns")
            if t8 != pO0[k] or B != Lin + Sg + Lout:
                fails.append("5GS block vs PCAP")
            total = Pin + Qin + Gin + Xin + B + Pout + Qout + Gout + Xout
            if total != t12 - t1 or ps(r["residence"]) != total:
                fails.append("sum of intervals != R")
            if not (t12 - t9 >= Xout > 0):
                fails.append("t12 - t9 >= X_out > 0")
            if Qin or Gin or Qout or Gout:
                nq += 1
            res.setdefault("iv", []).append((Pin, Qin, Gin, Xin, Lin, Sg, Lout, Pout, Qout, Gout, Xout, t12 - t1, t12 - t9))
        except (KeyError, TypeError):
            fails.append("missing event")
        for f in fails:
            sub[f] += 1
        if fails:
            pf[k]["C6"] = False
    if sub:
        prob["C6"].append(("sub-checks failing", dict(sub)))
    res["queued"] = nq

    # ---- C7 partial interval kept (M2-S0 A1-A4 on the M2-S0-format logs)
    for k, r in iEGM.items():
        ing = iING.get(k)
        ok = r["event"] == "recover" and ing is not None and ing["event"] == "tag" and \
            (r["frameId"], r["ingressTime"], r["ingressTtId"]) == (ing["frameId"], ing["ingressTime"], ing["ingressTtId"])
        if ok:
            ti, te = ps(r["ingressTime"]), ps(r["t"])
            ok = k in P and k in pO0 and ti == P[k][0] and int(r["frameId"]) == order[k] and \
                int(r["ingressTtId"]) == TT_ID[tin] and te == pO0[k] and te - ti == pO0[k] - P[k][0]
        if not ok:
            prob["C7"].append(("M2-S0 A1-A4", "fail"))
            pf[k]["C7"] = False
    if not any(r["event"] == "recover" for r in EGM):
        prob["C7"].append(("no recovered frame", "-"))
    res["pf"] = pf
    res.update(dev2=dev2, dev3=dev3, length=length, pO0=pO0, o1_order=o1_order, tx1_keys=[lkey(r, "hash") for r in tx1])
    res["kinds"] = {k: kind(k, P[k][1]) for k in P}
    return res


def describe(p):
    if not p:
        return "none"
    c = Counter()
    for x in p:
        if isinstance(x, tuple):
            what, v = x
            c[f"{what}: {fmt(v) if isinstance(v, int) else v}"] += 1
        else:
            c[x] += 1
    return "; ".join(f"{v}x {k}" for k, v in c.most_common(6)) + (" ..." if len(c) > 6 else "")


def evaluate(cfg, rep=0):
    run = Run(cfg, rep)
    rd = {d: analyse(run, d) for d in DIRS}
    rc = rlc(cfg, rep, rd)
    for d, r in rd.items():
        r["loss"] = losses(r, {drb: v for (dd, drb), v in rc.items() if dd == d})
        if not set(r["loss"]) <= BENIGN | {LOST_MAC}:
            r["prob"]["C1"].append(("unaccounted frames", dict(r["loss"])))
    return run, rd, rc


def verdict(r):
    return {c: not r["prob"][c] for c in ROWS}


def audit(run):
    tagged = frames = 0
    for node in ("talker", "listener"):
        for role in ("ingress", "egress"):
            lg = run.log(node, 0, role)
            frames += len(lg)
            tagged += sum(1 for r in lg if r["note"] != "allLevelTags=0" or r["regions"] != "0")
    return frames, tagged


# ======================================================================================
# C14 structure census and self-tests
census, sig_ok, counts_ok = Counter(), True, True
for cfg in ("M2S1-probe", "M2S1-probe-frag", "M2S1-probe-load"):
    run = Run(cfg, 0)
    for node, port in (("nwTt", 1), ("dsTt", 1), ("nwTt", 0), ("dsTt", 0), ("talker", 0), ("listener", 0)):
        idx = port if node.endswith("Tt") else 0
        for role in ("ingress", "egress"):
            lg = run.log(node, port, role)
            for r in lg:
                sig_ok &= r["event"] == "probe" and r["note"] == "allLevelTags=0"
                census[(f"{node}.eth[{port}] {'RX' if role == 'ingress' else 'TX'}", r["signature"].split(" back=")[0],
                        r["signature"].split(": ", 1)[1])] += 1
            n_p = sum(1 for p in run.pcap(node, idx) if p["dir"] == (pcapng.INBOUND if role == "ingress" else pcapng.OUTBOUND))
            counts_ok &= (len(lg) == n_p) if role == "ingress" else (len(lg) >= n_p)
with open(os.path.join(OUT, "census.txt"), "w") as fh:
    fh.write("Chunk structure of every frame at the measurement-layer slots (M2S1-probe, -probe-frag, -probe-load, seed 0)\n")
    fh.write("count  slot  front offset  data-part chunks\n")
    for (slot, front, s), n in sorted(census.items()):
        fh.write(f"{n:6d}  {slot:20s} {front:9s} {s}\n")
st = Run("M2S1", 0).selftest()
st_struct = [n for f, n in st if not f.endswith(".port.csv")]
st_pair = [n for f, n in st if f.endswith(".port.csv")]
add("C14 structure and self-tests: every frame at every slot (both ports of both translators, stations; base, N3 "
    "fragmentation, load) has the supported structure; structure/tag self-test and egress-pairing self-test pass",
    f"{sum(census.values())} frames, {len(census)} slot/structure combinations (census.txt); probe counts = PCAP counts: "
    f"{counts_ok}; structure self-test {sum(n.startswith('PASS') for n in st_struct)}/{len(st_struct)}, pairing self-test "
    f"{sum(n.startswith('PASS') for n in st_pair)}/{len(st_pair)} (M2S1 seed 0, both processors of nwTt eth[1])",
    sig_ok and counts_ok and len(census) > 0 and len(st_struct) == 20 and len(st_pair) == 20
    and all(n.startswith("PASS") for n in st_struct + st_pair))

# ---- C1-C7 on M2S1 seeds 0-9 ------------------------------------------------------------
agg = {d: {c: [] for c in ROWS} for d in DIRS}
tot = {d: Counter() for d in DIRS}
loss = {d: Counter() for d in DIRS}
cls = {d: defaultdict(lambda: [0, 0]) for d in DIRS}
cut_n = cut_ok = queued_n = queued_ok = 0
ivs = {d: [] for d in DIRS}
for rep in range(10):
    run, rd, rc = evaluate("M2S1", rep)
    for d, r in rd.items():
        for c in ROWS:
            agg[d][c] += r["prob"][c]
        tot[d].update({"in": r["n_in"], "out": r["n_out"], "pending": r["n_pending"], "queued": r["queued"],
                       "idle_in": r["idle_in"], "idle_out": r["idle_out"]})
        loss[d].update(r["loss"])
        ivs[d] += r.get("iv", [])
        for k in r["O1"]:
            ok = all(r["pf"][k].values())
            cls[d][r["kinds"][k]][0] += 1
            cls[d][r["kinds"][k]][1] += ok
    for (d, drb), v in rc.items():
        for k in v.get("cut", []):
            if k in rd[d]["O1"]:
                cut_n += 1
                cut_ok += all(rd[d]["pf"][k].values())

TXT = {
    "C1": "C1 completeness/accounting {d} (M2S1, seeds 0-9): every frame received at the TT_in TSN port is tagged; each "
          "port log has exactly one row per PCAP frame; every tagged frame without a final egress is accounted for",
    "C2": "C2 ingress event {d}: ingressTime = receptionEnded time = PCAP in at TT_in eth[1], exactly; = station PCAP out "
          "+ 50 ns; reception duration (streaming receiver) = (L+8)*8 ns",
    "C3": "C3 final-egress event {d}: logged egress time = PCAP out at TT_out eth[1] (transmissionEnded) = destination "
          "station PCAP in - 50 ns, exactly",
    "C4": "C4 frame pairing {d}: final-egress rows, in transmission order, carry the identity (payload hash, frame id = "
          "ingress arrival ordinal, TT_in id) of the PCAP frame in the same position; transmitted hash = enqueued hash",
    "C5": "C5 complete observed residence {d}: R = t12 - t1 (module) = PCAP out (TT_out eth[1]) - PCAP in (TT_in eth[1]), "
          "exactly",
    "C6": "C6 decomposition {d}: measured P, Q, G, X at both translators and the 5GS block; P equals the PCAP value on "
          "every idle-port frame and is 0; Q (MAC FIFO incl. inter-frame gap), G (dequeue to start, 0) and X equal the PCAP port model; B = 50 ns + S + 50 ns; sum = R; "
          "t12 - t9 >= X_out > 0",
    "C7": "C7 partial interval kept {d}: M2-S0 rows A1-A4 (recovery at t8/t9, R5 = t8 - t1) on the same runs",
}
for d in DIRS:
    t = tot[d]
    iv = ivs[d]

    def rng(i):
        v = [x[i] for x in iv]
        return f"{min(v) / NS:.0f}-{max(v) / NS:.0f} ns" if v else "-"
    det = {
        "C1": f"{t['in']} received, {t['out']} with final egress, {t['pending']} at TT_out still queued/in transmission "
              f"at the end; not completed: {dict(loss[d])}",
        "C5": f"{len(iv)} frames, R {min(x[11] for x in iv) / MS:.6f}-{max(x[11] for x in iv) / MS:.6f} ms" if iv else "",
        "C6": f"{len(iv)} frames; P_in {rng(0)}, Q_in {rng(1)}, G_in {rng(2)}, X_in {rng(3)}; cables {rng(4)} / {rng(6)}; "
              f"S {min(x[5] for x in iv) / MS:.6f}-{max(x[5] for x in iv) / MS:.6f} ms; P_out {rng(7)}, Q_out {rng(8)}, "
              f"G_out {rng(9)}, X_out {rng(10)}; t12 - t9 {rng(12)}; frames that waited in a translator MAC FIFO (incl. inter-frame gap): "
              f"{t['queued']}; idle-port frames giving an independent PCAP value of P: {t['idle_in']} (TT_in), "
              f"{t['idle_out']} (TT_out)" if iv else "",
    }
    for c in ROWS:
        add(TXT[c].format(d=d), (det.get(c, "") + "; " if det.get(c) else "") + f"problems: {describe(agg[d][c])}",
            not agg[d][c] and (c != "C1" or set(loss[d]) <= BENIGN))

det8, ok8 = [], True
for d in DIRS:
    det8.append(f"{d}: " + ", ".join(f"{c} {n}/{t_}" for c, (t_, n) in sorted(cls[d].items())))
    ok8 &= all(n == t_ and t_ > 0 for t_, n in cls[d].values())
need = {"DL": {"pcp0", "pcp5", "gptp-Sync", "gptp-FollowUp", "gptp-PdelayResp", "gptp-PdelayRespFollowUp"},
        "UL": {"pcp0", "pcp5", "gptp-PdelayReq"}}
ok8 &= all(need[d] <= set(cls[d]) for d in DIRS)
qn = sum(tot[d]["queued"] for d in DIRS)
add("C8 coverage (M2S1, seeds 0-9): C2-C7 hold per frame for every frame class (both DRBs, every gPTP message type), "
    "every RLC SDU cut and reassembled, and every frame that waited in a translator MAC FIFO (queueing or inter-frame gap)",
    " | ".join(det8) + f" (frames passing / with final egress) | RLC-cut SDUs with final egress: {cut_n}, passing: "
    f"{cut_ok} | frames that waited in a translator MAC FIFO (incl. inter-frame gap): {qn} (all included above)",
    ok8 and cut_n > 0 and cut_ok == cut_n and qn > 0)


# ---- C9 fragmentation --------------------------------------------------------------------
def n3_ipv4(run):
    frags, whole = defaultdict(int), []
    for p in run.pcap("upf", 0):
        b = p["data"]
        off = 5 if b[1:3] == b"\xff\x03" else 3
        if struct.unpack(">H", b[off - 2: off])[0] != 0x0021:
            continue
        ip = b[off:]
        ff = struct.unpack(">H", ip[6:8])[0]
        if (ff & 0x2000) or (ff & 0x1FFF):
            frags[(ip[12:16], ip[16:20], ip[4:6], ip[9])] += 1
        else:
            whole.append(struct.unpack(">H", ip[2:4])[0])
    return frags, whole


runf, rf, _ = evaluate("M2S1-frag")
frags, whole = n3_ipv4(runf)
okf = all(verdict(r)[c] for r in rf.values() for c in ROWS[:6]) and all(set(r["loss"]) <= BENIGN for r in rf.values())
add("C9 N3 fragmentation (M2S1-frag, seed 0): C1-C6 hold in both directions; every GTP-U datagram above the 128 B MTU "
    "fragmented on N3",
    " | ".join(f"{d}: {r['n_out']} with final egress, C1-C6 {[c for c in ROWS[:6] if not verdict(r)[c]] or 'all pass'}"
               for d, r in rf.items()) +
    f" | N3: {len(frags)} datagrams in {sum(frags.values())} fragments, {len(whole)} unfragmented "
    f"({min(whole)}-{max(whole)} B)", okf and frags and all(n >= 2 for n in frags.values()) and all(x <= 128 for x in whole))

# ---- C10 load -----------------------------------------------------------------------------
det10, ok10, mac = [], True, {}
for cfg in ("M2S1-load", "M2S1-load-harq16"):
    _, rl, _ = evaluate(cfg)
    mac[cfg] = sum(r["loss"][LOST_MAC] for r in rl.values())
    for d, r in rl.items():
        ok10 &= all(verdict(r)[c] for c in ROWS[:6])
        det10.append(f"{cfg} {d}: {r['n_in']} in, {r['n_out']} with final egress, waited in a translator MAC FIFO "
                     f"{r['queued']}, not completed {dict(r['loss'])}, failing {[c for c in ROWS[:6] if not verdict(r)[c]] or 'none'}")
add("C10 load (saturating PCP 0 background both directions): C1-C6 hold for every frame with a final egress; with 5 HARQ "
    "processes frames are lost after the TX RLC (M1 L1), with 16 none",
    " | ".join(det10), ok10 and mac["M2S1-load"] > 0 and mac["M2S1-load-harq16"] == 0)


# ---- C11 wire, C12 statistics, C15a M2-S0 records reproduced --------------------------------
def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


det11, ok11 = [], True
for a, b in (("M2S1", "M2S1-off"), ("M2S1-load", "M2S1-load-off")):
    da, db = Run(a).pdir, Run(b).pdir
    fa = sorted(os.listdir(da))
    same = [f for f in fa if os.path.exists(os.path.join(db, f)) and sha(os.path.join(da, f)) == sha(os.path.join(db, f))]
    ok11 &= len(fa) == 9 and len(same) == 9 and sorted(os.listdir(db)) == fa
    det11.append(f"{a} vs {b}: {len(same)}/{len(fa)} PCAP files byte-identical")
add("C11 wire unchanged: all 9 PCAP files (stations, both translator ports, UPF dnEth, UE eth[0], N3) byte-identical with "
    "and without the instrumentation", " | ".join(det11), ok11)


def stat_equal(a, b):
    da, db = stats(a), stats(b)
    da, db = da[da.rep == 0], db[db.rep == 0]
    ours = lambda m: ".measurementLayer" in m  # noqa: E731
    va = {(r.mod, r.name): (r.vectime, r.vecvalue) for r in da[da.type == "vector"].itertuples() if not ours(r.mod)}
    vb = {(r.mod, r.name): (r.vectime, r.vecvalue) for r in db[db.type == "vector"].itertuples()}
    sa = {(r.mod, r.name): r.value for r in da[da.type == "scalar"].itertuples() if not ours(r.mod)}
    sb = {(r.mod, r.name): r.value for r in db[db.type == "scalar"].itertuples()}
    vs = sum(1 for k in va if k in vb and va[k] == vb[k])
    ss = sum(1 for k in sa if k in sb and (sa[k] == sb[k] or (sa[k] != sa[k] and sb[k] != sb[k])))
    return len(va), len(vb), vs, len(sa), len(sb), ss


det12, ok12 = [], True
for a, b in (("M2S1", "M2S1-off"), ("M2S1-load", "M2S1-load-off")):
    nva, nvb, vs, nsa, nsb, ss = stat_equal(a, b)
    sa0 = stats(a)[(stats(a).type == "vector") & (stats(a).rep == 0)]
    clockv = sum(1 for m_ in sa0["mod"] if m_.startswith("talker.clock") or ".gptp" in m_)
    ok12 &= nva == nvb == vs and nsa == nsb == ss and nva > 0
    det12.append(f"{a} vs {b}: vectors {vs}/{nva} identical ({nvb} in control; {clockv} gPTP/clock vectors among them), "
                 f"scalars {ss}/{nsa} identical ({nsb} in control)")
add("C12 no side effects: every recorded vector and scalar identical with and without the instrumentation (the layers' "
    "own excluded): application delays, gPTP and slave clock, per-DRB RLC/PDCP/MAC", " | ".join(det12), ok12)

det13, ok13 = [], True
for cfg, reps in (("M2S1", range(10)), ("M2S1-frag", [0]), ("M2S1-load", [0]), ("M2S1-load-harq16", [0])):
    fr = tg = 0
    for rep in reps:
        f_, t_ = audit(Run(cfg, rep))
        fr += f_
        tg += t_
    ok13 &= tg == 0 and fr > 0
    det13.append(f"{cfg}: {fr} station frames audited, {tg} with a tag")
add("C13 containment: no frame at either station carries a TtTimestampTag at any chunk level", " | ".join(det13), ok13)

recorded = {}
with open(M2S0_HASHES) as fh:
    for line in fh:
        h, p = line.split(None, 1)
        recorded[p.strip().lstrip("./")] = h
det15, ok15 = [], True
for s1, s0 in (("M2S1", "M2S0"), ("M2S1-load", "M2S0-load")):
    run = Run(s1)
    n = same = 0
    for sub, d in (("pcap", run.pdir), ("m2log", run.ldir)):
        for f in sorted(os.listdir(d)):
            key = f"{s0}/{sub}/{s0}-0/{f}"
            if key not in recorded:
                continue        # files that do not exist in M2-S0 (new PCAP ports, eth[0] layers, port logs)
            n += 1
            same += sha(os.path.join(d, f)) == recorded[key]
    expect = sum(1 for k in recorded if k.startswith(f"{s0}/pcap/{s0}-0/") or k.startswith(f"{s0}/m2log/{s0}-0/"))
    ok15 &= n == same == expect and n > 0
    det15.append(f"{s1} seed 0 vs recorded {s0}: {same}/{n} files hash-identical ({expect} recorded)")
add("C15a M2-S0 reproduced with the M2-S1 instrumentation on: every PCAP file and M2-S0-format per-frame log of the "
    "M2-S0 recorded run (raw-outputs.sha256 at ad47a8a) is byte-identical in the M2-S1 run", " | ".join(det15), ok15)

# ---- negative controls ---------------------------------------------------------------------
NCS = {"M2S1-nc-ingress-offset": {"C2-DL", "C5-DL", "C6-DL", "C7-DL"},
       "M2S1-nc-ingress-rxstart": {"C2-DL", "C5-DL", "C6-DL", "C7-DL"},
       "M2S1-nc-pairing": {"C3-DL", "C4-DL", "C5-DL", "C6-DL"},
       "M2S1-nc-egress-enqueue": {"C3-DL", "C5-DL", "C6-DL"},
       "M2S1-nc-egress-txstart": {"C3-DL", "C5-DL", "C6-DL"},
       "M2S1-nc-nostrip": {"C13"}}


def signature(cfg, rd):
    """The deviation each negative control must produce, exactly, on every affected frame."""
    r = rd["DL"]
    if cfg.endswith("ingress-offset"):
        bad = [k for k, v in r["dev2"].items() if v != NS]
        return not bad and len(r["dev2"]) == r["n_in"], f"ingressTime - PCAP in = +1 ns on {len(r['dev2']) - len(bad)}/{r['n_in']} frames"
    if cfg.endswith("ingress-rxstart"):
        bad = [k for k, v in r["dev2"].items() if v != -dur(r["length"][k])]
        return not bad and len(r["dev2"]) == r["n_in"], \
            f"ingressTime - PCAP in = -(L+8)*8 ns of that frame on {len(r['dev2']) - len(bad)}/{r['n_in']} frames"
    if cfg.endswith("pairing"):
        o, t = r["o1_order"], r["tx1_keys"]
        ok = len(o) == len(t) > 1 and all(t[i] == o[i - 1] for i in range(len(t)))
        return ok, f"row i carries the identity of the frame transmitted in position i-1 (cyclic): {ok}"
    if cfg.endswith("egress-enqueue"):
        bad = [k for k, v in r["dev3"].items() if v != -(r["O1"][k] - r["pO0"][k]) or v == 0]
        return not bad and len(r["dev3"]) == r["n_out"], \
            f"egress - PCAP out = -(PCAP out - PCAP in at TT_out), never 0, on {len(r['dev3']) - len(bad)}/{r['n_out']} frames"
    if cfg.endswith("egress-txstart"):
        bad = [k for k, v in r["dev3"].items() if v != -dur(r["length"][k])]
        return not bad and len(r["dev3"]) == r["n_out"], \
            f"egress - PCAP out = -(L+8)*8 ns of that frame on {len(r['dev3']) - len(bad)}/{r['n_out']} frames"
    return True, "-"


for i, (cfg, target) in enumerate(NCS.items(), 1):
    run, rd, _ = evaluate(cfg)
    failed, info = set(), []
    for d, r in rd.items():
        for c in ROWS:
            if r["prob"][c]:
                failed.add(f"{c}-{d}")
                info.append(f"{c}-{d}: {describe(r['prob'][c])}")
    if audit(run)[1] != 0:
        failed.add("C13")
        info.append(f"C13: {audit(run)[1]} of {audit(run)[0]} station frames tagged")
    sig_ok, sig = signature(cfg, rd)
    add(f"N{i} {cfg}: fails exactly {sorted(target)}, with the expected signature",
        f"failed: {sorted(failed)}; signature: {sig} -- " + " | ".join(info)[:1200], failed == target and sig_ok)

for r in rows:
    print(f"{'PASS' if r['ok'] else 'FAIL':4}  {r['check']}")
    print(f"      {r['detail']}")
print()
print("OVERALL:", "PASS" if all(r["ok"] for r in rows) else "FAIL", f"({sum(r['ok'] for r in rows)}/{len(rows)})")
