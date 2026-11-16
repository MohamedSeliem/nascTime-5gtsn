#!/usr/bin/env python3
"""Tests of the A2-V1 single-run wrapper m2s72a2v1.sh and its gate helper m2s72a2v1_gate.py: every failure path stops
before the simulation (or, after it, without evaluation or retry), keeps every output, and the configuration is the
reviewed one. NO simulation: the simulator is a stub (recorded TEST in every record); 'opp_run -q runconfig' is the
real OMNeT++ 6.5.0 ($OMNETPP_ROOT or /root/stack/omnetpp-6.5.0), so G0-config checks the real effective configuration.
Each test works in a temporary git clone of this repository (the wrapper requires a clean, authorised commit) and a
temporary results root laid out like the VM's; the real results root is never touched."""
import gzip
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import time

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a2 as A2  # noqa: E402
import m2s72_harqfix as F  # noqa: E402
import m2s72a2v1_gate as G  # noqa: E402
import m2s72s5_lib as LIB  # noqa: E402
import test_m2s72_a2 as TA  # noqa: E402

TESTS = []
BASE, CFG = G.BASE, G.CFG
REAL_OMNETPP = os.environ.get("OMNETPP_ROOT") or "/root/stack/omnetpp-6.5.0"
GIB = 1 << 30
STUB = r"""#!/bin/bash
case " $* " in *" -v "*) echo "Version: 6.5.0 (A2V1 test stub)"; exit 0 ;; esac
if [[ " $* " == *" runconfig "* ]]; then source "$A2V1_STUB_REAL_OMNETPP/setenv" -f >/dev/null 2>&1; exec opp_run "$@"; fi
echo sim >> "$A2V1_STUB_COUNT"
rd=""; for a in "$@"; do case $a in --result-dir=*) rd=${a#--result-dir=} ;; esac; done
mkdir -p "$rd/M2S72-E0vN-q0-one0-n2-f1_A2V1"
case "$A2V1_STUB_MODE" in
  ok) echo "0.1|M2S72Bridge.gnb1.cellularNic.mac|stub line"; echo "version 3" > "$rd/M2S72-E0vN-q0-one0-n2-f1_A2V1/0.sca"; exit 0 ;;
  fail) echo "<!> Error: stub simulation failure"; exit 1 ;;
  hang) sleep 60; exit 0 ;;
  big) head -c 20000000 /dev/zero > "$rd/big.bin"; sleep 60; exit 0 ;;
  tamper) echo changed >> "$A2V1_STUB_TAMPER"; echo "version 3" > "$rd/M2S72-E0vN-q0-one0-n2-f1_A2V1/0.sca"; exit 0 ;;
esac
exit 3
"""


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def sh(cmd, **kw):
    return subprocess.run(cmd, shell=True, check=True, capture_output=True, text=True, **kw).stdout.strip()


class Env:
    """a clean clone at an authorised commit, a stub stack, and a VM-like results root with a no-NACK baseline"""

    def __init__(self, change_ini=False):
        self.t = tempfile.mkdtemp()
        t = self.t
        self.repo = os.path.join(t, "repo")
        sh(f"git clone -q {REPO} {self.repo}")
        # the working tree's version of this increment (identical to HEAD once committed)
        for rel in ("simulations/m2/m2s72a2v1.sh", "simulations/m2/check/m2s72a2v1_gate.py",
                    "simulations/m2/check/test_m2s72a2v1_wrapper.py"):
            shutil.copy2(os.path.join(REPO, rel), os.path.join(self.repo, rel))
        if change_ini:
            with open(os.path.join(self.repo, "simulations/m2/m2s72a2v.ini"), "a") as fh:
                fh.write("**.harqReduction = 0.5\n")
        sh(f"cd {self.repo} && git add -A && git -c user.name=t -c user.email=t@t commit -q --allow-empty -m test")
        self.commit = sh(f"git -C {self.repo} rev-parse HEAD")
        # stack: stub OMNeT++ (real one for runconfig), INET / Simu5G version files, Simu5G sources (A2-0s)
        om = os.path.join(t, "omnetpp")
        os.makedirs(os.path.join(om, "bin"))
        open(os.path.join(om, "setenv"), "w").write(f'export PATH="{om}/bin:$PATH"\n')
        p = os.path.join(om, "bin", "opp_run")
        open(p, "w").write(STUB)
        os.chmod(p, 0o755)
        self.inet = os.path.join(t, "inet")
        os.makedirs(self.inet)
        open(os.path.join(self.inet, "Version"), "w").write("4.7.0\n")
        self.simu5g = os.path.join(t, "simu5g")
        os.makedirs(os.path.join(self.simu5g, "src"))
        open(os.path.join(self.simu5g, "Version"), "w").write("1.8.1\n")
        open(os.path.join(self.simu5g, "src", "libsimu5g.so"), "w").write("stub library\n")
        os.symlink(os.path.join(TA.root(), "src", "simu5g"), os.path.join(self.simu5g, "src", "simu5g"))
        # results root
        R = self.R = os.path.join(t, "R")
        for d in ("a2-v1", "a2-v3", "a2-env-check", "s5-smoke-1", "a2-p0"):
            os.makedirs(os.path.join(R, d))
            open(os.path.join(R, d, "record.txt"), "w").write(f"{d} preserved\n")
        json.dump({"per_ue": {"2049": {"inserts": 11700, "feedback": 11700, "nack": 0},
                              "2050": {"inserts": 1250, "feedback": 1250, "nack": 0}}},
                  open(os.path.join(R, "a2-v3", f"a2-{BASE}.json"), "w"))
        n2 = os.path.join(R, "s5-n2-1/m2/M2-S7.2a-s5smoke-n2")
        runs, rec = os.path.join(n2, "runs"), os.path.join(n2, "records")
        os.makedirs(os.path.join(runs, BASE, BASE))
        os.makedirs(rec)
        lines, node, truth = F.make(2, 300, lambda tt: [0] + ([1] if tt % 3 == 1 else []), d_ue=3)
        with gzip.open(os.path.join(runs, f"run-{BASE}.log.gz"), "wt") as fh:
            fh.writelines(TA.omnet(lines))
        sca = ["version 3\n"]
        for k, n in node.items():
            sca += [f'par M2S72Bridge.ue[{k}].cellularNic.nrChannelModel[0] typename "\\"simu5g.stack.phy.channelmodel.Tr38901ChannelModel\\""\n',
                    f"par M2S72Bridge.ue[{k}].cellularNic.nrMac macNodeId {n}\n",
                    f"scalar M2S72Bridge.ue[{k}].cellularNic.nrMac harqErrorRateDl:mean 0\n"]
        open(os.path.join(runs, BASE, BASE, "0.sca"), "w").writelines(sca)
        self.write_env_record(G.sha256(os.path.join(self.simu5g, "src", "libsimu5g.so")))
        LIB.manifest(os.path.join(rec, f"{BASE}.manifest.sha256"), [os.path.join(runs, BASE), os.path.join(runs, f"run-{BASE}.log.gz")])
        for e, d in (("s5-smoke-1", "s5-smoke-1"), ("s5-n2-1", "s5-n2-1"), ("a2-p0", "a2-p0"), ("a2-v3", "a2-v3")):
            sh(f"cd {R} && find {d} -type f | LC_ALL=C sort | xargs sha256sum > {e}-evidence.sha256")
        self.count = os.path.join(t, "sim-count.txt")

    def write_env_record(self, lib_sha):
        rec = os.path.join(self.R, "s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records/env-smoke-n2.txt")
        open(rec, "w").write(f"mode: smoke-n2\nlibsimu5g_sha256: {lib_sha}\ninet_version_file: 4.7.0\nsimu5g_version_file: 1.8.1\n")

    def run(self, mode="run", stub="ok", commit=None, timeout=600, **extra):
        env = dict(os.environ, OMNETPP_ROOT=os.path.join(self.t, "omnetpp"), INET_ROOT=self.inet, SIMU5G_ROOT=self.simu5g,
                   A2V1_RESULTS_ROOT=self.R, A2V1_COMMIT=commit or self.commit, A2V1_TEST_HOOKS="1",
                   A2V1_TEST_SKIP_SUITES="1", A2V1_TEST_FREE_BYTES=str(100 * GIB), A2V1_TEST_POLL_S="0.2",
                   A2V1_TEST_BUILD_CMD=f"touch {self.repo}/src/nasctime/m2/libnasctime_m2.so",
                   A2V1_STUB_REAL_OMNETPP=REAL_OMNETPP, A2V1_STUB_MODE=stub, A2V1_STUB_COUNT=self.count,
                   A2V1_STUB_TAMPER=os.path.join(self.R, "a2-v1", "record.txt"))
        env.update(extra)
        t0 = time.time()
        p = subprocess.run(["bash", os.path.join(self.repo, "simulations/m2/m2s72a2v1.sh"), mode], env=env,
                           capture_output=True, text=True, timeout=timeout)
        self.elapsed = time.time() - t0
        return p

    def out(self):
        return os.path.join(self.R, "a2-nack-1")

    def rec(self, name):
        p = os.path.join(self.out(), "records", name)
        return open(p).read() if os.path.exists(p) else ""

    def sims(self):
        return len(open(self.count).read().split()) if os.path.exists(self.count) else 0

    def close(self):
        for r, ds, fs in os.walk(self.t):
            for x in ds + fs:
                try:
                    os.chmod(os.path.join(r, x), stat.S_IRWXU)
                except OSError:
                    pass
        shutil.rmtree(self.t, ignore_errors=True)


def gate_failure(e, p, gate_id):
    assert p.returncode == 10, (p.returncode, p.stdout[-2000:], p.stderr[-2000:])
    assert e.sims() == 0, "a simulation started after a failed gate"
    assert f"GATE FAIL {gate_id}" in e.rec("steps.txt"), e.rec("steps.txt")[-1500:]
    assert "GATE FAILED" in e.rec("wrapper-verdict.txt")
    assert os.listdir(os.path.join(e.out(), "runs")) == []


def with_env(fn, **kw):
    e = Env(**kw)
    try:
        fn(e)
    finally:
        e.close()


# ------------------------------------------------------------------------------------------ gate helper ---------
@test("T-g-config-diff: the real runconfig diff of the reviewed configuration is accepted; one extra line, one missing "
      "declared line, or a truncated dump each fail (rc 1 / 2)")
def _():
    t = tempfile.mkdtemp()
    try:
        env = f"source {REAL_OMNETPP}/setenv -f >/dev/null 2>&1; cd {M2}"
        sh(f"{env}; opp_run -u Cmdenv -f m2s72s5.ini -c {BASE} -r 0 -q runconfig > {t}/b.txt", executable="/bin/bash")
        sh(f"{env}; opp_run -u Cmdenv -f m2s72a2v.ini -c {CFG} -r 0 -q runconfig > {t}/n.txt", executable="/bin/bash")
        assert G.main(["x", "config-diff", f"{t}/b.txt", f"{t}/n.txt"]) == 0
        n = open(f"{t}/n.txt").read()
        open(f"{t}/extra.txt", "w").write(n.replace("\t**.perD2D = 0\n", "\t**.perD2D = 0\n\t**.harqReduction = 0.5\n"))
        open(f"{t}/missing.txt", "w").write(n.replace("\tseed-4-mt = 4000\n", ""))
        open(f"{t}/trunc.txt", "w").write(n[: len(n) // 2])
        assert G.main(["x", "config-diff", f"{t}/b.txt", f"{t}/extra.txt"]) == 1
        assert G.main(["x", "config-diff", f"{t}/b.txt", f"{t}/missing.txt"]) == 1
        assert G.main(["x", "config-diff", f"{t}/b.txt", f"{t}/trunc.txt"]) == 2
        assert G.main(["x", "config-diff", f"{t}/b.txt", f"{t}/absent.txt"]) == 2
    finally:
        shutil.rmtree(t)


@test("T-g-baseline-size: the baseline raw size is the manifest's sum and must equal the files on disk; a changed size, a "
      "missing or an unlisted file, or a missing manifest fail")
def _():
    t = tempfile.mkdtemp()
    try:
        os.makedirs(f"{t}/d")
        open(f"{t}/d/a", "w").write("x" * 100)
        open(f"{t}/log.gz", "w").write("y" * 50)
        LIB.manifest(f"{t}/m.sha256", [f"{t}/d", f"{t}/log.gz"])
        ok, msg, tot = G.baseline_size(f"{t}/m.sha256", [f"{t}/d", f"{t}/log.gz"])
        assert ok and tot == 150, msg
        open(f"{t}/d/a", "a").write("z")
        assert not G.baseline_size(f"{t}/m.sha256", [f"{t}/d", f"{t}/log.gz"])[0]
        open(f"{t}/d/a", "w").write("x" * 100)
        open(f"{t}/d/b", "w").write("new")
        assert not G.baseline_size(f"{t}/m.sha256", [f"{t}/d", f"{t}/log.gz"])[0]
        os.remove(f"{t}/d/b")
        os.remove(f"{t}/log.gz")
        assert not G.baseline_size(f"{t}/m.sha256", [f"{t}/d", f"{t}/log.gz"])[0]
        assert not G.baseline_size(f"{t}/none.sha256", [f"{t}/d"])[0]
    finally:
        shutil.rmtree(t)


@test("T-g-pins: the reviewed configuration files match their pins in this tree; any byte change fails")
def _():
    assert G.pins(M2)[0], G.pins(M2)[1]
    t = tempfile.mkdtemp()
    try:
        for f in G.PINS:
            shutil.copy2(os.path.join(M2, f), t)
        open(os.path.join(t, "m2s72a2v.ini"), "a").write("\n")
        assert not G.pins(t)[0]
    finally:
        shutil.rmtree(t)


@test("T-g-nc-baseline: NC-V-baseline holds only with rc 4 AND V-0 FAIL AND V-1 FAIL in the evaluator's record")
def _():
    t = tempfile.mkdtemp()
    try:
        good = "  FAIL            | V-0 | x\n  FAIL            | V-1 | y\n"
        open(f"{t}/a.txt", "w").write(good)
        assert G.nc_baseline(4, f"{t}/a.txt")[0]
        assert not G.nc_baseline(3, f"{t}/a.txt")[0]
        open(f"{t}/b.txt", "w").write(good.replace("FAIL            | V-0", "PASS            | V-0"))
        assert not G.nc_baseline(4, f"{t}/b.txt")[0]
        assert not G.nc_baseline(4, f"{t}/none.txt")[0]
    finally:
        shutil.rmtree(t)


# -------------------------------------------------------------------------------- wrapper: G-0 failures ---------
@test("T-w-gate-pass: gate mode with every check holding passes (rc 0), runs NO simulation, records every G-0 row, "
      "and NC-V-baseline is rc 4 on the no-NACK baseline")
def _():
    def f(e):
        p = e.run("gate")
        assert p.returncode == 0, (p.stdout[-3000:], p.stderr[-2000:])
        assert e.sims() == 0
        gdir = [d for d in os.listdir(e.R) if d.startswith("a2-nack-gate-")][0]
        g = open(os.path.join(e.R, gdir, "records", "gate.txt")).read()
        for row in ("G0-env", "G0-commit", "G0-frozen", "G0-evidence", "G0-stack", "G0-source", "G0-config", "G0-baseline",
                    "G0-ncbase", "G0-space"):
            assert f"{row}: PASS" in g, (row, g)
        assert "rc 4, V-0 FAIL, V-1 FAIL" in g and "the declared set exactly" in g, g
        assert not os.path.exists(e.out())
    with_env(f)


@test("T-w-commit: a commit other than the authorised one, a non-full id, or a dirty worktree stop at G0-commit (rc 10)")
def _():
    def f(e):
        gate_failure(e, e.run(commit="0" * 40), "G0-commit")
    with_env(f)

    def g(e):
        gate_failure(e, e.run(commit=e.commit[:12]), "G0-commit")
    with_env(g)

    def h(e):
        open(os.path.join(e.repo, "simulations/m2/m2s72a2v.ini"), "a").write("# local edit\n")
        gate_failure(e, e.run(), "G0-commit")
    with_env(h)


@test("T-w-config-altered: a COMMITTED change of the A2-V1 configuration stops at G0-frozen (pin), before any runconfig")
def _():
    with_env(lambda e: gate_failure(e, e.run(), "G0-frozen"), change_ini=True)


@test("T-w-evidence: a preserved evidence file that no longer verifies, or a missing one, stops at G0-evidence")
def _():
    def f(e):
        open(os.path.join(e.R, "a2-v3", "record.txt"), "a").write("tampered\n")
        gate_failure(e, e.run(), "G0-evidence")
    with_env(f)

    def g(e):
        os.remove(os.path.join(e.R, "a2-p0-evidence.sha256"))
        gate_failure(e, e.run(), "G0-evidence")
    with_env(g)


@test("T-w-stack-source: a Simu5G binary other than the baseline's stops at G0-stack; a Simu5G tree without A-2's texts "
      "stops at G0-source")
def _():
    def f(e):
        e.write_env_record("0" * 64)
        sh(f"cd {e.R} && find s5-n2-1 -type f | LC_ALL=C sort | xargs sha256sum > s5-n2-1-evidence.sha256")   # evidence re-made
        gate_failure(e, e.run(), "G0-stack")
    with_env(f)

    def g(e):
        os.remove(os.path.join(e.simu5g, "src", "simu5g"))
        os.makedirs(os.path.join(e.simu5g, "src", "simu5g"))
        gate_failure(e, e.run(), "G0-source")
    with_env(g)


@test("T-w-suites: a failing test suite stops at G0-suites")
def _():
    with_env(lambda e: gate_failure(e, e.run(A2V1_TEST_SKIP_SUITES="", A2V1_TEST_SUITE_CMD="false"), "G0-suites"))


@test("T-w-baseline: a baseline file whose size no longer matches its manifest stops at G0-baseline; a baseline that is "
      "not the no-NACK Tr38901 run (Ideal records) fails NC-V-baseline (G0-ncbase)")
def _():
    def f(e):
        sca = os.path.join(e.R, "s5-n2-1/m2/M2-S7.2a-s5smoke-n2/runs", BASE, BASE, "0.sca")
        open(sca, "a").write("scalar x y 1\n")
        sh(f"cd {e.R} && find s5-n2-1 -type f | LC_ALL=C sort | xargs sha256sum > s5-n2-1-evidence.sha256")   # evidence re-made
        gate_failure(e, e.run(), "G0-baseline")
    with_env(f)

    def g(e):
        runs = os.path.join(e.R, "s5-n2-1/m2/M2-S7.2a-s5smoke-n2/runs")
        sca = os.path.join(runs, BASE, BASE, "0.sca")
        txt = open(sca).read().replace("Tr38901ChannelModel", "IdealChannelModel")
        txt += "".join(f"par M2S72Bridge.ue[{k}].cellularNic.nrChannelModel[0] {n} {v}\n" for k, n, v in
                       ((1, "perDl", 0.1), (1, "harqReduction", 1), (0, "perDl", 0), (1, "perUl", 0), (0, "perUl", 0)))
        txt += ('par M2S72Bridge.gnb1.cellularNic.channelModel[0] typename "\\"simu5g.stack.phy.channelmodel.IdealChannelModel\\""\n'
                "par M2S72Bridge.gnb1.cellularNic.channelModel[0] perUl 0\npar M2S72Bridge.gnb1.cellularNic.channelModel[0] perDl 0\n")
        open(sca, "w").write(txt)
        rec = os.path.join(e.R, "s5-n2-1/m2/M2-S7.2a-s5smoke-n2/records")
        LIB.manifest(os.path.join(rec, f"{BASE}.manifest.sha256"), [os.path.join(runs, BASE), os.path.join(runs, f"run-{BASE}.log.gz")])
        sh(f"cd {e.R} && find s5-n2-1 -type f | LC_ALL=C sort | xargs sha256sum > s5-n2-1-evidence.sha256")
        gate_failure(e, e.run(), "G0-ncbase")
    with_env(g)


@test("T-w-space: free space below max(10 GiB, storage limit + 4 GiB) stops at G0-space")
def _():
    with_env(lambda e: gate_failure(e, e.run(A2V1_TEST_FREE_BYTES=str(GIB)), "G0-space"))


@test("T-w-env: a missing variable or results root writes nothing and stops (rc 10); an existing output root (an earlier "
      "attempt) is never reused or written: rc 10, its content unchanged")
def _():
    def f(e):
        p = e.run(A2V1_COMMIT="")
        assert p.returncode == 10 and "G0-env" in p.stderr and not os.path.exists(e.out()), p.stderr
        os.makedirs(e.out())
        open(os.path.join(e.out(), "earlier.txt"), "w").write("earlier attempt\n")
        p = e.run()
        assert p.returncode == 10 and "G0-fresh" in p.stderr, p.stderr
        assert os.listdir(e.out()) == ["earlier.txt"] and e.sims() == 0
    with_env(f)


@test("T-w-build: a failing build is a hard stop (rc 11): no simulation, build log and records kept")
def _():
    def f(e):
        p = e.run(A2V1_TEST_BUILD_CMD="echo compile error; false")
        assert p.returncode == 11 and e.sims() == 0, (p.returncode, p.stdout[-1500:])
        assert "compile error" in e.rec("build.log") and "BUILD FAILED" in e.rec("wrapper-verdict.txt")
    with_env(f)


# ---------------------------------------------------------------------------- wrapper: after the start ---------
def lifecycle_failure(e, p, row):
    assert p.returncode == 20, (p.returncode, p.stdout[-3000:], p.stderr[-1500:])
    assert e.sims() == 1, f"{e.sims()} simulations (exactly one allowed)"
    lc = e.rec("lifecycle.txt")
    line = next((x for x in lc.splitlines() if x.startswith(row + " ")), "")
    assert "): FAIL" in line or ": FAIL (" in line, lc
    assert "LIFECYCLE FAILURE" in e.rec("wrapper-verdict.txt")
    runs = os.path.join(e.out(), "runs")
    assert os.path.exists(os.path.join(runs, f"run-{CFG}.log.gz")), "the run log was not kept"
    assert not (os.stat(os.path.join(runs, f"run-{CFG}.log.gz")).st_mode & 0o222), "raw outputs not made read-only"
    assert e.rec(f"{CFG}.manifest.sha256"), "no manifest"
    assert not os.listdir(os.path.join(e.out(), "eval")), "evaluation ran after a lifecycle failure"
    assert os.path.exists(os.path.join(e.R, "a2-nack-1-evidence.sha256"))


@test("T-w-simfail: a failed simulation (rc 1, error line) -> rc 20, L-1 FAIL, ONE simulation, log / manifest kept "
      "read-only, no evaluation, no retry")
def _():
    def f(e):
        p = e.run(stub="fail")
        lifecycle_failure(e, p, "L-1")
        assert "stub simulation failure" in gzip.open(os.path.join(e.out(), "runs", f"run-{CFG}.log.gz"), "rt").read()
    with_env(f)


@test("T-w-timeout: the wall-time limit ends the run (rc 124, TIMEOUT) -> rc 20, L-1 / L-2 FAIL, one simulation")
def _():
    def f(e):
        p = e.run(stub="hang", A2V1_TEST_WALL_S="2")
        lifecycle_failure(e, p, "L-2")
        assert e.elapsed < 50
    with_env(f)


@test("T-w-storage: raw output beyond 2 x the baseline is detected while the run is going, the simulation is terminated "
      "(STORAGE-LIMIT) -> rc 20, L-3 FAIL, one simulation, every byte written kept")
def _():
    def f(e):
        p = e.run(stub="big")
        lifecycle_failure(e, p, "L-3")
        assert e.rec("storage-limit.txt") and e.elapsed < 50, (e.elapsed, e.rec("storage-limit.txt"))
        assert os.path.getsize(os.path.join(e.out(), "runs", CFG, "big.bin")) > 0
    with_env(f)


@test("T-w-storage-monitor (regression, r1 review): the storage measurement FAILS during the run (after three good "
      "readings) or returns a non-number -> the single simulation is terminated at once, outcome STORAGE-MONITOR-ERROR, "
      "rc 20, L-1 and L-3 FAIL, log / raw files / manifest / diagnostics kept read-only, no evaluation, no retry")
def _():
    for name, cmd in (("fails mid-run", 'n=$(cat "$A2V1_T_CNT" 2>/dev/null || echo 0); echo $((n + 1)) > "$A2V1_T_CNT"; '
                                        '[ "$n" -lt 3 ] && echo 0 || { echo "du: cannot read" >&2; exit 7; }'),
                      ("non-numeric", "echo 12abc")):
        def f(e):
            cnt = os.path.join(e.t, "size-calls.txt")
            p = e.run(stub="hang", A2V1_TEST_SIZE_CMD=cmd, A2V1_T_CNT=cnt)
            lifecycle_failure(e, p, "L-3")
            lc, steps = e.rec("lifecycle.txt"), e.rec("steps.txt")
            assert "L-1 " in lc and "): FAIL" in next(x for x in lc.splitlines() if x.startswith("L-1 ")), lc
            assert "outcome STORAGE-MONITOR-ERROR" in steps and "STORAGE-MONITOR-ERROR:" in lc, (name, steps[-1500:])
            assert e.elapsed < 50, f"{name}: the simulation was not terminated ({e.elapsed:.0f} s; the stub sleeps 60 s)"
            mon = e.rec("storage-monitor.txt")
            assert ("rc 7" in mon and "du: cannot read" in mon) if name == "fails mid-run" else "not numeric: '12abc'" in mon, mon
            if name == "fails mid-run":
                assert int(open(cnt).read()) >= 4, "the failure did not happen during the run"
            assert not e.rec("storage-limit.txt")
        with_env(f)


@test("T-w-complete: a completed stub run passes L-1..L-4, is evaluated read-only (records of a2, a2-controls, a2v1), "
      "and the preserved evidence is checked after; exactly one simulation; rc 0 or 21 (a stub has no scientific output)")
def _():
    def f(e):
        p = e.run(stub="ok")
        assert p.returncode in (0, 21), (p.returncode, p.stdout[-3000:])
        assert e.sims() == 1
        assert e.rec("lifecycle.txt").count(": PASS") == 4, e.rec("lifecycle.txt")
        for x in ("a2.console.txt", "a2-controls.console.txt", "a2v1.console.txt"):
            assert os.path.exists(os.path.join(e.out(), "eval", x)), x
        assert "LIFECYCLE COMPLETE" in e.rec("wrapper-verdict.txt")
        assert "TEST HOOKS ACTIVE" in e.rec("env.txt") and "fingerprint: not requested" in e.rec("env.txt")
        assert e.run().returncode == 10 and e.sims() == 1          # a second invocation never runs again
    with_env(f)


@test("T-w-integrity-after: preserved evidence changed during the run -> rc 30 after the evaluation; the change is recorded")
def _():
    def f(e):
        p = e.run(stub="tamper")
        assert p.returncode == 30, (p.returncode, p.stdout[-2000:])
        assert "PRESERVED EVIDENCE CHANGED" in e.rec("wrapper-verdict.txt") and e.sims() == 1
    with_env(f)


@test("T-w-config-unchanged: this increment does not alter the experiment: m2s72a2v.ini, the evaluator, its tests and A-2 "
      "are byte-identical to the reviewed commit 39a6434; the simulation command is the runner's without the fingerprint")
def _():
    r = subprocess.run(["git", "-C", REPO, "diff", "--quiet", "39a64348701fe14bb838964a113a278ecaf747e9", "--",
                        "simulations/m2/m2s72a2v.ini", "simulations/m2/check/check_m2s72_a2v1.py",
                        "simulations/m2/check/test_m2s72_a2v1.py", "simulations/m2/check/m2s72_a2.py",
                        "simulations/m2/check/check_m2s72_a2.py", "simulations/m2/m2s72s5.ini", "simulations/m2/m2s72.ini"])
    assert r.returncode == 0, "experiment files differ from 39a6434"
    w = open(os.path.join(M2, "m2s72a2v1.sh")).read()
    assert '-f m2s72a2v.ini -c "$CFG" --repeat=1 -r 0 --result-dir="$RUNS/$CFG" --cmdenv-express-mode=false )' in w
    assert "--fingerprint" not in w.replace("fingerprint: not requested", "")


def main():
    if not os.path.exists(os.path.join(REAL_OMNETPP, "setenv")):
        print(f"FAIL  OMNeT++ not found at {REAL_OMNETPP} (needed for the real runconfig): set OMNETPP_ROOT")
        return 1
    fails = 0
    only = sys.argv[1:]
    for name, f in TESTS:
        if only and not any(name.startswith(o) for o in only):
            continue
        try:
            f()
            print(f"PASS  {name}")
        except Exception as ex:
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {name}: {type(ex).__name__}: {str(ex)[:800]}")
    n = sum(1 for name, _ in TESTS if not only or any(name.startswith(o) for o in only))
    print(f"A2-V1 wrapper tests: {n - fails} / {n} PASS")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
