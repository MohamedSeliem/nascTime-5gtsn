# M2B-5 — Common-epoch TAS schedule alignment

**Status: draft for independent review (step 156; step 157 debug-assertion validation, §5.5).**

- **Branch:** `m2b/tas-common-basetime`, from `m2/continuation` at `9781291` (M2B-4 merged).
- **Stack:** OMNeT++ 6.5.0, INET 4.7.0, unmodified Simu5G 1.8.1.
- **Level:** 2, a functional-development milestone.

**What this shows.** Several translators can evaluate an S-CFG/2 gate schedule relative to one common TT-time epoch while existing behaviour is preserved.

**What this does not show:**
- clock synchronization accuracy;
- cross-translator schedule feasibility;
- bounded worst-case latency;
- IEEE 802.1Qbv conformance.

**Unchanged:** INET, Simu5G, `TtClock`, `TtGateClock`, the M2-S1 / M2B-4 observer, the accepted S7.2a INI files and generators, the frozen evaluators, and the M2B-3 / M2B-4 test configurations.

## 1. Target semantics

For a common-epoch schedule (cycle T, entries, base time b) at a translator whose accepted TT clock is C_T:

**position(t) = (C_T(t) − b) mod T**

The gate state is that of the declared entry covering the position; entries are half-open, [start, start + duration).

A common base time does **not** mean the translators' clocks are synchronized. Each translator evaluates the schedule on its own C_T, with its own offset, frequency error, drift and 5G time-update corrections.

## 2. Design alternatives

`PeriodicGate` (INET 4.7.0) reads `offset` at `INITSTAGE_LOCAL`. At `INITSTAGE_QUEUEING` it starts gating at position `offset` of its `durations` list, anchored on its clock reading at that instant, here C_T(0). Later changes are absolute clock events at that reading plus the durations.

| # | Option | Assessment |
|---|---|---|
| A1 | The compiler computes `offset` | **Impossible.** The needed position (C_T(0) − b) mod T depends on each translator's `TtClock` parameters (θ0, y, D and the update sawtooth at t = 0), which the compiler does not know and should not duplicate. A static `offset` cannot express it. |
| A2 | An INI / NED expression computes the offset from `TtClock` parameters | **Impossible.** A NED expression cannot read another module's parameters, nor reproduce C_T's exact 128-bit floor arithmetic. |
| A3 | Change `TtGateClock` to present (C_T − b) readings | **Not allowed** (accepted component). It would also change the time seen by every clock user. |
| A4 | INET `GateControlList` | It has no base-time or phase parameter and sets static offsets. |
| A5 | A new gate scheduler | It would duplicate INET's gating and guard-band logic. |
| **A6 (chosen)** | **`TtEpochGate`**, a subclass of INET's `PeriodicGate` that replaces only the initial list position | It reuses all INET gate behaviour and the accepted `TtGateClock` event semantics. The change is narrow and default-off. |

**`TtEpochGate`** (`src/nasctime/m2/TtEpochGate.{ned,h,cc}`, about 60 lines):

- It is `simple TtEpochGate extends PeriodicGate like IPacketGate` with one parameter, `baseTime`.
- At `INITSTAGE_QUEUEING`, just before `PeriodicGate` starts gating, it sets the initial position to **`offset + (C_T(init) − baseTime)`, modulo the cycle**. C_T(init) is the reading of its own clock. `offset` is the list position at TT time `baseTime`; the compiler emits it.
- It refuses:
  - a missing clock, or a clock that is not a `TtGateClock`, so a gate never silently runs on simulation time;
  - `scheduleForAbsoluteTime = false`, because relative events would not stay anchored across clock steps;
  - a base time later than C_T(init) (future activation, §4);
  - runtime changes of its schedule parameters (§4).
- It records `epochClockAtInit` and `epochElapsedAtInit` as diagnostic scalars.

## 3. S-CFG/2 extension (backwards compatible)

The schema stays `nasctime-scfg/2`. Common-epoch mode is **opt-in** via `tas.time_reference`:

```json
"tas": {
  "untagged_tc": 7,
  "time_reference": "common-epoch",
  "schedules": [
    {"id": "dl-ds-tt", "translator": "ds-tt", "port": "tsn", "cycle_ns": 10000000, "base_time_ns": 0,
     "entries": [{"start_ns": 0, "duration_ns": 2000000, "open": [0, 2, 3, 4, 5, 6, 7]},
                 {"start_ns": 2000000, "duration_ns": 3000000, "open": [0, 2, 3, 4, 6, 7]},
                 {"start_ns": 5000000, "duration_ns": 5000000, "open": [0, 1, 2, 3, 4, 6, 7]}]}
  ]
}
```

| Rule | Behaviour |
|---|---|
| `time_reference` absent or `"relative-phase"` | Exactly the accepted S-CFG/2. `phase_ns` is required, and `base_time_ns` stays an **unsupported field**, as the accepted tests require. The output is byte-identical (§6). |
| `"common-epoch"` | Every schedule needs `base_time_ns`. Without it: "missing base_time_ns: common-epoch mode … requires a common base time". |
| `phase_ns` with common-epoch | "conflicting phase_ns and base_time_ns". There is no reviewed combination, so it is refused. |
| `base_time_ns` | An integer number of ns in [0, 9·10¹² ns = 9000 s]. In that range the ps value is exactly representable as the INI double that OMNeT++ rounds to ps. Negative values, floats, booleans, strings and values beyond the range are refused. |
| Other values of `time_reference` | Refused |
| Other checks | Unchanged in both modes: untagged (gPTP) class always open, stream transmittability, entry gaps / overlaps / coverage, overlapping or duplicate schedules |
| Emission per gate | `typename = "nasctime.m2.TtEpochGate"`, `baseTime = <n>ns`, then `initiallyOpen` / `durations` / `offset` (the list position at TT time base) |
| Translator-level lines | Unchanged: shaper, `TtGateClock`, explicit gate binding, untagged class |
| Serialization | Deterministic, integer ns |

**Also fixed:** in relative mode, a schedule **without `phase_ns`** made the accepted compiler raise `KeyError` after it had recorded the error. It is now a controlled specification error (exit 1, no traceback). Valid inputs are unaffected.

## 4. Runtime behaviour, activation and clock corrections

**Initialisation.** At t = 0 the gate reads C_T(0). It requires C_T(0) ≥ b. Its initial state is the entry at position (C_T(0) − b) mod T.
- No transition happens at initialisation, also when the position is exactly a boundary: the state is then that of the entry starting there.
- No state is silently changed at start-up. The gate starts in the declared state.

**Past base time** (b ≤ C_T(0)): the schedule is active from start-up, as if it had run since b.

**Future base time** (b > C_T(0)) is **refused**: "base time … is later than the TT clock at initialization: activation at a future base time is not supported". A negative C_T(0) with b = 0 is the same case. An explicit policy (for example, holding an admin state until b) is left to a later, reviewed increment.

**Clock rate and drift.** Changes are anchored at the absolute TT times b + k·T + boundary. Their simulation times follow each translator's C_T (§5).

**5G time-update corrections** follow the reviewed `TtGateClock` event semantics (M2B-2):
- **A forward step** delivers, at the step instant, every change whose TT time it jumped over (overdue), in clock-time order. The state after the step equals the position formula.
- **A backward step** does not repeat a change already made. While the clock re-traverses an interval it had already passed (at most the step size), the gate keeps the state it had. During that interval it can therefore differ from the position formula. This is the defined behaviour of a **physical clock correction**, and it is tested (§5).

**Schedule reconfiguration** at runtime (a parameter change) is distinct from a clock correction. It is **refused** for common-epoch gates ("runtime change of 'offset' is not supported").

## 5. Evidence

### 5.1 Source checks (no simulation)

**`check/test_tsnaf_compile_epoch.py`: 32 / 32.**

| Area | Checks |
|---|---|
| Relative mode | M2B-3 fragment byte-identical; no epoch lines; explicit `relative-phase` gives identical output |
| Common-epoch emission | An independent model of `PeriodicGate` plus the `TtEpochGate` rule reproduces the declared state at (C_init − b + t) mod T, for several initial readings C_init ≥ b (the committed schedule and 150 random schedules) |
| Output | S-CFG/1 prefix; determinism; integer-ns serialization |
| Negatives | All in §3, including the duplicate / overlapping schedules and the gPTP and stream checks in epoch mode |
| Robustness | Fuzz (no crash); CLI |
| Regression | The `KeyError` fix above |

The accepted compiler suites are unchanged: S-CFG/1 **147 / 147** (37 cases) and S-CFG/2 **54 / 54**.

### 5.2 Local simulation evidence (release build; not hosted)

**Independent oracle** (`check/m2b5_oracle.py`):
- Inputs: the declared entries, cycle and base time; the translator's recorded `TtClock` parameters; C_T re-implemented from TtClock.ned in exact integers.
- Change j occurs at **t_j = inf{t ≥ t_(j−1) | C_T(t) ≥ c_j}**, c_j = b + k·T + boundary, searched segment by segment.
- It never reads compiled gate parameters.

**`check/test_m2b5_epoch_gate.py` on test network `m2b5/EpochGateTest.ned`** (two translators A / B, each `TtClock` + `TtGateClock` + one `TtEpochGate`): **38 / 38** (35 in step 156, plus the D-simultaneous case of step 157). Every gate transition equals the oracle to the ps, in every case:

| Scenario | Result |
|---|---|
| A: identical clocks | Transitions coincide |
| Initialisation inside an open window / inside a closed window / exactly at a boundary | As declared; no transition at initialisation |
| Base time equal to the initial reading | Position 0, first change at b + 2 ms |
| B: θ0 1 ms vs 3.3 ms | Same TT positions; each change of A has the same change of B exactly 2.3 ms earlier in simulation time |
| C: +200 ppm / −200 ppm with drift | Each follows its own TT clock, not an ideal clock |
| D, forward 5G steps | 6 changes jumped over and delivered at the step instant, equal to `TtGateClock`'s `numOverdueClockEvents` |
| D, backward 5G steps | 6 changes re-traversed and not repeated (§4) |
| D, simultaneous (step 157) | Two gates on **one** `TtGateClock`, each with 6 changes jumped over by the same forward steps: identical transitions, both equal to the oracle; the clock counts 12 overdue deliveries |

Negatives, each failing for its intended reason:

| Negative | Result |
|---|---|
| Future base time | Refused |
| Negative TT clock at initialisation | Refused |
| Missing gate-clock binding | Refused |
| Another clock type (INET `SettableClock`) | Refused |
| Relative scheduling | Refused |
| Runtime reconfiguration (`ScenarioManager set-param`) | Refused |
| 1 ns base-time error | Detected: every change 1 ns of TT time late |
| A gate bound to another translator's clock | Detected: runtime position inconsistent with its own clock |

A mutation with no epoch offset fails **14 / 35**.

**`check/test_m2b5_epoch_bridge.py` on `m2b5/epoch.ini`** (the accepted N = 2 M2S72Bridge; PCP 5 → TC5, PCP 0 → TC1; NW-TT and both DS-TTs with the same declared schedule, base 0; explicit TT gate binding; M2B-4 `pairingMode = "tas"` and M2-S1 observation): **36 / 36**.

| Area | Result |
|---|---|
| Gates | In EPO-gated (accepted TT clocks) and in EPO-clocks (θ0 NW-TT 1 ms / DS-TT[1] 3.3 ms; DS-TT[0] +200 ppm, DS-TT[1] −200 ppm; accepted 5G updates), every TC5 / TC1 transition at the three TSN ports equals the common-epoch oracle. Every other gate stays open. |
| Alignment | The three translators change their gates at the **same TT times** (121 changes in [0.1, 0.7] s TT time). In EPO-clocks these fall at **different simulation times**. Overdue counts equal each `TtGateClock`'s. |
| Real Ethernet traffic | 238 frames enqueued per run; 192–194 arrived with their gate closed and were held. Every dequeue happens with the gate open. |
| Residence (M2B-4 method) | Every transmitted frame: identity from the wire; t1 / t12 from PCAP; R exact in ps; enqueue / dequeue equal to INET's queues; counted once. Held frames' R contains the wait. |
| Frames unfinished at the end | Two frames in EPO-gated are explained precisely: one in transmission at the end (dequeued exactly at its gate opening), one queued behind it. |
| Statistics | `bridge_delay.py`, unchanged, equals the oracle per egress translator / PCP / VID |
| Negatives | Missing binding: refused. Future base: refused. 1 ns base error at the DS-TTs: detected and located (NW-TT unaffected). |

**Default-off and backwards compatibility:**
- With the base-commit library (`9781291`) and the M2B-5 library, these are identical: **all output files and scalars** of the accepted `M2S72-B-q0-Eall-n2` (57 files, 2812 scalars), M2B-3 `TAS-gated` (51 files, 3684 scalars) and M2B-4 `RES-tas` (57 files, 3710 scalars). The files are PCAPs, M2-S1 logs and vector data.
- `TtEpochGate` is referenced only by its own sources, the compiler and the M2B-5 test files (git grep).
- The default-off allowlists of the M2B-2 and M2B-3 tests list the new test-only files and `TtEpochGate` sources. Their check counts are unchanged.

### 5.3 Regression (local)

| Suite | Result |
|---|---|
| 12 tier-0 suites (workflow runner) | 12 / 12 |
| `m2s72_gen.py` / `m2s72s5_gen.py` | IDENTICAL |
| S-CFG/1 | 147 / 147 (37 cases) |
| S-CFG/2 | 54 / 54 |
| M2B-2 clock | 43 / 43 |
| bridge-delay | 33 / 33 |
| M2B-2 topology | 9 / 9 |
| M2B-3 TAS functional | 60 / 60 |
| M2B-3 configuration check | 10 / 10 |
| M2B-4 pairer | 33 / 33 |
| M2B-4 residence | 21 / 21 |
| **New:** compiler epoch / gate / bridge | **32 / 32**, **38 / 38**, **36 / 36** |

### 5.4 Hosted CI

- **Tier-0** runs the unchanged 12 suites. The new suites are separate and not added.
- **Tier-1** (if a maintainer applies `tier1:run`) builds and links `libnasctime_m2` with `TtEpochGate`. No protected tier-1 gate is changed, and no hosted run executes the M2B-5 configurations.

### 5.5 Debug-assertion validation (step 157; local)

**Build configuration:**

| Item | Value |
|---|---|
| Compiler | Ubuntu clang 18.1.3 |
| OMNeT++ | 6.5.0, `make MODE=debug` (`opp_run_dbg`, `liboppsim_dbg`) |
| INET | 4.7.0, unmodified pinned tarball, `make MODE=debug` (`libINET_dbg.so`) |
| `libnasctime_m2_dbg.so` | Built from this branch by `simulations/m2/m2b2/build_debug.sh`, linked against `INET_dbg`; includes `TtEpochGate` |
| Debug flags (OMNeT++ `Makefile.inc` `CFLAGS_DEBUG`) | `-O0 -Wall -glldb -fstandalone-debug`. **No `-DNDEBUG`**, so INET's `ASSERT` and `DEBUG_CHECK_IMPLEMENTATION` (`DEBUG_CMP`) are enabled. Release (`CFLAGS_RELEASE`) uses `-O3 -DNDEBUG=1`. |
| Simu5G 1.8.1 | NED sources only (the component network uses no Simu5G module) |

**Assertions present:** the assertion texts of the IClock invariants are in `libINET_dbg.so` and absent from the release `libINET.so`:
- `ClockEvent::execute`, invariant 2: `getArrivalClockTime() == clockTime`;
- `ClockBase::checkScheduledClockEvent`, invariant 5.

This is the same debug build that caught the IClock violations of the M2B-2 adapter at `c1a0d7d` in step 148.

**Executed:** `M2B5_MODE=debug python3 -B simulations/m2/check/test_m2b5_epoch_gate.py`, which uses `opp_run_dbg` with `INET_dbg` and `nasctime_m2_dbg`. It covers every component case:
- initialisation exactly at a schedule boundary, and in an open / closed window;
- base time equal to the initial reading;
- different TT clock offsets;
- ±200 ppm and drift;
- forward corrections with overdue gate events;
- backward corrections;
- simultaneous overdue gate events of two gates on one `TtGateClock` at the same update instants;
- all negative controls.

**Result: `M2B-5 common-epoch gate tests (debug): 38 / 38 PASS, 0 FAIL`.** No INET clock-event or scheduling invariant failed. The release run of the same suite is also 38 / 38.

**Not executed:**
- the bridge suites in debug mode (no Simu5G debug build);
- any sanitizer run of `TtEpochGate`.

## 6. Limitations and outstanding validation

| Limitation | Status |
|---|---|
| Future activation | Base time later than C_T at start-up: refused. An admin / oper schedule transition (802.1Qbv ConfigChange) is not modelled. |
| Runtime reconfiguration | Refused. Its semantics are not defined. |
| Backward 5G steps | The gate may differ from the position formula for at most the step size, because executed changes are not repeated (§4). |
| Base-time range | Limited to 9000 s for exact ps conversion |
| Debug and sanitizer builds | The component suite passes under the INET debug-assertion build (§5.5). The bridge tests were not run in debug mode: there is no Simu5G debug build. `TtEpochGate` was **not** run under any sanitizer. |
| Scientific validation outstanding | Clock synchronization accuracy between translators; feasibility and consistency of cross-translator schedules (e.g. windows sized for the 5G-system delay); worst-case latency bounds; conformance to IEEE 802.1Qbv / 802.1AS. |
