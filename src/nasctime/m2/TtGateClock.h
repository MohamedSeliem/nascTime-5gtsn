//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTGATECLOCK_H
#define __NASCTIME_M2_TTGATECLOCK_H

#include <vector>

#include "inet/clock/base/ClockBase.h"

namespace nasctime {

class TtClock;

//
// M2B-2 S-CLK adapter (docs/migration/m2b-2-clock-and-observation.md): presents the translator's accepted M2-S6
// TtClock (model A2) as an INET IClock, so that INET clock users of the translator (the time-aware shaper's
// PeriodicGates) schedule against TT time. The TtClock is only read: its noise-free clock function C_T and its
// parameters; it is never modified and gets no events. No second oscillator: the gate clock IS C_T.
//
// C_T is piecewise: within an update segment [u_k, u_k+1) it is C_k(s) = s + theta0 + floor((2e12 y (s - u_k)
// + D (s - u_k)^2) / 2e21) (ps), and at each 5G time update u_k it steps by C_k(u_k) - C_k-1(u_k). As INET's
// SettableClock does for an explicit step, the adapter applies each step at u_k: relative events keep their
// simulation arrival time, absolute events are re-anchored to the new mapping, and events that the step made
// overdue are delivered at once ("execute", INET's default) or raise an error ("error"). Between steps the
// conversions use the current segment's C_k, extended.
//
// IClock contract at picosecond resolution (step 148, C2). C_T can advance by more than 1 ps per simulated ps (rate
// above 1) and jumps at forward steps, so a simulation instant t covers the clock interval (C(t-1), C(t)]: an event
// scheduled at clock time c fires at t = inf { t >= now | C(t) >= c } and C(t-1) < c <= C(t).
//  - computeClockTimeFromSimTime(t, lowerBound = true) is the low end of that interval, min(C(t-1) + 1, C(t)) (at a
//    step instant C(t-1) is the pre-step segment), and lowerBound = false is C(t) (invariant 5).
//  - getClockTime() returns the arrival clock time of the clock event being executed: from ClockEvent::execute()
//    (where INET checks invariant 2, before the clock handles the event) to the end of its handling. The event is
//    recognised through public interfaces only: it is one of this clock's events, due now, and already taken off
//    the future event set (!isScheduled()). Otherwise getClockTime() is C(now).
//  - Clock events due at the same instant are kept in arrival clock-time order (within equal scheduling priority),
//    so the presented clock time does not go back between them.
//  - Overdue: a clock time jumped over by a forward step at u (C_old(u) < c < C_new(u)). In "execute" mode such
//    events are rescheduled to u and delivered at u in clock-time order, each presenting its own clock time, also
//    events scheduled while catching up (the SettableClock EXECUTE semantics, without its friend-only path).
// Range (C3): C is evaluated in 128-bit arithmetic; a time or clock time outside the int64 simtime_t range, or
// beyond the range where the current segment's C_T is non-decreasing (driftPpbPerS < 0), is a cRuntimeError, never
// a wrapped or non-monotone value. An update interval longer than that monotone range is refused at initialization.
// Lifetime: as for INET's SettableClock, a clock event must be cancelled through the clock before it is deleted.
//
class TtGateClock : public inet::ClockBase
{
  protected:
    enum OverdueMode { OVERDUE_EXECUTE, OVERDUE_ERROR };

    mutable TtClock *ttClock = nullptr;         // resolved lazily (clock users may ask before this module's stage)
    mutable bool resolved = false;
    mutable int64_t theta0 = 0, yPpb = 0, dPpbPerS = 0, updateInterval = 0, updateOffset = 0;   // ps, ppb, ppb/s
    mutable __int128 monotoneSpan = 0;          // C_u is non-decreasing on [u, u + monotoneSpan]; < 0: unbounded
    OverdueMode overdueMode = OVERDUE_EXECUTE;
    omnetpp::cMessage *stepTimer = nullptr;
    std::vector<inet::ClockEvent *> events;     // pending events scheduled through this clock
    inet::ClockEvent *handling = nullptr;       // the event being handled
    inet::clocktime_t handlingClockTime;        // its arrival clock time when delivered (the handler may reuse the event)
    int64_t lastStepAt = INT64_MIN, lastStepOld = 0, lastStepNew = 0;   // the last step: instant, C_old(u), C_new(u)
    long numSteps = 0, numOverdue = 0;

  protected:
    virtual void initialize(int stage) override;
    virtual void handleMessage(omnetpp::cMessage *msg) override;
    virtual void finish() override;

    void resolve() const;
    int64_t segmentStart(int64_t s) const;                    // u(s), as TtClock
    __int128 segmentClock128(int64_t u, int64_t s) const;     // C for segment start u, evaluated at s (extended)
    int64_t segmentClock(int64_t u, int64_t s) const;         // the same, checked to be within the int64 range
    int64_t monotoneEnd(int64_t u) const;                     // last s at which C_u is still non-decreasing (int64)
    int64_t currentSegmentStart() const;                       // u of the segment in force now (after any step at now)
    bool executingClockTime(inet::clocktime_t& clockTime) const;   // clock time of this clock's event executing now
    void orderSameInstant(inet::ClockEvent *event);           // keep events due with 'event' in clock-time order
    void track(inet::ClockEvent *event);
    void scheduleNextStep();
    void applyStep();

  public:
    virtual ~TtGateClock();

    // IClock
    virtual inet::clocktime_t getClockTime() const override;
    virtual inet::clocktime_t computeClockTimeFromSimTime(omnetpp::simtime_t time, bool lowerBound = false) const override;
    virtual omnetpp::simtime_t computeSimTimeFromClockTime(inet::clocktime_t time, bool lowerBound = true) const override;
    virtual void scheduleClockEventAt(inet::clocktime_t time, inet::ClockEvent *event) override;
    virtual void scheduleClockEventAfter(inet::clocktime_t delay, inet::ClockEvent *event) override;
    virtual inet::ClockEvent *cancelClockEvent(inet::ClockEvent *event) override;
    virtual void handleClockEvent(inet::ClockEvent *event) override;
};

} // namespace nasctime

#endif
