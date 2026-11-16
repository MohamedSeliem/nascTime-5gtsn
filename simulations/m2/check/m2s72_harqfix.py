#!/usr/bin/env python3
"""Test support (A-2 design increment): a source-faithful generator of Simu5G 1.8.1 DL H-ARQ MAC-log lines for N UEs,
INCLUDING the NACK / retransmission / discard paths that no preserved run contains (0 DL NACK in every run so far).
Used by test_m2s72_a2probe.py and, after approval, by the A-2 tests. Never reads or writes a run.

Every emitted text is copied from the 1.8.1 sources (commit 7477d26); the call order inside one gNB event follows the
code, each point cited:

  feedback event (LteMacBase::fromPhy -> LteHarqBufferTx::receiveHarqFeedback -> LteHarqUnitTx::pduFeedback):
    "<NOW> Mac::fromPhy: node <gnb> Received HARQ Feedback pkt"                           LteMacBase.cc:125
    "LteHarqBufferTx::receiveHarqFeedback - start"                                         LteHarqBufferTx.cc:175
    "LteHarqUnitTx::pduFeedback - Welcome!"                                                LteHarqUnitTx.cc:106
    ACK:     "\t pdu_ has been sent and received correctly "                               LteHarqUnitTx.cc:117
    NACK:    "<NOW> LteHarqUnitTx::pduFeedback H-ARQ process  <p> Codeword <c> PDU <id> set for RTX "   :141
    discard: "<NOW> LteHarqUnitTx::pduFeedback H-ARQ process  <p> Codeword <c> PDU <id> discarded (max retransmissions reached) : <maxHarqRtx>"   :126
    "H-ARQ TX: feedback received for process <p> codeword <c> result is ACK|NACK"           LteHarqBufferTx.cc:220
  TTI (LteMacEnb main loop): DL rtx scheduling only when a process awaits rtx (LteScheduler.cc:100-104):
    "<NOW> LteSchedulerEnbDl::rtxschedule --------------------::[ START RTX-SCHEDULE ]::--------------------"  :245
    "<NOW> LteSchedulerEnbDl::rtxschedule Cell:  <cell> Direction: DL"                      :246
    per UE "<NOW> LteSchedulerEnbDl::rtxschedule  UE: <node>"                               :270
    per process "<NOW> LteSchedulerEnbDl::rtxschedule process <p>"                          :284
      not BUFFERED: "<NOW> LteSchedulerEnbDl::rtxschedule detected Acid: <p> in status <s>"    :288 (status enum LteCommonEnum.msg:220)
      BUFFERED:     "<NOW> LteSchedulerEnbDl::rtxschedule detected RTX Acid: <p>"          :292
        "<NOW>LteSchedulerEnbDl::rtxAcid - Node [<gnb>], User[<node>],  Codeword [<c>]  of [<n>] , ACID [<p>] "   :108
        "<NOW> LteSchedulerEnbDl::rtxAcid HARQ Process <p>  codeword  <c> marking for retransmission "          :213
        "H-ARQ TX: process <p> has been selected for retransmission"                       LteHarqBufferTx.cc:109
    new data: grant lines, macPduMake, "H-ARQ TX: new pdu (id <id> ) inserted into process <p> codeword id: <c> for node with id <n>"  :131
    every transmission: "\t H-ARQ TX: pdu (id <id> ) extracted from process <p> codeword <c> for node with id <n>"  :242
  UE k: "H-ARQ RX: new PDU (id <id> ) inserted into process <p>" (LteHarqBufferRx.cc:63);
        "H-ARQ RX: feedback sent to TX process <p> Codeword  <c> of node with id <gnb> result: ACK|NACK" (:78)
Timing: gNB tx at TTI t; UE reception t + 1 slot (PhyBase.cc:120, :214); UE feedback t + 1 + d_ue; gNB receipt one
slot later. A NACKed unit is BUFFERED (LteHarqUnitTx.cc:140), retransmitted in the next TTI with a scheduled rtx;
after maxHarqRtx + 1 transmissions a NACK discards it (:124-136). Same-time order of events in a TTI: feedback events
first, then the main loop (one admissible order; the tools under test must not depend on it)."""
S, MS = 10 ** 12, 10 ** 9
GNB = "M2S72Bridge.gnb1.cellularNic.mac"
STATUS = {"BUFFERED": 0, "WAITING": 1, "EMPTY": 2, "SELECTED": 3}


def ts(t):
    return f"{t // S}.{t % S:012d}"


def now(t):
    """OMNeT++ prints SimTime in its shortest decimal form ('1.004', '2')"""
    s = f"{t // S}.{t % S:012d}".rstrip("0").rstrip(".")
    return s


def ue_mod(k):
    return f"M2S72Bridge.ue[{k}].cellularNic.nrMac"


def make(n_ue, ttis, sched, nack=(), d_ue=2, nproc=16, t0=1000, max_rtx=3, gnb_id=1, pid0=800, fb_first=True,
         ue_log=True):
    """returns (lines, node, truth). sched(tti) -> UEs given a NEW DL PDU (scheduling order); nack: {(pid, attempt)}
    answered NACK by the UE; truth: list of dicts per gNB feedback line, in emission order: {t, node, pid, p, cw,
    res, ntx, outcome: ack | rtx | discard}"""
    node = {k: 2049 + k for k in range(n_ue)}
    lines, seq = [], [0]
    procs = {k: [None] * nproc for k in range(n_ue)}          # unit: {pid, ntx, st}
    due, pid, truth = {}, [pid0], []
    nack = set(nack)

    def emit(t, mod, msg):
        seq[0] += 1
        lines.append((t, 0, seq[0], mod, msg))

    def emit_fb(t, mod, msg):                          # feedback events: before or after the TTI's main loop (fb_first)
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
            emit_fb(t, GNB, f"{now(t)} Mac::fromPhy: node {gnb_id} Received HARQ Feedback pkt")
            emit_fb(t, GNB, "LteHarqBufferTx::receiveHarqFeedback - start")
            emit_fb(t, GNB, "LteHarqUnitTx::pduFeedback - Welcome!")
            if res == "ACK":
                emit_fb(t, GNB, "\t pdu_ has been sent and received correctly ")
                procs[k][p] = None
                outcome = "ack"
            elif u["ntx"] == max_rtx + 1:
                emit_fb(t, GNB, f"{now(t)} LteHarqUnitTx::pduFeedback H-ARQ process  {p} Codeword 0 PDU {x} discarded (max retransmissions reached) : {max_rtx}")
                procs[k][p] = None
                outcome = "discard"
            else:
                emit_fb(t, GNB, f"{now(t)} LteHarqUnitTx::pduFeedback H-ARQ process  {p} Codeword 0 PDU {x} set for RTX ")
                u["st"] = "BUFFERED"
                outcome = "rtx"
            emit_fb(t, GNB, f"H-ARQ TX: feedback received for process {p} codeword 0 result is {res}")
            truth.append({"t": t, "node": node[k], "pid": x, "p": p, "cw": 0, "res": res, "ntx": u["ntx"], "outcome": outcome})
        at(tti + 2 + d_ue, fb_gnb)

    for tti in range(t0, t0 + ttis + d_ue + 4):
        t = tti * MS
        if fb_first or tti >= t0 + ttis:
            for f in due.pop(tti, []):
                f(t)
        if tti >= t0 + ttis:
            continue
        emit(t, GNB, "ENB MAIN LOOP -----")
        rtx = {}
        if any(u and u["st"] == "BUFFERED" for k in range(n_ue) for u in procs[k]):
            emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxschedule --------------------::[ START RTX-SCHEDULE ]::--------------------")
            emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxschedule Cell:  {gnb_id} Direction: DL")
            for k in range(n_ue):
                emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxschedule  UE: {node[k]}")
                for p in range(nproc):
                    emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxschedule process {p}")
                    u = procs[k][p]
                    if u is None or u["st"] != "BUFFERED":
                        st = "EMPTY" if u is None else u["st"]
                        emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxschedule detected Acid: {p} in status {STATUS[st]}")
                        continue
                    emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxschedule detected RTX Acid: {p}")
                    emit(t, GNB, f"{now(t)}LteSchedulerEnbDl::rtxAcid - Node [{gnb_id}], User[{node[k]}],  Codeword [0]  of [1] , ACID [{p}] ")
                    emit(t, GNB, f"{now(t)} LteSchedulerEnbDl::rtxAcid HARQ Process {p}  codeword  0 marking for retransmission ")
                    emit(t, GNB, f"H-ARQ TX: process {p} has been selected for retransmission")
                    u["st"] = "SELECTED"
                    rtx[k] = p
                    break                                      # one codeword per UE per TTI: allocatedCws_ == codewords
            emit(t, GNB, "    LteSchedulerEnbDl::rtxschedule --------------------::[  END RTX-SCHEDULE  ]::-------------------- ")
        emit(t, GNB, "= DOWNLINK =")
        new = [k for k in sched(tti) if k < n_ue and k not in rtx]
        for k in new:
            emit(t, GNB, f"QoSAwareScheduler::Grant cid=MacCid(nodeId={node[k]}, lcid=1) limit=10000 granted=1400B")
        emit(t, GNB, "= END DOWNLINK =")
        sent = []
        for k in new:
            p = next((i for i, u in enumerate(procs[k]) if u is None), None)
            if p is None:
                continue
            pid[0] += 1
            procs[k][p] = {"pid": pid[0], "ntx": 0, "st": "SELECTED"}
            emit(t, GNB, "START LteMacEnb::macPduMake")
            emit(t, GNB, "PDU Maker created PDU: (1400 B) containing 1 SDUs")
            emit(t, GNB, f"H-ARQ TX: new pdu (id {pid[0]} ) inserted into process {p} codeword id: 0 for node with id {node[k]}")
            emit(t, GNB, "END LteMacEnb::macPduMake")
            sent.append((k, p))
        for k, p in list(rtx.items()) + sent:                   # sendSelectedDown: every transmission
            u = procs[k][p]
            u["ntx"] += 1
            u["st"] = "WAITING"
            emit(t, GNB, f"LteHarqUnitTx::extractPdu - ndi set to {'true' if u['ntx'] == 1 else 'false'}")
            emit(t, GNB, f"\t H-ARQ TX: pdu (id {u['pid']} ) extracted from process {p} codeword 0 for node with id {node[k]}")
            air(k, p, u["pid"], u["ntx"], tti)
        if not fb_first:
            for f in due.pop(tti, []):
                f(t)
    lines.sort()
    return [f"{ts(t)}|{m}|{msg}\n" for t, _, _, m, msg in lines], node, truth
