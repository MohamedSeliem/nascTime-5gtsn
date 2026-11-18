# nascTime 2.0 — prioritised development backlog for the travel period (about 19 Nov 2026 to 19 Jan 2027)

**Status: revision 4, 18 November 2026 (WP-E4 Phase 3, documentation-only; pending the maintainer's review).** Revision 3 was approved on 17 November 2026 with the maintainer's targeted corrections. Canonical location: `docs/migration/travel-development-plan.md`.

Revision 4 records:
- the completion of WP E0–E3;
- the approved travel workflow (§0a);
- the rule for hosted functional simulations (DR-15);
- the approved nine-week roadmap (§3a), which supersedes the rev-3 "indicative sequencing" table (kept below for traceability).

Workstreams, work packages, dependencies and the held acceptance queue are otherwise unchanged.

**How to read this revision.**
- Text between *[Superseded (rev. 4)…]* and *[end of superseded text]* is retained revision-3 history. It is **not** an active instruction and **not** the current repository status.
- The current position is given by the "(rev. 4)" text and by the decisions DR-14 … DR-18.
- **WP-E4 (repository consolidation and travel handover) is completed by the documentation pull request that introduces revision 4.**
- **Still open:** release documentation and M4 readiness. These are plan work package **E4** (M4 groundwork: README 2.0, compatibility table, `opp_env` entry, skills, nightly job), which is a different item from WP-E4.

**This is a prioritised backlog, not a delivery commitment.** No item is promised by a date. Week labels give order only.

**Inputs:**
- `authoritative-migration-status.md` (rev. 3);
- `migration-decisions-register.md` (rev. 3);
- `remote-execution-feasibility.md`;
- the private evidence-collection record (not published).

## 0. Principles

**Remote development priorities (maintainer, 17 Nov), in this order:**
1. GitHub-based development on isolated branches.
2. Tier-0 Python regression CI.
3. Tier-1 full-stack build feasibility.
4. Tier-2 functional smoke testing.
5. Separately authorised scientific execution and acceptance.

**Access is never assumed.** **DR-12 (17 Nov): the initial remote agent has no private-repository access.** The maintainer provides reviewed documents selectively where necessary. Any future access must be configured and verified with real access controls, not instructions alone. The agent does not assume access to the private evidence repository or to any simulation environment. Each must be configured by the maintainer and verified by the agent (DR-12). No persistent personal VM runner is attached to the public repository.


1. **Parallel workstreams, dependency-driven.** There are five workstreams, A–E (§2). Week labels give priority and order, not completion dates.
2. **Two kinds of dependency** are marked on every work package:
   - **I-dep:** prevents *implementation*. The work cannot be written or CI-validated without it.
   - **A-dep:** prevents *scientific acceptance* only. The work proceeds to level 2 (CI-validated) and its acceptance is queued.
3. *[Superseded (rev. 4); not an active instruction:]* **The build environment comes first.** Tier-1 CI (the full pinned-stack build) is investigated in week 1 (WP E2), right after tier 0 (WP E1). C++ or NED work that needs it starts **only** when a build environment is verified. Until then it stays at design or prototype level, and this is stated in each package. *[end of superseded text]* Tier-1 is verified and integrated (DR-14); C++ / NED work proceeds to level 2 through tier-1.
4. **The VM is the current independent environment, not a permanent limit.** A package whose acceptance needs a simulation is queued for an independent execution environment, either the VM or one approved under `remote-execution-feasibility.md` §4. Development never waits for the VM unless an I-dep says so.
5. **Three levels** (handover §8): code complete → CI-validated → independently accepted. Only the maintainer grants the third.
6. **Evidence vs source.**
   - Accepted and failed records, evidence and fixtures are immutable.
   - Source files declared frozen by an accepted record stay frozen. Examples: the A-2 modules frozen at `fbee202`; `check_m2s72_a2v1.py` (39a6434), the A2-V1 evaluator, pinned by the A-2.1 test T-frozen-untouched.
   - Every other source file is active. It may be changed with justification, review and regression evidence that reviewed behaviour is preserved.

## 0a. Approved travel development workflow (rev. 4)

| Role | Who / what | Produces |
|---|---|---|
| Design, implementation and development testing | **Claude Code** (development agent) | Designs, code, tests; level 1 → 2 |
| Independent code and evidence review | **ChatGPT** | Review findings on designs, code, records and evidence |
| Automatic Python regressions | **GitHub tier-0** (required) | Level 2 for Python work |
| Release build, linkage and reviewed configuration checks | **GitHub tier-1**. Automatic for relevant non-draft pull requests; the label `tier1:run` overrides, including for drafts. It validates its specific reviewed configuration queries only. | Level 2 for C++ / NED / ini build work |
| Hosted functional simulations | **Individually authorised and bounded** runs (DR-15), using the frozen tier-2 harness pattern | Level-2 development smoke evidence |
| Experimental campaigns and qualifying scientific evidence | **Independent scientific executor** (feasibility §4) | Level-3 candidates |
| Approvals, integration and scientific acceptance | **Maintainer** | Merges; level 3 |

**Development CI never replaces independent scientific execution.** Hosted functional simulation capability is **not** suspended. Each run needs its own authorisation, bounds and pre-declared acceptance (as E3a and E3b-R1 had).

## 1. Integration architecture: linking M2-A, M2-B and M3

The three lines meet at the architectural seams of `revised-migration-roadmap.md` §1. Each work package below names the seam it touches. A change to a seam's contract needs a short interface note, reviewed before the code.

| Seam | M2-A (timing) | M2-B (bridge functions) | M3 (FRER) | Current state |
|---|---|---|---|---|
| **S-CFG: configuration emitter** | S7.2a generator `tools/m2s72_gen.py` (the first and only instance; audit §1.6) | The TSN AF offline compiler becomes the general emitter: streams → bearer tables, QoS rules, profiles; TAS gate lists | S-PATH bindings emit their member-stream S-CFG fields through it | Generalisation not started. **Key integration task (WP-B2).** |
| **S-META: region-tag metadata** | `TtSyncIngressTag` / `TtTimestampTag` (chunk-region tags) | The runtime bridge-delay observer reads the same timestamps for data frames | Per-member-stream latency and the recovery statistics reuse them | Implemented for gPTP; survival through GTP-U fixed upstream (#309, 1.8.1) |
| **S-CLK: clock** | The M2-S6 `TtClock` per port; the S8 model (DR-04) | TAS / Qbv gating runs on the TT port clock | `FrerRecovery` timeouts in TT time | Implemented (S6) |
| **S-OBS: observation** | Checkers read logs, signals and PCAP; no Simu5G headers | Observer statistics | Recovery statistics | Rule enforced (audit §1.6) |
| **S-PATH: transport binding** | — | Multi-endpoint data plane (one UE per DS-TT) | `IFrerTransportBinding` becomes a configuration emitter; bindings F1 / F2 now; F3 / F4 per Phase 5 | Legacy interface `src/nasctime/nodes/frer/IFrerTransportBinding.h` only |
| **S-RAD: radio include** | Per-scenario radio settings | Same | Same | Not yet a single include (roadmap §1) |

**Shared scenario.** The S7.2a network `M2S72Bridge` (N DS-TTs) is the common topology. M2-B adds TAS and the data-plane flows to it. M3 adds the replication and elimination points at the same TTs, as S7 roadmap §9 anticipates. Every new behaviour is default-off, so the S7.2a records stay byte-identical (C-2).

## 2. Workstreams

### Workstream E — Release engineering and CI (starts week 1; prerequisite for C++ work)

| WP | Objective | I-dep | A-dep | Deliverables and acceptance tests | Environment | Stop conditions | Effort |
|---|---|---|---|---|---|---|---|
| **E0** | Integration branch and document import. *[Superseded (rev. 4); not an active instruction:]* Prepared 17 Nov as a documentation-only commit; awaiting review and push by the maintainer. *[end of superseded text]* Done (see the status table below). | DR-11 approved (17 Nov) | — | `m2/continuation` from `033c3ed`. Approved documents imported into `docs/migration/` with provenance (`document-index.md`). | GitHub | Any import of a document not cleared for publication | 1 d |
| **E1** | CI tier 0: Python suites. **The first H4 task**; full specification in `h4-first-task.md` | E0 (the branch only) | — | Workflow running the handover §6 suites with a Simu5G `v1.8.1` **source** checkout. Expected counts as listed there; T-real-first-chain must PASS on the fixture. Measured locally: about 3.5 min for 11 suites on 2 cores. | GitHub-hosted runner | A count differs; PENDING reported as PASS | 1 d |
| **E2** | Tier-1 feasibility: full pinned-stack build | E0; checklist `remote-execution-feasibility.md` §2–§3 (licence, runner limits). The preserved environment description (`opp_env` 0.36.2.261110, Nix 2.34.4 flakes and lock files, in the private the private environment archive) is the reference. Publishing the flake and lock files to the public repository needs approval (DR-12; publication class). | — | Feasibility report with measured build time, cache size and runner limits. The first attempt reproduces the preserved `opp_env` / Nix environment; a from-source build is the fallback. Then, if feasible, a workflow building OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1 (unmodified) and `libnasctime_m2`, plus `opp_run -q runconfig` checks (the A2-V1 wrapper suite; generator `verify`) | GitHub-hosted runner, or another runner after approval | Licence not cleared; limits exceeded; any upstream source modified to make it build | 2–4 d |
| **E3** | Tier-2 functional smoke (short runs, not evidence) | E2 | — | *[Superseded (rev. 4); not an active instruction:]* Each NED / ini change gets one short run that must load and complete. *[end of superseded text]* Replaced by DR-15 (individually authorised runs). Labelled "functional smoke: not evidence". | Same as E2 | A smoke result used as a scientific result | 1 d |
| **E4** | M4 groundwork | E0; DR-10 | M4 acceptance: clean-machine install by the maintainer | `docs/README-2.0-draft.md`; compatibility table; `opp_env` check (B9); skill drafts `nasctime-dev-environment` and `nasctime-fingerprint-testing`; claim-scoping notes; a non-blocking nightly job against Simu5G `dev` (after E2) | GitHub | — | 3–4 d, spread over the period |

**Workstream E status (rev. 4; identities in `repository-archive-and-evidence-register.md` §3):**

| WP | Status |
|---|---|
| E0 | **Done.** `m2/continuation` created; documents imported (`db8027d`). |
| E1 | **Done.** Tier-0 integrated (PR #4). Both negative controls failed at their intended gates. |
| E2 | **Done.** Tier-1 integrated (PR #7) after E2b.1 PASS, E2b.2 FAIL, E2b.3 FAIL and E2b.3-R1 PASS. Tier-1 negative controls N-1 and N-2 failed in the offline self-tests of their hosted runs, which therefore did not reach the lock-identity gate or the C-5 SYS_LIBS gate. Both gates passed in the positive hosted tier-1 runs; their rejection behaviour was tested offline. |
| E3 | **Done, as one-time experiments:**<br>• E3a PASS (`M2S4U`: wired timing functionality);<br>• E3b PUBLICATION FAILURE (preserved);<br>• E3b-R1 PASS (`M2S5`: the downlink 5G–TSN timing path).<br>All level 2. The harness is frozen on `wp-e3/e3b-r1-publication` (DR-15).<br>**The rev-3 rule "each NED / ini change gets one short run" is replaced by DR-15:** a hosted functional run happens only when individually authorised and bounded. |
| E4 | Open: release documentation and M4 readiness (README 2.0 draft, compatibility table, `opp_env` entry B9, skills, nightly job), spread over the period. Plan package E4 is distinct from **WP-E4** (repository consolidation and handover), which is completed by the documentation PR introducing revision 4. |

### Workstream A — Remaining S7.2a tooling and protocols

| WP | Objective | I-dep | A-dep | Deliverables and tests | Stop | Effort |
|---|---|---|---|---|---|---|
| **A1** | A-2.1 integration into E0v-N (DR-07) | E1; **DR-07b** (the row design may be drafted before it) | V-N1, V-N2, V-V1 (DR-07c) on an independent environment; S5-2-D2 | New wrapper module with PU-4h, PU-4o and per-UE A2-8. A-1 PU-4 computed and reported verbatim. "First genuine occurrence" flag. Tests: synthetic N = 2 / 3 / 4 from `m2s72_harqfix21.py` against the truth; negative controls with the baseline guard; the genuine F3 fixture through the wrapper. A protocol document for V-N1 / V-N2 / V-V1 with exact commands. | Any accepted row altered; frozen modules touched | 4–6 d |
| **A2** | Full-contract diagnostic configuration (DR-07a) | E2 (the configuration must load); **DR-07a** | The diagnostic run and the non-perturbation twin | A default-off scheduler-logging mixin; a NACK-injection diagnostic configuration with declared coverage minima; a protocol | Logging changes non-log outputs (twin mismatch) | 2–3 d |
| **A3** | E0v-N batch protocol addendum | A1 | E0v core / H5 / p, E0v-N bracket | Predictions, stop rules, storage tiers (plan §4), exact commands; runner modes in new files; stub-simulator tests | — | 2–3 d |
| **A4** | E3 / E1 / E4 preparation (plan §3 G-1, G-2, G-3 remainder) | A1 | E3, E1, E4 | Append-only generator sections (regeneration and T0 byte-identical for the existing sections); per-UE S7.1 rows; per-UE no-stranding row; mutation controls | Any existing generated section changes | 5–7 d |
| **A5** | Stage 6 failure isolation (design §7, §11) | A4 | CP3 | Exact comparator, canaries CN-1…CN-4, rule AR, Block D / E configurations, CP3 protocol | — | 4–5 d |
| **A6** | S7.2a stages 7–9 tooling | A5 | Block F runs; fresh-clone reproduction | `m2s72.sh all` staging in a new runner mode; results-document template | — | 2 d |

### Workstream B — M2-B bridge functionality

| WP | Objective | I-dep | A-dep | Deliverables | Effort |
|---|---|---|---|---|---|
| **B1** | Legacy coverage evidence (the dispositions are proposed in status §3) | DR-02 (scope); none for drafting | Phase 0 evidence (C-4) for the "evidence" column | G1–G6, H1–H6, S1–S8 (README `v1.0.1`) → 1.8 scenario, M2-A stage, M2-B package, or "retired, replaced by X" (each retirement needs approval) | 2 d |
| **B2** | M2-B architecture and S-CFG generalisation | DR-02 | — | Design: TSN AF offline compiler (streams → S-CFG; PCP/VID → QFI; nascTime profiles; TSCAI); runtime observer; TAS / Qbv at the TT ports via INET `Ieee8021qLayer` gating; data-plane multi-endpoint. Interface notes for the §1 seams. | 4–5 d |
| **B3** | TSN AF offline compiler (Python) | B2 | Scenario runs that use its output | Tool plus unit tests; it reproduces the S7.2a generator's bearer and QoS sections for the existing configurations **byte for byte** (a strong regression oracle) before emitting anything new | 5–7 d |
| **B4** | `StaticBmca` validator (G6) | DR-03, including the equivalence analysis | Legacy-scalar check (Phase 0) | Offline validator over the resolved configuration (needs E2); one test per legacy check; the recorded fail-closed difference | 2–3 d |
| **B5** | TAS / Qbv at the TT ports | B2; **E2** (NED / ini must load; C++ only if needed) | Gate-observation rows on an independent environment | Default-off configuration; an oracle for gate open / close times from the configuration; negative controls | 4–6 d |
| **B6** | Runtime bridge-delay observer | B2; **E2** if C++ | Observer runs | Signals and statistics per port pair; an oracle from PCAP (S-META) | 3–4 d |
| **B7** | DR-04 analysis: the Phase 2 clock-error row vs M2-S6 / S8 | — | — | An analysis note for the decision | 1–2 d |

### Workstream C — S7.2b and S7.3

| WP | Objective | I-dep | A-dep | Deliverables | Effort |
|---|---|---|---|---|---|
| **C1** | S7.2b design (UL GM, UE-to-UE), re-based on 1.8.1 facts (#309 fixed; the UL scheduler skips HARQ-busy UEs) | DR-01 | V0-UL, U0–U3 | Design per `m2-s7-roadmap.md` §5.3: gates, oracles, controls; V0-UL first | 3 d |
| **C2** | S7.2b network, configurations, checker | C1 approved; **E2** | as C1 | NED network (default-off), generated configurations, UL and UE-to-UE checker paths; C++ only if the per-ingress-TT key is needed | 5–7 d |
| **C3** | S7.3 design (L-det / L-state; L-rec experimental, F2) | DR-01 | S0–S4 | Design per S7 roadmap §5.4; an independent state oracle from the design | 3 d |
| **C4** | S7.3 implementation | C3 approved; **E2** | as C3 | State machine, timers, window fault injectors (default-off, TEST only) | 6–8 d |

**V-3.1 / V-3.2 (standards texts)** block only the *freeze* of L-rec, not its implementation as experimental policies.

### Workstream D — M3 FRER

| WP | Objective | I-dep | A-dep | Deliverables | Effort |
|---|---|---|---|---|---|
| **D1** | M3 architecture | DR-01 | — | Design per roadmap Phase 3 and S7 roadmap §9 (TP-1…TP-3 vs RP):<br>• INET `StreamIdentifier` / `StreamSplitter` / `StreamEncoder` (802.1R) at the TTs;<br>• S-PATH bindings F1 / F2;<br>• `FrerRecovery` as an extension of INET `StreamMerger` semantics;<br>• the B4 probe;<br>• oracles for zero duplicates, surviving-path delivery and R-TAG placement;<br>• cause attribution of recovered losses.<br>**HARQ wording:** the #310 silent-deletion path is replaced on 1.8.1; discards after maxHarqRtx remain possible and must be attributed when they occur. No claim that all HARQ discards are absent. | 4–5 d |
| **D2** | INET-element feasibility probe | D1; **E2** | Probe runs | Configuration-only probe (no C++): replication and elimination around the TTs on `M2S72Bridge`; R-TAG placement check from PCAP | 3–4 d |
| **D3** | `FrerRecovery` extension and S-PATH bindings | D2; **E2** | Functional / protocol rows; experimental comparison (needs Phase 0 for the legacy F1 / F2 sweeps) | C++ subclass / extension (default-off), configuration emission through S-CFG, unit tests | 6–10 d |

## 3. Priority order (when capacity is limited)

1. *[Superseded (rev. 4); not an active instruction:]* **E0, E1, E2.** Without E2, C2, C4, B4–B6 and D2–D3 stay at design level. *[end of superseded text]* E0–E2 are done.
2. **A1**, the single blocker of every N > 1 Stage 5 result.
3. **B1, B2, D1, B7.** The designs that unblock two workstreams each.
4. **A2, A3, A4.**
5. **B3**, the S-CFG generalisation that M3 needs.
6. **C1 / C3**, then **C2 / C4**.
7. **D2 / D3**, **B4–B6**, **A5 / A6**.
8. **E4**, throughout.

**Indicative sequencing over eight weeks (an order, not a schedule). Rev. 3, superseded by §3a:**

| Weeks | Work packages |
|---|---|
| 1 | E0–E2, B1, B7, DR-04 analysis start |
| 2–3 | A1, B2, D1 |
| 3–4 | A2–A3, C1, C3, B3 |
| 4–6 | A4, C2, D2, B4 |
| 6–8 | A5, C4, D3, B5, B6, E4 |

## 3a. Approved nine-week roadmap (rev. 4; an order, not a schedule)

**Priority:**
1. **A1** (A-2.1 integration into E0v-N), the single blocker of every N > 1 Stage 5 result.
2. The remaining Stage 5 generator and protocol work.
3. The M2-B bridge architecture and the TSN AF compiler.
4. The Stage 6 comparator.
5. The M3 FRER architecture.
6. S7.2b and S7.3 design and implementation preparation.

**Scope and claims.**
- **S7.2a remains partial.** No release readiness and no complete M2-S5 campaign acceptance is claimed.
- Remote work reaches level 2 at most. Scientific acceptance stays with the independent executor and the maintainer (§4).

| Week | Remote development (Claude Code; ChatGPT review; tier-0 / tier-1; level 2) | Requires independent execution, VM access or the maintainer |
|---|---|---|
| 1 | Consolidation documentation (WP-E4). **A1 design note:** wrapper rows PU-4h, PU-4o and per-UE A2-8, the first-genuine-occurrence flag (DR-07b / d), the module boundary, the test plan. **B1** coverage table draft. | Review and merge of the documentation; job-log exports and internal raw-manifest verification of the preserved archives |
| 2–3 | **A1 implementation** (new module; frozen sources untouched): synthetic N = 2 / 3 / 4 tests from `m2s72_harqfix21.py`, negative controls with the baseline guard, the genuine F3 fixture through the wrapper (tier-0). **A1 validation protocol** for V-N1 / V-N2 / V-V1 with exact commands. **B7** clock-error note. **D1** M3 architecture. | DR-07c validations V-N1 / V-N2 / V-V1 (read-only, on the private evidence; DR-12, DR-13), then the S5-2-D2 decision |
| 3–5 | **A4** generator sections for E3 / E1 / E4 (append-only; existing sections regenerate byte-identically). **A3** E0v-N batch protocol addendum. **A2** full-contract diagnostic configuration and protocol. **B2** M2-B architecture with seam interface notes. | A2 non-perturbation twin and full-contract diagnostic; E0v core / H5 / p; the E0v-N bracket |
| 5–7 | **B3** TSN AF offline compiler: it must reproduce the generator's bearer and QoS sections byte for byte before emitting anything new. **A5** Stage 6 comparator, canaries CN-1…CN-4, rule AR. **C1** S7.2b and **C3** S7.3 designs. | Design reviews; E3, E1 + E4 when A4 is accepted |
| 7–9 | Implementation preparation for **C2 / C4** (S7.2b network and configurations; S7.3 state machine) and the **D2 / D3** skeletons (S-PATH emission through S-CFG). Default-off, release build and linkage validated by tier-1. New configurations get reviewed queries, or an individually authorised hosted functional run (DR-15). **E4** README 2.0 draft. | CP3 (Stage 6), S7.2b / S7.3 / M3 rows; Phase 0 and legacy comparisons (VM); M4 clean-machine install |

**Never in this window:**
- a development-agent run (tier-0 / tier-1 CI or an authorised hosted functional simulation) presented as independent scientific evidence;
- a Stage 5, M2-B or M3 campaign run by the development agent;
- a release.

**Independent scientific execution during travel is permitted.** An authorised independent scientific executor may undertake qualifying scientific experiments during the travel period (the right-hand column above). The conditions are those already established:
- a pre-declared, approved protocol;
- the approved budget (feasibility C-1);
- the conditions of `remote-execution-feasibility.md` §4;
- the maintainer's acceptance.

## 4. Held acceptance queue (order of independent execution)

The order is corrected so that evidence acquisition precedes the comparisons that need it.

| # | Item | Needs |
|---|---|---|
| ~~1~~ | **Completed (H1, H2), 17 Nov.** N1, N2 and A2-V1 evidence in the private evidence archives; the environment, F3, legacy-provenance and VM-compatibility archives (private). No further VM collection is planned before departure. | — |
| 2 | Review of the collected VM NED / INI corrections (the private VM-compatibility archive). Review by the maintainer, or by the agent from reviewed extracts the maintainer provides (DR-12: no private access). Integration is reviewed default-off commits; G0 identity on 6.4.0 is a held run. | collected archive; DR-12 |
| 3 | DR-07c validations V-N1, V-N2, V-V1 (read-only), then the S5-2-D2 decision. Inputs are in the private release, which is not accessible to the development agent. The run needs an approved independent environment with path resolution per DR-13. | A1; DR-12; DR-13 |
| 4 | A2 non-perturbation twin and full-contract diagnostic | A2 |
| 5 | E0v core / H5 / p; then the E0v-N bracket and f_E1 | A3 |
| 6 | E3; then E1 + E4 | A4 |
| 7 | CP3 (Stage 6); Block F; S7.2a fresh-clone closure | A5, A6 |
| 8 | **Phase 0 evidence acquisition.**<br>Done (H2): the legacy workspace identity, the working-tree patch, the 79-file inventory, the historical records.<br>Remaining: result-to-paper mapping and per-paper source identities (partly from the private inventory); preservation of the VM-only datasets (DR-06b). | private inventory; the maintainer on the VM for the datasets |
| 9 | **Legacy mapping evidence**: the B1 table's evidence column; the legacy scalar check for B4 | 8 |
| 10 | M2-B acceptance rows (TAS gates, observer) and **legacy-vs-1.8 comparison** | 8, 9, B5, B6 |
| 11 | S7.2b (V0-UL first), S7.3 | C2, C4 |
| 12 | M3 functional and protocol rows; then **M3 legacy F1 / F2 comparison** | D3; 8, 9 for the comparison |
| 13 | Phase 0 bit-identical regeneration (Phase 0 closure) | 8 |
| 14 | E2 re-declared (plan §2.6) | 6 |

Items 3–7 and 11–12 can run on any independent environment approved under `remote-execution-feasibility.md` §4. Items 8–9 and 13 need the legacy results machine.

**Rev. 4 note.** E3a and E3b-R1 are not acceptance-queue items. They are level-2 development smoke evidence and close no queue item.

## 5. Out of scope

- Upstream changes.
- Merges into `master`.
- Tags.
- Edits to accepted or failed records.
- Reopening S1 without a substantive new reason.
- S7.4b.
- Phase 5 items (no trigger met).
- Any simulation executed by the development agent and presented as evidence.
