# M2B-4 — TAS-compatible egress pairing and bridge-residence observation (B6 under TAS)

**Status: draft for independent review (step 154).**

- **Branch:** `m2b/tas-residence-observer`, from `m2/continuation` at `8771095` (M2B-3 merged).
- **Stack:** OMNeT++ 6.5.0, INET 4.7.0, unmodified Simu5G 1.8.1.
- **Level:** 2 (functional development tests). This increment draws **no scientific-performance conclusions**: the residence values below only demonstrate that the observation is correct.

**Unchanged:** INET, Simu5G, the accepted S7.2a INI files and generators, the frozen evaluators, the M2B-3 test configurations (`m2b3/tas.ini` is included unchanged), and the default M2-S1 FIFO behaviour (§4).

**The measurement is unchanged:** R = t12 − t1 (M2-S1), where
- t1 = the last bit received at the ingress translator's TSN port (`receptionEnded`), carried by `TtTimestampTag`;
- t12 = the last bit transmitted at the egress translator's TSN port (`transmissionEnded`).

Under TAS, R includes the time a frame waits behind a closed gate.

## 1. Why the accepted pairer fails under TAS

The M2-S1 observer (`TtTimestampProcessor`, `observePort`) records the following events, and `TtEgressPairer` pairs them by OMNeT++ tree id:

| Event | Where it is taken |
|---|---|
| Enqueue | measurement-layer TX slot, `tSlot` |
| Dequeue | MAC `outboundEmitter`, `packetSentToLower` |
| Transmission start / end | PHY transmitter |

Every rule of the accepted FIFO mode, and its status under TAS:

| FIFO rule (accepted) | Under TAS (per-class queues, gates, strict-priority selection) |
|---|---|
| Every event matches exactly one pending record (orphan, ambiguous) | **Must remain** |
| An event already recorded is a duplicate | **Must remain** |
| Per record: dequeue < start ≤ end; no event before the enqueue | **Must remain** |
| A dequeue must belong to the oldest record lacking a dequeue (port-wide FIFO) | **Invalid across traffic classes.** A frame of an open class legitimately overtakes an older frame held by a closed gate (M2B-3 TASN-pairer: `out-of-order MAC dequeue`). **Still valid within one class:** each class queue is FIFO. |
| A transmission start must belong to the oldest record lacking a start, in enqueue order | **Invalid as stated.** The physical order is the **dequeue order**; that must be enforced. |
| A transmission end must belong to the FIFO head; the processor then checks and removes `fifo.front()` | **Invalid as stated.** It must belong to the frame currently on the wire, and the processor must use the matched record. |
| *(implicit)* one transmission at a time | Not checked explicitly in FIFO mode. **Must be checked** once ordering is relaxed. |
| Payload hash and tag of the transmitted frame equal the enqueued record | **Must remain.** The hash alone **cannot** separate a PCP 5 frame from its PCP 0 twin (identical payload), so a PCP / VID / EtherType check is added in TAS mode. |

## 2. TAS pairing semantics (opt-in)

`TtEgressPairer` has `mode = FIFO` (default) or `TAS`. The parameter is `TtTimestampLayer.pairingMode = "fifo" | "tas"`, and `"tas"` requires `observePort`. In TAS mode the FIFO checks that must remain are unchanged, and:

1. **MAC dequeue:** a record may overtake older records of **other PCPs**, but never an older record of the **same PCP**. The PCP determines the traffic class, so per-class FIFO is enforced at PCP level; at INET's 8 classes, PCP and class are in one-to-one correspondence. No traffic-class table is needed.
2. Each dequeue receives the next position in the port's **transmission sequence** (`dequeueSeq`).
3. **Transmission start:**
   - It must belong to the earliest-dequeued record not yet started ("out-of-sequence").
   - No transmission may start while another is in progress ("overlapping transmission").
4. **Transmission end:**
   - It must belong to the record on the wire.
   - No earlier-dequeued record may still lack its end.
5. **Identity at the end:** the transmitted frame's EtherType, PCP and VID must equal the record (`verifyTransmitted`). The payload-hash and tag checks remain as in FIFO mode.
6. **No repair:** nothing is inferred or repaired. Every violation stops the simulation with `observePort pairing: …`, exactly as in FIFO mode.

**Minimal implementation:**
- `TtEgressPairer`: `matchTas()` and `verifyTransmitted()`, plus one record field `dequeueSeq`. The FIFO body of `match()` is byte-for-byte unchanged and only dispatched away from in TAS mode.
- `TtTimestampProcessor`:
  - parses `pairingMode`;
  - at the transmission end it uses and erases the *matched* record. FIFO mode guarantees that index is 0, the head;
  - adds the TAS identity check;
  - runs TAS self-test cases in TAS mode only.
- `TtTimestampLayer.ned`: one parameter.
- No packet copy and no scheduling change. The observer only listens to signals, as in M2-S1.

## 3. Bridge integration (`simulations/m2/m2b4/residence.ini`, test-only)

The file includes `../m2b3/tas.ini` unchanged; that file includes the accepted `m2s72.ini` unchanged.

| Config | Content |
|---|---|
| RES-off | M2B-3 TAS-off: the accepted configuration, TAS disabled, FIFO pairing |
| RES-tas | M2B-3 TAS-gated (N = 2, PCP 5 and PCP 0 in both directions, S-CFG/2 schedule). **`observePort = true` restored** on the gated TSN ports; `pairingMode = "tas"` at every shaped port. The 5GS-side ports are shaped too, with priority selection, so they can also reorder. |
| RESN-fifo | Negative: RES-tas with FIFO pairing |
| RESN-rotate | Negative: M2-S1 TEST-ONLY `pairingTest = "rotate"`, which writes each row with the previous row's identity |
| RESN-offset | Negative: M2-S1 TEST-ONLY `timestampOffset = 1ns` at the NW-TT TSN port (wrong t1 for DL frames) |

## 4. Tests and evidence

### 4.1 Source validation (no simulation)

**`check/test_m2b4_pairer.py`: 33 / 33 PASS.** It builds `m2b4/pairer_test.cc` with the repository's `TtEgressPairer.cc` outside the repository.

The **FIFO** cases (11):
- the 10 accepted M2-S1 self-test cases, with unchanged outcomes;
- the cross-class overtaking that FIFO refuses (the M2B-3 failure).

The **TAS** cases (22). Valid sequences:
- cross-class overtaking;
- gPTP overtaking held data;
- back-to-back transmission;
- FIFO order;
- a matching identity.

Negative controls, each failing with its intended message:

| Negative control | Error |
|---|---|
| Within-class overtaking | `… within PCP 5` |
| Orphan dequeue / orphan end | `orphan …` |
| Duplicate dequeue | `duplicate MAC dequeue` |
| Duplicate transmission end (record removed, or still pending) | `orphan transmissionEnded` / `duplicate transmissionEnded` |
| Ambiguous tree id (at enqueue, or two pending records) | `ambiguous …` |
| Start before dequeue | `no MAC dequeue yet` |
| Missing transmission start | `no transmission start yet` |
| Impossible overlapping transmissions | `overlapping transmission` |
| Start out of the dequeue sequence | `out-of-sequence` |
| Dequeue before enqueue; end before start | `time order violation` |
| Incorrect frame identity (PCP twin, or VID) | `identity of the transmitted frame … differs` |

The same driver also passes under clang AddressSanitizer and UBSan (`-fno-sanitize-recover=all`).

### 4.2 Local simulation evidence (release build, not hosted)

**Default FIFO unchanged.** The accepted `M2S72-B-q0-Eall-n2` (`observePort` on at all translator ports, FIFO, 0.8 s) was run with the library of the base commit `8771095` and with this branch's library. The results are identical:
- **all 56 output files byte-identical**: 12 M2-S1 port logs, M2-S1 frame logs, PCAPs, gPTP monitor and Pdelay logs;
- **all 2812 scalars identical**, including the in-simulation pairer self-test (10 / 10).

**`check/test_m2b4_residence.py`: 21 / 21 PASS.**

| Check | Result |
|---|---|
| Pairing | RES-tas completes with TAS pairing at all 6 shaped ports. No frame is left pending. The in-simulation self-tests at the NW-TT TSN port (where the accepted configuration enables them) pass: FIFO 10 / 10, TAS 6 / 6. **12 valid cross-class overtakings** occur and are accepted, **none within a PCP**. RESN-fifo refuses the same run with `out-of-order MAC dequeue`. |
| Passive observation | RES-tas against M2B-3 TAS-gated (observation off): every frame at both ports of the 3 translators (1037, gPTP included) is identical in bytes, time and order. The 1488 gate transitions are identical. The TT protocol timestamps (TtClock stamp logs) are identical. gPTP frames, and therefore their correction fields, are identical. |
| Independent oracle, RES-tas | For **all 238 bridged frames** (next table) |
| Independent oracle, RES-off | The same verification for all 238 bridged frames with TAS disabled (FIFO pairing) |
| Gate wait | **176** frames arrived while their gate was closed. Their R contains the gate wait: R ≥ held time + transmission time. |
| TAS on vs off | The same 238 frames are observed. All 238 reach the egress queue at the same instant in both runs, and for every one **R_on − R_off equals the gate-induced queueing-time difference exactly**. No claim is made about delay distributions in general. |
| Statistics | `bridge_delay.py` (unchanged) gives 8 groups (ingress TT, egress TT, PCP, VID): residence 238, gPTP 29, untagged 0, not-bridged 0. Count, min, max and sum equal the oracle's. |
| Negatives in the real bridge | RESN-rotate: 100 identity / t1 mismatches found by the oracle. RESN-offset: exactly the 100 DL frames refused for a wrong t1; the UL frames pass, and `bridge_delay.py` alone cannot see it, since the log is internally consistent. On mutated real logs: duplicate egress observation and t1 after t12 are refused by `bridge_delay.py`; a missing ingress tag is counted as `untagged` with no R inferred. |

For every bridged frame in RES-tas, the oracle checks, from sources that never include the pairer's output:
- egress translator and TSN port, PCP, VID, EtherType, payload hash, and identity (source, destination, PCP, VID, application sequence number) from the wire;
- the byte-identical frame received at the ingress translator's TSN port;
- **t1 = PCAP reception end there**;
- **t12 = PCAP transmission end**;
- **R = t12 − t1 equal to the logged R to the ps**;
- transmission start = t12 − (L·8 + 64) bit times;
- enqueue and dequeue equal INET's per-class queue statistics;
- dequeued only with its gate open (TT-time gate oracle);
- counted exactly once; residence rows = data frames on the wire.

Observed values, for illustration only:

| Path | R, TAS off | R, TAS on | Frames held |
|---|---|---|---|
| DL (NW-TT → DS-TT), every flow | ≈ 5.0 ms | ≈ 10.0 ms | every frame (DS-TT schedule: TC5 open 2 / 10 ms, TC1 open 5 / 10 ms) |
| UL PCP 5 | 6.0 – 20.0 ms | 7.0 – 23.0 ms | 30 of 35 per flow |
| UL PCP 0 | 7.0 – 47.0 ms | identical to TAS off | 8 of 34 per flow |

**Example frame** (DS-TT[0], listener → talker[0], PCP 5, VID 42, sequence 0):

| Event | Time |
|---|---|
| t1 | 300.001090 ms |
| Enqueued (gate closed) | 305.001090 ms |
| Dequeued and transmission starts | 310.000000 ms (the gate opens) |
| t12 | 310.001040 ms |

R = 9.999950 ms = R_off 5.001040 ms + 4.998910 ms of gate hold.

### 4.3 Regression (local)

| Suite | Result |
|---|---|
| 12 tier-0 suites, through the workflow's own runner | 12 / 12 PASS |
| `m2s72_gen.py` / `m2s72s5_gen.py` check | IDENTICAL |
| M2B-2 TtGateClock | 43 / 43 |
| M2B-2 bridge-delay | 33 / 33 |
| M2B-2 topology | 9 / 9 |
| M2B-3 S-CFG/2 compiler | 54 / 54 |
| M2B-3 TAS functional | 60 / 60 |
| M2B-3 configuration resolution | 10 / 10 |

The M2-S1 campaign checker `check_m2s1.py` was not re-run: it evaluates a full M2-S1 campaign (10 repetitions per configuration, older stack). The pairer's FIFO behaviour is covered instead by the 10 accepted self-test cases (unit and in-simulation) and the byte-identical default run above.

### 4.4 Hosted CI

- **Tier-0** runs the 12 Python suites. This increment adds no tier-0 suite: its tests need a built stack.
- **Tier-1** (if a maintainer applies `tier1:run` to the draft) builds and links `libnasctime_m2` with the changed sources. It does not run the observer or the bridge.
- **No hosted run executes the M2B-4 configurations.**

## 5. Limitations

- **Per-class FIFO at PCP level.** With fewer than 8 traffic classes, several PCPs share a class. The check is then necessary but not sufficient (a reordering between two PCPs of one class would not be caught). The bridge uses 8 classes.
- **Not covered:** frame preemption (802.1Qbu), aborted transmissions (refused as in M2-S1), and frames dropped by a shaped queue (refused as in M2-S1).
- **Self-tests.** The in-simulation pairer self-tests run where the accepted configuration enables them (the NW-TT TSN port). The full TAS case set runs as unit tests (§4.1).
- **Common AdminBaseTime across translators** remains not implemented (B5, M2B-3 §7). The gate phase is anchored on each translator's initial TT reading.
- **Hosted evidence.** The functional and residence results are local only (§4.4).
