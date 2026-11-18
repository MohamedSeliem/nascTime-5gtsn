import os, re
EV = os.environ["EV"]
roots = {}
for line in open(os.path.join(EV, "probe.txt")):
    m = re.match(r"(omnetpp|inet|simu5g)_root: (\S+)$", line.strip())
    if m:
        roots[m.group(1)] = m.group(2)
assert set(roots) == {"omnetpp", "inet", "simu5g"}, "project roots not found in probe output"

def manifest(root, name):
    d = {}
    for line in open(os.path.join(root, ".opp_env", name + ".sha")):
        h, p = line.rstrip("\n").split(maxsplit=1)
        d[p] = h
    return d

def contains(root, rel, s):
    try:
        return s in open(os.path.join(root, rel), errors="replace").read()
    except OSError:
        return False

# Pattern-based attribution to the pinned opp_env 0.36.2.261110 recipes (database/omnetpp.py, inet.py,
# simu5g.py). This establishes RECIPE CONSISTENCY ONLY: a string-presence check does not prove that a file
# received exactly the recipe's transformation and nothing else.
OMNETPP = {"./src/envir/evmain.cc", "./src/utils/opp_ide", "./Makefile.inc.in", "./configure.user", "./Version"}
def attributable(proj, root, p, kind):
    if proj == "omnetpp":
        return p in OMNETPP
    if proj == "inet":
        if p in ("./.oppfeaturestate", "./.nedexclusions"):
            return True
        if kind == "removed" and p.startswith("./examples/voipstream/osudp/"):
            return True
        return kind == "changed" and contains(root, p, "defined(__linux__)")
    if proj == "simu5g":
        if p == "./Makefile":
            return kind == "changed" and contains(root, p, "-KINET_PROJ=$(INET_ROOT)")
        return kind == "changed" and os.path.basename(p) == "omnetpp.ini" and contains(root, p, "#image-path")
    return False

unexpected = outputs = 0
with open(os.path.join(EV, "adaptations.tsv"), "w") as out:
    out.write("project\tkind\tpath\tattribution\n")
    for proj, root in sorted(roots.items()):
        pre, post = manifest(root, "prepatch"), manifest(root, "postdownload")
        changes = [(p, "changed") for p in post if p in pre and pre[p] != post[p]]
        changes += [(p, "added") for p in post if p not in pre]
        changes += [(p, "removed") for p in pre if p not in post]
        for p, kind in sorted(changes):
            ok = attributable(proj, root, p, kind)
            unexpected += not ok
            out.write(f"{proj}\t{kind}\t{p}\t{'recipe-consistent' if ok else 'UNEXPECTED'}\n")
        for d, dirs, files in os.walk(root):
            rel_d = os.path.relpath(d, root)
            if rel_d.split(os.sep)[0] in ("ide", ".opp_env"):
                continue
            for f in files:
                rp = "./" + os.path.normpath(os.path.join(rel_d, f))
                if re.search(r"\.(o|so|a)$", f) and rp not in post:
                    outputs += 1
                    out.write(f"{proj}\tbuild-output\t{rp}\tFRAMEWORK-BUILD-OUTPUT\n")
with open(os.path.join(EV, "adaptations-summary.txt"), "w") as s:
    s.write("scope: recipe consistency (pattern-based attribution); NOT exact transformation equivalence\n")
    s.write(f"unexpected_adaptations: {unexpected}\nframework_build_outputs_after_download: {outputs}\n")
print(open(os.path.join(EV, "adaptations-summary.txt")).read())
assert unexpected == 0, "change not attributable to the pinned opp_env recipe"
assert outputs == 0, "simulation-framework build outputs found"
