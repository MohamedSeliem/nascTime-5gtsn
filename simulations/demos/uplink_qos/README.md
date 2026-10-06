# Uplink QoS demo

Authors: Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)

## Implementation

`UplinkQosNetwork.ned` defines the scenario, and `omnetpp.ini` configures its
traffic and bearer mapping. `NRUeDsTt.ned` instantiates the UE's reflective QoS
table. Simu5G implements rule learning and expiry in
`src/simu5g/stack/sdap/common/ReflectiveQosTable.cc` and QFI/DRB selection in
`src/simu5g/stack/sdap/NrSdap.cc`.

Use `omnetpp.ini` for the QoS experiment. It uses the dedicated
`UplinkQosNetwork`, which contains exactly one path:

```text
TSN Device B -> DS-TT -> UE -> gNB -> UPF -> NW-TT -> TSN Device A
```

It intentionally has no TSN switch, standby UE, second DS-TT, ScenarioManager,
RouteSwitcher, TSN AF, BMCA, gPTP modules, or gPTP sideband. The separate
`../uplink_test` demo remains available for radio impairment and failover.

## Configurations

The two configurations use identical topology, traffic, radio geometry, and
random seed. The critical source sends 200-byte packets every 1 ms (1.6 Mbps),
while best effort sends 1000-byte packets every 500 us (16 Mbps). This mirrors
the working downlink experiment's small critical/heavy background load shape
and creates sustained radio contention without making the critical bearer
itself permanently backlogged:

- `Baseline`: untagged traffic, QFI/DRB 0, and the `MAXCI` uplink scheduler.
- `Qos`: TSN Device A sends a small downlink packet on each UDP flow before
  uplink traffic starts. Port 5000 is PCP 6 and port 5001 is PCP 0. The NW-TT
  translates PCP to DSCP, the UPF maps DSCP to QFI, and gNB SDAP marks the
  downlink packet for reflective QoS. The UE learns each reverse-flow QFI from
  that packet. Its uplink SDAP then uses the learned QFI to select a DRB. SDAP assigns
  DRB 1 to the UE's `CONVERSATIONAL` logical-channel group and DRB 0 to
  `BACKGROUND`, so UE MAC serves the high-priority DRB first in each UL grant.

Both applications set DSCP 0 themselves. The UE's DSCP-to-QFI fallback is
disabled. Thus uplink QFI 6 requires the downlink reflective QoS rule; uplink
PCP-to-DSCP translation alone cannot select it. The downlink probe and uplink
packet use the same IP addresses and UDP ports in opposite directions.

The critical load is deliberately much smaller than uplink capacity. An
earlier equal-load version offered a continuously backlogged 16 Mbps critical
bearer; strict logical-channel priority then consumed every grant and starved
best effort. That was an overloaded priority test, not a valid stable QoS
comparison.

## Validate and compare

From this directory, run:

```sh
python3 analyze_qos.py
```

The analyzer reports count, mean, p50, p95, and p99 received-packet lifetime
at TSN Device A for both uplink flows. It also validates bearer use:

```text
Baseline: DRB check PASS (DRB 0 only)
Qos:     DRB check PASS (DRB 0 and DRB 1)
```

Do not interpret the latency comparison unless both checks pass.
The analyzer also fails if either receiver stream has zero samples; QoS must
prioritize DRB 1 without starving DRB 0.

## Expected result

The required invariants are two active DRBs in `Qos`, only DRB 0 in
`Baseline`, nonzero uplink delivery for both flows, and lower critical-stream
latency in `Qos` than in `Baseline`. The previous reference numbers used the
DSCP fallback and do not apply to this reflective QoS version.

## Implementation boundary

The gNB schedules uplink resources for the UE as a whole. The UE MAC then
selects which logical channel fills each grant. Consequently, copying the
downlink `QOS_PF` configuration to the gNB uplink scheduler does not prioritize
two DRBs belonging to the same UE. In this demo SDAP assigns DRB 1 to the
`CONVERSATIONAL` LCG and DRB 0 to `BACKGROUND`; the NR UE reports the residual
aggregate backlog of both DRBs in its BSR so the lower class remains visible.
