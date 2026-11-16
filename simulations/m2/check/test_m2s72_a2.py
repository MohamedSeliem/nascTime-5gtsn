#!/usr/bin/env python3
"""Tests of the DL H-ARQ attribution rule A-2 (m2s72_a2.py, check_m2s72_a2.py). No simulation, no raw output.
Truth comes from the source-faithful generator m2s72_harqfix.make() (synthetic; labelled as such). The real-output
validation is the VM protocol (results/M2-S7.2a-a2-implementation.md §6)."""
import gzip
import os
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import check_m2s72_a2 as C  # noqa: E402
import m2s72_a2 as A2  # noqa: E402
import m2s72_a2probe as PR  # noqa: E402
import m2s72_harqfix as F  # noqa: E402
import m2s72_peru as P  # noqa: E402

TESTS = []
MS = F.MS
SCRATCH_SRC = "/tmp/claude-0/-home-claude/f08b3521-4dd6-5494-b405-fc45c61f17fc/scratchpad/src/simu5g-1.8.1"
NACKS = {(805, 1), (805, 2), (805, 3), (805, 4), (830, 1), (861, 1)}


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def root():
    r = os.environ.get("SIMU5G_ROOT", "")
    return r if r and os.path.isdir(os.path.join(r, "src", "simu5g")) else (SCRATCH_SRC if os.path.isdir(SCRATCH_SRC) else None)


def grants_of(lines):
    import test_m2s72s5_n2 as T
    return T.grants_of(lines)


def fixture(n_ue=2, ttis=400, sched=None, **kw):
    sched = sched or (lambda t: [0] + ([1] if t % 7 == 3 else []))
    lines, node, truth = F.make(n_ue, ttis, sched, **kw)
    return lines + [A2.sentinel(A2.t_end_of(lines))], node, truth


def evaluate(lines, node, nproc=16, sca=None, t0=1000 * MS):
    return C.evaluate(lines, nproc, t0, node, grants_of(lines), sca, root())


def st(rows):
    return {r[0]: r[2] for r in rows}


def truth_occupancy(lines, truth, nodes, nproc, window):
    import proto_m2s72_a2 as PA
    hist = PA.truth_hist(lines, truth)
    out = {}
    for n in nodes:
        out[n] = P.occupancy_log_order(sorted((i, t, d) for i, t, nn, d in hist if nn == n), nproc, (window[0] // MS, window[1] // MS))
    return out


# ------------------------------------------------------------------------------------------------ contracts ------
@test("T-contract: A-2 reads the contract-tested patterns (probe = adapter for insert / feedback); every text A-2 relies "
      "on is present verbatim in the Simu5G 1.8.1 tree ($SIMU5G_ROOT on the VM) - A2-0s PASS; NOT EVALUATED without a tree")
def _():
    import m2s72_peru_adapter as AD
    assert PR.R_INSERT.pattern == AD.R_INSERT.pattern and PR.R_FB.pattern == AD.R_FB.pattern
    r = root()
    row = A2.source_row(r)
    if r is None:
        assert row[2] == A2.NE, row
        print("    (no Simu5G source tree here: A2-0s NOT EVALUATED, as declared)")
        return
    assert row[2] == "PASS", row
    assert A2.source_row(os.path.join(tempfile.gettempdir(), "no-such-tree"))[2] == A2.NE


@test("T-load: load() keeps exactly the lines A-2 / XA / P0 read plus an end-of-log sentinel; P0 on the loaded lines "
      "equals P0 on the full log (the preserved-output V-B / V-C results stay comparable)")
def _():
    lines, node, truth = F.make(2, 300, lambda t: [0] + ([1] if t % 7 == 3 else []), nack=NACKS)
    noise = [x.split("|")[0] + "|M2S72Bridge.gnb1.cellularNic.mac|LteAllocator: noise line\n" for x in lines[::50]]
    full = sorted(lines + noise, key=lambda x: PR.t_ps(x.split("|")[0]))
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "run.log.gz")
        with gzip.open(p, "wt") as fh:
            fh.writelines(full)
        ld = A2.load(p)
        assert ld[-1].split("|")[1] == A2.SENTINEL_MOD and PR.t_ps(ld[-1].split("|")[0]) == A2.t_end_of(full)
        assert not any("noise line" in x for x in ld)
        a, b = PR.census(lines=full), PR.census(lines=ld)
        assert a["preconditions"] == b["preconditions"] and a["counts"] == b["counts"] and a["groups"] == b["groups"], (a, b)
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------- truth (synthetic) ----------
def check_against_truth(lines, node, truth, nproc):
    res = A2.replay(lines)
    assert not res["viol"], {k: v[:2] for k, v in res["viol"].items()}
    assert len(res["fb"]) == len(truth)
    for g in res["groups"]:
        js = [x["j"] for x in g["lines"]]
        if g["exchangeable"]:
            acks = [x for x in g["lines"] if x["cls"] == "exchangeable"]
            assert sorted(x["owner"] for x in acks) == sorted(truth[x["j"]]["node"] for x in acks), g
        for x in g["lines"]:
            if x["cls"] in ("id", "single"):
                assert x["owner"] == truth[x["j"]]["node"] and x["pid"] == truth[x["j"]]["pid"], (x, truth[x["j"]])
        assert all(res["fb"][j]["cls"] in ("id", "single", "exchangeable") for j in js)
    # per UE: feedback, NACK, discards, transmissions per ACKed PDU
    agg_a, agg_t = Counter(), Counter()
    for x in res["fb"]:
        agg_a[(x["owner"], x["res"])] += 1
    for x in truth:
        agg_t[(x["node"], x["res"])] += 1
    assert agg_a == agg_t
    disc_t = Counter(x["node"] for x in truth if x["outcome"] == "discard")
    disc_a = Counter(u["node"] for u in res["pdus"].values() if u["end"] == "discard")
    assert disc_a == disc_t
    ntx_t = Counter((x["node"], x["ntx"]) for x in truth if x["outcome"] == "ack")
    ntx_a = Counter((u["node"], u["ntx"]) for u in res["pdus"].values() if u["end"] == "ack")
    assert ntx_a == ntx_t
    window = (min(PR.t_ps(x.split("|")[0]) for x in lines), (res["t_end"] // MS + 1) * MS)
    per = A2.per_ue(res, nproc, window)
    occ_t = truth_occupancy(lines, truth, sorted(node.values()), nproc, window)
    assert {n: per[n]["occupancy"] for n in per} == occ_t
    assert len(res["ages"]) == 1
    return res


@test("T-sweep (synthetic): A-2 equals the generator truth in all 48 scenarios (N 2..4, HARQ 5 / 16, both event orders, "
      "NACK 0..5 % with discard chains and mixed groups): every id / single line names the true UE and PDU, every "
      "exchangeable group holds the true owners, per-UE feedback / NACK / discard / transmissions, per-UE log-order "
      "occupancy and one d*_tx; no violation")
def _():
    import random
    rnd = random.Random(20261116)
    n = 0
    for n_ue in (2, 3, 4):
        for nproc in (16, 5):
            for fb_first in (True, False):
                for rate in (0.0, 0.002, 0.02, 0.05):
                    probs = [0.97] + [rnd.choice([0.05, 0.2, 0.5]) for _ in range(n_ue - 1)]
                    sched = lambda tti, pr=probs, sd=n_ue: [k for k, q in enumerate(pr) if random.Random(tti * 7919 + sd * 31 + k).random() < q]  # noqa: E731
                    nack = {(x, a) for x in range(800, 3800) for a in (1, 2, 3, 4) if rnd.random() < rate}
                    lines, node, truth = fixture(n_ue, 600, sched, nack=nack, nproc=nproc, fb_first=fb_first, ue_log=False)
                    check_against_truth(lines, node, truth, nproc)
                    n += 1
    assert n == 48


@test("T-proto (synthetic): two implementations of one specification agree - A-2 (from the spec) and the design "
      "prototype (proto_m2s72_a2) give the same owner per id / single line and the same group node sets, on the sweep's "
      "NACK scenarios")
def _():
    import proto_m2s72_a2 as PA
    for rate_seed in (1, 2, 3):
        import random
        rnd = random.Random(rate_seed)
        nack = {(x, a) for x in range(800, 2000) for a in (1, 2, 3, 4) if rnd.random() < 0.03}
        lines, node, truth = fixture(3, 500, lambda t: [0] + ([1] if t % 3 == 1 else []) + ([2] if t % 4 == 2 else []), nack=nack, ue_log=False)
        res = A2.replay(lines)
        pl, _, probs = PA.attribute(lines)
        assert not probs and len(pl) == len(res["fb"])
        for a, b in zip(res["fb"], pl):
            if a["cls"] in ("id", "single"):
                assert a["owner"] == b["owner"] and b["kind"] in ("id", "single"), (a, b)
            else:
                assert b["kind"] == "group" and a["cls"] == "exchangeable"


@test("T-nack (synthetic): a discard chain, single NACKs and a NACK inside a same-TTI group - rows A2-0..A2-7 PASS, "
      "A2-4 PASS (each retransmission named by the scheduler), the NACKed unit stays busy until its final ACK, "
      "coverage reports the NACK features exercised")
def _():
    lines, node, truth = fixture(2, 400, nack=NACKS)
    res, rows, per, cov, extra, window = evaluate(lines, node)
    s = st(rows)
    assert all(s[r] == "PASS" for r in ("A2-0", "A2-1", "A2-2", "A2-3", "A2-4", "A2-5", "A2-6", "A2-7")), rows
    assert A2.verdict(rows)[0] == "A-2 VALID" or s["A2-0s"] == A2.NE
    c = {name: n for name, n, cls in cov}
    assert c["NACK identified by PDU id"] == 6 and c["discard after maxHarqRtx + 1 transmissions"] == 1 and c["mixed ACK / NACK groups"] >= 1
    u = res["pdus"][805]
    assert u["end"] == "discard" and u["ntx"] == 4 and [r for _, r in u["fbs"]] == ["NACK"] * 4
    # busy from insert to the discard line: the occupancy event list of the node holds +1 at its insert and -1 at the discard
    # four transmissions, each fed back d*_tx later (the generator retransmits in the NACK's own TTI: feedback first)
    assert u["close_gi"] > u["ins_gi"] and [b - a for a, b in zip(u["txs"], u["txs"][1:])] == [res["d_star"]] * 3
    assert u["t_close"] - u["t_ins"] == 4 * res["d_star"]
    occ = per[node[0]]["occupancy"]
    assert occ["max_peak"] >= 1


@test("T-discard (synthetic): a discard after fewer than maxHarqRtx + 1 transmissions fails A2-2; the text's own "
      "maxHarqRtx value is used")
def _():
    lines, node, truth = fixture(2, 200, nack={(805, 1), (805, 2), (805, 3), (805, 4)})
    i = next(i for i, x in enumerate(lines) if "PDU 805 set for RTX" in x)
    bad = list(lines)
    bad[i] = bad[i].replace("set for RTX ", "discarded (max retransmissions reached) : 3")
    s = st(evaluate(bad, node)[1])
    assert s["A2-2"] == "FAIL", s
    j = next(i for i, x in enumerate(lines) if "PDU 805 discarded" in x)
    bad = list(lines)
    bad[j] = bad[j].replace(": 3", ": 4")
    assert st(evaluate(bad, node)[1])["A2-2"] == "FAIL"


@test("T-censor (synthetic): end-of-run censoring - a log cut right after a NACK (awaiting retransmission), right after "
      "an insert line (inserted in the last TTI) and at a TTI boundary (awaiting feedback): no row FAILS and each unit "
      "gets its censored state; the same unit open long before the end FAILS A2-2")
def _():
    lines, node, truth = fixture(2, 300, nack={(830, 1)})
    i = next(i for i, x in enumerate(lines) if "feedback received for process" in x and "NACK" in x)
    cut = lines[:i + 1]
    cut.append(A2.sentinel(A2.t_end_of(cut)))
    res = A2.replay(cut)
    assert res["end_states"].get("censored: awaiting retransmission") == 1 and not res["viol"], (res["end_states"], res["viol"])
    k = [i for i, x in enumerate(lines) if "inserted into process" in x and "H-ARQ TX" in x][150]
    cut = lines[:k + 1]
    cut.append(A2.sentinel(A2.t_end_of(cut)))
    res = A2.replay(cut)
    assert res["end_states"].get("censored: inserted in the last TTI") == 1 and not res["viol"], (res["end_states"], res["viol"])
    assert res["end_states"].get("censored: awaiting feedback", 0) >= 1
    tc = PR.t_ps(lines[len(lines) // 2].split("|")[0]) // MS * MS
    cut = [x for x in lines if PR.t_ps(x.split("|")[0]) < tc]
    cut.append(A2.sentinel(A2.t_end_of(cut)))
    res, rows, per, cov, extra, _ = C.evaluate(cut, 16, 1000 * MS, node, [g for g in grants_of(lines) if g[0] < tc], None, root())
    assert not [r for r in rows if r[2] == "FAIL"], rows
    assert res["end_states"].get("censored: awaiting feedback", 0) >= 1
    # a unit that stays open: its feedback event removed far from the end -> not censored
    fbi = next(i for i, x in enumerate(lines) if "feedback received for process" in x and PR.t_ps(x.split("|")[0]) > 1100 * MS)
    s0 = max(i for i in range(fbi) if PR.T_START in lines[i])
    res = A2.replay(lines[:s0] + lines[fbi + 1:])
    assert res["viol"].get("A2-2"), res["end_states"]


@test("T-cert (synthetic, N = 3): the exchangeability certificate is exact in both directions - a new transmission of "
      "a NON-candidate UE logged inside a two-candidate ACK group is admissible (A2-5 does not fail: no false alarm), "
      "the same event of a CANDIDATE UE fails A2-5")
def _():
    lines, node, truth = fixture(3, 300, lambda t: [0] + ([1] if t % 7 == 3 else []) + ([2] if t % 11 == 5 else []))
    res = A2.replay(lines)
    g = next(g for g in res["groups"] if g["exchangeable"] and len(g["cands"]) == 2)
    cand = {k[0] for k in g["cands"]}
    outsider = next(n for n in node.values() if n not in cand)
    pos = C.gnb_positions(lines)
    a = pos[g["lines"][0]["gi"]]
    tg = C._ts(g["t"])

    def with_tx(nd):
        extra = [f"{tg}|{A2.GNB}|H-ARQ TX: new pdu (id 999999 ) inserted into process 15 codeword id: 0 for node with id {nd}\n",
                 f"{tg}|{A2.GNB}|\t H-ARQ TX: pdu (id 999999 ) extracted from process 15 codeword 0 for node with id {nd}\n"]
        return A2.replay(lines[:a + 1] + extra + lines[a + 1:])["viol"]
    assert not with_tx(outsider).get("A2-5"), with_tx(outsider).get("A2-5")
    assert with_tx(sorted(cand)[0]).get("A2-5")
    # a main-loop event on a candidate UNIT itself between the group's lines resolves the group early: its later line
    # is reported as a split group (A2-5), besides the count mismatch (A2-1)
    k = g["cands"][0]
    split = lines[:a + 1] + [f"{tg}|{A2.GNB}|H-ARQ TX: new pdu (id 999997 ) inserted into process {k[1]} codeword id: {k[2]} for node with id {k[0]}\n"] + lines[a + 1:]
    vv = A2.replay(split)["viol"]
    assert any("split" in m for m in vv.get("A2-5", [])) and vv.get("A2-1"), vv


@test("T-xa (synthetic): A2-7 compares with the independent UE-side reference - PASS on NACK / discard fixtures; FAIL "
      "when A-2's owner of one line is wrong (a deliberately broken A-2) and when the reference's own evidence is "
      "broken; NOT EVALUATED without UE-side lines")
def _():
    lines, node, truth = fixture(2, 400, nack=NACKS)
    assert st(evaluate(lines, node)[1])["A2-7"] == "PASS"
    res = A2.replay(lines)
    x = next(x for x in res["fb"] if x["cls"] == "single")
    x["owner"] = 2049 if x["owner"] == 2050 else 2050
    window = (1000 * MS, (res["t_end"] // MS + 1) * MS)
    per = A2.per_ue(res, 16, window)
    r7, _ = A2.xa_rows(res, lines, node, 16, window, per)
    assert r7[2] == "FAIL", r7
    # a per-line error that leaves every per-UE aggregate unchanged: two single ACK lines of different UEs (equal
    # latency) exchange owners; only the line-by-line comparison can see it
    res = A2.replay(lines)
    a = next(x for x in res["fb"] if x["cls"] == "single" and x["owner"] == 2049 and x["t"] - x["t_ins"] == res["d_star"])
    b = next(x for x in res["fb"] if x["cls"] == "single" and x["owner"] == 2050 and x["t"] - x["t_ins"] == res["d_star"])
    a["owner"], b["owner"] = b["owner"], a["owner"]
    a["t_ins"], b["t_ins"] = a["t"] - res["d_star"], b["t"] - res["d_star"]
    r7, _ = A2.xa_rows(res, lines, node, 16, window, A2.per_ue(res, 16, window))
    assert r7[2] == "FAIL" and "line " in r7[3], r7
    j = next(i for i, y in enumerate(lines) if "H-ARQ RX: new PDU" in y and ".ue[1]." in y)
    bad = list(lines)
    bad[j] = bad[j].replace(".ue[1].", ".ue[0].")
    assert st(evaluate(bad, node)[1])["A2-7"] == "FAIL"
    noue = [y for y in lines if ".ue[" not in y]
    assert st(evaluate(noue, node)[1])["A2-7"] == A2.NE


@test("T-scalars: A2-8 against Simu5G's own per-UE statistics - PASS when harqErrorRateDl:mean = NACK / feedback and "
      "harqTxAttemptsDl:mean = mean transmissions per ACKed PDU for each UE node (from the .sca macNodeId parameters); "
      "FAIL on a perturbed value; NOT EVALUATED without scalars")
def _():
    lines, node, truth = fixture(2, 400, nack=NACKS)
    res = A2.replay(lines)
    d = tempfile.mkdtemp()
    try:
        sca = os.path.join(d, "0.sca")
        rows = ["version 3\n"]
        for k, n in node.items():
            mod = f"M2S72Bridge.ue[{k}].cellularNic.nrMac"
            fbk = [x for x in res["fb"] if x["owner"] == n]
            ack = [u["ntx"] for u in res["pdus"].values() if u["node"] == n and u["end"] == "ack"]
            rows += [f"par {mod} macNodeId {n}\n", f"scalar {mod} harqErrorRateDl:mean {sum(x['res'] == 'NACK' for x in fbk) / len(fbk):.15g}\n",
                     f"scalar {mod} harqTxAttemptsDl:mean {sum(ack) / len(ack):.15g}\n"]
        open(sca, "w").writelines(rows)
        assert A2.scalar_row(res, sca)[0][2] == "PASS", A2.scalar_row(res, sca)
        open(sca, "w").writelines([r.replace("harqErrorRateDl:mean 0.", "harqErrorRateDl:mean 0.5") if "ue[0]" in r else r for r in rows])
        assert A2.scalar_row(res, sca)[0][2] == "FAIL"
        assert A2.scalar_row(res, os.path.join(d, "none.sca"))[0][2] == A2.NE
    finally:
        shutil.rmtree(d)


@test("T-controls (synthetic stand-in for the real output): every buildable control of a2-controls is AS DECLARED, "
      "including the NACK-path controls on an injected chain; a run whose UE reuses its process too soon reports the "
      "injection NOT BUILDABLE (never a pass)")
def _():
    lines, node, truth = fixture(2, 600, lambda t: [0] + ([1] if t % 15 == 3 else []), d_ue=3)
    out, st0 = C.controls(lines, 16, 1000 * MS, node, grants_of(lines), None, root())
    built = [x for x in out if x[2] != "NOT BUILDABLE"]
    assert all(x[2] == "AS DECLARED" for x in built), [x for x in built if x[2] != "AS DECLARED"]
    names = [x[0].split(":")[0] for x in built]
    for nm in ("PC-A2-unmodified", "NC-A2-shift", "NC-A2-dupack", "NC-A2-dropfb", "NC-A2-dropunit", "NC-A2-extract", "NC-A2-dupins",
               "NC-A2-swap", "NC-A2-xa", "NC-A2-grant", "PC-A2-censor", "PC-A2-inject", "NC-A2-nackid", "NC-A2-nackswap",
               "NC-A2-rtxacid", "NC-A2-rtxextract", "NC-A2-discard"):
        assert nm in names, (nm, names)
    lines, node, truth = fixture(2, 600, lambda t: [0] + ([1] if t % 7 == 3 else []), d_ue=3)
    out, st0 = C.controls(lines, 16, 1000 * MS, node, grants_of(lines), None, root())
    assert any(x[0].startswith("PC-A2-inject") and x[2] == "NOT BUILDABLE" for x in out)
    assert any(x[0].startswith("NC-A2-cert") and x[2] == "AS DECLARED" for x in out)


@test("T-verdict / coverage: A-2 VALID only when every required row is PASS or NOT EXERCISED; any FAIL -> NOT VALID; a "
      "required NOT EVALUATED -> INCOMPLETE. On an ACK-only run every NACK feature is reported NOT EXERCISED with "
      "where it is validated instead; nothing is claimed beyond the run")
def _():
    rows = [(r, "run", "PASS", "") for r in A2.REQUIRED] + [("A2-8", "run", A2.NE, "")]
    assert A2.verdict(rows) == ("A-2 VALID", 0)
    assert A2.verdict(rows[:3] + [("A2-2", "run", "FAIL", "")] + rows[4:])[0] == "A-2 NOT VALID"
    assert A2.verdict([x if x[0] != "A2-7" else ("A2-7", "run", A2.NE, "") for x in rows])[0] == "A-2 INCOMPLETE"
    assert A2.verdict([x if x[0] != "A2-4" else ("A2-4", "run", A2.NX, "") for x in rows])[0] == "A-2 VALID"
    assert A2.verdict(rows[:-1] + [("A2-8", "run", "FAIL", "")])[0] == "A-2 NOT VALID"
    lines, node, truth = fixture(2, 300)
    res, rows, per, cov, extra, _ = evaluate(lines, node)
    cv = {name: cls for name, n, cls in cov}
    for nm in ("NACK identified by PDU id", "retransmission state / retransmissions", "discard after maxHarqRtx + 1 transmissions",
               "mixed ACK / NACK groups", "end-of-run censoring: awaiting retransmission"):
        assert cv[nm].startswith("NOT EXERCISED") and "synthetic" in cv[nm], (nm, cv[nm])
    assert cv["exchangeable ACK groups (2 candidates)"].startswith("VALIDATED ON REAL OUTPUT")
    assert "PU-4" in A2.NOTE and "reclassify" in A2.NOTE


@test("T-cli: a2 and a2-controls end to end on a synthetic run tree (gzip log, .sca with macNodeId and the Simu5G "
      "per-UE scalars): exit 0; records a2-<cfg>.txt / .json and a2-controls-<cfg>.txt / .json written, with the PU-4 "
      "note and the coverage table")
def _():
    lines, node, truth = F.make(2, 500, lambda t: [0] + ([1] if t % 15 == 3 else []), d_ue=3)
    res = A2.replay(lines + [A2.sentinel(A2.t_end_of(lines))])
    d = tempfile.mkdtemp()
    try:
        cfg = "M2S72-E0vN-q0-one0-n2-f1"
        runs = os.path.join(d, "runs")
        os.makedirs(os.path.join(runs, cfg, cfg))
        with gzip.open(os.path.join(runs, f"run-{cfg}.log.gz"), "wt") as fh:
            fh.writelines(lines)
        rows = ["version 3\n"]
        for k, n in node.items():
            mod = f"M2S72Bridge.ue[{k}].cellularNic.nrMac"
            rows += [f"par {mod} macNodeId {n}\n", f"scalar {mod} harqErrorRateDl:mean 0\n", f"scalar {mod} harqTxAttemptsDl:mean 1\n"]
        open(os.path.join(runs, cfg, cfg, "0.sca"), "w").writelines(rows)
        env = dict(os.environ)
        if root():
            env["SIMU5G_ROOT"] = root()
        for cmd, out in (("a2", f"a2-{cfg}"), ("a2-controls", f"a2-controls-{cfg}")):
            r = subprocess.run([sys.executable, "-B", os.path.join(HERE, "check_m2s72_a2.py"), cmd, runs, cfg, os.path.join(d, "rec"), "--t0", "1"],
                               capture_output=True, text=True, env=env)
            assert r.returncode == (0 if root() or cmd == "a2-controls" else 4), (cmd, r.returncode, r.stdout[-1500:])
            assert os.path.exists(os.path.join(d, "rec", out + ".txt")) and os.path.exists(os.path.join(d, "rec", out + ".json"))
        txt = open(os.path.join(d, "rec", f"a2-{cfg}.txt")).read()
        assert "PU-4 FAIL of rule A-1 stands unchanged" in txt and "COVERAGE" in txt and "A2-8" in txt
        assert "PASS            | A2-8" in txt, txt[:3000]
        ctl = open(os.path.join(d, "rec", f"a2-controls-{cfg}.txt")).read()
        assert "NC-A2-scalar" in ctl and "PC-A2-inject" in ctl
    finally:
        shutil.rmtree(d)


@test("T-scope: vs 07b09b9 this increment only adds files; A-1 (m2s72_peru), the adapter, XA, the s5v / s5n / s5n2 "
      "checkers, the runner, configurations and every record are byte-identical")
def _():
    out = subprocess.run(["git", "-C", HERE, "diff", "--name-status", "07b09b9", "--", ".."], capture_output=True, text=True, check=True).stdout
    assert [x for x in out.splitlines() if x and not x.startswith("A")] == [], out


def main():
    ok = 0
    for name, f in TESTS:
        try:
            f()
            print(f"PASS | {name}")
            ok += 1
        except Exception as ex:
            import traceback
            print(f"FAIL | {name}: {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1200:]}")
    print(f"A-2 tests: {ok} / {len(TESTS)} PASS")
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
