# [DRAFT – not submitted] NR UM DL grant counts one RLC header per connection: the last of several queued SDUs is cut and its remainder waits for the next SDU

**Version:** Simu5G 1.8.0 (`v1.8.0`), INET 4.7.0, OMNeT++ 6.4.0, NR standalone, RLC UM with SO framing (12-bit SN), default DL scheduler.

## Summary

The DL scheduler sizes a connection's demand as its queued bytes plus **one** MAC header and **one** RLC header:

```
// LteSchedulerEnb.cc:314
queueLength += MAC_HEADER + RLC_HEADER_UM;  // TODO RLC may be either UM or AM
```

The NR-SO carve of the same grant charges an RLC header **per PDU** (`LteSchedulerEnb.cc:424` onward): 1 B per complete SDU, 2 B for a first segment, 4 B for a later one.

**Consequence 1: the last SDU is cut.**
- With n ≥ 2 SDUs queued on a DRB in one slot, the grant is up to n − 1 bytes short of what the PDUs need, unless resource-block rounding happens to cover it.
- The last SDU is then cut, and a few bytes remain.

**Consequence 2: the remainder is stranded.**
- After the grant, `queueLength` is set to 0 and the connection inactive (`LteSchedulerEnb.cc:403–408`), although the virtual buffer still holds the remainder.
- The remainder is therefore served only when the next SDU arrives on that DRB.
- That slot again holds ≥ 2 items (remainder + new SDU), so the DRB can stay in this state indefinitely. Each SDU is then completed only when the next one arrives.
- The last SDU before traffic stops is never completed.

## Reproduce

Run `issues.ini`, config `Issue2-DlTailLag`: `Ethernet-Bridge` plus two untagged DL flows (46 B and 76 B payload) sent 1 µs and 2 µs after dnStation's PCP 0 flow.
- Three SDUs (120 B, 62 B, 92 B) reach DRB 1 in the same slot every 20 ms.
- The grant (278 B) covers the demand formula (274 + 2 + 1 = 277 B) but not the three PDUs (274 + 3 + 2 = 279 B).
- Sources stop at 3 s; the run goes on to 5 s.

These are the sizes of a gPTP Sync and Follow_Up next to a data frame, which is where the behaviour was first seen.

## Observed (seed 0)

**Delay at device[0]:**

| Config | Frames at 5 ms | Frames at 25 ms |
|---|---|---|
| `Issue2-DlTailLag` | 438 | 145 |
| `Issue2-DlTailLag-apart` (counterfactual: the two extra flows 2 ms and 4 ms later) | all 584 | 0 |

- **One SDU left at the end:** 2 s after the last arrival, one SDU (92 B) is still in the gNB RLC with 6 B unsent; its frame is never delivered. In the counterfactual, no SDU is ever cut and none is left.
- **Replay evidence:** the gNB DRB 1 RLC was replayed from the recorded `receivedPacketFromUpperLayer` and `sentPduSize` vectors.
  - Every one of 437 SDUs is delivered at the UE RLC exactly 4 ms after the slot in which its last byte left.
  - In all 146 slots with a cut, ≥ 2 items were queued, and the grant was ≥ queued bytes + 3 B and < what the PDUs needed.
  - After every cut, DRB 1 sent nothing until the next SDU arrived.

## Expected

- The SO-framed DL demand includes one RLC header per PDU (and segment headers for a remainder).
- A connection whose virtual buffer is non-empty stays schedulable.

The UL `LcgScheduler` sizes NR-SO PDUs in its own code; we have not checked it for the same effect.

## Impact

DL latency on any DRB that occasionally receives two frames in one slot depends on the arrival of the next frame, not on the radio. In the nascTime case this was gPTP Sync + Follow_Up next to data, giving 10–25 ms instead of 5 ms. The last frame of a burst can be lost.
