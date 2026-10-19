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

    def vecv(self, module, name):
        return self.vec.get((f"{self.net}.{module}", name), [])
