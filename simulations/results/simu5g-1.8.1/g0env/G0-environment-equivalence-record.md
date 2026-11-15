# G0 environment-equivalence record: OMNeT++ 6.4.0 (accepted) → OMNeT++ 6.5.0 (D-2 reference)

**Status: OPEN.** The verdicts you reported are recorded in §4. The record closes when:
1. the G0 tool comparison of the VM record files has been run and committed (`g0-compare.txt` in this directory);
2. every listed difference has been attributed (§5);
3. S7.2a CP1 and CP2 have been tested independently on 6.5.0 (§4.2).

**Decision D-2** (Dr Mohamed Seliem, 2026-11-15 12:58):
- The Stage 5 reference environment is **OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1**.
- Conditions: this record, and S7.2a CP1 / CP2 tested independently.
- Do not migrate back to OMNeT++ 6.4.0 solely for hash matching.

**This record does not change** the M2-R181 acceptance (`../M2-R181-acceptance-record.md`), any historical record, checker or FAIL verdict. The accepted 1.8.1 evidence remains the 6.4.0 evidence. G0 establishes whether 6.5.0 reproduces it at the verdict level.

## 1. Environments

| | Accepted (A) | D-2 reference (V) |
|---|---|---|
| Machine | the original cloud container (2 cores, 11 GB disk allowance; since replaced) | your VirtualBox VM |
| OMNeT++ | 6.4.0, build 260506-2cf25223fe | **6.5.0** (build as in the VM `env*.txt` / `stack.txt`, to be attached) |
| INET | 4.7.0 (`inet-4.7.0-dfe270b21f`) | 4.7.0 |
| Simu5G | 1.8.1, tag `v1.8.1` (`7477d266`), unmodified; `libsimu5g.so` `0dbda409…` (build path embedded) | 1.8.1, unmodified (`git status` clean, `Version` = 1.8.1, to be attached) |
| Compiler | Ubuntu clang 18.1.3 | as recorded on the VM |
| nascTime | `m2/simu5g-1.8.1` at `2586bce` | the same tip, clean worktree `nascTime-r181` without the VM NED / INI patch (to be confirmed by `git status --short`, empty) |

## 2. Criteria (declared before the VM files are compared)

| Rule | Content | Status |
|---|---|---|
| **G0-V** | **Verdict identity.** Every compared record has the same verdict words on aligned lines: PASS / FAIL, OPEN / CLOSED for gates, IDENTICAL / DIFFERENT for identity checks. It also has the same PASS / FAIL totals, and no verdict-bearing line is added or removed. For CP2: the same multiset of (family, key, verdict) rows, and the same control verdicts. Historical FAILs must reproduce as FAILs | **required** |
| **G0-N** | **Numeric and textual differences.** Every matched line with a changed number, and every unmatched line without a verdict word, is listed. Each needs an attribution (timestamp, path, run time, …) | listed; attributed in §5 |
| **G0-R** | **Attributed verdict difference.** Allowed only with an exact, mechanically tested mechanism that is not a model or result difference. The historical verdict is kept unchanged, and the difference is counted separately. The tool reports it as attributed only when its attribution test holds | each one listed in §3 |
| **G0-H** | **Raw-output hash identity** (`raw-outputs*.sha256`, `r181c-files.sha256`), per file class | **informational** (D-2) |

**Tool:** `simulations/tools/g0_env_equivalence.py`.
- It reuses the accepted `diff_records.py` unchanged.
- Self-test: 9 / 9 on the committed records:
  - identity;
  - verdict, gate, number and CP2-row canaries;
  - the G0-R1 attribution and two canaries that defeat it;
  - CP2 single-file vs batch format equivalence.
- Exit codes: 0 holds, 1 does not hold, 3 incomplete.

Compared records (paths relative to the VM roots of the acceptance checklist):

| Group | Records | Expected |
|---|---|---|
| M1-S4 | `transport-check.txt`, `clock-check.txt` | PASS |
| M1-S5 | `S5/check.txt` | historical FAIL (W-identity, R-ingress, R-egress) |
| | `v181-s5` | W-identity-v PASS, R-egress-v FAIL |
| | `s5e` | PASS 1073 / 1073 |
| | `s5i` | PASS |
| | the three mutation outputs | FAIL |
| M2-S0 / S1 | `check.txt`, `census.txt` | historical FAIL 20/21 (A7) / 27/28 (C10) |
| M2-S4 | `check.txt` | FAIL 54/55 (R2b) |
| | `r2b-v` | PASS |
| | `r2b-v` mutation | FAIL |
| | `DEPENDENCY-GATE.txt` | OPEN |
| M2-S5 | `check.txt` | FAIL 66/71 |
| | `check-v181c` | 69/71 |
| | `c8demo`, `controls` | PASS |
| | `DEPENDENCY-GATE.txt` | OPEN |
| M2-S6 | `check.txt` | PASS 1863/1863 |
| | `gate-D0` | 8/8 |
| | `gate-E0b` | 3/3 |
| | `report.txt` | as committed |
| CP1 | `f0-check` | F0 PASS, controls 6/6 |
| | `comparator-canaries` | as committed |
| | `t0-check` | 5 PASS / 5 FAIL (T0-R) |
| | `regen.txt` | G0-R1 (§3) |
| CP2 | rows, controls, verdict | 2411 rows, 2391 gate rows PASS / 0 FAIL, controls 13/13, I-2H 40 PASS, verdict PASS |

## 3. Attributed differences

### G0-R1: OMNeT++ 6.5.0 `-q runconfig` prints the effective entry per key only

**Found** here on 2026-11-15, before any VM comparison, with OMNeT++ 6.5.0 built from `omnetpp-6.5.0-core.tgz` (sha256 `2e7dcea6…`). Record: `simulations/m2/results/M2-S7.2a-s5-checks-omnetpp650.txt`.

**Mechanism:**
- OMNeT++ 6.4.0 prints every entry of the inheritance chain, including shadowed ones (mixin `description`, `extends`, overridden keys).
- 6.5.0 prints only the first, effective entry per key.
- For all nine source configurations of `m2s72.ini`, the 6.5.0 output equals the generator's flattening reduced to its first entry per key, exactly (keys, values, order). Examples: `M2S71-q0-idle` 202 → 162 entries, `M2S71-qdu-Ca-sus` 246 → 187.

**Effect:**
- The accepted `m2s72_gen.py verify` (flattening identity, used by `m2s72.sh regen`, so in CP1 / CP2 `regen.txt`) reports `DIFFERENT` ×9 and `verify rc 1` on 6.5.0. On 6.4.0 it reported `IDENTICAL` ×9 and rc 0. That 6.5.0 verdict is **kept as it is**.
- No checker parses runconfig.
- The Stage 5 `verify` / `diff` compare effective configurations. They pass on 6.5.0.

**Version-independent check:** `simulations/m2/tools/m2s72_verify_eff.py`.
- It compares effective entries, keys, values and order. On 6.5.0: 9 / 9 IDENTICAL.
- Controls 5 / 5:
  - a changed value, a dropped key and a swapped pair are each detected;
  - a changed shadowed entry is correctly not an effective change.

**Attribution test** in the G0 tool. It holds only if:
- every differing line of `regen.txt` is a flattening line IDENTICAL → DIFFERENT, its "first difference" detail, or `verify rc 0 → 1`;
- each runconfig count equals the effective count reported by `verify-eff` run on the same VM, and that output reports all IDENTICAL;
- every other line is byte-equal.

## 4. Results

### 4.1 Reported by the reviewer (2026-11-15 12:58); VM record files not yet compared by the tool

| Item | Reported on the VM (6.5.0) | Accepted reference (6.4.0) | Verdict identity |
|---|---|---|---|
| M1-S4 | PASS | PASS | as reported: identical |
| M1-S5 (version-aware) | PASS | PASS (S5-W-identity-v, S5-R-ingress-v, S5-R-egress-v2) | as reported: identical |
| R2b-v / its mutation | PASS / FAIL | PASS / FAIL | as reported: identical |
| Dependency gates M2-S4 → S5, M2-S5 → S6 | both OPEN | both OPEN | as reported: identical |
| M2-S5 historical failures | match | FAIL 66/71 (C8, N-tseSlot, N-noFcsNw, N-noStrip, N-fwdPdelay) | as reported: identical |
| Replacement controls | PASS | PASS | as reported: identical |
| M2-S6 | 1863 / 1863 | 1863 / 1863 | as reported: identical |
| D0 / E0b | 8 / 8, 3 / 3 | 8 / 8, 3 / 3 | as reported: identical |

**Not yet reported:**
- M1 historical S5 `check.txt` and the mutation outputs;
- M2-S0 / S1 `check.txt`;
- `report.txt`;
- the raw hash lists (G0-H).

The tool comparison (VM procedure §4) covers them.

### 4.2 S7.2a CP1 / CP2 on 6.5.0 (D-2 condition 2)

**Not yet run.** Commands, expected results and stop conditions: `simulations/m2/results/M2-S7.2a-s5-vm-procedure.md` §3.

**Predicted:**
- CP1 as the accepted record, except `regen.txt` (G0-R1);
- CP2 2411 rows / 2391 gate rows PASS / 0 FAIL, controls 13 / 13, I-2H PASS.

## 5. Differences to attribute (G0-N)

Filled in from the appendix of `g0-compare.txt`.

**Expected kinds:**
- timestamps in gate files and run logs;
- results-root paths;
- run times;
- possibly `.sca` / `.vec` run metadata in the hash lists (G0-H, informational).

Any unexplained numeric difference in a check row is reported to you before the record is closed. It is not attributed by assumption.

## 6. Closure conditions

1. `g0-compare.txt` committed here. G0-V: `HOLDS` or `HOLDS EXCEPT … ATTRIBUTED (G0-R1 …)`, with no unattributed verdict difference.
2. Every G0-N line attributed in §5.
3. CP1 and CP2 as in §4.2.
4. The VM environment identities in §1 filled in from the VM `env*.txt` / `stack.txt`, and the VM worktree clean.

Until then, Stage 5 simulation modes stay unauthorised. Under protocol §8, `S5_ENV_DECISION` names this record's closing commit.
