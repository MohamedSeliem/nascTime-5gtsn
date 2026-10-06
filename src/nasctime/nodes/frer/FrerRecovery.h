//
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork),
//          Afshin Zanganeh and How-Hang Liu (Technical University of Dresden)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

#ifndef __SIMU5G_1_4_3_FRER_FRERRECOVERY_H_
#define __SIMU5G_1_4_3_FRER_FRERRECOVERY_H_

#include <omnetpp.h>
#include <map>
#include <set>
#include <vector>

#include "inet/common/packet/Packet.h"

using namespace omnetpp;
using namespace inet;

class FrerRecovery : public cSimpleModule
{
  public:
    enum RecoveryResult {
        ACCEPT,
        DUPLICATE,
        WINDOW_OVERRUN
    };

  protected:
    /** Per-stream state for the Vector Recovery Algorithm. */
    struct StreamState {
        uint16_t highestSeqSeen = 0;
        // Per-position: -1 = not yet seen, >=0 = sequence position accepted.
        // The stored DSCP is diagnostic only; any subsequent complete frame
        // at the same sequence position is a duplicate, even on the same leg.
        std::vector<int16_t> accepted;
        bool active = false;
        cMessage *timeoutMsg = nullptr;

        StreamState() = default;
        explicit StreamState(int windowSize)
            : accepted(windowSize, -1) {}
    };

    // --- Configuration ---
    std::set<int> frerStreamDscpSet;
    int replicaDscp;
    int windowSize;
    simtime_t windowTimeout;
    bool ethernetFramed = true;

    // --- Per-stream recovery state ---
    // Recovery state is scoped by source IPv4 address and FRER stream ID.
    // Separate DS-TTs start their sequence generators independently, so a
    // stream-ID-only key would cause equal sequence numbers from different
    // UEs to be eliminated as duplicates.
    std::map<uint64_t, StreamState> streams;
    std::map<cMessage *, uint64_t> timeoutKeys;

    // --- Gate IDs ---
    int inGateId;
    int outGateId;

    // --- Signals ---
    simsignal_t recoveredFromPrimarySignal;
    simsignal_t recoveredFromReplicaSignal;
    simsignal_t duplicatesDroppedSignal;
    simsignal_t windowOverrunsSignal;
    simsignal_t passedThroughSignal;

    // --- Counters ---
    long numRecoveredPrimary  = 0;
    long numRecoveredReplica  = 0;
    long numDuplicatesDropped = 0;
    long numWindowOverruns    = 0;
    long numPassedThrough     = 0;

  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    /**
     * IEEE 802.1CB Vector Recovery Algorithm (Annex C), extended to
     * track accepted DSCP per sequence-number position for correct
     * IP fragment handling.
     *
     * @param streamId  primary-stream DSCP
     * @param seqNum    IPv4 Identification value
     * @param dscp      actual DSCP of this packet (primary or replica)
     */
    virtual RecoveryResult recoverSequence(uint64_t recoveryKey,
                                           uint16_t seqNum,
                                           int dscp);

    virtual void resetStream(uint64_t recoveryKey);
    virtual void rescheduleTimeout(uint64_t recoveryKey);
};

#endif
