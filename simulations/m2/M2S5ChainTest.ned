//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.simulations.m2;

import inet.node.contract.INetworkNode;
import inet.node.ethernet.Eth100M;
import inet.node.ethernet.Eth1G;
import nasctime.tt.PassThroughTt;

//
// M2-S5 unit topology (migration/m2-s5-design.md 7.4, decision 6): the bridge without the
// 5G system. gm (gPTP grandmaster) -- ttN (NW-TT, TSN port eth[1]) -- cable -- ttD (DS-TT;
// eth[0] is its 5G side, eth[1] its TSN port) -- slave (gPTP slave). The slave link runs at
// a lower rate (default 100 Mb/s) so that a Sync can wait in the DS-TT's MAC FIFO behind a
// background frame while its Follow_Up arrives (FIFO hold), and so that first-bit and
// last-bit timestamp errors do not cancel (different port rates). Link delays are
// parameters (sub-ns variant).
//
network M2S5ChainTest
{
    parameters:
        double gmLinkDelay @unit(s) = default(50ns);
        double ttLinkDelay @unit(s) = default(1us);
        double slaveLinkDelay @unit(s) = default(50ns);
    submodules:
        gm: <default("StandardHost")> like INetworkNode {
            @display("p=100,100");
        }
        ttN: PassThroughTt {
            parameters:
                @display("p=250,100");
            gates:
                ethg[2];
        }
        ttD: PassThroughTt {
            parameters:
                @display("p=400,100");
            gates:
                ethg[2];
        }
        slave: <default("StandardHost")> like INetworkNode {
            @display("p=550,100");
        }
    connections:
        gm.ethg++ <--> Eth1G { delay = parent.gmLinkDelay; } <--> ttN.ethg[1];
        ttN.ethg[0] <--> Eth1G { delay = parent.ttLinkDelay; } <--> ttD.ethg[0];
        ttD.ethg[1] <--> Eth100M { delay = parent.slaveLinkDelay; } <--> slave.ethg++;
}
