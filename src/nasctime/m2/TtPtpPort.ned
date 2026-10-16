//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.m2;

import inet.protocolelement.trafficconditioner.ITrafficConditionerLayer;
import inet.queueing.base.PacketFlowBase;
import inet.queueing.contract.IPacketFlow;

//
// M2-S5: online downlink two-step gPTP correction at a translator's TSN-facing port
// (migration/m2-s5-design.md). Replaces TtPdelayPort (M2-S4, unchanged) in the
// trafficConditionerLayer slot of the TT's eth[1], directly above the M2-S0/S1
// TtTimestampLayer. Contains the M2-S4 classes unchanged, under the same names
// (engine, tx, rx, same parameters), and two new elements:
//   RX: lowerLayerIn -> rx (Pdelay terminated by the engine) -> syncIn -> upperLayerOut
//   TX: upperLayerIn -> tx (engine frames injected) -> syncOut -> lowerLayerOut
// syncIn (NW-TT, syncIngress = true): Sync ingress time, Follow_Up + upstream link delay,
//        TtSyncIngressTag, FCS.
// syncOut (DS-TT, syncEgress = true): Sync egress time, Follow_Up + residence time, tag
//        removed, FCS; fail-closed; FIFO hold.
// All new parameters default off: then the port behaves as TtPdelayPort (gate G0).
// Libraries: libnasctime_m2.
//
module TtPtpPort like ITrafficConditionerLayer
{
    parameters:
        bool terminate = default(false);        // M2-S4: divert Pdelay frames to the engine
        bool requester = default(false);        // M2-S4
        bool responder = default(false);        // M2-S4
        bool syncIngress = default(false);      // M2-S5 NW-TT role (RX)
        bool syncEgress = default(false);       // M2-S5 DS-TT role (TX)
        bool syncEgressAudit = default(false);  // M2-S5 gate V0: log the tags of transmitted Follow_Ups, change nothing
        @display("i=block/layer");
    gates:
        input upperLayerIn;
        output upperLayerOut;
        input lowerLayerIn;
        output lowerLayerOut;
    submodules:
        engine: TtPdelayEngine {
            terminate = parent.terminate;
            requester = parent.requester;
            responder = parent.responder;
            @display("p=250,100");
        }
        tx: TtPdelayFlow {
            role = "tx";
            @display("p=150,200");
        }
        rx: TtPdelayFlow {
            role = "rx";
            @display("p=350,200");
        }
        syncOut: TtSyncEgress {
            mode = parent.syncEgress ? "correct" : (parent.syncEgressAudit ? "audit" : "off");
            @display("p=150,300");
        }
        syncIn: TtSyncIngress {
            enabled = parent.syncIngress;
            @display("p=350,100");
        }
        // TEST ONLY (fault cases FS9c/FS9d): a fault injector between the Pdelay engine and
        // syncIn on the RX path, for frame representations that INET's grandmaster cannot
        // transmit itself (it parses its own transmitted gPTP frames). Absent by default.
        rxTest: <default("")> like IPacketFlow if typename != "" {
            @display("p=450,150");
        }
    connections:
        upperLayerIn --> { @display("m=n"); } --> tx.in;
        tx.out --> { @display("m=s"); } --> syncOut.in;
        syncOut.out --> lowerLayerOut;
        lowerLayerIn --> { @display("m=s"); } --> rx.in;
        rx.out --> { @display("m=n"); } --> syncIn.in if !exists(rxTest);
        rx.out --> { @display("m=n"); } --> rxTest.in if exists(rxTest);
        rxTest.out --> syncIn.in if exists(rxTest);
        syncIn.out --> upperLayerOut;
}

//
// NW-TT ingress element of TtPtpPort (RX). See TtSyncIngress.h.
//
simple TtSyncIngress extends PacketFlowBase
{
    parameters:
        bool enabled = default(false);
        int ttId = default(-1);
        int domainNumber = default(0);
        string engineModule = default("^.engine");
        bool selfCheck = default(true);            // verify every rewrite (design 5.1 step 7)
        bool selfTest = default(false);            // synthetic-frame self-test at initialization
        string logFile = default("");              // ".sync.csv" appended; times in integer ps
        // TEST ONLY (negative controls, design 8.1); "" / -1s = correct behaviour
        string correctionTest = default("");       // "noLinkDelay" | "lupTwice" | "rr" | "noFcs" | "tsiEnd" | "syncCf"
        double fixedLinkDelay @unit(s) = default(-1s);
        @class(nasctime::TtSyncIngress);
        @display("i=block/timer");
}

//
// DS-TT egress element of TtPtpPort (TX). See TtSyncEgress.h.
//
simple TtSyncEgress extends PacketFlowBase
{
    parameters:
        string mode @enum("off","audit","correct") = default("off");
        int ttId = default(-1);
        int domainNumber = default(0);
        double holdTimeout @unit(s) = default(10ms);
        bool crossCheckFrameId = default(true);
        bool selfCheck = default(true);
        string logFile = default("");
        // TEST ONLY (negative controls / hold cases, design 7.4, 8.1)
        string egressTest = default("");           // "tseEnd" | "tseSlot" | "prevSync" | "noFcs" | "noStrip" | "forwardInvalid" | "noHold"
        int dropSyncSeq = default(-1);             // the Sync with this sequenceId is lost below the hold point (H4)
        @class(nasctime::TtSyncEgress);
        @display("i=block/timer");
}

