#!/usr/bin/env python3
"""M2-S7.1 closure diagnostic: why the QOS_PF runs are (almost) seed-invariant (review 2026-10-22, item 5).

    diag_m2s71_seeds.py <results/M2-S7.1>   -> prints the report (m2s71.sh writes diagnostics/seeds.txt)

Inputs (all produced by m2s71.sh seeds):
  - M2S71-R-<base> (seeds fixed, reps 0-4): numbers drawn per physical RNG = per module group
    (TtSyncMonitorRngProbe scalars rngDrawn:<k>); reps must be identical (determinism sanity check);
  - M2S71-R-<base>-v<k> (reps 0-4): only physical RNG k varies with the repetition;
  - the primary runs: distinct runs per (option, variant, HARQ) group.
For each run the outputs compared are: the digest of every PCAP, and the gPTP view the experiment
uses (per cohort pair: outcome, lag, residence).
"""
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_m2s71 as K  # noqa: E402
import gate_m2s71_p0 as G  # noqa: E402

GROUPS = {0: "direct getEnvir()->getRNG(0) callers (PF/QoS score jitter, PhyPisaData)", 1: "clocks", 2: "UE MAC",
          3: "UE NIC rest (PHY, channel model)", 4: "gNB MAC", 5: "gNB NIC rest (PHY, channel model)", 6: "applications",
          7: "everything else"}
BASES = ("q0-idle", "q0-load", "qdu-idle", "qdu-load")


def drawn(sca):
    out = {}
    for line in open(sca):
        if line.startswith("scalar") and "rngDrawn:" in line:
            p = line.split()
            out[int(p[2].split(":")[1])] = int(float(p[3]))
    return out


def gptp_view(a):
    return tuple((s, a.outcome[s], a.lag[s], a.res[s]) for s in a.cohort_complete())


def main():
    res = sys.argv[1]
    root = os.path.join(res, "runs")
    have = set(G.run_dirs(root))
    print("M2-S7.1 seed-invariance diagnostic (closure, review 2026-10-22 item 5)\n")
    print("1. Numbers drawn per physical RNG (= module group) in one run of each base, seeds fixed:")
    for b in BASES:
        cfg = f"M2S71-R-{b}"
        if cfg not in have:
            continue
        reps = G.reps_of(root, cfg)
        d = [drawn(os.path.join(root, cfg, cfg, f"{r}.sca")) for r in reps]
        dig = {K.run_digest(root, cfg, r) for r in reps}
        print(f"  {cfg} (reps {reps}; identical runs: {len(dig) == 1}): " + ", ".join(f"RNG {k} {GROUPS[k]}: {v}" for k, v in sorted(d[0].items())))
    print("\n2. Influence: only physical RNG k varies (seeds 0-4); distinct runs (PCAP digests) and distinct gPTP views "
          "(cohort outcome, lag, residence per pair):")
    for b in BASES:
        for k in sorted(GROUPS):
            cfg = f"M2S71-R-{b}-v{k}"
            if cfg not in have:
                continue
            reps = G.reps_of(root, cfg)
            A = [K.Analysis(root, cfg, r) for r in reps]
            dig = {a.digest for a in A}
            views = {gptp_view(a) for a in A}
            cls = [dict(Counter(a.outcome[s] for s in a.cohort_complete())) for a in A]
            b0 = A[0]
            dif = [sum(1 for s in a.cohort_complete() if (a.outcome[s], a.lag[s], a.res[s]) != (b0.outcome[s], b0.lag[s], b0.res[s]))
                   for a in A[1:]]
            print(f"  {cfg}: RNG {k} ({GROUPS[k]}): {len(dig)} distinct runs, {len(views)} distinct gPTP views of {len(reps)}; "
                  f"cohort pairs differing from seed 0 (outcome, lag or residence), seeds 1-4: {dif}; cohort outcomes per seed {cls}")
    print("\n   Not varied: RNG 1 (clocks), 4 (gNB MAC), 6 (applications) draw no numbers in these configs (section 1).")
    print("\n3. Primary runs: distinct runs per (option, variant, HARQ) group:")
    groups = defaultdict(list)
    for cfg in G.run_dirs(root):
        if cfg.startswith("M2S71-R-") or any(x in cfg for x in ("-N-", "-H-", "-M0-", "-B5", "-B6", "-B10")):
            continue
        for r in G.reps_of(root, cfg):
            groups[cfg].append(K.run_digest(root, cfg, r))
    for cfg, dg in sorted(groups.items()):
        print(f"  {cfg}: {len(set(dg))} distinct of {len(dg)}")


if __name__ == "__main__":
    main()
