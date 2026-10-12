//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.simulations.m1;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.node.ethernet.Eth1G;
import inet.node.ethernet.Eth10G;
import inet.node.inet.Router;
import inet.node.inet.StandardHost;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.corenetwork.bearerConfigurator.BearerConfigurator;
import simu5g.corenetwork.coreControl.CoreControl;
import simu5g.nodes.NrUe;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.world.radio.LteChannelControl;

//
// M1 minimal 5G Ethernet bridge (stage S1): nascTime's own copy of Simu5G 1.8.0's
// EthernetSessions network as used by its Ethernet-Bridge configuration, with the
// two Ethernet end stations renamed:
//   talker   -- the TSN-side device behind the UE (Simu5G: device[0])
//   listener -- the station on the UPF's N6 Ethernet LAN (Simu5G: dnStation)
// The UE runs an Ethernet PDU session in bridge mode; the UPF anchors it in its
// Ethernet bridge. server and router are kept, unused, so that the topology,
// submodule order (hence auto-assigned addresses) and random number use are the
// same as in the upstream reference; S1's acceptance test depends on that.
// Unmodified Simu5G and INET modules only.
//
network M1Bridge
{
    parameters:
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
        listener: StandardHost {
            @display("p=351,215;i=device/pc");
        }
        upf: Upf {
            @display("p=500,115");
        }
        gnb1: gNodeB {
            @display("p=250,350;is=vl");
        }
        ue[1]: NrUe {
            @display("p=500,500");
        }
        talker: StandardHost {
            @display("p=500,650;i=device/device");
        }
    connections:
        server.pppg++ <--> Eth10G <--> router.pppg++;
        router.pppg++ <--> Eth10G <--> upf.dnPppg;
        upf.dnEthg <--> Eth1G <--> listener.ethg++;
        upf.pppg++ <--> Eth10G <--> gnb1.ppp;
        talker.ethg++ <--> Eth1G <--> ue[0].ethg++;
}
