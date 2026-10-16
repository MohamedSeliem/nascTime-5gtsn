//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTPDELAYENGINE_H
#define __NASCTIME_M2_TTPDELAYENGINE_H

#include <deque>
#include <fstream>
#include <map>

#include "inet/clock/common/ClockTimeScale.h"
#include "inet/common/packet/Packet.h"
#include "inet/linklayer/common/MacAddress.h"
#include "inet/linklayer/ieee8021as/GptpPacket_m.h"

namespace nasctime {

using namespace inet;

class TtPdelayFlow;

//
// M2-S4 per-port Pdelay engine (migration/m2-s4-design.md, revision 2), one per
// translator TSN port, inside TtPdelayPort. No gates: the rx flow offers every received
// frame (offerReceived); the engine's own frames enter the tx flow (TtPdelayFlow::inject).
//
//  - Classification: destination 01-80-C2-00-00-0E, EtherType 0x88F7 (untagged or behind
//    one 802.1Q tag), gPTP messageType 2/3/10. With terminate = false: counted, passed.
//    With terminate = true: taken (never forwarded), validated (design 4.8), then handled
//    by the responder (Pdelay_Req) or the requester (Pdelay_Resp / Pdelay_Resp_Follow_Up).
//  - Timestamps: first bit, from this interface's PHY signals receptionStarted /
//    transmissionStarted, associated with the frame by packet tree id (design 3.4).
//    Clock: simulation time (the ideal 5G time of the M2 model).
//  - Frames: INET Gptp chunks with INET's header values; Ethernet header, padding and FCS
//    built here as INET's EthernetLayer builds them (computed FCS, inet::computeChecksum).
//  - Requester state machine (design 4.5): IDLE, WAIT_RESP, WAIT_FU, DONE, FAULTED; each
//    sequenceId is published at most once; late duplicates are counted, never re-published.
//  - Link delay (design 4.6): D = (nRR * (t4 - t1) - (t3 - t2)) / 2 with INET's fixed-point
//    rate ratio and C++ truncation; nRR from consecutive completed exchanges.
// Nothing here touches Sync/Follow_Up or any correctionField.
//
class TtPdelayEngine : public cSimpleModule, public cListener
{
  public:
    // gPTP messageType of a frame addressed to 01-80-C2-00-00-0E with EtherType 0x88F7
    // (untagged or behind one 802.1Q tag): 0..15, or -1 if not such a frame; -2 if it is
    // such a frame but has no gPTP byte at all.
    static int classify(const Packet *packet, b& gptpOffset);
    static bool isPdelayType(int messageType) { return messageType == 2 || messageType == 3 || messageType == 10; }

    enum State { IDLE, WAIT_RESP, WAIT_FU, DONE, FAULTED };
    static const char *stateName(State s);

    // M2-S5 (migration/m2-s5-design.md 2.3): read-only view of the last published link
    // delay, for the NW-TT Follow_Up correction. valid: at least one publication;
    // measuring: the record-only flag of design 4.5 (D within [0, neighborPropDelayThresh],
    // fewer than allowedLostResponses + 1 consecutive losses).
    struct LinkDelayState {
        bool valid = false;
        bool measuring = false;
        simtime_t meanLinkDelay;
        ClockTimeScale neighborRateRatio;
        int64_t nrrNum = 1, nrrDen = 1;
        uint16_t sequenceId = 0;
        simtime_t publishedAt;
    };

  protected:
    // configuration
    bool terminate = false;
    bool requester = false;
    bool responder = false;
    uint64_t clockIdentity = 0;
    uint16_t portNumber = 1;
    int domainNumber = 0;
    simtime_t pdelayInterval;
    int allowedLostResponses = 3;
    simtime_t neighborPropDelayThresh;
    // TEST ONLY knobs (negative controls, design section 9); empty = correct behaviour
    std::string pairingTest, timestampTest, unitTest, formulaTest, faultPolicyTest;

    // environment
    cModule *interfaceModule = nullptr;
    cModule *transmitterModule = nullptr;
    cModule *receiverModule = nullptr;
    TtPdelayFlow *txFlow = nullptr;
    int interfaceId = -1;
    std::ofstream log;

    // PHY observation (first-bit timestamps)
    long rxStartTree = -1, rxEndTree = -1;
    simtime_t rxStartTime = -1, rxEndTime = -1;
    struct TxRecord {
        int messageType = -1;
        uint16_t seq = 0;
        PortIdentity requesting;      // Resp: requester identity (for the Resp_Follow_Up)
        simtime_t tTxStart = -1, tTxEnd = -1;
    };
    std::map<long, TxRecord> pendingTx;   // tree id -> own frame not yet fully transmitted
    std::deque<Packet *> outbox;          // own frames waiting for the send event
    cMessage *sendEvent = nullptr;

    // responder
    bool havePrevReq = false;             // TEST ONLY pairingTest = "previousSeq"
    uint16_t prevReqSeq = 0;
    PortIdentity prevReqSource;

    // requester
    cMessage *reqTimer = nullptr;
    State state = IDLE;
    uint16_t seq = 0;                     // sequenceId of the most recent own request
    bool firstRequest = true;
    simtime_t t1 = -1, t1End = -1, prevT1 = -1;
    simtime_t t2 = -1, t3 = -1, t4 = -1, t4End = -1;
    PortIdentity lastResponder;
    bool haveResponder = false;
    bool havePrevExchange = false;
    simtime_t prevT3, prevT4;             // last completed exchange (neighborRateRatio)
    ClockTimeScale lastNrr;               // rate ratio used for the last publication
    int64_t lastNrrNum = 1, lastNrrDen = 1;
    LinkDelayState lastPublished;         // M2-S5 accessor (assigned in publish(), never read here)
    int consecutiveLost = 0;
    bool measuring = false;
    cOutVector meanLinkDelayVector, nrrVector, measuringVector;

    // counters (scalars)
    long numPassedPdelay[16] = {};        // passive: seen and passed, per messageType
    long numTerminated[16] = {};          // terminate: taken, per messageType
    long numMalformed = 0, numLoopback = 0;
    long numReqAnswered = 0, numRespSent = 0, numRespFollowUpSent = 0;
    long numReqSent = 0, numPublished = 0, numLost = 0, numMultipleResp = 0, numOrphanFollowUp = 0;
    long numStaleSeq = 0, numNotForUs = 0, numLateDuplicateResp = 0, numLateDuplicateFU = 0, numLateAfterFault = 0;
    long numResponderChanged = 0, numRepublished = 0;
    bool selfTestPassed = false;

  public:
    virtual ~TtPdelayEngine();

  protected:
    virtual void initialize() override;
    virtual void finish() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details) override;

    MacAddress ownMacAddress() const;
    Packet *buildFrame(const char *name, const Ptr<GptpBase>& gptp) const;
    void send(Packet *packet, int messageType, uint16_t sequenceId, const PortIdentity& requesting);
    std::string validate(const Packet *packet, b gptpOffset, int messageType, Ptr<const GptpBase>& out) const;

    void processRequest(const GptpPdelayReq *req, simtime_t tRxStart, simtime_t tRxEnd);
    void sendRequest();
    void requestTimer();
    void processResponse(const GptpPdelayResp *resp, simtime_t tRxStart, simtime_t tRxEnd);
    void processResponseFollowUp(const GptpPdelayRespFollowUp *fu, simtime_t tRxStart, simtime_t tRxEnd);
    void publish(bool republish, const char *note);

    void writeLog(const char *event, int messageType, long seqId, const PortIdentity *source, const PortIdentity *requesting,
                  simtime_t tA, simtime_t tB, const std::string& note);
    void selfTest();

  public:
    // rx flow: true if the engine takes the frame (terminated here)
    bool offerReceived(Packet *packet);

    LinkDelayState linkDelayState() const;
};

} // namespace nasctime

#endif
