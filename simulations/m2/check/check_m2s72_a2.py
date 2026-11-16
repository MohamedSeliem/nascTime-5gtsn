#!/usr/bin/env python3
"""M2-S7.2a Stage 5: command-line checks of the DL H-ARQ attribution rule A-2 (m2s72_a2.py). Read-only on raw
outputs; no simulation. New tool: check_m2s72_s5n.py / _s5n2.py / _s5v.py and the adapter are unchanged.

    check_m2s72_a2.py a2 <runs> <cfg> <records dir> [--t0 <s>]
        rows A2-0 .. A2-8, per-UE outputs (counts, histograms, occupancy), the coverage table (what THIS run's real
        output exercised, and what is validated only on synthetic fixtures or not at all) -> a2-<cfg>.txt / .json.
        Exit 0 A-2 VALID, 1 NOT VALID, 4 INCOMPLETE, 2 evaluation error. $SIMU5G_ROOT: the run's Simu5G tree (A2-0s)
    check_m2s72_a2.py a2-controls <runs> <cfg> <records dir>
        the declared controls, in memory (raw outputs only read): on the real output (ACK-only paths), and on the real
        output with ONE source-faithful NACK -> retransmission -> ACK chain injected (real-context synthetic evidence
        for the NACK paths, labelled as such) -> a2-controls-<cfg>.txt / .json. Exit 0 iff every buildable control is
        as declared; a control that cannot be built on this run is reported NOT BUILDABLE, never counted as a pass

A-2 rows never replace, relabel or reclassify an accepted row: the recorded PU-4 FAIL of rule A-1 stands."""
import copy
import json
import os
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a2 as A2  # noqa: E402
import m2s72_a2probe as PR  # noqa: E402

MS, S = A2.MS, A2.S


def _durable(paths):
    try:
        import m2s72s5_lib as LIB
        LIB.durable(paths)
    except Exception:
        pass


def _nproc(cfg):
    _argv = sys.argv
    sys.argv = [_argv[0]]
    import check_m2s72_s5v as S5V
    sys.argv = _argv
    return 16 if S5V.parse_name(cfg)[2] else 5


def _node_ids(runs, cfg):
    try:
        import m2s72_runs as R
        return R.Run72(runs, cfg, 0).node_id
    except Exception as ex:
        print(f"note: run node ids unavailable ({type(ex).__name__}: {ex})")
        return None


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, set):
        return sorted(_clean(v) for v in x)
    return x


def evaluate(lines, nproc, t0, node_id=None, grants=None, sca=None, root=None):
    res = A2.replay(lines)
    window = (t0, (res["t_end"] // MS + 1) * MS)
    rows, per, cov, extra = A2.rows_for(res, lines, nproc, window, node_id=node_id, grants=grants, sca=sca, simu5g_root=root)
    return res, rows, per, cov, extra, window


def inputs(runs, cfg):
    import m2s72_maclog as ML
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    return (A2.load(mlp), ML.MacLog(mlp).grants, _node_ids(runs, cfg), os.path.join(runs, cfg, cfg, "0.sca"),
            os.environ.get("SIMU5G_ROOT"))


# --------------------------------------------------------------------------------------------------- a2 ---------
def a2(runs, cfg, recdir, t0=2 * S):
    lines, grants, node_id, sca, root = inputs(runs, cfg)
    res, rows, per, cov, extra, window = evaluate(lines, _nproc(cfg), t0, node_id, grants, sca, root)
    verdict, rc = A2.verdict(rows)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"a2-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a DL H-ARQ attribution A-2 (gNB-only unit-state) on {cfg}; window [{window[0]}, {window[1]}) ps\n")
        fh.write(f"{A2.NOTE}\n\nROWS\n")
        for r in rows:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {r[3]}\n")
        fh.write("\nCOVERAGE (what this run's real output exercised; never a claim beyond it)\n")
        for name, n, cls in cov:
            fh.write(f"  {n:>7} | {name} | {cls}\n")
        fh.write("\nPER UE (A-2 outputs; reported, never gates)\n")
        for n, o in per.items():
            occ = o["occupancy"]
            fh.write(f"  node {n}: inserts {o['inserts']}, transmissions {o['transmissions']}, feedback {o['feedback']} (ACK {o['ack']}, "
                     f"NACK {o['nack']}), discarded {o['discarded']}, lines {o['lines_by_class']}, end states {o['end_states']}, "
                     f"age {o['feedback_age_ps']}; occupancy max peak {occ.get('max_peak')}, busy at TTI start {occ.get('busy_at_tti_start_hist')}\n")
        fh.write(f"\nA-2 verdict: {verdict}\n")
    with open(os.path.join(recdir, f"a2-{cfg}.json"), "w") as fh:
        json.dump(_clean({"config": cfg, "rows": rows, "verdict": verdict, "coverage": cov, "per_ue": per, "d_star_ps": res["d_star"],
                          "t_end_ps": res["t_end"], "window_ps": window, "end_states": res["end_states"],
                          "group_sizes": {str(k): v for k, v in __import__("collections").Counter(len(g["cands"]) for g in res["groups"] if g["exchangeable"]).items()},
                          "a2_7": extra["xa"], "a2_8": extra["scalars"], "note": A2.NOTE}), fh, indent=1, sort_keys=True)
    _durable([p, os.path.join(recdir, f"a2-{cfg}.json")])
    print(open(p).read().rstrip())
    return rc


# --------------------------------------------------------------------------------------------- controls ---------
def gnb_positions(lines):
    """list index of every gNB line, in the gNB line numbering of A2.replay (gi starts at 1)"""
    pos = [None]
    for i, x in enumerate(lines):
        p = x.split("|", 2)
        if len(p) == 3 and p[0][:1].isdigit() and p[1] == A2.GNB:
            pos.append(i)
    return pos


def _t(x):
    return PR.t_ps(x.split("|", 1)[0])


def _put(lines, t, new, at_start):
    """insert new lines at the start (before the first line with time >= t) or at the end of time t"""
    i = next((i for i, x in enumerate(lines) if (_t(x) >= t if at_start else _t(x) > t)), len(lines) - 1)
    return lines[:i] + new + lines[i:]


def _ts(t):
    return f"{t // S}.{t % S:012d}"


def _now(t):
    """a time as OMNeT++ 6.5.0 writes the "%t" log prefix: the shortest decimal SimTime ('1.004', '12')"""
    return _ts(t).rstrip("0").rstrip(".")


def _retime(line, t):
    """the same log line with its time-stamp field (before the first '|') set to t; independent of how the original
    prefix was written (root cause of the NC-A2-shift no-op, report M2-S7.2a-a2-control-fix.md)"""
    return _now(t) + "|" + line.split("|", 1)[1]


def block_span(lines, fb_index):
    """list indices of the feedback event of the feedback line at fb_index: from its 'receiveHarqFeedback - start'"""
    i = fb_index
    while i > 0 and PR.T_START not in lines[i]:
        i -= 1
    return i, fb_index


def clean_single(res, lines, prefer_sparse=True, need_free=0):
    """a clean single-ACK PDU: one transmission, ACKed, its unit's (node, process) not reused within need_free ps
    after the feedback, the feedback not the last of the log. Prefers the node with the fewest PDUs."""
    by_node = __import__("collections").Counter(u["node"] for u in res["pdus"].values())
    order = sorted(by_node, key=lambda n: by_node[n]) if prefer_sparse else sorted(by_node, key=lambda n: -by_node[n])
    ins_by = {}
    for u in res["pdus"].values():
        ins_by.setdefault((u["node"], u["p"], u["cw"]), []).append(u["t_ins"])
    for n in order:
        for x in res["fb"]:
            if x["cls"] != "single" or x["owner"] != n or x["res"] != "ACK" or x["t"] < res["fb"][0]["t"] + 2 * MS:
                continue
            u = res["pdus"][x["pid"]]
            if u["ntx"] != 1 or x["t"] + need_free + 3 * MS > res["t_end"]:
                continue
            if any(x["t"] <= ti <= x["t"] + need_free for ti in ins_by[(n, u["p"], u["cw"])]):
                continue
            return x, u
    return None, None


def inject_nack(lines, res):
    """one source-faithful NACK -> retransmission -> ACK chain on a clean single PDU of the sparsest UE, gNB AND
    UE side (texts and call order of m2s72_harqfix / the 1.8.1 sources). Returns (lines, info) or (None, reason)."""
    d = res["d_star"]
    if d is None:
        return None, "no single d*_tx"
    x, u = clean_single(res, lines, need_free=d + MS - 1)      # the unit is held until its final ACK at tf + 1 TTI + d
    if x is None:
        return None, "no clean single PDU with a free process window"
    n, p, cw, pid, tf = u["node"], u["p"], u["cw"], u["pid"], x["t"]
    tr, t2 = tf + MS, tf + MS + d
    pos = gnb_positions(lines)
    out = list(lines)
    fbi = pos[x["gi"]]
    s0, s1 = block_span(out, fbi)
    ui = next((i for i in range(s0, s1) if PR.T_UACK in out[i]), None)
    if ui is None:
        return None, "unit ACK line not found"
    pre = out[ui].split("|", 2)
    out[ui] = f"{pre[0]}|{pre[1]}|{_now(tf)} LteHarqUnitTx::pduFeedback H-ARQ process  {p} Codeword {cw} PDU {pid} set for RTX \n"
    out[s1] = out[s1].replace("result is ACK", "result is NACK")
    # UE side: the UE that received the PDU, its feedback for it, and the offsets of this run
    rx = next(((i, y) for i, y in enumerate(out) if f"H-ARQ RX: new PDU (id {pid} )" in y), None)
    if rx is None:
        return None, "UE reception line not found"
    ue_mod = rx[1].split("|", 2)[1]
    t_rx = _t(rx[1])
    sent = next(((i, y) for i, y in enumerate(out) if i > rx[0] and y.split("|", 2)[1] == ue_mod
                 and f"feedback sent to TX process {p} " in y), None)
    if sent is None:
        return None, "UE feedback line not found"
    d_rx, d_fb = t_rx - u["txs"][0], tf - _t(sent[1])
    out[sent[0]] = sent[1].replace("result: ACK", "result: NACK")
    g = A2.GNB
    rtx = [f"{_now(tr)} LteSchedulerEnbDl::rtxschedule --------------------::[ START RTX-SCHEDULE ]::--------------------",
           f"{_now(tr)} LteSchedulerEnbDl::rtxschedule Cell:  1 Direction: DL",
           f"{_now(tr)} LteSchedulerEnbDl::rtxschedule  UE: {n}",
           f"{_now(tr)} LteSchedulerEnbDl::rtxschedule process {p}",
           f"{_now(tr)} LteSchedulerEnbDl::rtxschedule detected RTX Acid: {p}",
           f"{_now(tr)}LteSchedulerEnbDl::rtxAcid - Node [1], User[{n}],  Codeword [{cw}]  of [1] , ACID [{p}] ",
           f"{_now(tr)} LteSchedulerEnbDl::rtxAcid HARQ Process {p}  codeword  {cw} marking for retransmission ",
           f"H-ARQ TX: process {p} has been selected for retransmission",
           "    LteSchedulerEnbDl::rtxschedule --------------------::[  END RTX-SCHEDULE  ]::-------------------- ",
           f"\t H-ARQ TX: pdu (id {pid} ) extracted from process {p} codeword {cw} for node with id {n}"]
    out = _put(out, tr, [f"{_ts(tr)}|{g}|{m}\n" for m in rtx], at_start=False)
    out = _put(out, tr + d_rx, [f"{_ts(tr + d_rx)}|{ue_mod}|H-ARQ RX: new PDU (id {pid} ) inserted into process {p}\n"], at_start=False)
    out = _put(out, t2 - d_fb, [f"{_ts(t2 - d_fb)}|{ue_mod}|H-ARQ RX: feedback sent to TX process {p} Codeword  {cw} of node with id 1 result: ACK\n"],
               at_start=False)
    blk = ["LteHarqBufferTx::receiveHarqFeedback - start", "LteHarqUnitTx::pduFeedback - Welcome!",
           "\t pdu_ has been sent and received correctly ", f"H-ARQ TX: feedback received for process {p} codeword {cw} result is ACK"]
    out = _put(out, t2, [f"{_ts(t2)}|{g}|{m}\n" for m in blk], at_start=True)
    return out, {"pid": pid, "node": n, "process": p, "nack_t": tf, "rtx_t": tr, "ack_t": t2}


def _find(lines, pred, start=0):
    return next((i for i in range(start, len(lines)) if pred(lines[i])), None)


def controls(lines, nproc, t0, node_id=None, grants=None, sca=None, root=None):
    """returns [(name, kind, status, observed, declared)] with status AS DECLARED / NOT AS DECLARED / NOT BUILDABLE.
    kind: 'real output' (mutation of the real lines) or 'real output + injected NACK chain' (labelled synthetic)"""
    out = []
    base = A2.replay(lines)
    _, rows0, _, _, _, _ = evaluate(lines, nproc, t0, node_id, grants, sca, root)
    st0 = {r[0]: r[2] for r in rows0}

    state = {"same": False}

    def same_file(a, b):
        if a == b:
            return True
        if not a or not b or not os.path.exists(a) or not os.path.exists(b):
            return False
        return open(a, "rb").read() == open(b, "rb").read()

    def run(ls, gr=grants, sc=sca):
        # what the checker receives; a negative control whose input equals the unmodified input is a no-op
        state["same"] = ls == lines and gr == grants and same_file(sc, sca)
        _, rows, per, cov, extra, _ = evaluate(ls, nproc, t0, node_id, gr, sc, root)
        return {r[0]: r[2] for r in rows}, extra

    def rec(name, kind, ok, observed, declared):
        if name.startswith("NC-") and state["same"]:
            ok, observed = False, f"{observed} | MUTATION NOT APPLIED: the checker input is identical to the unmodified run"
        out.append((name, kind, "AS DECLARED" if ok else "NOT AS DECLARED", observed, declared))

    def nb(name, kind, why, declared):
        out.append((name, kind, "NOT BUILDABLE", why, declared))

    R = "real output"
    st, _ = run(lines)
    rec("PC-A2-unmodified", R, st == st0, f"{st}", "every row status reproduced")
    pos = gnb_positions(lines)
    x, u = clean_single(base, lines, need_free=0)
    if x is None:
        nb("NC-A2-* (real output)", R, "no clean single ACK line", "-")
        return out, st0
    fbi = pos[x["gi"]]
    s0, s1 = block_span(lines, fbi)
    # timing: the whole feedback event of one single ACK one TTI late
    moved = [_retime(y, x["t"] + MS) for y in lines[s0:s1 + 1]]
    ls = lines[:s0] + lines[s1 + 1:]
    ls = _put(ls, x["t"] + MS, moved, at_start=True)
    st, _ = run(ls)
    ok = all(_t(y) == x["t"] + MS for y in moved)
    rec("NC-A2-shift: one single ACK's feedback event one TTI late", R, ok and st["A2-3"] == "FAIL",
        f"A2-3 {st['A2-3']}; mutation: {len(moved)} lines retimed '{lines[s1].split('|', 1)[0]}' -> '{moved[-1].split('|', 1)[0]}' "
        f"(feedback age {(x['t'] - u['txs'][0]) // MS} -> {(x['t'] + MS - u['txs'][0]) // MS} ms)", "A2-3 FAIL")
    # duplicate feedback event
    st, _ = run(lines[:s1 + 1] + lines[s0:s1 + 1] + lines[s1 + 1:])
    rec("NC-A2-dupack: one ACK feedback event duplicated", R, st["A2-1"] == "FAIL", f"A2-1 {st['A2-1']}", "A2-1 FAIL")
    # feedback event removed
    st, _ = run(lines[:s0] + lines[s1 + 1:])
    rec("NC-A2-dropfb: one ACK feedback event removed", R, st["A2-2"] == "FAIL", f"A2-2 {st['A2-2']}, A2-6 {st['A2-6']}", "A2-2 FAIL")
    # unit line removed
    ui = _find(lines, lambda y: PR.T_UACK in y, s0)
    st, _ = run(lines[:ui] + lines[ui + 1:])
    rec("NC-A2-dropunit: the unit ACK line of one feedback event removed", R, st["A2-1"] == "FAIL" and st["A2-0"] == "FAIL",
        f"A2-1 {st['A2-1']}, A2-0 {st['A2-0']}", "A2-1 FAIL, A2-0 FAIL")
    # first transmission removed
    ei = _find(lines, lambda y: f"(id {u['pid']} ) extracted from process" in y)
    st, _ = run(lines[:ei] + lines[ei + 1:])
    rec("NC-A2-extract: the transmission line of one PDU removed", R, st["A2-2"] == "FAIL" or st["A2-1"] == "FAIL",
        f"A2-1 {st['A2-1']}, A2-2 {st['A2-2']}", "A2-1 or A2-2 FAIL")
    # duplicate insert
    ii = _find(lines, lambda y: f"new pdu (id {u['pid']} ) inserted" in y)
    st, _ = run(lines[:ii + 1] + [lines[ii]] + lines[ii + 1:])
    rec("NC-A2-dupins: one insert line duplicated", R, st["A2-2"] == "FAIL", f"A2-2 {st['A2-2']}", "A2-2 FAIL")
    # cross-UE swap of one PDU of the busiest UE (insert and transmission logged for another node)
    nodes = sorted({v["node"] for v in base["pdus"].values()})
    xb, ub = clean_single(base, lines, prefer_sparse=False)
    if len(nodes) >= 2 and xb is not None:
        other = next(nn for nn in nodes if nn != ub["node"])
        ls = [y.replace(f"for node with id {ub['node']}", f"for node with id {other}") if f"(id {ub['pid']} )" in y and y.split("|")[1] == A2.GNB else y
              for y in lines]
        st, _ = run(ls)
        rec("NC-A2-swap: one PDU's insert and transmission logged for the other UE's node", R, st["A2-7"] == "FAIL",
            f"A2-7 {st['A2-7']}, A2-6 {st['A2-6']}, A2-1 {st['A2-1']}", "A2-7 FAIL (the independent reference sees it)")
    else:
        nb("NC-A2-swap", R, "fewer than two UEs", "A2-7 FAIL")
    # independent reference broken: the UE-side lines of one PDU relabelled to another UE module
    if len(nodes) >= 2:
        mods = sorted({y.split("|")[1] for y in lines if PR.R_UE_MOD.match(y.split("|")[1])})
        rxi = _find(lines, lambda y: f"H-ARQ RX: new PDU (id {u['pid']} )" in y)
        if rxi is not None and len(mods) >= 2:
            m0 = lines[rxi].split("|")[1]
            m1 = next(m for m in mods if m != m0)
            ls = list(lines)
            ls[rxi] = ls[rxi].replace(m0, m1)
            st, _ = run(ls)
            rec("NC-A2-xa: one UE reception relabelled to another UE (reference evidence corrupted)", R, st["A2-7"] == "FAIL",
                f"A2-7 {st['A2-7']}", "A2-7 FAIL")
        else:
            nb("NC-A2-xa", R, "no UE-side lines for two UEs", "A2-7 FAIL")
    # grants
    if grants:
        gr = [g for g in grants if not (g[1] == "DL" and g[2] == u["node"] and g[0] // MS == u["t_ins"] // MS)]
        st, _ = run(lines, gr=gr)
        rec("NC-A2-grant: one UE's DL grants removed in one insert TTI", R, st["A2-6"] == "FAIL", f"A2-6 {st['A2-6']}", "A2-6 FAIL")
    else:
        nb("NC-A2-grant", R, "no grants", "A2-6 FAIL")
    # exchangeable group split by a main-loop event
    grp = next((g for g in base["groups"] if g["exchangeable"]), None)
    if grp is not None:
        a, b = pos[grp["lines"][0]["gi"]], pos[grp["lines"][1]["gi"]]
        nd = grp["cands"][0][0]
        tg = _ts(grp["t"])
        extra = [f"{tg}|{A2.GNB}|H-ARQ TX: new pdu (id 999999 ) inserted into process {nproc - 1} codeword id: 0 for node with id {nd}\n",
                 f"{tg}|{A2.GNB}|\t H-ARQ TX: pdu (id 999999 ) extracted from process {nproc - 1} codeword 0 for node with id {nd}\n"]
        st, _ = run(lines[:a + 1] + extra + lines[a + 1:])
        rec("NC-A2-cert: a candidate node's new transmission logged inside an exchangeable group", R, st["A2-5"] == "FAIL",
            f"A2-5 {st['A2-5']}", "A2-5 FAIL")
    else:
        nb("NC-A2-cert", R, "no exchangeable group in this run", "A2-5 FAIL")
    # Simu5G scalars perturbed
    if sca and os.path.exists(sca) and st0.get("A2-8") == "PASS":
        d = tempfile.mkdtemp()
        try:
            s2 = os.path.join(d, "0.sca")
            txt = open(sca).read().splitlines(True)
            # the line A2-8 actually compares: a UE NR MAC module with a macNodeId (not the first line of that name: the
            # gNB and LTE-leg MACs declare the same statistic; root cause of the NC-A2-scalar no-op)
            compared = A2.sca_nodes(sca)
            j = next((i for i, y in enumerate(txt) if y.startswith("scalar ") and len(y.split()) >= 4
                      and y.split()[2] == "harqErrorRateDl:mean" and y.split()[1] in compared and y.split()[3] != "nan"), None)
            if j is None:
                st, before, after = None, None, None
            else:
                p_ = txt[j].split()
                before, after = p_[3], repr(float(p_[3]) + 0.001)
                txt[j] = f"scalar {p_[1]} {p_[2]} {after}\n"
                open(s2, "w").writelines(txt)
                seen = (PR.scalars(s2) or {}).get(p_[1], {}).get(p_[2])          # what A2-8 reads from the mutated file
                st, _ = run(lines, sc=s2)
        finally:
            shutil.rmtree(d)
        if st is None:
            nb("NC-A2-scalar", R, "no compared UE NR MAC harqErrorRateDl:mean line", "A2-8 FAIL")
        else:
            rec("NC-A2-scalar: Simu5G harqErrorRateDl:mean of one compared UE perturbed", R, seen == after and st["A2-8"] == "FAIL",
                f"A2-8 {st['A2-8']}; mutation: {p_[1]} (node {compared[p_[1]]}) harqErrorRateDl:mean {before} -> {after}, A2-8 reads {seen}",
                "A2-8 FAIL")
    else:
        nb("NC-A2-scalar", R, f"A2-8 not PASS on the unmodified run ({st0.get('A2-8')})", "A2-8 FAIL")
    # end-of-run censoring: the log truncated at a TTI boundary in the middle of the run
    t_first = min(_t(y) for y in lines)
    mid = ((t_first + base["t_end"]) // 2) // MS * MS
    ls = [y for y in lines if _t(y) < mid]
    ls.append(A2.sentinel(A2.t_end_of(ls)))
    r2 = A2.replay(ls)
    st, _ = run(ls, gr=[g for g in grants if g[0] < mid] if grants else grants, sc=None)
    cens = r2["end_states"]
    ok = all(st[k] != "FAIL" for k in st) and cens.get("censored: awaiting feedback", 0) > 0
    rec("PC-A2-censor: log and grants truncated at a TTI boundary mid-run (Simu5G scalars not used: they are whole-run)", R, ok,
        f"rows {st}; end states {cens}", "no row FAIL; units awaiting feedback at the cut are censored")
    # ---- real output with one injected NACK chain (synthetic, labelled)
    K = "real output + injected NACK chain (synthetic)"
    inj, info = inject_nack(lines, base)
    if inj is None:
        nb("PC-A2-inject and NC-A2-nack*", K, info, "-")
        return out, st0
    st, extra = run(inj, sc=None)
    r3 = A2.replay(inj)
    ok = (st["A2-1"] == st["A2-2"] == st["A2-3"] == st["A2-4"] == st["A2-6"] == st["A2-7"] == "PASS" and st["A2-0"] == "PASS"
          and r3["counts"].get("retransmissions") == base["counts"].get("retransmissions", 0) + 1)
    rec(f"PC-A2-inject: NACK -> retransmission -> ACK of PDU {info['pid']} (node {info['node']}, process {info['process']})", K, ok,
        f"rows {st}; retransmissions {r3['counts'].get('retransmissions')}", "A2-0..A2-4, A2-6, A2-7 PASS; one retransmission, identified")
    ri = _find(inj, lambda y: f"PDU {info['pid']} set for RTX" in y)
    st, _ = run(inj[:ri] + inj[ri + 1:], sc=None)
    rec("NC-A2-nackid: the injected NACK's unit line removed", K, st["A2-1"] == "FAIL", f"A2-1 {st['A2-1']}", "A2-1 FAIL")
    ls = list(inj)
    ls[ri] = ls[ri].replace(f"PDU {info['pid']} set", "PDU 999998 set")
    st, _ = run(ls, sc=None)
    rec("NC-A2-nackswap: the injected NACK names another PDU", K, st["A2-1"] == "FAIL", f"A2-1 {st['A2-1']}", "A2-1 FAIL")
    ai = _find(inj, lambda y: "rtxAcid - Node" in y and f"User[{info['node']}]" in y and f"ACID [{info['process']}]" in y)
    other = next((nn for nn in nodes if nn != info["node"]), info["node"] + 1)
    ls = list(inj)
    ls[ai] = ls[ai].replace(f"User[{info['node']}]", f"User[{other}]")
    st, _ = run(ls, sc=None)
    rec("NC-A2-rtxacid: the scheduler names the other UE for the retransmission", K, st["A2-4"] == "FAIL", f"A2-4 {st['A2-4']}", "A2-4 FAIL")
    xi = [i for i, y in enumerate(inj) if f"(id {info['pid']} ) extracted from process" in y][-1]
    st, _ = run(inj[:xi] + inj[xi + 1:], sc=None)
    rec("NC-A2-rtxextract: the retransmission line removed", K, st["A2-1"] == "FAIL" or st["A2-2"] == "FAIL",
        f"A2-1 {st['A2-1']}, A2-2 {st['A2-2']}", "A2-1 or A2-2 FAIL")
    ls = list(inj)
    ls[ri] = ls[ri].replace("set for RTX ", "discarded (max retransmissions reached) : 3")
    st, _ = run(ls, sc=None)
    rec("NC-A2-discard: the injected NACK turned into a discard after 1 transmission (maxHarqRtx 3)", K, st["A2-2"] == "FAIL",
        f"A2-2 {st['A2-2']}", "A2-2 FAIL")
    return out, st0


def a2_controls(runs, cfg, recdir, t0=2 * S):
    lines, grants, node_id, sca, root = inputs(runs, cfg)
    out, st0 = controls(lines, _nproc(cfg), t0, node_id, grants, sca, root)
    built = [x for x in out if x[2] != "NOT BUILDABLE"]
    good = all(x[2] == "AS DECLARED" for x in built)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"a2-controls-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a A-2 controls on {cfg} (in memory; the raw outputs are only read)\nbaseline rows {st0}\n\n")
        for name, kind, status, obs, dec in out:
            fh.write(f"{status:<16} | {kind} | {name} | observed {obs} | declared {dec}\n")
        fh.write(f"\na2-controls on {cfg}: {sum(1 for x in built if x[2] == 'AS DECLARED')} / {len(built)} buildable controls as declared; "
                 f"not buildable on this run: {[x[0] for x in out if x[2] == 'NOT BUILDABLE']}\n")
    with open(os.path.join(recdir, f"a2-controls-{cfg}.json"), "w") as fh:
        json.dump({"config": cfg, "baseline": st0, "controls": [dict(zip(("name", "kind", "status", "observed", "declared"), x)) for x in out]},
                  fh, indent=1)
    _durable([p, os.path.join(recdir, f"a2-controls-{cfg}.json")])
    print(open(p).read().rstrip())
    return 0 if good and built else 1


def main(argv):
    try:
        t0 = 2 * S
        if "--t0" in argv:
            i = argv.index("--t0")
            t0 = int(float(argv[i + 1]) * S)
            argv = argv[:i] + argv[i + 2:]
        if len(argv) == 5 and argv[1] == "a2":
            return a2(argv[2], argv[3], argv[4], t0)
        if len(argv) == 5 and argv[1] == "a2-controls":
            return a2_controls(argv[2], argv[3], argv[4], t0)
    except Exception as ex:                     # an evaluation that cannot complete is never a PASS
        import traceback
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
