//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCMONITOR_H
#define __NASCTIME_M2_TTSYNCMONITOR_H

#include <fstream>
#include <map>

#include "TtSyncMonitorAccess.h"

namespace nasctime {

// See TtSyncMonitor.ned.
class TtSyncMonitor : public cSimpleModule, public ITtSyncMonitor
{
  protected:
    simtime_t residenceBound;
    bool testBoundGreaterEqual = false;
    std::ofstream log;
    std::map<std::pair<int, int>, simtime_t> syncTxTime;   // (domain, seq) -> Sync transmission start
    std::map<std::pair<int, int>, simtime_t> fuFirstSeen;  // (domain, seq) -> first keyed Follow_Up event
    std::map<std::string, long> eventCounts;
    long numExceeded = 0, numCorrected = 0;
    simsignal_t residenceExceededSignal;

  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

  public:
    virtual void egressEvent(const char *event, int msgType, int domain, int seq, bool hasKey,
                             simtime_t tsi, simtime_t tse, simtime_t res, bool holding) override;
};

} // namespace nasctime

#endif
