"""M2-S7.2a stage 4: the unchanged M2-S6 oracles applied to one DS-TT / slave pair of an M2S72Bridge run
(migration/m2-s7.2a-design.md rev. 2.1, 4.1 and 4.4).

S6View(run72, k, conf) has every attribute m2s6_runs.Run (check_m2s5.Run) provides to the M2-S6 oracles
(check_m2s6.Eval, k_rows, s_rows, r_rows, e_rows, t_rows, tt_components; slave_m2s6; decomp_m2s6), for the tuple
(listener = GM, nwTt, dsTt[k], talker[k]) of an M2S72Bridge run. Nothing is assumed per UE: frames, logs, vectors
and the TT-clock logs are those of dsTt[k] / talker[k]; the GM, NW-TT and UPF are shared.

conf is an m2s6_runs.cfg(...) dict for that pair: the GM and slave clocks of the config and, for TT clocks
(A2), {"nw": TT.tt(...), "ds": TT.tt(...)} with DS-TT k's own parameters (design D-13). CONF(cfg, k) states the
Block B clock configurations; the K / S / T rows check them against the recorded behaviour (a wrong entry fails).
"""
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s72_runs as R  # noqa: E402
import m2s6_runs as RR  # noqa: E402
import ttclock_model as TT  # noqa: E402

NS, MS, S = RR.NS, RR.MS, RR.S
C5 = RR.C5


def eall_ds(k):
    """D-13: DS-TT k TT clock in the S7.2a E-all configs (DS-TT 0 = M2-S6 E-all)."""
    return TT.tt(theta0=(300 + 100 * k) * NS, y=-100 + 50 * k, U=10 * MS, phi=(3 + k) * MS, sigma=10 * NS)


EALL_NW = TT.tt(theta0=200 * NS, y=100, U=10 * MS, sigma=10 * NS)


def CONF(cfg, k, end):
    """Clock configuration of pair k of a Block B config M2S72-B-<opt>-<clk>-n<N> (or its I-5 reference)."""
    m = re.match(r"M2S72-B[A-Z]*-(q0|qdu)-(ideal|Ca|Eall)-n(\d+)", cfg)
    if not m:
        raise ValueError(f"no clock configuration for {cfg}")
    clk = m.group(2)
    if clk == "ideal":
        return RR.cfg(False, RR.node(RR.IDEAL), RR.node(RR.IDEAL), end)
    gm, sl = RR.node(RR.C(100.0)), RR.node(RR.C(-100.0))
    if clk == "Ca":
        return RR.cfg(False, gm, sl, end)
    return RR.cfg(False, gm, sl, end, tt={"nw": EALL_NW, "ds": eall_ds(k)})


class S6View:
    def __init__(self, run, k, conf, vec=None):
        u = run.ue_view(k)
        self.run, self.k, self.conf = run, k, conf
        self.cfg, self.rep, self.unit = run.cfg, run.rep, False
        self.base, self.ldir = run.base, run.ldir
        self.sca_path, self.vec_path = run.sca_path, run.vec_path
        self.net = R.NET
        self.gmn, self.nwn, self.dsn, self.sln = "listener", "nwTt", f"dsTt[{k}]", f"talker[{k}]"
        self.station = f"{R.NET}.{self.sln}"
        self.gm, self.nw1, self.nw0 = run.gm, run.nw1, run.nw0
        self.ds0, self.ds1, self.sl, self.ue = u.ds0, u.ds1, u.sl, u.ue
        self.dn, self.n3path = run.dn, run.n3path
        self.nwlog, self.nweng = run.nwlog, run.nweng
        self.dslog, self.dseng = u.dslog, u.dseng
        tc = os.path.join(run.ldir, f"{R.NET}.nwTt.eth[1].trafficConditionerLayer")
        self.nweng_path = tc + ".engine.pdelay.csv"
        self.vec = vec if vec is not None else RR.read_vectors(run.vec_path)
        ttc = lambda tt: os.path.join(run.ldir, f"{R.NET}.{tt}.eth[1].trafficConditionerLayer.ttClock.ttclock.csv")  # noqa: E731
        self.ttlog = {"nw": TT.read_log(ttc("nwTt")), "ds": TT.read_log(ttc(self.dsn))} if conf["tt"] else None

    def vecv(self, module, name):
        return self.vec.get((f"{self.net}.{module}", name), [])
