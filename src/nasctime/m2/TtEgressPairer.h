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
// M2B-4: mode TAS (opt-in; FIFO, the accepted M2-S1 behaviour above, is the default and unchanged).
// A time-aware shaper (IEEE 802.1Qbv) keeps one FIFO queue per traffic class and lets a frame of
// an open class overtake an older frame of a closed class, so the port-wide FIFO rule no longer
// holds for the MAC dequeue. In TAS mode:
//  - identity, uniqueness (orphan, ambiguous), duplicates, the order dequeue < start <= end per
//    record and the time-order checks are those of FIFO mode;
//  - a MAC dequeue may overtake older records of OTHER PCPs, never an older record of the same PCP
//    (the PCP determines the traffic class, so per-class FIFO order is enforced at PCP level);
//  - the port transmits one frame at a time in dequeue order: a transmission start must belong
//    to the earliest dequeued record not yet started, no transmission may start while another
//    is in progress (no overlap), and a transmission end must belong to the frame on the wire;
//  - verifyTransmitted() checks the transmitted frame's EtherType / PCP / VID against the record.
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
    long dequeueSeq = -1;        // M2B-4 TAS mode: position in the port's dequeue (transmission) sequence
};

class TtEgressPairer
{
  public:
    enum Event { DEQUEUE = 0, TX_START = 1, TX_END = 2 };
    enum Mode { FIFO = 0, TAS = 1 };
    static const char *eventName(Event e);

    std::deque<TtPortRecord> fifo;
    Mode mode = FIFO;                    // M2B-4: TAS only where explicitly configured
    long nextDequeueSeq = 0;

    // Adds a frame that entered the MAC FIFO; returns "" or an error description. A tree id
    // that is already pending is rejected (copies of one packet entering the same port
    // could not be told apart by their transmission events).
    std::string push(const TtPortRecord& record);

    // Sets the event time on the matching record; returns "" or an error description.
    // On success, index is the record's position in the FIFO (0 for TX_END in FIFO mode; in TAS
    // mode the caller removes the record at index after the transmission end).
    std::string match(Event event, long treeId, simtime_t t, size_t& index);

    // M2B-4 TAS mode: the transmitted frame must be the recorded one (EtherType, PCP, VID; the
    // payload hash is compared by the caller in both modes). Returns "" or an error description.
    std::string verifyTransmitted(const TtPortRecord& r, int etherType, int pcp, int vid) const;

  protected:
    static simtime_t& field(TtPortRecord& r, Event e);
    std::string matchTas(Event event, long treeId, simtime_t t, size_t& index);
};

} // namespace nasctime

#endif
