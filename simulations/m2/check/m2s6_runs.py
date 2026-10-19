"""M2-S6 run access and clock configuration (migration/m2-s6-design.md rev. 2).

The clock parameters of every M2-S6 config are restated here (CLOCKS) from omnetpp.ini; rows K check
them against the recorded behaviour (a wrong entry fails K), and the initial driftRateChanged value is
compared with the table.
"""
import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
_argv = sys.argv
sys.argv = [_argv[0], "-", "-", "-", "-"]   # check_m2s5 / oracle_m2s3 read their arguments at import
import check_m2s5 as C5  # noqa: E402  (frames, sel, by_seq, read_csv, scalars_all, Run; unchanged)
sys.argv = _argv
import clock_model as K  # noqa: E402
import pcapng  # noqa: E402
import ttclock_model as TT  # noqa: E402

NS = 1000
MS = 10 ** 9
S = 10 ** 12
SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10
STAIR_DT = 12345 * 10 ** 6          # changeInterval 12.345 ms


def osc(kind="ideal", L=1, ppm=0.0, stair=None, rw=False):
    """kind ideal | drift; stair = (initial ppm, change ppm) for RandomDriftOscillator with a constant
    change every STAIR_DT; rw = random walk (values from the recorded driftRateChanged vector)."""
    return {"kind": kind, "L": L, "ppm": ppm, "stair": stair, "rw": rw}


IDEAL = osc()


def node(o=IDEAL, initial=0, servo="step", emit=True, emit_raw=True):
    return {"osc": o, "initial": initial, "servo": servo, "emit": emit, "emit_raw": emit_raw}


def cfg(unit, gm, sl, end, reps=(0,), tt=None, notes=""):
    return {"unit": unit, "gm": gm, "sl": sl, "end": end, "reps": tuple(reps), "tt": tt or {}, "notes": notes}


def C(ppm, L=NS):
    return osc("drift", L, ppm)


CLOCKS = {}
# gate D0
CLOCKS["M2S6U-Q10"] = cfg(True, node(C(100.0, 10 * NS)), node(C(-100.0, 10 * NS)), 10 * S)
# stage A: free-running (NoClockServo)
CLOCKS["M2S6U-A1"] = cfg(True, node(C(100.0)), node(C(-100.0), initial=1234567 * NS, servo="none"), 10 * S)
CLOCKS["M2S6U-A2"] = cfg(True, node(C(100.0, 10 * NS)), node(C(-100.0, 10 * NS), initial=1234560 * NS, servo="none"), 10 * S)
CLOCKS["M2S6U-A3"] = cfg(True, node(osc("drift", NS, 10.0, stair=(10.0, 0.012345))),
                         node(osc("drift", NS, -10.0, stair=(-10.0, -0.0012345)), initial=1234567 * NS, servo="none"), 10 * S)
CLOCKS["M2S6U-A4"] = cfg(True, node(osc("drift", NS, 20.0, rw=0.01)),
                         node(osc("drift", NS, -20.0, rw=0.02), initial=1234567 * NS, servo="none"), 10 * S, reps=(0, 1, 2))
CLOCKS["M2S6U-A5"] = cfg(True, node(C(100.0, 1)), node(C(-100.0, 1), initial=1234567 * NS, servo="none"), 10 * S)

# stage B: GM drift, slave 0 ppm (1 ns)
for name, y in (("m100", -100.0), ("m10", -10.0), ("m1", -1.0), ("p1", 1.0), ("p10", 10.0), ("p100", 100.0)):
    CLOCKS[f"M2S6U-B-{name}"] = cfg(True, node(C(y)), node(C(0.0)), 10 * S)
CLOCKS["M2S6-B-p100"] = cfg(False, node(C(100.0)), node(C(0.0)), 5 * S, reps=range(10))
CLOCKS["M2S6-B-m100"] = cfg(False, node(C(-100.0)), node(C(0.0)), 5 * S)
CLOCKS["M2S6-B-p10"] = cfg(False, node(C(10.0)), node(C(0.0)), 5 * S)

# stage C
CLOCKS["M2S6U-C-sp100"] = cfg(True, node(C(0.0)), node(C(100.0)), 10 * S)
CLOCKS["M2S6U-C-sm100"] = cfg(True, node(C(0.0)), node(C(-100.0)), 10 * S)
CLOCKS["M2S6U-C-a"] = cfg(True, node(C(100.0)), node(C(-100.0)), 10 * S)
CLOCKS["M2S6U-C-b"] = cfg(True, node(C(-100.0)), node(C(100.0)), 10 * S)
for name, ch in (("r001", 0.00012345), ("r01", 0.0012345), ("r1", 0.012345)):
    CLOCKS[f"M2S6U-C-{name}"] = cfg(True, node(osc("drift", NS, 0.0, stair=(0.0, ch))), node(C(0.0)), 10 * S)
CLOCKS["M2S6U-C-rs1"] = cfg(True, node(C(0.0)), node(osc("drift", NS, 0.0, stair=(0.0, -0.012345))), 10 * S)
CLOCKS["M2S6U-C-off"] = cfg(True, node(C(100.0)), node(C(-100.0), initial=1234567 * NS), 10 * S)
CLOCKS["M2S6U-C-1ps"] = cfg(True, node(C(100.0, 1)), node(C(-100.0, 1)), 10 * S)
CLOCKS["M2S6U-C-1psr"] = cfg(True, node(osc("drift", 1, 100.0, stair=(100.0, 0.012345))), node(C(-100.0, 1)), 10 * S)
CLOCKS["M2S6-C-a"] = cfg(False, node(C(100.0)), node(C(-100.0)), 5 * S, reps=range(10))
CLOCKS["M2S6-C-off"] = cfg(False, node(C(100.0)), node(C(-100.0), initial=1234567 * NS), 5 * S)
CLOCKS["M2S6-C-r1"] = cfg(False, node(osc("drift", NS, 0.0, stair=(0.0, 0.012345))), node(C(0.0)), 5 * S)
for f in ("FS1", "FS2", "FD1", "FD2"):
    CLOCKS[f"M2S6-C-{f}"] = cfg(False, node(C(100.0)), node(C(-100.0)), 5 * S, notes="fault")

# stage D
for name in ("frag", "load", "load-harq16", "nwpd025", "slpd0125"):
    CLOCKS[f"M2S6-D-{name}"] = cfg(False, node(C(100.0)), node(C(-100.0)), 5 * S)
CLOCKS["M2S6-D-nwpd8"] = cfg(False, node(C(100.0)), node(C(-100.0)), 20 * S)
for f in ("FS2late", "FD1late"):
    CLOCKS[f"M2S6-D-{f}"] = cfg(False, node(C(100.0)), node(C(-100.0)), 5 * S, notes="fault")

# stage E: TT clocks (A2) on the C-a clocks (GM +100 ppm, slave -100 ppm, 1 ns); tt = {"nw": ..., "ds": ...} in ps / ppb
NSx = NS
_ca = lambda: (node(C(100.0)), node(C(-100.0)))  # noqa: E731
for name, dth in (("th10", 10), ("th100", 100), ("th1000", 1000)):
    CLOCKS[f"M2S6U-E-{name}"] = cfg(True, *_ca(), 10 * S, tt={"nw": TT.tt(theta0=200 * NS), "ds": TT.tt(theta0=(200 + dth) * NS)})
CLOCKS["M2S6U-E-y"] = cfg(True, *_ca(), 10 * S, tt={"nw": TT.tt(y=100, U=10 * MS), "ds": TT.tt(y=-100, U=10 * MS, phi=3 * MS)})
CLOCKS["M2S6U-E-yfree"] = cfg(True, *_ca(), 10 * S, tt={"nw": TT.tt(y=100), "ds": TT.tt(y=-100)})
CLOCKS["M2S6U-E-D"] = cfg(True, *_ca(), 10 * S, tt={"nw": TT.tt(D=1000, U=100 * MS), "ds": TT.tt(D=-1000, U=100 * MS, phi=30 * MS)})
for name, sg in (("sig1", 1), ("sig10", 10), ("sig100", 100)):
    CLOCKS[f"M2S6U-E-{name}"] = cfg(True, *_ca(), 10 * S, reps=range(5), tt={"nw": TT.tt(sigma=sg * NS), "ds": TT.tt(sigma=sg * NS)})
CLOCKS["M2S6U-E-L8"] = cfg(True, *_ca(), 10 * S, tt={"nw": TT.tt(L=8 * NS), "ds": TT.tt(L=8 * NS)})
_all = {"nw": TT.tt(theta0=200 * NS, y=100, U=10 * MS, sigma=10 * NS), "ds": TT.tt(theta0=300 * NS, y=-100, U=10 * MS, phi=3 * MS, sigma=10 * NS)}
CLOCKS["M2S6-E-all"] = cfg(False, *_ca(), 5 * S, reps=range(3), tt=_all)
CLOCKS["M2S6-E-all-load"] = cfg(False, *_ca(), 5 * S, tt=_all)

# stage F: negative controls (TEST ONLY knobs) on the C-a clocks; the slave servo of the N-servo controls
# is the TEST servo (the rows evaluate them with the StepClockServo model and with the TEST model)
for name in ("rrIgnore", "rrTwice", "nrrInvert", "nrrStale", "lupLocal", "servoNoRate", "servoNegRate"):
    CLOCKS[f"M2S6U-F-{name}"] = cfg(True, *_ca(), 10 * S, notes="N")
CLOCKS["M2S6-F-rrIgnore"] = cfg(False, *_ca(), 5 * S, notes="N")
CLOCKS["M2S6U-R-inet"] = cfg(True, *_ca(), 10 * S, notes="R")
CLOCKS["M2S6U-F-domain"] = cfg(True, *_ca(), 10 * S, notes="N", tt={"nw": TT.tt(theta0=200 * NS), "ds": TT.tt(theta0=300 * NS)})


# ---------------------------------------------------------------------------------------
def read_vectors(path):
    """All vectors of a .vec file: {(module, name): [(t_ps, value_string)]} in file (event) order."""
    ids, data = {}, defaultdict(list)
    with open(path) as fh:
        for line in fh:
            c = line[:1]
            if c.isdigit():
                tab = line.find("\t")
                vid = line[:tab]
                k = ids.get(vid)
                if k is not None:
                    p = line.rstrip("\n").split("\t")
                    data[k].append((pcapng.simtime_ps(p[2]), p[3]))
            elif line.startswith("vector "):
                p = line.split()
                ids[p[1]] = (p[2], p[3])
    return data


class Run(C5.Run):
    """check_m2s5.Run plus every vector and the M2-S6 clock configuration."""
    def __init__(self, runs, cfgname, rep=0):
        self.conf = CLOCKS[cfgname]
        super().__init__(runs, cfgname, rep, unit=self.conf["unit"])
        self.vec = read_vectors(self.vec_path)
        tc = lambda tt: os.path.join(self.ldir, f"{self.net}.{tt}.eth[1].trafficConditionerLayer.ttClock.ttclock.csv")  # noqa: E731
        self.ttlog = {"nw": TT.read_log(tc(self.nwn)), "ds": TT.read_log(tc(self.dsn))} if self.conf["tt"] else None

    def vecv(self, module, name):
        return self.vec.get((f"{self.net}.{module}", name), [])
