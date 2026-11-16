#!/usr/bin/env python3
"""Tests of the PROPOSED A2-V1 evaluator (check_m2s72_a2v1.py). No simulation, no raw output: synthetic logs from the
source-faithful generator m2s72_harqfix.make() in OMNeT++'s real '%t' prefix format, with a .sca laid out as Simu5G
records it. They show that the evaluator accepts a correct NACK run, stops on a run without NACKs or with NACKs where
the design puts none, and that every negative control bites. They say nothing about real Simu5G output (A2-V1)."""
import gzip
import os
import shutil
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import check_m2s72_a2 as C  # noqa: E402
import check_m2s72_a2v1 as V  # noqa: E402
import m2s72_a2 as A2  # noqa: E402
import m2s72_harqfix as F  # noqa: E402
import test_m2s72_a2 as TA  # noqa: E402

TESTS = []
MS, S = F.MS, A2.S
NET = "M2S72Bridge"
D = dict(V.DESIGN, min_nack=5)
def SCHED(t):
    return [0] + ([1] if t % 3 == 1 else [])


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def sca(d, node, truth, per_dl=(0.0, 0.1), ideal=True, clean_scalars=True):
    """the .sca records the evaluator and A2-8 read: channel-model parameters (IdealChannelModel declares perDl / perUl /
    harqReduction), the NR MAC node ids and the Simu5G per-UE H-ARQ scalars computed from the truth as LteHarqUnitTx
    emits them (every feedback: error 0/1 overall and per attempt; ACK: attempts; ACK or discard: packet loss 0/1)"""
    rows = ["version 3\n", f"scalar {NET}.gnb1.cellularNic.mac harqErrorRateDl:mean nan\n"]
    if ideal:
        rows += [f"par {NET}.gnb1.cellularNic.channelModel[0] typename \"\\\"simu5g.stack.phy.channelmodel.IdealChannelModel\\\"\"\n",
                 f"par {NET}.gnb1.cellularNic.channelModel[0] perDl 0\n", f"par {NET}.gnb1.cellularNic.channelModel[0] perUl 0\n"]
    for k, n in node.items():
        cm = f"{NET}.ue[{k}].cellularNic.nrChannelModel[0]"
        if ideal:
            rows += [f"par {cm} typename \"\\\"simu5g.stack.phy.channelmodel.IdealChannelModel\\\"\"\n",
                     f"par {cm} perDl {per_dl[k]}\n", f"par {cm} perUl 0\n", f"par {cm} harqReduction {1 if k == 1 else 0.3}\n"]
        else:
            rows += [f"par {cm} typename \"\\\"simu5g.stack.phy.channelmodel.Tr38901ChannelModel\\\"\"\n",
                     f"par {cm} harqReduction 0.2\n"]
        m = f"{NET}.ue[{k}].cellularNic.nrMac"
        fb = [x for x in truth if x["node"] == n]
        rows.append(f"par {m} macNodeId {n}\n")
        if not fb:
            continue
        err = [1 if x["res"] == "NACK" else 0 for x in fb]
        ack = [x["ntx"] for x in fb if x["res"] == "ACK"]
        loss = [1 if x["outcome"] == "discard" else 0 for x in fb if x["outcome"] in ("ack", "discard")]
        rows += [f"scalar {m} harqErrorRateDl:mean {repr(sum(err) / len(err))}\n",
                 f"scalar {m} harqTxAttemptsDl:mean {repr(sum(ack) / len(ack)) if ack else 'nan'}\n"]
        for a, o in V.ORD.items():
            e = [1 if x["res"] == "NACK" else 0 for x in fb if x["ntx"] == a]
            if e:
                rows.append(f"scalar {m} harqErrorRate_{o}_Dl:mean {repr(sum(e) / len(e))}\n")
        if loss:
            rows.append(f"scalar {m} macPacketLossDl:mean {repr(sum(loss) / len(loss))}\n")
    p = os.path.join(d, "0.sca")
    open(p, "w").writelines(rows)
    return p


def chain_nacks(chains, ttis=900, sched=None, extra=frozenset()):
    """the {(pid, attempt)} NACK set giving the i-th PDU of the nack UE n NACKed attempts, for every {i: n} in chains.
    A retransmission takes its UE's slot in that TTI and shifts later PDU ids, so the set is built in PDU order"""
    nk = set(extra)
    for i in sorted(chains):
        _, node, truth = F.make(2, ttis, sched or SCHED, nack=nk, d_ue=3)
        pids = []
        for x in truth:
            if x["node"] == node[1] and x["pid"] not in pids:
                pids.append(x["pid"])
        nk |= {(pids[i], a) for a in range(1, chains[i] + 1)}
    return nk


def build(chains=None, nack=None, ttis=900, ue_log=True, sched=None):
    nk = nack if nack is not None else chain_nacks(chains or {}, ttis, sched)
    lines, node, truth = F.make(2, ttis, sched or SCHED, nack=nk, d_ue=3, ue_log=ue_log)
    lines = TA.omnet(lines)
    return lines + [A2.sentinel(A2.t_end_of(lines))], node, truth


def evaluate(lines, node, sca_path, raw=Counter(), d=D):
    grants = TA.grants_of(lines)
    res, rows, per, cov, extra, window = C.evaluate(lines, 16, 1000 * MS, node, grants, sca_path, TA.root())
    vr = V.v_rows(res, rows, per, cov, lines, node, sca_path, raw, d)
    return res, rows, vr, grants


CHAINS = {i: 1 for i in range(3, 60, 6)}
CHAINS.update({70: 2, 80: 3, 90: 4, 100: 2})          # retransmission chains of 2 and 3 NACKs and one discard


@test("T-v1-accept: NACK chains on the nack UE only (single NACKs, 2- and 3-NACK chains, one discard) -> every required "
      "row PASS, D-1..D-3 PASS, S-1/S-2 PASS, verdict ACCEPTED (rc 0), every control AS DECLARED")
def _():
    lines, node, truth = build(CHAINS)
    d = tempfile.mkdtemp()
    try:
        sp = sca(d, node, truth)
        res, rows, vr, grants = evaluate(lines, node, sp)
        s = {r[0]: r[1] for r in vr}
        assert all(s[k] == "PASS" for k in V.REQUIRED), [r for r in vr if r[1] != "PASS"]
        assert s["D-1"] == "PASS" and s["D-3"] == "PASS" and s["S-1"] == "PASS" and s["S-2"] == "PASS", vr
        ctl = V.controls(lines, 16, 1000 * MS, node, grants, sp, TA.root(), Counter(), D)
        bad = [c for c in ctl if c[2] != "AS DECLARED"]
        assert not bad and len(ctl) == 7, ctl
        assert V.accept(vr, ctl)[1] == 0
    finally:
        shutil.rmtree(d)


@test("T-v1-stop-nonack: the same configuration records but no NACK at all -> V-1 FAIL, verdict STOP: NO NACK (rc 3); "
      "the NACK-dependent rows are NOT EXERCISED, never PASS")
def _():
    lines, node, truth = build({})
    d = tempfile.mkdtemp()
    try:
        res, rows, vr, _ = evaluate(lines, node, sca(d, node, truth))
        s = {r[0]: r[1] for r in vr}
        assert s["V-0"] == "PASS" and s["V-1"] == "FAIL", vr
        assert s["V-4"] == s["V-5"] == s["V-6"] == s["V-7"] == "NOT EXERCISED", vr
        assert V.accept(vr, [])[1] == 3
    finally:
        shutil.rmtree(d)


@test("T-v1-stop-baseline: records of the baseline channel model (no IdealChannelModel parameters) and no NACK, as the "
      "preserved N = 2 smoke -> V-0 FAIL, V-1 FAIL, verdict STOP (rc 4)")
def _():
    lines, node, truth = build({})
    d = tempfile.mkdtemp()
    try:
        res, rows, vr, _ = evaluate(lines, node, sca(d, node, truth, ideal=False))
        s = {r[0]: r[1] for r in vr}
        assert s["V-0"] == "FAIL" and s["V-1"] == "FAIL", vr
        assert V.accept(vr, [])[1] == 4
    finally:
        shutil.rmtree(d)


@test("T-v1-specificity: a NACK on the clean UE (A-2 still attributes it correctly) -> V-2 FAIL, verdict STOP: DESIGN "
      "NOT REALISED (rc 4); a UL NACK alone (full-log count) does the same")
def _():
    pids0 = [x["pid"] for x in F.make(2, 900, SCHED, d_ue=3)[2] if x["node"] == 2049]
    lines, node, truth = build(nack=chain_nacks(CHAINS, extra={(pids0[5], 1)}))
    d = tempfile.mkdtemp()
    try:
        res, rows, vr, _ = evaluate(lines, node, sca(d, node, truth))
        s = {r[0]: r[1] for r in vr}
        assert s["V-2"] == "FAIL" and s["V-3"] == "PASS", vr
        assert V.accept(vr, [])[1] == 4
        lines, node, truth = build(CHAINS)
        res, rows, vr, _ = evaluate(lines, node, sca(d, node, truth), raw=Counter({"UE UL H-ARQ TX feedback NACK": 1}))
        assert {r[0]: r[1] for r in vr}["V-2"] == "FAIL", vr
        res, rows, vr, _ = evaluate(lines, node, sca(d, node, truth), raw=None)
        assert {r[0]: r[1] for r in vr}["V-2"] == "FAIL", vr        # fail closed: UL never assumed clean
    finally:
        shutil.rmtree(d)


@test("T-v1-floor: fewer NACK lines than the declared floor (30 in the design) -> V-1 FAIL (STOP), even though A-2 is valid")
def _():
    lines, node, truth = build({3: 1, 9: 1})
    d = tempfile.mkdtemp()
    try:
        res, rows, vr, _ = evaluate(lines, node, sca(d, node, truth), d=V.DESIGN)
        s = {r[0]: r[1] for r in vr}
        assert s["V-1"] == "FAIL" and s["V-3"] == "PASS", vr
        assert V.accept(vr, [])[1] == 3
    finally:
        shutil.rmtree(d)


@test("T-v1-scalars: Simu5G statistics that disagree with the log -> V-8 FAIL (harqErrorRateDl) and S-1 FAIL (per "
      "attempt); a discard-free run leaves D-1 NOT EXERCISED and S-2 PASS (0 losses)")
def _():
    lines, node, truth = build({i: 1 for i in range(3, 60, 6)})
    d = tempfile.mkdtemp()
    try:
        sp = sca(d, node, truth)
        res, rows, vr, _ = evaluate(lines, node, sp)
        s = {r[0]: r[1] for r in vr}
        assert s["D-1"] == "NOT EXERCISED" and s["S-2"] == "PASS" and s["V-8"] == "PASS", vr
        txt = open(sp).read().replace("harqErrorRate_1st_Dl:mean 0.", "harqErrorRate_1st_Dl:mean 0.5")
        open(sp, "w").write(txt)
        s = {r[0]: r[1] for r in evaluate(lines, node, sp)[2]}
        assert s["S-1"] == "FAIL" and s["V-8"] == "PASS", s
    finally:
        shutil.rmtree(d)


@test("T-v1-noop: a control whose mutation changes nothing is MUTATION NOT APPLIED, never AS DECLARED (here: the "
      "rtxAcid control when the clean and the nack UE are the same node); a control without evidence is NOT BUILDABLE")
def _():
    lines, node, truth = build(CHAINS)
    d = tempfile.mkdtemp()
    try:
        sp = sca(d, node, truth)
        grants = TA.grants_of(lines)
        ctl = V.controls(lines, 16, 1000 * MS, {0: node[1], 1: node[1]}, grants, sp, TA.root(), Counter(), D)
        by = {c[0].split(":")[0]: c for c in ctl}
        assert by["NC-V-rtxacid"][2] == "MUTATION NOT APPLIED", by["NC-V-rtxacid"]
        assert V.accept([(k, "PASS", "") for k in V.REQUIRED], ctl)[1] == 1
        lines2, node2, truth2 = build({})
        ctl = V.controls(lines2, 16, 1000 * MS, node2, TA.grants_of(lines2), sca(d, node2, truth2), TA.root(), Counter(), D)
        by = {c[0].split(":")[0]: c for c in ctl}
        assert by["NC-V-unitline"][2] == by["NC-V-rtxacid"][2] == by["NC-V-uenack"][2] == "NOT BUILDABLE", ctl
    finally:
        shutil.rmtree(d)


@test("T-v1-frozen: the evaluator calls the frozen A-2 unchanged: its in-process A-2 rows equal check_m2s72_a2.py's own "
      "evaluate() on the same input, and the A-2 sources are byte-identical to fbee202")
def _():
    import subprocess
    lines, node, truth = build(CHAINS)
    d = tempfile.mkdtemp()
    try:
        sp = sca(d, node, truth)
        g = TA.grants_of(lines)
        a = C.evaluate(lines, 16, 1000 * MS, node, g, sp, TA.root())[1]
        b = evaluate(lines, node, sp)[1]
        assert a == b
    finally:
        shutil.rmtree(d)
    repo = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
    r = subprocess.run(["git", "-C", repo, "diff", "--quiet", "fbee2028b9c6ba5a992c0f14f85ef3729e2db107", "--",
                        "simulations/m2/check/m2s72_a2.py", "simulations/m2/check/check_m2s72_a2.py", "simulations/m2/check/m2s72_harqx.py",
                        "simulations/m2/check/m2s72_a2probe.py", "simulations/m2/check/m2s72_peru.py", "simulations/m2/check/test_m2s72_a2.py"])
    assert r.returncode == 0, "A-2 sources differ from fbee202"


@test("T-v1-cli: the command line on a runs directory laid out as the runner writes it (run-<cfg>.log.gz, "
      "<cfg>/<cfg>/0.sca) writes a2v1-<cfg>.txt / .json and exits with the verdict's code; an evaluation error is rc 2")
def _():
    lines, node, truth = build(CHAINS)
    d = tempfile.mkdtemp()
    cfg = "M2S72-E0vN-q0-one0-n2-f1_A2V1"
    try:
        runs = os.path.join(d, "runs")
        os.makedirs(os.path.join(runs, cfg, cfg))
        with gzip.open(os.path.join(runs, f"run-{cfg}.log.gz"), "wt") as fh:
            fh.writelines(x for x in lines if A2.SENTINEL_MOD not in x)
        sca(os.path.join(runs, cfg, cfg), node, truth)
        old, old_floor, old_root = C._node_ids, V.DESIGN["min_nack"], os.environ.get("SIMU5G_ROOT")
        C._node_ids = lambda runs_, cfg_: dict(node)        # the run's pcaps are not part of this fixture
        V.DESIGN["min_nack"] = 5                            # this fixture has about 20 NACKs (the design's floor is 30)
        os.environ["SIMU5G_ROOT"] = TA.root()
        try:
            rc = V.main(["x", "v1", runs, cfg, os.path.join(d, "rec"), "--a2-json", os.path.join(d, "none.json")])
            assert rc == 2
            C.a2(runs, cfg, os.path.join(d, "a2"), t0=1000 * MS)
            rc = V.v1(runs, cfg, os.path.join(d, "rec"), os.path.join(d, "a2", f"a2-{cfg}.json"), t0=1000 * MS)
        finally:
            C._node_ids, V.DESIGN["min_nack"] = old, old_floor
            if old_root is None:
                os.environ.pop("SIMU5G_ROOT")
            else:
                os.environ["SIMU5G_ROOT"] = old_root
        txt = open(os.path.join(d, "rec", f"a2v1-{cfg}.txt")).read()
        assert rc == 0 and "V-a2" in txt and "ACCEPTED" in txt, txt[-1500:]
    finally:
        shutil.rmtree(d)


@test("T-v1-risk-R1 (declared before the run, design review §5.3): a log that ends between a NACK and its retransmission "
      "makes the FROZEN A-2's A2-0 FAIL (probe P0-3 'open at the end in state BUF') although A-2's own replay censors the "
      "unit ('censored: awaiting retransmission'); the evaluator then reports V-3 FAIL and NOT ACCEPTED, and is not adjusted")
def _():
    lines, node, truth = build(CHAINS)
    nk = [x for x in truth if x["res"] == "NACK" and x["outcome"] == "rtx"][-1]
    cut = [x for x in lines if A2.SENTINEL_MOD not in x and PR_t(x) <= nk["t"]]
    i = max(j for j, x in enumerate(cut) if "result is NACK" in x)
    cut = cut[:i + 1]
    cut = cut + [A2.sentinel(A2.t_end_of(cut))]
    d = tempfile.mkdtemp()
    try:
        res, rows, vr, _ = evaluate(cut, node, sca(d, node, [x for x in truth if x["t"] <= nk["t"]]))
        a = {r[0]: r[2] for r in rows}
        assert a["A2-0"] == "FAIL" and "P0-3 FAILS" in [r[3] for r in rows if r[0] == "A2-0"][0], rows[0]
        assert res["end_states"].get("censored: awaiting retransmission") == 1, res["end_states"]
        s = {r[0]: r[1] for r in vr}
        assert s["V-3"] == "FAIL" and V.accept(vr, [])[1] == 1, vr
    finally:
        shutil.rmtree(d)


def PR_t(x):
    return A2.PR.t_ps(x.split("|", 1)[0])


def main():
    fails = 0
    for name, f in TESTS:
        try:
            f()
            print(f"PASS  {name}")
        except Exception as ex:
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {name}: {type(ex).__name__}: {str(ex)[:600]}")
    print(f"{len(TESTS) - fails} / {len(TESTS)} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
