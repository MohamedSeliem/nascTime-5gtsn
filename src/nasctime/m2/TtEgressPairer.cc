//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#include "TtEgressPairer.h"

namespace nasctime {

const char *TtEgressPairer::eventName(Event e)
{
    switch (e) {
        case DEQUEUE: return "MAC dequeue";
        case TX_START: return "transmissionStarted";
        case TX_END: return "transmissionEnded";
    }
    return "?";
}

simtime_t& TtEgressPairer::field(TtPortRecord& r, Event e)
{
    switch (e) {
        case DEQUEUE: return r.tDequeue;
        case TX_START: return r.tTxStart;
        default: return r.tTxEnd;
    }
}

std::string TtEgressPairer::push(const TtPortRecord& record)
{
    for (const auto& r : fifo)
        if (r.treeId == record.treeId)
            return "ambiguous enqueue of tree id " + std::to_string(record.treeId) + ": a pending record already has this tree id";
    fifo.push_back(record);
    return "";
}

std::string TtEgressPairer::match(Event event, long treeId, simtime_t t, size_t& index)
{
    if (mode == TAS)
        return matchTas(event, treeId, t, index);       // M2B-4; the FIFO rules below are unchanged
    std::string what = std::string(eventName(event)) + " of tree id " + std::to_string(treeId);
    // uniqueness: exactly one pending record with this tree id
    size_t found = fifo.size(), count = 0;
    for (size_t i = 0; i < fifo.size(); i++)
        if (fifo[i].treeId == treeId) {
            found = i;
            count++;
        }
    if (count == 0)
        return "orphan " + what + ": no pending record";
    if (count > 1)
        return "ambiguous " + what + ": " + std::to_string(count) + " pending records share the tree id";
    TtPortRecord& r = fifo[found];
    if (field(r, event) >= 0)
        return "duplicate " + what + ": the record already has this event";
    // FIFO: the matched record must be the oldest one still lacking this event
    for (size_t i = 0; i < found; i++)
        if (field(fifo[i], event) < 0)
            return "out-of-order " + what + ": an older record (tree id " + std::to_string(fifo[i].treeId) + ") lacks this event";
    // per-record order: dequeue before start before end
    if (event == TX_START && r.tDequeue < 0)
        return "order violation for " + what + ": no MAC dequeue yet";
    if (event == TX_END && r.tTxStart < 0)
        return "order violation for " + what + ": no transmission start yet";
    if (event == TX_END && found != 0)
        return "order violation for " + what + ": transmission end of a record that is not at the head of the FIFO";
    if (t < r.tSlot || (event != DEQUEUE && t < r.tDequeue) || (event == TX_END && t < r.tTxStart))
        return "time order violation for " + what;
    field(r, event) = t;
    index = found;
    return "";
}

// M2B-4 TAS mode (see the header): cross-PCP overtaking at the MAC dequeue is valid; per-PCP
// FIFO order, the dequeue-ordered transmission sequence and single-transmission occupancy of the
// port are enforced; every other rule is that of FIFO mode.
std::string TtEgressPairer::matchTas(Event event, long treeId, simtime_t t, size_t& index)
{
    std::string what = std::string(eventName(event)) + " of tree id " + std::to_string(treeId);
    size_t found = fifo.size(), count = 0;
    for (size_t i = 0; i < fifo.size(); i++)
        if (fifo[i].treeId == treeId) {
            found = i;
            count++;
        }
    if (count == 0)
        return "orphan " + what + ": no pending record";
    if (count > 1)
        return "ambiguous " + what + ": " + std::to_string(count) + " pending records share the tree id";
    TtPortRecord& r = fifo[found];
    if (field(r, event) >= 0)
        return "duplicate " + what + ": the record already has this event";
    if (event == TX_START && r.tDequeue < 0)
        return "order violation for " + what + ": no MAC dequeue yet";
    if (event == TX_END && r.tTxStart < 0)
        return "order violation for " + what + ": no transmission start yet";
    if (t < r.tSlot || (event != DEQUEUE && t < r.tDequeue) || (event == TX_END && t < r.tTxStart))
        return "time order violation for " + what;
    if (event == DEQUEUE) {
        // per-class FIFO: no older record of the same PCP may still wait
        for (size_t i = 0; i < found; i++)
            if (fifo[i].pcp == r.pcp && fifo[i].tDequeue < 0)
                return "out-of-order " + what + " within PCP " + std::to_string(r.pcp) + ": an older record of the same PCP (tree id "
                        + std::to_string(fifo[i].treeId) + ") lacks this event";
    }
    else {
        for (size_t i = 0; i < fifo.size(); i++) {
            TtPortRecord& o = fifo[i];
            if (i == found)
                continue;
            if (event == TX_START && o.tTxStart >= 0 && o.tTxEnd < 0)
                return "overlapping transmission: " + what + " while tree id " + std::to_string(o.treeId) + " is still being transmitted";
            if (o.dequeueSeq >= 0 && o.dequeueSeq < r.dequeueSeq && field(o, event) < 0)
                return "out-of-sequence " + what + ": tree id " + std::to_string(o.treeId) + " was dequeued earlier and lacks this event";
        }
    }
    field(r, event) = t;
    if (event == DEQUEUE)
        r.dequeueSeq = nextDequeueSeq++;
    index = found;
    return "";
}

std::string TtEgressPairer::verifyTransmitted(const TtPortRecord& r, int etherType, int pcp, int vid) const
{
    if (etherType != r.etherType || pcp != r.pcp || vid != r.vid)
        return "identity of the transmitted frame (EtherType " + std::to_string(etherType) + ", PCP " + std::to_string(pcp) + ", VID "
                + std::to_string(vid) + ") differs from the record of tree id " + std::to_string(r.treeId) + " (EtherType "
                + std::to_string(r.etherType) + ", PCP " + std::to_string(r.pcp) + ", VID " + std::to_string(r.vid) + ")";
    return "";
}

} // namespace nasctime
