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

    def ct(s):
        u = u_of(s)
        dd = s - u
        return s + theta0 + floordiv(2 * PS * y * dd + d * dd * dd, 2 * 10 ** 21)
    return ct, u_of


def oracle(ct, u_of, upd, durations_ps, t_end):
    """absolute PeriodicGate transitions t_j = inf { t >= t_(j-1) | C_T(t) >= c_j }, searched segment by segment
    (C_T is monotone only within an update segment); also returns how many changes a forward step made overdue
    (c_j crossed by the step at an update instant u: C_T(u - 1) < c_j < C_T(u) - 1)"""
    c, t, out, j, overdue = ct(0), 0, [], 0, 0
    while True:
        c += durations_ps[j % len(durations_ps)]
        j += 1
        while True:
            end = u_of(t) + upd - 1 if upd > 0 else t_end + 1      # last ps of t's segment
            end = min(end, t_end + 1)
            if ct(end) >= c:
                break
            if end > t_end:
                return out, overdue
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
            return out, overdue
        if upd > 0 and u_of(hi) == hi and ct(hi - 1) < c < ct(hi) - 1:
            overdue += 1
        out.append(hi)
        t = hi


# ---------------------------------------------------------------- running ---------------------------------------
def opp_run(cfg, resdir, extra=()):
    nedpath = ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"),
                        os.path.join(SIMU5G, "src"), os.path.join(INET, "src")])
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", cfg, "-r", "0",
           "-n", nedpath, "-x", "nasctime.nodes;nasctime.simulations.demos;simu5g",
           "-l", os.path.join(INET, "src", "INET"), "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"),
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
        exp, exp_overdue = oracle(ct, u_of, p.get("upd", 0), [MS, MS], T_END)
        changes = [t for t, _ in (got or [])[1:]]           # row 0 is PeriodicGate's initial state at t = 0
        values = [v for _, v in (got or [])]
        ok = (r.returncode == 0 and got is not None and changes == exp
              and values == [(j % 2 == 0) * 1 for j in range(len(values))])    # initially open, then alternating
        check(f"T-clk {cfg}: {len(exp)} gate transitions at exactly the oracle times (ps), alternating", ok,
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

# ---- default-off: no accepted configuration or network references the adapter
hits = subprocess.run(["git", "-C", REPO, "grep", "-l", "TtGateClock", "--", "simulations", "src"], capture_output=True, text=True).stdout.split()
allowed = {"simulations/m2/m2b2/TtGateClockTest.ned", "simulations/m2/m2b2/omnetpp.ini", "simulations/m2/check/test_m2b2_ttgateclock.py",
           "src/nasctime/m2/TtGateClock.cc", "src/nasctime/m2/TtGateClock.h", "src/nasctime/m2/TtGateClock.ned"}
check("T-default-off TtGateClock is referenced only by its own sources, test network and test", set(hits) <= allowed, str(sorted(set(hits) - allowed)))

print(f"\nM2B-2 TtGateClock tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
