# nascTime 2.0 — Remaining-work roadmap

**Status: proposal, 24 November 2026 (step 160, documentation only; for independent review).** It is not a delivery commitment and gives no dates. Order is given by dependencies only.

**Baseline:** `m2/continuation` at `3b2c2941ef297cb20051798fd1ad3ed8dea69c20`.

**Companion record:** `docs/migration/authoritative-migration-status.md` revision 5, §9. That record holds the per-milestone reconciliation and the status vocabulary (CLOSED, IMPLEMENTED, PARTIAL, NOT STARTED, DEFERRED, BLOCKED).

**Relation to the travel plan:**
- The work-package definitions of `travel-development-plan.md` §2 (A1–A6, B1–B7, C1–C4, D1–D3, E0–E4) are **retained with their original numbers and scope**.
- This document adds labels only for items that have no package in the plan (V-x, P-x, BX-x, CI-x). It re-orders nothing that the maintainer has approved.
- If approved, its sequence (§3) would replace the order of plan §3a. Plan §4, the held acceptance queue, is refined in §4 below.

**Fixed rules (unchanged):**
- A merged pull request is level 2 at most. Scientific acceptance (level 3) needs an independent executor, a pre-declared protocol and the maintainer's acceptance.
- Development CI and development-agent runs are never independent evidence.
- Frozen and accepted records, fixtures, expectation files, the FGO registry and the historical verdicts are never edited. That covers A2-V1 NOT ACCEPTED and the A-1 PU-4 FAIL.
- No upstream modification. No merge into `master`. No tags by the agent.

---

## 1. Milestone status matrix

| Milestone | Status (24 Nov) | Required for 2.0 | Blocking item |
|---|---|---|---|
| Phase 0 | PARTIAL | Mapping: yes (DR-06). Closure: not a gate. | DR-06b dataset preservation (VM); B8 |
| M1 | CLOSED | yes | — |
| M2-A S0–S6, S7.1 | CLOSED (S7.1 for its 1.8.0 scope) | yes | — |
| M2-A S7.2a | PARTIAL: stages 1–4 CLOSED, 5 PARTIAL, 6–9 NOT STARTED | yes | V-N1 / V-N2 / V-V1, S5-2-D2 |
| M2-A S7.2b, S7.3 | NOT STARTED | yes | design (C1, C3) |
| M2-A S7.4a | NOT STARTED | no (optional, F1) | — |
| M2-A S7.4b | DEFERRED (D7) | no | — |
| M2-A S8 | NOT STARTED | undecided (Q-1) | B7 |
| M2-B B1, B4, B7 | NOT STARTED (B4 condition (1) BLOCKED) | yes | B4: Phase 0 datasets |
| M2-B B2, B3 | PARTIAL | yes | — |
| M2-B B5 | IMPLEMENTED (level 2, local evidence) | yes | hosted-evidence decision (Q-3); independent protocol |
| M2-B B6 | PARTIAL (offline statistics and passive per-frame observation at level 2; runtime `bridgeResidence` signal and per-port-pair statistics missing) | yes | B6-R; then as B5 |
| M2-B DS-TT VLAN translation | NOT STARTED | yes | — |
| M2-B multi-endpoint data plane | PARTIAL | yes | S7.2b (UL gPTP) for the S8 scenario |
| M2-B legacy comparison; fingerprint baseline | BLOCKED | yes | Phase 0 (DR-06); B8 |
| M3 | NOT STARTED | yes | D1 |
| M4 | NOT STARTED | — | M2, M3 |
| Phase 5 | DEFERRED | no | upstream triggers |
| Phase 6 | ongoing | — | — |

---

## 2. Tracks

The tracks run in parallel. Independent validation (track V) never waits for development, and development never waits for track V unless an I-dep below says so.

| Track | Owner | Content |
|---|---|---|
| **V**: independent validation | Maintainer and the designated executor | WP-A1 validations, Stage 5 batches, every acceptance row |
| **P**: Phase 0 | Maintainer (VM access), with documentation by the agent from reviewed extracts | Mapping, dataset preservation, reproduction |
| **A**: S7.2a tooling | Development agent | A2–A6 |
| **B**: M2-B | Development agent | B1–B7 and the DR-02 items without a number (BX-x) |
| **C**: S7.2b / S7.3 | Development agent | C1–C4 |
| **D**: M3 | Development agent | D1–D3 |
| **E**: release and CI | Development agent; CI changes reviewed and approved by the maintainer | E4, CI-x |

**Dependency kinds** (as in the travel plan): an **I-dep** prevents implementation; an **A-dep** prevents scientific acceptance only.

---

## 3. Work-package sequence

### 3.1 Track V: independent validation, highest priority

| WP | Inputs | Deliverables | Acceptance | Dependencies |
|---|---|---|---|---|
| **V-0** Gate A for session Q | Runbook rev. 4 §1–§3; `C` = `f3f68be`; procedure commit `D` (the tested revision is `544c093`) | Executor designated (X-1); the maintainer's public key out of band; signed `gate-a.txt` | The statement verifies with `ssh-keygen -Y verify` (principal `wpa1-maintainer`, namespace `wpa1-approval`) | Maintainer only |
| **V-1** Session Q | V-0; the three release archives and `SHA256SUMS`; the pinned image | DR-13 validation record (§6); G0-RO record against D-2 (§7) | Maintainer signs `a4-dr13.txt` and `a5-g0ro.txt` | V-0 |
| **V-2** Session V: V-N1, V-N2, V-V1 | V-1 approved; the gate-B checks of `stage2-p0.sh` | The three validation records (runbook stages 2–6) | VG-0 … VG-3, which give **AC-5** | V-1 |
| **V-3** S5-2-D2 decision | V-2 accepted (V-N1, V-N2) | Decision record (DR-07c); optionally a reviewed registry change citing the accepted record (design §8.5) | **AC-6** | V-2 |
| **V-4** DR-08 smoke closure records (N = 1, N = 2) | Private verified evidence | Two closure records, labelled as reconstructed from verified evidence | Maintainer approval | Can run in parallel with V-0 … V-3 |
| **V-5** Stage 5 batches: E0v core / H5 / p, then the E0v-N bracket and f_E1 | A3 protocol; V-3 | Batch records under the tiered evidence rules (plan §4) | Pre-declared rows; maintainer acceptance | A3 (I), V-3 (A) |
| **V-6** A2 non-perturbation twin and full-contract diagnostic | A2 | Records | Twin identical in non-log outputs; declared coverage minima | A2 |
| **V-7** E3, then E1 + E4 | A4 | Records | Pre-declared rows | A4; V-5 for E1 |
| **V-8** CP3 (Stage 6), Block F, fresh-clone closure | A5, A6 | S7.2a stage 6–9 records | Design §7, §11 | A5, A6 |
| **V-9** M2-B acceptance rows (gates observed, observer) | B5 / B6 protocol (BX-P) | Records | The protocol row "gates observed opening and closing"; the observer rows | BX-P; B6-R; Q-3 resolved |
| **V-10** S7.2b, S7.3 rows | C2, C4 | V0-UL first, U0–U3; S0–S4 | Roadmap §5.3, §5.4 | C2, C4 |
| **V-11** M3 functional and protocol rows; then the legacy F1 / F2 comparison | D3; P-1 | Records | §4 of the status | D3; P-1 for the comparison |

### 3.2 Track P: Phase 0

| WP | Inputs | Deliverables | Acceptance | Dependencies |
|---|---|---|---|---|
| **P-1** Result-to-paper mapping | The private 79-file inventory, as reviewed extracts (DR-12) | A mapping document (published after content review) | Every published or submitted result set mapped to a source identity and data | Maintainer extracts |
| **P-2** Dataset preservation (DR-06b) | VM access | Checksum-manifested private archives of the multi-endpoint, FRER, bridge and NW-TT results | Integrity verified | VM access (maintainer) |
| **P-3** Bit-identical regeneration | P-1, P-2; the legacy stack | Reproduction script and record | Roadmap Phase 0 acceptance | P-1, P-2; B8 |
| **P-4** Locate the fingerprint suite (B8) | Legacy provenance | The suite, or a recorded "not recoverable" decision | Maintainer decision | — |

### 3.3 Track A: S7.2a tooling

| WP | Inputs | Deliverables | Acceptance (level 2) | Dependencies |
|---|---|---|---|---|
| **A2** Full-contract diagnostic configuration (DR-07a) | Plan §2; DR-07a | Default-off scheduler-logging mixin; a NACK-injection diagnostic configuration with declared coverage minima; a protocol | Loads under a tier-1 query or an authorised run; accepted outputs unchanged | I: none beyond tier-1. A: V-6 |
| **A3** E0v-N batch protocol addendum. **Status (step 161): IMPLEMENTED at level 2, pending review**: protocol `simulations/m2/results/M2-S7.2a-e0vn-protocol.md`, runner `m2s72s5n.sh`, record `M2-S7.2a-a3-implementation.md`. The bracket stays BLOCKED on V-2, V-3 and the registry admissions | WP-A1 (level 2); plan §4 | Predictions, stop rules, storage tiers, exact commands; runner modes in new files; stub-simulator tests | Tier-0; frozen files untouched | I: A1 (met). A: V-3 |
| **A4** E3 / E1 / E4 generator sections (G-1, G-2, G-3 remainder) | Generator `tools/m2s72_gen.py` | Append-only sections; per-UE S7.1 rows; the per-UE no-stranding row; mutation controls | Existing sections regenerate byte-identically; T0 byte-identical | A1 |
| **A5** Stage 6 failure isolation | A4 | Exact comparator, canaries CN-1 … CN-4, rule AR, Block D / E configurations, CP3 protocol | Canary self-tests | A4 |
| **A6** Stages 7–9 tooling | A5 | `m2s72.sh all` staging; results-document template | Dry runs | A5 |

### 3.4 Track B: M2-B

| WP | Inputs | Deliverables | Acceptance (level 2) | Dependencies |
|---|---|---|---|---|
| **B1** Coverage table | DR-02 dispositions (status §3); M2B-1 … M2B-5; WP-A1 | G1–G6, H1–H6, S1–S8, F1–F4 → scenario / stage / package / "retired, replaced by X", with an evidence column | Every item mapped; every retirement cites its approval and the coverage of its replacement behaviour | Evidence column: P-1 |
| **B2** Architecture consolidation | `m2b-scfg-interface.md`; M2B-2 §1; travel plan §1 seams | One architecture note: runtime observer; multi-endpoint data plane; DS-TT VLAN translation (BX-VT); TSCAI; `GptpSideband` baseline (BX-SB); S-PATH emission for M3; the hosted-evidence path | Reviewed before any further B code | DR-02 |
| **B3** Compiler completion | B2 | TSCAI; VID classification (decision in B2); per-UE DRB templates; `.ini` section integration; traffic applications | The byte-identical oracle stays green for every existing configuration | B2 |
| **B4** `StaticBmca` validator | DR-03 | Conditions (2) and (3); then the offline validator over the resolved configuration, with one test per legacy check | The recorded fail-closed difference | Condition (1): P-2 (A-dep) |
| **B5 / B6 follow-up** | M2B-2 … M2B-5 | Hosted evidence per Q-3; the acceptance protocol **BX-P** for the gate and observer rows | Protocol reviewed before any run | Q-3 |
| **B6-R** Runtime B6 signal and statistics (the outstanding part of the original B6 contract) | M2B-2 §5 (B6 item 2); M2B-4 observer | A default-off, passive runtime signal `bridgeResidence` (R per frame) at the egress processor, with declared `@statistic` per port pair / PCP | Equal to `bridge_delay.py` on the same run (oracle); outputs of existing configurations unchanged; level 2 | B2 (observer section); tier-1 build
| **B7** DR-04 clock-error analysis | M2-S6; status §3.5 | Analysis note | Maintainer decision on Q-1 | — |
| **BX-VT** DS-TT VLAN translation (DR-02) on the Ethernet PDU-session architecture | B2. Legacy PR #2 (`1501a50`) is historical reference only: it implements legacy PCP-to-IPv4-DSCP translation and an uplink reflective-QoS demo, not this function | Default-off translation function at the DS-TT; oracle; negative controls | Accepted configurations unchanged | B2 |
| **BX-ME** Multi-endpoint S8 scenario (bidirectional, N = 3) | B3; C2 (UL gPTP) | Scenario and checker | Level-2 tests | B3, C2 |
| **BX-SB** `GptpSideband` labelled baseline | B2 | Default-off baseline, labelled idealised | Level-2 tests | B2 |
| **BX-H5** H5 equivalence analysis | The legacy `LayeredEthernetInterface` | Analysis note for the pending retirement | Maintainer decision | — |

### 3.5 Track C: S7.2b and S7.3

| WP | Inputs | Deliverables | Acceptance | Dependencies |
|---|---|---|---|---|
| **C1** S7.2b design | S7 roadmap §5.3; 1.8.1 facts (#309 fixed; UL scheduler skips HARQ-busy UEs) | Design: gates, oracles, controls; V0-UL first | Design review | DR-01 |
| **C2** S7.2b implementation | C1 approved | Default-off network, generated configurations, UL and UE-to-UE checker paths | Tier-0 / tier-1; accepted configurations unchanged | C1 |
| **C3** S7.3 design | S7 roadmap §5.4 | Design with an independent state oracle | Design review | DR-01 |
| **C4** S7.3 implementation | C3 approved | State machine, timers, window fault injectors (default-off, test only) | As C2 | C3 |

### 3.6 Track D: M3 FRER (prepared without bypassing dependencies)

| WP | Inputs | Deliverables | Acceptance | Dependencies |
|---|---|---|---|---|
| **D1** M3 architecture | Status §4; S7 roadmap §9 (TP-1 … TP-3 vs RP); legacy PR #3 as reference only | Design: INET replication and elimination at the TTs; S-PATH bindings F1 / F2; `FrerRecovery` as an INET merge extension; oracles (zero duplicates, surviving-path delivery, R-TAG placement); cause attribution; the HARQ wording of status §4 | Design review | DR-01 |
| **D2** INET-element feasibility probe | D1 | Configuration-only probe on `M2S72Bridge`; R-TAG placement from PCAP | Level 2 | D1; tier-1 query or an authorised run |
| **D3** `FrerRecovery` and S-PATH bindings | D2; B3 (S-PATH emission) | Default-off C++; configuration emission through S-CFG; unit tests | Level 2 | D2, B3 |

### 3.7 Track E: release and CI

| WP | Inputs | Deliverables | Acceptance | Dependencies |
|---|---|---|---|---|
| **E4** M4 groundwork | DR-10; DR-18 | README 2.0 draft with the boundary statement; compatibility table; `opp_env` check (B9); skill drafts; claim-scoping notes; nightly non-blocking `simu5g@dev` job | Review; the dev job has run at least once | — |
| **CI-1** M2B-5 compiler suite into tier-0 (Q-4) | `test_tsnaf_compile_epoch.py` | A separately reviewed tier-0 step with its declared line | Tier-0 green; no other gate changed | Maintainer approval |
| **CI-2** Tier-1 configuration-query extension (Q-3) | M2B-3 §8 proposal | A reviewed change to the audited query set | Tier-1 C-1 … C-15 semantics preserved or re-approved | Maintainer approval |

### 3.8 Order when capacity is limited

1. **V-0 → V-1 → V-2 → V-3**: maintainer and executor. This runs in parallel with everything below.
2. **A3, A2**: so that V-5 and V-6 can start as soon as V-3 is decided.
3. **B1, B7, BX-H5**: documentation that unblocks decisions Q-1 and H5, and the M2 functional row.
4. **A4**, then **A5 → A6**.
5. **B2** consolidation, then **B3** completion, **B6-R**, **BX-VT**, **BX-SB**.
6. **D1**, then **D2**. D3 waits for B3.
7. **C1, C3**, then **C2, C4**, then **BX-ME**.
8. **B4** conditions (2) and (3) at any point; the validator after them.
9. **E4** throughout. **CI-1** and **CI-2** whenever the maintainer approves them.

---

## 4. Outstanding independent validation (held queue, refined from plan §4)

| # | Item | Needs | Status |
|---|---|---|---|
| 1 | V-0 / V-1: gate A and session Q (DR-13-V, G0-RO) | Maintainer, executor, archives | **Next** |
| 2 | V-2 / V-3: V-N1, V-N2, V-V1; S5-2-D2 (AC-5, AC-6) | 1 | waiting |
| 3 | V-4: DR-08 smoke closure records | Private evidence | open |
| 4 | Review of the collected VM NED / INI corrections | Reviewed extracts (DR-12) | open |
| 5 | V-6: A2 twin and full-contract diagnostic | A2 | waiting on A2 |
| 6 | V-5: E0v core / H5 / p; the E0v-N bracket and f_E1 | A3; 2 | waiting |
| 7 | V-7: E3; E1 + E4 | A4 | waiting |
| 8 | V-8: CP3, Block F, S7.2a fresh-clone closure | A5, A6 | waiting |
| 9 | P-1, P-2: Phase 0 evidence acquisition and mapping | VM; reviewed extracts | open |
| 10 | V-9: M2-B rows (gates, observer); then the legacy-vs-1.8 comparison | BX-P; Q-3; 9 | waiting |
| 11 | V-10: S7.2b (V0-UL first), S7.3 | C2, C4 | waiting |
| 12 | V-11: M3 rows; then the legacy F1 / F2 comparison | D3; 9 | waiting |
| 13 | P-3: Phase 0 bit-identical regeneration | 9; B8 | waiting |
| 14 | E2 (load sweep) re-declared (plan §2.6) | 7 | waiting |
| 15 | M4 clean-machine install | E4; M2; M3 | waiting |

---

## 5. Known blockers and risks

| ID | Blocker or risk | Effect | Mitigation |
|---|---|---|---|
| R-1 | The independent executor and gate A are not yet in place | Every N > 1 Stage 5 result is blocked | V-0 first; session Q performs no WP-A1 evaluation, so it can start as soon as gate A is signed |
| R-2 | The validation procedure depends on `C` and `D` staying reachable | `h1-setup.sh` stops if they are missing | Both are ancestors of `m2/continuation`. Never rewrite its history. |
| R-3 | The VM-only legacy datasets (DR-06b) | Risk of loss; blocks the legacy comparisons, B4 condition (1) and Phase 0 | P-2 when VM access resumes |
| R-4 | B8: the fingerprint suite is not located | The M2 regression row and the M4 skill | P-4 |
| R-5 | The M2B functional evidence is local only, and B6 lacks its runtime signal and statistics | B5 / B6 acceptance cannot use it | B6-R; Q-3 (CI-2 or a DR-15 run); then BX-P and V-9 |
| R-6 | Standards texts not read (V-register) | The freeze of S7.3 L-rec, S7.4a and S8 | Not blocking implementation; schedule the reading before any freeze |
| R-7 | The S7.2a evidence volume (about 290–470 GB cumulative; plan §4.3 estimate) | Executor budget | Tiered evidence rules (plan §4); the budget is approved by the maintainer |
| R-8 | The A-2.1 full contract is INCOMPLETE (A2-4c not evaluated) | Limits the claims; never broadened | A2 / V-6 |
| R-9 | The hosted evidence archives expire on GitHub (24–25 Nov); job-log exports are pending | Evidence preservation | Maintainer (register §4.1; Q-7) |
| R-10 | Simulator-based M2B suites are not in any hosted CI | Silent regression of the TAS / residence / epoch paths | CI-1 for the Python part; CI-2 or authorised runs for the rest |
| R-11 | Scope growth from items without a work package (VLAN translation, sideband, H5, the S8 scenario) | They are easily dropped silently | Listed explicitly as BX-x |

---

## 6. Release eligibility criteria for nascTime 2.0

The criteria are taken from the sources quoted in the status record. **Undecided items are marked and are not resolved here.**

**Mandatory (from the sources):**
1. **Stack:** OMNeT++ 6.5.0 / INET 4.7.0 / unmodified Simu5G 1.8.1 (DR-01).
2. **M2-A minimum gPTP scope** (S7 roadmap §2.1): S7.1, S7.2a, S7.2b, S7.3 (detection and state; recovery experimental), each **CLOSED** with independent evidence. S7.2a closure includes stages 5–9 at N = 1, 2, 4, 8 (DR-05).
3. **M2-B** (DR-02): B1 coverage table complete, with every retirement evidenced; G5 and G6 covered (B3, B4); TAS and the observer accepted (B5; B6 including its runtime signal and per-port-pair statistics); DS-TT VLAN translation on the Ethernet PDU-session architecture; the multi-endpoint data plane; the legacy-vs-1.8 comparison; the fingerprint baseline. **M2 closes only when M2-A and M2-B close.**
4. **M3 F1 / F2** CLOSED with the functional, protocol and experimental rows (§4 of the status). Results over TP-1 … TP-3 are labelled "FRER over existing transport paths".
5. **M4 acceptance** (status §5): clean-machine install and run of every example; the CI dev job has run at least once; the boundary statement reviewed; claim-scoping notes; release line per DR-18.
6. **Claims:** no claim beyond the accepted evidence. In particular: no "3GPP-faithful carriage" before S8; A2-V1 NOT ACCEPTED and the A-1 PU-4 FAIL stated as such; no IEEE 802.1Qbv / 802.1AS conformance claim without evidence.

**Not required:** S7.4a (optional, F1); S7.4b (D7); Phase 5 items.

**Undecided (maintainer):**
- S8 (Q-1);
- whether Phase 0 bit-identical regeneration gates the release (Q-2).

**Minimum credible release.** If the maintainer were to narrow the release scope, that would require a recorded decision changing DR-02 or the S7 roadmap minimum scope. **No such decision exists, and this roadmap does not propose one.**

---

## 7. Recommended next three development steps

These are development-agent steps at level 2. They proceed in parallel with V-0 → V-3, which only the maintainer and the executor can perform.

1. **A3 and A2: Stage 5 protocol and diagnostic preparation.** The E0v-N batch protocol addendum, with predictions, stop rules, storage tiers, exact commands and new runner modes with stub tests. Then the default-off full-contract diagnostic configuration and its protocol. This lets V-5 and V-6 start as soon as S5-2-D2 is decided. Frozen files and accepted configurations stay untouched.
2. **B1 and B7: coverage table and clock-error analysis**, with the BX-H5 analysis note. Documentation only. It maps every legacy capability, including M2B-1 … M2B-5 and WP-A1, and gives the maintainer what is needed for Q-1 (S8) and the pending H5 retirement.
3. **A4: E3 / E1 / E4 generator sections.** Append-only, with the existing sections and T0 regenerating byte-identically. This unblocks A5 / A6 and the Stage 5 batches after E0v.

**Maintainer actions that unblock the most:**
- V-0, gate A for session Q;
- decisions Q-3 and Q-4 on the hosted evidence for the M2B configurations;
- P-2, dataset preservation.
