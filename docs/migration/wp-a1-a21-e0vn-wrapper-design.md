# WP-A1 — Integration of A-2.1 into the E0v-N per-run evaluation (design)

**Status: revision 2, 23 November 2026. Design for independent review. Nothing is implemented.**
- Baseline: `m2/continuation` at `7bb0e3a7145602ae556239c8667362203d9294b5`; branch `wp/a1-a21-e0vn-wrapper`.
- Revision 1: commit `bd6de62` (18 November 2026). Reviewed; revision 2 required (findings C1–C6).
- Revision 2 resolves C1–C6 and records the reviewer's rulings on D-A1-1 … D-A1-10. The resolution table is §0.
- Level: design only. No code, configuration, record, fixture, workflow or evidence is changed.
- No simulation was run and no private evidence was read.
- Every source fact below was read from the repository at the baseline. File references are `simulations/m2/check/…` unless stated otherwise.
- Three read-only checks were run for this revision, on public repository content only (§1.6):
  - the name guard against every configuration in `m2s72s5.ini`;
  - the import behaviour of `python3 -I`;
  - the accepted A-2.1 evaluator on the committed F3 fixture, to declare T-f3-hrq.

**Decisions this design implements:**
- DR-07a: the campaign contract F1-d(i), plus separately labelled full-contract diagnostics.
- DR-07b: new wrapper rows PU-4h, PU-4o and A2-8u (per-UE A2-8); the A-1 PU-4 is preserved and reported.
- DR-07c: the three validations V-N1, V-N2 and V-V1.
- DR-07d: the first-genuine-occurrence review gate.
- S5-2-D2 remains pending; it waits for independent execution of V-N1 and V-N2.

**Fixed boundaries (never broadened):**
- A2-V1 is NOT ACCEPTED, permanently.
- The A-1 PU-4 FAIL of the N = 2 smoke is retained verbatim.
- A-2 stays frozen at `fbee202`.
- A-2.1 is accepted only as recorded:
  - F3: CLOSED ACCEPTED;
  - A2-V1-S1: CLOSED ACCEPTED under F1-d(i);
  - the full contract: INCOMPLETE.
- S7.2a remains partial.

---

## 0. Revision 2: finding-by-finding resolution

| Finding | Revision-1 defect | Revision-2 resolution | Where |
|---|---|---|---|
| **C1** run-level vs per-UE A2-8 | T-a28-agg asserted that the per-UE rows aggregate *exactly* to `scalar_row`. That is false: `scalar_row` can PASS while some comparisons are unavailable. | • The run-level A2-8 row of A-2.1 is preserved verbatim and keeps its frozen effect: a FAIL makes A-2.1 NOT VALID, so PU-4h FAILs.<br>• A new, separately named per-UE gate **A2-8u UE k** requires **both** statistics for **every** expected UE.<br>• The exact invariant is replaced by the compatibility relation CR-1 … CR-4.<br>• T-a28-compat tests every intentional difference.<br>• The tolerance formula and `REL_TOL = 1e-9` are quoted exactly; a `ValueError` gives NE; a non-finite value is handled explicitly. | §4.5, §7.1 |
| **C2** censoring vs frozen contract | Censored NE was non-gating, which contradicts A2-7 (NE whenever `touched_nodes` is non-empty) and its required status under F1-d(i). | • No non-gating exception remains. Uncertainty NE gates (D-A1-3 ruling).<br>• Attributable unit-level end states never populate `censored_nodes`; they are distinguished from uncertain group-level censoring: §4.2 table.<br>• Uncertain group-level censoring → A2-7 NE → F1-d(i) INCOMPLETE → PU-4h NE → run **INCOMPLETE**.<br>• The verdict tables, the tests (T-censor-*) and D-A1-3 are reconciled. | §4.2, §4.3, §4.8, §7, §11 |
| **C3** fail-closed occupancy | PU-4o fell through to PASS; a missing `occupancy_equal` entry could reach PASS; there was no mapping validation; NC-occ-one-ue claimed "UE 1 rows unchanged". | • PU-4o PASS requires all of: an explicit `occupancy_equal[n_k] is True`; a valid A-2.1 occupancy; a valid reference; A2-7 PASS; PU-4h PASS.<br>• Every other path is FAIL or NE; a missing entry is FAIL.<br>• A new gate row **MAP-UE** validates the complete bijective UE-to-node mapping.<br>• The *local comparison* is separated from the *row status*, which also applies the global rules.<br>• NC-occ-one-ue is corrected: UE 1's local comparison is reported unchanged, but its row FAILs by the global rule. | §4.4, §4.6, §7.3 |
| **C4** FGO registry | The registry was incomplete; it included rows supported only by inference or prediction; unknown features and known-but-unexercised features were not distinguished. | • All 18 `coverage()` features are enumerated with their exact names, genuine-exercise status, accepted record and contract, evidence strength and admission.<br>• Only 10 are admitted.<br>• Excluded: single-candidate ACK and NACK (not stated in any accepted record; inferred only) and the 6 known-unexercised features.<br>• Predicted N = 2 counts are never evidence. F3 and S1 support coverage only within their scope and accept nothing about A2-V1.<br>• Unknown, known-unexercised and missing features have distinct outcomes.<br>• Synthetic tests never write the registry. | §4.7 |
| **C5** digest and downstream | There was no field-level ownership, and A-1-derived per-UE H-ARQ values could appear as current results. | • The s5n digest is preserved byte-identical.<br>• A new composed digest has a field-by-field ownership map. Per-UE H-ARQ values come from A-2.1 only, each with an availability status. A-1 values are confined to `historical`.<br>• Across-UE aggregates are all-or-nothing.<br>• The A3 batch interface and the A5 comparator interface are documented, not implemented. | §5.3, §5.4, §5.5 |
| **C6** commands and tests | • T-n1-identity was wrong without UE logs.<br>• The fixture interface was implicit.<br>• C-0 compared totals only.<br>• Historical rows could be dropped.<br>• The name guard was unverified.<br>• Each contract was replayed separately.<br>• The `-I` import was unverified.<br>• Commands were abbreviated.<br>• The batch boundary was unspecified.<br>• An expectation mismatch could exit 0. | • T-n1-identity: PU-4h NE without UE lines.<br>• New `hrq-fixture` mode with an explicit interface.<br>• C-0 is canonical event-sequence equality, with negative controls that keep the counts identical but change the events.<br>• Required s5n row presence, with exact s5n gate semantics (PU-4 is the only change).<br>• The name guard was checked against all 459 configurations: 294 E0v-N accepted, 0 others.<br>• One replay; both contract verdicts are derived from the same rows.<br>• `-I`: every script inserts its own directory; verified.<br>• Complete command blocks, including the extractor.<br>• The A3 boundary and the S5-2-D2 enforcement.<br>• Expectation mismatch exits 5. | §3.3, §4.9, §5, §7, §8 |
| **N ≥ 2 claim** | "PU-4 FAILs by construction at N ≥ 2" | Qualified: the demonstrated mechanism is same-process, same-instant overlapping feedback of two UEs (384 pairs on the N = 2 smoke). It is a property of the schedule, not of N alone. | §2 L-1, L-3; §12 |

**Rulings recorded** (reviewer, revision 1):

| Decision | Ruling | Applied in |
|---|---|---|
| D-A1-1 | approved, subject to C1–C3 | §4 |
| D-A1-2 | F1-d(i) campaign contract approved | §4.3 |
| D-A1-3 | uncertainty-related NE stays gating | §4.2, §4.8 |
| D-A1-4 | complete registry and evidence review required | §4.7 |
| D-A1-5 | retain PU-5 | §4.9 |
| D-A1-6 | new tier-0 suite approved in principle; separate CI review at implementation | §9 I-9 |
| D-A1-7 | stop the batch on HELD FOR REVIEW | §5.4 |
| D-A1-8 | wrapper-local name guard | §5.2 |
| D-A1-9 | single replay; contract verdicts derived without duplicate evaluation | §3.3 |
| D-A1-10 | A-1 agreement is diagnostic only | §4.10 |

---

## 1. Current architecture (as implemented at the baseline)

### 1.1 The E0v-N per-run path: `check_m2s72_s5n.py run <runs> <cfg> <records>`

1. **Refusal.** The run is refused (exit 2) in either case:
   - `S5N_ADAPTER_VALIDATED` is not set (decision S5-2-D2);
   - the name does not parse as kind `E0vN` (`check_m2s72_s5v.parse_name`).
2. **Accepted Block B evaluation at N.** `evaluation()` calls `check_m2s72_e0` / `_b` / `_i2h` (unchanged).
   - The rows accumulate in the module-global list `E.rows`.
   - F0-1 is relabelled "F0-1 (info)".
   - EOR is NOT APPLICABLE.
3. **Per-UE observation.** `m2s72_peru_adapter.observe(ev, run-<cfg>.log.gz, option, loaded, nproc)`:
   - `harq_events()` extracts the gNB insert lines `("ins", t_ps, node, process, codeword)` and the feedback lines `("fb", t_ps, process, codeword, result)`, in log order. The insert lines name the node; the feedback lines name no UE.
   - `m2s72_peru.attribute_feedback()` applies **rule A-1**:
     - A-1a: the only open candidate;
     - A-1b: the unique candidate at the single delay d*;
     - otherwise AMBIGUOUS, ORPHAN or RE-INSERT.
   - It returns per-node counts and an occupancy (produced only when the attribution is exact), plus a run summary `{a1a, a1b, ambiguous, orphan, reinsert, d_star_ps, a1a_delays_ps}`.
   - The adapter stores per UE `harq = {processes, inserts, feedback, nack, occupancy, feedback_delay_ps}` (`m2s72_peru_adapter.py:169`). `feedback`, `nack`, `occupancy` and `feedback_delay_ps` are **A-1-derived**. `processes` and `inserts` are not: the insert lines name their node.
4. **Correctness rows.** `m2s72_peru_adapter.validate()` → `m2s72_peru.structural_rows()`:
   - PU-1 (run); PU-2 and PU-3 per UE; PU-4 (run); PU-5 (run);
   - then AV-1, AV-2 and AV-3 per UE.
   - **PU-4 = A-1 complete:** ambiguous = orphan = re-insert = 0. It is NOT EVALUATED without a MAC log.
   - **PU-5:** the per-UE DL grant bytes and per-UE inserts sum to the run totals.
5. **Further rows:** Q8-v, SG-403 and MG-1 (`check_m2s72_s5v`, unchanged).
6. **Gate semantics** (`check_m2s72_s5n.py:140-141`, quoted):
   - `gate_fail = sorted({r[0] for r in mine if r[2] == "FAIL" and r[0] not in E.INFO})`
   - `ne = sorted({r[0] for r in mine if r[2] == E.NE and r[0].startswith(("PU-", "AV-"))})`
   - Verdict: `PASS` iff both are empty, otherwise `FAIL <ids> NE:<ids>`. The exit code is 0 or 1.
   - An NE row outside PU / AV (for example Q8-v NE "no MAC log") does not gate.
7. **Outputs:** `<cfg>.check.txt`, plus `<cfg>.digest.json`, which holds:
   - `{config, kind, option, placement, numUe, harq16, dl_factor}`;
   - `correctness{gate_failures, per_ue_not_evaluated, rows}`;
   - `performance{per_ue, across, harq_attribution, totals}`;
   - `mac_grammar_census`.

### 1.2 The A-2.1 path, standalone: `check_m2s72_a21.py a21 <runs> <cfg> <records> [--contract full|f1d-i] [--t0 <s>]`

1. **Inputs** (`inputs()`):
   - every MAC-log line (`m2s72_a21.load`);
   - DL grants (`m2s72_maclog`);
   - node ids from `check_m2s72_a2._node_ids` = `Run72(...).node_id`. This reads the `.sca` `par … ue[k].cellularNic.nrMac macNodeId` records. It raises on a missing or duplicate id, and `_node_ids` then returns `None`.
   - `<runs>/<cfg>/<cfg>/0.sca`;
   - `$SIMU5G_ROOT`.
2. **One replay.** `m2s72_a21.evaluate()` calls `replay()` once and then `rows_for()`. It returns `res, rows, per, cov, extra, window`. `extra = {"preconditions", "xa": x7, "scalars": x8}`.
   - `res["fb"]`: the feedback lines, in log order, each `{j, gi, t, p, cw, res, cls, owner, …}`.
   - `res["pdus"]`: the lifecycle units by PDU id, each `{pid, node, p, cw, t_ins, ins_gi, ntx, end, …}`.
   - `res["groups"]`: the groups; a pending group at the end carries `censored_nodes`.
3. **Rows** A2-0, A2-0s, A2-1, A2-2, A2-3, A2-4a, A2-4b, A2-4c, A2-5, A2-6, A2-7, A2-8, A2-9. All are run-level.
4. **Verdict** `verdict(rows, contract)`. This is a **pure function of `rows`**: it does not replay.
   - Any FAIL → NOT VALID (rc 1).
   - Else a required row neither PASS nor NOT EXERCISED → INCOMPLETE (rc 4).
   - Else → VALID (rc 0).
   - `REQUIRED["full"]` = A2-0, A2-0s, A2-1, A2-2, A2-3, A2-4a, A2-4b, A2-4c, A2-5, A2-6, A2-7, A2-9.
   - `REQUIRED["f1d-i"]` = the same without A2-4c.
   - A2-8 is in neither list, but an A2-8 FAIL makes the verdict NOT VALID.
5. **The standalone writer** `check_m2s72_a21.a21()` calls `evaluate()` itself. Writing two contracts through it replays twice.
6. **Coverage** `coverage(res, rows)` returns the 18 features of §4.7, each with a count and either "EXERCISED by this input" or "NOT EXERCISED → <SYNTH entry>".

### 1.3 A2-7, A2-8 and censoring, as frozen in the accepted A-2.1 (`m2s72_a21.py`, `d920125`)

**End-of-log classification** (`m2s72_a21.py:660-694`):

| Level | End state | Populates `g["censored_nodes"]`? | Attribution of the UE |
|---|---|---|---|
| group (a pending group at the end, after `finalize_all`) | `censored: awaiting resolution` (structural: no complete main loop after it); line class `censored` | **yes**: every candidate node | **uncertain**: the lines are unresolved between candidates |
| group | `unresolved: pending group at the end` (not structural); line class `unresolved-pending`; also listed in `res["unresolved"]`, so A2-9 is NE | **yes** | **uncertain** |
| unit | `censored: awaiting feedback` (state WAIT, last transmission + d* > t_end) | no | **attributable**: the unit's node is known from its insert line |
| unit | `censored: inserted in the last TTI` | no | attributable |
| unit | `censored: awaiting retransmission` (structural, buffered after a resolved NACK) | no | attributable |
| unit | `unresolved: retransmission not observed` (A2-9 NE) | no | attributable, but A2-9 NE |

**`touched_nodes(res)`** = the union of `censored_nodes` over the groups. It is therefore non-empty **only** for group-level (uncertain) end states.

**`xa_rows` (A2-7):**
- Returns NE with x7 = `None` when the log has no UE-side H-ARQ lines.
- Returns FAIL with x7 = `None` when the reference itself is invalid, or when the line counts differ.
- Otherwise it compares, excluding `skip = touched_nodes(res)`:
  - lines and group multisets;
  - per-node feedback, NACK and latency;
  - per-node occupancy: `occ_eq = {n: occ_x.get(n) == a2_per[n]["occupancy"] for n in a2_per if n not in skip}`.
- Its status is `FAIL if bad else (NE if skip else PASS)`. A2-7 is therefore **NE whenever `skip` is non-empty**, even if every comparison made is equal.
- `x7 = {"confirmed", "occupancy_equal", "skipped"}`.

**`scalar_row` (A2-8):**
- For each `(module, node)` of `A2.sca_nodes(sca)`:
  - a node in `skip`, or with no attributed feedback → `ne`;
  - each statistic is checked: `harqErrorRateDl:mean` = nack / feedback, and `harqTxAttemptsDl:mean` = the mean `ntx` of the ACKed units (`None` if there is none);
  - a statistic that is absent, or whose value is `None` → `ne`;
  - `rec = float(s[name])`; a `ValueError` → `ne`;
  - otherwise `ok = abs(rec - val) <= REL_TOL * max(1.0, abs(val))`, with `REL_TOL = 1e-9`.
- The status is computed in this order:
  1. FAIL if any comparison is not ok;
  2. NE if `skip & nodes`;
  3. NE if nothing was compared;
  4. otherwise **PASS**.
- PASS therefore holds while **some** comparisons are unavailable, provided at least one succeeded, none failed and no mapped node is in `skip`.
- A non-finite `rec` (`nan`, `inf`) parses without error. `abs(rec - val) <= …` is then false, so it is **FAIL** at run level.

### 1.4 The independent reference and the N = 2 smoke tooling

`check_m2s72_s5n2.py xa | controls-n2 | verdict` and `m2s72_harqx.py` provide:
- XA-0 … XA-6;
- the overlap census;
- the truth occupancy, reconstructed from the UE MAC lines `H-ARQ RX: new PDU (id X )` and `feedback sent`.

XA is the oracle that A2-7 reuses.

### 1.5 Frozen and accepted modules (never modified by WP-A1)

| Module | Status | Pin |
|---|---|---|
| `m2s72_a2.py`, `check_m2s72_a2.py`, `m2s72_a2probe.py`, `m2s72_harqfix.py`, `m2s72_harqx.py`, `m2s72_peru.py`, `test_m2s72_a2.py` | **frozen** (A-2, XA, A-1 / PU-4) | `fbee202`, enforced by `test_m2s72_a21.py` T-frozen-untouched |
| `check_m2s72_a2v1.py` | **frozen** (A2-V1 evaluator) | `39a6434`, same test |
| `m2s72_a21.py`, `check_m2s72_a21.py`, `m2s72_harqfix21.py`, `m2s72_a21_fixture.py`, `m2s72_a21_realchain.py` | **accepted**: F3 at `d920125`; S1 evaluated at `ddc1a93`, with zero code difference | treated as frozen by WP-A1 (§6) |
| `check_m2s72_s5n.py`, `m2s72_peru_adapter.py`, `check_m2s72_s5v.py`, `check_m2s72_s5n2.py`, `m2s72s5_lib.py` | tooling of the accepted S5-1 / S5-2 / N = 2 smoke records | kept byte-identical |
| `simulations/m2/m2s72s5.sh` (batch runner), `*.ini`, generators | accepted | never modified by WP-A1 (the A3 boundary, §5.4) |
| `simulations/m2/check/fixtures/a2v1-first-chain.log.gz` (+ `.sha256`, `.meta.json`) | genuine F3 fixture | sha256 `cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b`, gated by tier-0 |

### 1.6 Recorded facts the design relies on

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

**A-2 line-class counts on N = 1 / N = 2 are not evidence.** `-a2-implementation.md` §4 labels them "(predicted)", and that record's status is "implemented, not yet validated on the VM".
- The A-2 runs the VM reported (`-a2-control-fix.md`: "A-2 VALID (rc 0)") are not accepted records. Their controls were NOT AS DECLARED.
- No accepted record states the line classes of either smoke.
- V-N1 and V-N2 (§8) are the first records that can.

**A2-V1-S1** (`-a21-s1-closure.md` §3–§4; CLOSED ACCEPTED under F1-d(i)), configuration `M2S72-E0vN-q0-one0-n2-f1_A2V1`:

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
- 371 certified exchangeable groups, with 742 exchangeable lines;
- 40 lines resolved by retransmission evidence, 15 by bound handles;
- 129 handles, all retired;
- unresolved `[]`;
- end states only `censored: awaiting feedback` (S-7);
- XA agrees for both UEs, including per-UE occupancy;
- A2-8 values:

| Node | `harqErrorRateDl:mean` | `harqTxAttemptsDl:mean` |
|---|---|---|
| 2049 | 0 | 1 |
| 2050 | 0.10227272727272728 | 1.1139240506329113 |

- `full` → INCOMPLETE (A2-4c NOT EVALUATED); `f1d-i` → VALID.

**F3** (`-a21-f3-closure.md`; CLOSED ACCEPTED):
- a prefix of the same run, up to 385 ms;
- the mixed 366 ms group, whose NACK is `resolved-by-rtx` and bound to node 2050 / PDU 145933;
- handle 54326 bound at 366 ms and retired at 384 ms;
- A2-4a and A2-4b PASS; A2-4c NE; A2-8 NE (prefix);
- `f1d-i` VALID, `full` INCOMPLETE;
- **not** an A2-V1 acceptance.

**Configuration facts** (`simulations/m2/m2s72s5.ini`; `check_m2s72_s5v.parse_name`):
- Every E0v-N configuration extends `M2S72-MACLOG` and `M2S72S5-MACLOG-UE`, so the gNB **and** UE MAC lines are logged.
- No E0v-N configuration enables `mac.schedulerDl` logging, so A2-4c can never PASS on a campaign run.
- HARQ16 configurations are named `M2S72-E0vN-…`; HARQ5 configurations are `M2S72-E0vNH5-…`.

**Read-only checks run for revision 2** (public content; no simulation; no private evidence):

| Check | Result |
|---|---|
| Name guard (§5.2) against every `[Config …]` in `m2s72s5.ini` (459 names) | **294 accepted**: `E0vN` 168 + `E0vNH5` 126.<br>• n1 42, n2 84, n4 84, n8 84.<br>• options q0 84, q0p 84, qdu 84, qde 42; placements one0 168, sym 126.<br>• factors 0p5 49, 0p8 49, 1 49, 1p25 49, 1p6 49, 2 49.<br>**0 non-E0v-N names accepted.**<br>`parse_name(...)[0] == "E0vN"` holds for **exactly** the same 294 names, so the guard and the parser agree on every generated configuration.<br>The four `M2S72-E0vNL-q0-f{1,2,4,8}` are the **N = 1** E0v non-perturbation twins (kind `E0vNL`). They contain the substring "E0vN" but are not E0v-N and are rejected. |
| `python3 -I` (Python 3.13.18 here) | `-I` implies `-P`, so the script directory is **not** on `sys.path`. Every existing checker inserts it itself (`sys.path.insert(0, HERE)`: `check_m2s72_s5n.py:28`, `check_m2s72_a21.py:25`, `check_m2s72_s5n2.py:28`, `m2s72_a21.py:47`, `m2s72_a21_realchain.py:22`). `m2s72_a21_fixture.py` imports nothing from the repository.<br>`-I` ignores only `PYTHON*` variables and the user site directory. `SIMU5G_ROOT` and `S5N_ADAPTER_VALIDATED` are still read. |
| Accepted A-2.1 on the committed F3 fixture (`load_fixture` + `evaluate`, t0 = 0, no `.sca`, no `SIMU5G_ROOT`) | Rows: A2-0s, A2-4c and A2-8 NE (no root, no scheduler line, no `.sca`); every other row PASS.<br>`touched_nodes` = ∅; x7 `occupancy_equal` = `{2049: True, 2050: True}`.<br>Coverage counts:<br>• single-candidate ACK 83;<br>• exchangeable (2) 5;<br>• bound 2;<br>• resolved-by-rtx 1;<br>• retransmissions 3;<br>• mixed groups 3;<br>• awaiting feedback 6;<br>• occupancy confirmed 2;<br>• A2-7 1; A2-4b 1;<br>• every other feature 0.<br>These are public-fixture observations used only to **declare** T-f3-hrq. They are never registry evidence (§4.7). |

---

## 2. Identified technical limitations

| ID | Limitation | Evidence | Consequence |
|---|---|---|---|
| L-1 | A-1 cannot attribute a feedback line when two UEs have the same process open and their feedback arrives at the same instant. One gNB feedback line names no UE, and every UE's H-ARQ entity takes its lowest free process. | N = 2 smoke: 384 same-TTI same-process pairs → 768 ambiguous lines, 768 re-inserts | **PU-4 FAILs whenever such same-process overlapping feedback occurs.** This depends on the schedule, not on N alone.<br>• The N = 2 smoke has it with load on UE 0 only, because every UE carries a gPTP DL stream.<br>• It is expected at most N ≥ 2 configurations.<br>• An N ≥ 2 run without any same-process, same-instant overlap would not fail PU-4 under A-1.<br>This is a demonstrated mechanism, not a theorem about N. |
| L-2 | A-1 closes a unit at its first feedback, NACK included. Under NACKs, its later A-1a attributions are not trustworthy. | `m2s72_peru.attribute_feedback` (`open_.pop(pick)` on any feedback); a2 design review §2 | A-1 is not a valid per-UE source when NACKs occur |
| L-3 | `check_m2s72_s5n.py run` gates on PU-4, so every E0v-N run that contains same-process overlapping feedback fails | N2-D2: "the E0v-N campaign cannot start under A-1"; L-1 | The E0v-N bracket and E1 are blocked |
| L-4 | A-2.1 exists only as a standalone CLI. Its A2-7 and A2-8 are run-level, so there is no per-UE correctness row for occupancy or for Simu5G statistics. | `m2s72_a21.rows_for`, `xa_rows`, `scalar_row` | A per-UE measurement cannot be gated per UE |
| L-5 | E0v-N configurations have no scheduler logging | `m2s72s5.ini` | `full` is INCOMPLETE whenever retransmissions occur; the campaign contract must be F1-d(i) (DR-07a) |
| L-6 | Several A-2.1 paths have no genuine evidence in any accepted record (§4.7) | S1 closure §5; `m2s72_a21.SYNTH` | DR-07d requires review before any result relies on them |
| L-7 | `parse_name` accepts a suffixed configuration as `E0vN`, with a string factor (`'1_A2V1'`) | `check_m2s72_s5v.parse_name` | A non-campaign run could be evaluated as a campaign run |
| L-8 | `S5N_ADAPTER_VALIDATED` (S5-2-D2) is not set. The adapter's part B has never been validated on real MAC-logged N > 1 output under a rule that can pass. | S5-2 addendum §3.4 | E0v-N evaluation stays refused until V-N1 / V-N2 are accepted and S5-2-D2 is decided |
| L-9 | A-2.1 replay costs about 70 s on the 12 s N = 2 run (S1 closure S-5) and grows with the line count | S1 closure | One replay per run (D-A1-9); N = 8 needs a measured budget |
| L-10 | Tier-0 runs a hard-coded list of suites with exact expected lines | `.github/workflows/tier0-python.yml` | A new suite is not run by CI until the workflow lists it (D-A1-6) |
| L-11 | `E.rows` is a module-global list, appended to by the accepted checkers | `check_m2s72_s5n.py` | One run per process |
| L-12 | `scalar_row` PASS does not mean every UE was compared (§1.3) | `m2s72_a21.py:965-987` | A per-UE gate cannot be derived from the run-level row (C1) |
| L-13 | A2-7 is NE whenever any group-level censoring exists, and A2-7 is required under F1-d(i) | `m2s72_a21.py:935` | A run whose log ends inside an unresolved group is INCOMPLETE, never PASS (C2) |
| L-14 | The batch runner has no E0v-N batch mode; its `s5_full` treats any non-zero check rc as STOP | `m2s72s5.sh:139-170` | Wiring the wrapper into a batch is A3's task (§5.4) |

---

## 3. Proposed architecture

### 3.1 Principle

A **new wrapper** composes the unchanged E0v-N evaluation with one unchanged A-2.1 evaluation. It changes only the **gate scoping** of the H-ARQ attribution:

| | Before (S5-2) | After (WP-A1) |
|---|---|---|
| PU-4 (A-1) | gate | **reported verbatim, not a gate** (DR-07b). The **only** change to the s5n gate set. |
| MAP-UE (UE-to-node bijection) | — | **gate** |
| C-0 (canonical event-sequence consistency) | — | **gate** |
| PU-4h (A-2.1 attribution, run, F1-d(i)) | — | **gate** |
| PU-4o UE k (per-UE occupancy, A-2.1 confirmed by XA) | — | **gate**, one per expected UE |
| A2-8u UE k (Simu5G per-UE statistics, both required) | — | **gate**, one per expected UE |
| A2-8 (A-2.1 run-level, frozen) | — (standalone only) | reported verbatim; a FAIL acts through A-2.1 NOT VALID → PU-4h FAIL |
| First-genuine-occurrence flag (DR-07d) | — | **review gate**: HELD FOR REVIEW |
| PU-1, PU-2, PU-3, PU-5, AV-1 … AV-3, Block B, I-2H, per-UE Q8, Q8-v, SG-403, MG-1 | gates (s5n predicate) | **unchanged**, with the identical predicate (§4.9) |

**Historical results stand.**
- Nothing is relabelled.
- The unchanged `check_m2s72_s5n.py` records, including the s5n digest and its verdict line ("FAIL PU-4" where A-1 is incomplete), are produced byte-identically and kept.
- The new verdict is a separate, labelled evaluation result.

### 3.2 Modules (all new files; nothing existing is edited)

| New file | Role |
|---|---|
| `check/m2s72_e0vn21.py` | **Library: pure functions** over the outputs of the unchanged evaluators.<br>• MAP-UE, C-0, PU-4h, PU-4o, A2-8u;<br>• the A-1 historical report;<br>• the agreement diagnostic;<br>• the FGO registry loader and flag;<br>• the s5n row-set check;<br>• the composed verdict;<br>• the digest builder;<br>• the expectation comparator.<br>It reads no raw file. It begins with `HERE = os.path.dirname(os.path.abspath(__file__)); sys.path.insert(0, HERE)` before any local import (§1.6, `-I`). |
| `check/check_m2s72_s5n21.py` | CLI with modes `run`, `hrq`, `hrq-fixture` and `controls` (§5.1). One evaluation per process (L-11). Same `sys.path` preamble. |
| `check/m2s72_fgo_registry.json` | The FGO registry: all 18 known features, each with its admission and its evidence (§4.7). Changed only by maintainer-accepted records. |
| `check/test_m2s72_e0vn21.py` | The test suite of §7. Same `sys.path` preamble. |
| `check/expect/vn1.expect.json`, `vn2.expect.json`, `vv1.expect.json`, `f3.expect.json` | The declared expectations of §7.2 and §8, committed before any execution |
| `simulations/m2/results/M2-S7.2a-a1-implementation.md` | Implementation report, written at implementation time |

**Never modified:**
- every module in §1.5;
- `m2s72s5.sh`;
- the `.ini` files and the generators;
- `.github/workflows/*`, until the separate CI review of D-A1-6.

**Import discipline.** The wrapper calls only these functions:

| Function | Use |
|---|---|
| `check_m2s72_s5n.run_one` | the unchanged s5n evaluation; its rows are read back from `S5V.E.rows[start:]` |
| `check_m2s72_a21.inputs` | the A-2.1 inputs |
| `m2s72_a21.evaluate` | **once** per evaluation |
| `m2s72_a21.verdict` | twice, on the same rows |
| `m2s72_a21.touched_nodes` | the group-censored nodes |
| `m2s72_a21_realchain.load_fixture` | `hrq-fixture` only |
| `m2s72_peru_adapter.harq_events` and `m2s72_peru.attribute_feedback` | the A-1 report and C-0 |
| `m2s72_a2.sca_nodes`, `m2s72_a2probe.scalars`, `m2s72_a2probe.R_UE_MOD` and `m2s72_a21.REL_TOL` | exactly as `m2s72_a21.scalar_row` uses them |

`sys.argv` isolation follows the existing pattern of `check_m2s72_s5n.py`.

### 3.3 Data flow of `run` (single replay, D-A1-9)

```
check_m2s72_s5n21.py run <runs> <cfg> <records dir>
  0  name guard (§5.2); S5N_ADAPTER_VALIDATED non-empty (S5-2-D2); <records dir> fresh
  1  start = len(S5V.E.rows); S5N.run_one(runs, cfg, <records dir>/s5n)
        -> unchanged s5n records and verdict; s5n_rows = S5V.E.rows[start:]
        -> s5n row-set check (§4.9): a missing required row -> EVALUATION ERROR (exit 2), never dropped
  2  A-1 historical: the s5n PU-4 row verbatim; summary = s5n digest harq_attribution (verbatim)
  3  lines, grants, node_id, sca, root = A21C.inputs(runs, cfg)
     node_id is None -> REFUSED (exit 2)
     res, rows, per, cov, extra, window = A21.evaluate(lines, nproc, t0, node_id, grants, sca, root)   # ONE replay
     v_f1di = A21.verdict(rows, "f1d-i"); v_full = A21.verdict(rows, "full")                           # pure, no replay
  4  MAP-UE (§4.4); C-0 (§4.1) from harq_events(<log>) and (res)
  5  PU-4h (§4.3); PU-4o UE k (§4.6); A2-8u UE k (§4.5); agreement diagnostic (§4.10)
  6  FGO (§4.7) from cov and rows
  7  composed verdict (§4.8); records (§5.3): one a21 record holding both contract verdicts, the s5n21 record,
     and the composed digest
```

The A-2.1 record is written by the wrapper from the single evaluation, in the section layout of `check_m2s72_a21.a21()` (ROWS, COVERAGE, PER UE, handles). It carries both verdict lines: `A-2.1 verdict (f1d-i): …` and `A-2.1 verdict (full): …`. T-single-replay asserts that `replay` runs exactly once per invocation. T-a21-record-equiv asserts that the rows, coverage and per-UE sections equal those written by the accepted `check_m2s72_a21.a21()` on the same synthetic run, for each contract.

---

## 4. Evaluation contract

### 4.0 Status vocabulary

`PASS`, `FAIL`, `NOT EVALUATED` (NE), `NOT EXERCISED` (NX), `NOT APPLICABLE` (NA), `HELD FOR REVIEW` (HR).
- Only PASS, and NX where a row allows it, counts toward acceptance.
- NE is never a pass, and **every NE of a wrapper gate row gates**. There is no non-gating NE among the new rows (D-A1-3).
- HR is never a pass or a fail.

Every per-UE row has two parts:
- a **local comparison outcome** for that UE: EQUAL, DIFFERENT or NOT COMPARED (with the reason);
- a **row status**, which also applies the **global rules** (MAP-UE, PU-4h, A2-7).

A row is PASS only if its local outcome is EQUAL **and** every global precondition is PASS. Both parts are recorded.

### 4.1 C-0: canonical event-sequence consistency (gate)

A-1 and A-2.1 must have parsed **the same gNB H-ARQ events, in the same order**. Equal counts are not sufficient.

**Canonical event forms** (integers in ps, in log order):

| Source | Insert event | Feedback event |
|---|---|---|
| A-1: `harq_events(<log>)`, as produced | `("ins", t, node, process, codeword)` | `("fb", t, process, codeword, result)` |
| A-2.1: `res`; inserts are the units of `res["pdus"]`, feedback is `res["fb"]`; merged by the log line index (`ins_gi` / `gi`) | `("ins", u["t_ins"], u["node"], u["p"], u["cw"])` | `("fb", x["t"], x["p"], x["cw"], x["res"])` |

**C-0 PASS** iff the two sequences are equal element by element, with the same length and the same order.

**C-0 FAIL:**
- otherwise, reporting the first differing index, both events there, both lengths and the sha256 of each sequence's canonical JSON encoding;
- also when the A-2.1 sequence cannot be built: the `res["pdus"]` count differs from `res["counts"]["insert lines"]`, for example on a duplicated PDU id.

Both sha256 values are recorded in every case. The gNB module name of the two parsers is asserted equal at import (T-c0-module: `m2s72_peru_adapter.harq_events` default `gnb` == `m2s72_a2probe.GNB`).

### 4.2 Censoring classes and their effect (C2, D-A1-3)

| Class | End states (§1.3) | `touched_nodes` | A2-7 | F1-d(i) verdict | PU-4h | Per-UE rows of the affected UE | Composed |
|---|---|---|---|---|---|---|---|
| **Attributable outstanding feedback** (ordinary) | `censored: awaiting feedback` | ∅ (unaffected) | unaffected (S1: PASS with 6 such units) | unaffected | unaffected | unaffected: the units contribute no feedback line, and the counts of attributed feedback stay exact | unaffected. FGO: admitted (§4.7) |
| **Attributable, not yet genuine** | `censored: inserted in the last TTI`, `censored: awaiting retransmission` | ∅ | unaffected | unaffected | unaffected | unaffected | **HELD FOR REVIEW** (FGO: not admitted) unless otherwise INCOMPLETE / FAIL |
| **Attributable but unresolved** | `unresolved: retransmission not observed` | ∅ | unaffected | **INCOMPLETE** (A2-9 NE) | **NE** | NE (global) | **INCOMPLETE** |
| **Uncertain attribution: structural** | `censored: awaiting resolution` | candidate nodes | **NE** (`skip` non-empty) | **INCOMPLETE** (A2-7 required) | **NE** | touched UE: NE (local NOT COMPARED: uncertain); other UEs: local outcome reported, row NE (global) | **INCOMPLETE** |
| **Uncertain attribution: not structural** | `unresolved: pending group at the end` | candidate nodes | **NE** | **INCOMPLETE** (A2-7, A2-9) | **NE** | as above | **INCOMPLETE** |

**No censoring NE is non-gating.** A run whose log ends inside an uncertain group is INCOMPLETE. A maintainer review cannot convert it to PASS; only a new evaluation can, and none is defined here (R-9).

### 4.3 PU-4h: H-ARQ attribution of the run (A-2.1, F1-d(i)), gate

| Condition (in order) | PU-4h |
|---|---|
| MAP-UE FAIL | **FAIL** ("UE-to-node mapping invalid") |
| C-0 FAIL | **FAIL** ("parser divergence at event i: A-1 …, A-2.1 …") |
| `verdict(rows, "f1d-i")` = NOT VALID (any A2 row FAIL, **including the run-level A2-8 and A2-4c**) | **FAIL**; the detail names every failing A2 row |
| `verdict(rows, "f1d-i")` = INCOMPLETE (a required row NE, e.g. A2-0s without `$SIMU5G_ROOT`, A2-7 without UE lines or with `touched_nodes` ≠ ∅, A2-9 unresolved) | **NE**, gating; the detail names the rows and, for A2-7, the touched nodes |
| `verdict(rows, "f1d-i")` = VALID, C-0 PASS, MAP-UE PASS | **PASS** |

**Detail:**
- the counts of single, exchangeable, bound and resolved-by-retransmission lines;
- d*_tx;
- end states;
- handles.

**Also recorded:** `verdict(rows, "full")`, from the **same** rows, labelled "full contract (reported; scheduler logging absent in E0v-N configurations)".
- On ACK-only input it is VALID, because A2-4a/b/c are NX.
- With retransmissions it is INCOMPLETE, by design.

### 4.4 MAP-UE: complete bijective UE-to-node mapping, gate

**Inputs:**
- N, from the name (= `numUe` of the run, as checked by s5n);
- `node_id = {k: n_k}`, from `Run72` via `inputs()`;
- `sca_nodes(sca) = {module: n}`;
- the node set of `res["pdus"]`;
- the keys of `per`;
- the keys of `x7["occupancy_equal"]` and `x7["skipped"]`, when x7 is not `None`.

| Condition | MAP-UE |
|---|---|
| `node_id is None` (Run72 raised: a missing or duplicate `macNodeId`) | **REFUSED**, exit 2, at step 3. Nothing is guessed. |
| `set(node_id) != {0, …, N−1}` or `len(set(node_id.values())) != N` | **FAIL** (library path; reachable with injected maps in tests) |
| `.sca` present and `sca_nodes(sca) != {f"M2S72Bridge.ue[{k}].cellularNic.nrMac": n_k for k < N}`: an extra UE module, a missing module, or a different id | **FAIL** |
| a node in `res["pdus"]`, `per`, `occupancy_equal` or `skipped` outside `{n_k}` | **FAIL** ("evidence for an unmapped node") |
| `.sca` absent | MAP-UE on `node_id` alone. A2-8u is NE (§4.5). A run without `.sca` cannot have a `node_id` from Run72, so in `run` this case is REFUSED; it arises only in `hrq-fixture`, where the node ids come from the pinned fixture metadata. |
| otherwise | **PASS** |

### 4.5 A2-8u UE k: Simu5G per-UE statistics, gate, one row per expected UE (C1)

**Preserved:** A-2.1's run-level A2-8 row is reported **verbatim**, status and detail, with its frozen semantics (§1.3). It is never re-derived from the per-UE rows, and the per-UE rows are never derived from it.

**Local comparison for UE k** (module `M2S72Bridge.ue[k].cellularNic.nrMac`, node n_k), in order:

| Step | Condition | Local outcome |
|---|---|---|
| 1 | `scalars(sca)` is `None` or empty, or `sca_nodes(sca)` is empty | NOT COMPARED ("no Simu5G per-UE H-ARQ scalars") |
| 2 | no scalar record for the module | NOT COMPARED ("no statistics for ue[k]") |
| 3 | `n_k ∈ touched_nodes(res)` | NOT COMPARED ("uncertain attribution: censored or pending group") |
| 4 | no feedback attributed to n_k (`feedback == 0`) | NOT COMPARED ("no feedback") |
| 5 | for **each** of `harqErrorRateDl:mean` (val = nack / feedback) and `harqTxAttemptsDl:mean` (val = mean `ntx` of the ACKed units of n_k; `None` if there is none):<br>• name absent, or val `None` → that statistic NOT COMPARED ("absent" / "no ACKed lifecycle");<br>• `rec = float(s[name])` raises `ValueError` → NOT COMPARED ("unparsable");<br>• `not math.isfinite(rec)` → DIFFERENT ("non-finite Simu5G value against a finite A-2.1 value"), checked explicitly;<br>• otherwise equal iff `abs(rec - val) <= REL_TOL * max(1.0, abs(val))`, `REL_TOL = 1e-9` (`m2s72_a21.REL_TOL`), else DIFFERENT | |
| 6 | either statistic DIFFERENT | **DIFFERENT** |
| 7 | else either statistic NOT COMPARED | **NOT COMPARED** (both statistics are required) |
| 8 | both equal | **EQUAL** |

**Row status A2-8u UE k:**

| Condition (in order) | Status |
|---|---|
| MAP-UE FAIL or PU-4h FAIL | **FAIL** (global; the local outcome is reported) |
| local DIFFERENT | **FAIL** |
| local NOT COMPARED | **NE** (gating) |
| local EQUAL and PU-4h NE | **NE** (global: the counts are not established) |
| local EQUAL and PU-4h PASS | **PASS** |

**Compatibility relation with the run-level A2-8 (replaces the revision-1 exact invariant).** Let R be A-2.1's run-level A2-8 status and L_k the local outcome of UE k. Under MAP-UE PASS, so that the scalar modules are exactly the N expected modules:

| ID | Relation |
|---|---|
| CR-1 | R = FAIL ⇔ ∃k: L_k = DIFFERENT |
| CR-2 | R = PASS ⇒ (∀k: L_k ∈ {EQUAL, NOT COMPARED}) ∧ (∃k: at least one statistic of UE k compared equal) ∧ (∀k: n_k ∉ touched) |
| CR-3 | R = NE ⇒ (∀k: L_k ≠ DIFFERENT) ∧ ((∃k: n_k ∈ touched) ∨ (no statistic of any UE compared)) |
| CR-4 | (∀k: L_k = EQUAL) ⇒ R = PASS |

**Under MAP-UE FAIL**, no relation is asserted. R is reported as computed; the A2-8u rows are FAIL by the global rule.

**Intentional differences** (R and A2-8u disagree in strength, by design):

| Case | R (run-level, frozen) | A2-8u of the affected UE |
|---|---|---|
| statistics missing for one UE | PASS (others compared) | NE |
| one of the two statistics missing for UE k | PASS (the other compared) | NE |
| no ACKed lifecycle for UE k (`harqTxAttemptsDl` val `None`) | PASS (error rate compared) | NE |
| no feedback attributed to UE k | PASS (others compared) | NE |
| missing node mapping for UE k (in `run`: REFUSED by Run72; library: injected) | PASS on the mapped nodes | MAP-UE FAIL → FAIL |
| censored or pending group touching UE k | NE | NE; other UEs: local EQUAL reported, row NE (PU-4h NE) |
| non-finite Simu5G value | FAIL (comparison false) | FAIL (explicit `isfinite`): **same outcome** |

### 4.6 PU-4o UE k: per-UE H-ARQ occupancy, gate, one row per expected UE (C3)

**Local comparison for UE k:**

| Step | Condition | Local outcome |
|---|---|---|
| 1 | x7 is `None` (A2-7 NE without UE lines, or A2-7 FAIL with an invalid reference or a line-count mismatch) | NOT COMPARED ("no valid independent reference") |
| 2 | `n_k ∉ per` (no DL PDU for UE k) | NOT COMPARED ("no A-2.1 occupancy"; unexpected: every UE has a gPTP DL stream) |
| 3 | `per[n_k]["occupancy"]` is not a valid occupancy (not a dict, or it has an `error` key, e.g. "negative occupancy") | **DIFFERENT** ("A-2.1 occupancy invalid") |
| 4 | `n_k ∈ x7["skipped"]` | NOT COMPARED ("uncertain attribution: censored or pending group") |
| 5 | `n_k ∉ x7["occupancy_equal"]` | **DIFFERENT** ("no comparison entry for an unskipped node": inconsistent evidence; **a missing entry never passes**) |
| 6 | `x7["occupancy_equal"][n_k] is True` | **EQUAL** |
| 7 | anything else (False or a non-boolean) | **DIFFERENT** |

Steps 3 and 6 together guarantee a valid reference occupancy. The reference value `occ_x[n_k]` is compared with a valid A-2.1 occupancy, so equality implies validity: an `{"error": …}` reference cannot equal a valid occupancy.

**Row status PU-4o UE k:**

| Condition (in order) | Status |
|---|---|
| MAP-UE FAIL, or PU-4h FAIL (which includes A2-7 FAIL) | **FAIL** (global; the local outcome is reported) |
| local DIFFERENT | **FAIL** |
| local NOT COMPARED | **NE** (gating) |
| local EQUAL, and A2-7 not PASS or PU-4h not PASS | **NE** (global, e.g. A2-7 NE because another UE is touched, or A2-0s NE) |
| local EQUAL, A2-7 PASS, PU-4h PASS | **PASS** |

**Use.** The digest publishes the A-2.1 occupancy of UE k **only** where PU-4o UE k is PASS. Otherwise it is marked not available, never estimated (§5.3).

### 4.7 First-genuine-occurrence registry and flag (DR-07d, C4)

**Registry file** `m2s72_fgo_registry.json`:

```
{ "schema": "m2s72-fgo-registry/1",
  "features": [ { "name": <exact coverage() name>, "admitted": true|false,
                  "genuine": "explicit" | "inferred-only" | "not-exercised",
                  "evidence": [ { "record": <repo path>, "section": <§>, "contract": <contract>, "scope": <text>,
                                  "statement": <the record's own words> } ],
                  "strength": "E1" | "E2" | "I" | "N", "note": <text> } × 18 ] }
```

**Evidence strength:**

| Code | Meaning |
|---|---|
| E1 | The accepted record states a count or a row status for the feature, on genuine Simu5G output |
| E2 | The accepted record states an instance explicitly, without a count |
| I | Inferable by arithmetic from stated counts, but not stated. **Never sufficient for admission.** |
| N | The record states, or its counts imply, that the feature did not occur |

**Predictions and synthetic tests are never evidence.**

**Admission rule:** `admitted` iff `strength ∈ {E1, E2}` and each cited record is in `simulations/m2/results/` with a status of CLOSED ACCEPTED.

**Scope of the evidence:**
- F3 and S1 establish genuine coverage **only within their accepted scope**: one configuration, one seed, DL, two UEs, NACKs on ue[1] only; S1 under F1-d(i); F3 on a prefix.
- **Neither accepts A2-V1**, which stays NOT ACCEPTED. Citing them admits a feature as "not novel"; it does not accept any run.

**The 18 features** (exact names, in `coverage()` order):

| # | Feature (exact name) | Genuine exercise | Accepted record and contract | Strength | Initial registry |
|---|---|---|---|---|---|
| 1 | `single-candidate ACK attribution` | Almost certainly occurred (S1: 12 961 ACK lines, 742 exchangeable), but **no accepted record states the class count**. The N = 1 / N = 2 counts (11 697 / 12 194) are A-2 predictions (`-a2-implementation.md` §4, "(predicted)"), not records. | — | I | **excluded** |
| 2 | `exchangeable ACK groups (2 candidates)` | yes | S1 closure §3 (F1-d(i)): "371 certified exchangeable groups, with 742 exchangeable lines" and "Exchangeable lines are twice the groups: 2 × 371 = 742". Every group therefore has exactly 2 candidates. | E1 | **admitted** |
| 3 | `exchangeable groups of 3 or more` | no: 742 = 2 × 371 leaves none; S1 §5 "more than two UEs in a genuine run: not covered" | S1 closure §3, §5 | N | excluded (known, not exercised) |
| 4 | `NACK resolved: single candidate` | **unstated**: S1 gives 144 NACKs, 40 by retransmission evidence and 15 bound, but not the class of the rest | — | I | **excluded** |
| 5 | `NACK resolved: bound handle` | yes | S1 closure §3 (F1-d(i)): "15 by bound handles". Supported by F3 closure §2: "Handle 54326 is bound at 366 ms". | E1 | **admitted** |
| 6 | `NACK resolved by retransmission evidence (deferred)` | yes | S1 closure §3 (F1-d(i)): "40 lines resolved by retransmission evidence". F3 closure §2: "the NACK is `resolved-by-rtx`". | E1 | **admitted** |
| 7 | `multi-NACK groups (handle relations kept ambiguous)` | no | S1 closure §5: "multi-NACK groups … (ue[0] never NACKs, so no group holds two NACKs)" | N | excluded (known, not exercised) |
| 8 | `retransmissions` | yes | S1 closure §3: retransmissions 144 (on 129 PDUs); A2-4a PASS. F3 closure §1: transmissions at 361, 367, 373 and 379 ms. | E1 | **admitted** |
| 9 | `discard after maxHarqRtx + 1 transmissions` | no | S1 closure §3: "Discarded 0"; §5 | N | excluded (known, not exercised) |
| 10 | `mixed ACK / NACK groups` | yes, one instance stated | F3 closure §2 (prefix; `f1d-i` VALID): "A-2.1 resolves the mixed 366 ms group". S1 states no count. | E2 | **admitted** (scope: the stated instance; the prefix) |
| 11 | `end-of-run censoring: awaiting feedback` | yes | S1 closure §3: "Censored (awaiting feedback at the end) 5 / 1 / 6"; S-7: end states `{'censored: awaiting feedback': 6}` | E1 | **admitted** |
| 12 | `end-of-run censoring: inserted in the last TTI` | no | S1 closure S-7: the only end state is awaiting feedback | N | excluded (known, not exercised) |
| 13 | `end-of-run censoring: awaiting retransmission (structural)` | no | S1 closure §5: "structural censoring of a NACK … not evidenced" | N | excluded (known, not exercised) |
| 14 | `end-of-run censoring: awaiting resolution (structural)` | no | S1 closure §5: "… or of a pending group at the end of the log" | N | excluded (known, not exercised) |
| 15 | `per-UE occupancy confirmed by the independent reference` | yes | S1 closure §3: "XA (UE side, unchanged) agrees for both UEs, including per-UE occupancy"; A2-7 PASS | E1 | **admitted** |
| 16 | `independent UE-side reference (A2-7)` | yes | S1 closure §3: row table, A2-7 PASS. F3 closure §2: XA agreement. | E1 | **admitted** |
| 17 | `retransmission node identity from the UE side (A2-4b)` | yes | S1 closure §3: A2-4b PASS. F3 closure §2: "A2-4a and A2-4b are PASS". | E1 | **admitted** |
| 18 | `Simu5G per-UE statistics (A2-8)` | yes | S1 closure §4 (genuine whole-run scalars): "All four values are equal within … 1e-9" | E1 | **admitted** |

**Totals:**
- 10 admitted: #2, 5, 6, 8, 10, 11, 15, 16, 17 and 18.
- 2 excluded as inferred only: #1 and #4.
- 6 excluded as known but not exercised: #3, 7, 9, 12, 13 and 14.

**Consequence, stated plainly.** Until a maintainer-accepted record states the genuine count of `single-candidate ACK attribution`, every run in which it occurs is **HELD FOR REVIEW**. That is every realistic run.
- This is intended: the campaign is in any case blocked by S5-2-D2 until V-N1 and V-N2 are accepted.
- The `hrq` records of V-N1, V-N2 and V-V1 print the coverage counts explicitly. Their acceptance (VG-3) is the natural admission record for #1, and for #4 if V-V1 shows it.
- Admission is a separate, reviewed registry change citing those records. It is never part of an implementation commit and never derived from a test.

**FGO evaluation** (the coverage of the run against the registry):

| Situation | Outcome |
|---|---|
| a known feature with count > 0 and `admitted: false` | **HR**: "first genuine occurrence: <name> (<count>)" |
| a coverage name that is not among the 18 registry names (renamed or new feature) | **HR**: "unknown feature: <name>", a distinct reason |
| a registry name absent from the run's coverage output (schema drift) | **EVALUATION ERROR**, exit 2 |
| registry malformed: not exactly the 18 names, an admitted entry without E1 / E2 evidence, a citation outside `simulations/m2/results/`, or a cited record whose status is not CLOSED ACCEPTED | **EVALUATION ERROR**, exit 2 (checked at load) |
| A2-4c status PASS or FAIL (scheduler logging present; never genuine) | **HR**: "A2-4c exercised". A FAIL also fails PU-4h. |
| a known feature with count 0 | nothing (known, not exercised in this run) |

**Synthetic tests never extend the registry.**
- The suite tests the verdict logic twice: with the committed registry, asserting the real consequence, and with an in-memory test registry that is labelled "TEST ONLY" and never written.
- T-registry-immutable asserts that the committed file's sha256 is unchanged after the suite.

### 4.8 Composed per-run verdict

| Outcome | Condition | Exit |
|---|---|---|
| **REFUSED / EVALUATION ERROR** | name guard; `S5N_ADAPTER_VALIDATED` unset (`run`); records dir not fresh; node ids unavailable; registry invalid; missing s5n row; coverage schema drift; exception | 2 |
| **FAIL** `<rows>` | any gate FAIL | 1 |
| **INCOMPLETE** `<rows>` (+ held features, listed) | no gate FAIL; some gate NE | 4 |
| **HELD FOR REVIEW** `<features>` | no gate FAIL, no gate NE; FGO non-empty | 3 |
| **PASS** | every gate PASS (or NX where allowed); FGO empty | 0 |

**Precedence:** 2 > 1 > 4 > 3 > 0.
- An INCOMPLETE run is never shown as HELD FOR REVIEW. A review cannot make missing evidence acceptable.
- The held features are still listed.

**Gate set (`run`):**
- **s5n gates, with the identical s5n predicate (§1.1 step 6), minus PU-4 only:**
  - FAIL rows not in `E.INFO`;
  - NE rows whose id starts with `PU-` or `AV-`;
  - an NE row outside PU / AV stays non-gating, exactly as in s5n.
- **plus** MAP-UE, C-0, PU-4h, PU-4o UE k for every k < N, and A2-8u UE k for every k < N: FAIL and NE both gate.

**Reported, never gating:**
- PU-4 (A-1), verbatim;
- the A-2.1 `full` verdict;
- the run-level A2-8 row (it gates only through PU-4h);
- the agreement diagnostic.

### 4.9 Preservation of the s5n gate semantics; required s5n rows (C6)

- `gate_fail21 = s5n.gate_fail − {"PU-4"}` and `ne21 = s5n.ne − {"PU-4"}`, computed from `s5n_rows` with the **same expressions** as `check_m2s72_s5n.py:140-141`. Nothing else is removed, added or re-scoped.
- T-s5n-semantics checks this on every synthetic s5n row set, including a non-PU NE row (Q8-v NE), which must stay non-gating.
- **Required s5n rows:**
  - PU-1 ×1, PU-2 ×N, PU-3 ×N, PU-4 ×1, PU-5 ×1, AV-1 ×N, AV-2 ×N, AV-3 ×N;
  - Q8-v, SG-403, MG-1, EOR and F0-1 (info), each ≥ 1;
  - the Block B / I-2H row ids that s5n emits at N. Their declared list is taken at implementation from the accepted checkers and is pinned in T-s5n-rowset.
- If any is missing from `s5n_rows`, the result is **EVALUATION ERROR** (exit 2), naming the missing rows. A row is never silently dropped.
- The row set must also equal the rows written to `s5n/<cfg>.check.txt`, and their count must equal the s5n digest's `correctness.rows`.
- **PU-5** stays a gate (D-A1-5). It sums grant bytes and insert lines, which name their node, so it is independent of feedback attribution.

### 4.10 PU-4 (A-1): historical report, never a gate; agreement diagnostic (D-A1-10)

- The s5n PU-4 row is copied **verbatim**, status and detail, under the label `PU-4 (A-1, historical rule; reported, not a gate — DR-07b)`.
- The s5n digest's `harq_attribution` (the A-1 summary) is reported unchanged, under `historical` (§5.3).
- A PU-4 FAIL is printed as FAIL. It is never printed as PASS, NA or "superseded", and it never changes the composed verdict.
- The unchanged s5n verdict line is kept in `s5n/<cfg>.check.txt` and quoted in the new record.
- **Agreement diagnostic** (report only):
  - for each feedback line A-1 attributed (via `trace` of the frozen `attribute_feedback`), compare its node with A-2.1's owner at the same canonical index (C-0 guarantees that the indices align);
  - report agree, disagree, and A-1-unattributed lines by their A-2.1 class.

### 4.11 Missing, malformed and ambiguous evidence

| Situation | Handling |
|---|---|
| no `run-<cfg>.log.gz` | s5n: PU-4 / PU-5 NE (unchanged). Wrapper: A-2.1 not evaluable → **EVALUATION ERROR** (exit 2): there is nothing to replay. |
| log without UE-side H-ARQ lines | A2-7 NE (x7 `None`) → F1-d(i) INCOMPLETE → PU-4h NE; PU-4o NE (all UEs) → **INCOMPLETE** |
| no `.sca` / no `macNodeId` records | `run`: Run72 fails → **REFUSED** (exit 2). `hrq-fixture`: A2-8u NE (all UEs) → **INCOMPLETE** |
| `.sca` without H-ARQ scalars, or a UE's scalars partly missing or unparsable | A2-8u NE for that UE → **INCOMPLETE** (run-level A2-8 reported as computed; it may be PASS, CR-2) |
| `$SIMU5G_ROOT` unset or not 1.8.1 | A2-0s NE / FAIL → PU-4h NE / FAIL |
| UE-to-node mapping inconsistent | MAP-UE FAIL → PU-4h, PU-4o and A2-8u FAIL → **FAIL** |
| UNCLASSIFIED or malformed MAC-log line, or a line one parser reads and the other does not | MG-1 FAIL (unchanged) and / or A2-0 / A2-1 FAIL; C-0 FAIL → **FAIL** |
| exchangeable group | resolved as a certified multiset (A2-5); PU-4h PASS allowed |
| a line XA cannot separate but A-2.1 resolved | checked as a group multiset (A-2.1 rule, unchanged) |
| group-level censoring (uncertain) | §4.2: A2-7 NE → PU-4h NE → **INCOMPLETE** |
| unit-level censoring (attributable) | §4.2: unaffected rows; FGO governs novelty |
| configuration name not plain E0v-N | `run` **REFUSED** (§5.2) |

### 4.12 Backward compatibility (N = 1)

- **N = 1 configurations** (`M2S72-E0v-…`): `check_m2s72_s5v.py` stays their evaluator, unchanged. `run` refuses N = 1 names, as `s5n` does.
- **`M2S72-E0vN-…-n1-…`** (an E0v-N bracket at N = 1): `run` evaluates it. At N = 1, A-1 is exact by construction (one candidate per process).
- **`hrq`** accepts exactly one N = 1 name, `M2S72-E0v-q0-f1`, for V-N1. It evaluates only the H-ARQ rows; s5n is not run.

---

## 5. Input / output contract

### 5.1 Commands

Every command runs as `python3 -I -B <absolute path>/check_m2s72_s5n21.py …`. The script inserts its own directory into `sys.path` before any local import (§1.6), so it works under `-I` from any working directory.

```
check_m2s72_s5n21.py run         <runs> <cfg> <records dir> [--t0 <s>]
check_m2s72_s5n21.py hrq         <runs> <cfg> <records dir> [--t0 <s>] [--expect <expectation file>]
check_m2s72_s5n21.py hrq-fixture <fixture dir> <records dir> [--expect <expectation file>]
check_m2s72_s5n21.py controls    <runs> <cfg> <records dir> [--t0 <s>]
```

| Mode | Purpose |
|---|---|
| `run` | The E0v-N per-run evaluation (§3.3, §4.8). Requires a non-empty `S5N_ADAPTER_VALIDATED`; the unchanged `run_one` also enforces it. |
| `hrq` | H-ARQ rows only: A-1 report, one A-2.1 replay (both contracts), MAP-UE, C-0, PU-4h, PU-4o, A2-8u, agreement, FGO. It does not run s5n and does not read `S5N_ADAPTER_VALIDATED`. Names accepted: the §5.2 guard, plus `M2S72-E0v-q0-f1` (V-N1), plus `M2S72-E0vN-q0-one0-n2-f1_A2V1` (V-V1). |
| `hrq-fixture` | The F3 fixture interface (T-f3-hrq), below. The name guard is not applied: the fixture's own `cfg` is the A2-V1 name. The record is labelled "fixture (prefix of the sealed A2-V1 run); not an E0v-N run; not an A2-V1 acceptance". |
| `controls` | The negative controls of §7.3 that need a real run, in memory (the raw files are only read), with the baseline guard of `check_m2s72_a21.py`: a control counts only if its rows were PASS before the mutation. |

**`hrq-fixture` input interface (explicit):**
- `m2s72_a21_realchain.load_fixture(<fixture dir>)` (accepted, unchanged) refuses unless:
  - the directory holds `a2v1-first-chain.log.gz`, its `.sha256` pin and `a2v1-first-chain.meta.json`;
  - the pin reads `<sha256>  a2v1-first-chain.log.gz`;
  - sha256(log) equals the pin **and** the metadata's `fixture_sha256`.
- Refusal → exit 2.
- From the loaded fixture:

| Input | Source |
|---|---|
| lines | `fx["lines21"]` |
| node map | `fx["node"]` = `{int(k): int(v)}` of `meta["node_ids"]` (`{0: 2049, 1: 2050}`) |
| N | `len(fx["node"])` (2) |
| nproc | `fx["nproc"]` (16) |
| grants | `fx["grants"]` |
| t0 | 0 (the whole prefix, as `m2s72_a21_realchain`) |
| `.sca` | none |
| `SIMU5G_ROOT` | required, as in `m2s72_a21_realchain`: unset → exit 2 |

- C-0 reads the A-1 events from `fx["path"]` with `harq_events`.
- The record states the fixture sha256 `cfb05ff7…` and the metadata `cfg`.

**Exit codes.**
- **Without `--expect`:** the verdict code of §4.8 (0, 1, 2, 3 or 4).
- **With `--expect`:**
  - 0 iff **every** declared expectation, including the declared verdict, equals the evaluated value;
  - **5** if any expectation differs (EXPECTATION MISMATCH; the comparison table lists each mismatch);
  - 2 if the expectation file is malformed, names an unknown key, or the evaluation itself errs.
  - An expectation mismatch is never exit 0.

**Common rules:**
- **Inputs:**
  - `<runs>/run-<cfg>.log.gz`;
  - `<runs>/<cfg>/<cfg>/0.sca`;
  - the run's vector / scalar files for `Run72`;
  - `$SIMU5G_ROOT` (Simu5G 1.8.1 tree, for A2-0s).
- **Outputs:**
  - `<records dir>` must not exist; it is created. An existing directory → exit 2.
  - Files are written with `fsync` (`m2s72s5_lib.durable`).
- **Never written:** the raw files, the registry, the fixture.

**Output files:**

| Mode | Files |
|---|---|
| `run` | `s5n/<cfg>.check.txt` and `s5n/<cfg>.digest.json` (unchanged s5n); `a21-<cfg>.txt` and `a21-<cfg>.json` (one replay, both contract verdicts); `<cfg>.s5n21.txt`; `<cfg>.s5n21.json`; `<cfg>.s5n21.digest.json` |
| `hrq` | `a21-<cfg>.txt/.json`; `hrq-<cfg>.txt`; `hrq-<cfg>.json`; with `--expect`, `hrq-<cfg>.expect.txt` |
| `hrq-fixture` | the same, with `<cfg>` = `f3-fixture` |

### 5.2 Name guard (D-A1-8)

The guard is a wrapper-local regex. `check_m2s72_s5v.parse_name` is accepted code and is not modified.

```
^M2S72-E0vN(H5)?-(q0|q0p|qdu|qde)-(one0|sym)-n(1|2|4|8)-f(0p5|0p8|1|1p25|1p6|2)$
```

**Confirmed against every generated campaign configuration** (§1.6):
- it accepts exactly the 294 E0v-N configurations of `m2s72s5.ini`;
- it accepts no other name;
- it agrees with `parse_name` kind `E0vN` on all 459 names.

The regex admits 384 syntactic combinations, of which 294 are generated. A name that is not generated cannot be run, because OMNeT++ has no such configuration. T-name-guard re-derives the 294 from `m2s72s5.ini` at test time, so a generator change is detected.

`run` refuses everything else with exit 2, including `…-f1_A2V1` and the four `M2S72-E0vNL-q0-f*` N = 1 twins.

### 5.3 Composed digest `<cfg>.s5n21.digest.json`: field ownership (C5)

**The original s5n digest `s5n/<cfg>.digest.json` is preserved unchanged**: byte-identical to a standalone `check_m2s72_s5n.py run` (T-s5n-transparent). The composed digest is a **new** file with `"schema": "m2s72-s5n21-digest/1"`.

| Field | Owner | Content and rule |
|---|---|---|
| `schema` | wrapper | `m2s72-s5n21-digest/1` |
| `config`, `kind`, `option`, `placement`, `numUe`, `harq16`, `dl_factor` | s5n | copied verbatim from the s5n digest |
| `correctness.verdict` | wrapper | `{status, exit, gate_failures, gate_not_evaluated, held_features}` (§4.8) |
| `correctness.rows` | wrapper | every wrapper row: MAP-UE, C-0, PU-4h, PU-4o UE k (local + status), A2-8u UE k (local + status) |
| `correctness.s5n` | s5n | `{verdict_line, gate_failures, per_ue_not_evaluated, rows}` copied verbatim |
| `correctness.a21` | A-2.1 | `{rows (verbatim, incl. run-level A2-8), verdict_f1d_i, verdict_full, coverage}`, one replay |
| `performance.per_ue[k]` minus `harq` | s5n (adapter; **A-1-independent**) | every field of `P.per_ue(o)` except `harq`, copied verbatim: DL / UL rates and ratios, backlog, MAC grant fields (grant lines name their node), gPTP fates and deadlines, clock, `starvation`, `overloaded`. None of these reads A-1 (`m2s72_peru.py:201-280`). |
| `performance.per_ue[k].harq_a21` | **A-2.1** (current) | from `per[n_k]` of the single replay, each group with `{"available": bool, "reason": …}`:<br>• **counts** (inserts, transmissions, retransmissions, feedback, ack, nack, discarded, `transmissions_per_acked_pdu`, `harq_latency_ps`, `feedback_age_ps`, `end_states`, `lines_by_class`; derived `harq_error_rate` = nack / feedback and `harq_tx_attempts` = mean ntx of ACKed units): available iff PU-4h PASS and n_k ∉ touched;<br>• **occupancy**: available iff PU-4o UE k PASS;<br>• **Simu5G cross-check**: the A2-8u UE k status.<br>An unavailable group carries **no value**: never 0, never the A-1 value. |
| `performance.across` | s5n | `P.across(ms)` copied verbatim. Its keys (service ratios, gPTP, residence, lag, clock, MAC not-granted share, Jain, starvation and overload classes, system rates) read no A-1 field. |
| `performance.across_harq_a21` | **A-2.1** (current) | per metric (`harq_error_rate`, `harq_tx_attempts`, retransmissions, the occupancy mean): `{min, max, spread, worst_ue, n}`, computed **only if every expected UE's value is available**. Otherwise `{"available": false, "missing_ues": [...]}`. No partial aggregate is computed over a subset; unlike `P.across`, which reports `n`, the A-2.1 aggregates are all-or-nothing. Sums of counts likewise. |
| `performance.totals` | s5n | copied verbatim (`dl_grant_bytes`, `harq_inserts`: node-identified lines, A-1-independent) |
| `historical.a1` | s5n / A-1 (**historical, not current**) | `{pu4_row (verbatim), harq_attribution (verbatim A-1 summary), per_ue_harq: {k: s5n per_ue[k].harq verbatim}}`, labelled "A-1, historical rule; not a current measurement (DR-07b)" |
| `diagnostics.agreement` | wrapper | §4.10, labelled diagnostic |
| `mac_grammar_census` | s5n | copied verbatim |
| `inputs` | wrapper | sha256 of the log, the `.sca` and the registry; blob ids of `m2s72_a21.py`, `check_m2s72_a21.py`, `check_m2s72_s5n.py` and the wrapper files; the C-0 sequence digests; `S5N_ADAPTER_VALIDATED` verbatim |

**A-1-derived values appear only under `historical`.** T-digest-ownership asserts the following:
- no key outside `historical` holds an A-1-derived value. Mutating the A-1 summary or the s5n `per_ue[k].harq` changes only `historical.*`.
- `performance.per_ue[k]` has no `harq` key.

### 5.4 Batch-runner integration boundary (A3; not implemented here)

**WP-A1 does not modify `m2s72s5.sh`.** The runner has no E0v-N batch mode (L-14). WP-A3 adds it, against this interface:

| Item | Contract |
|---|---|
| Invocation | `python3 -I -B "$CHK/check_m2s72_s5n21.py" run "$OUT/runs" "$cfg" "$REC/$cfg"`, one process per run (L-11) |
| Exit codes | 0 PASS; 1 FAIL; 2 REFUSED / EVALUATION ERROR; 3 HELD FOR REVIEW; 4 INCOMPLETE |
| Batch rule | Only rc 0 lets the batch continue. Every other rc stops it, with the run's raw outputs kept (tier B), as `s5_full` does today for any non-zero rc.<br>• **rc 3 stops the batch** (D-A1-7).<br>• The run's ledger reason is "held for review: <features>". |
| Records | the files of §5.1 under `$REC/$cfg/`. The runner makes each file durable and lists them in the run's manifest record. |
| S5-2-D2 | The wrapper refuses `run` (exit 2) unless `S5N_ADAPTER_VALIDATED` is non-empty, and the unchanged `run_one` refuses as well. The wrapper records the value verbatim in `inputs`.<br>• **No WP-A1 file sets the variable**; T-no-d2-bypass greps the new files.<br>• A3 must take the value from the maintainer's S5-2-D2 decision record, not from the smoke-n2 diagnostic text (`m2s72s5.sh:320`).<br>• A3's own review must check that no other mode sets it. |
| Checker selection | A3 selects the wrapper through a new, explicit variable. It must not use `S5_TEST_CHECKER`, which is a test hook (`m2s72s5.sh:35`). |

### 5.5 Interface for the A5 comparators (not implemented here)

| Rule | Content |
|---|---|
| Input | `<cfg>.s5n21.digest.json` with `schema == "m2s72-s5n21-digest/1"`; any other schema → refuse |
| Run eligibility | only runs with `correctness.verdict.status == "PASS"` contribute. HELD, INCOMPLETE and FAIL runs are listed as excluded, with their reasons. |
| Per-UE H-ARQ values | only from `performance.per_ue[k].harq_a21`, and only where `available` is true. An unavailable value is **missing**, never 0. |
| Across-UE | `performance.across` as s5n defines it; `performance.across_harq_a21` only where `available` |
| Forbidden | reading `historical.*` or `diagnostics.*` as a measurement |
| Provenance | every comparison cites the digest file's sha256 and `inputs` |

---

## 6. Module boundary and preservation guarantees

| Guarantee | Enforcement |
|---|---|
| Frozen A-2 / XA / A-1 files byte-identical to `fbee202`; the A2-V1 evaluator to `39a6434` | the existing T-frozen-untouched; plus T-a1-frozen in the new suite (same lists) |
| Accepted A-2.1 files byte-identical to `d920125` | T-a1-a21-pinned (`git diff --quiet d920125 -- <5 files>`) |
| s5n / adapter / s5v / s5n2 / lib byte-identical to the baseline `7bb0e3a`; `m2s72s5.sh`, `.ini` files and workflows unchanged | T-a1-s5n-pinned (`git diff --quiet 7bb0e3a -- <files>`) |
| The s5n records produced inside `run` are identical to a standalone `check_m2s72_s5n.py run` | T-s5n-transparent (stubbed evaluation; byte comparison of `check.txt` and `digest.json`) |
| s5n gate semantics identical except PU-4 | T-s5n-semantics, T-s5n-rowset |
| Historical PU-4 never relabelled | T-pu4-verbatim, NC-pu4-relabel |
| One replay per evaluation | T-single-replay |
| All ten tier-0 suites keep their exact expected lines | tier-0 itself (unchanged workflow) |

---

## 7. Test matrix (`test_m2s72_e0vn21.py`; synthetic unless stated)

**Truth sources:**
- the corrected generator `m2s72_harqfix21.make(n_ue, ttis, sched, nack, d_ue, nproc, …)` → `(lines, node, truth)`, labelled synthetic;
- the frozen `m2s72_harqfix` for ACK-only identity cases;
- synthetic `.sca` files built from the generator truth.

**Registry used:**
- unless stated, the **committed** registry, so the real consequence is asserted: on any input with single-candidate ACK lines, the composed result is at best HELD FOR REVIEW.
- Where a test must reach PASS, it also runs with the in-memory **TEST ONLY** registry (all 18 admitted), and says so.

Every test states its inputs, its expected outputs, and the defect its failure detects.

### 7.1 Positive and structural tests

| ID | Input | Expected | Detects |
|---|---|---|---|
| T-n2-same-tti | N = 2, both UEs scheduled every TTI on the same process (ACK only), UE lines, `.sca` | • A-1: ambiguous > 0, re-insert > 0; **PU-4 FAIL reported verbatim**.<br>• A-2.1 `f1d-i` and `full` VALID (A2-4a/b/c NX); exchangeable groups = same-TTI pairs.<br>• MAP-UE, C-0, PU-4h PASS; PU-4o PASS ×2 (occupancy = truth); A2-8u PASS ×2.<br>• Committed registry: **HELD FOR REVIEW** {single-candidate ACK attribution}.<br>• TEST ONLY registry: PASS. | A-1 limitation masking; PU-4 still gating |
| T-n3-groups | N = 3, three UEs on one process in one TTI | exchangeable groups of 3 (certified); PU-4h PASS; held ⊇ {"exchangeable groups of 3 or more"} → HR (also with the TEST ONLY registry minus that feature) | synthetic-only path silently accepted |
| T-n4-independent | N = 4, NACK chains on UEs 1 and 3 (different processes), ACK on 0 and 2 | per-UE counts / occupancy = truth for each UE; PU-4o PASS ×4; A2-8u PASS ×4 | cross-UE leakage of counts |
| T-n4-overlap-nack | N = 4, a NACK on UE 2 in a TTI where UEs 0 and 2 share the process (mixed group) | resolved by retransmission evidence; PU-4h PASS; per-UE = truth; "mixed ACK / NACK groups" not held (admitted) | mixed-group regressions |
| T-n2-a2v1-like | N = 2, NACKs on UE 1 only (the A2-V1 pattern) | per-UE = truth; `full` INCOMPLETE (retransmissions, no scheduler lines) and `f1d-i` VALID, **from the same rows**; PU-4h PASS | wrong contract gating |
| T-multinack | N = 2, both UEs NACK the same process in the same TTI | counts exact as a multiset; held ⊇ {"multi-NACK groups …"} → HR | DR-07d bypass |
| T-discard | N = 2, a PDU NACKed maxHarqRtx + 1 times | held ⊇ {"discard after …"} → HR; per-UE discarded = truth | DR-07d bypass |
| T-censor-awaiting-feedback | ACK-only log cut so that units await feedback at the end | `touched_nodes` = ∅; A2-7 PASS; PU-4h, PU-4o and A2-8u unaffected (PASS); "awaiting feedback" admitted → not held | attributable censoring wrongly blocking |
| T-censor-structural-unit | log cut after a NACK with no complete main loop after it ("awaiting retransmission") | `touched_nodes` = ∅; rows unaffected; held ⊇ {"…awaiting retransmission (structural)"} → HR | unit-level censoring misclassified |
| T-censor-group | log ending inside a pending group with a structural cut ("awaiting resolution") | `touched_nodes` = the candidates; A2-7 **NE**; `f1d-i` INCOMPLETE; PU-4h **NE**; the touched UE: PU-4o / A2-8u NE (local NOT COMPARED); the other UE: local EQUAL reported, row NE (global); composed **INCOMPLETE** (exit 4), never HR or PASS, even with the TEST ONLY registry | uncertainty NE made non-gating (C2) |
| T-censor-pending-unresolved | as above, but a complete main loop follows (not structural) | A2-7 NE and A2-9 NE; PU-4h NE → **INCOMPLETE** | the same |
| T-unresolved | NACK followed by a main loop but no retransmission | A2-9 NE → PU-4h NE → **INCOMPLETE** | unresolved evidence passing |
| T-n1-identity | N = 1 ACK only (frozen generator), `.sca` present; **(a)** with UE lines, **(b)** without | A-1 PU-4 PASS; A-2.1 per-UE counts = A-1's.<br>**(a)** A2-7 PASS → `f1d-i` VALID → PU-4h PASS; PU-4o PASS with occupancy = A-1's = truth; A2-8u PASS; committed registry → HR {single-candidate ACK}.<br>**(b)** A2-7 NE → `f1d-i` **INCOMPLETE** → **PU-4h NE**; PU-4o NE (local NOT COMPARED: no reference); A2-8u NE (global; local EQUAL reported); composed **INCOMPLETE** | N = 1 behaviour change; absence read as pass |
| T-a28-compat | per case: run-level R (the accepted `scalar_row`) and L_k / A2-8u UE k:<br>(1) all equal;<br>(2) the scalars of one UE missing;<br>(3) one of the two statistics missing for UE 1;<br>(4) no ACKed lifecycle for UE 1;<br>(5) no feedback for UE 1;<br>(6) missing node mapping for UE 1 (injected map);<br>(7) a `nan` and an `inf` value for UE 1;<br>(8) an unparsable value for UE 1;<br>(9) a group-censored UE 1;<br>(10) a value mismatch on UE 1 | (1) R PASS, A2-8u PASS ×2.<br>(2)(3)(4)(5)(8) R PASS, UE 1 NE: **intentional difference**.<br>(6) R PASS, MAP-UE FAIL → A2-8u FAIL ×2.<br>(7) R FAIL, UE 1 FAIL (same outcome; explicit `isfinite`).<br>(9) R NE, UE 1 NE, UE 0 local EQUAL / row NE.<br>(10) R FAIL, UE 1 FAIL, UE 0 local EQUAL / row FAIL (global: PU-4h FAIL through NOT VALID).<br>**CR-1 … CR-4 hold in every case with MAP-UE PASS.**<br>The tolerance formula is the quoted `abs(rec - val) <= REL_TOL * max(1.0, abs(val))`; boundary cases at ±(1 ± 1e-3)·tolerance. | per-UE A2-8 weaker than declared, or a false exact invariant (C1) |
| T-map | N = 2: (a) a duplicate node id; (b) an extra `ue[2]` module in `.sca`; (c) a `.sca` id differing from `node_id`; (d) a PDU for an unmapped node; (e) `node_id` `None` in the CLI | (a)–(d) MAP-UE FAIL → PU-4h, PU-4o and A2-8u FAIL; (e) REFUSED (exit 2) | wrong or partial UE identity (C3) |
| T-c0 | the inputs above | C-0 PASS; the two canonical sequences are equal; their digests are recorded | parser divergence undetected |
| T-agree | T-n2-same-tti, T-n2-a2v1-like | ACK-only: disagree = 0; NACK input: disagreements reported by class; the verdict is identical with and without the diagnostic | the diagnostic changing a verdict |
| T-name-guard | every `[Config …]` of `m2s72s5.ini`; `…_A2V1`; `M2S72-E0v-q0-f1`; the four `E0vNL`; malformed names | exactly the 294 E0v-N accepted by `run`, equal to `parse_name` kind `E0vN`; the others REFUSED; `hrq` additionally accepts exactly `M2S72-E0v-q0-f1` and `M2S72-E0vN-q0-one0-n2-f1_A2V1` | L-7 |
| T-s5n-semantics | synthetic s5n row sets: a PU-4 FAIL; a PU-4 NE; a Q8-v NE; an F0-1 (info) FAIL; an AV-2 NE; a Block B FAIL | gate sets = s5n's minus PU-4 exactly (Q8-v NE non-gating, F0-1 (info) non-gating, AV-2 NE gating, Block B FAIL gating) | s5n semantics silently changed |
| T-s5n-rowset | an s5n row set with PU-3 of UE 1 removed; one with MG-1 removed | EVALUATION ERROR (exit 2) naming the row; never PASS | historical rows dropped |
| T-single-replay | `run` and `hrq` on synthetic runs | `m2s72_a21.replay` called exactly once; both contract verdicts present and equal to `verdict(rows, c)` | duplicate evaluation (D-A1-9) |
| T-a21-record-equiv | synthetic run, both contracts | the wrapper's a21 rows / coverage / per-UE sections equal those of `check_m2s72_a21.a21()` for each contract | record drift from the accepted writer |
| T-digest-ownership | synthetic N = 2 run | §5.3: no A-1 value outside `historical`; `per_ue[k]` has no `harq`; an unavailable `harq_a21` group has no value; `across_harq_a21` is unavailable with `missing_ues` when one UE is unavailable; the s5n digest is byte-identical | A-1 values exposed as current (C5) |
| T-one-run-per-process | two evaluations in one Python process | the second refused (exit 2) | L-11 row mixing |
| T-registry | the committed registry | exactly 18 names, equal to the names `coverage()` returns; the admitted set is exactly {#2, 5, 6, 8, 10, 11, 15, 16, 17, 18}; every admitted citation exists and is CLOSED ACCEPTED; no citation to a test, fixture generator or prediction | registry drift (C4) |
| T-registry-immutable | the whole suite | registry sha256 unchanged afterwards | tests extending the registry |
| T-imports-isolated | `subprocess.run([sys.executable, "-I", "-B", <abs path>, "--help"], cwd=<temp dir>)` for the CLI and the suite | the import succeeds (rc 2 with usage, no `ModuleNotFoundError`) | a command that cannot import under `-I` (C6) |
| T-expect-exit | `hrq` with a matching expectation file, a mismatching one (one count changed), and a malformed one | exits 0 / **5** / 2 | expectation mismatch exiting 0 (C6) |
| T-no-d2-bypass | grep the new files | no assignment of `S5N_ADAPTER_VALIDATED` | S5-2-D2 bypass |
| T-schema | every case | every §5.3 field; statuses only from §4.0 | schema drift |

### 7.2 Genuine F3 fixture through the wrapper (genuine input; `hrq-fixture`)

| ID | Input | Expected (`check/expect/f3.expect.json`, committed before implementation runs it) | Detects |
|---|---|---|---|
| T-f3-hrq | `hrq-fixture simulations/m2/check/fixtures <fresh dir> --expect check/expect/f3.expect.json`, `SIMU5G_ROOT` = the tier-0 Simu5G 1.8.1 checkout | • A-2.1 rows = those of `m2s72_a21_realchain` (R-1 … R-10): A2-0s PASS (root set); A2-4a/b PASS; A2-4c NE; A2-8 NE; all others PASS.<br>• `f1d-i` VALID, `full` INCOMPLETE (same rows).<br>• MAP-UE PASS (nodes {0: 2049, 1: 2050}); C-0 PASS; PU-4h PASS.<br>• PU-4o PASS ×2 (`occupancy_equal` {2049: True, 2050: True}).<br>• A2-8u NE ×2 (no `.sca`; local NOT COMPARED).<br>• Coverage counts as observed in §1.6:<br>  – single ACK 83; exchangeable (2) 5; bound 2; resolved-by-rtx 1;<br>  – retransmissions 3; mixed 3; awaiting feedback 6;<br>  – occupancy 2; A2-7 1; A2-4b 1; others 0.<br>• Held = {single-candidate ACK attribution}.<br>• Composed **INCOMPLETE** (exit 4; A2-8u NE takes precedence over HR).<br>• With `--expect`: exit 0. | the wrapper diverging from the accepted F3 validation |
| T-f3-a1 | the same fixture | the A-1 report equals a direct call of the frozen `attribute_feedback` on `harq_events(fixture)`: no hard-coded number (A-1 on this NACK chain is not an accepted quantity) | the A-1 report being altered |

### 7.3 Negative controls (baseline guard: the declared rows PASS before the mutation, otherwise NOT BUILDABLE)

| ID | Mutation | Expected | Detects |
|---|---|---|---|
| NC-swap | one PDU's gNB insert line relabelled to the other UE's node (N = 2) | A2-7 FAIL → PU-4h FAIL; PU-4o FAIL for **both** UEs: the affected UE local DIFFERENT or NOT COMPARED, the other by the global rule; the detail names the PDU | cross-UE misattribution invisible to sums |
| NC-ue-relabel | one UE-side RX line moved to the other UE's module | A2-7 FAIL (reference invalid, x7 `None`) → PU-4h FAIL; PU-4o local NOT COMPARED, row FAIL (global) | a corrupted reference passing |
| NC-occ-one-ue | UE 0's insert removed and its feedback kept (N = 2) | A-2.1 NOT VALID (A2-1 / A2-2 / A2-6 FAIL) → PU-4h FAIL.<br>• PU-4o UE 0: FAIL.<br>• **PU-4o UE 1: local outcome reported as computed (not asserted equal to the baseline), row status FAIL by the global rule; the detail attributes the FAIL to PU-4h, not to a UE 1 mismatch.**<br>• A2-8u: FAIL ×2 (global).<br>• Composed FAIL. | contamination concealed, or a local result misreported (C3) |
| NC-scalar-ue1 | `.sca` `harqErrorRateDl:mean` of UE 1 perturbed beyond tolerance | run-level A2-8 FAIL → A-2.1 NOT VALID → PU-4h FAIL; A2-8u UE 1 local DIFFERENT → FAIL; UE 0 local EQUAL, row FAIL (global); CR-1 holds | per-UE isolation of A2-8; correct global propagation |
| NC-scalar-missing-ue1 | UE 1's two statistics removed from `.sca` | run-level A2-8 **PASS** (UE 0 compared; frozen behaviour); A2-8u UE 1 NE → composed INCOMPLETE | the run-level PASS read as per-UE coverage (C1) |
| NC-occ-entry-missing | in memory: `x7["occupancy_equal"]` without UE 1's key, UE 1 not skipped | PU-4o UE 1 local DIFFERENT → FAIL; never PASS | a missing entry reaching PASS (C3) |
| NC-occ-invalid | in memory: `per[n_1]["occupancy"] = {"error": "negative occupancy"}` and the reference equally an error | PU-4o UE 1 FAIL (step 3), although `occupancy_equal` would be True | invalid data passing by equality |
| NC-c0-same-count | in memory: the process ids of two A-1 feedback events exchanged (counts and kinds unchanged) | C-0 FAIL at the first changed index → PU-4h FAIL | a totals-only consistency check (C6) |
| NC-c0-reorder | in memory: two adjacent A-1 events of different UEs swapped | C-0 FAIL → PU-4h FAIL | order-insensitive consistency |
| NC-c0-node | in memory: one A-1 insert event's node changed | C-0 FAIL | identity-insensitive consistency |
| NC-dropfb | one feedback event removed from the log | A2-1 or A2-2 FAIL → PU-4h FAIL | lost evidence |
| NC-dupins | one insert duplicated | A2-2 / A2-6 FAIL and C-0 FAIL; A-1 re-insert + 1 (reported) | duplicated evidence |
| NC-shift | one feedback one TTI late | A2-3 FAIL → PU-4h FAIL | timing corruption |
| NC-node-map | node-id map permuted | MAP-UE FAIL, or A2-4b / A2-7 FAIL | wrong UE identity |
| NC-no-ue-lines | all UE-side lines removed | PU-4h NE, PU-4o NE → INCOMPLETE, never PASS | absence read as pass |
| NC-registry | a registry feature's `admitted` flipped to false (in memory) | that feature is now held → HR | FGO fail-open |
| NC-registry-unknown | a coverage name unknown to the registry injected | HR with reason "unknown feature" | renamed features passing |
| NC-registry-missing | a registry name removed from the coverage output | EVALUATION ERROR (exit 2) | coverage drift |
| NC-registry-uncited | an entry `admitted: true` with strength I | EVALUATION ERROR at load | admission without evidence |
| NC-pu4-relabel | the wrapper's copy of PU-4 compared with s5n's row | byte-equal status and detail; a PU-4 FAIL never appears as PASS / NA in any output | historical result concealed |
| NC-name | `run` on `…-f1_A2V1` and on `M2S72-E0vNL-q0-f1` | REFUSED (exit 2) | L-7 |
| NC-full-masquerade | retransmissions, no scheduler lines | `full` reported INCOMPLETE; PU-4h uses `f1d-i` only; the record labels each contract | contract confusion |

### 7.4 Regression protection

| ID | Check |
|---|---|
| T-a1-frozen | frozen files byte-identical (`fbee202`, `39a6434`) |
| T-a1-a21-pinned | accepted A-2.1 files byte-identical to `d920125` |
| T-a1-s5n-pinned | `check_m2s72_s5n.py`, `m2s72_peru_adapter.py`, `check_m2s72_s5v.py`, `check_m2s72_s5n2.py`, `m2s72s5_lib.py`, `m2s72s5.sh` byte-identical to `7bb0e3a` |
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

**Path resolution:** DR-13 method 1, a read-only mount of the extraction at the original absolute prefix `$R`. The method is recorded in each record.

**Read-only evaluations; nothing is simulated.** The expectation files are committed **before** execution (§3.2). Every Python command uses `-I -B` and an absolute script path (§1.6, T-imports-isolated).

### 8.1 Common steps (each validation)

```bash
# --- variables (all set before P-0; none is guessed) ----------------------------------------------------------
W=<independent clean worktree of the reviewed implementation commit>
C=<the reviewed implementation commit (40 hex)>
R=<the original results prefix, mounted read-only (DR-13 method 1)>
E=<a fresh evidence directory; must not exist>
export SIMU5G_ROOT=<unmodified Simu5G 1.8.1 tree; HEAD 7477d2663644bbf78604267cba4fc113b4871ede>
CHK="$W/simulations/m2/check"
PY="python3 -I -B"

# --- P-0 code identity and suites ------------------------------------------------------------------------------
test "$(git -C "$W" rev-parse HEAD)" = "$C" && echo "P-0 commit OK"
test "$(git -C "$SIMU5G_ROOT" rev-parse HEAD)" = 7477d2663644bbf78604267cba4fc113b4871ede && echo "P-0 Simu5G OK"
test ! -e "$E" && mkdir "$E" && echo "P-0 fresh evidence dir"
$PY "$CHK/test_m2s72_e0vn21.py"; echo "P-0 e0vn21 suite rc=$?"
for t in test_m2s72_a2.py test_m2s72_a2probe.py test_m2s72_a2v1.py test_m2s72_gen.py test_m2s72s5.py \
         test_m2s72s5_2.py test_m2s72s5_n2.py test_m2s72s5_smoke.py test_m2s72_a21.py test_m2s72_a21_fixture.py; do
  (cd "$CHK" && python3 -B "$t" | tail -1); echo "P-0 $t rc=${PIPESTATUS[0]}"
done                                             # each line must equal its h4-first-task.md §5 expectation
```

- **P-1 / P-3** (integrity before and after): each validation defines its own commands below. Each run's directory is verified against its original manifest with the accepted tool: `$PY "$CHK/m2s72s5_lib.py" verify-manifest <manifest>`. Each result is recorded in `$E/<v>/integrity-{before,after}.txt` and must be identical.
- **P-4:** `(cd "$E" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum) > "$E/SHA256SUMS"`, plus the environment identity X-4 (`python3 --version`, `uname -srm`, the Simu5G HEAD).

**Comparison rules:**
- All counts are compared as exact integers.
- Statistics use `abs(rec - val) <= 1e-9 * max(1.0, abs(val))`.
- Statuses and verdicts must match exactly.
- `hrq --expect` exits 0 only if every expectation is met; a mismatch exits **5**.
- A deviation is reported as found. Nothing is re-run, adjusted or relabelled (X-6).

### 8.2 V-N1: N = 1 smoke `M2S72-E0v-q0-f1`, seed 0 (ACK only, one UE)

```bash
N1="$R/s5-smoke-1/m2/M2-S7.2a-s5smoke"
mkdir "$E/vn1"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-before.txt"; echo "P-1 rc=$?"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/hrq" --expect "$CHK/expect/vn1.expect.json"; echo "V-N1 hrq rc=$?"   # expect 0
$PY "$CHK/check_m2s72_s5n2.py" xa "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/xa"; echo "V-N1 xa rc=$?"                                              # unchanged reference
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-after.txt"; echo "P-3 rc=$?"
cmp "$E/vn1/integrity-before.txt" "$E/vn1/integrity-after.txt" && echo "P-3 identical"
```

The standalone `check_m2s72_a21.py` cross-check is dropped: `hrq` writes the a21 record from its single replay (D-A1-9), and T-a21-record-equiv covers writer equivalence.

| Declared expectation (`vn1.expect.json`) | Value |
|---|---|
| A-1 summary | a1a = 11 697; a1b = 0; ambiguous = orphan = re-insert = 0 |
| A-1 PU-4 (reported) | PASS, unchanged |
| A-2.1 rows | A2-0, A2-0s, A2-1, A2-2, A2-3, A2-6, A2-7, A2-9 PASS; A2-5 PASS or NX; A2-4a / 4b / 4c **NX**; A2-8 PASS. Verdicts: `f1d-i` VALID, `full` VALID. |
| MAP-UE / C-0 | PASS / PASS |
| per-UE occupancy | A-2.1 = A-1's (N = 1: A-1 exact) = XA's truth occupancy |
| PU-4h / PU-4o UE 0 / A2-8u UE 0 | PASS / PASS / PASS |
| held features | {single-candidate ACK attribution}, plus "end-of-run censoring: inserted in the last TTI" **iff** its count > 0. The split of the 5 censored units was never predicted (`-a2-implementation.md`), so this is a declared condition, not a value. |
| `hrq` verdict | **HELD FOR REVIEW** (exit 3 without `--expect`) |

### 8.3 V-N2: N = 2 smoke `M2S72-E0vN-q0-one0-n2-f1`, seed 0 (ACK only, two UEs)

```bash
N2="$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2"
mkdir "$E/vn2"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-before.txt"; echo "P-1 rc=$?"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/hrq" --expect "$CHK/expect/vn2.expect.json"; echo "V-N2 hrq rc=$?"   # expect 0
$PY "$CHK/check_m2s72_s5n2.py" xa "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/xa"; echo "V-N2 xa rc=$?"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-after.txt"; echo "P-3 rc=$?"
cmp "$E/vn2/integrity-before.txt" "$E/vn2/integrity-after.txt" && echo "P-3 identical"
```

| Declared expectation (`vn2.expect.json`) | Value |
|---|---|
| A-1 summary (reported unchanged) | a1a = 9 718; a1b = 2 476; ambiguous = 768; re-insert = 768; orphan = 0 |
| A-1 PU-4 (reported) | **FAIL, retained verbatim** |
| A-2.1 | • 12 194 single-candidate lines; 384 exchangeable groups / 768 lines, all certified (A2-5 PASS).<br>• A2-4a/b/c NX; A2-7 PASS; A2-8 PASS.<br>• Verdicts VALID / VALID.<br>*These counts are the declared expectations of PC-A2-N2 (predicted), never yet confirmed on the genuine output. A deviation is a finding: exit 5, reported as found.* |
| MAP-UE / C-0 | PASS / PASS |
| per-UE occupancy | A-2.1 = XA truth occupancy for both UEs |
| PU-4h / PU-4o ×2 / A2-8u ×2 | PASS / PASS ×2 / PASS ×2 |
| agreement | the 12 194 A-1-attributed lines: disagree = 0; the 768 A-1-unattributed lines, all `exchangeable` in A-2.1 |
| held features | {single-candidate ACK attribution}, plus "inserted in the last TTI" iff its count > 0 |
| `hrq` verdict | **HELD FOR REVIEW** |

### 8.4 V-V1: A2-V1 run `M2S72-E0vN-q0-one0-n2-f1_A2V1` (sealed; genuine NACKs on ue[1])

```bash
SEAL=3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0
FXSHA=cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b
mkdir "$E/vv1"
$PY "$CHK/m2s72_a21_fixture.py" extract --results-root "$R" --seal-sha256 "$SEAL" --out "$E/vv1/fx-before"; echo "P-1 extract rc=$?"   # expect 0
grep -q "^$FXSHA  a2v1-first-chain.log.gz$" "$E/vv1/fx-before/a2v1-first-chain.log.gz.sha256" && echo "P-1 reproduces the F3 fixture"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$R/a2-nack-1/runs" M2S72-E0vN-q0-one0-n2-f1_A2V1 "$E/vv1/hrq" --expect "$CHK/expect/vv1.expect.json"; echo "V-V1 hrq rc=$?"   # expect 0
$PY "$CHK/m2s72_a21_fixture.py" extract --results-root "$R" --seal-sha256 "$SEAL" --out "$E/vv1/fx-after"; echo "P-3 extract rc=$?"
grep -q "^$FXSHA  a2v1-first-chain.log.gz$" "$E/vv1/fx-after/a2v1-first-chain.log.gz.sha256" && echo "P-3 reproduces the F3 fixture"
```

- The extractor (accepted, unchanged; `-I` safe, because it imports nothing from the repository) re-verifies the seal, the 33 sealed records and the 58-entry raw manifest (E-1 … E-3, E-7) before and after. This is the S1 integrity procedure.
- The `.sha256` pin line format `<sha256>  a2v1-first-chain.log.gz` is the one `load_fixture` enforces.

| Declared expectation (`vv1.expect.json`) | Value |
|---|---|
| per-node accounting | exactly the S1 closure §3 table:<br>• node 2049: inserts 11 702, transmissions 11 702, feedback 11 697, ACK 11 697, NACK 0, discarded 0, censored 5;<br>• node 2050: inserts 1 265, transmissions 1 409, feedback 1 408, ACK 1 264, NACK 144, retransmissions 144, discarded 0, censored 1. |
| line classes | 371 exchangeable groups (742 lines); 40 resolved by retransmission evidence; 15 bound; 129 handles retired; unresolved `[]`; end states `{censored: awaiting feedback: 6}` |
| A-2.1 rows and verdicts | as S1 §3; run-level A2-8 PASS; `f1d-i` VALID; `full` INCOMPLETE (A2-4c NE, the only non-PASS required row) |
| A2-8u | node 2049: 0 / 1; node 2050: 0.10227272727272728 / 1.1139240506329113 → PASS ×2 |
| MAP-UE / C-0 / PU-4h / PU-4o ×2 | PASS / PASS / PASS / PASS ×2 |
| A-1 (reported) | values as computed. No expectation is declared, because A-1 on genuine NACK input is not an accepted quantity (L-2). Disagreements are listed by class. |
| held features | {single-candidate ACK attribution}, plus "NACK resolved: single candidate" iff its count > 0. S1 does not state that count; V-V1's record will. |
| `hrq` verdict | **HELD FOR REVIEW** |
| original A2-V1 verdict | **NOT ACCEPTED, unchanged.** V-V1 is a consistency check of the wrapper, not an acceptance of A2-V1. |

### 8.5 Acceptance gates of the validations

| Gate | Condition |
|---|---|
| VG-0 | P-0 … P-4 complete; integrity identical before and after |
| VG-1 | `hrq --expect` exit 0: every declared expectation met exactly |
| VG-2 | no wrapper output relabels a historical result (the PU-4 rows are verbatim; the A2-V1 verdict is untouched) |
| VG-3 | the maintainer accepts the record |

**After VG-3:**
- **For V-N1 and V-N2:** the maintainer decides **S5-2-D2** (DR-07c), which sets `S5N_ADAPTER_VALIDATED` for E0v-N campaign runs.
- **For any of the three:** the maintainer may admit "single-candidate ACK attribution", and, on V-V1, "NACK resolved: single candidate" if shown. This is a separate, reviewed registry change citing the accepted record (§4.7).
- Only after both can a campaign run reach PASS.

**None of these validations is executed by WP-A1.**

---

## 9. Implementation sequence (after design approval)

| Step | Content | Exit criterion |
|---|---|---|
| I-1 | `m2s72_e0vn21.py` skeleton: `sys.path` preamble, status vocabulary, the registry loader and its validation, name guard, schema | T-name-guard, T-registry, T-schema, T-imports-isolated |
| I-2 | MAP-UE and A2-8u with CR-1 … CR-4 | T-map, T-a28-compat, NC-scalar-ue1, NC-scalar-missing-ue1 |
| I-3 | C-0, PU-4h, PU-4o, censoring classes | T-c0, T-n2-*, T-n4-*, T-censor-*, NC-swap, NC-occ-*, NC-c0-* |
| I-4 | A-1 historical report and agreement diagnostic | T-agree, NC-pu4-relabel |
| I-5 | FGO flag and verdict composition (precedence 2 > 1 > 4 > 3 > 0) | T-n3-groups, T-multinack, T-discard, NC-registry* |
| I-6 | CLI `hrq` and `hrq-fixture`, single replay, the a21 record writer, `--expect` | T-f3-hrq, T-f3-a1, T-single-replay, T-a21-record-equiv, T-expect-exit |
| I-7 | CLI `run` (composition with `s5n.run_one`), s5n row-set check, composed digest, one run per process | T-s5n-*, T-digest-ownership, T-one-run-per-process, T-no-d2-bypass |
| I-8 | CLI `controls`; implementation record; the expectation files committed for review | all of §7 |
| I-9 | **separately reviewed CI change** (D-A1-6: approved in principle): add the suite to tier-0 with its exact line | tier-0 green with the new exact line |

- Each step is one commit, with tests.
- A draft PR is opened for review. There is no merge without the maintainer.
- The registry admissions of §8.5 are never part of these steps.

---

## 10. Acceptance criteria of WP-A1

| ID | Criterion | Level |
|---|---|---|
| AC-1 | This design approved (revision 2 or later), with the D-A1 rulings recorded (§0) | — |
| AC-2 | All tests of §7 PASS locally and in CI; every negative control AS DECLARED (none NOT BUILDABLE without a recorded reason) | 2 |
| AC-3 | §6 guarantees hold: no frozen, accepted, s5n or runner file differs | 2 |
| AC-4 | Every historical result reported verbatim; no PU-4 FAIL relabelled (NC-pu4-relabel) | 2 |
| AC-5 | V-N1, V-N2 and V-V1 executed independently and accepted (VG-0 … VG-3) | **3** (maintainer) |
| AC-6 | S5-2-D2 decided by the maintainer on the basis of AC-5 | decision |

WP-A1 closes at level 2 with AC-1 … AC-4. Level 3 needs AC-5 and AC-6, which are outside the development agent's authority.

---

## 11. Decisions and risks

### 11.1 Decisions (rulings on revision 1)

| ID | Decision | Ruling | Design consequence |
|---|---|---|---|
| D-A1-1 | PU-4h / PU-4o definitions | approved subject to C1–C3 | §4.3–§4.6 rewritten fail-closed; MAP-UE and C-0 added |
| D-A1-2 | Campaign contract | F1-d(i) approved | PU-4h uses `verdict(rows, "f1d-i")`; `full` is reported |
| D-A1-3 | Scope of censoring NE | uncertainty-related NE stays gating | §4.2: no non-gating NE; group-level censoring → INCOMPLETE; an absent UE (no PDU) → NE, gating |
| D-A1-4 | Registry | complete registry and evidence review required | §4.7: 18 rows; 10 admitted; inferred and predicted evidence excluded |
| D-A1-5 | PU-5 | retain | unchanged gate |
| D-A1-6 | Tier-0 suite | approved in principle; separate CI review | I-9 |
| D-A1-7 | HELD FOR REVIEW | stop the batch | §5.4: rc 3 stops |
| D-A1-8 | Name guard | wrapper-local | §5.2 |
| D-A1-9 | Contract evaluation | single replay, verdicts derived | §3.3; T-single-replay |
| D-A1-10 | Agreement | diagnostic only | §4.10 |

**New point for the reviewer (no ruling yet):**
- **D-A1-11.** The composed-verdict precedence INCOMPLETE (4) over HELD FOR REVIEW (3), so that a review never covers missing evidence. **Recommendation:** adopt.

### 11.2 Risks

| Risk | Mitigation |
|---|---|
| R-1: the per-UE A2-8 duplicates `scalar_row`'s arithmetic | the same quoted formula and the shared `REL_TOL`; CR-1 … CR-4 tested on every case (T-a28-compat) |
| R-2: `E.rows` global accumulation (L-11) | one evaluation per process, enforced |
| R-3: A-2.1 runtime and memory at N = 8 (no genuine N ≥ 3 evidence) | one replay; the per-run time recorded in the digest; measured at the first N = 8 run |
| R-4: genuine N ≥ 3 paths are untested on real output | FGO: HELD FOR REVIEW at first occurrence |
| R-5: XA cannot separate some same-instant lines | A2-7 group multisets; PU-4o relies on occupancy equality |
| R-6: the registry becomes a way to wave features through | admission only with E1 / E2 evidence from CLOSED ACCEPTED records; validated at load; sha256 recorded; NC-registry* |
| R-7: E0v-N runs on ideal channels contain no NACK | NACK paths stay evidenced only by A2-V1 (S1, F3); stated in every coverage section |
| R-8: the V-V1 expectations depend on VM-reported S1 values | V-V1 compares against the S1 closure tables. Any deviation is a finding (exit 5). |
| R-9: a campaign run whose log ends inside an uncertain group is INCOMPLETE (L-13). ACK-only groups certify at once, so it needs a NACK at the very end; it is expected to be rare on ideal channels. | reported as INCOMPLETE, stopping the batch; no fallback rule is defined. Any remedy, such as a longer run, is a separate decision. |
| R-10: every realistic run is HELD FOR REVIEW until "single-candidate ACK attribution" is admitted | intended (C4). Admission follows V-N1 / V-N2 acceptance, which S5-2-D2 requires anyway (§8.5). |

---

## 12. Summary for review

- **Problem.** Under rule A-1, PU-4 FAILs whenever two UEs' feedback on the same process arrives at the same instant. This was demonstrated on the N = 2 smoke (384 pairs). It is a property of the schedule, not of N alone, and it blocks the E0v-N campaign.
- **Change.** A-2.1, accepted on genuine output within stated limits, becomes the per-UE H-ARQ source through gates that fail closed:
  - **MAP-UE**: a bijective UE-to-node mapping;
  - **C-0**: identical canonical event sequences for A-1 and A-2.1;
  - **PU-4h**: run attribution under F1-d(i);
  - **PU-4o UE k**: per-UE occupancy, PASS only on explicit equality with a valid reference and valid global rows;
  - **A2-8u UE k**: both Simu5G statistics, for every expected UE.

  The run-level A2-8 is preserved verbatim. The compatibility relation CR-1 … CR-4 replaces the false exact invariant.
- **Censoring.** Attributable unit-level end states do not affect the rows. Uncertain group-level censoring makes the run INCOMPLETE. No NE is non-gating.
- **Review gate.** The FGO registry covers all 18 features, with 10 admitted on explicit accepted evidence. Inferred, predicted and synthetic evidence never admits a feature. Until "single-candidate ACK attribution" is admitted from an accepted validation, runs are HELD FOR REVIEW.
- **Preservation.**
  - The s5n records and digest are byte-identical. The s5n gate semantics are unchanged, except that PU-4 is not a gate.
  - The historical A-1 PU-4 is verbatim, and A-1 values appear only under `historical`.
  - Only new files are added.
- **Validation.** V-N1, V-N2 and V-V1 are specified with complete commands and committed expectation files. An expectation mismatch exits 5. S5-2-D2 remains pending until they are accepted.
