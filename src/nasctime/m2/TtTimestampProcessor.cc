//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtTimestampProcessor.h"

#include <algorithm>
#include <cinttypes>
#include <filesystem>

#include "inet/common/Simsignals.h"
#include "inet/common/TimeTag_m.h"
#include "inet/common/packet/chunk/ByteCountChunk.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/common/packet/chunk/SequenceChunk.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021q/Ieee8021qTagHeader_m.h"
#include "inet/physicallayer/wired/ethernet/EthernetPhyHeader_m.h"

namespace nasctime {

Define_Module(TtTimestampProcessor);

static std::string shortTypeName(const Chunk *chunk)
{
    std::string name = opp_typename(typeid(*chunk));
    if (name.rfind("inet::", 0) == 0)
        name = name.substr(6);
    return name;
}

void TtTimestampProcessor::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL) {
        std::string r = par("role").stdstringValue();
        if (r == "ingress")
            role = INGRESS;
        else if (r == "egress")
            role = EGRESS;
        else
            throw cRuntimeError("Unknown role '%s'", r.c_str());
        std::string m = par("mode").stdstringValue();
        if (m == "translator")
            mode = TRANSLATOR;
        else if (m == "audit")
            mode = AUDIT;
        else if (m == "probe")
            mode = PROBE;
        else if (m == "observer")
            mode = OBSERVER;
        else
            throw cRuntimeError("Unknown mode '%s'", m.c_str());
        ttId = par("ttId");
        tagAtIngress = par("tagAtIngress");
        stripAtEgress = par("stripAtEgress");
        timestampOffset = par("timestampOffset");
        frameIdStride = par("frameIdStride");
        failOnUnsupported = par("failOnUnsupported");
        if (mode == TRANSLATOR && ttId < 0)
            throw cRuntimeError("Mode 'translator' needs ttId >= 0");
        if (frameIdStride < 1)
            throw cRuntimeError("frameIdStride must be >= 1");
        std::string logFile = par("logFile").stdstringValue();
        if (!logFile.empty()) {
            std::string path = logFile + "." + r + ".csv";
            std::filesystem::path p(path);
            if (p.has_parent_path())
                std::filesystem::create_directories(p.parent_path());
            log.open(path, std::ios::out | std::ios::trunc);
            if (!log)
                throw cRuntimeError("Cannot open log file '%s'", path.c_str());
            log << "event,t,ttId,role,frameId,ingressTime,ingressTtId,regions,etherType,pcp,vid,payloadLen,payloadHash,signature,note\n";
        }
        // M2-S1 port observation (off by default: M2-S0 behaviour and logs unchanged)
        observePort = par("observePort").boolValue() || mode == OBSERVER;
        std::string ie = par("ingressEvent").stdstringValue();
        if (ie == "receptionEnded")
            ingressEvent = RX_END;
        else if (ie == "receptionStarted")
            ingressEvent = RX_START;
        else
            throw cRuntimeError("Unknown ingressEvent '%s'", ie.c_str());
        std::string ee = par("egressEvent").stdstringValue();
        if (ee == "transmissionEnded")
            egressEvent = EG_TX_END;
        else if (ee == "transmissionStarted")
            egressEvent = EG_TX_START;
        else if (ee == "enqueue")
            egressEvent = EG_SLOT;
        else
            throw cRuntimeError("Unknown egressEvent '%s'", ee.c_str());
        std::string pt = par("pairingTest").stdstringValue();
        if (pt == "rotate")
            pairingRotate = true;
        else if (!pt.empty())
            throw cRuntimeError("Unknown pairingTest '%s'", pt.c_str());
        if (!observePort && (ingressEvent != RX_END || egressEvent != EG_TX_END || pairingRotate))
            throw cRuntimeError("ingressEvent, egressEvent and pairingTest need observePort = true");
        if (observePort) {
            // processor -> TtTimestampLayer -> network interface (LayeredEthernetInterface)
            interfaceModule = getParentModule()->getParentModule();
            transmitterModule = interfaceModule->findModuleByPath(".phyLayer.transmitter");
            receiverModule = interfaceModule->findModuleByPath(".phyLayer.receiver");
            macEmitterModule = interfaceModule->findModuleByPath(".macLayer.outboundEmitter");
            macQueueModule = interfaceModule->findModuleByPath(".macLayer.queue");
            if (!transmitterModule || !receiverModule || !macEmitterModule || !macQueueModule)
                throw cRuntimeError("observePort: %s lacks phyLayer.transmitter/receiver or macLayer.outboundEmitter/queue",
                        interfaceModule->getFullPath().c_str());
            if (role == EGRESS) {
                interfaceModule->subscribe(transmissionStartedSignal, this);
                interfaceModule->subscribe(transmissionEndedSignal, this);
                interfaceModule->subscribe(packetSentToLowerSignal, this);
                interfaceModule->subscribe(packetDroppedSignal, this);
            }
            else {
                interfaceModule->subscribe(receptionStartedSignal, this);
                interfaceModule->subscribe(receptionEndedSignal, this);
            }
            if (!logFile.empty()) {
                std::string path = logFile + "." + r + ".port.csv";
                portLog.open(path, std::ios::out | std::ios::trunc);
                if (!portLog)
                    throw cRuntimeError("Cannot open log file '%s'", path.c_str());
                portLog << "event,t,ttId,role,treeId,tagged,frameId,ingressTime,ingressTtId,etherType,pcp,vid,payloadLen,hash,txHash,"
                           "tRxStart,tRxEnd,tSlot,tDequeue,tTxStart,tTxEnd,egressTime,residence,note\n";
            }
        }
        if (par("selfTest"))
            selfTest();
    }
}

static std::string ts(simtime_t t)
{
    return t < SIMTIME_ZERO ? std::string() : t.str();
}

const Packet *TtTimestampProcessor::encapsulatedPacket(cObject *obj)
{
    if (auto packet = dynamic_cast<Packet *>(obj))
        return packet;
    auto signal = check_and_cast<cPacket *>(obj);
    return check_and_cast<Packet *>(signal->getEncapsulatedPacket());
}

// Interface signals (observePort). Only the four sources resolved at initialization
// count; any other emitter of the same signal (e.g. the PHY layer's own outbound
// emitter, which also emits packetSentToLower) is ignored.
void TtTimestampProcessor::receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details)
{
    Enter_Method("receiveSignal");
    simtime_t now = simTime();
    if (role == INGRESS) {
        if (source != receiverModule)
            return;
        const Packet *packet = encapsulatedPacket(obj);
        if (signalID == receptionStartedSignal) {
            numRxStartSeen++;
            rxStartTree = packet->getTreeId();
            rxStartTime = now;
        }
        else if (signalID == receptionEndedSignal) {
            if (rxEndTree != -1)
                throw cRuntimeError("observePort: receptionEnded of tree id %ld while the previous one (tree id %ld) never reached the slot",
                        packet->getTreeId(), rxEndTree);
            if (numRxStartSeen > 0 && rxStartTree != packet->getTreeId())
                throw cRuntimeError("observePort: receptionEnded of tree id %ld does not match receptionStarted of tree id %ld",
                        packet->getTreeId(), rxStartTree);
            if (packet->hasBitError())
                throw cRuntimeError("observePort: received frame with bit error (unsupported)");
            rxEndTree = packet->getTreeId();
            rxEndTime = now;
        }
        return;
    }
    TtEgressPairer::Event event;
    if (signalID == packetSentToLowerSignal && source == macEmitterModule)
        event = TtEgressPairer::DEQUEUE;
    else if (signalID == transmissionStartedSignal && source == transmitterModule)
        event = TtEgressPairer::TX_START;
    else if (signalID == transmissionEndedSignal && source == transmitterModule)
        event = TtEgressPairer::TX_END;
    else if (signalID == packetDroppedSignal && source == macQueueModule) {
        auto packet = check_and_cast<Packet *>(obj);
        for (const auto& r : pairer.fifo)
            if (r.treeId == packet->getTreeId())
                throw cRuntimeError("observePort: frame of tree id %ld dropped by the MAC queue", r.treeId);
        return;
    }
    else
        return;
    const Packet *packet = encapsulatedPacket(obj);
    if (packet->hasBitError())
        throw cRuntimeError("observePort: %s with bit error (aborted transmission, unsupported)", TtEgressPairer::eventName(event));
    size_t index = 0;
    std::string error = pairer.match(event, packet->getTreeId(), now, index);
    if (!error.empty())
        throw cRuntimeError("observePort pairing: %s", error.c_str());
    if (event != TtEgressPairer::TX_END)
        return;
    // end of transmission: the transmitted packet must be the recorded frame
    TtPortRecord& r = pairer.fifo.front();
    Layout layout = parse(packet, true);
    if (!layout.error.empty())
        throw cRuntimeError("observePort: unsupported structure of the transmitted frame: %s (%s)", layout.error.c_str(), layout.signature.c_str());
    r.txHash = payloadHash(packet, layout);
    if (r.txHash != r.hash)
        throw cRuntimeError("observePort pairing: payload hash of the transmitted frame (tree id %ld) differs from the enqueued one", r.treeId);
    auto found = collectLeafTags(layout);
    bool txTagged = !found.empty();
    if (txTagged != r.tagOnWire || (txTagged && r.tagged && found[0].tag->getFrameId() != r.frameId))
        throw cRuntimeError("observePort pairing: tag of the transmitted frame differs from the enqueued one (tree id %ld)", r.treeId);
    numPortTx++;
    if (pairingRotate)
        rotateRows.push_back(r);
    else
        writePortTx(r, r, "tx");
    pairer.fifo.pop_front();
}

void TtTimestampProcessor::writePortTx(const TtPortRecord& r, const TtPortRecord& id, const char *event)
{
    if (!portLog.is_open())
        return;
    simtime_t egress = egressEvent == EG_TX_END ? r.tTxEnd : egressEvent == EG_TX_START ? r.tTxStart : r.tSlot;
    portLog << event << ',' << ts(r.tTxEnd) << ',' << ttId << ",egress," << r.treeId << ',' << (id.tagged ? 1 : 0) << ',';
    if (id.tagged)
        portLog << id.frameId << ',' << id.ingressTime.str() << ',' << id.ingressTtId;
    else
        portLog << ",,";
    portLog << ',' << id.etherType << ',' << id.pcp << ',' << id.vid << ',' << id.payloadLength << ',' << id.hash << ',' << r.txHash
            << ",,," << ts(r.tSlot) << ',' << ts(r.tDequeue) << ',' << ts(r.tTxStart) << ',' << ts(r.tTxEnd) << ',' << ts(egress) << ',';
    if (id.tagged && egress >= SIMTIME_ZERO)
        portLog << (egress - id.ingressTime).str();
    portLog << ',' << r.note << '\n';
}

// ingress role: the frame at the slot must be the one whose reception just ended
void TtTimestampProcessor::portRx(Packet *packet, const Layout& layout, const TtTimestampTag *tag)
{
    numPortRx++;
    if (portLog.is_open()) {
        portLog << "rx," << simTime().str() << ',' << ttId << ",ingress," << packet->getTreeId() << ',' << (tag ? 1 : 0) << ',';
        if (tag)
            portLog << tag->getFrameId() << ',' << tag->getIngressTime().str() << ',' << tag->getIngressTtId();
        else
            portLog << ",,";
        portLog << ',' << layout.etherType << ',' << layout.pcp << ',' << layout.vid << ',' << B(layout.payloadLength).get() << ','
                << payloadHash(packet, layout) << ",," << (numRxStartSeen > 0 ? ts(rxStartTime) : std::string()) << ','
                << ts(rxEndTime) << ',' << simTime().str() << ",,,,,,\n";
    }
    rxEndTree = -1;
}

// egress role: a frame enters the MAC FIFO
void TtTimestampProcessor::portEnqueue(Packet *packet, const Layout& layout, const TtTimestampTag *tag, const std::string& note)
{
    TtPortRecord r;
    r.tagOnWire = !collectLeafTags(layout).empty();
    r.treeId = packet->getTreeId();
    r.tSlot = simTime();
    r.tagged = tag != nullptr;
    if (tag) {
        r.frameId = tag->getFrameId();
        r.ingressTime = tag->getIngressTime();
        r.ingressTtId = tag->getIngressTtId();
    }
    r.hash = payloadHash(packet, layout);
    r.etherType = layout.etherType;
    r.pcp = layout.pcp;
    r.vid = layout.vid;
    r.payloadLength = B(layout.payloadLength).get();
    r.note = note;
    std::string error = pairer.push(r);
    if (!error.empty())
        throw cRuntimeError("observePort pairing: %s", error.c_str());
}

// mode "observer": record the frame's port events, change nothing
void TtTimestampProcessor::processObserver(Packet *packet, const Layout& layout)
{
    auto found = collectLeafTags(layout);
    const TtTimestampTag *tag = found.empty() ? nullptr : found[0].tag.get();
    if (role == INGRESS) {
        if (rxEndTree != packet->getTreeId() || rxEndTime != simTime())
            throw cRuntimeError("observePort: frame at the RX slot (tree id %ld) is not the one whose reception just ended (tree id %ld)",
                    packet->getTreeId(), rxEndTree);
        portRx(packet, layout, tag);
    }
    else
        portEnqueue(packet, layout, tag, "");
}

cGate *TtTimestampProcessor::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

// Packet streaming would hand over partial frames; the structure check needs the whole
// frame, so streaming through this slot is unsupported and fails explicitly.
void TtTimestampProcessor::pushPacketStart(Packet *packet, const cGate *gate, bps datarate)
{
    throw cRuntimeError("Packet streaming through the measurement-layer slot is not supported (packet %s)", packet->getName());
}

void TtTimestampProcessor::pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength)
{
    throw cRuntimeError("Packet streaming through the measurement-layer slot is not supported (packet %s)", packet->getName());
}

void TtTimestampProcessor::pushPacketEnd(Packet *packet, const cGate *gate)
{
    throw cRuntimeError("Packet streaming through the measurement-layer slot is not supported (packet %s)", packet->getName());
}

void TtTimestampProcessor::collectLeaves(const Ptr<const Chunk>& chunk, b offset, std::vector<Leaf>& leaves)
{
    if (chunk->getChunkType() == Chunk::CT_SEQUENCE) {
        for (const auto& element : staticPtrCast<const SequenceChunk>(chunk)->getChunks()) {
            collectLeaves(element, offset, leaves);
            offset += element->getChunkLength();
        }
    }
    else
        leaves.push_back({offset, chunk});
}

TtTimestampProcessor::Layout TtTimestampProcessor::parse(const Packet *packet, bool allowPhyHeader) const
{
    Layout layout;
    const auto& data = packet->peekData();
    collectLeaves(data, b(0), layout.leaves);
    auto& leaves = layout.leaves;
    std::ostringstream sig;
    sig << "front=" << B(packet->getFrontOffset()).get() << "B back=" << B(packet->getBackOffset()).get()
        << "B data=" << B(packet->getDataLength()).get() << "B:";
    for (const auto& leaf : leaves) {
        sig << " " << shortTypeName(leaf.chunk.get()) << "(" << B(leaf.chunk->getChunkLength()).get() << "B";
        if (auto mac = dynamicPtrCast<const EthernetMacHeader>(leaf.chunk)) {
            char buf[16];
            snprintf(buf, sizeof(buf), " 0x%04x", mac->getTypeOrLength());
            sig << buf;
        }
        else if (auto q = dynamicPtrCast<const Ieee8021qTagEpdHeader>(leaf.chunk)) {
            char buf[48];
            snprintf(buf, sizeof(buf), " pcp=%d vid=%d 0x%04x", q->getPcp(), q->getVid(), q->getTypeOrLength());
            sig << buf;
        }
        sig << ")";
    }
    layout.signature = sig.str();

    auto isEthernetPart = [] (const Ptr<const Chunk>& c) {
        return dynamicPtrCast<const EthernetMacHeader>(c) || dynamicPtrCast<const Ieee8021qTagEpdHeader>(c)
               || dynamicPtrCast<const EthernetPadding>(c) || dynamicPtrCast<const EthernetFcs>(c)
               || dynamicPtrCast<const physicallayer::EthernetPhyHeaderBase>(c);
    };
    size_t n = leaves.size();
    // a transmitted/received PHY frame (observePort) starts with the PHY header
    size_t s = allowPhyHeader && n > 0 && dynamicPtrCast<const physicallayer::EthernetPhyHeaderBase>(leaves[0].chunk) ? 1 : 0;
    if (n == s) {
        layout.error = "empty data part";
        return layout;
    }
    auto mac = dynamicPtrCast<const EthernetMacHeader>(leaves[s].chunk);
    if (!mac) {
        layout.error = "first chunk of the data part is not an EthernetMacHeader";
        return layout;
    }
    int typeOrLength = mac->getTypeOrLength();
    size_t i = s + 1;
    if (typeOrLength == 0x8100) {
        auto q = n > s + 1 ? dynamicPtrCast<const Ieee8021qTagEpdHeader>(leaves[s + 1].chunk) : nullptr;
        if (!q) {
            layout.error = "MAC typeOrLength is 0x8100 but the next chunk is not an Ieee8021qTagEpdHeader";
            return layout;
        }
        layout.pcp = q->getPcp();
        layout.vid = q->getVid();
        typeOrLength = q->getTypeOrLength();
        i = s + 2;
    }
    if (typeOrLength < 0x600) {
        layout.error = "length interpretation of typeOrLength (802.3 length / LLC) is not supported";
        return layout;
    }
    if (typeOrLength == 0x8100 || typeOrLength == 0x88a8) {
        layout.error = "stacked VLAN tags are not supported";
        return layout;
    }
    layout.etherType = typeOrLength;
    size_t e = n;
    if (e > i && dynamicPtrCast<const EthernetFcs>(leaves[e - 1].chunk))
        e--;
    if (e > i && dynamicPtrCast<const EthernetPadding>(leaves[e - 1].chunk))
        e--;
    if (e <= i) {
        layout.error = "no payload chunk";
        return layout;
    }
    for (size_t k = i; k < e; k++) {
        if (isEthernetPart(leaves[k].chunk)) {
            layout.error = "Ethernet header/padding/FCS chunk at payload position " + std::to_string(k);
            return layout;
        }
    }
    layout.firstPayload = i;
    layout.endPayload = e;
    layout.payloadOffset = leaves[i].offset;
    layout.payloadLength = leaves[e - 1].offset + leaves[e - 1].chunk->getChunkLength() - leaves[i].offset;
    b total = leaves[n - 1].offset + leaves[n - 1].chunk->getChunkLength();
    if (total != packet->getDataLength())
        throw cRuntimeError("Internal error: leaves cover %" PRId64 " b of %" PRId64 " b", total.get(), packet->getDataLength().get());
    return layout;
}

std::vector<TtTimestampProcessor::FoundTag> TtTimestampProcessor::collectLeafTags(const Layout& layout) const
{
    std::vector<FoundTag> found;
    for (size_t k = 0; k < layout.leaves.size(); k++) {
        const auto& leaf = layout.leaves[k];
        bool inPayload = k >= layout.firstPayload && k < layout.endPayload;
        for (const auto& rt : leaf.chunk->getAllTags<TtTimestampTag>())
            found.push_back({leaf.offset + rt.getOffset(), rt.getLength(), rt.getTag(), inPayload});
    }
    std::sort(found.begin(), found.end(), [] (const FoundTag& a, const FoundTag& b) { return a.offset < b.offset; });
    return found;
}

// Counts TtTimestampTag regions at every level of a chunk tree (the chunk itself and,
// for a sequence, every element, recursively). INET copies tags to the enclosing
// sequence on insertion, so a tag usually appears at more than one level.
void TtTimestampProcessor::collectAllLevelTags(const Ptr<const Chunk>& chunk, int& count)
{
    count += chunk->getAllTags<TtTimestampTag>().size();
    if (chunk->getChunkType() == Chunk::CT_SEQUENCE)
        for (const auto& element : staticPtrCast<const SequenceChunk>(chunk)->getChunks())
            collectAllLevelTags(element, count);
}

std::string TtTimestampProcessor::payloadHash(const Packet *packet, const Layout& layout)
{
    // FNV-1a 64 over the serialized payload bytes; the checker computes the same from PCAP
    const auto bytesChunk = packet->peekDataAt<BytesChunk>(layout.payloadOffset, layout.payloadLength);
    const auto& bytes = bytesChunk->getBytes();
    uint64_t h = 1469598103934665603ULL;
    for (uint8_t c : bytes) {
        h ^= c;
        h *= 1099511628211ULL;
    }
    char buf[20];
    snprintf(buf, sizeof(buf), "%016" PRIx64, h);
    return buf;
}

// Replaces the whole payload region in one step with mutable copies of its leaf chunks,
// each tagged over its full length (addTag) or with every TtTimestampTag removed
// (removeTags). The chunks inside the packet are never mutated, so other packets that
// share them are unaffected. Replacing the whole region at once also drops the copies
// of the tags that INET keeps on the enclosing sequence chunk.
void TtTimestampProcessor::replacePayload(Packet *packet, const Layout& layout, const TtTimestampTag *addTag, bool removeTags) const
{
    std::vector<Ptr<Chunk>> parts;
    for (size_t k = layout.firstPayload; k < layout.endPayload; k++) {
        auto copy = layout.leaves[k].chunk->dupShared();
        b length = copy->getChunkLength();
        if (removeTags) {
            // NOTE: INET 4.7's Chunk::removeTagsWherePresent<T>() clears the tags of EVERY type in
            // the range (SharingRegionTagSet::clearTags), which would also delete e.g. the
            // application's CreationTimeTag. Remove exactly the TtTimestampTag regions instead.
            for (const auto& region : copy->getAllTags<TtTimestampTag>(b(0), length))
                copy->removeTag<TtTimestampTag>(region.getOffset(), region.getLength());
        }
        if (addTag) {
            const auto& tag = copy->addTag<TtTimestampTag>(b(0), length);
            tag->setIngressTime(addTag->getIngressTime());
            tag->setIngressTtId(addTag->getIngressTtId());
            tag->setFrameId(addTag->getFrameId());
        }
        copy->markImmutable();
        parts.push_back(copy);
    }
    Ptr<const Chunk> replacement;
    if (parts.size() == 1)
        replacement = parts[0];
    else {
        auto sequence = makeShared<SequenceChunk>();
        for (const auto& part : parts)
            sequence->insertAtBack(part);
        sequence->markImmutable();
        replacement = sequence;
    }
    packet->replaceDataAt(replacement, layout.payloadOffset, layout.payloadLength);
}

void TtTimestampProcessor::processPacket(Packet *packet)
{
    numFrames++;
    Layout layout = parse(packet);
    if (!layout.error.empty()) {
        if (failOnUnsupported)
            throw cRuntimeError("Unsupported packet structure at the measurement-layer slot: %s. Structure: %s. Packet: %s",
                    layout.error.c_str(), layout.signature.c_str(), packet->str().c_str());
        numUnsupported++;
        writeLog("unsupported", layout, "", nullptr, 0, layout.error);
        return;
    }
    switch (mode) {
        case PROBE: {
            int all = 0;
            collectAllLevelTags(packet->peekAll(), all);
            writeLog("probe", layout, payloadHash(packet, layout), nullptr, 0, "allLevelTags=" + std::to_string(all));
            break;
        }
        case AUDIT:
            processAudit(packet, layout);
            break;
        case OBSERVER:
            processObserver(packet, layout);
            break;
        case TRANSLATOR:
            if (role == INGRESS)
                processIngress(packet, layout);
            else
                processEgress(packet, layout);
            break;
    }
}

void TtTimestampProcessor::processIngress(Packet *packet, const Layout& layout)
{
    int already = 0;
    collectAllLevelTags(packet->peekAll(), already);
    if (already > 0)
        throw cRuntimeError("Frame already carries a TtTimestampTag at translator ingress (containment breach). Structure: %s", layout.signature.c_str());
    std::string hash = payloadHash(packet, layout);
    simtime_t ingressEventTime = simTime();
    if (observePort) {
        // the ingress event is the receiver's receptionEnded of this very frame, in this call
        if (rxEndTree != packet->getTreeId() || rxEndTime != simTime())
            throw cRuntimeError("observePort: frame at the RX slot (tree id %ld) is not the one whose reception just ended (tree id %ld)",
                    packet->getTreeId(), rxEndTree);
        if (ingressEvent == RX_START) {     // TEST ONLY (negative control)
            if (numRxStartSeen == 0 || rxStartTree != packet->getTreeId())
                throw cRuntimeError("ingressEvent = receptionStarted needs a streaming receiver");
            ingressEventTime = rxStartTime;
        }
    }
    if (!tagAtIngress) {
        numNotTagged++;
        writeLog("pass", layout, hash, nullptr, 0, "");
        if (observePort)
            portRx(packet, layout, nullptr);
        return;
    }
    frameCounter += frameIdStride;
    TtTimestampTag tag;
    tag.setIngressTime(ingressEventTime + timestampOffset);
    tag.setIngressTtId(ttId);
    tag.setFrameId(frameCounter);
    replacePayload(packet, layout, &tag, false);
    // self-check: the tag now covers exactly the payload, with one value
    Layout after = parse(packet);
    auto found = collectLeafTags(after);
    b covered = b(0);
    for (const auto& f : found) {
        if (!f.inPayload || f.tag->getFrameId() != frameCounter || f.offset != after.payloadOffset + covered)
            throw cRuntimeError("Internal error: tag placement check failed. Structure: %s", after.signature.c_str());
        covered += f.length;
    }
    if (covered != after.payloadLength || after.signature != layout.signature || payloadHash(packet, after) != hash)
        throw cRuntimeError("Internal error: tagging changed the frame or does not cover the payload. Before: %s After: %s",
                layout.signature.c_str(), after.signature.c_str());
    numTagged++;
    writeLog("tag", layout, hash, &tag, (int)found.size(), "");
    if (observePort)
        portRx(packet, layout, &tag);
}

void TtTimestampProcessor::processEgress(Packet *packet, const Layout& layout)
{
    std::string hash = payloadHash(packet, layout);
    auto found = collectLeafTags(layout);
    if (found.empty()) {
        numUntagged++;
        writeLog("untagged", layout, hash, nullptr, 0, "");
        if (observePort)
            portEnqueue(packet, layout, nullptr, "untagged");
        return;
    }
    std::string reason;
    const auto& first = found[0].tag;
    b expected = layout.payloadOffset;
    for (const auto& f : found) {
        if (!f.inPayload) {
            reason = "tag outside the payload";
            break;
        }
        if (f.tag->getIngressTime() != first->getIngressTime() || f.tag->getIngressTtId() != first->getIngressTtId()
            || f.tag->getFrameId() != first->getFrameId()) {
            reason = "regions with different values";
            break;
        }
        if (f.offset != expected) {
            reason = f.offset > expected ? "gap in coverage" : "overlapping regions";
            break;
        }
        expected += f.length;
    }
    if (reason.empty() && expected != layout.payloadOffset + layout.payloadLength)
        reason = "payload tail not covered";
    if (reason.empty()) {
        numRecovered++;
        writeLog("recover", layout, hash, first.get(), (int)found.size(), "");
    }
    else {
        numInvalid++;
        writeLog("invalid", layout, hash, first.get(), (int)found.size(), reason);
    }
    if (stripAtEgress) {
        replacePayload(packet, layout, nullptr, true);
        int remaining = 0;
        collectAllLevelTags(packet->peekAll(), remaining);
        if (remaining > 0 && reason.empty())
            throw cRuntimeError("Internal error: %d TtTimestampTag regions remain after stripping. Structure: %s", remaining, layout.signature.c_str());
        Layout after = parse(packet);
        if (after.signature != layout.signature || payloadHash(packet, after) != hash)
            throw cRuntimeError("Internal error: stripping changed the frame");
        numStripped++;
    }
    if (observePort) {
        TtTimestampTag recovered = *first;
        Layout after = parse(packet);
        portEnqueue(packet, after, reason.empty() ? &recovered : nullptr, reason);
    }
}

void TtTimestampProcessor::processAudit(Packet *packet, const Layout& layout)
{
    int count = 0;
    collectAllLevelTags(packet->peekAll(), count);
    auto found = collectLeafTags(layout);
    if (count > 0)
        numAuditTagged++;
    writeLog("audit", layout, payloadHash(packet, layout), found.empty() ? nullptr : found[0].tag.get(), (int)found.size(),
            "allLevelTags=" + std::to_string(count));
}

// Structure check and tag round trip on synthetic frames (parameter selfTest). Each case
// states the expected outcome; any deviation is an error. Results go to the log
// ("selftest" rows) and to scalars.
void TtTimestampProcessor::selfTest()
{
    auto mac = [] (int typeOrLength) {
        auto h = makeShared<EthernetMacHeader>();
        h->setTypeOrLength(typeOrLength);
        h->markImmutable();
        return h;
    };
    auto qtag = [] (int typeOrLength) {
        auto h = makeShared<Ieee8021qTagEpdHeader>();
        h->setPcp(5);
        h->setVid(42);
        h->setTypeOrLength(typeOrLength);
        h->markImmutable();
        return h;
    };
    auto bytes = [] (int n) {
        auto c = makeShared<ByteCountChunk>(B(n), 0x5a);
        // a foreign tag that tagging and stripping must leave untouched
        c->addTag<CreationTimeTag>()->setCreationTime(SimTime(1000 + n, SIMTIME_NS));
        c->markImmutable();
        return c;
    };
    auto foreignTags = [this] (const Packet& p) {
        std::string s;
        Layout l = parse(&p);
        for (size_t k = l.firstPayload; k < l.endPayload; k++)
            for (const auto& rt : l.leaves[k].chunk->getAllTags<CreationTimeTag>())
                s += std::to_string((l.leaves[k].offset + rt.getOffset()).get()) + "+" + std::to_string(rt.getLength().get())
                     + "=" + rt.getTag()->getCreationTime().str() + " ";
        auto top = p.peekDataAt(l.payloadOffset, l.payloadLength)->getAllTags<CreationTimeTag>();
        return s + "| top-level regions " + std::to_string(top.size());
    };
    auto padding = [] (int n) {
        auto c = makeShared<EthernetPadding>();
        c->setChunkLength(B(n));
        c->markImmutable();
        return c;
    };
    auto fcs = [] () {
        auto c = makeShared<EthernetFcs>();
        c->setFcsMode(FCS_DECLARED_CORRECT);
        c->markImmutable();
        return c;
    };
    struct Case {
        const char *name;
        std::vector<Ptr<const Chunk>> chunks;
        const char *expectedError;  // nullptr: supported
        int payloadOffset, payloadLength;
    };
    std::vector<Case> cases = {
        {"Q-tagged, 2-chunk payload, padding, FCS", {mac(0x8100), qtag(0x88f7), bytes(10), bytes(20), padding(12), fcs()}, nullptr, 18, 30},
        {"untagged, payload, FCS", {mac(0x0800), bytes(46), fcs()}, nullptr, 14, 46},
        {"Q-tagged, payload, no FCS", {mac(0x8100), qtag(0x0800), bytes(46)}, nullptr, 18, 46},
        {"802.3 length field", {mac(46), bytes(46), fcs()}, "length interpretation", 0, 0},
        {"0x8100 without Q-tag chunk", {mac(0x8100), bytes(46), fcs()}, "next chunk is not an Ieee8021qTagEpdHeader", 0, 0},
        {"stacked C-tags", {mac(0x8100), qtag(0x8100), qtag(0x0800), bytes(46), fcs()}, "stacked VLAN tags", 0, 0},
        {"S-tag", {mac(0x88a8), bytes(4), bytes(46), fcs()}, "stacked VLAN tags", 0, 0},
        {"no MAC header", {bytes(60), fcs()}, "not an EthernetMacHeader", 0, 0},
        {"headers only", {mac(0x8100), qtag(0x88f7), padding(46), fcs()}, "no payload chunk", 0, 0},
        {"MAC header inside the payload", {mac(0x0800), bytes(10), mac(0x0800), bytes(30), fcs()}, "at payload position", 0, 0},
    };
    int passed = 0;
    for (const auto& c : cases) {
        Packet packet("selftest");
        for (const auto& chunk : c.chunks)
            packet.insertAtBack(chunk);
        Layout layout = parse(&packet);
        std::string detail;
        bool ok;
        if (c.expectedError == nullptr)
            ok = layout.error.empty() && layout.payloadOffset == B(c.payloadOffset) && layout.payloadLength == B(c.payloadLength);
        else {
            // the structure check must name the problem, and processing must stop with an error
            ok = layout.error.find(c.expectedError) != std::string::npos;
            bool threw = false;
            bool savedFail = failOnUnsupported;
            failOnUnsupported = true;
            try {
                processPacket(&packet);
            }
            catch (cRuntimeError& e) {
                threw = std::string(e.what()).find("Unsupported packet structure") != std::string::npos;
            }
            failOnUnsupported = savedFail;
            numFrames = 0;
            ok = ok && threw;
            detail = threw ? " / processing stops with an error" : " / processing did NOT stop";
        }
        if (ok && c.expectedError == nullptr) {
            // round trip: tag, recover (full coverage, one value), strip (no tag at any level), bytes unchanged
            std::string hash = payloadHash(&packet, layout);
            std::string foreign = foreignTags(packet);
            TtTimestampTag tag;
            tag.setIngressTime(SimTime(123456789, SIMTIME_PS));
            tag.setIngressTtId(7);
            tag.setFrameId(99);
            replacePayload(&packet, layout, &tag, false);
            Layout tagged = parse(&packet);
            auto found = collectLeafTags(tagged);
            b covered = b(0);
            for (const auto& f : found)
                if (f.inPayload && f.offset == tagged.payloadOffset + covered && f.tag->getFrameId() == 99
                    && f.tag->getIngressTime() == tag.getIngressTime() && f.tag->getIngressTtId() == 7)
                    covered += f.length;
            int taggedLevels = 0;
            collectAllLevelTags(packet.peekAll(), taggedLevels);
            bool tagOk = covered == tagged.payloadLength && taggedLevels > 0;
            bool tagSame = payloadHash(&packet, tagged) == hash && tagged.signature == layout.signature && foreignTags(packet) == foreign;
            replacePayload(&packet, tagged, nullptr, true);
            int remaining = 0;
            collectAllLevelTags(packet.peekAll(), remaining);
            Layout stripped = parse(&packet);
            bool stripOk = remaining == 0 && collectLeafTags(stripped).empty();
            bool stripSame = payloadHash(&packet, stripped) == hash && stripped.signature == layout.signature && foreignTags(packet) == foreign;
            ok = tagOk && tagSame && stripOk && stripSame;
            detail = " / round trip: tag covers payload " + std::string(tagOk ? "yes" : "NO") + " (" + std::to_string(found.size())
                     + " leaf regions, " + std::to_string(taggedLevels) + " at all levels), frame unchanged " + (tagSame ? "yes" : "NO: " + tagged.signature + " hash " + hash + " -> " + payloadHash(&packet, tagged))
                     + "; strip leaves no tag " + (stripOk ? "yes" : "NO (" + std::to_string(remaining) + ")") + ", frame unchanged " + (stripSame ? "yes" : "NO: " + stripped.signature + " hash " + hash + " -> " + payloadHash(&packet, stripped))
                     + "; CreationTimeTags kept: " + (foreignTags(packet) == foreign ? "yes (" + foreign + ")" : "NO: " + foreign + " -> " + foreignTags(packet));
        }
        if (ok)
            passed++;
        if (log.is_open())
            log << "selftest,0," << ttId << ',' << (role == INGRESS ? "ingress" : "egress") << ",,,,0,,,,,," << layout.signature
                << ',' << (ok ? "PASS " : "FAIL ") << c.name << " / " << (layout.error.empty() ? "supported" : layout.error) << detail << '\n';
        EV_INFO << "self-test " << (ok ? "PASS" : "FAIL") << ": " << c.name << " -> " << (layout.error.empty() ? "supported" : layout.error) << EV_ENDL;
    }
    recordScalar("selfTestCases", cases.size());
    recordScalar("selfTestPassed", passed);
    if (passed != (int)cases.size())
        throw cRuntimeError("Self-test failed: %d of %d cases passed (see log)", passed, (int)cases.size());
    if (observePort)
        selfTestPairer();
}

// M2-S1: the egress pairing rules on synthetic event sequences (observePort only, so that
// M2-S0 logs are unchanged). Each case states the expected outcome.
int TtTimestampProcessor::selfTestPairer()
{
    using E = TtEgressPairer;
    struct Step { char op; long tree; double t; };   // op: 'P' push, 'D' dequeue, 'S' start, 'E' end
    struct Case { const char *name; std::vector<Step> steps; const char *expectedError; };
    std::vector<Case> cases = {
        {"idle port: one frame", {{'P', 1, 1}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}}, nullptr},
        {"two frames queued in FIFO order", {{'P', 1, 1}, {'P', 2, 1}, {'D', 1, 1}, {'S', 1, 1}, {'E', 1, 2}, {'D', 2, 2}, {'S', 2, 3}, {'E', 2, 4}}, nullptr},
        {"event for an unknown frame", {{'P', 1, 1}, {'D', 9, 1}}, "orphan"},
        {"a second frame with a pending tree id enters the queue", {{'P', 5, 1}, {'P', 5, 1}}, "ambiguous enqueue"},
        {"two pending records share a tree id (bypassing the enqueue check)", {{'P', 5, 1}, {'p', 5, 1}, {'D', 5, 1}}, "ambiguous MAC dequeue"},
        {"second frame dequeued first", {{'P', 1, 1}, {'P', 2, 1}, {'D', 2, 1}}, "out-of-order"},
        {"same event twice", {{'P', 1, 1}, {'D', 1, 1}, {'D', 1, 1}}, "duplicate"},
        {"start before dequeue", {{'P', 1, 1}, {'S', 1, 1}}, "no MAC dequeue"},
        {"end of the second frame before the first", {{'P', 1, 1}, {'P', 2, 1}, {'D', 1, 1}, {'S', 1, 1}, {'D', 2, 1}, {'S', 2, 1}, {'E', 2, 2}}, "out-of-order"},
        {"event before the frame entered the queue", {{'P', 1, 2}, {'D', 1, 1}}, "time order"},
    };
    int passed = 0;
    for (const auto& c : cases) {
        TtEgressPairer p;
        std::string error;
        for (const auto& s : c.steps) {
            if (s.op == 'P' || s.op == 'p') {   // 'p': raw insertion, bypassing the enqueue check
                TtPortRecord r;
                r.treeId = s.tree;
                r.tSlot = s.t;
                if (s.op == 'p')
                    p.fifo.push_back(r);
                else
                    error = p.push(r);
                if (!error.empty())
                    break;
                continue;
            }
            size_t index;
            E::Event e = s.op == 'D' ? E::DEQUEUE : s.op == 'S' ? E::TX_START : E::TX_END;
            error = p.match(e, s.tree, s.t, index);
            if (!error.empty())
                break;
            if (e == E::TX_END)
                p.fifo.pop_front();
        }
        bool ok = c.expectedError == nullptr ? error.empty() && p.fifo.empty() : error.find(c.expectedError) != std::string::npos;
        if (ok)
            passed++;
        if (portLog.is_open())
            portLog << "selftest,0," << ttId << ',' << (role == INGRESS ? "ingress" : "egress") << ",,,,,,,,,,,,,,,,,,,,"
                    << (ok ? "PASS " : "FAIL ") << c.name << " / " << (error.empty() ? "accepted" : error) << '\n';
    }
    recordScalar("selfTestPairerCases", cases.size());
    recordScalar("selfTestPairerPassed", passed);
    if (passed != (int)cases.size())
        throw cRuntimeError("Pairer self-test failed: %d of %d cases passed (see log)", passed, (int)cases.size());
    return passed;
}

void TtTimestampProcessor::writeLog(const char *event, const Layout& layout, const std::string& hash, const TtTimestampTag *tag, int regions, const std::string& note)
{
    if (!log.is_open())
        return;
    log << event << ',' << simTime().str() << ',' << ttId << ',' << (role == INGRESS ? "ingress" : "egress") << ',';
    if (tag)
        log << tag->getFrameId() << ',' << tag->getIngressTime().str() << ',' << tag->getIngressTtId();
    else
        log << ",,";
    log << ',' << regions << ',' << layout.etherType << ',' << layout.pcp << ',' << layout.vid << ','
        << B(layout.payloadLength).get() << ',' << hash << ',' << layout.signature << ',' << note << '\n';
}

void TtTimestampProcessor::finish()
{
    recordScalar("frames", numFrames);
    recordScalar("framesTagged", numTagged);
    recordScalar("framesNotTagged", numNotTagged);
    recordScalar("framesRecovered", numRecovered);
    recordScalar("framesUntaggedAtEgress", numUntagged);
    recordScalar("framesInvalidTag", numInvalid);
    recordScalar("framesStripped", numStripped);
    recordScalar("framesAuditTagged", numAuditTagged);
    recordScalar("framesUnsupported", numUnsupported);
    recordScalar("lastFrameId", (double)frameCounter);
    if (log.is_open())
        log.close();
    if (observePort) {
        // TEST ONLY: identities rotated by one row (each record still written once)
        for (size_t i = 0; i < rotateRows.size(); i++)
            writePortTx(rotateRows[i], rotateRows[(i + rotateRows.size() - 1) % rotateRows.size()], "tx");
        // frames that entered the MAC FIFO but were not completely transmitted by the end
        for (const auto& r : pairer.fifo)
            writePortTx(r, r, "pending");
        recordScalar("portRx", numPortRx);
        recordScalar("portTx", numPortTx);
        recordScalar("portPending", (double)pairer.fifo.size());
        if (portLog.is_open())
            portLog.close();
    }
}

} // namespace nasctime
