# nascTime 2.0 migration — authoritative status (handover)

**Status: revision 5, 24 November 2026 (step 160 roadmap reconciliation, documentation-only; pending the maintainer's review).** Revision 4 (18 November 2026, WP-E4 Phase 3) was merged with PR #10. Revision 3 was approved on 17 November 2026 with the maintainer's targeted corrections.

**Two baselines are distinguished in this revision:**

| Baseline | Date | Integration head | Marked |
|---|---|---|---|
| **18 November baseline** (rev. 4) | 18 Nov 2026 | reviewed pre-E4 baseline `290babb`; rev. 4 merged by PR #10 | unmarked or "(rev. 4)" text |
| **24 November reconciliation** (rev. 5) | 24 Nov 2026 | `m2/continuation` at `3b2c2941ef297cb20051798fd1ad3ed8dea69c20` (the WP-A1 merge, PR #11) | "(rev. 5)" text and the new **§9** |

Revision 5 records:
- the M2-B implementation increments M2B-1 … M2B-5 (PRs #12 … #16), mapped onto the original work packages B1 … B7;
- the integration of WP-A1 (PR #11) at level 2;
- a reconciliation of every original milestone against the repository at `3b2c294` (§9), using the status vocabulary CLOSED / IMPLEMENTED / PARTIAL / NOT STARTED / DEFERRED / BLOCKED;
- the companion plan for the remaining work, `docs/migration/remaining-work-roadmap.md` (new in rev. 5).

Revision 5 **changes no code, configuration, CI workflow, evaluator, fixture, result or frozen record**, accepts no open scientific criterion and records **no new maintainer decision**. A merged pull request is never treated as scientific acceptance. Rev-4 text that rev. 5 supersedes is kept and labelled, as before.

**Previous header (rev. 4), retained:** *Status: revision 4, 18 November 2026 (WP-E4 Phase 3, documentation-only; pending the maintainer's review).* Revision 3 was approved on 17 November 2026 with the maintainer's targeted corrections.

Revision 4 records:
- the integrated tier-0 and tier-1 CI;
- the hosted functional simulation experiments E3a, E3b and E3b-R1;
- the repository consolidation (four permanent branches, 30 annotated tags);
- the decisions DR-14 … DR-18.

Revision 4 changes are marked "(rev. 4)". Revision-3 text that is superseded is kept and labelled, not deleted.

**How to read this revision.**
- Text between *[Superseded (rev. 4)…]* and *[end of superseded text]* is retained revision-3 history. It is **not** an active instruction and **not** the current repository status.
- The current position is given by the "(rev. 4)" text and by the decisions DR-14 … DR-18.
- **WP-E4 (repository consolidation and travel handover) is completed by the documentation pull request that introduces revision 4.**
- **Still open:** release documentation and M4 readiness. These are plan work package **E4** (M4 groundwork: README 2.0, compatibility table, `opp_env` entry, skills, nightly job), which is a different item from WP-E4. This record changes no code, configuration, test, evidence or historical record.

**Canonical location after approval:** `docs/migration/authoritative-migration-status.md` in the repository. Repository files are cited by repository path. Documents cited by bare name (for example `migration/revised-migration-roadmap.md`) are **private planning documents** unless `docs/migration/document-index.md` lists them as published. They are cited for traceability; the maintainer provides reviewed extracts on request (DR-12).

**Purpose.** This record reconciles the original migration roadmap with what has actually been implemented and accepted. It gives a development agent one place to see, for every milestone and stage:
- the original scope and acceptance criteria;
- the current implementation status;
- the accepted evidence, with commits;
- the remaining work;
- dependencies and blockers;
- whether the work can proceed remotely;
- whether independent simulation evidence is still required.

**Milestone numbering is the original one** and is not changed here. The sources are:

| Numbering | Source |
|---|---|
| Phase 0, M1 (Phase 1), M2 (Phase 2), M3 (Phase 3, FRER), M4 (Phase 4, release 2.0), Phase 5 (upstream-gated), Phase 6 (tracking) | `migration/revised-migration-roadmap.md` §2 |
| M2 sub-stages S0–S8 | `migration/m2-s2-design.md` §7 |
| S7 substeps S7.1 to S7.4b | `migration/m2-s7-roadmap.md` rev. 2.2 §1 |
| S7.2a implementation stages 1–9 | `migration/m2-s7.2a-design.md` §11 |

**Execution terms used in this record:**

| Term | Meaning |
|---|---|
| "Remote" | Development and CI validation by a GitHub-based agent |
| "Independent evidence" | A simulation or evaluation executed in an **independent execution environment** under a pre-declared, approved protocol, and accepted by the maintainer |
| "The VM" | The environment currently available for that: the maintainer's validation VM |

Other independent environments are possible only after the conditions in `remote-execution-feasibility.md` §4 are verified and approved. Final scientific acceptance stays with the maintainer.

Every discrepancy between these sources is listed in `migration/migration-decisions-register.md` (DR-01 … DR-13) and is resolved there by dated Decision lines (17 Nov 2026). This record applies those decisions; the open parts are marked.

---

## 0. Repository and evidence baseline

### 0.1 Branches

**Current state (rev. 4, 18 Nov 2026; DR-17).**
- **Permanent branches.** Exactly four remain:
  - `m2/continuation` (integration). **Reviewed pre-E4 integration baseline:** `290babba3d12942344a2153f9ea5ea54287df366`. This is not a permanent head: the live head advances when this documentation PR is merged, and with every later merge. New work starts from the current head;
  - `master` at `9e8bc83dfdfaffd918eb304bda6b8ecb98ff0684` (frozen legacy provenance);
  - `m1/ethernet-bridge` at `fbe41a9e9ba1befc0d68b9fd559be52b024c1ca9` (frozen M1 provenance);
  - `wp-e3/e3b-r1-publication` at `edf3329ddf2350650fd0957ddd5a965fe3ddbb56` (frozen experimental tier-2 harness).
- **Tags.** The other 26 branches were deleted on 18 November 2026, after 28 annotated `archive/*` tags preserved their heads. 30 tags in total, with `v1.0` and `v1.0.1` unchanged.
- **Register.** The complete branch / tag / commit mapping, and how to resolve a historical branch name, is in `docs/migration/repository-archive-and-evidence-register.md` §2.
- **History.** `m2/continuation` shares **no history** with `master`. Its only root is the snapshot `14d5e0f` (DR-18).

**Current state (rev. 5, 24 Nov 2026).**
- **Integration head:** `m2/continuation` at `3b2c2941ef297cb20051798fd1ad3ed8dea69c20`, the merge of PR #11 (WP-A1). The live head advances with later merges.
- **Merged since the 18 November baseline** (each by a merge commit into `m2/continuation`):

| PR | Increment | Merged | Head merged | Level |
|---|---|---|---|---|
| #11 | WP-A1: A-2.1 integration wrapper for E0v-N and the prepared independent-validation procedure | 24 Nov | `0b7da11` (merge `3b2c294`) | 2 |
| #12 | M2B-1: TSN AF offline compiler, S-CFG/1 | 23 Nov | `0655cee` (merge `1580a95`) | 2 |
| #13 | M2B-2: TT gate clock adapter (S-CLK) and offline bridge-delay observer (S-OBS) | 24 Nov | `1d03822` (merge `690b5bf`) | 2 |
| #14 | M2B-3: opt-in IEEE 802.1Qbv egress gating (S-CFG/2) | 24 Nov | `c6e82ed` (merge `8771095`) | 2 |
| #15 | M2B-4: TAS-compatible egress pairing; bridge residence under TAS | 24 Nov | `388826c` (merge `9781291`) | 2 |
| #16 | M2B-5: common-epoch TAS schedule alignment | 24 Nov | `09cffb4` (merge `f8bf10c`) | 2 |

- **Branches.** The four permanent branches are unchanged (`git ls-remote`, 24 Nov). The feature branches of PRs #11 … #16 are no longer on the remote; their content is reachable from `m2/continuation`. In particular the WP-A1 reviewed implementation commit `C` = `f3f68be` and the tested procedure commit `544c093` are ancestors of `3b2c294`, which the validation procedure requires (runbook §1, `h1-setup.sh`).
- **Tags:** 30, unchanged.
- **Open pull requests:** #2 and #3, both from an external fork and both against the frozen `master` (legacy line): uplink reflective QoS (#2, head `1501a50`, the source of the retained DS-TT VLAN translation task) and two-gNB uplink FRER demos (#3). Neither can be merged into `master` under DR-18; their disposition is a maintainer decision (§9.6).

**Historical table (rev. 3, 17 Nov 2026), retained.** The column "Archived as (rev. 4)" gives the tag that now preserves each deleted branch's head; the rev-3 text is otherwise unchanged. These commits come from the maintainer's independent audit of 17 November 2026. They are not re-verified by this record, because the authoring clone holds only the `m2/*` and `plan/*` branches.

| Branch (GitHub `MohamedSeliem/nascTime-5gtsn`) | Commit | Content | Archived as (rev. 4) |
|---|---|---|---|
| `master` | `9e8bc83` | Frozen legacy line (tag `v1.0.1`). **Never merged into.** | branch retained (frozen) |
| `m1/ethernet-bridge` | `fbe41a9` | M1 closure (`migration/m1-plan.md` status line) | branch retained (frozen); also `archive/m1/ethernet-bridge-closed` |
| `m2/architecture` | `14d5e0f` | M2-S0…S6, S7.1, S7.2a CP1/CP2 and E0 on Simu5G 1.8.0 (`migration/m2-simu5g-1.8.1-audit-and-plan.md` §0, §1.1) | `archive/m2/architecture-snapshot-1.8.0` |
| `m2/simu5g-1.8.1` | `2586bce` | M2-R181 / R181b / R181c, accepted (`migration/m2-r181-acceptance-record.md`) | `archive/m2/simu5g-1.8.1-r181-accepted` |
| `plan/m2-s7.2a-stage5` | `57fa0c5` | Stage 5 plan rev. 1.1. **Not an ancestor** of the development line (DR-11). | `archive/plan/m2-s7.2a-stage5-rev1.1` |
| `m2/s72a-stage5` | `86d7599` | S5-1, G0 record rev. 1 | `archive/m2/s72a-stage5-s5-1` |
| `m2/s72a-g0` | `04657b4` | G0 record CLOSED (D-2 condition) | `archive/m2/s72a-g0-closed` |
| `m2/s72a-s5-smoke` | `bc77a6f` | N = 1 smoke preparation | `archive/m2/s72a-s5-smoke-n1-prep` |
| `m2/s72a-s5-2` | `decf848` | S5-2 per-UE evaluation | `archive/m2/s72a-s5-2` |
| `m2/s72a-s5-n2` | `06fba26` | N = 2 smoke preparation, XA | `archive/m2/s72a-s5-n2-prep` |
| `m2/s72a-a2-design` | `07b09b9` | A-2 design review, probe P0 | `archive/m2/s72a-a2-design` |
| `m2/s72a-a2` | `fbee202` | A-2, frozen | `archive/m2/s72a-a2-frozen` |
| `m2/s72a-a2d2` | `612f353` | A2-V1 design and protocol r1.1 | `archive/m2/s72a-a2d2-a2v1-not-accepted` |
| `m2/s72a-a21` | `115012f` | A-2.1, F3, S1, S1 closure | `archive/m2/s72a-a21-closed` |
| **`m2/s72a-a21-fixture`** | **`033c3ed3fbc5b6ee21271ce24c62084283d8e79b`** | **Approved continuation baseline (DR-11):** `115012f` plus the three genuine F3 fixture files under `simulations/m2/check/fixtures/` (fixture sha256 `cfb05ff7…6e65b`). No implementation is changed. | `archive/m2/s72a-a21-fixture-baseline` |
| **`m2/continuation`** | E0 tip: given in the delivery note. A commit cannot contain its own hash. | **Integration branch** (DR-11), created from `033c3ed`. The E0 commit adds documentation only: the public handover set under `docs/migration/`, and the Stage 5 plan selectively imported from `57fa0c5`. | branch retained (integration); reviewed pre-E4 integration baseline `290babb` (rev. 4; the live head advances with merges) |
| `v1.5.0-migration` | `91ad643` | Stale, unrelated history (`migration/legacy-baseline-manifest.md` §1) | `archive/legacy/v1.5.0-migration` |

The local clone also has `m2/s72a-a2f1` at `13b0fb4`, which holds F1 rev. 2. The maintainer's list does not include it. It is an ancestor of `m2/s72a-a21`, so its content is reachable there.

### 0.2 Stacks

| Role | Stack | Source |
|---|---|---|
| Accepted 1.8.0 baseline (M1, M2-S0…S7.1, S7.2a CP1/CP2/E0) | OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0 | `migration/m1-closure-report.md`; audit §0 |
| Accepted 1.8.1 migration evidence | OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.1 | `migration/m2-r181-acceptance-record.md` §1.1 |
| Stage 5 reference environment (decision D-2) | OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, unmodified | `migration/m2-s7.2a-s5-env-decision.md`; G0 record rev. 3 |
| Release pin (M4) | **Decided (DR-01, 17 Nov):** OMNeT++ 6.5.0 / INET 4.7.0 / unmodified Simu5G 1.8.1 for the remainder of M2, M3 and M4. The roadmap text (6.4.0 / 4.7.0 / 1.8.0) is preserved; historical stack-qualified records are unchanged. | `migration/revised-migration-roadmap.md` §0 item 5 |
| **Target environment for the remaining work** (confirmed by the maintainer, 17 Nov; adopted for M2 / M3 / M4 by DR-01) | OMNeT++ 6.5.0; INET 4.7.0 (`dfe270b21f`); Simu5G 1.8.1, unmodified; `opp_env` 0.36.2.261110; Nix 2.34.4; Clang 21.1.8; GCC 15.2.0; GNU Make 4.2.1; Python 3.13.13; Ubuntu 22.04.5 LTS, x86_64 | maintainer statement, 17 Nov. The environment configuration, generated Nix flakes and lock files are preserved in a private archive. ~~Remote reproducibility has not yet been demonstrated.~~ **(rev. 4) Remote *build* reproducibility is demonstrated:** tier-1 (PR #7, C-1 … C-12) builds this stack, release only, from the approved lock (`ci/tier1/flake.lock`) on GitHub-hosted `ubuntu-22.04` runners. Differences from the VM identity are recorded in the tier-1 rows. Remote *scientific* reproducibility is **not** claimed (§8). |
| Legacy workspace (recovered, H2) | OMNeT++ 6.4.0; INET 4.6.0; nascTime `v1.0.1` (`9e8bc83dfdfaffd918eb304bda6b8ecb98ff0684`); customised Simu5G 1.5.0 at `31c38c176bd91d1bb88e883931bded825ad9cc8f` (tag `nasctime-v1.0`), whose working tree carries two further uncommitted functional corrections, preserved privately as a patch | maintainer statement, 17 Nov; private legacy-provenance archive |

### 0.3 Evidence locations

| Evidence | Location | Accessible to a remote agent |
|---|---|---|
| Records, checkers, protocols, closure reports | the branches above (`simulations/*/results/`, `simulations/*/check/`) | yes, on GitHub |
| Planning and design documents (roadmaps, designs, protocols) | Private planning documents. Reviewed ones are published under `docs/migration/` only after a content review (`document-index.md`) | published ones: yes; private ones: no (DR-12). Reviewed extracts are provided selectively by the maintainer. |
| Genuine F3 fixture (A2-V1 prefix, 181 153 lines) | `m2/continuation:simulations/m2/check/fixtures/` (rev. 4; originally committed at `033c3ed`, now tag `archive/m2/s72a-a21-fixture-baseline`) | yes |
| Private evidence | a private, access-controlled evidence archive maintained by the project owner (identity verified by the maintainer) | **no** for the initial remote agent (DR-12) |
| Sealed S1 archive | private evidence archive; archive sha256 `3fa12389…f0e34` | no |
| **N = 1 smoke, N = 2 smoke and A2-V1 raw evidence (H1, completed)** | private, checksum-manifested archives (N = 1 smoke, N = 2 smoke, A2-V1). Verified before packaging against the original manifests: N1 41 files / 720 571 149 B; N2 58 files / 748 297 469 B; A2-V1 58 files / 740 917 765 B; 157 files in total, zero integrity failures. All three archives were re-downloaded from their private storage and verified against the archive checksum manifest. | no. Path resolution after extraction: §0.4 |
| **Supplementary pre-departure archives (H2, completed)** | private supplementary archives (environment, F3 evidence, legacy provenance, VM compatibility), each checksum-verified | no |
| Legacy datasets: multi-endpoint, FRER, bridge and NW-TT result sets | **the VM only**. An inventory of 79 legacy experimental files and the historical migration records are in the private legacy-provenance archive. Their relationship to the published experiments is **unverified**. | **no** |
| Other larger raw datasets (E0, CP2 campaign outputs) | the VM only; not collected | **no** |
| **Hosted CI and experiment evidence (rev. 4)** | GitHub Actions artifacts (7-day retention; **scheduled to expire on 24–25 Nov 2026**), job logs. The 11 artifact ZIP archives were downloaded, verified against their GitHub SHA-256 digests and preserved by the maintainer in a private evidence release (the maintainer's statement). Register: `repository-archive-and-evidence-register.md` §3–§4. Job-log exports and the internal raw-manifest verification are **pending**. | identities and digests: yes (register); archives: no (DR-12) |

No further VM collection is planned before departure.

### 0.4 Resolving absolute paths after remote extraction

The original manifests record absolute VM paths: `<results-root>/…` for runs and `<vm-home>/…` for the F3 directories. They are part of the sealed evidence and are **never edited or regenerated**. Two methods are permitted, and the chosen one is stated in every verification record:

1. **Mount at the original path (preferred for tools).** Extract the archive into a directory and make it visible read-only at the original absolute prefix, for example with a container bind mount (`-v <extract-root>:<results-root>:ro`). Existing reviewed tools then run unchanged. This includes `m2s72_a21_fixture.py`, whose E-3 gate requires every manifest path to resolve inside `<R>/a2-nack-1/runs`.
2. **In-memory prefix mapping (verification only).** Read the original manifest and substitute the recorded prefix with the extraction root in the stream, without writing a modified manifest. For example: `sed "s#  <results-root>/#  $X/#" MANIFEST | awk '{print $1"  "$3}' | sha256sum -c`.

Rules:
- A tool that refuses a mapped path (a fail-closed path check) is reporting correct behaviour. It must not be weakened. Use method 1 instead.
- A verification is valid only if every file listed in the original manifest is checked, with the hash and size recorded there.

---

## 1. Phase 0 — Freeze and baseline

| Item | Content |
|---|---|
| Original scope | Tag `legacy-v1.0` with fork `nasctime-v1.0`. Create branch `legacy/1.x`. Archive every published and submitted result set (including arXiv:2604.04616) with configurations, seeds and scalars. Record the debug content of `nasctime-v1.0`. Locate the fingerprint suite (B8). Source: roadmap §2 Phase 0. |
| Acceptance | Each archived result regenerates bit-identically from the tag on a clean build, and a reproduction script is committed on `legacy/1.x` (roadmap §2 Phase 0). |
| Status | **Open.** The public part is pinned: `v1.0` → `f03e38d` and `v1.0.1` → `9e8bc83` (maintainer audit). Neither `legacy-v1.0` nor `legacy-snapshot-2026-10-12` exists. No `legacy/1.x` branch is listed.<br>**Provenance collected (H2, completed):** the legacy workspace stack (§0.2); two uncommitted Simu5G corrections, preserved privately as a patch; an inventory of 79 legacy experimental files; the historical migration records (the private legacy-provenance archive). |
| Accepted evidence | None for reproduction. Bit-identical reproduction is **not** claimed. |
| Remaining | 1. Map each published or submitted result set to its source identity and data (DR-06). The relationship of the VM datasets to the published experiments is **unverified**.<br>2. **DR-06b (17 Nov):** preserve the complete legacy datasets (about 5.5 GB multi-endpoint, 674 MB FRER, bridge and NW-TT results) when VM access resumes. **They are on the VM only until then, and that risk of loss is recorded.**<br>3. Reproduce bit-identically on the legacy stack. |
| Dependencies / blockers | The legacy stack is OMNeT++ 6.4.0 / INET 4.6.0 / the customised Simu5G 1.5.0 plus the working-tree patch. This resolves, **for this workspace**, the 6.3-or-6.4 conflict in manifest §2; whether it is the stack of each paper is part of the mapping. B8 (fingerprint suite): see the inventory. |
| Patches | The two legacy working-tree corrections are **historical provenance only**. They are not ported to the new stack, which takes no upstream modification. Their relation to upstream fixes is not assessed here. |
| Remote | Only the documentation reconciliation. No tags may be created (maintainer instruction, 17 Nov). |
| Independent evidence required | **Yes**: bit-identical regeneration on the legacy stack. |
| Rule | M1 did not wait for Phase 0 (manifest, "Rule"), and nothing later does either. Phase 0 is **not** declared closed. |

## 2. M1 (Phase 1) — Minimal bridge on vanilla Simu5G 1.8.0

| Item | Content |
|---|---|
| Original scope / acceptance | Roadmap §2 Phase 1: functional, protocol and experimental rows plus the seam grep gate. Stages S0–S5 are in `migration/m1-plan.md`. |
| Status | **CLOSED 2026-10-13**, on `m1/ethernet-bridge` at `fbe41a9` (`m1-closure-report.md`; `m1-plan.md` status line). One observation remains open and non-blocking: O-S0-1, the uplink delay pattern. |
| Accepted evidence | S0 `9138d83`, S1 `0226e56`, S2 `db81377`, S3 `ea05c1a`, S4 `ef500cd`, S5 `b7918ff` (`m1-plan.md`); records in `simulations/m1/results/`. On 1.8.1, the version-appropriate rows (S5-*-v, O1-cons, OT-strand) were accepted in `m2-r181-acceptance-record.md` §1.2, with the historical FAILs kept. |
| Remaining | O-S0-1 (observation only). |
| Remote | Not applicable. |
| Independent evidence | Already given (R181 on 1.8.1; G0 on 6.5.0, verdict level). |

## 3. M2 (Phase 2) — nascTime bridge functions

**Original scope** (roadmap §2 Phase 2):
- TT ports: timestamping, residence time, INET Qbv at the ports, optional hold-and-forward;
- gPTP time-aware relay, with `GptpSideband` as a labelled baseline;
- TSN AF: an offline compiler and a runtime observer;
- multi-endpoint operation;
- a `StaticBmca` port.

**Acceptance** (same section):
- *functional:* every legacy G1–G6 and S1–S8 capability has a 1.8-based scenario or a "retired, replaced by X" entry;
- *protocol:* gPTP offset equals the clock model; `correctionField` equals the measured residence; TAS gates are observed;
- *experimental:* a legacy vs 1.8 statistical comparison, with every difference attributed;
- *regression:* the fingerprint suite is recorded on 1.8.0.

**Legacy capability definitions: recovered from the legacy README.** The roadmap's "G1–G6 and S1–S8" are the feature tables of `README.md` at `master` / tag `v1.0.1` (`9e8bc83`, last changed 2026-07-24), section "Completed Features" (lines 114–143 of that file). The same tables also list the hardening items H1–H6 and the FRER items F1–F4. The README maps the legacy tests to them (lines 484–503).

**Disposition of every legacy capability** (DR-02 decision, 17 Nov). Each is either a migration task, a retirement or an explicit deferral.
- **Approved retirements:** H1, H2, S1 and S3. They are approved as implementation retirements, *subject to coverage of the replacement behaviour*.
- **Pending:** the H5 retirement, until an equivalence analysis covers the streaming PHY and its timing implications.
- **Approved deferrals:** F3 and F4, to Phase 5.
- **Retained in M2-B:** DS-TT VLAN translation. "Covered" means that a 1.8 counterpart exists; a coverage-evidence entry in the B1 table is still required.

| ID | Legacy capability (README `v1.0.1`) | Legacy evidence | Disposition (DR-02, 17 Nov) | 1.8 counterpart or task |
|---|---|---|---|---|
| G1 | NW-TT and DS-TT bridge port modules | `tests/nwtt_test`, `tests/bridge_test` | **Covered** | M1 pass-through TTs; M2-S0…S5 TT ports (`src/nasctime/m2`) |
| G2 | gPTP tunnel transport (sideband + L2-in-GTP-U) | `tests/gptp_test` | In-band part **covered**; sideband: **task** | In-band gPTP over the Ethernet PDU session (M1 S4). `GptpSideband` as a labelled idealised baseline (roadmap Phase 2): task in M2-B (WP B2) |
| G3 | Residence-time correction (transparent clock) | `tests/gptp_test` | **Covered** | M2-S3…S6 |
| G4 | QoS mapping (PCP ↔ 5QI) with SDAP DRB selection | `tests/qos_test` | **Covered** | M1 S3 (PCP → QFI → DRB, native Simu5G QoS rules); S7.1 |
| G5 | TSN AF / CNC configuration | `tests/qos_test` (`cnc_config.xml`) | **Task** | M2-B TSN AF offline compiler and runtime observer (WP B2, B3, B6) |
| G6 | Static BMCA (clock hierarchy management) | `tests/qos_test`; multi-endpoint demos | **Task** (DR-03) | Offline validator (WP B4), subject to the equivalence analysis |
| H1 | Dynamic pppIf interface-ID lookup | — | **Retire — approved** (subject to replacement-behaviour coverage) | The PPP / IP transport between the TTs and the UPF is replaced by the native Ethernet PDU session (inventory §3: NW-TT restructured as Ethernet-only) |
| H2 | DS-TT unicast MAC address resolution | — | **Retire — approved** (subject to replacement-behaviour coverage) | Replaced by native Ethernet bridging with MAC learning at the UPF (M1 S1) |
| H3 | NW-TT egress path (bidirectional traffic) | — | **Covered** | M1 S1 (unicast in both directions); M2-B data plane for the multi-endpoint case |
| H4 | Robust gPTP message-type handling | — | **Covered** for Sync / Follow_Up / Pdelay; Announce is a **task** | M2-S4 / S5 TT gPTP frame handling; Announce containment C-1 in S7.4a |
| H5 | `LayeredEthernetInterface` with streaming PHY | — | **Retirement PENDING**: equivalence analysis (streaming PHY, timing implications) required | The 1.8 TT nodes use INET 4.7 TSN / Ethernet interfaces (M1 `PassThroughTt` is an INET `TsnSwitch`). The legacy interface choice was tied to the legacy node structure. |
| H6 | VLAN tag preservation for pass-through traffic | — | **Covered** | M1 S2 / S3 (VLAN / PCP byte-identical across the 5GS) |
| S1 | Multi-destination binder registration | multi-endpoint demos | **Retire — approved** (subject to replacement-behaviour coverage) | Binder registration is dropped with the IP transport (inventory §3). Multi-destination delivery is the UPF bridge's. |
| S2 | Scalable parameterised network NED | multi-endpoint demos | **Covered** | `M2S72Bridge` (N DS-TTs) |
| S3 | Per-endpoint IP addressing | multi-endpoint demos | **Retire — approved** (subject to replacement-behaviour coverage) | The TTs are L2-only; no IP stack |
| S4 | Per-endpoint SDAP / DRB configuration | multi-endpoint demos | **Covered** for gPTP; general case is a **task** | S7.2a per-UE DRBs (generator); the general S-CFG emitter (WP B3) |
| S5 | Per-endpoint gPTP configuration | multi-endpoint demos | **Covered** | S7.2a |
| S6 | gPTP multi-destination replication | multi-endpoint demos | **Covered** | UPF bridge flooding; S7.2a flood census (row M1) |
| S7 | Multi-endpoint traffic configuration | multi-endpoint demos | **Partly covered; task** | S7.2a load placements (`one0`, `sym`); data-plane multi-endpoint scenarios in M2-B |
| S8 | Integration test (bidirectional, 3 endpoints) | multi-endpoint demos | **Task** | An M2-B multi-endpoint integration scenario including UL (UL gPTP in S7.2b). N = 3 is not in the S7.2a set (1, 2, 4, 8). |
| F1 | Stream replication and recovery, single N3 path (DRB diversity) | `simulations/demos/frer_test` | **Task** | M3 (S-PATH binding F1; S7 roadmap §9 TP-1) |
| F2 | UL replication and recovery | `frer_test` | **Task** | M3 (binding F2) |
| F3 | Inter-PDU-session transport diversity (README: "integration testing in progress") | `frer_test` | **Deferred to Phase 5 — approved** | Roadmap Phase 5: trigger: upstream support for several Ethernet sessions per UE with per-session anchors (blocker B2). Interim F3-MU only as a separately labelled mechanism. |
| F4 | NR dual-connectivity transport diversity (README: "in development") | — | **Deferred to Phase 5 — approved** | Roadmap Phase 5: trigger: upstream NR dual-connectivity support (blocker B1). Contingency `nasctime.compat.nrdc` only by approval. |
| — | DS-TT VLAN translation (nascTime PR #2; inventory §3 "keep") | PR #2 head `1501a50` | **Task — retained in M2-B (approved)** | M2-B (DS-TT function); not in the README tables |

The README also documents `tests/fingerprint/` (lines 504–509), but that directory is not in the repository at `115012f` or, per `legacy-baseline-manifest.md` §3, in the public repository. This is blocker B8.

**The M2 work actually executed** follows the gPTP stage plan of `m2-s2-design.md` §7 (S0–S8) and the S7 roadmap. It does not complete M2 alone: **DR-02 (17 Nov)** approved the full M2-A (timing, S0–S8) and M2-B (bridge functionality) scope. S8 stays within M2 as extended fidelity (DR-04). `StaticBmca` gets an offline replacement, conditional on equivalence analysis (DR-03).

### 3.1 M2-S0 to M2-S6

| Stage | Scope (source) | Status | Evidence | Remaining | Indep. evidence |
|---|---|---|---|---|---|
| S0 | Architecture probe A1–A6 (`m2-s0-design.md`) | Complete on 1.8.0; A7-v PASS on 1.8.1 | `m2-s0-results.md`; R181b (A7-v) | — | Given (R181, G0) |
| S1 | `m2-s1-design.md` | Complete on 1.8.0; C10-v PASS on 1.8.1 | `m2-s1-results.md`; R181b | — | Given |
| S2 | Design and standards stage (stage plan §7) | Complete (design) | `m2-s2-design.md` | Standards texts not read (V-register, S7 roadmap §6) | — |
| S3 | Offline correction oracle | Complete, 24/24 | `m2-s3-results.md` | — | Given |
| S4 | Pdelay termination at the TT ports | Complete, 55/55; R2b-v PASS on 1.8.1 | `m2-s4-results.md`; R181b | — | Given |
| S5 | DS-TT egress correction, gate V0 | Complete on 1.8.0 (71/71). On 1.8.1: C8-v PASS, 69/71 with two superseded controls (R181c) | `m2-s5-results.md`; `m2-r181c-closure-report.md` | — | Given |
| S6 | TT clocks and rate ratio | Complete, 1863/1863 on 1.8.0 and on 1.8.1 | `m2-s6-results.md` (`m2/architecture` at `189be27` when pushed, per S7 roadmap header; the branch is archived as `archive/m2/architecture-snapshot-1.8.0`, rev. 4); R181c §1 | — | Given |

Audit §1.1 summarises S0–S6 as "complete on 1.8.0, each with a record, raw-output hashes and a fresh-clone reproduction".

### 3.2 M2-S7 — Operational gPTP (`m2-s7-roadmap.md` rev. 2.2)

| Substep | Scope / acceptance (S7 roadmap) | Status | Evidence | Remaining | Blockers | Remote | Indep. evidence |
|---|---|---|---|---|---|---|---|
| **S7.1** | §5.1: QoS options, residence and lag monitoring, Q0b first; completion criteria §5.1 | **Complete on 1.8.0** | `m2-s7.1-results.md`; audit §1.1 (gates 256/256, Q0b 251 PASS / 24 NOT EVALUATED, G0 16/16) | 1.8.1 forms of Q0b are replaced in Stage 5 by per-UE no-stranding (plan rev. 1.1 §0.2) | — | — | Given (1.8.0) |
| **S7.2a** | §5.2 (N DS-TTs, DL, static roles); design rev. 2.1 stages 1–9 | **Partial** (§3.3) | §3.3 | §3.3 | §3.3 | partly | **yes** |
| **S7.2b** | §5.3: UL GM and UE-to-UE; gate V0-UL first; rows U0–U3 | **Not started** | — | Design, network, configs, checker (C++ 0–300 lines, default-off) | V0-UL; V-2.2 for naming; UL residence claims (P-2) | Design and code: yes. Runs: no. | **yes** |
| **S7.3** | §5.4: L-det / L-state (minimum), L-rec experimental (F2); rows S0–S4 | **Not started** | — | State machine, timers, fault injectors (400–700 lines C++), state oracle | V-3.1 / V-3.2 block freezing L-rec only | Design and code: yes. Runs: no. | **yes** |
| **S7.4a** | §5.5: `NtGptp`, Announce, configured port states; gates A0–A3. **Release-optional (F1)**: never delays M3 or M4. | **Not started** | — | 800–1 500 lines C++ | A0 byte identity; V-4.1 / V-4.2 for naming | Design and code: yes. Runs: no. | **yes** |
| **S7.4b** | §5.6: BMCA. **Deferred (D7)**; not mandatory for 2.0. | **Deferred** | — | — | standards texts, edition decision, S7.4a, architectural review | no | — |

### 3.3 S7.2a in detail (`m2-s7.2a-design.md` §11; plan `m2-s7.2a-stage5-plan-1.8.1.md` rev. 1.1)

| Design stage | Content | Status | Evidence / commit |
|---|---|---|---|
| 1–3 (CP1) | Network, base configs, F0 / T0 | **Accepted.** CP1 rev. 2 PASS (F0 73/73, controls 6/6, T0 10/10); re-established on 1.8.1 (R181b); verdict-equivalent on 6.5.0 (G0) | `m2-s7.2a-checkpoint1-rev2-results.md` (CP1 rev. 2 baseline `0314eac`, as cited by `m2-s7.2a-checkpoint2-results.md`); `m2-r181b-closure-report.md`; G0 record rev. 3 at `04657b4` |
| 4 (CP2) | Block B, per-slave and cross-slave correctness | **Accepted.** CP2 rev. 2 PASS (2391/0, controls 13/13); I-2H PASS; on 1.8.1 (R181b); on 6.5.0 (G0: 2411 rows, 2391 gate rows PASS) | `m2-s7.2a-checkpoint2-rev2-results.md`; R181b §3; G0 record §4.2 |
| **5 (Stage 5)** | S7.1 rows per UE, Block C, scaling report. Re-planned for 1.8.1 into E0v → E3 → E1 / E4 (plan rev. 1.1 §2) | **In progress; no quantitative result on 1.8.1** | Breakdown in §3.4 |
| 6 (CP3) | Exact comparator with canaries CN-1…CN-4, rule AR, Block D faults FI-1…FI-8, Block E controls (design §7) | **Not implemented** | R181 acceptance record §5.3 |
| 7 | Block F seed diagnostic at N = 4; block T traces | Not started | — |
| 8 | `m2s72.sh all` record, G0, results document | Not started | — |
| 9 | Bundle and fresh-clone reproduction | Not started | — |

E2 (the load sweep) is outside the plan's execution scope. It is re-declared after E0v and E1 (plan §2.6). The 1.8.0 `e2rb` remains a historical record.

### 3.4 S7.2a Stage 5 on 1.8.1 — component status

| Component | Status | Evidence | Next |
|---|---|---|---|
| Environment decision D-2 | **Recorded**; conditions met | `m2-s7.2a-s5-env-decision.md`; G0 rev. 3 `04657b4` | — |
| S5-1 (runner `m2s72s5.sh`, generator E0v section, `check_m2s72_s5v.py`) | Implemented and reviewed | `m2-s7.2a-s5-1-review.md`; commit `86d7599` (former branch `m2/s72a-stage5`, now `archive/m2/s72a-stage5-s5-1`) | — |
| S5-2 (per-UE adapter, PU / AV rows, RNG audit, E1 selection) | Implemented; synthetic tests | `m2-s7.2a-s5-2-addendum.md`; `decf848` | S5-2-D2 (adapter validation record) is **open** |
| E0v N = 1 instrumented smoke | **Accepted 2026-11-16** (27 rows PASS, controls-q8 11/11) | quoted in `m2-s7.2a-s5-n2-protocol.md` §1. Raw evidence preserved (private archive, 41 files, verified). **No dedicated closure record yet** (DR-08). | closure record from the verified evidence |
| E0v-N N = 2 smoke | **Accepted 2026-11-16 as "VALIDATED WITH A-1 LIMITATION"** (PU-4 FAIL retained) | quoted in `m2-s7.2a-a2-design-review.md` §1. Raw evidence preserved (private archive, 58 files, verified). **No dedicated closure record yet** (DR-08). | as above |
| A-2 (ACK-only H-ARQ attribution) | Frozen at `fbee202`. Validated on real ACK-only output. | `m2-s7.2a-a2-implementation.md`; `m2-s7.2a-a2-control-fix.md` | — |
| A2-V1 (real-NACK run of A-2) | **NOT ACCEPTED, permanently** | `m2-s7.2a-a2d2-protocol-r1.md`; `m2-s7.2a-a2d2-f1-root-cause.md` | — |
| A-2.1 | Implemented (`2a7b96e`). F3 **CLOSED, ACCEPTED** (`d920125`). A2-V1-S1 **CLOSED, ACCEPTED under F1-d(i)**; the full contract is INCOMPLETE (A2-4c NOT EVALUATED). | `results/M2-S7.2a-a21-implementation.md`, `-f3-closure.md`, `-s1-closure.md` (`115012f`) | ~~**Not yet integrated into E0v-N** (DR-07)~~ **(rev. 5)** Integrated into the E0v-N evaluation **at level 2** by WP-A1 (§3.4b). Not yet a gate of any accepted E0v-N verdict. |
| E0v core / H5 / p (N = 1 calibration) | **Not run** | plan §2.1 | Needs an independent execution batch and approval |
| E0v-N bracket (f_E1) | **Not run; blocked** until A-2.1 is integrated (A1) and validated (V-N1, V-N2, V-V1). DR-07a–d are approved. | plan §2.1. N2-D2: the campaign cannot start under A-1. S5-2-D2 is open. | A1, the validations, then an independent environment. About 60–200 GB cumulative (plan §4.3). **(rev. 5)** A1 is done at level 2; the bracket remains **BLOCKED** on V-N1 / V-N2 / V-V1 (AC-5) and S5-2-D2 (AC-6). |
| E3 | Not prepared (generator E3v section, G-1, missing) | plan §2.2, §3 | — |
| E1 + E4 | Not prepared (G-1 E1 section; G-2 per-UE S7.1 rows) | plan §2.3, §2.4, §3 | — |
| Stage 6, Block F, stages 8–9 | Not started | §3.3 | — |

### 3.4a Acceptance boundaries of the DL H-ARQ attribution line (fixed; never broadened)

| Item | What is accepted | What is **not** accepted or claimed |
|---|---|---|
| A-1 | The N = 1 attribution (A-1a 11 697, no ambiguity) | N > 1 attribution: **PU-4 FAIL at N = 2, retained** |
| A-2 (frozen `fbee202`) | Validated on real **ACK-only** output (`M2-S7.2a-a2-implementation.md`, `-a2-control-fix.md`) | NACK, retransmission and discard handling. On real NACK output A-2 fails (the identifier-namespace defect, RC-1) |
| **A2-V1 (A-2 on real NACKs)** | — | **NOT ACCEPTED, permanently.** Never relabelled. |
| A-2.1 | Implementation `2a7b96e`. **F3: CLOSED, ACCEPTED**: the genuine first chain, a 385 ms prefix. | It is not yet a gate of any E0v-N run (DR-07) |
| **A2-V1-S1** | **CLOSED, ACCEPTED under F1-d(i)** on the genuine whole run (one configuration, one seed, DL, two UEs, NACKs on ue[1] only), including A2-8 against the genuine scalars | The **full contract: INCOMPLETE**, because A2-4c is NOT EVALUATED (scheduler logging was off). Never presented as a full-contract acceptance. |
| **F1-d(i)** | The A-2.1 contract that requires every row except A2-4c | — |
| Evidence kinds | A2-4a: MAC selection evidence. A2-4b: UE-side reception evidence. | A2-4c, node-identified scheduler evidence: none genuine. Discards, multi-NACK groups, ambiguous handles and NACK or pending-group censoring at the end of a log: **synthetic only** (S1 closure §5). |

**Can proceed remotely:** protocols, generator sections, checker rows and synthetic tests (plan §3: G-1, G-2, G-3 remainder, G-6), the A-2.1 integration, and the Stage 6 comparator.

**Requires an independent execution environment** (currently the VM): every E0v / E3 / E1 / E4 run and every independent acceptance. Storage: cumulative 290–470 GB, peak 6 GB or less, with the tiered evidence rules of plan §4. Wall time about 18–25 h for the whole of Stage 5 (plan §4.3, an estimate).

### 3.4b WP-A1 — A-2.1 integration wrapper for E0v-N (step 159; updated rev. 5)

This entry adds status only. It does not change any row of §3.4a, and S7.2a remains **partial**.

**(rev. 5) Integration record:**
- **Integrated** into `m2/continuation` by the merge commit `3b2c294` of PR #11 (head `0b7da11`, itself containing the history-preserving merge `a54faf3` of `f8bf10c`).
- **Development tests and hosted CI passed:** tier-0 run 45470846973 on `0b7da11`, 13 / 13 suites including `test_m2s72_e0vn21.py` 52 / 52 (isolated); the historical-pin tests pass on the merged tree.
- **Preserved:** the reviewed implementation commit `C` (`f3f68be`) and the procedure commits (`544c093`, `532d579`) are ancestors of `3b2c294`; the wrapper files equal `C` and the procedure files equal `544c093` byte for byte.
- **Pending:** V-N1, V-N2, V-V1; AC-5 and AC-6; S5-2-D2. **S7.2a Stage 5 remains incomplete.** The next executable action is the maintainer's gate A for session Q (§9.2).

| Item | Status |
|---|---|
| Design | Revision 2.1 (`57a80ca`), approved with the D-A1 rulings (`docs/migration/wp-a1-a21-e0vn-wrapper-design.md`) |
| Implementation (`m2s72_e0vn21.py`, `check_m2s72_s5n21.py`, registry, expectation files, suite) | **Complete at level 2 (AC-1 … AC-4)**, ~~subject to confirmation by hosted CI on the integration branch~~ **(rev. 5) confirmed by hosted tier-0 on the merged head (run 45470846973) and integrated (`3b2c294`)**. Reviewed implementation commit `C` = `f3f68be`. Closure record: `docs/migration/wp-a1-level2-closure.md`. Suite: 52 / 52 PASS, run isolated as the 13th tier-0 suite. |
| FGO registry | 18 features, 9 admitted, unchanged since `7e5c169`. No admission without a reviewed change citing an accepted record. |
| Validation procedure | Runbook revision 4 with fail-closed scripts (`docs/migration/wp-a1-validation-runbook.md`, `docs/migration/wp-a1-validation/`; procedure tested at `544c093`, test report `docs/migration/wp-a1-validation-test-report.md`). Procedure commit `D` is fixed only when the maintainer signs gate A. |
| V-N1, V-N2, V-V1 | **Not executed.** NO-GO until gate A is signed, an executor is designated, session Q (DR-13-V, G0-RO) is approved and the three archives are released. |
| AC-5, AC-6 | **Open** (maintainer, level 3) |
| S5-2-D2 | **Open.** `S5N_ADAPTER_VALIDATED` is not set; the wrapper's `run` mode refuses without it. |
| Scientific acceptance | **Not claimed.** The `hrq` verdict is HELD FOR REVIEW. A2-V1 stays **NOT ACCEPTED**; the A-1 PU-4 FAIL of the N = 2 smoke is retained; A-2 and A-2.1 are unchanged. The E0v-N bracket stays blocked (§3.4). |

### 3.5 M2-S8 — Fidelity (`m2-s2-design.md` §7)

| Item | Content |
|---|---|
| Original scope | Option C wire Suffix TLV; TT clock synchronization error to 5G time (23.501 §5.27.1.2.1 / §5.27.1.9); one-step if required. "3GPP-faithful carriage" may be claimed only after S8. |
| Status | **Not started.** The S7 roadmap §2.3 lists the S8 items as "separate milestone" (extended fidelity). **DR-04 (17 Nov):** S8 remains within M2 as extended fidelity. Release eligibility follows the B7 analysis of the clock-error relationship. |
| Blockers | Standards texts (V-register); the edition decision (V-4.6). |
| Remote | Design only. |

### 3.6 M2 roadmap items outside the gPTP line

| Item (roadmap §2 Phase 2) | Status (audit §1.1) | Remote | Indep. evidence |
|---|---|---|---|
| TAS / Qbv at the TT ports ("TAS parsed, not applied" closed with INET Qbv; `upstream-dependency-matrix.md` §2) | ~~Not started~~ **(rev. 5) IMPLEMENTED at level 2** (B5: M2B-2 S-CLK, M2B-3 opt-in Qbv, M2B-5 common epoch; local functional evidence only). §9.4 | Design and configuration: yes | yes (protocol row "gates observed opening and closing") |
| TSN AF offline compiler (streams → S-CFG tables, PCP/VID → QFI, nascTime profiles, TSCAI) and runtime observer | ~~Not started. S-CFG exists only as the S7.2a generator (audit §1.6).~~ **(rev. 5)** Compiler **PARTIAL** (B3: S-CFG/1 bearer tables byte-identical to the generator; S-CFG/2 TAS and common epoch; no TSCAI, no VID classification, no `.ini` section integration). Observer **IMPLEMENTED at level 2** (B6: offline observer M2B-2, TAS pairing M2B-4). §9.4 | Compiler: yes. Observer: code yes, runs no. | yes |
| Multi-endpoint (N DS-TT / UE pairs on one UPF bridge) | Partly covered by S7.2a (gPTP only). **(rev. 5)** M2B-3 … M2B-5 add DL / UL Ethernet data traffic through the N = 2 bridge in their test configurations (level 2, local). The S8 integration scenario (bidirectional, 3 endpoints) is not started. | — | — |
| `StaticBmca` replacement | Not started. DR-03 approved an offline replacement, conditional on equivalence analysis. | yes (analysis; validator once tier 1 exists) | legacy-scalar check (Phase 0) |
| G1–G6 / H1–H6 / S1–S8 / F1–F4 coverage | Dispositions decided by DR-02 (§3 table); the H5 retirement is pending its equivalence analysis. The coverage-evidence entries (WP B1) are not started. | yes | no (it is a mapping) |
| Legacy-vs-1.8 statistical comparison | Not started. Needs the Phase 0 evidence acquisition and mapping first (DR-06). | no | **yes**: the legacy stack on the results machine |
| Fingerprint suite on the new baseline (merge gate for refactors) | Not started; the suite's location is B8. `Makefile` target `tests` refers to `tests/fingerprint/fingerprints`, which is not present in the repository (manifest §3). | partly | yes |
| README boundary statement (stale, audit §1.2) | Not done (DR-10) | yes | — |
| VM NED / INI compatibility corrections for 6.5.0 | **Collected** (H2: the private VM-compatibility archive). Not yet reviewed or incorporated. | review by the maintainer, or by the agent from reviewed extracts (DR-12); integration as reviewed default-off commits | yes (G0 identity, held) |

**M2 overall: OPEN.** S0–S6 and S7.1 are complete on 1.8.0, with the 1.8.1 forms accepted. S7.2a is partial. S7.2b, S7.3, S7.4a, S8 and the non-gPTP Phase 2 items have not started.

**(rev. 5)** M2 remains **OPEN**. The non-gPTP statement above is superseded for B3, B5 and B6, which now have level-2 implementations (§9.4). No M2-B acceptance row has independent evidence.

## 4. M3 (Phase 3) — FRER

| Item | Content |
|---|---|
| Original scope | Roadmap §2 Phase 3: INET `StreamIdentifier` / `StreamSplitter` / R-TAG at NW-TT and DS-TT; member streams by VID or PCP → QFI → DRB (F1 DL, F2 UL) through S-PATH; `FrerRecovery` as an extension of INET merge semantics; optional elements inside the UE and UPF `BridgingLayer` (B4). |
| Acceptance | Functional: zero duplicates; delivery equals the surviving path; sequence wrap and timeout. Protocol: R-TAG placement. Experimental: reliability vs single path across the legacy F1 / F2 sweeps, with differences attributed. The inter-session finding is **not** re-claimed until F3 exists. |
| Planning constraints | S7 roadmap §9: classes TP-1 (bearer paths of one UE), TP-2 (two UEs, same cell; F3-MU, labelled), TP-3 (two UEs, different gNBs) and RP (native radio-path diversity, upstream-dependent, schedule undecided). Results over TP-1…TP-3 are "FRER over existing transport paths", never radio-path diversity. Recovered losses are attributed by cause. On 1.8.1, the specific #310 path (a MAC PDU silently deleted when no H-ARQ process is free) is replaced by scheduler ineligibility and, if it is ever reached, a runtime error (plan rev. 1.1 §0.1 F1; audit §2 #310). This changes the TP-1 motivation, which must be re-stated. **It is not a claim that H-ARQ discards are absent on 1.8.1:** a discard after maxHarqRtx failed transmissions remains possible by design. A-2.1 handles it, but none occurred in the genuine A2-V1 run (S1 closure §5). |
| Status | **Not started.** The legacy FRER implementation (`FrerReplicator`, `FrerRecovery`) exists only on the legacy line (`inventory-and-architecture.md` §3: replace with INET elements; keep recovery as an extension). |
| Dependencies | S-PATH binding (roadmap §1). Multi-DRB and multi-UE configurations from S7.1 / S7.2a (S7 roadmap §9). Legacy F1 / F2 sweep profiles and results (Phase 0 mapping). The pinned stack: DR-01 (17 Nov) sets OMNeT++ 6.5.0 / INET 4.7.0 / unmodified Simu5G 1.8.1 for M3. The roadmap title "on vanilla 1.8.0" is preserved as historical text. |
| Blockers | F3 (inter-PDU-session) waits for upstream multi-session support with per-session anchors (blocker B2; roadmap Phase 5). F4 (NR-DC) waits for upstream NR dual-connectivity support (blocker B1). Neither blocks M3 (F1 / F2). |
| Remote | Design, S-PATH binding code, `FrerRecovery` extension code and unit tests: *[Superseded (rev. 4); not an active instruction:]* yes, once tier-1 CI is verified and enabled (plan WP-E2; `remote-execution-feasibility.md`). Until then: design and prototype only. *[end of superseded text]*<br>**(rev. 4)** Tier-1 is integrated (PR #7, DR-14). Default-off C++ code can be CI-validated for release build and linkage. A new configuration is validated only by its own reviewed query or an individually authorised hosted functional run (§8; DR-15). |
| Independent evidence | **Yes**: the functional, protocol and experimental rows need simulation, and the legacy comparison needs the legacy stack. |

## 5. M4 (Phase 4) — Release nascTime 2.0

| Item | Content |
|---|---|
| Original scope | Roadmap §2 Phase 4: README boundary statement and compatibility table; `opp_env` entry (B9); CI (a blocking pinned job plus a non-blocking nightly `simu5g@dev`); skills `nasctime-dev-environment` and `nasctime-fingerprint-testing`; claim-scoping notes. |
| Acceptance | Clean-machine install and run of every example; the CI dev job has run at least once; the boundary statement reviewed. |
| Release scope constraints | S7 roadmap §2.1 minimum scope: S7.1, S7.2a, S7.2b, S7.3 (detection and state; recovery experimental). §2.2: S7.4a optional. D7: BMCA not mandatory. F1: S7.4a never delays M3 or M4. |
| Status | **Not started.** *[Superseded (rev. 4); not an active instruction:]* No `.github/` CI exists in the repository (checked on the authoring clone at `115012f`). *[end of superseded text]*<br>**(rev. 4)** CI groundwork exists: tier-0 (PR #4) and tier-1 (PR #7) are integrated on `m2/continuation` (DR-14). **M4 itself is not started, and 2.0 is not release-ready.** The release path is decided in principle by DR-18. |
| Dependencies | The DR-01 pin; M2 (scope per DR-02) and M3. |
| Remote | README draft, CI and documentation: yes. The clean-machine run: partly (CI). |
| Independent evidence | The clean-machine install, by the maintainer. |

## 6. Phase 5 — Upstream-gated integrations, and Phase 6 — tracking

Roadmap §2 Phase 5 lists the items, triggers and contingencies: F4 NR-DC, F3 inter-PDU-session, PDCP duplication, TSC assistance / CG, 5G time distribution, mobility realism, VLAN-scoped flooding and radio stage C. **No trigger is recorded as met** in the sources read.

Phase 6 is ongoing per-release tracking. The Simu5G 1.8.1 integration (M2-R181) is one instance of it: `m2-simu5g-1.8.1-audit-and-plan.md` and `m2-r181-acceptance-record.md`.

Upstream contributions are coordinated separately by the maintainer. Simu5G 1.8.1 fixed #308–#311, which were reported from nascTime (per audit §2).

## 7. Summary matrix

**(rev. 5)** The table below is the **18 November baseline**, retained unchanged. The 24 November reconciliation is §9.1, which supersedes it for current status.

| Milestone / stage | Status | Remote work possible | Independent simulation evidence still required |
|---|---|---|---|
| Phase 0 | Open (provenance collected; mapping and reproduction outstanding) | Documentation; mapping analysis from reviewed extracts provided by the maintainer (DR-12) | yes (legacy regeneration) |
| M1 | Closed | — | — |
| M2-S0…S6 | Complete (1.8.0; 1.8.1 forms accepted) | — | — |
| M2-S7.1 | Complete (1.8.0) | — | — |
| M2-S7.2a | Partial (Stage 5 in progress; stages 6–9 open; N = 1 / N = 2 / A2-V1 evidence preserved privately) | yes (protocols, checkers, generator, A-2.1 integration) | **yes** (E0v, E3, E1, E4, Stage 6, fresh clone) |
| M2-S7.2b / S7.3 / S7.4a | Not started (S7.4a optional) | yes (design, code) | yes |
| M2-S7.4b | Deferred | no | — |
| M2-S8 | Not started; within M2 as extended fidelity (DR-04) | design | yes |
| M2-B (bridge functionality) | Not started; scope approved (DR-02) | yes (design, TSN AF compiler) | yes |
| M3 FRER | Not started | yes (design, code) | yes |
| M4 release | Not started | yes (CI, documentation) | clean-machine run |
| Phase 5 | No trigger met | monitoring | — |
| **Development CI (rev. 4)** | Tier-0 and tier-1 integrated (DR-14). Tier-2 harness frozen on `wp-e3/e3b-r1-publication` (DR-15). E3a and E3b-R1: level-2 smoke evidence. | yes | — (CI is never level 3) |

## 8. Development infrastructure and hosted experiments (rev. 4)

**Sources:**
- `repository-archive-and-evidence-register.md` §3 (identities, runs, results);
- `ci/tier1/README.md`;
- `ci/tier2/README.md` on `wp-e3/e3b-r1-publication`.

| Item | Status | Level |
|---|---|---|
| Tier-0 Python regression CI (H4 / WP-E1) | **Integrated** (PR #4, 17 Nov). Runs on every pull request to `m2/continuation`. Required at repository-ruleset level (DR-14). Negative controls NC-H4-fixture and NC-H4-simu5g each failed at their intended gate. **(rev. 5)** Now **13 declared suites**: the ten original ones, `test_tsnaf_compile.py` (M2B-1), `test_tsnaf_compile_tas.py` (M2B-3) and `test_m2s72_e0vn21.py` (WP-A1, isolated). Not in tier-0: the M2B-5 compiler suite `test_tsnaf_compile_epoch.py` (pure Python, 32 / 32 locally) and the simulator-based M2B-2 … M2B-5 suites. | 2 |
| Tier-1 full-stack CI (WP-E2) | **Integrated** (PR #7, 18 Nov). Pinned release build of OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1 and `libnasctime_m2`; linkage, single C++ runtime and RUNPATH classes; **its specific reviewed configuration queries** (the two `-q runconfig` queries of the A2-V1 wrapper suite). It does **not** automatically validate every newly introduced NED or INI configuration. **Triggering:** automatic for relevant **non-draft** pull requests (complete change set, fail closed); the label `tier1:run` overrides, including for drafts. **Not mandatory** at ruleset level (DR-14). | 2 |
| Tier-1 negative controls N-1 (lock) and N-2 (SYS_LIBS) | N-1 and N-2 failed during the **offline self-tests** of their hosted runs, so those hosted runs **never reached** the downstream gates they target. Those gates are the lock-identity gate (N-1) and the C-5 SYS_LIBS gate (N-2). Both gates **passed** in the positive hosted tier-1 runs: PR #7 and the C-1 … C-12 prerequisites of E3a, E3b and E3b-R1. Their negative (rejecting) behaviour was tested **offline** by the tier-1 self-tests. | — |
| E2b.1 / E2b.2 / E2b.3 / E2b.3-R1 | PASS / **FAIL** / **FAIL** / PASS. The failures are preserved (`archive/exp/*`). Superseded by tier-1. | — |
| **E3a** (`M2S4U`, run 0) | **E3a PASS.** C-1 … C-12 and E-1 … E-8 PASS; unmodified U1 oracle PASS. **Demonstrates wired timing functionality.** Seal manifest: 9 files, 24 496 082 B; the complete raw artifact has 37 files. E-9: 4/4 historical 6.4.0 engine-log / PCAP hashes reproduced. | **2** (development smoke) |
| **E3b** (`M2S5`, run 0; original) | **E3b PUBLICATION FAILURE, preserved.** E-1 … E-7 PASS. The evidence seal passed and was verified. The raw publication failed: the N3 publication policy was too narrow, and the raw evidence was lost with the runner. | — |
| **E3b-R1** (`M2S5`, run 0; publication correction) | **E3b PASS.** C-1 … C-12 and E-1 … E-8 PASS. Per-run M2-S5 oracle PASS: C1–C7, S1, S2 and P2 fully; C8 and P1 partially; S3 NOT EVALUATED. **Demonstrates the downlink 5G–TSN timing path.** 33/33 R181c CSV / PCAP hashes reproduced. 568 downlink and 488 uplink N3 packets passed publication validation. | **2** (development smoke) |
| Differing `.sca` / `.vec` hashes (E3b, E3b-R1) | **Cause unverified.** Not attributed to metadata or any other cause; no whole-result equivalence claim. | — |
| Hosted functional simulations during travel | **Permitted when individually authorised and bounded** (DR-15). There is no automatic tier-2 integration. **(rev. 5)** None was authorised for M2B-1 … M2B-5: their functional TAS, residence and common-epoch results are **local release-build runs only**. Tier-1 builds and links the changed C++ but does not resolve or run the M2B configurations; extending it is a proposal (M2B-3 §8) awaiting a maintainer decision. | 2 |
| Independent scientific execution during travel | **Permitted** for an authorised independent scientific executor, under a pre-declared protocol, the approved budget and the maintainer's acceptance (feasibility §4) | 3 candidates |
| **WP-E4: repository consolidation and travel handover** | **Completed by the documentation PR that introduces revision 4.** That covers four permanent branches, 30 tags and the archive and evidence register. **Still open:** release documentation and M4 readiness (plan package E4, M4). | — |

**Hosted development smoke tests and independent scientific execution are different things.**
- E3a and E3b-R1 were started by the development agent, so they are **not eligible for level 3** (`remote-execution-feasibility.md` §4, X-1).
- They do not accept the M2-S5 campaign, do not advance S7.2a (which **remains partial**), and carry no uplink claim.
- Development CI does not replace independent scientific execution. Every scientific acceptance listed in §3.4, §4, §5 and the travel plan's acceptance queue still requires the independent executor (or the VM) under a pre-declared protocol, and the maintainer's acceptance.

**Licensing (DR-16).** The maintainer has confirmed academic-use scope for current nascTime development and simulation, including hosted CI. No compiled framework binary is redistributed. Commercial use is outside the current scope.

---

## 9. Reconciliation of 24 November 2026 (rev. 5)

**Baseline:** `m2/continuation` at `3b2c2941ef297cb20051798fd1ad3ed8dea69c20`.

**Method:**
- Every original milestone is reconciled against the published records on that head, the merged pull requests and the hosted CI record.
- Private planning documents (DR-12) were **not** re-read for this revision. Where they are cited, the citation is the reviewed excerpt already quoted in this record (sections 1–8) or in the decisions register. Nothing is inferred about their unquoted content.
- A merged pull request is never treated as scientific acceptance. Level 2 means code complete and CI- or locally validated; level 3 is independent acceptance by the maintainer.

**Status vocabulary (used only in this section and in `remaining-work-roadmap.md`):**

| Status | Meaning |
|---|---|
| **CLOSED** | Accepted against its original scope |
| **IMPLEMENTED** | The functionality exists, but acceptance remains incomplete |
| **PARTIAL** | Some original requirements remain unimplemented |
| **NOT STARTED** | No implementation |
| **DEFERRED** | Deferred by an explicit, approved decision (cited) |
| **BLOCKED** | Cannot proceed until the named dependency is met |

**"Required for 2.0"** is taken from the sources already quoted:
- S7 roadmap §2.1 minimum gPTP scope: S7.1, S7.2a, S7.2b, S7.3 (detection and state; recovery experimental);
- §2.2 and F1: S7.4a optional, and it never delays M3 or M4; D7: BMCA (S7.4b) not mandatory;
- DR-02: the full M2-A and M2-B scope, and M2 closes only when both close;
- §5: M4 depends on M2 and M3;
- DR-04: the release eligibility of S8 claims follows the B7 analysis;
- the Phase 0 rule (§1): nothing waits for Phase 0 closure, but the legacy comparisons need its mapping (DR-06).

Where the sources leave a release question open, this record says **"undecided"** and lists it in §9.6.

### 9.1 Milestone status matrix (24 Nov 2026)

| Milestone / stage | Status | Required for 2.0 | Next concrete action |
|---|---|---|---|
| Phase 0: legacy baseline and preservation | **PARTIAL** (provenance collected; mapping, dataset preservation and reproduction outstanding) | Closure: not a gate (§1 rule). Mapping and evidence acquisition: **yes**, for the M2 and M3 legacy comparisons (DR-06) | Maintainer: DR-06b dataset preservation when VM access resumes |
| M1: Ethernet bridge | **CLOSED** (2026-10-13) | yes (done) | — (O-S0-1 observation only) |
| M2-A S0, S1, S3–S6 | **CLOSED** (1.8.0; 1.8.1 forms accepted) | yes (done) | — |
| M2-A S2 (design and standards stage) | **CLOSED** as a design stage; standards texts not read (V-register) | yes (done) | V-register affects S7.3 L-rec, S7.4a, S8 only |
| M2-A S7.1 | **CLOSED** for its 1.8.0 scope; the 1.8.1 per-UE forms are re-planned into Stage 5 (E1 + E4) | yes | via Stage 5 (A4) |
| M2-A S7.2a | **PARTIAL**: stages 1–4 CLOSED; stage 5 PARTIAL (E0v-N bracket **BLOCKED**); stages 6–9 NOT STARTED | **yes** | Maintainer gate A for WP-A1 session Q (§9.2) |
| M2-A S7.2b (UL GM, UE-to-UE) | **NOT STARTED** | **yes** | C1 design |
| M2-A S7.3 (L-det / L-state; L-rec experimental) | **NOT STARTED** | **yes** | C3 design |
| M2-A S7.4a (`NtGptp`, Announce, port states) | **NOT STARTED** | no (release-optional, F1) | after C1 / C3 |
| M2-A S7.4b (BMCA) | **DEFERRED** (D7) | no | — |
| M2-A S8 (fidelity) | **NOT STARTED** (within M2 by DR-04) | **undecided** (B7 analysis) | B7 note |
| M2-B B1 coverage table | **NOT STARTED** | **yes** (DR-02 functional acceptance) | B1 draft |
| M2-B B2 architecture and seams | **PARTIAL** (S-CFG interface note; S-CLK analysis) | yes | B2 consolidation |
| M2-B B3 TSN AF offline compiler | **PARTIAL** (M2B-1, M2B-3, M2B-5 compiler parts) | yes | B3 completion |
| M2-B B4 `StaticBmca` validator | **NOT STARTED**; DR-03 condition (1) **BLOCKED** on the Phase 0 datasets | yes (DR-03, conditional) | DR-03 conditions (2) and (3) |
| M2-B B5 TAS / Qbv at the TT ports | **IMPLEMENTED** (level 2; local evidence) | yes | hosted-evidence decision, then acceptance protocol |
| M2-B B6 bridge-delay observer | **IMPLEMENTED** (level 2; local evidence) | yes | as B5 |
| M2-B B7 DR-04 clock-error analysis | **NOT STARTED** | yes (decides S8 eligibility) | B7 note |
| M2-B DS-TT VLAN translation (DR-02, retained; no WP number in the plan) | **NOT STARTED** | yes (DR-02) | design within B2 |
| M2-B multi-endpoint data plane (S4, S7, S8) | **PARTIAL** (gPTP in S7.2a; N = 2 data traffic in the M2B test configurations) | yes | the S8 scenario needs S7.2b for UL gPTP |
| M2-B legacy-vs-1.8 comparison | **BLOCKED** on Phase 0 mapping and datasets (DR-06, DR-06b) | yes (M2 experimental row) | Phase 0 mapping |
| M2-B fingerprint baseline | **BLOCKED** on B8 (suite not located) | yes (M2 regression row) | maintainer: locate the suite |
| M3 FRER | **NOT STARTED** | **yes** (M4 depends on M3, §5) | D1 architecture |
| M4 release 2.0 | **NOT STARTED** (CI groundwork exists) | — | E4 groundwork |
| Phase 5 | **DEFERRED** (F3, F4 by DR-02; other items on upstream triggers, none met) | no | monitoring |
| Phase 6 | Ongoing; the R181 instance is **CLOSED** | — | per upstream release |

**M2 overall: OPEN. 2.0 is not release-ready.**

### 9.2 WP-A1 and S7.2a Stage 5

| Field | Record |
|---|---|
| Objective and acceptance | DR-07a–d: integrate A-2.1 into the E0v-N evaluation; design `wp-a1-a21-e0vn-wrapper-design.md` rev. 2.1, AC-1 … AC-6 (§10 of the design) |
| Status | **IMPLEMENTED.** The implementation is integrated into `m2/continuation` (`3b2c294`). AC-1 … AC-4 are met at level 2. Development tests passed: 52 / 52; tier-0 13 / 13 on `0b7da11`, run 45470846973. The historical implementation commit `C` (`f3f68be`) and the procedure commit (`544c093`) are preserved as ancestors. |
| Accepted evidence | Level 2 only: the suite, the 27 negative controls and the genuine F3 fixture through the wrapper. The procedure tests at `544c093` passed on dummy data (test report). There is **no** level-3 evidence. |
| Remaining development | None for the validations. Later: A3 (E0v-N batch protocol addendum), which uses the wrapper's `run` mode under S5-2-D2. |
| Remaining independent validation | **V-N1, V-N2, V-V1** (VG-0 … VG-3), giving **AC-5**; then **S5-2-D2**, giving **AC-6**. Optional registry admissions are a separate reviewed change (design §8.5). |
| Dependencies and blockers | The executor designated by the maintainer (X-1). Gate A signed by the maintainer. Session Q (the DR-13 validation record and G0-RO), each record approved by a signed statement. The three genuine release archives with `SHA256SUMS`. The image digest approved through G0-RO. |
| Required for 2.0 | **Yes**: every N > 1 Stage 5 result depends on it (plan §3a priority 1) |
| **Next executable action** | **Maintainer, gate A for session Q** (runbook §2–§3):<br>1. designate the executor (X-1) and supply the public key `allowed_signers` (principal `wpa1-maintainer`, namespace `wpa1-approval`) out of band;<br>2. fix `D`, the approved procedure commit (`544c093`, the tested revision 4, is reachable from `m2/continuation`);<br>3. sign `gate-a.txt` with `reviewed_commit=f3f68be…`, `docs_commit=D`, the three expectation sha256 and the registry sha256, `access=authorised`, `release_sums_sha256`, the three `archive=` lines and `rules=approved`.<br>The executor then runs H-1 (`h1-setup.sh D`), H-3 `qualification`, DR-13-V (§6) and G0-RO (§7), and the maintainer approves both records by signing `a4-dr13.txt` and `a5-g0ro.txt`. Only then can session V run V-N1 / V-N2 / V-V1. **Session Q performs no WP-A1 evaluation.** |

**Stage 5 components** (unchanged from §3.4 except where marked):

| Component | Status (rev. 5) |
|---|---|
| D-2, S5-1 | CLOSED |
| S5-2 | IMPLEMENTED (synthetic tests); S5-2-D2 open |
| E0v N = 1 smoke; E0v-N N = 2 smoke | Accepted 2026-11-16 (the N = 2 smoke with the A-1 limitation and the PU-4 FAIL retained). **No dedicated closure records yet (DR-08).** |
| A-2 | CLOSED within its ACK-only scope (frozen `fbee202`). A2-V1: **NOT ACCEPTED, permanently.** |
| A-2.1 | F3 CLOSED; A2-V1-S1 CLOSED under F1-d(i); full contract INCOMPLETE (A2-4c) |
| A1 (WP-A1) | IMPLEMENTED (above) |
| A2 full-contract diagnostic configuration (DR-07a) | NOT STARTED |
| A3 E0v-N batch protocol addendum | NOT STARTED (its I-dep A1 is now met at level 2) |
| E0v core / H5 / p | NOT STARTED (needs A3 and an independent batch) |
| E0v-N bracket, f_E1 | **BLOCKED** on AC-5, AC-6 and A3 |
| A4 E3 / E1 / E4 generator sections (G-1, G-2, G-3 remainder) | NOT STARTED |
| E3, E1 + E4 runs | BLOCKED on A4 |

### 9.3 Phase 0, M1 and M2-A

| Item | Objective and acceptance (source) | Status | Accepted evidence | Remaining development | Remaining independent validation | Dependencies / blockers | 2.0 | Next action |
|---|---|---|---|---|---|---|---|---|
| **Phase 0** | Tag the legacy line, archive every published result set, reproduction script; each archived result regenerates bit-identically (roadmap §2 Phase 0; §1) | **PARTIAL** | Public identities `v1.0` / `v1.0.1`; provenance collected (H2). No reproduction evidence. | Result-to-paper mapping documentation (from reviewed extracts, DR-12) | Bit-identical regeneration on the legacy stack; preservation of the VM-only datasets (DR-06b) | VM access; B8 (fingerprint suite not located); no tags may be created by the agent | Closure: no gate. Mapping: yes (DR-06) | Maintainer: DR-06b preservation; supply reviewed mapping extracts |
| **M1** | Roadmap Phase 1 rows and the seam grep gate | **CLOSED** 2026-10-13 | S0–S5 commits (§2); R181 on 1.8.1; G0 | — | — | — | yes | — |
| **M2-A S0, S1, S3, S4, S5, S6** | Stage plan `m2-s2-design.md` §7 | **CLOSED** | §3.1 (1.8.0 records; R181b / R181c on 1.8.1; G0) | — | — | — | yes | — |
| **M2-A S2** | Design and standards stage | **CLOSED** (design) | `m2-s2-design.md` | — | — | The standards texts (V-register) are still unread; they affect S7.3 L-rec, S7.4a and S8 | yes | — |
| **S7.1** | S7 roadmap §5.1 | **CLOSED** (1.8.0 scope) | `m2-s7.1-results.md` | 1.8.1 per-UE forms through A4 (G-2) | E1 + E4 | A4 | yes | A4 |
| **S7.2a** stages 1–3 (CP1) | Design §11 | **CLOSED** | CP1 rev. 2; R181b; G0 | — | — | — | yes | — |
| **S7.2a** stage 4 (CP2) | Design §11 | **CLOSED** | CP2 rev. 2; I-2H; R181b; G0 | — | — | — | yes | — |
| **S7.2a** stage 5 | Plan rev. 1.1 §2 (E0v → E3 → E1 / E4) | **PARTIAL** | §9.2 | A2, A3, A4 | V-N1 / V-N2 / V-V1; S5-2-D2; E0v core / H5 / p; E0v-N bracket; E3; E1 + E4; DR-08 smoke closure records | §9.2 | yes | §9.2 |
| **S7.2a** stage 6 (CP3) | Exact comparator, canaries CN-1 … CN-4, rule AR, Block D / E (design §7) | **NOT STARTED** | — | A5 | CP3 | A4 | yes | A5 after A4 |
| **S7.2a** stages 7–9 | Block F seed diagnostic (N = 4), block T; `m2s72.sh all` record; fresh-clone bundle | **NOT STARTED** | — | A6 | Block F; fresh-clone reproduction | A5 | yes | A6 |
| **S7.2b** | UL GM and UE-to-UE; gate V0-UL first; rows U0–U3 (§5.3) | **NOT STARTED** | — | C1 design; C2 network, configurations, checker | V0-UL, U0–U3 | V-2.2 naming; the UL residence claims (P-2) | **yes** | C1 |
| **S7.3** | L-det / L-state; L-rec experimental (F2); rows S0–S4 (§5.4) | **NOT STARTED** | — | C3 design; C4 state machine, timers, fault injectors | S0–S4 | V-3.1 / V-3.2 block only the freeze of L-rec | **yes** | C3 |
| **S7.4a** | `NtGptp`, Announce containment, configured port states; gates A0–A3 (§5.5) | **NOT STARTED** | — | 800–1 500 lines C++ (roadmap estimate) | A0–A3 | V-4.1 / V-4.2; legacy H4 (Announce) maps here | no (optional, F1) | after C1 / C3 |
| **S7.4b** | BMCA (§5.6) | **DEFERRED** (D7) | — | — | — | standards texts, edition decision, S7.4a | no | — |
| **S8** | Option C Suffix TLV; TT clock synchronization error to 5G time; one-step if required (§3.5) | **NOT STARTED** | — | Design (DR-04) | yes | B7 analysis; standards texts; the edition decision (V-4.6). "3GPP-faithful carriage" may not be claimed before S8. | **undecided** (B7) | B7 |

### 9.4 M2-B: original work packages B1–B7 and the DR-02 scope

**Mapping of the implementation increments.** M2B-1 … M2B-5 are increments **within** the original packages. They do not replace them.

| Increment | PR | Contributes to | What it does **not** establish |
|---|---|---|---|
| M2B-1: TSN AF offline compiler, S-CFG/1 | #12 | **B3** (and the B2 S-CFG interface note `m2b-scfg-interface.md`) | TAS, TSCAI, FRER, runtime observation, VID classification, `.ini` section integration (report §6) |
| M2B-2: TT gate clock adapter `TtGateClock` (S-CLK) and offline observer `bridge_delay.py` (S-OBS) | #13 | **B5** (clock binding), **B6** (offline observer), B2 (S-CLK seam analysis) | Gating itself; observation under TAS |
| M2B-3: opt-in 802.1Qbv egress gating, S-CFG/2 | #14 | **B5**, B3 (S-CFG/2) | Common base time; B6 under TAS; hosted execution |
| M2B-4: TAS-compatible egress pairing; residence under TAS | #15 | **B6** | Frames dropped by a shaped queue, preemption, aborted transmissions (refused); hosted execution |
| M2B-5: common-epoch schedule alignment (`base_time_ns`, `TtEpochGate`) | #16 | **B5**, B3 | Clock synchronization accuracy, cross-translator feasibility, worst-case latency, 802.1Qbv / 802.1AS conformance; sanitizer runs; future activation (ConfigChange); runtime reconfiguration |

**Evidence class of all five increments:** level 2. The functional bridge results come from **local release-build runs** on the pinned stack versions, not from the pinned tier-1 environment. No hosted run executed the M2B configurations. Tier-0 runs the M2B-1 and M2B-3 compiler suites. The tier-1 workflow completed successfully on each PR head; it builds and links the changed C++ but does not resolve or run the M2B configurations, and whether its full-stack job ran or was skipped by trigger selection is recorded per run and is not re-verified here.

| WP (travel plan §2) | Objective and acceptance | Status | Accepted evidence | Remaining development | Remaining independent validation | Dependencies / blockers | 2.0 | Next action |
|---|---|---|---|---|---|---|---|---|
| **B1** | G1–G6, H1–H6, S1–S8 → a 1.8 scenario, M2-A stage, M2-B package, or "retired, replaced by X"; the evidence column | **NOT STARTED** (the dispositions are decided, §3 table) | DR-02 dispositions | The coverage table, now able to cite M2B-1 … M2B-5 and WP-A1 | The evidence column for retirements and legacy items | Phase 0 mapping for the evidence column; the H5 equivalence analysis | **yes** (M2 functional row) | Draft B1 |
| **B2** | M2-B architecture and S-CFG generalisation; seam interface notes | **PARTIAL** | `m2b-scfg-interface.md`; M2B-2 §1 (S-CLK) | One architecture note covering: the runtime observer; the multi-endpoint data plane; DS-TT VLAN translation; TSCAI; the `GptpSideband` labelled baseline (G2); S-PATH emission for M3; the hosted-evidence path for the M2B configurations | — | DR-02 | yes | B2 consolidation |
| **B3** | TSN AF offline compiler; reproduces the generator's bearer and QoS sections byte for byte before emitting anything new | **PARTIAL** | Tier-0: 147 / 147 (37 compatibility cases), 54 / 54 (TAS). Locally: 32 / 32 (common epoch, **not in tier-0**) | TSCAI; VID classification (currently refused); per-UE DRB templates; `.ini` section integration; traffic applications; S-PATH member-stream emission (M3) | Scenario runs using its output | B2 | yes | after B2 |
| **B4** | `StaticBmca` offline validator, conditional on the equivalence analysis (DR-03) | **NOT STARTED** | DR-03 analysis table | DR-03 conditions (2) (the fail-closed difference) and (3) (every legacy check with an offline counterpart and a test); then the validator | Legacy scalar check | Condition (1) **BLOCKED** on the VM-only datasets (DR-06b) | yes (DR-03) | conditions (2), (3) |
| **B5** | TAS / Qbv at the TT ports: default-off configuration, a gate oracle from the configuration, negative controls; acceptance by gate-observation rows on an independent environment | **IMPLEMENTED** | Level 2: M2B-2 / 3 / 5 component and bridge suites (local); the picosecond gate oracle; negative configurations | A hosted-evidence path (a maintainer decision on the tier-1 query extension, M2B-3 §8, or a DR-15 hosted run); the M2B-5 compiler suite into tier-0 (a CI change); optionally ConfigChange semantics | The protocol row "gates observed opening and closing" on an independent environment; the scientific items of M2B-5 §6 | Independent executor; the acceptance protocol is not yet written | yes | hosted-evidence decision |
| **B6** | Runtime bridge-delay observer: statistics per port pair; independent oracle | **IMPLEMENTED** | Level 2: M2B-2 offline observer; M2B-4 per-class pairing, all 238 bridged frames against the independent oracle (local) | As B5 for hosted evidence | Observer runs under an approved protocol | As B5 | yes | as B5 |
| **B7** | DR-04 analysis: the Phase 2 clock-error row against M2-S6 / S8 | **NOT STARTED** | — | The analysis note | — | — | yes (it decides S8 eligibility) | Write B7 |

**DR-02 scope items without a B number in the travel plan.** Recorded here with their own labels; they are not renumbered into B1–B7.

| Item | Status | Remaining | Blocker | 2.0 |
|---|---|---|---|---|
| DS-TT VLAN translation (retained by DR-02; legacy source PR #2 head `1501a50`) | **NOT STARTED** | Design (in B2), then a default-off implementation and oracle | — (PR #2 is legacy input only and targets the frozen `master`) | yes |
| Multi-endpoint data plane: S4 general case, S7, S8 (bidirectional, 3 endpoints) | **PARTIAL** | The S-CFG per-UE emitter (B3); the S8 integration scenario at N = 3 (not in the S7.2a set 1, 2, 4, 8) | UL gPTP needs S7.2b | yes |
| `GptpSideband` labelled baseline (G2 sideband part) | **NOT STARTED** | Design in B2 | — | yes (DR-02 task) |
| H5 retirement: equivalence analysis (streaming PHY, timing) | **NOT STARTED** (retirement pending) | Analysis note | — | yes (a DR-02 decision is pending on it) |
| Legacy-vs-1.8 statistical comparison | **BLOCKED** | — | Phase 0 mapping and datasets (DR-06, DR-06b) | yes (M2 experimental row) |
| Fingerprint suite on the new baseline | **BLOCKED** | — | B8: suite not located | yes (M2 regression row; M4 skill) |
| README boundary statement (DR-10) | **NOT STARTED** | Draft in E4 | — | yes (M4) |
| VM NED / INI compatibility corrections for 6.5.0 | Collected, **not reviewed** | Review from reviewed extracts (DR-12) | DR-12 | undecided |

### 9.5 M3, M4, Phase 5 and Phase 6

| Item | Objective and acceptance | Status | Accepted evidence | Remaining development | Remaining independent validation | Dependencies / blockers | 2.0 | Next action |
|---|---|---|---|---|---|---|---|---|
| **M3 FRER** | §4: INET replication and elimination at the TTs; member streams by VID or PCP → QFI → DRB (F1 DL, F2 UL) through S-PATH; `FrerRecovery` as an INET merge extension. Acceptance: zero duplicates, surviving-path delivery, sequence wrap and timeout, R-TAG placement, reliability against the legacy F1 / F2 sweeps. | **NOT STARTED** | — | D1 architecture (TP-1 … TP-3 vs RP; the HARQ wording of §4); D2 configuration-only probe; D3 `FrerRecovery` and S-PATH bindings (emission through B3) | Functional and protocol rows; the experimental comparison | D2 needs D1; D3 needs D2 and B3 (S-PATH emission). The comparison needs Phase 0 (legacy F1 / F2 sweeps). F3 / F4 deferred (blockers B1, B2), not blocking M3. | **yes** | D1 |
| **M4 release** | §5: README boundary statement and compatibility table; `opp_env` entry (B9); CI (a blocking pinned job plus a non-blocking nightly `simu5g@dev`); skills; claim-scoping notes. Acceptance: clean-machine install and run of every example; the dev job has run at least once; the boundary statement reviewed. | **NOT STARTED** (tier-0 and tier-1 CI groundwork exist) | — | E4: README 2.0 draft, compatibility table, `opp_env` check, skill drafts, nightly job, claim-scoping notes | Clean-machine install by the maintainer | M2 and M3; DR-18 release line (a release branch from the 2.0 line, then a default-branch transition) | — | E4 drafts |
| **Phase 5** | Upstream-gated items: F4 NR-DC, F3 inter-PDU-session, PDCP duplication, TSC assistance / CG, 5G time distribution, mobility realism, VLAN-scoped flooding, radio stage C | **DEFERRED** (F3, F4: DR-02; the rest on upstream triggers, none met) | — | — | — | Upstream | no | monitoring |
| **Phase 6** | Per-release upstream tracking | Ongoing; R181 **CLOSED** | `m2-r181-acceptance-record.md` | — | — | — | — | next upstream release |

### 9.6 Approved deferrals, unfinished work and open questions

**Approved deferrals (with decisions):**
- S7.4b BMCA (D7);
- F3 and F4 (DR-02, to Phase 5);
- S7.4a is optional for the release (F1), not deferred.

**Approved retirements:** H1, H2, S1, S3 (DR-02), subject to coverage of the replacement behaviour, to be evidenced in B1.

**Unfinished, not deferred:**
- Phase 0 mapping and reproduction;
- S7.2a stages 5–9;
- S7.2b and S7.3;
- S8;
- B1, B2, B3 (completion), B4, B7;
- DS-TT VLAN translation;
- the multi-endpoint S8 scenario;
- the `GptpSideband` baseline;
- the H5 analysis;
- the legacy comparison;
- the fingerprint baseline;
- M3 and M4.

**Open questions for the maintainer.** These are listed only; none is decided here.

| # | Question | Why it matters |
|---|---|---|
| Q-1 | Is S8 required for 2.0, or released as optional extended fidelity? | DR-04 ties S8 eligibility to the B7 analysis, which is not written |
| Q-2 | Does Phase 0 bit-identical regeneration gate M4, or only the legacy comparisons? | The §1 rule says nothing waits for Phase 0 closure; the M2 and M3 experimental rows need its mapping |
| Q-3 | Hosted evidence for the M2B configurations: the tier-1 configuration-query extension (M2B-3 §8) and/or a DR-15 hosted functional run | Currently local-only functional evidence |
| Q-4 | Add `test_tsnaf_compile_epoch.py` (pure Python, 32 / 32) to tier-0 | The M2B-5 compiler path is not under hosted regression |
| Q-5 | The disposition of the open PRs #2 and #3 (external, against the frozen `master`) | #2 is the source of the retained VLAN translation; #3 is relevant to M3 F2 / TP-3. Neither can merge into `master` (DR-18). |
| Q-6 | The DR-08 smoke closure records (N = 1, N = 2) | They are part of the DR-07c audit trail and need the private evidence |
| Q-7 | Preservation status of the hosted evidence archives (artifact expiry 24–25 Nov) and the pending job-log exports (register §4.1) | Evidence preservation |
