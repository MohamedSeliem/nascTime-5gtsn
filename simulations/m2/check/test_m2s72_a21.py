#!/usr/bin/env python3
"""Tests of A-2.1 (m2s72_a21.py, check_m2s72_a21.py, m2s72_harqfix21.py). No simulation, no raw output of any run.
Truth: the corrected generator m2s72_harqfix21.make() (synthetic, labelled) and the frozen generator for ACK-only input.
The REAL first-chain fixture (fixtures/a2v1-first-chain.log.gz, extracted read-only from the sealed A2-V1 output) is
not in this repository yet: its test reports PENDING (never PASS) until the fixture and its pinned sha256 are added."""
import gzip
import os
import random
import shutil
import subprocess
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import check_m2s72_a2 as C  # noqa: E402  (frozen)
import check_m2s72_a21 as CC  # noqa: E402
import m2s72_a2 as A2  # noqa: E402  (frozen)
import m2s72_a21 as A  # noqa: E402
import m2s72_harqfix as F  # noqa: E402  (frozen generator)
import m2s72_harqfix21 as G  # noqa: E402
import test_m2s72_a2 as TA  # noqa: E402
import test_m2s72_a2v1 as TV  # noqa: E402

TESTS = []
MS, S = G.MS, G.S
FROZEN = "fbee2028b9c6ba5a992c0f14f85ef3729e2db107"
FIX = os.path.join(HERE, "fixtures", "a2v1-first-chain.log.gz")
PENDING = []


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def fin(lines):
    lines = TA.omnet(lines)
    return lines + [A.sentinel(A.t_end_of(lines))]


def ev21(lines, node, nproc=16, sca=None, t0=1000 * MS):
    return A.evaluate(lines, nproc, t0, node, TA.grants_of(lines), sca, TA.root())


def ev2(lines, node, nproc=16, sca=None, t0=1000 * MS):
    return C.evaluate(lines, nproc, t0, node, TA.grants_of(lines), sca, TA.root())


def st(rows):
    return {r[0]: r[2] for r in rows}


def sched3(t):
    return [0] + ([1] if t % 3 == 1 else [])


def chain_nacks(chains, n_ue=2, ttis=300, sched=sched3, k=1, extra=(), **kw):
    """{i: n}: the i-th PDU of UE k NACKed on its first n attempts (n = 4: discarded); built in PDU order"""
    nk = set(extra)
    for i in sorted(chains):
        _, node, tr = G.make(n_ue, ttis, sched, nack=nk, tail=40, **kw)
        pids = []
        for x in tr:
            if x["node"] == node[k] and x["pid"] not in pids:
                pids.append(x["pid"])
        nk |= {(pids[i], a) for a in range(1, chains[i] + 1)}
    return nk


def build(chains, n_ue=2, ttis=300, sched=sched3, k=1, extra=(), **kw):
    nk = chain_nacks(chains, n_ue, ttis, sched, k, extra, **{x: v for x, v in kw.items() if x != "tail"})
    lines, node, truth = G.make(n_ue, ttis, sched, nack=nk, tail=kw.pop("tail", 40), **kw)
    return fin(lines), node, truth


def recon():
    """synthetic RECONSTRUCTION of the first real chain (VM-reported facts): node 2050's MAC PDU 145933 on process 0 at
    361 ms, handle 54326, NACKs at 366 / 372 / 378, retransmissions at 367 / 373 / 379, ACK at 384; node 2049's
    concurrent units on process 0 ACKed in the same groups (mixed groups). Labelled synthetic: NOT the real fixture."""
    def sched(t):
        return [0] if t != 361 else [0, 1]
    _, node, tr = G.make(2, 90, sched, t0=301, tail=40)
    first = next(x for x in tr if x["node"] == 2050)
    pid, h = first["pid"], first["handle"]
    lines, node, truth = G.make(2, 90, sched, nack={(pid, 1), (pid, 2), (pid, 3)}, t0=301, tail=40)
    lines = [y.replace(f"(id {pid} )", "(id 145933 )").replace(f"PDU {h} ", "PDU 54326 ") for y in lines]
    for x in truth:
        if x["pid"] == pid:
            x["pid"], x["handle"] = 145933, 54326
    return fin(lines), node, truth


# ------------------------------------------------------------------------------------------- frozen intact ------
@test("T-frozen-untouched: the frozen A-2 sources and its generator are byte-identical to fbee202 (A-2.1 adds files only)")
def _():
    repo = os.path.abspath(os.path.join(HERE, "..", "..", ".."))
    files = [f"simulations/m2/check/{f}" for f in ("m2s72_a2.py", "check_m2s72_a2.py", "m2s72_a2probe.py", "m2s72_harqfix.py",
                                                   "m2s72_harqx.py", "m2s72_peru.py", "test_m2s72_a2.py", "check_m2s72_a2v1.py")]
    r = subprocess.run(["git", "-C", repo, "diff", "--quiet", FROZEN, "--"] + files[:7])
    assert r.returncode == 0, "frozen A-2 files differ from fbee202"
    r = subprocess.run(["git", "-C", repo, "diff", "--quiet", "39a64348701fe14bb838964a113a278ecaf747e9", "--", files[7]])
    assert r.returncode == 0, "the A2-V1 evaluator differs from the reviewed 39a6434"


# ------------------------------------------------------------------------------------------ ACK-only identity ----
def identity(lines, node, nproc=16, sca=None):
    f = ev2(lines, node, nproc, sca)
    n = ev21(lines, node, nproc, sca)
    fr, nr = {r[0]: r for r in f[1]}, {r[0]: r for r in n[1]}
    diff = [(k, fr[k][2:], nr.get(k, ("", "", "-", "-"))[2:]) for k in fr if k != "A2-4" and fr[k] != nr.get(k)]
    a4 = (fr["A2-4"][2] == NX_) == all(nr[k][2] == NX_ for k in ("A2-4a", "A2-4b", "A2-4c"))
    return diff, f[2] == n[2], a4, nr["A2-9"][2], f, n


NX_ = A.NX


@test("T-ackonly-identity: on ACK-only input (frozen generator; N 1-4; process counts 5 / 16; feedback before / after the "
      "main loop; with / without UE lines and a .sca) every frozen row except A2-4 is byte-identical (status and detail), "
      "the per-UE outputs are identical, A2-4 NOT EXERCISED <=> A2-4a/b/c NOT EXERCISED, A2-9 PASS")
def _():
    scheds = [lambda t: [0] + ([1] if t % 7 == 3 else []), lambda t: [0, 1], lambda t: [0, 1, 2] if t % 2 else [1],
              lambda t: [3, 2, 1, 0] if t % 5 else [0]]
    d = tempfile.mkdtemp()
    try:
        n_cases = 0
        for n in (1, 2, 3, 4):
            for si, sch in enumerate(scheds):
                for nproc in (16, 5):
                    for fb_first in (True, False):
                        lines, node, truth = F.make(n, 250, sch, nproc=nproc, fb_first=fb_first, ue_log=(si != 3))
                        lines = lines + [A2.sentinel(A2.t_end_of(lines))]
                        sca = sca2(d, node, truth) if (si == 1 and n == 2) else None
                        diff, peq, a4, a9, f, nn = identity(lines, node, nproc, sca)
                        assert not diff and peq and a4 and a9 == "PASS", (n, si, nproc, fb_first, diff[:2], peq, a4, a9)
                        n_cases += 1
        assert n_cases == 64
    finally:
        shutil.rmtree(d)


@test("T-ackonly-identity-gen21: ACK-only input in the corrected model (main-loop markers, feedback after the main loop) "
      "is also row-identical between the frozen A-2 and A-2.1 (markers never change an ACK-only row)")
def _():
    for n, sch in ((1, lambda t: [0]), (2, sched3), (3, lambda t: [0, 1, 2] if t % 2 else [2])):
        lines, node, truth = G.make(n, 250, sch)
        lines = fin(lines)
        diff, peq, a4, a9, f, nn = identity(lines, node)
        assert not diff and peq and a4 and a9 == "PASS", (n, diff[:2])


@test("T-ackonly-mutations: on the frozen controls' ACK-only mutations (shift, dupack, dropfb, dropunit, extract, dupins, "
      "cert, grant), A-2.1 gives the same status as the frozen A-2 for every frozen row except A2-4")
def _():
    lines, node, truth = TA.fixture(2, 400)
    base = A2.replay(lines)
    pos = C.gnb_positions(lines)
    x, u = C.clean_single(base, lines, need_free=0)
    s0, s1 = C.block_span(lines, pos[x["gi"]])
    moved = [C._retime(y, x["t"] + MS) for y in lines[s0:s1 + 1]]
    muts = {"shift": C._put(lines[:s0] + lines[s1 + 1:], x["t"] + MS, moved, at_start=True),
            "dupack": lines[:s1 + 1] + lines[s0:s1 + 1] + lines[s1 + 1:],
            "dropfb": lines[:s0] + lines[s1 + 1:]}
    ui = C._find(lines, lambda y: A2.PR.T_UACK in y, s0)
    muts["dropunit"] = lines[:ui] + lines[ui + 1:]
    ei = C._find(lines, lambda y: f"(id {u['pid']} ) extracted from process" in y)
    muts["extract"] = lines[:ei] + lines[ei + 1:]
    ii = C._find(lines, lambda y: f"new pdu (id {u['pid']} ) inserted" in y)
    muts["dupins"] = lines[:ii + 1] + [lines[ii]] + lines[ii + 1:]
    grp = next(g for g in base["groups"] if g["exchangeable"])
    a = pos[grp["lines"][0]["gi"]]
    nd, tg = grp["cands"][0][0], C._ts(grp["t"])
    muts["cert"] = lines[:a + 1] + [f"{tg}|{A2.GNB}|H-ARQ TX: new pdu (id 999999 ) inserted into process 15 codeword id: 0 for node with id {nd}\n",
                                    f"{tg}|{A2.GNB}|\t H-ARQ TX: pdu (id 999999 ) extracted from process 15 codeword 0 for node with id {nd}\n"] + lines[a + 1:]
    for name, ls in muts.items():
        f, n = st(ev2(ls, node)[1]), st(ev21(ls, node)[1])
        diff = {k: (f[k], n.get(k)) for k in f if k != "A2-4" and f[k] != n.get(k)}
        assert not diff, (name, diff)
        assert any(v == "FAIL" for v in f.values()), name


# ---------------------------------------------------------------------------------------- corrected generator ----
@test("T-gen21-faithful: unit lines print handles disjoint from the MAC ids; no scheduler text under the MAC (only under "
      "mac.schedulerDl, and only with sched_log); 'selected for retransmission' under the MAC; retransmission one TTI after "
      "its NACK; main-loop markers present")
def _():
    lines, node, truth = build({3: 1, 10: 2})
    macs = {int(m.group(1)) for y in lines for m in [A.PR.R_INSERT.search(y)] if m}
    hs = {int(m.group(3)) for y in lines for m in [A.PR.R_URTX.search(y) or A.PR.R_UDISC.search(y)] if m}
    assert hs and not (hs & macs), (sorted(hs)[:3], sorted(macs)[:3])
    assert not any("LteSchedulerEnb" in y for y in lines)
    assert any("selected for retransmission" in y and y.split("|")[1] == A.GNB for y in lines)
    assert sum(A.ML_START in y for y in lines) == sum(A.ML_END in y for y in lines) > 0
    res = A.replay(lines)
    assert res["nack_rtx_delays"] and set(res["nack_rtx_delays"]) == {MS}, res["nack_rtx_delays"]
    l2, _, _ = build({3: 1}, sched_log=True)
    assert all(y.split("|")[1] == G.SCHED for y in l2 if "LteSchedulerEnb" in y) and any("rtxAcid - Node" in y for y in l2)


@test("T-frozen-fails-on-corrected (RC-1 documented): the frozen A-2 on corrected-model NACK input fails A2-1 with "
      "'NACK (PDU <handle>) not among the candidates' (namespace defect), while A-2.1 is VALID under F1-d (i)")
def _():
    lines, node, truth = build({3: 1, 10: 2, 20: 3})
    f = ev2(lines, node)[1]
    assert st(f)["A2-1"] == "FAIL" and "not among the candidates" in dict((r[0], r[3]) for r in f)["A2-1"], f
    n = ev21(lines, node)[1]
    assert A.verdict(n, "f1d-i")[1] == 0, [r for r in n if r[2] not in ("PASS", A.NX)]


# ---------------------------------------------------------------------------------------- first chain ------------
def sca2(d, node, truth):
    """the scalar helper of test_m2s72_a2v1 writes the two-UE layout only: never called for another N"""
    assert len(node) == 2, f"scalar helper called for N = {len(node)}"
    return TV.sca(d, node, truth)


def chain_checks(lines, node, real=False):
    res, rows, per, cov, extra, window = ev21(lines, node, t0=300 * MS)
    s = st(rows)
    fbs = {(x["t"] // MS, x["res"]): x for x in res["fb"] if x["p"] == 0 and 366 <= x["t"] // MS <= 384}
    nk366 = fbs[(366, "NACK")]
    assert nk366["cls"] == "resolved-by-rtx" and nk366["owner"] == 2050 and nk366["pid"] == 145933 and nk366["handle"] == 54326, nk366
    assert fbs[(366, "ACK")]["owner"] == 2049 and fbs[(366, "ACK")]["cls"] in ("single", "resolved-by-elimination"), fbs[(366, "ACK")]
    for tt in (372, 378):
        assert fbs[(tt, "NACK")]["cls"] == "bound" and fbs[(tt, "NACK")]["pid"] == 145933, fbs[(tt, "NACK")]
    u = res["pdus"][145933]
    assert u["ntx"] == 4 and u["end"] == "ack" and u["t_close"] // MS == 384 and [tt // MS for tt in u["txs"]] == [361, 367, 373, 379], u
    assert res["handles"][54326] == {"st": "retired", "lc": 145933}, res["handles"][54326]
    other = res["pdus"][fbs[(366, "ACK")]["pid"]]
    assert other["t_close"] // MS == 366 and other["close_gi"] == fbs[(366, "ACK")]["gi"], other
    for k in ("A2-0", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-6", "A2-7", "A2-9"):
        assert s[k] == "PASS", (k, s[k], dict((r[0], r[3]) for r in rows)[k][:300])
    assert s["A2-4c"] == A.NE
    assert A.verdict(rows, "full")[0] == "A-2.1 INCOMPLETE" and A.verdict(rows, "f1d-i")[0] == "A-2.1 VALID"
    f = ev2(lines, node, t0=300 * MS)[1]
    assert st(f)["A2-1"] == "FAIL" and "NACK (PDU 54326) not among the candidates" in dict((r[0], r[3]) for r in f)["A2-1"]
    return res


@test("T-recon-first-chain (SYNTHETIC reconstruction of the VM-reported chain): group 366 'resolved-by-rtx' (NACK -> "
      "node 2050 / PDU 145933, ACK -> node 2049), handle 54326 bound at 366, used at 372 / 378 ('bound'), retired at the 384 "
      "ACK; transmissions 361 / 367 / 373 / 379; the other unit closed at its 366 line; A2-0..A2-4b, A2-6, A2-7, A2-9 "
      "PASS, A2-4c NOT EVALUATED; verdict full INCOMPLETE, f1d-i VALID; the frozen A-2 reproduces 'NACK (PDU 54326) not "
      "among the candidates'")
def _():
    lines, node, truth = recon()
    chain_checks(lines, node)


@test("T-real-first-chain: the REAL sealed-log prefix (fixtures/a2v1-first-chain.log.gz, its .sha256 pin and "
      "a2v1-first-chain.meta.json, written by m2s72_a21_fixture.py on the VM) meets every declared expectation R-1..R-10 of "
      "m2s72_a21_realchain.py; PENDING (never PASS) while the three files are absent; FAIL if only some are present")
def _():
    import m2s72_a21_realchain as RC
    d = os.path.dirname(FIX)
    files = [os.path.join(d, x) for x in (RC.FIX, RC.FIX + ".sha256", RC.META)]
    have = [os.path.exists(x) for x in files]
    if not any(have):
        PENDING.append("T-real-first-chain: fixture not yet extracted from the sealed A2-V1 output (A2-D2-F3 Phase 1)")
        return "PENDING"
    assert all(have), f"incomplete fixture set: {[f for f, h in zip(files, have) if not h]} missing"
    assert TA.root(), "SIMU5G_ROOT (Simu5G 1.8.1 sources) is needed for A2-0s: the real-chain test cannot be evaluated"
    fx = RC.load_fixture(d)
    out, ctx = RC.validate(fx, TA.root())
    bad = [r for r in out if r[1] != "PASS"]
    assert not bad, bad


# ------------------------------------------------------------------------------------- sweep against truth --------
def truth_agreement(lines, node, truth, res):
    """every feedback line against the generator truth (same emission order): unique classes name the true node; groups
    with exchangeable lines have the true node multiset; every PDU's history equals the truth"""
    assert len(res["fb"]) == len(truth), (len(res["fb"]), len(truth))
    for g in res["groups"]:
        js = [x["j"] for x in g["lines"]]
        if any(x["cls"] in ("censored", "unresolved-pending") for x in g["lines"]):
            continue
        assert sorted(x["owner"] for x in g["lines"]) == sorted(truth[j]["node"] for j in js), (g["t"], g["p"])
        for x in g["lines"]:
            if x["cls"] in A.UNIQUE:
                assert x["owner"] == truth[x["j"]]["node"] and x["pid"] == truth[x["j"]]["pid"], (x, truth[x["j"]])
    by = {}
    for x in truth:
        by.setdefault(x["pid"], []).append(x)
    for pid, xs in by.items():
        u = res["pdus"][pid]
        assert [r for _, r in u["fbs"]] == [x["res"] for x in xs], (pid, u["fbs"], [x["res"] for x in xs])
        assert u["ntx"] == xs[-1]["ntx"], (pid, u["ntx"], xs[-1]["ntx"])
        fin_ = xs[-1]["outcome"]
        if fin_ in ("ack", "discard"):
            assert u["end"] == fin_ and u["t_close"] == xs[-1]["t"], (pid, u["end"], u["t_close"], xs[-1])


@test("T-sweep21 / T-defer-equiv: random NACK patterns (ue[1] only; both UEs; 3 UEs), chains to a discard, 5 seeds x 3 "
      "layouts: A-2.1 VALID (f1d-i); every line and every PDU history (feedback sequence, transmissions, end, close time) "
      "equals the truth, so deferred resolution reproduces the original events; A2-7 (XA, incl. per-UE occupancy) PASS")
def _():
    layouts = [(2, sched3, (1,)), (2, lambda t: [0, 1] if t % 2 else [0], (0, 1)), (3, lambda t: [0, 1, 2] if t % 3 else [1, 2], (0, 2))]
    seen = Counter()
    for seed in range(5):
        rnd = random.Random(seed)
        for n_ue, sch, nack_ues in layouts:
            _, node, tr = G.make(n_ue, 200, sch, tail=40)
            pids = sorted({x["pid"] for x in tr if x["node"] in {node[k] for k in nack_ues}})
            nk = set()
            for p in rnd.sample(pids, 12):
                n = rnd.choice((1, 1, 1, 2, 3, 4))
                nk |= {(p, a) for a in range(1, n + 1)}
            lines, node, truth = G.make(n_ue, 200, sch, nack=nk, tail=40)
            lines = fin(lines)
            res, rows, per, cov, extra, window = ev21(lines, node, nproc=16)
            assert A.verdict(rows, "f1d-i")[1] == 0, (seed, n_ue, [r for r in rows if r[2] not in ("PASS", A.NX)])
            assert st(rows)["A2-7"] == "PASS"
            truth_agreement(lines, node, truth, res)
            seen.update(x["cls"] for x in res["fb"] if x["res"] == "NACK")
            seen["discards"] += sum(1 for u in res["pdus"].values() if u["end"] == "discard")
            seen["multi"] += res["counts"].get("multi-NACK groups", 0)
    assert seen["resolved-by-rtx"] and seen["bound"] and seen["single"] and seen["discards"], seen


# --------------------------------------------------------------------------------------- multi-NACK ambiguity -----
def twin(nack_both, nack_a=(), nack_b=(), ttis=1):
    """both UEs get one PDU in the same TTI on the same process (one group per feedback): nack_both attempts NACKed by
    both, nack_a / nack_b by one UE only"""
    def sch(t):
        return [0, 1] if t == 1000 else []
    _, node, tr = G.make(2, ttis, sch, tail=40)
    pa, pb = sorted({x["pid"] for x in tr})
    nk = {(pa, a) for a in nack_both} | {(pb, a) for a in nack_both} | {(pa, a) for a in nack_a} | {(pb, a) for a in nack_b}
    lines, node, truth = G.make(2, ttis, sch, nack=nk, tail=40)
    return fin(lines), node, truth, pa, pb


@test("T-multinack: two lifecycles NACKed in one group -> both lines 'exchangeable-nack', the handles AMBIGUOUS (no unique "
      "assignment), per-UE NACK counts exact; when both are ACKed later the handles stay ambiguous (never claimed); a later "
      "mixed group binds one handle by its retransmission and the other by elimination")
def _():
    lines, node, truth, pa, pb = twin((1,))
    res, rows, *_ = ev21(lines, node)
    nk = [x for x in res["fb"] if x["res"] == "NACK"]
    assert len(nk) == 2 and all(x["cls"] == "exchangeable-nack" and x["owner_set"] == sorted([pa, pb]) for x in nk), nk
    amb = [h for h, hs in res["handles"].items() if hs["st"] == "ambiguous"]
    assert len(amb) == 2 and all(res["handles"][h]["lc"] == sorted([pa, pb]) for h in amb), res["handles"]
    assert A.verdict(rows, "f1d-i")[1] == 0, [r for r in rows if r[2] not in ("PASS", A.NX)]
    lines, node, truth, pa, pb = twin((1,), nack_a=(2,))
    res, rows, *_ = ev21(lines, node)
    hs = res["handles"]
    assert all(v["st"] in ("bound", "retired") for v in hs.values()), hs
    ha = next(h for h, v in hs.items() if v["lc"] == pa)
    assert truth[[i for i, x in enumerate(truth) if x["pid"] == pa][0]]["handle"] == ha
    assert A.verdict(rows, "f1d-i")[1] == 0
    truth_agreement(lines, node, truth, res)


@test("T-multinack-discard: both lifecycles NACKed three times together, then one discarded and one ACKed in the same "
      "group: discard / ACK cannot be separated (both eligible, handles ambiguous) -> A2-1 FAIL 'UNRESOLVED discard'; both "
      "discarded together -> exchangeable discards, VALID")
def _():
    lines, node, truth, pa, pb = twin((1, 2, 3), nack_a=(4,))
    res, rows, *_ = ev21(lines, node)
    det = dict((r[0], r[3]) for r in rows)
    assert st(rows)["A2-1"] == "FAIL" and "UNRESOLVED discard" in det["A2-1"], det["A2-1"]
    lines, node, truth, pa, pb = twin((1, 2, 3, 4))
    res, rows, *_ = ev21(lines, node)
    assert A.verdict(rows, "f1d-i")[1] == 0, [r for r in rows if r[2] not in ("PASS", A.NX)]
    assert sum(1 for u in res["pdus"].values() if u["end"] == "discard") == 2


@test("T-handle-lifecycle: a new lifecycle on a reused key starts unbound (B-6): consecutive NACKed PDUs on the same unit "
      "key get distinct handles, each bound to its own lifecycle and retired at its end")
def _():
    lines, node, truth = build({3: 1, 4: 1, 5: 2})
    res = A.replay(lines)
    keys = Counter((res["pdus"][hs["lc"]]["node"], res["pdus"][hs["lc"]]["p"]) for hs in res["handles"].values())
    assert all(hs["st"] == "retired" for hs in res["handles"].values()), res["handles"]
    assert len({hs["lc"] for hs in res["handles"].values()}) == len(res["handles"]) == 3
    assert max(keys.values()) >= 1


# ----------------------------------------------------------------------------------------------- A2-4 ------------
@test("T-a24: A2-4a PASS with selection lines, FAIL when one is removed; A2-4b PASS, FAIL when the retransmission's "
      "reception is relabelled to the other UE, NOT EVALUATED when the UE log is absent, independent of any fixed delay "
      "(UE feedback delay 2 or 3); A2-4c NOT EVALUATED without scheduler lines (never PASS), PASS with scheduler logging "
      "on (lines under mac.schedulerDl), FAIL when its User[...] names the other UE")
def _():
    for d_ue in (2, 3):
        lines, node, truth = build({3: 1, 10: 2}, d_ue=d_ue)
        s = st(ev21(lines, node)[1])
        assert s["A2-4a"] == s["A2-4b"] == "PASS" and s["A2-4c"] == A.NE, (d_ue, s)
    si = next(i for i, y in enumerate(lines) if "selected for retransmission" in y)
    assert st(ev21(lines[:si] + lines[si + 1:], node)[1])["A2-4a"] == "FAIL"
    lines_n, node_n, _ = build({3: 1}, ue_log=False)
    assert st(ev21(lines_n, node_n)[1])["A2-4b"] == A.NE
    lines, node, truth = build({3: 1, 10: 2}, sched_log=True)
    s = st(ev21(lines, node)[1])
    assert s["A2-4c"] == "PASS", s
    ai = next(i for i, y in enumerate(lines) if "rtxAcid - Node" in y)
    ls = list(lines)
    ls[ai] = ls[ai].replace("User[2050]", "User[2049]")
    assert st(ev21(ls, node)[1])["A2-4c"] == "FAIL"


# --------------------------------------------------------------------------------------------- end of log --------
def cut_at(lines, t_ms):
    """the run ends at simulated time t_ms (every event at or before it is logged, nothing after): the way a sim-time
    limit truncates a log; never inside a TTI's event sequence"""
    c = [y for y in lines if A.SENTINEL_MOD not in y and int(round(float(y.split("|", 1)[0]) * 1000)) <= t_ms]
    return c + [A.sentinel(A.t_end_of(c))]


@test("T-end: a log ending right after a NACK (no complete main loop after it) censors it structurally (A2-9 PASS); with a "
      "complete main loop after it -> UNRESOLVED (A2-9 NOT EVALUATED, INCOMPLETE); without any main-loop marker -> UNRESOLVED "
      "(fail-closed); a pending mixed group at the end: censored (structural) with A2-7 / A2-8 NOT EVALUATED for its nodes, "
      "or UNRESOLVED when a main loop followed")
def _():
    lines, node, truth = recon()
    c = cut_at(lines, 372)
    res, rows, *_ = ev21(c, node, t0=300 * MS)
    s = st(rows)
    assert s["A2-9"] == "PASS" and res["end_states"].get("censored: awaiting retransmission", 0) + res["end_states"].get("censored: awaiting resolution", 0) >= 1, (s, res["end_states"])
    assert s["A2-2"] != "FAIL" and s["A2-1"] != "FAIL", s
    c2 = c[:-1] + [f"0.372|{A.GNB}|{A.ML_START}\n", f"0.372|{A.GNB}|{A.ML_END}\n", c[-1]]
    res2, rows2, *_ = ev21(c2, node, t0=300 * MS)
    assert st(rows2)["A2-9"] == A.NE and A.verdict(rows2, "f1d-i")[0] == "A-2.1 INCOMPLETE", st(rows2)
    c3 = [y for y in c if A.ML_START not in y and A.ML_END not in y]
    rows3 = ev21(c3, node, t0=300 * MS)[1]
    assert st(rows3)["A2-9"] == A.NE, st(rows3)
    c4 = cut_at(lines, 366)
    res4, rows4, *_ = ev21(c4, node, t0=300 * MS)
    s4 = st(rows4)
    assert [g["censored_nodes"] for g in res4["groups"] if g.get("censored_nodes")] == [[2049, 2050]], res4["end_states"]
    assert res4["end_states"].get("censored: awaiting resolution") == 2
    assert s4["A2-9"] == "PASS" and s4["A2-7"] == A.NE and s4["A2-1"] == s4["A2-2"] == "PASS", s4
    c5 = c4[:-1] + [f"0.366|{A.GNB}|{A.ML_START}\n", f"0.366|{A.GNB}|{A.ML_END}\n", c4[-1]]
    assert st(ev21(c5, node, t0=300 * MS)[1])["A2-9"] == A.NE


# --------------------------------------------------------------------------------------------- controls ----------
@test("T-controls: every declared A-2.1 control on corrected-model input with a .sca is AS DECLARED: ACK-only mutations "
      "and the F1 controls (rtxmove, doublertx, nortx, select, rtxnode, handle, handle-foreign, retired, endcensor, endfake, "
      "xa, scalar); each negative control's declared row was PASS before and the failure names the mutated element where a "
      "token is declared; no control is NOT BUILDABLE on this input")
def _():
    d = tempfile.mkdtemp()
    try:
        lines, node, truth = build({3: 1, 10: 2, 20: 3, 30: 4, 40: 1, 50: 1, 60: 2})
        sca = sca2(d, node, truth)
        out, st0 = CC.controls(lines, 16, 1000 * MS, node, TA.grants_of(lines), sca, TA.root())
        bad = [o for o in out if o[2] != "AS DECLARED"]
        assert not bad, bad
        names = {o[0].split(":")[0] for o in out}
        for n in ("NC-F1-rtxmove", "NC-F1-doublertx", "NC-F1-nortx", "NC-F1-select", "NC-F1-rtxnode", "NC-F1-handle",
                  "NC-F1-handle-foreign", "NC-F1-retired", "PC-F1-endcensor", "NC-F1-endfake", "NC-F1-xa", "NC-A21-scalar"):
            assert n in names, n
    finally:
        shutil.rmtree(d)


@test("T-controls-baseline-guard: a negative control whose declared row already fails before the mutation is NOT "
      "BUILDABLE (never counted as a pass); on ACK-only real-like input without NACKs the F1 controls run on one injected "
      "chain in the corrected model (labelled synthetic) and are AS DECLARED")
def _():
    lines, node, truth = TA.fixture(2, 400, sched=lambda t: [0] + ([1] if t % 13 == 3 else []))
    out, st0 = CC.controls(lines, 16, 1000 * MS, node, TA.grants_of(lines), None, TA.root())
    inj = [o for o in out if o[0].startswith("PC-F1-inject")]
    assert inj and inj[0][2] == "AS DECLARED", inj
    bad = [o for o in out if o[2] == "NOT AS DECLARED"]
    assert not bad, bad
    # guard: break A2-3 first (several ages), then the shift control must be NOT BUILDABLE
    base = A2.replay(lines)
    x, u = C.clean_single(base, lines, need_free=0)
    s0, s1 = C.block_span(lines, C.gnb_positions(lines)[x["gi"]])
    moved = [C._retime(y, x["t"] + MS) for y in lines[s0:s1 + 1]]
    broken = C._put(lines[:s0] + lines[s1 + 1:], x["t"] + MS, moved, at_start=True)
    out2, st2 = CC.controls(broken, 16, 1000 * MS, node, TA.grants_of(broken), None, TA.root())
    assert st2["A2-3"] == "FAIL"
    sh = [o for o in out2 if o[0].startswith("NC-A21-shift")]
    assert sh and sh[0][2] == CC.NOTB, sh


@test("T-contract: any FAIL -> NOT VALID (rc 1) under both contracts; A2-4c NOT EVALUATED -> full INCOMPLETE (rc 4), "
      "f1d-i VALID; A2-4c NOT EXERCISED (no retransmission) -> VALID under both; A2-4c never PASS by absence; any other "
      "required row NOT EVALUATED -> INCOMPLETE under both")
def _():
    base = [(k, "run", "PASS", "") for k in A.REQUIRED["full"]] + [("A2-8", "run", A.NE, "")]

    def with_(**kw):
        return [(k, s_, kw.get(k.replace("-", "_"), st_), d) for k, s_, st_, d in base]
    assert A.verdict(with_(), "full") == ("A-2.1 VALID", 0) == A.verdict(with_(), "f1d-i")
    r = with_(A2_4c=A.NE)
    assert A.verdict(r, "full") == ("A-2.1 INCOMPLETE", 4) and A.verdict(r, "f1d-i") == ("A-2.1 VALID", 0)
    r = with_(A2_4a=A.NX, A2_4b=A.NX, A2_4c=A.NX)
    assert A.verdict(r, "full")[1] == 0 == A.verdict(r, "f1d-i")[1]
    for k in ("A2-1", "A2-4b", "A2-8"):
        r = with_(**{k.replace("-", "_"): "FAIL", "A2_4c": A.NE})
        assert A.verdict(r, "full")[1] == 1 == A.verdict(r, "f1d-i")[1], k
    for k in ("A2-7", "A2-9", "A2-4b"):
        r = with_(**{k.replace("-", "_"): A.NE})
        assert A.verdict(r, "full")[1] == 4 == A.verdict(r, "f1d-i")[1], k
    lines, node, truth = build({3: 1})
    assert st(ev21(lines, node)[1])["A2-4c"] == A.NE


@test("T-cli: 'a21' and 'a21-controls' on a runs directory laid out as the runner writes it: records written, exit "
      "codes = verdict (contract full: 4 INCOMPLETE without scheduler lines; f1d-i: 0); unknown contract -> rc 2")
def _():
    lines, node, truth = recon()
    d = tempfile.mkdtemp()
    cfg = "M2S72-E0vN-q0-one0-n2-f1_A2V1"
    old_n, old_r = C._node_ids, os.environ.get("SIMU5G_ROOT")
    try:
        runs = os.path.join(d, "runs")
        os.makedirs(os.path.join(runs, cfg, cfg))
        with gzip.open(os.path.join(runs, f"run-{cfg}.log.gz"), "wt") as fh:
            fh.writelines(x for x in lines if A.SENTINEL_MOD not in x)
        sca2(os.path.join(runs, cfg, cfg), node, truth)
        C._node_ids = lambda r, c: dict(node)
        os.environ["SIMU5G_ROOT"] = TA.root()
        assert CC.main(["x", "a21", runs, cfg, os.path.join(d, "r1"), "--t0", "0.3"]) == 4
        assert CC.main(["x", "a21", runs, cfg, os.path.join(d, "r2"), "--t0", "0.3", "--contract", "f1d-i"]) == 0
        assert "A-2.1 VALID" in open(os.path.join(d, "r2", f"a21-{cfg}.txt")).read()
        assert CC.main(["x", "a21", runs, cfg, os.path.join(d, "r3"), "--contract", "loose"]) == 2
        rc = CC.main(["x", "a21-controls", runs, cfg, os.path.join(d, "r4"), "--t0", "0.3"])
        txt = open(os.path.join(d, "r4", f"a21-controls-{cfg}.txt")).read()
        assert rc == 0, txt[-3000:]
    finally:
        C._node_ids = old_n
        if old_r is None:
            os.environ.pop("SIMU5G_ROOT", None)
        else:
            os.environ["SIMU5G_ROOT"] = old_r
        shutil.rmtree(d)


def main():
    fails = 0
    pend = 0
    only = sys.argv[1:]
    run = [(n, f) for n, f in TESTS if not only or any(n.startswith(o) for o in only)]
    for name, f in run:
        try:
            r = f()
            if r == "PENDING":
                pend += 1
                print(f"PENDING  {name}")
            else:
                print(f"PASS  {name}")
        except Exception as ex:
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {name}: {type(ex).__name__}: {str(ex)[:800]}")
    print(f"A-2.1 tests: {len(run) - fails - pend} / {len(run)} PASS, {pend} PENDING, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
