# M2-R181: Simu5G 1.8.1 integration baseline — execution plan, revision 2

**Decision.** Review of 2026-11-11 14:14:
- B → A → C approved;
- runner-output isolation approved, with four refinements;
- issue #308 confirmed closed as completed (user-verified).

**Scope:**
- the baseline migration and the validation gate only;
- no Q1–Q4, no E2, no Stage 5 load campaign;
- the VM NED corrections are excluded (§4).

**Base:** `m2/architecture` at `14d5e0f`. New work is on branch `m2/simu5g-1.8.1`.

**Stack:**
- OMNeT++ 6.4.0 and INET 4.7.0, unchanged.
- **Simu5G 1.8.1 unmodified**: `git archive v1.8.1` (`7477d266`) into `/root/stack/simu5g-1.8.1`, built with `make makefiles; make MODE=release`. The library hash is recorded in every 1.8.1 output.
- The 1.8.0 tree `/root/stack/simu5g-1.8.0` (`libsimu5g.so` `203cf231…`) is untouched.

This plan is committed before any change to runners or checkers, and before any 1.8.1 run. Predictions are in `M2-R181-predictions.md`, committed before the 1.8.1 runs.

## 1. Result preservation

### R-1: two modes, selected only by `NASCTIME_RESULTS_ROOT`

**Legacy mode** (variable unset):
- `RESULTS = $HERE/results`. This is the existing path, and the behaviour is byte for byte as before: same files, same names, same content.
- New fail-closed condition: the runner refuses to start unless `$SIMU5G_ROOT/src/libsimu5g.so` is the accepted 1.8.0 library (`203cf231…`). The legacy tree can never receive output from another stack.
- The only exception is the 1.8.0 counterfactual mode `m2s72.sh cfqd`, which keeps its own guards and record.

**Isolated mode** (variable set):
- `RESULTS = $NASCTIME_RESULTS_ROOT/<m1|m2>`.
- The root must be absolute. It must not be, contain, or lie inside `simulations/m1/results` or `simulations/m2/results` (checked on resolved paths).
- Default root for this milestone: `simulations/results/simu5g-1.8.1/`. It is git-ignored, like every results tree, and records are added explicitly.

### R-2: no overwrite in isolated mode

- Every *run* mode refuses to start if its stage directory already exists ("isolated results are never overwritten").
- A runner's internal sub-modes (`"$0" <sub-mode>`) inherit a claim on the directory they created; nothing else does.
- Check-only modes may read an existing stage directory, and write only their check outputs into it.
- **Modes specific to the 1.8.0 Stage 5 record** (`e0*`, `cfqd`, `e0r2`, `e2rb*`) refuse to run in isolated mode. They are not part of M2-R181.

### R-3: environment metadata and G0 byte identity

**Legacy mode** writes no new file, and no new line in `env*.txt`.

**Isolated mode only** adds `stack.txt` to each stage directory:
- Simu5G `Version`;
- `libsimu5g.so` sha256;
- OMNeT++ / INET versions;
- the nascTime commit;
- the results root.

**References between stages** point into the same results root, so each run is checked against its own stack:
- M2-S1 → M2-S0 hashes;
- M2-S3 / S4 → M2-S1 runs;
- M2-S5 → M2-S4;
- M2-S6 → M2-S5;
- M1 S1 → S0, S2 → S1, S5 → S4.

**Cross-version references stay explicit.** T0's "reference run reproduces the committed record" rows keep reading the committed 1.8.0 records. On 1.8.1 they are reported as a cross-version comparison (§3).

### R-4: proof of legacy identity (G0)

1. After the runner commit, the 16 G0 runners run in **legacy mode on 1.8.0** in a temporary `git worktree` of that commit, never in this working tree.
2. Pass condition:
   - `git status` in the worktree shows changes **only** in `env*.txt` lines `date_utc` and `nascTime_commit`;
   - every committed `raw-outputs.sha256` and `check.txt` / `*-check.txt` / `*.md` is byte-identical;
   - all 16 runners return rc 0.
3. The worktree's raw outputs are then deleted (they duplicate committed hashes). The worktree is removed.

## 2. Packet conservation (replacing "sent = delivered + queued")

The simple equation is valid only at a declared boundary, with every in-system state either counted or shown empty.

**Boundary.** A packet is counted at two points, identified by packet identity (application sequence number per flow, or gPTP sequenceId):
- **source egress:** application `packetSent`, or translator egress PCAP;
- **sink ingress:** sink `packets`, or far-translator ingress PCAP.

**States for a packet sent before T_end:**

| State | How it is measured (independently of the scheduler code) |
|---|---|
| delivered | the identity is seen at the sink exactly once (duplicates counted separately, never netted) |
| before RLC (bridges, links, N3 / N6, UPF / UE bridge queues) | sent − RLC TX SDUs in, per flow; bounded by the frames sent in the last `W_eth` (the measured maximum source→RLC sojourn, ≤ 1 ms in M1) |
| queued whole in RLC TX | byte-level RLC UM TX replay (the M1 O-tail method: SDU arrivals and `sentPduSize` per entity): SDU with 0 bytes sent at T_end |
| segmented (partly sent) in RLC TX | replay: SDU with 0 < bytes sent < SDU size at T_end |
| in MAC / HARQ / air / RLC RX reassembly | replay: the SDU's last byte left RLC TX at t_last, and it is not delivered; allowed only if t_last > T_end − W_harq, with `W_harq` = (max HARQ transmissions) × (measured TB-to-feedback time) + 1 slot |
| lost, attributed | a named statistic or log event: HARQ failure after the maximum attempts, `macPacketLoss*`, RLC RX discard, queue overflow. MAC deletion for lack of a HARQ process is expected to be impossible on 1.8.1 (it now raises an error); it is asserted 0 by "run completed" **and** by the trace pattern |
| UNEXPLAINED | anything else. **Must be 0** |

**Equation (exact, per flow):**

sent = delivered + before-RLC + queued + segmented + in-HARQ + lost_attributed + UNEXPLAINED, with UNEXPLAINED = 0.

**When the simple form is valid.** sent = delivered + lost_attributed holds only when every in-system state is shown empty at T_end. The drain design ensures that: sources stop at T_stop, and the run ends at T_end ≥ T_stop + D. The checker must then show:
- queued = segmented = in-HARQ = before-RLC = 0;
- the last delivery before T_end − margin.

The O-S3-1 `O1-drain` configs (stop 3 s, end 5 s) are such a design, **provided the 2 s drain actually empties the saturated backlog on 1.8.1**. This is not assumed: if the replay shows a residual queue, the full equation is used and the residual is reported.

**Saturated runs.** RLC UM TX is unbounded, so backlog grows with load. Under saturation the in-system states are expected to be non-zero at T_end, and only the full equation applies.

## 3. Independent validation

1. **Historical 1.8.0 oracles are unchanged** (code and records).
   - On 1.8.1 every historical checker runs unchanged. A row that encodes a 1.8.0 defect is expected to FAIL, and is **reported as FAIL**, never reclassified or skipped.
   - The predictions file lists these rows before the runs, with the reason.
2. **Version-neutral rows** are added as new checker code, alongside the old rows, and selected by a flag. Each verifies the behaviour from raw evidence, never from an expected verdict. Each new row must:
   - (a) PASS on its positive evidence;
   - (b) FAIL on the 1.8.0 outputs (from the R-4 legacy run, before they are deleted) where 1.8.0 has the defect;
   - (c) FAIL on a declared in-memory mutation (negative control).

**New rows:**

| Row | Evidence | Pass condition |
|---|---|---|
| **S5-R-egress-v** (M1 S5) | FlowMeasurementRecorder `transit5gs` samples at the far translator; PCAP at both translators | Samples = frames that crossed, per direction and seed. Each sample (matched by arrival time to the far-translator ingress frame) equals that frame's PCAP transit within one maximum frame serialisation time at the link rate |
| **O1-cons** (M1 O-S3-1 configs O1-drain / O1-harq16) | sources, RLC TX / RX vectors, RLC TX replay, MAC trace | The §2 equation, per flow and direction, UNEXPLAINED = 0; the MAC-deletion trace pattern count = 0. Discards are reported as counts for HARQ5 and HARQ16 separately |
| **OT-strand** (M1 O-tail configs) | RLC TX replay (unchanged code), arrival times | (i) the existing replay row (delivery 4 ms after the last byte left RLC) still holds; (ii) number of stranding events (bytes left in RLC TX, and the entity idle until the next SDU arrival) = 0; (iii) Follow_Up gNB wait ≤ 2 ms for every Follow_Up |
| **Q8-zero** (M2 S7.2a, when Q8 is run) | MAC log | MAC PDU deletions = 0; Q8 UNEXPLAINED = 0 |

3. **Every numerical change is recorded.** `tools/diff_records.py` aligns each 1.8.1 check output with its 1.8.0 record, row by row, and lists:
   - every verdict change;
   - every changed number in the row's detail text (old → new).

   The full diff is committed. The report summarises it, but the diff is the evidence.
4. **Exact oracles** (O1 / O3 / O5, the C1–C5 closure, the clock model) are version-independent by construction: they are computed from that run's own timestamps. They must PASS unchanged on 1.8.1.

## 4. NED compatibility

- The VM's NED corrections are **not** part of M2-R181. They will be reviewed from your diff, and only the necessary ones enter as a **separate commit** after this milestone, with G0 identity on 6.4.0 re-proven.
- 1.8.1 changes no NED, so this milestone needs none.

## 5. Commits (small, reviewable)

1. This plan.
2. `simulations/nt_results.sh` plus the runner edits (R-1…R-3). G0 legacy-identity proof (R-4) recorded.
3. `M2-R181-predictions.md`.
4. Version-neutral rows plus `tools/diff_records.py`, with their controls run on the 1.8.0 legacy-proof outputs.
5. U0: Simu5G 1.8.1's own new module tests.
6. 1.8.1 runs, then the record and report: U1, R1–R6, I1–I3.

**Gate.** STOP for review. No Q1–Q4, no E2.

## 6. Resources

- Disk: 11 GB free.
- The G0 suite took 1 h 22 min on 1.8.0 (2 CPUs).
- Raw outputs of the 1.8.1 runs are retained as long as space allows. If not, hashes are recorded first and the deletion is reported; any deletion of 1.8.0 evidence needs authorisation.
- S7.2a CP2 revision 2 (I2 / I3) is the largest item. If it does not fit in time or space, it is reported as not run, never as passed.
