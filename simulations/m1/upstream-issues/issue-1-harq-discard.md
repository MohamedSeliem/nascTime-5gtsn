# [DRAFT – not submitted] MAC PDUs are deleted, with the RLC data in them, when no HARQ TX process is free; no statistic records it

**Version:** Simu5G 1.8.0 (`v1.8.0`), INET 4.7.0, OMNeT++ 6.4.0, NR standalone, default `harqProcesses` (5 for `NrMacGnb` and `NrMacUe`).

## Summary

Under sustained load, `LteMacEnb::macPduMake` (DL) and `LteMacUe::macPduMake` (UL) build a MAC PDU from RLC PDUs already pulled from the RLC. They then delete it when the TX HARQ buffer has no free process:

```
// LteMacEnb.cc:584-586 (LteMacUe.cc:652-654 is the same)
if (txList.second.empty()) {
    EV << "macPduMake() : no available process for this MAC PDU in TxHarqBuffer" << endl;
    delete macPacket;
}
```

- The data is lost for good: RLC UM does not retransmit.
- No statistic records the deletion. `macPacketLoss*`, `macCellPacketLoss*` and `macBufferOverFlow*` stay 0 or are never emitted, and HARQ statistics show no error. The loss is visible only as a debug-log line.
- In the reproduction, HARQ feedback arrives exactly 5 slots after a TB, and there are 5 processes. When a UE is scheduled in every slot, all processes can still be waiting for feedback when the next TB is built; the scheduler does not check for a free process before granting.

## Reproduce

Run `issues.ini`, config `Issue1-HarqDiscard`: `Ethernet-Bridge` plus a 1400 B PCP 0 flow every 0.25 ms in each direction. All sources stop at 3 s and the run continues to 5 s, so nothing is still in flight at the end.

## Observed (seed 0)

| | DL | UL |
|---|---|---|
| Frames sent / received | 11 891 / 9 368 | 11 891 / 9 631 |
| RLC PDUs sent by the TX RLC and never received by the peer RLC | 2 522 | 2 260 |

- The last frame is delivered at 3.105 s; nothing arrives in the remaining 1.9 s.
- UE HARQ: error rate 0 and 1 attempt per TB, in both directions.
- MAC loss/overflow statistics: none non-zero.
- **Trace config** `Issue1-HarqDiscard-trace` (MAC debug log; sources stop at 0.4 s, run to 0.6 s):
  - RLC PDUs buffered at the TX MAC minus those extracted at the RX MAC: DL 261, UL 217.
  - RLC PDUs inside MAC PDUs deleted with the message above: DL 261 (50 MAC PDUs), UL 217 (35 MAC PDUs). This is an exact match.
- **Counterfactual** `Issue1-HarqDiscard-16proc` (16 HARQ processes): RLC PDUs sent but never received: 0 in both directions.

## Expected

Either:
- the scheduler does not grant (or the MAC does not pull data from the RLC) when no HARQ process is free; or
- the pulled data is kept for a later TB.

At minimum, the deletion should be counted in a statistic.

## Impact

- In any loaded NR scenario with the default 5 HARQ processes, a large share of TBs can be lost silently. In nascTime's saturated scenario this was 16.6 % of DL and 15.8 % of UL MAC PDUs.
- Delivery and latency statistics look like radio or queueing effects that are neither.
