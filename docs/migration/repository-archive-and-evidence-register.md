# nascTime 2.0 — repository archive and hosted evidence register

**Status: revision 1, 18 November 2026 (WP-E4 Phase 3).** Canonical location: `docs/migration/repository-archive-and-evidence-register.md`. This register records:
- the repository consolidation of WP-E4 (decision DR-17);
- the hosted CI and experiment evidence of WP-E1 … WP-E3.

It changes no code, configuration, test, fixture, evidence or historical record.

**Sources.**
- The branch, tag and pull-request state was read from GitHub on 18 November 2026.
- The run, job and artifact identities come from the GitHub Actions records of each run.
- The results come from the verdict tables in the job logs.
- **Preservation of the evidence archives (§4) is the maintainer's statement.** The development agent has no access to the private evidence release (DR-12), and has not accessed or verified it.

## 1. Permanent branches (DR-17)

| Branch | Head | Role |
|---|---|---|
| `m2/continuation` | `290babba3d12942344a2153f9ea5ea54287df366` | **Integration branch** of the 2.0 line (DR-11). Every new work package starts from it. |
| `master` | `9e8bc83dfdfaffd918eb304bda6b8ecb98ff0684` | **Frozen legacy provenance** (1.x line, tag `v1.0.1`). Default branch. No common history with `m2/continuation` (DR-18). Target of the open external PRs #2 and #3. |
| `m1/ethernet-bridge` | `fbe41a9e9ba1befc0d68b9fd559be52b024c1ca9` | **Frozen provenance.** M1, CLOSED 2026-10-13. Holds 28 commits that are on no other branch, including the accepted M1 stage commits S0 `9138d83`, S1 `0226e56`, S2 `db81377`, S3 `ea05c1a`, S4 `ef500cd` and S5 `b7918ff`. |
| `wp-e3/e3b-r1-publication` | `edf3329ddf2350650fd0957ddd5a965fe3ddbb56` | **Frozen experimental branch.** The tier-2 harness (`ci/tier2/`) accepted with E3b-R1 (DR-15). It is not integrated into `m2/continuation`. |

**The 2.0 line and `master`.**
- The only root of `m2/continuation` is `14d5e0f`, a single-commit snapshot of 2026-11-03.
- Its tree equals the tree of `m1/ethernet-bridge` plus 468 added files: no file is modified or removed.
- M1 and the legacy content are therefore integrated **as a snapshot**. Their history is preserved only by `master`, `m1/ethernet-bridge` and the tags below.

## 2. Tags (30)

All 30 tags are annotated.

### 2.1 Release tags (unchanged)

| Tag | Tag object | Commit |
|---|---|---|
| `v1.0` | `b0b3f6b0d86550963776651b013d5978edfa3aab` | `f03e38da4d209a86e00f8d1cb79220163ae9aff9` |
| `v1.0.1` | `c2202fb051b05088b2f68a6cba24efedb5a9ff83` | `9e8bc83dfdfaffd918eb304bda6b8ecb98ff0684` |

Phase 0 tags (`legacy-v1.0`, `legacy/1.x`) remain **deferred**.

### 2.2 Archive tags (28)

- The maintainer pushed the 28 tags on 18 November 2026.
- Independent verification confirmed that all are annotated and that each dereferences to the commit below.
- Each annotation records the original branch, the full SHA, the purpose, the outcome, the PR / run / artifact identities and the reason for archival.

**How to resolve a historical branch name.**
- **Historical records are not rewritten.** Accepted and failed records outside `docs/migration/` keep their original branch names.
- **Resolving a name.** Use this table to find the tag that now preserves a deleted branch's head. For example, `git show archive/m2/s72a-a2-frozen` or `git log archive/m1/ethernet-bridge-closed`.
- **Full SHAs.** Commit SHAs cited in records remain valid: every deleted branch head is reachable from its tag.

| Former branch (deleted 18 Nov 2026) | Archive tag | Commit | Outcome |
|---|---|---|---|
| `v1.5.0-migration` | `archive/legacy/v1.5.0-migration` | `91ad6432dfe6a3c14e55a7001bb49d3361b4151f` | Legacy, superseded (contained in `master`) |
| `m2/architecture` | `archive/m2/architecture-snapshot-1.8.0` | `14d5e0f05181b76e8c374c225e373b5d8834e938` | Accepted 1.8.0 snapshot; root of the 2.0 line |
| `m2/simu5g-1.8.1` | `archive/m2/simu5g-1.8.1-r181-accepted` | `2586bce106bf021284191f6907a599a92fe77d83` | R181 / R181b / R181c accepted |
| `m2/s72a-stage5` | `archive/m2/s72a-stage5-s5-1` | `86d7599a95f136a139a00bfd139cabc369b3a954` | S5-1 implemented and reviewed |
| `m2/s72a-s5-2` | `archive/m2/s72a-s5-2` | `decf848e9e83cecc7fae39cf84b119c13ed187be` | S5-2 implemented; S5-2-D2 open |
| `m2/s72a-g0` | `archive/m2/s72a-g0-closed` | `04657b41ad9e3b53dc026c454a822d46cfc1bbdd` | G0 record rev. 3 CLOSED |
| `m2/s72a-s5-smoke` | `archive/m2/s72a-s5-smoke-n1-prep` | `bc77a6f8a103102d751d4110c4623e002f077a3c` | N = 1 smoke preparation (smoke accepted 16 Nov) |
| `m2/s72a-s5-n2` | `archive/m2/s72a-s5-n2-prep` | `06fba26f57088ffe862c02450c45cbc5aef1d693` | N = 2 smoke preparation ("VALIDATED WITH A-1 LIMITATION") |
| `m2/s72a-a2-design` | `archive/m2/s72a-a2-design` | `07b09b9999c7bbb92a951bb9f51cf509298f726a` | Design review |
| `m2/s72a-a2` | `archive/m2/s72a-a2-frozen` | `fbee2028b9c6ba5a992c0f14f85ef3729e2db107` | A-2, frozen (ACK-only validated) |
| `m2/s72a-a2d2` | `archive/m2/s72a-a2d2-a2v1-not-accepted` | `612f353a61ca91763917bed2c57d9397e9303c83` | **Failed attempt:** A2-V1 NOT ACCEPTED, permanently |
| `m2/s72a-a21` | `archive/m2/s72a-a21-closed` | `115012f1548e6816befd5124a21a08fe182149ff` | F3 CLOSED ACCEPTED; A2-V1-S1 CLOSED ACCEPTED under F1-d(i); full contract INCOMPLETE |
| `m2/s72a-a21-fixture` | `archive/m2/s72a-a21-fixture-baseline` | `033c3ed3fbc5b6ee21271ce24c62084283d8e79b` | Approved continuation baseline (DR-11) |
| `plan/m2-s7.2a-stage5` | `archive/plan/m2-s7.2a-stage5-rev1.1` | `57fa0c5684fde9d47d80a1119b7ef7364f71ea14` | Plan rev. 1 → 1.1. The file is identical in `m2/continuation`; its revision history is preserved by the tag. |
| `ci/tier0-python` | `archive/ci/tier0-python-pr4` | `aa5693879957be9be198ad208c907caf257a8a54` | Tier-0 accepted; PR #4 merged |
| `ci/tier1-full-stack` | `archive/ci/tier1-full-stack-pr7` | `46e95bacc3ceaae9ec163aa0676f03c834f3ff50` | Tier-1 accepted; PR #7 merged |
| `ci/nc-h4-fixture` | `archive/nc/h4-3-fixture-byte-expected-fail` | `61871909cd9f7b69b699636e6a418bfce87259c9` | **Negative control**, failed at its intended gate (§3.1) |
| `ci/nc-h4-simu5g` | `archive/nc/h4-4-simu5g-commit-expected-fail` | `21350bb1919cd08b07c6e517ec3c3a66293c779c` | **Negative control**, failed at its intended gate (§3.1) |
| `ci/nc-tier1-lock` | `archive/nc/t1-n1-lock-expected-fail` | `c2ddebd9d5c4f7f983b8428379b7b75c0b6ee75c` | **Negative control**, failed in the offline self-tests; intended hosted gate **not exercised** (§3.2) |
| `ci/nc-tier1-syslibs` | `archive/nc/t1-n2-syslibs-expected-fail` | `ea9e378ef74c8c2abba9d486822cc72508c7a75b` | **Negative control**, failed in the offline self-tests; intended hosted gate **not exercised** (§3.2) |
| `wp-e2/e2b1-preflight` | `archive/exp/e2b1-preflight-pass` | `d49930e08a053f3610209ba8f795470c66a2232e` | Experiment PASS |
| `wp-e2/e2b2-full-build` | `archive/exp/e2b2-full-build-fail` | `ae312a52af066597d6940fcbb9961905cccebf74` | **Experiment FAIL** (preserved) |
| `wp-e2/e2b3-runtime-consistency` | `archive/exp/e2b3-runtime-consistency-fail` | `a24d797ae0db1b54500c4cd44ef7a427f01cf109` | **Experiment FAIL** (preserved) |
| `wp-e2/e2b3-r1-correction` | `archive/exp/e2b3-r1-correction-pass` | `5cfd890dc4660656ed9d3042c7c94b8eeda28a3a` | Experiment PASS |
| `wp-e3/e3a-m2s4u-smoke` | `archive/exp/e3a-m2s4u-smoke-pass` | `f2215ad38169b86e4c0c7e0f220c14c82a78d603` | Experiment PASS (level 2) |
| `wp-e3/e3b-m2s5-bridge` | `archive/exp/e3b-m2s5-publication-failure` | `4ed675976ac516aaf26dccf720e0b12fb671cf4a` | **E3b PUBLICATION FAILURE** (preserved) |
| *(branch retained)* `m1/ethernet-bridge` | `archive/m1/ethernet-bridge-closed` | `fbe41a9e9ba1befc0d68b9fd559be52b024c1ca9` | M1 CLOSED |
| *(branch retained)* `wp-e3/e3b-r1-publication` | `archive/exp/e3b-r1-m2s5-pass` | `edf3329ddf2350650fd0957ddd5a965fe3ddbb56` | Experiment PASS (level 2) |

**The deletion.**
- **What was deleted:** the maintainer deleted exactly the 26 former branches above on 18 November 2026, in one atomic push with an expected-head lease per branch.
- **Verified afterwards:**
  - exactly the four permanent branches remain, with unchanged heads;
  - all 30 tags are unchanged;
  - every deleted head is reachable through its tag;
  - PRs #2 and #3 are unaffected.
- **Local-only branch:** `m2/s72a-a2f1` (`13b0fb4`, F1 rev. 2) was never on the remote. It is an ancestor of `115012f` and is therefore reachable through `archive/m2/s72a-a21-closed`.

### 2.3 Pull requests

| PR | Head → base | State |
|---|---|---|
| #1 | `inet-framework:opp_env_recommendations` → `master` | merged 2026-08-05 (legacy, `v1.0.1`) |
| #2 | `howhangliu:feat/uplink-reflective-qos` (`1501a50`) → `master` | **open, kept open** (DS-TT VLAN translation retained in M2-B, DR-02) |
| #3 | `howhangliu:feat/uplink-frer` (`ea172c8`) → `master` | **open, kept open** |
| #4 | `ci/tier0-python` → `m2/continuation` | merged 2026-11-17 |
| #5, #6 | H4 negative controls → `m2/continuation` | closed unmerged (draft) |
| #7 | `ci/tier1-full-stack` → `m2/continuation` | merged 2026-11-18 |
| #8, #9 | tier-1 negative controls → `m2/continuation` | closed unmerged (draft) |

## 3. Hosted CI and experiment record

**Evidence class.** Every run below was started by the development agent on GitHub-hosted runners. **All of it is development evidence: level 2 at most.** None of it is independent scientific acceptance (`remote-execution-feasibility.md` §4, condition X-1).

### 3.1 H4 / WP-E1: tier-0 Python regression CI

| Item | Run | Result |
|---|---|---|
| Acceptance, PR #4 (`aa56938`) | 44118333251 (job 134162461692) | PASS. Fixture gate, Simu5G identity gate and the 10 declared suites, each with its exact expected line. Job duration 89 s. |
| NC-H4-fixture (`6187190`, PR #5) | 44119591587 (job 134166971757) | Failed **at the fixture gate**, as intended. Every suite and the Simu5G gate were skipped. |
| NC-H4-simu5g (`21350bb`, PR #6) | 44119608933 (job 134167030746) | The fixture gate passed; the run failed **at the Simu5G identity gate**, as intended. Every suite was skipped. |

### 3.2 WP-E2: tier-1 feasibility and the integrated tier-1 CI

| Item | Run | Result |
|---|---|---|
| E2b.1 preflight (`d49930e`) | 44186948262 | PASS (Nix 2.34.4, opp_env 0.36.2.261110, approved lock; no build) |
| E2b.2 full build (`ae312a5`) | 44192817834 | **FAIL**. Per `ci/tier1/README.md`, OMNeT++'s configure selected the host libc++ (`-lc++`). The diagnostic artifact is the authoritative record. |
| E2b.3 runtime consistency (`a24d797`) | 44204158423 | **FAIL** at the R-1 causal gate (versioned libc++ trace paths not accepted) |
| E2b.3-R1 (`5cfd890`) | 44207656877 | PASS; its linker trace is reused as a tier-1 test fixture |
| Tier-1, PR #7 (`46e95ba`) | 44227341499; 44264734964 (accepted pre-merge run) | TIER-1 PASS (C-1 … C-15) |
| N-1 wrong `LOCK_SHA256` (`c2ddebd`, PR #8) | 44261863234 (job 134656911594) | Failed in the job **"Tier 1 - offline self-tests"**. The full-stack job was skipped. **Its intended downstream hosted negative gate (lock identity before realisation) was not exercised.** |
| N-2 reordered `VM_SYS_LIBS` (`ea9e378`, PR #9) | 44261866832 | Failed **during the offline self-tests**. **Its intended downstream hosted negative gate (the SYS_LIBS gate C-5) was not exercised.** |

**Tier-1 scope (correction).** Tier-1 validates:
- the pinned release build of OMNeT++ 6.5.0, INET 4.7.0, Simu5G 1.8.1 and `libnasctime_m2`;
- linkage, the single C++ runtime and RUNPATH classes;
- **its specific reviewed configuration queries**: the two `-q runconfig` queries of the A2-V1 wrapper suite, run through the audit shim.

It does **not** automatically validate every newly introduced NED or INI configuration. A new configuration needs its own reviewed query, or an individually authorised hosted functional run (DR-15).

**Tier-1 triggering (correction).**
- **Automatic:** tier-1 automatically selects relevant **non-draft** pull requests to `m2/continuation`, from the complete change set (fail closed).
- **Override:** the collaborator label `tier1:run` forces a run, including for draft pull requests.

### 3.3 WP-E3: hosted functional simulation experiments (one-time, individually authorised)

| Item | E3a | Original E3b | E3b-R1 |
|---|---|---|---|
| Commit / branch | `f2215ad` (`archive/exp/e3a-m2s4u-smoke-pass`) | `4ed6759` (`archive/exp/e3b-m2s5-publication-failure`) | `edf3329` (`wp-e3/e3b-r1-publication`; `archive/exp/e3b-r1-m2s5-pass`) |
| Run / job | 44286506080 | 44301703292 (job 134792789497) | 44324020733 (job 134870310171) |
| Configuration | `M2S4U`, run 0 of `--repeat=10` (network `M2S4LinkTest`) | `M2S5`, run 0 (network `nasctime.simulations.m1.M1Bridge`, 5 s, seed-set 0) | same as E3b |
| **What it demonstrates** | **Wired timing functionality** (two TT ports over a link; U1 unit oracle) | — | **The downlink 5G–TSN timing path** (per-run M2-S5 oracle) |
| Oracle | Unmodified U1 of `check_m2s4.py`: PASS | `check_m2s5.rows_5gs`: PASS (C1–C7, S1, S2, P2 fully; C8, P1 partially; S3 NOT EVALUATED) | Same rows, PASS. Counts: 39 GM Sync / 39 Follow_Up, 39 slave Sync / Follow_Up, 39 N3 Follow_Ups, 5 NW-TT link-delay exchanges, 5 slave Pdelay samples, 5081 clock samples, 39 model steps. No file opened outside the raw and checker directories. |
| Tier-1 prerequisites | C-1 … C-12 PASS | C-1 … C-12 PASS | C-1 … C-12 PASS |
| E-1 … E-7 | PASS | PASS | PASS |
| **E-8 (evidence)** | PASS | **Seal PASS** (manifest `2d20992f…`, 38 files, 13 097 363 B; verified after evaluation). **Raw publication FAILED**: the N3 check refused packet 0 (`10.0.0.1 -> 192.168.2.1 outside 10.0.0.0/8`, a publication policy that was too narrow). | PASS. Seal manifest `34d3e5f358886020d6df20bcb6e34a93dec38bdbc3599b1191a7365da9fe4c83`, 38 files, 13 097 355 B, verified. Raw publication PASS: 65 files, 13 223 766 B. |
| **Verdict** | **E3a PASS** | **E3b PUBLICATION FAILURE (preserved)** | **E3b PASS** (title "E3b-R1") |
| Sealed raw evidence | Seal manifest: **9 files, 24 496 082 B**. The complete raw artifact contains **37 files** (sealed outputs plus records and manifests). | Sealed; **never published, lost** with the runner | 38 sealed files (36 run files, the run log and the effective configuration); 66 files in the raw artifact |
| Historical hashes (E-9, informational) | 4/4 OMNeT++ 6.4.0 engine-log / PCAP hashes REPRODUCED | 33 REPRODUCED, 2 DIFFER (`0.sca`, `0.vec`) | 33/33 R181c CSV and PCAP hashes REPRODUCED; `0.sca` and `0.vec` DIFFER |
| Monitoring | numeric initial and final values | wall 1.498 s; no in-run sample (maxima NOT MEASURED) | wall 0.925 s; 99 897 events; 13 087 127 B; no in-run sample (maxima NOT MEASURED) |

**N3 publication inventory, E3b-R1.**
- 1 056 frames, every one an IPv4 / UDP / GTP-U G-PDU with a PDU-session container.
- 568 downlink frames, `10.0.0.1 -> 192.168.2.1` (UPF `ppp[0]` to the gNB tunnel endpoint), recorded outbound.
- 488 uplink frames, `10.0.0.2 -> 10.0.0.1` (gNB N3 address to UPF), recorded inbound.
- No violation class. The policy and its source derivation are in `ci/tier2/README.md` on `wp-e3/e3b-r1-publication`.

**Not claimed, explicitly:**
- **Differing hashes.** The cause of the differing `.sca` / `.vec` hashes is **unverified**. They are not attributed to metadata or to any other cause, and no whole-result equivalence is claimed.
- **Scope.** E3a and E3b-R1 are **level-2 hosted development smoke evidence**; neither is independent scientific acceptance. E3b-R1 is not an M2-S5 campaign result (S3 and the M2-S4 baseline comparisons NOT EVALUATED), carries no uplink claim, and does not advance S7.2a.

## 4. Hosted evidence archives (11)

All artifacts had a 7-day retention and expired on 24–25 November 2026.

**The maintainer reports that all 11 ZIP archives were downloaded, verified against the GitHub SHA-256 digests below, and preserved in a private evidence release.** That statement is recorded here as given; the development agent did not access or verify the private release.

| Artifact | ID | Run | Bytes | GitHub SHA-256 digest |
|---|---|---|---|---|
| `e2b1-preflight-diagnostics` | 14374103515 | 44186948262 | 1 161 932 | `227dd6ba5d965d69af01019feaaa3fae30c7eeec3ca79e65ffa8895048e664ba` |
| `e2b2-full-build-diagnostics` | 14379063836 | 44192817834 | 1 187 184 | `1453a57d497aed8088b31de3c3a46e24895b151c16a938fbef1a32dc8a98f274` |
| `e2b3-runtime-consistency-diagnostics` | 14383232144 | 44204158423 | 1 186 887 | `191464ce95ea6b20013db398ba70d4b1afc298b0f19460cfaa085978730931d3` |
| `e2b3-r1-correction-diagnostics` | 14386506886 | 44207656877 | 1 240 786 | `b173df110c11d429c7accaf07408cbed1b554dcac0a21da235db9d1efee76b91` |
| `tier1-diagnostics-pr7-run44227341499-1` | 14395422931 | 44227341499 | 71 944 | `8695665a99caf52bba8665f5ec7c8214b8aa503387ed488e1c2f395fb71a8e00` |
| `tier1-diagnostics-pr7-run44264734964-1` | 14411707417 | 44264734964 | 70 219 | `1b9698b0f88a421b67051489cc2ae668a6dabca616dbd425be605e19b1b4abe4` |
| `e3a-diagnostics-run44286506080-1` | 14421578856 | 44286506080 | 86 005 | `b76a9d1ab34d26993645d7a60bc75874c74a65e9b8b4b1c26a5cb5e26fc1d529` |
| `e3a-raw-m2s4u-run44286506080-1` | 14422660700 | 44286506080 | 4 661 716 | `97cccf129ebecb2fc0764aed4812a9bac61bb2a08128c80e159dee7f02e8e2a5` |
| `e3b-diagnostics-run44301703292-1` | 14429091637 | 44301703292 | 90 768 | `c5cb4ecd74dd0a8463ed870e68af963c148b944c3e96b7311a332bddc24672f1` |
| `e3b-r1-diagnostics-run44324020733-1` | 14439080395 | 44324020733 | 90 038 | `6c92ab92dcc7cce2f3da60e86689f986ba18acc09cce06b6d2123de5d55aff4c` |
| `e3b-r1-raw-m2s5-run44324020733-1` | 14437664261 | 44324020733 | 1 927 439 | `bfd45012b802ca95a19badd4f70fdd23e265bc93dea457f2ced658ada34883ff` |

**Runs without artifacts.**
- The tier-0 runs publish logs only.
- The tier-1 negative-control runs failed before the publication step.
- The early tier-1 runs 44227303992, 44261844595 and 44261856429 were trigger-selection skips.

### 4.1 Preservation actions still pending (maintainer)

| Action | Status |
|---|---|
| Export the job logs of every run in §3 (the only record of the H4 and tier-1 negative controls; repository log retention, typically 90 days, to be verified) | **Pending** |
| Verify the internal raw manifests inside the preserved archives:<br>• E3a: seal manifest, 9 files / 24 496 082 B; 37-file raw artifact;<br>• E3b-R1: seal manifest `34d3e5f3…` and the publication manifest;<br>• the 33 E3b-R1 hashes against `ci/tier2/ref-e3b-r181c-run0.sha256` | **Pending** |
| VM-only legacy datasets (DR-06b) | Unchanged: at risk until VM access resumes |
