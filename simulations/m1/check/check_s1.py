#!/usr/bin/env python3
"""M1-S1 checker: nascTime's copy of the reference scenario vs S0, seed by seed.

Criteria (migration/m1-plan.md, S1):
  run          all seeds of Config S1 finished
  functional   per-flow sent and received counts equal S0 Ethernet-Bridge for each seed
  experimental per-packet delay samples (meanBitLifeTimePerPacket at each sink, values
               and timestamps) identical to S0 for each seed
Station mapping: talker = device[0], listener = dnStation.
Usage: check_s1.py <results dir containing S0/ and S1/>
"""
import os
import sys

import pandas as pd

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(stage, net):
    d = pd.read_csv(os.path.join(RES, stage, "seeds.csv"), low_memory=False)
    d = d[d.run.notna()].copy()
    d["seed"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
    d["mod"] = d.module.str.replace(net + ".", "", regex=False)
    return d


s0 = load("S0", "EthernetSessions")
s1 = load("S1", "M1Bridge")
MAP = {"talker": "device[0]", "listener": "dnStation"}


def to_s0(mod):
    for a, b in MAP.items():
        if mod == a or mod.startswith(a + "."):
            return b + mod[len(a):]
    return mod


seeds0 = sorted(s0.seed.dropna().unique())
seeds1 = sorted(s1.seed.dropna().unique())
log = open(os.path.join(RES, "S1", "run-S1-seeds.log")).read()
add("run: S1 seeds", f"{len(seeds1)} seeds finished; S0 has {len(seeds0)}",
    seeds1 == seeds0 and len(seeds1) > 0 and "<!> Error" not in log)

COUNTS = [("talker.app[0].source", "packets:count"), ("talker.app[1].source", "packets:count"),
          ("listener.app[0].source", "packets:count"), ("listener.app[1].source", "packets:count"),
          ("listener.app[2].sink", "packets:count"), ("talker.app[2].sink", "packets:count")]
DELAYS = [("listener.app[2].sink", "UL talker->listener"), ("talker.app[2].sink", "DL listener->talker")]

cnt_fail, dly_fail, n_samples = [], [], 0
for seed in [int(s) for s in seeds1]:
    a = s1[(s1.seed == seed) & (s1.type == "scalar")]
    b = s0[(s0.seed == seed) & (s0.type == "scalar")]
    for mod, name in COUNTS:
        va = a[(a["mod"] == mod) & (a.name == name)].value
        vb = b[(b["mod"] == to_s0(mod)) & (b.name == name)].value
        if len(va) != 1 or len(vb) != 1 or float(va.iloc[0]) != float(vb.iloc[0]):
            cnt_fail.append((seed, mod, list(va), list(vb)))
    va_ = s1[(s1.seed == seed) & (s1.type == "vector") & (s1.name == "meanBitLifeTimePerPacket:vector")]
    vb_ = s0[(s0.seed == seed) & (s0.type == "vector") & (s0.name == "meanBitLifeTimePerPacket:vector")]
    for mod, _ in DELAYS:
        x = va_[va_["mod"] == mod]
        y = vb_[vb_["mod"] == to_s0(mod)]
        if len(x) != 1 or len(y) != 1:
            dly_fail.append((seed, mod, "vector missing"))
            continue
        tx, vx = x.vectime.iloc[0].split(), x.vecvalue.iloc[0].split()
        ty, vy = y.vectime.iloc[0].split(), y.vecvalue.iloc[0].split()
        n_samples += len(vx)
        if tx != ty or vx != vy:
            dly_fail.append((seed, mod, f"{len(vx)} vs {len(vy)} samples"))

add("functional: per-flow counts == S0", f"{len(seeds1)} seeds x {len(COUNTS)} counters; mismatches: {len(cnt_fail)}",
    not cnt_fail and len(seeds1) > 0)
add("experimental: delay samples == S0", f"{n_samples} samples compared (value and time); mismatching vectors: {len(dly_fail)}",
    not dly_fail and n_samples > 0)

w = max(len(r[0]) for r in rows)
for c, det, verdict in rows:
    print(f"{verdict:4}  {c:<{w}}  {det}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
for f in cnt_fail[:10]:
    print("  count mismatch:", f)
for f in dly_fail[:10]:
    print("  delay mismatch:", f)

# seed-0 summary for the record
print()
print("seed 0 (S1): sent/received per direction")
a = s1[(s1.seed == 0) & (s1.type == "scalar")]
g = lambda m: int(float(a[(a["mod"] == m) & (a.name == "packets:count")].value.iloc[0]))
print(f"  UL talker->listener: sent {g('talker.app[0].source') + g('talker.app[1].source')}, received {g('listener.app[2].sink')}")
print(f"  DL listener->talker: sent {g('listener.app[0].source') + g('listener.app[1].source')}, received {g('talker.app[2].sink')}")
