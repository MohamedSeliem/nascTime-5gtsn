"""Tier-2 experiment trigger and commit identity (E-1). The experiment runs only from a push of its authorised branch,
first attempt, with exactly one commit on its authorised parent. Change scope of that commit: the experiment's workflow
(added) and files under the experiment scope (added; modified only where the experiment allows it, e.g. E3b's shared
tier-2 implementation); nothing deleted, frozen paths untouched. Cumulatively against the integration baseline, only the
scope, the experiment workflow and the frozen (earlier experiment) workflows may differ.
usage: identity.py <repo> <out>  (environment: GITHUB_EVENT_NAME, GITHUB_REF, GITHUB_SHA, GITHUB_RUN_ATTEMPT, EXP_* pins)"""
import os
import subprocess
import sys


def git(repo, *a):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def entries(repo, a, b):
    rc, diff = git(repo, "diff", "--name-status", "--no-renames", a, b)
    if rc:
        return None
    return [l.split("\t", 1) for l in diff.splitlines() if l]


def check(repo, env):
    problems, out = [], []
    ev, ref, sha, att = (env.get(k, "") for k in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_SHA", "GITHUB_RUN_ATTEMPT"))
    branch, parent_want, base = env["EXP_BRANCH"], env["EXP_PARENT"], env["EXP_BASELINE"]
    wf, scope = env["EXP_WORKFLOW"], env["EXP_SCOPE"]
    allow_mod = env.get("EXP_ALLOW_MODIFIED") == "yes"
    frozen = env.get("EXP_FROZEN", "").split()
    rc, head = git(repo, "rev-parse", "HEAD")
    rc1, parent = git(repo, "rev-parse", "-q", "--verify", "HEAD^1")
    rc2, _ = git(repo, "rev-parse", "-q", "--verify", "HEAD^2")
    out += [f"experiment: {env.get('EXP_ID')}", f"event: {ev}", f"ref: {ref}", f"github_sha: {sha}", f"run_attempt: {att}",
            f"head: {head}", f"parent: {parent if rc1 == 0 else 'none'}", f"authorised_parent: {parent_want}",
            f"integration_baseline: {base}"]
    if ev != "push":
        problems.append(f"event {ev!r} is not push")
    if ref != f"refs/heads/{branch}":
        problems.append(f"ref {ref!r} is not the authorised branch")
    if att != "1":
        problems.append(f"run attempt {att!r}: the experiment allows exactly one attempt")
    if rc or head != sha:
        problems.append("checked-out commit is not GITHUB_SHA")
    if rc1 or parent != parent_want:
        problems.append("the commit's parent is not the authorised parent")
    if rc2 == 0:
        problems.append("merge commit")
    own = entries(repo, parent_want, "HEAD")
    cum = entries(repo, base, "HEAD")
    if own is None or cum is None:
        problems.append("change set cannot be determined")
        own, cum = own or [], cum or []

    def in_scope(p):
        return p.startswith(scope)
    bad = []
    for s, p in own:
        if p == wf:
            ok = s == "A"
        elif in_scope(p):
            ok = s == "A" or (s == "M" and allow_mod)
        else:
            ok = False
        if not ok:
            bad.append(f"{s} {p}")
    if bad:
        problems.append(f"changes outside the authorised scope: {bad[:5]}")
    if not any(p == wf and s == "A" for s, p in own):
        problems.append("experiment workflow not added")
    touched_frozen = [p for s, p in own if p in frozen]
    if touched_frozen:
        problems.append(f"frozen paths changed: {touched_frozen}")
    cum_bad = [f"{s} {p}" for s, p in cum if not (in_scope(p) or p == wf or p in frozen)]
    if cum_bad:
        problems.append(f"cumulative changes against the integration baseline outside the scope: {cum_bad[:5]}")
    out += [f"commit_entries: {len(own)}", f"added: {sum(s == 'A' for s, _ in own)}", f"modified: {sum(s == 'M' for s, _ in own)}",
            f"cumulative_entries_vs_baseline: {len(cum)}", f"scope_ok: {'yes' if not bad and not cum_bad else 'no'}"]
    out += [f"problem: {p}" for p in problems]
    out.append(f"identity_result: {'PASS' if not problems else 'FAIL'}")
    return not problems, out


if __name__ == "__main__":
    ok, out = check(sys.argv[1], os.environ)
    open(sys.argv[2], "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    sys.exit(0 if ok else 1)
