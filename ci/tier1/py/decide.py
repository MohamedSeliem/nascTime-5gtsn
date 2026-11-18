"""Tier-1 trigger selection (C3). Decides whether the expensive full-stack job runs for a pull_request event.

  labeled                         -> run only if the added label is the override label (an unrelated label never
                                     starts a run)
  opened / synchronize / reopened /
  ready_for_review                -> run if the PR carries the override label; otherwise skip drafts; otherwise run
                                     if the complete change set (added, modified, deleted, both sides of renames and
                                     copies) touches a relevant path
  anything else                   -> fail closed

The change set is `git diff --name-status -M <base>...<head>` of the PR. If it cannot be determined (missing commits,
git error, unparsable output, or an empty diff for a PR that GitHub reports as changing files) the job FAILS; it never
silently skips. usage: decide.py <event.json> <repo> <out>; writes run=true|false and reason=... to <out>.
"""
import fnmatch
import json
import subprocess
import sys

LABEL = "tier1:run"
RELEVANT = ["src/*", "simulations/*.ned", "simulations/*.ini", "simulations/m2/m2s72a2v1.sh", "simulations/m2/check/*",
            "Makefile", "ci/tier1/*", ".github/workflows/tier1-full-stack.yml"]


class Undetermined(Exception):
    pass


def relevant(path):
    return any(fnmatch.fnmatchcase(path, p) for p in RELEVANT)


def change_set(repo, base, head, reported):
    for sha in (base, head):
        if not sha or subprocess.run(["git", "-C", repo, "cat-file", "-e", f"{sha}^{{commit}}"], capture_output=True).returncode:
            raise Undetermined(f"commit {sha or '<missing>'} not available")
    r = subprocess.run(["git", "-C", repo, "diff", "--name-status", "-M", "-C", "-z", f"{base}...{head}"], capture_output=True)
    if r.returncode:
        raise Undetermined(f"git diff failed: {r.stderr.decode(errors='replace').strip()[:300]}")
    f = r.stdout.decode("utf-8", "surrogateescape").split("\0")
    if f and f[-1] == "":
        f.pop()
    paths, entries, i = [], 0, 0
    while i < len(f):
        st = f[i]
        if not st or st[0] not in "AMDTRCU":
            raise Undetermined(f"unparsable diff status {st!r}")
        n = 2 if st[0] in "RC" else 1
        if i + n >= len(f):
            raise Undetermined("truncated diff output")
        paths += f[i + 1:i + 1 + n]
        entries += 1
        i += 1 + n
    if entries == 0 and reported:
        raise Undetermined(f"empty change set but the PR reports {reported} changed files")
    return entries, paths


def decide(event, repo):
    action = event.get("action")
    pr = event.get("pull_request") or {}
    labels = {l.get("name") for l in pr.get("labels") or []}
    if not pr:
        raise Undetermined("event has no pull_request")
    if action == "labeled":
        name = (event.get("label") or {}).get("name")
        if name == LABEL:
            return True, f"override label '{LABEL}' added"
        return False, f"unrelated label '{name}' added; no run"
    if action not in ("opened", "synchronize", "reopened", "ready_for_review"):
        raise Undetermined(f"unexpected action {action!r}")
    if LABEL in labels:
        return True, f"PR carries the override label '{LABEL}'"
    if pr.get("draft"):
        return False, "draft PR without the override label; no run"
    entries, paths = change_set(repo, (pr.get("base") or {}).get("sha"), (pr.get("head") or {}).get("sha"), pr.get("changed_files"))
    hits = sorted({p for p in paths if relevant(p)})
    if hits:
        return True, f"{len(hits)} relevant path(s) in {entries} changed entries, e.g. {', '.join(hits[:5])}"
    return False, f"no relevant path in {entries} changed entries"


def main(argv):
    if len(argv) != 4:
        raise SystemExit(__doc__)
    event = json.load(open(argv[1]))
    try:
        run, reason = decide(event, argv[2])
    except Undetermined as e:
        print(f"::error::tier-1 trigger selection could not determine the change set: {e}")
        return 1
    reason = reason.replace("\n", " ")
    with open(argv[3], "a") as f:
        f.write(f"run={'true' if run else 'false'}\nreason={reason}\n")
    print(f"run={run} reason={reason}")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
