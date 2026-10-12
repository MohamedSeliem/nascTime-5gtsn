#!/usr/bin/env python3
"""M1-S0 checker: vanilla Simu5G 1.8.0 Ethernet-session reference.

Reads results/S0 written by s0_vanilla_reference.sh and prints a PASS/FAIL table.
Criteria (migration/m1-plan.md, S0):
  build        upstream fingerprint rows for /nr/ethernet/ all PASS
  run          each config finished ("End." in its log, .sca present)
  functional   every sink received frames; delivered/sent per flow recorded
  experimental Ethernet-Bridge over the seed range: per-direction delay
               (meanBitLifeTimePerPacket at the sink) mean and 95% CI recorded
Delivered/sent is recorded, not judged: frames in flight at sim-time-limit are
counted as not delivered, and the handover config's losses are upstream behaviour.
"""
import math
import os
import re
import sys

import pandas as pd

OUT = sys.argv[1] if len(sys.argv) > 1 else "results/S0"
NET = "EthernetSessions."
rows = []          # (check, detail, verdict)


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


# --- build: upstream fingerprint rows -------------------------------------------
fp = open(os.path.join(OUT, "fingerprints.log")).read()
fp_rows = re.findall(r"-c (\S+) -r 0\s+\.\.\. : (\w+)", fp)
add("build: upstream fingerprints", ", ".join(f"{c}={v}" for c, v in fp_rows),
    len(fp_rows) == 4 and all(v == "PASS" for _, v in fp_rows))

# --- run completion -----------------------------------------------------------
configs = ["Ethernet-Hosts", "Ethernet-Bridge", "Ethernet-Handover", "Ethernet-Mixed"]
for c in configs:
    log = open(os.path.join(OUT, f"run-{c}.log")).read()
    sca = os.path.exists(os.path.join(OUT, "runs", c, "0.sca"))
    add(f"run: {c}", "finished" if ("End." in log and sca) else "did not finish",
        "End." in log and sca and "<!> Error" not in log)

# --- functional: per-flow delivery --------------------------------------------
d = pd.read_csv(os.path.join(OUT, "runs.csv"), low_memory=False)
sca = d[d.type == "scalar"].copy()
sca["config"] = sca.run.str.extract(r"^(Ethernet-[A-Za-z]+)")[0]


def val(cfg, module, name):
    r = sca[(sca.config == cfg) & (sca.module == NET + module) & (sca.name == name)]
    return int(float(r.value.iloc[0])) if len(r) else None


# sink -> list of sources whose frames it should receive (from the example's ini)
flows = {
    "Ethernet-Hosts": [
        ("dnStation.app[1].sink", ["ue[0].app[0].source"]),
        ("ue[1].app[1].sink", ["dnStation.app[0].source", "dnStation.app[2].source"]),
        ("ue[0].app[1].sink", ["ue[1].app[0].source", "dnStation.app[2].source"]),
    ],
    "Ethernet-Bridge": [
        ("dnStation.app[2].sink", ["device[0].app[0].source", "device[0].app[1].source"]),
        ("device[0].app[2].sink", ["dnStation.app[0].source", "dnStation.app[1].source"]),
    ],
    "Ethernet-Handover": [
        ("dnStation.app[1].sink", ["ue[0].app[0].source"]),
        ("ue[0].app[1].sink", ["dnStation.app[0].source"]),
    ],
    "Ethernet-Mixed": [
        ("dnStation.app[1].sink", ["ue[0].app[0].source"]),
        ("ue[0].app[1].sink", ["dnStation.app[0].source"]),
        ("ue[2].unstructuredApp[0].sink", ["ue[2].unstructuredApp[0].source"]),
    ],
}
delivery = []
for cfg, fl in flows.items():
    for sink, srcs in fl:
        rx = val(cfg, sink, "packets:count")
        tx = [val(cfg, s, "packets:count") for s in srcs]
        ok = rx is not None and rx > 0 and all(t is not None for t in tx)
        txs = sum(t for t in tx if t is not None)
        delivery.append((cfg, sink, txs, rx))
        add(f"functional: {cfg}", f"{sink}: received {rx} of {txs} sent", ok)

# --- experimental: Ethernet-Bridge delay over seeds -------------------------------
s = pd.read_csv(os.path.join(OUT, "seeds.csv"), low_memory=False)
v = s[(s.type == "vector") & (s.name == "meanBitLifeTimePerPacket:vector")].copy()
stats = []
for sink, label in [("dnStation.app[2].sink", "UL device->dnStation"),
                    ("device[0].app[2].sink", "DL dnStation->device")]:
    per_seed = []
    for _, r in v[v.module == NET + sink].iterrows():
        vals = [float(x) for x in str(r.vecvalue).split()]
        if vals:
            per_seed.append(sum(vals) / len(vals))
    n = len(per_seed)
    mean = sum(per_seed) / n if n else float("nan")
    sd = math.sqrt(sum((x - mean) ** 2 for x in per_seed) / (n - 1)) if n > 1 else float("nan")
    t = {10: 2.262}.get(n, 1.96)
    ci = t * sd / math.sqrt(n) if n > 1 else float("nan")
    stats.append((label, n, mean, ci, min(per_seed) if n else None, max(per_seed) if n else None))
    add(f"experimental: Ethernet-Bridge {label}",
        f"{n} seeds, mean of per-seed means {mean*1e3:.3f} ms +/- {ci*1e3:.3f} ms (95% CI)",
        n == 10 and not math.isnan(mean))

# --- print ------------------------------------------------------------------------
w = max(len(r[0]) for r in rows)
for c, det, verdict in rows:
    print(f"{verdict:4}  {c:<{w}}  {det}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
print()
print("delivery table (config, sink, sent, received):")
for r in delivery:
    print("  ", r)
print("delay table (direction, seeds, mean_s, ci95_s, min_seed_mean_s, max_seed_mean_s):")
for r in stats:
    print("  ", r)
