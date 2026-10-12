//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//
package nasctime.tt;

import inet.node.tsn.TsnSwitch;

//
// M1 pass-through TSN translator (stage S2): a two-port IEEE 802.1Q bridge that
// stands where a DS-TT or NW-TT will be, and does nothing a translator does.
// It is INET's TsnSwitch with every TSN feature left off (no time synchronization,
// no shaping, no filtering, no stream redundancy): frames are relayed between its
// two ports unchanged (store-and-forward, MAC learning), with no timestamping,
// no PCP/VLAN translation and no residence-time handling.
//
// Port convention: ethg[0] faces the 5G system (UE for a DS-TT, UPF N6 for an
// NW-TT); ethg[1] faces the TSN side.
//
// Unmodified INET modules only; no C++.
//
module PassThroughTt extends TsnSwitch
{
    parameters:
        @display("i=device/switch");
}
