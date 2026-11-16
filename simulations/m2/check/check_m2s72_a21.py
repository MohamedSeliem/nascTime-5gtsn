#!/usr/bin/env python3
"""M2-S7.2a: command-line checks and declared controls of the DL H-ARQ attribution rule A-2.1 (m2s72_a21.py).
Read-only on raw outputs; no simulation. The frozen A-2 tools (check_m2s72_a2.py, m2s72_a2.py at fbee202) are unchanged.

    check_m2s72_a21.py a21 <runs> <cfg> <records dir> [--contract full|f1d-i] [--t0 <s>]
        rows A2-0 .. A2-9 (A2-4a / b / c separate), per-UE outputs, coverage -> a21-<cfg>.txt / .json.
        Exit 0 A-2.1 VALID, 1 NOT VALID, 4 INCOMPLETE, 2 evaluation error. Contract 'full' (default) requires A2-4c;
        'f1d-i' (decision F1-d (i): supplementary post-hoc validation only) reports A2-4c without requiring it.
    check_m2s72_a21.py a21-controls <runs> <cfg> <records dir>
        the declared controls, in memory: ACK-only mutations of the real output; the F1 controls on the real NACK
        evidence (or, if the run has none, on one injected chain in the corrected model, labelled synthetic).
        A negative control counts only if its declared row was PASS before the mutation and the failure names the
        mutated element (token); otherwise NOT BUILDABLE. A no-op mutation is MUTATION NOT APPLIED.
        Exit 0 iff every buildable control is as declared.

Not run on the sealed A2-V1 evidence by this increment (a separately authorised stage)."""
import json
import os
import shutil
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import check_m2s72_a2 as C  # noqa: E402  (frozen; reused read-only: _nproc, _node_ids, _clean, _durable, time helpers)
import m2s72_a21 as A  # noqa: E402
import m2s72_a2probe as PR  # noqa: E402

MS, S = A.MS, A.S
NOTB = "NOT BUILDABLE"


def inputs(runs, cfg):
    import m2s72_maclog as ML
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    return (A.load(mlp), ML.MacLog(mlp).grants, C._node_ids(runs, cfg), os.path.join(runs, cfg, cfg, "0.sca"),
            os.environ.get("SIMU5G_ROOT"))


def a21(runs, cfg, recdir, contract="full", t0=2 * S):
    lines, grants, node_id, sca, root = inputs(runs, cfg)
    res, rows, per, cov, extra, window = A.evaluate(lines, C._nproc(cfg), t0, node_id, grants, sca, root)
    verdict, rc = A.verdict(rows, contract)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"a21-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a DL H-ARQ attribution {A.VERSION} on {cfg}; contract {contract}; window [{window[0]}, {window[1]}) ps\n")
        fh.write(f"{A.NOTE}\n\nROWS\n")
        for r in rows:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {r[3]}\n")
        fh.write("\nCOVERAGE\n")
        for name, n, cls in cov:
            fh.write(f"  {n:>7} | {name} | {cls}\n")
        fh.write("\nPER UE\n")
        for n, o in per.items():
            fh.write(f"  node {n}: inserts {o['inserts']}, transmissions {o['transmissions']}, feedback {o['feedback']} (ACK {o['ack']}, "
                     f"NACK {o['nack']}), discarded {o['discarded']}, lines {o['lines_by_class']}, end states {o['end_states']}\n")
        fh.write(f"\nhandles: {Counter(h['st'] for h in res['handles'].values())}; unresolved {res['unresolved'][:5]}\n")
        fh.write(f"\n{A.VERSION} verdict ({contract}): {verdict}\n")
    with open(os.path.join(recdir, f"a21-{cfg}.json"), "w") as fh:
        json.dump(C._clean({"config": cfg, "version": A.VERSION, "contract": contract, "rows": rows, "verdict": verdict,
                            "coverage": cov, "per_ue": per, "d_star_ps": res["d_star"], "t_end_ps": res["t_end"],
                            "window_ps": window, "end_states": res["end_states"], "handles": res["handles"],
                            "unresolved": res["unresolved"], "a2_7": extra["xa"], "a2_8": extra["scalars"],
                            "preconditions": extra["preconditions"], "note": A.NOTE}), fh, indent=1, sort_keys=True)
    C._durable([p, os.path.join(recdir, f"a21-{cfg}.json")])
    print(open(p).read().rstrip())
    return rc


# --------------------------------------------------------------------------------------------- controls ---------
_t, _put, _ts, _now, _retime = C._t, C._put, C._ts, C._now, C._retime


def gnb_pos(lines):
    pos = [None]
    for i, x in enumerate(lines):
        p = x.split("|", 2)
        if len(p) == 3 and p[0][:1].isdigit() and p[1] == A.GNB:
            pos.append(i)
    return pos


def _find(lines, pred, start=0):
    return next((i for i in range(start, len(lines)) if pred(lines[i])), None)


def inject_nack21(lines, res):
    """one NACK -> retransmission -> ACK chain in the CORRECTED model (handle namespace, retransmission one TTI after
    the NACK, 'selected for retransmission' under the MAC, no scheduler-module line) on a clean single PDU"""
    d = res["d_star"]
    if d is None:
        return None, "no single d*_tx"
    x, u = C.clean_single(res, lines, need_free=d + MS - 1)
    if x is None:
        return None, "no clean single PDU with a free process window"
    n, p, cw, pid, tf = u["node"], u["p"], u["cw"], u["pid"], x["t"]
    tr, t2 = tf + MS, tf + MS + d
    used = set(res["pdus"]) | {h for h in res["handles"]}
    h = max(used | {0}) + 1_000_003
    pos = gnb_pos(lines)
    out = list(lines)
    fbi = pos[x["gi"]]
    s0, s1 = C.block_span(out, fbi)
    ui = next((i for i in range(s0, s1) if PR.T_UACK in out[i]), None)
    if ui is None:
        return None, "unit ACK line not found"
    pre = out[ui].split("|", 2)
    out[ui] = f"{pre[0]}|{pre[1]}|{_now(tf)} LteHarqUnitTx::pduFeedback H-ARQ process  {p} Codeword {cw} PDU {h} set for RTX \n"
    out[s1] = out[s1].replace("result is ACK", "result is NACK")
    rx = next(((i, y) for i, y in enumerate(out) if f"H-ARQ RX: new PDU (id {pid} )" in y), None)
    if rx is None:
        return None, "UE reception line not found"
    ue_mod = rx[1].split("|", 2)[1]
    t_rx = _t(rx[1])
    sent = next(((i, y) for i, y in enumerate(out) if i > rx[0] and y.split("|", 2)[1] == ue_mod and f"feedback sent to TX process {p} " in y), None)
    if sent is None:
        return None, "UE feedback line not found"
    d_rx, d_fb = t_rx - u["txs"][0], tf - _t(sent[1])
    out[sent[0]] = sent[1].replace("result: ACK", "result: NACK")
    g = A.GNB
    out = _put(out, tr, [f"{_ts(tr)}|{g}|H-ARQ TX: process {p} has been selected for retransmission\n",
                         f"{_ts(tr)}|{g}|\t H-ARQ TX: pdu (id {pid} ) extracted from process {p} codeword {cw} for node with id {n}\n"], at_start=False)
    out = _put(out, tr + d_rx, [f"{_ts(tr + d_rx)}|{ue_mod}|H-ARQ RX: new PDU (id {pid} ) inserted into process {p}\n"], at_start=False)
    out = _put(out, t2 - d_fb, [f"{_ts(t2 - d_fb)}|{ue_mod}|H-ARQ RX: feedback sent to TX process {p} Codeword  {cw} of node with id 1 result: ACK\n"],
               at_start=False)
    blk = ["LteHarqBufferTx::receiveHarqFeedback - start", "LteHarqUnitTx::pduFeedback - Welcome!",
           "\t pdu_ has been sent and received correctly ", f"H-ARQ TX: feedback received for process {p} codeword {cw} result is ACK"]
    out = _put(out, t2, [f"{_ts(t2)}|{g}|{m}\n" for m in blk], at_start=True)
    return out, {"pid": pid, "node": n, "process": p, "handle": h, "nack_t": tf, "rtx_t": tr, "ack_t": t2}


def nack_targets(res):
    """the NACK lines of a run, best first: a deferred (mixed) one, then a bound / single one; with its lifecycle"""
    out = []
    for cls in ("resolved-by-rtx", "single", "bound"):
        for x in res["fb"]:
            if x["res"] == "NACK" and x["cls"] == cls and x["block_kind"] == "rtx":
                out.append(x)
    return out


def controls(lines, nproc, t0, node_id=None, grants=None, sca=None, root=None):
    out = []
    base = A.replay(lines)
    _, rows0, _, _, _, _ = A.evaluate(lines, nproc, t0, node_id, grants, sca, root)
    st0 = {r[0]: r[2] for r in rows0}
    state = {"same": False}

    def same_file(a, b):
        if a == b:
            return True
        if not a or not b or not os.path.exists(a) or not os.path.exists(b):
            return False
        return open(a, "rb").read() == open(b, "rb").read()

    def run(ls, gr=grants, sc=sca):
        state["same"] = ls == lines and gr == grants and same_file(sc, sca)
        _, rows, _, _, _, _ = A.evaluate(ls, nproc, t0, node_id, gr, sc, root)
        return {r[0]: r[2] for r in rows}, {r[0]: r[3] for r in rows}, rows

    def rec(name, kind, ok, observed, declared):
        if name.startswith("NC-") and state["same"]:
            ok, observed = False, f"{observed} | MUTATION NOT APPLIED"
        out.append((name, kind, "AS DECLARED" if ok else "NOT AS DECLARED", observed, declared))

    def nb(name, kind, why, declared):
        out.append((name, kind, NOTB, why, declared))

    def nc(name, kind, ls, rows, token=None, base_st=None, gr=grants, sc=sca):
        """a negative control: every declared row must be PASS before the mutation (else NOT BUILDABLE: an already
        failing row would not isolate the defect); after it, at least one declared row must FAIL and, when a token is
        given, that row's detail must name the mutated element"""
        rows = [rows] if isinstance(rows, str) else list(rows)
        bst = base_st or st0
        notpass = {r: bst.get(r) for r in rows if bst.get(r) != "PASS"}
        if notpass:
            nb(name, kind, f"declared row(s) not PASS before the mutation {notpass} (would not isolate the defect)", f"{' or '.join(rows)} FAIL")
            return
        st, det, _ = run(ls, gr=gr, sc=sc)
        hit = [r for r in rows if st.get(r) == "FAIL" and (token is None or str(token) in det.get(r, ""))]
        rec(name, kind, bool(hit), ", ".join(f"{r} {st.get(r)}" for r in rows) + (f"; token {token} named by {hit}" if token is not None else ""),
            f"{' or '.join(rows)} FAIL" + (f" naming {token}" if token is not None else ""))

    R = "real output"
    st, _, _ = run(lines)
    rec("PC-A21-unmodified", R, st == st0, f"{st}", "every row status reproduced")
    pos = gnb_pos(lines)
    x, u = C.clean_single(base, lines, need_free=0)
    if x is None:
        nb("NC-A21-* (ACK-only, real output)", R, "no clean single ACK line", "-")
    else:
        fbi = pos[x["gi"]]
        s0, s1 = C.block_span(lines, fbi)
        moved = [_retime(y, x["t"] + MS) for y in lines[s0:s1 + 1]]
        ls = _put(lines[:s0] + lines[s1 + 1:], x["t"] + MS, moved, at_start=True)
        nc("NC-A21-shift: one single ACK's feedback event one TTI late", R, ls, "A2-3")
        nc("NC-A21-dupack: one ACK feedback event duplicated", R, lines[:s1 + 1] + lines[s0:s1 + 1] + lines[s1 + 1:], "A2-1")
        nc("NC-A21-dropfb: one ACK feedback event removed", R, lines[:s0] + lines[s1 + 1:], "A2-2")   # no token: the
        # missing event shifts the attribution of the next event on that process, so A2-2 may name a neighbouring PDU
        ui = _find(lines, lambda y: PR.T_UACK in y, s0)
        nc("NC-A21-dropunit: the unit ACK line of one feedback event removed", R, lines[:ui] + lines[ui + 1:], "A2-0")
        ei = _find(lines, lambda y: f"(id {u['pid']} ) extracted from process" in y)
        nc("NC-A21-extract: the transmission line of one PDU removed", R, lines[:ei] + lines[ei + 1:], "A2-2", token=u["pid"])
        ii = _find(lines, lambda y: f"new pdu (id {u['pid']} ) inserted" in y)
        nc("NC-A21-dupins: one insert line duplicated", R, lines[:ii + 1] + [lines[ii]] + lines[ii + 1:], "A2-2", token=u["pid"])
        nodes = sorted({v["node"] for v in base["pdus"].values()})
        mods = sorted({y.split("|")[1] for y in lines if PR.R_UE_MOD.match(y.split("|")[1])})
        rxi = _find(lines, lambda y: f"H-ARQ RX: new PDU (id {u['pid']} )" in y)
        if len(nodes) >= 2 and rxi is not None and len(mods) >= 2:
            m0 = lines[rxi].split("|")[1]
            ls = list(lines)
            ls[rxi] = ls[rxi].replace(m0, next(m for m in mods if m != m0))
            nc("NC-A21-xa: one UE reception relabelled to another UE (reference evidence corrupted)", R, ls, "A2-7")
        else:
            nb("NC-A21-xa", R, "no UE-side lines for two UEs", "A2-7 FAIL")
        if grants:
            gr = [g for g in grants if not (g[1] == "DL" and g[2] == u["node"] and g[0] // MS == u["t_ins"] // MS)]
            nc("NC-A21-grant: one UE's DL grants removed in one insert TTI", R, lines, "A2-6", token=u["node"], gr=gr)
        else:
            nb("NC-A21-grant", R, "no grants", "A2-6 FAIL")
        grp = next((g for g in base["groups"] if g["exchangeable"]), None)
        if grp is not None:
            a = pos[grp["lines"][0]["gi"]]
            nd = grp["cands"][0][0]
            tg = _ts(grp["t"])
            extra = [f"{tg}|{A.GNB}|H-ARQ TX: new pdu (id 999999 ) inserted into process {nproc - 1} codeword id: 0 for node with id {nd}\n",
                     f"{tg}|{A.GNB}|\t H-ARQ TX: pdu (id 999999 ) extracted from process {nproc - 1} codeword 0 for node with id {nd}\n"]
            nc("NC-A21-cert: a candidate node's new transmission logged inside an exchangeable group", R, lines[:a + 1] + extra + lines[a + 1:], "A2-5")
        else:
            nb("NC-A21-cert", R, "no exchangeable group", "A2-5 FAIL")
    if sca and os.path.exists(sca) and st0.get("A2-8") == "PASS":
        d = tempfile.mkdtemp()
        try:
            s2 = os.path.join(d, "0.sca")
            txt = open(sca).read().splitlines(True)
            compared = A.A2.sca_nodes(sca)
            j = next((i for i, y in enumerate(txt) if y.startswith("scalar ") and len(y.split()) >= 4 and y.split()[2] == "harqErrorRateDl:mean"
                      and y.split()[1] in compared and y.split()[3] != "nan"), None)
            if j is None:
                nb("NC-A21-scalar", R, "no compared UE NR MAC harqErrorRateDl:mean line", "A2-8 FAIL")
            else:
                p_ = txt[j].split()
                after = repr(float(p_[3]) + 0.001)
                txt[j] = f"scalar {p_[1]} {p_[2]} {after}\n"
                open(s2, "w").writelines(txt)
                nc("NC-A21-scalar: Simu5G harqErrorRateDl:mean of one compared UE perturbed", R, lines, "A2-8", token=compared[p_[1]], sc=s2)
        finally:
            shutil.rmtree(d)
    else:
        nb("NC-A21-scalar", R, f"A2-8 is {st0.get('A2-8')} on the unmodified run", "A2-8 FAIL")

    # ---- F1 controls: on the run's real NACK evidence, else on one injected chain (synthetic, labelled) ----
    targets = nack_targets(base)
    if targets:
        K, L, B = R, lines, base
        st_b = st0
    else:
        K = "real output + injected NACK chain (corrected model; synthetic)"
        L, info = inject_nack21(lines, base)
        if L is None:
            nb("NC-F1-* (no NACK evidence and no injectable chain)", K, info, "-")
            return out, st0
        B = A.replay(L)
        st_b, _, rows_b = run(L, sc=None)
        good = all(st_b.get(k) in ("PASS", "NOT EVALUATED") for k in ("A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-6", "A2-7", "A2-9")) \
            and st_b.get("A2-4a") == "PASS"
        rec(f"PC-F1-inject: NACK -> retransmission -> ACK of PDU {info['pid']} (handle {info['handle']}, node {info['node']})", K, good,
            f"rows {st_b}", "A2-1..A2-3, A2-4a, A2-4b, A2-6, A2-7, A2-9 PASS")
        targets = nack_targets(B)
    sc_b = sca if K == R else None
    x = targets[0]
    u = B["pdus"][x["pid"]]
    xpos = gnb_pos(L)
    # the retransmission that follows this NACK (first extract of the same MAC id after the NACK line)
    ri = _find(L, lambda y: f"(id {u['pid']} ) extracted from process" in y and y.split("|")[1] == A.GNB, xpos[x["gi"]] + 1)
    grp = next((g for g in B["groups"] if any(l is x for l in g["lines"])), None)
    other = None
    if grp is not None:
        okeys = [c for c in grp["cands"] if c != (u["node"], u["p"], u["cw"])]
        other = next((q for q in B["pdus"].values() if (q["node"], q["p"], q["cw"]) in okeys and q["t_ins"] < x["t"]
                      and (q.get("t_close") is None or q["t_close"] >= x["t"])), None)
    if ri is None:
        nb("NC-F1-rtx* / select / rtxnode", K, "no retransmission after the chosen NACK", "-")
    else:
        if other is not None:
            moved = L[ri].replace(f"(id {u['pid']} )", f"(id {other['pid']} )").replace(f"node with id {u['node']}", f"node with id {other['node']}")
            ls = L[:ri] + [moved] + L[ri + 1:]
            nc("NC-F1-rtxmove: the retransmission names the other candidate's PDU", K, ls, ["A2-1", "A2-2", "A2-7"], base_st=st_b, sc=sc_b)
            nc("NC-F1-doublertx: the other candidate retransmitted too", K, L[:ri + 1] + [moved] + L[ri + 1:], ["A2-1", "A2-2"], base_st=st_b, sc=sc_b)
        else:
            nb("NC-F1-rtxmove / doublertx", K, "the chosen NACK's group has no other candidate (no mixed group)", "A2-1 / A2-2 FAIL")
        ls = L[:ri] + L[ri + 1:]
        b = st_b.get("A2-9"), st_b.get("A2-1"), st_b.get("A2-2")
        stx, det, rows_x = run(ls, sc=sc_b)
        vx, _ = A.verdict(rows_x, "f1d-i")
        rec("NC-F1-nortx: the retransmission after the NACK removed", K, "VALID" not in vx or "NOT VALID" in vx,
            f"verdict {vx}; A2-1 {stx.get('A2-1')}, A2-2 {stx.get('A2-2')}, A2-9 {stx.get('A2-9')}", "A-2.1 not VALID (FAIL or INCOMPLETE)")
        si = max((i for i in range(ri) if f"process {u['p']} has been selected for retransmission" in L[i]), default=None)
        if si is not None:
            nc("NC-F1-select: the 'selected for retransmission' line of the retransmission removed", K, L[:si] + L[si + 1:], "A2-4a",
               token=u["pid"], base_st=st_b, sc=sc_b)
        else:
            nb("NC-F1-select", K, "no selection line before the retransmission", "A2-4a FAIL")
        rxs = [i for i, y in enumerate(L) if f"H-ARQ RX: new PDU (id {u['pid']} )" in y]
        mods = sorted({y.split("|")[1] for y in L if PR.R_UE_MOD.match(y.split("|")[1])})
        if len(rxs) >= 2 and len(mods) >= 2:
            m0 = L[rxs[1]].split("|")[1]
            ls = list(L)
            ls[rxs[1]] = ls[rxs[1]].replace(m0, next(m for m in mods if m != m0))
            nc("NC-F1-rtxnode: the UE-side reception of the retransmission relabelled to the other UE", K, ls, ["A2-4b"], token=u["pid"],
               base_st=st_b, sc=sc_b)
        else:
            nb("NC-F1-rtxnode", K, "no UE-side reception of the retransmission, or one UE", "A2-4b FAIL")
    # handles: a later NACK of the same lifecycle with another handle; with a foreign / retired handle
    nks = [y for y in B["fb"] if y["res"] == "NACK" and y["pid"] == u["pid"]]
    ui2 = None
    if len(nks) >= 2:
        s0_, s1_ = C.block_span(L, xpos[nks[1]["gi"]])
        ui2 = _find(L, lambda y: (PR.R_URTX.search(y) or PR.R_UDISC.search(y)) is not None, s0_)
    if ui2 is not None:
        h = nks[1]["handle"]
        fresh = max(set(B["pdus"]) | set(B["handles"]) | {0}) + 7_000_001
        ls = list(L)
        ls[ui2] = ls[ui2].replace(f"PDU {h} ", f"PDU {fresh} ")
        nc("NC-F1-handle: a later NACK of the same lifecycle prints another handle", K, ls, "A2-1", token=fresh, base_st=st_b, sc=sc_b)
        foreign = next((hh for hh, hs in B["handles"].items() if hs["lc"] != u["pid"] and hs["st"] in ("bound", "retired")), None)
        if foreign is not None:
            ls = list(L)
            ls[ui2] = ls[ui2].replace(f"PDU {h} ", f"PDU {foreign} ")
            nc("NC-F1-handle-foreign: a later NACK prints another lifecycle's handle", K, ls, "A2-1", token=foreign, base_st=st_b, sc=sc_b)
        else:
            nb("NC-F1-handle-foreign", K, "no other bound / retired handle in this input", "A2-1 FAIL")
    else:
        nb("NC-F1-handle / handle-foreign", K, "no lifecycle with two NACKs in this input", "A2-1 FAIL")
    pick = None
    for hh, hs in B["handles"].items():
        lc = hs["lc"]
        if hs["st"] != "retired" or not isinstance(lc, int) or B["pdus"].get(lc, {}).get("t_close") is None:
            continue
        y = next((y for y in B["fb"] if y["res"] == "NACK" and y["t"] > B["pdus"][lc]["t_close"] and y["handle"] != hh), None)
        if y is not None:
            pick = (hh, y)
            break
    if pick is not None:
        hh, y = pick
        s0_, _ = C.block_span(L, xpos[y["gi"]])
        k_ = _find(L, lambda z: (PR.R_URTX.search(z) or PR.R_UDISC.search(z)) is not None, s0_)
        ls = list(L)
        ls[k_] = ls[k_].replace(f"PDU {y['handle']} ", f"PDU {hh} ")
        nc("NC-F1-retired: a retired handle reappears on a later NACK", K, ls, "A2-1", token=hh, base_st=st_b, sc=sc_b)
    else:
        nb("NC-F1-retired", K, "no retired handle followed by a later NACK of another lifecycle", "A2-1 FAIL")
    # end of the log right after the chosen NACK (before its retransmission)
    s0_, s1_ = C.block_span(L, xpos[x["gi"]])
    cut = [y for y in L[:s1_ + 1] if A.SENTINEL_MOD not in y]
    if any(A.ML_END in y for y in L):
        c1 = cut + [A.sentinel(A.t_end_of(cut))]
        st1, _, rows1 = run(c1, gr=[g for g in grants if g[0] <= x["t"]] if grants else grants, sc=None)
        rec("PC-F1-endcensor: log ends right after the NACK (no complete main loop after it) -> structural censoring",
            K, st1.get("A2-9") == "PASS" and st1.get("A2-2") != "FAIL", f"A2-9 {st1.get('A2-9')}, A2-2 {st1.get('A2-2')}", "A2-9 PASS (censored)")
        tl = x["t"]          # a complete main loop AFTER the NACK in log order, at the same time (t_end unchanged)
        c2 = cut + [f"{_ts(tl)}|{A.GNB}|{A.ML_START}\n", f"{_ts(tl)}|{A.GNB}|{A.ML_END}\n"]
        c2 = c2 + [A.sentinel(A.t_end_of(c2))]
        st2, det2, rows2 = run(c2, gr=[g for g in grants if g[0] <= x["t"]] if grants else grants, sc=None)
        rec("NC-F1-endfake: a complete main loop follows the NACK, no retransmission -> UNRESOLVED (INCOMPLETE), never censored",
            K, st2.get("A2-9") == NE_ and "INCOMPLETE" in A.verdict(rows2, "f1d-i")[0], f"A2-9 {st2.get('A2-9')}; {A.verdict(rows2, 'f1d-i')[0]}",
            "A2-9 NOT EVALUATED, verdict INCOMPLETE")
    else:
        nb("PC-F1-endcensor / NC-F1-endfake", K, "no main-loop markers in this log", "-")
    # UE-side NACK of the chosen lifecycle written as ACK
    mod_u = next((y.split("|")[1] for y in L if f"H-ARQ RX: new PDU (id {u['pid']} )" in y), None)
    us = [i for i, y in enumerate(L) if y.split("|")[1:2] == [mod_u] and "result: NACK" in y and f"TX process {u['p']} " in y and _t(y) <= x["t"]]
    if us:
        ls = list(L)
        ls[us[-1]] = ls[us[-1]].replace("result: NACK", "result: ACK")
        nc("NC-F1-xa: one UE-side NACK of the chosen lifecycle written as ACK", K, ls, "A2-7", base_st=st_b, sc=sc_b)
    else:
        nb("NC-F1-xa", K, "UE-side NACK line not found", "A2-7 FAIL")
    return out, st0


NE_ = A.NE


def a21_controls(runs, cfg, recdir, t0=2 * S):
    lines, grants, node_id, sca, root = inputs(runs, cfg)
    out, st0 = controls(lines, C._nproc(cfg), t0, node_id, grants, sca, root)
    built = [x for x in out if x[2] != NOTB]
    good = all(x[2] == "AS DECLARED" for x in built)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"a21-controls-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a {A.VERSION} controls on {cfg} (in memory; the raw outputs are only read)\nbaseline rows {st0}\n\n")
        for name, kind, status, obs, dec in out:
            fh.write(f"{status:<16} | {kind} | {name} | observed {obs} | declared {dec}\n")
        fh.write(f"\na21-controls on {cfg}: {sum(1 for x in built if x[2] == 'AS DECLARED')} / {len(built)} buildable controls as declared; "
                 f"not buildable: {[x[0] for x in out if x[2] == NOTB]}\n")
    with open(os.path.join(recdir, f"a21-controls-{cfg}.json"), "w") as fh:
        json.dump({"config": cfg, "baseline": st0, "controls": [dict(zip(("name", "kind", "status", "observed", "declared"), x)) for x in out]},
                  fh, indent=1)
    C._durable([p, os.path.join(recdir, f"a21-controls-{cfg}.json")])
    print(open(p).read().rstrip())
    return 0 if good and built else 1


def main(argv):
    try:
        t0 = 2 * S
        contract = "full"
        if "--t0" in argv:
            i = argv.index("--t0")
            t0 = int(float(argv[i + 1]) * S)
            argv = argv[:i] + argv[i + 2:]
        if "--contract" in argv:
            i = argv.index("--contract")
            contract = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
            if contract not in A.REQUIRED:
                raise ValueError(f"unknown contract {contract}")
        if len(argv) == 5 and argv[1] == "a21":
            return a21(argv[2], argv[3], argv[4], contract, t0)
        if len(argv) == 5 and argv[1] == "a21-controls":
            return a21_controls(argv[2], argv[3], argv[4], t0)
    except Exception as ex:
        import traceback
        traceback.print_exc()
        print(f"EVALUATION ERROR: {type(ex).__name__}: {ex}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
