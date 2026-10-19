//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtClock.h"

#include <cmath>
#include <filesystem>

namespace nasctime {

Define_Module(TtClock);

static int64_t toPs(double seconds)
{
    return std::llround(seconds * 1e12);
}

static __int128 floorDiv(__int128 a, __int128 b)
{
    __int128 q = a / b, r = a % b;
    if (r != 0 && ((a < 0) != (b < 0)))
        --q;
    return q;
}

TtClock::~TtClock()
{
}

void TtClock::initialize()
{
    theta0 = toPs(par("theta0").doubleValue());
    yPpb = par("freqOffsetPpb").intValue();
    dPpbPerS = par("driftPpbPerS").intValue();
    updateInterval = toPs(par("updateInterval").doubleValue());
    updateOffset = toPs(par("updateOffset").doubleValue());
    sigmaPs = par("noiseSigma").doubleValue() * 1e12;
    tick = toPs(par("tickLength").doubleValue());
    if (tick <= 0 || updateInterval < 0 || sigmaPs < 0)
        throw cRuntimeError("TtClock: tickLength must be > 0, updateInterval >= 0, noiseSigma >= 0");
    std::string path = par("logFile").stdstringValue();
    if (!path.empty()) {
        path += ".ttclock.csv";
        std::filesystem::path p(path);
        if (p.has_parent_path())
            std::filesystem::create_directories(p.parent_path());
        log.open(path, std::ios::out | std::ios::trunc);
        if (!log)
            throw cRuntimeError("Cannot open log file '%s'", path.c_str());
        log << "kind,seq,s,C,w,tau\n";
    }
    WATCH(numStamps);
}

void TtClock::handleMessage(cMessage *msg)
{
    throw cRuntimeError("TtClock schedules no events");
}

void TtClock::finish()
{
    recordScalar("numStamps", numStamps);
}

int64_t TtClock::clockFunction(int64_t s) const
{
    int64_t u = updateInterval > 0 ? updateOffset + updateInterval * (int64_t)floorDiv(s - updateOffset, updateInterval) : 0;
    __int128 d = s - u;
    __int128 num = (__int128)2000000000000LL * yPpb * d + (__int128)dPpbPerS * d * d;
    __int128 den = (__int128)2000000000000000000LL * 1000;   // 2e21
    return s + theta0 + (int64_t)floorDiv(num, den);
}

simtime_t TtClock::stamp(int kind, simtime_t s, long seq)
{
    int64_t c = clockFunction(s.raw());
    int64_t w = 0;
    bool testKind = kind == T1_END || kind == T3_END || kind == T4_END;
    if (sigmaPs > 0 && !testKind)
        w = std::llround(normal(0, sigmaPs));
    int64_t tau = (int64_t)floorDiv((__int128)c + w, tick) * tick;
    numStamps++;
    if (log.is_open())
        log << kind << ',' << seq << ',' << s.raw() << ',' << c << ',' << w << ',' << tau << '\n';
    return SimTime::fromRaw(tau);
}

} // namespace nasctime
