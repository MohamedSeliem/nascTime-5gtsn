"""H8 counterfactual (diagnostic, not a checker row): replay the INET slave (O5) on the same recorded inputs
   with and without the K7 tick-phase resets and compare (i) the mean between-step drift e-_{k+1} - e+_k and
   (ii) the mean gmRR. Caveat: in the counterfactual the slave's own Pdelay timer times would shift slightly;
   the inputs (Sync/Follow_Up arrival, POT, cf, DS-TT t2/t3) are taken from the recorded run.
   Usage: diag_m2s6_h8.py <runs dir> <config> <rep>"""
import sys
sys.path.insert(0, __import__("os").path.dirname(__import__("os").path.abspath(__file__)))
import m2s6_runs as RR, check_m2s6 as CK, slave_m2s6 as O5, m2s6_clocks as MC
R = RR.Run(sys.argv[1], sys.argv[2], int(sys.argv[3]))
E = CK.Eval(R)
CG = lambda t: E.gnc.reads[("C", t)]
pot = {s: E.gnc.reads[("C", f["start"])] for s, f in E.sync.items()}
sel = RR.C5.sel
t2 = {f["seq"]: f["start"] for f in sel(R.ds1, 1, RR.REQ, dom=None)}
t3 = {f["seq"]: f["start"] for f in sel(R.ds1, 2, RR.RESP, dom=None)}

def drift(fus):
    st = [f for f in fus if "old" in f]
    ds = [b["old"] - CG(b["sF"]) - (a["new"] - CG(a["sF"])) for a, b in zip(st[9:], st[10:])]
    gm = [O5.K.to_double(f["gm_e"]) for f in st[9:]]
    return sum(ds) / len(ds), sum(gm) / len(gm), len(ds), sum(1 for f in st if f.get("reset"))

class NoReset(MC.NodeClocks):
    def step(self, t, new_time, ppm, reset=True):
        return super().step(t, new_time, ppm, False)

with_r = drift(E.o5.out["fu"])
O5.MC.NodeClocks = NoReset
o = O5.SlaveO5(R.conf["sl"], R.conf["end"], None, R.sln)
O5.MC.NodeClocks = NoReset.__mro__[1]
assert isinstance(o.nc, NoReset)
o.run(R.sl, lambda s: t2[s], lambda s: t3[s], lambda s: pot[s], lambda s: E.cf[s])
without = drift(o.out["fu"])
print(f"{sys.argv[2]}-{sys.argv[3]}  L_S = {R.conf['sl']['osc'].get('L', '?')}")
for name, (d, g, n, nr) in (("with K7 resets (recorded = O5)", with_r), ("counterfactual: no resets", without)):
    print(f"  {name:32s} mean between-step drift {d / 1e3:+.4f} ns over {n} intervals; mean gmRR - 1 = {(g - 1) * 1e9:+.4f} ppb; steps with reset {nr}")
mean_phase = sum(c[2] for c in E.o5.nc.osc.changes if c[1] == "reset") / max(1, sum(1 for c in E.o5.nc.osc.changes if c[1] == "reset"))
print(f"  mean reset phase {mean_phase / 1e3:.4f} ns; mean reset phase / 125 ms = {mean_phase / 125e9 * 1e9:.4f} ppb")
