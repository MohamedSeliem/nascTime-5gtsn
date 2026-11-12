# M2-R181 acceptance record: Simu5G 1.8.1 migration validation

**Decision.** Accepted by Dr Mohamed Seliem, 2026-11-12 14:58 (Europe/Dublin), on the M2-R181c closure report at `db96347`. This closes the M2-R181 / R181b / R181c validation milestone on the documented version-appropriate criteria.

**Branch.** `m2/simu5g-1.8.1`: 25 commits on top of `m2/architecture` at `14d5e0f`, which contains the frozen GitHub `master` (`9e8bc83`) as an ancestor. Accepted closure commit: `db96347`. The commit that adds this record is the transfer tip. Its SHA is given in `IMPORT-M2-R181.md` next to the bundles, because a commit cannot contain its own hash.

**This record does not change** any historical record, checker, prediction or FAIL verdict.

---

## 1. Acceptance summary

### 1.1 Validated stack

| Component | Version / identity |
|---|---|
| OMNeT++ | 6.4.0 (build 260506-2cf25223fe) |
| INET | 4.7.0 (`inet-4.7.0-dfe270b21f`) |
| Simu5G | **1.8.1, unmodified**: `git archive v1.8.1` (`7477d266`), `tar --diff` against the tag clean; `libsimu5g.so` sha256 `0dbda409…2ddb270131` (environment-specific: the build path is embedded) |
| Reference baseline | Simu5G 1.8.0, accepted build `203cf231…` (1.8.0 controls only) |
| Upstream patches | none (OMNeT++, INET, Simu5G) |
| Not validated | OMNeT++ 6.5.0 / the reviewer's VirtualBox VM; the VM NED / INI patch is not incorporated |

### 1.2 Accepted results on 1.8.1

| Area | Historical record (kept, verdict unchanged) | Accepted version-appropriate result |
|---|---|---|
| Upstream U0 / U1 | PASS | — |
| M1 S0–S4 (incl. S2-phase) | PASS (S4 transport and clock checks PASS) | — |
| M1 O-S3-1 | FAIL (the row expects 1.8.0 HARQ losses; 0 on 1.8.1) | O1-cons PASS; mutation FAILs |
| M1 upstream-issues | "issues reproduced: NO" (fixed upstream in 1.8.1, as predicted) | — |
| M1 S5 | FAIL: W-identity, R-ingress, R-egress | S5-W-identity-v PASS; S5-R-ingress-v PASS; S5-R-egress-v2 PASS (1073/1073 exact); each mutation FAILs |
| M1 O-tail | historical checker crashes (no cut SDU) | OT-strand PASS (mutation FAILs); `check_o_tail_v181.py`: defined no-cut verdicts, byte-identical to the 1.8.0 record on 1.8.0 outputs |
| M2-S0 | FAIL 20/21 (A7) | A7-v PASS |
| M2-S1 | FAIL 27/28 (C10) | C10-v PASS |
| M2-S3 | PASS 24/24 | — |
| M2-S4 | FAIL 54/55 (R2b) | R2b-v PASS (send-time differences all attributed to the talker's own Pdelay_Req; arrivals unchanged); M2-S4 → M2-S5 gate open |
| M2-S5 | FAIL 66/71 (C8, N-tseSlot, N-noFcsNw, N-noStrip, N-fwdPdelay) | C8-v PASS on all 13 run pairs; 69/71, only the two superseded controls fail; N-tseSlot-v and N-noFcsNw-v PASS (S3o); C8-v demonstration PASS; M2-S5 → M2-S6 gate open |
| M2-S6 | (never evaluated on 1.8.1 before R181c) | **PASS 1863/1863**, 0 verdict changes from 1.8.0; D0 8/8 and E0b 3/3 byte-identical to 1.8.0 |
| S7.2a CP1 rev. 2 | F0 PASS (controls 6/6); T0 5 PASS / 5 FAIL (T0-R: reruns compared with 1.8.0 hashes) | T0-R reviewed: a cross-version difference, not a functional failure |
| S7.2a CP2 rev. 2 + I-2H | — | PASS: 2391 gate rows / 0 FAIL, controls 13/13; I-2H PASS (assembled from batches) |
| R-4 legacy identity | FAIL (3 files) | adjudicated: historical or non-semantic; no reproducible output changed |

### 1.3 Accepted criteria (added alongside the historical ones, never replacing them)

- **A7-v / C10-v:** byte identity, exactly once, in order, and conservation, with the same rule for 5 and 16 HARQ processes.
- **R2b-v:** exact arrival equality, and an exact attribution of every send-time difference. The 10 shifted frames are a regression fingerprint, not the invariant.
- **S5-R-egress-v2:** sample = PCAP transit + own serialisation + near-port egress wait, to 1 ns.
- **S5-R-ingress-v:** counts both directions at the module that carries both.
- **C8-v:** M2-S0 tag carriage validated by packet class:
  - forwarded frames are tagged at the NW-TT, recovered at the DS-TT and equal to M2S4;
  - DS-TT-generated Pdelay_Resp / Resp_FU frames are one-to-one with the engine and excluded from the cross-scenario comparison by identity.
- **N-tseSlot-v** (the same mutation under load) and **N-noFcsNw-v** (the same mutation with an initial slave offset, an `M2S4R-offset` reference and S3o, the step-pair rule).
- **Dependency gates M2-S4 → M2-S5 and M2-S5 → M2-S6.** Each writes `raw-outputs.sha256` with the runner's own command over the real runs, only when its explicit conditions hold.

### 1.4 Limitations (explicit; part of the acceptance)

1. **C8-v (d) assumes a lossless 5GS.** It checks bridge carriage only where the 5GS delivers every forwarded frame. On 1.8.0 M2S5-load it fails because the 5GS discards 2531 frames (consistent with the 5-HARQ MAC discards, not separately replayed). Every M2-S5 run on 1.8.1 is lossless.
2. **M2-S6 hypothesis refutations remain** (reported, not gating), as on 1.8.0: H8 (K7 tick-reset bias) refuted in 29 configurations; H1c refuted in E-sig100. H1c E-all-load now holds.
3. **S3 is blind to a slave that starts exact** (N-noFcsDs, N-noFcsNw). The replacement adds an offset; the historical S3 is unchanged.
4. **Replacement controls use seed 0**, as the historical controls do.
5. **Historical FAILs kept:** M1 S5 (3 rows), M1 O-S3-1, O-tail checker crash, S5-R-egress-v (superseded by v2), M2-S0 A7, M2-S1 C10, M2-S4 R2b, M2-S5 66/71 (5 rows), S7.2a T0-R ×5, R-4.
6. **Single environment.** All 1.8.1 evidence comes from one machine (OMNeT++ 6.4.0, 2 cores, an 11 GB disk allowance). Not yet reproduced independently (§4).
7. **Load results on 1.8.0** (S7.1, S7.2a E0, the cfqd counterfactual) are not re-established on 1.8.1 (§5).

---

## 2. Git history and repository hygiene review

### 2.1 History

| Item | Finding |
|---|---|
| Branches (local) | `m2/architecture` at `14d5e0f` (194 commits); `m2/simu5g-1.8.1` at the tip (219 + this record). No local `master`, no remotes, no tags |
| Ancestry | `9e8bc83` (GitHub master, "README fixes") is an ancestor; 177 commits `9e8bc83..db96347`. Two root commits (`0a83509` initial project; `86ea952` vboxuser baseline, joined by the v1.5.0 merge `f69ea9c`) predate M1 and are already on GitHub |
| Authors | Mohamed Seliem 90, Claude `<noreply@anthropic.com>` 119, Rudolf Hornig 8 (upstream template), vboxuser@TSN.myguest.virtualbox.org 2. Authorship is public after a push; nothing else identifying is in the metadata |
| Merges / rewrites | No history rewriting is needed or recommended. Every record cites commit hashes |

### 2.2 Size

| Item | Finding |
|---|---|
| Repository | `.git` 12 MB; pack 2.9 MB; 1137 tracked files, 29.5 MB working tree (results records 25.6 MB) |
| Largest tracked files | `m2/results/M2-S7.1/raw-outputs.sha256` 4.7 MB; `M2-S7.2a-cp2r2/raw-outputs.sha256` 1.1 MB; `m2s72.ini` 0.7 MB (generated, regeneration-checked by design) |
| Largest blobs in history | 4.7 MB (three versions of the S7.1 hash list). No blob reaches GitHub's 50 MB warning or 100 MB limit |
| Binaries | none tracked (`.so`, `.o`, `.sca`, `.vec`, `.vci`, `.pcapng`, archives: 0). `*_m.h` / `*_m.cc` are ignored |
| Line endings | 4 tracked CSVs are CRLF by content (`demos/.../fading.csv`, `M2-S3/syncs.csv`, both `e0-metrics.csv`). No `.gitattributes`. Clone with `core.autocrlf=false` so that byte-identity checks hold |

### 2.3 Generated outputs and untracked evidence (stay local; never pushed)

- `.gitignore` excludes `results/`, `*.sca`, `*.vec`, `*.vci`, `*.elog`, `*.log`, `*.so`. **Every committed record under `results/` was force-added (`git add -f`).**
- About **19 GB of ignored raw evidence** is on this machine. All of it is hash-listed in committed manifests:

  | Evidence | Size |
  |---|---|
  | `m2/results/M2-S7.2a-e0/runs` (**E0, must not be deleted**) | 11.5 GB |
  | cfqd runs | 1.4 GB |
  | cp2r2-trial1 runs | 1.3 GB |
  | cp1r2 runs | 1.1 GB |
  | S7.2a runs | 1.0 GB |
  | 1.8.1 M1 per-run CSVs (`out/m1/*/seeds.csv` etc.), including several **> 100 MB** (S3 `load.csv.gz` 156 MB, O-tail CSVs 109 MB, S5 `seeds.csv` 104 MB) | — |
  | Leftover run logs in `out-r181b-cp2/*/runs/` | 276 MB |

- **Risk:** a broad `git add -f simulations/results/...` would stage these. Some exceed GitHub's 100 MB limit, and an accepted push would bloat the history permanently.
  - **Rule:** force-add named record files only, and check `git diff --cached --stat` before every commit.
  - **Optional hardening** (not done; a configuration-only commit, if you approve): explicit ignore lines for `**/runs/`, `*.csv.gz` and `seeds.csv` under `simulations/results/`.

### 2.4 Environment-specific paths

| Where | Finding | Effect elsewhere |
|---|---|---|
| All M1 / M2 runners | `OMNETPP_ROOT`, `INET_ROOT`, `SIMU5G_ROOT` default to `/root/stack/...`; **`SIMU5G_ROOT` defaults to 1.8.0** | Overridable: always export all three on another machine |
| `nt_results.sh` legacy mode | refuses to run unless `libsimu5g.so` hashes to the accepted 1.8.0 build (`203cf231…`) | On any other machine legacy mode is refused, because the build path changes the hash. **Always use isolated mode** (`NASCTIME_RESULTS_ROOT`) |
| `m2s72.sh` modes `e2rb`, `cfqd` | hard-coded `/root/stack/simu5g-1.8.0` (accepted-build guard) | These 1.8.0-only modes cannot run elsewhere unchanged; they are not needed for 1.8.1 |
| `r181b/run_controls_180.sh`, `r181c/run_r181c_ctl180.sh`, `run_diag_c8v_load_180.sh` | require the accepted 1.8.0 library hash | 1.8.0 evidence: not reproducible elsewhere without that exact build. Not needed for 1.8.1 verification |
| Historical helper files: `M2-S7.2a-cp2r2-trial1/{opp.sh, htry.py, ptry.py, probe-load.ini}`, `M2-S7.2a-upstream-repro/repro.ini` | hard-coded `/root/inv/...` and `/root/stack/...` | Records of what ran; leave unchanged |
| Records (`env*.txt`, `stack.txt`, manifests, reports) | contain `/root/inv/nascTime-5gtsn/...` and `/root/stack/...` | Provenance only; harmless; no credentials, keys or e-mail addresses found in tracked content |
| `README.md` | still describes the legacy v1.0 (Simu5G 1.5, fork, FRER) | Misleading on a pushed branch; documentation fix recommended, separately |

**Nothing on `m2/simu5g-1.8.1` needs to be removed before a push.**

---

## 3. Transfer of `m2/simu5g-1.8.1` to GitHub (master untouched)

Deliverables: `/root/inv/deliver/m2r181/`, sent as files. `IMPORT-M2-R181.md` holds the tip SHA, the bundle checksums and the rehearsal outcome.

| Bundle | Contents | Use when |
|---|---|---|
| `nascTime-m2-simu5g-1.8.1-full.bundle` | the single ref `m2/simu5g-1.8.1` with its complete history, no prerequisites | always works |
| `nascTime-m2-simu5g-1.8.1-14d5e0f.bundle` | `14d5e0f..m2/simu5g-1.8.1` (incremental) | your clone already has `14d5e0f` (the last delivered `m2/architecture` bundle) |

**Procedure.** Run in your normal clone of the GitHub repository, with a clean working tree. Nothing below touches `master`, other branches or the working tree.

```bash
cd ~/nascTime                                  # your clone of the GitHub repo
git status --short                             # must be empty (stash or commit the VM patch elsewhere first)
git fetch origin
git rev-parse origin/master                    # note it: must be identical at the end

sha256sum -c nascTime-m2-simu5g-1.8.1-full.bundle.sha256
git bundle verify nascTime-m2-simu5g-1.8.1-full.bundle       # "... is okay"
git fetch nascTime-m2-simu5g-1.8.1-full.bundle m2/simu5g-1.8.1:m2/simu5g-1.8.1
git rev-parse m2/simu5g-1.8.1                  # must equal the tip SHA in IMPORT-M2-R181.md
git log --oneline -3 m2/simu5g-1.8.1
git merge-base --is-ancestor 9e8bc83 m2/simu5g-1.8.1 && echo "contains frozen master"

git push origin refs/heads/m2/simu5g-1.8.1:refs/heads/m2/simu5g-1.8.1   # this branch only
git ls-remote origin refs/heads/master refs/heads/m2/simu5g-1.8.1         # master unchanged; branch = tip
```

- **Never use** `git push --all`, `--mirror`, `--force`, or a bare `git push` with `push.default=matching`.
- **`m2/architecture`:** it is not needed, because the new branch contains its history. If you also want it on GitHub, push it the same way with its own refspec, after checking `git rev-parse m2/architecture` = `14d5e0f`.
- **Optional:** protect `master` in the GitHub settings (Branches → protection rule) before pushing.
- **The VM patch stays separate:** keep it on its own local branch, or as an uncommitted diff, on the VM; never on `m2/simu5g-1.8.1` until it has been reviewed.

---

## 4. Minimal independent verification checklist (VirtualBox VM)

**Principle.** Reproduce on a second machine from the bundle, using the same runners and checkers, and compare the record files byte for byte with the committed ones. A verdict match is required. Byte-identity is expected on OMNeT++ 6.4.0. **Use a clean worktree without the VM patch.**

### V0. Environment (record everything in a log)

1. **Stack.**
   - Install OMNeT++ **6.4.0** next to 6.5.0, plus INET 4.7.0.
   - Build Simu5G 1.8.1 from tag `v1.8.1` (`7477d266`), unmodified. `git status` in Simu5G must be clean, and `cat $SIMU5G_ROOT/Version` must give `1.8.1`.
   - If only 6.5.0 is possible, run the checklist as a separate cross-version study. Verdicts are then compared, byte-identity is not expected, and the NED / INI patch question arises first.
2. **Worktree.**
   - `git worktree add ~/nt-r181 m2/simu5g-1.8.1` (clean tree; your patched tree is untouched).
   - `git -C ~/nt-r181 rev-parse HEAD` must equal the tip SHA.
3. **Environment variables.**
   - `export OMNETPP_ROOT=… INET_ROOT=… SIMU5G_ROOT=<simu5g-1.8.1>`.
   - Each step below uses its own new **absolute** `NASCTIME_RESULTS_ROOT` outside the repository, for example `~/r181vm/<step>`.
   - Legacy mode is refused by design.
4. **Disk and CPU.** ≥ 15 GB free for V2 (peak about 8.5 GB) and ≥ 25 GB for V3b. `JOBS=1` everywhere.

### V1. M1 S4–S5 (about 20 min)

```bash
export NASCTIME_RESULTS_ROOT=~/r181vm/m1; S=~/nt-r181/simulations
$S/m1/s4_gptp_transport.sh && $S/m1/s5_metadata.sh          # s5_metadata.sh reads S4's seeds.csv
python3 $S/m1/check/check_v181.py  s5  $NASCTIME_RESULTS_ROOT/m1 > v181-s5.txt
python3 $S/m1/check/check_v181b.py s5e $NASCTIME_RESULTS_ROOT/m1 > s5e.txt
python3 $S/m1/check/check_v181b.py s5i $NASCTIME_RESULTS_ROOT/m1 > s5i.txt
# each of the three again with --mutate: must FAIL
```

Compare with `simulations/results/simu5g-1.8.1/`:

| Output | Expected | Committed reference |
|---|---|---|
| `m1/S4/transport-check.txt`, `m1/S4/clock-check.txt` | PASS | `out/m1/S4/` |
| `m1/S5/check.txt` | FAIL (W-identity, R-ingress, R-egress) | `out/m1/S5/check.txt` |
| `v181-s5.txt` | W-identity-v PASS, R-egress-v FAIL | `out/m1/v181-s5-check.txt` |
| `s5e.txt` | PASS, 1073/1073 | `r181b/m1-on-1.8.1/v181b-s5e-check.txt` |
| `s5i.txt` | PASS | `r181b/m1-on-1.8.1/v181b-s5i-check.txt` |

### V2. M2-S0 → S6 with both gates (about 2.5 h)

```bash
~/nt-r181/simulations/results/simu5g-1.8.1/r181c/run_r181c.sh ~/r181vm/m2   # absolute, new; JOBS=1 inside
```

The driver runs, in order:
- m2s0 and m2s1;
- m2s4, then R2b-v and its mutation, then the M2-S4 gate;
- m2s5, then the three `m2s5r181c.ini` configurations, then the C8-v check, `c8demo`, `controls` and the M2-S5 gate;
- m2s6.

It hashes every run before deleting it, and stops on a closed gate.

Compare with `out-r181c-m2/` (expected byte-identical on 6.4.0):

| File | Expected |
|---|---|
| `m2/M2-S0/check.txt` | FAIL 20/21 (A7) |
| `m2/M2-S1/check.txt` | FAIL 27/28 (C10) |
| `m2/M2-S4/check.txt` | FAIL 54/55 (R2b) |
| `r2b-v-check.txt` / `r2b-v-mutation-check.txt` | PASS / FAIL |
| `m2/M2-S5/check.txt` | FAIL 66/71 |
| `check-v181c.txt` | 69/71 (FAIL only N-tseSlot, N-noFcsNw) |
| `c8demo-v181c.txt`, `controls-v181c.txt` | PASS |
| `m2/M2-S6/check.txt` | PASS 1863/1863 |
| `gate-D0.txt` 8/8, `gate-E0b.txt` 3/3, `report.txt` | as committed |
| `DEPENDENCY-GATE.txt` (both) | OPEN; differs only in timestamps |
| `.pcapng` and per-run CSV log hashes in each `raw-outputs.sha256` | identical; `.sca` / `.vec` differ (run metadata) |

A7-v / C10-v are R181b rows: optionally run `check_v181b_m2.py a7|c10` as in `r181b/run_m2.sh`.

**Any difference: stop and send the differing file.** Do not rerun until its cause is understood.

### V3. S7.2a representative cases

- **V3a. CP1 rev. 2** (about 10 min, about 1.1 GB): `NASCTIME_RESULTS_ROOT=~/r181vm/s72 JOBS=1 ~/nt-r181/simulations/m2/m2s72.sh all`.
  - Expected: `f0-check.txt` F0 PASS, controls 6/6; `comparator-canaries.txt` as committed; `t0-check.txt` 5 PASS / 5 FAIL. The FAILs are exactly the T0-R rows, which compare with the 1.8.0 hashes, as reviewed.
  - Reference: `out-s72/m2/M2-S7.2a-cp1r2/`.
- **V3b. CP2 rev. 2 + I-2H, complete** (optional; ≥ 25 GB free, several hours): `NASCTIME_RESULTS_ROOT=~/r181vm/cp2 JOBS=1 ~/nt-r181/simulations/m2/m2s72.sh r2`.
  - This is the single-campaign form that this environment could not hold (here it was run in batches Q / Q2 / D and assembled).
  - Expected: the `check_m2s72_cp2r2.py` verdict PASS, 2391 gate rows, 0 FAIL, controls 13/13, I-2H PASS.
  - Reference: `out-r181b-cp2/m2/cp2r2-assembled.txt`. Compare verdicts and row counts per family; the line order differs from the assembled form.

### V4. Report back

Send the `steps.txt` files, every compared record, and `stack.txt` / `env*.txt`, plus `git -C ~/nt-r181 status --short` (must be empty).

---

## 5. Remaining M2-S7.2a work (status at this acceptance)

**Baseline change.** Every S7.2a load result was produced on 1.8.0, where #308 / #310 / #311 confound it:
- the Q-d UL starvation;
- the HARQ-5 discards;
- the DRB-1 tail lag.

On 1.8.1 these mechanisms are gone or changed (M2-R181), so the load-dependent results must be re-established, not reused. The functional gates (CP1, CP2 r2, I-2H) are already re-established.

### 5.1 Implementation gaps (before any Stage 5 run)

| Gap | Content | Status |
|---|---|---|
| G-1 Generator | `sym` regime and load factors (E1 / E2); E3 configurations | not implemented (E0's one-UE factors exist) |
| G-2 S7.1 per-UE rows | P0, C0, C1, H0, Q0a, Q0b, Q1, Q5, Q6 per UE (≈ 1,500 lines of Python) | not implemented; Q8 / Q8-x exist in the E0 checker |
| G-3 Version-aware oracles | rows that encode 1.8.0 behaviour (W2 MAC-log deletion accounting, W3 RLC tail-cut replay, Q8 "deletions" classes, the SG-403 expectation) need 1.8.1 forms, added alongside as in R181b / R181c | not started |
| G-4 1.8.1 runtime errors | 1.8.1 throws on a MAC PDU with no free HARQ process and on an inactive connection with data. Any 5-HARQ overload configuration may abort instead of losing data. The handling must be declared (gate, or expected abort) | unverified |
| G-5 Runner hygiene | `SIMU5G_ROOT` defaults to 1.8.0; the 1.8.0-only modes (`e0`, `cfqd`, `e2rb`) refuse isolated mode; 1.8.1 equivalents are needed | not started |
| G-6 Storage | E0 ≈ 11 GB, E1 batches ≈ 13 GB, E2 up to ≈ 227 GB cumulative; the ≥ 20 GB start rule | blocks quantitative work in this environment |
| G-7 VM NED / INI patch | needed for OMNeT++ 6.5.0 | awaiting the patch |

### 5.2 Experiments

| ID | Purpose | State on 1.8.0 | Needed on 1.8.1 |
|---|---|---|---|
| **E0** capacity calibration | define "overload" before any overload claim | done, r2 PASS (8 runs); Q-d UL 2.48 Mb/s, a #308 artefact | **re-run** (N = 1, Q-0 / Q-d, HARQ16); the Q-d UL starvation should disappear; SG-403 kept as a regression invariant (expected 0 / 0) |
| **E3** combined TT-clock + path heterogeneity | closes the largest remaining oracle gap (both terms non-zero) | proposed, not run | run before E1 (≈ 12 runs, 6–7 GB) |
| **E1** scaling core (Block C) | N = 1, 2, 4, 8 × idle / sym / one × Q-0 / Q-d × HARQ | not run (≈ 200 runs) | after E0 and E3 |
| **E4** horizon and trace evidence | P0 / H0 per UE; in-run MAC logs | not run | with E1 |
| **E2** load sweep / failure onset | onset order, degradation | DL-only re-baseline prepared (rev. 2.1, SG-403 safeguard), **not run** (storage) | **re-declare**: the DL-only restriction (W5) becomes unnecessary on 1.8.1 once verified; restore UL load and the matched Q-0 / Q-d design, after E0 |

### 5.3 Failure isolation (design §7, Stage 6, Checkpoint 3)

FI-1…FI-8 at N = 4 on UE 1 / DS-TT 1 / slave 1:
- downstream faults FI-1…5 require byte-identity of everything outside the affected set;
- shared-radio faults FI-6…8 require attribution of every difference to a shared resource (rule AR);
- plus the exact comparator with canaries CN-1…CN-4 and the Block E negative controls.

**Status: not implemented.** Configuration only (existing TEST knobs); no C++ planned. Block F (seed diagnostic at N = 4) and the stage-8 `m2s72.sh all` record follow.

### 5.4 E2 preparation (when authorised)

1. E0 on 1.8.1, with SG-403 and the 1.8.1 runtime-error handling (G-4).
2. Re-declare the E2 protocol for 1.8.1, with predictions committed before any run:
   - UL restored;
   - matched Q-0 / Q-d;
   - HARQ pairing reconsidered (on 1.8.1, 5 processes no longer discard silently);
   - the onset thresholds of the Stage 5 proposal §5.2.
3. Storage: run on the VM or a larger environment (≥ 20 GB per batch).
4. Upstream #308 is open (MohamedSeliem). Its fix in 1.8.1 differs from our candidate patch, so U1 and the `upstream-repro` rerun on 1.8.1 establish what remains; no new upstream action without approval.

**Suggested order after the VM verification:**
1. VM NED / INI patch review and integration (G0 identical on 6.4.0);
2. G-3 / G-5;
3. E0 on 1.8.1;
4. E3;
5. G-1 / G-2, then E1 + E4;
6. Stage 6 failure isolation;
7. E2 re-declared;
8. S7.2a closure (fresh-clone reproduction);
9. S7.2b (UL / UE-to-UE).

**Not started by this record:** no M2 implementation and no quantitative experiment.
