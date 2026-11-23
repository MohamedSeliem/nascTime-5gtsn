# M2B-2 — TAS clock integration and bridge observation foundation

**Status: for independent review (step 147; step 148 targeted corrections C1–C4).** The branch is `m2b/tas-observer-foundation`, from `m2/continuation` at `1580a95e8d2ee2b324945b04430a3f9f490a7767` (M2B-1 merged). The stack is OMNeT++ 6.5.0, INET 4.7.0 and unmodified Simu5G 1.8.1.

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
- `EthernetSwitch` sets `*.clockModule = default(exists(clock) ? absPath(".clock") : "")`. **Corrected in step 148 (C4):** that default reaches only the switch's *direct* submodules. The shaper's gates (`eth[*].macLayer.queue.transmissionGate[*]`, four levels down) keep `clockModule = ""`, meaning simulation time. This was verified in the real M2S72Bridge topology (test C4-tas-unbound).
- So the binding needs two INI entries per translator and **no INET change and no custom TAS**: `clock.typename = "nasctime.m2.TtGateClock"` and `eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"`. The second is the binding INET's own TSN showcases use (`gptpandtas`, `invehicle`, `clockdrift`). Test C4-tas verifies it.

## 2. S-CLK contract (the clock seam)

| Item | Contract |
|---|---|
| Ownership and source | One clock per translator: its `TtClock` (M2-S6 model A2). `TtGateClock` is a read-only view of it. **No second oscillator:** the gate clock is C_T, not a separate model. |
| Location and binding | The translator's switch-level `clock` submodule. `ttClockModule` defaults to `^.eth[1].trafficConditionerLayer.ttClock`, the TSN port's `TtClock`. It must resolve to a `TtClock`; there is no ideal fallback, and a wrong or missing path stops with "is not a nasctime::TtClock". The shaper gates are bound explicitly: `<translator>.eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"` (§1 E, step 148 C4). In M2S72Bridge, each translator has 8 gates on each of its two Ethernet ports: eth[0] on the 5GS side and eth[1] on the TSN side. |
| Time representation | `clocktime_t` raw = integer ps. `simtime-resolution` must be ps (checked). The arithmetic is the exact `__int128` floor of `TtClock::clockFunction`. It is cross-checked against `TtClock::clockFunction` at initialisation and at every step, so a divergence is an error. |
| What the gate clock includes | C_T: θ0, y, D and the update sawtooth. **Excluded:** stamp noise w (`noiseSigma`) and the tick (`tickLength`), which are measurement effects of protocol timestamps, never fed back into C_T (TtClock.ned). |
| Scheduling against TT time | Between updates, the conversions use the current segment's C_k, extended. The inverse is the generalised inverse of `IClock` (lower: inf{t ≥ now \| C(t) ≥ c}; upper: > c), by exact integer search. |
| Picosecond semantics (step 148, C2) | C_T can advance by more than 1 ps per simulated ps (rate above 1) and jumps at forward steps. A simulation instant t therefore covers the clock interval (C(t−1), C(t)]: an event at clock time c fires at t = inf{t ≥ now \| C(t) ≥ c}, and C(t−1) < c ≤ C(t).<br>• `computeClockTimeFromSimTime(t, lowerBound=true)` = min(C(t−1)+1, C(t)), with C(t−1) from the segment in force at t−1 (so at a step instant the pre-step segment); `lowerBound=false` = C(t). This is IClock invariant 5.<br>• `getClockTime()` returns the arrival clock time of the clock event being executed. That runs from `ClockEvent::execute()`, where INET checks invariant 2 before the clock sees the event, to the end of its handling. The event is recognised through public interfaces only: one of this clock's events, due now, and already off the future event set (`!isScheduled()`). Otherwise `getClockTime()` = C(now).<br>• Clock events due at the same instant are kept in arrival-clock-time order (within equal scheduling priority), so the presented clock time does not go back between them.<br>• Within one instant a clock event can present a clock time below C(t), by at most the clock's advance in that picosecond, or by the step size at a forward step. This is the same presentation INET's `SettableClock` gives an overdue event in EXECUTE mode. |
| Rescheduling when the clock changes | At every update instant u_k (a self-timer at the lowest scheduling priority, so before any other event at u_k): relative events keep their simulation arrival time; absolute events are rescheduled by `computeScheduleTime`; **Overdue** means a clock time jumped over by the forward step: C_old(u) < c < C_new(u). Such events are rescheduled to u and delivered there in clock-time order, each presenting its own clock time, including the events scheduled while catching up. This is the `SettableClock` EXECUTE semantics without its friend-only synchronous path. In `error` mode they raise an error. |
| Initialisation | `INITSTAGE_LOCAL`: mode, resolution check, `TtClock` resolution, first step timer. The mapping also resolves lazily, so a clock user asking earlier gets the same answer. `INITSTAGE_LAST`: the cross-check against `TtClock`. |
| Parameter limits | \|y\| ≤ 10⁶ ppb and \|D\| ≤ 10⁶ ppb/s; anything else is refused. |
| Range and monotonicity (step 148, C3) | C_u is non-decreasing for s − u ≤ span, where span = ⌊(⌊(2e21 + 2e12·y)/\|D\|⌋ − 1)/2⌋ + 1 for D < 0 (from 2e12·y + D·(2dd+1) ≥ −2e21), and is unbounded for D ≥ 0. With \|D\| = 10⁶ the span is 1000 s.<br>• An update interval longer than the span is refused at initialisation.<br>• A query beyond the span (free-running with D < 0) is a `cRuntimeError`, as is a clock or simulation time outside the int64 `clocktime_t` / `simtime_t` range.<br>• C is evaluated in 128-bit arithmetic.<br>• The expanding inverse search never probes beyond min(span end, max simtime), so it cannot overflow.<br>• Targets at or below C(now), including negative ones and INT64_MIN, map to now.<br>• A target not reached within the range is an error, never a wrapped or non-monotone result. |
| Default-off | No accepted network or configuration instantiates `TtGateClock` |
| Compatibility with S6 | `TtClock` is unchanged; protocol timestamps remain `stamp()`; the gate clock equals C_T exactly (cross-check). With all `TtClock` parameters at their defaults, the gate clock is the simulation time (TG-ideal). |
| Not covered | `skip` overdue handling (a skipped `PeriodicGate` timer would stop the gate). Clock events of *different scheduling priorities* due at the same instant follow the future-event-set order, not clock-time order. Lifetime: as with INET's `SettableClock`, a clock event must be cancelled through the clock before it is deleted. |

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

**Time parsing (step 148, C1).**
- Every time must be an exact, finite decimal number of picoseconds within the `simtime_t` range. There is no rounding.
- Each of the following is a controlled error (CLI: exit 1, nothing on stdout, no traceback): a fractional picosecond; NaN or Infinity; a non-decimal spelling (whitespace, `_`, `+`, hex); an out-of-range value; an undecodable or malformed CSV.
- Extreme exponents are rejected without evaluating large powers.

## 4. Blockers and constraints found

1. **M2-S1 egress pairing assumes one FIFO (affects B6 under B5).** With `hasEgressTrafficShaping`, `macLayer.queue` is an `Ieee8021qTimeAwareShaper` with per-traffic-class queues and gates. Frames can leave out of enqueue order, and `TtEgressPairer` stops with a pairing error. B6 with TAS needs pairing per traffic class (or by tree id), as a new, separately reviewed default-off path; the M2-S1 pairer stays as accepted.
2. **`ClockEvent` friendship.** Only INET's `ClockBase`, `OscillatorBasedClock` and `SettableClock` may call `ClockEvent::execute()`. The adapter therefore implements "execute overdue" by rescheduling to the step instant in clock-time order, not by synchronous execution. The observable gate behaviour is the same (tested, also with INET assertions on). A skip mode is not offered.
3. **Debug builds of INET: resolved in step 148 (C2), without relying on `NDEBUG`.** The PR #13 version (`c1a0d7d`) did violate the IClock contract. In a debug INET build it fails `ASSERT getArrivalClockTime() == clockTime` (invariant 2) at the first overdue gate change of TG-step-fwd. It also fails `checkScheduledClockEvent` invariant 5 when an event is scheduled at a clock picosecond that C skips. The corrected adapter (§2, picosecond semantics) uses public INET interfaces only. It passes the whole functional suite with `DEBUG_CHECK_IMPLEMENTATION` and `ASSERT` enabled (§6).
4. **The TAS gate-control-list source** (S-CFG emission of gate lists from the TSN AF compiler) is not defined yet. It is B5.
5. **Gate binding is not implicit (step 148, C4).** Enabling `hasEgressTrafficShaping` and the clock slot alone leaves the gates on simulation time, with no error. Every B5 configuration must carry the explicit gate binding of §1 E, and its gate oracle must include a negative control with the binding missing.

## 5. Next implementation tasks

**B5 (TAS / Qbv):**
1. A default-off M2S72Bridge configuration mixin containing:
   - `*.dsTt[*].hasEgressTrafficShaping = true`;
   - `*.dsTt[*].clock.typename = "nasctime.m2.TtGateClock"`;
   - `*.dsTt[*].eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"`;
   - gate durations per traffic class.

   Validate it with the C4 binding check (`test_m2b2_topology.py`) and a tier-1 reviewed configuration query.
2. Extend the TSN AF compiler (S-CFG/2) to emit `Ieee8021qTimeAwareShaper` gate lists (`transmissionGate[*].durations` / `offset`) from stream windows, with byte-identical regression for configurations without TAS.
3. A gate oracle: recorded `gateState` vectors against the compiler's schedule in TT time (the T-clk oracle generalised to the shaper's gates), with negative controls such as a wrong offset or a missing clock.
4. One individually authorised hosted functional run (DR-15) of the TAS mixin at N = 2: gates open and close as scheduled, R within each gated window. Level 2 only.

**B6 (bridge-delay observer):**
1. Per-traffic-class (or tree-id) egress pairing for shaped ports (blocker 1), default-off, with pairing self-tests under out-of-order dequeue.
2. A runtime signal `bridgeResidence` (R per frame) at the egress processor, with `@statistic` per port pair / PCP, equal to `bridge_delay.py` on the same run (oracle). It is default-off and passive.
3. A PCAP oracle at both TSN ports (as M2-S1 C5) for a shaped configuration.

## 6. Tests

**Stack used locally.** OMNeT++ 6.5.0, INET 4.7.0 (unmodified, pinned tarball) and Simu5G 1.8.1 (unmodified), each built in release mode. OMNeT++ and INET were also built in **debug** mode (`make MODE=debug`). The debug builds have no `NDEBUG`, so INET's `ASSERT` and `DEBUG_CHECK_IMPLEMENTATION` (the IClock invariant checks in `ClockEvent::execute` and `ClockBase::checkScheduledClockEvent`) are active.

**`simulations/m2/check/test_m2b2_ttgateclock.py`.** A functional test that needs a built stack and is not part of tier-0.
- `M2B2_MODE=release` (default) or `debug`. The debug variant of `libnasctime_m2` is built by `simulations/m2/m2b2/build_debug.sh`.
- It builds the test-only probe library (`simulations/m2/m2b2/probe/`) outside the repository.

**Gate tests (T-clk).**
- They run the test network TtGateClockTest: `TtClock` + `TtGateClock` + an unmodified INET `PeriodicGate` (1 ms / 1 ms, 30 ms).
- Every recorded `gateState` transition is compared, to the picosecond, with an independent Python oracle of C_T (re-implemented from TtClock.ned) and the IClock step semantics.
- The oracle is t_j = inf{t ≥ t_(j−1) | C_T(t) ≥ c_j}, searched segment by segment. It also gives the exact number of changes a forward step jumps over: C_old(u) < c_j < C_new(u).
- Cases:
  - ideal;
  - offset;
  - rate;
  - rate + drift + updates;
  - backward steps (7);
  - forward steps (6), each jumping over a gate change, so 6 overdue deliveries;
  - relative scheduling across steps, equal within 2 ps to the same rate without updates;
  - negatives: not a `TtClock`; |y| > 1e6; overdue in `error` mode; resolution not ps;
  - default-off: a git-grep allowlist.

**Probe tests (T-inv, T-c2; step 148, C2 / C3).**
- They run the test network TtGateClockProbeTest. The probe calls the public IClock interface at chosen instants, and every result is compared with an oracle of the §2 contract.
- `P-rate-pos` / `P-rate-neg` (y = ±1e6):
  - targets INT64_MIN, negative, C(now), +1, +2, +1000, 2^62 and INT64_MAX;
  - simulation times up to the maximum simtime;
  - this covers overflow, the clocktime range and "not reached".
- `P-drift-neg` (D = −1e6, no updates): the 1000 s monotone span; a target beyond C at the span end, and a time beyond the span, are errors.
- `P-step-fwd` / `P-step-back`: queries at u−1, u and u+1 around a step, covering the lower and upper bound at the step instant and the extended old segment before it.
- `P-skip`: two clock events at a clock picosecond that C skips (C(t)−1 and C(t)), scheduled in reverse clock order. They must be delivered at t in clock-time order, each with `getClockTime()` == its arrival clock time.
- `PN-interval` (negative): an update interval longer than the monotone span is refused.

**Results (local).**

| Run | Result |
|---|---|
| Release | `M2B-2 TtGateClock tests (release): 34 / 34 PASS, 0 FAIL` |
| Debug, assertions on | `M2B-2 TtGateClock tests (debug): 34 / 34 PASS, 0 FAIL` |
| PR #13 adapter (`c1a0d7d`) under debug, for comparison | TG-ideal passes. TG-step-fwd stops with `ASSERT: Condition 'getArrivalClockTime() == clockTime' does not hold … ClockEvent.cc:25` (invariant 2, first overdue change). P-skip stops with `checkScheduledClockEvent` invariant 5 (`0.000000002001 >= 0.000000002002`). |

**Mutation checks.**

| Mutation | Result |
|---|---|
| No re-anchoring at steps (PR #13 version) | 16 / 19 |
| No arrival clock time during handling (PR #13 version) | 17 / 19 |
| No executing-event lookup in `getClockTime()` (debug) | 30 / 34 |
| No same-instant clock-time ordering (release) | 33 / 34 |

**`simulations/m2/check/test_m2b2_topology.py`** (step 148, C4).
- Real-topology binding in M2S72Bridge. The test-only `simulations/m2/m2b2/topology.ini` includes `m2s72.ini` unchanged and extends the accepted `M2S72-B-q0-Eall-n2` (N = 2; A2 `TtClock` in each translator's TSN port).
- `sim-time-limit = 1ps`: network set-up and initialisation only. The binding is read from the recorded parameters.

Cases:

| Case | What it shows |
|---|---|
| C4-clock | One adapter per translator, each reading its own translator's TSN-port `TtClock` (the adapter's cross-check passes). With shaping off, no clock user is bound to it. |
| C4-tas-unbound | With shaping on, 48 gates (16 per translator) all have an empty `clockModule`. INET's default does not bind them. |
| C4-tas | With the explicit binding, all 48 gates resolve to their own translator's adapter. |
| C4N-no-ttclock | The accepted configuration without TT clocks stops with "is not a nasctime::TtClock". |

**Result:** `M2B-2 topology binding tests: 9 / 9 PASS, 0 FAIL` (release stack, including Simu5G 1.8.1).

**`simulations/m2/check/test_bridge_delay.py`** (synthetic M2-S1 port logs, no simulation): `33 / 33 PASS, 0 FAIL`. That is the 17 previous checks plus 16 strict-parsing checks (C1). It is not added to the tier-0 workflow, so the tier-0 suite set is unchanged.
