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
import ttclock_model as TT  # noqa: E402
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
def tt_maps(R):
    """TT stamps by kind and sequenceId from the TtClock logs (A2; validated by the T rows), or None (A1)."""
    if not R.ttlog:
        return None
    m = {}
    for side, kinds in (("nw", (3, 6)), ("ds", (4, 5))):
        for k in kinds:
            m[k] = {r["seq"]: r["tau"] for r in R.ttlog[side] if r["kind"] == k}
    return {"ds_t2": m[4], "ds_t3": m[5], "nw_t1": m[3], "nw_t4": m[6]}


class Eval:
    """Everything the oracles predict for one run, with the TT timestamp source (A1: simulation time;
    A2: the logged TT stamps, each recomputed by the T rows)."""
    def __init__(self, R, tt=None):
        self.R = R
        tt = tt_maps(R) if tt is None else tt
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
    tm = tt_maps(R)
    for r in [x for x in R.nweng if x["event"] == "measure"]:
        s = int(r["seq"])
        t1, t4 = req[s]["start"], resp[s]["start"]                 # A1: NW-TT timestamps = simulation time
        if tm:                                                      # A2: the NW-TT's measured stamps (T rows)
            t1, t4 = tm["nw_t1"][s], tm["nw_t4"][s]
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
    if R.ttlog:
        t_rows(R, tag)
        tc = tt_components(E)
        nb = sum(1 for x in tc if not x["sum_ok"])
        add(f"T {tag}", f"E_res,TT = sum of the TT components (theta0, osc, w, q) of the NW-TT and DS-TT stamps of the Sync "
            f"({len(tc)} Follow_Ups)", nb == 0 and tc, f"{nb} mismatches")
    report.append((cfg, rep, E, s_ok))
    return E


# ---------------------------------------------------------------------------------------
# rows T (stage E): every TT stamp recomputed from the configuration (ttclock_model), at the PCAP time
# of its event, and used unchanged by the translators and the slave
def t_rows(R, tag):
    conf, sel = R.conf["tt"], RR.C5.sel
    events = {
        ("nw", 1): [f["start"] for f in sel(R.nw1, 1, RR.SYNC, dom=None)],
        ("nw", 3): [f["start"] for f in sel(R.nw1, 2, RR.REQ, dom=None)],
        ("nw", 6): [f["start"] for f in sel(R.nw1, 1, RR.RESP, dom=None)],
        ("nw", 7): [f["end"] for f in sel(R.nw1, 2, RR.REQ, dom=None)],
        ("nw", 9): [f["end"] for f in sel(R.nw1, 1, RR.RESP, dom=None)],
        ("ds", 2): [f["start"] for f in sel(R.ds1, 2, RR.SYNC, dom=None)],
        ("ds", 4): [f["start"] for f in sel(R.ds1, 1, RR.REQ, dom=None)],
        ("ds", 5): [f["start"] for f in sel(R.ds1, 2, RR.RESP, dom=None)],
    }
    for side in ("nw", "ds"):
        p, log = conf[side], R.ttlog[side]
        bad = [r for r in log if r["C"] != TT.clock(p, r["s"]) or r["tau"] != TT.measure(p, r["s"], r["w"])
               or ((p["sigma"] == 0 or r["kind"] in TT.TEST_KINDS) and r["w"] != 0)]
        add(f"T {tag}", f"{side.upper()}-TT: every stamp recomputed from the configuration: C_T(s) and tau = Q(C_T(s) + w) "
            f"({len(log)} stamps; theta0 {p['theta0'] / NS:g} ns, y {p['y']} ppb, D {p['D']} ppb/s, U {p['U'] / 1e9:g} ms, "
            f"sigma {p['sigma'] / NS:g} ns, L {p['L'] / NS:g} ns)", not bad and len(log) > 0, str(bad[:2]))
        for (sd, k), ts in events.items():
            if sd != side:
                continue
            got = sorted(r["s"] for r in log if r["kind"] == k)
            ts = sorted(ts)
            end = R.conf["end"]
            # a frame that starts within the last 10 us of the run is stamped but never completes (no PCAP
            # record); a *_END stamp exists only for completed frames
            ok = got == ts or (got[:len(ts)] == ts and all(x >= end - 10 ** 7 for x in got[len(ts):]) and len(got) - len(ts) <= 1)
            add(f"T {tag}", f"{side.upper()}-TT {TT.KINDS[k]}: stamped at the PCAP first/last bit of every such event ({len(got)})", ok,
                f"{len(got)} stamps vs {len(ts)} events")
    # values used: DS-TT log TSi/TSe, NW-TT engine t1/t4, what the slave received (wire: whole ns)
    nwk = {(r["kind"], r["s"]): r["tau"] for r in R.ttlog["nw"]}
    dsk = {(r["kind"], r["s"]): r["tau"] for r in R.ttlog["ds"]}
    nws, dss = {f["seq"]: f for f in sel(R.nw1, 1, RR.SYNC)}, {f["seq"]: f for f in sel(R.ds1, 2, RR.SYNC)}
    nb = n = 0
    for r in R.dslog:
        if r["event"] != "corrected":
            continue
        q = int(r["seq"])
        n += 1
        if int(r["TSi"]) != nwk.get((1, nws[q]["start"])) or int(r["TSe"]) != dsk.get((2, dss[q]["start"])):
            nb += 1
    add(f"T {tag}", f"DS-TT correction used TSi = NW-TT stamp and TSe = DS-TT stamp of the Sync ({n} Follow_Ups)", nb == 0 and n > 0, f"{nb}")
    tm = tt_maps(R)
    nb = n = 0
    for r in R.nweng:
        if r["event"] == "measure":
            n += 1
            q = int(r["seq"])
            if int(r["t1"]) != tm["nw_t1"][q] or int(r["t4"]) != tm["nw_t4"][q]:
                nb += 1
    add(f"T {tag}", f"NW-TT link delay used t1 / t4 = NW-TT stamps ({n} exchanges)", nb == 0 and n > 0, f"{nb}")
    nb = n = 0
    for f in sel(R.sl, 1, RR.RESP, RR.RFU, dom=None):
        if f["g"]:
            q = f["g"]["seq"]
            v = tm["ds_t2"].get(q) if f["g"]["type"] == RR.RESP else tm["ds_t3"].get(q)
            n += 1
            if v is None or M.inet_read_timestamp(*f["g"]["ts"]) != M.inet_read_timestamp(*M.inet_write_timestamp(v)):
                nb += 1
    add(f"T {tag}", f"slave received the DS-TT stamps t2 / t3 (wire, whole ns) ({n} frames)", nb == 0 and n > 0, f"{nb}")


def tt_components(E):
    """E_res,TT, E_link,TT and E_ldn,TT split into theta0 / osc / noise / quantization (design 2.3, 4.4)."""
    R = E.R
    if not R.ttlog:
        return []
    conf = R.conf["tt"]
    byk = {side: {(r["kind"], r["s"]): r for r in R.ttlog[side]} for side in ("nw", "ds")}
    out = []
    for f in E.fus:
        if "skip" in f:
            continue
        ri, re_ = byk["nw"][(1, f["si"])], byk["ds"][(2, f["se"])]
        ci = TT.components(conf["nw"], f["si"], ri["w"])
        ce = TT.components(conf["ds"], f["se"], re_["w"])
        res = {k: f["r"] * (ce[k] - ci[k]) for k in ci}
        out.append({"seq": f["seq"], "nrr_valid": f["nrr_valid"], "res": res, "eps": f["eps"], "link_TT": f["L"]["TT"], "ldn_TT": f["D"]["TT"],
                    "sum_ok": sum(res.values()) == f["Rr"]["TT"]})
    return out


# ---------------------------------------------------------------------------------------
# rows N (stage F, design 6.4): each negative control fails exactly its predicted rows, with an exact
# per-Follow_Up signature computed by the oracles
def n_oracle_sign(runs):
    """N-oracleSign (oracle sensitivity): O1 given the wrong sign of the GM drift must fail the K rows of
    stage A1 (GM clock samples, POT on the wire, sign row)."""
    R = RR.Run(runs, "M2S6U-A1", 0)
    conf = dict(R.conf)
    g = dict(conf["gm"])
    g["osc"] = dict(g["osc"], ppm=-g["osc"]["ppm"])
    conf["gm"] = g
    R.conf = conf
    before = len(rows)
    k_rows(R, gm_clocks(R), slave_clocks(R, []), "M2S6U-A1-0 (GM drift sign inverted)")
    mine = rows[before:]
    del rows[before:]
    failed = sorted({r[1].split(":")[0].split(" (")[0] for r in mine if not r[2]})
    add("N M2S6U-A1-0 oracleSign", f"O1 with the GM drift sign inverted fails the GM K rows: {failed} "
        f"({sum(1 for r in mine if not r[2])} of {len(mine)} rows fail; slave rows unaffected)",
        any("gm.clock timeChanged" in f for f in failed) and any("GM POT" in f for f in failed)
        and all(r[2] for r in mine if "slave" in r[1].split(":")[0]))


def row_key(r):
    fam, d = r[0].split()[0], r[1]
    if fam == "E":
        return "E " + d.split(":")[0]
    if fam == "R":
        return "R " + d.split()[0].rstrip(":")
    if fam == "T":
        return "T " + " ".join(d.split()[:4])
    return fam


N_EXPECT = {
    "M2S6U-F-rrIgnore": {"E C2 cf", "E C1 eps"},
    "M2S6-F-rrIgnore": {"E C2 cf", "E C1 eps"},
    "M2S6U-F-rrTwice": {"E C2 cf", "E C1 eps"},
    "M2S6U-F-nrrInvert": {"R rr_out", "R direction"},
    "M2S6U-F-nrrStale": {"R rr_out", "R direction"},
    "M2S6U-F-lupLocal": {"E C2 cf", "E C1 eps"},
    "M2S6U-F-domain": {"T DS-TT correction used TSi", "T E_res,TT = sum of"},
    "M2S6U-F-servoNoRate": {"S"},
    "M2S6U-F-servoNegRate": {"S"},
}
N_SERVO = {"M2S6U-F-servoNoRate": "testNoRate", "M2S6U-F-servoNegRate": "testNegRate"}


def n_rows(runs, cfg, report):
    rep = 0
    before = len(rows)
    R = RR.Run(runs, cfg, rep)
    E = Eval(R)
    k_rows(R, E.gnc, None, f"{cfg}-{rep}")
    s_rows(E, f"{cfg}-{rep}")
    r_rows(E, f"{cfg}-{rep}")
    e_rows(E, f"{cfg}-{rep}")
    if R.ttlog:
        t_rows(R, f"{cfg}-{rep}")
        tc = tt_components(E)
        nb = sum(1 for x in tc if not x["sum_ok"])
        add(f"T {cfg}-{rep}", "E_res,TT = sum of the TT components (theta0, osc, w, q) of the NW-TT and DS-TT stamps of the Sync", nb == 0)
    mine = rows[before:]
    del rows[before:]
    failed = {row_key(r) for r in mine if not r[2]}
    exp = N_EXPECT[cfg]
    tag = f"N {cfg}-{rep}"
    add(tag, f"fails exactly its predicted rows {sorted(exp)} ({len(mine)} rows evaluated)", failed == exp, f"failed {sorted(failed)}")
    fus = [f for f in E.fus if "skip" not in f]
    dsc = {int(x["seq"]): x for x in R.dslog if x["event"] == "corrected"}
    nwc = {int(x["seq"]): x for x in R.nwlog if x["event"] == "corrected"}
    y = R.conf["gm"]["osc"]["ppm"] * 1e-6
    if cfg.endswith("rrIgnore") or cfg.endswith("rrTwice"):
        nb, d = 0, []
        for f in fus:
            R_, r_e = f["Rm"], KM.from_double(f["rr_out"])
            exp_add = R_ if cfg.endswith("rrIgnore") else KM.mul_round(KM.mul_round(R_, r_e), r_e)
            if f["cf2"] - f["cf1"] != exp_add:
                nb += 1
            d.append(f["cf2"] - f["cf1"] - KM.mul_round(R_, r_e))
        add(tag, f"signature: cf2 - cf1 = {'Res (r = 1)' if cfg.endswith('rrIgnore') else 'r (x) (r (x) Res)'} for every Follow_Up ({len(fus)}); "
            f"offset vs the correct composition {rng(d)} ns (predicted {'-' if cfg.endswith('rrIgnore') else '+'}y_G x Res = "
            f"{rng([(-y if cfg.endswith('rrIgnore') else y) * f['Rm'] for f in fus if f['nrr_valid']])} ns for calibrated)", nb == 0)
        if cfg == "M2S6-F-rrIgnore":
            # H5 (reported): with r ignored the rate term of every Follow_Up is (1 - rho_res) Res ~ -y_G Res
            cal = [f for f in fus if f["nrr_valid"]]
            obs = mean([float(f["eps"]) for f in cal])
            report.append(("H5", f"{cfg}-0: the DS-TT ignoring rr makes eps ~ -y_G x Res for every calibrated Follow_Up",
                           f"{mean([-y * f['Res_s'] for f in cal]) / NS:+.3f} ns (mean)", f"{obs / NS:+.3f} ns (mean)",
                           abs(obs - mean([-y * f["Res_s"] for f in cal])) <= 0.02 * abs(y) * mean([f["Res_s"] for f in cal]) + 2 * NS, "1/1"))
    elif cfg.endswith("nrrInvert") or cfg.endswith("nrrStale"):
        meas = [x for x in R.nweng if x["event"] == "measure"]
        nb = 0
        for q, x in nwc.items():
            ex = [m for m in meas if int(m["t"]) < int(x["t"])][-1]
            e = int(ex["nrrQ63"])
            if cfg.endswith("nrrInvert"):
                inv = KM.from_double(1.0 / KM.to_double(e))
                expv = KM.to_double(KM.product(KM.from_double(float(x["rrIn"])), inv))
            else:
                expv = float(x["rrIn"])
            nb += float(x["rrOut"]) != expv
        rate = [f["Rr"]["carriage"] + f["Rr"]["nrr"] + f["Rr"]["window"] + f["Rr"]["uncal"] for f in fus if f["nrr_valid"]]
        pred = "-2 y_G x Res" if cfg.endswith("nrrInvert") else "-y_G x Res"
        add(tag, f"signature: rr_out = rr_in x {'1/nRR' if cfg.endswith('nrrInvert') else '1'} for every Follow_Up ({len(nwc)}); rate term "
            f"E_res,rate {rng(rate)} ns (predicted {pred} = "
            f"{rng([(-2 if cfg.endswith('nrrInvert') else -1) * y * f['Res_s'] for f in fus if f['nrr_valid']])} ns)", nb == 0)
    elif cfg.endswith("lupLocal"):
        meas = [x for x in R.nweng if x["event"] == "measure"]
        nb, d = 0, []
        for f in fus:
            x = nwc[f["seq"]]
            ex = [m for m in meas if int(m["t"]) < int(x["t"])][-1]
            exp_add = KM.mul_round(KM.div_round(f["lup"], int(ex["nrrQ63"])), KM.from_double(float(x["rrIn"])))
            nb += f["cf1"] != exp_add
            d.append(f["cf1"] - f["add_link"])
        add(tag, f"signature: cf1 = rr_in (x) (Lup / nRR) for every Follow_Up ({len(fus)}); offset vs the correct composition "
            f"{', '.join(sorted({f'{v} ps' for v in d}))} (predicted -y_G x Lup = {-y * fus[-1]['lup']:.1f} ps)", nb == 0)
    elif cfg.endswith("domain"):
        nws = {f["seq"]: f for f in RR.C5.sel(R.nw1, 1, RR.SYNC)}
        nb = sum(1 for q, x in dsc.items() if int(x["TSi"]) != nws[q]["start"])
        tt = R.conf["tt"]
        cal1 = next((f["seq"] for f in fus if f["nrr_valid"]), None)
        st = [x["e_plus"] for x in E.iv[2:] if x["seq"] != cal1 and any(f["seq"] == x["seq"] and f["nrr_valid"] for f in fus)]
        add(tag, f"signature: TSi = simulation time for every Follow_Up ({len(dsc)}); steady e+ {mean(st) / NS:+.3f} ns = theta_DS "
            f"({tt['ds']['theta0'] / NS:g} ns) instead of Delta theta ({(tt['ds']['theta0'] - tt['nw']['theta0']) / NS:g} ns)",
            nb == 0 and abs(mean(st) - tt["ds"]["theta0"]) <= 4 * NS)
    elif cfg in N_SERVO:
        conf = dict(R.conf)
        conf["sl"] = dict(conf["sl"], servo=N_SERVO[cfg])
        R.conf = conf
        E2 = Eval(R)
        res = O5.compare(E2.o5, R, R.sln)
        ok = all(v[0] for v in res.values())
        d = [x["e_minus_next"] - x["e_plus"] for x in E2.iv[3:-1] if x["e_minus_next"] is not None]
        dy = (R.conf["sl"]["osc"]["ppm"] - R.conf["gm"]["osc"]["ppm"]) * 1e-6
        k = 1 if N_SERVO[cfg] == "testNoRate" else 2
        pred = k * dy * 125e9
        add(tag, f"signature: O5 with the TEST servo model reproduces every recorded slave value; between-step drift {rng(d)} ns "
            f"(predicted {k} (y_S - y_G) x T = {pred / NS:+.0f} ns)", ok and all(abs(v - pred) <= 0.02 * abs(pred) for v in d),
            "; ".join(f"{a}: {b[2]}" for a, b in res.items() if not b[0]))


# ---------------------------------------------------------------------------------------
# R-INET cross-check (design 6.3; reported, not gating except the GM clock row that validates O1 there)
def slave_error_samples(V, net, sln, gnc, t_from):
    """e(s) = C_S(s) - C_G(s) at the 1 ms samples from t_from (recorded slave clock; O1 GM clock). At a
    1 ms time that coincides with a step the last recorded value is used."""
    last = {}
    for t, v in V.get((f"{net}.{sln}.clock", "timeChanged:vector"), []):
        if t % MC.MS == 0:
            last[t] = M_ps(v)
    gm = dict(gnc.C.ms_values)
    return [last[t] - gm[t] for t in sorted(last) if t >= t_from and t in gm]


def r_inet(runs, report):
    cfg = "M2S6U-R-inet"
    net = "M2S6InetBridgeTest"
    V = RR.read_vectors(os.path.join(runs, cfg, cfg, "0.vec"))
    conf = RR.CLOCKS[cfg]
    gnc = MC.NodeClocks(conf["gm"], conf["end"], None, "gm")
    MC.replay(gnc)
    fixed, alt = MC.predicted_samples(gnc, gnc.C, True)
    ok, n, bad = MC.compare_samples(V.get((f"{net}.gm.clock", "timeChanged:vector"), []), fixed, alt)
    add(f"K {cfg}-0", f"GM clock samples = O1 in the INET bridge network ({n} samples)", ok, str(bad))
    e_r = slave_error_samples(V, net, "slave", gnc, 2 * RR.S)
    lines = [f"{cfg} (cross-check, not ground truth): slave error e(s) = C_S - C_G at the 1 ms samples from 2 s: "
             f"{rng(e_r)} ns, mean {mean(e_r) / NS:+.3f} ns, max |e| {max(abs(x) for x in e_r) / NS:.3f} ns ({len(e_r)} samples)"]
    ref = "M2S6U-C-a"
    if os.path.isdir(os.path.join(runs, ref)):
        R = RR.Run(runs, ref, 0)
        g2 = gm_clocks(R)
        e_t = slave_error_samples(R.vec, R.net, R.sln, g2, 2 * RR.S)
        lines.append(f"  {ref} (the M2-S6 translators, A1, same clocks and traffic): {rng(e_t)} ns, mean {mean(e_t) / NS:+.3f} ns, "
                     f"max |e| {max(abs(x) for x in e_t) / NS:.3f} ns ({len(e_t)} samples)")
    comp = [(t, float(v)) for t, v in V.get((f"{net}.slave.clock", "oscillatorCompensationChanged:vector"), [])][1:]
    lines.append(f"  R-INET slave compensation from step 3: {min(c for t, c in comp[2:]):+.6f}..{max(c for t, c in comp[2:]):+.6f} ppm "
                 f"({len(comp)} steps; the true ratio is +200.02 ppm)")
    report += lines


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
    cal_seq = {(rep, f["seq"]) for rep, E in items for f in E.fus if "skip" not in f and f["nrr_valid"]}
    first_cal = {}
    for rep, E in items:
        c1 = [f["seq"] for f in E.fus if "skip" not in f and f["nrr_valid"]]
        first_cal[rep] = c1[0] if c1 else None
    ivs_all = [(rep, x) for rep, E in items for x in E.iv[2:]]
    # steady state: calibrated intervals after the first calibrated step (whose interval carries the H6b transition)
    ivs = [x for rep, x in ivs_all if (rep, x["seq"]) in cal_seq and x["seq"] != first_cal[rep]]
    ivs_t = [x for rep, x in ivs_all if x["seq"] == first_cal[rep]]
    ivs_u = [x for rep, x in ivs_all if (rep, x["seq"]) not in cal_seq]
    lag = [f["sF"] - f["s2"] for r, f in fus]
    res = [f["Res_s"] for r, f in fus]
    out.append(f"{cfg} (reps {[r for r, E in items]}): {len(fus)} Follow_Ups ({len(cal)} calibrated, {len(unc)} uncalibrated); "
               f"Res {rng(res)} ns; Follow_Up lag at the slave {rng(lag)} ns")
    from collections import Counter
    inv = Counter(r["note"] for rep, E in items for r in E.R.nwlog if r["event"] == "invalid")
    if inv:
        out.append(f"  NW-TT INVALID Follow_Ups (discarded by the DS-TT, no step): {dict(inv)} over {len(items)} reps")
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
    for label, sub in (("calibrated, steady state", ivs), ("first calibrated step: transition", ivs_t), ("uncalibrated", ivs_u)):
        if not sub:
            continue
        out.append(f"  after step k >= 3 ({label}): e+ {rng([x['e_plus'] for x in sub])} ns = eps {rng([x['eps'] for x in sub])} "
                   f"+ lag {rng([x['lam'] for x in sub])} + round-up {rng([x['rho'] for x in sub])}")
        bt = [x["max_between"] for x in sub if x["max_between"] is not None]
        em = [x["e_minus_next"] for x in sub if x["e_minus_next"] is not None]
        out.append(f"  between steps after step k >= 3 ({label}): max |e| {max(ns(b) for b in bt) if bt else float('nan'):.3f} ns; "
                   f"end of interval e- {rng(em)} ns")
    ttc = [x for rep, E in items for x in tt_components(E) if x["nrr_valid"]]
    if ttc:
        out.append("  TT terms (calibrated): E_res,TT = r x [(TSe - s_e) - (TSi - s_i)]: " +
                   ", ".join(f"{k} {rng([x['res'][k] for x in ttc])}" for k in ("theta0", "osc", "w", "q")) +
                   f"; E_link,TT {rng([x['link_TT'] for x in ttc])}; E_ldn,TT {rng([x['ldn_TT'] for x in ttc])}")
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
        if go["stair"] and not so["stair"] and go["stair"][1] != 0 and \
                abs(go["stair"][1] / (RR.STAIR_DT / 1e12) * 1e-6) * 0.125 ** 2 * 1e12 >= 4 * max(LS, LG):
            # evaluated only where D T^2 is at least 4 ticks (below that the coefficient is quantization noise)
            D = go["stair"][1] / (RR.STAIR_DT / 1e12) * 1e-6        # 1/s
            T = 0.125
            cs = [ns(x["e_minus_next"]) / (D * T * T * 1e9) for x in iv[3:-1] if x["e_minus_next"] is not None]
            cm = mean(cs)
            out.append(("H2", f"{cfg}-{rep}: GM ramp D = {D * 1e6:g} ppm/s: end-of-interval error of order D T^2 = {D * T * T * 1e9:.3f} ns",
                        "coefficient of order 1", f"mean coefficient {cm:+.3f} (range {min(cs):+.3f}..{max(cs):+.3f})", 0.1 <= abs(cm) <= 10))
        tt = c["tt"]
        if tt and all(tt[k]["y"] == 0 and tt[k]["D"] == 0 and tt[k]["sigma"] == 0 and tt[k]["L"] == 1 for k in tt):
            dth = tt["ds"]["theta0"] - tt["nw"]["theta0"]
            cal1 = next((f["seq"] for f in fus if f["nrr_valid"]), None)
            st = [x["e_plus"] for x in iv[2:] if x["seq"] != cal1 and any(f["seq"] == x["seq"] and f["nrr_valid"] for f in fus)]
            out.append(("H3", f"{cfg}-{rep}: constant Delta theta = theta0_DS - theta0_NW = {dth / NS:g} ns: steady-state e+ = +Delta theta "
                        "(the common part cancels; within 2 L_S + 2 ns)", f"{dth / NS:+.3f} ns",
                        f"{mean(st) / NS:+.3f} ns (mean of {len(st)}; {rng(st)})", abs(mean(st) - dth) <= 2 * LS + 2 * NS))
        if tt and any(tt[k]["sigma"] > 0 for k in tt):
            sg = tt["nw"]["sigma"]
            cal1 = next((f["seq"] for f in fus if f["nrr_valid"]), None)
            epsv = [float(f["eps"]) for f in fus if f["nrr_valid"] and f["seq"] != cal1]
            st = TT.ci95_std(epsv)
            if st:
                out.append(("H4a", f"{cfg}-{rep}: white TT noise sigma = {sg / NS:g} ns: std(eps) = sqrt(2) sigma (TSi, TSe; design 4.6)",
                            f"{2 ** 0.5 * sg / NS:.3f} ns", f"{st[1] / NS:.3f} ns (95 % CI {st[2] / NS:.3f}..{st[3] / NS:.3f}, n {st[4]})",
                            st[2] <= 2 ** 0.5 * sg <= st[3]))
            # steady state only: calibrated intervals after the first calibrated step, of normal length (< 1.5 T)
            calset = {f["seq"] for f in fus if f["nrr_valid"] and f["seq"] != cal1}
            sF = {f["seq"]: f["sF"] for f in fus}
            em = [float(x["e_minus_next"]) for i, x in enumerate(iv[:-1]) if x["e_minus_next"] is not None and x["seq"] in calset
                  and iv[i + 1]["seq"] in calset and sF[iv[i + 1]["seq"]] - sF[x["seq"]] < 1.5 * 125 * 10 ** 9]
            st2 = TT.ci95_std(em)
            if st and st2:
                out.append(("H4b", f"{cfg}-{rep}: end-of-interval error e- ~ 2 eps_k - eps_k-1: std(e-) = sqrt(5) std(eps)",
                            f"{5 ** 0.5 * st[1] / NS:.3f} ns", f"{st2[1] / NS:.3f} ns (95 % CI {st2[2] / NS:.3f}..{st2[3] / NS:.3f})",
                            st2[2] <= 5 ** 0.5 * st[1] <= st2[3]))
        if c["notes"] == "fault":
            T = 125 * 10 ** 9
            longs = [(i, x) for i, x in enumerate(iv[:-1]) if fus[i + 1]["sF"] - fus[i]["sF"] > 1.5 * T]
            for i, x in longs:
                dur = fus[i + 1]["sF"] - fus[i]["sF"]
                d_end = x["e_minus_next"] - x["e_plus"]
                ref = [iv[k]["e_minus_next"] - iv[k]["e_plus"] for k in range(3, len(iv) - 1)
                       if k != i and iv[k]["e_minus_next"] is not None and fus[k + 1]["sF"] - fus[k]["sF"] < 1.5 * T]
                bound = 2 * max(abs(v) for v in ref) + 2 * LS + 2 * LG
                out.append(("H7", f"{cfg}-{rep}: affected interval after Follow_Up {x['seq']} ({dur / 1e9:.3f} ms without a step): "
                            "drift over the long interval <= 2 x the largest normal-interval drift + 2 L_S + 2 L_G",
                            f"<= {bound / NS:.3f} ns", f"{ns(d_end):+.3f} ns (max |e| {ns(x['max_between']):.3f} ns)", abs(d_end) <= bound))
        if const and LS > 1 and len(iv) > 10 and not tt:   # tick resets occur only for L_S > 1 ps (K7); TT error absent
            ds = [iv[k]["e_minus_next"] - iv[k]["e_plus"] for k in range(9, len(iv) - 1) if iv[k]["e_minus_next"] is not None]
            out.append(("H8", f"{cfg}-{rep}: K7 tick resets bias the raw time base by about +L_S/2 per interval, so the mean "
                        f"between-step drift (calibrated intervals) is +L_S/2 within L_S/4 (L_S = {LS / NS:g} ns)",
                        f"+{LS / 2 / NS:.3f} ns", f"{mean(ds) / NS:+.3f} ns (mean of {len(ds)})",
                        abs(mean(ds) - LS / 2) <= LS / 4))
        unc = [f for f in fus if not f["nrr_valid"]]
        if go["ppm"] != 0 and not go["stair"] and unc and not tt:     # H6: translators on ideal 5G time
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


def aggregate(hs, cfg):
    """One line per hypothesis and config: held in n of N reps, predicted/observed of every rep."""
    by = {}
    for h in hs:
        by.setdefault(h[0], []).append(h)
    out = []
    for hid, lst in by.items():
        stmt = lst[0][1].split(": ", 1)[1]
        pred = sorted({h[2] for h in lst})
        obs = [h[3] for h in lst]
        n = sum(1 for h in lst if h[4])
        out.append((hid, f"{cfg} ({len(lst)} reps): {stmt}", " / ".join(pred), " / ".join(obs) if len(obs) <= 3 else
                    f"{obs[0]} ... {obs[-1]} ({len(obs)} values)", n == len(lst), f"{n}/{len(lst)}"))
    return out


STAGES = {
    "A": ["M2S6U-A1", "M2S6U-A2", "M2S6U-A3", "M2S6U-A4", "M2S6U-A5"],
    "B": ["M2S6U-B-m100", "M2S6U-B-m10", "M2S6U-B-m1", "M2S6U-B-p1", "M2S6U-B-p10", "M2S6U-B-p100",
          "M2S6-B-p100", "M2S6-B-m100", "M2S6-B-p10"],
    "C": ["M2S6U-Q10", "M2S6U-C-sp100", "M2S6U-C-sm100", "M2S6U-C-a", "M2S6U-C-b", "M2S6U-C-r001", "M2S6U-C-r01", "M2S6U-C-r1",
          "M2S6U-C-rs1", "M2S6U-C-off", "M2S6U-C-1ps", "M2S6U-C-1psr", "M2S6-C-a", "M2S6-C-off", "M2S6-C-r1",
          "M2S6-C-FS1", "M2S6-C-FS2", "M2S6-C-FD1", "M2S6-C-FD2"],
    "D": ["M2S6-D-frag", "M2S6-D-load", "M2S6-D-load-harq16", "M2S6-D-nwpd025", "M2S6-D-nwpd8", "M2S6-D-slpd0125",
          "M2S6-D-FS2late", "M2S6-D-FD1late"],
    "E": ["M2S6U-E-th10", "M2S6U-E-th100", "M2S6U-E-th1000", "M2S6U-E-y", "M2S6U-E-yfree", "M2S6U-E-D", "M2S6U-E-sig1",
          "M2S6U-E-sig10", "M2S6U-E-sig100", "M2S6U-E-L8", "M2S6-E-all", "M2S6-E-all-load"],
    "F": list(N_EXPECT),
    "R": [],
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
            if st == "F":
                n_rows(runs, cfg, hyp)
                continue
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
                hyp += aggregate(hypotheses(cfg, items), cfg)
    if "F" in stages and present("M2S6U-A1"):
        n_oracle_sign(runs)
    if "R" in stages and present("M2S6U-R-inet"):
        r_inet(runs, report)
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
                fh.write(f"{h[0]} | {h[1]} | {h[2]} | {h[3]} | {'held' if h[4] else 'REFUTED'} ({h[5]})\n")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
