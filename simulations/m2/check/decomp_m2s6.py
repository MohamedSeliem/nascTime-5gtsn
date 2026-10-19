"""M2-S6 oracle O3/O4 (migration/m2-s6-design.md rev. 2, sections 4.3-4.5): exact error decomposition of
every Follow_Up the slave used, in explicit clock domains, with the closure checks C1-C5, and the
immediately-after-step / between-step error of every interval.

All arithmetic is exact (integers in ps, Fractions for unquantized GM / slave raw time and for exact
rate values). Inputs: PCAP first-bit times (simulation time = 5G reference time), the NW-TT and DS-TT
logs (the values the translators used), O1 (GM clock C_G, U_G = C_G, unquantized Gamma_G) and O5 (the
slave: C_S at Sync reception, pdelay history, steps). TT timestamps: tt(kind, seq) -> (value, s)
(A1: the simulation time itself; A2: the logged TtClock value)."""
from fractions import Fraction

import clock_model as K
import inet_model as M

SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10


def half(x):
    return Fraction(x, 2)


class Decomp:
    def __init__(self, R, sel, by_seq, cf_map, gm_reads, o5, tt=None):
        self.R, self.o5, self.G = R, o5, gm_reads          # G(kind, t): kind C (reading) or G (Gamma)
        self.sel, self.by_seq = sel, by_seq
        self.tt = tt
        R_ = R
        self.gm_sync = {f["seq"]: f for f in sel(R_.gm, 2, SYNC)}
        self.nw_sync = {f["seq"]: f for f in sel(R_.nw1, 1, SYNC)}
        self.ds_sync = {f["seq"]: f for f in sel(R_.ds1, 2, SYNC)}
        self.nw_req = {f["seq"]: f for f in sel(R_.nw1, 2, REQ, dom=None)}
        self.nw_resp = {f["seq"]: f for f in sel(R_.nw1, 1, RESP, dom=None)}
        self.gm_req = {f["seq"]: f for f in sel(R_.gm, 1, REQ, dom=None)}
        self.gm_resp = {f["seq"]: f for f in sel(R_.gm, 2, RESP, dom=None)}
        self.ds_req = {f["seq"]: f for f in sel(R_.ds1, 1, REQ, dom=None)}
        self.ds_resp = {f["seq"]: f for f in sel(R_.ds1, 2, RESP, dom=None)}
        self.nwlog = {int(r["seq"]): r for r in R_.nwlog if r["event"] == "corrected"}
        self.dslog = {int(r["seq"]): r for r in R_.dslog if r["event"] == "corrected"}
        self.meas = [r for r in R_.nweng if r["event"] == "measure"]

    # GM time helpers
    def dG(self, a, b):
        return self.G("G", b) - self.G("G", a)

    def queries(self):
        """GM reads the decomposition needs (for O1 attach_reads)."""
        q = []
        for f in self.gm_sync.values():
            q += [("C", f["start"]), ("G", f["start"])]
        for rec in self.o5.out["fu"]:
            q += [("C", rec["s2"]), ("G", rec["s2"]), ("C", rec["sF"])]
            s = rec["seq"]
            for d in (self.nw_sync, self.ds_sync):
                if s in d:
                    q.append(("G", d[s]["start"]))
        for d in (self.nw_req, self.nw_resp, self.gm_req, self.gm_resp):
            for f in d.values():
                q.append(("G", f["start"]))
        return q

    def published_exchange(self, t_fu):
        """The NW-TT engine exchange published when the Follow_Up was processed (latest 'measure' row
        before t_fu), with its predecessor (for the nRR window)."""
        prev, cur = None, None
        for r in self.meas:
            if int(r["t"]) < t_fu:
                prev, cur = cur, r
        return cur, prev

    def follow_up(self, rec):
        s = rec["seq"]
        R = self.R
        out = {"seq": s, "sF": rec["sF"], "s2": rec["s2"]}
        nl, dl = self.nwlog.get(s), self.dslog.get(s)
        if nl is None or dl is None or s not in self.gm_sync or s not in self.nw_sync or s not in self.ds_sync:
            out["skip"] = "Follow_Up not corrected by both translators"
            return out
        s1, si, se, s2 = self.gm_sync[s]["start"], self.nw_sync[s]["start"], self.ds_sync[s]["start"], rec["s2"]
        out.update(s1=s1, si=si, se=se)
        pot, cf2, pd = rec["pot"], rec["cf"], rec["pd"]
        CG = lambda t: self.G("C", t)  # noqa: E731
        eps = cf2 + pd - (CG(s2) - CG(s1))
        e_s2 = rec["t2"] - CG(s2)
        out.update(eps=eps, e_s2=e_s2, o=rec["o"])
        # ---- E_link (NW-TT): exchange j
        lup, rr_in = int(nl["Lup"]), float(nl["rrIn"])
        cf1 = int(nl["cfOut"])
        ex, exprev = self.published_exchange(int(nl["t"]))
        j = int(ex["seq"])
        t1, t2, t3, t4 = int(ex["t1"]), int(ex["t2"]), int(ex["t3"]), int(ex["t4"])
        nrr_e = int(ex["nrrQ63"])
        nrr = K.value(nrr_e)
        nrr_valid = not (int(ex["nrrNum"]) == 1 and int(ex["nrrDen"]) == 1 and exprev is None)
        s1p, s4p = self.nw_req[j]["start"], self.nw_resp[j]["start"]
        s2p, s3p = self.gm_req[j]["start"], self.gm_resp[j]["start"]
        e_in = K.from_double(rr_in)
        add_link = K.mul_round(lup, e_in)
        T = t4 - t1
        A = K.mul_round(T, nrr_e) - (t3 - t2)
        rho_rt = self.dG(s1p, s4p) / (s4p - s1p)
        tt1 = t1 - s1p if self.tt is None else t1 - s1p
        tt4 = t4 - s4p
        L = {
            "rrin": Fraction(add_link - lup),
            "trunc": Fraction(lup) - half(A),
            "mul": half(K.mul_round(T, nrr_e) - nrr * T),
            "nrr": half((nrr - rho_rt) * (s4p - s1p)),
            "TT": half(nrr * (tt4 - tt1)),
            "qG": -half(Fraction(t3 - t2) - self.dG(s2p, s3p)),
            "stale": half(self.dG(s1p, s4p) - self.dG(s2p, s3p)) - self.dG(s1, si),
        }
        E_link = add_link - self.dG(s1, si)
        # ---- E_res (DS-TT)
        rr_out = float(dl["rrOut"])
        r_e = K.from_double(rr_out)
        r = K.value(r_e)
        TSi, TSe = int(dl["TSi"]), int(dl["TSe"])
        Rm = TSe - TSi
        Res_s = se - si
        add_res = K.mul_round(Rm, r_e)
        rho_res = self.dG(si, se) / Res_s
        Rr = {
            "mul": Fraction(add_res) - r * Rm,
            "TT": r * ((TSe - se) - (TSi - si)),
        }
        rate = (r - rho_res) * Res_s
        if nrr_valid:
            s3a, s3b = self.gm_resp[int(exprev["seq"])]["start"], s3p
            rho_win = self.dG(s3a, s3b) / (s3b - s3a)
            Rr.update(carriage=(r - nrr) * Res_s, nrr=(nrr - rho_win) * Res_s, window=(rho_win - rho_res) * Res_s, uncal=Fraction(0))
        else:
            Rr.update(carriage=Fraction(0), nrr=Fraction(0), window=Fraction(0), uncal=rate)
        E_res = add_res - self.dG(si, se)
        # ---- E_ldn (slave Pdelay, exchange M = the latest the slave completed before the Follow_Up)
        exs = [x for x in self.o5.out["exchanges"] if x["t"] < rec["sF"]]
        X = exs[-1]
        sg1, sg4 = X["s1"], X["s4"]
        sg2, sg3 = self.ds_req[X["seq"]]["start"], self.ds_resp[X["seq"]]["start"]
        TS = X["t4"] - X["t1"]
        dGS = X["g4"] - X["g1"]
        nS = K.value(X["nrr_e"])
        B = K.mul_round(TS, X["nrr_e"]) - (X["t3"] - X["t2"])
        rho_S = Fraction(sg4 - sg1) / dGS
        D = {
            "smooth": Fraction(pd - X["d"]),
            "trunc": Fraction(X["d"]) - half(B),
            "mul": half(K.mul_round(TS, X["nrr_e"]) - nS * TS),
            "nrrS": half((nS - rho_S) * dGS),
            "qS": half(nS * (TS - dGS)),
            "TT": -half(Fraction(X["t3"] - X["t2"]) - (sg3 - sg2)),
            "stale": half(Fraction((sg4 - sg1) - (sg3 - sg2))) - (s2 - se),
            "base": Fraction(s2 - se) - self.dG(se, s2),
        }
        E_ldn = pd - self.dG(se, s2)
        qG1 = self.G("G", s1) - CG(s1)
        qG2 = self.G("G", s2) - CG(s2)
        E_qG = qG2 - qG1
        out.update(L=L, Rr=Rr, D=D, E_link=E_link, E_res=E_res, E_ldn=E_ldn, E_qG=E_qG, nrr_valid=nrr_valid,
                   nrrS_valid=X["nrr_valid"], j=j, M=X["seq"], lup=lup, cf1=cf1, cf2=cf2, add_link=add_link, add_res=add_res,
                   Res_s=Res_s, Rm=Rm, rr_out=rr_out, r=r, rho_res=rho_res, qG=(qG1, qG2))
        # ---- closures
        c = {}
        c["C1 link"] = sum(L.values()) == E_link
        c["C1 res"] = Rr["mul"] + Rr["TT"] + Rr["carriage"] + Rr["nrr"] + Rr["window"] + Rr["uncal"] == E_res
        c["C1 ldn"] = sum(D.values()) == E_ldn
        c["C1 eps"] = E_link + E_res + E_ldn + E_qG == eps
        c["C2 cf"] = (cf1 == add_link and cf2 == cf1 + add_res and int(dl["cfIn"]) == cf1 and lup == int(ex["D"])
                      and Rm == int(dl["Res"]))
        c["C3 offset"] = rec["o"] == rec["t2"] - pot - cf2 - pd and rec["o"] == e_s2 - eps and pot == CG(s1)
        if "old" in rec:
            Ls = self.o5.nc.C.L
            rho = rec["new"] - (rec["old"] - rec["o"])
            c["C4 step"] = rec["new"] == K.round_up(rec["old"] - rec["o"], Ls) and 0 <= rho < Ls
            out.update(old=rec["old"], new=rec["new"], rho=rho, exact_step=(Ls == 1 and rho == 0))
        if rec["prev_src"] is not None:
            c["C5 gmRR"] = rec["gm_e"] == K.from_integer_ratio(rec["src"] - rec["prev_src"], rec["loc"] - rec["prev_loc"])
        out["closure"] = c
        out["L_ld"] = L
        return out

    def run(self):
        self.fus = [self.follow_up(rec) for rec in self.o5.out["fu"]]
        return self.fus


def intervals(fus, gm_ms, sl_ms, CG):
    """After-step / between-step error (design 4.5) for every pair of consecutive steps.
    gm_ms, sl_ms: {t: C(t)} of the 1 ms samples (GM from O1, slave recorded = O5).
    Returns [(k, e_plus, lam, rho, max_abs_between, e_minus_next, n_samples)]."""
    out = []
    steps = [f for f in fus if "old" in f]
    for a, b in zip(steps, steps[1:] + [None]):
        e_plus = a["new"] - CG(a["sF"])
        lam = (a["old"] - (a["e_s2"] + CG(a["s2"]))) - (CG(a["sF"]) - CG(a["s2"]))
        t_end = b["sF"] if b else None
        es = [sl_ms[t] - gm_ms[t] for t in sl_ms if t > a["sF"] and (t_end is None or t < t_end) and t in gm_ms]
        e_minus = (b["old"] - CG(b["sF"])) if b else None
        assert e_plus == a["eps"] + lam + a["rho"]          # design 4.5 identity (exact)
        out.append({"seq": a["seq"], "e_plus": e_plus, "lam": lam, "rho": a["rho"], "eps": a["eps"],
                    "max_between": max((abs(x) for x in es), default=None), "e_minus_next": e_minus, "n": len(es),
                    "end": es[-1] if es else None})
    return out
