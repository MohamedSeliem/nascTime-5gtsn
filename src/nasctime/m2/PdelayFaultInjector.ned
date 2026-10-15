//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.m2;

import inet.protocolelement.measurement.IMeasurementLayer;
import inet.protocolelement.trafficconditioner.ITrafficConditionerLayer;
import inet.queueing.base.PacketFlowBase;

//
// TEST ONLY (M2-S4 fault cases and negative controls, migration/m2-s4-design.md 8.3/9).
// Fits an empty measurementLayer or trafficConditionerLayer slot of a LayeredEthernetInterface;
// acts on the TX path only (the RX path is a plain connection). Default: inert.
//
module PdelayFaultInjectorLayer like IMeasurementLayer, ITrafficConditionerLayer
{
    parameters:
        @display("i=block/layer");
    gates:
        input upperLayerIn;
        output upperLayerOut;
        input lowerLayerIn;
        output lowerLayerOut;
    submodules:
        injector: PdelayFaultInjector {
            @display("p=150,100");
        }
    connections:
        upperLayerIn --> injector.in;
        injector.out --> lowerLayerOut;
        lowerLayerIn --> upperLayerOut;
}

//
// Acts on transmitted gPTP Pdelay frames (01-80-C2-00-00-0E, EtherType 0x88F7) whose
// messageType is in messageTypes and whose sequenceId is in sequenceIds:
//   drop            discard
//   dup             forward, then a copy immediately behind it (back to back)
//   dupAfter        forward; a copy is released right after the next frame of type
//                   afterMessageType with the same sequenceId (late duplicate)
//   holdUntilAfter  hold; release right after the next frame of type afterMessageType with
//                   the same sequenceId (reorder)
//   delay           hold for 'delay', then forward
//   rewrite         set 'field' to 'value' (FCS recomputed)
//   truncate        replace the gPTP message by its first truncateTo bytes (raw), pad, FCS recomputed
//   badFcs          invert the FCS (the receiver's FCS checker drops the frame)
//   fuBefore        (Pdelay_Resp only) send a Pdelay_Resp_Follow_Up with the same sequenceId and
//                   requester (responseOriginTimestamp 0) ahead of the Resp: a reordering medium
//
simple PdelayFaultInjector extends PacketFlowBase
{
    parameters:
        string action = default("");             // "" = inert
        string messageTypes = default("3");      // space-separated gPTP messageTypes
        string sequenceIds = default("");        // space-separated sequenceIds; "*" = all
        int afterMessageType = default(10);
        double delay @unit(s) = default(0s);
        string field = default("");              // "sequenceId" | "requestingPortNumber" | "versionPTP" | "messageLength" | "domainNumber"
        int value = default(0);
        int truncateTo = default(40);
        @class(nasctime::PdelayFaultInjector);
}
