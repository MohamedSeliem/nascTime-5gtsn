# M2-R181c: final M2-S5 / M2-S6 validation closure — plan, definitions and predictions

Declared before any verdict run of this milestone.

**Decision.** Review of 2026-11-12 12:24, "M2-R181c — Final S5/S6 Validation Closure".

**Accepted in M2-R181b:**
- the 736 ns and 224 ns root causes;
- the rows A7-v, C10-v, R2b-v, S5-R-ingress-v and S5-R-egress-v2;
- the M2-S4 dependency gate (conditional on R2b-v);
- the R-4 adjudication (FAIL kept);
- CP2 r2 and I-2H.

**Reviewer note.** The exact count of 10 shifted frames in R2b-v is a regression fingerprint of the pinned experiment. The invariant is the causal attribution of every send-time difference, with unchanged listener arrivals.

**Unchanged:**
- `check_m2s5.py`, `omnetpp.ini`, every historical checker, record and prediction;
- upstream (unmodified Simu5G 1.8.1);
- the reviewer's VM patch is not incorporated.

**Development evidence.** Seed-0 diagnostic runs on scratch, hashed into `diag-raw-outputs.sha256`. Script: `check_v181c_m2s5.py` on them; outputs quoted below.

## 1. C8: definition (`check_v181c_m2s5.py`, C8-v)

### 1.1 What C8 validates

Sources: M2-S5 design §6.3 "Containment"; M2-S0 design (tags are bridge-internal metadata).

The DS-TT eth[1] egress, towards the slave, carries exactly two disjoint packet classes:

| Class | Frames | Expected tag state |
|---|---|---|
| **F, forwarded** | Tagged at NW-TT eth[1] ingress by the M2-S0 layer (frameId), crossed the 5GS | Each reaches the DS-TT egress with its valid tag (recovered, same frameId) and is stripped |
| **L, locally generated** | The DS-TT Pdelay engine's Pdelay_Resp and Pdelay_Resp_Follow_Up | Injected above the measurement layer, so untagged by construction (`TtTimestampProcessor::processEgress`, `numUntagged`) |

- **The count of class L follows the slave's Pdelay_Req timer**, a slave-clock property (`root-causes.md` §3). It is therefore excluded from the cross-scenario comparison and checked on its own.
- **The historical C8** compares the per-class-blind counter `framesUntaggedAtEgress` with M2S4. This mixes class L into the forwarding comparison.

### 1.2 C8-v sub-rows (all must hold)

| | Sub-row |
|---|---|
| (a) | Containment: the slave's audit counts 0 frames with a TtSyncIngressTag (as C8) |
| (b) | Every untagged egress frame is class L: its logged chunk signature is GptpPdelayResp / GptpPdelayRespFollowUp, and it is one-to-one with a DS-TT engine `tx` row of that message type (in order; egress enqueue ≤ engine transmission start < enqueue + 1 ms). Invalid tags 0; recovered = stripped |
| (c) | Class L on its own (M2-S4 responder contract): engine Resp = Resp_FU = received Pdelay_Req, each Resp_FU after its Resp |
| (d) | Class F conservation in the run: every frameId tagged at NW-TT eth[1] ingress is recovered at the DS-TT egress, or is a Pdelay frame terminated by the NW-TT engine (count = NW-TT engine rx), or was tagged in the last 100 ms (still inside). Nothing else |
| (e) | Class F cross-scenario (M2S4 of the same seed / variant): the recovered frameId set and the NW-TT-terminated set equal M2S4's |

**Not done:** the expected count is not changed from 12 to 10. Class L is excluded by identity, not by number.

### 1.3 Development evidence (1.8.1, seed 0, `check_v181c_m2s5.py c8demo`)

| Case | Result |
|---|---|
| Unmodified | **PASS**: recovered 568; untagged 10 = DS-TT Resp 5 + Resp_FU 5 for 5 Pdelay_Req; NW-TT tagged 578 = 568 recovered + 10 NW-TT-terminated (GM Pdelay Resp / Resp_FU) + 0 inside; = M2S4 |
| Mutation "forwarded-untagged" (one forwarded frame arrives without its tag) | **FAIL** (b), (d) |
| Mutation "local-missing" (one DS-TT Pdelay_Resp missing) | **FAIL** (b), (c) |
| Real faults (in the M2-S5 controls) | N-noStrip → (a); N-noFcsNw → (d), (e); N-fwdPdelay → (e) (the GM's Pdelay frames are forwarded instead of terminated) |

## 2. Negative controls

### 2.1 N-tseSlot (`M2S5-nc-tseSlot`, idle; historical expected failures C2, C3, S2, S3)

1. **Intended defect.** The DS-TT takes TSe when the Sync passes its slot (enqueue) instead of at transmission start. The DS-TT egress queueing is then missing from Res.
2. **Why it is no longer detected on 1.8.1.**
   - The mutation changes the correction only when the Sync waits at the DS-TT egress.
   - Seed 0, sync log, TSe − slot time:

     | Simu5G | Config | TSe − slot time |
     |---|---|---|
     | 1.8.0 | M2S5 | 464 ns for 38 of 39 Syncs |
     | 1.8.1 | M2S5 | **0 for 39 of 39** |
     | 1.8.1 | M2S5-load | 10.864 µs for 24 of 39; 0 for 15 |
     | 1.8.0 | M2S5-load | 0 / 240 ns / 464 ns / 10.864 µs for 4 / 14 / 1 / 15 |

   - **Cause.** On 1.8.0 the UE delivered the Sync in the same slot as a 122-B best-effort frame (PCP 0, DRB 1), which went first. The PCP 0 frame ended at the DS-TT egress 96 ns before the Sync started. On 1.8.1 that frame is delivered one or more TTIs earlier: the 1.8.0 DRB-1 RLC tail stranding (#311) is gone.
3. **Does the mutation still exercise the targeted behaviour?** The code path runs: 39/39 Follow_Ups carry the slot-time cf. Its value equals the correct one whenever TSe = slot, which on idle 1.8.1 is always.
4. **Replacement N-tseSlot-v.**
   - `M2S5R-nc-tseSlot-load` (`m2s5r181c.ini`: M2S5-nc-tseSlot + the M2S0 load traffic, exactly as M2S5-load = M2S5 + load).
   - Base: M2S5-load; M2-S4 reference: M2S4-load.
   - Expected failures beyond the base: {C2, C3, S2, S3} (the historical set).
   - Signature: every delivered Follow_Up carries the slot-time cf, and ≥ 1 Sync queued.
5. **Development evidence.** **PASS**:
   - failed beyond base = [C2, C3, S2, S3], base fails nothing;
   - 24 queued Syncs;
   - slave error after step 1 = −10 864 ns.

### 2.2 N-noFcsNw (`M2S5-nc-noFcsNw`; historical expected failures C1, C2, C6, C7, C8, S2, S3)

1. **Intended defect.** The NW-TT rewrites the Follow_Up correctionField without recomputing the FCS. The NW-TT node's own FCS checker then drops every Follow_Up: none enters the 5GS, and the slave is never corrected.
2. **Why S3 no longer detects it on 1.8.1** (established, `diag` below; the M2-R181b hypothesis is now replaced).

   | Simu5G | Syncs with identical TSi / TSe / POT in M2S4 and noFcsNw | Prediction cf | S3 trace match | S3 |
   |---|---|---|---|---|
   | 1.8.0 | **1 of 39** | Falls back to the uncorrected wire cf of M2S4 for the 38 others | 272 / 5003 | FAIL |
   | 1.8.1 | **39 of 39** | All 39 corrected | 5003 / 5003 | PASS |

   - **On 1.8.0** removing the Follow_Ups from the DRB changed the RLC timing of the Syncs. S3 failed through that side effect, not through the absent correction.
   - **On 1.8.1** the predicted model steps the clock 39 times, every step by exactly 0: the slave's clock starts exact (initial offset 0) and does not drift. The never-stepped slave clock records the same values.
   - So S3 cannot distinguish "never synchronised" from "synchronised by zero steps" when the slave starts exact. This is the same S3 blindness the checker already documents for N-noFcsDs.
3. **Does the mutation still exercise the targeted behaviour?** Yes. The NW-TT node FCS checker drops 39 = Follow_Ups received, and 0 Follow_Ups are in the 5GS. C1, C2, C6, C7 and S2 detect it on 1.8.1.
4. **Replacement N-noFcsNw-v.**
   - `M2S5R-nc-noFcsNw-offset`: N-noFcsNw with the initial slave offset of M2S5-offset, 1.234567891 ms. The slave must now be stepped to become exact.
   - Base: M2S5-offset.
   - **M2-S4 reference `M2S4R-offset`** (M2S4 with the same offset). S3 predicts from the M2-S4 records, and with the offset the slave's clock-driven Pdelay timing differs from M2S4. The historical checker evaluates M2S5-offset without S3 (R4 = None).
   - **S3 is evaluated as S3o.**
     - S3o is identical to S3 except at a step instant. There the slave records two samples (old, then new value; `SettableClock.cc:81`), and S3 compares both with one predicted value.
     - S3o applies the step-pair rule of S1 (`compare_recorded`).
     - S3's comparator therefore cannot be applied to a run with a non-zero step. That is why the historical checker never did; development: S3 on the base matches 5080 of 5081, the one mismatch being the step-1 "new" sample.
   - Expected failures beyond the base: {C1, C2, C6, C7, C8, S2, S3o}, with the base failing nothing.
   - Signature: as historical.
5. **Development evidence.** **PASS**:
   - failed beyond base = [C1, C2, C6, C7, C8, S2, S3o], base fails nothing (S3o base 5081 / 5081);
   - control S3o 132 / 5003; the slave clock stays at +1 234 567 891 ps.

The historical N-tseSlot and N-noFcsNw rows are kept and keep their 1.8.1 verdict (FAIL). The replacements are additional rows.

## 3. Execution (`run_r181c.sh`, root `out-r181c-m2`, new; JOBS 1 for every runner)

| Step | Action |
|---|---|
| 1 | `m2s0` → drop runs (`m2s1` reads only the hash file) |
| 2 | `m2s1` |
| 3 | `m2s4` → R2b-v (+ mutation) → **M2-S4 dependency gate** (as M2-R181b, accepted). Drop M2-S1 runs and the M2-S4 configs not read later (all except M2S4, -frag, -load, -load-harq16) |
| 4 | `m2s5` → manifest |
| 5 | The three M2-R181c configs (`m2s5r181c.ini`, seed 0), run with `m2s5.sh run()`'s command → manifest |
| 6 | `check_v181c_m2s5.py full` (check_m2s5 with C8-v), `c8demo`, `controls` |
| 7 | **M2-S5 → M2-S6 gate** (`m2s5_dependency_gate.sh`). All must hold:<ul><li>G1: the historical M2-S5 check fails only {C8, N-tseSlot, N-noFcsNw, N-noStrip, N-fwdPdelay};</li><li>G2: the C8-v check fails only {N-tseSlot, N-noFcsNw}: every functional row passes, and the 12 other historical controls pass;</li><li>G3: `controls` PASS;</li><li>G4: `c8demo` PASS.</li></ul>Then `raw-outputs.sha256` is written with `m2s5.sh`'s own hash command over the real runs, plus `DEPENDENCY-GATE.txt` |
| 8 | Drop M2-S4 runs, the M2-S5 configs not read by M2-S6 (all except M2S5 and M2S5U-hold; `gate_m2s6.py`), and the M2-R181c config runs |
| 9 | `m2s6` with JOBS=1 (no overlapping configurations) → manifest → drop runs |

**Disk guard:** 300 MB.

**1.8.0 evidence for the new rows** (`run_r181c_ctl180.sh`, isolated scratch, manifested): C8-v (`c8demo`) and the two replacement controls on 1.8.0.

## 4. Predictions

| Item | Prediction |
|---|---|
| m2s0 / m2s1 / m2s4 check outputs | Byte-identical to M2-R181 / M2-R181b |
| R2b-v | PASS. Invariant: every send-time difference attributed, arrivals unchanged. Regression fingerprint: 10 shifts |
| M2-S4 gate | Opens |
| Historical M2-S5 `check.txt` | Byte-identical to `out-r181b-m2/m2/M2-S5/check.txt` (66/71; C8 + the 4 controls) |
| C8-v check (full) | <ul><li>C1–C7, C8-v, S1–S5, P1, P2, G0, A0, E1, V1, G1, F-*, H*, W1 and all unit rows: PASS;</li><li>N-noStrip, N-fwdPdelay and the 10 other historical controls: PASS;</li><li>historical N-tseSlot and N-noFcsNw: FAIL (as on 1.8.1, superseded)</li></ul> |
| `controls` | N-tseSlot-v PASS, N-noFcsNw-v PASS |
| `c8demo` | PASS (unmodified PASS, both mutations FAIL) |
| M2-S5 → M2-S6 gate | Opens |
| M2-S6 on 1.8.1 | **No row-level prediction**: never evaluated on 1.8.1, and its baselines (M2-S5) changed. Every FAIL is reported. If its cause is not understood: stop for review |
| 1.8.0 evidence | C8-v PASS on 1.8.0 (classes as on 1.8.1; not a defect detector). N-tseSlot-v and N-noFcsNw-v detect on 1.8.0 as well |

**STOP after these, at the M2-R181c review gate.**

## Addendum 1 (2026-11-12 13:15Z, after the gate closed; nothing above is changed)

**Unexpected result.** The first C8-v check (`check-v181c-v1-crash.txt`, OVERALL FAIL 68/71) reported N-fwdPdelay as a "checker exception FileNotFoundError" on `dsTt.eth[1].trafficConditionerLayer.engine.pdelay.csv`. Gate G2 therefore closed: its failures were [N-fwdPdelay, N-noFcsNw, N-tseSlot], and the driver stopped before M2-S6, as designed.

**Cause (understood).** N-fwdPdelay sets `terminate = requester = responder = false` (`omnetpp.ini`, `[Config M2S5-nc-fwdPdelay]`). The translators' Pdelay engines are then inactive and write no log. The first C8-v code treated the absent log as an error instead of as "no engine-generated or engine-terminated frames".

**Fix.** In `check_v181c_m2s5.py`, `rd_engine()`: an absent engine log = zero rows. An untagged frame that is not matched to an engine transmission still fails (b). Nothing else changed.

**Re-evaluation.** The same raw runs are re-evaluated (`check-v181c.txt`); the closed gate record is kept as `DEPENDENCY-GATE-closed-1.txt`. The gate and steps 8–9 then continue (`run_r181c_cont.sh`). The predictions in §4 are unchanged.

**1.8.0 evidence** (`out-r181c-ctl180`; it ran before the fix and is not affected by it, because neither `c8demo` nor `controls` reads a run without an engine):
- `c8demo`: PASS;
- `controls`: N-tseSlot-v PASS, N-noFcsNw-v PASS.
