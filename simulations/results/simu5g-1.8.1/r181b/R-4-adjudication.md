# M2-R181b: R-4 legacy-identity adjudication

**Reviewer decision, 2026-11-12:**
- The three documented differences are conditionally accepted as historical or non-semantic exceptions, subject to evidence that the new runner implementation does not cause them.
- **The original R-4 verdict is kept: FAIL (3 files).**
- No identity criterion is relaxed; this record adjudicates exactly these three files.

**Original result:** `g0-legacy/identity.txt`, produced by `g0_identity.sh` on the legacy-mode G0 proof at `cfc2d39`, Simu5G 1.8.0.

| Class | Files |
|---|---|
| IDENTICAL | 209 |
| METADATA | 15 |
| RUNHEADER | 6 |
| DIFFERS / MISSING | 3 |

**Script verdict: R-4 FAIL (3 files).** Every checker output was byte-identical.

## Evidence that the runner change (`cfc2d39`) does not cause them

**1. Rerun at the pre-isolation commit `14d5e0f`** (git worktree, legacy mode, Simu5G 1.8.0, 2026-11-12).
- I reran `m1/s0_vanilla_reference.sh` and `m1/o_tail_investigation.sh`; both exited rc=0.
- Results:
  - `O-tail/raw-outputs.sha256` was **deleted** (`git status`: ` D`).
  - `S0/fingerprints.log` differs **only** in the unittest wall-clock line (`Ran 4 tests in 3.007s` → `3.518s`).
  - `O-tail/check.txt` and `S0/check.txt` are byte-identical to the commit.
- So both differences occur without the runner change.

**2. Code.**
- `git diff 14d5e0f cfc2d39` of the two runners and of `m2s5.sh` adds only the following, and changes no other line:
  - `source nt_results.sh; nt_results_init`;
  - `OUT=$RESULTS/...` in place of `$HERE/results/...`;
  - `nt_fresh_out` and `nt_stack_record`, which are no-ops in legacy mode.
- `git grep check_txt 14d5e0f -- simulations/` matches only the committed record `M2-S5/env.txt` itself; no runner writes that line, at either commit.
- `git grep raw-outputs.sha256 14d5e0f -- simulations/m1/o_tail_investigation.sh` finds nothing: the O-tail runner never writes that file. It starts with `rm -rf "$OUT"`, and this line is unchanged in `cfc2d39`.

## Adjudication per file

| File | Exact difference | Provenance | Permitted non-semantic exception? | Reproducible output or checker result changed? |
|---|---|---|---|---|
| `simulations/m1/results/O-tail/raw-outputs.sha256` | MISSING after the rerun | Committed in `4519b21` (2026-10-13, "O-S4-1 and O-S3-2 explained") alongside the runner's records; no runner writes it, and the runner deletes `results/O-tail` at start. **Reproduced at `14d5e0f`**; already recorded as pre-existing in the M2-S5 results §7 | **Yes, historical.** It holds .sca/.vci/.vec hashes only, which embed run ids and dates, so they are never byte-reproducible | **No.** `O-tail/check.txt` is IDENTICAL at `cfc2d39` and at `14d5e0f`. The file is unaffected in content; it is removed by a pre-existing runner behaviour |
| `simulations/m1/results/S0/fingerprints.log` | One line: `Ran 4 tests in 3.007s` → `2.806s` (and → `3.518s` at `14d5e0f`) | Python unittest's wall-clock report; the four fingerprint lines (`... OK`) are unchanged. Recorded as pre-existing in the M2-S5 results §7 (3.007 → 3.009 s) | **Yes, non-semantic.** Host wall-clock time, not simulation output | **No.** The 4/4 upstream fingerprints are OK and identical; `S0/check.txt` is IDENTICAL |
| `simulations/m2/results/M2-S5/env.txt` | One line present only in the commit: `check_txt: check_m2s5.py at 8bcfc14 (output-order fix only) rerun on these raw outputs; identical under PYTHONHASHSEED 1 and 2`. All other differing lines are the tolerated metadata keys | A hand-written annotation committed in `5b4676e` (2026-10-16, M2-S5 results) to document the checker rerun; no runner writes it (`git grep`, above) | **Yes, historical.** It is environment metadata of the record, not output. `g0_identity.sh` tolerates only listed metadata keys, so it flags the line | **No.** `M2-S5/check.txt` and every M2-S5 gate, report and stage file are IDENTICAL; `raw-outputs.sha256` differs only in .sca/.vec lines (RUNHEADER) |

## Conclusion

- **R-4 script verdict: FAIL (3 files), kept.**
- **Adjudication:**
  - All three differences are historical or non-semantic exceptions.
  - None is caused by the runner change: two are reproduced at `14d5e0f`, and the third is a line no runner writes.
  - No reproducible output and no checker result changed.
- **No change to `g0_identity.sh` or to the identity rule.**
