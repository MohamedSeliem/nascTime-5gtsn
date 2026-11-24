#!/usr/bin/env python3
"""M2B-2 functional tests of the S-CLK adapter TtGateClock (docs/migration/m2b-2-clock-and-observation.md).

Runs the TEST network simulations/m2/m2b2 (TtClock + TtGateClock + an unmodified INET PeriodicGate) with opp_run
and compares every recorded gate transition with an INDEPENDENT oracle: the TT clock function C_T of the accepted
M2-S6 model A2 (re-implemented here from TtClock.ned's definition, not from the adapter's code), and the IClock step
semantics: with absolute scheduling the j-th transition is anchored to the clock time c_j = C(0) + sum of the first j
durations and occurs at t_j = inf { t >= t_(j-1) | C_T(t) >= c_j }.

Not a tier-0 suite: it needs a built stack. Environment: OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (NED sources only:
other networks under simulations/ import Simu5G types), and libnasctime_m2 built by src/nasctime/m2/build.sh.
Development test only (level 2); no scientific claim.
"""
import os
import re
import subprocess
import sys
import tempfile
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
NET = os.path.join(M2, "m2b2")
OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
MODE = os.environ.get("M2B2_MODE", "release")          # debug: opp_run_dbg + INET / nasctime_m2 debug builds (assertions on)
SFX = "_dbg" if MODE == "debug" else ""
PROBE_LIB = None                                        # set below: the test-only probe library (built outside the repo)
PS = 10 ** 12
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


# ---------------------------------------------------------------- oracle (TtClock.ned model A2) --------------------
def floordiv(a, b):
    return a // b                                       # Python ints: exact floor division


def make_ct(theta0=0, y=0, d=0, upd=0, uoff=0):
    """C_T(s) in integer ps, exactly as TtClock.ned defines it (u(s) = 0 without updates)"""
    def u_of(s):
        return uoff + upd * floordiv(s - uoff, upd) if upd > 0 else 0

    def seg(u, s):                                      # the segment starting at u, evaluated at s
        dd = s - u
        return s + theta0 + floordiv(2 * PS * y * dd + d * dd * dd, 2 * 10 ** 21)

    def ct(s):
        return seg(u_of(s), s)
    ct.seg = seg
    return ct, u_of


def oracle(ct, u_of, upd, durations_ps, t_end):
    """absolute PeriodicGate transitions t_j = inf { t >= t_(j-1) | C_T(t) >= c_j }, searched segment by segment
    (C_T is monotone only within an update segment); also returns how many changes a forward step made overdue
    (c_j jumped over by the forward step at an update instant u: C_old(u) < c_j < C_new(u))"""
    c, t, out, j, overdue, skipped = ct(0), 0, [], 0, 0, 0
    while True:
        c += durations_ps[j % len(durations_ps)]
        j += 1
        while True:
            end = u_of(t) + upd - 1 if upd > 0 else t_end + 1      # last ps of t's segment
            end = min(end, t_end + 1)
            if ct(end) >= c:
                break
            if end > t_end:
                return out, overdue, skipped
            t = end + 1
        lo, hi = t - 1, t                                   # ct(lo) < c <= ct(hi) within one segment
        if ct(t) < c:
            lo, hi = t, end
            while hi - lo > 1:
                mid = (lo + hi) // 2
                if ct(mid) >= c:
                    hi = mid
                else:
                    lo = mid
        if hi > t_end:
            return out, overdue, skipped
        if upd > 0 and u_of(hi) == hi and ct.seg(hi - upd, hi) < c < ct(hi):
            overdue += 1
        elif ct(hi) != c:
            skipped += 1                                # an ordinary change at a clock ps the clock skipped: C(t) > c
        out.append(hi)
        t = hi


# ---------------------------------------------------------------- running ---------------------------------------
def opp_run(cfg, resdir, extra=()):
    nedpath = ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"),
                        os.path.join(SIMU5G, "src"), os.path.join(INET, "src")])
    cmd = [os.path.join(OMNETPP, "bin", "opp_run" + SFX), "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", cfg, "-r", "0",
           "-n", nedpath, "-x", "nasctime.nodes;nasctime.simulations.demos;simu5g",
           "-l", os.path.join(INET, "src", "INET"), "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"),
           *(["-l", PROBE_LIB] if PROBE_LIB else []),
           f"--result-dir={resdir}", "--cmdenv-express-mode=true", *extra]
    return subprocess.run(cmd, cwd=NET, capture_output=True, text=True, timeout=300)


def transitions(resdir, cfg):
    """the gateState vector: [(t_ps, value)] in event order"""
    vec = [f for f in os.listdir(resdir) if f.startswith(cfg + "-") and f.endswith(".vec")]
    if len(vec) != 1:
        return None
    vid, rows = None, []
    for line in open(os.path.join(resdir, vec[0])):
        m = re.match(r"^vector (\d+) \S+ gateState:vector", line)
        if m:
            vid = m.group(1)
        elif vid is not None and re.match(rf"^{vid}\t", line):
            p = line.split("\t")
            rows.append((int(Decimal(p[2]) * PS), int(p[3])))
    return rows


def scalar(resdir, cfg, name):
    for f in os.listdir(resdir):
        if f.startswith(cfg + "-") and f.endswith(".sca"):
            for line in open(os.path.join(resdir, f)):
                p = line.split()
                if len(p) >= 4 and p[0] == "scalar" and p[2] == name:
                    return float(p[3])
    return None


if not (OMNETPP and INET and SIMU5G):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 and the Simu5G 1.8.1 sources")
    sys.exit(2)
if MODE not in ("release", "debug"):
    print("SKIP: M2B2_MODE must be release or debug")
    sys.exit(2)
print(f"mode {MODE}: opp_run{SFX}, INET{SFX}, nasctime_m2{SFX}" + ("  (INET DEBUG_CHECK_IMPLEMENTATION and ASSERT enabled)" if SFX else ""))
PROBE_DIR = tempfile.mkdtemp(prefix="m2b2probe-")
_b = subprocess.run(["bash", os.path.join(NET, "probe", "build.sh"), MODE, PROBE_DIR], capture_output=True, text=True)
if _b.returncode != 0:
    print(f"FAIL  probe library build ({MODE})\n{_b.stdout[-500:]}{_b.stderr[-500:]}")
    sys.exit(1)
PROBE_LIB = os.path.join(PROBE_DIR, "m2b2probe")        # opp_run_dbg appends _dbg to -l names itself

MS = 10 ** 9
T_END = 30 * MS + 500 * 10 ** 3
CASES = {
    "TG-ideal": dict(),
    "TG-offset": dict(theta0=250 * 10 ** 6),
    "TG-rate": dict(y=100000),
    "TG-drift": dict(y=-50000, d=1000000, upd=10 * MS),
    "TG-step-back": dict(y=200000, upd=5 * MS, uoff=500 * 1000),
    "TG-step-fwd": dict(y=-200000, upd=5 * MS, uoff=999500 * 1000),
}
with tempfile.TemporaryDirectory() as res:
    for cfg, p in CASES.items():
        r = opp_run(cfg, res)
        got = transitions(res, cfg) if r.returncode == 0 else None
        ct, u_of = make_ct(**p)
        exp, exp_overdue, exp_skipped = oracle(ct, u_of, p.get("upd", 0), [MS, MS], T_END)
        changes = [t for t, _ in (got or [])[1:]]           # row 0 is PeriodicGate's initial state at t = 0
        values = [v for _, v in (got or [])]
        ok = (r.returncode == 0 and got is not None and changes == exp
              and values == [(j % 2 == 0) * 1 for j in range(len(values))])    # initially open, then alternating
        check(f"T-clk {cfg}: {len(exp)} gate transitions at exactly the oracle times (ps), alternating "
              f"({exp_skipped} at a skipped clock ps, {exp_overdue} overdue)", ok,
              f"rc {r.returncode}; {r.stderr[-300:]}; first differences "
              f"{[(a, b) for a, b in zip(changes, exp) if a != b][:3]}; counts {len(changes)}/{len(exp)}")
        if cfg.startswith("TG-step"):
            steps = len([k for k in range(0, 40) if p["uoff"] + k * p["upd"] <= T_END])   # TtClock also updates at updateOffset
            check(f"T-clk {cfg}: numSteps = {steps} (one per 5G time update, incl. the one at updateOffset)",
                  scalar(res, cfg, "numSteps") == steps, str(scalar(res, cfg, "numSteps")))
            check(f"T-clk {cfg}: numOverdueClockEvents = {exp_overdue} (gate changes crossed by a forward step, oracle)",
                  scalar(res, cfg, "numOverdueClockEvents") == exp_overdue, str(scalar(res, cfg, "numOverdueClockEvents")))
            if cfg == "TG-step-fwd":
                check("T-clk TG-step-fwd: the scenario does exercise overdue execution (oracle count > 0)", exp_overdue > 0, str(exp_overdue))
    # relative scheduling keeps the simulation spacing across steps: identical (within 2 ps) to the same rate without updates
    for cfg in ("TG-step-fwd-relative", "TG-rate-relative"):
        r = opp_run(cfg, res)
        check(f"T-clk {cfg}: runs", r.returncode == 0, r.stderr[-300:])
    a = [t for t, _ in (transitions(res, "TG-step-fwd-relative") or [])]
    b = [t for t, _ in (transitions(res, "TG-rate-relative") or [])]
    check("T-clk relative scheduling: transitions across steps keep their simulation times (|diff| <= 2 ps vs no updates)",
          len(a) == len(b) > 20 and max(abs(x - y) for x, y in zip(a, b)) <= 2,
          f"{len(a)}/{len(b)}; max diff {max((abs(x - y) for x, y in zip(a, b)), default=None)}")
    # ---- negative controls: each must stop with its error
    for cfg, want in (("TGN-no-ttclock", "is not a nasctime::TtClock"), ("TGN-range", "must be <= 1e6"),
                      ("TGN-overdue-error", "overdue after the step"), ("TGN-resolution", "simtime-resolution must be ps")):
        r = opp_run(cfg, res, ["--simtime-resolution=us"] if cfg == "TGN-resolution" else [])
        check(f"T-clk-negative {cfg}: stops with '{want}'", r.returncode != 0 and want in (r.stdout + r.stderr),
              f"rc {r.returncode}; {(r.stdout + r.stderr)[-300:]}")

# ---- step 148 C2 / C3: IClock queries at chosen instants (probe), against the oracle of the contract -----------
MAXRAW, I64 = 2 ** 63 - 1, (-2 ** 63, 2 ** 63 - 1)


def span_of(y, d):
    """the contract's monotone range: C_u non-decreasing on [u, u + span] (None: unbounded, D >= 0)"""
    return None if d >= 0 else ((2 * 10 ** 21 + 2 * PS * y) // (-d) - 1) // 2 + 1


def probe_oracle(p, out):
    """compare every PROBE line with the contract; returns (mismatches, results)"""
    ct, u_of = make_ct(**p)
    seg, upd = ct.seg, p.get("upd", 0)
    span = span_of(p.get("y", 0), p.get("d", 0))
    presented, bad, res = {}, [], []
    for line in out.splitlines():
        f = line.split()
        if not f or f[0] != "PROBE":
            continue
        t = int(f[1])
        u = u_of(t) if upd > 0 else 0
        last = MAXRAW if span is None else min(MAXRAW, u + span)
        if f[2] == "now":
            presented[t] = int(f[3])
            if int(f[3]) != ct(t):
                bad.append((line, ct(t)))
            continue
        kind, tok, side, got = f[2], f[3], f[4], f[5]
        if kind == "inv":
            base = presented[t]
            c = {"min": I64[0], "max": I64[1]}.get(tok)
            if c is None:
                c = base + int(tok[4:]) if tok.startswith("now+") else base - int(tok[4:]) if tok.startswith("now-") else int(tok)
            target = c + (0 if side == "lower" else 1)
            if seg(u, t) >= target:
                exp = t
            elif seg(u, last) < target:
                exp = "ERR"
            else:
                lo, hi = t, last
                while hi - lo > 1:
                    mid = (lo + hi) // 2
                    lo, hi = (lo, mid) if seg(u, mid) >= target else (mid, hi)
                exp = hi
        else:
            s_ = MAXRAW if tok == "smax" else t + int(tok[4:])
            up = seg(u, s_)
            if s_ > last or not I64[0] <= up <= I64[1]:
                exp = "ERR"
            elif side == "upper":
                exp = up
            else:
                prev = seg(u_of(s_ - 1) if upd > 0 else 0, s_ - 1) if s_ == t else seg(u, s_ - 1)
                exp = min(prev + 1, up)
        res.append((t, kind, tok, side, got))
        if str(exp) != got:
            bad.append((line, exp))
    return bad, res


PROBES = {
    "P-rate-pos": dict(y=1000000),
    "P-rate-neg": dict(y=-1000000),
    "P-drift-neg": dict(d=-1000000),
    "P-step-fwd": dict(y=-200000, upd=5 * MS, uoff=999500 * 1000),
    "P-step-back": dict(y=200000, upd=5 * MS, uoff=500 * 1000),
}
with tempfile.TemporaryDirectory() as res:
    outs = {}
    for cfg, p in PROBES.items():
        r = opp_run(cfg, res)
        outs[cfg] = r.stdout
        bad, rr = probe_oracle(p, r.stdout)
        check(f"T-inv {cfg}: {len(rr)} IClock queries equal the contract oracle (results and controlled errors)",
              r.returncode == 0 and len(rr) > 20 and not bad, f"rc {r.returncode}; {bad[:3]}; {r.stderr[-300:]}")
    o = outs["P-rate-pos"]
    check("T-inv P-rate-pos: computeClockTimeFromSimTime(max simtime) beyond clocktime_t -> controlled error (no wrap)",
          o.count("PROBE 0 c2s smax lower ERR") == 1 and "outside the clocktime_t range" in o)
    check("T-inv P-rate-pos: targets 2^62 and INT64_MAX found by the bounded expanding search (no overflow)",
          "inv max lower 9214157878975800007" in o and "inv now+4611686018427387904 lower 4607078939487900004" in o)
    check("T-inv P-rate-pos: negative and minimum clock-time targets -> now (already reached)",
          "PROBE 0 inv min lower 0" in o and "PROBE 1000000000 inv now-1 upper 1000000000" in o)
    o = outs["P-rate-neg"]
    check("T-inv P-rate-neg: INT64_MAX clock time not reached within the simtime_t range -> controlled error",
          "PROBE 0 inv max lower ERR" in o and "is not reached before simulation time" in o)
    o = outs["P-drift-neg"]
    check("T-inv P-drift-neg (D < 0, no updates): target beyond C at the end of the monotone range -> controlled error",
          "PROBE 0 inv now+600000000000000 lower ERR" in o and "PROBE 0 inv now+400000000000000 lower ERR" not in o)
    check("T-inv P-drift-neg: computeClockTimeFromSimTime beyond the monotone range -> controlled error",
          "PROBE 1000000000000 c2s now+1000000000000000 upper ERR" in o and "beyond the range in which the TT clock is non-decreasing" in o
          and "PROBE 1000000000000 c2s now+998000000000000 upper ERR" not in o)
    ct, u_of = make_ct(**PROBES["P-step-fwd"])
    U = 5999500000
    o = outs["P-step-fwd"]
    check("T-inv P-step-fwd at the step instant u: lowerBound = C_old(u-1)+1, upperBound = C_new(u); before u the old "
          "segment is extended", f"PROBE {U} c2s now+0 lower {ct.seg(U - 5 * MS, U - 1) + 1}" in o
          and f"PROBE {U} c2s now+0 upper {ct(U)}" in o and f"PROBE {U - 1} c2s now+1 upper {ct.seg(U - 5 * MS, U)}" in o
          and ct.seg(U - 5 * MS, U - 1) + 1 < ct(U))
    ct, u_of = make_ct(**PROBES["P-step-back"])
    U = 5000500000
    o = outs["P-step-back"]
    check("T-inv P-step-back at u: lowerBound = upperBound = C_new(u) (the interval is empty below the new clock)",
          f"PROBE {U} c2s now+0 lower {ct(U)}" in o and f"PROBE {U} c2s now+0 upper {ct(U)}" in o and ct.seg(U - 5 * MS, U - 1) > ct(U))
    # ---- step 149 (C3-R1): arithmetic boundaries - exact results also where D*d^2 exceeds the int128 range
    ARITH = {
        "P-arith-pos-max": dict(d=1000000),
        "P-arith-pos-min": dict(d=1),
        "P-arith-pos-3": dict(y=-1000000, d=3),
        "P-arith-pos-upd": dict(y=1000000, d=1000000, upd=10 * MS, uoff=MS),
        "P-arith-neg-max": dict(y=1000000, d=-1000000, upd=500 * 10 ** 12),
    }
    I128 = 2 ** 127 - 1
    beyond_total = 0
    for cfg, p in ARITH.items():
        r = opp_run(cfg, res)
        outs[cfg] = r.stdout
        bad, rr = probe_oracle(p, r.stdout)
        ct, u_of = make_ct(**p)
        # queries whose d = s - u (s: the result, or the queried time) makes |D| d^2 exceed the int128 range
        beyond = 0
        for t, kind, tok, side, got in rr:
            u = u_of(t) if p.get("upd", 0) > 0 else 0
            s_ = (int(got) if got != "ERR" else None) if kind == "inv" else (MAXRAW if tok == "smax" else t + int(tok[4:]))
            if s_ is not None and abs(p.get("d", 0)) * (s_ - u) ** 2 > I128:
                beyond += 1
        beyond_total += beyond
        check(f"T-arith {cfg}: {len(rr)} IClock queries equal the exact contract oracle ({beyond} of them with "
              f"|D|*d^2 beyond the int128 range)", r.returncode == 0 and len(rr) >= 8 and not bad,
              f"rc {r.returncode}; {bad[:3]}; {r.stderr[-300:]}")
    check(f"T-arith: the boundary configurations reach the former overflow region ({beyond_total} queries)", beyond_total >= 10,
          str(beyond_total))
    o = outs["P-arith-pos-3"]
    ct, _ = make_ct(y=-1000000, d=3)
    check("T-arith P-arith-pos-3: C(9e18 ps) = exact value in int64 although 3*d^2 > 2^127-1",
          f"PROBE 0 c2s now+9000000000000000000 upper {ct(9 * 10 ** 18)}" in o and 3 * (9 * 10 ** 18) ** 2 > I128
          and ct(9 * 10 ** 18) < 2 ** 63)
    check("T-arith P-arith-pos-max / pos-min: C(max simtime) beyond clocktime_t -> controlled error, no wrap",
          "PROBE 0 c2s smax upper ERR" in outs["P-arith-pos-max"] and "PROBE 0 c2s smax upper ERR" in outs["P-arith-pos-min"]
          and "outside the clocktime_t range" in outs["P-arith-pos-max"])
    check("T-arith P-arith-neg-max: the last ps of the monotone span (1001 s at y = +1e6) is exact, the next is a "
          "controlled error", "PROBE 0 c2s now+1001000000000001 upper ERR" in outs["P-arith-neg-max"]
          and "PROBE 0 c2s now+1001000000000000 upper ERR" not in outs["P-arith-neg-max"])

    r = opp_run("P-skip", res)
    sk = [l.split() for l in r.stdout.splitlines() if l.startswith("SKIP")]
    dl = [list(map(int, l.split()[1:])) for l in r.stdout.splitlines() if l.startswith("DELIVER")]
    ok = (r.returncode == 0 and len(sk) == 1 and sk[0][1] != "none" and len(dl) == 2
          and dl[0][0] == dl[1][0] == int(sk[0][1]) and [d[1] for d in dl] == [int(sk[0][2]), int(sk[0][3])]
          and all(d[1] == d[2] for d in dl))
    check("T-c2 P-skip: events at a skipped clock ps (C(t)-1, C(t)), scheduled in reverse order: delivered at t in "
          "clock-time order, getClockTime() == arrival clock time for each", ok, f"{sk} {dl} {r.stderr[-300:]}")
    r = opp_run("PN-interval", res)
    check("T-inv-negative PN-interval: update interval longer than the monotone range is refused at initialization",
          r.returncode != 0 and "exceeds the range in which C_T is non-decreasing" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-300:])

# ---- default-off: no accepted configuration or network references the adapter
hits = subprocess.run(["git", "-C", REPO, "grep", "-l", "TtGateClock", "--", "simulations", "src"], capture_output=True, text=True).stdout.split()
allowed = {"simulations/m2/m2b2/TtGateClockTest.ned", "simulations/m2/m2b2/omnetpp.ini", "simulations/m2/check/test_m2b2_ttgateclock.py",
           "simulations/m2/m2b2/TtGateClockProbe.ned", "simulations/m2/m2b2/probe/TtGateClockProbe.cc",
           "simulations/m2/m2b2/probe/build.sh", "simulations/m2/m2b2/topology.ini", "simulations/m2/check/test_m2b2_topology.py",
           # M2B-3 (opt-in TAS): the S-CFG/2 compiler emits the binding; test-only configurations and tests
           "simulations/m2/tools/tsnaf_compile.py", "simulations/m2/m2b3/s72-q0-tas.scfg.ini", "simulations/m2/m2b3/tas.ini",
           "simulations/m2/check/test_m2b3_tas_bridge.py", "simulations/m2/check/test_tsnaf_compile_tas.py",
           "src/nasctime/m2/TtGateClock.cc", "src/nasctime/m2/TtGateClock.h", "src/nasctime/m2/TtGateClock.ned"}
check("T-default-off TtGateClock is referenced only by its own sources, test network and test", set(hits) <= allowed, str(sorted(set(hits) - allowed)))

print(f"\nM2B-2 TtGateClock tests ({MODE}): {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
