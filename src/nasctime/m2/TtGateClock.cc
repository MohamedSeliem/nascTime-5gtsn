//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtGateClock.h"

#include <algorithm>
#include <cmath>

#include "inet/clock/common/ClockEvent.h"

#include "TtClock.h"

namespace nasctime {

using namespace inet;

Define_Module(TtGateClock);

static __int128 floorDiv128(__int128 a, __int128 b)
{
    __int128 q = a / b, r = a % b;
    if (r != 0 && ((a < 0) != (b < 0)))
        --q;
    return q;
}

static int64_t psOf(cPar& p)
{
    return std::llround(p.doubleValue() * 1e12);
}

TtGateClock::~TtGateClock()
{
    cancelAndDelete(stepTimer);
}

void TtGateClock::initialize(int stage)
{
    ClockBase::initialize(stage);
    if (stage == INITSTAGE_LOCAL) {
        if (SimTime::getScaleExp() != -12)
            throw cRuntimeError("TtGateClock: simtime-resolution must be ps (TtClock computes in integer ps)");
        std::string m = par("overdueClockEventHandlingMode").stdstringValue();
        if (m == "execute")
            overdueMode = OVERDUE_EXECUTE;
        else if (m == "error")
            overdueMode = OVERDUE_ERROR;
        else
            throw cRuntimeError("TtGateClock: overdueClockEventHandlingMode '%s' (expected execute or error)", m.c_str());
        resolve();
        stepTimer = new cMessage("TtGateClockStep");
        stepTimer->setSchedulingPriority(par("stepSchedulingPriority").intValue());
        scheduleNextStep();
        WATCH(numSteps);
        WATCH(numOverdue);
    }
    else if (stage == INITSTAGE_LAST) {
        // cross-check: within the current segment the adapter's C equals the accepted TtClock's C_T
        int64_t now = simTime().raw();
        for (int64_t s : {now, now + (int64_t)1000000, now + (int64_t)999999999937LL})
            if (segmentStart(s) == segmentStart(now) && segmentClock(segmentStart(s), s) != ttClock->clockFunction(s))
                throw cRuntimeError("TtGateClock: C(%" PRId64 ") differs from TtClock::clockFunction", s);
    }
}

void TtGateClock::resolve() const
{
    if (resolved)
        return;
    cModule *m = getModuleByPath(par("ttClockModule").stringValue());
    ttClock = dynamic_cast<TtClock *>(m);
    if (ttClock == nullptr)
        throw cRuntimeError("TtGateClock: ttClockModule '%s' is not a nasctime::TtClock (no ideal fallback)",
                par("ttClockModule").stringValue());
    theta0 = psOf(ttClock->par("theta0"));
    yPpb = ttClock->par("freqOffsetPpb").intValue();
    dPpbPerS = ttClock->par("driftPpbPerS").intValue();
    updateInterval = psOf(ttClock->par("updateInterval"));
    updateOffset = psOf(ttClock->par("updateOffset"));
    if (updateInterval < 0)
        throw cRuntimeError("TtGateClock: TtClock updateInterval < 0");
    // monotone (non-decreasing) C within a segment: |y| and |D| bounded (rate stays within 1 +- 1e-3)
    if (std::llabs(yPpb) > 1000000 || std::llabs(dPpbPerS) > 1000000)
        throw cRuntimeError("TtGateClock: |freqOffsetPpb| and |driftPpbPerS| must be <= 1e6 for a monotone gate clock");
    resolved = true;
}

int64_t TtGateClock::segmentStart(int64_t s) const
{
    return updateInterval > 0 ? updateOffset + updateInterval * (int64_t)floorDiv128(s - updateOffset, updateInterval) : 0;
}

int64_t TtGateClock::segmentClock(int64_t u, int64_t s) const
{
    __int128 d = s - u;
    __int128 num = (__int128)2000000000000LL * yPpb * d + (__int128)dPpbPerS * d * d;
    __int128 den = (__int128)2000000000000000000LL * 1000;   // 2e21, as TtClock::clockFunction
    return s + theta0 + (int64_t)floorDiv128(num, den);
}

int64_t TtGateClock::currentSegmentStart() const
{
    resolve();
    return segmentStart(simTime().raw());
}

clocktime_t TtGateClock::getClockTime() const
{
    if (handling != nullptr)
        return handling->getArrivalClockTime();   // IClock invariant 2 while one of this clock's events is handled
    clocktime_t c = computeClockTimeFromSimTime(simTime());
    lastClockTime = c;
    return c;
}

clocktime_t TtGateClock::computeClockTimeFromSimTime(simtime_t t, bool lowerBound) const
{
    resolve();
    int64_t s = t.raw(), now = simTime().raw();
    if (s < now)
        throw cRuntimeError("TtGateClock: computeClockTimeFromSimTime of a past time");
    int64_t u = currentSegmentStart();
    if (lowerBound && updateInterval > 0 && s == u && numSteps > 0 && s == now)
        return ClockTime::fromRaw(segmentClock(u - updateInterval, s));   // the side before the step at u
    return ClockTime::fromRaw(segmentClock(u, s));
}

simtime_t TtGateClock::computeSimTimeFromClockTime(clocktime_t c, bool lowerBound) const
{
    resolve();
    int64_t u = currentSegmentStart(), now = simTime().raw();
    int64_t target = c.raw() + (lowerBound ? 0 : 1);       // inf { t >= now | C(t) >= target }
    if (segmentClock(u, now) >= target)
        return SimTime::fromRaw(now);
    int64_t lo = now, hi = now, step = 1;
    while (segmentClock(u, hi) < target) {              // C has rate ~1: doubling reaches the target quickly
        lo = hi;
        if (step > INT64_MAX / 4)
            throw cRuntimeError("TtGateClock: clock time %s out of range", c.str().c_str());
        hi = now + step;
        step *= 2;
    }
    while (hi - lo > 1) {                                // invariant: C(lo) < target <= C(hi)
        int64_t mid = lo + (hi - lo) / 2;
        if (segmentClock(u, mid) >= target)
            hi = mid;
        else
            lo = mid;
    }
    return SimTime::fromRaw(hi);
}

void TtGateClock::scheduleClockEventAt(clocktime_t time, ClockEvent *event)
{
    ClockBase::scheduleClockEventAt(time, event);
    if (std::find(events.begin(), events.end(), event) == events.end())
        events.push_back(event);
}

void TtGateClock::scheduleClockEventAfter(clocktime_t delay, ClockEvent *event)
{
    ClockBase::scheduleClockEventAfter(delay, event);
    if (std::find(events.begin(), events.end(), event) == events.end())
        events.push_back(event);
}

ClockEvent *TtGateClock::cancelClockEvent(ClockEvent *event)
{
    events.erase(std::remove(events.begin(), events.end(), event), events.end());
    return ClockBase::cancelClockEvent(event);
}

void TtGateClock::handleClockEvent(ClockEvent *event)
{
    events.erase(std::remove(events.begin(), events.end(), event), events.end());
    int64_t actual = segmentClock(currentSegmentStart(), simTime().raw());
    if (event->getArrivalClockTime().raw() < actual - 1)   // delivered after its clock time: overdue (a step)
        numOverdue++;
    struct Guard { ClockEvent *& h; ~Guard() { h = nullptr; } } guard{handling};
    handling = event;
    ClockBase::handleClockEvent(event);
}

void TtGateClock::scheduleNextStep()
{
    if (updateInterval <= 0)
        return;                                           // free-running TT clock: no steps
    int64_t now = simTime().raw();
    int64_t next = segmentStart(now) + updateInterval;   // the next update strictly after now
    scheduleAt(SimTime::fromRaw(next), stepTimer);
}

void TtGateClock::handleMessage(cMessage *msg)
{
    if (msg == stepTimer) {
        applyStep();
        scheduleNextStep();
    }
    else
        ClockBase::handleMessage(msg);
}

void TtGateClock::applyStep()
{
    int64_t now = simTime().raw();
    int64_t u = segmentStart(now);
    if (u != now)
        throw cRuntimeError("TtGateClock: step timer off its update instant");
    int64_t oldClock = segmentClock(u - updateInterval, now), newClock = segmentClock(u, now);
    if (newClock != ttClock->clockFunction(now))
        throw cRuntimeError("TtGateClock: C after the step differs from TtClock::clockFunction");
    numSteps++;
    int64_t delta = newClock - oldClock;
    emit(timeChangedSignal, SimTime::fromRaw(oldClock));
    for (auto event : events)                             // relative events keep their simulation arrival time
        if (event->getRelative())
            event->setArrivalClockTime(event->getArrivalClockTime() + ClockTime::fromRaw(delta));
    if (overdueMode == OVERDUE_ERROR)
        for (auto event : events)
            if (event->getArrivalClockTime().raw() < newClock)
                throw cRuntimeError("TtGateClock: clock event '%s' overdue after the step at %s (mode error)",
                        event->getName(), SimTime::fromRaw(now).str().c_str());
    std::vector<ClockEvent *> pending = events;
    std::sort(pending.begin(), pending.end(), [] (auto a, auto b) { return cEvent::compareBySchedulingOrder(a, b) < 0; });
    for (auto event : pending) {                          // re-anchor every pending event to the new mapping
        cSimpleModule *target = check_and_cast<cSimpleModule *>(event->getArrivalModule());
        cContextSwitcher contextSwitcher(target);
        target->rescheduleAt(computeScheduleTime(event->getArrivalClockTime()), event);
    }
    lastClockTime = ClockTime::fromRaw(newClock);
    emit(timeChangedSignal, SimTime::fromRaw(newClock));
}

void TtGateClock::finish()
{
    ClockBase::finish();
    recordScalar("numSteps", numSteps);
    recordScalar("numOverdueClockEvents", numOverdue);
}

} // namespace nasctime
