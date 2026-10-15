//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtPdelayFlow.h"

#include "TtPdelayEngine.h"

namespace nasctime {

Define_Module(TtPdelayFlow);

void TtPdelayFlow::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL) {
        std::string r = par("role").stdstringValue();
        if (r == "rx")
            isRx = true;
        else if (r == "tx")
            isRx = false;
        else
            throw cRuntimeError("Unknown role '%s'", r.c_str());
        engine = check_and_cast<TtPdelayEngine *>(getModuleByPath(par("engineModule").stringValue()));
    }
}

cGate *TtPdelayFlow::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

void TtPdelayFlow::pushPacket(Packet *packet, const cGate *gate)
{
    Enter_Method("pushPacket");
    if (isRx && engine->offerReceived(packet)) {
        // taken over by the engine: terminated at this port, never forwarded
        return;
    }
    PacketFlowBase::pushPacket(packet, gate);
}

void TtPdelayFlow::inject(Packet *packet)
{
    Enter_Method("inject");
    if (isRx)
        throw cRuntimeError("inject() on the rx flow");
    take(packet);
    pushOrSendPacket(packet, outputGate, consumer);
}

void TtPdelayFlow::pushPacketStart(Packet *packet, const cGate *gate, bps datarate)
{
    throw cRuntimeError("Packet streaming through TtPdelayPort is not supported (packet %s)", packet->getName());
}

void TtPdelayFlow::pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength)
{
    throw cRuntimeError("Packet streaming through TtPdelayPort is not supported (packet %s)", packet->getName());
}

void TtPdelayFlow::pushPacketEnd(Packet *packet, const cGate *gate)
{
    throw cRuntimeError("Packet streaming through TtPdelayPort is not supported (packet %s)", packet->getName());
}

} // namespace nasctime
