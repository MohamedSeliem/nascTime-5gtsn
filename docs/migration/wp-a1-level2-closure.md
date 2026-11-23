# WP-A1 — Level-2 closure assessment (AC-1 … AC-4)

**Status: prepared for independent review (step 133), 23 November 2026.**
- This is the development agent's assessment. It is not a maintainer sign-off, an acceptance decision or a merge approval.
- AC-1 … AC-4 are decided by the maintainer (design §10).
- **Level 3 has not been performed.** V-N1, V-N2 and V-V1 have not been executed, AC-5 and AC-6 are open, S5-2-D2 is open, and `S5N_ADAPTER_VALIDATED` has never been set.

| Item | Value |
|---|---|
| Design (contract) | `docs/migration/wp-a1-a21-e0vn-wrapper-design.md`, revision 2.1, `57a80ca2e9d84d11ee20148b378437c6317456ec`; **not modified by this document** |
| Implementation record | `simulations/m2/results/M2-S7.2a-a1-implementation.md` (version 1, added in I-8) |
| **Reviewed implementation** | **`f3f68be696777e42b0717f949625855ddb475435`** (I-1 … I-9, plus the I-8 pin correction `70425d33b80b980874b3cd7274e4e6ee99dd0759`) |
| Baseline | `m2/continuation` at `7bb0e3a7145602ae556239c8667362203d9294b5` |
| Pull request | draft PR #11, `wp/a1-a21-e0vn-wrapper`; open, not merged |
| Validation runbook (level 3, prepared only) | `docs/migration/wp-a1-validation-runbook.md`, revision 3 (step 139; fail-closed scripts in `docs/migration/wp-a1-validation/`; GO / NO-GO gate in its §3) |

## 1. GitHub CI evidence for `f3f68be`

| Workflow | Run | Result |
|---|---|---|
| `tier0-python` | [45168770895](https://github.com/MohamedSeliem/nascTime-5gtsn/actions/runs/45168770895), job `137672512864` | **success**. 11 / 11 suites PASS: exit 0, exact final line and zero non-success counts. Fixture gate and Simu5G v1.8.1 gate (`7477d266…`) PASS. Python 3.13.18. Tested merge ref `4ed458a2f10bf846fb7cd731afe30082e2e8ccd4`. |
| `tier1-full-stack` | [45168770830](https://github.com/MohamedSeliem/nascTime-5gtsn/actions/runs/45168770830) | **success** overall. "Trigger selection" PASS. "Offline self-tests" and "full-stack build" were **SKIPPED**, because the PR is a draft and has no `tier1:run` label (DR-14). **Tier-1 therefore provides no build evidence for this PR.** |

Tier-0 final lines on GitHub:

| Suite | Final line | s |
|---|---|---:|
| `test_m2s72_a2.py` | `A-2 tests: 18 / 18 PASS` | 18.7 |
| `test_m2s72_a2probe.py` | `A-2 probe tests: 11 / 11 PASS` | 7.0 |
| `test_m2s72_a2v1.py` | `10 / 10 PASS` | 16.6 |
| `test_m2s72_gen.py` | `generator negative tests: 67 PASS, 0 FAIL` | 1.6 |
| `test_m2s72s5.py` | `S5-1 tests: 38 / 38 PASS` | 15.3 |
| `test_m2s72s5_2.py` | `S5-2 tests: 28 / 28 PASS` | 1.1 |
| `test_m2s72s5_n2.py` | `S5 N = 2 tests: 19 / 19 PASS` | 18.9 |
| `test_m2s72s5_smoke.py` | `S5 smoke contract tests: 9 / 9 PASS` | 0.1 |
| `test_m2s72_a21.py` | `A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL` | 25.9 |
| `test_m2s72_a21_fixture.py` | `A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL` | 2.5 |
| `test_m2s72_e0vn21.py` (WP-A1; `python3 -I -B` from `$RUNNER_TEMP`) | `WP-A1 e0vn21 tests: 52 / 52 PASS, 0 FAIL` | 45.8 |

The working tree was not modified during the run. The two suites outside tier-0 (`test_m2s72a2v1_wrapper.py`, `test_m2s72_compare.py`) were NOT RUN, as declared.

## 2. Assessment against AC-1 … AC-4

| ID | Criterion (design §10) | Evidence | Assessment |
|---|---|---|---|
| AC-1 | Design approved (revision 2 or later), D-A1 rulings recorded | Revision 2.1 (`57a80ca`) approved for implementation at step 113. D-A1-1 … D-A1-10 recorded in design §0 / §11.1; D-A1-11 approved at step 112c. | **Met.** |
| AC-2 | All §7 tests PASS locally and in CI; every negative control as declared; no NOT BUILDABLE without a recorded reason | §3 below. 52 / 52 locally (`python3 -I -B`, unrelated directory) and on GitHub tier-0. Every §7 ID is implemented under its own name, except T-s5n-rowset, which is implemented as T-s5n-rows (record §4.5). The `controls` NOT BUILDABLE results all carry recorded reasons (record §5). | **Met, at synthetic and public-fixture level** (see §5). |
| AC-3 | §6 guarantees: no frozen, accepted, s5n or runner file differs | §4 below. The pin tests pass in CI with full history. The diff against `7bb0e3a` contains only the new WP-A1 files and the tier-0 workflow. | **Met, with one authorised deviation for the maintainer to confirm:** design §6 lists "workflows unchanged". `.github/workflows/tier0-python.yml` was changed by I-9 under D-A1-6 and the step-131 authorisation. The I-8 pin correction excludes only that one file; `tier1-full-stack.yml` and the rest of `.github` stay pinned. |
| AC-4 | Every historical result reported verbatim; no PU-4 FAIL relabelled | NC-pu4-relabel PASS: verbatim, never PASS / NA / superseded. Design §6 also names "T-pu4-verbatim"; the suite has no test under that name, and NC-pu4-relabel carries the verbatim assertion. This is noted for the reviewer. A-1 values appear only under `historical` (T-digest-ownership). The PU-4 row is extracted verbatim and never gates (`extract_pu4`, T-s5n-semantics). No existing record under `simulations/m2/results/` or `simulations/results/` was changed. | **Met.** |

**Conclusion (development agent's assessment, for the maintainer):** the evidence supports closing WP-A1 at level 2 on AC-1 … AC-4, subject to the maintainer confirming the §6 workflow deviation noted under AC-3.

## 3. Completed tests and negative controls

All declared tests are listed with their expected and observed outcomes in implementation record §4. In summary:

| Group (design §7) | Count | Input types | Result |
|---|---|---|---|
| §7.1 positive and structural | 30 IDs (incl. T-n1-identity, T-a28-compat, T-map, T-c0, T-name-guard, T-s5n-semantics, T-single-replay, T-a21-record-equiv, T-digest-ownership, T-registry, T-expect-exit, T-no-d2-bypass) | synthetic, accepted references, repository | all PASS |
| §7.2 genuine F3 fixture | T-f3-hrq (58 / 58 declared values), T-f3-a1 | public fixture `cfb05ff7…` | PASS |
| §7.3 negative controls | 27 IDs: NC-swap, NC-ue-relabel, NC-occ-*, NC-scalar-*, NC-c0-* (8), NC-dropfb, NC-dupins, NC-shift, NC-node-map, NC-no-ue-lines, NC-registry* (4), NC-pu4-relabel, NC-name, NC-full-masquerade | synthetic, repository | all as declared |
| §7.4 regression protection | T-a1-frozen, T-a1-a21-pinned, T-a1-s5n-pinned, T-s5n-transparent, tier-0 | git history, accepted code | PASS |
| Added by reviews | T-pu4h, T-a24c-review, T-verdict, NC-cli-inputs, NC-run, NC-provenance, T-controls, T-expect-files | synthetic, fixture | PASS |

**`controls` mode (synthetic runs, record §5):**

| Run | PASS | FAIL | NOT BUILDABLE | Exit |
|---|---:|---:|---:|---:|
| N = 2 with NACKs and `.sca` | 22 | 0 | 0 | 0 |
| N = 1 | 12 | 0 | 10 (reason: needs N ≥ 2 or a retransmission) | 0 |
| N = 2 without `.sca` | 19 | 0 | 3 (reason: no `.sca`, A2-8u baseline not PASS) | 0 |
| N = 2 without UE-side lines | 2 | 0 | 20 (reason: PU-4h NE without a reference) | 4 |

**Sensitivity:** T-controls breaks four guarded mechanisms in memory and shows that the corresponding control FAILs (record §5).

## 4. Protected files and historical results

| Protection | Pin | Checked by | CI result |
|---|---|---|---|
| Frozen A-2 / XA / A-1 files; A2-V1 evaluator | `fbee202`, `39a6434` | T-a1-frozen | PASS |
| Accepted A-2.1 files (5) | `d920125` | T-a1-a21-pinned | PASS |
| s5n, adapter, s5v, s5n2, lib, e0, b, i2h, f0, f0r2, MAC-log reader, `m2s72s5.sh`, `.ini` files, `.github` except the tier-0 workflow, `check/fixtures` | `7bb0e3a` | T-a1-s5n-pinned | PASS |
| FGO registry (18 features, 9 admitted) | `7e5c169` | T-registry-immutable, plus a sha256 check in the suite | PASS |

**Detection of the I-8 pin correction (step 131, verified locally before commit):** a change to `tier1-full-stack.yml`, a new staged file under `.github`, or a change to any of `check_m2s72_s5n.py`, `check_m2s72_b.py`, `m2s72_maclog.py`, `m2s72s5.sh`, `m2s72s5.ini`, `m2s72a2v.ini` or the fixture `meta.json` makes T-a1-s5n-pinned FAIL. **Limitation:** the pin uses `git diff`, so a file that is untracked locally is not seen. Anything committed is tracked.

**`git diff --name-status 7bb0e3a f3f68be`** (complete):

```
M  .github/workflows/tier0-python.yml                  (I-9, authorised)
A  docs/migration/wp-a1-a21-e0vn-wrapper-design.md
A  simulations/m2/check/check_m2s72_s5n21.py
A  simulations/m2/check/expect/f3.expect.json
A  simulations/m2/check/expect/vn1.expect.json
A  simulations/m2/check/expect/vn2.expect.json
A  simulations/m2/check/expect/vv1.expect.json
A  simulations/m2/check/m2s72_e0vn21.py
A  simulations/m2/check/m2s72_fgo_registry.json
A  simulations/m2/check/test_m2s72_e0vn21.py
A  simulations/m2/results/M2-S7.2a-a1-implementation.md
```

**Historical results preserved unchanged:**
- the frozen A-2 results (`fbee202`);
- the A-1 PU-4 FAIL of the N = 2 smoke (retained verbatim; reported, never gating);
- **A2-V1 NOT ACCEPTED**;
- A-2.1 accepted within its recorded limits;
- S7.2a partial.

## 5. Limitations of the synthetic and public-fixture testing

1. **Synthetic inputs are level-2 evidence only.** They come from the corrected and frozen generators, plus labelled s5n stand-ins. They establish the wrapper's logic, fail-closed behaviour and record formats, not scientific results.
2. **The public F3 fixture is not an E0v-N run.** It is a two-UE prefix of the sealed A2-V1 run, without `.sca`, so A2-8u is NE and the run is INCOMPLETE by declaration. It is not an A2-V1 acceptance.
3. **No genuine run has been evaluated.** `vn1`, `vn2` and `vv1.expect.json` are declared and schema-checked only. The V-N2 A-2.1 counts are predictions (PC-A2-N2), never confirmed on genuine output.
4. **`run` was tested with stand-ins.** Block B, I-2H, the adapter's observation and validation, SG-403, the grammar census and MG-1 were replaced. The s5n row contract is derived from source, not observed on a genuine E0v-N s5n run.
5. **`controls` ran on synthetic runs only.** It was not run on the fixture or on any private run.
6. **Audit-hook input integrity covers Python-level opens only**, from first opening, under the tracked roots (record §8.1).
7. **No genuine N ≥ 3 evidence exists.** Runtime and memory at N = 8 are unmeasured (risk R-3), and every genuine first occurrence is HELD FOR REVIEW.
8. **NACK paths are evidenced only by A2-V1** (S1, F3). E0v-N runs on ideal channels contain no NACKs (risk R-7).
9. **Tier-1 skipped the build jobs for this PR** (see §1). The WP-A1 code is Python-only and changes no build input.

## 6. Level 3: not performed

- V-N1, V-N2 and V-V1 have not been executed, by the development agent or anyone else.
- No private evidence was read, and no simulation was run.
- AC-5 (independent execution and acceptance, VG-0 … VG-3) and AC-6 (S5-2-D2) are open. Both are outside the development agent's authority (design §10; `remote-execution-feasibility.md` §4, X-1).
- Until registry admissions are made after accepted validations, every realistic run is HELD FOR REVIEW (risk R-10).
- The prepared procedure is `docs/migration/wp-a1-validation-runbook.md`, revision 3. Execution requires GO on its gate (runbook §3); any unmet item is NO-GO.
