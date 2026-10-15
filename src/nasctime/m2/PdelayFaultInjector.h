//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_PDELAYFAULTINJECTOR_H
#define __NASCTIME_M2_PDELAYFAULTINJECTOR_H

#include <set>
#include <vector>

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/queueing/base/PacketFlowBase.h"

namespace nasctime {

using namespace inet;

// TEST ONLY: see PdelayFaultInjector.ned
class PdelayFaultInjector : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener
{
  protected:
    std::string action;
    std::set<int> types;
    std::set<int> seqs;
    bool allSeqs = false;
    int afterType = 10;
    simtime_t delay;
    std::string field;
    int value = 0;
    int truncateTo = 40;
    struct Held {
        Packet *packet;
        int seq;
    };
    std::vector<Held> held;            // dupAfter / holdUntilAfter
    std::vector<std::pair<cMessage *, Packet *>> delayed;
    long numActed = 0;

  protected:
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override {}
    void forward(Packet *packet);
    Packet *rewritten(Packet *packet) const;
    static void recomputeFcs(Packet *packet);

  public:
    virtual ~PdelayFaultInjector();
    virtual void pushPacket(Packet *packet, const cGate *gate) override;
};

} // namespace nasctime

#endif
