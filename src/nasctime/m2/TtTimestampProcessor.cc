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

#include "inet/common/packet/chunk/ByteCountChunk.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/common/packet/chunk/SequenceChunk.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021q/Ieee8021qTagHeader_m.h"

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
        if (par("selfTest"))
            selfTest();
    }
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

TtTimestampProcessor::Layout TtTimestampProcessor::parse(const Packet *packet) const
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
               || dynamicPtrCast<const EthernetPadding>(c) || dynamicPtrCast<const EthernetFcs>(c);
    };
    size_t n = leaves.size();
    if (n == 0) {
        layout.error = "empty data part";
        return layout;
    }
    auto mac = dynamicPtrCast<const EthernetMacHeader>(leaves[0].chunk);
    if (!mac) {
        layout.error = "first chunk of the data part is not an EthernetMacHeader";
        return layout;
    }
    int typeOrLength = mac->getTypeOrLength();
    size_t i = 1;
    if (typeOrLength == 0x8100) {
        auto q = n > 1 ? dynamicPtrCast<const Ieee8021qTagEpdHeader>(leaves[1].chunk) : nullptr;
        if (!q) {
            layout.error = "MAC typeOrLength is 0x8100 but the next chunk is not an Ieee8021qTagEpdHeader";
            return layout;
        }
        layout.pcp = q->getPcp();
        layout.vid = q->getVid();
        typeOrLength = q->getTypeOrLength();
        i = 2;
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
        if (removeTags)
            copy->removeTagsWherePresent<TtTimestampTag>(b(0), length);
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
    if (!tagAtIngress) {
        numNotTagged++;
        writeLog("pass", layout, hash, nullptr, 0, "");
        return;
    }
    frameCounter += frameIdStride;
    TtTimestampTag tag;
    tag.setIngressTime(simTime() + timestampOffset);
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
}

void TtTimestampProcessor::processEgress(Packet *packet, const Layout& layout)
{
    std::string hash = payloadHash(packet, layout);
    auto found = collectLeafTags(layout);
    if (found.empty()) {
        numUntagged++;
        writeLog("untagged", layout, hash, nullptr, 0, "");
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
        c->markImmutable();
        return c;
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
        else
            ok = layout.error.find(c.expectedError) != std::string::npos;
        if (ok && c.expectedError == nullptr) {
            // round trip: tag, recover (full coverage, one value), strip (no tag at any level), bytes unchanged
            std::string hash = payloadHash(&packet, layout);
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
            bool tagSame = payloadHash(&packet, tagged) == hash && tagged.signature == layout.signature;
            replacePayload(&packet, tagged, nullptr, true);
            int remaining = 0;
            collectAllLevelTags(packet.peekAll(), remaining);
            Layout stripped = parse(&packet);
            bool stripOk = remaining == 0 && collectLeafTags(stripped).empty();
            bool stripSame = payloadHash(&packet, stripped) == hash && stripped.signature == layout.signature;
            ok = tagOk && tagSame && stripOk && stripSame;
            detail = " / round trip: tag covers payload " + std::string(tagOk ? "yes" : "NO") + " (" + std::to_string(found.size())
                     + " leaf regions, " + std::to_string(taggedLevels) + " at all levels), frame unchanged " + (tagSame ? "yes" : "NO: " + tagged.signature + " hash " + hash + " -> " + payloadHash(&packet, tagged))
                     + "; strip leaves no tag " + (stripOk ? "yes" : "NO (" + std::to_string(remaining) + ")") + ", frame unchanged " + (stripSame ? "yes" : "NO: " + stripped.signature + " hash " + hash + " -> " + payloadHash(&packet, stripped));
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
}

} // namespace nasctime
