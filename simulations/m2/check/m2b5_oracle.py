"""M2B-5 independent TT-time gate oracle (docs/migration/m2b-5-common-epoch.md), shared by the M2B-5 tests.

Built only from: the declared S-CFG/2 schedule (cycle, entries), the declared common base time, and a translator's
TtClock parameters; C_T is re-implemented from TtClock.ned (model A2) in exact integers. It never reads compiled gate
parameters.

Common-epoch semantics: the gate position at TT time c is (c - base) mod cycle; the state is that of the entry covering
the position (half-open [start, start + duration)). The gate initializes at simulation time 0 at TT time C_T(0) (it
must be >= base: future activation is refused). Every later state change is anchored to an absolute TT time
c_j = base + k * cycle + b (b a boundary where the state of the class changes) and happens at
t_j = inf { t >= t_(j-1) | C_T(t) >= c_j } - the IClock / TtGateClock event semantics: a forward 5G time-update step
delivers the changes it jumps over at the step instant (overdue), a backward step never repeats a change already made.
"""
PS = 10 ** 12
NS = 1000


def make_ct(theta0=0, y=0, d=0, upd=0, uoff=0):
    """C_T(s) in integer ps (TtClock.ned, model A2); also .seg(u, s) and .u_of(s)"""
    def u_of(s):
        return uoff + upd * ((s - uoff) // upd) if upd > 0 else 0

    def seg(u, s):
        dd = s - u
        return s + theta0 + (2 * PS * y * dd + d * dd * dd) // (2 * 10 ** 21)

    def ct(s):
        return seg(u_of(s), s)
    ct.u_of, ct.upd, ct.seg = u_of, upd, seg
    return ct


def first_reach(ct, c, t0, tmax):
    """inf { t >= t0 | C_T(t) >= c } within [t0, tmax] (segment by segment: C_T is monotone within one)"""
    t = t0
    while t <= tmax:
        end = min(tmax, ct.u_of(t) + ct.upd - 1) if ct.upd > 0 else tmax
        if ct(end) >= c:
            if ct(t) >= c:
                return t
            lo, hi = t, end
            while hi - lo > 1:
                mid = (lo + hi) // 2
                lo, hi = (lo, mid) if ct(mid) >= c else (mid, hi)
            return hi
        t = end + 1
    return None


def declared(entries, tc, pos_ns):
    for e in entries:
        if e["start_ns"] <= pos_ns < e["start_ns"] + e["duration_ns"]:
            return tc in e["open"]
    raise AssertionError(pos_ns)


def epoch_transitions(entries, cycle_ns, base_ns, tc, ct, t_end):
    """[(t_ps, state)]: the initial state at t = 0, then every change up to t_end; None if C_T(0) < base (refused)"""
    full = epoch_changes(entries, cycle_ns, base_ns, tc, ct, t_end)
    return None if full is None else [(t, st) for t, st, _ in full]


def epoch_changes(entries, cycle_ns, base_ns, tc, ct, t_end):
    """[(t_ps, state, c_ps)] with the TT time c of each change (c of the initial row = C_T(0))"""
    cyc, base = cycle_ns * NS, base_ns * NS
    c0 = ct(0)
    if c0 < base:
        return None
    pos0 = (c0 - base) % cyc
    init = declared(entries, tc, pos0 // NS)            # boundaries are whole ns: floor gives the covering entry
    out = [(0, init, c0)]
    states = [tc in e["open"] for e in entries]
    bounds = sorted((e["start_ns"] * NS, states[j]) for j, e in enumerate(entries) if states[j] != states[j - 1])
    if not bounds:
        return out
    k = (c0 - base) // cyc                              # the cycle containing the initial reading
    t = 0
    while True:
        for b, st in bounds:
            c = base + k * cyc + b
            if c <= c0:                                  # at or before the initial reading: already the initial state
                continue
            t = first_reach(ct, c, t, t_end)
            if t is None:
                return out
            out.append((t, st, c))
        k += 1


def overdue_count(changes, ct):
    """changes delivered at a forward step instant u whose TT time was jumped over (C_old(u) < c < C_new(u))"""
    return sum(1 for t, _, c in changes[1:] if ct.upd > 0 and ct.u_of(t) == t and ct.seg(t - ct.upd, t) < c < ct(t))


def backward_retraversals(changes, ct):
    """changes whose TT time the clock passes again after a backward step (the change is not repeated)"""
    n = 0
    for t, _, c in changes[1:]:
        if ct.upd > 0:
            u = ct.u_of(t) + ct.upd                     # the next update instant after t
            if ct.seg(u - ct.upd, u) > ct(u) and ct(u) < c:   # a backward step back below c
                n += 1
    return n


def position_ps(ct, base_ns, cycle_ns, t):
    """the declared schedule position (ps) at simulation time t"""
    return (ct(t) - base_ns * NS) % (cycle_ns * NS)
