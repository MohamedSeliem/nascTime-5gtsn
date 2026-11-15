#!/usr/bin/env python3
"""M2-S7.2a Stage 5, increment S5-2: raw outputs of one N > 1 run -> the per-UE observation records of
m2s72_peru (addendum §3.2). Built only on the accepted readers, unchanged: m2s72_runs (Run72, UE views, vectors),
check_m2s72_e0.Q8 with k > 0 and the strict "exclusion" attribution rule (E0 r2 / P1), replay_um, the E0 cohort and
pair rules, m2s72_maclog, diag_m2s72_dl_active.dl_sched. Read-only.

STATUS: NOT YET VALIDATED ON REAL N > 1 OUTPUT. The functions that touch raw outputs (observe, totals) can only be
validated on a real 1.8.1 run with N > 1. 'validate' (check_m2s72_s5n.py adapter-validate) is the declared
read-only validation on the CP2 rev. 2 outputs the VM keeps (no new simulation); until it has passed and been
reviewed, check_m2s72_s5n.py refuses to evaluate E0v-N runs (fail-closed). harq_events() is tested on synthetic logs.

Evidence sources per UE k (node n_k = run.node_id[k]):
  DL load    gNB RLC TX gnb1.cellularNic.rlc-um-<n_k>-1.tx (SDUs in) -> UE RLC RX ue[k].cellularNic.nrRlc-um-1-1.rx
             (SDUs delivered), SDUs > 1000 B (the E0 load filter), replayed with replay_um / G.deliveries
  UL load    UE RLC TX ue[k].cellularNic.nrRlc-um-1-1.tx (SDUs in) -> gNB RLC RX gnb1.cellularNic.rlc-um-<n_k>-1.rx
             (SDUs delivered), SDUs > 1000 B. The PCAP recorders capture gPTP only, so no application-level per-UE UL
             count exists; RLC level is the E0 level for DL too. Missing vectors -> NOT EVALUATED (never zero)
  MAC        m2s72_maclog grants of node n_k (DL); candidate TTIs from diag_m2s72_dl_active.dl_sched; MAXCI ineligible
  H-ARQ      m2s72_peru.attribute_feedback over harq_events() (gNB MAC log in log order)
  gPTP       Q8(ev, mlog, opt, k, attr="exclusion"): stage times, fates, pairs (E0 rules), per UE
  clock      ev.E[k] (the M2-S6 evaluation of slave k inside the accepted Block B evaluation)
"""
import gzip
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s72_peru as P  # noqa: E402

LOAD_MIN = 1000
R_INSERT = re.compile(r"H-ARQ TX: new pdu \(id (\d+) \) inserted into process (\d+) codeword id: (\d+) for node with id (\d+)")
R_FB = re.compile(r"H-ARQ TX: feedback received for process (\d+) codeword (\d+) result is (ACK|NACK)")


def t_ps(s):
    """'1.234567890123' (s) -> ps, exactly (the m2s72_maclog rule)"""
    whole, _, frac = s.partition(".")
    return int(whole) * P.S + int((frac + "0" * 12)[:12])


def harq_events(path, gnb="M2S72Bridge.gnb1.cellularNic.mac"):
    """the gNB MAC log's H-ARQ insert and feedback lines in LOG order (the line format "<t>|<module>|<message>" of
    the runner's cmdenv-log-prefix "%t|%M|")"""
    out = []
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|", 2)
            if len(p) < 3 or p[1] != gnb or not p[0][:1].isdigit():
                continue
            m = R_INSERT.search(p[2])
            if m:
                out.append(("ins", t_ps(p[0]), int(m.group(4)), int(m.group(2)), int(m.group(3))))
                continue
            m = R_FB.search(p[2])
            if m:
                out.append(("fb", t_ps(p[0]), int(m.group(1)), int(m.group(2)), m.group(3)))
    return out


# ------------------------------------------------------------------------------------------- raw -> records ------
def _vec(ev, mod, name, T):
    key = (f"M2S72Bridge.{mod}", name)
    if key not in ev.vec:
        return None
    return [(t, int(float(v))) for t, v in ev.vec[key] if t <= T]


class _Drb:
    """the replayed RLC UM TX of one DRB: sdus_h, done (E0 backlog() input)"""
    def __init__(self, sdus, pdus):
        import check_m2s72_e0 as E
        self.sdus_h = sdus
        self.done, _, self.left = E.replay_um(sdus, pdus)


def dl_load(ev, k, node, T):
    import check_m2s72_e0 as E
    import gate_m2s71_p0 as G
    tx, rx = f"gnb1.cellularNic.rlc-um-{node}-1.tx", f"ue[{k}].cellularNic.nrRlc-um-1-1.rx"
    sdus = _vec(ev, tx, "receivedPacketFromUpperLayer:vector(packetBytes)", T)
    pdus = _vec(ev, tx, "sentPduSize:vector", T)
    deliv = _vec(ev, rx, "sentPacketToUpperLayer:vector(packetBytes)", T)
    rxp = _vec(ev, rx, "receivedPacketFromLowerLayer:vector(packetBytes)", T)
    if None in (sdus, pdus, deliv, rxp):
        return None
    d = _Drb(sdus, pdus)
    matched, unmatched, rest, _ = G.deliveries(d.done, deliv, rxp, pdus, sdus, T)
    acc = {"predicted_observed": len(matched), "destroyed": sum(1 for x in unmatched if x[3] is True),
           "inflight": sum(1 for x in unmatched if x[3] == "inflight"), "unexplained": sum(1 for x in unmatched if x[3] is False),
           "observed_not_predicted": len(rest), "queued_end": len(d.left)}
    return {"offered": [x for x in sdus if x[1] > LOAD_MIN], "delivered": [x for x in deliv if x[1] > LOAD_MIN],
            "backlog": E.backlog(d, T), "accounting": acc}


def ul_load(ev, k, node, T):
    tx, rx = f"ue[{k}].cellularNic.nrRlc-um-1-1.tx", f"gnb1.cellularNic.rlc-um-{node}-1.rx"
    sdus = _vec(ev, tx, "receivedPacketFromUpperLayer:vector(packetBytes)", T)
    deliv = _vec(ev, rx, "sentPacketToUpperLayer:vector(packetBytes)", T)
    if sdus is None or deliv is None:
        return None
    return {"offered": [t for t, b in sdus if b > LOAD_MIN], "achieved": [t for t, b in deliv if b > LOAD_MIN],
            "frame_bytes": None, "sdu_bytes": sorted({b for _, b in sdus if b > LOAD_MIN})}


def gptp(ev, mlog, opt, k, T):
    """per-UE cohort records with the E0 rules (Q8 fates and pairs, residence NW-TT rx -> DS-TT k tx, lag)"""
    import check_m2s72_e0 as E
    q = E.Q8(ev, mlog, opt, k=k, attr="exclusion")
    pairs = E.q8_rows(f"{ev.run.cfg}-0 UE {k}", q)            # the per-UE Q8 gate rows (E.rows)
    co = [s for s in pairs if (E.SYNC, s) in q.st["GM"] and q.st["GM"][(E.SYNC, s)] < E.T_COHORT]
    out = []
    for s in sorted(co):
        a, b = q.st["NW-TT rx"].get((E.SYNC, s)), q.ds_tx.get((E.SYNC, s))
        res = b - a if (a is not None and b is not None and b <= T) else P.INF
        if pairs[s] == "used" and (E.FU, s) in q.ds_rx and (E.SYNC, s) in q.ds_tx:
            lag = q.ds_rx[(E.FU, s)] - q.ds_tx[(E.SYNC, s)]
        else:
            lag = P.INF
        out.append({"seq": s, "t_gm": q.st["GM"][(E.SYNC, s)], "fate": pairs[s], "res": res, "lag": lag})
    return {"cohort": out, "q8_internal": {"n3_bad": q.n3_bad, "map_bad": q.map_bad, "model_err": q.model_err}}


def clock(ev, k):
    import check_m2s72_e0 as E
    Ek = ev.E.get(k)
    if Ek is None:
        return None
    cal = [x["seq"] for x in Ek.fus if "skip" not in x and x.get("nrr_valid")]
    vals = [abs(x["max_between"]) for x in Ek.iv[2:] if x["seq"] in cal and cal and x["seq"] != cal[0] and x["max_between"] is not None]
    upd = [x["sF"] for x in Ek.fus if "old" in x]
    gaps = sorted(b - a for a, b in zip(upd, upd[1:]))
    return {"max_e_ns": float(max(vals)) / E.NS if vals else None, "update_gap_max_ps": gaps[-1] if gaps else None,
            "updates": len(upd)}


def observe(ev, mlog_path, opt, loaded, t0=2 * P.S, nproc=16):
    """per-UE observation records of one run + the run totals + the H-ARQ attribution summary.
    loaded: {k: (dl, ul)} as DECLARED by the configuration (the generator's placement); the evidence is compared
    with it in validate()"""
    import diag_m2s72_dl_active as D
    import m2s72_maclog as ML
    T, run = ev.T, ev.run
    mlog = ML.MacLog(mlog_path) if mlog_path and os.path.exists(mlog_path) else None
    cand = grants_tti = None
    if mlog is not None:
        cand, grants_tti = D.dl_sched(mlog_path)
    events = harq_events(mlog_path) if mlog is not None else None
    per_h, summ = P.attribute_feedback(events, nproc, (t0, T)) if events is not None else ({}, None)
    obs = []
    for k in range(run.n):
        node = run.node_id[k]
        o = {"k": k, "node": node, "T": T, "t0": t0, "loaded_dl": loaded[k][0], "loaded_ul": loaded[k][1]}
        o["dl"] = dl_load(ev, k, node, T)
        o["ul"] = ul_load(ev, k, node, T)
        if o["ul"] is not None:
            o["ul"]["frame_bytes"] = o["ul"]["sdu_bytes"][0] if len(o["ul"]["sdu_bytes"]) == 1 else None
            if o["ul"]["frame_bytes"] is None and o["ul"]["offered"]:
                o["ul"] = None                               # several load SDU sizes: not the declared load (NE)
            elif o["ul"]["frame_bytes"] is None:
                o["ul"]["frame_bytes"] = 0
        if mlog is not None:
            o["mac"] = {"grants": [(t, l, b) for t, d, n, l, b in mlog.grants if d == "DL" and n == node],
                        "candidate_ttis": sorted(tti for tti, cs in cand.items() if any(c[0] == node for c in cs)),
                        "ineligible": None}
            h = per_h.get(node, {"inserts": 0, "feedback": 0, "nack": 0, "delays_ps": [], "occupancy": None})
            o["harq"] = {"processes": nproc, **{x: h[x] for x in ("inserts", "feedback", "nack", "occupancy")},
                         "feedback_delay_ps": sorted(set(h["delays_ps"]))}
        else:
            o["mac"] = o["harq"] = None
        o["gptp"] = gptp(ev, mlog, opt, k, T)
        o["clock"] = clock(ev, k)
        obs.append(o)
    totals = None
    if mlog is not None:
        totals = {"dl_grant_bytes": sum(b for t, d, n, l, b in mlog.grants if d == "DL"),
                  "harq_inserts": sum(1 for e in events if e[0] == "ins")}
    return obs, totals, summ


def validate(obs, totals, summ, expected_ues):
    """the adapter's own correctness rows on a real run (addendum §3.4): the structural PU rows plus
      AV-1  per UE: Q8's internal consistency (no N3 tunnel problem, no SDU-to-frame mapping problem, no replay
            model error) for UE k's gPTP DRB
      AV-2  per UE: the observed load matches the declared placement (load SDUs present iff declared, DL and UL)
      AV-3  every UE has DL and UL RLC evidence (vectors present)"""
    rows = P.structural_rows(obs, expected_ues, summ, totals)
    for o in obs:
        qi = o["gptp"]["q8_internal"]
        ok = not qi["n3_bad"] and not qi["map_bad"] and qi["model_err"] is None
        rows.append(("AV-1", f"UE {o['k']}", "PASS" if ok else "FAIL", f"Q8 internal {qi}"))
        probs = []
        for d, key in (("dl", "offered"), ("ul", "offered")):
            if o[d] is None:
                continue
            seen = bool(o[d][key])
            if seen != bool(o[f"loaded_{d}"]):
                probs.append(f"{d}: declared {o[f'loaded_{d}']}, load SDUs observed {seen}")
        rows.append(("AV-2", f"UE {o['k']}", "PASS" if not probs else "FAIL", "; ".join(probs) or "declared load = observed load"))
        miss = [d for d in ("dl", "ul") if o[d] is None]
        rows.append(("AV-3", f"UE {o['k']}", "PASS" if not miss else "NOT EVALUATED", f"missing RLC evidence {miss}" if miss else "DL and UL RLC vectors present"))
    return rows
