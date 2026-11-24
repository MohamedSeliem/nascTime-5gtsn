//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
// M2B-2 TEST-ONLY probe (step 148, C2 / C3): calls the public IClock interface of a clock module at chosen
// simulation instants and prints one line per query on stdout, for an independent oracle in
// simulations/m2/check/test_m2b2_ttgateclock.py. Not part of libnasctime_m2; built by simulations/m2/m2b2/build.sh.
//
//   PROBE <t> inv <target> lower|upper <result raw | ERR>     computeSimTimeFromClockTime
//   PROBE <t> c2s <s> lower|upper <result raw | ERR>          computeClockTimeFromSimTime
//   PROBE <t> now <C(now) raw>                                getClockTime() outside a clock event
//   DELIVER <t> <arrival clock raw> <getClockTime() raw>      a probe clock event delivered (ordinary / skipped ps)
//   ERROR <query> <message>                                   the cRuntimeError text of an ERR result
//

#include <cinttypes>
#include <iostream>
#include <sstream>

#include "inet/clock/common/ClockEvent.h"
#include "inet/clock/contract/IClock.h"

using namespace omnetpp;
using namespace inet;

namespace nasctime {

class TtGateClockProbe : public cSimpleModule
{
  protected:
    IClock *clock = nullptr;
    std::vector<int64_t> times;
    int nextTime = 0;
    cMessage *timer = nullptr;

    static std::string str128(__int128 v)
    {
        if (v == 0)
            return "0";
        bool neg = v < 0;
        unsigned __int128 u = neg ? -(unsigned __int128)v : (unsigned __int128)v;
        std::string s;
        while (u > 0) {
            s.insert(s.begin(), char('0' + (int)(u % 10)));
            u /= 10;
        }
        return neg ? "-" + s : s;
    }

    // a target token: min | max | now+<n> | now-<n> | <n> (raw ps); n may exceed int64 only through min / max
    bool target(const std::string& tok, int64_t now, int64_t& out)
    {
        if (tok == "min") { out = INT64_MIN; return true; }
        if (tok == "max") { out = INT64_MAX; return true; }
        __int128 v;
        if (tok.rfind("now+", 0) == 0)
            v = (__int128)now + std::stoll(tok.substr(4));
        else if (tok.rfind("now-", 0) == 0)
            v = (__int128)now - std::stoll(tok.substr(4));
        else
            v = std::stoll(tok);
        if (v > INT64_MAX || v < INT64_MIN)
            return false;
        out = (int64_t)v;
        return true;
    }

    virtual int numInitStages() const override { return 2; }

    virtual void initialize(int stage) override
    {
        if (stage != 1)
            return;
        clock = dynamic_cast<IClock *>(getModuleByPath(par("clockModule").stringValue()));
        if (clock == nullptr)
            throw cRuntimeError("probe: clockModule is not an IClock");
        std::istringstream in(par("times").stdstringValue());
        for (std::string s; in >> s;)
            times.push_back(std::stoll(s));
        timer = new cMessage("probe");
        if (!times.empty())
            scheduleAt(SimTime::fromRaw(times[0]), timer);
    }

    void query()
    {
        int64_t now = simTime().raw();
        std::cout << "PROBE " << now << " now " << clock->getClockTime().raw() << "\n";
        std::istringstream tin(par("targets").stdstringValue());
        for (std::string tok; tin >> tok;) {
            int64_t c;
            if (!target(tok, getClockTimeRaw(), c))
                continue;
            for (bool lower : {true, false}) {
                std::cout << "PROBE " << now << " inv " << tok << " " << (lower ? "lower" : "upper") << " ";
                try {
                    std::cout << clock->computeSimTimeFromClockTime(ClockTime::fromRaw(c), lower).raw() << "\n";
                }
                catch (std::exception& e) {
                    std::cout << "ERR\nERROR inv:" << tok << " " << e.what() << "\n";
                }
            }
        }
        std::istringstream sin(par("simTimes").stdstringValue());
        for (std::string tok; sin >> tok;) {
            int64_t s;
            if (tok == "smax")
                s = SimTime::getMaxTime().raw();
            else if (!target(tok, now, s))
                continue;
            for (bool lower : {true, false}) {
                std::cout << "PROBE " << now << " c2s " << tok << " " << (lower ? "lower" : "upper") << " ";
                try {
                    std::cout << clock->computeClockTimeFromSimTime(SimTime::fromRaw(s), lower).raw() << "\n";
                }
                catch (std::exception& e) {
                    std::cout << "ERR\nERROR c2s:" << tok << " " << e.what() << "\n";
                }
            }
        }
    }

    int64_t getClockTimeRaw() { return clock->getClockTime().raw(); }

    // schedule clock events at clock times the clock skips (C(t) - C(t - 1) >= 2): c = C(t) - 1, and C(t) first,
    // then C(t) - 1, so that the clock-time order differs from the scheduling order (same simulation instant)
    void scheduleSkipEvents()
    {
        int64_t now = simTime().raw();
        for (int64_t t = now + 1; t < now + 10000000; t++) {
            int64_t a = clock->computeClockTimeFromSimTime(SimTime::fromRaw(t - 1)).raw();
            int64_t b = clock->computeClockTimeFromSimTime(SimTime::fromRaw(t)).raw();
            if (b - a >= 2) {
                auto *later = new ClockEvent("probe-skip-upper");
                auto *earlier = new ClockEvent("probe-skip-lower");
                clock->scheduleClockEventAt(ClockTime::fromRaw(b), later);
                clock->scheduleClockEventAt(ClockTime::fromRaw(b - 1), earlier);
                std::cout << "SKIP " << t << " " << b - 1 << " " << b << "\n";
                return;
            }
        }
        std::cout << "SKIP none\n";
    }

    virtual void handleMessage(cMessage *msg) override
    {
        if (msg == timer) {
            query();
            if (par("skipEvents").boolValue() && nextTime == 0)
                scheduleSkipEvents();
            if (++nextTime < (int)times.size())
                scheduleAt(SimTime::fromRaw(times[nextTime]), timer);
            return;
        }
        auto *event = check_and_cast<ClockEvent *>(msg);
        std::cout << "DELIVER " << simTime().raw() << " " << event->getArrivalClockTime().raw() << " "
                  << clock->getClockTime().raw() << "\n";
        delete msg;
    }

    virtual void finish() override { std::cout.flush(); }

  public:
    virtual ~TtGateClockProbe() { cancelAndDelete(timer); }
};

Define_Module(TtGateClockProbe);

} // namespace nasctime
