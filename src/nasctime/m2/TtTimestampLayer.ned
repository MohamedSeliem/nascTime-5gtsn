//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.m2;

import inet.protocolelement.measurement.IMeasurementLayer;
import inet.queueing.base.PacketFlowBase;

//
// M2-S0 (architecture validation, not a translator). Placed in the measurement-layer
// slot of an INET LayeredEthernetInterface, i.e. between the interface's upper layer
// and its MAC layer:
//   RX path (lowerLayerIn -> ingress -> upperLayerOut): role "ingress"
//   TX path (upperLayerIn -> egress -> lowerLayerOut):  role "egress"
// In mode "translator", ingress tags the Ethernet payload of every received frame with
// a TtTimestampTag, and egress recovers, verifies, logs and strips it. Mode "audit"
// only counts tagged frames; mode "probe" only records the packet structure. No mode
// changes a frame's bytes. Libraries: libnasctime_m2 (src/nasctime/m2/build.sh).
//
module TtTimestampLayer like IMeasurementLayer
{
    parameters:
        int ttId = default(-1);                 // identifies this translator in the tag
        string mode = default("translator");    // "translator" | "audit" | "probe" | "observer" (M2-S1: port events only, implies observePort)
        bool tagAtIngress = default(true);      // translator: tag frames on the RX path
        bool stripAtEgress = default(true);     // translator: remove tags on the TX path
        double timestampOffset @unit(s) = default(0s); // TEST ONLY (negative control): added to the ingress time
        int frameIdStride = default(1);         // TEST ONLY (negative control): frame counter increment
        bool failOnUnsupported = default(true); // unsupported packet structure: error (true) or count and pass (false)
        string logFile = default("");           // per-frame CSV log ("" = none); one file per role is derived from it
        bool selfTest = default(false);         // run the structure/tag self-test on synthetic frames at initialization
        // M2-S1 (all off by default; M2-S0 behaviour and logs unchanged)
        bool observePort = default(false);      // also record this interface's reception / MAC dequeue / transmission events per frame
        string ingressEvent = default("receptionEnded");   // TEST ONLY: "receptionStarted" (streaming receivers)
        string egressEvent = default("transmissionEnded"); // TEST ONLY: "transmissionStarted" | "enqueue"
        string pairingTest = default("");       // TEST ONLY: "rotate" writes each tx row with the previous row's identity
        ingress.role = "ingress";
        egress.role = "egress";
        *.ttId = this.ttId;
        *.mode = this.mode;
        *.tagAtIngress = this.tagAtIngress;
        *.stripAtEgress = this.stripAtEgress;
        *.timestampOffset = this.timestampOffset;
        *.frameIdStride = this.frameIdStride;
        *.failOnUnsupported = this.failOnUnsupported;
        *.logFile = this.logFile;
        *.selfTest = this.selfTest;
        *.observePort = this.observePort;
        *.ingressEvent = this.ingressEvent;
        *.egressEvent = this.egressEvent;
        *.pairingTest = this.pairingTest;
        @display("i=block/layer");
    gates:
        input upperLayerIn;
        output upperLayerOut;
        input lowerLayerIn;
        output lowerLayerOut;
    submodules:
        egress: TtTimestampProcessor {
            @display("p=150,100");
        }
        ingress: TtTimestampProcessor {
            @display("p=350,100");
        }
    connections:
        upperLayerIn --> { @display("m=n"); } --> egress.in;
        egress.out --> { @display("m=s"); } --> lowerLayerOut;
        lowerLayerIn --> { @display("m=s"); } --> ingress.in;
        ingress.out --> { @display("m=n"); } --> upperLayerOut;
}

simple TtTimestampProcessor extends PacketFlowBase
{
    parameters:
        string role;                 // "ingress" (RX path) | "egress" (TX path)
        int ttId;
        string mode;
        bool tagAtIngress;
        bool stripAtEgress;
        double timestampOffset @unit(s);
        int frameIdStride;
        bool failOnUnsupported;
        string logFile;
        bool selfTest;
        bool observePort;
        string ingressEvent;
        string egressEvent;
        string pairingTest;
        @class(nasctime::TtTimestampProcessor);
}
