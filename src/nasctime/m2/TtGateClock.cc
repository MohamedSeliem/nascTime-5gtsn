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
    // rate 1 + y*1e-9 + D*dd*1e-21 with |y| <= 1e6: positive at dd = 0
    if (std::llabs(yPpb) > 1000000 || std::llabs(dPpbPerS) > 1000000)
        throw cRuntimeError("TtGateClock: |freqOffsetPpb| and |driftPpbPerS| must be <= 1e6 for a monotone gate clock");
    // C_u(s + 1) - C_u(s) >= 0 whenever f(dd + 1) - f(dd) >= -2e21 with f(dd) = 2e12 y dd + D dd^2, i.e.
    // 2e12 y + D (2 dd + 1) >= -2e21. Always true for D >= 0 (|2e12 y| <= 2e18); for D < 0 it holds for
    // dd <= ((2e21 + 2e12 y) / |D| - 1) / 2, so C_u is non-decreasing on [u, u + that + 1].
    if (dPpbPerS >= 0)
        monotoneSpan = -1;
    else {
        __int128 n = (__int128)2000000000000000000LL * 1000 + (__int128)2000000000000LL * yPpb;
        monotoneSpan = (n / -(__int128)dPpbPerS - 1) / 2 + 1;
    }
    if (updateInterval > 0 && monotoneSpan >= 0 && (__int128)updateInterval - 1 > monotoneSpan)
        throw cRuntimeError("TtGateClock: TtClock updateInterval %s exceeds the range in which C_T is non-decreasing "
                "for driftPpbPerS %" PRId64 " (%s)", SimTime::fromRaw(updateInterval).str().c_str(), dPpbPerS,
                SimTime::fromRaw((int64_t)monotoneSpan).str().c_str());
    resolved = true;
}

int64_t TtGateClock::segmentStart(int64_t s) const
{
    return updateInterval > 0 ? updateOffset + updateInterval * (int64_t)floorDiv128((__int128)s - updateOffset, updateInterval) : 0;
}

__int128 TtGateClock::segmentClock128(int64_t u, int64_t s) const
{
    __int128 d = (__int128)s - u;
    __int128 num = (__int128)2000000000000LL * yPpb * d + (__int128)dPpbPerS * d * d;
    __int128 den = (__int128)2000000000000000000LL * 1000;   // 2e21, as TtClock::clockFunction
    return (__int128)s + theta0 + floorDiv128(num, den);
}

int64_t TtGateClock::segmentClock(int64_t u, int64_t s) const
{
    __int128 c = segmentClock128(u, s);
    if (c > INT64_MAX || c < INT64_MIN)
        throw cRuntimeError("TtGateClock: the clock time at simulation time %s is outside the clocktime_t range",
                SimTime::fromRaw(s).str().c_str());
    return (int64_t)c;
}

int64_t TtGateClock::monotoneEnd(int64_t u) const
{
    __int128 end = monotoneSpan < 0 ? (__int128)INT64_MAX : (__int128)u + monotoneSpan;
    return (int64_t)std::min(end, (__int128)SimTime::getMaxTime().raw());
}

int64_t TtGateClock::currentSegmentStart() const
{
    resolve();
    return segmentStart(simTime().raw());
}

bool TtGateClock::executingClockTime(clocktime_t& clockTime) const
{
    if (handling != nullptr) {
        clockTime = handlingClockTime;
        return true;
    }
    // inside ClockEvent::execute() (before handleClockEvent): the event is due now and no longer in the FES
    simtime_t now = simTime();
    const ClockEvent *found = nullptr;
    for (auto event : events)
        if (event->getArrivalTime() == now && !event->isScheduled()) {
            if (found != nullptr)
                return false;                             // ambiguous (an event removed from the FES behind the clock)
            found = event;
        }
    if (found == nullptr)
        return false;
    clockTime = found->getArrivalClockTime();
    return true;
}

clocktime_t TtGateClock::getClockTime() const
{
    clocktime_t c;
    if (executingClockTime(c))
        return c;                                    // IClock invariant 2 for the event being executed
    c = computeClockTimeFromSimTime(simTime());
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
    if (s > monotoneEnd(u))
        throw cRuntimeError("TtGateClock: simulation time %s is beyond the range in which the TT clock is "
                "non-decreasing (driftPpbPerS %" PRId64 " without a time update)", t.str().c_str(), dPpbPerS);
    int64_t upper = segmentClock(u, s);
    if (!lowerBound)
        return ClockTime::fromRaw(upper);
    // the instant s covers (C(s - 1), C(s)]; at now, C(s - 1) is the segment in force at s - 1 (before a step at s)
    __int128 prev = s == now ? segmentClock128(segmentStart(s - 1), s - 1) : segmentClock128(u, s - 1);
    return ClockTime::fromRaw((int64_t)std::min(prev + 1, (__int128)upper));
}

simtime_t TtGateClock::computeSimTimeFromClockTime(clocktime_t c, bool lowerBound) const
{
    resolve();
    int64_t u = currentSegmentStart(), now = simTime().raw();
    __int128 target = (__int128)c.raw() + (lowerBound ? 0 : 1);    // inf { t >= now | C(t) >= target }
    if (segmentClock128(u, now) >= target)
        return SimTime::fromRaw(now);
    int64_t last = monotoneEnd(u);                     // C_u is non-decreasing on [now, last] and last <= max simtime
    if (segmentClock128(u, last) < target)
        throw cRuntimeError("TtGateClock: clock time %s is not reached before simulation time %s (the end of the "
                "simtime_t range or of the range in which the TT clock is non-decreasing)", c.str().c_str(),
                SimTime::fromRaw(last).str().c_str());
    int64_t lo = now, hi = last;
    for (int64_t step = 1; ; step = step > (last - now) / 2 ? last - now : step * 2) {   // expanding, never past last
        int64_t probe = now + step;                    // step <= last - now: no overflow
        if (segmentClock128(u, probe) >= target) {
            hi = probe;
            break;
        }
        lo = probe;
        if (step == last - now)
            break;                                     // unreachable: excluded above
    }
    while (hi - lo > 1) {                              // C(lo) < target <= C(hi), C_u monotone on [lo, hi]
        int64_t mid = lo + (hi - lo) / 2;
        if (segmentClock128(u, mid) >= target)
            hi = mid;
        else
            lo = mid;
    }
    return SimTime::fromRaw(hi);
}

void TtGateClock::track(ClockEvent *event)
{
    if (std::find(events.begin(), events.end(), event) == events.end())
        events.push_back(event);
}

void TtGateClock::orderSameInstant(ClockEvent *event)
{
    // events due at the same instant with a later clock time (equal priority) go after 'event' in the FES
    std::vector<ClockEvent *> later;
    for (auto other : events)
        if (other != event && other->isScheduled() && other->getArrivalTime() == event->getArrivalTime()
                && other->getSchedulingPriority() == event->getSchedulingPriority()
                && other->getArrivalClockTime() > event->getArrivalClockTime())
            later.push_back(other);
    std::stable_sort(later.begin(), later.end(), [] (ClockEvent *a, ClockEvent *b) {
        return a->getArrivalClockTime() != b->getArrivalClockTime() ? a->getArrivalClockTime() < b->getArrivalClockTime()
                : cEvent::compareBySchedulingOrder(a, b) < 0; });
    for (auto other : later) {
        cSimpleModule *target = check_and_cast<cSimpleModule *>(other->getArrivalModule());
        cContextSwitcher contextSwitcher(target);
        target->rescheduleAt(other->getArrivalTime(), other);
    }
}

void TtGateClock::scheduleClockEventAt(clocktime_t time, ClockEvent *event)
{
    ClockBase::scheduleClockEventAt(time, event);
    track(event);
    orderSameInstant(event);
}

void TtGateClock::scheduleClockEventAfter(clocktime_t delay, ClockEvent *event)
{
    ClockBase::scheduleClockEventAfter(delay, event);
    track(event);
    orderSameInstant(event);
}

ClockEvent *TtGateClock::cancelClockEvent(ClockEvent *event)
{
    events.erase(std::remove(events.begin(), events.end(), event), events.end());
    return ClockBase::cancelClockEvent(event);
}

void TtGateClock::handleClockEvent(ClockEvent *event)
{
    int64_t c = event->getArrivalClockTime().raw();
    if (simTime().raw() == lastStepAt && c > lastStepOld && c < lastStepNew)
        numOverdue++;                                    // its clock time was jumped over by the step at this instant
    struct Guard { ClockEvent *& h; ~Guard() { h = nullptr; } } guard{handling};
    handlingClockTime = event->getArrivalClockTime();
    handling = event;                                    // set before untracking: getClockTime() stays its clock time
    events.erase(std::remove(events.begin(), events.end(), event), events.end());
    ClockBase::handleClockEvent(event);
}

void TtGateClock::scheduleNextStep()
{
    if (updateInterval <= 0)
        return;                                           // free-running TT clock: no steps
    __int128 next = (__int128)segmentStart(simTime().raw()) + updateInterval;   // the next update strictly after now
    if (next <= SimTime::getMaxTime().raw())
        scheduleAt(SimTime::fromRaw((int64_t)next), stepTimer);
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
    lastStepAt = now;
    lastStepOld = oldClock;
    lastStepNew = newClock;
    int64_t delta = newClock - oldClock;
    emit(timeChangedSignal, SimTime::fromRaw(oldClock));
    for (auto event : events)                             // relative events keep their simulation arrival time
        if (event->getRelative())
            event->setArrivalClockTime(event->getArrivalClockTime() + ClockTime::fromRaw(delta));
    if (overdueMode == OVERDUE_ERROR)
        for (auto event : events)
            if (!event->getRelative() && event->getArrivalClockTime().raw() > oldClock && event->getArrivalClockTime().raw() < newClock)
                throw cRuntimeError("TtGateClock: clock event '%s' overdue after the step at %s (mode error)",
                        event->getName(), SimTime::fromRaw(now).str().c_str());
    std::vector<ClockEvent *> pending = events;            // re-anchor every pending event, in clock-time order
    std::stable_sort(pending.begin(), pending.end(), [] (ClockEvent *a, ClockEvent *b) {
        return a->getArrivalClockTime() != b->getArrivalClockTime() ? a->getArrivalClockTime() < b->getArrivalClockTime()
                : cEvent::compareBySchedulingOrder(a, b) < 0; });
    for (auto event : pending) {
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
