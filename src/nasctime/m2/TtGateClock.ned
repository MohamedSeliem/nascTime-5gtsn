//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

import inet.clock.base.ClockBase;
import inet.clock.contract.IClock;

//
// M2B-2 S-CLK adapter (docs/migration/m2b-2-clock-and-observation.md): the translator's M2-S6 TtClock presented as
// an INET IClock. Default-off: it exists only where a configuration sets a translator's switch-level clock, e.g.
//   *.dsTt[*].clock.typename = "nasctime.m2.TtGateClock"
// INET's EthernetSwitch then binds every clock user of the translator (*.clockModule, e.g. the PeriodicGates of an
// Ieee8021qTimeAwareShaper) to it. The TtClock is read only (clock function and parameters); no second oscillator.
// Timestamp noise (noiseSigma) and quantization (tickLength) of TtClock are measurement effects of protocol
// timestamps and do not apply to gate scheduling. Steps of C_T at 5G time updates are applied as INET's
// SettableClock applies an explicit step (see TtGateClock.h).
//
module TtGateClock extends ClockBase like IClock
{
    parameters:
        string ttClockModule = default("^.eth[1].trafficConditionerLayer.ttClock"); // the translator's TtClock (required)
        string overdueClockEventHandlingMode @enum("execute","error") = default("execute"); // events a forward step made overdue
        int stepSchedulingPriority = default(-32768);   // the step at an update instant precedes every other event then
        @class(nasctime::TtGateClock);
        @display("i=block/timer");
}
