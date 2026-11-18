import hashlib, os, re, subprocess
EV, repo = os.environ["EV"], os.environ["REPO"]
roots = {}
for line in open(os.path.join(EV, "probe.txt")):
    m = re.match(r"(omnetpp|inet|simu5g)_root: (\S+)$", line.strip())
    if m:
        roots[m.group(1)] = m.group(2)
assert set(roots) == {"omnetpp", "inet", "simu5g"}, "project roots not found"
# Declared build-output classes. A pre-existing (manifest-tracked) file that changed is acceptable only if it
# is in one of these classes; any other modification, and any removal, is an unexpected upstream source edit.
GEN = re.compile(r"(^|/)(Makefile|Makefile\.inc|features\.h|config\.(status|log)|\.oppfeaturestate|\.nedexclusions)$"
                 r"|_m\.(cc|h)$|\.(o|so|a|d|pyc)$|(^|/)(out|lib|bin|__pycache__)/")
def sha1(p):
    h = hashlib.sha1()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()
unexpected = 0
rows = ["project\tchange\tpath\tclass"]
summary = []
for proj, root in sorted(roots.items()):
    post = {}
    for line in open(os.path.join(root, ".opp_env", "postdownload.sha")):
        h, p = line.rstrip("\n").split(maxsplit=1)
        post[p] = h
    modified, removed = [], []
    for p, h in post.items():
        fp = os.path.join(root, p)
        if not os.path.isfile(fp):
            removed.append(p)
        elif sha1(fp) != h:
            modified.append(p)
    added = []
    for d, dirs, files in os.walk(root):
        rel_d = os.path.relpath(d, root)
        if rel_d.split(os.sep)[0] in ("ide", ".opp_env"):
            continue
        for f in files:
            rp = "./" + os.path.normpath(os.path.join(rel_d, f))
            if rp not in post:
                added.append(rp)
    for p in sorted(modified):
        cls = "build-generated" if GEN.search(p) else "UNEXPECTED"
        unexpected += cls == "UNEXPECTED"
        rows.append(f"{proj}\tmodified\t{p}\t{cls}")
    for p in sorted(removed):
        unexpected += 1
        rows.append(f"{proj}\tremoved\t{p}\tUNEXPECTED")
    cats = {"out/": 0, "lib/": 0, "bin/": 0, "generated-pattern": 0, "other": 0}
    for p in added:
        c = ("out/" if "/out/" in p or p.startswith("./out/") else "lib/" if p.startswith("./lib/")
             else "bin/" if p.startswith("./bin/") else "generated-pattern" if GEN.search(p) else "other")
        cats[c] += 1
        if c == "other":
            rows.append(f"{proj}\tadded\t{p}\tbuild-output (other location)")
    summary.append(f"{proj} manifest_entries: {len(post)}")
    summary.append(f"{proj} modified: {len(modified)} removed: {len(removed)} added: {len(added)} added_by_class: {cats}")
# nascTime: the build must not modify tracked files; build outputs are gitignored.
st = subprocess.run(["git", "-C", repo, "status", "--porcelain=v1", "--untracked-files=all"], capture_output=True, text=True, check=True).stdout.splitlines()
tracked = [l for l in st if not l.startswith("??")]
untracked = [l[3:] for l in st if l.startswith("??")]
ignored = subprocess.run(["git", "-C", repo, "status", "--porcelain=v1", "--ignored=matching", "--untracked-files=all", "--", "src/nasctime/m2"],
                         capture_output=True, text=True, check=True).stdout.splitlines()
for l in tracked:
    rows.append(f"nascTime\ttracked-change\t{l[3:]}\tUNEXPECTED")
for p in untracked:
    rows.append(f"nascTime\tuntracked-not-ignored\t{p}\treported")
summary.append(f"nascTime tracked_changes: {len(tracked)} untracked_not_ignored: {len(untracked)} "
               f"ignored_build_outputs_in_m2: {sum(1 for l in ignored if l.startswith('!!'))}")
summary.append(f"unexpected_upstream_source_changes: {unexpected}")
summary.append(f"nascTime_tracked_source_changes: {len(tracked)}")
open(os.path.join(EV, "source-changes.tsv"), "w").write("\n".join(rows) + "\n")
open(os.path.join(EV, "source-changes-summary.txt"), "w").write("\n".join(summary) + "\n")
print("\n".join(summary))
assert unexpected == 0, "unexpected upstream source changes"
assert not tracked, "tracked nascTime files changed by the build"
