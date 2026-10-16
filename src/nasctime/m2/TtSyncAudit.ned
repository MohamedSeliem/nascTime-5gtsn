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
// M2-S5 containment audit for a station's (default-empty) trafficConditionerLayer slot:
// counts received frames that carry a TtSyncIngressTag; changes nothing.
//
module TtSyncAuditLayer like ITrafficConditionerLayer
{
    parameters:
        @display("i=block/layer");
    gates:
        input upperLayerIn;
        output upperLayerOut;
        input lowerLayerIn;
        output lowerLayerOut;
    submodules:
        audit: TtSyncAudit {
            @display("p=150,100");
        }
    connections:
        upperLayerIn --> lowerLayerOut;
        lowerLayerIn --> audit.in;
        audit.out --> upperLayerOut;
}

simple TtSyncAudit extends PacketFlowBase
{
    parameters:
        @class(nasctime::TtSyncAudit);
}

