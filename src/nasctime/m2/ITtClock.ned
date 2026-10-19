//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

//
// M2-S6: module interface of a translator (TT) clock (TtClock; C++ interface ITtClock in
// TtClockAccess.h). TtPtpPort's "ttClock" submodule is absent unless its typename is set.
//
moduleinterface ITtClock
{
    parameters:
        @display("i=block/timer");
}
