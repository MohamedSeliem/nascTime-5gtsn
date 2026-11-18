# nascTime 2.0 migration — decisions register (handover)

**Status: revision 3, approved 17 November 2026 with the maintainer's targeted corrections.** 17 November 2026 (revision 3: the evidence collection H1 / H2 is completed; the updates are marked "Update (rev. 3)"). Canonical location after approval: `docs/migration/migration-decisions-register.md`. Documents cited by name are located through `docs/migration/document-index.md`.

**Revision 4 (18 Nov 2026, WP-E4 Phase 3; pending the maintainer's review of this documentation).** Adds the entries DR-14 … DR-18 with the maintainer's decisions of 18 November 2026 as given to the development agent. Entries DR-01 … DR-13 are unchanged.

**Status (17 Nov 2026): every entry DR-01…DR-13 now has a dated Decision line.** The earlier text, including the recommendations, is preserved unchanged. Where a decision leaves a part open (for example the H5 retirement and per-paper reproduction), that part stays open.

Originally, every entry was OPEN. Each entry has two recommendation lines:
- "Author recommendation": the proposal of the draft author.
- "Reviewer recommendation (17 Nov 2026, pending final approval)": the maintainer's handover review. It is **not** a final decision.

A final decision is added as a new dated "Decision" line. The entry text is never rewritten. No agent may act on a recommendation as if it were approved.

| ID | Subject | Approval needed | Prevents implementation of | Prevents scientific acceptance of |
|---|---|---|---|---|
| DR-01 | Pinned stack | yes | the tier-1 CI pinned job; release packaging | every new M2 / M3 record (the stack is in its header) |
| DR-02 | M2 structure M2-A / M2-B | yes | M2-B work-package scope | M2 closure |
| DR-03 | `StaticBmca` | yes | the G6 replacement | the G6 coverage entry |
| DR-04 | M2-S8 | yes | — (design may proceed) | the release eligibility of S8 claims |
| DR-05 | S7.2a N range | confirmation | — | the S7.2a closure claim |
| DR-06 | Phase 0 | yes | — | the legacy comparisons (M2-B, M3) |
| DR-07a–d | Stage 5 H-ARQ contract; A-2.1 in E0v-N | yes | the A1 wrapper rows (design may proceed) | every E0v-N / E1 per-UE verdict |
| DR-08 | Smoke records | content confirmation | — | the DR-07c audit trail |
| DR-09 | Naming | no | — | — |
| DR-10 | README 2.0 | yes | the README draft location | M4 |
| DR-11 | Integration branch and document import | yes | **everything** (plan WP E0) | — |
| DR-12 | Remote access: private evidence repository and execution environments | yes | any agent work that reads private evidence; tiers 1–3 | every remote acceptance |
| DR-13 | Path resolution for extracted evidence archives | yes | DR-07c validations on a remote environment | the same |
| DR-14 | Tier-0 and tier-1 CI (rev. 4) | decided | — | — (CI is level 2 only) |
| DR-15 | Experimental tier-2 harness and hosted functional simulations (rev. 4) | decided | an unauthorised hosted run | — (level 2 only) |
| DR-16 | Licensing scope (rev. 4) | decided | any binary redistribution; commercial use | — |
| DR-17 | Archive policy and permanent branches (rev. 4) | decided | — | — |
| DR-18 | Release line and default branch (rev. 4) | decided in principle | an unrelated-history merge or a default-branch change now | M4 |

---

## DR-01 — Pinned stack

**Conflicting sources:**

| Source | What it says |
|---|---|
| `revised-migration-roadmap.md` §0 item 5 | OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0 |
| Roadmap §2 Phase 3 | Titled "FRER on vanilla 1.8.0" |
| Roadmap §2 Phase 4 | `opp_env` check for `simu5g-1.8.0` |
| `m2-s7-roadmap.md` §3 | A later release is a new baseline; 1.8.0 records are never re-labelled |
| `m2-r181-acceptance-record.md` §1.1 | 1.8.1 accepted on 6.4.0 |
| `m2-s7.2a-s5-env-decision.md` (D-2) and G0 record rev. 3 | Stage 5 reference is 6.5.0 / 4.7.0 / 1.8.1; G0 is verdict equivalence only |

**Implications:**
- Load-dependent 1.8.0 results are shaped by #308 / #310 / #311 (audit §5).
- The VM's 6.5.0 NED / INI corrections are not in the repository (R181 acceptance record §1.1; later status unconfirmed). They were collected privately before departure.

**Options:**
- (a) 1.8.0 for the release.
- (b) 6.5.0 / 4.7.0 / 1.8.1 for the remaining M2, M3 and M4.
- (c) 6.4.0 / 4.7.0 / 1.8.1.
- (d) Defer.

**Author recommendation:** (b), as a roadmap amendment that does not edit the roadmap text.

**Reviewer recommendation (17 Nov 2026, pending final approval):** adopt OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1 for the remaining M2, M3 and M4. **Preserve every historical stack-qualified record:**
- the 1.8.0 records;
- the 1.8.1-on-6.4.0 R181 records;
- the D-2 records.

**Update (rev. 3).**
- The maintainer has confirmed the identity of the target environment: OMNeT++ 6.5.0; INET 4.7.0 (`dfe270b21f`); unmodified Simu5G 1.8.1; `opp_env` 0.36.2.261110; Nix 2.34.4; Clang 21.1.8; GCC 15.2.0; GNU Make 4.2.1; Python 3.13.13; Ubuntu 22.04.5 LTS x86_64.
- Its configuration, Nix flakes and lock files are preserved (private archive).
- The VM NED / INI corrections are collected (the private VM-compatibility archive), not yet reviewed.
- **Remote reproducibility of this environment has not been demonstrated.** That is WP E2, and is not part of this decision.

**Decision (17 Nov 2026, maintainer):** Approved. OMNeT++ 6.5.0, INET 4.7.0 and unmodified Simu5G 1.8.1 for the remainder of M2, M3 and M4. Historical stack-qualified records are preserved.

## DR-02 — M2 structure and completion scope

**Sources:**
- Roadmap §2 Phase 2 (the full bridge-function scope and acceptance).
- `m2-s2-design.md` §7 (the gPTP stage plan S0–S8).
- `m2-s7-roadmap.md` §2.1 (the gPTP-only minimum release scope).
- Audit §1.1 (the non-gPTP items have not started).
- **The G1–G6 / S1–S8 definitions are recovered:** `README.md` at `v1.0.1` (`9e8bc83`), "Completed Features" tables, which also list H1–H6 and F1–F4. See `authoritative-migration-status.md` §3.

**Implications:**
- Coverage of G5 (TSN AF / CNC configuration) and G6 (Static BMCA) is missing on the 1.8 line.
- The S1–S8 data-plane multi-endpoint scaling items are covered only for gPTP (S7.2a).
- H1–H6 are not named by the roadmap's acceptance row. Including or retiring them must be decided, never silently dropped.

**Options:**
- (a) M2 = the full Phase 2.
- (b) M2 = gPTP only (scope reduction; rejected by constraint).
- (c) M2 = Phase 2 structured as M2-A and M2-B.

**Author recommendation:** (c).

**Reviewer recommendation (17 Nov 2026, pending final approval):** structure M2 into **M2-A (timing)** and **M2-B (bridge functionality)**, retaining the complete original Phase 2 scope.
- **M2-A:** S0–S7, plus S8 per DR-04.
- **M2-B:**
  - TAS / Qbv at the TT ports;
  - TSN AF offline compiler and runtime observer (G5);
  - multi-endpoint data plane (S1–S8);
  - `StaticBmca` per DR-03 (G6);
  - the G1–G6 / H1–H6 / S1–S8 coverage table;
  - the legacy-vs-1.8 comparison;
  - the fingerprint baseline.
- M2 closes only when both close.

**Proposed further point (for decision):** include H1–H6 in the coverage table, each either mapped or "retired, replaced by X".

**Decision (17 Nov 2026, maintainer):** Approved: the full M2-A and M2-B scope.
  - **Retirements approved:** H1, H2, S1 and S3, as implementation retirements, subject to coverage of the replacement behaviour.
  - **Pending:** the H5 retirement, until an equivalence analysis covers the streaming PHY and its timing implications.
  - **Deferred to Phase 5:** F3 and F4.
  - **Retained in M2-B:** DS-TT VLAN translation.

## DR-03 — `StaticBmca` (legacy G6)

**Sources:**
- Roadmap Phase 2: "ported".
- Inventory §3 and dependency matrix §2: "Keep".
- `m2-s7-roadmap.md` §4.3: "not reusable".
- S7 roadmap D7: BMCA deferred.

**Legacy capability-equivalence analysis.** Read-only, from the repository at `115012f`, which contains the legacy files:

| Aspect | Legacy implementation | Equivalence consideration |
|---|---|---|
| What it is | `src/nasctime/nodes/TsnAf/StaticBmca.{h,cc,ned}` (366 lines): a `cSimpleModule` that does all its work in `initialize()` and nothing in `handleMessage` | Not a BMCA. No dataset comparison and no Announce. |
| Inputs | Grandmaster module path and its 802.1AS attributes (priority1/2, clockClass, clockAccuracy, offsetScaledLogVariance); a JSON `spanningTree` (node, role MASTER / BRIDGE / SLAVE / TRANSPARENT, masterPorts, slavePort); `nwTtModule` / `dsTtModule` / `tsnAfModule`; `transparentClockEnabled`, `correctionFieldSupport` (`StaticBmca.ned`) | An offline validator can read the same data from the generated configuration (INET `Gptp` `gptpNodeType` / `slavePort` / `masterPorts`; S7 roadmap §4.1) |
| Checks | A grandmaster is configured and its module **exists** (`getModuleByPath`); exactly one MASTER; at least one SLAVE; transparent-clock consistency (`StaticBmca.cc` 109–170) | Module existence needs the resolved network. An offline validator must use OMNeT++'s own resolution (`opp_run -q runconfig` / NED loading), so it needs tier-1 CI. |
| Outputs | Signals `bmcaEstablished` / `bmcaValidationError`, recorded as `count` statistics; `EV` warnings; it **does not stop** the simulation on an error | Whether any legacy result used these scalars must be checked in the legacy results (Phase 0). The validator should fail closed, which is a behavioural difference and must be recorded as such. |
| API | `getNodeRole`, `isTransparentClock`, `getGrandmasterInfo`, `getSpanningTree` | **No caller in the repository:** `git grep` at `115012f` finds only the instantiations in `tests/qos_test`, `simulations/demos/multi_endpoint_test` and `ext_multiendpoint_test`, and their ini settings |

**Options:**
- (a) An offline validator (Python, over the resolved configuration).
- (b) Retire it with a "replaced by INET static roles" entry.
- (c) Port the C++ module.

**Author recommendation:** (a).

**Reviewer recommendation (17 Nov 2026, pending final approval):** prefer the offline `StaticBmca` validator, **conditional on a legacy capability-equivalence analysis**. The analysis above is the starting point. Still to be done before the decision:
- (1) confirm from the legacy results (Phase 0) that no published result used the `bmca*` scalars;
- (2) define the fail-closed difference;
- (3) list every legacy check with its offline counterpart and a test each.

**Update (rev. 3).** Item (1) can be partly prepared from the inventory of 79 legacy experimental files (private): which `.sca` files exist, and for which scenarios. Confirming the absence of `bmca*` scalars in the data needs the datasets themselves, which are on the VM only (DR-06b).

**Decision (17 Nov 2026, maintainer):** Approved: the offline `StaticBmca` replacement, conditional on the equivalence analysis.

## DR-04 — M2-S8

**Sources:**
- `m2-s2-design.md` §7: S8 = the Option C Suffix TLV, the TT clock synchronization error to 5G time (23.501 §5.27.1.2.1 / §5.27.1.9) and one-step. "3GPP-faithful carriage" only after S8.
- `m2-s7-roadmap.md` §2.3: a "separate milestone".
- The roadmap has no S8.
- **Relation to the original clock-error requirement.** The roadmap Phase 2 protocol row requires "offset error equal to the configured 5G-clock error model (ideal → bounded by INET's own error)", and S-CLK (§1) makes the 5G time source pluggable (ideal, nascTime error model, upstream T5). M2-S6 implemented per-port TT clocks with configured offset / drift models (C-a, E-all), 1863/1863 (`m2-s6-results.md`). Whether the S6 TT-clock model **is** the "configured 5G-clock error model" of the Phase 2 row, or whether the row needs S8's TT synchronization-error model, is **not settled** in the sources.

**Options:**
- (a) S8 required for M2.
- (b) S8 inside M2, extended fidelity, release-eligible only when its gates pass.
- (c) S8 moved out of M2.

**Author recommendation:** (b).

**Reviewer recommendation (17 Nov 2026, pending final approval):**
- Keep S8 inside M2 as extended standards fidelity.
- Do not block M3 development on it.
- Before deciding its release eligibility, resolve its relationship with the original configured clock-error requirement.

**Analysis to be prepared (plan WP B7, remote):** map the Phase 2 protocol row onto the M2-S6 TT-clock parameters and oracles, and state exactly what part, if any, needs the S8 model.

**Decision (17 Nov 2026, maintainer):** Approved. S8 remains within M2 as extended fidelity.

## DR-05 — S7.2a N range

**Sources:**
- `m2-s7-roadmap.md` §5.2: N ∈ {2, 4}.
- `m2-s7.2a-stage5-plan-1.8.1.md` rev. 1.1: N = 1, 2, 4, 8 (approved).

**Author recommendation:** N = 1, 2, 4, 8.

**Reviewer recommendation (17 Nov 2026, pending final approval):** retain N = 1, 2, 4, 8.

**Decision (17 Nov 2026, maintainer):** Approved: N = 1, 2, 4, 8 for the S7.2a campaign. This is **not** an overall framework scaling limit.

## DR-06 — Phase 0

**Sources:**
- Roadmap Phase 0: `legacy-v1.0`, `legacy/1.x`, bit-identical regeneration.
- `legacy-baseline-manifest.md` §4–§5: `legacy-snapshot-2026-10-12`, the local part pending, every result set unmapped.
- Maintainer audit, 17 Nov: `v1.0` → `f03e38d` and `v1.0.1` → `9e8bc83` exist; the other two tag names do not.
- The freeze scripts named in the manifest (`legacy-freeze.sh`, `legacy-results-archive.sh`, `test-freeze.sh`) are **not tracked in the repository** at `115012f`. Their current location is unknown (collected by procedure C-4).

**Author recommendation:** `v1.0.1` as the legacy source identity; no new tags; Phase 0 closes only on bit-identical regeneration.

**Reviewer recommendation (17 Nov 2026, pending final approval):** use `v1.0.1` **provisionally** as the legacy source identity, **without assuming that it identifies every paper's experimental baseline**.

Each published or submitted result set (including arXiv:2604.04616 and the multi-endpoint scaling results) needs its own recorded source identity:
- the commit, plus the uncommitted state;
- the Simu5G fork tag;
- the stack;
- the configurations and seeds.

These come from the evidence-acquisition step (C-4), **before** any legacy comparison is attempted.

**Update (rev. 3): provenance collected (H2, completed).**

| Item | What was collected |
|---|---|
| Recovered workspace | OMNeT++ 6.4.0; INET 4.6.0; nascTime `v1.0.1` (`9e8bc83dfdfaffd918eb304bda6b8ecb98ff0684`); customised Simu5G 1.5.0 at `31c38c176bd91d1bb88e883931bded825ad9cc8f` (tag `nasctime-v1.0`) |
| Uncommitted Simu5G working-tree corrections | Two functional corrections (insufficient MAC grants; unsigned header-size subtraction), preserved as a patch |
| Experimental files | An inventory of 79 legacy experimental files, and the historical migration records |
| Datasets | Remain on the VM: multi-endpoint, FRER, bridge and NW-TT result sets |

Consequences:
- **The relationship of these datasets to the published experiments is unverified.** The per-paper identities are therefore still open. The workspace identity is one candidate, not a proven baseline for any paper.
- **The working-tree patch shows that the legacy results may have been produced with code that differs from the tag.** Any reproduction must record which state was used.
- Phase 0 remains open. Bit-identical reproduction is **not** claimed.
- The historical patches are **not** ported into the new stack (zero-modification rule).

**Open sub-decision DR-06b: preserving the VM-only legacy datasets.**

| Option | What it means |
|---|---|
| (i) | Private release assets, as for H1 |
| (ii) | External archival storage |
| (iii) | Inventory only, accepting the risk that the datasets are lost |

**Author recommendation:** (i) when VM access resumes, because the VM holds the only copy.

**Decision (17 Nov 2026, maintainer):** Approved: the provisional `v1.0.1` identity. Per-paper reproduction remains open.

**Decision DR-06b (17 Nov 2026, maintainer):**
  - Preserve the complete legacy datasets when VM access resumes.
  - Until then they are on the VM only, so there is a risk of loss. That risk is recorded here.
  - No additional pre-departure collection is planned.

## DR-07 — Stage 5 H-ARQ contract and integration of A-2.1 into E0v-N

**Sources:**
- `m2-s7.2a-s5-2-addendum.md` §3.3–§3.5 (A-1, PU-4, S5-2-D2).
- `m2-s7.2a-s5-n2-protocol.md` §6.3 / N2-D2.
- `m2-s7.2a-a2-implementation.md` §10 (A2-D5).
- `simulations/m2/results/M2-S7.2a-a21-s1-closure.md` (`115012f`).

### DR-07a — Campaign contract

**Author recommendation:** F1-d(i) for the campaign, plus one full-contract diagnostic seed per batch.

**Reviewer recommendation (17 Nov 2026, pending final approval):** an F1-d(i) campaign contract plus **separately labelled full-contract diagnostics**, with three conditions:
- **Diagnostics are selected for meaningful retransmission coverage**, not as an arbitrary seed. E0v-N runs on ideal channels may contain no NACK at all; no recorded run except A2-V1 contains a DL NACK (`m2-s7.2a-a2-design-review.md` §1).
- The diagnostic is therefore a **declared configuration** with scheduler logging on (a default-off mixin) and declared NACK injection (the A2-V1 mixin pattern, `m2s72a2v.ini`).
- Before the run, it declares minimum counts: NACK chains on more than one UE, multi-NACK groups, and at least one maxHarqRtx discard.

The MAC / scheduler-log **non-perturbation gate** (plan rev. 1.1 §2.1, NC-nonpert) is kept: a twin with and without scheduler logging must be identical on the non-log outputs.

### DR-07b — Integration form

**Author recommendation:** new wrapper rows (PU-4h, PU-4o, per-UE A2-8) in a new module. A-1 PU-4 kept and reported, not gating.

**Reviewer recommendation (17 Nov 2026, pending final approval):** adopt new A-2.1 wrapper rows. Preserve and report the historical A-1 PU-4.

### DR-07c — Validation of the integration

**Correction from revision 1.** Revision 1 was inconsistent:
- the executive summary named "N = 2 and A2-V1";
- the register named "N = 1 plus N = 2";
- WP-2 named "N = 2 and A2-V1".

Revision 2 defines three distinct validations. Each uses the preserved outputs where they exist; the existence and integrity of those outputs is checked by procedure C-2. Each is a read-only evaluation, not a simulation.

| ID | Input | What is checked | Expected (declared now) |
|---|---|---|---|
| V-N1 | N = 1 smoke `M2S72-E0v-q0-f1`, seed 0 (preserved on the VM; smoke protocol §5) | ACK-only, one UE. Invariance of the new rows against the accepted A-1 result. | A-1a = 11 697 lines, with ambiguous = orphan = re-insert = 0, as accepted. The A-2.1 rows PASS, with A2-4a / b / c NOT EXERCISED. Per-UE occupancy from A-2.1 equals the A-1 occupancy. PU-4 (A-1) PASS, reported unchanged. A2-8 PASS. |
| V-N2 | N = 2 smoke `M2S72-E0vN-q0-one0-n2-f1`, seed 0 (preserved; `m2-s7.2a-s5-n2-protocol.md` §7) | ACK-only, two UEs, 384 same-TTI pairs | A-1 numbers reproduced unchanged: A-1a 9 718, A-1b 2 476, ambiguous 768, re-insert 768, orphan 0, **PU-4 FAIL retained**. A-2.1: every line attributed, the exchangeable groups certified, per-UE occupancy evaluated and equal to the XA truth (XA-6, NOT EVALUATED under A-1, now evaluable). A2-8 PASS for both UEs. A2-4 rows NOT EXERCISED. |
| V-V1 | A2-V1 run `M2S72-E0vN-q0-one0-n2-f1_A2V1` (sealed; seal `3d00ef8e…`) | Genuine NACKs; consistency of the wrapper with the accepted S1 result | The wrapper's per-UE accounting is identical to the S1 closure §3 tables (13 105 lines, 144 NACKs, 129 PDUs retransmitted, 6 censored, A2-8 values of §4). Under F1-d(i), A2-4c NOT EVALUATED. The E0v-N rows that do not apply to this non-E0v configuration are reported NOT APPLICABLE, never PASS. |

S5-2-D2 (the adapter validation record) would cite V-N1 and V-N2. S5-2-D2 stays a separate decision.

**Update (rev. 3): inputs now preserved.**
- V-N1, V-N2 and V-V1 can use the private evidence archives (N = 1 smoke: 41 files; N = 2 smoke: 58 files; A2-V1: 58 files). All were verified against the original manifests before packaging, and re-verified after download.
- They can therefore run on any approved independent environment with access to the release (DR-12), using the path resolution of DR-13. They no longer need the VM.
- They remain **read-only evaluations** and level-3 candidates only under `remote-execution-feasibility.md` §4.

**Reviewer recommendation (17 Nov 2026, pending final approval):** reconcile as above; distinct expectations for N = 1, N = 2 and A2-V1, using preserved output where available.

### DR-07d — First genuine occurrence gate

**Author recommendation:** a run in which A-2.1 meets a path validated only synthetically (a discard, a multi-NACK group or a censored NACK) is flagged "first genuine occurrence" and held for review.

**Reviewer recommendation (17 Nov 2026, pending final approval):** retain the first-genuine-occurrence review gate.

**Decision (17 Nov 2026, maintainer):** Approved: the revision-3 recommendations DR-07a–d. That includes:
  - the declared diagnostic coverage;
  - the non-perturbation gate;
  - preservation of the historical A-1 PU-4 result;
  - the three distinct adapter validations V-N1, V-N2 and V-V1;
  - the first-genuine-occurrence review.

## DR-08 — Smoke closure records

**Sources:**
- N = 1 acceptance quoted only in `m2-s7.2a-s5-n2-protocol.md` §1.
- N = 2 acceptance quoted only in `m2-s7.2a-a2-design-review.md` §1.
- No closure record in either location.

**Author recommendation:** export the VM records first, then write the closure records citing them.

**Reviewer recommendation (17 Nov 2026, pending final approval):**
- Reconstruct the smoke records from **verified evidence**: the records collected by C-2, checked against their manifests.
- Or, where the evidence is unavailable, from **explicitly identified historical statements**, quoted with their source document and labelled as such.

**Update (rev. 3).** The verified evidence now exists in the private evidence archives. The closure records can therefore be written from it, citing the archives and their checksum manifest. The original verdicts are transcribed, never re-derived or reinterpreted. A closure record is a **private** document until its publication class is approved.

**Decision (17 Nov 2026, maintainer):** Approved. Closure records are reconstructed from verified evidence, or from explicitly labelled historical statements.

## DR-09 — Naming

The collisions are F1–F4 (FRER bindings vs S7-roadmap decisions), F3 (also A2-D2-F3), F1-d(i), S-numbers (M1, M2 and the legacy S1–S8), and S5 (M2-S5 vs S7.2a Stage 5). The legacy README adds G, H, S and F series of its own.

**Author recommendation:** qualified names everywhere, with a glossary.

**Reviewer recommendation (17 Nov 2026, pending final approval):** adopt the qualified naming convention.

**Decision (17 Nov 2026, maintainer):** Approved.

## DR-10 — README 2.0

**Source:** audit §1.2. The legacy README describes v1.0 and documents a `tests/fingerprint/` that is not in the repository.

**Author recommendation:** draft on the development line; replace at the M4 release.

**Reviewer recommendation (17 Nov 2026, pending final approval):** prepare the README 2.0 draft on the development line.

**Decision (17 Nov 2026, maintainer):** Approved.

## DR-11 — Integration branch and document import

**Sources:**
- Maintainer ancestry audit, 17 Nov: the eleven implementation branches are ancestors of `m2/s72a-a21`; `plan/m2-s7.2a-stage5` (`57fa0c5`) is not.
- Proposed baseline `033c3ed`.
- **Checked (read-only, 17 Nov):** relative to its merge base `2586bce`, `plan/m2-s7.2a-stage5` adds exactly one file, `simulations/m2/plans/M2-S7.2a-stage5-plan-1.8.1.md` (341 lines, sha256 `fc94011f…`). That file is not in `115012f`. A selective import of that one file therefore carries the branch's entire content.

**Author recommendation:** merge the plan branch into a new integration branch.

**Reviewer recommendation (17 Nov 2026, pending final approval):**
- Create `m2/continuation` from `033c3ed` **after approval**.
- Prefer **selective import** of the approved plan documents, with source-commit provenance (each imported file records its source commit `57fa0c5` and path in `document-index.md`).
- A complete branch merge requires a **reviewed merge preview** (`git merge --no-commit --no-ff` in a scratch worktree, then a review of the diff) before any merge.

**Decision (17 Nov 2026, maintainer):** Approved. Create `m2/continuation` from `033c3ed` and selectively import the Stage 5 plan file.

## DR-12 — Remote access: private evidence and execution environments (new in rev. 3)

**Sources:** the maintainer instruction of 17 Nov: "Do not assume that a remote development agent has access to the private repository or to a simulation execution environment. Both must be explicitly configured and verified. Do not attach a persistent personal VM runner to the public repository." Also `remote-execution-feasibility.md`.

**Implications:**
- By default, the agent works only on the public repository with tier-0 CI.
- Access to the private repository (a read-only deploy key or a fine-grained token scoped to that repository) must be configured by the maintainer. The agent then verifies it by a read of a known file with a known sha256.
- Private content must never flow into public workflows, logs or commits.

**Options:**
- (a) No private access during travel.
- (b) Read-only access for the development agent, limited to the handover set, the inventories and the protocols.
- (c) Read-only access including the evidence archives (needed only by an independent executor, not by the development agent).

**Author recommendation:** (b) for the development agent. Evidence archives (c) go only to a designated independent executor (feasibility X-1), never to the development agent's public workflows. No persistent personal VM runner is attached to the public repository.

**Decision (17 Nov 2026, maintainer):** **No private-repository access for the initial remote development agent.** Reviewed documents are provided selectively where necessary. Any future private access must be explicitly configured and verified, with real access controls, not instructions alone.

## DR-13 — Path resolution for extracted evidence archives (new in rev. 3)

**Source:** the original manifests record absolute VM paths (`<results-root>/…`, `<vm-home>/…`). They are sealed and must not be rewritten.

**Options:**
- (a) Mount the extraction read-only at the original absolute prefix (for example a container bind mount), so that the reviewed tools run unchanged.
- (b) In-memory prefix mapping, for checksum verification only, with no modified manifest written.
- (c) Rewrite the manifests (rejected: alters sealed evidence).

**Author recommendation:** (a) for any evaluation, (b) for integrity checks. The method is recorded in every verification record (`authoritative-migration-status.md` §0.4). A tool that rejects mapped paths is correct and is not weakened.

**Decision (17 Nov 2026, maintainer):** Approved:
  - read-only mounting at the original prefix, for evaluation;
  - in-memory path mapping, for integrity verification.

  The method is validated before any independent evaluation. Original manifests are never rewritten, and original evidence is never modified.

## DR-14 — Tier-0 and tier-1 CI (new in rev. 4)

**Sources:**
- `h4-first-task.md` and PR #4 (tier-0);
- `ci/tier1/README.md` and PR #7 (tier-1);
- `repository-archive-and-evidence-register.md` §3.1–§3.2.

**Facts recorded with the decision:**
- **Tier-0 negative controls.** Both failed at their intended hosted gates: the fixture gate, and the Simu5G identity gate.
- **Tier-1 negative controls N-1 and N-2.** Both failed during the offline self-tests. **Neither exercised its intended downstream hosted negative gate.**
- **Tier-1 triggering.** Tier-1 automatically selects relevant non-draft pull requests. The label `tier1:run` is an override, including for draft pull requests.
- **Tier-1 scope.** Tier-1 validates the release build, linkage and its specific reviewed configuration queries. It does not automatically validate every newly introduced NED or INI configuration.

**Decision (18 Nov 2026, maintainer):** Tier-0 and tier-1 CI are accepted and integrated. Tier-0 remains required. Tier-1 remains non-mandatory at repository-ruleset level.

## DR-15 — Experimental tier-2 harness and hosted functional simulations (new in rev. 4)

**Sources:** the WP-E3 experiments E3a (PASS), E3b (PUBLICATION FAILURE, preserved) and E3b-R1 (PASS) (`repository-archive-and-evidence-register.md` §3.3); `ci/tier2/` on `wp-e3/e3b-r1-publication`.

**Decision (18 Nov 2026, maintainer):**
- The experimental tier-2 harness is retained on the frozen `wp-e3/e3b-r1-publication` branch.
- Individually authorised, bounded hosted functional simulations are permitted during travel.
- There is no automatic tier-2 integration.
- Hosted functional simulations remain **level-2 development evidence**. They never replace independent scientific execution, and they are never level 3 (`remote-execution-feasibility.md` §4, X-1).

## DR-16 — Licensing scope (new in rev. 4)

**Sources:** `remote-execution-feasibility.md` §3 (L-1 … L-3).

**Decision (18 Nov 2026, maintainer):**
- Academic-use scope is confirmed by the maintainer for current nascTime development and simulation.
- No compiled framework binary is redistributed.
- Commercial use is outside the current scope.

## DR-17 — Archive policy and permanent branches (new in rev. 4)

**Sources:** the WP-E4 consolidation plan; `repository-archive-and-evidence-register.md` §1–§2.

**Decision (18 Nov 2026, maintainer):** The archive policy is implemented.
- **Branches:** four permanent branches are retained:
  - `master` (frozen legacy provenance);
  - `m2/continuation` (integration);
  - `m1/ethernet-bridge` (frozen M1 provenance);
  - `wp-e3/e3b-r1-publication` (frozen experimental tier-2 harness).
- **Tags:** 30 tags are retained: `v1.0`, `v1.0.1` and 28 annotated `archive/*` tags.
- **Deleted branches:** the 26 deleted branches remain reachable through their archive tags.
- **External PRs:** #2 and #3 stay open.
- **Phase 0:** additional Phase 0 tags remain deferred.
- **Future work** uses short-lived work-package branches from `m2/continuation`.

## DR-18 — Release line and default branch (new in rev. 4)

**Source:** `m2/continuation` shares no history with `master` (its only root is the snapshot `14d5e0f`), and the default branch is `master`.

**Decision (18 Nov 2026, maintainer):**
- **When release-ready:** prefer a release branch cut from the 2.0 integration line, and a default-branch transition.
- **Not now:** no unrelated-history merge into `master` and no default-branch change.
- `master` and `m1/ethernet-bridge` are retained as frozen provenance.
