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
    ("asymmetric load: a load setting naming a per-UE module", add_after("M2S71-load-sustained", '**.app[3].io.localAddress = "talker"'),
     r"untranslatable value \*\*\.app\[3\]\.io\.localAddress"),
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
    # the unmodified copy regenerates the committed file (except the header's source path lines, which are relative)
    err, out, wrote = run_case(None)
    committed = open(os.path.join(M2, "m2s72.ini")).read()
    ok = err is None and out == committed
    bad += not ok
    print(f"{'PASS' if ok else 'FAIL'} | unmodified sources in a temporary copy | "
          f"{'identical to the committed m2s72.ini' if ok else (err or 'output differs from the committed m2s72.ini')}")
    print(f"generator negative tests: {len(CASES) + 6 - bad} PASS, {bad} FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
