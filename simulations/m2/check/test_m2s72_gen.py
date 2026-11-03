#!/usr/bin/env python3
"""Negative tests of tools/m2s72_gen.py (Checkpoint 1 safeguard: the generator must fail on missing, unexpected or
untranslatable required source settings). Each case edits a temporary copy of omnetpp.ini (and copies
../m1/omnetpp.ini beside it), runs the generator on it and must get an error naming the problem; the committed
m2s72.ini is never written. A last case runs the unmodified copy and must succeed with the committed output."""
import importlib.util
import os
import re
import shutil
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
spec = importlib.util.spec_from_file_location("m2s72_gen", os.path.join(M2, "tools", "m2s72_gen.py"))
G = importlib.util.module_from_spec(spec)
spec.loader.exec_module(G)

ORIG = open(os.path.join(M2, "omnetpp.ini")).read()
M1 = os.path.join(M2, "..", "m1", "omnetpp.ini")


def sub(pattern, repl, count=1):
    def f(text):
        new, n = re.subn(pattern, repl, text, count=count, flags=re.M)
        if n == 0:
            raise RuntimeError(f"test setup: pattern {pattern!r} not found")
        return new
    return f


def add_after(header, line):
    return sub(rf"^(\[Config {re.escape(header)}\]\n)", rf"\g<1>{line}\n")


CASES = [
    ("missing required: DS-TT clockIdentity removed", sub(r'^\*\.dsTt\.eth\[1\]\.trafficConditionerLayer\.engine\.clockIdentity = .*\n', ""),
     r"missing required setting \*\.dsTt\.eth\[1\]\.trafficConditionerLayer\.engine\.clockIdentity"),
    ("missing required: ulQfiRules removed (in ../m1/omnetpp.ini)", ("m1", sub(r'^\*\.bearerConfigurator\.ulQfiRules = .*\n', "")),
     r"missing required setting \*\.bearerConfigurator\.ulQfiRules"),
    ("unexpected setting: unknown key in M2S71-base", add_after("M2S71-base", "*.someNewModule.param = 1"),
     r"unexpected setting \*\.someNewModule\.param"),
    ("unexpected setting: a DS-TT identity no per-UE rule knows", add_after("M2S71-base", "*.dsTt.eth[1].trafficConditionerLayer.engine.ttId = 2"),
     r"per-UE identity or address setting without a per-UE rule"),
    ("unexpected setting: a talker address no per-UE rule knows", add_after("M2S71-base", '*.talker.eth[0].address = "0A-AA-00-00-00-0A"'),
     r"per-UE identity or address setting without a per-UE rule"),
    ("allowed: a shared DS-TT setting is vectorised", add_after("M2S71-base", "*.dsTt.eth[1].trafficConditionerLayer.monitor.residenceBound = 5.5ms"),
     None),
    ("untranslatable value: a shared module pointing at talker", add_after("M2S71-base", '*.nwTt.eth[1].trafficConditionerLayer.peer = "talker"'),
     r"untranslatable value naming a per-UE module"),
    ("untranslatable: listener DL flow not to talker (in ../m1/omnetpp.ini)", ("m1", sub(r'^\*\.listener\.app\[0\.\.1\]\.io\.remoteAddress = "talker"', '*.listener.app[0..1].io.remoteAddress = "server"')),
     r"required setting \*\.listener\.app\[0\.\.1\]\.io\.remoteAddress"),
    ("untranslatable: ancestorIndex outside source.*", add_after("M2S71-base", "**.app[0..1].io.steal = ancestorIndex(1) > 0"),
     r"untranslatable ancestorIndex"),
    ("required value: num-rngs changed", sub(r"^num-rngs = 2$", "num-rngs = 3"), r"required setting num-rngs = 3"),
    ("required value: DS-TT ttId changed", sub(r"^\*\.dsTt\.eth\[1\]\.trafficConditionerLayer\.syncOut\.ttId = 2$", "*.dsTt.eth[1].trafficConditionerLayer.syncOut.ttId = 7"),
     r"required setting \*\.dsTt\.eth\[1\]\.trafficConditionerLayer\.syncOut\.ttId = 7"),
    ("staticDrbs entry of another UE", sub(r'ue: "ue\[0\]", drbId: 4, mappedQfis: \[10\]', 'ue: "ue[1]", drbId: 4, mappedQfis: [10]', count=0),
     r'entry without ue: "ue\[0\]"'),
    # Checkpoint 1 rev. 2 (design rev. 2.1 A-1): static listener entry
    ("source sets the listener MAC (owned by M2S72-SL)", add_after("M2S71-base", '*.listener.eth[0].address = "0A-AA-00-00-00-77"'),
     r"which the generated static-listener mixin M2S72-SL owns"),
    ("source sets a UPF MAC-table parameter (owned by M2S72-SL)", add_after("M2S71-base", "*.upf.ethBridge.macTable.agingTime = 300s"),
     r"which the generated static-listener mixin M2S72-SL owns"),
    ("VLAN-42 assumption: base flows on VLAN 43 (in ../m1/omnetpp.ini)", ("m1", sub(r"^\*\*\.app\[0\.\.1\]\.tagger\.vlanId = 42$", "**.app[0..1].tagger.vlanId = 43")),
     r"required setting \*\*\.app\[0\.\.1\]\.tagger\.vlanId = 43, expected 42 \(VLAN of the static listener entry\)"),
    ("VLAN-42 assumption: base-flow VLAN setting removed (in ../m1/omnetpp.ini)", ("m1", sub(r"^\*\*\.app\[0\.\.1\]\.tagger\.vlanId = 42\n", "")),
     r"missing required setting \*\*\.app\[0\.\.1\]\.tagger\.vlanId"),
    ("VLAN-42 assumption: a further flow on VLAN 43", add_after("M2S71-base", "**.app[2].tagger.vlanId = 43"),
     r"traffic on a VLAN other than 42"),
    ("N = 1 only rule requested at N > 1 (load app at N = 2)", ("SOURCES", "M2S71-q0-load", (1, 2)),
     r"(load application app\[3\] has no N > 1 translation|required setting \*\.listener\.numApps = 4, expected 3)"),
    ("N = 1 only rule requested at N > 1 (E-all TT-clock parameters at N = 2)", ("SOURCES", "M2S6-E-all", (1, 2)),
     r"(per-DS-TT TT-clock parameters|missing required setting|required setting)"),
    # Checkpoint 2 rev. 2: asymmetric-load sources (LOAD_UE)
    ("asymmetric load: listener load not addressed to the talker", sub(r'^\*\.listener\.app\[3\]\.io\.remoteAddress = "talker"$', '*.listener.app[3].io.remoteAddress = "server"'),
     r'unexpected \*\.listener\.app\[3\]\.io\.remoteAddress = "server"'),
    ("HARQ16 mixin: an entry no rule translates", add_after("M2S0-harq16", "*.someNewModule.harqProcesses = 16"),
     r"(M2S0-harq16 mixin: \*\.someNewModule\.harqProcesses matches 0 rules|unexpected setting \*\.someNewModule)"),
    ("asymmetric load: a load setting naming a per-UE module", add_after("M2S71-load-sustained", '**.app[3].io.localAddress = "talker"'),
     r"untranslatable value \*\*\.app\[3\]\.io\.localAddress"),
    # Stage 5: load-capable variants (LOAD_REQ: the values the load mixins scale must be the S7.1 L_tot ones)
    ("load variant: L_tot interval not 0.25 ms", sub(r"^(\[Config M2S71-load-sustained\]\n(?:.*\n)*?)\*\*\.app\[3\]\.source\.productionInterval = 0\.25ms$",
                                                   r"\g<1>**.app[3].source.productionInterval = 0.3ms"),
     r"required setting \*\*\.app\[3\]\.source\.productionInterval = 0\.3ms, expected 0\.25ms"),
    ("load variant: L_tot frame length not 1400 B", sub(r"^\*\*\.app\[3\]\.source\.packetLength = 1400B$", "**.app[3].source.packetLength = 1000B"),
     r"required setting \*\*\.app\[3\]\.source\.packetLength = 1000B, expected 1400B"),
    ("load variant: load PCP not 0", sub(r"^\*\*\.app\[3\]\.tagger\.pcp = 0$", "**.app[3].tagger.pcp = 5"),
     r"required setting \*\*\.app\[3\]\.tagger\.pcp = 5, expected 0"),
    ("load variant: load app setting removed", sub(r"^\*\*\.app\[3\]\.source\.initialProductionOffset = 0\.1s \+ 500us\n", ""),
     r"missing required setting \*\*\.app\[3\]\.source\.initialProductionOffset"),
]


def run_case(edit):
    d = tempfile.mkdtemp(prefix="m2s72gen-")
    try:
        os.makedirs(os.path.join(d, "m2", "tools"))
        os.makedirs(os.path.join(d, "m1"))
        m1text = open(M1).read()
        text = ORIG
        saved = dict(G.SOURCES)
        if isinstance(edit, tuple) and edit[0] == "m1":
            m1text = edit[1](m1text)
        elif isinstance(edit, tuple):
            _, cfg, ns = edit
            G.SOURCES[cfg] = (G.SOURCES[cfg][0], ns)
        elif edit is not None:
            text = edit(text)
        open(os.path.join(d, "m2", "omnetpp.ini"), "w").write(text)
        open(os.path.join(d, "m1", "omnetpp.ini"), "w").write(m1text)
        G.INI, G.M2, G.OUT = os.path.join(d, "m2", "omnetpp.ini"), os.path.join(d, "m2"), os.path.join(d, "m2", "m2s72.ini")
        try:
            out, _ = G.generate()
            return None, out, os.path.exists(G.OUT)
        except G.GenError as ex:
            return str(ex), None, os.path.exists(G.OUT)
        finally:
            G.SOURCES.clear()
            G.SOURCES.update(saved)
    finally:
        shutil.rmtree(d)


V = "M2S71-q0-Ca-sus@L"


def _err(fn):
    try:
        fn()
        return None
    except G.GenError as ex:
        return str(ex)


def _ents(spec, extra=()):
    """runconfig-like entries of a load placement as generated (the verify_load_entries input), plus extra entries first"""
    ents = list(extra) + [(f"*.{m}.{r}", v) for (m, r), v in spec.items()]
    ents += [("*.gnb1.cellularNic.mac.harqProcesses", "16"), ("*.ue[*].cellularNic.nrMac.harqProcesses", "16"),
             ("*.listener.eth[0].address", f'"{G.LISTENER_MAC}"'), ("*.numUe", "1")]
    return ents + [(k, "x") for k in G.MACLOG_KEYS]


def _sym8():
    spec, ues, dl, ul = G.load_spec(V, "sym", 8, 1)
    ok = (ues == list(range(8)) and dl == "2000us" and ul == "2000us" and spec[("listener", "numApps")] == "25"
          and spec[("listener.app[17]", "io.remoteAddress")] == '"talker[0]"' and spec[("listener.app[24]", "io.remoteAddress")] == '"talker[7]"'
          and spec[("listener.app[24]", "source.initialProductionOffset")] == G.LOAD_D4 and spec[("talker[7]", "numApps")] == "4")
    return None if ok else f"unexpected sym n8 spec {dl} {ul} {spec[('listener', 'numApps')]}"


def _one0_4():
    spec, ues, dl, ul = G.load_spec(V, "one0", 4, 2)
    ok = (ues == [0] and dl == "125us" and ul == "250us" and spec[("listener", "numApps")] == "10" and spec[("talker[3]", "numApps")] == "3"
          and ("listener.app[9]", "io.remoteAddress") in spec)
    return None if ok else "unexpected one0 n4 spec"


def _foreign():
    G.APPSEL_RESTS[V].setdefault(0, set()).add("source.someNewParameter")
    try:
        G.load_spec(V, "one0", 1, 1)
    finally:
        G.APPSEL_RESTS[V][0].discard("source.someNewParameter")


def _vl(mut, maclog=True):
    spec, *_ = G.load_spec(V, "one0", 1, 2)
    ents = _ents(spec)
    ents = mut(ents)
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return G.verify_load_entries("test", ents, V, "one0", 1, 2, 1, maclog)


def _u0():
    spec, ues, dl, ul = G.load_spec(V, "one0", 2, 1, 0)
    ok = (ul is None and ues == [0] and spec[("talker[0]", "numApps")] == str(G.LISTENER_APPS)
          and not any(m.startswith("talker") and ".app[" in m for m, _ in spec) and spec[("listener", "numApps")] == "6"
          and ("listener.app[5]", "source.productionInterval") in spec)
    return None if ok else f"unexpected u0 spec ul={ul} {sorted(spec)[:4]}"


def _nominal():
    a = G.interval_ns(1, 1.1, nominal=True)
    eff = G.effective_factor(1, 1.1, nominal=True)
    ok = a == 227273 and abs(float(eff) - 1.1) / 1.1 < 1e-5 and G.load_interval(1, 2, nominal=True) == G.load_interval(1, 2) == "125us"
    return None if ok else f"nominal 1.1 -> {a} ns, factor {float(eff)}"


def _e2_all_nominal():
    for o, pl, n, f in G.e2_matrix():
        k = len(G.loaded_ues(pl, n))
        if abs(G.effective_factor(k, f, True) - G.Fraction(str(f))) / G.Fraction(str(f)) > G.E2_NOMINAL_TOL:
            return f"{o} {pl} n{n} f{f} beyond tolerance"
    names = [G.e2_name(*x) for x in G.e2_matrix()]
    if len(names) != 98 or len(set(names)) != 98 or any(pl == "sym" and n == 1 for _, pl, n, _ in G.e2_matrix()):
        return f"E2 matrix {len(names)} configs ({len(set(names))} unique)"
    return None


def _ve(mut, h5=False, n=2, pl="one0", f=1.1):
    spec, *_ = G.load_spec(V, pl, n, f, 0, nominal=True)
    ents = [(f"*.{m}.{r}", v) for (m, r), v in spec.items()]
    ents += [(f"*.talker[{k}].numApps", "3") for k in range(n)]
    ents += ([] if h5 else [("*.gnb1.cellularNic.mac.harqProcesses", "16"), ("*.ue[*].cellularNic.nrMac.harqProcesses", "16")])
    ents += [("*.listener.eth[0].address", f'"{G.LISTENER_MAC}"'), ("*.numUe", str(n))] + [(k, "x") for k in G.MACLOG_KEYS]
    ents = mut(ents)
    import io
    import contextlib
    with contextlib.redirect_stdout(io.StringIO()):
        return G.verify_e2_entries("test", ents, V, pl, n, f, h5)


LOAD_CASES = [
    ("load interval not an integer ns (factor 3)", lambda: _err(lambda: G.load_interval(1, 3)), r"not an integer number of ns"),
    ("load factor 0", lambda: _err(lambda: G.load_spec(V, "one0", 1, 0)), r"must be > 0"),
    ("unknown placement", lambda: _err(lambda: G.load_spec(V, "half", 2, 1)), r"unknown load placement"),
    ("sym at numUe = 1 (one name per configuration)", lambda: _err(lambda: G.load_spec(V, "sym", 1, 1)), r"placement sym at numUe = 1"),
    ("numUe not generated (3)", lambda: _err(lambda: G.load_spec(V, "one0", 3, 1)), r"numUe 3 not generated"),
    ("numUe above NMAX (16)", lambda: _err(lambda: G.loaded_ues("one0", 16)), r"numUe 16 outside"),
    ("not a load-capable variant (plain -sus source)", lambda: _err(lambda: G.load_effective("M2S71-q0-Ca-sus")), r"not a translated load-capable variant"),
    ("a base-flow setting reaching a load app", lambda: _err(_foreign), r"base-flow settings \['source\.someNewParameter'\] of app\[0\] reach load app"),
    ("allowed: sym n8 values exact", _sym8, None),
    ("allowed: one0 n4 DL factor 2 values exact", _one0_4, None),
    ("verify: as generated passes", lambda: None if _vl(lambda e: e) else "verify_load_entries rejected the generated values", None),
    ("verify: DL interval changed is detected", lambda: "detected" if not _vl(lambda e: [("*.listener.app[3].source.productionInterval", "250us")] + e) else None, r"detected"),
    ("verify: a foreign load-app setting is detected", lambda: "detected" if not _vl(lambda e: [("*.listener.app[3].display-string", '"x"')] + e) else None, r"detected"),
    ("verify: a wildcard app setting reaching the load app is detected", lambda: "detected" if not _vl(lambda e: [("**.app[*].source.foo", "1")] + e) else None, r"detected"),
    ("verify: HARQ16 missing is detected", lambda: "detected" if not _vl(lambda e: [x for x in e if "harq" not in x[0]]) else None, r"detected"),
    ("verify: MAC log missing is detected", lambda: "detected" if not _vl(lambda e: [x for x in e if x[0] != "cmdenv-log-prefix"]) else None, r"detected"),
    ("verify: MAC log in a no-log twin is detected", lambda: "detected" if not _vl(lambda e: e, maclog=False) else None, r"detected"),
    # Stage 5 E2 preparation (decision 2026-11-03 20:05): UL factor 0, nominal DL factors, DL-only verification
    ("UL factor negative", lambda: _err(lambda: G.load_spec(V, "one0", 1, 1, -1)), r"must be >= 0 \(UL\)"),
    ("DL factor 0 with UL factor 0", lambda: _err(lambda: G.load_spec(V, "one0", 1, 0, 0)), r"must be > 0"),
    ("exact mode still refuses a non-integer interval (factor 1.1, E0 path)", lambda: _err(lambda: G.load_interval(1, 1.1)), r"not an integer number of ns"),
    ("nominal mode refuses a factor beyond 1e-5 (factor 11, 1 UE)", lambda: _err(lambda: G.interval_ns(1, 11, nominal=True)), r"beyond"),
    ("u0 name suffix", lambda: None if G.load_name("q0", "one0", 1, 1, 0) == "M2S72LD-q0-one0-n1-f1-u0" else G.load_name("q0", "one0", 1, 1, 0), None),
    ("allowed: u0 spec has no UL load app (talker numApps 3, no talker app[3] values)", _u0, None),
    ("allowed: nominal 1.1 rounds to 227273 ns within 1e-5; exact factors unchanged", _nominal, None),
    ("allowed: every E2 factor within tolerance; 98 unique configs, no sym at N = 1", _e2_all_nominal, None),
    ("verify E2: as generated passes (HARQ16)", lambda: None if _ve(lambda e: e) else "verify_e2_entries rejected the generated values", None),
    ("verify E2: as generated passes (HARQ5)", lambda: None if _ve(lambda e: e, h5=True) else "rejected HARQ5", None),
    ("verify E2: sym n8 as generated passes", lambda: None if _ve(lambda e: e, n=8, pl="sym", f=1.3) else "rejected sym n8", None),
    ("verify E2: a talker UL load app (numApps 4) is detected", lambda: "detected" if not _ve(lambda e: [("*.talker[0].numApps", "4")] + e) else None, r"detected"),
    ("verify E2: a talker[k].app[3] setting is detected", lambda: "detected" if not _ve(lambda e: [("*.talker[*].app[3].typename", '"UdpSourceApp"')] + e) else None, r"detected"),
    ("verify E2: a wildcard talker app setting reaching app[3] is detected", lambda: "detected" if not _ve(lambda e: [("**.talker[1].app[*].source.productionInterval", "250us")] + e) else None, r"detected"),
    ("verify E2: DL load interval shifted by 1 ns (listener.app[5], one0 n2) is detected", lambda: "detected" if not _ve(lambda e: [("*.listener.app[5].source.productionInterval", "227272ns")] + e) else None, r"detected"),
    ("verify E2: HARQ16 in an E2H5 config is detected", lambda: "detected" if not _ve(lambda e: e + [("*.gnb1.cellularNic.mac.harqProcesses", "16")], h5=True) else None, r"detected"),
    ("verify E2: HARQ16 missing on one UE is detected", lambda: "detected" if not _ve(lambda e: [("*.ue[1].cellularNic.nrMac.harqProcesses", "5")] + e) else None, r"detected"),
    ("verify E2: MAC log missing is detected", lambda: "detected" if not _ve(lambda e: [x for x in e if x[0] != "cmdenv-log-prefix"]) else None, r"detected"),
]


def load_tests():
    G.INI, G.M2, G.OUT = os.path.join(M2, "omnetpp.ini"), M2, os.path.join(M2, "m2s72.ini")
    G.generate()                      # translation state (LOAD_REC, APPSEL_RESTS) of the unmodified sources
    bad = 0
    for name, fn, expect in LOAD_CASES:
        try:
            res = fn()
        except Exception as ex:      # an unexpected exception fails the case
            res = f"EXCEPTION {type(ex).__name__}: {ex}"
        ok = (res is None) if expect is None else (res is not None and re.search(expect, res) is not None)
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'} | load: {name} | {res if res else 'accepted'}")
    return bad


def main():
    bad = 0
    for name, edit, expect in CASES:
        err, out, wrote = run_case(edit)
        if expect is None:
            ok = err is None and not wrote
            res = "generated (no error expected)" if err is None else f"ERROR {err}"
        else:
            ok = err is not None and re.search(expect, err) is not None and not wrote
            res = f"ERROR {err}" if err else "NO ERROR"
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'} | {name} | {res}")
    # inheritance assertions (rev. 2.1 A-1), on crafted extends maps
    for name, ext, expect in [
        ("T0 inheriting M2S72-SL directly", {"M2S72-T0-x": ["M2S72-SL", "M2S72N1-x", "M2S72B-x"]}, r"T0 config inherits \['M2S72-SL'\]"),
        ("T0 inheriting M2S72-SL through a census config", {"M2S72-T0-x": ["M2S72-F0-q0-n1"], "M2S72-F0-q0-n1": ["M2S72-SL", "M2S72B-x"]},
         r"T0 config inherits"),
        ("T0 inheriting a control mixin", {"M2S72-T0-x": ["M2S72-SLN-age", "M2S72B-x"]}, r"T0 config inherits \['M2S72-SLN-age'\]"),
        ("non-T0 config without M2S72-SL", {"M2S72-F0-q0-n2": ["M2S72-L", "M2S72B-x"]}, r"non-T0 config does not inherit M2S72-SL"),
        ("allowed: census with M2S72-SL, T0 without", {"M2S72-F0-q0-n2": ["M2S72-SL", "M2S72B-x"], "M2S72-T0-x": ["M2S72N1-x", "M2S72B-x"]}, None)]:
        try:
            G.check_inheritance(ext)
            err = None
        except G.GenError as ex:
            err = str(ex)
        ok = (err is None) if expect is None else (err is not None and re.search(expect, err) is not None)
        bad += not ok
        print(f"{'PASS' if ok else 'FAIL'} | inheritance: {name} | {'ERROR ' + err if err else 'accepted'}")
    # Stage 5 load placement (load_spec / load_mixin / verify_load_entries), on the unmodified sources
    nf = load_tests()
    bad += nf
    # the unmodified copy regenerates the committed file (except the header's source path lines, which are relative)
    err, out, wrote = run_case(None)
    committed = open(os.path.join(M2, "m2s72.ini")).read()
    ok = err is None and out == committed
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL'} | unmodified sources in a temporary copy | "
          f"{'identical to the committed m2s72.ini' if ok else (err or 'output differs from the committed m2s72.ini')}")
    print(f"generator negative tests: {len(CASES) + 6 + len(LOAD_CASES) - bad} PASS, {bad} FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
