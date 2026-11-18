#!/usr/bin/env python3
"""Offline validation of the E3a tier-2 implementation (ci/tier2). No Nix, no opp_env, no network, no OMNeT++, no
simulation: the simulator is a stand-in script; simulation outputs are SYNTHETIC (tests/synth.py) and are never evidence.
The reviewed U1 oracle (simulations/m2/check/check_m2s4.py) is exercised unchanged through the adapter.
usage: python3 -I ci/tier2/tests/test_tier2.py"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
T2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(T2))
T1 = os.path.join(REPO, "ci", "tier1")
PYD, STEPS, SESSION = (os.path.join(T2, d) for d in ("py", "steps", "session"))
CHECK = os.path.join(REPO, "simulations", "m2", "check")
WF = os.path.join(REPO, ".github", "workflows", "e3a-functional-smoke.yml")
sys.path.insert(0, HERE)
import synth  # noqa: E402

WORK = tempfile.mkdtemp(prefix="t2-selftest-")
os.chdir(WORK)
results = []
TEST_VARS = ("TIER1_TEST_", "E2B3_TEST_", "A2V1_TEST_", "A2V1_STUB_")


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:700]}]" if detail and not cond else ""), flush=True)


def clean_env(**kw):
    e = {k: v for k, v in os.environ.items() if not k.startswith(TEST_VARS) and k not in ("A2V1_RESULTS_ROOT", "A2V1_COMMIT")}
    e.update(kw)
    return e


def pins(path):
    d = {}
    for l in open(path):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1)
            d[k] = v[1:-1] if v[:1] == '"' and v[-1:] == '"' else v
    return d


P1, P2 = pins(os.path.join(T1, "pins.env")), pins(os.path.join(T2, "pins-tier2.env"))
PINS = {**P1, **P2}


def run(cmd, env, timeout=120, **kw):
    return subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout, **kw)


def git(repo, *a, **kw):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, **kw)


# ======================================================================= T0 static checks
for d, _, fs in os.walk(T2):
    for f in fs:
        p = os.path.join(d, f)
        if f.endswith(".sh") or f.endswith(".env"):
            r = subprocess.run(["bash", "-n", p], capture_output=True, text=True)
            check(f"T0 bash -n {os.path.relpath(p, T2)}", r.returncode == 0, r.stderr)
        elif f.endswith(".py"):
            r = subprocess.run([sys.executable, "-I", "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())", p], capture_output=True, text=True)
            check(f"T0 python parses {os.path.relpath(p, T2)}", r.returncode == 0, r.stderr)
WFT = open(WF).read()
check("T0 workflow: push to wp-e3/e3a-m2s4u-smoke only; no pull_request / dispatch / schedule",
      "on:\n  push:\n    branches: [wp-e3/e3a-m2s4u-smoke]\n" in WFT and "pull_request" not in WFT and "workflow_dispatch" not in WFT
      and "schedule" not in WFT)
check("T0 workflow: read-only token, no secrets, no caches, standard runner, 120-minute job",
      "permissions:\n  contents: read\n" in WFT and "secrets." not in WFT and "actions/cache" not in WFT
      and "runs-on: ubuntu-22.04" in WFT and "timeout-minutes: 120" in WFT and "persist-credentials: false" in WFT)
check("T0 workflow: actions pinned by sha", set(re.findall(r"uses: (\S+)", WFT)) == {
      "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"})
ids = re.findall(r"\n        id: (\w+)", WFT)
check("T0 workflow: step order (identity, tier-1 prerequisites, sim, seal, oracle, gates, evaluations, publications, verdict, uploads)",
      ids == ["checkout", "t2identity", "setup", "bootstrap", "verify", "runtime", "b_omnetpp", "b_inet", "b_simu5g", "b_nasctime",
              "validate", "srcchanges", "sim", "seal", "oracle", "lockend", "t2lockend", "measure", "evaluate", "t2evaluate",
              "publish", "t2publish", "rawpub", "final", "upload_diag", "upload_raw", "conclude"], ids)
sim_block = WFT[WFT.index("id: sim\n"):WFT.index("id: seal\n")]
check("T0 workflow: the simulation step runs only if every earlier step succeeded (no 'if')", "if:" not in sim_block)
check("T0 workflow: tier-1 steps are called unchanged from ci/tier1/steps", all(
      f"bash ci/tier1/steps/{s}" in WFT for s in ("setup.sh", "bootstrap.sh", "verify.sh", "runtime.sh", "build.sh omnetpp",
                                                 "build.sh inet", "build.sh simu5g", "build.sh nasctime", "validate.sh",
                                                 "srcchanges.sh", "lockend.sh", "measure.sh", "evaluate.sh", "publish.sh"))
      and "wrapper.sh" not in WFT and "steps/final.sh" not in WFT.replace("ci/tier2/steps/final.sh", ""))
check("T0 workflow: event values never interpolated into run scripts", not re.search(r"\n        run: [^\n]*\$\{\{", WFT))
check("T0 workflow: both artifacts retained 7 days", WFT.count("retention-days: 7") == 2)
RS = open(os.path.join(SESSION, "run-sim.sh")).read()
check("T0 run-sim: the reviewed argument vector is fixed in the script (m2s4.sh run(), M2S4U, --repeat=10 -r 0)",
      '-l "$REPO/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"' in RS
      and '-n "$REPO/simulations:$REPO/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes' in RS
      and "-u Cmdenv -f omnetpp.ini -c M2S4U --repeat=10 -r 0)" in RS
      and 'FULL=("$OPP" "${ARGV[@]}" --result-dir="$RESDIR" --cmdenv-express-mode=true)' in RS)
M2S4 = subprocess.run(["git", "-C", REPO, "show", "290babba3d12942344a2153f9ea5ea54287df366:simulations/m2/m2s4.sh"],
                      capture_output=True, text=True).stdout
check("T0 the argument vector matches the reviewed simulations/m2/m2s4.sh run() at the baseline",
      '-l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"' in M2S4
      and '-n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes' in M2S4
      and '-u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$OUT/runs/$1"' in M2S4
      and "--cmdenv-express-mode=true" in M2S4, "baseline m2s4.sh not readable" if not M2S4 else "")
ref_file = subprocess.run(["git", "-C", REPO, "show", "290babba3d12942344a2153f9ea5ea54287df366:simulations/m2/results/M2-S4/raw-outputs.sha256"],
                          capture_output=True, text=True).stdout
check("T0 historical reference hashes equal the committed M2-S4 raw-outputs.sha256", all(
      PINS[k] in ref_file for k in ("REF_CSV_TTA", "REF_CSV_TTB", "REF_PCAP_TTA", "REF_PCAP_TTB")))
check("T0 resource pins as approved (600 s, 500 000 000 B watchdog, 200 000 000 B acceptance, decimal MB)",
      PINS["SIM_WALL_CAP_S"] == "600" and PINS["SIM_WATCHDOG_LIMIT_B"] == "500000000" and PINS["SIM_ACCEPT_LIMIT_B"] == "200000000")
AD = open(os.path.join(PYD, "u1_oracle.py")).read()
check("T0 adapter never calls check_m2s4.main() (replaced by a trap) and calls only eval_unit('M2S4U', L_REF)",
      "C.main(" not in AD and "C.main = _trap" in AD and 'C.eval_unit("M2S4U", C.L_REF)' in AD and AD.count("eval_unit(") == 2)
base = "290babba3d12942344a2153f9ea5ea54287df366"
r = subprocess.run(["git", "-C", REPO, "diff", "--name-status", base, "--", "ci/tier1", ".github/workflows/tier0-python.yml",
                    ".github/workflows/tier1-full-stack.yml", "simulations", "src"], capture_output=True, text=True)
check("T0 tier-0, tier-1, simulations and sources unchanged against the baseline (working tree)", r.returncode == 0 and r.stdout == "", r.stdout[:300])

# ======================================================================= T1 production refuses test overrides (tier-1 C5 reused)
for var in ("TIER1_TEST_FS_ROOT", "A2V1_STUB_MODE", "A2V1_RESULTS_ROOT"):
    t = tempfile.mkdtemp(prefix="t2c5-")
    r = run(["bash", os.path.join(STEPS, "identity.sh")], clean_env(RUNNER_TEMP=t, **{var: "/x"}))
    check(f"T1 tier-2 step refuses {var} (exit 3, nothing created)", r.returncode == 3 and not os.path.exists(f"{t}/e3a"), r.stdout)
    shutil.rmtree(t)
for s in sorted(os.listdir(STEPS)):
    if s.endswith(".sh") and s != "conclude.sh":
        check(f"T1 step {s} sources lib/t2common.sh", '. "$(dirname "$0")/../lib/t2common.sh"' in open(os.path.join(STEPS, s)).read())

# ======================================================================= T2 trigger and commit identity
t = tempfile.mkdtemp(prefix="t2id-")
git(t, "init", "-q", "-b", "main")
open(f"{t}/a.txt", "w").write("a\n")
os.makedirs(f"{t}/ci/tier1")
open(f"{t}/ci/tier1/x", "w").write("x\n")
git(t, "add", "-A")
git(t, "commit", "-qm", "base")
BASE = git(t, "rev-parse", "HEAD").stdout.strip()


def ident_commit(changes):
    git(t, "checkout", "-q", "-B", "e", BASE)
    for op, path in changes:
        full = os.path.join(t, path)
        if op == "add":
            os.makedirs(os.path.dirname(full), exist_ok=True)
            open(full, "w").write("n\n")
        elif op == "mod":
            open(full, "a").write("m\n")
        elif op == "del":
            os.remove(full)
    git(t, "add", "-A")
    git(t, "commit", "-qm", "c")
    return git(t, "rev-parse", "HEAD").stdout.strip()


GOOD = [("add", ".github/workflows/e3a-functional-smoke.yml"), ("add", "ci/tier2/steps/x.sh")]
IDENV = dict(E3A_BRANCH="wp-e3/e3a-m2s4u-smoke", E3A_ALLOWED_PATHS=PINS["E3A_ALLOWED_PATHS"], GITHUB_EVENT_NAME="push",
             GITHUB_REF="refs/heads/wp-e3/e3a-m2s4u-smoke", GITHUB_RUN_ATTEMPT="1")
for label, changes, over, want in (("authorised push", GOOD, {}, 0),
                                   ("pull_request event", GOOD, {"GITHUB_EVENT_NAME": "pull_request"}, 1),
                                   ("other branch", GOOD, {"GITHUB_REF": "refs/heads/main"}, 1),
                                   ("second attempt", GOOD, {"GITHUB_RUN_ATTEMPT": "2"}, 1),
                                   ("existing file modified", GOOD + [("mod", "ci/tier1/x")], {}, 1),
                                   ("file deleted", GOOD + [("del", "a.txt")], {}, 1),
                                   ("new file outside the scope", GOOD + [("add", "simulations/m2/new.ini")], {}, 1),
                                   ("workflow missing", [("add", "ci/tier2/steps/x.sh")], {}, 1)):
    sha = ident_commit(changes)
    env = clean_env(**{**IDENV, "E3A_BASELINE": BASE, "GITHUB_SHA": sha, **over})
    r = run([sys.executable, "-I", os.path.join(PYD, "identity.py"), t, f"{t}/../id-{os.getpid()}.txt"], env)
    check(f"T2 identity [{label}] -> {'PASS' if want == 0 else 'FAIL'}", r.returncode == want, r.stdout[-400:])
sha = ident_commit(GOOD)
r = run([sys.executable, "-I", os.path.join(PYD, "identity.py"), t, f"{t}/../id.txt"], clean_env(**IDENV, E3A_BASELINE=BASE, GITHUB_SHA="0" * 40))
check("T2 identity: checked-out commit differs from GITHUB_SHA -> FAIL", r.returncode == 1)
r = run([sys.executable, "-I", os.path.join(PYD, "identity.py"), t, f"{t}/../id.txt"], clean_env(**IDENV, E3A_BASELINE="f" * 40, GITHUB_SHA=sha))
check("T2 identity: parent is not the authorised baseline -> FAIL", r.returncode == 1)
shutil.rmtree(t)


# ======================================================================= T3 the in-session runner (stand-in simulator)
FAKE_OPP = r'''#!/bin/bash
# stand-in simulator for the offline tests (never a simulation)
echo "$*" >> "$FAKE_CALLS"
if [[ " $* " == *" -q runconfig"* ]]; then
  printf 'Config: M2S4U\nRun 0: $repetition=0\n\tnetwork = nasctime.simulations.m2.M2S4LinkTest\n\tsim-time-limit = 3s\n\tseed-set = 0\nEnd.\n'
  exit 0
fi
rd=""; for a in "$@"; do case $a in --result-dir=*) rd=${a#--result-dir=} ;; esac; done
mkdir -p "$rd"
echo "Preparing for running configuration M2S4U, run #0..."
case "${FAKE_MODE:-ok}" in
  ok) echo data > "$rd/0.sca"; echo "<!> Simulation time limit reached -- at t=3s, event #10"; echo; echo "Calling finish() at end of Run #0..."; echo; echo "End."; exit 0 ;;
  big) head -c 50000 /dev/zero > "$rd/big.bin"; sleep 60; exit 0 ;;
  slow) sleep 60; exit 0 ;;
  child) (sleep 307 & sleep 307) & sleep 60; exit 0 ;;
  stop) sleep 2; echo "disk guard: synthetic" > "$FAKE_EV/STOP"; sleep 60; exit 0 ;;
  fail) echo "<!> Error: no such module type 'Foo' -- in module (M2S4LinkTest) (NED)"; exit 1 ;;
esac
'''


def sim_env(mode="ok", readelf_runpath=None, du_bad=False):
    t = tempfile.mkdtemp(prefix="t2rs-")
    ws, repo = f"{t}/ws", f"{t}/repo"
    om, inet, s5 = f"{ws}/omnetpp-6.5.0", f"{ws}/inet-4.7.0", f"{ws}/simu5g-1.8.1"
    for d in (f"{om}/bin", f"{om}/lib", f"{inet}/src", f"{s5}/src", f"{repo}/simulations/m2", f"{repo}/src/nasctime/m2", f"{t}/fb", f"{t}/ev"):
        os.makedirs(d)
    open(f"{om}/bin/opp_run", "w").write(FAKE_OPP)
    os.chmod(f"{om}/bin/opp_run", 0o755)
    for f in (f"{inet}/src/libINET.so", f"{s5}/src/libsimu5g.so", f"{repo}/src/nasctime/m2/libnasctime_m2.so", f"{om}/lib/liboppsim.so"):
        open(f, "w").write("stand-in\n")
    open(f"{repo}/simulations/m2/omnetpp.ini", "w").write("[Config M2S4U]\n")
    fb = f"{t}/fb"
    open(f"{fb}/ld.so", "w").write('#!/bin/sh\nprintf "\\tlibc.so.6 => /nix/store/x-glibc/lib/libc.so.6 (0x0)\\n"\n')
    open(f"{fb}/patchelf", "w").write(f"#!/bin/sh\necho {fb}/ld.so\n")
    shims = ["ld.so", "patchelf"]
    if readelf_runpath:
        open(f"{fb}/readelf", "w").write(f'#!/bin/sh\necho " 0x000000000000001d (RUNPATH)            Library runpath: [{readelf_runpath}]"\n')
        shims.append("readelf")
    if du_bad:
        open(f"{fb}/du", "w").write("#!/bin/sh\necho 'n/a'\n")
        shims.append("du")
    for x in shims:
        os.chmod(f"{fb}/{x}", 0o755)
    env = clean_env(PATH=f"{om}/bin:{fb}:" + os.environ["PATH"], OMNETPP_ROOT=om, INET_ROOT=inet, SIMU5G_ROOT=s5,
                    FAKE_MODE=mode, FAKE_CALLS=f"{t}/calls.txt", FAKE_EV=f"{t}/ev")
    return t, ws, repo, env


def rs(t, ws, repo, env, mode, cap="600", limit="500000000", raw=None, timeout=120):
    raw = raw or f"{t}/raw"
    os.makedirs(raw, exist_ok=True)
    return run(["bash", os.path.join(SESSION, "run-sim.sh"), mode, repo, ws, raw, f"{t}/rec", f"{t}/ev", cap, limit, "1", "5"], env, timeout=timeout)


def nulf(p):
    return open(p, "rb").read().split(b"\0")[:-1]


t, ws, repo, env = sim_env()
r = rs(t, ws, repo, env, "preflight")
expected = [f"{ws}/omnetpp-6.5.0/bin/opp_run", "-l", f"{repo}/src/nasctime/m2/nasctime_m2", "-l", f"{ws}/simu5g-1.8.1/src/simu5g",
            "-n", f"{repo}/simulations:{repo}/src:{ws}/simu5g-1.8.1/src:{ws}/inet-4.7.0/src", "-x", "nasctime.nodes",
            "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", "M2S4U", "--repeat=10", "-r", "0"]
check("T3 pre-flight: exit 0, effective configuration written, exact argument vector, hazards none",
      r.returncode == 0 and "Run 0: $repetition=0" in open(f"{t}/raw/effective-config.txt").read()
      and [x.decode() for x in nulf(f"{t}/rec/argv-preflight.nul")] == expected + ["-q", "runconfig"]
      and "hazards: none" in open(f"{t}/rec/hazards-preflight.txt").read(), r.stdout + r.stderr)
r = rs(t, ws, repo, env, "sim")
argv_sim = [x.decode() for x in nulf(f"{t}/rec/argv-sim.nul")]
ctl = open(f"{t}/rec/sim-control-sim.txt").read()
check("T3 simulation: exactly the reviewed command, one start, exit 0, watchdog not triggered",
      r.returncode == 0 and argv_sim == expected + [f"--result-dir={t}/raw/runs/M2S4U", "--cmdenv-express-mode=true"]
      and ctl.count("simulation_started:") == 1 and "simulation_exit: 0" in ctl and "watchdog_terminated: no" in ctl
      and open(f"{t}/calls.txt").read().count("--result-dir") == 1, r.stdout + r.stderr + ctl)
r = rs(t, ws, repo, env, "sim")
check("T3 duplicate invocation refused (exit 3) and the simulator is not started again",
      r.returncode == 3 and "duplicate" in r.stderr and open(f"{t}/calls.txt").read().count("--result-dir") == 1, r.stderr)
shutil.rmtree(f"{t}/raw/runs")
r = rs(t, ws, repo, env, "sim")
check("T3 a second start is refused even after the output directory is removed (start marker)",
      r.returncode == 3 and "already" in r.stderr and open(f"{t}/calls.txt").read().count("--result-dir") == 1, r.stderr)
shutil.rmtree(t)
t, ws, repo, env = sim_env()
r = rs(t, ws, repo, env, "sim")
check("T3 simulation without a successful pre-flight refused", r.returncode == 3 and not os.path.exists(f"{t}/calls.txt"), r.stderr)
r = run(["bash", os.path.join(SESSION, "run-sim.sh"), "sim", repo], env)
check("T3 wrong argument count refused", r.returncode == 3)
r = rs(t, ws, repo, env, "simulate")
check("T3 unknown mode refused", r.returncode == 3)
r = rs(t, ws, repo, dict(env, OMNETPP_ROOT="/elsewhere"), "preflight")
check("T3 session stack not the tier-1 workspace -> refused", r.returncode == 3 and "OMNETPP_ROOT" in r.stderr)
r = rs(t, ws, repo, env, "preflight", raw=f"{repo}/out")
check("T3 output directory inside the repository -> refused", r.returncode == 3 and "inside the repository" in r.stderr)
r = rs(t, ws, repo, env, "preflight", cap="abc")
check("T3 non-numeric limit -> refused", r.returncode == 3)
shutil.rmtree(t)
t, ws, repo, env = sim_env(readelf_runpath=".")
open(f"{repo}/simulations/m2/libplanted.so", "w").write("x")
r = rs(t, ws, repo, env, "preflight")
check("T3 shared library reachable through relative RUNPATH '.' in the working directory -> refused before any start",
      r.returncode == 3 and "hazard" in open(f"{t}/rec/hazards-preflight.txt").read() and not os.path.exists(f"{t}/calls.txt"), r.stderr)
shutil.rmtree(t)


def watchdog_case(mode, **kw):
    t, ws, repo, env = sim_env(mode, du_bad=kw.pop("du_bad", False))
    assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
    t0 = time.time()
    r = rs(t, ws, repo, env, "sim", **kw)
    return t, r, open(f"{t}/rec/sim-control-sim.txt").read(), time.time() - t0


def no_proc(tag):
    ps = subprocess.run(["ps", "-eo", "stat=,args="], capture_output=True, text=True).stdout.splitlines()
    return not [l for l in ps if tag in l and not l.strip().startswith("Z") and "ps -eo" not in l]


for mode, kw, want in (("big", {"limit": "20000"}, "exceeds the watchdog limit"),
                       ("slow", {"cap": "3"}, "exceeds the cap"),
                       ("slow", {"du_bad": True}, "measurement failed"),
                       ("stop", {}, "STOP declared"),
                       ("child", {"cap": "3"}, "exceeds the cap")):
    t, r, ctl, el = watchdog_case(mode, **kw)
    extra = no_proc("sleep 307") if mode == "child" else True
    check(f"T3 watchdog [{mode}{' ' + str(kw) if kw else ''}] -> terminated ({want}), exit 4, evidence kept, children gone",
          r.returncode == 4 and want in ctl and "watchdog_terminated: no" not in ctl and el < 40 and extra
          and os.path.exists(f"{t}/raw/run-M2S4U.log") and os.path.exists(f"{t}/rec/watchdog.tsv"), r.stderr + ctl)
    shutil.rmtree(t)

# ======================================================================= T4 U1 oracle adapter (reviewed oracle, synthetic evidence)


def u1(variant=None, n=30, min_ex="25"):
    t = tempfile.mkdtemp(prefix="t2u1-")
    synth.make(f"{t}/raw", n=n, variant=variant)
    r = run([sys.executable, "-I", "-B", os.path.join(PYD, "u1_oracle.py"), f"{t}/raw", CHECK, f"{t}/u1.json", f"{t}/u1.txt", "50000", min_ex],
            clean_env())
    j = json.load(open(f"{t}/u1.json"))
    shutil.rmtree(t)
    return r, j


r, j = u1()
check("T4 adapter positive: reviewed U, TU, F rows PASS, non-vacuity PASS, D = 50 000 ps both sides, counters 0, selfTest 1",
      r.returncode == 0 and j["result"] == "PASS" and j["u1_reviewed"] == "PASS"
      and all(j["rows"][k]["result"] == "PASS" for k in ("U", "TU", "F", "N"))
      and all(s["D_values_ps"] == [50000] and s["exchanges"] == 30 and s["selfTestPassed"] == 1 and not any(s["counters"].values())
              for s in j["sides"].values()), r.stdout[-600:])
check("T4 adapter confirms the requirements in the reviewed implementation (D, PCAP, FCS termination, 11 counters, selfTest)",
      all(j["requirements"][k] for k in ("L_REF_is_reference", "counters_count_11", "D_equals_pcap_and_reference",
                                         "logged_t1_t4_equal_pcap", "termination_valid_fcs", "counters_expected_zero", "selftest_required")))
for variant, row in (("D-off-by-1", "U"), ("counter", "F"), ("selftest", "F"), ("unterminated", "TU")):
    r, j = u1(variant)
    check(f"T4 adapter negative [{variant}] -> reviewed row {row} FAIL, overall FAIL (integer ps, no tolerance)",
          r.returncode == 1 and j["result"] == "FAIL" and j["rows"][row]["result"] == "FAIL", r.stdout[-400:])
for variant in ("missing-pcap", "missing-csv", "missing-sca", "truncated-pcap", "republish"):
    r, j = u1(variant)
    check(f"T4 adapter negative [{variant}] -> FAIL (missing or malformed evidence)", r.returncode == 1 and j["result"] == "FAIL", r.stdout[-300:])
r, j = u1(n=0)
check("T4 no exchanges at all: the reviewed rows pass vacuously, the adapter's non-vacuity guard FAILS the oracle",
      r.returncode == 1 and j["u1_reviewed"] == "PASS" and j["rows"]["N"]["result"] == "FAIL", j.get("rows"))
r, j = u1(n=10)
check("T4 fewer than the minimum exchanges -> FAIL", r.returncode == 1 and j["rows"]["N"]["result"] == "FAIL")
check("T4 no bytecode written into the reviewed checker directory", not os.path.exists(os.path.join(CHECK, "__pycache__")))

# ======================================================================= T5 evidence sealing
SEAL = os.path.join(PYD, "seal.py")
t = tempfile.mkdtemp(prefix="t2seal-")
synth.make(f"{t}/raw")
open(f"{t}/raw/run-M2S4U.log", "w").write("End.\n")
r = run([sys.executable, "-I", SEAL, "create", f"{t}/raw", f"{t}/m.sha256", f"{t}/seal.txt"], clean_env())
ro = not os.access(f"{t}/raw/run-M2S4U.log", os.W_OK) or os.geteuid() == 0
check("T5 seal: manifest of every file with size, read-only tree", r.returncode == 0 and "seal_result: PASS" in open(f"{t}/seal.txt").read()
      and len(open(f"{t}/m.sha256").read().splitlines()) == 8 and (os.stat(f"{t}/raw/run-M2S4U.log").st_mode & 0o222) == 0 and ro)
r = run([sys.executable, "-I", SEAL, "verify", f"{t}/raw", f"{t}/m.sha256", f"{t}/v.txt"], clean_env())
check("T5 verify unchanged -> PASS", r.returncode == 0 and "verify_result: PASS" in open(f"{t}/v.txt").read())
for label, act in (("modified", lambda: (os.chmod(f"{t}/raw/run-M2S4U.log", 0o644), open(f"{t}/raw/run-M2S4U.log", "a").write("x"))),
                   ("added", lambda: (os.chmod(f"{t}/raw", 0o755), open(f"{t}/raw/new.txt", "w").write("x"))),
                   ("removed", lambda: (os.chmod(f"{t}/raw/runs/M2S4U/M2S4U", 0o755), os.remove(f"{t}/raw/runs/M2S4U/M2S4U/0.vci")))):
    act()
    r = run([sys.executable, "-I", SEAL, "verify", f"{t}/raw", f"{t}/m.sha256", f"{t}/v.txt"], clean_env())
    check(f"T5 verify after a file was {label} -> FAIL", r.returncode == 1 and "verify_result: FAIL" in open(f"{t}/v.txt").read())
for d, _, fs in os.walk(t):
    os.chmod(d, 0o755)
os.symlink("/etc/hostname", f"{t}/raw/link")
r = run([sys.executable, "-I", SEAL, "create", f"{t}/raw", f"{t}/m2.sha256", f"{t}/seal2.txt"], clean_env())
check("T5 symbolic link in the raw evidence -> seal FAIL", r.returncode == 1)
for d, _, fs in os.walk(t):
    os.chmod(d, 0o755)
shutil.rmtree(t)

# ======================================================================= T6 raw-evidence publication checks
RAWPUB = os.path.join(PYD, "rawpub.py")


def rawpub(mut=None, limit="250000000"):
    t = tempfile.mkdtemp(prefix="t2pub-")
    synth.make(f"{t}/raw")
    open(f"{t}/raw/run-M2S4U.log", "w").write("Preparing for running configuration M2S4U, run #0...\nEnd.\n")
    open(f"{t}/raw/effective-config.txt", "w").write("Config: M2S4U\nRun 0: $repetition=0\nEnd.\n")
    os.makedirs(f"{t}/rec")
    open(f"{t}/rec/sim-control-sim.txt", "w").write("simulation_exit: 0\n")
    open(f"{t}/rec/lddebug.123", "w").write("     123:\tcalling init: /nix/store/x/libc.so.6\n")
    open(f"{t}/rec/argv-sim.nul", "wb").write(b"a\0b\0")
    open(f"{t}/raw-manifest.sha256", "w").write("x  1  ./a\n")
    if mut:
        mut(t)
    r = run([sys.executable, "-I", RAWPUB, f"{t}/raw", f"{t}/rec", t, f"{t}/pub", os.path.join(T1, "lib", "screen.py"), CHECK, limit,
             f"{t}/rep.txt"], clean_env())
    rep = open(f"{t}/rep.txt").read() if os.path.exists(f"{t}/rep.txt") else ""
    pub = sorted(os.path.relpath(os.path.join(d, f), f"{t}/pub") for d, _, fs in os.walk(f"{t}/pub") for f in fs) if os.path.isdir(f"{t}/pub") else None
    shutil.rmtree(t)
    return r, rep, pub


r, rep, pub = rawpub()
check("T6 raw publication: synthetic set passes; raw outputs, text records and manifests published; NUL argv file not published",
      r.returncode == 0 and "rawpub_result: PASS" in rep and "raw/runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttA.pcapRecorder[0].pcapng" in pub
      and "records/lddebug.123" in pub and "publication-manifest.sha256" in pub and "records/argv-sim.nul" not in pub, rep)


def put(path, data, mode="w"):
    def f(t):
        p = os.path.join(t, path)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        open(p, mode).write(data)
    return f


def pcap_mut(packets, note=b""):
    def f(t):
        p = os.path.join(t, "raw/runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttB.pcapRecorder[0].pcapng")
        open(p, "wb").write(synth.pcapng(packets, note))
    return f


ok_frame = synth.eth(synth.GPTP, "0aaa00000004", synth.gptp(2, (0x0B, 1), 1))
for label, mut, limit in (
        ("ELF file disguised as a text record", put("rec/evil.txt", b"\x7fELF\x02\x01\x01" + b"\0" * 50, "wb"), "250000000"),
        ("unexpected raw output file", put("raw/runs/M2S4U/M2S4U/1.sca", "version 3\n"), "250000000"),
        ("credential in the scalar file", put("raw/runs/M2S4U/M2S4U/0.sca", "attr x password=hunter2hunter2\n"), "250000000"),
        ("private path in the run log", put("raw/run-M2S4U.log", "/home/someone/secret\n"), "250000000"),
        ("non-UTF-8 text", put("raw/runs/M2S4U/M2S4U/0.vci", b"\xff\xfe\x00bad", "wb"), "250000000"),
        ("PCAP with a globally administered (real) source MAC", pcap_mut([(10 ** 9, 1, synth.eth(synth.GPTP, "001122334455", synth.gptp(2, (1, 1), 1)))]), "250000000"),
        ("PCAP with a token in its section header", pcap_mut([(10 ** 9, 1, ok_frame)], b"ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123"), "250000000"),
        ("malformed PCAP", put("raw/runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttA.pcapRecorder[0].pcapng", b"not a pcap at all", "wb"), "250000000"),
        ("publication above the size limit", None, "1000")):
    r, rep, pub = rawpub(mut, limit)
    check(f"T6 raw publication refused [{label}] and nothing left to upload", r.returncode == 1 and "rawpub_result: FAIL" in rep and pub is None, rep[-400:])

# ======================================================================= T7 evaluation E-1 .. E-9 and the verdict (synthetic records)
EVAL, FINAL, CONCLUDE = os.path.join(PYD, "evaluate_t2.py"), os.path.join(PYD, "final_t2.py"), os.path.join(STEPS, "conclude.sh")
WF_IDS = ["checkout", "t2identity", "setup", "bootstrap", "verify", "runtime", "b_omnetpp", "b_inet", "b_simu5g", "b_nasctime",
          "validate", "srcchanges", "sim", "seal", "oracle", "lockend", "t2lockend", "measure", "evaluate"]
LOG_OK = ("OMNeT++ Discrete Event Simulation  (C) 1992-2025 Andras Varga, OpenSim Ltd.\nSetting up Cmdenv...\n\n"
          "Preparing for running configuration M2S4U, run #0...\nSetting up network \"M2S4LinkTest\"...\nRunning simulation...\n"
          "\n<!> Simulation time limit reached -- at t=3s, event #123456\n\nCalling finish() at end of Run #0...\n\nEnd.\n")


def nulw(p, items):
    open(p, "wb").write(b"".join(x.encode() + b"\0" for x in items))


def full_state():
    t = tempfile.mkdtemp(prefix="t2ev-")
    ci, e3 = f"{t}/tier1", f"{t}/e3a"
    ev, rec, raw = f"{ci}/evidence", f"{e3}/records", f"{e3}/raw"
    repo, ws = f"{t}/repo", f"{ci}/ws"
    for d in (ev, rec, f"{repo}/simulations/m2", f"{ci}/publish"):
        os.makedirs(d)
    synth.make(raw)
    open(f"{raw}/run-M2S4U.log", "w").write(LOG_OK)
    open(f"{raw}/effective-config.txt", "w").write("Config: M2S4U\nRun 0: $repetition=0\n\tnetwork = nasctime.simulations.m2.M2S4LinkTest\n"
                                                    "\tsim-time-limit = 3s\n\tseed-set = 0\nEnd.\n")
    rows = [{"id": f"C-{i}", "criterion": "x", "result": "PASS", "detail": ""} for i in range(1, 15)]
    rows[12]["result"] = "NOT EVALUATED"
    rows[13]["result"] = "FAIL"   # tier-1's own C-14 forbids simulation: not used by E3a
    json.dump({"rows": rows}, open(f"{ev}/c-rows.json", "w"))
    shas = {"opp_run": "a" * 64, "libnasctime_m2.so": "b" * 64, "libsimu5g.so": "c" * 64, "libINET.so": "d" * 64}
    open(f"{ev}/binaries.tsv", "w").write("project\tkind\tpath\tbytes\tsha256\n" + "".join(
        f"p\tk\tx/{n}\t1\t{s}\n" for n, s in shas.items()))
    paths = {"opp_run": f"{ws}/omnetpp-6.5.0/bin/opp_run", "libnasctime_m2.so": f"{repo}/src/nasctime/m2/libnasctime_m2.so",
             "libsimu5g.so": f"{ws}/simu5g-1.8.1/src/libsimu5g.so", "libINET.so": f"{ws}/inet-4.7.0/src/libINET.so"}
    open(f"{rec}/binary-identity-sim.tsv", "w").write("role\tpath\tsha256\tbytes\n" + "".join(f"{n}\t{paths[n]}\t{shas[n]}\t1\n" for n in shas))
    labels = ["nix-install", "realise", "probe", "probe-runtime-before", "probe-runtime-after", "build-omnetpp", "build-inet",
              "build-simu5g", "build-nasctime", "validate", "t2-runconfig", "t2-sim"]
    open(f"{ev}/timings.tsv", "w").write("step\tseconds\texit\tstart_epoch\tend_epoch\n" + "".join(f"{l}\t5\t0\t1\t6\n" for l in labels))
    open(f"{ev}/guard.txt", "w").write("guard_terminated: yes\nliveness_checks_ok: 30\nliveness_checks_failed: 0\n")
    open(f"{ev}/lock.txt", "w").write("".join(f"{p} result: PASS\n" for p in ("before-realisation", "after-t2-runconfig", "after-t2-sim", "final", "final-t2")))
    open(f"{ev}/exec-checks.txt", "w").write("x [before t2-sim] ok\n")
    for l in ("build-omnetpp", "build-inet", "validate", "t2-runconfig"):
        open(f"{ev}/{l}.log", "w").write("compiling\n")
    open(f"{rec}/identity.txt", "w").write("head: abc\nidentity_result: PASS\n")
    open(f"{rec}/sim-control-preflight.txt", "w").write("preflight_exit: 0\n")
    open(f"{rec}/sim-control-sim.txt", "w").write("simulation_started: 1 pid=9\nsimulation_exit: 0\nwall_s: 7.500\nwatchdog_samples: 6\n"
                                                  "watchdog_max_output_bytes: 24000000\nfinal_output_bytes: 24490001\npeak_vmhwm_kib: 90000\n"
                                                  "watchdog_terminated: no\n")
    base = [paths["opp_run"], "-l", f"{repo}/src/nasctime/m2/nasctime_m2", "-l", f"{ws}/simu5g-1.8.1/src/simu5g",
            "-n", f"{repo}/simulations:{repo}/src:{ws}/simu5g-1.8.1/src:{ws}/inet-4.7.0/src", "-x", "nasctime.nodes",
            "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", "M2S4U", "--repeat=10", "-r", "0"]
    nulw(f"{rec}/argv-preflight.nul", base + ["-q", "runconfig"])
    sim = base + [f"--result-dir={raw}/runs/M2S4U", "--cmdenv-express-mode=true"]
    nulw(f"{rec}/argv-sim.nul", sim)
    nulw(f"{rec}/observed-cmdline.nul", sim)
    cwd = os.path.realpath(f"{repo}/simulations/m2")
    open(f"{rec}/observed-cwd.txt", "w").write(cwd + "\n")
    open(f"{rec}/cwd-preflight.txt", "w").write(f"cwd: {cwd}\n")
    for m in ("preflight", "sim"):
        open(f"{rec}/hazards-{m}.txt", "w").write("hazards: none\n")
    open(f"{rec}/lddebug.9", "w").write("".join(f"      9:\tcalling init: {p}\n" for p in (
        "/nix/store/x-glibc/lib/libc.so.6", f"{ws}/omnetpp-6.5.0/lib/liboppsim.so", paths["libnasctime_m2.so"],
        paths["libsimu5g.so"], paths["libINET.so"])))
    open(f"{rec}/sim.started", "w").close()
    r = run([sys.executable, "-I", "-B", os.path.join(PYD, "u1_oracle.py"), raw, CHECK, f"{rec}/u1-oracle.json", f"{rec}/u1-oracle.txt", "50000", "25"], clean_env())
    assert r.returncode == 0, r.stdout
    open(f"{rec}/modified-during-sim.txt", "w").close()
    for x in ("before", "after", "final"):
        open(f"{rec}/git-status-{x}.txt", "w").write("!! src/nasctime/m2/libnasctime_m2.so\n")
    open(f"{rec}/seal.txt", "w").write("manifest_sha256: e\nfiles: 9\ntotal_bytes: 100\nseal_result: PASS\n")
    open(f"{rec}/seal-verify.txt", "w").write("verify_result: PASS\n")
    open(f"{rec}/rawpub-check.txt", "w").write("total_bytes: 100\nfiles: 20\nrawpub_result: PASS\n")
    env = clean_env(EV=ev, REC=rec, RAW=raw, E3=e3, CI=ci, REPO=repo, WS=ws, **PINS,
                    STEP_OUTCOMES=json.dumps({i: {"outcome": "success"} for i in WF_IDS}),
                    PUBLISH_OUTCOME="success", T2PUBLISH_OUTCOME="success", RAWPUB_OUTCOME="success", GITHUB_STEP_SUMMARY=f"{t}/sum.md")
    return t, env


def evaluate(t, env, mut=None):
    if mut:
        mut(t, env)
    r1 = run([sys.executable, "-I", EVAL], env)
    r2 = run([sys.executable, "-I", FINAL], env)
    v = open(f"{env['E3']}/verdict.txt").read().strip() if os.path.exists(f"{env['E3']}/verdict.txt") else None
    rows = {x["id"]: x["result"] for x in json.load(open(f"{env['REC']}/e-final.json"))["rows"]} if os.path.exists(f"{env['REC']}/e-final.json") else {}
    return v, rows, r1, r2


t, env = full_state()
v, rows, r1, r2 = evaluate(t, env)
check("T7 complete synthetic record set -> E3a PASS, E-1 .. E-8 PASS, E-9 INFORMATIONAL, final exit 0",
      v == "E3a PASS" and all(rows.get(f"E-{i}") == "PASS" for i in range(1, 9)) and rows.get("E-9") == "INFORMATIONAL" and r2.returncode == 0,
      f"{v} {rows} {r1.stdout[-1500:]} {r1.stderr[-500:]}")
check("T7 E-9 compares the historical hashes (synthetic outputs differ -> DIFFERS, informational only)",
      "DIFFERS" in json.dumps(json.load(open(f"{env['REC']}/e-rows.json"))["facts"]["reference"]))
check("T7 verdict written to the diagnostic publication and the job summary", os.path.exists(f"{env['CI']}/publish/e3a-verdict.md")
      and "E3a PASS" in open(f"{t}/sum.md").read())
shutil.rmtree(t)


def edit(path, a, b):
    def f(t, env):
        p = path.format(**env)
        s = open(p).read()
        assert a in s, (p, a)
        open(p, "w").write(s.replace(a, b))
    return f


def write(path, data, binary=False):
    def f(t, env):
        open(path.format(**env), "wb" if binary else "w").write(data)
    return f


def remove(path):
    def f(t, env):
        p = path.format(**env)
        os.remove(p) if os.path.isfile(p) else shutil.rmtree(p)
    return f


def outcome(**o):
    def f(t, env):
        s = json.loads(env["STEP_OUTCOMES"])
        for k, v in o.items():
            s[k] = {"outcome": v}
        env["STEP_OUTCOMES"] = json.dumps(s)
    return f


def setenv(**kv):
    def f(t, env):
        env.update(kv)
    return f


def both(*fs):
    def f(t, env):
        for x in fs:
            x(t, env)
    return f


NE = "NOT EVALUATED"
CASES = [
    ("identity failed", edit("{REC}/identity.txt", "identity_result: PASS", "identity_result: FAIL"), "E3a FAIL", {"E-1": "FAIL"}),
    ("a tier-1 prerequisite (C-11) failed", edit("{EV}/c-rows.json", '"id": "C-11", "criterion": "x", "result": "PASS"',
                                                 '"id": "C-11", "criterion": "x", "result": "FAIL"'), "E3a FAIL", {"E-1": "FAIL"}),
    ("tier-1 rows missing", remove("{EV}/c-rows.json"), "E3a FAIL", {"E-1": "FAIL"}),
    ("pre-flight selects two runs", edit("{RAW}/effective-config.txt", "Run 0: $repetition=0\n", "Run 0: $repetition=0\nRun 1: $repetition=1\n"),
     "E3a FAIL", {"E-2": "FAIL"}),
    ("other simulation time in the effective configuration", edit("{RAW}/effective-config.txt", "sim-time-limit = 3s", "sim-time-limit = 30s"),
     "E3a FAIL", {"E-2": "FAIL"}),
    ("argument vector differs (extra option)", lambda t, env: nulw(f"{env['REC']}/argv-sim.nul",
     open(f"{env['REC']}/argv-sim.nul", "rb").read().decode().split("\0")[:-1] + ["--fingerprint=0"]), "E3a FAIL", {"E-2": "FAIL"}),
    ("observed process argv differs", lambda t, env: nulw(f"{env['REC']}/observed-cmdline.nul", ["opp_run", "-u", "Qtenv"]), "E3a FAIL", {"E-2": "FAIL"}),
    ("observed process argv missing", remove("{REC}/observed-cmdline.nul"), "E3a FAIL", {"E-2": "FAIL"}),
    ("other working directory", write("{REC}/observed-cwd.txt", "/tmp\n"), "E3a FAIL", {"E-2": "FAIL"}),
    ("simulator differs from the validated binary", edit("{REC}/binary-identity-sim.tsv", "a" * 64, "f" * 64), "E3a FAIL", {"E-2": "FAIL"}),
    ("a host library loaded", edit("{REC}/lddebug.9", "/nix/store/x-glibc/lib/libc.so.6", "/usr/lib/x86_64-linux-gnu/libc.so.6"),
     "E3a FAIL", {"E-2": "FAIL"}),
    ("loader record missing", remove("{REC}/lddebug.9"), "E3a FAIL", {"E-2": "FAIL"}),
    ("working-directory hazard", write("{REC}/hazards-sim.txt", "hazard: x\nhazards: FOUND\n"), "E3a FAIL", {"E-2": "FAIL"}),
    ("two start records", edit("{REC}/sim-control-sim.txt", "simulation_started: 1 pid=9\n", "simulation_started: 1 pid=9\nsimulation_started: 1 pid=10\n"),
     "E3a FAIL", {"E-3": "FAIL"}),
    ("two runs in the log", edit("{RAW}/run-M2S4U.log", "Running simulation...", "Running simulation...\nPreparing for running configuration M2S4U, run #1..."),
     "E3a FAIL", {"E-3": "FAIL"}),
    ("an output of another run", write("{RAW}/runs/M2S4U/M2S4U/1.sca", "version 3\n"), "E3a FAIL", {"E-3": "FAIL", "E-5": "FAIL"}),
    ("undeclared stage label", lambda t, env: open(f"{env['EV']}/timings.tsv", "a").write("t2-sim-again\t5\t0\t1\t6\n"), "E3a FAIL", {"E-3": "FAIL"}),
    ("simulation markers in a build log", write("{EV}/build-inet.log", "Preparing for running configuration X, run #0...\n"),
     "E3a FAIL", {"E-3": "FAIL"}),
    ("time budget breach", edit("{EV}/timings.tsv", "validate\t5\t0", "validate\t5\t124"), "E3a FAIL", {"E-3": "FAIL"}),
    ("execution-safety check failed", write("{EV}/exec-checks.txt", "x [after t2-sim] FAIL controlled directory not empty;\n"),
     "E3a FAIL", {"E-3": "FAIL"}),
    ("non-zero simulator exit", edit("{REC}/sim-control-sim.txt", "simulation_exit: 0", "simulation_exit: 1"), "E3a FAIL", {"E-4": "FAIL"}),
    ("time limit not reached", edit("{RAW}/run-M2S4U.log", "<!> Simulation time limit reached -- at t=3s, event #123456\n", ""),
     "E3a FAIL", {"E-4": "FAIL"}),
    ("stopped early at another simulation time", edit("{RAW}/run-M2S4U.log", "at t=3s,", "at t=2.5s,"), "E3a FAIL", {"E-4": "FAIL"}),
    ("last line not End.", edit("{RAW}/run-M2S4U.log", "\nEnd.\n", "\n"), "E3a FAIL", {"E-4": "FAIL"}),
    ("error line in the log", edit("{RAW}/run-M2S4U.log", "Running simulation...", "Running simulation...\n<!> Error: something"),
     "E3a FAIL", {"E-4": "FAIL"}),
    ("wall time above the cap", edit("{REC}/sim-control-sim.txt", "wall_s: 7.500", "wall_s: 600.500"), "E3a FAIL", {"E-4": "FAIL"}),
    ("watchdog terminated the run", edit("{REC}/sim-control-sim.txt", "watchdog_terminated: no", "watchdog_terminated: output too large"),
     "E3a FAIL", {"E-4": "FAIL"}),
    ("non-numeric watchdog measurement", edit("{REC}/sim-control-sim.txt", "final_output_bytes: 24490001", "final_output_bytes: ERR"),
     "E3a FAIL", {"E-4": "FAIL"}),
    ("output above the watchdog limit", edit("{REC}/sim-control-sim.txt", "watchdog_max_output_bytes: 24000000", "watchdog_max_output_bytes: 500000001"),
     "E3a FAIL", {"E-4": "FAIL"}),
    ("a result file missing", remove("{RAW}/runs/M2S4U/M2S4U/0.vci"), "E3a FAIL", {"E-5": "FAIL"}),
    ("an empty result file", write("{RAW}/runs/M2S4U/M2S4U/0.vec", ""), "E3a FAIL", {"E-5": "FAIL"}),
    ("scalar file of another configuration", edit("{RAW}/runs/M2S4U/M2S4U/0.sca", "attr configname M2S4U", "attr configname M2S4U-73"),
     "E3a FAIL", {"E-5": "FAIL"}),
    ("outputs above the acceptance limit", setenv(SIM_ACCEPT_LIMIT_B="10"), "E3a FAIL", {"E-5": "FAIL"}),
    ("U1 oracle failed", edit("{REC}/u1-oracle.json", '"result": "PASS"', '"result": "FAIL"'), "E3a FAIL", {"E-6": "FAIL"}),
    ("U1 oracle output missing although the oracle ran", remove("{REC}/u1-oracle.json"), "E3a FAIL", {"E-6": "FAIL"}),
    ("a file modified during the simulation", write("{REC}/modified-during-sim.txt", "/r/simulations/m2/omnetpp.ini\n"), "E3a FAIL", {"E-7": "FAIL"}),
    ("repository status changed", write("{REC}/git-status-final.txt", " M simulations/m2/omnetpp.ini\n"), "E3a FAIL", {"E-7": "FAIL"}),
    ("lock gate after the simulation failed", edit("{EV}/lock.txt", "after-t2-sim result: PASS", "after-t2-sim result: FAIL"), "E3a FAIL", {"E-7": "FAIL"}),
    ("seal verification failed", edit("{REC}/seal-verify.txt", "PASS", "FAIL"), "E3a FAIL", {"E-8": "FAIL"}),
    ("raw publication refused", setenv(RAWPUB_OUTCOME="failure"), "E3a FAIL", {"E-8": "FAIL"}),
    ("tier-2 diagnostic publication failed", setenv(T2PUBLISH_OUTCOME="failure"), "E3a FAIL", {"E-8": "FAIL"}),
    ("tier-1 diagnostic publication skipped", setenv(PUBLISH_OUTCOME="skipped"), "E3a FAIL", {"E-8": "FAIL"}),
    ("simulation step did not run", both(outcome(sim="skipped", seal="skipped", oracle="skipped"), remove("{REC}/u1-oracle.json")),
     "E3a FAIL", {"E-2": NE, "E-3": NE, "E-4": NE, "E-5": NE, "E-6": NE, "E-7": NE, "E-8": NE}),
    ("STOP", write("{EV}/STOP", "disk guard\n"), "STOP", {"E-3": "FAIL"}),
    ("guard failure", write("{EV}/GUARD_FAILURE", "dead\n"), "INFRASTRUCTURE FAILURE", {"E-3": "FAIL"}),
    ("NED incompatibility in a failed simulation -> BLOCKED with the diagnostic quoted",
     both(edit("{REC}/sim-control-sim.txt", "simulation_exit: 0", "simulation_exit: 1"),
          write("{RAW}/run-M2S4U.log", "Preparing for running configuration M2S4U, run #0...\n<!> Error: no such module type 'Foo' -- in module (M2S4LinkTest) (NED)\n")),
     "E3a BLOCKED (OMNeT++ 6.5.0 compatibility; no NED/INI patched)", {"E-4": "FAIL"}),
    ("other failure in a failed simulation -> FAIL, not BLOCKED",
     both(edit("{REC}/sim-control-sim.txt", "simulation_exit: 0", "simulation_exit: 139"), write("{RAW}/run-M2S4U.log", "Segmentation fault\n")),
     "E3a FAIL", {"E-4": "FAIL"}),
]
for label, mut, want_v, expect in CASES:
    t, env = full_state()
    v, rows, r1, r2 = evaluate(t, env, mut)
    bad = {k: (rows.get(k), w) for k, w in expect.items() if rows.get(k) != w}
    check(f"T7 {label} -> {want_v}", v == want_v and not bad and r2.returncode != 0, f"{v} mismatches={bad} {r1.stderr[-300:]}")
    shutil.rmtree(t)
t, env = full_state()
v, rows, r1, r2 = evaluate(t, env, remove("{REC}/e-rows.json") if False else None)
os.remove(f"{env['REC']}/e-rows.json")
r2 = run([sys.executable, "-I", FINAL], env)
check("T7 missing evaluation -> never PASS (INFRASTRUCTURE FAILURE / non-zero)", r2.returncode != 0
      and open(f"{env['E3']}/verdict.txt").read().strip() != "E3a PASS")
shutil.rmtree(t)

# ======================================================================= T8 conclusion: verdict and both uploads required
for v, d, rw, want in (("E3a PASS", "success", "success", 0), ("E3a PASS", "success", "failure", 1), ("E3a PASS", "skipped", "success", 1),
                       ("E3a FAIL", "success", "success", 1), (None, "success", "success", 1)):
    t = tempfile.mkdtemp(prefix="t2cc-")
    os.makedirs(f"{t}/e3a")
    if v:
        open(f"{t}/e3a/verdict.txt", "w").write(v + "\n")
    r = run(["bash", CONCLUDE], clean_env(RUNNER_TEMP=t, UPLOAD_DIAG_OUTCOME=d, UPLOAD_RAW_OUTCOME=rw))
    check(f"T8 conclusion [verdict={v}, diagnostics={d}, raw={rw}] -> exit {want}", (r.returncode == 0) == (want == 0), r.stdout)
    shutil.rmtree(t)

check("T9 the whole suite wrote no bytecode into the reviewed checker directory (oracle, publication)",
      not os.path.exists(os.path.join(CHECK, "__pycache__")))
os.chdir(REPO)
shutil.rmtree(WORK, ignore_errors=True)
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("FAILED:", *failed, sep="\n  ")
sys.exit(1 if failed else 0)
