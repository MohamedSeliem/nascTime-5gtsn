# WP-A1 — Independent validation runbook: V-N1, V-N2, V-V1 (prepared, not executed)

**Status: revision 3, 23 November 2026, for independent review (step 139). Nothing has been executed against genuine evidence.**

**Revision history:**
- Revision 1: `e1b5a76`.
- Revision 2: `bb39906`, the step-135 corrections R1 – R5.
- Revision 3 (this one) closes the step-137 / step-139 gaps:
  - the procedure is now committed, fail-closed scripts in `docs/migration/wp-a1-validation/`, so the stop rules no longer depend on the operator;
  - exact release SHA-256 verification and extraction commands (§5);
  - the DR-13 validation protocol (§6) and the G0-RO comparison against D-2 (§7), each with its approval record;
  - the readiness of the archived inputs as derived from the reviewed code (§8.1);
  - the resolution of every fail-open point found (§11).

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
| Container image | Python ≥ 3.11 with git, coreutils, `awk`, `findmnt`. **Pinned by digest.** The digest is the one the approved G0-RO record covers. |

**Script pins at `D`** (sha256; `h1-setup.sh` exports the scripts from `D`, so these are for the reviewer):

| File | sha256 |
|---|---|
| `common.sh` | `f5659436f636b49df78d41c7203645f79c833f0da4e6b6976fc4fb15f35316b5` |
| `dr13-validate.sh` | `465f12533d839f1a331d15f6b1a874ec28af3ec24d2fcc18bfaeb0c396a51f0b` |
| `extract_checked.py` | `00190e4e9d0a9cb0da25d9ea9fdd23d9490d9770f53dd853a1f6ededec257b2d` |
| `g0ro-run.sh` | `586e1304ddf92841f6aa8333f79d284d0f02e648e30fc69a4659f152584e7d33` |
| `g0ro_compare.py` | `02109c328c7d9cec1767711fbb77cf2fa4adfdbb8475159030ec20476855b021` |
| `h1-setup.sh` | `5f2aed83a848bbe788d619a181de2868ba599bc16f98afff44af3e371eecda10` |
| `h3-release.sh` | `a0694e0c56de16b92f5c884f3b03037fccbe02bd6ff315464f908cfa048f7ecd` |
| `host-stage.sh` | `7ef9309f1ed3882e631bc84a5a8da17434b187e7bc4177db37a13e110cd79551` |
| `stage2-p0.sh` | `6f4f3f8ab092d5bfac7a933e7d43196ab8c9556648de66f3686ecc2c4749aab9` |
| `stage3-x2a.sh` | `f4fcf74b1fe78462085f69e95f71c22251983fa8c3e1dec323944f80f0529827` |
| `stage4-mount.sh` | `c47295bb5257f66ea5aea115748d6ec3a9d7305e338d3af73b9455c91ab34a8f` |
| `stage5-validate.sh` | `a03097c89a4b354f69511c8c6e66739ea4e70335c1f76c8e1c61e19ba649ce9e` |
| `stage6-finalise.sh` | `5a5251133380a912b0657a4ba052403b339b8bbffb2df63f7344230f95a61a8b` |
| `vars.env.template` | `c98fd08c97077b0e5bf663b89cf9cf0ae62fdf5bb027427d311ac77f3611934a` |

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

### Gate A: administrative, before session V

| # | Item | Evidence | Reference file in `$Z/refs/` |
|---|---|---|---|
| A-1 | Designated independent executor | the maintainer's written designation | `gate-a.txt`: `executor=` |
| A-2 | Fixed reviewed commit, procedure commit and expectation files | the maintainer's confirmation of `C`, of `D` and of the four sha256 values | `gate-a.txt`: `docs_commit=<D>` (checked by `h1-setup.sh`) |
| A-3 | Authorised access to the three archives, for this executor | the maintainer's authorisation | `release-ref.txt`: `release_sums_sha256=` and the three `archive=` names (checked by H-3) |
| A-4 | DR-13 procedure approved **and validated** | the DR-13 validation record (§6), approved | `dr13-ref.txt`: `dr13_record_sha256=` (checked by Stage 2) |
| A-5 | Environment equivalence (X-4) | the G0-RO record (§7) for **this image digest**, approved. **An identity statement or the regression suites alone are not sufficient.** | `equivalence-ref.txt`: `g0ro_record_sha256=`, `image_digest=`. Stage 2 checks the running image digest equals it. |
| A-6 | Agreed stop, mismatch and retry rules | the maintainer's approval of §9 | `gate-a.txt`: `rules=approved` |

The reference files only carry values out of the approval records. They cannot create an approval: the approval is the maintainer's dated record.

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
- the gate-A reference files must be well-formed;
- the image digest must be the one the G0-RO record covers.

**GO is only the script's exit 0**, together with the line `GATE B: GO (B-1 ... B-6 met)` in `$E/gate/gate-b.txt`.

## 4. H-1: set-up on the host (network, no evidence)

```bash
export Z="$(mktemp -d)"                                    # fresh for each session
git clone https://github.com/MohamedSeliem/nascTime-5gtsn.git "$Z/nasctime-src"
mkdir "$Z/refs"        # write gate-a.txt, release-ref.txt, dr13-ref.txt, equivalence-ref.txt from the approval records
D=<the approved procedure commit, 40 hex>
git -C "$Z/nasctime-src" show "$D:docs/migration/wp-a1-validation/vars.env.template" > "$Z/vars.env"
#   edit $Z/vars.env: replace the two <...> placeholders (X, REL); every other line stays as given
git -C "$Z/nasctime-src" show "$D:docs/migration/wp-a1-validation/h1-setup.sh" > "$Z/h1-setup.sh"
bash "$Z/h1-setup.sh" "$D"                                 # exports the scripts from D, worktree at C, Simu5G at its pin
docker pull "<image>@sha256:<digest>"                      # the digest of the approved G0-RO record (session V)
export IMG="<image>@sha256:<digest>"
```

**What `h1-setup.sh` and `common.sh` refuse:**
- a `D` other than the approved one;
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

It is stored in the private evidence repository with checksums. **The maintainer approves it with a dated decision line.** That approval also closes the DR-13 condition "validated before any independent evaluation". Its sha256 becomes `dr13_record_sha256` (gate A-4). A dated entry in `migration-decisions-register.md` under DR-13 records the approval; that is a later documentation change by the maintainer, not part of this step.

## 7. G0-RO: environment equivalence against D-2 (session Q) and its approval record

**What D-2 is.** The reference environment of the G0 record revision 3 (`archive/m2/s72a-g0-closed`, `04657b4`): the reviewer's VM with OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, clang 21.1.8 and Python 3.13.13. The accepted A2-V1-S1 and smoke evaluations were executed there.

**What equivalence means.** As in G0: **verdict equivalence**, not hash identity. In the proposed container, the accepted read-only evaluators whose D-2 results are recorded are re-run, unchanged and with the D-2 invocation, on the same archived inputs. Their exit codes, verdicts, row statuses and exact counts must equal the D-2 record. **Regression-suite success is a precondition only (G0RO-P), never equivalence evidence by itself.** No WP-A1 code takes part in the comparison.

```bash
bash "$Z/scripts/host-stage.sh" g0ro-run.sh mounted "$Z/console.log"    # runs g0ro_compare.py; exit 0 only if all items pass
```

| ID | Evaluator and invocation (unchanged code at `C`) | D-2 reference (committed) | Compared |
|---|---|---|---|
| G0RO-P | the 11 suites, exact lines | tier-0 / runbook | precondition only |
| G0RO-1a | `check_m2s72_a21.py a21 <A2-V1 runs> <cfg> … --contract full` (S1 protocol E-1) | S1 closure §2 S-5: rc 4, `A-2.1 INCOMPLETE`; §3 rows | exit code, verdict, the 13 row statuses (A2-4c NOT EVALUATED, others PASS) |
| G0RO-1b | the same, `--contract f1d-i` (E-2) | S-5: rc 0, `A-2.1 VALID` | as 1a |
| G0RO-1c | per-node accounting of 1a and 1b | S1 §3: node 2049 11 702 / 11 702 / 11 697 / 11 697 / 0 / 0; node 2050 1 265 / 1 409 / 1 408 / 1 264 / 144 / 0; 129 handles, all retired; unresolved `[]`; end states `{censored: awaiting feedback: 6}` | exact integers |
| G0RO-1d | `check_m2s72_a21.py a21-controls` (E-3) | S-6: rc 0, 22 / 22 as declared, 0 not buildable | exit code, counts |
| G0RO-2a | `check/check_m2s72_s5n2.py xa <N1 runs> M2S72-E0v-q0-f1` (from `simulations/m2`, as on the VM) | `M2-S7.2a-s5-n2-protocol.md` step C: rc 0; XA-pre … XA-6 PASS; A-1a 11 697, A-1b 0, ambiguous / orphan / re-insert 0; δ 1 000 000 000 ps | exit code, row statuses, counts |
| G0RO-2b | the same on the N = 2 smoke | the N = 2 acceptance (N2-A1, N2-A4 … N2-A6, P-N2-4) and DR-07c: rc 0; XA-pre … XA-5 PASS, XA-6 NOT EVALUATED; A-1 9 718 / 2 476 / 768 / 0 / 768 | as 2a |
| G0RO-I | identity: image digest, Python, OS, Simu5G HEAD | the D-2 column of G0 §1 | recorded and compared in the record; differences listed, not a pass criterion |
| G0RO-H | byte identity with D-2 record files | the S1 archive (`3fa12389…f0e34`), if the maintainer provides it | **informational only** |

**Expected limit, recorded rather than hidden:** G0RO-1 and G0RO-2 exercise the same read-only evaluation stack the WP-A1 wrapper builds on (A-2.1, A-1, XA, the MAC-log and `.sca` readers). They do not exercise the wrapper itself; that is what V-N1, V-N2 and V-V1 do.

**Exercised here:** `g0ro_compare.py` on synthetic outputs shaped like the tools' real JSON. Matching gave 63 / 63 PASS, exit 0; one changed count gave exit 1; missing outputs gave FAILs.

**The approval record: "G0-RO environment-equivalence record (WP-A1)".** It holds:
- the image digest;
- `compare.txt`;
- the `SHA256SUMS` hash of `$Z/g0ro/`;
- the G0RO-I table against G0 §1;
- deviations.

It is approved by the maintainer with a dated decision line. Its sha256 and the image digest become `equivalence-ref.txt` (gate A-5). It covers **only that image digest**; another image needs a new record.

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

**Stage 6** (F-2 … F-9 of revision 2, as a script):
- the post-checks;
- copies of the procedure, references and console transcript;
- the inventory of every file except the two top-level records, including the nested `fx-*/SHA256SUMS`;
- a completeness check and verification, top level and nested;
- `SHA256SUMS.final`, then `chmod -R a-w`. The containers run as the executor's user; root would bypass `chmod`.

It prints the `SHA256SUMS.final` line for F-10. It refuses a second finalisation.

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
| Any failure | no retry, no clean-up, no relabelling (X-6). Each stage refuses an existing output (single attempt). |
| A fresh attempt | only with the maintainer's written approval, as a new session V (new `$Z`, new `X`). The failed one is preserved, finalised and reported. |

## 10. Evidence for VG-0 … VG-3

| Gate | Evidence |
|---|---|
| VG-0 | `gate/gate-b.txt`; `p0/*`; `release/*` (`sums-identity`, `selected.sha256`, `verify-before` / `-after`, `members-*`); `x2a/*` (method, manifests, presence, verify, public pins, seal and seal set, Run72 readiness, `mount.txt`, `mount-vs-x.txt`); the integrity files of each validation; `vv1/fx-{before,after}/`; `environment/*` (identity, the two gate-A references); `console.log`; `SHA256SUMS`, `SHA256SUMS.final`; the approved DR-13 and G0-RO records cited |
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

## 12. Decisions requiring the maintainer

| ID | Decision | Gate |
|---|---|---|
| M-1 | Executor and host | A-1 |
| M-2 | `C`, `D` and the four sha256 values | A-2 |
| M-3 | Access for the executor; the `SHA256SUMS` hash and the three archive names (the release check already passed for the maintainer) | A-3 |
| M-4 | Approve the DR-13 validation record (§6) | A-4 |
| M-5 | Approve the G0-RO record (§7) for one image digest; decide whether G0RO-H (the S1 archive) is wanted | A-5 |
| M-6 | Approve §9 | A-6 |
| M-7 | `xa` non-gating in V-N1 / V-N2 (proposed) | §9 |
| M-8 | X-7: not applicable to read-only evaluations, or define its form | — |
| M-9 | A later design revision carrying C-1 / C-2 and this procedure | — |
| M-10 | After VG-3: S5-2-D2; registry admissions | — |

## 13. What was exercised while preparing

Nothing touched genuine evidence. Mount profiles were emulated with private mount namespaces; no container daemon was available, so `docker run` itself is untested here.
- **Stage 2** on public code (real worktree at `C`, real Simu5G, TEST-ONLY gate references): 11 / 11 suites, GO.
- **H-3** on dummy archives:
  - verified and extracted (78 files);
  - refused: an unapproved `SHA256SUMS`, a second attempt, a qualification run with `E` present, and a validation run without gate B.
- **Stage 3** on the dummy extraction:
  - the manifest, presence and mapped-verification checks passed;
  - it stopped at the A2-V1 public pins, as it must on dummy data;
  - a TEST-ONLY copy without the two pin comparisons passed the seal-set, smoke-seal and `Run72` readiness checks.
- **Stage 4:** passed.
- **Stage 5** on dummy data:
  - V-N1 / V-N2: `hrq` exit 5 → findings, P-3 identical, continued;
  - V-V1: stopped at P-1, extractor exit 11 (seal gate), before evaluation.
- **Stage 6:** finalised, nested sums included, re-verified, a second run refused.
- **DR-13-V and G0-RO:** see §6 and §7.
- **`host-stage.sh`:** refused an unpinned image, an absent image and an unknown script.
