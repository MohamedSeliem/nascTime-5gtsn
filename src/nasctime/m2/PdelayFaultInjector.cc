//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "PdelayFaultInjector.h"

#include <sstream>

#include "inet/common/MemoryOutputStream.h"
#include "inet/common/checksum/ChecksumType_m.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021as/GptpPacket_m.h"

#include "TtPdelayEngine.h"

namespace nasctime {

Define_Module(PdelayFaultInjector);

PdelayFaultInjector::~PdelayFaultInjector()
{
    for (auto& h : held)
        delete h.packet;
    for (auto& d : delayed) {
        cancelAndDelete(d.first);
        delete d.second;
    }
}

void PdelayFaultInjector::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL) {
        action = par("action").stdstringValue();
        static const std::set<std::string> known = {"", "drop", "dup", "dupAfter", "holdUntilAfter", "delay", "rewrite", "truncate", "badFcs"};
        if (!known.count(action))
            throw cRuntimeError("Unknown action '%s'", action.c_str());
        std::istringstream ts(par("messageTypes").stdstringValue());
        for (int t; ts >> t;)
            types.insert(t);
        std::string sq = par("sequenceIds").stdstringValue();
        if (sq == "*")
            allSeqs = true;
        else {
            std::istringstream ss(sq);
            for (int s; ss >> s;)
                seqs.insert(s);
        }
        afterType = par("afterMessageType");
        delay = par("delay");
        field = par("field").stdstringValue();
        value = par("value");
        truncateTo = par("truncateTo");
    }
}

cGate *PdelayFaultInjector::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

void PdelayFaultInjector::forward(Packet *packet)
{
    pushOrSendPacket(packet, outputGate, consumer);
}

void PdelayFaultInjector::recomputeFcs(Packet *packet)
{
    auto oldFcs = packet->popAtBack<EthernetFcs>(B(4));
    auto fcs = makeShared<EthernetFcs>();
    fcs->setFcsMode(FCS_COMPUTED);
    fcs->setFcs((uint32_t)inet::computeChecksum(packet->peekDataAsBytes()->getBytes(), CHECKSUM_ETHERNET_FCS));
    packet->insertAtBack(fcs);
}

Packet *PdelayFaultInjector::rewritten(Packet *packet) const
{
    // data part: [EthernetMacHeader][gPTP 54 B][EthernetFcs]
    auto copy = packet->dup();
    copy->trim();
    auto mac = copy->popAtFront<EthernetMacHeader>();
    copy->popAtBack<EthernetFcs>(B(4));
    auto rest = copy->peekData();   // gPTP message (and any padding)
    int type = copy->peekDataAt<BytesChunk>(b(0), B(1))->getByte(0) & 0x0F;
    Ptr<Chunk> gptp;
    if (action == "truncate") {
        MemoryOutputStream out;
        Chunk::serialize(out, rest);
        std::vector<uint8_t> bytes(out.getData().begin(), out.getData().begin() + truncateTo);
        gptp = makeShared<BytesChunk>(bytes);
    }
    else {
        Ptr<GptpBase> msg;
        if (type == 2)
            msg = staticPtrCast<GptpBase>(copy->peekDataAt<GptpPdelayReq>(b(0), B(54))->dupShared());
        else if (type == 3)
            msg = staticPtrCast<GptpBase>(copy->peekDataAt<GptpPdelayResp>(b(0), B(54))->dupShared());
        else
            msg = staticPtrCast<GptpBase>(copy->peekDataAt<GptpPdelayRespFollowUp>(b(0), B(54))->dupShared());
        if (field == "sequenceId")
            msg->setSequenceId(value);
        else if (field == "versionPTP")
            msg->setVersionPTP(value);
        else if (field == "messageLength")
            msg->setMessageLengthField(value);
        else if (field == "domainNumber")
            msg->setDomainNumber(value);
        else if (field == "requestingPortNumber") {
            if (auto r = dynamicPtrCast<GptpPdelayResp>(msg)) {
                PortIdentity p = r->getRequestingPortIdentity();
                p.portNumber = value;
                r->setRequestingPortIdentity(p);
            }
            else if (auto f = dynamicPtrCast<GptpPdelayRespFollowUp>(msg)) {
                PortIdentity p = f->getRequestingPortIdentity();
                p.portNumber = value;
                f->setRequestingPortIdentity(p);
            }
            else
                throw cRuntimeError("requestingPortNumber: not a Resp/Resp_Follow_Up");
        }
        else
            throw cRuntimeError("Unknown field '%s'", field.c_str());
        gptp = msg;
    }
    auto out = new Packet(packet->getName());
    out->copyTags(*packet);
    out->insertAtBack(mac);
    out->insertAtBack(gptp);
    if (out->getDataLength() < B(60)) {
        auto padding = makeShared<EthernetPadding>();
        padding->setChunkLength(B(60) - out->getDataLength());
        out->insertAtBack(padding);
    }
    out->insertAtBack(makeShared<EthernetFcs>());
    recomputeFcs(out);
    delete copy;
    return out;
}

void PdelayFaultInjector::pushPacket(Packet *packet, const cGate *gate)
{
    Enter_Method("pushPacket");
    take(packet);
    b off;
    int type = TtPdelayEngine::classify(packet, off);
    int seq = -1;
    if (type >= 0 && TtPdelayEngine::isPdelayType(type) && packet->getDataLength() >= off + B(32))
        seq = (int)(packet->peekDataAt<BytesChunk>(off + B(30), B(2))->getByte(0) << 8 | packet->peekDataAt<BytesChunk>(off + B(31), B(1))->getByte(0));
    bool target = !action.empty() && seq >= 0 && types.count(type) && (allSeqs || seqs.count(seq));
    if (!target) {
        forward(packet);
        // release frames held until this one has passed
        if (seq >= 0 && type == afterType) {
            for (auto it = held.begin(); it != held.end();) {
                if (it->seq == seq) {
                    forward(it->packet);
                    it = held.erase(it);
                }
                else
                    ++it;
            }
        }
        return;
    }
    numActed++;
    EV_WARN << "TEST fault injection: " << action << " on gPTP type " << type << " seq " << seq << EV_ENDL;
    if (action == "drop")
        delete packet;
    else if (action == "dup") {
        auto copy = packet->dup();
        forward(packet);
        forward(copy);
    }
    else if (action == "dupAfter") {
        held.push_back({packet->dup(), seq});
        forward(packet);
    }
    else if (action == "holdUntilAfter")
        held.push_back({packet, seq});
    else if (action == "delay") {
        auto msg = new cMessage("release");
        delayed.push_back({msg, packet});
        scheduleAfter(delay, msg);
    }
    else if (action == "rewrite" || action == "truncate") {
        Packet *out = rewritten(packet);
        delete packet;
        forward(out);
    }
    else if (action == "badFcs") {
        auto fcs = packet->popAtBack<EthernetFcs>(B(4));
        auto bad = makeShared<EthernetFcs>();
        bad->setFcsMode(FCS_COMPUTED);
        bad->setFcs(fcs->getFcs() ^ 0xFFFFFFFFu);
        packet->insertAtBack(bad);
        forward(packet);
    }
}

void PdelayFaultInjector::handleMessage(cMessage *msg)
{
    for (auto it = delayed.begin(); it != delayed.end(); ++it) {
        if (it->first == msg) {
            Packet *p = it->second;
            delayed.erase(it);
            delete msg;
            forward(p);
            return;
        }
    }
    PacketFlowBase::handleMessage(msg);
}

void PdelayFaultInjector::finish()
{
    recordScalar("acted", numActed);
    recordScalar("heldAtEnd", (double)held.size());
}

} // namespace nasctime
