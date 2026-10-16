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
// TEST ONLY (M2-S5 fault cases, design 7.5). Fits an empty measurementLayer or
// trafficConditionerLayer slot; acts on the TX path (direction "tx") or on the RX path
// (direction "rx"); the other direction is a plain connection. Default: inert.
//
module SyncFaultInjectorLayer like IMeasurementLayer, ITrafficConditionerLayer
{
    parameters:
        string direction @enum("tx","rx") = default("tx");
        @display("i=block/layer");
    gates:
        input upperLayerIn;
        output upperLayerOut;
        input lowerLayerIn;
        output lowerLayerOut;
    submodules:
        injector: SyncFaultInjector {
            @display("p=150,100");
        }
    connections:
        upperLayerIn --> injector.in if direction == "tx";
        injector.out --> lowerLayerOut if direction == "tx";
        lowerLayerIn --> upperLayerOut if direction == "tx";
        lowerLayerIn --> injector.in if direction == "rx";
        injector.out --> upperLayerOut if direction == "rx";
        upperLayerIn --> lowerLayerOut if direction == "rx";
}

//
// Acts on gPTP Sync (0) / Follow_Up (8) frames whose messageType is in messageTypes and
// whose sequenceId is in sequenceIds:
//   drop            discard
//   dup             forward, then a second frame with the same content right behind it
//   holdUntilAfter  hold; release right after the next frame of type afterMessageType whose
//                   sequenceId is the held one + afterSeqOffset (reorder)
//   delay           hold for 'delay', then forward
//   rewrite         field ("sequenceId" += value | "versionPTP" | "messageLength" | "domainNumber" = value), FCS recomputed
//   truncate        gPTP message replaced by its first truncateTo bytes (raw), padded, FCS recomputed
//   fuBefore        (Sync k) a copy of the previous Follow_Up with sequenceId k is sent ahead of the Sync
//   stripTag        TtSyncIngressTag removed from the Follow_Up
//   tagSeq          TtSyncIngressTag sequenceId += value
//   tagFrameId      TtSyncIngressTag syncFrameId += value
//
simple SyncFaultInjector extends PacketFlowBase
{
    parameters:
        string action = default("");
        string messageTypes = default("8");
        string sequenceIds = default("");          // "*" = all
        int afterMessageType = default(0);
        int afterSeqOffset = default(0);
        double delay @unit(s) = default(0s);
        string field = default("");
        int value = default(0);
        int truncateTo = default(60);
        @class(nasctime::SyncFaultInjector);
}
