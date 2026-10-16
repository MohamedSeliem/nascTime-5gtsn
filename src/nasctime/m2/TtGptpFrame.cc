//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtGptpFrame.h"

#include <cinttypes>

#include "inet/common/checksum/ChecksumType_m.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/common/packet/chunk/SequenceChunk.h"

#include "TtPdelayEngine.h"

namespace nasctime {

namespace gptpframe {

static const MacAddress GPTP_ADDRESS("01:80:C2:00:00:0E");

std::string Key::str() const
{
    char buf[96];
    snprintf(buf, sizeof(buf), "%d/%d/0x%016" PRIx64 ":%d", domain, seq, clock, port);
    return buf;
}

void collectLeaves(const Ptr<const Chunk>& chunk, b offset, std::vector<Leaf>& leaves)
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

int messageType(const Packet *packet, b& gptpOffset)
{
    int t = TtPdelayEngine::classify(packet, gptpOffset);
    return t < 0 ? -1 : t;
}

static Ptr<const Chunk> leafAt(const Packet *packet, b offset)
{
    std::vector<Leaf> leaves;
    collectLeaves(packet->peekData(), b(0), leaves);
    for (const auto& l : leaves)
        if (l.offset == offset)
            return l.chunk;
    return nullptr;
}

uint64_t m2s0FrameId(const Packet *packet, b gptpOffset)
{
    auto leaf = leafAt(packet, gptpOffset);
    if (!leaf)
        return 0;
    for (const auto& rt : leaf->getAllTags<TtTimestampTag>())
        return rt.getTag()->getFrameId();
    return 0;
}

SyncFrame parseSync(const Packet *packet, b gptpOffset)
{
    SyncFrame s;
    if (packet->getDataLength() < gptpOffset + B(44)) {
        s.error = "shorter than a two-step Sync";
        return s;
    }
    auto sync = packet->peekDataAt<GptpBase>(gptpOffset, B(34), Chunk::PF_ALLOW_ALL);
    auto leaf = leafAt(packet, gptpOffset);
    if (leaf && dynamicPtrCast<const GptpSync>(leaf))
        sync = staticPtrCast<const GptpBase>(leaf);
    if (sync->isIncomplete() || sync->isIncorrect() || sync->isImproperlyRepresented())
        s.error = "Sync not properly represented";
    else if (sync->getVersionPTP() != 2 || sync->getMessageLengthField() != 44)
        s.error = "Sync versionPTP/messageLength";
    s.key.domain = sync->getDomainNumber();
    s.key.seq = sync->getSequenceId();
    s.key.clock = sync->getSourcePortIdentity().clockIdentity;
    s.key.port = sync->getSourcePortIdentity().portNumber;
    s.frameId = m2s0FrameId(packet, gptpOffset);
    return s;
}

FollowUpFrame parseFollowUp(const Packet *packet, int expectedDomain)
{
    FollowUpFrame f;
    std::vector<Leaf> leaves;
    collectLeaves(packet->peekData(), b(0), leaves);
    if (leaves.size() != 3) {
        f.unsupported = "not exactly [MAC header][Follow_Up][FCS] (" + std::to_string(leaves.size()) + " leaf chunks)";
        return f;
    }
    f.mac = dynamicPtrCast<const EthernetMacHeader>(leaves[0].chunk);
    f.fu = dynamicPtrCast<const GptpFollowUp>(leaves[1].chunk);
    f.fcs = dynamicPtrCast<const EthernetFcs>(leaves[2].chunk);
    if (!f.mac || f.mac->getDest() != GPTP_ADDRESS) {
        f.unsupported = "first chunk is not an EthernetMacHeader to 01-80-C2-00-00-0E";
        return f;
    }
    if (f.mac->getTypeOrLength() == 0x8100) {
        f.malformed = "VLAN-tagged gPTP";
        return f;
    }
    if (f.mac->getTypeOrLength() != 0x88F7) {
        f.unsupported = "EtherType";
        return f;
    }
    if (!f.fu) {
        f.unsupported = std::string("Follow_Up payload is a ") + leaves[1].chunk->getClassName() + ", not a GptpFollowUp";
        return f;
    }
    if (!f.fcs) {
        f.unsupported = "no EthernetFcs chunk";
        return f;
    }
    if (f.fu->getChunkLength() != B(76) || f.fu->isIncomplete() || f.fu->isIncorrect() || f.fu->isImproperlyRepresented()) {
        f.unsupported = "GptpFollowUp chunk not complete/correct/properly represented or not 76 B";
        return f;
    }
    f.fuOffset = leaves[1].offset;
    f.fuLength = f.fu->getChunkLength();
    f.key.domain = f.fu->getDomainNumber();
    f.key.seq = f.fu->getSequenceId();
    f.key.clock = f.fu->getSourcePortIdentity().clockIdentity;
    f.key.port = f.fu->getSourcePortIdentity().portNumber;
    for (const auto& rt : f.fu->getAllTags<TtTimestampTag>()) {
        f.frameId = rt.getTag()->getFrameId();
        break;
    }
    if (f.key.domain != expectedDomain)
        return f;   // other domain: the caller passes it unchanged
    const auto& tlv = f.fu->getFollowUpInformationTLV();
    if (f.fu->getVersionPTP() != 2)
        f.malformed = "versionPTP " + std::to_string(f.fu->getVersionPTP());
    else if (f.fu->getMessageLengthField() != 76)
        f.malformed = "messageLength " + std::to_string(f.fu->getMessageLengthField());
    else if (tlv.getTlvType() != GPTP_FOLLOW_UP_INFORMATION_TLV || tlv.getLengthField() != 28 || tlv.getOrganizationId() != 0x0080C2
             || tlv.getOrganizationSubType() != 1)
        f.malformed = "Follow_Up information TLV";
    return f;
}

std::vector<SyncTagRegion> syncTags(const Ptr<const GptpFollowUp>& fu)
{
    std::vector<SyncTagRegion> out;
    for (const auto& rt : fu->getAllTags<TtSyncIngressTag>())
        out.push_back({rt.getOffset(), rt.getLength(), rt.getTag()});
    return out;
}

int countSyncTagsAllLevels(const Ptr<const Chunk>& chunk)
{
    int n = chunk->getAllTags<TtSyncIngressTag>().size();
    if (chunk->getChunkType() == Chunk::CT_SEQUENCE)
        for (const auto& element : staticPtrCast<const SequenceChunk>(chunk)->getChunks())
            n += countSyncTagsAllLevels(element);
    return n;
}

uint32_t crc32Independent(const std::vector<uint8_t>& bytes)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (uint8_t byte : bytes) {
        crc ^= byte;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

double multiplyRateRatio(double rateRatio, const ClockTimeScale& nrr)
{
    ClockTimeScale a = ClockTimeScale::fromDouble(rateRatio);
    return (a * nrr).toDouble();
}

clocktime_t scale(double rateRatio, clocktime_t t)
{
    return ClockTimeScale::fromDouble(rateRatio).mul(t);
}

static std::vector<uint8_t> frameBytes(const Packet *packet)
{
    auto chunk = packet->peekDataAsBytes();
    return chunk->getBytes();
}

std::string rewriteFollowUp(Packet *packet, const FollowUpFrame& f, const Rewrite& r)
{
    std::vector<uint8_t> before = r.selfCheck ? frameBytes(packet) : std::vector<uint8_t>();
    long treeId = packet->getTreeId();
    b length = packet->getDataLength();
    auto m2s0Before = f.fu->getAllTags<TtTimestampTag>();
    auto copy = staticPtrCast<GptpFollowUp>(f.fu->dupShared());
    copy->setCorrectionField(r.correctionField);
    if (r.setRateRatio) {
        GptpFollowUpInformationTlv tlv = copy->getFollowUpInformationTLV();
        tlv.setRateRatio(r.rateRatio);
        copy->setFollowUpInformationTLV(tlv);
    }
    if (r.removeSyncTag) {
        // exactly the TtSyncIngressTag regions (removeTagsWherePresent would clear every tag type)
        for (const auto& region : copy->getAllTags<TtSyncIngressTag>(b(0), copy->getChunkLength()))
            copy->removeTag<TtSyncIngressTag>(region.getOffset(), region.getLength());
    }
    if (r.addTag) {
        const auto& tag = copy->addTag<TtSyncIngressTag>(b(0), copy->getChunkLength());
        *tag = *r.addTag;
    }
    copy->markImmutable();
    packet->replaceDataAt(copy, f.fuOffset, f.fuLength);
    uint32_t fcsValue = 0;
    if (r.recomputeFcs) {
        b fcsOffset = packet->getDataLength() - B(4);
        auto bytesChunk = packet->peekDataAt<BytesChunk>(b(0), fcsOffset);
        fcsValue = (uint32_t)inet::computeChecksum(bytesChunk->getBytes(), CHECKSUM_ETHERNET_FCS);
        auto fcs = makeShared<EthernetFcs>();
        fcs->setFcsMode(f.fcs->getFcsMode());
        fcs->setFcs(fcsValue);
        fcs->markImmutable();
        packet->replaceDataAt(fcs, fcsOffset, B(4));
    }
    if (!r.selfCheck)
        return "";
    // ---- self-check (design 5.1 step 7)
    if (packet->getTreeId() != treeId || packet->getDataLength() != length)
        return "tree id or length changed";
    std::vector<Leaf> leaves;
    collectLeaves(packet->peekData(), b(0), leaves);
    if (leaves.size() != 3 || !dynamicPtrCast<const EthernetMacHeader>(leaves[0].chunk) || !dynamicPtrCast<const GptpFollowUp>(leaves[1].chunk)
        || !dynamicPtrCast<const EthernetFcs>(leaves[2].chunk))
        return "chunk structure changed";
    auto after = frameBytes(packet);
    if (after.size() != before.size())
        return "serialized length changed";
    for (size_t i = 0; i < after.size(); i++) {
        if (after[i] == before[i])
            continue;
        bool allowed = (i >= 22 && i < 30) || (r.setRateRatio && i >= 68 && i < 72) || (i >= 90 && i < 94);
        if (!allowed)
            return "serialized byte " + std::to_string(i) + " changed outside correctionField/csro/FCS";
    }
    auto fu2 = staticPtrCast<const GptpFollowUp>(leaves[1].chunk);
    if (fu2->getCorrectionField() != r.correctionField)
        return "correctionField not as written";
    auto m2s0After = fu2->getAllTags<TtTimestampTag>();
    if (m2s0After.size() != m2s0Before.size())
        return "M2-S0 tag regions changed";
    for (size_t i = 0; i < m2s0After.size(); i++)
        if (m2s0After[i].getOffset() != m2s0Before[i].getOffset() || m2s0After[i].getLength() != m2s0Before[i].getLength()
            || m2s0After[i].getTag()->getFrameId() != m2s0Before[i].getTag()->getFrameId())
            return "M2-S0 tag changed";
    auto tags = syncTags(fu2);
    if (r.addTag) {
        if (tags.size() != 1 || tags[0].offset != b(0) || tags[0].length != fu2->getChunkLength())
            return "TtSyncIngressTag not present exactly once over the whole Follow_Up";
    }
    else if (r.removeSyncTag) {
        if (!tags.empty() || countSyncTagsAllLevels(packet->peekAll()) != 0)
            return "TtSyncIngressTag left on the frame";
    }
    if (r.recomputeFcs) {
        std::vector<uint8_t> data(after.begin(), after.end() - 4);
        uint32_t wire = (uint32_t)after[after.size() - 1] << 24 | (uint32_t)after[after.size() - 2] << 16 |
                        (uint32_t)after[after.size() - 3] << 8 | after[after.size() - 4];
        if (crc32Independent(data) != wire)   // the FCS on the wire (LSB first) = CRC-32 of the frame
            return "FCS differs from the independent CRC-32";
    }
    return "";
}

// ---------------------------------------------------------------------------------------
// self-test (design 10, commit 3): synthetic frames as INET builds them at the TT slots

static Packet *syntheticFollowUp(int domain, int seq, clocktime_t cf, bool m2s0Tag)
{
    auto fu = makeShared<GptpFollowUp>();
    fu->setDomainNumber(domain);
    fu->setSequenceId(seq);
    fu->setCorrectionField(cf);
    fu->setPreciseOriginTimestamp(ClockTime::fromRaw(125000000000LL));
    GptpFollowUpInformationTlv tlv;
    tlv.setRateRatio(1.0);
    fu->setFollowUpInformationTLV(tlv);
    if (m2s0Tag) {
        const auto& t = fu->addTag<TtTimestampTag>(b(0), fu->getChunkLength());
        t->setFrameId(77);
        t->setIngressTtId(1);
        t->setIngressTime(SimTime::fromRaw(123));
    }
    fu->markImmutable();
    auto packet = new Packet("selfTestFollowUp");
    auto mac = makeShared<EthernetMacHeader>();
    mac->setDest(GPTP_ADDRESS);
    mac->setSrc(MacAddress("0A:AA:00:00:00:01"));
    mac->setTypeOrLength(0x88F7);
    packet->insertAtBack(mac);
    packet->insertAtBack(fu);
    auto fcs = makeShared<EthernetFcs>();
    fcs->setFcsMode(FCS_COMPUTED);
    fcs->setFcs((uint32_t)inet::computeChecksum(packet->peekDataAsBytes()->getBytes(), CHECKSUM_ETHERNET_FCS));
    packet->insertAtBack(fcs);
    return packet;
}

void selfTest(int domainNumber)
{
    // rate-ratio arithmetic: fromDouble(1.0) (x) t = t, including sub-ns values; 1 (x) nRR(1/1) = 1
    for (int64_t raw : {0LL, 1LL, 999LL, 50000LL, 73217LL, 5000576000LL, 1234567891234LL, -270000LL}) {
        clocktime_t t = ClockTime::fromRaw(raw);
        if (scale(1.0, t) != t)
            throw cRuntimeError("gptpframe self-test: 1.0 (x) %" PRId64 " ps != itself", raw);
    }
    if (multiplyRateRatio(1.0, ClockTimeScale::fromRatio(ClockTime::fromRaw(1000), ClockTime::fromRaw(1000))) != 1.0)
        throw cRuntimeError("gptpframe self-test: 1.0 (x) nRR 1/1 != 1.0");
    // NW-TT rewrite on an M2-S0-tagged Follow_Up, then DS-TT rewrite
    Packet *p = syntheticFollowUp(domainNumber, 4242, CLOCKTIME_ZERO, true);
    auto f = parseFollowUp(p, domainNumber);
    if (f.isClassM() || f.key.seq != 4242 || f.frameId != 77)
        throw cRuntimeError("gptpframe self-test: parse: %s%s", f.unsupported.c_str(), f.malformed.c_str());
    TtSyncIngressTag tag;
    tag.setValid(true);
    tag.setTtId(1);
    tag.setSyncIngressTime(SimTime::fromRaw(125000050123LL));
    tag.setSequenceId(4242);
    Rewrite r1;
    r1.correctionField = ClockTime::fromRaw(73217);   // sub-ns: wire carries 73 ns
    r1.setRateRatio = true;
    r1.rateRatio = 1.0;
    r1.addTag = &tag;
    std::string e = rewriteFollowUp(p, f, r1);
    if (!e.empty())
        throw cRuntimeError("gptpframe self-test: NW-TT rewrite: %s", e.c_str());
    auto f2 = parseFollowUp(p, domainNumber);
    auto tags = syncTags(f2.fu);
    if (tags.size() != 1 || tags[0].tag->getSyncIngressTime() != SimTime::fromRaw(125000050123LL) || f2.frameId != 77)
        throw cRuntimeError("gptpframe self-test: tag not carried");
    auto bytes = p->peekDataAsBytes()->getBytes();
    uint64_t wireCf = 0;
    for (int i = 22; i < 30; i++)
        wireCf = wireCf << 8 | bytes[i];
    if (wireCf != (uint64_t)73 << 16)
        throw cRuntimeError("gptpframe self-test: wire correctionField 0x%" PRIx64 ", expected 73 ns << 16", wireCf);
    Rewrite r2;
    r2.correctionField = ClockTime::fromRaw(73217 + 5000576123LL);
    r2.removeSyncTag = true;
    e = rewriteFollowUp(p, f2, r2);
    if (!e.empty())
        throw cRuntimeError("gptpframe self-test: DS-TT rewrite: %s", e.c_str());
    auto f3 = parseFollowUp(p, domainNumber);
    if (!syncTags(f3.fu).empty() || f3.frameId != 77 || f3.fu->getCorrectionField() != ClockTime::fromRaw(73217 + 5000576123LL))
        throw cRuntimeError("gptpframe self-test: DS-TT result");
    delete p;
    // class M detection
    Packet *q = syntheticFollowUp(domainNumber, 1, CLOCKTIME_ZERO, false);
    auto g = parseFollowUp(q, domainNumber);
    if (g.isClassM())
        throw cRuntimeError("gptpframe self-test: valid frame classified M");
    delete q;
    auto fu = makeShared<GptpFollowUp>();
    fu->setDomainNumber(domainNumber);
    fu->setVersionPTP(1);
    auto bad = new Packet("selfTestBad");
    auto mac = makeShared<EthernetMacHeader>();
    mac->setDest(GPTP_ADDRESS);
    mac->setTypeOrLength(0x88F7);
    bad->insertAtBack(mac);
    bad->insertAtBack(fu);
    bad->insertAtBack(makeShared<EthernetFcs>());
    if (parseFollowUp(bad, domainNumber).malformed.empty())
        throw cRuntimeError("gptpframe self-test: versionPTP 1 not malformed");
    delete bad;
    auto raw = new Packet("selfTestBytes");
    raw->insertAtBack(mac);
    raw->insertAtBack(makeShared<BytesChunk>(std::vector<uint8_t>(76, 0x08)));
    raw->insertAtBack(makeShared<EthernetFcs>());
    if (parseFollowUp(raw, domainNumber).unsupported.empty())
        throw cRuntimeError("gptpframe self-test: BytesChunk Follow_Up not unsupported");
    delete raw;
}

} // namespace gptpframe

} // namespace nasctime
