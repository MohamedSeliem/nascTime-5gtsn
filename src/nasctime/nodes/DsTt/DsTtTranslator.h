//
//                  nascTime
//
// Authors: Mohamed Seliem (University College Cork), Afshin Zanganeh and How-Hang Liu
//          (Technical University of Dresden)
//
// This file is part of a software released under the license included in file
// "LICENSE.txt". Please read LICENSE.txt and README files before using it.
// The above files and the present reference are part of the software itself,
// and cannot be removed from it.
//

#ifndef __NASCTIME_DSTTTRANSLATOR_H_
#define __NASCTIME_DSTTTRANSLATOR_H_

#include <omnetpp.h>

#include "inet/common/packet/Packet.h"
#include "inet/linklayer/common/MacAddress.h"

#include <set>

using namespace omnetpp;
using namespace inet;

class DsTtTranslator : public cSimpleModule
{
  protected:
    int gptpEncapUdpPort;
    std::set<int> mappedPcpSet;
    // Gate IDs
    int tsnInGateId;
    int tsnOutGateId;
    int ueInGateId;
    int ueOutGateId;
    int gptpInGateId;

    // Signals
    simsignal_t tsnToUeSignal;
    simsignal_t ueToTsnSignal;
    simsignal_t packetDroppedSignal;
    simsignal_t residenceTimeSignal;

    // Counters
    long numTsnToUe = 0;
    long numUeToTsn = 0;
    long numDropped  = 0;
    long numGptpForwarded = 0;

  protected:
    virtual void initialize() override;
    virtual void handleMessage(cMessage *msg) override;
    virtual void finish() override;

    /** Forward frame from TSN device toward UE */
    virtual void forwardToUe(Packet *pkt);

    /** Forward frame from UE toward TSN device */
    virtual void forwardToTsn(Packet *pkt);
};

#endif
