//
//                  nascTime
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
//

#ifndef __NASCTIME_M2_TTEGRESSPAIRER_H
#define __NASCTIME_M2_TTEGRESSPAIRER_H

#include <deque>
#include <string>

#include <omnetpp.h>

namespace nasctime {

using omnetpp::simtime_t;

//
// M2-S1: pairs the transmission events of an Ethernet port (MAC dequeue, transmission
// start, transmission end) with the frames that entered the port's MAC FIFO through the
// measurement-layer slot. Pure logic, no simulation dependencies (self-tested).
//
// A frame is identified by the OMNeT++ tree id of its packet (kept by every copy).
// Every event must match exactly one pending record (no orphan, no ambiguity even if
// copies of one packet share a tree id), be the first record still lacking that event
// (FIFO order), and follow the order dequeue < start <= end per record. The end of
// transmission must belong to the record at the head of the FIFO. Any violation is
// reported as an error string; the caller stops the simulation.
//
struct TtPortRecord
{
    long treeId = -1;
    simtime_t tSlot = -1;        // entered the MAC FIFO (measurement-layer TX slot)
    simtime_t tDequeue = -1;     // MAC outbound emitter (packetSentToLower)
    simtime_t tTxStart = -1;     // transmitter transmissionStarted
    simtime_t tTxEnd = -1;       // transmitter transmissionEnded (last bit sent)
    bool tagged = false;         // identity (frame id, ingress time, translator) known
    bool tagOnWire = false;      // the transmitted frame is expected to carry the tag
    uint64_t frameId = 0;
    simtime_t ingressTime = -1;
    int ingressTtId = -1;
    std::string hash;            // payload hash at the slot
    std::string txHash;          // payload hash of the transmitted packet
    int etherType = -1, pcp = -1, vid = -1;
    long payloadLength = 0;
    std::string note;
};

class TtEgressPairer
{
  public:
    enum Event { DEQUEUE = 0, TX_START = 1, TX_END = 2 };
    static const char *eventName(Event e);

    std::deque<TtPortRecord> fifo;

    void push(const TtPortRecord& record) { fifo.push_back(record); }

    // Sets the event time on the matching record; returns "" or an error description.
    // On success, index is the record's position in the FIFO (0 for TX_END).
    std::string match(Event event, long treeId, simtime_t t, size_t& index);

  protected:
    static simtime_t& field(TtPortRecord& r, Event e);
};

} // namespace nasctime

#endif
