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
Increment I-2 adds MAP-UE (4.4) and A2-8u with its compatibility relation CR-1 .. CR-4 (4.5).
Increment I-3 adds C-0 with R-0a .. R-0e (4.1), PU-4h (4.3) and PU-4o (4.6); the censoring classes of 4.2 act through
the unchanged A-2.1 rows.
Increment I-4 adds the historical A-1 report (PU-4 verbatim, the A-1 summary and per-UE values under 'historical') and
the non-gating A-1 / A-2.1 agreement diagnostic (4.10).
Increment I-7 adds the complete row-set checks (A-2.1 rows incl. A2-7 / A2-8, the s5n rows incl. the historical
PU-4), the availability-gated current H-ARQ values, the all-or-nothing across-UE aggregates and the composed digest
of the run mode (3.3, 4.8 - 4.10, 5.3).
Increment I-6 adds IG-2 (no A2-8u comparison without the duplicate census) and the record writers used by the
hrq / hrq-fixture modes of check_m2s72_s5n21.py.
Increment I-5 adds the first-genuine-occurrence evaluation against the committed registry (4.7), the s5n gate
predicate minus the historical PU-4 (4.8, 4.9) and the composed verdict with the precedence
REFUSED / EVALUATION ERROR > FAIL > INCOMPLETE > HELD FOR REVIEW > PASS (exits 2, 1, 4, 3, 0; D-A1-11).
The CLI modes are later increments (I-6 .. I-8) and are deliberately absent.

Pure functions. Never writes a file. Reads only the registry and the result records the registry cites. The frozen
and accepted modules are imported read-only and are never modified.
"""
import copy
from collections import Counter
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
import m2s72_a2probe as PR  # noqa: E402  (frozen, fbee202; read-only: NET, R_UE_MOD, HARQ_SCALARS)
import m2s72_peru_adapter as PA  # noqa: E402  (accepted S5-2 tooling; read-only: harq_events' gNB module)

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


def _text(x):
    """non-empty text"""
    return isinstance(x, str) and x != ""


def _show(x):
    """a short, always-printable rendering of any JSON-compatible value (for problem messages)"""
    s = repr(x)
    return s if len(s) <= 80 else s[:77] + "..."


def _record_text(rel):
    if not _text(rel) or "\x00" in rel:
        raise EvaluationError(f"registry: cited record {_show(rel)} is not a path")
    p = os.path.normpath(os.path.join(REPO, rel))
    if not p.startswith(os.path.join(REPO, "")) or not os.path.isfile(p):
        raise EvaluationError(f"registry: cited record {rel!r} is not a file in the repository")
    try:
        with open(p, encoding="utf-8") as fh:
            return fh.read()
    except (OSError, UnicodeDecodeError) as ex:
        raise EvaluationError(f"registry: cited record {rel!r} cannot be read as UTF-8 text ({type(ex).__name__})")


def record_status(text):
    """the record's status line: the first line starting with '**Status'"""
    if not isinstance(text, str):
        return None
    for line in text.splitlines():
        if line.startswith("**Status"):
            return line
    return None


def closed_accepted(text):
    s = record_status(text)
    return s is not None and "CLOSED" in s and "ACCEPTED" in s and "NOT ACCEPTED" not in s


def _cite(c, keys, where, texts, probs, accepted_required):
    """one citation {record, section, ...}: exact keys, non-empty text fields, a record under RESULTS_DIR, the
    statement verbatim in it, and (for an admission) a CLOSED ACCEPTED record"""
    if not isinstance(c, dict):
        probs.append(f"{where}: must be an object, got {type(c).__name__}")
        return
    if set(c) != keys:
        probs.append(f"{where}: keys {sorted(map(str, c))}, required exactly {sorted(keys)}")
        return
    bad = [k for k in sorted(keys) if not _text(c[k])]
    if bad:
        probs.append(f"{where}: fields {bad} must be non-empty text")
        return
    rec = c["record"]
    if not rec.startswith(RESULTS_DIR) or ".." in rec.split("/") or "\\" in rec:
        probs.append(f"{where}: record {rec!r} is not under {RESULTS_DIR}")
        return
    try:
        if rec not in texts:
            texts[rec] = _record_text(rec)
    except EvaluationError as ex:
        probs.append(f"{where}: {ex}")
        return
    if c["statement"] not in texts[rec]:
        probs.append(f"{where}: statement not found verbatim in {rec}")
    if accepted_required and not closed_accepted(texts[rec]):
        probs.append(f"{where}: cited record {rec} is not CLOSED ACCEPTED (status {record_status(texts[rec])!r})")


def validate_registry(reg, names=None):
    """structural and evidence validation (design 4.7 / 4.7.1). Returns the list of problems (empty = valid). Never
    raises on a JSON-compatible input: every defect is reported as a problem."""
    names = coverage_names() if names is None else names
    probs = []
    if not isinstance(reg, dict):
        return [f"top level must be an object, got {type(reg).__name__}"]
    if set(reg) != {"schema", "features"}:
        return [f"top level keys {sorted(map(str, reg))}, required exactly ['features', 'schema']"]
    if reg["schema"] != REGISTRY_SCHEMA:
        probs.append(f"schema {_show(reg['schema'])} != {REGISTRY_SCHEMA!r}")
    fs = reg["features"]
    if not isinstance(fs, list):
        return probs + [f"features must be a list, got {type(fs).__name__}"]
    got = [f.get("name") if isinstance(f, dict) else None for f in fs]
    if got != names:
        texts_got = [n for n in got if isinstance(n, str)]
        probs.append(f"feature names differ from m2s72_a21.coverage() (order included): count {len(got)} vs {len(names)}; "
                     f"missing {[n for n in names if n not in texts_got]}; unknown {[_show(n) for n in got if n not in names]}; "
                     f"duplicates {sorted({n for n in texts_got if texts_got.count(n) > 1})}")
    texts = {}
    consistent = {"E1": "explicit", "E2": "explicit", "I": "inferred-only", "N": "not-exercised"}
    for i, f in enumerate(fs):
        if not isinstance(f, dict):
            probs.append(f"feature {i + 1}: must be an object, got {type(f).__name__}")
            continue
        where = f"feature {i + 1} {_show(f.get('name'))}"
        keys = set(f)
        if not FEATURE_KEYS <= keys or not keys <= FEATURE_KEYS | FEATURE_OPTIONAL:
            probs.append(f"{where}: keys {sorted(map(str, keys))}; required {sorted(FEATURE_KEYS)}, optional {sorted(FEATURE_OPTIONAL)}")
            continue
        if not _text(f["name"]):
            probs.append(f"{where}: name must be non-empty text")
        if not isinstance(f["admitted"], bool):
            probs.append(f"{where}: admitted must be true or false, got {_show(f['admitted'])}")
        strength_ok = isinstance(f["strength"], str) and f["strength"] in STRENGTHS
        if not strength_ok:
            probs.append(f"{where}: strength {_show(f['strength'])} not in {STRENGTHS}")
        if not (isinstance(f["genuine"], str) and f["genuine"] in GENUINE):
            probs.append(f"{where}: genuine {_show(f['genuine'])} not in {GENUINE}")
        elif strength_ok and f["genuine"] != consistent[f["strength"]]:
            probs.append(f"{where}: genuine {f['genuine']!r} inconsistent with strength {f['strength']}")
        if not isinstance(f["note"], str):
            probs.append(f"{where}: note must be text")
        if not isinstance(f["evidence"], list):
            probs.append(f"{where}: evidence must be a list, got {type(f['evidence']).__name__}")
            continue
        admitted = f["admitted"] is True
        if not f["evidence"]:
            probs.append(f"{where}: no evidence (every feature documents its provenance, admitted or excluded)")
        if admitted and (not strength_ok or f["strength"] not in ("E1", "E2")):
            probs.append(f"{where}: admitted with strength {_show(f['strength'])} (only E1 / E2 admit)")
        for j, e in enumerate(f["evidence"]):
            _cite(e, EVIDENCE_KEYS, f"{where} evidence {j + 1}", texts, probs, accepted_required=admitted)
        if "definition" in f:
            _cite(f["definition"], DEFINITION_KEYS, f"{where} definition", texts, probs, accepted_required=False)
    return probs


def load_registry(path=REGISTRY_PATH):
    """returns {"path", "sha256", "registry", "admitted": [names], "known": [names]}; raises EvaluationError (exit 2)
    on any structural or evidence problem. Reads only; never writes."""
    if not isinstance(path, (str, os.PathLike)) or not os.path.isfile(path):   # an int would be a file descriptor
        raise EvaluationError(f"registry {path!r}: not a regular file path")
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
    except (OSError, TypeError, ValueError) as ex:
        raise EvaluationError(f"registry {path!r}: {type(ex).__name__}: {ex}")
    try:
        reg = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, ValueError, RecursionError) as ex:      # json.JSONDecodeError is a ValueError
        raise EvaluationError(f"registry {path}: not valid JSON ({type(ex).__name__})")
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
HISTORICAL_A1_KEYS = ("label", "pu4_row", "harq_attribution", "per_ue_harq")
INPUTS_KEYS = ("log_sha256", "sca_sha256", "registry_sha256", "consumed_sha256", "code", "c0", "s5n_adapter_validated")
ROW_KEYS = ("id", "subject", "status", "detail")
RUN_ROWS = (ROW_MAP, ROW_C0, ROW_PU4H)
GATE_ROW_STATUSES = (PASS, FAIL, NE)          # a wrapper gate row is never NX / NA / HR (design 4.3 - 4.6)
DIGEST_VERDICTS = (V_PASS, V_FAIL, V_INCOMPLETE, V_HELD)   # REFUSED / EVALUATION ERROR runs write no digest
HISTORICAL_PU4 = "PU-4"                       # the only s5n gate removed from the composed gate set (design 4.9)


def _keys(obj, required, where, probs, optional=()):
    """exact key set: required keys present, nothing else (optional keys allowed). False if obj is unusable."""
    if not isinstance(obj, dict):
        probs.append(f"{where}: must be an object, got {type(obj).__name__}")
        return False
    miss = [k for k in required if k not in obj]
    extra = sorted(str(k) for k in obj if k not in required and k not in optional)
    if miss:
        probs.append(f"{where}: missing {miss}")
    if extra:
        probs.append(f"{where}: unexpected {extra}")
    return not miss


def _str_list(x, where, probs):
    """a list of distinct non-empty strings; returns it, or None after reporting"""
    if not isinstance(x, list) or not all(_text(v) for v in x):
        probs.append(f"{where}: must be a list of non-empty strings, got {_show(x)}")
        return None
    if len(set(x)) != len(x):
        probs.append(f"{where}: duplicate entries {sorted({v for v in x if x.count(v) > 1})}")
    return x


def validate_row(r, where="row"):
    """a wrapper row {id, subject, status, detail[, local]}: id from WRAPPER_ROWS, status from 4.0 restricted to
    PASS / FAIL / NE for the wrapper gates; run-level rows have subject 'run' and no local outcome; per-UE rows
    (PU-4o, A2-8u) have subject 'UE <k>' and a local outcome; PASS needs a local EQUAL, a local DIFFERENT is FAIL.
    Never raises on a JSON-compatible input."""
    probs = []
    if not _keys(r, ROW_KEYS, where, probs, optional=("local",)):
        return probs
    rid, st, subj = r["id"], r["status"], r["subject"]
    rid_ok = isinstance(rid, str) and rid in WRAPPER_ROWS
    if not rid_ok:
        probs.append(f"{where}: id {_show(rid)} not a wrapper row {WRAPPER_ROWS}")
    if not (isinstance(st, str) and st in GATE_ROW_STATUSES):
        probs.append(f"{where}: status {_show(st)} not a wrapper gate status {GATE_ROW_STATUSES}")
    if not isinstance(subj, str):
        probs.append(f"{where}: subject must be text, got {type(subj).__name__}")
    if not isinstance(r["detail"], str):
        probs.append(f"{where}: detail must be text, got {type(r['detail']).__name__}")
    if not rid_ok:
        return probs
    if rid in PER_UE_ROWS:
        if not (isinstance(subj, str) and re.fullmatch(r"UE (0|[1-9]\d*)", subj)):
            probs.append(f"{where}: per-UE subject {_show(subj)} is not 'UE <k>'")
        if "local" not in r:
            probs.append(f"{where}: per-UE row without a local comparison outcome")
        elif not (isinstance(r["local"], str) and r["local"] in LOCAL_OUTCOMES):
            probs.append(f"{where}: local {_show(r['local'])} not in {LOCAL_OUTCOMES}")
        elif st == PASS and r["local"] != EQUAL:
            probs.append(f"{where}: PASS with local {r['local']}")
        elif r["local"] == DIFFERENT and st != FAIL:
            probs.append(f"{where}: local DIFFERENT must be FAIL, got {_show(st)}")
    else:
        if subj != "run":
            probs.append(f"{where}: run-level subject {_show(subj)} is not 'run'")
        if "local" in r:
            probs.append(f"{where}: local outcome on a run-level row")
    return probs


def _rows_consistency(rows, n, verdict, s5n, a21, probs):
    """design 4.3 - 4.9, structural only (the verdict composer is I-5): completeness and uniqueness of the wrapper
    rows, the global rules between them, and their agreement with the composed verdict and its gate lists"""
    st, seen = {}, set()
    for i, r in enumerate(rows):
        if not isinstance(r, dict) or validate_row(r, ""):
            continue                                   # reported by validate_row; not used for the relations
        key = (r["id"], r["subject"])
        if key in seen:
            probs.append(f"correctness.rows: duplicate row {r['id']} {r['subject']}")
            continue
        seen.add(key)
        if r["id"] in PER_UE_ROWS:
            k = int(r["subject"].split()[1])
            if k >= n:
                probs.append(f"correctness.rows: {r['id']} {r['subject']} outside the expected UEs 0 .. {n - 1}")
                continue
        st[key] = r["status"]
    for rid in RUN_ROWS:
        if (rid, "run") not in seen:
            probs.append(f"correctness.rows: no {rid} row")
    for rid in PER_UE_ROWS:
        for k in range(n):
            if (rid, f"UE {k}") not in seen:
                probs.append(f"correctness.rows: no {rid} row for UE {k}")
    # global rules between rows (design 4.3, 4.5, 4.6)
    g = {rid: st.get((rid, "run")) for rid in RUN_ROWS}
    per = {key: s for key, s in st.items() if key[0] in PER_UE_ROWS}
    if g[ROW_PU4H] == PASS and (g[ROW_MAP] != PASS or g[ROW_C0] != PASS):
        probs.append(f"PU-4h PASS with MAP-UE {g[ROW_MAP]} and C-0 {g[ROW_C0]} (both must PASS)")
    if FAIL in (g[ROW_MAP], g[ROW_C0]) and g[ROW_PU4H] not in (FAIL, None):
        probs.append(f"PU-4h {g[ROW_PU4H]} although MAP-UE / C-0 FAIL")
    for key, s in sorted(per.items()):
        if s == PASS and (g[ROW_PU4H] != PASS or g[ROW_MAP] != PASS):
            probs.append(f"{key[0]} {key[1]} PASS with PU-4h {g[ROW_PU4H]} and MAP-UE {g[ROW_MAP]} (both must PASS)")
        if FAIL in (g[ROW_PU4H], g[ROW_MAP]) and s != FAIL:
            probs.append(f"{key[0]} {key[1]} {s} although PU-4h / MAP-UE FAIL (global rule: FAIL)")
        if s == PASS and key[0] == ROW_PU4O and g[ROW_PU4H] == PASS and a21.get("rows_status", {}).get("A2-7") not in (None, PASS):
            probs.append(f"{key[0]} {key[1]} PASS with A2-7 {a21['rows_status']['A2-7']}")
    vf = a21.get("verdict_f1d_i")
    if vf in A21_VERDICTS:
        if g[ROW_PU4H] == PASS and vf != f"{A21.VERSION} VALID":
            probs.append(f"PU-4h PASS with the F1-d(i) verdict {vf!r}")
        if vf == f"{A21.VERSION} NOT VALID" and g[ROW_PU4H] not in (FAIL, None):
            probs.append(f"PU-4h {g[ROW_PU4H]} with the F1-d(i) verdict {vf!r} (must FAIL)")
    # the composed verdict and its gate lists (design 4.8, 4.9)
    if not isinstance(verdict, dict):
        return
    vs = verdict.get("status")
    fails = _str_list(verdict.get("gate_failures"), "verdict.gate_failures", probs)
    nes = _str_list(verdict.get("gate_not_evaluated"), "verdict.gate_not_evaluated", probs)
    held = _str_list(verdict.get("held_features"), "verdict.held_features", probs)
    if fails is None or nes is None or held is None:
        return
    w_fail = sorted({rid for (rid, _), s in st.items() if s == FAIL})
    w_ne = sorted({rid for (rid, _), s in st.items() if s == NE})
    got_wf = sorted(x for x in fails if x in WRAPPER_ROWS)
    got_wn = sorted(x for x in nes if x in WRAPPER_ROWS)
    if got_wf != w_fail:
        probs.append(f"verdict.gate_failures lists wrapper rows {got_wf}, the rows FAIL in {w_fail}")
    if got_wn != w_ne:
        probs.append(f"verdict.gate_not_evaluated lists wrapper rows {got_wn}, the rows NOT EVALUATED in {w_ne}")
    if isinstance(s5n, dict):
        sf = s5n.get("gate_failures")
        sn = s5n.get("per_ue_not_evaluated")
        if isinstance(sf, list) and all(_text(x) for x in sf) and isinstance(sn, list) and all(_text(x) for x in sn):
            want_f = sorted(set(sf) - {HISTORICAL_PU4})
            want_n = sorted(set(sn) - {HISTORICAL_PU4})
            if sorted(x for x in fails if x not in WRAPPER_ROWS) != want_f:
                probs.append(f"verdict.gate_failures s5n part {sorted(x for x in fails if x not in WRAPPER_ROWS)} != "
                             f"s5n gate failures minus PU-4 {want_f}")
            if sorted(x for x in nes if x not in WRAPPER_ROWS) != want_n:
                probs.append(f"verdict.gate_not_evaluated s5n part {sorted(x for x in nes if x not in WRAPPER_ROWS)} != "
                             f"s5n not-evaluated gates minus PU-4 {want_n}")
            if HISTORICAL_PU4 in fails or HISTORICAL_PU4 in nes:
                probs.append("PU-4 (A-1, historical) listed as a gate")
        else:
            probs.append("correctness.s5n gate lists must be lists of non-empty strings")
    want = V_FAIL if fails else V_INCOMPLETE if nes else V_HELD if held else V_PASS
    if vs in DIGEST_VERDICTS and vs != want:
        probs.append(f"verdict {vs} contradicts its lists (failures {fails}, not evaluated {nes}, held {held}): "
                     f"expected {want} by the precedence FAIL > INCOMPLETE > HELD FOR REVIEW > PASS")


def _finite_json(x, where, probs, depth=0):
    if depth > 64:
        probs.append(f"{where}: nested deeper than 64 levels")
    elif isinstance(x, float) and not math.isfinite(x):
        probs.append(f"{where}: non-finite number")
    elif isinstance(x, dict):
        for k, v in x.items():
            _finite_json(v, f"{where}.{k}", probs, depth + 1)
    elif isinstance(x, list):
        for i, v in enumerate(x):
            _finite_json(v, f"{where}[{i}]", probs, depth + 1)


def validate_digest(d):
    """structural validation of a composed digest (design 5.3) including the consistency of its wrapper rows with the
    composed verdict (4.8, 4.9). Returns the list of problems (empty = valid). Never raises on a JSON-compatible input."""
    probs = []
    if not _keys(d, DIGEST_KEYS, "digest", probs):
        return probs
    if d["schema"] != DIGEST_SCHEMA:
        probs.append(f"schema {_show(d['schema'])} != {DIGEST_SCHEMA!r}")
    if not _text(d["config"]) or not run_name_ok(d["config"]):
        probs.append(f"config {_show(d['config'])} is not admissible for 'run' (name guard)")
    if d["kind"] != "E0vN":
        probs.append(f"kind {_show(d['kind'])} != 'E0vN'")
    n_ok = isinstance(d["numUe"], int) and not isinstance(d["numUe"], bool) and d["numUe"] >= 1
    if not n_ok:
        probs.append(f"numUe {_show(d['numUe'])} must be an integer >= 1")
    n = d["numUe"] if n_ok else 0
    c = d["correctness"]
    if _keys(c, CORRECTNESS_KEYS, "correctness", probs):
        v = c["verdict"]
        if _keys(v, VERDICT_KEYS, "correctness.verdict", probs):
            if not (isinstance(v["status"], str) and v["status"] in DIGEST_VERDICTS):
                probs.append(f"verdict status {_show(v['status'])} not in {DIGEST_VERDICTS}")
            elif v["exit"] != EXIT[v["status"]] or isinstance(v["exit"], bool):
                probs.append(f"verdict exit {_show(v['exit'])} != {EXIT[v['status']]} for {v['status']}")
        else:
            v = None
        rows = c["rows"]
        if not isinstance(rows, list):
            probs.append(f"correctness.rows must be a list, got {type(rows).__name__}")
            rows = []
        for i, r in enumerate(rows):
            probs += validate_row(r, f"correctness.rows[{i}]")
        s5n = c["s5n"]
        _keys(s5n, S5N_KEYS, "correctness.s5n", probs)
        a21 = c["a21"]
        a21_view = {}
        if _keys(a21, A21_KEYS, "correctness.a21", probs):
            for k in ("verdict_f1d_i", "verdict_full"):
                if not (isinstance(a21[k], str) and a21[k] in A21_VERDICTS):
                    probs.append(f"correctness.a21.{k} {_show(a21[k])} not in {A21_VERDICTS}")
                else:
                    a21_view[k] = a21[k]
            if not isinstance(a21["rows"], list) or not isinstance(a21["coverage"], list):
                probs.append("correctness.a21 rows and coverage must be lists")
            else:
                rs = {}
                for i, r in enumerate(a21["rows"]):
                    if isinstance(r, list) and len(r) == 4 and all(isinstance(x, str) for x in r):
                        if r[0] in rs:
                            probs.append(f"correctness.a21.rows: {r[0]} twice")
                        rs[r[0]] = r[2]
                    else:
                        probs.append(f"correctness.a21.rows[{i}]: must be [id, subject, status, detail] text")
                # I-7: the accepted A-2.1 row set is complete (A2-7 and A2-8 included), nothing else
                if sorted(rs) != sorted(A21_ROW_IDS):
                    probs.append(f"correctness.a21.rows: missing {sorted(set(A21_ROW_IDS) - set(rs))}, "
                                 f"unexpected {sorted(set(rs) - set(A21_ROW_IDS))}")
                bad_st = sorted(k for k, v in rs.items() if v not in (PASS, FAIL, NE, NX))
                if bad_st:
                    probs.append(f"correctness.a21.rows: statuses not PASS / FAIL / NE / NX for {bad_st}")
                a21_view["rows_status"] = rs
        if n_ok:
            _rows_consistency(rows, n, v, s5n if isinstance(s5n, dict) else None, a21_view, probs)
    pf = d["performance"]
    if _keys(pf, PERFORMANCE_KEYS, "performance", probs):
        pu = pf["per_ue"]
        if not isinstance(pu, list) or len(pu) != n:
            probs.append(f"performance.per_ue must be a list of numUe = {n} entries, got {_show(pu)}")
        else:
            for k, m in enumerate(pu):
                w = f"performance.per_ue[{k}]"
                if not isinstance(m, dict):
                    probs.append(f"{w}: must be an object, got {type(m).__name__}")
                    continue
                if "harq" in m:
                    probs.append(f"{w}: holds 'harq' (A-1-derived values belong only under historical)")
                if m.get("k") != k:
                    probs.append(f"{w}: k {_show(m.get('k'))} != {k}")
                if "harq_a21" not in m:
                    probs.append(f"{w}: missing harq_a21")
                    continue
                h = m["harq_a21"]
                if _keys(h, HARQ_A21_GROUPS, f"{w}.harq_a21", probs):
                    for gname in HARQ_A21_GROUPS:
                        gv = h[gname]
                        if not isinstance(gv, dict) or not isinstance(gv.get("available"), bool):
                            probs.append(f"{w}.harq_a21.{gname}: must be an object with a boolean 'available'")
                        elif gv["available"] is False and (set(gv) != {"available", "reason"} or not _text(gv["reason"])):
                            probs.append(f"{w}.harq_a21.{gname}: unavailable must carry only a reason, never a value")
        ah = pf["across_harq_a21"]
        if not isinstance(ah, dict):
            probs.append(f"performance.across_harq_a21: must be an object, got {type(ah).__name__}")
        else:
            for key, val in ah.items():
                if not isinstance(val, dict) or not isinstance(val.get("available"), bool):
                    probs.append(f"performance.across_harq_a21.{key}: must be an object with a boolean 'available'")
                elif val["available"] is False:
                    mu = val.get("missing_ues")
                    if set(val) != {"available", "missing_ues"} or not isinstance(mu, list) or not mu or not all(
                            isinstance(x, int) and not isinstance(x, bool) and 0 <= x < max(n, 1) for x in mu):
                        probs.append(f"performance.across_harq_a21.{key}: unavailable must carry only a non-empty "
                                     f"missing_ues list of expected UEs")
        if not isinstance(pf["across"], dict) or not isinstance(pf["totals"], dict):
            probs.append("performance.across and performance.totals must be objects")
    hi = d["historical"]
    if _keys(hi, ("a1",), "historical", probs):
        a1 = hi["a1"]
        if _keys(a1, HISTORICAL_A1_KEYS, "historical.a1", probs):
            if a1["label"] != "A-1, historical rule; not a current measurement (DR-07b)":   # I-4: HISTORICAL_A1_LABEL
                probs.append(f"historical.a1.label {_show(a1['label'])} is not the historical label")
            pr = a1["pu4_row"]
            # I-4: the s5n PU-4 row, verbatim: [PU-4, subject, status, detail] with an s5n status; never relabelled
            if not (isinstance(pr, list) and len(pr) == 4 and all(isinstance(x, str) for x in pr) and pr[0] == "PU-4"):
                probs.append(f"historical.a1.pu4_row {_show(pr)} is not the s5n PU-4 row")
            elif pr[2] not in (PASS, FAIL, NE):
                probs.append(f"historical.a1.pu4_row status {pr[2]!r} is not an s5n PU-4 status (relabelled?)")
    if not isinstance(d["diagnostics"], dict):
        probs.append(f"diagnostics: must be an object, got {type(d['diagnostics']).__name__}")
    if not isinstance(d["mac_grammar_census"], list):
        probs.append("mac_grammar_census: must be a list")
    inp = d["inputs"]
    if _keys(inp, INPUTS_KEYS, "inputs", probs):
        cs = inp["consumed_sha256"]
        if not (isinstance(cs, dict) and all(isinstance(k, str) and isinstance(v, str) and re.fullmatch(r"[0-9a-f]{64}", v)
                                             for k, v in cs.items())):
            probs.append("inputs.consumed_sha256 must map each consumed input to its sha256")
        cd = inp["code"]
        if not (isinstance(cd, dict) and isinstance(cd.get("required"), dict) and isinstance(cd.get("loaded"), dict)):
            probs.append("inputs.code must hold the required and loaded source hashes")
        if not (isinstance(inp["registry_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", inp["registry_sha256"])):
            probs.append(f"inputs.registry_sha256 {_show(inp['registry_sha256'])} is not a sha256")
    _finite_json(d, "digest", probs)
    return probs


# ================================================================================================ I-2 ============
def _is_int(x):
    return isinstance(x, int) and not isinstance(x, bool)


def ue_module(k):
    """the UE NR MAC module of UE k, as the frozen sca_nodes() / R_UE_MOD read it"""
    return f"{PR.NET}.ue[{k}].cellularNic.nrMac"


# ------------------------------------------------------------------------------------- MAP-UE (design 4.4) ------
def evidence_nodes(res, per, x7):
    """the nodes the A-2.1 evidence refers to, by source (design 4.4 inputs): res["pdus"], the keys of per, and the
    keys of x7["occupancy_equal"] and x7["skipped"] when x7 is not None. Reads only."""
    out = {"pdus": set(), "per": set(), "occupancy_equal": set(), "skipped": set()}
    pdus = res.get("pdus") if isinstance(res, dict) else None
    if isinstance(pdus, dict):
        out["pdus"] = {u.get("node") for u in pdus.values() if isinstance(u, dict)}
    if isinstance(per, dict):
        out["per"] = set(per)
    if isinstance(x7, dict):
        if isinstance(x7.get("occupancy_equal"), dict):
            out["occupancy_equal"] = set(x7["occupancy_equal"])
        if isinstance(x7.get("skipped"), (list, tuple, set)):
            out["skipped"] = {n for n in x7["skipped"] if not isinstance(n, (list, dict, set))}
    return out


def map_ue(n, node_id, sca_map, evidence):
    """MAP-UE (design 4.4): the complete bijective UE-to-node mapping.
    n: numUe (from the name, checked by s5n); node_id: {k: n_k} from Run72 via inputs(), or None when it could not be
    obtained; sca_map: sca_nodes(sca) {module: n}, or None when the run has no .sca; evidence: evidence_nodes(...).
    Raises Refused when node_id is None (nothing is guessed). Returns the run-level row (PASS or FAIL). Reads only."""
    if node_id is None:
        raise Refused("UE-to-node mapping unavailable (Run72: a missing or duplicate macNodeId); nothing is guessed")
    if not _is_int(n) or n < 1:
        raise EvaluationError(f"MAP-UE: numUe {_show(n)} is not an integer >= 1")
    probs = []
    if not isinstance(node_id, dict):
        probs.append(f"node map is not a mapping: {_show(node_id)}")
    else:
        keys = list(node_id)
        if not all(_is_int(k) for k in keys) or set(keys) != set(range(n)):
            probs.append(f"node map UEs {sorted(map(str, keys))} != 0 .. {n - 1}")
        vals = list(node_id.values())
        if not all(_is_int(v) and v >= 0 for v in vals):
            probs.append(f"node ids not non-negative integers: {_show(node_id)}")
        elif len(set(vals)) != len(vals):
            probs.append(f"duplicate node ids {sorted(v for v in set(vals) if vals.count(v) > 1)}")
    if probs:
        return {"id": ROW_MAP, "subject": "run", "status": FAIL, "detail": "; ".join(probs)}
    image = set(node_id.values())
    if sca_map is not None:
        want = {ue_module(k): node_id[k] for k in range(n)}
        if not isinstance(sca_map, dict):
            probs.append(f".sca module map is not a mapping: {_show(sca_map)}")
        elif sca_map != want:
            extra = sorted(str(m) for m in sca_map if m not in want)
            miss = sorted(m for m in want if m not in sca_map)
            diff = sorted(f"{m}: .sca {sca_map[m]!r}, run {want[m]}" for m in want if m in sca_map and sca_map[m] != want[m])
            probs.append(f".sca macNodeId records differ from the run's mapping: extra {extra}, missing {miss}, different {diff}")
    for src in ("pdus", "per", "occupancy_equal", "skipped"):
        out = sorted(map(str, {x for x in evidence.get(src, set()) if x not in image}))
        if out:
            probs.append(f"evidence for an unmapped node in {src}: {out[:5]}")
    if probs:
        return {"id": ROW_MAP, "subject": "run", "status": FAIL, "detail": "; ".join(probs)}
    return {"id": ROW_MAP, "subject": "run", "status": PASS,
            "detail": f"UE k -> node bijective for k = 0 .. {n - 1}: {dict(sorted(node_id.items()))}; "
                      + ("consistent with the .sca macNodeId records" if sca_map is not None else "no .sca (mapping from node ids alone)")
                      + "; every A-2.1 evidence node mapped"}


# ------------------------------------------------------------------------------------- A2-8u (design 4.5) -------
A28_STATS = ("harqErrorRateDl:mean", "harqTxAttemptsDl:mean")   # the two statistics m2s72_a21.scalar_row compares
STAT_EQUAL = "equal"


def a28u_counts(res):
    """per node, the inputs of the two statistics, exactly as m2s72_a21.scalar_row derives them: feedback and NACK
    lines attributed to the node (res["fb"] owner), and the ntx of its ACKed lifecycles (res["pdus"] end == "ack").
    Reads only; returns new objects."""
    per = {}
    for x in res["fb"]:
        if x["owner"] is not None:
            d = per.setdefault(x["owner"], {"feedback": 0, "nack": 0, "ntx": []})
            d["feedback"] += 1
            d["nack"] += x["res"] == "NACK"
    for u in res["pdus"].values():
        if u["end"] == "ack":
            per.setdefault(u["node"], {"feedback": 0, "nack": 0, "ntx": []})["ntx"].append(u["ntx"])
    return per


def scalar_record_counts(lines):
    """the duplicate census of V-1: {(module, name): number of 'scalar' records} for the H-ARQ statistics, parsed
    exactly as the frozen m2s72_a2probe.scalars() parses them (which keeps the last of duplicates silently). Pure:
    the caller reads the .sca."""
    out = {}
    for line in lines:
        if isinstance(line, str) and line.startswith("scalar "):
            parts = line.split()
            if len(parts) >= 4 and parts[2] in PR.HARQ_SCALARS:
                out[(parts[1], parts[2])] = out.get((parts[1], parts[2]), 0) + 1
    return out


def _stat(name, rec_raw, c, dup_count):
    """the value procedure V-1 .. V-8 for one statistic of one UE (design 4.5). Returns {outcome, step, reason,
    rec, val}; outcome: "equal", DIFFERENT or NOT_COMPARED."""
    def out(outcome, step, reason, rec=None, val=None):
        return {"outcome": outcome, "step": step, "reason": reason, "rec": rec, "val": val}
    if _is_int(dup_count) and dup_count > 1:
        return out(NOT_COMPARED, "V-1", f"ambiguous: {dup_count} records")
    if rec_raw is _ABSENT:
        return out(NOT_COMPARED, "V-2", "absent")
    fb, nk = c.get("feedback"), c.get("nack")
    if not (_is_int(fb) and _is_int(nk)):
        return out(DIFFERENT, "V-3", f"A-2.1 value not computable: feedback {_show(fb)}, nack {_show(nk)} not integers")
    if fb <= 0 or nk < 0 or nk > fb:
        return out(DIFFERENT, "V-3", f"A-2.1 value not computable: feedback {fb}, nack {nk}")
    if name == "harqTxAttemptsDl:mean":
        ntx = c.get("ntx")
        if not isinstance(ntx, list) or not all(_is_int(v) and v >= 1 for v in ntx):
            return out(DIFFERENT, "V-3", f"A-2.1 value not computable: ntx of ACKed lifecycles {_show(ntx)}")
        if not ntx:
            return out(NOT_COMPARED, "V-4", "no ACKed lifecycle")
    try:
        val = nk / fb if name == "harqErrorRateDl:mean" else sum(ntx) / len(ntx)
    except OverflowError:                            # integers too large for a float: never a finite value
        return out(DIFFERENT, "V-4", "non-finite A-2.1 value (overflow)")
    if not math.isfinite(val):
        return out(DIFFERENT, "V-4", f"non-finite A-2.1 value {val!r}", val=val)
    if not isinstance(rec_raw, str):
        return out(NOT_COMPARED, "V-5", f"unexpected scalar type {type(rec_raw).__name__}", val=val)
    try:
        rec = float(rec_raw)
    except (ValueError, TypeError, OverflowError):
        return out(NOT_COMPARED, "V-6", f"unparsable {rec_raw!r}", val=val)
    if not math.isfinite(rec):
        return out(DIFFERENT, "V-7", f"non-finite Simu5G value {rec_raw!r}", rec=rec, val=val)
    if abs(rec - val) <= A21.REL_TOL * max(1.0, abs(val)):
        return out(STAT_EQUAL, "V-8", f"Simu5G {rec_raw}, A-2.1 {val:.12g}", rec=rec, val=val)
    return out(DIFFERENT, "V-8", f"Simu5G {rec_raw}, A-2.1 {val:.12g} (relative tolerance {A21.REL_TOL})", rec=rec, val=val)


class _Absent:
    def __repr__(self):
        return "<absent>"


_ABSENT = _Absent()


def a28u_local(k, n_k, sc, sca_map, counts, touched, dups):
    """the local comparison of UE k (design 4.5 steps 1 .. 8). sc: m2s72_a2probe.scalars(sca) (None / {} without
    scalars); sca_map: sca_nodes(sca); counts: a28u_counts(res); touched: m2s72_a21.touched_nodes(res); dups:
    scalar_record_counts(<.sca lines>). Returns {local, step, detail, stats: {name: _stat()}}. Reads only."""
    mod = ue_module(k)

    def done(local, step, detail, stats=None):
        return {"local": local, "step": step, "detail": f"ue[{k}] node {n_k}: {detail}", "stats": stats or {}}
    if not isinstance(sc, dict) or not sc or not isinstance(sca_map, dict) or not sca_map:
        return done(NOT_COMPARED, "1", "no Simu5G per-UE H-ARQ scalars")
    s = sc.get(mod)
    if not isinstance(s, dict) or not s:
        return done(NOT_COMPARED, "2", "no statistics for this UE")
    if n_k in (touched or ()):
        return done(NOT_COMPARED, "3", "uncertain attribution: censored or pending group")
    c = counts.get(n_k) if isinstance(counts, dict) else None
    if c is None or (isinstance(c, dict) and _is_int(c.get("feedback")) and c["feedback"] == 0):
        return done(NOT_COMPARED, "4", "no feedback")
    if not isinstance(c, dict):
        c = {}                                       # malformed counts: V-3 reports them as DIFFERENT
    if not isinstance(dups, dict):
        # IG-2: without the duplicate census of the .sca, a statistic can never be compared (never a silent pass)
        stats = {name: {"outcome": NOT_COMPARED, "step": "V-1", "reason": "duplicate census not performed (IG-2)",
                        "rec": None, "val": None} for name in A28_STATS}
    else:
        stats = {name: _stat(name, s[name] if name in s else _ABSENT, c, dups.get((mod, name), 0)) for name in A28_STATS}
    detail = "; ".join(f"{name} {v['outcome']} ({v['step']}: {v['reason']})" for name, v in stats.items())
    if any(v["outcome"] == DIFFERENT for v in stats.values()):
        return done(DIFFERENT, "6", detail, stats)
    if any(v["outcome"] == NOT_COMPARED for v in stats.values()):
        return done(NOT_COMPARED, "7", detail + " (both statistics are required)", stats)
    return done(EQUAL, "8", detail, stats)


def a28u_row(k, local, map_status, pu4h_status):
    """the row status of A2-8u UE k (design 4.5): the global rules (MAP-UE, PU-4h) over the local outcome"""
    loc = local["local"]
    if map_status == FAIL or pu4h_status == FAIL:
        st, why = FAIL, f"global: MAP-UE {map_status}, PU-4h {pu4h_status}"
    elif loc == DIFFERENT:
        st, why = FAIL, "local DIFFERENT"
    elif loc == NOT_COMPARED:
        st, why = NE, "local NOT COMPARED"
    elif map_status == PASS and pu4h_status == PASS:
        st, why = PASS, "local EQUAL, MAP-UE PASS, PU-4h PASS"
    else:
        st, why = NE, f"global: local EQUAL but MAP-UE {map_status}, PU-4h {pu4h_status} (counts not established)"
    return {"id": ROW_A28U, "subject": f"UE {k}", "status": st, "local": loc, "detail": f"{why}; {local['detail']}"}


def a28u_rows(n, node_id, sc, sca_map, res, dups, map_status, pu4h_status):
    """A2-8u for every expected UE 0 .. n-1: (rows, locals). The frozen run-level A2-8 is not called, wrapped or
    re-derived here; it stays in the A-2.1 rows verbatim. Reads only."""
    counts = a28u_counts(res)
    touched = A21.touched_nodes(res)
    locs = [a28u_local(k, node_id.get(k) if isinstance(node_id, dict) else None, sc, sca_map, counts, touched, dups)
            for k in range(n)]
    return [a28u_row(k, locs[k], map_status, pu4h_status) for k in range(n)], locs


def cr_violations(r_status, locals_, node_ids, touched):
    """the compatibility relation CR-1 .. CR-4 (design 4.5) between the frozen run-level A2-8 status R and the local
    outcomes L_k, under MAP-UE PASS. Returns the violated relations (empty = compatible).
    'compared' = a statistic whose outcome came from V-7 or V-8 (the comparisons the frozen code also makes)."""
    out = []
    L = [x["local"] for x in locals_]
    stats = [s_ for x in locals_ for s_ in x["stats"].values()]
    v1 = any(s_["step"] == "V-1" for s_ in stats)
    diff78 = any(s_["outcome"] == DIFFERENT and s_["step"] in ("V-7", "V-8") for s_ in stats)
    equal_any = any(s_["outcome"] == STAT_EQUAL for s_ in stats)
    compared_any = any(s_["step"] in ("V-7", "V-8") for s_ in stats)
    t = set(touched or ()) & set(node_ids)
    if r_status == FAIL and not (DIFFERENT in L or v1):
        out.append("CR-1: R FAIL without a DIFFERENT or a V-1 statistic")
    if diff78 and r_status != FAIL:
        out.append(f"CR-1: a statistic DIFFERENT by V-7 / V-8 but R {r_status}")
    if not v1 and (r_status == FAIL) != (DIFFERENT in L):
        out.append(f"CR-1: without duplicate records, R {r_status} but L {L}")
    if r_status == PASS and not (all(x in (EQUAL, NOT_COMPARED) for x in L) and equal_any and not t):
        out.append(f"CR-2: R PASS with L {L}, any equal statistic {equal_any}, touched {sorted(t)}")
    if r_status == NE and not (DIFFERENT not in L and (t or not compared_any)):
        out.append(f"CR-3: R NE with L {L}, touched {sorted(t)}, compared {compared_any}")
    if L and all(x == EQUAL for x in L) and r_status != PASS:
        out.append(f"CR-4: every L EQUAL but R {r_status}")
    return out


# ================================================================================================ I-3 ============
# ------------------------------------------------------------------------------------------ C-0 (design 4.1) -----
GNB_MODULE = PR.GNB                       # "M2S72Bridge.gnb1.cellularNic.mac"
TOKEN_INS = "H-ARQ TX: new pdu"
TOKEN_FB = "H-ARQ TX: feedback received"
RESULTS = ("ACK", "NACK")


def a1_gnb_module():
    """the gNB module A-1's harq_events() reads (its default argument): T-c0-module asserts it equals GNB_MODULE"""
    import inspect
    return inspect.signature(PA.harq_events).parameters["gnb"].default


def token_census(lines):
    """R-0e: regex-free counts of the raw log lines whose module is exactly the gNB MAC and whose message contains the
    insert / feedback token. No timestamp filter and no pattern: a malformed line is still counted. Pure (the caller
    reads the raw log). lines: the raw text lines of run-<cfg>.log.gz."""
    ins = fb = 0
    for line in lines:
        if not isinstance(line, str):
            continue
        p = line.split("|", 2)
        if len(p) < 3 or p[1] != GNB_MODULE:
            continue
        ins += TOKEN_INS in p[2]
        fb += TOKEN_FB in p[2]
    return {"insert": ins, "feedback": fb}


def _canon_ok(e):
    """R-0d: one canonical event: ('ins', t, node, p, cw) or ('fb', t, p, cw, result), integers (bool excluded)"""
    if not isinstance(e, tuple) or len(e) != 5 or e[0] not in ("ins", "fb"):
        return False
    if e[0] == "ins":
        return all(_is_int(v) for v in e[1:])
    return all(_is_int(v) for v in e[1:4]) and isinstance(e[4], str) and e[4] in RESULTS


def c0_a1_sequence(events):
    """the A-1 canonical sequence: harq_events() output as produced, in log order. Returns (sequence, problems)."""
    if not isinstance(events, list):
        return None, [f"A-1 event extraction missing or malformed ({type(events).__name__}): never an empty set (IG-1)"]
    seq = [tuple(e) if isinstance(e, (tuple, list)) else e for e in events]
    bad = [i for i, e in enumerate(seq) if not _canon_ok(e)]
    return seq, ([f"R-0d: A-1 events malformed at {bad[:5]}"] if bad else [])


def c0_a21_sequence(res):
    """the A-2.1 canonical sequence, reconstructed from res["pdus"] and res["fb"] merged by the log line index, with the
    preconditions R-0a .. R-0d. Never deduplicates, repairs, filters or re-sorts by anything but the line index.
    Returns (sequence or None, problems). Reads only."""
    probs = []
    if not isinstance(res, dict) or not isinstance(res.get("pdus"), dict) or not isinstance(res.get("fb"), list) \
            or not isinstance(res.get("counts"), dict):
        return None, ["A-2.1 replay result missing or malformed: never an empty set (IG-1)"]
    units, fb = list(res["pdus"].values()), res["fb"]
    if not all(isinstance(u, dict) for u in units) or not all(isinstance(x, dict) for x in fb):
        return None, ["R-0d: A-2.1 units or feedback lines are not objects"]
    n_ins = res["counts"].get("insert lines", 0)
    if not _is_int(n_ins) or len(units) != n_ins:
        probs.append(f"R-0a: {len(units)} PDU lifecycles vs {n_ins!r} insert lines (an insert lost by reconstruction, "
                     f"e.g. a repeated PDU id)")
    igi = [u.get("ins_gi") for u in units]
    fgi = [x.get("gi") for x in fb]
    if len(set(map(repr, igi))) != len(igi) or len(set(map(repr, fgi))) != len(fgi) or set(map(repr, igi)) & set(map(repr, fgi)):
        probs.append("R-0b: two events claim one log line (insert and feedback line indices not pairwise distinct)")
    if [x.get("j") for x in fb] != list(range(len(fb))):
        probs.append("R-0c: feedback entries not indexed 0 .. n-1 in order (repeated, dropped or reordered)")
    if not all(_is_int(g) for g in fgi) or any(b <= a for a, b in zip(fgi, fgi[1:])):
        probs.append("R-0c: feedback line indices not strictly increasing integers")
    ev = [(u.get("ins_gi"), ("ins", u.get("t_ins"), u.get("node"), u.get("p"), u.get("cw"))) for u in units]
    ev += [(x.get("gi"), ("fb", x.get("t"), x.get("p"), x.get("cw"), x.get("res"))) for x in fb]
    if not all(_is_int(g) for g, _ in ev):
        return None, probs + ["R-0d: a line index is not an integer"]
    bad = [e for _, e in ev if not _canon_ok(e)]
    if bad:
        probs.append(f"R-0d: malformed reconstructed events {bad[:3]}")
    return [e for _, e in sorted(ev, key=lambda ge: ge[0])], probs


def _digest(seq):
    return hashlib.sha256(json.dumps([list(e) for e in seq] if seq is not None else None,
                                     separators=(",", ":")).encode()).hexdigest()


def c0_row(a1_events, res, census):
    """C-0 (design 4.1): PASS iff R-0a .. R-0e hold and the A-1 and A-2.1 canonical sequences are equal element by
    element. Missing or malformed extraction is FAIL, never an empty evidence set (IG-1). Returns (row, info). Reads only."""
    a1, p1 = c0_a1_sequence(a1_events)
    a2, p2 = c0_a21_sequence(res)
    probs = p1 + p2
    if not (isinstance(census, dict) and _is_int(census.get("insert")) and _is_int(census.get("feedback"))):
        probs.append(f"R-0e: token census missing or malformed ({_show(census)}): never an empty set (IG-1)")
        census = None
    cnt = lambda seq, k: None if seq is None else sum(1 for e in seq if isinstance(e, tuple) and e[:1] == (k,))
    counts = {"a1": {"insert": cnt(a1, "ins"), "feedback": cnt(a1, "fb")},
              "a21": {"insert": cnt(a2, "ins"), "feedback": cnt(a2, "fb")}, "census": census}
    if census is not None:
        for k in ("insert", "feedback"):
            if not (census[k] == counts["a1"][k] == counts["a21"][k]):
                probs.append(f"R-0e: {k} token census {census[k]} vs A-1 {counts['a1'][k]} vs A-2.1 {counts['a21'][k]} "
                             f"(a malformed or skipped {k} line)")
    if a1 is not None and a2 is not None:
        if not a1 and not a2:
            probs.append("no gNB H-ARQ event in either sequence: nothing to compare (never an empty PASS, IG-1)")
        elif a1 != a2:
            i = next((i for i, (x, y) in enumerate(zip(a1, a2)) if x != y), min(len(a1), len(a2)))
            probs.append(f"parser divergence at event {i}: A-1 {a1[i] if i < len(a1) else '<end>'}, "
                         f"A-2.1 {a2[i] if i < len(a2) else '<end>'} (lengths {len(a1)} / {len(a2)})")
    info = {"sha256_a1": _digest(a1), "sha256_a21": _digest(a2), "lengths": [None if a1 is None else len(a1),
            None if a2 is None else len(a2)], "counts": counts, "problems": probs}
    detail = (f"sequences equal: {len(a1)} events ({counts['a1']['insert']} inserts, {counts['a1']['feedback']} feedback); "
              f"census {census}; sha256 {info['sha256_a1'][:16]}" if not probs else "; ".join(probs)
              + f"; sha256 A-1 {info['sha256_a1'][:16]}, A-2.1 {info['sha256_a21'][:16]}")
    return {"id": ROW_C0, "subject": "run", "status": FAIL if probs else PASS, "detail": detail}, info


# ------------------------------------------------------------------------------------------ PU-4h (design 4.3) ---
def pu4h_row(map_row, c0, rows, res=None):
    """PU-4h (design 4.3): MAP-UE, C-0 and the unchanged A-2.1 F1-d(i) verdict, derived from the SAME rows as the
    reported full-contract verdict (one replay). Returns (row, {"verdict_f1d_i", "verdict_full"}). Reads only."""
    vf, _ = A21.verdict(rows, "f1d-i")
    vfull, _ = A21.verdict(rows, "full")
    st = {r[0]: r[2] for r in rows}
    if map_row.get("status") != PASS:
        status, why = FAIL, f"UE-to-node mapping invalid (MAP-UE {map_row.get('status')})"
    elif c0.get("status") != PASS:
        status, why = FAIL, f"parser divergence (C-0 {c0.get('status')}): {str(c0.get('detail'))[:300]}"
    elif vf == f"{A21.VERSION} NOT VALID":
        status, why = FAIL, f"F1-d(i) NOT VALID: failing rows {sorted(k for k, v in st.items() if v == FAIL)}"
    elif vf == f"{A21.VERSION} INCOMPLETE":
        miss = sorted(k for k in A21.REQUIRED["f1d-i"] if st.get(k) not in (PASS, NX))
        touched = sorted(A21.touched_nodes(res)) if isinstance(res, dict) and "groups" in res else None
        status, why = NE, f"F1-d(i) INCOMPLETE: required rows not PASS {miss}" + (
            f"; A2-7 not evaluated for the touched nodes {touched}" if touched and "A2-7" in miss else "")
    elif vf == f"{A21.VERSION} VALID":
        status, why = PASS, "F1-d(i) VALID; MAP-UE PASS; C-0 PASS"
    else:
        raise EvaluationError(f"PU-4h: unknown A-2.1 verdict {vf!r}")
    extra = ""
    if isinstance(res, dict) and isinstance(res.get("fb"), list):
        from collections import Counter
        cls = Counter(x.get("cls") for x in res["fb"] if isinstance(x, dict))
        extra = (f"; line classes {dict(sorted(cls.items(), key=lambda kv: str(kv[0])))}; d*_tx {res.get('d_star')}; "
                 f"end states {res.get('end_states')}; handles {len(res.get('handles') or {})}")
    detail = f"{why}{extra}; full contract (reported; scheduler logging absent in E0v-N configurations): {vfull}"
    return {"id": ROW_PU4H, "subject": "run", "status": status, "detail": detail}, {"verdict_f1d_i": vf, "verdict_full": vfull}


# ------------------------------------------------------------------------------------------ PU-4o (design 4.6) ---
def occupancy_valid(o):
    """a valid A-2.1 occupancy: a non-empty object without an 'error' key (m2s72_peru.occupancy_log_order output)"""
    return isinstance(o, dict) and bool(o) and "error" not in o


def pu4o_local(k, n_k, per, x7):
    """the local comparison of UE k (design 4.6 steps 1 .. 7). Returns {local, step, detail}. Reads only."""
    def done(local, step, detail):
        return {"local": local, "step": step, "detail": f"ue[{k}] node {n_k}: {detail}"}
    if x7 is None:
        return done(NOT_COMPARED, "1", "no valid independent reference (A2-7 without x7)")
    if not (isinstance(x7, dict) and isinstance(x7.get("occupancy_equal"), dict) and isinstance(x7.get("skipped"), (list, tuple))):
        return done(DIFFERENT, "1", f"independent reference output malformed: {_show(x7)}")
    if not isinstance(per, dict) or n_k not in per:
        return done(NOT_COMPARED, "2", "no A-2.1 occupancy (no DL PDU for this UE; unexpected)")
    o = per[n_k].get("occupancy") if isinstance(per[n_k], dict) else None
    if not occupancy_valid(o):
        return done(DIFFERENT, "3", f"A-2.1 occupancy invalid: {_show(o)}")
    if n_k in x7["skipped"]:
        return done(NOT_COMPARED, "4", "uncertain attribution: censored or pending group")
    if n_k not in x7["occupancy_equal"]:
        return done(DIFFERENT, "5", "no comparison entry for an unskipped node (inconsistent evidence; never a pass)")
    if x7["occupancy_equal"][n_k] is True:
        return done(EQUAL, "6", "A-2.1 occupancy equals the independent UE-side reference")
    return done(DIFFERENT, "7", f"occupancy differs from the reference (occupancy_equal {_show(x7['occupancy_equal'][n_k])})")


def pu4o_row(k, local, map_status, pu4h_status, a27_status):
    """the row status of PU-4o UE k (design 4.6) over the local outcome"""
    loc = local["local"]
    if map_status == FAIL or pu4h_status == FAIL:
        st, why = FAIL, f"global: MAP-UE {map_status}, PU-4h {pu4h_status}"
    elif loc == DIFFERENT:
        st, why = FAIL, "local DIFFERENT"
    elif loc == NOT_COMPARED:
        st, why = NE, "local NOT COMPARED"
    elif map_status == PASS and pu4h_status == PASS and a27_status == PASS:
        st, why = PASS, "local EQUAL, A2-7 PASS, PU-4h PASS"
    else:
        st, why = NE, f"global: local EQUAL but A2-7 {a27_status}, PU-4h {pu4h_status}, MAP-UE {map_status}"
    return {"id": ROW_PU4O, "subject": f"UE {k}", "status": st, "local": loc, "detail": f"{why}; {local['detail']}"}


def pu4o_rows(n, node_id, per, x7, rows, map_status, pu4h_status):
    """PU-4o for every expected UE 0 .. n-1: (rows, locals). A2-7's status is read from the unchanged A-2.1 rows."""
    a27 = {r[0]: r[2] for r in rows}.get("A2-7")
    locs = [pu4o_local(k, node_id.get(k) if isinstance(node_id, dict) else None, per, x7) for k in range(n)]
    return [pu4o_row(k, locs[k], map_status, pu4h_status, a27) for k in range(n)], locs


# ================================================================================================ I-4 ============
# --------------------------------------------------------------------- historical A-1 report (design 4.10, 5.3) --
HISTORICAL_PU4_ID = "PU-4"
HISTORICAL_PU4_LABEL = "PU-4 (A-1, historical rule; reported, not a gate — DR-07b)"
HISTORICAL_A1_LABEL = "A-1, historical rule; not a current measurement (DR-07b)"


def extract_pu4(s5n_rows):
    """the one PU-4 row of the unchanged s5n evaluation, exactly as produced (a 4-tuple). A missing or repeated PU-4
    row is an EVALUATION ERROR: the historical result is never silently dropped or chosen."""
    if not isinstance(s5n_rows, (list, tuple)):
        raise EvaluationError(f"s5n rows missing or malformed ({type(s5n_rows).__name__})")
    found = [r for r in s5n_rows if isinstance(r, (list, tuple)) and len(r) == 4 and r[0] == HISTORICAL_PU4_ID]
    if len(found) != 1:
        raise EvaluationError(f"s5n rows hold {len(found)} PU-4 rows (exactly one expected): the historical A-1 result "
                              f"cannot be reported verbatim")
    r = found[0]
    if not all(isinstance(x, str) for x in r):
        raise EvaluationError(f"the s5n PU-4 row is malformed: {_show(r)}")
    return tuple(r)


def pu4_report_row(pu4_row):
    """the historical PU-4 under its reporting label: status and detail VERBATIM (PASS, FAIL or NOT EVALUATED as
    produced). It is not a wrapper gate row and never enters a gate list or the verdict."""
    r = tuple(pu4_row)
    if len(r) != 4 or r[0] != HISTORICAL_PU4_ID:
        raise EvaluationError(f"not the historical PU-4 row: {_show(r)}")
    return {"label": HISTORICAL_PU4_LABEL, "id": r[0], "subject": r[1], "status": r[2], "detail": r[3], "gating": False}


def split_per_ue(ms):
    """the s5n per-UE measurements split into (current, historical): `current` is every field except 'harq' (new
    objects); `historical` is {k: harq} with the A-1-derived 'harq' record verbatim. Reads only."""
    if not isinstance(ms, list) or not all(isinstance(m, dict) for m in ms):
        raise EvaluationError(f"s5n per-UE measurements missing or malformed ({type(ms).__name__})")
    current = [{k: copy.deepcopy(v) for k, v in m.items() if k != "harq"} for m in ms]
    hist = {}
    for i, m in enumerate(ms):
        k = m.get("k", i)
        if k in hist:
            raise EvaluationError(f"s5n per-UE measurements: UE {k} twice")
        hist[k] = copy.deepcopy(m.get("harq"))
    return current, hist


def historical_a1(pu4_row, harq_attribution, per_ue_harq):
    """the composed digest's historical.a1 (design 5.3): the s5n PU-4 row as a list, the A-1 summary and the per-UE
    A-1 'harq' records, all verbatim (deep copies), under the label that they are not current measurements"""
    r = tuple(pu4_row)
    if len(r) != 4 or r[0] != HISTORICAL_PU4_ID:
        raise EvaluationError(f"not the historical PU-4 row: {_show(r)}")
    return {"label": HISTORICAL_A1_LABEL, "pu4_row": list(r), "harq_attribution": copy.deepcopy(harq_attribution),
            "per_ue_harq": copy.deepcopy(per_ue_harq)}


# --------------------------------------------------------------- A-1 / A-2.1 agreement diagnostic (4.10) ---------
A1_ATTRIBUTED = ("a1a", "a1b")


def a21_canonical_feedback(res):
    """{canonical index: res["fb"] entry} for the feedback events of the A-2.1 canonical sequence (the order C-0
    compares: units and feedback lines merged by the log line index). Reads only."""
    ev = [(u.get("ins_gi"), None) for u in res["pdus"].values()] + [(x.get("gi"), x) for x in res["fb"]]
    ev.sort(key=lambda g: g[0])
    return {i: x for i, (_, x) in enumerate(ev) if x is not None}


def agreement(a1_events, a1_trace, res, c0_status):
    """the non-gating A-1 / A-2.1 agreement diagnostic (design 4.10, D-A1-10). Only when C-0 PASSED (the canonical
    indices align); otherwise it is not computed and nothing is inferred. For each feedback line, by its canonical
    index: A-1 attributed (A-1a / A-1b) -> agree / disagree with A-2.1's owner, or 'not comparable' when A-2.1 holds
    no owner (e.g. a censored line); A-1 not attributed (ambiguous / orphan) -> counted by A-2.1 class, never as
    agreement. Returns a report dict; it has no status and is never read by a gate. Reads only."""
    from collections import Counter
    base = {"diagnostic": "A-1 / A-2.1 agreement (report only; never a gate; D-A1-10)", "gating": False}
    if c0_status != PASS:
        return dict(base, computed=False, reason=f"C-0 {c0_status}: the canonical indices do not align; nothing inferred")
    if not isinstance(a1_trace, list):
        return dict(base, computed=False, reason="no A-1 trace")
    fbmap = a21_canonical_feedback(res)
    fb_idx = [i for i, e in enumerate(a1_events) if isinstance(e, (tuple, list)) and e[:1] == ("fb",)]
    traced = {}
    for t in a1_trace:
        if not (isinstance(t, (tuple, list)) and len(t) == 3):
            return dict(base, computed=False, reason=f"malformed A-1 trace entry {_show(t)}")
        if t[0] in traced:
            return dict(base, computed=False, reason=f"A-1 trace holds event {t[0]} twice")
        traced[t[0]] = t
    if set(traced) != set(fb_idx) or set(fb_idx) != set(fbmap):
        return dict(base, computed=False, reason=f"A-1 trace ({len(traced)}), A-1 feedback events ({len(fb_idx)}) and "
                                                 f"A-2.1 feedback lines ({len(fbmap)}) do not cover the same indices")
    agree, disagree, dis_cls, not_comp, unattr = 0, 0, Counter(), Counter(), Counter()
    examples = []
    for i in sorted(fb_idx):
        _, node, kind = traced[i]
        x = fbmap[i]
        cls, owner = x.get("cls"), x.get("owner")
        if kind in A1_ATTRIBUTED:
            if owner is None:
                not_comp[str(cls)] += 1
            elif owner == node:
                agree += 1
            else:
                disagree += 1
                dis_cls[str(cls)] += 1
                if len(examples) < 10:
                    examples.append({"index": i, "t_ps": x.get("t"), "process": x.get("p"), "result": x.get("res"),
                                     "a1": {"node": node, "rule": kind}, "a21": {"owner": owner, "class": cls}})
        else:
            unattr[f"{kind} -> {cls}"] += 1
    return dict(base, computed=True, a1_attributed=agree + disagree + sum(not_comp.values()), agree=agree,
                disagree=disagree, disagree_by_a21_class=dict(sorted(dis_cls.items())),
                a1_attributed_without_a21_owner=dict(sorted(not_comp.items())),
                a1_unattributed_by_a21_class=dict(sorted(unattr.items())), disagreements=examples)


# ================================================================================================ I-5 ============
# --------------------------------------------------------------------------- FGO evaluation (design 4.7) ---------
FGO_A24C = "A2-4c (node-identified scheduler evidence)"
TEST_ONLY_LABEL = "TEST ONLY (in-memory; never written; not a registry)"


def registry_view(loaded):
    """the part of a load_registry() result the FGO evaluation reads: known names (in order), admitted names, sha256"""
    return {"label": f"committed registry {os.path.relpath(loaded['path'], REPO) if os.path.isabs(str(loaded['path'])) else loaded['path']}",
            "known": list(loaded["known"]), "admitted": list(loaded["admitted"]), "sha256": loaded["sha256"]}


def test_only_view(admitted):
    """an in-memory registry view for tests that must reach the PASS path. Labelled TEST ONLY, never written, and it
    has no sha256 of a file: a verdict computed with it can never be mistaken for one computed with the registry."""
    return {"label": TEST_ONLY_LABEL, "known": coverage_names(), "admitted": list(admitted), "sha256": None}


def fgo(coverage, rows, view):
    """the first-genuine-occurrence evaluation (design 4.7): coverage = m2s72_a21.coverage(res, rows) of the run;
    rows = its A-2.1 rows; view = registry_view(load_registry()) or test_only_view(...). Returns
    {"held": [{feature, count, reason}], "exercised": {name: count}, "registry": label, "registry_sha256"}.
    Raises EvaluationError (exit 2) on coverage schema drift or a malformed view. Reads only."""
    names = coverage_names()
    if not (isinstance(view, dict) and view.get("known") == names and isinstance(view.get("admitted"), list)
            and all(isinstance(a, str) and a in names for a in view["admitted"])
            and len(set(view["admitted"])) == len(view["admitted"])):
        raise EvaluationError(f"FGO: registry view malformed or not the 18 coverage features: {_show(view)}")
    if not isinstance(coverage, (list, tuple)):
        raise EvaluationError(f"FGO: coverage output missing or malformed ({type(coverage).__name__})")
    counts = {}
    for e in coverage:
        if not (isinstance(e, (list, tuple)) and len(e) == 3 and isinstance(e[0], str) and _is_int(e[1]) and e[1] >= 0):
            raise EvaluationError(f"FGO: malformed coverage entry {_show(e)}")
        if e[0] in counts:
            raise EvaluationError(f"FGO: coverage feature {e[0]!r} twice")
        counts[e[0]] = e[1]
    missing = [n for n in names if n not in counts]
    if missing:
        raise EvaluationError(f"FGO: registry features absent from the run's coverage output (schema drift): {missing}")
    held = []
    for name in names:
        if counts[name] > 0 and name not in view["admitted"]:
            held.append({"feature": name, "count": counts[name], "reason": "first genuine occurrence"})
    for name in counts:
        if name not in names:
            held.append({"feature": name, "count": counts[name], "reason": "unknown feature"})
    st = {r[0]: r[2] for r in rows if isinstance(r, (list, tuple)) and len(r) == 4}
    if "A2-4c" not in st:
        raise EvaluationError("FGO: the A-2.1 rows hold no A2-4c row")
    if st["A2-4c"] in (PASS, FAIL):
        held.append({"feature": FGO_A24C, "count": 1, "reason": f"A2-4c exercised ({st['A2-4c']}): never genuine before"})
    return {"held": held, "exercised": {n: c for n, c in counts.items() if c > 0}, "registry": view["label"],
            "registry_sha256": view["sha256"]}


# ---------------------------------------------------------------- s5n gates minus PU-4 (design 4.8, 4.9) ----------
def s5n_info():
    """check_m2s72_s5n's E.INFO (the rows whose FAIL is information only), from the accepted modules, imported with
    the sys.argv isolation check_m2s72_s5n.py itself uses"""
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        import check_m2s72_s5v as S5V      # accepted; brings check_m2s72_e0 as E
    finally:
        sys.argv = argv
    return tuple(S5V.E.INFO), S5V.E.NE


def s5n_gates(s5n_rows, info=None, ne=None):
    """(gate failures, gate not-evaluated) of the unchanged s5n rows: the two expressions of check_m2s72_s5n.py:140-141,
    verbatim, then the historical PU-4 removed - the only change (DR-07b)"""
    if info is None or ne is None:
        info, ne = s5n_info()
    if not isinstance(s5n_rows, (list, tuple)) or not all(isinstance(r, (list, tuple)) and len(r) == 4 and
                                                          all(isinstance(x, str) for x in r[:3]) for r in s5n_rows):
        raise EvaluationError(f"s5n rows missing or malformed ({type(s5n_rows).__name__})")
    mine = s5n_rows
    gate_fail = sorted({r[0] for r in mine if r[2] == "FAIL" and r[0] not in info})
    ne_ = sorted({r[0] for r in mine if r[2] == ne and r[0].startswith(("PU-", "AV-"))})
    return [x for x in gate_fail if x != HISTORICAL_PU4_ID], [x for x in ne_ if x != HISTORICAL_PU4_ID]


# ------------------------------------------------------------------------- composed verdict (design 4.8) ----------
def check_wrapper_rows(n, rows):
    """every wrapper gate row present exactly once (MAP-UE, C-0, PU-4h; PU-4o and A2-8u for UE 0 .. n-1), each
    schema-valid; raises EvaluationError otherwise: a gate is never silently absent from the verdict"""
    if not _is_int(n) or n < 1 or not isinstance(rows, (list, tuple)):
        raise EvaluationError(f"wrapper rows: numUe {_show(n)} / rows {type(rows).__name__}")
    seen = {}
    for i, r in enumerate(rows):
        probs = validate_row(r, f"wrapper row {i}")
        if probs:
            raise EvaluationError(f"wrapper row malformed: {probs[:3]}")
        key = (r["id"], r["subject"])
        if key in seen:
            raise EvaluationError(f"wrapper row {r['id']} {r['subject']} twice")
        seen[key] = r["status"]
    want = {(rid, "run") for rid in RUN_ROWS} | {(rid, f"UE {k}") for rid in PER_UE_ROWS for k in range(n)}
    if set(seen) != want:
        raise EvaluationError(f"wrapper rows incomplete or unexpected: missing {sorted(want - set(seen))}, "
                              f"unexpected {sorted(set(seen) - want)}")
    return seen


def compose_verdict(n, rows, fgo_result, s5n_rows=None, info=None, ne=None):
    """the composed per-run verdict (design 4.8): wrapper gates (FAIL and NE both gate), the s5n gates minus the
    historical PU-4 (None in hrq, where s5n is not run), and the held features. Precedence FAIL > INCOMPLETE >
    HELD FOR REVIEW > PASS; held features are listed whatever the outcome. Takes no historical value and no
    diagnostic. Raises EvaluationError (-> error_verdict) when a gate or the FGO result is missing or malformed."""
    st = check_wrapper_rows(n, rows)
    if not (isinstance(fgo_result, dict) and isinstance(fgo_result.get("held"), list)):
        raise EvaluationError(f"FGO result missing or malformed: {_show(fgo_result)}")
    held = []
    for h in fgo_result["held"]:
        if not (isinstance(h, dict) and _text(h.get("feature")) and _text(h.get("reason"))):
            raise EvaluationError(f"malformed held feature {_show(h)}")
        if h["feature"] not in held:
            held.append(h["feature"])
    fails = {rid for (rid, _), s in st.items() if s == FAIL}
    nes = {rid for (rid, _), s in st.items() if s == NE}
    if s5n_rows is not None:
        f5, n5 = s5n_gates(s5n_rows, info, ne)
        clash = (set(f5) | set(n5)) & set(WRAPPER_ROWS)
        if clash:
            raise EvaluationError(f"s5n rows use wrapper row ids {sorted(clash)}")
        fails |= set(f5)
        nes |= set(n5)
    status = V_FAIL if fails else V_INCOMPLETE if nes else V_HELD if held else V_PASS
    return {"status": status, "exit": EXIT[status], "gate_failures": sorted(fails), "gate_not_evaluated": sorted(nes),
            "held_features": held, "held": copy.deepcopy(fgo_result["held"])}


def error_verdict(reason, refused=False):
    """REFUSED / EVALUATION ERROR (exit 2): never accompanied by a PASS of anything"""
    status = V_REFUSED if refused else V_ERROR
    return {"status": status, "exit": EXIT[status], "reason": str(reason), "gate_failures": [], "gate_not_evaluated": [],
            "held_features": [], "held": []}


def run_verdict(fn, *args, **kwargs):
    """compose_verdict at the boundary: Refused -> REFUSED, any other exception -> EVALUATION ERROR (exit 2)"""
    try:
        return fn(*args, **kwargs)
    except Refused as ex:
        return error_verdict(ex, refused=True)
    except Exception as ex:                      # includes EvaluationError
        return error_verdict(f"{type(ex).__name__}: {ex}")


# ================================================================================================ I-7 ============
# ------------------------------------------------------------------------- complete row sets (design 4.9) ---------
A21_ROW_IDS = ("A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-4c", "A2-5", "A2-6", "A2-7", "A2-8", "A2-9")


def check_a21_rows(rows, extra):
    """the accepted A-2.1 row set, exactly once each, well formed, with A2-7 and A2-8 consistent with their own
    structured output (extra["xa"], extra["scalars"]): never a missing, duplicated or unexplained row. Raises
    EvaluationError."""
    if not isinstance(rows, (list, tuple)):
        raise EvaluationError(f"A-2.1 rows missing ({type(rows).__name__})")
    ids = []
    for r in rows:
        if not (isinstance(r, (list, tuple)) and len(r) == 4 and all(isinstance(x, str) for x in r)):
            raise EvaluationError(f"A-2.1 row malformed: {_show(r)}")
        if r[1] != "run" or r[2] not in (PASS, FAIL, NE, NX):
            raise EvaluationError(f"A-2.1 row {r[0]}: subject {r[1]!r}, status {r[2]!r}")
        ids.append(r[0])
    dup = sorted({i for i in ids if ids.count(i) > 1})
    if dup or sorted(ids) != sorted(A21_ROW_IDS):
        raise EvaluationError(f"A-2.1 row set incomplete or unexpected: missing {sorted(set(A21_ROW_IDS) - set(ids))}, "
                              f"unexpected {sorted(set(ids) - set(A21_ROW_IDS))}, duplicated {dup}")
    st = {r[0]: r[2] for r in rows}
    if not isinstance(extra, dict) or "xa" not in extra or "scalars" not in extra:
        raise EvaluationError("A-2.1 structured output (xa, scalars) missing")
    x7, x8 = extra["xa"], extra["scalars"]
    if x7 is None:
        if st["A2-7"] not in (NE, FAIL):
            raise EvaluationError(f"A2-7 {st['A2-7']} without its reference output")
    else:
        if not (isinstance(x7, dict) and isinstance(x7.get("occupancy_equal"), dict) and isinstance(x7.get("skipped"), list)
                and isinstance(x7.get("confirmed"), dict)):
            raise EvaluationError(f"A2-7 reference output malformed: {_show(x7)}")
        if st["A2-7"] == PASS and (x7["skipped"] or not all(v is True for v in x7["occupancy_equal"].values())):
            raise EvaluationError("A2-7 PASS with skipped nodes or an unequal occupancy")
    if st["A2-8"] == PASS and not (isinstance(x8, list) and x8):
        raise EvaluationError("A2-8 PASS without any compared statistic")
    if st["A2-8"] != PASS and x8 is not None:
        raise EvaluationError(f"A2-8 {st['A2-8']} with compared statistics")
    return st


# The row contract of the accepted check_m2s72_s5n.run_one() for an E0v-N configuration at N UEs, derived from the
# accepted source (I7-R1). name = f"{cfg}-0" (rep 0). B.evaluate(full=True, ref=None) with the clock class "Ca"
# (BN_BASE[cfg] = "M2S72-H-<q0|qdu>-Ca-n<N>"):
#   f0_rows   F1.f01 -> F0-1 (renamed "F0-1 (info)" by run_one); F1.f02 -> F0-2, renamed "I-2" by f0_rows and
#             "I-2 strict (info)" by check_m2s72_i2h.relabel; F1.f03 F0-3; F2.f04 or (session problems) F2.add F0-4;
#             F1.f05 F0-5; F2.add F0-7d; F2.f06 F0-6; F2.f08 F0-8: each exactly once (no early return before its add;
#             F1.f02's early return follows its own add)
#   i_rows    I-1, I-3 once each
#   m2_rows   M2 once per slave k in range(N), subject "<name> slave <k>" (RunEval builds ev.m2 for every k)
#   m3_rows   M3 and M3d once each per pair (i < j) of the slaves whose M2-S6 evaluation succeeded (ev.series):
#             CONDITIONAL. A slave whose evaluation raised has an "X k<k>" M2-S6 row, so its M2 row FAILs: when
#             every M2 row PASSes, every pair is present; otherwise a subset (and the run already fails on M2)
#   m4_rows   M4 "<name> GM drift" once (clk "Ca" != "ideal"); "<name> TT clocks" only with clk "Eall": never here
#   i5_rows   not called (ref None)
# then i2h_rows: I-2H once per DS-TT, subject "<name> DS-TT <k>"; EOR once (NOT APPLICABLE); the adapter's observe():
# Q8 once per UE (gptp -> E.q8_rows, subject "<name> UE <k>"); validate(): PU-1, PU-4, PU-5 once ("run"), PU-2,
# PU-3, AV-1, AV-2, AV-3 once per UE ("UE <k>"); Q8-v, SG-403, MG-1 once each. Nothing else.
S5N_ONCE_NAME = ("F0-1 (info)", "I-2 strict (info)", "F0-3", "F0-4", "F0-5", "F0-6", "F0-7d", "F0-8", "I-1", "I-3",
                 "EOR", "Q8-v", "SG-403", "MG-1")
S5N_ONCE_RUN = ("PU-1", "PU-4", "PU-5")
S5N_PER_UE = ("PU-2", "PU-3", "AV-1", "AV-2", "AV-3")
S5N_STATUSES = (PASS, FAIL, NE, NA)
S5N_DETAIL_WIDTH = 400                     # run_one writes str(detail)[:400]


def parse_name_n(cfg):
    """N of an E0v-N configuration name admitted by the run guard"""
    guard(cfg, "run")
    return int(re.search(r"-n(\d+)-f", cfg).group(1))


def s5n_row_contract(cfg, n):
    """(mandatory {(id, subject)}, conditional {(id, subject)}) of run_one at N"""
    name = f"{cfg}-0"
    mand = {(i, name) for i in S5N_ONCE_NAME} | {(i, "run") for i in S5N_ONCE_RUN}
    mand |= {(i, f"UE {k}") for i in S5N_PER_UE for k in range(n)}
    mand |= {("M2", f"{name} slave {k}") for k in range(n)} | {("I-2H", f"{name} DS-TT {k}") for k in range(n)}
    mand |= {("Q8", f"{name} UE {k}") for k in range(n)} | {("M4", f"{name} GM drift")}
    cond = {(t, f"{name} pair ({i},{j})") for t in ("M3", "M3d") for i in range(n) for j in range(i + 1, n)}
    return mand, cond


def s5n_written_block(rows):
    """the CORRECTNESS lines run_one writes for these rows, exactly (its format and 400-character detail cut)"""
    return "".join(f"  {r[2]:<15} | {r[0]} | {r[1]} | {str(r[3])[:S5N_DETAIL_WIDTH]}\n" for r in rows)


def s5n_written_section(text):
    """(the CORRECTNESS block, the per-run verdict line) of an s5n <cfg>.check.txt"""
    head = "\n\nCORRECTNESS (gates)\n"
    tail = "\nper-run verdict: "
    if text.count(head) != 1 or text.count(tail) != 1 or text.index(head) > text.index(tail):
        raise EvaluationError("s5n check.txt: not the accepted layout (CORRECTNESS section / per-run verdict line)")
    block = text[text.index(head) + len(head):text.index(tail)]          # the row lines, each ending in "\n"
    vline = text[text.index(tail) + len(tail):].split("\n", 1)[0]
    return block, vline


def check_s5n_rows(s5n_rows, n, cfg, check_txt, s5n_digest, info, ne):
    """the s5n rows of the run against the accepted contract (I7-R1): mandatory identities and multiplicities, the
    conditional M3 / M3d pairs, no duplicate or unexpected row, the CORRECTNESS lines of check.txt equal to the rows
    rendered exactly as run_one writes them (detail cut at 400 characters), and the digest consistent with the rows
    (count, gate lists by the accepted predicate, verdict line). Raises EvaluationError naming every defect."""
    if not isinstance(s5n_rows, (list, tuple)) or not all(
            isinstance(r, (list, tuple)) and len(r) == 4 and all(isinstance(x, str) for x in r[:3]) for r in s5n_rows):
        raise EvaluationError("s5n rows missing or malformed")
    probs = []
    bad_st = sorted({f"{r[0]} {r[2]}" for r in s5n_rows if r[2] not in S5N_STATUSES})
    if bad_st:
        probs.append(f"statuses outside {S5N_STATUSES}: {bad_st[:5]}")
    keys = Counter((r[0], r[1]) for r in s5n_rows)
    mand, cond = s5n_row_contract(cfg, n)
    dup = sorted(f"{k[0]} | {k[1]}" for k, c in keys.items() if c > 1)
    miss = sorted(f"{k[0]} | {k[1]}" for k in mand if k not in keys)
    unexp = sorted(f"{k[0]} | {k[1]}" for k in keys if k not in mand and k not in cond)
    if dup:
        probs.append(f"duplicated rows {dup[:5]}")
    if miss:
        probs.append(f"missing mandatory rows {miss[:8]} ({len(miss)})")
    if unexp:
        probs.append(f"unexpected rows {unexp[:8]} ({len(unexp)})")
    st = {(r[0], r[1]): r[2] for r in s5n_rows}
    pairs3 = {k[1] for k in keys if k[0] == "M3"}
    pairs3d = {k[1] for k in keys if k[0] == "M3d"}
    if pairs3 != pairs3d:
        probs.append(f"M3 / M3d pairs differ: {sorted(pairs3 ^ pairs3d)[:4]}")
    m2_all_pass = all(st.get(("M2", f"{cfg}-0 slave {k}")) == PASS for k in range(n))
    if m2_all_pass and not cond <= set(keys):
        probs.append(f"every M2 row PASSes but M3 / M3d pairs are missing: {sorted(f'{a} | {b}' for a, b in cond - set(keys))[:4]}")
    if st.get(("EOR", f"{cfg}-0")) not in (None, NA):
        probs.append(f"EOR {st.get(('EOR', f'{cfg}-0'))!r} (run_one writes NOT APPLICABLE)")
    try:
        block, vline = s5n_written_section(check_txt)
        if block != s5n_written_block(s5n_rows):
            exp = s5n_written_block(s5n_rows).splitlines()
            got = block.splitlines()
            i = next((i for i, (a, b) in enumerate(zip(exp, got)) if a != b), min(len(exp), len(got)))
            probs.append(f"check.txt rows differ from the evaluated rows at line {i}: written "
                         f"{got[i][:160] if i < len(got) else '<end>'!r}, expected {exp[i][:160] if i < len(exp) else '<end>'!r}")
    except EvaluationError as ex:
        probs.append(str(ex))
        vline = None
    gate_fail = sorted({r[0] for r in s5n_rows if r[2] == "FAIL" and r[0] not in info})
    ne_ = sorted({r[0] for r in s5n_rows if r[2] == ne and r[0].startswith(("PU-", "AV-"))})
    want_v = "PASS" if not gate_fail and not ne_ else "FAIL " + " ".join(gate_fail + [f"NE:{x}" for x in ne_])
    c = s5n_digest.get("correctness") if isinstance(s5n_digest, dict) else None
    if not isinstance(c, dict):
        probs.append("s5n digest without its correctness section")
    else:
        if c.get("rows") != len(s5n_rows):
            probs.append(f"s5n digest counts {c.get('rows')!r} rows, the evaluation {len(s5n_rows)}")
        if c.get("gate_failures") != gate_fail or c.get("per_ue_not_evaluated") != ne_:
            probs.append(f"s5n digest gate lists {c.get('gate_failures')} / {c.get('per_ue_not_evaluated')} differ from the rows "
                         f"({gate_fail} / {ne_})")
    if vline is not None and vline != want_v:
        probs.append(f"s5n verdict line {vline!r} differs from the rows ({want_v!r})")
    if s5n_digest.get("numUe") != n:
        probs.append(f"s5n digest numUe {s5n_digest.get('numUe')!r} != {n}")
    if probs:
        raise EvaluationError(f"s5n rows violate the accepted row contract: {probs}")
    return vline


# --------------------------------------------------------- current H-ARQ values and availability (design 5.3) -----
HARQ_COUNT_FIELDS = ("inserts", "transmissions", "retransmissions", "feedback", "ack", "nack", "discarded",
                     "transmissions_per_acked_pdu", "harq_latency_ps", "feedback_age_ps", "end_states", "lines_by_class")


def _unavail(reason):
    return {"available": False, "reason": reason}


def harq_a21_groups(n_k, per, touched, pu4h_row, pu4o_row, a28u_row):
    """the current per-UE H-ARQ values of UE k from the single A-2.1 replay, each group with its availability:
    counts only with PU-4h PASS and the node untouched; occupancy only with PU-4o UE k PASS; the Simu5G cross-check
    only with A2-8u UE k PASS. An unavailable group carries a reason and no value: never 0, never an A-1 value."""
    o = per.get(n_k) if isinstance(per, dict) else None
    if pu4h_row["status"] != PASS:
        counts = _unavail(f"PU-4h {pu4h_row['status']}")
    elif n_k in touched:
        counts = _unavail("uncertain attribution: censored or pending group")
    elif o is None:
        counts = _unavail("no A-2.1 lifecycle for this UE")
    else:
        counts = {"available": True, **{f: copy.deepcopy(o[f]) for f in HARQ_COUNT_FIELDS}}
        acked = o["transmissions_per_acked_pdu"]
        n_ack = sum(acked.values())
        counts["harq_error_rate"] = (o["nack"] / o["feedback"]) if o["feedback"] else None
        counts["harq_tx_attempts"] = (sum(int(t) * c for t, c in acked.items()) / n_ack) if n_ack else None
    if pu4o_row["status"] == PASS and o is not None and occupancy_valid(o.get("occupancy")):
        occ = {"available": True, "occupancy": copy.deepcopy(o["occupancy"])}
    else:
        occ = _unavail(f"PU-4o {pu4o_row['status']} (local {pu4o_row.get('local')})")
    if a28u_row["status"] == PASS:
        sim = {"available": True, "status": PASS, "detail": a28u_row["detail"]}
    else:
        sim = _unavail(f"A2-8u {a28u_row['status']} (local {a28u_row.get('local')})")
    return {"counts": counts, "occupancy": occ, "simu5g": sim}


def _occ_mean(occ):
    h = occ.get("busy_at_tti_start_hist") if isinstance(occ, dict) else None
    if not isinstance(h, dict) or not h:
        return None
    tot = sum(h.values())
    return (sum(int(b) * c for b, c in h.items()) / tot) if tot else None


ACROSS_HARQ = (("harq_error_rate", "counts", lambda g: g.get("harq_error_rate")),
               ("harq_tx_attempts", "counts", lambda g: g.get("harq_tx_attempts")),
               ("retransmissions", "counts", lambda g: g.get("retransmissions")),
               ("occupancy_busy_mean", "occupancy", lambda g: _occ_mean(g.get("occupancy"))))


def across_harq_a21(per_ue_groups):
    """across-UE aggregates of the current A-2.1 values: all-or-nothing. A metric is computed only if EVERY expected
    UE's value is available (and defined); otherwise {available: false, missing_ues}. No partial aggregate."""
    out = {}
    for key, group, get in ACROSS_HARQ:
        vals, missing = [], []
        for k, g in enumerate(per_ue_groups):
            gv = g[group]
            v = get(gv) if gv.get("available") else None
            if v is None or not math.isfinite(v):
                missing.append(k)
            else:
                vals.append((k, v))
        if missing or not vals:
            out[key] = {"available": False, "missing_ues": missing or list(range(len(per_ue_groups)))}
        else:
            w = max(vals, key=lambda kv: kv[1])
            v = [x for _, x in vals]
            out[key] = {"available": True, "min": min(v), "max": max(v), "spread": max(v) - min(v), "worst_ue": w[0],
                        "worst": w[1], "n": len(v)}
    return out


def composed_digest(s5n_digest, s5n_verdict_line, s5n_rows, wrapper_rows, verdict, a21_out, per, touched, node_id,
                    agreement_report, inputs):
    """the composed digest <cfg>.s5n21.digest.json (design 5.3), field by field from its owner. The s5n digest is
    read, never modified."""
    n = s5n_digest["numUe"]
    current, hist_harq = split_per_ue(s5n_digest["performance"]["per_ue"])
    rows_by = {(r["id"], r["subject"]): r for r in wrapper_rows}
    groups = []
    for k in range(n):
        groups.append(harq_a21_groups(node_id[k], per, touched, rows_by[(ROW_PU4H, "run")], rows_by[(ROW_PU4O, f"UE {k}")],
                                      rows_by[(ROW_A28U, f"UE {k}")]))
    for k, m in enumerate(current):
        if m.get("k") != k:
            raise EvaluationError(f"s5n per-UE measurement {k} carries k {m.get('k')!r}")
        m["harq_a21"] = groups[k]
    pu4 = extract_pu4(s5n_rows)
    d = {"schema": DIGEST_SCHEMA,
         **{f: copy.deepcopy(s5n_digest[f]) for f in ("config", "kind", "option", "placement", "numUe", "harq16", "dl_factor")},
         "correctness": {"verdict": {f: verdict[f] for f in VERDICT_KEYS}, "rows": copy.deepcopy(wrapper_rows),
                         "s5n": {"verdict_line": s5n_verdict_line,
                                 "gate_failures": copy.deepcopy(s5n_digest["correctness"]["gate_failures"]),
                                 "per_ue_not_evaluated": copy.deepcopy(s5n_digest["correctness"]["per_ue_not_evaluated"]),
                                 "rows": s5n_digest["correctness"]["rows"]},
                         "a21": {"rows": [list(r) for r in a21_out["rows"]], "verdict_f1d_i": a21_out["verdict_f1d_i"],
                                 "verdict_full": a21_out["verdict_full"], "coverage": [list(c) for c in a21_out["coverage"]]}},
         "performance": {"per_ue": current, "across": copy.deepcopy(s5n_digest["performance"]["across"]),
                         "across_harq_a21": across_harq_a21(groups), "totals": copy.deepcopy(s5n_digest["performance"]["totals"])},
         "historical": {"a1": historical_a1(pu4, s5n_digest["performance"]["harq_attribution"], hist_harq)},
         "diagnostics": {"agreement": copy.deepcopy(agreement_report)},
         "mac_grammar_census": copy.deepcopy(s5n_digest["mac_grammar_census"]),
         "inputs": copy.deepcopy(inputs)}
    return d
