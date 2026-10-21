//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtSyncMonitor.h"

#include <filesystem>
#include <string>

namespace nasctime {

Define_Module(TtSyncMonitor);

static std::string raw(simtime_t t) { return t < SIMTIME_ZERO ? std::string() : std::to_string(t.raw()); }

void TtSyncMonitor::initialize()
{
    residenceBound = par("residenceBound");
    testBoundGreaterEqual = par("testBoundGreaterEqual");
    residenceExceededSignal = registerSignal("residenceExceeded");
    std::string logFile = par("logFile").stdstringValue();
    if (!logFile.empty()) {
        std::string path = logFile + ".monitor.csv";
        std::filesystem::path p(path);
        if (p.has_parent_path())
            std::filesystem::create_directories(p.parent_path());
        log.open(path, std::ios::out | std::ios::trunc);
        if (!log)
            throw cRuntimeError("Cannot open log file '%s'", path.c_str());
        // times in integer ps (raw simulation time)
        log << "event,t,msgType,domain,seq,TSi,TSe,Res,exceeded,lag,holding\n";
    }
    if (par("testSelfMessage").boolValue())   // TEST ONLY (N-monitor): perturbs the event sequence
        scheduleAt(simTime(), new cMessage("monitorTest"));
}

void TtSyncMonitor::handleMessage(cMessage *msg)
{
    delete msg;   // only the TEST ONLY self-message
}

void TtSyncMonitor::egressEvent(const char *event, int msgType, int domain, int seq, bool hasKey,
                                simtime_t tsi, simtime_t tse, simtime_t res, bool holding)
{
    eventCounts[event]++;
    auto key = std::make_pair(domain, seq);
    simtime_t lag = -1;
    int exceeded = -1;
    if (hasKey && msgType == 0 && !strcmp(event, "syncTx"))
        syncTxTime[key] = simTime();
    if (hasKey && msgType == 8 && !fuFirstSeen.count(key)) {
        fuFirstSeen[key] = simTime();
        auto it = syncTxTime.find(key);
        if (it != syncTxTime.end())
            lag = simTime() - it->second;
    }
    if (!strcmp(event, "corrected")) {
        numCorrected++;
        exceeded = residenceBound >= SIMTIME_ZERO && (testBoundGreaterEqual ? res >= residenceBound : res > residenceBound) ? 1 : 0;
        if (exceeded) {
            numExceeded++;
            emit(residenceExceededSignal, (long)seq);
        }
    }
    if (log.is_open())
        log << event << ',' << simTime().raw() << ',' << msgType << ',' << (hasKey ? std::to_string(domain) : "") << ','
            << (hasKey ? std::to_string(seq) : "") << ',' << raw(tsi) << ',' << raw(tse) << ',' << raw(res) << ','
            << (exceeded < 0 ? "" : std::to_string(exceeded)) << ',' << raw(lag) << ',' << (holding ? 1 : 0) << '\n';
}

void TtSyncMonitor::finish()
{
    recordScalar("corrected", numCorrected);
    recordScalar("residenceExceeded", numExceeded);
    for (const auto& kv : eventCounts)
        recordScalar(("event:" + kv.first).c_str(), kv.second);
}

} // namespace nasctime
