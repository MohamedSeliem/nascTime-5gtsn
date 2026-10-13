# O-S4-1 and O-S3-2: late and stranded downlink SDU tails (investigation)

**Status: both EXPLAINED by one mechanism** (all 9 rows of `O-tail/check.txt`).

| | |
|---|---|
| Run | 2026-10-13, `simulations/m1/o_tail_investigation.sh` (about 1 min, seed 0) |
| Commit | `13a788a` (recorded in `O-tail/env.txt`; tree clean at run time) |
| Method | Configuration and recorded statistics only. No change to OMNeT++, INET or Simu5G. S3, S4 and their checks are unchanged. |

## The two observations

- **O-S4-1 (S4):** a Follow_Up took 10–25 ms through the 5G system, although its Sync, sent 2 µs earlier on the same DRB, took 5–6 ms.
- **O-S3-2 (O-S3-1 counterfactual with 16 HARQ processes):** exactly one frame per run was never delivered, the last downlink SDU.

## Method

The gNB's DRB 1 RLC UM TX entity is replayed byte by byte from Simu5G's own statistics:
- SDUs in: size and time;
- PDUs out: `sentPduSize` and time;
- header sizes: Simu5G 1.8.0's NR UM headers for a 12-bit SN, i.e. 1 B for a complete SDU, 2 B for a first segment, 4 B for a later segment (SN + SO).

The replay gives the slot in which each SDU's last byte leaves the gNB. Every replayed SDU (S4: 332; the two load runs: about 12 600 each) is then delivered by the UE's RLC exactly 4 ms later, in the same order. That is 1 slot on the air plus 3 slots until HARQ delivers, as seen in the MAC trace. The replay therefore accounts for every DL DRB 1 delivery in these runs.

## Mechanism (Simu5G 1.8.0)

**1. The DL grant is a few bytes short whenever more than one item is queued on a DRB.**
- The DL scheduler sizes a connection's demand as its queued bytes plus 2 B MAC header plus **one** 1 B RLC header (`LteSchedulerEnb.cc`: `queueLength += MAC_HEADER + RLC_HEADER_UM`).
- NR UM sends one RLC PDU per SDU or segment, each with its own header.
- With n queued SDUs the grant is n − 1 bytes short, unless resource-block rounding happens to cover it.
- The last SDU is then cut: its first segment goes now, and a few bytes remain.
- Evidence: in all 277 slots of S4 where an SDU was cut, the grant (sum of PDU sizes + 2 B) was ≥ the demand formula and < what the queued SDUs needed, with at least 2 items queued. A single fresh SDU was never cut.

**2. The remainder is stranded until the next SDU arrives on that DRB.**
- After the grant, the scheduler's own counter says the queue is drained and the connection is set inactive, although the remainder is still in the buffer.
- Evidence: in all 277 cases, DRB 1 sent nothing until the next SDU arrived. The remainder then left together with that SDU, within 2 slots.
- Since that slot again has ≥ 2 items (tail + new SDU), the new SDU is cut in turn. Once triggered, the DRB stays in a tail-lag state: each SDU is completed only when the next one arrives.

## O-S4-1, explained

- At 0.125 s the gNB receives Sync (62 B RLC SDU), a PCP 0 application frame (120 B) and Follow_Up (92 B) on DRB 1 within the same slot. The grant is 1 B short, and the Follow_Up is cut.
- From then on, 276 of the 327 later DRB 1 SDUs were cut and waited 1–21 ms for the next arrival.
- All 39 Follow_Ups waited more than 2 ms at the gNB, and all 39 were cut. Their 10–25 ms delays are the wait for the next DRB 1 SDU: the 20 ms PCP 0 application frame, or the next Sync.
- **Counterfactual (O2-s4-nodl):** without the DL PCP 0 application flow, DRB 1 carries gPTP only. No SDU is ever cut, and every SDU leaves within 2 slots.

**Side effect not visible in the S4 checks.** In S4 the DL PCP 0 application flow is itself in tail lag. At the talker, seed 0:
- 200 of its frames arrive after 25 ms;
- the DRB 2 (PCP 5) frames arrive after 5 ms.

S4's T-traffic check counts delivery, not delay, so it is unaffected. The S4 delays of DL DRB 1 traffic are therefore not representative of the 5G system and must not be reused.

## O-S3-2, explained

- In O1-harq16, the one SDU left in the gNB RLC at the end is the last SDU to arrive (316 B, untagged, 3.016 s), with 4 B unsent: the stranded remainder of a cut.
- **Counterfactual (O2-flush):** one more DL frame at 3.5 s. That SDU is completed in the slot right after the extra frame arrives (3.501 s). The extra frame (70 B) becomes the stranded one, with 4 B unsent.
- The stranding always moves to whichever SDU is cut last.

## Consequences

- **Light load:** S0–S3 are not affected by the stranding. Their DL frames were never queued together on one DRB in the same slot, which the constant 5 ms DL delays of S0–S3 confirm.
  - S3-load and the O-S3-1 runs are affected only through the residual (O-S3-2). Their losses are fully explained by O-S3-1.
- **For nascTime (M2 onward):**
  - Any DL DRB carrying two frames within one slot (gPTP Sync + Follow_Up next to data, bursts, TSN streams sharing a DRB) can enter tail lag. Its delay then depends on the next frame's arrival, not on the 5G system.
  - Timing results on such DRBs must check for cuts with this replay, or avoid the condition (for example one gPTP DRB, or traffic spacing). Choosing that is an M2 decision.
- **Upstream:** reportable to Simu5G with this replay as evidence:
  - the DL demand counts one RLC header per connection instead of one per PDU;
  - the connection is set inactive while a remainder is buffered.

  No upstream change was made.
- **Not examined:** the UL (`LcgScheduler`) has its own NR-SO sizing. It was not examined here.

## Files

| File | Content |
|---|---|
| `O-tail/check.txt` | Checker output (9 rows) |
| `O-tail/env.txt` | Stack and nascTime commit |
| `O-tail/raw-outputs.sha256` | Hashes of the `.sca`/`.vec`/CSV outputs. Not committed; the script regenerates them. |
