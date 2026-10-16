//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtSyncEgress.h"

#include <cinttypes>
#include <filesystem>
#include <set>

#include "inet/common/Simsignals.h"

namespace nasctime {

Define_Module(TtSyncEgress);

using namespace gptpframe;

static std::string raw(simtime_t t) { return t < SIMTIME_ZERO ? std::string() : std::to_string(t.raw()); }
static simtime_t toSim(clocktime_t t) { return CLOCKTIME_AS_SIMTIME(t); }
static clocktime_t toClock(simtime_t t) { return SIMTIME_AS_CLOCKTIME(t); }

TtSyncEgress::~TtSyncEgress()
{
    cancelAndDelete(releaseEvent);
    cancelAndDelete(holdTimer);
    for (auto p : held)
        delete p;
}

void TtSyncEgress::initialize(int stage)
{
    PacketFlowBase::initialize(stage);
    if (stage != INITSTAGE_LOCAL)
        return;
    std::string m = par("mode").stdstringValue();
    if (m == "off")
        mode = OFF;
    else if (m == "audit")
        mode = AUDIT;
    else if (m == "correct")
        mode = CORRECT;
    else
        throw cRuntimeError("Unknown mode '%s'", m.c_str());
    ttId = par("ttId");
    domainNumber = par("domainNumber");
    holdTimeout = par("holdTimeout");
    crossCheckFrameId = par("crossCheckFrameId");
    selfCheck = par("selfCheck");
    egressTest = par("egressTest").stdstringValue();
    dropSyncSeq = par("dropSyncSeq");
    static const std::set<std::string> known = {"", "tseEnd", "tseSlot", "prevSync", "noFcs", "noStrip", "forwardInvalid", "noHold"};
    if (!known.count(egressTest))
        throw cRuntimeError("Unknown TEST ONLY egressTest '%s'", egressTest.c_str());
    if (mode == OFF)
        return;   // passive: classify and count only (gate G0)
    if (ttId < 0)
        throw cRuntimeError("ttId must be set");
    interfaceModule = getParentModule()->getParentModule();
    transmitterModule = interfaceModule->findModuleByPath(".phyLayer.transmitter");
    if (!transmitterModule)
        throw cRuntimeError("%s lacks phyLayer.transmitter", interfaceModule->getFullPath().c_str());
    interfaceModule->subscribe(transmissionStartedSignal, this);
    interfaceModule->subscribe(transmissionEndedSignal, this);
    releaseEvent = new cMessage("holdRelease");
    holdTimer = new cMessage("holdTimeout");
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
        log << "event,t,msgType,domain,seq,srcClock,srcPort,treeId,syncFrameId,fuFrameId,tagValid,tagReason,tagTtId,tagSeq,TSi,Lup,rrOut,"
               "cfIn,TSe,Res,cfOut,holding,note\n";
    }
}

cGate *TtSyncEgress::getRegistrationForwardingGate(cGate *gate)
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

void TtSyncEgress::receiveSignal(cComponent *source, simsignal_t signalID, cObject *obj, cObject *details)
{
    Enter_Method("receiveSignal");
    if (source != transmitterModule)
        return;
    long tree = encapsulatedPacket(obj)->getTreeId();
    if (signalID == transmissionEndedSignal) {
        if (egressTest == "tseEnd" && tree == lastTx.treeId)   // TEST ONLY (N3)
            lastTx.tse = simTime();
        return;
    }
    if (signalID != transmissionStartedSignal)
        return;
    auto it = pending.begin();
    while (it != pending.end() && it->first != tree)
        ++it;
    if (it == pending.end())
        return;
    TxSync t;
    t.key = it->second.key;
    t.frameId = it->second.frameId;
    t.treeId = tree;
    t.tse = egressTest == "tseSlot" ? it->second.slotTime : simTime();   // TEST ONLY (N6)
    t.ambiguous = lastTx.key.isSet() && lastTx.key == t.key;
    lastTx = t;
    recentTx.push_back(t.key);
    if (recentTx.size() > 16)
        recentTx.pop_front();
    pending.erase(it);
    numSyncTransmitted++;
    writeLog("syncTx", 0, t.key, tree, t.frameId, 0, nullptr, simTime(), -1, -1, t.ambiguous ? "ambiguous" : "");
    if (holding && heldKey == t.key && !releaseEvent->isScheduled())
        scheduleAt(simTime(), releaseEvent);   // zero-delay release, behind the Sync in the MAC FIFO
}

void TtSyncEgress::pushPacket(Packet *packet, const cGate *gate)
{
    Enter_Method("pushPacket");
    take(packet);
    if (mode == OFF) {
        b off;
        int type = messageType(packet, off);
        if (type == 0)
            numSyncSeen++;
        else if (type == 8)
            numFollowUpSeen++;
        forward(packet);
        return;
    }
    deliver(packet);
}

void TtSyncEgress::forward(Packet *packet)
{
    pushOrSendPacket(packet, outputGate, consumer);
}

void TtSyncEgress::deliver(Packet *packet)
{
    if (holding) {
        held.push_back(packet);
        numHeldFrames++;
        b off;
        int type = messageType(packet, off);
        Key none;
        writeLog("held", type, none, packet->getTreeId(), 0, 0, nullptr, -1, -1, -1, "");
        return;
    }
    b off;
    int type = messageType(packet, off);
    if (type == 0) {
        numSyncSeen++;
        SyncFrame s = parseSync(packet, off);
        if (s.key.domain != domainNumber) {
            numOtherDomain++;
            writeLog("otherDomain", 0, s.key, packet->getTreeId(), s.frameId, 0, nullptr, -1, -1, -1, "passed unchanged");
            forward(packet);
            return;
        }
        numSync++;
        if (mode == CORRECT) {
            PendingSync ps;
            ps.key = s.key;
            ps.frameId = s.frameId;
            ps.slotTime = simTime();
            pending.push_back({packet->getTreeId(), ps});
            if (s.key.seq == dropSyncSeq) {   // TEST ONLY (H4): lost below the hold point, never transmitted
                numSyncDroppedTest++;
                writeLog("syncDroppedTest", 0, s.key, packet->getTreeId(), s.frameId, 0, nullptr, -1, -1, -1, "TEST dropSyncSeq");
                delete packet;
                return;
            }
        }
        writeLog("syncSlot", 0, s.key, packet->getTreeId(), s.frameId, 0, nullptr, -1, -1, -1, s.error);
        forward(packet);
        return;
    }
    if (type == 8) {
        numFollowUpSeen++;
        if (mode == AUDIT) {
            FollowUpFrame f = parseFollowUp(packet, domainNumber);
            auto tags = f.fu ? syncTags(f.fu) : std::vector<SyncTagRegion>();
            bool whole = tags.size() == 1 && tags[0].offset == b(0) && tags[0].length == f.fuLength;
            if (!whole)
                numAuditNoTag++;
            else if (tags[0].tag->getValid())
                numAuditValid++;
            else
                numAuditInvalid++;
            writeLog("audit", 8, f.key, packet->getTreeId(), 0, f.frameId, whole ? tags[0].tag.get() : nullptr, -1, -1, -1,
                    std::to_string(tags.size()) + " tag regions" + (whole ? "" : " (not exactly one over the whole Follow_Up)"));
            forward(packet);
            return;
        }
        processFollowUp(packet);
        return;
    }
    forward(packet);
}

void TtSyncEgress::discard(Packet *packet, long& counter, const char *event, const FollowUpFrame& f, const std::string& note)
{
    counter++;
    const TtSyncIngressTag *tag = nullptr;
    std::vector<SyncTagRegion> tags;
    if (f.fu) {
        tags = syncTags(f.fu);
        if (tags.size() == 1)
            tag = tags[0].tag.get();
    }
    writeLog(event, 8, f.key, packet->getTreeId(), lastTx.frameId, f.frameId, tag, -1, -1, -1, note);
    delete packet;
}

void TtSyncEgress::processFollowUp(Packet *packet)
{
    FollowUpFrame f = parseFollowUp(packet, domainNumber);
    if (f.unsupported.empty() && f.key.domain != domainNumber) {
        numOtherDomain++;
        writeLog("otherDomain", 8, f.key, packet->getTreeId(), 0, f.frameId, nullptr, -1, -1, -1, "passed unchanged");
        forward(packet);
        return;
    }
    if (!f.unsupported.empty())
        return discard(packet, numUnsupportedRepresentation, "unsupportedRepresentation", f, f.unsupported);
    if (!f.malformed.empty())
        return discard(packet, numMalformedFU, "malformedFU", f, f.malformed);
    auto tags = syncTags(f.fu);
    if (tags.size() != 1 || tags[0].offset != b(0) || tags[0].length != f.fuLength)
        return discard(packet, numFuNoTag, "fuNoTag", f, std::to_string(tags.size()) + " tag regions");
    const auto& tag = tags[0].tag;
    if (!tag->getValid()) {
        if (egressTest == "forwardInvalid") {   // TEST ONLY (N10): an uncorrected FU forwarded
            Rewrite r;
            r.correctionField = f.fu->getCorrectionField();
            r.removeSyncTag = true;
            r.selfCheck = selfCheck;
            std::string e = rewriteFollowUp(packet, f, r);
            if (!e.empty())
                throw cRuntimeError("Follow_Up rewrite self-check failed: %s", e.c_str());
            writeLog("forwardedInvalidTest", 8, f.key, packet->getTreeId(), 0, f.frameId, tag.get(), -1, -1, toSim(r.correctionField),
                    "TEST forwardInvalid");
            forward(packet);
            return;
        }
        return discard(packet, numFuInvalidUpstream, "fuInvalidUpstream", f, tag->getReason());
    }
    Key tk;
    tk.domain = tag->getDomainNumber();
    tk.seq = tag->getSequenceId();
    tk.clock = tag->getSourceClockIdentity();
    tk.port = tag->getSourcePortNumber();
    if (tk != f.key || tag->getTtId() == ttId)
        return discard(packet, numTagMismatch, "tagMismatch", f, "tag key " + tk.str());
    for (const auto& kv : pending) {
        if (kv.second.key == f.key) {
            if (egressTest == "noHold")    // TEST ONLY (N13)
                return discard(packet, numFuNoSync, "fuNoSync", f, "TEST noHold: Sync still queued");
            // step 5: the FIFO hold is enabled in step 6 (a Follow_Up whose Sync is still queued is an internal error here)
            throw cRuntimeError("TtSyncEgress: Follow_Up %s reached the slot while its Sync is still queued (FIFO hold: step 6)", f.key.str().c_str());
            startHold(packet, f.key);
            return;
        }
    }
    if (lastTx.key.isSet() && lastTx.key == f.key) {
        if (lastTx.ambiguous)
            return discard(packet, numAmbiguousSync, "ambiguousSync", f, "");
        if (lastTx.fuSent)
            return discard(packet, numDuplicateFU, "duplicateFU", f, "");
        if (crossCheckFrameId && lastTx.frameId != 0 && tag->getSyncFrameId() != 0 && lastTx.frameId != tag->getSyncFrameId())
            return discard(packet, numAssociationMismatch, "associationMismatch", f,
                    "Sync frame id " + std::to_string(lastTx.frameId) + " vs tag " + std::to_string(tag->getSyncFrameId()));
        simtime_t res = lastTx.tse - tag->getSyncIngressTime();
        if (res < SIMTIME_ZERO)
            throw cRuntimeError("Negative residence time %s for %s", res.str().c_str(), f.key.str().c_str());
        simtime_t resUse = res;
        if (egressTest == "prevSync") {   // TEST ONLY (N5): residence of the previous Sync
            if (lastCorrectedRes >= SIMTIME_ZERO)
                resUse = lastCorrectedRes;
            lastCorrectedRes = res;
        }
        clocktime_t cfIn = f.fu->getCorrectionField();
        clocktime_t cf2 = cfIn + scale(tag->getRateRatioOut(), toClock(resUse));
        Rewrite r;
        r.correctionField = cf2;
        r.removeSyncTag = egressTest != "noStrip";
        r.recomputeFcs = egressTest != "noFcs";
        r.selfCheck = selfCheck;
        // keep a copy of the tag for the log (the rewrite removes it from the frame)
        TtSyncIngressTag tagCopy = *tag;
        std::string e = rewriteFollowUp(packet, f, r);
        if (!e.empty())
            throw cRuntimeError("Follow_Up rewrite self-check failed: %s", e.c_str());
        lastTx.fuSent = true;
        numCorrected++;
        writeLog("corrected", 8, f.key, packet->getTreeId(), lastTx.frameId, f.frameId, &tagCopy, lastTx.tse, resUse, toSim(cf2),
                egressTest.empty() ? "" : "TEST " + egressTest);
        forward(packet);
        return;
    }
    for (const auto& k : recentTx)
        if (k == f.key)
            return discard(packet, numStaleFU, "staleFU", f, "last transmitted Sync " + lastTx.key.str());
    return discard(packet, numFuNoSync, "fuNoSync", f, "last transmitted Sync " + lastTx.key.str());
}

void TtSyncEgress::startHold(Packet *packet, const Key& key)
{
    holding = true;
    heldKey = key;
    held.push_back(packet);
    numHolds++;
    scheduleAfter(holdTimeout, holdTimer);
    writeLog("hold", 8, key, packet->getTreeId(), 0, 0, nullptr, -1, -1, -1, "Sync still queued");
}

void TtSyncEgress::handleMessage(cMessage *msg)
{
    if (msg == releaseEvent)
        release(false);
    else if (msg == holdTimer)
        release(true);
    else
        PacketFlowBase::handleMessage(msg);
}

void TtSyncEgress::release(bool expired)
{
    cancelEvent(holdTimer);
    cancelEvent(releaseEvent);
    holding = false;
    std::deque<Packet *> q;
    q.swap(held);
    Key key = heldKey;
    heldKey = Key();
    writeLog(expired ? "holdExpired" : "release", 8, key, -1, 0, 0, nullptr, -1, -1, -1, std::to_string(q.size()) + " frames");
    Packet *first = q.front();
    q.pop_front();
    if (expired) {
        // the Sync never started transmitting (lost below the hold point): FU discarded
        for (auto it = pending.begin(); it != pending.end();)
            it = it->second.key == key ? pending.erase(it) : std::next(it);
        FollowUpFrame f = parseFollowUp(first, domainNumber);
        discard(first, numFuHoldExpired, "fuHoldExpired", f, "");
    }
    else
        deliver(first);
    for (auto p : q)
        deliver(p);
}

void TtSyncEgress::writeLog(const char *event, int msgType, const Key& key, long treeId, uint64_t syncFrameId, uint64_t fuFrameId,
                            const TtSyncIngressTag *tag, simtime_t tse, simtime_t res, simtime_t cfOut, const std::string& note)
{
    if (!log.is_open())
        return;
    char buf[64];
    snprintf(buf, sizeof(buf), "0x%016" PRIx64, key.clock);
    log << event << ',' << simTime().raw() << ',' << msgType << ',' << key.domain << ',' << key.seq << ',' << buf << ',' << key.port << ','
        << treeId << ',' << syncFrameId << ',' << fuFrameId << ',';
    if (tag) {
        snprintf(buf, sizeof(buf), "%.17g", tag->getRateRatioOut());
        log << (tag->getValid() ? 1 : 0) << ',' << tag->getReason() << ',' << tag->getTtId() << ',' << tag->getSequenceId() << ','
            << raw(tag->getSyncIngressTime()) << ',' << raw(tag->getLinkDelay()) << ',' << buf << ',' << raw(tag->getCorrectionOut()) << ',';
    }
    else
        log << ",,,,,,,,";
    log << raw(tse) << ',' << raw(res) << ',' << raw(cfOut) << ',' << (holding ? 1 : 0) << ',' << note << '\n';
}

void TtSyncEgress::pushPacketStart(Packet *packet, const cGate *gate, bps datarate)
{
    throw cRuntimeError("Packet streaming through TtPtpPort is not supported (packet %s)", packet->getName());
}

void TtSyncEgress::pushPacketProgress(Packet *packet, const cGate *gate, bps datarate, b position, b extraProcessableLength)
{
    throw cRuntimeError("Packet streaming through TtPtpPort is not supported (packet %s)", packet->getName());
}

void TtSyncEgress::pushPacketEnd(Packet *packet, const cGate *gate)
{
    throw cRuntimeError("Packet streaming through TtPtpPort is not supported (packet %s)", packet->getName());
}

void TtSyncEgress::finish()
{
    recordScalar("syncSeen", numSyncSeen);
    recordScalar("followUpSeen", numFollowUpSeen);
    if (mode == OFF)
        return;
    recordScalar("sync", numSync);
    recordScalar("otherDomain", numOtherDomain);
    if (mode == AUDIT) {
        recordScalar("auditValid", numAuditValid);
        recordScalar("auditInvalid", numAuditInvalid);
        recordScalar("auditNoTag", numAuditNoTag);
        return;
    }
    recordScalar("syncTransmitted", numSyncTransmitted);
    recordScalar("corrected", numCorrected);
    recordScalar("fuNoTag", numFuNoTag);
    recordScalar("fuInvalidUpstream", numFuInvalidUpstream);
    recordScalar("tagMismatch", numTagMismatch);
    recordScalar("holds", numHolds);
    recordScalar("heldFrames", numHeldFrames);
    recordScalar("ambiguousSync", numAmbiguousSync);
    recordScalar("duplicateFU", numDuplicateFU);
    recordScalar("associationMismatch", numAssociationMismatch);
    recordScalar("staleFU", numStaleFU);
    recordScalar("fuNoSync", numFuNoSync);
    recordScalar("fuHoldExpired", numFuHoldExpired);
    recordScalar("malformedFU", numMalformedFU);
    recordScalar("unsupportedRepresentation", numUnsupportedRepresentation);
    recordScalar("syncDroppedTest", numSyncDroppedTest);
    recordScalar("heldAtEnd", (double)held.size());
    recordScalar("pendingAtEnd", (double)pending.size());
}

} // namespace nasctime
