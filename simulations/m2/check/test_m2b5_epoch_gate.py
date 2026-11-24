#!/usr/bin/env python3
"""M2B-5 runtime gate-transition tests of common-epoch gates (TtEpochGate) on the TEST network
simulations/m2/m2b5/EpochGateTest.ned (two translators A and B, each TtClock + TtGateClock + one gate).

For each case the test writes a configuration: TT clock parameters per translator, and the gate parameters of one traffic
class of the declared schedule (scfg/s72-q0-epoch.json, DS-TT schedule) as emitted by the S-CFG/2 compiler (common
epoch, base_time_ns). The recorded gateState vectors are compared, to the picosecond, with the INDEPENDENT oracle
check/m2b5_oracle.py (declared entries + base time + C_T re-implemented from TtClock.ned; never the compiled gate
parameters). Negative controls must fail for their stated reason.

Not a tier-0 suite: needs OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (NED sources) and libnasctime_m2 (src/nasctime/m2/build.sh).
Development test (level 2); no scientific claim.
"""
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
sys.path.insert(0, HERE)
import m2b5_oracle as O  # noqa: E402

spec_ = importlib.util.spec_from_file_location("tsnaf_compile", os.path.join(M2, "tools", "tsnaf_compile.py"))
TC = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(TC)
OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
MODE = os.environ.get("M2B5_MODE", "release")          # debug: opp_run_dbg + INET / nasctime_m2 debug builds (assertions on)
SFX = "_dbg" if MODE == "debug" else ""
PASS, FAIL = [], []
MS = 10 ** 9
T_END = 60 * MS
SCHED = json.load(open(os.path.join(M2, "scfg", "s72-q0-epoch.json")))["tas"]["schedules"][1]


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


def gate_lines(gate, tc, base_ns):
    """the compiler's common-epoch emission for one traffic class of SCHED (via the compiler, not the oracle)"""
    norm = {"cycle": SCHED["cycle_ns"], "phase": 0, "entries": [(e["start_ns"], e["duration_ns"], frozenset(e["open"]))
                                                             for e in SCHED["entries"]]}
    op, durs, off = TC.gate_params(norm, tc)
    return [f"**.{gate}.baseTime = {base_ns}ns", f"**.{gate}.initiallyOpen = {'true' if op else 'false'}",
            f"**.{gate}.durations = [{', '.join(f'{d}ns' for d in durs)}]", f"**.{gate}.offset = {off}ns"]


def tt_lines(tt, p):
    out = [f"**.{tt}.theta0 = {p.get('theta0', 0)}ps", f"**.{tt}.freqOffsetPpb = {p.get('y', 0)}",
           f"**.{tt}.driftPpbPerS = {p.get('d', 0)}"]
    if p.get("upd"):
        out += [f"**.{tt}.updateInterval = {p['upd']}ps", f"**.{tt}.updateOffset = {p.get('uoff', 0)}ps"]
    return out


def run(case, res):
    lines = ["[General]", "network = nasctime.simulations.m2.m2b5.EpochGateTest", "simtime-resolution = ps",
             f"sim-time-limit = {Decimal(T_END) / 10 ** 12}s", "**.source*.packetLength = 64B", "**.source*.productionInterval = 1s",
             "**.gate*.gateState:vector.vector-recording = true", "**.vector-recording = false", "**.scalar-recording = true",
             "**.clockA.ttClockModule = \"^.ttClockA\"", "**.clockB.ttClockModule = \"^.ttClockB\"",
             "**.clock*.numOverdueClockEvents.scalar-recording = true"]
    for side in ("A", "B"):
        lines += tt_lines(f"ttClock{side}", case[side])
        lines += gate_lines(f"gate{side}", case.get("tc", 5), case[side].get("run_base", case[side].get("base", 0)))
    lines += case.get("extra", [])
    with tempfile.TemporaryDirectory() as d:
        ini = os.path.join(d, "epoch.ini")
        open(ini, "w").write("\n".join(lines) + "\n")
        cmd = [os.path.join(OMNETPP, "bin", "opp_run" + SFX), "-u", "Cmdenv", "-f", ini, "-r", "0",
               "-n", ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"), os.path.join(SIMU5G, "src"),
                               os.path.join(INET, "src")]), "-x", "nasctime.nodes;nasctime.simulations.demos;simu5g",
               "-l", os.path.join(INET, "src", "INET"), "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"),
               f"--result-dir={res}", "--cmdenv-express-mode=true"]
        r = subprocess.run(cmd, cwd=d, capture_output=True, text=True, timeout=300)
    vec, sca = {}, {}
    vp = [f for f in os.listdir(res) if f.endswith(".vec")] if os.path.isdir(res) else []
    for f in vp:
        names = {}
        for line in open(os.path.join(res, f)):
            if line.startswith("vector "):
                p = line.split()
                names[p[1]] = p[2]
            elif line[:1].isdigit():
                p = line.split("\t")
                if p[0] in names:
                    vec.setdefault(names[p[0]].split(".")[-1], []).append((int(Decimal(p[2]) * 10 ** 12), p[3].strip() == "1"))
    for f in [f for f in os.listdir(res) if f.endswith(".sca")] if os.path.isdir(res) else []:
        for line in open(os.path.join(res, f)):
            p = line.split()
            if len(p) >= 4 and p[0] == "scalar":
                sca[(p[1].split(".")[-1], p[2])] = p[3]
    return r, vec, sca


def oracle(p, tc=5):
    ct = O.make_ct(p.get("theta0", 0), p.get("y", 0), p.get("d", 0), p.get("upd", 0), p.get("uoff", 0))
    return ct, O.epoch_changes(SCHED["entries"], SCHED["cycle_ns"], p.get("base", 0), tc, ct, T_END)


if not (OMNETPP and INET and SIMU5G):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 and the Simu5G 1.8.1 sources")
    sys.exit(2)
if MODE not in ("release", "debug"):
    print("SKIP: M2B5_MODE must be release or debug")
    sys.exit(2)
print(f"mode {MODE}: opp_run{SFX}, INET{SFX}, nasctime_m2{SFX}" + ("  (INET DEBUG_CHECK_IMPLEMENTATION and ASSERT enabled)" if SFX else ""))

ACC = dict(theta0=300000, y=-100, upd=10 * MS, uoff=3 * MS)       # the accepted DS-TT[0] TT clock (M2S6-E-all)
CASES = {
    "A-identical": {"A": ACC, "B": ACC},
    "init-open": {"A": dict(theta0=1 * MS), "B": dict(theta0=1 * MS + 999999)},
    "init-closed": {"A": dict(theta0=4 * MS), "B": dict(theta0=9 * MS + 999999)},
    "init-boundary": {"A": dict(theta0=2 * MS), "B": dict(theta0=10 * MS)},      # C_T(0) exactly at a boundary
    "base-aligned": {"A": dict(theta0=7 * MS, base=7000000), "B": dict(theta0=123456789, base=123456)},
    "B-offsets": {"A": dict(theta0=1 * MS), "B": dict(theta0=3300 * 10 ** 6)},
    "C-rates": {"A": dict(theta0=1 * MS, y=200000), "B": dict(theta0=1 * MS, y=-200000, d=1000000)},
    "D-forward": {"A": dict(theta0=2001 * 10 ** 6, y=-200000, upd=10 * MS, uoff=3 * MS), "B": ACC, "tc": 1},
    "D-backward": {"A": dict(theta0=1999 * 10 ** 6, y=200000, upd=10 * MS, uoff=3 * MS), "B": ACC, "tc": 1},
    # two gates on ONE TtGateClock whose changes are jumped over by the same forward step: simultaneous overdue events
    "D-simultaneous": {"A": dict(theta0=2001 * 10 ** 6, y=-200000, upd=10 * MS, uoff=3 * MS),
                       "B": dict(theta0=2001 * 10 ** 6, y=-200000, upd=10 * MS, uoff=3 * MS), "tc": 1,
                       "extra": ['**.gateB.clockModule = "^.clockA"']},
}
results = {}
with tempfile.TemporaryDirectory() as root:
    for name, case in CASES.items():
        res = os.path.join(root, name)
        r, vec, sca = run(case, res)
        results[name] = (r, vec, sca)
        tc = case.get("tc", 5)
        for side in ("A", "B"):
            ct, exp = oracle(case[side], tc)
            got = vec.get(f"gate{side}")
            check(f"T5g {name} gate{side}: {len(exp) - 1} transitions equal the common-epoch oracle (ps; initial state included)",
                  r.returncode == 0 and got == [(t, s) for t, s, _ in exp],
                  f"rc {r.returncode} {(r.stdout + r.stderr)[-200:]}; {len(got or [])}/{len(exp)}; first diff "
                  f"{next(((a, b) for a, b in zip(got or [], exp) if a != (b[0], b[1])), None)}")
    # scenario-specific properties
    _, vec, _ = results["A-identical"]
    check("T5g A identical TT clocks: the two translators' transitions coincide exactly", vec.get("gateA") == vec.get("gateB"))
    for name in ("init-open", "init-closed", "init-boundary"):
        _, vec, _ = results[name]
        for side, want in (("A", {"init-open": True, "init-closed": False, "init-boundary": False}[name]),):
            check(f"T5g {name}: initial state {'open' if want else 'closed'} as declared at position (C_T(0) - base) mod cycle; "
                  f"no transition at initialization", vec.get(f"gate{side}", [(None, None)])[0] == (0, want)
                  and all(t > 0 for t, _ in vec.get(f"gate{side}", [])[1:]))
    _, vec, _ = results["base-aligned"]
    ctA, exA = oracle(CASES["base-aligned"]["A"])
    check("T5g base aligned with initialization (C_T(0) = base): position 0, first change at TT time base + 2 ms",
          vec.get("gateA", [None])[0] == (0, True) and exA[1][2] == 7 * MS + 2 * MS)
    _, vec, _ = results["B-offsets"]
    ctA, _ = oracle(CASES["B-offsets"]["A"])
    ctB, _ = oracle(CASES["B-offsets"]["B"])
    posA = {O.position_ps(ctA, 0, SCHED["cycle_ns"], t) for t, _ in vec["gateA"][1:]}
    posB = {O.position_ps(ctB, 0, SCHED["cycle_ns"], t) for t, _ in vec["gateB"][1:]}
    setB = set(vec["gateB"][1:])
    shifted = [(t - 2300 * 10 ** 6, s) for t, s in vec["gateA"][1:] if t - 2300 * 10 ** 6 > 0]
    check(f"T5g B different offsets (theta0 1 ms vs 3.3 ms): every transition at the same TT schedule positions {sorted(posA)} "
          f"while the simulation times differ: each change of A has the same change of B exactly 2.3 ms earlier "
          f"({len(shifted)} pairs)", posA == posB == {0, 2 * MS} and len(shifted) > 5 and all(x in setB for x in shifted)
          and vec["gateA"] != vec["gateB"])
    _, vec, _ = results["C-rates"]
    ideal = [(t, s) for t, s, _ in O.epoch_changes(SCHED["entries"], SCHED["cycle_ns"], 0, 5, O.make_ct(1 * MS), T_END)]
    check("T5g C rates +200 ppm / -200 ppm (+ drift): both differ from an ideal clock and from each other (each follows its own "
          "TT clock, verified above)", vec["gateA"] != ideal and vec["gateB"] != ideal and vec["gateA"] != vec["gateB"])
    r, vec, sca = results["D-forward"]
    ctA, exA = oracle(CASES["D-forward"]["A"], 1)
    od = O.overdue_count(exA, ctA)
    check(f"T5g D forward 5G update steps: {od} gate changes jumped over by a step are delivered at the step instant (oracle) and "
          f"counted by TtGateClock (numOverdueClockEvents = {sca.get(('clockA', 'numOverdueClockEvents'))})",
          od > 0 and sca.get(("clockA", "numOverdueClockEvents")) == str(od))
    r, vec, sca = results["D-simultaneous"]
    ctA, exA = oracle(CASES["D-simultaneous"]["A"], 1)
    od = O.overdue_count(exA, ctA)
    check(f"T5g D simultaneous: two gates on one TtGateClock with {od} overdue changes each at the same update instants: "
          f"identical transitions, both equal to the oracle, the clock counts {2 * od} overdue deliveries",
          od > 0 and vec.get("gateA") == vec.get("gateB") and sca.get(("clockA", "numOverdueClockEvents")) == str(2 * od),
          str(sca.get(("clockA", "numOverdueClockEvents"))))
    r, vec, sca = results["D-backward"]
    ctA, exA = oracle(CASES["D-backward"]["A"], 1)
    br = O.backward_retraversals(exA, ctA)
    diverge = sum(1 for t, s, c in exA[1:] if ctA.upd and ctA(ctA.u_of(t) + ctA.upd) < c)
    check(f"T5g D backward 5G update steps: {br} gate changes whose TT time the clock passes again after a step back are not "
          f"repeated (IClock event semantics); during that re-traversal (at most the step size) the gate state differs from "
          f"the position formula - the documented difference between a clock correction and a reconfiguration",
          br > 0 and sca.get(("clockA", "numOverdueClockEvents")) == "0" and diverge == br)

    # ---- negative controls
    NEG = {
        "future base": ({"A": dict(theta0=1 * MS, base=10000000), "B": ACC}, "base time 0.01 is later than the TT clock at initialization"),
        "negative TT clock at initialization": ({"A": dict(theta0=-1 * MS), "B": ACC}, "later than the TT clock at initialization (-0.001)"),
        "missing gate-clock binding": ({"A": ACC, "B": ACC, "extra": ['**.gateA.clockModule = ""']}, "no clock (clockModule is empty)"),
        "gate on another clock type (simulation-time-like SettableClock)": (
            {"A": ACC, "B": ACC, "extra": ['**.clockA.typename = "inet.clock.model.SettableClock"',
                                           "**.clockA.oscillator.nominalTickLength = 1ps"]}, "is not a nasctime::TtGateClock"),
        "relative scheduling (unsupported across clock steps)": (
            {"A": ACC, "B": ACC, "extra": ["**.gateA.scheduleForAbsoluteTime = false"]}, "scheduleForAbsoluteTime = false is not supported"),
        "runtime schedule reconfiguration": (
            {"A": ACC, "B": ACC, "extra": ["*.hasScenario = true",
                                           '*.scenarioManager.script = xml("<scenario><set-param t=\'0.005\' module=\'gateA\' par=\'offset\' value=\'1ms\'/></scenario>")']},
            "runtime change of 'offset' is not supported"),
    }
    for name, (case, want) in NEG.items():
        r, _, _ = run(case, os.path.join(root, "neg-" + name.replace(" ", "_")))
        out = r.stdout + r.stderr
        check(f"T5g-negative {name}: refused ({want!r})", r.returncode != 0 and want in out, out[-300:])
    # detection negatives: the oracle must see the error
    case = {"A": dict(ACC, run_base=1), "B": ACC}                  # the gate runs with base 1 ns, declared base 0
    r, vec, _ = run(case, os.path.join(root, "neg-base1ns"))
    ct, exp = oracle(ACC)
    d = {a[0] - b[0] for a, b in zip(vec.get("gateA", []), exp) if a[0] != b[0]}
    check("T5g-negative a 1 ns base-time error is detected by the oracle (every change 1 ns of TT time late)",
          r.returncode == 0 and d and d <= {1000, 1001}, str(sorted(d)[:3]))
    case = {"A": dict(theta0=1 * MS), "B": dict(theta0=3300 * 10 ** 6), "extra": ['**.gateB.clockModule = "^.clockA"']}
    r, vec, _ = run(case, os.path.join(root, "neg-wrongclock"))
    ctB, expB = oracle(case["B"])
    check("T5g-negative a gate bound to another translator's TT clock: its runtime schedule position is inconsistent with its own "
          "translator's clock and the oracle detects it", r.returncode == 0 and vec.get("gateB") != [(t, s) for t, s, _ in expB])

print(f"\nM2B-5 common-epoch gate tests ({MODE}): {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
