# M2-R181b closure report: Simu5G 1.8.1 corrective milestone

**Branch.** `m2/simu5g-1.8.1`, 13 commits on top of `83f2704`; the M2-R181 records are untouched. Plan and predictions in `M2-R181b-plan.md`, with addenda 1 and 2.

**Stack.**
- OMNeT++ 6.4.0, INET 4.7.0.
- Simu5G 1.8.1, unmodified.
- The accepted 1.8.0 build for the controls.

This environment is not the reviewer's OMNeT++ 6.5.0 VM.

**Stop.** No Q1–Q4, no E2, no S7.2a quantitative scaling, no new M2 features. The VM NED / INI corrections were not touched.

## 1. Summary

1. **Root causes found for both timing discrepancies, with exact cycle accounting** (`root-causes.md` §1, §2). Neither is a 5G-system, Simu5G 1.8.1 or nascTime implementation defect; both rows assumed a boundary that does not hold.
   - **R2b, 736 ns:** the talker's own Pdelay_Req collides with an application frame at the talker's egress.
   - **S5-R-egress-v, 224 ns:** the INET measurement includes the near translator's egress wait.
2. **R-4 adjudicated** (`R-4-adjudication.md`). The script FAIL is kept. All three differences predate the runner change (two are reproduced at `14d5e0f`) and change no reproducible output.
3. **New version-appropriate rows** alongside the unchanged historical ones: A7-v, C10-v, R2b-v, S5-R-egress-v2, S5-R-ingress-v, and the no-cut-safe O-tail checker copy. Every new row behaves as predicted on 1.8.1, on 1.8.0 and under mutation.
4. **S7.2a CP2 revision 2 on 1.8.1: PASS.**
   - Assembled from three batches: 2391 gate rows PASS, 0 FAIL; controls 13/13.
   - Per-family row counts are identical to the 1.8.0 record, with 0 verdict changes on common rows.
   - **I-2H: PASS** (40 I-2H rows, 5 I-2H controls).
5. **M2-S5 on 1.8.1: FAIL (66/71). Not predicted, cause established** (`root-causes.md` §3).
   - **C8:** its "as in M2S4" counter includes the DS-TT's own Pdelay responses. Their number depends on the slave clock rate, which differs between M2S4 and M2S5 by design.
   - **Two controls lose sensitivity on 1.8.1** (N-tseSlot, N-noFcsNw S3).
   - **Consequence:** the runner's fail-stop holds, so **M2-S6 was not run**. I did not open a second gate.

## 2. Root-cause investigations (deliverable items 1–5)

| | M2-S4 R2b, 736 ns | M1-S5 S5-R-egress-v, 224 ns |
|---|---|---|
| 1. First divergence | Talker eth[0] egress, seed 3, t = 1 s: the application frame ends at 1.000001776 s instead of 1.000001040 s, behind a 72-B Pdelay_Req (1.000000640 s). The UE ingress is also shifted by 736 ns. The UPF N6 egress (1.006001225 s) and the listener arrival (1.006002365 s) are identical | Per sample: INET sample − PCAP transit − own serialisation = egress wait at the near translator's eth[0], exactly, for all 1073 samples. Non-zero only for the 19 DL Follow_Ups (94 B) |
| 2. Exact cause | INET `Gptp` schedules the slave's Pdelay timer on its clock (`Gptp.cc:100`, `:118`). With 1.8.1's Sync timing, the slave clock reaches k s at exactly the simulation time of the talker application's k-second frame, in 7 of 10 seeds. The frame queues 640 ns (frame) + 96 ns (IFG) behind the Pdelay_Req. The control has no talker Pdelay (`pdelayInitialOffset = 10s`). Latency is measured from the talker's transmit end, so it shrinks; the 5G system's TTI-quantised UL delivery is unchanged | The INET measurement starter sits before the near translator's eth[0] MAC queue (S5 ini). A 94-B Follow_Up, stored and forwarded directly behind a 122-B frame, waits 1040 − 816 = 224 ns. The upstream TSN-side effect is version-independent; on 1.8.0 the samples were never recorded |
| 3. Supporting code and events | `Gptp.cc`; `omnetpp.ini` `[Config M2S4-ctl-nopdelay]`; `diag-r2b-all-1.8.1.txt` (10 / 10 differing frames are all queued behind the talker's Pdelay_Req; Pdelay_Req starts per seed); `diag-r2b-all-1.8.0.txt` (no collision, 0 differ) | `m1/omnetpp.ini` `[Config S5]`; `s5-egress-per-frame.csv` (all 1073 samples: value, transit, serialisation, wait, gap to the previous frame = 96 ns); listener / nwTt PCAP frame sequence |
| 4. Correction | **Acceptance criterion:** "exactly the latencies of the control" is not a property, only a phase coincidence on 1.8.0 (400 ns margin). Implementation: none | **Acceptance criterion:** my M2-R181 bound "within serialisation + 1 ns" ignored the egress wait. Implementation: none |
| 5. Minimal regression test | **R2b-v** (`check_v181b_m2.py r2b`):<ul><li>same frames delivered;</li><li>every arrival identical;</li><li>send times identical except frames queued behind their station's own Pdelay_Req.</li></ul>Mutation: one arrival + 1 ns → FAIL. Reproducer: M2S4 vs ctl, seed 3 | **S5-R-egress-v2** (`check_v181b.py s5e`): the exact relation to 1 ns, plus the counts per seed. Mutation: one sample + 2 ns → FAIL; 1.8.0: FAIL (0 samples) |

**Correction to the M2-R181 report.** It located the 736 ns "inside the 5GS (UE Ethernet ingress → UPF N6)". That is true only of per-hop transit. The first divergence in absolute time is at the talker's egress.

## 3. Status of every failed or unevaluated gate

| Gate (M2-R181 status) | Historical row (kept) | M2-R181b result on 1.8.1 | 1.8.0 control | Mutation | Status |
|---|---|---|---|---|---|
| M2-S0 A7 (FAIL) | FAIL; check byte-identical to M2-R181 | **A7-v PASS**: 11981 / 11981 DL and 11897 / 11897 UL with 5 HARQ processes; 2 gPTP frames still inside with 16 (last 100 ms) | FAIL: 2529 DL / 2255 UL missing | FAIL | resolved by the new row (review) |
| M2-S1 C10 (FAIL) | FAIL; byte-identical | **C10-v PASS** (as A7-v) | FAIL | FAIL | resolved by the new row (review) |
| M2-S4 R2b (FAIL) | FAIL; byte-identical; `m2s4.sh` fail-stop | **R2b-v PASS**: 33562 frames; 10 send shifts of 736 ns, all behind the talker's own Pdelay_Req (seeds 1, 3, 4, 5, 6, 7, 9), exactly as predicted; 0 arrival differences | PASS (0 shifts) | FAIL | root cause established; resolved by the new row (review) |
| M2-S4 → M2-S5 dependency | — | **Gate opened** (`DEPENDENCY-GATE.txt`): R2b the only FAIL; R2b-v PASS; mutation FAIL; hashes from the real outputs by the runner's command | — | — | **conditional on accepting R2b-v** |
| M2-S5 (not evaluated) | **FAIL 66/71**: C8, N-tseSlot, N-noFcsNw, N-noStrip, N-fwdPdelay | All other 66 rows PASS, including C1–C7, S1–S3, P1–P2, H1–H5 | — | — | **FAIL kept**; cause established (`root-causes.md` §3); proposed C8 form not applied |
| M2-S6 (not evaluated) | — | **not run**: `m2s5.sh` wrote no `raw-outputs.sha256` (fail-stop) | — | — | **blocked by M2-S5** |
| M1 S5 R-ingress (FAIL) | FAIL | **S5-R-ingress-v PASS**: DL 1073 = 578 + 495, UL 1074 = 496 + 578, all seeds | PASS (reduces to the historical row) | FAIL | resolved (review) |
| S5-R-egress-v (FAIL) | FAIL | **S5-R-egress-v2 PASS**: 1073 / 1073 exact | FAIL (0 samples) | FAIL | root cause established; resolved (review) |
| M1 O-tail (checker crashed) | crash, unchanged | **`check_o_tail_v181.py`**: shortfall, O-S4-1, O-S3-2 FAIL (no cut SDU on 1.8.1: the 1.8.0 explanations no longer apply); replays and counterfactual PASS; stranding (S4) PASS vacuously (0 cuts) | **byte-identical** to the committed 1.8.0 `O-tail/check.txt` | — | defined observation; verdicts as predicted |
| S7.2a T0-R ×5 (FAIL) | FAIL | Reviewed (`t0r-review-diag.txt`) | — | — | cross-version difference, not a functional failure (see below) |
| S7.2a CP2 r2 (incomplete) | — | **PASS**: 2391 / 0; controls 13/13; EOR 250/250; I-4 stream 10/10; H16 rows PASS | — | — | **closed** |
| I-2H (not evaluated) | — | **PASS**: I-2H 40/40, I-5 75/75, H-cov 20/20, H-nv 1/1, 5 / 5 I-2H controls | — | — | **closed** (from the assembled record) |
| R-4 legacy identity (FAIL, 3 files) | FAIL | Adjudicated | — | — | historical / non-semantic exceptions; no output changed |

**T0-R detail:**
- **qdu-idle, C-a, E-all:** only the `treeId` column of the port logs differs. That is OMNeT++'s internal packet-tree id, changed by #309 packet reuse. All PCAPs are byte-identical.
- **q0-idle, q0-load** (gPTP on the best-effort DRB): real DL timing changes from the #310 / #311 fixes. In q0-load the DS-TT receives 9550 frames on 1.8.0 and 12081 on 1.8.1.

## 4. Changes to acceptance criteria

- **No historical row, checker or record was changed.** The new rows are added alongside them; every failed row keeps its FAIL.
- **Why each new row replaces its predecessor:** `M2-R181b-plan.md` §3.
- **What each new row is stricter or more exact about:**

| Row | What it asserts |
|---|---|
| A7-v / C10-v | Byte identity, exactly once, in order, and conservation, with the same rule for 5 and 16 HARQ processes, instead of "loss expected with 5" |
| R2b-v | Exact equality of every arrival, and an exact attribution of every send-time difference |
| S5-R-egress-v2 | An exact identity to 1 ns, instead of a ±serialisation bound |
| S5-R-ingress-v | Counts both directions at the module that carries both; reduces to the old row on 1.8.0 |
| `check_o_tail_v181.py` | No criterion change; the no-cut case is printed instead of raising, and the copy is byte-identical on 1.8.0 outputs |

**Process changes (recorded, not criteria):**
- the explicit M2-S4 dependency gate;
- the CP2 batch evaluation, which calls the unchanged row functions, because `main()` cannot handle a partial matrix;
- the assembly rule;
- one assembler fix: the I-4 stream pair rows had been counted as per-run keys. The first assembly output is kept as `cp2r2-assembled-v1-keybug.txt`.

**Proposed, NOT applied:**
- A C8 form that excludes the DS-TT's own Pdelay responses from `framesUntaggedAtEgress`.
- Re-declared 1.8.1 controls N-tseSlot and N-noFcsNw (S3), which lose sensitivity on 1.8.1.

## 5. Coverage actually achieved on Simu5G 1.8.1

| Area | Evaluated on 1.8.1 | Not evaluated |
|---|---|---|
| Upstream | U0 7/7, U1 (M2-R181) | — |
| M1 | S0–S5, O-S3-1, O-tail (copy), upstream-issues, plus O1-cons, OT-strand, S5-W-identity-v, S5-R-egress-v2, S5-R-ingress-v | — |
| M2 | M2-S0, M2-S1, M2-S3 (M2-R181), M2-S4, A7-v, C10-v, R2b-v, M2-S5 (FAIL) | **M2-S6** |
| S7.2a | CP1 (F0, T0) (M2-R181), CP2 r2 complete, I-2H | E0 / E2 (out of scope) |
| Legacy (1.8.0) | R-4 G0 proof; controls of all new rows | — |

## 6. Incidents and deviations

1. **The CP2 batch Q filled the disk** (11:23Z).
   - **Cause:** H16 configurations write about 2–3 GB each; two ran concurrently past the 2 GB start guard.
   - **Damage:**
     - To regain space, I **deleted two completed runs before their manifest** (B-q0-ideal-n4, B-q0-Eall-n4). They were never evaluated, and were rerun in Q2.
     - H16-qdu-Ca-n2 was truncated by the full disk: invalid, deleted after the manifest, rerun in D.
   - **Records:** plan addenda 1 and 2, committed before the further runs; `deleted-raw.txt`.
2. **`check_m2s72_i2h.py focused` was not run separately.** It needs all seven I-2H configurations at once (about 9.5 GB). The same functions are in the assembled record.
3. **M2-S5 was evaluated with no row-level prediction** (declared). Its FAIL is reported as is.
4. **Raw outputs.** Every raw output of this milestone was manifested (sha256 of every file) before deletion. The one exception is item 1. Nothing pre-existing was deleted. The E0 and other earlier scratch evidence is untouched.

## 7. Remaining blockers (for review)

1. **Accept or reject the new rows and the M2-S4 → M2-S5 dependency gate.** The M2-S5 and M2-S6 verdicts depend on R2b-v.
2. **M2-S5 C8 and the two insensitive controls (N-tseSlot, N-noFcsNw S3).**
   - Needed: a reviewer decision on the proposed C8 form, and on re-declaring those controls for 1.8.1.
   - Then: M2-S5 rerun, then M2-S6, which has never been evaluated on 1.8.1.
3. **The reviewer's VM NED / INI corrections** (separate commit, pending the patch).
4. **Disk.** The 11 GB allowance limits M2-S5 / M2-S6 to one family at a time and CP2 H16 to one configuration at a time. Additional disk would remove the batching.
