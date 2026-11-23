#!/usr/bin/env python3
"""Tests of tools/tsnaf_compile.py (M2B-1; docs/migration/m2b-scfg-interface.md).

Compatibility oracle (independent of the compiler): for every (source, N) of the accepted S7.2a configurations
(m2s72.ini from tools/m2s72_gen.py, m2s72s5.ini from tools/m2s72s5_gen.py; both committed, never written here), the
EFFECTIVE value of each of the four BearerConfigurator keys is extracted from the committed files by OMNeT++'s
first-match rule over the section chain [M2S72N<N>-<src>, M2S72B-<src>, the base's extends chain], as the exact
entry text (key line plus continuation lines). The compiler's output for the declared specification at N UEs must
equal the concatenation of those entries byte for byte, and must contain no other key. The structural premises of
this extraction are themselves tested (T-premises).
"""
import copy
import hashlib
import importlib.util
import json
import os
import re
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

KEYS = ("dlQfiRules", "drbProfiles", "staticDrbs", "ulQfiRules")
# (committed file, source) -> (specification, N values). Every generated M2S72N<N>-<src> section is listed (T-premises).
CASES = {
    ("m2s72.ini", "q0-idle"): ("s72-q0", (1, 2, 4, 8)), ("m2s72.ini", "qdu-idle"): ("s72-qdu", (1, 2, 4, 8)),
    ("m2s72.ini", "q0-load"): ("s72-q0", (1,)), ("m2s72.ini", "C-a"): ("s72-q0", (1,)),
    ("m2s72.ini", "E-all"): ("s72-q0", (1,)), ("m2s72.ini", "q0-Ca"): ("s72-q0", (1, 2, 4)),
    ("m2s72.ini", "qdu-Ca"): ("s72-qdu", (1, 2, 4)), ("m2s72.ini", "q0-Ca-sus"): ("s72-q0", (2, 4)),
    ("m2s72.ini", "qdu-Ca-sus"): ("s72-qdu", (2, 4)), ("m2s72.ini", "q0-Ca-L"): ("s72-q0", (1, 2, 4, 8)),
    ("m2s72.ini", "qdu-Ca-L"): ("s72-qdu", (1, 2, 4, 8)),
    ("m2s72s5.ini", "q0p-Ca-L"): ("s72-q0p", (1, 2, 4, 8)), ("m2s72s5.ini", "qde-Ca-L"): ("s72-qde", (1, 2, 4, 8)),
}
COMMITTED = {"m2s72.ini": "dfc8a7f7bb7cd1632c335c169cdbd3535e4e90a14b0d04882bb07b406aaf5505",
             "m2s72s5.ini": "e563c489852db4cac7ad8562c97373e2379c8bd4029c7f1ebb9d2ace2ff96903"}

PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


# ---------------------------------------------------------------- independent oracle ------------------------------
def sections(path):
    """{section: [(key, entry text)], ...} and {section: extends list}, in file order; includes are followed"""
    secs, ext, cur = {}, {}, None
    lines = open(path, encoding="utf-8").read().split("\n")
    i = 0
    while i < len(lines):
        l = lines[i]
        m = re.match(r"^include (\S+)$", l)
        if m:
            s2, e2 = sections(os.path.join(os.path.dirname(path), m.group(1)))
            for k, v in s2.items():
                secs.setdefault(k, v)
            ext.update(e2)
        m = re.match(r"^\[(?:Config )?(.+)\]$", l)
        if m:
            cur = m.group(1)
            secs.setdefault(cur, [])
            i += 1
            continue
        m = re.match(r"^([^#\s][^=]*?) = ", l)
        if m and cur is not None:
            block = [l]
            j = i + 1
            while j < len(lines) and re.match(r"^\s+\S", lines[j]):
                block.append(lines[j])
                j += 1
            if m.group(1) == "extends":
                ext[cur] = [x.strip() for x in l.split("=", 1)[1].split(",")]
            secs[cur].append((m.group(1), "\n".join(block)))
            i = j
            continue
        i += 1
    return secs, ext


def chain(sec, ext):
    out = [sec]
    for p in ext.get(sec, []):
        for x in chain(p, ext):
            if x not in out:
                out.append(x)
    return out


def expected(fname, src, n):
    secs, ext = sections(os.path.join(M2, fname))
    order = [f"M2S72N{n}-{src}"] + chain(f"M2S72B-{src}", ext)
    got = {}
    for s in order:
        for k, text in secs.get(s, []):
            m = re.fullmatch(r"\*\.bearerConfigurator\.(\w+)", k)
            if m and m.group(1) not in got:
                got[m.group(1)] = text
    return got


def split_output(text):
    secs = {}
    cur = None
    for l in text.rstrip("\n").split("\n"):
        m = re.match(r"^\*\.bearerConfigurator\.(\w+) = ", l)
        if m:
            cur = m.group(1)
            secs[cur] = l
        else:
            secs[cur] += "\n" + l
    return secs


def spec(name):
    return json.load(open(os.path.join(SCFG, name + ".json")))


def sha(p):
    return hashlib.sha256(open(p, "rb").read()).hexdigest()


# ---------------------------------------------------------------- T-premises -------------------------------------
before = {f: sha(os.path.join(M2, f)) for f in COMMITTED}
check("T-premises committed files are the accepted ones", before == COMMITTED, str(before))
runnable = 0
for fname in COMMITTED:
    secs, ext = sections(os.path.join(M2, fname))
    has_bearer = {x for x, es in secs.items() if any(k.startswith("*.bearerConfigurator.") for k, _ in es)}
    check(f"T-premises {fname}: [General] (this file and its includes) sets no bearer key", "General" not in has_bearer)
    own_text = open(os.path.join(M2, fname), encoding="utf-8").read()
    present = {(m.group(2), int(m.group(1))) for m in re.finditer(r"^\[Config M2S72N(\d+)-(.+)\]$", own_text, re.M)}
    own = {(src, n) for (f, src), (_, ns) in CASES.items() if f == fname for n in ns}
    check(f"T-premises {fname}: the case list covers exactly the per-N mixins generated in this file", present == own,
          f"missing {sorted(present - own)}, extra {sorted(own - present)}")
    # every configuration that extends a source's N mixin and base: within its whole extends chain, only that N mixin
    # and the base chain set bearer keys, and the N mixin comes before the base (so the oracle's order is OMNeT++'s)
    viol = []
    for cfg, ps in ext.items():
        nm = [m for p_ in ps for m in [re.match(r"^M2S72N(\d+)-(.+)$", p_)] if m]
        bm = [p_ for p_ in ps if p_.startswith("M2S72B-")]
        if not nm or not bm or cfg.startswith("M2S72B-"):
            continue
        runnable += 1
        n, src = nm[0].group(1), nm[0].group(2)
        allowed = {f"M2S72N{n}-{src}"} | set(chain(f"M2S72B-{src}", ext))
        setters = [x for x in chain(cfg, ext) if x in has_bearer]
        if len(nm) != 1 or bm != [f"M2S72B-{src}"] or not set(setters) <= allowed or ps.index(nm[0].group(0)) > ps.index(bm[0]):
            viol.append(cfg)
    check(f"T-premises {fname}: in every configuration built on a source, only its N mixin and base chain set bearer "
          f"keys, N mixin first", not viol, str(viol[:5]))
check("T-premises runnable configurations examined", runnable > 0, str(runnable))
print(f"      (premises checked on {runnable} configurations built on an S7.2a source)")

# ---------------------------------------------------------------- T-compat ---------------------------------------
reproduced = []
for (fname, src), (sp, ns) in sorted(CASES.items()):
    for n in ns:
        exp = expected(fname, src, n)
        act = TC.emit(TC.check(spec(sp), n))
        want = "\n".join(exp[k] for k in KEYS if k in exp) + "\n"
        ok = act == want and set(split_output(act)) == set(exp)
        check(f"T-compat {fname} {src} N={n} ({sp}): byte-identical effective bearer entries {sorted(exp)}", ok)
        if ok:
            reproduced.append((fname, src, n, sp, sorted(exp)))
check("T-compat every listed case reproduced", len(reproduced) == sum(len(v[1]) for v in CASES.values()),
      f"{len(reproduced)} reproduced")

# ---------------------------------------------------------------- T-determinism ----------------------------------
s = spec("s72-qdu")
a = TC.emit(TC.check(s, 4))
check("T-determinism repeated compilation is identical", a == TC.emit(TC.check(copy.deepcopy(s), 4)))
r = json.loads(json.dumps(s, sort_keys=True))            # object member order changed
r["drbs"] = list(reversed(r["drbs"]))                     # DRB order changed
r["qos_flows"] = list(reversed(r["qos_flows"]))
r["drb_profiles"] = dict(reversed(list(r["drb_profiles"].items())))
check("T-determinism member, DRB, QoS-flow and profile order do not change the output", TC.emit(TC.check(r, 4)) == a)
r2 = copy.deepcopy(s)
r2["streams"] = [r2["streams"][1], r2["streams"][0], r2["streams"][2]]
b = TC.emit(TC.check(r2, 4))
check("T-determinism stream order sets the (first-match) rule order", b != a and b.index("pcp == 5") < b.index("GptpSync"))

# ---------------------------------------------------------------- T-allowed (not conflicts) ----------------------
def ok_spec(mut, n=2):
    x = spec("s72-qdu")
    mut(x)
    try:
        return TC.emit(TC.check(x, n))
    except TC.SpecError as ex:
        return "ERROR: " + "; ".join(ex.problems)


def add_flow(x, q, drb):
    x["qos_flows"].append({"qfi": q, "drb_id": drb})


def m_ul_per_ue(x):
    x["streams"][2]["ues"] = [0]
    x["streams"].append({"id": "ul-pcp5-ue1", "direction": "ul", "source": "talker", "destination": "listener",
                         "ues": [1], "vid": 42, "pcp": 5, "qfi": 10})
o = ok_spec(m_ul_per_ue)
check("T-allowed the same PCP mapped to different QFIs on different UEs (UL, per-UE scope)",
      'ue: "ue[0]", filter: "expr(has(ieee8021qctag) && ieee8021qctag.pcp == 5)", qfi: 5' in o
      and 'ue: "ue[1]", filter: "expr(has(ieee8021qctag) && ieee8021qctag.pcp == 5)", qfi: 10' in o, o[:200])


def m_ul_dl_differ(x):
    x["streams"][2]["qfi"] = 10
o = ok_spec(m_ul_dl_differ)
check("T-allowed different UL and DL mappings of the same PCP", not o.startswith("ERROR") and "pcp == 5)\", qfi: 10}" in o, o[:200])
o = ok_spec(lambda x: None, n=8)
check("T-allowed a QFI reused by every UE", o.count('mappedQfis: [5]') == 8 and not o.startswith("ERROR"))


def m_same_rule(x):
    x["streams"].append({"id": "dl-pcp5-vid43", "direction": "dl", "source": "listener", "destination": "talker",
                         "ues": [1], "vid": 43, "pcp": 5, "qfi": 5})
o = ok_spec(m_same_rule)
check("T-allowed two streams with the same classifier and QFI give one rule", o.count("pcp == 5)\", qfi: 5}") == 1 + 2, o[:300])

# ---------------------------------------------------------------- T-negative ---------------------------------------
def stream(x, sid):
    return next(s for s in x["streams"] if s["id"] == sid)


def setf(path, val):
    def f(x):
        o = x
        for p in path[:-1]:
            o = stream(o, p) if isinstance(o, dict) and "streams" in o and isinstance(p, str) and p.startswith(("dl-", "ul-")) else o[p]
        o[path[-1]] = val
    return f


def delf(path):
    def f(x):
        o = x
        for p in path[:-1]:
            o = stream(o, p) if isinstance(o, dict) and "streams" in o and isinstance(p, str) and p.startswith(("dl-", "ul-")) else o[p]
        del o[path[-1]]
    return f


def dup_stream(x):
    x["streams"].append(copy.deepcopy(x["streams"][1]))


def conflict_dl(x):
    x["streams"].append({"id": "dl-pcp5-other", "direction": "dl", "source": "listener", "destination": "talker",
                         "ues": "all", "vid": 42, "pcp": 5, "qfi": 10})


def conflict_ul(x):
    x["streams"].append({"id": "ul-pcp5-other", "direction": "ul", "source": "talker", "destination": "listener",
                         "ues": [1], "vid": 42, "pcp": 5, "qfi": 10})


def both_classifiers(x):
    stream(x, "dl-gptp-event")["pcp"] = 6


NEG = [
    ("PCP above 7", setf(["dl-pcp5", "pcp"], 8), "pcp: 8 is not an integer in [0, 7]"),
    ("PCP below 0", setf(["ul-pcp5", "pcp"], -1), "pcp: -1 is not an integer in [0, 7]"),
    ("PCP not an integer (boolean)", setf(["dl-pcp5", "pcp"], True), "pcp: True is not an integer"),
    ("VID 0", setf(["dl-pcp5", "vid"], 0), "vid: 0 is not an integer in [1, 4094]"),
    ("VID 4095", setf(["dl-pcp5", "vid"], 4095), "vid: 4095 is not an integer in [1, 4094]"),
    ("PCP stream without VID", delf(["dl-pcp5", "vid"]), "needs its VLAN ID"),
    ("QFI 0 on a stream", setf(["dl-pcp5", "qfi"], 0), "qfi: 0 is not an integer in [1, 63]"),
    ("QFI 64 on a QoS flow", lambda x: x["qos_flows"].__setitem__(0, {"qfi": 64, "drb_id": 2}), "qfi: 64 is not an integer in [1, 63]"),
    ("unknown endpoint", setf(["dl-pcp5", "destination"], "talker2"), "unknown endpoint 'talker2'"),
    ("unknown UE index", setf(["ul-pcp5", "ues"], [0, 2]), "unknown UE index [2]"),
    ("UE list empty", setf(["ul-pcp5", "ues"], []), "must be \"all\" or a non-empty list"),
    ("invalid direction", setf(["dl-pcp5", "direction"], "both"), "direction: 'both', expected 'dl' or 'ul'"),
    ("DL stream from the UE side", setf(["dl-pcp5", "source"], "talker"), "a DL stream runs from a network-side"),
    ("missing referenced DRB profile", lambda x: x["drbs"][2].__setitem__("profile", "nasc-tsn"), "profile 'nasc-tsn' is not defined"),
    ("conflicting DL classification (shared scope)", conflict_dl, "conflicting DL classification"),
    ("conflicting UL classification on one UE", conflict_ul, "conflicting UL classification for UE 1"),
    ("unsupported top-level field (TAS)", lambda x: x.__setitem__("tas_gate_lists", []), "unsupported field 'tas_gate_lists'"),
    ("unsupported stream field", setf(["dl-pcp5", "max_latency"], 1), "unsupported field 'max_latency'"),
    ("unsupported DRB field", lambda x: x["drbs"][0].__setitem__("pdcpDuplication", True), "unsupported field 'pdcpDuplication'"),
    ("unsupported profile field", lambda x: x["drb_profiles"]["nasc-be"].__setitem__("resourceType", "GBR"), "unsupported field 'resourceType'"),
    ("duplicate stream identity", dup_stream, "duplicate stream identity 'dl-pcp5'"),
    ("wrong schema", lambda x: x.__setitem__("schema", "nasctime-scfg/2"), "schema: 'nasctime-scfg/2'"),
    ("missing streams", lambda x: x.pop("streams"), "missing required field 'streams'"),
    ("no default DRB", lambda x: x["drbs"][0].pop("default"), "exactly one default DRB"),
    ("two default DRBs", lambda x: x["drbs"][1].__setitem__("default", True), "exactly one default DRB"),
    ("duplicate DRB id", lambda x: x["drbs"][2].__setitem__("drb_id", 2), "duplicate DRB id 2"),
    ("duplicate QoS flow", lambda x: x["qos_flows"].append({"qfi": 5, "drb_id": 4}), "QoS flow 5 is declared twice"),
    ("QoS flow on an undefined DRB", lambda x: x["qos_flows"].__setitem__(1, {"qfi": 10, "drb_id": 3}), "DRB 3 is not defined"),
    ("QoS flow on the default DRB", lambda x: x["qos_flows"].__setitem__(1, {"qfi": 10, "drb_id": 1}), "is the default DRB"),
    ("stream QFI without a QoS flow", setf(["ul-pcp5", "qfi"], 7), "QoS flow 7 is not declared"),
    ("both classifiers", both_classifiers, "exactly one classifier"),
    ("no classifier", delf(["dl-pcp5", "pcp"]), "exactly one classifier"),
    ("unknown class", setf(["dl-gptp-event", "class"], "gptp-general"), "class: 'gptp-general'"),
    ("LCG out of range", lambda x: x["drbs"][0].__setitem__("lcg", 8), "lcg: 8 is not an integer in [0, 7]"),
    ("unsupported RLC mode", lambda x: x["drbs"][0].__setitem__("rlc_mode", "TM"), "rlc_mode: 'TM'"),
    ("DRB list empty (incomplete)", lambda x: x.__setitem__("drbs", []), "drbs: must be a non-empty list"),
]
for name, mut, want in NEG:
    x = spec("s72-qdu")
    mut(x)
    try:
        TC.check(x, 2)
        check(f"T-negative {name}", False, "accepted")
    except TC.SpecError as ex:
        msg = "\n".join(ex.problems)
        check(f"T-negative {name}", want in msg, msg)
try:
    TC.check(spec("s72-q0"), 0)
    check("T-negative --ues 0", False, "accepted")
except TC.SpecError as ex:
    check("T-negative --ues 0", "--ues" in ex.problems[0])

# ---------------------------------------------------------------- T-cli (no partial output) ------------------------
def cli(*args, cwd=None):
    r = subprocess.run([sys.executable, "-I", "-B", TOOL, *args], capture_output=True, text=True, cwd=cwd)
    return r.returncode, r.stdout, r.stderr


with tempfile.TemporaryDirectory() as d:
    good = os.path.join(SCFG, "s72-q0.json")
    rc, out, err = cli("emit", good, "--ues", "2", cwd=d)
    check("T-cli emit to stdout from an unrelated directory under -I", rc == 0 and out == TC.compile_file(good, 2), err)
    o = os.path.join(d, "out.ini")
    rc, _, err = cli("emit", good, "--ues", "2", "--out", o)
    check("T-cli emit --out writes the complete result", rc == 0 and open(o).read() == TC.compile_file(good, 2), err)
    rc, _, err = cli("emit", good, "--ues", "4", "--out", o)
    check("T-cli an existing output file is refused and left unchanged", rc == 2 and open(o).read() == TC.compile_file(good, 2), err)
    bad = os.path.join(d, "bad.json")
    x = spec("s72-q0")
    x["streams"][0]["pcp"] = 9
    json.dump(x, open(bad, "w"))
    o2 = os.path.join(d, "never.ini")
    rc, out, err = cli("emit", bad, "--ues", "2", "--out", o2)
    check("T-cli invalid specification: exit 1, no output file, no stdout", rc == 1 and not os.path.exists(o2) and out == "" and "error:" in err)
    rc, out, err = cli("emit", bad, "--ues", "2")
    check("T-cli invalid specification to stdout: nothing printed", rc == 1 and out == "")
    with open(bad, "w") as fh:
        fh.write('{"schema": "nasctime-scfg/1", "schema": "x"}')
    rc, _, err = cli("validate", bad, "--ues", "1")
    check("T-cli duplicate JSON key refused", rc == 1 and "duplicate JSON key" in err, err)
    with open(bad, "w") as fh:
        fh.write("{not json")
    rc, _, err = cli("validate", bad, "--ues", "1")
    check("T-cli malformed JSON refused (exit 1)", rc == 1 and "cannot read a JSON specification" in err, err)
    rc, _, _ = cli("validate", good, "--ues", "1")
    check("T-cli validate exit 0", rc == 0)
    check("T-cli no stray temporary file left", sorted(os.listdir(d)) == ["bad.json", "out.ini"], str(os.listdir(d)))

# ---------------------------------------------------------------- T-isolation ----------------------------------
for g in ("m2s72_gen.py", "m2s72s5_gen.py"):
    r = subprocess.run([sys.executable, "-B", os.path.join("tools", g), "check"], capture_output=True, text=True, cwd=M2)
    check(f"T-isolation accepted generator {g} check: IDENTICAL", r.returncode == 0 and "IDENTICAL" in r.stdout, r.stdout[-200:])
after = {f: sha(os.path.join(M2, f)) for f in COMMITTED}
check("T-isolation committed configurations unchanged by the tests", after == COMMITTED)

print(f"\nTSN AF compiler tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL; "
      f"{len(reproduced)} compatibility cases reproduced")
sys.exit(1 if FAIL else 0)
