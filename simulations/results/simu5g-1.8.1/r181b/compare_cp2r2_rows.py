#!/usr/bin/env python3
"""M2-R181b: row-by-row comparison of the CP2 r2 gate/information rows, 1.8.0 record vs 1.8.1 batch evaluations.
    compare_cp2r2_rows.py <1.8.0 cp2r2-check.txt> <1.8.1 eval> [<1.8.1 eval> ...]   -> stdout
Rows are keyed by (family, key); reported: rows only on one side, verdict changes, and per family the number of rows
whose detail numbers changed, with up to 3 examples (old -> new)."""
import re
import sys
from collections import Counter, defaultdict
NUM = re.compile(r"[-+]?\d+(?:\.\d+)?(?:[eE][-+]?\d+)?")


def rows(f):
    out = {}
    for line in open(f):
        p = line.rstrip("\n").split(" | ")
        if len(p) >= 4 and p[2] in ("PASS", "FAIL") and p[0] not in ("CONTROL",) and not p[0].startswith("FAIL row"):
            out[(p[0], p[1])] = (p[2], " | ".join(p[3:]))
    return out


old = rows(sys.argv[1])
new = {}
for f in sys.argv[2:]:
    new.update(rows(f))
only_old, only_new = sorted(set(old) - set(new)), sorted(set(new) - set(old))
vchg = [(k, old[k][0], new[k][0]) for k in old if k in new and old[k][0] != new[k][0]]
nchg, ex = Counter(), defaultdict(list)
for k in old:
    if k in new and old[k][1] != new[k][1]:
        nchg[k[0]] += 1
        a, b = NUM.findall(old[k][1]), NUM.findall(new[k][1])
        d = [f"{x} -> {y}" for x, y in zip(a, b) if x != y][:6]
        if len(ex[k[0]]) < 3:
            ex[k[0]].append(f"{k[1]}: {'; '.join(d)}")
print(f"rows: 1.8.0 {len(old)}, 1.8.1 {len(new)}; only in 1.8.0 {len(only_old)} {only_old[:4]}; only in 1.8.1 {len(only_new)} {only_new[:4]}")
print(f"verdict changes: {len(vchg)} {vchg[:10]}")
print("rows with changed detail numbers, per family (total rows in the family):")
tot = Counter(k[0] for k in old)
for fam in sorted(tot):
    print(f"  {fam}: {nchg[fam]} of {tot[fam]}" + ("".join(f"\n      e.g. {e[:300]}" for e in ex[fam]) if nchg[fam] else ""))
