#!/usr/bin/env python3
"""M2-S7.2a Stage 5, increment S5-2: per-UE measurements for N > 1 (E0v-N, E1), as pure functions over a declared
per-UE observation record. Specification: results/M2-S7.2a-s5-2-addendum.md §3 (per-UE metrics) and §4 (H-ARQ
attribution, starvation and overload). No raw-output reading here: the adapter (m2s72_peru_adapter.py) builds the
observation records from a run; everything in this module is deterministic and tested on synthetic fixtures
(test_m2s72s5_2.py).

Units: simulation time in ps (int), sizes in bytes. +inf marks "not delivered by T_end" (the S7.1 / E0 rule:
undelivered ranks above every delivered value and is never dropped from a distribution).

Observation record of UE k (dict; every list in time order; missing evidence is None, never an empty list):
  k, node                     UE index, MacNodeId
  T, t0                       T_end and the start of the measurement window ([t0, T), E0: t0 = 2 s)
  loaded_dl, loaded_ul        does UE k carry configured load (placement one0 / sym)
  dl  {offered: [(t, B)], delivered: [(t, B)]}       load-DRB RLC SDUs entering the gNB RLC / delivered by the UE RLC
      {backlog: [(t, B)]}                            replayed load-DRB RLC TX backlog (E0 backlog()) at 0.5 s steps
      {accounting: {predicted_observed, destroyed, inflight, unexplained, observed_not_predicted, queued_end}}
  ul  {offered: [t], achieved: [t], frame_bytes}     talker[k] UL load frames sent / seen on N3 in UE k's tunnel
  mac {grants: [(t, lcid, B)], candidate_ttis: [tti], ineligible: int}   gNB DL grants / candidacy for node
  harq {processes, occupancy: {...} | None, ambiguous: int, orphan: int}  attribute_feedback() output for node
  gptp {cohort: [{seq, t_gm, fate, res, lag}]}       GM Syncs of domain 0 sent before the cohort horizon; fate from
                                                     the per-UE Q8 (used, delivered, lost, censored, invalid, late,
                                                     UNEXPLAINED); res = NW-TT rx -> DS-TT k tx; lag = DS-TT k tx of
                                                     the Sync -> DS-TT k rx of its Follow_Up (used pairs), else +inf
  clock {max_e_ns, update_gap_max_ps, updates}       slave k (M2-S6 between-step max |e|, exact oracle values)
"""
import math
from collections import Counter

S, MS, US, NS = 10 ** 12, 10 ** 9, 10 ** 6, 10 ** 3
INF = float("inf")
SYNC_INTERVAL = 125 * MS
B_RES = 5500 * US                  # Sync residence deadline (E0 exploratory deadline, kept)
WINDOW = S                         # starvation / service windows: 1 s
STARVE_SERVICE_RATIO = 0.5         # "severely under-served" (declared before any run; addendum §4.3)
SERVICE_TOL = 0.01                 # E1 verification: achieved >= (1 - tol) x offered over the window (addendum §5)


# ------------------------------------------------------------------------------------------- generic helpers ------
def pct(vals, q):
    """the S7.1 / E0 percentile rule (nearest rank on the sorted list, +inf allowed); None for an empty list"""
    if not vals:
        return None
    v = sorted(vals)
    return v[min(len(v) - 1, max(0, math.ceil(q * len(v)) - 1))]


def rate_bps(items, t0, T, size=None):
    """bits per second of the items inside [t0, T); items are (t, B) pairs or bare times (with a fixed size)"""
    if T <= t0:
        raise ValueError(f"empty window [{t0}, {T})")
    if size is None:
        b = sum(sz for t, sz in items if t0 <= t < T)
    else:
        b = sum(size for t in items if t0 <= t < T)
    return b * 8 / ((T - t0) / S)


def per_window(items, t0, T, w=WINDOW, size=None):
    """bytes per window [t0 + i w, t0 + (i + 1) w) for every complete window inside [t0, T)"""
    out = []
    i = 0
    while t0 + (i + 1) * w <= T:
        a, b = t0 + i * w, t0 + (i + 1) * w
        out.append(sum((size if size is not None else x[1]) for x in items if a <= (x if size is not None else x[0]) < b))
        i += 1
    return out


def sustained_growth(backlog):
    """the accepted E0 rule [A]: the per-second minimum of the backlog strictly increases in every second from
    [4 s, 5 s) to [11 s, 12 s) (8 windows)"""
    mins = []
    for s in range(4, 12):
        v = [b for t, b in backlog if s * S <= t < (s + 1) * S]
        mins.append(min(v) if v else None)
    return all(x is not None for x in mins) and all(mins[i + 1] > mins[i] for i in range(len(mins) - 1)), mins


def jain(xs):
    """Jain's fairness index of non-negative values; None if undefined (no value, or all zero)"""
    xs = [x for x in xs if x is not None]
    if not xs or sum(xs) == 0:
        return None
    return sum(xs) ** 2 / (len(xs) * sum(x * x for x in xs))


# ------------------------------------------------------------------------------------ H-ARQ feedback attribution ---
def attribute_feedback(events, nproc, window=None):
    """attribution rule A-1 (addendum §4.1). The gNB MAC log names the UE on every H-ARQ insert line ("for node with
    id <n>") but not on the feedback line ("feedback received for process <p> codeword <c>"). Process ids are per UE
    (one H-ARQ entity per UE), so a feedback line is attributed to UE u when u is the ONLY UE whose process p is open
    (inserted, codeword c, not yet fed back) at that point of the log (A-1a). If several UEs have process p open, the
    one whose open insert is exactly d* before the feedback is chosen, where d* is the single feedback delay of every
    A-1a attribution of the same run (A-1b); otherwise the line is AMBIGUOUS. A feedback line with no open candidate
    is ORPHAN. Never guessed: per-UE occupancy is returned only when ambiguous = orphan = 0.

    events: the gNB MAC log in LOG order: ("ins", t, node, proc, cw) and ("fb", t, proc, cw, result)
    window: (t_from, t_to) in ps: the TTIs over which the per-UE occupancy histograms are taken (default: the TTIs
    from the first to the last event of the log)
    returns {node: {...}} with the per-UE occupancy and delays, and a summary {ambiguous, orphan, a1a, a1b, d_star}"""
    # pass 1: A-1a only, to learn d*
    open_ = {}                                        # (node, proc, cw) -> insert time
    delays = Counter()
    for e in events:
        if e[0] == "ins":
            _, t, node, p, cw = e
            open_[(node, p, cw)] = t
        else:
            _, t, p, cw, res = e
            cands = [k for k in open_ if k[1] == p and k[2] == cw and open_[k] <= t]
            if len(cands) == 1:
                delays[t - open_.pop(cands[0])] += 1
            elif len(cands) > 1:
                # leave them open; pass 2 decides. Closing none keeps pass 1 conservative (no learned delay from it)
                pass
    d_star = next(iter(delays)) if len(delays) == 1 else None
    # pass 2: attribution with A-1a, then A-1b
    open_ = {}
    per = {}
    summ = {"a1a": 0, "a1b": 0, "ambiguous": 0, "orphan": 0, "reinsert": 0, "d_star_ps": d_star,
            "a1a_delays_ps": dict(delays)}
    nodes = sorted({e[2] for e in events if e[0] == "ins"})
    for n in nodes:
        per[n] = {"inserts": 0, "feedback": 0, "nack": 0, "delays_ps": [], "busy_events": []}
    for i, e in enumerate(events):
        if e[0] == "ins":
            _, t, node, p, cw = e
            if (node, p, cw) in open_:
                summ["reinsert"] += 1                 # an insert into a process that is still open: never expected
            open_[(node, p, cw)] = t
            per[node]["inserts"] += 1
            per[node]["busy_events"].append((i, t, +1))
            continue
        _, t, p, cw, res = e
        cands = [k for k in open_ if k[1] == p and k[2] == cw and open_[k] <= t]
        pick = None
        if len(cands) == 1:
            pick = cands[0]
            summ["a1a"] += 1
        elif len(cands) > 1 and d_star is not None:
            exact = [k for k in cands if t - open_[k] == d_star]
            if len(exact) == 1:
                pick = exact[0]
                summ["a1b"] += 1
        if pick is None:
            summ["ambiguous" if cands else "orphan"] += 1
            continue
        node = pick[0]
        per[node]["feedback"] += 1
        per[node]["nack"] += res == "NACK"
        per[node]["delays_ps"].append(t - open_.pop(pick))
        per[node]["busy_events"].append((i, t, -1))
    exact = summ["ambiguous"] == 0 and summ["orphan"] == 0 and summ["reinsert"] == 0
    tt = [e[1] // MS for e in events]
    span = (window[0] // MS, window[1] // MS) if window else ((min(tt), max(tt) + 1) if tt else (0, 0))
    for n in nodes:
        ev = per[n].pop("busy_events")
        per[n]["open_at_end"] = sum(1 for k in open_ if k[0] == n)
        if not exact:
            per[n]["occupancy"] = None
            continue
        per[n]["occupancy"] = occupancy_log_order(ev, nproc, span)
    return per, summ


def occupancy_log_order(busy_events, nproc, span):
    """busy-process count of one UE in LOG order (S5-1 F-2) over every TTI of span = [tti_from, tti_to): the count
    at the start of each TTI (carried through TTIs without an event of this UE) and the peak within each TTI.
    busy_events: (log index, t, +1 insert / -1 feedback), in log order."""
    by_tti = {}
    for _, t, d in busy_events:
        by_tti.setdefault(t // MS, []).append(d)
    busy, at_start, peak = 0, Counter(), Counter()
    first_tti = min(by_tti) if by_tti else None
    lo = span[0] if first_tti is None else min(span[0], first_tti)
    for tti in range(lo, span[1]):
        at = busy
        pk = busy
        for d in by_tti.get(tti, ()):
            busy += d
            if busy < 0:
                raise ValueError("negative occupancy: a feedback before its insert")
            pk = max(pk, busy)
        if tti >= span[0]:
            at_start[at] += 1
            peak[pk] += 1
    return {"processes": nproc, "ttis": span[1] - span[0], "busy_at_tti_start_hist": dict(sorted(at_start.items())),
            "peak_within_tti_hist": dict(sorted(peak.items())), "max_peak": max(peak) if peak else 0,
            "ttis_all_busy_at_peak": peak.get(nproc, 0)}


# ------------------------------------------------------------------------------------------- per-UE metrics -------
def per_ue(o):
    """every per-UE measurement of the addendum §3 table, from one observation record. Never a gate."""
    T, t0, k = o["T"], o["t0"], o["k"]
    m = {"k": k, "node": o["node"], "loaded_dl": o["loaded_dl"], "loaded_ul": o["loaded_ul"]}
    # 1. offered / achieved rates
    dl, ul = o.get("dl"), o.get("ul")
    if dl is not None:
        m["dl_offered_bps"] = rate_bps(dl["offered"], t0, T)
        m["dl_achieved_bps"] = rate_bps(dl["delivered"], t0, T)
        m["dl_service_ratio"] = (m["dl_achieved_bps"] / m["dl_offered_bps"]) if m["dl_offered_bps"] > 0 else None
        m["dl_offered_per_s"] = per_window(dl["offered"], t0, T)
        m["dl_achieved_per_s"] = per_window(dl["delivered"], t0, T)
        if dl.get("backlog") is not None:
            g, mins = sustained_growth(dl["backlog"])
            m["dl_backlog_sustained_growth"] = g
            m["dl_backlog_window_min"] = mins
            m["dl_backlog_end_bytes"] = dl["backlog"][-1][1] if dl["backlog"] else None
        m["dl_accounting"] = dl.get("accounting")
    if ul is not None:
        fb = ul["frame_bytes"]
        m["ul_offered_bps"] = rate_bps(ul["offered"], t0, T, size=fb)
        m["ul_achieved_bps"] = rate_bps(ul["achieved"], t0, T, size=fb)
        m["ul_service_ratio"] = (m["ul_achieved_bps"] / m["ul_offered_bps"]) if m["ul_offered_bps"] > 0 else None
        m["ul_offered_per_s"] = per_window(ul["offered"], t0, T, size=fb)
        m["ul_achieved_per_s"] = per_window(ul["achieved"], t0, T, size=fb)
    # 2. bearer service (MAC, DL)
    mac = o.get("mac")
    if mac is not None:
        g = [(t, l, b) for t, l, b in mac["grants"] if t0 <= t < T and b > 0]
        tti_all = max(1, (T - t0) // MS)
        gt = {t // MS for t, _, _ in g}
        ct = {x for x in mac["candidate_ttis"] if t0 // MS <= x < T // MS}
        m["mac_dl_grant_bps"] = sum(b for _, _, b in g) * 8 / ((T - t0) / S)
        m["mac_dl_grant_bytes_per_lcid"] = dict(_sum_by(g))
        m["mac_dl_tti_share"] = len(gt) / tti_all
        m["mac_dl_candidate_ttis"] = len(ct)
        m["mac_dl_candidate_not_granted_ttis"] = len(ct - gt)
        m["mac_dl_candidate_not_granted_share"] = (len(ct - gt) / len(ct)) if ct else None
        m["mac_maxci_found_ineligible"] = mac.get("ineligible")
    h = o.get("harq")
    if h is not None:
        m["harq"] = h
    # 3. packet delivery and 4. deadline outcomes (gPTP, per UE)
    gp = o.get("gptp")
    if gp is not None:
        co = gp["cohort"]
        fates = Counter(x["fate"] for x in co)
        res = [x["res"] for x in co]
        lag = [x["lag"] for x in co]
        m["gptp_cohort_n"] = len(co)
        m["gptp_fates"] = dict(fates)
        m["gptp_P_used"] = fates["used"] / len(co) if co else None
        m["gptp_unexplained"] = fates["UNEXPLAINED"]
        m["res_p50_ms"], m["res_p99_ms"], m["res_max_ms"] = (_ms(pct(res, 0.5)), _ms(pct(res, 0.99)), _ms(max(res) if res else None))
        m["lag_p99_ms"] = _ms(pct(lag, 0.99))
        m["deadline_res_gt_5p5ms"] = sum(1 for x in res if x > B_RES)
        m["deadline_lag_gt_sync_interval"] = sum(1 for x in lag if x > SYNC_INTERVAL)
        m["gptp_used_per_s"] = per_window([x["t_gm"] for x in co if x["fate"] == "used"], t0, T, size=1)
        m["gptp_sent_per_s"] = per_window([x["t_gm"] for x in co], t0, T, size=1)
    # 5. clock synchronisation (slave k)
    c = o.get("clock")
    if c is not None:
        m["max_e_ns"] = c.get("max_e_ns")
        m["update_gap_max_ms"] = _ms(c.get("update_gap_max_ps"))
        m["slave_updates"] = c.get("updates")
    m["starvation"] = starvation(m)
    m["overloaded"] = overloaded(m)
    return m


def _sum_by(g):
    out = Counter()
    for _, l, b in g:
        out[l] += b
    return out


def _ms(x):
    if x is None:
        return None
    return x if x == INF else x / MS


# --------------------------------------------------------------------------------- starvation and overload --------
def overloaded(m):
    """the accepted overload definition [A], per UE: sustained growth of UE k's load-DRB backlog AND DL achieved <
    offered. None (not evaluable) without DL load evidence; False for a UE without DL load."""
    if not m.get("loaded_dl"):
        return False
    if "dl_backlog_sustained_growth" not in m or m.get("dl_offered_bps") is None:
        return None
    return bool(m["dl_backlog_sustained_growth"]) and m["dl_achieved_bps"] < m["dl_offered_bps"]


def starvation(m):
    """per-UE starvation classes (addendum §4.3; declared before any run, reported, never correctness gates):
      ST-dl     a complete 1 s window with DL offered > 0 and DL achieved = 0
      ST-ul     the same for UL
      ST-gptp   a complete 1 s window in which the GM sent Syncs and UE k used none (every UE, loaded or not)
      US-dl/ul  under-served: service ratio over [t0, T) below STARVE_SERVICE_RATIO
    returns the list of classes that hold (empty = none); None entries are not produced: missing evidence makes the
    class absent from 'evaluated' instead"""
    out, evald = [], []
    for d in ("dl", "ul"):
        off, ach = m.get(f"{d}_offered_per_s"), m.get(f"{d}_achieved_per_s")
        if off is not None and ach is not None:
            evald.append(f"ST-{d}")
            if any(a == 0 and o > 0 for o, a in zip(off, ach)):
                out.append(f"ST-{d}")
        r = m.get(f"{d}_service_ratio")
        if r is not None:
            evald.append(f"US-{d}")
            if r < STARVE_SERVICE_RATIO:
                out.append(f"US-{d}")
    sent, used = m.get("gptp_sent_per_s"), m.get("gptp_used_per_s")
    if sent is not None and used is not None:
        evald.append("ST-gptp")
        if any(u == 0 and s > 0 for s, u in zip(sent, used)):
            out.append("ST-gptp")
    return {"holds": out, "evaluated": evald}


# -------------------------------------------------------------------------------------------- across UEs ---------
def across(ms):
    """distribution of the per-UE values (never a system-wide average alone): per metric min / max / spread / the
    worst UE, Jain's index of the service ratios, and the UEs in each starvation / overload class"""
    out = {"N": len(ms)}
    for key, worst in (("dl_service_ratio", min), ("ul_service_ratio", min), ("gptp_P_used", min), ("res_p99_ms", max),
                       ("lag_p99_ms", max), ("max_e_ns", max), ("update_gap_max_ms", max),
                       ("mac_dl_candidate_not_granted_share", max)):
        vals = [(m["k"], m.get(key)) for m in ms if m.get(key) is not None]
        if not vals:
            out[key] = None
            continue
        v = [x for _, x in vals]
        w = worst(vals, key=lambda kv: kv[1])
        out[key] = {"min": min(v), "max": max(v), "spread": (max(v) - min(v)) if INF not in v else INF,
                    "worst_ue": w[0], "worst": w[1], "n": len(v)}
    for d in ("dl", "ul"):
        rs = [m.get(f"{d}_service_ratio") for m in ms if m.get(f"loaded_{d}")]
        out[f"jain_{d}_service_ratio_loaded"] = jain(rs) if rs and None not in rs else None
    out["overloaded_ues"] = [m["k"] for m in ms if m.get("overloaded")]
    out["overload_not_evaluable_ues"] = [m["k"] for m in ms if m.get("overloaded") is None]
    cls = Counter()
    for m in ms:
        for c in m["starvation"]["holds"]:
            cls[c] += 1
    out["starvation_ues"] = {c: [m["k"] for m in ms if c in m["starvation"]["holds"]] for c in sorted(cls)}
    # the system aggregate is reported next to (never instead of) the per-UE values
    for d in ("dl", "ul"):
        off = [m.get(f"{d}_offered_bps") for m in ms]
        ach = [m.get(f"{d}_achieved_bps") for m in ms]
        out[f"system_{d}_offered_bps"] = sum(off) if None not in off else None
        out[f"system_{d}_achieved_bps"] = sum(ach) if None not in ach else None
    return out


# --------------------------------------------------------------------------- structural checks (correctness) ----
def structural_rows(obs, expected_ues, harq_summary=None, totals=None):
    """correctness rows of the per-UE evidence itself (addendum §3.3), each (row, subject, status, detail) with
    status PASS / FAIL / NOT EVALUATED. These gate the per-UE evaluation of a run, never performance:
      PU-1  every expected UE has an observation record, each with its own node id (distinct)
      PU-2  per-UE gPTP accounting: every cohort Sync has exactly one fate; UNEXPLAINED = 0 (the Q8 rule, per UE)
      PU-3  per-UE load-DRB accounting: destroyed = unexplained = observed-not-predicted = 0 (1.8.1: no deletion)
      PU-4  H-ARQ attribution complete: ambiguous = orphan = 0 (else the per-UE occupancy is NOT EVALUATED)
      PU-5  conservation of attribution: the per-UE DL grant bytes and H-ARQ inserts sum to the run totals"""
    rows = []
    ks = sorted(o["k"] for o in obs)
    nodes = [o["node"] for o in obs]
    ok = ks == sorted(expected_ues) and len(set(nodes)) == len(nodes) and None not in nodes
    rows.append(("PU-1", "run", "PASS" if ok else "FAIL", f"UEs {ks} (expected {sorted(expected_ues)}), nodes {nodes}"))
    for o in obs:
        gp = o.get("gptp")
        if gp is None:
            rows.append(("PU-2", f"UE {o['k']}", "NOT EVALUATED", "no per-UE gPTP evidence"))
        else:
            seqs = [x["seq"] for x in gp["cohort"]]
            un = sum(1 for x in gp["cohort"] if x["fate"] == "UNEXPLAINED")
            dup = len(seqs) - len(set(seqs))
            nofate = sum(1 for x in gp["cohort"] if not x.get("fate"))
            ok = un == 0 and dup == 0 and nofate == 0 and len(seqs) > 0
            rows.append(("PU-2", f"UE {o['k']}", "PASS" if ok else "FAIL",
                         f"cohort {len(seqs)}, UNEXPLAINED {un}, duplicate fates {dup}, without fate {nofate}"))
        dl = o.get("dl")
        if not o["loaded_dl"]:
            rows.append(("PU-3", f"UE {o['k']}", "NOT APPLICABLE", "no DL load on this UE"))
        elif dl is None or dl.get("accounting") is None:
            rows.append(("PU-3", f"UE {o['k']}", "NOT EVALUATED", "no load-DRB accounting"))
        else:
            a = dl["accounting"]
            ok = a.get("destroyed") == 0 and a.get("unexplained") == 0 and a.get("observed_not_predicted") == 0
            rows.append(("PU-3", f"UE {o['k']}", "PASS" if ok else "FAIL", f"load-DRB accounting {a}"))
    if harq_summary is None:
        rows.append(("PU-4", "run", "NOT EVALUATED", "no MAC log"))
    else:
        ok = harq_summary["ambiguous"] == 0 and harq_summary["orphan"] == 0 and harq_summary.get("reinsert", 0) == 0
        rows.append(("PU-4", "run", "PASS" if ok else "FAIL",
                     f"A-1a {harq_summary['a1a']}, A-1b {harq_summary['a1b']} (d* {harq_summary['d_star_ps']} ps), "
                     f"ambiguous {harq_summary['ambiguous']}, orphan {harq_summary['orphan']}, re-insert "
                     f"{harq_summary.get('reinsert', 0)}"))
    if totals is None:
        rows.append(("PU-5", "run", "NOT EVALUATED", "no run totals"))
    else:
        gsum = sum(sum(b for _, _, b in o["mac"]["grants"]) for o in obs if o.get("mac") is not None)
        isum = sum(o["harq"]["inserts"] for o in obs if o.get("harq") is not None and "inserts" in o["harq"])
        ok = gsum == totals["dl_grant_bytes"] and (totals.get("harq_inserts") is None or isum == totals["harq_inserts"])
        rows.append(("PU-5", "run", "PASS" if ok else "FAIL",
                     f"per-UE DL grant bytes {gsum} vs run {totals['dl_grant_bytes']}; per-UE H-ARQ inserts {isum} vs run "
                     f"{totals.get('harq_inserts')}"))
    return rows
