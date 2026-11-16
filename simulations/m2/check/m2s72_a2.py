#!/usr/bin/env python3
"""M2-S7.2a Stage 5: DL H-ARQ attribution rule A-2 (gNB-only unit-state attribution), as specified in
results/M2-S7.2a-a2-design-review.md §5 and approved for implementation (A2-D1, 2026-11-16). Read-only.

A-2 replays the gNB DL H-ARQ TX state of every unit (UE node, process, codeword) from the gNB MAC log ALONE:
  insert ("new pdu (id X ) inserted ... for node with id n")      opens the unit with PDU X of node n
  extracted ("pdu (id X ) extracted ... for node with id n")       a transmission (first or retransmission)
  feedback event = "receiveHarqFeedback - start" block with ONE unit outcome line and the feedback line:
     ACK      unit line without PDU id (anonymous)
     NACK     "... PDU X set for RTX"                 -> the unit waits for retransmission (stays busy)
     discard  "... PDU X discarded (max retransmissions reached) : m"  -> the unit is emptied (HARQ loss)
  DL rtx scheduler lines ("rtxAcid - ... User[n] ... ACID [p]", "selected for retransmission"): node-identified
  evidence of every retransmission
Attribution of a feedback line (t, p, c): the candidates are the units awaiting feedback on (p, c) with the largest
age t - last transmission, which must be the run's single d*_tx. All lines with the same (t, p, c) form one group,
resolved as a whole when its feedback burst ends (time advances, or a main-loop insert / transmission of one of its
candidate units): NACK / discard
lines by their PDU id (class 'id'), then the remaining ACK lines against the remaining candidates: 1:1 'single',
k:k 'exchangeable' (any bijection gives the same per-unit outcome; certified when no main-loop event splits the
group), any other count: unresolved (fails).
Per-UE occupancy: a process of UE k is busy from its insert line to the line that empties the unit (final ACK or
discard); a NACKed unit stays busy. Histograms by m2s72_peru.occupancy_log_order (unchanged).

Rows (gates of A-2's own per-UE evaluation only; they never replace or relabel an accepted row such as PU-4):
  A2-0   preconditions P0-1..P0-6 (m2s72_a2probe) on this log: none FAILS
  A2-0s  every Simu5G text A-2 relies on occurs in the run's Simu5G 1.8.1 source tree ($SIMU5G_ROOT)
  A2-1   every feedback line resolved: events well formed, NACKs identified, group counts consistent
  A2-2   unit life cycle: no insert into an occupied unit, no duplicate PDU id, first transmission in the insert TTI,
         transmissions only from an inserted or NACKed unit, discard exactly at maxHarqRtx + 1 transmissions,
         every unit ACKed, discarded or end-censored
  A2-3   one feedback age d*_tx from the last transmission for every attributed line
  A2-4   every retransmission preceded in its TTI by DL rtx-scheduler lines naming its node / process and by
         "selected for retransmission" (NOT EXERCISED without retransmissions)
  A2-5   every exchangeable group certified (NOT EXERCISED without groups)
  A2-6   conservation: lines, inserts, transmissions, outcomes; per-UE DL grant TTIs = insert TTIs (rtx TTIs excepted)
  A2-7   agreement with the INDEPENDENT UE-side reference XA (m2s72_harqx; UE-side ownership evidence A-2 never reads)
  A2-8   agreement with Simu5G's own per-UE statistics harqErrorRateDl:mean, harqTxAttemptsDl:mean (UE MAC scalars)
Statuses: PASS, FAIL, NOT EVALUATED (evidence missing), NOT EXERCISED (nothing of that kind occurred in this run)."""
import gzip
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a2probe as PR  # noqa: E402  (contract-tested patterns; P0 census)
import m2s72_peru as P  # noqa: E402

S, MS = PR.S, PR.MS
GNB = PR.GNB
NE, NX = "NOT EVALUATED", "NOT EXERCISED"
REL_TOL = 1e-9
KEYWORDS = ("H-ARQ", "pduFeedback", "receiveHarqFeedback", "pdu_ has been", "rtxschedule", "rtxAcid", "Grant", "granted",
            "DOWNLINK", "UPLINK", "macPduMake", "PDU Maker", "The corresponding unit", "not addressed")
SENTINEL_MOD = "A2.end-of-log"

# the texts A-2 relies on, as they appear in the 1.8.1 sources (A2-0s)
SOURCE_NEEDLES = {
    "stack/mac/buffer/harq/LteHarqUnitTx.cc": ('" LteHarqUnitTx::pduFeedback H-ARQ process  "', '" set for RTX "',
                                               '" discarded (max retransmissions reached) : "',
                                               '"\\t pdu_ has been sent and received correctly "', '"LteHarqUnitTx::pduFeedback - Welcome!"'),
    "stack/mac/buffer/harq/LteHarqBufferTx.cc": ('"LteHarqBufferTx::receiveHarqFeedback - start"', '" has been selected for retransmission"',
                                                 '" ) extracted from process "', '"H-ARQ TX: new pdu (id "', '"H-ARQ TX: feedback received for process "'),
    "stack/mac/scheduler/LteSchedulerEnbDl.cc": ('"LteSchedulerEnbDl::rtxAcid - Node ["', '"], User["', '"],  Codeword ["', '"]  of ["',
                                                 '"] , ACID ["', '" LteSchedulerEnbDl::rtxschedule Cell:  "', '::[ START RTX-SCHEDULE ]::'),
    "stack/mac/buffer/harq/LteHarqBufferRx.cc": ('"H-ARQ RX: new PDU (id "', '"H-ARQ RX: feedback sent to TX process "', '" Codeword  "'),
}


# ------------------------------------------------------------------------------------------------- input ---------
def load(path):
    """the lines A-2, XA and P0 read (gNB H-ARQ / scheduler / grant lines, UE nrMac H-ARQ RX lines), in log order,
    plus a sentinel line at the log's last time stamp (so every tool sees the true end of the log). Bounded memory."""
    out, t_end = [], 0
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.split("|", 2)
            if len(p) < 3 or not p[0][:1].isdigit():
                continue
            t_end = max(t_end, PR.t_ps(p[0]))
            if p[1] == GNB:
                if any(k in p[2] for k in KEYWORDS):
                    out.append(line if line.endswith("\n") else line + "\n")
            elif PR.R_UE_MOD.match(p[1]) and "H-ARQ RX" in p[2]:
                out.append(line if line.endswith("\n") else line + "\n")
    out.append(sentinel(t_end))
    return out


def sentinel(t_end):
    return f"{t_end // S}.{t_end % S:012d}|{SENTINEL_MOD}|end of log\n"


def t_end_of(lines):
    return max((PR.t_ps(x.split("|", 1)[0]) for x in lines if x[:1].isdigit()), default=0)


# ------------------------------------------------------------------------------------------------ replay ---------
def replay(lines):
    """the A-2 state machine over the log lines (log order). Returns a result dict (see keys at the end)."""
    units = {}                  # (node, p, cw) -> pdu dict (the live unit)
    pdus = {}                   # pid -> pdu dict (kept after the unit empties)
    fb = []                     # one dict per gNB feedback line, log order
    groups_done = []
    open_groups = {}            # (t, p, cw) -> group
    finalized = set()           # keys finalized in the current feedback burst time
    burst_t = None
    viol = defaultdict(list)
    busy = defaultdict(list)    # node -> [(gNB line index, t, +1 / -1)]
    ages = Counter()
    rtx_ev = defaultdict(set)   # tti -> {(node, p, cw)} named by DL rtxAcid lines
    sel_ev = set()              # (tti, p) "selected for retransmission"
    rtx_dir = None
    block = None
    nack_rtx_delay = []
    counts = Counter()
    t_end = 0
    gi = 0

    def v(row, msg):
        viol[row].append(msg)

    def close(k, line, kind):
        u = units.pop(k)
        u["end"], u["t_close"], u["close_gi"] = kind, line["t"], line["gi"]
        busy[u["node"]].append((line["gi"], line["t"], -1))

    def finalize(g):
        cands = list(g["cands"])
        for line in g["lines"]:
            if line["res"] != "NACK":
                continue
            pid = line["block_pid"]
            k = next((k for k in cands if units[k]["pid"] == pid), None)
            if k is None:
                v("A2-1", f"t {line['t']}: NACK (PDU {pid}) not among the candidates of process {line['p']}")
                line["cls"] = "unresolved"
                continue
            cands.remove(k)
            u = units[k]
            line.update(cls="id", owner=u["node"], pid=u["pid"], ntx=u["ntx"], age=g["age"], t_ins=u["t_ins"])
            u["fbs"].append((line["t"], "NACK"))
            g["nacks"] += 1
            if line["block_kind"] == "discard":
                if line["maxrtx"] is None or u["ntx"] != line["maxrtx"] + 1:
                    v("A2-2", f"t {line['t']}: PDU {pid} discarded after {u['ntx']} transmissions (maxHarqRtx {line['maxrtx']})")
                close(k, line, "discard")
            else:
                u["st"], u["nack_t"] = "BUF", line["t"]
        acks = [x for x in g["lines"] if x["res"] == "ACK"]
        g["acks"] = len(acks)
        if len(acks) != len(cands):
            v("A2-1", f"group t {g['t']} process {g['p']}: {len(acks)} ACK lines for {len(cands)} remaining candidates")
            for x in acks:
                x["cls"] = "unresolved"
            return
        cls = "single" if len(acks) == 1 else "exchangeable"
        g["exchangeable"] = len(acks) >= 2
        if g["exchangeable"]:
            # certificate (design §5.6): no +1 step (insert) of a candidate node strictly between the group's first and
            # last line, so the arbitrary assignment of the anonymous ACKs cannot change any per-UE occupancy value
            lo, hi = acks[0]["gi"], acks[-1]["gi"]
            inside = [(nd, e[0]) for nd in {k[0] for k in g["cands"]} for e in busy.get(nd, []) if e[2] > 0 and lo < e[0] < hi]
            if inside:
                v("A2-5", f"group t {g['t']} process {g['p']}: insert(s) of candidate nodes inside the group {inside[:3]} (not certified)")
        for x, k in zip(acks, sorted(cands, key=lambda k: (k[0], units[k]["pid"]))):   # any bijection (design §5.6)
            u = units[k]
            x.update(cls=cls, owner=u["node"], pid=u["pid"], ntx=u["ntx"], age=g["age"], t_ins=u["t_ins"])
            u["fbs"].append((x["t"], "ACK"))
            close(k, x, "ack")

    def finalize_all():
        for key in sorted(open_groups, key=lambda key: open_groups[key]["first_gi"]):
            g = open_groups[key]
            finalize(g)
            groups_done.append(g)
            finalized.add(key)
        open_groups.clear()

    def finalize_touching(unit_key):
        """a main-loop insert / transmission of unit_key ends the open group that holds unit_key as a candidate (its
        unit must be resolved first); groups of other units stay open (design §5.3, §5.6)"""
        for key in sorted(open_groups, key=lambda key: open_groups[key]["first_gi"]):
            g = open_groups[key]
            if unit_key in g["cands"]:
                finalize(g)
                groups_done.append(g)
                finalized.add(key)
                del open_groups[key]

    for raw in lines:
        p_ = raw.rstrip("\n").split("|", 2)
        if len(p_) < 3 or not p_[0][:1].isdigit():
            continue
        t = PR.t_ps(p_[0])
        t_end = max(t_end, t)
        if p_[1] != GNB:
            continue
        msg = p_[2]
        gi += 1
        if burst_t is not None and t != burst_t:
            finalize_all()
            finalized.clear()
            burst_t = None
        if PR.T_DROPPED in msg or PR.T_NOTADDR in msg:
            v("A2-0", f"t {t}: out-of-scope text: {msg.strip()[:90]}")
            continue
        if PR.T_RTXS_START in msg:
            rtx_dir = None
            continue
        m = PR.R_RTXS_DIR.search(msg)
        if m:
            rtx_dir = m.group(2)
            continue
        m = PR.R_RTXACID.search(msg)
        if m:
            if rtx_dir == "DL":
                rtx_ev[t // MS].add((int(m.group(2)), int(m.group(5)), int(m.group(3))))
            continue
        m = PR.R_SELRTX.search(msg)
        if m:
            sel_ev.add((t // MS, int(m.group(1))))
            continue
        if PR.T_START in msg:
            if block is not None:
                v("A2-1", f"t {t}: feedback event starts while the previous one (t {block['t']}) has no feedback line")
            block = {"t": t, "kind": None, "pid": None, "p": None, "cw": None, "n": 0, "maxrtx": None}
            continue
        if PR.T_UACK in msg:
            if block is None:
                v("A2-1", f"t {t}: unit ACK line outside a feedback event")
            else:
                block.update(kind="ack", n=block["n"] + 1)
            continue
        m = PR.R_URTX.search(msg) or PR.R_UDISC.search(msg)
        if m:
            kind = "rtx" if PR.R_URTX.search(msg) else "discard"
            mx = re.search(r"reached\) : (\d+)", msg)
            if block is None:
                v("A2-1", f"t {t}: unit {kind} line outside a feedback event")
            else:
                block.update(kind=kind, pid=int(m.group(3)), p=int(m.group(1)), cw=int(m.group(2)), n=block["n"] + 1,
                             maxrtx=int(mx.group(1)) if mx else None)
            continue
        m = PR.R_INSERT.search(msg)
        if m:
            counts["insert lines"] += 1
            pid, p, cw, node = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            finalize_touching((node, p, cw))
            key = (node, p, cw)
            if key in units:
                v("A2-2", f"t {t}: insert of PDU {pid} into the occupied unit {key} (PDU {units[key]['pid']})")
                units[key]["end"] = "overwritten"
                del units[key]
            if pid in pdus:
                v("A2-2", f"t {t}: duplicate PDU id {pid}")
            u = {"pid": pid, "node": node, "p": p, "cw": cw, "st": "INS", "t_ins": t, "ins_gi": gi, "last_tx": None, "ntx": 0,
                 "txs": [], "fbs": [], "nack_t": None, "end": None}
            units[key] = u
            pdus[pid] = u
            busy[node].append((gi, t, +1))
            continue
        m = PR.R_EXTRACT.search(msg)
        if m:
            counts["extract lines"] += 1
            pid, p, cw, node = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            finalize_touching((node, p, cw))
            u = units.get((node, p, cw))
            if u is None or u["pid"] != pid:
                v("A2-2", f"t {t}: transmission of PDU {pid} {(node, p, cw)} that is not in that unit")
                continue
            if u["st"] == "INS":
                if t // MS != u["t_ins"] // MS:
                    v("A2-2", f"t {t}: first transmission of PDU {pid} not in its insert TTI")
            elif u["st"] == "BUF":
                counts["retransmissions"] += 1
                nack_rtx_delay.append(t - u["nack_t"])
                if (node, p, cw) not in rtx_ev.get(t // MS, set()):
                    v("A2-4", f"t {t}: retransmission of PDU {pid} {(node, p, cw)} without a DL rtxAcid line naming node {node}, process {p}")
                if (t // MS, p) not in sel_ev:
                    v("A2-4", f"t {t}: retransmission of PDU {pid} without 'selected for retransmission' of process {p}")
            else:
                v("A2-2", f"t {t}: transmission of PDU {pid} while it awaits feedback")
            u.update(st="WAIT", last_tx=t, ntx=u["ntx"] + 1)
            u["txs"].append(t)
            continue
        m = PR.R_FB.search(msg)
        if m:
            p, cw, res = int(m.group(1)), int(m.group(2)), m.group(3)
            ok = (block is not None and block["t"] == t and block["n"] == 1 and
                  ((res == "ACK" and block["kind"] == "ack") or
                   (res == "NACK" and block["kind"] in ("rtx", "discard") and block["p"] == p and block["cw"] == cw)))
            if not ok:
                v("A2-1", f"t {t}: malformed feedback event for process {p} {res}: {block}")
            line = {"j": len(fb), "gi": gi, "t": t, "p": p, "cw": cw, "res": res, "cls": None, "owner": None, "pid": None,
                    "block_pid": (block or {}).get("pid"), "block_kind": (block or {}).get("kind"), "maxrtx": (block or {}).get("maxrtx")}
            fb.append(line)
            block = None
            key = (t, p, cw)
            if key in finalized:
                v("A2-5", f"t {t}: the feedback group of process {p} is split by a main-loop event (not certified)")
            g = open_groups.get(key)
            if g is None:
                cand = [k for k, u in units.items() if k[1] == p and k[2] == cw and u["st"] == "WAIT"]
                if not cand:
                    v("A2-1", f"t {t}: feedback for process {p} with no unit awaiting feedback")
                    line["cls"] = "unresolved"
                    burst_t = t
                    continue
                amax = max(t - units[k]["last_tx"] for k in cand)
                top = [k for k in cand if t - units[k]["last_tx"] == amax]
                g = open_groups[key] = {"t": t, "p": p, "cw": cw, "cands": top, "age": amax, "lines": [], "first_gi": gi,
                                        "nacks": 0, "acks": 0, "exchangeable": False}
                ages[amax] += 1
            g["lines"].append(line)
            burst_t = t
            continue
    finalize_all()
    d_star = next(iter(ages)) if len(ages) == 1 else None
    if len(ages) > 1:
        v("A2-3", f"several feedback ages from the last transmission: {dict(ages)}")
    # end of the log: censoring
    rtx_wait = max([MS] + nack_rtx_delay)
    cens = Counter()
    for k, u in list(units.items()):
        if u["st"] == "WAIT" and d_star is not None and u["last_tx"] + d_star > t_end:
            u["end"] = "censored: awaiting feedback"
        elif u["st"] == "INS" and u["t_ins"] // MS == t_end // MS:
            u["end"] = "censored: inserted in the last TTI"
        elif u["st"] == "BUF" and t_end - u["nack_t"] <= rtx_wait:
            u["end"] = "censored: awaiting retransmission"
        else:
            u["end"] = f"OPEN at the end in state {u['st']}"
            v("A2-2", f"PDU {u['pid']} {k} open at the end of the log in state {u['st']} (t_end {t_end})")
        cens[u["end"]] += 1
    return {"fb": fb, "groups": groups_done, "pdus": pdus, "busy": dict(busy), "viol": dict(viol), "d_star": d_star,
            "ages": dict(ages), "t_end": t_end, "counts": dict(counts), "end_states": dict(cens), "rtx_wait_max_ps": rtx_wait,
            "nack_rtx_delays": nack_rtx_delay}


# ------------------------------------------------------------------------------------------ per-UE outputs -------
def per_ue(res, nproc, window):
    """per node: counts, histograms, occupancy (never gates)"""
    out = {}
    nodes = sorted({u["node"] for u in res["pdus"].values()})
    tt0, tt1 = window[0] // MS, window[1] // MS            # the TTIs [t0, t1) (the XA / adapter convention)
    for n in nodes:
        us = [u for u in res["pdus"].values() if u["node"] == n]
        lines = [x for x in res["fb"] if x["owner"] == n]
        acked = [u for u in us if u["end"] == "ack"]
        o = {"inserts": len(us), "transmissions": sum(u["ntx"] for u in us), "retransmissions": sum(max(0, u["ntx"] - 1) for u in us),
             "feedback": len(lines), "ack": sum(1 for x in lines if x["res"] == "ACK"), "nack": sum(1 for x in lines if x["res"] == "NACK"),
             "discarded": sum(1 for u in us if u["end"] == "discard"),
             "transmissions_per_acked_pdu": dict(sorted(Counter(u["ntx"] for u in acked).items())),
             "harq_latency_ps": dict(sorted(Counter(u["t_close"] - u["t_ins"] for u in acked).items())),
             "feedback_age_ps": dict(sorted(Counter(x["age"] for x in lines).items())),
             "end_states": dict(Counter(u["end"] for u in us if u["end"] not in ("ack", "discard"))),
             "lines_by_class": dict(Counter(x["cls"] for x in lines))}
        try:
            o["occupancy"] = P.occupancy_log_order(sorted(res["busy"].get(n, [])), nproc, (tt0, tt1))
        except ValueError as ex:
            o["occupancy"] = {"error": str(ex)}
        out[n] = o
    return out


# ------------------------------------------------------------------------------------------------ rows -----------
def source_row(root):
    if not root or not os.path.isdir(os.path.join(root, "src", "simu5g")):
        return ("A2-0s", "run", NE, f"no Simu5G source tree given or found ({root or '$SIMU5G_ROOT unset'})")
    miss = []
    for rel, needles in SOURCE_NEEDLES.items():
        f = os.path.join(root, "src", "simu5g", rel)
        txt = open(f, errors="replace").read() if os.path.exists(f) else ""
        miss += [f"{rel}: {n}" for n in needles if n not in txt]
    ver = open(os.path.join(root, "Version")).read().strip() if os.path.exists(os.path.join(root, "Version")) else "?"
    return ("A2-0s", "run", "PASS" if not miss and ver == "1.8.1" else "FAIL",
            f"Simu5G {ver} at {root}: {sum(len(v) for v in SOURCE_NEEDLES.values()) - len(miss)} / "
            f"{sum(len(v) for v in SOURCE_NEEDLES.values())} texts present" + (f"; missing {miss[:3]}" if miss else ""))


def grants_rows(res, grants):
    """A2-6 grant part: per node, TTIs with DL grant bytes > 0 = TTIs with an insert (rtx TTIs excepted)"""
    if grants is None:
        return None, "no grants given"
    gb = defaultdict(Counter)
    for t, d, n, l, b in grants:
        if d == "DL":
            gb[n][t // MS] += b
    g = {n: {tti for tti, b in c.items() if b > 0} for n, c in gb.items()}
    ins, rtx = defaultdict(set), defaultdict(set)
    for u in res["pdus"].values():
        ins[u["node"]].add(u["t_ins"] // MS)
        for t in u["txs"][1:]:
            rtx[u["node"]].add(t // MS)
    bad = []
    for n in sorted(set(g) | set(ins)):
        a = sorted(g.get(n, set()) - ins[n] - rtx[n])
        b = sorted(ins[n] - g.get(n, set()))
        if a or b:
            bad.append(f"node {n}: grant w/o insert {len(a)} {a[:3]}, insert w/o grant {len(b)} {b[:3]}")
    return bad, "; ".join(f"node {n}: grant TTIs {len(g.get(n, ()))}, insert TTIs {len(ins[n])}, rtx TTIs {len(rtx[n])}"
                          for n in sorted(set(g) | set(ins)))


def xa_rows(res, lines, node_id, nproc, window, a2_per):
    """A2-7: A-2 against the independent UE-side reference XA (m2s72_harqx), line by line and per UE"""
    import m2s72_harqx as H
    log = H.read_log(None, lines=lines)
    log["t_last"] = res["t_end"]
    if not log["ue_rx"] and not log["ue_fb"]:
        return ("A2-7", "run", NE, "no UE-side H-ARQ RX lines in this log: the independent reference is unavailable"), None
    tr = H.truth(log, node_id)
    delta, xl, cens, probs = H.match_feedback(log, tr, None)
    ref_bad = tr["xa0"] + tr["xa1"][:3] + probs[:3] + tr["chain_bad"][:3] + ([f"codeword != 0: {tr['cw_other']}"] if tr["cw_other"] else [])
    if delta is None or ref_bad:
        return ("A2-7", "run", "FAIL", f"the reference itself is not valid (XA-0/1/2 problems {ref_bad[:3]}): A-2 cannot be confirmed"), None
    if len(xl) != len(res["fb"]):
        return ("A2-7", "run", "FAIL", f"{len(res['fb'])} A-2 feedback lines vs {len(xl)} in the reference"), None
    c, bad = Counter(), []
    for gid, g in enumerate(res["groups"]):
        own_a = sorted(x["owner"] for x in g["lines"] if x["owner"] is not None)
        idx = [x["j"] for x in g["lines"]]
        own_x = sorted(xl[j][2]["node"] for j in idx if xl[j][2] is not None)
        for x, j in zip(g["lines"], idx):
            if x["cls"] in ("id", "single"):
                if xl[j][3] != {x["owner"]}:
                    bad.append(f"line {j} ({x['cls']}): A-2 node {x['owner']}, reference {sorted(xl[j][3])}")
                else:
                    c[x["cls"]] += 1
        if g["exchangeable"]:
            if own_a != own_x:
                bad.append(f"group t {g['t']} process {g['p']}: A-2 nodes {own_a}, reference {own_x}")
            else:
                c["exchangeable lines"] += len([x for x in g["lines"] if x["cls"] == "exchangeable"])
    # per UE: feedback, NACK, latency multiset (insert -> feedback), occupancy
    xs = defaultdict(lambda: {"feedback": 0, "nack": 0, "lat": Counter()})
    for x in tr["tf"]:
        if "t_g" in x and x["pid"] in tr["ins"]:
            d = xs[x["node"]]
            d["feedback"] += 1
            d["nack"] += x["res"] == "NACK"
            d["lat"][x["t_g"] - tr["ins"][x["pid"]]["t"]] += 1
    as_ = defaultdict(lambda: {"feedback": 0, "nack": 0, "lat": Counter()})
    for x in res["fb"]:
        if x["owner"] is not None:
            d = as_[x["owner"]]
            d["feedback"] += 1
            d["nack"] += x["res"] == "NACK"
            d["lat"][x["t"] - x["t_ins"]] += 1
    for n in sorted(set(xs) | set(as_)):
        if dict(xs[n]) != dict(as_[n]):
            bad.append(f"node {n}: per-UE feedback / NACK / latency differ (A-2 {as_[n]['feedback']} / {as_[n]['nack']}, reference "
                       f"{xs[n]['feedback']} / {xs[n]['nack']})")
    # reference occupancy from the UE-side truth: +1 at the insert, -1 at the line of the PDU's last feedback when that
    # feedback ends the PDU (ACK, or a NACK the gNB logged as a discard). A PDU whose last feedback is a NACK that was
    # not a discard is still held at the end of the log (awaiting retransmission), as in Simu5G.
    j_of = {i: j for j, (i, own, x, grp) in enumerate(xl)}
    ev = defaultdict(list)
    for g_ in tr["ins"].values():
        ev[g_["node"]].append((g_["idx"], g_["t"], +1))
    for x in tr["tf"]:
        if x.get("final") and "fb_idx" in x:
            j = j_of.get(x["fb_idx"])
            if x["res"] == "ACK" or (j is not None and res["fb"][j]["block_kind"] == "discard"):
                ev[x["node"]].append((x["fb_idx"], x["t_g"], -1))
    occ_x = {}
    for n, e in ev.items():
        try:
            occ_x[n] = P.occupancy_log_order(sorted(e), nproc, (window[0] // MS, window[1] // MS))
        except ValueError as ex:
            occ_x[n] = {"error": str(ex)}
    occ_eq = {n: (occ_x.get(n) == a2_per[n]["occupancy"]) for n in a2_per}
    if not all(occ_eq.values()):
        bad.append(f"per-UE occupancy differs from the reference: {occ_eq}")
    return ("A2-7", "run", "FAIL" if bad else "PASS",
            f"reference XA (UE-side ownership, delta {delta} ps): lines confirmed {dict(c)}; per-UE feedback / NACK / latency equal "
            f"for {len(as_)} UEs; per-UE occupancy equal {occ_eq}" + (f"; FAIL {len(bad)}: {bad[:3]}" if bad else "")), {"confirmed": dict(c), "occupancy_equal": occ_eq}


def sca_nodes(sca):
    """{UE MAC module: macNodeId} from the run's .sca parameter records"""
    out = {}
    if not sca or not os.path.exists(sca):
        return out
    for line in open(sca, errors="replace"):
        if line.startswith("par ") and " macNodeId " in line:
            p = line.split()
            if len(p) >= 4 and PR.R_UE_MOD.match(p[1]):
                out[p[1]] = int(float(p[3]))
    return out


def scalar_row(res, sca):
    sc = PR.scalars(sca)
    nodes = sca_nodes(sca)
    if not sc or not nodes:
        return ("A2-8", "run", NE, f"no Simu5G per-UE H-ARQ scalars or no macNodeId records in {sca}"), None
    per = defaultdict(lambda: {"feedback": 0, "nack": 0, "ntx": []})
    for x in res["fb"]:
        if x["owner"] is not None:
            per[x["owner"]]["feedback"] += 1
            per[x["owner"]]["nack"] += x["res"] == "NACK"
    for u in res["pdus"].values():
        if u["end"] == "ack":
            per[u["node"]]["ntx"].append(u["ntx"])
    bad, done, ne = [], [], []
    for mod, n in sorted(nodes.items()):
        s = sc.get(mod, {})
        d = per.get(n)
        if d is None or d["feedback"] == 0:
            ne.append(f"{mod} (node {n}): no feedback attributed")
            continue
        for name, val in (("harqErrorRateDl:mean", d["nack"] / d["feedback"]),
                          ("harqTxAttemptsDl:mean", (sum(d["ntx"]) / len(d["ntx"])) if d["ntx"] else None)):
            if name not in s or val is None:
                ne.append(f"{mod} {name} absent")
                continue
            try:
                rec = float(s[name])
            except ValueError:
                ne.append(f"{mod} {name} = {s[name]}")
                continue
            ok = abs(rec - val) <= REL_TOL * max(1.0, abs(val))
            (done if ok else bad).append(f"node {n} {name}: Simu5G {s[name]}, A-2 {val:.12g}")
    if bad:
        return ("A2-8", "run", "FAIL", f"FAIL {bad}; equal {done}"), None
    if not done:
        return ("A2-8", "run", NE, f"nothing comparable: {ne}"), None
    return ("A2-8", "run", "PASS", f"equal {done}" + (f"; not comparable {ne}" if ne else "")), done


def rows_for(res, lines, nproc, window, node_id=None, grants=None, sca=None, simu5g_root=None):
    """every A-2 row on one log; returns (rows, per-UE outputs, coverage, extra)"""
    rows = []
    pre = PR.census(lines=lines)
    fails = {k: v for k, v in pre["preconditions"].items() if v.startswith("FAILS")}
    rows.append(("A2-0", "run", "FAIL" if fails or res["viol"].get("A2-0") else "PASS",
                 "; ".join(f"{k.split(' ')[0]} {v}" for k, v in pre["preconditions"].items()) + (f"; {res['viol'].get('A2-0', [])[:2]}" if res["viol"].get("A2-0") else "")))
    rows.append(source_row(simu5g_root))
    cls = Counter(x["cls"] for x in res["fb"])

    def vr(row, okdetail, exercised=True):
        vv = res["viol"].get(row, [])
        if vv:
            return (row, "run", "FAIL", f"FAIL {len(vv)}: {vv[:3]}")
        return (row, "run", "PASS" if exercised else NX, okdetail)
    rows.append(vr("A2-1", f"feedback lines {len(res['fb'])}: {dict(cls)}"))
    rows.append(vr("A2-2", f"PDUs {len(res['pdus'])}; transmissions {res['counts'].get('extract lines', 0)}; end states "
                           f"{dict(Counter(u['end'] for u in res['pdus'].values()))}"))
    rows.append(vr("A2-3", f"d*_tx {res['d_star']} ps for every attributed line ({res['ages']})"))
    nrtx = res["counts"].get("retransmissions", 0)
    rows.append(vr("A2-4", f"{nrtx} retransmissions, each with node-identified scheduler evidence", exercised=nrtx > 0))
    ex = [g for g in res["groups"] if g["exchangeable"]]
    rows.append(vr("A2-5", f"{len(ex)} exchangeable groups certified (sizes {dict(Counter(len(g['cands']) for g in ex))})", exercised=bool(ex)))
    # A2-6 conservation
    cons = []
    nfb = len(res["fb"])
    attributed = sum(1 for x in res["fb"] if x["owner"] is not None)
    if attributed != nfb:
        cons.append(f"attributed {attributed} of {nfb} feedback lines")
    ends = Counter(u["end"] for u in res["pdus"].values())
    n_ins = res["counts"].get("insert lines", 0)
    if len(res["pdus"]) != n_ins:
        cons.append(f"PDUs {len(res['pdus'])} vs insert lines {n_ins}")
    closed = ends.get("ack", 0) + ends.get("discard", 0) + sum(v for k, v in ends.items() if k.startswith("censored"))
    if closed != n_ins:
        cons.append(f"ACKed + discarded + censored = {closed} vs inserts {n_ins}")
    ntx = sum(u["ntx"] for u in res["pdus"].values())
    if ntx != res["counts"].get("extract lines", 0):
        cons.append(f"transmissions {ntx} vs extract lines {res['counts'].get('extract lines', 0)}")
    nfb_units = sum(len(u["fbs"]) for u in res["pdus"].values())
    if nfb_units != attributed:
        cons.append(f"unit feedbacks {nfb_units} vs attributed lines {attributed}")
    gb, gdet = grants_rows(res, grants)
    if gb:
        cons += gb
    rows.append(("A2-6", "run", "FAIL" if cons else ("PASS" if gb is not None else NE),
                 (f"FAIL {cons[:4]}" if cons else f"lines {nfb} = attributed; inserts {n_ins} = ACKed {ends.get('ack', 0)} + discarded "
                  f"{ends.get('discard', 0)} + censored {closed - ends.get('ack', 0) - ends.get('discard', 0)}; transmissions {ntx}; ") + f"grants: {gdet}"))
    per = per_ue(res, nproc, window)
    r7, x7 = xa_rows(res, lines, node_id, nproc, window, per)
    rows.append(r7)
    r8, x8 = scalar_row(res, sca)
    rows.append(r8)
    cov = coverage(res, rows)
    return rows, per, cov, {"preconditions": pre, "xa": x7, "scalars": x8}


SYNTH = {   # where a feature not exercised by a run is validated (test names in test_m2s72_a2.py)
    "NACK identified by PDU id": "synthetic fixtures (T-sweep, T-nack) + real-output injection (a2-controls PC-A2-inject)",
    "retransmission state / retransmissions": "synthetic fixtures (T-sweep, T-nack) + real-output injection (PC-A2-inject)",
    "discard after maxHarqRtx + 1 transmissions": "synthetic fixtures only (T-sweep, T-discard)",
    "mixed ACK / NACK groups": "synthetic fixtures only (T-sweep)",
    "exchangeable groups of 3 or more": "synthetic fixtures only (T-sweep N 3, 4)",
    "exchangeable ACK groups (2 candidates)": "synthetic fixtures (T-sweep)",
    "end-of-run censoring: awaiting retransmission": "synthetic fixtures only (T-censor)",
    "end-of-run censoring: inserted in the last TTI": "synthetic fixtures only (T-censor)",
    "end-of-run censoring: awaiting feedback": "synthetic fixtures (T-censor) + real-output truncation (a2-controls PC-A2-censor)",
    "per-UE occupancy confirmed by the independent reference": "not confirmed on this run (A2-7 not PASS)",
}


def coverage(res, rows):
    """for every A-2 feature: exercised on THIS run's real output (count), or not exercised (and where it is validated
    instead). A run never claims a feature it did not exercise."""
    st = {r[0]: r[2] for r in rows}
    ex = [g for g in res["groups"] if g["exchangeable"]]
    ends = Counter(u["end"] for u in res["pdus"].values())
    items = [
        ("single-candidate ACK attribution", sum(1 for x in res["fb"] if x["cls"] == "single")),
        ("exchangeable ACK groups (2 candidates)", sum(1 for g in ex if len(g["cands"]) == 2)),
        ("exchangeable groups of 3 or more", sum(1 for g in ex if len(g["cands"]) >= 3)),
        ("NACK identified by PDU id", sum(1 for x in res["fb"] if x["cls"] == "id")),
        ("retransmission state / retransmissions", res["counts"].get("retransmissions", 0)),
        ("discard after maxHarqRtx + 1 transmissions", ends.get("discard", 0)),
        ("mixed ACK / NACK groups", sum(1 for g in res["groups"] if g["nacks"] and g["acks"])),
        ("end-of-run censoring: awaiting feedback", ends.get("censored: awaiting feedback", 0)),
        ("end-of-run censoring: inserted in the last TTI", ends.get("censored: inserted in the last TTI", 0)),
        ("end-of-run censoring: awaiting retransmission", ends.get("censored: awaiting retransmission", 0)),
        ("per-UE occupancy confirmed by the independent reference", len({u["node"] for u in res["pdus"].values()}) if st.get("A2-7") == "PASS" else 0),
        ("independent UE-side reference (A2-7)", 1 if st.get("A2-7") == "PASS" else 0),
        ("Simu5G per-UE statistics (A2-8)", 1 if st.get("A2-8") == "PASS" else 0),
    ]
    out = []
    for name, n in items:
        if n:
            out.append((name, n, "VALIDATED ON REAL OUTPUT (this run)"))
        else:
            out.append((name, 0, "NOT EXERCISED by this run -> " + SYNTH.get(name, "not evaluated")))
    return out


REQUIRED = ("A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4", "A2-5", "A2-6", "A2-7")


def verdict(rows):
    st = {r[0]: r[2] for r in rows}
    if any(st.get(r) == "FAIL" for r in st):
        return "A-2 NOT VALID", 1
    if any(st.get(r) not in ("PASS", NX) for r in REQUIRED):
        return "A-2 INCOMPLETE", 4
    return "A-2 VALID", 0


NOTE = ("A-2 rows are new rows. They gate only A-2's own per-UE H-ARQ evaluation; they do not replace, relabel or "
        "reclassify any accepted row. In particular the recorded PU-4 FAIL of rule A-1 stands unchanged.")
