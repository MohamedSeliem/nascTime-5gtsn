# M2-R181 predictions (declared before any nascTime run on Simu5G 1.8.1)

**Basis.** The plan (`M2-R181-plan.md`) and the v1.8.0 → v1.8.1 source diff (`git diff v1.8.0 v1.8.1`, read 2026-11-11).

**Rules:**
- Historical checkers run unchanged.
- A row predicted to FAIL is reported as FAIL. It is never reclassified, and a prediction never makes a row pass.
- A row marked **"no prediction"** is reported as observed.
- Every verdict or number that differs from 1.8.0 is listed by `diff_records.py`.
- An **unpredicted verdict change** is a finding: it is reported and attributed, or left open.

## U: upstream

| Id | Prediction |
|---|---|
| U0 | The Simu5G 1.8.1 module tests `SaturatedNrTrafficNoMacLoss`, `FewHarqProcessesLteDlNoMacLoss`, `FewHarqProcessesLteUlNoMacLoss`, `SlowHarqFeedbackNrUlGrants`, `DlCappedGrantKeepsBacklog`, `DlGrantCoversEverySduHeader` and `EthernetSessionFlowMeasurement` PASS on the build used here |
| U1 | The `results/M2-S7.2a-upstream-repro` scenario (unmodified `standalone_drb`, 3 s) on 1.8.1:<ul><li>QOS_PF UDP delivered ≥ 0.99 × MAXCI delivered;</li><li>MAXCI unchanged from 1.8.0 within ±1 % (8711 / 11601);</li><li>no runtime error</li></ul> |

## R: historical rows (G0 suite on 1.8.1)

**Predicted to FAIL, because the row asserts a 1.8.0 defect:**

| Record | Row | Mechanism |
|---|---|---|
| M1 S5 | **R-egress** (requires 0 transit samples) | #309: region tags now cross |
| M1 S5 | **W-identity** — only through its clause "DL SDUs cut and reassembled, delivered intact > 0". Identity, bytes, once, order and still-inside must hold | #311: no light-load cut expected |
| M1 O-S3-1 | **frame loss reproduced**; **H1** (needs frames still missing); **H4** (deletions CONFIRMED); **H5** (deletions unrecorded); **residual with 16 processes** (last DL SDU stranded) | #310, #311 |
| M1 O-tail | **shortfall** (needs ≥ 1 cut); **O-S4-1 explained** (needs late Follow_Ups); **O-S3-2 explained** (needs the stranded last SDU) | #311 |
| M1 upstream-issues | **Issue 1** rows (loss; deletions; not radio / overflow / no statistic); **Issue 2** rows (cuts; effect); **Issue 3** row (tags do not cross) | #310, #311, #309 |

**No prediction:**
- O-S3-1 H2, H3, the HARQ round-trip row and the 16-process counterfactual;
- O-tail stranding, which is vacuous if there is no cut;
- the Issue 2 replay and counterfactual rows;
- S2 / S2-phase timing values;
- M2-S6 stage D load rows (`M2S6-D-load`, `D-load-harq16`).

**Predicted PASS** (verdict unchanged; numbers may change and are listed):
- every other row of S0–S5, O-S3-1, O-tail and M2-S0, S1, S3, S4, S5, S6;
- in particular every exact oracle row: S4 K-rows, M2-S3 offline correction, M2-S4 Pdelay, M2-S5 V0 and the egress correction, M2-S6 O1 / O3 / O5 and C1–C5, the negative controls 19 / 19 and D0 / E0b;
- intra-version gates (M2-S1 → S0 hashes, S5 → S4, S6 → S5) compare against the 1.8.1 runs of the same root.

## New version-neutral rows (`simulations/m1/check/check_v181.py`)

Each new row has three required outcomes:
- on 1.8.1: as predicted below;
- on the 1.8.0 legacy-proof outputs: **FAIL** where 1.8.0 has the defect;
- on a declared in-memory mutation: **FAIL**.

| Row | 1.8.1 | 1.8.0 | Mutation |
|---|---|---|---|
| **S5-R-egress-v**: recorder samples = frames crossed, per direction and seed; each sample = its frame's PCAP transit within that frame's serialisation time at 1 Gb/s + 1 ns | PASS | FAIL (0 samples) | one sample shifted by 1 serialisation time + 2 ns → FAIL |
| **S5-W-identity-v**: identity, bytes, once, order, still-inside, without the cut clause | PASS | PASS | one frame's byte altered → FAIL |
| **O1-cons**: plan §2 equation per (seed, direction, flow), UNEXPLAINED = 0, for O1-drain (HARQ5) and O1-harq16; trace MAC-deletion count 0 | PASS. No prediction whether the HARQ5 2 s drain empties the backlog: if not, the residual is counted in the queued / segmented states, never as loss | FAIL (deletions > 0) | one RLC RX delivery removed → UNEXPLAINED 1 → FAIL |
| **OT-strand**: on O2-s4, O2-s4-nodl, O1-harq16 and O2-flush, stranding events = 0 (residual bytes after a slot and the entity idle ≥ 2 slots until the next SDU arrival); in O2-s4 every SDU's gNB wait (arrival → last byte out) ≤ 2 slots; nothing left in RLC at the end of O1-harq16 | PASS | FAIL (277 stranding events; O1-harq16 leaves 1 SDU) | one PDU delayed past the next arrival → FAIL |

**Out of this milestone:** Q8-zero is not evaluated, because no Stage 5 run is in M2-R181.

## I: S7.2a integration (`m2s72.sh all` = CP1, `m2s72.sh r2` = CP2 revision 2)

| Id | Prediction |
|---|---|
| I1 | CP1 F0 rows: PASS (73 / 73, controls 6 / 6). T0 rows that compare the new network with its own reference runs: PASS. **T0-R** ("reference run reproduces the committed record", which reads the 1.8.0 records): **no prediction**; reported as a cross-version comparison |
| I2 / I3 | CP2 revision 2 gate rows: PASS (2391 / 2391); controls 13 / 13 as declared there. The I-2H hold and release rows hold with **changed counts** (reported). Residence and timing values change (listed) |

**STOP** after these, for review.

## Addendum 1 (2026-11-11, before any 1.8.1 run, while implementing the rows; the text above is unchanged)

**OT-strand scope.**

- **Light-load configs O2-s4 and O2-s4-nodl.** The stranding-event count and the ≤ 2-slot wait are evaluated here only.
  - In the saturated, multi-DRB drain configs (O1-harq16, O2-flush), MaxCI serves one connection per node per TTI. DRB 1 then legitimately idles while other DRBs are served, so "idle until the next arrival" is not evidence of stranding there.
- **Drain configs O1-harq16 and O2-flush.** The row is "nothing left in the gNB DRB 1 RLC after the drain":
  - sources stop at 3 s, with one extra frame at 3.5 s in O2-flush;
  - the run ends at 5 s.
- **Predictions:**
  - 1.8.1: PASS on all four configs.
  - 1.8.0: FAIL on O2-s4 (stranding) and on O1-harq16 / O2-flush (one SDU left).

**O1-cons declared bounds.**

| Bound | Value | Basis |
|---|---|---|
| `W_ETH` (source → RLC TX, and RLC RX → sink) | 1 ms | — |
| `W_HARQ` | 25 ms | 4 transmissions × (5-slot feedback + 1) + 1 slot |

- **Delivered SDUs** must equal the replay's completed SDUs, in order and by size (UM in-order delivery).
- **Completed but undelivered SDUs** must have their last byte after `END − W_HARQ`.
- **MAC loss statistics** (`macPacketLoss*`) must be 0 in these ideal-channel configs.
