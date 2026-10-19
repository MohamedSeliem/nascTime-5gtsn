//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

//
// M2-S6 translator (TT) clock, model A2 (migration/m2-s6-design.md rev. 2, 2.3). A pure function of
// simulation time (= the ideal 5G reference), plus a per-timestamp measurement:
//
//   u(s)   = updateOffset + updateInterval * floor((s - updateOffset) / updateInterval)   (0 if no updates)
//   C_T(s) = s + theta0 + floor((2e12 * y * (s - u) + D * (s - u)^2) / 2e21)              [ps; y ppb, D ppb/s]
//   tau    = tickLength * floor((C_T(s) + w) / tickLength),  w = llround(normal(0, noiseSigma)) ps
//
// theta0: 5G time-reference error (constant); y, D: TT oscillator frequency error and its drift since
// the last 5G time update (sawtooth); w: white timestamp noise, drawn per protocol timestamp in event
// order from the module's RNG 0 (M2-S6 maps it to RNG 1), never applied to the TEST-only *_END kinds
// and never fed back into C_T; tickLength: timestamp quantization. The module schedules no events:
// timers, hold release and bookkeeping of the port stay in simulation time. Every stamp is logged.
// All parameters at their defaults: tau = s (event-identical to having no TT clock).
//
simple TtClock
{
    parameters:
        double theta0 @unit(s) = default(0s);          // 5G time-reference error (constant)
        int freqOffsetPpb = default(0);                // TT oscillator frequency error y (ppb)
        int driftPpbPerS = default(0);                 // TT oscillator frequency drift D (ppb/s)
        double updateInterval @unit(s) = default(0s);  // 5G time update period (0: none, free-running from 0)
        double updateOffset @unit(s) = default(0s);    // phase of the updates
        double noiseSigma @unit(s) = default(0s);      // white timestamp noise (standard deviation)
        double tickLength @unit(s) = default(1ps);     // timestamp quantization
        string logFile = default("");                  // ".ttclock.csv" appended; times in integer ps
        @class(nasctime::TtClock);
        @display("i=block/timer");
}
