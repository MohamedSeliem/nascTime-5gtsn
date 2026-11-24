#!/usr/bin/env python3
"""M2B-3 step 152 (C2): bounded configuration-resolution check of the test-only TAS configuration
simulations/m2/m2b3/tas.ini, config TAS-gated, in M2S72Bridge (docs/migration/m2b-3-tas-qbv.md section 8).

Two levels, both bounded; neither is an experiment:
  query  opp_run -q runconfig only (no network, no simulation), the class of query tier-1 already runs:
         Q1 the effective TAS-gated entries equal the committed S-CFG/2 fragment m2b3/s72-q0-tas.scfg.ini
            (first-match value of every fragment key);
         Q2 the accepted M2S72-B-q0-Eall-n2 has no TAS, gate-clock or gate entry;
         Q3 the accepted m2s72.ini / m2s72s5.ini are byte-identical to their committed sha256.
  setup  (omitted with --queries-only) the network of TAS-gated is built and initialized (sim-time-limit 1 ps,
         parameter recording) and the RESOLVED module parameters are read from the .sca:
         S1 exactly the three translators (nwTt, dsTt[0], dsTt[1]) have INET's Ieee8021qTimeAwareShaper on both
            ports, no other module has one;
         S2 each translator's clock is a TtGateClock reading its own TSN-port TtClock;
         S3 every transmissionGate of every shaped port is a PeriodicGate whose clockModule resolves to its own
            translator's TtGateClock;
         S4 the classifier is PcpTrafficClassClassifier (mode both, untagged class 7); the traffic classes of the
            bridge's PCPs, derived from the RESOLVED mapping table, are PCP 5 -> 5 and PCP 0 -> 1, as the compiler
            assumes (tools/tsnaf_compile.py PCP_TO_TC);
         S5 every gate's initiallyOpen / durations / offset equals the fragment (scheduled TSN ports) or is
            always open (5GS ports).

    python3 -B check_m2b3_tas_config.py [--queries-only] [--config NAME]
(--config runs the same checks on another tas.ini config, e.g. the negative TASN-unbound or TASN-phase, which must fail)
Environment: OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT (built Simu5G 1.8.1); libnasctime_m2 built. Exit 0 all pass,
1 a check failed, 2 environment missing.
"""
import hashlib
import importlib.util
import os
import re
import subprocess
import sys
import tempfile
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
NET = os.path.join(M2, "m2b3")
FRAGMENT = os.path.join(NET, "s72-q0-tas.scfg.ini")
OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
ACCEPTED_SHA = {"m2s72.ini": "dfc8a7f7bb7cd1632c335c169cdbd3535e4e90a14b0d04882bb07b406aaf5505",
                "m2s72s5.ini": "e563c489852db4cac7ad8562c97373e2379c8bd4029c7f1ebb9d2ace2ff96903"}
TRANSLATORS = ["M2S72Bridge.nwTt", "M2S72Bridge.dsTt[0]", "M2S72Bridge.dsTt[1]"]
PASS, FAIL = [], []
QUERIES_ONLY = "--queries-only" in sys.argv[1:]
CFG = sys.argv[sys.argv.index("--config") + 1] if "--config" in sys.argv[1:] else "TAS-gated"   # negative evidence only


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


def opp_run(args, cwd):
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", *args,
           "-n", ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"), os.path.join(SIMU5G, "src"),
                           os.path.join(INET, "src")]), "-x", "nasctime.nodes",
           "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"), "-l", os.path.join(SIMU5G, "src", "simu5g")]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=600)


def runconfig(ini_dir, ini, cfg):
    """[(key, value)] of the flattened configuration, in lookup order"""
    r = opp_run(["-f", ini, "-c", cfg, "-r", "0", "-q", "runconfig"], ini_dir)
    out = []
    for line in r.stdout.splitlines():
        m = re.match(r"^\t(\S.*?) = (.*)$", line)
        if m:
            out.append([m.group(1), m.group(2)])
        elif out and line.startswith(" ") and line.strip():   # continuation of a multi-line value
            out[-1][1] += "\n" + line
    return r.returncode, [tuple(x) for x in out]


def fragment():
    """[(key, value)] of the S-CFG/2 fragment; continuation lines (indented) belong to the previous entry"""
    out = []
    for line in open(FRAGMENT).read().splitlines():
        if line.startswith(" ") and out:
            out[-1][1] += "\n" + line
        elif " = " in line:
            out.append(line.split(" = ", 1))
    return [tuple(x) for x in out]


def to_ps(text):
    """'0s', '0.001s', '1000000ns' -> integer ps (exact)"""
    m = re.fullmatch(r"(-?[0-9.eE+-]+)\s*(s|ms|us|ns|ps)", text.strip())
    scale = {"s": 10 ** 12, "ms": 10 ** 9, "us": 10 ** 6, "ns": 10 ** 3, "ps": 1}[m.group(2)]
    v = Decimal(m.group(1)) * scale
    assert v == v.to_integral_value(), text
    return int(v)


def durations_ps(text):
    inner = text.strip().strip('"').strip("[]").strip()
    return [to_ps(x) for x in inner.split(",")] if inner else []


def unq(v):
    v = v.strip()
    while len(v) >= 2 and v[0] == '"' and v[-1] == '"':
        v = v[1:-1].replace('\\"', '"')
    return v


def resolve(module, rel):
    parts = module.split(".")
    for step in rel.split("."):
        parts = parts[:-1] if step == "^" else parts + [step]
    return ".".join(parts)


if not (OMNETPP and INET and SIMU5G and os.path.exists(os.path.join(SIMU5G, "src", "libsimu5g.so"))):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1")
    sys.exit(2)

# ---------------------------------------------------------------- query level (no simulation) --------------------
FRAG = fragment()
rc, rcfg = runconfig(NET, "tas.ini", CFG)
first = {}
for k, v in rcfg:
    first.setdefault(k, v)
bad = [(k, v, first.get(k)) for k, v in FRAG if first.get(k) != v]
check(f"Q1 {CFG} (-q runconfig): every one of the {len(FRAG)} fragment entries is the effective (first-match) entry "
      f"with the fragment's value (multi-line values compared in full)", rc == 0 and not bad and len(FRAG) == 59, str(bad[:3]))
check(f"Q1 {CFG}: the M2-S1 egress pairer is off on the gated TSN ports (observePort = false)",
      first.get("*.dsTt[*].eth[1].measurementLayer.observePort") == "false"
      and first.get("*.nwTt.eth[1].measurementLayer.observePort") == "false")
rc2, acc = runconfig(M2, "m2s72.ini", "M2S72-B-q0-Eall-n2")
tas_keys = [k for k, v in acc if re.search(r"hasEgressTrafficShaping|transmissionGate|TimeAwareShaper", k + v)
            or (k.endswith(".clock.typename") and "TtGateClock" in v)]
check(f"Q2 the accepted M2S72-B-q0-Eall-n2 ({len(acc)} entries): no egress shaping, gate or gate-clock entry",
      rc2 == 0 and len(acc) > 300 and not tas_keys, str(tas_keys[:3]))
shas = {f: hashlib.sha256(open(os.path.join(M2, f), "rb").read()).hexdigest() for f in ACCEPTED_SHA}
check("Q3 the accepted m2s72.ini and m2s72s5.ini are byte-identical to their committed sha256", shas == ACCEPTED_SHA, str(shas))
nq = len(PASS) + len(FAIL)

# ---------------------------------------------------------------- setup level (network resolution, 1 ps) ----------
if not QUERIES_ONLY:
    with tempfile.TemporaryDirectory() as res:
        r = opp_run(["-f", "tas.ini", "-c", CFG, "-r", "0", "--sim-time-limit=1ps", "--**.param-recording=true",
                     f"--result-dir={res}", "--cmdenv-express-mode=true"], NET)
        par = {}
        sca = os.path.join(res, CFG, "0.sca")
        if os.path.exists(sca):
            for line in open(sca):
                m = re.match(r"^par (\S+) (\S+) (.*)$", line.rstrip("\n"))
                if m:
                    par[(m.group(1), m.group(2))] = m.group(3)
    check(f"S0 {CFG}: the M2S72Bridge network is built and initialized (all stages; sim-time-limit 1 ps)",
          r.returncode == 0 and len(par) > 1000, (r.stdout + r.stderr)[-300:])
    shapers = sorted(m for (m, n), v in par.items() if n == "typename" and unq(v) == "inet.linklayer.ieee8021q.Ieee8021qTimeAwareShaper")
    want = sorted(f"{t}.eth[{p}].macLayer.queue" for t in TRANSLATORS for p in (0, 1))
    check(f"S1 exactly the 3 translators have the native INET Ieee8021qTimeAwareShaper on both ports ({len(shapers)} "
          f"shaped ports, no other module)", shapers == want, str(shapers))
    check("S2 each translator's clock is a TtGateClock reading its own TSN-port TtClock (nasctime.m2.TtClock)",
          all(unq(par.get((f"{t}.clock", "typename"), "")) == "nasctime.m2.TtGateClock"
              and unq(par.get((f"{t}.eth[1].trafficConditionerLayer.ttClock", "typename"), "")) == "nasctime.m2.TtClock"
              and resolve(f"{t}.clock", unq(par.get((f"{t}.clock", "ttClockModule"), ""))) == f"{t}.eth[1].trafficConditionerLayer.ttClock"
              for t in TRANSLATORS))
    gates = {m: v for (m, n), v in par.items() if n == "clockModule" and ".macLayer.queue.transmissionGate[" in m}
    wrong = [(m, v) for m, v in gates.items() if resolve(m, unq(v)) != m.split(".eth[")[0] + ".clock"
             or unq(par.get((m, "typename"), "")) != "inet.queueing.gate.PeriodicGate"]
    check(f"S3 every transmissionGate of every shaped port ({len(gates)}) is a PeriodicGate bound to its own "
          f"translator's TtGateClock", len(gates) == 48 and not wrong, str(wrong[:3]))
    spec_ = importlib.util.spec_from_file_location("tsnaf_compile", os.path.join(M2, "tools", "tsnaf_compile.py"))
    TC = importlib.util.module_from_spec(spec_)
    spec_.loader.exec_module(TC)
    cls_ok, cls_detail = True, []
    for q in want:
        c = f"{q}.classifier"
        mapping = [[int(x) for x in row.split(",")] for row in re.findall(r"\[([0-9, ]+)\]", par.get((c, "mapping"), ""))]
        ntc = int(par.get((q, "numTrafficClasses"), "0"))
        resolved = tuple(row[ntc - 1] for row in mapping) if len(mapping) == 8 and ntc == 8 else None
        ok = (unq(par.get((c, "typename"), "")) == "inet.linklayer.ieee8021q.PcpTrafficClassClassifier"
              and unq(par.get((c, "mode"), "")) == "both" and par.get((c, "defaultGateIndex")) == "7"
              and resolved == TC.PCP_TO_TC and resolved[5] == 5 and resolved[0] == 1)
        cls_ok &= ok
        if not ok:
            cls_detail.append((q, resolved))
    check("S4 every shaped port classifies with PcpTrafficClassClassifier (mode both, untagged -> class 7); the RESOLVED "
          "mapping table gives PCP 5 -> TC 5 and PCP 0 -> TC 1, equal to the compiler's PCP_TO_TC", cls_ok, str(cls_detail[:2]))
    expected = {}
    for k, v in FRAG:                                      # concrete expected gate parameters from the fragment
        m = re.fullmatch(r"\*\.(nwTt|dsTt\[\*\])\.eth\[(\d)\]\.macLayer\.queue\.transmissionGate\[(\d)\]\.(initiallyOpen|durations|offset)", k)
        if m:
            tts = ["M2S72Bridge.nwTt"] if m.group(1) == "nwTt" else ["M2S72Bridge.dsTt[0]", "M2S72Bridge.dsTt[1]"]
            for t in tts:
                expected[(f"{t}.eth[{m.group(2)}].macLayer.queue.transmissionGate[{m.group(3)}]", m.group(4))] = v
    mism, scheduled = [], 0
    for t in TRANSLATORS:
        for p in (0, 1):
            for tc in range(8):
                g = f"{t}.eth[{p}].macLayer.queue.transmissionGate[{tc}]"
                exp_open = expected.get((g, "initiallyOpen"), "true")
                exp_dur = durations_ps(expected.get((g, "durations"), "[]"))
                exp_off = to_ps(expected.get((g, "offset"), "0s"))
                got = (par.get((g, "initiallyOpen")), durations_ps(par.get((g, "durations"), "x")),
                       to_ps(par.get((g, "offset"), "x")))
                scheduled += bool(exp_dur)
                if got != (exp_open, exp_dur, exp_off):
                    mism.append((g, got, (exp_open, exp_dur, exp_off)))
    check(f"S5 the resolved initiallyOpen / durations / offset of all 48 gates equal the fragment ({scheduled} gates with "
          f"a schedule on the TSN ports; every other gate always open)", not mism and scheduled == 6, str(mism[:3]))

ns = len(PASS) + len(FAIL) - nq
print(f"\nM2B-3 TAS configuration resolution: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL "
      f"(query level {nq}, setup level {ns})")
sys.exit(1 if FAIL else 0)
