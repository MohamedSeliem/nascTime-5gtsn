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
INPUTS_KEYS = ("log_sha256", "sca_sha256", "registry_sha256", "code", "c0", "s5n_adapter_validated")
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
                        rs[r[0]] = r[2]
                    else:
                        probs.append(f"correctness.a21.rows[{i}]: must be [id, subject, status, detail] text")
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
        if _keys(a1, HISTORICAL_A1_KEYS, "historical.a1", probs) and not _text(a1["label"]):
            probs.append("historical.a1.label must be non-empty text")
    if not isinstance(d["diagnostics"], dict):
        probs.append(f"diagnostics: must be an object, got {type(d['diagnostics']).__name__}")
    if not isinstance(d["mac_grammar_census"], list):
        probs.append("mac_grammar_census: must be a list")
    inp = d["inputs"]
    if _keys(inp, INPUTS_KEYS, "inputs", probs):
        if not (isinstance(inp["registry_sha256"], str) and re.fullmatch(r"[0-9a-f]{64}", inp["registry_sha256"])):
            probs.append(f"inputs.registry_sha256 {_show(inp['registry_sha256'])} is not a sha256")
    _finite_json(d, "digest", probs)
    return probs
