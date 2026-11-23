#!/usr/bin/env python3
"""Tests of the WP-A1 wrapper (design revision 2.1, 57a80ca, section 7). Increment I-1: T-name-guard, T-registry,
T-schema, T-imports-isolated. No simulation; no raw output of any run; synthetic inputs and repository files only.
The committed registry is only read; T-registry and main() check that its sha256 is unchanged.

    python3 -I -B test_m2s72_e0vn21.py [<test name prefix> ...]
    python3 -I -B test_m2s72_e0vn21.py --import-only      (used by T-imports-isolated)
"""
import copy
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a21 as A21  # noqa: E402  (accepted; read-only)
import m2s72_e0vn21 as W  # noqa: E402

TESTS = []
INI = os.path.join(HERE, "..", "m2s72s5.ini")
INI_A2V = os.path.join(HERE, "..", "m2s72a2v.ini")
CLI = os.path.join(HERE, "check_m2s72_s5n21.py")
LIB = os.path.join(HERE, "m2s72_e0vn21.py")
SELF = os.path.abspath(__file__)

ADMITTED = ["NACK resolved: bound handle", "NACK resolved by retransmission evidence (deferred)", "retransmissions",
            "mixed ACK / NACK groups", "end-of-run censoring: awaiting feedback",
            "per-UE occupancy confirmed by the independent reference", "independent UE-side reference (A2-7)",
            "retransmission node identity from the UE side (A2-4b)", "Simu5G per-UE statistics (A2-8)"]
INFERRED = ["single-candidate ACK attribution", "exchangeable ACK groups (2 candidates)", "NACK resolved: single candidate"]
NOT_EXERCISED = ["exchangeable groups of 3 or more", "multi-NACK groups (handle relations kept ambiguous)",
                 "discard after maxHarqRtx + 1 transmissions", "end-of-run censoring: inserted in the last TTI",
                 "end-of-run censoring: awaiting retransmission (structural)",
                 "end-of-run censoring: awaiting resolution (structural)"]


def test(f):
    TESTS.append((f.__name__.replace("test_", "T-").replace("_", "-"), f))
    return f


def check(cond, msg):
    if not cond:
        raise AssertionError(msg)


def ini_configs(path):
    return [m.group(1) for m in re.finditer(r"^\[Config ([^\]]+)\]\s*$", open(path).read(), re.M)]


def parse_name():
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        import check_m2s72_s5v as S5V  # accepted; its import reads sys.argv
    finally:
        sys.argv = argv
    return S5V.parse_name


# ----------------------------------------------------------------------------------------------- T-name-guard ---
@test
def test_name_guard():
    cfgs = ini_configs(INI)
    check(len(cfgs) == 459 and len(set(cfgs)) == 459, f"m2s72s5.ini: {len(cfgs)} configurations ({len(set(cfgs))} distinct)")
    pn = parse_name()

    def kind(c):
        try:
            return pn(c)[0]
        except ValueError:
            return None
    acc = [c for c in cfgs if W.run_name_ok(c)]
    e0vn = [c for c in cfgs if kind(c) == "E0vN"]
    check(len(acc) == 294, f"run guard accepts {len(acc)} configurations, expected 294")
    check(acc == e0vn, f"guard and parse_name differ: {sorted(set(acc) ^ set(e0vn))[:5]}")
    check(not [c for c in cfgs if W.run_name_ok(c) and "E0vN-" not in c and "E0vNH5-" not in c], "a non-E0v-N name accepted")
    parts = Counter(c.split("-")[1] for c in acc)
    check(parts == Counter({"E0vN": 168, "E0vNH5": 126}), f"variants {parts}")
    check(Counter(c.split("-")[4] for c in acc) == Counter({"n1": 42, "n2": 84, "n4": 84, "n8": 84}), "numUe split")
    check(Counter(c.split("-")[2] for c in acc) == Counter({"q0": 84, "q0p": 84, "qdu": 84, "qde": 42}), "option split")
    check(Counter(c.split("-")[3] for c in acc) == Counter({"one0": 168, "sym": 126}), "placement split")
    check(Counter(c.split("-")[5] for c in acc) == Counter({f: 49 for f in ("f0p5", "f0p8", "f1", "f1p25", "f1p6", "f2")}),
          "factor split")
    nl = [c for c in cfgs if c.startswith("M2S72-E0vNL-")]
    check(nl == [f"M2S72-E0vNL-q0-f{f}" for f in (1, 2, 4, 8)], f"E0vNL names {nl}")
    for c in nl:
        check(not W.run_name_ok(c) and not W.hrq_name_ok(c) and kind(c) == "E0vNL", f"{c}: N = 1 twin must be refused")
    # hrq: the guard plus exactly the V-N1 and V-V1 names; both exist as configurations
    a2v1 = "M2S72-E0vN-q0-one0-n2-f1_A2V1"
    check(a2v1 in ini_configs(INI_A2V) and "M2S72-E0v-q0-f1" in cfgs, "hrq-only names must be real configurations")
    check(kind(a2v1) == "E0vN", "parse_name accepts the A2-V1 suffix (the hazard L-7 the guard closes)")
    check(not W.run_name_ok(a2v1) and W.hrq_name_ok(a2v1), "A2-V1 name: run refused, hrq accepted")
    check(not W.run_name_ok("M2S72-E0v-q0-f1") and W.hrq_name_ok("M2S72-E0v-q0-f1"), "V-N1 name: run refused, hrq accepted")
    hrq_acc = [c for c in cfgs + ini_configs(INI_A2V) if W.hrq_name_ok(c)]
    check(len(hrq_acc) == 296, f"hrq accepts {len(hrq_acc)} repository configurations, expected 294 + 2")
    for c in cfgs:
        if c not in acc and c != "M2S72-E0v-q0-f1":
            check(not W.hrq_name_ok(c), f"{c}: hrq must refuse")
    bad = ["", " ", None, 1, "M2S72-E0vN-q0-one0-n3-f1", "M2S72-E0vN-q0-one0-n2-f4", "M2S72-E0vN-q0-one0-n2-f1 ",
           "M2S72-E0vN-q0-one0-n2-f1\n", " M2S72-E0vN-q0-one0-n2-f1", "m2s72-e0vn-q0-one0-n2-f1", "M2S72-E0vN-q1-one0-n2-f1",
           "M2S72-E0vN-q0-one1-n2-f1", "M2S72-E0vN-q0-one0-n2-f1_A2V1", "M2S72-E0vN-q0-one0-n2-f1-x", "XM2S72-E0vN-q0-one0-n2-f1",
           "M2S72-E0vNH16-q0-one0-n2-f1", "M2S72-E0vN-q0-one0-n02-f1", "M2S72-E0vN-q0-one0-n2-f01", "M2S72-E0v-q0-f2"]
    for c in bad:
        check(not W.run_name_ok(c), f"run guard accepts {c!r}")
        try:
            W.guard(c, "run")
            raise AssertionError(f"guard(run) did not refuse {c!r}")
        except W.Refused:
            pass
    for c in bad:
        if c not in ("M2S72-E0vN-q0-one0-n2-f1_A2V1",):
            check(not W.hrq_name_ok(c), f"hrq guard accepts {c!r}")
    check(W.guard("M2S72-E0vN-q0-one0-n2-f1", "run") == "M2S72-E0vN-q0-one0-n2-f1", "guard returns the name")
    for mode in ("", "RUN", "hrq-fixture", None):
        try:
            W.guard("M2S72-E0vN-q0-one0-n2-f1", mode)
            raise AssertionError(f"guard accepted mode {mode!r}")
        except W.Refused:
            pass


# ------------------------------------------------------------------------------------------------ T-registry ---
def _reg():
    return json.load(open(W.REGISTRY_PATH, encoding="utf-8"))


def _must_fail(reg, what):
    d = tempfile.mkdtemp(prefix="e0vn21-reg-")
    try:
        p = os.path.join(d, "reg.json")
        with open(p, "w", encoding="utf-8") as fh:
            if isinstance(reg, str):
                fh.write(reg)
            else:
                json.dump(reg, fh)
        try:
            W.load_registry(p)
        except W.EvaluationError:
            return
        raise AssertionError(f"registry variant accepted: {what}")
    finally:
        shutil.rmtree(d)


def _by(reg, name):
    return next(f for f in reg["features"] if f["name"] == name)


@test
def test_registry():
    before = hashlib.sha256(open(W.REGISTRY_PATH, "rb").read()).hexdigest()
    names = W.coverage_names()
    cov = [n for n, _, _ in A21.coverage({"groups": [], "pdus": {}, "fb": [], "counts": {}}, [])]
    check(names == cov and len(names) == 18 and len(set(names)) == 18, f"coverage names {names}")
    r = W.load_registry()
    check(r["known"] == names, "registry names != coverage() names (order included)")
    check(r["admitted"] == ADMITTED, f"admitted {r['admitted']}")
    check(sorted(INFERRED + NOT_EXERCISED + ADMITTED) == sorted(names), "the three classes partition the 18 features")
    reg = r["registry"]
    for n in ADMITTED:
        f = _by(reg, n)
        check(f["strength"] in ("E1", "E2") and f["genuine"] == "explicit" and f["evidence"], f"{n}: admission evidence")
        for e in f["evidence"]:
            t = open(os.path.join(W.REPO, e["record"]), encoding="utf-8").read()
            check(e["record"] in ("simulations/m2/results/M2-S7.2a-a21-s1-closure.md",
                                  "simulations/m2/results/M2-S7.2a-a21-f3-closure.md"), f"{n}: cites {e['record']}")
            check(W.closed_accepted(t), f"{n}: {e['record']} not CLOSED ACCEPTED")
            check(e["statement"] in t, f"{n}: statement not verbatim")
    for n in INFERRED:
        check(_by(reg, n)["strength"] == "I" and _by(reg, n)["admitted"] is False, f"{n}: must be excluded, inferred only")
    for n in NOT_EXERCISED:
        check(_by(reg, n)["strength"] == "N" and _by(reg, n)["admitted"] is False, f"{n}: must be excluded, not exercised")
    for f in reg["features"]:
        for e in f["evidence"] + ([f["definition"]] if "definition" in f else []):
            check(not re.search(r"test_|harqfix|/fixtures/|\.py$", e["record"]), f"{f['name']}: cites {e['record']}")
    check(_by(reg, "mixed ACK / NACK groups")["definition"]["record"].endswith("M2-S7.2a-a2-design-review.md"),
          "the glossary definition of 'mixed'")
    check(W.closed_accepted("**Status: CLOSED. ACCEPTED** on x") and not W.closed_accepted("**Status:** NOT ACCEPTED, CLOSED")
          and not W.closed_accepted("no status line"), "status-line rule")
    # fail-closed loader: every variant below must be refused (EvaluationError, exit 2)
    v = copy.deepcopy(reg)
    _by(v, "single-candidate ACK attribution")["admitted"] = True
    _must_fail(v, "an inferred feature admitted (NC-registry-uncited)")
    # #2 cannot be refused by structure alone (its statements are verbatim and S1 is accepted): its exclusion is a
    # registry content decision (design F-3), asserted directly
    check(_by(reg, "exchangeable ACK groups (2 candidates)")["admitted"] is False, "#2 must stay excluded (design F-3)")
    v = copy.deepcopy(reg)
    v["features"].append(dict(_by(v, "retransmissions"), name="an unknown feature"))
    _must_fail(v, "an unknown feature")
    v = copy.deepcopy(reg)
    del v["features"][3]
    _must_fail(v, "a missing feature")
    v = copy.deepcopy(reg)
    v["features"][0], v["features"][1] = v["features"][1], v["features"][0]
    _must_fail(v, "reordered features")
    v = copy.deepcopy(reg)
    v["features"][1] = copy.deepcopy(v["features"][0])
    _must_fail(v, "a duplicated feature")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["evidence"][0]["statement"] += " (edited)"
    _must_fail(v, "a statement not verbatim")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["evidence"][0]["record"] = "simulations/m2/check/test_m2s72_a21.py"
    _must_fail(v, "a citation outside the results directory")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["evidence"][0]["record"] = "simulations/m2/results/../results/M2-S7.2a-a21-s1-closure.md"
    _must_fail(v, "a path with '..'")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["evidence"] = copy.deepcopy(_by(v, "single-candidate ACK attribution")["evidence"])
    _must_fail(v, "an admitted feature citing a record that is not CLOSED ACCEPTED")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["evidence"] = []
    _must_fail(v, "an admitted feature without evidence")
    v = copy.deepcopy(reg)
    _by(v, "multi-NACK groups (handle relations kept ambiguous)")["evidence"] = []
    _must_fail(v, "an excluded feature without evidence")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["genuine"] = "inferred-only"
    _must_fail(v, "genuine inconsistent with strength")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["strength"] = "E3"
    _must_fail(v, "an unknown strength")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["admitted"] = "yes"
    _must_fail(v, "a non-boolean admission")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["extra"] = 1
    _must_fail(v, "an unknown feature key")
    v = copy.deepcopy(reg)
    _by(v, "retransmissions")["evidence"][0]["page"] = 1
    _must_fail(v, "an unknown evidence key")
    v = copy.deepcopy(reg)
    _by(v, "mixed ACK / NACK groups")["definition"]["statement"] = "| GA-4 something else |"
    _must_fail(v, "a definition statement not verbatim")
    v = copy.deepcopy(reg)
    v["schema"] = "m2s72-fgo-registry/2"
    _must_fail(v, "a wrong schema")
    v = copy.deepcopy(reg)
    v["comment"] = "x"
    _must_fail(v, "an unknown top-level key")
    _must_fail("{ not json", "invalid JSON")
    try:
        W.load_registry(os.path.join(tempfile.gettempdir(), "e0vn21-no-such-registry.json"))
        raise AssertionError("a missing registry file was accepted")
    except W.EvaluationError:
        pass
    _registry_malformed(reg)
    _cli_boundary()
    after = hashlib.sha256(open(W.REGISTRY_PATH, "rb").read()).hexdigest()
    check(before == after == r["sha256"], "the committed registry changed during the test")


# -------------------------------------------------------------------------------------------------- T-schema ----
def _row(rid, subject, status, local=None):
    r = {"id": rid, "subject": subject, "status": status, "detail": "synthetic"}
    if local is not None:
        r["local"] = local
    return r


def good_digest(n=2):
    rows = [_row(W.ROW_MAP, "run", W.PASS), _row(W.ROW_C0, "run", W.PASS), _row(W.ROW_PU4H, "run", W.PASS)]
    rows += [_row(W.ROW_PU4O, f"UE {k}", W.PASS, W.EQUAL) for k in range(n)]
    rows += [_row(W.ROW_A28U, f"UE {k}", W.PASS, W.EQUAL) for k in range(n)]
    ue = {"available": True, "value": 1}
    return {
        "schema": W.DIGEST_SCHEMA, "config": "M2S72-E0vN-q0-one0-n2-f1", "kind": "E0vN", "option": "q0",
        "placement": "one0", "numUe": n, "harq16": True, "dl_factor": "1",
        "correctness": {
            "verdict": {"status": W.V_PASS, "exit": 0, "gate_failures": [], "gate_not_evaluated": [], "held_features": []},
            "rows": rows,
            "s5n": {"verdict_line": "FAIL PU-4", "gate_failures": ["PU-4"], "per_ue_not_evaluated": [], "rows": 42},
            "a21": {"rows": [], "verdict_f1d_i": "A-2.1 VALID", "verdict_full": "A-2.1 VALID", "coverage": []}},
        "performance": {
            "per_ue": [{"k": k, "harq_a21": {"counts": dict(ue), "occupancy": dict(ue), "simu5g": {"available": True, "status": "PASS"}}}
                       for k in range(n)],
            "across": {"N": n}, "across_harq_a21": {"harq_error_rate": {"available": True, "min": 0.0, "max": 0.0}},
            "totals": {"dl_grant_bytes": 1, "harq_inserts": 1}},
        "historical": {"a1": {"label": "A-1, historical rule; not a current measurement (DR-07b)",
                              "pu4_row": ["PU-4", "run", "FAIL", "A-1 ambiguous 768"], "harq_attribution": {},
                              "per_ue_harq": {}}},
        "diagnostics": {"agreement": {}}, "mac_grammar_census": [],
        "inputs": {"log_sha256": "0" * 64, "sca_sha256": "0" * 64, "registry_sha256": "0" * 64, "code": {}, "c0": {},
                   "s5n_adapter_validated": "x"}}


@test
def test_schema():
    # status vocabulary (design 4.0, 4.8)
    check(W.NE == "NOT EVALUATED" == A21.NE and W.NX == "NOT EXERCISED" == A21.NX, "NE / NX are the accepted strings")
    check(W.ROW_STATUSES == ("PASS", "FAIL", "NOT EVALUATED", "NOT EXERCISED", "NOT APPLICABLE", "HELD FOR REVIEW"), "row statuses")
    check(W.LOCAL_OUTCOMES == ("EQUAL", "DIFFERENT", "NOT COMPARED"), "local outcomes")
    check(W.EXIT == {"PASS": 0, "FAIL": 1, "REFUSED": 2, "EVALUATION ERROR": 2, "HELD FOR REVIEW": 3, "INCOMPLETE": 4}
          and W.EXIT_EXPECT_MISMATCH == 5, "exit codes")
    check([W.EXIT[v] for v in W.PRECEDENCE] == [2, 2, 1, 4, 3, 0], "precedence 2 > 1 > 4 > 3 > 0 (D-A1-11)")
    check(W.A21_VERDICTS == ("A-2.1 VALID", "A-2.1 INCOMPLETE", "A-2.1 NOT VALID"), "A-2.1 verdict strings")
    check(A21.verdict([], "f1d-i")[0] in W.A21_VERDICTS, "the accepted verdict() yields a declared string")
    d = good_digest()
    check(W.validate_digest(d) == [], f"valid digest rejected: {W.validate_digest(d)}")
    check(W.validate_digest(json.loads(json.dumps(d))) == [], "JSON round trip")
    muts = {
        "wrong schema": lambda x: x.update(schema="m2s72-s5n21-digest/2"),
        "missing top key": lambda x: x.pop("inputs"),
        "unexpected top key": lambda x: x.update(extra=1),
        "kind not E0vN": lambda x: x.update(kind="E0v"),
        "numUe bool": lambda x: x.update(numUe=True),
        "A-1 harq in per_ue": lambda x: x["performance"]["per_ue"][0].update(harq={"feedback": 1}),
        "unavailable with a value": lambda x: x["performance"]["per_ue"][1]["harq_a21"].update(
            occupancy={"available": False, "reason": "PU-4o NE", "value": 0}),
        "unavailable without a reason": lambda x: x["performance"]["per_ue"][1]["harq_a21"].update(counts={"available": False}),
        "available not boolean": lambda x: x["performance"]["per_ue"][0]["harq_a21"].update(counts={"available": 1}),
        "missing harq_a21 group": lambda x: x["performance"]["per_ue"][0]["harq_a21"].pop("simu5g"),
        "per_ue length": lambda x: x["performance"]["per_ue"].pop(),
        "partial across aggregate": lambda x: x["performance"]["across_harq_a21"].update(
            retransmissions={"available": False, "missing_ues": [1], "min": 0}),
        "verdict exit mismatch": lambda x: x["correctness"]["verdict"].update(exit=1),
        "unknown verdict": lambda x: x["correctness"]["verdict"].update(status="OK", exit=0),
        "PASS with held features": lambda x: x["correctness"]["verdict"].update(held_features=["retransmissions"]),
        "PASS with gate NE": lambda x: x["correctness"]["verdict"].update(gate_not_evaluated=["PU-4h"]),
        "row status unknown": lambda x: x["correctness"]["rows"][0].update(status="OK"),
        "row id unknown": lambda x: x["correctness"]["rows"][0].update(id="PU-4"),
        "per-UE row without local": lambda x: x["correctness"]["rows"][3].pop("local"),
        "PASS with NOT COMPARED": lambda x: x["correctness"]["rows"][3].update(local=W.NOT_COMPARED),
        "DIFFERENT not FAIL": lambda x: x["correctness"]["rows"][4].update(local=W.DIFFERENT, status=W.NE),
        "local on run-level row": lambda x: x["correctness"]["rows"][2].update(local=W.EQUAL),
        "per-UE subject": lambda x: x["correctness"]["rows"][5].update(subject="node 2049"),
        "missing per-UE row": lambda x: x["correctness"]["rows"].pop(6),
        "A-2.1 verdict string": lambda x: x["correctness"]["a21"].update(verdict_full="VALID"),
        "missing s5n key": lambda x: x["correctness"]["s5n"].pop("verdict_line"),
        "missing historical label": lambda x: x["historical"]["a1"].pop("label"),
        "missing inputs key": lambda x: x["inputs"].pop("registry_sha256"),
        "non-finite number": lambda x: x["performance"]["across_harq_a21"]["harq_error_rate"].update(max=float("nan")),
    }
    for what, m in muts.items():
        x = copy.deepcopy(d)
        m(x)
        check(W.validate_digest(x), f"digest mutation accepted: {what}")
    # allowed non-PASS combinations of a per-UE row (local EQUAL, row FAIL / NE by the global rules)
    for st in (W.FAIL, W.NE):
        check(W.validate_row(_row(W.ROW_PU4O, "UE 1", st, W.EQUAL)) == [], f"global {st} with local EQUAL")
    check(W.validate_row(_row(W.ROW_A28U, "UE 0", W.NE, W.NOT_COMPARED)) == [], "NE with NOT COMPARED")
    check(W.validate_row(_row(W.ROW_A28U, "UE 0", W.FAIL, W.DIFFERENT)) == [], "FAIL with DIFFERENT")
    check(W.validate_row(["PU-4h", "run", "PASS", "x"]), "a list row must be rejected (rows are objects)")
    _digest_consistency()
    _schema_malformed()


# ------------------------------------------------------------- I1-R2: malformed JSON-compatible inputs ---------
JUNK = [None, True, False, 0, -1, 7, 1.5, float("nan"), "", "x", "UE 99", [], [None], [[]], [{}], {}, {"a": []}, {"": None}]


def _paths(x, path=()):
    """every (path) to a value inside a JSON-compatible object, the root included"""
    yield path
    if isinstance(x, dict):
        for k, v in x.items():
            yield from _paths(v, path + (k,))
    elif isinstance(x, list):
        for i, v in enumerate(x):
            yield from _paths(v, path + (i,))


def _get(x, path):
    for k in path:
        x = x[k]
    return x


def _variants(obj):
    """(description, mutated copy, original value, changed type?) for every path: each JUNK replacement and deletion"""
    for path in _paths(obj):
        orig = _get(obj, path)
        for j in JUNK:
            if type(j) is type(orig) and j == orig:
                continue
            x = copy.deepcopy(obj)
            if path:
                _get(x, path[:-1])[path[-1]] = copy.deepcopy(j)
            else:
                x = copy.deepcopy(j)
            yield f"{path} := {j!r}", x, path, type(j) is not type(orig)
        if path:
            x = copy.deepcopy(obj)
            del _get(x, path[:-1])[path[-1]]
            yield f"del {path}", x, path, True


def _no_raise(fn, x, what):
    try:
        out = fn(x)
    except Exception as ex:
        raise AssertionError(f"{fn.__name__} raised {type(ex).__name__} on {what}: {ex}")
    check(isinstance(out, list) and all(isinstance(p_, str) and p_ for p_ in out), f"{fn.__name__} on {what}: not a problem list")
    return out


def _registry_malformed(reg):
    names = W.coverage_names()
    n = 0
    for what, x, path, changed in _variants(reg):
        out = _no_raise(lambda r: W.validate_registry(r, names), x, what)
        n += 1
        # in the registry every key is fixed, and every value is typed or checked verbatim: any change of type or any
        # deletion is a problem; the only optional key is 'definition'
        # deleting one entry of an evidence list that keeps another entry is legitimately still valid
        shrink = what.startswith("del") and isinstance(path[-1], int) and path[-2:-1] == ("evidence",) and \
            len(_get(reg, path[:-1])) > 1
        if changed and path[-1:] != ("definition",) and not shrink:
            check(out, f"registry variant accepted: {what}")
    check(n > 3000, f"only {n} registry variants")
    # explicit malformed evidence entries (I1-R2)
    for bad in (None, [], "x", 1, {}, {"record": 1}, {"record": "simulations/m2/results/M2-S7.2a-a21-s1-closure.md"},
                dict.fromkeys(W.EVIDENCE_KEYS, ""), dict.fromkeys(W.EVIDENCE_KEYS, ["x"]),
                dict(dict.fromkeys(W.EVIDENCE_KEYS, "x"), record="/etc/passwd"),
                dict(dict.fromkeys(W.EVIDENCE_KEYS, "x"), record="simulations/m2/results/no-such-record.md"),
                dict(dict.fromkeys(W.EVIDENCE_KEYS, "x"), record="simulations/m2/results/a\x00b.md"),
                dict(dict.fromkeys(W.EVIDENCE_KEYS, "x"), record="simulations/m2/results/..\\check\\m2s72_a21.py")):
        v = copy.deepcopy(reg)
        _by(v, "retransmissions")["evidence"] = [bad]
        check(_no_raise(lambda r: W.validate_registry(r, names), v, f"evidence {bad!r}"), f"malformed evidence accepted: {bad!r}")
    for top in (None, [], "x", 0, {"schema": W.REGISTRY_SCHEMA}, {"schema": W.REGISTRY_SCHEMA, "features": None},
                {"schema": W.REGISTRY_SCHEMA, "features": [None] * 18}, {"schema": [], "features": []}):
        check(_no_raise(lambda r: W.validate_registry(r, names), top, f"top {top!r}"), f"registry accepted: {top!r}")
    _must_fail("[1, 2, 3]", "a JSON list")
    d = tempfile.mkdtemp(prefix="e0vn21-reg-")
    try:
        p_ = os.path.join(d, "bad.json")
        open(p_, "wb").write(b"\xff\xfe\x00")
        try:
            W.load_registry(p_)
            raise AssertionError("non-UTF-8 registry accepted")
        except W.EvaluationError:
            pass
        open(p_, "w").write("[" * 100000)
        try:
            W.load_registry(p_)
            raise AssertionError("deeply nested registry accepted")
        except W.EvaluationError:
            pass
        for bad_path in (d, None, 1):
            try:
                W.load_registry(bad_path)
                raise AssertionError(f"registry path {bad_path!r} accepted")
            except W.EvaluationError:
                pass
    finally:
        shutil.rmtree(d)


def _cli_boundary():
    """exit 2 at the CLI boundary for a refusal, an evaluation error and any other exception (I1-R2)"""
    import contextlib
    import io
    import check_m2s72_s5n21 as CLI
    orig = CLI._dispatch
    try:
        for exc, word in ((W.Refused("x"), "REFUSED"), (W.EvaluationError("registry invalid"), "EVALUATION ERROR"),
                          (KeyError("k"), "EVALUATION ERROR"), (TypeError("t"), "EVALUATION ERROR")):
            def boom(argv, exc=exc):
                raise exc
            CLI._dispatch = boom
            buf = io.StringIO()
            with contextlib.redirect_stdout(buf):
                rc = CLI.main(["check_m2s72_s5n21.py", "run"])
            check(rc == 2 and buf.getvalue().startswith(word), f"CLI boundary {type(exc).__name__}: rc {rc}, {buf.getvalue()[:80]}")
        CLI._dispatch = lambda argv: W.load_registry(os.path.join(tempfile.gettempdir(), "e0vn21-missing.json"))
        with contextlib.redirect_stdout(io.StringIO()):
            check(CLI.main(["x", "run"]) == 2, "a registry error at the CLI boundary must exit 2")
    finally:
        CLI._dispatch = orig


def _schema_malformed():
    d = good_digest()
    n = 0
    for what, x, path, changed in _variants(d):
        _no_raise(W.validate_digest, x, what)
        n += 1
    check(n > 2000, f"only {n} digest variants")
    # every structural position must reject a change of type or a deletion
    structural = [("schema",), ("config",), ("kind",), ("numUe",), ("correctness",), ("correctness", "verdict"),
                  ("correctness", "verdict", "status"), ("correctness", "verdict", "exit"),
                  ("correctness", "verdict", "gate_failures"), ("correctness", "verdict", "gate_not_evaluated"),
                  ("correctness", "verdict", "held_features"), ("correctness", "rows"), ("correctness", "s5n"),
                  ("correctness", "s5n", "gate_failures"), ("correctness", "a21"), ("correctness", "a21", "rows"),
                  ("correctness", "a21", "verdict_f1d_i"), ("performance",), ("performance", "per_ue"),
                  ("performance", "across_harq_a21"), ("historical",), ("historical", "a1"), ("historical", "a1", "label"),
                  ("inputs",), ("inputs", "registry_sha256"), ("mac_grammar_census",), ("diagnostics",)]
    for i in range(len(d["correctness"]["rows"])):
        structural += [("correctness", "rows", i)] + [("correctness", "rows", i, k) for k in ("id", "subject", "status", "detail")]
    for k in range(d["numUe"]):
        structural += [("performance", "per_ue", k), ("performance", "per_ue", k, "harq_a21"),
                       ("performance", "per_ue", k, "harq_a21", "counts"),
                       ("performance", "per_ue", k, "harq_a21", "occupancy", "available")]
    structural = set(structural)
    checked = 0
    for what, x, path, changed in _variants(d):
        if path in structural and changed:
            check(W.validate_digest(x), f"digest variant accepted: {what}")
            checked += 1
    check(checked > 1000, f"only {checked} structural digest variants")
    for r in (None, [], "x", 1, {}, {"id": "PU-4o"}, dict.fromkeys(W.ROW_KEYS, None), dict.fromkeys(W.ROW_KEYS, []),
              dict.fromkeys(W.ROW_KEYS, {}), {"id": ["PU-4h"], "subject": {}, "status": [], "detail": 1, "local": []},
              {"id": "PU-4o", "subject": ["UE 0"], "status": "PASS", "detail": "x", "local": {"EQUAL": 1}}):
        check(_no_raise(W.validate_row, r, f"row {r!r}"), f"malformed row accepted: {r!r}")
    for top in (None, [], "x", 0, {}, {k: None for k in W.DIGEST_KEYS}, {k: [] for k in W.DIGEST_KEYS},
                {k: {} for k in W.DIGEST_KEYS}, {k: "x" for k in W.DIGEST_KEYS}):
        check(_no_raise(W.validate_digest, top, f"digest {str(top)[:60]}"), f"malformed digest accepted: {str(top)[:60]}")


# ------------------------------------------------------------- I1-R1: row completeness and verdict consistency -
def _set_rows(d, status_of):
    """status_of(id, subject) -> (status, local or None) for every wrapper row of d"""
    for r in d["correctness"]["rows"]:
        st, loc = status_of(r["id"], r["subject"])
        r["status"] = st
        if loc is not None:
            r["local"] = loc


def _verdict(d, status, fails=(), nes=(), held=()):
    d["correctness"]["verdict"] = {"status": status, "exit": W.EXIT[status], "gate_failures": list(fails),
                                   "gate_not_evaluated": list(nes), "held_features": list(held)}


def fail_digest():
    d = good_digest()
    d["correctness"]["a21"]["verdict_f1d_i"] = "A-2.1 NOT VALID"
    _set_rows(d, lambda rid, subj: (W.PASS, None) if rid in (W.ROW_MAP, W.ROW_C0) else
              (W.FAIL, W.EQUAL if rid in W.PER_UE_ROWS else None))
    _verdict(d, W.V_FAIL, fails=sorted([W.ROW_PU4H, W.ROW_PU4O, W.ROW_A28U]))
    return d


def incomplete_digest():
    d = good_digest()
    d["correctness"]["a21"]["verdict_f1d_i"] = "A-2.1 INCOMPLETE"
    _set_rows(d, lambda rid, subj: (W.PASS, None) if rid in (W.ROW_MAP, W.ROW_C0) else
              (W.NE, W.EQUAL if rid in W.PER_UE_ROWS else None))
    _verdict(d, W.V_INCOMPLETE, nes=sorted([W.ROW_PU4H, W.ROW_PU4O, W.ROW_A28U]), held=["single-candidate ACK attribution"])
    return d


def held_digest():
    d = good_digest()
    _verdict(d, W.V_HELD, held=["single-candidate ACK attribution", "exchangeable ACK groups (2 candidates)"])
    return d


def _digest_consistency():
    for name, fn in (("FAIL", fail_digest), ("INCOMPLETE", incomplete_digest), ("HELD", held_digest)):
        check(W.validate_digest(fn()) == [], f"consistent {name} digest rejected: {W.validate_digest(fn())}")
    x = good_digest()
    x["correctness"]["verdict"]["gate_failures"] = ["SG-403"]
    x["correctness"]["s5n"]["gate_failures"] = ["PU-4", "SG-403"]
    _verdict(x, W.V_FAIL, fails=["SG-403"])
    check(W.validate_digest(x) == [], f"an s5n gate failure carried over: {W.validate_digest(x)}")
    rows = lambda x: x["correctness"]["rows"]
    def drop(rid, subj):
        return lambda x: rows(x).remove(next(r for r in rows(x) if r["id"] == rid and r["subject"] == subj))
    def dup(i):
        return lambda x: rows(x).append(copy.deepcopy(rows(x)[i]))
    def set_row(rid, subj, **kv):
        return lambda x: next(r for r in rows(x) if r["id"] == rid and r["subject"] == subj).update(kv)
    cases = {
        # completeness and uniqueness
        "no MAP-UE": (good_digest, drop(W.ROW_MAP, "run")),
        "no C-0": (good_digest, drop(W.ROW_C0, "run")),
        "no PU-4h": (good_digest, drop(W.ROW_PU4H, "run")),
        "no PU-4o UE 0": (good_digest, drop(W.ROW_PU4O, "UE 0")),
        "no A2-8u UE 1": (good_digest, drop(W.ROW_A28U, "UE 1")),
        "duplicate MAP-UE": (good_digest, dup(0)),
        "duplicate PU-4h": (good_digest, dup(2)),
        "duplicate PU-4o UE 1": (good_digest, dup(4)),
        "duplicate PU-4h with another status": (good_digest, lambda x: rows(x).append(dict(rows(x)[2], status=W.FAIL))),
        "PU-4o UE 2 with numUe 2": (good_digest, lambda x: rows(x).append(_row(W.ROW_PU4O, "UE 2", W.PASS, W.EQUAL))),
        "A2-8u UE 7 with numUe 2": (good_digest, lambda x: rows(x).append(_row(W.ROW_A28U, "UE 7", W.PASS, W.EQUAL))),
        "UE 01 subject": (good_digest, set_row(W.ROW_PU4O, "UE 1", subject="UE 01")),
        "run-level subject not 'run'": (good_digest, set_row(W.ROW_C0, "run", subject="UE 0")),
        "wrapper row HELD FOR REVIEW": (good_digest, set_row(W.ROW_C0, "run", status=W.HR)),
        "wrapper row NOT EXERCISED": (good_digest, set_row(W.ROW_MAP, "run", status=W.NX)),
        # PASS with a gate not PASS
        "PASS with MAP-UE FAIL": (good_digest, set_row(W.ROW_MAP, "run", status=W.FAIL)),
        "PASS with C-0 NE": (good_digest, set_row(W.ROW_C0, "run", status=W.NE)),
        "PASS with PU-4h NE": (good_digest, set_row(W.ROW_PU4H, "run", status=W.NE)),
        "PASS with PU-4o UE 1 FAIL": (good_digest, set_row(W.ROW_PU4O, "UE 1", status=W.FAIL)),
        "PASS with A2-8u UE 0 NE": (good_digest, set_row(W.ROW_A28U, "UE 0", status=W.NE, local=W.NOT_COMPARED)),
        "PASS with a failing s5n gate": (good_digest, lambda x: x["correctness"]["s5n"].update(gate_failures=["SG-403"])),
        "PASS with an s5n NE gate": (good_digest, lambda x: x["correctness"]["s5n"].update(per_ue_not_evaluated=["AV-3"])),
        "PASS with held features": (good_digest, lambda x: x["correctness"]["verdict"].update(held_features=["retransmissions"])),
        # verdict vs lists
        "FAIL with empty lists": (good_digest, lambda x: _verdict(x, W.V_FAIL)),
        "INCOMPLETE without NE": (held_digest, lambda x: x["correctness"]["verdict"].update(status=W.V_INCOMPLETE, exit=4)),
        "HELD with gate NE": (incomplete_digest, lambda x: x["correctness"]["verdict"].update(status=W.V_HELD, exit=3)),
        "INCOMPLETE with a failure": (fail_digest, lambda x: x["correctness"]["verdict"].update(status=W.V_INCOMPLETE, exit=4)),
        "PASS with failures listed": (fail_digest, lambda x: x["correctness"]["verdict"].update(status=W.V_PASS, exit=0)),
        "FAIL list misses a FAIL row": (fail_digest, lambda x: x["correctness"]["verdict"].update(gate_failures=[W.ROW_PU4H, W.ROW_PU4O])),
        "FAIL list names a PASS row": (fail_digest, lambda x: x["correctness"]["verdict"]["gate_failures"].append(W.ROW_C0)),
        "NE list misses an NE row": (incomplete_digest, lambda x: x["correctness"]["verdict"].update(gate_not_evaluated=[W.ROW_PU4H])),
        "NE list names a FAIL-free PASS row": (incomplete_digest, lambda x: x["correctness"]["verdict"]["gate_not_evaluated"].append(W.ROW_MAP)),
        "duplicate gate list entry": (fail_digest, lambda x: x["correctness"]["verdict"]["gate_failures"].append(W.ROW_PU4H)),
        "gate list with a non-string": (fail_digest, lambda x: x["correctness"]["verdict"]["gate_failures"].append(1)),
        "s5n failure not carried over": (good_digest, lambda x: (x["correctness"]["s5n"].update(gate_failures=["MG-1"]),
                                                                  _verdict(x, W.V_FAIL, fails=[]))),
        "PU-4 listed as a gate": (good_digest, lambda x: _verdict(x, W.V_FAIL, fails=["PU-4"])),
        "REFUSED digest": (good_digest, lambda x: x["correctness"]["verdict"].update(status=W.V_REFUSED, exit=2)),
        # global rules between rows
        "PU-4h PASS with MAP-UE FAIL (lists consistent)": (good_digest, lambda x: (set_row(W.ROW_MAP, "run", status=W.FAIL)(x),
                                                                                   _verdict(x, W.V_FAIL, fails=[W.ROW_MAP]))),
        "per-UE PASS with PU-4h NE (lists consistent)": (good_digest, lambda x: (set_row(W.ROW_PU4H, "run", status=W.NE)(x),
                                                                                 _verdict(x, W.V_INCOMPLETE, nes=[W.ROW_PU4H]))),
        "per-UE NE with PU-4h FAIL": (fail_digest, lambda x: (set_row(W.ROW_A28U, "UE 0", status=W.NE)(x),
                                                              _verdict(x, W.V_FAIL, fails=[W.ROW_PU4H, W.ROW_PU4O, W.ROW_A28U],
                                                                       nes=[W.ROW_A28U]))),
        "PU-4h PASS with F1-d(i) INCOMPLETE": (good_digest, lambda x: x["correctness"]["a21"].update(verdict_f1d_i="A-2.1 INCOMPLETE")),
        "PU-4h NE with F1-d(i) NOT VALID": (incomplete_digest, lambda x: x["correctness"]["a21"].update(verdict_f1d_i="A-2.1 NOT VALID")),
        "PU-4o PASS with A2-7 NE": (good_digest, lambda x: x["correctness"]["a21"].update(rows=[["A2-7", "run", W.NE, "touched"]])),
        "config not admissible": (good_digest, lambda x: x.update(config="M2S72-E0vN-q0-one0-n2-f1_A2V1")),
        "missing_ues outside the UEs": (good_digest, lambda x: x["performance"]["across_harq_a21"].update(
            occupancy_mean={"available": False, "missing_ues": [5]})),
        "per_ue k out of order": (good_digest, lambda x: x["performance"]["per_ue"].reverse()),
    }
    for what, (base, mut) in cases.items():
        x = base()
        mut(x)
        check(W.validate_digest(x), f"inconsistent digest accepted: {what}")


# --------------------------------------------------------------------------------------- T-imports-isolated ----
def _run(args, cwd):
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON")}
    return subprocess.run([sys.executable] + args, cwd=cwd, env=env, capture_output=True, text=True, timeout=300)


@test
def test_imports_isolated():
    check(sys.version_info >= (3, 11), f"Python {sys.version.split()[0]}: -I implies -P only from 3.11")
    d = tempfile.mkdtemp(prefix="e0vn21-iso-")
    try:
        # control: under -I neither the working directory nor the caller's script directory is on sys.path, so a plain
        # import of the library fails: the test below is therefore meaningful
        r = _run(["-I", "-B", "-c", "import m2s72_e0vn21"], d)
        check(r.returncode != 0 and "ModuleNotFoundError" in r.stderr, f"control: a bare import succeeded under -I ({r.returncode})")
        r = _run(["-I", "-B", "-c", "import sys; print(repr(sys.path[0]))"], d)
        check(r.returncode == 0 and repr(d) not in r.stdout, f"-I put the working directory on sys.path: {r.stdout}")
        # the CLI (usage only in I-1): rc 2, its usage, no import failure
        for args in ([CLI], [CLI, "--help"], [CLI, "run", "x", "M2S72-E0vN-q0-one0-n2-f1", "y"]):
            r = _run(["-I", "-B"] + args, d)
            check(r.returncode == 2 and "Traceback" not in r.stderr and "Error" not in r.stderr,
                  f"CLI {args[1:]}: rc {r.returncode}, stderr {r.stderr[-400:]}")
            check("check_m2s72_s5n21.py run" in r.stdout or "not implemented in increment I-1" in r.stdout, f"CLI output {r.stdout[:200]}")
        # the library, executed by path (its own preamble must make m2s72_a21 and the frozen modules importable)
        r = _run(["-I", "-B", "-c", f"import runpy; g = runpy.run_path({LIB!r}); print(len(g['coverage_names']()))"], d)
        check(r.returncode == 0 and r.stdout.strip() == "18", f"library under -I: rc {r.returncode}, {r.stderr[-400:]}")
        # the suite itself
        r = _run(["-I", "-B", SELF, "--import-only"], d)
        check(r.returncode == 0 and "imports OK" in r.stdout, f"suite under -I: rc {r.returncode}, {r.stderr[-400:]}")
        check(not os.listdir(d), f"files written into the working directory: {os.listdir(d)}")
    finally:
        shutil.rmtree(d)


# ------------------------------------------------------------------------------------------------------- main ---
def main():
    if sys.argv[1:] == ["--import-only"]:
        print(f"imports OK: {W.__file__}; {A21.__file__}")
        return 0
    before = hashlib.sha256(open(W.REGISTRY_PATH, "rb").read()).hexdigest()
    only = sys.argv[1:]
    run = [(n, f) for n, f in TESTS if not only or any(n.startswith(o) for o in only)]
    fails = 0
    for name, f in run:
        try:
            f()
            print(f"PASS  {name}")
        except Exception as ex:
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {name}: {type(ex).__name__}: {str(ex)[:800]}")
    if hashlib.sha256(open(W.REGISTRY_PATH, "rb").read()).hexdigest() != before:
        fails += 1
        print("FAIL  T-registry-immutable: the committed registry changed during the suite")
    print(f"WP-A1 e0vn21 tests: {len(run) - fails} / {len(run)} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
