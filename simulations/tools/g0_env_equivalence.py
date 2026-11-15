#!/usr/bin/env python3
"""G0 environment-equivalence comparison (decision D-2, 2026-11-15): records produced on a second environment
(OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, the reviewer's VirtualBox VM) against the committed records of the
accepted environment (OMNeT++ 6.4.0, same INET / Simu5G), for the accepted M2-R181 validation and the S7.2a
Checkpoint 1 / Checkpoint 2 cases. Read-only on both sides; nothing is interpreted beyond the rules below.

    g0_env_equivalence.py compare --ref <simulations/results/simu5g-1.8.1> [--m1 <V1 root>] [--m1x <dir>]
                                  [--m2 <V2 root>] [--cp1 <V3a root>] [--cp2 <CP2 file or batch root>]   -> stdout
    g0_env_equivalence.py selftest --ref <simulations/results/simu5g-1.8.1>

Roots are the NASCTIME_RESULTS_ROOT values used on the VM (checklist §4 of the acceptance record):
  --m1   V1: <root>/m1/S4/{transport,clock}-check.txt, <root>/m1/S5/check.txt, raw-outputs-all.sha256
  --m1x  directory with the V1 checker outputs under these names: v181-s5.txt, v181-s5-mutation.txt, s5e.txt,
         s5e-mutation.txt, s5i.txt, s5i-mutation.txt (copies of the files the checklist wrote; unrenamed originals
         are not required to have these names)
  --m2   V2 (run_r181c.sh root): <root>/m2/M2-S{0,1,4,5,6}/...
  --cp1  V3a: <root>/m2/M2-S7.2a-cp1r2/{f0-check,t0-check,comparator-canaries}.txt, raw-outputs.sha256
  --cp2  V3b: either the file <root>/m2/M2-S7.2a-cp2r2/cp2r2-check.txt (m2s72.sh r2), or a directory holding the
         batch evaluations (*/cp2r2-batch-eval*.txt, r181b/run_cp2_batch.sh) and optionally cp2r2-assembled.txt

Rules (the G0 record defines them; this tool only measures):
  G0-V  verdict identity, REQUIRED: every compared record has the same verdict words (PASS / FAIL, and OPEN /
        CLOSED for dependency gates, IDENTICAL / DIFFERENT for the configuration identity checks of regen.txt) on
        aligned lines, the same PASS / FAIL totals, no verdict-bearing line added
        or removed; for CP2, the same multiset of (family, key, verdict) rows and the same control verdicts.
  G0-N  numeric and textual differences, LISTED: matched lines with changed numbers and unmatched lines without
        a verdict word are counted per record and printed in full in the appendix; each needs an attribution in
        the G0 record (for example a timestamp, a path, a run time); none is a failure by itself.
  G0-H  raw-output hash identity, INFORMATIONAL (D-2: no return to OMNeT++ 6.4.0 for hash matching): per hash
        list, per file class, identical / different / only on one side.
"""
import argparse
import collections
import glob
import hashlib
import os
import re
import shutil
import sys
import tempfile

sys.dont_write_bytecode = True   # leaves no __pycache__ in simulations/tools (not ignored there; worktrees stay clean)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import diff_records as DR  # noqa: E402  (unchanged accepted tool: alignment and verdict / number diff)

GATE = re.compile(r"\b(OPEN|CLOSED|IDENTICAL|DIFFERENT)\b")   # gate words; identity-check words (regen.txt)

# (group, reference path under --ref, VM root option, VM path under that root, expectation from the acceptance)
M2S = "out-r181c-m2/m2"
RECORDS = [
    ("M1-S4", "out/m1/S4/transport-check.txt", "m1", "m1/S4/transport-check.txt", "PASS"),
    ("M1-S4", "out/m1/S4/clock-check.txt", "m1", "m1/S4/clock-check.txt", "PASS"),
    ("M1-S5", "out/m1/S5/check.txt", "m1", "m1/S5/check.txt", "historical FAIL (W-identity, R-ingress, R-egress)"),
    ("M1-S5", "out/m1/v181-s5-check.txt", "m1x", "v181-s5.txt", "W-identity-v PASS, R-egress-v FAIL"),
    ("M1-S5", "out/m1/v181-s5-mutation-check.txt", "m1x", "v181-s5-mutation.txt", "mutation FAIL"),
    ("M1-S5", "r181b/m1-on-1.8.1/v181b-s5e-check.txt", "m1x", "s5e.txt", "PASS 1073/1073"),
    ("M1-S5", "r181b/m1-on-1.8.1/v181b-s5e-mutation-check.txt", "m1x", "s5e-mutation.txt", "mutation FAIL"),
    ("M1-S5", "r181b/m1-on-1.8.1/v181b-s5i-check.txt", "m1x", "s5i.txt", "PASS"),
    ("M1-S5", "r181b/m1-on-1.8.1/v181b-s5i-mutation-check.txt", "m1x", "s5i-mutation.txt", "mutation FAIL"),
    ("M2-S0", f"{M2S}/M2-S0/check.txt", "m2", "m2/M2-S0/check.txt", "historical FAIL 20/21 (A7)"),
    ("M2-S0", f"{M2S}/M2-S0/census.txt", "m2", "m2/M2-S0/census.txt", "as committed"),
    ("M2-S1", f"{M2S}/M2-S1/check.txt", "m2", "m2/M2-S1/check.txt", "historical FAIL 27/28 (C10)"),
    ("M2-S1", f"{M2S}/M2-S1/census.txt", "m2", "m2/M2-S1/census.txt", "as committed"),
    ("M2-S4", f"{M2S}/M2-S4/check.txt", "m2", "m2/M2-S4/check.txt", "historical FAIL 54/55 (R2b)"),
    ("M2-S4", f"{M2S}/M2-S4/r2b-v-check.txt", "m2", "m2/M2-S4/r2b-v-check.txt", "R2b-v PASS"),
    ("M2-S4", f"{M2S}/M2-S4/r2b-v-mutation-check.txt", "m2", "m2/M2-S4/r2b-v-mutation-check.txt", "mutation FAIL"),
    ("M2-S4", f"{M2S}/M2-S4/DEPENDENCY-GATE.txt", "m2", "m2/M2-S4/DEPENDENCY-GATE.txt", "OPEN"),
    ("M2-S5", f"{M2S}/M2-S5/check.txt", "m2", "m2/M2-S5/check.txt", "historical FAIL 66/71"),
    ("M2-S5", f"{M2S}/M2-S5/check-v181c.txt", "m2", "m2/M2-S5/check-v181c.txt", "69/71 (N-tseSlot, N-noFcsNw)"),
    ("M2-S5", f"{M2S}/M2-S5/c8demo-v181c.txt", "m2", "m2/M2-S5/c8demo-v181c.txt", "PASS"),
    ("M2-S5", f"{M2S}/M2-S5/controls-v181c.txt", "m2", "m2/M2-S5/controls-v181c.txt", "PASS"),
    ("M2-S5", f"{M2S}/M2-S5/DEPENDENCY-GATE.txt", "m2", "m2/M2-S5/DEPENDENCY-GATE.txt", "OPEN"),
    ("M2-S6", f"{M2S}/M2-S6/check.txt", "m2", "m2/M2-S6/check.txt", "PASS 1863/1863"),
    ("M2-S6", f"{M2S}/M2-S6/gate-D0.txt", "m2", "m2/M2-S6/gate-D0.txt", "8/8"),
    ("M2-S6", f"{M2S}/M2-S6/gate-E0b.txt", "m2", "m2/M2-S6/gate-E0b.txt", "3/3"),
    ("M2-S6", f"{M2S}/M2-S6/report.txt", "m2", "m2/M2-S6/report.txt", "as committed"),
    ("CP1", "out-s72/m2/M2-S7.2a-cp1r2/regen.txt", "cp1", "m2/M2-S7.2a-cp1r2/regen.txt",
     "6.4.0: flattening IDENTICAL x9, verify rc 0; on 6.5.0 predicted DIFFERENT x9, verify rc 1 (G0-R1)"),
    ("CP1", "out-s72/m2/M2-S7.2a-cp1r2/f0-check.txt", "cp1", "m2/M2-S7.2a-cp1r2/f0-check.txt", "F0 PASS, controls 6/6"),
    ("CP1", "out-s72/m2/M2-S7.2a-cp1r2/comparator-canaries.txt", "cp1", "m2/M2-S7.2a-cp1r2/comparator-canaries.txt",
     "as committed"),
    ("CP1", "out-s72/m2/M2-S7.2a-cp1r2/t0-check.txt", "cp1", "m2/M2-S7.2a-cp1r2/t0-check.txt",
     "5 PASS / 5 FAIL (T0-R vs 1.8.0 hashes)"),
]
HASHES = [
    ("M1-S4", "out/m1/S4/raw-outputs-all.sha256", "m1", "m1/S4/raw-outputs-all.sha256"),
    ("M1-S5", "out/m1/S5/raw-outputs-all.sha256", "m1", "m1/S5/raw-outputs-all.sha256"),
] + [(f"M2-{s}", f"{M2S}/M2-{s}/{h}", "m2", f"m2/M2-{s}/{h}")
     for s in ("S0", "S1", "S4", "S5", "S6") for h in ("raw-outputs.sha256", "r181c-files.sha256")] + [
    ("M2-S5", f"{M2S}/M2-S5-r181c/r181c-files.sha256", "m2", "m2/M2-S5-r181c/r181c-files.sha256"),
    ("CP1", "out-s72/m2/M2-S7.2a-cp1r2/raw-outputs.sha256", "cp1", "m2/M2-S7.2a-cp1r2/raw-outputs.sha256"),
]
CP2_REF = "out-r181b-cp2/m2"
G0R1_EFF = "g0r1/verify-eff.txt"   # under --cp1: m2s72_verify_eff.py check output on the same VM (procedure §4)
FLAT = re.compile(r"^(\S+): generator (\d+) entries, OMNeT\+\+ runconfig (\d+) entries: (IDENTICAL|DIFFERENT)")
EFF = re.compile(r"^(\S+): effective entries generator (\d+), OMNeT\+\+ (\d+): IDENTICAL .*runconfig form: first per key")


def g0r1(ref, vm, eff):
    """G0-R1 attribution test for regen.txt (OMNeT++ 6.5.0 runconfig prints the effective entry per key only):
    holds only if (a) every differing line of the two files is a flattening line IDENTICAL -> DIFFERENT, its
    'first difference' detail line, or 'verify rc 0' -> 'verify rc 1'; (b) each DIFFERENT line keeps the reference
    generator count and its runconfig count equals the effective count of the VM's m2s72_verify_eff.py check output;
    (c) that output reports all IDENTICAL in the first-per-key form for the same nine configurations"""
    if not os.path.exists(eff):
        return False, f"{G0R1_EFF} not provided"
    a = open(ref, errors="replace").read().split("\n")
    b = open(vm, errors="replace").read().split("\n")
    effn = {m.group(1): int(m.group(3)) for m in map(EFF.match, open(eff, errors="replace")) if m}
    if "effective-entry check: all IDENTICAL" not in open(eff, errors="replace").read():
        return False, "verify-eff does not report all IDENTICAL"
    fa = {m.group(1): m for m in map(FLAT.match, a) if m}
    fb = {m.group(1): m for m in map(FLAT.match, b) if m}
    if set(fa) != set(fb) or set(fb) != set(effn):
        return False, f"configuration sets differ: regen ref {sorted(fa)}, vm {sorted(fb)}, verify-eff {sorted(effn)}"
    for c, m in fb.items():
        r = fa[c]
        if r.group(4) != "IDENTICAL" or m.group(2) != r.group(2):
            return False, f"{c}: reference not IDENTICAL or generator count changed"
        if m.group(4) == "DIFFERENT" and int(m.group(3)) != effn[c]:
            return False, f"{c}: runconfig printed {m.group(3)}, effective entries {effn[c]}"
    rest_a = [x for x in a if not FLAT.match(x) and not x.startswith("   first difference at entry") and x != "verify rc 0"]
    rest_b = [x for x in b if not FLAT.match(x) and not x.startswith("   first difference at entry") and x != "verify rc 1"]
    if rest_a != rest_b:   # regen.txt holds no path, time or run-time text: every other line must be byte-equal
        j = next((i for i, (x, y) in enumerate(zip(rest_a, rest_b)) if x != y), min(len(rest_a), len(rest_b)))
        return False, f"a line other than the flattening lines differs (other-line {j + 1})"
    nd = sum(1 for m in fb.values() if m.group(4) == "DIFFERENT")
    return True, f"G0-R1 holds: {nd} flattening lines DIFFERENT, each runconfig count = its effective count; verify-eff all IDENTICAL"


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as fh:
        for b in iter(lambda: fh.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def totals(lines):
    c = collections.Counter(v for l in lines for v in DR.VERD.findall(l))
    return c["PASS"], c["FAIL"]


def compare_record(ref, vm, rel):
    """-> dict: status, verdict identity, counts, appendix lines"""
    if not os.path.exists(ref):
        return dict(status="NO REFERENCE", ok=None, detail=f"{ref} missing", app=[])
    if not os.path.exists(vm):
        return dict(status="NOT PROVIDED", ok=None, detail="", app=[])
    if sha(ref) == sha(vm):
        a = open(ref, errors="replace").read().split("\n")
        return dict(status="BYTE-IDENTICAL", ok=True, detail="PASS %d / FAIL %d" % totals(a), app=[], n=0, u=0)
    lines, vchg, nchg = DR.diff_file(ref, vm, rel)
    a = open(ref, errors="replace").read().split("\n")
    b = open(vm, errors="replace").read().split("\n")
    ta, tb = totals(a), totals(b)
    ga = [w for l in a for w in GATE.findall(l)]
    gb = [w for l in b for w in GATE.findall(l)]
    unmatched = sum(1 for l in lines if l.startswith("- removed line") or l.startswith("- added line"))
    ok = vchg == 0 and ta == tb and ga == gb
    why = []
    if vchg:
        why.append(f"{vchg} verdict-bearing lines changed, added or removed")
    if ta != tb:
        why.append(f"totals PASS/FAIL {ta} -> {tb}")
    if ga != gb:
        why.append(f"gate / identity words {collections.Counter(ga)} -> {collections.Counter(gb)}")
    st = "VERDICT-IDENTICAL" if ok else "VERDICT-DIFFERENT"
    det = f"PASS {tb[0]} / FAIL {tb[1]}" + (f"; gate / identity words {dict(collections.Counter(gb))}" if gb else "")
    det += f"; {nchg} matched lines with changed numbers; {unmatched} unmatched lines"
    if why:
        det += "; " + "; ".join(why)
    return dict(status=st, ok=ok, detail=det, app=lines, n=nchg, u=unmatched)


def read_hashes(p):
    out = {}
    for line in open(p, errors="replace"):
        parts = line.rstrip("\n").split(None, 1)
        if len(parts) != 2 or not re.fullmatch(r"[0-9a-f]{64}", parts[0]):
            continue
        q = parts[1].lstrip("*")
        q = q[2:] if q.startswith("./") else q
        q = q[5:] if q.startswith("runs/") else q
        out[q] = parts[0]
    return out


def fclass(p):
    b = os.path.basename(p)
    b = b[:-3] if b.endswith(".gz") else b
    return os.path.splitext(b)[1].lstrip(".") or "(none)"


def compare_hashes(ref, vm):
    if not os.path.exists(ref):
        return None, "NO REFERENCE"
    if not os.path.exists(vm):
        return None, "NOT PROVIDED"
    a, b = read_hashes(ref), read_hashes(vm)
    per = collections.defaultdict(collections.Counter)
    for p in set(a) | set(b):
        c = fclass(p)
        if p not in b:
            per[c]["only ref"] += 1
        elif p not in a:
            per[c]["only vm"] += 1
        else:
            per[c]["identical" if a[p] == b[p] else "different"] += 1
    return per, "COMPARED"


def cp2_rows(path):
    """(family, key, verdict) multiset, control verdicts and the verdict line, from a check file or a directory of
    batch evaluations; rows are split exactly as cp2r2_batch_eval.assemble splits them (' | ', verdict in field 3)"""
    files = [path] if os.path.isfile(path) else sorted(glob.glob(os.path.join(path, "*", "cp2r2-batch-eval*.txt")))
    rows, ctl, verdict = collections.Counter(), {}, None
    for f in files:
        for line in open(f, errors="replace"):
            if line[:1].isspace():          # control detail lines (mutated rows) and indented assembled controls
                continue
            p = line.rstrip("\n").split(" | ")
            if p[0] == "CONTROL" and len(p) >= 4:                       # batch evaluation: CONTROL | name | v | ...
                ctl[p[1]] = p[2]
            elif p[0] in ("PASS", "FAIL") and len(p) >= 3 and p[1] in ("Stage 4", "I-2H"):
                ctl[f"{p[1]}: {p[2]}"] = p[0]                             # check_m2s72_cp2r2.py: v | block | name | ...
            elif len(p) >= 4 and p[2] in ("PASS", "FAIL"):
                rows[(p[0], p[1], p[2])] += 1
    asm = path if os.path.isfile(path) else os.path.join(path, "cp2r2-assembled.txt")
    if os.path.exists(asm):
        for line in open(asm, errors="replace"):
            if "verdict" in line and DR.VERD.search(line):
                verdict = DR.VERD.findall(line)[-1]
    return rows, ctl, verdict, files


def compare_cp2(refdir, vm):
    if not vm or not os.path.exists(vm):
        return dict(status="NOT PROVIDED", ok=None, detail="", app=[])
    ra, ca, va, fa = cp2_rows(refdir)
    rb, cb, vb, fb = cp2_rows(vm)
    if not rb:
        return dict(status="NO ROWS", ok=False, detail=f"no rows in {fb}", app=[])
    fam = lambda r: collections.Counter((f, v) for (f, _, v), n in r.items() for _ in range(n))  # noqa: E731
    app = []
    for k in sorted(set(ra) | set(rb)):
        if ra[k] != rb[k]:
            app.append(f"- row {k}: reference {ra[k]}, vm {rb[k]}")
    for k in sorted(set(ca) | set(cb)):
        if ca.get(k) != cb.get(k):
            app.append(f"- control {k}: reference {ca.get(k)}, vm {cb.get(k)}")
    ok = ra == rb and (not cb or ca == cb) and (vb is None or vb == va)
    fa_, fb_ = fam(ra), fam(rb)
    gate = lambda c: sum(n for (f, v), n in c.items() if v == "PASS" and "(info)" not in f and "(diagnostic)" not in f)  # noqa: E731
    det = (f"rows {sum(rb.values())} (reference {sum(ra.values())}); PASS rows outside information families "
           f"{gate(fb_)} (reference {gate(fa_)}); controls {sum(1 for v in cb.values() if v == 'PASS')}/{len(cb)} "
           f"(reference {sum(1 for v in ca.values() if v == 'PASS')}/{len(ca)}); verdict {vb} (reference {va}); "
           f"{len(app)} differing row / control keys")
    if not cb:
        det += "; controls not compared (no assembled file with control lines)"
    return dict(status="VERDICT-IDENTICAL" if ok else "VERDICT-DIFFERENT", ok=ok, detail=det, app=app)


def compare(ref, roots, cp2):
    out, app = [], []
    nok = nbad = nmiss = nattr = 0
    out.append("# G0 environment-equivalence comparison\n")
    out.append(f"reference: {ref}")
    for k, v in roots.items():
        out.append(f"vm {k}: {v or '(not given)'}")
    out.append(f"vm cp2: {cp2 or '(not given)'}\n")
    out.append("## G0-V verdict identity (required) and G0-N differences (listed)\n")
    out.append("| Group | Record | Expected (acceptance) | Status | Detail |")
    out.append("|---|---|---|---|---|")
    for grp, rrel, opt, vrel, exp in RECORDS:
        if not roots.get(opt):
            r = dict(status="NOT PROVIDED", ok=None, detail=f"--{opt} not given", app=[])
        else:
            r = compare_record(os.path.join(ref, rrel), os.path.join(roots[opt], vrel), rrel)
        if r["ok"] is False and rrel.endswith("M2-S7.2a-cp1r2/regen.txt"):
            held, why = g0r1(os.path.join(ref, rrel), os.path.join(roots[opt], vrel), os.path.join(roots[opt], G0R1_EFF))
            r["detail"] += f"; attribution: {why}"
            if held:
                r["status"], r["ok"] = "VERDICT-DIFFERENT, ATTRIBUTED G0-R1", "attr"
        nok += r["ok"] is True
        nattr += r["ok"] == "attr"
        nbad += r["ok"] is False
        nmiss += r["ok"] is None
        out.append(f"| {grp} | `{os.path.basename(vrel)}` | {exp} | {r['status']} | {r['detail']} |")
        if r["app"]:
            app += [f"### {grp} {rrel}", ""] + r["app"] + [""]
    r = compare_cp2(os.path.join(ref, CP2_REF), cp2)
    nok += r["ok"] is True
    nbad += r["ok"] is False
    nmiss += r["ok"] is None
    out.append(f"| CP2 | rows, controls, verdict | 2391 gate rows PASS / 0 FAIL, controls 13/13, I-2H PASS | "
               f"{r['status']} | {r['detail']} |")
    if r["app"]:
        app += ["### CP2", ""] + r["app"] + [""]
    out.append("\n## G0-H raw-output hash identity (informational)\n")
    out.append("| Group | Hash list | Status | Per class: identical / different / only ref / only vm |")
    out.append("|---|---|---|---|")
    for grp, rrel, opt, vrel in HASHES:
        if not roots.get(opt):
            out.append(f"| {grp} | `{rrel}` | NOT PROVIDED | |")
            continue
        per, st = compare_hashes(os.path.join(ref, rrel), os.path.join(roots[opt], vrel))
        cells = "" if per is None else "; ".join(
            f"{c}: {n['identical']}/{n['different']}/{n['only ref']}/{n['only vm']}" for c, n in sorted(per.items()))
        out.append(f"| {grp} | `{rrel}` | {st} | {cells} |")
    verdict = ("DOES NOT HOLD" if nbad else f"INCOMPLETE ({nmiss} records not provided)" if nmiss else
               "HOLDS" if nattr == 0 else f"HOLDS EXCEPT {nattr} ATTRIBUTED DIFFERENCE(S) (G0-R1; historical verdict kept)")
    out.append(f"\nG0-V summary: {nok} verdict-identical, {nattr} verdict-different and attributed (G0-R1), "
               f"{nbad} verdict-different, {nmiss} not provided")
    out.append(f"G0-V verdict identity: {verdict}")
    out.append("\n## Appendix: every difference (G0-N attribution input)\n")
    out += app or ["(none)"]
    return "\n".join(out), nbad, nmiss


def selftest(ref):
    """the reference against itself must hold with every record byte-identical; a one-word verdict flip, a changed
    number, a gate word and a CP2 row flip must each be detected; the G0-R1 attribution must hold on the 6.5.0 form
    and fail on any other change; the two CP2 formats must parse alike (canaries on a temporary copy, each restored)"""
    d = tempfile.mkdtemp()
    res = []
    try:
        vm = {k: os.path.join(d, k) for k in ("m1", "m1x", "m2", "cp1")}
        for grp, rrel, opt, vrel, _ in RECORDS:
            src = os.path.join(ref, rrel)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(os.path.join(vm[opt], vrel)), exist_ok=True)
                shutil.copy(src, os.path.join(vm[opt], vrel))
        for grp, rrel, opt, vrel in HASHES:
            src = os.path.join(ref, rrel)
            if os.path.exists(src):
                os.makedirs(os.path.dirname(os.path.join(vm[opt], vrel)), exist_ok=True)
                shutil.copy(src, os.path.join(vm[opt], vrel))
        cp2 = os.path.join(d, "cp2")
        shutil.copytree(os.path.join(ref, CP2_REF), cp2)
        txt, bad, miss = compare(ref, vm, cp2)
        res.append(("identity: reference vs itself holds, all byte-identical",
                    bad == 0 and miss == 0 and "VERDICT-DIFFERENT" not in txt and txt.count("BYTE-IDENTICAL") == len(RECORDS)))

        def canary(path, old, new, count=1):
            s = open(path).read()
            assert old in s, (path, old)
            open(path, "w").write(s.replace(old, new, count))

        p = os.path.join(vm["m2"], "m2/M2-S6/check.txt")
        keep = open(p).read()
        canary(p, "PASS", "FAIL")
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("canary: one PASS -> FAIL in M2-S6 check.txt is VERDICT-DIFFERENT", bad == 1))
        open(p, "w").write(keep)
        p = os.path.join(vm["m2"], "m2/M2-S4/DEPENDENCY-GATE.txt")
        keep = open(p).read()
        canary(p, "OPEN", "CLOSED")
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("canary: gate OPEN -> CLOSED is VERDICT-DIFFERENT", bad == 1))
        open(p, "w").write(keep)
        p = os.path.join(vm["m1"], "m1/S4/clock-check.txt")
        keep = open(p).read()
        s = keep
        m = re.search(r"(?<![\d.])(\d{2,})(?![\d.])", s)
        open(p, "w").write(s[:m.start()] + str(int(m.group(1)) + 1) + s[m.end():])
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("canary: one changed number is listed (G0-N) without a verdict change",
                    bad == 0 and "1 matched lines with changed numbers" in txt))
        open(p, "w").write(keep)
        p = sorted(glob.glob(os.path.join(cp2, "*", "cp2r2-batch-eval*.txt")))[0]
        keep = open(p).read()
        canary(p, " pair (0,1) | PASS | ", " pair (0,1) | FAIL | ")
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("canary: one CP2 row PASS -> FAIL is VERDICT-DIFFERENT", bad == 1))
        open(p, "w").write(keep)
        # G0-R1: a 6.5.0-form regen.txt (the nine flattening lines as first-per-key counts, verify rc 1) is attributed
        # only with a matching verify-eff output, and not if any other line or count differs
        rg = os.path.join(vm["cp1"], "m2/M2-S7.2a-cp1r2/regen.txt")
        keep = open(rg).read()
        effc = {"M2S71-q0-idle": 162, "M2S71-qdu-idle": 165, "M2S71-q0-load": 174, "M2S6-C-a": 167, "M2S6-E-all": 178,
                "M2S71-q0-Ca": 172, "M2S71-qdu-Ca": 175, "M2S71-q0-Ca-sus": 184, "M2S71-qdu-Ca-sus": 187}
        lines = []
        for l in keep.split("\n"):
            m = FLAT.match(l)
            lines.append(f"{m.group(1)}: generator {m.group(2)} entries, OMNeT++ runconfig {effc[m.group(1)]} entries: DIFFERENT"
                         if m else ("verify rc 1" if l == "verify rc 0" else l))
        open(rg, "w").write("\n".join(lines))
        os.makedirs(os.path.join(vm["cp1"], "g0r1"))
        open(os.path.join(vm["cp1"], G0R1_EFF), "w").write("".join(
            f"{c}: effective entries generator {n}, OMNeT++ {n}: IDENTICAL (keys, values, order); runconfig form: first per key\n"
            for c, n in effc.items()) + "effective-entry check: all IDENTICAL\n")
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("G0-R1: 6.5.0-form regen.txt with matching verify-eff is ATTRIBUTED, not counted as different",
                    bad == 0 and "ATTRIBUTED G0-R1" in txt))
        open(rg, "w").write("\n".join(lines).replace("check rc 0", "check rc 1", 1))
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("G0-R1 canary: one other changed line defeats the attribution", bad == 1))
        open(rg, "w").write("\n".join(lines).replace("runconfig 162 entries", "runconfig 161 entries", 1))
        txt, bad, _ = compare(ref, vm, cp2)
        res.append(("G0-R1 canary: a runconfig count other than the effective count defeats the attribution", bad == 1))
        open(rg, "w").write(keep)
        os.remove(os.path.join(vm["cp1"], G0R1_EFF))
        # format: the single-file check_m2s72_cp2r2.py output (m2s72.sh r2; here the committed 1.8.0 record, read
        # only) parses to the same row keys and control names as the assembled batch reference
        one = os.path.join(ref, "..", "..", "m2", "results", "M2-S7.2a-cp2r2", "cp2r2-check.txt")
        ra, ca, _, _ = cp2_rows(os.path.join(ref, CP2_REF))
        rb, cb, vb, _ = cp2_rows(one)
        res.append(("format: single-file r2 check and batch evaluations give the same row keys (2411) and controls (13)",
                    {k[:2] for k in ra} == {k[:2] for k in rb} and sum(rb.values()) == 2411 and set(ca) == set(cb)
                    and len(cb) == 13 and vb == "PASS"))
    finally:
        shutil.rmtree(d)
    for nm, ok in res:
        print(f"{'PASS' if ok else 'FAIL'} | {nm}")
    print(f"G0 tool selftest: {sum(ok for _, ok in res)} / {len(res)} PASS")
    return 0 if all(ok for _, ok in res) else 1


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("cmd", choices=["compare", "selftest"])
    ap.add_argument("--ref", required=True)
    for k in ("m1", "m1x", "m2", "cp1", "cp2"):
        ap.add_argument(f"--{k}")
    a = ap.parse_args()
    if a.cmd == "selftest":
        return selftest(a.ref)
    txt, bad, miss = compare(a.ref, {"m1": a.m1, "m1x": a.m1x, "m2": a.m2, "cp1": a.cp1}, a.cp2)
    print(txt)
    return 1 if bad else (3 if miss else 0)


if __name__ == "__main__":
    sys.exit(main())
