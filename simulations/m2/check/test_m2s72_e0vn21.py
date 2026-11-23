#!/usr/bin/env python3
"""Tests of the WP-A1 wrapper (design revision 2.1, 57a80ca, section 7). Increment I-1: T-name-guard, T-registry,
T-schema, T-imports-isolated. Increment I-2: T-map, T-a28-compat, NC-scalar-ue1, NC-scalar-missing-ue1.
Increment I-3: T-c0, NC-c0, T-n2-same-tti, T-n2-a2v1-like, T-n4-independent, T-n4-overlap-nack, T-censor-*,
T-unresolved, NC-no-ue-lines, NC-swap, NC-occ, T-pu4h. Increment I-4: T-agree, NC-pu4-relabel.
Increment I-5: T-n3-groups, T-multinack, T-discard, NC-registry, T-a24c-review, T-verdict, T-s5n-semantics.
Increment I-6: T-f3-hrq, T-f3-a1, T-single-replay, T-a21-record-equiv, T-expect-exit, NC-cli-inputs; T-imports-isolated
on the functional CLI.
Increment I-7: T-s5n-transparent, T-s5n-rows, T-digest-ownership, T-one-run-per-process, T-no-d2-bypass, NC-run. I-7 corrections: NC-provenance; T-s5n-rows on the derived row contract.
Increment I-8: T-controls (the controls mode, design 7.3), T-n1-identity, T-a1-frozen, T-a1-a21-pinned, T-a1-s5n-pinned,
T-registry-immutable, T-expect-files. The I-2 and I-3 tests that run the accepted A-2.1 need
SIMU5G_ROOT (the Simu5G 1.8.1 sources, for A2-0s), as test_m2s72_a21.py does; tier-0 provides it. No simulation; no raw output of any run; synthetic inputs and repository files only.
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
            "a21": {"rows": [[k, "run", "PASS", ""] for k in W.A21_ROW_IDS], "verdict_f1d_i": "A-2.1 VALID",
                    "verdict_full": "A-2.1 VALID", "coverage": []}},
        "performance": {
            "per_ue": [{"k": k, "harq_a21": {"counts": dict(ue), "occupancy": dict(ue), "simu5g": {"available": True, "status": "PASS"}}}
                       for k in range(n)],
            "across": {"N": n}, "across_harq_a21": {"harq_error_rate": {"available": True, "min": 0.0, "max": 0.0}},
            "totals": {"dl_grant_bytes": 1, "harq_inserts": 1}},
        "historical": {"a1": {"label": "A-1, historical rule; not a current measurement (DR-07b)",
                              "pu4_row": ["PU-4", "run", "FAIL", "A-1 ambiguous 768"], "harq_attribution": {},
                              "per_ue_harq": {}}},
        "diagnostics": {"agreement": {}}, "mac_grammar_census": [],
        "inputs": {"log_sha256": "0" * 64, "sca_sha256": "0" * 64, "registry_sha256": "0" * 64, "consumed_sha256": {"runs:x": "0" * 64},
                   "code": {"required": {}, "loaded": {}}, "c0": {},
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
        "PU-4o PASS with A2-7 NE": (good_digest, lambda x: x["correctness"]["a21"].update(
            rows=[[k, "run", W.NE if k == "A2-7" else "PASS", ""] for k in W.A21_ROW_IDS])),
        "A-2.1 rows without A2-7": (good_digest, lambda x: x["correctness"]["a21"].update(
            rows=[[k, "run", "PASS", ""] for k in W.A21_ROW_IDS if k != "A2-7"])),
        "A-2.1 rows without A2-8": (good_digest, lambda x: x["correctness"]["a21"].update(
            rows=[[k, "run", "PASS", ""] for k in W.A21_ROW_IDS if k != "A2-8"])),
        "A-2.1 row duplicated": (good_digest, lambda x: x["correctness"]["a21"]["rows"].append(["A2-7", "run", "PASS", ""])),
        "A-2.1 row unknown": (good_digest, lambda x: x["correctness"]["a21"]["rows"].append(["A2-10", "run", "PASS", ""])),
        "A-2.1 row status unknown": (good_digest, lambda x: x["correctness"]["a21"]["rows"].__setitem__(10, ["A2-7", "run", "HELD FOR REVIEW", ""])),
        "config not admissible": (good_digest, lambda x: x.update(config="M2S72-E0vN-q0-one0-n2-f1_A2V1")),
        "missing_ues outside the UEs": (good_digest, lambda x: x["performance"]["across_harq_a21"].update(
            occupancy_mean={"available": False, "missing_ues": [5]})),
        "per_ue k out of order": (good_digest, lambda x: x["performance"]["per_ue"].reverse()),
    }
    for what, (base, mut) in cases.items():
        x = base()
        mut(x)
        check(W.validate_digest(x), f"inconsistent digest accepted: {what}")


# ================================================================================================ I-2 ============
import m2s72_a2 as A2  # noqa: E402  (frozen; read-only: sca_nodes)
import m2s72_a2probe as PR  # noqa: E402  (frozen; read-only: scalars)
import m2s72_harqfix21 as G  # noqa: E402  (accepted corrected generator; synthetic, labelled)

NODES2 = {0: 2049, 1: 2050}
ER, TX = W.A28_STATS
TOL = A21.REL_TOL


def named(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def mkres(spec, censored=()):
    """a synthetic A-2.1 replay result holding only the fields A2-8 reads: spec {node: (feedback results, ntx of the
    ACKed lifecycles)}; censored: nodes of a group censored at the end (touched_nodes)"""
    fb, pdus, pid = [], {}, 1000
    for n, (results, ntx) in spec.items():
        fb += [{"owner": n, "res": r} for r in results]
        for x in ntx:
            pid += 1
            pdus[pid] = {"node": n, "end": "ack", "ntx": x}
    groups = [{"censored_nodes": sorted(censored)}] if censored else []
    return {"fb": fb, "pdus": pdus, "groups": groups}


BASE = {2049: (["ACK"] * 10, [1] * 10), 2050: (["ACK"] * 9 + ["NACK"] * 3, [1] * 6 + [2] * 3)}   # UE 1: 0.25 / 4/3


def truth_values(spec):
    return {n: (sum(r == "NACK" for r in res) / len(res) if res else None, sum(ntx) / len(ntx) if ntx else None)
            for n, (res, ntx) in spec.items()}


def write_sca(d, nodes, values, extra=(), drop_par=(), name="0.sca"):
    """values: {k: {stat: text}} (a stat missing from the dict is not written); par macNodeId for every k not in drop_par"""
    rows = ["version 3\n", "run M2S72-synthetic-0\n"]
    for k, n in nodes.items():
        if k not in drop_par:
            rows.append(f"par {W.ue_module(k)} macNodeId {n}\n")
        for stat, v in values.get(k, {}).items():
            rows.append(f"scalar {W.ue_module(k)} {stat} {v}\n")
    rows += list(extra)
    p = os.path.join(d, name)
    with open(p, "w") as fh:
        fh.writelines(rows)
    return p


def std_values(spec, nodes=NODES2, override=None):
    tv = truth_values(spec)
    vals = {k: {ER: repr(tv[n][0]), TX: repr(tv[n][1])} for k, n in nodes.items() if n in tv and tv[n][0] is not None and tv[n][1] is not None}
    for k, upd in (override or {}).items():
        vals.setdefault(k, {}).update(upd)
        vals[k] = {s_: v for s_, v in vals[k].items() if v is not None}
    return vals


def evaluate_case(d, spec, values, censored=(), nodes=NODES2, extra=(), drop_par=(), map_status=None, pu4h="PASS"):
    """returns (R row, locals, rows, map row): R = the frozen run-level A2-8 (m2s72_a21.scalar_row, called here only
    to obtain the reference status; the wrapper never calls it), the local outcomes and the A2-8u rows"""
    sca = write_sca(d, nodes, values, extra=extra, drop_par=drop_par)
    res = mkres(spec, censored)
    lines = open(sca).read().splitlines(True)
    sc, smap, dups = PR.scalars(sca), A2.sca_nodes(sca), W.scalar_record_counts(lines)
    before = (copy.deepcopy(res), copy.deepcopy(sc), copy.deepcopy(smap), hashlib.sha256(open(sca, "rb").read()).hexdigest())
    r_frozen, _ = A21.scalar_row(copy.deepcopy(res), sca)
    mrow = W.map_ue(len(nodes), dict(nodes), smap, W.evidence_nodes(res, None, None))
    rows, locs = W.a28u_rows(len(nodes), dict(nodes), sc, smap, res, dups, map_status or mrow["status"], pu4h)
    after = (res, sc, smap, hashlib.sha256(open(sca, "rb").read()).hexdigest())
    check(before == after, "the wrapper modified its inputs or the .sca")
    check(A21.scalar_row(copy.deepcopy(res), sca)[0] == r_frozen, "the frozen run-level A2-8 changed after the wrapper ran")
    for r in rows:
        check(W.validate_row(r) == [], f"row schema {W.validate_row(r)}")
    return r_frozen, locs, rows, mrow


def L(locs):
    return [x["local"] for x in locs]


def ST(rows):
    return [r["status"] for r in rows]


def steps(locs, k):
    return {n: v["step"] for n, v in locs[k]["stats"].items()}


# ---------------------------------------------------------------------------------------------------- T-map -----
@named("T-map")
def t_map():
    ev = lambda **kw: dict({"pdus": set(), "per": set(), "occupancy_equal": set(), "skipped": set()}, **kw)
    good_sca = {W.ue_module(0): 2049, W.ue_module(1): 2050}
    check(W.map_ue(2, dict(NODES2), dict(good_sca), ev(pdus={2049, 2050}))["status"] == "PASS", "valid N = 2 with .sca")
    check(W.map_ue(2, dict(NODES2), None, ev(pdus={2049}))["status"] == "PASS", "valid N = 2 without .sca (hrq-fixture)")
    fails = {
        "duplicate node id": (2, {0: 2049, 1: 2049}, None, ev()),
        "UE 1 without a node (incomplete map)": (2, {0: 2049}, None, ev()),
        "an extra UE 2 in the map": (2, {0: 2049, 1: 2050, 2: 2051}, None, ev()),
        "a string UE key": (2, {"0": 2049, 1: 2050}, None, ev()),
        "a boolean node id": (2, {0: True, 1: 2050}, None, ev()),
        "a negative node id": (2, {0: -1, 1: 2050}, None, ev()),
        "a float node id": (2, {0: 2049.0, 1: 2050}, None, ev()),
        "the map is a list": (2, [2049, 2050], None, ev()),
        ".sca: an extra ue[2] module": (2, dict(NODES2), dict(good_sca, **{W.ue_module(2): 2051}), ev()),
        ".sca: ue[1] module missing": (2, dict(NODES2), {W.ue_module(0): 2049}, ev()),
        ".sca: ue[1] with a different id": (2, dict(NODES2), {W.ue_module(0): 2049, W.ue_module(1): 2060}, ev()),
        ".sca: ids swapped between modules": (2, dict(NODES2), {W.ue_module(0): 2050, W.ue_module(1): 2049}, ev()),
        ".sca: an empty module map": (2, dict(NODES2), {}, ev()),
        ".sca: not a mapping": (2, dict(NODES2), [1], ev()),
        "a PDU for an unmapped node": (2, dict(NODES2), dict(good_sca), ev(pdus={2049, 2051})),
        "per-UE output for an unmapped node": (2, dict(NODES2), dict(good_sca), ev(per={2052})),
        "an occupancy entry for an unmapped node": (2, dict(NODES2), dict(good_sca), ev(occupancy_equal={2049, 9})),
        "a skipped unmapped node": (2, dict(NODES2), dict(good_sca), ev(skipped={7})),
        "a None node in the evidence": (2, dict(NODES2), dict(good_sca), ev(pdus={None})),
    }
    for what, (n, nid, smap, e) in fails.items():
        args = copy.deepcopy((n, nid, smap, e))
        r = W.map_ue(n, nid, smap, e)
        check(r["status"] == "FAIL" and r["detail"] and W.validate_row(r) == [], f"MAP-UE not FAIL for {what}: {r}")
        check((n, nid, smap, e) == args, f"map_ue modified its inputs ({what})")
    for nid in (None,):
        try:
            W.map_ue(2, nid, None, ev())
            raise AssertionError("an unavailable mapping was not REFUSED")
        except W.Refused:
            pass
    for n in (0, -1, True, "2", None, 2.0):
        try:
            W.map_ue(n, dict(NODES2), None, ev())
            raise AssertionError(f"numUe {n!r} accepted")
        except W.EvaluationError:
            pass
    # the real readers: the frozen sca_nodes() of a written .sca, and the evidence of a genuine replay (synthetic log)
    d = tempfile.mkdtemp(prefix="e0vn21-map-")
    try:
        nodes4 = {k: 2049 + k for k in range(4)}
        sca = write_sca(d, nodes4, {})
        check(W.map_ue(4, nodes4, A2.sca_nodes(sca), ev())["status"] == "PASS", "sca_nodes() of a 4-UE .sca")
        sca = write_sca(d, nodes4, {}, drop_par=(3,), name="drop.sca")
        check(W.map_ue(4, nodes4, A2.sca_nodes(sca), ev())["status"] == "FAIL", "a .sca without ue[3]'s macNodeId")
        sca = write_sca(d, nodes4, {}, extra=[f"par {W.ue_module(4)} macNodeId 2053\n"], name="extra.sca")
        check(W.map_ue(4, nodes4, A2.sca_nodes(sca), ev())["status"] == "FAIL", "a .sca with an extra ue[4]")
        lines, node, truth = G.make(4, 30, lambda tti: [k for k in range(4) if (tti + k) % 2 == 0], tail=40)
        res, rows, per, cov, extra, window = A21.evaluate(lines, 16, 0, node, None, None, None)
        evn = W.evidence_nodes(res, per, extra["xa"])
        check(evn["pdus"] == set(node.values()) and evn["per"] == set(node.values()), f"evidence nodes {evn}")
        check(W.map_ue(4, dict(node), None, evn)["status"] == "PASS", "a genuine replay's evidence")
        bad = dict(node)
        bad[3] = 4000
        check(W.map_ue(4, bad, None, evn)["status"] == "FAIL", "replay evidence for a node outside a wrong map")
    finally:
        shutil.rmtree(d)
    for junk in (None, [], "x", 1, {"pdus": None}):
        W.evidence_nodes(junk, junk, junk)          # never raises


# -------------------------------------------------------------------------------------------- T-a28-compat ------
@named("T-a28-compat")
def t_a28_compat():
    d = tempfile.mkdtemp(prefix="e0vn21-a28-")
    tv = truth_values(BASE)
    check(tv[2050] == (0.25, 4 / 3), f"base values {tv}")
    try:
        def case(what, spec=BASE, values=None, censored=(), want_r=None, want_l=None, want_rows=None, pu4h="PASS",
                 cr=True, **kw):
            r, locs, rows, mrow = evaluate_case(d, spec, std_values(spec) if values is None else values, censored, pu4h=pu4h, **kw)
            check(want_r is None or r[2] == want_r, f"{what}: R {r[2]} (expected {want_r}): {r[3][:200]}")
            check(want_l is None or L(locs) == want_l, f"{what}: L {L(locs)} (expected {want_l}); {[x['detail'] for x in locs]}")
            check(want_rows is None or ST(rows) == want_rows, f"{what}: rows {ST(rows)} (expected {want_rows})")
            if cr and mrow["status"] == "PASS":
                v = W.cr_violations(r[2], locs, list(NODES2.values()), A21.touched_nodes(mkres(spec, censored)))
                check(not v, f"{what}: {v}")
            return r, locs, rows, mrow
        E, D, N = W.EQUAL, W.DIFFERENT, W.NOT_COMPARED
        # (1) all equal
        case("(1) all equal", want_r="PASS", want_l=[E, E], want_rows=["PASS", "PASS"])
        # (2) - (5), (8): R PASS, UE 1 NOT COMPARED -> NE: the intentional differences
        _, locs, _, _ = case("(2) no statistics for ue[1]", values=std_values(BASE, override={1: {ER: None, TX: None}}),
                             want_r="PASS", want_l=[E, N], want_rows=["PASS", "NOT EVALUATED"])
        check(locs[1]["step"] == "2", "step 2")
        _, locs, _, _ = case("(3) harqTxAttemptsDl missing for ue[1]", values=std_values(BASE, override={1: {TX: None}}),
                             want_r="PASS", want_l=[E, N], want_rows=["PASS", "NOT EVALUATED"])
        check(steps(locs, 1) == {ER: "V-8", TX: "V-2"} and locs[1]["step"] == "7", f"(3) steps {steps(locs, 1)}")
        spec4 = {2049: BASE[2049], 2050: (["NACK"] * 4, [])}
        _, locs, _, _ = case("(4) no ACKed lifecycle for ue[1]", spec=spec4,
                             values=std_values(BASE, override={1: {ER: "1", TX: "4"}}),
                             want_r="PASS", want_l=[E, N], want_rows=["PASS", "NOT EVALUATED"])
        check(steps(locs, 1) == {ER: "V-8", TX: "V-4"}, f"(4) steps {steps(locs, 1)}")
        spec5 = {2049: BASE[2049]}
        _, locs, _, _ = case("(5) no feedback for ue[1]", spec=spec5, values=std_values(BASE),
                             want_r="PASS", want_l=[E, N], want_rows=["PASS", "NOT EVALUATED"])
        check(locs[1]["step"] == "4", "step 4")
        # (6) missing node mapping: injected map / a .sca without ue[1]'s macNodeId -> MAP-UE FAIL -> FAIL x 2
        r, locs, rows, mrow = case("(6a) .sca without ue[1] macNodeId", drop_par=(1,), cr=False, want_rows=["FAIL", "FAIL"])
        check(mrow["status"] == "FAIL" and r[2] == "PASS", f"(6a) MAP-UE {mrow['status']}, R {r[2]}")
        sc_ = PR.scalars(write_sca(d, NODES2, std_values(BASE)))
        rows6, _ = W.a28u_rows(2, {0: 2049}, sc_, {W.ue_module(0): 2049, W.ue_module(1): 2050}, mkres(BASE), {}, "FAIL", "PASS")
        check(ST(rows6) == ["FAIL", "FAIL"], f"(6b) injected incomplete map: {ST(rows6)}")
        # (7) / (12) non-finite Simu5G values: R FAIL, UE 1 DIFFERENT by V-7 (same outcome)
        for v in ("nan", "-nan", "inf", "-inf", "1e999", "NaN"):
            _, locs, _, _ = case(f"(7) {v} for ue[1]", values=std_values(BASE, override={1: {ER: v}}), pu4h="FAIL",
                                 want_r="FAIL", want_l=[E, D], want_rows=["FAIL", "FAIL"])
            check(steps(locs, 1)[ER] == "V-7", f"(7) {v}: {steps(locs, 1)}")
        # (8) unparsable: R PASS (the other statistic compared), UE 1 NE by V-6
        for v in ("abc", "0x10", "1,5", "--1"):
            _, locs, _, _ = case(f"(8) unparsable {v!r}", values=std_values(BASE, override={1: {ER: v}}),
                                 want_r="PASS", want_l=[E, N], want_rows=["PASS", "NOT EVALUATED"])
            check(steps(locs, 1)[ER] == "V-6", f"(8) {v}")
        # (9) group-censored ue[1]: R NE, UE 1 NOT COMPARED (step 3), UE 0 local EQUAL but row NE (PU-4h NE)
        _, locs, rows, _ = case("(9) censored ue[1]", censored=(2050,), pu4h="NOT EVALUATED",
                                want_r="NOT EVALUATED", want_l=[E, N], want_rows=["NOT EVALUATED", "NOT EVALUATED"])
        check(locs[1]["step"] == "3", "step 3")
        # (10) value mismatch on ue[1]: R FAIL, UE 1 DIFFERENT, UE 0 local EQUAL / row FAIL (PU-4h FAIL through NOT VALID)
        _, locs, rows, _ = case("(10) mismatch ue[1]", values=std_values(BASE, override={1: {ER: "0.3"}}), pu4h="FAIL",
                                want_r="FAIL", want_l=[E, D], want_rows=["FAIL", "FAIL"])
        check(rows[0]["local"] == E and "global" in rows[0]["detail"], f"(10) UE 0 row {rows[0]}")
        # (11) duplicate records for ue[1]: NOT COMPARED by V-1, whatever the last record says
        dup_line = lambda v: [f"scalar {W.ue_module(1)} {ER} {v}\n"]
        _, locs, _, _ = case("(11a) duplicate, equal values", extra=dup_line("0.25"), want_r="PASS", want_l=[E, N],
                             want_rows=["PASS", "NOT EVALUATED"])
        check(steps(locs, 1)[ER] == "V-1", f"(11a) {steps(locs, 1)}")
        _, locs, _, _ = case("(11b) duplicate, a wrong first record", values=std_values(BASE, override={1: {ER: "0.9"}}),
                             extra=dup_line("0.25"), want_r="PASS", want_l=[E, N])
        _, locs, _, _ = case("(11c) duplicate, a wrong last record", extra=dup_line("0.9"), pu4h="FAIL",
                             want_r="FAIL", want_l=[E, N], want_rows=["FAIL", "FAIL"])
        # tolerance boundary (V-8), both statistics, both sides: (1 - 1e-3) x tolerance equal, (1 + 1e-3) x different
        for stat, val in ((ER, 0.25), (TX, 4 / 3)):
            tol = TOL * max(1.0, abs(val))
            for sign in (1, -1):
                inside = repr(val + sign * tol * (1 - 1e-3))
                outside = repr(val + sign * tol * (1 + 1e-3))
                case(f"tolerance {stat} {sign:+d} inside", values=std_values(BASE, override={1: {stat: inside}}),
                     want_r="PASS", want_l=[E, E])
                case(f"tolerance {stat} {sign:+d} outside", values=std_values(BASE, override={1: {stat: outside}}),
                     pu4h="FAIL", want_r="FAIL", want_l=[E, D])
        big = {2049: BASE[2049], 2050: (["ACK"] * 3, [5, 5, 6])}          # tx 16/3 > 1: tolerance scales with |val|
        tv_big = 16 / 3
        case("tolerance scales: inside", spec=big,
             values=std_values(big, override={1: {TX: repr(tv_big * (1 + TOL * (1 - 1e-3)))}}), want_r="PASS", want_l=[E, E])
        case("tolerance scales: outside", spec=big, pu4h="FAIL",
             values=std_values(big, override={1: {TX: repr(tv_big * (1 + TOL * (1 + 1e-3)))}}), want_r="FAIL", want_l=[E, D])
        # (13) injected scalar types (not reachable in run: scalars() yields text): V-5, and the other step order
        counts = W.a28u_counts(mkres(BASE))
        smap = {W.ue_module(0): 2049, W.ue_module(1): 2050}
        for junk in (0.25, 1, True, None, ["0.25"], {"v": 1}, b"0.25"):
            sc = {W.ue_module(0): {ER: "0", TX: "1"}, W.ue_module(1): {ER: junk, TX: repr(4 / 3)}}
            loc = W.a28u_local(1, 2050, sc, smap, counts, set(), {})
            check(loc["local"] == N and loc["stats"][ER]["step"] == "V-5", f"(13) {junk!r}: {loc['local']} {loc['stats'][ER]}")
        # (14) malformed counts (V-3: DIFFERENT, never a pass)
        sc = {W.ue_module(1): {ER: "0.25", TX: "1"}}
        for c in ({"feedback": 3, "nack": 4, "ntx": [1]}, {"feedback": True, "nack": 0, "ntx": [1]},
                  {"feedback": -2, "nack": 0, "ntx": [1]}, {"feedback": 4, "nack": -1, "ntx": [1]},
                  {"feedback": 4.0, "nack": 1, "ntx": [1]}, {"feedback": 4, "nack": 1, "ntx": [0]},
                  {"feedback": 4, "nack": 1, "ntx": [True]}, {"feedback": 4, "nack": 1, "ntx": "1"},
                  {"feedback": 4, "nack": 1}, {"nack": 1, "ntx": [1]}, "4 feedbacks", [4, 1]):
            loc = W.a28u_local(1, 2050, sc, smap, {2050: c}, set(), {})
            check(loc["local"] == D and "V-3" in [v["step"] for v in loc["stats"].values()], f"(14) {c!r}: {loc}")
        # (15) a non-finite computed value (V-4): integers beyond the float range
        loc = W.a28u_local(1, 2050, {W.ue_module(1): {ER: "0", TX: "1"}}, smap,
                           {2050: {"feedback": 1, "nack": 0, "ntx": [10 ** 400]}}, set(), {})
        check(loc["local"] == D and loc["stats"][TX]["step"] == "V-4", f"(15) {loc}")
        # step 1: no scalars at all; R NE; both NE
        case("no H-ARQ scalars", values={}, want_r="NOT EVALUATED", want_l=[N, N], want_rows=["NOT EVALUATED", "NOT EVALUATED"])
        for sc_bad in (None, {}, [], "x"):
            check(W.a28u_local(0, 2049, sc_bad, smap, counts, set(), {})["step"] == "1", f"step 1 for {sc_bad!r}")
        check(W.a28u_local(0, 2049, {W.ue_module(0): {ER: "0"}}, {}, counts, set(), {})["step"] == "1", "step 1: empty module map")
        # missing measurements are never zero: a UE with no statistics stays NOT COMPARED even when its true values are 0
        zero = {2049: (["ACK"] * 5, [1] * 5), 2050: (["ACK"] * 5, [1] * 5)}
        case("zero-valued UE without statistics", spec=zero, values=std_values(zero, override={1: {ER: None, TX: None}}),
             want_r="PASS", want_l=[E, N], want_rows=["PASS", "NOT EVALUATED"])
        # row status table (design 4.5)
        Ld = {"local": D, "detail": "x"}
        Le = {"local": E, "detail": "x"}
        Ln = {"local": N, "detail": "x"}
        table = [(Le, "FAIL", "PASS", "FAIL"), (Le, "PASS", "FAIL", "FAIL"), (Ld, "PASS", "PASS", "FAIL"),
                 (Ln, "PASS", "PASS", "NOT EVALUATED"), (Le, "PASS", "NOT EVALUATED", "NOT EVALUATED"),
                 (Le, "PASS", "PASS", "PASS"), (Ln, "FAIL", "PASS", "FAIL"), (Ld, "PASS", "NOT EVALUATED", "FAIL"),
                 (Ln, "PASS", "NOT EVALUATED", "NOT EVALUATED")]
        for loc, ms, ps, want in table:
            r = W.a28u_row(1, loc, ms, ps)
            check(r["status"] == want and r["local"] == loc["local"], f"row status for {loc['local']}, MAP {ms}, PU-4h {ps}: {r}")
        # the CR checker itself detects incompatible pairs
        bad = [("PASS", [E, D]), ("FAIL", [E, E]), ("NOT EVALUATED", [E, E])]
        for r_st, ls in bad:
            fake = [{"local": x, "stats": {ER: {"outcome": "equal" if x == E else x, "step": "V-8"}}} for x in ls]
            check(W.cr_violations(r_st, fake, [2049, 2050], set()), f"CR checker accepted R {r_st} with L {ls}")
    finally:
        shutil.rmtree(d)


# ------------------------------------------------------------------- NC-scalar-ue1, NC-scalar-missing-ue1 ------
def genuine_like_run(d):
    """a corrected-generator N = 2 run with NACKs on UE 1 (synthetic, labelled), evaluated by the accepted A-2.1, and a
    .sca written from the GENERATOR TRUTH (independent of A-2.1's attribution)"""
    lines, node, truth = G.make(2, 60, lambda tti: [0, 1] if tti % 3 == 0 else [0], nack={(805, 1), (813, 1), (813, 2)}, tail=40)
    per_node = {}
    for x in truth:
        e = per_node.setdefault(x["node"], {"fb": 0, "nack": 0, "ntx": []})
        e["fb"] += 1
        e["nack"] += x["res"] == "NACK"
        if x["res"] == "ACK":
            e["ntx"].append(x["ntx"])
    vals = {k: {ER: repr(per_node[n]["nack"] / per_node[n]["fb"]), TX: repr(sum(per_node[n]["ntx"]) / len(per_node[n]["ntx"]))}
            for k, n in node.items()}
    check(any(per_node[n]["nack"] for n in node.values()), "the generated run has NACKs")
    return lines, node, vals


def run_genuine_like(d, vals, node, lines, name):
    sca = write_sca(d, node, vals, name=name)
    res, rows, per, cov, extra, window = A21.evaluate(lines, 16, 0, node, None, sca, None)
    r = {x[0]: x for x in rows}["A2-8"]
    raw = open(sca).read().splitlines(True)
    before = (fingerprint((res, rows)), hashlib.sha256(open(sca, "rb").read()).hexdigest())
    smap = A2.sca_nodes(sca)
    mrow = W.map_ue(2, dict(node), smap, W.evidence_nodes(res, per, extra["xa"]))
    pu4h = "FAIL" if A21.verdict(rows, "f1d-i")[1] == 1 else "PASS"     # stand-in for I-3: NOT VALID -> PU-4h FAIL
    rws, locs = W.a28u_rows(2, dict(node), PR.scalars(sca), smap, res, W.scalar_record_counts(raw), mrow["status"], pu4h)
    check(before == (fingerprint((res, rows)), hashlib.sha256(open(sca, "rb").read()).hexdigest()),
          "the wrapper modified the frozen evaluator results or the .sca")
    check(not W.cr_violations(r[2], locs, list(node.values()), A21.touched_nodes(res)), "CR on the genuine-like run")
    return r, mrow, rws, locs, pu4h


@named("NC-scalar-ue1")
def nc_scalar_ue1():
    d = tempfile.mkdtemp(prefix="e0vn21-nc1-")
    try:
        lines, node, vals = genuine_like_run(d)
        r, mrow, rws, locs, pu4h = run_genuine_like(d, vals, node, lines, "base.sca")
        check(mrow["status"] == "PASS" and r[2] == "PASS" and L(locs) == [W.EQUAL, W.EQUAL] and ST(rws) == ["PASS", "PASS"],
              f"baseline guard: MAP-UE {mrow['status']}, R {r[2]}, L {L(locs)}, rows {ST(rws)}")
        v = copy.deepcopy(vals)
        v[1][ER] = repr(float(v[1][ER]) + 1e-3)               # beyond the tolerance
        r, mrow, rws, locs, pu4h = run_genuine_like(d, v, node, lines, "perturbed.sca")
        check(r[2] == "FAIL" and pu4h == "FAIL", f"run-level A2-8 {r[2]}, A-2.1 NOT VALID -> PU-4h {pu4h}")
        check(L(locs) == [W.EQUAL, W.DIFFERENT] and ST(rws) == ["FAIL", "FAIL"], f"L {L(locs)}, rows {ST(rws)}")
        check("global" in rws[0]["detail"] and rws[0]["local"] == W.EQUAL, f"UE 0 fails by the global rule only: {rws[0]}")
    finally:
        shutil.rmtree(d)


@named("NC-scalar-missing-ue1")
def nc_scalar_missing_ue1():
    d = tempfile.mkdtemp(prefix="e0vn21-nc2-")
    try:
        lines, node, vals = genuine_like_run(d)
        v = copy.deepcopy(vals)
        del v[1]                                              # ue[1]'s two statistics removed; its macNodeId kept
        r, mrow, rws, locs, pu4h = run_genuine_like(d, v, node, lines, "missing.sca")
        check(mrow["status"] == "PASS", f"MAP-UE {mrow}")
        check(r[2] == "PASS", f"the frozen run-level A2-8 PASSes with ue[0] alone (frozen behaviour): {r[2]}")
        check(L(locs) == [W.EQUAL, W.NOT_COMPARED] and locs[1]["step"] == "2", f"L {L(locs)}")
        check(ST(rws) == ["PASS", "NOT EVALUATED"], f"A2-8u rows {ST(rws)}: the run-level PASS is never per-UE coverage")
    finally:
        shutil.rmtree(d)


# ================================================================================================ I-3 ============
import gzip  # noqa: E402
import m2s72_peru as P  # noqa: E402  (frozen; read-only: A-1 attribute_feedback, to show the A-1 ambiguity of a case)
import m2s72_peru_adapter as PA  # noqa: E402  (accepted; read-only: harq_events)
import m2s72_a21_realchain as RC  # noqa: E402  (accepted; read-only: load_fixture)
import test_m2s72_a2 as TA  # noqa: E402  (frozen test helpers: root(), grants_of())

MS = G.MS


def tms(line):
    return float(line.split("|")[0]) * 1000


def simu5g_root():
    r = TA.root()
    check(r is not None, "SIMU5G_ROOT must name the Simu5G 1.8.1 sources (A2-0s); tier-0 provides it")
    return r


def pipe(lines, node, nproc=16, t0=1000 * MS):
    """the I-3 composition on one synthetic run, as the wrapper will wire it (I-6 / I-7): the raw log is written, A-1's
    harq_events() and the token census read it, A-2.1 runs ONCE on m2s72_a21.load() of it; then MAP-UE, C-0, PU-4h and
    PU-4o. Every input of the library is checked unchanged afterwards."""
    d = tempfile.mkdtemp(prefix="e0vn21-i3-")
    try:
        p = os.path.join(d, "run.log.gz")
        with gzip.open(p, "wt") as fh:
            fh.writelines(lines)
        a1 = PA.harq_events(p)
        with gzip.open(p, "rt") as fh:
            census = W.token_census(fh.read().splitlines(True))
        res, rows, per, cov, extra, window = A21.evaluate(A21.load(p), nproc, t0, node, TA.grants_of(lines), None, simu5g_root())
    finally:
        shutil.rmtree(d)
    return compose(len(node), node, a1, census, res, rows, per, cov, extra)


def fingerprint(obj):
    """a digest of a (possibly cyclic) structure: the A-2.1 replay result links groups and units both ways, so deep
    equality would recurse forever; repr() marks a back-reference as {...} and still prints every value once"""
    return hashlib.sha256(repr(obj).encode()).hexdigest()


def compose(n, node, a1, census, res, rows, per, cov, extra):
    x7 = extra["xa"]
    snap = fingerprint((a1, census, res, rows, per, x7, node))
    m = W.map_ue(n, dict(node), None, W.evidence_nodes(res, per, x7))
    c0, info = W.c0_row(a1, res, census)
    ph, v = W.pu4h_row(m, c0, rows, res)
    po, locs = W.pu4o_rows(n, dict(node), per, x7, rows, m["status"], ph["status"])
    check(snap == fingerprint((a1, census, res, rows, per, x7, node)), "the wrapper modified the frozen results or its inputs")
    for r in [m, c0, ph] + po:
        check(W.validate_row(r) == [], f"row schema: {W.validate_row(r)}")
    st = {r[0]: r[2] for r in rows}
    return {"a1": a1, "census": census, "res": res, "rows": rows, "per": per, "cov": dict((k, v_) for k, v_, _ in cov),
            "x7": x7, "st": st, "map": m, "c0": c0, "c0info": info, "pu4h": ph, "v": v, "pu4o": po, "locs": locs,
            "touched": sorted(A21.touched_nodes(res)), "node": node, "n": n}


def S(r):
    return [x["status"] for x in r["pu4o"]]


def LO(r):
    return [x["local"] for x in r["locs"]]


def nack_run(n_ue, sched, who, attempt_idx=0, ttis=40, **kw):
    """a corrected-generator run (synthetic, labelled) in which the attempt_idx-th PDU of UE `who` is NACKed once"""
    _, _, t0 = G.make(n_ue, ttis, sched, tail=40, **kw)
    pid = [x["pid"] for x in t0 if x["node"] == 2049 + who][attempt_idx]
    lines, node, truth = G.make(n_ue, ttis, sched, nack={(pid, 1)}, tail=40, **kw)
    x = next(x for x in truth if x["res"] == "NACK")
    return lines, node, truth, x["t"] // MS


def truth_per_node(truth):
    out = {}
    for x in truth:
        d = out.setdefault(x["node"], {"pids": set(), "feedback": 0, "nack": 0, "ack": 0})
        d["pids"].add(x["pid"])
        d["feedback"] += 1
        d["nack"] += x["res"] == "NACK"
        d["ack"] += x["res"] == "ACK"
    return out


def check_counts_truth(r, truth):
    tp = truth_per_node(truth)
    for n, t in tp.items():
        o = r["per"][n]
        got = (o["inserts"], o["feedback"], o["nack"], o["ack"])
        check(got == (len(t["pids"]), t["feedback"], t["nack"], t["ack"]), f"node {n}: A-2.1 {got} vs truth "
              f"{(len(t['pids']), t['feedback'], t['nack'], t['ack'])}")


def all_pass(r, n):
    check(r["map"]["status"] == "PASS" and r["c0"]["status"] == "PASS", f"MAP-UE {r['map']} / C-0 {r['c0']['detail'][:300]}")
    check(r["pu4h"]["status"] == "PASS", f"PU-4h {r['pu4h']['detail'][:400]}")
    check(S(r) == ["PASS"] * n and LO(r) == [W.EQUAL] * n, f"PU-4o {S(r)} {LO(r)}")


# --------------------------------------------------------------------------------------------------- T-c0 -------
@named("T-c0")
def t_c0():
    check(W.a1_gnb_module() == W.GNB_MODULE == A21.GNB == "M2S72Bridge.gnb1.cellularNic.mac", "T-c0-module")
    for name, (lines, node, _) in {
            "N=2 same TTI": G.make(2, 40, lambda tti: [0, 1], tail=40),
            "N=2 NACK": nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)[:3],
            "N=4": G.make(4, 30, lambda tti: [0, 2] + ([1] if tti % 4 == 1 else []) + ([3] if tti % 5 == 3 else []), tail=40)}.items():
        r = pipe(lines, node)
        i = r["c0info"]
        check(r["c0"]["status"] == "PASS" and not i["problems"], f"{name}: C-0 {r['c0']['detail'][:300]}")
        check(i["sha256_a1"] == i["sha256_a21"] and i["lengths"][0] == i["lengths"][1] > 0, f"{name}: {i}")
        check(i["counts"]["census"] == i["counts"]["a1"] == i["counts"]["a21"], f"{name}: census {i['counts']}")
        check(i["counts"]["a21"]["insert"] == r["res"]["counts"]["insert lines"], f"{name}: insert lines")
    # the genuine F3 fixture (public, pinned): A-1 and A-2.1 parse the same 99 inserts and 96 feedback lines
    fx = RC.load_fixture(os.path.join(HERE, "fixtures"))
    res, rows, per, cov, extra, window = A21.evaluate(fx["lines21"], fx["nproc"], 0, fx["node"], fx["grants"], None, simu5g_root())
    with gzip.open(fx["path"], "rt", errors="replace") as fh:
        census = W.token_census(fh.read().splitlines(True))
    r = compose(2, fx["node"], PA.harq_events(fx["path"]), census, res, rows, per, cov, extra)
    check(census == {"insert": 99, "feedback": 96}, f"F3 census {census}")
    check(r["c0"]["status"] == "PASS" and r["c0info"]["lengths"] == [195, 195], f"F3 C-0 {r['c0']['detail'][:300]}")
    check(r["map"]["status"] == "PASS" and r["pu4h"]["status"] == "PASS" and S(r) == ["PASS", "PASS"],
          f"F3: MAP-UE {r['map']['status']}, PU-4h {r['pu4h']['detail'][:300]}, PU-4o {S(r)}")
    # IG-1: a missing or malformed extraction is FAIL, never an empty evidence set
    lines, node, _ = G.make(2, 20, lambda tti: [0, 1], tail=40)
    base = pipe(lines, node)
    a1, res, cen = base["a1"], base["res"], base["census"]
    for what, args in {"A-1 events None": (None, res, cen), "A-1 events a dict": ({}, res, cen),
                       "A-2.1 result None": (a1, None, cen), "A-2.1 without pdus": (a1, {"fb": [], "counts": {}}, cen),
                       "census None": (a1, res, None), "census malformed": (a1, res, {"insert": "80"}),
                       "census without feedback": (a1, res, {"insert": cen["insert"]}),
                       "both sequences empty": ([], {"pdus": {}, "fb": [], "counts": {"insert lines": 0}}, {"insert": 0, "feedback": 0}),
                       "A-1 event of a wrong shape": (a1[:1] + [("ins", 1, 2)] + a1[1:], res, cen),
                       "A-1 event with a bool": ([("ins", True) + tuple(a1[0][2:])] + a1[1:], res, cen),
                       "A-1 events a string": ("ins", res, cen)}.items():
        row, info = W.c0_row(*args)
        check(row["status"] == "FAIL", f"IG-1 {what}: C-0 {row['status']}")


# ------------------------------------------------------------------------------------------------ NC-c0-* -------
def _c0_base():
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    r = pipe(lines, node)
    check(r["c0"]["status"] == "PASS", "NC-c0 baseline guard: C-0 PASS before the mutation")
    return lines, node, r


@named("NC-c0")
def nc_c0():
    lines, node, base = _c0_base()
    a1, res, cen = base["a1"], base["res"], base["census"]

    def fails(row, what, token=None):
        check(row[0]["status"] == "FAIL", f"{what}: C-0 {row[0]['status']}")
        check(token is None or token in row[0]["detail"], f"{what}: detail lacks {token!r}: {row[0]['detail'][:300]}")
        return row
    # NC-c0-same-count: two A-1 feedback events exchange their process ids (counts and kinds unchanged)
    fbi = [i for i, e in enumerate(a1) if e[0] == "fb"]
    i, j = next((i, j) for i in fbi for j in fbi if a1[i][2] != a1[j][2])
    m = list(a1)
    m[i], m[j] = m[i][:2] + (a1[j][2],) + m[i][3:], m[j][:2] + (a1[i][2],) + m[j][3:]
    fails(W.c0_row(m, res, cen), "NC-c0-same-count", "parser divergence")
    # NC-c0-reorder: two adjacent events of different UEs swapped
    k = next(k for k in range(len(a1) - 1) if a1[k][0] == a1[k + 1][0] == "ins" and a1[k][2] != a1[k + 1][2])
    m = list(a1)
    m[k], m[k + 1] = m[k + 1], m[k]
    fails(W.c0_row(m, res, cen), "NC-c0-reorder", "parser divergence")
    # NC-c0-node: one A-1 insert's node changed
    k = next(k for k, e in enumerate(a1) if e[0] == "ins")
    m = list(a1)
    m[k] = m[k][:2] + (m[k][2] + 1,) + m[k][3:]
    fails(W.c0_row(m, res, cen), "NC-c0-node", "parser divergence")
    # NC-c0-recon-drop: an entry removed from a copy of res["pdus"], and separately from a copy of res["fb"]
    fp = fingerprint(res)
    r2 = copy.deepcopy(res)
    del r2["pdus"][next(iter(r2["pdus"]))]
    fails(W.c0_row(a1, r2, cen), "NC-c0-recon-drop (pdus)", "R-0a")
    r2 = copy.deepcopy(res)
    del r2["fb"][3]
    fails(W.c0_row(a1, r2, cen), "NC-c0-recon-drop (fb)", "R-0c")
    check(fingerprint(res) == fp, "the original replay result is unchanged")
    # NC-c0-recon-dup: a duplicated feedback entry; and one unit's ins_gi set to another's
    r2 = copy.deepcopy(res)
    r2["fb"].insert(5, copy.deepcopy(r2["fb"][4]))
    fails(W.c0_row(a1, r2, cen), "NC-c0-recon-dup (fb)", "R-0c")
    r2 = copy.deepcopy(res)
    us = list(r2["pdus"].values())
    us[1]["ins_gi"] = us[0]["ins_gi"]
    fails(W.c0_row(a1, r2, cen), "NC-c0-recon-dup (ins_gi)", "R-0b")
    # R-0d: a malformed reconstructed unit
    r2 = copy.deepcopy(res)
    next(iter(r2["pdus"].values()))["node"] = None
    fails(W.c0_row(a1, r2, cen), "R-0d", "R-0d")
    # NC-c0-dup-pid (log mutation): a later insert line reuses an earlier PDU id -> A-2.1 loses a unit in pdus
    ins = [i for i, y in enumerate(lines) if W.TOKEN_INS in y and W.GNB_MODULE in y]
    first_pid = re.search(r"\(id (\d+) \)", lines[ins[0]]).group(1)
    k = next(i for i in ins[5:] if "for node with id 2050" in lines[i])
    m = list(lines)
    m[k] = re.sub(r"\(id \d+ \)", f"(id {first_pid} )", m[k])
    r = pipe(m, node)
    fails((r["c0"],), "NC-c0-dup-pid", "R-0a")
    check(r["c0info"]["lengths"][0] == r["c0info"]["lengths"][1] + 1, f"NC-c0-dup-pid: lengths {r['c0info']['lengths']}")
    check(r["st"]["A2-2"] == "FAIL" and r["pu4h"]["status"] == "FAIL", f"NC-c0-dup-pid: A2-2 {r['st']['A2-2']}, PU-4h {r['pu4h']['status']}")
    # NC-c0-malformed-ins / -fb: a corrupted token line; A-1 and A-2.1 still agree with each other; only R-0e sees it
    for what, sel, sub in (("NC-c0-malformed-ins", W.TOKEN_INS, (r"\(id (\d)(\d*) \)", r"(id \1x\2 )")),
                           ("NC-c0-malformed-fb", W.TOKEN_FB, (r"result is ACK", "result is ACX")),
                           ("NC-c0-malformed-timestamp", W.TOKEN_INS, (r"^(\d)", r"x\1"))):
        k = next(i for i, y in enumerate(lines) if sel in y and W.GNB_MODULE in y and tms(y) > 1010 and
                 (sel != W.TOKEN_FB or "result is ACK" in y))
        m = list(lines)
        m[k] = re.sub(sub[0], sub[1], m[k], count=1)
        check(m[k] != lines[k], f"{what}: mutation applied")
        r = pipe(m, node)
        fails((r["c0"],), what, "R-0e")
        a1s, _ = W.c0_a1_sequence(r["a1"])
        a2s, _ = W.c0_a21_sequence(r["res"])
        check(a1s == a2s, f"{what}: A-1 and A-2.1 agree with each other (identical regexes): only the census detects it")
        check(r["pu4h"]["status"] == "FAIL", f"{what}: PU-4h {r['pu4h']['status']}")
    # a token in a UE-module line is not counted (the census is restricted to the gNB MAC)
    check(W.token_census(["1.0|M2S72Bridge.ue[0].cellularNic.nrMac|H-ARQ TX: feedback received x\n",
                          "1.0|M2S72Bridge.gnb1.cellularNic.mac|H-ARQ TX: new pdu (id ?? )\n", "garbage\n", None, 7]) ==
          {"insert": 1, "feedback": 0}, "census scope")


# ------------------------------------------------------------------------------------------- N = 2, N = 4 -------
@named("T-n2-same-tti")
def t_n2_same_tti():
    lines, node, truth = G.make(2, 40, lambda tti: [0, 1], tail=40)
    r = pipe(lines, node)
    _, summ = P.attribute_feedback(r["a1"], 16)
    check(summ["ambiguous"] > 0 and summ["reinsert"] > 0, f"A-1 must be ambiguous on same-TTI feedback: {summ}")
    check(r["v"] == {"verdict_f1d_i": "A-2.1 VALID", "verdict_full": "A-2.1 VALID"}, f"verdicts {r['v']}")
    check(all(r["st"][k] == W.NX for k in ("A2-4a", "A2-4b", "A2-4c")), "A2-4a/b/c NOT EXERCISED")
    pairs = sum(1 for c in Counter(x["t"] for x in truth).values() if c == 2)
    check(r["cov"]["exchangeable ACK groups (2 candidates)"] == pairs > 0, f"groups {r['cov']} vs same-TTI pairs {pairs}")
    all_pass(r, 2)
    check_counts_truth(r, truth)
    check(r["v"]["verdict_f1d_i"] == A21.verdict(r["rows"], "f1d-i")[0] and r["v"]["verdict_full"] == A21.verdict(r["rows"], "full")[0],
          "both contract verdicts from the same rows")


@named("T-n2-a2v1-like")
def t_n2_a2v1_like():
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    check(all(x["node"] == 2050 for x in truth if x["res"] == "NACK"), "NACKs on UE 1 only")
    r = pipe(lines, node)
    check(r["st"]["A2-4a"] == "PASS" and r["st"]["A2-4c"] == W.NE, f"A2-4a {r['st']['A2-4a']}, A2-4c {r['st']['A2-4c']}")
    check(r["v"] == {"verdict_f1d_i": "A-2.1 VALID", "verdict_full": "A-2.1 INCOMPLETE"}, f"verdicts {r['v']}")
    all_pass(r, 2)
    check("full contract (reported" in r["pu4h"]["detail"] and "A-2.1 INCOMPLETE" in r["pu4h"]["detail"], "full verdict recorded")
    check_counts_truth(r, truth)


@named("T-n4-independent")
def t_n4_independent():
    s4 = lambda tti: [0, 2] + ([1] if tti % 4 == 1 else []) + ([3] if tti % 5 == 3 else [])
    _, _, t0 = G.make(4, 40, s4, tail=40)
    pp = [x["pid"] for x in t0 if x["node"] == 2050][:2] + [x["pid"] for x in t0 if x["node"] == 2052][:2]
    lines, node, truth = G.make(4, 40, s4, nack={(p, 1) for p in pp}, tail=40)
    check({x["node"] for x in truth if x["res"] == "NACK"} == {2050, 2052}, "NACK chains on UEs 1 and 3")
    r = pipe(lines, node)
    all_pass(r, 4)
    check_counts_truth(r, truth)


@named("T-n4-overlap-nack")
def t_n4_overlap_nack():
    s4 = lambda tti: [0, 2] + ([1] if tti % 6 == 1 else []) + ([3] if tti % 7 == 2 else [])
    lines, node, truth, T = nack_run(4, s4, 2, 3, ttis=30)
    r = pipe(lines, node)
    check(r["cov"]["mixed ACK / NACK groups"] >= 1 and r["cov"]["NACK resolved by retransmission evidence (deferred)"] >= 1,
          f"a mixed group resolved by retransmission evidence: {r['cov']}")
    all_pass(r, 4)
    check_counts_truth(r, truth)


# ------------------------------------------------------------------------------------------ T-censor-* ----------
def cut_at(lines, T):
    return [y for y in lines if tms(y) < T + 1 - 1e-9]


def loops_only_after(lines, T):
    return [y for y in lines if tms(y) < T + 1 - 1e-9 or "ENB MAIN LOOP" in y]


@named("T-censor-awaiting-feedback")
def t_censor_awaiting_feedback():
    lines, node, truth = G.make(2, 40, lambda tti: [0, 1], tail=1)
    r = pipe(lines, node)
    check(r["res"]["end_states"].get("censored: awaiting feedback", 0) > 0 and r["touched"] == [], f"{r['res']['end_states']}")
    check(r["st"]["A2-7"] == "PASS", "A2-7 unaffected")
    all_pass(r, 2)


@named("T-censor-structural-unit")
def t_censor_structural_unit():
    s = lambda tti: ([0] if tti - 1000 < 3 else []) + ([1] if tti - 1000 == 10 else [])
    lines, node, truth, T = nack_run(2, s, 1)
    r = pipe(cut_at(lines, T), node)
    check(r["res"]["end_states"] == {"censored: awaiting retransmission": 1} and r["touched"] == [], f"{r['res']['end_states']}")
    all_pass(r, 2)


@named("T-censor-group")
def t_censor_group():
    s = lambda tti: ([0, 1] if tti - 1000 == 10 else []) + ([2] if tti - 1000 == 4 else [])
    lines, node, truth, T = nack_run(3, s, 1)
    r = pipe(cut_at(lines, T), node)
    check(r["res"]["end_states"] == {"censored: awaiting resolution": 2} and r["touched"] == [2049, 2050], f"{r['res']['end_states']} {r['touched']}")
    check(r["st"]["A2-7"] == W.NE and r["v"]["verdict_f1d_i"] == "A-2.1 INCOMPLETE", f"A2-7 {r['st']['A2-7']}, {r['v']}")
    check(r["pu4h"]["status"] == W.NE and "touched nodes [2049, 2050]" in r["pu4h"]["detail"], f"PU-4h {r['pu4h']['detail'][:300]}")
    check(LO(r) == [W.NOT_COMPARED, W.NOT_COMPARED, W.EQUAL] and S(r) == [W.NE] * 3, f"PU-4o {LO(r)} {S(r)}")
    check([x["step"] for x in r["locs"]] == ["4", "4", "6"] and "global" in r["pu4o"][2]["detail"], "touched: step 4; UE 2: global NE")


@named("T-censor-pending-unresolved")
def t_censor_pending_unresolved():
    lines, node, truth, T = nack_run(2, lambda tti: [0, 1] if tti - 1000 == 10 else [], 1)
    r = pipe(loops_only_after(lines, T), node)
    check(r["res"]["end_states"] == {"unresolved: pending group at the end": 2} and r["touched"] == [2049, 2050], f"{r['res']['end_states']}")
    check(r["st"]["A2-7"] == W.NE and r["st"]["A2-9"] == W.NE and r["pu4h"]["status"] == W.NE, f"{r['st']} {r['pu4h']['status']}")
    check(S(r) == [W.NE, W.NE] and LO(r) == [W.NOT_COMPARED] * 2, f"PU-4o {S(r)} {LO(r)}")


@named("T-unresolved")
def t_unresolved():
    s = lambda tti: ([0] if tti - 1000 < 3 else []) + ([1] if tti - 1000 == 10 else [])
    lines, node, truth, T = nack_run(2, s, 1)
    r = pipe(loops_only_after(lines, T), node)
    check(r["res"]["end_states"] == {"unresolved: retransmission not observed": 1} and r["touched"] == [], f"{r['res']['end_states']}")
    check(r["st"]["A2-9"] == W.NE and r["st"]["A2-7"] == "PASS" and r["pu4h"]["status"] == W.NE, f"{r['st']} {r['pu4h']['status']}")
    check(LO(r) == [W.EQUAL, W.EQUAL] and S(r) == [W.NE, W.NE], f"PU-4o: local EQUAL, row NE (global): {LO(r)} {S(r)}")


@named("NC-no-ue-lines")
def nc_no_ue_lines():
    lines, node, truth = G.make(2, 40, lambda tti: [0, 1], tail=40, ue_log=False)
    r = pipe(lines, node)
    check(r["x7"] is None and r["st"]["A2-7"] == W.NE and r["pu4h"]["status"] == W.NE, f"A2-7 {r['st']['A2-7']}, PU-4h {r['pu4h']['status']}")
    check(S(r) == [W.NE, W.NE] and [x["step"] for x in r["locs"]] == ["1", "1"], f"PU-4o {S(r)}")


# ------------------------------------------------------------------------------------------ NC-swap, NC-occ-* ----
def _occ_base():
    s = lambda tti: [0] + ([1] if tti % 3 == 0 else [])
    lines, node, truth, T = nack_run(2, s, 1, 1)
    r = pipe(lines, node)
    all_pass(r, 2)                                     # baseline guard
    return lines, node, r


@named("NC-swap")
def nc_swap():
    lines, node, base = _occ_base()
    k = next(i for i, y in enumerate(lines) if "for node with id 2049" in y and tms(y) > 1012)
    m = list(lines)
    m[k] = m[k].replace("for node with id 2049", "for node with id 2050")
    r = pipe(m, node)
    check(r["st"]["A2-7"] == "FAIL" and r["pu4h"]["status"] == "FAIL", f"A2-7 {r['st']['A2-7']}, PU-4h {r['pu4h']['status']}")
    check(S(r) == ["FAIL", "FAIL"] and all("global" in x["detail"] for x in r["pu4o"]), f"PU-4o {S(r)}")


@named("NC-occ")
def nc_occ():
    lines, node, base = _occ_base()
    # NC-occ-one-ue: one of UE 0's insert lines removed, its feedback kept
    k = next(i for i, y in enumerate(lines) if "for node with id 2049" in y and tms(y) > 1012)
    m = list(lines)
    del m[k]
    r = pipe(m, node)
    check(r["v"]["verdict_f1d_i"] == "A-2.1 NOT VALID" and r["pu4h"]["status"] == "FAIL", f"{r['v']} PU-4h {r['pu4h']['status']}")
    check(S(r) == ["FAIL", "FAIL"], f"PU-4o {S(r)}")
    check("global" in r["pu4o"][1]["detail"] and r["pu4o"][1]["local"] in W.LOCAL_OUTCOMES,
          f"UE 1 FAILs by the global rule, its local outcome reported: {r['pu4o'][1]}")
    # NC-occ-entry-missing: occupancy_equal without UE 1's entry (UE 1 not skipped)
    x7 = copy.deepcopy(base["x7"])
    del x7["occupancy_equal"][2050]
    rows, locs = W.pu4o_rows(2, dict(node), base["per"], x7, base["rows"], "PASS", "PASS")
    check([x["local"] for x in locs] == [W.EQUAL, W.DIFFERENT] and locs[1]["step"] == "5" and rows[1]["status"] == "FAIL",
          f"NC-occ-entry-missing: {locs} {rows[1]['status']}")
    # NC-occ-invalid: an invalid A-2.1 occupancy with occupancy_equal True
    per = copy.deepcopy(base["per"])
    per[2050]["occupancy"] = {"error": "negative occupancy: a feedback before its insert"}
    rows, locs = W.pu4o_rows(2, dict(node), per, base["x7"], base["rows"], "PASS", "PASS")
    check(base["x7"]["occupancy_equal"][2050] is True and locs[1]["step"] == "3" and rows[1]["status"] == "FAIL",
          f"NC-occ-invalid: {locs[1]} {rows[1]['status']}")
    # non-boolean / false entries, a malformed reference, a UE without PDUs, skipped
    for val, step, local in ((False, "7", W.DIFFERENT), (1, "7", W.DIFFERENT), ("True", "7", W.DIFFERENT), (None, "7", W.DIFFERENT)):
        x7 = copy.deepcopy(base["x7"])
        x7["occupancy_equal"][2050] = val
        loc = W.pu4o_local(1, 2050, base["per"], x7)
        check((loc["local"], loc["step"]) == (local, step), f"occupancy_equal {val!r}: {loc}")
    for x7 in ({}, [], "x", {"occupancy_equal": [], "skipped": []}, {"occupancy_equal": {2050: True}}):
        loc = W.pu4o_local(1, 2050, base["per"], x7)
        check(loc["local"] == W.DIFFERENT and loc["step"] == "1", f"malformed reference {x7!r}: {loc}")
    for o in (None, {}, [], "x", {"error": "e"}):
        per = copy.deepcopy(base["per"])
        per[2050]["occupancy"] = o
        check(W.pu4o_local(1, 2050, per, base["x7"])["step"] == "3", f"invalid occupancy {o!r}")
    check(W.pu4o_local(1, 2051, base["per"], base["x7"])["step"] == "2", "no PDU for the UE")
    x7 = copy.deepcopy(base["x7"])
    x7["skipped"] = [2050]
    check(W.pu4o_local(1, 2050, base["per"], x7)["local"] == W.NOT_COMPARED, "skipped")
    # the row status table (design 4.6)
    E, D, N = ({"local": W.EQUAL, "detail": "x"}, {"local": W.DIFFERENT, "detail": "x"}, {"local": W.NOT_COMPARED, "detail": "x"})
    for loc, ms, ps, a27, want in ((E, "FAIL", "PASS", "PASS", "FAIL"), (E, "PASS", "FAIL", "PASS", "FAIL"), (D, "PASS", "PASS", "PASS", "FAIL"),
                                   (N, "PASS", "PASS", "PASS", W.NE), (E, "PASS", "PASS", W.NE, W.NE), (E, "PASS", W.NE, "PASS", W.NE),
                                   (E, "PASS", "PASS", "PASS", "PASS"), (N, "PASS", "FAIL", "PASS", "FAIL"), (E, "PASS", "PASS", None, W.NE)):
        r = W.pu4o_row(1, loc, ms, ps, a27)
        check(r["status"] == want and r["local"] == loc["local"], f"PU-4o row for {loc['local']}, MAP {ms}, PU-4h {ps}, A2-7 {a27}: {r['status']}")


@named("T-pu4h")
def t_pu4h():
    """the PU-4h precedence (design 4.3) on the accepted verdict() of synthetic row sets"""
    ok = {"id": "MAP-UE", "subject": "run", "status": "PASS", "detail": ""}
    c0 = {"id": "C-0", "subject": "run", "status": "PASS", "detail": ""}
    bad = dict(ok, status="FAIL")
    valid = [(k, "run", "PASS", "") for k in A21.REQUIRED["full"]] + [("A2-8", "run", "PASS", "")]
    inc = [(k, "run", W.NE if k == "A2-7" else "PASS", "") for k in A21.REQUIRED["full"]]
    nv = [(k, "run", "FAIL" if k == "A2-8" else "PASS", "") for k in A21.REQUIRED["full"]] + [("A2-8", "run", "FAIL", "")]
    a4c = [(k, "run", "FAIL" if k == "A2-4c" else "PASS", "") for k in A21.REQUIRED["full"]]
    cases = [(ok, c0, valid, "PASS"), (bad, c0, valid, "FAIL"), (ok, dict(c0, status="FAIL"), valid, "FAIL"),
             (ok, c0, nv, "FAIL"), (ok, c0, a4c, "FAIL"), (ok, c0, inc, W.NE), (bad, c0, inc, "FAIL"),
             (ok, dict(c0, status=W.NE), valid, "FAIL")]
    for m, c, rows, want in cases:
        r, v = W.pu4h_row(m, c, rows)
        check(r["status"] == want, f"PU-4h MAP {m['status']} C-0 {c['status']} {v['verdict_f1d_i']}: {r['status']} (want {want})")
        check(v == {"verdict_f1d_i": A21.verdict(rows, "f1d-i")[0], "verdict_full": A21.verdict(rows, "full")[0]}, "verdicts")
    r, _ = W.pu4h_row(ok, c0, nv)
    check("A2-8" in r["detail"], "the failing A2 rows are named")


# ================================================================================================ I-4 ============
def a1_of(r):
    """A-1 on the run's events, as the unchanged s5n path runs it (frozen attribute_feedback), with its trace; and the
    genuine frozen PU-4 row for that summary (m2s72_peru.structural_rows)"""
    trace = []
    _, summ = P.attribute_feedback(r["a1"], 16, trace=trace)
    pu4 = next(x for x in P.structural_rows([], [], summ, None) if x[0] == "PU-4")
    return summ, trace, pu4


def gate_rows(r):
    """every wrapper gate row of a composed run (I-2 / I-3 functions), as comparable text"""
    m, c0, ph, po = r["map"], r["c0"], r["pu4h"], r["pu4o"]
    return json.dumps([m, c0, ph] + po, sort_keys=True, default=str)


# ------------------------------------------------------------------------------------------------- T-agree ------
@named("T-agree")
def t_agree():
    cases = {}
    # (a) complete agreement: N = 1 (A-1 exact by construction): every line A-1a / A-1b and equal to A-2.1's owner
    lines, node, truth = G.make(1, 40, lambda tti: [0], tail=40)
    cases["N=1"] = r = pipe(lines, node)
    summ, trace, pu4 = a1_of(r)
    a = W.agreement(r["a1"], trace, r["res"], r["c0"]["status"])
    check(pu4[2] == "PASS" and r["pu4h"]["status"] == "PASS", f"N=1: A-1 PU-4 {pu4[2]}, PU-4h {r['pu4h']['status']}")
    check(a["computed"] and a["disagree"] == 0 and a["agree"] == len(truth) == summ["a1a"] + summ["a1b"]
          and a["a1_unattributed_by_a21_class"] == {}, f"N=1 agreement {a}")
    # (b) A-1 ambiguous, A-2.1 independently valid: no agreement inferred for the ambiguous lines
    lines, node, truth = G.make(2, 40, lambda tti: [0, 1], tail=40)
    cases["same-TTI"] = r = pipe(lines, node)
    summ, trace, pu4 = a1_of(r)
    a = W.agreement(r["a1"], trace, r["res"], r["c0"]["status"])
    check(pu4[2] == "FAIL" and r["pu4h"]["status"] == "PASS", f"same-TTI: A-1 PU-4 {pu4[2]}, PU-4h {r['pu4h']['status']}")
    check(a["computed"] and a["agree"] == summ["a1a"] + summ["a1b"] and a["disagree"] == 0, f"same-TTI {a}")
    check(sum(a["a1_unattributed_by_a21_class"].values()) == summ["ambiguous"] + summ["orphan"] > 0 and
          set(a["a1_unattributed_by_a21_class"]) == {"ambiguous -> exchangeable"}, f"unattributed {a['a1_unattributed_by_a21_class']}")
    # (c) a genuine disagreement: under NACKs A-1 closes a unit at its first feedback (L-2) and gives a later line of
    # UE 1 to UE 0; A-2.1's owner is confirmed by the independent UE-side reference (A2-7 PASS, PU-4h PASS)
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    cases["NACK"] = r = pipe(lines, node)
    summ, trace, pu4 = a1_of(r)
    a = W.agreement(r["a1"], trace, r["res"], r["c0"]["status"])
    check(r["st"]["A2-7"] == "PASS" and r["pu4h"]["status"] == "PASS", f"NACK: A2-7 {r['st']['A2-7']}, PU-4h {r['pu4h']['status']}")
    check(a["computed"] and a["disagree"] > 0 and a["agree"] + a["disagree"] == summ["a1a"] + summ["a1b"], f"NACK {a}")
    check(sum(a["disagree_by_a21_class"].values()) == a["disagree"] and a["disagreements"], "disagreements by class, with examples")
    truth_owner = {}
    for x in truth:
        truth_owner.setdefault(x["t"], []).append(x["node"])
    for ex in a["disagreements"]:
        check(ex["a21"]["owner"] in truth_owner[ex["t_ps"]] and ex["a1"]["node"] != ex["a21"]["owner"],
              f"the A-2.1 owner is the generator truth, A-1's node is not: {ex}")
    check(sum(a["a1_unattributed_by_a21_class"].values()) == summ["ambiguous"] + summ["orphan"], "unattributed lines all counted")
    # (d) never inferred without aligned indices, or from a malformed trace
    r = cases["NACK"]
    summ, trace, _ = a1_of(r)
    for c0s in ("FAIL", "NOT EVALUATED", None):
        check(W.agreement(r["a1"], trace, r["res"], c0s)["computed"] is False, f"computed with C-0 {c0s}")
    for bad in (None, trace[:-1], trace + [trace[0]], [("x",)] + trace[1:], "trace"):
        check(W.agreement(r["a1"], bad, r["res"], "PASS")["computed"] is False, f"computed from a malformed trace {str(bad)[:40]}")
    # (e) the diagnostic is non-gating: the gate rows are identical whatever the diagnostic says, no gate function
    # takes it, and a composed digest's consistency does not depend on its content
    import inspect
    for fn in (W.map_ue, W.c0_row, W.pu4h_row, W.pu4o_rows, W.pu4o_row, W.a28u_rows, W.a28u_row):
        check(not any("agree" in p_ or "diagnos" in p_ for p_ in inspect.signature(fn).parameters), f"{fn.__name__} reads the diagnostic")
    for name, r in cases.items():
        before = gate_rows(r)
        summ, trace, _ = a1_of(r)
        snap = fingerprint((r["a1"], r["res"], r["rows"], trace))
        a = W.agreement(r["a1"], trace, r["res"], r["c0"]["status"])
        a["disagree"], a["agree"] = 10 ** 6, -1
        r2 = compose(r["n"], r["node"], r["a1"], r["census"], r["res"], r["rows"], r["per"],
                     [(k, v, "") for k, v in r["cov"].items()], {"xa": r["x7"]})
        check(gate_rows(r2) == before, f"{name}: gate rows changed after the diagnostic")
        check(fingerprint((r["a1"], r["res"], r["rows"], trace)) == snap, f"{name}: the diagnostic modified its inputs")
        check(not {"status", "verdict", "gate"} & set(a), f"{name}: the diagnostic carries a status: {sorted(a)}")
    for diag in ({}, {"agreement": {"disagree": 999}}, {"agreement": {"computed": False}}):
        for base in (good_digest, fail_digest, incomplete_digest, held_digest):
            x = base()
            want = W.validate_digest(x)
            x["diagnostics"] = diag
            check(W.validate_digest(x) == want, f"digest consistency depends on the diagnostic {diag}")


# ------------------------------------------------------------------------------------------ NC-pu4-relabel ------
@named("NC-pu4-relabel")
def nc_pu4_relabel():
    summaries = {"PASS": {"a1a": 11697, "a1b": 0, "ambiguous": 0, "orphan": 0, "reinsert": 0, "d_star_ps": 5000000000},
                 "FAIL": {"a1a": 9718, "a1b": 2476, "ambiguous": 768, "orphan": 0, "reinsert": 768, "d_star_ps": 5000000000},
                 "NOT EVALUATED": None}
    for want, summ in summaries.items():
        s5n_rows = P.structural_rows([], [], summ, None) + [("Q8-v", "run", "PASS", "x"), ("MG-1", "run", "FAIL", "y")]
        orig = next(x for x in s5n_rows if x[0] == "PU-4")
        check(orig[2] == want, f"frozen PU-4 status {orig[2]}")
        snap = copy.deepcopy(s5n_rows)
        pu4 = W.extract_pu4(s5n_rows)
        rep = W.pu4_report_row(pu4)
        hist = W.historical_a1(pu4, summ, {0: {"feedback": 3}})
        check(s5n_rows == snap, "extract / report modified the s5n rows")
        # byte-equal status and detail, everywhere the row appears
        check(tuple(pu4) == tuple(orig) and (rep["status"], rep["detail"]) == (orig[2], orig[3]) and
              tuple(hist["pu4_row"]) == tuple(orig), f"{want}: not verbatim")
        check(rep["label"] == W.HISTORICAL_PU4_LABEL and "not a gate" in rep["label"] and rep["gating"] is False, "label")
        check(hist["harq_attribution"] == summ and hist["label"] == W.HISTORICAL_A1_LABEL, "the A-1 summary verbatim")
        out = json.loads(json.dumps({"report": rep, "historical": hist}))
        check(out["report"]["status"] == orig[2] and out["historical"]["pu4_row"] == list(orig), "JSON round trip")
        if want == "FAIL":
            for o in (rep, hist):
                text = json.dumps(o)
                check("superseded" not in text.lower() and '"PASS"' not in text and '"NOT APPLICABLE"' not in text,
                      f"a PU-4 FAIL relabelled in {text[:200]}")
    # a digest carrying the historical FAIL stays valid with a PASS verdict: PU-4 never gates
    d = good_digest()
    check(d["historical"]["a1"]["pu4_row"][2] == "FAIL" and d["correctness"]["verdict"]["status"] == "PASS"
          and W.validate_digest(d) == [], "historical PU-4 FAIL with a composed PASS")
    # the digest rejects a relabelled or reshaped historical row, and PU-4 in a gate list
    for st in ("NOT APPLICABLE", "SUPERSEDED", "superseded", "PASS (A-1 superseded)", "HELD FOR REVIEW", ""):
        x = good_digest()
        x["historical"]["a1"]["pu4_row"][2] = st
        check(W.validate_digest(x), f"relabelled historical status {st!r} accepted")
    for row in (["PU-4h", "run", "FAIL", "x"], ["PU-4", "run", "FAIL"], ("PU-4", "run", "FAIL", "x"), None):
        x = good_digest()
        x["historical"]["a1"]["pu4_row"] = row
        check(W.validate_digest(x), f"historical row {row!r} accepted")
    x = good_digest()
    x["historical"]["a1"]["label"] = "A-1 (current)"
    check(W.validate_digest(x), "a historical section presented as current")
    x = good_digest()
    x["correctness"]["verdict"].update(status="FAIL", exit=1, gate_failures=["PU-4"])
    check(W.validate_digest(x), "PU-4 as a gate")
    # extraction never drops or chooses the historical row
    for rows in ([("PU-1", "run", "PASS", "")], [("PU-4", "run", "FAIL", "a"), ("PU-4", "run", "PASS", "b")],
                 [("PU-4", "run", "FAIL")], [("PU-4", "run", None, "x")], None, "rows"):
        try:
            W.extract_pu4(rows)
            raise AssertionError(f"extract_pu4 accepted {rows!r}")
        except W.EvaluationError:
            pass
    for row in (("PU-4h", "run", "PASS", "x"), ("PU-4", "run", "FAIL")):
        for fn in (W.pu4_report_row, lambda r_: W.historical_a1(r_, {}, {})):
            try:
                fn(row)
                raise AssertionError(f"accepted {row!r}")
            except W.EvaluationError:
                pass
    # the historical per-UE A-1 values: split off verbatim, never left among the current measurements
    ms = [{"k": 0, "node": 2049, "dl_service_ratio": 1.0, "harq": {"processes": 16, "inserts": 5, "feedback": 5, "nack": 0,
                                                                   "occupancy": {"busy": 1}, "feedback_delay_ps": [5]}},
          {"k": 1, "node": 2050, "dl_service_ratio": None, "harq": {"processes": 16, "inserts": 2, "feedback": 1, "nack": 1,
                                                                   "occupancy": None, "feedback_delay_ps": []}}]
    snap = copy.deepcopy(ms)
    cur, hist = W.split_per_ue(ms)
    check(ms == snap and all("harq" not in m for m in cur) and hist == {0: snap[0]["harq"], 1: snap[1]["harq"]}, "split")
    check([{k: v for k, v in m.items() if k != "harq"} for m in snap] == cur, "every current field verbatim")
    hist[0]["feedback"] = -1
    cur[0]["dl_service_ratio"] = -1
    check(ms == snap, "the split outputs share state with the s5n measurements")
    for bad in (None, {}, [None], [{"k": 0}, {"k": 0}]):
        try:
            W.split_per_ue(bad)
            raise AssertionError(f"split_per_ue accepted {bad!r}")
        except W.EvaluationError:
            pass
    h = W.historical_a1(("PU-4", "run", "FAIL", "x"), {"a1a": 1}, {0: {"f": 1}})
    h["harq_attribution"]["a1a"] = 2
    check(W.historical_a1(("PU-4", "run", "FAIL", "x"), {"a1a": 1}, {0: {"f": 1}})["harq_attribution"] == {"a1a": 1}, "copies")


# ================================================================================================ I-5 ============
COMMITTED = None


def committed_view():
    global COMMITTED
    if COMMITTED is None:
        COMMITTED = W.registry_view(W.load_registry())
    return COMMITTED


def truth_sca_values(node, truth):
    """Simu5G-like per-UE statistics from the GENERATOR TRUTH (independent of A-2.1): error rate = NACK / feedback,
    tx attempts = mean ntx of the ACKed PDUs"""
    per = {}
    for x in truth:
        e = per.setdefault(x["node"], {"fb": 0, "nack": 0, "ntx": []})
        e["fb"] += 1
        e["nack"] += x["res"] == "NACK"
        if x["res"] == "ACK":
            e["ntx"].append(x["ntx"])
    return {k: {ER: repr(per[n]["nack"] / per[n]["fb"]), TX: repr(sum(per[n]["ntx"]) / len(per[n]["ntx"]))}
            for k, n in node.items() if n in per and per[n]["ntx"]}


def pipe_full(lines, node, truth, view=None, nproc=16, t0=1000 * MS):
    """the complete library composition of one synthetic run (as I-7 will wire it): log + truth .sca written, A-1
    events, census, ONE A-2.1 replay, MAP-UE, C-0, PU-4h, PU-4o, A2-8u, FGO and the composed verdict"""
    d = tempfile.mkdtemp(prefix="e0vn21-i5-")
    try:
        p = os.path.join(d, "run.log.gz")
        with gzip.open(p, "wt") as fh:
            fh.writelines(lines)
        sca = write_sca(d, node, truth_sca_values(node, truth))
        a1 = PA.harq_events(p)
        with gzip.open(p, "rt") as fh:
            census = W.token_census(fh.read().splitlines(True))
        res, rows, per, cov, extra, window = A21.evaluate(A21.load(p), nproc, t0, node, TA.grants_of(lines), sca, simu5g_root())
        r = compose(len(node), node, a1, census, res, rows, per, cov, extra)
        a8, locs8 = W.a28u_rows(len(node), dict(node), PR.scalars(sca), A2.sca_nodes(sca), res,
                                W.scalar_record_counts(open(sca).read().splitlines(True)), r["map"]["status"], r["pu4h"]["status"])
    finally:
        shutil.rmtree(d)
    r["a28u"], r["coverage"] = a8, cov
    r["wrapper_rows"] = [r["map"], r["c0"], r["pu4h"]] + r["pu4o"] + a8
    r["fgo"] = W.fgo(cov, rows, view or committed_view())
    r["verdict"] = W.compose_verdict(len(node), r["wrapper_rows"], r["fgo"])
    return r


def HELD(r):
    return set(r["verdict"]["held_features"])


def nonadmitted_exercised(r, view):
    return {n for n, c, _ in r["coverage"] if c > 0 and n not in view["admitted"]}


def all_but(*names):
    return W.test_only_view([n for n in W.coverage_names() if n not in names])


# -------------------------------------------------------------------------------- T-n3-groups / multinack / discard
@named("T-n3-groups")
def t_n3_groups():
    lines, node, truth = G.make(3, 30, lambda tti: [0, 1, 2], tail=40)
    r = pipe_full(lines, node, truth)
    check(r["cov"]["exchangeable groups of 3 or more"] > 0 and r["st"]["A2-5"] == "PASS", f"groups of 3: {r['cov']}")
    check(r["pu4h"]["status"] == "PASS" and S(r) == ["PASS"] * 3 and [x["status"] for x in r["a28u"]] == ["PASS"] * 3,
          f"gates: PU-4h {r['pu4h']['status']}, PU-4o {S(r)}, A2-8u {[x['status'] for x in r['a28u']]}")
    check("exchangeable groups of 3 or more" in HELD(r) and r["verdict"]["status"] == W.V_HELD and r["verdict"]["exit"] == 3,
          f"committed registry: {r['verdict']}")
    check(HELD(r) == nonadmitted_exercised(r, committed_view()), f"held {HELD(r)} = the exercised non-admitted features")
    for x in r["fgo"]["held"]:
        check(x["reason"] == "first genuine occurrence", f"reason {x}")
    # TEST ONLY: everything admitted except groups of 3 -> exactly that feature held; everything admitted -> PASS
    r2 = W.compose_verdict(3, r["wrapper_rows"], W.fgo(r["coverage"], r["rows"], all_but("exchangeable groups of 3 or more")))
    check(r2["status"] == W.V_HELD and r2["held_features"] == ["exchangeable groups of 3 or more"], f"TEST ONLY minus groups of 3: {r2}")
    f_all = W.fgo(r["coverage"], r["rows"], W.test_only_view(W.coverage_names()))
    check(f_all["registry"] == W.TEST_ONLY_LABEL and f_all["registry_sha256"] is None, "TEST ONLY label, no file digest")
    check(W.compose_verdict(3, r["wrapper_rows"], f_all)["status"] == W.V_PASS, "TEST ONLY all admitted: PASS")


@named("T-multinack")
def t_multinack():
    s = lambda tti: [0, 1]
    _, _, t0 = G.make(2, 30, s, tail=40)
    by_t = {}
    for x in t0:
        by_t.setdefault(x["t"], []).append(x)
    pair = next(v for t, v in sorted(by_t.items()) if len(v) == 2 and t // MS > 1010)
    lines, node, truth = G.make(2, 30, s, nack={(pair[0]["pid"], 1), (pair[1]["pid"], 1)}, tail=40)
    r = pipe_full(lines, node, truth)
    check(r["cov"]["multi-NACK groups (handle relations kept ambiguous)"] > 0, f"multi-NACK {r['cov']}")
    check_counts_truth(r, truth)                                   # counts exact (as multisets)
    check("multi-NACK groups (handle relations kept ambiguous)" in HELD(r), f"held {HELD(r)}")
    check(HELD(r) == nonadmitted_exercised(r, committed_view()), "held = the exercised non-admitted features")
    check(r["verdict"]["status"] == W.V_HELD and r["verdict"]["exit"] == 3 and not r["verdict"]["gate_failures"]
          and not r["verdict"]["gate_not_evaluated"], f"every gate PASS, held for review: {r['verdict']}")


@named("T-discard")
def t_discard():
    s = lambda tti: [0] + ([1] if tti % 4 == 1 else [])
    _, _, t0 = G.make(2, 30, s, tail=60)
    pid = [x["pid"] for x in t0 if x["node"] == 2050][1]
    lines, node, truth = G.make(2, 30, s, nack={(pid, a) for a in (1, 2, 3, 4)}, max_rtx=3, tail=60)
    disc = {x["pid"] for x in truth if x["outcome"] == "discard"}
    check(disc == {pid}, f"truth discards {disc}")
    r = pipe_full(lines, node, truth)
    check(r["cov"]["discard after maxHarqRtx + 1 transmissions"] == 1, f"discard {r['cov']}")
    check(r["per"][2050]["discarded"] == 1 and r["per"][2049]["discarded"] == 0, "per-UE discarded = truth")
    check("discard after maxHarqRtx + 1 transmissions" in HELD(r) and HELD(r) == nonadmitted_exercised(r, committed_view()),
          f"held {HELD(r)}")
    check(r["verdict"]["status"] == W.V_HELD and not r["verdict"]["gate_failures"] and not r["verdict"]["gate_not_evaluated"],
          f"every gate PASS, held for review: {r['verdict']}")


# ----------------------------------------------------------------------------------------------- NC-registry ----
@named("NC-registry")
def nc_registry():
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    r = pipe_full(lines, node, truth)
    reg_sha = hashlib.sha256(open(W.REGISTRY_PATH, "rb").read()).hexdigest()
    check(r["fgo"]["registry_sha256"] == reg_sha and r["fgo"]["registry"].startswith("committed registry"), "committed view")
    base_held = HELD(r)
    check(r["cov"]["retransmissions"] > 0 and "retransmissions" not in base_held, "admitted retransmissions are not held")
    # genuinely unexercised features never trigger review
    for n_, c, _ in r["coverage"]:
        if c == 0:
            check(n_ not in base_held, f"an unexercised feature is held: {n_}")
    check(base_held == nonadmitted_exercised(r, committed_view()), f"held {base_held}")
    # NC-registry: 'retransmissions' no longer admitted (in memory) -> now held
    v = dict(committed_view(), admitted=[a for a in committed_view()["admitted"] if a != "retransmissions"])
    f = W.fgo(r["coverage"], r["rows"], v)
    check("retransmissions" in {h["feature"] for h in f["held"]}, "NC-registry: a de-admitted exercised feature is held")
    # NC-registry-unknown: a coverage name unknown to the registry -> held with its own reason (also with count 0)
    for cnt in (3, 0):
        f = W.fgo(list(r["coverage"]) + [("exchangeable groups of 5 or more", cnt, "x")], r["rows"], committed_view())
        u = [h for h in f["held"] if h["feature"] == "exchangeable groups of 5 or more"]
        check(len(u) == 1 and u[0]["reason"] == "unknown feature", f"NC-registry-unknown ({cnt}): {f['held']}")
        v_ = W.compose_verdict(2, r["wrapper_rows"], f)
        check("exchangeable groups of 5 or more" in v_["held_features"] and v_["status"] != W.V_PASS, f"{v_}")
    # NC-registry-missing: a registry name absent from the coverage output -> EVALUATION ERROR (exit 2)
    cov = [e for e in r["coverage"] if e[0] != "retransmissions"]
    v_ = W.run_verdict(lambda: W.compose_verdict(2, r["wrapper_rows"], W.fgo(cov, r["rows"], committed_view())))
    check(v_["status"] == W.V_ERROR and v_["exit"] == 2 and "schema drift" in v_["reason"], f"NC-registry-missing: {v_}")
    # NC-registry-uncited: an inferred feature admitted -> the registry is refused at load (EVALUATION ERROR)
    reg = json.load(open(W.REGISTRY_PATH, encoding="utf-8"))
    _by(reg, "single-candidate ACK attribution")["admitted"] = True
    _must_fail(reg, "NC-registry-uncited")
    # malformed coverage entries and views -> EVALUATION ERROR, never a silent pass
    for cov in (None, "x", [("a", 1)], list(r["coverage"]) + [r["coverage"][0]], [(n_, -1, "") for n_, _, _ in r["coverage"]],
                [(n_, True, "") for n_, _, _ in r["coverage"]]):
        check(W.run_verdict(W.fgo, cov, r["rows"], committed_view())["status"] == W.V_ERROR, f"coverage {str(cov)[:60]}")
    for view in (None, {}, dict(committed_view(), known=W.coverage_names()[:-1]),
                 dict(committed_view(), admitted=["not a feature"]), dict(committed_view(), admitted=["retransmissions"] * 2)):
        check(W.run_verdict(W.fgo, r["coverage"], r["rows"], view)["status"] == W.V_ERROR, f"view {str(view)[:60]}")
    check(W.run_verdict(W.fgo, r["coverage"], [x for x in r["rows"] if x[0] != "A2-4c"], committed_view())["status"] == W.V_ERROR,
          "no A2-4c row")
    # the admissions are exactly the nine of revision 2.1
    check(committed_view()["admitted"] == ADMITTED, "committed admissions")


@named("T-a24c-review")
def t_a24c_review():
    """A2-4c exercised (scheduler logging on: never genuine) is held; an A2-4c FAIL also fails PU-4h (NOT VALID)"""
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1, sched_log=True)
    r = pipe_full(lines, node, truth)
    check(r["st"]["A2-4c"] == "PASS" and W.FGO_A24C in HELD(r), f"A2-4c {r['st']['A2-4c']}, held {HELD(r)}")
    rows_fail = [(k, s_, "FAIL" if k == "A2-4c" else st, d_) for k, s_, st, d_ in r["rows"]]
    ph, _ = W.pu4h_row(r["map"], r["c0"], rows_fail, r["res"])
    check(ph["status"] == "FAIL", "an A2-4c FAIL fails PU-4h")
    f = W.fgo(r["coverage"], rows_fail, committed_view())
    check(W.FGO_A24C in {h["feature"] for h in f["held"]}, "an A2-4c FAIL is also held")
    rows_w = [r["map"], r["c0"], ph] + [W.pu4o_row(k, x, "PASS", "FAIL", "PASS") for k, x in enumerate(r["locs"])] + \
        [W.a28u_row(k, x, "PASS", "FAIL") for k, x in enumerate(W.a28u_rows(2, dict(node), None, None, r["res"], {}, "PASS", "FAIL")[1])]
    v = W.compose_verdict(2, rows_w, f)
    check(v["status"] == W.V_FAIL and W.FGO_A24C in v["held_features"], f"FAIL with the review item listed: {v}")
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    r = pipe_full(lines, node, truth)
    check(r["st"]["A2-4c"] == W.NE and W.FGO_A24C not in HELD(r), "no scheduler logging: A2-4c NE, not held")


# -------------------------------------------------------------------------------------------------- T-verdict ----
def _wrows(n=2, **status):
    """synthetic wrapper rows: every row PASS unless overridden, e.g. PU4h='NOT EVALUATED', PU4o1='FAIL'"""
    def st(key, local=False):
        s_ = status.get(key, "PASS")
        return s_, (W.EQUAL if s_ == "PASS" else (W.DIFFERENT if s_ == "FAIL" else W.NOT_COMPARED)) if local else None
    rows = []
    for rid, key in ((W.ROW_MAP, "MAP"), (W.ROW_C0, "C0"), (W.ROW_PU4H, "PU4h")):
        rows.append({"id": rid, "subject": "run", "status": st(key)[0], "detail": "synthetic"})
    for rid, key in ((W.ROW_PU4O, "PU4o"), (W.ROW_A28U, "A28u")):
        for k in range(n):
            s_, loc = st(f"{key}{k}", True)
            rows.append({"id": rid, "subject": f"UE {k}", "status": s_, "local": loc, "detail": "synthetic"})
    return rows


def _held(*names):
    return {"held": [{"feature": n, "count": 1, "reason": "first genuine occurrence"} for n in names]}


@named("T-verdict")
def t_verdict():
    info, ne = W.s5n_info()
    NONE = _held()
    H = _held("exchangeable groups of 3 or more")
    s5 = lambda *rs: list(rs)
    table = [
        ("all PASS, nothing held", _wrows(), NONE, None, W.V_PASS, [], []),
        ("held only", _wrows(), H, None, W.V_HELD, [], []),
        ("wrapper NE", _wrows(PU4h=W.NE), NONE, None, W.V_INCOMPLETE, [], ["PU-4h"]),
        ("wrapper NE + held: INCOMPLETE wins", _wrows(A28u1=W.NE), H, None, W.V_INCOMPLETE, [], ["A2-8u"]),
        ("wrapper FAIL + NE + held: FAIL wins", _wrows(C0="FAIL", PU4o0=W.NE), H, None, W.V_FAIL, ["C-0"], ["PU-4o"]),
        ("every wrapper row FAIL", _wrows(MAP="FAIL", C0="FAIL", PU4h="FAIL", PU4o0="FAIL", PU4o1="FAIL", A28u0="FAIL", A28u1="FAIL"),
         NONE, None, W.V_FAIL, ["A2-8u", "C-0", "MAP-UE", "PU-4h", "PU-4o"], []),
        ("s5n gate FAIL", _wrows(), NONE, s5(("SG-403", "run", "FAIL", "")), W.V_FAIL, ["SG-403"], []),
        ("s5n info FAIL is not a gate", _wrows(), NONE, s5(("F0-1 (info)", "run", "FAIL", ""), ("H-cov (diagnostic)", "run", "FAIL", "")),
         W.V_PASS, [], []),
        ("s5n non-PU NE is not a gate", _wrows(), NONE, s5(("Q8-v", "run", ne, ""), ("EOR", "x", "NOT APPLICABLE", "")), W.V_PASS, [], []),
        ("s5n AV NE gates", _wrows(), H, s5(("AV-2", "UE 1", ne, "")), W.V_INCOMPLETE, [], ["AV-2"]),
        ("s5n PU-5 NE gates", _wrows(), NONE, s5(("PU-5", "run", ne, "")), W.V_INCOMPLETE, [], ["PU-5"]),
        ("historical PU-4 FAIL is not a gate", _wrows(), NONE, s5(("PU-4", "run", "FAIL", "A-1 ambiguous 768")), W.V_PASS, [], []),
        ("historical PU-4 NE is not a gate", _wrows(), NONE, s5(("PU-4", "run", ne, "no MAC log")), W.V_PASS, [], []),
        ("historical PU-4 FAIL with held", _wrows(), H, s5(("PU-4", "run", "FAIL", "x")), W.V_HELD, [], []),
        ("s5n FAIL + wrapper NE + held", _wrows(PU4o1=W.NE), H, s5(("MG-1", "run", "FAIL", ""), ("PU-4", "run", "FAIL", "")),
         W.V_FAIL, ["MG-1"], ["PU-4o"]),
    ]
    for what, rows, f, s5rows, want, wf, wn in table:
        v = W.compose_verdict(2, rows, f, s5rows, info, ne)
        check((v["status"], v["exit"], v["gate_failures"], v["gate_not_evaluated"]) == (want, W.EXIT[want], wf, wn),
              f"{what}: {v}")
        check(v["held_features"] == [h["feature"] for h in f["held"]], f"{what}: held features listed whatever the outcome")
        # the composed verdict is consistent with the digest schema of I-1
        x = good_digest()
        x["correctness"]["rows"] = rows
        x["correctness"]["verdict"] = {k: v[k] for k in W.VERDICT_KEYS}
        x["correctness"]["s5n"]["gate_failures"] = sorted({r_[0] for r_ in (s5rows or []) if r_[2] == "FAIL" and r_[0] not in info})
        x["correctness"]["s5n"]["per_ue_not_evaluated"] = sorted({r_[0] for r_ in (s5rows or []) if r_[2] == ne and r_[0].startswith(("PU-", "AV-"))})
        if any(r_["status"] != "PASS" for r_ in rows if r_["id"] in (W.ROW_MAP, W.ROW_C0, W.ROW_PU4H)):
            continue                                   # the digest also checks the global rules between rows
        check(W.validate_digest(x) == [], f"{what}: digest {W.validate_digest(x)[:3]}")
    # precedence exits: 2 > 1 > 4 > 3 > 0
    check([W.EXIT[s_] for s_ in W.PRECEDENCE] == [2, 2, 1, 4, 3, 0], "exit codes")
    # REFUSED / EVALUATION ERROR: missing, duplicated or malformed gates, a bad FGO result, s5n rows using wrapper ids
    bad = [("a missing PU-4h", lambda: W.compose_verdict(2, [x for x in _wrows() if x["id"] != W.ROW_PU4H], NONE)),
           ("a missing UE 1 row", lambda: W.compose_verdict(2, [x for x in _wrows() if x["subject"] != "UE 1"], NONE)),
           ("UE 2 rows with numUe 2", lambda: W.compose_verdict(2, _wrows(3), NONE)),
           ("a duplicated row", lambda: W.compose_verdict(2, _wrows() + [_wrows()[0]], NONE)),
           ("a malformed row", lambda: W.compose_verdict(2, _wrows()[:-1] + [dict(_wrows()[-1], status="OK")], NONE)),
           ("an NX wrapper row", lambda: W.compose_verdict(2, [dict(x, status=W.NX) if x["id"] == W.ROW_C0 else x for x in _wrows()], NONE)),
           ("no FGO result", lambda: W.compose_verdict(2, _wrows(), None)),
           ("a malformed held entry", lambda: W.compose_verdict(2, _wrows(), {"held": [{"feature": ""}]})),
           ("malformed s5n rows", lambda: W.compose_verdict(2, _wrows(), NONE, [("PU-1",)], info, ne)),
           ("s5n row with a wrapper id", lambda: W.compose_verdict(2, _wrows(), NONE, [("PU-4h", "run", "FAIL", "")], info, ne)),
           ("numUe 0", lambda: W.compose_verdict(0, [], NONE))]
    for what, fn in bad:
        v = W.run_verdict(fn)
        check(v["status"] == W.V_ERROR and v["exit"] == 2 and not v["gate_failures"] and not v["held_features"], f"{what}: {v}")
    v = W.run_verdict(lambda: (_ for _ in ()).throw(W.Refused("name guard")))
    check(v["status"] == W.V_REFUSED and v["exit"] == 2, f"REFUSED {v}")
    # historical values and the diagnostic cannot influence the verdict: compose_verdict takes neither
    import inspect
    params = list(inspect.signature(W.compose_verdict).parameters)
    check(params == ["n", "rows", "fgo_result", "s5n_rows", "info", "ne"], f"compose_verdict parameters {params}")


@named("T-s5n-semantics")
def t_s5n_semantics():
    """s5n_gates() equals the two expressions of the accepted check_m2s72_s5n.py:140-141, executed verbatim on the same
    rows, minus PU-4 only"""
    src = open(os.path.join(HERE, "check_m2s72_s5n.py")).read().splitlines()
    exprs = [l_.strip() for l_ in src[139:141]]
    check(exprs[0].startswith("gate_fail = sorted({r[0] for r in mine if r[2] == \"FAIL\" and r[0] not in E.INFO})") and
          exprs[1].startswith("ne = sorted({r[0] for r in mine if r[2] == E.NE and r[0].startswith((\"PU-\", \"AV-\"))})"),
          f"the accepted s5n predicate moved or changed: {exprs}")
    info, ne = W.s5n_info()
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        import check_m2s72_s5n as S5N
    finally:
        sys.argv = argv
    check(tuple(S5N.E.INFO) == info and S5N.E.NE == ne, "INFO / NE from the same accepted module")
    import random
    rnd = random.Random(7)
    ids = ["PU-1", "PU-2", "PU-3", "PU-4", "PU-5", "AV-1", "AV-2", "AV-3", "Q8-v", "SG-403", "MG-1", "EOR", "F0-1 (info)",
           "F0-2", "I-2H", "I-2 strict (info)", "H-cov (diagnostic)", "M3d", "Q8 UE 0"]
    sts = ["PASS", "FAIL", ne, "NOT APPLICABLE", "NOT EXERCISED"]
    for _ in range(400):
        rows = [(rnd.choice(ids), "run", rnd.choice(sts), "x") for _ in range(rnd.randint(0, 25))]
        ns = {"mine": rows, "E": S5N.E}
        exec(exprs[0] + "\n" + exprs[1], {}, ns)
        f, n_ = W.s5n_gates(rows, info, ne)
        check(f == [x for x in ns["gate_fail"] if x != "PU-4"] and n_ == [x for x in ns["ne"] if x != "PU-4"],
              f"s5n semantics differ on {rows}")


# ================================================================================================ I-6 ============
import contextlib  # noqa: E402
import io  # noqa: E402
import check_m2s72_a21 as CC  # noqa: E402  (accepted; read-only: inputs(), a21())
import check_m2s72_s5n21 as CLIM  # noqa: E402

FIXDIR = os.path.join(HERE, "fixtures")
F3_EXPECT = os.path.join(HERE, "expect", "f3.expect.json")
SYN_CFG = "M2S72-E0vN-q0-one0-n2-f1"


def cli(args, env_extra=None, drop=(), cwd=None):
    """the CLI as a separate process under -I -B (what tier-0 and the executors run)"""
    env = {k: v for k, v in os.environ.items() if not k.startswith("PYTHON") and k not in drop}
    env.update(env_extra or {})
    return subprocess.run([sys.executable, "-I", "-B", CLI_PATH] + args, cwd=cwd or tempfile.gettempdir(), env=env,
                          capture_output=True, text=True, timeout=600)


CLI_PATH = os.path.join(HERE, "check_m2s72_s5n21.py")


def cli_inproc(args):
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = CLIM.main(["check_m2s72_s5n21.py"] + args)
    return rc, buf.getvalue()


def file_digests(paths):
    return {p: hashlib.sha256(open(p, "rb").read()).hexdigest() for p in paths}


def fixture_files():
    return [os.path.join(FIXDIR, x) for x in ("a2v1-first-chain.log.gz", "a2v1-first-chain.log.gz.sha256",
                                              "a2v1-first-chain.meta.json")]


@contextlib.contextmanager
def synthetic_runs(lines, node, truth, cfg=SYN_CFG, sca=True):
    """a synthetic run tree in the layout hrq reads (<runs>/run-<cfg>.log.gz, <runs>/<cfg>/<cfg>/0.sca). The node ids
    come from Run72 on a real run tree; here check_m2s72_a21.inputs() is replaced IN MEMORY, for the duration of the
    block, by the same tuple built from the synthetic files (the accepted file is not changed)."""
    d = tempfile.mkdtemp(prefix="e0vn21-runs-")
    runs = os.path.join(d, "runs")
    os.makedirs(os.path.join(runs, cfg, cfg))
    log = os.path.join(runs, f"run-{cfg}.log.gz")
    with gzip.open(log, "wt") as fh:
        fh.writelines(lines)
    scap = None
    if sca:
        scap = write_sca(os.path.join(runs, cfg, cfg), node, truth_sca_values(node, truth))
    orig = CC.inputs

    def fake(runs_, cfg_):
        check(runs_ == runs and cfg_ == cfg, "inputs() called for another run")
        return A21.load(log), TA.grants_of(lines), dict(node), os.path.join(runs, cfg, cfg, "0.sca"), simu5g_root()
    CC.inputs = fake
    try:
        yield d, runs, log, scap
    finally:
        CC.inputs = orig
        shutil.rmtree(d)


def count_replays():
    calls = []
    orig = A21.replay

    def counted(lines):
        calls.append(1)
        return orig(lines)
    return calls, orig, counted


# ---------------------------------------------------------------------------------------- T-f3-hrq / T-f3-a1 ----
@named("T-f3-hrq")
def t_f3_hrq():
    root = simu5g_root()
    before = file_digests(fixture_files() + [W.REGISTRY_PATH, F3_EXPECT])
    d = tempfile.mkdtemp(prefix="e0vn21-f3-")
    try:
        r = cli(["hrq-fixture", FIXDIR, os.path.join(d, "a"), "--expect", F3_EXPECT], {"SIMU5G_ROOT": root})
        check(r.returncode == 0 and "58 / 58 MATCH; ALL EXPECTATIONS MET" in r.stdout, f"rc {r.returncode}: {r.stdout[-600:]} {r.stderr[-600:]}")
        r2 = cli(["hrq-fixture", FIXDIR, os.path.join(d, "b")], {"SIMU5G_ROOT": root})
        check(r2.returncode == 4, f"without --expect: rc {r2.returncode} (INCOMPLETE expected)")
        names = sorted(os.listdir(os.path.join(d, "a")))
        check(names == ["a21-f3-fixture.json", "a21-f3-fixture.txt", "hrq-f3-fixture.expect.txt", "hrq-f3-fixture.json",
                        "hrq-f3-fixture.txt"], f"records {names}")
        check(sorted(os.listdir(os.path.join(d, "b"))) == [n for n in names if "expect" not in n], "records without --expect")
        out = json.load(open(os.path.join(d, "b", "hrq-f3-fixture.json")))
        check(out["label"] == CLIM.FIXTURE_LABEL and out["inputs"]["fixture"]["sha256"] == "cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b"
              and out["inputs"]["fixture"]["cfg"] == "M2S72-E0vN-q0-one0-n2-f1_A2V1", "fixture provenance recorded")
        check(out["verdict"]["status"] == "INCOMPLETE" and out["verdict"]["exit"] == 4, f"{out['verdict']}")
        check(all(W.validate_row(x) == [] for x in out["rows"]), "row schema")
        # the A-2.1 rows are those of the accepted real-chain validation (R-1 .. R-10) on the same fixture
        fx = RC.load_fixture(FIXDIR)
        rc_out, ctx = RC.validate(fx, root)
        check(all(s_ == "PASS" for _, s_, _ in rc_out), f"accepted real-chain expectations {[x for x in rc_out if x[1] != 'PASS']}")
        check([list(x) for x in ctx["rows"]] == out["a21"]["rows"], "A-2.1 rows differ from m2s72_a21_realchain's")
        # reproducible records: two evaluations give byte-identical files (the expectation table aside)
        for n_ in ("a21-f3-fixture.json", "a21-f3-fixture.txt", "hrq-f3-fixture.json", "hrq-f3-fixture.txt"):
            check(open(os.path.join(d, "a", n_), "rb").read() == open(os.path.join(d, "b", n_), "rb").read(), f"{n_} not reproducible")
    finally:
        shutil.rmtree(d)
    check(file_digests(fixture_files() + [W.REGISTRY_PATH, F3_EXPECT]) == before, "an input, the registry or the expectation file changed")


@named("T-f3-a1")
def t_f3_a1():
    root = simu5g_root()
    d = tempfile.mkdtemp(prefix="e0vn21-f3a1-")
    try:
        r = cli(["hrq-fixture", FIXDIR, os.path.join(d, "a")], {"SIMU5G_ROOT": root})
        check(r.returncode == 4, f"rc {r.returncode}")
        out = json.load(open(os.path.join(d, "a", "hrq-f3-fixture.json")))
    finally:
        shutil.rmtree(d)
    fx = RC.load_fixture(FIXDIR)
    ev = PA.harq_events(fx["path"])
    trace = []
    _, summ = P.attribute_feedback(ev, fx["nproc"], window=tuple(out["window_ps"]), trace=trace)
    pu4 = next(x for x in P.structural_rows([], [], summ, None) if x[0] == "PU-4")
    check(out["historical"]["a1_summary"] == json.loads(json.dumps(W_clean(summ))), "the A-1 summary differs from the frozen rule's")
    check(out["historical"]["a1_pu4_row"] == list(pu4), f"the A-1 PU-4 row differs: {out['historical']['a1_pu4_row']} vs {pu4}")
    ag = out["diagnostics"]["agreement"]
    check(ag["computed"] and ag["agree"] + ag["disagree"] + sum(ag["a1_attributed_without_a21_owner"].values()) == summ["a1a"] + summ["a1b"]
          and sum(ag["a1_unattributed_by_a21_class"].values()) == summ["ambiguous"] + summ["orphan"], f"agreement vs A-1 {ag} {summ}")
    check("not a gate" in out["historical"]["label"] and "PU-4" not in out["verdict"]["gate_failures"], "A-1 reported, never gating")


def W_clean(x):
    import check_m2s72_a2 as C
    return C._clean(x)


# ------------------------------------------------------------------------------------------- T-single-replay ----
@named("T-single-replay")
def t_single_replay():
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    calls, orig, counted = count_replays()
    A21.replay = counted
    try:
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca):
            before = file_digests([log, sca])
            rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d, "rec"), "--t0", "1"])
            check(len(calls) == 1, f"hrq replayed {len(calls)} times")
            out = json.load(open(os.path.join(d, "rec", f"hrq-{SYN_CFG}.json")))
            rows = [tuple(x) for x in out["a21"]["rows"]]
            check(out["a21"]["verdict_f1d_i"] == A21.verdict(rows, "f1d-i")[0] and out["a21"]["verdict_full"] == A21.verdict(rows, "full")[0],
                  "both contract verdicts from the same rows")
            check(out["a21"]["verdict_f1d_i"] == "A-2.1 VALID" and out["a21"]["verdict_full"] == "A-2.1 INCOMPLETE", f"{out['a21']['verdict_f1d_i']}")
            check(file_digests([log, sca]) == before, "hrq modified its inputs")
            # IG-2: the .sca duplicate census ran before the comparisons; A2-8u PASS on truth statistics
            check(out["inputs"]["sca_duplicate_census"] == {"performed": True, "duplicates": []}, f"{out['inputs']['sca_duplicate_census']}")
            check([x["status"] for x in out["rows"] if x["id"] == "A2-8u"] == ["PASS", "PASS"], "A2-8u PASS with the census")
            check(rc == out["verdict"]["exit"] == 3 and out["verdict"]["status"] == "HELD FOR REVIEW", f"rc {rc}, {out['verdict']}")
            # IG-3: A2-7 / its occupancy comparison are exactly those of an independent run of the accepted evaluator
            res, rows2, per, cov, extra, window = A21.evaluate(A21.load(log), 16, 1000 * MS, dict(node), TA.grants_of(lines), sca, simu5g_root())
            check(out["a21"]["a2_7"] == json.loads(json.dumps(W_clean(extra["xa"]))), "A2-7 reference output not passed through verbatim")
        # IG-2 on the CLI path: a duplicated scalar record in the .sca is found by the census and blocks that UE's A2-8u
        calls.clear()
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca):
            dup = [x for x in open(sca).read().splitlines(True) if f"{W.ue_module(1)} {ER}" in x]
            open(sca, "a").writelines(dup)
            rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d, "rec"), "--t0", "1"])
            out = json.load(open(os.path.join(d, "rec", f"hrq-{SYN_CFG}.json")))
            a8 = {x["subject"]: x for x in out["rows"] if x["id"] == "A2-8u"}
            check(out["inputs"]["sca_duplicate_census"]["duplicates"] == [f"{W.ue_module(1)} {ER}"], f"{out['inputs']['sca_duplicate_census']}")
            check(a8["UE 1"]["status"] == "NOT EVALUATED" and "ambiguous: 2 records" in a8["UE 1"]["detail"] and a8["UE 0"]["status"] == "PASS",
                  f"duplicate record: {a8}")
            check(out["a21"]["run_level_a2_8"][2] == "PASS" and rc == 4, f"run-level A2-8 (frozen, last record) {out['a21']['run_level_a2_8'][2]}, rc {rc}")
        calls.clear()
        with tempfile.TemporaryDirectory() as d:
            rc, _ = cli_inproc(["hrq-fixture", FIXDIR, os.path.join(d, "f")])
            check(rc == 4 and len(calls) == 1, f"hrq-fixture: rc {rc}, replays {len(calls)}")
    finally:
        A21.replay = orig
    # IG-2 in the library: without the duplicate census, a present statistic is never compared
    locs = W.a28u_rows(2, {0: 2049, 1: 2050}, {W.ue_module(0): {ER: "0", TX: "1"}, W.ue_module(1): {ER: "0", TX: "1"}},
                       {W.ue_module(0): 2049, W.ue_module(1): 2050}, mkres({2049: (["ACK"], [1]), 2050: (["ACK"], [1])}),
                       None, "PASS", "PASS")
    check([x["status"] for x in locs[0]] == ["NOT EVALUATED"] * 2 and all(s_["step"] == "V-1" for x in locs[1] for s_ in x["stats"].values()),
          f"IG-2: {[x['status'] for x in locs[0]]}")
    # IG-3 / IG-5 / IG-6 in the source: no constructed reference, no TEST ONLY view, the committed registry only
    src = open(CLI_PATH).read()
    check("test_only_view" not in src and "TEST ONLY" not in src and "TEST_ONLY" not in src, "the CLI can reach a TEST ONLY view")
    check(src.count("W.load_registry(W.REGISTRY_PATH)") == 1 and "registry_view(W.load_registry(W.REGISTRY_PATH))" in src, "registry path")
    check(not re.search(r"occupancy_equal\"?\]?\s*=|\[\"occupancy_equal\"\]\s*=", src), "the CLI assigns an occupancy comparison")
    check(src.count("W.A21.evaluate(") == 1 and "A21.replay" not in src and "fgo(cov, rows, view)" in src, "one replay; coverage and rows of it")


# ------------------------------------------------------------------------------------------ T-a21-record-equiv ---
def sections(txt):
    """the ROWS .. handles part of an A-2.1 record (between the header and the verdict line(s))"""
    i = txt.index("ROWS\n")
    j = txt.index("\nA-2.1 verdict")
    return txt[i:j]


@named("T-a21-record-equiv")
def t_a21_record_equiv():
    lines, node, truth, T = nack_run(2, lambda tti: [0] + ([1] if tti % 3 == 0 else []), 1, 1)
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca):
        rc, _ = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d, "rec")])
        mine_t = open(os.path.join(d, "rec", f"a21-{SYN_CFG}.txt")).read()
        mine_j = json.load(open(os.path.join(d, "rec", f"a21-{SYN_CFG}.json")))
        for contract in ("f1d-i", "full"):
            with contextlib.redirect_stdout(io.StringIO()):
                CC.a21(runs, SYN_CFG, os.path.join(d, f"acc-{contract}"), contract=contract)
            acc_t = open(os.path.join(d, f"acc-{contract}", f"a21-{SYN_CFG}.txt")).read()
            acc_j = json.load(open(os.path.join(d, f"acc-{contract}", f"a21-{SYN_CFG}.json")))
            check(sections(mine_t) == sections(acc_t), f"{contract}: ROWS / COVERAGE / PER UE / handles sections differ")
            check(f"A-2.1 verdict ({contract}): {acc_j['verdict']}" in mine_t and mine_j["verdicts"][contract] == acc_j["verdict"],
                  f"{contract}: verdict {acc_j['verdict']} not in the wrapper record")
            same = {k: v for k, v in acc_j.items() if k not in ("contract", "verdict")}
            check({k: mine_j[k] for k in same} == same, f"{contract}: JSON fields differ: "
                  f"{[k for k in same if mine_j.get(k) != same[k]]}")
            check(acc_t.splitlines()[1:3] == mine_t.splitlines()[1:3], "the NOTE lines")


# ------------------------------------------------------------------------------------------------ T-expect-exit --
@named("T-expect-exit")
def t_expect_exit():
    root = simu5g_root()
    base = json.load(open(F3_EXPECT))
    d = tempfile.mkdtemp(prefix="e0vn21-exp-")
    try:
        def run(doc, name, raw=None):
            p = os.path.join(d, f"{name}.json")
            with open(p, "w") as fh:
                fh.write(raw if raw is not None else json.dumps(doc))
            r = cli(["hrq-fixture", FIXDIR, os.path.join(d, name), "--expect", p], {"SIMU5G_ROOT": root})
            return r, os.path.join(d, name)
        r, rec = run(base, "match")
        check(r.returncode == 0, f"matching: rc {r.returncode}")
        for key, val in (("census.insert", 98), ("verdict.status", "PASS"), ("coverage.retransmissions", 4),
                         ("verdict.held_features", ["single-candidate ACK attribution"]), ("rows.PU-4o.UE 1.local", "DIFFERENT"),
                         ("per_ue.2050.nack", 99)):
            doc = copy.deepcopy(base)
            doc["expect"][key] = val
            r, rec = run(doc, f"mis-{key.replace(' ', '_').replace('/', '_')}")
            t = open(os.path.join(rec, "hrq-f3-fixture.expect.txt")).read()
            check(r.returncode == 5 and "EXPECTATION MISMATCH" in t and f"MISMATCH | {key} |" in t, f"mismatch {key}: rc {r.returncode}")
            check(os.path.isfile(os.path.join(rec, "hrq-f3-fixture.json")), "the records are kept on a mismatch")
        # held_features_if_exercised: a declared condition
        doc = copy.deepcopy(base)
        doc["expect"]["verdict.held_features"] = ["single-candidate ACK attribution"]
        doc["expect"]["verdict.held_features_if_exercised"] = ["exchangeable ACK groups (2 candidates)", "multi-NACK groups (handle relations kept ambiguous)"]
        r, rec = run(doc, "cond")
        check(r.returncode == 0, f"conditional held features: rc {r.returncode}")
        # malformed expectation files: exit 2, nothing evaluated or written
        bad = {"json": None, "schema": dict(base, schema="m2s72-s5n21-expect/2"), "config": dict(base, config="M2S72-E0v-q0-f1"),
               "unknown-key": dict(base, expect=dict(base["expect"], **{"verdict.colour": "green"})),
               "empty": dict(base, expect={}), "extra-top": dict(base, extra=1), "no-expect": {"schema": base["schema"], "config": "f3-fixture"},
               "cond-alone": dict(base, expect={"verdict.held_features_if_exercised": []}), "list": None}
        for name, doc in bad.items():
            raw = "{ not json" if name == "json" else ("[1]" if name == "list" else None)
            r, rec = run(doc, f"bad-{name}", raw)
            check(r.returncode == 2 and "expectation file" in r.stdout and not os.path.exists(rec), f"malformed {name}: rc {r.returncode}")
        r = cli(["hrq-fixture", FIXDIR, os.path.join(d, "noexp"), "--expect", os.path.join(d, "missing.json")], {"SIMU5G_ROOT": root})
        check(r.returncode == 2, "a missing expectation file")
    finally:
        shutil.rmtree(d)


# ----------------------------------------------------------------------------------------------- NC-cli-inputs ---
@named("NC-cli-inputs")
def nc_cli_inputs():
    root = simu5g_root()
    d = tempfile.mkdtemp(prefix="e0vn21-cli-")
    try:
        rec = lambda n_: os.path.join(d, n_)
        cases = [
            ("no mode", [], {}),
            ("unknown mode", ["evaluate", "x"], {}),
            ("run without S5N_ADAPTER_VALIDATED", ["run", d, SYN_CFG, rec("r")], {"drop": ("S5N_ADAPTER_VALIDATED",)}),
            ("controls: no log", ["controls", d, SYN_CFG, rec("c")], {}),
            ("hrq: wrong arity", ["hrq", d, SYN_CFG], {}),
            ("hrq: extra positional", ["hrq", d, SYN_CFG, rec("x"), "y"], {}),
            ("hrq: name refused", ["hrq", d, "M2S72-E0vNL-q0-f1", rec("n1")], {}),
            ("hrq: suffixed name refused", ["hrq", d, "M2S72-E0vN-q0-one0-n2-f1_X", rec("n2")], {}),
            ("hrq: no log", ["hrq", d, SYN_CFG, rec("nolog")], {}),
            ("hrq: --t0 not a number", ["hrq", d, SYN_CFG, rec("t0"), "--t0", "abc"], {}),
            ("hrq: --t0 negative", ["hrq", d, SYN_CFG, rec("t0n"), "--t0", "-1"], {}),
            ("hrq: --t0 twice", ["hrq", d, SYN_CFG, rec("t02"), "--t0", "1", "--t0", "2"], {}),
            ("unknown option (e.g. a registry override)", ["hrq-fixture", FIXDIR, rec("reg"), "--registry", W.REGISTRY_PATH], {}),
            ("hrq-fixture: --t0", ["hrq-fixture", FIXDIR, rec("ft0"), "--t0", "1"], {}),
            ("hrq-fixture: no SIMU5G_ROOT", ["hrq-fixture", FIXDIR, rec("noroot")], {"env": {}, "drop": ("SIMU5G_ROOT",)}),
            ("hrq-fixture: SIMU5G_ROOT not a directory", ["hrq-fixture", FIXDIR, rec("badroot")], {"env": {"SIMU5G_ROOT": os.path.join(d, "none")}}),
            ("hrq-fixture: no fixture", ["hrq-fixture", os.path.join(d, "nofx"), rec("nofx-r")], {}),
            ("records dir parent missing", ["hrq-fixture", FIXDIR, os.path.join(d, "no", "parent")], {}),
        ]
        for what, args, kw in cases:
            r = cli(args, kw.get("env", {"SIMU5G_ROOT": root}), kw.get("drop", ()))
            check(r.returncode == 2, f"{what}: rc {r.returncode}: {r.stdout[-300:]}")
            check("Traceback" not in r.stderr, f"{what}: {r.stderr[-300:]}")
        for a in ("r", "c", "n1", "n2", "nolog", "t0", "reg", "ft0", "noroot", "badroot", "nofx-r"):
            check(not os.path.exists(rec(a)), f"records dir {a} created by a refused call")
        # an existing records dir is never reused or touched
        os.mkdir(rec("exists"))
        open(os.path.join(rec("exists"), "keep.txt"), "w").write("mine")
        r = cli(["hrq-fixture", FIXDIR, rec("exists")], {"SIMU5G_ROOT": root})
        check(r.returncode == 2 and os.listdir(rec("exists")) == ["keep.txt"] and open(os.path.join(rec("exists"), "keep.txt")).read() == "mine",
              f"records dir reuse: rc {r.returncode}")
        check("REFUSED: records dir" in r.stdout and "never reused" in r.stdout and "WRAPPER ROWS" not in r.stdout,
              f"an existing records dir is refused before any evaluation: {r.stdout[-300:]}")
        # a corrupted fixture copy (pin / metadata mismatch) is refused before any evaluation
        fx2 = os.path.join(d, "fx2")
        shutil.copytree(FIXDIR, fx2)
        meta = os.path.join(fx2, "a2v1-first-chain.meta.json")
        m = json.load(open(meta))
        m["fixture_sha256"] = "0" * 64
        json.dump(m, open(meta, "w"))
        r = cli(["hrq-fixture", fx2, rec("fx2r")], {"SIMU5G_ROOT": root})
        check(r.returncode == 2 and "fixture refused" in r.stdout and not os.path.exists(rec("fx2r")), f"corrupted fixture: rc {r.returncode}")
        # the registry is validated on the CLI path: a corrupted registry (in place of the committed one) is exit 2
        bad_reg = os.path.join(d, "reg.json")
        reg = json.load(open(W.REGISTRY_PATH))
        _by(reg, "single-candidate ACK attribution")["admitted"] = True
        json.dump(reg, open(bad_reg, "w"))
        orig = W.REGISTRY_PATH
        W.REGISTRY_PATH = bad_reg
        try:
            rc, txt = cli_inproc(["hrq-fixture", FIXDIR, rec("badreg")])
        finally:
            W.REGISTRY_PATH = orig
        check(rc == 2 and "registry" in txt and not os.path.exists(rec("badreg")), f"invalid registry on the CLI path: rc {rc}")
        # node ids unavailable -> REFUSED; a numUe that contradicts the name -> EVALUATION ERROR
        lines, node, truth = G.make(2, 20, lambda tti: [0, 1], tail=40)
        with synthetic_runs(lines, node, truth) as (d2, runs, log, sca):
            o = CC.inputs
            CC.inputs = lambda r_, c_: o(r_, c_)[:2] + (None,) + o(r_, c_)[3:]
            rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d2, "x")])
            check(rc == 2 and "REFUSED" in txt, f"no node ids: rc {rc}")
            CC.inputs = lambda r_, c_: o(r_, c_)[:2] + ({0: 2049},) + o(r_, c_)[3:]
            rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d2, "y")])
            check(rc == 2 and "numUe" in txt, f"numUe contradicting the name: rc {rc}")
            CC.inputs = o
        # an input that changes during the evaluation is detected (simulated by a log rewritten by harq_events' reader)
        lines, node, truth = G.make(2, 20, lambda tti: [0, 1], tail=40)
        with synthetic_runs(lines, node, truth) as (d2, runs, log, sca):
            orig_he = PA.harq_events

            def tamper(path, *a, **k):
                out = orig_he(path, *a, **k)
                open(sca, "a").write("\n")
                return out
            PA.harq_events = tamper
            try:
                rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d2, "z")])
            finally:
                PA.harq_events = orig_he
            check(rc == 2 and "an input changed" in txt and not os.path.exists(os.path.join(d2, "z")), f"changed input: rc {rc}")
    finally:
        shutil.rmtree(d)


# ================================================================================================ I-7 ============
D2 = "TEST: labelled stand-in for the S5-2-D2 decision record (synthetic run; never an E0v-N result)"


def s5n_module():
    return CLIM.import_s5n()


@contextlib.contextmanager
def stub_s5n(spec=None):
    """the accepted check_m2s72_s5n.run_one() runs UNCHANGED; only the evaluations it calls that need a complete
    simulation output tree (Block B, I-2H, the per-UE adapter, SG-403, the MAC grammar census, MG-1) are replaced
    IN MEMORY by deterministic stand-ins that append rows of the same shape (the MAC log itself is read by the real
    m2s72_maclog: Q8-v runs for real on the synthetic log). The A-1 summary and per-UE A-1 harq
    records are computed for real by the frozen attribute_feedback() on the run's log. spec: {"status": {(id,
    subject): status}, "drop": [(id, subject)], "dup": [(id, subject)], "tamper": callable(runs, cfg)}"""
    spec = spec or {}
    S5N = s5n_module()
    E, I, A, S5V = S5N.E, S5N.I, S5N.A, S5N.S5V
    saved = {(S5N, "evaluation"): S5N.evaluation, (I, "i2h_rows"): I.i2h_rows,
             (A, "observe"): A.observe, (A, "validate"): A.validate, (S5V, "sg403_row"): S5V.sg403_row,
             (S5V, "grammar"): S5V.grammar, (S5V, "mg1_row"): S5V.mg1_row}
    st = spec.get("status", {})
    state = {}

    def status(i, subj, default="PASS"):
        return st.get((i, subj), st.get(i, default))

    def emit(rows):
        for r in rows:
            if (r[0], r[1]) in spec.get("drop", ()):
                continue
            S5N.rows.append(r)
            if (r[0], r[1]) in spec.get("dup", ()):
                S5N.rows.append(r)

    def evaluation(runs, cfg, opt, full):
        """the identities and multiplicities of the accepted B.evaluate(full=True, ref=None) at clock class Ca
        (m2s72_e0vn21.s5n_row_contract): f0_rows (F0-2 as "I-2", relabelled by the real i2h.relabel), i_rows, M2
        per slave, M3 / M3d per pair, M4 GM drift. One detail exceeds run_one's 400-character cut."""
        n = S5V.parse_name(cfg)[4]
        state["n"], state["name"], state["runs"], state["cfg"] = n, f"{cfg}-0", runs, cfg
        nm = state["name"]
        vec = os.path.join(runs, cfg, cfg, "vectors.vec")
        if os.path.isfile(vec):                                  # a consumed run file, as Run72 reads its vectors
            state["vec"] = open(vec, "rb").read()
        rows = [(i, nm, status(i, nm), "F0 stand-in") for i in ("F0-1", "I-2", "F0-3", "F0-4", "F0-5", "F0-7d", "F0-6", "F0-8")]
        rows += [("I-1", nm, status("I-1", nm), "I-1 stand-in"), ("I-3", nm, status("I-3", nm), "I-3 stand-in; " + "x" * 600)]
        rows += [("M2", f"{nm} slave {k}", status("M2", f"{nm} slave {k}"), "M2 stand-in") for k in range(n)]
        for i in range(n):
            for j in range(i + 1, n):
                rows += [(t, f"{nm} pair ({i},{j})", status(t, f"{nm} pair ({i},{j})"), f"{t} stand-in") for t in ("M3", "M3d")]
        rows += [("M4", f"{nm} GM drift", status("M4", f"{nm} GM drift"), "M4 stand-in")]
        emit(rows + spec.get("extra_rows", []))
        if "tamper" in spec:
            spec["tamper"](runs, cfg)
        return {}, "q0", f"M2S72-H-q0-Ca-n{n}", n

    def i2h_rows(ev):
        nm = state["name"]
        emit([("I-2H", f"{nm} DS-TT {k}", status("I-2H", f"{nm} DS-TT {k}"), "I-2H stand-in") for k in range(state["n"])])

    def observe(ev, mlp, aopt, loaded, nproc=16):
        nm = state["name"]
        emit([("Q8", f"{nm} UE {k}", status("Q8", f"{nm} UE {k}"), "per-UE Q8 stand-in (gptp -> q8_rows)") for k in range(state["n"])])
        if "tamper_late" in spec:
            spec["tamper_late"](state["runs"], state["cfg"])
        events = PA.harq_events(mlp)
        per, summ = P.attribute_feedback(events, nproc)
        obs = []
        for k in range(state["n"]):
            node = 2049 + k
            h = per.get(node, {"inserts": 0, "feedback": 0, "nack": 0, "delays_ps": [], "occupancy": None})
            obs.append({"k": k, "node": node, "T": 12 * P.S, "t0": 2 * P.S, "loaded_dl": loaded[k][0], "loaded_ul": loaded[k][1],
                        "dl": None, "ul": None, "mac": None, "gptp": None, "clock": None,
                        "harq": {"processes": nproc, **{x: h[x] for x in ("inserts", "feedback", "nack", "occupancy")},
                                 "feedback_delay_ps": sorted(set(h["delays_ps"]))}})
        totals = {"dl_grant_bytes": 0, "harq_inserts": sum(1 for e in events if e[0] == "ins")}
        state["summ"], state["obs_harq"] = summ, {o["k"]: o["harq"] for o in obs}
        return obs, totals, summ

    def validate(obs, totals, summ, expected):
        n = len(expected)
        pu4 = next(r for r in P.structural_rows([], [], summ, None) if r[0] == "PU-4")
        rows = [("PU-1", "run", status("PU-1", "run"), "stand-in")]
        rows += [(i, f"UE {k}", status(i, f"UE {k}"), "stand-in") for i in ("PU-2", "PU-3") for k in range(n)]
        rows += [pu4, ("PU-5", "run", status("PU-5", "run"), "stand-in")]
        rows += [(i, f"UE {k}", status(i, f"UE {k}"), "stand-in") for i in ("AV-1", "AV-2", "AV-3") for k in range(n)]
        out = []
        for r in rows:
            if (r[0], r[1]) in spec.get("drop", ()):
                continue
            out.append(r)
            if (r[0], r[1]) in spec.get("dup", ()):
                out.append(r)
        return out

    S5N.evaluation = evaluation
    I.i2h_rows = i2h_rows
    A.observe, A.validate = observe, validate
    S5V.sg403_row = lambda name, runs, cfg: emit([("SG-403", name, status("SG-403", name), "stand-in")])
    S5V.grammar = lambda mlp: ({("gnb", "H-ARQ TX"): 1}, {}, [], None)
    S5V.mg1_row = lambda name, mlog, removed: emit([("MG-1", name, status("MG-1", name), "stand-in")])
    old_env = os.environ.get("S5N_ADAPTER_VALIDATED")
    if spec.get("d2", True):
        os.environ["S5N_ADAPTER_VALIDATED"] = D2
    else:
        os.environ.pop("S5N_ADAPTER_VALIDATED", None)
    try:
        yield state
    finally:
        for (obj, name), v in saved.items():
            setattr(obj, name, v)
        if old_env is None:
            os.environ.pop("S5N_ADAPTER_VALIDATED", None)
        else:
            os.environ["S5N_ADAPTER_VALIDATED"] = old_env


def run_inproc(runs, rec, cfg=SYN_CFG, fresh=True, t0="1"):
    if fresh:
        CLIM._RUN_STARTED = False
    return cli_inproc(["run", runs, cfg, rec, "--t0", t0])


def sync_run(n_ue=2, sched=None, nack=None, ttis=40, ue_log=True):
    sched = sched or (lambda tti: [0] + ([1] if tti % 3 == 0 else []))
    if nack:
        lines, node, truth, T = nack_run(n_ue, sched, *nack, ttis=ttis, ue_log=ue_log)
    else:
        lines, node, truth = G.make(n_ue, ttis, sched, tail=40, ue_log=ue_log)
    return lines, node, truth


def load_records(rec, cfg=SYN_CFG):
    return (json.load(open(os.path.join(rec, f"{cfg}.s5n21.digest.json"))), json.load(open(os.path.join(rec, f"{cfg}.s5n21.json"))))


# ------------------------------------------------------------------------------------------- T-s5n-transparent --
@named("T-s5n-transparent")
def t_s5n_transparent():
    lines, node, truth = sync_run(nack=(1, 1))
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n() as stt:
        S5N = s5n_module()
        start = len(S5N.rows)
        with contextlib.redirect_stdout(io.StringIO()):
            rc_alone, dig_alone = S5N.run_one(runs, SYN_CFG, os.path.join(d, "alone"))
        alone_rows = list(S5N.rows[start:])
        before = file_digests([log, sca])
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        rec = os.path.join(d, "rec")
        check(rc in (0, 1, 3, 4) and os.path.isdir(rec) and not os.path.exists(rec + ".incomplete"), f"rc {rc}: {txt[-500:]}")
        for f in (f"{SYN_CFG}.check.txt", f"{SYN_CFG}.digest.json"):
            check(open(os.path.join(d, "alone", f), "rb").read() == open(os.path.join(rec, "s5n", f), "rb").read(),
                  f"s5n/{f} differs from a standalone check_m2s72_s5n.run() (byte comparison)")
        dig, out = load_records(rec)
        pu4_alone = next(r for r in alone_rows if r[0] == "PU-4")
        check(dig["historical"]["a1"]["pu4_row"] == list(pu4_alone) and out["historical"]["pu4"]["status"] == pu4_alone[2]
              and out["historical"]["pu4"]["detail"] == pu4_alone[3], "the s5n PU-4 row verbatim")
        check(out["s5n"]["rows"] == [list(r) for r in alone_rows], "the wrapper's s5n rows = the standalone rows")
        check(file_digests([log, sca]) == before, "inputs modified")
        sums = open(os.path.join(rec, "SHA256SUMS")).read().splitlines()
        listed = sorted(l_.split("  ", 1)[1] for l_ in sums)
        files = sorted(os.path.relpath(os.path.join(dp, f), rec) for dp, _, fn in os.walk(rec) for f in fn if f != "SHA256SUMS")
        check(listed == files and all(hashlib.sha256(open(os.path.join(rec, l_.split("  ", 1)[1]), "rb").read()).hexdigest() == l_.split("  ")[0]
                                      for l_ in sums), "SHA256SUMS covers every record")
        check(sorted(os.listdir(rec)) == sorted(["s5n", "SHA256SUMS", f"a21-{SYN_CFG}.txt", f"a21-{SYN_CFG}.json", f"{SYN_CFG}.s5n21.txt",
                                                  f"{SYN_CFG}.s5n21.json", f"{SYN_CFG}.s5n21.digest.json"]), f"records {os.listdir(rec)}")


# ------------------------------------------------------------------------------------------------- T-s5n-rows ---
@named("T-s5n-rows")
def t_s5n_rows():
    lines, node, truth = sync_run(nack=(1, 1))
    N_ = f"{SYN_CFG}-0"
    cases = [("PU-3 of UE 1 missing", {"drop": [("PU-3", "UE 1")]}, "PU-3 | UE 1"),
             ("AV-2 of UE 0 missing", {"drop": [("AV-2", "UE 0")]}, "AV-2 | UE 0"),
             ("MG-1 missing", {"drop": [("MG-1", N_)]}, "MG-1 |"),
             ("SG-403 missing", {"drop": [("SG-403", N_)]}, "SG-403 |"),
             ("I-2H of DS-TT 1 missing", {"drop": [("I-2H", f"{N_} DS-TT 1")]}, "I-2H |"),
             ("historical PU-4 missing", {"drop": [("PU-4", "run")]}, "PU-4 | run"),
             ("historical PU-4 duplicated", {"dup": [("PU-4", "run")]}, "duplicated rows"),
             ("PU-1 duplicated", {"dup": [("PU-1", "run")]}, "duplicated rows"),
             # Block B (I7-R1)
             ("Block B F0-6 missing", {"drop": [("F0-6", N_)]}, "F0-6 |"),
             ("Block B I-2 strict missing", {"drop": [("I-2", N_)]}, "I-2 strict (info) |"),
             ("Block B M2 of slave 1 missing", {"drop": [("M2", f"{N_} slave 1")]}, "M2 |"),
             ("Block B M4 GM drift missing", {"drop": [("M4", f"{N_} GM drift")]}, "M4 |"),
             ("Q8 of UE 1 missing", {"drop": [("Q8", f"{N_} UE 1")]}, "Q8 |"),
             ("M3 / M3d pair missing although every M2 PASSes", {"drop": [("M3", f"{N_} pair (0,1)"), ("M3d", f"{N_} pair (0,1)")]},
              "M3 / M3d pairs are missing"),
             ("M3d without its M3", {"drop": [("M3", f"{N_} pair (0,1)")]}, "M3 / M3d pairs differ"),
             ("an unexpected M4 TT clocks row (clock class Ca)", {"extra_rows": [("M4", f"{N_} TT clocks", "PASS", "x")]}, "unexpected rows"),
             ("an unexpected I-5 row (ref None)", {"extra_rows": [("I-5", N_, "PASS", "x")]}, "unexpected rows"),
             ("a pair outside the UEs", {"extra_rows": [("M3", f"{N_} pair (0,2)", "PASS", "x"), ("M3d", f"{N_} pair (0,2)", "PASS", "x")]},
              "unexpected rows"),
             ("Block B F0-3 duplicated", {"dup": [("F0-3", N_)]}, "duplicated rows"),
             ("EOR not NOT APPLICABLE", {"status": {"EOR": "PASS"}}, "EOR")]
    for what, spec, token in cases:
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n(spec):
            if what == "EOR not NOT APPLICABLE":
                S5N = s5n_module()
                orig_add = S5N.E.add
                S5N.E.add = lambda row, run, st_, det: orig_add(row, run, "PASS" if row == "EOR" else st_, det)
            rec = os.path.join(d, "rec")
            try:
                rc, txt = run_inproc(runs, rec)
            finally:
                if what == "EOR not NOT APPLICABLE":
                    S5N.E.add = orig_add
            check(rc == 2 and "EVALUATION ERROR" in txt and "row contract" in txt and token in txt, f"{what}: rc {rc}: {txt[:400]}")
            check(not os.path.exists(rec) and os.path.isdir(rec + ".incomplete"), f"{what}: a partial record must not look complete")
    # conditional rows: a FAILing M2 (its slave's evaluation raised) may leave pairs absent; the run FAILs on M2
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n({"status": {("M2", f"{N_} slave 1"): "FAIL"},
                                                                          "drop": [("M3", f"{N_} pair (0,1)"), ("M3d", f"{N_} pair (0,1)")]}):
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
        check(rc == 1 and "M2" in dig["correctness"]["verdict"]["gate_failures"], f"M2 FAIL without pairs: rc {rc}")
    # a changed detail field in check.txt (same length): the written rows differ from the evaluated rows
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        S5N = s5n_module()
        orig = S5N.run_one

        def edited(runs_, cfg_, recdir_):
            rc_, dg_ = orig(runs_, cfg_, recdir_)
            p_ = os.path.join(recdir_, f"{cfg_}.check.txt")
            t_ = open(p_).read()
            open(p_, "w").write(t_.replace("I-3 stand-in; xxxx", "I-3 stand-in; xxXx", 1))
            return rc_, dg_
        S5N.run_one = edited
        try:
            rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        finally:
            S5N.run_one = orig
        check(rc == 2 and "check.txt rows differ" in txt and "I-3" in txt, f"a changed detail: rc {rc}: {txt[:300]}")
    # the library check on its own (I7-R1)
    info, ne = W.s5n_info()
    nm = "M2S72-E0vN-q0-one0-n2-f1-0"
    rows = [(i, nm, "PASS", "d") for i in W.S5N_ONCE_NAME if i != "EOR"] + [("EOR", nm, W.NA, "e")]
    rows += [(i, "run", "PASS", "d") for i in W.S5N_ONCE_RUN] + [(i, f"UE {k}", "PASS", "d") for i in W.S5N_PER_UE for k in range(2)]
    rows += [("M2", f"{nm} slave {k}", "PASS", "d") for k in range(2)] + [("I-2H", f"{nm} DS-TT {k}", "PASS", "d") for k in range(2)]
    rows += [("Q8", f"{nm} UE {k}", "PASS", "d") for k in range(2)] + [("M4", f"{nm} GM drift", "PASS", "d")]
    rows += [("M3", f"{nm} pair (0,1)", "PASS", "y" * 450), ("M3d", f"{nm} pair (0,1)", "PASS", "d")]
    txt_ok = "header\n\nCORRECTNESS (gates)\n" + W.s5n_written_block(rows) + "\nper-run verdict: PASS\n\nPERFORMANCE\n"
    dg = {"numUe": 2, "correctness": {"rows": len(rows), "gate_failures": [], "per_ue_not_evaluated": []}}
    check(W.check_s5n_rows(rows, 2, SYN_CFG, txt_ok, dg, info, ne) == "PASS", "the contract on a complete row set")
    check(len(W.s5n_row_contract(SYN_CFG, 2)[0]) == 34 and len(W.s5n_row_contract(SYN_CFG, 4)[0]) == 14 + 3 + 5 * 4 + 3 * 4 + 1
          and len(W.s5n_row_contract(SYN_CFG, 4)[1]) == 12 and W.s5n_row_contract(SYN_CFG, 1)[1] == set(), "contract sizes")
    check("y" * 400 + "\n" in W.s5n_written_block(rows) and "y" * 401 not in W.s5n_written_block(rows), "the 400-character cut")
    bad = {"a full-length detail written": (rows, txt_ok.replace("y" * 400, "y" * 450), dg),
           "a detail changed": (rows, txt_ok.replace("| d\n", "| D\n", 1), dg),
           "rows reordered": (rows[1:] + rows[:1], txt_ok, dg),
           "digest count": (rows, txt_ok, dict(dg, correctness=dict(dg["correctness"], rows=len(rows) + 1))),
           "digest gate list": (rows, txt_ok, dict(dg, correctness=dict(dg["correctness"], gate_failures=["F0-3"]))),
           "verdict line": (rows, txt_ok.replace("per-run verdict: PASS", "per-run verdict: FAIL PU-4"), dg),
           "an unknown status": ([(r[0], r[1], "OK", r[3]) if r[0] == "F0-3" else r for r in rows], txt_ok, dg),
           "no CORRECTNESS section": (rows, "nothing", dg), "numUe": (rows, txt_ok, dict(dg, numUe=3))}
    for what, (r_, t_, d_) in bad.items():
        try:
            W.check_s5n_rows(r_, 2, SYN_CFG, t_, d_, info, ne)
            raise AssertionError(f"check_s5n_rows accepted: {what}")
        except W.EvaluationError:
            pass
    # s5n gate semantics carried into the composed verdict: a Block B FAIL gates, Q8-v-like NE does not, PU-4 never
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n({"status": {"F0-3": "FAIL", "I-2": "FAIL"}}):
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
        v = dig["correctness"]["verdict"]
        check(rc == 1 and v["status"] == "FAIL" and "F0-3" in v["gate_failures"], f"a Block B FAIL must fail the run: {v}")
        check("I-2 strict (info)" not in v["gate_failures"] and "I-2" not in v["gate_failures"],
              f"F0-2 -> I-2 strict (info) is informational (relabelled by the accepted i2h.relabel): {v}")
        check(any(r[0] == "I-2 strict (info)" and r[2] == "FAIL" for r in out["s5n"]["rows"]), "the relabelled row is reported")
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n({"status": {"F0-1": "FAIL", "AV-3": W.NE}}):
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
        v = dig["correctness"]["verdict"]
        check("F0-1 (info)" not in v["gate_failures"] and "AV-3" in v["gate_not_evaluated"] and v["status"] == "INCOMPLETE",
              f"F0-1 (info) informational, AV-3 NE gating: {v}")
    same = sync_run(sched=lambda tti: [0, 1])
    with synthetic_runs(*same) as (d, runs, log, sca), stub_s5n():
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
        v = dig["correctness"]["verdict"]
        check(dig["historical"]["a1"]["pu4_row"][2] == "FAIL" and "PU-4" not in v["gate_failures"] + v["gate_not_evaluated"]
              and dig["correctness"]["s5n"]["verdict_line"].startswith("FAIL") and "PU-4" in dig["correctness"]["s5n"]["verdict_line"],
              f"the historical PU-4 FAIL is reported (s5n verdict line kept) and never gates: {v}")
        check(v["status"] == "HELD FOR REVIEW" and rc == 3, f"same-TTI N = 2 with every gate PASS: {v}")


# ------------------------------------------------------------------------------------------- T-digest-ownership --
@named("T-digest-ownership")
def t_digest_ownership():
    lines, node, truth = sync_run(sched=lambda tti: [0, 1])          # A-1 ambiguous; A-2.1 exact
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n() as stt:
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        rec = os.path.join(d, "rec")
        dig, out = load_records(rec)
        s5 = json.load(open(os.path.join(rec, "s5n", f"{SYN_CFG}.digest.json")))
    check(W.validate_digest(dig) == [], f"digest schema {W.validate_digest(dig)[:3]}")
    for f in ("config", "kind", "option", "placement", "numUe", "harq16", "dl_factor", "mac_grammar_census"):
        check(dig[f] == s5[f], f"{f} not copied from the s5n digest")
    check(dig["performance"]["across"] == s5["performance"]["across"] and dig["performance"]["totals"] == s5["performance"]["totals"], "across / totals")
    for k, (m, m5) in enumerate(zip(dig["performance"]["per_ue"], s5["performance"]["per_ue"])):
        check("harq" not in m and {x: v for x, v in m.items() if x != "harq_a21"} == {x: v for x, v in m5.items() if x != "harq"},
              f"UE {k}: current s5n fields verbatim, no A-1 'harq'")
        check(dig["historical"]["a1"]["per_ue_harq"][str(k)] == m5["harq"], f"UE {k}: A-1 harq only under historical, verbatim")
    check(dig["historical"]["a1"]["harq_attribution"] == s5["performance"]["harq_attribution"], "A-1 summary verbatim")
    # the current values are A-2.1's (= generator truth), not A-1's (ambiguous here)
    tp = truth_per_node(truth)
    for k, m in enumerate(dig["performance"]["per_ue"]):
        n_ = 2049 + k
        c = m["harq_a21"]["counts"]
        check(c["available"] and c["feedback"] == tp[n_]["feedback"] and c["inserts"] == len(tp[n_]["pids"]), f"UE {k} counts {c}")
        check(dig["historical"]["a1"]["per_ue_harq"][str(k)]["feedback"] != c["feedback"], "A-1 differs here (ambiguous): never substituted")
        check(m["harq_a21"]["occupancy"]["available"] and m["harq_a21"]["simu5g"]["available"], "occupancy / Simu5G available with PASS gates")
    a = dig["performance"]["across_harq_a21"]
    check(all(v["available"] for v in a.values()) and a["harq_error_rate"]["n"] == 2, f"across available: {a}")
    # unavailable values: no UE-side lines -> PU-4h NE -> no counts, no occupancy, no across value; never 0, never A-1
    lines, node, truth = sync_run(sched=lambda tti: [0, 1], ue_log=False)
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
    check(rc == 4 and W.validate_digest(dig) == [], f"rc {rc}")
    for m in dig["performance"]["per_ue"]:
        for g in ("counts", "occupancy", "simu5g"):
            check(set(m["harq_a21"][g]) == {"available", "reason"} and m["harq_a21"][g]["available"] is False, f"{g}: {m['harq_a21'][g]}")
    check(all(v == {"available": False, "missing_ues": [0, 1]} for v in dig["performance"]["across_harq_a21"].values()), "all-or-nothing")
    # one UE without Simu5G statistics: its simu5g group unavailable, its counts still available; aggregates of counts available
    lines, node, truth = sync_run(nack=(1, 1))
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        keep = [l_ for l_ in open(sca).read().splitlines(True) if not l_.startswith(f"scalar {W.ue_module(1)} ")]
        open(sca, "w").writelines(keep)
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
    u = dig["performance"]["per_ue"]
    check(u[1]["harq_a21"]["simu5g"]["available"] is False and u[0]["harq_a21"]["simu5g"]["available"] and u[1]["harq_a21"]["counts"]["available"],
          "per-UE availability")
    check(rc == 4 and "A2-8u" in dig["correctness"]["verdict"]["gate_not_evaluated"], "A2-8u NE gates")
    # the library's all-or-nothing rule on its own
    g_ok = {"counts": {"available": True, "harq_error_rate": 0.1, "harq_tx_attempts": 1.1, "retransmissions": 2},
            "occupancy": {"available": True, "occupancy": {"busy_at_tti_start_hist": {"0": 3, "1": 1}}}}
    g_none = {"counts": {"available": True, "harq_error_rate": None, "harq_tx_attempts": None, "retransmissions": 0},
              "occupancy": {"available": False, "reason": "x"}}
    a = W.across_harq_a21([g_ok, g_none, g_ok])
    check(a["harq_error_rate"] == {"available": False, "missing_ues": [1]} and a["retransmissions"]["available"]
          and a["retransmissions"]["n"] == 3 and a["occupancy_busy_mean"] == {"available": False, "missing_ues": [1]}, f"{a}")


# --------------------------------------------------------------------------------------- T-one-run-per-process ---
@named("T-one-run-per-process")
def t_one_run_per_process():
    lines, node, truth = sync_run(nack=(1, 1))
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        rc1, _ = run_inproc(runs, os.path.join(d, "r1"))
        rc2, txt = run_inproc(runs, os.path.join(d, "r2"), fresh=False)
        check(rc1 in (0, 1, 3, 4) and rc2 == 2 and "one run per process" in txt and not os.path.exists(os.path.join(d, "r2"))
              and not os.path.exists(os.path.join(d, "r2.incomplete")), f"second run: rc {rc2}")
    check(CLIM._RUN_STARTED is True, "the flag stays set for the process")
    CLIM._RUN_STARTED = False


# ---------------------------------------------------------------------------------------------- T-no-d2-bypass ---
@named("T-no-d2-bypass")
def t_no_d2_bypass():
    # production files: never set, synthesize or default the decision variable
    for f in ("m2s72_e0vn21.py", "check_m2s72_s5n21.py"):
        src = open(os.path.join(HERE, f)).read()
        for pat in (r"environ\[\s*[\"']S5N_ADAPTER_VALIDATED[\"']\s*\]\s*=", r"setdefault\(\s*[\"']S5N_ADAPTER_VALIDATED",
                    r"putenv\(\s*[\"']S5N_ADAPTER_VALIDATED", r"S5N_ADAPTER_VALIDATED\s*=", r"environ\.update\(",
                    r"__setitem__\(\s*[\"']S5N_ADAPTER_VALIDATED"):
            check(not re.findall(pat, src), f"{f}: assignment of S5N_ADAPTER_VALIDATED ({pat})")
    # this suite: only the labelled TEST stand-in D2, a test value under examination, or the restored prior value
    src = open(os.path.join(HERE, "test_m2s72_e0vn21.py")).read()
    for rhs in re.findall(r"environ\[\s*\"S5N_ADAPTER_VALIDATED\"\s*\]\s*=\s*([A-Za-z_]\w*)", src):
        check(rhs in ("D2", "val", "old_env"), f"the suite sets S5N_ADAPTER_VALIDATED to {rhs}")
    check(D2.startswith("TEST: labelled stand-in"), "the suite's stand-in is labelled")
    lines, node, truth = sync_run(nack=(1, 1))
    S5N = s5n_module()
    for val in (None, "", "   "):
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n({"d2": False}):
            if val is not None:
                os.environ["S5N_ADAPTER_VALIDATED"] = val
            calls = []
            orig = S5N.run_one
            S5N.run_one = lambda *a: calls.append(a) or orig(*a)
            try:
                rc, txt = run_inproc(runs, os.path.join(d, "rec"))
            finally:
                S5N.run_one = orig
            check(rc == 2 and "S5-2-D2" in txt and not calls and not os.path.exists(os.path.join(d, "rec"))
                  and not os.path.exists(os.path.join(d, "rec.incomplete")), f"S5N_ADAPTER_VALIDATED {val!r}: rc {rc}")
            with contextlib.redirect_stdout(io.StringIO()):
                rc5, dg = S5N.run_one(runs, SYN_CFG, os.path.join(d, "alone"))
            if val is None or val == "":
                check(rc5 == 2 and dg is None, "the accepted run_one refuses as well")
            else:
                # the accepted run_one accepts a whitespace-only value (os.environ.get is truthy); the wrapper does not
                check(rc5 != 2, "the accepted run_one's own (weaker) check, recorded as found")
    check(CLIM._RUN_STARTED is False or True, "")
    CLIM._RUN_STARTED = False
    # hrq never reads it
    check("S5N_ADAPTER_VALIDATED" not in CLIM.gather_hrq.__code__.co_consts, "hrq reads S5N_ADAPTER_VALIDATED")


# --------------------------------------------------------------------- NC-run: evidence, provenance, interruption -
@named("NC-run")
def nc_run():
    lines, node, truth = sync_run(nack=(1, 1))
    # incomplete A-2.1 evidence: A2-7 / A2-8 missing or inconsistent with their structured output
    orig_ev = A21.evaluate

    def patched(mut):
        def ev(*a, **k):
            res, rows, per, cov, extra, window = orig_ev(*a, **k)
            rows, extra = mut(list(rows), dict(extra))
            return res, rows, per, cov, extra, window
        return ev
    muts = {"A2-7 missing": lambda r, e: ([x for x in r if x[0] != "A2-7"], e),
            "A2-8 missing": lambda r, e: ([x for x in r if x[0] != "A2-8"], e),
            "A2-7 duplicated": lambda r, e: (r + [next(x for x in r if x[0] == "A2-7")], e),
            "A2-7 PASS without its reference": lambda r, e: (r, dict(e, xa=None)),
            "A2-8 PASS without compared statistics": lambda r, e: (r, dict(e, scalars=None)),
            "an unknown A-2.1 row": lambda r, e: (r + [("A2-10", "run", "PASS", "")], e),
            "an A-2.1 row with a held status": lambda r, e: ([(x[0], x[1], "HELD FOR REVIEW", x[3]) if x[0] == "A2-6" else x for x in r], e)}
    for what, m in muts.items():
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
            A21.evaluate = patched(m)
            try:
                rc, txt = run_inproc(runs, os.path.join(d, "rec"))
            finally:
                A21.evaluate = orig_ev
            check(rc == 2 and "EVALUATION ERROR" in txt and not os.path.exists(os.path.join(d, "rec")), f"{what}: rc {rc} {txt[:200]}")
    # provenance: a required file missing -> REFUSED; a run file changing during the evaluation -> EVALUATION ERROR
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        os.remove(sca)
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        check(rc == 2 and "REFUSED" in txt and "0.sca" in txt and not os.path.exists(os.path.join(d, "rec.incomplete")), f"no .sca: rc {rc}")
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), \
            stub_s5n({"tamper": lambda runs_, cfg_: open(os.path.join(runs_, cfg_, "vector.vec"), "w").write("x")}):
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        check(rc == 2 and "inventory changed" in txt and not os.path.exists(os.path.join(d, "rec")), f"changed run tree: rc {rc}")
    # interrupted record writing: the records dir never appears; <records dir>.incomplete is left, and refused next time
    for what, target in (("digest building", ("W", "composed_digest")), ("the final rename", ("os", "rename"))):
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
            mod = W if target[0] == "W" else os
            orig = getattr(mod, target[1])

            def boom(*a, **k):
                raise OSError(f"interrupted ({what})")
            setattr(mod, target[1], boom)
            try:
                rc, txt = run_inproc(runs, os.path.join(d, "rec"))
            finally:
                setattr(mod, target[1], orig)
            rec = os.path.join(d, "rec")
            check(rc == 2 and not os.path.exists(rec) and os.path.isdir(rec + ".incomplete"), f"{what}: rc {rc}")
            rc, txt = run_inproc(runs, rec)
            check(rc == 2 and "interrupted earlier evaluation" in txt and not os.path.exists(rec), f"{what}: a leftover staging dir is refused")
    # the composed digest's own schema check guards the published record
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        orig = W.harq_a21_groups
        W.harq_a21_groups = lambda *a: dict(orig(*a), counts={"available": False, "reason": "x", "feedback": 0})
        try:
            rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        finally:
            W.harq_a21_groups = orig
        check(rc == 2 and "own schema" in txt and not os.path.exists(os.path.join(d, "rec")), f"a zero-substituted unavailable value: rc {rc}")
    # the name guard and the arguments of run
    for args in (["run", "x", "M2S72-E0vN-q0-one0-n2-f1_A2V1", "r"], ["run", "x", "M2S72-E0v-q0-f1", "r"],
                 ["run", "x", SYN_CFG, "r", "--expect", F3_EXPECT], ["run", "x", SYN_CFG]):
        CLIM._RUN_STARTED = False
        old = os.environ.get("S5N_ADAPTER_VALIDATED")
        os.environ["S5N_ADAPTER_VALIDATED"] = D2
        try:
            rc, txt = cli_inproc(args)
        finally:
            os.environ.pop("S5N_ADAPTER_VALIDATED", None) if old is None else os.environ.__setitem__("S5N_ADAPTER_VALIDATED", old)
        check(rc == 2, f"{args}: rc {rc}")
    CLIM._RUN_STARTED = False


# ----------------------------------------------------------------------- I7-R2 / I7-R3: provenance and integrity --
def same_size_tamper(path):
    """change bytes of a file without changing its size or its timestamps (atime, mtime restored to the ns). This is
    an EXTERNAL modifier, not the evaluator: an active input tracker is paused so its reads are not consumption."""
    t = CLIM.InputTracker.active
    if t is not None:
        t.busy = True
    try:
        _same_size_tamper(path)
    finally:
        if t is not None:
            t.busy = False


def _same_size_tamper(path):
    st = os.stat(path)
    b = bytearray(open(path, "rb").read())
    k = next(i for i in range(len(b) - 1, -1, -1) if chr(b[i]).isdigit())
    b[k] = ord("1") if b[k] != ord("1") else ord("2")
    open(path, "r+b").write(bytes(b))
    os.utime(path, ns=(st.st_atime_ns, st.st_mtime_ns))
    st2 = os.stat(path)
    check(st2.st_size == st.st_size and st2.st_mtime_ns == st.st_mtime_ns, "tamper keeps size and mtime")


@named("NC-provenance")
def nc_provenance():
    lines, node, truth = sync_run(nack=(1, 1))
    # R2: a normal run records every required source and every local module it loaded, hashed
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
        vec = os.path.join(runs, SYN_CFG, SYN_CFG, "vectors.vec")
        open(vec, "w").write("vector 0 x\n1 2 3\n")
        rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        dig, out = load_records(os.path.join(d, "rec"))
    code = dig["inputs"]["code"]
    check(sorted(code["required"]) == sorted(CLIM.REQUIRED_S5N) and all(re.fullmatch(r"[0-9a-f]{64}", h) for h in code["required"].values()),
          "every required source hashed")
    for f in ("check_m2s72_s5n.py", "check_m2s72_b.py", "m2s72_a21.py", "m2s72_e0vn21.py", "check_m2s72_s5n21.py"):
        check(code["loaded"].get(f) == code["required"][f], f"loaded module {f} hashed")
    check(set(code["loaded"]) - set(code["required"]) <= {f for f in code["loaded"] if not f.startswith("test_")}, "loaded set")
    # R3: the consumed inputs, byte-level: the log, the .sca, a vector file the evaluation read, the Simu5G sources A2-0s read
    cs = dig["inputs"]["consumed_sha256"]
    check(f"runs:run-{SYN_CFG}.log.gz" in cs and f"runs:{SYN_CFG}/{SYN_CFG}/0.sca" in cs and f"runs:{SYN_CFG}/{SYN_CFG}/vectors.vec" in cs,
          f"consumed inputs {sorted(cs)[:6]}")
    check(any(k.startswith("simu5g:") for k in cs), "the Simu5G sources read by A2-0s are consumed inputs")
    check(cs[f"runs:{SYN_CFG}/{SYN_CFG}/0.sca"] == dig["inputs"]["sca_sha256"], "the .sca hash")
    check("NOT integrity" in out["inputs"]["run_tree_inventory"]["note"], "the inventory is labelled supplementary")
    # R2: a missing required source -> exit 2 before any evaluation; nothing published, no staging
    for mode in ("run", "hrq"):
        with synthetic_runs(lines, node, truth) as (d, runs, log, sca), stub_s5n():
            name = "REQUIRED_S5N" if mode == "run" else "REQUIRED_A21"
            orig = getattr(CLIM, name)
            setattr(CLIM, name, orig + ("m2s72_missing_source.py",))
            try:
                if mode == "run":
                    rc, txt = run_inproc(runs, os.path.join(d, "rec"))
                else:
                    rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d, "rec")])
            finally:
                setattr(CLIM, name, orig)
            check(rc == 2 and "required source files missing" in txt and "m2s72_missing_source.py" in txt
                  and not os.path.exists(os.path.join(d, "rec")) and not os.path.exists(os.path.join(d, "rec.incomplete")),
                  f"{mode}: missing source: rc {rc}: {txt[:200]}")
    # R3: a same-size, timestamp-preserving change of the .sca during the evaluation: the inventory does not see it,
    # the byte-level hashes do
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca):
        inv = {}

        def tamper(runs_, cfg_):
            inv["before"] = CLIM.tree_fingerprint(os.path.join(runs_, cfg_))
            same_size_tamper(os.path.join(runs_, cfg_, cfg_, "0.sca"))
            inv["after"] = CLIM.tree_fingerprint(os.path.join(runs_, cfg_))
        with stub_s5n({"tamper": tamper}):
            rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        check(inv["before"] == inv["after"], "size / mtime inventory unchanged by the tamper (it is not integrity)")
        check(rc == 2 and "sha256" in txt and not os.path.exists(os.path.join(d, "rec")), f"same-size .sca change: rc {rc}: {txt[:300]}")
    # R3: a consumed run file (read by the evaluation) changed later, same size and timestamps: its first-read hash
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca):
        vec = os.path.join(runs, SYN_CFG, SYN_CFG, "vectors.vec")
        open(vec, "w").write("vector 0 x\n1 2 3\n")
        with stub_s5n({"tamper_late": lambda runs_, cfg_: same_size_tamper(os.path.join(runs_, cfg_, cfg_, "vectors.vec"))}) as stt:
            rc, txt = run_inproc(runs, os.path.join(d, "rec"))
        check("vec" in stt and rc == 2 and "consumed files" in txt and "vectors.vec" in txt and not os.path.exists(os.path.join(d, "rec")),
              f"same-size consumed-file change: rc {rc}: {txt[:300]}")
    # R3 in hrq: the log changed after its first reading -> exit 2, nothing written
    with synthetic_runs(lines, node, truth) as (d, runs, log, sca):
        orig_he = PA.harq_events

        def he(path, *a, **k):
            out_ = orig_he(path, *a, **k)
            same_size_tamper(sca)
            return out_
        PA.harq_events = he
        try:
            rc, txt = cli_inproc(["hrq", runs, SYN_CFG, os.path.join(d, "rec")])
        finally:
            PA.harq_events = orig_he
        check(rc == 2 and "changed" in txt and not os.path.exists(os.path.join(d, "rec")), f"hrq: same-size change: rc {rc}")
    check(CLIM.InputTracker.active is None, "no tracker left active")
    CLIM._RUN_STARTED = False


# ================================================================================================ I-8 ============
import m2s72_harqfix as F  # noqa: E402  (frozen generator, ACK only; synthetic, labelled)

CONTROL_IDS = ["PC-unmodified", "NC-full-masquerade", "NC-swap", "NC-ue-relabel", "NC-occ-one-ue", "NC-dropfb", "NC-dupins",
               "NC-shift", "NC-node-map", "NC-no-ue-lines", "NC-c0-dup-pid", "NC-c0-malformed-ins", "NC-c0-malformed-fb",
               "NC-c0-malformed-timestamp", "NC-c0-same-count", "NC-c0-reorder", "NC-c0-node", "NC-occ-entry-missing",
               "NC-occ-invalid", "NC-scalar-ue1", "NC-scalar-missing-ue1", "NC-scalar-duplicate"]


def run_controls(lines, node, truth, sca=True):
    with synthetic_runs(lines, node, truth, sca=sca) as (d, runs, log, scap):
        files = [log] + ([scap] if scap else [])
        before = file_digests(files)
        rc, txt = cli_inproc(["controls", runs, SYN_CFG, os.path.join(d, "ctl"), "--t0", "1"])
        out = json.load(open(os.path.join(d, "ctl", f"controls-{SYN_CFG}.json")))
        check(file_digests(files) == before, "the controls modified an input")
        check(sorted(os.listdir(os.path.join(d, "ctl"))) == [f"controls-{SYN_CFG}.json", f"controls-{SYN_CFG}.txt"], "records")
        check(os.listdir(runs) == [f"run-{SYN_CFG}.log.gz", SYN_CFG] or sorted(os.listdir(runs)) == sorted([f"run-{SYN_CFG}.log.gz", SYN_CFG]),
              "nothing written beside the inputs")
    return rc, txt, out, {r["id"]: r for r in out["controls"]}


@named("T-controls")
def t_controls():
    # every control on a run where each is buildable: PASS, with its before / after evidence
    lines, node, truth = sync_run(nack=(1, 1))
    rc, txt, out, by = run_controls(lines, node, truth)
    check([r["id"] for r in out["controls"]] == CONTROL_IDS, f"control set {[r['id'] for r in out['controls']]}")
    bad = {k: (r["result"], r.get("observed")) for k, r in by.items() if r["result"] != "PASS"}
    check(rc == 0 and not bad, f"rc {rc}; not PASS: {bad}")
    for k, r in by.items():
        if k.startswith("NC-") and k != "NC-full-masquerade":
            check(r["mutation"] and r["mutation"] != "none" and all(v == "PASS" for v in r["baseline"].values()) and r["after"],
                  f"{k}: baseline / mutation / after evidence {r}")
    check(by["NC-c0-malformed-ins"]["after"]["C-0"] == "FAIL" and "R-0e" in by["NC-c0-malformed-ins"]["details"]["C-0"], "evidence")
    check(out["inputs"]["consumed_sha256"] and out["inputs"]["code_sha256"]["required"], "provenance recorded")
    # NOT BUILDABLE with a reason: N = 1 (no second UE) and no .sca
    l1, n1_, t1 = G.make(1, 40, lambda tti: [0], tail=40)
    with synthetic_runs(l1, n1_, t1, cfg="M2S72-E0vN-q0-one0-n1-f1") as (d, runs, log, scap):
        rc, txt = cli_inproc(["controls", runs, "M2S72-E0vN-q0-one0-n1-f1", os.path.join(d, "ctl"), "--t0", "1"])
        out = json.load(open(os.path.join(d, "ctl", "controls-M2S72-E0vN-q0-one0-n1-f1.json")))
    by = {r["id"]: r for r in out["controls"]}
    for k in ("NC-swap", "NC-ue-relabel", "NC-occ-one-ue", "NC-node-map", "NC-occ-entry-missing", "NC-scalar-ue1"):
        check(by[k]["result"] == "NOT BUILDABLE" and "N >= 2" in by[k]["observed"], f"N = 1: {k} {by[k]}")
    check(by["NC-full-masquerade"]["result"] == "NOT BUILDABLE" and by["NC-c0-malformed-ins"]["result"] == "PASS"
          and by["NC-shift"]["result"] == "PASS" and rc == 0, f"N = 1 buildable controls: rc {rc}")
    check(out["summary"] == {"PASS": 12, "FAIL": 0, "NOT BUILDABLE": 10, "exit": 0}, f"N = 1 summary {out['summary']}")
    rc, txt, out, by = run_controls(lines, node, truth, sca=False)
    for k in ("NC-scalar-ue1", "NC-scalar-missing-ue1", "NC-scalar-duplicate"):
        check(by[k]["result"] == "NOT BUILDABLE" and ("not PASS before the mutation" in by[k]["observed"] or ".sca" in by[k]["observed"]),
              f"no .sca: {k} {by[k]}")
    # a control counts only on a PASSing baseline: without UE lines, the A2-7-dependent controls are NOT BUILDABLE
    l2, n2_, t2 = sync_run(nack=(1, 1), ue_log=False)
    rc, txt, out, by = run_controls(l2, n2_, t2)
    for k in ("NC-swap", "NC-ue-relabel", "NC-no-ue-lines", "NC-occ-entry-missing", "NC-c0-malformed-ins"):
        check(by[k]["result"] == "NOT BUILDABLE" and "not PASS before the mutation" in by[k]["observed"], f"baseline guard {k}: {by[k]}")
    check(rc == 4 and out["summary"]["FAIL"] == 0, f"no mutation control buildable -> exit 4 (not a pass): rc {rc}")
    # sensitivity: each control FAILs when the mechanism it guards is broken (the controls are not vacuous)
    breaks = {
        "NC-c0-malformed-ins": (W, "token_census", lambda lines_: {"insert": sum(1 for x in lines_ if isinstance(x, str) and PR.R_INSERT.search(x)
                                                                                   and x.split("|")[1:2] == [W.GNB_MODULE]),
                                                                    "feedback": sum(1 for x in lines_ if isinstance(x, str) and PR.R_FB.search(x)
                                                                                    and x.split("|")[1:2] == [W.GNB_MODULE])}),
        "NC-scalar-duplicate": (W, "scalar_record_counts", lambda lines_: {}),
        "NC-occ-entry-missing": (W, "pu4o_local", (lambda orig: lambda k, n_k, per, x7: orig(k, n_k, per, dict(x7, occupancy_equal={
            **x7["occupancy_equal"], n_k: True})) if isinstance(x7, dict) and isinstance(x7.get("occupancy_equal"), dict) else orig(k, n_k, per, x7))(W.pu4o_local)),
        "NC-c0-same-count": (W, "c0_row", (lambda orig: lambda a1, res, cen: (dict(orig(a1, res, cen)[0], status="PASS", detail="patched"),
                                                                                orig(a1, res, cen)[1]))(W.c0_row)),
    }
    for cid, (mod, name, fake) in breaks.items():
        orig = getattr(mod, name)
        setattr(mod, name, fake)
        try:
            rc, txt, out, by = run_controls(lines, node, truth)
        finally:
            setattr(mod, name, orig)
        check(by[cid]["result"] == "FAIL" and rc == 1, f"{cid} did not detect a broken {name}: {by[cid]['result']} rc {rc}")


@named("T-n1-identity")
def t_n1_identity():
    """N = 1, ACK only, the FROZEN generator; (a) with UE lines, (b) without; .sca from the generator truth"""
    for with_ue in (True, False):
        lines, node, truth = F.make(1, 40, lambda tti: [0], ue_log=with_ue)
        r = pipe_full(lines, node, truth)
        a1_per, summ = P.attribute_feedback(r["a1"], 16, window=(1000 * MS, (r["res"]["t_end"] // MS + 1) * MS))
        pu4 = next(x for x in P.structural_rows([], [], summ, None) if x[0] == "PU-4")
        check(pu4[2] == "PASS" and summ["ambiguous"] == summ["orphan"] == summ["reinsert"] == 0, f"A-1 PU-4 {pu4}")
        o, h = r["per"][2049], a1_per[2049]
        check((o["inserts"], o["feedback"], o["nack"]) == (h["inserts"], h["feedback"], h["nack"]), f"A-2.1 counts = A-1's: {o} {h}")
        if with_ue:
            check(r["pu4h"]["status"] == "PASS" and S(r) == ["PASS"] and r["a28u"][0]["status"] == "PASS", "(a) gates PASS")
            check(o["occupancy"] == h["occupancy"] and r["x7"]["occupancy_equal"][2049] is True, "(a) occupancy = A-1's = the XA truth")
            check(r["verdict"]["status"] == "HELD FOR REVIEW" and HELD(r) == {"single-candidate ACK attribution"}, f"(a) {r['verdict']}")
        else:
            check(r["st"]["A2-7"] == W.NE and r["v"]["verdict_f1d_i"] == "A-2.1 INCOMPLETE" and r["pu4h"]["status"] == W.NE, "(b) PU-4h NE")
            check(S(r) == [W.NE] and r["locs"][0]["step"] == "1", "(b) PU-4o NE: no reference")
            check(r["a28u"][0]["status"] == W.NE and r["a28u"][0]["local"] == W.EQUAL and "global" in r["a28u"][0]["detail"],
                  f"(b) A2-8u NE by the global rule, local EQUAL: {r['a28u'][0]}")
            check(r["verdict"]["status"] == "INCOMPLETE" and r["verdict"]["exit"] == 4, f"(b) {r['verdict']}")


def git_unchanged(pin, paths):
    r = subprocess.run(["git", "-C", W.REPO, "cat-file", "-e", f"{pin}^{{commit}}"], capture_output=True)
    check(r.returncode == 0, f"pin {pin} not in this clone (tier-0 checks out the full history)")
    r = subprocess.run(["git", "-C", W.REPO, "diff", "--quiet", pin, "--"] + paths, capture_output=True)
    check(r.returncode == 0, f"{paths} differ from {pin}")


CHK_REL = "simulations/m2/check/"


@named("T-a1-frozen")
def t_a1_frozen():
    git_unchanged("fbee202", [CHK_REL + f for f in ("m2s72_a2.py", "check_m2s72_a2.py", "m2s72_a2probe.py", "m2s72_harqfix.py",
                                                    "m2s72_harqx.py", "m2s72_peru.py", "test_m2s72_a2.py")])
    git_unchanged("39a6434", [CHK_REL + "check_m2s72_a2v1.py"])


@named("T-a1-a21-pinned")
def t_a1_a21_pinned():
    git_unchanged("d920125", [CHK_REL + f for f in ("m2s72_a21.py", "check_m2s72_a21.py", "m2s72_harqfix21.py",
                                                    "m2s72_a21_fixture.py", "m2s72_a21_realchain.py")])


@named("T-a1-s5n-pinned")
def t_a1_s5n_pinned():
    git_unchanged("7bb0e3a", [CHK_REL + f for f in ("check_m2s72_s5n.py", "m2s72_peru_adapter.py", "check_m2s72_s5v.py",
                                                    "check_m2s72_s5n2.py", "m2s72s5_lib.py", "check_m2s72_e0.py", "check_m2s72_b.py",
                                                    "check_m2s72_i2h.py", "check_m2s72_f0.py", "check_m2s72_f0r2.py", "m2s72_maclog.py")]
                  + ["simulations/m2/m2s72s5.sh", "simulations/m2/m2s72s5.ini", "simulations/m2/m2s72a2v.ini", ".github",
                     CHK_REL + "fixtures"])


@named("T-registry-immutable")
def t_registry_immutable():
    """the committed registry is the one of increment I-1 (7e5c169): no admission was added since; the suite never
    writes it (main() also compares its sha256 before and after the whole suite)"""
    git_unchanged("7e5c169", [CHK_REL + "m2s72_fgo_registry.json"])
    check(W.load_registry()["admitted"] == ADMITTED, "nine admissions")


@named("T-expect-files")
def t_expect_files():
    """the declared expectation files (design 8): schema, configuration, known keys, the conditional forms preserved,
    and every key resolvable on a real record of the same shape. NO genuine run is evaluated here."""
    files = {"vn1.expect.json": ("M2S72-E0v-q0-f1", 1), "vn2.expect.json": ("M2S72-E0vN-q0-one0-n2-f1", 2),
             "vv1.expect.json": ("M2S72-E0vN-q0-one0-n2-f1_A2V1", 2), "f3.expect.json": ("f3-fixture", 2)}
    docs = {}
    for f, (cfg, n) in files.items():
        p = os.path.join(HERE, "expect", f)
        e = CLIM.load_expect(p, cfg)
        docs[f] = e
        check("never" in e["note"] or "deviation is a finding" in e["note"], f"{f}: note")
        check(e["expect"].get("verdict.status") in ("HELD FOR REVIEW", "INCOMPLETE"), f"{f}: declared verdict")
        try:
            CLIM.load_expect(p, "M2S72-E0vN-q0-one0-n4-f1")
            raise AssertionError(f"{f} accepted for another configuration")
        except CLIM.ExpectationError:
            pass
    v1, v2, vv = (docs[f]["expect"] for f in ("vn1.expect.json", "vn2.expect.json", "vv1.expect.json"))
    check(v1["a21.rows.A2-5"] == {"any_of": ["PASS", "NOT EXERCISED"]} and v1["verdict.held_features_if_exercised"] ==
          ["end-of-run censoring: inserted in the last TTI"], "V-N1 conditional forms (design 8.2)")
    check(v1["a1.summary.a1a"] == 11697 and v2["a1.summary.a1a"] == 9718 and v2["a1.summary.a1b"] == 2476
          and v2["a1.summary.ambiguous"] == 768 and v2["a1.pu4_status"] == "FAIL", "A-1 values of the records")
    check(v2["coverage.single-candidate ACK attribution"] == 12194 and v2["a21.exchangeable_groups"] == 384, "V-N2 declared A-2 counts")
    check(vv["per_ue.2050.nack"] == 144 and vv["per_ue.2049.inserts"] == 11702 and vv["a21.exchangeable_groups"] == 371
          and vv["a21.handles_by_state"] == {"retired": 129} and vv["a28u.UE 1.harqTxAttemptsDl:mean"] == 1.1139240506329113
          and vv["a21.verdict_full"] == "A-2.1 INCOMPLETE" and vv["verdict.held_features_if_exercised"] == ["NACK resolved: single candidate"],
          "V-V1 = S1 closure tables (design 8.4)")
    check(not any(k.startswith("a1.") for k in vv), "V-V1 declares no A-1 value")
    # every declared key resolves on a real hrq record of the same shape (synthetic run; values naturally differ)
    for f, (lines, node, truth, cfg) in {"vn1.expect.json": (*G.make(1, 30, lambda tti: [0], tail=40), "M2S72-E0v-q0-f1"),
                                         "vn2.expect.json": (*sync_run(sched=lambda tti: [0, 1]), "M2S72-E0vN-q0-one0-n2-f1"),
                                         "vv1.expect.json": (*sync_run(nack=(1, 1)), "M2S72-E0vN-q0-one0-n2-f1_A2V1")}.items():
        with synthetic_runs(lines, node, truth, cfg=cfg) as (d, runs, log, sca):
            rc, txt = cli_inproc(["hrq", runs, cfg, os.path.join(d, "rec"), "--t0", "1"])
            out = json.load(open(os.path.join(d, "rec", f"hrq-{cfg}.json")))
        unresolved = [k for k in docs[f]["expect"] if k != "verdict.held_features_if_exercised"
                      and CLIM.evaluated_value(k, out) == CLIM.ABSENT]
        check(not unresolved, f"{f}: keys without a value on a real record: {unresolved}")


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
            check("check_m2s72_s5n21.py hrq" in r.stdout or "REFUSED: S5N_ADAPTER_VALIDATED is not set" in r.stdout,
                  f"CLI output {r.stdout[:200]}")
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
