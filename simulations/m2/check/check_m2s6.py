#!/usr/bin/env python3
"""M2-S6 checker (migration/m2-s6-design.md rev. 2, section 6.2): rows K (clocks), R (rate ratios), S
(slave reproduction), E (error decomposition and closure), P (Pdelay), T (TT clocks), H (hypotheses,
reported), W (network conditions, reported), X (statistics, reported), N (negative controls).

    check_m2s6.py <runs dir>      checks every M2-S6 config whose runs are present
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s6_runs as RR  # noqa: E402
import m2s6_clocks as MC  # noqa: E402
import inet_model as M  # noqa: E402
import clock_model as KM  # noqa: E402
import slave_m2s6 as O5  # noqa: E402
import decomp_m2s6 as DC  # noqa: E402
from fractions import Fraction  # noqa: E402

NS = RR.NS
rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def fmt_ps(p):
    return f"{p / NS:.3f} ns"


# ---------------------------------------------------------------------------------------
# rows K: clocks (O1) against every recorded sample
def gm_clocks(R):
    c = R.conf
    nc = MC.NodeClocks(c["gm"], c["end"], R.vecv(f"{R.gmn}.clock.oscillator", "driftRateChanged:vector"), R.gmn)
    MC.replay(nc)
    return nc


def recorded_steps(R):
    """[(t, new, ppm)] of the slave's setClockTime calls, from the recorded vectors (replay mode:
    gate D0d; stage A free-running clocks have none). new = last timeChanged value at that time."""
    comp = R.vecv(f"{R.sln}.clock", "oscillatorCompensationChanged:vector")[1:]
    tc = R.vecv(f"{R.sln}.clock", "timeChanged:vector")
    last = {}
    for t, v in tc:
        last[t] = v
    out = []
    for t, v in comp:
        out.append((t, M_ps(last[t]), float(v)))
    return out


def M_ps(v):
    """A recorded clock value (double of ps * 1e-12, %.17g) back to integer ps (exact: |v| < 2^53 ps)."""
    p = round(float(v) * 1e12)
    assert MC.dbl(p) == float(v), v
    return p


def slave_clocks(R, steps):
    c = R.conf
    nc = MC.NodeClocks(c["sl"], c["end"], R.vecv(f"{R.sln}.clock.oscillator", "driftRateChanged:vector"), R.sln)
    MC.replay(nc, steps)
    return nc


def k_rows(R, gnc, snc, tag):
    c = R.conf
    for nc, mod, emit_c, emit_u in [x for x in ((gnc, R.gmn, True, False), (snc, R.sln, True, True)) if x[0] is not None]:
        for clk, sub, emit in ((nc.C, "clock", emit_c), (nc.U, "clock.underlyingClock", emit_u)):
            fixed, alt = MC.predicted_samples(nc, clk, emit)
            ok, n, bad = MC.compare_samples(R.vecv(f"{mod}.{sub}", "timeChanged:vector"), fixed, alt)
            add(f"K {tag}", f"{mod}.{sub} timeChanged: every recorded sample = O1 ({n} samples; "
                f"{len(nc.osc.changes)} oscillator changes, {sum(1 for s in nc.steps if s[4])} tick resets)", ok, str(bad) if not ok else "")
        ok, n, bad = MC.compare_drift(R.vecv(f"{mod}.clock.oscillator", "driftRateChanged:vector"), nc)
        o = c[("gm" if nc is gnc else "sl")]["osc"]
        if o["kind"] == "drift" and not o["rw"]:
            add(f"K {tag}", f"{mod} driftRateChanged = schedule ({n} values)", ok, "" if ok else str(bad))
        elif o["rw"]:
            # random walk (RandomDriftOscillator, driftRateChange = uniform(-b, b) every 12.345 ms): the values are
            # replayed from the recording; checked here: change times k x 12.345 ms and every step within [-b, b]
            v = [(t, float(x)) for t, x in R.vecv(f"{mod}.clock.oscillator", "driftRateChanged:vector")]
            ch = v[1:-1]
            times_ok = all(t == (i + 1) * RR.STAIR_DT for i, (t, x) in enumerate(ch)) and v[0] == (0, o["ppm"])
            steps = [b - a for (_, a), (_, b) in zip([v[0]] + ch[:-1], ch)]
            add(f"K {tag}", f"{mod} random-walk drift: {len(ch)} changes at k x 12.345 ms, every step within +-{o['rw']} ppm "
                f"(largest {max(abs(x) for x in steps):.6f} ppm); final drift {v[-1][1]:+.6f} ppm",
                times_ok and all(abs(x) <= o["rw"] * (1 + 1e-12) for x in steps) and len(ch) == 810)
        if nc.ties:
            add(f"K {tag}", f"{mod}: no drift change at the time of a step", False, f"{nc.ties} ties")
    # GM timestamps on the wire: POT = C_G(Sync TX first bit); Pdelay t2 = U_G(Req RX first bit), t3 = U_G(Resp TX first bit)
    sync = {f["seq"]: f for f in RR.C5.sel(R.gm, 2, RR.SYNC)}
    req = {f["seq"]: f for f in RR.C5.sel(R.gm, 1, RR.REQ, dom=None)}
    resp = {f["seq"]: f for f in RR.C5.sel(R.gm, 2, RR.RESP, dom=None)}
    q = [("C", f["start"]) for f in sync.values()] + [("U", f["start"]) for f in req.values()] + [("U", f["start"]) for f in resp.values()]
    attach_reads(gnc, q, R.vecv(f"{R.gmn}.clock.oscillator", "driftRateChanged:vector") if c["gm"]["osc"]["rw"] else None)
    nbad = n = 0
    for f in RR.C5.sel(R.gm, 2, RR.FU):
        g = f["g"]
        if g is None or g["seq"] not in sync:
            continue
        n += 1
        if M.inet_read_timestamp(*g["pot"]) != (gnc_read(gnc, "C", sync[g["seq"]]["start"]) // NS) * NS:
            nbad += 1
    np_ = npbad = 0
    for f in RR.C5.sel(R.gm, 2, RR.RESP, dom=None):
        if f["g"] and f["seq"] in req:
            np_ += 1
            if M.inet_read_timestamp(*f["g"]["ts"]) != (gnc_read(gnc, "U", req[f["seq"]]["start"]) // NS) * NS:
                npbad += 1
    for f in RR.C5.sel(R.gm, 2, RR.RFU, dom=None):
        if f["g"] and f["seq"] in resp:
            np_ += 1
            if M.inet_read_timestamp(*f["g"]["ts"]) != (gnc_read(gnc, "U", resp[f["seq"]]["start"]) // NS) * NS:
                npbad += 1
    add(f"K {tag}", f"GM POT on the wire = C_G(Sync first bit) ({n} Follow_Ups); Pdelay t2/t3 = U_G ({np_} values)",
        nbad == 0 and npbad == 0 and n > 0, f"{nbad} POT, {npbad} t2/t3 mismatches")
    # sign: positive ppm -> POT - s grows
    o = c["gm"]["osc"]
    if o["kind"] == "drift" and not o["stair"] and not o["rw"] and o["ppm"] != 0:
        pots = [(sync[f["g"]["seq"]]["start"], M.inet_read_timestamp(*f["g"]["pot"])) for f in RR.C5.sel(R.gm, 2, RR.FU)
                if f["g"] and f["g"]["seq"] in sync]
        d = (pots[-1][1] - pots[-1][0]) - (pots[0][1] - pots[0][0])
        add(f"K {tag}", f"sign: GM {o['ppm']:+g} ppm -> POT - s changes by {fmt_ps(d)} over the run", (d > 0) == (o["ppm"] > 0))


def gnc_read(nc, which, t):
    return nc.reads[(which, t)]


def attach_reads(nc, queries, drift_vec=None):
    """Fresh O1 pass over the node's drift schedule and steps, reading C or U at every (which, t) of
    `queries` in time order (a read at a step time is taken before the step: INET reads before it
    applies a Follow_Up)."""
    f = MC.NodeClocks(nc.nconf, nc.end, drift_vec, nc.name)
    ev = sorted(set(queries), key=lambda q: (q[1], q[0]))
    steps, si, out = list(nc.steps), 0, {}
    for which, t in ev:
        while si < len(steps) and steps[si][0] < t:
            st = steps[si]
            f.step(st[0], st[2], st[3], True)
            si += 1
        if which == "C":
            out[(which, t)] = f.read_C(t)
        elif which == "U":
            out[(which, t)] = f.read_U(t)
        else:                                   # "G": unquantized time (design 4.1) of the raw clock
            f.advance(t)
            out[(which, t)] = f.U.gamma(t)
    nc.reads = out
    return out


# ---------------------------------------------------------------------------------------
# servo runs: O5 (rows S), O4 (rows R, P), O3 (rows E), intervals (design 4.5)
class Eval:
    """Everything the oracles predict for one run, with the TT timestamp source (A1: simulation time)."""
    def __init__(self, R, tt=None):
        self.R = R
        c = R.conf
        sel = RR.C5.sel
        self.gnc = gm_clocks(R)
        self.sync = {f["seq"]: f for f in sel(R.gm, 2, RR.SYNC)}
        gvec = R.vecv(f"{R.gmn}.clock.oscillator", "driftRateChanged:vector") if c["gm"]["osc"]["rw"] else None
        attach_reads(self.gnc, [("C", f["start"]) for f in self.sync.values()], gvec)
        pot = {s: self.gnc.reads[("C", f["start"])] for s, f in self.sync.items()}
        # what the slave read from the DS-TT's Pdelay_Resp / Resp_FU chunks (A1: simulation times)
        if tt is None:
            t2 = {f["seq"]: f["start"] for f in sel(R.ds1, 1, RR.REQ, dom=None)}
            t3 = {f["seq"]: f["start"] for f in sel(R.ds1, 2, RR.RESP, dom=None)}
        else:
            t2, t3 = tt["ds_t2"], tt["ds_t3"]
        self.cf = RR.C5.cf_map(R)
        svec = R.vecv(f"{R.sln}.clock.oscillator", "driftRateChanged:vector") if c["sl"]["osc"]["rw"] else None
        self.o5 = O5.SlaveO5(c["sl"], c["end"], svec, R.sln)
        self.o5.run(R.sl, lambda s: t2[s], lambda s: t3[s], lambda s: pot[s], lambda s: self.cf[s])
        self.dec = DC.Decomp(R, sel, RR.C5.by_seq, RR.C5.cf_map, None, self.o5, tt)
        q = self.dec.queries() + [("C", t) for t, v in self.gnc.C.ms_values]
        attach_reads(self.gnc, q, gvec)
        self.dec.G = lambda k, t: self.gnc.reads[(k, t)]
        self.fus = self.dec.run()
        gm_ms = dict(self.gnc.C.ms_values)
        sl_ms = dict(self.o5.nc.C.ms_values)
        self.iv = DC.intervals(self.fus, gm_ms, sl_ms, lambda t: self.gnc.reads[("C", t)])


def s_rows(E, tag):
    res = O5.compare(E.o5, E.R, E.R.sln)
    ok = all(v[0] for v in res.values())
    add(f"S {tag}", "O5 = every recorded slave value: " + ", ".join(f"{k} {v[1]}" for k, v in res.items()), ok,
        "; ".join(f"{k}: {v[2]}" for k, v in res.items() if not v[0]))
    return ok


def r_rows(E, tag):
    """O4: NW-TT neighborRateRatio and link delay recomputed from PCAP + O1 (not from the logs), rr_out,
    carriage to the DS-TT, csro on the wire (design 4.3)."""
    R, sel, G = E.R, RR.C5.sel, E.gnc
    req, resp = {f["seq"]: f for f in sel(R.nw1, 2, RR.REQ, dom=None)}, {f["seq"]: f for f in sel(R.nw1, 1, RR.RESP, dom=None)}
    greq, gresp = {f["seq"]: f for f in sel(R.gm, 1, RR.REQ, dom=None)}, {f["seq"]: f for f in sel(R.gm, 2, RR.RESP, dom=None)}
    attach_reads(G, list(G.reads) + [("U", greq[s]["start"]) for s in greq] + [("U", gresp[s]["start"]) for s in gresp],
                 R.vecv(f"{R.gmn}.clock.oscillator", "driftRateChanged:vector") if R.conf["gm"]["osc"]["rw"] else None)
    bad, n, prev = [], 0, None
    for r in [x for x in R.nweng if x["event"] == "measure"]:
        s = int(r["seq"])
        t1, t4 = req[s]["start"], resp[s]["start"]                 # A1: NW-TT timestamps = simulation time
        t2, t3 = G.reads[("U", greq[s]["start"])], G.reads[("U", gresp[s]["start"])]
        e = 0 if prev is None else KM.from_integer_ratio(t3 - prev[0], t4 - prev[1])
        D = M.trunc_div2(KM.mul_round(t4 - t1, e) - (t3 - t2))
        n += 1
        if (int(r["nrrQ63"]), int(r["D"]), int(r["t2"]), int(r["t3"])) != (e, D, t2, t3) or int(r["t1"]) != t1 or int(r["t4"]) != t4:
            bad.append(s)
        prev = (t3, t4)
    add(f"R {tag}", f"NW-TT neighborRateRatio (Q63) and link delay D recomputed from PCAP + O1 = engine log ({n} exchanges)", not bad and n > 0, str(bad[:5]))
    nwc = {int(x["seq"]): x for x in R.nwlog if x["event"] == "corrected"}
    dsc = {int(x["seq"]): x for x in R.dslog if x["event"] == "corrected"}
    meas = [x for x in R.nweng if x["event"] == "measure"]
    bad_rr, bad_carry, n = [], [], 0
    for s, x in nwc.items():
        ex = [m for m in meas if int(m["t"]) < int(x["t"])][-1]
        exp = KM.to_double(KM.product(KM.from_double(float(x["rrIn"])), int(ex["nrrQ63"])))
        n += 1
        if float(x["rrOut"]) != exp or float(x["rrIn"]) != 1.0:
            bad_rr.append(s)
        if s in dsc and float(dsc[s]["rrOut"]) != float(x["rrOut"]):
            bad_carry.append(s)
    add(f"R {tag}", f"rr_out = toDouble(fromDouble(rr_in) x nRR) with rr_in = 1.0 from the INET GM ({n} Follow_Ups); the DS-TT uses the carried value",
        not bad_rr and not bad_carry and n > 0, f"rr {bad_rr[:3]} carry {bad_carry[:3]}")
    pts = [("NW-TT eth[0] TX", R.nw0, 2), ("DS-TT eth[1] TX", R.ds1, 2), ("slave RX", R.sl, 1)]
    if not R.unit:
        pts.insert(1, ("UE eth[0] TX", R.ue, 2))
    nb, nt = 0, 0
    for name, fr, d in pts:
        for f in sel(fr, d, RR.FU):
            if f["g"] and f["g"]["seq"] in nwc:
                nt += 1
                if f["g"]["csro"] != M.inet_csro(float(nwc[f["g"]["seq"]]["rrOut"])):
                    nb += 1
    add(f"R {tag}", f"csro on the wire = ceil((rr_out - 1) * 2^41) at {', '.join(p[0] for p in pts)} ({nt} frames)", nb == 0 and nt > 0, f"{nb} mismatches")
    y = R.conf["gm"]["osc"]["ppm"]
    cal = [float(dsc[s]["rrOut"]) for s, f in [(f["seq"], f) for f in E.fus if "skip" not in f] if f["nrr_valid"] and s in dsc]
    uncal = [f["seq"] for f in E.fus if "skip" not in f and not f["nrr_valid"]]
    if y != 0 and cal:
        add(f"R {tag}", f"direction: GM {y:+g} ppm -> calibrated rr_out {min(cal):.12f}..{max(cal):.12f} ({'> 1' if y > 0 else '< 1'}); "
            f"uncalibrated (rr_out = 1, before the NW-TT's 2nd exchange): Follow_Ups {uncal}", all((v > 1) == (y > 0) for v in cal))


def e_rows(E, tag):
    fus = [f for f in E.fus if "skip" not in f]
    keys = sorted({k for f in fus for k in f["closure"]})
    for k in keys:
        n = sum(1 for f in fus if k in f["closure"])
        nb = sum(1 for f in fus if k in f["closure"] and not f["closure"][k])
        add(f"E {tag}", f"{k}: exact for every Follow_Up ({n})", nb == 0 and n > 0, f"{nb} failures")
    skipped = [f["seq"] for f in E.fus if "skip" in f]
    if skipped:
        add(f"E {tag}", f"Follow_Ups used by the slave but not corrected by both translators: {skipped}", False)
    L1 = E.o5.nc.C.L == 1
    if L1:
        nb = sum(1 for f in fus if "old" in f and not f["exact_step"])
        add(f"E {tag}", f"C4 exact against the measured offset (1 ps ticks): old - new = o_k for every step ({sum(1 for f in fus if 'old' in f)})", nb == 0)


def run_eval(runs, cfg, rep, report):
    R = RR.Run(runs, cfg, rep)
    tag = f"{cfg}-{rep}"
    E = Eval(R)
    k_rows(R, E.gnc, None, tag)      # GM clocks; the slave's clocks are checked by the S rows
    s_ok = s_rows(E, tag)
    r_rows(E, tag)
    e_rows(E, tag)
    report.append((cfg, rep, E, s_ok))
    return E


# ---------------------------------------------------------------------------------------
# reported statistics (W) and hypotheses (H, design 4.6): computed only from runs whose S rows passed
def ns(x):
    return float(x) / NS


def rng(v):
    v = [ns(x) for x in v]
    return f"{min(v):+.3f}..{max(v):+.3f}" if v else "n/a"


def mean(v):
    v = [float(x) for x in v]
    return sum(v) / len(v) if v else float("nan")


COMP_KEYS = (("L", ("rrin", "trunc", "mul", "nrr", "TT", "qG", "stale")),
             ("Rr", ("mul", "TT", "carriage", "nrr", "window", "uncal")),
             ("D", ("smooth", "trunc", "mul", "nrrS", "qS", "TT", "stale", "base")))


def stats_lines(cfg, items):
    """items: [(rep, Eval)]; per-component ranges over all calibrated Follow_Ups (steps >= 3) of all reps."""
    out = []
    fus = [(rep, f) for rep, E in items for f in E.fus if "skip" not in f]
    cal = [f for r, f in fus if f["nrr_valid"]]
    unc = [f for r, f in fus if not f["nrr_valid"]]
    ivs = [x for rep, E in items for x in E.iv[2:]]
    lag = [f["sF"] - f["s2"] for r, f in fus]
    res = [f["Res_s"] for r, f in fus]
    out.append(f"{cfg} (reps {[r for r, E in items]}): {len(fus)} Follow_Ups ({len(cal)} calibrated, {len(unc)} uncalibrated); "
               f"Res {rng(res)} ns; Follow_Up lag at the slave {rng(lag)} ns")
    for label, sub in (("calibrated", cal), ("uncalibrated", unc)):
        if not sub:
            continue
        out.append(f"  epsilon ({label}) {rng([f['eps'] for f in sub])} ns: E_link {rng([f['E_link'] for f in sub])}, "
                   f"E_res {rng([f['E_res'] for f in sub])}, E_ldn {rng([f['E_ldn'] for f in sub])}, E_qG {rng([f['E_qG'] for f in sub])}")
    if cal:
        for grp, keys in COMP_KEYS:
            name = {"L": "E_link", "Rr": "E_res", "D": "E_ldn"}[grp]
            out.append(f"    {name}: " + ", ".join(f"{k} {rng([f[grp][k] for f in cal])}" for k in keys
                                                    if any(f[grp][k] != 0 for f in cal)) or f"    {name}: all components 0")
    if ivs:
        out.append(f"  after step (k >= 3): e+ {rng([x['e_plus'] for x in ivs])} ns = eps {rng([x['eps'] for x in ivs])} "
                   f"+ lag {rng([x['lam'] for x in ivs])} + round-up {rng([x['rho'] for x in ivs])}")
        bt = [x["max_between"] for x in ivs if x["max_between"] is not None]
        em = [x["e_minus_next"] for x in ivs if x["e_minus_next"] is not None]
        out.append(f"  between steps (k >= 3): max |e| {max(ns(b) for b in bt) if bt else float('nan'):.3f} ns; "
                   f"end of interval e- {rng(em)} ns")
    for rep, E in items[:1]:
        t = E.iv[:3]
        out.append("  transient (rep %d): " % rep + "; ".join(
            f"step {i + 1}: e+ {ns(x['e_plus']):+.3f}, max between {ns(x['max_between'] or 0):.3f}, e- {ns(x['e_minus_next'] or 0):+.3f} ns"
            for i, x in enumerate(t)))
    return out


def hypotheses(cfg, items):
    """H rows (reported, not gating): (id, statement, predicted, observed, held)."""
    c = RR.CLOCKS[cfg]
    go, so = c["gm"]["osc"], c["sl"]["osc"]
    out = []
    const = not go["stair"] and not go["rw"] and not so["stair"] and not so["rw"] and go["kind"] == so["kind"] == "drift"
    LS, LG = so["L"], go["L"]
    for rep, E in items:
        iv, fus = E.iv, [f for f in E.fus if "skip" not in f]
        if len(iv) < 4:
            continue
        dy = (so["ppm"] - go["ppm"]) * 1e-6
        if const and dy != 0:
            ds = fus[1]["sF"] - fus[0]["sF"]
            pred = dy * ds
            obs = iv[0]["e_minus_next"] - iv[0]["e_plus"]
            out.append(("H1a", f"{cfg}-{rep}: compensation 0 until step 2, so the error grows at y_S - y_G between steps 1 and 2",
                        f"{pred / NS:+.3f} ns", f"{ns(obs):+.3f} ns", abs(obs - pred) <= 2 * LS + 1e-3 * abs(pred)))
            pl = dy * (fus[1]["sF"] - fus[1]["s2"])
            out.append(("H1b", f"{cfg}-{rep}: lag term of step 2 = (y_S - y_G) x Follow_Up lag", f"{pl / NS:+.3f} ns",
                        f"{ns(iv[1]['lam']):+.3f} ns", abs(iv[1]["lam"] - pl) <= 2 * LS + 1e-3 * abs(pl)))
        if const:
            worst, held = 0, True
            for k in range(3, len(iv) - 1):
                x, f0, f1 = iv[k], fus[k - 1], fus[k]
                if x["e_minus_next"] is None:
                    continue
                d_end = x["e_minus_next"] - x["e_plus"]
                bound = abs(f1["eps"] - f0["eps"]) * 1.5 + 2 * LS + 2 * LG
                worst = max(worst, abs(d_end) - bound)
                held &= abs(d_end) <= bound
            out.append(("H1c", f"{cfg}-{rep}: from step 3, between-step drift |delta| <= 1.5 |eps_k - eps_k-1| + 2 L_S + 2 L_G (leakage + quantization)",
                        "<= 0 ns excess", f"max excess {ns(worst):+.3f} ns", held))
        if go["stair"] and not so["stair"] and go["stair"][1] != 0:
            D = go["stair"][1] / (RR.STAIR_DT / 1e12) * 1e-6        # 1/s
            T = 0.125
            cs = [ns(x["e_minus_next"]) / (D * T * T * 1e9) for x in iv[3:-1] if x["e_minus_next"] is not None]
            cm = mean(cs)
            out.append(("H2", f"{cfg}-{rep}: GM ramp D = {D * 1e6:g} ppm/s: end-of-interval error of order D T^2 = {D * T * T * 1e9:.3f} ns",
                        "coefficient of order 1", f"mean coefficient {cm:+.3f} (range {min(cs):+.3f}..{max(cs):+.3f})", 0.1 <= abs(cm) <= 10))
        unc = [f for f in fus if not f["nrr_valid"]]
        if go["ppm"] != 0 and not go["stair"] and unc:
            pred = mean([-go["ppm"] * 1e-6 * f["Res_s"] for f in unc])
            obs = mean([f["eps"] for f in unc])
            out.append(("H6a", f"{cfg}-{rep}: uncalibrated Follow_Ups: eps ~ -y_G x Res", f"{pred / NS:+.3f} ns (mean)", f"{obs / NS:+.3f} ns (mean)",
                        abs(obs - pred) <= 0.02 * abs(pred) + 2 * LG + 2 * NS))
            k = next(i for i, f in enumerate(fus) if f["nrr_valid"])
            if 0 < k < len(iv):
                y = go["ppm"] * 1e-6
                exc = iv[k]["max_between"]
                predx = abs(y) * mean([f["Res_s"] for f in unc])
                out.append(("H6b", f"{cfg}-{rep}: first calibrated step (Follow_Up {fus[k]['seq']}): one-interval excursion of order y_G x Res",
                            f"{predx / NS:.3f} ns", f"{ns(exc or 0):.3f} ns", 0.2 * predx <= (exc or 0) <= 5 * predx + 4 * LS))
    return out


STAGES = {
    "A": ["M2S6U-A1", "M2S6U-A2", "M2S6U-A3", "M2S6U-A4", "M2S6U-A5"],
    "B": ["M2S6U-B-m100", "M2S6U-B-m10", "M2S6U-B-m1", "M2S6U-B-p1", "M2S6U-B-p10", "M2S6U-B-p100",
          "M2S6-B-p100", "M2S6-B-m100", "M2S6-B-p10"],
    "C": ["M2S6U-Q10", "M2S6U-C-sp100", "M2S6U-C-sm100", "M2S6U-C-a", "M2S6U-C-b", "M2S6U-C-r001", "M2S6U-C-r01", "M2S6U-C-r1",
          "M2S6U-C-rs1", "M2S6U-C-off", "M2S6U-C-1ps", "M2S6U-C-1psr", "M2S6-C-a", "M2S6-C-off", "M2S6-C-r1",
          "M2S6-C-FS1", "M2S6-C-FS2", "M2S6-C-FD1", "M2S6-C-FD2"],
    "D": ["M2S6-D-frag", "M2S6-D-load", "M2S6-D-load-harq16", "M2S6-D-nwpd025", "M2S6-D-nwpd8", "M2S6-D-slpd0125"],
}


def main():
    runs = sys.argv[1]
    stages = [a for a in sys.argv[2:] if not a.startswith("--")] or list(STAGES)
    rep_path = next((a.split("=", 1)[1] for a in sys.argv[2:] if a.startswith("--report=")), None)
    present = lambda cfg: os.path.isdir(os.path.join(runs, cfg))  # noqa: E731
    report, hyp = [], []
    for st in stages:
        for cfg in STAGES[st]:
            if not present(cfg):
                continue
            items = []
            for rep in RR.CLOCKS[cfg]["reps"]:
                if st == "A":
                    R = RR.Run(runs, cfg, rep)
                    k_rows(R, gm_clocks(R), slave_clocks(R, []), f"{cfg}-{rep}")
                    continue
                rr = []
                E = run_eval(runs, cfg, rep, rr)
                if rr[0][3]:
                    items.append((rep, E))
            if items:
                report += stats_lines(cfg, items)
                hyp += hypotheses(cfg, items)
    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {check}: {detail}" + (f" -- {extra}" if extra else ""))
    print(f"OVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    if rep_path:
        with open(rep_path, "w") as fh:
            fh.write("M2-S6 reported results (not gating; every run listed here passed its S rows)\n\n")
            fh.write("Per-config error components (ns; ranges over all Follow_Ups of all reps)\n")
            fh.write("\n".join(report) + "\n\nHypotheses (design 4.6): id | statement | predicted | observed | held\n")
            for h in hyp:
                fh.write(f"{h[0]} | {h[1]} | {h[2]} | {h[3]} | {'held' if h[4] else 'REFUTED'}\n")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
