"""Independent Python re-implementation of the INET 4.7.0 gPTP slave path and its clock, used by
the M2-S3 offline oracle. Integer picoseconds throughout (simulation-time scale 10^-12 s, the
OMNeT++ default used by every M1/M2 run). Every rule names the INET source it re-implements
(paths relative to $INET_ROOT/src/inet). Nothing here is imported from INET; the oracle checks
this model against the slave's recorded behaviour (rows C1/C2) before using it for predictions.
"""
import math
from fractions import Fraction

Q63 = 1 << 63
NS = 1000  # ps

# INET's Gptp ASSERTs (currentPdelay >= 0, pdelay >= 0) are inactive in the release build
# that M1/M2 use (-DNDEBUG, OMNeT++ Makefile.inc). True: the model raises on them (M2-S3
# default, unchanged); False: it continues as the release build does (M2-S4 replays of
# negative controls that produce a negative link delay).
STRICT_INET_ASSERTS = True


# ---------------------------------------------------------------------------------------
# NumberNear1 (common/NumberNear1.h): value = 1 - e_q63 / 2^63
def from_integer_ratio(num, den):
    """NumberNear1::fromIntegerRatio (NumberNear1.h:57-86): e = round(diff * 2^63 / den), diff = den - num,
    round to nearest, ties away from 0. Used via ClockTimeScale::fromRatio (clock/common/ClockTimeScale.h:25)."""
    assert den != 0 and 2 * num >= den and num <= 2 * den
    diff = den - num
    a = abs(diff)
    qmag = ((a << 63) + (den >> 1)) // den
    return -qmag if diff < 0 else qmag


def mul_round(t, e_q63):
    """NumberNear1::mulRound (NumberNear1.h:196-206 -> mul_round(t, -e_q63), :292ff):
    t * (1 - e/2^63), i.e. t + round(t * E / 2^63) with E = -e, ties away from 0."""
    E = -e_q63
    if E == 0:
        return t
    neg = (t < 0) ^ (E < 0)
    mag = (abs(t) * abs(E) + (1 << 62)) >> 63
    return t - mag if neg else t + mag


def to_double(e):
    """NumberNear1::toDouble (NumberNear1.h): 1.0 - (double)e / (double)2^63 (IEEE doubles)."""
    return 1.0 - float(e) / float(Q63)


def to_ppm(e):
    """NumberNear1::toPpm = toDifferenceFrom1() * 1e6, toDifferenceFrom1 = -((double)e / 2^63)."""
    return (-(float(e) / float(Q63))) * 1000000.0


def _llround(x):
    fx = Fraction(x)
    m = math.floor(abs(fx) + Fraction(1, 2))
    return m if fx >= 0 else -m


def from_ppm(ppm):
    """NumberNear1::fromPpm -> fromDifferenceTo1(ppm / 1e6): e = llround(-d * 2^63) (double product,
    rounded half away from zero), as used by SettableClock for the oscillator compensation."""
    d = ppm / 1000000.0
    return _llround(-d * float(Q63))


# ---------------------------------------------------------------------------------------
class Clock:
    """SettableClock over an IdealOscillator with tick = simulation-time precision (1 ps;
    clock/oscillator/IdealOscillator.ned: tickLength default 0s = precision), OscillatorBasedClock
    fixed-point compensation (clock/model/OscillatorBasedClock.cc fracAdvance/Arel, ~:196-215):
        clock(s) = C0 + m + floor((p - e*m) / 2^63),  m = s - s0 (ticks).
    setClockTime (clock/model/SettableClock.cc:72ff) with StepClockServo (resetOscillator = true):
    the compensation is changed before the origin is moved, so the accumulator becomes
    (p - e_new*m) mod 2^63."""

    def __init__(self, initial=0):
        self.s0, self.C0, self.p, self.e = 0, initial, 0, 0
        self.steps = []  # (sim time, old clock, new clock, ppm)

    def at(self, t):
        m = t - self.s0
        return self.C0 + m + ((self.p - self.e * m) // Q63)

    def set(self, t, new, ppm):
        old = self.at(t)
        self.e = from_ppm(ppm)
        m = t - self.s0
        self.p = (self.p - self.e * m) % Q63
        self.s0, self.C0 = t, new
        self.steps.append((t, old, new, ppm))


def trunc_div2(x):
    """C++ integer division by 2 (truncation toward zero), clocktime_t / int."""
    return x // 2 if x >= 0 else -((-x) // 2)


def simtime_times_double(x_ps, d):
    """SimTime * double (OMNeT++ simtime.h): fromRaw(floor(raw * d + 0.5)) -- double arithmetic."""
    return math.floor(float(x_ps) * d + 0.5)


# ---------------------------------------------------------------------------------------
# INET GptpPacketSerializer (linklayer/ieee8021as/GptpPacketSerializer.cc), wire value <-> ps.
# Compared with the real INET serializer by gptp_serializer_probe (row A5).
def inet_write_clock8(ps):
    """writeClock8 (:29-38): split(SIMTIME_NS) -> whole ns << 16, plus remainder_ps * 1e9 / 1e12
    (integer division: always 0 for a remainder < 1000 ps, and not shifted): sub-ns dropped."""
    q = int(ps / NS) if ps >= 0 else -int((-ps) // NS)  # SimTime::split truncates toward zero
    rem = ps - q * NS
    num = rem * 1000000000  # C++ int64 division truncates toward zero
    return (q << 16) + (num // 10 ** 12 if num >= 0 else -((-num) // 10 ** 12))


def inet_read_clock8(raw):
    """readClock8 (:21-27): (raw >> 16) ns + ((raw & 0xFFFF) * 1000 >> 16) ps (floor)."""
    return (raw >> 16) * NS + (((raw & 0xFFFF) * 1000) >> 16)


def inet_write_timestamp(ps):
    """writeTimestamp (:50-58): 48-bit seconds, 32-bit ns, the sub-ns part dropped (truncation)."""
    s, rest = divmod(ps, 10 ** 12)
    return s, rest // NS


def inet_read_timestamp(s, ns):
    return s * 10 ** 12 + ns * NS


def inet_csro(rr):
    """GptpPacket.msg:183 getCumulativeScaledRateOffset: (int32) ceil((rr - 1.0) * 2^41) (doubles)."""
    return int(math.ceil((rr - 1.0) * float(1 << 41)))


def inet_rr_from_csro(x):
    """GptpPacket.msg:182 setCumulativeScaledRateOffset: 1.0 + x / 2^41 (doubles)."""
    return 1.0 + float(x) / float(1 << 41)


# 802.1AS / 1588 correctionField: scaled ns, 2^-16 ns units (encoding variants for row D3;
# the rounding rule of the standard is not verified here).
def scaled_ns_floor(ps):
    return (ps * 65536) // NS


def scaled_ns_round(ps):
    return (ps * 65536 + NS // 2) // NS


# ---------------------------------------------------------------------------------------
class SlaveModel:
    """The INET 4.7.0 gPTP SLAVE_NODE receive path (linklayer/ieee8021as/Gptp.cc), event by event.

    Input events (time-ordered; the caller supplies decoded fields in the chosen mode):
      ('reqtx',  t_end, seq, t_start, spi)        own Pdelay_Req transmitted     (t1 = transmissionStarted, local clock, :607-614)
      ('resprx', t_end, seq, t_start, t2, reqPort) Pdelay_Resp received          (t4 = receptionStarted, :541-547; processPdelayResp :386-399)
      ('rfurx',  t_end, seq, t3, reqPort)         Pdelay_Resp_Follow_Up received (processPdelayRespFollowUp :401-417)
      ('syncrx', t_end, seq, t_start)             Sync received (receptionStarted :554-560; processSync :353-359)
      ('furx',   t_end, seq, pot, cf)             Follow_Up received (processFollowUp :361-374)
    Messages are processed when their reception ends (handleMessage dispatch, :127-160).
    The unsynchronized local clock (localClock) is the ideal underlying clock = simulation time.
    """

    def __init__(self, smoothing=0.1, initial_clock=0, pdelay_override=None):
        self.clk = Clock(initial_clock)
        self.smoothing = smoothing          # Gptp.ned pdelaySmoothingFactor default 0.1
        self.pdelay = -1                    # Gptp.h:184
        self.pdelay_override = pdelay_override
        self.nrr_e = 0                      # neighborRateRatio = 1
        self.gm_e = 0                       # gmRateRatio = 1
        self.prev_resp = None               # (t3, t4) of the previous exchange (:445-458)
        self.prev_src = self.prev_loc = None  # previousSourceTime / previousLocalTime (:419-437)
        self.req = self.resp = self.sync = None
        self.own_spi = None
        self.out = {"pdelay": [], "nrr": [], "gm": [], "fu": [], "ignored": [], "sync_overwritten": 0}

    def feed(self, ev):
        kind, t = ev[0], ev[1]
        if kind == "reqtx":
            _, _, seq, t1, spi = ev
            self.req = {"seq": seq, "t1": t1}
            self.own_spi = spi
            self.resp = None
        elif kind == "resprx":
            _, _, seq, t4, t2, reqport = ev
            # :391-397 requesting port identity and sequence id must match the outstanding request
            if self.req is None or reqport != self.own_spi or seq != self.req["seq"]:
                self.out["ignored"].append(("resp", t, seq))
                return
            self.resp = {"seq": seq, "t4": t4, "t2": t2}
        elif kind == "rfurx":
            _, _, seq, t3, reqport = ev
            if self.req is None or self.resp is None or reqport != self.own_spi or seq != self.req["seq"]:
                self.out["ignored"].append(("rfu", t, seq))
                return
            t4 = self.resp["t4"]
            # computeNeighborRateRatio (:439-458): fromRatio(t3 - t3_prev, t4 - t4_prev)
            if self.prev_resp is not None:
                self.nrr_e = from_integer_ratio(t3 - self.prev_resp[0], t4 - self.prev_resp[1])
                self.out["nrr"].append((t, to_double(self.nrr_e)))
            self.prev_resp = (t3, t4)
            # computePropTime (:461-484): (nRR * (t4 - t1) - (t3 - t2)) / 2, then smoothing
            cur = trunc_div2(mul_round(t4 - self.req["t1"], self.nrr_e) - (t3 - self.resp["t2"]))
            assert cur >= 0 or not STRICT_INET_ASSERTS, "INET ASSERT(currentPdelay >= 0)"
            if self.pdelay == -1:
                self.pdelay = cur
            else:
                self.pdelay = simtime_times_double(cur, self.smoothing) + \
                    simtime_times_double(self.pdelay, 1 - self.smoothing)
            self.out["pdelay"].append((t, self.pdelay))
        elif kind == "syncrx":
            _, _, seq, ts = ev
            if self.sync is not None:
                self.out["sync_overwritten"] += 1
            # syncReceptionStartSynchronized = clock (settable), ...Unsynchronized = localClock (sim time)
            self.sync = {"seq": seq, "ts": ts, "t2": self.clk.at(ts)}
        elif kind == "furx":
            _, _, seq, pot, cf = ev
            if self.sync is None or seq != self.sync["seq"]:
                self.out["ignored"].append(("fu", t, seq))
                self.sync = None  # :141-142 the SLAVE_NODE resets syncReceiverProcess after every Follow_Up
                return
            pd = self.pdelay if self.pdelay_override is None else self.pdelay_override
            assert self.pdelay >= 0 or not STRICT_INET_ASSERTS, "INET ASSERT(pdelay >= 0) (Gptp.cc:221/422)"
            # computeGmRateRatio (:419-437)
            src = pot + cf + pd
            loc = self.sync["ts"]
            if self.prev_src is not None:
                self.gm_e = from_integer_ratio(src - self.prev_src, loc - self.prev_loc)
                self.out["gm"].append((t, to_double(self.gm_e)))
            self.prev_src, self.prev_loc = src, loc
            # synchronize (:195-226) + StepClockServo::adjustClockForDifference
            diff = self.sync["t2"] - src
            now = self.clk.at(t)
            self.clk.set(t, now - diff, to_ppm(self.gm_e))
            self.out["fu"].append({"seq": seq, "ts": loc, "t": t, "t2": self.sync["t2"], "src": src, "diff": diff,
                                   "pd": pd, "cf": cf, "pot": pot,
                                   "new": now - diff, "old": now, "gm_e": self.gm_e})
            self.sync = None

    def run(self, events):
        for ev in sorted(events, key=lambda e: (e[1], _ORDER[e[0]])):
            self.feed(ev)
        return self


_ORDER = {"reqtx": 0, "resprx": 1, "rfurx": 2, "syncrx": 3, "furx": 4}
