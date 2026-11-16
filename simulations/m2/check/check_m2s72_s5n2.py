#!/usr/bin/env python3
"""M2-S7.2a Stage 5, N = 2 increment: the multi-UE smoke's own checks (protocol results/M2-S7.2a-s5-n2-protocol.md).
Read-only on the raw outputs; no simulation; every accepted / S5-1 / S5-2 checker is called unchanged.

    check_m2s72_s5n2.py xa <runs> <cfg> <records dir>
        the independent UE-side H-ARQ reference (m2s72_harqx: XA-0 .. XA-6, overlap census, truth occupancy) on one run
        with MAC logs. Works for N = 1 too: run first on the preserved N = 1 smoke output as the positive control.
        -> xa-<cfg>.txt, xa-<cfg>.json; exit 0 iff XA-0 .. XA-5 PASS and XA-6 PASS (or NOT EVALUATED because A-1 is
        not exact), 1 otherwise, 2 evaluation error
    check_m2s72_s5n2.py controls-n2 <runs> <cfg> <option> <dl UEs> <ul UEs> <records dir>
        the declared multi-UE negative / positive controls, in memory on the run's real output (the raw files are
        never written): cross-UE misattribution, orphan feedback, duplicate insert, inconsistent totals, UE-side
        evidence removed / relabelled, timing shift, grant removed, per-UE Q8 delivery removed (UE 0 and UE 1, with
        the other UE's Q8 row required unchanged), declared load flipped, duplicate node id, PU-2 / PU-3 accounting
        -> controls-n2-<cfg>.txt / .json; exit 0 iff every control is as declared
    check_m2s72_s5n2.py verdict <records dir> <cfg>
        applies the acceptance rules of protocol §6 (N2-A0 .. N2-A8) to the records of the smoke stage
        -> smoke-n2-verdict-<cfg>.txt / .json; exit 0 VALIDATED, 3 VALIDATED WITH A-1 LIMITATION, 1 NOT VALIDATED,
        4 INCOMPLETE, 2 evaluation error
"""
import copy
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_harqx as H  # noqa: E402
import m2s72_peru as P  # noqa: E402

NE = "NOT EVALUATED"


def _durable(paths):
    try:
        import m2s72s5_lib as LIB
        LIB.durable(paths)
    except Exception:                                  # a missing fsync helper never changes a record
        pass


def _nproc(cfg):
    _argv = sys.argv
    sys.argv = [_argv[0]]
    import check_m2s72_s5v as S5V
    sys.argv = _argv
    kind, o, h16, f, n = S5V.parse_name(cfg)
    return 16 if h16 else 5


def _node_ids(runs, cfg):
    try:
        import m2s72_runs as R
        return R.Run72(runs, cfg, 0).node_id
    except Exception as ex:                            # XA-0 then reports the bijection only
        print(f"note: run node ids unavailable ({type(ex).__name__}: {ex})")
        return None


def _grants(mlp):
    import m2s72_maclog as ML
    return ML.MacLog(mlp).grants


def xa_ok(rows):
    st = {r[0]: r[2] for r in rows}
    if any(st.get(x) != "PASS" for x in ("XA-0", "XA-1", "XA-2", "XA-3", "XA-4", "XA-5")):
        return False
    return st.get("XA-6") == "PASS" or (st.get("XA-6") == NE and "not exact" in next(r[3] for r in rows if r[0] == "XA-6"))


def write_rows(path, title, rows, footer):
    with open(path, "w") as fh:
        fh.write(title + "\n\n")
        for r in rows:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {r[3]}\n")
        fh.write("\n" + footer + "\n")


def xa(runs, cfg, recdir):
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    log = H.read_log(mlp)
    import m2s72_peru_adapter as A
    same = log["events"] == A.harq_events(mlp)          # the reader is the adapter's (contract; on the real log)
    node_id = _node_ids(runs, cfg)
    rows, rep, _ = H.crossvalidate(log, _nproc(cfg), node_id=node_id, grants=_grants(mlp))
    rows.insert(0, ("XA-pre", "run", "PASS" if same else "FAIL",
                    f"gNB H-ARQ event list identical to m2s72_peru_adapter.harq_events(): {same} ({len(log['events'])} events); "
                    f"UE modules with H-ARQ RX lines {sorted(set(log['ue_rx']) | set(log['ue_fb']))}"))
    ok = same and xa_ok(rows[1:])
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"xa-{cfg}.txt")
    cen = rep["overlap_census"]
    write_rows(p, f"M2-S7.2a N = 2 increment: UE-side H-ARQ reference (XA) on {cfg}", rows,
               f"overlap census (gNB feedback lines by true holders of the process): {cen}\n"
               f"A-1 summary: {rep['a1_summary']}\n"
               f"UE-sent NACKs {rep['nack_ue_sent']}, retransmitted PDU ids {rep['retransmitted_pdus']}\n"
               f"XA verdict: {'PASS' if ok else 'FAIL'}")
    pj = os.path.join(recdir, f"xa-{cfg}.json")
    with open(pj, "w") as fh:
        json.dump(_clean({"config": cfg, "rows": rows, "report": rep}), fh, indent=1, sort_keys=True)
    _durable([p, pj])
    print(open(p).read().rstrip())
    return 0 if ok else 1


def _clean(x):
    if isinstance(x, dict):
        return {str(k): _clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_clean(v) for v in x]
    if isinstance(x, set):
        return sorted(_clean(v) for v in x)
    if isinstance(x, float) and x in (float("inf"), float("-inf")):
        return str(x)
    return x


# ----------------------------------------------------------------------------------------------- controls --------
def _status(rows):
    return {(r[0], r[1]): r[2] for r in rows}


def _pu45(log, nproc, node_id, grants, totals_add=0):
    """PU-4 / PU-5 of m2s72_peru.structural_rows on a (mutated) log, with the adapter's own construction of the
    grant and insert inputs (m2s72_peru_adapter.observe): the rows are the accepted functions, unchanged"""
    per, summ = P.attribute_feedback(log["events"], nproc)
    obs = []
    for k, n in sorted(node_id.items()):
        obs.append({"k": k, "node": n, "loaded_dl": False, "loaded_ul": False, "gptp": None, "dl": None,
                    "mac": {"grants": [(t, l, b) for t, d, nn, l, b in grants if d == "DL" and nn == n]},
                    "harq": {"inserts": per.get(n, {"inserts": 0})["inserts"]}})
    totals = {"dl_grant_bytes": sum(b for t, d, n, l, b in grants if d == "DL") + totals_add,
              "harq_inserts": sum(1 for e in log["events"] if e[0] == "ins")}
    rows = [r for r in P.structural_rows(obs, sorted(node_id), summ, totals) if r[0] in ("PU-4", "PU-5")]
    return rows, summ


def _ctl_log(base):
    lg = dict(base)
    lg["events"] = list(base["events"])
    lg["ins_pid"] = list(base["ins_pid"])
    lg["extract"] = list(base["extract"])
    lg["ue_rx"] = {k: list(v) for k, v in base["ue_rx"].items()}
    lg["ue_fb"] = {k: list(v) for k, v in base["ue_fb"].items()}
    return lg


def harq_controls(log, nproc, node_id, grants):
    """the H-ARQ / XA controls; returns [(name, ok, observed, declared)]"""
    out = []
    rows0, rep0, trace0 = H.crossvalidate(log, nproc, node_id=node_id, grants=grants)
    st0 = _status(rows0)
    pu0, summ0 = _pu45(log, nproc, node_id, grants)
    pst0 = _status(pu0)
    nodes = sorted(node_id.values())
    n0, n1 = nodes[0], nodes[1] if len(nodes) > 1 else None
    tr = H.truth(log, node_id)
    final_cls = {i: cls for i, n, cls in trace0}
    # a clean UE-0 PDU: inserted for n0, its (only) feedback attributed A-1a, no retransmission
    fb_of = {}
    _d, lines, _c, _p = H.match_feedback(log, H.truth(log, node_id), trace0)
    for i, own, x, grp in lines:
        if x is not None:
            fb_of[x["pid"]] = (i, x)
    ins_idx = [i for i, e in enumerate(log["events"]) if e[0] == "ins"]
    pick = None
    for j, i in enumerate(ins_idx):
        e = log["events"][i]
        pid = log["ins_pid"][j]
        f = fb_of.get(pid)
        if e[2] == n0 and f and final_cls.get(f[0]) == "a1a" and not f[1]["rtx_chain"] and pid in tr["rx_first"]:
            pick = (j, i, pid)
            break

    def run(lg, gr=grants, add=0):
        rows, rep, _ = H.crossvalidate(lg, nproc, node_id=node_id, grants=gr)
        pr, summ = _pu45(lg, nproc, node_id, gr, add)
        return _status(rows), _status(pr), summ, rep

    st, pst, summ, _ = run(log)
    out.append(("PC-n2-unmodified: every XA / PU-4 / PU-5 status reproduced", st == st0 and pst == pst0,
                f"XA {sorted(st.items())}; PU {sorted(pst.items())}", "identical to the baseline evaluation"))
    if pick is None or n1 is None:
        out.append(("NC-n2-* (H-ARQ)", False, "no clean A-1a UE-0 PDU or no second UE in this run",
                    "a clean A-1a PDU of UE 0 and two UEs"))
        return out, st0, pst0, summ0, rep0
    j, i, pid = pick
    # cross-UE misattribution of one PDU (insert and, consistently, its feedback)
    lg = _ctl_log(log)
    e = lg["events"][i]
    lg["events"][i] = ("ins", e[1], n1, e[3], e[4])
    st, pst, summ, rep = run(lg)
    ok = st[("XA-1", "run")] == "FAIL" and st[("XA-3", "run")] == "FAIL" and pst[("PU-5", "run")] == pst0[("PU-5", "run")]
    out.append(("NC-n2-swap: one UE-0 PDU logged for UE 1's node (consistent cross-UE misattribution)", ok,
                f"XA-1 {st[('XA-1', 'run')]}, XA-3 {st[('XA-3', 'run')]} ({rep['agreement']}), PU-4 {pst[('PU-4', 'run')]}, "
                f"PU-5 {pst[('PU-5', 'run')]}", "XA-1 FAIL, XA-3 FAIL; PU-5 unchanged (sums cannot see it)"))
    # orphan feedback: the gNB insert line removed
    lg = _ctl_log(log)
    del lg["events"][i]
    del lg["ins_pid"][j]
    st, pst, summ, _ = run(lg)
    ok = (summ["orphan"] > summ0["orphan"] and pst[("PU-4", "run")] == "FAIL" and st[("XA-1", "run")] == "FAIL"
          and st[("XA-4", "run")] == "FAIL")
    out.append(("NC-n2-orphan: the gNB insert line of one PDU removed", ok,
                f"orphan {summ0['orphan']} -> {summ['orphan']}, PU-4 {pst[('PU-4', 'run')]}, XA-1 {st[('XA-1', 'run')]}, "
                f"XA-4 {st[('XA-4', 'run')]}", "orphan + >= 1, PU-4 FAIL, XA-1 FAIL, XA-4 FAIL (orphan UNEXPLAINED)"))
    # duplicate insert
    lg = _ctl_log(log)
    lg["events"].insert(i + 1, lg["events"][i])
    lg["ins_pid"].insert(j + 1, pid)
    st, pst, summ, _ = run(lg)
    ok = (summ["reinsert"] > summ0["reinsert"] and pst[("PU-4", "run")] == "FAIL" and st[("XA-1", "run")] == "FAIL"
          and st[("XA-4", "run")] == "FAIL")
    out.append(("NC-n2-dup: one gNB insert line duplicated", ok,
                f"re-insert {summ0['reinsert']} -> {summ['reinsert']}, PU-4 {pst[('PU-4', 'run')]}, XA-1 {st[('XA-1', 'run')]}, "
                f"XA-4 {st[('XA-4', 'run')]}", "re-insert + >= 1, PU-4 FAIL, XA-1 FAIL, XA-4 FAIL (re-insert UNEXPLAINED)"))
    # inconsistent totals
    st, pst, summ, _ = run(log, add=1)
    ok = pst0[("PU-5", "run")] == "PASS" and pst[("PU-5", "run")] == "FAIL"
    out.append(("NC-n2-totals: run DL grant total + 1 byte", ok, f"PU-5 {pst0[('PU-5', 'run')]} -> {pst[('PU-5', 'run')]}",
                "PU-5 PASS -> FAIL"))
    # UE-side evidence: one UE-1 feedback removed; one UE-1 reception relabelled as UE 0
    k1 = next(k for k, n in node_id.items() if n == n1)
    k0 = next(k for k, n in node_id.items() if n == n0)
    if log["ue_fb"].get(k1) and log["ue_rx"].get(k1):
        lg = _ctl_log(log)
        lg["ue_fb"][k1] = lg["ue_fb"][k1][1:]
        st, _, _, _ = run(lg)
        out.append(("NC-n2-uefb: UE 1's first sent feedback removed", st[("XA-2", "run")] == "FAIL",
                    f"XA-2 {st[('XA-2', 'run')]}", "XA-2 FAIL"))
        lg = _ctl_log(log)
        x = lg["ue_rx"][k1].pop(0)
        lg["ue_rx"].setdefault(k0, []).append(x)
        lg["ue_rx"][k0].sort()
        st, _, _, _ = run(lg)
        out.append(("NC-n2-uerx: UE 1's first reception relabelled as UE 0's", st[("XA-1", "run")] == "FAIL",
                    f"XA-1 {st[('XA-1', 'run')]}", "XA-1 FAIL"))
    else:
        out.append(("NC-n2-uefb / NC-n2-uerx", False, f"UE {k1} has no H-ARQ RX lines", "UE-side lines of UE 1"))
    # timing: the gNB feedback line of the clean PDU moved one TTI later
    lg = _ctl_log(log)
    fi = fb_of[pid][0]
    e = lg["events"][fi]
    lg["events"][fi] = ("fb", e[1] + H.MS, e[2], e[3], e[4])
    st, _, _, _ = run(lg)
    out.append(("NC-n2-shift: one gNB feedback line one TTI late", st[("XA-2", "run")] == "FAIL",
                f"XA-2 {st[('XA-2', 'run')]}", "XA-2 FAIL"))
    # grants: UE 1's DL grants removed in the TTI of its first insert
    first1 = next((e[1] // H.MS for e in log["events"] if e[0] == "ins" and e[2] == n1), None)
    if first1 is not None:
        gr = [g for g in grants if not (g[1] == "DL" and g[2] == n1 and g[0] // H.MS == first1)]
        st, _, _, _ = run(log, gr=gr)
        out.append(("NC-n2-grant: UE 1's DL grants removed in the TTI of its first insert", st[("XA-5", "run")] == "FAIL",
                    f"XA-5 {st[('XA-5', 'run')]} ({len(grants) - len(gr)} grant lines removed)", "XA-5 FAIL"))
    return out, st0, pst0, summ0, rep0


def perue_controls(runs, cfg, opt, dl, ul):
    """per-UE Q8 / AV / PU controls on the run's real per-UE records (one evaluation, mutations in memory)"""
    _argv = sys.argv
    sys.argv = [_argv[0]]
    import check_m2s72_s5n as N
    sys.argv = _argv
    import m2s72_maclog as ML
    import m2s72_peru_adapter as A
    E = N.E
    out = []
    start = len(N.rows)
    ev, aopt, base, n = N.evaluation(runs, cfg, opt, full=False)
    del N.rows[start:]
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    loaded = {k: (k in dl, k in ul) for k in range(n)}
    obs, totals, summ = A.observe(ev, mlp, aopt, loaded, nproc=_nproc(cfg))
    del N.rows[start:]
    mlog = ML.MacLog(mlp)

    def q8row(k, mut=None):
        s = len(E.rows)
        q = E.Q8(ev, mlog, aopt, mut=mut, k=k, attr="exclusion")
        E.q8_rows(f"{cfg}-0 UE {k}", q)
        r = [x for x in E.rows[s:] if x[0] == "Q8"]
        del E.rows[s:]
        return q, r[0] if r else None

    base_rows = {k: q8row(k)[1] for k in range(n)}
    for k in range(n):
        q, _ = q8row(k)
        dlv = sorted(key for key, x in q.fate.items() if x[0] == "delivered" and key[0] == E.SYNC and key in q.sdu_of)
        if not dlv:
            out.append((f"NC-n2-q8-deliv UE {k}", False, "no delivered Sync of this UE", "a delivered Sync"))
            continue
        key = dlv[len(dlv) // 2]
        sdu = q.sdu_of[key]
        deliv = next(m_ for m_ in q.matched if (m_[0], m_[1]) == sdu)
        t_d, sz = deliv[3], deliv[1]
        removed = None
        for mod, e in mlog.rlc_rx.items():                 # the UE RLC log loses the delivery too (E0 rule), UE k only
            if f".ue[{k}]." in mod and (t_d, sz) in e["deliv"]:
                removed = (mod, e["deliv"].index((t_d, sz)))
                e["deliv"].remove((t_d, sz))
                break
        try:
            _, rk = q8row(k, mut={"drop_deliv": ((t_d, sz), key)})
            others = {j: q8row(j)[1] for j in range(n) if j != k}
        finally:
            if removed is not None:
                mlog.rlc_rx[removed[0]]["deliv"].insert(removed[1], (t_d, sz))
        ok = rk is not None and rk[2] == "FAIL" and all(others[j] == base_rows[j] for j in others)
        out.append((f"NC-n2-q8-deliv UE {k}: one delivered Sync of UE {k} loses its delivery evidence", ok,
                    f"Q8 UE {k} {rk[2] if rk else None}; other UEs' Q8 rows identical: {all(others[j] == base_rows[j] for j in others)}",
                    f"Q8 UE {k} FAIL; every other UE's Q8 row unchanged (status and detail)"))
    v0 = _status(A.validate(obs, totals, summ, list(range(n))))

    def val(o2):
        return _status(A.validate(o2, totals, summ, list(range(n))))

    for k in range(n):
        o2 = copy.deepcopy(obs)
        o2[k]["loaded_dl"] = not o2[k]["loaded_dl"]
        v = val(o2)
        other = all(v[("AV-2", f"UE {j}")] == v0[("AV-2", f"UE {j}")] for j in range(n) if j != k)
        out.append((f"NC-n2-av2 UE {k}: declared DL load of UE {k} flipped", v[("AV-2", f"UE {k}")] == "FAIL" and other,
                    f"AV-2 UE {k} {v[('AV-2', f'UE {k}')]}; other UEs unchanged {other}", f"AV-2 UE {k} FAIL, others unchanged"))
    o2 = copy.deepcopy(obs)
    o2[1]["node"] = o2[0]["node"]
    v = val(o2)
    out.append(("NC-n2-pu1: UE 1 given UE 0's node id", v[("PU-1", "run")] == "FAIL", f"PU-1 {v[('PU-1', 'run')]}", "PU-1 FAIL"))
    for k in range(n):
        o2 = copy.deepcopy(obs)
        if o2[k]["gptp"] and o2[k]["gptp"]["cohort"]:
            o2[k]["gptp"]["cohort"][0]["fate"] = "UNEXPLAINED"
            v = val(o2)
            other = all(v[("PU-2", f"UE {j}")] == v0[("PU-2", f"UE {j}")] for j in range(n) if j != k)
            out.append((f"NC-n2-pu2 UE {k}: one cohort Sync of UE {k} UNEXPLAINED", v[("PU-2", f"UE {k}")] == "FAIL" and other,
                        f"PU-2 UE {k} {v[('PU-2', f'UE {k}')]}; other UEs unchanged {other}", f"PU-2 UE {k} FAIL, others unchanged"))
    kl = next((k for k in range(n) if obs[k]["loaded_dl"] and obs[k]["dl"] and obs[k]["dl"].get("accounting")), None)
    if kl is not None:
        o2 = copy.deepcopy(obs)
        o2[kl]["dl"]["accounting"]["unexplained"] += 1
        v = val(o2)
        other = all(v[("PU-3", f"UE {j}")] == v0[("PU-3", f"UE {j}")] for j in range(n) if j != kl)
        out.append((f"NC-n2-pu3 UE {kl}: one load SDU of UE {kl} unexplained", v[("PU-3", f"UE {kl}")] == "FAIL" and other,
                    f"PU-3 UE {kl} {v[('PU-3', f'UE {kl}')]}; other UEs unchanged {other}", f"PU-3 UE {kl} FAIL, others unchanged"))
    return out, run_node_ids(ev)


def run_node_ids(ev):
    return dict(ev.run.node_id)


def controls_n2(runs, cfg, opt, dl, ul, recdir):
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    log = H.read_log(mlp)
    pq, node_id = perue_controls(runs, cfg, opt, dl, ul)
    hq, st0, pst0, summ0, rep0 = harq_controls(log, _nproc(cfg), node_id, _grants(mlp))
    out = hq + pq
    good = all(x[1] for x in out)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"controls-n2-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a N = 2 increment: multi-UE controls on {cfg} (in memory; raw outputs read only)\n")
        fh.write(f"baseline: XA {sorted(st0.items())}; PU {sorted(pst0.items())}; A-1 {summ0}\n\n")
        for nm, ok, obs_, exp in out:
            fh.write(f"{'PASS' if ok else 'FAIL'} | {nm} | observed {obs_} | declared {exp}\n")
        fh.write(f"\ncontrols-n2 on {cfg}: {sum(1 for x in out if x[1])} / {len(out)} as declared\n")
    pj = os.path.join(recdir, f"controls-n2-{cfg}.json")
    with open(pj, "w") as fh:
        json.dump(_clean({"config": cfg, "controls": [{"name": a, "ok": b, "observed": c, "declared": d} for a, b, c, d in out],
                          "as_declared": sum(1 for x in out if x[1]), "total": len(out)}), fh, indent=1, sort_keys=True)
    _durable([p, pj])
    print(open(p).read().rstrip())
    return 0 if good else 1


# ------------------------------------------------------------------------------------------------ verdict --------
ROW = re.compile(r"^  (PASS|FAIL|NOT EVALUATED|NOT APPLICABLE)\s*\| ([^|]+?) \| ([^|]+?) \| (.*)$")


def parse_rows(path):
    rows = []
    if not os.path.exists(path):
        return None
    for line in open(path):
        m = ROW.match(line.rstrip("\n"))
        if m:
            rows.append((m.group(2), m.group(3), m.group(1), m.group(4)))
    return rows


def verdict(recdir, cfg, n=2):
    """protocol §6: N2-A0 .. N2-A8. Every criterion cites the records it reads; nothing is re-evaluated here"""
    C = []

    def crit(cid, what, status, detail, required=True):
        C.append((cid, what, status, detail, required))

    def st(rows, row, subj):
        if rows is None:
            return None
        return next((r[2] for r in rows if r[0] == row and r[1] == subj), None)

    runs_tsv = os.path.join(recdir, "runs.tsv")
    steps = open(os.path.join(recdir, "steps.txt")).read() if os.path.exists(os.path.join(recdir, "steps.txt")) else ""
    tsv = open(runs_tsv).read().splitlines()[1:] if os.path.exists(runs_tsv) else []
    row = next((x.split("\t") for x in tsv if x.startswith(cfg + "\t")), None)
    ok0 = row is not None and row[2] == "OK" and "manifest verified" in steps
    crit("N2-A0", "run outcome OK, manifest re-verified", "ACCEPT" if ok0 else ("REJECT" if row else NE),
         f"runs.tsv {row[2:6] if row else None}; manifest verified in steps: {'manifest verified' in steps}")
    adp = parse_rows(os.path.join(recdir, f"adapter-validate-{cfg}.txt"))
    adj = os.path.join(recdir, f"adapter-validate-{cfg}.json")
    adj = json.load(open(adj)) if os.path.exists(adj) else None
    xaj = os.path.join(recdir, f"xa-{cfg}.json")
    xaj = json.load(open(xaj)) if os.path.exists(xaj) else None
    xrows = [tuple(r) for r in xaj["rows"]] if xaj else None
    chk = parse_rows(os.path.join(recdir, f"{cfg}.check.txt"))
    dg = os.path.join(recdir, f"{cfg}.digest.json")
    dg = json.load(open(dg)) if os.path.exists(dg) else None
    ctl = os.path.join(recdir, f"controls-n2-{cfg}.json")
    ctl = json.load(open(ctl)) if os.path.exists(ctl) else None
    ues = [f"UE {k}" for k in range(n)]

    def need(*vals):
        return NE if any(v is None for v in vals) else None

    # A1 identities
    s = [st(adp, "PU-1", "run"), st(xrows, "XA-0", "run")]
    crit("N2-A1", "two distinct UE identities / NR MAC node ids (PU-1; XA-0 from PDU ids = run node ids)",
         need(*s) or ("ACCEPT" if s == ["PASS", "PASS"] else "REJECT"), f"PU-1 {s[0]}, XA-0 {s[1]}")
    # A2 accounting (one0: UE 0 loaded DL / UL, UE 1 unloaded)
    s = {f"PU-3 {u}": st(adp, "PU-3", u) for u in ues}
    s.update({f"{r} {u}": st(adp, r, u) for r in ("AV-2", "AV-3") for u in ues})
    exp = {f"PU-3 {u}": ("PASS" if u == "UE 0" else "NOT APPLICABLE") for u in ues}
    exp.update({f"{r} {u}": "PASS" for r in ("AV-2", "AV-3") for u in ues})
    crit("N2-A2", "per-UE DL / UL load accounting and roles (PU-3, AV-2, AV-3)", need(*s.values()) or
         ("ACCEPT" if s == exp else "REJECT"), "; ".join(f"{k} {v}" for k, v in s.items()))
    # A3 gPTP per UE
    q8 = {u: next((r[2] for r in (adp or []) if r[0] == "Q8" and r[1].endswith(u)), None) for u in ues}
    s = {f"{r} {u}": st(adp, r, u) for r in ("PU-2", "AV-1") for u in ues}
    s.update({f"Q8 {u}": q8[u] for u in ues})
    cov = {}
    if adj:
        for m in adj.get("per_ue", []):
            f = m.get("gptp_fates") or {}
            cov[f"UE {m['k']}"] = {x: f.get(x, 0) for x in ("used", "delivered", "lost", "censored", "invalid", "late")}
    crit("N2-A3", "per-UE gPTP Sync / Follow_Up fates (PU-2, AV-1, per-UE Q8 with the exclusion attribution)",
         need(*s.values()) or ("ACCEPT" if all(v == "PASS" for v in s.values()) else "REJECT"),
         "; ".join(f"{k} {v}" for k, v in s.items()) + f"; fate coverage {cov} (a fate class with 0 is NOT EXERCISED, not claimed)")
    # A4 attribution vs truth
    s = {r: st(xrows, r, "run") for r in ("XA-pre", "XA-1", "XA-2", "XA-3")}
    a1b = (xaj or {}).get("report", {}).get("agreement", {}).get("agree", {}).get("a1b", 0) if xaj else None
    crit("N2-A4", "DL inserts and feedback attribution against the UE-side truth (XA-1, XA-2, XA-3)",
         need(*s.values()) or ("ACCEPT" if all(v == "PASS" for v in s.values()) else "REJECT"),
         "; ".join(f"{k} {v}" for k, v in s.items()) + f"; A-1b attributions checked: {a1b}"
         + (" (A-1b NOT EXERCISED: not claimed)" if a1b == 0 else ""))
    # A5 conservation
    s = {"PU-5": st(adp, "PU-5", "run"), "XA-5": st(xrows, "XA-5", "run"), "XA-6": st(xrows, "XA-6", "run")}
    x6 = s["XA-6"] == "PASS" or (s["XA-6"] == NE and xaj and not _exact(xaj["report"]["a1_summary"]))
    crit("N2-A5", "conservation and per-UE consistency (PU-5; XA-5 grants <-> inserts; XA-6 aggregates)",
         need(*s.values()) or ("ACCEPT" if s["PU-5"] == "PASS" and s["XA-5"] == "PASS" and x6 else "REJECT"),
         "; ".join(f"{k} {v}" for k, v in s.items()))
    # A6 classification of ambiguous / overlapping feedback, and the two tools agree on A-1
    s4 = st(xrows, "XA-4", "run")
    same = None
    if xaj and adj and adj.get("harq_attribution"):
        a, b = xaj["report"]["a1_summary"], adj["harq_attribution"]
        same = all(a.get(k) == b.get(k) for k in ("a1a", "a1b", "ambiguous", "orphan", "reinsert", "d_star_ps"))
    crit("N2-A6", "classification of ambiguous / overlapping feedback (XA-4); A-1 summary identical in adapter and XA",
         need(s4, same) or ("ACCEPT" if s4 == "PASS" and same else "REJECT"),
         f"XA-4 {s4}; same A-1 summary {same}; census {(xaj or {}).get('report', {}).get('overlap_census')}")
    crit("N2-A7", "runtime RNG-stream isolation", NE, "not evaluated by design: protocol §5 (baseline mapping; static "
         "resolution only; runtime evidence needs the RngProbe paired runs of §5.3)", required=False)
    # A8 checkers on multi-UE output
    gf = dg["correctness"]["gate_failures"] if dg else None
    ne = dg["correctness"]["per_ue_not_evaluated"] if dg else None
    rr = {r: st(chk, r, f"{cfg}-0") for r in ("MG-1", "Q8-v", "SG-403")}
    cok = ctl is not None and ctl["as_declared"] == ctl["total"] and ctl["total"] > 0
    ok8 = gf is not None and set(gf) <= {"PU-4"} and ne == [] and all(v == "PASS" for v in rr.values()) and cok
    crit("N2-A8", "accepted rows at N = 2, MG-1 / Q8-v / SG-403, and controls-n2 as declared",
         need(gf, chk, ctl) or ("ACCEPT" if ok8 else "REJECT"),
         f"per-run gate failures {gf} (only PU-4 is admissible, see N2-A6); per-UE NE {ne}; {rr}; controls-n2 "
         f"{ctl['as_declared'] if ctl else None} / {ctl['total'] if ctl else None}")
    req = [c for c in C if c[4]]
    pu4 = st(adp, "PU-4", "run")
    if any(c[2] == "REJECT" for c in req):
        overall, rc = "NOT VALIDATED", 1
    elif any(c[2] != "ACCEPT" for c in req):
        overall, rc = "INCOMPLETE", 4
    elif pu4 == "PASS":
        overall, rc = "VALIDATED", 0
    else:
        overall, rc = ("VALIDATED WITH A-1 LIMITATION: PU-4 FAIL retained (A-1 cannot attribute every feedback line; "
                       "every unresolved line is explained by XA-4); per-UE H-ARQ occupancy NOT EVALUATED under A-1"), 3
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"smoke-n2-verdict-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a N = 2 smoke verdict on {cfg} (protocol §6; the per-run verdicts are quoted, never changed)\n\n")
        for cid, what, s_, d, r in C:
            fh.write(f"  {s_:<13} | {cid} | {what}{'' if r else ' (not required)'} | {d}\n")
        fh.write(f"\nPU-4 as recorded by adapter-validate: {pu4}\n")
        fh.write(f"per-run verdict as recorded by check_m2s72_s5n.py run: {_verdict_line(recdir, cfg)}\n")
        fh.write(f"\nN = 2 smoke: {overall}\n")
    pj = os.path.join(recdir, f"smoke-n2-verdict-{cfg}.json")
    with open(pj, "w") as fh:
        json.dump({"config": cfg, "criteria": [list(c) for c in C], "pu4": pu4, "overall": overall}, fh, indent=1)
    _durable([p, pj])
    print(open(p).read().rstrip())
    return rc


def _exact(s):
    return s["ambiguous"] == 0 and s["orphan"] == 0 and s["reinsert"] == 0


def _verdict_line(recdir, cfg):
    p = os.path.join(recdir, f"{cfg}.check.txt")
    if not os.path.exists(p):
        return None
    return next((x.strip() for x in open(p) if x.startswith("per-run verdict:")), None)


def ue_list(s):
    return [] if s == "none" else [int(x) for x in s.split(",")]


def main(argv):
    try:
        if len(argv) == 5 and argv[1] == "xa":
            return xa(argv[2], argv[3], argv[4])
        if len(argv) == 8 and argv[1] == "controls-n2":
            return controls_n2(argv[2], argv[3], argv[4], ue_list(argv[5]), ue_list(argv[6]), argv[7])
        if len(argv) == 4 and argv[1] == "verdict":
            return verdict(argv[2], argv[3])
    except Exception as ex:                     # an evaluation that cannot complete is never a PASS
        import traceback
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
