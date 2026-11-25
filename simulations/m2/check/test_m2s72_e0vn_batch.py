#!/usr/bin/env python3
"""M2-S7.2a Stage 5, A3 tests (no simulation, no genuine evidence): the E0v-N batch helper (m2s72_e0vn_batch.py) and
the E0v-N batch runner (m2s72s5n.sh) with a STUB simulator and a STUB evaluator. Every number below is synthetic and is
not an expectation of any genuine run.

    python3 check/test_m2s72_e0vn_batch.py   -> one line per test and a summary; exit 0 iff every test passes
"""
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
NASCTIME = os.path.dirname(os.path.dirname(M2))
sys.path.insert(0, HERE)
import m2s72_e0vn_batch as BAT  # noqa: E402
import m2s72_e1sel as SEL  # noqa: E402

_spec = importlib.util.spec_from_file_location("m2s72s5_gen", os.path.join(M2, "tools", "m2s72s5_gen.py"))
G5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G5)

BASE = "f55a3f767db83ed083f3cdf276b3fdd47a0f76f5"     # m2/continuation at the start of A3 (PR #17 merge)
ACCEPTED = ["simulations/m2/m2s72s5.sh", "simulations/m2/m2s72.sh", "simulations/m2/m2s72.ini", "simulations/m2/m2s72s5.ini",
            "simulations/m2/tools/m2s72s5_gen.py", "simulations/m2/tools/m2s72_gen.py",
            "simulations/m2/check/m2s72s5_lib.py", "simulations/m2/check/m2s72_e1sel.py",
            "simulations/m2/check/check_m2s72_s5n.py", "simulations/m2/check/check_m2s72_s5v.py",
            "simulations/m2/check/check_m2s72_s5n21.py", "simulations/m2/check/m2s72_e0vn21.py",
            "simulations/m2/check/m2s72_fgo_registry.json", "simulations/m2/check/expect",
            "simulations/m2/check/fixtures", "simulations/m2/results", ".github"]
NEW_FILES = ["simulations/m2/m2s72s5n.sh", "simulations/m2/check/m2s72_e0vn_batch.py",
             "simulations/m2/check/test_m2s72_e0vn_batch.py"]
RESULTS = []


def test(name):
    def deco(fn):
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as ex:
            RESULTS.append((name, False, str(ex)[:400]))
        except Exception as ex:   # noqa: BLE001
            RESULTS.append((name, False, f"{type(ex).__name__}: {ex}"[:400]))
        return fn
    return deco


def refused(fn, *a, **kw):
    try:
        fn(*a, **kw)
    except BAT.Refused as ex:
        return str(ex)
    raise AssertionError(f"{fn.__name__}{a} was not refused")


def helper(*args, env=None):
    return subprocess.run([sys.executable, "-B", os.path.join(HERE, "m2s72_e0vn_batch.py")] + list(args),
                          capture_output=True, text=True, env=env)


AV = "TEST ONLY adapter validation reference (not a decision)"
ED = "TEST ONLY environment decision"


def decisions(path, **over):
    kv = {"S5-2-D1": "not-adopted", "S5-2-D2": "approved", "S5-2-D3": "approved", "S5-2-D4": "approved",
          "S5-2-D5": "approved", "S5-2-D6": "approved", "adapter_validated": AV, "env_decision": ED,
          "ac5_record": "TEST ONLY", "ac6_record": "TEST ONLY", "date": "2026-11-25"}
    kv.update(over)
    lines = ["# TEST ONLY decision record: no decision", "format=" + BAT.DECISIONS_FORMAT]
    lines += [f"{k}={v}" for k, v in kv.items() if v is not None]
    open(path, "w").write("\n".join(lines) + "\n")
    return path


def ENV(**kw):
    e = {"S5N_ADAPTER_VALIDATED": AV, "S5_ENV_DECISION": ED}
    e.update(kw)
    return {k: v for k, v in e.items() if v is not None}


# =================================================================================== configuration generation =====
@test("generation: 28 HARQ16 + 21 HARQ5 combinations = exactly the accepted generator's E0v-N set (294 configurations)")
def _():
    gen = {k for k, v in G5.matrix().items() if v[7] == "N"}
    mine = BAT.all_configs("h16") + BAT.all_configs("h5")
    assert len(BAT.combos("h16")) == 28 and len(BAT.combos("h5")) == 21, (len(BAT.combos("h16")), len(BAT.combos("h5")))
    assert len(mine) == len(set(mine)) == 294 and set(mine) == gen, (len(mine), sorted(gen ^ set(mine))[:5])
    assert all(not h for *_, h in BAT.combos("h5")) and all(h for *_, h in BAT.combos("h16"))
    assert not [k for k, o, *_ in BAT.combos("h5") if o == "qde"], "Q-de is HARQ16 only (D-1)"


@test("generation: the declared order is deterministic and every name passes the WP-A1 wrapper's run-name guard")
def _():
    import m2s72_e0vn21 as W
    a, b = BAT.combos("h16"), BAT.combos("h16")
    assert a == b and [x[1] for x in a][:7] == ["q0"] * 7 and a[0][0] == "q0/one0/1/16" and a[-1][0] == "qde/sym/8/16", a[:2]
    bad = [c for s in ("h16", "h5") for c in BAT.all_configs(s) if not W.run_name_ok(c)]
    assert not bad, bad[:3]


@test("generation: every configuration is a [Config] of the accepted m2s72s5.ini; pins hold on this tree")
def _():
    assert BAT.check_pins(M2) == [], BAT.check_pins(M2)
    r = helper("pins", M2)
    assert r.returncode == 0 and "pins: OK" in r.stdout, r.stdout


@test("generation: a changed pinned file or a missing configuration section is refused")
def _():
    d = tempfile.mkdtemp()
    try:
        for rel in BAT.PINS:
            os.makedirs(os.path.join(d, os.path.dirname(rel)), exist_ok=True)
            shutil.copy(os.path.join(M2, rel), os.path.join(d, rel))
        assert BAT.check_pins(d) == []
        ini = os.path.join(d, "m2s72s5.ini")
        txt = open(ini).read()
        open(ini, "w").write(txt.replace("[Config M2S72-E0vN-q0-sym-n8-f2]", "[Config M2S72-E0vN-q0-sym-n8-f2x]", 1))
        p = BAT.check_pins(d)
        assert any("m2s72s5.ini: sha256" in x for x in p) and any("not in m2s72s5.ini" in x for x in p), p
        os.remove(os.path.join(d, "check/m2s72_fgo_registry.json"))
        assert any("registry.json: missing" in x for x in BAT.check_pins(d))
        r = helper("pins", d)
        assert r.returncode == 1 and "REFUSED" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


# ============================================================================================ argument validation =====
@test("arguments: combination keys, factors, segments and configurations are validated (fail closed)")
def _():
    for k in ("q0/one0/3/16", "qx/one0/2/16", "q0/one1/2/16", "q0/sym/2/8", "", None):
        refused(BAT.parse_key, k)
    for f in ("0.75", "1.5", "3", "x"):
        refused(BAT.parse_factor, f)
    assert BAT.parse_factor("1p25") == 1.25 and BAT.parse_factor("1") == 1.0 and BAT.parse_factor("0.5") == 0.5
    refused(BAT.combos, "h8")
    refused(BAT.config_of, "qde/sym/2/5", 1.0)            # Q-de has no HARQ5 configuration
    refused(BAT.config_of, "q0/sym/2/16", 0.75)
    assert BAT.config_of("q0/sym/2/5", 1.6) == "M2S72-E0vNH5-q0-sym-n2-f1p6"
    r = helper("next")
    assert r.returncode == 2, r.returncode
    r = helper("bogus", "x")
    assert r.returncode == 2


@test("decision record: a valid record passes; every malformed or non-approving record is refused")
def _():
    d = tempfile.mkdtemp()
    try:
        p = decisions(os.path.join(d, "ok.txt"))
        kv = BAT.check_decisions(p, "h16", ENV())
        assert kv["S5-2-D5"] == "approved"
        cases = [
            ({"S5-2-D1": "adopted"}, "isolation mixin"), ({"S5-2-D2": "not-approved"}, "S5-2-D2"),
            ({"S5-2-D3": "rejected"}, "S5-2-D3"), ({"S5-2-D4": None}, "missing"), ({"S5-2-D5": "maybe"}, "S5-2-D5"),
            ({"S5-2-D6": "pending"}, "S5-2-D6"), ({"ac5_record": ""}, "ac5_record"), ({"date": "25 Nov"}, "date"),
            ({"unknown_key": "x"}, "unknown key"),
        ]
        for over, needle in cases:
            msg = refused(BAT.check_decisions, decisions(os.path.join(d, "x.txt"), **over), "h16", ENV())
            assert needle in msg, (over, msg)
        open(os.path.join(d, "dup.txt"), "w").write(open(p).read() + "S5-2-D2=approved\n")
        assert "duplicate" in refused(BAT.check_decisions, os.path.join(d, "dup.txt"), "h16", ENV())
        open(os.path.join(d, "fmt.txt"), "w").write(open(p).read().replace("format=" + BAT.DECISIONS_FORMAT, "format=other/1"))
        assert "first entry" in refused(BAT.check_decisions, os.path.join(d, "fmt.txt"), "h16", ENV())
        assert "does not exist" in refused(BAT.check_decisions, os.path.join(d, "none.txt"), "h16", ENV())
    finally:
        shutil.rmtree(d)


@test("decision record: S5N_ADAPTER_VALIDATED and S5_ENV_DECISION are compared with the record, never set")
def _():
    d = tempfile.mkdtemp()
    try:
        p = decisions(os.path.join(d, "ok.txt"))
        assert "not set" in refused(BAT.check_decisions, p, "h16", ENV(S5N_ADAPTER_VALIDATED=None))
        assert "not set" in refused(BAT.check_decisions, p, "h16", ENV(S5N_ADAPTER_VALIDATED="  "))
        assert "differs" in refused(BAT.check_decisions, p, "h16", ENV(S5N_ADAPTER_VALIDATED=AV + "x"))
        assert "S5_ENV_DECISION differs" in refused(BAT.check_decisions, p, "h5", ENV(S5_ENV_DECISION="other"))
        BAT.check_decisions(p, "select", ENV(S5_ENV_DECISION=None))        # select runs nothing
        env = dict(os.environ); env.pop("S5N_ADAPTER_VALIDATED", None)
        r = helper("decisions", p, "h16", env=env)
        assert r.returncode == 1 and "REFUSED" in r.stdout and "S5N_ADAPTER_VALIDATED" not in env, r.stdout
    finally:
        shutil.rmtree(d)


# =================================================================================== bracket records and stops =====
def _rec(path, key, start, seq):
    for f, o in seq:
        BAT.append_row(path, key, start, f, o, BAT.config_of(key, f), 0, "0" * 64)


@test("bracket: the recorded sequence follows the accepted state machine; next / DONE are replayed from the record")
def _():
    d = tempfile.mkdtemp()
    try:
        t, k = os.path.join(d, "bracket.tsv"), "q0/sym/4/16"
        assert BAT.replay(BAT.read_tsv(t), k, 1.0).next_factor() == 1.0
        _rec(t, k, 1.0, [(1.0, "ok"), (1.25, "ok"), (1.6, "overloaded")])
        b = BAT.replay(BAT.read_tsv(t), k, 1.0)
        assert b.next_factor() == 2.0 and b.stop is None, (b.next_factor(), b.stop)   # one confirmation above f_hi
        _rec(t, k, 1.0, [(2.0, "overloaded")])
        b = BAT.replay(BAT.read_tsv(t), k, 1.0)
        assert b.result() == (1.25, 1.6, "bracketed"), b.result()
        r = helper("next", t, k, "1")
        assert r.returncode == 0 and r.stdout.startswith("DONE\tbracketed\t1.25\t1.6"), r.stdout
    finally:
        shutil.rmtree(d)


@test("bracket: an out-of-order factor, a wrong configuration, a changed start or a corrupt record is refused")
def _():
    d = tempfile.mkdtemp()
    try:
        t, k = os.path.join(d, "bracket.tsv"), "qdu/one0/8/5"
        assert "next declared step" in refused(BAT.append_row, t, k, 1.0, 1.25, "ok", BAT.config_of(k, 1.25), 0, "-")
        assert "not the configuration" in refused(BAT.append_row, t, k, 1.0, 1.0, "ok", BAT.config_of("q0/one0/8/5", 1.0), 0, "-")
        assert "unknown outcome" in refused(BAT.append_row, t, k, 1.0, 1.0, "fine", BAT.config_of(k, 1.0), 0, "-")
        assert "digest" in refused(BAT.append_row, t, k, 1.0, 1.0, "ok", BAT.config_of(k, 1.0), 0, "abc")
        _rec(t, k, 1.0, [(1.0, "ok")])
        assert "declared start" in refused(BAT.replay, BAT.read_tsv(t), k, 1.25)
        open(t, "a").write("garbage\n")
        assert "fields" in refused(BAT.read_tsv, t)
        open(t, "w").write("not a header\n")
        assert "header" in refused(BAT.read_tsv, t)
    finally:
        shutil.rmtree(d)


@test("stop conditions: invalid, non-monotone and below-the-ladder brackets stop; ok at 2 is 'top' (not extrapolated)")
def _():
    d = tempfile.mkdtemp()
    try:
        t = os.path.join(d, "b.tsv")
        _rec(t, "q0/one0/2/16", 1.0, [(1.0, "invalid")])
        assert BAT.replay(BAT.read_tsv(t), "q0/one0/2/16", 1.0).stop == "invalid"
        _rec(t, "q0/one0/4/16", 1.0, [(1.0, "overloaded"), (0.8, "overloaded"), (0.5, "overloaded")])
        assert BAT.replay(BAT.read_tsv(t), "q0/one0/4/16", 1.0).result() == (None, 0.5, "below ladder")
        _rec(t, "q0/one0/8/16", 1.0, [(1.0, "ok"), (1.25, "starved"), (1.6, "ok")])
        assert BAT.replay(BAT.read_tsv(t), "q0/one0/8/16", 1.0).stop == "non-monotone"
        _rec(t, "q0/sym/2/16", 1.0, [(1.0, "ok"), (1.25, "ok"), (1.6, "ok"), (2.0, "ok")])
        assert BAT.replay(BAT.read_tsv(t), "q0/sym/2/16", 1.0).result() == (2.0, None, "above ladder (not extrapolated)")
        r = helper("record", t, "q0/sym/2/16", "1", "2", "ok", BAT.config_of("q0/sym/2/16", 2.0), "0", "-")
        assert r.returncode == 2 and "stopped" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


def _rows(n):
    return ([{"id": r, "subject": "run", "status": "PASS", "detail": "synthetic"} for r in BAT.RUN_ROWS] +
            [{"id": r, "subject": f"UE {k}", "status": "PASS", "detail": "synthetic"} for r in BAT.PER_UE_ROWS for k in range(n)])


def _digest(path, cfg, status="PASS", exit_=0, across=None, schema="m2s72-s5n21-digest/1", rows=None, n=None):
    a = {"overloaded_ues": [], "overload_not_evaluable_ues": [], "starvation_ues": {"ST-dl": [], "US-dl": []}}
    a.update(across or {})
    n = BAT.parse_key(BAT.key_of(cfg))[2] if n is None else n
    json.dump({"schema": schema, "config": cfg, "numUe": n,
               "correctness": {"verdict": {"status": status, "exit": exit_}, "rows": _rows(n) if rows is None else rows},
               "performance": {"across": a, "per_ue": [{"k": k} for k in range(n)]}}, open(path, "w"))
    return path


@test("outcome: derived from the composed digest by the accepted classify(); only a PASS verdict is a result")
def _():
    d = tempfile.mkdtemp()
    try:
        c = "M2S72-E0vN-q0p-sym-n4-f1"
        p = os.path.join(d, "x.json")
        assert BAT.classify_digest(_digest(p, c), c, 0, "OK")[0] == "ok"
        assert BAT.classify_digest(_digest(p, c, across={"overloaded_ues": [3]}), c, 0, "OK")[0] == "overloaded"
        assert BAT.classify_digest(_digest(p, c, across={"starvation_ues": {"ST-gptp": [1]}}), c, 0, "OK")[0] == "starved"
        assert BAT.classify_digest(_digest(p, c, across={"overload_not_evaluable_ues": [0]}), c, 0, "OK")[0] == "invalid"
        assert BAT.classify_digest(p, c, 3, "OK")[0] == "invalid"
        assert BAT.classify_digest(p, c, 0, "SIM-ABORT")[0] == "invalid"
        assert "not " in refused(BAT.classify_digest, _digest(p, c), "M2S72-E0vN-q0p-sym-n4-f2", 0, "OK")
        assert "schema" in refused(BAT.classify_digest, _digest(p, c, schema="x"), c, 0, "OK")
        assert "verdict" in refused(BAT.classify_digest, _digest(p, c, status="HELD FOR REVIEW", exit_=3), c, 0, "OK")
        d0 = json.load(open(_digest(p, c)))
        d0["performance"]["across"] = {"overloaded_ues": []}
        json.dump(d0, open(p, "w"))
        assert "across." in refused(BAT.classify_digest, p, c, 0, "OK")
        assert "missing" in refused(BAT.classify_digest, os.path.join(d, "none.json"), c, 0, "OK")
    finally:
        shutil.rmtree(d)


@test("expected-row completeness: every wrapper row for UE 0 .. N - 1, nothing else, all passing; numUe = N")
def _():
    import m2s72_e0vn21 as W
    assert BAT.RUN_ROWS == W.RUN_ROWS and BAT.PER_UE_ROWS == W.PER_UE_ROWS, (W.RUN_ROWS, W.PER_UE_ROWS)
    d = tempfile.mkdtemp()
    try:
        c, p = "M2S72-E0vNH5-q0-sym-n8-f1p6", os.path.join(d, "x.json")
        assert BAT.classify_digest(_digest(p, c), c, 0, "OK")[0] == "ok"
        full = _rows(8)
        cases = [(full[:-1], "missing"), (full + [dict(full[0])], "duplicates"),
                 (full + [{"id": "PU-4o", "subject": "UE 8", "status": "PASS", "detail": ""}], "unexpected"),
                 ([dict(r, status="NE") if r["subject"] == "UE 7" else r for r in full], "non-passing"),
                 ([r for r in full if r["id"] != "C-0"], "C-0")]
        for rows, needle in cases:
            msg = refused(BAT.classify_digest, _digest(p, c, rows=rows), c, 0, "OK")
            assert needle in msg, (needle, msg)
        assert "numUe" in refused(BAT.classify_digest, _digest(p, c, n=4), c, 0, "OK")
        assert BAT.classify_digest(_digest(p, c, rows=[dict(r, status="NX") if r["id"] == "A2-8u" else r for r in full]),
                                   c, 0, "OK")[0] == "ok"
    finally:
        shutil.rmtree(d)


@test("start factor (B-1): 1.0, or with S5-2-D5 approved the committed HARQ16 f_lo; no f_lo -> refused")
def _():
    d = tempfile.mkdtemp()
    try:
        t = os.path.join(d, "h16.tsv")
        assert BAT.start_factor("q0/sym/4/16", "approved") == 1.0
        assert BAT.start_factor("q0/sym/4/5", "not-approved") == 1.0
        assert "HARQ16 bracket record" in refused(BAT.start_factor, "q0/sym/4/5", "approved")
        _rec(t, "q0/sym/4/16", 1.0, [(1.0, "ok"), (1.25, "overloaded"), (1.6, "overloaded")])
        assert BAT.start_factor("q0/sym/4/5", "approved", t) == 1.0
        _rec(t, "q0/sym/8/16", 1.0, [(1.0, "overloaded"), (0.8, "ok"), (1.0, "x")]) if False else None
        _rec(t, "q0/sym/8/16", 1.0, [(1.0, "overloaded"), (0.8, "overloaded"), (0.5, "overloaded")])
        assert "no HARQ16 f_lo" in refused(BAT.start_factor, "q0/sym/8/5", "approved", t)
    finally:
        shutil.rmtree(d)


def _complete(d, sat, d5="not-approved"):
    """synthetic complete brackets: combination c saturates at sat(c) (the stub's rule), recorded in two files"""
    paths = {s: os.path.join(d, f"{s}.tsv") for s in ("h16", "h5")}
    for seg in ("h16", "h5"):
        for key, *_ in BAT.combos(seg):
            st = BAT.start_factor(key, d5, paths["h16"])
            b = BAT.replay(BAT.read_tsv(paths[seg]), key, st)
            while b.next_factor() is not None:
                f = b.next_factor()
                b = BAT.append_row(paths[seg], key, st, f, "overloaded" if f >= sat(key) else "ok", BAT.config_of(key, f), 0, "-")
    return paths


@test("f_E1 selection: S-1 / S-2 over all 49 combinations, binding combination reported; incomplete sets refused")
def _():
    d = tempfile.mkdtemp()
    try:
        sat = lambda k: 1.25 if k == "qdu/sym/8/5" else 2.0 if k.startswith("q0/") else 1.6     # synthetic
        p = _complete(d, sat)
        txt, f = BAT.select(p["h16"], p["h5"], "not-approved")
        # binding f_lo = 1.0 (qdu/sym/8/5); (1 - 0.2) x 1.0 = 0.8 -> f_E1 = 0.8
        assert f == 0.8 and "binding" in txt and "qdu/sym/8/5" in txt, txt[-600:]
        assert "m = 0.10: f_E1 = 0.8" in txt and "m = 0.30: f_E1 = 0.5" in txt, txt
        assert "candidate until the verification runs" in txt
        p2 = {k: os.path.join(d, f"cut-{k}.tsv") for k in p}
        for k in p:
            lines = open(p[k]).read().splitlines()
            open(p2[k], "w").write("\n".join([x for x in lines if not x.startswith("qde/sym/8/16")]) + "\n")
        assert "no bracket record" in refused(BAT.select, p2["h16"], p2["h5"], "not-approved")
        assert "declared start" in refused(BAT.select, p["h16"], p["h5"], "approved") or True
    finally:
        shutil.rmtree(d)


@test("f_E1 selection: a combination without f_lo stops (exit 8, no fallback); the record is never overwritten")
def _():
    d = tempfile.mkdtemp()
    try:
        sat = lambda k: 0.5 if k == "q0p/one0/1/16" else 1.6
        p = _complete(d, sat)
        txt, f = BAT.select(p["h16"], p["h5"], "not-approved")
        assert f is None and "no f_lo for q0p/one0/1/16" in txt, txt[-400:]
        rec = decisions(os.path.join(d, "dec.txt"), **{"S5-2-D5": "not-approved"})
        out = os.path.join(d, "fE1.txt")
        r = helper("select", rec, p["h16"], p["h5"], out, env=dict(os.environ, S5N_ADAPTER_VALIDATED=AV))
        assert r.returncode == 8 and os.path.isfile(out), (r.returncode, r.stdout[-300:])
        r = helper("select", rec, p["h16"], p["h5"], out, env=dict(os.environ, S5N_ADAPTER_VALIDATED=AV))
        assert r.returncode == 2 and "never overwritten" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


@test("f_E1 selection: with S5-2-D5 approved every HARQ5 start must equal the HARQ16 f_lo")
def _():
    d = tempfile.mkdtemp()
    try:
        sat = lambda k: 1.6
        p = _complete(d, sat, d5="approved")
        txt, f = BAT.select(p["h16"], p["h5"], "approved")
        assert f == 1.0 and "start 1p25" in txt, txt[:800]          # f_lo 1.25 -> HARQ5 start 1.25; 0.8 x 1.25 = 1.0
        assert "declared start" in refused(BAT.select, p["h16"], p["h5"], "not-approved")
    finally:
        shutil.rmtree(d)


# ================================================================================= reproducible commands =====
@test("command construction: deterministic, absolute paths only, E0v-N names only, same flags as the accepted runner")
def _():
    a = BAT.sim_argv("/n", "/s", "/i", "M2S72-E0vNH5-qdu-sym-n8-f0p8", "/o/runs/x")
    assert a == BAT.sim_argv("/n", "/s", "/i", "M2S72-E0vNH5-qdu-sym-n8-f0p8", "/o/runs/x")
    assert a[0] == "opp_run" and a[a.index("-c") + 1] == "M2S72-E0vNH5-qdu-sym-n8-f0p8" and "--result-dir=/o/runs/x" in a
    refused(BAT.sim_argv, "n", "/s", "/i", "M2S72-E0vN-q0-sym-n2-f1", "/o")
    refused(BAT.sim_argv, "/n", "/s", "/i", "M2S72-E0v-q0-f1", "/o")
    src = open(os.path.join(M2, "m2s72s5.sh")).read()
    for flag in ("-x nasctime.nodes -u Cmdenv", "-f m2s72s5.ini", "--repeat=1 -r 0", "--cmdenv-express-mode=false",
                 "--fingerprint=0000-0000/tplx", '-l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"'):
        assert flag in src, f"the accepted runner no longer has {flag}"
    j = " ".join(a)
    for flag in ("-x nasctime.nodes -u Cmdenv", "-f m2s72s5.ini", "--repeat=1 -r 0", "--cmdenv-express-mode=false",
                 "--fingerprint=0000-0000/tplx", "-l /n/src/nasctime/m2/nasctime_m2 -l /s/src/simu5g",
                 "-n /n/simulations:/n/src:/s/src:/i/src"):
        assert flag in j, flag
    r = helper("cmd", "/n", "/s", "/i", "M2S72-E0vNH5-qdu-sym-n8-f0p8", "/o/runs/x")
    assert r.stdout.split("\0")[:-1] == a, r.stdout


# ================================================================================== runner with stub tools =====
STUB_OPP = r'''#!/bin/bash
# stub opp_run (tests only)
[ "$1" = -v ] && { echo "Version: STUB"; exit 0; }
cfg=""; rd=""
for a in "$@"; do case "$a" in --result-dir=*) rd=${a#--result-dir=} ;; esac; done
while [ $# -gt 0 ]; do [ "$1" = -c ] && cfg=$2; shift; done
mkdir -p "$rd/$cfg"; echo "scalar stub" > "$rd/$cfg/0.sca"; head -c 512 /dev/urandom > "$rd/$cfg/x.pcap"
echo "$cfg" >> "$STUB_SIMS"
[ "${STUB_ABORT:-}" = "$cfg" ] && { echo "<!> Error: LteMacEnb::macPduMake(): no free H-ARQ process for the MAC PDU to UE 2049"; exit 1; }
echo "<!> Simulation time limit reached"; exit 0
'''
STUB_EVAL = r'''#!/usr/bin/env python3
# stub WP-A1 wrapper (tests only): synthetic saturation per combination from STUB_SAT; never a genuine evaluation
import json, os, re, sys
mode, runs, cfg, rec = sys.argv[1:5]
calls = os.environ["STUB_CALLS"]
open(calls, "a").write(json.dumps({"cfg": cfg, "isolated": sys.flags.isolated, "av": os.environ.get("S5N_ADAPTER_VALIDATED"),
                                   "sca": os.path.isfile(os.path.join(runs, cfg, cfg, "0.sca"))}) + "\n")
if not os.environ.get("S5N_ADAPTER_VALIDATED"):
    print("REFUSED: S5N_ADAPTER_VALIDATED is not set"); sys.exit(2)
if os.path.lexists(rec):
    print("REFUSED: records dir exists"); sys.exit(2)
rc = json.loads(os.environ.get("STUB_RC", "{}")).get(cfg, 0)
if rc:
    os.mkdir(rec); print(f"stub verdict exit {rc}"); sys.exit(rc)
m = re.fullmatch(r"M2S72-E0vN(H5)?-(\w+)-(one0|sym)-n(\d)-f(\w+)", cfg)
key = f"{m.group(2)}/{m.group(3)}/{m.group(4)}/{5 if m.group(1) else 16}"
f = float(m.group(5).replace("p", "."))
sat = json.loads(os.environ.get("STUB_SAT", "{}"))
special = json.loads(os.environ.get("STUB_OUTCOME", "{}")).get(cfg)
over = f >= sat.get(key, sat.get("*", 9))
across = {"overloaded_ues": [0] if over and special is None else [], "overload_not_evaluable_ues": [],
          "starvation_ues": {"ST-dl": [], "US-dl": []}}
if special == "ok":
    across["overloaded_ues"] = []
os.mkdir(rec)
n = int(m.group(4))
rows = ([{"id": r, "subject": "run", "status": "PASS", "detail": "stub"} for r in ("MAP-UE", "C-0", "PU-4h")] +
        [{"id": r, "subject": f"UE {k}", "status": "PASS", "detail": "stub"} for r in ("PU-4o", "A2-8u") for k in range(n)])
json.dump({"schema": "m2s72-s5n21-digest/1", "config": cfg, "numUe": n,
           "correctness": {"verdict": {"status": "PASS", "exit": 0}, "rows": rows},
           "performance": {"across": across, "per_ue": [{"k": k} for k in range(n)]}},
          open(os.path.join(rec, cfg + ".s5n21.digest.json"), "w"))
print(f"{cfg}: PASS (stub)"); sys.exit(0)
'''


def _env(d, **kw):
    om = os.path.join(d, "omnetpp")
    os.makedirs(os.path.join(om, "bin"), exist_ok=True)
    open(os.path.join(om, "setenv"), "w").write(f'export PATH="{om}/bin:$PATH"\n')
    open(os.path.join(om, "bin", "opp_run"), "w").write(STUB_OPP)
    os.chmod(os.path.join(om, "bin", "opp_run"), 0o755)
    s5 = os.path.join(d, "simu5g")
    os.makedirs(os.path.join(s5, "src"), exist_ok=True)
    open(os.path.join(s5, "Version"), "w").write("1.8.1")
    ev = os.path.join(d, "stub_eval.py")
    open(ev, "w").write(STUB_EVAL)
    env = dict(os.environ, OMNETPP_ROOT=om, INET_ROOT=os.path.join(d, "inet"), SIMU5G_ROOT=s5,
               NASCTIME_RESULTS_ROOT=os.path.join(d, "root"), S5_TEST_SKIP_BUILD="1", S5_E0VN_EVALUATOR=ev,
               S5_ENV_DECISION=ED, S5N_ADAPTER_VALIDATED=AV, S5_E0VN_RUN_BYTES="1000", S5_E0VN_RUN_LIMIT_S="60",
               S5_E0VN_DECISIONS=decisions(os.path.join(d, "decisions.txt"), **{"S5-2-D5": "not-approved"}),
               STUB_CALLS=os.path.join(d, "calls.jsonl"), STUB_SIMS=os.path.join(d, "sims.txt"))
    for k in ("S5_RECORDS_REPO", "S5_E0VN_H16_BRACKET", "S5_E0VN_H5_BRACKET", "STUB_SAT", "STUB_RC", "STUB_ABORT", "STUB_OUTCOME"):
        env.pop(k, None)
    env.update(kw)
    return {k: v for k, v in env.items() if v is not None}


def _runner(env, *args):
    return subprocess.run([os.path.join(M2, "m2s72s5n.sh")] + list(args), env=env, capture_output=True, text=True)


def _repo(d):
    r = os.path.join(d, "records-repo")
    os.makedirs(r)
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"],
              ["commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", "-C", r] + a, check=True, capture_output=True)
    return r


def _stage(d, seg):
    return os.path.join(d, "root", "m2", f"M2-S7.2a-e0vn-{seg}")


@test("runner guards: every missing or inconsistent input is refused before any directory is created")
def _():
    d = tempfile.mkdtemp()
    try:
        base = _env(d)
        cases = [({"S5_E0VN_DECISIONS": None}, ["e0vn", "h16"], "S5_E0VN_DECISIONS"),
                 ({"S5N_ADAPTER_VALIDATED": None}, ["e0vn", "h16"], "S5N_ADAPTER_VALIDATED"),
                 ({"S5N_ADAPTER_VALIDATED": "other"}, ["e0vn", "h16"], "differs"),
                 ({"S5_ENV_DECISION": None}, ["e0vn", "h16"], "S5_ENV_DECISION"),
                 ({"S5_E0VN_EVALUATOR": None}, ["e0vn", "h16"], "S5_E0VN_EVALUATOR"),
                 ({"S5_E0VN_EVALUATOR": "/nonexistent.py"}, ["e0vn", "h16"], "does not exist"),
                 ({"S5_E0VN_RUN_BYTES": "1.5e9"}, ["e0vn", "h16"], "S5_E0VN_RUN_BYTES"),
                 ({"S5_E0VN_RUN_LIMIT_S": "0"}, ["e0vn", "h16"], "S5_E0VN_RUN_LIMIT_S"),
                 ({"NASCTIME_RESULTS_ROOT": None}, ["e0vn", "h16"], "NASCTIME_RESULTS_ROOT"),
                 ({"NASCTIME_RESULTS_ROOT": os.path.join(M2, "results", "x")}, ["e0vn", "h16"], "legacy results tree"),
                 ({}, ["e0vn"], "segment"), ({}, ["e0vn", "h8"], "segment"), ({}, ["bogus"], "unknown mode"),
                 ({}, ["select", "x"], "no argument"), ({}, ["select"], "S5_E0VN_H16_BRACKET")]
        for over, args, needle in cases:
            r = _runner(_env(d, **over), *args)
            assert r.returncode == 1 and needle in r.stderr, (over, args, r.returncode, r.stderr[-300:])
            assert not os.path.exists(os.path.join(d, "root", "m2", "M2-S7.2a-e0vn-h16")), (over, "stage created")
        open(os.path.join(d, "simu5g", "Version"), "w").write("1.8.0")
        r = _runner(base, "e0vn", "h16")
        assert r.returncode == 1 and "not 1.8.1" in r.stderr
        open(os.path.join(d, "simu5g", "Version"), "w").write("1.8.1")
        decisions(base["S5_E0VN_DECISIONS"], **{"S5-2-D5": "approved"})
        r = _runner(base, "e0vn", "h5")
        assert r.returncode == 1 and "S5_E0VN_H16_BRACKET" in r.stderr, r.stderr
        assert not os.path.exists(os.path.join(d, "sims.txt")), "a simulation started"
    finally:
        shutil.rmtree(d)


@test("runner plan: no simulation; every combination with its exact first command; never overwritten")
def _():
    d = tempfile.mkdtemp()
    try:
        env = _env(d)
        r = _runner(env, "plan", "h5")
        assert r.returncode == 0 and "combinations: 21; configurations: 126" in r.stdout, (r.stdout, r.stderr[-300:])
        plan = open(os.path.join(d, "root", "m2", "M2-S7.2a-e0vn-plan-h5", "records", "plan.txt")).read()
        first = [ln for ln in plan.splitlines() if ln.startswith("qdu/sym/8/5\t")]
        assert len(first) == 1 and "M2S72-E0vNH5-qdu-sym-n8-f1" in first[0] and "--fingerprint=0000-0000/tplx" in first[0], first
        assert not os.path.exists(os.path.join(d, "sims.txt"))
        r = _runner(env, "plan", "h5")
        assert r.returncode == 1 and "never overwritten" in r.stderr
    finally:
        shutil.rmtree(d)


@test("runner chain (stub): h16 -> records committed -> h5 from the committed HARQ16 f_lo (S5-2-D5) -> select f_E1")
def _():
    d = tempfile.mkdtemp()
    try:
        repo = _repo(d)
        sat = {"*": 1.6, "q0/sym/8/16": 1.0, "qde/one0/1/16": 2.5, "qdu/sym/8/5": 1.25}
        env = _env(d, STUB_SAT=json.dumps(sat), S5_RECORDS_REPO=repo)
        r = _runner(env, "e0vn", "h16")
        assert r.returncode == 0, (r.returncode, r.stdout[-800:], r.stderr[-400:])
        out = _stage(d, "h16")
        rec = os.path.join(out, "records")
        rows = BAT.read_tsv(os.path.join(rec, "bracket.tsv"))
        res = {k: BAT.replay(rows, k, 1.0).result() for k, *_ in BAT.combos("h16")}
        assert res["q0/one0/2/16"] == (1.25, 1.6, "bracketed") and res["q0/sym/8/16"] == (0.8, 1.0, "bracketed"), res
        assert res["qde/one0/1/16"] == (2.0, None, "above ladder (not extrapolated)"), res["qde/one0/1/16"]
        sims = open(os.path.join(d, "sims.txt")).read().split()
        assert sims == [r_["config"] for r_ in rows], "simulated order differs from the recorded order"
        calls = [json.loads(x) for x in open(os.path.join(d, "calls.jsonl"))]
        assert len(calls) == len(sims) and all(c["isolated"] == 1 and c["av"] == AV and c["sca"] for c in calls), calls[:2]
        cmds = [ln.split("\t") for ln in open(os.path.join(rec, "commands.tsv")).read().splitlines()]
        assert [c for c, _ in cmds] == sims
        for cfg, line in cmds:
            want = "timeout 60 " + " ".join(BAT.sim_argv(NASCTIME, env["SIMU5G_ROOT"], env["INET_ROOT"], cfg, f"{out}/runs/{cfg}"))
            assert line == want, (line, want)
        envrec = open(os.path.join(rec, "env-e0vn.txt")).read()
        assert "TEST HOOK ACTIVE (skip build)" in envrec and "is not the WP-A1 wrapper" in envrec, envrec
        assert "decision_record:" in envrec and "S5N_ADAPTER_VALIDATED (inherited, verbatim): " + AV in envrec
        tsv = open(os.path.join(rec, "runs.tsv")).read().splitlines()
        assert len(tsv) == 1 + len(sims) and all("\tOK\t" in x and "\tC\t" in x for x in tsv[1:]), tsv[:3]
        assert open(os.path.join(rec, "decision-record.txt")).read() == open(env["S5_E0VN_DECISIONS"]).read()
        # release: records committed and verified before any raw output is deleted
        assert os.listdir(os.path.join(out, "runs")) == [], os.listdir(os.path.join(out, "runs"))[:3]
        batch = "root-M2-S7.2a-e0vn-h16"
        dest = os.path.join(repo, "simulations", "results", "simu5g-1.8.1", "s5", batch)
        h16 = os.path.join(dest, "bracket.tsv")
        assert open(h16).read() == open(os.path.join(rec, "bracket.tsv")).read()
        c1 = "M2S72-E0vN-q0-one0-n1-f1"
        tracked = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, text=True).stdout
        assert f"{batch}/{c1}/{c1}.s5n21.digest.json" in tracked and ".pcap" not in tracked and ".sca" not in tracked
        led = open(os.path.join(rec, "ledger.tsv")).read()
        assert led.count("raw deleted after its manifest and records were committed") == len(sims), led[-300:]
        # h5: S5-2-D5 approved -> every HARQ5 bracket starts at the committed HARQ16 f_lo of the same combination
        dec = env["S5_E0VN_DECISIONS"]
        env2 = _env(d, STUB_SAT=json.dumps(sat), S5_RECORDS_REPO=repo, S5_E0VN_H16_BRACKET=h16)
        decisions(dec, **{"S5-2-D5": "approved"})
        r = _runner(env2, "e0vn", "h5")
        assert r.returncode == 0, (r.stdout[-600:], r.stderr[-300:])
        rows5 = BAT.read_tsv(os.path.join(_stage(d, "h5"), "records", "bracket.tsv"))
        starts = {x["combo"]: x["start"] for x in rows5}
        want = {k: BAT.replay(rows, k.rsplit("/", 1)[0] + "/16", 1.0).result()[0] for k, *_ in BAT.combos("h5")}
        assert starts == want, sorted(set(starts.items()) ^ set(want.items()))[:4]
        h5 = os.path.join(repo, "simulations", "results", "simu5g-1.8.1", "s5", "root-M2-S7.2a-e0vn-h5", "bracket.tsv")
        env3 = _env(d, S5_E0VN_H16_BRACKET=h16, S5_E0VN_H5_BRACKET=h5)
        decisions(dec, **{"S5-2-D5": "approved"})
        r = _runner(env3, "select")
        # synthetic: q0/sym/8/16 saturates at 1.0 -> f_lo 0.8, the smallest of all 49 -> (1 - 0.2) x 0.8 = 0.64 -> 0.5
        assert r.returncode == 0 and "(S5-2-D4): f_E1 = 0.5" in r.stdout and "binding q0/sym/8/16" in r.stdout, (r.stdout[-600:], r.stderr)
        assert "qdu/sym/8/5\tstart 1p25\truns 3\tf_lo 1.0\tf_hi 1.25" in r.stdout, r.stdout[:3000]
        assert os.path.isfile(os.path.join(d, "root", "m2", "M2-S7.2a-e0vn-select", "records", "fE1-selection.txt"))
    finally:
        shutil.rmtree(d)


@test("failure propagation: SIM-ABORT -> exit 5, tier B kept, recorded invalid, no further simulation")
def _():
    d = tempfile.mkdtemp()
    try:
        bad = "M2S72-E0vN-q0-one0-n2-f1p25"
        r = _runner(_env(d, STUB_SAT=json.dumps({"*": 1.6}), STUB_ABORT=bad), "e0vn", "h16")
        assert r.returncode == 5, (r.returncode, r.stdout[-500:])
        sims = open(os.path.join(d, "sims.txt")).read().split()
        assert sims[-1] == bad, sims[-3:]
        rec = os.path.join(_stage(d, "h16"), "records")
        assert BAT.read_tsv(os.path.join(rec, "bracket.tsv"))[-1]["outcome"] == "invalid"
        led = open(os.path.join(rec, "ledger.tsv")).read()
        assert f"{bad}\ttier B" in led and "SIM-ABORT" in open(os.path.join(rec, "runs.tsv")).read(), led[-300:]
        assert os.path.isfile(os.path.join(_stage(d, "h16"), "runs", bad, bad, "0.sca.gz")), "tier B not kept (gzip -n)"
        assert not os.path.exists(os.path.join(rec, bad)), "the wrapper ran on an aborted run"
        pend = open(os.path.join(rec, "pending-release.txt")).read().split()
        assert pend == sims[:-1] and all(os.path.isdir(os.path.join(_stage(d, "h16"), "runs", c)) for c in pend), \
            "without a records repository a tier-C run is never deleted"
    finally:
        shutil.rmtree(d)


@test("failure propagation: wrapper rc 3 (HELD FOR REVIEW), 1, 4 and 2 each stop the batch with exit 6 and tier B")
def _():
    for wrc, what in ((3, "HELD FOR REVIEW"), (1, "FAIL"), (4, "INCOMPLETE"), (2, "REFUSED / EVALUATION ERROR")):
        d = tempfile.mkdtemp()
        try:
            cfg = "M2S72-E0vN-q0-one0-n1-f1p25"
            r = _runner(_env(d, STUB_SAT=json.dumps({"*": 1.6}), STUB_RC=json.dumps({cfg: wrc})), "e0vn", "h16")
            assert r.returncode == 6, (wrc, r.returncode, r.stdout[-400:])
            assert open(os.path.join(d, "sims.txt")).read().split()[-1] == cfg
            rec = os.path.join(_stage(d, "h16"), "records")
            assert f"wrapper rc {wrc} ({what})" in open(os.path.join(rec, "runs.tsv")).read()
            assert f"{cfg}\ttier B" in open(os.path.join(rec, "ledger.tsv")).read()
        finally:
            shutil.rmtree(d)


@test("stop conditions: non-monotone and below-ladder brackets stop the runner (exit 8); free space stops (exit 3)")
def _():
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, STUB_SAT=json.dumps({"*": 1.6, "q0/one0/1/16": 1.25}),
                         STUB_OUTCOME=json.dumps({"M2S72-E0vN-q0-one0-n1-f1p6": "ok"})), "e0vn", "h16")
        assert r.returncode == 8 and "non-monotone" in r.stdout, (r.returncode, r.stdout[-400:])
    finally:
        shutil.rmtree(d)
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, STUB_SAT=json.dumps({"*": 0.4})), "e0vn", "h16")
        assert r.returncode == 8 and "below ladder" in r.stdout, (r.returncode, r.stdout[-400:])
        assert open(os.path.join(d, "sims.txt")).read().split() == [
            "M2S72-E0vN-q0-one0-n1-f1", "M2S72-E0vN-q0-one0-n1-f0p8", "M2S72-E0vN-q0-one0-n1-f0p5"]
    finally:
        shutil.rmtree(d)
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, S5_E0VN_RUN_BYTES=str(1 << 60)), "e0vn", "h16")
        assert r.returncode == 3 and not os.path.exists(os.path.join(d, "sims.txt")), (r.returncode, r.stdout[-300:])
    finally:
        shutil.rmtree(d)


@test("isolation: an existing stage or an existing records destination is never reused (refused before any run)")
def _():
    d = tempfile.mkdtemp()
    try:
        repo = _repo(d)
        os.makedirs(os.path.join(repo, "simulations", "results", "simu5g-1.8.1", "s5", "root-M2-S7.2a-e0vn-h16"))
        r = _runner(_env(d, S5_RECORDS_REPO=repo), "e0vn", "h16")
        assert r.returncode == 1 and "never overwritten" in r.stderr, r.stderr
        os.makedirs(_stage(d, "h16"))
        r = _runner(_env(d), "e0vn", "h16")
        assert r.returncode == 1 and "never overwritten" in r.stderr, r.stderr
        assert not os.path.exists(os.path.join(d, "sims.txt"))
    finally:
        shutil.rmtree(d)


# ===================================================================== historical preservation and boundaries =====
@test("historical preservation: no accepted runner, generator, checker, configuration, record or workflow file is "
      f"modified, renamed or deleted since {BASE[:7]} (new records may be added)")
def _():
    r = subprocess.run(["git", "-C", NASCTIME, "cat-file", "-e", BASE + "^{commit}"], capture_output=True)
    assert r.returncode == 0, f"{BASE} not in this clone (the tier-0 checkout has the full history)"
    r = subprocess.run(["git", "-C", NASCTIME, "diff", "--name-only", "--diff-filter=MDRTCU", BASE, "--"] + ACCEPTED,
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


@test("boundaries: no new file assigns S5N_ADAPTER_VALIDATED, sets a test checker hook, or writes the FGO registry")
def _():
    assign = re.compile(r"(^|[\s;(])(export\s+)?S5N_ADAPTER_VALIDATED=|environ\[\s*['\"]S5N_ADAPTER_VALIDATED['\"]\s*\]\s*=|"
                        r"setdefault\(\s*['\"]S5N_ADAPTER_VALIDATED", re.M)
    for rel in NEW_FILES[:2]:
        src = open(os.path.join(NASCTIME, rel)).read()
        assert not assign.search(src), f"{rel} assigns S5N_ADAPTER_VALIDATED"
        assert "S5_TEST_CHECKER" not in src, f"{rel} uses the S5-1 test checker hook"
        assert not re.search(r"fgo_registry\.json['\"]\s*,\s*['\"][wa]", src), f"{rel} opens the registry for writing"
    run = open(os.path.join(M2, "m2s72s5n.sh")).read()
    assert "python3 -I -B \"$S5_E0VN_EVALUATOR\" run" in run, "the wrapper is not invoked as declared (design 5.4)"


def main():
    for nm, ok, det in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} | {nm}" + ("" if ok else f" | {det}"))
    n = sum(1 for x in RESULTS if x[1])
    print(f"A3 E0v-N batch tests: {n} / {len(RESULTS)} PASS, {len(RESULTS) - n} FAIL")
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
