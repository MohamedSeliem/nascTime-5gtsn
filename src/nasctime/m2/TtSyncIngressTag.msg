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
// M2-S5 (migration/m2-s5-design.md, option B): metadata the NW-TT attaches to a
// Follow_Up it has handled, over the whole GptpFollowUp payload chunk (a chunk-level
// region tag; never serialized, never on the wire). Read and removed by the DS-TT.
//   valid = true  (class V): the FU was corrected by the NW-TT (cf1 = cf_in + rr_in*Lup)
//                 and its Sync's ingress time is syncIngressTime;
//   valid = false (class I): parseable but not correctable (reason); cf unchanged. The
//                 DS-TT never forwards such a FU.
//
class TtSyncIngressTag extends inet::TagBase
{
    bool valid = false;
    string reason;                   // class I: why the FU could not be corrected
    int ttId = -1;                   // ttId of the translator that set the tag
    simtime_t syncIngressTime = -1;  // TSi: first bit of the associated Sync at the NW-TT TSN port
    int domainNumber = -1;           // association key of the Sync/Follow_Up pair
    int sequenceId = -1;
    uint64_t sourceClockIdentity = 0;
    int sourcePortNumber = -1;
    uint64_t syncFrameId = 0;        // M2-S0 frame id of the associated Sync (0: none)
    uint64_t followUpFrameId = 0;    // M2-S0 frame id of this Follow_Up (0: none)
    simtime_t linkDelay = -1;        // Lup added by the NW-TT (valid only)
    double rateRatioOut = 1;         // rr_out written to the TLV by the NW-TT
    simtime_t correctionIn = -1;     // cf_in (ps)
    simtime_t correctionOut = -1;    // cf1 (ps)
}
