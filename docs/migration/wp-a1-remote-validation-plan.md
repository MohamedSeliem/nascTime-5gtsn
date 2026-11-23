# WP-A1 — Remote execution plan for the independent validations V-N1, V-N2, V-V1 (preparation)

**Status: prepared for review (step 137), 23 November 2026.**
- **Assessment: NO-GO** (§7). Nothing in this plan has been executed.
- No private evidence was accessed, no evaluation or simulation was run, and no secret, workflow or accepted code was added or changed.

**Scope:**
- This plan shows how to execute `docs/migration/wp-a1-validation-runbook.md` **revision 2** (commit `bb39906`) on remote infrastructure. It changes neither that runbook nor the design.
- It reuses what exists from E1 – E3 and adds no CI framework.

**Fixed inputs:**
- The reviewed implementation `C` = `f3f68be696777e42b0717f949625855ddb475435`.
- The expectation files and registry, pinned by the runbook (§1, four sha256 values).
- The original results prefix `RR` = `/mnt/nasctime-results`. This is corroborated by committed records, e.g. `simulations/m2/check/fixtures/a2v1-first-chain.meta.json` and `M2-S7.2a-a2-implementation.md`.

## 1. Reuse of the E1 – E3 infrastructure for a read-only evaluation

The validations are **read-only Python evaluations**. They need Python ≥ 3.11, git, coreutils and the Simu5G 1.8.1 **sources** (A2-0s). They need no OMNeT++, INET or Simu5G build and no simulation.

| Component | Where | Reuse | Reason |
|---|---|---|---|
| Tier-0 environment contract: Python 3.13, the Simu5G `v1.8.1` / `7477d266` identity gate, `SIMU5G_ROOT`, full history, the 11 suites with exact lines | `.github/workflows/tier0-python.yml` at `C` | **Reused as a contract, not as a workflow.** Runbook Stage 2 (gated P-0) reproduces the same gates offline. | It is exactly what the evaluation code needs. GitHub tier-0 already passed 11 / 11 at `C`. |
| Tier-0 `run_suite.sh` semantics (exit code, exact line, isolated mode) | same | Reused: runbook Stage 2 implements the same checks | |
| Tier-1 Nix / opp_env / OMNeT++ 6.5.0 / INET / Simu5G builds, linkage and RUNPATH gates (C-1 … C-15) | `ci/tier1/` | **Not needed** | Nothing is compiled or simulated. Using them would add hours of build and identity surface for no evaluated input. |
| Tier-1 rule that the hosted runner never has the VM results root (`vm_results_root_present_before/after`) | `ci/tier1/wrapper/run-suite.sh` | **Principle reused** | Hosted CI must never see `/mnt/nasctime-results`. This plan keeps the evidence off GitHub entirely. |
| E3 single-attempt identity (E-1: authorised branch, first attempt, fixed commit) | `ci/tier2/py/identity.py` (branch `wp-e3/e3b-r1-publication`, never merged) | **Principle reused; code not used** | The code is not at `C` and is bound to GitHub variables. Its equivalent is the runbook's commit pin (P-0), fresh `$E`, "no retry" rule and gate A-2. |
| E3 sealing before evaluation and verification after (`seal.py`) | same branch | **Principle reused; code not used** | The runbook already seals via P-1 / P-3 (accepted `verify-manifest`, the extractor's E-1 … E-7) and finalises `$E` (F-5 … F-8). A second sealing tool from an unmerged branch would add an unreviewed dependency for this use. |
| E3 audit-hook confinement of the oracle | `ci/tier2/py/m2s5_oracle.py` | Not needed | The WP-A1 wrapper has its own reviewed input tracker (I7-R3), which records every consumed file. |
| E3 raw publication (`rawpub.py`) and artifact upload | `ci/tier2/` | **Must not be reused** | The repository is **public**: hosted logs and artifacts are publicly readable. Genuine evidence and validation outputs are never published. They go only to the private evidence repository (X-5). |
| E3 GitHub-hosted workflow pattern (push on a dedicated branch) | `.github/workflows/e3*.yml` | **Not usable for level 3** | X-1: the development agent can push and therefore trigger, and §4a records E3 runs as level-2 only. Getting the archives onto a hosted runner would need a secret, which is excluded. |

**Conclusion:** reuse the tier-0 environment contract and the E3 principles (single attempt, seal before and after, fail closed, no publication of evidence). Do not run the validation as a GitHub workflow of this repository.

## 2. Providing the archives securely to an ephemeral environment

| Option | Assessment |
|---|---|
| A. GitHub Actions in this repository (hosted or self-hosted runner) | **Rejected.** The repository is public, so run logs and artifacts are world-readable. A download secret would have to enter Actions, which is excluded. Self-hosted runners on a public repository are exposed to pull-request workflows. X-1 is not met, because the development agent can trigger. |
| B. A separate private repository with a protected-branch workflow and a required-reviewer environment | **Not recommended now.** It is a new CI surface (contrary to "no new framework"), it needs a secret in Actions, and it would require its own security review (S-1 … S-3). |
| **C. An executor-operated ephemeral host with a container (recommended)** | The independent executor uses their own credentials, **outside GitHub Actions**, on an ephemeral VM or machine they control: for example a university machine or cloud VM (open item M-3 of the feasibility document, §5 item 3). Nothing is added to the repository. The evidence is mounted read-only into a **network-less** container, and the outputs go only to the private evidence repository. |

**Option C, security properties:**
1. **Download and verification.** The archives are downloaded from the private release by the executor (e.g. `gh release download` with the executor's own token, never stored in any repository or workflow). The release SHA-256 is verified; for the three archives this is reported as done.
2. **Extraction.** They are extracted on the host into `X`, outside every repository checkout. `X` is made read-only (`chmod -R a-w "$X"`).
3. **Network separation.** All network access (cloning `C` and Simu5G) happens **before** any evidence is mounted. Every container that sees evidence runs with `--network none`, so nothing can leave during evaluation.
4. **Read-only evidence.** The evidence is bind-mounted **read-only**, once at `/mnt/nasctime-results` (DR-13 method (a)) and once at `X` (method (b) needs the extraction path). Only `$Z` (work directory and `$E`) is writable.
5. **Clean-up.** After finalisation (runbook §9), `$E` and `finalisation.log` are transferred to the private evidence repository with checksums (X-5). The host is then destroyed or `X` is wiped. Nothing is posted to GitHub: no comment, artifact or log containing evidence values. The maintainer receives the record privately.

## 3. DR-13 path-resolution validation record

**Not found.**
- DR-13 (decision 17 Nov 2026) approves the two methods and requires that "the method is validated before any independent evaluation".
- `authoritative-migration-status.md` §0.4 describes the methods.
- A search of every document under `docs/migration/` and the records at `C` finds **no record of that validation**. The only occurrences are the decision itself, X-2a, the travel plan's dependency lines and the runbook's own NO-GO items A-4 / PR-4.

The runbook's Stages 3 – 4 apply the methods. They do not validate them.

**Proposed content of the missing record (for M-4; to be performed by the executor, not by the development agent):**
- **DR-13-V1 (method (a)), on the executor's host and container:**
  - the read-only bind mount at `/mnt/nasctime-results` passes the runbook's `M-ro` / `M-nowrite` checks;
  - the accepted `m2s72s5_lib.py verify-manifest` verifies each original manifest **unchanged** through the mount;
  - the accepted extractor passes E-0 … E-3 on `RR`.
- **DR-13-V2 (method (b)):** the stream-mapping command of runbook §6.1 verifies the same three manifests against `X`. A deliberately altered **copy** of one extracted file, in a scratch tree outside `X`, is reported as a mismatch.
- **Constraints:** no manifest is written, and no evidence is modified.

These checks access the private evidence, so they need A-3 authorisation, and they may be performed in the same executor session **before** the runbook's gate A is decided. A record must be written and approved.

**Already checked here (dummy data only, no evidence):**
- The `M-ro` / `M-nowrite` checks hold on a read-only bind mount at `/mnt/nasctime-results` in a private mount namespace.
- The method (b) stream form verifies (exit 0) and detects a change (exit 1) with the accepted `verify-manifest`.

## 4. G0-style environment-equivalence record

**No approved record covers the proposed environment.**
- The only G0 record is `simulations/results/simu5g-1.8.1/g0env/G0-environment-equivalence-record.md`, revision 3, CLOSED, at `04657b4` (`archive/m2/s72a-g0-closed`).
- It establishes **verdict equivalence** from the accepted OMNeT++ 6.4.0 cloud container to the D-2 reference: the reviewer's VirtualBox VM with OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, clang 21.1.8 and Python 3.13.13.
- It does not cover any other machine, container or Python installation.
- Tier-0 and tier-1 CI establish build, linkage and suite results on hosted runners. Neither is a G0-style record (DR-14, §4a).

X-4 requires an approved record before the first acceptance-bearing run on a new environment, and the identity record does not replace it (runbook §4.2). **A new record ("G0-RO") is required. Its scope is the maintainer's decision (M-5).**

**Proposed scope, for a read-only evaluation environment where no simulator is executed:**

| Criterion | Content | Evidence |
|---|---|---|
| G0-RO-1 identity | The X-4 list, as in the runbook's `identity.txt`: OS, Python, interpreter sha256, container image digest, Simu5G HEAD, `C`. OMNeT++ / INET are "not installed (not used)". | file |
| G0-RO-2 public verdict identity | In the same container image, the 11 tier-0 suites give their exact lines. This includes the genuine-derived F3 fixture suites, whose fixture line is the result of the independent VM run (`h4-first-task.md` §5). | runbook Stage 2 outputs |
| G0-RO-3 genuine verdict identity (optional; maintainer's choice) | In the same container, on the same archives, the **accepted** read-only evaluators reproduce verdicts the VM recorded: for example `check_m2s72_s5n2.py xa` and the smoke verdict rules against the records in the N = 1 / N = 2 archives, if those records are archived. This accesses evidence, so it needs A-3. | a record comparing verdicts, not hashes |

The record must be **approved** before runbook gate A-5 can be met. Producing it is the executor's task.

## 5. Missing approvals, records, archive-specific commands and environment dependencies

| # | Missing item | Type | Blocks |
|---|---|---|---|
| 1 | Designation of the independent executor (X-1; feasibility §5 item 4, open) | approval | A-1 |
| 2 | Choice and budget of the remote host (feasibility §5 item 3, open) and acceptance of option C (§2) | approval | all |
| 3 | Confirmation of `C` and of the four sha256 values | approval | A-2 |
| 4 | Authorisation for **this executor** to access the three archives (recovering them is not an authorisation) | approval | A-3, DR-13-V, G0-RO-3 |
| 5 | The DR-13 validation record (§3), performed and approved | record | A-4 |
| 6 | The G0-RO equivalence record (§4), scoped, performed and approved | record | A-5 |
| 7 | Approval of the runbook's stop, mismatch and retry rules (§8) | approval | A-6 |
| 8 | **Archive content confirmation.** The archives are described as raw evidence: N1 41 files, N2 58, A2-V1 58, "verified before packaging against the original manifests". The runbook additionally needs, at their original relative paths under `RR`: (a) the original manifests `…/records/<cfg>.manifest.sha256` (P-1 / P-3, Stage 3); (b) for V-V1, the seal `a2-nack-1-evidence.sha256` and **exactly** the 33 sealed records under `a2-nack-1/{p0,records,eval}` (extractor E-0 … E-2, which fail on anything added or missing); (c) the `.sca` and the configuration files `hrq` reads for the node ids. It is not documented whether (a) and (b) are inside the three archives, or in the separate "sealed S1 archive" (`3fa12389…f0e34`), which would then also be required. | archive-specific | Stages 3 – 5 |
| 9 | **Archive-specific commands:** the inner archive checksum-manifest verification command (runbook PR-9, placeholder in §6.1); the extraction command and its mapping to `X/<rel>` = `RR/<rel>` (PR-10) | archive-specific | Stage 3 |
| 10 | Optional: whether the smoke evidence seals `s5-smoke-1-evidence.sha256` / `s5-n2-1-evidence.sha256`, which accepted procedures verify (e.g. `M2-S7.2a-s5-n2-protocol.md`), are in the archives. If so, the maintainer may add their `sha256sum -c` as a supplementary Stage 3 check. That would be an addition, not part of runbook revision 2. | archive-specific (optional) | — |
| 11 | **Environment dependencies on the host:** a container runtime (Docker or Podman) with bind mounts and `--network none`; network to `github.com` (repository, Simu5G) for the set-up phase only; disk for the three extractions (≈ 2.2 GB) plus `$E` | environment | all |
| 12 | **Container image:** a Python 3.13 image providing git, coreutils, `awk`, `script` (bsdutils) and `findmnt` (util-linux), **pinned by digest** and recorded in the identity record. For example the Debian-based official `python:3.13`; the executor fixes the digest. | environment | Stage 2 |
| 13 | X-7 (reproducibility re-execution) is written for simulation runs. The maintainer should confirm it is not applicable to these read-only evaluations, or define its form. | approval | — |

## 6. Minimal executable plan (option C)

**Rules for the executor:**
- The validation commands, expectation files and evidence-integrity steps are those of runbook revision 2, used unchanged.
- The executor obtains the runbook from commit `bb39906` and checks two pins before use:

| Pinned item | Value |
|---|---|
| runbook blob | `d4a10e88cd25e5d7bcdd564ce67df8c36414fb55` |
| runbook sha256 | `6a5ee6c6d2845959b7bbc492c5cf578d60578701081a08c0dadfbb61d5cad425` |
| the Stage 2 script extracted from it (from `#!/usr/bin/env bash` to the first `exit 0`) | sha256 `cacb8f3865224d74981aad419b77d87857855d94f6e94fe8ef443fe7ffb9e4be` |

- **Host prerequisite:** the paths `$Z` and `$X` are mounted into the containers at **the same absolute paths**, so that `vars.env` is valid inside and outside.

### Phase H-1: host set-up, with network, no evidence present

Runbook §4.1 is carried out on the host, without `script`. The transcript starts in the first container.

```bash
export Z="$(mktemp -d)"; cd "$Z"
git clone https://github.com/MohamedSeliem/nascTime-5gtsn.git nasctime-src
git -C nasctime-src worktree add --detach "$Z/wpa1-validate" f3f68be696777e42b0717f949625855ddb475435
git clone --branch v1.8.1 https://github.com/Unipisa/Simu5G.git simu5g-1.8.1
git -C nasctime-src show bb39906:docs/migration/wp-a1-validation-runbook.md > runbook-r2.md
echo "6a5ee6c6d2845959b7bbc492c5cf578d60578701081a08c0dadfbb61d5cad425  runbook-r2.md" | sha256sum -c
awk '/^#!\/usr\/bin\/env bash$/{p=1} p{print} p&&/^exit 0$/{exit}' runbook-r2.md > stage2-p0.sh
echo "cacb8f3865224d74981aad419b77d87857855d94f6e94fe8ef443fe7ffb9e4be  stage2-p0.sh" | sha256sum -c
# vars.env exactly as runbook 4.1, with R=/mnt/nasctime-results, X=<extraction root>, E="$Z/evidence-wpa1"
# equivalence-ref.txt: the name and sha256 of the approved G0-RO record (gate A-5)
IMG=<python 3.13 image>@sha256:<digest fixed by the executor>
```

### Phase H-2: gate B, network-less container, **without** evidence mounts

```bash
docker run --rm --network none --user "$(id -u):$(id -g)" -e Z="$Z" -e HOME=/tmp -v "$Z":"$Z":rw -w "$Z" "$IMG" \
  bash -c 'script -q -a -c "bash $Z/stage2-p0.sh" "$Z/console.log"'
echo "gate B rc=$?"     # only 0 is GO; otherwise stop (runbook §8) and finalise $E (runbook §9)
```

### Phase H-3: extraction on the host, only after gate B is GO

```bash
<download the three archives with the executor's own credentials; verify the release SHA-256>
<extract them into X so that X/<rel> holds RR/<rel>>      # item 9
chmod -R a-w "$X"
```

### Phase H-4: Stages 3 – 5 and the finalisation, in a network-less container with read-only evidence

```bash
docker run --rm -it --network none --user "$(id -u):$(id -g)" -e Z="$Z" -e HOME=/tmp \
  -v "$Z":"$Z":rw -v "$X":"$X":ro -v "$X":/mnt/nasctime-results:ro -w "$Z" "$IMG" \
  script -q -a -c bash "$Z/console.log"
# inside: runbook 6.1 (Stage 3, method (b)), 6.2 (Stage 4, method (a); M-ro / M-nowrite must be 0),
#         7.1 V-N1, 7.2 V-N2, 7.3 V-V1 - verbatim, applying the stop rules of runbook 8 after every command;
#         then runbook 9 F-1 ... F-9 (the finalisation transcript in "$Z/finalisation.log")
```

### Phase H-5: transfer and clean-up

1. Record `SHA256SUMS.final` at sealing time (runbook F-10).
2. Transfer `$E` and `finalisation.log` to the private evidence repository with checksums (X-5).
3. Destroy the host, or wipe `X` and `$Z`.
4. Report privately to the maintainer. The status stays "executed, not accepted" until VG-3 (X-9).

**Untested elements:**
- The container commands were **not executed here**: this environment has no running container daemon.
- `script -a` appends both containers' transcripts to one `console.log`. This is consistent with runbook F-3.
- `--user` runs the containers as the owner of `$Z`. Without it, git refuses the bind-mounted worktree ("dubious ownership"), and P-0 would stop at its commit check.

## 7. GO / NO-GO assessment

| Runbook gate item | State | Basis |
|---|---|---|
| A-1 designated independent executor | **NOT MET** | §5 item 1 |
| A-2 fixed commit and expectation files | **met technically; confirmation pending** | `C` fixed and the four sha256 values pinned; the maintainer's confirmation is not recorded (§5 item 3) |
| A-3 authorised access to the original evidence | **NOT MET** | The archives are recovered and their release checks passed, but no authorisation for an executor is recorded (§5 item 4) |
| A-4 approved and validated DR-13 procedure | **NOT MET** | approved (17 Nov), **no validation record** (§3) |
| A-5 approved G0-style equivalence record | **NOT MET** | G0 rev. 3 covers only the 6.4.0 container → D-2 VM (§4) |
| A-6 agreed stop, mismatch and retry rules | **NOT MET** | proposed in runbook §8, not approved |
| B-1 … B-6 (identity, clean worktree, pinned Simu5G, suites, fresh `$E`, `S5N_ADAPTER_VALIDATED` unset) | **ready, not yet run** | Decided only by the Stage 2 script on the executor's host. The script passed GO on public code at step 135, and GitHub tier-0 passed 11 / 11 at `C`. |
| Archive content and commands | **NOT CONFIRMED** | §5 items 8 – 9 |
| Host and container | **NOT AVAILABLE** | §5 items 2, 11, 12 |

**Overall: NO-GO.** Execution becomes possible only when every NOT MET, NOT CONFIRMED and NOT AVAILABLE item above is resolved.

**Exact remaining prerequisites, in dependency order:**
1. The maintainer designates the executor and the host, and accepts option C (§2).
2. The maintainer authorises that executor's access to the three archives, and confirms `C`, the four sha256 values and the runbook commit `bb39906` with its two pins.
3. The maintainer confirms the archive contents (§5 item 8): the manifests, the A2-V1 seal and its 33 sealed records, `.sca` and configuration files. The maintainer supplies the inner checksum-verification and extraction commands (item 9). If the seal and records are in the sealed S1 archive, that archive is authorised too.
4. The executor performs the DR-13 validation (§3), and the maintainer approves its record.
5. The executor produces the G0-RO record (§4) in the pinned container image, and the maintainer approves its scope and result.
6. The maintainer approves the runbook §8 rules, and decides X-7's applicability (item 13).
7. The executor runs gate B (Phase H-2). Only on exit 0 do Phases H-3 to H-5 follow.

**Not affected by this plan:**
- `S5N_ADAPTER_VALIDATED` stays unset.
- PR #11 stays a draft.
- The FGO registry, the expectation files and every accepted evaluator are unchanged.
- S5-2-D2 and the registry admissions remain post-VG-3 decisions.
