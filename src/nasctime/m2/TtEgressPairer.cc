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

} // namespace nasctime
