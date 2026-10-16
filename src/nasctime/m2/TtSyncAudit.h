//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCAUDIT_H
#define __NASCTIME_M2_TTSYNCAUDIT_H

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

namespace nasctime {

using namespace inet;

//
// M2-S5 containment audit (migration/m2-s5-design.md C8): counts frames that carry a
// TtSyncIngressTag at any chunk level; changes nothing.
//
class TtSyncAudit : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener
{
  protected:
    long numFrames = 0, numFollowUps = 0, numTaggedFrames = 0, numTagRegions = 0;

  protected:
    virtual void finish() override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override;
};

} // namespace nasctime

#endif
