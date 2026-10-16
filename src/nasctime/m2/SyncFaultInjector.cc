//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "SyncFaultInjector.h"

#include <sstream>

#include "inet/common/MemoryOutputStream.h"
#include "inet/common/checksum/ChecksumType_m.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021as/GptpPacket_m.h"

#include "TtGptpFrame.h"

namespace nasctime {

Define_Module(SyncFaultInjector);

SyncFaultInjector::~SyncFaultInjector()
{
    for (auto& h : held)
        delete h.packet;
    for (auto& d : delayed) {
        cancelAndDelete(d.first);
        delete d.second;
    }
    delete lastFollowUp;
}

void SyncFaultInjector::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL) {
        action = par("action").stdstringValue();
        static const std::set<std::string> known = {"", "drop", "dup", "holdUntilAfter", "delay", "rewrite", "truncate", "fuBefore",
                                                    "stripTag", "tagSeq", "tagFrameId"};
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
        afterSeqOffset = par("afterSeqOffset");
        delay = par("delay");
        field = par("field").stdstringValue();
        value = par("value");
        truncateTo = par("truncateTo");
    }
}

cGate *SyncFaultInjector::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

void SyncFaultInjector::forward(Packet *packet)
{
    pushOrSendPacket(packet, outputGate, consumer);
}

void SyncFaultInjector::recomputeFcs(Packet *packet)
{
    b fcsOffset = packet->getDataLength() - B(4);
    auto old = packet->peekDataAt<EthernetFcs>(fcsOffset);
    auto fcs = makeShared<EthernetFcs>();
    fcs->setFcsMode(old->getFcsMode() == FCS_MODE_UNDEFINED ? FCS_COMPUTED : old->getFcsMode());
    fcs->setFcs((uint32_t)inet::computeChecksum(packet->peekDataAt<BytesChunk>(b(0), fcsOffset)->getBytes(), CHECKSUM_ETHERNET_FCS));
    fcs->markImmutable();
    packet->replaceDataAt(fcs, fcsOffset, B(4));
}

// a second frame with the same content (a medium that duplicates creates a new frame)
Packet *SyncFaultInjector::copyWithNewTree(const Packet *packet) const
{
    auto copy = new Packet(packet->getName(), packet->peekAll());
    copy->copyTags(*packet);
    copy->setFrontOffset(packet->getFrontOffset());
    copy->setBackOffset(packet->getBackOffset());
    return copy;
}

Packet *SyncFaultInjector::rewritten(const Packet *packet, int type) const
{
    auto out = copyWithNewTree(packet);
    std::vector<gptpframe::Leaf> leaves;
    gptpframe::collectLeaves(out->peekData(), b(0), leaves);
    if (leaves.size() < 3)
        throw cRuntimeError("rewrite: unexpected frame structure");
    if (action == "truncate") {
        // the gPTP message replaced by its first truncateTo bytes (raw); FCS recomputed
        b off = leaves[1].offset;
        b len = out->getDataLength() - B(4) - off;
        MemoryOutputStream os;
        Chunk::serialize(os, out->peekDataAt(off, len));
        std::vector<uint8_t> bytes(os.getData().begin(), os.getData().begin() + truncateTo);
        auto mac = out->peekDataAt<EthernetMacHeader>(b(0));
        auto fcs = out->peekDataAt<EthernetFcs>(out->getDataLength() - B(4));
        auto res = new Packet(packet->getName());
        res->copyTags(*packet);
        res->insertAtBack(mac);
        res->insertAtBack(makeShared<BytesChunk>(bytes));
        if (res->getDataLength() < B(60)) {
            auto padding = makeShared<EthernetPadding>();
            padding->setChunkLength(B(60) - res->getDataLength());
            res->insertAtBack(padding);
        }
        res->insertAtBack(fcs);
        recomputeFcs(res);
        delete out;
        return res;
    }
    auto msg = dynamicPtrCast<const GptpBase>(leaves[1].chunk);
    if (!msg)
        throw cRuntimeError("rewrite: payload is not a gPTP chunk");
    auto copy = staticPtrCast<GptpBase>(msg->dupShared());
    if (field == "sequenceId")
        copy->setSequenceId(copy->getSequenceId() + value);
    else if (field == "versionPTP")
        copy->setVersionPTP(value);
    else if (field == "messageLength")
        copy->setMessageLengthField(value);
    else if (field == "domainNumber")
        copy->setDomainNumber(value);
    else
        throw cRuntimeError("Unknown field '%s'", field.c_str());
    copy->markImmutable();
    out->replaceDataAt(copy, leaves[1].offset, copy->getChunkLength());
    recomputeFcs(out);
    return out;
}

Packet *SyncFaultInjector::tagEdited(const Packet *packet) const
{
    auto out = copyWithNewTree(packet);
    auto f = gptpframe::parseFollowUp(out, 0);
    if (!f.fu)
        throw cRuntimeError("tag action on a frame that is not a Follow_Up");
    auto copy = staticPtrCast<GptpFollowUp>(f.fu->dupShared());
    if (action == "stripTag") {
        for (const auto& region : copy->getAllTags<TtSyncIngressTag>(b(0), copy->getChunkLength()))
            copy->removeTag<TtSyncIngressTag>(region.getOffset(), region.getLength());
    }
    else {
        bool seqAction = action == "tagSeq";
        int v = value;
        copy->mapAllTagsForUpdate<TtSyncIngressTag>(b(0), copy->getChunkLength(), [=] (b o, b l, const Ptr<TtSyncIngressTag>& t) {
            if (seqAction)
                t->setSequenceId(t->getSequenceId() + v);
            else
                t->setSyncFrameId(t->getSyncFrameId() + v);
        });
    }
    copy->markImmutable();
    out->replaceDataAt(copy, f.fuOffset, f.fuLength);
    return out;
}

void SyncFaultInjector::pushPacket(Packet *packet, const cGate *gate)
{
    Enter_Method("pushPacket");
    take(packet);
    b off;
    int type = gptpframe::messageType(packet, off);
    int seq = -1;
    if ((type == 0 || type == 8) && packet->getDataLength() >= off + B(32)) {
        auto h = packet->peekDataAt<BytesChunk>(off + B(30), B(2));
        seq = h->getByte(0) << 8 | h->getByte(1);
    }
    bool target = !action.empty() && seq >= 0 && types.count(type) && (allSeqs || seqs.count(seq));
    if (!target) {
        if (type == 8 && action == "fuBefore") {
            delete lastFollowUp;
            lastFollowUp = packet->dup();
        }
        forward(packet);
        // release frames held until this one has passed
        if (seq >= 0 && type == afterType) {
            for (auto it = held.begin(); it != held.end();) {
                if (it->seq + afterSeqOffset == seq) {
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
        auto copy = copyWithNewTree(packet);
        forward(packet);
        forward(copy);
    }
    else if (action == "holdUntilAfter")
        held.push_back({packet, seq});
    else if (action == "delay") {
        auto msg = new cMessage("release");
        delayed.push_back({msg, packet});
        scheduleAfter(delay, msg);
    }
    else if (action == "rewrite" || action == "truncate") {
        Packet *out = rewritten(packet, type);
        delete packet;
        forward(out);
    }
    else if (action == "stripTag" || action == "tagSeq" || action == "tagFrameId") {
        Packet *out = tagEdited(packet);
        delete packet;
        forward(out);
    }
    else if (action == "fuBefore") {
        // (Sync k) a Follow_Up for sequenceId k, made from the previous Follow_Up, sent ahead of
        // the Sync: as a medium that reorders would deliver it (the INET GM sends its Follow_Up
        // only when the Sync starts transmitting, so the real one cannot be moved ahead)
        if (type != 0 || !lastFollowUp)
            throw cRuntimeError("fuBefore applies to a Sync after at least one Follow_Up");
        auto fu = copyWithNewTree(lastFollowUp);
        std::vector<gptpframe::Leaf> leaves;
        gptpframe::collectLeaves(fu->peekData(), b(0), leaves);
        auto copy = staticPtrCast<GptpFollowUp>(dynamicPtrCast<const GptpFollowUp>(leaves[1].chunk)->dupShared());
        copy->setSequenceId(seq);
        copy->markImmutable();
        fu->replaceDataAt(copy, leaves[1].offset, copy->getChunkLength());
        recomputeFcs(fu);
        fu->setName("injectedFollowUp");
        forward(fu);
        forward(packet);
    }
}

void SyncFaultInjector::handleMessage(cMessage *msg)
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

void SyncFaultInjector::finish()
{
    recordScalar("acted", numActed);
    recordScalar("heldAtEnd", (double)held.size());
}

} // namespace nasctime
