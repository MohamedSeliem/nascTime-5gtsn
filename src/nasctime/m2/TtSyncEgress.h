//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCEGRESS_H
#define __NASCTIME_M2_TTSYNCEGRESS_H

#include <deque>
#include <fstream>
#include <map>

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

#include "TtGptpFrame.h"

namespace nasctime {

using namespace inet;

//
// M2-S5 DS-TT egress (migration/m2-s5-design.md 6.3), TX path of TtPtpPort, below the
// Pdelay engine's injection point and above the M2-S0/S1 TtTimestampLayer and the MAC FIFO.
//  - Sync of domainNumber: recorded as pending (tree id); TSe = first bit
//    (transmissionStarted of that tree id); never changed.
//  - Follow_Up of domainNumber, fail-closed: forwarded only with exactly one VALID
//    TtSyncIngressTag over the whole chunk whose key matches, and only for the most
//    recently transmitted Sync, at most once per Sync. Then Res = TSe - TSi,
//    cf2 = cf1 + rr_out (x) Res, the tag is removed and the FCS recomputed. Every other
//    Follow_Up is discarded (counted by reason).
//  - FIFO hold: a Follow_Up whose Sync is still pending (queued in the MAC FIFO) is held,
//    with every later frame behind it, until that Sync starts transmitting (zero-delay
//    release) or holdTimeout expires (the Follow_Up is then discarded).
// mode "off": classify and count only (gate G0); "audit": log every Follow_Up's tag, change
// nothing (gate V0); "correct": as above.
//
class TtSyncEgress : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener, public cListener
{
  protected:
    enum Mode { OFF, AUDIT, CORRECT };
    Mode mode = OFF;
    int ttId = -1;
    int domainNumber = 0;
    simtime_t holdTimeout;
    bool crossCheckFrameId = true;
    bool selfCheck = true;
    // TEST ONLY (negative controls, design 8.1); "" / -1 = correct behaviour
    std::string egressTest;          // "tseEnd" | "tseSlot" | "prevSync" | "noFcs" | "noStrip" | "forwardInvalid" | "noHold"
    int dropSyncSeq = -1;            // TEST ONLY (H4): this Sync is registered, then lost below the hold point

    cModule *interfaceModule = nullptr;
    cModule *transmitterModule = nullptr;
    std::ofstream log;

    struct PendingSync {
        gptpframe::Key key;
        uint64_t frameId = 0;
        simtime_t slotTime;
    };
    // Syncs that passed here and have not started transmitting, in FIFO order (tree id, Sync);
    // a duplicated frame may carry the same tree id, so this is not a map
    std::deque<std::pair<long, PendingSync>> pending;
    struct TxSync {
        gptpframe::Key key;
        uint64_t frameId = 0;
        long treeId = -1;
        simtime_t tse = -1;
        bool fuSent = false;
        bool ambiguous = false;
    };
    TxSync lastTx;
    std::deque<gptpframe::Key> recentTx;     // last 16 transmitted Sync keys
    simtime_t lastCorrectedRes = -1;         // TEST ONLY prevSync

    std::deque<Packet *> held;               // FIFO hold: held Follow_Up first, then every later frame
    bool holding = false;
    gptpframe::Key heldKey;
    cMessage *releaseEvent = nullptr;
    cMessage *holdTimer = nullptr;

    // counters
    long numSyncSeen = 0, numFollowUpSeen = 0;
    long numSync = 0, numSyncTransmitted = 0, numCorrected = 0, numFuNoTag = 0, numFuInvalidUpstream = 0, numTagMismatch = 0;
    long numHolds = 0, numHeldFrames = 0, numAmbiguousSync = 0, numDuplicateFU = 0, numAssociationMismatch = 0;
    long numStaleFU = 0, numFuNoSync = 0, numFuHoldExpired = 0, numMalformedFU = 0, numUnsupportedRepresentation = 0;
    long numOtherDomain = 0, numSyncDroppedTest = 0, numAuditValid = 0, numAuditInvalid = 0, numAuditNoTag = 0;

  public:
    virtual ~TtSyncEgress();

  protected:
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override {}
    virtual void receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details) override;

    void deliver(Packet *packet);            // in arrival order (also for released frames)
    void forward(Packet *packet);
    void discard(Packet *packet, long& counter, const char *event, const gptpframe::FollowUpFrame& f, const std::string& note);
    void processFollowUp(Packet *packet);
    void startHold(Packet *packet, const gptpframe::Key& key);
    void release(bool expired);

    void writeLog(const char *event, int msgType, const gptpframe::Key& key, long treeId, uint64_t syncFrameId, uint64_t fuFrameId,
                  const TtSyncIngressTag *tag, simtime_t tse, simtime_t res, simtime_t cfOut, const std::string& note);

  public:
    virtual void pushPacket(Packet *packet, const cGate *gate) override;
    virtual void pushPacketStart(Packet *packet, const cGate *gate, bps datarate) override;
    virtual void pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength) override;
    virtual void pushPacketEnd(Packet *packet, const cGate *gate) override;
};

} // namespace nasctime

#endif
