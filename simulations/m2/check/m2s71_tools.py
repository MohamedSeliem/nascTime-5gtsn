#!/usr/bin/env python3
"""Small helpers for m2s71.sh (they choose TEST control parameters from a completed run).

    m2s71_tools.py first-res <m2log run dir>   the residence of the first corrected Follow_Up (OMNeT++ ps quantity)
    m2s71_tools.py p99-lag   <m2log run dir>   the 99th percentile (nearest rank) of the monitor's Follow_Up lag
"""
import csv
import glob
import sys


def monitor_rows(d):
    p = glob.glob(f"{d}/*.monitor.csv")
    if len(p) != 1:
        raise SystemExit(f"expected one monitor log in {d}, found {len(p)}")
    return list(csv.DictReader(open(p[0])))


def main():
    mode, d = sys.argv[1:3]
    rows = monitor_rows(d)
    if mode == "first-res":
        r = next(r for r in rows if r["event"] == "corrected" and r["Res"])
        print(f"{int(r['Res'])}ps")
    elif mode == "p99-lag":
        lags = sorted(int(r["lag"]) for r in rows if r["lag"])
        k = -(-99 * len(lags) // 100) - 1
        print(f"{lags[k] - 1}ps")   # strictly below the p99 sample, so that the slowest 1 % (at least one) is above
    else:
        raise SystemExit("unknown mode " + mode)


if __name__ == "__main__":
    main()
