#!/usr/bin/env python3
"""M2-S4 hard gate G0 (migration/m2-s4-design.md 8.0): passive transparency of TtPdelayPort.

Usage: gate_m2s4.py <M2-S1 runs dir> <M2-S4 runs dir>   (also imported by check_m2s4.py)

For every M2S1 run (seeds 0-9, frag, load, load-harq16) and its M2S4-passive counterpart:
  - every .pcapng is byte-identical (same file name, same bytes);
  - every per-frame log (m2log/*.csv) is byte-identical;
  - every vector data line (event number, time, value) and every scalar / statistic line of
    every module present in M2S1 is identical, in order; recorded parameters (par lines) are
    identical except the relocation of one ideal-channel object per translator (see
    EXPECTED_PAR_ONLY_M2S1); excluded: run attributes / config lines (they
    name the config, date, process id, result dir), the result dir and config name inside
    recorded parameter values (they name the output files) and the rows of the new TtPdelayPort
    modules (trafficConditionerLayer);
  - the final event number in the run log is identical.
"""
import hashlib
import os
import re
import sys
from collections import Counter

PAIRS = [("M2S1", "M2S4-passive", list(range(10))), ("M2S1-frag", "M2S4-passive-frag", [0]),
         ("M2S1-load", "M2S4-passive-load", [0]), ("M2S1-load-harq16", "M2S4-passive-load-harq16", [0])]
NEW_MODULE = "trafficConditionerLayer"
# The only structural difference allowed in recorded parameters: in M2S1 the (empty)
# trafficConditionerLayer slot is bypassed, so the ideal channel object of the connection
# above the TtTimestampLayer is recorded under measurementLayer.upperLayerOut; with the
# TtPdelayPort installed that connection ends at the new module and its channel is recorded
# there (excluded as a new-module row).
EXPECTED_PAR_ONLY_M2S1 = Counter({
    f'par M1Bridge.{tt}.eth[1].measurementLayer.upperLayerOut.channel typename "\\"ned.IdealChannel\\""': 1
    for tt in ("dsTt", "nwTt")})


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def files(base):
    out = {}
    if os.path.isdir(base):
        for root, _, names in os.walk(base):
            for n in names:
                out[os.path.relpath(os.path.join(root, n), base)] = os.path.join(root, n)
    return out


def vec_data(path):
    """{(module, name): [(event, time, value), ...]} for every vector except new modules."""
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
                if NEW_MODULE not in p[2]:
                    k = (p[2], p[3])
                    if k in data:
                        raise ValueError(f"duplicate vector {k}")
                    ids[p[1]] = k
                    data[k] = []
    return data


def sca_data(path, resultdir, config):
    """Ordered list of scalar/statistic/field/bin/par lines, excluding run attributes and new
    modules. In recorded parameter values (par lines) the result directory and the config
    name, which name the output files, are replaced by placeholders."""
    out, skip = [], False
    with open(path) as fh:
        for line in fh:
            if line.startswith(("version", "run ", "attr ", "config ", "itervar ")):
                continue
            if line.startswith(("scalar ", "statistic ", "par ")):
                mod = line.split(" ", 2)[1]
                skip = NEW_MODULE in mod
            if not skip:
                line = line.rstrip("\n")
                if line.startswith("par "):
                    line = line.replace(os.path.abspath(resultdir), "<RESULTDIR>").replace(config, "<CONFIG>")
                out.append(line)
    return out


def last_events(log):
    with open(log) as fh:
        return re.findall(r"event #(\d+)", "\n".join(l for l in fh if "Simulation time limit reached" in l))


def compare_run(runs1, c1, r1, runs4, c4, r4, totals=None):
    """Problems (empty list = identical) between run (c1, r1) under runs1 and (c4, r4) under runs4."""
    totals = totals if totals is not None else {"pcapng": 0, "logs": 0, "vectors": 0, "vector lines": 0, "scalar lines": 0}
    probs = []
    for kind, sub1, sub4 in (("pcapng", f"pcap/{c1}-{r1}", f"pcap/{c4}-{r4}"), ("logs", f"m2log/{c1}-{r1}", f"m2log/{c4}-{r4}")):
        f1, f4 = files(os.path.join(runs1, c1, sub1)), files(os.path.join(runs4, c4, sub4))
        if kind == "logs":   # the engine's own log (active configs only) is not an M2-S1 log
            f4 = {k: v for k, v in f4.items() if NEW_MODULE not in k}
        if not f1:
            probs.append(f"no {kind} in M2-S1")
        if set(f1) != set(f4):
            probs.append(f"{kind} file sets differ: {sorted(set(f1) ^ set(f4))[:3]}")
        for n in sorted(set(f1) & set(f4)):
            totals[kind] += 1
            if sha(f1[n]) != sha(f4[n]):
                probs.append(f"{kind} differs: {n}")
    v1 = vec_data(os.path.join(runs1, c1, c1, f"{r1}.vec"))
    v4 = vec_data(os.path.join(runs4, c4, c4, f"{r4}.vec"))
    if set(v1) != set(v4):
        probs.append(f"vector sets differ: {sorted(set(v1) ^ set(v4))[:3]}")
    for k in set(v1) & set(v4):
        totals["vectors"] += 1
        totals["vector lines"] += len(v1[k])
        if v1[k] != v4[k]:
            probs.append(f"vector differs: {k}")
    s1 = sca_data(os.path.join(runs1, c1, c1, f"{r1}.sca"), os.path.join(runs1, c1), c1)
    s4 = sca_data(os.path.join(runs4, c4, c4, f"{r4}.sca"), os.path.join(runs4, c4), c4)
    totals["scalar lines"] += len(s1)
    n1 = [x for x in s1 if not x.startswith("par ")]
    n4 = [x for x in s4 if not x.startswith("par ")]
    if n1 != n4:
        d = next((i for i, (a, b) in enumerate(zip(n1, n4)) if a != b), min(len(n1), len(n4)))
        probs.append(f"scalars differ at line {d}: {n1[d:d+1]} vs {n4[d:d+1]}")
    p1 = Counter(x for x in s1 if x.startswith("par "))
    p4 = Counter(x for x in s4 if x.startswith("par "))
    if p4 - p1 or (p1 - p4) != EXPECTED_PAR_ONLY_M2S1:
        probs.append(f"recorded parameters differ beyond the expected channel relocation: "
                     f"only M2S1 {sorted(p1 - p4)[:3]}, only passive {sorted(p4 - p1)[:3]}")
    e1 = last_events(os.path.join(runs1, f"run-{c1}.log"))
    e4 = last_events(os.path.join(runs4, f"run-{c4}.log"))
    reps1 = sorted({int(x[:-4]) for x in os.listdir(os.path.join(runs1, c1, c1)) if x.endswith(".sca")})
    reps4 = sorted({int(x[:-4]) for x in os.listdir(os.path.join(runs4, c4, c4)) if x.endswith(".sca")})
    ev1 = e1[reps1.index(r1)] if r1 in reps1 and reps1.index(r1) < len(e1) else None
    ev4 = e4[reps4.index(r4)] if r4 in reps4 and reps4.index(r4) < len(e4) else None
    if ev1 is None or ev1 != ev4:
        probs.append(f"final event number {ev1} vs {ev4}")
    return probs, ev1


def gate(runs1, runs4):
    rows, ok_all = [], True
    totals = {"pcapng": 0, "logs": 0, "vectors": 0, "vector lines": 0, "scalar lines": 0, "runs": 0}
    for c1, c4, reps in PAIRS:
        for r in reps:
            totals["runs"] += 1
            probs, ev = compare_run(runs1, c1, r, runs4, c4, r, totals)
            rows.append((f"{c4}#{r}", not probs, probs[:4], ev))
            ok_all &= not probs
    return ok_all, rows, totals


if __name__ == "__main__":
    ok, rows, totals = gate(sys.argv[1], sys.argv[2])
    for n, ok_, probs, ev in rows:
        print(f"{'PASS' if ok_ else 'FAIL'}  {n}: final event #{ev}; {probs or 'identical'}")
    print(f"totals {totals}")
    print(f"G0: {'PASS' if ok else 'FAIL'}")
    sys.exit(0 if ok else 1)
