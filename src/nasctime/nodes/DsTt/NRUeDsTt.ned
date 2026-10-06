//
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork), Afshin Zanganeh and How-Hang Liu
//          (Technical University of Dresden)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

package nasctime.nodes.DsTt;

import inet.linklayer.ethernet.basic.EthernetInterface;
import simu5g.nodes.NrUe;
import simu5g.stack.sdap.common.ReflectiveQosTable;

module NRUeDsTt extends NrUe
{
    parameters:
        @display("i=device/pocketpc;bgb=858,750");
        numEthInterfaces = default(1);
        eth[*].typename = default("EthernetInterface");
        encap.typename = default("EthernetEncapsulation");

    gates:
        inout ethg @labels(EthernetSignal);

    submodules:
        // Simu5G implements flow learning and expiry in
        // simu5g/stack/sdap/common/ReflectiveQosTable.cc.
        reflectiveQosTable: ReflectiveQosTable {
            @display("p=600,650");
        }

    connections:
        ethg <--> eth[0].phys;
}
