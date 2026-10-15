//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtPdelayEngine.h"

#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021q/Ieee8021qTagHeader_m.h"

namespace nasctime {

Define_Module(TtPdelayEngine);

static const MacAddress GPTP_ADDRESS("01:80:C2:00:00:0E");

void TtPdelayEngine::initialize()
{
    terminate = par("terminate");
    requester = par("requester");
    responder = par("responder");
    if (terminate || requester || responder)
        throw cRuntimeError("TtPdelayEngine: only the passive mode is implemented in this version");
}

int TtPdelayEngine::classify(const Packet *packet, b& gptpOffset)
{
    b length = packet->getDataLength();
    if (length < B(14))
        return -1;
    const auto& mac = packet->peekDataAt<EthernetMacHeader>(b(0));
    if (mac->getDest() != GPTP_ADDRESS)
        return -1;
    b offset = B(14);
    int typeOrLength = mac->getTypeOrLength();
    if (typeOrLength == 0x8100) {
        if (length < B(18))
            return -1;
        const auto& tag = packet->peekDataAt<Ieee8021qTagEpdHeader>(offset);
        typeOrLength = tag->getTypeOrLength();
        offset += B(4);
    }
    if (typeOrLength != 0x88F7)
        return -1;
    gptpOffset = offset;
    if (length < offset + B(1))
        return -2;
    const auto& first = packet->peekDataAt<BytesChunk>(offset, B(1));
    return first->getByte(0) & 0x0F;
}

bool TtPdelayEngine::offerReceived(Packet *packet)
{
    Enter_Method("offerReceived");
    b off;
    int type = classify(packet, off);
    if (type >= 0 && isPdelayType(type))
        numPassedPdelay[type]++;
    return false;   // passive: never taken
}

void TtPdelayEngine::handleMessage(cMessage *msg)
{
    throw cRuntimeError("Unexpected message");
}

void TtPdelayEngine::finish()
{
    recordScalar("passedPdelayReq", numPassedPdelay[2]);
    recordScalar("passedPdelayResp", numPassedPdelay[3]);
    recordScalar("passedPdelayRespFollowUp", numPassedPdelay[10]);
}

} // namespace nasctime
