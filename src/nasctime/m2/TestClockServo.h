//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TESTCLOCKSERVO_H
#define __NASCTIME_M2_TESTCLOCKSERVO_H

#include "inet/clock/base/ClockServoBase.h"

namespace nasctime {

using namespace inet;

// TEST ONLY: see TestClockServo.ned
class TestClockServo : public ClockServoBase
{
  protected:
    bool noRate = true;

  protected:
    virtual void initialize(int stage) override;

  public:
    virtual void adjustClockForDifference(clocktime_t timeDifference, ppm rateDifference) override;
};

} // namespace nasctime

#endif
