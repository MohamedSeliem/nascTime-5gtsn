"""M2-S6 oracle O1 (migration/m2-s6-design.md rev. 2, sections 4.1-4.2): an independent Python
re-implementation of the INET 4.7.0 oscillator and clock arithmetic. Integer picoseconds (OMNeT++
simulation-time precision 10^-12 s), exact Q1.63 integer arithmetic, Fractions for the unquantized
time Gamma. Every rule names the INET source it re-implements (paths relative to $INET_ROOT/src/inet).
Nothing is imported from INET; the M2-S6 checker compares this model with the recorded clock vectors
(rows K) before any prediction uses it.

    python3 clock_model.py      runs the self-tests (Q63 helpers against their Fraction definitions)
"""
import math
import random
from fractions import Fraction

Q63 = 1 << 63
PS = 1
MAX_S64 = (1 << 63) - 1


# ---------------------------------------------------------------------------------------
# NumberNear1 (common/NumberNear1.h): x = 1 - e/2^63, e = raw (S64). The C++ helpers take e' = -e.
def llround(x):
    """std::llround of a double: nearest, ties away from zero (exact on the double value)."""
    fx = Fraction(x)
    m = math.floor(abs(fx) + Fraction(1, 2))
    return m if fx >= 0 else -m


def from_difference_to_1(d):
    """NumberNear1::fromDifferenceTo1 (:136-152): e = llround(-d * 2^63) in double, saturated."""
    scaled = -d * float(Q63)
    if scaled <= float(-Q63):
        return -Q63
    if scaled >= float(1 << 62):
        return 1 << 62
    return llround(scaled)


def from_ppm(ppm):
    """NumberNear1::fromPpm (:160-164) -> fromDifferenceTo1(ppm / 1000000.0)."""
    return from_difference_to_1(ppm / 1000000.0)


def from_double(v):
    """NumberNear1::fromDouble (:154-158) -> fromDifferenceTo1(v - 1.0)."""
    return from_difference_to_1(v - 1.0)


def to_ppm(e):
    """NumberNear1::toPpm (:174-176): toDifferenceFrom1() * 1e6 = -((double)e / (double)2^63) * 1e6."""
    return -(float(e) / float(Q63)) * 1000000.0


def to_double(e):
    """NumberNear1::toDouble (:170-172)."""
    return 1.0 - float(e) / float(Q63)


def from_integer_ratio(num, den):
    """NumberNear1::fromIntegerRatio (:57-86): e = round((den - num) * 2^63 / den), ties away from 0."""
    assert den > 0 and 2 * num >= den and num <= 2 * den
    diff = den - num
    q = ((abs(diff) << 63) + (den >> 1)) // den
    return -q if diff < 0 else q


def product(e1, e2):
    """NumberNear1::operator* (:178-190): e3 = e1 + e2 - cross, cross = trunc((e1*e2 +- 2^62) / 2^63)."""
    t = e1 * e2
    t += (1 << 62) if t >= 0 else -(1 << 62)
    cross = abs(t) >> 63
    cross = cross if t >= 0 else -cross
    return e1 + e2 - cross


def value(e):
    """Exact rational value of the scale x = 1 - e/2^63."""
    return 1 - Fraction(e, Q63)


def mul_round(t, e):
    """mulRound = mul_round(t, -e) (:197-206, :303-327): t + round(t*(-e)/2^63), ties away from 0."""
    ep = -e
    if ep == 0:
        return t
    mag = (abs(t) * abs(ep) + (1 << 62)) >> 63
    return t - mag if (t < 0) != (ep < 0) else t + mag


def mul_floor(t, e):
    """mulFloor = mul_floor(t, -e) (:329-358): floor(t * (1 - e/2^63))."""
    return t + ((t * -e) >> 63)


def mul_ceil(t, e):
    """mulCeil = mul_ceil(t, -e) (:361-390): ceil(t * (1 - e/2^63))."""
    return t - ((t * e) >> 63)


def _den(e):
    D = Q63 - e  # D = 2^63 + e' (e' = -e), U64 in C++
    assert 0 < D < (1 << 64)
    return D


def div_round(t, e):
    """divRound = div_round(t, -e) (:392-455): round(t / x), ties away from 0."""
    D = _den(e)
    mag = ((abs(t) << 63) + (D >> 1)) // D
    return -mag if t < 0 else mag


def div_floor(t, e):
    """divFloor = div_floor(t, -e) (:457-505): floor(t / x)."""
    return (t << 63) // _den(e)


def div_ceil(t, e):
    """divCeil = div_ceil(t, -e) (:507-565): ceil(t / x)."""
    return -((-t << 63) // _den(e))


def cfmod(a, b):
    """OMNeT++ fmod(SimTime, SimTime): raw % raw with C++ semantics (sign of the dividend)."""
    r = abs(a) % b
    return -r if a < 0 else r


def round_up(t, l):
    """OscillatorBasedClock.cc roundUp: (t + l - 1) / l * l (C++ int64 division, toward zero)."""
    v = t + l - 1
    q = abs(v) // l
    return (q if v >= 0 else -q) * l


# ---------------------------------------------------------------------------------------
class Oscillator:
    """IdealOscillator (clock/oscillator/IdealOscillator.cc) or a DriftingOscillatorBase
    (clock/base/DriftingOscillatorBase.cc) with a piecewise-constant drift rate (ConstantDriftOscillator,
    RandomDriftOscillator). frequencyCompensationRate is never used by M2-S6 (factor 1)."""

    def __init__(self, kind, L=1, ppm=0.0, tick_offset=0, name=""):
        self.kind, self.name, self.L = kind, name, L
        self.clocks = []          # OscillatorBasedClocks subscribed to the pre/post state signals
        self.changes = []         # (time, kind, detail) log
        if kind == "ideal":
            self.origin, self.e, self.ppm, self.nT = 0, 0, 0.0, None
            return
        assert kind == "drift"
        self.origin = 0                               # initialize: setOrigin(simTime()) at s = 0
        self.ppm = ppm
        self.e = from_ppm(ppm)                        # setDriftFactor(SimTimeScale::fromPpm(driftRate))
        T = self.tick_length()
        assert 0 <= tick_offset < T, "First tick offset must be in the range [0, currentTickLength)"
        self.nT = T - tick_offset                     # nextTickFromOrigin

    # DriftingOscillatorBase::getCurrentTickLength
    def tick_length(self):
        if self.kind == "ideal":
            return self.L
        if self.e > 0:                                # effectiveTickLengthFactor < 1
            return div_floor(self.L, self.e)
        if self.e < 0:
            return div_ceil(self.L, self.e)
        return self.L

    # computeTicksForInterval (ticks in (0, d] after the origin)
    def ticks(self, d):
        assert d >= 0
        if self.kind == "ideal":
            return d // self.L                        # IdealOscillator::computeTicksForInterval
        if d == 0:
            return 0
        r = mul_floor(d - self.nT, self.e) // self.L + 1   # doComputeTicksForInterval (floor division)
        return max(r, 0)

    def nu(self, d):
        """Continuous tick phase: ticks(d) = floor(nu(d)) for d > 0 (design 4.1)."""
        if self.kind == "ideal":
            return Fraction(d, self.L)
        return value(self.e) * (d - self.nT) / self.L + 1

    def _pre(self, now):
        for c in self.clocks:
            c.move_origin(now)

    def _post(self, now):
        for c in self.clocks:
            c.emit_post(now)

    def set_drift_rate(self, now, new_ppm):
        """DriftingOscillatorBase::setDriftRate (:58-80)."""
        assert self.kind == "drift"
        if new_ppm == self.ppm:
            return False
        self._pre(now)
        T_old = self.tick_length()
        base = self.origin + self.nT - T_old
        elapsed = cfmod(now - base, T_old)
        remaining = T_old - elapsed
        e_new = from_ppm(new_ppm)
        self.nT = div_round(mul_round(remaining, self.e), e_new)   # raw * driftFactor / newDriftFactor
        self.ppm, self.e = new_ppm, e_new
        self.origin = now
        self.changes.append((now, "drift", new_ppm))
        self._post(now)
        return True

    def reset_tick_offset(self, now):
        """DriftingOscillatorBase::setTickOffset(0) (:104-122), called by SettableClock::setClockTime
        with resetOscillator = true (no effect on an IdealOscillator: dynamic_cast fails)."""
        if self.kind != "drift":
            return False
        T = self.tick_length()
        base = self.origin + self.nT - T
        old = cfmod(now - base, T)
        if old == 0:
            return False
        self._pre(now)
        self.origin = now
        self.nT = T
        self.changes.append((now, "reset", old))
        self._post(now)
        return True


class Clock:
    """OscillatorBasedClock (clock/model/OscillatorBasedClock.cc, useFutureEventSet = true, clock
    granularity = nominal tick) and SettableClock (clock/model/SettableClock.cc). The reading clamp to a
    pending clock event of the same simulation time (OscillatorBasedClock::getClockTime :65-81) is not
    modelled; callers flag readings that coincide with such events."""

    def __init__(self, osc, initial=0, name=""):
        self.osc, self.name = osc, name
        self.L = osc.L                                # getClockGranularity() = nominal tick length
        assert initial % self.L == 0, "Initial clock time must be a multiple of the oscillator nominal tick length"
        self.cos, self.coc, self.p, self.e = 0, initial, 0, 0   # setOrigin(initialClockTime) at s = 0
        self.ppm = 0.0
        self.samples = []                             # predicted timeChanged emissions (time, value, cause)
        osc.clocks.append(self)

    def _n(self, s):
        return self.osc.ticks(s - self.osc.origin)

    # doComputeClockTimeFromSimTime (:289-311), lowerBound = false
    def at(self, s):
        m = self._n(s) - self._n(self.cos)
        if m < 0:
            m = 0
        return self.coc + (m + ((self.p - self.e * m) >> 63)) * self.L

    def gamma(self, s):
        """Unquantized clock time (design 4.1); defined for compensation 0 (GM, raw clocks)."""
        assert self.e == 0
        d0 = self.cos - self.osc.origin
        return self.coc + self.L * (self.osc.nu(s - self.osc.origin) - self._n(self.cos)) if d0 >= 0 else None

    def q(self, s):
        return self.gamma(s) - self.at(s)

    # moveOrigin (:231-257): on preOscillatorStateChanged
    def move_origin(self, s):
        m = self._n(s) - self._n(self.cos)
        self.coc = self.coc + (m + ((self.p - self.e * m) >> 63)) * self.L
        self.p = (self.p - self.e * m) % Q63
        self.cos = s

    # setOrigin(clockTime) (:259-287)
    def set_origin(self, s, clock_time):
        m = self._n(s) - self._n(self.cos)
        self.p = (self.p - self.e * m) % Q63
        self.cos, self.coc = s, clock_time

    def emit_post(self, s):
        """postOscillatorStateChanged (:486-500) emits timeChanged with the (unchanged) clock time."""
        self.samples.append((s, self.at(s), "osc"))

    # SettableClock::setClockTime (:72-150) with the StepClockServo arguments
    def set_clock_time(self, s, new_time, ppm, reset=True):
        if ppm < -500000 or ppm > 1000000:
            raise ValueError("Invalid argument: oscillatorCompensation")
        old = self.at(s)
        new_time = round_up(new_time, self.L)          # roundingFunction (roundingMode "up")
        reset_done = False
        if new_time != old or ppm != self.ppm or reset:
            self.samples.append((s, old, "stepOld"))
            if reset:
                reset_done = self.osc.reset_tick_offset(s)
            self.ppm = ppm
            self.e = from_ppm(ppm)                    # getOscillatorCompensation() = SimTimeScale::fromPpm
            self.set_origin(s, new_time)
            self.samples.append((s, new_time, "stepNew"))
        return old, new_time, reset_done


# ---------------------------------------------------------------------------------------
# self-tests: the integer helpers against their Fraction definitions (hand-checkable cases + random)
def _rnd_ties_away(fr):
    m = math.floor(abs(fr) + Fraction(1, 2))
    return m if fr >= 0 else -m


def self_test(n=20000, seed=1):
    rng = random.Random(seed)
    fails = []
    # hand-computed cases
    hand = [
        (from_ppm(100.0), -922337203685478),   # -(1e-4 * 2^63) = -922337203685477.5808 -> ties away -> ...478
        (from_ppm(-50.0), 461168601842739),    # 0.5e-4 * 2^63 = 461168601842738.79 -> 739
        (mul_round(1000, from_ppm(100.0)), 1000),      # 1000 * 1.0001 = 1000.1 -> 1000
        (mul_round(5000, from_ppm(100.0)), 5001),      # 5000.5 (just above, e not exact) -> 5001
        (mul_floor(999, from_ppm(100.0)), 999),        # 999.0999
        (div_ceil(1000, from_ppm(100.0)), 1000),       # 1000 / 1.0001 = 999.90 -> 1000
        (div_floor(1000, from_ppm(-100.0)), 1000),     # 1000 / 0.9999 = 1000.1 -> 1000
        (Oscillator("drift", L=1, ppm=100.0).tick_length(), 1),
        (Oscillator("drift", L=1, ppm=-100.0).tick_length(), 1),
        (Oscillator("drift", L=1000, ppm=100.0).tick_length(), 1000),
        (Oscillator("drift", L=1000, ppm=-100.0).tick_length(), 1000),
        (Oscillator("drift", L=10000, ppm=100.0).tick_length(), 10000),  # ceil(10000 / 1.0001 = 9999.0001)
        (Oscillator("drift", L=10000, ppm=-100.0).tick_length(), 10001),  # floor(10000 / 0.9999 = 10001.0001)
    ]
    for i, (got, exp) in enumerate(hand):
        if got != exp:
            fails.append(f"hand case {i}: got {got}, expected {exp}")
    for _ in range(n):
        e = rng.choice([from_ppm(rng.uniform(-200, 200)), rng.randrange(-(1 << 50), 1 << 50), 0])
        t = rng.randrange(-10 ** 13, 10 ** 13)
        x = value(e)
        if mul_round(t, e) != _rnd_ties_away(t * x):
            fails.append(f"mul_round {t} {e}")
        if mul_floor(t, e) != math.floor(t * x):
            fails.append(f"mul_floor {t} {e}")
        if mul_ceil(t, e) != math.ceil(t * x):
            fails.append(f"mul_ceil {t} {e}")
        if div_round(t, e) != _rnd_ties_away(t / x):
            fails.append(f"div_round {t} {e}")
        if div_floor(t, e) != math.floor(t / x):
            fails.append(f"div_floor {t} {e}")
        if div_ceil(t, e) != math.ceil(t / x):
            fails.append(f"div_ceil {t} {e}")
        e2 = rng.randrange(-(1 << 50), 1 << 50)
        tt = e * e2
        cross = (abs(tt) + (1 << 62)) // Q63 * (1 if tt >= 0 else -1)
        if product(e, e2) != e + e2 - cross:
            fails.append("product")
        if len(fails) > 20:
            break
    # tick counting against the definition: n(d) = #{k >= 1 : nT + (k - 1) * L / x <= d}
    for _ in range(2000):
        L = rng.choice([1, 1000, 10000])
        o = Oscillator("drift", L=L, ppm=rng.uniform(-150, 150))
        x = value(o.e)
        d = rng.randrange(1, 10 ** 10)
        exp = 0 if d < o.nT else math.floor((d - o.nT) * x / L) + 1
        if o.ticks(d) != max(exp, 0):
            fails.append(f"ticks L={L} d={d}")
        if d >= o.nT and math.floor(o.nu(d)) != o.ticks(d):
            fails.append(f"nu L={L} d={d}")
    # ideal 1 ps oscillator clock = simulation time
    c = Clock(Oscillator("ideal", L=1))
    if any(c.at(s) != s for s in (0, 1, 12345, 10 ** 12)):
        fails.append("ideal clock")
    # a 0 ppm, 1 ps drifting oscillator counts like the ideal one
    c0 = Clock(Oscillator("drift", L=1, ppm=0.0))
    if any(c0.at(s) != s for s in (0, 1, 2, 999, 10 ** 12 + 7)):
        fails.append("0 ppm 1 ps clock")
    # +100 ppm, 1 ns: the clock advances (1 + 1e-4) * s, floored to the ns, within one tick
    c1 = Clock(Oscillator("drift", L=1000, ppm=100.0))
    for s in (10 ** 9, 125 * 10 ** 9, 3 * 10 ** 12 + 17):
        v = c1.at(s)
        exact = Fraction(s) * value(from_ppm(100.0))
        if v % 1000 or not (exact - 2000 <= v <= exact):
            fails.append(f"100 ppm clock at {s}: {v} vs {float(exact)}")
        g = c1.gamma(s)
        if not (0 <= g - v < 1000):
            fails.append(f"gamma-q at {s}")
    return fails


if __name__ == "__main__":
    f = self_test()
    print("clock_model self-test:", "PASS" if not f else "FAIL")
    for x in f[:20]:
        print("  ", x)
    raise SystemExit(1 if f else 0)
