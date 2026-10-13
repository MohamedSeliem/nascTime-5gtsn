# [DRAFT – not submitted] GtpUser re-creates packets from their data, so INET packet-level region tags (flow measurement) do not cross the 5G system

**Version:** Simu5G 1.8.0 (`v1.8.0`), INET 4.7.0, OMNeT++ 6.4.0.

## Summary

INET's measurement framework keeps its tags as packet-level region tags on the `Packet` (`Packet::regionTags`): `FlowMeasurementStarter` / `MeasurementLayer`, i.e. `FlowTag`, `ElapsedTimeTag`, `QueueingTimeTag`, …

`GtpUser` builds a new `Packet` from the old one's data when it tunnels and when it decapsulates, so these tags are left behind:

```
// GtpUser.cc:306-309 (tunnel), 463-466 (tunnelDownlink), 346-348 (decapsulation)
auto gtpPacket = new Packet(datagram->getName());
gtpPacket->insertAtFront(header);
auto data = datagram->peekData();
gtpPacket->insertAtBack(data);
```

- Chunk-level tags, such as the application's `CreationTimeTag`, travel with the data and survive.
- An INET flow measurement started before the 5G system therefore never arrives at a recorder after it.

## Reproduce

Run `issues.ini`, config `Issue3-RegionTags`: `Ethernet-Bridge`, plus a `FlowMeasurementStarter` (flow `dl`, `elapsedTime`) on dnStation's PCP 0 application. Recorders for flow `dl` are placed:
- on the UPF's N6 interface, before `GtpUser`, as a control;
- in device[0]'s sink application, after the 5G system.

## Observed (seed 0)

| Point | Result |
|---|---|
| Frames tagged at dnStation | 245 |
| Measured at the UPF N6 interface | 245 |
| Measured at device[0] | 0 |
| `CreationTimeTag` lifetimes at device[0] | 490 of 490 received frames |

## Expected / question

Should packet-level region tags be carried across GTP-U encapsulation and decapsulation, so that INET flow measurements work end to end through the 5G system? This would mean copying them to the new packet, with offsets shifted by the GTP-U header.

If not, a note in the documentation would help, since the measurement framework otherwise fails silently: no error, and simply no samples.

## Impact

INET's per-flow end-to-end measurements (elapsed, queueing and transmission time per flow) cannot be used across the 5G system. Only chunk-tag-based statistics (`meanBitLifeTimePerPacket` at the sink) work.
