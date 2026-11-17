# nascTime 2.0 migration — public document index

**Status:** published with the E0 documentation-only integration commit on `m2/continuation`, 17 November 2026, after a line-by-line publication review.

## 1. Publication classes

| Class | Meaning | Where it lives |
|---|---|---|
| **P** (public) | Reviewed for publication and committed to this repository | `docs/migration/` and existing repository paths |
| **R** (restricted) | Private planning, design and protocol documents; cited for traceability only | maintainer's private planning space; reviewed extracts on request |
| **X** (excluded) | Private evidence, infrastructure details, collaboration material and collection procedures | private archives; never published |

Approval of the classification framework is **not** approval to publish any R or X document. Each new public document requires its own line-by-line content review (decision of 17 November 2026).

## 2. Published migration documents (P)

| Document | Purpose |
|---|---|
| `docs/migration/authoritative-migration-status.md` | Single status record: environment, evidence locations (generic), capability dispositions, workstream status |
| `docs/migration/migration-decisions-register.md` | DR-01 … DR-13 with recommendations and dated decisions |
| `docs/migration/travel-development-plan.md` | Prioritised backlog for remote development (not a delivery commitment) |
| `docs/migration/remote-agent-handover.md` | Instructions and boundaries for a remote development agent |
| `docs/migration/remote-execution-feasibility.md` | Execution tiers 0–3; requirements and open items |
| `docs/migration/h4-first-task.md` | Specification (revision 2) of the first implementation task: tier-0 Python regression CI. **Not implemented.** |
| `docs/migration/document-index.md` | This index |

## 3. Imported planning file (P)

| File | Provenance |
|---|---|
| `simulations/m2/plans/M2-S7.2a-stage5-plan-1.8.1.md` | Imported byte-identically (DR-11) from commit `57fa0c5` on branch `plan/m2-s7.2a-stage5`. Relative to the merge base `2586bce`, that branch adds only this file. SHA-256 `fc94011f4a79cf4397be04ed2353b4b6a25c08becaf5a13da8594654099f065a`, 341 lines. The branch itself is not merged. |

## 4. Documents cited by bare name

### 4.1 Available in this repository

The migration documents cite some records by their planning-space names. Their repository counterparts are:

| Cited name | Repository path |
|---|---|
| `m1-closure-report.md` | `simulations/m1/M1-closure.md` |
| `m2-r181-acceptance-record.md` | `simulations/results/simu5g-1.8.1/M2-R181-acceptance-record.md` |
| `m2-r181b-closure-report.md` | `simulations/results/simu5g-1.8.1/r181b/M2-R181b-closure-report.md` |
| `m2-r181c-closure-report.md` | `simulations/results/simu5g-1.8.1/r181c/M2-R181c-closure-report.md` |
| `m2-s0-results.md` | `simulations/m2/results/M2-S0.md` |
| `m2-s1-results.md` | `simulations/m2/results/M2-S1.md` |
| `m2-s3-results.md` | `simulations/m2/results/M2-S3.md` |
| `m2-s4-results.md` | `simulations/m2/results/M2-S4.md` |
| `m2-s5-results.md` | `simulations/m2/results/M2-S5.md` |
| `m2-s6-results.md` | `simulations/m2/results/M2-S6.md` |
| `m2-s7.1-results.md` | `simulations/m2/results/M2-S7.1.md` |
| `m2-s7.2a-a2-control-fix.md` | `simulations/m2/results/M2-S7.2a-a2-control-fix.md` |
| `m2-s7.2a-a2-design-review.md` | `simulations/m2/results/M2-S7.2a-a2-design-review.md` |
| `m2-s7.2a-a2-implementation.md` | `simulations/m2/results/M2-S7.2a-a2-implementation.md` |
| `m2-s7.2a-a2d2-f1-root-cause.md` | `simulations/m2/results/M2-S7.2a-a2d2-f1-root-cause.md` |
| `m2-s7.2a-a2d2-protocol-r1.md` | `simulations/m2/results/M2-S7.2a-a2d2-protocol-r1.md` |
| `m2-s7.2a-checkpoint1-rev2-results.md` | `simulations/m2/results/M2-S7.2a-checkpoint1-rev2.md` |
| `m2-s7.2a-checkpoint2-results.md` | `simulations/m2/results/M2-S7.2a-checkpoint2.md` |
| `m2-s7.2a-checkpoint2-rev2-results.md` | `simulations/m2/results/M2-S7.2a-checkpoint2-rev2.md` |
| `m2-s7.2a-s5-2-addendum.md` | `simulations/m2/results/M2-S7.2a-s5-2-addendum.md` |
| `m2-s7.2a-s5-env-decision.md` | `simulations/m2/results/M2-S7.2a-s5-env-decision.md` |
| `m2-s7.2a-s5-n2-protocol.md` | `simulations/m2/results/M2-S7.2a-s5-n2-protocol.md` |
| `m2-s7.2a-stage5-plan-1.8.1.md` | `simulations/m2/plans/M2-S7.2a-stage5-plan-1.8.1.md` (imported in E0) |

### 4.2 Private planning documents (R)

Cited for traceability only. They are not in this repository. A remote agent has no access to them (DR-12); the maintainer provides reviewed extracts where necessary.

| Cited name |
|---|
| `inventory-and-architecture.md` |
| `legacy-baseline-manifest.md` |
| `m1-plan.md` |
| `m2-s0-design.md` |
| `m2-s1-design.md` |
| `m2-s2-design.md` |
| `m2-s7-roadmap.md` |
| `m2-s7.2a-design.md` |
| `m2-s7.2a-s5-1-review.md` |
| `m2-simu5g-1.8.1-audit-and-plan.md` |
| `revised-migration-roadmap.md` |
| `upstream-dependency-matrix.md` |

## 5. Private material (X), referenced generically

- Private evidence archives: N = 1 smoke, N = 2 smoke and A2-V1 raw evidence; the sealed S1 archive; supplementary environment, F3, legacy-provenance and VM-compatibility archives. Checksum-manifested; maintained privately by the project owner.
- The pre-departure evidence-collection record and its reusable procedure. Not published: the procedure's repository discovery must first be restricted to explicitly approved workspaces and reviewed content.
- The preserved `opp_env` / Nix configuration, flakes and lock files: publication only after content review (feasibility F-11).
- The maintainer's decision checklist and internal revision notes.
- Legacy datasets that currently exist only on the original VM (DR-06b).
