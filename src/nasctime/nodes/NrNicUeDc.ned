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

package nasctime.nodes;

import simu5g.stack.NrNicUe;
import simu5g.stack.mac.ILteMac;
import simu5g.stack.phy.ILtePhy;
import simu5g.stack.phy.channelmodel.ILteChannelModel;
import simu5g.stack.phy.feedback.LteDlFeedbackGenerator;
import simu5g.stack.pdcp.UpperMux;
import simu5g.stack.rlc.RlcMux;
import simu5g.stack.sdap.INrSdap;
import nasctime.nodes.frer.NrDcMux;

module NrNicUeDC extends NrNicUe
{
    parameters:
        bool dualConnEnabled = default(false);
        string nrChannelModel2Type = default("NrChannelModel_3GPP38_901");

        nrPhy2.channelModelModule = "^.nrChannelModel2[0]";
        nrPhy2.feedbackGeneratorModule = "^.nrDlFbGen2";

        // FIX (was broken): the third HandoverController instance is
        // enabled via Rrc's own hasNrHandoverController2 flag, not by
        // trying to set rrc.nrHandoverController2.typename from outside
        // -- that submodule must already be declared inside Rrc.ned
        // itself (patched separately) for this to mean anything.
        rrc.hasNrHandoverController2 = dualConnEnabled;
        rrc.nrHandoverController2.isNr = true;
        rrc.nrHandoverController2.isDcSecondary = true;
        rrc.nrHandoverController2.macModule = "^.^.nrMac2";
        rrc.nrHandoverController2.feedbackGeneratorModule = "^.^.nrDlFbGen2";
        rrc.nrHandoverController2.otherHandoverControllerModule = "^.nrHandoverController";

        // Pairs nrPhy2 with nrHandoverController2 instead of the primary
        // nrHandoverController -- confirmed sufficient via
        // LtePhyUe.ned's handoverControllerModule param, no C++ change needed.
        nrPhy2.handoverControllerModule = "^.rrc.nrHandoverController2";

    gates:
        input nrRadioIn2 @directIn @loose;

    submodules:
        nrDcMux: NrDcMux if dualConnEnabled {
            @display("p=439,230");
        }
        sdap2: <default("NrSdap")> like INrSdap if dualConnEnabled {
            pdcpMuxModule = "^.pdcpMux2";
            @display("p=440,155");
        }
        pdcpMux2: UpperMux if dualConnEnabled {
            isNR = true;
            @display("p=440,350");
        }
        nrRlcMux2: RlcMux if dualConnEnabled {
            @display("p=440,430");
        }
        nrMac2: <default("NrMacUe")> like ILteMac if dualConnEnabled {
            @display("p=440,510");
        }
        nrPhy2: <default("NrPhyUe")> like ILtePhy if dualConnEnabled {
            @display("p=440,600");
        }
        nrChannelModel2[numNrCarriers]: <nrChannelModel2Type> like ILteChannelModel if dualConnEnabled {
            @display("p=200,400");
        }
        nrDlFbGen2: LteDlFeedbackGenerator if dualConnEnabled {
            @display("p=200,300");
            phyModule = "^.nrPhy2";
        }

    connections:
        // Confirmed against NrDcMux's real gate declarations
        // (inout upper/primary/secondary) -- $i/$o referencing verified.
        ip2nic.stackOut --> { @reconnect; } --> nrDcMux.upper$i if dualConnEnabled && hasSdap;
        nrDcMux.upper$o --> { @reconnect; } --> ip2nic.stackIn if dualConnEnabled && hasSdap;

        nrDcMux.primary$o --> sdap.upperLayerIn if dualConnEnabled;
        nrDcMux.primary$i <-- sdap.upperLayerOut if dualConnEnabled;
        nrDcMux.secondary$o --> sdap2.upperLayerIn if dualConnEnabled;
        nrDcMux.secondary$i <-- sdap2.upperLayerOut if dualConnEnabled;

        sdap2.pdcpOut --> pdcpMux2.upperLayerIn if dualConnEnabled;
        pdcpMux2.upperLayerOut --> sdap2.pdcpIn if dualConnEnabled;

        nrRlcMux2.macOut --> nrMac2.upperLayerIn if dualConnEnabled;
        nrRlcMux2.macIn <-- nrMac2.upperLayerOut if dualConnEnabled;
        nrMac2.phyOut --> nrPhy2.upperGateIn if dualConnEnabled;
        nrMac2.phyIn <-- nrPhy2.upperGateOut if dualConnEnabled;
        nrRadioIn2 --> nrPhy2.radioIn if dualConnEnabled;
}
