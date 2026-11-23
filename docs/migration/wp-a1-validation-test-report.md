# WP-A1 — Validation procedure test report (step 141)

**Status: for independent review, 23 November 2026.**
- These are tests of the **procedure** (runbook revision 4) on dummy data and public code only.
- No genuine archive was accessed.
- No qualification, validation or simulation was run.

| Item | Value |
|---|---|
| Procedure commit tested (`D`) | `544c093a6353ac37dcd9f40fa4d2b01696bc08a7` (runbook revision 4, scripts and tests) |
| Reviewed implementation `C` | `f3f68be696777e42b0717f949625855ddb475435` |
| Container image | `python:3.13@sha256:9ffe84122ce74ebdffe2e0e6b946c9dd95d0bf3463f6eb1006b4dc6fefe36d01` (Python 3.13.18; git 2.47.3; util-linux 2.41.5; OpenSSH `ssh-keygen -Y`) — a test choice, not an approval |
| Docker | Engine 29.9.2, overlayfs, seccomp; containers run `--network none` through `host-stage.sh` |
| Host tools | util-linux 2.39.3 (`script -e`), OpenSSH 9.6 |
| Signing key | a throwaway ed25519 key labelled TEST ONLY, standing in for the maintainer's |

## 1. Results

| Suite | Result |
|---|---|
| `test-stage6.sh` | **17 / 17 PASS** |
| `test-approvals.sh` | **17 / 17 PASS** |
| `test-extract.sh` | **16 / 16 PASS** |
| `test-g0ro-compare.sh` | **8 / 8 PASS** |
| `run-all.sh` on the host | ALL PASS |
| `run-all.sh` inside the pinned image, network-less | ALL PASS |
| `docker-integration.sh 544c093…` | **29 / 29 PASS**, 378 s |

**Sensitivity check.** The same `test-stage6.sh` against the revision-3 `stage6-finalise.sh` (`151e164`) gives 1 PASS / 16 FAIL. This includes the changed-expectation case, where the old script only warned and exited 0.

This is a coarse check: the revision-3 script also aborts early, because its `refs/` copy no longer exists. So not every one of those failures is attributable to the specific integrity rule the test targets.

## 2. Stage 6 failure behaviour (step 141, items 1 – 2)

| Case | Exit | `RESULT.txt` | Preserved (final record and inventory verify) |
|---|---|---|---|
| clean, complete, no findings | 0 | `integrity: PASS`, `acceptance_eligible: YES` | yes |
| **changed expectation file** | **4** | `integrity: FAILED`, I-1 (and I-3), `acceptance_eligible: NO` | **yes** |
| **dirty worktree: untracked file** | **4** | I-3, NO | **yes** |
| dirty worktree: modified evaluator file | 4 | I-3, NO | yes |
| worktree moved off `C` | 4 | I-2, NO | yes |
| dirty Simu5G tree | 4 | I-4, NO | yes |
| symlink in the evidence | 4 | I-5 (listed, not followed, not inventoried), NO | yes |
| nested `SHA256SUMS` no longer verifies | 4 | `F7-verification.txt`: FAILED (covered by `SHA256SUMS.final`) | yes |
| missing console transcript | 4 | F-3, NO | yes |
| findings (Stage 5 exit 3) | 5 | `integrity: PASS`, NO | yes |
| NO-GO record (no gate B) | 5 | PASS, NO | yes |
| second finalisation | 1 | — (refused) | unchanged |

## 3. Docker integration sequence (dummy data; step 141, item 4)

The host and container sequence, run through `host-stage.sh` with a real daemon:

**Session Q (qualification):**
- H-1 (signed gate A; scripts exported from `D`) → 0.
- H-3 `qualification` → 0: release verified, 78 dummy files extracted, archives re-verified.
- DR-13-V (b), mapped profile, no mount at `R` → 0: DV-b1, b2, b3 and X unchanged.
- DR-13-V (a), mounted profile → 1. DV-a1 and DV-a2 passed. DV-a3 stopped at the extractor's seal gate, as dummy data must.
- G0-RO → 1, NOT EQUIVALENT, as dummy data must. **All 11 suites passed inside the image (G0RO-P)**, and the coverage record was printed.
- The transcript holds every `host-stage` exit code.

**Session V (validation), with TEST-ONLY signed A-4 / A-5 statements and records:**
- H-1 → 0.
- **Refusals:**
  - H-3 `validation` before gate B → 1, with nothing extracted;
  - Stage 2 with an altered A-5 statement → 1, with no evidence directory created.
- **Stage 2 → 0, GO**, in the pinned image: 11 suites, signed gates, image digest.
- H-3 `validation` → 0.
- Stage 3 → 1: stopped at the A2-V1 public pins (real hashes), after the three manifests were verified by mapping.
- **TEST-ONLY copy of Stage 3** without its two real-hash comparisons → 0: seal set, smoke seals, `Run72` readiness.
- Stage 4 → 0: read-only mount equals X.
- Stage 5 → 1. V-N1 and V-N2: `hrq` exit 5, recorded as findings, P-3 identical. V-V1: stopped at P-1 (dummy seal), not evaluated.
- Stage 6 → 5: integrity PASS, not eligible. The final record and inventory verify. The approvals, records and the labelled TEST-ONLY script copy are preserved in the evidence.

## 4. G0-RO reference review (step 141, item 3)

The values were checked against the committed records. The details are in runbook §7.

**R (recorded D-2 results):**
- **A2-V1-S1, from S1 closure §1 – §3:** exit codes, verdicts, window, 13 row statuses, per-node accounting, handles, unresolved, end states, and the controls counts.
- **N = 2 XA, from `M2-S7.2a-a2-design-review.md` §1:** row statuses, A-1 counts, UE-sent NACK and retransmitted PDUs.
- **N = 1, same source:** A-1a 11 697; ambiguous, orphan, re-insert 0; no DL NACK.

**D (derived):** the N = 2 `xa` exit code, from `xa_ok`.

**P (declared only; corrected):** the N = 1 XA row statuses, δ, A-1b and exit code. They are a protocol expectation, not a committed result. Revision 3 had counted them; they are now information only.

**Added:** the recorded window, and the N = 2 UE-sent NACK and retransmitted-PDU counts.

**Not compared, recorded with reasons:**
- the line-class totals 742 / 40 / 15, because the JSON class-key mapping is not verified;
- the A2-8 scalar values (implied by the counts and the row status);
- A2-7 details and occupancy;
- the coverage section;
- the per-control rows;
- S1 S-1 / S-2;
- run times;
- XA aggregates;
- the N = 1 retransmitted PDUs.

## 5. Gate-A references (step 141, item 5)

- Every gate-A item is now a maintainer-**signed** statement (`ssh-keygen -Y`, namespace `wpa1-approval`).
- A-4 and A-5 bind the approved record by sha256, and all three statements name the same procedure commit.
- **Refused** (AP-2 … AP-16): unsigned, altered, wrong key or namespace, not APPROVED, duplicate keys, wrong gate, wrong reviewed commit or expectation hash, missing `allowed_signers`, a changed or absent approved record, another procedure commit.
- In Docker, an altered A-5 statement made Stage 2 NO-GO before any evidence directory existed.

## 6. Remaining limitations

1. **Dummy data cannot exercise the real-hash checks.** The Stage 3 public pins and seal identity, DR-13 DV-a3, the V-V1 P-1 extraction, G0-RO equivalence and `hrq` on genuine runs are untested by design. In session V, Stages 4 – 6 were reached through a labelled TEST-ONLY Stage 3 copy.
2. **The genuine node-id path (`Run72` on real PCAP / CSV files) and `hrq` on genuine trees** have only run on the VM historically. Their first independent execution is session Q (G0-RO) and then session V.
3. **The tests ran as root (uid 0).** Read-only mounts were refused through EROFS, which holds for root. The `chmod -R a-w` seal is not effective for root. The executor should run the containers as a non-root user; `host-stage.sh` passes the caller's uid and gid.
4. **Key provenance is outside the scripts.** The scripts verify signatures against the `allowed_signers` the executor installs. Obtaining the maintainer's key genuinely, out of band, is a procedural duty of the executor; its fingerprint is recorded in the evidence.
5. **H-1's GitHub cloning was replaced by local clones** in the test (`NASCTIME_SRC`; `SIMU5G_URL`, which keeps the HEAD pin check). The real network clone happens once on the executor's host.
6. **Only Docker was exercised**, not Podman. Only gzip tar was used in the Docker run; zip and the other tar forms are covered by `test-extract.sh`.
7. **The G0-RO omissions** of §4 remain uncompared, and the N = 1 XA statuses are information only.

## 7. Recommendation

- **Procedure: ready for remote qualification**, subject to the maintainer's approvals. Every requested correction is implemented and tested, and the full host / container sequence runs end to end in Docker on dummy data.
- **GO to authorise session Q (qualification)** once all of these exist:
  1. the executor and host are designated;
  2. the maintainer approves `C` and `D` = `544c093a6353ac37dcd9f40fa4d2b01696bc08a7` with the four expectation and registry hashes;
  3. the maintainer authorises archive access and supplies the release `SHA256SUMS` hash and archive names;
  4. the maintainer hands the executor their public signing key out of band and signs `gate-a.txt`.
- **Genuine validation (session V): NO-GO.** It requires the DR-13 and G0-RO records from session Q, approved by the maintainer's signed `a4-dr13.txt` and `a5-g0ro.txt`, and then Stage 2 GO.
