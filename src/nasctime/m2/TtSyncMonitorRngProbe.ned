//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

// M2-S7.1 closure diagnostic (seed-invariance investigation): TtSyncMonitor that also records, at
// finish, how many numbers each physical RNG of the run delivered (cRNG::getNumbersDrawn()), as
// scalars rngDrawn:<k>. With per-module RNG mappings in the ini this counts the draws per module
// group. Observes only, like TtSyncMonitor; draws nothing itself. Used by M2S71-R-* configs only.
simple TtSyncMonitorRngProbe extends TtSyncMonitor
{
    parameters:
        @class(nasctime::TtSyncMonitorRngProbe);
}
