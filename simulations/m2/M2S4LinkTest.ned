//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.simulations.m2;

import inet.node.ethernet.Eth1G;
import inet.node.inet.StandardHost;
import nasctime.tt.PassThroughTt;

//
// M2-S4 unit topology (migration/m2-s4-design.md 8.1): two translators joined
// TSN port to TSN port (ttA.eth[1] <-> ttB.eth[1]), each eth[0] connected to a station
// that sends background frames across the A-B link. The A-B link has a separate delay
// per direction (linkDelayAB, linkDelayBA) for the asymmetric-link limitation test.
// No 5G system; no TtTimestampLayer. Used to validate the TtPdelayPort requester and
// responder engine-to-engine, and the fault handling.
//
network M2S4LinkTest
{
    parameters:
        double linkDelayAB @unit(s) = default(50ns);
        double linkDelayBA @unit(s) = default(50ns);
    submodules:
        stA: StandardHost {
            @display("p=100,100");
        }
        ttA: PassThroughTt {
            parameters:
                @display("p=250,100");
            gates:
                ethg[2];
        }
        ttB: PassThroughTt {
            parameters:
                @display("p=400,100");
            gates:
                ethg[2];
        }
        stB: StandardHost {
            @display("p=550,100");
        }
    connections:
        stA.ethg++ <--> Eth1G <--> ttA.ethg[0];
        stB.ethg++ <--> Eth1G <--> ttB.ethg[0];
        ttA.ethg$o[1] --> Eth1G { delay = parent.linkDelayAB; } --> ttB.ethg$i[1];
        ttB.ethg$o[1] --> Eth1G { delay = parent.linkDelayBA; } --> ttA.ethg$i[1];
}
