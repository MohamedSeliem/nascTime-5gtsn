"""E-6: the existing, reviewed U1 oracle of simulations/m2/check/check_m2s4.py, applied unchanged to the E3a run.

check_m2s4.py reads `OUT, RUNS1, HASHES1 = sys.argv[1:4]` at import time and imports oracle_m2s3 / gate_m2s4 (which only
parse argv / define functions at import). This adapter supplies that argument vector with OUT = the sealed raw directory
(so RUNS = <raw>/runs, the layout of m2s4.sh's --result-dir=$OUT/runs/<config>), imports the module without executing
main() (which is replaced by a trap), and calls exactly the U1 evaluation that main() performs:
    eval_unit("M2S4U", L_REF)            # main(): UNIT["M2S4U"] = ("U1", L_REF, ...); okall = all(ok for ok, d in res)
No tolerance is introduced and no reviewed file is modified. The adapter adds one stricter guard (non-vacuity: each
requester published at least U1_MIN_EXCHANGES exchanges, all with D = the reference), reported separately.

usage: u1_oracle.py <raw dir> <checker dir> <out json> <out txt> <ref_D_ps> <min_exchanges>; exit 0 only on PASS."""
import importlib
import inspect
import json
import os
import sys


def evaluate(raw, check_dir, ref_d, min_ex):
    sys.dont_write_bytecode = True
    out = {"requirements": {}, "rows": {}, "sides": {}, "problems": []}
    saved_argv = sys.argv[:]
    sys.argv = ["check_m2s4.py", raw, "-", "-"]
    sys.path.insert(0, check_dir)
    try:
        C = importlib.import_module("check_m2s4")
    except Exception as e:  # noqa: BLE001
        out["problems"].append(f"checker import failed: {type(e).__name__}: {e}")
        out["result"] = "FAIL"
        return out
    finally:
        sys.argv = saved_argv

    def _trap(*a, **k):
        raise RuntimeError("check_m2s4.main() must not be called by the E3a adapter")
    C.main = _trap
    # Confirm the acceptance requirements directly against the reviewed implementation.
    src = inspect.getsource(C.eval_unit)
    req = {
        "checker_path": os.path.realpath(C.__file__),
        "L_REF_ps": C.L_REF,
        "L_REF_is_reference": C.L_REF == ref_d,
        "counters": list(C.COUNTERS),
        "counters_count_11": len(C.COUNTERS) == 11,
        "D_equals_pcap_and_reference": 'if int(r["D"]) != D or D != ref_D' in src,
        "logged_t1_t4_equal_pcap": "logged t1..t4 != PCAP" in src,
        "termination_valid_fcs": 'f["f"]["fcs_ok"]' in src and "terminated" in src,
        "counters_expected_zero": "want = {k: exp.get(X, {}).get(k, 0) for k in COUNTERS}" in src,
        "selftest_required": 'U.sc[X].get("selfTestPassed") != 1' in src,
        "runs_dir": C.RUNS,
    }
    out["requirements"] = req
    if not all(v for k, v in req.items() if k not in ("checker_path", "L_REF_ps", "counters", "runs_dir")) \
            or C.RUNS != os.path.join(raw, "runs"):
        out["problems"].append("reviewed oracle does not contain the expected U1 requirements")
    try:
        res, data = C.eval_unit("M2S4U", C.L_REF)
    except Exception as e:  # noqa: BLE001  missing or malformed evidence
        out["problems"].append(f"U1 evidence missing or malformed: {type(e).__name__}: {str(e)[:300]}")
        out["result"] = "FAIL"
        return out
    out["rows"] = {k: {"result": "PASS" if ok else "FAIL", "detail": d} for k, (ok, d) in res.items()}
    u1 = all(ok for ok, d in res.values())
    nonvac = True
    for side, (n, ds, owd) in data["info"].items():
        sc = data["U"].sc.get(side, {})
        out["sides"][side] = {"exchanges": n, "D_values_ps": ds, "one_way_ps": owd,
                              "counters": {k: sc.get(k) for k in C.COUNTERS}, "selfTestPassed": sc.get("selfTestPassed")}
        if n < min_ex or ds != [ref_d]:
            nonvac = False
    out["rows"]["N"] = {"result": "PASS" if nonvac else "FAIL",
                        "detail": f"adapter guard: each requester >= {min_ex} exchanges, all D = {ref_d} ps"}
    if set(data["info"]) != {"ttA", "ttB"}:
        nonvac = False
        out["problems"].append("both requesters must be evaluated")
    out["u1_reviewed"] = "PASS" if u1 else "FAIL"
    out["result"] = "PASS" if u1 and nonvac and not out["problems"] else "FAIL"
    return out


def main(argv):
    if len(argv) != 7:
        raise SystemExit(__doc__)
    raw, check_dir, oj, ot, ref_d, min_ex = argv[1], argv[2], argv[3], argv[4], int(argv[5]), int(argv[6])
    r = evaluate(raw, check_dir, ref_d, min_ex)
    json.dump(r, open(oj, "w"), indent=1, default=str)
    lines = [f"u1_oracle_result: {r['result']}", f"u1_reviewed_rows: {r.get('u1_reviewed', 'NOT EVALUATED')}"]
    lines += [f"row {k}: {v['result']}  {v['detail']}" for k, v in r["rows"].items()]
    lines += [f"side {k}: {v}" for k, v in r["sides"].items()]
    lines += [f"requirement {k}: {v}" for k, v in r["requirements"].items()]
    lines += [f"problem: {p}" for p in r["problems"]]
    open(ot, "w").write("\n".join(lines) + "\n")
    print("\n".join(lines))
    return 0 if r["result"] == "PASS" else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
