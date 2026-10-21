//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

package nasctime.m2;

// M2-S7.1: interface of the optional residence-time / Follow_Up-lag monitor of a TtPtpPort
// (migration/m2-s7.1-design.md rev. 3, 3.3). Absent by default.
moduleinterface ITtSyncMonitor
{
    parameters:
        @display("i=block/cogwheel");
}
