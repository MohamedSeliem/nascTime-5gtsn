#!/usr/bin/env python3
"""Investigation of O-S4-1 (Follow_Up DL delay 10-25 ms vs Sync 5-6 ms) and O-S3-2 (the
last DL SDU of a run never delivered). One mechanism is tested for both.

Method: replay the gNB's DRB 1 RLC UM TX entity byte by byte from recorded statistics
only -- SDUs in (size, time), PDUs out (sentPduSize, time) -- using the NR UM header
sizes Simu5G 1.8.0 uses (12-bit SN): complete SDU 1 B, first segment 2 B, later
segment 4 B (SN + SO). The replay says when each SDU's last byte left the RLC. Each
prediction is then checked against what the UE's DRB 1 RLC RX entity delivered.

Rows:
  replay            every DL DRB 1 SDU is delivered at the UE exactly 4 ms (1 slot to
                    send + 3 slots HARQ until delivery, as traced) after the slot in
                    which the replay says its last byte left the gNB RLC; same order
  shortfall         (S4, light load) every slot in which an SDU is cut into a segment
                    has a grant (sum of PDU sizes + 2 B MAC header) that is at least
                    the scheduler's demand formula (queued bytes + 2 B MAC header + ONE
                    1 B RLC header: LteSchedulerEnb.cc, "queueLength += MAC_HEADER +
                    RLC_HEADER_UM") but smaller than what the queued SDUs need (one RLC
                    header per PDU), and holds at least 2 queued items; a single fresh
                    SDU is never cut
  stranding         (S4) after a slot that leaves bytes in the RLC, DRB 1 sends nothing
                    until the next SDU arrives on DRB 1; the remainder then goes out
                    with it (within 2 slots of the arrival)
  O-S4-1            the late Follow_Ups are exactly the segmented ones; once triggered,
                    every later DRB 1 SDU waits for the next one (tail lag)
  counterfactual    O2-s4-nodl (no DL application flow on DRB 1): no SDU is ever cut,
                    every SDU leaves within 2 slots
  O-S3-2            O1-harq16: exactly one SDU is left in the RLC at the end -- the last
                    one, partly sent; O2-flush (one more DL frame at 3.5 s): that SDU is
                    completed in the first slot after the extra frame arrives, and the
                    extra frame becomes the stranded one
Usage: check_o_tail.py <results dir containing O-tail/>
"""
import os
import sys

import pandas as pd

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = os.path.join(RES, "O-tail")
TX, RX = "gnb1.cellularNic.rlc-um-2049-1.tx", "ue[0].cellularNic.nrRlc-um-1-1.rx"
MS = 1e-3
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(name):
    d = pd.read_csv(os.path.join(OUT, name + ".csv"), low_memory=False)
    d = d[(d.type == "vector") & d.module.notna() & d.run.notna()]
    d = d[d.run.str.contains(r"-0-\d{8}-")]                       # seed 0
    return {(m.replace("M1Bridge.", ""), n): list(zip(map(float, t.split()), map(float, v.split())))
            for m, n, t, v in zip(d.module, d.name, d.vectime, d.vecvalue) if isinstance(t, str)}


def replay(V):
    sdus = V[(TX, "receivedPacketFromUpperLayer:vector(packetBytes)")]
    pdus = V[(TX, "sentPduSize:vector")]
    queue, i, done, slots = [], 0, [], {}
    for t, s in pdus:
        while i < len(sdus) and sdus[i][0] <= t:
            queue.append({"arr": sdus[i][0], "size": int(sdus[i][1]), "sent": 0})
            i += 1
        sl = slots.setdefault(t, {"pdus": [], "before": [(q["size"] - q["sent"], q["sent"] == 0) for q in queue],
                                  "cut": []})
        s = int(s)
        h = queue[0]
        if h["sent"] == 0:
            pay = h["size"] if s == h["size"] + 1 else s - 2
            if pay < h["size"]:
                sl["cut"].append(h["arr"])
        else:
            pay = s - 4
        sl["pdus"].append(s)
        h["sent"] += pay
        if h["sent"] >= h["size"]:
            done.append((h["arr"], h["size"], t))
            queue.pop(0)
    for t in slots:
        slots[t]["after"] = None
    return sdus, done, slots, queue


def check_replay(name, V):
    sdus, done, slots, left = replay(V)
    rx = V[(RX, "sentPacketToUpperLayer:vector(packetBytes)")]
    ok = len(rx) == len(done) and all(int(s) == b and abs(rt - (c + 4 * MS)) < 1e-9 for (a, b, c), (rt, s) in zip(done, rx))
    add(f"replay {name}: each DRB 1 SDU delivered 4 ms after its last byte left the gNB RLC",
        f"{len(sdus)} SDUs in, {len(done)} completed, {len(rx)} delivered at the UE, all matching: {ok}; "
        f"left in the RLC at the end: {[(round(q['arr'], 6), q['size'], q['size'] - q['sent']) for q in left]}", ok)
    return sdus, done, slots, left


# --- O-S4-1: Config S4 ---------------------------------------------------------------
V = load("O2-s4")
sdus, done, slots, left = check_replay("O2-s4 (S4)", V)
cut_slots = {t: s for t, s in slots.items() if s["cut"]}
bad, nmulti = [], 0
for t, s in cut_slots.items():
    alloc = sum(s["pdus"]) + 2
    demand = sum(r for r, _ in s["before"]) + 2 + 1
    need = sum(r + (1 if fresh else 4) for r, fresh in s["before"]) + 2
    nmulti += len(s["before"]) >= 2
    if not (demand <= alloc < need and len(s["before"]) >= 2):
        bad.append((round(t, 3), alloc, demand, need, len(s["before"])))
single_cut = [t for t, s in slots.items() if s["cut"] and len(s["before"]) == 1 and s["before"][0][1]]
add("shortfall (S4): every cut happens when the grant covers the scheduler's demand but not the SDUs' headers",
    f"{len(cut_slots)} slots with a cut, all with >= 2 queued items: {nmulti == len(cut_slots)}; demand <= grant < need in all: "
    f"{not bad}{' ' + str(bad[:3]) if bad else ''}; cuts of a single fresh SDU: {len(single_cut)}",
    bool(cut_slots) and not bad and not single_cut)

arrivals = [t for t, _ in sdus]
pdu_times = sorted(slots)
viol = []
for t in sorted(cut_slots):
    nxt_pdu = next((x for x in pdu_times if x > t), None)
    nxt_arr = next((a for a in arrivals if a > t), None)
    if nxt_pdu is not None and (nxt_arr is None or not (nxt_arr < nxt_pdu <= nxt_arr + 2 * MS)):
        viol.append((round(t, 4), nxt_arr, nxt_pdu))
add("stranding (S4): after a cut, DRB 1 sends nothing until the next SDU arrives",
    f"{len(cut_slots)} cuts; next DRB 1 transmission always within 2 slots after the next arrival and never before: {not viol}"
    f"{' ' + str(viol[:3]) if viol else ''}", not viol)

waits = [(a, b, c - a) for a, b, c in done]
fu = [w for w in waits if w[1] == 92]                         # Follow_Up: 92 B RLC SDU
late_fu = [w for w in fu if w[2] > 2 * MS]
cut_arr = {a for s in slots.values() for a in s["cut"]}
first_cut = min(cut_arr) if cut_arr else None
after = [w for w in waits if first_cut is not None and w[0] >= first_cut]
add("O-S4-1 explained: late Follow_Ups are exactly the cut ones; afterwards every DRB 1 SDU waits for the next",
    f"Follow_Ups {len(fu)}, waiting > 2 ms at the gNB {len(late_fu)}, of which cut {sum(1 for w in late_fu if w[0] in cut_arr)}, "
    f"cut but not late {sum(1 for w in fu if w[0] in cut_arr and w[2] <= 2 * MS)}; first cut at {first_cut:.6f} s; "
    f"DRB 1 SDUs from then on cut {sum(1 for w in after if w[0] in cut_arr)} of {len(after)}, waits "
    f"{min(w[2] for w in after) / MS:.1f}..{max(w[2] for w in after) / MS:.1f} ms",
    bool(late_fu) and all(w[0] in cut_arr for w in late_fu) and not any(w[0] in cut_arr and w[2] <= 2 * MS for w in fu))

V2 = load("O2-s4-nodl")
s2, d2, sl2, l2 = check_replay("O2-s4-nodl", V2)
ncut2 = sum(len(s["cut"]) for s in sl2.values())
wmax = max(c - a for a, _, c in d2)
add("counterfactual O2-s4-nodl: gPTP alone on DRB 1 -- no cut, no lag",
    f"{len(d2)} SDUs, cuts {ncut2}, longest wait at the gNB {wmax / MS:.3f} ms, left {len(l2)}",
    ncut2 == 0 and wmax <= 2 * MS and not l2)

# --- O-S3-2 ---------------------------------------------------------------------------
H = load("O1-harq16")
sh, dh, _, lh = check_replay("O1-harq16 (seed 0)", H)
F = load("O2-flush")
_, dfl, _, lf = check_replay("O2-flush (seed 0)", F)
stranded = lh[0] if len(lh) == 1 else None
is_last = stranded is not None and stranded["arr"] == sh[-1][0] and stranded["sent"] < stranded["size"]
fixed = [c for a, _, c in dfl if stranded is not None and a == stranded["arr"]]
moved = len(lf) == 1 and lf[0]["arr"] >= 3.5 and lf[0]["sent"] < lf[0]["size"]
fmt = lambda qs: [(round(q["arr"], 6), q["size"], q["size"] - q["sent"]) for q in qs]
add("O-S3-2 explained: the last segmented SDU is stranded; one more frame releases it and is stranded itself",
    f"O1-harq16: left (arrival, size, bytes unsent) {fmt(lh)}, the last SDU to arrive: {is_last}; O2-flush: it completes at "
    f"{fixed[0] if fixed else None} s; now left {fmt(lf)}",
    is_last and len(fixed) == 1 and 3.5 < fixed[0] <= 3.5 + 2 * MS and moved)

w = max(len(r[0]) for r in rows)
for c, d_, v in rows:
    print(f"{v:4}  {c:<{w}}  {d_}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
