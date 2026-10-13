# M1 closure report: minimal 5G Ethernet bridge on vanilla OMNeT++ 6.4.0 / INET 4.7.0 / Simu5G 1.8.0

**Status: CLOSED (2026-10-13).** Stages S0–S5 all PASS. One observation remains open (O-S0-1), recorded and not blocking.

- **Branch:** `m1/ethernet-bridge`, off the untouched `master` (`9e8bc83`).
- **No changes** to OMNeT++, INET or Simu5G.
- **M2 has not started:** its scope is to be agreed first.

Evidence for every statement below is in `simulations/m1/results/` (one `.md` per stage or investigation, plus checker outputs). Every run records its commit and stack versions.

## 1. What M1 validated

### 1a. Native capabilities of Simu5G 1.8.0 / INET 4.7.0, used unmodified

| Capability | Evidence |
|---|---|
| Ethernet PDU sessions: UE in Ethernet bridge mode, UPF Ethernet bridge. nascTime's own scenario is bit-identical to Simu5G's `Ethernet-Bridge` reference. | S0 (upstream fingerprints 4/4), S1 (60/60 counters, 9780/9780 delay samples) |
| VLAN/PCP → QFI → DRB mapping, verified separately in UL and DL: classification as the QFI in GTP-U on N3, and actual DRB as the per-DRB RLC entity. Holds under saturating load. Four negative controls each fail exactly their own checks. | S3, 24/24 |
| Ethernet frames, including VLAN/PCP, cross the 5G system byte-identical. | S2, S3, S5 |
| Packet identity in the frame (sequence numbers) and gPTP fields are preserved, including SDUs cut and reassembled by RLC. | S5 |
| gPTP messages cross the non-time-aware 5G system intact; INET's gPTP slave updates its clock from every Sync/Follow_Up pair. | S4 transport, 8/8 |
| The slave clock behaves exactly as IEEE 802.1AS (INET implementation) predicts from the measured path: offset = path asymmetry, rate error = path delay variation. | S4 clock, 4/4; every step reproduced within 1 ns |
| Chunk-level metadata (the application's `CreationTimeTag`) arrives with the correct value. | S5 |

### 1b. Delivered by nascTime in M1: configuration and test only, no C++

- **`nasctime.tt.PassThroughTt`:** an INET `TsnSwitch` with every TSN feature off. It is a placeholder for DS-TT/NW-TT and does nothing a translator does.
- **`M1Bridge` network** with default-off wiring (`hasPassThroughTts`, retypable stations), and plain-ini configs S1–S5. Every addition is shown not to change S1–S4 (regressions).
- **Test harness:** one runner and one checker per stage; PCAP-based protocol checks; an independent clock-model check; and a byte-level RLC replay tool that reproduces every DL delivery from recorded statistics.
- **By observation only:** per-frame ingress/egress times at the translator ports and per-frame 5G-system transit, reconstructed from PCAP by packet identity.

### 1c. NOT available: nascTime functionality still to be developed

- **Time-aware translators.** No ingress timestamping, residence-time computation or `correctionField` update. **M1 provides no transparent-clock support or residence-time correction.** `correctionField` stays 0 end to end (S4, S5).
- **Carrying translator timestamps across the 5G system.** INET's packet-level measurement tags are dropped inside Simu5G (S5). Any in-band mechanism, whether a frame field or a chunk-level tag, is untested and needs design.
- **Out of M1 scope:** gPTP termination/BMCA at the translators, TSN AF, FRER, multi-endpoint, legacy translator migration, the S-CFG generator.

## 2. Limitations found in the native stack

| # | Limitation (Simu5G 1.8.0 unless stated) | Effect | Record |
|---|---|---|---|
| L1 | MAC deletes MAC PDUs, including RLC data already pulled, when no HARQ TX process is free. Not counted by any statistic. | Under saturation, 16.6 % DL / 15.8 % UL of MAC PDUs are lost silently (default 5 processes; feedback after exactly 5 slots). With 16 processes, none. | `O-S3-1.md`; draft issue 1 |
| L2 | NR UM DL grant counts one RLC header per connection; the remainder is held until the next SDU arrives ("tail lag"). | A DRB receiving ≥ 2 frames in one slot can stay in tail lag: delay depends on the next arrival. Seen as 10–25 ms Follow_Ups (S4); the last frame of a burst is stranded. | `O-tail.md`; draft issue 2 |
| L3 | `GtpUser` re-creates packets from their data; packet-level region tags (INET flow measurement) are dropped. | No INET flow/elapsed-time measurement across the 5G system. | `S5.md`; draft issue 3 |
| L4 | UL scheduling (BSR/grant, no SR modelled) | UL transit varies widely (6–48 ms, light load). It dominates the gPTP pdelay estimate (7–17.6 ms raw). | S0, S4 |
| L5 | INET: gPTP needs reception/transmission-*start* signals. | The station links need INET's streaming PHY transmitter/receiver (ini setting). | `S4.md` |
| L6 | INET bridges (pass-through TT, UE and UPF bridges) forward `01-80-C2-00-00-0E`. | M1 relies on this to pass gPTP through. A standards-conformant 802.1Q bridge would not forward it, so this is a test convenience, not translator behaviour. | S4 |
| L7 | Configuration-specific timing. | The +1090 ns of S2 (front translator absorbed by slot alignment) holds only for slot-aligned generation; it is confirmed to 1 ns by a phase-offset test. | `S2.md` |

The three upstream drafts are in `simulations/m1/upstream-issues/`, each with a reproduction that uses Simu5G only (9/9 evidence rows). **They have not been submitted.**

## 3. Unresolved observations

- **O-S0-1 (open, not a blocker):** at light load, UL delay takes a small set of discrete values (6–47 ms, 14 values in S0) in a repeating pattern. The candidate cause is the BSR/grant cycle without SR. It has not been attributed.
- **Not examined:**
  - whether the UL scheduler (`LcgScheduler`) has an NR-SO sizing effect like L2;
  - INET packet-level non-region tags across the 5G system;
  - any configuration other than one gNB, one UE, numerology 0 and an unloaded or saturated channel.

All other M1 observations are explained and recorded: O-S3-1 → L1; O-S3-2 and O-S4-1 → L2.

## 4. Implications for M2 (inputs for the scope discussion, not decisions)

1. **Time-aware translators are new nascTime code.**
   - Ingress/egress timestamping at the translator ports is observable (S5), so it can be implemented there.
   - Moving the ingress time from one translator to the other needs a mechanism that survives `GtpUser`: an in-frame field (e.g. a gPTP TLV, or a translator header/trailer) or a chunk-level tag. This is a design decision, and it should be tested with the S5 checker before any accuracy claim.
2. **Residence-time correction must be validated against the S4 baseline.** The current baseline is max |offset| 5.3–6.4 ms, explained exactly by path asymmetry and variation. M2 claims should be phrased as improvement over this, with the S4 clock-model check kept as an oracle.
3. **L2 (tail lag) can distort any DL timing result.** Options include a separate DRB for gPTP, traffic spacing, an upstream fix, or detecting cuts with the replay tool in every timing test. Pick one.
4. **L1 (HARQ discard) under load:** choose between `harqProcesses = 16` (documented configuration) and counting discards from the trace. Results under load are not valid without one of them.
5. **UL variability (L4, O-S0-1)** dominates the 5G-system residence. M2 timing claims need it characterised or controlled (for example by configured grants, if Simu5G supports them; not yet checked).
6. **Upstream:** decide whether and when to submit the three drafts. Keep production pinned to Simu5G 1.8.0, with non-blocking CI on upstream master.
7. **Keep the M1 method:** small stage commits, functional + protocol + experimental checks, negative controls, regressions of earlier stages, recorded results and one bundle per stage.

## 5. Index

| Item | Location |
|---|---|
| Stage results | `results/S0.md` … `results/S5.md` (+ `S2-phase/`) |
| Investigations | `results/O-S3-1.md`, `results/O-tail.md` |
| Upstream drafts and reproduction | `upstream-issues/` (README, three drafts, `issues.ini`, `run_issues.sh`, `check_issues.py`); evidence in `results/upstream-issues/check.txt` |
| Plan and status | claude.ai Project `nascTime`: `migration/m1-plan.md` |
