//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCMONITORACCESS_H
#define __NASCTIME_M2_TTSYNCMONITORACCESS_H

#include <omnetpp.h>

namespace nasctime {

using namespace omnetpp;

//
// M2-S7.1 residence-time / Follow_Up-lag monitor access (migration/m2-s7.1-design.md rev. 3, 3.3).
// TtSyncEgress reports every event it logs to the port's monitor, if one exists, by a plain
// function call. The monitor observes only: it sends and schedules no messages, draws no random
// numbers and never changes a frame. Without a monitor (no "monitor" submodule next to the
// caller, the default and every earlier config) nothing is called.
//
class ITtSyncMonitor
{
  public:
    virtual ~ITtSyncMonitor() {}
    // one TtSyncEgress event at the current simulation time; times < 0 when not applicable
    virtual void egressEvent(const char *event, int msgType, int domain, int seq, bool hasKey,
                             simtime_t tsi, simtime_t tse, simtime_t res, bool holding) = 0;
};

// the monitor of the port that contains `self`, or nullptr
inline ITtSyncMonitor *findTtSyncMonitor(cModule *self)
{
    cModule *parent = self->getParentModule();
    cModule *m = parent ? parent->getSubmodule("monitor") : nullptr;
    return m ? dynamic_cast<ITtSyncMonitor *>(m) : nullptr;
}

} // namespace nasctime

#endif
