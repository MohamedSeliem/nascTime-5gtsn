//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtSyncAudit.h"

#include "TtGptpFrame.h"

namespace nasctime {

Define_Module(TtSyncAudit);

cGate *TtSyncAudit::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

void TtSyncAudit::processPacket(Packet *packet)
{
    numFrames++;
    b off;
    if (gptpframe::messageType(packet, off) == 8)
        numFollowUps++;
    int n = gptpframe::countSyncTagsAllLevels(packet->peekAll());
    if (n > 0) {
        numTaggedFrames++;
        numTagRegions += n;
        EV_WARN << "TtSyncIngressTag reached a station: " << packet->getName() << EV_ENDL;
    }
}

void TtSyncAudit::finish()
{
    recordScalar("frames", numFrames);
    recordScalar("followUps", numFollowUps);
    recordScalar("framesWithSyncTag", numTaggedFrames);
    recordScalar("syncTagRegions", numTagRegions);
}

} // namespace nasctime
