//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCINGRESS_H
#define __NASCTIME_M2_TTSYNCINGRESS_H

#include <fstream>

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

#include "TtGptpFrame.h"

namespace nasctime {

using namespace inet;

class TtPdelayEngine;

//
// M2-S5 NW-TT ingress (migration/m2-s5-design.md 6.2), RX path of TtPtpPort, above the
// Pdelay engine. Downlink two-step gPTP:
//  - Sync of domainNumber: TSi = first bit (receptionStarted of the same tree id);
//    state IDLE / WAIT_FU(k) / AMBIGUOUS(k). The Sync is never changed.
//  - Follow_Up of domainNumber:
//      class V (associated with WAIT_FU(k), valid link delay): cf1 = cf_in + rr_in (x) Lup,
//               rr_out = rr_in (x) nRR, TtSyncIngressTag{VALID, TSi, key, ...}, FCS recomputed;
//      class I (parseable, not correctable): cf unchanged, TtSyncIngressTag{INVALID, reason};
//      class M (malformed / unsupported representation): discarded here.
//  - everything else passes unchanged.
// enabled = false: classify and count only (gate G0).
//
class TtSyncIngress : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener, public cListener
{
  protected:
    enum State { IDLE, WAIT_FU, AMBIGUOUS };
    static const char *stateName(State s);

    bool enabled = false;
    int ttId = -1;
    int domainNumber = 0;
    bool selfCheck = true;
    // TEST ONLY (negative controls, design 8.1); "" / -1 = correct behaviour
    std::string correctionTest;      // "noLinkDelay" | "lupTwice" | "rr" | "noFcs" | "tsiEnd" | "syncCf"
    simtime_t fixedLinkDelay;        // >= 0: use this instead of the engine's (N14)

    TtPdelayEngine *engine = nullptr;
    cModule *interfaceModule = nullptr;
    cModule *receiverModule = nullptr;
    long rxStartTree = -1, rxEndTree = -1;
    simtime_t rxStartTime = -1, rxEndTime = -1;
    std::ofstream log;

    State state = IDLE;
    gptpframe::Key waitKey, lastKey;
    simtime_t waitTsi;
    uint64_t waitSyncFrameId = 0;

    // counters
    long numSyncSeen = 0, numFollowUpSeen = 0;     // also when disabled
    long numSync = 0, numCorrected = 0, numInvalid = 0;
    long numSyncWithoutFU = 0, numDuplicateSync = 0, numAmbiguousSync = 0, numFuMismatch = 0;
    long numNoLinkDelay = 0, numDuplicateFU = 0, numOrphanFU = 0;
    long numMalformedFU = 0, numUnsupportedRepresentation = 0, numMalformedSync = 0, numOtherDomain = 0;
    bool selfTestPassed = false;

  protected:
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override {}
    virtual void receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details) override;

    // false: the packet was consumed (discarded)
    bool process(Packet *packet);
    void processSync(Packet *packet, b off, simtime_t tsi);
    bool processFollowUp(Packet *packet);
    void tagInvalid(Packet *packet, const gptpframe::FollowUpFrame& f, const char *reason);
    void rewriteSyncCorrection(Packet *packet, b off, clocktime_t cf);   // TEST ONLY syncCf

    void writeLog(const char *event, int msgType, const gptpframe::Key& key, long treeId, uint64_t syncFrameId, uint64_t fuFrameId,
                  simtime_t tsi, simtime_t lup, simtime_t cfIn, simtime_t cfOut, double rrIn, double rrOut, const std::string& note);

  public:
    virtual void pushPacket(Packet *packet, const cGate *gate) override;
    virtual void pushPacketStart(Packet *packet, const cGate *gate, bps datarate) override;
    virtual void pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength) override;
    virtual void pushPacketEnd(Packet *packet, const cGate *gate) override;
};

} // namespace nasctime

#endif
