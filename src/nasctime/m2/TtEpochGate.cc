//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtEpochGate.h"

#include "TtGateClock.h"

namespace nasctime {

using namespace inet;

Define_Module(TtEpochGate);

void TtEpochGate::initialize(int stage)
{
    // PeriodicGate reads "offset" into initialOffset at INITSTAGE_LOCAL and starts gating at INITSTAGE_QUEUEING;
    // the epoch position is inserted in between, from the translator's TT clock reading at that instant.
    if (stage == INITSTAGE_QUEUEING) {
        IClock *c = clock.getNullable();
        if (c == nullptr)
            throw cRuntimeError("TtEpochGate: no clock (clockModule is empty): a common-epoch gate must not run on simulation time");
        if (dynamic_cast<TtGateClock *>(c) == nullptr)
            throw cRuntimeError("TtEpochGate: clockModule '%s' is not a nasctime::TtGateClock (the translator's TT clock)",
                    par("clockModule").stringValue());
        if (!par("scheduleForAbsoluteTime").boolValue())
            throw cRuntimeError("TtEpochGate: scheduleForAbsoluteTime = false is not supported (relative scheduling would not "
                    "stay anchored to the epoch across TT clock steps)");
        clockAtInit = getClockTime().raw();
        baseTimeRaw = SimTime(par("baseTime").doubleValue()).raw();
        if (clockAtInit < baseTimeRaw)
            throw cRuntimeError("TtEpochGate: base time %s is later than the TT clock at initialization (%s): activation at a "
                    "future base time is not supported", SimTime::fromRaw(baseTimeRaw).str().c_str(), SimTime::fromRaw(clockAtInit).str().c_str());
        elapsedAtInit = clockAtInit - baseTimeRaw;      // >= 0, both int64: no overflow
        int64_t total = 0;
        for (auto d : durations)
            total += d.raw();
        if (total > 0) {
            __int128 pos = ((__int128)initialOffset.raw() % total + elapsedAtInit % total) % total;
            initialOffset = ClockTime::fromRaw((int64_t)pos);
        }
        initialized = true;
    }
    PeriodicGate::initialize(stage);
}

void TtEpochGate::handleParameterChange(const char *name)
{
    if (initialized)
        throw cRuntimeError("TtEpochGate: runtime change of '%s' is not supported (a schedule reconfiguration is not a clock "
                "correction; reconfiguration semantics are not defined for common-epoch gates)", name);
    PeriodicGate::handleParameterChange(name);
}

void TtEpochGate::finish()
{
    PeriodicGate::finish();
    recordScalar("epochClockAtInit", SimTime::fromRaw(clockAtInit));
    recordScalar("epochElapsedAtInit", SimTime::fromRaw(elapsedAtInit));
}

} // namespace nasctime
