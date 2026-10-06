#!/usr/bin/env python3
# Authors: Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)
"""Validate the essential invariants of the two-gNB uplink FRER run."""

from __future__ import annotations

import argparse
import shlex
from pathlib import Path


def read_scalars(path: Path) -> dict[tuple[str, str], float]:
    values: dict[tuple[str, str], float] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.startswith("scalar "):
            continue
        fields = shlex.split(line)
        if len(fields) >= 4:
            values[(fields[1], fields[2])] = float(fields[3])
    return values


def find(values: dict[tuple[str, str], float], module_suffix: str, name: str) -> float:
    matches = [value for (module, scalar), value in values.items()
               if module.endswith(module_suffix) and scalar == name]
    if len(matches) != 1:
        raise AssertionError(
            f"expected one scalar {module_suffix}:{name}, found {len(matches)}")
    return matches[0]


def positive(values: dict[tuple[str, str], float], module_suffix: str, name: str) -> float:
    value = find(values, module_suffix, name)
    if value <= 0:
        raise AssertionError(f"{module_suffix}:{name} must be positive, got {value}")
    return value


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("scalar_file", type=Path)
    args = parser.parse_args()
    values = read_scalars(args.scalar_file)

    primary = positive(values, "dsTt[0].frerReplicatorUl", "primarySent:count")
    replica = positive(values, "dsTt[0].frerReplicatorUl", "replicaSent:count")
    if primary != replica:
        raise AssertionError(f"replication mismatch: primary={primary}, replica={replica}")

    # Both UE radio stacks must receive uplink traffic.  nrMac is attached to
    # gNB; nrMac2 is attached to gNB2 and carries replica DRB 4.
    positive(values, "ue[0].cellularNic.nrMac", "receivedPacketFromUpperLayer:count")
    positive(values, "ue[0].cellularNic.nrMac2", "receivedPacketFromUpperLayer:count")

    # Both gNBs must deliver user-plane packets upward. Merely receiving a
    # lower-layer packet is insufficient because BSR/control frames can make
    # that counter positive even when gNB2 never schedules DRB 4 data.
    positive(values, "gnb.cellularNic.mac", "sentPacketToUpperLayer:count")
    positive(values, "gnb2.cellularNic.mac", "sentPacketToUpperLayer:count")

    # Require traffic beyond gNB2 as proof that the secondary N3 path was used.
    positive(values, "upf2.udp", "packetReceived:count")

    recovered_primary = find(values, "nwTt.frerRecoveryUl", "recoveredFromPrimary:count")
    recovered_replica = find(values, "nwTt.frerRecoveryUl", "recoveredFromReplica:count")
    duplicates = positive(values, "nwTt.frerRecoveryUl", "duplicatesDropped:count")
    if recovered_primary + recovered_replica <= 0:
        raise AssertionError("NW-TT recovery did not forward any uplink FRER frame")

    print("PASS: DS-TT replicated uplink traffic over both UE/gNB legs")
    print(f"  copies: primary={primary:g}, replica={replica:g}")
    print(f"  NW-TT accepted: primary={recovered_primary:g}, replica={recovered_replica:g}")
    print(f"  NW-TT eliminated duplicates={duplicates:g}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
