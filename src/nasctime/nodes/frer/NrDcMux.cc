////
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork),
//          Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

#include "nasctime/nodes/frer/NrDcMux.h"

#include "inet/common/packet/Packet.h"
#include "inet/common/ModuleAccess.h"
#include "simu5g/common/LteControlInfoTags_m.h"
#include "simu5g/common/binder/Binder.h"
#include "simu5g/stack/mac/LteMacEnb.h"
#include "simu5g/stack/mac/LteMacUe.h"

using namespace inet;
using namespace simu5g;

Define_Module(NrDcMux);

void NrDcMux::initialize()
{
    upperInId     = gate("upper$i")->getId();
    upperOutId    = gate("upper$o")->getId();
    primaryInId   = gate("primary$i")->getId();
    primaryOutId  = gate("primary$o")->getId();
    secondaryInId = gate("secondary$i")->getId();
    secondaryOutId= gate("secondary$o")->getId();
    binder_ = getModuleFromPar<Binder>(par("binderModule"), this);

    cStringTokenizer tokenizer(par("secondaryDscps").stringValue(), ",");
    while (tokenizer.hasMoreTokens())
        secondaryDscps_.insert(atoi(tokenizer.nextToken()));
}

bool NrDcMux::useSecondaryLeg(cMessage *msg) const
{
    auto *pkt = dynamic_cast<Packet *>(msg);
    if (!pkt)
        return false;

    // Ip2Nic records the IPv4 ToS octet in FlowControlInfo before handing
    // the packet to SDAP.  Convert it back to the six-bit DSCP value using
    // the same rule as NrSdap::useDscpAsQfiFallback.
    auto flowInfo = pkt->findTag<FlowControlInfo>();
    if (!flowInfo)
        return false;
    int dscp = static_cast<uint8_t>(flowInfo->getTypeOfService()) >> 2;
    return secondaryDscps_.count(dscp) != 0;
}

void NrDcMux::selectSecondaryDestination(cMessage *msg)
{
    auto *pkt = check_and_cast<Packet *>(msg);
    auto flowInfo = pkt->getTagForUpdate<FlowControlInfo>();
    MacNodeId secondary = binder_->getDcSecondaryNextHop(flowInfo->getSourceId());
    if (secondary == NODEID_NONE) {
        throw cRuntimeError("NrDcMux: no DC secondary registered for UE %d",
                            num(flowInfo->getSourceId()));
    }

    // SDAP uses destId while asking Binder to establish the DRB.  Point the
    // replica at gNB2 before it reaches sdap2; otherwise the UE creates a
    // secondary local PDCP/RLC stack whose peer and UL grants still belong to
    // the primary gNB.
    flowInfo->setDestId(secondary);

    // Simu5G normally models one MAC/RAC state machine per UE node ID.  The
    // DC FRER UE deliberately has two MACs sharing that identity, so prime
    // the secondary access once.  The first RAC-sized grant carries a BSR;
    // all later grants are driven by the ordinary gNB2 BSR scheduler state.
    int ueKey = num(flowInfo->getSourceId());
    if (primedSecondaryUes_.insert(ueKey).second) {
        auto *secondaryMac = check_and_cast<LteMacUe *>(
            getParentModule()->getSubmodule("nrMac2"));
        auto *gnb2Mac = check_and_cast<LteMacEnb *>(
            binder_->getMacFromMacNodeId(secondary));
        secondaryMac->primeDcUplinkAccess(secondary);
        gnb2Mac->primeDcUplinkAccess(flowInfo->getSourceId());
    }
}

void NrDcMux::handleMessage(cMessage *msg)
{
    int gateId = msg->getArrivalGateId();

    if (gateId == primaryInId || gateId == secondaryInId) {
        // Downlink: forward from either NR stack to ip2nic
        send(msg, upperOutId);
    }
    else if (gateId == upperInId) {
        // Uplink: FRER replica DSCPs enter the fully independent secondary
        // SDAP/PDCP/RLC/MAC/PHY stack; all other traffic uses the primary.
        if (useSecondaryLeg(msg)) {
            selectSecondaryDestination(msg);
            send(msg, secondaryOutId);
        }
        else {
            send(msg, primaryOutId);
        }
    }
    else {
        EV_WARN << "NrDcMux: unexpected gate, dropping" << endl;
        delete msg;
    }
}
