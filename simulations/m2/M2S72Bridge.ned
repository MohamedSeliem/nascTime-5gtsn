//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.simulations.m2;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.contract.INetworkNode;
import inet.node.ethernet.Eth10G;
import inet.node.ethernet.Eth1G;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import nasctime.tt.PassThroughTt;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.corenetwork.bearerConfigurator.BearerConfigurator;
import simu5g.corenetwork.coreControl.CoreControl;
import simu5g.nodes.NrUe;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.world.radio.LteChannelControl;

//
// M2-S7.2a (migration/m2-s7.2a-design.md rev. 2, 1.2): several UEs and DS-TTs, downlink, static roles.
// The M1Bridge network (simulations/m1/M1Bridge.ned) with the translators always present and the UE side
// replicated numUe times: ue[k] -- dsTt[k] -- talker[k] (talker[k] is gPTP slave k). One gNB, one UPF
// (one Ethernet session bridge), one NW-TT and one listener (gPTP grandmaster) are shared by every UE.
//
// The infrastructure submodules (channelControl ... carrierAggregation, server, router, listener, upf,
// gnb1) are declared in M1Bridge's order, so that with numUe = 1 the submodule order (hence the
// auto-assigned addresses and the module-path-based identities other than the vector indices) is the
// same as M1Bridge's; gate T0 (design 8.1) compares numUe = 1 with the single-UE M1Bridge runs.
// M1Bridge itself is not changed. Unmodified Simu5G and INET modules only.
//
network M2S72Bridge
{
    parameters:
        int numUe = default(1);
        **.cellularNic.hasSdap = default(true);
        upf.hasEthernetBridge = default(true);
        @display("i=block/network2;bgb=1000,700");
    submodules:
        channelControl: LteChannelControl {
            @display("p=50,25;is=s");
        }
        configurator: Ipv4NetworkConfigurator {
            @display("p=50,125;is=s");
        }
        binder: Binder {
            @display("p=50,175;is=s");
        }
        coreControl: CoreControl {
            @display("p=50,375;is=s");
        }
        bearerConfigurator: BearerConfigurator {
            @display("p=50,225;is=s");
        }
        carrierAggregation: CarrierAggregation {
            @display("p=50,275;is=s");
        }
        server: StandardHost {
            @display("p=212,118;is=n;i=device/server");
        }
        router: Router {
            @display("p=351,115;i=device/smallrouter");
        }
        listener: <default("StandardHost")> like INetworkNode {
            @display("p=351,215;i=device/pc");
        }
        upf: Upf {
            @display("p=500,115");
        }
        gnb1: gNodeB {
            @display("p=250,350;is=vl");
        }
        ue[numUe]: NrUe {
            @display("p=500,500,row,120");
        }
        talker[numUe]: <default("StandardHost")> like INetworkNode {
            @display("p=500,650,row,120;i=device/device");
        }
        dsTt[numUe]: PassThroughTt {
            @display("p=560,575,row,120");
        }
        nwTt: PassThroughTt {
            @display("p=500,215");
        }
    connections:
        server.pppg++ <--> Eth10G <--> router.pppg++;
        router.pppg++ <--> Eth10G <--> upf.dnPppg;
        upf.dnEthg <--> Eth1G <--> nwTt.ethg++;
        nwTt.ethg++ <--> Eth1G <--> listener.ethg++;
        upf.pppg++ <--> Eth10G <--> gnb1.ppp;
        for k=0..numUe-1 {
            ue[k].ethg++ <--> Eth1G <--> dsTt[k].ethg++;
            dsTt[k].ethg++ <--> Eth1G <--> talker[k].ethg++;
        }
}
