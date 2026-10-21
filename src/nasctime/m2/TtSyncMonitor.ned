//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

// M2-S7.1 monitor (migration/m2-s7.1-design.md rev. 3, 3.3), selected in a TtPtpPort by
// monitor.typename = "nasctime.m2.TtSyncMonitor". Observes the DS-TT egress (TtSyncEgress) by
// function calls only; never sends, schedules, draws random numbers or changes a frame.
// Per Sync: TSi, TSe, Res = TSe - TSi and exceeded = Res > residenceBound. Per Follow_Up: lag =
// the time it is first processed with its key at the DS-TT TX path - its Sync's transmission
// start. Per sequenceId: the outcome events (feeds Q8). Monitoring only (decision D4).
simple TtSyncMonitor like ITtSyncMonitor
{
    parameters:
        double residenceBound @unit(s) = default(-1s);   // < 0: no bound, exceeded never set
        string logFile = default("");                    // ".monitor.csv" appended; times in integer ps
        bool testSelfMessage = default(false);           // TEST ONLY (N-monitor): schedule one self-message
        bool testBoundGreaterEqual = default(false);     // TEST ONLY (N-bound): flag Res >= bound instead of Res > bound
        @class(nasctime::TtSyncMonitor);
        @display("i=block/cogwheel");
        @signal[residenceExceeded](type=long);
        @statistic[residenceExceeded](record=count; source=residenceExceeded);
}
