# WP-A1 — Independent validation runbook: V-N1, V-N2, V-V1 (prepared, not executed)

**Status: revision 4, 23 November 2026, for independent review (step 141). Nothing has been executed against genuine evidence.**

**Revision history:**
- Revision 1: `e1b5a76`.
- Revision 2: `bb39906`, the step-135 corrections R1 – R5.
- Revision 3 (`151e164`) closes the step-137 / step-139 gaps:
  - the procedure is now committed, fail-closed scripts in `docs/migration/wp-a1-validation/`, so the stop rules no longer depend on the operator;
  - exact release SHA-256 verification and extraction commands (§5);
  - the DR-13 validation protocol (§6) and the G0-RO comparison against D-2 (§7), each with its approval record;
  - the readiness of the archived inputs as derived from the reviewed code (§8.1);
  - the resolution of every fail-open point found (§11).
- Revision 4 (this one), the step-141 corrections:
  - Stage 6 gives an explicit integrity and acceptance-eligibility result; failed evidence is preserved, never eligible (§8);
  - tests of that behaviour, the approvals, the extractor and the comparator, plus a Docker integration test of the whole host / container sequence on dummy data (§13);
  - the G0-RO references are reviewed against the committed D-2 records, with source classes and an explicit coverage record (§7);
  - the gate-A references are now signed approval statements verified against the maintainer's key, not populated text files (§3).

**Unchanged:**
- the design (`wp-a1-a21-e0vn-wrapper-design.md`, revision 2.1, `57a80ca`);
- the reviewed implementation `C`, the expectation files and the registry;
- every V-N1 / V-N2 / V-V1 argument vector of design §8.2 – §8.4;
- the corrections C-1 (gated P-0) and C-2 (corrected P-4) of revision 2.

**Architecture:** option C, approved at step 139.
- An independent, executor-operated, ephemeral host.
- Each stage runs in a fresh **network-less** container from an image pinned by digest, with exactly the mounts of its profile, through `host-stage.sh`.
- No GitHub Actions, no secret in any workflow, no publication of evidence.

**Roles and restrictions:**
- The executor is designated by the maintainer (X-1); it is never the development agent.
- Read-only evaluations only. No simulation.
- `S5N_ADAPTER_VALIDATED` is never set, and every stage refuses to run if it is set.

## 1. Fixed identities

| Item | Value |
|---|---|
| Reviewed implementation `C` | `f3f68be696777e42b0717f949625855ddb475435` |
| Procedure commit `D` | the commit of this runbook revision, **approved by the maintainer in gate A**. The scripts are taken from `D` by `h1-setup.sh`. |
| Simu5G | 1.8.1, `7477d2663644bbf78604267cba4fc113b4871ede`, unmodified |
| Expectation files and registry (sha256) | `vn1` `b7341054…a97b`, `vn2` `5821d0e5…47e3`, `vv1` `fe68ab98…1a8d`, registry `2bb539cd…b3ae`. Full values in `stage2-p0.sh`. |
| Original results prefix `R` | `/mnt/nasctime-results` |
| A2-V1 seal; F3 fixture | `3d00ef8e…49ca0` (33 records); `cfb05ff7…6e65b` |
| A2-V1 public pins, from `fixtures/a2v1-first-chain.meta.json` at `C` | manifest `3e7a78f5…3f41`, log `84320fb5…3873`, `0.sca` `3bdcc9fc…7db1`, node ids {0: 2049, 1: 2050} |
| Container image | Python ≥ 3.11 with git, coreutils, `awk`, `findmnt`, `ssh-keygen` (OpenSSH ≥ 8.2, for `-Y verify`). **Pinned by digest.** The digest is the one the approved G0-RO record covers. The Docker integration test used `python:3.13@sha256:9ffe84122ce74ebdffe2e0e6b946c9dd95d0bf3463f6eb1006b4dc6fefe36d01` (Python 3.13.18, the tier-0 version); that is a test choice, not an approval. |

**Script pins at `D`** (sha256; `h1-setup.sh` exports the scripts from `D`, so these are for the reviewer):

| File | sha256 |
|---|---|
| `common.sh` | `5212807ab3ad3c3d74a46db3596e8fd7bff25b65dc1c66700627a3e9e2421ea6` |
| `dr13-validate.sh` | `1362175d3bcd357f2591965a86bf9fe4c1a987cf9f30e6db5f76f5fccb6d8683` |
| `extract_checked.py` | `00190e4e9d0a9cb0da25d9ea9fdd23d9490d9770f53dd853a1f6ededec257b2d` |
| `g0ro-run.sh` | `6d65c2df53175bfb2dee3c4bffb5802323363152a401e1cced6b038f01a72a6b` |
| `g0ro_compare.py` | `9641108c5237b4d74d5ac43ba9e51248004e03e81fd25270cdf1adbae2e0c270` |
| `h1-setup.sh` | `c93f4b63dc21b2f648baeb428b31ca2f47830d74f2fa5bfe00c53cbdd17ec763` |
| `h3-release.sh` | `24aea1edb475ae8983796a55fda23c49d927fdb81b384cff21d3255804ff221a` |
| `host-stage.sh` | `7ef9309f1ed3882e631bc84a5a8da17434b187e7bc4177db37a13e110cd79551` |
| `stage2-p0.sh` | `ed7981e2aab797ea131946f54f636079c15c705fdd7f6c86383f0bfd280688b5` |
| `stage3-x2a.sh` | `f4fcf74b1fe78462085f69e95f71c22251983fa8c3e1dec323944f80f0529827` |
| `stage4-mount.sh` | `c47295bb5257f66ea5aea115748d6ec3a9d7305e338d3af73b9455c91ab34a8f` |
| `stage5-validate.sh` | `a03097c89a4b354f69511c8c6e66739ea4e70335c1f76c8e1c61e19ba649ce9e` |
| `stage6-finalise.sh` | `939e0e9aa0d2c93eb1eb0d863231ded4cd21cf2d7b563e03ac66a3a32b8226fb` |
| `vars.env.template` | `c98fd08c97077b0e5bf663b89cf9cf0ae62fdf5bb027427d311ac77f3611934a` |
| `tests/docker-integration.sh` | `497cb0652a1e5bc39380cc2b576d485160ba7c4fee98a5b9a75e527dfcaa207a` |
| `tests/lib.sh` | `8426124082888566b66483e0717509fd439886ddf61442fe7d6a29088e0e8cbc` |
| `tests/run-all.sh` | `a63ee53a1b85fe1b1d627fbfe317527bd5859dcb3023721947834cca2ff030d2` |
| `tests/test-approvals.sh` | `ed5d20585a10ff9ef711a53b372e21ef547e2363cde8affc4e6b67bfcda5da3e` |
| `tests/test-extract.sh` | `63fe47c412fce2dadd9291de695fdc1748a736725cea14c7ce410ce3019b3d2a` |
| `tests/test-g0ro-compare.sh` | `b79b64007577c0a4a81eba5f0a577b59da93b580770329fc57a49ce43a07438e` |
| `tests/test-stage6.sh` | `3161fa1c523ed11b51bc713ecea5ef0de3b224ebca143124f99ed3abc0021534` |

## 2. Two sessions, one order

| Session | Purpose | Steps |
|---|---|---|
| **Q, qualification** | Produce the two records gate A needs. No WP-A1 validation. | H-1 → H-3 `qualification` → DR-13-V (§6) → G0-RO (§7) → the maintainer approves both records |
| **V, validation** | V-N1, V-N2 and V-V1 | **a fresh `$Z` and a fresh `X`** → H-1 → **Stage 2 (P-0, gate B)** → H-3 `validation` → Stage 3 → Stage 4 → Stage 5 → Stage 6 |

In session V, nothing reads the evidence before gate B is GO:
- Stage 2 refuses to run if `R`, `X` or `REL` is visible.
- H-3 `validation` refuses to run without gate B GO.

Every stage is single-attempt: each refuses an existing output directory.

| Step | Script | `host-stage.sh` profile | Network | Evidence visible |
|---|---|---|---|---|
| H-1 | `h1-setup.sh <D>` (on the host) | — | **yes** (clone only) | no |
| Stage 2 | `stage2-p0.sh` | `p0` | no | **no (checked)** |
| H-3 | `h3-release.sh qualification\|validation` | `release` | no | archives read-only, extraction into a fresh `X` |
| DR-13-V (b) | `dr13-validate.sh b` | `mapped` | no | `X` read-only; **no mount at `R` (checked)** |
| DR-13-V (a) | `dr13-validate.sh a` | `mounted` | no | `X` read-only at `X` and at `R` |
| G0-RO | `g0ro-run.sh` | `mounted` | no | read-only |
| Stage 3 | `stage3-x2a.sh` | `mapped` | no | `X` read-only; **no mount at `R` (checked)** |
| Stage 4 | `stage4-mount.sh` | `mounted` | no | read-only |
| Stage 5 | `stage5-validate.sh` | `mounted` | no | read-only |
| Stage 6 | `stage6-finalise.sh` | `final` | no | no |

Every step's exit code is the script's own: `host-stage.sh` uses `script -e`. **Only exit 0 continues.** The one exception is Stage 5 exit 3 (completed with findings), which continues to Stage 6 only.

## 3. GO / NO-GO gate

GO requires every item. **Any unmet item is NO-GO.**

### Gate A: administrative, before session V — signed approval statements

Every gate-A item is a **statement signed by the maintainer**. Verification is mechanical, by `ssh-keygen -Y verify` against `$Z/approvals/allowed_signers`: principal `wpa1-maintainer`, namespace `wpa1-approval`.
- The executor obtains the maintainer's public key **out of band**, for example from the maintainer's published SSH keys, confirmed through a second channel. Its fingerprint is recorded in the evidence (`environment/approver-key-fingerprint.txt`).
- **The development agent never holds the signing key.**

A statement is refused if any of these hold:
- it is unsigned, or signed by another key or in another namespace;
- it was altered after signing;
- it is malformed, has a duplicate key, or is not `decision=APPROVED`;
- it is for another gate.

For A-4 and A-5:
- the approved record itself must be in `$Z/records/` with the signed sha256;
- both must name the same procedure commit as statement A.

**A populated text file can no longer satisfy a gate.**

| # | Item | Signed statement (`$Z/approvals/`) | Checked by |
|---|---|---|---|
| A-1 | Designated independent executor | `gate-a.txt`: `executor=` | `gate_a` (H-1, H-3, DR-13-V, G0-RO, Stage 2) |
| A-2 | Reviewed commit, procedure commit, expectation files | `gate-a.txt`: `reviewed_commit=C`, `docs_commit=D`, `vn1_sha256`, `vn2_sha256`, `vv1_sha256`, `registry_sha256`. These must equal the fixed values. | `gate_a`; `h1-setup.sh` (D) |
| A-3 | Access to the three archives | `gate-a.txt`: `access=authorised`, `release_sums_sha256=`, three `archive=` lines | `gate_a`; H-3 |
| A-4 | DR-13 approved and validated | `a4-dr13.txt`: `gate=A-4`, `subject_file`, `subject_sha256`, `docs_commit=D` + the record in `$Z/records/` | `gate_a45` (Stage 2) |
| A-5 | Environment equivalence (X-4) | `a5-g0ro.txt`: `gate=A-5`, `subject_file`, `subject_sha256`, `image_digest`, `docs_commit=D` + the record. **An identity statement or the regression suites alone are not sufficient.** | `gate_a45`; Stage 2 checks the running image digest |
| A-6 | Stop, mismatch and retry rules | `gate-a.txt`: `rules=approved` | `gate_a` |

**Statement format:**
- the first line is `format=wpa1-approval/1`;
- then one `key=value` per line;
- `gate=`, `decision=APPROVED`, `docs_commit=` and `date=` are required.

The maintainer signs it with `ssh-keygen -Y sign -f <private key> -n wpa1-approval <statement>`. Session Q needs `gate-a.txt` only; session V needs all three.

### Gate B: technical, decided by `stage2-p0.sh`

The same checks as revision 2:
- B-1 environment identity;
- B-2 clean worktree at `C` and Simu5G at its pin;
- B-3 the four sha256 values;
- B-4 `S5N_ADAPTER_VALIDATED` unset;
- B-5 11 suites with real exit code, non-empty output and exact line;
- B-6 a fresh `E`.

Additionally:
- the evidence must not be visible;
- the three signed gate-A statements (and the two approved records) must verify;
- the image digest must be the one the G0-RO record covers.

**GO is only the script's exit 0**, together with the line `GATE B: GO (B-1 ... B-6 met)` in `$E/gate/gate-b.txt`.

## 4. H-1: set-up on the host (network, no evidence)

```bash
export Z="$(mktemp -d)"                                    # fresh for each session
git clone https://github.com/MohamedSeliem/nascTime-5gtsn.git "$Z/nasctime-src"
mkdir "$Z/approvals" "$Z/records"   # allowed_signers (the maintainer's public key, out of band); the signed statements
                                    # and their .sig files; session V: the approved DR-13 and G0-RO records
D=<the approved procedure commit, 40 hex>
git -C "$Z/nasctime-src" show "$D:docs/migration/wp-a1-validation/vars.env.template" > "$Z/vars.env"
#   edit $Z/vars.env: replace the two <...> placeholders (X, REL); every other line stays as given
git -C "$Z/nasctime-src" show "$D:docs/migration/wp-a1-validation/h1-setup.sh" > "$Z/h1-setup.sh"
bash "$Z/h1-setup.sh" "$D"                                 # exports the scripts from D, worktree at C, Simu5G at its pin
docker pull "<image>@sha256:<digest>"                      # the digest of the approved G0-RO record (session V)
export IMG="<image>@sha256:<digest>"
```

**What `h1-setup.sh` and `common.sh` refuse:**
- a gate-A statement that does not verify (§3), and a `D` other than the one it approves;
- a clone without the history the pin tests need;
- an existing worktree or Simu5G tree;
- a Simu5G HEAD other than the pin;
- a `vars.env` with a placeholder;
- a relative path;
- overlapping `X` / `REL` / `$Z`;
- an `R` other than `/mnt/nasctime-results`;
- a `C` other than the reviewed commit.

## 5. H-3: release SHA-256 verification and extraction layout (exact, fail-closed)

```bash
bash "$Z/scripts/host-stage.sh" h3-release.sh release "$Z/console.log" qualification   # session Q
bash "$Z/scripts/host-stage.sh" h3-release.sh release "$Z/console.log" validation      # session V, after gate B
```

`h3-release.sh` runs in a container with `REL` read-only and the parent of `X` read-write. It does, in order:
1. **Checksum list identity.** `sha256(REL/SHA256SUMS)` must equal `release_sums_sha256` from the approval record.
2. **Exactly the three approved archives.** Each name is listed **exactly once** in `SHA256SUMS`, is a plain file name and is a regular file. The three lines are verified with `sha256sum -c --strict`. There is no `--ignore-missing`, and a missing, extra or duplicated name is a stop.
3. **Extraction** into a **fresh** `X` by `extract_checked.py`, archive by archive. Formats: `.tar`, `.tar.gz`, `.tgz`, `.tar.xz`, `.tar.bz2`, `.zip`; anything else is refused.
   - **Layout rule:** after removing one optional stored prefix `mnt/nasctime-results/` (all members or none), every member is one of the evidence seals or lies under `s5-smoke-1/`, `s5-n2-1/` or `a2-nack-1/`. Then `X/<rel>` holds what was `/mnt/nasctime-results/<rel>`.
   - **Refused:** absolute or `..` names, links, devices, members outside the layout, duplicates, and any member that would overwrite an existing file (`open(…, "x")`).
   - **Each member's bytes** are hashed while written and re-hashed from disk, with a size or zip CRC check. They are recorded in `members-<archive>.txt` (sha256, size, path), and the member's mtime is kept.
4. **Afterwards:** the archives are verified again (unchanged), `X` is made read-only, and `X` is checked to hold only regular files and directories.

**Retaining the originals:**
- The archives are never written: they are mounted read-only and re-verified.
- No manifest is rewritten.
- The extracted bytes equal the members, and the original manifests then verify them (Stage 3).

**Exercised here on dummy archives only:**
- valid tar, tar.gz and zip, with and without the stored prefix: extracted;
- refused (1): traversal, absolute name, tar symlink, zip symlink, member outside the layout, mixed prefix, a member overwriting another archive's file;
- refused (2): unknown format;
- in H-3: an unapproved `SHA256SUMS`, a second attempt, a qualification run with `E` present, and a validation run without gate B were each refused.

## 6. DR-13 validation protocol (session Q) and its approval record

**Purpose:** validate both approved methods on the recovered archives before any independent evaluation (DR-13 decision, X-2a). No WP-A1 code runs. Output goes to `$Z/dr13-validation/mode-{b,a}/`.

```bash
bash "$Z/scripts/host-stage.sh" dr13-validate.sh mapped  "$Z/console.log" b
bash "$Z/scripts/host-stage.sh" dr13-validate.sh mounted "$Z/console.log" a
```

| ID | Method | Check | Pass condition |
|---|---|---|---|
| DV-b1 | (b) in-memory mapping, **no mount at `R` (checked)** | each of the three original manifests: every line `<sha256>  <size>  /mnt/nasctime-results/…`; verified by the accepted `m2s72s5_lib.py verify-manifest` on the prefix-substituted **stream** (process substitution; no manifest written) | exit 0 and `manifest verified`, ×3 |
| DV-b2 | (b) | negative control on a **copy**: the smallest entry of the N = 1 manifest is copied to a scratch tree. The unmodified copy verifies through a one-line mapped stream; after one byte is changed it does not. The copy is then deleted. | 0, then 1 |
| DV-b3 | (b) vs (a) | a fail-closed tool refuses a mapped root: the accepted extractor with `--results-root X` must **not** succeed (E-3: the manifest entries lie under `/mnt/nasctime-results`) | exit ≠ 0. The tool is not weakened; method (a) is used for it. |
| DV-a1 | (a) read-only mount | `findmnt` shows `ro`; not writable (`test ! -w`, nothing created); `find` of the mount equals `find` of `X` (type, size, path) | all hold |
| DV-a2 | (a) | the three **original** manifests verify through the mount with the accepted tool, unchanged | exit 0 ×3 |
| DV-a3 | (a) | the accepted extractor on `--results-root /mnt/nasctime-results` with the seal: E-0 … E-7 pass, and the F3 fixture `cfb05ff7…` is reproduced | exit 0, fixture pin |
| DV-x | both | `X` unchanged by the validation: type, mode, size, mtime and path, before and after each mode | identical |

**Exercised here on dummy data only:**
- DV-b1, DV-b2, DV-b3, DV-a1 and DV-a2 behaved as declared;
- DV-a3 stopped at the extractor's seal gate, as it must on dummy data.

**The approval record: "DR-13 validation record (WP-A1)"**, written by the executor. It holds:
- executor, host, image digest, date, `D`, `C`;
- `release_sums_sha256` and the three archive names;
- the `results.txt` of both modes and each mode's `SHA256SUMS` hash;
- any deviation, as found.

It is stored in the private evidence repository with checksums. **The maintainer approves it by signing the statement `a4-dr13.txt`** (§3), which names the record and its sha256. That approval also closes the DR-13 condition "validated before any independent evaluation". A dated entry in `migration-decisions-register.md` under DR-13 records the approval; that is a later documentation change by the maintainer, not part of this step.

## 7. G0-RO: environment equivalence against D-2 (session Q) and its approval record

**What D-2 is.** The reference environment of the G0 record revision 3 (`archive/m2/s72a-g0-closed`, `04657b4`): the reviewer's VM with OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, clang 21.1.8 and Python 3.13.13. The accepted A2-V1-S1 and smoke evaluations were executed there.

**What equivalence means.** As in G0: **verdict equivalence**, not hash identity. In the proposed container, the accepted read-only evaluators whose D-2 results are recorded are re-run, unchanged and with the D-2 invocation, on the same archived inputs. Their exit codes, verdicts, row statuses and exact counts must equal the D-2 record. **Regression-suite success is a precondition only (G0RO-P), never equivalence evidence by itself.** No WP-A1 code takes part in the comparison.

```bash
bash "$Z/scripts/host-stage.sh" g0ro-run.sh mounted "$Z/console.log"    # runs g0ro_compare.py; exit 0 only if all items pass
```

**Review of the reference values against the committed D-2 records (step 141).** Each value carries a source class, and only R and D items decide equivalence:

| Class | Meaning |
|---|---|
| **R** | a D-2 result recorded in a committed record |
| **D** | derived from R values by the accepted code at `C` |
| **P** | a declared protocol expectation, executed on D-2 but **not** in a committed record. Reported as information only. |

The review found that revision 3 had treated the N = 1 XA row statuses, δ, A-1b and exit code as D-2 records. They are declared expectations of `M2-S7.2a-s5-n2-protocol.md` step C. **They are now class P.**

| ID | Evaluator and invocation (unchanged code at `C`) | Compared | Class and source |
|---|---|---|---|
| G0RO-P | the 11 suites, exact lines | precondition only | — |
| G0RO-1a / 1b | `check_m2s72_a21.py a21 <A2-V1 runs> <cfg> … --contract full` / `f1d-i` (S1 protocol E-1 / E-2) | exit code (4 / 0); verdict (`A-2.1 INCOMPLETE` / `A-2.1 VALID`) with the contract; window `[2000000000000, 12001000000000]`; the 13 row statuses (A2-4c NOT EVALUATED, others PASS); per-node inserts, transmissions, feedback, ACK, NACK, discarded (2049: 11 702 / 11 702 / 11 697 / 11 697 / 0 / 0; 2050: 1 265 / 1 409 / 1 408 / 1 264 / 144 / 0); 129 handles, all retired; unresolved `[]`; end states `{censored: awaiting feedback: 6}` | **R**: S1 closure §1, §2 S-5 / S-7, §3 |
| G0RO-1d | `check_m2s72_a21.py a21-controls` (E-3) | exit code 0; 22 / 22 as declared; 0 not buildable | **R**: S1 S-6 |
| G0RO-2b | `check/check_m2s72_s5n2.py xa <N2 runs> M2S72-E0vN-q0-one0-n2-f1` (from `simulations/m2`) | XA-pre … XA-5 PASS, XA-6 NOT EVALUATED; A-1a 9 718, A-1b 2 476, ambiguous 768, re-insert 768, orphan 0; UE-sent NACK 0; retransmitted PDUs 0 | **R**: `M2-S7.2a-a2-design-review.md` §1 |
| | | exit code 0 | **D**: `xa` returns 0 iff `xa_ok` (XA-pre … XA-5 PASS, XA-6 NE because A-1 is not exact) |
| G0RO-2a | the same on the N = 1 smoke | A-1a 11 697; ambiguous, orphan, re-insert 0; UE-sent NACK 0 | **R**: a2-design-review §1 ("neither run … contains a DL NACK") |
| | | XA-pre … XA-6 PASS; A-1b 0; δ 1 000 000 000 ps; exit code 0 | **P**: protocol step C (declared; information only) |
| G0RO-I | identity: image digest, Python, OS, Simu5G HEAD, against the D-2 column of G0 §1 | recorded in the record, differences listed | not a criterion |
| G0RO-H | byte identity with the S1 archive (`3fa12389…`), if provided | — | informational only |

**Coverage record: not compared, with reason.** This list is also printed in every `compare.txt`.

| Field | Reason |
|---|---|
| a21 per-UE `lines_by_class`, and the S1 totals 371 groups / 742 exchangeable lines / 40 resolved by retransmission / 15 bound | recorded in S1 §3, but the mapping from the JSON class keys to these totals is not verified |
| the A2-8 Simu5G scalar values (S1 §4) | `.sca` inputs (byte-identical by the manifest). The A-2.1 side is implied by the compared counts and the A2-8 row status. |
| A2-7 details, per-UE occupancy equality, coverage section, d*, t_end | row statuses only |
| per-control observed / declared rows | exit code and counts only |
| S1 S-1 (integrity) and S-2 (original A2-V1 rows, `check_m2s72_a2v1`) | S-1 is the DR-13 validation; S-2's evaluator is not re-run |
| run times | not a criterion |
| XA overlap census, truth / A-1 aggregates, d* | not recorded for the smokes |
| N = 1 retransmitted PDUs | declared only |

**Expected limit, recorded rather than hidden:** G0RO-1 and G0RO-2 exercise the same read-only evaluation stack the WP-A1 wrapper builds on (A-2.1, A-1, XA, the MAC-log and `.sca` readers). They do not exercise the wrapper itself; that is what V-N1, V-N2 and V-V1 do.

**Exercised here:** `tests/test-g0ro-compare.sh` (§13).

**The approval record: "G0-RO environment-equivalence record (WP-A1)".** It holds:
- the image digest;
- `compare.txt`;
- the `SHA256SUMS` hash of `$Z/g0ro/`;
- the G0RO-I table against G0 §1;
- deviations.

It is approved by the maintainer **signing `a5-g0ro.txt`** (§3), naming the record, its sha256 and the image digest. It covers **only that image digest**; another image needs a new record.

## 8. Session V: Stages 2 – 6

```bash
bash "$Z/scripts/host-stage.sh" stage2-p0.sh      p0      "$Z/console.log"            || exit   # NO-GO: go to Stage 6
bash "$Z/scripts/host-stage.sh" h3-release.sh     release "$Z/console.log" validation || exit
bash "$Z/scripts/host-stage.sh" stage3-x2a.sh     mapped  "$Z/console.log"            || exit
bash "$Z/scripts/host-stage.sh" stage4-mount.sh   mounted "$Z/console.log"            || exit
bash "$Z/scripts/host-stage.sh" stage5-validate.sh mounted "$Z/console.log"; echo "stage 5 exit $?"   # 0 or 3 continue to Stage 6
bash "$Z/scripts/host-stage.sh" stage6-finalise.sh final "$Z/finalisation.log"           # after any stop from Stage 2 on, too
```

**Stage 3 (method (b), X-2a), in addition to revision 2:**
- `R` must not be visible.
- Every manifest line is well-formed and lies under `R`.
- **Strict presence:** every manifest entry exists at its **exact** original name, as a regular file of the recorded size. The accepted `verify-manifest` also accepts a `.gz` copy; `Run72` and the extractor do not.
- The A2-V1 files match their public pins.
- The seal identity, its 33 entries, and exactly the sealed files under `a2-nack-1/{p0,records,eval}`.
- The smoke seals are verified if archived, and recorded either way.
- The `Run72` readiness of the three runs (§8.1).

**Stage 4:** the mount and `X` are read-only (no file created), and the mount shows exactly `X`.

**Stage 5** runs the design commands with their exact argument vectors:

| Validation | Commands (design §8.2 – §8.4, argument vectors unchanged) |
|---|---|
| V-N1 | `verify-manifest` (P-1) → `check_m2s72_s5n21.py hrq … --expect expect/vn1.expect.json` → `check_m2s72_s5n2.py xa …` → `verify-manifest` (P-3) → `cmp` |
| V-N2 | the same, for the N = 2 configuration and `vn2.expect.json` |
| V-V1 | `m2s72_a21_fixture.py extract … --out fx-before` + fixture pin (P-1) → `hrq … --expect expect/vv1.expect.json` → `extract … --out fx-after` + fixture pin (P-3) |

Each design suffix `; echo "… rc=$?"` is replaced by `; rc=$?; note "… rc=$rc"`. The script then applies §9 itself. An `hrq` exit 0 counts only if `hrq-<cfg>.expect.txt` ends `ALL EXPECTATIONS MET`.

**Stage 6: finalisation with an explicit result (step 141).** Every outcome is finalised and preserved; a failed check never prevents the inventory or the final record.

**Integrity checks** (each failure is recorded as `integrity_failure:` in `RESULT.txt`):

| Check | Fails when |
|---|---|
| I-1 | the expectation files or the registry differ from the reviewed sha256 values |
| I-2 | the worktree is not at `C` |
| I-3 | the worktree is not clean (tracked change or untracked file) |
| I-4 | Simu5G is not at its pin, or not clean |
| I-5 | the evidence directory holds a non-regular entry (listed; not followed or inventoried) |
| F-3 | the procedure or console-transcript copy failed |

**Completeness checks** (`not_eligible:`): gate B GO; Stage 5 completed with every `hrq --expect` exit 0; no `findings.md`; the required records present.

**`RESULT.txt`** states `integrity: PASS|FAILED` and `acceptance_eligible: YES|NO`. It is written **before** the inventory, so `SHA256SUMS` covers it.

**The inventory's own verification** (F-7: count, `sha256sum -c`, nested `fx-*/SHA256SUMS`) is written to `F7-verification.txt`. A failure there overrides eligibility to NO. `SHA256SUMS.final` covers both `SHA256SUMS` and `F7-verification.txt`.

| Exit | Meaning |
|---|---|
| 0 | integrity PASS, acceptance-eligible: a precondition of VG-1 … VG-3, never an acceptance |
| **4** | **integrity FAILED: preserved as failed evidence, never acceptance-eligible** |
| 5 | integrity PASS, not eligible (NO-GO, stop, incomplete or findings) |
| 1 | not finalised (no evidence directory, already finalised, records not writable) |

`chmod -R a-w` follows. It is effective for the non-root container user; root bypasses it. Stage 6 prints the `SHA256SUMS.final` lines for F-10, and refuses a second finalisation.

### 8.1 Inputs the reviewed evaluators read (from the code at `C`; no configuration file)

| Reader (code at `C`) | Opens | Needed by |
|---|---|---|
| `check_m2s72_a21.inputs()` → `m2s72_a21.load`, `m2s72_maclog.MacLog` | `<runs>/run-<cfg>.log.gz` | `hrq`, `xa`, G0-RO |
| `check_m2s72_a2._node_ids` → `m2s72_runs.Run72(runs, cfg, 0)` | the `.sca` (`par … nrMac macNodeId`, one per UE); the directory `<runs>/<cfg>/pcap/<cfg>-0/`, whose `dsTt[k]`, `talker[k]`, `ue[k]` PCAPs set N; the PCAPs of `listener`, `nwTt` 0 and 1, `upf` 1, parsed; the CSVs `M2S72Bridge.nwTt.eth[1].trafficConditionerLayer.{syncIn.sync,engine.pdelay}.csv` under `<runs>/<cfg>/m2log/<cfg>-0/` | the node ids. If any file is missing or does not parse, `hrq` **refuses** (exit 2), with no node id guessed. |
| `m2s72_a2probe.scalars`, `m2s72_a2.sca_nodes`, `scalar_record_counts` | `<runs>/<cfg>/<cfg>/0.sca` | A2-8u, MAP-UE, the duplicate census |
| `check_m2s72_s5v.parse_name` (code, via `_nproc`) | none; the H-ARQ process count comes from the configuration **name** | `hrq`, `xa` |
| `m2s72_a21` A2-0s | `$SIMU5G_ROOT` sources (public) | `hrq`, G0-RO |
| `m2s72_a21_fixture.extract` | the seal, the 33 sealed records, the raw manifest and its 58 entries (exact names) | V-V1 P-1 / P-3, DV-a3 |
| `m2s72s5_lib.verify-manifest` | the manifests and their entries (a `.gz` copy is accepted) | P-1 / P-3, X-2a |

**No `.ini` or other configuration file is opened** by any of these. A `grep` of the whole evaluation chain at `C` finds no `.ini` reference. The absence of standalone `.ini` files in the archives therefore blocks nothing.

What is needed beyond the logs and `.sca` files is the PCAP and NW-TT CSV files that `Run72` opens. They are raw outputs and therefore manifest entries, so the strict presence check covers them. Stage 3's readiness check names them explicitly.

On a dummy tree, `Run72` took the node ids from the `.sca` while only requiring the other files to exist and parse. `MAP-UE` then cross-checked them against the `.sca`.

## 9. Stop, mismatch and retry rules (enforced by the scripts; gate A-6 approves them)

| Event | Action |
|---|---|
| Any gate-A item unmet | NO-GO: session V is not started |
| Stage 2 exit ≠ 0 | NO-GO. Genuine evidence was never accessed. Stage 6 finalises the NO-GO record. |
| H-3, Stage 3 or Stage 4 exit ≠ 0 | stop before any evaluation; Stage 6 |
| P-1 ≠ 0, or the V-V1 fixture not reproduced at P-1 | that run is not evaluated; stop; Stage 6 |
| `hrq --expect` exit 5 | finding, written to `<v>/findings.md`; P-3 and `cmp`; continue with the next validation; Stage 5 exits 3 |
| `hrq` exit 0 without `ALL EXPECTATIONS MET`, or any other exit | P-3 and `cmp`, then stop; Stage 6 |
| `xa` exit ≠ 0 | finding (non-gating, M-7); continue |
| P-3 ≠ 0, `cmp` differs, or the fixture not reproduced at P-3 | integrity failure; stop; Stage 6 |
| Stage 6 exit 4 (integrity FAILED) or 5 (not eligible) | the evidence is preserved and reported, and is never acceptance-eligible. A new session V needs the maintainer's approval. |
| Any failure | no retry, no clean-up, no relabelling (X-6). Each stage refuses an existing output (single attempt). |
| A fresh attempt | only with the maintainer's written approval, as a new session V (new `$Z`, new `X`). The failed one is preserved, finalised and reported. |

## 10. Evidence for VG-0 … VG-3

| Gate | Evidence |
|---|---|
| VG-0 | `RESULT.txt` with `integrity: PASS` and `acceptance_eligible: YES`, and `F7-verification.txt` PASS (Stage 6 exit 0); `gate/gate-b.txt`; `p0/*`; `release/*` (`sums-identity`, `selected.sha256`, `verify-before` / `-after`, `members-*`); `x2a/*` (method, manifests, presence, verify, public pins, seal and seal set, Run72 readiness, `mount.txt`, `mount-vs-x.txt`); the integrity files of each validation; `vv1/fx-{before,after}/`; `environment/*` (identity, the signed approvals with the approver key fingerprint, the approved records); `console.log`; `SHA256SUMS`, `SHA256SUMS.final`; the approved DR-13 and G0-RO records cited |
| VG-1 | `stage5-summary.txt`: `hrq rc 0: ALL EXPECTATIONS MET` for all three, and Stage 5 exit 0 |
| VG-2 | the A-1 PU-4 row verbatim under `historical` (PASS for V-N1, **FAIL** for V-N2) and never a gate; no output restating the A2-V1 verdict |
| VG-3 | the maintainer's acceptance of the validation record (X-9) |

## 11. Fail-open points found and resolved

| # | Fail-open point (where) | Resolution |
|---|---|---|
| FO-1 | `script` without `-e` returns 0 whatever the child returns (step-137 plan H-2 / H-4); **checked: `exit 7` gives rc 0** | `host-stage.sh` runs `script -e` and returns the stage's exit code; checked: rc 7 |
| FO-2 | Stages 3 – 5 typed by hand, the stop rules applied by the operator (revision 2) | scripts enforce §9 |
| FO-3 | `M-nowrite` used `touch`, which **creates a file in the evidence** if the mount is writable | `findmnt` `ro` + `test ! -w`; nothing is created (checked on a read-only bind mount) |
| FO-4 | `docker -v` silently creates a missing source directory | `--mount type=bind` (an error on a missing source), plus a check of every source before the command is built |
| FO-5 | placeholders, relative or overlapping paths in `vars.env` | `load_vars`: no `<`/`>`; absolute; fixed `W`, `E`, `CHK`, `PY`, `R`, `C`; `X` / `REL` / `$Z` / `R` disjoint |
| FO-6 | `verify-manifest` accepts a `.gz` copy that `Run72` and the extractor cannot read | strict exact-name presence before evaluation (Stage 3) |
| FO-7 | method (b) could resolve through the mount, or P-0 could run with the evidence present | Stage 3 and DV-b refuse if `R` is visible; Stage 2 refuses if `R`, `X` or `REL` is visible |
| FO-8 | the equivalence reference was only "non-empty" | `key=<64 hex>` lines; the running image digest must equal the approved one |
| FO-9 | `hrq` exit 0 trusted without its record | also requires `ALL EXPECTATIONS MET` as the final line of `hrq-<cfg>.expect.txt` |
| FO-10 | partial release verification: missing, extra or duplicate names, `--ignore-missing`, an unauthenticated checksum list | the approved `SHA256SUMS` hash; exactly three names, each listed once; `--strict`; re-verification after extraction |
| FO-11 | extraction: traversal, links, overwrite, unknown layout | `extract_checked.py` (tested on crafted archives) |
| FO-12 | finalisation as prose | `stage6-finalise.sh`: completeness, nested sums, verification, final record; a second run refused |
| FO-13 | an unpinned or absent image | digest required and present locally; recorded in the identity record |
| FO-14 | re-runs into existing outputs | every stage refuses an existing output (single attempt) |
| FO-15 | `bind()` stopping inside `$(…)` would only end a subshell | sources checked before any substitution |
| FO-16 | the `map` stream could silently drop an unprefixed line (found in the draft DR-13 script) | an explicit prefix check of every line first; the stream maps every line |
| FO-17 | Stage 6 only **warned** on a changed expectation file and ignored a dirty worktree, then finalised normally with exit 0 (step 141) | an explicit `integrity: FAILED` result, exit 4, never acceptance-eligible, still preserved (tests S6-3 … S6-9, S6-12) |
| FO-18 | gate-A references were populated text files that anyone could write (step 141) | maintainer-signed statements verified with `ssh-keygen -Y verify`; approved records hash-bound (tests AP-1 … AP-16) |
| FO-19 | G0-RO counted declared protocol expectations as D-2 records (step 141) | source classes R / D / P; only R and D decide (test GC-5) |

## 12. Decisions requiring the maintainer

| ID | Decision | Gate |
|---|---|---|
| M-1 | Executor and host | A-1 |
| M-2 | `C`, `D` and the four sha256 values | A-2 |
| M-3 | Access for the executor; the `SHA256SUMS` hash and the three archive names (the release check already passed for the maintainer) | A-3 |
| M-3a | Publish or hand over the maintainer's SSH public key for `wpa1-approval` and sign the statements (§3) | A-1 … A-6 |
| M-4 | Approve the DR-13 validation record (§6) by signing `a4-dr13.txt` | A-4 |
| M-5 | Approve the G0-RO record (§7) for one image digest by signing `a5-g0ro.txt`; decide whether G0RO-H (the S1 archive) is wanted | A-5 |
| M-6 | Approve §9 | A-6 |
| M-7 | `xa` non-gating in V-N1 / V-N2 (proposed) | §9 |
| M-8 | X-7: not applicable to read-only evaluations, or define its form | — |
| M-9 | A later design revision carrying C-1 / C-2 and this procedure | — |
| M-10 | After VG-3: S5-2-D2; registry admissions | — |

## 13. Tests of the procedure (TEST ONLY: dummy data and public code; never genuine archives)

| Test (`docs/migration/wp-a1-validation/tests/`) | What it covers |
|---|---|
| `test-stage6.sh` (S6-1 … S6-12) | Stage 6 on synthetic evidence with a real worktree at `C` and real Simu5G:<br>• clean → exit 0, eligible;<br>• **changed expectation file**, **dirty worktree** (untracked file; modified evaluator), worktree off `C`, dirty Simu5G, symlink in the evidence, a nested `SHA256SUMS` that no longer verifies, a missing transcript → exit 4, integrity FAILED, never eligible, and **preserved** (final record and inventory verify);<br>• findings, NO-GO → exit 5;<br>• second finalisation → exit 1 |
| `test-approvals.sh` (AP-1 … AP-16) | the signed gate-A statements with a throwaway key: valid; altered; another key; another namespace; unsigned; not APPROVED; duplicate key; another gate; malformed; another reviewed commit or expectation hash; no `allowed_signers`; A-4 / A-5 record changed or absent; another procedure commit |
| `test-extract.sh` (EX-1 … EX-8 + refusals) | `extract_checked.py` on crafted tar / tar.gz / zip archives: prefix handling; traversal; absolute; symlink; hardlink; outside the layout; mixed prefix; duplicates; overwrite; unknown format |
| `test-g0ro-compare.sh` (GC-1 … GC-8) | the comparator: equivalence; coverage record; source classes; R, D and P differences; window; missing output |
| `run-all.sh` | the four above |
| `docker-integration.sh <D>` | the whole sequence through `host-stage.sh` and a real Docker daemon, in a pinned image:<br>• session Q: H-1, H-3, DR-13-V (b) and (a), G0-RO;<br>• session V: H-1, refusals before gate B and on an altered A-5 statement, Stage 2 GO, H-3, Stages 3 – 6;<br>• `run-all.sh` inside the image.<br>Dummy-data stops are asserted. A TEST-ONLY copy of Stage 3 without its two real-hash comparisons drives Stages 4 – 6 in that session only, and is preserved in the evidence as such. |

**Running them:**

```bash
NASCTIME_SRC=<full clone> SIMU5G_SRC=<Simu5G clone with v1.8.1> bash docs/migration/wp-a1-validation/tests/run-all.sh
NASCTIME_SRC=<full clone> SIMU5G_SRC=<…> IMG=<image>@sha256:<digest> bash docs/migration/wp-a1-validation/tests/docker-integration.sh <D>
```

The results at the procedure commit are in `docs/migration/wp-a1-validation-test-report.md`.
