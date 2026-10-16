//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtSyncIngress.h"

#include <cinttypes>
#include <filesystem>
#include <set>

#include "inet/common/Simsignals.h"
#include "inet/common/checksum/ChecksumType_m.h"
#include "inet/common/packet/chunk/BytesChunk.h"
#include "inet/linklayer/ethernet/common/EthernetMacHeader_m.h"

#include "TtPdelayEngine.h"

namespace nasctime {

Define_Module(TtSyncIngress);

using namespace gptpframe;

static std::string raw(simtime_t t) { return t < SIMTIME_ZERO ? std::string() : std::to_string(t.raw()); }
static simtime_t toSim(clocktime_t t) { return CLOCKTIME_AS_SIMTIME(t); }
static clocktime_t toClock(simtime_t t) { return SIMTIME_AS_CLOCKTIME(t); }

const char *TtSyncIngress::stateName(State s)
{
    switch (s) {
        case IDLE: return "IDLE";
        case WAIT_FU: return "WAIT_FU";
        case AMBIGUOUS: return "AMBIGUOUS";
    }
    return "?";
}

void TtSyncIngress::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage != INITSTAGE_LOCAL)
        return;
    enabled = par("enabled");
    ttId = par("ttId");
    domainNumber = par("domainNumber");
    selfCheck = par("selfCheck");
    correctionTest = par("correctionTest").stdstringValue();
    fixedLinkDelay = par("fixedLinkDelay");
    static const std::set<std::string> known = {"", "noLinkDelay", "lupTwice", "rr", "noFcs", "tsiEnd", "syncCf"};
    if (!known.count(correctionTest))
        throw cRuntimeError("Unknown TEST ONLY correctionTest '%s'", correctionTest.c_str());
    if (!enabled)
        return;   // passive: classify and count only (gate G0)
    if (ttId < 0)
        throw cRuntimeError("ttId must be set");
    engine = check_and_cast<TtPdelayEngine *>(getModuleByPath(par("engineModule").stringValue()));
    interfaceModule = getParentModule()->getParentModule();
    receiverModule = interfaceModule->findModuleByPath(".phyLayer.receiver");
    if (!receiverModule)
        throw cRuntimeError("%s lacks phyLayer.receiver", interfaceModule->getFullPath().c_str());
    interfaceModule->subscribe(receptionStartedSignal, this);
    interfaceModule->subscribe(receptionEndedSignal, this);
    std::string logFile = par("logFile").stdstringValue();
    if (!logFile.empty()) {
        std::string path = logFile + ".sync.csv";
        std::filesystem::path p(path);
        if (p.has_parent_path())
            std::filesystem::create_directories(p.parent_path());
        log.open(path, std::ios::out | std::ios::trunc);
        if (!log)
            throw cRuntimeError("Cannot open log file '%s'", path.c_str());
        // times in integer ps (raw simulation time)
        log << "event,t,msgType,domain,seq,srcClock,srcPort,state,treeId,syncFrameId,fuFrameId,TSi,Lup,cfIn,cfOut,rrIn,rrOut,note\n";
    }
    if (par("selfTest")) {
        gptpframe::selfTest(domainNumber);
        selfTestPassed = true;
    }
}

cGate *TtSyncIngress::getRegistrationForwardingGate(cGate *gate)
{
    if (gate == outputGate)
        return inputGate;
    else if (gate == inputGate)
        return outputGate;
    else
        throw cRuntimeError("Unknown gate");
}

static const Packet *encapsulatedPacket(cObject *obj)
{
    if (auto packet = dynamic_cast<Packet *>(obj))
        return packet;
    auto signal = check_and_cast<cPacket *>(obj);
    return check_and_cast<Packet *>(signal->getEncapsulatedPacket());
}

void TtSyncIngress::receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details)
{
    Enter_Method("receiveSignal");
    if (source != receiverModule)
        return;
    const Packet *packet = encapsulatedPacket(obj);
    if (signalID == receptionStartedSignal) {
        rxStartTree = packet->getTreeId();
        rxStartTime = simTime();
    }
    else if (signalID == receptionEndedSignal) {
        rxEndTree = packet->getTreeId();
        rxEndTime = simTime();
    }
}

void TtSyncIngress::pushPacket(Packet *packet, const cGate *gate)
{
    Enter_Method("pushPacket");
    take(packet);
    if (process(packet))
        pushOrSendPacket(packet, outputGate, consumer);
}

bool TtSyncIngress::process(Packet *packet)
{
    b off;
    int type = messageType(packet, off);
    if (type != 0 && type != 8)
        return true;
    if (type == 0)
        numSyncSeen++;
    else
        numFollowUpSeen++;
    if (!enabled)
        return true;
    if (type == 0) {
        if (rxEndTree != packet->getTreeId() || rxEndTime != simTime() || rxStartTree != packet->getTreeId())
            throw cRuntimeError("Sync at the slot (tree id %ld) is not the frame whose reception just ended (%ld/%ld)", packet->getTreeId(),
                    rxStartTree, rxEndTree);
        processSync(packet, off, correctionTest == "tsiEnd" ? rxEndTime : rxStartTime);   // TEST ONLY tsiEnd
        return true;
    }
    return processFollowUp(packet);
}

void TtSyncIngress::processSync(Packet *packet, b off, simtime_t tsi)
{
    SyncFrame s = parseSync(packet, off);
    if (s.key.domain != domainNumber) {
        numOtherDomain++;
        writeLog("otherDomain", 0, s.key, packet->getTreeId(), s.frameId, 0, tsi, -1, -1, -1, 0, 0, "passed unchanged");
        return;
    }
    if (!s.error.empty()) {
        numMalformedSync++;
        writeLog("malformedSync", 0, s.key, packet->getTreeId(), s.frameId, 0, tsi, -1, -1, -1, 0, 0, s.error);
        return;
    }
    numSync++;
    std::string note;
    if (state == IDLE)
        state = WAIT_FU;
    else if (s.key == waitKey) {
        numDuplicateSync++;
        state = AMBIGUOUS;
        note = "duplicateSync";
    }
    else {
        numSyncWithoutFU++;
        state = WAIT_FU;
        note = "syncWithoutFU " + waitKey.str();
    }
    if (state == WAIT_FU) {
        waitKey = s.key;
        waitTsi = tsi;
        waitSyncFrameId = s.frameId;
    }
    if (correctionTest == "syncCf") {   // TEST ONLY: Lup also written into the Sync (two-step violation, N11)
        auto st = engine->linkDelayState();
        if (st.valid)
            rewriteSyncCorrection(packet, off, toClock(st.meanLinkDelay));
    }
    writeLog("sync", 0, s.key, packet->getTreeId(), s.frameId, 0, tsi, -1, -1, -1, 0, 0, note);
}

void TtSyncIngress::tagInvalid(Packet *packet, const FollowUpFrame& f, const char *reason)
{
    numInvalid++;
    TtSyncIngressTag tag;
    tag.setValid(false);
    tag.setReason(reason);
    tag.setTtId(ttId);
    tag.setDomainNumber(f.key.domain);
    tag.setSequenceId(f.key.seq);
    tag.setSourceClockIdentity(f.key.clock);
    tag.setSourcePortNumber(f.key.port);
    tag.setFollowUpFrameId(f.frameId);
    tag.setRateRatioOut(f.fu->getFollowUpInformationTLV().getRateRatio());
    tag.setCorrectionIn(toSim(f.fu->getCorrectionField()));
    tag.setCorrectionOut(toSim(f.fu->getCorrectionField()));
    Rewrite r;
    r.correctionField = f.fu->getCorrectionField();
    r.addTag = &tag;
    r.recomputeFcs = correctionTest != "noFcs";
    r.selfCheck = selfCheck;
    std::string e = rewriteFollowUp(packet, f, r);
    if (!e.empty())
        throw cRuntimeError("Follow_Up rewrite self-check failed (INVALID): %s", e.c_str());
    writeLog("invalid", 8, f.key, packet->getTreeId(), 0, f.frameId, -1, -1, tag.getCorrectionIn(), tag.getCorrectionOut(),
            tag.getRateRatioOut(), tag.getRateRatioOut(), reason);
}

bool TtSyncIngress::processFollowUp(Packet *packet)
{
    FollowUpFrame f = parseFollowUp(packet, domainNumber);
    if (f.unsupported.empty() && f.key.domain != domainNumber) {
        numOtherDomain++;
        writeLog("otherDomain", 8, f.key, packet->getTreeId(), 0, f.frameId, -1, -1, -1, -1, 0, 0, "passed unchanged");
        return true;
    }
    if (f.isClassM()) {
        // class M: safe tagging not demonstrated; discarded here (design 6.0); state unchanged
        if (!f.unsupported.empty())
            numUnsupportedRepresentation++;
        else
            numMalformedFU++;
        writeLog(f.unsupported.empty() ? "malformedFU" : "unsupportedRepresentation", 8, f.key, packet->getTreeId(), 0, f.frameId, -1, -1,
                -1, -1, 0, 0, f.unsupported + f.malformed);
        delete packet;
        return false;
    }
    if (state == IDLE) {
        if (f.key == lastKey) {
            numDuplicateFU++;
            tagInvalid(packet, f, "duplicateFU");
        }
        else {
            numOrphanFU++;
            tagInvalid(packet, f, "orphanFU");
        }
        return true;
    }
    if (f.key != waitKey) {
        numFuMismatch++;
        tagInvalid(packet, f, "fuMismatch");   // state unchanged
        return true;
    }
    if (state == AMBIGUOUS) {
        numAmbiguousSync++;
        state = IDLE;
        lastKey = f.key;
        tagInvalid(packet, f, "ambiguousSync");
        return true;
    }
    // WAIT_FU(k), FU k
    simtime_t lup = -1;
    ClockTimeScale nrr;
    if (fixedLinkDelay >= SIMTIME_ZERO)            // TEST ONLY (N14)
        lup = fixedLinkDelay;
    else {
        auto st = engine->linkDelayState();
        if (st.valid && st.measuring) {
            lup = st.meanLinkDelay;
            nrr = st.neighborRateRatio;
        }
    }
    state = IDLE;
    lastKey = f.key;
    if (lup < SIMTIME_ZERO) {
        numNoLinkDelay++;
        tagInvalid(packet, f, "noLinkDelay");
        return true;
    }
    clocktime_t cfIn = f.fu->getCorrectionField();
    double rrIn = f.fu->getFollowUpInformationTLV().getRateRatio();
    double rrUse = correctionTest == "rr" ? 1.0001 : rrIn;   // TEST ONLY (N9)
    clocktime_t add = scale(rrUse, toClock(lup));
    if (correctionTest == "noLinkDelay")               // TEST ONLY (N1)
        add = CLOCKTIME_ZERO;
    else if (correctionTest == "lupTwice")             // TEST ONLY (N2)
        add = add + add;
    clocktime_t cf1 = cfIn + add;
    double rrOut = multiplyRateRatio(rrUse, nrr);
    TtSyncIngressTag tag;
    tag.setValid(true);
    tag.setTtId(ttId);
    tag.setSyncIngressTime(waitTsi);
    tag.setDomainNumber(f.key.domain);
    tag.setSequenceId(f.key.seq);
    tag.setSourceClockIdentity(f.key.clock);
    tag.setSourcePortNumber(f.key.port);
    tag.setSyncFrameId(waitSyncFrameId);
    tag.setFollowUpFrameId(f.frameId);
    tag.setLinkDelay(lup);
    tag.setRateRatioOut(rrOut);
    tag.setCorrectionIn(toSim(cfIn));
    tag.setCorrectionOut(toSim(cf1));
    Rewrite r;
    r.correctionField = cf1;
    r.setRateRatio = true;
    r.rateRatio = rrOut;
    r.addTag = &tag;
    r.recomputeFcs = correctionTest != "noFcs";
    r.selfCheck = selfCheck;
    std::string e = rewriteFollowUp(packet, f, r);
    if (!e.empty())
        throw cRuntimeError("Follow_Up rewrite self-check failed: %s", e.c_str());
    numCorrected++;
    writeLog("corrected", 8, f.key, packet->getTreeId(), waitSyncFrameId, f.frameId, waitTsi, lup, toSim(cfIn), toSim(cf1), rrIn, rrOut,
            correctionTest.empty() ? "" : "TEST " + correctionTest);
    return true;
}

// TEST ONLY (N11): correctionField of the Sync set to cf (FCS recomputed)
void TtSyncIngress::rewriteSyncCorrection(Packet *packet, b off, clocktime_t cf)
{
    std::vector<Leaf> leaves;
    collectLeaves(packet->peekData(), b(0), leaves);
    for (const auto& l : leaves) {
        if (l.offset != off)
            continue;
        auto sync = dynamicPtrCast<const GptpSync>(l.chunk);
        if (!sync)
            return;
        auto copy = staticPtrCast<GptpSync>(sync->dupShared());
        copy->setCorrectionField(cf);
        copy->markImmutable();
        packet->replaceDataAt(copy, off, copy->getChunkLength());
        b fcsOffset = packet->getDataLength() - B(4);
        auto oldFcs = packet->peekDataAt<EthernetFcs>(fcsOffset);
        auto fcs = makeShared<EthernetFcs>();
        fcs->setFcsMode(oldFcs->getFcsMode());
        fcs->setFcs((uint32_t)inet::computeChecksum(packet->peekDataAt<BytesChunk>(b(0), fcsOffset)->getBytes(), CHECKSUM_ETHERNET_FCS));
        fcs->markImmutable();
        packet->replaceDataAt(fcs, fcsOffset, B(4));
        return;
    }
}

void TtSyncIngress::writeLog(const char *event, int msgType, const Key& key, long treeId, uint64_t syncFrameId, uint64_t fuFrameId, simtime_t tsi,
                             simtime_t lup, simtime_t cfIn, simtime_t cfOut, double rrIn, double rrOut, const std::string& note)
{
    if (!log.is_open())
        return;
    char buf[48];
    snprintf(buf, sizeof(buf), "0x%016" PRIx64, key.clock);
    log << event << ',' << simTime().raw() << ',' << msgType << ',' << key.domain << ',' << key.seq << ',' << buf << ',' << key.port << ','
        << stateName(state) << ',' << treeId << ',' << syncFrameId << ',' << fuFrameId << ',' << raw(tsi) << ',' << raw(lup) << ','
        << raw(cfIn) << ',' << raw(cfOut) << ',';
    snprintf(buf, sizeof(buf), "%.17g,%.17g", rrIn, rrOut);
    log << (cfIn < SIMTIME_ZERO ? std::string(",") : std::string(buf)) << ',' << note << '\n';
}

void TtSyncIngress::pushPacketStart(Packet *packet, const cGate *gate, bps datarate)
{
    throw cRuntimeError("Packet streaming through TtPtpPort is not supported (packet %s)", packet->getName());
}

void TtSyncIngress::pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength)
{
    throw cRuntimeError("Packet streaming through TtPtpPort is not supported (packet %s)", packet->getName());
}

void TtSyncIngress::pushPacketEnd(Packet *packet, const cGate *gate)
{
    throw cRuntimeError("Packet streaming through TtPtpPort is not supported (packet %s)", packet->getName());
}

void TtSyncIngress::finish()
{
    recordScalar("syncSeen", numSyncSeen);
    recordScalar("followUpSeen", numFollowUpSeen);
    if (!enabled)
        return;
    recordScalar("sync", numSync);
    recordScalar("corrected", numCorrected);
    recordScalar("invalid", numInvalid);
    recordScalar("syncWithoutFU", numSyncWithoutFU);
    recordScalar("duplicateSync", numDuplicateSync);
    recordScalar("ambiguousSync", numAmbiguousSync);
    recordScalar("fuMismatch", numFuMismatch);
    recordScalar("noLinkDelay", numNoLinkDelay);
    recordScalar("duplicateFU", numDuplicateFU);
    recordScalar("orphanFU", numOrphanFU);
    recordScalar("malformedFU", numMalformedFU);
    recordScalar("unsupportedRepresentation", numUnsupportedRepresentation);
    recordScalar("malformedSync", numMalformedSync);
    recordScalar("otherDomain", numOtherDomain);
    recordScalar("selfTestPassed", selfTestPassed ? 1 : 0);
}

} // namespace nasctime
