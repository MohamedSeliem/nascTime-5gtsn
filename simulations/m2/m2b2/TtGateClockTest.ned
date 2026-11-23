//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.simulations.m2.m2b2;

import inet.queueing.gate.PeriodicGate;
import inet.queueing.sink.PassivePacketSink;
import inet.queueing.source.ActivePacketSource;
import nasctime.m2.TtClock;
import nasctime.m2.TtGateClock;

//
// M2B-2 TEST network (no TT, no 5G system): the accepted TtClock, the TtGateClock adapter, and an unmodified INET
// PeriodicGate scheduled through the adapter. The gate's recorded state changes are compared with an independent
// oracle of the TT clock in check/test_m2b2_ttgateclock.py. Not part of any accepted configuration.
//
network TtGateClockTest
{
    submodules:
        ttClock: TtClock;
        clock: TtGateClock {
            ttClockModule = default("^.ttClock");
        }
        source: ActivePacketSource;
        gate: PeriodicGate {
            clockModule = default("^.clock");
        }
        sink: PassivePacketSink;
    connections:
        source.out --> gate.in;
        gate.out --> sink.in;
}
