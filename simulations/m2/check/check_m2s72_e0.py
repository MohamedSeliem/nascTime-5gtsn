#!/usr/bin/env python3
"""M2-S7.2a Stage 5, E0 capacity calibration checker (authorisation 2026-11-03 11:35; protocol, checker specification
and predictions: results/M2-S7.2a-e0-protocol.md, committed before the runs).

    check_m2s72_e0.py <OUT>                       full E0 check of <OUT>/runs -> stdout (m2s72.sh e0check:
                                                  <OUT>/e0-check.txt), per-run metrics -> <OUT>/e0-metrics.csv
    check_m2s72_e0.py quick <runs> <cfg>          runner's escalation-stop proxy: fraction of cohort GM Syncs not
                                                  received by DS-TT 0 by T_end (an upper bound of the censored fraction)
    check_m2s72_e0.py nonpert <runs> <cfgA> <cfgB>  MAC-log non-perturbation comparison of two runs

Gate scoping (review item 3, declared in the protocol before the batch):
  F0-1        gated only for the configs declared loss-free (LOSS_FREE); elsewhere reported as "F0-1 (info)"
  Q8          every run: every GM Sync / Follow_Up (domain 0) gets exactly one packet-level fate with its last confirmed
              location; UNEXPLAINED (or a replay model that does not reproduce the observed deliveries) fails
  Q8-x        every run: MAC-log evidence consistent with the recorded vectors (same run, same counts)
  strict I-2  no idle config in E0: reported as "I-2 strict (info)"; I-2H gates (loaded)
  EOR         gated only where bounded latency is verified (L_max <= 2 Sync intervals and no sustained backlog growth on
              the gPTP DRB); else NOT APPLICABLE and Q8 censoring governs
  I-5 / AR    NOT APPLICABLE (E0 is N = 1: there is no N = 1 reference of a different N)
  H-cov/H-nv  NOT APPLICABLE (no residence heterogeneity is declared at N = 1)
  I-4 stream  NOT APPLICABLE (needs N = 2 and N = 4)
  M2/M3/M3d/M4, I-1, I-3, I-4, F0-2..F0-8, F0-7d  every run, unchanged oracles
  CFG-rate    every run: the load sources produce exactly the configured frames (listener / talker egress logs)
Missing or inapplicable evidence is a row with status NOT APPLICABLE or NOT EVALUATED, never a silent PASS.
"""
import csv
import gzip
import hashlib
import math
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_b as B  # noqa: E402
import check_m2s72_i2h as I  # noqa: E402
import gate_m2s71_p0 as G  # noqa: E402
sys.argv = _argv
import m2s71_lib as L  # noqa: E402
import m2s72_maclog as ML  # noqa: E402
import m2s72_runs as R  # noqa: E402
import m2s72_s6 as V  # noqa: E402

rows = B.rows
S, MS, US, NS = 10 ** 12, 10 ** 9, 10 ** 6, 10 ** 3
SYNC, FU = 0, 8
INF = float("inf")
SYNC_INTERVAL = 125 * MS
T_COHORT = 10 * S
B_RES = 5500 * US                     # exploratory deadline: Sync residence > 5.5 ms
OPTS = ("q0", "qdu")
FACTORS = (1, 2, 4, 8)
LOSS_FREE = {"M2S72-E0-q0-f1", "M2S72-E0-qdu-f1"}         # declared before the batch (protocol §4)
TWIN_OPT = "q0"      # the runner runs the twin M2S72-E0NL-q0-f<F> of the highest Q-0 factor executed


def twin(runs):
    for f in sorted(FACTORS, reverse=True):
        a, b = f"M2S72-E0-{TWIN_OPT}-f{f}", f"M2S72-E0NL-{TWIN_OPT}-f{f}"
        if os.path.isdir(os.path.join(runs, b)):
            return a, b
    return None
NA, NE = "NOT APPLICABLE", "NOT EVALUATED"
INFO = I.INFO + ("F0-1 (info)",)
LOAD_LEN = 1400
LOAD_INTERVAL = {f: Fraction(250 * US, f) for f in FACTORS}  # DL, per factor (UE 0 only, N = 1)
UL_INTERVAL = 250 * US
DL_START, UL_START = 300500 * MS // 1000, 100500 * MS // 1000
THRESH = {"res_p99": (2750 * US, 5500 * US, 11000 * US), "max_e": (500 * NS, 1000 * NS, 2000 * NS), "p_used": (0.95, 0.99, 0.999)}


def add(row, run, status, detail):
    """status: True / False (gated PASS / FAIL) or NA / NE (explicitly not applicable / not evaluated)"""
    rows.append((row, run, ("PASS" if status else "FAIL") if isinstance(status, bool) else status, detail))


def cfgs():
    return [(f"M2S72-E0-{o}-f{f}", o, f) for f in FACTORS for o in OPTS]


def first(fr, d):
    out = {}
    for f in fr:
        if f["dir"] == d and f["type"] in (SYNC, FU) and f["dom"] == 0:
            out.setdefault((f["type"], f["seq"]), f)
    return out


def pct(vals, q):
    return L.pct(vals, q)


# --------------------------------------------------------------------------------------------- Q8 (review item 2) ----
class Q8:
    """Packet-level fate of every GM Sync / Follow_Up (domain 0) of DS-TT 0 / slave 0 (N = 1).

    Stages (each a recorded observation of that very frame): GM tx -> NW-TT rx -> NW-TT tx -> UPF N6 rx -> UPF N3 tx
    (GTP-U, the UE's session) -> gNB RLC UM TX SDU (order of the frames of that size on the gPTP DRB, checked against
    the N3 order and timing) -> RLC replay (single-segment-per-PDU NR UM model, S7.1/P1, validated per run: every
    observed delivery must be predicted) -> UE RLC delivery -> UE tx -> DS-TT rx -> DS-TT tx -> slave rx.
    Fate of an undelivered frame (exactly one):
      censored   packet-specific evidence that it was still inside the system at T_end: queued in the replayed RLC TX
                 buffer (not started / partially sent: its own remainder), its last RLC PDU sent with the delivery due
                 after T_end, its DS-TT hold open at T_end, or its own last observation + the largest latency of that
                 stage observed in this run > T_end (frame on a link or inside a node)
      lost       a destroyed PDU of its own SDU WITH an observed discard of that TTI in the MAC log (HARQ-process
                 deletion, NACK, MAC buffer overflow)
      invalid / late   its own DS-TT discard event (the S7.1 event classes)
      UNEXPLAINED anything else, including a destroyed PDU without an observed discard. Never reclassified.
    """

    def __init__(self, ev, mlog, opt, mut=None):
        self.ev, self.mlog, self.opt, self.mut = ev, mlog, opt, mut or {}
        run, T = ev.run, ev.T
        self.T = T
        u = run.ue_view(0)
        self.node = run.node_id[0]
        ds, df, mode = L.OPTIONS[opt][:3]
        if ds != df or mode != "um":
            raise ValueError(f"{opt}: E0 expects Sync and Follow_Up on one UM DRB")
        self.drb = ds
        st = {}
        st["GM"] = {k: f["start"] for k, f in first(run.gm, 2).items()}
        st["NW-TT rx"] = {k: f["end"] for k, f in first(run.nw1, 1).items()}
        st["NW-TT tx"] = {k: f["end"] for k, f in first(run.nw0, 2).items()}
        st["UPF N6 rx"] = {k: f["end"] for k, f in first(run.dn, 1).items()}
        n3 = {}
        self.n3_bad = []
        for r in R.n3_records(run.n3path):
            if r["gtype"] in (SYNC, FU) and r["dir"] == 2 and not r["frag"]:
                key = (r["gtype"], r["gseq"])
                if key in n3:
                    self.n3_bad.append(f"duplicate N3 DL copy {key}")
                n3[key] = r["t"]
        st["UPF N3 tx"] = n3
        self.ue_tx = {k: f["end"] for k, f in first(u.ue, 2).items()}
        self.ds_rx = {k: f["end"] for k, f in first(u.ds0, 1).items() if f["end"] <= T}
        self.ds_tx = {k: f["start"] for k, f in first(u.ds1, 2).items()}
        self.sl_rx = {k: f["end"] for k, f in first(u.sl, 1).items() if f["end"] <= T}
        self.st = st
        self.dslog = defaultdict(list)
        for r in u.dslog:
            if r.get("seq", "") not in ("", None) and r.get("msgType") in ("0", "8") and int(r["t"]) <= T:
                self.dslog[(int(r["msgType"]), int(r["seq"]))].append(r["event"])
        # RLC (vectors), the replay, the UE side
        tx = f"gnb1.cellularNic.rlc-um-{self.node}-{self.drb}.tx"
        rx = f"ue[0].cellularNic.nrRlc-um-1-{self.drb}.rx"
        vec = lambda m, n: [(t, int(float(v))) for t, v in ev.vec.get((f"{R.NET}.{m}", n), [])]  # noqa: E731
        self.sdus = vec(tx, "receivedPacketFromUpperLayer:vector(packetBytes)")
        self.pdus = vec(tx, "sentPduSize:vector")
        self.deliv = vec(rx, "sentPacketToUpperLayer:vector(packetBytes)")
        self.rxpdus = vec(rx, "receivedPacketFromLowerLayer:vector(packetBytes)")
        if "drop_rxpdu" in self.mut:                      # control NC-q8-noevid
            self.rxpdus = [x for x in self.rxpdus if x != self.mut["drop_rxpdu"]]
        if "drop_deliv" in self.mut:                      # control NC-q8-deliv
            self.deliv = [x for x in self.deliv if x != self.mut["drop_deliv"][0]]
            for d in (self.ds_rx, self.ue_tx, self.ds_tx, self.sl_rx):
                d.pop(self.mut["drop_deliv"][1], None)
        self.replay()
        self.map_sdus()
        self.classify()

    # ---------------------------------------------------------------------------------------------- replay
    def replay(self):
        T = self.T
        sdus, pdus = [x for x in self.sdus if x[0] <= T], [x for x in self.pdus if x[0] <= T]
        if self.mut.get("seg"):                           # control NC-q8-seg: wrong first-segment header size
            pdus = [(t, s + 1) for t, s in pdus]
        self.model_err = None
        try:
            done, slots, left = L.replay_um(sdus, pdus)
            matched, unmatched, rest, lostpdu = G.deliveries(done, [x for x in self.deliv if x[0] <= T],
                                                             [x for x in self.rxpdus if x[0] <= T], pdus, sdus, T)
        except (ValueError, IndexError, KeyError) as ex:
            self.model_err = f"{type(ex).__name__}: {ex}"
            done, left, matched, unmatched, rest, lostpdu = [], [], [], [], [], []
        self.done, self.left, self.matched, self.unmatched, self.rest, self.lostpdu = done, left, matched, unmatched, rest, lostpdu
        self.own = L.pdu_owner(sdus, pdus) if self.model_err is None else []
        self.pdus_h = pdus
        self.sdus_h = sdus

    def map_sdus(self):
        """gPTP SDUs of the DRB by size (Sync < Follow_Up < 110 B < data), in N3 order; checked: same count up to the
        frames still between N3 and the RLC, arrival after its N3 copy, monotone"""
        self.sdu_of, self.map_bad = {}, []
        small = sorted({sz for _, sz in self.sdus_h if sz < 110})
        if len(small) != 2:
            self.map_bad.append(f"gPTP SDU sizes on DRB {self.drb}: {small} (expected two: Sync, Follow_Up)")
            return
        for typ, sz in ((SYNC, small[0]), (FU, small[1])):
            sd = [x for x in self.sdus_h if x[1] == sz]
            n3 = sorted(((t, k) for k, t in self.st["UPF N3 tx"].items() if k[0] == typ), key=lambda x: x[0])
            for i, (t3, k) in enumerate(n3):
                if i < len(sd):
                    if sd[i][0] < t3:
                        self.map_bad.append(f"{k}: RLC SDU at {sd[i][0]} before its N3 copy at {t3}")
                    self.sdu_of[k] = sd[i]
            if len(sd) > len(n3):
                self.map_bad.append(f"type {typ}: {len(sd)} RLC SDUs of {sz} B, {len(n3)} N3 copies")
        lat = [sdu[0] - self.st["UPF N3 tx"][k] for k, sdu in self.sdu_of.items()]
        self.lat_n3_rlc = max(lat) if lat else None

    # ---------------------------------------------------------------------------------------------- fates
    def stage_max(self, a, b):
        lat = [b[k] - a[k] for k in b if k in a]
        return max(lat) if lat else None

    def mac_discard(self, t_pdu):
        """observed discard in the MAC log at the TTI of a destroyed PDU (N = 1: every DL MAC PDU is UE 0's)"""
        if self.mlog is None:
            return None
        tti = t_pdu // MS
        for d in self.mlog.pdus:
            if d["deleted"] and d["t"] // MS == tti:
                return f"HARQ-process MAC PDU deletion at {tti} ms"
        for t, n, l, k in self.mlog.overflow:
            if t // MS == tti and n == self.node:
                return f"MAC buffer overflow at {tti} ms"
        for t, p, res in self.mlog.feedback:
            if res == "NACK" and t // MS in range(tti, tti + 40):
                return f"HARQ NACK at {t // MS} ms"
        return None

    def classify(self):
        T, st = self.T, self.st
        order = ["GM", "NW-TT rx", "NW-TT tx", "UPF N6 rx", "UPF N3 tx"]
        smax = {order[i + 1]: self.stage_max(st[order[i]], st[order[i + 1]]) for i in range(len(order) - 1)}
        sdu_fate = {}
        for (arr, size, tl, td) in self.matched:
            sdu_fate[(arr, size)] = ("delivered", tl, td)
        for (arr, size, tl, status) in self.unmatched:
            sdu_fate[(arr, size)] = ({True: "destroyed", "inflight": "inflight", False: "unexplained"}[status], tl, None)
        left = {(q["arr"], q["size"]): q for q in self.left}
        ue_deliv = {k: sdu_fate[s][2] for k, s in self.sdu_of.items() if s in sdu_fate and sdu_fate[s][0] == "delivered"}
        lat_ue = self.stage_max(ue_deliv, self.ue_tx)
        lat_ds = self.stage_max(self.ue_tx, self.ds_rx)
        lat_dstx = self.stage_max(self.ds_rx, self.ds_tx)
        lat_sl = self.stage_max(self.ds_tx, self.sl_rx)
        self.fate = {}
        destroyed_sdu_pdus = defaultdict(list)
        for k, (t, s) in enumerate(self.pdus_h):
            if (t, s) in self.lostpdu and k < len(self.own):
                destroyed_sdu_pdus[self.own[k]].append(t)
        sdu_index = {(a, sz): i for i, (a, sz, _) in enumerate(self.done)}

        def bound(name, t_last, lat):
            if lat is None:
                return ("UNEXPLAINED", name, f"no {name} latency observed in this run")
            if t_last + lat > T:
                return ("censored", name, f"own last observation {t_last} + largest observed latency {lat} > T_end")
            return ("UNEXPLAINED", name, f"not observed after {name} by T_end although {t_last} + {lat} <= T_end")
        for key, tg in sorted(st["GM"].items(), key=lambda kv: kv[1]):
            if key in self.sl_rx:
                self.fate[key] = ("delivered", "slave", "")
                continue
            if key in self.ds_rx:
                evs = set(self.dslog.get(key, []))
                inval = evs & {"fuInvalidUpstream", "fuNoTag", "tagMismatch", "malformedFU", "unsupportedRepresentation",
                               "associationMismatch", "ambiguousSync", "duplicateFU"}
                late = evs & {"staleFU", "fuNoSync", "holdExpired", "dropLagTest"}
                if inval:
                    self.fate[key] = ("invalid", "DS-TT egress", f"own DS-TT discard event {sorted(inval)}")
                elif late:
                    self.fate[key] = ("late", "DS-TT egress", f"own DS-TT discard event {sorted(late)}")
                elif "hold" in evs and "release" not in evs:
                    self.fate[key] = ("censored", "DS-TT egress", "own DS-TT hold open at T_end")
                elif key in self.ds_tx:
                    self.fate[key] = bound("DS-TT tx", self.ds_tx[key], lat_sl)
                else:
                    self.fate[key] = bound("DS-TT rx", self.ds_rx[key], lat_dstx)
                continue
            if key in self.ue_tx:
                self.fate[key] = bound("UE tx", self.ue_tx[key], lat_ds)
                continue
            last = "GM"
            for name in order[1:]:
                if key in st[name]:
                    last = name
                else:
                    break
            if last != "UPF N3 tx":
                nxt = order[order.index(last) + 1]
                self.fate[key] = bound(last, st[last][key], smax[nxt])
                continue
            sdu = self.sdu_of.get(key)
            if sdu is None:
                self.fate[key] = bound("UPF N3 tx", st["UPF N3 tx"][key], self.lat_n3_rlc)
                continue
            if sdu in left:
                q = left[sdu]
                self.fate[key] = ("censored", "gNB RLC UM TX buffer",
                                  f"own SDU queued at T_end ({'not started' if q['sent'] == 0 else 'partially sent: ' + str(q['sent']) + ' of ' + str(q['size']) + ' B'})")
                continue
            f = sdu_fate.get(sdu)
            if f is None:
                self.fate[key] = ("UNEXPLAINED", "gNB RLC UM TX", "SDU neither queued nor completed in the replay")
            elif f[0] == "inflight":
                self.fate[key] = ("censored", "gNB MAC / air", f"own last RLC PDU at {f[1]}, delivery due {f[1] + 4 * MS} > T_end")
            elif f[0] == "destroyed":
                ts = destroyed_sdu_pdus.get(sdu_index.get(sdu), [])
                why = [self.mac_discard(t) for t in ts]
                why = [w for w in why if w]
                if why:
                    self.fate[key] = ("lost", "gNB MAC / HARQ", f"own PDU destroyed; observed discard: {why[0]}")
                else:
                    self.fate[key] = ("UNEXPLAINED", "gNB MAC / air", f"own PDU never received (PDU times {ts}), no observed discard")
            elif f[0] == "delivered":
                self.fate[key] = bound("UE RLC delivery", f[2], lat_ue)
            else:
                self.fate[key] = ("UNEXPLAINED", "gNB RLC UM TX", "replay: completed SDU without a predicted delivery")
        self.lat = {"UE RLC->UE tx": lat_ue, "UE tx->DS-TT rx": lat_ds, "DS-TT rx->tx": lat_dstx, "DS-TT tx->slave": lat_sl,
                    "N3->RLC": self.lat_n3_rlc, **smax}

    # ---------------------------------------------------------------------------------------------- pairs
    def pairs(self):
        """S7.1 Q8 pair classes per GM Sync with a Follow_Up: used / ignored (INET's slave rule) / lost / censored /
        UNEXPLAINED; incomplete GM events counted separately"""
        gs = {s for (t, s) in self.st["GM"] if t == SYNC}
        gf = {s for (t, s) in self.st["GM"] if t == FU}
        use = {}
        last = None
        for f in sorted(self.ev.run.ue_view(0).sl, key=lambda f: f["end"]):
            if f["dir"] != 1 or f["type"] not in (SYNC, FU) or f["end"] > self.T or f["dom"] != 0:
                continue
            if f["type"] == SYNC:
                last = f["seq"]
            else:
                use.setdefault(f["seq"], "used" if f["seq"] == last else "ignored")
        out = {}
        for s in sorted(gs & gf):
            a, b = self.fate[(SYNC, s)][0], self.fate[(FU, s)][0]
            if "UNEXPLAINED" in (a, b):
                o = "UNEXPLAINED"
            elif s in use:
                o = use[s]
            elif "lost" in (a, b):
                o = "lost"
            elif "invalid" in (a, b):
                o = "invalid"
            elif "late" in (a, b):
                o = "late"
            elif "censored" in (a, b):
                o = "censored"
            else:
                o = "UNEXPLAINED"          # both delivered to the slave yet not used / ignored: not explained
            out[s] = o
        self.incomplete = sorted((gs ^ gf))
        return out


# --------------------------------------------------------------------------------------- MAC-log consistency (Q8-x) --
def q8x(name, q, mlog, sca_over):
    probs = []
    if mlog is None:
        add("Q8-x", name, NE, "no MAC log in this run")
        return
    tx = f"{R.NET}.gnb1.cellularNic.rlc-um-{q.node}-{q.drb}.tx"
    e = mlog.rlc_tx.get(tx)
    if e is None:
        probs.append(f"no RLC TX log lines of {tx}")
    else:
        if len(e["sdu"]) != len(q.sdus):
            probs.append(f"RLC TX SDUs: log {len(e['sdu'])}, vector {len(q.sdus)}")
        if len(e["pdu"]) != len(q.pdus):
            probs.append(f"RLC TX PDUs: log {len(e['pdu'])}, vector {len(q.pdus)}")
        if e["drop"]:
            probs.append(f"RLC TX drops {len(e['drop'])}")
    rx = f"{R.NET}.ue[0].cellularNic.nrRlc-um-1-{q.drb}.rx"
    er = mlog.rlc_rx.get(rx)
    if er is None:
        probs.append(f"no RLC RX log lines of {rx}")
    elif len(er["deliv"]) != len(q.deliv):
        probs.append(f"UE RLC deliveries: log {len(er['deliv'])}, vector {len(q.deliv)}")
    if mlog.unclassified:
        probs.append(f"{len(mlog.unclassified)} UNCLASSIFIED loss-like lines, first {mlog.unclassified[0][2][:120]}")
    if (len(mlog.overflow) > 0) != (sca_over > 0):
        probs.append(f"MAC overflow lines {len(mlog.overflow)} vs macBufferOverFlowDl samples {sca_over}")
    # a MAC PDU deletion must not coincide with a delivered gPTP SDU's last PDU (TTI)
    dl = {k: q.sdu_of[k] for k, f in q.fate.items() if f[0] == "delivered" and k in q.sdu_of}
    tl = {(a, s): t for a, s, t in q.done}
    dels = {d["t"] // MS for d in mlog.pdus if d["deleted"]}
    clash = [k for k, sdu in dl.items() if sdu in tl and tl[sdu] // MS in dels]
    if clash:
        probs.append(f"MAC log deletes the PDU of delivered gPTP frames {clash[:3]}")
    if mlog.ttis == 0 or not mlog.grants:
        probs.append("no scheduler main loop / grants in the MAC log")
    add("Q8-x", name, not probs, f"MAC log {dict(mlog.lines)}; RLC TX/RX log vs vectors, UNCLASSIFIED, overflow vs scalar, deletion vs delivered: "
        + ("consistent" if not probs else "FAIL " + "; ".join(probs[:4])))


def q8_rows(name, q):
    fates = Counter(f[0] for f in q.fate.values())
    unexpl = [(k, f) for k, f in q.fate.items() if f[0] == "UNEXPLAINED"]
    pairs = q.pairs()
    pc = Counter(pairs.values())
    probs = []
    if q.model_err:
        probs.append(f"RLC replay failed: {q.model_err}")
    if q.rest:
        probs.append(f"{len(q.rest)} observed UE RLC deliveries not predicted by the replay, first {q.rest[:2]}")
    dmatch = set()
    if q.lostpdu and q.model_err is None:
        idx = {(a, sz): i for i, (a, sz, _) in enumerate(q.done)}
        lost_own = {q.own[kk] for kk, x in enumerate(q.pdus_h) if x in set(q.lostpdu) and kk < len(q.own)}
        dmatch = {(a, sz) for a, sz, _, _ in q.matched if idx.get((a, sz)) in lost_own}
    if dmatch:
        probs.append(f"{len(dmatch)} delivered SDUs with a PDU never received (inconsistent evidence), first {sorted(dmatch)[:2]}")
    une = [x for x in q.unmatched if x[3] is False]
    if une:
        probs.append(f"{len(une)} replayed SDUs (any flow) whose delivery was due by T_end, not observed, no destroyed PDU: first {une[:2]}")
    dest = [x for x in q.unmatched if x[3] is True]
    if dest:
        sdu_index = {(a, sz): i for i, (a, sz, _) in enumerate(q.done)}
        own_t = defaultdict(list)
        for kk, (t, sz) in enumerate(q.pdus_h):
            if (t, sz) in q.lostpdu and kk < len(q.own):
                own_t[q.own[kk]].append(t)
        noev = [x for x in dest if not any(q.mac_discard(t) for t in own_t.get(sdu_index.get((x[0], x[1])), []))]
        if noev:
            probs.append(f"{len(noev)} destroyed SDUs (any flow) without an observed MAC discard, first {noev[:2]}")
    if q.map_bad:
        probs.append("SDU mapping: " + "; ".join(q.map_bad[:3]))
    if q.n3_bad:
        probs.append("N3: " + "; ".join(q.n3_bad[:3]))
    if unexpl:
        probs.append(f"{len(unexpl)} UNEXPLAINED frames, first {[(('S' if k[0] == 0 else 'F') + str(k[1]), f[1], f[2]) for k, f in unexpl[:3]]}")
    if sum(fates.values()) != len(q.st["GM"]):
        probs.append("frame conservation")
    if pc["UNEXPLAINED"]:
        probs.append(f"{pc['UNEXPLAINED']} UNEXPLAINED pairs")
    loc = Counter((f[0], f[1]) for f in q.fate.values() if f[0] != "delivered")
    add("Q8", name, not probs,
        f"GM frames {len(q.st['GM'])}: {dict(fates)}; undelivered by (fate, last confirmed location) {dict(loc)}; pairs {dict(pc)}, "
        f"incomplete GM events {len(q.incomplete)}; replay: {len(q.matched)} deliveries predicted and observed, {len(q.rest)} observed not predicted"
        + ("" if not probs else "; FAIL " + " | ".join(probs)))
    return pairs


# --------------------------------------------------------------------------------------------------- metrics -------
def series_per_s(times_sizes, t0, T):
    out = []
    for s in range(int(t0 // S), int(T // S)):
        out.append(sum(sz for t, sz in times_sizes if s * S <= t < (s + 1) * S))
    return out


class DrbReplay:
    """RLC UM TX replay of one DRB of UE 0 (for the load DRB 1 of Q-d, where the gPTP DRB is 4): SDUs, completed SDUs,
    queue at T_end, and the UE-side accounting of deliveries.deliveries (destroyed / unexplained SDUs of any flow)"""
    def __init__(self, ev, node, drb):
        T = ev.T
        vec = lambda m, n: [(t, int(float(v))) for t, v in ev.vec.get((f"{R.NET}.{m}", n), []) if t <= T]  # noqa: E731
        tx, rx = f"gnb1.cellularNic.rlc-um-{node}-{drb}.tx", f"ue[0].cellularNic.nrRlc-um-1-{drb}.rx"
        self.sdus_h, pdus = vec(tx, "receivedPacketFromUpperLayer:vector(packetBytes)"), vec(tx, "sentPduSize:vector")
        self.done, _, self.left = L.replay_um(self.sdus_h, pdus)
        matched, unmatched, rest, lostpdu = G.deliveries(self.done, vec(rx, "sentPacketToUpperLayer:vector(packetBytes)"),
                                                         vec(rx, "receivedPacketFromLowerLayer:vector(packetBytes)"), pdus, self.sdus_h, T)
        self.acc = {"predicted_observed": len(matched), "destroyed": sum(1 for x in unmatched if x[3] is True),
                    "inflight": sum(1 for x in unmatched if x[3] == "inflight"), "unexplained": sum(1 for x in unmatched if x[3] is False),
                    "observed_not_predicted": len(rest), "queued_end": len(self.left)}


def backlog(q, T, step=S // 2):
    """replayed RLC TX backlog of a DRB (bytes not yet sent) at every step: arrivals - payload of completed SDUs"""
    arr = sorted((t, sz) for t, sz in q.sdus_h)
    done_t = sorted((tl, sz) for _, sz, tl in q.done)
    out, i, j, a, d = [], 0, 0, 0, 0
    for t in range(step, T + 1, step):
        while i < len(arr) and arr[i][0] <= t:
            a += arr[i][1]
            i += 1
        while j < len(done_t) and done_t[j][0] <= t:
            d += done_t[j][1]
            j += 1
        out.append((t, a - d))
    return out


def sustained_growth(bl):
    """declared rule: the per-second minimum of the backlog strictly increases in every second from [4 s, 5 s) to
    [11 s, 12 s) (8 windows)"""
    mins = []
    for s in range(4, 12):
        v = [b for t, b in bl if s * S <= t < (s + 1) * S]
        mins.append(min(v) if v else None)
    return all(x is not None for x in mins) and all(mins[i + 1] > mins[i] for i in range(len(mins) - 1)), mins


def csv_frames(path, pcp=0, length=LOAD_LEN):
    out = []
    with open(path) as fh:
        for r in csv.DictReader(fh):
            if r["pcp"] == str(pcp) and r["payloadLen"] == str(length) and r["vid"] == "42":
                out.append(R.pcapng.simtime_ps(r["t"]))
    return out


def cfg_rate(name, ev, f):
    """the load sources produce exactly the configured frames: DL at the listener egress from 0.3005 s every
    0.25 ms / f, UL at talker[0] egress from 0.1005 s every 0.25 ms (exact ps)"""
    probs = []
    for who, start, iv in (("listener", DL_START, LOAD_INTERVAL[f]), ("talker[0]", UL_START, Fraction(UL_INTERVAL))):
        ts = csv_frames(os.path.join(ev.run.ldir, f"{R.NET}.{who}.eth[0].measurementLayer.egress.csv"))
        n_exp = int((Fraction(ev.T - start) / iv)) + 1 if ev.T >= start else 0
        exp_t = [start + int(iv * i) for i in range(n_exp)]
        ok = ts == exp_t[:len(ts)] and n_exp - 1 <= len(ts) <= n_exp
        if not ok:
            probs.append(f"{who}: {len(ts)} load frames (expected {n_exp - 1}..{n_exp}), first {ts[:2]}")
    add("CFG-rate", name, not probs, f"DL every {float(LOAD_INTERVAL[f]) / US:g} us from {DL_START / S} s, UL every {UL_INTERVAL / US:g} us from "
        f"{UL_START / S} s, exact" + ("" if not probs else "; FAIL " + "; ".join(probs)))


def sca_samples(sca, name):
    """samples of the gNB MAC statistic: its :count if recorded, else 0 for a NaN :mean (no sample) and >= 1 otherwise"""
    cnt, mean = None, None
    for line in open(sca):
        p = line.split()
        if line.startswith("scalar ") and len(p) >= 4 and p[1].endswith("gnb1.cellularNic.mac"):
            if p[2] == f"{name}:count":
                cnt = int(float(p[3]))
            elif p[2] == f"{name}:mean":
                mean = p[3]
    if cnt is not None:
        return cnt
    if mean is None:
        raise ValueError(f"{sca}: no {name} statistic of the gNB MAC")
    return 0 if mean in ("nan", "-nan") else 1


def sca_value(sca, mod_end, name):
    for line in open(sca):
        if line.startswith("scalar ") and line.split()[1].endswith(mod_end) and line.split()[2] == name:
            return line.split()[3]
    return None


# ------------------------------------------------------------------------------------------------ run evaluation ----
def evaluate(runs, cfg, opt, f, mlog_path=None, mut=None, gates=True):
    """every correctness row of one E0 run (gate scoping of the module docstring), Q8, Q8-x, the metrics"""
    base = f"M2S72-H-{opt}-Ca-n1"            # evaluated as (option, C-a clocks, N = 1): clock configuration and option only
    B.BN_BASE[cfg] = base
    name = f"{cfg}-0"
    start = len(rows)
    T = B.F1.t_end(R.Run72(runs, cfg, 0))
    ev, stats, _ = B.evaluate(runs, cfg, 0, ref=None, conf_fn=lambda k: V.CONF(base, k, T), full=gates)
    st = I.i2h_rows(ev) if gates else {}
    I.relabel(start, base)
    for i in range(start, len(rows)):
        if rows[i][0] == "F0-1" and cfg not in LOSS_FREE:
            rows[i] = ("F0-1 (info)",) + rows[i][1:]
    mlog = ML.MacLog(mlog_path) if mlog_path and os.path.exists(mlog_path) else None
    if mut and "fake_deletion" in mut and mlog is not None:   # control NC-maclog-del
        mlog.pdus.append({"t": mut["fake_deletion"], "bytes": 0, "sdus": 1, "deleted": True, "proc": None, "node": None, "pid": None})
    if mut and "drop_deliv" in mut and mlog is not None:      # NC-q8-deliv / NC-q8-noevid: the UE RLC log loses the delivery too
        t_d, sz = mut["drop_deliv"][0]
        for e in mlog.rlc_rx.values():
            if (t_d, sz - 0) in e["deliv"]:
                e["deliv"].remove((t_d, sz))
                break
    q = Q8(ev, mlog, opt, mut=mut)
    pairs = q8_rows(name, q)
    sca = ev.run.sca_path
    q8x(name, q, mlog, sca_samples(sca, "macBufferOverFlowDl"))
    if gates:
        cfg_rate(name, ev, f)
        # EOR, scoped: bounded latency verified?
        bl = backlog(q, T)
        grow, mins = sustained_growth(bl)
        lat = [q.ds_rx[k] - q.st["GM"][k] for k in q.ds_rx if k in q.st["GM"]]
        lmax = max(lat) if lat else None
        if lmax is not None and lmax <= 2 * SYNC_INTERVAL and not grow:
            import check_m2s72_cp2r2 as CP
            CP.eor_rows(ev)
        else:
            add("EOR", f"{name} DS-TT 0", NA, f"bounded latency not verified (L_max {None if lmax is None else lmax / MS} ms vs 2 Sync intervals = "
                f"{2 * SYNC_INTERVAL / MS} ms; sustained backlog growth {grow}); Q8 packet-level censoring governs")
        add("I-5", name, NA, "E0 is N = 1: no reference of another N")
        add("M3", name, NA, "cross-slave pair oracle: no pair of slaves at N = 1")
        add("M3d", name, NA, "cross-slave pair decomposition: no pair of slaves at N = 1")
        add("H-cov", name, NA, "no residence heterogeneity declared at N = 1")
        add("I-4 stream", name, NA, "needs N = 2 and N = 4")
    m = metrics(name, ev, q, pairs, mlog, f, opt)
    fails = {r[0] for r in rows[start:] if r[2] == "FAIL" and r[0] not in INFO}
    return ev, q, m, fails


def metrics(name, ev, q, pairs, mlog, f, opt):
    T = ev.T
    run = ev.run
    t0 = 2 * S
    m = {"run": name, "option": opt, "factor": f, "T_end_s": T / S}
    # offered vs achieved, per direction (bytes / s over [2 s, T_end))
    load_sz = sorted({sz for _, sz in q.sdus_h if sz > 1000})
    m["rlc_load_sdu_size"] = load_sz
    tx1 = f"gnb1.cellularNic.rlc-um-{q.node}-1.tx"
    rx1 = "ue[0].cellularNic.nrRlc-um-1-1.rx"
    vec = lambda mm, n: [(t, int(float(v))) for t, v in ev.vec.get((f"{R.NET}.{mm}", n), [])]  # noqa: E731
    sd1 = [x for x in vec(tx1, "receivedPacketFromUpperLayer:vector(packetBytes)") if x[1] > 1000]
    dv1 = [x for x in vec(rx1, "sentPacketToUpperLayer:vector(packetBytes)") if x[1] > 1000]
    dur = (T - t0) / S
    m["dl_offered_cfg_Mbps"] = LOAD_LEN * 8 / (float(LOAD_INTERVAL[f]) / S) / 1e6
    m["dl_offered_rlc_Mbps"] = sum(sz for t, sz in sd1 if t >= t0) * 8 / dur / 1e6
    m["dl_achieved_rlc_Mbps"] = sum(sz for t, sz in dv1 if t >= t0) * 8 / dur / 1e6
    m["dl_offered_rlc_per_s"] = series_per_s(sd1, 0, T)
    m["dl_achieved_rlc_per_s"] = series_per_s(dv1, 0, T)
    ul_tx = csv_frames(os.path.join(run.ldir, f"{R.NET}.talker[0].eth[0].measurementLayer.egress.csv"))
    ul_rx = csv_frames(os.path.join(run.ldir, f"{R.NET}.listener.eth[0].measurementLayer.ingress.csv"))
    dl_rx = csv_frames(os.path.join(run.ldir, f"{R.NET}.talker[0].eth[0].measurementLayer.ingress.csv"))
    m["ul_offered_Mbps"] = sum(1 for t in ul_tx if t >= t0) * LOAD_LEN * 8 / dur / 1e6
    m["ul_achieved_Mbps"] = sum(1 for t in ul_rx if t >= t0) * LOAD_LEN * 8 / dur / 1e6
    m["dl_app_achieved_Mbps"] = sum(1 for t in dl_rx if t >= t0) * LOAD_LEN * 8 / dur / 1e6
    m["dl_load_frames"] = (len(csv_frames(os.path.join(run.ldir, f"{R.NET}.listener.eth[0].measurementLayer.egress.csv"))), len(dl_rx))
    # MAC grants, HARQ, buffers
    if mlog is not None:
        s = mlog.summary()
        m.update({f"mac_{k}": v for k, v in s.items() if k != "min_space"})
        m["mac_min_space"] = {f"{a}-{b}": v for (a, b), v in s["min_space"].items()}
        g = mlog.grant_bytes("DL", q.node)
        m["mac_dl_grant_Mbps"] = sum(b for t, b in g if t >= t0) * 8 / dur / 1e6
        ttis = {t // MS for t, b in g if b > 0}
        m["mac_dl_tti_share"] = len([x for x in ttis if x >= t0 // MS]) / max(1, (T - t0) // MS)
        m["mac_dl_grant_bytes_per_lcid"] = dict(Counter({l: 0 for l in ()}))
        per = Counter()
        for t, d, n, l, b in mlog.grants:
            if d == "DL" and n == q.node and t >= t0:
                per[l] += b
        m["mac_dl_grant_bytes_per_lcid"] = dict(per)
    m["sca_macBufferOverFlowDl_samples"] = sca_samples(run.sca_path, "macBufferOverFlowDl")
    # backlog evolution of the gPTP DRB (and DRB 1 if different)
    bl = backlog(q, T)
    grow, mins = sustained_growth(bl)
    m["gptp_drb"] = q.drb
    m["backlog_bytes_per_0p5s"] = [b for _, b in bl]
    m["backlog_end_bytes"] = bl[-1][1] if bl else None
    m["sustained_growth"] = grow
    m["backlog_window_min"] = mins
    m["rlc_left_sdus_end"] = len(q.left)
    d1 = q if q.drb == 1 else DrbReplay(ev, q.node, 1)
    bl1 = backlog(d1, T)
    g1, mins1 = sustained_growth(bl1)
    m["load_drb1_backlog_per_0p5s"] = [b for _, b in bl1]
    m["load_drb1_backlog_end_bytes"] = bl1[-1][1] if bl1 else None
    m["load_drb1_sustained_growth"] = g1
    m["load_drb1_window_min"] = mins1
    m["load_drb1_accounting"] = getattr(d1, "acc", None) or {"predicted_observed": len(q.matched), "destroyed": sum(1 for x in q.unmatched if x[3] is True),
                                                            "inflight": sum(1 for x in q.unmatched if x[3] == "inflight"),
                                                            "unexplained": sum(1 for x in q.unmatched if x[3] is False),
                                                            "observed_not_predicted": len(q.rest), "queued_end": len(q.left)}
    # Q8 classes
    fates = Counter(f_[0] for f_ in q.fate.values())
    m["q8_frames"] = dict(fates)
    m["q8_undelivered_by_location"] = dict(Counter(f"{f_[0]}@{f_[1]}" for f_ in q.fate.values() if f_[0] != "delivered"))
    pc = Counter(pairs.values())
    co = [s for s in pairs if (SYNC, s) in q.st["GM"] and q.st["GM"][(SYNC, s)] < T_COHORT]
    pcc = Counter(pairs[s] for s in co)
    m["pairs"] = dict(pc)
    m["cohort_pairs"] = dict(pcc)
    m["cohort_n"] = len(co)
    m["P_used_cohort"] = pcc["used"] / len(co) if co else None
    m["censored_cohort_fraction"] = pcc["censored"] / len(co) if co else None
    first_lc = [s for s in sorted(co, key=lambda s: q.st["GM"][(SYNC, s)]) if pairs[s] in ("lost", "censored")]
    m["first_lost_or_censored_pair"] = (first_lc[0], q.st["GM"][(SYNC, first_lc[0])] / S) if first_lc else None
    # timing: Sync residence (NW-TT rx -> DS-TT tx, as S7.1), +inf if not delivered; Follow_Up lag for used pairs
    res, lag = [], []
    for s in co:
        a, b = q.st["NW-TT rx"].get((SYNC, s)), q.ds_tx.get((SYNC, s))
        res.append(b - a if (a is not None and b is not None and b <= T) else INF)
        if pairs[s] == "used" and (FU, s) in q.ds_rx and (SYNC, s) in q.ds_tx:
            lag.append(q.ds_rx[(FU, s)] - q.ds_tx[(SYNC, s)])
        else:
            lag.append(INF)
    m["res_p50_ms"], m["res_p99_ms"], m["res_max_ms"] = [None if x is None else (x if x == INF else x / MS) for x in (pct(res, 0.5), pct(res, 0.99), max(res) if res else None)]
    fin = [x for x in res if x != INF]
    m["res_delivered_max_ms"] = max(fin) / MS if fin else None
    m["lag_p99_ms"] = (lambda x: None if x is None else (x if x == INF else x / MS))(pct(lag, 0.99))
    m["deadline_res_gt_5p5ms"] = sum(1 for x in res if x > B_RES)
    m["deadline_lag_gt_sync_interval"] = sum(1 for x in lag if x > SYNC_INTERVAL)
    # sync error: M2-S6 steady-state between-step max |e| (calibrated intervals from step 3), exact oracle values
    E = ev.E.get(0)
    if E is not None:
        cal = [x["seq"] for x in E.fus if "skip" not in x and x.get("nrr_valid")]
        vals = [abs(x["max_between"]) for x in E.iv[2:] if x["seq"] in cal and cal and x["seq"] != cal[0] and x["max_between"] is not None]
        m["max_e_ns"] = float(max(vals)) / NS if vals else None
        gaps = sorted(b - a for a, b in zip([x["sF"] for x in E.fus if "old" in x], [x["sF"] for x in E.fus if "old" in x][1:]))
        m["update_gap_max_ms"] = gaps[-1] / MS if gaps else None
        m["slave_updates"] = len([x for x in E.fus if "old" in x])
    else:
        m["max_e_ns"] = None
    m["holds"] = sum(1 for r in run.ue_view(0).dslog if r["event"] == "hold")
    m["stage_latency_max_us"] = {k: (None if v is None else v / US) for k, v in q.lat.items()}
    return m


def onset(m):
    """exploratory onset thresholds (review item 4): which metric crosses which threshold (with sensitivity)"""
    out = {"lost_or_censored_pair": m["first_lost_or_censored_pair"] is not None}
    rp = m["res_p99_ms"]
    rp = INF if rp == INF else (rp * MS if rp is not None else None)
    for th in THRESH["res_p99"]:
        out[f"res_p99>{th / MS:g}ms"] = rp is not None and rp > th
    me = m.get("max_e_ns")
    for th in THRESH["max_e"]:
        out[f"max|e|>{th / NS:g}ns"] = me is None or me * NS > th
    pu = m["P_used_cohort"]
    for th in THRESH["p_used"]:
        out[f"P(used)<{th}"] = pu is None or pu < th
    return out


# --------------------------------------------------------------------------------------------- non-perturbation ----
HDR = re.compile(r"^(run|attr|config|itervar|version) ")
ELOG_KEEP = ("E ", "BS ", "ES ", "SH ", "CMB ", "CME ", "DM ", "CM ", "CC ", "CE ", "GC ", "MC ", "MDC ", "CL ", "SD ", "BU ", "EN ")


def file_digest(path, cfg, kind):
    h = hashlib.sha256()
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rb") as fh:
        if kind == "raw":
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
            return h.hexdigest()
        for line in fh:
            s = line.decode("utf-8", "replace")
            if kind in ("vec", "sca") and HDR.match(s):
                continue
            if kind == "elog":
                if s.startswith("- "):
                    # log text: only the UPF MAC-table lines (F0-7's input), prefix removed
                    mm = re.match(r"- (?:[^|]*\|M2S72Bridge\.upf\.ethBridge\.macTable\||\[INFO\]\t)(.*)", s)
                    if not mm or ("|" in s[:40] and "macTable" not in s[:80]):
                        continue
                    s = "- " + mm.group(1) + "\n"
                elif not s.startswith(ELOG_KEEP):
                    continue
            h.update(s.replace(cfg, "<config>").encode())
    return h.hexdigest()


def nonpert(runs, a, b, mutate=None):
    """every output of run a equals run b: PCAP and per-frame logs byte for byte; .vec / .sca without the run header
    (config name normalised); .elog event / message lines and the UPF MAC-table log lines (the MAC-log lines and the
    eventlog's index / snapshot records, whose byte offsets move with the file size, excluded); .vci (byte offsets
    of the .vec) excluded; fingerprints from the run logs equal. Returns (ok, detail)."""
    def files(c):
        out = {}
        for r_, _, fs in os.walk(os.path.join(runs, c)):
            for fn in fs:
                p = os.path.join(r_, fn)
                out[os.path.relpath(p, os.path.join(runs, c)).replace(c, "<config>")] = p
        return out
    fa, fb = files(a), files(b)
    if mutate:
        fb = dict(fb)
        fb[mutate[0]] = mutate[1]
    probs = []
    if set(fa) != set(fb):
        probs.append(f"file sets differ {sorted(set(fa) ^ set(fb))[:4]}")
    n = Counter()
    for k in sorted(set(fa) & set(fb)):
        kind = "vec" if k.endswith(".vec") else "sca" if k.endswith(".sca") else "elog" if k.endswith(".elog") else "skip" if k.endswith(".vci") else "raw"
        if kind == "skip":
            n["vci excluded"] += 1
            continue
        if file_digest(fa[k], a, kind) != file_digest(fb[k], b, kind):
            probs.append(f"{k} differs")
        n[kind] += 1
    fps = []
    for c in (a, b):
        p = os.path.join(runs, f"run-{c}.log.gz")
        fp = None
        if os.path.exists(p):
            with gzip.open(p, "rt", errors="replace") as fh:
                for line in fh:
                    if "Fingerprint" in line:
                        mm = re.search(r"calculated: (\S+),", line)
                        fp = mm.group(1) if mm else None
        fps.append(fp)
    if fps[0] is None or fps[0] != fps[1]:
        probs.append(f"fingerprints {fps}")
    return not probs, f"{dict(n)} compared; fingerprints {fps}" + ("" if not probs else "; DIFFERENT: " + "; ".join(probs[:5]))


# ---------------------------------------------------------------------------------------------------- controls -----
# declared before any E0 run (results/M2-S7.2a-e0-protocol.md §6): each must fail exactly these gate families
PRED = {"NC-q8-deliv": {"Q8"}, "NC-q8-seg": {"Q8"}, "NC-q8-noevid": {"Q8"}, "NC-maclog-del": {"Q8-x"},
        "PC-q8-lost": set()}          # positive control: the same loss WITH an observed HARQ deletion is "lost", Q8 passes
PRED_NONPERT = "DIFFERENT"
CTRL_CFG = ("M2S72-E0-q0-f1", "q0", 1)


def controls(runs, out):
    cfg, opt, f = CTRL_CFG
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    res = []
    # the delivered Sync in the middle of the run
    start = len(rows)
    ev, q, _, _ = evaluate(runs, cfg, opt, f, mlp, gates=False)
    del rows[start:]
    dl = sorted(k for k, x in q.fate.items() if x[0] == "delivered" and k[0] == SYNC and k in q.sdu_of)
    k = dl[len(dl) // 2]
    sdu = q.sdu_of[k]
    tl = {(a, s): t for a, s, t in q.done}[sdu]
    deliv = next(m_ for m_ in q.matched if (m_[0], m_[1]) == sdu)
    own = L.pdu_owner(q.sdus_h, q.pdus_h)
    idx = {(a, s): i for i, (a, s, _) in enumerate(q.done)}[sdu]
    pdu = next(q.pdus_h[j] for j, o in enumerate(own) if o == idx)
    got, _ = G.pdu_receptions(q.pdus_h, q.rxpdus)
    rx = sorted(x for x in q.rxpdus if x[1] == pdu[1] and pdu[0] <= x[0] <= pdu[0] + G.AIR)
    muts = {"NC-q8-deliv": {"drop_deliv": ((deliv[3], deliv[1]), k)},
            "NC-q8-seg": {"seg": True},
            "NC-q8-noevid": {"drop_rxpdu": rx[0] if rx else None, "drop_deliv": ((deliv[3], deliv[1]), k)},
            "NC-maclog-del": {"fake_deletion": tl},
            "PC-q8-lost": {"drop_rxpdu": rx[0] if rx else None, "drop_deliv": ((deliv[3], deliv[1]), k), "fake_deletion": pdu[0]}}
    for name, mut in muts.items():
        start = len(rows)
        _, qm, _, _ = evaluate(runs, cfg, opt, f, mlp, mut=mut, gates=False)
        mine = rows[start:]
        del rows[start:]
        fails = {r[0] for r in mine if r[2] == "FAIL"}
        ok = fails == PRED[name]
        if name == "PC-q8-lost":
            fk = qm.fate.get(k)
            ok = ok and fk is not None and fk[0] == "lost" and "HARQ-process MAC PDU deletion" in fk[2]
            mine = mine + [("PC-q8-lost", "fate", "PASS" if ok else "FAIL", f"Sync {k}: {fk}")]
        res.append((name, ok, fails, PRED[name], mine))
    # non-perturbation comparator canary: one PCAP byte of the twin changed in a copy
    a, b = twin(runs)
    tmp = tempfile.mkdtemp(prefix="m2s72e0np-")
    try:
        rel = None
        for r_, _, fs in os.walk(os.path.join(runs, b, "pcap")):
            for fn in sorted(fs):
                if "dsTt[0].pcapRecorder[0]" in fn:
                    rel = os.path.join(r_, fn)
        cp = os.path.join(tmp, "x.pcapng")
        shutil.copy(rel, cp)
        with open(cp, "r+b") as fh:
            fh.seek(os.path.getsize(cp) // 2)
            c = fh.read(1)
            fh.seek(-1, 1)
            fh.write(bytes([c[0] ^ 1]))
        key = os.path.relpath(rel, os.path.join(runs, b)).replace(b, "<config>")
        ok, det = nonpert(runs, a, b, mutate=(key, cp))
        res.append(("NC-nonpert", (not ok) == (PRED_NONPERT == "DIFFERENT"), {"nonpert"} if not ok else set(), {"nonpert"}, [("nonpert", "canary", "FAIL" if not ok else "PASS", det)]))
    finally:
        shutil.rmtree(tmp)
    return res, k


# -------------------------------------------------------------------------------------------------------- main -----
def quick(runs, cfg):
    run = R.Run72(runs, cfg, 0)
    T = B.F1.t_end(run)
    gm = [f["seq"] for f in run.gm if f["dir"] == 2 and f["type"] == SYNC and f["dom"] == 0 and f["start"] < T_COHORT]
    got = {f["seq"] for f in run.ue_view(0).ds0 if f["dir"] == 1 and f["type"] == SYNC and f["dom"] == 0 and f["end"] <= T}
    miss = sum(1 for s in gm if s not in got)
    print(f"{cfg}: cohort GM Syncs {len(gm)}, not received by DS-TT 0 by T_end {miss} ({miss / max(1, len(gm)):.4f})")
    return miss / max(1, len(gm))


def fmt(v):
    if isinstance(v, float):
        return "inf" if v == INF else f"{v:.6g}"
    return str(v)


def main(out):
    runs = os.path.join(out, "runs")
    P = print
    P("M2-S7.2a Stage 5 E0 capacity calibration check (protocol results/M2-S7.2a-e0-protocol.md)\n")
    allm, per_run = [], []
    for cfg, opt, f in cfgs():
        name = f"{cfg}-0"
        start = len(rows)
        if not os.path.isdir(os.path.join(runs, cfg)):
            add("RUN", name, NE, "run not present (escalation stop or not run: see e0-runs.txt)")
            continue
        try:
            ev, q, m, fails = evaluate(runs, cfg, opt, f, os.path.join(runs, f"run-{cfg}.log.gz"))
        except Exception as ex:            # a checker that cannot evaluate a run fails that run
            import traceback
            add("X", name, False, f"evaluation error {type(ex).__name__}: {ex} {traceback.format_exc()[-600:]}")
            continue
        m["onset"] = onset(m)
        allm.append(m)
        fam = [r for r in rows[start:] if r[0] not in INFO]
        per_run.append((name, sum(r[2] == "PASS" for r in fam), sum(r[2] == "FAIL" for r in fam),
                        sorted({r[0] for r in fam if r[2] == "FAIL"}), sorted({r[0] for r in rows[start:] if r[2] in (NA, NE)})))
    # non-perturbation
    tw = twin(runs)
    if tw and os.path.isdir(os.path.join(runs, tw[0])):
        ok, det = nonpert(runs, *tw)
        add("NONPERT", f"{tw[0]} vs {tw[1]}", ok, det)
    else:
        add("NONPERT", "MAC-log twin", False, f"twin pair missing ({tw}): the non-perturbation proof is mandatory")
    ctrl, ck = controls(runs, out) if os.path.isdir(os.path.join(runs, CTRL_CFG[0])) and tw else ([], None)
    # report
    for r in rows:
        P(" | ".join(r))
    by = Counter((r[0], r[2]) for r in rows)
    P("\nrows per family: " + ", ".join(f"{g} " + "/".join(f"{by[(g, s)]} {s}" for s in ("PASS", "FAIL", NA, NE) if by[(g, s)]) for g in sorted({r[0] for r in rows})))
    nf = sum(1 for r in rows if r[2] == "FAIL" and r[0] not in INFO)
    ng = sum(1 for r in rows if r[0] not in INFO and r[2] in ("PASS", "FAIL"))
    P(f"gate rows: {ng - nf} PASS, {nf} FAIL; information rows {sorted(INFO)}; NOT APPLICABLE {sum(1 for r in rows if r[2] == NA)}, "
      f"NOT EVALUATED {sum(1 for r in rows if r[2] == NE)}")
    P("\nper run: run | gate rows PASS / FAIL | failing families | NOT APPLICABLE / NOT EVALUATED families")
    for x in per_run:
        P(" | ".join(str(v) for v in x))
    keys = ["run", "option", "factor", "dl_offered_cfg_Mbps", "dl_offered_rlc_Mbps", "dl_achieved_rlc_Mbps", "dl_app_achieved_Mbps",
            "mac_dl_grant_Mbps", "mac_dl_tti_share", "ul_offered_Mbps", "ul_achieved_Mbps", "backlog_end_bytes", "sustained_growth",
            "rlc_left_sdus_end", "load_drb1_backlog_end_bytes", "load_drb1_sustained_growth", "mac_harq_deletions", "mac_max_busy_harq", "mac_nack", "mac_overflow", "sca_macBufferOverFlowDl_samples",
            "mac_rlc_tx_drops", "mac_unclassified", "cohort_n", "P_used_cohort", "censored_cohort_fraction", "first_lost_or_censored_pair",
            "res_p50_ms", "res_p99_ms", "res_delivered_max_ms", "lag_p99_ms", "deadline_res_gt_5p5ms", "deadline_lag_gt_sync_interval",
            "max_e_ns", "update_gap_max_ms", "slave_updates", "holds"]
    P("\nmetrics per run (reported, never gated):")
    P(" | ".join(keys))
    for m in allm:
        P(" | ".join(fmt(m.get(k)) for k in keys))
    P("\nper run detail: Q8 frames, undelivered by location, pairs, backlog (0.5 s steps), per-second offered / achieved DL bytes, "
      "MAC minimum buffer space, stage latencies, onset flags")
    for m in allm:
        P(f"{m['run']}: q8 {m['q8_frames']}; undelivered {m['q8_undelivered_by_location']}; pairs {m['pairs']}; cohort {m['cohort_pairs']}")
        P(f"    backlog {m['backlog_bytes_per_0p5s']}")
        P(f"    window minima [4 s .. 12 s) {m['backlog_window_min']}")
        P(f"    load DRB 1 backlog {m['load_drb1_backlog_per_0p5s']}")
        P(f"    load DRB 1 window minima {m['load_drb1_window_min']}; accounting {m['load_drb1_accounting']}")
        P(f"    DL offered / s {m['dl_offered_rlc_per_s']}")
        P(f"    DL achieved / s {m['dl_achieved_rlc_per_s']}")
        P(f"    MAC min space {m.get('mac_min_space')}; DL grant bytes per lcid {m.get('mac_dl_grant_bytes_per_lcid')}; load SDU sizes {m['rlc_load_sdu_size']}; "
          f"DL load frames listener egress / talker ingress {m['dl_load_frames']}")
        P(f"    stage latency max (us) {m['stage_latency_max_us']}")
        P(f"    onset {m['onset']}")
    nc = 0
    P("\nnegative controls (predictions in results/M2-S7.2a-e0-protocol.md §6; each must fail exactly its predicted families):")
    for name, ok, fails, exp, mine in ctrl:
        nc += not ok
        P(f"{'PASS' if ok else 'FAIL'} | {name} | failed {sorted(fails)}, predicted {sorted(exp)}")
        for r in mine:
            if r[2] == "FAIL":
                P("      " + " | ".join(r)[:500])
    if not ctrl:
        P("controls NOT EVALUATED (control run or twin missing)")
        nc += 1
    P(f"control mutations target Sync {ck}")
    P(f"controls: {len(ctrl) - nc if ctrl else 0} PASS, {nc} FAIL")
    with open(os.path.join(out, "e0-metrics.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(keys + ["q8_frames", "q8_undelivered_by_location", "pairs", "cohort_pairs", "backlog_window_min", "onset"])
        for m in allm:
            w.writerow([fmt(m.get(k)) for k in keys] + [m["q8_frames"], m["q8_undelivered_by_location"], m["pairs"], m["cohort_pairs"],
                                                        m["backlog_window_min"], m["onset"]])
    verdict = nf == 0 and nc == 0
    P("E0 correctness verdict: " + ("PASS (calibration results are reported above; STOP for review)" if verdict else "FAIL (stop and report)"))
    return 0 if verdict else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "quick":
        quick(sys.argv[2], sys.argv[3])
        sys.exit(0)
    if len(sys.argv) > 1 and sys.argv[1] == "nonpert":
        ok, det = nonpert(sys.argv[2], sys.argv[3], sys.argv[4])
        print(("IDENTICAL " if ok else "DIFFERENT ") + det)
        sys.exit(0 if ok else 1)
    sys.exit(main(sys.argv[1]))
