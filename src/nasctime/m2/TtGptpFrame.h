//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTGPTPFRAME_H
#define __NASCTIME_M2_TTGPTPFRAME_H

#include <string>
#include <vector>

#include "inet/clock/common/ClockTimeScale.h"
#include "inet/common/packet/Packet.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021as/GptpPacket_m.h"

#include "TtSyncIngressTag_m.h"
#include "TtTimestampTag_m.h"

namespace nasctime {

using namespace inet;

//
// M2-S5 Sync/Follow_Up frame handling shared by TtSyncIngress (NW-TT) and TtSyncEgress
// (DS-TT): parsing, validation (migration/m2-s5-design.md 5.1, classes of 6.0), the
// Follow_Up rewrite (correctionField, TLV rateRatio, TtSyncIngressTag, FCS) and its
// self-check. The packet's chunks are never mutated: the GptpFollowUp chunk is copied,
// edited and put back in place of the original (as M2-S0's replacePayload).
//
namespace gptpframe {

// association key of a Sync/Follow_Up pair (domainNumber, sequenceId, sourcePortIdentity)
struct Key {
    int domain = -1;
    int seq = -1;
    uint64_t clock = 0;
    int port = -1;
    bool operator==(const Key& o) const { return domain == o.domain && seq == o.seq && clock == o.clock && port == o.port; }
    bool operator!=(const Key& o) const { return !(*this == o); }
    bool isSet() const { return seq >= 0; }
    std::string str() const;
};

struct Leaf {
    b offset;
    Ptr<const Chunk> chunk;
};
void collectLeaves(const Ptr<const Chunk>& chunk, b offset, std::vector<Leaf>& leaves);

// gPTP messageType (0..15) of a frame to 01-80-C2-00-00-0E with EtherType 0x88F7, -1 if
// none (TtPdelayEngine::classify)
int messageType(const Packet *packet, b& gptpOffset);

// M2-S0 frame id of the TtTimestampTag covering the chunk at gptpOffset (0 if none)
uint64_t m2s0FrameId(const Packet *packet, b gptpOffset);

struct SyncFrame {
    std::string error;          // non-empty: not a valid two-step Sync of the expected form
    Key key;
    uint64_t frameId = 0;       // M2-S0 frame id
};
SyncFrame parseSync(const Packet *packet, b gptpOffset);

// Follow_Up classes (design 6.0): unsupported / malformed are class M
struct FollowUpFrame {
    std::string unsupported;    // representation is not [EthernetMacHeader][GptpFollowUp 76 B][EthernetFcs]
    std::string malformed;      // fields fail validation (5.1 step 2)
    Ptr<const EthernetMacHeader> mac;
    Ptr<const GptpFollowUp> fu;
    Ptr<const EthernetFcs> fcs;
    b fuOffset, fuLength;
    Key key;
    uint64_t frameId = 0;       // M2-S0 frame id of the Follow_Up
    bool isClassM() const { return !unsupported.empty() || !malformed.empty(); }
};
FollowUpFrame parseFollowUp(const Packet *packet, int expectedDomain);

// TtSyncIngressTag regions on the GptpFollowUp chunk (relative to the chunk)
struct SyncTagRegion {
    b offset, length;
    Ptr<const TtSyncIngressTag> tag;
};
std::vector<SyncTagRegion> syncTags(const Ptr<const GptpFollowUp>& fu);
// TtSyncIngressTag regions at every chunk level of the packet (containment audit)
int countSyncTagsAllLevels(const Ptr<const Chunk>& chunk);

struct Rewrite {
    clocktime_t correctionField;
    bool setRateRatio = false;
    double rateRatio = 1;
    const TtSyncIngressTag *addTag = nullptr;   // NW-TT: added over the whole Follow_Up chunk
    bool removeSyncTag = false;                  // DS-TT: exactly the TtSyncIngressTag regions
    bool recomputeFcs = true;                    // false: TEST ONLY (negative controls N7/N8)
    bool selfCheck = true;
};
// Applies the rewrite; returns "" or the self-check error (an internal error for the caller)
std::string rewriteFollowUp(Packet *packet, const FollowUpFrame& f, const Rewrite& r);

uint32_t crc32Independent(const std::vector<uint8_t>& bytes);

// rr_out = rr_in (x) nRR with INET's fixed-point arithmetic (ClockTimeScale), as a double
double multiplyRateRatio(double rateRatio, const ClockTimeScale& nrr);
// rr (x) t with INET's ClockTimeScale::mul (round half away from zero)
clocktime_t scale(double rateRatio, clocktime_t t);

// Self-test on synthetic frames (design 10, commit 3); throws on failure
void selfTest(int domainNumber);

} // namespace gptpframe

} // namespace nasctime

#endif
