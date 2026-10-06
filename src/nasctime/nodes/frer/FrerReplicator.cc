//
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

#include "nasctime/nodes/frer/FrerReplicator.h"

#include "nasctime/nodes/frer/FrerSequenceHeader_m.h"
#include "inet/common/ProtocolTag_m.h"
#include "inet/common/IProtocolRegistrationListener.h"
#include "inet/common/ProtocolUtils.h"
#include "inet/linklayer/common/InterfaceTag_m.h"
#include "inet/networklayer/ipv4/Ipv4Header_m.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/networklayer/common/InterfaceTable.h"

Define_Module(FrerReplicator);

// ============================================================================
// Initialization
// ============================================================================
void FrerReplicator::initialize(int stage)
{
    if (stage == INITSTAGE_LOCAL) {
        inGateId  = gate("in")->getId();
        outGateId = gate("out")->getId();

        replicaDscp = par("replicaDscp");
        transportBindingType = par("transportBinding").stdstringValue();
        ethernetFramed     = par("ethernetFramed");

        // Parse comma-separated DSCP values
        const char *streams = par("frerStreams").stringValue();
        cStringTokenizer tokenizer(streams, ",");
        while (tokenizer.hasMoreTokens()) {
            frerStreamDscpSet.insert(atoi(tokenizer.nextToken()));
        }

        // Register signals
        replicatedFramesSignal = registerSignal("replicatedFrames");
        primarySentSignal      = registerSignal("primarySent");
        replicaSentSignal      = registerSignal("replicaSent");
        passedThroughSignal    = registerSignal("passedThrough");
    }
    else if (stage == INITSTAGE_NETWORK_INTERFACE_CONFIGURATION) {
        initializeTransportBinding();
        // Register protocol when handling Ethernet-framed packets (uplink at DS-TT)
        if (ethernetFramed) {
            registerProtocol(Protocol::ethernetMac, gate("out"), gate("in"));
        }

        EV_INFO << "FrerReplicator: initialised — eligible DSCPs={";
        for (int d : frerStreamDscpSet)
            EV_INFO << d << ",";
        EV_INFO << "} replicaDscp=" << replicaDscp
                << " binding=" << transportBindingType << endl;
    }
}

void FrerReplicator::initializeTransportBinding()
{
    int representativeDscp = frerStreamDscpSet.empty()
                                 ? 7
                                 : *frerStreamDscpSet.begin();

    if (transportBindingType == "drb") {
        transportBinding = new DrbTransportBinding(representativeDscp,
                                                   replicaDscp);
    }
    else if (transportBindingType == "pduSession"
          || transportBindingType == "dualConnectivity") {

        const char *ifName = par("replicaInterface").stringValue();

        if (strlen(ifName) == 0)
            throw cRuntimeError("FrerReplicator: replicaInterface must be set "
                                "for '%s' binding", transportBindingType.c_str());

        IInterfaceTable *ift = getModuleFromPar<IInterfaceTable>(
            par("interfaceTableModule"), this);

        EV_INFO << "FrerReplicator available interfaces in "
                << getParentModule()->getFullPath()
                << ":\n";

        for (int i = 0; i < ift->getNumInterfaces(); i++) {
            NetworkInterface *iface = ift->getInterface(i);

            EV_INFO << "  - name=" << iface->getInterfaceName()
                    << ", id=" << iface->getInterfaceId()
                    << "\n";
        }

        NetworkInterface *ie = ift->findInterfaceByName(ifName);

        if (!ie)
            throw cRuntimeError("FrerReplicator: interface '%s' not found in "
                                "interface table", ifName);

        int replicaIfId = ie->getInterfaceId();

        if (transportBindingType == "pduSession") {
            transportBinding = new PduSessionTransportBinding(
                representativeDscp, replicaDscp, replicaIfId);
        }
        else {
            transportBinding = new DualConnTransportBinding(
                representativeDscp, replicaDscp, replicaIfId);
        }

        EV_INFO << "FrerReplicator: replica interface '" << ifName
                << "' (id=" << replicaIfId << ")" << endl;
    }
    else {
        throw cRuntimeError("FrerReplicator: unknown transportBinding '%s'",
                            transportBindingType.c_str());
    }

}


// ============================================================================
// Message handling
// ============================================================================

void FrerReplicator::handleMessage(cMessage *msg)
{
    if (msg->isSelfMessage()) {
        delete msg;
        return;
    }

    auto pkt = check_and_cast<Packet *>(msg);
    int dscp = -1;

    if (isFrerEligible(pkt, dscp)) {
        replicateAndSend(pkt, dscp);
    }
    else {
        numPassedThrough++;
        emit(passedThroughSignal, numPassedThrough);
        send(pkt, outGateId);
    }
}

// ============================================================================
// Stream identification (802.1CB §6)
// ============================================================================

bool FrerReplicator::isFrerEligible(Packet *pkt, int &dscp)
{
    if (ethernetFramed) {
        // Strip Ethernet to peek at IPv4
        auto ethHdr = pkt->popAtFront<EthernetMacHeader>();
        auto fcs    = pkt->popAtBack<EthernetFcs>(B(4));
        auto ipHdr  = pkt->peekAtFront<Ipv4Header>();
        dscp = ipHdr->getDscp();
        // Re-insert Ethernet
        pkt->insertAtFront(ethHdr);
        pkt->insertAtBack(fcs);
    } else {
        auto ipHdr = pkt->peekAtFront<Ipv4Header>();
        dscp = ipHdr->getDscp();
    }
    return frerStreamDscpSet.count(dscp) > 0;
}

// ============================================================================
// Sequence generation (802.1CB §7.4)
// ============================================================================

uint16_t FrerReplicator::nextSequenceNumber(int streamId)
{
    uint16_t seq = sequenceCounters[streamId];
    sequenceCounters[streamId] = static_cast<uint16_t>(seq + 1);
    return seq;
}

// ============================================================================
// Stream splitting (802.1CB §7.7)
// ============================================================================

void FrerReplicator::replicateAndSend(Packet *pkt, int dscp)
{
    // For Ethernet-framed packets, strip framing first
    inet::Ptr<const EthernetMacHeader> ethHdr;
    inet::Ptr<const EthernetFcs> fcs;

    if (ethernetFramed) {
        ethHdr = pkt->popAtFront<EthernetMacHeader>();
        fcs    = pkt->popAtBack<EthernetFcs>(B(4));
    }

    // --- MTU guard: prevent IP fragmentation ---
    // FRER-eligible flows must be sized so payload + headers + R-TAG <= 1500.
    // If not, skip replication to avoid fragmenting the R-TAG across packets.
    if (pkt->getTotalLength() + B(4) > B(1500)) {
        EV_WARN << "FrerReplicator: packet too large for FRER ("
                << pkt->getTotalLength() << " + 4 B > 1500 B MTU), "
                << "passing through without replication: "
                << pkt->getName() << endl;
        numPassedThrough++;
        emit(passedThroughSignal, numPassedThrough);
        // The uplink replicator receives complete Ethernet frames.  Restore
        // the framing removed above before taking the non-FRER pass-through
        // path; otherwise a bare IPv4 packet is sent to the Ethernet
        // dispatcher.
        if (ethernetFramed) {
            pkt->insertAtFront(ethHdr);
            pkt->insertAtBack(fcs);
        }
        send(pkt, outGateId);
        return;
    }

    uint16_t seqNum = nextSequenceNumber(dscp);

    // --- PRIMARY encoding: R-TAG (FrerSequenceHeader) at packet back ---
    // Standards-compliant 802.1CB R-TAG carrying streamId + sequenceNumber.
    // Inserted at the back to preserve the IPv4 header at the front for
    // downstream routing and dispatcher compatibility.
    auto frerHdr = makeShared<simu5g::FrerSequenceHeader>();
    frerHdr->setStreamId(static_cast<uint16_t>(dscp));
    frerHdr->setSequenceNumber(seqNum);
    pkt->insertAtBack(frerHdr);

    // --- SECONDARY encoding: IPv4 Identification field ---
    // Fallback for edge cases (IP fragments, detection failures).
    // Also aids debugging: the seq# is visible in the IPv4 header.
    auto ipHdr = pkt->removeAtFront<Ipv4Header>();
    ipHdr->setIdentification(seqNum);
    pkt->insertAtFront(ipHdr);

    // Re-add Ethernet framing before dup (both copies need it)
    if (ethernetFramed) {
        pkt->insertAtFront(ethHdr);
        pkt->insertAtBack(fcs);
    }

    // Create replica as deep copy (includes both R-TAG and IPv4 ID)
    auto replica = pkt->dup();
    replica->setName((std::string(pkt->getName()) + "-frer-replica").c_str());

    // For Ethernet-framed replicas, strip Ethernet so transport binding
    // can modify IPv4 DSCP, then re-add Ethernet
    if (ethernetFramed) {
        auto repEth = replica->popAtFront<EthernetMacHeader>();
        auto repFcs = replica->popAtBack<EthernetFcs>(B(4));
        transportBinding->prepareMemberStreams(pkt, replica);
        replica->insertAtFront(repEth);
        replica->insertAtBack(repFcs);
    } else {
        // Apply transport binding — for DRB binding this sets the replica's
        // DSCP so the SDAP layer routes it to a different DRB.
        transportBinding->prepareMemberStreams(pkt, replica);
    }

    // --- Send primary ---
    numPrimarySent++;
    numReplicated++;
    emit(primarySentSignal, numPrimarySent);
    emit(replicatedFramesSignal, numReplicated);
    send(pkt, outGateId);

    // --- Send replica ---
    numReplicaSent++;
    emit(replicaSentSignal, numReplicaSent);
    send(replica, outGateId);

    EV_INFO << "FrerReplicator: stream=" << dscp
            << " seq=" << seqNum
            << " primary DSCP=" << dscp
            << " replica DSCP=" << replicaDscp
            << " [R-TAG + IPv4 ID]" << endl;
}

// ============================================================================
// Cleanup
// ============================================================================

void FrerReplicator::finish()
{
    EV_INFO << "FrerReplicator stats:"
            << " replicated=" << numReplicated
            << " primarySent=" << numPrimarySent
            << " replicaSent=" << numReplicaSent
            << " passedThrough=" << numPassedThrough << endl;

    delete transportBinding;
    transportBinding = nullptr;
}
