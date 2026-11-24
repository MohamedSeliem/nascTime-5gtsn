//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.simulations.m2.m2b2;

import nasctime.m2.TtClock;
import nasctime.m2.TtGateClock;

//
// M2B-2 TEST-ONLY probe (step 148): queries the public IClock interface of 'clockModule' at the simulation times
// 'times' (raw ps) and prints the results on stdout (see probe/TtGateClockProbe.cc). Its C++ is built separately
// (probe/build.sh); this module and network are used only by check/test_m2b2_ttgateclock.py.
//
simple TtGateClockProbe
{
    parameters:
        string clockModule = default("^.clock");
        string times;                       // raw ps, space separated
        string targets = default("");       // clock-time targets: min | max | now+<n> | now-<n> | <n> (raw ps; now = C(now))
        string simTimes = default("");      // simulation times: smax | now+<n> | <n> (raw ps)
        bool skipEvents = default(false);   // schedule clock events at a skipped clock picosecond (C(t) - 1, C(t))
        @class(nasctime::TtGateClockProbe);
}

network TtGateClockProbeTest
{
    submodules:
        ttClock: TtClock;
        clock: TtGateClock {
            ttClockModule = default("^.ttClock");
        }
        probe: TtGateClockProbe;
}
