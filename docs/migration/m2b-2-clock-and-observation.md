# M2B-2 — TAS clock integration and bridge observation foundation

**Status: for independent review (step 147).** The branch is `m2b/tas-observer-foundation`, from `m2/continuation` at `1580a95e8d2ee2b324945b04430a3f9f490a7767` (M2B-1 merged). The stack is OMNeT++ 6.5.0, INET 4.7.0 and unmodified Simu5G 1.8.1.

**Level and scope:**
- level 2 (software validation);
- no scientific-performance or timing-equivalence claim;
- no accepted configuration, generator, evaluator, INET or Simu5G file is changed.

## 1. Clock interfaces compared, and the selected mechanism

| | nascTime `ITtClock` / `TtClock` (M2-S6, model A2) | INET 4.7.0 `IClock` (`ClockBase`, `SettableClock`) |
|---|---|---|
| Purpose | Measures protocol timestamps: `stamp(kind, s, seq)` returns the TT's reading τ of an event at simulation time s | Schedules work in clock time: `scheduleClockEventAt/After`, conversion in both directions, `getClockTime()` |
| Time model | A pure function of simulation time. C_T(s) = s + θ0 + ⌊(2e12·y·(s−u) + D·(s−u)²)/2e21⌋ ps, with u(s) the last 5G time update; a **sawtooth** that steps at every update. White noise w and tick quantisation are applied only to stamps. | A piecewise-monotone, right-continuous C(t). Steps happen only through explicit modification (`setClockTime`), which re-anchors pending events. |
| Inverse (clock → simulation time) | none | required: `computeSimTimeFromClockTime(c, lowerBound)` = inf{t ≥ now \| C(t) ≥ c} (or > c) |
| Events | none: "the module schedules no events" | the clock owns the semantics of pending events; overdue handling is execute, skip or error |
| Invariant 1 (C non-decreasing) | violated at a backward update step | holds between explicit modifications |
| Invariant 2 (`getClockTime()` equals the event's clock time at delivery) | n/a | required; `SettableClock` keeps it for overdue events by a friend-only path |
| Unit | integer ps (`simtime_t::raw()` at ps resolution) | `clocktime_t` = `SimTime` (same raw scale) |

**A. Can `TtClock` implement `IClock`? Not as it stands.** It has no inverse and no event handling, and its steps are not announced. Making it an `IClock` would mean changing the accepted M2-S6 code, which is frozen.

**B. An adapter is preferable.** `TtGateClock`, a new `ClockBase` subclass, *reads* the `TtClock`: its `clockFunction` and its parameters. It adds the inverse, the event bookkeeping and the step handling. `TtClock` and every protocol timestamp stay byte-identical.

**C. Behaviour of gate schedules under offset, drift and correction:**

| Condition | Behaviour |
|---|---|
| Offset θ0 | Gates act at their clock times, hence shifted by −θ0 in simulation time |
| Rate y and drift D | Gate periods are measured in TT time, so the simulation spacing is d / (1 + y + D·Δ) |
| Correction (5G time update) | The step at u_k is applied as INET applies an explicit step:<br>• relative events keep their simulation arrival time;<br>• absolute events (PeriodicGate's default) are re-anchored to the corrected mapping;<br>• events a forward step made overdue are executed at once, in order, each seeing its own clock time, so the gate phase on the clock grid is kept;<br>• or the step raises an error (`overdueClockEventHandlingMode = "error"`).<br>Backward steps delay pending absolute events. |

**D. With TAS disabled, nothing changes.** The adapter exists only where a configuration sets a translator's `clock.typename`. No accepted configuration does (test T-default-off). `TtClock` is unchanged, and the transparent-clock path (`TtSyncIngress` / `TtSyncEgress` / Pdelay) never sees the adapter.

**E. INET's time-aware shaper is reused unmodified.**
- `TsnSwitch` (hence `PassThroughTt`) with `hasEgressTrafficShaping = true` puts an `Ieee8021qTimeAwareShaper` (`PeriodicGate`s) in each port's MAC queue.
- `EthernetSwitch` binds every clock user of the switch through `*.clockModule = default(exists(clock) ? absPath(".clock") : "")`.
- So `clock.typename = "nasctime.m2.TtGateClock"` on a translator drives its gates in TT time with **no INET change and no custom TAS**.

## 2. S-CLK contract (the clock seam)

| Item | Contract |
|---|---|
| Ownership and source | One clock per translator: its `TtClock` (M2-S6 model A2). `TtGateClock` is a read-only view of it. **No second oscillator:** the gate clock is C_T, not a separate model. |
| Location and binding | The translator's switch-level `clock` submodule. `ttClockModule` defaults to `^.eth[1].trafficConditionerLayer.ttClock`, the TSN port's `TtClock`. It must resolve to a `TtClock`; there is no ideal fallback, and a wrong path is an error. INET's `*.clockModule` default binds the gates. |
| Time representation | `clocktime_t` raw = integer ps. `simtime-resolution` must be ps (checked). The arithmetic is the exact `__int128` floor of `TtClock::clockFunction`. It is cross-checked against `TtClock::clockFunction` at initialisation and at every step, so a divergence is an error. |
| What the gate clock includes | C_T: θ0, y, D and the update sawtooth. **Excluded:** stamp noise w (`noiseSigma`) and the tick (`tickLength`), which are measurement effects of protocol timestamps, never fed back into C_T (TtClock.ned). |
| Scheduling against TT time | Between updates, the conversions use the current segment's C_k, extended. The inverse is the generalised inverse of `IClock` (lower: inf{t ≥ now \| C(t) ≥ c}; upper: > c), by exact integer search. |
| Rescheduling when the clock changes | At every update instant u_k (a self-timer at the lowest scheduling priority, so before any other event at u_k): relative events keep their simulation arrival time; absolute events are rescheduled by `computeScheduleTime`; overdue events are executed at once (default) or raise an error. While an event of this clock is handled, `getClockTime()` returns its arrival clock time (IClock invariant 2). |
| Initialisation | `INITSTAGE_LOCAL`: mode, resolution check, `TtClock` resolution, first step timer. The mapping also resolves lazily, so a clock user asking earlier gets the same answer. `INITSTAGE_LAST`: the cross-check against `TtClock`. |
| Parameter limits | \|y\| ≤ 10⁶ ppb and \|D\| ≤ 10⁶ ppb/s, so C stays monotone within a segment; anything else is refused |
| Default-off | No accepted network or configuration instantiates `TtGateClock` |
| Compatibility with S6 | `TtClock` is unchanged; protocol timestamps remain `stamp()`; the gate clock equals C_T exactly (cross-check). With all `TtClock` parameters at their defaults, the gate clock is the simulation time (TG-ideal). |
| Not covered | `skip` overdue handling: a skipped `PeriodicGate` timer would stop the gate. INET debug-mode assertions when C skips the exact arrival picosecond (rate > 1 by ppb; release builds compile `ASSERT` out, and delivery uses the arrival clock time) |

## 3. S-META / S-OBS contract (bridge-delay observation)

**Metadata (S-META), reused unchanged from M2-S0 / S1.**
- `TtTimestampTag`: `ingressTime`, `ingressTtId` and `frameId` are set on the payload region by `TtTimestampLayer` (INET's `measurementLayer` slot) at the **ingress translator's TSN port**, on `receptionEnded`.
- The tag survives the Ethernet PDU session and GTP-U (Simu5G 1.8.1 #309) and is stripped at the egress translator (`stripAtEgress`), so it never reaches a downstream bridge.
- PCP and VID are taken from the frame's 802.1Q tag where present (−1 otherwise).

**Bridge entry and exit.**
- DL: entry at the NW-TT `eth[1]` (`receptionEnded`), exit at the DS-TT `eth[1]` (`transmissionEnded`).
- UL: the reverse.

**Correlation, per frame.** The egress processor with `observePort` pairs each transmission to the enqueued frame by tree id, FIFO order and payload hash (M2-S1 `TtEgressPairer`). The frame identity is (`ingressTtId`, `frameId`).

**Port pair.** (`ingressTtId` → `egressTtId`), plus PCP and VID. A stream identity beyond PCP / VID is not carried in S-CFG/1 frames.

**Quantities (distinct, never mixed):**

| Quantity | Definition | Source |
|---|---|---|
| **Bridge residence R** | t12 − t1: last bit in at the ingress TT's TSN port to last bit out at the egress TT's TSN port (M2-S1; it telescopes into P/Q/G/X at each TT plus the 5G-system block B, with no double counting) | port logs; `bridge_delay.py` |
| 5G-system (wireless) delay B | t8 − t5, between the two TTs' 5G-side ports | M2-S1 decomposition / PCAP |
| End-to-end packet latency | talker to listener application | INET application statistics; not part of S-OBS |
| gPTP correctionField | the TT transparent-clock correction (M2-S5 / S6), written into Follow_Up | the gPTP path; **never** derived from R |

**Absent metadata.** An untagged frame at egress is counted as `untagged` and gives no R; no value is inferred. gPTP frames (EtherType 0x88F7) are counted as `gptp` and never mixed into the data-plane R. A frame tagged by the transmitting TT itself is `not-bridged`.

**No double counting.**
- R is taken once per (frame, egress TT), at the egress TSN port only. A DL frame flooded to N DS-TTs gives N observations, one per port pair.
- The same frame transmitted twice by one egress TT is an error.
- Residence is never summed across TT-level intervals and R.

**Passivity.** The observer reads logs after the run. In-simulation, the M2-S1 instrumentation is default-off and was shown wire-, QoS- and clock-neutral (M2-S1 C12).

**Implemented foundation.** `simulations/m2/tools/bridge_delay.py` is an offline observer over the M2-S1 egress TSN-port logs. It gives per-port-pair / PCP / VID counts and exact-ps min / max / sum / mean, the class counts, and fail-closed checks (R = egressTime − ingressTime, egressTime = tTxEnd, no double count).

## 4. Blockers and constraints found

1. **M2-S1 egress pairing assumes one FIFO (affects B6 under B5).** With `hasEgressTrafficShaping`, `macLayer.queue` is an `Ieee8021qTimeAwareShaper` with per-traffic-class queues and gates. Frames can leave out of enqueue order, and `TtEgressPairer` stops with a pairing error. B6 with TAS needs pairing per traffic class (or by tree id), as a new, separately reviewed default-off path; the M2-S1 pairer stays as accepted.
2. **`ClockEvent` friendship.** Only INET's `ClockBase`, `OscillatorBasedClock` and `SettableClock` may call `ClockEvent::execute()`. The adapter therefore implements "execute overdue" by rescheduling to now and presenting the arrival clock time during handling, not by synchronous execution. The observable gate behaviour is the same (tested); a skip mode is not offered.
3. **Debug builds of INET.** `ClockEvent::execute` asserts arrival == `getClockTime()` *before* the clock handles the event. When C skips the exact arrival picosecond (rate above 1), this assertion would fire in a debug build. Release builds (tier-1, `-DNDEBUG`) are unaffected. Deferred: a rounding policy, as INET's oscillator clocks have.
4. **The TAS gate-control-list source** (S-CFG emission of gate lists from the TSN AF compiler) is not defined yet. It is B5.

## 5. Next implementation tasks

**B5 (TAS / Qbv):**
1. A default-off M2S72Bridge configuration mixin: `*.dsTt[*].hasEgressTrafficShaping = true`, `*.dsTt[*].clock.typename = "nasctime.m2.TtGateClock"`, gate durations per traffic class. Validate with a tier-1 reviewed `-q runconfig` query.
2. Extend the TSN AF compiler (S-CFG/2) to emit `Ieee8021qTimeAwareShaper` gate lists (`transmissionGate[*].durations` / `offset`) from stream windows, with byte-identical regression for configurations without TAS.
3. A gate oracle: recorded `gateState` vectors against the compiler's schedule in TT time (the T-clk oracle generalised to the shaper's gates), with negative controls such as a wrong offset or a missing clock.
4. One individually authorised hosted functional run (DR-15) of the TAS mixin at N = 2: gates open and close as scheduled, R within each gated window. Level 2 only.

**B6 (bridge-delay observer):**
1. Per-traffic-class (or tree-id) egress pairing for shaped ports (blocker 1), default-off, with pairing self-tests under out-of-order dequeue.
2. A runtime signal `bridgeResidence` (R per frame) at the egress processor, with `@statistic` per port pair / PCP, equal to `bridge_delay.py` on the same run (oracle). It is default-off and passive.
3. A PCAP oracle at both TSN ports (as M2-S1 C5) for a shaped configuration.

## 6. Tests

**`simulations/m2/check/test_m2b2_ttgateclock.py`.**
- A functional test. It needs a built stack and is not part of tier-0.
- It runs the test network `simulations/m2/m2b2`: `TtClock` + `TtGateClock` + an unmodified INET `PeriodicGate` (1 ms / 1 ms, 30 ms).
- It compares every recorded `gateState` transition, to the picosecond, with an independent Python oracle of C_T (re-implemented from TtClock.ned) and the IClock step semantics. The oracle is t_j = inf{t ≥ t_(j−1) | C_T(t) ≥ c_j}, searched segment by segment, plus the exact number of changes a forward step makes overdue.

Cases:
- ideal;
- offset;
- rate;
- rate + drift + updates;
- backward steps (7);
- forward steps (6), each crossing a gate change, so 6 overdue executions;
- relative scheduling across steps, equal within 2 ps to the same rate without updates;
- negatives: not a `TtClock`; |y| > 1e6; overdue in `error` mode; simulation-time resolution not ps;
- default-off: a git-grep allowlist.

**Result (local release build, OMNeT++ 6.5.0 / INET 4.7.0):** `M2B-2 TtGateClock tests: 19 / 19 PASS, 0 FAIL`. Mutation checks:

| Mutation | Result |
|---|---|
| No re-anchoring at steps | 16 / 19 |
| No arrival clock time during handling | 17 / 19 |

**`simulations/m2/check/test_bridge_delay.py`** (synthetic M2-S1 port logs, no simulation): `17 / 17 PASS, 0 FAIL`. It is not added to the tier-0 workflow in this change, so the tier-0 suite set is unchanged.
