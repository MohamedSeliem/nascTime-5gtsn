#!/usr/bin/env python3
"""M2-R181b batch evaluation of Checkpoint 2 revision 2 (plan §4.4), with the UNCHANGED row functions of
check_m2s72_cp2r2.py / check_m2s72_b.py / check_m2s72_i2h.py.

    cp2r2_batch_eval.py eval <batch dir> [<ref-only config> ...]  -> stdout: the rows of the configurations present in
                                                       <batch dir>/runs; a ref-only configuration is evaluated as the N = 1
                                                       reference only, its rows are not printed (evaluated in the other batch)
    cp2r2_batch_eval.py assemble <eval> <eval> ...      -> stdout: the combined record and the verdict

eval: the loops of check_m2s72_cp2r2.main(), unchanged in order and arguments, restricted to the configurations present
(the original main() stops with an exception on a missing control configuration):
  Block B (N = 1 reference of the same option / clock / seed evaluated first, as in main()), EOR per run, I-4 stream for
  an option only when both B-<opt>-Eall-n2 and -n4 are present, Block H16 (needs B-<opt>-Ca-n1), Stage 4 controls only
  when M2S72-B-q0-Eall-n4, -n2, BN-rng and BN-theta1 are present, I-2H controls only when M2S72-H16-q0-Ca-n2 and the
  H16N configurations are present. Every row is printed as "family | key | verdict | detail" (the original format),
  and each control as "CONTROL | name | PASS/FAIL | failed ..., predicted ...".
assemble: every expected per-run key of the complete matrix (r2_configs of m2s72.sh, seeds 0-4) must appear in exactly
one of the evaluations; all 13 controls must appear exactly once; then the verdict rule of check_m2s72_cp2r2.py:
PASS iff no gate row FAILs (information rows excluded) and every control PASSes.
"""
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
CHK = os.path.join(HERE, "../../../m2/check")
sys.path.insert(0, CHK)


def evaluate(out, ref_only=()):
    argv = sys.argv
    sys.argv = [argv[0], out]
    import check_m2s72_cp2r2 as C  # noqa: E402  (imports B, I, R exactly as the checker does)
    sys.argv = argv
    B, I = C.B, C.I
    runs = os.path.join(out, "runs")
    have = lambda c: os.path.isdir(os.path.join(runs, c))
    refs = {}
    for opt in B.OPTS:
        for clk in B.CLKS:
            for n in (1,) + B.NS_B:
                cfg = f"M2S72-B-{opt}-{clk}-n{n}"
                if not have(cfg):
                    continue
                for rep in B.REPS:
                    n0 = len(B.rows)
                    ref = refs.get((opt, clk, rep))
                    if n > 1 and ref is None:
                        B.add("RUN", f"{cfg}-{rep}", False, "N = 1 reference missing in this batch")
                        continue
                    ev, stats, _ = B.evaluate(runs, cfg, rep, ref=ref if n > 1 else None)
                    C.eor_rows(ev)
                    if n == 1:
                        refs[(opt, clk, rep)] = ev
                    if cfg in ref_only:
                        del B.rows[n0:]
    for opt in B.OPTS:
        if have(f"M2S72-B-{opt}-Eall-n2") and have(f"M2S72-B-{opt}-Eall-n4"):
            for rep in B.REPS:
                B.i4_stream(runs, opt, rep)
    for o, ns in (("q0", (2, 4)), ("qdu", (2,))):
        for n in ns:
            cfg = f"M2S72-H16-{o}-Ca-n{n}"
            if not have(cfg) or cfg in ref_only:   # ref-only: present for the controls, rows evaluated in another batch
                continue
            for rep in B.REPS:
                ev, stats, cov, st, fails, info = I.evaluate_h(runs, cfg, rep, refs[(o, "Ca", rep)], f"M2S72-H-{o}-Ca-n{n}")
                C.eor_rows(ev)
                if cfg == I.BASE and rep == 0:
                    c01 = cov[(0, 1)]
                    ok = st[1]["hold"] > 0 and st[1]["release"] > 0 and c01["dres"] > 0 and c01["nz"] > 0
                    B.add("H-nv", f"{cfg}-{rep}", ok, f"DS-TT 1 holds {st[1]['hold']}, releases {st[1]['release']}; pair (0,1) Res_0 != Res_1 on "
                          f"{c01['dres']} common Follow_Ups, non-zero GM-drift pair contributions {c01['nz']}")
    ctl = []
    if all(have(c) for c in ("M2S72-B-q0-Eall-n4", "M2S72-B-q0-Eall-n2", "M2S72-BN-rng", "M2S72-BN-theta1")):
        for name, ok, fails, exp, mine in B.stage4_controls(runs):
            ctl.append(("Stage 4", name, ok, sorted(fails), sorted(exp)))
    if all(have(c) for c in ("M2S72-H16-q0-Ca-n2", "M2S72-H16N-nohold", "M2S72-H16N-hto")):
        ci, _ = I.controls(runs)
        for name, ok, fails, exp, info, mine in ci:
            ctl.append(("I-2H", name, ok, sorted(fails), sorted(exp)))
    print(f"M2-R181b CP2 r2 batch evaluation of {out}")
    for r in B.rows:
        print(" | ".join(r))
    for kind, name, ok, fails, exp in ctl:
        print(f"CONTROL | {kind}: {name} | {'PASS' if ok else 'FAIL'} | failed {fails}, predicted {exp}")
    print("INFO families: " + ", ".join(I.INFO))


def assemble(*files):
    def parse(f):
        rows, ctl, info = [], [], []
        for line in open(f):
            p = line.rstrip("\n").split(" | ")
            if line.startswith("INFO families: "):
                info = line.strip()[len("INFO families: "):].split(", ")
            elif p[0] == "CONTROL" and len(p) >= 4:
                ctl.append((p[1], p[2]))
            elif len(p) >= 4 and p[2] in ("PASS", "FAIL"):
                rows.append((p[0], p[1], p[2], " | ".join(p[3:])))
        return rows, ctl, info
    parsed = [parse(f) for f in files]
    info = parsed[0][2]
    run_of = lambda key: re.match(r"(M2S72-[\w-]+?-\d)(?:\s|$)", key)
    exp = set()
    for o in ("q0", "qdu"):
        for c in ("ideal", "Ca", "Eall"):
            for n in (1, 2, 4):
                exp |= {f"M2S72-B-{o}-{c}-n{n}-{r}" for r in range(5)}
    exp |= {f"M2S72-H16-q0-Ca-n{n}-{r}" for n in (2, 4) for r in range(5)} | {f"M2S72-H16-qdu-Ca-n2-{r}" for r in range(5)}
    src = {}
    for tag, (rows, _, _) in zip(files, parsed):
        for fam, key, v, det in rows:
            m = run_of(key)
            if m and m.group(1) in exp:
                src.setdefault(m.group(1), set()).add(tag)
    missing = sorted(exp - set(src))
    twice = sorted(k for k, s in src.items() if len(s) > 1)
    rows = [r for p in parsed for r in p[0]]
    ctl = [c for p in parsed for c in p[1]]
    nctl = Counter(n for n, _ in ctl)
    gate = [r for r in rows if r[0] not in info]
    nf = sum(1 for r in gate if r[2] == "FAIL")
    cf = sum(1 for _, v in ctl if v != "PASS")
    print("M2-R181b Checkpoint 2 revision 2 on Simu5G 1.8.1, assembled from {len(files)} batch evaluations")
    print(f"per-run keys expected {len(exp)}, present {len(src)}, missing {len(missing)} {missing[:6]}, in more than one batch {len(twice)} {twice[:6]}")
    by = Counter((r[0], r[2]) for r in rows)
    print("rows per family: " + ", ".join(f"{g} {by[(g, 'PASS')]} PASS / {by[(g, 'FAIL')]} FAIL" for g in sorted({r[0] for r in rows})))
    print(f"gate rows: {len(gate) - nf} PASS, {nf} FAIL (information rows {', '.join(info)} reported, not gated)")
    for r in gate:
        if r[2] == "FAIL":
            print("FAIL row: " + " | ".join(r)[:400])
    print(f"controls: {len(ctl)} evaluated ({len(nctl)} distinct, duplicates {[n for n, k in nctl.items() if k > 1]}), "
          f"{len(ctl) - cf} PASS, {cf} FAIL")
    for n, v in ctl:
        print(f"  {v} | {n}")
    ok = not missing and not twice and nf == 0 and cf == 0 and len(nctl) == 13 and len(ctl) == 13
    print("Checkpoint 2 revision 2 verdict (assembled): " + ("PASS" if ok else "FAIL (stop and report)"))


if __name__ == "__main__":
    if sys.argv[1] == "eval":
        evaluate(sys.argv[2], tuple(sys.argv[3:]))
    elif sys.argv[1] == "assemble":
        assemble(*sys.argv[2:])
