# G0 environment-equivalence record: OMNeT++ 6.4.0 (accepted) → OMNeT++ 6.5.0 (D-2 reference)

**Revision 3, closing (2026-11-15).**
- Revision 1 (`86d7599`) declared the criteria and the closure conditions before any VM file was compared.
- Revision 2 (`5bfded0`) added `g0-compare.txt` and the independent CP1 / CP2 results, with the status kept OPEN.
- Revision 3 adds the VM environment evidence (B-1) and the original report's checksum (B-2), and closes the record.

The criteria (§2) and the closure conditions (§7) are unchanged since revision 1.

**Status: CLOSED.** All four declared closure conditions are satisfied (§7). The basis for each is stated there, including what rests on the reviewer's statement rather than on a file.

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

**V column sources** (§8; committed under `evidence-vm/`):
- the 28 runner-written `env*.txt` / `stack.txt` files (`B1-environment-files.tar.gz`);
- the identity report (`B1-VM-identities.txt`, 2026-11-15T16:07:46Z).

| | Accepted (A) | D-2 reference (V) |
|---|---|---|
| Machine | the original cloud container (2 cores, 11 GB disk allowance; since replaced) | the reviewer's VirtualBox VM, Linux x86_64. Kernel `6.8.0-136-generic` for the 2026-11-12 runs (M1, M2); `6.8.0-138-generic` for the 2026-11-15 runs (CP1, CP2, Stage 5 regen) and the identity report |
| OMNeT++ | 6.4.0, build 260506-2cf25223fe | **6.5.0, build `261029-ccd51e11a4`** in every one of the 18 env files and in the identity report; root `/home/vboxuser/testing_nasc/omnetpp-6.5.0` (every `stack.txt`). This is the same build id as the `omnetpp-6.5.0-core` release built in the development environment (`M2-S7.2a-s5-checks-omnetpp650.txt`) |
| INET | 4.7.0 (`inet-4.7.0-dfe270b21f`) | **`inet-4.7.0-dfe270b21f`** (`Version` file, every env / stack file); `libINET.so` sha256 `da6391946d9e1e5c7f8cc71291f66bcb51a43ce75273194934f4d4a04ad9823c`; root `/home/vboxuser/testing_nasc/inet-4.7.0`. **Not a git checkout:** source state not verifiable by `git status` (§8.1) |
| Simu5G | 1.8.1, tag `v1.8.1` (`7477d266`), unmodified; `libsimu5g.so` `0dbda409…` (build path embedded) | **`Version` 1.8.1**; `libsimu5g.so` sha256 `28a4cbf659e1d7682bd8c5e3b57a28ad6253b91d21f4ad80078a98f9ccaf0d96`, the same in all 10 `stack.txt` files, the Stage 5 regen env and the identity report; root `/home/vboxuser/testing_nasc/simu5g-1.8.1`. **Not a git checkout:** "unmodified" is the reviewer's statement, not verified by `git status` (§8.1) |
| Compiler / Python | Ubuntu clang 18.1.3; Python 3.13.16 | **clang 21.1.8** (env files of M2-S5, M2-S6, CP1, CP2; identity report); **Python 3.13.13** (env files from M2-S4 on; identity report) |
| nascTime, M1 and M2 (V1, V2) | `m2/simu5g-1.8.1` at `2586bce` | `nascTime_commit: 2586bce106bf021284191f6907a599a92fe77d83` in every M1-S4 / S5 and M2-S0 / S1 / S4 / S5 / S6 env and stack file; `libnasctime_m2` sha256 `2ff73f52…` |
| nascTime, CP1 and CP2 | (CP1 rev. 2, CP2 rev. 2 records) | `nascTime_commit: 2586bce…` in all 10 CP1 / CP2 env files and both `stack.txt`; `libnasctime_m2` `2ff73f52…` (the same library as M2); `m2s72_ini_sha256: dfc8a7f7…`, the accepted `m2s72.ini` |
| nascTime, G0 comparison | — | reference records read from worktree `nascTime-s5-2` at `decf848` (paths in `g0-compare.txt`; HEAD in the identity report). Those records are byte-identical to `2586bce`'s (additions only) |
| Worktrees (identity report) | — | `nascTime-r181` `2586bce…`, `nascTime-s5` `86d7599…`, `nascTime-s5-2` `decf848…`. **Clean:** stated by the reviewer (2026-11-15, twice). Basis in the report: §7, condition 4 |

**Consistency observations** (recorded, not used as criteria):
- The VM gate times of §5 fall inside the VM run sequence: the M2-S4 gate at 16:23:37, then the M2-S5 env at 16:23:39; the M2-S5 gate at 16:41:43, then the M2-S6 env at 16:41:46.
- The Stage 5 regen (VM procedure §2) ran from `nascTime-s5` at `86d7599`, with `libnasctime_m2` `f643c660…`. That library hash differs from `2ff73f52…`, although `git diff 2586bce 86d7599 -- src` is empty. The cause is not determined (the worktree path differs). That run is not a G0 record.

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

**Source:** the VM comparison report, produced on the VM by `simulations/tools/g0_env_equivalence.py compare`. Its conclusions are incorporated unchanged.

**Copies in this directory, and their exact relation (B-2):**

| File | sha256 | Bytes | What it is |
|---|---|---|---|
| VM original `/mnt/nasctime-results/g0-validation/g0-compare-corrected.txt` | `a92751f27e64e2f2eb8eccf4b3c737f7b371cfea9e15bc3f7df3e6a9c2a11096` | 11,295 | as reported (`evidence-vm/B2-original-comparison-sha256.txt`; the file name is the reviewer's) |
| `g0-compare.txt` (rev. 2, unchanged) | `2db61d14140502f346510c0268dcd6d322df4e131789eb7ceb9513d0716fa7fa` | 11,408 | the transferred copy, as received |
| `g0-compare.vm-original.txt` (rev. 3) | `a92751f27e64e2f2eb8eccf4b3c737f7b371cfea9e15bc3f7df3e6a9c2a11096` | 11,295 | **byte-identical to the VM original** (equal sha256), reconstructed from the transferred copy |

**Exact explanation:** the VM original ends with two LF characters. The comparator itself produces that: its appendix list ends with an empty element, so `"\n".join(...)` ends in LF and `print` adds a second one (`g0_env_equivalence.py`, lines 291 / 299 and 430).

The transferred copy is the VM original with two changes:
1. every line terminator converted from LF to CRLF;
2. the final empty line removed.

No other byte differs. So `(transferred copy with CR removed) + one LF` reproduces the VM original exactly (sha256 equal, 11,295 bytes). The two copies have the same 114 lines of text.

**Correction to revision 2.** Revision 2 predicted `b3faf345…` (the CR-free transferred copy, 11,294 bytes) "if only the line endings changed". That prediction missed the dropped final empty line; it is superseded by the exact relation above, not adjusted after the fact. The transferred copy is kept unchanged; both copies stay.

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

| # | Condition | State | Basis |
|---|---|---|---|
| 1 | `g0-compare.txt` committed here; G0-V `HOLDS` or `HOLDS EXCEPT … ATTRIBUTED (G0-R1 …)`, no unattributed verdict difference | **satisfied** | `HOLDS EXCEPT 1 ATTRIBUTED DIFFERENCE(S) (G0-R1; historical verdict kept)`; 0 unattributed; 0 missing. The committed copies relate exactly to the VM original (§4, B-2); `g0-compare.vm-original.txt` is byte-identical to it |
| 2 | every G0-N line attributed in §5 | **satisfied** | N-1, N-2: gate time (`date -u`) and the stage manifest digest, a consequence of the G0-H non-identity, not an explanation of it; N-3: G0-R1, tested by the comparator |
| 3 | CP1 and CP2 as in §4.2 | **satisfied** | §4.2. CP1 / CP2 ran at `nascTime_commit 2586bce` on OMNeT++ 6.5.0 build `261029-ccd51e11a4` (env / stack files) |
| 4 | the VM environment identities in §1 filled in from the VM `env*.txt` / `stack.txt`, and the VM worktree clean | **satisfied** | **Identities:** §1, every value from the 28 env / stack files and the identity report, mutually consistent. **Clean worktree:** the reviewer's explicit statement. The identity report gives each worktree's HEAD. In its dependency blocks each tree gets two git commands (two `fatal` lines each for INET / Simu5G); for the nascTime worktrees nothing follows the HEAD line, which is what an empty `git status --short` prints. The report does not print the commands themselves, so the cleanliness rests on the reviewer's statement, with the report consistent with it |

**G0 is CLOSED** by this revision's commit. Under protocol §8, `S5_ENV_DECISION` names that commit. Closure lifts the environment condition (D-2, condition 1) only; it authorises no simulation. The smoke run and every Stage 5 experiment still need their own authorisation.

## 8. Evidence received from the VM

All files are committed as received; sha256 of each upload is listed in `EVIDENCE.sha256` (this directory):

| File | Content |
|---|---|
| `evidence-vm/B1-VM-identities.txt` | identity report, 2026-11-15T16:07:46Z: OMNeT++, INET, Simu5G, library hashes, compiler, Python, OS, worktree HEADs |
| `evidence-vm/B1-environment-files.tar.gz` | the 28 runner-written `env*.txt` / `stack.txt` files: M1-S4 / S5; M2-S0 / S1 / S4 / S5 / S6; CP1 rev. 2 (`env-all`, `-regen`, `-f0`, `-t0`, `-hashes`); CP2 rev. 2 (`env-r2`, `-r2regen`, `-r2run`, `-r2hashes`, `-r2check`); Stage 5 regen |
| `evidence-vm/B2-original-comparison-sha256.txt` | sha256 of the VM original comparison report |
| `g0-compare.txt`, `g0-compare.vm-original.txt` | §4 |

### 8.1 Limitations carried forward (not closure conditions)

1. **Dependency source state.** INET and Simu5G on the VM are release trees, not git checkouts. Their identity is established by `Version` files and library hashes. That they are unmodified rests on the reviewer's statement. Optional check **O-4**, on the VM, no simulation:

```bash
git clone -q --depth 1 -b v1.8.1 https://github.com/Unipisa/Simu5G.git /tmp/s5ref && diff -rq /tmp/s5ref/src $SIMU5G_ROOT/src | grep -v '\.\(o\|so\|d\)$\|_m\.\(cc\|h\)' ; echo rc $?
git clone -q --depth 1 -b v4.7.0 https://github.com/inet-framework/inet.git /tmp/inetref && diff -rq /tmp/inetref/src $INET_ROOT/src | grep -v '\.\(o\|so\|d\)$\|_m\.\(cc\|h\)' ; echo rc $?
```

   Only build products should be listed: `Only in …` lines for generated files.
2. **G0-H as in §6.** Unexplained CSV non-identity in M2-S0 (13) and M2-S1 (15); `.sca` / `.vec` / `.vci` and log non-identity everywhere; no numerical-equivalence claim; M1 lists not provided. Optional O-1…O-3 (revision 2) remain open and do not affect this closure.
3. **Worktree cleanliness** rests on the reviewer's statement (condition 4 above).
