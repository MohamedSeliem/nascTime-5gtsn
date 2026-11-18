"""E3a verdict: completes E-8 with the publication outcomes and decides the verdict.

E3a PASS only if every mandatory row E-1 .. E-8 is PASS (E-9 is informational). Otherwise STOP, INFRASTRUCTURE FAILURE,
E3a BLOCKED (6.5.0 compatibility; only when a failed pre-flight or simulation shows a NED/INI/loading diagnostic, which
is quoted) or E3a FAIL. Uploads are checked by the conclusion step. Evidence class: functional smoke evidence (level 2),
not independent scientific validation.
usage: final_t2.py (environment: REC, E3, CI, PUBLISH_OUTCOME, T2PUBLISH_OUTCOME, RAWPUB_OUTCOME, GITHUB_STEP_SUMMARY)"""
import json
import os


def kv(p):
    d = {}
    try:
        for line in open(p):
            if ": " in line:
                k, v = line.rstrip("\n").split(": ", 1)
                d.setdefault(k, v)
    except OSError:
        pass
    return d


def verdict(state, env, rawpub):
    rows = [dict(r) for r in state.get("rows", [])]
    pub = {"tier-1 diagnostics": env.get("PUBLISH_OUTCOME"), "tier-2 diagnostics": env.get("T2PUBLISH_OUTCOME"),
           "raw evidence": env.get("RAWPUB_OUTCOME")}
    for r in rows:
        if r["id"] == "E-8":
            ok = r["result"] == "PASS" and all(v == "success" for v in pub.values()) and rawpub.get("rawpub_result") == "PASS"
            r["result"] = "NOT EVALUATED" if r["result"] == "NOT EVALUATED" else ("PASS" if ok else "FAIL")
            r["detail"] += (f"; publication: " + ", ".join(f"{k}={v}" for k, v in pub.items())
                            + f"; raw content check={rawpub.get('rawpub_result', 'absent')} files={rawpub.get('files')} "
                              f"bytes={rawpub.get('total_bytes')}")
    mand = [r for r in rows if r.get("mandatory")]
    complete = [r["id"] for r in mand] == [f"E-{i}" for i in range(1, 9)]
    if state.get("stop"):
        v = "STOP"
    elif state.get("guard_failure"):
        v = "INFRASTRUCTURE FAILURE"
    elif state.get("blocked"):
        v = "E3a BLOCKED (OMNeT++ 6.5.0 compatibility; no NED/INI patched)"
    elif complete and all(r["result"] == "PASS" for r in mand):
        v = "E3a PASS"
    else:
        v = "E3a FAIL"
    return v, rows


def main():
    rec, e3, ci = os.environ["REC"], os.environ["E3"], os.environ["CI"]
    try:
        state = json.load(open(os.path.join(rec, "e-rows.json")))
    except (OSError, ValueError):
        state = {"stop": False, "guard_failure": True, "blocked": False, "rows": []}
    v, rows = verdict(state, os.environ, kv(os.path.join(rec, "rawpub-check.txt")))
    lines = [f"# E3a hosted functional smoke (M2S4U, run 0): {v}", "",
             "Functional smoke evidence (level 2): the existing reviewed M2S4U configuration initialises, executes, completes "
             "and meets its reviewed U1 unit oracle on standard GitHub-hosted infrastructure with the tier-1 stack. It is NOT "
             "independent scientific validation (a CI run started by the development agent is not level-3 evidence).", "",
             "| ID | Criterion | Result | Detail |", "|---|---|---|---|"]
    lines += [f"| {r['id']} | {r['criterion']} | {r['result']} | {r['detail']} |" for r in rows]
    if state.get("blocked_diagnostics"):
        lines += ["", "Blocking diagnostics: " + " / ".join(state["blocked_diagnostics"])]
    text = "\n".join(lines) + "\n"
    if os.environ.get("GITHUB_STEP_SUMMARY"):
        open(os.environ["GITHUB_STEP_SUMMARY"], "a").write(text)
    print(text)
    os.makedirs(e3, exist_ok=True)
    open(os.path.join(e3, "verdict.txt"), "w").write(v + "\n")
    json.dump({"verdict": v, "rows": rows}, open(os.path.join(rec, "e-final.json"), "w"), indent=1)
    p = os.path.join(ci, "publish")
    if os.path.isdir(p):
        open(os.path.join(p, "e3a-verdict.md"), "w").write(text)
    return 0 if v == "E3a PASS" else 1


if __name__ == "__main__":
    raise SystemExit(main())
