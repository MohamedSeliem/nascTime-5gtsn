//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTCLOCKACCESS_H
#define __NASCTIME_M2_TTCLOCKACCESS_H

#include <omnetpp.h>

namespace nasctime {

using namespace omnetpp;

//
// M2-S6 translator (TT) clock access (migration/m2-s6-design.md rev. 2, 2.3 and 3.3).
// Every protocol timestamp of a translator's TSN port is read through ttStamp(): TSi (NW-TT Sync
// reception start), TSe (DS-TT Sync transmission start) and the Pdelay engine's t1, t2, t3, t4.
// Scheduling and bookkeeping (timers, hold release, pairing checks) stay in simulation time.
// Without a TT clock (no "ttClock" submodule next to the caller, the default and every M2-S5
// config) ttStamp() returns the simulation time unchanged: the A1 model, ideal 5G time.
//
class ITtClock
{
  public:
    enum Kind { TSI = 1, TSE = 2, T1 = 3, T2 = 4, T3 = 5, T4 = 6, T1_END = 7, T3_END = 8, T4_END = 9 };
    virtual ~ITtClock() {}
    // measured timestamp of an event that happened at simulation time s (s <= now)
    virtual simtime_t stamp(int kind, simtime_t s, long seq) = 0;
};

// the TT clock of the port that contains `self`, or nullptr (A1)
inline ITtClock *findTtClock(cModule *self)
{
    cModule *parent = self->getParentModule();
    cModule *m = parent ? parent->getSubmodule("ttClock") : nullptr;
    return m ? dynamic_cast<ITtClock *>(m) : nullptr;
}

inline simtime_t ttStamp(ITtClock *clock, int kind, simtime_t s, long seq)
{
    return clock ? clock->stamp(kind, s, seq) : s;
}

} // namespace nasctime

#endif
