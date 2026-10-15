//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.m2;

import inet.protocolelement.trafficconditioner.ITrafficConditionerLayer;
import inet.queueing.base.PacketFlowBase;

//
// M2-S4: link-local gPTP Pdelay termination at a translator's TSN-facing port
// (migration/m2-s4-design.md). Placed in the (default-empty) trafficConditionerLayer
// slot of the TT's eth[1] LayeredEthernetInterface, directly above the M2-S0/M2-S1
// TtTimestampLayer in the measurementLayer slot:
//   RX path (lowerLayerIn -> rx -> upperLayerOut): frames to 01-80-C2-00-00-0E with
//      EtherType 0x88F7 and gPTP messageType 2/3/10 (Pdelay_Req/Resp/Resp_Follow_Up)
//      are handed to the engine and never reach the bridge (terminate = true);
//      every other frame (incl. Sync/Follow_Up) passes unchanged.
//   TX path (upperLayerIn -> tx -> lowerLayerOut): unchanged; the engine's own Pdelay
//      frames are injected here.
// With terminate = false (passive) nothing is diverted or injected: equality control.
// No Sync/Follow_Up is held, rewritten or corrected. Libraries: libnasctime_m2.
//
module TtPdelayPort like ITrafficConditionerLayer
{
    parameters:
        bool terminate = default(false);        // divert Pdelay frames to the engine (false: count only)
        bool requester = default(false);        // send Pdelay_Req on this port (needs terminate)
        bool responder = default(false);        // answer Pdelay_Req on this port (needs terminate)
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
    connections:
        upperLayerIn --> { @display("m=n"); } --> tx.in;
        tx.out --> { @display("m=s"); } --> lowerLayerOut;
        lowerLayerIn --> { @display("m=s"); } --> rx.in;
        rx.out --> { @display("m=n"); } --> upperLayerOut;
}

//
// One direction of TtPdelayPort. rx: hands frames classified as Pdelay to the engine
// (when terminating); tx: forwards, and accepts the engine's frames (inject()).
// Packet streaming is not supported (store-and-forward bridging), as in TtTimestampLayer.
//
simple TtPdelayFlow extends PacketFlowBase
{
    parameters:
        string role;                 // "rx" | "tx"
        string engineModule = default("^.engine");
        @class(nasctime::TtPdelayFlow);
}

//
// Per-port Pdelay engine (no gates). See TtPdelayEngine.h.
//
simple TtPdelayEngine
{
    parameters:
        bool terminate;
        bool requester;
        bool responder;
        @class(nasctime::TtPdelayEngine);
        @display("i=block/cogwheel");
}
