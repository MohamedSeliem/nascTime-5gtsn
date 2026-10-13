//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

import inet.common.INETDefs;
import inet.common.TagBase;

namespace nasctime;

//
// M2-S0: translator ingress metadata carried with the Ethernet payload inside the
// simulation (a chunk-level region tag; never serialized, never on the wire).
// Added by TtTimestampProcessor (role "ingress") on the payload bytes of every frame a
// translator receives on its TSN-side port; read and removed by the opposite
// translator (role "egress").
//
class TtTimestampTag extends inet::TagBase
{
    simtime_t ingressTime;       // simulation time of the ingress event (+ test-only offset)
    int ingressTtId = -1;           // ttId of the translator that set the tag
    uint64_t frameId = 0;           // per-translator frame counter, starts at 1
}
