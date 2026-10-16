//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtSyncIngress.h"

#include "TtPdelayEngine.h"

namespace nasctime {

Define_Module(TtSyncIngress);

void TtSyncIngress::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL && par("enabled").boolValue())
        throw cRuntimeError("TtSyncIngress: the correction is not implemented at this commit (skeleton for gate G0)");
}

cGate *TtSyncIngress::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

void TtSyncIngress::processPacket(Packet *packet)
{
    b off;
    int type = TtPdelayEngine::classify(packet, off);
    if (type == 0)
        numSyncSeen++;
    else if (type == 8)
        numFollowUpSeen++;
}

void TtSyncIngress::finish()
{
    recordScalar("syncSeen", numSyncSeen);
    recordScalar("followUpSeen", numFollowUpSeen);
}

} // namespace nasctime
