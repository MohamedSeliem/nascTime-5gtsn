"""E-6 (E3b): the existing, reviewed per-run M2-S5 oracle of simulations/m2/check/check_m2s5.py, applied unchanged to the
single E3b run:
    rows_5gs(Run(RUNS, "M2S5", 0), None, exp_missing=0)
check_m2s5.py reads `OUT, RUNS4, HASHES4 = sys.argv[1:4]` at import and imports check_m2s4, pcapng, inet_model,
oracle_m2s3, gate_m2s5 and gate_v0 (which only parse argv / define functions at import). The adapter supplies
OUT = the sealed raw directory and "-" for the M2-S4 baseline arguments (never used: R4 is None), imports the module
without executing main() (replaced by a trap) and calls only rows_5gs. A Python audit hook records every file the import
and the evaluation open; any file outside the raw directory, the reviewed checker directory and the Python runtime
fails the oracle (no historical or private result file may be read).

Rows (unmodified; integer ps): C1..C7, S1, S2, P2 fully; C8 and P1 PARTIALLY (their M2-S4 baseline comparisons are not
evaluated without the baseline run); S3 NOT EVALUATED (needs the M2S4 baseline run). No full M2-S5 campaign acceptance.
usage: m2s5_oracle.py <raw dir> <checker dir> <out json> <out txt>; exit 0 only on PASS."""
import importlib
import inspect
import json
import os
import sys

EXPECTED_ROWS = ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "S1", "S2", "P1", "P2"]
PARTIAL = {
    "C8": {"evaluated": "no TtSyncIngressTag reaches the slave (slave eth[0] audit framesWithSyncTag = 0)",
           "not_evaluated": "DS-TT eth[1] M2-S0 tag recovery counters equal to the M2-S4 baseline and framesInvalidTag = 0 "
                            "(checked by the reviewed code only with the baseline run)"},
    "P1": {"evaluated": "NW-TT link delay from PCAP = 50 000 ps for every completed exchange (non-empty)",
           "not_evaluated": "NW-TT Pdelay-engine log byte-identical to the M2-S4 baseline (the detail text 'engine log "
                            "byte-identical to M2S4: False' printed by the reviewed code means NOT EVALUATED here)"},
}
NOT_EVALUATED = {"S3": "online correction = offline oracle on the M2-S4 records (needs the M2S4 baseline run, which the "
                       "one-simulation rule excludes)"}


def evaluate(raw, check_dir):
    out, opened, roots = _evaluate(raw, check_dir)
    raw_r, chk_r, py_roots = roots
    outside = sorted({p for p in opened
                      if not os.path.realpath(p).startswith((raw_r + os.sep, chk_r + os.sep))
                      and not any(os.path.realpath(p).startswith(r + os.sep) or os.path.realpath(p) == r for r in py_roots)
                      and not p.startswith(("/proc/", "/dev/"))})
    out["files_opened_outside_raw_and_checker"] = outside
    if outside:
        out["problems"].append(f"files opened outside the raw directory and the checker: {outside[:5]}")
        out["result"] = "FAIL"
    return out


def _evaluate(raw, check_dir):
    sys.dont_write_bytecode = True
    raw_r, chk_r = os.path.realpath(raw), os.path.realpath(check_dir)
    py_roots = {os.path.realpath(p) for p in (sys.prefix, sys.base_prefix, sys.exec_prefix, os.path.dirname(os.__file__))}
    opened = []

    def hook(event, args):
        if event == "open" and args and isinstance(args[0], (str, bytes, os.PathLike)):
            opened.append(os.fsdecode(args[0]))
    sys.addaudithook(hook)
    out = {"requirements": {}, "rows": {}, "partial": PARTIAL, "not_evaluated": NOT_EVALUATED, "counts": {}, "problems": []}
    roots = (raw_r, chk_r, py_roots)
    saved = sys.argv[:]
    sys.argv = ["check_m2s5.py", raw, "-", "-"]
    sys.path.insert(0, check_dir)
    try:
        C = importlib.import_module("check_m2s5")
    except Exception as e:  # noqa: BLE001
        out["problems"].append(f"checker import failed: {type(e).__name__}: {e}")
        out["result"] = "FAIL"
        return out, opened, roots
    finally:
        sys.argv = saved

    def _trap(*a, **k):
        raise RuntimeError("check_m2s5.main() must not be called by the E3b adapter")
    C.main = _trap
    src = inspect.getsource(C.rows_5gs)
    req = {
        "checker_path": os.path.realpath(C.__file__),
        "runs_dir_is_raw": os.path.realpath(C.RUNS) == os.path.join(raw_r, "runs"),
        "C1_requires_n3_and_ethernet_points": 'res["C1"] = (not probs and n > 0 and n3 > 0' in src,
        "C7_all_gm_syncs_delivered": "len(fus) == n_sync_gm - exp_missing" in src,
        "S2_zero_error_nonvacuous": 'len(m.out["fu"]) > 0' in src and "not bad_samples" in src and "not nonzero" in src,
        "P2_no_pdelay_in_5gs": "in5gs == 0" in src,
        "C8_audit_zero": "ok8 = audit == 0" in src,
        "baseline_parts_guarded_by_R4": src.count("if R4 is not None:") == 3,
        "L_REF_ps": getattr(C, "L_REF", None),
    }
    out["requirements"] = req
    if not all(v for k, v in req.items() if k not in ("checker_path", "L_REF_ps")) or req["L_REF_ps"] != 50000:
        out["problems"].append("reviewed oracle does not contain the expected per-run requirements")
    try:
        R = C.Run(C.RUNS, "M2S5", 0)
        res = C.rows_5gs(R, None, exp_missing=0)
    except Exception as e:  # noqa: BLE001  missing or malformed evidence
        out["problems"].append(f"M2-S5 evidence missing or malformed: {type(e).__name__}: {str(e)[:300]}")
        out["result"] = "FAIL"
        return out, opened, roots
    keys = sorted(k for k in res if not k.startswith("_"))
    if keys != sorted(EXPECTED_ROWS):
        out["problems"].append(f"unexpected row set {keys}")
    for k in EXPECTED_ROWS:
        if k in res:
            ok, d = res[k]
            out["rows"][k] = {"result": "PASS" if ok else "FAIL", "detail": d,
                              "scope": "partial" if k in PARTIAL else "full"}
    try:
        m = res.get("_model")
        n3_fu = sum(1 for d, q, inner in C.n3_inner(R.n3path)
                    if C.C4.inner_type(inner)[0] and C.C4.inner_type(inner)[1] == C.FU)
        out["counts"] = {
            "gm_syncs": len(C.sel(R.gm, 2, C.SYNC)), "gm_follow_ups": len(C.sel(R.gm, 2, C.FU)),
            "slave_syncs": len(C.sel(R.sl, 1, C.SYNC)), "slave_follow_ups": len(C.sel(R.sl, 1, C.FU)),
            "n3_follow_ups": n3_fu, "nwtt_link_delay_exchanges": len(R.lup_table_cache),
            "slave_pdelay_samples": len(R.V["pdelay"]), "slave_clock_samples": len(C.clock_samples(R.V)),
            "slave_model_steps": len(m.out["fu"]) if m else None,
        }
    except Exception as e:  # noqa: BLE001
        out["problems"].append(f"counts not computable: {type(e).__name__}: {e}")
    out["result"] = "PASS" if (not out["problems"] and all(r["result"] == "PASS" for r in out["rows"].values())
                               and len(out["rows"]) == len(EXPECTED_ROWS)) else "FAIL"
    return out, opened, roots


def main(argv):
    if len(argv) != 5:
        raise SystemExit(__doc__)
    r = evaluate(argv[1], argv[2])
    json.dump(r, open(argv[3], "w"), indent=1, default=str)
    lines = [f"m2s5_oracle_result: {r['result']}"]
    for k, v in r["rows"].items():
        lines.append(f"row {k}: {v['result']} ({v['scope']})  {v['detail']}")
        if k in PARTIAL:
            lines.append(f"row {k} evaluated: {PARTIAL[k]['evaluated']}")
            lines.append(f"row {k} NOT EVALUATED: {PARTIAL[k]['not_evaluated']}")
    lines += [f"row {k}: NOT EVALUATED  {v}" for k, v in NOT_EVALUATED.items()]
    lines += [f"count {k}: {v}" for k, v in r["counts"].items()]
    lines += [f"requirement {k}: {v}" for k, v in r["requirements"].items()]
    lines.append(f"files_opened_outside_raw_and_checker: {r.get('files_opened_outside_raw_and_checker', 'n/a')}")
    lines += [f"problem: {p}" for p in r["problems"]]
    open(argv[4], "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if r["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
