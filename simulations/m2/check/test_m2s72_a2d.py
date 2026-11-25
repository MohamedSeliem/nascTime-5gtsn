#!/usr/bin/env python3
"""M2-S7.2a work package A2 tests (no simulation, no genuine evidence): the full-contract diagnostic configuration
(m2s72a2d.ini) and its checks (m2s72_a2d.py). Inputs: the committed ini files; the RECORDED OMNeT++ 6.5.0 resolution
(results/M2-S7.2a-a2d/runconfig-*.txt, produced by `m2s72_a2d.py resolve` on the pinned stack; re-resolution needs the
stack and is not repeated here); synthetic twin outputs; synthetic A-2.1 input from the accepted corrected generator
m2s72_harqfix21 (labelled synthetic). Every number below is synthetic.

    python3 check/test_m2s72_a2d.py   -> one line per test and a summary; exit 0 iff every test passes
"""
import gzip
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
NASCTIME = os.path.dirname(os.path.dirname(M2))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a2d as D  # noqa: E402

BASE_COMMIT = "b7a951dc7ddad5b006e10db3083fcab03f0d327a"     # m2/continuation at the start of A2 (PR #18 merge)
REC = os.path.join(M2, "results", "M2-S7.2a-a2d")
ACCEPTED = ["simulations/m2/m2s72.ini", "simulations/m2/m2s72s5.ini", "simulations/m2/m2s72a2v.ini", "simulations/m2/omnetpp.ini",
            "simulations/m2/tools", "simulations/m2/check/m2s72_a21.py", "simulations/m2/check/check_m2s72_a21.py",
            "simulations/m2/check/m2s72_harqfix21.py", "simulations/m2/check/check_m2s72_e0.py",
            "simulations/m2/check/check_m2s72_a2.py", "simulations/m2/check/m2s72_a2.py",
            "simulations/m2/check/check_m2s72_a2v1.py", "simulations/m2/check/m2s72_e0vn21.py",
            "simulations/m2/check/check_m2s72_s5n21.py", "simulations/m2/check/m2s72_fgo_registry.json",
            "simulations/m2/check/expect", "simulations/m2/check/fixtures", "simulations/m2/results", "src", ".github",
            ":(exclude).github/workflows/tier0-python.yml",       # the one authorised CI change (162-R1: the 15th suite)
            "docs/migration/wp-a1-a21-e0vn-wrapper-design.md", "docs/migration/wp-a1-validation-runbook.md",
            "docs/migration/wp-a1-validation"]
RESULTS = []


def test(name):
    def deco(fn):
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as ex:
            RESULTS.append((name, False, str(ex)[:400]))
        except Exception as ex:   # noqa: BLE001
            RESULTS.append((name, False, f"{type(ex).__name__}: {ex}"[:400]))
        return fn
    return deco


def tool(*args):
    return subprocess.run([sys.executable, "-B", os.path.join(HERE, "m2s72_a2d.py")] + list(args), capture_output=True, text=True)


def sections(path):
    """{section: [(key, value)]} of one ini file, in order (text level; include lines ignored)"""
    out, cur = {}, None
    for ln in open(path, encoding="utf-8").read().splitlines():
        s = ln.strip()
        if not s or s.startswith("#") or s.startswith("include "):
            continue
        m = re.fullmatch(r"\[Config (.+)\]", s)
        if m:
            cur = m.group(1)
            out[cur] = []
            continue
        k, v = [x.strip() for x in s.split("=", 1)]
        out[cur].append((k, v))
    return out


# ================================================================================== default-off and preservation ===
@test("default off: no accepted configuration file enables scheduler logging or NACK injection; only the two "
      "hand-written diagnostic files mention IdealChannelModel")
def _():
    for f in ("m2s72.ini", "m2s72s5.ini", "omnetpp.ini"):
        t = open(os.path.join(M2, f), encoding="utf-8").read()
        assert "schedulerDl" not in t and "IdealChannelModel" not in t and "perDl" not in t, f
    mention = sorted(f for f in os.listdir(M2) if f.endswith(".ini") and "IdealChannelModel" in open(os.path.join(M2, f)).read())
    assert mention == ["m2s72a2d.ini", "m2s72a2v.ini"], mention
    a2v = open(os.path.join(M2, "m2s72a2v.ini")).read()
    assert "schedulerDl" not in a2v, "A2-V1 configuration must stay without scheduler logging (historical)"


@test(f"preservation: no accepted ini, generator, evaluator, record, fixture, registry, workflow, source or WP-A1 file is "
      f"modified, renamed or deleted since {BASE_COMMIT[:7]} (new A2 files only)")
def _():
    r = subprocess.run(["git", "-C", NASCTIME, "cat-file", "-e", BASE_COMMIT + "^{commit}"], capture_output=True)
    assert r.returncode == 0, f"{BASE_COMMIT} not in this clone (full history needed)"
    r = subprocess.run(["git", "-C", NASCTIME, "diff", "--name-only", "--diff-filter=MDRTCU", BASE_COMMIT, "--"] + ACCEPTED,
                       capture_output=True, text=True)
    assert r.returncode == 0 and r.stdout.strip() == "", r.stdout


@test("configuration text: the mixins hold exactly the declared entries; the diagnostic extends the scheduler-logging "
      "mixin, the twin does not; both extend the accepted base unchanged")
def _():
    sec = sections(os.path.join(M2, D.INI))
    assert set(sec) == {"M2S72A2D-schedlog", "M2S72A2D-nack-all", D.DIAG, D.REF}, set(sec)
    sched = [(k, v) for k, v in sec["M2S72A2D-schedlog"] if k != "description"]
    assert sched == [(D.SCHED_KEY, D.SCHED_VALUE)], sched
    nack = [(k, v.replace("${repetition}", "0")) for k, v in sec["M2S72A2D-nack-all"] if k != "description"]
    assert nack == D.NACK, nack
    ext = {c: dict(sec[c]).get("extends") for c in (D.DIAG, D.REF)}
    assert ext[D.DIAG] == f"M2S72A2D-schedlog, M2S72A2D-nack-all, {D.BASE}", ext
    assert ext[D.REF] == f"M2S72A2D-nack-all, {D.BASE}", ext
    assert all(set(dict(sec[c])) == {"description", "extends"} for c in (D.DIAG, D.REF))
    assert open(os.path.join(M2, D.INI)).read().count("include m2s72s5.ini") == 1


@test("isolated names: the WP-A1 run / hrq guards and the A3 E0v-N batch set refuse both diagnostic names; the accepted "
      "A-2.1 name parser reads them as HARQ16, N = 2 (so the accepted check_m2s72_a21.py evaluates them unchanged)")
def _():
    import m2s72_e0vn21 as W
    import m2s72_e0vn_batch as BAT
    allcfg = set(BAT.all_configs("h16")) | set(BAT.all_configs("h5"))
    for c in (D.DIAG, D.REF):
        assert not W.run_name_ok(c) and not W.hrq_name_ok(c) and c not in allcfg, c
    _argv = sys.argv
    sys.argv = [_argv[0]]
    import check_m2s72_s5v as S5V
    sys.argv = _argv
    for c in (D.DIAG, D.REF):
        kind, o, h16, _, n = S5V.parse_name(c)
        assert (kind, o, h16, n) == ("E0vN", "q0", True, 2), (c, kind, o, h16, n)


# ========================================================================================= resolution (recorded) ===
def _rc_paths():
    return [os.path.join(REC, f"runconfig-{c}.txt") for c in (D.DIAG, D.REF, D.BASE, D.A2V1)]


@test("resolution (recorded OMNeT++ 6.5.0 runconfig of the pinned stack): R-1 .. R-4 AS DECLARED")
def _():
    for p in _rc_paths():
        assert os.path.isfile(p), p
        assert "Version: 6.5.0" in open(p).read(), p
    r = tool("resolve-files", *_rc_paths())
    assert r.returncode == 0 and "A2 resolution: AS DECLARED" in r.stdout, r.stdout[-600:]
    assert r.stdout.count("PASS |") == 4, r.stdout


def _mutated(i, fn):
    d = tempfile.mkdtemp()
    ps = []
    for j, p in enumerate(_rc_paths()):
        q = os.path.join(d, os.path.basename(p))
        t = open(p).read()
        open(q, "w").write(fn(t) if j == i else t)
        ps.append(q)
    return d, ps


@test("resolution negative controls: an extra entry, a missing scheduler entry, a changed perDl, a second scheduler "
      "log entry, an unchanged num-rngs and an empty resolution are each refused")
def _():
    cases = [(0, lambda t: t.replace("\tnum-rngs = 5\n", "\tnum-rngs = 5\n\t*.ue[0].cellularNic.nrMac.queueSize = 1\n", 1), "R-1"),
             (0, lambda t: t.replace(f"\t{D.SCHED_KEY} = info\n", "", 1), "R-1"),
             (1, lambda t: t.replace("nrChannelModel[*].perDl = 0.3", "nrChannelModel[*].perDl = 0.2", 1), "R-2"),
             (0, lambda t: t.replace(f"\t{D.SCHED_KEY} = info\n",
                                     f"\t{D.SCHED_KEY} = info\n\t*.gnb1.cellularNic.mac.schedulerUl.cmdenv-log-level = info\n", 1), "R-4"),
             (2, lambda t: t.replace("\tnum-rngs = 4\n", "\tnum-rngs = 5\n", 1), "R-2")]
    for i, fn, row in cases:
        d, ps = _mutated(i, fn)
        try:
            assert open(ps[i]).read() != open(_rc_paths()[i]).read(), f"mutation for {row} not applied"
            r = tool("resolve-files", *ps)
            assert r.returncode == 1 and f"FAIL | {row}" in r.stdout, (row, r.stdout[-500:])
        finally:
            shutil.rmtree(d)
    d, ps = _mutated(1, lambda t: "")
    try:
        r = tool("resolve-files", *ps)
        assert r.returncode == 2 and "EVALUATION ERROR" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


# ====================================================================================== twin (synthetic outputs) ===
SCHED = "M2S72Bridge.gnb1.cellularNic.mac.schedulerDl"
MAC = "M2S72Bridge.gnb1.cellularNic.mac"


def _log(cfg, sched, extra=(), runid="20261125-1", elapsed="1.234s", fp="aaaa-bbbb/tplx"):
    out = ["OMNeT++ Discrete Event Simulation  (C) 1992-2026 Andras Varga, OpenSim Ltd.",
           f"Preparing for running configuration {cfg}, run #0...", f"Assigned runID={cfg}-0-{runid}",
           "Setting up network \"M2S72Bridge\"...", "Running simulation..."]
    for t in range(3):
        out.append(f"1.00{t}|{MAC}|LteHarqBufferTx::receiveHarqFeedback - start")
        if sched:
            out.append(f"1.00{t}|{SCHED}|1.00{t}LteSchedulerEnbDl::rtxAcid - Node [1], User[2049],  Codeword [0]  of [1] , "
                       f"ACID [{t}] ")
            out.append(f"1.00{t}|{SCHED}|1.00{t} LteSchedulerEnbDl::rtxschedule UE: 2049")
        out.append(f"1.00{t}|{MAC}|H-ARQ TX: process {t} has been selected for retransmission")
    out += list(extra)
    out += [f"** Event #1000   t=12   Elapsed: {elapsed}  ", "<!> Simulation time limit reached -- at t=12s, event #1000",
            f"Fingerprint successfully verified: calculated: {fp}, expected: none", "Calling finish() at end of Run #0...", "End."]
    return "\n".join(out) + "\n"


def _runs(d, sched_diag=True, sched_ref=False, ref_extra=(), ref_runid="20261125-2", ref_elapsed="9.876s", ref_fp="aaaa-bbbb/tplx",
          ref_pcap=b"\x0a\x0d\x0d\x0a" + bytes(range(64))):
    runs = os.path.join(d, "runs")
    for c, s, extra, rid, el, fp, pc in ((D.DIAG, sched_diag, (), "20261125-1", "1.234s", "aaaa-bbbb/tplx", b"\x0a\x0d\x0d\x0a" + bytes(range(64))),
                                         (D.REF, sched_ref, ref_extra, ref_runid, ref_elapsed, ref_fp, ref_pcap)):
        os.makedirs(os.path.join(runs, c, c), exist_ok=True)
        os.makedirs(os.path.join(runs, c, "pcap", f"{c}-0"), exist_ok=True)
        open(os.path.join(runs, c, c, "0.sca"), "w").write(
            f"version 3\nrun {c}-0-{rid}\nattr configname {c}\nattr datetime {rid}\nconfig {D.SCHED_KEY if s else 'x'} info\n"
            f"scalar M2S72Bridge.ue[0].cellularNic.nrMac harqErrorRateDl 0.25\n")
        open(os.path.join(runs, c, "pcap", f"{c}-0", "dsTt[0].pcapng"), "wb").write(pc)
        with gzip.open(os.path.join(runs, f"run-{c}.log.gz"), "wt") as fh:
            fh.write(_log(c, s, extra, rid, el, fp))
    return runs


@test("twin (synthetic): identical non-log outputs and console logs differing only by scheduler lines and volatile "
      "Cmdenv lines -> non-perturbation SHOWN; every canary as declared")
def _():
    d = tempfile.mkdtemp()
    try:
        runs = _runs(d)
        r = tool("twin", runs, os.path.join(d, "rec"))
        assert r.returncode == 0 and "non-perturbation: SHOWN" in r.stdout, r.stdout
        for row in ("T-1", "T-2", "T-3", "NC-T1", "NC-T2", "NC-T3", "NC-T4"):
            assert f"PASS | {row} |" in r.stdout, (row, r.stdout)
        assert os.path.isfile(os.path.join(d, "rec", f"a2d-twin-{D.DIAG}.txt"))
    finally:
        shutil.rmtree(d)


@test("twin negative controls: a changed PCAP byte, a different MAC log line, a different fingerprint, scheduler lines in "
      "the twin, and no scheduler lines in the diagnostic are each NOT SHOWN (exit 1)")
def _():
    pcap = b"\x0a\x0d\x0d\x0a" + bytes(range(63)) + b"\xff"
    cases = [(dict(ref_pcap=pcap), "FAIL | T-1"), (dict(ref_extra=(f"1.009|{MAC}|an extra MAC line",)), "FAIL | T-2"),
             (dict(ref_fp="cccc-dddd/tplx"), "FAIL | T-1"), (dict(sched_ref=True), "FAIL | T-3"),
             (dict(sched_diag=False), "FAIL | T-3"), (dict(ref_extra=("Unexpected Cmdenv line",)), "FAIL | T-2")]
    for kw, needle in cases:
        d = tempfile.mkdtemp()
        try:
            r = tool("twin", _runs(d, **kw), os.path.join(d, "rec"))
            assert r.returncode == 1 and needle in r.stdout and "NOT SHOWN" in r.stdout, (kw, r.stdout[-700:])
        finally:
            shutil.rmtree(d)
    d = tempfile.mkdtemp()
    try:
        runs = _runs(d)
        shutil.rmtree(os.path.join(runs, D.REF))
        r = tool("twin", runs, os.path.join(d, "rec"))
        assert r.returncode == 2 and "EVALUATION ERROR" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


# ============================================================================================ coverage minima ======
def _a21_json(path, cfg=None, contract="full", a24c="PASS", nack=(3, 2), multi=1, discard=1, drop=None):
    rows = [["A2-0", "run", "PASS", ""], ["A2-4c", "run", a24c, ""], ["A2-9", "run", "PASS", ""]]
    cov = [[D.COV_MULTI, multi, ""], [D.COV_DISCARD, discard, ""], [D.COV_RTX, 7, ""],
           ["end-of-run censoring: awaiting retransmission (structural)", 0, ""]]
    if drop:
        cov = [c for c in cov if c[0] != drop]
    json.dump({"config": cfg or D.DIAG, "contract": contract, "rows": rows, "coverage": cov,
               "per_ue": {"2049": {"nack": nack[0]}, "2050": {"nack": nack[1]}}, "verdict": "A-2.1 VALID"}, open(path, "w"))
    return path


@test("coverage minima (DR-07a): met -> a valid diagnostic; each unmet minimum, A2-4c not exercised, contract f1d-i or a "
      "foreign configuration -> NOT A VALID DIAGNOSTIC (exit 5); the A-2.1 verdict is reported verbatim")
def _():
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "a21.json")
        r = tool("coverage", _a21_json(p), os.path.join(d, "rec"))
        assert r.returncode == 0 and "VALID (minima met, A2-4c exercised)" in r.stdout and "A-2.1 VALID" in r.stdout, r.stdout
        out = json.load(open(os.path.join(d, "rec", f"a2d-coverage-{D.DIAG}.json")))
        assert out["diagnostic_valid"] and out["first_genuine_occurrence_held_for_review"] == [D.COV_MULTI, D.COV_DISCARD, "A2-4c PASS on genuine scheduler evidence"], out
        cases = [(dict(nack=(3, 0)), "FAIL | M-1"), (dict(multi=0), "FAIL | M-2"), (dict(discard=0), "FAIL | M-3"),
                 (dict(a24c="NOT EVALUATED"), "FAIL | M-4"), (dict(a24c="NOT EXERCISED"), "FAIL | M-4"),
                 (dict(contract="f1d-i"), "FAIL | C-1"), (dict(cfg=D.A2V1), "FAIL | C-0")]
        for kw, needle in cases:
            r = tool("coverage", _a21_json(p, **kw), os.path.join(d, "rec2"))
            assert r.returncode == 5 and needle in r.stdout and "NOT A VALID DIAGNOSTIC" in r.stdout, (kw, r.stdout)
        r = tool("coverage", _a21_json(p, a24c="FAIL"), os.path.join(d, "rec3"))
        assert r.returncode == 0 and "A2-4c exercised: FAIL" in r.stdout, r.stdout     # exercised; the A-2.1 verdict decides
        r = tool("coverage", _a21_json(p, drop=D.COV_DISCARD), os.path.join(d, "rec4"))
        assert r.returncode == 2 and "schema drift" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


def _synthetic_a21(sched_log=True, discard=True):
    """the accepted A-2.1 evaluation of SYNTHETIC input from the accepted corrected generator (2 UEs; NACKs on both;
    a multi-NACK group; optionally a 4-attempt chain): the a21 JSON fields the coverage check reads"""
    import m2s72_a21 as A
    import m2s72_harqfix21 as G
    import test_m2s72_a2 as TA

    def sch(t):
        return [0, 1] if (t == 1000 or t % 2) else [0]
    _, node, tr = G.make(2, 120, sch, t0=1000, tail=40)
    first = {}
    for x in tr:
        first.setdefault((x["node"], x["t"] // G.MS), x["pid"])
    odd = sorted(t for (n, t) in first if n == node[1])
    pair = odd[0]                    # TTI 1000: both UEs' first PDU, both on process 0 -> one feedback group
    nk = {(first[(node[0], pair)], 1), (first[(node[1], pair)], 1)}               # both UEs NACK in one group
    nk |= {(first[(node[1], odd[6])], 1)}                                         # a further NACK on UE 1
    even = sorted(t for (n, t) in first if n == node[0] and t % 2 == 0)
    if discard:
        nk |= {(first[(node[0], even[4])], a) for a in (1, 2, 3, 4)}              # 4 failed attempts: discarded
    lines, node, truth = G.make(2, 120, sch, nack=nk, t0=1000, tail=40, sched_log=sched_log)
    lines = TA.omnet(lines)
    lines = lines + [A.sentinel(A.t_end_of(lines))]
    res, rows, per, cov, extra, window = A.evaluate(lines, 16, 1000 * G.MS, node, TA.grants_of(lines), None, TA.root())
    verdict, rc = A.verdict(rows, "full")
    return {"config": D.DIAG, "contract": "full", "rows": [list(r) for r in rows], "coverage": [list(c) for c in cov],
            "per_ue": {str(n): o for n, o in per.items()}, "verdict": verdict}


@test("coverage on the ACCEPTED A-2.1 evaluation of synthetic generator input (labelled synthetic): with scheduler "
      "logging and a discard the minima are met and A2-4c is PASS; without scheduler logging M-4 fails; without the "
      "4-attempt chain M-3 fails")
def _():
    d = tempfile.mkdtemp()
    try:
        for kw, rc, needle in ((dict(), 0, "PASS | M-4 | A2-4c exercised: PASS"), (dict(sched_log=False), 5, "FAIL | M-4"),
                               (dict(discard=False), 5, "FAIL | M-3")):
            p = os.path.join(d, "a21.json")
            json.dump(_synthetic_a21(**kw), open(p, "w"))
            r = tool("coverage", p, os.path.join(d, f"rec{rc}{len(kw)}"))
            assert r.returncode == rc and needle in r.stdout, (kw, r.stdout)
            if rc == 0:
                assert "PASS | M-1" in r.stdout and "PASS | M-2" in r.stdout and "PASS | M-3" in r.stdout, r.stdout
    finally:
        shutil.rmtree(d)


# ============================================================== network-initialization smoke (162-R1, recorded) ===
SMOKE = os.path.join(REC, "smoke-init.json")


def _smoke_tool(d):
    p = os.path.join(tempfile.mkdtemp(), "s.json")
    json.dump(d, open(p, "w"))
    try:
        return tool("smoke-check", p)
    finally:
        shutil.rmtree(os.path.dirname(p))


@test("initialization smoke (recorded run of the pinned stack, stopped at t = 0; development level, not V-6): SM-1 .. "
      "SM-5 AS DECLARED; the record holds no local path")
def _():
    assert os.path.isfile(SMOKE), SMOKE
    t = open(SMOKE).read()
    assert "/tmp/" not in t and "/home/" not in t and "/root" not in t
    d = json.loads(t)
    assert d["args"][d["args"].index("--sim-time-limit=0s")] == "--sim-time-limit=0s" and \
        "--unused-entry-check-time=initialization" in d["args"], d["args"]
    r = tool("smoke-check", SMOKE)
    assert r.returncode == 0 and "AS DECLARED" in r.stdout and r.stdout.count("PASS |") == 11, r.stdout


@test("initialization smoke negative controls: a failed run, a run not stopped at t = 0, an A2 entry without effect, a "
      "different unused set, a non-Ideal channel model, a wrong perDl, Ideal in the base, scheduler lines in the twin")
def _():
    base = json.load(open(SMOKE))

    def mut(fn):
        d = json.loads(json.dumps(base))
        fn(d["runs"])
        return d
    ue0 = "M2S72Bridge.ue[0].cellularNic.nrChannelModel[0]"
    cases = [(lambda R: R[D.DIAG].update(rc=1), "FAIL | SM-1"),
             (lambda R: R[D.REF].update(stopped_at_t0_event=None), "FAIL | SM-1"),
             (lambda R: R[D.DIAG]["unused"].append([D.SCHED_KEY, "info", "m2s72a2d.ini", 28]), "FAIL | SM-2"),
             (lambda R: R[D.REF]["unused"].pop(0), "FAIL | SM-2"),
             (lambda R: R[D.DIAG]["types"].update({ue0: "simu5g.stack.phy.channelmodel.Tr38901ChannelModel"}), "FAIL | SM-3"),
             (lambda R: R[D.REF]["par"][ue0].update(perDl="0.2"), "FAIL | SM-4"),
             (lambda R: R[D.BASE]["types"].update({ue0: "simu5g.stack.phy.channelmodel.IdealChannelModel"}), "FAIL | SM-3"),
             (lambda R: R[D.REF].update(scheduler_lines=3), "FAIL | SM-5")]
    for fn, needle in cases:
        r = _smoke_tool(mut(fn))
        assert r.returncode == 1 and needle in r.stdout and "NOT AS DECLARED" in r.stdout, (needle, r.stdout[-500:])
    r = _smoke_tool({"schema": "m2s72-a2d-smoke/1", "runs": {}})
    assert r.returncode == 2 and "not a complete smoke record" in r.stdout, r.stdout


@test("initialization smoke parsers: the unused-entry list, the t = 0 stop, errors and scheduler lines (console); module "
      "types from eventlog creation records; parameter scalars (.sca)")
def _():
    con = "\n".join(["Setting up network \"M2S72Bridge\"...",
                     "<!> Warning: 2 configuration entries had no effect in this run (see the unused-entry-check option):",
                     "  *.talker[2].app[2].io.localAddress = \"talker[2]\"  -- /x/simulations/m2/m2s72.ini:6873",
                     "  **.routingRecorder.enabled = false  -- /x/simulations/m2/m2s72.ini:6886",
                     "Possible causes: a typo", "0|M2S72Bridge.gnb1.cellularNic.mac.schedulerDl|Creating LteScheduler MAXCI",
                     "<!> Simulation time limit reached -- at t=0s, event #36", "End."])
    unused, count, stop, errs, sched = D.parse_console(con)
    assert count == 2 and len(unused) == 2 and unused[0][2] == "m2s72.ini" and stop == 36 and not errs and sched == 1, \
        (unused, count, stop, errs, sched)
    _, _, stop2, errs2, _ = D.parse_console("<!> Error: Unknown parameter\nEnd.")
    assert stop2 is None and errs2, errs2
    d = tempfile.mkdtemp()
    try:
        el = os.path.join(d, "0.elog")
        open(el, "w").write("MC id 1 c omnetpp::cModule t M2S72Bridge n M2S72Bridge\n"
                            "MC id 2 c x t simu5g.nodes.NR.gNodeB pid 1 n gnb1\n"
                            "MC id 3 c x t simu5g.stack.NrNicEnb pid 2 n cellularNic\n"
                            "MC id 4 c simu5g::IdealChannelModel t simu5g.stack.phy.channelmodel.IdealChannelModel pid 3 n channelModel[0]\n"
                            "E # 0 t 0 m 1 ce -1 msg -1\n")
        t = D.parse_elog_types(el)
        assert t["M2S72Bridge.gnb1.cellularNic.channelModel[0]"] == "simu5g.stack.phy.channelmodel.IdealChannelModel", t
        sc = os.path.join(d, "0.sca")
        open(sc, "w").write("version 3\nrun x\npar M2S72Bridge.ue[0].cellularNic.nrChannelModel[0] perDl 0.3\n"
                            "scalar M2S72Bridge.ue[0] y 1\n")
        assert D.parse_sca_par(sc) == {"M2S72Bridge.ue[0].cellularNic.nrChannelModel[0]": {"perDl": "0.3"}}
    finally:
        shutil.rmtree(d)


# =============================================================================================== commands ==========
@test("plan: deterministic, absolute paths only, diagnostic names only, the accepted runner's simulation flags, the A2 "
      "file; evaluation order twin -> A-2.1 full -> coverage -> manifests")
def _():
    a = D.plan("/n", "/s", "/i", "/r")
    assert a == D.plan("/n", "/s", "/i", "/r") and len(a) == 10, a
    for c in (D.DIAG, D.REF):
        sim = next(x for x in a if f"-c {c} " in x)
        for flag in ("-f m2s72a2d.ini", "--repeat=1 -r 0", "--cmdenv-express-mode=false", "--fingerprint=0000-0000/tplx",
                     "-x nasctime.nodes -u Cmdenv", f"--result-dir=/r/runs/{c}", "gzip -n -1"):
            assert flag in sim, (flag, sim)
    order = [i for i, x in enumerate(a) if "m2s72_a2d.py twin" in x or "a21 /r/runs" in x or "m2s72_a2d.py coverage" in x]
    assert len(order) == 3 and order == sorted(order), a
    assert "--contract full" in a[order[1]]
    for bad in (("n", "/s", "/i", D.DIAG, "/o"), ("/n", "/s", "/i", D.A2V1, "/o"), ("/n", "/s", "/i", D.BASE, "/o")):
        try:
            D.sim_argv(*bad)
            raise AssertionError(f"accepted {bad}")
        except D.EvalError:
            pass
    src = open(os.path.join(M2, "m2s72s5.sh")).read()
    for flag in ("--cmdenv-express-mode=false", "--fingerprint=0000-0000/tplx", "-x nasctime.nodes -u Cmdenv"):
        assert flag in src


@test("boundaries: the new files never assign S5N_ADAPTER_VALIDATED, never write the FGO registry or an expectation "
      "file, never call opp_run outside 'resolve', and never change a verdict")
def _():
    for rel in ("simulations/m2/check/m2s72_a2d.py", "simulations/m2/m2s72a2d.ini"):
        t = open(os.path.join(NASCTIME, rel)).read()
        assert "S5N_ADAPTER_VALIDATED" not in t, rel
        assert not re.search(r"fgo_registry\.json['\"]\s*,\s*['\"][wa]", t) and "expect/" not in t, rel
    src = open(os.path.join(HERE, "m2s72_a2d.py")).read()
    # exactly two simulator calls: -q runconfig (resolve) and the bounded initialization smoke (stopped at t = 0)
    assert src.count("subprocess.run(") == 2 and "-q\", \"runconfig\"" in src, "opp_run only for runconfig and the smoke"
    assert '"--sim-time-limit=0s"' in src and "SMOKE_ARGS" in src and src.count("SMOKE_ARGS") >= 2
    assert "a21_verdict_verbatim" in src


def main():
    for nm, ok, det in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} | {nm}" + ("" if ok else f" | {det}"))
    n = sum(1 for x in RESULTS if x[1])
    print(f"A2 diagnostic tests: {n} / {len(RESULTS)} PASS, {len(RESULTS) - n} FAIL")
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
