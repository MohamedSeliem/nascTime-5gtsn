"""E3a trigger and commit identity (E-1). The experiment runs only from a push of the authorised branch, first attempt,
with exactly one commit on the authorised baseline that adds only new files under the authorised paths.
usage: identity.py <repo> <out>   (environment: GITHUB_EVENT_NAME, GITHUB_REF, GITHUB_SHA, GITHUB_RUN_ATTEMPT, pins)"""
import os
import subprocess
import sys


def git(repo, *a):
    r = subprocess.run(["git", "-C", repo, *a], capture_output=True, text=True)
    return r.returncode, r.stdout.strip()


def check(repo, env):
    problems, out = [], []
    ev, ref, sha, att = (env.get(k, "") for k in ("GITHUB_EVENT_NAME", "GITHUB_REF", "GITHUB_SHA", "GITHUB_RUN_ATTEMPT"))
    branch, base = env["E3A_BRANCH"], env["E3A_BASELINE"]
    allowed = env["E3A_ALLOWED_PATHS"].split()
    rc, head = git(repo, "rev-parse", "HEAD")
    rc1, parent = git(repo, "rev-parse", "-q", "--verify", "HEAD^1")
    rc2, _ = git(repo, "rev-parse", "-q", "--verify", "HEAD^2")
    out += [f"event: {ev}", f"ref: {ref}", f"github_sha: {sha}", f"run_attempt: {att}", f"head: {head}",
            f"parent: {parent if rc1 == 0 else 'none'}", f"authorised_baseline: {base}"]
    if ev != "push":
        problems.append(f"event {ev!r} is not push")
    if ref != f"refs/heads/{branch}":
        problems.append(f"ref {ref!r} is not the authorised branch")
    if att != "1":
        problems.append(f"run attempt {att!r}: E3a allows exactly one attempt")
    if rc or head != sha:
        problems.append("checked-out commit is not GITHUB_SHA")
    if rc1 or parent != base:
        problems.append("the commit's parent is not the authorised baseline")
    if rc2 == 0:
        problems.append("merge commit")
    rc, diff = git(repo, "diff", "--name-status", "--no-renames", base, "HEAD")
    if rc:
        problems.append("change set cannot be determined")
        diff = ""
    entries = [l.split("\t", 1) for l in diff.splitlines() if l]
    bad = [f"{s} {p}" for s, p in entries if s != "A" or not any(p == a or (a.endswith("/") and p.startswith(a)) for a in allowed)]
    if bad:
        problems.append(f"changes outside the authorised scope: {bad[:5]}")
    if not any(p == ".github/workflows/e3a-functional-smoke.yml" for _, p in entries):
        problems.append("workflow file not added")
    out += [f"changed_entries: {len(entries)}", f"all_new_files_in_scope: {'yes' if not bad else 'no'}"]
    out += [f"problem: {p}" for p in problems]
    out.append(f"identity_result: {'PASS' if not problems else 'FAIL'}")
    return not problems, out


if __name__ == "__main__":
    ok, out = check(sys.argv[1], os.environ)
    open(sys.argv[2], "w").write("\n".join(out) + "\n")
    print("\n".join(out))
    sys.exit(0 if ok else 1)
