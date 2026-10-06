<p align='center'>
  <img width="430" height="146" alt="upscaled_logo-removebg-preview" src="https://github.com/user-attachments/assets/76eb2f68-5924-402b-936e-5ec78fc352d0" />
</p>

# nascTime (5G-TSN Bridge)

## Overview

This package implements the 3GPP Release 16 5G-TSN integration bridge model
(TS 23.501 §5.28) for the OMNeT++ / INET / Simu5G simulation stack. The 5G
system acts as a transparent IEEE 802.1AS-compliant bridge between two TSN
network segments, with full QoS mapping, CNC-style configuration, static
BMCA clock hierarchy, multi-endpoint scaling, LayeredEthernetInterface
with streaming PHY for TSN feature compatibility, and IEEE 802.1CB Frame
Replication and Elimination for Reliability (FRER) across configurable
transport-diversity paths.

**Stack:** OMNeT++ 6.4 · INET 4.6.x · Simu5G v1.5.0

nascTime is a standalone OMNeT++ project. Its core TSN/5G bridge
functionality (NW-TT, DS-TT, QoS mapping, gPTP transparent clock, static
BMCA, multi-endpoint scaling) builds against **vanilla Simu5G v1.5.0**
with no source modifications, locating INET and Simu5G through the
`INET_ROOT` and `SIMU5G_ROOT` environment variables.

**IEEE 802.1CB FRER (F1–F4), however, requires [nascTime's Simu5G
fork](https://github.com/MohamedSeliem/Simu5G/tree/nasctime-v1.0)** — tag `nasctime-v1.0` — which adds transport-diversity
support (dual-connectivity secondary-leg attach, per-DRB leg routing,
and several upstream bug fixes) that vanilla Simu5G does not have. FRER
scenarios will not run correctly against unpatched Simu5G. See "Which
Simu5G do I need?" below for the exact split.

## Which Simu5G do I need?

| You want to run... | Simu5G build |
|---|---|
| NW-TT/DS-TT bridge, QoS mapping, gPTP, BMCA, multi-endpoint scaling (`tests/`, `simulations/demos/multi_endpoint_test`, `ext_multiendpoint_test`) | **Vanilla Simu5G v1.5.0** — no changes needed |
| FRER — any scenario in `simulations/demos/frer_test/` (F1–F4), and therefore a full `make tests` run | **[nascTime's Simu5G fork](https://github.com/MohamedSeliem/Simu5G/tree/nasctime-v1.0)**, tag `nasctime-v1.0` |

The two-gNB **uplink** FRER configurations (`FrerUplinkDualConn_N1`, `_N2`,
and `_N10`) additionally require the companion Simu5G
[`feat/uplink-frer`](https://github.com/howhangliu/Simu5G/tree/feat/uplink-frer)
branch. Its `Ip2Nic` preserves IPv4 ToS in `FlowControlInfo`, which the UE's
`NrDcMux` and SDAP use to send the replica on DRB 4 through the second gNB.

The fork is a strict superset of vanilla Simu5G v1.5.0 — everything that
works against vanilla also works against the fork. **If you're setting
up nascTime for the first time and aren't sure which scenarios you'll
run, use the fork** to avoid re-building later.

`nasctime-v1.0` on the fork corresponds to `v1.0` on this repo — both
tags mark the same validated, working state.

**End-to-end path (multi-endpoint):**
```
                                                    UE[0] → DS-TT[0] → TSN Device B[0]
TSN Device A → TsnSwitch → NW-TT → UPF → gNB ────   UE[1] → DS-TT[1] → TSN Device B[1]
                                                    UE[2] → DS-TT[2] → TSN Device B[2]
```

**Validated results (3-endpoint, 10s simulation, bidirectional):**

| Direction | Endpoint 0 | Endpoint 1 | Endpoint 2 |
|-----------|-----------|-----------|-----------|
| Forward high priority | 9990 | 9993 | 9993 |
| Forward best effort | 5020 | 5122 | 5101 |
| Reverse (to Device A) | 800 | 800 | 800 |
| gPTP forwarded | 158 | 158 | 158 |

- Device A received 2400 reverse packets (800 × 3 endpoints)
- 5GS residence time: min=2499.756µs, max=2499.948µs, avg=2499.852µs
- QoS: PCP=6 → DSCP=6 → QFI=6 → DRB 1 per endpoint
- TSN AF: 6 stream reservations, live delay tracking
- Static BMCA: 6-node hierarchy validated, 0 errors
- All bridge ports use LayeredEthernetInterface with EthernetStreamingPhyLayer

Figures above were measured on the legacy Simu5G v1.4.1-sdap-2 stack
referenced in the paper below, which this repository no longer targets or
supports. The same scenario has since been confirmed to run cleanly on
Simu5G v1.5.0 with consistent delivery behavior; v1.5.0 is the primary
supported target. Exact per-endpoint counts on v1.5.0 may differ — for
reproducible, version-pinned numbers use the fingerprint baselines in
`tests/fingerprint/simulations.csv` rather than this table.

---

## License & Citation

### License

This project is licensed under the GNU Lesser General Public License v3.0 (LGPL-3.0).

You are free to use, modify, and distribute this software in both open-source and proprietary applications, provided that any modifications to the library itself remain open and users retain the ability to relink against modified versions.

For full details, see the LICENSE file or visit the official page by the Free Software Foundation.

### Support the Project

If you find this repository useful for your research or development, please consider giving it a ⭐ on GitHub, it helps increase visibility and supports continued development.

### Citation

If you use this work in your research, please cite:

```bibtex
@article{nasctime2026,
  title   = {nascTime: A Full-Stack 5G-TSN Bridge Simulation Framework with SDAP-Based QoS Mapping and IEEE 802.1AS Transparent Clock},
  author  = {Mohamed Seliem, Utz Roedig, Cormac Sreenan, Dirk Pesch},
  journal = {arXiv preprint arXiv:2604.04616},
  year    = {2026}
}
```

### Paper
<a href= "https://arxiv.org/abs/2604.04616"> nascTime Draft</a> (Final version will appear in a conference proceeding)

---

## Completed Features

| Gap | Description | Status |
|-----|-------------|--------|
| G1  | NW-TT and DS-TT bridge port modules | ✅ Complete |
| G2  | gPTP tunnel transport (sideband + L2-in-GTP-U) | ✅ Complete |
| G3  | Residence time correction (transparent clock) | ✅ Complete |
| G4  | QoS mapping (PCP ↔ 5QI) with SDAP DRB selection | ✅ Complete |
| G5  | TSN AF / CNC configuration | ✅ Complete |
| G6  | Static BMCA (clock hierarchy management) | ✅ Complete |


| Hardening | Description | Status |
|-----------|-------------|--------|
| H1 | Dynamic pppIf interface ID lookup | ✅ Complete |
| H2 | DS-TT unicast MAC address resolution | ✅ Complete |
| H3 | NW-TT egress path (bidirectional traffic) | ✅ Complete |
| H4 | Robust gPTP message type handling | ✅ Complete |
| H5 | LayeredEthernetInterface with streaming PHY | ✅ Complete |
| H6 | VLAN tag preservation for passthrough traffic | ✅ Complete |

| Scaling | Description | Status |
|---------|-------------|--------|
| S1 | Multi-destination binder registration | ✅ Complete |
| S2 | Scalable parameterized network NED | ✅ Complete |
| S3 | Per-endpoint IP addressing | ✅ Complete |
| S4 | Per-endpoint SDAP/DRB configuration | ✅ Complete |
| S5 | Per-endpoint gPTP configuration | ✅ Complete |
| S6 | gPTP multi-destination replication | ✅ Complete |
| S7 | Multi-endpoint traffic configuration | ✅ Complete |
| S8 | Integration test (bidirectional, 3 endpoints) | ✅ Complete |

| FRER (IEEE 802.1CB) | Description | Status |
|---------|-------------|--------|
| F1 | Stream replication and DSCP-based recovery, single N3 path (DRB-level transport diversity only) | ✅ Complete |
| F2 | Uplink replication/recovery (device → network) | ✅ Complete |
| F3 | Inter-PDU-session transport diversity (independent N3 paths through two UPFs to the same gNB) | 🔶 Implemented, integration testing in progress |
| F4 | NR dual-connectivity transport diversity (independent gNBs, independent radio channels) | 🔷 In development |

---

## Architecture

### NW-TT (Network-side TSN Translator)

**Module:** `NwTt extends NetworkLayerNodeBase`

The NW-TT is the ingress bridge port (TS 23.501 §5.28.3). It connects the
external TSN network to the UPF.

```
                    NwTt compound module
            ┌──────────────────────────────────────┐
            │                                      │
            │  LayeredEthernetInterface (ethIf)     │
            │  [EthernetStreamingPhyLayer]          │
TSN Switch ◄──►    │                               │
            │      ▼                               │
            │  ethLi (MessageDispatcher)            │
            │      │                               │
            │      ├──► NwTtTranslator (ingress)   │
            │      │    ├─ Data: strip Eth + VLAN, │
            │      │    │  read PCP, set DSCP,     │
            │      │    │  forward to pppIf        │
            │      │    └─ gPTP: detect 0x88F7,    │
            │      │       replicate to endpoints, │
            │      │       L2-in-GTP-U transport   │
            │      │                               │
            │      └──► EthernetEncapsulation       │
            │           (egress: 5GS → TSN)        │
            │              │                       │
            │  PppInterface (pppIf) ──────────────►│◄──► UPF
            └──────────────────────────────────────┘
```

**Key design decisions:**
- Extends `NetworkLayerNodeBase` (same pattern as `Upf.ned`)
- `ethIf` uses `LayeredEthernetInterface` with `EthernetStreamingPhyLayer` (H5)
- `ethLi` MessageDispatcher routes between `ethIf`, translator, and `encap`
- `serviceMapping = {"ethernetmac": "ethIf"}` on `ethLi` for egress routing
- Asymmetric paths: ingress through translator, egress through `encap`
- `encap.registerProtocol = false` to avoid dispatcher conflicts; service
  registered manually on `nl` for IPv4 egress routing
- gPTP frames replicated to all registered downstream devices (S6)
- Dynamic pppIf interface ID lookup via InterfaceTable (H1)
- PCP→DSCP translation is configurable via `mappedPcpValues` (default maps
  all PCP 0–7)

The diagram shows the base configuration. `NwTt` additionally contains a
`udp` module, and three conditional submodules omitted above: `frerReplicator`
(spliced into the downlink path when `frerEnabled`), `frerRecoveryUl`
(spliced into the uplink egress path when `frerUplinkEnabled`), and `pppIf2`
(a second N3 link when `frerInterSession`). See the FRER section below.

### DS-TT (Device-side TSN Translator)

**Module:** `DsTt` (standalone two-port L2 bridge)

The DS-TT is the egress bridge port (TS 23.501 §5.28.4).

```
            DsTt compound module
    ┌─────────────────────────────────────────┐
    │                                         │
    │  LayeredEthernetInterface (ueEth)       │
    │  [EthernetPhyLayer — non-streaming]     │
UE ◄──►    │                                  │
    │      ▼                                  │
    │  ueLi (MessageDispatcher)               │
    │      │                                  │
    │      ▼                                  │
    │  DsTtTranslator                         │
    │   ├─ Data: strip/rebuild Eth frames,    │
    │   │  DSCP→PCP mapping, unicast MAC (H2) │
    │   ├─ gPTP: detect UDP:30001, unwrap,    │
    │   │  residence time + correctionField   │
    │   └─ Reverse: TSN→UE forwarding         │
    │      │                                  │
    │      ▼                                  │
    │  tsnLi (MessageDispatcher)              │
    │      │                                  │
    │      ▼                                  │
    │  LayeredEthernetInterface (tsnEth)       │
    │  [EthernetStreamingPhyLayer]            │
    │──►                                      │◄──► TSN Device B
    └─────────────────────────────────────────┘
```

**Key design decisions:**
- `tsnEth` uses streaming PHY (matches TSN Device B's streaming PHY)
- `ueEth` uses non-streaming `EthernetPhyLayer` (faces the UE's plain
  `EthernetInterface` with `EthernetMacPhy`)
- `tsnLi` and `ueLi` MessageDispatchers with `serviceMapping` for routing
- `DispatchProtocolReq` + `DirectionTag` set on outgoing packets
- FCS value `0xC00DC00D` for `LayeredEthernetInterface` compatibility
- `registerProtocol(Protocol::ethernetMac)` on both gate pairs

As with `NwTt`, the diagram shows the base configuration: `DsTt` also holds
an `interfaceTable` and two conditional submodules on the UE-facing path —
`frerRecovery` (when `frerEnabled`) and `frerReplicatorUl` (when
`frerUplinkEnabled`).

### TSN AF (Application Function)

**Module:** `TsnAf` (3GPP TS 23.501 §5.28.2)

```
        TSN AF
    ┌─────────────────────────────────────┐
    │  Live Bridge Monitoring             │
    │  ├─ Subscribes to DS-TT residence   │
    │  │  time signal                     │
    │  ├─ Publishes delay min/max/avg     │
    │  └─ Detects QoS violations          │
    │                                     │
    │  CNC Configuration (from XML)       │
    │  ├─ Stream reservations             │
    │  └─ TAS gate control lists          │
    │                                     │
    │  API                                │
    │  ├─ getQfiForPcp() / getPcpForQfi() │
    │  └─ getBridgeDelayMin/Max/Avg()     │
    └─────────────────────────────────────┘
```

### Static BMCA

**Module:** `StaticBmca` (IEEE 802.1AS-2020 §10.3)

```
        Static BMCA
    ┌─────────────────────────────────────┐
    │  Clock Hierarchy                    │
    │  ├─ Grandmaster: tsnDeviceA         │
    │  ├─ Bridge: tsnSwitch               │
    │  ├─ Slaves: tsnDeviceB[0..N]        │
    │  └─ Transparent clock: 5GS bridge   │
    │                                     │
    │  Topology Validation                │
    │  ├─ Single grandmaster check        │
    │  ├─ Missing role detection          │
    │  └─ CorrectionField support check   │
    │                                     │
    │  API                                │
    │  ├─ getGrandmasterInfo()            │
    │  ├─ getNodeRole(moduleName)         │
    │  └─ isTransparentClock(moduleName)  │
    └─────────────────────────────────────┘
```

### QoS Mapping Pipeline

```
TSN Device A (PCP=6 in VLAN tag)
  → NW-TT: strips 802.1Q VLAN tag, reads PCP=6, sets IPv4 DSCP=6
  → UPF TrafficFlowFilter: reads DSCP=6, sets QFI=6
  → GtpUser: carries QFI=6 in GTP-U PDU Session Container
  → gNB SDAP: reads QfiReq(6), selects DRB 1 per drbConfig
  → MAC scheduler: schedules DRB 1 with configured priority
  → UE SDAP: extracts QFI=6 from SDAP header
  → DS-TT: reads IPv4 DSCP=6, maps to PCP=6 via UserPriorityReq
  → TSN Device B receives with original priority
```

### gPTP Transport

Two modes via `*.nwTt.translator.gptpTransportMode`:

**`"gtpu"` (primary):** gPTP frames wrapped in UDP:30001, sent through actual
5GS data plane. Replicated to all registered endpoints (S6). Carries
`GptpResidenceHeader` with ingress timestamp. DS-TT computes residence time
and updates correctionField per message type (Sync/FollowUp separately, H4).

**`"sideband"` (fallback):** Direct OMNeT++ connection with configurable delay.

Set `gptpTransportMode` explicitly in your scenario's `.ini` file — don't
rely on its default.

### IEEE 802.1CB FRER (Frame Replication and Elimination for Reliability)

**Modules:** `FrerReplicator`, `FrerRecovery`

FRER duplicates selected traffic streams at the network edge and
eliminates duplicates at the receiving edge, providing seamless
redundancy without relying on retransmission. In nascTime, replication
happens at the NW-TT (downlink) or DS-TT (uplink), and recovery happens
at the corresponding opposite end.

```
        FrerReplicator                        FrerRecovery
    ┌─────────────────────┐               ┌─────────────────────┐
    │  Eligible streams    │               │  Sequence-window     │
    │  selected by DSCP    │               │  duplicate            │
    │  (frerStreams)        │──── primary ─►│  elimination          │
    │                       │──── replica ─►│  (windowSize,         │
    │  Replica gets its own │               │  windowTimeout)       │
    │  DSCP (replicaDscp)   │               │                       │
    │  and, for path-diverse│               │  Non-FRER streams     │
    │  bindings, a distinct │               │  pass through          │
    │  egress interface     │               │  untouched             │
    └─────────────────────┘               └─────────────────────┘
```

**Transport bindings** (`transportBinding` parameter) control how the
replica is made physically or logically distinct from the primary:

| Binding | Replica path | Diversity |
|---|---|---|
| `drb` | Same N3 path, different DRB/QFI | QoS-level separation only |
| `pduSession` | Independent N3 path, same gNB | Independent PDCP/RLC + independent core-network path |
| `dualConnectivity` | Independent N3 path, independent gNB | Full radio-path diversity — uncorrelated radio-level failures |

**Module names per direction.** Each direction has its own replicator and
recovery submodule, gated by a separate boolean on the enclosing node.
Setting the wrong pair silently leaves that direction unreplicated:

| Direction | Replicator | Recovery | Gating parameters |
|---|---|---|---|
| Downlink (network → device) | `nwTt.frerReplicator` | `dsTt[*].frerRecovery` | `nwTt.frerEnabled`, `dsTt[*].frerEnabled` |
| Uplink (device → network) | `dsTt[*].frerReplicatorUl` | `nwTt.frerRecoveryUl` | `dsTt[*].frerUplinkEnabled`, `nwTt.frerUplinkEnabled` |

A third parameter, `frerInterSession`, instantiates the second PPP interface
(`pppIf2` on `NwTt`, `ppp2` on `NGNodeB`) that the path-diverse bindings route
the replica through. `ExtendedMultiEndpointNetwork` carries it as a
network-level parameter too, where it also gates the second UPF; the
companion `frerDualConn` gates the second gNB.

**Downlink:**

```ini
*.nwTt.frerEnabled = true
*.nwTt.frerReplicator.frerStreams = "7"        # comma-separated DSCP values to replicate
*.nwTt.frerReplicator.replicaDscp = 8          # DSCP assigned to the replica
*.nwTt.frerReplicator.transportBinding = "drb" # "drb" | "pduSession" | "dualConnectivity"

*.dsTt[*].frerEnabled = true
*.dsTt[*].frerRecovery.frerStreams = "7"       # must match the replicator
*.dsTt[*].frerRecovery.replicaDscp = 8         # must match the replicator
*.dsTt[*].frerRecovery.windowSize = 64         # IEEE 802.1CB Annex C recommends 64
*.dsTt[*].frerRecovery.windowTimeout = 0.1s    # resets stale recovery state when idle
```

**Uplink** (as in `simulations/demos/frer_test/frer_uplink.ini`):

```ini
*.dsTt[*].frerUplinkEnabled = true
*.dsTt[*].frerReplicatorUl.frerStreams = "7"
*.dsTt[*].frerReplicatorUl.replicaDscp = 8
*.dsTt[*].frerReplicatorUl.transportBinding = "drb"

*.nwTt.frerUplinkEnabled = true
*.nwTt.frerRecoveryUl.frerStreams = "7"
*.nwTt.frerRecoveryUl.replicaDscp = 8
```

**Path-diverse bindings.** For `pduSession` and `dualConnectivity`, also set
`replicaInterface` to the name of the secondary PPP interface, enable the
second N3 link on both ends, and add a second UPF (and, for
`dualConnectivity`, a second gNB) to your topology:

```ini
*.frerInterSession = true                      # network: adds upf2; NGNodeB: adds ppp2
*.nwTt.frerInterSession = true                 # NwTt: adds pppIf2
*.nwTt.frerReplicator.transportBinding = "pduSession"
*.nwTt.frerReplicator.replicaInterface = "pppIf2"
*.upf2.gtp_user.forceTunnelPeer = "gnb"        # pduSession: same gNB, independent N3
```

For `dualConnectivity`, set the network's `frerDualConn = true` as well to
instantiate the second gNB.

The replicator throws a runtime error if `replicaInterface` is left empty for
either path-diverse binding, or if `transportBinding` is not one of the three
names above.

**Framing.** Both modules take an `ethernetFramed` parameter, preset by the
enclosing NED: `false` where packets are bare IPv4 (NW-TT downlink
replication) and `true` where they carry Ethernet framing (everywhere else).
Scenarios do not normally need to set it.

---

## File Inventory

### Source modules (`src/nasctime/`)

All sources live under `src/nasctime/`, mirroring the `nasctime` NED package
root — the same convention Simu5G uses for `src/simu5g/`. The project builds
as a shared library, `src/libnasctime.so`.

```
src/nasctime/package.ned                 NED package root (package nasctime)

src/nasctime/nodes/NwTt/                 NW-TT (Network-side TSN Translator)
├── NwTt.ned                             Compound module (LayeredEthernetInterface + ethLi dispatcher)
├── NwTtTranslator.ned                   Simple module (L2↔IP + QoS + gPTP replication)
├── NwTtTranslator.h / .cc                C++ implementation
├── GptpSideband.ned / .h / .cc           gPTP sideband delay module (fallback transport)
└── GptpResidenceHeader.msg              Residence time header (auto-compiled)

src/nasctime/nodes/DsTt/                 DS-TT (Device-side TSN Translator) + UE variant
├── DsTt.ned                             Compound module (LayeredEthernetInterface + tsnLi/ueLi dispatchers)
├── DsTtTranslator.ned                   Simple module (L2 forwarder + gPTP + QoS)
├── DsTtTranslator.h / .cc                C++ implementation
└── NRUeDsTt.ned                         NR UE with Ethernet port (extends NrUe)

src/nasctime/nodes/TsnAf/                TSN Application Function + BMCA
├── TsnAf.ned / .h / .cc                  TSN AF (bridge capabilities + CNC config)
└── StaticBmca.ned / .h / .cc             Static BMCA (clock hierarchy)

src/nasctime/nodes/frer/                 IEEE 802.1CB FRER framework
├── FrerReplicator.ned / .h / .cc         Stream replication (DL at NW-TT, UL at DS-TT)
├── FrerRecovery.ned / .h / .cc           Duplicate elimination (DL at DS-TT, UL at NW-TT)
├── FrerSequenceHeader.msg               Per-stream sequence number header (auto-compiled)
├── IFrerTransportBinding.h              Transport-binding interface *and* all four
│                                          implementations in one header:
│                                          DrbTransportBinding, PathDiverseTransportBinding
│                                          (base), PduSessionTransportBinding,
│                                          DualConnTransportBinding
└── NrDcMux.ned / .h / .cc                Dual-connectivity leg multiplexer (F4)

src/nasctime/nodes/nGNodeB.ned           NGNodeB — gNB with a second PPP interface (ppp2)
                                           for FRER inter-session / dual-connectivity
                                           transport diversity
src/nasctime/nodes/NrNicUeDc.ned         NrNicUeDC — UE NIC with a secondary NR leg (F4);
                                           requires the Simu5G fork's Rrc extensions
```

### Simulations (`simulations/demos/`) and Tests (`tests/`)

```
tests/package.ned                        package nasctime.tests
tests/nwtt_test/            NW-TT only baseline (G1)
├── NwTtTestNetwork.ned
├── omnetpp.ini                          configs NwTtBasicTest, NwTtHighLoad, NwTtFading
└── nwtt_ip_config.xml

tests/bridge_test/          Full bridge without gPTP (G1)
├── BridgeTestNetwork.ned
├── omnetpp.ini                          configs FullBridgeTest, FullBridgeWithFading
└── bridge_ip_config.xml

tests/gptp_test/            Full bridge with gPTP + residence time (G2+G3)
├── GptpBridgeTestNetwork.ned
├── omnetpp_gptp.ini                     config GptpBridgeTest
└── bridge_ip_config.xml

tests/qos_test/             QoS + TSN AF + BMCA (G4+G5+G6)
├── qosBridgeTestNetwork.ned
├── omnetpp_qos.ini                      config GptpBridgeTest
├── bridge_ip_config.xml
└── cnc_config.xml

tests/fingerprint/          Fingerprint regression suite (run with `make tests`)
├── fingerprints                         Test runner
├── simulations.csv                      Recorded baselines, one line per scenario
├── updateallfingerprints.sh             Promotes *.UPDATED baselines after a verified change
└── README                               Usage, and the -d (debug library) limitation

simulations/package.ned                  package nasctime.simulations
simulations/demos/multi_endpoint_test/  Multi-endpoint scaling (S1-S8)
├── MultiEndpointNetwork.ned
├── omnetpp_multi.ini                    config MultiEndpointTest
├── multi_ip_config.xml
└── cnc_config.xml

simulations/demos/ext_multiendpoint_test/  Scalability sweep, heterogeneous traffic mix
├── ExtendedMultiEndpointNetwork.ned     Also the network used by every frer_test scenario
├── ex_multi_omnetpp.ini                 Base config (Hetero_N*), included by frer_test
├── omnetpp_sweep.ini                    Scheduler × N sweep
├── multi_ip_config.xml / cnc_config.xml
├── gen_profile_ini.py                   Generates per-N traffic profile fragments
├── profiles/                            Generated fragments (profiles_N*.ini)
├── fading.csv                           Fading trace input
└── analyze_primary.py, parse_results.py, vec_parse.py   Result post-processing

simulations/demos/frer_test/            FRER validation (F1-F4)
├── frer_uplink.ini                      Bidirectional replication/recovery (FrerBidirectional_N1)
├── frer_uplink_dualconn.ini             Uplink DS-TT replication over gNB + gNB2 (FrerUplinkDualConn_N1)
├── analyze_uplink_dualconn.py           Checks both radio legs and NW-TT elimination
├── frer_uplink_dualconn_scalability.ini  2/10-UE uplink FRER load tests
├── analyze_uplink_dualconn_scalability.py Aggregate and per-UE scalability checks
├── frer_intersession.ini                Inter-PDU-session transport diversity (FrerInterSession_N15)
├── frer_dualconn.ini                    NR dual-connectivity transport diversity (FrerDualConn_N15)
├── frer_sweep.ini                       Scheduler × N × FRER-mode evaluation sweep
├── gen_profile_ini.py                   FRER-extended traffic profile generator
└── profiles/                            Generated fragments (plain, _frer_sym, _frer_asym)
```

The `frer_test/` scenarios carry no network NED of their own — each one
`include`s `../ext_multiendpoint_test/ex_multi_omnetpp.ini` and runs on
`ExtendedMultiEndpointNetwork`.

### Helper scripts (`bin/`)

```
bin/nasctime                 Runs a scenario against libnasctime.so (release)
bin/nasctime_dbg             Same, against libnasctime_dbg.so
bin/nasctime-run.sh          Scenario-agnostic opp_run wrapper; passes all args through
bin/run_matrix.sh            Parallel launcher for the full experiment matrix
bin/smoke_test.sh            End-to-end check of the heterogeneous traffic generator
```

`bin/` is added to `PATH` by sourcing `setenv` from the nascTime root; the
launchers resolve NED and library paths from `NASCTIME_ROOT`, `INET_ROOT`
and `SIMU5G_ROOT`.

---

## H5: LayeredEthernetInterface Migration

The NW-TT and DS-TT bridge ports use `LayeredEthernetInterface` with
`EthernetStreamingPhyLayer` for compatibility with TSN features (TAS,
frame preemption, gPTP peer delay measurement).

### Key technical decisions

**Problem:** `LayeredEthernetInterface` extends `NetworkInterface` which uses
`pushPacket()` internally. Direct connection to a plain `cSimpleModule`
(our translators) breaks the gate chain.

**Solution:** `MessageDispatcher` modules (`ethLi`, `tsnLi`, `ueLi`) sit
between each `LayeredEthernetInterface` and the translator. The dispatchers
route packets using protocol registration and `serviceMapping`.

**NW-TT `encap` conflict:** `EthernetEncapsulation` with `registerProtocol=true`
propagates its registration through ALL connected dispatchers, including `ethLi`.
This conflicts with `ethIf`'s own registration. Fix: set `registerProtocol=false`
and manually register the service on `nl` from the translator's `initialize()`.

**PHY asymmetry in DS-TT:** `tsnEth` uses streaming PHY (faces Device B which
also uses streaming). `ueEth` uses non-streaming `EthernetPhyLayer` (faces the
UE's plain `EthernetInterface` with `EthernetMacPhy`).

**Packet tags:** Outgoing packets from the translator to `LayeredEthernetInterface`
require `DispatchProtocolReq`, `DirectionTag(DIRECTION_OUTBOUND)`, and
`PacketProtocolTag(Protocol::ethernetMac)`. FCS must use value `0xC00DC00D`.

---

## Configuration Reference

### Essential .ini parameters

```ini
simtime-resolution = fs
**.arp.typename = "GlobalArp"
*.configurator.addStaticRoutes = true

# NW-TT
*.nwTt.translator.ueAddress = "ue[0]"
*.nwTt.translator.localAddress = "nwTt"
*.nwTt.translator.gptpTransportMode = "gtpu"
*.nwTt.translator.gptpEncapUdpPort = 30001
*.nwTt.ethIf.bitrate = 1Gbps

# NW-TT multi-endpoint registration
*.nwTt.translator.tsnDeviceBAddresses = [ \
    {address: "tsnDeviceB[0]", ue: "ue[0]"}, \
    {address: "tsnDeviceB[1]", ue: "ue[1]"}, \
    {address: "tsnDeviceB[2]", ue: "ue[2]"}]

# UE
*.ue[*].servingNodeId = 0
*.ue[*].nrServingNodeId = 1
*.ue[*].ipv4.forwarding = true

# H5: All TSN nodes use LayeredEthernetInterface with streaming PHY
*.tsnDeviceA.eth[*].typename = "LayeredEthernetInterface"
*.tsnDeviceA.eth[*].phyLayer.typename = "EthernetStreamingPhyLayer"
*.tsnSwitch.eth[*].typename = "LayeredEthernetInterface"
*.tsnSwitch.eth[*].phyLayer.typename = "EthernetStreamingPhyLayer"
*.tsnDeviceB[*].eth[*].typename = "LayeredEthernetInterface"
*.tsnDeviceB[*].eth[*].phyLayer.typename = "EthernetStreamingPhyLayer"
```

### SDAP / DRB configuration

SDAP is enabled per NIC via `hasSdap`, and DRB routing is configured with a
JSON-style `drbConfig` list mapping QFIs to DRB indices:

```ini
*.gnb.cellularNic.hasSdap = true
*.ue[*].cellularNic.hasSdap = true

*.gnb.cellularNic.sdap.drbConfig = [ \
    {"drb": 0, "ue": 2049, "qfiList": [0], "rlcType": "UM"}, \
    {"drb": 1, "ue": 2049, "qfiList": [6], "rlcType": "UM"}, \
    {"drb": 0, "ue": 2050, "qfiList": [0], "rlcType": "UM"}, \
    {"drb": 1, "ue": 2050, "qfiList": [6], "rlcType": "UM"}, \
    {"drb": 0, "ue": 2051, "qfiList": [0], "rlcType": "UM"}, \
    {"drb": 1, "ue": 2051, "qfiList": [6], "rlcType": "UM"}]

*.ue[*].cellularNic.sdap.drbConfig = [ \
    {"drb": 0, "qfiList": [0], "rlcType": "UM"}, \
    {"drb": 1, "qfiList": [6], "rlcType": "UM"}]
```

`ue` fields on the gNB side are NR MacNodeIds, which for UEs declared in
array order start at 2049 by default. Optional per-DRB scheduler QoS
parameters (used by the `QOS_PF` scheduling discipline) are configured
separately via `mac.drbQosConfig`.

### gPTP configuration

```ini
*.tsnDeviceA.hasTimeSynchronization = true
*.tsnDeviceA.gptp.gptpNodeType = "MASTER_NODE"
*.tsnDeviceA.gptp.masterPorts = ["eth0"]
*.tsnDeviceA.gptp.slavePort = ""

*.tsnDeviceB[*].hasTimeSynchronization = true
*.tsnDeviceB[*].gptp.gptpNodeType = "SLAVE_NODE"
*.tsnDeviceB[*].gptp.slavePort = "eth0"
*.tsnDeviceB[*].gptp.masterPorts = []
```

### IP addressing scheme

```
10.0.0.0/24       TSN domain A (tsnDeviceA, tsnSwitch, nwTt.ethIf)
10.0.1.0/24       NW-TT ↔ UPF link
10.0.2.0/24       UPF ↔ gNB link
10.0.3.0/24       Cellular (gNB ↔ UEs)
192.168.1.0/24    UE[0] ↔ DS-TT[0] ↔ TSN Device B[0]
192.168.2.0/24    UE[1] ↔ DS-TT[1] ↔ TSN Device B[1]
192.168.3.0/24    UE[2] ↔ DS-TT[2] ↔ TSN Device B[2]
```

---

## Build Instructions

See [INSTALL.md](INSTALL.md) for the full installation walkthrough,
including the recommended `opp_env` setup and the IDE import steps. This
section is the summary.

### Prerequisites
- OMNeT++ 6.4.0 or later
- INET 4.6.x, built
- Simu5G v1.5.0, built against that INET — **vanilla for everything except
  FRER**. For any scenario under `simulations/demos/frer_test/`, build
  [nascTime's Simu5G fork](https://github.com/MohamedSeliem/Simu5G/tree/nasctime-v1.0)
  (tag `nasctime-v1.0`) instead. See "Which Simu5G do I need?" above.

### Building

nascTime is a standalone OMNeT++ project that consumes INET and Simu5G the
same way Simu5G consumes INET: through the `INET_ROOT` and `SIMU5G_ROOT`
environment variables. There is no hardcoded sibling-directory assumption —
source each project's own `setenv` (OMNeT++, INET, Simu5G, then nascTime),
or pass the paths explicitly:

```bash
cd nascTime-5gtsn
make                                    # regenerates src/Makefile, then builds
make INET_ROOT=/path/to/inet SIMU5G_ROOT=/path/to/simu5g
make MODE=debug                         # debug build, coexists with release
```

`make` refuses to run with a helpful message if either variable is unset or
points somewhere without a `src/` directory. The build product is a shared
library, `src/libnasctime.so` — not a standalone executable.

In the OMNeT++ IDE, import the project and tick `inet` and `simu5g` under
*Properties* → *Project References*; the makemake options come from
`.oppbuildspec`, which the command-line build reads too, so both paths stay
in sync.

### Running a scenario

After sourcing nascTime's `setenv`, the `bin/nasctime` launcher resolves the
NED and library paths for you:

```bash
cd simulations/demos/multi_endpoint_test
nasctime -f omnetpp_multi.ini -c MultiEndpointTest
```

Use `nasctime_dbg` for the debug library. Without `setenv`, invoke the
launcher by path (`../../../bin/nasctime -f omnetpp_multi.ini`) — it still
needs `INET_ROOT` and `SIMU5G_ROOT` exported.

### Running the regression suite

```bash
make tests            # equivalently: cd tests/fingerprint && ./fingerprints
```

The fingerprint baselines in `tests/fingerprint/simulations.csv` cover the
`tests/` scenarios plus `frer_test`/`ext_multiendpoint_test`, so a full pass
requires the Simu5G fork. Baselines are tied to the exact OMNeT++/INET/Simu5G
versions they were recorded with — see `tests/fingerprint/README` for how to
re-record them and for the known debug-library limitation.

---

## Known Limitations

1. **TSN AF TAS gate control** parsed and logged but not programmatically
   applied to TSN Device A's `Ieee8021qTimeAwareShaper`.

2. **Static BMCA** validates topology but does not dynamically reconfigure
   gPTP port roles. INET's `Gptp` module does not support dynamic BMCA.

3. **No dedicated DRB-enabled UE variant.** Multi-DRB QoS is configured on the
   stock `NRUeDsTt` via `cellularNic.hasSdap = true` plus a `drbConfig` list;
   there is no separate `NRUeDsTtDrb` module.

4. **FRER inter-PDU-session transport diversity (F3)** is implemented but
   has not yet completed full end-to-end integration testing across all
   scenario configurations.

5. **FRER NR dual-connectivity transport diversity (F4)** is implemented for
   the two-gNB uplink scenario with the companion Simu5G `feat/uplink-frer`
   branch.

6. **Vanilla Simu5G v1.5.0 is sufficient only for non-FRER features.**
   Earlier versions of this README incorrectly stated no Simu5G source
   modifications were required at all — this was wrong for FRER
   specifically. See "Which Simu5G do I need?" above.

---

## References

- 3GPP TS 23.501 §5.28 — 5G-TSN integration architecture
- 3GPP TS 23.501 §5.28.2 — TSN Application Function (TSN AF)
- 3GPP TS 23.501 §5.28.3 — NW-TT functionality
- 3GPP TS 23.501 §5.28.4 — DS-TT functionality
- 3GPP TS 29.281 §5.2.1 — GTP-U PDU Session Container
- IEEE 802.1AS-2020 — Timing and Synchronization for TSN
- IEEE 802.1AS-2020 §10.3 — Best Master Clock Algorithm (BMCA)
- IEEE 802.1AS-2020 §11.2.14.2.3 — Transparent clock correction
- IEEE 802.1Q — VLAN tagging and Priority Code Point (PCP)
- IEEE 802.1Qbv — Time-Aware Shaping (TAS) gate control
