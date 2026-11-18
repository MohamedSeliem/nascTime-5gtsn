# nascTime 2.0 — remote execution feasibility and licensing checklist

**Status: revision 4, 18 November 2026 (WP-E4 Phase 3, documentation-only; pending the maintainer's review).** Revision 3 was approved on 17 November 2026 with the maintainer's targeted corrections. Canonical location: `docs/migration/remote-execution-feasibility.md`.

**Revision 4.**
- The checklists of §2 and §3 are kept as written in revision 3 (their "Status" column is the rev-3 state).
- The results of WP-E1, WP-E2 and WP-E3, and the decisions DR-14 … DR-16, are recorded in **§2a**, **§3a** and **§4a**.
- Run identities are in `repository-archive-and-evidence-register.md` §3.

**Revision-3 note, retained:** "Nothing in this document is verified yet." Every item was a check to be done, either by WP-E2 or by the maintainer, before the corresponding tier is enabled. Statements about third-party services and licences are the author's current understanding. Where they are still marked **[verify]**, they are not facts to rely on.

**How to read this revision.**
- Text between *[Superseded (rev. 4)…]* and *[end of superseded text]* is retained revision-3 history. It is **not** an active instruction and **not** the current repository status.
- The current position is given by the "(rev. 4)" text and by the decisions DR-14 … DR-18.
- **WP-E4 (repository consolidation and travel handover) is completed by the documentation pull request that introduces revision 4.**
- **Still open:** release documentation and M4 readiness. These are plan work package **E4** (M4 groundwork: README 2.0, compatibility table, `opp_env` entry, skills, nightly job), which is a different item from WP-E4.

The VM is the currently available independent environment. It is not the only possible one.

## 1. The three mechanisms

| # | Mechanism | Purpose | Can produce | Cannot produce |
|---|---|---|---|---|
| M-1 | Python-only GitHub Actions CI (tier 0) | Regression of checkers, oracles, generators and extractors on synthetic data and committed fixtures | Level 2 for Python work | Any simulation evidence |
| M-2 | Full pinned-stack CI (tiers 1–2): build, configuration resolution, NED loading, short functional runs | Build validation of C++ / NED / ini; "loads and completes" smoke runs | Level 2 for C++ / NED / ini work | Scientific evidence: smoke runs are never acceptance |
| M-3 | Independent remote execution environment (tier 3), hosted or self-hosted | Approved scientific experiments under a pre-declared protocol | Level 3 candidates, **only** if §4 holds and the maintainer accepts the record | — |

## 2. M-1 and M-2 checks (WP-E1 / WP-E2)

| ID | Check | Why | Status (rev. 3; superseded by §2a, not the current status) |
|---|---|---|---|
| F-1 | Measured tier-0 runtime on a hosted runner. Locally: about 3.5 min for 11 suites on 2 cores, 17 Nov. | CI cost and latency | to do (E1) |
| F-2 | A Simu5G `v1.8.1` source checkout in CI (public tag; no build) | A2-0s rows | to do |
| F-3 | Hosted-runner limits for this repository: CPU / RAM, disk free, maximum job duration, concurrent jobs **[verify in GitHub's current documentation and the account's plan]** | A from-source OMNeT++ + INET + Simu5G build is long and disk-heavy | to do (E2) |
| F-4 | Measured full build time and installed size of OMNeT++ 6.5.0 + INET 4.7.0 + Simu5G 1.8.1 + `libnasctime_m2` on that runner | Feasibility | to do (E2) |
| F-5 | Cache strategy and size against the repository's Actions cache quota **[verify]**; cache key = exact versions + build options | Avoid rebuilding on every pull request | to do |
| F-6 | Reproduce the preserved environment remotely. The VM used `opp_env` 0.36.2.261110 with Nix 2.34.4; the configuration, generated flakes and lock files are preserved (private the private environment archive). Check whether a hosted runner can install Nix and realise the same lock **[verify]**. | The most direct route to the same identity; B9 | **input available; reproduction not yet demonstrated** |
| F-7 | Identity check of the CI build against the confirmed target: OMNeT++ 6.5.0; INET 4.7.0 (`dfe270b21f`); Simu5G 1.8.1 unmodified; Clang 21.1.8 / GCC 15.2.0; GNU Make 4.2.1; Python 3.13.13; reference OS Ubuntu 22.04.5 LTS x86_64 | Same identity as the evidence environment. Differences (for example the runner OS) are recorded, not hidden. | input available (H2) |
| F-8 | The VM's NED / INI 6.5.0 corrections (collected: the private VM-compatibility archive), reviewed and applied as default-off commits if they are needed to load the configurations | Otherwise tier 1 may fail for a known local reason | input available; review pending |
| F-11 | Publication of the flake and lock files to the public repository (needed if public CI uses them): content review for local paths or credentials; publication class approval | Private-by-default rule | to do |
| F-9 | Tier-2 smoke duration and output size per configuration (seconds of simulated time) | Keep smoke runs small | to do |
| F-10 | Upstream source unmodified: the build uses the official tag or tarball, with a checksum recorded in the job log | The zero-modification rule | in every job |

## 2a. Results of M-1 and M-2 (rev. 4)

| ID | Result (rev. 4) |
|---|---|
| F-1 | Tier-0 on a hosted runner: job duration 89 s for the 10 declared suites (PR #4, run 44118333251) |
| F-2 | Done: Simu5G `v1.8.1` source checkout with a fail-closed commit gate (`7477d266…`) in tier-0 |
| F-3 | Measured on `ubuntu-22.04` hosted runners (tier-1 and E3 runs). The completed jobs used about 11 GB of peak disk with more than 77 GB free above the STOP threshold, a minimum available memory of about 14 GB, and about 26–40 minutes per run. Plan limits and concurrency remain **[verify]**. |
| F-4 | Release builds (E3b-R1 run): OMNeT++ about 446 s, INET about 1253 s, Simu5G about 345 s, `libnasctime_m2` about 25 s. Installed sizes are in the tier-1 diagnostics. |
| F-5 | No cache is used. Every run builds from the pinned release assets (deliberate: no cached binaries). |
| F-6 | **Demonstrated (build):** Nix 2.34.4 and `opp_env` 0.36.2.261110 realise the approved lock on a hosted runner (E2b.1; tier-1 C-1, C-2) |
| F-7 | **Recorded:** the tier-1 identity rows (C-1, C-10, C-12). Runner-image differences from the VM are recorded, not hidden. |
| F-8 | Not needed for the configurations exercised so far: `M2S4U`, `M2S5` and the two reviewed wrapper queries loaded on 6.5.0 without the VM's NED / INI corrections. Their review remains **pending** for every other configuration. |
| F-9 | Hosted functional runs: E3a (`M2S4U`, 3 s simulated) and E3b-R1 (`M2S5`, 5 s simulated; wall time 0.925 s; 13 087 127 B of outputs). |
| F-10 | In every job: release assets pinned by SHA-256; upstream sources unmodified (tier-1 C-3) |
| F-11 | The approved lock is public as `ci/tier1/flake.lock` (pinned by `LOCK_SHA256` in `ci/tier1/pins.env`), after review. The remaining private environment material stays private. |

**Tier boundaries (DR-14, DR-15).**
- **M-1 (tier-0)** is integrated and **required** at repository-ruleset level.
- **M-2 tier-1** is integrated and **not mandatory** at ruleset level.
  - It runs automatically for relevant **non-draft** pull requests. The label `tier1:run` is an override, including for drafts.
  - It validates the release build, linkage and **its specific reviewed configuration queries**. It does not automatically validate every newly introduced NED or INI configuration.
- **M-2 tier-2** (hosted functional simulation):
  - It exists only as the experimental harness frozen on `wp-e3/e3b-r1-publication`.
  - Each run must be **individually authorised and bounded**; there is no automatic integration.
  - Its results are level-2 development smoke evidence (E3a: wired timing functionality; E3b-R1: the downlink 5G–TSN timing path).

**Negative controls.**
- **Tier-0:** both controls failed at their intended hosted gates.
- **Tier-1 (N-1, N-2):** N-1 and N-2 failed during the **offline self-tests** of their hosted runs, so those hosted runs **never reached** the downstream gates they target. Those gates are the lock-identity gate (N-1) and the C-5 SYS_LIBS gate (N-2). Both gates **passed** in the positive hosted tier-1 runs: PR #7 and the C-1 … C-12 prerequisites of E3a, E3b and E3b-R1. Their negative (rejecting) behaviour was tested **offline** by the tier-1 self-tests.

## 3. Licensing and security checks

| ID | Check | Note |
|---|---|---|
| L-1 | **OMNeT++ licence.** Building and running OMNeT++ on hosted CI, caching the built tree and keeping logs, under the maintainer's academic use **[verify against the licence text distributed with OMNeT++ 6.5.0]** | The author understands OMNeT++ to be distributed under its own Academic Public License for non-commercial use. Not verified. |
| L-2 | **INET 4.7.0 and Simu5G 1.8.1 licences** **[verify each project's `LICENSE` file]** | Understood to be LGPL. Obligations matter mainly if binaries are redistributed. |
| L-3 | **No redistribution of built binaries** (release assets, public artifacts, container images) until L-1 and L-2 are cleared | Caches are not public artifacts, but check whether caches or artifacts of a public repository are downloadable by others **[verify]** |
| L-4 | nascTime's own `LICENSE.txt` at the repository root is unchanged by any CI work | — |
| S-1 | **No persistent personal VM runner on the public repository** (maintainer instruction, 17 Nov). Self-hosted runners on a public repository can run code from pull requests, including from forks; GitHub's documentation advises against this **[verify current guidance]**. Any other self-hosted runner needs explicit approval and must be ephemeral, with no persistent credentials, restricted to protected workflows that the maintainer starts manually, and never triggered by pull requests. | security |
| S-4 | Access to the private evidence repository is **never assumed**. **DR-12 (17 Nov): none for the initial remote development agent.** Any future access is configured by the maintainer with real access controls (scoped, read-only credentials; not instructions alone) and verified by a checksum read before use. | security / privacy |
| S-2 | No secrets exposed to pull-request workflows | security |
| S-3 | Private evidence (the evidence repository) never uploaded by public workflows | privacy |
| C-1 | **Cost.** Hosted minutes, larger runners or cloud VMs, and storage for campaign outputs: E0v-N bracket about 60–200 GB cumulative; Stage 5 total 290–470 GB cumulative, peak 6 GB or less, with tiered deletion (plan rev. 1.1 §4.3). Budget approved by the maintainer before use. | cost |

## 3a. Licensing and security results (rev. 4)

- **L-1 / L-2, decided by DR-16.** The maintainer confirms academic-use scope for current nascTime development and simulation, including building and running OMNeT++ 6.5.0, INET 4.7.0 and Simu5G 1.8.1 in hosted CI. Commercial use is outside the current scope.
- **L-3 remains in force: no compiled framework binary is redistributed.** The tier-1 and tier-2 publication checks refuse executables, shared objects and archives in every published artifact.
- **S-1, S-2, S-3:** unchanged and respected. There are no self-hosted runners and no secrets in pull-request workflows. Private evidence never enters public workflows.
- **S-4:** unchanged (DR-12). The development agent has no access to the private evidence release.

## 4. Conditions under which remotely executed experiments could be independently accepted (M-3)

An experiment executed outside the VM can be a level-3 candidate only if **all** of the following hold. The maintainer retains final acceptance authority.

| ID | Condition |
|---|---|
| X-1 | **Independence of the executor.** The run is started by the maintainer, or by an executor the maintainer designates who is not the development agent. The tier-3 workflow and runner configuration live on a protected branch with the maintainer as code owner. The development agent has no write access to them, cannot trigger them, and cannot change their inputs after approval. |
| X-2 | **Pre-declared protocol.** Criteria, predictions, stop conditions and exact commands are committed and approved **before** the run, as for every accepted VM protocol (for example `M2-S7.2a-a21-s1-protocol.md`). |
| X-2a | **Evidence inputs from the private evidence archives**: re-verified against the archive checksum manifest and the original manifests after extraction. Paths are resolved by a read-only mount at the original prefix (evaluation) or by in-memory mapping (integrity verification), never by rewriting a manifest or modifying evidence (DR-13). **The method is validated before any independent evaluation (DR-13 decision).** |
| X-3 | **Pinned inputs.** The nascTime commit SHA, the generated-configuration hash (regeneration check), the configuration names and the seeds are recorded in the run record and match the protocol. |
| X-4 | **Environment identity and equivalence.** An identity record (OMNeT++ build id, INET and Simu5G versions, library hashes, compiler, OS, Python), in the form of the runner-written `env*.txt` / `stack.txt` and the G0 record §1. Before the first acceptance-bearing run on a new environment, a **G0-style verdict-equivalence record** against the D-2 environment must be approved. Like the original G0, it is verdict equivalence, not a hash-identity claim. |
| X-5 | **Sealed outputs.** Raw-output manifests (sha256 and size) and durable records are written by the run lifecycle before any deletion (the Stage 5 tier rules, plan §4.2). The seal hash is recorded **at sealing time** (the lesson of D-F3-1). Records and seals are transferred to the private evidence repository with checksums. |
| X-6 | **Read-only, fail-closed evaluation** with reviewed tools at a pinned commit, writing to fresh directories. No retries. A failed or stopped run is preserved and reported as found. |
| X-7 | **Reproducibility check.** One run per batch is re-executed and must reproduce its committed manifest hashes within the same environment (numerical repeatability, plan RD-3). Cross-environment differences are handled by X-4, not by this check. |
| X-8 | **Security and cost:** S-1, S-2, S-3 and C-1 satisfied. |
| X-9 | **Maintainer acceptance.** The maintainer reviews the record and accepts it. Until then, the run's status is "executed, not accepted". |

**Not eligible for level 3:** any run started or modified by the development agent, any tier-1 or tier-2 CI run, and any run without a pre-declared protocol.

### 4a. Hosted experiments and level 3 (rev. 4)

E3a and E3b-R1 were started by the development agent. Under X-1 they are **not eligible for level 3**, and they are not independent scientific acceptance. M-3 is unchanged: an independent scientific executor is still required for qualifying scientific evidence.

## 5. Decision points for the maintainer

1. Approve tier 0 (M-1).
2. Approve the investigation of tiers 1–2 (WP-E2) and, after F-1…F-10 and L-1…L-3, their enabling.
3. Decide whether to investigate M-3 options (a hosted larger runner, a university machine or a cloud VM), and under which budget.
4. Designate who may act as independent executor (X-1) besides the maintainer, if anyone.

**Rev. 4:**
- Items 1 and 2 are decided by DR-14: tier-0 required, tier-1 integrated and not mandatory.
- Hosted tier-2 runs are permitted only when individually authorised (DR-15).
- Items 3 and 4 remain **open**.
