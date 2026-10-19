//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

import inet.clock.base.ClockServoBase;
import inet.clock.contract.IClockServo;

//
// TEST ONLY (M2-S6 negative controls N-servoNoRate / N-servoSign, migration/m2-s6-design.md rev. 2,
// 6.4): INET's StepClockServo with a wrong rate command. Steps the clock by the measured offset like
// StepClockServo (resetOscillator true) but sets the oscillator compensation to 0 ("noRate") or to the
// negated rate difference ("negRate"). Never used by the experiments.
//
module TestClockServo extends ClockServoBase like IClockServo
{
    parameters:
        @class(nasctime::TestClockServo);
        string mode @enum("noRate","negRate") = default("noRate");
}
