//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtSyncMonitorRngProbe.h"

namespace nasctime {

Define_Module(TtSyncMonitorRngProbe);

void TtSyncMonitorRngProbe::finish()
{
    TtSyncMonitor::finish();
    for (int k = 0; k < getEnvir()->getNumRNGs(); k++)
        recordScalar(("rngDrawn:" + std::to_string(k)).c_str(), (double)getEnvir()->getRNG(k)->getNumbersDrawn());
}

} // namespace nasctime
