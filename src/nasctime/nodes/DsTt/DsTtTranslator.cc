//
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork), Afshin Zanganeh and How-Hang Liu
//          (Technical University of Dresden)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

#include "nasctime/nodes/DsTt/DsTtTranslator.h"

#include "nasctime/nodes/NwTt/GptpResidenceHeader_m.h"
#include "inet/common/ProtocolTag_m.h"
#include "inet/linklayer/common/MacAddressTag_m.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/common/InterfaceTag_m.h"
#include "inet/linklayer/common/EtherType_m.h"
#include "inet/linklayer/ieee8021q/Ieee8021qTagHeader_m.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"
#include "inet/transportlayer/udp/UdpHeader_m.h"
#include "inet/linklayer/ieee8021as/GptpPacket_m.h"
#include "inet/clock/common/ClockTime.h"
#include "inet/linklayer/common/UserPriorityTag_m.h"
#include "inet/linklayer/common/PcpTag_m.h"
#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/DirectionTag_m.h"
#include "inet/common/ProtocolUtils.h"

Define_Module(DsTtTranslator);

void DsTtTranslator::initialize()
{
    gptpEncapUdpPort = par("gptpEncapUdpPort");
    cStringTokenizer tokenizer(par("mappedPcpValues").stringValue(), ",");
    while (tokenizer.hasMoreTokens())
        mappedPcpSet.insert(atoi(tokenizer.nextToken()));
    tsnInGateId  = gate("tsnIn")->getId();
    tsnOutGateId = gate("tsnOut")->getId();
    ueInGateId   = gate("ueIn")->getId();
    ueOutGateId  = gate("ueOut")->getId();
    gptpInGateId = gate("gptpIn")->getId();

    tsnToUeSignal     = registerSignal("tsnToUeForwarded");
    ueToTsnSignal     = registerSignal("ueToTsnForwarded");
    packetDroppedSignal = registerSignal("packetDropped");
    residenceTimeSignal = registerSignal("residenceTime");

    registerProtocol(Protocol::ethernetMac, gate("tsnOut"), gate("tsnIn"));
    registerProtocol(Protocol::ethernetMac, gate("ueOut"), gate("ueIn"));
}

void DsTtTranslator::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage()) {
        delete msg;
        return;
    }

    auto pkt = check_and_cast<Packet *>(msg);
    int gateId = pkt->getArrivalGateId();

    if (gateId == tsnInGateId) {
        forwardToUe(pkt);
    }
    else if (gateId == ueInGateId) {
        forwardToTsn(pkt);
    }
    else if (gateId == gptpInGateId) {
        // gPTP frame from sideband — forward directly to TSN side
        numGptpForwarded++;
        EV_INFO << "DsTtTranslator gPTP sideband->TSN: " << pkt->getName() << endl;

        // The gPTP frame arrives with full Ethernet framing intact
        // (it was NOT stripped at the NW-TT). Tag it as an Ethernet frame
        // and send directly to tsnEth.
        pkt->removeTagIfPresent<PacketProtocolTag>();
        pkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ethernetMac);
        send(pkt, tsnOutGateId);
    }
    else {
        EV_WARN << "DsTtTranslator: unexpected gate, dropping" << endl;
        emit(packetDroppedSignal, ++numDropped);
        delete pkt;
    }
}

// ============================================================================
// TSN Device → UE
//
// Frame arrives from TSN device via tsnEth. Translate a mapped 802.1Q PCP to
// IPv4 DSCP before forwarding it to the UE. This is the uplink counterpart of
// NwTtTranslator's downlink PCP->DSCP translation.
// ============================================================================

void DsTtTranslator::forwardToUe(Packet *pkt)
{
    emit(tsnToUeSignal, ++numTsnToUe);

    EV_INFO << "DsTtTranslator TSN->UE: " << pkt->getName()
            << " (" << pkt->getTotalLength() << ")" << endl;

    // Strip incoming Ethernet framing from tsnEth.
    auto incomingMac = pkt->popAtFront<EthernetMacHeader>();
    pkt->popAtBack<EthernetFcs>(B(4));

    uint16_t payloadType = incomingMac->getTypeOrLength();
    auto firstChunk = pkt->peekAtFront<Chunk>();
    if (auto vlanTag = dynamicPtrCast<const Ieee8021qTagEpdHeader>(firstChunk)) {
        int pcp = vlanTag->getPcp();
        if (mappedPcpSet.count(pcp) > 0) {
            auto removedVlanTag = pkt->popAtFront<Ieee8021qTagEpdHeader>();
            payloadType = removedVlanTag->getTypeOrLength();
            if (payloadType != ETHERTYPE_IPv4)
                throw cRuntimeError("DsTtTranslator: PCP mapping currently requires IPv4 payload (EtherType 0x%04x)", payloadType);

            auto ipHeader = pkt->removeAtFront<Ipv4Header>();
            ipHeader->setDscp(pcp);
            pkt->insertAtFront(ipHeader);
            EV_INFO << "DsTtTranslator: stripped VLAN tag, PCP=" << pcp
                    << " -> DSCP=" << pcp << endl;
        }
        else {
            EV_INFO << "DsTtTranslator: preserving VLAN tag, PCP=" << pcp
                    << " (not mapped)" << endl;
        }
    }

    // Clear stale tags from incoming interface
    pkt->removeTagIfPresent<MacAddressInd>();
    pkt->removeTagIfPresent<PacketProtocolTag>();
    pkt->removeTagIfPresent<DispatchProtocolReq>();
    pkt->removeTagIfPresent<InterfaceInd>();

    // Build new Ethernet frame for ueEth (EthernetMacPhy expects complete frame)
    auto macHeader = makeShared<EthernetMacHeader>();
    macHeader->setSrc(MacAddress::UNSPECIFIED_ADDRESS);  // ueEth fills in
    macHeader->setDest(incomingMac->getDest());          // preserve original dest
    macHeader->setTypeOrLength(payloadType);
    pkt->insertAtFront(macHeader);

    auto fcs = makeShared<EthernetFcs>();
    fcs->setFcsMode(FCS_DECLARED_CORRECT);
    fcs->setFcs(0xC00DC00D);
    pkt->insertAtBack(fcs);

    pkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ethernetMac);
    pkt->addTagIfAbsent<DispatchProtocolReq>()->setProtocol(&Protocol::ethernetMac);
    pkt->addTagIfAbsent<DispatchProtocolReq>()->setServicePrimitive(SP_REQUEST);
    pkt->addTagIfAbsent<DirectionTag>()->setDirection(DIRECTION_OUTBOUND);

    send(pkt, ueOutGateId);
}

// ============================================================================
// UE → TSN Device
//
// Frame arrives from UE via ueEth. Same stripping/retagging in reverse.
// ============================================================================

void DsTtTranslator::forwardToTsn(Packet *pkt)
{
    emit(ueToTsnSignal, ++numUeToTsn);

    EV_INFO << "DsTtTranslator UE->TSN: " << pkt->getName()
            << " (" << pkt->getTotalLength() << ")" << endl;

    // Strip incoming Ethernet framing from ueEth
    pkt->popAtFront<EthernetMacHeader>();
    pkt->popAtBack<EthernetFcs>(B(4));

    // H2: Save original destination MAC before clearing tags
    MacAddress origDstMac = MacAddress::BROADCAST_ADDRESS;
    auto macInd = pkt->findTag<MacAddressInd>();
    if (macInd) {
        origDstMac = macInd->getDestAddress();
    }

    EV_INFO << "DsTtTranslator: first chunk type = "
                << pkt->peekAtFront<Chunk>()->getClassName() << endl;
    auto ipCheck = pkt->peekAtFront<Ipv4Header>();
    int pcp = ipCheck->getDscp();
    if (pcp < 0 || pcp > 7)
        pcp = 0;
    EV_INFO << "DsTtTranslator: src=" << ipCheck->getSrcAddress()
            << " dst=" << ipCheck->getDestAddress()
            << " proto=" << ipCheck->getProtocolId() << endl;

    // Check if this is a gPTP-in-UDP encapsulated frame (dedicated port)
    auto ipHdr = pkt->peekAtFront<Ipv4Header>();
    if (ipHdr->getProtocolId() == IP_PROT_UDP) {
        // Pop the IP header so UDP is at the front
        if (ipHdr->getMoreFragments() || ipHdr->getFragmentOffset() > 0) {
            EV_INFO << "DsTtTranslator: IP fragment, skipping UDP peek" << endl;
            // Fall through to regular data handling
        } else {
        auto ipHdrPopped = pkt->popAtFront<Ipv4Header>();
        //auto udpOffset = ipHdr->getChunkLength();
        auto udpHdr = pkt->peekAtFront<UdpHeader>();//pkt->peekAt<UdpHeader>(udpOffset);
        EV_INFO << "DsTtTranslator: UDP dstPort=="<< udpHdr->getDestinationPort()
                << " gptpPort="<< gptpEncapUdpPort<<endl;
        if (udpHdr->getDestinationPort() == gptpEncapUdpPort) {
            EV_INFO << "DsTtTranslator: detected gPTP-in-UDP, unwrapping" << endl;
            numGptpForwarded++;

            // Strip IP + UDP headers to get the original gPTP Ethernet frame
            //pkt->popAtFront<Ipv4Header>();
            pkt->popAtFront<UdpHeader>();
            // G3: Read and strip the residence time header
            auto residenceHdr = pkt->popAtFront<simu5g::GptpResidenceHeader>();
            simtime_t ingressTime = residenceHdr->getIngressTime();
            simtime_t residenceTime = simTime() - ingressTime;
            emit(residenceTimeSignal, residenceTime);
            EV_INFO << "DsTtTranslator: gPTP residence time = "
                    << residenceTime * 1e6 << " us" << endl;

            // What remains is the original gPTP Ethernet frame
            // Strip MAC + FCS, update correctionField, rebuild
            auto macHdr = pkt->popAtFront<EthernetMacHeader>();
            auto fcsTrailer = pkt->popAtBack<EthernetFcs>(B(4));

            if (residenceTime > SIMTIME_ZERO) {
                // H4: Peek at message type before modifying
                auto gptpPeek = pkt->peekAtFront<GptpBase>();
                auto msgType = gptpPeek->getMessageType();

                if (msgType == GPTPTYPE_SYNC) {
                    auto chunk = pkt->removeAtFront<GptpSync>();
                    clocktime_t oldCorr = chunk->getCorrectionField();
                    chunk->setCorrectionField(oldCorr + ClockTime(residenceTime.dbl()));
                    EV_INFO << "DsTtTranslator: Sync correctionField "
                            << oldCorr << " -> " << chunk->getCorrectionField() << endl;
                    pkt->insertAtFront(chunk);
                }
                else if (msgType == GPTPTYPE_FOLLOW_UP) {
                    auto chunk = pkt->removeAtFront<GptpFollowUp>();
                    clocktime_t oldCorr = chunk->getCorrectionField();
                    chunk->setCorrectionField(oldCorr + ClockTime(residenceTime.dbl()));
                    EV_INFO << "DsTtTranslator: FollowUp correctionField "
                            << oldCorr << " -> " << chunk->getCorrectionField() << endl;
                    pkt->insertAtFront(chunk);
                }
                else {
                    EV_INFO << "DsTtTranslator: gPTP msgType=" << msgType
                            << " — no correctionField update" << endl;
                }
           }

            // Rebuild Ethernet frame
            pkt->insertAtFront(macHdr);
            pkt->insertAtBack(fcsTrailer);

            pkt->removeTagIfPresent<PacketProtocolTag>();
            pkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ethernetMac);
            pkt->removeTagIfPresent<MacAddressInd>();
            pkt->removeTagIfPresent<InterfaceInd>();
            pkt->removeTagIfPresent<DispatchProtocolReq>();

            pkt->addTagIfAbsent<DispatchProtocolReq>()->setProtocol(&Protocol::ethernetMac);
            pkt->addTagIfAbsent<DispatchProtocolReq>()->setServicePrimitive(SP_REQUEST);
            pkt->addTagIfAbsent<DirectionTag>()->setDirection(DIRECTION_OUTBOUND);
            send(pkt, tsnOutGateId);
            return;
        }     else {
            // Not gPTP — put the IP header back
            pkt->insertAtFront(ipHdrPopped);
        }
        }
    }
    // Normal data frame — existing forwarding logic
    pkt->removeTagIfPresent<MacAddressInd>();
    pkt->removeTagIfPresent<PacketProtocolTag>();
    pkt->removeTagIfPresent<DispatchProtocolReq>();
    pkt->removeTagIfPresent<InterfaceInd>();

    auto macHeader = makeShared<EthernetMacHeader>();
    macHeader->setSrc(MacAddress::UNSPECIFIED_ADDRESS);
    macHeader->setDest(origDstMac);
    macHeader->setTypeOrLength(ETHERTYPE_IPv4);
    pkt->insertAtFront(macHeader);

    auto fcs = makeShared<EthernetFcs>();
    fcs->setFcsMode(FCS_DECLARED_CORRECT);
    fcs->setFcs(0xC00DC00D);
    pkt->insertAtBack(fcs);

    pkt->addTagIfAbsent<PacketProtocolTag>()->setProtocol(&Protocol::ethernetMac);
    pkt->addTagIfAbsent<DispatchProtocolReq>()->setProtocol(&Protocol::ethernetMac);
    pkt->addTagIfAbsent<DispatchProtocolReq>()->setServicePrimitive(SP_REQUEST);
    pkt->addTagIfAbsent<DirectionTag>()->setDirection(DIRECTION_OUTBOUND);
    pkt->addTagIfAbsent<PcpReq>()->setPcp(pcp);
    send(pkt, tsnOutGateId);
}

void DsTtTranslator::finish()
{
    EV_INFO << "DsTtTranslator stats:"
            << " tsnToUe=" << numTsnToUe
            << " ueToTsn=" << numUeToTsn
            << " gptpForwarded=" << numGptpForwarded
            << " dropped=" << numDropped << endl;
}
