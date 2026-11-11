# M2-R181: Simu5G 1.8.1 integration baseline — validation record and report

**Decision.** 2026-11-11 14:14: B → A → C, runner isolation with four safeguards, stop at the validation gate.

**Branch:** `m2/simu5g-1.8.1` (from `14d5e0f`).

**Stack:**
- OMNeT++ 6.4.0 and INET 4.7.0.
- **Simu5G 1.8.1, unmodified.** Built from `git archive v1.8.1` (`7477d266`) into `/root/stack/simu5g-1.8.1`. `tar --diff` against the tag shows no content difference. `libsimu5g.so` sha256 `0dbda40960e1b5b2…2ddb270131`.
- **Simu5G 1.8.0 baseline:** untouched (`203cf231…`). No 1.8.0 record was modified.

**Gate.** **STOP for review.** No Q1–Q4, no E2.

## 0. Summary

**Verdict: the migration validation is NOT complete.** The gate is reached with failures and with items not evaluated.

**Upstream:**
- U0: 7/7 PASS.
- U1: PASS. One prediction (MAXCI unchanged) was refuted; this is explained below.

**M1 on 1.8.1:**
- S0–S4: every historical row PASS. S1, S2, S2-phase and S3 checks are byte-identical to 1.8.0.
- The flips predicted from the 1.8.0 defects occurred.
- **Two unpredicted flips:** S5 R-ingress, and the O-tail checker aborting.

**Version-neutral rows on 1.8.1:**
- O1-cons 2/2 PASS, with exact conservation and 0 MAC deletions.
- OT-strand 4/4 PASS.
- S5-W-identity-v PASS.
- **S5-R-egress-v FAIL** on the per-sample bound I declared; the counts are exact.

**M2 on 1.8.1:**
- M2-S3: 24/24 PASS.
- M2-S0 A7 and M2-S1 C10 FAIL. These rows assert the 1.8.0 HARQ loss; this was not in my prediction list.
- **M2-S4 R2b FAIL. Unexpected; attribution open.**
- **M2-S5 and M2-S6 not evaluated.**

**S7.2a on 1.8.1:**
- CP1: F0 PASS, and T0 same-version 5/5 PASS.
- CP2 Block B: 1780 gate rows PASS, 0 FAIL, controls 8/8, over the 21 complete configurations.
- **The CP2 revision-2 campaign was not completed** (disk), so I-2H was not evaluated.

**R-4 legacy identity** (§6):
- the script verdict is FAIL on 3 non-checker files, all documented as pre-existing;
- every checker output is byte-identical;
- the 1.8.0 controls of the new rows FAIL where 1.8.0 has the defect.

## 1. What was done (commits on `m2/simu5g-1.8.1`)

| Commit | Content |
|---|---|
| `6a28f04` | Plan revision 2 (four safeguards) |
| `cfc2d39` | Runner isolation (`nt_results.sh`, 18 runners); guard tests |
| `4924091`, `4580205` | Predictions, then addendum 1, both before any 1.8.1 run |
| `ed89c34` | `check_v181.py` (version-neutral rows), `diff_records.py`, run scripts |
| (this commit) | Records, the R-4 legacy proof and this report |

## 2. Upstream (U0, U1)

**U0.** The seven new 1.8.1 module tests all PASS on this build (`u0/runtest.log`).

**U1.** Unmodified `standalone_drb`, 3 s run.

| Simu5G | QOS_PF UDP delivered | MAXCI UDP delivered |
|---|---|---|
| 1.8.0 | 594 / 11601 | 8711 / 11601 |
| 1.8.1 | **9699 / 11601** | **9696 / 11601** |

- QOS_PF ≥ 0.99 × MAXCI: **PASS**.
- **Prediction "MAXCI unchanged ±1 %": refuted** (+11 %).
- **Diagnostic** (`u1/maxci-diagnostic.txt`, the same run with the UE MAC log enabled):
  - 1.8.0: the UE MAC deleted **395** MAC PDUs for lack of a HARQ process (#310).
  - 1.8.1: 0 deletions, and 423 "grant is not used" events.
- **Consequence:** the 1.8.0 MAXCI reference of the #308 reproduction (75.1 %) was itself reduced by #310. The original gNB-only MAC log could not show this.

## 3. M1 on 1.8.1 (`out/m1/`)

| Record | Historical rows on 1.8.1 | Predicted | Agreement |
|---|---|---|---|
| S0, S1, S2, S2-phase, S3, S4 transport / clock | all PASS. S1, S2, S2-phase and S3 `check.txt` byte-identical to 1.8.0 | PASS | ✓ |
| S5 | W-identity **FAIL** (cut clause only: 0 cut SDUs, 578/578 DL); **R-egress FAIL**; **R-ingress FAIL** | W-identity and R-egress FAIL; R-ingress PASS | **R-ingress not predicted** (see below) |
| O-S3-1 | frame loss, H1, H4, H5, residual: FAIL. H2, H3, RTT, counterfactual: PASS | the five FAIL; the others no prediction | ✓ |
| O-tail | **the historical checker aborted** (`TypeError`: `first_cut` is None — no cut SDU exists); no row printed | shortfall, O-S4-1, O-S3-2 FAIL; the others PASS | **crash, not predicted**; all rows unreported |
| upstream-issues | Issue 1 loss and deletion rows, Issue 2 cut and effect rows, Issue 3: FAIL. "Issue 1: not radio / overflow / no statistic" PASS (vacuous: no loss) | predicted that row FAIL | **1 row mispredicted** |

**Unpredicted S5 R-ingress.** The row requires "tagged at translator = tagged at the last INET module before the 5G system" per direction. On 1.8.1 the UPF bridge FCS inserter counts:
- DL: 1073 = 578 + 495;
- UL: 1074 = 496 + 578.

The frames of the opposite direction now arrive tagged (#309). The row's equality held on 1.8.0 only because those tags were lost.

**New rows on 1.8.1** (`out/m1/v181-*-check.txt`):

| Row | Result |
|---|---|
| S5-W-identity-v | PASS |
| **S5-R-egress-v** | **FAIL** — details below |
| O1-cons O1-drain / O1-harq16 | **PASS / PASS** — details below |
| OT-strand | **PASS** ×4 — details below |

**S5-R-egress-v:**
- Recorder samples = frames crossed, exactly, in all 10 seeds (seed 0: DL 578/578, UL 495/495).
- Per sample, matched in order, elapsed − PCAP transit = **exactly that frame's serialisation time** for 1054 of 1073 samples.
- **19 DL gPTP 94-B frames exceed it by 224 ns.**
- The bound I declared ("within the serialisation time + 1 ns") is therefore violated. The cause of the 224 ns is not attributed.

**O1-cons:**
- 64565 SDUs per direction delivered, 0 queued / segmented / in-HARQ / before-RLC, UNEXPLAINED 0, MAC-deletion trace count 0.
- The HARQ5 2 s drain does empty the backlog on 1.8.1.

**OT-strand:**
- O2-s4 and O2-s4-nodl: stranding events 0, maximum gNB wait 1.999 ms.
- O1-harq16 and O2-flush: nothing left after the drain.

**Mutation controls** (`*-mutation-check.txt`):

| Mutation | Result |
|---|---|
| Identity (one byte altered) | FAIL as required |
| O1-cons (one delivery removed) | UNEXPLAINED 3 → FAIL |
| OT-strand (one PDU delayed past the next arrival) | 275 stranding events → FAIL |

The S5-R-egress-v mutation is uninformative, because the unmutated row already fails.

**1.8.0 controls** (rows must FAIL where 1.8.0 has the defect): §6.

**Numerical changes** (`diffs/m1.md`):
- **S4 clock baseline:** max |offset| per seed 5.26–6.43 → 5.52–6.74 ms. The exact model rows still hold (K-pdelay max error 0.063 → 0.073 ns).
- **S3-load** (saturating, HARQ5, not drained): flows are no longer lost but queue.
  - UL best-effort delivered 0.73–0.89 → 0.92, mean delay ≈ 104 → 277 ms.
  - **DL DRB 1 flows** delivered 1.000 → 0.922, mean delay 5.0 → 193 ms.
  - DL and UL PCP 5 / 6 on their own DRBs: delivered → 1.000.
- **O-S3-1:** UL / DL losses 12222 / 12694 → 0.
- **upstream-issues:** Issue 1 DL 9368 → 11891 of 11891; Issue 2 DL delays {5 ms: 438, 25 ms: 145} → {5 ms: 584}; Issue 3 tagged frames at device[0] 0 → 245.

## 4. M2 on 1.8.1 (`out-m2full/m2/`; attempts 1 and 2 kept under `out/`)

| Record | Result | Note |
|---|---|---|
| M2-S0 | 20/21. **A7 FAIL** | On 1.8.1: 11981/11981 DL and 11897/11897 UL delivered with 5 HARQ processes. The row requires "frames lost after the TX RLC expected (L1)". **Defect-encoding row missing from my predictions** |
| M2-S1 | 27/28. **C10 FAIL** | Same reason: 0 frames lost with 5 processes |
| M2-S3 | **24/24 PASS** | Offline correction oracle |
| M2-S4 | 54/55. **R2b FAIL, unexpected** | See below |
| M2-S5 | **not evaluated** | All runs completed (7.0 GB), but the check aborted: `M2-S4/raw-outputs.sha256` is absent. m2s4 writes it only after a passing check (`set -e`), and R2b failed. This is the runners' fail-stop. Runs hashed, then deleted |
| M2-S6 | **not evaluated** | Stopped by me after start (disk); its two "failed" configs are my kill, not simulation errors |

**M2-S4 R2b.** 10 of 33562 UL application frames have a latency **736 ns lower** with the TT Pdelay engine than in the no-Pdelay control:
- seeds 1, 3, 4 and 5;
- deterministic: identical in two independent attempts;
- in seed 3, the frames are sent at t = 1.000001776 s and 2.000001776 s.

Localised per hop (PCAP): talker → dsTt → UE Ethernet is identical. The 736 ns appears **between UE Ethernet ingress and UPF N6 egress**, i.e. inside the 5G system. 736 ns is one 92-B frame time at 1 Gb/s. **Cause not attributed.**

The 1.8.0 record has 0 differing frames. The row's claim "latency changes come only from removing Pdelay from the 5GS" therefore does not hold on 1.8.1 for these frames.

**Numerical changes:** `diffs/m2.md`:
- 52 matched lines with changed numbers, over M2-S0, S1, S3, S4.
- M2-S3 keeps all PASS verdicts; 17 of its lines have changed numbers.
- The M2-S5 check is absent on 1.8.1, so all 72 of its 1.8.0 verdict words appear as removed.

**Diff totals:**

| Diff | Verdict-bearing changes | Lines with changed numbers |
|---|---|---|
| `diffs/m1.md` | 31 | 16 |
| `diffs/s72-cp1.md` | 42 (re-aligned lines; tallies F0 unchanged, T0 PASS 11 / FAIL 1 → 6 / 6) | 7 |

CP2 r2 has no 1.8.0 counterpart file to diff, because the 1.8.0 CP2 r2 record is the complete-campaign check.

## 5. S7.2a on 1.8.1 (`out-s72/m2/`)

**CP1 (I1):**
- F0 verdict **PASS**: verdict tallies identical to 1.8.0 (118 PASS / 21 FAIL words, the FAILs being the negative controls); controls 6/6.
- **T0 same-version rows 5/5 PASS**: the N = 1 `M2S72Bridge` reproduces its 1.8.1 reference runs frame by frame.
- **T0-R 5/5 FAIL.** The 1.8.1 reference runs do not reproduce the committed 1.8.0 records (10 differing measurement-layer CSV files). No prediction; this is a cross-version comparison.

**CP2 revision 2 (I2 / I3):**
- **The campaign could not complete.** Its raw outputs reached 9.3 GB and the disk filled; the 1.8.0 record has no raw size to compare, because its raw outputs are deleted.
- The 21 complete configurations (all 18 Block B, BN-rng, BN-theta1, H16-q0-Ca-n2) were evaluated with `check_m2s72_b.py` (`b-check-partial.txt`):
  - **1780 gate rows PASS, 0 FAIL**;
  - **controls 8/8 as predicted**;
  - the only FAILs are "run missing" for the Block H configurations that the r2 campaign does not run.
- **I-2H (H16 n4, qdu n2, H16N controls) not evaluated.**
- **The CP2 revision-2 verdict is therefore not established.**

## 6. R-4 legacy identity and 1.8.0 controls of the new rows

**Run.** The 16 G0 runners in **legacy mode** (no `NASCTIME_RESULTS_ROOT`), on Simu5G 1.8.0, in a git worktree of `cfc2d39` (the runner-isolation commit). All 16 runners exited rc=0 (`g0-legacy/g0.log`).

**Order.** Under the disk allowance, the first driver (`g0_legacy_lowdisk.sh`) was stopped by me at m1/s0: m2s6 needs the 6.6 GB of M2-S5 runs, which would otherwise have been held through M1. `g0_legacy_lowdisk_cont.sh` ran m2s6 next, then M1 from a reset `m1/` tree. Only the order between the independent M1 and M2 families changed. Raw outputs in the worktree are scratch duplicates; they were hashed (`g0-legacy/worktree-untracked.sha256`) before the worktree was removed.

**Result of `g0_identity.sh`** (`g0-legacy/identity.txt`), over 233 tracked record files:

| Class | Files |
|---|---|
| IDENTICAL (byte-for-byte; includes every checker output of M1 and M2-S0…S6) | 209 |
| METADATA (env*.txt run metadata only) | 15 |
| RUNHEADER (only .sca / .vec / .csv hash lines differ) | 6 |
| **DIFFERS / MISSING** | **3** |

**Script verdict: R-4 FAIL (3 files).** I report the verdict as computed. Each of the three is a difference that earlier G0 records already document as pre-existing; none is in a checker output:

| File | Difference | Earlier record |
|---|---|---|
| `m1/results/O-tail/raw-outputs.sha256` | MISSING: `o_tail_investigation.sh` starts with `rm -rf results/O-tail` and never writes it (only .sca/.vci/.vec hashes). Runner change in `cfc2d39` does not touch this | M2-S5 results §7: "pre-existing behaviour; the file was restored" |
| `m1/results/S0/fingerprints.log` | the unittest wall-clock line only (3.007 s → 2.806 s); 4/4 fingerprints OK | M2-S5 results §7 (3.007 → 3.009 s) |
| `m2/results/M2-S5/env.txt` | a hand-added annotation line in the committed file (`check_txt: check_m2s5.py at 8bcfc14 … rerun`), which no runner writes; everything else is run metadata | not in the earlier rule; `g0_identity.sh` is stricter than the rule, because only listed metadata keys are tolerated |

**Conclusion.**
- Legacy behaviour is unchanged by the isolation commit: every checker output is byte-identical, and every reproducible raw-output hash is identical.
- The script's FAIL is due to the three items above. I did not edit the script or the rule after seeing the result. Whether to accept them is your decision.

**Controls of the new rows on the 1.8.0 legacy outputs** (`g0-legacy/v181-*-on-1.8.0.txt`):

| Row | 1.8.0 prediction | 1.8.0 result |
|---|---|---|
| S5-R-egress-v | FAIL (0 samples) | **FAIL**: DL 0 samples / 577 frames, UL 0 / 495 ✓ |
| S5-W-identity-v | PASS | **PASS** (DL 578 in, 577 out, 1 still inside) ✓ |
| O1-cons | FAIL (deletions > 0) | **O1-drain FAIL**: UNEXPLAINED UL 12222 / DL 12689 (= the historical O-S3-1 losses), 855 MAC PDU deletions in the seed-0 trace ✓. **O1-harq16 PASS** on 1.8.0 (0 deletions, everything delivered): the prediction did not split by config, so the control discriminates only on O1-drain |
| OT-strand | FAIL on O2-s4 (277 stranding events); O1-harq16 / O2-flush one SDU left | **O2-s4 FAIL with 276 events** (prediction said 277), max gNB wait 20.998 ms; O2-s4-nodl PASS; **O1-harq16 and O2-flush FAIL**, one SDU left ✓ |

The O1-cons table column "in-HARQ" is the candidate count of completed-but-undelivered SDUs. When those SDUs are not late (within `W_HARQ` of the end) or delivery order breaks, the same count is reported as UNEXPLAINED. That is what happens on 1.8.0 O1-drain.

## 7. Deviations and incidents (all disclosed)

1. **The predictions missed defect-encoding rows.** M2-S0 A7, M2-S1 C10 and upstream-issue 1 "not radio …" were not listed, and S5 R-ingress was not anticipated.
2. **Two disk-full events** stopped running work:
   - attempt 2 of m2s5;
   - CP2 revision 2.

   Partial outputs are kept as records. Raw outputs were hashed before every deletion (`deleted-raw.txt` in each root).
3. **M2 attempt 1 failed by ordering.** In a fresh root, m2s1's check needs M2-S0's hash file, so m2s0 must run first. The order was fixed in `run_m2_family_lowdisk.sh`, and attempt 1 is kept.
4. **The first legacy-proof attempt was invalidated** by my deleting M2-S1 runs before m2s4 had read them. It was killed and rerun from a clean worktree.
5. **R-4 criterion wording.** Plan R-4 said every `raw-outputs.sha256` must be byte-identical. Lines for `.sca` / `.vec` / `opp_scavetool` CSV files embed the run id and date, and differed in every earlier G0 too. `g0_identity.sh` applies the established rule: those lines and env metadata may differ; everything else must be identical.
6. **Lossless compression** (gzip) of some 1.8.1 CSV exports to free space; the hashes of the uncompressed files are recorded.
7. **The legacy proof used the commit `cfc2d39`** (runner change). The runners are unchanged after it.
8. **The legacy proof was reordered mid-run** (§6); m1/s0 ran twice (first completed rc=0, then reset and rerun).
9. **`~/.cache/uv` was deleted again** to free 425 MB during m2s5 (package cache, not evidence).
10. **VM NED corrections:** not touched; they await your diff as a separate commit (plan §4).
