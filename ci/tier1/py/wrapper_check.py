"""C-13: evaluation of the A2-V1 wrapper regression suite run (ci/tier1/wrapper/run-suite.sh) and its audit log.

Evidence class: REAL CONFIGURATION QUERIES (opp_run -q runconfig of the reviewed configurations) + SYNTHETIC LIFECYCLE
TESTS (stub simulator, synthetic evaluation). Level-2 validation; not functional simulation and not scientific evidence.

usage: wrapper_check.py <evidence dir> <expected summary line> <expected test count> <guarded exit>
Writes wrapper-results.tsv and wrapper-result.txt; exit 0 only on PASS.
"""
import os
import re
import sys

APPROVED = {"runconfig-base": "-u Cmdenv -f m2s72s5.ini -c M2S72-E0vN-q0-one0-n2-f1 -r 0 -q runconfig",
            "runconfig-a2v1": "-u Cmdenv -f m2s72a2v.ini -c M2S72-E0vN-q0-one0-n2-f1_A2V1 -r 0 -q runconfig",
            "identity": "-v"}
CWD = re.compile(r"^(<repo>/simulations/m2|<suite-tmp>/[^/]+/repo/simulations/m2)$")


def kv(path):
    d = {}
    try:
        for line in open(path):
            if ": " in line:
                k, v = line.rstrip("\n").split(": ", 1)
                d.setdefault(k, v)
    except OSError:
        pass
    return d


def status_sets(path):
    tracked, untracked, ignored = set(), set(), set()
    try:
        for l in open(path).read().splitlines():
            code, p = l[:2], l[3:]
            (untracked if code == "??" else ignored if code == "!!" else tracked).add(p)
    except OSError:
        return None
    return tracked, untracked, ignored


def evaluate(ev, expected_line, expected_n, guarded_rc):
    setup = kv(os.path.join(ev, "wrapper-setup.txt"))
    try:
        out = open(os.path.join(ev, "wrapper-suite.txt"), errors="replace").read().splitlines()
    except OSError:
        out = []
    tests = [(m.group(1), m.group(2)) for m in (re.match(r"^(PASS|FAIL)  (.*?)(?::\s.*)?$", l) for l in out) if m]
    passed = [n for r, n in tests if r == "PASS"]
    failed = [n for r, n in tests if r == "FAIL"]
    last = next((l for l in reversed(out) if l.strip()), "")
    calls = []
    try:
        for l in open(os.path.join(ev, "opp_run-audit.tsv")).read().splitlines()[1:]:
            f = l.split("\t")
            if len(f) == 8:
                calls.append(dict(zip(("seq", "utc", "decision", "kind", "cwd", "argv", "exit", "detail"), f)))
    except OSError:
        calls = None
    problems = []
    if setup.get("suite_setup") != "PASS":
        problems.append("suite setup failed")
    if str(guarded_rc) != "0":
        problems.append(f"guarded session exit {guarded_rc}")
    if setup.get("suite_exit") != "0":
        problems.append(f"suite exit {setup.get('suite_exit', 'absent')}")
    if last != expected_line:
        problems.append(f"summary line {last!r}")
    if failed:
        problems.append(f"{len(failed)} failed test(s)")
    if len(tests) != expected_n or len(passed) != expected_n:
        problems.append(f"{len(passed)} PASS lines of {len(tests)} test lines (expected {expected_n})")
    forwarded = [c for c in calls or [] if c["decision"] == "FORWARDED"]
    refused = [c for c in calls or [] if c["decision"] != "FORWARDED"]
    runconfig = [c for c in forwarded if c["kind"].startswith("runconfig-")]
    nonzero = [c for c in forwarded if c["exit"] != "0"]
    if calls is None:
        problems.append("audit log missing")
    else:
        if refused or setup.get("unauthorised_marker") != "absent":
            problems.append(f"{len(refused)} refused simulator call(s)")
        bad = [c["seq"] for c in forwarded if APPROVED.get(c["kind"]) != c["argv"] or not CWD.match(c["cwd"])
               or c["detail"] != "hazards none"]
        if bad:
            problems.append(f"forwarded calls outside the approved vectors/directories: {bad}")
        if not any(c["kind"] == "runconfig-base" and c["cwd"] == "<repo>/simulations/m2" for c in runconfig) \
                or not any(c["kind"] == "runconfig-a2v1" for c in runconfig) or len(runconfig) < 2:
            problems.append("expected real configuration queries not observed")
    if setup.get("results_root_env") != "<unset>" or setup.get("vm_results_root_present_after") != "no":
        problems.append("real results root reachable")
    st_b = status_sets(os.path.join(ev, "wrapper-git-status-before.txt"))
    st_a = status_sets(os.path.join(ev, "wrapper-git-status-after.txt"))
    if st_b is None or st_a is None:
        problems.append("repository status not recorded")
        new_untracked, new_ignored = [], []
    else:
        new_untracked = sorted(st_a[1] - st_b[1])
        new_ignored = sorted(st_a[2] - st_b[2])
        if st_a[0]:
            problems.append(f"tracked repository modifications: {sorted(st_a[0])[:5]}")
        if new_untracked:
            problems.append(f"new untracked (not ignored) files: {new_untracked[:5]}")
    # Classification of a failure (no automatic correction is ever applied).
    text = "\n".join(out)
    blocked = bool(failed) and bool(nonzero) and any(k in text for k in ("G0-config", "runconfig", "config-diff"))
    source_discrepancy = bool(failed) and any(k in text for k in ("A2-0s", "G0-source"))
    ok = not problems
    rows = ["result\ttest"] + [f"{r}\t{n}" for r, n in tests]
    open(os.path.join(ev, "wrapper-results.tsv"), "w").write("\n".join(rows) + "\n")
    res = [f"evidence_class: REAL CONFIGURATION QUERIES + SYNTHETIC LIFECYCLE TESTS (level 2; not simulation, not scientific evidence)",
           f"tests_total: {len(tests)}", f"tests_passed: {len(passed)}", f"tests_failed: {len(failed)}",
           f"summary_line: {last}", f"suite_exit: {setup.get('suite_exit', 'absent')}",
           f"audit_calls_total: {len(calls or [])}", f"audit_forwarded: {len(forwarded)}",
           f"audit_forwarded_runconfig_base: {sum(c['kind'] == 'runconfig-base' for c in forwarded)}",
           f"audit_forwarded_runconfig_a2v1: {sum(c['kind'] == 'runconfig-a2v1' for c in forwarded)}",
           f"audit_forwarded_identity: {sum(c['kind'] == 'identity' for c in forwarded)}",
           f"audit_forwarded_nonzero_exit: {len(nonzero)}", f"audit_refused: {len(refused)}",
           f"audit_working_directories: {', '.join(sorted({re.sub(r'<suite-tmp>/[^/]+/', '<suite-tmp>/<clone>/', c['cwd']) for c in forwarded})) or 'none'}",
           f"repository_tracked_changes: {len(st_a[0]) if st_a else 'n/a'}",
           f"repository_new_untracked: {len(new_untracked)}", f"repository_new_ignored: {len(new_ignored)}",
           f"classification_vm_compatibility_blocked: {'yes (F-8; no patch applied)' if blocked else 'no'}",
           f"classification_simu5g_source_discrepancy: {'yes (release tree vs reviewed source; no substitution)' if source_discrepancy else 'no'}"]
    res += [f"problem: {p}" for p in problems]
    res.append(f"wrapper_result: {'PASS' if ok else 'FAIL'}")
    open(os.path.join(ev, "wrapper-result.txt"), "w").write("\n".join(res) + "\n")
    return ok, res


if __name__ == "__main__":
    if len(sys.argv) != 5:
        raise SystemExit(__doc__)
    ok, res = evaluate(sys.argv[1], sys.argv[2], int(sys.argv[3]), sys.argv[4])
    print("\n".join(res))
    sys.exit(0 if ok else 1)
