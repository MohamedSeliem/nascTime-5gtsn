"""Tier-1 verdict: C-15 (diagnostic evidence complete, screened and prepared for publication) and the overall verdict.

TIER-1 PASS only if C-1 .. C-15 are all PASS. Otherwise: STOP (disk guard or gate), INFRASTRUCTURE FAILURE (guard not
healthy), TIER-1 BLOCKED (the wrapper suite's real configuration query failed: VM compatibility, F-8; no patch is
applied), or TIER-1 FAIL. An earlier mandatory failure can never yield PASS, and a publication failure fails C-15.
usage: final.py (environment: EV, CI, STEP_OUTCOMES, PUBLISH_OUTCOME, GITHUB_STEP_SUMMARY); exit 0 only on TIER-1 PASS.
"""
import json
import os

REQUIRED = ["identity.txt", "runner.txt", "timings.tsv", "disk.tsv", "lock.txt", "guard.txt", "stage-resources.tsv",
            "capacity.txt", "c-rows.json", "exec-checks.txt"]
CONDITIONAL = {
    "bootstrap": ["nix.txt", "opp_env.txt", "release-assets.txt", "lock-enforcement.txt", "flake-lock-check.txt", "workspace-admin-check.txt"],
    "verify": ["probe.txt", "postdownload-verify.txt", "adaptations-summary.txt", "source-identity.txt"],
    "runtime": ["host-cxx-packages-before.tsv", "runtime-probe-before.txt", "c4-case.txt", "runpath-observation.txt"],
    "b_omnetpp": ["sys-libs.txt"],
    "validate": ["binaries.tsv", "identity-tools.txt", "build-options.txt", "opp_run-version.txt", "runtime-symbols.txt",
                 "validate-result.txt", "runpath-observation-validate.txt"],
    "srcchanges": ["source-changes-summary.txt"],
    "wrapper": ["wrapper-setup.txt", "wrapper-suite.txt", "opp_run-audit.tsv", "wrapper-result.txt", "wrapper-results.tsv"],
}


def verdict(state, outcomes, publish_outcome, present):
    def ran(s):
        return outcomes.get(s) in ("success", "failure")
    required = list(REQUIRED)
    for step, files in CONDITIONAL.items():
        if ran(step):
            required += files
    case = state.get("c4_case")
    if case == "A":
        required += ["host-libcxx.txt"]
        if outcomes.get("runtime") == "success":
            required += ["apt-remove-proposed.txt", "apt-remove-simulation.txt", "apt-remove-transaction.txt", "apt-remove.txt",
                         "host-cxx-packages-after.tsv", "host-packages.diff", "runtime-probe-after.txt"]
    if case in ("A", "B") and outcomes.get("runtime") == "success":
        required += ["runtime-gates.txt"]
    missing = [f for f in required if f not in present]
    c15 = publish_outcome == "success" and not missing
    rows = [r for r in state["rows"] if r["id"].startswith("C-")]
    rows.append({"id": "C-15", "criterion": "diagnostic evidence complete, screened and prepared for publication",
                 "result": "PASS" if c15 else "FAIL", "detail": f"publication={publish_outcome}; missing={missing or 'none'}"})
    complete = [r["id"] for r in rows] == [f"C-{i}" for i in range(1, 16)]
    if state["stop"]:
        v = "STOP"
    elif state["guard_failure"]:
        v = "INFRASTRUCTURE FAILURE"
    elif state.get("blocked"):
        v = "TIER-1 BLOCKED (VM compatibility, F-8; no patch applied)"
    elif complete and all(r["result"] == "PASS" for r in rows):
        v = "TIER-1 PASS"
    else:
        v = "TIER-1 FAIL"
    return v, rows


def main():
    ev, ci = os.environ["EV"], os.environ["CI"]
    p = os.path.join(ci, "publish")
    outcomes = {k: v.get("outcome") for k, v in json.loads(os.environ.get("STEP_OUTCOMES") or "{}").items()}
    try:
        state = json.load(open(os.path.join(ev, "c-rows.json")))
    except (OSError, ValueError):
        state = {"stop": False, "guard_failure": True, "blocked": False, "rows": []}
    try:
        state["c4_case"] = open(os.path.join(ev, "c4-case.txt")).read().split(": ", 1)[1].strip()
    except (OSError, IndexError):
        state["c4_case"] = ""
    present = set(os.listdir(p)) if os.path.isdir(p) else set()
    v, rows = verdict(state, outcomes, os.environ.get("PUBLISH_OUTCOME"), present)
    lines = [f"# Tier-1 full-stack validation: {v}", "",
             "Level-2 validation only: release builds, linkage, the single C++ runtime, real OMNeT++ configuration queries "
             "and synthetic wrapper lifecycle tests. No simulation is executed; no functional, scientific or VM "
             "byte-equivalence claim. Release-asset checksums come from a separate fetch; adaptation screening is recipe "
             "consistency; an in-process lock update is detected and write-blocked, not proven impossible; only SYS_LIBS is "
             "compared with the VM.", "",
             "| ID | Criterion | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['criterion']} | {r['result']} | {r['detail']} |" for r in rows]
    text = "\n".join(lines) + "\n"
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text)
    print(text)
    open(os.path.join(ci, "verdict.txt"), "w").write(v + "\n")
    if os.path.isdir(p):
        open(os.path.join(p, "verdict.md"), "w").write(text)
    return 0 if v == "TIER-1 PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
