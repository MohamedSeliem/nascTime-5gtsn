#!/usr/bin/env python3
"""M2-S7.2a S5-1 tests (no simulation): run outcome classification (SIM-ABORT), the per-run free-space rule, manifests,
tier-B retention, the committed-records check, the RD-4 option-diff classifier, the configuration-name parser and the
Q-0p analysis mapping, the E0v generator (regeneration and refusals), and the runner's guards and per-run lifecycle
end to end with a stub simulator and a stub checker (m2s72s5.sh test hooks).

    python3 check/test_m2s72s5.py            -> one line per test, a summary; exit 0 iff every test passes
"""
import gzip
import importlib.util
import json
import os
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
NASCTIME = os.path.dirname(os.path.dirname(M2))
sys.path.insert(0, HERE)
import m2s72s5_lib as LIB  # noqa: E402

_spec = importlib.util.spec_from_file_location("m2s72s5_gen", os.path.join(M2, "tools", "m2s72s5_gen.py"))
G5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G5)

RESULTS = []


def test(name):
    def deco(fn):
        try:
            fn()
            RESULTS.append((name, True, ""))
        except AssertionError as ex:
            RESULTS.append((name, False, str(ex)[:300]))
        except Exception as ex:   # noqa: BLE001
            RESULTS.append((name, False, f"{type(ex).__name__}: {ex}"[:300]))
        return fn
    return deco


# ---------------------------------------------------------------------------------- outcome classification ------
ABORT_HARQ = ("<!> Error in module (simu5g::LteMacEnb) M2S72Bridge.gnb1.cellularNic.mac (id=150), at t=3.20100s, event #1: "
              "LteMacEnb::macPduMake(): no free H-ARQ process for the MAC PDU to UE 2049, codeword 0 -- in module ...\n")
ABORT_UE = "<!> Error: LteMacUe::macPduMake(): no free H-ARQ process for the UL MAC PDU to node 1, codeword 0\n"
ABORT_INACT = "<!> Error: LteSchedulerEnb::scheduleGrant(): connection MacCid(nodeId=2049, lcid=1) is marked inactive with 1420 bytes in its buffer\n"
NORMAL = ("1.2|M2S72Bridge.gnb1.cellularNic.mac|LteMaxCI::schedule connection MacCid(nodeId=2049, lcid=1) was found ineligible\n"
          "2.0|M2S72Bridge.ue[0].cellularNic.nrMac|NrMacUe::handleSelfMessage - no free H-ARQ process for the grant on carrier [2GHz], the grant is not used\n"
          "<!> Simulation time limit reached -- at t=12s, event #123\n")


@test("classify: gNB 'no free H-ARQ process' with rc != 0 -> SIM-ABORT")
def _():
    assert LIB.classify(1, NORMAL + ABORT_HARQ)[0] == "SIM-ABORT"


@test("classify: UE UL 'no free H-ARQ process' -> SIM-ABORT")
def _():
    assert LIB.classify(134, ABORT_UE)[0] == "SIM-ABORT"


@test("classify: 'marked inactive with N bytes' -> SIM-ABORT")
def _():
    assert LIB.classify(1, ABORT_INACT)[0] == "SIM-ABORT"


@test("classify: an abort text with rc 0 -> ERROR (fail closed, never OK)")
def _():
    assert LIB.classify(0, ABORT_HARQ)[0] == "ERROR"


@test("classify: rc 124 -> TIMEOUT")
def _():
    assert LIB.classify(124, NORMAL)[0] == "TIMEOUT"


@test("classify: the UE info line 'no free H-ARQ process for the grant ... not used' alone, rc 1 -> ERROR, not SIM-ABORT")
def _():
    assert LIB.classify(1, NORMAL)[0] == "ERROR"


@test("classify: other runtime error -> ERROR, not SIM-ABORT")
def _():
    assert LIB.classify(1, "<!> Error in module x: something else\n")[0] == "ERROR"


@test("classify: rc 0 with an error line -> ERROR")
def _():
    assert LIB.classify(0, "<!> Error: bad parameter\n")[0] == "ERROR"


@test("classify: normal log incl. the UE 'grant is not used' info line -> OK")
def _():
    assert LIB.classify(0, NORMAL) == ("OK", "rc 0")


# --------------------------------------------------------------------------------------------- free space -------
@test("space rule: free >= 1.5 x run + twin + 1 GB + 2 GB")
def _():
    g = LIB.GB
    ok, req = LIB.space_rule(7 * g, 2 * g, 2 * g)
    assert req == 3 * g + 2 * g + g + 2 * g and not ok
    assert LIB.space_rule(8 * g, 2 * g, 2 * g)[0]
    assert not LIB.space_rule(8 * g - 1, 2 * g, 2 * g)[0]


# ------------------------------------------------------------------------------ manifests and retention ---------
def _tree(d):
    os.makedirs(os.path.join(d, "run", "sub"))
    open(os.path.join(d, "run", "a.pcapng"), "wb").write(os.urandom(5000))
    open(os.path.join(d, "run", "sub", "b.csv"), "w").write("t,x\n1,2\n")
    with gzip.open(os.path.join(d, "run.log.gz"), "wb") as fh:
        fh.write(b"log\n")


@test("manifest: every file listed; verify passes; a changed byte and a missing file fail")
def _():
    d = tempfile.mkdtemp()
    try:
        _tree(d)
        man = os.path.join(d, "m.sha256")
        h, n = LIB.manifest(man, [os.path.join(d, "run"), os.path.join(d, "run.log.gz")])
        assert n == 3, n
        assert LIB.verify_manifest(man)[0]
        p = os.path.join(d, "run", "sub", "b.csv")
        open(p, "a").write("x")
        assert not LIB.verify_manifest(man)[0]
        os.remove(p)
        assert not LIB.verify_manifest(man)[0]
    finally:
        shutil.rmtree(d)


@test("retain (tier B): gzip -n in place, originals removed, manifest still verifies; a corrupted .gz fails")
def _():
    d = tempfile.mkdtemp()
    try:
        _tree(d)
        man = os.path.join(d, "m.sha256")
        LIB.manifest(man, [os.path.join(d, "run"), os.path.join(d, "run.log.gz")])
        ok, probs = LIB.retain(man)
        assert ok, probs
        assert os.path.exists(os.path.join(d, "run", "a.pcapng.gz")) and not os.path.exists(os.path.join(d, "run", "a.pcapng"))
        assert LIB.verify_manifest(man)[0]
        g = os.path.join(d, "run", "sub", "b.csv.gz")
        with gzip.open(g, "wb") as fh:
            fh.write(b"different\n")
        assert not LIB.verify_manifest(man)[0]
    finally:
        shutil.rmtree(d)


@test("committed: HEAD blob equal -> ok; local differs -> fail; path not in HEAD -> fail")
def _():
    d = tempfile.mkdtemp()
    try:
        r = os.path.join(d, "repo")
        os.makedirs(r)
        git = lambda *a: subprocess.run(["git", "-C", r] + list(a), check=True, capture_output=True)  # noqa: E731
        git("init", "-q")
        git("config", "user.email", "t@t")
        git("config", "user.name", "t")
        open(os.path.join(r, "x.txt"), "w").write("record\n")
        git("add", "x.txt")
        git("commit", "-q", "-m", "x")
        loc = os.path.join(d, "x.txt")
        open(loc, "w").write("record\n")
        assert LIB.committed(r, [("x.txt", loc)])[0]
        open(loc, "w").write("other\n")
        assert not LIB.committed(r, [("x.txt", loc)])[0]
        assert not LIB.committed(r, [("y.txt", loc)])[0]
    finally:
        shutil.rmtree(d)


# ---------------------------------------------------------------------------------- RD-4 diff classifier -------
DRB = '[{coreNetwork: "5gc", ue: "ue[0]", drbId: 1, isDefault: true, lcg: 3, rlcMode: "UM"%s}, {coreNetwork: "5gc", ue: "ue[0]", drbId: 2, mappedQfis: [5], lcg: 1, rlcMode: "UM"%s}%s]'
P_BE = ', profile: "nasc-be"'
DRB4 = ', {coreNetwork: "5gc", ue: "ue[0]", drbId: 4, mappedQfis: [10], lcg: 2, rlcMode: "UM", profile: "%s"}'
RULE5 = '[{filter: "expr(pcp == 5)", qfi: 5}]'
RULE10 = '[{filter: "expr(gptp)", qfi: 10}, {filter: "expr(pcp == 5)", qfi: 5}]'
SB = "*.bearerConfigurator.staticDrbs"
Q0 = {SB: DRB % ("", "", "")}
Q0P = {SB: DRB % (P_BE, P_BE, ""), "*.gnb1.cellularNic.mac.schedulingDisciplineDl": '"QOS_PF"',
       "*.gnb1.cellularNic.mac.schedulingDisciplineUl": '"QOS_PF"', "*.bearerConfigurator.drbProfiles": "{}"}
QDE = dict(Q0P, **{SB: DRB % (P_BE, P_BE, DRB4 % "nasc-be"), "*.bearerConfigurator.dlQfiRules": RULE10})
QDU = dict(QDE, **{SB: DRB % (P_BE, P_BE, DRB4 % "nasc-gptp")})
Q0P[ "*.bearerConfigurator.dlQfiRules"] = RULE5
Q0["*.bearerConfigurator.dlQfiRules"] = RULE5


@test("RD-4 classifier: q0->q0p scheduler ISOLATED; q0p->qde mapping ISOLATED; qde->qdu priority ISOLATED")
def _():
    assert not G5.classify_diff("scheduler", Q0, Q0P)[1]
    assert not G5.classify_diff("mapping", Q0P, QDE)[1]
    assert not G5.classify_diff("priority", QDE, QDU)[1]


@test("RD-4 classifier: q0p->qdu is NOT mapping-only (the gPTP DRB has another profile)")
def _():
    assert G5.classify_diff("mapping", Q0P, QDU)[1] == [SB]


@test("RD-4 classifier mutations: a load / traffic difference, an RLC-mode change, a scheduler change are not allowed")
def _():
    a = dict(Q0P, **{"*.listener.app[3].source.productionInterval": "250us"})
    b = dict(Q0P, **{"*.listener.app[3].source.productionInterval": "200us"})
    assert "*.listener.app[3].source.productionInterval" in G5.classify_diff("scheduler", a, b)[1]
    rlc = dict(Q0P, **{SB: (DRB % (P_BE, P_BE, "")).replace('"UM", profile: "nasc-be"}, {', '"AM", profile: "nasc-be"}, {', 1)})
    assert SB in G5.classify_diff("scheduler", Q0, rlc)[1]
    sch = dict(QDE, **{"*.gnb1.cellularNic.mac.schedulingDisciplineDl": '"MAXCI"'})
    assert "*.gnb1.cellularNic.mac.schedulingDisciplineDl" in G5.classify_diff("mapping", Q0P, sch)[1]
    assert G5.classify_diff("priority", QDE, dict(QDU, **{"*.bearerConfigurator.dlQfiRules": RULE5}))[1]


# ------------------------------------------------------------------------------- names, analysis mapping -------
@test("name parser: E0v / twins / H5 / E0 (1.8.0) / E0v-N; unknown names refused")
def _():
    import check_m2s72_s5v as V
    assert V.parse_name("M2S72-E0v-q0p-f2") == ("E0v", "q0p", True, 2, 1)
    assert V.parse_name("M2S72-E0vH5-qdu-f1") == ("E0vH5", "qdu", False, 1, 1)
    assert V.parse_name("M2S72-E0vH5NL-q0-f1")[0] == "E0vH5NL"
    assert V.parse_name("M2S72-E0-q0-f8") == ("E0", "q0", True, 8, 1)
    assert V.parse_name("M2S72-E0vNH5-q0p-sym-n8-f1p25")[:2] == ("E0vN", "q0p")
    assert V.parse_name("M2S72-E0v-qde-f1") == ("E0v", "qde", True, 1, 1) and V.ANALYSIS_OPT["qde"] == "qdu"
    for bad in ("M2S72-E0-q0p-f1", "M2S72-E0-qde-f1", "M2S72-E2-q0-one0-n1-f1", "X"):
        try:
            V.parse_name(bad)
            raise AssertionError(f"{bad} accepted")
        except ValueError:
            pass


@test("Q-0p analysis mapping: m2s71_lib OPTIONS q0p = q0 in DRBs / RLC mode / split; scheduler differs")
def _():
    import m2s71_lib as L
    assert L.OPTIONS["q0p"][:4] == L.OPTIONS["q0"][:4] and L.OPTIONS["q0p"][4] != L.OPTIONS["q0"][4]
    assert L.QFI["q0p"] == L.QFI["q0"]


# ---------------------------------------------------------------------------------------------- generator ------
@test("generator: m2s72s5.ini regenerates byte for byte; m2s72.ini unchanged; every matrix config present")
def _():
    text, _ = G5.generate()
    assert text == open(G5.OUT5).read(), "m2s72s5.ini differs from the regenerated text"
    for nm in G5.matrix():
        assert f"[Config {nm}]\n" in text, nm
    assert text.splitlines()[9] == "include m2s72.ini"


def _fresh_gen():
    spec = importlib.util.spec_from_file_location("m2s72s5_gen_t", os.path.join(M2, "tools", "m2s72s5_gen.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


@test("Q-de (D-1): each per-N mixin is Q-d's accepted section with only the gPTP DRB profile changed; base / D-4 extend Q-d's")
def _():
    import re
    ini = open(G5.OUT5).read()
    acc = open(G5.G.OUT).read()
    sec = lambda txt, nm: re.search(rf"^\[Config {re.escape(nm)}\]\n(.*?)(?=^\[Config |\Z)", txt, re.M | re.S).group(1)  # noqa: E731
    for n in G5.QDE_NS:
        a = sec(acc, f"M2S72N{n}-qdu-Ca-L").split("\n")[1:]
        b = sec(ini, f"M2S72N{n}-qde-Ca-L").split("\n")[1:]
        assert len(a) == len(b)
        d = [(x, y) for x, y in zip(a, b) if x != y]
        assert len(d) == n and all(x.replace('"nasc-gptp"', '"nasc-be"') == y and "drbId: 4" in x for x, y in d), d
        assert f"extends = M2S72D4N{n}-qdu-Ca-L" in sec(ini, f"M2S72D4N{n}-qde-Ca-L")
    assert "extends = M2S72B-qdu-Ca-L" in sec(ini, "M2S72B-qde-Ca-L")
    m = G5.matrix()
    assert {k for k, v in m.items() if v[0] == "qde" and v[-1] == "p"} == {"M2S72-E0v-qde-f1", "M2S72-E0v-qde-f2"}
    assert all(v[5] for v in m.values() if v[0] == "qde"), "Q-de must be HARQ16 only (D-1)"


@test("Q-de refusal: a gPTP-profile substitution outside DRB 4 or with the wrong count is refused")
def _():
    g = _fresh_gen()
    real = g.G.OUT
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "m2s72.ini")
        txt = open(real).read()
        i = txt.index("[Config M2S72N1-qdu-Ca-L]")
        j = txt.index('drbId: 2, mappedQfis: [5], lcg: 1, rlcMode: "UM", profile: "nasc-be"}', i)
        base = txt[:j] + txt[j:].replace('profile: "nasc-be"}', 'profile: "nasc-gptp"}', 1)
        open(p, "w").write(base)
        try:
            g.qde_sections(base, set())
            raise AssertionError("accepted")
        except g.GenError as ex:
            assert "outside the gPTP DRB" in str(ex), ex
    finally:
        shutil.rmtree(d)


@test("generator refusal: a factor whose interval is not an exact ns (0.75 at one loaded UE)")
def _():
    g = _fresh_gen()
    g.E0VN_FACTORS = (0.75,)
    try:
        g.generate()
        raise AssertionError("accepted")
    except g.GenError as ex:
        assert "integer number of ns" in str(ex), ex


@test("generator refusal: a config name already defined in m2s72.ini")
def _():
    g = _fresh_gen()
    orig = g.matrix
    g.matrix = lambda: dict(orig(), **{"M2S72-E0-q0-f1": ("q0", "one0", 1, 1, 1, True, True, "core")})
    try:
        g.generate()
        raise AssertionError("accepted")
    except g.GenError as ex:
        assert "already defined" in str(ex), ex


@test("generator refusal: m2s72.ini not regenerated byte for byte by the accepted generator")
def _():
    g = _fresh_gen()
    real = g.G.OUT
    d = tempfile.mkdtemp()
    try:
        p = os.path.join(d, "m2s72.ini")
        open(p, "w").write(open(real).read() + "\n# edited\n")
        g.G.OUT = p
        try:
            g.generate()
            raise AssertionError("accepted")
        except g.GenError as ex:
            assert "byte for byte" in str(ex), ex
    finally:
        g.G.OUT = real
        shutil.rmtree(d)


# --------------------------------------------------------------------------- MAC-log grammar and occupancy ------
GNB = "M2S72Bridge.gnb1.cellularNic.mac"
UEM = "M2S72Bridge.ue[0].cellularNic.nrMac"


def _log(lines):
    d = tempfile.mkdtemp()
    p = os.path.join(d, "run.log.gz")
    with gzip.open(p, "wt") as fh:
        fh.write("".join(lines))
    return d, p


@test("grammar: H-ARQ occupancy in LOG order (feedback logged after the insert of the same TTI keeps the process busy)")
def _():
    import check_m2s72_s5v as V
    ins = lambda t, p: f"{t}|{GNB}|H-ARQ TX: new pdu (id {p} ) inserted into process {p} codeword id: 0 for node with id 2049\n"  # noqa: E731
    fb = lambda t, p: f"{t}|{GNB}|H-ARQ TX: feedback received for process {p} codeword 0 result is ACK\n"  # noqa: E731
    # TTI 0: insert p0; TTI 1: insert p1, then (same time, logged after) feedback p0 -> peak 2 in TTI 1
    d, p = _log([ins("0.000", 0), ins("0.001", 1), fb("0.001", 0), f"0.002|{GNB}|-----ENB MAIN LOOP -----\n"])
    try:
        _, _, _, occ = V.grammar(p)
        assert occ["peak_busy_within_tti_hist"] == {"1": 2, "2": 1}, occ
        assert occ["max_peak_busy"] == 2 and occ["inserts"] == 2, occ
        assert occ["busy_at_first_logged_line_of_tti_hist"] == {"0": 1, "1": 2}, occ
    finally:
        shutil.rmtree(d)


@test("grammar: UE 'grant is not used' counted (not a loss); a UE loss-like line and a 1.8.0-only text fail MG-1")
def _():
    import check_m2s72_s5v as V
    import m2s72_maclog as ML
    ok_line = f"1.0|{UEM}|NrMacUe::handleSelfMessage - no free H-ARQ process for the grant on carrier [2GHz], the grant is not used\n"
    d, p = _log([ok_line, f"1.1|{GNB}|-----ENB MAIN LOOP -----\n"])
    try:
        _, removed, unused, _ = V.grammar(p)
        assert len(unused) == 1 and not removed, (unused, removed)
    finally:
        shutil.rmtree(d)
    d, p = _log([f"1.0|{UEM}|LteMacUe::macPduMake - no free H-ARQ process for this D2D MAC PDU, deleting it\n",
                 f"1.1|{GNB}|macPduMake() : no available process for this MAC PDU in TxHarqBuffer\n"])
    try:
        _, removed, _, _ = V.grammar(p)
        assert sum(removed.values()) == 2, removed
        start = len(V.rows)
        ok = V.mg1_row("t", ML.MacLog(p), removed)
        del V.rows[start:]
        assert not ok
    finally:
        shutil.rmtree(d)


@test("manifest: a missing result directory is skipped (early abort); a manifest of nothing is refused")
def _():
    d = tempfile.mkdtemp()
    try:
        log = os.path.join(d, "run.log.gz")
        with gzip.open(log, "wb") as fh:
            fh.write(b"x")
        _, n = LIB.manifest(os.path.join(d, "m"), [os.path.join(d, "absent"), log])
        assert n == 1
        try:
            LIB.manifest(os.path.join(d, "m2"), [os.path.join(d, "absent")])
            raise AssertionError("manifest of nothing accepted")
        except ValueError:
            pass
    finally:
        shutil.rmtree(d)


# ------------------------------------------------------------------------------------- runner, end to end -------
STUB_OPP = r'''#!/bin/bash
# stub opp_run (tests only): -v -> version; else writes a small result tree and a log; behaviour by STUB_SIM
[ "$1" = -v ] && { echo "Version: STUB"; exit 0; }
cfg=""; rd=""
for a in "$@"; do case "$a" in --result-dir=*) rd=${a#--result-dir=} ;; esac; done
while [ $# -gt 0 ]; do [ "$1" = -c ] && cfg=$2; shift; done
mkdir -p "$rd/$cfg/pcap"
head -c 2000 /dev/urandom > "$rd/$cfg/pcap/x.pcapng"; echo "t,v" > "$rd/$cfg/x.csv"
echo "1.0|M2S72Bridge.gnb1.cellularNic.mac|LteMaxCI::schedule granted 10 bytes to connection MacCid(nodeId=2049, lcid=1)"
case "${STUB_SIM:-ok}:$cfg" in
  abort:*q0p-f1*) echo "<!> Error in module (simu5g::LteMacEnb) x: LteMacEnb::macPduMake(): no free H-ARQ process for the MAC PDU to UE 2049, codeword 0"; exit 1 ;;
esac
echo "<!> Simulation time limit reached"; exit 0
'''
STUB_CHECK = r'''#!/usr/bin/env python3
import json, os, sys
cmd = sys.argv[1]
if cmd == "run":
    runs, cfg, rec = sys.argv[2:5]
    rc = int(os.environ.get("STUB_CHECK_RC", "0"))
    open(os.path.join(rec, cfg + ".check.txt"), "w").write("stub check\n")
    json.dump({"config": cfg}, open(os.path.join(rec, cfg + ".digest.json"), "w"))
    print(f"{cfg}: {'PASS' if rc == 0 else 'FAIL'}"); sys.exit(rc)
if cmd == "quick":
    print(f"{sys.argv[3]}: cohort GM Syncs 80, not received by DS-TT 0 by T_end 0 (0.0000)"); sys.exit(0)
if cmd in ("controls-q8", "controls-sg", "nonpert"):
    open(os.environ["STUB_CALLS"], "a").write(" ".join(sys.argv[1:]) + "\n"); print("stub " + cmd + ": as declared"); sys.exit(0)
sys.exit(2)
'''


def _env(d, version="1.8.1", **kw):
    om = os.path.join(d, "omnetpp")
    os.makedirs(os.path.join(om, "bin"), exist_ok=True)
    open(os.path.join(om, "setenv"), "w").write(f'export PATH="{om}/bin:$PATH"\n')
    open(os.path.join(om, "bin", "opp_run"), "w").write(STUB_OPP)
    os.chmod(os.path.join(om, "bin", "opp_run"), 0o755)
    s5 = os.path.join(d, "simu5g")
    os.makedirs(os.path.join(s5, "src"), exist_ok=True)
    open(os.path.join(s5, "Version"), "w").write(version)
    chk = os.path.join(d, "stubcheck.py")
    open(chk, "w").write(STUB_CHECK)
    env = dict(os.environ, OMNETPP_ROOT=om, INET_ROOT=os.path.join(d, "inet"), SIMU5G_ROOT=s5,
               NASCTIME_RESULTS_ROOT=os.path.join(d, "root"), S5_TEST_SKIP_BUILD="1", S5_TEST_CHECKER=chk,
               S5_ENV_DECISION="test", STUB_CALLS=os.path.join(d, "calls.txt"))
    env.pop("S5_RECORDS_REPO", None)
    env.update(kw)
    return env


def _repo(d):
    r = os.path.join(d, "records-repo")
    os.makedirs(r)
    for a in (["init", "-q"], ["config", "user.email", "t@t"], ["config", "user.name", "t"], ["commit", "-q", "--allow-empty", "-m", "init"]):
        subprocess.run(["git", "-C", r] + a, check=True, capture_output=True)
    return r


def _runner(env, *args):
    return subprocess.run([os.path.join(M2, "m2s72s5.sh")] + list(args), env=env, capture_output=True, text=True)


@test("runner guard: no S5_ENV_DECISION -> refused before anything is created (RD-7)")
def _():
    d = tempfile.mkdtemp()
    try:
        env = _env(d)
        env.pop("S5_ENV_DECISION")
        r = _runner(env, "e0vp")
        assert r.returncode != 0 and "not confirmed" in r.stderr, r.stderr
        assert not os.path.exists(os.path.join(d, "root", "m2", "M2-S7.2a-e0vp"))
    finally:
        shutil.rmtree(d)


@test("runner guard: Simu5G Version other than 1.8.1 -> refused")
def _():
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, version="1.8.0"), "e0vp")
        assert r.returncode != 0 and "not 1.8.1" in r.stderr, r.stderr
    finally:
        shutil.rmtree(d)


@test("runner guard: no NASCTIME_RESULTS_ROOT (legacy mode) -> refused; a root inside simulations/m2/results -> refused")
def _():
    d = tempfile.mkdtemp()
    try:
        env = _env(d)
        env.pop("NASCTIME_RESULTS_ROOT")
        r = _runner(env, "e0vp")
        assert r.returncode != 0 and "NASCTIME_RESULTS_ROOT" in r.stderr, r.stderr
        r = _runner(_env(d, NASCTIME_RESULTS_ROOT=os.path.join(M2, "results", "x")), "e0vp")
        assert r.returncode != 0 and "legacy results tree" in r.stderr, r.stderr
    finally:
        shutil.rmtree(d)


@test("runner lifecycle (records repo): runs OK -> check -> manifest -> records committed and verified -> raw deleted")
def _():
    d = tempfile.mkdtemp()
    try:
        repo = _repo(d)
        r = _runner(_env(d, S5_RECORDS_REPO=repo), "e0vp")
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
        out = os.path.join(d, "root", "m2", "M2-S7.2a-e0vp")
        assert not os.path.exists(os.path.join(out, "runs", "M2S72-E0v-q0p-f1")), "raw not deleted"
        rec = os.path.join(out, "records")
        led = open(os.path.join(rec, "ledger.tsv")).read()
        assert led.count("raw deleted after its manifest and records were committed") == 4, led
        log = subprocess.run(["git", "-C", repo, "log", "--format=%s"], capture_output=True, text=True).stdout
        assert "S5 records:" in log, log
        rel = subprocess.run(["git", "-C", repo, "ls-files"], capture_output=True, text=True).stdout
        assert "M2S72-E0v-q0p-f1.manifest.sha256" in rel and "M2S72-E0v-q0p-f2.check.txt" in rel, rel
        # the committed manifest lists the deleted raw files with their hashes
        man = [l for l in rel.splitlines() if l.endswith("M2S72-E0v-q0p-f1.manifest.sha256")][0]
        assert "x.pcapng" in open(os.path.join(repo, man)).read()
    finally:
        shutil.rmtree(d)


@test("runner lifecycle (no records repo): raw outputs kept, pending release; 'release' later commits then deletes")
def _():
    d = tempfile.mkdtemp()
    try:
        env = _env(d)
        r = _runner(env, "e0vp")
        assert r.returncode == 0, r.stderr[-500:]
        out = os.path.join(d, "root", "m2", "M2-S7.2a-e0vp")
        assert os.path.isdir(os.path.join(out, "runs", "M2S72-E0v-q0p-f1"))
        assert open(os.path.join(out, "records", "pending-release.txt")).read().split() == [
            "M2S72-E0v-q0p-f1", "M2S72-E0v-qde-f1", "M2S72-E0v-q0p-f2", "M2S72-E0v-qde-f2"]
        repo = _repo(d)
        env["S5_RECORDS_REPO"] = repo
        r = _runner(env, "release", "M2-S7.2a-e0vp")
        assert r.returncode == 0, r.stderr[-500:]
        assert not os.path.exists(os.path.join(out, "runs", "M2S72-E0v-q0p-f1"))
    finally:
        shutil.rmtree(d)


@test("runner: SIM-ABORT -> batch stops (exit 5), outcome recorded, raw kept as tier B (gzip, verified), nothing deleted")
def _():
    d = tempfile.mkdtemp()
    try:
        repo = _repo(d)
        r = _runner(_env(d, S5_RECORDS_REPO=repo, STUB_SIM="abort"), "e0vp")
        assert r.returncode == 5, (r.returncode, r.stdout[-500:])
        out = os.path.join(d, "root", "m2", "M2-S7.2a-e0vp")
        tsv = open(os.path.join(out, "records", "runs.tsv")).read()
        assert "\tSIM-ABORT\t" in tsv, tsv
        assert os.path.exists(os.path.join(out, "runs", "M2S72-E0v-q0p-f1", "M2S72-E0v-q0p-f1", "x.csv.gz"))
        assert subprocess.run(["python3", os.path.join(HERE, "m2s72s5_lib.py"), "verify-manifest",
                               os.path.join(out, "records", "M2S72-E0v-q0p-f1.manifest.sha256")], capture_output=True).returncode == 0
        assert not os.path.exists(os.path.join(out, "runs", "M2S72-E0v-q0p-f2")), "batch did not stop"
    finally:
        shutil.rmtree(d)


@test("runner: a failed per-run check -> batch stops (exit 6), raw kept as tier B")
def _():
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, STUB_CHECK_RC="1"), "e0vp")
        assert r.returncode == 6, (r.returncode, r.stdout[-500:])
        out = os.path.join(d, "root", "m2", "M2-S7.2a-e0vp")
        assert os.path.exists(os.path.join(out, "runs", "M2S72-E0v-q0p-f1", "M2S72-E0v-q0p-f1", "x.csv.gz"))
        assert "tier B" in open(os.path.join(out, "records", "ledger.tsv")).read()
    finally:
        shutil.rmtree(d)


def _rmtree_ro(d):
    """cleanup of a tree that holds read-only smoke evidence (rmtree needs writable directories as non-root)"""
    for root, dirs, _ in os.walk(d):
        for x in dirs:
            os.chmod(os.path.join(root, x), 0o755)
    shutil.rmtree(d)


@test("runner smoke: one run E0v-q0-f1, check, quick, controls-q8, manifest; raw held uncompressed and read-only; "
      "nothing committed or deleted even with S5_RECORDS_REPO; release of the smoke stage refused")
def _():
    d = tempfile.mkdtemp()
    try:
        repo = _repo(d)
        env = _env(d, S5_RECORDS_REPO=repo)
        r = _runner(env, "smoke")
        assert r.returncode == 0, r.stdout[-800:] + r.stderr[-800:]
        out = os.path.join(d, "root", "m2", "M2-S7.2a-s5smoke")
        run = os.path.join(out, "runs", "M2S72-E0v-q0-f1")
        assert sorted(os.listdir(os.path.join(out, "runs"))) == ["M2S72-E0v-q0-f1", "run-M2S72-E0v-q0-f1.log.gz"]
        x = os.path.join(run, "M2S72-E0v-q0-f1", "x.csv")
        assert os.path.exists(x) and not os.path.exists(x + ".gz"), "smoke raw must stay uncompressed"
        assert not (os.stat(x).st_mode & 0o222) and not (os.stat(run).st_mode & 0o222), "smoke raw not read-only"
        rec = os.path.join(out, "records")
        assert "held (smoke review" in open(os.path.join(rec, "ledger.tsv")).read()
        assert not os.path.exists(os.path.join(rec, "pending-release.txt"))
        tsv = open(os.path.join(rec, "runs.tsv")).read().splitlines()
        assert len(tsv) == 2 and "\tOK\t" in tsv[1] and "\theld\t" in tsv[1], tsv
        assert open(env["STUB_CALLS"]).read().startswith("controls-q8 "), "controls-q8 not called"
        assert "manifest verified" in open(os.path.join(rec, "steps.txt")).read()
        log = subprocess.run(["git", "-C", repo, "log", "--format=%s"], capture_output=True, text=True).stdout
        assert "S5 records" not in log, log
        r = _runner(env, "release", "M2-S7.2a-s5smoke")
        assert r.returncode != 0 and "never released" in r.stderr, r.stderr
        assert os.path.exists(x)
        r = _runner(env, "smoke")
        assert r.returncode != 0 and "never overwritten" in r.stderr, r.stderr
    finally:
        _rmtree_ro(d)


@test("runner smoke: a failed per-run check -> exit 6, every later step still recorded, raw held uncompressed")
def _():
    d = tempfile.mkdtemp()
    try:
        r = _runner(_env(d, STUB_CHECK_RC="1"), "smoke")
        assert r.returncode == 6, (r.returncode, r.stdout[-500:])
        out = os.path.join(d, "root", "m2", "M2-S7.2a-s5smoke")
        assert os.path.exists(os.path.join(out, "runs", "M2S72-E0v-q0-f1", "M2S72-E0v-q0-f1", "x.csv"))
        steps = open(os.path.join(out, "records", "steps.txt")).read()
        assert "NOT CLEAN (check 1, quick 0, controls 0, manifest 0)" in steps, steps[-600:]
    finally:
        _rmtree_ro(d)


@test("runner: an existing stage directory is never overwritten")
def _():
    d = tempfile.mkdtemp()
    try:
        env = _env(d)
        assert _runner(env, "e0vp").returncode == 0
        r = _runner(env, "e0vp")
        assert r.returncode != 0 and "never overwritten" in r.stderr, r.stderr
    finally:
        shutil.rmtree(d)


@test("runner e0v (stub): factors 1, 2, 4, 8, controls on q0-f1 and qdu-f2, twin of the top factor, every hold released")
def _():
    d = tempfile.mkdtemp()
    try:
        repo = _repo(d)
        env = _env(d, S5_RECORDS_REPO=repo)
        r = _runner(env, "e0v")
        assert r.returncode == 0, r.stdout[-1500:] + r.stderr[-500:]
        out = os.path.join(d, "root", "m2", "M2-S7.2a-e0v")
        calls = open(env["STUB_CALLS"]).read().split("\n")
        assert any(c.startswith("controls-q8") and "M2S72-E0v-q0-f1" in c for c in calls), calls
        assert any(c.startswith("controls-sg") and "M2S72-E0v-qdu-f2" in c for c in calls), calls
        assert any(c.startswith("nonpert") and "M2S72-E0v-q0-f8 M2S72-E0vNL-q0-f8" in c for c in calls), calls
        left = [x for x in os.listdir(os.path.join(out, "runs"))]
        assert left == [], f"raw outputs left: {left}"
        tsv = open(os.path.join(out, "records", "runs.tsv")).read()
        assert tsv.count("\tOK\t") == 9, tsv
    finally:
        shutil.rmtree(d)


def main():
    for nm, ok, det in RESULTS:
        print(f"{'PASS' if ok else 'FAIL'} | {nm}" + ("" if ok else f" | {det}"))
    n = sum(1 for x in RESULTS if x[1])
    print(f"S5-1 tests: {n} / {len(RESULTS)} PASS")
    return 0 if n == len(RESULTS) else 1


if __name__ == "__main__":
    sys.exit(main())
