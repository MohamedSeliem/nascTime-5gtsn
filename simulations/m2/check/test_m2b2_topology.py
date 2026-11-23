#!/usr/bin/env python3
"""M2B-2 step 148 (C4): binding of the S-CLK adapter TtGateClock in the real M2 TT topology (M2S72Bridge).

Runs the TEST-ONLY configurations of simulations/m2/m2b2/topology.ini. Each extends an accepted S7.2a configuration
(M2S72-B-q0-Eall-n2: numUe = 2, the accepted A2 TtClock in every translator's TSN port; m2s72.ini included unchanged)
and only adds the translators' clock slot (and, for C4-tas, egress shaping). sim-time-limit = 1ps: network set-up and
initialization only. The recorded parameters (.sca "par" lines) show what each clock user is bound to.

Not a tier-0 suite: it needs a built stack. Environment: OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (built Simu5G 1.8.1),
libnasctime_m2 built by src/nasctime/m2/build.sh. Configuration validation only (level 2); no traffic, no result.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
NET = os.path.join(M2, "m2b2")
OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
PASS, FAIL = [], []
TRANSLATORS = ["M2S72Bridge.nwTt", "M2S72Bridge.dsTt[0]", "M2S72Bridge.dsTt[1]"]


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


def opp_run(cfg, resdir):
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", "-f", "topology.ini", "-c", cfg, "-r", "0",
           "-n", ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"), os.path.join(SIMU5G, "src"),
                           os.path.join(INET, "src")]), "-x", "nasctime.nodes",
           "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"), "-l", os.path.join(SIMU5G, "src", "simu5g"),
           f"--result-dir={resdir}", "--cmdenv-express-mode=true"]
    return subprocess.run(cmd, cwd=NET, capture_output=True, text=True, timeout=600)


def sca(resdir, cfg):
    """{(module, name): value} for par and scalar lines of the run's .sca"""
    out = {}
    files = [os.path.join(resdir, f) for f in os.listdir(resdir) if f.startswith(cfg + "-") and f.endswith(".sca")]
    sub = os.path.join(resdir, cfg)                     # the accepted configurations write ${resultdir}/${configname}/
    files += [os.path.join(sub, f) for f in (os.listdir(sub) if os.path.isdir(sub) else []) if f.endswith(".sca")]
    for path in files:
            for line in open(path):
                m = re.match(r'^(par|scalar) (\S+) (\S+) (.*)$', line.rstrip("\n"))
                if m:
                    out[(m.group(2), m.group(3))] = m.group(4)
    return out


def unq(v):
    """a recorded string parameter value without its quoting"""
    v = v.strip()
    while len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"')
    return v


if not (OMNETPP and INET and SIMU5G and os.path.exists(os.path.join(SIMU5G, "src", "libsimu5g.so"))):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1")
    sys.exit(2)

with tempfile.TemporaryDirectory() as res:
    r = opp_run("C4-clock", res)
    v = sca(res, "C4-clock")
    check("C4-clock: M2S72-B-q0-Eall-n2 + TtGateClock in the clock slot sets up and initializes (adapter cross-check vs "
          "each translator's TtClock passed)", r.returncode == 0, (r.stdout + r.stderr)[-400:])
    check("C4-clock: one TtGateClock per translator (nwTt, dsTt[0], dsTt[1])",
          all((t + ".clock", "numSteps") in v for t in TRANSLATORS), str([t for t in TRANSLATORS if (t + ".clock", "numSteps") not in v]))
    check("C4-clock: each adapter reads its own translator's TSN-port TtClock (ttClockModule default "
          "^.eth[1].trafficConditionerLayer.ttClock)",
          all(unq(v.get((t + ".clock", "ttClockModule"), "")) == "^.eth[1].trafficConditionerLayer.ttClock" for t in TRANSLATORS))
    bound_off = sorted(k[0] for k, val in v.items() if k[1] == "clockModule" and unq(val).endswith(".clock") and
                       any(unq(val) == t + ".clock" for t in TRANSLATORS))
    print(f"      C4-clock clock users bound to a TtGateClock (egress shaping off): {len(bound_off)} {bound_off[:6]}")
    foreign = [(k[0], unq(val)) for k, val in v.items() for t in TRANSLATORS
               if k[1] == "clockModule" and k[0].startswith(t + ".") and unq(val) in {o + ".clock" for o in TRANSLATORS if o != t}]
    check("C4-clock: no clock user of a translator is bound to another translator's clock", not foreign, str(foreign[:4]))

    r = opp_run("C4-tas-unbound", res)
    v = sca(res, "C4-tas-unbound")
    gates = {k[0]: unq(val) for k, val in v.items() if k[1] == "clockModule" and ".macLayer.queue.transmissionGate[" in k[0]}
    check("C4-tas-unbound: egress shaping on sets up; with INET's defaults alone the shaper gates are NOT bound to the "
          "translator clock (clockModule empty: EthernetSwitch's *.clockModule reaches only direct submodules)",
          r.returncode == 0 and len(gates) == 48 and all(val == "" for val in gates.values()),
          f"rc {r.returncode}; {len(gates)} gates; {sorted(set(gates.values()))[:3]}")

    r = opp_run("C4-tas", res)
    v = sca(res, "C4-tas")
    check("C4-tas: with the explicit gate binding, sets up and initializes (every gate resolves its clock module)",
          r.returncode == 0, (r.stdout + r.stderr)[-400:])
    gates = {k[0]: unq(val) for k, val in v.items() if k[1] == "clockModule" and ".macLayer.queue.transmissionGate[" in k[0]}
    per_tt = {t: [g for g in gates if g.startswith(t + ".")] for t in TRANSLATORS}
    check("C4-tas: every translator has 8 time-aware-shaper gates on each Ethernet port (eth[0] 5GS side, eth[1] TSN side)",
          all(len([g for g in gs if ".eth[0]." in g]) == 8 and len([g for g in gs if ".eth[1]." in g]) == 8 for gs in per_tt.values()),
          str({t: len(gs) for t, gs in per_tt.items()}))

    def resolve(module, rel):
        parts = module.split(".")
        for step in rel.split("."):
            if step == "^":
                parts = parts[:-1]
            else:
                parts.append(step)
        return ".".join(parts)
    wrong = [(g, val) for g, val in gates.items() if resolve(g, val) != g.split(".eth[")[0] + ".clock"]
    check("C4-tas: every transmission gate's clockModule resolves to its own translator's TtGateClock (no gate on "
          "another translator's clock, none on simulation time)", gates and not wrong, str(wrong[:4]))
    print(f"      C4-tas gates per translator: { {t.split('.')[-1]: len(gs) for t, gs in per_tt.items()} }")

    r = opp_run("C4N-no-ttclock", res)
    check("C4N-no-ttclock: TtGateClock in an accepted configuration without TT clocks stops (no ideal fallback)",
          r.returncode != 0 and "is not a nasctime::TtClock" in (r.stdout + r.stderr), (r.stdout + r.stderr)[-300:])

print(f"\nM2B-2 topology binding tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
