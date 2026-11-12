# M2-R181c closure report: final M2-S5 / M2-S6 validation on Simu5G 1.8.1

**Branch.** `m2/simu5g-1.8.1`, local only. M2-R181c commits: `941f90e` (plan, C8-v, controls, gate, drivers; before any verdict run), `8f30f42` (addendum 1), `28759e7` (records, diffs, addendum 2), then this report. Earlier records (M2-R181, M2-R181b, every 1.8.0 record) are untouched.

**Stack.** OMNeT++ 6.4.0, INET 4.7.0, Simu5G 1.8.1 unmodified; the accepted 1.8.0 build (`libsimu5g.so` 203cf231…) for the 1.8.0 evidence. Not the reviewer's OMNeT++ 6.5.0 VM; the VM NED / INI patch is not incorporated.

**Stop.** At the M2-R181c review gate. No E2, Q1–Q4, S7.2a quantitative scaling or new M2 feature.

## 1. Summary

1. **C8 revised by packet class (C8-v), not by count.** It separates forwarded frames (must be tagged, carried and recovered) from frames the DS-TT generates itself (Pdelay_Resp / Resp_FU, untagged by construction, checked one-to-one against the engine). Unmodified M2-S5 passes; both mutations fail; three real faults (N-noStrip, N-noFcsNw, N-fwdPdelay) fail it.
2. **Both insensitive controls explained and replaced.**
   - N-tseSlot: on idle 1.8.1 the Sync never waits at the DS-TT egress, so "TSe at slot time" equals the correct TSe. Replacement under load: detects.
   - N-noFcsNw: on 1.8.1 the slave starts exact and its Sync timing is unchanged by the fault, so S3 cannot tell "never stepped" from "stepped by zero". On 1.8.0 S3 failed only through a timing side effect. Replacement with an initial slave offset and S3o: detects.
3. **M2-S5 closed on 1.8.1.** Every functional row PASSES; every required negative control detects its fault (the two historical controls stay FAIL and are superseded). The historical `check.txt` is unchanged (FAIL 66/71).
4. **M2-S6 on 1.8.1: PASS 1863/1863**, same row set as 1.8.0, 0 verdict changes. Numerical changes are confined to five 1 GB-load / drift configurations and come from Follow_Ups that 1.8.0 delayed (up to 125 ms) or lost under load and 1.8.1 delivers in 1.5–1.7 µs.
5. **One new limitation found** (addendum 2): C8-v sub-row (d) assumes the 5GS delivers every forwarded frame. On 1.8.0 under load it fails because the 5GS discards frames; on 1.8.1 every M2-S5 run delivers all of them.

## 2. Revised C8 (C8-v): definition and evidence

**What C8 validates** (M2-S5 design §6.3 "Containment"; M2-S0: tags are bridge-internal). The DS-TT eth[1] egress towards the slave carries two disjoint classes:

| Class | Frames | Expected |
|---|---|---|
| F, forwarded | tagged at NW-TT eth[1] ingress (frameId), crossed the 5GS | recovered with its valid tag at the DS-TT egress and stripped |
| L, local | the DS-TT Pdelay engine's Pdelay_Resp and Resp_FU | untagged; their number follows the slave's Pdelay_Req timer (slave clock), so excluded from the cross-scenario comparison |

**Sub-rows (all must hold):** (a) 0 tagged frames reach the slave; (b) every untagged egress frame is a DS-TT Pdelay_Resp / Resp_FU, one-to-one and in order with an engine `tx`; invalid tags 0; recovered = stripped; (c) engine Resp = Resp_FU = received Pdelay_Req, Resp before Resp_FU; (d) every frame tagged at NW-TT eth[1] is recovered, or is a Pdelay frame terminated by the NW-TT engine (count = engine rx), or entered in the last 100 ms; (e) recovered and terminated frameId sets equal M2S4's. The expected count was **not** changed from 12 to 10: class L is excluded by identity.

**Evidence** (`out-r181c-m2/m2/M2-S5/`):

| Case | 1.8.1 | 1.8.0 |
|---|---|---|
| M2S5 seed 0, unmodified (`c8demo-v181c.txt`) | **PASS**: 568 recovered; 10 untagged = 5 Resp + 5 Resp_FU for 5 Req; NW-TT tagged 578 = 568 + 10 terminated + 0 inside; = M2S4 | **PASS** (567 + 10 + 1 inside) |
| Mutation: one forwarded frame untagged | **FAIL** (b), (d) | FAIL |
| Mutation: one DS-TT Pdelay_Resp missing | **FAIL** (b), (c) | FAIL |
| All 13 M2-S5 run pairs (`check-v181c.txt`) | **C8-v PASS** | (historical C8 PASS on 1.8.0) |
| N-noStrip (tag not stripped) | fails exactly {C8} → PASS | — |
| N-noFcsNw (Follow_Ups dropped at the NW-TT) | C8 in its failure set | — |
| N-fwdPdelay (Pdelay forwarded, not terminated) | C8 in its failure set | — |

**Effect on the historical controls:** with C8-v, N-noStrip and N-fwdPdelay detect their faults again (their historical FAIL on 1.8.1 came only from the count-based C8).

**Addendum 1 (fixed before any M2-S6 run).** The first C8-v evaluation raised FileNotFoundError on N-fwdPdelay, whose engines are disabled and write no log; gate G2 closed and the driver stopped. `rd_engine()` now treats an absent log as zero rows; same raw runs re-evaluated; the closed gate record is kept.

**Addendum 2 (limitation).** 1.8.0 M2S5-load fails C8-v (d) only: 2531 forwarded frames (2520 application frames, 5 Syncs, 6 Follow_Ups) are neither recovered nor terminated; (e) holds, so the same frames are missing in M2S4-load. Consistent with 1.8.0's documented 5-HARQ MAC discards (M1 L1), not separately replayed. (d) therefore tests the bridge only where the 5GS is lossless, which holds for every M2-S5 run on 1.8.1. Possible future form: accept frames whose 5GS loss is accounted for by the RLC replay, as A7-v does. Not applied.

## 3. Negative controls: root cause and sensitivity

| | N-tseSlot | N-noFcsNw |
|---|---|---|
| Intended defect | DS-TT takes TSe when the Sync passes its slot, not at transmission start: egress queueing missing from Res | NW-TT rewrites the Follow_Up cf without recomputing the FCS: the NW-TT's FCS checker drops every Follow_Up; the slave is never corrected |
| Why undetected on 1.8.1 | Seed 0 idle: TSe − slot = 0 for 39/39 Syncs (1.8.0: 464 ns for 38/39, the Sync queued behind a 122-B PCP 0 frame delivered in the same slot by the 1.8.0 DRB-1 tail stranding #311, absent on 1.8.1). Wrong and correct correction coincide | 1.8.1: 39/39 Syncs have identical TSi / TSe / POT to M2S4, the predicted steps are all 0 and the slave starts exact, so the never-stepped clock matches 5003/5003. 1.8.0: only 1/39 identical; S3 failed (272/5003) through that side effect, not through the missing correction |
| Mutation still exercised? | Yes: 39/39 Follow_Ups carry the slot-time cf | Yes: 39 drops = Follow_Ups received, 0 in the 5GS; C1, C2, C6, C7, S2 still detect it |
| Replacement | **N-tseSlot-v**: `M2S5R-nc-tseSlot-load` (same mutation + M2S0 load), base M2S5-load, reference M2S4-load; expected beyond base {C2, C3, S2, S3} | **N-noFcsNw-v**: `M2S5R-nc-noFcsNw-offset` (initial slave offset 1.234567891 ms), base M2S5-offset, reference `M2S4R-offset`; S3 evaluated as S3o (step-pair rule, `SettableClock.cc:81`); expected {C1, C2, C6, C7, C8, S2, S3o} |
| 1.8.1 result (`controls-v181c.txt`) | **PASS**: base fails nothing; control fails exactly the set; 24 Syncs queued; slave error after step 1 −10 864 ns | **PASS**: base fails nothing (S3o 5081/5081); control fails exactly the set; slave never stepped, error stays +1 234 567 891 ps |
| 1.8.0 result (`out-r181c-ctl180`) | **PASS** (29 queued; base fails C8-v, addendum 2) | **PASS** (base fails nothing) |

The historical N-tseSlot and N-noFcsNw rows keep their FAIL; the replacements are additional rows.

## 4. M2-S5 results (1.8.1, `out-r181c-m2/m2/M2-S5/`)

| Record | Result |
|---|---|
| `check.txt` (historical checker) | FAIL 66/71, **byte-identical** to M2-R181b: C8, N-tseSlot, N-noFcsNw, N-noStrip, N-fwdPdelay |
| `check-v181c.txt` (same checker, C8 → C8-v) | 69/71. **PASS:** G0, A0, E1, V1, C1–C7, C8-v, S1–S7, P1, P2, G1, F-FS1…FS10, F-FD1…FD10, F-lupLate, F-pdelayLoss, H0–H5, H2b, W1, N-bothEnd-unit, N-noHold and 12 historical controls (incl. N-noStrip, N-fwdPdelay). **FAIL:** historical N-tseSlot, N-noFcsNw only (superseded) |
| `controls-v181c.txt` | PASS (N-tseSlot-v, N-noFcsNw-v) |
| `c8demo-v181c.txt` | PASS |
| M2-S5 → M2-S6 gate (`DEPENDENCY-GATE.txt`) | **OPEN** 13:15:40Z: G1–G4 hold; `raw-outputs.sha256` by `m2s5.sh`'s own command over the real runs, 2479 files |

M2-S0, M2-S1, M2-S4 `check.txt` are byte-identical to M2-R181b; R2b-v PASS, its mutation FAIL; the M2-S4 gate opened again. PCAPs and per-run CSV logs are identical to M2-R181b; `.sca` / `.vec` and their per-config exports differ (run metadata; not compared line by line, runs deleted).

## 5. M2-S6 results (1.8.1, `out-r181c-m2/m2/M2-S6/`)

Unmodified 1.8.1, existing criteria, `m2s6.sh` with JOBS=1 (69 configurations, 5628 s, rc 0). The 1.8.0 record `simulations/m2/results/M2-S6/` is unchanged.

| Record | 1.8.0 | 1.8.1 |
|---|---|---|
| `check.txt` | PASS 1863/1863 | **PASS 1863/1863**, same 1864 lines in the same order, 0 verdict changes |
| `gate-D0.txt` (RNG policy, 0 ppm oscillator, tick-reset probe vs M2-S5) | PASS 8/8 | **PASS 8/8**, byte-identical |
| `gate-E0b.txt` (zero-parameter TT clocks = M2-S5) | PASS 3/3 | **PASS 3/3**, byte-identical |
| `report.txt` hypotheses (reported, not gating) | 203 held, 31 refuted | **204 held, 30 refuted**: H1c E-all-load refuted → held; H8 refuted in the same 29 configs; H1c E-sig100 still refuted |
| Raw outputs | 2969 files | 2969 files (same names); 1890 identical hashes |

**Where numbers changed** (`diffs/m2s6-1.8.0-vs-1.8.1.md`: 34 check lines, 87 report lines): M2S6-B-m100, B-p10, C-r1, D-load, D-load-harq16, E-all-load. All idle configurations at 1 Gb/s without load are unchanged in `check.txt`.

| Config | 1.8.0 | 1.8.1 |
|---|---|---|
| D-load / E-all-load | 29 of 39 Follow_Ups reach the slave; lag up to 124.999904 ms; Res 4.07–5.24 ms | **39 of 39**; lag 1.488–1.728 µs; Res 4.31–15.33 ms (Syncs now queue in DRB 1 instead of being lost) |
| D-load-harq16 | 38 of 39; lag up to 125 ms | 39 of 39; lag ≤ 1.728 µs |
| B-m100 | lag 4.0–20.0 ms; steady max \|e\| 77 ns | lag 1.488–1.728 µs; steady max \|e\| 1 ns |
| B-p10 / C-r1 | lag up to 16 ms | lag up to 1.0 / 2.0 ms |
| E-all-load H1c | refuted, +23.6 ns excess (bound has no lag term) | held, 0 excess |

**Cause.** The same 1.8.0 → 1.8.1 change already established in M2-R181/R181b: the DRB-1 RLC tail stranding (#311, M1 O-tail "no cut SDU on 1.8.1") and the 5-HARQ discards (M1 O-S3-1 losses → 0) are gone. Every changed value is still reproduced exactly by the M2-S6 oracles (O1, O4, O5 rows PASS on every Follow_Up).

## 6. M2-S5 numerical differences from 1.8.0 (`diffs/m2s5-1.8.0-vs-1.8.1.md`)

6 verdict changes (C8 and four controls PASS → FAIL in the historical checker; all resolved above) and 11 lines with changed numbers, e.g.: vector lines 17 137 766 → 17 669 540; GTP-U inner frames 57 076 → 59 336; G1 frames matched 8 496 → 8 500; S4 samples before step 1 152 → 132; M2-S4 max error 6 002 226 → 6 000 626 ns; FS2 interval 260 → 250 ms; control slave-error values.

## 7. Updated M2-R181 validation matrix (Simu5G 1.8.1)

| Stage | Historical record on 1.8.1 (kept) | Version-appropriate result | Status |
|---|---|---|---|
| U0 / U1 upstream | PASS | — | closed (M2-R181) |
| M1 S0–S5, O-S3-1, upstream-issues | PASS, except R-ingress, R-egress | S5-R-ingress-v, S5-R-egress-v2 PASS | accepted (R181b) |
| M1 O-tail | crash | `check_o_tail_v181.py`: defined no-cut verdicts | accepted (R181b) |
| M2-S0 | FAIL 20/21 (A7) | A7-v PASS | accepted (R181b) |
| M2-S1 | FAIL 27/28 (C10) | C10-v PASS | accepted (R181b) |
| M2-S3 | PASS 24/24 | — | closed |
| M2-S4 | FAIL 54/55 (R2b) | R2b-v PASS; M2-S4 gate open | accepted (conditional on R2b-v) |
| **M2-S5** | FAIL 66/71 | **C8-v PASS; 69/71 with only the two superseded controls failing; N-tseSlot-v, N-noFcsNw-v PASS; gate open** | **for review** |
| **M2-S6** | — | **PASS 1863/1863; D0 8/8; E0b 3/3** | **for review** |
| S7.2a CP1 | PASS (T0-R ×5 reviewed) | — | closed |
| S7.2a CP2 r2, I-2H | — | PASS 2391/0, controls 13/13; I-2H PASS | accepted (R181b) |
| R-4 legacy identity | FAIL kept | adjudicated | accepted (R181b) |

## 8. Remaining limitations and unresolved items

1. **Review needed:** C8-v, N-tseSlot-v, N-noFcsNw-v (with S3o and `M2S4R-offset`), and the M2-S5 → M2-S6 gate. M2-S6 is conditional on them and on R2b-v.
2. **C8-v (d) assumes a lossless 5GS** (addendum 2); applicable on 1.8.1 M2-S5, not on 1.8.0 load runs.
3. **S3 blindness** for a slave that starts exact (now shown for N-noFcsNw as well as N-noFcsDs); the replacement adds the offset, the historical S3 is unchanged.
4. **Replacement controls are seed 0 only**, as the historical controls.
5. **M2-S6 hypotheses** H8 (29 configs) and H1c E-sig100 remain refuted, as on 1.8.0 (reported, not gating).
6. **Historical failures kept:** M2-S5 `check.txt` 66/71, M2-S4 R2b, M2-S0 A7, M2-S1 C10, M1 R-ingress / R-egress, R-4.
7. **Not re-run here:** the R181b 1.8.0 evidence for the earlier rows; the reviewer's VM NED / INI patch (separate).

## 9. Raw outputs and incidents

- Every raw output was hashed (`r181c-files.sha256`, per-configuration `r181c-manifest.txt`) before deletion; deletions are logged in `deleted-raw.txt`. Nothing pre-existing was deleted or moved; E0 evidence untouched.
- 1.8.0 evidence (`out-r181c-ctl180`, 8 configs) and the addendum-2 diagnostic (`out-r181c-diag180`, 2 configs) were manifested and deleted.
- Disk stayed above 1.6 GB throughout; the 300 MB guard never triggered.
- Incidents: the addendum-1 checker exception (gate closed, fixed, re-evaluated); the 1.8.0 evidence script ran while the main driver was stopped (unaffected by the fix).
