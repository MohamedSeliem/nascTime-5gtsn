//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

import inet.queueing.contract.IPacketGate;
import inet.queueing.gate.PeriodicGate;

//
// M2B-5 (docs/migration/m2b-5-common-epoch.md): INET PeriodicGate whose cycle is anchored to a common TT-time epoch.
// Default-off: used only where a configuration sets transmissionGate[*].typename (the S-CFG/2 compiler does so for
// schedules with tas.time_reference = "common-epoch").
//
// PeriodicGate anchors its cycle on the clock reading at initialization: at that reading it is at position "offset"
// of its durations list. TtEpochGate only replaces that initial position by
//     offset + (C_T(init) - baseTime)   (modulo the cycle),
// where C_T(init) is the reading of its own clock, which must be the translator's TtGateClock (the accepted TT clock;
// no other time source, no simulation time). "offset" is thus the list position at TT time baseTime, and the gate
// position at TT time c is (c - baseTime) mod cycle, as declared. Everything else (gating, guard band, absolute
// scheduling, the TtGateClock step semantics) is INET's PeriodicGate.
// Refused (errors): no clock or not a TtGateClock; scheduleForAbsoluteTime = false; a base time later than the TT
// clock at initialization (future activation is not supported); runtime changes of the schedule parameters.
//
simple TtEpochGate extends PeriodicGate like IPacketGate
{
    parameters:
        double baseTime @unit(s);    // common TT-time epoch (exact integer ps; S-CFG/2 base_time_ns)
        @class(nasctime::TtEpochGate);
}
