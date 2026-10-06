#!/usr/bin/env python3
"""Validate the standalone uplink QoS demo using only the Python standard library.

Authors: Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)
"""

from __future__ import annotations

import math
import re
import statistics
import sys
from pathlib import Path


VECTOR_RE = re.compile(
    r"^vector\s+(\d+)\s+\S+\.tsnDeviceA\.app\[(\d+)\]\s+rcvdPkLifetime:vector\b"
)


def percentile(values: list[float], probability: float) -> float:
    ordered = sorted(values)
    position = (len(ordered) - 1) * probability
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (position - lower)


def read_delays(path: Path) -> dict[int, list[float]]:
    ids: dict[int, int] = {}
    delays = {0: [], 1: []}
    with path.open(encoding="utf-8") as vector_file:
        for line in vector_file:
            match = VECTOR_RE.match(line)
            if match:
                ids[int(match.group(1))] = int(match.group(2))
                continue
            fields = line.split()
            if len(fields) != 4 or not fields[0].isdigit():
                continue
            vector_id = int(fields[0])
            if vector_id in ids:
                delays[ids[vector_id]].append(float(fields[3]) * 1000)
    return delays


def report(path: Path) -> bool:
    print(path.name)
    delays = read_delays(path)
    valid = True
    for app, pcp in ((0, 6), (1, 0)):
        values = delays[app]
        if not values:
            print(f"  PCP {pcp}: no received packets")
            valid = False
            continue
        print(
            f"  PCP {pcp}: n={len(values)} mean={statistics.fmean(values):.3f} ms "
            f"p50={percentile(values, 0.50):.3f} ms "
            f"p95={percentile(values, 0.95):.3f} ms "
            f"p99={percentile(values, 0.99):.3f} ms"
        )
    return valid


def verify_drbs(vector_path: Path) -> bool:
    scalar_path = vector_path.with_suffix(".sca")
    if not scalar_path.is_file():
        print(f"  ERROR: missing {scalar_path.name}; the run did not finish cleanly")
        return False
    scalar_text = scalar_path.read_text(encoding="utf-8")
    drb0 = (
        "UplinkNetwork.gnb.cellularNic.pdcp-rx-2049-0",
        "UplinkNetwork.gnb.cellularNic.rlc-um-rx-2049-0",
    )
    drb1 = (
        "UplinkNetwork.gnb.cellularNic.pdcp-rx-2049-1",
        "UplinkNetwork.gnb.cellularNic.rlc-um-rx-2049-1",
    )
    # Module paths begin with the actual network name, so match the stable
    # cellular suffix rather than coupling the checker to a NED type name.
    expected = tuple(module.removeprefix("UplinkNetwork.") for module in drb0)
    require_drb1 = vector_path.name.startswith("Qos-")
    if require_drb1:
        expected += tuple(module.removeprefix("UplinkNetwork.") for module in drb1)
    missing = [module for module in expected if module not in scalar_text]
    if missing:
        print("  ERROR: QoS path incomplete; missing receive entities:")
        for module in missing:
            print(f"    {module}")
        return False
    if require_drb1:
        print("  DRB check: PASS (gNB instantiated receive entities for DRB 0 and DRB 1)")
    else:
        unexpected = [module.removeprefix("UplinkNetwork.") for module in drb1 if module.removeprefix("UplinkNetwork.") in scalar_text]
        if unexpected:
            print("  ERROR: baseline unexpectedly instantiated DRB 1")
            return False
        print("  DRB check: PASS (baseline used DRB 0 only)")
    return True


def main() -> None:
    paths = [Path(argument) for argument in sys.argv[1:]]
    if not paths:
        result_dir = Path("results/qos")
        paths = [
            result_dir / "Baseline-#0.vec",
            result_dir / "Qos-#0.vec",
        ]
    missing = [str(path) for path in paths if not path.is_file()]
    if missing:
        raise SystemExit("missing result file(s): " + ", ".join(missing))
    valid = True
    for path in paths:
        valid = report(path) and valid
        valid = verify_drbs(path) and valid
    if not valid:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
