//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTEPOCHGATE_H
#define __NASCTIME_M2_TTEPOCHGATE_H

#include "inet/queueing/gate/PeriodicGate.h"

namespace nasctime {

// M2B-5: INET PeriodicGate anchored to a common TT-time epoch (see TtEpochGate.ned).
class TtEpochGate : public inet::queueing::PeriodicGate
{
  protected:
    int64_t clockAtInit = 0, baseTimeRaw = 0, elapsedAtInit = 0;   // ps (recorded for diagnostics only)
    bool initialized = false;

  protected:
    virtual void initialize(int stage) override;
    virtual void handleParameterChange(const char *name) override;
    virtual void finish() override;
};

} // namespace nasctime

#endif
