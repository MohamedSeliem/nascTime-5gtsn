# nascTime 2.0 — operating instructions for a remote development agent

**Status: revision 4, 18 November 2026 (WP-E4 Phase 3, documentation-only; pending the maintainer's review).** Revision 3 was approved on 17 November 2026 with the maintainer's targeted corrections. Canonical location: `docs/migration/remote-agent-handover.md`. Revision-4 changes are marked "(rev. 4)".

**How to read this revision.**
- Text between *[Superseded (rev. 4)…]* and *[end of superseded text]* is retained revision-3 history. It is **not** an active instruction and **not** the current repository status.
- The current position is given by the "(rev. 4)" text and by the decisions DR-14 … DR-18.
- **WP-E4 (repository consolidation and travel handover) is completed by the documentation pull request that introduces revision 4.**
- **Still open:** release documentation and M4 readiness. These are plan work package **E4** (M4 groundwork: README 2.0, compatibility table, `opp_env` entry, skills, nightly job), which is a different item from WP-E4.

This file is self-contained. Where it and any other document disagree, stop and ask (§12). Do not choose between them yourself.

## 1. Repository and continuation baseline

| Item | Value |
|---|---|
| Repository | `github.com/MohamedSeliem/nascTime-5gtsn` |
| Continuation baseline | `m2/s72a-a21-fixture` at `033c3ed3fbc5b6ee21271ce24c62084283d8e79b`: the accepted A2-V1-S1 closure (`115012f`) plus the genuine F3 fixture `simulations/m2/check/fixtures/a2v1-first-chain.log.gz` (sha256 `cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b`) with its `.sha256` and `.meta.json` |
| Integration branch | `m2/continuation`, created from `033c3ed` **after the maintainer approves DR-11**. Work only there, through feature branches. **(rev. 4)** Reviewed pre-E4 integration baseline: `290babba3d12942344a2153f9ea5ea54287df366` (tier-0 and tier-1 integrated). This is not a permanent head: the live head advances when the WP-E4 documentation PR is merged, and with every later merge. Always start from the **current** head of `m2/continuation`. |
| Frozen | `master` (`9e8bc83`, tag `v1.0.1`) and tag `v1.0` (`f03e38d`). Never commit to, merge into or rebase `master`. Never create, move or delete tags. **(rev. 4)** Also frozen:<br>• `m1/ethernet-bridge` (`fbe41a9`, M1 provenance);<br>• `wp-e3/e3b-r1-publication` (`edf3329`, the experimental tier-2 harness);<br>• the 28 annotated `archive/*` tags (DR-17).<br>`master` and `m2/continuation` share no history (DR-18). |
| Accepted history | *[Superseded (rev. 4); not an active instruction:]* All branches listed in `docs/migration/authoritative-migration-status.md` §0.1. Never rewrite, force-push or delete them. *[end of superseded text]* Current rule: never rewrite, force-push, move or delete the four permanent branches or any tag. **(rev. 4)** Only four branches remain. The heads of the 26 deleted branches are preserved by archive tags. Resolve a historical branch name with `repository-archive-and-evidence-register.md` §2.2; never recreate a deleted branch. |
| Private evidence | A private, access-controlled evidence archive maintained by the project owner. Contents: the N = 1 smoke, N = 2 smoke and A2-V1 evidence archives; the sealed S1 evidence ((private)); supplementary archives (environment, F3, legacy provenance, VM compatibility).<br>**You have no access (DR-12, 17 Nov).** The maintainer gives you reviewed documents where necessary. Any future access will be configured with real access controls, and you will verify it (read a named file and compare its sha256) before using it. Never write to it. Never copy its content into the public repository, a public workflow, a log, an issue or a pull request. |
| Simulation environments | **None is available to you by default.** The VM is the maintainer's. No persistent personal VM runner is attached to the public repository (maintainer instruction, 17 Nov). **(rev. 4)** A hosted functional simulation on a GitHub-hosted runner is possible **only when the maintainer individually authorises it**, with its bounds and acceptance declared beforehand (DR-15). It is level-2 development evidence only. |

## 2. Required reading order

All paths are repository paths on the integration branch, after plan WP E0 has imported the approved documents. `docs/migration/document-index.md` is the **single navigation index**. It gives every document's origin, version, checksum and publication class.

A document marked *private* there is not in the public repository. You have no access to it (DR-12); ask the maintainer for a reviewed extract if you need it. Never reconstruct a document.

1. `docs/migration/remote-agent-handover.md` (this file)
2. `docs/migration/document-index.md`
3. `docs/migration/authoritative-migration-status.md`
4. `docs/migration/migration-decisions-register.md`. Only dated "Decision" lines are approved.
5. `docs/migration/travel-development-plan.md`
6. `docs/migration/remote-execution-feasibility.md`
7. The roadmap and S7 documents, at the locations given by the index: the revised migration roadmap (§0, §1 seams, §2 phases) and the S7 roadmap rev. 2.2 (D1–D8, F1–F4, C-1…C-8, §2, §9).
8. The S7.2a design rev. 2.1 (§7, §10, §11); the Stage 5 plan rev. 1.1; decision D-2; the G0 record; the S5-2 addendum (§3.3–§3.5); the E0v protocol rev. 1.1.
9. The A-2 / A-2.1 chain under `simulations/m2/results/`: `M2-S7.2a-a2-design-review.md`, `-a2-implementation.md`, `-a2d2-f1-root-cause.md`, `-a21-implementation.md`, `-a21-f3-protocol.md`, `-a21-f3-closure.md`, `-a21-s1-protocol.md`, `-a21-s1-closure.md`.
10. The legacy README at `v1.0.1` (`git show v1.0.1:README.md`): the G / H / S / F capability tables.

## 2a. Priorities (maintainer, 17 Nov), in this order

1. GitHub-based development on isolated branches.
2. Tier-0 Python regression CI.
3. Tier-1 full-stack build feasibility.
4. Tier-2 functional smoke testing.
5. Separately authorised scientific execution and acceptance.

*[Superseded (rev. 4); not an active instruction:]* Your first task is specified in `docs/migration/h4-first-task.md` (if approved). *[end of superseded text]* H4 is completed; the next task is A1.

**(rev. 4) Status:**
- Items 1–3 are done: tier-0 (PR #4) and tier-1 (PR #7) are integrated (DR-14).
- Item 4 was demonstrated by the one-time experiments E3a and E3b-R1. Further hosted runs are individually authorised (DR-15).
- Item 5 is unchanged.
- The next development task is **A1** (`travel-development-plan.md` §3a).

**(rev. 4) Working roles:**
- Claude Code designs, implements and tests.
- ChatGPT reviews code and evidence independently.
- GitHub tier-0 / tier-1 validate (level 2).
- The independent scientific executor produces qualifying scientific evidence.
- The maintainer approves, integrates and accepts.

## 3. Branching and pull-request policy

- *[Superseded (rev. 4); not an active instruction:]* One feature branch per increment from `m2/continuation`, named `wp-<id>/<short-name>` (WP ids as in the plan). *[end of superseded text]* **(rev. 4, DR-17)** Short-lived work-package branches named `wp/<id>-<slug>` (for example `wp/a1-a21-e0vn-wrapper`). They are deleted by the maintainer after merge.
- **Pull requests:**
  - target `m2/continuation` only;
  - contain one increment;
  - list every changed existing file with its justification;
  - state the level reached (§8).
- **Merge:** the maintainer approves and merges. The agent never self-merges, squashes or rebases reviewed history.
- **Commit messages** state what was run and what was not ("no simulation", "synthetic only", "functional smoke only").

## 4. Development environment

| Purpose | Environment |
|---|---|
| Python checkers and tests | Python ≥ 3.11 (validated locally on 3.13); the checkers use the standard library only. A Simu5G `v1.8.1` **source** checkout in `SIMU5G_ROOT` (no build) for the A2-0s source-contract rows. |
| C++ / NED / ini | The pinned stack (DR-01; currently D-2: OMNeT++ 6.5.0, INET 4.7.0, Simu5G 1.8.1), built **unmodified**; `libnasctime_m2` built with the repository `Makefile`. *[Superseded (rev. 4); not an active instruction:]* Available to you only through tier-1 CI once WP-E2 has verified and enabled it. Until then, C++ / NED work stays at design or prototype level and is labelled so. *[end of superseded text]*<br>**(rev. 4)** Tier-1 is enabled (PR #7).<br>• **What it validates:** the release build, linkage and **its specific reviewed configuration queries** only. A new NED or INI configuration is **not** validated automatically.<br>• **When it runs:** automatically for relevant non-draft pull requests; for a draft, only if the maintainer adds `tier1:run`. |
| Simulations | *[Superseded (rev. 4); not an active instruction:]* Short functional smoke runs in tier 2 only, once enabled, and **never** as evidence. *[end of superseded text]* Scientific runs happen only in an independent environment (§11) and are never started by you. **(rev. 4)** Tier 2 is not integrated. A hosted functional run needs an individual authorisation (DR-15) and yields level-2 development evidence only. |

## 5. Upstream prohibition and change discipline

- **Never modify OMNeT++, INET or Simu5G**, on any branch, including vendored copies.
- **Allowed:**
  - subclassing in nascTime's library;
  - NED `typename` replacement;
  - new chunks, serializers and tags;
  - parameters and configuration.
- **New behaviour is default-off**, through conditional NED wiring or default-off parameters, so every existing configuration stays byte-identical (S7 roadmap C-2).
- nascTime includes no Simu5G header outside `simu5g/common` type definitions.
- **Evidence vs source:**
  - Records, evidence, fixtures and manifests are immutable.
  - Source files frozen by an accepted record stay frozen: the A-2 modules (`fbee202`) and the A2-V1 evaluator (`39a6434`), guarded by the A-2.1 test T-frozen-untouched.
  - Generated-configuration sections are append-only (plan rev. 1.1 §3).
  - Every other source file is active. It may be changed when the pull request justifies the change and the regression suites show that reviewed behaviour is preserved, or that a deliberate change is declared.

## 6. Regression testing requirements

Every pull request reports CI results for:

| Suite (`simulations/m2/check/`) | Expected on the baseline |
|---|---|
| `test_m2s72_a2.py` | 18 / 18 |
| `test_m2s72_a2probe.py` | 11 / 11 |
| `test_m2s72_a2v1.py` | 10 / 10 |
| `test_m2s72_gen.py` | 67 PASS, 0 FAIL |
| `test_m2s72s5.py` | 38 / 38 |
| `test_m2s72s5_2.py` | 28 / 28 |
| `test_m2s72s5_n2.py` | 19 / 19 |
| `test_m2s72s5_smoke.py` | 9 / 9 |
| `test_m2s72_a21.py` | 18 / 18, 0 PENDING (fixture present at `033c3ed`) |
| `test_m2s72_a21_fixture.py` | 14 / 14 |
| `test_m2s72a2v1_wrapper.py` | 21 / 21 with a real `opp_run` (tier 1). Otherwise NOT RUN, never "passed". **(rev. 4)** Run by tier-1 (C-13) under the strict audit shim. |
| `test_m2s72_compare.py` | needs a census run directory: NOT APPLICABLE |

Rules:
- A changed count is a finding to explain before merging. PENDING is never PASS.
- New code brings tests and negative controls. A negative control counts only if its declared row passed before the mutation; otherwise it is NOT BUILDABLE.
- NED / ini / C++ changes also need, as **held items**: G0-style byte identity of earlier milestones, and regeneration with T0 identity for the generator.

## 7. Scientific acceptance gates

- Criteria and predictions are committed **before** the run they judge, and never adjusted afterwards.
- **Verdict vocabulary:** PASS, FAIL, NOT EVALUATED, NOT EXERCISED, NOT BUILDABLE, INCOMPLETE, STOP. Only PASS (and NOT EXERCISED, where a protocol allows it) count toward acceptance.
- Correctness gates and performance measurements are reported separately.
- **Synthetic evidence is always labelled** and never substitutes for genuine evidence. This covers the generators, injected chains and tier-2 smoke runs. The S1 closure §5 lists which A-2.1 paths are synthetic-only.
- **HARQ claims stay specific.** On 1.8.1 the #310 silent-deletion path is replaced, but maxHarqRtx discards remain possible. Never claim that HARQ discards are absent.
- **Acceptance boundaries are fixed** (status record §3.4a):
  - A-2 is validated on real ACK-only output only.
  - A2-V1 is **NOT ACCEPTED, permanently**.
  - A-2.1 F3 is accepted.
  - S1 is accepted **under F1-d(i) only**; the A-2.1 full contract is INCOMPLETE on A2-V1.
  - Never broaden any of these in wording.
- **Evidence paths.** Extracted evidence archives keep their original manifests with absolute VM paths. Resolve them by a read-only mount at the original prefix, or by in-memory mapping for checksum checks only. **Never rewrite a manifest** (status record §0.4; DR-13).

## 8. Code complete, CI-validated and independently accepted are different

| Level | Meaning | Who |
|---|---|---|
| 1. Code complete | Implemented to an approved design; tests written | development agent |
| 2. CI-validated | Every applicable CI tier green (synthetic, fixture, build, functional smoke) | CI; the agent reports |
| 3. Independently accepted | Executed in an independent environment (§11) under a pre-declared, approved protocol, by an executor other than the development agent; the record is accepted by the maintainer | **the maintainer** |

Every status statement names its level, for example "A1: level 2; V-N1 / V-N2 / V-V1 queued". A milestone or stage closes only at level 3, and only by the maintainer.

## 9. Evidence preservation

- Never delete, move, overwrite or re-hash existing evidence, fixtures, manifests or records.
- New evidence goes into new files with a sha256 pin. Protocols read raw outputs read-only and write to fresh directories, failing closed (pattern: `m2s72_a21_fixture.py`, E-0…E-7).
- Large raw data never enters Git (plan rev. 1.1 §4.2 tiers).
- Private evidence stays in the private repository.

## 10. Historical records; incomplete or failed evaluations

- Accepted and failed records are immutable. Examples:
  - A2-V1 NOT ACCEPTED;
  - the A-1 PU-4 FAIL;
  - CP2 rev. 1 FAIL;
  - the M2-S5 historical FAIL 66/71;
  - every stack-qualified 1.8.0 and 1.8.1 record.
- A correction is a **new**, versioned record or row that cites the old one.
- A FAIL, INCOMPLETE, NOT EVALUATED or STOP is reported as found, with its evidence, and stops at the review gate.
- No retry-until-pass. No change of inputs, thresholds or rows after seeing results.
- S1 is not reopened without a substantive new reason, stated to the maintainer.

## 11. Execution tiers and CI

The full analysis is in `docs/migration/remote-execution-feasibility.md`. *[Superseded (rev. 4); not an active instruction:]* Nothing beyond tier 0 may be assumed available or permitted until that document's checks are completed and the maintainer approves. *[end of superseded text]* The current tier status is the rev-4 table below (DR-14, DR-15).

| Tier | Purpose | Level it can support |
|---|---|---|
| 0 | GitHub Actions, Python suites, Simu5G source checkout | 2 |
| 1 | Full pinned-stack build, `opp_run -q runconfig`, NED loading | 2 |
| 2 | Short functional smoke runs | 2 ("runs to completion" is never a pass) |
| 3 | Independent scientific execution: the VM, or an approved hosted or self-hosted environment meeting feasibility §4 (independence, pinned identity, sealed outputs, pre-declared protocol, user acceptance) | 3 |

**(rev. 4) Tier status (DR-14, DR-15):**

| Tier | Status |
|---|---|
| 0 | Integrated and required |
| 1 | Integrated, not mandatory at ruleset level. Automatic for relevant non-draft pull requests; `tier1:run` overrides, including for drafts. Validates its specific reviewed configuration queries only. |
| 2 | Not integrated. The experimental harness is frozen on `wp-e3/e3b-r1-publication`. Individually authorised, bounded hosted runs only. |
| 3 | Unchanged |

E3a and E3b-R1 are level 2; they are not level 3.

The development agent never triggers, configures or alters tier-3 runs or their workflow files.

Rules for runners and secrets:
- **No persistent personal VM runner** may be attached to the public repository.
- Any self-hosted runner needs explicit approval, and must be ephemeral and limited to manually started protected workflows (feasibility S-1).
- Pull-request workflows get no secrets.

## 12. Maintainer approval boundaries

**Ask before:**
- any register item marked "approval needed";
- any change to milestone numbering or scope;
- any edit to a record, evidence or frozen source file;
- any new or changed acceptance criterion or threshold;
- merging;
- creating branches other than feature branches;
- any tag;
- enabling tiers 1–3 or any runner, paid resource or secret;
- **(rev. 4)** any hosted functional simulation (each needs an individual authorisation with bounds, DR-15);
- applying the `tier1:run` label;
- importing or publishing any document not classed public-safe in the index;
- any write to the evidence repository, or any request for access to it;
- any upstream contact (no new upstream action without the maintainer's approval).

**Never:**
- modify upstream;
- merge into `master`;
- run scientific simulations or fake their results;
- present synthetic or smoke results as genuine evidence;
- rewrite history;
- close a milestone.

When sources disagree or a decision is missing, raise it in the pull request or an issue and continue only with work that does not depend on the answer.

## 13. Glossary of easily confused names (DR-09)

| Name | Meaning |
|---|---|
| Legacy G1–G6, H1–H6, S1–S8, F1–F4 | Capability tables of the legacy `README.md` at `v1.0.1` |
| FRER bindings F1–F4 | Roadmap: F1 DL DRB, F2 UL, F3 inter-PDU-session, F4 NR-DC (= legacy F1–F4) |
| S7-roadmap decisions F1–F4 | The 2026-10-19 decisions (S7 roadmap §0.1) |
| A2-D2-F3 | Real-chain fixture sub-stage |
| F1-d(i) | A-2.1 contract without A2-4c |
| M1 S0–S5 / M2-S0…S8 | Milestone stages |
| M2-S5 | DS-TT egress correction |
| S7.2a Stage 5 | Scaling experiments: S5-1, S5-2, files `m2s72s5*` |
| A-1 / A-2 / A-2.1 | DL H-ARQ attribution rules. A-1 has the N = 2 PU-4 FAIL; A-2 is frozen at `fbee202`; A-2.1 is current. |
| M2-A / M2-B | M2 structure: timing / bridge functions (DR-02, approved 17 Nov 2026; this glossary said "pending" in rev. 3) |
| E3a / E3b / E3b-R1 (rev. 4) | One-time hosted functional experiments of WP-E3 (level 2):<br>• E3a: `M2S4U`, wired timing functionality;<br>• E3b: `M2S5`, PUBLICATION FAILURE;<br>• E3b-R1: `M2S5`, the downlink 5G–TSN timing path.<br>Not the M2-S5 stage or campaign. |
