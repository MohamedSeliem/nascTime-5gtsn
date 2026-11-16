#!/usr/bin/env python3
"""Stage 5 N = 2 increment: contract, fixture and mutation tests of the multi-UE checks (m2s72_harqx.py,
check_m2s72_s5n2.py), the identity of the observation-only change to m2s72_peru.attribute_feedback (trace), and the
runner's smoke-n2 lifecycle with stub tools. No simulation, no raw output, no OMNeT++.

The H-ARQ fixtures come from a small generator that reproduces the Simu5G 1.8.1 behaviour the checks rely on, each
point cited to the source: one H-ARQ TX buffer per UE (LteMacBase.h:36), the lowest free process for a new PDU
(LteHarqBufferTx.cc:137), a NACKed unit kept for retransmission (LteHarqUnitTx.cc:137-148), retransmission without an
insert line (LteHarqBufferTx.cc:109, :242), the exact gNB and UE line texts (LteHarqBufferTx.cc:131, :220, :242;
LteHarqBufferRx.cc:63, :78), the MAC PDU id kept across the air (LteMacPdu.msg:134, :143), and an air frame of one
slot delivered at its end (PhyBase.cc:120, :214)."""
import gzip
import importlib.util
import json
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import check_m2s72_s5n2 as N2  # noqa: E402
import m2s72_harqx as H  # noqa: E402
import m2s72_peru as P  # noqa: E402
import m2s72_peru_adapter as A  # noqa: E402

TESTS = []
MS, S = P.MS, P.S
GNB = "M2S72Bridge.gnb1.cellularNic.mac"


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


# ------------------------------------------------------------------------------------- synthetic Simu5G log ------
def ts(t):
    return f"{t // S}.{t % S:012d}"


def _mk(n_ue, ttis, sched, nack=(), d_ue=2, nproc=16, t0=1000, grant_rtx=False):
    """a gNB + UE MAC log as the runner records it ("%t|%M|<message>"), and the node ids.
    sched(tti) -> UEs given a NEW DL PDU in that TTI (scheduling order); nack: {(pid, attempt)} answered NACK.
    Timing: gNB tx at TTI t; UE reception t + 1 slot; UE feedback t + 1 + d_ue; gNB receipt one slot later
    (d* = d_ue + 2 slots); a NACKed process is retransmitted in the TTI after the NACK reaches the gNB."""
    node = {k: 2049 + k for k in range(n_ue)}
    lines, seq = [], [0]
    procs = {k: [None] * nproc for k in range(n_ue)}
    due, pid, rtx_q = {}, [800], {k: [] for k in range(n_ue)}
    nack = set(nack)

    def emit(t, mod, msg):
        seq[0] += 1
        lines.append((t, seq[0], mod, msg))

    def at(tti, f):
        due.setdefault(tti, []).append(f)

    def ue(k):
        return f"M2S72Bridge.ue[{k}].cellularNic.nrMac"

    def air(k, p, x, attempt, tti):
        def rx(t):
            emit(t, ue(k), f"H-ARQ RX: new PDU (id {x} ) inserted into process {p}")
        at(tti + 1, rx)
        res = "NACK" if (x, attempt) in nack else "ACK"

        def fb_ue(t):
            emit(t, ue(k), f"H-ARQ RX: feedback sent to TX process {p} Codeword  0 of node with id 1 result: {res}")
        at(tti + 1 + d_ue, fb_ue)

        def fb_gnb(t):
            emit(t, GNB, f"H-ARQ TX: feedback received for process {p} codeword 0 result is {res}")
            if res == "ACK":
                procs[k][p] = None
            else:
                procs[k][p][2] = "rtx"
                rtx_q[k].append(p)
        at(tti + 2 + d_ue, fb_gnb)

    for tti in range(t0, t0 + ttis + d_ue + 4):
        t = tti * MS
        for f in due.pop(tti, []):
            f(t)
        if tti >= t0 + ttis:
            continue
        emit(t, GNB, "ENB MAIN LOOP -----")
        emit(t, GNB, "= DOWNLINK =")
        new = [k for k in sched(tti) if k < n_ue]
        rtx = {k: rtx_q[k].pop(0) for k in range(n_ue) if rtx_q[k]}
        for k in new:
            if k not in rtx:
                emit(t, GNB, f"QoSAwareScheduler::Grant cid=MacCid(nodeId={node[k]}, lcid=1) limit=10000 granted=1400B")
        if grant_rtx:
            for k in rtx:
                emit(t, GNB, f"QoSAwareScheduler::Grant cid=MacCid(nodeId={node[k]}, lcid=1) limit=10000 granted=1400B")
        emit(t, GNB, "= END DOWNLINK =")
        for k, p in rtx.items():
            u = procs[k][p]
            u[1] += 1
            u[2] = "wait"
            emit(t, GNB, f"H-ARQ TX: process {p} has been selected for retransmission")
            emit(t, GNB, f"\t H-ARQ TX: pdu (id {u[0]} ) extracted from process {p} codeword 0 for node with id {node[k]}")
            air(k, p, u[0], u[1], tti)
        for k in new:
            if k in rtx:
                continue
            p = next((i for i, u in enumerate(procs[k]) if u is None), None)
            if p is None:
                continue
            pid[0] += 1
            procs[k][p] = [pid[0], 1, "wait"]
            emit(t, GNB, "START LteMacEnb::macPduMake")
            emit(t, GNB, "PDU Maker created PDU: (1400 B) containing 1 SDUs")
            emit(t, GNB, f"H-ARQ TX: new pdu (id {pid[0]} ) inserted into process {p} codeword id: 0 for node with id {node[k]}")
            emit(t, GNB, "END LteMacEnb::macPduMake")
            emit(t, GNB, f"\t H-ARQ TX: pdu (id {pid[0]} ) extracted from process {p} codeword 0 for node with id {node[k]}")
            air(k, p, pid[0], 1, tti)
    lines.sort()
    text = [f"{ts(t)}|{m}|{msg}\n" for t, _, m, msg in lines]
    return text, node


def grants_of(text):
    """the gNB DL grants of a synthetic log as m2s72_maclog.MacLog reads them (via a temporary gzip file)"""
    import m2s72_maclog as ML
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "x.log.gz")
        with gzip.open(p, "wt") as fh:
            fh.writelines(text)
        return ML.MacLog(p).grants
    finally:
        shutil.rmtree(d)


def run(text, node, nproc=16, grants=None):
    log = H.read_log(None, lines=text)
    rows, rep, trace = H.crossvalidate(log, nproc, node_id={k: n for k, n in node.items()},
                                       grants=grants if grants is not None else grants_of(text))
    return log, {r[0]: r for r in rows}, rep, trace


EVERY = lambda tti: [0]                                       # noqa: E731
S2 = lambda tti: [0] + ([1] if tti % 7 == 3 else [])         # noqa: E731  same-TTI and cross-TTI overlaps
S3 = lambda tti: [0] + ([1] if tti % 4 == 1 else [])         # noqa: E731  cross-TTI overlaps only (A-1b)


def st(rows):
    return {k: v[2] for k, v in rows.items()}


# ------------------------------------------------------------------------------------------------ contracts ------
@test("contract: XA's gNB regexes are the accepted parser's; the UE-side regexes match the exact Simu5G 1.8.1 texts "
      "(LteHarqBufferRx.cc:63, :78 - note the two spaces after 'Codeword'), and nothing else")
def _():
    import m2s72_maclog as ML
    assert H.R_INSERT.pattern == ML.R_INSERT.pattern == A.R_INSERT.pattern
    assert H.R_FB.pattern == ML.R_FB.pattern == A.R_FB.pattern
    m = H.R_UE_RX.search("H-ARQ RX: new PDU (id 812 ) inserted into process 3")
    assert m and m.groups() == ("812", "3")
    m = H.R_UE_FB.search("H-ARQ RX: feedback sent to TX process 3 Codeword  0 of node with id 1 result: NACK")
    assert m and m.groups() == ("3", "0", "1", "NACK")
    assert not H.R_UE_FB.search("H-ARQ RX: feedback sent to TX process 3 Codeword 0 of node with id 1 result: ACK")
    m = H.R_EXTRACT.search("\t H-ARQ TX: pdu (id 812 ) extracted from process 3 codeword 0 for node with id 2049")
    assert m and m.groups() == ("812", "3", "0", "2049")
    assert not H.R_UE_RX.search("H-ARQ TX: new pdu (id 812 ) inserted into process 3 codeword id: 0 for node with id 2049")
    assert H.R_UE_MOD.match("M2S72Bridge.ue[1].cellularNic.nrMac").group(1) == "1"
    assert not H.R_UE_MOD.match("M2S72Bridge.ue[1].cellularNic.mac")         # the LTE leg is not logged / not read
    assert H.GNB == "M2S72Bridge.gnb1.cellularNic.mac"


@test("contract: the XA reader's gNB event list is exactly m2s72_peru_adapter.harq_events() on the same log file")
def _():
    text, node = _mk(2, 200, S2)
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "run.log.gz")
        with gzip.open(p, "wt") as fh:
            fh.writelines(text)
        a = A.harq_events(p)
        b = H.read_log(p)["events"]
        assert a == b and len(a) > 100, (len(a), len(b))
        assert len(H.read_log(p)["ins_pid"]) == sum(1 for e in a if e[0] == "ins")
    finally:
        shutil.rmtree(d)


def _old_peru():
    """m2s72_peru.py as committed at bc77a6f (the accepted N = 1 smoke preparation)"""
    src = subprocess.run(["git", "-C", HERE, "show", "bc77a6f:simulations/m2/check/m2s72_peru.py"],
                         capture_output=True, text=True, check=True).stdout
    d = tempfile.mkdtemp()
    p = os.path.join(d, "peru_bc77a6f.py")
    open(p, "w").write(src)
    spec = importlib.util.spec_from_file_location("peru_bc77a6f", p)
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    shutil.rmtree(d)
    return m


@test("identity: attribute_feedback with and without trace returns exactly what the bc77a6f version returns, on 300 "
      "random multi-UE event lists (A-1a, A-1b, ambiguous, orphan, re-insert all occurring) and on the fixtures")
def _():
    old = _old_peru()
    rnd = random.Random(20261116)
    seen = set()
    for it in range(300):
        ev, t = [], 0
        for _ in range(rnd.randint(5, 80)):
            t += rnd.choice([0, 0, MS, 2 * MS])
            if rnd.random() < 0.55:
                ev.append(("ins", t, rnd.choice([2049, 2050, 2051]), rnd.randint(0, 3), 0))
            else:
                ev.append(("fb", t, rnd.randint(0, 3), 0, rnd.choice(["ACK", "ACK", "NACK"])))
        a = old.attribute_feedback(ev, 4)
        b = P.attribute_feedback(ev, 4)
        tr = []
        c = P.attribute_feedback(ev, 4, None, trace=tr)
        assert a == b == c, it
        assert len(tr) == sum(1 for e in ev if e[0] == "fb")
        for k in ("a1a", "a1b", "ambiguous", "orphan", "reinsert"):
            if a[1][k]:
                seen.add(k)
    assert seen == {"a1a", "a1b", "ambiguous", "orphan", "reinsert"}, seen
    for sch in (EVERY, S2, S3):
        text, node = _mk(2, 300, sch)
        ev = H.read_log(None, lines=text)["events"]
        assert old.attribute_feedback(ev, 16) == P.attribute_feedback(ev, 16, trace=[])


@test("identity: the only change to an S5-2 / accepted checker file is the optional trace of attribute_feedback "
      "(git diff bc77a6f limited to m2s72_peru.py, additions only inside attribute_feedback)")
def _():
    out = subprocess.run(["git", "-C", HERE, "diff", "--name-status", "bc77a6f", "--", "."], capture_output=True, text=True,
                         check=True).stdout.split("\n")
    mod = sorted(x.split("\t")[1] for x in out if x and not x.startswith("A"))
    assert mod == ["simulations/m2/check/m2s72_peru.py"], mod
    diff = subprocess.run(["git", "-C", HERE, "diff", "-U0", "bc77a6f", "--", "m2s72_peru.py"], capture_output=True,
                          text=True, check=True).stdout
    minus = [x for x in diff.splitlines() if x.startswith("-") and not x.startswith("---")]
    assert minus == ["-def attribute_feedback(events, nproc, window=None):",
                     '-    returns {node: {...}} with the per-UE occupancy and delays, and a summary {ambiguous, orphan, a1a, a1b, d_star}"""'], minus
    plus = [x for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++")]
    assert plus[0] == "+def attribute_feedback(events, nproc, window=None, trace=None):", plus[0]
    assert all("trace" in x or x.startswith(('+    returns', '+    appended', '+    values', '+            continue')) for x in plus), plus


@test("contract: the per-UE controls (controls-n2 part 2, real output only) call the accepted / S5-2 functions with "
      "the signatures and attributes they have (s5n evaluation, adapter observe / validate, Q8 with mut / k / attr, "
      "q8_rows, the NC-q8-deliv mutation of the E0 controls)")
def _():
    import inspect
    _argv = sys.argv
    sys.argv = [_argv[0]]
    import check_m2s72_s5n as SN
    sys.argv = _argv
    E = SN.E
    assert list(inspect.signature(SN.evaluation).parameters) == ["runs", "cfg", "opt", "full"]
    assert "return ev, aopt, base, n" in inspect.getsource(SN.evaluation)
    assert list(inspect.signature(A.observe).parameters) == ["ev", "mlog_path", "opt", "loaded", "t0", "nproc"]
    assert list(inspect.signature(A.validate).parameters) == ["obs", "totals", "summ", "expected_ues"]
    assert list(inspect.signature(E.Q8.__init__).parameters) == ["self", "ev", "mlog", "opt", "mut", "k", "attr"]
    q8 = inspect.getsource(E.Q8)
    for needle in ('if "drop_deliv" in self.mut:', 'self.deliv = [x for x in self.deliv if x != self.mut["drop_deliv"][0]]',
                   'd.pop(self.mut["drop_deliv"][1], None)', "self.sdu_of", "self.matched"):
        assert needle in q8, needle
    ctl = inspect.getsource(sys.modules["check_m2s72_s5v"].controls_q8)
    for needle in ('k[0] == E.SYNC and k in q.sdu_of', "deliv = next(m_ for m_ in q.matched if (m_[0], m_[1]) == sdu)",
                   '"drop_deliv": ((deliv[3], deliv[1]), k)'):
        assert needle in ctl, needle                      # controls-n2 builds the same mutation, per UE
    assert list(inspect.signature(E.q8_rows).parameters) == ["name", "q"]
    src = inspect.getsource(N2.perue_controls)
    assert 'attr="exclusion"' in src and 'f".ue[{k}]." in mod' in src


# --------------------------------------------------------------------------------------------- fixtures ----------
@test("fixture N = 1 (every TTI): A-1 exact, all A-1a; XA-0..XA-6 PASS; delta = 1 slot; truth = A-1 per UE")
def _():
    text, node = _mk(1, 300, EVERY)
    log, rows, rep, trace = run(text, node)
    assert all(v == "PASS" for v in st(rows).values()), st(rows)
    assert rep["delta_ps"] == MS and rep["a1_summary"]["a1a"] == 300 and rep["a1_summary"]["a1b"] == 0
    assert rep["overlap_census"] == {"1 holder(s)": 300}, rep["overlap_census"]
    assert rep["truth_aggregates"][2049]["inserts"] == 300 and rep["truth_aggregates"][2049]["delays_ps"] == {4 * MS: 300}


@test("fixture N = 2, cross-TTI overlaps only: A-1b is exercised and every A-1b attribution agrees with the UE side; "
      "A-1 exact -> XA-6 PASS; PU-4 PASS")
def _():
    text, node = _mk(2, 400, S3)
    log, rows, rep, trace = run(text, node)
    assert all(v == "PASS" for v in st(rows).values()), {k: v for k, v in rows.items() if v[2] != "PASS"}
    assert rep["agreement"]["agree"].get("a1b", 0) > 50 and not rep["agreement"]["disagree"], rep["agreement"]
    assert any("different insert TTIs" in k for k in rep["overlap_census"]), rep["overlap_census"]
    pu, summ = N2._pu45(log, 16, node, grants_of(text))
    assert {r[0]: r[2] for r in pu} == {"PU-4": "PASS", "PU-5": "PASS"}


@test("fixture N = 2 with same-TTI same-process overlaps (the lowest-free rule makes them likely): A-1 AMBIGUOUS, "
      "classified irreducible by XA-4 (PASS); A-1a / A-1b agree (XA-3 PASS); PU-4 FAIL; XA-6 NOT EVALUATED")
def _():
    text, node = _mk(2, 400, S2)
    log, rows, rep, trace = run(text, node)
    s = st(rows)
    assert [s[x] for x in ("XA-0", "XA-1", "XA-2", "XA-3", "XA-4", "XA-5")] == ["PASS"] * 6, rows
    assert s["XA-6"] == H.NE
    assert rep["a1_summary"]["ambiguous"] > 0
    assert set(rep["ambiguous"]) == {"irreducible: identical feedback, same insert TTI"}, rep["ambiguous"]
    assert all(k.startswith("stale candidate") for k in rep["reinsert"]), rep["reinsert"]
    assert any("same insert TTI" in k for k in rep["overlap_census"])
    pu, _ = N2._pu45(log, 16, node, grants_of(text))
    assert {r[0]: r[2] for r in pu} == {"PU-4": "FAIL", "PU-5": "PASS"}
    assert N2.xa_ok(list(rows.values()))
    occ = rep["truth_occupancy"]
    assert occ[2049]["max_peak"] >= 4 and occ[2050]["max_peak"] >= 1


@test("fixture N = 1 with a NACK: A-1 closes the process on the NACK, so the retransmission's feedback is ORPHAN "
      "(the declared A-1 limitation L-A1-NACK); XA-4 classifies it as a retransmission chain; XA-5 excepts the "
      "retransmission TTI; XA-6 NOT EVALUATED")
def _():
    text, node = _mk(1, 120, EVERY, nack={(805, 1)})
    log, rows, rep, trace = run(text, node)
    s = st(rows)
    assert rep["a1_summary"]["orphan"] >= 1, rep["a1_summary"]
    assert [s[x] for x in ("XA-0", "XA-1", "XA-2", "XA-3", "XA-4", "XA-5")] == ["PASS"] * 6, rows
    assert "retransmission chain" in rep["orphan"] and rep["retransmitted_pdus"] == 1 and rep["nack_ue_sent"] == 1
    assert s["XA-6"] == H.NE


@test("fixture: a retransmission TTI that also carries a grant line is still excepted by XA-5")
def _():
    text, node = _mk(1, 120, EVERY, nack={(805, 1)}, grant_rtx=True)
    _, rows, _, _ = run(text, node)
    assert rows["XA-5"][2] == "PASS", rows["XA-5"]


# --------------------------------------------------------------------------------------------- mutations ---------
@test("mutations (the controls-n2 H-ARQ set, on the N = 2 fixtures): cross-UE swap, orphan, duplicate insert, "
      "inconsistent totals, UE feedback removed, UE reception relabelled, feedback shifted, grant removed - each as "
      "declared; PU-5 provably blind to the swap and the orphan")
def _():
    for sch in (S3, S2):
        text, node = _mk(2, 400, sch)
        log = H.read_log(None, lines=text)
        out, st0, pst0, summ0, rep0 = N2.harq_controls(log, 16, node, grants_of(text))
        names = [x[0].split(":")[0] for x in out]
        assert names == ["PC-n2-unmodified", "NC-n2-swap", "NC-n2-orphan", "NC-n2-dup", "NC-n2-totals", "NC-n2-uefb",
                         "NC-n2-uerx", "NC-n2-shift", "NC-n2-grant"], names
        bad = [x for x in out if not x[1]]
        assert not bad, bad
        sw = next(x for x in out if x[0].startswith("NC-n2-swap"))
        assert "PU-5 PASS" in sw[2], sw


@test("mutation sensitivity of the controls themselves: a control whose mutation is undone must report 'not as "
      "declared' (the swap control with XA blind)")
def _():
    text, node = _mk(2, 300, S3)
    log = H.read_log(None, lines=text)
    real = H.crossvalidate
    try:
        def blind(lg, nproc, **kw):                    # an XA that never fails
            rows, rep, tr = real(lg, nproc, **kw)
            return [(r[0], r[1], "PASS" if r[2] == "FAIL" else r[2], r[3]) for r in rows], rep, tr
        H.crossvalidate = blind
        out, *_ = N2.harq_controls(log, 16, node, grants_of(text))
    finally:
        H.crossvalidate = real
    assert not next(x for x in out if x[0].startswith("NC-n2-swap"))[1]
    assert not next(x for x in out if x[0].startswith("NC-n2-uefb"))[1]


@test("mutation: an A-1 defect is caught by XA-3 (a deliberately wrong A-1 that swaps the pick of every 10th "
      "A-1a attribution) while PU-4 and PU-5 still PASS")
def _():
    text, node = _mk(2, 300, S3)
    log = H.read_log(None, lines=text)
    real = P.attribute_feedback

    def wrong(events, nproc, window=None, trace=None):
        per, summ = real(events, nproc, window, trace=trace)
        if trace is not None:
            a = 0
            for j, (i, n, cls) in enumerate(trace):
                if cls == "a1a":
                    a += 1
                    if a % 10 == 0:
                        trace[j] = (i, 2049 if n == 2050 else 2050, cls)
        return per, summ
    try:
        P.attribute_feedback = wrong
        rows, rep, _ = H.crossvalidate(log, 16, node_id=node, grants=grants_of(text))
    finally:
        P.attribute_feedback = real
    s = {r[0]: r[2] for r in rows}
    assert s["XA-3"] == "FAIL" and rep["agreement"]["disagree"]["a1a"] > 0, rows
    pu, _ = N2._pu45(log, 16, node, grants_of(text))
    assert {r[0]: r[2] for r in pu} == {"PU-4": "PASS", "PU-5": "PASS"}


@test("mutation: XA-0 fails when the run's node ids disagree with the PDU-id map; XA-2 fails on a codeword 1 line "
      "(NOT EVALUATED) and when there is no UE side at all")
def _():
    text, node = _mk(2, 200, S3)
    log = H.read_log(None, lines=text)
    rows, _, _ = H.crossvalidate(log, 16, node_id={0: 2050, 1: 2049}, grants=grants_of(text))
    assert {r[0]: r[2] for r in rows}["XA-0"] == "FAIL"
    t2 = [x.replace("Codeword  0", "Codeword  1", 1) if "feedback sent" in x else x for x in text]
    i = next(i for i, x in enumerate(text) if "feedback sent" in x)
    t2 = text[:i] + [text[i].replace("Codeword  0", "Codeword  1")] + text[i + 1:]
    rows, _, _ = H.crossvalidate(H.read_log(None, lines=t2), 16, node_id=node, grants=grants_of(text))
    assert {r[0]: r[2] for r in rows}["XA-2"] == H.NE
    t3 = [x for x in text if ".ue[" not in x]
    rows, _, _ = H.crossvalidate(H.read_log(None, lines=t3), 16, node_id=node, grants=grants_of(text))
    s = {r[0]: r[2] for r in rows}
    assert s["XA-0"] == "FAIL" and s["XA-1"] == "FAIL" and s["XA-2"] == "FAIL", s


@test("end censoring: a PDU inserted in the last TTI before the log ends (no UE reception, no feedback) is "
      "end-censored, not a failure; the same PDU earlier in the log is a failure")
def _():
    text, node = _mk(1, 100, EVERY)
    last_ins = max(i for i, x in enumerate(text) if "inserted into process" in x and "H-ARQ TX" in x)
    pid = text[last_ins].split("(id ")[1].split(" )")[0]
    cut = [x for x in text if not (f"(id {pid} )" in x and ".ue[" in x) and not (x.split("|")[0] > text[last_ins].split("|")[0]
                                                                                and "feedback" in x)]
    rows, rep, _ = H.crossvalidate(H.read_log(None, lines=cut), 16, node_id=node, grants=grants_of(cut))
    s = {r[0]: r for r in rows}
    assert s["XA-1"][2] == "PASS" and "end-censored 1" in s["XA-1"][3], s["XA-1"]
    first_ins = next(i for i, x in enumerate(text) if "inserted into process" in x and "H-ARQ TX" in x)
    pid0 = text[first_ins].split("(id ")[1].split(" )")[0]
    cut0 = [x for x in text if not (f"(id {pid0} )" in x and ".ue[" in x)]
    rows, _, _ = H.crossvalidate(H.read_log(None, lines=cut0), 16, node_id=node, grants=grants_of(cut0))
    assert {r[0]: r[2] for r in rows}["XA-1"] == "FAIL"


# ------------------------------------------------------------------------------------------------ verdict -------
def _records(d, cfg, pu4="PASS", xa_rows=None, gate_failures=(), ctl=(14, 14), a1=None, outcome="OK", a1b=10):
    rec = os.path.join(d, "rec")
    os.makedirs(rec, exist_ok=True)
    open(os.path.join(rec, "runs.tsv"), "w").write("config\tseed\toutcome\trc\twall_s\traw_bytes\tcheck\tmanifest_sha256\ttier\tdetail\n"
                                                  f"{cfg}\t0\t{outcome}\t0\t300\t1\trc 1\tx\theld\t-\n")
    open(os.path.join(rec, "steps.txt"), "w").write("x manifest verified: 41 files\n")
    a1 = a1 or {"a1a": 100, "a1b": a1b, "ambiguous": 0 if pu4 == "PASS" else 4, "orphan": 0, "reinsert": 0 if pu4 == "PASS" else 2,
                "d_star_ps": 4 * MS}
    adp = [("PASS", "PU-1", "run"), ("PASS", "PU-2", "UE 0"), ("NOT APPLICABLE", "PU-3", "UE 1"), ("PASS", "PU-2", "UE 1"),
           ("PASS", "PU-3", "UE 0"), (pu4, "PU-4", "run"), ("PASS", "PU-5", "run")]
    for u in ("UE 0", "UE 1"):
        adp += [("PASS", "AV-1", u), ("PASS", "AV-2", u), ("PASS", "AV-3", u)]
    with open(os.path.join(rec, f"adapter-validate-{cfg}.txt"), "w") as fh:
        fh.write("S5-2 adapter validation\n\n")
        for s_, r, u in adp:
            fh.write(f"  {s_:<15} | {r} | {u} | detail\n")
        fh.write("\nper-UE Q8 rows (accepted rules, UE k, strict exclusion attribution), reported:\n")
        for k in (0, 1):
            fh.write(f"  {'PASS':<15} | Q8 | {cfg}-0 UE {k} | GM frames 192: {{'delivered': 192}}\n")
    json.dump({"per_ue": [{"k": 0, "gptp_fates": {"used": 80}}, {"k": 1, "gptp_fates": {"used": 79, "censored": 1}}],
               "harq_attribution": a1}, open(os.path.join(rec, f"adapter-validate-{cfg}.json"), "w"))
    xr = xa_rows or [["XA-pre", "run", "PASS", ""]] + [[f"XA-{i}", "run", "PASS", ""] for i in range(6)] + \
        [["XA-6", "run", "PASS" if pu4 == "PASS" else H.NE, "" if pu4 == "PASS" else "A-1 not exact"]]
    json.dump({"rows": xr, "report": {"a1_summary": a1, "agreement": {"agree": {"a1a": 100, "a1b": a1b}},
                                      "overlap_census": {}}}, open(os.path.join(rec, f"xa-{cfg}.json"), "w"))
    with open(os.path.join(rec, f"{cfg}.check.txt"), "w") as fh:
        for r in ("MG-1", "Q8-v", "SG-403"):
            fh.write(f"  {'PASS':<15} | {r} | {cfg}-0 | d\n")
        fh.write(f"\nper-run verdict: {'PASS' if not gate_failures else 'FAIL ' + ' '.join(gate_failures)}\n")
    json.dump({"correctness": {"gate_failures": list(gate_failures), "per_ue_not_evaluated": []}},
              open(os.path.join(rec, f"{cfg}.digest.json"), "w"))
    if ctl is not None:
        json.dump({"as_declared": ctl[0], "total": ctl[1]}, open(os.path.join(rec, f"controls-n2-{cfg}.json"), "w"))
    return rec


@test("verdict: VALIDATED (rc 0); VALIDATED WITH A-1 LIMITATION when PU-4 FAILs and XA-4 explains it (rc 3); "
      "NOT VALIDATED on any REJECT (rc 1): an XA-3 disagreement, a gate failure other than PU-4, a control not as "
      "declared, adapter / XA A-1 summaries that differ; INCOMPLETE when a record is missing (rc 4)")
def _():
    import contextlib
    import io
    cfg = "M2S72-E0vN-q0-one0-n2-f1"

    def v(**kw):
        d = tempfile.mkdtemp()
        try:
            rec = _records(d, cfg, **kw)
            with contextlib.redirect_stdout(io.StringIO()):
                rc = N2.verdict(rec, cfg)
            return rc, json.load(open(os.path.join(rec, f"smoke-n2-verdict-{cfg}.json")))
        finally:
            shutil.rmtree(d)
    assert v()[0] == 0
    rc, j = v(pu4="FAIL", gate_failures=("PU-4",))
    assert rc == 3 and j["overall"].startswith("VALIDATED WITH A-1 LIMITATION"), j["overall"]
    bad = [["XA-pre", "run", "PASS", ""]] + [[f"XA-{i}", "run", "FAIL" if i == 3 else "PASS", ""] for i in range(6)] + [["XA-6", "run", "PASS", ""]]
    assert v(xa_rows=bad)[0] == 1
    assert v(gate_failures=("F0-3",))[0] == 1
    assert v(ctl=(13, 14))[0] == 1
    d = tempfile.mkdtemp()
    try:
        rec = _records(d, cfg)
        j = json.load(open(os.path.join(rec, f"xa-{cfg}.json")))
        j["report"]["a1_summary"]["a1b"] += 1
        json.dump(j, open(os.path.join(rec, f"xa-{cfg}.json"), "w"))
        import contextlib as cl
        with cl.redirect_stdout(io.StringIO()):
            assert N2.verdict(rec, cfg) == 1
    finally:
        shutil.rmtree(d)
    assert v(ctl=None)[0] == 4
    assert v(outcome="SIM-ABORT")[0] == 1
    rc, j = v(a1b=0)
    a4 = next(c for c in j["criteria"] if c[0] == "N2-A4")
    assert rc == 0 and "A-1b NOT EXERCISED" in a4[3], a4


# ------------------------------------------------------------------------------------------- runner, stubbed -----
STUB_OPP = r'''#!/bin/bash
[ "$1" = -v ] && { echo "Version: STUB"; exit 0; }
cfg=""; rd=""
for a in "$@"; do case "$a" in --result-dir=*) rd=${a#--result-dir=} ;; esac; done
while [ $# -gt 0 ]; do [ "$1" = -c ] && cfg=$2; shift; done
mkdir -p "$rd/$cfg/pcap"; echo "t,v" > "$rd/$cfg/x.csv"
echo "$cfg" > "$rd/$cfg/config-name.txt"
echo "<!> Simulation time limit reached"; exit 0
'''
STUB_N2 = r'''#!/usr/bin/env python3
import os, sys
open(os.environ["STUB_CALLS"], "a").write(" ".join(sys.argv[1:]) + " | ADAPTER_VALIDATED=" + os.environ.get("S5N_ADAPTER_VALIDATED", "-") + "\n")
cmd = sys.argv[1]
rc = int(os.environ.get("STUB_N2_RC_" + cmd.replace("-", "_"), "0"))
if cmd == "verdict":
    print("N = 2 smoke: STUB"); sys.exit(rc)
print("stub " + cmd); sys.exit(rc)
'''


def _env(d, **kw):
    sys.path.insert(0, HERE)
    import test_m2s72s5 as T1
    env = T1._env(d)
    om = env["OMNETPP_ROOT"]
    open(os.path.join(om, "bin", "opp_run"), "w").write(STUB_OPP)
    stub = os.path.join(d, "stubn2.py")
    open(stub, "w").write(STUB_N2)
    env.update(S5_TEST_N2_CHECKER=stub)
    env.update(kw)
    return env


def _runner(env, *args):
    return subprocess.run([os.path.join(M2, "m2s72s5.sh")] + list(args), env=env, capture_output=True, text=True)


def _rmtree_ro(d):
    for root, dirs, _ in os.walk(d):
        for x in dirs:
            os.chmod(os.path.join(root, x), 0o755)
    shutil.rmtree(d)


@test("runner smoke-n2: one run M2S72-E0vN-q0-one0-n2-f1 (seed 0); manifest; adapter-validate q0 0 0; xa; "
      "controls-n2; the E0v-N per-run rows with the labelled diagnostic value; verdict; raw held uncompressed and "
      "read-only; nothing committed even with S5_RECORDS_REPO; release refused; never rerun into the same stage")
def _():
    import test_m2s72s5 as T1
    d = tempfile.mkdtemp()
    try:
        repo = T1._repo(d)
        env = _env(d, S5_RECORDS_REPO=repo)
        r = _runner(env, "smoke-n2")
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
        out = os.path.join(d, "root", "m2", "M2-S7.2a-s5smoke-n2")
        cfg = "M2S72-E0vN-q0-one0-n2-f1"
        assert sorted(os.listdir(os.path.join(out, "runs"))) == [cfg, f"run-{cfg}.log.gz"]
        x = os.path.join(out, "runs", cfg, cfg, "x.csv")
        assert os.path.exists(x) and not (os.stat(x).st_mode & 0o222), "smoke-n2 raw not held read-only"
        calls = open(env["STUB_CALLS"]).read().splitlines()
        cmds = [c.split()[0] for c in calls]
        assert cmds == ["adapter-validate", "xa", "controls-n2", "run", "verdict"], calls
        assert calls[0].startswith(f"adapter-validate {out}/runs {cfg} q0 0 0 ")
        assert calls[2].startswith(f"controls-n2 {out}/runs {cfg} q0 0 0 ")
        assert "ADAPTER_VALIDATED=-" in calls[0] and "ADAPTER_VALIDATED=smoke-n2 labelled diagnostic" in calls[3], calls
        rec = os.path.join(out, "records")
        tsv = open(os.path.join(rec, "runs.tsv")).read().splitlines()
        assert len(tsv) == 2 and tsv[1].startswith(cfg + "\t0\tOK\t") and "\theld\t" in tsv[1], tsv
        assert "held (smoke-n2 review" in open(os.path.join(rec, "ledger.tsv")).read()
        steps = open(os.path.join(rec, "steps.txt")).read()
        assert "manifest verified" in steps and "lifecycle complete" in steps, steps[-600:]
        assert "TEST HOOKS ACTIVE" in open(os.path.join(rec, "env-smoke-n2.txt")).read()
        log = subprocess.run(["git", "-C", repo, "log", "--format=%s"], capture_output=True, text=True).stdout
        assert "S5 records" not in log, log
        r = _runner(env, "release", "M2-S7.2a-s5smoke-n2")
        assert r.returncode != 0 and "never released" in r.stderr, r.stderr
        r = _runner(env, "smoke-n2")
        assert r.returncode != 0 and "never overwritten" in r.stderr, r.stderr
        assert os.path.exists(x)
    finally:
        _rmtree_ro(d)


@test("runner smoke-n2: an evaluation error (rc 2) of any tool -> exit 6, every later step still done and recorded; "
      "an acceptance FAIL (rc 1) is recorded, not a lifecycle failure; no S5_ENV_DECISION -> refused, nothing created")
def _():
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, STUB_N2_RC_xa="2"), "smoke-n2")
        assert r.returncode == 6, (r.returncode, r.stdout[-400:])
        rec = os.path.join(d, "root", "m2", "M2-S7.2a-s5smoke-n2", "records")
        steps = open(os.path.join(rec, "steps.txt")).read()
        assert "INCOMPLETE LIFECYCLE" in steps and "verdict rc" in steps and "manifest verified" in steps, steps[-500:]
    finally:
        _rmtree_ro(d)
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, STUB_N2_RC_adapter_validate="1", STUB_N2_RC_run="1"), "smoke-n2")
        assert r.returncode == 0, (r.returncode, r.stdout[-400:])
    finally:
        _rmtree_ro(d)
    d = tempfile.mkdtemp()
    try:
        env = _env(d)
        env.pop("S5_ENV_DECISION")
        r = _runner(env, "smoke-n2")
        assert r.returncode != 0 and "S5_ENV_DECISION" in r.stderr and not os.path.exists(os.path.join(d, "root", "m2", "M2-S7.2a-s5smoke-n2"))
    finally:
        _rmtree_ro(d)


@test("runner: the accepted modes are unchanged (diff vs bc77a6f touches only the usage line, the test-hook line, "
      "the smoke-n2 stage name, the smoke-n2 branch and its release refusal)")
def _():
    diff = subprocess.run(["git", "-C", HERE, "diff", "-U0", "bc77a6f", "--", "../m2s72s5.sh"], capture_output=True,
                          text=True, check=True).stdout
    minus = [x for x in diff.splitlines() if x.startswith("-") and not x.startswith("---")]
    assert len(minus) == 2 and "usage:" in minus[0] and "TEST HOOKS ACTIVE" in minus[1], minus
    plus = [x for x in diff.splitlines() if x.startswith("+") and not x.startswith("+++")]
    assert all(("smoke-n2" in x or "N2CHK" in x or "S5N" in x or x.startswith(("+    ", "+#", "+  smoke-n2", "+TEST")))
               for x in plus), [x for x in plus][:5]


def main():
    ok = 0
    for name, f in TESTS:
        try:
            f()
            print(f"PASS | {name}")
            ok += 1
        except Exception as ex:
            import traceback
            print(f"FAIL | {name}: {type(ex).__name__}: {ex}\n{traceback.format_exc()[-900:]}")
    print(f"S5 N = 2 tests: {ok} / {len(TESTS)} PASS")
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
