# M2-R181b: root causes of the two timing discrepancies

**Evidence.** Diagnostic runs only (scratch, hashed in `diag-raw-outputs.sha256`, then deleted).
- They use the unchanged ini configs on the unmodified Simu5G 1.8.1 and 1.8.0 builds.
- Scripts: `diag_r2b.py`, `diag_r2b_all.py`, `diag_s5_egress.py`.
- Records: `diag-r2b-all-1.8.1.txt`, `diag-r2b-all-1.8.0.txt`, `s5-egress-per-frame.csv`.

**Correction of the M2-R181 report.** That report said the 736 ns "arises inside the 5GS, between UE Ethernet ingress and UPF N6 egress". That was a statement about **per-hop transit**, and it is true only in that sense. The first point where the two runs differ in **absolute time** is earlier: the talker's own egress (below).

---

## 1. M2-S4 R2b, 736 ns

### 1.1 First divergence (seed 3, t = 1 s; identical at 2 s and in every other affected seed)

Absolute PCAP end-of-frame times, M2S4 vs M2S4-ctl-nopdelay, 1.8.1:

| Recorder | M2S4 | Control | |
|---|---|---|---|
| talker eth[0], out | Pdelay_Req (72 B) **1.000000640**, then app frame (122 B) **1.000001776** | app frame **1.000001040** | **first divergence: +736 ns** |
| dsTt eth[1], in | 1.000001826 | 1.000001090 | +736 |
| dsTt eth[0], out | 1.000002866 | 1.000002130 | +736 |
| ue[0] eth, in | 1.000002916 | 1.000002180 | +736 |
| upf N6, out (UL) | 1.006001225 | 1.006001225 | **identical** |
| nwTt eth[1] → listener (UL) | 1.006002315 | 1.006002315 | identical |
| listener, in | **1.006002365** | **1.006002365** | **identical** |

Notes on the table:
- The latency is measured from the talker's transmit end to the listener's receive end, so it is **736 ns shorter in M2S4**.
- The frame leaves the talker 736 ns later but reaches the listener at the same instant: the 5G system's TTI-quantised UL delivery absorbs the delay.

### 1.2 Exact cause

1. **The app frame queues behind a Pdelay_Req at the talker.**
   - In M2S4 the talker (an INET `Gptp` slave) sends a link-local Pdelay_Req at **exactly the same simulation time** as the talker application's frame: both start at t = 1.000000000 s.
   - The Pdelay_Req is serialised first. The application frame waits 72 B + 8 B preamble = 640 ns, plus the 96 ns inter-frame gap: **736 ns**.
2. **The talker's Pdelay timer runs on its clock, which version 1.8.1 shifted.**
   - INET `Gptp` schedules the Pdelay timer on the node's clock: `Gptp.cc:100` `scheduleClockEventAfter(pdelayInitialOffset, pdelayTimer)` and `Gptp.cc:118` `scheduleClockEventAfter(pdelayInterval, pdelayTimer)`.
   - The talker is the slave, and its clock is corrected by Syncs that cross the 5G system. 1.8.1 changes that delivery timing (see the M2-R181 S4 clock-baseline numbers), so the simulation time at which the talker's clock reaches k s changes.
   - Second Pdelay_Req start, 1.8.0 → 1.8.1:

     | Seed | 1.8.0 | 1.8.1 |
     |---|---|---|
     | 3 | 1.000001536 s | **1.000000000 s** |
     | 6 | 1.000001536 s | **1.000000000 s** |
     | 9 | 1.000001536 s | **1.000000000 s** |

     On 1.8.0 the Pdelay_Req starts after the application frame (frame end 1.000001040 + IFG), so they never collide. On 1.8.1 the two coincide in seeds 1, 3, 4, 5, 6, 7 and 9 (`diag-r2b-all-1.8.1.txt`).
3. **The control has no talker Pdelay at all.** It sets `*.talker.gptp.pdelayInitialOffset = 10s` (`omnetpp.ini`, `[Config M2S4-ctl-nopdelay]`). So its application frames never queue behind one.
4. **The complete classification**, over all 33,562 application frames in seeds 0–9 and the load run:
   - **10 frames differ, all by −736 ns, and every one** is a talker-egress frame that starts exactly one IFG after the end of the talker's own Pdelay_Req.
   - **No frame differs for any other reason.** Every arrival time at the receiving station is identical.
   - On 1.8.0, no such collision occurs, and 0 frames differ.

### 1.3 Does enabling Pdelay change forwarding, or only the measurement?

- Forwarding through the 5G system is unchanged: every frame is delivered at the same instant.
- What changes is the **send instant at the talker**, before the measurement's start point, because of contention on the talker's own link with the talker's own Pdelay_Req.
- This contention is a property of the M2S4 scenario: link-local Pdelay on the TSN link. **It is neither a 5G-system nor a TtPdelayPort effect.**
  - The TtPdelayPort only answers; it does not send the Pdelay_Req.
  - The control removes the talker's Pdelay entirely.
  - Packet sizes, serialisation and metadata are unchanged: the frames are byte-identical in both runs.

### 1.4 Implementation or acceptance criterion?

- **The acceptance criterion needs correcting; the implementation does not.**
- R2b claims "application frames in M2S4 have exactly the latencies of a control with no Pdelay anywhere". That is a statement about wire-to-wire latency, and it can fail whenever the slave's Pdelay timer collides with an application send instant.
- It held on 1.8.0 by phase coincidence, not as a property. On 1.8.0 the gap was only 1.536 µs − 1.040 µs − 96 ns = 400 ns.
- Historical R2b keeps its FAIL.
- **Replacement row R2b-v** (`check_v181b_m2.py r2b`) states what does hold, exactly:
  - the same application frames are delivered;
  - every arrival time is identical;
  - send times are identical except for frames queued at their station's egress behind that station's own Pdelay_Req. Those frames are listed with their shift.

### 1.5 Minimal regression test

`check_v181b_m2.py r2b <M2-S4 runs>` with its mutation control (one arrival in M2S4 seed 0 shifted by 1 ns → FAIL). The smallest reproducer is M2S4 and M2S4-ctl-nopdelay, seed 3 (`diag_r2b.py`): the two frames sent at 1 s and 2 s.

---

## 2. M1-S5 S5-R-egress-v, 224 ns

### 2.1 Per-frame breakdown

`s5-egress-per-frame.csv` covers all 1073 samples (S5-pcap, seed 0). For every sample, exactly (to 1 ns):

```
sample (INET transit5gs meanBitElapsedTimePerPacket) = PCAP transit + own serialisation time + near-translator egress wait
```

- **Egress wait.** It is computed from PCAP alone: the near translator's eth[0] transmit start minus (the station's transmit end + 50 ns propagation).
- **Propagation.** INET `EthernetLink` default length 10 m / 2e8 m/s.
- **The 19 failing samples** are all DL gPTP Follow_Ups (94 B), each with an egress wait of **224 ns**. The other 1054 samples have a wait of 0.
- **Holds in both directions:** UL 495 of 495 samples, DL 578 of 578.

### 2.2 First divergence and exact cause

- **Where the measurement starts.** The measurement starter sits in the near translator's eth[0] `MeasurementLayer`, *before* that port's MAC queue (S5 ini: `*.*Tt.eth[0].measurementLayer.measurementStarter`). The PCAP "in" stamp is the end of the frame on the wire.
- **Why the Follow_Up waits.** The GM sends the application frame (122 B) and the Follow_Up (94 B) back to back: 1.000001712 and 1.000002624 s end, gap 96 ns IFG.
  - The translator stores and forwards each frame after its full reception.
  - The shorter Follow_Up is fully received while the longer application frame is still being transmitted on eth[0]. It waits 1040 − 816 = **224 ns**, the difference of the two serialisation times.
- **So:** the INET sample includes this egress queueing at the near translator; the PCAP transit does not.
- **Version.** This is a TSN-side effect upstream of the 5G system, so it is version-independent. It was invisible on 1.8.0 only because 1.8.0 recorded 0 samples (tags lost).

### 2.3 Implementation or acceptance criterion?

- **The criterion is wrong; the implementation is right.**
- The bound I declared in M2-R181 ("the sample is within the frame's serialisation time of the PCAP transit") ignored egress queueing at the near translator. No 5G-system or measurement defect is involved.
- S5-R-egress-v keeps its FAIL.
- **Replacement row S5-R-egress-v2** (`check_v181b.py s5e`):
  - the exact relation above, to 1 ns, with the wait from PCAP;
  - plus the sample counts per seed and direction.
- This is stricter than the old bound: every sample must match exactly.

### 2.4 Minimal regression test

`check_v181b.py s5e <M1 results root>` with its mutation control (one DL sample + 2 ns → FAIL). On 1.8.0 it must fail with 0 samples.
