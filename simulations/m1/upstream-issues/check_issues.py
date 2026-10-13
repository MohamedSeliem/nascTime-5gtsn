#!/usr/bin/env python3
"""Evidence for the three Simu5G 1.8.0 issue reproductions (issues.ini), from recorded
statistics and the MAC debug log only. Usage: check_issues.py <output dir of run_issues.sh>"""
import os
import re
import sys
from collections import Counter

import pandas as pd

OUT = sys.argv[1]
MS = 1e-3
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(name):
    d = pd.read_csv(os.path.join(OUT, name + ".csv"), low_memory=False)
    d = d[d.run.notna()].copy()
    d["mod"] = d.module.fillna("").str.replace("EthernetSessions.", "", regex=False)
    return d


def vec(d, mod, name):
    r = d[(d.type == "vector") & (d["mod"] == mod) & (d.name == name)]
    if len(r) != 1 or not isinstance(r.vectime.iloc[0], str):
        return []
    return list(zip(map(float, r.vectime.iloc[0].split()), map(float, r.vecvalue.iloc[0].split())))


def sc(d, mod, name):
    r = d[(d.type == "scalar") & (d["mod"] == mod) & (d.name == name)].value
    return float(r.iloc[0]) if len(r) == 1 else float("nan")


def rlc_pdus(d, node, side):
    stat = "sentPacketToLowerLayer:count" if side == "tx" else "receivedPacketFromLowerLayer:count"
    r = d[(d.type == "scalar") & d["mod"].str.startswith(node + ".cellularNic.") & d["mod"].str.contains("-um-")
          & d["mod"].str.endswith("." + side) & (d.name == stat)]
    return int(r.value.astype(float).sum())


def deficit(d):
    return {"DL": rlc_pdus(d, "gnb1", "tx") - rlc_pdus(d, "ue[0]", "rx"),
            "UL": rlc_pdus(d, "ue[0]", "tx") - rlc_pdus(d, "gnb1", "rx")}


# ---- Issue 1 ---------------------------------------------------------------------------
d1, d16 = load("Issue1-HarqDiscard"), load("Issue1-HarqDiscard-16proc")
df1, df16 = deficit(d1), deficit(d16)
sent = {"DL": sum(sc(d1, f"dnStation.app[{i}].io", "packetSent:count") for i in (0, 1, 3)),
        "UL": sum(sc(d1, f"device[0].app[{i}].io", "packetSent:count") for i in (0, 1, 3))}
recv = {"DL": sc(d1, "device[0].app[2].sink", "packets:count"), "UL": sc(d1, "dnStation.app[2].sink", "packets:count")}
last = max(t for m in ("device[0].app[2].sink", "dnStation.app[2].sink") for t, _ in vec(d1, m, "packetLengths:vector"))
add("Issue 1: frames lost although every source stopped 2 s before the end",
    f"frames sent/received DL {int(sent['DL'])}/{int(recv['DL'])}, UL {int(sent['UL'])}/{int(recv['UL'])}; last delivery "
    f"{last:.3f} s; RLC PDUs sent but never received by the peer RLC: DL {df1['DL']}, UL {df1['UL']}",
    df1["DL"] > 0 and df1["UL"] > 0 and last < 3.5)
harq = {k: sc(d1, "ue[0].cellularNic.nrMac", k) for k in ("harqErrorRateDl:mean", "harqErrorRateUl:mean",
                                                             "harqTxAttemptsDl:mean", "harqTxAttemptsUl:mean")}
loss = {f"{m} {k}": sc(d1, m, k) for m in ("gnb1.cellularNic.mac", "ue[0].cellularNic.nrMac")
        for k in ("macBufferOverFlowDl:mean", "macBufferOverFlowUl:mean", "macPacketLossDl:mean", "macPacketLossUl:mean")}
reported = {k: v for k, v in loss.items() if v == v and v != 0}
add("Issue 1: not radio loss, not queue overflow, and no statistic reports it",
    f"UE HARQ {harq}; MAC loss/overflow statistics that are non-zero: {reported or 'none'}",
    harq["harqErrorRateDl:mean"] == 0 and harq["harqErrorRateUl:mean"] == 0 and harq["harqTxAttemptsDl:mean"] == 1
    and harq["harqTxAttemptsUl:mean"] == 1 and not reported)
ev, last_n = Counter(), {}
for line in open(os.path.join(OUT, "trace-Issue1.log")):
    m = re.match(r"\S+ (mac|nrMac) \| (.*)", line)
    if not m:
        continue
    mod, msg = m.groups()
    if "created PDU" in msg:
        last_n[mod] = int(re.search(r"containing (\d+) SDUs", msg).group(1))
    elif "no available process" in msg:
        ev[(mod, "deleted_mac")] += 1
        ev[(mod, "deleted_rlc")] += last_n[mod]
    elif "Using buffer for" in msg:
        ev[(mod, "buffered")] += 1
    elif "extracted SDU" in msg:
        ev[(mod, "extracted")] += 1
gap = {"DL": ev[("mac", "buffered")] - ev[("nrMac", "extracted")], "UL": ev[("nrMac", "buffered")] - ev[("mac", "extracted")]}
dele = {"DL": ev[("mac", "deleted_rlc")], "UL": ev[("nrMac", "deleted_rlc")]}
add("Issue 1: the missing RLC PDUs are exactly those inside MAC PDUs deleted for lack of a HARQ process (trace: sources stop at 0.4 s, run to 0.6 s)",
    f"RLC PDUs buffered at TX MAC - extracted at RX MAC: {gap}; inside deleted MAC PDUs "
    f"('no available process for this MAC PDU in TxHarqBuffer'): {dele} in "
    f"{ev[('mac', 'deleted_mac')]} DL / {ev[('nrMac', 'deleted_mac')]} UL MAC PDUs",
    gap == dele and dele["DL"] > 0 and dele["UL"] > 0)
add("Issue 1: counterfactual with 16 HARQ processes",
    f"RLC PDUs sent but never received: {df16}", df16 == {"DL": 0, "UL": 0})

# ---- Issue 2 ---------------------------------------------------------------------------
TX, RX = "gnb1.cellularNic.rlc-um-2049-1.tx", "ue[0].cellularNic.nrRlc-um-1-1.rx"


def replay(d):
    sdus = vec(d, TX, "receivedPacketFromUpperLayer:vector(packetBytes)")
    pdus = vec(d, TX, "sentPduSize:vector")
    q, i, slots, done = [], 0, {}, []
    for t, s in pdus:
        while i < len(sdus) and sdus[i][0] <= t:
            q.append([sdus[i][0], int(sdus[i][1]), 0])
            i += 1
        sl = slots.setdefault(t, {"pdus": [], "before": [(x[1] - x[2], x[2] == 0) for x in q], "cut": False})
        s, h = int(s), q[0]
        if h[2] == 0:
            pay = h[1] if s == h[1] + 1 else s - 2
            sl["cut"] |= pay < h[1]
        else:
            pay = s - 4
        sl["pdus"].append(s)
        h[2] += pay
        if h[2] >= h[1]:
            done.append((h[0], h[1], t))
            q.pop(0)
    return sdus, slots, done, q


d2, d2a = load("Issue2-DlTailLag"), load("Issue2-DlTailLag-apart")
sdus, slots, done, left = replay(d2)
rx = vec(d2, RX, "sentPacketToUpperLayer:vector(packetBytes)")
match = len(rx) == len(done) and all(abs(rt - (c + 4 * MS)) < 1e-9 for (_, _, c), (rt, _) in zip(done, rx))
cuts = {t: s for t, s in slots.items() if s["cut"]}
short = all(sum(r for r, _ in s["before"]) + 3 <= sum(s["pdus"]) + 2 < sum(r + (1 if f else 4) for r, f in s["before"]) + 2
            and len(s["before"]) >= 2 for s in cuts.values())
arr = [t for t, _ in sdus]
def held(t):
    nxt_pdu = next((x for x in sorted(slots) if x > t), None)
    nxt_arr = next((a for a in arr if a > t), None)
    return nxt_pdu is None or (nxt_arr is not None and nxt_pdu > nxt_arr)


strand = all(held(t) for t in cuts)
dly = [v for _, v in vec(d2, "device[0].app[2].sink", "meanBitLifeTimePerPacket:vector")]
dly_a = [v for _, v in vec(d2a, "device[0].app[2].sink", "meanBitLifeTimePerPacket:vector")]
add("Issue 2: replay of the gNB DRB 1 RLC from recorded PDU sizes predicts every DL delivery",
    f"{len(done)} SDUs completed, {len(rx)} delivered at the UE RLC exactly 4 ms after completion: {match}", match and len(done) > 0)
add("Issue 2: SDUs are cut only when >= 2 are queued; grant >= queued bytes + 2 B MAC + ONE 1 B RLC header, < what the PDUs need",
    f"{len(cuts)} slots with a cut; condition holds in all: {short}; remainder held until the next SDU arrives in all: {strand}",
    len(cuts) > 0 and short and strand)
add("Issue 2: effect on delay and delivery",
    f"device[0] DL delays: {Counter(round(x * 1e3) for x in dly).most_common(4)} ms (count); with the flows 2 ms apart: "
    f"{Counter(round(x * 1e3) for x in dly_a).most_common(3)}; SDUs left in the gNB RLC 2 s after the last arrival: "
    f"{[(round(a, 6), s, s - n) for a, s, n in left]} (arrival, size, bytes unsent)",
    max(dly) > 0.015 and max(dly_a) < 0.0075 and len(left) >= 1)
s2a, slots_a, done_a, left_a = replay(d2a)
add("Issue 2: counterfactual, flows 2 ms apart (one SDU per DRB per slot)",
    f"cuts {sum(1 for s in slots_a.values() if s['cut'])}, SDUs left {len(left_a)}", not any(s["cut"] for s in slots_a.values()) and not left_a)

# ---- Issue 3 ---------------------------------------------------------------------------
d3 = load("Issue3-RegionTags")
before = len(vec(d3, "upf.dnEth.measurementLayer.measurementRecorder", "dl:meanBitElapsedTimePerPacket:vector"))
after = len(vec(d3, "device[0].app[2].measurementRecorder", "dl:meanBitElapsedTimePerPacket:vector"))
started = sc(d3, "dnStation.app[1].io", "packetSent:count")
life = len(vec(d3, "device[0].app[2].sink", "meanBitLifeTimePerPacket:vector"))
got = sc(d3, "device[0].app[2].sink", "packets:count")
add("Issue 3: INET flow-measurement (region) tags do not cross the 5G system; chunk-level CreationTimeTag does",
    f"flow 'dl' started on {int(started)} frames; measured at the UPF N6 interface (before GtpUser) {before}; at "
    f"device[0] (after the 5G system) {after}; CreationTimeTag lifetimes at device[0] {life} of {int(got)} received",
    before > 0 and after == 0 and life == got and got > 0)

w = max(len(r[0]) for r in rows)
for c, d_, v in rows:
    print(f"{v:4}  {c:<{w}}  {d_}")
print()
print("OVERALL (issues reproduced):", "YES" if all(r[2] == "PASS" for r in rows) else "NO")
