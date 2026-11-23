# WP-A1 — Independent validation runbook: V-N1, V-N2, V-V1 (prepared, not executed)

**Status: prepared for independent review (step 133), 23 November 2026. Nothing in this runbook has been executed.**
- The procedure is design §8 (`docs/migration/wp-a1-a21-e0vn-wrapper-design.md`, revision 2.1, `57a80ca`), which this runbook **does not modify**.
- The commands in §4 – §7 are copied verbatim from design §8. This runbook adds only:
  - the environment set-up (§3), which design §8 leaves as variables;
  - the bookkeeping of results;
  - supplementary checks (marked **S-n**). These are **not** part of the design procedure and need maintainer approval before they are used (§10).
- **Executor:** an independent executor designated by the maintainer (`remote-execution-feasibility.md` §4, X-1). Never the development agent.
- **Read-only evaluations only.** No simulation is run. No evaluator, source pin, FGO registry or expectation file is changed. `S5N_ADAPTER_VALIDATED` is never set: `hrq` does not read it, and `run` is not used.

## 1. Fixed identities (recorded in every validation record)

| Item | Value |
|---|---|
| Reviewed implementation commit `C` | `f3f68be696777e42b0717f949625855ddb475435` |
| Simu5G | 1.8.1, `HEAD` `7477d2663644bbf78604267cba4fc113b4871ede` (tag `v1.8.1`, `https://github.com/Unipisa/Simu5G`), unmodified |
| `expect/vn1.expect.json` at `C` | blob `cb6665625a2970a1d9c72ab563293b046c6418d9`, sha256 `b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b` (35 keys) |
| `expect/vn2.expect.json` at `C` | blob `883abdf53f64bf41ed74406cde27715132998f55`, sha256 `5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3` (39 keys) |
| `expect/vv1.expect.json` at `C` | blob `f6507bac012c022d52e50cf966f23d59f8188ba1`, sha256 `fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d` (56 keys) |
| `m2s72_fgo_registry.json` at `C` | blob `648506e5e48f54535fabf96c83e6451c14025be0`, sha256 `2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae` (18 features, 9 admitted) |
| A2-V1 seal | `3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0` |
| F3 fixture | `cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b` |
| Python | ≥ 3.11 required (`-I` implies `-P`); the reviewed CI used 3.13.18 |
| Path resolution | DR-13 method 1: a read-only mount of the extraction at the original absolute prefix `$R` |

## 2. Prerequisite checklist

Status values:
- **available**: in the public repository or verified here;
- **missing**: must be provided before execution;
- **to confirm**: exists by record but cannot be verified from this environment.

| # | Prerequisite | Status | Notes |
|---|---|---|---|
| PR-1 | Independent executor designated (X-1) | **missing** | Maintainer decision M-1. |
| PR-2 | Approval of design §8 as the pre-declared protocol (X-2), with the expectation files committed before execution | to confirm | The files are committed at `C`. The maintainer confirms that `C` is the commit to validate (M-2). |
| PR-3 | Full git clone with history containing `7bb0e3a`, `fbee202`, `39a6434`, `d920125`, `7e5c169` and `C` | available | Needed by the pin tests of the P-0 WP-A1 suite. A shallow clone fails them. |
| PR-4 | Simu5G 1.8.1 checkout at `7477d266…`, unmodified (`git status --porcelain` empty) | available (public) | Read-only sources only (A2-0s); not built. |
| PR-5 | Private evidence archives: N = 1 smoke (41 files), N = 2 smoke (58), A2-V1 (58), with their archive checksum manifests | **missing / not authorised here** | Private. Access needs the maintainer's authorisation (M-3). The development agent has not read them. |
| PR-6 | Extraction re-verified against the archive checksum manifest and the original manifests (X-2a) | **missing** | Done by the executor before P-0. Integrity uses DR-13 method (b), in-memory mapping. |
| PR-7 | DR-13 method validated **before any independent evaluation** (DR-13 decision) | **to confirm** | No record of this validation is cited in the WP-A1 documents. Maintainer decision M-4. |
| PR-8 | Read-only mount of the extraction at the original prefix `$R`, with the layout below | **missing** | `"$R/s5-smoke-1/m2/M2-S7.2a-s5smoke/{runs,records}"`, `"$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2/{runs,records}"`, `"$R/a2-nack-1/runs"`, plus the A2-V1 seal and sealed records the extractor needs under `$R`. The mount must reject writes; check with S-2. |
| PR-9 | Per run, the inputs `hrq` reads | to confirm | `<runs>/run-<cfg>.log.gz`, `<runs>/<cfg>/<cfg>/0.sca`, and the run's configuration files for the node ids (Run72). A missing `.sca` makes A2-8u NE and the expectation fails (exit 5). |
| PR-10 | Environment identity record (X-4) | partly defined | Design P-4 records `python3 --version`, `uname -srm` and the Simu5G HEAD. Whether a G0-style equivalence record is needed for a read-only evaluation is maintainer decision M-5. |
| PR-11 | Disk for `$E` and for the I/O of hashing each consumed file twice (record §8.1) | to confirm | The smoke logs are modest. No vector files are read by `hrq`. |
| PR-12 | Bash, coreutils `sha256sum`, `find`, `cmp`, `xargs` | available (standard) | |
| PR-13 | `S5N_ADAPTER_VALIDATED` unset in the executor's environment | executor check (S-1) | `hrq` does not read it. It is unset to keep the environment clean. |

## 3. Environment set-up (not in design §8; fills its variables)

```bash
unset S5N_ADAPTER_VALIDATED
# a full clone (history needed by the pin tests), then a clean detached worktree at C
git clone https://github.com/MohamedSeliem/nascTime-5gtsn.git nasctime-src
git -C nasctime-src worktree add --detach "$PWD/wpa1-validate" f3f68be696777e42b0717f949625855ddb475435
# unmodified Simu5G 1.8.1
git clone --branch v1.8.1 https://github.com/Unipisa/Simu5G.git simu5g-1.8.1
```

Then set the design §8.1 variables exactly:
- `W` = the worktree path;
- `C` = `f3f68be696777e42b0717f949625855ddb475435`;
- `R` = the read-only mount;
- `E` = a fresh path that does not exist;
- `SIMU5G_ROOT` = the Simu5G checkout.

Run everything from a working directory **outside** `$W` and `$E`, for example `cd "$(mktemp -d)"`, so that nothing is written into either.

**Supplementary pre-checks (S-1 … S-4; need approval M-6):**

```bash
test -z "${S5N_ADAPTER_VALIDATED+x}" && echo "S-1 S5N_ADAPTER_VALIDATED unset"
touch "$R/.wtest" 2>/dev/null && { echo "S-2 FAIL: R is writable"; rm -f "$R/.wtest"; } || echo "S-2 R read-only"
test -z "$(git -C "$W" status --porcelain)" && test -z "$(git -C "$SIMU5G_ROOT" status --porcelain)" && echo "S-3 both trees clean"
( cd "$W/simulations/m2/check" && sha256sum expect/vn1.expect.json expect/vn2.expect.json expect/vv1.expect.json m2s72_fgo_registry.json )
                                                    # S-4: must equal the four sha256 values of §1
```

## 4. Common steps (design §8.1, verbatim)

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

**P-0 expected results:**
- `P-0 commit OK`, `P-0 Simu5G OK` and `P-0 fresh evidence dir` are all printed.
- The e0vn21 suite ends with `WP-A1 e0vn21 tests: 52 / 52 PASS, 0 FAIL` and `rc=0`.
- The ten suites print exactly the lines of `h4-first-task.md` §5:

  | Suite | Final line |
  |---|---|
  | `test_m2s72_a2.py` | `A-2 tests: 18 / 18 PASS` |
  | `test_m2s72_a2probe.py` | `A-2 probe tests: 11 / 11 PASS` |
  | `test_m2s72_a2v1.py` | `10 / 10 PASS` |
  | `test_m2s72_gen.py` | `generator negative tests: 67 PASS, 0 FAIL` |
  | `test_m2s72s5.py` | `S5-1 tests: 38 / 38 PASS` |
  | `test_m2s72s5_2.py` | `S5-2 tests: 28 / 28 PASS` |
  | `test_m2s72s5_n2.py` | `S5 N = 2 tests: 19 / 19 PASS` |
  | `test_m2s72s5_smoke.py` | `S5 smoke contract tests: 9 / 9 PASS` |
  | `test_m2s72_a21.py` | `A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL` |
  | `test_m2s72_a21_fixture.py` | `A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL` |

**Preparation finding F-P0 (the design is not changed):** in the ten-suite loop, `${PIPESTATUS[0]}` is read after a subshell. It therefore holds the subshell's status, which is the status of `tail`, and it always prints `rc=0` whatever the suite returned. This was checked: a suite exiting 3 prints `rc=0`. The exact-line comparison remains the effective P-0 check for these ten suites. **S-5** (supplementary, M-6) records each suite's real exit code without changing the declared loop:

```bash
for t in <the same ten suites>; do (cd "$CHK" && python3 -B "$t" > /dev/null 2>&1); echo "S-5 $t rc=$?"; done   # each rc must be 0
```

**P-1 / P-3:** as defined per validation below. Each output is recorded in `$E/<v>/integrity-{before,after}.txt`, and the two must be identical.

**P-4 (after all three validations):**

```bash
(cd "$E" && find . -type f ! -name SHA256SUMS | LC_ALL=C sort | xargs sha256sum) > "$E/SHA256SUMS"
```

The environment identity X-4 is also recorded: `python3 --version`, `uname -srm` and the Simu5G HEAD. **S-6** writes them to `$E/environment.txt` *before* P-4, so that SHA256SUMS covers them.

**Preparation finding F-P4:** `! -name SHA256SUMS` also excludes the extractor's own `SHA256SUMS` files in `$E/vv1/fx-before/` and `$E/vv1/fx-after/`. Those files are therefore not covered by the top-level sums. **S-7** (M-6) additionally records `sha256sum "$E"/vv1/fx-*/SHA256SUMS >> "$E/SHA256SUMS.supplement"`. The declared P-4 command is run unchanged.

**Console transcript (S-8, M-6):** P-1 / P-3 write only the tool's one-line verdict to the integrity files (`manifest verified` or `MANIFEST MISMATCH: …`), and every `rc=` is echoed to the console only. The executor therefore keeps a complete transcript, for example with `script -q "$E.console.log"` started before P-0 and kept **outside** `$E`, and attaches it to the record.

**Comparison rules (design §8.1):**
- Counts are compared as exact integers.
- Statistics use `abs(rec - val) <= 1e-9 * max(1.0, abs(val))`.
- Statuses and verdicts must match exactly.
- `hrq --expect` exits 0 only if every expectation is met, and **5** on a mismatch.
- Nothing is re-run, adjusted or relabelled (X-6).

## 5. V-N1: N = 1 smoke `M2S72-E0v-q0-f1`, seed 0

**Inputs:**
- `N1="$R/s5-smoke-1/m2/M2-S7.2a-s5smoke"`;
- `$N1/runs/run-M2S72-E0v-q0-f1.log.gz`;
- `$N1/runs/M2S72-E0v-q0-f1/M2S72-E0v-q0-f1/0.sca` and the run's configuration files;
- `$N1/records/M2S72-E0v-q0-f1.manifest.sha256` (absolute original paths, resolved by the mount);
- `$CHK/expect/vn1.expect.json`.

**Commands (design §8.2, verbatim):**

```bash
N1="$R/s5-smoke-1/m2/M2-S7.2a-s5smoke"
mkdir "$E/vn1"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-before.txt"; echo "P-1 rc=$?"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/hrq" --expect "$CHK/expect/vn1.expect.json"; echo "V-N1 hrq rc=$?"   # expect 0
$PY "$CHK/check_m2s72_s5n2.py" xa "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/xa"; echo "V-N1 xa rc=$?"                                              # unchanged reference
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-after.txt"; echo "P-3 rc=$?"
cmp "$E/vn1/integrity-before.txt" "$E/vn1/integrity-after.txt" && echo "P-3 identical"
```

**Expected outputs and exit codes:**

| Step | Exit | Output |
|---|---|---|
| P-1 / P-3 | 0 / 0 | `integrity-before.txt` = `integrity-after.txt` = `manifest verified`; then `P-3 identical` |
| `hrq --expect` | **0** | `$E/vn1/hrq/` with `a21-M2S72-E0v-q0-f1.{txt,json}`, `hrq-M2S72-E0v-q0-f1.{txt,json}` and `hrq-M2S72-E0v-q0-f1.expect.txt` ending `ALL EXPECTATIONS MET` |
| `xa` | 0 (tool contract: XA-0 … XA-6 PASS) | `$E/vn1/xa/xa-M2S72-E0v-q0-f1.{txt,json}`. Design §8 declares no expectation for `xa`; it is the unchanged reference (M-7). |

**Declared values** (`vn1.expect.json`, design §8.2):
- A-1: a1a = 11 697; a1b = ambiguous = orphan = re-insert = 0. PU-4 PASS, reported unchanged.
- A-2.1 rows:
  - A2-0, A2-0s, A2-1, A2-2, A2-3, A2-6, A2-7, A2-8 and A2-9 PASS;
  - A2-5 PASS or NX;
  - A2-4a / 4b / 4c NX.
- Verdicts: `f1d-i` VALID, `full` VALID.
- Gates: MAP-UE, C-0, PU-4h, PU-4o UE 0 and A2-8u UE 0 all PASS.
- Held features: {single-candidate ACK attribution}, plus "inserted in the last TTI" iff its count > 0.
- Composed verdict: HELD FOR REVIEW. That is exit 3 without `--expect`; it is still exit 0 with `--expect` when every value matches.

## 6. V-N2: N = 2 smoke `M2S72-E0vN-q0-one0-n2-f1`, seed 0

**Inputs:** as V-N1, under `N2="$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2"`, for configuration `M2S72-E0vN-q0-one0-n2-f1`, with `$CHK/expect/vn2.expect.json`.

**Commands (design §8.3, verbatim):**

```bash
N2="$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2"
mkdir "$E/vn2"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-before.txt"; echo "P-1 rc=$?"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/hrq" --expect "$CHK/expect/vn2.expect.json"; echo "V-N2 hrq rc=$?"   # expect 0
$PY "$CHK/check_m2s72_s5n2.py" xa "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/xa"; echo "V-N2 xa rc=$?"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-after.txt"; echo "P-3 rc=$?"
cmp "$E/vn2/integrity-before.txt" "$E/vn2/integrity-after.txt" && echo "P-3 identical"
```

**Expected outputs and exit codes:**
- P-1 = 0 and P-3 = 0, both files `manifest verified`, then `P-3 identical`.
- `hrq --expect` = **0**, with the same record set as V-N1 for the N = 2 configuration.
- `xa` = 0 by the tool contract: XA-6 is NOT EVALUATED when A-1 is not exact, which still exits 0. No expectation is declared for it (M-7).

**Declared values** (`vn2.expect.json`, design §8.3):
- A-1, reported unchanged: a1a 9 718, a1b 2 476, ambiguous 768, re-insert 768, orphan 0. **PU-4 FAIL, retained verbatim.**
- A-2.1:
  - 12 194 single-candidate lines;
  - 384 exchangeable groups (768 lines), all certified, so A2-5 PASS;
  - A2-4a / b / c NX; A2-7 PASS; A2-8 PASS;
  - verdicts VALID / VALID.

  These counts are predictions (PC-A2-N2) and have never been confirmed on genuine output.
- Gates: MAP-UE, C-0 and PU-4h PASS; PU-4o PASS ×2; A2-8u PASS ×2.
- Agreement: disagree = 0 on the 12 194 lines, and all 768 A-1-unattributed lines are `exchangeable`.
- Held features: {single-candidate ACK attribution, exchangeable ACK groups (2 candidates)}, plus "inserted in the last TTI" iff its count > 0.
- Composed verdict: HELD FOR REVIEW.

## 7. V-V1: A2-V1 run `M2S72-E0vN-q0-one0-n2-f1_A2V1` (sealed)

**Inputs:**
- `$R` containing the sealed A2-V1 tree: the seal, the 33 sealed records and the 58-entry raw manifest the extractor verifies (E-1 … E-3, E-7);
- `$R/a2-nack-1/runs/run-M2S72-E0vN-q0-one0-n2-f1_A2V1.log.gz`, its `.sca` and its configuration files;
- `$CHK/expect/vv1.expect.json`.

**Commands (design §8.4, verbatim):**

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

**Expected outputs and exit codes:**
- **P-1 extract = 0**, writing to `fx-before/`: `steps.txt`, `a2v1-first-chain.log.gz`, its `.sha256`, the metadata file and `SHA256SUMS`. Then `P-1 reproduces the F3 fixture` is printed.
  - Exit 10 is E-0 STOP, with nothing written.
  - Any other non-zero exit leaves `FAILED.txt` and `.partial` outputs. They are kept as found.
- **`hrq --expect` = 0.**
- **P-3 extract = 0** and `P-3 reproduces the F3 fixture`.

**Declared values** (`vv1.expect.json`, design §8.4):
- Per-node accounting, exactly as in the S1 closure §3:
  - node 2049: inserts 11 702, transmissions 11 702, feedback 11 697, ACK 11 697, NACK 0, discarded 0, censored 5;
  - node 2050: inserts 1 265, transmissions 1 409, feedback 1 408, ACK 1 264, NACK 144, retransmissions 144, discarded 0, censored 1.
- Line classes:
  - 371 exchangeable groups (742 lines);
  - 40 resolved by retransmission evidence; 15 bound; 129 handles retired;
  - unresolved `[]`; end states `{censored: awaiting feedback: 6}`.
- Run level: A2-8 PASS; `f1d-i` VALID; `full` INCOMPLETE (A2-4c NE).
- A2-8u: node 2049 = 0 / 1; node 2050 = 0.10227272727272728 / 1.1139240506329113. PASS ×2.
- Gates: MAP-UE, C-0 and PU-4h PASS; PU-4o PASS ×2.
- A-1 is reported with no expectation declared (L-2).
- Held features: {single-candidate ACK attribution, exchangeable ACK groups (2 candidates)}, plus "NACK resolved: single candidate" iff its count > 0.
- Composed verdict: HELD FOR REVIEW.
- **The original A2-V1 verdict stays NOT ACCEPTED.** V-V1 is a consistency check of the wrapper.

## 8. Recording mismatches (expectations are never modified)

1. **Expectation mismatch (`hrq` exit 5).**
   - `hrq-<cfg>.expect.txt` already lists every declared value against the evaluated one, and ends with `EXPECTATION MISMATCH`.
   - The executor copies nothing and edits nothing. The record cites that file, its sha256 from P-4, and the console line `rc=5`.
2. **Other non-zero exits:**
   - 2 = refused, evaluation error, or a malformed expectation file;
   - P-1 / P-3 rc ≠ 0;
   - `cmp` differs;
   - the extractor exits 10 or another non-zero code.

   The partial outputs are kept as found and the step is recorded as failed. The validation stops there: **no retry and no clean-up** (X-6). A fresh attempt needs a new `$E` and the maintainer's approval (M-8).
3. **Expectation files stay as committed at `C`.** S-4, repeated after the run, together with an empty `git -C "$W" status --porcelain`, shows that nothing changed. A discrepancy is a finding against the expectation **or** the implementation; the maintainer decides which. Any correction is a separate reviewed change at a new commit, followed by a new validation.
4. **Findings file.** Each deviation is written to `$E/<v>/findings.md` (written before P-4, so that it is covered). Each entry gives the declared value, the evaluated value, the source file and line in the record, and "reported as found".

## 9. Evidence for VG-0 … VG-3 (design §8.5)

| Gate | Condition | Evidence the executor supplies |
|---|---|---|
| VG-0 | P-0 … P-4 complete; integrity identical before and after | The console transcript with every `P-0 …`, `P-1 rc=0`, `P-3 rc=0`, `P-3 identical` / `reproduces the F3 fixture` line; the `integrity-{before,after}.txt` files (V-N1, V-N2); `fx-before/` and `fx-after/` (V-V1); `$E/SHA256SUMS`; the X-4 environment identity; the DR-13 method statement; S-1 … S-8 if approved. |
| VG-1 | `hrq --expect` exit 0, every declared expectation met exactly | `rc=0` per validation; `hrq-<cfg>.expect.txt` ending `ALL EXPECTATIONS MET`, with its `n / n MATCH` count (35 / 39 / 56 declared keys). |
| VG-2 | No wrapper output relabels a historical result | In `hrq-<cfg>.{txt,json}`: the A-1 PU-4 row is verbatim under `historical` (PASS for V-N1; **FAIL** for V-N2) and never gates. A-1 values appear only under `historical`. The A2-V1 verdict is not restated or changed by any V-V1 output. |
| VG-3 | The maintainer accepts the record | The validation record (one per validation, or one combined), with commit `C`, the four expectation and registry hashes, the input archive identities, the transcript, `$E/SHA256SUMS` and the findings. It is stored in the private evidence repository with checksums (X-5). Until acceptance, its status is "executed, not accepted" (X-9). |

**After VG-3 (outside this runbook):**
- S5-2-D2 (V-N1 and V-N2);
- the registry admissions of design §8.5, each a separate reviewed change.

## 10. Decisions that require maintainer approval

| ID | Decision |
|---|---|
| M-1 | Designate the independent executor (X-1), and who records and transfers the evidence. |
| M-2 | Confirm `f3f68be…` as the commit `C` to validate, and the three committed expectation files as the pre-declared expectations (X-2). |
| M-3 | Authorise access to the three private archives for the executor (PR-5). Their use by the development agent is not requested. |
| M-4 | Confirm that the DR-13 method was validated before this evaluation, or authorise that validation first (PR-7). |
| M-5 | Environment identity: whether P-4's X-4 record (Python, kernel, Simu5G HEAD) suffices for these read-only evaluations, or whether a G0-style equivalence record is required (PR-10). |
| M-6 | Whether the supplementary checks S-1 … S-8 are required, optional or not used. They add evidence and change no declared command. They answer findings F-P0 (the loop's exit code is that of `tail`) and F-P4 (nested `SHA256SUMS` are not covered). |
| M-7 | The status of the `xa` exit code and output in V-N1 and V-N2. Design §8 declares no expectation and VG-1 covers only `hrq`. Recommendation: record it as found; non-gating. |
| M-8 | Policy after a failed step or exit 5: whether a fresh attempt in a new `$E` is ever allowed, and under which record. |
| M-9 | Whether F-P0 and F-P4 should be corrected in a later revision of design §8. This runbook leaves the design unchanged. |
| M-10 | After VG-3: S5-2-D2, and the registry admissions (design §8.5). |

## 11. What was checked while preparing (no execution against evidence)

- Every command in design §8 names a tool and mode that exists at `C`, with the same argument order:
  - `check_m2s72_s5n21.py hrq … --expect`;
  - `check_m2s72_s5n2.py xa`;
  - `m2s72s5_lib.py verify-manifest`;
  - `m2s72_a21_fixture.py extract --results-root --seal-sha256 --out`.
- Each tool imports correctly under `python3 -I -B` from an unrelated directory. With non-existent inputs each reaches its file-open step and fails there; no evidence was used.
- `hrq` and the extractor refuse an existing output directory. `xa` creates its directory if it is missing. A fresh `$E` satisfies all of them.
- The `hrq` name guard admits `M2S72-E0v-q0-f1` (V-N1) and `M2S72-E0vN-q0-one0-n2-f1_A2V1` (V-V1) explicitly. V-N2 is an E0v-N name.
- The `PIPESTATUS` behaviour behind F-P0 was reproduced in Bash with a dummy command; no suite was involved.
