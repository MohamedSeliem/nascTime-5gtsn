//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTPDELAYENGINE_H
#define __NASCTIME_M2_TTPDELAYENGINE_H

#include "inet/common/packet/Packet.h"

namespace nasctime {

using namespace inet;

//
// M2-S4 per-port Pdelay engine (migration/m2-s4-design.md). Passive skeleton: classifies
// and counts; terminate/requester/responder are not implemented in this commit.
//
class TtPdelayEngine : public cSimpleModule
{
  public:
    // gPTP messageType of a frame addressed to 01-80-C2-00-00-0E with EtherType 0x88F7
    // (untagged or behind one 802.1Q tag): 0..15, or -1 if not such a frame; -2 if it is
    // such a frame but has no gPTP byte at all.
    static int classify(const Packet *packet, b& gptpOffset);
    static bool isPdelayType(int messageType) { return messageType == 2 || messageType == 3 || messageType == 10; }

  protected:
    bool terminate = false;
    bool requester = false;
    bool responder = false;
    long numPassedPdelay[16] = {};   // passive: Pdelay frames seen and passed, per messageType

  protected:
    virtual void initialize() override;
    virtual void finish() override;
    virtual void handleMessage(cMessage *msg) override;

  public:
    // rx flow: true if the engine takes the frame (terminated here)
    bool offerReceived(Packet *packet);
};

} // namespace nasctime

#endif
