# G0 environment-equivalence record: OMNeT++ 6.4.0 (accepted) → OMNeT++ 6.5.0 (D-2 reference)

**Revision 2 (2026-11-15).** Revision 1 (`86d7599`) declared the criteria and the closure conditions before any VM file was compared. Revision 2 adds the VM evidence: `g0-compare.txt`, CP1 and CP2 completed independently on the VM. The criteria (§2) and the closure conditions (§7) are unchanged.

**Status: OPEN.** Three of the four declared closure conditions are satisfied. **Condition 4 is not:** the VM environment identities and the clean-worktree evidence must come from the VM's own files, which I have not received (§8, blocker B-1). The integrity of the committed `g0-compare.txt` copy also awaits one checksum from the VM (§8, B-2). The record is not closed by assumption.

**What G0 establishes, and what it does not.** G0 establishes **validation-verdict equivalence**:
- every compared validation record of the accepted environment reproduces its verdict on OMNeT++ 6.5.0, historical FAILs included;
- one verdict difference is mechanically attributed (G0-R1);
- the CP2 row-level outcomes are identical.

It does **not** establish raw-output identity or numerical equivalence of the simulation outputs. The `.sca` / `.vec` / `.vci` hashes differ in every compared stage, and some CSV hashes differ in M2-S0 and M2-S1. The cause of those differences has not been determined (§6).

**Decision D-2** (Dr Mohamed Seliem, 2026-11-15 12:58):
- The Stage 5 reference environment is **OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1**.
- Conditions: this record, and S7.2a CP1 / CP2 tested independently.
- Do not migrate back to OMNeT++ 6.4.0 solely for hash matching.

**This record does not change** the M2-R181 acceptance (`../M2-R181-acceptance-record.md`), any historical record, checker or FAIL verdict. The accepted 1.8.1 evidence remains the 6.4.0 evidence. G0 establishes whether 6.5.0 reproduces it at the verdict level.

## 1. Environments

| | Accepted (A) | D-2 reference (V) |
|---|---|---|
| Machine | the original cloud container (2 cores, 11 GB disk allowance; since replaced) | your VirtualBox VM (`/home/vboxuser/testing_nasc`, results also on `/mnt/nasctime-results`) |
| OMNeT++ | 6.4.0, build 260506-2cf25223fe | **6.5.0** (reported). Build id: **pending B-1** |
| INET | 4.7.0 (`inet-4.7.0-dfe270b21f`) | 4.7.0 (reported). Commit, library hash: **pending B-1** |
| Simu5G | 1.8.1, tag `v1.8.1` (`7477d266`), unmodified; `libsimu5g.so` `0dbda409…` (build path embedded) | 1.8.1, unmodified (reported). Commit, `git status`, library hash: **pending B-1** |
| Compiler | Ubuntu clang 18.1.3 | **pending B-1** |
| nascTime | `m2/simu5g-1.8.1` at `2586bce` | worktrees `nascTime-r181` (expected `2586bce`) and `nascTime-s5-2` (expected `decf848`), both **reported clean**, without the VM NED / INI patch. `rev-parse` / `status` output and the commit used by each part: **pending B-1** |

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

**Confirmed on the VM** (`g0-compare.txt`): the attribution test held, every runconfig count equalling its effective count from the VM's `verify-eff.txt`.

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

## 4. Results (VM evidence)

**Source:** `g0-compare.txt` in this directory, produced on the VM by `simulations/tools/g0_env_equivalence.py compare`.
- Its conclusions are incorporated unchanged.
- The file is committed **exactly as received**. The received copy has CRLF line endings (114 / 114 lines); the tool writes LF, so the copy was transformed in transfer.
  - received copy: sha256 `2db61d14140502f346510c0268dcd6d322df4e131789eb7ceb9513d0716fa7fa`, 11,408 bytes;
  - LF-normalised content: sha256 `b3faf345875696908b6bec82100e09eecca2ab6b7f307cb51f700a2e0fbba570`, 11,294 bytes. It must equal the VM file's sha256 (B-2).

**Comparator self-test on the VM:** 9 / 9 PASS (reported).

**Roots** (as printed in `g0-compare.txt`):

| Option | VM path |
|---|---|
| reference | `/home/vboxuser/testing_nasc/nascTime-s5-2/simulations/results/simu5g-1.8.1` |
| `--m1` | `/home/vboxuser/testing_nasc/r181-results` |
| `--m1x` | `/mnt/nasctime-results/g0-validation/m1x` |
| `--m2` | `/home/vboxuser/testing_nasc/r181-results/m2` |
| `--cp1` | `/home/vboxuser/testing_nasc/r181-results/s72` |
| `--cp2` | `/mnt/nasctime-results/cp2-validation-1/m2/M2-S7.2a-cp2r2/cp2r2-check.txt` |

The reference records read from the `nascTime-s5-2` worktree are byte-identical to `2586bce`'s: S5-2 and its ancestors add files only (`git diff --name-status 2586bce decf848`: additions only).

### 4.1 G0-V: verdict identity (required)

`G0-V verdict identity: HOLDS EXCEPT 1 ATTRIBUTED DIFFERENCE(S) (G0-R1; historical verdict kept)`

31 compared items: 30 verdict-identical, 1 verdict-different and attributed (G0-R1), 0 unattributed, 0 not provided.

| Group | Records | Status on the VM | Verdicts (as accepted) |
|---|---|---|---|
| M1-S4 | `transport-check`, `clock-check` | BYTE-IDENTICAL | PASS |
| M1-S5 | historical `check.txt` | BYTE-IDENTICAL | historical FAIL kept (PASS 5 / FAIL 4 verdict words) |
| M1-S5 | `v181-s5`, `s5e`, `s5i` and their three mutation outputs | BYTE-IDENTICAL (6 / 6) | version-aware verdicts as accepted; every mutation FAIL |
| M2-S0, M2-S1 | `check.txt`, `census.txt` | BYTE-IDENTICAL | historical FAIL 20/21 (A7), 27/28 (C10) kept |
| M2-S4 | `check.txt`, `r2b-v-check`, `r2b-v-mutation-check` | BYTE-IDENTICAL | historical FAIL 54/55 (R2b) kept; R2b-v PASS; mutation FAIL |
| M2-S4 | `DEPENDENCY-GATE.txt` | VERDICT-IDENTICAL (differences: §5) | **OPEN** |
| M2-S5 | `check.txt`, `check-v181c`, `c8demo-v181c`, `controls-v181c` | BYTE-IDENTICAL | historical FAIL 66/71 kept; 69/71; C8-v demonstration and replacement controls as accepted |
| M2-S5 | `DEPENDENCY-GATE.txt` | VERDICT-IDENTICAL (differences: §5) | **OPEN** |
| M2-S6 | `check.txt`, `gate-D0`, `gate-E0b`, `report.txt` | BYTE-IDENTICAL | 1863/1863, D0 8/8, E0b 3/3 |
| CP1 | `f0-check`, `comparator-canaries`, `t0-check` | BYTE-IDENTICAL | F0 PASS, controls 6/6; T0 5 PASS / 5 FAIL. The five FAILs are the historical T0-R cross-version rows, kept as FAIL |
| CP1 | `regen.txt` | VERDICT-DIFFERENT, **ATTRIBUTED G0-R1** (§3) | accepted generator `verify`: DIFFERENT ×9, rc 1 on 6.5.0, kept as is |
| CP2 | 2411 rows, controls, verdict | VERDICT-IDENTICAL; 0 differing row / control keys | 2391 gate rows PASS / 0 FAIL; controls 13/13; verdict PASS |

Totals: 27 records byte-identical, 2 verdict-identical with listed differences (the two gates), CP2 identical at the row level, and 1 attributed.

### 4.2 S7.2a CP1 / CP2 on 6.5.0 (D-2 condition 2): completed independently

Revision 1 listed these as "not yet run, predicted". They have now run on the VM, independently of the development environment.

| | Result on the VM | Prediction (rev. 1) |
|---|---|---|
| **CP1 rev. 2** | `f0-check`, `t0-check` and `comparator-canaries` byte-identical to the accepted records. `regen.txt` differs exactly as G0-R1 predicts. The VM's `verify-eff.txt` reports 9 / 9 IDENTICAL; the comparator's G0-R1 attribution test, which reads that file, held. Effective-entry controls 5 / 5 PASS (reported) | as predicted |
| **CP2 rev. 2** (single campaign `m2s72.sh r2`) | 2411 rows aligned with the reference; 2391 gate rows PASS / 0 FAIL; information families as in the reference; controls 13 / 13; verdict PASS; 0 differing (family, key, verdict) rows or control keys | as predicted |

## 5. G0-N: listed differences and their attribution

`g0-compare.txt` lists exactly three difference sections. Every other compared record is byte-identical.

| # | Record | Difference | Attribution | Basis |
|---|---|---|---|---|
| N-1 | M2-S4 `DEPENDENCY-GATE.txt` | line 1: gate time `2026-11-12T12:55:34Z` → `2026-11-12T16:23:37Z`; line 4: manifest digest `7dafacb610710ec3` → `cc094d5b2d56ca91` (file count 1794 on both) | **time:** line 1 is written by `date -u` when the gate runs (`r181b/m2s4_dependency_gate.sh:25`). **digest:** the G3 line is the first 16 hex digits of the sha256 of the stage's own `raw-outputs.sha256` (`:28`). For the reference this is verified here: `sha256(out-r181c-m2/m2/M2-S4/raw-outputs.sha256)` begins `7dafacb610710ec3`. That manifest differs between the environments in 73 `.sca` and 73 `.vec` entries (§6), and its 1794 entries equal 1138 + 510 + 73 + 73. A different manifest has a different digest | mechanical. The digest difference is **a consequence of G0-H non-identity, not an explanation of it** |
| N-2 | M2-S5 `DEPENDENCY-GATE.txt` | line 1: `2026-11-12T13:15:40Z` → `2026-11-12T16:41:43Z`; line 6: digest `ee09b70f2c152a70` → `c593248c23463b75` (2479 files on both) | as N-1 (`r181c/m2s5_dependency_gate.sh:23`, `:28`). Reference prefix verified here (`ee09b70f2c152a70`). Manifest differs in 77 `.sca` and 77 `.vec` entries; 2479 = 1656 + 669 + 77 + 77 | as N-1 |
| N-3 | CP1 `regen.txt` | the nine flattening lines IDENTICAL → DIFFERENT, their "first difference" details, `verify rc 0` → `1` | G0-R1 (§3); the comparator's attribution test held on the VM | mechanical (tested) |

Both gates stay **OPEN** with unchanged G1–G4 text. The VM digests (`cc094d5b…`, `c593248c…`) are as printed in the VM gate files. Their computation from the VM manifests can be confirmed with one `sha256sum` each (§8, optional O-2).

## 6. G0-H: raw-output hash identity (informational)

As compared in `g0-compare.txt`: identical / different / only in the reference / only on the VM.

| Stage | Hash list | pcapng | csv | sca | vec | vci | log |
|---|---|---|---|---|---|---|---|
| M2-S0 | `raw-outputs.sha256` | 154 / 0 / 0 / 0 | **160 / 13** / 0 / 0 | 0 / 22 | 0 / 22 | — | — |
| M2-S0 | `r181c-files.sha256` | 154 / 0 | **160 / 13** | 0 / 22 | 0 / 22 | 0 / 22 | 1 / 13 |
| M2-S1 | `raw-outputs.sha256` | 216 / 0 | **416 / 15** | 0 / 24 | 0 / 24 | — | — |
| M2-S1 | `r181c-files.sha256` | 216 / 0 | **416 / 15** | 0 / 24 | 0 / 24 | 0 / 24 | 1 / 15 |
| M2-S4 | both lists | 510 / 0 | 1138 / 0 | 0 / 73 | 0 / 73 | 0 / 73 | 1 / 46 |
| M2-S5 | both lists | 669 / 0 | 1656 / 0 | 0 / 77 | 0 / 77 | 0 / 77 | 1 / 59 |
| M2-S6 | both lists | 911 / 0 | 1816 / 0 | 0 / 121 | 0 / 121 | 0 / 121 | 1 / 69 |
| M2-S5-r181c | `r181c-files.sha256` | 27 / 0 | 70 / 0 | 0 / 3 | 0 / 3 | 0 / 3 | 0 / 3 |
| CP1 | `raw-outputs.sha256` | 722 / 0 | 2012 / 0 | — | — | — | — |
| M1-S4, M1-S5 | `raw-outputs-all.sha256` | **not provided** (the VM lists were not found under `--m1`) | | | | | |

No file is present on only one side in any compared list.

**What is established:**
- every compared PCAP hash is identical (3,209 files, each stage counted once);
- every compared CSV hash is identical in M2-S4, M2-S5, M2-S6, M2-S5-r181c and CP1 (6,692 files);
- every `.sca`, `.vec` and `.vci` hash differs, and most run logs differ.

**What is not established:**
- **M2-S0: 13, and M2-S1: 15, CSV files differ. The cause is not determined.**
  - The accepted CSV contents are not available for direct comparison: the raw outputs of the accepted environment were lost with its container (recovery record).
  - The corresponding VM CSV files were not found in the preserved VM result tree.
  - The records computed from these runs (`check.txt`, `census.txt`) are byte-identical. That shows these differences do not reach those records' verdicts or printed values. It does not show that the files are equivalent.
- **`.sca` / `.vec` / `.vci` and log non-identity is recorded, not explained.** No claim is made that these differences are metadata only, and no numerical equivalence of scalar or vector results is claimed.
- M1 raw-output identity is not assessed (lists not provided). This is an evidence gap in G0-H only. All nine M1 verdict records are compared under G0-V.

Under the declared criteria, G0-H is informational (D-2: no return to OMNeT++ 6.4.0 for hash matching). None of the above blocks G0-V, and none of it is reclassified.

**Consequence for later work.** Stage 5 results are produced and compared entirely within the D-2 environment. No Stage 5 claim rests on numerical identity with 6.4.0 raw outputs.

## 7. Closure conditions (declared in revision 1, unchanged) and their state

| # | Condition | State | Evidence |
|---|---|---|---|
| 1 | `g0-compare.txt` committed here; G0-V `HOLDS` or `HOLDS EXCEPT … ATTRIBUTED (G0-R1 …)`, no unattributed verdict difference | **satisfied**, with integrity confirmation pending (B-2) | §4; `g0-compare.txt` |
| 2 | every G0-N line attributed in §5 | **satisfied** | §5 (N-1, N-2 mechanical from the gate scripts and the reference manifests; N-3 G0-R1, tested) |
| 3 | CP1 and CP2 as in §4.2 | **satisfied** | §4.2 |
| 4 | the VM environment identities in §1 filled in from the VM `env*.txt` / `stack.txt`, and the VM worktree clean | **NOT satisfied** | §1 still holds the reported values only. The clean worktrees are reported (`nascTime-r181`, `nascTime-s5-2`), but the `git status` / `rev-parse` outputs and the env files are not in hand (B-1) |

**G0 stays OPEN.** Stage 5 simulation modes stay unauthorised. The closing commit will fill §1 from the files of B-1, record B-2, set the status to CLOSED, and nothing else. Under protocol §8, `S5_ENV_DECISION` names that commit.

## 8. Evidence still needed from the VM (nothing below is invented here)

**B-1 (blocks condition 4).**

1. **Environment files:** every `env*.txt` and `stack.txt` that the runners wrote under these roots:
   - `~/testing_nasc/r181-results` (M1, M2, CP1);
   - `/mnt/nasctime-results/cp2-validation-1` (CP2).
2. **Stack and worktree identity:** the output of these commands, with the environment variables as used for the runs:

```bash
opp_run -v | head -3
cat $INET_ROOT/Version; git -C $INET_ROOT rev-parse HEAD; git -C $INET_ROOT status --short | wc -l
cat $SIMU5G_ROOT/Version; git -C $SIMU5G_ROOT rev-parse HEAD; git -C $SIMU5G_ROOT status --short | wc -l
sha256sum $INET_ROOT/src/libINET.so $SIMU5G_ROOT/src/libsimu5g.so
${CXX:-clang++} --version | head -1; python3 --version; uname -srm
for w in ~/testing_nasc/nascTime-r181 ~/testing_nasc/nascTime-s5-2 <any other worktree used for CP1 / CP2>; do
  echo "== $w"; git -C $w rev-parse HEAD; git -C $w status --short | wc -l; git -C $w status --short; done
```

3. **Which worktree and commit ran each part:** M1 (V1), M2 (V2), CP1, CP2 and the G0 comparison. The `nascTime_commit` line of each env file may already say this.

**B-2 (integrity of the committed copy).**
- `sha256sum` of the VM's `g0-compare.txt`.
- Expected `b3faf345875696908b6bec82100e09eecca2ab6b7f307cb51f700a2e0fbba570` if only the line endings changed in transfer.
- A different value means the content differs, and the record would then be rebuilt from the VM file.

**Optional (G0-H detail; does not block closure):**
- **O-1:** the VM `raw-outputs.sha256` of M2-S0 and M2-S1, so the 13 and 15 differing CSV files can be named (identity only, no explanation).
- **O-2:** `sha256sum` of the VM `M2-S4/raw-outputs.sha256` and `M2-S5/raw-outputs.sha256`; prefixes `cc094d5b2d56ca91` and `c593248c23463b75` expected.
- **O-3:** the M1 `raw-outputs-all.sha256` lists, if the M1 runner wrote them under another name.
