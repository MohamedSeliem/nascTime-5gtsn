//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTSYNCMONITORRNGPROBE_H
#define __NASCTIME_M2_TTSYNCMONITORRNGPROBE_H

#include "TtSyncMonitor.h"

namespace nasctime {

// See TtSyncMonitorRngProbe.ned.
class TtSyncMonitorRngProbe : public TtSyncMonitor
{
  protected:
    virtual void finish() override;
};

} // namespace nasctime

#endif
