//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTPDELAYFLOW_H
#define __NASCTIME_M2_TTPDELAYFLOW_H

#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/packet/Packet.h"
#include "inet/queueing/base/PacketFlowBase.h"

namespace nasctime {

using namespace inet;

class TtPdelayEngine;

//
// One direction of TtPdelayPort (see TtPdelayPort.ned).
//
class TtPdelayFlow : public queueing::PacketFlowBase, public TransparentProtocolRegistrationListener
{
  protected:
    bool isRx = true;
    TtPdelayEngine *engine = nullptr;

  protected:
    virtual void initialize(int stage) override;
    virtual cGate *getRegistrationForwardingGate(cGate *gate) override;
    virtual void processPacket(Packet *packet) override {}

  public:
    virtual void pushPacket(Packet *packet, const cGate *gate) override;
    virtual void pushPacketStart(Packet *packet, const cGate *gate, bps datarate) override;
    virtual void pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength) override;
    virtual void pushPacketEnd(Packet *packet, const cGate *gate) override;

    // tx role: the engine's own frame enters the TX path here (below the bridge,
    // above the TtTimestampLayer and the MAC)
    void inject(Packet *packet);
};

} // namespace nasctime

#endif
