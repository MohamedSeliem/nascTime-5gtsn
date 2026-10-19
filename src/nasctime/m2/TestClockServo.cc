//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TestClockServo.h"

#include "inet/clock/model/SettableClock.h"

namespace nasctime {

Define_Module(TestClockServo);

void TestClockServo::initialize(int stage)
{
    ClockServoBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL)
        noRate = !strcmp(par("mode").stringValue(), "noRate");
}

// as StepClockServo::adjustClockForDifference, with a wrong rate command (TEST ONLY)
void TestClockServo::adjustClockForDifference(clocktime_t timeDifference, ppm rateDifference)
{
    Enter_Method("adjustClockForDifference");
    ppm rate = noRate ? ppm(0) : -rateDifference;
    clock->setClockTime(clock->getClockTime() - timeDifference, rate, true);
}

} // namespace nasctime
