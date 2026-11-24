# M2B-3 — IEEE 802.1Qbv time-aware egress gating in the 5G–TSN bridge

**Status: draft for independent review (step 151).**

- **Branch:** `m2b/tas-qbv-integration`, from `m2/continuation` at `690b5bf` (M2B-2 merged).
- **Stack:** OMNeT++ 6.5.0, INET 4.7.0, unmodified Simu5G 1.8.1.
- **Level:** 2 (functional development tests). There is no scientific acceptance or timing-equivalence claim.

**Unchanged:** INET, Simu5G, the accepted timing components (`TtClock`, `TtGateClock`, the M2-S1 measurement path), the accepted S7.2a INI files and generators, and PR #11. **No C++ is changed in M2B-3.**

## 1. What is integrated

TAS uses INET's native time-aware shaper inside the translators of the existing `M2S72Bridge`, clocked by the accepted `TtGateClock` (M2B-2). It stays **opt-in**: only the test configurations in `simulations/m2/m2b3/tas.ini` enable it.

Module paths, verified in the real topology (tests C4 and T3):

| Element | Path |
|---|---|
| Shaper | `<tt>.eth[p].macLayer.queue` = `Ieee8021qTimeAwareShaper`, when `<tt>.hasEgressTrafficShaping = true`. `<tt>` is `nwTt` or `dsTt[k]`; p = 0 is the 5GS side and p = 1 the TSN side. |
| Classifier | `….queue.classifier` = `PcpTrafficClassClassifier`, mode `both`. At 8 classes INET's default table gives **PCP 0 → TC 1, PCP 1 → TC 0, PCP 2..7 → TC 2..7** (IEEE 802.1Q Table 8-5). Untagged frames (gPTP) → `defaultGateIndex`. |
| Per-class queues | `….queue.queue[0..7]` (`PacketQueue`, FIFO) |
| Gates | `….queue.transmissionGate[0..7]` (`PeriodicGate`), then `transmissionSelection` (`PriorityScheduler`) |
| Clock | `<tt>.clock` = `nasctime.m2.TtGateClock`, reading `<tt>.eth[1].trafficConditionerLayer.ttClock` |
| Gate binding | `<tt>.eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"`. This must be explicit: INET's `*.clockModule` default reaches only direct submodules (M2B-2 C4). |

Traffic in the accepted N = 2 configuration (`M2S72-B-q0-Eall-n2`):
- The listener sends PCP 5 and PCP 0 frames (VID 42, 100 B every 20 ms) to each talker. Each talker sends the same to the listener.
- gPTP runs through every translator.

Hence:
- **DL** frames are gated at the DS-TT TSN port (`dsTt[k].eth[1]`).
- **UL** frames are gated at the NW-TT TSN port (`nwTt.eth[1]`).

## 2. S-CFG/2: the TAS extension of the TSN AF compiler

`simulations/m2/tools/tsnaf_compile.py`, schema `"nasctime-scfg/2"` = S-CFG/1 plus a **required** `tas` section.

S-CFG/1 is preserved:
- An S-CFG/1 specification compiles exactly as before: the accepted `test_tsnaf_compile.py` passes unchanged, 147 / 147, with all 37 compatibility cases byte-identical.
- An S-CFG/1 specification containing `tas` is still refused ("unsupported field 'tas'").
- `nasctime-scfg/2` without `tas` is refused.
- The S-CFG/2 output **begins with the byte-identical S-CFG/1 output** of the same bearer part.

```json
"tas": {
  "untagged_tc": 7,
  "schedules": [
    {"id": "dl-ds-tt", "translator": "ds-tt", "port": "tsn", "cycle_ns": 10000000, "phase_ns": 0,
     "entries": [{"start_ns": 0,       "duration_ns": 2000000, "open": [0, 2, 3, 4, 5, 6, 7]},
                 {"start_ns": 2000000, "duration_ns": 3000000, "open": [0, 2, 3, 4, 6, 7]},
                 {"start_ns": 5000000, "duration_ns": 5000000, "open": [0, 1, 2, 3, 4, 6, 7]}]}
  ]
}
```

| Field | Meaning and validation |
|---|---|
| `untagged_tc` | Traffic class of untagged frames (gPTP). It becomes the classifier's `defaultGateIndex` and **must be open in every entry**. |
| `schedules[].id` | Unique name |
| `translator` | `"nw-tt"`, `"ds-tt"` (every DS-TT) or `"ds-tt[k]"` (k < number of UEs) |
| `port` | `"tsn"` (eth[1]) or `"5gs"` (eth[0]) |
| `cycle_ns` | Integer, 1 µs … 1 s |
| `phase_ns` | Integer in [0, cycle). It is the schedule position at the gate's initialisation, i.e. at the translator TT clock's initial reading C_T(0). Equivalently the base time is C_T(0) − phase in TT time. |
| `entries` | 1 … 256 gate-control entries `{start_ns, duration_ns ≥ 1, open: [traffic classes]}`. The first must start at 0; each starts where the previous ends. Overlaps, gaps, and ends before or after the cycle are refused. A class listed twice or a class outside 0..7 is refused. |
| Cross-checks | **Overlapping schedules** (two schedules on the same translator port, e.g. `ds-tt` and `ds-tt[0]`) are refused. Every declared stream must be transmittable at every scheduled egress port on its path (DL: NW-TT 5gs, DS-TT tsn; UL: DS-TT 5gs, NW-TT tsn). A stream whose class (via the INET PCP mapping) is closed in every entry is refused. |

Emitted, deterministically: translators in the order nw-tt, ds-tt, ds-tt[k]; ports 5gs then tsn; classes 0..7. First, per translator:

```
<P>.hasEgressTrafficShaping = true
<P>.clock.typename = "nasctime.m2.TtGateClock"
<P>.eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"
<P>.eth[*].macLayer.queue.classifier.defaultGateIndex = <untagged_tc>
```

Then, per scheduled port and class, the native `PeriodicGate` parameters `initiallyOpen`, `durations = [… ns]` and `offset = … ns`:
- The durations alternate, starting at a state change of the class (a rotation of the cycle), as `PeriodicGate` requires.
- `offset` = (phase − rotation) mod cycle.
- A class that never changes gets `durations = []`.

INET's `GateControlList` was not used because it has no phase parameter. There is no separate TAS scheduler: INET's gates run the schedule.

The equivalence of the emitted parameters to the declared states is tested against an independent re-implementation of `PeriodicGate` (`initializeGating` / `scheduleChangeTimer`). This covers every entry boundary and midpoint over two cycles, for the committed schedule and for 300 random schedules.

The test schedule `simulations/m2/scfg/s72-q0-tas.json` has the s72-q0 bearer part plus two schedules:

| Port | Cycle | TC5 (PCP 5) | TC1 (PCP 0) | Other classes |
|---|---|---|---|---|
| `ds-tt`, tsn (DL) | 10 ms, phase 0 | open [0, 2) ms | open [5, 10) ms | always open (gPTP in TC7) |
| `nw-tt`, tsn (UL) | 4 ms, phase 1 ms | open [0, 1) ms | open [1, 4) ms | always open |

Its compiler output is committed as `simulations/m2/m2b3/s72-q0-tas.scfg.ini`, and its byte-identity is tested.

## 3. Functional scenarios (`simulations/m2/m2b3/tas.ini`, 0.8 s each)

Every configuration extends the accepted `M2S72-B-q0-Eall-n2`; `m2s72.ini` is included unchanged.

`TAS-common` adds only:
- result paths;
- data-frame PCAP at both ports of the three translators;
- gate and per-class queue vectors;
- `TtClock` parameter recording.

| Config | Purpose |
|---|---|
| TAS-off | A: TAS disabled |
| TAS-open | A′: shaper, `TtGateClock` and explicit binding on, every gate open |
| TAS-gated | B–D: the S-CFG/2 output above (includes `s72-q0-tas.scfg.ini`) |
| TAS-tt | E: as TAS-gated, with dsTt[1]'s `TtClock` at θ0 = +400 µs and y = +200 ppm (5G time updates every 10 ms, as accepted) |
| TASN-unbound | Negative: TAS-tt without the DS-TTs' explicit gate binding |
| TASN-phase | Negative: one gate's phase off by 1 ns |
| TASN-pairer | Investigation: TAS-gated with the accepted M2-S1 egress pairer (`observePort`) left on |

## 4. Oracle and observation

**Independent gate-schedule oracle** (`check/test_m2b3_tas_bridge.py`):
- The schedule comes from the S-CFG/2 JSON, not from the compiled INI.
- Each translator's TT clock comes from the run's recorded `TtClock` parameters. C_T is re-implemented from TtClock.ned in exact integers.
- Gate transition j occurs at t_j = inf{t ≥ t_(j−1) | C_T(t) ≥ c_j}, where c_j = C_T(0) plus the TT offset of the j-th state change after the initial position `phase_ns`. The search runs segment by segment across 5G time-update steps.

**Per-frame observation without the M2-S1 pairer**, using INET's per-class FIFO statistics and PCAP:
- **Enqueue:** `queue[tc].incomingPacketLengths`.
- **Dequeue (transmission start) and holding time:** `queue[tc].queueingTime`; enqueue = dequeue − holding time, checked equal for every frame.
- **Occupancy:** `queue[tc].queueLength`.
- **Transmission end:** the egress-port PCAP (`transmissionEnded`). Identity is (source, destination, PCP, application sequence number) from the payload.

Correlation is k-th dequeue of a class ↔ k-th transmitted frame of that PCP. This is valid because each class queue is FIFO and the port transmits one frame at a time; it is checked by the counts, consecutive sequence numbers, and transmission end = dequeue + (length·8 + 64) bit times.

**Gate opening versus transmission.**
- Eligibility = the enqueue time if the gate is open; otherwise the next opening.
- A frame's dequeue can only follow eligibility. It is later when other frames are ahead of it.
- The PCAP gives the end of the transmission.

## 5. Results (local release stack)

| Suite | Result |
|---|---|
| `test_m2b3_tas_bridge.py` | **60 / 60 PASS** (7 bridge runs plus one run of the unmodified accepted configuration; about 10 s) |
| `test_tsnaf_compile_tas.py` | **54 / 54 PASS** |
| `test_tsnaf_compile.py` (accepted, unchanged) | 147 / 147 PASS; 37 compatibility cases reproduced |

**Default-off and baseline (A).**
- TAS-off and TAS-open are **byte- and time-identical for all 1037 frames** at both ports of the three translators.
- Every gPTP frame (81) is identical in the unmodified accepted run, TAS-off and TAS-gated.
- No accepted configuration, network or generator enables TAS or the gate clock (git grep).
- Both S7.2a generators: IDENTICAL.

**Gates (B–D).** Every transition of TC5 and TC1 at the three gated ports equals the TT-time oracle to the picosecond:

| Port | Transitions per class |
|---|---|
| nwTt | 400 |
| dsTt[0] | 160 |
| dsTt[1] | 160 |

The other gates of these ports, and all eth[0] gates, stay open and bound.

**Frames.** 238 gated-class frames; 176 of them arrived while their gate was closed and were held, the queue staying occupied.

| Port, class | Frames | Held | Released at the opening instant | Longest hold |
|---|---|---|---|---|
| dsTt[0], TC5 / PCP 5 | 25 | 25 | 25 | 4.99891 ms |
| dsTt[0], TC1 / PCP 0 | 25 | 25 | 25 | 4.99891 ms |
| dsTt[1], TC5 / TC1 | 25 / 25 | 25 / 25 | 25 / 25 | ≈ 5 ms |
| nwTt, TC5 / PCP 5 | 70 | 60 | 30 (the rest follow the frame ahead) | 2.99872 ms |
| nwTt, TC1 / PCP 0 | 68 | 16 | 8 | 0.99872 ms |

In every case:
- no frame is dequeued while its gate is closed;
- every transmission ends inside its open window (implicit guard band);
- no frame is lost or reordered within a class;
- on the DS-TT, PCP 5 transmissions start only in TT positions [0, 2) ms and PCP 0 only in [5, 10) ms;
- gPTP (TC7) is never held.

**Example (dsTt[0], listener → talker[0], PCP 5, sequence 0):**

| Event | Time |
|---|---|
| Enqueued (gate closed) | 305.001090 ms |
| Gate opens; frame eligible and dequeued | 310.000000 ms |
| Transmission ends | 310.001040 ms |

The same frame's PCP 0 twin: enqueued at 310.001090 ms, dequeued when TC1 opens at 314.9999995 ms (the DS-TT clock runs at −100 ppb), transmission end at 315.0010395 ms.

**TT time (E).**
- With dsTt[1] at y = +200 ppm and 10 ms updates, its 161 transitions per class equal the TT oracle.
- An ideal clock would differ in 80 of them, by up to 0.4 µs (TC5) and 1.0 µs (TC1), through the rate and the update steps.
- Frames are dequeued only inside the TT-time windows.

**Negative controls.**

| Config | Result |
|---|---|
| TASN-unbound | Without the explicit binding, the DS-TT gates run on simulation time: they equal the ideal-clock oracle and differ from the TT oracle. A missing binding is detected. |
| TASN-phase | A 1 ns phase error of one gate is detected: every changed transition is 1 ns of TT time early, i.e. 1000 or 1001 ps. |
| Compiler negatives | Invalid and overlapping schedules (§2) |

## 6. Egress pairing (B6)

The accepted M2-S1 `TtEgressPairer` requires FIFO order of dequeue and transmission events across the whole port. With per-class queues, a frame of a gated class is overtaken by later frames of an open class.

TASN-pairer shows the result: **`observePort pairing: out-of-order MAC dequeue of tree id 2819: an older record (tree id 3277) lacks this event`** at `nwTt.eth[1]`. The run stops, as the accepted pairer is designed to.

The pairer is not changed. The TAS configurations set `observePort = false` on the gated TSN ports; the ingress tagging and the 5GS-side observers stay as accepted. Correlation uses the non-invasive per-class method of §4. **Full B6 residence observation under TAS (R = t12 − t1 per frame) is deferred.**

## 7. Limitations and next tasks

| Limitation | Next task |
|---|---|
| **Base time.** `PeriodicGate` anchors its cycle on the clock reading at initialisation, so S-CFG/2 `phase_ns` is relative to C_T(0). A constant TT offset θ0 therefore does not shift the cycle; rate, drift and 5G time-update steps do (scenario E). Aligning cycles of different translators to a common TT epoch (802.1Qbv AdminBaseTime) needs C_T(0)-aware anchoring. | B5 |
| **Pairing.** The B6 observer under TAS needs a per-traffic-class pairer, separately enabled with default FIFO, with self-tests under out-of-order dequeue, then the per-frame R signal (M2B-2 §5). | B6 |
| **Scope.** Schedules for two traffic classes on the TSN ports only; 8 classes fixed; no frame preemption or hold/release; no guard-band sizing check against the maximum frame size (INET's implicit guard band holds a frame that cannot finish within its window). | Later |
| **Hosted validation.** Tier-1 compiles only; it has no NED/INI query for these configurations. | Add a reviewed tier-1 `-q runconfig` query for `TAS-gated`, and an individually authorised hosted functional run (DR-15) of `test_m2b3_tas_bridge.py`. |
| **Tier-0 coverage.** `test_tsnaf_compile_tas.py` is pure Python but not in the tier-0 workflow, which is unchanged. | Proposed for inclusion. |
