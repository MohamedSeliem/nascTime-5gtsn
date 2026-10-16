//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_SYNCFAULTINJECTOR_H
#define __NASCTIME_M2_SYNCFAULTINJECTOR_H

#include <set>

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

namespace nasctime {

using namespace inet;

//
// TEST ONLY (M2-S5 fault cases, migration/m2-s5-design.md 7.5). See SyncFaultInjector.ned.
//
class SyncFaultInjector : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener
{
  protected:
    std::string action;
    std::set<int> types;
    std::set<int> seqs;
    bool allSeqs = false;
    int afterType = 0;
    int afterSeqOffset = 0;
    simtime_t delay;
    std::string field;
    int value = 0;
    int truncateTo = 60;

    struct Held {
        Packet *packet;
        int seq;
    };
    std::vector<Held> held;
    std::vector<std::pair<cMessage *, Packet *>> delayed;
    Packet *lastFollowUp = nullptr;   // fuBefore
    long numActed = 0;

  public:
    virtual ~SyncFaultInjector();

  protected:
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override {}

    void forward(Packet *packet);
    static void recomputeFcs(Packet *packet);
    Packet *copyWithNewTree(const Packet *packet) const;
    Packet *rewritten(const Packet *packet, int type) const;
    Packet *tagEdited(const Packet *packet) const;

  public:
    virtual void pushPacket(Packet *packet, const cGate *gate) override;
};

} // namespace nasctime

#endif
