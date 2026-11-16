#!/usr/bin/env python3
"""A-2 design increment, step P0: read-only feasibility probe of the gNB-side evidence that the proposed attribution
rule A-2 (results/M2-S7.2a-a2-design-review.md §5) relies on. It attributes NOTHING and produces no gate row: it
counts the line classes, checks the structural preconditions of A-2 on a real log, and reports which of them the
log can and cannot exercise. Run on the preserved N = 1 and N = 2 smoke outputs (no simulation).

    python3 -B check/m2s72_a2probe.py <runs> <cfg> <output dir>
        reads runs/run-<cfg>.log.gz, runs/<cfg>/<cfg>/0.sca and 0.elog if present; writes a2probe-<cfg>.txt / .json;
        exit 0 when every precondition that the log exercises holds (P0-1 .. P0-6 not FAIL), 1 otherwise, 2 error

Preconditions (each: HOLDS / FAILS / NOT EXERCISED, never assumed):
  P0-1 feedback events are well formed: every gNB "feedback received" line closes one "receiveHarqFeedback - start"
       block of the same time stamp holding exactly one unit outcome line, consistent with the result
       (ACK <-> "sent and received correctly"; NACK <-> "set for RTX <id>" or "discarded ... <id>")
  P0-2 every transmission is logged with PDU id and node: each insert is followed by exactly one first "extracted"
       line of the same id / process / codeword / node (same TTI); further extracts of an id only after its NACK
  P0-3 one feedback delay from the LAST transmission (d*_tx): at every feedback line, the oldest awaiting unit on
       that (process, codeword) has age d*_tx (single value), so no awaiting unit is older than d*_tx
  P0-4 retransmission evidence is node-identified: each retransmission is preceded in its TTI by a DL rtxschedule
       block naming the UE ("UE: <node>", "rtxAcid ... User[<node>] ... ACID [<p>]") and "selected for retransmission"
  P0-5 groups of feedback lines with the same (t, process, codeword) and several awaiting candidates: result mix
       (all ACK / mixed / all NACK) and, for groups with >= 2 ACK lines, the exchangeability certificate (no event of
       a candidate's node between the group's first and last line other than the group's own closes)
  P0-6 out-of-scope texts absent: dropped-unit reset (handover / D2D), "not addressed to the actually contained pdu"
Also reported (never gates): the per-UE H-ARQ scalars that Simu5G records itself (harqErrorRateDl:mean,
harqTxAttemptsDl:mean, ... of each UE MAC), and the eventlog's coverage of feedback events."""
import gzip
import json
import os
import re
import sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True
S, MS = 10 ** 12, 10 ** 9
NET = "M2S72Bridge"
GNB = f"{NET}.gnb1.cellularNic.mac"
R_UE_MOD = re.compile(r"^" + re.escape(NET) + r"\.ue\[(\d+)\]\.cellularNic\.nrMac$")
R_INSERT = re.compile(r"H-ARQ TX: new pdu \(id (\d+) \) inserted into process (\d+) codeword id: (\d+) for node with id (\d+)")
R_FB = re.compile(r"H-ARQ TX: feedback received for process (\d+) codeword (\d+) result is (ACK|NACK)")
R_EXTRACT = re.compile(r"H-ARQ TX: pdu \(id (\d+) \) extracted from process (\d+) codeword (\d+) for node with id (\d+)")
T_START = "LteHarqBufferTx::receiveHarqFeedback - start"
T_WELCOME = "LteHarqUnitTx::pduFeedback - Welcome!"
T_UACK = "pdu_ has been sent and received correctly"
R_URTX = re.compile(r"LteHarqUnitTx::pduFeedback H-ARQ process  (\d+) Codeword (\d+) PDU (\d+) set for RTX")
R_UDISC = re.compile(r"LteHarqUnitTx::pduFeedback H-ARQ process  (\d+) Codeword (\d+) PDU (\d+) discarded \(max retransmissions reached\)")
R_SELRTX = re.compile(r"H-ARQ TX: process (\d+) has been selected for retransmission")
T_RTXS_START = "LteSchedulerEnbDl::rtxschedule --------------------::[ START RTX-SCHEDULE ]"
R_RTXS_DIR = re.compile(r"LteSchedulerEnbDl::rtxschedule Cell:  (\d+) Direction: (DL|UL)")
R_RTXS_UE = re.compile(r"LteSchedulerEnbDl::rtxschedule  UE: (\d+)")
R_RTXACID = re.compile(r"LteSchedulerEnbDl::rtxAcid - Node \[(\d+)\], User\[(\d+)\],  Codeword \[(\d+)\]  of \[(\d+)\] , ACID \[(\d+)\]")
T_DROPPED = "The corresponding unit has been"
T_NOTADDR = "not addressed to the actually contained pdu"
R_UE_RX = re.compile(r"H-ARQ RX: new PDU \(id (\d+) \) inserted into process (\d+)\s*$")
R_UE_FB = re.compile(r"H-ARQ RX: feedback sent to TX process (\d+) Codeword  (\d+) of node with id (\d+) result: (ACK|NACK)")
HARQ_SCALARS = ("harqErrorRateDl:mean", "harqTxAttemptsDl:mean", "harqErrorRate_1st_Dl:mean", "harqErrorRate_2nd_Dl:mean",
                "harqErrorRate_3rd_Dl:mean", "harqErrorRate_4th_Dl:mean", "macPacketLossDl:mean")


def t_ps(s):
    whole, _, frac = s.partition(".")
    return int(whole) * S + int((frac + "0" * 12)[:12])


def _lines(path=None, lines=None):
    if lines is not None:
        return iter(lines), None
    op = gzip.open if path.endswith(".gz") else open
    fh = op(path, "rt", errors="replace")
    return fh, fh


def census(path=None, lines=None):
    """one pass, log order, gNB DL TX side + UE RX counts; returns the report dict"""
    it, fh = _lines(path, lines)
    c = Counter()
    units = {}                       # (node, p, cw) -> {pid, st, last_tx, ntx, events}
    viol = defaultdict(list)
    block = None                     # current feedback block: {t, outcome, pid}
    ages = Counter()
    groups = {}                      # (t, p, cw) -> {k, res: [], first_idx, last_idx, nodes}
    rtx_ttis = defaultdict(set)      # tti -> nodes named by the DL rtx scheduler (User[...] in rtxAcid)
    rtx_dir = None
    seen_sel = set()                 # (tti, p) selected for retransmission
    node_events = defaultdict(list)  # node -> [log index]
    t_last = 0
    gi = 0
    try:
        for li, raw in enumerate(it):
            p_ = raw.rstrip("\n").split("|", 2)
            if len(p_) < 3 or not p_[0][:1].isdigit():
                continue
            t, mod, msg = t_ps(p_[0]), p_[1], p_[2]
            t_last = max(t_last, t)
            mu = R_UE_MOD.match(mod)
            if mu:
                if R_UE_RX.search(msg):
                    c["ue rx insert"] += 1
                elif R_UE_FB.search(msg):
                    c["ue feedback sent " + R_UE_FB.search(msg).group(4)] += 1
                continue
            if mod != GNB:
                continue
            gi += 1
            if T_DROPPED in msg:
                c["dropped-unit reset (out of scope)"] += 1
                viol["P0-6"].append(f"t {t}: {msg.strip()[:100]}")
            if T_NOTADDR in msg:
                c["feedback not addressed (out of scope)"] += 1
                viol["P0-6"].append(f"t {t}: {msg.strip()[:100]}")
            if T_RTXS_START in msg:
                c["rtxschedule start"] += 1
                rtx_dir = None
                continue
            m = R_RTXS_DIR.search(msg)
            if m:
                rtx_dir = m.group(2)
                c[f"rtxschedule {rtx_dir}"] += 1
                continue
            m = R_RTXS_UE.search(msg)
            if m:
                c["rtxschedule UE line"] += 1
                continue
            m = R_RTXACID.search(msg)
            if m:
                c["rtxAcid (node-identified rtx)"] += 1
                if rtx_dir == "DL":
                    rtx_ttis[t // MS].add((int(m.group(2)), int(m.group(5)), int(m.group(3))))
                continue
            m = R_SELRTX.search(msg)
            if m:
                c["selected for retransmission"] += 1
                seen_sel.add((t // MS, int(m.group(1))))
                continue
            if T_START in msg:
                c["feedback block start"] += 1
                if block is not None:
                    viol["P0-1"].append(f"t {t}: a block starts while the previous one (t {block['t']}) has no feedback line")
                block = {"t": t, "outcome": None, "pid": None, "n": 0}
                continue
            if T_WELCOME in msg:
                c["unit welcome"] += 1
                continue
            if T_UACK in msg:
                c["unit ACK"] += 1
                if block is not None:
                    block["outcome"], block["n"] = "ack", block["n"] + 1
                continue
            m = R_URTX.search(msg) or R_UDISC.search(msg)
            if m:
                kind = "rtx" if R_URTX.search(msg) else "discard"
                c[f"unit {kind} (PDU id)"] += 1
                if block is not None:
                    block.update(outcome=kind, pid=int(m.group(3)), p=int(m.group(1)), cw=int(m.group(2)), n=block["n"] + 1)
                continue
            m = R_INSERT.search(msg)
            if m:
                c["insert"] += 1
                pid, p, cw, node = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                key = (node, p, cw)
                if key in units:
                    viol["P0-2"].append(f"t {t}: insert of PDU {pid} into the occupied unit {key} (PDU {units[key]['pid']})")
                units[key] = {"pid": pid, "st": "INS", "last_tx": None, "ntx": 0, "t_ins": t}
                node_events[node].append(gi)
                continue
            m = R_EXTRACT.search(msg)
            if m:
                c["extract"] += 1
                pid, p, cw, node = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
                key = (node, p, cw)
                u = units.get(key)
                if u is None or u["pid"] != pid:
                    viol["P0-2"].append(f"t {t}: extract of PDU {pid} {key} without that PDU in the unit")
                    continue
                if u["st"] == "INS":
                    if t // MS != u["t_ins"] // MS:
                        viol["P0-2"].append(f"t {t}: first extract of PDU {pid} not in its insert TTI")
                elif u["st"] == "BUF":
                    c["retransmission (extract after NACK)"] += 1
                    if (node, p, cw) not in rtx_ttis.get(t // MS, set()):
                        viol["P0-4"].append(f"t {t}: retransmission of PDU {pid} {key} without a DL rtxAcid line naming node {node}, process {p}")
                    if (t // MS, p) not in seen_sel:
                        viol["P0-4"].append(f"t {t}: retransmission of PDU {pid} without 'selected for retransmission'")
                else:
                    viol["P0-2"].append(f"t {t}: extract of PDU {pid} in state {u['st']}")
                u.update(st="WAIT", last_tx=t, ntx=u["ntx"] + 1)
                node_events[node].append(gi)
                continue
            m = R_FB.search(msg)
            if m:
                p, cw, res = int(m.group(1)), int(m.group(2)), m.group(3)
                c["feedback " + res] += 1
                ok = (block is not None and block["t"] == t and block["n"] == 1
                      and ((res == "ACK" and block["outcome"] == "ack") or (res == "NACK" and block["outcome"] in ("rtx", "discard")
                                                                         and block.get("p") == p and block.get("cw") == cw)))
                if not ok:
                    viol["P0-1"].append(f"t {t}: feedback line process {p} {res} with block {block}")
                cand = [k for k, u in units.items() if k[1] == p and k[2] == cw and u["st"] == "WAIT"]
                if not cand:
                    viol["P0-3"].append(f"t {t}: feedback process {p} with no awaiting unit")
                    block = None
                    continue
                amax = max(t - units[k]["last_tx"] for k in cand)
                top = [k for k in cand if t - units[k]["last_tx"] == amax]
                ages[amax] += 1
                g = groups.get((t, p, cw))
                if g is None:
                    g = groups[(t, p, cw)] = {"k": len(top), "res": [], "first": gi, "last": gi, "nodes": sorted(k[0] for k in top)}
                g["res"].append(res)
                g["last"] = gi
                # close the unit: NACK by its PDU id (the block's unit line), ACK: any oldest awaiting unit (exchangeable)
                if res == "NACK" and block is not None and block.get("pid") is not None:
                    pick = next((k for k in top if units[k]["pid"] == block["pid"]), None)
                    if pick is None:
                        viol["P0-3"].append(f"t {t}: NACK for PDU {block['pid']} which is not an oldest awaiting unit on process {p}")
                        pick = next((k for k in cand if units[k]["pid"] == block["pid"]), None)
                    if pick is not None:
                        if block["outcome"] == "rtx":
                            units[pick]["st"] = "BUF"
                        else:
                            del units[pick]
                            c["discarded PDUs"] += 1
                        node_events[pick[0]].append(gi)
                else:
                    pick = top[0]
                    del units[pick]
                    node_events[pick[0]].append(gi)
                block = None
                continue
    finally:
        if fh is not None:
            fh.close()
    d_star = next(iter(ages)) if len(ages) == 1 else None
    if len(ages) > 1:
        viol["P0-3"].append(f"several feedback ages from the last transmission: {dict(ages)}")
    # groups
    gc = Counter()
    cert_bad = 0
    for (t, p, cw), g in groups.items():
        if g["k"] < 2:
            continue
        mix = "all ACK" if set(g["res"]) == {"ACK"} else ("all NACK" if set(g["res"]) == {"NACK"} else "mixed")
        gc[f"{g['k']} candidates, {len(g['res'])} lines, {mix}"] += 1
        # exchangeability certificate, needed only where ACK lines are not identified (a NACK names its PDU):
        # between the group's first and last line, no event of a candidate node other than the group's own closes
        # (the lines strictly inside the group close one unit each)
        acks = sum(1 for r in g["res"] if r == "ACK")
        if acks >= 2:
            inside = sum(1 for n in g["nodes"] for e in node_events[n] if g["first"] < e < g["last"])
            if inside > max(0, len(g["res"]) - 2):
                cert_bad += 1
    left = Counter()
    for k, u in units.items():
        if u["st"] == "WAIT" and d_star is not None and u["last_tx"] + d_star > t_last:
            left["awaiting feedback at the end (censored)"] += 1
        elif u["st"] == "INS" and u["t_ins"] // MS == t_last // MS:
            left["inserted in the last TTI (censored)"] += 1
        else:
            left[f"open at the end in state {u['st']}"] += 1
            viol["P0-2" if u["st"] == "INS" else "P0-3"].append(f"unit {k} PDU {u['pid']} open at the end in state {u['st']}")
    rep = {"counts": dict(sorted(c.items())), "d_star_tx_ps": d_star, "ages_ps": dict(ages), "groups": dict(sorted(gc.items())),
           "groups_certificate_failures": cert_bad, "open_at_end": dict(left), "t_last_ps": t_last,
           "violations": {k: v[:5] for k, v in viol.items()}, "violation_counts": {k: len(v) for k, v in viol.items()}}
    rep["preconditions"] = preconditions(rep)
    return rep


def preconditions(rep):
    c, v = rep["counts"], rep["violation_counts"]
    nack = c.get("feedback NACK", 0)

    def st(k, exercised=True):
        return "FAILS" if v.get(k) else ("HOLDS" if exercised else "NOT EXERCISED")
    out = {
        "P0-1 feedback event structure": st("P0-1", c.get("feedback ACK", 0) + nack > 0)
        + ("" if nack else " (ACK blocks only; NACK blocks NOT EXERCISED)"),
        "P0-2 transmissions logged with id and node": st("P0-2", c.get("extract", 0) > 0)
        + ("" if c.get("retransmission (extract after NACK)") else " (first transmissions only; retransmissions NOT EXERCISED)"),
        "P0-3 single feedback delay from the last transmission": st("P0-3", bool(rep["ages_ps"])),
        "P0-4 node-identified retransmission evidence": st("P0-4", c.get("retransmission (extract after NACK)", 0) > 0),
        "P0-5 multi-candidate groups": ("HOLDS" if not rep["groups_certificate_failures"] else "FAILS")
        if rep["groups"] else "NOT EXERCISED",
        "P0-6 out-of-scope texts absent": "FAILS" if v.get("P0-6") else "HOLDS",
    }
    mixed = any("mixed" in k or "all NACK" in k for k in rep["groups"])
    if rep["groups"] and not mixed:
        out["P0-5 multi-candidate groups"] += " (all-ACK groups only; groups with a NACK NOT EXERCISED)"
    return out


def scalars(sca):
    """Simu5G's own per-UE H-ARQ statistics (record=mean; LteMacBase.ned:56-79), emitted on the UE MAC at the gNB
    feedback event (LteHarqUnitTx.cc:165-195): an attribution made by the simulator itself"""
    out = defaultdict(dict)
    if not sca or not os.path.exists(sca):
        return None
    for line in open(sca, errors="replace"):
        if line.startswith("scalar "):
            parts = line.split()
            if len(parts) >= 4 and parts[2] in HARQ_SCALARS:
                out[parts[1]][parts[2]] = parts[3]
    return dict(out)


def elog(path):
    """the eventlog's coverage (record-eventlog, ..0.5 s): feedback air frames and gNB feedback log lines in it"""
    if not path or not os.path.exists(path):
        return None
    c = Counter()
    last_t = None
    for line in open(path, errors="replace"):
        if "harqFeedback" in line:
            c["lines naming harqFeedback"] += 1
        if "feedback received for process" in line:
            c["gNB feedback log lines"] += 1
        if "H-ARQ RX: feedback sent" in line:
            c["UE feedback log lines"] += 1
        if line.startswith("E "):
            m = re.search(r" t (\S+)", line)
            if m:
                last_t = m.group(1)
    c["last event time"] = last_t
    return dict(c)


def run(runs, cfg, outdir):
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    base = os.path.join(runs, cfg, cfg)
    rep = census(mlp)
    rep["harq_scalars"] = scalars(os.path.join(base, "0.sca"))
    rep["eventlog"] = elog(os.path.join(base, "0.elog"))
    ok = not any(x.startswith("FAILS") for x in rep["preconditions"].values())
    os.makedirs(outdir, exist_ok=True)
    p = os.path.join(outdir, f"a2probe-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"A-2 feasibility probe P0 on {cfg} (read-only; attributes nothing)\n\n")
        for k, v in rep["preconditions"].items():
            fh.write(f"  {v.split(' ')[0]:<13} | {k} | {v}\n")
        fh.write(f"\nd*_tx {rep['d_star_tx_ps']} ps; ages {rep['ages_ps']}\n")
        fh.write(f"line classes {rep['counts']}\n")
        fh.write(f"multi-candidate groups {rep['groups']}; certificate failures {rep['groups_certificate_failures']}\n")
        fh.write(f"open at end {rep['open_at_end']}\n")
        fh.write(f"violations (first 5 per precondition) {rep['violations']}\n")
        fh.write(f"Simu5G per-UE H-ARQ scalars {rep['harq_scalars']}\n")
        fh.write(f"eventlog coverage {rep['eventlog']}\n")
        fh.write(f"\nP0 verdict: {'no exercised precondition fails' if ok else 'A PRECONDITION FAILS'}\n")
    with open(os.path.join(outdir, f"a2probe-{cfg}.json"), "w") as fh:
        json.dump(rep, fh, indent=1, sort_keys=True, default=str)
    print(open(p).read().rstrip())
    return 0 if ok else 1


if __name__ == "__main__":
    if len(sys.argv) != 4:
        print(__doc__)
        sys.exit(2)
    try:
        sys.exit(run(sys.argv[1], sys.argv[2], sys.argv[3]))
    except Exception as ex:
        import traceback
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}")
        sys.exit(2)
