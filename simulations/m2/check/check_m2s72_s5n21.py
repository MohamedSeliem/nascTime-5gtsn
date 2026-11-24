#!/usr/bin/env python3
"""WP-A1 CLI: the E0v-N per-run evaluation with A-2.1 as the per-UE H-ARQ source (design revision 2.1, 57a80ca).

    python3 -I -B check_m2s72_s5n21.py hrq         <runs> <cfg> <records dir> [--t0 <s>] [--expect <file>]
    python3 -I -B check_m2s72_s5n21.py hrq-fixture <fixture dir> <records dir> [--expect <file>]
    python3 -I -B check_m2s72_s5n21.py run         <runs> <cfg> <records dir> [--t0 <s>]
    python3 -I -B check_m2s72_s5n21.py controls    <runs> <cfg> <records dir> [--t0 <s>]

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
controls     the negative controls of design 7.3 that need a run (synthetic or the public fixture's run layout; never a
             private run in this work package): each mutation is applied to a COPY of the run's evidence in a
             temporary directory (the inputs are only read), and the copy is evaluated exactly as hrq evaluates.
             A control counts only if its declared rows PASS on the unmutated copy (else NOT BUILDABLE, with the
             reason); a mutation that changes nothing is a FAIL. Per control: PASS (as declared), FAIL (not as
             declared) or NOT BUILDABLE, with the before / after evidence. Records controls-<cfg>.txt / .json.
             Exit 0 every buildable control as declared, 1 any FAIL, 4 no mutation control buildable, 2 refused / error.
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
# I7-R2: every source of the evaluation chain, by mode. A missing required source is EVALUATION ERROR (exit 2)
# before anything is evaluated; every local module actually loaded is hashed again at the end.
REQUIRED_A21 = ("check_m2s72_s5n21.py", "m2s72_e0vn21.py", "m2s72_a21.py", "check_m2s72_a21.py", "check_m2s72_a2.py",
                "m2s72_a2.py", "m2s72_a2probe.py", "m2s72_harqx.py", "m2s72_peru.py", "m2s72_peru_adapter.py",
                "m2s72_maclog.py", "check_m2s72_s5v.py")
REQUIRED_FIXTURE = REQUIRED_A21 + ("m2s72_a21_realchain.py",)
REQUIRED_S5N = REQUIRED_A21 + ("check_m2s72_s5n.py", "check_m2s72_e0.py", "check_m2s72_b.py", "check_m2s72_i2h.py",
                               "check_m2s72_f0.py", "check_m2s72_f0r2.py", "check_m2s6.py", "check_m2s5.py", "check_m2s4.py",
                               "m2s72_runs.py", "m2s6_runs.py", "m2s72_s6.py", "m2s6_clocks.py", "slave_m2s6.py",
                               "decomp_m2s6.py", "clock_model.py", "ttclock_model.py", "inet_model.py", "pcapng.py",
                               "m2s71_lib.py", "m2s72_compare.py", "m2s72s5_lib.py", "diag_m2s72_dl_active.py",
                               "gate_m2s4.py", "gate_m2s5.py", "gate_m2s71_p0.py", "gate_v0.py", "oracle_m2s3.py")


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
    if mode in ("hrq", "run", "controls"):
        if len(pos) != 3:
            raise Usage(f"{mode} <runs> <cfg> <records dir>")
        if mode in ("run", "controls") and opts["expect"] is not None:
            raise Usage(f"{mode} has no --expect (expectations are compared by hrq)")
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
            r"agreement\.(computed|agree|disagree|a1_attributed|a1_unattributed_by_a21_class)",
            r"a21\.(exchangeable_groups|handles_by_state)", r"a21\.lines_by_class\.[a-z-]+",
            r"a28u\.UE \d+\.(harqErrorRateDl|harqTxAttemptsDl):mean"]
TOLERANT = r"a28u\.UE \d+\.(harqErrorRateDl|harqTxAttemptsDl):mean"      # Simu5G statistics: REL_TOL as A2-8


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
        if key == "a21.exchangeable_groups":
            cov = {n: c for n, c, _ in out["a21"]["coverage"]}
            return cov["exchangeable ACK groups (2 candidates)"] + cov["exchangeable groups of 3 or more"]
        if key == "a21.handles_by_state":
            return out["a21"]["handles_by_state"]
        if key.startswith("a21.lines_by_class."):
            cls = key.split(".", 2)[2]
            return sum(o["lines_by_class"].get(cls, 0) for o in out["a21"]["per_ue"].values())
        if key.startswith("a28u."):
            _, ue, stat = key.split(".", 2)
            return out["a28u_stats"][ue][stat]["rec"]
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
    import re
    for k in sorted(exp):
        want = exp[k]
        got = evaluated_value(k, out)
        if isinstance(want, dict) and set(want) == {"any_of"} and isinstance(want["any_of"], list):
            table.append((k, want, got, "MATCH" if got in want["any_of"] else "MISMATCH"))
            continue
        if re.fullmatch(TOLERANT, k) and isinstance(want, (int, float)) and isinstance(got, (int, float)) \
                and not isinstance(want, bool) and not isinstance(got, bool):
            ok = abs(got - want) <= W.A21.REL_TOL * max(1.0, abs(want))
            table.append((k, want, got, "MATCH" if ok else "MISMATCH"))
            continue
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


def code_provenance_start(required):
    """the required sources must all exist; their sha256 before the evaluation"""
    miss = [f for f in required if not os.path.isfile(os.path.join(HERE, f))]
    if miss:
        raise W.EvaluationError(f"required source files missing: {miss} (code provenance, I7-R2)")
    return {f: sha256_file(os.path.join(HERE, f)) for f in required}


def loaded_local_modules():
    out = {}
    for m in list(sys.modules.values()):
        f = getattr(m, "__file__", None)
        if f and os.path.abspath(f).startswith(HERE + os.sep) and f.endswith(".py"):
            out[os.path.basename(f)] = os.path.abspath(f)
    return out


def code_provenance_end(start):
    """every local module loaded by the evaluation hashed now; a required source changed or vanished, or a loaded
    module whose file is gone, is EVALUATION ERROR"""
    loaded = loaded_local_modules()
    probs = [f for f in start if not os.path.isfile(os.path.join(HERE, f)) or sha256_file(os.path.join(HERE, f)) != start[f]]
    gone = [f for f, p in loaded.items() if not os.path.isfile(p)]
    if probs or gone:
        raise W.EvaluationError(f"source files changed or vanished during the evaluation: {sorted(probs + gone)}")
    return {"required": dict(sorted(start.items())),
            "loaded": {f: sha256_file(p) for f, p in sorted(loaded.items()) if not f.startswith("test_")}}


# --- I7-R3: the inputs the evaluators actually read --------------------------------------------------------------
class InputTracker:
    """records, through a Python audit hook ("open" events), every regular file opened for READING under the given
    roots while active, hashes it (sha256) at its first opening, and re-hashes it at the end: a byte-level check of
    the inputs the accepted evaluators consumed. The hook is installed once per process; it is inert unless a tracker
    is active."""
    _installed = False
    active = None

    def __init__(self, roots):
        self.roots = {k: os.path.realpath(v) for k, v in roots.items() if v and os.path.isdir(v)}
        self.first = {}
        self.busy = False

    @classmethod
    def _hook(cls, event, args):
        t = cls.active
        if t is None or t.busy or event != "open" or not args:
            return
        path = args[0]
        if isinstance(path, int) or path is None:
            return
        try:
            mode = args[1] if len(args) > 1 else None
            flags = args[2] if len(args) > 2 else 0
            if isinstance(mode, str) and any(c in mode for c in "wax+"):
                return
            if isinstance(flags, int) and flags & (os.O_WRONLY | os.O_RDWR):
                return
            rp = os.path.realpath(os.fsdecode(path))
            if rp in t.first or not os.path.isfile(rp) or not any(rp.startswith(r + os.sep) for r in t.roots.values()):
                return
            t.busy = True
            try:
                t.first[rp] = sha256_file(rp)
            finally:
                t.busy = False
        except Exception:                        # never break the evaluator; verify() re-hashes what was recorded
            t.busy = False

    def __enter__(self):
        if not InputTracker._installed:
            sys.addaudithook(InputTracker._hook)
            InputTracker._installed = True
        if InputTracker.active is not None:
            raise W.EvaluationError("an input tracker is already active")
        InputTracker.active = self
        return self

    def __exit__(self, *exc):
        InputTracker.active = None
        return False

    def label(self, rp):
        for k, r in self.roots.items():
            if rp.startswith(r + os.sep):
                return f"{k}:{os.path.relpath(rp, r)}"
        return rp

    def verify(self):
        """{label: sha256} of every consumed input; EVALUATION ERROR if any changed (bytes) or vanished since its
        first reading"""
        changed = [self.label(p) for p, h in self.first.items() if not os.path.isfile(p) or sha256_file(p) != h]
        if changed:
            raise W.EvaluationError(f"an input changed during the evaluation (sha256 of consumed files): {sorted(changed)[:5]}")
        return {self.label(p): h for p, h in sorted(self.first.items(), key=lambda kv: self.label(kv[0]))}


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
    if ctx.get("hook_a1") is not None:                                # controls only: a mutated A-1 event list
        a1_events = ctx["hook_a1"](list(a1_events))
    census = W.token_census(raw_lines(ctx["log"]))
    res, rows, per, cov, extra, window = W.A21.evaluate(ctx["lines21"], ctx["nproc"], ctx["t0"], node_id, ctx["grants"],
                                                        ctx["sca"], ctx["root"])
    W.check_a21_rows(rows, extra)                                     # I-7: the complete accepted row set
    if ctx.get("hook_replay") is not None:                            # controls only: corrupted replay output
        per, extra = ctx["hook_replay"](per, extra)
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
                        "unresolved": res["unresolved"], "per_ue": {str(k): v for k, v in per.items()},
                        "handles_by_state": dict(sorted(Counter(h["st"] for h in res["handles"].values()).items()))},
                "a28u_stats": {f"UE {k}": {name: {f: _finite_or_text(st[f]) for f in ("outcome", "step", "rec", "val")}
                                           for name, st in x["stats"].items()} for k, x in enumerate(a8_loc)},
                "historical": {"label": "A-1 rule, computed by the frozen m2s72_peru on the same log; reported, not a gate (DR-07b)",
                               "a1_pu4_row": list(pu4), "a1_summary": summ},
                "diagnostics": {"agreement": agree},
                "inputs": {"files": before, "sca": ctx["sca"], "sca_duplicate_census": census_sca,
                           "simu5g_root": ctx["root"], "registry_sha256": view["sha256"], "code_sha256": None,
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



def _finite_or_text(v):
    """a JSON value: a non-finite float (a Simu5G 'nan') is recorded as its text, never dropped or replaced"""
    import math
    return repr(v) if isinstance(v, float) and not math.isfinite(v) else v


# ------------------------------------------------------------------------------------------------- controls -----
class NotBuildable(Exception):
    pass


def _lt(line):
    """the time of a raw log line in ps, or None for a line without a time stamp"""
    p = line.split("|", 2)
    if len(p) < 3 or not p[0][:1].isdigit():
        return None
    try:
        return W.A21.PR.t_ps(p[0])
    except Exception:
        return None


def _mod(line):
    p = line.split("|", 2)
    return p[1] if len(p) >= 3 else None


def _median(xs, what):
    if not xs:
        raise NotBuildable(f"no {what} in this run")
    return xs[len(xs) // 2]


def _variant(ctx, raw, sca_lines, node_id, hook_a1=None, hook_replay=None):
    """evaluate a COPY of the run's evidence (in a fresh temporary directory) exactly as hrq evaluates; the inputs
    are never written. Returns a summary {key: status}, the details, the local outcomes and the verdicts."""
    import shutil
    import tempfile
    import m2s72_maclog as ML
    d = tempfile.mkdtemp(prefix="s5n21-control-")
    try:
        log = os.path.join(d, "run.log.gz")
        with gzip.open(log, "wt", encoding="utf-8") as fh:
            fh.writelines(raw)
        sca = None
        if sca_lines is not None:
            sca = os.path.join(d, "0.sca")
            with open(sca, "w", encoding="utf-8") as fh:
                fh.writelines(sca_lines)
        c = dict(ctx, log=log, sca=sca, lines21=W.A21.load(log), grants=ML.MacLog(log).grants, node_id=dict(node_id),
                 watch=[log] + ([sca] if sca else []), hook_a1=hook_a1, hook_replay=hook_replay)
        ev = evaluate(c)
    finally:
        shutil.rmtree(d, ignore_errors=True)
    out = ev["out"]
    st, det, loc = {}, {}, {}
    for r in out["rows"]:
        k = r["id"] if r["subject"] == "run" else f"{r['id']} {r['subject']}"
        st[k], det[k] = r["status"], r["detail"]
        if "local" in r:
            loc[k] = r["local"]
    for r in out["a21"]["rows"]:
        st[f"a21:{r[0]}"], det[f"a21:{r[0]}"] = r[2], r[3]
    return {"st": st, "det": det, "loc": loc, "f1d_i": out["a21"]["verdict_f1d_i"], "full": out["a21"]["verdict_full"],
            "verdict": out["verdict"]["status"], "res": ev["res"], "a28u_steps": out["local_steps"]["A2-8u"],
            "retransmissions": next(c for nm, c, _ in out["a21"]["coverage"] if nm == "retransmissions"),
            "sched_lines": bool(ev["res"].get("sched_lines"))}


def control_specs(n, node_id, raw, sca_lines, base):
    """the negative controls of design 7.3 that need a run: (id, mechanism, baseline rows, build, check, declared).
    build() returns (raw, sca_lines, node_id, hook_a1, hook_replay, mutation text) or raises NotBuildable;
    check(after) returns (ok, observed)."""
    G = W.GNB_MODULE
    n0, n1 = node_id[0], node_id.get(1)
    gnb = [i for i, x in enumerate(raw) if _mod(x) == G]
    ins = [i for i in gnb if W.TOKEN_INS in raw[i]]
    fbl = [i for i in gnb if W.TOKEN_FB in raw[i]]
    ins0 = [i for i in ins if f"for node with id {n0}" in raw[i]]
    pu4o = [f"PU-4o UE {k}" for k in range(n)]
    a28u = [f"A2-8u UE {k}" for k in range(n)]

    def need2():
        if n1 is None:
            raise NotBuildable("needs N >= 2 (a second UE)")

    def edit(i, new_line):
        out = list(raw)
        out[i] = new_line
        return out

    def st(a, keys):
        return ", ".join(f"{k} {a['st'].get(k)}" + (f" [local {a['loc'][k]}]" if k in a["loc"] else "") for k in keys)

    specs = []

    def spec(cid, mech, baseline, build, check, declared):
        specs.append({"id": cid, "mechanism": mech, "baseline": baseline, "build": build, "check": check, "declared": declared})

    # --- the attribution and its independent reference
    def b_swap():
        need2()
        i = _median(ins0, f"insert line of node {n0}")
        return edit(i, raw[i].replace(f"for node with id {n0}", f"for node with id {n1}")), sca_lines, node_id, None, None, \
            f"line {i}: the gNB insert of node {n0} relabelled to node {n1}"
    spec("NC-swap", "cross-UE misattribution invisible to sums: A2-7 (UE-side reference) must disagree",
         ["PU-4h", "a21:A2-7"] + pu4o, b_swap,
         lambda a: (a["st"]["PU-4h"] == "FAIL" and a["st"]["a21:A2-7"] == "FAIL" and all(a["st"][k] == "FAIL" for k in pu4o),
                    st(a, ["a21:A2-7", "PU-4h"] + pu4o)), "A2-7 FAIL, PU-4h FAIL, PU-4o FAIL for every UE")

    def b_ue_relabel():
        need2()
        m0 = f"{W.PR.NET}.ue[0].cellularNic"
        rx = [i for i, x in enumerate(raw) if (_mod(x) or "").startswith(m0) and "H-ARQ RX" in x]
        i = _median(rx, "UE 0 H-ARQ RX line")
        return edit(i, raw[i].replace(f"{W.PR.NET}.ue[0].", f"{W.PR.NET}.ue[1].", 1)), sca_lines, node_id, None, None, \
            f"line {i}: a UE 0 H-ARQ RX line moved to UE 1's module"
    spec("NC-ue-relabel", "a corrupted independent reference must never confirm: A2-7 FAIL", ["PU-4h", "a21:A2-7"] + pu4o, b_ue_relabel,
         lambda a: (a["st"]["a21:A2-7"] == "FAIL" and a["st"]["PU-4h"] == "FAIL" and all(a["st"][k] == "FAIL" for k in pu4o),
                    st(a, ["a21:A2-7", "PU-4h"] + pu4o)), "A2-7 FAIL, PU-4h FAIL, PU-4o FAIL (global)")

    def b_occ_one():
        need2()
        i = _median(ins0, f"insert line of node {n0}")
        return raw[:i] + raw[i + 1:], sca_lines, node_id, None, None, f"line {i}: one insert of node {n0} removed, its feedback kept"
    spec("NC-occ-one-ue", "a damaged UE 0 lifecycle FAILs UE 0 and, by the global rule, UE 1 (local outcome reported)",
         ["PU-4h"] + pu4o, b_occ_one,
         lambda a: (a["f1d_i"] == "A-2.1 NOT VALID" and a["st"]["PU-4h"] == "FAIL" and a["st"]["PU-4o UE 0"] == "FAIL"
                    and a["st"]["PU-4o UE 1"] == "FAIL" and "global" in a["det"]["PU-4o UE 1"],
                    f"F1-d(i) {a['f1d_i']}; " + st(a, ["PU-4h"] + pu4o)),
         "F1-d(i) NOT VALID, PU-4h FAIL, PU-4o UE 0 FAIL, PU-4o UE 1 FAIL by the global rule")

    def b_dropfb():
        i = _median(fbl, "gNB feedback line")
        return raw[:i] + raw[i + 1:], sca_lines, node_id, None, None, f"line {i}: one gNB feedback line removed"
    spec("NC-dropfb", "lost feedback evidence: the lifecycle accounting must break",
         ["PU-4h", "a21:A2-1", "a21:A2-2", "a21:A2-6"], b_dropfb,
         lambda a: (a["st"]["PU-4h"] == "FAIL" and any(a["st"][f"a21:{r}"] == "FAIL" for r in ("A2-1", "A2-2", "A2-6")),
                    st(a, ["PU-4h", "a21:A2-1", "a21:A2-2", "a21:A2-6"])), "A2-1, A2-2 or A2-6 FAIL; PU-4h FAIL")

    def b_dupins():
        i = _median(ins, "gNB insert line")
        return raw[:i + 1] + [raw[i]] + raw[i + 1:], sca_lines, node_id, None, None, f"line {i}: one gNB insert line duplicated"
    spec("NC-dupins", "duplicated evidence: A-2.1 loses one unit (repeated PDU id), C-0 R-0a must see it",
         ["C-0", "PU-4h", "a21:A2-2"], b_dupins,
         lambda a: (a["st"]["C-0"] == "FAIL" and "R-0a" in a["det"]["C-0"] and a["st"]["a21:A2-2"] == "FAIL" and a["st"]["PU-4h"] == "FAIL",
                    st(a, ["C-0", "a21:A2-2", "PU-4h"])), "C-0 FAIL (R-0a), A2-2 FAIL, PU-4h FAIL")

    def b_shift():
        import check_m2s72_a2 as C
        res = base["res"]
        cand = [x for x in res["fb"] if x["cls"] == "single" and x["res"] == "ACK"]
        x = _median(cand, "single-candidate ACK feedback line")
        t = x["t"]
        idx = [i for i in fbl if _lt(raw[i]) == t and f"process {x['p']} codeword" in raw[i] and "result is ACK" in raw[i]]
        if len(idx) != 1:
            raise NotBuildable(f"the feedback line at {t} ps process {x['p']} is not unique in the raw log")
        j = idx[0]
        k = max((i for i in gnb if i <= j and _lt(raw[i]) == t and "receiveHarqFeedback - start" in raw[i]), default=None)
        if k is None:
            raise NotBuildable("no feedback event block start before the line")
        block = [i for i in gnb if k <= i <= j]
        moved = [C._retime(raw[i], t + W.A21.MS) for i in block]
        rest = [y for i, y in enumerate(raw) if i not in set(block)]
        at = next((i for i, y in enumerate(rest) if _lt(y) is not None and _lt(y) >= t + W.A21.MS), len(rest))
        return rest[:at] + moved + rest[at:], sca_lines, node_id, None, None, \
            f"lines {k}..{j}: one single ACK's feedback event ({len(block)} gNB lines) moved one TTI later"
    spec("NC-shift", "timing corruption: the single feedback delay d* must break (A2-3)", ["PU-4h", "a21:A2-3"], b_shift,
         lambda a: (a["st"]["a21:A2-3"] == "FAIL" and a["st"]["PU-4h"] == "FAIL", st(a, ["a21:A2-3", "PU-4h"])), "A2-3 FAIL, PU-4h FAIL")

    def b_node_map():
        need2()
        perm = {k: node_id[(k + 1) % n] for k in range(n)}
        return raw, sca_lines, perm, None, None, f"node-id map permuted to {perm}"
    spec("NC-node-map", "wrong UE identity: MAP-UE (with the .sca) or the node-identified rows must FAIL", ["MAP-UE", "PU-4h"], b_node_map,
         lambda a: (a["st"]["PU-4h"] == "FAIL" and (a["st"]["MAP-UE"] == "FAIL" or a["st"]["a21:A2-4b"] == "FAIL"
                                                     or a["st"]["a21:A2-7"] == "FAIL"), st(a, ["MAP-UE", "a21:A2-4b", "a21:A2-7", "PU-4h"])),
         "PU-4h FAIL through MAP-UE FAIL or A2-4b / A2-7 FAIL")

    def b_no_ue():
        rx = [i for i, x in enumerate(raw) if W.PR.R_UE_MOD.match(_mod(x) or "") and "H-ARQ RX" in x]
        if not rx:
            raise NotBuildable("no UE-side H-ARQ RX line in this run")
        drop = set(rx)
        return [y for i, y in enumerate(raw) if i not in drop], sca_lines, node_id, None, None, f"{len(rx)} UE-side H-ARQ RX lines removed"
    spec("NC-no-ue-lines", "absence of the independent reference is NOT EVALUATED, never PASS", ["PU-4h", "a21:A2-7"] + pu4o, b_no_ue,
         lambda a: (a["st"]["a21:A2-7"] == "NOT EVALUATED" and a["st"]["PU-4h"] == "NOT EVALUATED"
                    and all(a["st"][k] == "NOT EVALUATED" for k in pu4o), st(a, ["a21:A2-7", "PU-4h"] + pu4o)),
         "A2-7 NE, PU-4h NE, PU-4o NE for every UE")

    # --- C-0: the two parsers and the raw census
    def b_dup_pid():
        import re
        if len(ins) < 6:
            raise NotBuildable("fewer than 6 insert lines")
        first = re.search(r"\(id (\d+) \)", raw[ins[0]]).group(1)
        i = ins[len(ins) // 2]
        return edit(i, re.sub(r"\(id \d+ \)", f"(id {first} )", raw[i])), sca_lines, node_id, None, None, \
            f"line {i}: the insert reuses the PDU id {first} of line {ins[0]}"
    spec("NC-c0-dup-pid", "an insert lost by reconstruction (pdus keyed by PDU id) must be seen (R-0a)", ["C-0", "PU-4h"], b_dup_pid,
         lambda a: (a["st"]["C-0"] == "FAIL" and "R-0a" in a["det"]["C-0"] and a["st"]["PU-4h"] == "FAIL", st(a, ["C-0", "PU-4h"])),
         "C-0 FAIL naming R-0a; PU-4h FAIL")

    def b_mal(sel_idx, pat, rep_, what):
        import re

        def b():
            pool = [i for i in sel_idx if re.search(pat, raw[i])]
            i = _median(pool, what)
            new = re.sub(pat, rep_, raw[i], count=1)
            return edit(i, new), sca_lines, node_id, None, None, f"line {i}: {what} corrupted"
        return b
    for cid, idx, pat, rp, what in (("NC-c0-malformed-ins", ins, r"\(id (\d)(\d*) \)", r"(id \1x\2 )", "an insert line's PDU id"),
                                    ("NC-c0-malformed-fb", fbl, r"result is ACK", "result is ACX", "a feedback line's result"),
                                    ("NC-c0-malformed-timestamp", ins, r"^(\d)", r"x\1", "an insert line's time stamp")):
        spec(cid, "a malformed line both regexes skip must be seen by the raw token census (R-0e)", ["C-0", "PU-4h"],
             b_mal(idx, pat, rp, what),
             lambda a: (a["st"]["C-0"] == "FAIL" and "R-0e" in a["det"]["C-0"] and a["st"]["PU-4h"] == "FAIL", st(a, ["C-0", "PU-4h"])),
             "C-0 FAIL naming R-0e; PU-4h FAIL")

    def a1_hook(kind):
        state = {}

        def hook(ev):
            if kind == "same-count":
                fb = [i for i, e in enumerate(ev) if e[0] == "fb"]
                pair = next(((i, j) for i in fb for j in fb if ev[i][2] != ev[j][2]), None)
                if pair is None:
                    return ev
                i, j = pair
                ev[i], ev[j] = ev[i][:2] + (ev[j][2],) + ev[i][3:], ev[j][:2] + (ev[i][2],) + ev[j][3:]
            elif kind == "reorder":
                # two adjacent inserts of different UEs where they exist (N >= 2), else any two adjacent distinct events
                k = next((k for k in range(len(ev) - 1) if ev[k][0] == ev[k + 1][0] == "ins" and ev[k][2] != ev[k + 1][2]),
                         next((k for k in range(len(ev) - 1) if ev[k] != ev[k + 1]), None))
                if k is None:
                    return ev
                ev[k], ev[k + 1] = ev[k + 1], ev[k]
            else:
                k = next((k for k, e in enumerate(ev) if e[0] == "ins"), None)
                if k is None:
                    return ev
                ev[k] = ev[k][:2] + (ev[k][2] + 1,) + ev[k][3:]
            state["applied"] = True
            return ev

        def b():
            return raw, sca_lines, node_id, hook, None, f"A-1 events: {kind} (in memory; counts unchanged)"
        return b, state
    for kind in ("same-count", "reorder", "node"):
        b, stt = a1_hook(kind)
        spec(f"NC-c0-{kind}", "C-0 compares the canonical event sequences, not counts", ["C-0", "PU-4h"], b,
             (lambda stt_: lambda a: (stt_.get("applied", False) and a["st"]["C-0"] == "FAIL" and "parser divergence" in a["det"]["C-0"]
                                      and a["st"]["PU-4h"] == "FAIL", f"applied {stt_.get('applied', False)}; " + st(a, ["C-0", "PU-4h"])))(stt),
             "C-0 FAIL (parser divergence); PU-4h FAIL")

    # --- PU-4o on corrupted replay output (fail-closed)
    def occ_hook(kind):
        import copy

        def hook(per, extra):
            per, extra = copy.deepcopy(per), dict(extra)
            if kind == "entry-missing":
                x7 = copy.deepcopy(extra["xa"])
                x7["occupancy_equal"].pop(n1, None)
                extra["xa"] = x7
            else:
                per[n1]["occupancy"] = {"error": "negative occupancy: a feedback before its insert"}
            return per, extra

        def b():
            need2()
            return raw, sca_lines, node_id, None, hook, f"in memory: {'no occupancy comparison entry for UE 1' if kind == 'entry-missing' else 'an invalid A-2.1 occupancy for UE 1'}"
        return b
    for kind in ("entry-missing", "invalid"):
        spec(f"NC-occ-{kind}", "a missing or invalid occupancy comparison never reaches PASS", ["PU-4o UE 1"] if n1 is not None else pu4o,
             occ_hook(kind),
             lambda a: (a["st"].get("PU-4o UE 1") == "FAIL" and a["loc"].get("PU-4o UE 1") == "DIFFERENT", st(a, pu4o)),
             "PU-4o UE 1 FAIL, local DIFFERENT")

    # --- A2-8u against Simu5G's statistics (.sca copy)
    ue1 = f"{W.PR.NET}.ue[1].cellularNic.nrMac"

    def sca_needed():
        need2()
        if sca_lines is None:
            raise NotBuildable("no .sca in this run")

    def b_scalar():
        sca_needed()
        out, hit = [], False
        for x in sca_lines:
            p = x.split()
            if not hit and len(p) >= 4 and p[0] == "scalar" and p[1] == ue1 and p[2] == "harqErrorRateDl:mean":
                try:
                    x = f"scalar {p[1]} {p[2]} {float(p[3]) + 1e-3!r}\n"
                    hit = True
                except ValueError:
                    pass
            out.append(x)
        if not hit:
            raise NotBuildable("no parsable harqErrorRateDl:mean of UE 1")
        return raw, out, node_id, None, None, "UE 1 harqErrorRateDl:mean + 1e-3 (beyond the relative tolerance 1e-9)"
    spec("NC-scalar-ue1", "per-UE isolation of the Simu5G cross-check and its global effect", a28u + ["a21:A2-8", "PU-4h"], b_scalar,
         lambda a: (a["st"]["A2-8u UE 1"] == "FAIL" and a["loc"]["A2-8u UE 1"] == "DIFFERENT" and a["st"]["a21:A2-8"] == "FAIL"
                    and a["st"]["PU-4h"] == "FAIL", st(a, ["a21:A2-8", "PU-4h"] + a28u)),
         "A2-8u UE 1 FAIL (local DIFFERENT), run-level A2-8 FAIL, PU-4h FAIL")

    def b_scalar_missing():
        sca_needed()
        out = [x for x in sca_lines if not (x.startswith("scalar ") and x.split()[1:2] == [ue1])]
        if len(out) == len(sca_lines):
            raise NotBuildable("no scalar of UE 1")
        return raw, out, node_id, None, None, "UE 1's scalar records removed (its macNodeId kept)"
    spec("NC-scalar-missing-ue1", "the frozen run-level A2-8 PASSes on UE 0 alone; the per-UE gate must not",
         a28u + ["a21:A2-8"], b_scalar_missing,
         lambda a: (a["st"]["a21:A2-8"] == "PASS" and a["st"]["A2-8u UE 1"] == "NOT EVALUATED" and a["loc"]["A2-8u UE 1"] == "NOT COMPARED",
                    st(a, ["a21:A2-8"] + a28u)), "run-level A2-8 PASS (frozen), A2-8u UE 1 NE (local NOT COMPARED)")

    def b_scalar_dup():
        sca_needed()
        dup = [x for x in sca_lines if x.startswith(f"scalar {ue1} harqErrorRateDl:mean ")]
        if not dup:
            raise NotBuildable("no harqErrorRateDl:mean of UE 1")
        return raw, list(sca_lines) + dup[:1], node_id, None, None, "UE 1 harqErrorRateDl:mean record duplicated"
    spec("NC-scalar-duplicate", "IG-2: a duplicated scalar record is ambiguous (V-1), never compared", a28u, b_scalar_dup,
         lambda a: (a["st"]["A2-8u UE 1"] == "NOT EVALUATED" and "ambiguous: 2 records" in a["det"]["A2-8u UE 1"], st(a, a28u)),
         "A2-8u UE 1 NE (V-1, ambiguous: 2 records)")
    return specs


def _controls(args):
    """design 5.1 / 7.3: the negative controls on a COPY of one run's evidence"""
    fresh_dir(args["recdir"])
    code0 = code_provenance_start(REQUIRED_A21)
    with InputTracker({"runs": args["runs"], "simu5g": os.environ.get("SIMU5G_ROOT")}) as tracker:
        ctx = gather_hrq(dict(args, mode="hrq"))
        ctx["mode"] = "controls"
        raw = raw_lines(ctx["log"])
        sca_lines = raw_lines(ctx["sca"]) if ctx["sca"] else None
        node_id = ctx["node_id"]
        direct = evaluate(ctx)                                            # the run itself, as hrq
    consumed = tracker.verify()
    base = _variant(ctx, raw, sca_lines, node_id)                       # the unmodified COPY
    direct_st = {(r["id"] if r["subject"] == "run" else f"{r['id']} {r['subject']}"): r["status"] for r in direct["out"]["rows"]}
    results = []
    pc_ok = all(base["st"][k] == v for k, v in direct_st.items())
    results.append({"id": "PC-unmodified", "mechanism": "the evaluated copy reproduces the run's own evaluation", "mutation": "none",
                    "baseline": direct_st, "after": {k: base["st"][k] for k in direct_st}, "declared": "every wrapper row status reproduced",
                    "result": "PASS" if pc_ok else "FAIL", "observed": "reproduced" if pc_ok else "differs"})
    # PC-full-masquerade: the contract labels (design 7.3 NC-full-masquerade): observation, no mutation
    if base["retransmissions"] > 0 and not base["sched_lines"]:
        ok = base["full"] == "A-2.1 INCOMPLETE" and base["f1d_i"] == W.A21.verdict(
            [tuple(r) for r in direct["out"]["a21"]["rows"]], "f1d-i")[0] and "full contract (reported" in base["det"]["PU-4h"]
        results.append({"id": "NC-full-masquerade", "mechanism": "PU-4h uses F1-d(i) only; full is reported and labelled",
                        "mutation": "none (observation on a run with retransmissions and no scheduler lines)",
                        "baseline": {}, "after": {"full": base["full"], "f1d-i": base["f1d_i"], "PU-4h": base["st"]["PU-4h"]},
                        "declared": "full INCOMPLETE; PU-4h derived from F1-d(i); the record labels the contract",
                        "result": "PASS" if ok else "FAIL", "observed": f"full {base['full']}, F1-d(i) {base['f1d_i']}"})
    else:
        results.append({"id": "NC-full-masquerade", "mechanism": "PU-4h uses F1-d(i) only", "mutation": "none", "baseline": {},
                        "after": {}, "declared": "full INCOMPLETE with retransmissions", "result": "NOT BUILDABLE",
                        "observed": "no retransmission in this run" if base["retransmissions"] == 0 else "scheduler lines present"})
    for sp in control_specs(len(node_id), node_id, raw, sca_lines, base):
        rec = {"id": sp["id"], "mechanism": sp["mechanism"], "declared": sp["declared"],
               "baseline": {k: base["st"].get(k) for k in sp["baseline"]}}
        notpass = {k: v for k, v in rec["baseline"].items() if v != "PASS"}
        if notpass:
            rec.update(result="NOT BUILDABLE", mutation="not applied",
                       observed=f"declared row(s) not PASS before the mutation {notpass} (would not isolate the defect)")
            results.append(rec)
            continue
        try:
            r2, s2, n2, h1, h2, text = sp["build"]()
        except NotBuildable as ex:
            rec.update(result="NOT BUILDABLE", mutation="not applied", observed=str(ex))
            results.append(rec)
            continue
        rec["mutation"] = text
        if r2 == raw and s2 == sca_lines and n2 == node_id and h1 is None and h2 is None:
            rec.update(result="FAIL", observed="MUTATION NOT APPLIED (the copy is identical to the run)")
            results.append(rec)
            continue
        a = _variant(ctx, r2, s2, n2, hook_a1=h1, hook_replay=h2)
        ok, observed = sp["check"](a)
        rec.update(result="PASS" if ok else "FAIL", observed=observed,
                   after={k: a["st"].get(k) for k in sorted(set(sp["baseline"]) | {"PU-4h", "C-0", "MAP-UE"})},
                   details={k: a["det"][k][:300] for k in ("C-0", "PU-4h") if k in a["det"]})
        results.append(rec)
    code = code_provenance_end(code0)
    n_fail = sum(1 for r in results if r["result"] == "FAIL")
    n_pass = sum(1 for r in results if r["result"] == "PASS")
    n_nb = sum(1 for r in results if r["result"] == "NOT BUILDABLE")
    # exit 4 when no MUTATION control could be built: the positive control and the observation alone prove nothing
    n_mut_pass = sum(1 for r in results if r["result"] == "PASS" and r["id"].startswith("NC-") and r["id"] != "NC-full-masquerade")
    rc = 1 if n_fail else (4 if n_mut_pass == 0 else 0)
    cfg = ctx["cfg"]
    out = {"schema": "m2s72-s5n21-controls/1", "config": cfg, "numUe": len(node_id), "nodes": {str(k): v for k, v in node_id.items()},
           "controls": results, "summary": {"PASS": n_pass, "FAIL": n_fail, "NOT BUILDABLE": n_nb, "exit": rc},
           "inputs": {"consumed_sha256": consumed, "code_sha256": code, "registry_sha256": direct["registry_sha256"],
                      "note": "every mutation is applied to a copy in a temporary directory; the inputs are only read"}}
    lines = [f"M2-S7.2a WP-A1 negative controls on {cfg} (N = {len(node_id)}): each on a COPY of the run's evidence; a control "
             f"counts only if its declared rows PASS before the mutation\n\n"]
    for r in results:
        lines.append(f"  {r['result']:<13} | {r['id']} | {r['mechanism']}\n      mutation: {r.get('mutation')}\n"
                     f"      baseline: {r.get('baseline')}\n      declared: {r['declared']}\n      observed: {r.get('observed')}\n")
    lines.append(f"\n{n_pass} PASS, {n_fail} FAIL, {n_nb} NOT BUILDABLE (exit {rc})\n")
    write_records(args["recdir"], [(f"controls-{cfg}.txt", "".join(lines)), (f"controls-{cfg}.json", dumps(out))])
    print("".join(lines).rstrip())
    return rc

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
    code0 = code_provenance_start(REQUIRED_S5N)
    tree0 = tree_fingerprint(os.path.join(runs, cfg))                    # supplementary inventory, not integrity
    hashes0 = {p: sha256_file(p) for p in (log, sca)}                    # the declared inputs, before anything reads them
    S5N = import_s5n()
    os.mkdir(staging)
    s5dir = os.path.join(staging, "s5n")
    start = len(S5N.rows)
    with InputTracker({"runs": runs, "simu5g": os.environ.get("SIMU5G_ROOT")}) as tracker:
        rc5, dig5 = S5N.run_one(runs, cfg, s5dir)                        # the accepted checker, unchanged
        if rc5 == 2 or dig5 is None:
            raise W.Refused(f"the accepted s5n checker refused {cfg} (rc {rc5})")
        s5n_rows = list(S5N.rows[start:])
        chk_txt = open(os.path.join(s5dir, f"{cfg}.check.txt"), encoding="utf-8").read()
        with open(os.path.join(s5dir, f"{cfg}.digest.json"), encoding="utf-8") as fh:
            dig5_file = json.load(fh)
        if dig5_file != json.loads(json.dumps(W_clean_s5v(S5N, dig5))):
            raise W.EvaluationError("the s5n digest written differs from the one returned")
        info, ne = W.s5n_info()
        n = W.parse_name_n(cfg)
        s5n_vline = W.check_s5n_rows(s5n_rows, n, cfg, chk_txt, dig5_file, info, ne)     # the accepted row contract
        pu4 = W.extract_pu4(s5n_rows)                                   # exactly one, well formed; verbatim
        ctx = gather_hrq(args)
        if len(ctx["node_id"]) != n:
            raise W.EvaluationError(f"numUe {n} (name) vs {len(ctx['node_id'])} node ids")
        ev = evaluate(ctx)                                              # ONE A-2.1 replay
    consumed = tracker.verify()
    out = ev["out"]
    verdict = W.compose_verdict(n, ev["wrapper"], ev["fgo"], s5n_rows, info, ne)
    if {p: sha256_file(p) for p in (log, sca)} != hashes0:
        raise W.EvaluationError("an input changed during the evaluation (sha256 of the log / .sca)")
    code = code_provenance_end(code0)
    inputs = {"log_sha256": hashes0[log], "sca_sha256": hashes0[sca], "registry_sha256": ev["registry_sha256"],
              "consumed_sha256": consumed,
              "code": code, "c0": {"census": ev["census"], "lengths": ev["c0info"]["lengths"],
                                              "sha256_a1": ev["c0info"]["sha256_a1"], "sha256_a21": ev["c0info"]["sha256_a21"]},
              "s5n_adapter_validated": d2}
    digest = W.composed_digest(dig5_file, s5n_vline, s5n_rows, ev["wrapper"], verdict, out["a21"], ev["per"],
                               set(W.A21.touched_nodes(ev["res"])), ev["node_id"], ev["agreement"], inputs)
    probs = W.validate_digest(json.loads(dumps(digest)))
    if probs:
        raise W.EvaluationError(f"the composed digest fails its own schema: {probs[:5]}")
    txt_view = dict(out, mode="run", verdict={k: verdict[k] for k in W.VERDICT_KEYS}, held=verdict["held"])
    out["inputs"]["consumed_sha256"] = consumed
    out["inputs"]["code_sha256"] = code
    out["inputs"]["run_tree_inventory"] = {"note": "supplementary diagnostic (path, size, mtime); NOT integrity: the "
                                           "byte-level check is consumed_sha256", "files": len(tree0)}
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
    if {p: sha256_file(p) for p in (log, sca)} != hashes0 or tracker.verify() != consumed:
        raise W.EvaluationError("an input changed during the evaluation (sha256)")
    if tree_fingerprint(os.path.join(runs, cfg)) != tree0:
        raise W.EvaluationError("the run tree inventory changed during the evaluation (supplementary check: files "
                                "added, removed, resized or re-timed)")
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
    code0 = code_provenance_start(REQUIRED_A21 if args["mode"] == "hrq" else REQUIRED_FIXTURE)
    roots = {"simu5g": os.environ.get("SIMU5G_ROOT")}
    roots.update({"runs": args["runs"]} if args["mode"] == "hrq" else {"fixture": args["fixture"]})
    with InputTracker(roots) as tracker:
        ctx = gather_hrq(args) if args["mode"] == "hrq" else gather_fixture(args)
        ev = evaluate(ctx)
    out, cfg = ev["out"], ctx["cfg"]
    out["inputs"]["consumed_sha256"] = tracker.verify()
    out["inputs"]["code_sha256"] = code_provenance_end(code0)
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
    if args["mode"] == "controls":
        return _controls(args)
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
