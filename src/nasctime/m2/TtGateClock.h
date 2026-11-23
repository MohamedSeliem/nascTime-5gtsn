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
// While one of its events is being handled, getClockTime() returns that event's arrival clock time (IClock
// invariant 2), so a PeriodicGate that anchors its next change on getClockTime() keeps its phase exactly, also
// when catching up overdue changes after a forward step (the same effect SettableClock obtains for EXECUTE).
//
class TtGateClock : public inet::ClockBase
{
  protected:
    enum OverdueMode { OVERDUE_EXECUTE, OVERDUE_ERROR };

    mutable TtClock *ttClock = nullptr;         // resolved lazily (clock users may ask before this module's stage)
    mutable bool resolved = false;
    mutable int64_t theta0 = 0, yPpb = 0, dPpbPerS = 0, updateInterval = 0, updateOffset = 0;   // ps, ppb, ppb/s
    OverdueMode overdueMode = OVERDUE_EXECUTE;
    omnetpp::cMessage *stepTimer = nullptr;
    std::vector<inet::ClockEvent *> events;     // pending events scheduled through this clock
    inet::ClockEvent *handling = nullptr;       // the event being handled (getClockTime() returns its clock time)
    long numSteps = 0, numOverdue = 0;

  protected:
    virtual void initialize(int stage) override;
    virtual void handleMessage(omnetpp::cMessage *msg) override;
    virtual void finish() override;

    void resolve() const;
    int64_t segmentStart(int64_t s) const;                    // u(s), as TtClock
    int64_t segmentClock(int64_t u, int64_t s) const;         // C for segment start u, evaluated at s (extended)
    int64_t currentSegmentStart() const;                       // u of the segment in force now (after any step at now)
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

    // for tests: C for the segment starting at u, evaluated at s (ps)
    int64_t segmentClockForTest(int64_t u, int64_t s) const { resolve(); return segmentClock(u, s); }
};

} // namespace nasctime

#endif
