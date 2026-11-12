# M2-R181b: corrective milestone — plan, criteria changes and predictions

Declared before any verdict run of this milestone.

**Decision.** Review of 2026-11-12, "M2-R181 — Validation Gate Review and Next Actions".

**Baseline kept intact:**
- Commit `83f2704` and every M2-R181 record.
- The frozen 1.8.0 records, the M2-R181 predictions and every historical checker.

**Out of scope until review:** Q1–Q4, E2, S7.2a quantitative scaling, new M2 features, and the reviewer's VM corrections (separate review; this environment is OMNeT++ 6.4.0, not the reviewer's 6.5.0).

## 1. Preservation rules (unchanged from M2-R181, restated)

- No 1.8.0 record, M2-R181 record, prediction or historical checker is modified.
- Failed rows keep their FAIL.
- Every new row is added alongside the historical one, in a new file:
  - `m1/check/check_v181b.py`
  - `m1/check/check_o_tail_v181.py`
  - `m2/check/check_v181b_m2.py`
- Every new row runs three ways:
  - on 1.8.1;
  - on 1.8.0 outputs as a control;
  - on an in-memory mutation, which must FAIL.
- All runs use unmodified Simu5G 1.8.1, or the accepted 1.8.0 build for controls, in isolated results roots.
- Raw data is deleted only after its manifest (`manifest.sh`: every file's sha256, per-configuration counts and bytes) and its checks.

## 2. Root causes (record `root-causes.md`; diagnostic, no verdict)

| Discrepancy | Cause | Kind |
|---|---|---|
| M2-S4 R2b, 736 ns | The talker's own INET Pdelay_Req (timer on the slave clock, `Gptp.cc:100/118`) and the talker application's frame start at the same simulation time on 1.8.1; the frame queues 640 + 96 ns at the talker's egress, before the latency measurement starts. All arrivals are identical | acceptance criterion |
| M1-S5 S5-R-egress-v, 224 ns | The INET measurement starts before the near translator's eth[0] MAC queue. A 94-B Follow_Up stored and forwarded right behind a 122-B frame waits 1040 − 816 = 224 ns; sample = PCAP transit + serialisation + egress wait, exactly, for all 1073 samples | acceptance criterion (my M2-R181 bound) |

## 3. Acceptance-criteria changes (new rows; historical rows unchanged, FAIL kept)

| Historical row (verdict kept) | New row | Why the old row is not version-appropriate | New row asserts |
|---|---|---|---|
| M2-S0 A7 (FAIL on 1.8.1) | **A7-v** | It requires frame loss after the TX RLC with 5 HARQ processes (the 1.8.0 HARQ defect #310) | PCAP conservation across the 5GS for M2S0-load and -harq16:<ul><li>every leaving frame byte-identical to an entering one, once, in order per flow;</li><li>everything else entered in the last 100 ms (still inside)</li></ul>Same rule for 5 and 16 HARQ processes |
| M2-S1 C10 (FAIL) | **C10-v** | Same requirement as A7 | Same as A7-v, on M2S1-load and -harq16 |
| M2-S4 R2b (FAIL) | **R2b-v** | §2 | Same frames delivered; every arrival identical; send times identical except frames queued behind their station's own Pdelay_Req (listed) |
| M1-S5 R-ingress (FAIL) | **S5-R-ingress-v** | The counted module carries both directions; 1.8.1 keeps the other direction's tags (#309) | Tagged at UPF bridge (UE) fcsInserter = started at nwTt (dsTt) + recorded at nwTt (dsTt), per seed; reduces to the old row on 1.8.0 |
| S5-R-egress-v (FAIL, M2-R181 row) | **S5-R-egress-v2** | §2 | Exact relation to 1 ns, plus counts per seed |
| M1 O-tail (checker crashed) | **`check_o_tail_v181.py`** | Absence of cuts raised a `TypeError` in two format strings | Same rows, same verdict logic; "none" is printed for no cut. On 1.8.0 outputs it must reproduce the committed `O-tail/check.txt` byte for byte |
| S7.2a T0-R ×5 (FAIL) | none: reviewed (`t0r-review-diag.txt`) | Cross-version reproduction of 1.8.0 records | See §5 |
| `g0_identity.sh` R-4 (FAIL, 3 files) | none: adjudicated (`R-4-adjudication.md`) | — | Verdict kept |

## 4. Execution (checkpointed; nothing that already passed is rerun without need)

### 4.1 Roots

| Root | Contents |
|---|---|
| `out-r181b-m2` | M2 family on 1.8.1 |
| `out-r181b-cp2` | CP2 r2 and I-2H on 1.8.1 |
| `out-r181b-ctl180` | 1.8.0 controls |

All three are new and isolated.

### 4.2 M2 family (`run_m2.sh`)

**Order:** m2s0 → A7-v → m2s1 → C10-v → m2s4 → R2b-v → dependency gate (§4.3) → m2s5 → m2s6.

**Why each rerun is needed:**
- m2s0, m2s1: A7-v and C10-v need their raw runs, which were deleted in M2-R181.
- m2s4: M2-S5 reads its raw runs, and R2b-v must run on them.
- M2-S3 is not rerun (24/24 PASS in M2-R181).

**Deletions, each after its manifest:**

| Data | Deleted when |
|---|---|
| M2-S0 runs | after A7-v |
| M2-S1 runs | after m2s4 |
| M2-S4 configs not read by M2-S5 (all except M2S4, -frag, -load, -load-harq16; per `gate_m2s5.py` / `check_m2s5.py`) | after the gate |
| M2-S4 runs | after m2s5 |
| M2-S5 and M2-S6 runs | after m2s6 |

**Disk guard:** 300 MB.

### 4.3 M2-S4 → M2-S5 dependency gate (`m2s4_dependency_gate.sh`; explicit, recorded)

`m2s4.sh` stops before writing `raw-outputs.sha256` when its check fails. The gate writes that file with the runner's own hash command only if all of:
1. G1: R2b is the only FAIL row of `M2-S4/check.txt`;
2. G2: R2b-v PASSes on the same runs, and its mutation control FAILs.

The gate writes `DEPENDENCY-GATE.txt` either way. The hashes are of the real outputs; nothing is edited.

**M2-S5 and M2-S6 verdicts read through this gate are conditional on the reviewer's acceptance of R2b-v.**

### 4.4 CP2 r2 and I-2H (`run_cp2_batch.sh Q`, then `D`)

**What was already evaluated in M2-R181.** Block B was evaluated on 1.8.1 only by `check_m2s72_b.py` (1780 rows PASS). The EOR rows, I-4 stream rows, Block H16, and the Stage 4 and I-2H controls of the CP2 r2 checker were never evaluated on 1.8.1, and those raw runs are deleted. The matrix is therefore rerun, in two batches.

| Batch | Configurations | Seeds | Configs |
|---|---|---|---|
| Q | B-q0 ×9; B-qdu-Ca-n1; H16-q0-Ca-n2, n4; H16-qdu-Ca-n2 | 0–4 | 13 |
| Q | H16N-nohold, H16N-hto; BN-rng, BN-theta1 | 0 | 4 |
| D | the other 8 B-qdu configurations, with B-qdu-Ca-n1 moved from Q as their N = 1 reference (evaluated as reference only) | 0–4 | 8 |

Batch Q holds every I-2H configuration, so `check_m2s72_i2h.py focused` runs on it unchanged.

**Evaluation.**
- The unchanged `check_m2s72_cp2r2.py main()` stops with an exception on a partial matrix (shown on an empty one).
- `cp2r2_batch_eval.py eval` calls its unchanged row functions in `main()`'s order, on the configurations present.
- `assemble` requires:
  - every per-run key of the complete matrix in exactly one batch;
  - all 13 controls exactly once.

  It then applies the checker's own verdict rule.

**Commands.** Runs use `m2s72.sh run()`'s command (same ini, configs, repetitions, non-express mode, `--fingerprint=0000-0000/tplx`).

**Disk guard:** no configuration starts below 2 GB free; a running one is stopped below 300 MB.

### 4.5 1.8.0 controls (`run_controls_180.sh`)

**M1:** s4, s5, O-tail on 1.8.0 (isolated). Then:
- s5e and s5i;
- the `check_o_tail_v181.py` byte-identity proof against the committed `O-tail/check.txt`.

**M2:** the load configs and the M2S4 / ctl configs read by A7-v, C10-v and R2b-v.

## 5. Predictions (declared now; not changed afterwards)

### 5.1 New rows

| Row | 1.8.1 | 1.8.0 control | Mutation |
|---|---|---|---|
| A7-v | PASS: 0 still inside with 5 HARQ processes; 2 gPTP still inside with 16 (entered in the last 100 ms) | FAIL: about 2500 DL / 2250 UL missing, entered before end − 100 ms | FAIL |
| C10-v | PASS (as A7-v) | FAIL | FAIL |
| R2b-v | PASS: 10 send shifts of 736 ns:<ul><li>seeds 1, 3, 4, 5, 6, 7, 9;</li><li>at 1.000001776 s, and also at 2.000001776 s in seeds 3, 6, 9;</li><li>0 arrival differences</li></ul> | PASS: 0 shifts (not a defect-detecting row) | FAIL |
| S5-R-egress-v2 (M2-R181 1.8.1 records) | PASS: 1073 exact; waits 224 ns on 19 DL Follow_Ups | FAIL (0 samples) | FAIL |
| S5-R-ingress-v | PASS: DL 1073 = 578 + 495, UL 1074 = 496 + 578 | PASS (reduces to the historical row) | FAIL |
| `check_o_tail_v181.py` | Rows as `M2-R181-predictions.md` O-tail (shortfall, O-S4-1, O-S3-2 FAIL; others PASS; stranding (S4) vacuous PASS) | Output **byte-identical** to the committed `O-tail/check.txt` | — |

### 5.2 Historical checkers rerun on 1.8.1

- **M2-S0, M2-S1, M2-S4 check outputs: byte-identical to the M2-R181 records** in `out-m2full`. The simulations are deterministic.
- **The m2s4 runner stops after its check** (R2b), without writing `raw-outputs.sha256`.
- **The gate opens.**
- **M2-S5 and M2-S6 on 1.8.1:** no row-level prediction (never evaluated; changed timing baseline). Every FAIL is reported and investigated, not reclassified. If m2s5 does not write its hash file (fail-stop), M2-S6 is not run.

### 5.3 CP2 r2 (assembled) and I-2H on 1.8.1

- **CP2 r2:**
  - Block B gate rows PASS (as `b-check-partial.txt`); EOR rows PASS; I-4 stream PASS.
  - Block H16 gate rows PASS with changed counts.
  - Controls 13 / 13 as declared.
  - Verdict PASS.
- **I-2H focused:** gate rows PASS, controls 5 / 5, verdict PASS, counts changed and reported.

**No numeric prediction for:**
- hold / release counts;
- residence;
- RLC accounting.

### 5.4 T0-R review (diagnostic, `t0r-review-diag.txt`, already observed; no prediction)

| Configs | What differs from 1.8.0 |
|---|---|
| qdu-idle, C-a, E-all | Only the column `treeId` of the port logs (OMNeT++'s internal packet-tree id; 1.8.1 `GtpUser` reuses packets instead of allocating new ones, #309). All PCAPs are byte-identical |
| q0-idle, q0-load (gPTP shares DRB 1 with best effort) | Real DL timing changes: the RLC cut / stranding and HARQ fixes (#310 / #311). In q0-load, 1.8.0 delivered 9550 frames at the DS-TT and 1.8.1 delivers 12081 |

T0-R stays FAIL as a cross-version comparison. It is a functional difference only in the sense that 1.8.1 removes 1.8.0 defects.

**STOP after these, for review.**

## Addendum 1 (2026-11-12 11:35Z, after the batch-Q disk-full incident, before any further CP2 run; the text above is unchanged)

### Incident

- **Batch Q filled the disk at 11:23Z.**
  - The three H16 configurations write about 2–3 GB of raw output each, against ~0.3 GB for the largest Block B configuration.
  - Two of them ran concurrently. The 2 GB start guard does not bound a running pair.
- **No configuration failed.** Every completed run has rc=0.
- **The driver stopped before H16N-hto, BN-rng and BN-theta1.**
- **Operator deletion without manifest.** To regain space, I deleted the completed runs M2S72-B-q0-ideal-n4 and M2S72-B-q0-Eall-n4 before their manifest. They were not evaluated, are logged in `deleted-raw.txt`, and are rerun below.
- **No row of those two runs exists.** The other 12 Q configurations were manifested afterwards (`M2-S7.2a-cp2r2-Q/r181b-*`).

### Changes

1. **Q1.** `cp2r2_batch_eval.py eval` evaluates the 12 present Q configurations (`cp2r2-batch-eval-Q1.txt`).
   - Stage 4 controls, I-2H controls and I-4 q0 are skipped by the presence rule; their configurations are incomplete.
2. **After Q1.** The evaluated Q runs not needed later are deleted (after the manifest): H16-q0-Ca-n4, H16-qdu-Ca-n2, B-q0-ideal-n2, B-q0-Ca-n1/n2/n4.
3. **Batch Q2** (`run_cp2_batch.sh Q2`, JOBS 2).
   - **Runs:** B-q0-ideal-n4, B-q0-Eall-n4 (seeds 0–4), H16N-hto, BN-rng, BN-theta1 (seed 0).
   - **References moved from Q** (evaluated in Q1, reference-only here): B-q0-ideal-n1, B-q0-Eall-n1, B-q0-Eall-n2, H16-q0-Ca-n2. H16N-nohold is also moved; it has no rows of its own and is used only by the I-2H controls.
   - **Q2 evaluates:**
     - the rows of the two n4 configurations;
     - I-4 stream q0;
     - the 8 Stage 4 and 5 I-2H controls.
   - **`cp2r2_batch_eval.py` change:** a reference-only configuration is now also excluded from the H16 rows (not only from Block B), so no row is evaluated twice.
4. **Batch D** is unchanged.
5. **Assembly over Q1, Q2 and D.** `assemble` now takes any number of evaluation files; the rules are unchanged. Every per-run key must appear exactly once, and all 13 controls exactly once.
6. **`check_m2s72_i2h.py focused` is not run.**
   - It needs all seven I-2H configurations at once (about 9.5 GB).
   - Its content is the same function calls as the CP2 r2 H16 section and I-2H controls (`I.evaluate_h` with the B-<opt>-Ca-n1 references, H-nv, `I.controls`), all of which the assembled record contains.
   - **The I-2H verdict is therefore taken from the assembled record:** the H16 rows plus the 5 I-2H controls. There is no separate focused record.

### Predictions

Unchanged (§5.3).
