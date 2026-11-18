# Tier-2 hosted functional experiments E3a and E3b

The tier-2 code in `ci/tier2/` is shared by two **one-time experiments**. `T2_EXPERIMENT` selects one; it defaults to
`e3a`, and any other value is refused.

| | E3a (accepted) | E3b |
|---|---|---|
| Branch (never merged) | `wp-e3/e3a-m2s4u-smoke` | `wp-e3/e3b-m2s5-bridge`, branched from the accepted E3a commit `f2215ad` |
| Workflow | `e3a-functional-smoke.yml` (frozen: the E3b commit may not touch it, and its push trigger only fires on the E3a branch) | `e3b-bridge-functional.yml` |
| Pins | `pins-tier2.env` | `pins-e3b.env` |
| Configuration | `M2S4U` (network `M2S4LinkTest`, 3 s) | `M2S5` (network `nasctime.simulations.m1.M1Bridge`, 5 s) |
| Reviewed command | `simulations/m2/m2s4.sh` `run()` | `simulations/m2/m2s5.sh` `run()` |
| Oracle (E-6) | U1 of `check_m2s4.py` (`py/u1_oracle.py`) | `check_m2s5.rows_5gs(Run(RUNS, "M2S5", 0), None, exp_missing=0)` (`py/m2s5_oracle.py`) |
| E-9 reference (informational) | four OMNeT++ 6.4.0 hashes | the 35 R181c (Simu5G 1.8.1) run-0 hashes, `ref-e3b-r181c-run0.sha256` |

Each experiment authorises exactly one configuration, fixed in `session/run-sim.sh` and `steps/sim.sh`; the evaluator and
the raw publisher check it again. E3b therefore refuses `M2S4U`, `M2S5-frag` or any other configuration.

## E3b in brief

**Evidence class:** level-2 hosted functional smoke evidence for the **downlink 5G–TSN timing path**. It is not scientific
validation and not a full M2-S5 campaign result; uplink is outside its scope.

**The single simulation** (run 0 of `--repeat=10`, seed-set 0):

```bash
cd "$REPO/simulations/m2" && "$OMNETPP_ROOT/bin/opp_run" -l "$REPO/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
  -n "$REPO/simulations:$REPO/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
  -u Cmdenv -f omnetpp.ini -c M2S5 --repeat=10 -r 0 --result-dir="$RAW/runs/M2S5" --cmdenv-express-mode=true
```

The pre-flight `-q runconfig` dump must show exactly `Run 0: $repetition=0`, network `nasctime.simulations.m1.M1Bridge`,
`sim-time-limit = 5s` and `seed-set = 0`. The run must produce exactly 36 non-empty files: the 35 names of the R181c
reference plus `M2S5/M2S5/0.vci` (9 PCAP files, 24 CSV logs, `.sca`, `.vec`, `.vci`).

**Oracle (E-6).** The adapter imports the unmodified `check_m2s5.py` and its full import chain offline. It replaces
`main()` with a trap, gives `"-"` for the M2-S4 baseline arguments (never used, because `R4` is `None`) and calls only
`rows_5gs`. An audit hook fails the oracle if any file outside the raw directory, the checker directory or the Python
runtime is opened, so no historical or private result can be read.
- **Fully evaluated:** C1–C7, S1, S2, P2 (integer picoseconds).
- **Partially evaluated:** C8 (slave audit `framesWithSyncTag = 0`) and P1 (NW-TT D = 50 000 ps from PCAP). Their M2-S4
  baseline comparisons are **NOT EVALUATED**. P1's printed text "engine log byte-identical to M2S4: False" means NOT
  EVALUATED here.
- **NOT EVALUATED:** S3, which needs the M2S4 baseline run.
- **Counts recorded:** Syncs and Follow_Ups at the GM, the slave and on N3; NW-TT link-delay exchanges; slave Pdelay and
  clock samples; model steps.

**Monitoring.** There is an immediate initial measurement after the start, then a sample every second while the process
is alive, then a final measurement.
- The initial and final values must both be numeric.
- A failed or non-numeric measurement while the process is alive terminates it as a monitoring failure. A failure after
  it ended is noted but does not terminate anything.
- Maxima that were never sampled are reported `NOT MEASURED`, never 0.
- The limits are the same as E3a (below).

**N3 capture.** `M1Bridge.upf.pcapRecorder[0]` records UPF `ppp[0]`. The raw publisher accepts it only as PPP (link type
9, 50 or 204), decoded exactly as `check_m2s5.n3_inner` does:
- PPP framing: one prefix byte, optional `ff03`, protocol `0x0021` only;
- IPv4: valid header, consistent length, at most 3 trailing bytes;
- addresses: source and destination in 10.0.0.0/8, the configurator's gNB/UPF range `10.x.x.x/24`;
- fragments must reassemble completely;
- UDP: consistent length, port 2152 or 31;
- GTP-U: version 1 G-PDU, consistent length, bounded extension chain;
- the inner Ethernet frame must meet the MAC policy;
- the extracted strings are screened.

Every other PCAP file must be Ethernet. Anything unexpected fails closed, and the outputs are never rewritten.

**Verdicts** (both experiments, in order of precedence):
- `STOP`;
- `INFRASTRUCTURE FAILURE`;
- `<X> BLOCKED`, for compatibility, quoting the diagnostic;
- `<X> PUBLICATION FAILURE`, when E-1 to E-7 PASS but E-8 does not;
- `<X> FAIL`, a functional failure;
- `<X> PASS`.

The job succeeds only with `<X> PASS` and both uploads.

**Artifacts:** `e3b-diagnostics-run<id>-1` and `e3b-raw-m2s5-run<id>-1`, each kept for 7 days.

---

The rest of this file describes the accepted E3a experiment. Its sections apply to E3b with the substitutions in the
table above.

## E3a: hosted functional smoke run of M2S4U

E3a is a **one-time experiment**. It is authorised for branch `wp-e3/e3a-m2s4u-smoke` only, which is never merged. Its
workflow is `.github/workflows/e3a-functional-smoke.yml`.

It runs exactly **one** simulation of the existing reviewed configuration `M2S4U` on a standard GitHub-hosted runner,
using the integrated tier-1 stack. That configuration is in `simulations/m2/omnetpp.ini`, and its network is
`simulations/m2/M2S4LinkTest.ned`.

**Evidence class:** functional smoke evidence (level 2). The scenario initialises, executes, completes and meets its
reviewed unit oracle. It is **not** independent scientific validation: a CI run started by the development agent is never
level-3 evidence. It is unrelated to the A2-V1 campaign, and it reads no private evidence, VM results root or archived
campaign outputs.

### What it reuses and what it adds

**Reused, not modified:** the integrated tier-1 steps.
- `setup`, `bootstrap`, `verify` and `runtime`;
- the four release builds;
- `validate`, `srcchanges`, `lockend`, `measure`, `evaluate` and `publish`;
- `ci/tier1/lib/*`, including test-override refusal, guarded sessions, the disk guard, lock gates and screening.

Tier-1's rows **C-1 … C-12** are E3a prerequisites. Tier-1's **C-14 forbids any simulation**, and E3a does not use it.
The separate tier-2 evaluator does not weaken or bypass it.

**Added (`ci/tier2/`):**
- **Identity check:** `py/identity.py`.
- **In-session runner:** `session/run-sim.sh`, which runs the pre-flight `runconfig` query and the single simulation with
  its watchdog.
- **Evidence sealing:** `py/seal.py`.
- **U1 oracle adapter:** `py/u1_oracle.py`.
- **Raw-evidence publication checks:** `py/rawpub.py`.
- **Evaluator and verdict:** `py/evaluate_t2.py` and `py/final_t2.py`.
- **Offline tests:** `tests/`.

### The single authorised simulation

The command is that of the reviewed `simulations/m2/m2s4.sh` `run()` (lines 39–43), for configuration `M2S4U`, run 0. It
is fixed in `session/run-sim.sh`, and nothing can be passed in to change it:

```bash
cd "$REPO/simulations/m2" && "$OMNETPP_ROOT/bin/opp_run" -l "$REPO/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g" \
  -n "$REPO/simulations:$REPO/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes \
  -u Cmdenv -f omnetpp.ini -c M2S4U --repeat=10 -r 0 --result-dir="$RAW/runs/M2S4U" --cmdenv-express-mode=true
```

**Pre-flight.** The approved pre-flight query is the same vector with `-q runconfig` in place of the last two arguments.
Its dump must show exactly one run, `Run 0: $repetition=0`, which proves that `--repeat=10 -r 0` selects one run. It must
also show:
- `network = …M2S4LinkTest`
- `sim-time-limit = 3s`
- `seed-set = 0`

The configuration, seed, duration, logging and recording are unchanged.

**Loader record.** The simulator runs with `LD_DEBUG=files`, written to a records file. This records the identity of every
object it loads. It does not change its arguments or behaviour.

**Limits** (1 MB = 1 000 000 bytes; sizes are apparent sizes):

| Limit | Value |
|---|---|
| Job | 120 min |
| Simulation wall time | 600 s |
| Watchdog emergency limit | 500 000 000 B |
| Acceptance limit | 200 000 000 B |
| Disk and time budget | tier-1 controls (start gate, 4 GiB STOP, guarded stage caps) |

**Watchdog.** It samples once per second. It terminates the simulator and all of its descendants (TERM, then KILL) in any
of these cases:
- a size measurement fails or is non-numeric;
- the output exceeds the emergency limit;
- the wall-time cap is exceeded;
- STOP is declared.

The evidence written up to that point is kept, and nothing is retried. If monitoring itself is lost, the opp_env session
ends, and tier-1's guarded runner kills the whole process group.

**Duplicate starts.** A second start is refused, by an atomic start marker and by refusing an existing output directory.

### Acceptance (defined before the hosted run)

E3a PASS requires every mandatory row, E-1 to E-8, to PASS. E-9 is informational. Each row is PASS, FAIL or NOT
EVALUATED, and NOT EVALUATED is never PASS.

| ID | Mandatory | Criterion |
|---|---|---|
| E-1 | yes | Authorised trigger and commit, and the tier-1 prerequisites. See below. |
| E-2 | yes | Configuration, run and binary identity. See below. |
| E-3 | yes | Exactly one simulation, with healthy execution control. See below. |
| E-4 | yes | Completion within the approved limits. See below. |
| E-5 | yes | Complete result files. See below. |
| E-6 | yes | The **unmodified U1 oracle** of `simulations/m2/check/check_m2s4.py`. See below. |
| E-7 | yes | No repository or upstream change. See below. |
| E-8 | yes | Evidence sealed and published. See below. |
| E-9 | no | Historical OMNeT++ 6.4.0 reference hashes. See below. |

**E-1, authorised trigger and commit:**
- the trigger is a push of `wp-e3/e3a-m2s4u-smoke`, run attempt 1;
- `HEAD` equals `GITHUB_SHA`;
- `HEAD^` is the baseline `290babba3d12942344a2153f9ea5ea54287df366`;
- the commit only adds new files under the workflow file and `ci/tier2/`;
- tier-1 C-1 … C-12 are all PASS.

**E-2, configuration, run and binary identity:**
- the pre-flight exits 0, and the effective configuration is as above (its sha256 is recorded);
- the recorded argument vectors equal the reviewed ones;
- the running process's own argument vector (`/proc/<pid>/cmdline`) equals the reviewed one;
- its working directory (`/proc/<pid>/cwd`) is `simulations/m2`;
- `opp_run`, `libnasctime_m2.so`, `libsimu5g.so` and `libINET.so` equal the binaries validated by C-10 (sha256);
- every loaded object comes from `/nix/store` or the project library directories;
- no RUNPATH or working-directory hazard exists. Relative entries may not resolve a shared library in the actual working
  directory, and absent entries must stay absent.

**E-3, exactly one simulation and healthy execution control:**
- there is one start record;
- the log has exactly one `Preparing for running configuration M2S4U, run #0...`;
- there are no outputs of another run;
- there is exactly one `t2-runconfig` stage and one `t2-sim` stage, and no undeclared stage;
- the guard was healthy and terminated, no STOP was declared, and the time budget was not breached;
- no simulation marker appears in any other log;
- tier-1's controlled-directory checks pass.

**E-4, completion within the approved limits:**
- the simulator and the guarded stage exit 0;
- the log contains `<!> Simulation time limit reached -- at t=3s` and `Calling finish() at end of Run #0...`, and its last
  line is `End.`;
- the log has no error and no fingerprint line;
- wall time is at most 600 s;
- the watchdog was never triggered, its measurements were numeric, and the output stayed at or below 500 000 000 B.

**E-5, complete result files:**
- exactly 7 non-empty files: `M2S4U/0.sca`, `0.vec` and `0.vci`; two engine CSV logs; two PCAP files;
- the scalar file shows `configname M2S4U`, `repetition 0`, `seedset 0` and network `M2S4LinkTest`;
- total at most 200 000 000 B.

**E-6, the unmodified U1 oracle:**
- **How it is called:** `eval_unit("M2S4U", L_REF)`, exactly as its `main()` does. Its rows U, TU and F must all PASS.
- **D:** D is 50 000 ps at both requesters, equal to the PCAP-derived value; the logged t1…t4 equal PCAP. Integer
  picoseconds, no tolerance.
- **Termination:** every valid-FCS Pdelay frame received is terminated.
- **Counters:** all 11 fault counters are 0, and `selfTestPassed` is 1 at both requesters.
- **Requirement check:** the adapter checks these requirements against the reviewed source itself.
- **Added guard:** the adapter adds one stricter check, non-vacuity. Each requester must publish at least 25 exchanges, all
  with D equal to 50 000 ps.

**E-7, no repository or upstream change:**
- no file in the repository (outside `.git`) or in the three project trees was modified during the pre-flight or the
  simulation;
- `git status` (tracked, untracked and ignored) is identical before, after and at evaluation;
- both locks pass before and after the pre-flight and the simulation, and at the end;
- C-3 PASS.

**E-8, evidence:**
- the raw outputs are sealed (SHA-256 manifest with sizes, read-only) before any evaluation, and verified unchanged after
  evaluation and again before publication;
- the screened diagnostics are prepared (text only, screened);
- the raw evidence is prepared, content-checked per file type (see below);
- the conclusion step requires both uploads to succeed.

**E-9, historical reference hashes (informational):**
- the SHA-256 of the two engine logs and the two PCAP files is compared with the OMNeT++ 6.4.0 hashes;
- those hashes are identical in M2-S4 (15 Oct), R181b and R181c;
- the result is REPRODUCED or DIFFERS, and it is not an acceptance criterion.

**Verdicts:**
- **STOP:** the disk guard or a disk gate stopped the run.
- **INFRASTRUCTURE FAILURE:** the guard was not healthy.
- **E3a BLOCKED:** only when the pre-flight or the simulation failed with a NED, INI or loading diagnostic, which is quoted.
  No NED or INI file is ever patched.
- **E3a FAIL:** any other failed or unevaluated mandatory row.
- **E3a PASS:** every mandatory row is PASS.

### Evidence and publication

There are two artifacts, each kept for 7 days.

**`e3a-diagnostics-run<id>-1`:**
- tier-1's screened diagnostics;
- the tier-2 text records, prefixed `e3a-`;
- the verdict;
- text only, screened, at most 20 MiB.

**`e3a-raw-m2s4u-run<id>-1`** contains:
- the complete sealed raw outputs: simulation log, `.sca`, `.vec`, `.vci`, both PCAP files, both engine CSV logs and the
  effective configuration;
- the seal manifest;
- the execution, identity, loader, watchdog and oracle records;
- a publication manifest.

**Checks on every raw-artifact file, by type:**
- **Every file:**
  - it must be one of the expected outputs or an allow-listed record;
  - it must be a regular file;
  - it must not be ELF, `ar`, gzip or zip.

  No compiled OMNeT++, INET, Simu5G or nascTime binary is ever published.
- **Text files:** strict UTF-8, no NUL byte, and the tier-1 screen must pass.
- **PCAP files:**
  - the file must be valid pcapng, parsed completely by the repository's reader;
  - every frame must be Ethernet and parsable;
  - every source MAC must be a simulation-assigned (locally administered) unicast address;
  - every destination must be such an address, the gPTP multicast address or broadcast;
  - the screen must pass on all strings extracted from the file.

A binary file is never treated as screened merely because a text regex found nothing.

## Offline validation

```bash
python3 -I ci/tier2/tests/test_tier2.py
```

```bash
python3 -I ci/tier2/tests/test_e3b.py
```

`test_tier2.py` is the E3a regression suite for the shared code. `test_e3b.py` covers the E3b additions. Each check name says
what kind of input it uses:
- `[stand-in]`: a script in place of `opp_run`;
- `[synthetic]`: generated files from `tests/synth.py` and `tests/synth5.py`;
- `[mock]`: a mocked `check_m2s5`, used for the adapter's row mapping only;
- `[reviewed]`: the real `check_m2s5.py` with its import chain, on synthetic evidence. Empty traffic must FAIL, as must
  missing or malformed files.

No test runs OMNeT++ or a simulation.

The E3a suite:

The suite takes about 2 minutes and needs no Nix, network, OMNeT++ or simulation. Its synthetic outputs come from
`tests/synth.py` and are never evidence. It covers:
- trigger and commit identity;
- the exact argument vector and duplicate-start refusal;
- the watchdog paths: size, non-numeric measurement, wall cap, STOP, and child processes;
- RUNPATH hazards;
- the U1 adapter on positive, negative, missing and malformed evidence, through the reviewed oracle itself;
- sealing;
- raw-publication refusals;
- the evaluator's fail-closed rows and verdicts;
- the conclusion, which requires both uploads.
