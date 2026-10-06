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

#ifndef __SIMU5G_1_5_0_NRDCMUX_H_
#define __SIMU5G_1_5_0_NRDCMUX_H_

#include <omnetpp.h>
#include <set>

namespace simu5g { class Binder; }

using namespace omnetpp;

/**
 * TODO - Generated class
 */
class NrDcMux : public cSimpleModule
{
    protected:
      int upperInId, upperOutId;
      int primaryInId, primaryOutId;
      int secondaryInId, secondaryOutId;
      std::set<int> secondaryDscps_;
      std::set<int> primedSecondaryUes_;
      simu5g::Binder *binder_ = nullptr;

      virtual void initialize() override;
      virtual void handleMessage(cMessage *msg) override;
      bool useSecondaryLeg(cMessage *msg) const;
      void selectSecondaryDestination(cMessage *msg);
};


#endif
