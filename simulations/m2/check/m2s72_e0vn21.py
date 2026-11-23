#!/usr/bin/env python3
"""WP-A1: composition of the unchanged E0v-N per-run evaluation with the accepted A-2.1 H-ARQ evaluation (library).

Implementation contract: docs/migration/wp-a1-a21-e0vn-wrapper-design.md, revision 2.1 (57a80ca), section 9.
This file holds increment I-1 only:
  - the status vocabulary (design 4.0) and the exit codes (4.8, 5.1);
  - the first-genuine-occurrence registry: loading, structural validation, evidence validation (4.7, 4.7.1);
  - the wrapper-local configuration name guard (5.2);
  - the initial schema definitions and their validation (5.3);
  - isolated import handling: this directory is put on sys.path before any local import, so the module imports
    under `python3 -I` (which does not add the script directory to sys.path).
MAP-UE, C-0, PU-4h, PU-4o, A2-8u, the FGO flag, the verdict composition and the CLI modes are later increments
(I-2 .. I-8) and are deliberately absent.

Pure functions. Never writes a file. Reads only the registry and the result records the registry cites. The frozen
and accepted modules are imported read-only and are never modified.
"""
import hashlib
import json
import math
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import m2s72_a21 as A21  # noqa: E402  (accepted, d920125; read-only)

REPO = os.path.normpath(os.path.join(HERE, "..", "..", ".."))
REGISTRY_PATH = os.path.join(HERE, "m2s72_fgo_registry.json")

# ------------------------------------------------------------------------------------------- status vocabulary ---
PASS, FAIL = "PASS", "FAIL"
NE, NX = A21.NE, A21.NX                       # "NOT EVALUATED", "NOT EXERCISED": the accepted A-2.1 strings
NA = "NOT APPLICABLE"
HR = "HELD FOR REVIEW"
ROW_STATUSES = (PASS, FAIL, NE, NX, NA, HR)

# local comparison outcome of a per-UE row (design 4.0); the row status additionally applies the global rules
EQUAL, DIFFERENT, NOT_COMPARED = "EQUAL", "DIFFERENT", "NOT COMPARED"
LOCAL_OUTCOMES = (EQUAL, DIFFERENT, NOT_COMPARED)

# composed verdicts and exit codes (design 4.8; 5 is the --expect mismatch of 5.1)
V_PASS, V_FAIL, V_INCOMPLETE, V_HELD = "PASS", "FAIL", "INCOMPLETE", HR
V_REFUSED, V_ERROR = "REFUSED", "EVALUATION ERROR"
EXIT = {V_PASS: 0, V_FAIL: 1, V_REFUSED: 2, V_ERROR: 2, V_HELD: 3, V_INCOMPLETE: 4}
EXIT_EXPECT_MISMATCH = 5
PRECEDENCE = (V_ERROR, V_REFUSED, V_FAIL, V_INCOMPLETE, V_HELD, V_PASS)   # 2 > 1 > 4 > 3 > 0 (D-A1-11)

# the A-2.1 verdict strings (m2s72_a21.verdict)
A21_VERDICTS = tuple(f"{A21.VERSION} {x}" for x in ("VALID", "INCOMPLETE", "NOT VALID"))

# row ids of the wrapper (design 3.1); per-UE rows carry a local comparison outcome
ROW_MAP, ROW_C0, ROW_PU4H, ROW_PU4O, ROW_A28U = "MAP-UE", "C-0", "PU-4h", "PU-4o", "A2-8u"
WRAPPER_ROWS = (ROW_MAP, ROW_C0, ROW_PU4H, ROW_PU4O, ROW_A28U)
PER_UE_ROWS = (ROW_PU4O, ROW_A28U)


class Refused(Exception):
    """input refused before evaluation (exit 2)"""


class EvaluationError(Exception):
    """an evaluation that cannot complete; never a PASS (exit 2)"""


# ------------------------------------------------------------------------------------------------ name guard ----
# design 5.2 (D-A1-8): wrapper-local; check_m2s72_s5v.parse_name is accepted code and is not changed
RUN_NAME = re.compile(r"^M2S72-E0vN(H5)?-(q0|q0p|qdu|qde)-(one0|sym)-n(1|2|4|8)-f(0p5|0p8|1|1p25|1p6|2)$")
HRQ_EXTRA = ("M2S72-E0v-q0-f1",                    # V-N1 (N = 1 smoke)
             "M2S72-E0vN-q0-one0-n2-f1_A2V1")      # V-V1 (the sealed A2-V1 run)


def run_name_ok(cfg):
    return isinstance(cfg, str) and RUN_NAME.fullmatch(cfg) is not None


def hrq_name_ok(cfg):
    return run_name_ok(cfg) or cfg in HRQ_EXTRA


def guard(cfg, mode):
    """raises Refused unless cfg is admissible for mode ('run' or 'hrq'); returns cfg"""
    if mode == "run":
        ok = run_name_ok(cfg)
    elif mode == "hrq":
        ok = hrq_name_ok(cfg)
    else:
        raise Refused(f"unknown mode {mode!r} for the name guard")
    if not ok:
        raise Refused(f"{cfg!r}: not admissible for '{mode}' (wrapper name guard, design 5.2)")
    return cfg


# ------------------------------------------------------------------------------------------------- registry -----
REGISTRY_SCHEMA = "m2s72-fgo-registry/1"
STRENGTHS = ("E1", "E2", "I", "N")
GENUINE = ("explicit", "inferred-only", "not-exercised")
RESULTS_DIR = "simulations/m2/results/"
FEATURE_KEYS = {"name", "admitted", "genuine", "strength", "evidence", "note"}
FEATURE_OPTIONAL = {"definition"}
EVIDENCE_KEYS = {"record", "section", "contract", "scope", "statement"}
DEFINITION_KEYS = {"record", "section", "statement"}


def coverage_names():
    """the 18 feature names of the accepted m2s72_a21.coverage(), in its order, taken from the function itself (on an
    empty replay result: no count, no row), so a renamed or added feature is detected"""
    empty = {"groups": [], "pdus": {}, "fb": [], "counts": {}}
    return [name for name, _, _ in A21.coverage(empty, [])]


def _record_text(rel):
    p = os.path.normpath(os.path.join(REPO, rel))
    if not p.startswith(os.path.join(REPO, "")) or not os.path.isfile(p):
        raise EvaluationError(f"registry: cited record {rel!r} is not a file in the repository")
    return open(p, encoding="utf-8").read()


def record_status(text):
    """the record's status line: the first line starting with '**Status'"""
    for line in text.splitlines():
        if line.startswith("**Status"):
            return line
    return None


def closed_accepted(text):
    s = record_status(text)
    return s is not None and "CLOSED" in s and "ACCEPTED" in s and "NOT ACCEPTED" not in s


def validate_registry(reg, names=None):
    """structural and evidence validation (design 4.7 / 4.7.1). Returns the list of problems (empty = valid)."""
    names = coverage_names() if names is None else names
    probs = []
    if not isinstance(reg, dict) or set(reg) != {"schema", "features"}:
        return [f"top level must be exactly {{schema, features}}, got {sorted(reg) if isinstance(reg, dict) else type(reg).__name__}"]
    if reg["schema"] != REGISTRY_SCHEMA:
        probs.append(f"schema {reg['schema']!r} != {REGISTRY_SCHEMA!r}")
    fs = reg["features"]
    if not isinstance(fs, list):
        return probs + ["features must be a list"]
    got = [f.get("name") if isinstance(f, dict) else None for f in fs]
    if got != names:
        probs.append(f"feature names differ from m2s72_a21.coverage() (order included): missing "
                     f"{[n for n in names if n not in got]}, unknown {[n for n in got if n not in names]}, "
                     f"duplicates {sorted({n for n in got if got.count(n) > 1}, key=str)}")
    texts = {}
    for i, f in enumerate(fs):
        where = f"feature {i + 1} {f.get('name') if isinstance(f, dict) else f!r}"
        if not isinstance(f, dict):
            probs.append(f"{where}: not an object")
            continue
        keys = set(f)
        if not FEATURE_KEYS <= keys or not keys <= FEATURE_KEYS | FEATURE_OPTIONAL:
            probs.append(f"{where}: keys {sorted(keys)}; required {sorted(FEATURE_KEYS)}, optional {sorted(FEATURE_OPTIONAL)}")
            continue
        if not isinstance(f["admitted"], bool):
            probs.append(f"{where}: admitted must be true or false")
        if f["strength"] not in STRENGTHS:
            probs.append(f"{where}: strength {f['strength']!r} not in {STRENGTHS}")
        if f["genuine"] not in GENUINE:
            probs.append(f"{where}: genuine {f['genuine']!r} not in {GENUINE}")
        if not isinstance(f["note"], str):
            probs.append(f"{where}: note must be text")
        if not isinstance(f["evidence"], list):
            probs.append(f"{where}: evidence must be a list")
            continue
        consistent = {"E1": "explicit", "E2": "explicit", "I": "inferred-only", "N": "not-exercised"}
        if f["strength"] in consistent and f["genuine"] != consistent[f["strength"]]:
            probs.append(f"{where}: genuine {f['genuine']!r} inconsistent with strength {f['strength']}")
        if f["admitted"] is True:
            if f["strength"] not in ("E1", "E2"):
                probs.append(f"{where}: admitted with strength {f['strength']} (only E1 / E2 admit)")
            if not f["evidence"]:
                probs.append(f"{where}: admitted without evidence")
        for j, e in enumerate(f["evidence"]):
            w = f"{where} evidence {j + 1}"
            if not isinstance(e, dict) or set(e) != EVIDENCE_KEYS:
                probs.append(f"{w}: keys must be exactly {sorted(EVIDENCE_KEYS)}")
                continue
            if not all(isinstance(e[k], str) and e[k] for k in EVIDENCE_KEYS):
                probs.append(f"{w}: every field must be non-empty text")
                continue
            if not e["record"].startswith(RESULTS_DIR) or ".." in e["record"]:
                probs.append(f"{w}: record {e['record']!r} is not under {RESULTS_DIR}")
                continue
            try:
                t = texts.setdefault(e["record"], _record_text(e["record"]))
            except EvaluationError as ex:
                probs.append(f"{w}: {ex}")
                continue
            if e["statement"] not in t:
                probs.append(f"{w}: statement not found verbatim in {e['record']}")
            if f["admitted"] is True and not closed_accepted(t):
                probs.append(f"{w}: cited record {e['record']} is not CLOSED ACCEPTED (status {record_status(t)!r})")
        d = f.get("definition")
        if d is not None:
            if not isinstance(d, dict) or set(d) != DEFINITION_KEYS or not all(isinstance(d[k], str) and d[k] for k in DEFINITION_KEYS):
                probs.append(f"{where}: definition keys must be exactly {sorted(DEFINITION_KEYS)}, non-empty text")
            elif not d["record"].startswith(RESULTS_DIR) or ".." in d["record"]:
                probs.append(f"{where}: definition record {d['record']!r} is not under {RESULTS_DIR}")
            else:
                try:
                    if d["statement"] not in texts.setdefault(d["record"], _record_text(d["record"])):
                        probs.append(f"{where}: definition statement not found verbatim in {d['record']}")
                except EvaluationError as ex:
                    probs.append(f"{where}: definition: {ex}")
    return probs


def load_registry(path=REGISTRY_PATH):
    """returns {"path", "sha256", "registry", "admitted": [names], "known": [names]}; raises EvaluationError (exit 2)
    on any structural or evidence problem. Reads only; never writes."""
    try:
        raw = open(path, "rb").read()
    except OSError as ex:
        raise EvaluationError(f"registry {path}: {ex}")
    try:
        reg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as ex:
        raise EvaluationError(f"registry {path}: not valid JSON ({ex})")
    probs = validate_registry(reg)
    if probs:
        raise EvaluationError(f"registry {path} invalid ({len(probs)}): {probs[:5]}")
    fs = reg["features"]
    return {"path": path, "sha256": hashlib.sha256(raw).hexdigest(), "registry": reg,
            "admitted": [f["name"] for f in fs if f["admitted"]], "known": [f["name"] for f in fs]}


# -------------------------------------------------------------------------------------------------- schema ------
# design 5.3: the composed digest <cfg>.s5n21.digest.json (the s5n digest itself is preserved unchanged)
DIGEST_SCHEMA = "m2s72-s5n21-digest/1"
DIGEST_KEYS = ("schema", "config", "kind", "option", "placement", "numUe", "harq16", "dl_factor", "correctness",
               "performance", "historical", "diagnostics", "mac_grammar_census", "inputs")
CORRECTNESS_KEYS = ("verdict", "rows", "s5n", "a21")
VERDICT_KEYS = ("status", "exit", "gate_failures", "gate_not_evaluated", "held_features")
S5N_KEYS = ("verdict_line", "gate_failures", "per_ue_not_evaluated", "rows")
A21_KEYS = ("rows", "verdict_f1d_i", "verdict_full", "coverage")
PERFORMANCE_KEYS = ("per_ue", "across", "across_harq_a21", "totals")
HARQ_A21_GROUPS = ("counts", "occupancy", "simu5g")
HISTORICAL_A1_KEYS = ("pu4_row", "harq_attribution", "per_ue_harq")
INPUTS_KEYS = ("log_sha256", "sca_sha256", "registry_sha256", "code", "c0", "s5n_adapter_validated")
ROW_KEYS = ("id", "subject", "status", "detail")


def _keys(obj, required, where, probs, extra_ok=False):
    if not isinstance(obj, dict):
        probs.append(f"{where}: not an object")
        return False
    miss = [k for k in required if k not in obj]
    extra = [k for k in obj if k not in required]
    if miss:
        probs.append(f"{where}: missing {miss}")
    if extra and not extra_ok:
        probs.append(f"{where}: unexpected {extra}")
    return not miss


def validate_row(r, where="row"):
    """a wrapper row {id, subject, status, detail[, local]}: status from 4.0; per-UE rows (PU-4o, A2-8u) also carry
    the local comparison outcome; PASS is only possible with a local EQUAL"""
    probs = []
    if not _keys(r, ROW_KEYS + (("local",) if isinstance(r, dict) and "local" in r else ()), where, probs):
        return probs
    if r["id"] not in WRAPPER_ROWS:
        probs.append(f"{where}: id {r['id']!r} not a wrapper row {WRAPPER_ROWS}")
    if r["status"] not in ROW_STATUSES:
        probs.append(f"{where}: status {r['status']!r} not in {ROW_STATUSES}")
    if not isinstance(r["subject"], str) or not isinstance(r["detail"], str):
        probs.append(f"{where}: subject and detail must be text")
    if r["id"] in PER_UE_ROWS:
        if "local" not in r:
            probs.append(f"{where}: per-UE row without a local comparison outcome")
        elif r["local"] not in LOCAL_OUTCOMES:
            probs.append(f"{where}: local {r['local']!r} not in {LOCAL_OUTCOMES}")
        elif r["status"] == PASS and r["local"] != EQUAL:
            probs.append(f"{where}: PASS with local {r['local']}")
        elif r["local"] == DIFFERENT and r["status"] != FAIL:
            probs.append(f"{where}: local DIFFERENT must be FAIL, got {r['status']}")
        if not re.fullmatch(r"UE \d+", str(r["subject"])):
            probs.append(f"{where}: per-UE subject {r['subject']!r} is not 'UE <k>'")
    elif "local" in r:
        probs.append(f"{where}: local outcome on a run-level row")
    return probs


def _finite_json(x, where, probs):
    if isinstance(x, float) and not math.isfinite(x):
        probs.append(f"{where}: non-finite number")
    elif isinstance(x, dict):
        for k, v in x.items():
            _finite_json(v, f"{where}.{k}", probs)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _finite_json(v, f"{where}[{i}]", probs)


def validate_digest(d):
    """structural validation of a composed digest (design 5.3). Returns the list of problems (empty = valid)."""
    probs = []
    if not _keys(d, DIGEST_KEYS, "digest", probs):
        return probs
    if d["schema"] != DIGEST_SCHEMA:
        probs.append(f"schema {d['schema']!r} != {DIGEST_SCHEMA!r}")
    if d["kind"] != "E0vN" or not isinstance(d["numUe"], int) or isinstance(d["numUe"], bool) or d["numUe"] < 1:
        probs.append(f"kind / numUe: {d['kind']!r} / {d['numUe']!r}")
    n = d["numUe"] if isinstance(d["numUe"], int) and not isinstance(d["numUe"], bool) else 0
    c = d["correctness"]
    if _keys(c, CORRECTNESS_KEYS, "correctness", probs):
        v = c["verdict"]
        if _keys(v, VERDICT_KEYS, "correctness.verdict", probs):
            if v["status"] not in EXIT:
                probs.append(f"verdict status {v['status']!r} not in {sorted(EXIT)}")
            elif v["exit"] != EXIT[v["status"]]:
                probs.append(f"verdict exit {v['exit']!r} != {EXIT[v['status']]} for {v['status']}")
            for k in ("gate_failures", "gate_not_evaluated", "held_features"):
                if not isinstance(v[k], list):
                    probs.append(f"verdict {k} must be a list")
            if v.get("status") == V_PASS and (v.get("gate_failures") or v.get("gate_not_evaluated") or v.get("held_features")):
                probs.append("verdict PASS with gate failures, not-evaluated gates or held features")
        if not isinstance(c["rows"], list):
            probs.append("correctness.rows must be a list")
        else:
            for i, r in enumerate(c["rows"]):
                probs += validate_row(r, f"correctness.rows[{i}]")
            per_ue = {(r.get("id"), r.get("subject")) for r in c["rows"] if isinstance(r, dict)}
            for rid in PER_UE_ROWS:
                for k in range(n):
                    if (rid, f"UE {k}") not in per_ue:
                        probs.append(f"correctness.rows: no {rid} row for UE {k}")
        _keys(c["s5n"], S5N_KEYS, "correctness.s5n", probs)
        if _keys(c["a21"], A21_KEYS, "correctness.a21", probs):
            for k in ("verdict_f1d_i", "verdict_full"):
                if c["a21"][k] not in A21_VERDICTS:
                    probs.append(f"correctness.a21.{k} {c['a21'][k]!r} not in {A21_VERDICTS}")
    pf = d["performance"]
    if _keys(pf, PERFORMANCE_KEYS, "performance", probs):
        pu = pf["per_ue"]
        if not isinstance(pu, list) or len(pu) != n:
            probs.append(f"performance.per_ue must be a list of numUe = {n} entries")
        else:
            for k, m in enumerate(pu):
                w = f"performance.per_ue[{k}]"
                if not isinstance(m, dict):
                    probs.append(f"{w}: not an object")
                    continue
                if "harq" in m:
                    probs.append(f"{w}: holds 'harq' (A-1-derived values belong only under historical)")
                h = m.get("harq_a21")
                if _keys(h, HARQ_A21_GROUPS, f"{w}.harq_a21", probs):
                    for g in HARQ_A21_GROUPS:
                        gv = h[g]
                        if not isinstance(gv, dict) or not isinstance(gv.get("available"), bool):
                            probs.append(f"{w}.harq_a21.{g}: needs a boolean 'available'")
                        elif gv["available"] is False and (set(gv) - {"available", "reason"} or not gv.get("reason")):
                            probs.append(f"{w}.harq_a21.{g}: unavailable must carry only a reason, never a value")
        ah = pf["across_harq_a21"]
        if not isinstance(ah, dict):
            probs.append("performance.across_harq_a21: not an object")
        else:
            for key, val in ah.items():
                if not isinstance(val, dict) or not isinstance(val.get("available"), bool):
                    probs.append(f"performance.across_harq_a21.{key}: needs a boolean 'available'")
                elif val["available"] is False and set(val) != {"available", "missing_ues"}:
                    probs.append(f"performance.across_harq_a21.{key}: unavailable must carry only missing_ues")
    hi = d["historical"]
    if _keys(hi, ("a1",), "historical", probs):
        _keys(hi["a1"], HISTORICAL_A1_KEYS + ("label",), "historical.a1", probs)
    if not isinstance(d["diagnostics"], dict):
        probs.append("diagnostics: not an object")
    _keys(d["inputs"], INPUTS_KEYS, "inputs", probs)
    _finite_json(d, "digest", probs)
    return probs
