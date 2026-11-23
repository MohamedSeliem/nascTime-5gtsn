# WP-A1 — Independent validation runbook: V-N1, V-N2, V-V1 (prepared, not executed)

**Status: revision 2, 23 November 2026, prepared for review.** Revision 1 (`e1b5a76`) was reviewed at step 135, and this revision applies the corrections R1 … R5. **Nothing in this runbook has been executed.**

**Procedure and corrections:**
- The procedure is design §8 (`docs/migration/wp-a1-a21-e0vn-wrapper-design.md`, revision 2.1, `57a80ca`). **The design is not modified.**
- The V-N1, V-N2 and V-V1 commands (§8.2 – §8.4) are used verbatim.
- Two design commands are **corrected** under step 135 (table below). The corrected forms replace the design text for this execution. A later design revision is maintainer decision M-9.

| Correction | Design §8.1 text | Defect | Replaced by |
|---|---|---|---|
| **C-1** (R1) | the P-0 loop `(cd "$CHK" && python3 -B "$t" \| tail -1); echo "… rc=${PIPESTATUS[0]}"` | `${PIPESTATUS[0]}` after the subshell is the exit code of `tail`, so a failing suite prints `rc=0`. Reproduced in Bash with a dummy command. Nothing stops on failure. | the gated P-0 script of §5: each suite's real exit code, exact final line and non-empty output are checked, and the session stops before any access to evidence |
| **C-2** (R2) | P-4 `find . -type f ! -name SHA256SUMS` | the extractor's nested `vv1/fx-*/SHA256SUMS` are left out of the inventory, and nothing covers the inventory itself | the finalisation sequence of §9: every file except the two top-level checksum records, followed by a final checksum record |

**Roles and limits:**
- **Executor:** an independent executor designated by the maintainer (`remote-execution-feasibility.md` §4, X-1). Never the development agent.
- **Read-only evaluations only.** No simulation is run.
- No evaluator, source pin, FGO registry or expectation file is changed.
- `S5N_ADAPTER_VALIDATED` is never set. P-0 requires it to be unset, and `run` is not used.

**Contents:**
- §1 fixed identities;
- §2 the GO / NO-GO gate;
- §3 prerequisites;
- §4 – §9 the stages, in this order:

| Stage | Content | Touches genuine evidence |
|---|---|---|
| 0 | gate A (administrative), §2 | no |
| 1 | set-up and environment identity, §4 | no |
| 2 | P-0 (corrected) and gate B, §5 | **no**: the session stops here on any failure |
| 3 | X-2a integrity of the extraction, DR-13 method (b), §6 | yes, read-only |
| 4 | read-only mount at the original prefix, DR-13 method (a), §6 | yes, read-only |
| 5 | V-N1, V-N2, V-V1 (design §8.2 – §8.4 verbatim), §7 | yes, read-only |
| 6 | evidence finalisation (corrected P-4), §9 | no |

## 1. Fixed identities (recorded in every validation record)

| Item | Value |
|---|---|
| Reviewed implementation commit `C` | `f3f68be696777e42b0717f949625855ddb475435` |
| Simu5G | 1.8.1, `HEAD` `7477d2663644bbf78604267cba4fc113b4871ede` (tag `v1.8.1`, `https://github.com/Unipisa/Simu5G`), unmodified |
| `expect/vn1.expect.json` at `C` | sha256 `b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b` (blob `cb666562…`; 35 keys) |
| `expect/vn2.expect.json` at `C` | sha256 `5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3` (blob `883abdf5…`; 39 keys) |
| `expect/vv1.expect.json` at `C` | sha256 `fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d` (blob `f6507bac…`; 56 keys) |
| `m2s72_fgo_registry.json` at `C` | sha256 `2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae` (blob `648506e5…`; 18 features, 9 admitted) |
| A2-V1 seal | `3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0` |
| F3 fixture | `cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b` |
| Python | ≥ 3.11 (`-I` implies `-P`). The reviewed CI used 3.13.18. |

## 2. GO / NO-GO gate (R5)

**Rule:** GO requires every item in both parts to be met, with the evidence named. **Any unmet item is NO-GO.**
- On NO-GO, nothing further is done. Genuine evidence is not accessed, and the NO-GO is reported to the maintainer with the failed item.
- Gate A is decided before Stage 1. Gate B is decided by the Stage 2 script, after P-0 and before Stage 3.

### Gate A: administrative (before Stage 1)

| # | Item | Evidence required | Met when |
|---|---|---|---|
| A-1 | Designated independent executor (X-1) | the maintainer's written designation, naming the executor and who records and transfers the evidence | designation exists, and the executor is not the development agent |
| A-2 | Fixed reviewed commit and expectation files (X-2) | the maintainer's confirmation of `C` and of the four sha256 values of §1 | confirmed. The values are re-checked mechanically in gate B. |
| A-3 | Authorised access to the original evidence | the maintainer's authorisation for the N = 1 smoke, N = 2 smoke and A2-V1 archives, for this executor and this purpose | authorisation exists |
| A-4 | Approved **and validated** DR-13 procedure | DR-13 (approved 17 Nov 2026), **plus** a record that methods (a) and (b) were validated before this independent evaluation (DR-13 decision; `authoritative-migration-status.md` §0.4) | the validation record exists and is approved. Stages 3 – 4 apply the method; they **do not** validate it. |
| A-5 | Required environment-equivalence evidence (X-4) | an **approved G0-style verdict-equivalence record** for the executor's environment against the D-2 environment, unless the maintainer records that this environment already has one | approved record identified by name and hash. An identity statement alone is **not** sufficient (§4.2). |
| A-6 | Agreed stop, mismatch and retry rules | the maintainer's approval of §8 as proposed or amended | approved |

### Gate B: technical (decided by the Stage 2 script, before any access to evidence)

| # | Item | Checked by | Met when |
|---|---|---|---|
| B-1 | Environment identity recorded | Stage 1 (§4.1) | `$E/environment/identity.txt` complete, and the approved A-5 record referenced in `$E/environment/equivalence-ref.txt` |
| B-2 | Clean worktree at `C` and pinned Simu5G | P-0 (§5) | `HEAD` = `C`; Simu5G `HEAD` = `7477d266…`; both `git status --porcelain --untracked-files=all` empty, before and after the suites |
| B-3 | Fixed expectation files and registry | P-0 | the four sha256 values equal §1 |
| B-4 | `S5N_ADAPTER_VALIDATED` unset | P-0 | unset |
| B-5 | Passing prerequisite suites | P-0 | all 11 suites: exit 0, non-empty output, exact final line |
| B-6 | Fresh evidence directory | P-0 | `$E` did not exist and was created by P-0 |

**GO** is printed by the Stage 2 script only when B-1 … B-6 all hold. That script's exit code 0 is the only GO signal; any other exit code is NO-GO.

## 3. Prerequisites

| # | Prerequisite | Status | Notes |
|---|---|---|---|
| PR-1 | A-1 executor | **missing** | M-1 |
| PR-2 | A-2 confirmation of `C` and the expectation files | **missing** | M-2 |
| PR-3 | A-3 access authorisation | **missing / not authorised here** | M-3. The development agent has not read the private archives. |
| PR-4 | A-4 DR-13 validation record | **missing** | No such record is cited in the WP-A1 documents. M-4. |
| PR-5 | A-5 approved G0-style equivalence record for the executor's environment | **missing** | M-5 |
| PR-6 | A-6 agreed rules | **missing** | M-6 |
| PR-7 | Full git clone with history containing `7bb0e3a`, `fbee202`, `39a6434`, `d920125`, `7e5c169` and `C` | available | The pin tests in P-0 need it. A shallow clone fails them. |
| PR-8 | Simu5G 1.8.1 checkout at `7477d266…` | available (public) | Sources only; not built. |
| PR-9 | The three archives with their archive checksum manifests (N = 1 smoke: 41 files; N = 2 smoke: 58; A2-V1: 58) | **missing** | Private. The format of the archive checksum manifests is to be confirmed by the maintainer: the Stage 3 command for them is the one distributed with the archives. |
| PR-10 | Extraction at `$X` mirroring the original results prefix `$RR`, i.e. `$X/<rel>` holds what was `$RR/<rel>` | to confirm | `$RR` is read from the manifests (§6), never guessed. |
| PR-11 | A read-only bind mount facility (for example a container `-v "$X":"$RR":ro`) | to confirm | Needed for Stage 4. |
| PR-12 | Per run, the inputs `hrq` reads: `<runs>/run-<cfg>.log.gz`, `<runs>/<cfg>/<cfg>/0.sca`, and the configuration files for the node ids | to confirm | A missing `.sca` makes A2-8u NE, and the expectation fails with exit 5. |
| PR-13 | Bash, coreutils (`sha256sum`, `find`, `sort -z`, `xargs -0`), `awk`, `git`, `script`, `findmnt` | available (standard) | |

## 4. Stage 1: set-up and environment identity (no evidence)

### 4.1 Set-up

```bash
export Z="$(mktemp -d)"              # executor's work dir: outside the worktree, the evidence dir and the mount
cd "$Z"
script -q "$Z/console.log"           # complete console transcript of Stages 1-5 (kept outside $E until §9)
git clone https://github.com/MohamedSeliem/nascTime-5gtsn.git nasctime-src          # full history (PR-7)
git -C nasctime-src worktree add --detach "$Z/wpa1-validate" f3f68be696777e42b0717f949625855ddb475435
git clone --branch v1.8.1 https://github.com/Unipisa/Simu5G.git simu5g-1.8.1
cat > "$Z/vars.env" <<'EOF'
W="$Z/wpa1-validate"
C=f3f68be696777e42b0717f949625855ddb475435
R=<the original results prefix RR; the mount point of Stage 4>
X=<the extraction root (Stage 3); not the mount>
E=<a fresh evidence directory outside $Z/wpa1-validate and outside $X; must not exist>
export SIMU5G_ROOT="$Z/simu5g-1.8.1"
CHK="$W/simulations/m2/check"
PY="python3 -I -B"
EOF
```

`vars.env` holds the design §8.1 variables, plus `X`. Every stage script reads it and contains nothing else variable. The stage scripts are copied from this runbook into `$Z` unchanged and run with `bash`.

### 4.2 Environment identity and equivalence (X-4, R4)

X-4 has two parts, and both are required:

1. **The identity record** below.
2. **Before the first acceptance-bearing validation on a new environment: an approved G0-style verdict-equivalence record against the D-2 environment** (gate A-5).
   - Like the original G0, it is verdict equivalence, not a hash-identity claim.
   - This runbook does not define, produce or replace that record. Its scope for a read-only evaluation environment is the maintainer's decision (M-5).
   - **The identity record is not a substitute for it.**

The identity record follows the X-4 list. It is written by the Stage 2 script into `$E/environment/identity.txt`, after `$E` is created, as part of the same script:
- Python: version, `sys.executable`, and the sha256 of the resolved interpreter binary;
- OS: `uname -srm` and `/etc/os-release`;
- compiler: `cc --version`, or "not installed";
- OMNeT++ build id and INET version: from `opp_run -v` and the INET tree if present, otherwise "not installed (not used by these evaluations)";
- Simu5G: tag and `HEAD`;
- `git --version` and the coreutils version;
- for the reviewed code, the `C` commit and the four sha256 values of §1. These are the hashes of the libraries actually executed, which are pure Python at `C`.

`$E/environment/equivalence-ref.txt` names the approved A-5 record and gives its sha256.

## 5. Stage 2: P-0 (corrected, C-1) and gate B, before any access to evidence (R1)

Run as `bash "$Z/stage2-p0.sh"`. **Only exit 0 is GO.** Any other exit code stops the validation, and Stage 3 is not started.

```bash
#!/usr/bin/env bash
# Stage 2 - P-0 (design 8.1, corrected by C-1) and gate B. Reads only the worktree, Simu5G and $Z; never $R or $X.
set -u
. "$Z/vars.env"
stop() { echo "P-0 NO-GO: $*"; exit 1; }

test -z "${S5N_ADAPTER_VALIDATED+x}" || stop "S5N_ADAPTER_VALIDATED is set"                               # B-4
test "$(git -C "$W" rev-parse HEAD)" = "$C" && echo "P-0 commit OK" || stop "worktree HEAD is not C"       # B-2
test -z "$(git -C "$W" status --porcelain --untracked-files=all)" || stop "worktree not clean"
test "$(git -C "$SIMU5G_ROOT" rev-parse HEAD)" = 7477d2663644bbf78604267cba4fc113b4871ede && echo "P-0 Simu5G OK" || stop "Simu5G HEAD"
test -z "$(git -C "$SIMU5G_ROOT" status --porcelain --untracked-files=all)" || stop "Simu5G tree not clean"
(cd "$CHK" && sha256sum -c --strict --quiet) <<'EOF' || stop "expectation files or registry differ from the runbook"   # B-3
b73410549c6ac085b0cd82b3255307174153cb1fc8b6737a15bfb2c978a5b97b  expect/vn1.expect.json
5821d0e57adb352d8a68c8e11441e4f76467ed41a89c7bc025a4a74ca95a47e3  expect/vn2.expect.json
fe68ab9855e1574ca26709be12359c23be45f114dcc3f6eecc4d1c1683c31a8d  expect/vv1.expect.json
2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae  m2s72_fgo_registry.json
EOF
test ! -e "$E" && mkdir "$E" && echo "P-0 fresh evidence dir" || stop "E exists or cannot be created"     # B-6
mkdir "$E/p0" "$E/environment" "$E/gate" || stop "cannot create E subdirectories"

# B-1: environment identity (4.2); the equivalence reference is written by the executor before this script
{ python3 -c 'import sys; print("python", sys.version.replace("\n", " ")); print("executable", sys.executable)'
  echo "python binary sha256 $(sha256sum "$(readlink -f "$(command -v python3)")" | cut -d' ' -f1)"
  echo "uname $(uname -srm)"; cat /etc/os-release
  { cc --version 2>/dev/null | head -1; } || true; command -v cc >/dev/null || echo "cc not installed"
  command -v opp_run >/dev/null && opp_run -v 2>&1 | head -3 || echo "OMNeT++ not installed (not used by these evaluations)"
  echo "simu5g HEAD $(git -C "$SIMU5G_ROOT" rev-parse HEAD) tag $(git -C "$SIMU5G_ROOT" describe --tags --exact-match 2>/dev/null)"
  git --version; sha256sum --version | head -1
  echo "nascTime commit $C"; (cd "$CHK" && sha256sum expect/vn1.expect.json expect/vn2.expect.json expect/vv1.expect.json m2s72_fgo_registry.json)
} > "$E/environment/identity.txt" 2>&1 || stop "identity record"
test -s "$Z/equivalence-ref.txt" || stop "no approved G0-style equivalence record referenced (gate A-5)"
cp "$Z/equivalence-ref.txt" "$E/environment/equivalence-ref.txt" || stop "equivalence reference copy"

# B-5: every suite - real exit code, non-empty output, exact final line (expected lines: h4-first-task.md 5)
suite() {   # <suite> <expected final line> <isolated|plain>
  local t=$1 exp=$2 mode=$3 out="$E/p0/$1.out" err="$E/p0/$1.err" rc last
  if [ "$mode" = isolated ]; then (cd "$Z" && $PY "$CHK/$t") >"$out" 2>"$err"; rc=$?
  else (cd "$CHK" && python3 -B "$t") >"$out" 2>"$err"; rc=$?; fi
  echo "$rc" > "$E/p0/$t.rc"
  [ "$rc" -eq 0 ] || stop "$t exit code $rc"
  [ -s "$out" ] || stop "$t produced no output (missing result)"
  last=$(tail -n 1 "$out")
  [ "$last" = "$exp" ] || stop "$t final line '$last' is not '$exp'"
  echo "P-0 PASS $t rc=0 '$last'"
}
suite test_m2s72_e0vn21.py      "WP-A1 e0vn21 tests: 52 / 52 PASS, 0 FAIL" isolated
suite test_m2s72_a2.py          "A-2 tests: 18 / 18 PASS" plain
suite test_m2s72_a2probe.py     "A-2 probe tests: 11 / 11 PASS" plain
suite test_m2s72_a2v1.py        "10 / 10 PASS" plain
suite test_m2s72_gen.py         "generator negative tests: 67 PASS, 0 FAIL" plain
suite test_m2s72s5.py           "S5-1 tests: 38 / 38 PASS" plain
suite test_m2s72s5_2.py         "S5-2 tests: 28 / 28 PASS" plain
suite test_m2s72s5_n2.py        "S5 N = 2 tests: 19 / 19 PASS" plain
suite test_m2s72s5_smoke.py     "S5 smoke contract tests: 9 / 9 PASS" plain
suite test_m2s72_a21.py         "A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL" plain
suite test_m2s72_a21_fixture.py "A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL" plain
test "$(ls "$E"/p0/*.rc | wc -l)" -eq 11 || stop "not exactly 11 suite results"
test -z "$(git -C "$W" status --porcelain --untracked-files=all)" || stop "the suites modified the worktree"
test -z "$(git -C "$SIMU5G_ROOT" status --porcelain --untracked-files=all)" || stop "the suites modified Simu5G"

echo "GATE B: GO (B-1 ... B-6 met)" | tee "$E/gate/gate-b.txt"
exit 0
```

**Notes on the script:**
- The invocations are those of design §8.1: `$PY` (`python3 -I -B`) for the WP-A1 suite, run from `$Z`, outside the worktree; `python3 -B` from `$CHK` for the other ten.
- The expected lines are the approved ones (`h4-first-task.md` §5 and the I-9 line), unchanged.
- `$R` and `$X` are not referenced in this script.
- The executor writes `$Z/equivalence-ref.txt` (the name and sha256 of the approved A-5 record) before running it.

## 6. Stages 3 and 4: DR-13, the two methods kept apart (R3)

DR-13 (decision of 17 Nov 2026) and `authoritative-migration-status.md` §0.4 permit exactly two methods. **Original manifests are never rewritten, and evidence is never modified.**

| Method | Used for | Stage | Writes |
|---|---|---|---|
| **(b) in-memory prefix mapping** | **integrity verification** of the extraction against the original manifests (X-2a) | 3 | nothing in `$X`; results go to `$E/x2a/` |
| **(a) read-only mount at the original absolute prefix** | **evaluation** by the reviewed tools, unchanged (`hrq`, `xa`, `verify-manifest` in P-1 / P-3, the extractor) | 4 – 5 | nothing under `$R`; results go to `$E/<v>/` |

- **Neither method replaces the other.** A tool that refuses a mapped path is correct and is not weakened; method (a) is used instead.
- **Method validation (A-4) comes first.** Both methods must have been validated, with an approved record, before this evaluation. Stages 3 and 4 apply them; they do not validate them.

### 6.1 Stage 3: X-2a integrity of the extraction, method (b)

These commands are run interactively under the transcript. **Any non-zero exit code is a stop** (§8).

```bash
. "$Z/vars.env"; mkdir "$E/x2a"
# (1) each archive against its archive checksum manifest - the command distributed with the archives (PR-9)
<archive checksum verification command> > "$E/x2a/archives.txt" 2>&1; echo "X-2a archives rc=$?"            # expect 0

# (2) RR = the original results prefix, read from the manifests: every entry must lie under it
RR="$R"
for m in s5-smoke-1/m2/M2-S7.2a-s5smoke/records/M2S72-E0v-q0-f1.manifest.sha256 \
         s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256 \
         a2-nack-1/records/M2S72-E0vN-q0-one0-n2-f1_A2V1.manifest.sha256; do
  awk -v a="  $RR/" 'index($0, a) == 0 { bad++ } END { exit bad > 0 }' "$X/$m"; echo "X-2a prefix $m rc=$?"   # expect 0
  echo "$m entries $(wc -l < "$X/$m") sha256 $(sha256sum "$X/$m" | cut -d' ' -f1)" >> "$E/x2a/manifests.txt"
  # in-memory mapping: the prefix is substituted in the stream; no modified manifest is written anywhere
  $PY "$CHK/m2s72s5_lib.py" verify-manifest \
      <(awk -v a="  $RR/" -v b="  $X/" '{ i = index($0, a); print substr($0, 1, i - 1) b substr($0, i + length(a)) }' "$X/$m") \
      > "$E/x2a/$(basename "$m").verify.txt"; echo "X-2a verify $m rc=$?"                                       # expect 0
done

# (3) the A2-V1 seal: relative paths, no mapping needed
test "$(sha256sum "$X/a2-nack-1-evidence.sha256" | cut -d' ' -f1)" = 3d00ef8ebc2bd03e18e2d4a986a75771b3bcac8e54fae402d742fd19c5749ca0; echo "X-2a seal identity rc=$?"
(cd "$X" && sha256sum -c --strict a2-nack-1-evidence.sha256) > "$E/x2a/seal.txt" 2>&1; echo "X-2a seal rc=$?"  # expect 0
echo "DR-13 method (b), in-memory prefix mapping RR=$RR -> X=$X, for integrity verification" > "$E/x2a/method.txt"
```

**Why the tool is used this way:**
- The accepted `verify-manifest` checks every entry's size and sha256, as the DR-13 rule requires. It also checks the decompressed hash of tier-B `.gz`-retained files.
- The `awk` stream form is the §0.4 substitution, done by literal prefix rather than by regex.
- Exit 0 = every entry verified; 1 = a mismatch.
- Checked here with dummy files only, never with evidence: a mapped stream verifies (exit 0), and a changed file gives `MANIFEST MISMATCH` (exit 1).

### 6.2 Stage 4: the read-only mount at the original prefix, method (a)

```bash
# the mount is made by the executor's container or host tooling, for example:  -v "$X":"$RR":ro
. "$Z/vars.env"
findmnt -no OPTIONS --target "$R" | tr ',' '\n' | grep -qx ro; echo "M-ro rc=$?"                              # expect 0
touch "$R/.wtest" 2>/dev/null; test $? -ne 0; echo "M-nowrite rc=$?"                                          # expect 0 (write refused)
echo "DR-13 method (a), read-only mount of $X at $R, for evaluation" > "$E/x2a/mount.txt"
findmnt --target "$R" >> "$E/x2a/mount.txt"
```

## 7. Stage 5: the validations (design §8.2 – §8.4, verbatim)

Each block is run interactively under the transcript, with `. "$Z/vars.env"` sourced first. After every command, the executor applies the stop rules of §8 before typing the next one.

### 7.1 V-N1: N = 1 smoke `M2S72-E0v-q0-f1`, seed 0

**Inputs:**
- `$N1/runs/run-M2S72-E0v-q0-f1.log.gz`, `$N1/runs/M2S72-E0v-q0-f1/M2S72-E0v-q0-f1/0.sca` and the configuration files;
- `$N1/records/M2S72-E0v-q0-f1.manifest.sha256`;
- `$CHK/expect/vn1.expect.json`.

```bash
N1="$R/s5-smoke-1/m2/M2-S7.2a-s5smoke"
mkdir "$E/vn1"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-before.txt"; echo "P-1 rc=$?"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/hrq" --expect "$CHK/expect/vn1.expect.json"; echo "V-N1 hrq rc=$?"   # expect 0
$PY "$CHK/check_m2s72_s5n2.py" xa "$N1/runs" M2S72-E0v-q0-f1 "$E/vn1/xa"; echo "V-N1 xa rc=$?"                                              # unchanged reference
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N1/records/M2S72-E0v-q0-f1.manifest.sha256" > "$E/vn1/integrity-after.txt"; echo "P-3 rc=$?"
cmp "$E/vn1/integrity-before.txt" "$E/vn1/integrity-after.txt" && echo "P-3 identical"
```

**Expected results:**
- P-1 = 0 and P-3 = 0; both files read `manifest verified`; then `P-3 identical`.
- `hrq --expect` = **0**. `$E/vn1/hrq/` holds `a21-…{txt,json}`, `hrq-…{txt,json}` and `hrq-M2S72-E0v-q0-f1.expect.txt`, which ends `ALL EXPECTATIONS MET`.
- `xa` = 0 by the tool contract. No expectation is declared for it (M-7).

**Declared values** (design §8.2):
- A-1: a1a 11 697; the other counts 0; PU-4 PASS, reported unchanged.
- A-2.1 rows:
  - A2-0, A2-0s, A2-1, A2-2, A2-3, A2-6, A2-7, A2-8 and A2-9 PASS;
  - A2-5 PASS or NX;
  - A2-4a / b / c NX.
- Verdicts VALID / VALID.
- MAP-UE, C-0, PU-4h, PU-4o UE 0 and A2-8u UE 0 PASS.
- Held features: {single-candidate ACK attribution}, plus "inserted in the last TTI" iff its count > 0.
- Composed verdict HELD FOR REVIEW.

### 7.2 V-N2: N = 2 smoke `M2S72-E0vN-q0-one0-n2-f1`, seed 0

**Inputs:** as V-N1, under `$N2`, for this configuration, with `vn2.expect.json`.

```bash
N2="$R/s5-n2-1/m2/M2-S7.2a-s5smoke-n2"
mkdir "$E/vn2"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-before.txt"; echo "P-1 rc=$?"
$PY "$CHK/check_m2s72_s5n21.py" hrq "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/hrq" --expect "$CHK/expect/vn2.expect.json"; echo "V-N2 hrq rc=$?"   # expect 0
$PY "$CHK/check_m2s72_s5n2.py" xa "$N2/runs" M2S72-E0vN-q0-one0-n2-f1 "$E/vn2/xa"; echo "V-N2 xa rc=$?"
$PY "$CHK/m2s72s5_lib.py" verify-manifest "$N2/records/M2S72-E0vN-q0-one0-n2-f1.manifest.sha256" > "$E/vn2/integrity-after.txt"; echo "P-3 rc=$?"
cmp "$E/vn2/integrity-before.txt" "$E/vn2/integrity-after.txt" && echo "P-3 identical"
```

**Expected results:**
- P-1 / P-3 = 0, and the integrity files are identical.
- `hrq --expect` = **0**.
- `xa` = 0: XA-6 is NOT EVALUATED when A-1 is not exact, which still exits 0 (M-7).

**Declared values** (design §8.3):
- A-1: a1a 9 718, a1b 2 476, ambiguous 768, re-insert 768, orphan 0; **PU-4 FAIL retained verbatim**.
- A-2.1 (predicted counts, PC-A2-N2, never confirmed on genuine output):
  - 12 194 single-candidate lines;
  - 384 certified exchangeable groups (768 lines);
  - A2-4a / b / c NX; A2-5, A2-7 and A2-8 PASS;
  - verdicts VALID / VALID.
- MAP-UE, C-0 and PU-4h PASS; PU-4o PASS ×2; A2-8u PASS ×2.
- Agreement: disagree = 0, and all 768 A-1-unattributed lines are `exchangeable`.
- Held features: {single-candidate ACK, exchangeable ACK groups (2 candidates)}, plus "inserted in the last TTI" iff > 0.
- Composed verdict HELD FOR REVIEW.

### 7.3 V-V1: A2-V1 run `M2S72-E0vN-q0-one0-n2-f1_A2V1` (sealed)

**Inputs:**
- the sealed tree under `$R`: the seal `a2-nack-1-evidence.sha256`, the 33 sealed records and the 58-entry raw manifest;
- `$R/a2-nack-1/runs` with the log, the `.sca` and the configuration files;
- `vv1.expect.json`.

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

**Expected results:**
- **P-1 extract = 0**, followed by `P-1 reproduces the F3 fixture`.
- **`hrq --expect` = 0.**
- **P-3 extract = 0**, followed by `P-3 reproduces the F3 fixture`.
- Extractor exit codes:
  - 10 = E-0 STOP, nothing written;
  - 11 – 14 = an integrity gate failed (E-1 … E-3, E-7), leaving `FAILED.txt` and `.partial` outputs.
- Each `fx-*/` directory holds `steps.txt`, the fixture, its `.sha256`, the metadata file and **its own `SHA256SUMS`**. These are covered by §9.

**Declared values** (design §8.4):
- Per-node accounting, exactly as in the S1 closure §3:
  - node 2049: 11 702 / 11 702 / 11 697 / 11 697 / 0 / discarded 0 / censored 5;
  - node 2050: 1 265 / 1 409 / 1 408 / 1 264 / 144 / retransmissions 144 / discarded 0 / censored 1.
- 371 exchangeable groups (742 lines); 40 resolved by retransmission; 15 bound; 129 handles retired; unresolved `[]`; end states `{censored: awaiting feedback: 6}`.
- A2-8 PASS; `f1d-i` VALID; `full` INCOMPLETE (A2-4c NE).
- A2-8u: 0 / 1 and 0.10227272727272728 / 1.1139240506329113. PASS ×2.
- MAP-UE, C-0 and PU-4h PASS; PU-4o PASS ×2.
- A-1 reported, with no expectation declared.
- Held features: {single-candidate ACK, exchangeable ACK groups (2 candidates)}, plus "NACK resolved: single candidate" iff > 0.
- Composed verdict HELD FOR REVIEW.
- **The A2-V1 verdict stays NOT ACCEPTED.**

## 8. Stop, mismatch and retry rules (proposed; gate A-6 requires their approval)

| Event | Action |
|---|---|
| Gate A item unmet | NO-GO. Nothing is set up or accessed. |
| Stage 2 exits non-zero | NO-GO. Stop. `$E` keeps the P-0 outputs and is finalised (§9) as a NO-GO record. Genuine evidence was never accessed. |
| Stage 3 or 4: any non-zero exit code (archive verification, prefix check, `verify-manifest`, seal identity or seal check, `M-ro`, `M-nowrite`) | Stop before any evaluation. Finalise `$E` (§9) and report. |
| P-1 of a validation is non-zero, or its extract is not 0 | Do not evaluate that run. Stop the session. Finalise and report. |
| `hrq --expect` exits **5** (expectation mismatch) | A finding. Do not re-run. Run that validation's P-3 and `cmp`, then continue with the next validation. `hrq-<cfg>.expect.txt` already lists every declared value against the evaluated one. |
| `hrq` exits 2, or any other code than 0 or 5 | Run that validation's P-3 and `cmp`, then stop the session. Finalise and report. |
| `xa` exits non-zero | Record it as found (non-gating, M-7). Continue. |
| P-3 is non-zero, `cmp` differs, or `reproduces` is not printed after P-3 | An integrity failure. Stop the session. Finalise and report. |
| Any failure | No retry, no clean-up, no relabelling (X-6). Partial outputs stay as found. |
| A fresh attempt | Only with the maintainer's written approval, in a **new** `$E`. The failed `$E` is preserved, finalised and reported with it. |

**Recording deviations:**
- Each deviation is entered in `$E/<v>/findings.md` before §9. Each entry gives the declared value, the evaluated value, the record file and line, and "reported as found".
- **Expectation files are never modified.** Gate B pins their hashes, and §9 re-checks them.
- A discrepancy is a finding against the expectation **or** the implementation. The maintainer decides which; any correction is a separate reviewed change at a new commit, followed by a new validation.

## 9. Stage 6: evidence finalisation (corrected P-4, C-2; R2)

This is run after Stage 5 completes, or after any stop from Stage 2 onwards. The sequence is fixed:

| Step | Action |
|---|---|
| F-1 | End the console transcript (`exit` from `script`). Start a second transcript, `script -q "$Z/finalisation.log"`, for F-2 … F-9. |
| F-2 | Re-check the expectation files and registry (the gate-B `sha256sum -c` block of §5, run again) and `git -C "$W" status --porcelain --untracked-files=all` (empty). Write both results to `$E/supplementary/post-checks.txt`. |
| F-3 | Copy the procedure and the console transcript into `$E`: `mkdir "$E/procedure"`, copy `"$Z/vars.env"`, `"$Z/stage2-p0.sh"` and `"$Z/equivalence-ref.txt"` into it, and copy `"$Z/console.log"` to `"$E/console.log"`, refusing to overwrite. |
| F-4 | Preconditions: no top-level `SHA256SUMS` or `SHA256SUMS.final`; only regular files and directories (`find "$E" ! -type f ! -type d` prints nothing); every supplementary record (`environment/`, `gate/`, `x2a/`, `supplementary/`, `findings.md`) is already written. **Nothing may be added to `$E` after F-5 except the F-8 record.** |
| F-5 | **The inventory, including nested checksum files:**<br>`(cd "$E" && find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.final -print0 \| LC_ALL=C sort -z \| xargs -0 sha256sum) > "$E/SHA256SUMS"` |
| F-6 | Completeness: the number of lines in `SHA256SUMS` equals `find . -type f ! -path ./SHA256SUMS ! -path ./SHA256SUMS.final \| wc -l`. Where those stages ran, it contains `./vv1/fx-before/SHA256SUMS`, `./vv1/fx-after/SHA256SUMS`, `./environment/identity.txt`, `./environment/equivalence-ref.txt`, `./gate/gate-b.txt`, `./x2a/method.txt`, `./x2a/mount.txt`, `./console.log` and `./procedure/stage2-p0.sh`. |
| F-7 | Verification: `(cd "$E" && sha256sum -c --strict --quiet SHA256SUMS)` exits 0. Each nested sum also verifies: `(cd "$E/vv1/fx-before" && sha256sum -c --strict --quiet SHA256SUMS)`, and the same for `fx-after`. |
| F-8 | **The final checksum record:** `(cd "$E" && sha256sum SHA256SUMS) > "$E/SHA256SUMS.final"`. It covers `SHA256SUMS`, which covers every other file, including the supplementary records and the nested sums. |
| F-9 | Seal locally with `chmod -R a-w "$E"`. End the finalisation transcript. |
| F-10 | Record the content of `SHA256SUMS.final` **at once**, at sealing time (X-5), in the validation record outside `$E`, together with the sha256 of `"$Z/finalisation.log"`. Then transfer `$E` and `finalisation.log` to the private evidence repository with checksums (X-5). |

**How the corrected P-4 differs from design §8.1:**
- `! -name SHA256SUMS` became `! -path ./SHA256SUMS`, so nested `SHA256SUMS` files are included.
- `SHA256SUMS.final` is added, and the transcripts are now covered.
- The X-4 identity is now `$E/environment/identity.txt` (§4.2), written in Stage 2 so that it is inside the inventory.

## 10. Evidence for VG-0 … VG-3 (design §8.5)

| Gate | Condition | Evidence |
|---|---|---|
| VG-0 | P-0 … P-4 complete; integrity identical before and after | `gate/gate-b.txt` (GO); `p0/*.{out,err,rc}` (11 suites); `x2a/*` (method (b) results and the method statement); `x2a/mount.txt` (method (a)); `vn1/` and `vn2/integrity-{before,after}.txt`, identical; `vv1/fx-{before,after}/`; `environment/identity.txt` with `equivalence-ref.txt` (the approved A-5 record); `console.log`; `SHA256SUMS`, `SHA256SUMS.final` and their F-7 verification; the A-4 DR-13 validation record cited. |
| VG-1 | `hrq --expect` exit 0, every declared expectation met exactly | `rc=0` in `console.log`; `hrq-<cfg>.expect.txt` ending `ALL EXPECTATIONS MET`, with `n / n MATCH` (35 / 39 / 56 declared keys). |
| VG-2 | No wrapper output relabels a historical result | `hrq-<cfg>.{txt,json}`: the A-1 PU-4 row is verbatim under `historical` (PASS for V-N1, **FAIL** for V-N2) and never gates. A-1 values appear only under `historical`. No V-V1 output restates or changes the A2-V1 verdict. |
| VG-3 | The maintainer accepts the record | The validation record, citing: `C`; the four sha256 values; the archive identities; gate A evidence A-1 … A-6; `SHA256SUMS.final`; the findings. It is stored with checksums (X-5) and has the status "executed, not accepted" until accepted (X-9). |

**After VG-3 (outside this runbook):**
- S5-2-D2 (V-N1 and V-N2);
- the registry admissions of design §8.5, each a separate reviewed change.

## 11. Decisions that require maintainer approval

| ID | Decision | Gate |
|---|---|---|
| M-1 | Designate the independent executor, and who records and transfers the evidence | A-1 |
| M-2 | Confirm `C` and the expectation files (the four sha256 values) | A-2 |
| M-3 | Authorise access to the three archives for the executor | A-3 |
| M-4 | Validate DR-13 methods (a) and (b) and approve the validation record, or identify an existing one | A-4 |
| M-5 | Define the scope of, and approve, the G0-style verdict-equivalence record for the executor's environment against D-2 (X-4) | A-5 |
| M-6 | Approve the stop, mismatch and retry rules of §8, as proposed or amended | A-6 |
| M-7 | The status of `xa` (no declared expectation; proposed non-gating, recorded as found) | §8 |
| M-8 | Confirm the archive checksum verification command (PR-9) and the extraction layout (PR-10) | Stage 3 |
| M-9 | Whether design §8.1 is revised to carry corrections C-1 and C-2 | — |
| M-10 | After VG-3: S5-2-D2 and the registry admissions | — |

## 12. What was checked while preparing (no evidence used, nothing executed against evidence)

- Every design §8 command names a tool and mode that exists at `C`, with the same argument order. Each tool imports under `python3 -I -B` from an unrelated directory.
- `hrq` and the extractor refuse an existing output directory; `xa` creates its own directory. The `hrq` name guard admits the V-N1 and V-V1 names, and V-N2 is an E0v-N name.
- The P-0 `PIPESTATUS` defect (C-1) was reproduced in Bash with a dummy command.
- **The Stage 2 script, extracted verbatim from §5, was run on public code only.** It used a detached worktree at `C` and Simu5G at `7477d266…`, with `R` and `X` set to non-existent paths and a placeholder equivalence reference labelled TEST ONLY:
  - all 11 suites gave their exact lines, and the script printed `GATE B: GO` with exit 0;
  - each of the following was NO-GO with exit 1: `S5N_ADAPTER_VALIDATED` set; an existing `$E`; a wrong expected line; an untracked file in the worktree; a missing equivalence reference; a dummy suite with the right line but exit 3; a dummy suite with empty output.

  This is a check of the procedure, not a P-0 of any validation.
- Method (b), the stream form, was exercised with dummy files: verified (0) and changed (1).
- F-5 … F-8 were exercised on a dummy tree:
  - the nested `fx-*/SHA256SUMS` are listed in the inventory;
  - the F-6 count matches, and F-7 verifies;
  - a change to a nested `SHA256SUMS` after F-5 is detected (exit 1).
- The extractor writes its own `SHA256SUMS` in each output directory (C-2).
