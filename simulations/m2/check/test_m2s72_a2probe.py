#!/usr/bin/env python3
"""A-2 design increment: tests of the read-only feasibility probe P0 (m2s72_a2probe.py) and of the source-faithful
fixture generator with NACK / retransmission / discard paths (m2s72_harqfix.py). No simulation, no raw output."""
import os
import random
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a2probe as PR  # noqa: E402
import m2s72_harqfix as F  # noqa: E402
import m2s72_harqx as H  # noqa: E402

TESTS = []
MS = F.MS


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


S2 = lambda tti: [0] + ([1] if tti % 7 == 3 else [])                     # noqa: E731  same-TTI and cross-TTI overlaps
S3W = lambda tti: [0] + ([1] if tti % 5 == 0 else []) + ([2] if tti % 10 == 0 else [])   # noqa: E731  3-way groups
NACKS = {(805, 1), (805, 2), (805, 3), (805, 4), (830, 1), (861, 1)}     # a discard chain (4 NACKs) and two single NACKs


def pre(rep):
    return {k.split(" ")[0]: v for k, v in rep["preconditions"].items()}


# ------------------------------------------------------------------------------------------------ contracts ------
@test("contract: the probe's patterns match the exact Simu5G 1.8.1 texts (LteHarqUnitTx.cc:117/:126/:141 with two "
      "spaces after 'process'; LteSchedulerEnbDl.cc:108/:245/:246/:270; LteHarqBufferTx.cc:109/:175/:220/:242) and "
      "the accepted gNB patterns are the adapter's")
def _():
    import m2s72_peru_adapter as A
    assert PR.R_INSERT.pattern == A.R_INSERT.pattern and PR.R_FB.pattern == A.R_FB.pattern and PR.R_EXTRACT.pattern == H.R_EXTRACT.pattern
    assert PR.R_URTX.search("1.007 LteHarqUnitTx::pduFeedback H-ARQ process  3 Codeword 0 PDU 805 set for RTX ").groups() == ("3", "0", "805")
    assert not PR.R_URTX.search("1.007 LteHarqUnitTx::pduFeedback H-ARQ process 3 Codeword 0 PDU 805 set for RTX ")
    assert PR.R_UDISC.search("1.019 LteHarqUnitTx::pduFeedback H-ARQ process  3 Codeword 0 PDU 805 discarded "
                             "(max retransmissions reached) : 3").groups() == ("3", "0", "805")
    assert PR.T_UACK in "\t pdu_ has been sent and received correctly "
    assert PR.R_RTXACID.search("1.011LteSchedulerEnbDl::rtxAcid - Node [1], User[2049],  Codeword [0]  of [1] , ACID [3] ").groups() == \
        ("1", "2049", "0", "1", "3")
    assert PR.R_RTXS_DIR.search("1.011 LteSchedulerEnbDl::rtxschedule Cell:  1 Direction: DL").group(2) == "DL"
    assert PR.R_RTXS_UE.search("1.011 LteSchedulerEnbDl::rtxschedule  UE: 2050").group(1) == "2050"
    assert PR.T_RTXS_START in "1.011 LteSchedulerEnbDl::rtxschedule --------------------::[ START RTX-SCHEDULE ]::--------------------"
    assert PR.R_SELRTX.search("H-ARQ TX: process 3 has been selected for retransmission").group(1) == "3"
    assert PR.T_START == "LteHarqBufferTx::receiveHarqFeedback - start" and PR.T_WELCOME == "LteHarqUnitTx::pduFeedback - Welcome!"


@test("contract (source, when the Simu5G 1.8.1 tree is available as SIMU5G_ROOT or the scratch clone): every text the "
      "probe and the generator use occurs verbatim in the 1.8.1 sources; skipped (reported) when no tree is present")
def _():
    roots = [os.environ.get("SIMU5G_ROOT", ""), "/tmp/claude-0/-home-claude/f08b3521-4dd6-5494-b405-fc45c61f17fc/scratchpad/src/simu5g-1.8.1"]
    root = next((r for r in roots if r and os.path.exists(os.path.join(r, "src/simu5g/stack/mac/buffer/harq/LteHarqUnitTx.cc"))), None)
    if root is None:
        print("    (no Simu5G 1.8.1 source tree here: source-text contract skipped)")
        return
    src = lambda rel: open(os.path.join(root, "src/simu5g", rel)).read()   # noqa: E731
    u, b, s = src("stack/mac/buffer/harq/LteHarqUnitTx.cc"), src("stack/mac/buffer/harq/LteHarqBufferTx.cc"), src("stack/mac/scheduler/LteSchedulerEnbDl.cc")
    for needle in ('" LteHarqUnitTx::pduFeedback H-ARQ process  "', '" set for RTX "', '" discarded (max retransmissions reached) : "',
                   '"\\t pdu_ has been sent and received correctly "', '"LteHarqUnitTx::pduFeedback - Welcome!"'):
        assert needle in u, needle
    for needle in ('"LteHarqBufferTx::receiveHarqFeedback - start"', '" has been selected for retransmission"', '" ) extracted from process "'):
        assert needle in b, needle
    for needle in ('"LteSchedulerEnbDl::rtxAcid - Node ["', '"], User["', '"],  Codeword ["', '"]  of ["', '"] , ACID ["',
                   '" LteSchedulerEnbDl::rtxschedule  UE: "', '" LteSchedulerEnbDl::rtxschedule Cell:  "',
                   '::[ START RTX-SCHEDULE ]::'):
        assert needle in s, needle
    enum = src("common/LteCommonEnum.msg")
    for k, v in F.STATUS.items():
        assert f"TXHARQ_PDU_{k} = {v};" in enum, k


# --------------------------------------------------------------------------------------------------- fixtures ------
@test("fixture without NACK (the situation of every preserved run): P0-1..P0-3 and P0-6 HOLD, P0-4 NOT EXERCISED, "
      "P0-5 holds for all-ACK groups only, each qualifier stated")
def _():
    lines, node, truth = F.make(2, 400, S2)
    rep = PR.census(lines=lines)
    p = pre(rep)
    assert p["P0-1"].startswith("HOLDS") and "NACK blocks NOT EXERCISED" in p["P0-1"], p
    assert p["P0-2"].startswith("HOLDS") and "retransmissions NOT EXERCISED" in p["P0-2"], p
    assert p["P0-3"] == "HOLDS" and p["P0-4"] == "NOT EXERCISED" and p["P0-6"] == "HOLDS", p
    assert p["P0-5"].startswith("HOLDS") and "groups with a NACK NOT EXERCISED" in p["P0-5"], p
    assert rep["d_star_tx_ps"] == 4 * MS and not rep["violations"]


@test("fixture with NACK chains (a 4-transmission discard and two single NACKs, one inside a same-TTI group): every "
      "precondition HOLDS, the mixed group is seen, retransmissions are node-identified, nothing open at the end")
def _():
    lines, node, truth = F.make(2, 400, S2, nack=NACKS)
    rep = PR.census(lines=lines)
    assert all(v == "HOLDS" for v in pre(rep).values()), rep["preconditions"]
    c = rep["counts"]
    assert c["feedback NACK"] == 6 and c["unit discard (PDU id)"] == 1 and c["unit rtx (PDU id)"] == 5
    assert c["retransmission (extract after NACK)"] == 5 == c["rtxAcid (node-identified rtx)"]
    assert any("mixed" in k for k in rep["groups"]), rep["groups"]
    assert rep["open_at_end"] == {} and rep["d_star_tx_ps"] == 4 * MS
    assert sum(1 for x in truth if x["outcome"] == "discard") == 1


@test("generality: N = 3 with three-way same-TTI groups, HARQ 5, and feedback events after the main loop of the "
      "TTI (the other admissible order): every exercised precondition HOLDS")
def _():
    for kw in (dict(n_ue=3, sched=S3W), dict(n_ue=2, sched=S2, nproc=5), dict(n_ue=2, sched=S2, fb_first=False)):
        n = kw.pop("n_ue")
        sch = kw.pop("sched")
        lines, node, truth = F.make(n, 300, sch, nack=NACKS, **kw)
        rep = PR.census(lines=lines)
        assert not any(v.startswith("FAILS") for v in pre(rep).values()), (kw, rep["preconditions"], rep["violations"])
        if n == 3:
            assert any(k.startswith("3 candidates") for k in rep["groups"]), rep["groups"]


@test("the UE-side reference XA on the faithful generator WITH retransmissions: its per-line truth equals the "
      "generator's own truth on every feedback line (retransmitted ids, repeated UE receptions, a discard chain); "
      "XA-0/1/2/5 PASS. Finding: after a NACK, A-1 does not only orphan the retransmission's feedback, it MISATTRIBUTES "
      "later lines as A-1a (cascade through its stale state); XA-3 counts exactly the generator-truth disagreements")
def _():
    import m2s72_peru as P
    import test_m2s72s5_n2 as T
    lines, node, truth = F.make(2, 400, lambda t: [0] + ([1] if t % 4 == 1 else []), nack=NACKS)
    log = H.read_log(None, lines=lines)
    rows, rep, trace = H.crossvalidate(log, 16, node_id=node, grants=T.grants_of(lines))
    s = {r[0]: r[2] for r in rows}
    assert [s[x] for x in ("XA-0", "XA-1", "XA-2", "XA-5")] == ["PASS"] * 4, rows
    assert rep["retransmitted_pdus"] == 3 and rep["nack_ue_sent"] == 6
    tr = H.truth(log, node)
    _, lines_x, _, _ = H.match_feedback(log, tr, trace)
    fb_truth = [x["node"] for x in truth]
    assert [grp == {fb_truth[j]} for j, (i, own, x, grp) in enumerate(lines_x)] == [True] * len(fb_truth)
    wrong = sum(1 for j, (i, n, c) in enumerate(trace) if c in ("a1a", "a1b") and n != fb_truth[j])
    assert wrong > 0 and rep["agreement"]["disagree"].get("a1a", 0) + rep["agreement"]["disagree"].get("a1b", 0) == wrong, wrong
    assert s["XA-3"] == "FAIL" and rep["a1_summary"]["orphan"] > 0     # PU-4 would FAIL (fail-closed at run level)


# -------------------------------------------------------------------------------------------------- mutations -----
def _mut(lines, pred, repl=None, nth=0):
    idx = [i for i, x in enumerate(lines) if pred(x)]
    i = idx[nth]
    out = list(lines)
    if repl is None:
        del out[i]
    else:
        out[i] = repl(out[i])
    return out


@test("mutations: each precondition fails on the corruption it exists to detect - unit NACK line removed (P0-1), "
      "first extract removed (P0-2), one feedback line one TTI late (P0-3), rtxAcid line removed (P0-4), a candidate "
      "node's new transmission logged inside an all-ACK group (P0-5), a dropped-unit text added (P0-6)")
def _():
    lines, node, truth = F.make(2, 400, S2, nack=NACKS)
    cases = {
        "P0-1": _mut(lines, lambda x: "set for RTX" in x),
        "P0-2": _mut(lines, lambda x: "extracted from process" in x and "(id 812 )" in x),
        "P0-3": _mut(lines, lambda x: "feedback received for process" in x, lambda x: x.replace(x.split("|")[0], F.ts(PR.t_ps(x.split("|")[0]) + MS)), nth=40),
        "P0-4": _mut(lines, lambda x: "rtxAcid - Node" in x),
        "P0-6": lines[:200] + [lines[200].split("|")[0] + "|" + F.GNB + "|H-ARQ TX buffer: received pdu for acid 3. The corresponding unit has been  reset\n"] + lines[200:],
    }
    fbi = [i for i, x in enumerate(lines) if "feedback received for process" in x]
    # P0-5: inside an all-ACK group, a new transmission of one candidate node (fresh PDU on an unused process) is
    # logged between the group's two feedback blocks: the assignment of the two ACKs is no longer immaterial
    acks = [(a, b) for a, b in zip(fbi, fbi[1:]) if lines[a].split("|")[0] == lines[b].split("|")[0]
            and lines[a].split("process ")[1].split(" ")[0] == lines[b].split("process ")[1].split(" ")[0]
            and lines[a].strip().endswith("ACK") and lines[b].strip().endswith("is ACK") and lines[a].strip().endswith("is ACK")]
    a, b = acks[0]
    tsx = lines[a].split("|")[0]
    extra = [f"{tsx}|{F.GNB}|H-ARQ TX: new pdu (id 99999 ) inserted into process 15 codeword id: 0 for node with id 2049\n",
             f"{tsx}|{F.GNB}|\t H-ARQ TX: pdu (id 99999 ) extracted from process 15 codeword 0 for node with id 2049\n"]
    cases["P0-5"] = lines[:a + 1] + extra + lines[a + 1:]
    for k, l in cases.items():
        p = pre(PR.census(lines=l))
        assert p[k].startswith("FAILS"), (k, p)


@test("design evidence: the A-2 prototype (gNB-only unit-state attribution, proto_m2s72_a2.py) is exact against the "
      "generator truth in all 48 sweep scenarios (N 2..4, HARQ 5 / 16, both event orders, NACK rate 0..5 %, discard "
      "chains): NACK / discard lines identified by PDU id, single-candidate ACKs correct, each exchangeable group holds "
      "the true owner, per-UE aggregates and per-UE log-order occupancy equal the truth, one d*_tx; A-1 on the same "
      "lines: never wrong without NACK (its unresolved lines are exactly A-2's groups), wrong after NACKs")
def _():
    import proto_m2s72_a2 as PA
    res = PA.sweep()
    assert len(res) == 48
    a1_wrong_nack = 0
    for key, nacks, c, a1w, a1u, nfb in res:
        assert not any("WRONG" in k for k in c["lines"]) and "unattributed" not in c["lines"], (key, c["lines"])
        assert all(c["aggregates_equal"].values()) and c["occupancy_equal"] and c["n_problems"] == 0 and len(c["ages"]) == 1, (key, c)
        if nacks == 0:
            assert a1w == 0 and a1u == c["lines"].get("group ok", 0), (key, a1w, a1u, c["lines"])
        a1_wrong_nack += a1w
    assert a1_wrong_nack > 0


@test("helpers: Simu5G per-UE H-ARQ scalars read from a .sca; eventlog coverage counted; both None when absent")
def _():
    d = tempfile.mkdtemp()
    try:
        sca = os.path.join(d, "0.sca")
        open(sca, "w").write("version 3\nscalar M2S72Bridge.ue[0].cellularNic.nrMac harqErrorRateDl:mean 0\n"
                             "scalar M2S72Bridge.ue[1].cellularNic.nrMac harqTxAttemptsDl:mean 1\nscalar x y:mean 3\n")
        s = PR.scalars(sca)
        assert s == {"M2S72Bridge.ue[0].cellularNic.nrMac": {"harqErrorRateDl:mean": "0"},
                     "M2S72Bridge.ue[1].cellularNic.nrMac": {"harqTxAttemptsDl:mean": "1"}}, s
        el = os.path.join(d, "0.elog")
        open(el, "w").write("E # 5 t 0.301 m 12 ce 4 msg 9\nBS id 9 tid 9 c LteAirFrame n harqFeedback\n- H-ARQ TX: feedback received for process 0 codeword 0 result is ACK\n")
        e = PR.elog(el)
        assert e["lines naming harqFeedback"] == 1 and e["gNB feedback log lines"] == 1 and e["last event time"] == "0.301", e
        assert PR.scalars(os.path.join(d, "none")) is None and PR.elog(os.path.join(d, "none")) is None
    finally:
        shutil.rmtree(d)


@test("CLI end to end on a synthetic run tree (gzip log): exit 0, a2probe-<cfg>.txt / .json written; exit 1 when a "
      "precondition fails")
def _():
    import gzip
    d = tempfile.mkdtemp()
    try:
        for name, l, rc in (("OK", F.make(2, 200, S2, nack=NACKS)[0], 0), ("BAD", _mut(F.make(2, 200, S2, nack=NACKS)[0], lambda x: "set for RTX" in x), 1)):
            runs = os.path.join(d, name)
            os.makedirs(os.path.join(runs, "cfg", "cfg"))
            with gzip.open(os.path.join(runs, "run-cfg.log.gz"), "wt") as fh:
                fh.writelines(l)
            r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "m2s72_a2probe.py"), runs, "cfg", os.path.join(d, name + "-out")],
                               capture_output=True, text=True)
            assert r.returncode == rc, (name, r.returncode, r.stdout[-500:])
            assert os.path.exists(os.path.join(d, name + "-out", "a2probe-cfg.json"))
    finally:
        shutil.rmtree(d)


@test("scope: vs 06fba26 this increment only adds files (A-1, PU-4, the adapter, XA, the runner and every record "
      "unchanged)")
def _():
    out = subprocess.run(["git", "-C", HERE, "diff", "--name-status", "06fba26", "--", ".."], capture_output=True, text=True, check=True).stdout
    changed = [x for x in out.splitlines() if x and not x.startswith("A")]
    assert changed == [], changed


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
    print(f"A-2 probe tests: {ok} / {len(TESTS)} PASS")
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
