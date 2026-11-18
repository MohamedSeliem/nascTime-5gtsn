# H4 — first implementation task: tier-0 Python regression CI

**Status: revision 2 (corrected per the maintainer's review of 17 Nov 2026).** Canonical location: `docs/migration/h4-first-task.md`.

~~**Not started.**~~ The maintainer implements H4 through the GitHub-based remote development workflow. This document specifies it; it does not implement it.

**Status (revision 3, 18 Nov 2026): implemented and accepted (DR-14).** The specification below is unchanged and is now **historical**. Its authorisation boundary, stop conditions and "next tasks" applied to H4 only. They are **not** active restrictions or the current status: see `travel-development-plan.md` §3a and `remote-agent-handover.md`.

| Criterion | Record |
|---|---|
| H4-1, H4-2, H4-6 | PR #4 from `ci/tier0-python` (`aa5693879957be9be198ad208c907caf257a8a54`), merged into `m2/continuation` 2026-11-17 (`c4fb6c8`). Acceptance run 44118333251 (job 134162461692): fixture gate, Simu5G identity gate, the 10 declared suites with their exact lines, and the two NOT RUN entries. |
| H4-3 | NC-H4-fixture (`61871909cd9f7b69b699636e6a418bfce87259c9`, draft PR #5, closed unmerged). Run 44119591587 failed **at the fixture gate**; every suite and the Simu5G gate were skipped. Intended reason: **met**. |
| H4-4 | NC-H4-simu5g (`21350bb1919cd08b07c6e517ec3c3a66293c779c`, draft PR #6, closed unmerged). Run 44119608933: the fixture gate passed; the run failed **at the Simu5G identity gate**; every suite was skipped. Intended reason: **met**. |
| H4-5 | Both negative controls failed for their intended reason. |
| H4-7 | Job duration 89 s (feasibility F-1) |
| Branches | `ci/tier0-python`, `ci/nc-h4-fixture` and `ci/nc-h4-simu5g` were deleted on 18 Nov 2026 after their run records were captured. Their heads are preserved by `archive/ci/tier0-python-pr4`, `archive/nc/h4-3-fixture-byte-expected-fail` and `archive/nc/h4-4-simu5g-commit-expected-fail` (`repository-archive-and-evidence-register.md`). |


**Terminology.** "H4" is the first implementation step after the evidence collection (H1, H2) and the E0 integration commit. It corresponds to plan work package **E1**.

## 1. Objective

Every pull request to `m2/continuation` automatically runs the existing Python regression suites. The run fails on any deviation from the declared baseline, and never reports a suite that it could not run as passed.

This is **level 2 (regression validation) infrastructure only**. It produces no scientific evidence and changes no existing file.

## 2. Authorisation boundary

| Authorised | **Not authorised** for this task |
|---|---|
| **One new file:** `.github/workflows/tier0-python.yml` | Any helper script or other new file. A helper requires separate approval. |
| A GitHub-hosted runner | A self-hosted runner of any kind |
| Public checkout of `https://github.com/Unipisa/Simu5G` at `v1.8.1` | A full-stack build (OMNeT++, INET or a Simu5G build) |
| — | Any simulation |
| — | Secrets; private evidence or the private repository |
| — | Changes to any existing file, test, checker, record, fixture or configuration |
| — | Changes to `master`; tags; force-push |

## 3. Starting point (precondition checks, recorded in the pull request)

1. The base is **the approved post-E0 integration commit**: the tip of `m2/continuation` after the E0 documentation-only commit has been reviewed and pushed.
2. Verify that `033c3ed3fbc5b6ee21271ce24c62084283d8e79b` is an ancestor of that base: `git merge-base --is-ancestor 033c3ed <base>`.
3. Verify that the changes between them are documentation-only:
   - `git diff --name-status 033c3ed <base>` lists only added files under `docs/migration/` and the added `simulations/m2/plans/M2-S7.2a-stage5-plan-1.8.1.md`;
   - no `M`, `D` or `R` entries.

   If anything else appears, stop.
4. Work on the isolated feature branch `ci/tier0-python`, created from that base. Only the maintainer merges, and only after review.

## 4. Workflow specification

| Item | Requirement |
|---|---|
| Trigger | `pull_request` with `branches: [m2/continuation]` only. No `workflow_dispatch`: it cannot be relied on while the workflow is absent from the default branch, and `master` is not modified. No `pull_request_target`, no `push` trigger. |
| Permissions | Top-level `permissions: contents: read`. No secrets referenced. |
| Action pinning | Every `uses:` is pinned to a **full 40-character commit SHA**, with the release tag as a trailing comment (`actions/checkout`, `actions/setup-python`). The SHAs are resolved at implementation time from the official action repositories and listed in the pull request. |
| Checkout | `persist-credentials: false`. `fetch-depth: 0` (full history): the A-2.1 test T-frozen-untouched compares against `fbee202` and `39a6434`. |
| Runner and Python | GitHub-hosted `ubuntu-22.04`; Python 3.13 (reference 3.13.13). The image version and the exact Python version are printed in the job summary. |
| Simu5G sources | `git clone --branch v1.8.1 --depth 1 https://github.com/Unipisa/Simu5G "$RUNNER_TEMP/simu5g-1.8.1"` (the official upstream URL). **Fail-closed gate:** `git -C … rev-parse HEAD` must equal `7477d2663644bbf78604267cba4fc113b4871ede`. Export `SIMU5G_ROOT`. No build. |
| Fixture gate | `sha256sum simulations/m2/check/fixtures/a2v1-first-chain.log.gz` must equal the **independently recorded full value** `cfb05ff78e63e056f512bdea9fdc568d555dba71ffd884675fc46f905bc6e65b`, which is written into the workflow. This is checked in addition to, not instead of, the accompanying `.sha256` file. |
| Suites | One step per suite, from `simulations/m2/check/`, with `python3 -B`. Each step must pass all three checks:<br>(a) the process exit code is 0;<br>(b) the suite's final summary line equals the expected line of §5 **exactly**;<br>(c) every non-success count in that line is zero.<br>Lines such as `0 FAIL` or `0 PENDING` are valid. A line is rejected only if it differs from the expectation, or if a FAIL, PENDING or NOT-RUN count is non-zero. |
| Not run in tier 0 | `test_m2s72a2v1_wrapper.py` (needs a real `opp_run`: tier 1) and `test_m2s72_compare.py` (needs a census run directory). Both are listed in the summary as **NOT RUN (reason)**, never as passed and never silently omitted. |
| Summary | Base and head SHAs; runner image; Python version; Simu5G commit; the fixture gate result; per suite the exit code, summary line and duration; the NOT RUN list; the statement "Tier 0 — regression validation only (level 2); not scientific evidence". |
| Time limit | `timeout-minutes: 30`. The local measurement was about 3.5 min. |

## 5. Expected results (declared before the first run)

These were measured locally on 17 Nov. The fixture-dependent line is the result of the independent VM run of 17 Nov.

| Suite | Expected final line |
|---|---|
| `test_m2s72_a2.py` | `A-2 tests: 18 / 18 PASS` |
| `test_m2s72_a2probe.py` | `A-2 probe tests: 11 / 11 PASS` |
| `test_m2s72_a2v1.py` | `10 / 10 PASS` |
| `test_m2s72_gen.py` | `generator negative tests: 67 PASS, 0 FAIL` |
| `test_m2s72s5.py` | `S5-1 tests: 38 / 38 PASS` |
| `test_m2s72s5_2.py` | `S5-2 tests: 28 / 28 PASS` |
| `test_m2s72s5_n2.py` | `S5 N = 2 tests: 19 / 19 PASS` |
| `test_m2s72s5_smoke.py` | `S5 smoke contract tests: 9 / 9 PASS` |
| `test_m2s72_a21.py` | `A-2.1 tests: 18 / 18 PASS, 0 PENDING, 0 FAIL` (T-real-first-chain must PASS with the fixture present) |
| `test_m2s72_a21_fixture.py` | `A-2.1 fixture-extractor tests: 14 / 14 PASS, 0 FAIL` |

If a suite does not produce its expected line on the hosted runner (for example through an undeclared dependency on a local path or an OMNeT++ installation):
- the run fails, and the finding is reported in the pull request with the log;
- **neither the test nor the expected line is changed** to make CI pass;
- reclassifying a suite as "tier 1 / NOT RUN" requires the maintainer's approval.

## 6. Acceptance criteria (level 2; decided by the maintainer's review)

| ID | Criterion |
|---|---|
| H4-1 | §3 precondition checks recorded. `git diff --name-status <base>...ci/tier0-python` shows exactly one `A` entry: `.github/workflows/tier0-python.yml`. |
| H4-2 | The pull request from `ci/tier0-python` to `m2/continuation` has a green run whose summary shows:<br>• every §5 line exactly, with exit code 0;<br>• the two NOT RUN entries with their reasons;<br>• the fixture gate;<br>• the Simu5G commit gate. |
| H4-3 | **Negative control NC-H4-fixture.** An isolated branch from `ci/tier0-python` changes one byte of the fixture. It is opened as a draft pull request to `m2/continuation`, **never merged**, and closed after the run. **Intended failure:** the fixture gate step fails on the full-SHA mismatch. Record the branch name, head SHA, run ID and the failing step's message. |
| H4-4 | **Negative control NC-H4-simu5g.** An isolated branch changes the expected Simu5G commit in the workflow to a wrong value. Same procedure. **Intended failure:** the Simu5G identity gate fails before any suite runs. Same record. |
| H4-5 | Each negative control failed **for its intended reason**. A failure at a different step does not count as a demonstration. |
| H4-6 | Workflow audit: every `uses:` is pinned to a full SHA; `persist-credentials: false`; `permissions: contents: read`; no secrets, no `pull_request_target`, no `workflow_dispatch`, no self-hosted runner |
| H4-7 | The measured duration is recorded (feasibility F-1) |

**The negative-control branches are never merged and are deleted only after their run records are captured in the H4 pull request.** Branch deletion is the maintainer's decision.

**Not claimed:** any build, configuration validity, simulation behaviour or scientific result.

## 7. Stop conditions

- An existing file would need to change.
- A second new file would be needed.
- The §3 precondition checks fail.
- A suite fails on the baseline for a reason other than an environment difference (report it; do not fix it in this task).
- Any need for secrets, private access, a full-stack build or a self-hosted runner.

## 8. Next tasks after H4 (backlog order)

*[Superseded (rev. 4): this list is historical; E2 is done and A1 is next.]*

1. Plan E2: tier-1 feasibility, from the preserved `opp_env` / Nix environment (publication of the configuration only after content review).
2. A1: A-2.1 integration into E0v-N.
3. B1 / B2 / D1: designs.
