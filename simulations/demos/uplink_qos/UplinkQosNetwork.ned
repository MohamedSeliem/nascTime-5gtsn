//
//                  nascTime
//
// Authors: Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

package nasctime.simulations.demos.uplink_qos;

import inet.networklayer.configurator.ipv4.Ipv4NetworkConfigurator;
import inet.networklayer.ipv4.RoutingTableRecorder;
import inet.node.tsn.TsnDevice;
import nasctime.nodes.DsTt.DsTt;
import nasctime.nodes.DsTt.NRUeDsTt;
import nasctime.nodes.NwTt.NwTt;
import ned.DatarateChannel;
import simu5g.common.binder.Binder;
import simu5g.common.carrierAggregation.CarrierAggregation;
import simu5g.nodes.Upf;
import simu5g.nodes.gNodeB;
import simu5g.world.radio.LteChannelControl;

// Minimal single-path uplink QoS experiment. It intentionally contains no
// standby UE, TSN switch, ScenarioManager, RouteSwitcher, TSN AF, BMCA, or
// gPTP sideband.
network UplinkQosNetwork
{
    parameters:
        @display("bgb=1350,430");

    types:
        channel Eth1G extends DatarateChannel {
            datarate = 1Gbps;
            delay = 0.1us;
        }
        channel Eth10G extends DatarateChannel {
            datarate = 10Gbps;
            delay = 0.1us;
        }

    submodules:
        channelControl: LteChannelControl { @display("p=50,50;is=s"); }
        routingRecorder: RoutingTableRecorder { @display("p=50,100;is=s"); }
        configurator: Ipv4NetworkConfigurator {
            @display("p=50,150;is=s");
            config = xmldoc("ip_config.xml");
        }
        binder: Binder { @display("p=50,200;is=s"); }
        carrierAggregation: CarrierAggregation { @display("p=50,250;is=s"); }

        tsnDeviceA: TsnDevice { @display("p=160,350"); }
        nwTt: NwTt {
            @display("p=350,350");
            ueAddress = "ue";
            localAddress = "nwTt";
        }
        upf: Upf { @display("p=550,350"); }
        gnb: gNodeB { @display("p=750,350;is=vl"); }
        ue: NRUeDsTt { @display("p=930,350"); }
        dsTt: DsTt { @display("p=1090,350"); }
        tsnDeviceB: TsnDevice { @display("p=1260,350"); }

    connections:
        tsnDeviceA.ethg++ <--> Eth1G <--> nwTt.tsnEthg;
        nwTt.filterGate <--> Eth10G <--> upf.dnPppg;
        upf.pppg++ <--> Eth10G <--> gnb.ppp;
        ue.ethg <--> Eth1G <--> dsTt.ueEthg;
        dsTt.tsnEthg <--> Eth1G <--> tsnDeviceB.ethg++;
}
