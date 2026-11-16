#!/usr/bin/env python3
"""Test support for A-2.1 (results/M2-S7.2a-a2d2-f1-root-cause.md rev. 2, §9 T-gen-faithful): a corrected generator of
Simu5G 1.8.1 DL H-ARQ MAC-log lines for N UEs. The frozen generator m2s72_harqfix.py stays unchanged (it is part of the
frozen A-2 test base); this module corrects its three source-faithfulness gaps found with the first real NACK run:

  1. identifier namespace: the unit's NACK / discard line prints pdu_->getId() of the unit's inet::Packet, a cMessage
     id (LteHarqUnitTx.cc:127, :142; LteHarqUnitTx.h:46; omnetpp cmessage.h:583), NOT the MAC PDU id printed by the
     insert / extract / UE lines (LteMacPdu::getId(), LteMacPdu.msg:46, :134). One handle per PDU lifecycle (pdu_ is
     set at insertPdu, :56, sent as dup() at every transmission, :99, deleted at resetUnit, :254-261); handles come
     from a separate counter (h0) and never equal a MAC id of the same log.
  2. log context: the DL scheduler is the submodule mac.schedulerDl (LteMacEnb.ned:104), a cSimpleModule; its EV
     lines (rtxschedule / rtxAcid, LteSchedulerEnbDl.cc:108, :245-322) are filtered by ITS log level
     (clog.cc defaultComponentLogPredicate). They are emitted under module <gnb>.mac.schedulerDl only with
     sched_log=True; with the runs' configuration (**.cmdenv-log-level = off) they are absent. "H-ARQ TX: process p
     has been selected for retransmission" (LteHarqBufferTx.cc:109, a non-component) is always logged under the MAC.
  3. timing: feedback events are processed after the TTI's main loop (fb_first=False, the order observed on the real
     A2-V1 log: NACK at 366 ms, retransmission at 367 ms), so a retransmission follows its NACK one TTI later.
Also emitted: the main-loop markers "-----ENB MAIN LOOP -----" / "--- END ENB MAIN LOOP ---" (LteMacEnb.cc:767, :841).
Never reads or writes a run."""
S, MS = 10 ** 12, 10 ** 9
GNB = "M2S72Bridge.gnb1.cellularNic.mac"
SCHED = GNB + ".schedulerDl"
STATUS = {"BUFFERED": 0, "WAITING": 1, "EMPTY": 2, "SELECTED": 3}
ML_START, ML_END = "-----ENB MAIN LOOP -----", "--- END ENB MAIN LOOP ---"


def ts(t):
    return f"{t // S}.{t % S:012d}"


def now(t):
    return f"{t // S}.{t % S:012d}".rstrip("0").rstrip(".")


def ue_mod(k):
    return f"M2S72Bridge.ue[{k}].cellularNic.nrMac"


def make(n_ue, ttis, sched, nack=(), d_ue=3, nproc=16, t0=1000, max_rtx=3, gnb_id=1, pid0=800, h0=50000,
         fb_first=False, ue_log=True, sched_log=False, markers=True, tail=None):
    """returns (lines, node, truth). sched(tti) -> UEs given a NEW DL PDU; nack: {(pid, attempt)} answered NACK by the
    UE; truth: per gNB feedback line, in emission order: {t, node, pid, handle, p, cw, res, ntx, outcome}.
    tail: TTIs simulated after the last new PDU (default d_ue + 4: every feedback of a first transmission arrives)."""
    node = {k: 2049 + k for k in range(n_ue)}
    lines, seq = [], [0]
    procs = {k: [None] * nproc for k in range(n_ue)}
    due, pid, hid, truth = {}, [pid0], [h0], []
    nack = set(nack)

    def emit(t, mod, msg):
        seq[0] += 1
        lines.append((t, 0, seq[0], mod, msg))

    def at(tti, f):
        due.setdefault(tti, []).append(f)

    def air(k, p, x, attempt, tti):
        res = "NACK" if (x, attempt) in nack else "ACK"
        if ue_log:
            at(tti + 1, lambda t: emit(t, ue_mod(k), f"H-ARQ RX: new PDU (id {x} ) inserted into process {p}"))
            at(tti + 1 + d_ue, lambda t: emit(t, ue_mod(k), f"H-ARQ RX: feedback sent to TX process {p} Codeword  0 of node with id {gnb_id} result: {res}"))

        def fb_gnb(t):
            u = procs[k][p]
            h = u["handle"]
            emit(t, GNB, f"{now(t)} Mac::fromPhy: node {gnb_id} Received HARQ Feedback pkt")
            emit(t, GNB, "LteHarqBufferTx::receiveHarqFeedback - start")
            emit(t, GNB, "LteHarqUnitTx::pduFeedback - Welcome!")
            if res == "ACK":
                emit(t, GNB, "\t pdu_ has been sent and received correctly ")
                procs[k][p] = None
                outcome = "ack"
            elif u["ntx"] == max_rtx + 1:
                emit(t, GNB, f"{now(t)} LteHarqUnitTx::pduFeedback H-ARQ process  {p} Codeword 0 PDU {h} discarded (max retransmissions reached) : {max_rtx}")
                procs[k][p] = None
                outcome = "discard"
            else:
                emit(t, GNB, f"{now(t)} LteHarqUnitTx::pduFeedback H-ARQ process  {p} Codeword 0 PDU {h} set for RTX ")
                u["st"] = "BUFFERED"
                outcome = "rtx"
            emit(t, GNB, f"H-ARQ TX: feedback received for process {p} codeword 0 result is {res}")
            truth.append({"t": t, "node": node[k], "pid": x, "handle": h, "p": p, "cw": 0, "res": res, "ntx": u["ntx"],
                          "outcome": outcome})
        at(tti + 2 + d_ue, fb_gnb)

    end = t0 + ttis + (d_ue + 4 if tail is None else tail)
    for tti in range(t0, end):
        t = tti * MS
        if fb_first:
            for f in due.pop(tti, []):
                f(t)
        if markers:
            emit(t, GNB, ML_START)
        rtx = {}
        if any(u and u["st"] == "BUFFERED" for k in range(n_ue) for u in procs[k]):
            if sched_log:
                emit(t, SCHED, f"{now(t)} LteSchedulerEnbDl::rtxschedule --------------------::[ START RTX-SCHEDULE ]::--------------------")
                emit(t, SCHED, f"{now(t)} LteSchedulerEnbDl::rtxschedule Cell:  {gnb_id} Direction: DL")
            for k in range(n_ue):
                if sched_log:
                    emit(t, SCHED, f"{now(t)} LteSchedulerEnbDl::rtxschedule  UE: {node[k]}")
                for p in range(nproc):
                    u = procs[k][p]
                    if u is None or u["st"] != "BUFFERED":
                        continue
                    if sched_log:
                        emit(t, SCHED, f"{now(t)} LteSchedulerEnbDl::rtxschedule detected RTX Acid: {p}")
                        emit(t, SCHED, f"{now(t)}LteSchedulerEnbDl::rtxAcid - Node [{gnb_id}], User[{node[k]}],  Codeword [0]  of [1] , ACID [{p}] ")
                    emit(t, GNB, f"H-ARQ TX: process {p} has been selected for retransmission")
                    u["st"] = "SELECTED"
                    rtx[k] = p
                    break                                      # one codeword per UE per TTI
            if sched_log:
                emit(t, SCHED, "    LteSchedulerEnbDl::rtxschedule --------------------::[  END RTX-SCHEDULE  ]::-------------------- ")
        emit(t, GNB, "= DOWNLINK =")
        new = [k for k in sched(tti) if k < n_ue and k not in rtx] if tti < t0 + ttis else []
        for k in new:
            emit(t, GNB, f"QoSAwareScheduler::Grant cid=MacCid(nodeId={node[k]}, lcid=1) limit=10000 granted=1400B")
        emit(t, GNB, "= END DOWNLINK =")
        sent = []
        for k in new:
            p = next((i for i, u in enumerate(procs[k]) if u is None), None)
            if p is None:
                continue
            pid[0] += 1
            hid[0] += 1
            procs[k][p] = {"pid": pid[0], "handle": hid[0], "ntx": 0, "st": "SELECTED"}
            emit(t, GNB, "START LteMacEnb::macPduMake")
            emit(t, GNB, f"H-ARQ TX: new pdu (id {pid[0]} ) inserted into process {p} codeword id: 0 for node with id {node[k]}")
            emit(t, GNB, "END LteMacEnb::macPduMake")
            sent.append((k, p))
        for k, p in list(rtx.items()) + sent:
            u = procs[k][p]
            u["ntx"] += 1
            u["st"] = "WAITING"
            emit(t, GNB, f"LteHarqUnitTx::extractPdu - ndi set to {'true' if u['ntx'] == 1 else 'false'}")
            emit(t, GNB, f"\t H-ARQ TX: pdu (id {u['pid']} ) extracted from process {p} codeword 0 for node with id {node[k]}")
            air(k, p, u["pid"], u["ntx"], tti)
        if markers:
            emit(t, GNB, ML_END)
        if not fb_first:
            for f in due.pop(tti, []):
                f(t)
    lines.sort()
    return [f"{ts(t)}|{m}|{msg}\n" for t, _, _, m, msg in lines], node, truth
