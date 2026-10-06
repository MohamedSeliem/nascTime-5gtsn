#!/usr/bin/env python3
# Authors: Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)
"""Validate aggregate and per-UE invariants for the N=100 uplink FRER run."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path


def read_scalars(path: Path) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if line.startswith("scalar "):
            fields = shlex.split(line)
            if len(fields) >= 4:
                values[(fields[1], fields[2])] = float(fields[3])
    return values


def one(values, suffix: str, scalar: str) -> float:
    matches = [value for (module, name), value in values.items()
               if module.endswith(suffix) and name == scalar]
    if len(matches) != 1:
        raise AssertionError(f"expected one {suffix}:{scalar}, found {len(matches)}")
    return matches[0]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scalar_file", type=Path)
    parser.add_argument("--ues", type=int, default=10)
    args = parser.parse_args()
    values = read_scalars(args.scalar_file)

    primary = replica = 0.0
    inactive_primary: list[int] = []
    inactive_secondary: list[int] = []
    for ue in range(args.ues):
        primary += one(values, f"dsTt[{ue}].frerReplicatorUl", "primarySent:count")
        replica += one(values, f"dsTt[{ue}].frerReplicatorUl", "replicaSent:count")
        if one(values, f"ue[{ue}].cellularNic.nrMac",
               "receivedPacketFromUpperLayer:count") <= 0:
            inactive_primary.append(ue)
        if one(values, f"ue[{ue}].cellularNic.nrMac2",
               "receivedPacketFromUpperLayer:count") <= 0:
            inactive_secondary.append(ue)

    if primary != replica:
        raise AssertionError(f"replication mismatch: primary={primary}, replica={replica}")
    if inactive_primary or inactive_secondary:
        raise AssertionError(
            f"inactive UE legs: primary={inactive_primary}, secondary={inactive_secondary}")

    accepted_primary = one(values, "nwTt.frerRecoveryUl", "recoveredFromPrimary:count")
    accepted_replica = one(values, "nwTt.frerRecoveryUl", "recoveredFromReplica:count")
    duplicates = one(values, "nwTt.frerRecoveryUl", "duplicatesDropped:count")
    overruns = one(values, "nwTt.frerRecoveryUl", "windowOverruns:count")
    accepted = accepted_primary + accepted_replica
    if accepted_primary <= 0 or accepted_replica <= 0:
        raise AssertionError("both radio paths must contribute accepted frames")

    delivery_ratio = accepted / primary if primary else 0.0
    missing = primary - accepted
    duplicate_ratio = duplicates / replica if replica else 0.0

    print(f"RESULT: {args.ues}-UE uplink FRER scalability run")
    print(f"  original frames={primary:g}, replicas={replica:g}")
    print(f"  accepted: primary={accepted_primary:g}, replica={accepted_replica:g}")
    print(f"  unique delivery={accepted:g}/{primary:g} ({delivery_ratio:.2%}), missing={missing:g}")
    print(f"  duplicates eliminated={duplicates:g}/{replica:g} ({duplicate_ratio:.2%})")
    print(f"  recovery window overruns={overruns:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
