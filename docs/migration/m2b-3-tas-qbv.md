# M2B-3 — IEEE 802.1Qbv time-aware egress gating in the 5G–TSN bridge

**Status: draft for independent review (step 151; step 152 CI closure and precision: C1 tier-0, C2 configuration check, C3 this wording).**

- **Branch:** `m2b/tas-qbv-integration`, from `m2/continuation` at `690b5bf` (M2B-2 merged).
- **Stack:** OMNeT++ 6.5.0, INET 4.7.0, unmodified Simu5G 1.8.1.
- **Level:** 2 (functional development tests). There is no scientific acceptance or timing-equivalence claim.

**Unchanged:** INET, Simu5G, the accepted timing components (`TtClock`, `TtGateClock`, the M2-S1 measurement path), the accepted S7.2a INI files and generators, and PR #11. **No C++ is changed in M2B-3.**

## 0. What this increment does and does not establish

| # | Statement | Status |
|---|---|---|
| 1 | **IEEE 802.1Qbv-style time-aware gating is functionally demonstrated** on actual Ethernet traffic in the N = 2 5G–TSN bridge. INET's native shaper is driven by each translator's TT clock (via `TtGateClock`) and configured by the S-CFG/2 compiler. Frames of a gated traffic class are held while the gate is closed and transmitted when it opens; gate transitions follow TT time to the picosecond. | **Demonstrated** (local functional tests, §5; level 2) |
| 2 | **A common absolute AdminBaseTime across translators** (every translator's cycle starting at the same TT epoch). The cycle of each port is anchored on its own TT clock reading at initialisation (`phase_ns`, §2), so cycles of different translators are aligned only up to their initial TT readings. | **Not implemented** (B5, §7) |
| 3 | **Full B6 per-frame bridge-residence observation under TAS** (R = t12 − t1 per frame with the M2-S1 path). The accepted FIFO pairer stops under per-class queues (§6). This increment correlates frames per port and class (§4) but measures no bridge residence. | **Not implemented** (B6, §6, §7) |
| 4 | **Evidence classes.** Functional evidence comes from **local** runs on a release build of the same stack versions (OMNeT++ 6.5.0, INET 4.7.0, Simu5G 1.8.1), not from the pinned tier-1 environment. **Hosted CI evidence** is limited to tier-0 (Python suites, now 12 including S-CFG/2) and, if a maintainer applies `tier1:run`, tier-1's build and linkage gates. No hosted run executes the TAS configurations (§8). | See §8 |

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

## 5. Results: local functional evidence (release build, not the pinned tier-1 environment)

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
| **Not implemented: common AdminBaseTime.** `PeriodicGate` anchors its cycle on the clock reading at initialisation, so S-CFG/2 `phase_ns` is relative to C_T(0). A constant TT offset θ0 therefore does not shift the cycle; rate, drift and 5G time-update steps do (scenario E). Aligning cycles of different translators to a common TT epoch (802.1Qbv AdminBaseTime) needs C_T(0)-aware anchoring. | B5 |
| **Not implemented: B6 under TAS.** The B6 observer under TAS needs a per-traffic-class pairer, separately enabled with default FIFO, with self-tests under out-of-order dequeue, then the per-frame R signal (M2B-2 §5). | B6 |
| **Scope.** Schedules for two traffic classes on the TSN ports only; 8 classes fixed; no frame preemption or hold/release; no guard-band sizing check against the maximum frame size (INET's implicit guard band holds a frame that cannot finish within its window). | Later |
| **Hosted validation.** Tier-1 builds and links; it does not resolve the TAS configuration. | The tier-1 extension proposed in §8 (a maintainer decision), and an individually authorised hosted functional run (DR-15) of `test_m2b3_tas_bridge.py`. |
| **Tier-0 coverage.** Done in step 152: `test_tsnaf_compile_tas.py` is the 12th tier-0 suite (§8). | — |

## 8. CI and hosted evidence (step 152)

**Tier-0 (hosted, every PR to `m2/continuation`).** `test_tsnaf_compile_tas.py` is the **12th suite** of `.github/workflows/tier0-python.yml`, added in a separate commit.
- It runs under the same gates as the other 11 suites: exit 0, exact final line, zero non-success counts.
- **Declared expected line: `M2B-3 S-CFG/2 TAS compiler tests: 54 / 54 PASS, 0 FAIL`.**
- The job summary now expects 12 suites.
- The 11 existing suites and their expected lines are unchanged. S-CFG/1 stays `TSN AF compiler tests: 147 / 147 PASS, 0 FAIL; 37 compatibility cases reproduced`.
- The generator checks are unaffected: IDENTICAL.

**Configuration resolution (`simulations/m2/check/check_m2b3_tas_config.py`).** A bounded check of `tas.ini` / `TAS-gated`, with two levels.

The **query level** uses only `opp_run -u Cmdenv -f <ini> -c <config> -r 0 -q runconfig`. That builds no network and runs no simulation, which is the class of query tier-1 already runs.

| Check | What it verifies |
|---|---|
| Q1 | The effective `TAS-gated` entries equal the committed S-CFG/2 fragment: 59 entries, first-match values, multi-line values in full. The M2-S1 pairer is off on the gated TSN ports. |
| Q2 | The accepted `M2S72-B-q0-Eall-n2` has no shaping, gate or gate-clock entry |
| Q3 | `m2s72.ini` and `m2s72s5.ini` equal their committed sha256 |

The **setup level** builds and initialises the network (sim-time-limit 1 ps, parameter recording) and reads the *resolved* module parameters.

| Check | What it verifies |
|---|---|
| S1 | Exactly nwTt, dsTt[0] and dsTt[1] have INET's `Ieee8021qTimeAwareShaper` on both ports, and no other module has one |
| S2 | Each translator's clock is a `TtGateClock` reading its own `TtClock` |
| S3 | All 48 transmission gates are `PeriodicGate`s bound to their own translator's `TtGateClock` |
| S4 | The resolved classifier mapping gives PCP 5 → TC 5 and PCP 0 → TC 1, as the compiler assumes |
| S5 | Every resolved `initiallyOpen` / `durations` / `offset` equals the fragment |

Local results:

| Run | Result |
|---|---|
| `TAS-gated` | **10 / 10 PASS** (query level 4 / 4) |
| Negative `TASN-unbound` | Fails Q1 and S3 |
| Negative `TASN-phase` | Fails Q1 and S5 |

**Tier-1: not extended, proposal only.** Tier-1's real-simulator calls go through an audit shim (`ci/tier1/wrapper/opp_run-audit.sh`). It forwards exactly two argument vectors from one approved working directory and refuses everything else. The verdict requires exactly rows C-1 … C-15, and C-14 forbids simulation markers. Running even the query level therefore changes the accepted tier-1 gates. As instructed, this is reported, not implemented. The smallest change would be:

1. `opp_run-audit.sh`: approve two more vectors.
   - `-u Cmdenv -f tas.ini -c TAS-gated -r 0 -q runconfig`, from `$AUDIT_REPO/simulations/m2/m2b3`. This is a new approved working directory.
   - `-u Cmdenv -f m2s72.ini -c M2S72-B-q0-Eall-n2 -r 0 -q runconfig`, from `$AUDIT_REPO/simulations/m2`.
2. A step after the wrapper suite, inside the same opp_env session and audit setenv. It runs `python3 -I -B simulations/m2/check/check_m2b3_tas_config.py --queries-only` and passes only on the exact line `M2B-3 TAS configuration resolution: 4 / 4 PASS, 0 FAIL (query level 4, setup level 0)`, with the audit showing exactly those two queries.
3. `ci/tier1/py/evaluate.py`: a new row C-16, "M2B-3 TAS configuration resolution (query level)". `final.py` would then require C-1 … C-16 (`range(1, 17)`); add self-tests in `ci/tier1/tests/test_tier1.py` and update the README gate table.

The setup level (S1–S5) builds the network and executes initialisation and events at t ≤ 1 ps. It conflicts with C-14 and stays outside tier-1. It would need a separately authorised hosted development run (DR-15), like the functional suite.

**Evidence classes in this PR:**

| Evidence | Where | Class |
|---|---|---|
| Tier-0: 12 Python suites, including S-CFG/2 (54 / 54) and S-CFG/1 (147 / 147, 37 cases) | GitHub-hosted | Hosted CI |
| Tier-1: pinned release build, linkage, C++ runtime, existing wrapper queries | GitHub-hosted, only if `tier1:run` is applied to the draft | Hosted CI (does not resolve TAS) |
| `check_m2b3_tas_config.py`: 10 / 10 | Local release build | Local configuration evidence |
| `test_m2b3_tas_bridge.py`: 60 / 60 (gating on traffic, oracle, negatives) | Local release build | Local functional evidence (level 2) |
