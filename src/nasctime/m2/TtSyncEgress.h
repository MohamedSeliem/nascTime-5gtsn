//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCEGRESS_H
#define __NASCTIME_M2_TTSYNCEGRESS_H

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

namespace nasctime {

using namespace inet;

//
// M2-S5 DS-TT egress element of TtPtpPort (migration/m2-s5-design.md 6.3).
// SKELETON (implementation step 2, gate G0): classifies and counts Sync/Follow_Up frames
// and passes every frame unchanged. The correction is not implemented yet: mode != "off"
// is refused.
//
class TtSyncEgress : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener
{
  protected:
    long numSyncSeen = 0, numFollowUpSeen = 0;

  protected:
    virtual void initialize(int stage) override;
    virtual void finish() override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override;
};

} // namespace nasctime

#endif
