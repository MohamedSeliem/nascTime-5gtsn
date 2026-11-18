# Tier-1 full-stack CI

Tier-1 builds the pinned simulation stack on a standard GitHub-hosted runner and checks that nascTime builds, links and
answers real OMNeT++ configuration queries against it. It is **level-2 validation infrastructure only**:

| Tier | What it shows | Where |
|---|---|---|
| 0 | Python regression suites (no build) | `.github/workflows/tier0-python.yml` |
| **1** | **Release build, linkage, single C++ runtime, real configuration queries, synthetic wrapper lifecycle tests** | **this directory** |
| 2 | Functional simulation | not automated |
| 3 | Scientific acceptance | never CI |

Tier-1 never runs a simulation, a smoke test or a fingerprint test, and it produces **no scientific evidence**. It is not
a required check.

## Pinned inputs

All pins are in [`pins.env`](pins.env); changing one requires maintainer review.

- Nix 2.34.4 (installer and tarball sha256), `require-sigs = true`
- opp_env 0.36.2.261110 (PyPI wheel sha256, main-module sha256, no dependencies, private virtual environment)
- the approved 26.05 lock [`flake.lock`](flake.lock) (sha256 `9ead1465…`, byte-identical to the preserved VM lock) and
  the opp_env 22.11 helper lock (sha256 `0fc40c96…`); both are made immutable in the workspace
- OMNeT++ 6.5.0, INET 4.7.0, Simu5G 1.8.1, release-asset sha256 measured in E2b
- toolchain Clang 21.1.8, GCC 15.2.0, GNU Make 4.2.1, Python 3.13.13; the 11 reference `WITH_*` values
- `VM_SYS_LIBS`, the SYS_LIBS line recovered from the VM's OMNeT++ 6.5.0 `Makefile.inc`

**Known, deliberate differences from the VM:** the runner OS image, release-only builds, and (case A below) the removal of
the runner's host libc++ development packages.

## The host libc++ incompatibility and its correction (C-4)

E2b.2 failed: OMNeT++'s configure tries `-lc++` before `-lstdc++`. The Nix clang wrapper still searches the host
library directories, and the GitHub `ubuntu-22.04` image ships `libc++-14-dev`. So `SYS_LIBS` selected the host libc++,
and the libraries then could not resolve `libc++.so.1` at run time. Two experiments verified the correction:

- E2b.3 established the cause;
- E2b.3-R1 established the corrected causal chain and produced a PASS (run 44207656877).

Tier-1 first runs a minimal in-session link probe. The probe binaries are only listed by the loader, never executed.
The outcome decides what happens next:

- **Case A, `-lc++` links (contaminated host).**
  1. The provenance gate (`py/provenance.py`) must prove five things:
     - the libc++ selected by the linker trace is a host library outside `/nix/store`;
     - the unversioned linker entry was found by replaying the driver's `-L` order;
     - that entry leads to the selected library, by symlink chain or linker-script `INPUT`;
     - its dpkg ownership, checked under both merged-`/usr` spellings;
     - runtime and development owners are kept separate.
  2. Only the verified libc++/libc++abi development packages, plus the installed `libc++-dev`/`libc++abi-dev`
     metapackages, may be removed. The simulated apt transaction is inspected first. There is no autoremove and no
     purge, and the dpkg inventory may change by exactly that set.
- **Case B, `-lc++` already fails with exactly `unable to find library -lc++` (clean host).** Nothing is removed.
- **Anything else fails closed.** Examples: libc++ found in `/nix/store`, or a different link error.

In both cases the negative control must then fail for exactly that reason. The default and `-lstdc++` positive controls
must resolve libstdc++, and every other library, from the pinned store. C-5 then compares the OMNeT++ `SYS_LIBS` with
`VM_SYS_LIBS` as an ordered token sequence (whitespace collapsed). `-lstdc++` must be present and `-lc++` absent.

## Triggering

- **Event:** `pull_request` targeting `m2/continuation` (opened, synchronize, reopened, ready_for_review, labeled).
- **Selection:** `py/decide.py` reads the PR's **complete** change set (`git diff --name-status -M -C base...head`): added,
  modified and deleted files, and both sides of renames and copies. Tier-1 runs if any relevant path is touched:
  - `src/**`
  - `simulations/**/*.ned` and `simulations/**/*.ini`
  - `simulations/m2/m2s72a2v1.sh`
  - `simulations/m2/check/**`
  - `Makefile`
  - `ci/tier1/**`
  - the workflow file
- **Fails closed:** if the change set cannot be determined, the job **fails**; it is never silently skipped.
- **Drafts** are skipped unless labelled.
- **Override:** a collaborator with triage rights or higher adds the label **`tier1:run`**. Adding any other label never
  starts a run. Unselected events use a unique concurrency group, so they cannot cancel a running job. A new push to the
  PR cancels the superseded run.
- **Manual re-runs** ("Re-run all jobs") are allowed and recorded as the run attempt. A failure is investigated, never
  re-run until it passes.
- **Not used:** `workflow_dispatch` is omitted, because its UI needs the workflow on the default branch (`master`, frozen).
  There is also no `pull_request_target`, no `schedule` and no `push` trigger.

Every run records the PR head SHA, the base SHA and the tested merge commit (`identity.txt`). It verifies that the
checked-out commit is `GITHUB_SHA` and that its second parent is the PR head.

## Security model and its limits (C3)

- **Workflow settings:**
  - `permissions: contents: read`;
  - `persist-credentials: false` on every checkout;
  - actions pinned by commit SHA;
  - no secrets, no caches, no private repositories and no persistent resources;
  - standard ephemeral `ubuntu-22.04` runners;
  - artifacts are screened text only, kept for 7 days.
- **PR-controlled code runs with `sudo`.** The scripts in this directory come from the PR under test and run on the
  runner with passwordless `sudo`: they remove packages, install Nix and set file attributes. A PR can therefore change
  what tier-1 does. That is acceptable only because the runner is disposable, isolated and holds nothing of value.
- **Tier-1 cannot vouch for a PR.** A PASS on a PR that modifies `ci/tier1/**` validates that PR's own version of tier-1.
- **Outside contributors:** a full run costs about 40–60 runner minutes. Repository administrators should consider
  "Require approval for all outside collaborators" (Settings → Actions). Tier-1 does not change repository settings.

## The wrapper regression suite and the simulator audit (C-13; C1, C2)

`wrapper/run-suite.sh` runs the existing, unchanged `simulations/m2/check/test_m2s72a2v1_wrapper.py` inside the opp_env
session. `SIMU5G_ROOT` is the compiled Simu5G tree.

**The audit shim.** The suite reaches the real OMNeT++ only through `wrapper/opp_run-audit.sh`, installed as
`opp_run` behind an audit `setenv`. The shim forwards only these argument vectors, exactly:

- `-u Cmdenv -f m2s72s5.ini -c M2S72-E0vN-q0-one0-n2-f1 -r 0 -q runconfig`
- `-u Cmdenv -f m2s72a2v.ini -c M2S72-E0vN-q0-one0-n2-f1_A2V1 -r 0 -q runconfig`
- `-v`

Before forwarding, it checks four things:

- **Working directory:** the call comes from the repository's `simulations/m2` or from `simulations/m2` of a suite clone
  directly under the suite's private temporary directory.
- **Binary:** it calls the real binary by its verified absolute path, whose sha256 must equal the binary validated by C-10.
- **Library-search hazards:**
  - no shared library may be reachable through a relative RUNPATH entry (`.`) in the actual working directory;
  - absent RUNPATH directories must still be absent;
  - the loader must resolve `opp_run` only from `/nix/store` and the OMNeT++ library directory.
- **Refusals:** anything else is refused with exit 97.

Every call is logged with its arguments, actual working directory and exit status (`opp_run-audit.tsv`).

**The shim is a regression safeguard, not a security boundary.** The suite and the shim are PR-controlled code.

**Pass requires all of the following:**

- exit 0;
- the exact line `A2-V1 wrapper tests: 21 / 21 PASS`;
- 21 PASS lines and no FAIL line;
- the audit shows the expected real queries and no refused call;
- no results root reachable;
- no tracked repository modification, and no new untracked file.

New *ignored* files are recorded but allowed.

**Evidence class:** real configuration queries plus synthetic lifecycle tests (stub simulator, synthetic evaluation).
These are not simulation results.

**If a real configuration query fails** because of a VM-specific NED/INI difference, the verdict is
**TIER-1 BLOCKED (F-8)**. No configuration is patched and no test is weakened. If the A2-0s/G0-source check fails, the
discrepancy between the release tree and the reviewed source is reported. Tier-1 does not substitute a git checkout.

## Acceptance (C-1 … C-15) and verdicts

| ID | Gate |
|---|---|
| C-1 | Pins and identity: Nix, opp_env, lock content, release assets, toolchain, `configure.user` |
| C-2 | Lock integrity: both locks unchanged and immutable at every gate; metadata with updates forbidden; admin files |
| C-3 | Source integrity: manifest `sha1sum -c`, recipe-consistency screening, classification of build-induced changes, clean nascTime tree |
| C-4 | Host C++ runtime: case A or case B, as above |
| C-5 | SYS_LIBS ordered tokens equal to `VM_SYS_LIBS` |
| C-6 … C-9 | Release builds of OMNeT++, INET, Simu5G and `libnasctime_m2` |
| C-10 | 22 binaries and libraries (size, sha256, ELF metadata, no debug outputs); `opp_run -v` exits 0 and reports 6.5.0 |
| C-11 | No unresolved dynamic dependency (18 ELF files) |
| C-12 | Single C++ runtime; every library resolves from `/nix/store` or the project trees; RUNPATH classes; controlled working directory |
| C-13 | Wrapper suite 21/21 with the strict audit |
| C-14 | Execution control: guard healthy, no STOP, time budget held, declared stages only, no simulation markers, release only; resources recorded |
| C-15 | Diagnostic evidence complete, screened and prepared for publication |

**Row results:** each row is **PASS**, **FAIL** or **NOT EVALUATED**. NOT EVALUATED means a prerequisite did not run; it
is never a PASS.

**Verdicts:**

- **TIER-1 PASS** requires all 15 rows to be PASS.
- **TIER-1 FAIL** covers any other failed or unevaluated row.
- **STOP:** the disk guard or a disk gate stopped the run.
- **INFRASTRUCTURE FAILURE:** the guard was not healthy.
- **TIER-1 BLOCKED:** see the wrapper section above.

**Job outcome:** the job succeeds only with TIER-1 PASS *and* a successfully uploaded artifact.

The verdict table is in the job summary and in `verdict.md` inside the artifact `tier1-diagnostics-pr<N>-run<id>-<attempt>`.

## Runtime and resources

These figures were measured in E2b.3-R1 on a standard 4-CPU / 16 GB runner.

| Measure | E2b.3-R1 |
|---|---|
| Whole job | 34 min |
| OMNeT++ build | 388 s |
| INET build | 1112 s |
| Simu5G build | 313 s |
| `libnasctime_m2` build | 22 s |
| Peak disk use | 11.0 GB, about 77 GB of headroom |
| Minimum available memory | 14.2 GB |

The wrapper suite had not been measured on a hosted runner before tier-1. The expected total is 40–60 minutes.

**Limits:**

- the job is capped at 120 minutes;
- every guarded stage has its own cap (`CAP_*` in `pins.env`);
- 10 minutes are always kept for evaluation and publication;
- a disk gate requires at least 10 GiB free before each stage, and the guard declares STOP below 4 GiB.

## Execution safety and RUNPATH (C2)

The released ELF files carry these non-store RUNPATH entries:

- `.` (relative);
- the Nix shell's `<cwd>/outputs/out/lib` (absent);
- `$OMNETPP_ROOT/tools/linux.x86_64/lib` (absent);
- the project library directories.

Their origin is recorded but not established, and the build machinery is not modified. Tier-1 controls them in three ways:

- **One empty starting directory.** Every opp_env session starts in a single, initially empty directory (`$CI/exec`).
  Before and after each session, that directory must still be empty, and the absent RUNPATH directories must still be
  absent.
- **Classification in C-12.** Validation classifies every non-store RUNPATH entry as `project`, `relative`, `absent` or
  `UNEXPECTED`. An existing absolute directory that is neither store nor project is **UNEXPECTED**, and that fails C-12.
- **Per-call inspection.** The audit shim re-inspects the actual working directory before every real query.

## Self-tests

```bash
python3 -I ci/tier1/tests/test_tier1.py               # offline; about 3–5 minutes; also the workflow's selftest job
python3 -I ci/tier1/tests/test_tier1.py --host-probe  # plus the in-session link probe on this host
```

**What the tests exercise:** the production scripts and modules against synthetic sandboxes. They use mocked
filesystems and dpkg databases through dependency injection, and shims for apt, dpkg-query and sudo.

**What production refuses:** every test or mocking variable, including `TIER1_TEST_*`, `E2B3_TEST_*`, `A2V1_TEST_*`,
`A2V1_STUB_*`, `A2V1_RESULTS_ROOT` and `A2V1_COMMIT`. It exits 3 before doing anything.

**The fixture:** `tests/fixtures/e2b3-runtime-probe-before.txt` is real hosted evidence (see its README).

## Limitations

- No VM byte-equivalence. Only SYS_LIBS is compared with the VM; the VM's ELF dependency records and apt inventory are
  unavailable.
- **Release-asset checksums** come from a separate streamed fetch. They detect an upstream re-upload but do not prove the
  bytes opp_env consumed (it streams `curl | tar`).
- **Source equivalence with E2b.3-R1 is not evaluated.** Tier-1 records the opp_env manifest hashes but has no pinned
  reference manifest.
- **Adaptation screening** shows recipe consistency, not exact transformation equivalence.
- **Lock updates:** opp_env's `nix develop` cannot be given `--no-update-lock-file`. An in-process lock update is detected
  and its write blocked, but it is not proven impossible.
- **Runner-image drift** is expected. Case B already covers a host without libc++. Any other new host contamination fails
  closed.
- The origin of the `.` and `tools/linux.x86_64/lib` RUNPATH entries is not established.
- The wrapper suite's lifecycle tests are synthetic, and its source-text check reads the release tree.
- **Licensing:** the OMNeT++ commercial-licensing clarification is outstanding. This infrastructure serves academic
  research only.
