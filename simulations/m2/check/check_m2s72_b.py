#!/usr/bin/env python3
"""M2-S7.2a stage 4, Block B (migration/m2-s7.2a-design.md rev. 2.1, 2, 4.1-4.3, 8.2, 8.3): exact per-slave and
cross-slave timing correctness with several UEs.

    check_m2s72_b.py <results dir> [config regex]     -> prints the Checkpoint 2 record (m2s72.sh b writes b-check.txt)

Runs (m2s72.sh b): M2S72-B-<opt>-<clk>-n<N>, opt q0 (Q-0) / qdu (Q-d (UM), experimental comparison), clk ideal / Ca /
Eall (E-all TT clocks, DS-TT k per D-13), N = 2, 4 (correctness) and 1 (I-5 reference), seeds 0-4, 12 s; and the
config control M2S72-BN-theta1 (seed 0). Every run carries M2S72-SL, the learning recorders and the eventlog.
The earlier oracles are called unchanged: check_m2s6 (O1/O5/O3/O4 and the K/S/R/E/T rows) through the per-UE adapter
m2s72_s6.S6View; check_m2s72_f0 / check_m2s72_f0r2 (F0 rows). Integer ps / Fractions; no tolerance anywhere.

Rows (one per run, or per run and pair; details list every failure):
  F0     F0-1, F0-2 (= I-2), F0-3, F0-4, F0-5, F0-6, F0-8 of Checkpoint 1 rev. 2 in every run, and F0-7d: the
         UPF-internal delays from the run's own eventlog, 0 ps in both directions
  I-1    per DS-TT k: every corrected Follow_Up has exactly one syncTx row of its own Sync in DS-TT k's log, the same
         syncFrameId and TSe, and TSe = DS-TT k's own egress stamp of that Sync (A1: PCAP first bit; A2: TT log)
  I-3    every Follow_Up slave k received carries the correctionField of DS-TT k's own cfOut (wire encoding)
  I-4    distinct DS-TT ttIds and Pdelay clockIdentities (recorded parameters), distinct slave gPTP clockIdentities
         (Pdelay_Req on the wire), distinct NR MAC node ids and station MACs; the recorded RNG mapping (talker[k]
         oscillator -> RNG 2k, dsTt[k] TT clock -> RNG 2k+1, k >= 1; num-rngs = 2N); E-all: DS-TT 1's noise draws
         are the same sequence at N = 2 and N = 4 (its own stream)
  M2     per slave k: every M2-S6 row (K GM clocks, S slave = O5, R rate ratios, E C1-C5 closure, T TT stamps,
         E_res,TT = sum of components) exact
  M3     per pair (i, j): at every common 1 ms sample, measured e_i - e_j (recorded slave clocks and GM clock) =
         predicted (O5 slave clocks, O1 GM clock)
  M3d    per pair: e_k(t) = sum of slave k's terms (L.*, Rr.mul, Rr.TT_nw, Rr.TT_ds, Rr.carriage/nrr/window/uncal,
         D.*, qG2, -qG1, lambda, rho, delta(t)) exactly for both slaves; case A (both slaves' last update from the
         same Sync): every term of the cancelling set C (L.*, -qG1, Rr.TT_nw: only common inputs, design 4.2.2) is
         bit-identical for i and j, and the path-specific differences sum to the measured difference exactly;
         case B (different Syncs): the full term-by-term difference sums to it exactly (nothing claimed to cancel)
  M4     Ca / Eall: GM drift attribution: the GM rate (O1, unquantized GM time) over every residence interval of every
         slave is one value rho_G (ConstantDriftOscillator +100 ppm; rho_G is the exact rational rate of its 1 ns tick in
         double arithmetic, reported against 1 + 100 ppm); per slave and Follow_Up the rate part of E_res (carriage + nrr
         + window + uncal) = (r - rho_G) Res; per pair and common Sync its difference = (r - rho_G) (Res_i - Res_j). Eall: TT attribution: per slave the TT stamps recomputed with
         DS-TT k's own D-13 parameters (T rows) and E_res,TT = r (sum C_ds - sum C_nw); per pair and common Sync,
         Rr.TT_nw identical and Rr.TT_ds,i - Rr.TT_ds,j = r [(theta0_i - theta0_j) + d osc + d w + d q], theta0 part =
         r x 100 ns x (i - j) (D-13)
  I-5    slave 0 at N = 2, 4 vs N = 1 (same option, clocks, seed), rule AR: identical DS-TT 0 / slave 0 clock
         parameters; per Follow_Up and term family (L, Rr, D, qG, step) every family whose inputs are identical is
         identical and every changed family has a changed input; delta(t) likewise per sample
Negative controls (each must fail exactly its predicted row families):
  NC-swap   B-q0-Eall-n4 seed 0, slave 1 analysed with DS-TT 2's logs and frames             -> M2, M3
  NC-theta1 M2S72-BN-theta1 (DS-TT 1 theta0 + 1 us), checker keeps the D-13 parameters     -> M2, M4
  NC-cancel B-q0-Eall-n4 seed 0, Rr.mul (and separately qG2) claimed cancelling           -> M3d
  NC-cf     B-q0-Eall-n4 seed 0, copy with DS-TT 1's logged cfOut +1 ps on one Follow_Up    -> M2, M3, I-3
  NC-tse    B-q0-Eall-n4 seed 0, copy with DS-TT 1's logged TSe +1 ps on one Follow_Up      -> M2, I-1, M4
"""
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s6 as K6  # noqa: E402  (unchanged M2-S6 rows and Eval)
sys.argv = _argv
import check_m2s72_f0 as F1  # noqa: E402
import check_m2s72_f0r2 as F2  # noqa: E402
import m2s72_runs as R  # noqa: E402
import m2s72_s6 as V  # noqa: E402
import m2s6_runs as RR  # noqa: E402
import inet_model as M  # noqa: E402
import ttclock_model as TT  # noqa: E402

NS, MS, S = RR.NS, RR.MS, RR.S
OPTS, CLKS, NS_B, REPS = ("q0", "qdu"), ("ideal", "Ca", "Eall"), (2, 4), range(5)
Y_G = Fraction(100, 10 ** 6)                 # GM +100 ppm (C-a)
C_SET = ("L.rrin", "L.trunc", "L.mul", "L.nrr", "L.TT", "L.qG", "L.stale", "qG1", "Rr.TT_nw")
rows = []


def add(row, run, ok, detail):
    rows.append((row, run, "PASS" if ok else "FAIL", detail))


BN_BASE = {"M2S72-BN-theta1": "M2S72-B-q0-Eall-n4"}   # control configs and the Block B config they extend


def opt_of(cfg):
    cfg = BN_BASE.get(cfg, cfg)
    if "-q0-" in cfg:
        return "q0"
    if "-qdu-" in cfg:
        return "qdu"
    raise ValueError(f"no queue option for {cfg}")


# ---------------------------------------------------------------------------------------------------------------
class RunEval:
    """One Block B run: the M2-S6 evaluation of every pair, the per-slave term series."""
    def __init__(self, runs, cfg, rep=0, conf_fn=None, swap=None):
        self.cfg, self.rep = cfg, rep
        self.run = R.Run72(runs, cfg, rep)
        self.T = F1.t_end(self.run)
        self.vec = RR.read_vectors(self.run.vec_path)
        conf_fn = conf_fn or (lambda k: V.CONF(cfg, k, self.T))
        self.views, self.E, self.m2 = {}, {}, {}
        for k in range(self.run.n):
            v = V.S6View(self.run, k, conf_fn(k), self.vec)
            if swap and k == swap[0]:              # NC-swap: DS-TT evidence of another DS-TT
                o = V.S6View(self.run, swap[1], conf_fn(swap[1]), self.vec)
                v.ds0, v.ds1, v.dslog, v.dseng, v.ttlog = o.ds0, o.ds1, o.dslog, o.dseng, o.ttlog
            self.views[k] = v
            before = len(K6.rows)
            try:
                E = K6.Eval(v)
                E.reads0 = dict(E.gnc.reads)        # the decomposition's GM reads (k_rows re-attaches others)
                K6.k_rows(v, E.gnc, None, f"k{k}")
                K6.s_rows(E, f"k{k}")
                K6.r_rows(E, f"k{k}")
                K6.e_rows(E, f"k{k}")
                if v.ttlog:
                    K6.t_rows(v, f"k{k}")
                    tc = K6.tt_components(E)
                    nb = sum(1 for x in tc if not x["sum_ok"])
                    K6.add(f"T k{k}", f"E_res,TT = sum of the TT components ({len(tc)} Follow_Ups)", nb == 0 and tc, f"{nb} mismatches")
                self.E[k] = E
            except Exception as ex:                # an oracle that cannot evaluate the pair is a failure of M2
                K6.add(f"X k{k}", "M2-S6 evaluation", False, f"{type(ex).__name__}: {ex}")
                self.E[k] = None
            self.m2[k] = K6.rows[before:]
            del K6.rows[before:]
        self.series = {k: self.slave_series(k) for k in self.E if self.E[k] is not None}

    def recorded(self, module, name):
        out = defaultdict(list)
        for t, v in self.vec.get((f"{R.NET}.{module}", name), []):
            out[t].append(K6.M_ps(v))
        return out

    def slave_series(self, k):
        """Per 1 ms sample t: measured C_S(t), C_G(t) (recordings), predicted (O5 / O1), last update, terms."""
        E, v = self.E[k], self.views[k]
        sl_rec = self.recorded(f"talker[{k}].clock", "timeChanged:vector")
        gm_rec = self.recorded("listener.clock", "timeChanged:vector")
        sl_pred = dict(E.o5.nc.C.ms_values)
        gm_pred = dict(E.gnc.C.ms_values)
        fus = {f["seq"]: f for f in E.fus if "skip" not in f}
        steps = sorted((f["sF"], f["seq"]) for f in fus.values() if "old" in f)
        ivs = {x["seq"]: x for x in E.iv}
        dsl = {int(r["seq"]): r for r in v.dslog if r["event"] == "corrected"}
        CG = lambda t: E.reads0[("C", t)]  # noqa: E731
        terms_of = {}
        for s, f in fus.items():
            if "old" not in f:
                continue
            r = f["r"]
            TSi, TSe = int(dsl[s]["TSi"]), int(dsl[s]["TSe"])
            tt_nw, tt_ds = -r * (TSi - f["si"]), r * (TSe - f["se"])
            x = {f"L.{a}": Fraction(b) for a, b in f["L"].items()}
            x.update({f"Rr.{a}": Fraction(b) for a, b in f["Rr"].items() if a != "TT"})
            x.update({"Rr.TT_nw": tt_nw, "Rr.TT_ds": tt_ds})
            x.update({f"D.{a}": Fraction(b) for a, b in f["D"].items()})
            x.update({"qG2": Fraction(f["qG"][1]), "qG1": -Fraction(f["qG"][0])})
            x.update({"lambda": Fraction(ivs[s]["lam"]), "rho": Fraction(ivs[s]["rho"])})
            terms_of[s] = {"x": x, "TT_split_ok": tt_nw + tt_ds == f["Rr"]["TT"], "f": f, "TSi": TSi, "TSe": TSe}
        samples = {}
        step_times = {t for t, _ in steps}
        si = 0
        for t in sorted(sl_pred):
            while si < len(steps) and steps[si][0] < t:
                si += 1
            m = steps[si - 1][1] if si > 0 else None
            samples[t] = {"m": m, "meas": (sl_rec.get(t), gm_rec.get(t)), "pred": (sl_pred[t], gm_pred.get(t)), "step_at_t": t in step_times}
            if m is not None:
                f = fus[m]
                samples[t]["delta"] = Fraction((sl_pred[t] - f["new"]) - (gm_pred[t] - CG(f["sF"])))
        return {"samples": samples, "terms": terms_of, "fus": fus, "steps": steps}


# ---------------------------------------------------------------------------------------------------------------
def m2_rows(ev):
    for k, rs in ev.m2.items():
        bad = [r for r in rs if not r[2]]
        fam = Counter(r[0].split()[0] for r in rs)
        add("M2", f"{ev.cfg}-{ev.rep} slave {k}", not bad and rs,
            f"{len(rs)} M2-S6 rows ({dict(fam)}) all exact" if not bad else
            f"{len(bad)} of {len(rs)} rows fail: " + "; ".join(f"{r[0]} {r[1][:80]} -- {r[3][:100]}" for r in bad[:4]))


def usable(sa, sb):
    """A common sample is used when both slaves have an update before it, no slave steps at that time, and the
    recordings hold exactly one value per clock at t."""
    if sa["m"] is None or sb["m"] is None or sa["step_at_t"] or sb["step_at_t"]:
        return False
    for s in (sa, sb):
        sl, gm = s["meas"]
        if not sl or not gm or len(sl) != 1 or len(gm) != 1 or s["pred"][1] is None:
            return False
    return True


def m3_rows(ev, claimed=C_SET, tag="M3d"):
    ks = sorted(ev.series)
    stats = {}
    for i in ks:
        for j in ks:
            if j <= i:
                continue
            A, B = ev.series[i], ev.series[j]
            common = sorted(set(A["samples"]) & set(B["samples"]))
            n_used = nA = nB = 0
            m3_bad, id_bad, canc_bad, sum_bad, split_bad = [], [], [], [], []
            cat = defaultdict(lambda: [None, None])
            excluded = Counter()
            for t in common:
                sa, sb = A["samples"][t], B["samples"][t]
                if not usable(sa, sb):
                    excluded["no update yet" if sa["m"] is None or sb["m"] is None else
                             ("step at t" if sa["step_at_t"] or sb["step_at_t"] else "recording ambiguous")] += 1
                    continue
                n_used += 1
                meas = (sa["meas"][0][0] - sa["meas"][1][0]) - (sb["meas"][0][0] - sb["meas"][1][0])
                pred = (sa["pred"][0] - sa["pred"][1]) - (sb["pred"][0] - sb["pred"][1])
                if meas != pred:
                    m3_bad.append((t, meas, pred))
                xa = dict(A["terms"][sa["m"]]["x"], delta=sa["delta"])
                xb = dict(B["terms"][sb["m"]]["x"], delta=sb["delta"])
                for s, x, ser in ((sa, xa, A), (sb, xb, B)):
                    if sum(x.values()) != s["pred"][0] - s["pred"][1]:
                        id_bad.append(t)
                    if not ser["terms"][s["m"]]["TT_split_ok"]:
                        split_bad.append(t)
                diff = {key: xa[key] - xb[key] for key in xa}
                if sa["m"] == sb["m"]:
                    nA += 1
                    nz = [key for key in claimed if diff.get(key, 0) != 0]
                    if nz:
                        canc_bad.append((t, nz))
                    path = sum(v for key, v in diff.items() if key not in claimed)
                    if path != meas:
                        sum_bad.append(t)
                    for key, v in diff.items():
                        if key not in claimed:
                            c = cat[key]
                            c[0] = v if c[0] is None or v < c[0] else c[0]
                            c[1] = v if c[1] is None or v > c[1] else c[1]
                else:
                    nB += 1
                    if sum(diff.values()) != meas:
                        sum_bad.append(t)
            name = f"{ev.cfg}-{ev.rep} pair ({i},{j})"
            add("M3", name, n_used > 0 and not m3_bad,
                f"{n_used} samples of {len(common)}: measured e_i - e_j = predicted exactly" + (f"; excluded {dict(excluded)}" if excluded else "")
                + (f"; {len(m3_bad)} MISMATCHES, first {m3_bad[0]}" if m3_bad else ""))
            add(tag, name, n_used > 0 and not (id_bad or canc_bad or sum_bad or split_bad),
                f"case A (same Sync) {nA} = {100 * nA / max(n_used, 1):.1f} %, case B (different Syncs) {nB} = "
                f"{100 * nB / max(n_used, 1):.1f} %; per-slave identity e = sum of terms "
                f"{'exact' if not id_bad else str(len(id_bad)) + ' FAIL'}; Rr.TT = TT_nw + TT_ds {'exact' if not split_bad else 'FAIL'}; "
                f"claimed-cancelling set {len(claimed)} terms bit-identical in case A {'yes' if not canc_bad else 'NO: ' + str(len(canc_bad)) + ' samples, first ' + str(canc_bad[0])}; "
                f"path-specific (A) / full (B) differences sum to the measured difference {'exactly' if not sum_bad else str(len(sum_bad)) + ' FAIL'}")
            stats[(i, j)] = {"n": n_used, "A": nA, "B": nB, "common": len(common), "excluded": dict(excluded),
                             "cat": {key: (float(v[0]) / NS, float(v[1]) / NS) for key, v in cat.items()}}
    return stats


def m4_rows(ev, clk):
    if clk == "ideal":
        return
    ks = sorted(ev.series)
    bad_rate, n_rate = [], 0
    # constant GM drift: the GM rate over every residence interval (O1, unquantized GM time) is one value rho_G
    rhos = {d["f"]["rho_res"] for k in ks for d in ev.series[k]["terms"].values()}
    rho_G = next(iter(rhos)) if len(rhos) == 1 else None
    for k in ks:
        for s, d in ev.series[k]["terms"].items():
            f = d["f"]
            rate = sum(Fraction(f["Rr"][a]) for a in ("carriage", "nrr", "window", "uncal"))
            n_rate += 1
            if rho_G is None or rate != (f["r"] - rho_G) * f["Res_s"]:
                bad_rate.append((k, s))
    pair_bad, n_pair = [], 0
    for i in ks:
        for j in ks:
            if j <= i:
                continue
            ti, tj = ev.series[i]["terms"], ev.series[j]["terms"]
            for s in sorted(set(ti) & set(tj)):
                fi, fj = ti[s]["f"], tj[s]["f"]
                ri = sum(Fraction(fi["Rr"][a]) for a in ("carriage", "nrr", "window", "uncal"))
                rj = sum(Fraction(fj["Rr"][a]) for a in ("carriage", "nrr", "window", "uncal"))
                n_pair += 1
                if rho_G is None or fi["r"] != fj["r"] or ri - rj != (fi["r"] - rho_G) * (fi["Res_s"] - fj["Res_s"]):
                    pair_bad.append((i, j, s))
    rho_txt = "not one value" if rho_G is None else f"{float(rho_G):.12f} (rho_G - (1 + 100 ppm) = {float(rho_G - 1 - Y_G):.3e})"
    add("M4", f"{ev.cfg}-{ev.rep} GM drift", rho_G is not None and not bad_rate and not pair_bad and n_rate > 0,
        f"GM rate over every residence interval of every slave one value rho_G = {rho_txt} ({len(rhos)} distinct); rate part of E_res = "
        f"(r - rho_G) Res: {n_rate} slave Follow_Ups{'' if not bad_rate else ', ' + str(len(bad_rate)) + ' FAIL'}; per pair and common Sync, "
        f"difference = (r - rho_G) (Res_i - Res_j): {n_pair}{'' if not pair_bad else ', ' + str(len(pair_bad)) + ' FAIL'}")
    if clk != "Eall":
        return
    t_bad = [k for k in ks if any(not r[2] for r in ev.m2[k] if r[0].startswith("T"))]
    nt = sum(1 for k in ks for r in ev.m2[k] if r[0].startswith("T"))
    tt_bad, n_tt, th = [], 0, Counter()
    comp = {}
    for k in ks:
        v = ev.views[k]
        byk = {(r["kind"], r["s"]): r for r in v.ttlog["ds"]}
        nwk = {(r["kind"], r["s"]): r for r in v.ttlog["nw"]}
        for s, d in ev.series[k]["terms"].items():
            f = d["f"]
            ce = TT.components(V.eall_ds(k), f["se"], byk[(2, f["se"])]["w"])
            ci = TT.components(V.EALL_NW, f["si"], nwk[(1, f["si"])]["w"])
            comp[(k, s)] = (ce, ci)
    for i in ks:
        for j in ks:
            if j <= i:
                continue
            ti, tj = ev.series[i]["terms"], ev.series[j]["terms"]
            for s in sorted(set(ti) & set(tj)):
                fi = ti[s]["f"]
                r = fi["r"]
                cei, cii = comp[(i, s)]
                cej, cij = comp[(j, s)]
                n_tt += 1
                lhs = ti[s]["x"]["Rr.TT_ds"] - tj[s]["x"]["Rr.TT_ds"]
                rhs = r * sum(cei[a] - cej[a] for a in cei)
                th_part = r * (cei["theta0"] - cej["theta0"])
                ok = (ti[s]["x"]["Rr.TT_nw"] == tj[s]["x"]["Rr.TT_nw"] and cii == cij and lhs == rhs
                      and cei["theta0"] - cej["theta0"] == 100 * NS * (i - j) * 1)
                th[(i, j)] = float(th_part) / NS
                if not ok:
                    tt_bad.append((i, j, s))
    # the pair part needs two slaves: at N = 1 it is not applicable (reported as such), the per-slave part still applies
    add("M4", f"{ev.cfg}-{ev.rep} TT clocks", not t_bad and not tt_bad and nt > 0 and (n_tt > 0 or len(ks) == 1),
        f"T rows with each DS-TT's own D-13 parameters: {nt} rows{'' if not t_bad else ', FAIL for slaves ' + str(t_bad)}; "
        f"per pair and common Sync: Rr.TT_nw identical, Rr.TT_ds,i - Rr.TT_ds,j = r [d theta0 + d osc + d w + d q], d theta0 = 100 ns (i - j): "
        f"{n_tt if len(ks) > 1 else 'not applicable (N = 1)'}{'' if not tt_bad else ', ' + str(len(tt_bad)) + ' FAIL'}; theta0 part (last Sync) per pair (ns): "
        f"{ {p: round(x, 6) for p, x in sorted(th.items())} }")


def i_rows(ev):
    run, name = ev.run, f"{ev.cfg}-{ev.rep}"
    bad1, n1 = [], 0
    bad3, n3, indep = [], 0, 0
    cfouts = defaultdict(dict)
    for k, v in ev.views.items():
        rows_ = v.dslog
        tx = defaultdict(list)
        for r in rows_:
            if r["event"] == "syncTx":
                tx[r["seq"]].append(r)
        own = {f["seq"]: f["start"] for f in RR.C5.sel(v.ds1, 2, RR.SYNC)}
        stamp = {(r["kind"], r["s"]): r["tau"] for r in v.ttlog["ds"]} if v.ttlog else None
        for r in rows_:
            if r["event"] != "corrected":
                continue
            n1 += 1
            s = int(r["seq"])
            t = tx.get(r["seq"], [])
            exp_tse = own.get(s) if stamp is None else stamp.get((2, own.get(s)))
            # syncTx logs the Sync's egress time (simulation time = PCAP first bit); corrected logs TSe as the DS-TT's
            # stamp of it (A1: the same simulation time; A2: its TT-clock stamp)
            if (len(t) != 1 or t[0]["syncFrameId"] != r["syncFrameId"] or own.get(s) is None or int(t[0]["TSe"]) != own[s]
                    or exp_tse is None or int(r["TSe"]) != exp_tse):
                bad1.append((k, s))
            cfouts[s][k] = int(r["cfOut"])
        for f in RR.C5.sel(v.sl, 1, RR.FU):
            if not f["g"]:
                continue
            s = f["g"]["seq"]
            if s not in cfouts or k not in cfouts[s]:
                continue
            n3 += 1
            if f["g"]["cf_raw"] != M.inet_write_clock8(cfouts[s][k]):
                bad3.append((k, s))
    indep = sum(1 for s, d in cfouts.items() if len(set(d.values())) > 1)
    add("I-1", name, not bad1 and n1 > 0, f"{n1} corrected Follow_Ups over {len(ev.views)} DS-TTs paired with their own Sync (syncFrameId, TSe = own egress stamp)"
        + (f"; FAIL {bad1[:4]}" if bad1 else ""))
    add("I-3", name, not bad3 and n3 > 0, f"{n3} Follow_Ups at the slaves carry their own DS-TT's cfOut; Syncs whose cfOut differs between DS-TTs: "
        f"{indep} of {len(cfouts)}" + (f"; FAIL {bad3[:4]}" if bad3 else ""))
    # I-4 identities and RNG mapping
    par = run.par
    n = run.n
    ttids = [(par.get((f"{R.NET}.dsTt[{k}].eth[1].trafficConditionerLayer.syncOut", "ttId")),
              par.get((f"{R.NET}.dsTt[{k}].eth[1].measurementLayer", "ttId")),
              par.get((f"{R.NET}.dsTt[{k}].eth[0].measurementLayer", "ttId"))) for k in range(n)]
    cids = [par.get((f"{R.NET}.dsTt[{k}].eth[1].trafficConditionerLayer.engine", "clockIdentity")) for k in range(n)]
    spi = []
    for k in range(n):
        ids = {f["g"]["spi"][:8] if isinstance(f["g"]["spi"], (bytes, bytearray)) else str(f["g"]["spi"])
               for f in RR.C5.sel(ev.views[k].sl, 2, RR.REQ, dom=None) if f["g"]}
        spi.append(tuple(sorted(ids)))
    probs = []
    if any(None in t for t in ttids) or len({t[0] for t in ttids}) != n or any(len(set(t)) != 1 for t in ttids):
        probs.append(f"ttIds {ttids}")
    if None in cids or len(set(cids)) != n:
        probs.append(f"clockIdentities {cids}")
    if any(len(x) != 1 for x in spi) or len(set(spi)) != n:
        probs.append(f"slave sourcePortIdentities {spi}")
    cfg_lines = config_lines(run.sca_path)
    nr = cfg_lines.get("num-rngs")
    if nr != str(2 * n):
        probs.append(f"num-rngs {nr}")
    for k in range(1, n):
        if cfg_lines.get(f"*.talker[{k}].clock.oscillator.rng-0") != str(2 * k):
            probs.append(f"talker[{k}] oscillator rng {cfg_lines.get(f'*.talker[{k}].clock.oscillator.rng-0')}")
        if "Eall" in ev.cfg and cfg_lines.get(f"*.dsTt[{k}].eth[1].trafficConditionerLayer.ttClock.rng-0") != str(2 * k + 1):
            probs.append(f"dsTt[{k}] TT clock rng")
    add("I-4", name, not probs, f"distinct ttIds {[t[0] for t in ttids]}, Pdelay clockIdentities {cids}, slave identities {len(set(spi))}, "
        f"NR MAC node ids {sorted(run.node_id.values())}; RNG mapping recorded (num-rngs {nr})" + (f"; FAIL {probs}" if probs else ""))


def config_lines(sca):
    out = {}
    with open(sca) as fh:
        for line in fh:
            if line.startswith("config "):
                k, v = line[7:].rstrip("\n").split(" ", 1)
                out.setdefault(k, v.strip('"'))
    return out


def f0_rows(ev):
    run, name = ev.run, f"{ev.cfg}-{ev.rep}"
    opt = opt_of(ev.cfg)
    start = len(F1.rows)
    teids = F1.f01(run, opt, name)
    F1.f02(run, name)
    F1.f03(run, name)
    n3 = R.n3_records(run.learn_n3)
    dn = R.dn_records(run.learn_dn)
    tk, lst = F2.macs(run)
    teid, probs = F1.sessions(run, n3, tk)
    ul_ok = False if probs else F2.f04(run, name, n3, dn, tk, lst, teid, ev.T)
    if probs:
        F2.add("F0-4", name, False, "sessions: " + "; ".join(probs))
    F1.f05(run, opt, name, teids, teid)
    keys = F1.learning(run, n3, dn, tk, lst, teid)
    meas, notes, end = F1.measure_d(run, n3, dn, keys)
    d = {s: (v[0] if v and set(v) == {0} else None) for s, v in meas.items()}
    F2.add("F0-7d", name, all(x == 0 for x in d.values()) and not notes,
           f"UPF-internal delays from this run's eventlog: UL {sorted(Counter(meas['UL']).items())} DL {sorted(Counter(meas['DL']).items())} (ps: count)"
           + ("; " + "; ".join(notes[:3]) if notes else ""))
    tlog = F2.table_log(run.elog_path)
    F2.f06(run, name, keys, tk, lst, teid, d if all(x is not None for x in d.values()) else None, tlog, n3, ev.T, ul_ok)
    F2.f08(run, name, n3, lst, ev.T)
    for r in F1.rows[start:]:
        rows.append(("I-2" if r[0] == "F0-2" else r[0], r[1], r[2], r[3]))
    del F1.rows[start:]


def i5_rows(ev, ref):
    """slave 0 at N > 1 (ev) vs N = 1 (ref), rule AR (design 7.2), per Follow_Up and term family."""
    name = f"{ev.cfg}-{ev.rep} vs {ref.cfg}-{ref.rep}"
    probs = []
    pa = {k: v for k, v in ev.run.par.items() if k[0].startswith((f"{R.NET}.dsTt[0].eth[1].trafficConditionerLayer.ttClock", f"{R.NET}.talker[0].clock"))}
    pb = {k: v for k, v in ref.run.par.items() if k[0].startswith((f"{R.NET}.dsTt[0].eth[1].trafficConditionerLayer.ttClock", f"{R.NET}.talker[0].clock"))}
    drop = ("logFile",)
    pa = {k: v for k, v in pa.items() if k[1] not in drop}
    pb = {k: v for k, v in pb.items() if k[1] not in drop}
    if pa != pb:
        probs.append(f"DS-TT 0 / slave 0 clock parameters differ: {sorted(set(pa.items()) ^ set(pb.items()))[:3]}")
    A, B = ev.series[0], ref.series[0]
    Ea, Eb = ev.E[0], ref.E[0]
    exa = {int(r["seq"]): r for r in Ea.dec.meas}
    exb = {int(r["seq"]): r for r in Eb.dec.meas}
    sxa = {x["seq"]: x for x in Ea.o5.out["exchanges"]}
    sxb = {x["seq"]: x for x in Eb.o5.out["exchanges"]}

    def ex(d, j):
        r = d.get(j)
        return None if r is None else tuple(r[c] for c in ("t1", "t2", "t3", "t4", "nrrQ63", "D"))

    def sx(d, m):
        x = d.get(m)
        return None if x is None else tuple(x[c] for c in ("t1", "t2", "t3", "t4", "g1", "g4", "d", "nrr_e"))
    fam_keys = {"L": lambda x: {k: v for k, v in x.items() if k.startswith("L.")},
                "Rr": lambda x: {k: v for k, v in x.items() if k.startswith("Rr.")},
                "D": lambda x: {k: v for k, v in x.items() if k.startswith("D.")},
                "qG": lambda x: {k: x[k] for k in ("qG1", "qG2")},
                "step": lambda x: {k: x[k] for k in ("lambda", "rho")}}

    def inputs(fam, t, f, side):
        exd, sxd = (exa, sxa) if side == "a" else (exb, sxb)
        if fam == "L":
            return (f["s1"], f["si"], f["j"], f["lup"], f["cf1"], ex(exd, f["j"]))
        if fam == "Rr":
            return (f["si"], f["se"], t["TSi"], t["TSe"], f["rr_out"], f["j"], ex(exd, f["j"]))
        if fam == "D":
            return (f["se"], f["s2"], f["M"], sx(sxd, f["M"]), f["cf2"])
        if fam == "qG":
            return (f["s1"], f["s2"])
        return (f["old"], f["new"], f["o"], f["s2"], f["sF"], f["e_s2"])
    counts = Counter()
    for s in sorted(set(A["terms"]) & set(B["terms"])):
        ta, tb = A["terms"][s], B["terms"][s]
        for fam, sel in fam_keys.items():
            same_in = inputs(fam, ta, ta["f"], "a") == inputs(fam, tb, tb["f"], "b")
            same_x = sel(ta["x"]) == sel(tb["x"])
            if same_in and not same_x:
                probs.append(f"Follow_Up {s} family {fam}: inputs identical, terms differ")
            counts[(fam, "identical" if same_x else "changed (inputs changed)")] += 1
    nd = nd_same = 0
    for t in sorted(set(A["samples"]) & set(B["samples"])):
        sa, sb = A["samples"][t], B["samples"][t]
        if "delta" not in sa or "delta" not in sb:
            continue
        nd += 1
        fa, fb = A["fus"][sa["m"]], B["fus"][sb["m"]]
        same_in = (fa["sF"], fa["new"], sa["pred"]) == (fb["sF"], fb["new"], sb["pred"])
        if same_in and sa["delta"] != sb["delta"]:
            probs.append(f"sample {t}: delta inputs identical, delta differs")
        nd_same += sa["delta"] == sb["delta"]
    add("I-5", name, not probs and counts,
        f"common Follow_Ups {len(set(A['terms']) & set(B['terms']))}; per family {dict(sorted(counts.items()))}; delta samples {nd} "
        f"({nd_same} identical); every family / delta with identical inputs is identical" + (f"; FAIL {probs[:3]}" if probs else ""))


# ---------------------------------------------------------------------------------------------------------------
def evaluate(runs, cfg, rep, ref=None, conf_fn=None, swap=None, claimed=C_SET, full=True):
    start = len(rows)
    ev = RunEval(runs, cfg, rep, conf_fn=conf_fn, swap=swap)
    if full:
        f0_rows(ev)
        i_rows(ev)
    m2_rows(ev)
    stats = m3_rows(ev, claimed)
    clk = re.match(r"M2S72-BN?-(?:q0|qdu)-(ideal|Ca|Eall)", cfg)
    clk = clk.group(1) if clk else "Eall"
    m4_rows(ev, clk)
    if ref is not None:
        i5_rows(ev, ref)
    fails = {r[0] for r in rows[start:] if r[2] == "FAIL"}
    return ev, stats, fails


def mutate_log(runs, cfg, col, k=1):
    tmp = tempfile.mkdtemp(prefix="m2s72bn-")
    shutil.copytree(os.path.join(runs, cfg), os.path.join(tmp, cfg))
    p = os.path.join(tmp, cfg, "m2log", f"{cfg}-0", f"{R.NET}.dsTt[{k}].eth[1].trafficConditionerLayer.syncOut.sync.csv")
    L = open(p).read().split("\n")
    h = L[0].split(",")
    j = h.index(col)
    idx = [i for i in range(1, len(L)) if L[i].startswith("corrected,")]
    i = idx[len(idx) // 2]
    c = L[i].split(",")
    c[j] = str(int(c[j]) + 1)
    L[i] = ",".join(c)
    open(p, "w").write("\n".join(L))
    return tmp, c[h.index("seq")]


def main():
    out = sys.argv[1]
    runs = os.path.join(out, "runs")
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    summary = {}
    refs = {}
    for opt in OPTS:
        for clk in CLKS:
            for n in (1,) + NS_B:
                cfg = f"M2S72-B-{opt}-{clk}-n{n}"
                if filt and not re.search(filt, cfg):
                    continue
                for rep in REPS:
                    if not os.path.isdir(os.path.join(runs, cfg)):
                        add("RUN", f"{cfg}-{rep}", False, "run missing")
                        continue
                    ref = refs.get((opt, clk, rep))
                    ev, stats, fails = evaluate(runs, cfg, rep, ref=ref if n > 1 else None)
                    if n == 1:
                        refs[(opt, clk, rep)] = ev
                    summary[(cfg, rep)] = stats
    # negative controls
    ctrl = []
    base = "M2S72-B-q0-Eall-n4"
    if not filt or re.search(filt, "controls"):
        def control(name, exp, fn):
            start = len(rows)
            try:
                fails = fn()
            except Exception as ex:
                fails = {f"EXCEPTION {type(ex).__name__}: {ex}"}
            mine = rows[start:]
            del rows[start:]
            ctrl.append((name, fails == exp, fails, exp, mine))
        control("NC-swap (slave 1 with DS-TT 2's evidence)", {"M2", "M3"},
                lambda: evaluate(runs, base, 0, swap=(1, 2), full=False)[2])
        control("NC-theta1 (M2S72-BN-theta1: DS-TT 1 theta0 + 1 us; checker D-13)", {"M2", "M4"},
                lambda: evaluate(runs, "M2S72-BN-theta1", 0, conf_fn=lambda k: V.CONF("M2S72-B-q0-Eall-n4", k, 12 * S))[2])
        control("NC-cancel (Rr.mul claimed cancelling)", {"M3d"},
                lambda: evaluate(runs, base, 0, claimed=C_SET + ("Rr.mul",), full=False)[2])
        control("NC-cancel (qG2 claimed cancelling)", {"M3d"},
                lambda: evaluate(runs, base, 0, claimed=C_SET + ("qG2",), full=False)[2])
        for col, exp in (("cfOut", {"M2", "M3", "I-3"}), ("TSe", {"M2", "I-1", "M4"})):
            def fn(col=col):
                tmp, seq = mutate_log(runs, base, col)
                try:
                    _, _, fails = evaluate(tmp, base, 0)
                    return fails
                finally:
                    shutil.rmtree(tmp)
            control(f"NC-{col.lower()} (DS-TT 1 logged {col} + 1 ps on one Follow_Up)", exp, fn)
    # report
    print("M2-S7.2a stage 4 / Checkpoint 2: Block B (design rev. 2.1)\n")
    for r in rows:
        print(" | ".join(r))
    nf = sum(1 for r in rows if r[2] == "FAIL")
    by = Counter((r[0], r[2]) for r in rows)
    print("\nrows per gate: " + ", ".join(f"{g} {by[(g, 'PASS')]} PASS / {by[(g, 'FAIL')]} FAIL" for g in sorted({r[0] for r in rows})))
    print(f"Block B: {len(rows) - nf} PASS, {nf} FAIL")
    print("\nsamples per pair (all seeds): config | pair | used / common | case A | case B | excluded")
    agg = defaultdict(lambda: Counter())
    for (cfg, rep), st in summary.items():
        for p, x in st.items():
            a = agg[(cfg, p)]
            a["n"] += x["n"]
            a["A"] += x["A"]
            a["B"] += x["B"]
            a["common"] += x["common"]
            for k, v in x["excluded"].items():
                a["x:" + k] += v
    for (cfg, p), a in sorted(agg.items()):
        print(f"{cfg} | {p} | {a['n']} / {a['common']} | {a['A']} ({100 * a['A'] / max(a['n'], 1):.2f} %) | {a['B']} "
              f"({100 * a['B'] / max(a['n'], 1):.2f} %) | { {k[2:]: v for k, v in a.items() if k.startswith('x:')} }")
    print("\npath-specific term differences in case A, range over all samples and seeds (ns): config | pair | term: [min, max]")
    rng = defaultdict(lambda: [None, None])
    for (cfg, rep), st in summary.items():
        for p, x in st.items():
            for key, (lo, hi) in x["cat"].items():
                r_ = rng[(cfg, p, key)]
                r_[0] = lo if r_[0] is None or lo < r_[0] else r_[0]
                r_[1] = hi if r_[1] is None or hi > r_[1] else r_[1]
    cur = None
    for (cfg, p, key), (lo, hi) in sorted(rng.items()):
        if (cfg, p) != cur:
            cur = (cfg, p)
            print(f"{cfg} | {p}:")
        if lo != 0 or hi != 0:
            print(f"    {key}: [{lo:.6f}, {hi:.6f}]")
    print("\nnegative controls (each must fail exactly its predicted row families):")
    for name, ok, fails, exp, mine in ctrl:
        print(f"{'PASS' if ok else 'FAIL'} | {name} | failed {sorted(fails)}, predicted {sorted(exp)}")
        for r in mine:
            if r[2] == "FAIL":
                print("      " + " | ".join(r)[:400])
    nc = sum(1 for c in ctrl if not c[1])
    print(f"controls: {len(ctrl) - nc} PASS, {nc} FAIL")
    print("Checkpoint 2 verdict: " + ("PASS" if nf == 0 and nc == 0 and ctrl else "FAIL (stop and report)"))
    return 0 if nf == 0 and nc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
