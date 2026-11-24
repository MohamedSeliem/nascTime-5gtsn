#!/usr/bin/env python3
"""M2B-3 tests of the S-CFG/2 TAS extension of tools/tsnaf_compile.py (docs/migration/m2b-3-tas-qbv.md).

No simulation. The S-CFG/1 behaviour (37 compatibility cases, 147 checks) stays covered, unchanged, by
test_tsnaf_compile.py; this suite checks S-CFG/2: schema, strict validation (invalid and overlapping schedules),
deterministic serialisation, the S-CFG/1 prefix property, and the emitted PeriodicGate parameters against an
INDEPENDENT re-implementation of INET 4.7.0 PeriodicGate (initializeGating / scheduleChangeTimer) evaluated at every
gate-control boundary.
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


def load(name):
    with open(os.path.join(SCFG, name)) as fh:
        return json.load(fh)


BASE = load("s72-q0-tas.json")
OTHER = [0, 2, 3, 4, 6, 7]


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


# ---------------------------------------------------------------- independent PeriodicGate model (INET 4.7.0) -------
def periodic_gate_state(initially_open, durations, offset, t):
    """state at clock time t after the gate's initialization at clock time 0, following PeriodicGate exactly:
    initializeGating skips whole durations covered by offset (toggling), then the first change is at duration - offset"""
    if not durations:
        return initially_open
    total = sum(durations)
    off = offset % total
    is_open, idx = initially_open, 0
    while off > 0 and off >= durations[idx]:
        is_open, off, idx = not is_open, off - durations[idx], (idx + 1) % len(durations)
    nxt = durations[idx] - off                          # clock time of the next change
    idx = (idx + 1) % len(durations)
    while nxt <= t:
        is_open = not is_open
        nxt += durations[idx]
        idx = (idx + 1) % len(durations)
    return is_open


def spec_state(sched, tc, t):
    """the declared state of tc at clock time t, the gate's initialization being at schedule position phase_ns"""
    pos = (sched["phase_ns"] + t) % sched["cycle_ns"]
    for e in sched["entries"]:
        if e["start_ns"] <= pos < e["start_ns"] + e["duration_ns"]:
            return tc in e["open"]
    raise AssertionError("position not covered")


def parse_gate_lines(text):
    """{(prefix, port, tc): (initiallyOpen, [ns], offset ns)} from emitted S-CFG/2 lines"""
    out = {}
    for line in text.splitlines():
        if ".transmissionGate[" not in line or "clockModule" in line:
            continue
        key, val = line.split(" = ", 1)
        head, gate = key.split(".macLayer.queue.transmissionGate[")
        tc, par = gate.split("].")
        prefix, port = head.rsplit(".eth[", 1)
        k = (prefix, int(port.rstrip("]")), int(tc))
        d = out.setdefault(k, {})
        if par == "initiallyOpen":
            d["open"] = val == "true"
        elif par == "durations":
            inner = val.strip("[]").strip()
            d["durations"] = [int(x.strip()[:-2]) for x in inner.split(",")] if inner else []
        elif par == "offset":
            d["offset"] = int(val[:-2])
    return {k: (v["open"], v["durations"], v["offset"]) for k, v in out.items()}


def gate_equivalence(spec, n=2):
    """every emitted gate reproduces the declared state at every entry boundary and midpoint over two cycles"""
    text = compile_spec(spec, n)
    gates = parse_gate_lines(text)
    bad, count = [], 0
    for s in spec["tas"]["schedules"]:
        prefix = TC._prefix(s["translator"])
        port = TC.PORTS[s["port"]]
        for tc in range(8):
            g = gates.get((prefix, port, tc))
            if g is None:
                bad.append((s["id"], tc, "missing"))
                continue
            pts = set()
            for k in range(2):
                for e in s["entries"]:
                    for x in (e["start_ns"], e["start_ns"] + e["duration_ns"] // 2, e["start_ns"] + e["duration_ns"] - 1):
                        pts.add((x - s["phase_ns"]) % s["cycle_ns"] + k * s["cycle_ns"])
            for t in sorted(pts):
                count += 1
                if periodic_gate_state(*g, t) != spec_state(s, tc, t):
                    bad.append((s["id"], tc, t))
    return bad, count, text


# ---------------------------------------------------------------- positive ---------------------------------------
bad, cnt, text = gate_equivalence(BASE)
check(f"T2-gates s72-q0-tas: every PeriodicGate reproduces the declared gate states ({cnt} boundary points, 16 gates)",
      not bad and cnt > 100, str(bad[:5]))
v1 = TC.compile_file(os.path.join(SCFG, "s72-q0.json"), 2)
check("T2-prefix the S-CFG/2 output begins with the byte-identical S-CFG/1 output of the same bearer part",
      text.startswith(v1) and len(text) > len(v1))
check("T2-deterministic two compilations are byte-identical", compile_spec(BASE) == compile_spec(BASE))
ok_all = True
for name in ("s72-q0.json", "s72-qdu.json", "s72-q0p.json", "s72-qde.json"):
    s = load(name)
    s2 = copy.deepcopy(s)
    s2["schema"] = "nasctime-scfg/2"
    s2["tas"] = {"untagged_tc": 7, "schedules": [{"id": "x", "translator": "ds-tt", "port": "tsn", "cycle_ns": 1000000,
                                                   "phase_ns": 0, "entries": [{"start_ns": 0, "duration_ns": 1000000,
                                                                               "open": list(range(8))}]}]}
    for n in (1, 2, 4):
        a, b = TC.compile_file(os.path.join(SCFG, name), n), compile_spec(s2, n)
        ok_all &= b.startswith(a) and "hasEgressTrafficShaping" not in a
check("T2-prefix every committed S-CFG/1 specification at N = 1, 2, 4: S-CFG/2 output = S-CFG/1 output + TAS lines",
      ok_all)
emitted = [l for l in text.splitlines() if l.startswith("*.dsTt") or l.startswith("*.nwTt")]
check("T2-binding each scheduled translator gets the shaper, TtGateClock and the explicit gate clock binding",
      all(f'{p}.eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"' in emitted
          and f'{p}.clock.typename = "nasctime.m2.TtGateClock"' in emitted and f"{p}.hasEgressTrafficShaping = true" in emitted
          for p in ("*.nwTt", "*.dsTt[*]")))
check("T2-untagged the untagged traffic class (gPTP) is the classifier default class",
      "*.dsTt[*].eth[*].macLayer.queue.classifier.defaultGateIndex = 7" in emitted)
g = parse_gate_lines(text)
check("T2-values DS-TT TC5 open 2 ms of 10 ms; TC1 (PCP 0) closed 5 ms then open 5 ms; NW-TT TC1 closed 1 ms, open 3 ms, offset 1 ms",
      g[("*.dsTt[*]", 1, 5)] == (True, [2000000, 8000000], 0) and g[("*.dsTt[*]", 1, 1)] == (False, [5000000, 5000000], 0)
      and g[("*.nwTt", 1, 1)] == (False, [1000000, 3000000], 1000000) and g[("*.dsTt[*]", 1, 7)] == (True, [], 0)
      and g[("*.dsTt[*]", 1, 0)] == (True, [], 0))

# random schedules: rotation, merging and phase handled for any layout
rnd = random.Random(148)
rbad, rcnt = [], 0
for case in range(300):
    cyc = rnd.choice([1000, 125000, 1000000, 10000000, 999999937])
    k = rnd.randint(1, 7)
    cuts = sorted(rnd.sample(range(1, cyc), k - 1)) if k > 1 else []
    bounds = [0] + cuts + [cyc]
    ents = [{"start_ns": bounds[j], "duration_ns": bounds[j + 1] - bounds[j],
             "open": sorted(set([7] + [x for x in range(7) if rnd.random() < 0.5]))} for j in range(k)]
    sp = copy.deepcopy(BASE)
    sp["tas"]["schedules"] = [{"id": "r", "translator": rnd.choice(["ds-tt", "ds-tt[1]", "nw-tt"]), "port": rnd.choice(["tsn", "5gs"]),
                               "cycle_ns": cyc, "phase_ns": rnd.randrange(cyc), "entries": ents}]
    if any(5 not in e["open"] for e in ents) and all(5 not in e["open"] for e in ents):
        ents[0]["open"] = sorted(set(ents[0]["open"]) | {5})
    try:
        b_, c_, _ = gate_equivalence(sp)
    except TC.SpecError as ex:
        b_, c_ = [("spec error", ex.problems)], 0
    rbad += b_
    rcnt += c_
check(f"T2-gates 300 random schedules (1 .. 7 entries, any phase, both ports, three translator forms): every gate "
      f"reproduces the declared states ({rcnt} boundary points)", not rbad, str(rbad[:3]))

# ---------------------------------------------------------------- negative ---------------------------------------
def mut(f):
    s = copy.deepcopy(BASE)
    f(s)
    return s


def sched(s, i=0):
    return s["tas"]["schedules"][i]


def entries(s, i=0):
    return sched(s, i)["entries"]


def add_second(s, translator, port="tsn"):
    x = copy.deepcopy(sched(s))
    x["id"], x["translator"], x["port"] = "second", translator, port
    s["tas"]["schedules"].append(x)


NEG = [
    ("S-CFG/2 without the tas section", lambda s: s.pop("tas"), "requires the 'tas' section"),
    ("S-CFG/1 with a tas section", lambda s: s.__setitem__("schema", "nasctime-scfg/1"), "unsupported field 'tas'"),
    ("unknown schema", lambda s: s.__setitem__("schema", "nasctime-scfg/3"), "schema: 'nasctime-scfg/3'"),
    ("tas not an object", lambda s: s.__setitem__("tas", []), "tas: must be an object"),
    ("tas unknown field", lambda s: s["tas"].__setitem__("hold", 1), "tas: unsupported field 'hold'"),
    ("untagged_tc missing", lambda s: s["tas"].pop("untagged_tc"), "missing required field 'untagged_tc'"),
    ("untagged_tc out of range", lambda s: s["tas"].__setitem__("untagged_tc", 8), "tas.untagged_tc: 8 is not an integer in [0, 7]"),
    ("untagged_tc boolean", lambda s: s["tas"].__setitem__("untagged_tc", True), "tas.untagged_tc: True"),
    ("schedules empty", lambda s: s["tas"].__setitem__("schedules", []), "tas.schedules: must be a non-empty list"),
    ("schedule unknown field", lambda s: sched(s).__setitem__("base_time_ns", 0), "unsupported field 'base_time_ns'"),
    ("schedule id invalid", lambda s: sched(s).__setitem__("id", "Bad Id"), "schedule identity 'Bad Id'"),
    ("duplicate schedule id", lambda s: sched(s, 1).__setitem__("id", "dl-ds-tt"), "duplicate schedule identity 'dl-ds-tt'"),
    ("unknown translator", lambda s: sched(s).__setitem__("translator", "upf"), "translator: 'upf'"),
    ("DS-TT index beyond the UEs", lambda s: sched(s).__setitem__("translator", "ds-tt[2]"), "'ds-tt[2]' does not exist"),
    ("unknown port", lambda s: sched(s).__setitem__("port", "eth1"), "port: 'eth1'"),
    ("cycle below 1 us", lambda s: sched(s).__setitem__("cycle_ns", 999), "cycle_ns: 999 is not an integer in [1000, 1000000000]"),
    ("cycle above 1 s", lambda s: sched(s).__setitem__("cycle_ns", 1000000001), "cycle_ns: 1000000001"),
    ("cycle as float", lambda s: sched(s).__setitem__("cycle_ns", 1e7), "cycle_ns: 10000000.0"),
    ("phase equal to the cycle", lambda s: sched(s).__setitem__("phase_ns", 10000000), "phase_ns: 10000000 is not an integer in [0, 9999999]"),
    ("negative phase", lambda s: sched(s).__setitem__("phase_ns", -1), "phase_ns: -1"),
    ("no entries", lambda s: sched(s).__setitem__("entries", []), "entries: must be a list of 1 .. 256"),
    ("too many entries", lambda s: sched(s).__setitem__("entries", [{"start_ns": i, "duration_ns": 1, "open": [7]} for i in range(257)]),
     "entries: must be a list of 1 .. 256"),
    ("entry missing duration", lambda s: entries(s)[1].pop("duration_ns"), "missing required field 'duration_ns'"),
    ("entry unknown field (hold)", lambda s: entries(s)[1].__setitem__("operation", "hold"), "unsupported field 'operation'"),
    ("zero duration", lambda s: entries(s)[1].__setitem__("duration_ns", 0), "duration_ns: 0 is not an integer in [1, 1000000000]"),
    ("open not a list", lambda s: entries(s)[0].__setitem__("open", "5"), "open: '5' must be a list"),
    ("traffic class 8", lambda s: entries(s)[0].__setitem__("open", [7, 8]), "must be a list of traffic classes in [0, 7]"),
    ("traffic class listed twice", lambda s: entries(s)[0].__setitem__("open", [5, 5, 7]), "a traffic class is listed twice"),
    ("first entry not at 0 (gap)", lambda s: entries(s)[0].__setitem__("start_ns", 1), "gap before the entry (0 .. 1 ns"),
    ("overlapping entries", lambda s: entries(s)[1].__setitem__("start_ns", 1999999), "overlaps the previous entry"),
    ("gap between entries", lambda s: entries(s)[2].__setitem__("start_ns", 5000001), "gap before the entry (5000000 .. 5000001 ns"),
    ("entries extend beyond the cycle", lambda s: entries(s)[2].__setitem__("duration_ns", 5000001), "(they extend beyond the cycle)"),
    ("entries end before the cycle", lambda s: entries(s)[2].__setitem__("duration_ns", 4999999), "(gap at the end of the cycle)"),
    ("untagged class (gPTP) gated", lambda s: entries(s)[1].__setitem__("open", [1, 2, 3, 4, 6]), "untagged traffic class 7 (gPTP) must be open in every entry"),
    ("overlapping schedules ds-tt and ds-tt[0]", lambda s: add_second(s, "ds-tt[0]"), "overlapping schedules: 'dl-ds-tt' and 'second' both configure the gates of ds-tt[0] port tsn"),
    ("overlapping schedules nw-tt twice", lambda s: add_second(s, "nw-tt"), "both configure the gates of nw-tt port tsn"),
    ("stream never transmitted (PCP 5 closed in every DS-TT entry)", lambda s: [e.__setitem__("open", [x for x in e["open"] if x != 5]) for e in entries(s)],
     "stream 'dl-pcp5' (traffic class 5) is never transmitted at ds-tt[0] port tsn"),
    ("UL stream never transmitted at the NW-TT", lambda s: [e.__setitem__("open", [x for x in e["open"] if x != 5]) for e in entries(s, 1)],
     "stream 'ul-pcp5' (traffic class 5) is never transmitted at nw-tt port tsn"),
]
for name, f, want in NEG:
    p = errors(mut(f))
    check(f"T2-negative {name}", p is not None and any(want in x for x in p), str(p))

# PCP -> traffic class follows INET's PcpTrafficClassClassifier default (802.1Q Table 8-5): PCP 0 -> TC 1, PCP 1 -> TC 0
check("T2-pcp-map PCP_TO_TC is INET 4.7.0's default mapping at 8 classes (PCP 0 -> 1, PCP 1 -> 0, PCP 2..7 -> 2..7)",
      TC.PCP_TO_TC == (1, 0, 2, 3, 4, 5, 6, 7))


def add_pcp0_stream(s):
    s["streams"].append({"id": "dl-pcp0", "direction": "dl", "source": "listener", "destination": "talker", "ues": "all",
                         "vid": 42, "pcp": 0, "qfi": 5})


def close_tc_everywhere(s, tc, i=0):
    for e in entries(s, i):
        e["open"] = [x for x in e["open"] if x != tc]


p = errors(mut(lambda s: (add_pcp0_stream(s), close_tc_everywhere(s, 1))))
check("T2-pcp-map a PCP 0 stream whose class (TC 1) is closed in every entry is refused, naming traffic class 1",
      p is not None and any("stream 'dl-pcp0' (traffic class 1) is never transmitted" in x for x in p), str(p))
p = errors(mut(lambda s: (add_pcp0_stream(s), close_tc_everywhere(s, 0))))
check("T2-pcp-map closing TC 0 (PCP 1) does not affect a PCP 0 stream", p is None, str(p))

# disjoint schedules on different ports / translators are not overlaps
p = errors(mut(lambda s: add_second(s, "ds-tt[1]", "5gs")))
check("T2-disjoint ds-tt (tsn) and ds-tt[1] (5gs) are not an overlap", p is None, str(p))

# type fuzz: any value at any TAS path is either accepted or a SpecError, never a crash
BADV = [[], {}, None, "x", "", 1, -1, 0, True, False, 1.5, float("nan"), [1, 2], ["all"], [[0]], {"a": 1}, 10 ** 30, -10 ** 30]


def paths(o, p=()):
    yield p
    if isinstance(o, dict):
        for k, v in o.items():
            yield from paths(v, p + (k,))
    elif isinstance(o, list):
        for i, v in enumerate(o):
            yield from paths(v, p + (i,))


crash, tried = [], 0
for pth in list(paths(BASE["tas"])):
    for v in BADV:
        s = copy.deepcopy(BASE)
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
check(f"T2-fuzz {tried} type substitutions in the tas section: a SpecError or a valid result, never a crash", not crash, str(crash[:3]))

# CLI: emit writes the TAS lines; an invalid schedule exits 1 without output
with tempfile.TemporaryDirectory() as d:
    good = os.path.join(d, "g.json")
    json.dump(BASE, open(good, "w"))
    r = subprocess.run([sys.executable, "-I", "-B", TOOL, "emit", good, "--ues", "2"], capture_output=True, text=True)
    check("T2-cli emit: exit 0, S-CFG/2 text on stdout", r.returncode == 0 and r.stdout == compile_spec(BASE))
    bad_ = os.path.join(d, "b.json")
    json.dump(mut(lambda s: entries(s)[1].__setitem__("start_ns", 1999999)), open(bad_, "w"))
    r = subprocess.run([sys.executable, "-I", "-B", TOOL, "emit", bad_, "--ues", "2"], capture_output=True, text=True)
    check("T2-cli invalid schedule: exit 1, nothing on stdout, the error on stderr",
          r.returncode == 1 and r.stdout == "" and "overlaps the previous entry" in r.stderr)

# the committed generated fragment is the compiler output
GEN = os.path.join(M2, "m2b3", "s72-q0-tas.scfg.ini")
if os.path.exists(GEN):
    check("T2-committed m2b3/s72-q0-tas.scfg.ini is byte-identical to the compiler output of scfg/s72-q0-tas.json (N = 2)",
          open(GEN).read() == compile_spec(BASE))

print(f"\nM2B-3 S-CFG/2 TAS compiler tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
