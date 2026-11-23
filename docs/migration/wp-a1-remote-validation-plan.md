# WP-A1 — Remote execution plan for the independent validations V-N1, V-N2, V-V1

**Status: revision 2, 23 November 2026, for independent review (step 139).**
- Revision 1 is `e2523f8` (step 137).
- **Option C** (an independent, executor-operated, ephemeral environment) was approved at step 139 as the preferred architecture.
- **Genuine validation remains NO-GO** (§4).

**Supersession:**
- The executable procedure is now `docs/migration/wp-a1-validation-runbook.md` **revision 3** and the scripts in `docs/migration/wp-a1-validation/`.
- They replace the phase commands H-1 … H-5 of revision 1 §6. Those commands contained a fail-open point: `script` without `-e` returns 0 (runbook §11, FO-1).

**Restrictions observed in this step:**
- documentation and public-code inspection only;
- no private archive access, simulation, genuine evaluation, workflow change, registry change or merge;
- the dry runs used dummy data and public code only.

## 1. Archive readiness: updated to the verified facts

**Facts verified by the maintainer (step 139):**
- The three release archives match the release `SHA256SUMS`.
- The original N1, N2 and A2-V1 manifests are included at their expected paths.
- The compressed logs and the `0.sca` files are present.
- The A2-V1 seal is included, lists 33 records and has the sha256 `3d00ef8e…49ca0`.
- The original prefix is `/mnt/nasctime-results`.
- No standalone `.ini` file is in the three archives.

| Item | State | Basis |
|---|---|---|
| Release integrity of the three archives | **verified** (maintainer) | release `SHA256SUMS`. Its own sha256 must be supplied for H-3 (M-3). |
| Original manifests at their paths | **verified** (maintainer) | re-checked mechanically by Stage 3 and DV-b1 / DV-a2 |
| Compressed logs, `0.sca` | **verified present** (maintainer) | |
| A2-V1 seal (33 records, `3d00ef8e…`) | **verified** (maintainer) | Stage 3 also requires **exactly** the 33 sealed files under `a2-nack-1/{p0,records,eval}` (extractor E-2) |
| Original prefix `/mnt/nasctime-results` | **verified** (maintainer); consistent with the committed records | e.g. `fixtures/a2v1-first-chain.meta.json` |
| `.ini` files | **not needed** | no reviewed evaluator opens one (runbook §8.1) |
| The PCAP and NW-TT CSV files that `Run72` opens to derive the node ids | **not yet confirmed** | They are raw outputs, so they should be manifest entries. The maintainer's check covered the manifests, logs and `.sca`. Stage 3 checks them before any evaluation; if they are absent, `hrq` refuses (exit 2). |
| Every manifest entry at its exact name, uncompressed | **not yet confirmed** | Stage 3 strict presence. The smoke outputs were "held uncompressed" by the runner, and the A2-V1 extractor already requires exact names. |
| Smoke evidence seals (`s5-smoke-1-` / `s5-n2-1-evidence.sha256`) | unknown; optional | verified if archived, recorded either way |
| Archive format and stored prefix | to be read by `extract_checked.py` | supported: tar (plain / gz / xz / bz2), zip; stored prefix none or `mnt/nasctime-results/` |
| Sealed S1 archive (`3fa12389…`) | **not required** | only for the optional, informational G0RO-H |

## 2. Is any configuration file required? (from the reviewed code at `C`)

**No.** The full trace is in runbook §8.1:
- The H-ARQ process count comes from the configuration **name** (`check_m2s72_s5v.parse_name`, code).
- The UE-to-node mapping comes from the `.sca` `nrMac macNodeId` records, read through `m2s72_runs.Run72`.
- No evaluator in the chain opens an `.ini` file; a search of the chain at `C` finds no `.ini` reference.

**What is required beyond the logs and `.sca` files:**
- `Run72`'s constructor also opens the run's PCAP directory and parses the PCAPs of `listener`, `nwTt` 0 / 1 and `upf` 1, and the `dsTt[k]`, `talker[k]` and `ue[k]` PCAPs, which determine N.
- It also reads two NW-TT CSV logs.
- These must exist and parse, or the node ids are unavailable and `hrq` **refuses** (fail-closed, exit 2).

**This path is untested on genuine trees.** The WP-A1 suite replaces `inputs()` in memory, so the genuine node-id path has only run on the VM (S1 used it on the A2-V1 tree). On a dummy tree here, `Run72` took the node ids from the `.sca` and `MAP-UE` cross-checked them.

## 3. What this step adds (all in runbook revision 3)

| Item | Where |
|---|---|
| Exact release SHA-256 verification and extraction-layout commands that keep every original unchanged | runbook §5; `h3-release.sh`, `extract_checked.py` (tested on crafted archives) |
| Independent DR-13 validation protocol (DV-b1 … b3, DV-a1 … a3, DV-x) and its approval record | runbook §6; `dr13-validate.sh` |
| The G0-RO comparison against D-2: accepted evaluators re-run with their D-2 invocation; verdicts, row statuses and exact counts compared with the committed S1 closure and N = 2 smoke records; suites a precondition only | runbook §7; `g0ro-run.sh`, `g0ro_compare.py` |
| Fail-open points resolved (FO-1 … FO-16) | runbook §11 |
| Qualification and validation as separate sessions, so that no evidence is read before gate B in the validation session | runbook §2 |

## 4. Final prerequisites

### Verified

| # | Item |
|---|---|
| V-1 | The three archives match the release `SHA256SUMS` (maintainer) |
| V-2 | The original manifests, compressed logs and `0.sca` are present; the A2-V1 seal is present with 33 records and `3d00ef8e…` (maintainer) |
| V-3 | The original prefix is `/mnt/nasctime-results` (maintainer; consistent with committed records) |
| V-4 | No configuration file is required by the reviewed evaluators (code inspection, §2) |
| V-5 | The reviewed implementation `C` passes GitHub tier-0 11 / 11. The gated P-0 passes on public code. |
| V-6 | The procedure scripts behave as declared on public code and dummy data: Stage 2 GO; H-3, Stages 3 – 6 and DR-13-V stop where dummy data must; the refusal cases were exercised (runbook §13) |
| V-7 | Option C approved as the architecture (step 139) |

### Pending approval or confirmation (maintainer)

| # | Item | Gate |
|---|---|---|
| P-1 | Designate the independent executor (X-1) and the host | A-1 |
| P-2 | Approve `C`, the procedure commit `D` (this runbook revision) and the four sha256 values | A-2 |
| P-3 | Authorise the executor's access to the three archives; supply the sha256 of the release `SHA256SUMS` and the three archive names | A-3 |
| P-4 | After session Q: approve the DR-13 validation record | A-4 |
| P-5 | After session Q: approve the G0-RO record for one image digest | A-5 |
| P-6 | Approve the stop, mismatch and retry rules (runbook §9) | A-6 |
| P-7 | Confirm that every manifest entry, in particular the PCAP and NW-TT CSV files `Run72` needs, is in the archives under its exact name. Otherwise Stage 3 stops, as designed. | readiness |
| P-8 | `xa` non-gating (M-7); X-7's applicability (M-8) | — |

### Missing records and infrastructure

| # | Item |
|---|---|
| M-1 | The **DR-13 validation record**: not yet produced (session Q) |
| M-2 | The **G0-RO environment-equivalence record**: not yet produced (session Q) |
| M-3 | The **ephemeral host**: a container runtime (Docker or Podman, `--mount type=bind`, `--network none`); network for H-1 only; ≈ 2.2 GB for one extraction plus the evidence directory, per session |
| M-4 | The **container image**: Python ≥ 3.11 with git, coreutils, `awk` and `findmnt`, pulled and pinned by digest |
| M-5 | `docker run` through `host-stage.sh` has not been executed anywhere: no container daemon was available here. Its first execution is session Q's H-3 on the executor's host. |

**Assessment: NO-GO.**
- Session Q may start once P-1, P-2 and P-3 are given and M-3 and M-4 exist.
- Session V may start only after P-4 … P-6, with Stage 2 GO.
