#!/usr/bin/env python3
"""M2B-5 tests of the S-CFG/2 common-epoch extension of tools/tsnaf_compile.py (docs/migration/m2b-5-common-epoch.md).

No simulation. The relative-phase behaviour stays covered, unchanged, by test_tsnaf_compile.py (S-CFG/1) and
test_tsnaf_compile_tas.py (S-CFG/2). This suite checks: the opt-in (tas.time_reference = "common-epoch"), the backwards
compatibility of relative schedules (byte-identical output, base_time_ns still unsupported without the opt-in), strict
validation of base_time_ns, deterministic emission, and that the emitted TtEpochGate parameters reproduce the declared
gate state at position (C_init - base) mod cycle for any initial TT reading C_init >= base - evaluated with an
INDEPENDENT model of INET PeriodicGate plus the TtEpochGate initial-position rule (offset + C_init - base).
"""
import copy
import importlib.util
import json
import os
import random
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
TOOL = os.path.join(M2, "tools", "tsnaf_compile.py")
SCFG = os.path.join(M2, "scfg")
spec_ = importlib.util.spec_from_file_location("tsnaf_compile", TOOL)
TC = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(TC)
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


REL = json.load(open(os.path.join(SCFG, "s72-q0-tas.json")))
EPOCH = json.load(open(os.path.join(SCFG, "s72-q0-epoch.json")))


def compile_spec(spec, n=2):
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as fh:
        json.dump(spec, fh)
    try:
        return TC.compile_file(fh.name, n)
    finally:
        os.unlink(fh.name)


def errors(spec, n=2):
    try:
        compile_spec(spec, n)
        return None
    except TC.SpecError as ex:
        return ex.problems


def periodic_gate_state(initially_open, durations, offset, t):
    """INET 4.7.0 PeriodicGate (initializeGating / scheduleChangeTimer), independent model: state at clock time t after
    initialization at clock time 0 with initial offset 'offset'"""
    if not durations:
        return initially_open
    total = sum(durations)
    off = offset % total
    is_open, idx = initially_open, 0
    while off > 0 and off >= durations[idx]:
        is_open, off, idx = not is_open, off - durations[idx], (idx + 1) % len(durations)
    nxt = durations[idx] - off
    idx = (idx + 1) % len(durations)
    while nxt <= t:
        is_open = not is_open
        nxt += durations[idx]
        idx = (idx + 1) % len(durations)
    return is_open


def declared(sched, tc, pos):
    for e in sched["entries"]:
        if e["start_ns"] <= pos < e["start_ns"] + e["duration_ns"]:
            return tc in e["open"]
    raise AssertionError(pos)


def parse_gates(text):
    out = {}
    for line in text.splitlines():
        if ".transmissionGate[" not in line or "clockModule" in line:
            continue
        key, val = line.split(" = ", 1)
        head, gate = key.split(".macLayer.queue.transmissionGate[")
        tc, par = gate.split("].")
        prefix, port = head.rsplit(".eth[", 1)
        out.setdefault((prefix, int(port.rstrip("]")), int(tc)), {})[par] = val
    return out


def epoch_equivalence(spec, n=2, rnd=None):
    """for every gate: runtime rule (offset + C_init - base) + PeriodicGate reproduces declared((C_init - base + t) mod
    cycle) at every boundary and midpoint over two cycles, for several initial readings C_init >= base"""
    text = compile_spec(spec, n)
    gates = parse_gates(text)
    bad, count = [], 0
    rnd = rnd or random.Random(5)
    for s in spec["tas"]["schedules"]:
        prefix, port, cyc, base = TC._prefix(s["translator"]), TC.PORTS[s["port"]], s["cycle_ns"], s["base_time_ns"]
        inits = {base, base + 1, base + cyc - 1, base + s["entries"][-1]["start_ns"], base + 7 * cyc + cyc // 3,
                 base + rnd.randrange(0, 50 * cyc)} | {base + e["start_ns"] for e in s["entries"]}
        for tc in range(8):
            g = gates.get((prefix, port, tc))
            if g is None or g.get("typename") != '"nasctime.m2.TtEpochGate"' or g.get("baseTime") != f"{base}ns":
                bad.append((s["id"], tc, "typename/baseTime", g))
                continue
            op = g["initiallyOpen"] == "true"
            inner = g["durations"].strip("[]").strip()
            durs = [int(x.strip()[:-2]) for x in inner.split(",")] if inner else []
            off = int(g["offset"][:-2])
            for c_init in sorted(inits):
                elapsed = c_init - base
                start_off = (off + elapsed) % sum(durs) if durs else 0         # TtEpochGate initial position
                pts = set()
                for k in range(2):
                    for e in s["entries"]:
                        for x in (e["start_ns"], e["start_ns"] + e["duration_ns"] // 2, e["start_ns"] + e["duration_ns"] - 1):
                            pts.add((x - elapsed) % cyc + k * cyc)
                pts.add(0)
                for t in sorted(pts):
                    count += 1
                    if periodic_gate_state(op, durs, start_off, t) != declared(s, tc, (elapsed + t) % cyc):
                        bad.append((s["id"], tc, c_init, t))
    return bad, count, text


# ---------------------------------------------------------------- relative mode unchanged ----------------------------
GEN = os.path.join(M2, "m2b3", "s72-q0-tas.scfg.ini")
check("T5c-compat the M2B-3 relative-phase fragment m2b3/s72-q0-tas.scfg.ini is reproduced byte-identically",
      open(GEN).read() == compile_spec(REL))
check("T5c-compat a relative-phase schedule emits no TtEpochGate / baseTime line", "TtEpochGate" not in compile_spec(REL)
      and "baseTime" not in compile_spec(REL))
rel_explicit = copy.deepcopy(REL)
rel_explicit["tas"]["time_reference"] = "relative-phase"
check("T5c-compat an explicit time_reference \"relative-phase\" compiles byte-identically to the implicit one",
      compile_spec(rel_explicit) == compile_spec(REL))

# ---------------------------------------------------------------- common-epoch emission ------------------------------
bad, cnt, text = epoch_equivalence(EPOCH)
check(f"T5c-gates s72-q0-epoch: every TtEpochGate (typename, baseTime) with the runtime rule reproduces the declared state "
      f"at (C_init - base + t) mod cycle ({cnt} points over several initial readings)", not bad and cnt > 1000, str(bad[:4]))
v1 = TC.compile_file(os.path.join(SCFG, "s72-q0.json"), 2)
check("T5c-prefix the common-epoch output begins with the byte-identical S-CFG/1 output", text.startswith(v1))
check("T5c-deterministic two compilations are byte-identical", compile_spec(EPOCH) == compile_spec(EPOCH))
lines = text.splitlines()
check("T5c-binding the translator lines are those of relative mode (shaper, TtGateClock, explicit gate binding, untagged class)",
      all(l in lines for l in ['*.nwTt.clock.typename = "nasctime.m2.TtGateClock"',
                               '*.dsTt[*].eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"',
                               "*.dsTt[*].eth[*].macLayer.queue.classifier.defaultGateIndex = 7"]))
check("T5c-serialization base_time_ns is serialized as an integer number of ns (baseTime = <n>ns) on every gate",
      sum(1 for l in lines if l.endswith(f".baseTime = {EPOCH['tas']['schedules'][0]['base_time_ns']}ns")) == 16)
rnd = random.Random(156)
rbad, rcnt = [], 0
for case in range(150):
    cyc = rnd.choice([1000, 125000, 1000000, 10000000, 999999937])
    k = rnd.randint(1, 6)
    cuts = sorted(rnd.sample(range(1, cyc), k - 1)) if k > 1 else []
    bounds = [0] + cuts + [cyc]
    ents = [{"start_ns": bounds[j], "duration_ns": bounds[j + 1] - bounds[j],
             "open": sorted(set([7, 5] + [x for x in range(7) if rnd.random() < 0.5]))} for j in range(k)]
    sp = copy.deepcopy(EPOCH)
    sp["tas"]["schedules"] = [{"id": "r", "translator": rnd.choice(["ds-tt", "ds-tt[1]", "nw-tt"]), "port": "tsn",
                               "cycle_ns": cyc, "base_time_ns": rnd.randrange(0, TC.MAX_BASE_NS), "entries": ents}]
    b_, c_, _ = epoch_equivalence(sp, rnd=rnd)
    rbad += b_
    rcnt += c_
check(f"T5c-gates 150 random common-epoch schedules (any base up to the maximum, several initial readings): runtime rule "
      f"reproduces the declared states ({rcnt} points)", not rbad, str(rbad[:3]))


# ---------------------------------------------------------------- negative -------------------------------------------
def mut(f, src=EPOCH):
    s = copy.deepcopy(src)
    f(s)
    return s


def sched(s, i=0):
    return s["tas"]["schedules"][i]


NEG = [
    ("missing base time in explicitly requested common-epoch mode", lambda s: sched(s).pop("base_time_ns"),
     "missing base_time_ns: common-epoch mode (tas.time_reference) requires a common base time"),
    ("conflicting phase_ns and base_time_ns", lambda s: sched(s).__setitem__("phase_ns", 0),
     "conflicting phase_ns and base_time_ns"),
    ("phase_ns instead of base_time_ns in common-epoch mode", lambda s: (sched(s).pop("base_time_ns"), sched(s).__setitem__("phase_ns", 0)),
     "conflicting phase_ns and base_time_ns"),
    ("negative base time", lambda s: sched(s).__setitem__("base_time_ns", -1), "base_time_ns: -1 is not an integer in [0, 9000000000000]"),
    ("base time beyond the exact range (overflowing)", lambda s: sched(s).__setitem__("base_time_ns", TC.MAX_BASE_NS + 1),
     "base_time_ns: 9000000000001 is not an integer"),
    ("base time 2^63", lambda s: sched(s).__setitem__("base_time_ns", 2 ** 63), "base_time_ns: 9223372036854775808 is not an integer"),
    ("base time as float", lambda s: sched(s).__setitem__("base_time_ns", 300000000.0), "base_time_ns: 300000000.0 is not an integer"),
    ("base time as boolean", lambda s: sched(s).__setitem__("base_time_ns", True), "base_time_ns: True is not an integer"),
    ("base time as string", lambda s: sched(s).__setitem__("base_time_ns", "300ms"), "base_time_ns: '300ms' is not an integer"),
    ("unknown time_reference", lambda s: s["tas"].__setitem__("time_reference", "absolute"), "tas.time_reference: 'absolute', expected one of"),
    ("base_time_ns without the opt-in (relative mode: still unsupported)", lambda s: (s["tas"].pop("time_reference"),),
     "unsupported field 'base_time_ns'"),
    ("base_time_ns with explicit relative-phase", lambda s: s["tas"].__setitem__("time_reference", "relative-phase"),
     "unsupported field 'base_time_ns'"),
    ("duplicate schedule id", lambda s: s["tas"]["schedules"].append(dict(copy.deepcopy(sched(s)), translator="ds-tt[1]", port="5gs")),
     "duplicate schedule identity"),
    ("overlapping schedules (ds-tt and ds-tt[0], same port)", lambda s: s["tas"]["schedules"].append(dict(copy.deepcopy(sched(s, 1)), id="second", translator="ds-tt[0]")),
     "overlapping schedules"),
    ("untagged class (gPTP) gated", lambda s: sched(s)["entries"][1].__setitem__("open", [0, 2, 3, 4, 6]),
     "untagged traffic class 7 (gPTP) must be open in every entry"),
    ("stream never transmitted", lambda s: [e.__setitem__("open", [x for x in e["open"] if x != 5]) for e in sched(s, 1)["entries"]],
     "is never transmitted"),
    ("overlapping entries", lambda s: sched(s)["entries"][1].__setitem__("start_ns", sched(s)["entries"][1]["start_ns"] - 1),
     "overlaps the previous entry"),
]
for name, f, want in NEG:
    p = errors(mut(f))
    check(f"T5c-negative {name}", p is not None and any(want in x for x in p), str(p))
p = errors(mut(lambda s: sched(s).pop("phase_ns"), REL))
check("T5c-negative relative schedule without phase_ns: a controlled SpecError (the accepted M2B-3 compiler raised KeyError)",
      p is not None and any("missing required field 'phase_ns'" in x for x in p), str(p))
p = errors(mut(lambda s: sched(s).__setitem__("base_time_ns", 0)))
check("T5c-range base time 0 and the maximum are accepted", p is None and errors(mut(lambda s: sched(s).__setitem__("base_time_ns", TC.MAX_BASE_NS))) is None, str(p))

BADV = [[], {}, None, "x", "", 1, -1, 0, True, False, 1.5, float("nan"), [1, 2], {"a": 1}, 10 ** 30, -10 ** 30]


def paths(o, p=()):
    yield p
    if isinstance(o, dict):
        for k, v in o.items():
            yield from paths(v, p + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from paths(v, p + (i,))


crash, tried = [], 0
for pth in list(paths(EPOCH["tas"])):
    for v in BADV:
        s = copy.deepcopy(EPOCH)
        o = s["tas"]
        if pth:
            for k in pth[:-1]:
                o = o[k]
            o[pth[-1]] = v
        else:
            s["tas"] = v
        tried += 1
        try:
            TC.check(json.loads(json.dumps(s, allow_nan=True)), 2)
        except TC.SpecError:
            pass
        except Exception as ex:                          # noqa: BLE001
            crash.append((pth, v, repr(ex)))
check(f"T5c-fuzz {tried} type substitutions in a common-epoch tas section: a SpecError or a valid result, never a crash",
      not crash, str(crash[:3]))

with tempfile.TemporaryDirectory() as d:
    path = os.path.join(d, "e.json")
    json.dump(EPOCH, open(path, "w"))
    r = subprocess.run([sys.executable, "-I", "-B", TOOL, "emit", path, "--ues", "2"], capture_output=True, text=True)
    check("T5c-cli emit: exit 0, common-epoch S-CFG/2 text on stdout", r.returncode == 0 and r.stdout == compile_spec(EPOCH))
    json.dump(mut(lambda s: sched(s).__setitem__("phase_ns", 0)), open(path, "w"))
    r = subprocess.run([sys.executable, "-I", "-B", TOOL, "emit", path, "--ues", "2"], capture_output=True, text=True)
    check("T5c-cli conflicting phase_ns / base_time_ns: exit 1, nothing on stdout",
          r.returncode == 1 and r.stdout == "" and "conflicting phase_ns and base_time_ns" in r.stderr)
GEN5 = os.path.join(M2, "m2b5", "s72-q0-epoch.scfg.ini")
if os.path.exists(GEN5):
    check("T5c-committed m2b5/s72-q0-epoch.scfg.ini is byte-identical to the compiler output of scfg/s72-q0-epoch.json",
          open(GEN5).read() == compile_spec(EPOCH))

print(f"\nM2B-5 S-CFG/2 common-epoch compiler tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
