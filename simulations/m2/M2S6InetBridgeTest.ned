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
import inet.node.tsn.TsnSwitch;

//
// M2-S6 R-INET cross-check (migration/m2-s6-design.md rev. 2, 6.3): the M2S5ChainTest chain with the
// two translators replaced by INET 4.7 gPTP bridges (TsnSwitch, BRIDGE_NODE): gm -- br1 -- 1 us --
// br2 -- 100 Mb/s -- slave, same link delays and rates. A comparison, not ground truth: an INET bridge
// measures its own Pdelay, residence on its own raw clock and writes its own gmRateRatio (design G5).
//
network M2S6InetBridgeTest
{
    parameters:
        double gmLinkDelay @unit(s) = default(50ns);
        double brLinkDelay @unit(s) = default(1us);
        double slaveLinkDelay @unit(s) = default(50ns);
    submodules:
        gm: <default("StandardHost")> like INetworkNode {
            @display("p=100,100");
        }
        br1: TsnSwitch {
            @display("p=250,100");
        }
        br2: TsnSwitch {
            @display("p=400,100");
        }
        slave: <default("StandardHost")> like INetworkNode {
            @display("p=550,100");
        }
    connections:
        gm.ethg++ <--> Eth1G { delay = parent.gmLinkDelay; } <--> br1.ethg++;
        br1.ethg++ <--> Eth1G { delay = parent.brLinkDelay; } <--> br2.ethg++;
        br2.ethg++ <--> Eth100M { delay = parent.slaveLinkDelay; } <--> slave.ethg++;
}
