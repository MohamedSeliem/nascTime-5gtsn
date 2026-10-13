// M2-S3: runs INET 4.7.0's own GptpPacketSerializer (unmodified, from libINET) on synthetic
// Follow_Up values, so that the oracle's Python encoders/decoders can be compared with the
// real INET code instead of with a reading of it. Prints one line per vector:
//   cf   <in ps> <correctionField bytes 8..15 as hex> <deserialized ps>
//   ts   <in ps> <preciseOriginTimestamp bytes 34..43 as hex> <deserialized ps>
//   cfraw <correctionField wire value, int64> <deserialized ps>   (wire values with a sub-ns fraction)
//   rr   <in rateRatio %.17g> <cumulativeScaledRateOffset bytes 54..57 as int32> <deserialized rateRatio %.17g>
// Simulation-time scale: 10^-12 s (OMNeT++ default, as in all M1/M2 runs). No simulation is run.
#include <cstdio>
#include <cinttypes>
#include <vector>
#include <omnetpp/onstartup.h>
#include "inet/common/INETDefs.h"
#include "inet/common/packet/chunk/Chunk.h"
#include "inet/common/MemoryInputStream.h"
#include "inet/common/MemoryOutputStream.h"
#include "inet/linklayer/ieee8021as/GptpPacket_m.h"

using namespace inet;

static std::vector<uint8_t> ser(const Ptr<const Chunk>& c)
{
    MemoryOutputStream s;
    Chunk::serialize(s, c);
    return s.getData();
}

static Ptr<GptpFollowUp> deser(const std::vector<uint8_t>& d)
{
    MemoryInputStream s(d);
    return dynamicPtrCast<GptpFollowUp>(Chunk::deserialize(s, typeid(GptpFollowUp)));
}

static void hex(const std::vector<uint8_t>& d, int from, int n)
{
    for (int i = from; i < from + n; i++)
        printf("%02x", d[i]);
}

static clocktime_t fromPs(int64_t x) { return SIMTIME_AS_CLOCKTIME(SimTime::fromRaw(x)); }
static int64_t raw(clocktime_t t) { return CLOCKTIME_AS_SIMTIME(t).raw(); }

int main()
{
    // run the EXECUTE_ON_STARTUP blocks (Register_Serializer etc.), as opp_run does at startup
    omnetpp::CodeFragments::executeAll(omnetpp::CodeFragments::STARTUP);
    // and INET's pre-network-setup blocks, where Register_Serializer registers the gPTP serializer
    inet::CodeFragment::executeAll(omnetpp::LF_PRE_NETWORK_SETUP);
    SimTime::setScaleExp(-12);
    const int64_t cfs[] = {0, 1, 499, 500, 999, 1000, 1001, 1500, 50000, 4999114800LL, 5001234567LL,
                           5000050100LL, 123456789012LL, -1500};
    for (int64_t v : cfs) {
        auto fu = makeShared<GptpFollowUp>();
        fu->setCorrectionField(fromPs(v));
        auto d = ser(fu);
        printf("cf %" PRId64 " ", v); hex(d, 8, 8);
        printf(" %" PRId64 "\n", raw(deser(d)->getCorrectionField()));
    }
    const int64_t raws[] = {0x8000LL, 0x0001LL, 0x0041LL, 0x0042LL, 0xFFFFLL, (4999114LL << 16) | 0xCCCD,
                            (50LL << 16) | 0x4000, -0x8000LL, -(1LL << 16)};
    for (int64_t v : raws) {
        auto d = ser(makeShared<GptpFollowUp>());
        for (int i = 0; i < 8; i++)
            d[8 + i] = (uint8_t)((uint64_t)v >> (56 - 8 * i));
        printf("cfraw %" PRId64 " %" PRId64 "\n", v, raw(deser(d)->getCorrectionField()));
    }
    const int64_t tss[] = {0, 1, 999, 1000, 1001, 125000000000LL, 125000000200LL, 1000000000000LL,
                           1234567890123456LL};
    for (int64_t v : tss) {
        auto fu = makeShared<GptpFollowUp>();
        fu->setPreciseOriginTimestamp(fromPs(v));
        auto d = ser(fu);
        printf("ts %" PRId64 " ", v); hex(d, 34, 10);
        printf(" %" PRId64 "\n", raw(deser(d)->getPreciseOriginTimestamp()));
    }
    const double two41 = (double)((uint64_t)1 << 41);
    const double rrs[] = {1.0, 1.0 + 1e-4, 1.0 - 1e-4, 1.0 + 1.0 / two41, 1.0 - 1.0 / two41,
                          1.0 + 0.5 / two41, 1.0 - 0.5 / two41, 1.0 + 1e-9, 1.0 - 1e-9};
    for (double v : rrs) {
        auto fu = makeShared<GptpFollowUp>();
        fu->getFollowUpInformationTLVForUpdate().setRateRatio(v);
        auto d = ser(fu);
        int32_t x = (int32_t)(((uint32_t)d[54] << 24) | ((uint32_t)d[55] << 16) | ((uint32_t)d[56] << 8) | d[57]);
        printf("rr %.17g %d %.17g\n", v, x, deser(d)->getFollowUpInformationTLV().getRateRatio());
    }
    return 0;
}
