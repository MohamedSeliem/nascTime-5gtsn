# WP-A1 — Integration of A-2.1 into the E0v-N per-run evaluation (design)

**Status: revision 1, 18 November 2026. Design for independent review. Nothing is implemented.**
- Baseline: `m2/continuation` at `7bb0e3a7145602ae556239c8667362203d9294b5`; branch `wp/a1-a21-e0vn-wrapper`.
- Level: design only. No code, configuration, record, fixture, workflow or evidence is changed.
- No simulation was run and no private evidence was read.
- Every source fact below was read from the repository at the baseline. File references are `simulations/m2/check/…` unless stated otherwise.

**Decisions this design implements:**
- DR-07a: the campaign contract F1-d(i), plus separately labelled full-contract diagnostics.
- DR-07b: new wrapper rows PU-4h, PU-4o and per-UE A2-8; the A-1 PU-4 is preserved and reported.
- DR-07c: the three validations V-N1, V-N2 and V-V1.
- DR-07d: the first-genuine-occurrence review gate.
- S5-2-D2 remains pending; it waits for independent execution of V-N1 and V-N2.

**Fixed boundaries (never broadened):**
- A2-V1 is NOT ACCEPTED, permanently.
- The A-1 PU-4 FAIL of the N = 2 smoke is retained verbatim.
- A-2 stays frozen at `fbee202`.
- A-2.1 is accepted only as recorded (F3 CLOSED ACCEPTED; A2-V1-S1 CLOSED ACCEPTED under F1-d(i); the full contract INCOMPLETE).
- S7.2a remains partial.

---

## 1. Current architecture (as implemented at the baseline)

### 1.1 The E0v-N per-run path: `check_m2s72_s5n.py run <runs> <cfg> <records>`

1. **Refusal.** The run is refused (exit 2) unless `S5N_ADAPTER_VALIDATED` is set (decision S5-2-D2), or the name does not parse as kind `E0vN` (`check_m2s72_s5v.parse_name`).
2. **Accepted Block B evaluation at N.** `evaluation()` calls `check_m2s72_e0` / `_b` / `_i2h` (unchanged). The rows accumulate in the module-global list `E.rows`. F0-1 is relabelled "F0-1 (info)", and EOR is NOT APPLICABLE.
3. **Per-UE observation.** `m2s72_peru_adapter.observe(ev, run-<cfg>.log.gz, option, loaded, nproc)`:
   - `harq_events()` extracts the gNB insert lines (naming the node) and the feedback lines (naming no UE), in log order;
   - `m2s72_peru.attribute_feedback()` applies **rule A-1**:
     - A-1a: the only open candidate;
     - A-1b: the unique candidate at the single delay d*;
     - otherwise AMBIGUOUS, ORPHAN or RE-INSERT;
   - it returns per-node counts and an occupancy, which is produced only when the attribution is exact, plus a run summary `{a1a, a1b, ambiguous, orphan, reinsert, d_star_ps, a1a_delays_ps}`.
4. **Correctness rows.** `m2s72_peru_adapter.validate()` → `m2s72_peru.structural_rows()`: PU-1 … PU-5, then AV-1 … AV-3.
   - **PU-4 = A-1 complete:** ambiguous = orphan = re-insert = 0.
   - **PU-5:** the per-UE DL grant bytes and per-UE inserts sum to the run totals.
5. **Further rows:** Q8-v, SG-403 and MG-1 (`check_m2s72_s5v`, unchanged).
6. **Verdict.** It is `PASS` only if there is no gate FAIL and no PU / AV row is NOT EVALUATED. The outputs are `<cfg>.check.txt` and `<cfg>.digest.json`; the digest carries `harq_attribution` (the A-1 summary) and the per-UE measurements.

### 1.2 The A-2.1 path, standalone: `check_m2s72_a21.py a21 <runs> <cfg> <records> [--contract full|f1d-i] [--t0 <s>]`

1. **Inputs** (`inputs()`):
   - all MAC-log lines (`m2s72_a21.load`);
   - DL grants (`m2s72_maclog`);
   - node ids `Run72(...).node_id`;
   - `<runs>/<cfg>/<cfg>/0.sca`;
   - `$SIMU5G_ROOT`.
2. **Replay.** `m2s72_a21.evaluate()` → `replay()` builds lifecycle units, handles B-1 … B-6, groups (exchangeable, multi-NACK, pending), retransmissions, discards and structural censoring.
3. **Rows** A2-0, A2-0s, A2-1, A2-2, A2-3, A2-4a, A2-4b, A2-4c, A2-5, A2-6, A2-7, A2-8, A2-9. All are run-level.
   - **A2-7** (`xa_rows`) checks against the independent UE-side reference (`m2s72_harqx`). Its structured output includes `occupancy_equal{node: bool}` and `skipped` (the nodes touched by censored or pending groups).
   - **A2-8** (`scalar_row`) compares Simu5G's `harqErrorRateDl:mean` and `harqTxAttemptsDl:mean` per node, as one run-level row.
4. **Per-UE outputs** (`m2s72_a2.per_ue`, frozen): inserts, transmissions, retransmissions, feedback, ACK, NACK, discarded, end states, line classes and occupancy (`m2s72_peru.occupancy_log_order`).
5. **Verdict.**
   - Any FAIL → `A-2.1 NOT VALID` (rc 1).
   - A required row neither PASS nor NOT EXERCISED → `INCOMPLETE` (rc 4).
   - Otherwise → `VALID` (rc 0).
   - Required rows: `full` = A2-0 … A2-9 including A2-4c, excluding A2-8; `f1d-i` = the same without A2-4c.
   - A2-8 is not required, but a FAIL in it makes the verdict NOT VALID.
6. **Coverage table.** For each feature, A-2.1 reports either "EXERCISED by this input" or "NOT EXERCISED → validated only in <synthetic fixtures>" (`SYNTH`).

### 1.3 The independent reference and the N = 2 smoke tooling

`check_m2s72_s5n2.py xa | controls-n2 | verdict` and `m2s72_harqx.py` provide:
- XA-0 … XA-6;
- the overlap census;
- the truth occupancy, reconstructed from the UE MAC lines `H-ARQ RX: new PDU (id X )` and `feedback sent`.

XA is the oracle that A2-7 reuses.

### 1.4 Frozen and accepted modules (never modified by WP-A1)

| Module | Status | Pin |
|---|---|---|
| `m2s72_a2.py`, `check_m2s72_a2.py`, `m2s72_a2probe.py`, `m2s72_harqfix.py`, `m2s72_harqx.py`, `m2s72_peru.py`, `test_m2s72_a2.py` | **frozen** (A-2, XA, A-1 / PU-4) | `fbee202`, enforced by `test_m2s72_a21.py` T-frozen-untouched |
| `check_m2s72_a2v1.py` | **frozen** (A2-V1 evaluator) | `39a6434`, same test |
| `m2s72_a21.py`, `check_m2s72_a21.py`, `m2s72_harqfix21.py`, `m2s72_a21_fixture.py`, `m2s72_a21_realchain.py` | **accepted**: F3 at `d920125`; S1 evaluated at `ddc1a93`, with zero code difference | treated as frozen by WP-A1 (§3.2, AC-3) |
| `check_m2s72_s5n.py`, `m2s72_peru_adapter.py`, `check_m2s72_s5v.py`, `check_m2s72_s5n2.py` | tooling of accepted S5-1 / S5-2 / N = 2 smoke records | kept byte-identical (the A-2 R-1 precedent) |
| `simulations/m2/check/fixtures/a2v1-first-chain.log.gz` (+ `.sha256`, `.meta.json`) | genuine F3 fixture | sha256 `cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b`, gated by tier-0 |

### 1.5 Recorded facts the design relies on (quoted, not re-derived)

**N = 1 smoke** `M2S72-E0v-q0-f1`, seed 0:
- A-1a 11 697;
- ambiguous = orphan = re-insert = 0.

**N = 2 smoke** `M2S72-E0vN-q0-one0-n2-f1`, seed 0 (`M2-S7.2a-a2-design-review.md` §1):

| Quantity | Value |
|---|---|
| A-1a | 9 718 agree |
| A-1b | 2 476 agree |
| A-1 ambiguous | 768 (384 same-TTI pairs) |
| Re-inserts | 768 |
| Orphans | 0 |
| PU-4 | **FAIL, retained** |
| XA-pre … XA-5 | PASS |
| XA-6 | NOT EVALUATED |
| UE-side NACKs | 0 |

For A-2 on the same run, the records give **declared expectations, not recorded measurements**:
- 12 194 single-candidate lines (12 194 is also the count of lines A-1 attributed: 9 718 + 2 476);
- 384 two-candidate exchangeable groups (768 lines), certified;
- per-UE occupancy equal to the XA truth occupancy.

The sources are control PC-A2-N2 (`-a2-design-review.md` §7.1) and `-a2-implementation.md` §4, whose coverage table labels them "(predicted)". The probe P0's 384 two-candidate groups were the declared expectation of the VM step in `-a2-design-review.md` (the V-C … V-D procedure). V-N2 (§8.3) is therefore the first independent check of these values under A-2.1.

**A2-V1-S1** (`-a21-s1-closure.md` §3–§4), configuration `M2S72-E0vN-q0-one0-n2-f1_A2V1`:

| Metric | Node 2049 (ue[0]) | Node 2050 (ue[1]) | Total |
|---|---:|---:|---:|
| Inserts | 11 702 | 1 265 | 12 967 |
| Transmissions | 11 702 | 1 409 | 13 111 |
| Feedback | 11 697 | 1 408 | 13 105 |
| ACK | 11 697 | 1 264 | 12 961 |
| NACK | 0 | 144 | 144 |
| Retransmissions | 0 | 144 | 144 |
| Discarded | 0 | 0 | 0 |
| Censored (awaiting feedback) | 5 | 1 | 6 |

Further A2-V1-S1 facts:
- 371 exchangeable groups (742 lines);
- 40 lines resolved by retransmission evidence, 15 by bound handles;
- 129 handles, all retired;
- unresolved `[]`;
- A2-8 values:

| Node | `harqErrorRateDl:mean` | `harqTxAttemptsDl:mean` |
|---|---|---|
| 2049 | 0 | 1 |
| 2050 | 0.10227272727272728 | 1.1139240506329113 |

- `full` → INCOMPLETE (A2-4c NOT EVALUATED); `f1d-i` → VALID.

**Configuration facts** (`simulations/m2/m2s72s5.ini`; `check_m2s72_s5v.parse_name`):
- Every E0v-N configuration extends `M2S72-MACLOG` and `M2S72S5-MACLOG-UE`, so the gNB **and** UE MAC lines are logged and the XA reference is available.
- No E0v-N configuration enables `mac.schedulerDl` logging, so A2-4c can never PASS on a campaign run.
- HARQ16 configurations are named `M2S72-E0vN-…`; HARQ5 configurations are `M2S72-E0vNH5-…`. The process count comes from `parse_name` (16 or 5).
- **Name parsing hazard:** `parse_name("M2S72-E0vN-q0-one0-n2-f1_A2V1")` returns kind `E0vN` with factor `'1_A2V1'`. The A2-V1 variant is therefore **not** rejected by the name rule.

---

## 2. Identified technical limitations

| ID | Limitation | Evidence | Consequence |
|---|---|---|---|
| L-1 | A-1 cannot attribute feedback when two UEs hold the same process and feedback arrives at the same instant. One gNB feedback line names no UE, and every UE has its own H-ARQ buffer taking the lowest free process. | N = 2 smoke: 768 ambiguous lines, 768 re-inserts (stale candidates) | **PU-4 FAILs by construction at N ≥ 2** under ordinary same-TTI scheduling |
| L-2 | A-1 closes a unit at its first feedback, NACK included. Under NACKs, its later A-1a attributions are not trustworthy. | `m2s72_peru.attribute_feedback` (`open_.pop(pick)` on any feedback); a2 design review §2 | A-1 is not a valid per-UE source when NACKs occur |
| L-3 | `check_m2s72_s5n.py run` gates on PU-4, so every E0v-N run with N ≥ 2 fails | N2-D2: "the E0v-N campaign cannot start under A-1" | The E0v-N bracket and E1 are blocked |
| L-4 | A-2.1 exists only as a standalone CLI. Its A2-7 and A2-8 are run-level, so there is no per-UE correctness row for occupancy or for Simu5G statistics. | `m2s72_a21.rows_for`, `xa_rows`, `scalar_row` | A per-UE measurement cannot be gated per UE |
| L-5 | E0v-N configurations have no scheduler logging | `m2s72s5.ini` | `full` is INCOMPLETE whenever retransmissions occur; the campaign contract must be F1-d(i) (DR-07a) |
| L-6 | Several A-2.1 paths are validated only synthetically. Examples: discard at maxHarqRtx, multi-NACK groups, exchangeable groups of 3 or more, structural censoring of NACKs or pending groups, codeword 1. | S1 closure §5; `m2s72_a21.SYNTH` | A campaign run may meet them for the first time. DR-07d requires review before any result relies on them. |
| L-7 | `parse_name` accepts a suffixed configuration as `E0vN`, with a string factor | §1.5 | A non-E0v-N run could be evaluated as an E0v-N run |
| L-8 | `S5N_ADAPTER_VALIDATED` (S5-2-D2) is not set. The adapter's Part B (PU-4, PU-5) has never been validated on real MAC-logged N > 1 output under a rule that can pass. | S5-2 addendum §3.4 | E0v-N evaluation stays refused until V-N1 / V-N2 are executed and S5-2-D2 is decided |
| L-9 | A-2.1 runtime is about 70 s per contract on the 12 s N = 2 run (S1 closure S-5) and grows with the line count | S1 closure | N = 8 runs need a time budget; evaluating two contracts doubles it |
| L-10 | Tier-0 runs a hard-coded list of suites with exact expected lines | `.github/workflows/tier0-python.yml` | A new test suite is not executed by CI until the workflow lists it, which is a CI change (D-A1-6) |
| L-11 | `E.rows` is a module-global list, appended to by the accepted checkers | `check_m2s72_s5n.py` | Evaluating two runs in one process can mix rows; the wrapper must evaluate one run per process |

---

## 3. Proposed architecture

### 3.1 Principle

A **new wrapper** composes the unchanged E0v-N evaluation with the unchanged A-2.1 evaluation, and changes only the **gate scoping** of the H-ARQ attribution:

| | Before (S5-2) | After (WP-A1) |
|---|---|---|
| PU-4 (A-1) | gate | **reported verbatim, not a gate** (DR-07b) |
| PU-4h (A-2.1 attribution, run) | — | **gate** |
| PU-4o (per-UE occupancy, A-2.1 confirmed by XA) | — | **gate, per UE** |
| A2-8 per UE (Simu5G statistics) | — | **gate, per UE** (scoping in §4.4) |
| First-genuine-occurrence flag (DR-07d) | — | **review gate**: HELD FOR REVIEW |
| PU-1, PU-2, PU-3, PU-5, AV-1 … AV-3, Block B, I-2H, per-UE Q8, Q8-v, SG-403, MG-1 | gates | **unchanged gates** |

**Historical results stand.**
- Nothing is relabelled. Every earlier record stays as written, including the N = 2 smoke's "VALIDATED WITH A-1 LIMITATION" and the PU-4 FAIL.
- The unchanged `check_m2s72_s5n.py` verdict ("FAIL PU-4" where A-1 is incomplete) is still produced and kept in the run's records.
- The new verdict is a separate, labelled evaluation result.

### 3.2 Modules (all new files; nothing existing is edited)

| New file | Role |
|---|---|
| `check/m2s72_e0vn21.py` | Library: pure functions over the outputs of the unchanged evaluators.<br>• contract selection;<br>• PU-4h, PU-4o, per-UE A2-8;<br>• the A-1 historical report;<br>• the A-1 / A-2.1 agreement diagnostic;<br>• the first-genuine-occurrence (FGO) registry and flag;<br>• the composed verdict.<br>It reads no raw file and imports the frozen and accepted modules read-only. |
| `check/check_m2s72_s5n21.py` | CLI with modes `run` and `hrq` (§5) and `controls`. One run per process (L-11). |
| `check/m2s72_fgo_registry.json` | The FGO baseline: the A-2.1 coverage features already **genuinely** exercised in an accepted record, each with its record citation. It is changed only by maintainer-accepted records (append-only). |
| `check/test_m2s72_e0vn21.py` | The test suite of §7 |
| `simulations/m2/results/M2-S7.2a-a1-implementation.md` | Implementation report, written at implementation time |

**Never modified:** every module in §1.4, `m2s72s5.sh`, the `.ini` files and the generator.

**Import discipline.** The wrapper calls only these public functions:
- `check_m2s72_s5n.run_one`;
- `check_m2s72_a21.inputs`, `m2s72_a21.evaluate` and `m2s72_a21.verdict`;
- `m2s72_peru_adapter.harq_events` and `m2s72_peru.attribute_feedback` (A-1 report);
- `m2s72_a2.sca_nodes` and `m2s72_peru.scalars`, exactly as `m2s72_a21.scalar_row` uses them.

`sys.argv` isolation follows the existing pattern in `check_m2s72_s5n.py`.

### 3.3 Data flow of `run`

```
check_m2s72_s5n21.py run <runs> <cfg> <records>
  0  name guard (§5.3); S5N_ADAPTER_VALIDATED required (S5-2-D2, unchanged)
  1  S5N.run_one(runs, cfg, <records>/s5n)                  -> unchanged records, unchanged verdict (historical scoping)
  2  A-1 report: rows "PU-4 (A-1, historical; reported)" = the s5n PU-4 row verbatim + digest.harq_attribution
  3  A21.inputs(runs, cfg); A21.evaluate(..., t0 = 2 s)     -> res, rows A2-*, per_ue, coverage, extra
       contract verdicts: f1d-i (campaign, gating) and full (reported, labelled)
  4  consistency C-0: A-1 and A-2.1 parsed the same log (equal insert and feedback line counts)
  5  PU-4h (run), PU-4o (per UE), A2-8/UE k (per UE), A-1 / A-2.1 agreement (diagnostic)
  6  FGO: A-2.1 coverage features EXERCISED by this run and absent from the registry
  7  composed verdict (§4.6) -> <records>/<cfg>.s5n21.txt, <cfg>.s5n21.json; A-2.1 records via A21's own writer
```

---

## 4. Evaluation contract

### 4.1 Status vocabulary

`PASS`, `FAIL`, `NOT EVALUATED` (NE), `NOT EXERCISED` (NX), `NOT APPLICABLE` (NA), `HELD FOR REVIEW` (HR).
- Only PASS, and NX where a row allows it, count toward acceptance.
- NE is never a pass.
- HR is never a pass or a fail.

### 4.2 PU-4h: H-ARQ attribution of the run (A-2.1), gate

**Input:** the A-2.1 rows and their verdict under the **campaign contract `f1d-i`** (DR-07a).

| A-2.1 verdict (`f1d-i`) | Consistency C-0 | PU-4h |
|---|---|---|
| VALID | equal | **PASS** |
| NOT VALID (any FAIL, including A2-4c or A2-8) | any | **FAIL**; the detail names every failing A2 row |
| INCOMPLETE (a required row NE, e.g. A2-0s without `$SIMU5G_ROOT`, A2-7 without UE lines, A2-9 unresolved) | equal | **NOT EVALUATED**; the detail names the rows |
| any | different | **FAIL** ("parser divergence: A-1 saw i inserts / f feedback lines, A-2.1 saw i' / f'") |

**Detail:**
- the counts of single, exchangeable, bound and resolved-by-retransmission lines;
- d*_tx;
- end states;
- handles.

**Also recorded:** the `full` verdict, labelled "full contract (reported; scheduler logging absent in E0v-N configurations)". For ACK-only runs it is VALID, because A2-4a/b/c are NOT EXERCISED. With retransmissions it is INCOMPLETE, by design.

### 4.3 PU-4o: per-UE H-ARQ occupancy, gate, one row per UE k

**Input:** the A-2.1 `per_ue[n_k]` and A2-7's `occupancy_equal[n_k]` and `skipped`.

| Condition (in order) | PU-4o UE k |
|---|---|
| PU-4h FAIL | **FAIL** ("attribution not valid") |
| A2-7 row FAIL | **FAIL** (the detail names the A2-7 detail) |
| `per_ue[n_k]["occupancy"]` has `error` (negative occupancy) | **FAIL** |
| `occupancy_equal[n_k]` is False | **FAIL** |
| A2-7 NE (no UE-side lines) | **NOT EVALUATED** |
| `n_k ∈ skipped` (censored or pending groups touch UE k) | **NOT EVALUATED (censored)**, scoped by D-A1-3 |
| `n_k` absent from A-2.1 `per_ue` (no DL PDU for UE k) | **NOT EXERCISED**. A gPTP DL stream exists for every UE, so this is unexpected; it is reported, and decided by D-A1-3. |
| otherwise | **PASS** |

**Use.** The per-UE occupancy in the digest's performance section comes from A-2.1 **only** where PU-4o UE k is PASS. Otherwise it is "not evaluated", never estimated (the S5-2 §3.3 rule, unchanged).

### 4.4 A2-8 per UE: Simu5G per-UE statistics, gate, one row per UE k

**Computation.** The same quantities and tolerance as `m2s72_a21.scalar_row`, for node n_k only:
- `harqErrorRateDl:mean` = NACK / feedback;
- `harqTxAttemptsDl:mean` = mean `ntx` of ACKed lifecycles;
- relative tolerance 1e-9.

| Condition | A2-8/UE k |
|---|---|
| a value differs | **FAIL** |
| `n_k` touched by censored or pending groups | **NOT EVALUATED (censored)** |
| no `.sca`, no `macNodeId` record for UE k's module, scalar absent or unparsable, or no feedback attributed to n_k | **NOT EVALUATED** |
| both statistics equal | **PASS** |

**Consistency invariant (tested, T-a28-agg):** the aggregate of the per-UE rows reproduces the run-level A2-8 status of `m2s72_a21.scalar_row` exactly:
- FAIL iff any UE FAIL;
- else NE iff any compared node is censored, or nothing compared;
- else PASS.

**Gate scoping (D-A1-3, recommendation):**
- FAIL is a gate.
- NE for a missing or unparsable scalar is a gate (NE stops the batch, as for the PU / AV rows).
- NE (censored) is **reported, not a gate**. It arises from structural end-of-log censoring only; the run's other UEs are still compared, and A2-9 already guarantees that nothing is unresolved.

### 4.5 PU-4 (A-1): historical report, never a gate

- The row produced by the unchanged `check_m2s72_s5n.run_one` is copied **verbatim**, status and detail, under the label `PU-4 (A-1, historical rule; reported, not a gate — DR-07b)`.
- The A-1 summary `{a1a, a1b, ambiguous, orphan, reinsert, d_star_ps}` from the digest is reported unchanged.
- A PU-4 FAIL is printed as FAIL. It is never printed as PASS, NA or "superseded", and it never changes the composed verdict.
- The unchanged s5n verdict line (for example `FAIL PU-4`) is kept in `records/s5n/<cfg>.check.txt` and quoted in the new record.

**A-1 / A-2.1 agreement diagnostic** (report only, never a gate; D-A1-10):
- For each feedback line A-1 attributed (A-1a or A-1b), compare its node with A-2.1's owner.
- Reported: agree, disagree, and A-1-unattributed lines resolved by A-2.1 (the class of each: single, exchangeable and so on).
- Expected on ACK-only input: disagree = 0. The N = 2 smoke's XA-3 recorded 0 disagreements for A-1a and A-1b.

### 4.6 First-genuine-occurrence flag (DR-07d)

**Registry entries** (`m2s72_fgo_registry.json`): `{feature: [record citations]}`.
- Features use the exact names of `m2s72_a21.coverage`.
- An entry exists only where an **accepted** record states that the feature was exercised on genuine Simu5G output.
- Proposed initial content (D-A1-4; each citation to be confirmed in review):

| Feature (A-2.1 coverage name) | Genuine in | Citation |
|---|---|---|
| single-candidate ACK attribution | N = 1, N = 2 smokes; A2-V1 | `-a2-implementation.md` §4; S1 closure §3 |
| exchangeable ACK groups (2 candidates) | N = 2 smoke (384); A2-V1 (371) | the same |
| NACK resolved: single candidate | A2-V1 | S1 closure §3 (lines by class reported by the VM) |
| NACK resolved: bound handle | A2-V1 (15) | S1 closure §3 |
| NACK resolved by retransmission evidence (deferred) | A2-V1 (40) | S1 closure §3; F3 closure R-1…R-10 |
| retransmissions | A2-V1 (144) | S1 closure §3 |
| mixed ACK / NACK groups | A2-V1 (the 366 ms group) | F3 closure §2 |
| end-of-run censoring: awaiting feedback | A2-V1 (6) | S1 closure §3 |

**Not in the registry** (synthetic only, S1 closure §5):
- exchangeable groups of 3 or more;
- multi-NACK groups;
- discard after maxHarqRtx + 1 transmissions;
- end-of-run censoring of the kinds "inserted in the last TTI", "awaiting retransmission" and "awaiting resolution".

The NACK classes are a precondition fact recorded in S1 only as aggregate counts. If the reviewer finds that a registry row is not explicitly supported by a record, it is removed, which is fail-closed.

**Flag.**
- The FGO is the set of features with coverage count > 0 in the run that are absent from the registry.
- Any feature whose name is unknown to the registry also flags, so a renamed or new feature can never pass silently.
- A2-4c evidence present in a run (scheduler logging on) flags too, because it has never been genuinely exercised.

**Effect.**
- A non-empty FGO makes the composed verdict **HELD FOR REVIEW** (exit 3).
- The rows are still computed and recorded. Nothing is converted to PASS or FAIL.
- The batch stops at the review gate (D-A1-7).
- The maintainer's review outcome is recorded as a new record. If accepted, the registry receives the feature with that record's citation, and the run's verdict is re-derived from the unchanged records.

### 4.7 Composed per-run verdict (`run` mode)

| Outcome | Condition | Exit |
|---|---|---|
| **PASS** | every gate PASS (or NX where allowed), no gate NE, FGO empty | 0 |
| **FAIL** `<rows>` | any gate FAIL | 1 |
| **REFUSED / EVALUATION ERROR** | name guard, no adapter validation, node ids unavailable, exception | 2 |
| **HELD FOR REVIEW** `<features>` | no gate FAIL, FGO non-empty | 3 |
| **INCOMPLETE** `<rows>` | no gate FAIL, FGO empty, some gate NE | 4 |

**Gate set:**
- the s5n gates **minus PU-4**: Block B rows at N, I-2H, per-UE Q8, Q8-v, SG-403, MG-1, PU-1, PU-2, PU-3, PU-5, AV-1 … AV-3;
- plus PU-4h, PU-4o (every UE), and A2-8/UE k (FAIL and non-censored NE).

**Reported, never gating:**
- PU-4 (A-1);
- the A-2.1 `full` verdict;
- the agreement diagnostic;
- censored-scope NE.

**PU-5** stays a gate (D-A1-5). It sums grant bytes and insert lines, which name their node, so it is independent of feedback attribution. It passed on the N = 2 smoke.

### 4.8 Missing, malformed and ambiguous evidence

| Situation | Handling |
|---|---|
| no `run-<cfg>.log.gz` | s5n: PU-4 / PU-5 NE (unchanged). Wrapper: A-2.1 not evaluable → PU-4h NE, PU-4o NE (all UEs), A2-8/UE NE → **INCOMPLETE** |
| log without UE-side H-ARQ lines | A2-7 NE → `f1d-i` INCOMPLETE → PU-4h NE; PU-4o NE → **INCOMPLETE** |
| no `.sca` / no `macNodeId` records | A2-8/UE k NE (gating) → **INCOMPLETE**; PU-4h unaffected (A2-8 not required) |
| `$SIMU5G_ROOT` unset or not 1.8.1 | A2-0s NE / FAIL → PU-4h NE / FAIL |
| node ids unavailable (`Run72` fails) | **REFUSED** (exit 2): no per-UE mapping is possible; nothing is guessed |
| UNCLASSIFIED MAC-log line, malformed line, or a line A-1 parses and A-2.1 does not (or vice versa) | MG-1 FAIL (unchanged) and / or A2-0 / A2-1 FAIL; consistency C-0 FAIL → **FAIL** |
| exchangeable group (same process, same instant, identical results) | resolved as a certified multiset (A2-5). Per-UE counts and occupancy are exact; no line is claimed individually. PU-4h PASS allowed. |
| line that XA cannot separate but A-2.1 resolved | checked as a group multiset ("reference ambiguous"), never counted as confirmed (A-2.1 rule 6, unchanged) |
| unresolved lifecycle (not structurally censorable) | A2-9 NE → **INCOMPLETE** |
| structural end-of-log censoring | censored nodes: PU-4o / A2-8 "NOT EVALUATED (censored)", reported. A censoring kind not in the registry → FGO → **HELD FOR REVIEW** |
| configuration name not plain E0v-N (suffix, unknown variant) | `run` **REFUSED** (§5.3) |

### 4.9 Backward compatibility (N = 1)

- **N = 1 configurations** (`M2S72-E0v-…`): the N = 1 checker `check_m2s72_s5v.py` stays the evaluator, unchanged. `run` refuses N = 1 names (`s5n` does too).
- **`M2S72-E0vN-…-n1-…`** (an E0v-N bracket at N = 1): `run` evaluates it. At N = 1 A-1 is exact by construction. The tests require that A-1 PU-4 PASS, PU-4h PASS and PU-4o PASS, and that the A-2.1 per-UE counts **and occupancy** equal A-1's (T-n1-identity).
- **`hrq` mode** accepts the N = 1 smoke configuration `M2S72-E0v-q0-f1`, because V-N1 needs it. It evaluates only the H-ARQ rows; every E0v-N-specific row is NOT APPLICABLE.

---

## 5. Input / output contract

### 5.1 Commands

```
check_m2s72_s5n21.py run  <runs> <cfg> <records dir> [--t0 <s>]
check_m2s72_s5n21.py hrq  <runs> <cfg> <records dir> [--t0 <s>] [--expect <declared expectation file>]
check_m2s72_s5n21.py controls <runs> <cfg> <records dir>
```

| Mode | Purpose |
|---|---|
| `run` | The E0v-N per-run evaluation (§3.3, §4.7). Needs `S5N_ADAPTER_VALIDATED`. |
| `hrq` | H-ARQ rows only: A-1 report, A-2.1 (both contracts), C-0, PU-4h, PU-4o, A2-8/UE, agreement, FGO. Does **not** call the adapter and does **not** need `S5N_ADAPTER_VALIDATED`. Used by V-N1, V-N2 and V-V1. With `--expect`, it also compares every declared value with the evaluated value (§8) and writes a comparison table. It never adjusts anything. |
| `controls` | The in-memory negative controls of §7.3 on a real run (the raw files are only read), with the baseline guard of `check_m2s72_a21.py` (a control counts only if its rows were PASS before the mutation). |

**Common rules:**
- **Inputs:**
  - `<runs>/run-<cfg>.log.gz`;
  - `<runs>/<cfg>/<cfg>/0.sca`;
  - the run's vector / scalar files for `Run72` node ids;
  - `$SIMU5G_ROOT` (Simu5G 1.8.1 source tree, for A2-0s).
- **Outputs:**
  - `<records dir>` must not already contain the outputs;
  - files are written with `fsync` (`LIB.durable`);
  - `<records dir>/s5n/…` holds the unchanged s5n records (`run` only);
  - `a21-<cfg>.txt/.json` is written by A-2.1's own writer, for each contract;
  - `<cfg>.s5n21.txt` and `<cfg>.s5n21.json` (`run`), or `hrq-<cfg>.txt` and `hrq-<cfg>.json` (`hrq`).
- **Never written:** the raw files.

### 5.2 `<cfg>.s5n21.json` schema (fields)

| Field | Content |
|---|---|
| `config`, `kind`, `numUe`, `nproc`, `window_ps`, `contract_campaign` | `"f1d-i"` for the campaign contract |
| `s5n` | `{verdict_line, gate_failures, per_ue_not_evaluated, records}`: the unchanged s5n verdict |
| `a1_historical` | `{row: [PU-4, run, status, detail], summary: {...}}` |
| `a21` | `{verdict_f1d_i, verdict_full, rows: [...], coverage: [...], per_ue: {...}}`, verbatim |
| `consistency` | `{inserts: [a1, a21], feedback: [a1, a21], status}` |
| `rows` | `[[id, subject, status, detail], ...]` for PU-4h, PU-4o UE k, A2-8/UE k |
| `agreement` | `{agree, disagree, a21_only_by_class}` |
| `fgo` | `{exercised_features: {name: count}, not_in_registry: [...], registry_sha256}` |
| `verdict` | `{status, exit, gate_failures, gate_not_evaluated, held_features}` |
| `inputs` | sha256 of the log, `.sca` and registry; the A-2.1 code identity (blob ids of `m2s72_a21.py` and `check_m2s72_a21.py`) |

### 5.3 Name guard

`run` accepts only names matching the generator's E0v-N patterns exactly, using a wrapper-local regex. `check_m2s72_s5v.parse_name` is accepted code and is not modified:
- `^M2S72-E0vN(H5)?-(q0|q0p|qdu|qde)-(one0|sym)-n(1|2|4|8)-f(0p5|0p8|1|1p25|1p6|2)$`

Anything else is **REFUSED** (exit 2), including the A2-V1 name with its suffix. That name is evaluated only through `hrq`.

The exact option and factor sets are to be confirmed against the generator at implementation (test T-name-guard enumerates `m2s72s5.ini`).

---

## 6. Module boundary and preservation guarantees

| Guarantee | Enforcement |
|---|---|
| Frozen A-2 / XA / A-1 files byte-identical to `fbee202`; A2-V1 evaluator to `39a6434` | the existing T-frozen-untouched; plus T-a1-frozen in the new suite (same lists) |
| Accepted A-2.1 files byte-identical to `d920125` | T-a1-a21-pinned (`git diff --quiet d920125 -- <5 files>`) |
| s5n / adapter / s5v / s5n2 byte-identical to the baseline `7bb0e3a` | T-a1-s5n-pinned |
| s5n records produced inside `run` identical to a standalone `check_m2s72_s5n.py run` | T-s5n-transparent (stubbed evaluation; byte comparison) |
| Historical PU-4 never relabelled | T-pu4-verbatim, NC-pu4-relabel |
| All ten tier-0 suites keep their exact expected lines | tier-0 itself (unchanged workflow) |

---

## 7. Test matrix (`test_m2s72_e0vn21.py`; synthetic unless stated)

**Truth source:**
- the corrected generator `m2s72_harqfix21.make(n_ue, ttis, sched, nack, d_ue, nproc, …)` → `(lines, node, truth)`, labelled synthetic;
- the frozen `m2s72_harqfix` for ACK-only identity cases;
- synthetic `.sca` files built from the generator truth.

Every test states its inputs, its expected outputs, and the defect its failure detects.

### 7.1 Positive and structural tests

| ID | Input | Expected | Detects |
|---|---|---|---|
| T-n2-same-tti | N = 2, both UEs scheduled every TTI on the same process (ACK only) | A-1: ambiguous > 0, re-insert > 0, **PU-4 FAIL reported verbatim**; A-2.1 VALID (both contracts; A2-4a/b/c NX); exchangeable groups = same-TTI pairs; PU-4h PASS; PU-4o PASS × 2 with occupancy = truth; composed PASS | A-1 limitation masking; PU-4 accidentally still gating |
| T-n3-groups | N = 3, three UEs on one process in one TTI | A-2.1 exchangeable groups of 3 (certified); PU-4h PASS; FGO = {"exchangeable groups of 3 or more"} → **HELD FOR REVIEW** (exit 3) | synthetic-only path silently accepted |
| T-n4-independent | N = 4, NACK chains on UEs 1 and 3 (different processes, no overlaps), ACK on 0 and 2 | per-UE inserts / transmissions / NACK / occupancy = truth for each UE; PU-4o PASS × 4; A2-8/UE PASS × 4 (synthetic `.sca` from truth) | cross-UE leakage of counts |
| T-n4-overlap-nack | N = 4, a NACK on UE 2 in a TTI where UEs 0 and 2 share the process (mixed group) | A-2.1 resolves by retransmission evidence; PU-4h PASS; no FGO (mixed groups genuine); per-UE = truth | mixed-group attribution regressions |
| T-n2-a2v1-like | N = 2, NACKs on UE 1 only (the A2-V1 pattern) | per-UE = truth; FGO empty; `full` verdict INCOMPLETE without scheduler lines (with retransmissions), `f1d-i` VALID → PU-4h PASS | wrong contract gating |
| T-multinack | N = 2, both UEs NACK the same process in the same TTI | A-2.1 multi-NACK handling (counts exact as multiset); FGO = {"multi-NACK groups …"} → HR | DR-07d bypass |
| T-discard | N = 2, a PDU NACKed maxHarqRtx + 1 times | FGO = {"discard after maxHarqRtx + 1 transmissions"} → HR; per-UE discarded = truth | DR-07d bypass |
| T-censor-structural | log cut after a NACK without a following complete main loop | censored nodes: PU-4o and A2-8/UE "NOT EVALUATED (censored)", non-gating; FGO = {"…awaiting retransmission (structural)"} → HR | censoring hidden or wrongly gating |
| T-unresolved | NACK followed by a main loop but no retransmission evidence | A2-9 NE → PU-4h NE → **INCOMPLETE** (exit 4) | unresolved evidence passing |
| T-n1-identity | N = 1 ACK only (frozen generator), with and without UE lines, `.sca` present | A-1 PU-4 PASS; PU-4h PASS; A-2.1 per-UE counts and occupancy = A-1's; with UE lines: PU-4o PASS; without: NE → INCOMPLETE | N = 1 behaviour change |
| T-a28-agg | the cases above with `.sca` | aggregate of A2-8/UE rows = `m2s72_a21.scalar_row` status | divergence of the per-UE A2-8 from accepted A-2.1 |
| T-agree | T-n2-same-tti, T-n2-a2v1-like | agreement: A-1-attributed lines disagree = 0 on ACK-only; on NACK input, the disagreements are reported with their classes (diagnostic only; the verdict is unchanged) | the diagnostic changing a verdict |
| T-name-guard | every `[Config M2S72-E0vN…]` name in `m2s72s5.ini`; `…_A2V1`; `M2S72-E0v-q0-f1`; malformed | all generator E0v-N names accepted; the others REFUSED in `run`; `hrq` accepts the A2-V1 and N = 1 names | L-7 |
| T-one-run-per-process | two `run` invocations in one Python process | refused (exit 2) on the second | L-11 row mixing |
| T-schema | every case | the JSON has every §5.2 field; statuses only from §4.1 | silent schema drift |

### 7.2 Genuine F3 fixture through the wrapper (genuine input)

| ID | Input | Expected | Detects |
|---|---|---|---|
| T-f3-hrq | `fixtures/a2v1-first-chain.log.gz` (sha256 pinned; tier-0 gate), `hrq` with t0 = 0, no `.sca`, node ids from the fixture `.meta.json` (as `m2s72_a21_realchain.py`) | A-2.1 rows identical to `m2s72_a21_realchain` R-1…R-10 (A2-4a/b PASS, A2-4c NE, A2-8 NE); `f1d-i` VALID → PU-4h PASS; PU-4o PASS for both nodes (A2-7 equal); A2-8/UE NE (no `.sca`, gating) → composed `hrq` verdict **INCOMPLETE** by declaration; FGO empty (NACK by retransmission evidence, bound handle, mixed group and retransmissions are all registry features from A2-V1) | the wrapper diverging from the accepted F3 validation |
| T-f3-a1 | the same fixture | the A-1 report equals a direct call of the frozen `attribute_feedback` on the same events (no hard-coded number; A-1 on this NACK chain is not an accepted quantity) | the A-1 report being altered |

### 7.3 Negative controls (mutation of synthetic logs; baseline guard: the declared rows PASS before the mutation, otherwise NOT BUILDABLE)

| ID | Mutation | Expected | Detects |
|---|---|---|---|
| NC-swap | one PDU's gNB insert line relabelled to the other UE's node (N = 2) | A2-7 FAIL → PU-4h FAIL; PU-4o FAIL for the affected UEs; the detail names the PDU | **cross-UE misattribution** invisible to sums |
| NC-ue-relabel | one UE-side RX line moved to the other UE's module | A2-7 FAIL (reference invalid) → PU-4h FAIL, never PASS | a corrupted reference passing |
| NC-occ-one-ue | UE 0's insert removed and its feedback kept | PU-4o UE 0 FAIL; **UE 1 rows unchanged** | contamination of other UEs' rows |
| NC-scalar-ue1 | `.sca` `harqErrorRateDl:mean` of UE 1 perturbed | A2-8/UE 1 FAIL; A2-8/UE 0 PASS; aggregate FAIL = run-level A2-8 FAIL | per-UE isolation of A2-8 |
| NC-dropfb | one feedback event removed | A2-1 or A2-2 FAIL → PU-4h FAIL | lost evidence |
| NC-dupins | one insert duplicated | A2-2 FAIL; A-1 re-insert + 1 (reported) | duplicated evidence |
| NC-shift | one feedback one TTI late | A2-3 FAIL → PU-4h FAIL | timing corruption |
| NC-node-map | node-id map permuted | A2-4b / A2-7 FAIL (or REFUSED if the map is not a bijection) | wrong UE identity |
| NC-no-ue-lines | all UE-side lines removed | PU-4h NE, PU-4o NE → INCOMPLETE, never PASS | absence read as pass |
| NC-no-sca | `.sca` removed | A2-8/UE NE (gating) → INCOMPLETE | absence read as pass |
| NC-divergence | a feedback line in a format A-2.1 classifies and A-1's regex does not (or vice versa) | C-0 FAIL → PU-4h FAIL | parser divergence |
| NC-registry | a registry feature removed | the same run now flags it → HR | FGO fail-open |
| NC-registry-unknown | a coverage name unknown to the registry injected | HR | renamed features passing |
| NC-pu4-relabel | the wrapper's copy of PU-4 compared with s5n's row | byte-equal status and detail; a PU-4 FAIL never appears as PASS / NA in any output | **historical result concealed** |
| NC-name | `run` on `…-f1_A2V1` | REFUSED (exit 2) | L-7 |
| NC-full-masquerade | a run with retransmissions and no scheduler lines | `full` reported INCOMPLETE; PU-4h uses `f1d-i` only; the record labels the contract | contract confusion |

### 7.4 Regression protection

| ID | Check |
|---|---|
| T-a1-frozen | frozen files byte-identical (`fbee202`, `39a6434`) |
| T-a1-a21-pinned | accepted A-2.1 files byte-identical to `d920125` |
| T-a1-s5n-pinned | `check_m2s72_s5n.py`, `m2s72_peru_adapter.py`, `check_m2s72_s5v.py`, `check_m2s72_s5n2.py`, `m2s72s5_lib.py` byte-identical to `7bb0e3a` |
| T-s5n-transparent | stubbed `run`: the s5n records equal a standalone s5n run byte for byte |
| tier-0 | the ten existing suites keep their exact lines; the fixture and Simu5G gates are unchanged |

---

## 8. Independent validation protocol (DR-07c) — prepared, not executed

**Executor and conditions:**
- an independent executor designated by the maintainer (`remote-execution-feasibility.md` §4, X-1 … X-9);
- never the development agent.

**Inputs:**
- the private archives (N = 1 smoke: 41 files; N = 2 smoke: 58 files; A2-V1: 58 files);
- each verified against its archive checksum manifest and the original manifests (X-2a).

**Path resolution:** DR-13 method 1, a read-only mount of the extraction at the original absolute prefix. The method is recorded in each record.

**Code:**
- the reviewed implementation commit `<C>` of WP-A1 (to be pinned in the protocol revision that accompanies the implementation PR);
- an independent clean worktree;
- `SIMU5G_ROOT` = an unmodified Simu5G 1.8.1 tree.

**Read-only evaluations; nothing is simulated.**

### 8.1 Common steps (each validation)

```
P-0  git -C <wt> rev-parse HEAD                    == <C>
     python3 -I -B simulations/m2/check/test_m2s72_e0vn21.py      (all PASS)
     the ten tier-0 suites with their exact lines; T-frozen-untouched PASS
P-1  verify the archive: sha256sum -c <archive checksum manifest>; then every original manifest entry (size, sha256)
     at the mounted prefix                         (record: integrity-before.txt)
P-2  evaluation command (below), records into a FRESH directory <E>
P-3  re-verify the archive and the mounted tree    (record: integrity-after.txt; identical to before)
P-4  SHA256SUMS of <E>; environment identity (X-4: OMNeT++ / Simu5G versions, Python, OS)
```

**Comparison rules:**
- All counts are compared as exact integers.
- The statistics in V-V1 use the declared relative tolerance of 1e-9, the same as A2-8.
- A row's status must equal the declared status exactly.
- A deviation is reported as found. Nothing is re-run, adjusted or relabelled (X-6).
- `hrq --expect <file>` writes the comparison table. The expectation files below are committed **before** execution.

### 8.2 V-N1: N = 1 smoke `M2S72-E0v-q0-f1`, seed 0 (ACK only, one UE)

```
python3 -I -B check_m2s72_s5n21.py hrq <R>/<N1 runs> M2S72-E0v-q0-f1 <E>/vn1 --expect vn1.expect.json
python3 -I -B check_m2s72_a21.py a21 <R>/<N1 runs> M2S72-E0v-q0-f1 <E>/vn1-a21-f1d --contract f1d-i      (cross-check)
python3 -I -B check_m2s72_s5n2.py xa <R>/<N1 runs> M2S72-E0v-q0-f1 <E>/vn1-xa                              (unchanged reference)
```

| Declared expectation | Value |
|---|---|
| A-1 summary | a1a = 11 697; a1b = 0; ambiguous = orphan = re-insert = 0 |
| A-1 PU-4 (reported) | PASS, unchanged |
| A-2.1 rows (`f1d-i` and `full`) | A2-0, A2-0s, A2-1, A2-2, A2-3, A2-5 (NX acceptable), A2-6, A2-7, A2-9 PASS; A2-4a / 4b / 4c **NOT EXERCISED**; verdicts VALID / VALID |
| per-UE A-2.1 occupancy | equal to A-1's occupancy (N = 1: A-1 exact) and to XA's truth occupancy |
| PU-4h / PU-4o UE 0 / A2-8 UE 0 | PASS / PASS / PASS |
| FGO | empty |
| `hrq` verdict | PASS |

### 8.3 V-N2: N = 2 smoke `M2S72-E0vN-q0-one0-n2-f1`, seed 0 (ACK only, two UEs, 384 same-TTI pairs)

```
python3 -I -B check_m2s72_s5n21.py hrq <R>/<N2 runs> M2S72-E0vN-q0-one0-n2-f1 <E>/vn2 --expect vn2.expect.json
python3 -I -B check_m2s72_a21.py a21 <R>/<N2 runs> M2S72-E0vN-q0-one0-n2-f1 <E>/vn2-a21-f1d --contract f1d-i
python3 -I -B check_m2s72_s5n2.py xa <R>/<N2 runs> M2S72-E0vN-q0-one0-n2-f1 <E>/vn2-xa
```

| Declared expectation | Value |
|---|---|
| A-1 summary (reported unchanged) | a1a = 9 718; a1b = 2 476; ambiguous = 768; re-insert = 768; orphan = 0 |
| A-1 PU-4 (reported) | **FAIL, retained verbatim** |
| A-2.1 | 12 194 single-candidate lines; 384 exchangeable groups / 768 lines, all certified (A2-5 PASS); A2-4a/b/c NX; A2-7 PASS; verdicts VALID / VALID. *These counts are the declared expectations of PC-A2-N2, never yet confirmed on the genuine output; a deviation is a finding, reported as found.* |
| per-UE occupancy | A-2.1 = XA truth occupancy for both UEs (XA-6's comparison, previously NOT EVALUATED under A-1, now evaluable) |
| A2-8 per UE | PASS for both UEs |
| PU-4h / PU-4o × 2 | PASS / PASS × 2 |
| agreement | the 12 194 A-1-attributed lines (9 718 + 2 476): disagree = 0; 768 lines A-1-unattributed, all `exchangeable` in A-2.1 |
| FGO | empty |
| `hrq` verdict | PASS |

### 8.4 V-V1: A2-V1 run `M2S72-E0vN-q0-one0-n2-f1_A2V1` (sealed; seal `3d00ef8e…`; genuine NACKs on ue[1])

```
python3 -I -B check_m2s72_s5n21.py hrq <R>/a2-nack-1/runs M2S72-E0vN-q0-one0-n2-f1_A2V1 <E>/vv1 --expect vv1.expect.json
python3 -I -B m2s72_a21_fixture.py extract ...      (integrity check exactly as in S1; reproduces the F3 fixture sha256)
```

| Declared expectation | Value |
|---|---|
| per-node accounting | exactly the S1 closure §3 table: node 2049 inserts 11 702, transmissions 11 702, feedback 11 697, ACK 11 697, NACK 0, discarded 0, censored 5; node 2050 inserts 1 265, transmissions 1 409, feedback 1 408, ACK 1 264, NACK 144, retransmissions 144, discarded 0, censored 1 |
| line classes | 371 exchangeable groups (742 lines); 40 resolved by retransmission evidence; 15 bound; 129 handles retired; unresolved `[]` |
| A2-8 per UE | node 2049: 0 / 1; node 2050: 0.10227272727272728 / 1.1139240506329113 (relative 1e-9) → PASS × 2 |
| A-2.1 verdicts | `f1d-i` VALID; `full` INCOMPLETE (A2-4c NE, the only non-PASS row) |
| PU-4h / PU-4o × 2 | PASS / PASS × 2 |
| A-1 (reported) | values reported as computed; no expectation is declared, because A-1 on genuine NACK input is not an accepted quantity (L-2). Disagreements are listed by class. |
| E0v-N-specific rows | NOT APPLICABLE (this is not an E0v-N bracket configuration) |
| FGO | empty. Every exercised feature is in the registry **by citation of A2-V1 itself**; the reviewer must confirm that this self-citation is acceptable (D-A1-4). |
| original A2-V1 verdict | **NOT ACCEPTED, unchanged.** V-V1 is a consistency check of the wrapper, not an acceptance of A2-V1. |

### 8.5 Acceptance gates of the validations

| Gate | Condition |
|---|---|
| VG-0 | P-0 … P-4 complete; integrity identical before and after |
| VG-1 | every declared expectation of the validation met exactly |
| VG-2 | no wrapper output relabels a historical result (the PU-4 rows are verbatim; the A2-V1 verdict is untouched) |
| VG-3 | the maintainer accepts the record |

**After VG-3 for V-N1 and V-N2:**
- the maintainer decides **S5-2-D2** (DR-07c: S5-2-D2 would cite V-N1 and V-N2), which sets `S5N_ADAPTER_VALIDATED` for E0v-N campaign runs;
- only then can the E0v-N bracket start.

V-V1 is independent of S5-2-D2. **None of these validations is executed by WP-A1.**

---

## 9. Implementation sequence (after design approval)

| Step | Content | Exit criterion |
|---|---|---|
| I-1 | `m2s72_e0vn21.py` skeleton: status vocabulary, registry loader (with sha256), name guard, schema | T-name-guard, T-schema |
| I-2 | per-UE A2-8 and the aggregate invariant | T-a28-agg, NC-scalar-ue1, NC-no-sca |
| I-3 | consistency C-0, PU-4h, PU-4o | T-n2-same-tti, T-n4-*, NC-swap, NC-occ-one-ue, NC-divergence |
| I-4 | A-1 historical report and agreement diagnostic | T-agree, NC-pu4-relabel |
| I-5 | FGO flag and verdict composition | T-n3-groups, T-multinack, T-discard, T-censor-structural, NC-registry* |
| I-6 | CLI `hrq` (no s5n), the F3 fixture tests, `--expect` comparison | T-f3-hrq, T-f3-a1 |
| I-7 | CLI `run` (composition with `s5n.run_one`), one run per process, the s5n transparency test | T-s5n-transparent, T-one-run-per-process |
| I-8 | CLI `controls`; implementation record; the expectation files `vn1/vn2/vv1.expect.json` committed for review | all of §7 |
| I-9 | **separately authorised:** adding the suite to tier-0 (a CI change; D-A1-6) | tier-0 green with the new exact line |

Each step is one commit on `wp/a1-a21-e0vn-wrapper` (or a follow-up work-package branch), with tests. A draft PR is opened for review; there is no merge without the maintainer.

---

## 10. Acceptance criteria of WP-A1

| ID | Criterion | Level |
|---|---|---|
| AC-1 | This design reviewed and approved, with decisions D-A1-1 … D-A1-10 recorded | — |
| AC-2 | All tests of §7 PASS locally and in CI; every negative control AS DECLARED (none NOT BUILDABLE without a recorded reason) | 2 |
| AC-3 | §6 guarantees hold: no frozen, accepted or s5n tooling file differs | 2 |
| AC-4 | Every historical result reported verbatim; no PU-4 FAIL relabelled (NC-pu4-relabel) | 2 |
| AC-5 | V-N1, V-N2 and V-V1 executed independently and accepted (VG-0 … VG-3) | **3** (maintainer) |
| AC-6 | S5-2-D2 decided by the maintainer on the basis of AC-5 | decision |

WP-A1 closes at level 2 with AC-1 … AC-4. Level 3 needs AC-5 and AC-6, which are outside the development agent's authority.

---

## 11. Risks and unresolved design decisions

### 11.1 Decisions for the reviewer and maintainer

| ID | Decision | Recommendation |
|---|---|---|
| D-A1-1 | The definitions of PU-4h (run attribution under the campaign contract, plus parser consistency) and PU-4o (per-UE occupancy confirmed by the independent reference). They are named in DR-07b but defined nowhere before this document. | adopt §4.2–§4.3 |
| D-A1-2 | Campaign contract `f1d-i` for the PU-4h gate; `full` reported (DR-07a) | adopt; full-contract diagnostics belong to WP A2 (scheduler-logging diagnostic configuration), not to A1 |
| D-A1-3 | Scope of "NOT EVALUATED (censored)" for PU-4o and A2-8/UE: reported, non-gating, versus gating. Also the PU-4o NX case. | non-gating for structural end-of-log censoring only. Any other NE gates. NX for a UE without DL PDUs is reported and **gates** (unexpected for gPTP DL). |
| D-A1-4 | Initial FGO registry content and citations, including V-V1's self-citation of A2-V1 | confirm row by row; remove any row whose genuine exercise is not explicit in an accepted record |
| D-A1-5 | PU-5 stays a gate (attribution-independent) | keep |
| D-A1-6 | CI change to add `test_m2s72_e0vn21.py` to tier-0 with its exact expected line | authorise at I-9, as a separate reviewed CI change |
| D-A1-7 | HELD FOR REVIEW: stop the batch, or continue and hold only that run | stop the batch (consistent with the per-run lifecycle "stop on gate failure") |
| D-A1-8 | Name guard in the wrapper versus changing `parse_name` | wrapper guard; `check_m2s72_s5v.py` is accepted tooling |
| D-A1-9 | Runtime budget: evaluate `full` in campaign runs, or `f1d-i` only (L-9) | `f1d-i` only in campaign runs; `full` on validation runs and diagnostics |
| D-A1-10 | The A-1 / A-2.1 agreement diagnostic: report or gate | report only (A-1 is not a correctness source; L-2) |

### 11.2 Risks

| Risk | Mitigation |
|---|---|
| R-1: the per-UE A2-8 duplicates `scalar_row`'s arithmetic | T-a28-agg makes the aggregate equal the accepted run-level row on every test input |
| R-2: `E.rows` global accumulation (L-11) | one run per process, enforced (T-one-run-per-process) |
| R-3: A-2.1 runtime and memory at N = 8 (no genuine N ≥ 3 evidence) | measured at the first N = 8 run; the per-run time is recorded in the digest; D-A1-9 |
| R-4: genuine N ≥ 3 paths (groups of 3+) are untested on real output | FGO HELD FOR REVIEW at first occurrence (DR-07d) |
| R-5: XA cannot separate some same-instant lines | A2-7 treats them as group multisets ("reference ambiguous"); occupancy equality remains exact; PU-4o relies on occupancy equality, not on per-line confirmation |
| R-6: the registry becomes a way to wave features through | changed only by maintainer-accepted records; registry sha256 recorded in every output; NC-registry tests |
| R-7: E0v-N runs on ideal channels contain no NACK, so the NACK paths stay validated only by A2-V1 and synthetic fixtures | stated in every record's coverage section (A-2.1 coverage table, unchanged); no general H-ARQ claim |
| R-8: the A2-V1 expectation in V-V1 depends on the VM-reported S1 values; the S1 archive is VM-only | V-V1 compares against the S1 closure tables. If the S1 archive is unavailable, V-V1 still evaluates the sealed A2-V1 run itself (58 files in the private archive). |

---

## 12. Summary for review

- **Problem.** A-1 makes PU-4 FAIL at N ≥ 2 by construction, which blocks the E0v-N campaign.
- **Change.** A-2.1, which is accepted on genuine output within stated limits, becomes the per-UE H-ARQ source through three new gating rows:
  - **PU-4h**: run attribution under F1-d(i);
  - **PU-4o**: per-UE occupancy confirmed by the independent UE-side reference;
  - **A2-8/UE k**: Simu5G per-UE statistics.
- **Review gate.** A **first-genuine-occurrence** flag holds any run that meets a path validated only synthetically.
- **Preservation.** The historical A-1 PU-4, and every accepted or failed record, are reported verbatim and never relabelled.
- **Code boundary.** Only new files are added. Frozen, accepted and s5n tooling stays byte-identical.
- **Validation.** V-N1, V-N2 and V-V1 are specified with exact expectations, for an independent executor. S5-2-D2 remains pending until they are accepted.
