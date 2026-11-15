#!/usr/bin/env python3
"""M2-S7.2a Stage 5 on Simu5G 1.8.1, increment S5-1: per-run evaluation of E0v runs with the accepted E0 row functions
(check_m2s72_e0.py, unchanged) plus the version-appropriate rows of plan rev. 1 (G-3) and the RD-1 measurements.
Protocol and predictions: results/M2-S7.2a-e0v-protocol.md (committed before any run).

    check_m2s72_s5v.py run <runs> <cfg> <records dir>      one run: <cfg>.check.txt, <cfg>.digest.json; exit 0 PASS,
                                                           1 FAIL (a gate row failed), 2 evaluation error / refused
    check_m2s72_s5v.py nonpert <runs> <cfg> <twin> <records dir>
                                                           MAC-log non-perturbation (E0's comparator) + its canary
    check_m2s72_s5v.py controls-q8 <runs> <cfg> <records dir>
                                                           E0 r2 Q8 controls on <cfg> (as declared) + the new-row controls
    check_m2s72_s5v.py controls-sg <runs> <cfg> <records dir>
                                                           SG-403 classification controls SC-1..6, RC-1..3 on a Q-d run
    check_m2s72_s5v.py quick <runs> <cfg>                  E0's escalation proxy (unchanged)

Rows added to the E0 rows (each NOT a replacement; the E0 rows run unchanged):
  Q8-v   (G-3, F1 / F6) no gNB MAC log line of a H-ARQ-process MAC PDU deletion (the 1.8.0 text "no available process
         for this MAC PDU"; on 1.8.1 that branch throws instead), no Q8 fate attributed to such a deletion, and no
         SIM-ABORT text in the run log
  SG-403 (G-3) the E2 protocol rev. 2.1 classification of every backlogged DL TTI; regression invariant on 1.8.1:
         0 CONFIRMED-403 and 0 UNEXPLAINED (a non-zero count fails; the run is kept and the batch stops)
  MG-1   (G-3) MAC-log grammar: 0 UNCLASSIFIED loss-like lines (the parser's fail-closed rule for the gNB MAC / RLC
         lines; the same rule applied here to the UE MAC lines, whose only classified 1.8.1 event is "the grant is not
         used") and 0 lines of a text that Simu5G 1.8.1 can no longer emit; the census of every normalised line template is recorded in the digest
         (the 1.8.1 grammar is frozen from the first reviewed run, not assumed)
RD-1 measurements (reported, never gates): DL H-ARQ busy processes per TTI start (insert -> feedback), feedback delay,
candidate / ineligible / granted TTIs of the UE's DL connections, granted bytes, UE "grant is not used" events
(UE MAC log), queue growth (E0 backlog metrics), achieved service (E0 metrics).

Option analysis mapping: Q-0p has Q-0's DRB mapping (m2s71_lib.OPTIONS) and the same C-a clocks, so its runs are
evaluated with the Q-0 mapping; Q-de has Q-d's mapping (it differs from Q-d only in the gPTP DRB's profile, D-1), so
its runs are evaluated with the Q-d mapping. Neither the scheduler nor a DRB profile is an input of any row (rows observe). Checked in test_m2s72s5.py.
Scope of S5-1: N = 1 configurations only (E0v core, twins, E0v-p, E0v-H5). E0v-N (N > 1) is refused (exit 2): the
per-UE N > 1 evaluation is the next increment (G-2).
"""
import gzip
import json
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_e0 as E  # noqa: E402
import diag_m2s72_dl_active as D  # noqa: E402
sys.argv = _argv
import m2s71_lib as L  # noqa: E402
import m2s72_maclog as ML  # noqa: E402
import m2s72s5_lib as LIB  # noqa: E402

rows = E.rows
S, MS = E.S, E.MS
NA, NE = E.NA, E.NE
ANALYSIS_OPT = {"q0": "q0", "q0p": "q0", "qdu": "qdu", "qde": "qdu"}   # Q-de: Q-d's DRB mapping (D-1)
# declared loss-free before any run (protocol §4): HARQ16 at DL factor 1, every option
LOSS_FREE_V = {"M2S72-E0v-q0-f1", "M2S72-E0v-qdu-f1", "M2S72-E0v-q0p-f1", "M2S72-E0v-qde-f1"}
REMOVED_181 = ("no available process for this MAC PDU",)        # emitted by 1.8.0 only (LteMacEnb.cc:585, LteMacUe.cc)
UE_GRANT_UNUSED = re.compile(r"no free H-ARQ process for the grant on carrier \[[^\]]*\], the grant is not used")
NAME = re.compile(r"M2S72-(E0v|E0vNL|E0vH5|E0vH5NL|E0)-(q0p|q0|qdu|qde)-f(\d+)$")
NAME_N = re.compile(r"M2S72-E0vN(H5)?-(q0p|q0|qdu|qde)-(one0|sym)-n(\d+)-f(\w+)$")


def parse_name(cfg):
    """(kind, option, HARQ16, DL factor, N); kind: E0v | E0vNL | E0vH5 | E0vH5NL | E0 (the 1.8.0 E0 names, read-only
    validation of these rows on accepted outputs) | E0vN"""
    m = NAME.fullmatch(cfg)
    if m:
        kind, o, f = m.group(1), m.group(2), int(m.group(3))
        if kind == "E0" and o in ("q0p", "qde"):
            raise ValueError(f"{cfg}: no {o} E0 config")
        return kind, o, not kind.startswith("E0vH5"), f, 1
    m = NAME_N.fullmatch(cfg)
    if m:
        return "E0vN", m.group(2), m.group(1) is None, m.group(5), int(m.group(4))
    raise ValueError(f"{cfg}: not an E0v / E0 configuration name")


# ------------------------------------------------------------------------------------------ G-3 rows --------------
def q8v_row(name, mlog, q, log_text):
    probs = []
    if mlog is None:
        rows.append(("Q8-v", name, NE, "no MAC log in this run"))
        return False
    d = mlog.deletions()
    if d:
        probs.append(f"{len(d)} H-ARQ-process MAC PDU deletion lines (first at {d[0]['t'] / S:.6f} s)")
    att = [k for k, f in q.fate.items() if "HARQ-process MAC PDU deletion" in str(f[2:])]
    if att:
        probs.append(f"{len(att)} Q8 fates attributed to a H-ARQ-process deletion, first {att[0]}")
    ab = [what for p, what in LIB.SIM_ABORT if p.search(log_text)]
    if ab:
        probs.append(f"SIM-ABORT text in the run log: {ab}")
    ok = not probs
    rows.append(("Q8-v", name, "PASS" if ok else "FAIL",
                 "1.8.1: deletion lines 0, deletion fates 0, no abort text" if ok else "FAIL " + "; ".join(probs)))
    return ok


def sg403_row(name, runs, cfg, mut=None):
    res = D.analyse2(runs, cfg, mut)
    c, u = D.safeguard(res)
    ok = (c, u) == (0, 0)
    per = "; ".join(f"{r['node']}-{r['drb']}: backlogged {r['backlogged_ttis']}, served {r['served']}, cand-not-served "
                    f"{r['cand_not_served']}, confirmed {r['confirmed_403']}, unexplained {r['unexplained']}" for r in res)
    rows.append(("SG-403", name, "PASS" if ok else "FAIL", f"(confirmed, unexplained) = {(c, u)} (invariant (0, 0)); {per}"))
    return ok, res


TEMPLATE_NUM = re.compile(r"\d+(\.\d+)?(e-?\d+)?")


def grammar(path, gnb=f"{E.R.NET}.gnb1.cellularNic.mac"):
    """census of normalised line templates per observed module class, and the removed-text count"""
    census, removed, ue_unused = Counter(), Counter(), []
    busy, cur, at_start, peak, seen = set(), None, Counter(), Counter(), 0       # DL H-ARQ occupancy in LOG order
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|", 2)
            if len(p) < 3 or not p[0][:1].isdigit():
                continue
            mod, msg = p[1], p[2]
            if mod == gnb:
                tti = ML.t_ps(p[0]) // MS
                if tti != cur:
                    if cur is not None:
                        peak[cur_peak] += 1
                    cur, cur_peak = tti, len(busy)
                    at_start[len(busy)] += 1
                m = ML.R_INSERT.search(msg)
                if m:
                    busy.add(int(m.group(2)))
                    seen += 1
                    cur_peak = max(cur_peak, len(busy))
                else:
                    m = ML.R_FB.search(msg)
                    if m:
                        busy.discard(int(m.group(1)))
            cls = ("gnb-mac" if mod == gnb else "gnb-rlc-tx" if ".rlc-um-" in mod and mod.endswith(".tx")
                   else "ue-rlc-rx" if ".nrRlc-um-" in mod and mod.endswith(".rx") else "ue-mac" if mod.endswith(".nrMac") else "other")
            census[(cls, TEMPLATE_NUM.sub("N", msg.strip())[:160])] += 1
            for r in REMOVED_181:
                if r in msg:
                    removed[r] += 1
            if cls == "ue-mac" and UE_GRANT_UNUSED.search(msg):
                ue_unused.append((ML.t_ps(p[0]), mod))
            elif cls == "ue-mac" and ML.LOSSY.search(msg) and not any(b in msg for b in ML.KNOWN_BENIGN):
                removed["UE MAC loss-like line not classified: " + TEMPLATE_NUM.sub("N", msg.strip())[:100]] += 1
    if cur is not None:
        peak[cur_peak] += 1
    occ = {"logged_ttis": sum(at_start.values()), "inserts": seen,
           "busy_at_first_logged_line_of_tti_hist": {str(k): v for k, v in sorted(at_start.items())},
           "peak_busy_within_tti_hist": {str(k): v for k, v in sorted(peak.items())},
           "max_peak_busy": max(peak) if peak else None}
    return census, removed, ue_unused, occ


def mg1_row(name, mlog, removed):
    probs = []
    if mlog is None:
        rows.append(("MG-1", name, NE, "no MAC log"))
        return False
    if mlog.unclassified:
        probs.append(f"{len(mlog.unclassified)} UNCLASSIFIED loss-like lines, first {mlog.unclassified[0][2][:120]}")
    if sum(removed.values()):
        probs.append(f"removed-text or unclassified UE MAC loss-like lines: {dict(removed)}")
    ok = not probs
    rows.append(("MG-1", name, "PASS" if ok else "FAIL", "UNCLASSIFIED 0, removed-text lines 0" if ok else "FAIL " + "; ".join(probs)))
    return ok


# ---------------------------------------------------------------------------------- RD-1 measurements -------------
def harq_measure(mlog, node, nproc, T, cand, grants, ue_unused, ineligible):
    """DL H-ARQ feedback delay, eligibility and service of the UE's DL connections. N = 1: every DL process belongs
    to the one UE (as m2s72_maclog.max_busy). The time-sorted busy histogram here breaks same-time ties as insert
    before feedback; the authoritative occupancy is grammar()'s log-order count (dl_occupancy_log_order)."""
    ins = [(d["t"], d["proc"]) for d in mlog.pdus if d["proc"] is not None and d["node"] in (None, node)]
    fb = sorted((t, p) for t, p, _ in mlog.feedback)
    ev = sorted([(t, 0, p) for t, p in ins] + [(t, 1, p) for t, p in fb])
    busy, hist, i, open_t, delays = set(), Counter(), 0, {}, []
    for tti in range(int(T // MS)):
        t0 = tti * MS
        while i < len(ev) and ev[i][0] < t0:
            t, kind, p = ev[i]
            if kind == 0:
                busy.add(p)
                open_t[p] = t
            else:
                busy.discard(p)
                if p in open_t:
                    delays.append(t - open_t.pop(p))
            i += 1
        hist[len(busy)] += 1
    cons = sorted(k for k in set(grants) | {c for s in cand.values() for c in s} if k[0] == node)
    per = {}
    for c in cons:
        ct = {t for t, s in cand.items() if c in s}
        gt = {g[0] for g in grants.get(c, []) if g[1] > 0}
        per[f"{c[0]}-{c[1]}"] = {"candidate_ttis": len(ct), "granted_ttis": len(gt), "candidate_not_granted_ttis": len(ct - gt),
                                 "granted_bytes": sum(g[1] for g in grants.get(c, [])),
                                 "maxci_found_ineligible": ineligible.get(c, 0)}
    dd = sorted(delays)
    return {"harq_processes_configured": nproc, "dl_busy_at_tti_start_time_sorted_hist": {str(k): v for k, v in sorted(hist.items())},
            "dl_ttis_all_processes_busy": hist.get(nproc, 0),
            "harq_feedback_delay_ms": {"n": len(dd), "min": dd[0] / MS if dd else None, "median": dd[len(dd) // 2] / MS if dd else None,
                                       "max": dd[-1] / MS if dd else None},
            "dl_connections": per, "ue_grant_not_used_events": len(ue_unused),
            "ue_grant_not_used_first_s": [t / S for t, _ in ue_unused[:5]]}


def maxci_ineligible(path, node_filter=None):
    out = Counter()
    pat = re.compile(r"LteMaxCI::schedule connection " + D.R_CID + r" was found ineligible")
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            if "found ineligible" in line:
                m = pat.search(line)
                if m:
                    out[(int(m.group(1)), int(m.group(2)))] += 1
    return out


# ------------------------------------------------------------------------------------------------ one run ---------
def clean(x):
    """JSON-safe digest: dict keys as strings, +/-inf and NaN as strings, tuples / sets as lists"""
    if isinstance(x, dict):
        return {str(k): clean(v) for k, v in x.items()}
    if isinstance(x, (list, tuple, set)):
        return [clean(v) for v in (sorted(x, key=str) if isinstance(x, set) else x)]
    if isinstance(x, float) and (x != x or x in (float("inf"), float("-inf"))):
        return str(x)
    return x


def read_log(path):
    with gzip.open(path, "rt", errors="replace") as fh:
        return fh.read()


def run_one(runs, cfg, recdir):
    kind, o, h16, f, n = parse_name(cfg)
    if kind == "E0vN":
        print(f"{cfg}: REFUSED: N > 1 per-UE evaluation is not part of S5-1 (G-2)")
        return 2, None
    if kind in ("E0vNL", "E0vH5NL"):
        print(f"{cfg}: twin: evaluated only by 'nonpert' against its logged partner")
        return 2, None
    name = f"{cfg}-0"
    E.LOSS_FREE.update(LOSS_FREE_V)
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    start = len(rows)
    ev, q, m, fails = E.evaluate(runs, cfg, ANALYSIS_OPT[o], f, mlp)
    mlog = ML.MacLog(mlp) if os.path.exists(mlp) else None
    log_text = read_log(mlp) if os.path.exists(mlp) else ""
    q8v_row(name, mlog, q, log_text)
    sg_ok, sg = sg403_row(name, runs, cfg)
    census, removed, ue_unused, occ = grammar(mlp) if os.path.exists(mlp) else (Counter(), Counter(), [], None)
    mg1_row(name, mlog, removed)
    mine = rows[start:]
    gate_fail = sorted({r[0] for r in mine if r[2] == "FAIL" and r[0] not in E.INFO})
    T = ev.T
    cand, grants = D.dl_sched(mlp)
    meas = harq_measure(mlog, q.node, 16 if h16 else 5, T, cand, grants, ue_unused, maxci_ineligible(mlp)) if mlog else None
    if meas is not None:
        meas["dl_occupancy_log_order"] = occ          # the authoritative occupancy (same-time events in log order)
    m["option"] = o
    m["option_analysed_as"] = ANALYSIS_OPT[o]
    m["harq_processes"] = 16 if h16 else 5
    m["onset"] = E.onset(m)
    over = bool(m.get("load_drb1_sustained_growth")) and (m.get("dl_achieved_rlc_Mbps") or 0) < (m.get("dl_offered_rlc_Mbps") or 0)
    digest = {"config": cfg, "kind": kind, "option": o, "harq16": h16, "dl_factor": f, "numUe": n,
              "correctness": {"gate_failures": gate_fail, "rows": len(mine),
                              "row_status": dict(Counter(r[2] for r in mine))},
              "performance": {k: v for k, v in m.items() if k != "onset"} | {"onset": m["onset"]},
              "rd1_harq_service": meas, "sg403": [{k: v for k, v in r.items() if k not in ("first_confirmed", "first_unexplained")} for r in sg],
              "mac_grammar_census": [[c, t, v] for (c, t), v in sorted(census.items())],
              "overloaded_by_definition": over,
              "retain": (["gate failure"] if gate_fail else [])}
    os.makedirs(recdir, exist_ok=True)
    with open(os.path.join(recdir, f"{cfg}.check.txt"), "w") as fh:
        fh.write(f"M2-S7.2a S5-1 per-run check of {cfg} (E0 rows unchanged + Q8-v, SG-403, MG-1)\n\n")
        fh.write("CORRECTNESS (gates)\n")
        for r in mine:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {r[3]}\n")
        fh.write(f"\nper-run verdict: {'PASS' if not gate_fail else 'FAIL ' + ' '.join(gate_fail)}\n")
        fh.write("\nPERFORMANCE (measurements, never gates): see the digest\n")
    with open(os.path.join(recdir, f"{cfg}.digest.json"), "w") as fh:
        json.dump(clean(digest), fh, indent=1, sort_keys=True)
    LIB.durable([os.path.join(recdir, f"{cfg}.check.txt"), os.path.join(recdir, f"{cfg}.digest.json")])
    print(f"{cfg}: {'PASS' if not gate_fail else 'FAIL ' + ' '.join(gate_fail)} ({len(mine)} rows); overloaded {over}")
    return (0 if not gate_fail else 1), digest


# ------------------------------------------------------------------------------------------------ controls --------
PRED_Q8 = dict(E.PRED)
PRED_Q8.pop("PC-q8-lost")                       # superseded by PC-q8-lost-r2 (E0 r2), reported there


def controls_q8(runs, cfg, recdir):
    """the E0 r2 Q8 controls on <cfg> (predictions unchanged: E.PRED, E.PRED_R2), plus the new-row controls
    NC-q8v-del (an injected deletion must fail Q8-v) and NC-mg-removed / NC-mg-unknown (MG-1)"""
    kind, o, h16, f, n = parse_name(cfg)
    aopt = ANALYSIS_OPT[o]
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    out = []
    start = len(rows)
    ev, q, _, _ = E.evaluate(runs, cfg, aopt, f, mlp, gates=False)
    del rows[start:]
    dl = sorted(k for k, x in q.fate.items() if x[0] == "delivered" and k[0] == E.SYNC and k in q.sdu_of)
    k = dl[len(dl) // 2]
    sdu = q.sdu_of[k]
    tl = {(a, s): t for a, s, t in q.done}[sdu]
    deliv = next(m_ for m_ in q.matched if (m_[0], m_[1]) == sdu)
    own = E.pdu_owner(q.sdus_h, q.pdus_h)
    idx = {(a, s): i for i, (a, s, _) in enumerate(q.done)}[sdu]
    pdu = next(q.pdus_h[j] for j, o_ in enumerate(own) if o_ == idx)
    rx = sorted(x for x in q.rxpdus if x[1] == pdu[1] and pdu[0] <= x[0] <= pdu[0] + E.G.AIR)
    muts = {"NC-q8-deliv": {"drop_deliv": ((deliv[3], deliv[1]), k)},
            "NC-q8-seg": {"seg": True},
            "NC-q8-noevid": {"drop_rxpdu": rx[0] if rx else None, "drop_deliv": ((deliv[3], deliv[1]), k)},
            "NC-maclog-del": {"fake_deletion": tl}}
    for nm, mut in muts.items():
        start = len(rows)
        E.evaluate(runs, cfg, aopt, f, mlp, mut=mut, gates=False)
        mine = rows[start:]
        del rows[start:]
        fails = {r[0] for r in mine if r[2] == "FAIL"}
        out.append((nm, fails == PRED_Q8[nm], sorted(fails), sorted(PRED_Q8[nm])))
    E.CTRL_CFG = (cfg, aopt, f)
    res, comp = E.controls_r2(runs)
    for nm, ok, fails, exp, _ in res:
        out.append((nm, ok, sorted(fails), sorted(exp)))
    # new rows
    mlog = ML.MacLog(mlp)
    log_text = read_log(mlp)
    start = len(rows)
    base_ok = q8v_row("ctl", mlog, q, log_text)
    mlog.pdus.append({"t": tl, "bytes": 0, "sdus": 1, "deleted": True, "proc": None, "node": None, "pid": None})
    del_ok = q8v_row("ctl", mlog, q, log_text)
    abort_ok = q8v_row("ctl", ML.MacLog(mlp), q, log_text + "\n<!> Error in module (x): LteMacEnb::macPduMake(): no free H-ARQ process for the MAC PDU to UE 2049, codeword 0\n")
    del rows[start:]
    out.append(("Q8-v unmodified", base_ok, [] if base_ok else ["Q8-v"], []))
    out.append(("NC-q8v-del (injected deletion line)", not del_ok, [] if del_ok else ["Q8-v"], ["Q8-v"]))
    out.append(("NC-q8v-abort (injected 1.8.1 abort text)", not abort_ok, [] if abort_ok else ["Q8-v"], ["Q8-v"]))
    start = len(rows)
    ok0 = mg1_row("ctl", ML.MacLog(mlp), Counter())
    m2 = ML.MacLog(mlp)
    m2.unclassified.append((0, "gnb", "synthetic: packet discarded for an unknown reason"))
    ok1 = mg1_row("ctl", m2, Counter())
    ok2 = mg1_row("ctl", ML.MacLog(mlp), Counter({REMOVED_181[0]: 1}))
    del rows[start:]
    out.append(("MG-1 unmodified", ok0, [] if ok0 else ["MG-1"], []))
    out.append(("NC-mg-unknown (injected unclassified loss-like line)", not ok1, [] if ok1 else ["MG-1"], ["MG-1"]))
    out.append(("NC-mg-removed (injected 1.8.0-only text)", not ok2, [] if ok2 else ["MG-1"], ["MG-1"]))
    good = all(x[1] for x in out)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"controls-q8-{cfg}.txt")
    with open(p, "w") as fh:
        for nm, ok, fails, exp in out:
            fh.write(f"{'PASS' if ok else 'FAIL'} | {nm} | failing {fails} | predicted {exp}\n")
        fh.write(f"controls on {cfg}: {sum(1 for x in out if x[1])} / {len(out)} as declared\n")
    LIB.durable([p])
    print(open(p).read().rstrip())
    return 0 if good else 1


def controls_sg(runs, cfg, recdir):
    import contextlib
    import io
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        ok = D.selftest2(runs, cfg)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"controls-sg-{cfg}.txt")
    open(p, "w").write(buf.getvalue())
    LIB.durable([p])
    print(buf.getvalue().rstrip())
    return 0 if ok else 1


def nonpert(runs, a, b, recdir):
    ok, det = E.nonpert(runs, a, b)
    # canary: one PCAP byte of the twin changed in a copy must be detected
    import shutil
    import tempfile
    tmp = tempfile.mkdtemp(prefix="s5np-")
    try:
        rel = None
        for r_, _, fs in os.walk(os.path.join(runs, b)):
            for fn in sorted(fs):
                if fn.endswith(".pcapng") and "dsTt[0]" in fn:
                    rel = os.path.join(r_, fn)
        cp = os.path.join(tmp, "x.pcapng")
        shutil.copy(rel, cp)
        with open(cp, "r+b") as fh:
            fh.seek(os.path.getsize(cp) // 2)
            c = fh.read(1)
            fh.seek(-1, 1)
            fh.write(bytes([c[0] ^ 1]))
        key = os.path.relpath(rel, os.path.join(runs, b)).replace(b, "<config>")
        cok, cdet = E.nonpert(runs, a, b, mutate=(key, cp))
    finally:
        shutil.rmtree(tmp)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"nonpert-{b}.txt")
    with open(p, "w") as fh:
        fh.write(f"{'PASS' if ok else 'FAIL'} | non-perturbation {a} vs {b} | {det}\n")
        fh.write(f"{'PASS' if not cok else 'FAIL'} | NC-nonpert canary (one PCAP byte of the twin changed) | detected {not cok}: {cdet}\n")
    LIB.durable([p])
    print(open(p).read().rstrip())
    return 0 if (ok and not cok) else 1


def main(argv):
    cmd = argv[1]
    try:
        if cmd == "run":
            rc, _ = run_one(argv[2], argv[3], argv[4])
            return rc
        if cmd == "nonpert":
            return nonpert(argv[2], argv[3], argv[4], argv[5])
        if cmd == "controls-q8":
            return controls_q8(argv[2], argv[3], argv[4])
        if cmd == "controls-sg":
            return controls_sg(argv[2], argv[3], argv[4])
        if cmd == "quick":
            E.quick(argv[2], argv[3])
            return 0
    except Exception as ex:                     # an evaluation that cannot complete is never a PASS
        import traceback
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
