//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTTIMESTAMPPROCESSOR_H
#define __NASCTIME_M2_TTTIMESTAMPPROCESSOR_H

#include <fstream>
#include <string>
#include <vector>

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

#include "TtEgressPairer.h"
#include "TtTimestampTag_m.h"

namespace nasctime {

using namespace inet;

//
// M2-S0 processor (see TtTimestampLayer.ned). One instance per direction of an
// Ethernet interface's measurement-layer slot. Stateless with respect to the frames,
// except for the per-translator frame counter (ingress) and the statistics.
// M2-S1 (observePort, or mode "observer"): also listens to its own interface's PHY/MAC
// signals and records, per frame, the reception events (ingress role) or the MAC
// dequeue / transmission start / transmission end events (egress role). Passive.
//
class TtTimestampProcessor : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener, public cListener
{
  public:
    // Data part of a frame at the measurement-layer slot, as checked by parse():
    //   [EthernetMacHeader][Ieee8021qTagEpdHeader iff MAC typeOrLength == 0x8100]
    //   [payload chunk]+ [EthernetPadding]? [EthernetFcs]?
    // Offsets are relative to the start of the packet's data part.
    struct Leaf {
        b offset;
        Ptr<const Chunk> chunk;
    };
    struct Layout {
        std::vector<Leaf> leaves;   // all leaf chunks of the data part, in order
        size_t firstPayload = 0;    // index of the first payload leaf
        size_t endPayload = 0;      // one past the last payload leaf
        b payloadOffset = b(0);
        b payloadLength = b(0);
        int etherType = -1;         // after the 802.1Q tag, if any
        int pcp = -1;
        int vid = -1;
        std::string signature;      // human-readable structure, for the probe and errors
        std::string error;          // non-empty: unsupported structure
    };
    struct FoundTag {
        b offset;                   // relative to the data part
        b length;
        Ptr<const TtTimestampTag> tag;
        bool inPayload;
    };

  protected:
    enum Role { INGRESS, EGRESS };
    enum Mode { TRANSLATOR, AUDIT, PROBE, OBSERVER };

    Role role = INGRESS;
    Mode mode = TRANSLATOR;
    int ttId = -1;
    bool tagAtIngress = true;
    bool stripAtEgress = true;
    simtime_t timestampOffset;
    int frameIdStride = 1;
    bool failOnUnsupported = true;
    std::ofstream log;

    uint64_t frameCounter = 0;      // last frame id assigned (ingress)

    // M2-S1 port observation
    bool observePort = false;
    enum IngressEvent { RX_END, RX_START } ingressEvent = RX_END;           // TEST ONLY: RX_START
    enum EgressEvent { EG_TX_END, EG_TX_START, EG_SLOT } egressEvent = EG_TX_END; // TEST ONLY: others
    bool pairingRotate = false;     // TEST ONLY: write each tx row with the previous row's identity
    cModule *interfaceModule = nullptr;
    cModule *transmitterModule = nullptr;
    cModule *receiverModule = nullptr;
    cModule *macEmitterModule = nullptr;
    cModule *macQueueModule = nullptr;
    std::ofstream portLog;
    TtEgressPairer pairer;          // egress role
    std::vector<TtPortRecord> rotateRows;
    long rxStartTree = -1, rxEndTree = -1;   // ingress role: last reception events
    simtime_t rxStartTime = -1, rxEndTime = -1;
    long numPortRx = 0, numPortTx = 0, numRxStartSeen = 0;

    // statistics (scalars)
    long numFrames = 0;             // frames processed
    long numTagged = 0;             // ingress: frames tagged
    long numNotTagged = 0;          // ingress: frames passed untagged (tagAtIngress = false)
    long numRecovered = 0;          // egress: exactly one valid tag over the whole payload
    long numUntagged = 0;           // egress: no tag at all
    long numInvalid = 0;            // egress: partial coverage, split values, or tag outside the payload
    long numStripped = 0;           // egress: tags removed
    long numAuditTagged = 0;        // audit: frames carrying any TtTimestampTag at any level
    long numUnsupported = 0;        // structure not as above (only with failOnUnsupported = false)

  protected:
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;

    virtual void pushPacketStart(Packet *packet, const cGate *gate, bps datarate) override;
    virtual void pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength) override;
    virtual void pushPacketEnd(Packet *packet, const cGate *gate) override;
    virtual void processPacket(Packet *packet) override;
    virtual void receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details) override;

    Layout parse(const Packet *packet, bool allowPhyHeader = false) const;
    static void collectLeaves(const Ptr<const Chunk>& chunk, b offset, std::vector<Leaf>& leaves);
    static void collectAllLevelTags(const Ptr<const Chunk>& chunk, int& count);
    std::vector<FoundTag> collectLeafTags(const Layout& layout) const;
    static std::string payloadHash(const Packet *packet, const Layout& layout);
    void replacePayload(Packet *packet, const Layout& layout, const TtTimestampTag *addTag, bool removeTags) const;

    void processIngress(Packet *packet, const Layout& layout);
    void processEgress(Packet *packet, const Layout& layout);
    void processAudit(Packet *packet, const Layout& layout);

    void processObserver(Packet *packet, const Layout& layout);
    void portRx(Packet *packet, const Layout& layout, const TtTimestampTag *tag);
    void portEnqueue(Packet *packet, const Layout& layout, const TtTimestampTag *tag, const std::string& note);
    void writePortTx(const TtPortRecord& r, const TtPortRecord& identity, const char *event);
    static const Packet *encapsulatedPacket(cObject *obj);

    void selfTest();
    int selfTestPairer();

    void writeLog(const char *event, const Layout& layout, const std::string& hash, const TtTimestampTag *tag, int regions, const std::string& note);
};

} // namespace nasctime

#endif
