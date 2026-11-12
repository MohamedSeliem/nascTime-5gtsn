#!/usr/bin/env python3
"""M2-R181b diagnostic (no verdict): what differs between Simu5G 1.8.0 and 1.8.1 in the five T0-R reference runs.

    diag_t0r.py <1.8.0 runs root> <1.8.1 runs root> <config> [<config> ...]

Each root holds <config>/ as written by opp_run --result-dir (pcap/<config>-0/*.pcapng, m2log/<config>-0/*.csv).
For every PCAP and m2log file: identical or not. For a differing CSV: the columns that differ (row-aligned) and the row
counts. For a differing PCAP: frame counts and the number of frames whose (bytes, timestamp) differ, per direction.
"""
import csv
import glob
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "../../../m2/check"))
import pcapng  # noqa: E402

A, B, CFGS = sys.argv[1], sys.argv[2], sys.argv[3:]
for cfg in CFGS:
    fa = sorted(glob.glob(os.path.join(A, cfg, "pcap", "*", "*.pcapng")) + glob.glob(os.path.join(A, cfg, "m2log", "*", "*.csv")))
    same, out = 0, []
    for p in fa:
        q = p.replace(A, B, 1)
        name = os.path.basename(p).replace("M1Bridge.", "")
        if not os.path.exists(q):
            out.append(f"  MISSING in 1.8.1: {name}")
            continue
        x, y = open(p, "rb").read(), open(q, "rb").read()
        if x == y:
            same += 1
            continue
        if p.endswith(".csv"):
            a = list(csv.reader(x.decode().splitlines()))
            b = list(csv.reader(y.decode().splitlines()))
            h = a[0] if a else []
            dc = {}
            for r1, r2 in zip(a[1:], b[1:]):
                for i, (u, v) in enumerate(zip(r1, r2)):
                    if u != v:
                        col = h[i] if i < len(h) else str(i)
                        dc[col] = dc.get(col, 0) + 1
            out.append(f"  CSV  {name}: rows {len(a) - 1} -> {len(b) - 1}; differing columns {dc}")
        else:
            pa, pb = list(pcapng.read(p)), list(pcapng.read(q))
            dd = {}
            for d in (1, 2):
                xa = [(r["t_ps"], r["data"]) for r in pa if r["dir"] == d]
                xb = [(r["t_ps"], r["data"]) for r in pb if r["dir"] == d]
                dd[d] = (len(xa), len(xb), sum(1 for u, v in zip(xa, xb) if u != v),
                         sum(1 for u, v in zip(xa, xb) if u[1] != v[1]))
            out.append(f"  PCAP {name}: per direction (in=1, out=2): frames 1.8.0 / 1.8.1, frames with time or bytes differing, "
                       f"bytes differing: {dd}")
    print(f"{cfg}: {len(fa)} files, identical {same}, differing {len(fa) - same}")
    print("\n".join(out))
