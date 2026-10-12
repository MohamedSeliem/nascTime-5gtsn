#!/usr/bin/env python3
"""Investigation of O-S3-1: frames accepted by RLC TX but not delivered by RLC RX under
saturating load (Config S3-load). Each candidate cause gets a criterion that the
evidence either meets or not; nothing here changes what check_s3 tests.

Inputs (o_s3_1_investigation.sh): Config O1-drain (S3-load whose sources stop at 3 s,
run to 5 s), O1-harq16 (the same with 16 instead of 5 HARQ processes), seeds 0..4, and
filtered Simu5G MAC debug logs of seed 0 of both (O1-*-trace, same runs plus logging).

Rows:
  frame loss reproduced     O1-drain: frames are missing although the sources stopped
                            2 s before the end; accounting per flow
  H1 end of run             EXCLUDED if every flow's last delivery is long before the end
                            (>= 1.5 s idle) while frames are still missing
  H2 queue overflow         EXCLUDED if no frame is lost before RLC (sent = RLC TX in) and
                            the MAC buffer-overflow statistic never fired (Simu5G emits it
                            on every MAC queue drop; the NR RLC UM TX buffer is unbounded)
  H3 radio loss             EXCLUDED if every transport block was acknowledged at the
                            first transmission (trace: HARQ feedback all ACK; statistics:
                            HARQ error rate 0, 1 attempt) -- no TB was lost on the air
  H4 MAC discard            CONFIRMED if, per direction, the RLC PDUs inside MAC PDUs that
                            the MAC deleted because no HARQ process was free (Simu5G
                            LteMacEnb/LteMacUe::macPduMake: "no available process for this
                            MAC PDU in TxHarqBuffer") equal exactly the RLC PDUs buffered
                            at the TX MAC minus those extracted at the RX MAC, and equal
                            the RLC PDU deficit in the recorded statistics
  HARQ round trip           the measured TB-to-feedback time in slots, against the number
                            of HARQ processes (5)
  H5 instrumentation        CONFIRMED if no recorded statistic reports these discards
  counterfactual            O1-harq16: no discard event, every RLC PDU delivered, and the
                            frame loss gone (a residual is reported, not hidden)
Usage: check_o_s3_1.py <results dir containing O-S3-1/>
"""
import os
import re
import sys
from collections import Counter, defaultdict

import pandas as pd

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = os.path.join(RES, "O-S3-1")
STOP, END = 3.0, 5.0
FLOWS = {f"pcp{p}": (100 + 20 * p, True) for p in range(8)}
FLOWS["untagged"] = (300, False)
FLOWS["bg"] = (1400, True)
APP = {f: i for i, f in enumerate(list(FLOWS)[:9])}
APP["bg"] = 10
FRAME = {f: 14 + (4 if t else 0) + pl for f, (pl, t) in FLOWS.items()}
SINKLEN = {f: pl + (4 if t else 0) for f, (pl, t) in FLOWS.items()}
DIRS = {"UL": ("talker", "listener", "ue[0]", "gnb1"), "DL": ("listener", "talker", "gnb1", "ue[0]")}
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(name):
    d = pd.read_csv(os.path.join(OUT, name + ".csv"), low_memory=False)
    d = d[d.run.notna()].copy()
    d["seed"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
    d["mod"] = d.module.fillna("").str.replace("M1Bridge.", "", regex=False)
    return d


def vec(d, seed, mod_pred, name):
    r = d[(d.seed == seed) & (d.type == "vector") & (d.name == name) & d["mod"].map(mod_pred)]
    out = {}
    for m, t, v in zip(r["mod"], r.vectime, r.vecvalue):
        out[m] = list(zip(map(float, t.split()), map(float, v.split()))) if isinstance(t, str) else []
    return out


def scalar(d, seed, mod, name):
    r = d[(d.seed == seed) & (d.type == "scalar") & (d["mod"] == mod) & (d.name == name)].value
    return float(r.iloc[0]) if len(r) == 1 else float("nan")


def flow_of(size):
    for f, L in FRAME.items():
        if L <= size <= L + 3:
            return f
    return None


def accounting(d, seed):
    """per direction: {flow: (sent, rlc tx in, rlc rx out, received, last rx time)}."""
    res = {}
    for dirn, (src, snk, txn, rxn) in DIRS.items():
        tx, rx = Counter(), Counter()
        for m, tv in vec(d, seed, lambda m, n=txn: m.startswith(n + ".cellularNic.") and "-um-" in m and m.endswith(".tx"),
                         "receivedPacketFromUpperLayer:vector(packetBytes)").items():
            tx.update(flow_of(int(v)) for _, v in tv)
        for m, tv in vec(d, seed, lambda m, n=rxn: m.startswith(n + ".cellularNic.") and "-um-" in m and m.endswith(".rx"),
                         "sentPacketToUpperLayer:vector(packetBytes)").items():
            rx.update(flow_of(int(v)) for _, v in tv)
        sink = vec(d, seed, lambda m, s=snk: m == f"{s}.app[9].sink", "packetLengths:vector").get(f"{snk}.app[9].sink", [])
        recv, last = Counter(), defaultdict(float)
        for t, v in sink:
            for f in FLOWS:
                if SINKLEN[f] == int(v) // 8:
                    recv[f] += 1
                    last[f] = max(last[f], t)
        sent = {}
        for f in FLOWS:
            m = f"{src}.app[{APP[f]}].io"
            sent[f] = len(vec(d, seed, lambda x, m=m: x == m, "packetSent:vector(packetBytes)").get(m, []))
        res[dirn] = {f: (sent[f], tx[f], rx[f], recv[f], last[f]) for f in FLOWS}
    return res


def rlc_pdus(d, seed, node, side):
    stat = "sentPacketToLowerLayer:count" if side == "tx" else "receivedPacketFromLowerLayer:count"
    r = d[(d.seed == seed) & (d.type == "scalar") & d["mod"].str.startswith(node + ".cellularNic.")
          & d["mod"].str.contains("-um-") & d["mod"].str.endswith("." + side) & (d.name == stat)]
    return int(r.value.astype(float).sum())


def trace(path):
    """MAC events per module: buffered RLC PDUs, extracted RLC PDUs, discarded MAC PDUs and
    the RLC PDUs inside them, HARQ insertions/feedback and round-trip times in slots."""
    ev = defaultdict(Counter)
    rtt = Counter()
    last_made, inserted = {}, {}
    for line in open(path):
        m = re.match(r"([0-9.e-]+) (mac|nrMac) [^|]*\| (.*)", line)
        if not m:
            continue
        t, mod, msg = float(m.group(1)), m.group(2), m.group(3)
        if "created PDU" in msg:
            last_made[mod] = int(re.search(r"containing (\d+) SDUs", msg).group(1))
            ev[mod]["mac_pdus"] += 1
        elif "no available process for this MAC PDU" in msg:
            ev[mod]["discarded_mac_pdus"] += 1
            ev[mod]["discarded_rlc_pdus"] += last_made[mod]
        elif msg.startswith("LteMacBuffers : Using buffer"):
            ev[mod]["buffered"] += 1
        elif "extracted SDU" in msg:
            ev[mod]["extracted"] += 1
        else:
            a = re.search(r"new pdu \(id \d+ \) inserted into process (\d+)", msg)
            b = re.search(r"feedback received for process (\d+) codeword \d+ result is (\w+)", msg)
            if a:
                inserted[(mod, a.group(1))] = t
                ev[mod]["harq_inserted"] += 1
            elif b:
                ev[mod]["fb_" + b.group(2)] += 1
                if (mod, b.group(1)) in inserted:
                    rtt[round((t - inserted.pop((mod, b.group(1)))) * 1000)] += 1
    return ev, rtt


# --- O1-drain ---------------------------------------------------------------------------
dr = load("O1-drain")
seeds = sorted(int(s) for s in dr.seed.unique())
acc = {s: accounting(dr, s) for s in seeds}
lost = {dirn: sum(a[dirn][f][1] - a[dirn][f][2] for a in acc.values() for f in FLOWS) for dirn in DIRS}
txin = {dirn: sum(a[dirn][f][1] for a in acc.values() for f in FLOWS) for dirn in DIRS}
per_flow = {dirn: sorted((1 - sum(a[dirn][f][2] for a in acc.values()) / sum(a[dirn][f][1] for a in acc.values()), f)
                         for f in FLOWS) for dirn in DIRS}
add("frame loss reproduced (O1-drain, sources stop at 3 s, run to 5 s)",
    "; ".join(f"{dirn}: {lost[dirn]} of {txin[dirn]} frames accepted by RLC TX never left RLC RX "
              f"(per flow {per_flow[dirn][0][0]:.1%}..{per_flow[dirn][-1][0]:.1%})" for dirn in DIRS)
    + f"; seeds {seeds}", all(lost[x] > 0 for x in DIRS))

last_rx = max(a[dirn][f][4] for a in acc.values() for dirn in DIRS for f in FLOWS)
missing = sum(lost.values())
add("H1 frames in flight at the end of the run: EXCLUDED",
    f"last delivery of any frame at {last_rx:.3f} s, {END - last_rx:.2f} s before the end; {missing} frames still missing",
    END - last_rx >= 1.5 and missing > 0)

pre = [(s, dirn, f, a[dirn][f][0], a[dirn][f][1]) for s, a in acc.items() for dirn in DIRS for f in FLOWS
       if a[dirn][f][0] != a[dirn][f][1]]
ovf = [scalar(dr, s, m, f"macBufferOverFlow{x}:mean") for s in seeds
       for m in ("gnb1.cellularNic.mac", "ue[0].cellularNic.nrMac") for x in ("Dl", "Ul")]
add("H2 queue overflow: EXCLUDED",
    f"frames lost before RLC: {len(pre)}; MAC buffer-overflow statistic fired: {sum(not pd.isna(x) for x in ovf)} of {len(ovf)} "
    "(gNB/UE x DL/UL x seeds); NR RLC UM TX buffer is unbounded in Simu5G 1.8.0",
    not pre and all(pd.isna(x) for x in ovf))

ev, rtt = trace(os.path.join(OUT, "runs", "trace-O1-drain-trace.log"))
tr = load("O1-drain-trace")
harq = {x: scalar(tr, 0, "ue[0].cellularNic.nrMac", f"harqErrorRate{x}:mean") for x in ("Dl", "Ul")}
att = {x: scalar(tr, 0, "ue[0].cellularNic.nrMac", f"harqTxAttempts{x}:mean") for x in ("Dl", "Ul")}
fb = {m: (ev[m]["harq_inserted"], ev[m]["fb_ACK"], sum(v for k, v in ev[m].items() if k.startswith("fb_") and k != "fb_ACK"))
      for m in ("mac", "nrMac")}
add("H3 radio loss: EXCLUDED (seed 0 trace)",
    f"TBs into HARQ / ACKed / other feedback: DL {fb['mac']}, UL {fb['nrMac']}; HARQ error rate DL {harq['Dl']:g}, "
    f"UL {harq['Ul']:g}; mean attempts DL {att['Dl']:g}, UL {att['Ul']:g}",
    all(i == a and o == 0 for i, a, o in fb.values()) and harq["Dl"] == 0 and harq["Ul"] == 0
    and att["Dl"] == 1 and att["Ul"] == 1)

stat_def = {"DL": rlc_pdus(tr, 0, "gnb1", "tx") - rlc_pdus(tr, 0, "ue[0]", "rx"),
            "UL": rlc_pdus(tr, 0, "ue[0]", "tx") - rlc_pdus(tr, 0, "gnb1", "rx")}
h4, det = True, []
for dirn, txm, rxm in (("DL", "mac", "nrMac"), ("UL", "nrMac", "mac")):
    gap = ev[txm]["buffered"] - ev[rxm]["extracted"]
    disc = ev[txm]["discarded_rlc_pdus"]
    h4 &= gap == disc == stat_def[dirn] and disc > 0
    det.append(f"{dirn}: RLC PDUs buffered at TX MAC {ev[txm]['buffered']}, extracted at RX MAC {ev[rxm]['extracted']}, "
               f"gap {gap}; inside {ev[txm]['discarded_mac_pdus']} of {ev[txm]['mac_pdus']} MAC PDUs deleted for lack of a "
               f"free HARQ process: {disc}; RLC PDU deficit in statistics: {stat_def[dirn]}")
add("H4 MAC PDUs deleted when no HARQ process is free: CONFIRMED (seed 0 trace)", " | ".join(det), h4)

add("HARQ round trip vs HARQ processes",
    f"TB to feedback: {dict(sorted(rtt.items()))} (slots of 1 ms: count); harqProcesses = 5 at gNB and UE (NR default in "
    "Simu5G 1.8.0): with the UE scheduled in every slot, all 5 processes can be busy when the next TB is built",
    set(rtt) == {5})

lossstats = {f"{m} {n}": scalar(tr, 0, m, n) for m in ("gnb1.cellularNic.mac", "ue[0].cellularNic.nrMac")
             for n in ("macPacketLossDl:mean", "macPacketLossUl:mean", "macCellPacketLossDl:mean",
                       "macCellPacketLossUl:mean", "macBufferOverFlowDl:mean", "macBufferOverFlowUl:mean")}
reported = {k: v for k, v in lossstats.items() if not pd.isna(v) and v != 0}
add("H5 no statistic records the deletions: CONFIRMED",
    f"{ev['mac']['discarded_rlc_pdus'] + ev['nrMac']['discarded_rlc_pdus']} RLC PDUs deleted; MAC loss/overflow statistics "
    f"non-zero: {reported or 'none'}; the deletion is reported only in the MAC debug log",
    not reported and ev["mac"]["discarded_rlc_pdus"] + ev["nrMac"]["discarded_rlc_pdus"] > 0)

# --- counterfactual: 16 HARQ processes ---------------------------------------------------
hq = load("O1-harq16")
hseeds = sorted(int(s) for s in hq.seed.unique())
hacc = {s: accounting(hq, s) for s in hseeds}
hlost = {dirn: sum(a[dirn][f][1] - a[dirn][f][2] for a in hacc.values() for f in FLOWS) for dirn in DIRS}
htx = {dirn: sum(a[dirn][f][1] for a in hacc.values() for f in FLOWS) for dirn in DIRS}
resid = [(s, dirn, f, a[dirn][f][1] - a[dirn][f][2]) for s, a in hacc.items() for dirn in DIRS for f in FLOWS
         if a[dirn][f][1] != a[dirn][f][2]]
hev, hrtt = trace(os.path.join(OUT, "runs", "trace-O1-harq16-trace.log"))
hdisc = hev["mac"]["discarded_mac_pdus"] + hev["nrMac"]["discarded_mac_pdus"]
hgap = (hev["mac"]["buffered"] - hev["nrMac"]["extracted"], hev["nrMac"]["buffered"] - hev["mac"]["extracted"])
add("counterfactual: 16 HARQ processes (O1-harq16)",
    f"seed-0 trace: MAC PDUs deleted {hdisc}, RLC PDU gap DL/UL {hgap}; frames missing after drain: "
    f"UL {hlost['UL']} of {htx['UL']}, DL {hlost['DL']} of {htx['DL']} (O1-drain: UL {lost['UL']}, DL {lost['DL']}); "
    f"residual (seed, dir, flow, frames): {resid or 'none'}",
    hdisc == 0 and hgap == (0, 0) and sum(hlost.values()) <= 0.01 * sum(lost.values()))

# residual (O-S3-2): is the missing frame the last SDU that entered the gNB's DRB 1?
res_det, res_ok = [], bool(resid)
for s_ in hseeds:
    m = "gnb1.cellularNic.rlc-um-2049-1.tx"
    sdus = vec(hq, s_, lambda x: x == m, "receivedPacketFromUpperLayer:vector(packetBytes)").get(m, [])
    pdus = vec(hq, s_, lambda x: x == m, "sentPduSize:vector").get(m, [])
    t_last, size_last = sdus[-1]
    after = [int(v) for t, v in pdus if t >= t_last]
    mine = [r for r in resid if r[0] == s_]
    res_ok &= len(mine) == 1 and mine[0][1] == "DL" and mine[0][2] == flow_of(int(size_last)) and mine[0][3] == 1
    res_det.append(f"seed {s_}: last SDU into gNB DRB 1 at {t_last:.6f} s, {int(size_last)} B ({flow_of(int(size_last))}); "
                   f"RLC PDUs sent after it: {after} B")
add("residual with 16 processes = the last DL SDU of the run (open item O-S3-2)", " | ".join(res_det), res_ok)

# --- print -----------------------------------------------------------------------------
w = max(len(r[0]) for r in rows)
for c, d_, v in rows:
    print(f"{v:4}  {c:<{w}}  {d_}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
