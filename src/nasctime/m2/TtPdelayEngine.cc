//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtPdelayEngine.h"

#include <cinttypes>
#include <filesystem>
#include <numeric>

#include "inet/clock/common/ClockTimeScale.h"
#include "inet/common/DirectionTag_m.h"
#include "inet/common/MemoryInputStream.h"
#include "inet/common/MemoryOutputStream.h"
#include "inet/common/ProtocolTag_m.h"
#include "inet/common/Simsignals.h"
#include "inet/common/checksum/ChecksumType_m.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/linklayer/common/InterfaceTag_m.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"
#include "inet/linklayer/ieee8021q/Ieee8021qTagHeader_m.h"
#include "inet/networklayer/common/NetworkInterface.h"

#include "TtPdelayFlow.h"

namespace nasctime {

Define_Module(TtPdelayEngine);

static const MacAddress GPTP_ADDRESS("01:80:C2:00:00:0E");
static const b GPTP_PDELAY_LENGTH = B(54);

const char *TtPdelayEngine::stateName(State s)
{
    switch (s) {
        case IDLE: return "IDLE";
        case WAIT_RESP: return "WAIT_RESP";
        case WAIT_FU: return "WAIT_FU";
        case DONE: return "DONE";
        case FAULTED: return "FAULTED";
    }
    return "?";
}

static simtime_t toSim(clocktime_t t) { return CLOCKTIME_AS_SIMTIME(t); }
static clocktime_t toClock(simtime_t t) { return SIMTIME_AS_CLOCKTIME(t); }
static std::string raw(simtime_t t) { return t < SIMTIME_ZERO ? std::string() : std::to_string(t.raw()); }

TtPdelayEngine::~TtPdelayEngine()
{
    cancelAndDelete(sendEvent);
    cancelAndDelete(reqTimer);
    for (auto p : outbox)
        delete p;
}

void TtPdelayEngine::initialize()
{
    terminate = par("terminate");
    requester = par("requester");
    responder = par("responder");
    if ((requester || responder) && !terminate)
        throw cRuntimeError("requester/responder need terminate = true");
    domainNumber = par("domainNumber");
    portNumber = (uint16_t)par("portNumber").intValue();
    pdelayInterval = par("pdelayInterval");
    allowedLostResponses = par("allowedLostResponses");
    neighborPropDelayThresh = par("neighborPropDelayThresh");
    pairingTest = par("pairingTest").stdstringValue();
    timestampTest = par("timestampTest").stdstringValue();
    unitTest = par("unitTest").stdstringValue();
    formulaTest = par("formulaTest").stdstringValue();
    faultPolicyTest = par("faultPolicyTest").stdstringValue();
    // TEST ONLY knobs: only the documented values (negative controls, design section 9)
    auto allowed = [](const std::string& v, std::initializer_list<const char *> ok) {
        if (v.empty())
            return true;
        for (auto o : ok)
            if (v == o)
                return true;
        return false;
    };
    if (!allowed(pairingTest, {"previousRequest", "previousSeq"}) || !allowed(timestampTest, {"t4End", "t1t4End", "t3End"})
        || !allowed(unitTest, {"nsAsPs"}) || !allowed(formulaTest, {"noHalf", "noTurnaround"})
        || !allowed(faultPolicyTest, {"noTimeout", "acceptLast", "republishLate"}))
        throw cRuntimeError("Unknown TEST ONLY knob value");
    if (std::string(par("fcsMode").stringValue()) != "computed")
        throw cRuntimeError("Only fcsMode = \"computed\" is supported");
    if (!terminate)
        return;   // passive: classify and count only (gate G0)

    std::string ci = par("clockIdentity").stdstringValue();
    if (ci.empty())
        throw cRuntimeError("clockIdentity must be set explicitly (design decision 5)");
    clockIdentity = std::stoull(ci, nullptr, 0);
    interfaceModule = getParentModule()->getParentModule();
    auto networkInterface = check_and_cast<NetworkInterface *>(interfaceModule);
    interfaceId = networkInterface->getInterfaceId();
    transmitterModule = interfaceModule->findModuleByPath(".phyLayer.transmitter");
    receiverModule = interfaceModule->findModuleByPath(".phyLayer.receiver");
    if (!transmitterModule || !receiverModule)
        throw cRuntimeError("%s lacks phyLayer.transmitter/receiver", interfaceModule->getFullPath().c_str());
    interfaceModule->subscribe(receptionStartedSignal, this);
    interfaceModule->subscribe(receptionEndedSignal, this);
    interfaceModule->subscribe(transmissionStartedSignal, this);
    interfaceModule->subscribe(transmissionEndedSignal, this);
    txFlow = check_and_cast<TtPdelayFlow *>(getModuleByPath("^.tx"));
    sendEvent = new cMessage("send");
    meanLinkDelayVector.setName("meanLinkDelay");
    nrrVector.setName("neighborRateRatio");
    measuringVector.setName("measuring");
    std::string logFile = par("logFile").stdstringValue();
    if (!logFile.empty()) {
        std::string path = logFile + ".pdelay.csv";
        std::filesystem::path p(path);
        if (p.has_parent_path())
            std::filesystem::create_directories(p.parent_path());
        log.open(path, std::ios::out | std::ios::trunc);
        if (!log)
            throw cRuntimeError("Cannot open log file '%s'", path.c_str());
        // times in integer ps (raw simulation time); D in ps
        log << "event,t,msgType,seq,state,srcClock,srcPort,reqClock,reqPort,tA,tB,t1,t2,t3,t4,D,nrrNum,nrrDen,nrrQ63,note\n";
    }
    if (par("selfTest"))
        selfTest();
    if (requester) {
        seq = (uint16_t)par("initialSequenceId").intValue();
        reqTimer = new cMessage("pdelayReqTimer");
        scheduleAt(simTime() + par("pdelayInitialOffset").doubleValue(), reqTimer);
    }
}

// ---------------------------------------------------------------------------------------
// classification and frames

int TtPdelayEngine::classify(const Packet *packet, b& gptpOffset)
{
    b length = packet->getDataLength();
    if (length < B(14))
        return -1;
    const auto& mac = packet->peekDataAt<EthernetMacHeader>(b(0));
    if (mac->getDest() != GPTP_ADDRESS)
        return -1;
    b offset = B(14);
    int typeOrLength = mac->getTypeOrLength();
    if (typeOrLength == 0x8100) {
        if (length < B(18))
            return -1;
        const auto& tag = packet->peekDataAt<Ieee8021qTagEpdHeader>(offset);
        typeOrLength = tag->getTypeOrLength();
        offset += B(4);
    }
    if (typeOrLength != 0x88F7)
        return -1;
    gptpOffset = offset;
    if (length < offset + B(1))
        return -2;
    const auto& first = packet->peekDataAt<BytesChunk>(offset, B(1));
    return first->getByte(0) & 0x0F;
}

MacAddress TtPdelayEngine::ownMacAddress() const
{
    return check_and_cast<NetworkInterface *>(interfaceModule)->getMacAddress();
}

// The frame as INET's EthernetLayer would build it for a gPTP chunk sent on this port:
// EthernetMacHeader, payload, EthernetPadding to 60 B if needed, EthernetFcs (computed).
Packet *TtPdelayEngine::buildFrame(const char *name, const Ptr<GptpBase>& gptp) const
{
    auto packet = new Packet(name);
    packet->insertAtBack(gptp);
    auto mac = makeShared<EthernetMacHeader>();
    mac->setDest(GPTP_ADDRESS);
    mac->setSrc(ownMacAddress());
    mac->setTypeOrLength(0x88F7);
    packet->insertAtFront(mac);
    if (packet->getDataLength() < B(60)) {
        auto padding = makeShared<EthernetPadding>();
        padding->setChunkLength(B(60) - packet->getDataLength());
        packet->insertAtBack(padding);
    }
    auto fcs = makeShared<EthernetFcs>();
    fcs->setFcsMode(FCS_COMPUTED);
    fcs->setFcs((uint32_t)inet::computeChecksum(packet->peekDataAsBytes()->getBytes(), CHECKSUM_ETHERNET_FCS));
    packet->insertAtBack(fcs);
    packet->addTag<PacketProtocolTag>()->setProtocol(&Protocol::ethernetMac);
    packet->addTag<InterfaceReq>()->setInterfaceId(interfaceId);
    packet->addTag<DirectionTag>()->setDirection(DIRECTION_OUTBOUND);
    return packet;
}

// own frames leave in a separate event at the same simulation time (as INET's Gptp,
// whose sends are message deliveries)
void TtPdelayEngine::send(Packet *packet, int messageType, uint16_t sequenceId, const PortIdentity& requesting)
{
    TxRecord r;
    r.messageType = messageType;
    r.seq = sequenceId;
    r.requesting = requesting;
    pendingTx[packet->getTreeId()] = r;
    outbox.push_back(packet);
    if (!sendEvent->isScheduled())
        scheduleAt(simTime(), sendEvent);
}

void TtPdelayEngine::handleMessage(cMessage *msg)
{
    if (msg == sendEvent) {
        while (!outbox.empty()) {
            Packet *packet = outbox.front();
            outbox.pop_front();
            txFlow->inject(packet);
        }
    }
    else if (msg == reqTimer)
        requestTimer();
    else
        throw cRuntimeError("Unexpected message");
}

static const Packet *encapsulatedPacket(cObject *obj)
{
    if (auto packet = dynamic_cast<Packet *>(obj))
        return packet;
    auto signal = check_and_cast<cPacket *>(obj);
    return check_and_cast<Packet *>(signal->getEncapsulatedPacket());
}

void TtPdelayEngine::receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details)
{
    Enter_Method("receiveSignal");
    if (source == receiverModule) {
        const Packet *packet = encapsulatedPacket(obj);
        if (signalID == receptionStartedSignal) {
            rxStartTree = packet->getTreeId();
            rxStartTime = simTime();
        }
        else if (signalID == receptionEndedSignal) {
            rxEndTree = packet->getTreeId();
            rxEndTime = simTime();
        }
        return;
    }
    if (source != transmitterModule || (signalID != transmissionStartedSignal && signalID != transmissionEndedSignal))
        return;
    const Packet *packet = encapsulatedPacket(obj);
    auto it = pendingTx.find(packet->getTreeId());
    if (it == pendingTx.end())
        return;   // not an engine frame
    TxRecord& r = it->second;
    if (signalID == transmissionStartedSignal) {
        r.tTxStart = simTime();
        if (r.messageType == 2) {
            t1 = simTime();
            writeLog("tx", 2, r.seq, nullptr, nullptr, r.tTxStart, -1, "");
        }
    }
    else {
        r.tTxEnd = simTime();
        if (r.messageType == 2) {
            t1End = simTime();
            writeLog("txEnd", 2, r.seq, nullptr, nullptr, r.tTxStart, r.tTxEnd, "");
        }
        else if (r.messageType == 3) {
            // Pdelay_Resp fully sent: send the Pdelay_Resp_Follow_Up with its first-bit time
            // (as INET Gptp.cc:661-670)
            simtime_t t3own = timestampTest == "t3End" ? r.tTxEnd : r.tTxStart;   // TEST ONLY t3End
            writeLog("tx", 3, r.seq, nullptr, &r.requesting, r.tTxStart, r.tTxEnd, "");
            auto fu = makeShared<GptpPdelayRespFollowUp>();
            fu->setDomainNumber(domainNumber);
            PortIdentity own;
            own.clockIdentity = clockIdentity;
            own.portNumber = portNumber;
            fu->setSourcePortIdentity(own);
            fu->setRequestingPortIdentity(r.requesting);
            fu->setSequenceId(r.seq);
            fu->setResponseOriginTimestamp(toClock(t3own));
            numRespFollowUpSent++;
            send(buildFrame("TtPdelayRespFollowUp", fu), 10, r.seq, r.requesting);
        }
        else if (r.messageType == 10)
            writeLog("tx", 10, r.seq, nullptr, &r.requesting, r.tTxStart, r.tTxEnd, "");
        pendingTx.erase(it);
    }
}

// ---------------------------------------------------------------------------------------
// reception

bool TtPdelayEngine::offerReceived(Packet *packet)
{
    Enter_Method("offerReceived");
    b off;
    int type = classify(packet, off);
    if (type == -1 || (type >= 0 && !isPdelayType(type)))
        return false;                 // not Pdelay: Sync, Follow_Up, everything else pass
    if (!terminate) {
        if (type >= 0)
            numPassedPdelay[type]++;
        return false;                 // passive
    }
    take(packet);
    // the frame whose reception just ended (first-bit time from receptionStarted)
    if (rxEndTree != packet->getTreeId() || rxEndTime != simTime() || rxStartTree != packet->getTreeId())
        throw cRuntimeError("Pdelay frame at the slot (tree id %ld) is not the one whose reception just ended (tree id %ld/%ld)",
                packet->getTreeId(), rxStartTree, rxEndTree);
    simtime_t tRxStart = rxStartTime, tRxEnd = rxEndTime;
    if (type >= 0)
        numTerminated[type]++;
    Ptr<const GptpBase> msg;
    std::string error = type < 0 ? std::string("no gPTP header byte") : validate(packet, off, type, msg);
    if (!error.empty()) {
        numMalformed++;
        writeLog("malformed", type, -1, nullptr, nullptr, tRxStart, tRxEnd, error);
    }
    else if (type == 2) {
        if (responder)
            processRequest(check_and_cast<const GptpPdelayReq *>(msg.get()), tRxStart, tRxEnd);
        else
            writeLog("rxIgnored", 2, msg->getSequenceId(), &msg->getSourcePortIdentity(), nullptr, tRxStart, tRxEnd, "responder off");
    }
    else if (requester) {
        if (type == 3)
            processResponse(check_and_cast<const GptpPdelayResp *>(msg.get()), tRxStart, tRxEnd);
        else
            processResponseFollowUp(check_and_cast<const GptpPdelayRespFollowUp *>(msg.get()), tRxStart, tRxEnd);
    }
    else
        writeLog("rxIgnored", type, msg->getSequenceId(), &msg->getSourcePortIdentity(), nullptr, tRxStart, tRxEnd, "requester off");
    delete packet;
    return true;
}

// design 4.8: anything not exactly a 54-B Pdelay message of this domain is malformed
std::string TtPdelayEngine::validate(const Packet *packet, b off, int type, Ptr<const GptpBase>& out) const
{
    if (off != B(14))
        return "VLAN-tagged";
    b fcsLength = B(4);
    if (packet->getDataLength() < off + fcsLength + GPTP_PDELAY_LENGTH)
        return "shorter than 54 B";
    int flags = Chunk::PF_ALLOW_INCORRECT | Chunk::PF_ALLOW_INCOMPLETE | Chunk::PF_ALLOW_IMPROPERLY_REPRESENTED;
    Ptr<const GptpBase> msg;
    try {
        if (type == 2)
            msg = packet->peekDataAt<GptpPdelayReq>(off, GPTP_PDELAY_LENGTH, flags);
        else if (type == 3)
            msg = packet->peekDataAt<GptpPdelayResp>(off, GPTP_PDELAY_LENGTH, flags);
        else
            msg = packet->peekDataAt<GptpPdelayRespFollowUp>(off, GPTP_PDELAY_LENGTH, flags);
    }
    catch (std::exception& e) {
        return std::string("unreadable: ") + e.what();
    }
    if (msg == nullptr)
        return "unreadable";
    if (msg->isIncorrect() || msg->isIncomplete() || msg->isImproperlyRepresented())
        return "incorrect/incomplete chunk";
    if ((int)msg->getMessageType() != type)
        return "messageType mismatch";
    if (msg->getVersionPTP() != 2)
        return "versionPTP " + std::to_string(msg->getVersionPTP());
    if (msg->getMessageLengthField() != 54)
        return "messageLength " + std::to_string(msg->getMessageLengthField());
    if (msg->getDomainNumber() != domainNumber)
        return "domainNumber " + std::to_string(msg->getDomainNumber());
    out = msg;
    return "";
}

// ---------------------------------------------------------------------------------------
// responder (design 4.7)

void TtPdelayEngine::processRequest(const GptpPdelayReq *req, simtime_t tRxStart, simtime_t tRxEnd)
{
    const PortIdentity& src = req->getSourcePortIdentity();
    if (src.clockIdentity == clockIdentity && src.portNumber == portNumber) {
        numLoopback++;
        writeLog("loopback", 2, req->getSequenceId(), &src, nullptr, tRxStart, tRxEnd, "");
        return;
    }
    writeLog("rx", 2, req->getSequenceId(), &src, nullptr, tRxStart, tRxEnd, "");
    uint16_t answerSeq = req->getSequenceId();
    PortIdentity answerTo = src;
    if (pairingTest == "previousSeq") {          // TEST ONLY: answer with the previous request's identity
        bool have = havePrevReq;
        uint16_t ps = prevReqSeq;
        PortIdentity pp = prevReqSource;
        havePrevReq = true;
        prevReqSeq = req->getSequenceId();
        prevReqSource = src;
        if (!have) {
            writeLog("noPrevious", 2, req->getSequenceId(), &src, nullptr, tRxStart, tRxEnd, "TEST previousSeq: not answered");
            return;
        }
        answerSeq = ps;
        answerTo = pp;
    }
    auto resp = makeShared<GptpPdelayResp>();
    resp->setDomainNumber(domainNumber);
    PortIdentity own;
    own.clockIdentity = clockIdentity;
    own.portNumber = portNumber;
    resp->setSourcePortIdentity(own);
    resp->setRequestingPortIdentity(answerTo);
    resp->setSequenceId(answerSeq);
    resp->setRequestReceiptTimestamp(toClock(tRxStart));     // t2 = first bit of the request
    numReqAnswered++;
    numRespSent++;
    send(buildFrame("TtPdelayResp", resp), 3, answerSeq, answerTo);
}

// ---------------------------------------------------------------------------------------
// requester (design 4.5 state machine, 4.6 calculation)

void TtPdelayEngine::requestTimer()
{
    // close the exchange of the previous request
    if (!firstRequest) {
        if (state == WAIT_RESP || state == WAIT_FU) {
            if (faultPolicyTest != "noTimeout") {
                numLost++;
                consecutiveLost++;
            }
            writeLog("lost", 2, seq, nullptr, nullptr, -1, -1, faultPolicyTest == "noTimeout" ? "not counted (TEST noTimeout)" : "");
        }
        if (measuring && consecutiveLost > allowedLostResponses) {
            measuring = false;
            measuringVector.record(0);
        }
    }
    sendRequest();
    scheduleAt(simTime() + pdelayInterval, reqTimer);
}

void TtPdelayEngine::sendRequest()
{
    if (!firstRequest)
        seq = (uint16_t)(seq + 1);    // wraps 65535 -> 0
    firstRequest = false;
    prevT1 = t1;
    t1 = t1End = t2 = t3 = t4 = t4End = -1;
    state = WAIT_RESP;
    auto req = makeShared<GptpPdelayReq>();
    req->setDomainNumber(domainNumber);
    req->setCorrectionField(CLOCKTIME_ZERO);
    PortIdentity own;
    own.clockIdentity = clockIdentity;
    own.portNumber = portNumber;
    req->setSourcePortIdentity(own);
    req->setSequenceId(seq);
    numReqSent++;
    PortIdentity none;
    send(buildFrame("TtPdelayReq", req), 2, seq, none);
}

static bool samePort(const PortIdentity& a, const PortIdentity& b)
{
    return a.clockIdentity == b.clockIdentity && a.portNumber == b.portNumber;
}

void TtPdelayEngine::processResponse(const GptpPdelayResp *resp, simtime_t tRxStart, simtime_t tRxEnd)
{
    const PortIdentity& rp = resp->getRequestingPortIdentity();
    const PortIdentity& src = resp->getSourcePortIdentity();
    uint16_t s = resp->getSequenceId();
    PortIdentity own;
    own.clockIdentity = clockIdentity;
    own.portNumber = portNumber;
    if (!samePort(rp, own)) {
        numNotForUs++;
        writeLog("notForUs", 3, s, &src, &rp, tRxStart, tRxEnd, "");
        return;
    }
    if (state == IDLE || s != seq) {
        numStaleSeq++;
        writeLog("staleSeq", 3, s, &src, &rp, tRxStart, tRxEnd, "");
        return;
    }
    switch (state) {
        case WAIT_RESP:
            t2 = toSim(resp->getRequestReceiptTimestamp());
            t4 = tRxStart;
            t4End = tRxEnd;
            if (haveResponder && !samePort(src, lastResponder))
                numResponderChanged++;
            lastResponder = src;
            haveResponder = true;
            state = WAIT_FU;
            writeLog("rx", 3, s, &src, &rp, tRxStart, tRxEnd, "");
            break;
        case WAIT_FU:
            if (faultPolicyTest == "acceptLast") {    // TEST ONLY: wrong policy
                t2 = toSim(resp->getRequestReceiptTimestamp());
                t4 = tRxStart;
                t4End = tRxEnd;
                writeLog("rx", 3, s, &src, &rp, tRxStart, tRxEnd, "duplicate accepted (TEST acceptLast)");
            }
            else {
                numMultipleResp++;
                state = FAULTED;
                writeLog("multipleResp", 3, s, &src, &rp, tRxStart, tRxEnd, "exchange discarded");
            }
            break;
        case DONE:
            if (faultPolicyTest == "republishLate") {  // TEST ONLY: wrong policy
                t2 = toSim(resp->getRequestReceiptTimestamp());
                t4 = tRxStart;
                t4End = tRxEnd;
                publish(true, "late duplicate re-published (TEST republishLate)");
            }
            else {
                numLateDuplicateResp++;
                writeLog("lateDuplicateResp", 3, s, &src, &rp, tRxStart, tRxEnd, "published value unchanged");
            }
            break;
        case FAULTED:
            numLateAfterFault++;
            writeLog("lateAfterFault", 3, s, &src, &rp, tRxStart, tRxEnd, "");
            break;
        default:
            break;
    }
}

void TtPdelayEngine::processResponseFollowUp(const GptpPdelayRespFollowUp *fu, simtime_t tRxStart, simtime_t tRxEnd)
{
    const PortIdentity& rp = fu->getRequestingPortIdentity();
    const PortIdentity& src = fu->getSourcePortIdentity();
    uint16_t s = fu->getSequenceId();
    PortIdentity own;
    own.clockIdentity = clockIdentity;
    own.portNumber = portNumber;
    if (!samePort(rp, own)) {
        numNotForUs++;
        writeLog("notForUs", 10, s, &src, &rp, tRxStart, tRxEnd, "");
        return;
    }
    if (state == IDLE || s != seq) {
        numStaleSeq++;
        writeLog("staleSeq", 10, s, &src, &rp, tRxStart, tRxEnd, "");
        return;
    }
    switch (state) {
        case WAIT_RESP:
            numOrphanFollowUp++;
            writeLog("orphanFollowUp", 10, s, &src, &rp, tRxStart, tRxEnd, "");
            break;
        case WAIT_FU:
            t3 = toSim(fu->getResponseOriginTimestamp());
            state = DONE;
            writeLog("rx", 10, s, &src, &rp, tRxStart, tRxEnd, "");
            publish(false, "");
            break;
        case DONE:
            numLateDuplicateFU++;
            writeLog("lateDuplicateFU", 10, s, &src, &rp, tRxStart, tRxEnd, "published value unchanged");
            break;
        case FAULTED:
            numLateAfterFault++;
            writeLog("lateAfterFault", 10, s, &src, &rp, tRxStart, tRxEnd, "");
            break;
        default:
            break;
    }
}

// D = (nRR * (t4 - t1) - (t3 - t2)) / 2 (INET Gptp.cc:476 arithmetic: ClockTimeScale
// fixed point, C++ truncating division); nRR = (t3 - t3prev) / (t4 - t4prev) from the
// previous completed exchange (INET Gptp.cc:439-458), 1 until then.
void TtPdelayEngine::publish(bool republish, const char *note)
{
    simtime_t a1 = t1, a2 = t2, a3 = t3, a4 = t4;
    if (timestampTest == "t4End")                // TEST ONLY
        a4 = t4End;
    else if (timestampTest == "t1t4End") {       // TEST ONLY
        a1 = t1End;
        a4 = t4End;
    }
    if (pairingTest == "previousRequest") {      // TEST ONLY
        if (prevT1 < SIMTIME_ZERO) {
            writeLog("noPrevious", 10, seq, nullptr, nullptr, -1, -1, "TEST previousRequest: no earlier request");
            return;
        }
        a1 = prevT1;
    }
    if (unitTest == "nsAsPs") {                  // TEST ONLY: wire ns numbers taken as ps
        a2 = SimTime::fromRaw(t2.raw() / 1000);
        a3 = SimTime::fromRaw(t3.raw() / 1000);
    }
    ClockTimeScale nrr;
    int64_t num = 1, den = 1;
    if (havePrevExchange) {
        num = (t3 - prevT3).raw();
        den = (t4 - prevT4).raw();
        nrr = ClockTimeScale::fromRatio(toClock(t3 - prevT3), toClock(t4 - prevT4));
        int64_t g = std::gcd(num, den);
        if (g > 1) {
            num /= g;
            den /= g;
        }
    }
    clocktime_t rt = nrr * toClock(a4 - a1);
    clocktime_t turnaround = toClock(a3 - a2);
    clocktime_t d;
    if (formulaTest == "noHalf")                 // TEST ONLY
        d = rt - turnaround;
    else if (formulaTest == "noTurnaround")      // TEST ONLY
        d = rt / 2;
    else
        d = (rt - turnaround) / 2;
    simtime_t D = toSim(d);
    if (!republish) {
        havePrevExchange = true;
        prevT3 = t3;
        prevT4 = t4;
        numPublished++;
    }
    else
        numRepublished++;
    consecutiveLost = 0;
    bool m = D >= SIMTIME_ZERO && D <= neighborPropDelayThresh;
    if (m != measuring) {
        measuring = m;
        measuringVector.record(m ? 1 : 0);
    }
    meanLinkDelayVector.record(D);
    nrrVector.record(nrr.toDouble());
    if (log.is_open())
        log << (republish ? "republish" : "measure") << ',' << simTime().raw() << ",10," << seq << ',' << stateName(state)
            << ",,,,,,," << a1.raw() << ',' << a2.raw() << ',' << a3.raw() << ',' << a4.raw() << ',' << D.raw() << ',' << num << ','
            << den << ',' << nrr.raw() << ',' << note << '\n';
}

// ---------------------------------------------------------------------------------------

void TtPdelayEngine::writeLog(const char *event, int messageType, long seqId, const PortIdentity *source,
                              const PortIdentity *requesting, simtime_t tA, simtime_t tB, const std::string& note)
{
    if (!log.is_open())
        return;
    char buf[64];
    log << event << ',' << simTime().raw() << ',' << messageType << ',';
    if (seqId >= 0)
        log << seqId;
    log << ',' << stateName(state) << ',';
    if (source) {
        snprintf(buf, sizeof(buf), "0x%016" PRIx64, source->clockIdentity);
        log << buf << ',' << source->portNumber;
    }
    else
        log << ',';
    log << ',';
    if (requesting) {
        snprintf(buf, sizeof(buf), "0x%016" PRIx64, requesting->clockIdentity);
        log << buf << ',' << requesting->portNumber;
    }
    else
        log << ',';
    log << ',' << raw(tA) << ',' << raw(tB) << ",,,,,,,,," << note << '\n';
}

// Self-test (design 3.3): one frame of each type, round trip through INET's own
// serializer, lengths, field values, and the FCS against an independent CRC-32.
static uint32_t crc32Independent(const std::vector<uint8_t>& bytes)
{
    uint32_t crc = 0xFFFFFFFFu;
    for (uint8_t byte : bytes) {
        crc ^= byte;
        for (int k = 0; k < 8; k++)
            crc = (crc >> 1) ^ (0xEDB88320u & (0u - (crc & 1u)));
    }
    return ~crc;
}

void TtPdelayEngine::selfTest()
{
    PortIdentity own, other;
    own.clockIdentity = clockIdentity;
    own.portNumber = portNumber;
    other.clockIdentity = 0x0123456789abcdefULL;
    other.portNumber = 7;
    std::vector<Ptr<GptpBase>> msgs;
    auto req = makeShared<GptpPdelayReq>();
    req->setDomainNumber(domainNumber);
    req->setSourcePortIdentity(own);
    req->setSequenceId(65535);
    msgs.push_back(req);
    auto resp = makeShared<GptpPdelayResp>();
    resp->setDomainNumber(domainNumber);
    resp->setSourcePortIdentity(own);
    resp->setRequestingPortIdentity(other);
    resp->setSequenceId(12345);
    resp->setRequestReceiptTimestamp(toClock(SimTime::fromRaw(1234567890123LL)));
    msgs.push_back(resp);
    auto fu = makeShared<GptpPdelayRespFollowUp>();
    fu->setDomainNumber(domainNumber);
    fu->setSourcePortIdentity(own);
    fu->setRequestingPortIdentity(other);
    fu->setSequenceId(12345);
    fu->setResponseOriginTimestamp(toClock(SimTime::fromRaw(1234567890123000LL)));
    msgs.push_back(fu);
    for (auto& m : msgs) {
        Packet *packet = buildFrame("selfTest", m);
        auto bytes = packet->peekDataAsBytes()->getBytes();
        std::vector<uint8_t> data(bytes.begin(), bytes.end() - 4);
        uint32_t crc = crc32Independent(data);
        // the FCS is transmitted least-significant byte first
        uint32_t wire = (uint32_t)bytes[bytes.size() - 1] << 24 | (uint32_t)bytes[bytes.size() - 2] << 16 |
                        (uint32_t)bytes[bytes.size() - 3] << 8 | bytes[bytes.size() - 4];
        if (bytes.size() != 72 || wire != crc)
            throw cRuntimeError("self-test: frame of %zu B, FCS 0x%08x vs independent CRC-32 0x%08x", bytes.size(), wire, crc);
        b off;
        int type = classify(packet, off);
        Ptr<const GptpBase> back;
        std::string error = validate(packet, off, type, back);
        if (type != (int)m->getMessageType() || !error.empty())
            throw cRuntimeError("self-test: classify/validate: type %d, %s", type, error.c_str());
        // through INET's serializer
        MemoryOutputStream out;
        Chunk::serialize(out, m);
        if (out.getLength() != GPTP_PDELAY_LENGTH)
            throw cRuntimeError("self-test: serialized gPTP length %s", out.getLength().str().c_str());
        MemoryInputStream in(out.getData());
        const GptpBase& mref = *m;
        auto d = staticPtrCast<const GptpBase>(Chunk::deserialize(in, typeid(mref)));
        if (d->getSequenceId() != m->getSequenceId() || d->getSourcePortIdentity().clockIdentity != own.clockIdentity
            || d->getSourcePortIdentity().portNumber != own.portNumber || d->getDomainNumber() != m->getDomainNumber()
            || d->getVersionPTP() != 2 || d->getMessageLengthField() != 54)
            throw cRuntimeError("self-test: serializer round trip differs");
        if (auto r = dynamicPtrCast<const GptpPdelayResp>(d))
            if (r->getRequestReceiptTimestamp() != toClock(SimTime::fromRaw(1234567890000LL))   // wire: whole ns (truncated)
                || r->getRequestingPortIdentity().clockIdentity != other.clockIdentity)
                throw cRuntimeError("self-test: Pdelay_Resp round trip differs");
        delete packet;
    }
    selfTestPassed = true;
}

void TtPdelayEngine::finish()
{
    recordScalar("passedPdelayReq", numPassedPdelay[2]);
    recordScalar("passedPdelayResp", numPassedPdelay[3]);
    recordScalar("passedPdelayRespFollowUp", numPassedPdelay[10]);
    if (!terminate)
        return;
    recordScalar("terminatedPdelayReq", numTerminated[2]);
    recordScalar("terminatedPdelayResp", numTerminated[3]);
    recordScalar("terminatedPdelayRespFollowUp", numTerminated[10]);
    recordScalar("malformed", numMalformed);
    recordScalar("loopback", numLoopback);
    recordScalar("reqAnswered", numReqAnswered);
    recordScalar("respSent", numRespSent);
    recordScalar("respFollowUpSent", numRespFollowUpSent);
    recordScalar("reqSent", numReqSent);
    recordScalar("published", numPublished);
    recordScalar("republished", numRepublished);
    recordScalar("lost", numLost);
    recordScalar("multipleResp", numMultipleResp);
    recordScalar("orphanFollowUp", numOrphanFollowUp);
    recordScalar("staleSeq", numStaleSeq);
    recordScalar("notForUs", numNotForUs);
    recordScalar("lateDuplicateResp", numLateDuplicateResp);
    recordScalar("lateDuplicateFU", numLateDuplicateFU);
    recordScalar("lateAfterFault", numLateAfterFault);
    recordScalar("responderChanged", numResponderChanged);
    recordScalar("selfTestPassed", selfTestPassed ? 1 : 0);
    recordScalar("pendingAtEnd", (double)(outbox.size() + pendingTx.size()));
}

} // namespace nasctime
