#!/usr/bin/env python3
"""WP-A1 CLI: the E0v-N per-run evaluation with A-2.1 as the per-UE H-ARQ source (design revision 2.1, 57a80ca).

    python3 -I -B check_m2s72_s5n21.py hrq         <runs> <cfg> <records dir> [--t0 <s>] [--expect <file>]
    python3 -I -B check_m2s72_s5n21.py hrq-fixture <fixture dir> <records dir> [--expect <file>]
    python3 -I -B check_m2s72_s5n21.py run         <runs> <cfg> <records dir> [--t0 <s>]
    python3 -I -B check_m2s72_s5n21.py controls    <runs> <cfg> <records dir> [--t0 <s>]      (I-8: not implemented)

hrq          the H-ARQ rows of one run: ONE A-2.1 replay (F1-d(i) and full verdicts from the same rows), MAP-UE, C-0,
             PU-4h, PU-4o, A2-8u, the first-genuine-occurrence review (committed registry only), the composed verdict,
             the A-1 rule reported for comparison (frozen m2s72_peru, never a gate) and the non-gating agreement
             diagnostic. s5n is not run and S5N_ADAPTER_VALIDATED is not read. Names: the E0v-N guard, plus
             M2S72-E0v-q0-f1 (V-N1) and M2S72-E0vN-q0-one0-n2-f1_A2V1 (V-V1). Inputs: <runs>/run-<cfg>.log.gz,
             <runs>/<cfg>/<cfg>/0.sca, the run's files for the node ids (Run72), $SIMU5G_ROOT (A2-0s).
run          the E0v-N per-run evaluation: REFUSED unless S5N_ADAPTER_VALIDATED is non-empty (decision S5-2-D2; never
             set here). The accepted check_m2s72_s5n.run_one() runs unchanged (its records under s5n/, byte for byte);
             its PU-4 is reported verbatim and never gates; the s5n gates otherwise keep their exact semantics. One
             A-2.1 replay gives MAP-UE, C-0, PU-4h, PU-4o, A2-8u, FGO and the current per-UE H-ARQ values. One run per
             process. The records are written into <records dir>.incomplete and renamed to <records dir> only when
             complete: <records dir> exists only for a completed evaluation.
hrq-fixture  the same on the committed real-chain fixture (m2s72_a21_realchain.load_fixture: pinned sha256), t0 = 0,
             no .sca; SIMU5G_ROOT required. "fixture (prefix of the sealed A2-V1 run); not an E0v-N run; not an A2-V1
             acceptance".
--t0 <s>     start of the evaluation window in seconds (default 2, as check_m2s72_a21.py)
--expect     a declared expectation file (schema m2s72-s5n21-expect/1), compared after the evaluation

run: s5n/<cfg>.check.txt, s5n/<cfg>.digest.json (the unchanged s5n records), a21-<cfg>.txt / .json,
     <cfg>.s5n21.txt, <cfg>.s5n21.json, <cfg>.s5n21.digest.json (the composed digest) and SHA256SUMS.
hrq / hrq-fixture:
<records dir> must not exist (its parent must); it is created and receives, durably (fsync):
    a21-<cfg>.txt / .json     the A-2.1 record of the single replay, with both contract verdicts
    hrq-<cfg>.txt / .json     the composed H-ARQ record
    hrq-<cfg>.expect.txt      with --expect: every declared value against the evaluated one
(<cfg> = f3-fixture in hrq-fixture). Nothing else is written; the inputs are hashed before and after.

Exit codes (design 4.8, 5.1): 0 PASS, 1 FAIL, 2 REFUSED / EVALUATION ERROR, 3 HELD FOR REVIEW, 4 INCOMPLETE;
with --expect: 0 every expectation met, 5 EXPECTATION MISMATCH, 2 malformed expectation file or evaluation error.
"""
import gzip
import hashlib
import json
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import m2s72_e0vn21 as W  # noqa: E402

MODES = ("run", "hrq", "hrq-fixture", "controls")
FIXTURE_CFG = "f3-fixture"
FIXTURE_LABEL = "fixture (prefix of the sealed A2-V1 run); not an E0v-N run; not an A2-V1 acceptance"
HRQ_SCHEMA = "m2s72-s5n21-hrq/1"
EXPECT_SCHEMA = "m2s72-s5n21-expect/1"
CODE = ("m2s72_e0vn21.py", "check_m2s72_s5n21.py", "m2s72_a21.py", "check_m2s72_a21.py", "m2s72_a2.py",
        "m2s72_a2probe.py", "m2s72_harqx.py", "m2s72_peru.py", "m2s72_peru_adapter.py", "m2s72_a21_realchain.py")


class Usage(Exception):
    pass


class ExpectationError(Exception):
    """a malformed expectation file (exit 2)"""


# ------------------------------------------------------------------------------------------------- arguments ----
def parse_args(argv):
    if len(argv) < 2 or argv[1] not in MODES:
        raise Usage("no mode")
    mode, rest = argv[1], list(argv[2:])
    opts = {"t0": None, "expect": None}
    pos = []
    while rest:
        a = rest.pop(0)
        if a in ("--t0", "--expect"):
            if not rest:
                raise Usage(f"{a} needs a value")
            key = a[2:]
            if opts[key] is not None:
                raise Usage(f"{a} given twice")
            opts[key] = rest.pop(0)
        elif a.startswith("-"):
            raise Usage(f"unknown option {a}")
        else:
            pos.append(a)
    if mode == "controls":
        raise W.Refused(f"mode '{mode}' is not implemented in this increment (design revision 2.1, section 9: I-8)")
    if mode in ("hrq", "run"):
        if len(pos) != 3:
            raise Usage(f"{mode} <runs> <cfg> <records dir>")
        if mode == "run" and opts["expect"] is not None:
            raise Usage("run has no --expect (expectations are compared by hrq)")
        args = {"mode": mode, "runs": pos[0], "cfg": pos[1], "recdir": pos[2]}
    else:
        if len(pos) != 2:
            raise Usage("hrq-fixture <fixture dir> <records dir>")
        if opts["t0"] is not None:
            raise Usage("hrq-fixture has no --t0 (the window is the whole prefix, t0 = 0)")
        args = {"mode": mode, "fixture": pos[0], "recdir": pos[1], "cfg": FIXTURE_CFG}
    t0 = 2.0
    if opts["t0"] is not None:
        try:
            t0 = float(opts["t0"])
        except ValueError:
            raise Usage(f"--t0 {opts['t0']!r} is not a number of seconds")
        if not (t0 >= 0 and t0 < 1e6):
            raise Usage(f"--t0 {opts['t0']!r} out of range")
    args["t0_ps"] = 0 if mode == "hrq-fixture" else int(round(t0 * W.A21.S))
    args["expect"] = opts["expect"]
    return args


# ---------------------------------------------------------------------------------------------- expectations ----
FLAT = {"verdict.status", "verdict.exit", "verdict.gate_failures", "verdict.gate_not_evaluated", "verdict.held_features",
        "verdict.held_features_if_exercised", "a21.verdict_f1d_i", "a21.verdict_full", "census.insert",
        "census.feedback", "c0.status", "c0.lengths", "nodes", "end_states", "unresolved", "a2_7.occupancy_equal",
        "a1.pu4_status", "touched_nodes"}
PATTERNS = [r"rows\.(MAP-UE|C-0|PU-4h)", r"rows\.(PU-4o|A2-8u)\.UE \d+(\.local)?", r"a21\.rows\.A2-[0-9a-z]+",
            r"coverage\..+", r"a1\.summary\.[a-z0-9_]+", r"per_ue\.\d+\.(inserts|transmissions|retransmissions|feedback|ack|nack|discarded)",
            r"agreement\.(computed|agree|disagree|a1_attributed)"]


def known_key(k):
    import re
    return k in FLAT or any(re.fullmatch(p, k) for p in PATTERNS)


def load_expect(path, cfg):
    try:
        with open(path, encoding="utf-8") as fh:
            e = json.load(fh)
    except (OSError, ValueError, RecursionError) as ex:
        raise ExpectationError(f"expectation file {path}: {type(ex).__name__}: {ex}")
    if not isinstance(e, dict) or set(e) - {"schema", "config", "expect", "note"} or not {"schema", "config", "expect"} <= set(e):
        raise ExpectationError("expectation file: top level must be {schema, config, expect[, note]}")
    if e["schema"] != EXPECT_SCHEMA:
        raise ExpectationError(f"expectation file: schema {e['schema']!r} != {EXPECT_SCHEMA!r}")
    if e["config"] != cfg:
        raise ExpectationError(f"expectation file is for {e['config']!r}, not {cfg!r}")
    if not isinstance(e["expect"], dict) or not e["expect"]:
        raise ExpectationError("expectation file: 'expect' must be a non-empty object")
    unknown = sorted(k for k in e["expect"] if not isinstance(k, str) or not known_key(k))
    if unknown:
        raise ExpectationError(f"expectation file: unknown keys {unknown}")
    if "verdict.held_features_if_exercised" in e["expect"] and "verdict.held_features" not in e["expect"]:
        raise ExpectationError("verdict.held_features_if_exercised needs verdict.held_features")
    return e


ABSENT = "<absent>"


def evaluated_value(key, out):
    """the evaluated value of a declared key, from the record itself (never recomputed)"""
    try:
        if key.startswith("verdict."):
            f = key.split(".", 1)[1]
            if f in ("held_features", "held_features_if_exercised"):
                return sorted(out["verdict"]["held_features"])
            v = out["verdict"][f]
            return sorted(v) if isinstance(v, list) else v
        if key.startswith("rows."):
            parts = key.split(".")
            rid = parts[1]
            subj = parts[2] if len(parts) > 2 else "run"
            r = next(x for x in out["rows"] if x["id"] == rid and x["subject"] == subj)
            return r["local"] if len(parts) > 3 else r["status"]
        if key.startswith("a21.rows."):
            return next(x[2] for x in out["a21"]["rows"] if x[0] == key.split(".", 2)[2])
        if key in ("a21.verdict_f1d_i", "a21.verdict_full"):
            return out["a21"][key.split(".")[1]]
        if key.startswith("coverage."):
            return next(c for n, c, _ in out["a21"]["coverage"] if n == key.split(".", 1)[1])
        if key.startswith("census."):
            return out["c0"]["census"][key.split(".")[1]]
        if key == "c0.status":
            return next(x["status"] for x in out["rows"] if x["id"] == "C-0")
        if key == "c0.lengths":
            return out["c0"]["lengths"]
        if key == "nodes":
            return out["nodes"]
        if key in ("end_states", "unresolved", "touched_nodes"):
            return out["a21"][key]
        if key == "a2_7.occupancy_equal":
            return out["a21"]["a2_7"]["occupancy_equal"] if out["a21"]["a2_7"] else None
        if key == "a1.pu4_status":
            return out["historical"]["a1_pu4_row"][2]
        if key.startswith("a1.summary."):
            return out["historical"]["a1_summary"][key.split(".", 2)[2]]
        if key.startswith("per_ue."):
            _, node, field = key.split(".")
            return out["a21"]["per_ue"][node][field]
        if key.startswith("agreement."):
            return out["diagnostics"]["agreement"][key.split(".", 1)[1]]
    except (KeyError, StopIteration, TypeError, IndexError):
        return ABSENT
    return ABSENT


def compare_expect(e, out):
    """[(key, declared, evaluated, MATCH / MISMATCH)]; held_features_if_exercised adds each listed feature to the
    declared held set iff its coverage count > 0 (a declared condition, design 8.2)"""
    exp = dict(e["expect"])
    if "verdict.held_features_if_exercised" in exp:
        cov = {n: c for n, c, _ in out["a21"]["coverage"]}
        cond = exp.pop("verdict.held_features_if_exercised")
        base = list(exp["verdict.held_features"])
        exp["verdict.held_features"] = base + [f for f in cond if cov.get(f, 0) > 0]
    table = []
    for k in sorted(exp):
        want = exp[k]
        got = evaluated_value(k, out)
        if isinstance(want, list) and isinstance(got, list) and k in ("verdict.held_features", "verdict.gate_failures",
                                                                       "verdict.gate_not_evaluated", "touched_nodes"):
            want, got = sorted(map(str, want)), sorted(map(str, got))
        table.append((k, want, got, "MATCH" if want == got else "MISMATCH"))
    return table


# --------------------------------------------------------------------------------------------------- helpers ----
def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def raw_lines(path):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        return fh.read().splitlines(True)


def fresh_dir(recdir):
    parent = os.path.dirname(os.path.abspath(recdir))
    if os.path.lexists(recdir):
        raise W.Refused(f"records dir {recdir} exists (never reused)")
    if not os.path.isdir(parent):
        raise W.Refused(f"the parent of the records dir {recdir} does not exist")


def code_identity():
    return {f: sha256_file(os.path.join(HERE, f)) for f in CODE if os.path.isfile(os.path.join(HERE, f))}


# -------------------------------------------------------------------------------------------- the evaluation ----
def gather_hrq(args):
    """the inputs of hrq / run: the accepted check_m2s72_a21.inputs(), the raw log for A-1 and the census, the .sca"""
    import check_m2s72_a2 as C
    import check_m2s72_a21 as CC
    runs, cfg = args["runs"], args["cfg"]
    W.guard(cfg, "run" if args["mode"] == "run" else "hrq")
    log = os.path.join(runs, f"run-{cfg}.log.gz")
    if not os.path.isfile(log):
        raise W.Refused(f"no gNB MAC log {log}: nothing to replay")
    lines21, grants, node_id, sca, root = CC.inputs(runs, cfg)
    if node_id is None:
        raise W.Refused("UE-to-node mapping unavailable (Run72: a missing or duplicate macNodeId); nothing is guessed")
    if W.run_name_ok(cfg):
        n_name = int(cfg.split("-n")[-1].split("-")[0])
        if n_name != len(node_id):
            raise W.EvaluationError(f"{cfg}: numUe {len(node_id)} in the run, {n_name} in the name")
    return {"mode": args["mode"], "cfg": cfg, "label": f"{args['mode']} on {cfg}", "log": log, "lines21": lines21, "grants": grants,
            "node_id": dict(node_id), "sca": sca if sca and os.path.isfile(sca) else None, "root": root,
            "nproc": C._nproc(cfg), "t0": args["t0_ps"], "watch": [log] + ([sca] if sca and os.path.isfile(sca) else [])}


def gather_fixture(args):
    import m2s72_a21_realchain as RC
    root = os.environ.get("SIMU5G_ROOT")
    if not root or not os.path.isdir(root):
        raise W.Refused("SIMU5G_ROOT is not set to a directory (A2-0s needs the Simu5G 1.8.1 sources)")
    try:
        fx = RC.load_fixture(args["fixture"])
    except RC.Refused as ex:
        raise W.Refused(f"fixture refused: {ex}")
    d = args["fixture"]
    return {"mode": "hrq-fixture", "cfg": FIXTURE_CFG, "label": FIXTURE_LABEL, "log": fx["path"], "lines21": fx["lines21"],
            "grants": fx["grants"], "node_id": dict(fx["node"]), "sca": None, "root": root, "nproc": fx["nproc"], "t0": 0,
            "fixture": {"sha256": fx["sha256"], "cfg": fx["cfg"]},
            "watch": [fx["path"], os.path.join(d, RC.FIX + ".sha256"), os.path.join(d, RC.META)]}


def evaluate(ctx):
    """ONE A-2.1 replay and every wrapper row from it (design 3.3); the committed registry only (IG-5); coverage and
    rows of the same replay (IG-6); A2-7 / its occupancy comparison exactly as A-2.1 produced them (IG-3); the .sca
    duplicate census before any A2-8u comparison (IG-2)"""
    import m2s72_a2 as A2
    import m2s72_a2probe as PR
    import m2s72_peru as P
    import m2s72_peru_adapter as PA
    view = W.registry_view(W.load_registry(W.REGISTRY_PATH))       # EvaluationError (exit 2) if invalid
    before = {p: sha256_file(p) for p in ctx["watch"]}
    node_id, n = ctx["node_id"], len(ctx["node_id"])
    a1_events = PA.harq_events(ctx["log"])
    census = W.token_census(raw_lines(ctx["log"]))
    res, rows, per, cov, extra, window = W.A21.evaluate(ctx["lines21"], ctx["nproc"], ctx["t0"], node_id, ctx["grants"],
                                                        ctx["sca"], ctx["root"])
    W.check_a21_rows(rows, extra)                                     # I-7: the complete accepted row set
    x7 = extra["xa"]                                                  # IG-3: passed through, never constructed
    v_f1di, v_full = W.A21.verdict(rows, "f1d-i")[0], W.A21.verdict(rows, "full")[0]
    if ctx["sca"]:
        sca_lines = raw_lines(ctx["sca"])
        dups = W.scalar_record_counts(sca_lines)                     # IG-2: the census, before any comparison
        sc, smap = PR.scalars(ctx["sca"]), A2.sca_nodes(ctx["sca"])
        census_sca = {"performed": True, "duplicates": sorted(f"{m} {s}" for (m, s), c in dups.items() if c > 1)}
    else:
        dups = sc = smap = None
        census_sca = {"performed": False, "reason": "no .sca"}
    m = W.map_ue(n, node_id, smap, W.evidence_nodes(res, per, x7))
    c0, c0info = W.c0_row(a1_events, res, census)
    ph, verd = W.pu4h_row(m, c0, rows, res)
    if verd != {"verdict_f1d_i": v_f1di, "verdict_full": v_full}:
        raise W.EvaluationError("contract verdicts differ between derivations of the same rows")
    po, po_loc = W.pu4o_rows(n, node_id, per, x7, rows, m["status"], ph["status"])
    a8, a8_loc = W.a28u_rows(n, node_id, sc, smap, res, dups, m["status"], ph["status"])
    wrapper = [m, c0, ph] + po + a8
    f = W.fgo(cov, rows, view)
    verdict = W.compose_verdict(n, wrapper, f)
    trace = []
    _, summ = P.attribute_feedback(a1_events, ctx["nproc"], window=window, trace=trace)
    pu4 = next(r for r in P.structural_rows([], [], summ, None) if r[0] == "PU-4")
    agree = W.agreement(a1_events, trace, res, c0["status"])
    after = {p: sha256_file(p) for p in ctx["watch"]}
    if after != before:
        raise W.EvaluationError(f"an input changed during the evaluation: {sorted(p for p in before if before[p] != after[p])}")
    return {"res": res, "rows": rows, "per": per, "cov": cov, "extra": extra, "window": window, "wrapper": wrapper,
            "fgo": f, "agreement": agree, "node_id": node_id, "census_sca": census_sca, "registry_sha256": view["sha256"],
            "c0info": c0info, "census": census,
            "out": {
                "schema": HRQ_SCHEMA, "mode": ctx["mode"], "config": ctx["cfg"], "label": ctx["label"],
                "numUe": n, "nproc": ctx["nproc"], "t0_ps": ctx["t0"], "window_ps": list(window),
                "nodes": {str(k): v for k, v in sorted(node_id.items())},
                "rows": wrapper, "local_steps": {"PU-4o": [x["step"] for x in po_loc], "A2-8u": [x["step"] for x in a8_loc]},
                "verdict": {k: verdict[k] for k in W.VERDICT_KEYS}, "held": verdict["held"],
                "fgo": {"registry": f["registry"], "registry_sha256": f["registry_sha256"], "exercised": f["exercised"]},
                "c0": {"census": census, "lengths": c0info["lengths"], "sha256_a1": c0info["sha256_a1"],
                       "sha256_a21": c0info["sha256_a21"], "problems": c0info["problems"]},
                "a21": {"rows": [list(r) for r in rows], "verdict_f1d_i": v_f1di, "verdict_full": v_full,
                        "coverage": [list(c) for c in cov], "run_level_a2_8": list(next(r for r in rows if r[0] == "A2-8")),
                        "a2_7": x7, "touched_nodes": sorted(W.A21.touched_nodes(res)), "end_states": res["end_states"],
                        "unresolved": res["unresolved"], "per_ue": {str(k): v for k, v in per.items()}},
                "historical": {"label": "A-1 rule, computed by the frozen m2s72_peru on the same log; reported, not a gate (DR-07b)",
                               "a1_pu4_row": list(pu4), "a1_summary": summ},
                "diagnostics": {"agreement": agree},
                "inputs": {"files": before, "sca": ctx["sca"], "sca_duplicate_census": census_sca,
                           "simu5g_root": ctx["root"], "registry_sha256": view["sha256"], "code_sha256": code_identity(),
                           **({"fixture": ctx["fixture"]} if "fixture" in ctx else {})}}}


# ------------------------------------------------------------------------------------------------- records ------
def a21_sections(res, rows, per, cov):
    """the ROWS, COVERAGE, PER UE and handles sections, in the layout of the accepted check_m2s72_a21.a21()"""
    out = ["ROWS\n"]
    for r in rows:
        out.append(f"  {r[2]:<15} | {r[0]} | {r[1]} | {r[3]}\n")
    out.append("\nCOVERAGE\n")
    for name, n, cls in cov:
        out.append(f"  {n:>7} | {name} | {cls}\n")
    out.append("\nPER UE\n")
    for n, o in per.items():
        out.append(f"  node {n}: inserts {o['inserts']}, transmissions {o['transmissions']}, feedback {o['feedback']} (ACK {o['ack']}, "
                   f"NACK {o['nack']}), discarded {o['discarded']}, lines {o['lines_by_class']}, end states {o['end_states']}\n")
    out.append(f"\nhandles: {Counter(h['st'] for h in res['handles'].values())}; unresolved {res['unresolved'][:5]}\n")
    return "".join(out)


def a21_record(cfg, ev):
    import check_m2s72_a2 as C
    A = W.A21
    out = ev["out"]
    w = ev["window"]
    txt = (f"M2-S7.2a DL H-ARQ attribution {A.VERSION} on {cfg}; contracts f1d-i (campaign) and full (reported), one replay; "
           f"window [{w[0]}, {w[1]}) ps\n{A.NOTE}\n\n" + a21_sections(ev["res"], ev["rows"], ev["per"], ev["cov"])
           + f"\n{A.VERSION} verdict (f1d-i): {out['a21']['verdict_f1d_i']}\n{A.VERSION} verdict (full): {out['a21']['verdict_full']}\n")
    res, extra = ev["res"], ev["extra"]
    js = C._clean({"config": cfg, "version": A.VERSION, "contracts": ["f1d-i", "full"],
                   "verdicts": {"f1d-i": out["a21"]["verdict_f1d_i"], "full": out["a21"]["verdict_full"]},
                   "rows": ev["rows"], "coverage": ev["cov"], "per_ue": ev["per"], "d_star_ps": res["d_star"],
                   "t_end_ps": res["t_end"], "window_ps": w, "end_states": res["end_states"], "handles": res["handles"],
                   "unresolved": res["unresolved"], "a2_7": extra["xa"], "a2_8": extra["scalars"],
                   "preconditions": extra["preconditions"], "note": A.NOTE})
    return txt, js


def hrq_text(out):
    L = [f"M2-S7.2a WP-A1 H-ARQ rows ({out['mode']}) on {out['config']}: {out['label']}\n",
         f"N = {out['numUe']}, nodes {out['nodes']}, processes {out['nproc']}, window {out['window_ps']} ps\n",
         f"A-2.1 (one replay): F1-d(i) {out['a21']['verdict_f1d_i']} (campaign contract); full {out['a21']['verdict_full']} (reported)\n",
         "\nWRAPPER ROWS (gates)\n"]
    for r in out["rows"]:
        loc = f" [local {r['local']}]" if "local" in r else ""
        L.append(f"  {r['status']:<15} | {r['id']} | {r['subject']}{loc} | {r['detail'][:500]}\n")
    L.append(f"\nrun-level A2-8 (A-2.1, verbatim; gates only through PU-4h): {out['a21']['run_level_a2_8'][2]} | {out['a21']['run_level_a2_8'][3][:300]}\n")
    L.append(f"C-0 census {out['c0']['census']}, lengths {out['c0']['lengths']}, sha256 A-1 {out['c0']['sha256_a1']}, A-2.1 {out['c0']['sha256_a21']}\n")
    L.append(f".sca duplicate census: {out['inputs']['sca_duplicate_census']}\n")
    L.append(f"\nFIRST GENUINE OCCURRENCE ({out['fgo']['registry']}, sha256 {out['fgo']['registry_sha256']})\n")
    for h in out["held"]:
        L.append(f"  HELD | {h['feature']} ({h['count']}) | {h['reason']}\n")
    if not out["held"]:
        L.append("  none\n")
    hp = out["historical"]["a1_pu4_row"]
    L.append(f"\n{out['historical']['label']}\n  {hp[2]:<15} | {hp[0]} | {hp[1]} | {hp[3]}\n")
    ag = out["diagnostics"]["agreement"]
    L.append(f"\nA-1 / A-2.1 agreement (report only, never a gate): "
             + (f"agree {ag['agree']}, disagree {ag['disagree']} {ag['disagree_by_a21_class']}, A-1 unattributed {ag['a1_unattributed_by_a21_class']}"
                if ag.get("computed") else f"not computed ({ag.get('reason')})") + "\n")
    v = out["verdict"]
    detail = " ".join(v["gate_failures"] + [f"NE:{x}" for x in v["gate_not_evaluated"]] + [f"HELD:{x}" for x in v["held_features"]])
    L.append(f"\nverdict: {v['status']}{(' ' + detail) if detail else ''} (exit {v['exit']})\n")
    return "".join(L)


def write_records(recdir, files):
    import m2s72s5_lib as LIB
    os.mkdir(recdir)
    paths = []
    for name, content in files:
        p = os.path.join(recdir, name)
        with open(p, "x", encoding="utf-8") as fh:
            fh.write(content)
        paths.append(p)
    LIB.durable(paths)
    return paths


def dumps(x):
    import check_m2s72_a2 as C
    return json.dumps(C._clean(x), indent=1, sort_keys=True, allow_nan=False) + "\n"


# ------------------------------------------------------------------------------------------------------ run ------
_RUN_STARTED = False          # one run per process: the accepted checkers accumulate rows in a module-global list


def tree_fingerprint(path):
    """(relative path, size, mtime_ns) of every file under a run directory: a change during the evaluation is
    detected without hashing gigabytes of vectors twice"""
    out = []
    for dp, dn, fn in os.walk(path):
        dn.sort()
        for f in sorted(fn):
            p = os.path.join(dp, f)
            st = os.stat(p)
            out.append((os.path.relpath(p, path), st.st_size, st.st_mtime_ns))
    return out


def import_s5n():
    argv = sys.argv
    sys.argv = [argv[0]]
    try:
        import check_m2s72_s5n as S5N         # accepted; unchanged
    finally:
        sys.argv = argv
    return S5N


def _run(args):
    global _RUN_STARTED
    d2 = os.environ.get("S5N_ADAPTER_VALIDATED")
    if not d2 or not d2.strip():
        raise W.Refused("S5N_ADAPTER_VALIDATED is not set: the per-UE adapter is not validated on real N > 1 output "
                        "(decision S5-2-D2); E0v-N evaluation stays refused")
    cfg, runs, recdir = args["cfg"], args["runs"], args["recdir"]
    W.guard(cfg, "run")
    if _RUN_STARTED:
        raise W.Refused("one run per process: the accepted checkers accumulate their rows in a module-global list (L-11)")
    staging = recdir.rstrip("/") + ".incomplete"
    fresh_dir(recdir)
    if os.path.lexists(staging):
        raise W.Refused(f"{staging} exists: an interrupted earlier evaluation; its records are not a result (remove it)")
    log, sca = os.path.join(runs, f"run-{cfg}.log.gz"), os.path.join(runs, cfg, cfg, "0.sca")
    for p in (log, sca):
        if not os.path.isfile(p):
            raise W.Refused(f"required input {p} missing")
    if not os.path.isdir(os.path.join(runs, cfg)):
        raise W.Refused(f"run directory {os.path.join(runs, cfg)} missing")
    _RUN_STARTED = True
    tree0 = tree_fingerprint(os.path.join(runs, cfg))
    hashes0 = {p: sha256_file(p) for p in (log, sca)}
    S5N = import_s5n()
    os.mkdir(staging)
    s5dir = os.path.join(staging, "s5n")
    start = len(S5N.rows)
    rc5, dig5 = S5N.run_one(runs, cfg, s5dir)                            # the accepted checker, unchanged
    if rc5 == 2 or dig5 is None:
        raise W.Refused(f"the accepted s5n checker refused {cfg} (rc {rc5})")
    s5n_rows = list(S5N.rows[start:])
    chk_txt = open(os.path.join(s5dir, f"{cfg}.check.txt"), encoding="utf-8").read()
    with open(os.path.join(s5dir, f"{cfg}.digest.json"), encoding="utf-8") as fh:
        dig5_file = json.load(fh)
    if dig5_file != json.loads(json.dumps(W_clean_s5v(S5N, dig5))):
        raise W.EvaluationError("the s5n digest written differs from the one returned")
    written, s5n_vline = W.parse_s5n_check(chk_txt)
    n = dig5_file["numUe"]
    W.check_s5n_rows(s5n_rows, n, written, dig5_file["correctness"]["rows"])
    pu4 = W.extract_pu4(s5n_rows)                                       # exactly one, well formed; verbatim
    ctx = gather_hrq(args)
    if len(ctx["node_id"]) != n:
        raise W.EvaluationError(f"numUe {n} (s5n) vs {len(ctx['node_id'])} node ids")
    ev = evaluate(ctx)                                                  # ONE A-2.1 replay
    out = ev["out"]
    info, ne = W.s5n_info()
    verdict = W.compose_verdict(n, ev["wrapper"], ev["fgo"], s5n_rows, info, ne)
    inputs = {"log_sha256": hashes0[log], "sca_sha256": hashes0[sca], "registry_sha256": ev["registry_sha256"],
              "code": code_identity(), "c0": {"census": ev["census"], "lengths": ev["c0info"]["lengths"],
                                              "sha256_a1": ev["c0info"]["sha256_a1"], "sha256_a21": ev["c0info"]["sha256_a21"]},
              "s5n_adapter_validated": d2}
    digest = W.composed_digest(dig5_file, s5n_vline, s5n_rows, ev["wrapper"], verdict, out["a21"], ev["per"],
                               set(W.A21.touched_nodes(ev["res"])), ev["node_id"], ev["agreement"], inputs)
    probs = W.validate_digest(json.loads(dumps(digest)))
    if probs:
        raise W.EvaluationError(f"the composed digest fails its own schema: {probs[:5]}")
    txt_view = dict(out, mode="run", verdict={k: verdict[k] for k in W.VERDICT_KEYS}, held=verdict["held"])
    out = dict(out, mode="run", verdict={k: verdict[k] for k in W.VERDICT_KEYS}, held=verdict["held"],
               historical={"label": W.HISTORICAL_A1_LABEL, "pu4": W.pu4_report_row(pu4),
                           "a1_summary_s5n": dig5_file["performance"]["harq_attribution"],
                           "a1_rule_on_the_same_log": {"pu4_row": out["historical"]["a1_pu4_row"],
                                                       "summary": out["historical"]["a1_summary"]}},
               s5n={"verdict_line": s5n_vline, "rc": rc5, "gate_failures": dig5_file["correctness"]["gate_failures"],
                    "per_ue_not_evaluated": dig5_file["correctness"]["per_ue_not_evaluated"], "rows": [list(r) for r in s5n_rows]})
    a21_txt, a21_js = a21_record(cfg, ev)
    txt = run_text(txt_view, pu4, s5n_vline)
    files = [(f"a21-{cfg}.txt", a21_txt), (f"a21-{cfg}.json", dumps(a21_js)), (f"{cfg}.s5n21.txt", txt),
             (f"{cfg}.s5n21.json", dumps(out)), (f"{cfg}.s5n21.digest.json", dumps(digest))]
    if tree_fingerprint(os.path.join(runs, cfg)) != tree0 or {p: sha256_file(p) for p in (log, sca)} != hashes0:
        raise W.EvaluationError("an input changed during the evaluation")
    publish(staging, recdir, files)
    print(txt.rstrip())
    return verdict["exit"]


def W_clean_s5v(S5N, x):
    return S5N.S5V.clean(x)


def publish(staging, recdir, files):
    """write the wrapper records into the staging directory, then SHA256SUMS of everything in it, fsync, and only
    then rename it to <records dir> (atomic on one file system): an interrupted evaluation leaves <records dir>.incomplete,
    never a <records dir> that could be read as a result"""
    import m2s72s5_lib as LIB
    paths = []
    for name, content in files:
        p = os.path.join(staging, name)
        with open(p, "x", encoding="utf-8") as fh:
            fh.write(content)
        paths.append(p)
    allf = sorted(os.path.relpath(os.path.join(dp, f), staging) for dp, _, fn in os.walk(staging) for f in fn)
    sums = "".join(f"{sha256_file(os.path.join(staging, f))}  {f}\n" for f in allf)
    with open(os.path.join(staging, "SHA256SUMS"), "x", encoding="utf-8") as fh:
        fh.write(sums)
    LIB.durable(paths + [os.path.join(staging, "SHA256SUMS")] + [os.path.join(staging, f) for f in allf])
    if os.path.lexists(recdir):
        raise W.Refused(f"records dir {recdir} appeared during the evaluation")
    os.rename(staging, recdir)
    LIB.durable([os.path.join(recdir, "SHA256SUMS")])


def run_text(out, pu4, s5n_vline):
    base = hrq_text(out)
    i = base.index("\nA-1 rule")
    j = base.index("\nA-1 / A-2.1 agreement")
    rep = W.pu4_report_row(pu4)
    hist = (f"\n{rep['label']}\n  {rep['status']:<15} | {rep['id']} | {rep['subject']} | {rep['detail']}\n"
            f"s5n per-run verdict (unchanged, historical scoping): {s5n_vline}\n"
            f"s5n gates carried (identical predicate, PU-4 removed): failures {out['verdict']['gate_failures']}, "
            f"not evaluated {out['verdict']['gate_not_evaluated']}\n")
    return base[:i] + hist + base[j:]

# ------------------------------------------------------------------------------------------------------ main -----
def _hrq(args):
    expect = load_expect(args["expect"], args["cfg"]) if args["expect"] else None
    fresh_dir(args["recdir"])
    ctx = gather_hrq(args) if args["mode"] == "hrq" else gather_fixture(args)
    ev = evaluate(ctx)
    out, cfg = ev["out"], ctx["cfg"]
    a21_txt, a21_js = a21_record(cfg, ev)
    files = [(f"a21-{cfg}.txt", a21_txt), (f"a21-{cfg}.json", dumps(a21_js)), (f"hrq-{cfg}.txt", hrq_text(out)),
             (f"hrq-{cfg}.json", dumps(out))]
    rc = out["verdict"]["exit"]
    if expect is not None:
        table = compare_expect(expect, json.loads(dumps(out)))
        bad = [t for t in table if t[3] != "MATCH"]
        txt = (f"declared expectations ({args['expect']}) against the evaluation of {cfg}\n\n"
               + "".join(f"  {s:<8} | {k} | declared {json.dumps(w, sort_keys=True)} | evaluated {json.dumps(g, sort_keys=True)}\n"
                         for k, w, g, s in table)
               + f"\n{len(table) - len(bad)} / {len(table)} MATCH; " + ("ALL EXPECTATIONS MET\n" if not bad else "EXPECTATION MISMATCH\n"))
        files.append((f"hrq-{cfg}.expect.txt", txt))
        rc = 0 if not bad else W.EXIT_EXPECT_MISMATCH
    write_records(args["recdir"], files)
    print(hrq_text(out).rstrip())
    if expect is not None:
        print(files[-1][1].rstrip().splitlines()[-1])
    return rc


def _dispatch(argv):
    try:
        args = parse_args(argv)
    except Usage as ex:
        print(f"usage error: {ex}\n\n{__doc__}")
        return W.EXIT[W.V_REFUSED]
    return _run(args) if args["mode"] == "run" else _hrq(args)


def main(argv):
    """the CLI boundary: a refusal, a malformed expectation file or any evaluation that cannot complete is exit 2"""
    try:
        return _dispatch(argv)
    except W.Refused as ex:
        print(f"REFUSED: {ex}")
        return W.EXIT[W.V_REFUSED]
    except ExpectationError as ex:
        print(f"EVALUATION ERROR (expectation file): {ex}")
        return W.EXIT[W.V_ERROR]
    except Exception as ex:                     # includes W.EvaluationError
        import traceback
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}")
        return W.EXIT[W.V_ERROR]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
