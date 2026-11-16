#!/usr/bin/env python3
"""M2-S7.2a Stage 5, N = 2 increment: an independent reference for the DL H-ARQ attribution of rule A-1
(m2s72_peru.attribute_feedback), reconstructed from the UE side of the same MAC log. Read-only; no simulation.

Why it is needed. The gNB feedback line ("H-ARQ TX: feedback received for process p codeword c result is ...",
LteHarqBufferTx.cc:220) does not name the UE, and Simu5G 1.8.1 keeps one H-ARQ TX buffer per UE (LteMacBase.h:36,
HarqTxBuffers = map<MacNodeId, LteHarqBufferTx*>), each taking the lowest free process (LteHarqBufferTx::firstAvailable,
:137). Two UEs can therefore hold the same process id at the same time. Rule A-1 resolves this from the gNB lines
only; PU-5 (sums of grants and inserts) cannot see a consistent cross-UE misattribution. The UE side gives the truth:

  gNB   "H-ARQ TX: new pdu (id X ) inserted into process p codeword id: c for node with id n"   (LteHarqBufferTx.cc:131)
  UE k  "H-ARQ RX: new PDU (id X ) inserted into process p"                                    (LteHarqBufferRx.cc:63)
  UE k  "H-ARQ RX: feedback sent to TX process p Codeword  c of node with id g result: ACK|NACK" (LteHarqBufferRx.cc:78)

X is LteMacPdu::getId() = macPduId_, copied on duplication (LteMacPdu.msg:134, :143), so the same PDU carries the same
id at the gNB and at the UE. The UE module path (prefix "%t|%M|") names UE k. Per UE and process, the UE lines form a
chain PDU -> feedback (-> retransmitted PDU -> feedback ...). The gNB feedback line is the UE's feedback received
delta later (one constant delta per run, learned, must give a complete bijection). Every quantity A-1 estimates is then
known exactly per UE, with no attribution: feedback count, NACKs, insert -> feedback delay, busy processes.

These lines are already in every E0v / E0v-N log: M2S72-MACLOG (gNB MAC at info, prefix "%t|%M|") and
M2S72S5-MACLOG-UE (UE nrMac at info). Nothing is added to any configuration.

Rows (gates of the N = 2 smoke protocol, results/M2-S7.2a-s5-n2-protocol.md §6; never E0v-N per-run gates):
  XA-0  UE <-> NR MAC node map learned from PDU ids is a bijection (and equals run.node_id when given)
  XA-1  PDU identity: every UE-received PDU id was inserted at the gNB for that UE's node, same process; no id received
        by two UEs; no duplicate gNB id; every gNB insert received by its UE except end-censored ones
  XA-2  feedback bijection: one delta; every gNB feedback line is exactly one UE-sent feedback (same p, c, result,
        t - delta); every UE-sent feedback received or end-censored; UE chains well formed; codeword 0 only
  XA-3  A-1 agreement: every A-1a and every A-1b attribution names a UE that truly sent that feedback
  XA-4  A-1 classification: every AMBIGUOUS line is irreducible from gNB lines (>= 2 UEs sent identical (p, c, result)
        at the same time for PDUs inserted in the same TTI) or lies on a retransmission chain; every ORPHAN line and
        every re-insert is explained (retransmission chain / a candidate left open by an unresolved line)
  XA-5  grants <-> inserts: per UE, the TTIs with DL grant bytes > 0 are the TTIs with a gNB insert for that node,
        retransmission TTIs of that node excepted
  XA-6  per-UE H-ARQ aggregates of A-1 (inserts, feedback, NACKs, delays) equal the truth; evaluated only when A-1 is
        exact (ambiguous = orphan = re-insert = 0), else NOT EVALUATED (the truth values are still reported)
"""
import bisect
import gzip
import re
from collections import Counter, defaultdict

import m2s72_peru as P

MS = P.MS
NET = "M2S72Bridge"
GNB = f"{NET}.gnb1.cellularNic.mac"
R_UE_MOD = re.compile(r"^" + re.escape(NET) + r"\.ue\[(\d+)\]\.cellularNic\.nrMac$")
R_INSERT = re.compile(r"H-ARQ TX: new pdu \(id (\d+) \) inserted into process (\d+) codeword id: (\d+) for node with id (\d+)")
R_FB = re.compile(r"H-ARQ TX: feedback received for process (\d+) codeword (\d+) result is (ACK|NACK)")
R_EXTRACT = re.compile(r"H-ARQ TX: pdu \(id (\d+) \) extracted from process (\d+) codeword (\d+) for node with id (\d+)")
R_UE_RX = re.compile(r"H-ARQ RX: new PDU \(id (\d+) \) inserted into process (\d+)\s*$")
R_UE_FB = re.compile(r"H-ARQ RX: feedback sent to TX process (\d+) Codeword  (\d+) of node with id (\d+) result: (ACK|NACK)")
DELTA_MAX = 20 * MS            # search window for the gNB-receipt delay of a UE feedback (learned, then exact)
NE = "NOT EVALUATED"


def t_ps(s):
    whole, _, frac = s.partition(".")
    return int(whole) * P.S + int((frac + "0" * 12)[:12])


# --------------------------------------------------------------------------------------------------- reader -------
def read_log(path, lines=None):
    """one pass over a "%t|%M|" MAC log (gzip or plain), or over an iterable of lines (tests, controls).
    returns a dict:
      events   the gNB H-ARQ insert / feedback events in LOG order, exactly m2s72_peru_adapter.harq_events()'s list
      ins_pid  the PDU id of each "ins" event, aligned with the "ins" events of events
      extract  gNB (t, pid, p, cw, node) transmissions (first transmission and retransmissions)
      ue_rx    {k: [(line, t, pid, p)]}; ue_fb {k: [(line, t, p, cw, g, res)]}   (line = global line index)
      t_last   the last timestamp of the log"""
    out = {"events": [], "ins_pid": [], "ins_line": [], "fb_line": [], "extract": [], "ue_rx": defaultdict(list),
           "ue_fb": defaultdict(list), "t_last": 0}
    if lines is None:
        op = gzip.open if path.endswith(".gz") else open
        fh = op(path, "rt", errors="replace")
    else:
        fh = lines
    try:
        for li, line in enumerate(fh):
            p = line.rstrip("\n").split("|", 2)
            if len(p) < 3 or not p[0][:1].isdigit():
                continue
            t = t_ps(p[0])
            out["t_last"] = max(out["t_last"], t)
            if p[1] == GNB:
                m = R_INSERT.search(p[2])
                if m:
                    out["events"].append(("ins", t, int(m.group(4)), int(m.group(2)), int(m.group(3))))
                    out["ins_pid"].append(int(m.group(1)))
                    out["ins_line"].append(li)
                    continue
                m = R_FB.search(p[2])
                if m:
                    out["events"].append(("fb", t, int(m.group(1)), int(m.group(2)), m.group(3)))
                    out["fb_line"].append(li)
                    continue
                m = R_EXTRACT.search(p[2])
                if m:
                    out["extract"].append((t, int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))))
                continue
            mu = R_UE_MOD.match(p[1])
            if mu:
                k = int(mu.group(1))
                m = R_UE_RX.search(p[2])
                if m:
                    out["ue_rx"][k].append((li, t, int(m.group(1)), int(m.group(2))))
                    continue
                m = R_UE_FB.search(p[2])
                if m:
                    out["ue_fb"][k].append((li, t, int(m.group(1)), int(m.group(2)), int(m.group(3)), m.group(4)))
    finally:
        if lines is None:
            fh.close()
    out["ue_rx"], out["ue_fb"] = dict(out["ue_rx"]), dict(out["ue_fb"])
    return out


# ------------------------------------------------------------------------------------------------ truth -----------
def truth(log, node_id=None):
    """the UE-side reconstruction: XA-0, XA-1 and the per-UE feedback chains. node_id: {k: node} from the run, or
    None (then XA-0 is the bijection test only)"""
    ins = {}                                           # pid -> dict(t, p, cw, node, idx)
    dup = []
    ei = 0
    for idx, e in enumerate(log["events"]):
        if e[0] != "ins":
            continue
        pid = log["ins_pid"][ei]
        ei += 1
        if pid in ins:
            dup.append(pid)
        ins[pid] = {"t": e[1], "node": e[2], "p": e[3], "cw": e[4], "idx": idx}
    rx_first, rtx_rx, probs = {}, Counter(), []
    kmap = defaultdict(Counter)
    for k in sorted(log["ue_rx"]):
        for li, t, pid, p in log["ue_rx"][k]:
            g = ins.get(pid)
            if g is None:
                probs.append(f"UE {k} received PDU {pid} that was never inserted at the gNB")
                continue
            if g["p"] != p:
                probs.append(f"UE {k} PDU {pid}: process {p} at the UE, {g['p']} at the gNB")
            if pid in rx_first:
                if rx_first[pid][0] != k:
                    probs.append(f"PDU {pid} received by UE {rx_first[pid][0]} and UE {k}")
                else:
                    rtx_rx[pid] += 1
                continue
            rx_first[pid] = (k, t, p)
            kmap[k][g["node"]] += 1
    # XA-0
    knode = {}
    for k, c in kmap.items():
        if len(c) != 1:
            probs.append(f"UE {k} received PDUs of several gNB nodes {dict(c)}")
        knode[k] = c.most_common(1)[0][0]
    xa0 = []
    if len(set(knode.values())) != len(knode):
        xa0.append(f"two UEs map to one node: {knode}")
    if node_id is not None:
        for k, n in knode.items():
            if node_id.get(k) != n:
                xa0.append(f"UE {k}: node {n} from PDU ids, {node_id.get(k)} in the run")
    # unreceived inserts: censored only after the last possible reception
    rx_delay = [rx_first[pid][1] - g["t"] for pid, g in ins.items() if pid in rx_first]
    dmax = max(rx_delay) if rx_delay else 0
    unrx = [pid for pid, g in ins.items() if pid not in rx_first]
    cens_ins = [pid for pid in unrx if ins[pid]["t"] + dmax >= log["t_last"]]
    for pid in unrx:
        if pid not in cens_ins:
            probs.append(f"gNB insert PDU {pid} (node {ins[pid]['node']}, t {ins[pid]['t']}) never received by a UE")
    if dup:
        probs.append(f"{len(dup)} duplicate gNB PDU ids, first {dup[:3]}")
    # chains: per UE, per process, in log order
    tf, chain_bad, cw_other = [], [], 0
    node2k = {n: k for k, n in knode.items()}
    for k in sorted(set(log["ue_rx"]) | set(log["ue_fb"])):
        evs = sorted([(li, "rx", t, pid, p) for li, t, pid, p in log["ue_rx"].get(k, [])]
                     + [(li, "fb", t, p, cw, res) for li, t, p, cw, g, res in log["ue_fb"].get(k, [])])
        cur = {}                                       # p -> [pid, fed]
        for e in evs:
            if e[1] == "rx":
                _, _, t, pid, p = e
                c = cur.get(p)
                if c is not None and not c[1] and c[0] != pid:
                    chain_bad.append(f"UE {k} process {p}: PDU {pid} received while PDU {c[0]} awaits feedback")
                cur[p] = [pid, False]
            else:
                _, _, t, p, cw, res = e
                if cw != 0:
                    cw_other += 1
                c = cur.get(p)
                if c is None or c[1]:
                    chain_bad.append(f"UE {k} process {p}: feedback at {t} without a PDU awaiting it")
                    continue
                c[1] = True
                tf.append({"k": k, "node": knode.get(k), "pid": c[0], "t_s": t, "p": p, "cw": cw, "res": res})
    # final feedback of each PDU: ACK, or the last NACK (no later reception of the same id)
    last = {}
    for i, x in enumerate(tf):
        last[x["pid"]] = i
    for i, x in enumerate(tf):
        x["final"] = last[x["pid"]] == i
        x["rtx_chain"] = rtx_rx.get(x["pid"], 0) > 0 or x["res"] == "NACK"
    return {"ins": ins, "rx_first": rx_first, "rtx_rx": dict(rtx_rx), "knode": knode, "node2k": node2k,
            "xa0": xa0, "xa1": probs, "censored_inserts": len(cens_ins), "rx_delay_max_ps": dmax,
            "tf": tf, "chain_bad": chain_bad, "cw_other": cw_other}


def match_feedback(log, tr, trace=None):
    """XA-2: learn delta, then match every gNB feedback line (log order) to UE-sent feedback. trace: A-1's per-line
    picks (attribute_feedback(trace=...)); inside a group of identical UE feedbacks (same t_s, p, c, result: the gNB
    lines cannot tell them apart) the entry of A-1's pick is consumed, so an exchangeable pair is never counted as a
    disagreement. returns (delta, per-line truth [(line idx, owners, entry or None, group owners)], unmatched UE
    entries, probs). owners: the UEs whose identical feedback is still unmatched when the line is reached (A-1's pick
    must be one of them); group owners: every UE that sent that identical feedback (the line's ambiguity class)"""
    tf = tr["tf"]
    fbs = [(i, e) for i, e in enumerate(log["events"]) if e[0] == "fb"]
    by_key = defaultdict(list)
    for x in tf:
        by_key[(x["p"], x["cw"], x["res"])].append(x["t_s"])
    for v in by_key.values():
        v.sort()
    cand = Counter()
    for i, e in fbs:
        ts = by_key.get((e[2], e[3], e[4]), [])
        lo = bisect.bisect_left(ts, e[1] - DELTA_MAX)
        hi = bisect.bisect_right(ts, e[1])
        for t_s in ts[lo:hi]:
            cand[e[1] - t_s] += 1
    probs = []
    if not fbs:
        return None, [], [], ["no gNB feedback line"]
    # the smallest delay at which every gNB feedback line has a UE sender (dry run on counts); PHY air frames last one
    # slot and are delivered at the end of reception (PhyBase.cc:120, :214), so one slot is expected, not assumed
    keys = Counter((x["t_s"], x["p"], x["cw"], x["res"]) for x in tf)
    best = None
    for d in sorted(cand):
        need = Counter((e[1] - d, e[2], e[3], e[4]) for _, e in fbs)
        miss = sum(max(0, v - keys.get(k, 0)) for k, v in need.items())
        if best is None or miss < best[1]:
            best = (d, miss)
        if miss == 0:
            break
    if best is None:
        return None, [], [], ["no candidate gNB-receipt delay (no UE-sent feedback with the same process / result)"]
    delta = best[0]
    pool = defaultdict(list)                           # (t_s, p, cw, res) -> unmatched entries
    for x in tf:
        pool[(x["t_s"], x["p"], x["cw"], x["res"])].append(x)
    picks = {i: n for i, n, _ in trace} if trace is not None else {}
    lines = []
    group = {k: {x["node"] for x in v} for k, v in pool.items()}
    for i, e in fbs:
        key = (e[1] - delta, e[2], e[3], e[4])
        ent = pool.get(key, [])
        owners = {x["node"] for x in ent}
        if not ent:
            probs.append(f"gNB feedback line {i} (t {e[1]}, process {e[2]}, {e[4]}) has no UE sender at t - delta")
            lines.append((i, set(), None, group.get(key, set())))
            continue
        pick = picks.get(i)
        j = next((j for j, x in enumerate(ent) if x["node"] == pick), 0)
        x = ent.pop(j)
        x["t_g"] = e[1]
        x["fb_idx"] = i
        lines.append((i, owners, x, group[key]))
    left = [x for v in pool.values() for x in v]
    cens = [x for x in left if x["t_s"] + delta > log["t_last"]]
    cid = {id(x) for x in cens}
    for x in left:
        if id(x) not in cid:
            probs.append(f"UE {x['k']} feedback at {x['t_s']} (process {x['p']}, {x['res']}) never received at the gNB")
    return delta, lines, cens, probs


def grants_inserts(log, grants):
    """XA-5. grants: [(t, dir, node, lcid, bytes)] (m2s72_maclog.MacLog.grants)"""
    g = defaultdict(set)
    gb = defaultdict(Counter)
    for t, d, n, l, b in grants:
        if d == "DL":
            gb[n][t // MS] += b
    for n, c in gb.items():
        g[n] = {tti for tti, b in c.items() if b > 0}
    ins = defaultdict(set)
    for e in log["events"]:
        if e[0] == "ins":
            ins[e[2]].add(e[1] // MS)
    seen, rtx = set(), defaultdict(set)
    for t, pid, p, cw, n in log["extract"]:
        if pid in seen:
            rtx[n].add(t // MS)
        seen.add(pid)
    res = {}
    for n in sorted(set(g) | set(ins)):
        only_g = sorted(g[n] - ins[n] - rtx[n])
        only_i = sorted(ins[n] - g[n])
        res[n] = {"grant_ttis": len(g[n]), "insert_ttis": len(ins[n]), "rtx_ttis": len(rtx[n]),
                  "grant_without_insert": only_g[:5], "n_grant_without_insert": len(only_g),
                  "insert_without_grant": only_i[:5], "n_insert_without_grant": len(only_i)}
    return res


def a1_state_replay(log, trace):
    """A-1's open set as its trace implies (inserts open (node, p, c); a picked feedback closes it): the re-inserts,
    with the line that left the stale candidate open"""
    picked = {i: n for i, n, _ in trace}
    open_ = {}
    reins = []
    for i, e in enumerate(log["events"]):
        if e[0] == "ins":
            key = (e[2], e[3], e[4])
            if key in open_:
                reins.append((i, key, open_[key]))
            open_[key] = i
        else:
            n = picked.get(i)
            if n is not None:
                open_.pop((n, e[2], e[3]), None)
    return reins




def crossvalidate(log, nproc, node_id=None, grants=None, window=None):
    """every XA row, the truth aggregates and the overlap census; returns (rows, report).
    rows: (row, subject, status, detail), status PASS / FAIL / NOT EVALUATED"""
    trace = []
    per, summ = P.attribute_feedback(log["events"], nproc, window, trace=trace)
    tr = truth(log, node_id)
    delta, lines, cens_fb, p2 = match_feedback(log, tr, trace)
    by_line = {i: (own, x, grp) for i, own, x, grp in lines}
    pid_of_idx = {}
    ei = 0
    for idx, e in enumerate(log["events"]):
        if e[0] == "ins":
            pid_of_idx[idx] = log["ins_pid"][ei]
            ei += 1
    sib = defaultdict(list)                            # identical UE feedbacks (t_s, p, cw, res) -> entries
    for x in tr["tf"]:
        sib[(x["t_s"], x["p"], x["cw"], x["res"])].append(x)
    final_of = {x["pid"]: x for x in tr["tf"] if x["final"]}

    rows = []
    rows.append(("XA-0", "run", "PASS" if not tr["xa0"] and tr["knode"] else "FAIL",
                 f"UE -> node from PDU ids {tr['knode']}" + (f"; FAIL {tr['xa0']}" if tr["xa0"] else "")
                 + ("" if node_id is None else f"; run node ids {node_id}")))
    rows.append(("XA-1", "run", "PASS" if not tr["xa1"] else "FAIL",
                 f"gNB inserts {len(tr['ins'])}, received by a UE {len(tr['rx_first'])}, end-censored "
                 f"{tr['censored_inserts']}, retransmitted PDU ids {len(tr['rtx_rx'])}, max insert -> UE rx "
                 f"{tr['rx_delay_max_ps']} ps" + (f"; FAIL {len(tr['xa1'])}: {tr['xa1'][:3]}" if tr["xa1"] else "")))
    if tr["cw_other"]:
        rows.append(("XA-2", "run", NE, f"{tr['cw_other']} UE feedbacks on codeword != 0 (the UE RX line has no codeword)"))
    else:
        bad2 = p2 + tr["chain_bad"]
        rows.append(("XA-2", "run", "PASS" if delta is not None and not bad2 else "FAIL",
                     f"delta {delta} ps; gNB feedback lines {len(lines)}, UE-sent feedbacks {len(tr['tf'])}, end-censored "
                     f"{len(cens_fb)}, chain violations {len(tr['chain_bad'])}" + (f"; FAIL {len(bad2)}: {bad2[:3]}" if bad2 else "")))
    agree, dis, amb, orph, dis_ex = Counter(), Counter(), Counter(), Counter(), []
    for i, n, cls in trace:
        own, x, grp = by_line.get(i, (set(), None, set()))
        if cls in ("a1a", "a1b"):
            if n in own:
                agree[cls] += 1
            else:
                dis[cls] += 1
                dis_ex.append((i, cls, n, sorted(own)))
        elif cls == "ambiguous":
            if x is None:
                amb["no UE sender (see XA-2)"] += 1
            elif x["rtx_chain"]:
                amb["retransmission chain"] += 1
            elif len(grp) >= 2:
                s = sib[(x["t_s"], x["p"], x["cw"], x["res"])]
                same = len({tr["ins"][y["pid"]]["t"] // MS for y in s if y["pid"] in tr["ins"]}) == 1
                amb["irreducible: identical feedback, same insert TTI" if same else
                    "irreducible: identical feedback, different insert TTIs"] += 1
            else:
                amb["conservative: single true owner (A-1 had a stale or second candidate)"] += 1
        else:
            if x is None:
                orph["no UE sender (see XA-2)"] += 1
            elif x["rtx_chain"]:
                orph["retransmission chain"] += 1
            else:
                orph["UNEXPLAINED: true owner exists, no retransmission"] += 1
    rows.append(("XA-3", "run", "FAIL" if dis else ("PASS" if lines else NE),
                 f"A-1a {agree['a1a']} agree / {dis['a1a']} disagree; A-1b {agree['a1b']} agree / {dis['a1b']} disagree"
                 + (f"; first disagreements (line, class, A-1 node, true owners) {dis_ex[:3]}" if dis else "")))
    unres = {i for i, n, cls in trace if n is None}
    wrong = {i for i, n, cls in trace if n is not None and n not in by_line.get(i, (set(), None, set()))[0]}
    rein = Counter()
    for i, key, prev in a1_state_replay(log, trace):
        x = final_of.get(pid_of_idx[prev])
        if x is None:
            rein["UNEXPLAINED: previous PDU of the process has no final UE feedback"] += 1
        elif x.get("fb_idx") in unres or x.get("fb_idx") in wrong or x["rtx_chain"]:
            rein["stale candidate: the previous PDU's feedback line was unresolved / retransmission chain"] += 1
        else:
            rein["UNEXPLAINED: the previous PDU's feedback was attributed to it"] += 1
    bad4 = [c for c in list(amb) + list(orph) + list(rein) if c.startswith(("UNEXPLAINED", "no UE sender"))]
    rows.append(("XA-4", "run", "FAIL" if bad4 else "PASS",
                 f"A-1 ambiguous {summ['ambiguous']} {dict(amb)}; orphan {summ['orphan']} {dict(orph)}; re-insert "
                 f"{summ['reinsert']} {dict(rein)}"))
    gi = None
    if grants is None:
        rows.append(("XA-5", "run", NE, "no grants given"))
    else:
        gi = grants_inserts(log, grants)
        bad = {n: v for n, v in gi.items() if v["n_grant_without_insert"] or v["n_insert_without_grant"]}
        rows.append(("XA-5", "run", "PASS" if gi and not bad else "FAIL",
                     "; ".join(f"node {n}: grant TTIs {v['grant_ttis']}, insert TTIs {v['insert_ttis']}, rtx TTIs "
                               f"{v['rtx_ttis']}, grant w/o insert {v['n_grant_without_insert']} {v['grant_without_insert']}, "
                               f"insert w/o grant {v['n_insert_without_grant']} {v['insert_without_grant']}"
                               for n, v in gi.items()) or "no DL grant and no insert"))
    tagg = {}
    for n in sorted({g["node"] for g in tr["ins"].values()} | set(tr["knode"].values())):
        mine = [x for x in tr["tf"] if x["node"] == n and "t_g" in x]
        tagg[n] = {"inserts": sum(1 for g in tr["ins"].values() if g["node"] == n), "feedback": len(mine),
                   "nack": sum(1 for x in mine if x["res"] == "NACK"),
                   "delays_ps": sorted(x["t_g"] - tr["ins"][x["pid"]]["t"] for x in mine if x["pid"] in tr["ins"])}
    exact = summ["ambiguous"] == 0 and summ["orphan"] == 0 and summ["reinsert"] == 0
    if not exact:
        rows.append(("XA-6", "run", NE, "A-1 not exact (ambiguous / orphan / re-insert > 0): its per-UE aggregates are "
                     "incomplete by definition (addendum §4.1); the truth aggregates are in the report"))
    else:
        diffs = []
        for n in sorted(set(tagg) | set(per)):
            a, t_ = per.get(n, {}), tagg.get(n, {})
            for f in ("inserts", "feedback", "nack"):
                if a.get(f) != t_.get(f):
                    diffs.append(f"node {n} {f}: A-1 {a.get(f)}, truth {t_.get(f)}")
            if sorted(a.get("delays_ps", [])) != t_.get("delays_ps", []):
                diffs.append(f"node {n}: delay multisets differ")
        rows.append(("XA-6", "run", "PASS" if not diffs else "FAIL", "; ".join(diffs) or "; ".join(
            f"node {n}: inserts {v['inserts']}, feedback {v['feedback']}, NACK {v['nack']}" for n, v in tagg.items())))
    report = {"a1_summary": summ, "delta_ps": delta,
              "truth_aggregates": {n: {**{k: v for k, v in a.items() if k != "delays_ps"},
                                       "delays_ps": dict(Counter(a["delays_ps"]))} for n, a in tagg.items()},
              "a1_aggregates": {n: {"inserts": a["inserts"], "feedback": a["feedback"], "nack": a["nack"],
                                    "delays_ps": dict(Counter(a["delays_ps"])), "open_at_end": a["open_at_end"]}
                                for n, a in per.items()},
              "agreement": {"agree": dict(agree), "disagree": dict(dis)}, "ambiguous": dict(amb), "orphan": dict(orph),
              "reinsert": dict(rein), "grants_inserts": gi, "ue_node": tr["knode"],
              "nack_ue_sent": sum(1 for x in tr["tf"] if x["res"] == "NACK"), "retransmitted_pdus": len(tr["rtx_rx"]),
              "truth_occupancy": truth_occupancy(log, tr, nproc, window),
              "overlap_census": overlap_census(log, tr, by_line)}
    return rows, report, trace


def truth_occupancy(log, tr, nproc, window=None):
    """per-UE busy processes in LOG order from the truth (+1 at the insert line, -1 at the gNB line of the PDU's final
    feedback; P.occupancy_log_order): the quantity A-1 cannot give under overlap. Reported, never a gate"""
    ev = defaultdict(list)
    for g in tr["ins"].values():
        ev[g["node"]].append((g["idx"], g["t"], +1))
    for x in tr["tf"]:
        if x["final"] and "fb_idx" in x:
            ev[x["node"]].append((x["fb_idx"], x["t_g"], -1))
    tt = [e[1] // MS for e in log["events"]]
    span = (window[0] // MS, window[1] // MS) if window else ((min(tt), max(tt) + 1) if tt else (0, 0))
    out = {}
    for n, v in ev.items():
        v.sort()
        try:
            out[n] = P.occupancy_log_order(v, nproc, span)
        except ValueError as ex:
            out[n] = {"error": str(ex)}
    return out


def overlap_census(log, tr, by_line):
    """A-1's precondition measured on the run: for every gNB feedback line, how many UEs truly hold that (process,
    codeword) at that point of the log (insert line .. line of the PDU's final feedback), and for 2+ holders whether
    their open PDUs were inserted in the same TTI (A-1b cannot separate them) or not (A-1b can, by d*)"""
    holders = defaultdict(dict)                        # (p, cw) -> {node: insert t}
    final_line = {x["fb_idx"]: x for x in tr["tf"] if x["final"] and "fb_idx" in x}
    c = Counter()
    for i, e in enumerate(log["events"]):
        if e[0] == "ins":
            holders[(e[3], e[4])][e[2]] = e[1]
            continue
        h = holders[(e[2], e[3])]
        if len(h) <= 1:
            c[f"{len(h)} holder(s)"] += 1
        else:
            same = len({t // MS for t in h.values()}) == 1
            c[f"{len(h)} holders, same insert TTI" if same else f"{len(h)} holders, different insert TTIs"] += 1
        x = final_line.get(i)
        if x is not None:
            h.pop(x["node"], None)
    return dict(sorted(c.items()))
