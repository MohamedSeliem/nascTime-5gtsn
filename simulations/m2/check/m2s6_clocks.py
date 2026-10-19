"""M2-S6 clock replay on top of O1 (clock_model.py): one node's oscillator with its settable clock
(C, INET SettableClock) and raw clock (U, underlyingClock), the drift-change schedule, steps, and the
predicted timeChanged / driftRateChanged sample sequences (design 1.1 K10, 5)."""
from collections import Counter, defaultdict

import clock_model as K
import inet_model as M

NS = 1000
MS = 10 ** 9
STAIR_DT = 12345 * 10 ** 6
O_DBL = 1.0 / 1e12                   # OMNeT++ SimTime::dbl (invfscale), as oracle_m2s3.dbl


def dbl(ps):
    return ps * O_DBL


class NodeClocks:
    def __init__(self, nconf, end, drift_vec=None, name=""):
        o = nconf["osc"]
        self.name, self.end, self.nconf = name, end, nconf
        self.osc = K.Oscillator(o["kind"], L=o["L"], ppm=o["ppm"], name=name)
        self.C = K.Clock(self.osc, nconf["initial"], name + ".clock")
        self.U = K.Clock(self.osc, 0, name + ".clock.underlyingClock")
        self.drift_samples = [(0, o["ppm"], "init")]
        self.changes = []                      # (t, new ppm) in time order
        if o["stair"]:
            init, ch = o["stair"]
            total, t = 0.0, STAIR_DT
            while t <= end:
                total += ch                    # RandomDriftOscillator::handleMessage: double accumulation
                self.changes.append((t, init + total))
                t += STAIR_DT
        elif o["rw"]:
            assert drift_vec is not None, "random walk: the recorded driftRateChanged vector is required"
            vals = [(t, float(v)) for t, v in drift_vec]
            # init sample, changes, finish sample (DriftingOscillatorBase initialize / setDriftRate / finish)
            self.changes = [(t, v) for t, v in vals[1:-1]]
        self.ci = 0
        self.ties = 0
        self.steps = []                        # (t, old, new, ppm, reset_done)

    def advance(self, t, inclusive=False):
        """Applies the drift changes strictly before t (inclusive: also at t)."""
        while self.ci < len(self.changes) and (self.changes[self.ci][0] < t or (inclusive and self.changes[self.ci][0] == t)):
            tc, v = self.changes[self.ci]
            if self.osc.set_drift_rate(tc, v):
                self.drift_samples.append((tc, v, "change"))
            self.ci += 1

    def read_C(self, t):
        self.advance(t)
        return self.C.at(t)

    def read_U(self, t):
        self.advance(t)
        return self.U.at(t)

    def step(self, t, new_time, ppm, reset=True):
        """A drift change at the same simulation time as a step is order-dependent (the reading is
        continuous at a change, so reads are not): counted in self.ties."""
        self.advance(t)
        if self.ci < len(self.changes) and self.changes[self.ci][0] == t:
            self.ties += 1
        old, new, r = self.C.set_clock_time(t, new_time, ppm, reset)
        self.steps.append((t, old, new, ppm, r))
        return old, new, r

    def finish(self):
        self.advance(self.end, inclusive=True)
        self.drift_samples.append((self.end, self.osc.ppm, "finish"))


def predicted_samples(nc, clock, emit):
    """Predicted timeChanged emissions of `clock` (nc.C or nc.U) after a completed replay:
    {t: [values]} plus {t: set of alternatives} for 1 ms samples coinciding with a step.
    Emissions (design K10): INITSTAGE_LAST at 0; the periodic timer (at 0, then every 1 ms, if emit);
    every oscillator post-change; at a step (settable clock): old, new; finish at the end."""
    fixed, alt = defaultdict(list), defaultdict(list)
    fixed[0].append(clock.samples_init)
    for t, v, cause in clock.samples:
        fixed[t].append(v)
    fixed[nc.end].append(clock.value_end)
    if emit:
        step_at = {}
        if clock is nc.C:
            for t, old, new, ppm, r in nc.steps:
                step_at[t] = (old, new)
        for t, v in clock.ms_values:
            if t in step_at:
                alt[t].append(step_at[t])
            else:
                fixed[t].append(v)
    return fixed, alt


def replay(nc, step_list=(), sample_ms=True):
    """Runs the node's clocks over [0, end]: drift changes, the given steps [(t, new, ppm)] and the 1 ms
    sample reads. Fills clock.samples (osc/step emissions), clock.ms_values, clock.samples_init and
    clock.value_end."""
    for c in (nc.C, nc.U):
        c.samples_init = c.at(0)
        c.ms_values = []
    events = []
    if sample_ms:
        t = 0
        while t <= nc.end:
            events.append((t, 1, "ms", None))
            t += MS
    for st in step_list:
        events.append((st[0], 2, "step", st))
    events.sort(key=lambda e: (e[0], e[1]))
    for t, _, kind, st in events:
        if kind == "ms":
            nc.advance(t, inclusive=True)
            vC, vU = nc.C.at(t), nc.U.at(t)
            nc.C.ms_values.append((t, vC))
            nc.U.ms_values.append((t, vU))
        else:
            nc.step(t, st[1], st[2], True)
    nc.finish()
    nc.C.value_end, nc.U.value_end = nc.C.at(nc.end), nc.U.at(nc.end)


def compare_samples(recorded, fixed, alt):
    """recorded: [(t, value string)] of a timeChanged vector. Exact comparison per simulation time
    (ps -> double, design K10); order inside one simulation time is not compared. Returns (ok, n, detail)."""
    rec = defaultdict(list)
    for t, v in recorded:
        rec[t].append(float(v))
    bad, n = [], 0
    for t in sorted(set(rec) | set(fixed) | set(alt)):
        r = Counter(rec.get(t, []))
        n += sum(r.values())
        for v in fixed.get(t, []):
            d = dbl(v)
            if r[d] > 0:
                r[d] -= 1
            else:
                bad.append((t, "missing", v))
        for a, b in alt.get(t, []):
            if r[dbl(a)] > 0:
                r[dbl(a)] -= 1
            elif r[dbl(b)] > 0:
                r[dbl(b)] -= 1
            else:
                bad.append((t, "missing alt", (a, b)))
        extra = +r
        for v, c in extra.items():
            bad.append((t, "unexpected", v))
    return not bad, n, bad[:5]


def compare_drift(recorded, nc):
    rec = [(t, float(v)) for t, v in recorded]
    pred = [(t, v) for t, v, c in nc.drift_samples]
    return rec == pred, len(rec), [(a, b) for a, b in zip(rec, pred) if a != b][:3] or (len(rec), len(pred))


def to_ppm_from_gm(gm_e):
    return M.to_ppm(gm_e)
