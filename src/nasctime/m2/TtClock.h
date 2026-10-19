//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTCLOCK_H
#define __NASCTIME_M2_TTCLOCK_H

#include <fstream>

#include "TtClockAccess.h"

namespace nasctime {

//
// M2-S6 TT clock, model A2 (see TtClock.ned and migration/m2-s6-design.md rev. 2, 2.3).
//
class TtClock : public cSimpleModule, public ITtClock
{
  protected:
    int64_t theta0 = 0;           // ps
    int64_t yPpb = 0;
    int64_t dPpbPerS = 0;
    int64_t updateInterval = 0;   // ps
    int64_t updateOffset = 0;     // ps
    double sigmaPs = 0;
    int64_t tick = 1;             // ps
    std::ofstream log;
    long numStamps = 0;

  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

  public:
    virtual ~TtClock();
    // C_T(s) in ps (noise-free clock function)
    int64_t clockFunction(int64_t s) const;
    virtual simtime_t stamp(int kind, simtime_t s, long seq) override;
};

} // namespace nasctime

#endif
