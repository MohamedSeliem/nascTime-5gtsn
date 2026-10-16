#!/usr/bin/env python3
"""M2-S5 hard gate G0 (migration/m2-s5-design.md 7.1): passive transparency of TtPtpPort.

Usage: gate_m2s5.py <M2-S5 runs dir> [<M2-S4 runs dir>]   (also imported by check_m2s5.py)

M2-S4 is the timing baseline. For every M2S4 run (seeds 0-9, frag, load, load-harq16) and
its M2S5-passive counterpart, and for the unit topology (M2S5U-base vs M2S5U-passive, both
M2-S5 runs: TtPdelayPort vs TtPtpPort with the correction off):
  - every .pcapng is byte-identical;
  - every per-frame log (M2-S0/S1 port logs AND the Pdelay engine's .pdelay.csv) is
    byte-identical;
  - every vector data line and every scalar / statistic line of every module present in the
    M2-S4 run is identical, in order -- including the Pdelay engine and its flows (engine,
    tx, rx, whose names are unchanged inside TtPtpPort); only the rows of the two new
    submodules (trafficConditionerLayer.syncIn / .syncOut) are excluded;
  - recorded parameters (par lines) are identical except the explicitly listed differences
    of the compound itself (EXPECTED_PAR_DIFF): its typename and its three new parameters;
  - the final event number is identical.
"""
import os
import re
import sys
from collections import Counter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gate_m2s4 import files, sha, last_events  # noqa: E402

PAIRS = [("M2S4", "M2S5-passive", list(range(10))), ("M2S4-frag", "M2S5-passive-frag", [0]),
         ("M2S4-load", "M2S5-passive-load", [0]), ("M2S4-load-harq16", "M2S5-passive-load-harq16", [0])]
UNIT_PAIR = ("M2S5U-base", "M2S5U-passive", [0])
NEW_MODULES = (".trafficConditionerLayer.syncIn", ".trafficConditionerLayer.syncOut")


def is_new(mod):
    return any(mod.endswith(n) or (n + ".") in mod for n in NEW_MODULES)


def expected_par_diff(network, tts):
    """(only in the M2-S4 run, only in the M2-S5 run): the compound's typename and its new
    parameters. Nothing else may differ."""
    only4, only5 = Counter(), Counter()
    for tt in tts:
        m = f"{network}.{tt}.eth[1].trafficConditionerLayer"
        only4[f'par {m} typename "\\"nasctime.m2.TtPdelayPort\\""'] += 1
        only5[f'par {m} typename "\\"nasctime.m2.TtPtpPort\\""'] += 1
        for p in ("syncIngress", "syncEgress", "syncEgressAudit"):
            only5[f"par {m} {p} false"] += 1
    return only4, only5


def vec_data(path):
    ids, data = {}, {}
    with open(path) as fh:
        for line in fh:
            c = line[:1]
            if c.isdigit():
                tab = line.find("\t")
                k = ids.get(line[:tab])
                if k is not None:
                    data[k].append(line[tab + 1:].rstrip("\n"))
            elif line.startswith("vector "):
                p = line.split(" ", 4)
                if not is_new(p[2]):
                    k = (p[2], p[3])
                    if k in data:
                        raise ValueError(f"duplicate vector {k}")
                    ids[p[1]] = k
                    data[k] = []
    return data


def sca_data(path, resultdir, config):
    out, skip = [], False
    with open(path) as fh:
        for line in fh:
            if line.startswith(("version", "run ", "attr ", "config ", "itervar ")):
                continue
            if line.startswith(("scalar ", "statistic ", "par ")):
                skip = is_new(line.split(" ", 2)[1])
            if not skip:
                line = line.rstrip("\n")
                if line.startswith("par "):
                    line = line.replace(os.path.abspath(resultdir), "<RESULTDIR>").replace(config, "<CONFIG>")
                out.append(line)
    return out


def compare_run(runs4, c4, r4, runs5, c5, r5, network="M1Bridge", tts=("dsTt", "nwTt"), totals=None):
    totals = totals if totals is not None else Counter()
    probs = []
    for kind, sub4, sub5 in (("pcapng", f"pcap/{c4}-{r4}", f"pcap/{c5}-{r5}"), ("logs", f"m2log/{c4}-{r4}", f"m2log/{c5}-{r5}")):
        f4, f5 = files(os.path.join(runs4, c4, sub4)), files(os.path.join(runs5, c5, sub5))
        if not f4:
            probs.append(f"no {kind} in the M2-S4 run")
        if set(f4) != set(f5):
            probs.append(f"{kind} file sets differ: {sorted(set(f4) ^ set(f5))[:3]}")
        for n in sorted(set(f4) & set(f5)):
            totals[kind] += 1
            if sha(f4[n]) != sha(f5[n]):
                probs.append(f"{kind} differs: {n}")
    v4 = vec_data(os.path.join(runs4, c4, c4, f"{r4}.vec"))
    v5 = vec_data(os.path.join(runs5, c5, c5, f"{r5}.vec"))
    if set(v4) != set(v5):
        probs.append(f"vector sets differ: {sorted(set(v4) ^ set(v5))[:3]}")
    for k in set(v4) & set(v5):
        totals["vectors"] += 1
        totals["vector lines"] += len(v4[k])
        if v4[k] != v5[k]:
            probs.append(f"vector differs: {k}")
    s4 = sca_data(os.path.join(runs4, c4, c4, f"{r4}.sca"), os.path.join(runs4, c4), c4)
    s5 = sca_data(os.path.join(runs5, c5, c5, f"{r5}.sca"), os.path.join(runs5, c5), c5)
    totals["scalar lines"] += len(s4)
    n4 = [x for x in s4 if not x.startswith("par ")]
    n5 = [x for x in s5 if not x.startswith("par ")]
    if n4 != n5:
        d = next((i for i, (a, b) in enumerate(zip(n4, n5)) if a != b), min(len(n4), len(n5)))
        probs.append(f"scalars differ at line {d}: {n4[d:d+1]} vs {n5[d:d+1]}")
    p4 = Counter(x for x in s4 if x.startswith("par "))
    p5 = Counter(x for x in s5 if x.startswith("par "))
    e4, e5 = expected_par_diff(network, tts)
    if (p4 - p5) != e4 or (p5 - p4) != e5:
        probs.append(f"recorded parameters differ beyond the listed compound differences: only M2-S4 "
                     f"{sorted((p4 - p5) - e4)[:3]}, only M2-S5 {sorted((p5 - p4) - e5)[:3]}, "
                     f"missing expected {sorted((e4 - (p4 - p5)) + (e5 - (p5 - p4)))[:3]}")
    l4 = last_events(os.path.join(runs4, f"run-{c4}.log"))
    l5 = last_events(os.path.join(runs5, f"run-{c5}.log"))
    reps4 = sorted({int(x[:-4]) for x in os.listdir(os.path.join(runs4, c4, c4)) if x.endswith(".sca")})
    reps5 = sorted({int(x[:-4]) for x in os.listdir(os.path.join(runs5, c5, c5)) if x.endswith(".sca")})
    ev4 = l4[reps4.index(r4)] if r4 in reps4 and reps4.index(r4) < len(l4) else None
    ev5 = l5[reps5.index(r5)] if r5 in reps5 and reps5.index(r5) < len(l5) else None
    if ev4 is None or ev4 != ev5:
        probs.append(f"final event number {ev4} vs {ev5}")
    return probs, ev4


def gate(runs5, runs4):
    rows, ok_all, totals = [], True, Counter()
    for c4, c5, reps in PAIRS:
        for r in reps:
            probs, ev = compare_run(runs4, c4, r, runs5, c5, r, totals=totals)
            totals["runs"] += 1
            rows.append((f"{c4}#{r} vs {c5}#{r}", not probs, probs, ev))
            ok_all &= not probs
    c4, c5, reps = UNIT_PAIR
    for r in reps:
        probs, ev = compare_run(runs5, c4, r, runs5, c5, r, network="M2S5ChainTest", tts=("ttD", "ttN"), totals=totals)
        totals["runs"] += 1
        rows.append((f"{c4}#{r} vs {c5}#{r}", not probs, probs, ev))
        ok_all &= not probs
    return ok_all, rows, dict(totals)


if __name__ == "__main__":
    runs5 = sys.argv[1]
    runs4 = sys.argv[2] if len(sys.argv) > 2 else os.path.join(os.path.dirname(runs5.rstrip("/")), "..", "M2-S4", "runs")
    ok, rows, totals = gate(runs5, runs4)
    for name, good, probs, ev in rows:
        print(f"{'PASS' if good else 'FAIL'}  {name}  final event #{ev}" + ("" if good else f"\n      {probs[:6]}"))
    print(f"\nG0: {'PASS' if ok else 'FAIL'} ({sum(1 for r in rows if r[1])}/{len(rows)} run pairs identical); totals {totals}")
    sys.exit(0 if ok else 1)
