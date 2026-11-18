#!/usr/bin/env python3
"""Offline self-tests of the tier-1 implementation (ci/tier1). No Nix, no opp_env, no network, no upstream compilation
and no simulation. Small throw-away ELF files are compiled with the host gcc only to exercise the binary, linkage and
loader-resolution logic. The production scripts are executed directly against synthetic sandboxes; mocked inputs are
stated in each section. Synthetic wrapper-suite results here test the evaluation logic only; they are never evidence.

usage: python3 -I ci/tier1/tests/test_tier1.py [--host-probe]
  --host-probe  also run the in-session link probe on this host (host dependent; reported NOT RUN otherwise)
"""
import hashlib
import importlib.util
import json
import os
import re
import shutil
import signal
import subprocess
import sys
import tempfile
import time

sys.dont_write_bytecode = True
HERE = os.path.dirname(os.path.abspath(__file__))
T1 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(T1))
LIB, PYD, STEPS, SESSION, WRAP = (os.path.join(T1, d) for d in ("lib", "py", "steps", "session", "wrapper"))
WF = os.path.join(REPO, ".github", "workflows", "tier1-full-stack.yml")
HOST_PROBE = "--host-probe" in sys.argv[1:]
results = []
# Run from a private scratch directory so that no test can leave files in the repository working tree.
WORKDIR = tempfile.mkdtemp(prefix="t1-selftest-")
os.chdir(WORKDIR)
TEST_VARS = ("TIER1_TEST_", "E2B3_TEST_", "A2V1_TEST_", "A2V1_STUB_")


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:700]}]" if detail and not cond else ""), flush=True)


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(PYD, name + ".py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m


def clean_env(**kw):
    e = {k: v for k, v in os.environ.items() if not k.startswith(TEST_VARS) and k not in ("A2V1_RESULTS_ROOT", "A2V1_COMMIT")}
    e.update(kw)
    return e


def pins():
    d = {}
    for l in open(os.path.join(T1, "pins.env")):
        l = l.strip()
        if l and not l.startswith("#") and "=" in l:
            k, v = l.split("=", 1)
            d[k] = v[1:-1] if v.startswith('"') and v.endswith('"') else v
    return d


PINS = pins()


def run(cmd, env, timeout=120, **kw):
    return subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout, **kw)


def alive(pid):
    st = subprocess.run(["ps", "-o", "stat=", "-p", str(pid)], capture_output=True, text=True).stdout.strip()
    return bool(st) and not st.startswith("Z")


def no_sleepers(tag):
    ps = subprocess.run(["ps", "-eo", "stat=,args="], capture_output=True, text=True).stdout.splitlines()
    return not [l for l in ps if tag in l and not l.strip().startswith("Z") and "ps -eo" not in l]


# ======================================================================= T0 static checks
for d, dirs, files in os.walk(T1):
    for f in files:
        p = os.path.join(d, f)
        if f.endswith(".sh") or f == "pins.env":
            r = subprocess.run(["bash", "-n", p], capture_output=True, text=True)
            check(f"T0 bash -n {os.path.relpath(p, T1)}", r.returncode == 0, r.stderr)
        elif f.endswith(".py"):
            r = subprocess.run([sys.executable, "-I", "-c", "import ast,sys; ast.parse(open(sys.argv[1]).read())", p], capture_output=True, text=True)
            check(f"T0 python parses {os.path.relpath(p, T1)}", r.returncode == 0, r.stderr)
lock = os.path.join(REPO, PINS["LOCK_FILE"])
check("T0 approved lock: size and sha256 equal the pins", os.path.getsize(lock) == int(PINS["LOCK_SIZE"])
      and hashlib.sha256(open(lock, "rb").read()).hexdigest() == PINS["LOCK_SHA256"] == "9ead146500c1f8b54f2a611e0a753e705e35682639307c3ea7bd104f5109f60a")
r = subprocess.run([sys.executable, "-I", os.path.join(PYD, "lock_content.py"), lock], capture_output=True, text=True)
check("T0 approved lock content (nixpkgs, flake-utils, systems, indirect 26.05)", r.returncode == 0, r.stdout + r.stderr)
check("T0 reviewed pins", PINS["NIX_VERSION"] == "2.34.4" and PINS["OPP_ENV_PIN"] == "0.36.2.261110"
      and PINS["PROJECTS"] == "omnetpp-6.5.0 inet-4.7.0 simu5g-1.8.1"
      and PINS["VM_SYS_LIBS"] == "-lstdc++ -lpython3.13 -ldl -lm -L/nix/store/qhmqdg27kcrlkl8ida6d5hiacw0y8d21-elfutils-0.194/lib -ldw -lelf"
      and PINS["ASSET_OMNETPP_SHA256"].startswith("d4f40a1c") and PINS["ASSET_INET_SHA256"].startswith("0de338f8")
      and PINS["ASSET_SIMU5G_SHA256"].startswith("a63b3318") and PINS["JOB_BUDGET_S"] == "7200" and PINS["RESERVE_S"] == "600"
      and PINS["WRAPPER_EXPECTED_LINE"] == "A2-V1 wrapper tests: 21 / 21 PASS", PINS)
caps = {k: int(v) for k, v in PINS.items() if k.startswith("CAP_")}
check("T0 stage caps as approved (bootstrap 20, runtime 10, omnetpp 20, inet 45, simu5g 20, nasctime 5, validate 5, wrapper 25 min)",
      caps == {"CAP_BOOTSTRAP_S": 1200, "CAP_RUNTIME_S": 600, "CAP_OMNETPP_S": 1200, "CAP_INET_S": 2700, "CAP_SIMU5G_S": 1200,
               "CAP_NASCTIME_S": 300, "CAP_VALIDATE_S": 300, "CAP_WRAPPER_S": 1500}, caps)
WFT = open(WF).read()
check("T0 workflow: pull_request to m2/continuation only, with the five approved types",
      "on:\n  pull_request:\n    branches: [m2/continuation]\n    types: [opened, synchronize, reopened, ready_for_review, labeled]\n" in WFT
      and "pull_request_target" not in WFT and "workflow_dispatch" not in WFT and "\n  push:" not in WFT and "schedule" not in WFT)
check("T0 workflow: read-only permissions, no secrets, no caches, no self-hosted runners",
      "permissions:\n  contents: read\n" in WFT and "secrets." not in WFT and "actions/cache" not in WFT and "self-hosted" not in WFT
      and WFT.count("runs-on: ubuntu-22.04") == 3)
uses = re.findall(r"uses: (\S+)", WFT)
check("T0 workflow: actions pinned by commit sha", set(uses) == {"actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1",
      "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"}, uses)
check("T0 workflow: every checkout without persisted credentials", WFT.count("actions/checkout@") == WFT.count("persist-credentials: false") == 3)
check("T0 workflow: 120-minute full-stack job, unique concurrency group for unselected runs",
      "timeout-minutes: 120" in WFT and "cancel-in-progress: true" in WFT and "needs.decide.outputs.run == 'true' && 'run' || github.run_id" in WFT)
check("T0 workflow: event values only through env, never interpolated into run scripts",
      not re.search(r"\n        run: [^\n]*\$\{\{", WFT) and "run: |" not in WFT)
ids = re.findall(r"\n        id: (\w+)", WFT[WFT.index("\n  fullstack:"):])
check("T0 workflow: step order", ids == ["checkout", "setup", "bootstrap", "verify", "runtime", "b_omnetpp", "b_inet", "b_simu5g",
      "b_nasctime", "validate", "srcchanges", "wrapper", "lockend", "measure", "evaluate", "publish", "final", "upload", "conclude"], ids)
alltext = "\n".join(open(os.path.join(d, f)).read() for d, _, fs in os.walk(T1) for f in fs
                    if f.endswith((".sh", ".py")) and "tests" not in d)
code = "\n".join(l for l in alltext.splitlines() if not l.strip().startswith("#"))
check("T0 never: smoke tests, test_all, fingerprints, top-level make, autoremove/purge, LD_LIBRARY_PATH with host dirs, lock/Makefile.inc writes",
      not re.search(r"--smoke-test|\btest_all\b|smoke_test_|autoremove|apt-get[^\n]*purge|--purge|LD_LIBRARY_PATH=[^\n]*(/usr/lib|/lib/x86_64)", code)
      and not re.search(r"(sed -i|>|tee)[^\n]*(Makefile\.inc|flake\.lock)", code.replace('> "$EV/', "")))
check("T0 release-only builds", all(f"build_{p} release" in open(os.path.join(STEPS, "build.sh")).read() for p in ("omnetpp", "inet", "simu5g"))
      and open(os.path.join(STEPS, "build.sh")).read().count("--build-modes release") == 1)
check("T0 provenance module has no environment hook (C5: dependency injection only)",
      "os.environ" not in open(os.path.join(PYD, "provenance.py")).read() and "getenv" not in open(os.path.join(PYD, "provenance.py")).read()
      and "TEST_FS_ROOT" not in open(os.path.join(PYD, "provenance.py")).read())
check("T0 README present", os.path.exists(os.path.join(T1, "README.md")))

# ======================================================================= T1 production rejects test overrides (C5)
for var in ("TIER1_TEST_FS_ROOT", "E2B3_TEST_FS_ROOT", "A2V1_STUB_MODE", "A2V1_TEST_HOOKS", "A2V1_RESULTS_ROOT", "A2V1_COMMIT"):
    t = tempfile.mkdtemp(prefix="t1c5-")
    r = run(["bash", os.path.join(STEPS, "setup.sh")], clean_env(RUNNER_TEMP=t, **{var: "/x"}))
    check(f"T1 production refuses {var} (exit 3, nothing created)", r.returncode == 3 and var in r.stdout and not os.path.exists(f"{t}/tier1"),
          r.stdout + r.stderr)
    shutil.rmtree(t)
for step in sorted(os.listdir(STEPS)):
    if step.endswith(".sh") and step != "conclude.sh":
        check(f"T1 step {step} sources lib/common.sh", '. "$(dirname "$0")/../lib/common.sh"' in open(os.path.join(STEPS, step)).read())


# ======================================================================= sandbox for the lib scripts
def sandbox(stop_gib="0", interval="1", stale="5", job_start=None, budget="7200", reserve="600", gate_gib="0"):
    t = tempfile.mkdtemp(prefix="t1-")
    ci = os.path.join(t, "tier1")
    ev = os.path.join(ci, "evidence")
    for d in (ev, os.path.join(ci, "exec"), os.path.join(ci, "ws"), os.path.join(ci, "unpublished"), os.path.join(t, "repo")):
        os.makedirs(d)
    open(os.path.join(ev, "timings.tsv"), "w").write("step\tseconds\texit\tstart_epoch\tend_epoch\n")
    env = clean_env(E2B=ci, EV=ev, RUNNER_TEMP=t, WS=os.path.join(ci, "ws"), STOP_FREE_GIB=stop_gib, GUARD_INTERVAL_S=interval,
                    GUARD_STALE_S=stale, JOB_START=str(job_start or int(time.time())), JOB_BUDGET_S=budget, RESERVE_S=reserve,
                    START_MIN_FREE_GIB=gate_gib, REPO=os.path.join(t, "repo"), T1_LIB=LIB, LOCK_SHA256="0" * 64, HELPER_LOCK_SHA256="0" * 64)
    return t, ci, ev, env


def start_guard(ev, env):
    subprocess.run(["bash", "-c", f'nohup setsid "{LIB}/guard.sh" > /dev/null 2>&1 < /dev/null &'], env=env, check=True)
    for _ in range(40):
        if os.path.exists(os.path.join(ev, "guard.heartbeat")):
            break
        time.sleep(0.25)
    return int(open(os.path.join(ev, "guard.pid")).read())


def stop_guard(ev, pid):
    open(os.path.join(ev, "guard.off"), "w").close()
    for _ in range(40):
        if not alive(pid):
            return True
        time.sleep(0.25)
    return False


G = os.path.join(LIB, "guarded.sh")
# ======================================================================= T2 guard lifecycle and guarded runs
t, ci, ev, env = sandbox()
gp = start_guard(ev, env)
r = run([G, "ok", "true"], env)
check("T2 guarded true -> 0", r.returncode == 0, r.stdout + r.stderr)
r = run([G, "bad", "sh", "-c", "echo visible-tail; exit 3"], env)
check("T2 failure -> rc 3 with screened tail", r.returncode == 3 and "visible-tail" in r.stdout, r.stdout)
r = run([G, "leak", "sh", "-c", "echo ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123; exit 2"], env)
check("T2 sensitive tail suppressed", r.returncode == 2 and "ghp_" not in r.stdout and "suppressed" in r.stdout, r.stdout)
tl = [l.split("\t") for l in open(f"{ev}/timings.tsv").read().splitlines()]
check("T2 timings have 5 columns with epochs", all(len(x) == 5 for x in tl) and tl[1][0] == "ok" and int(tl[1][4]) >= int(tl[1][3]))
check("T2 guard terminates on guard.off", stop_guard(ev, gp) and os.path.exists(f"{ev}/guard.exited"))
r = run([G, "after", "true"], env)
check("T2 guarded run with a dead guard -> 91 (infrastructure failure)", r.returncode == 91 and os.path.exists(f"{ev}/GUARD_FAILURE"), r.stdout)
shutil.rmtree(t)
# ======================================================================= T3 STOP enforcement and race
t, ci, ev, env = sandbox(stop_gib="100000")
gp = start_guard(ev, env)
time.sleep(1.5)
r = run([G, "x", "sleep", "131"], env)
check("T3 STOP before start -> 90, not run", r.returncode == 90 and no_sleepers("sleep 131"))
os.remove(f"{ev}/STOP")
t0 = time.time()
r = run([G, "race", "bash", "-c", f"sleep 1; echo x > {ev}/STOP; sleep 132 & sleep 132"], env)
check("T3 STOP mid-run -> group killed, 90", r.returncode == 90 and time.time() - t0 < 40 and no_sleepers("sleep 132"), r.stdout)
stop_guard(ev, gp)
shutil.rmtree(t)
t, ci, ev, env = sandbox()
gp = start_guard(ev, env)
open(f"{ev}/STOP", "w").write("synthetic\n")
p = subprocess.Popen(["setsid", "sleep", "133"])
open(f"{ev}/guard.target", "w").write(str(p.pid))
for _ in range(30):
    if p.poll() is not None:
        break
    time.sleep(0.5)
check("T3 group registered after STOP is killed by the guard", p.poll() is not None)
stop_guard(ev, gp)
shutil.rmtree(t)
# ======================================================================= T4 time budget
t, ci, ev, env = sandbox()
gp = start_guard(ev, env)
t0 = time.time()
r = run([G, "slow", "bash", "-c", "sleep 134 & sleep 134"], dict(env, STAGE_CAP_S="3"))
check("T4 stage cap exceeded -> 124, group killed", r.returncode == 124 and time.time() - t0 < 20 and no_sleepers("sleep 134"), r.stdout)
r = run([G, "late", "touch", f"{ev}/ran"], dict(env, JOB_START=str(int(time.time()) - 7200 + 600 + 60)))
check("T4 job budget exhausted -> 92, not run", r.returncode == 92 and not os.path.exists(f"{ev}/ran"), r.stdout)
r = run([G, "tight", "bash", "-c", "sleep 136"], dict(env, JOB_START=str(int(time.time()) - 7200 + 600 + 125)), timeout=240)
check("T4 remaining job budget limits a stage -> 124", r.returncode == 124 and re.search(r"time limit 12[0-5]s", r.stdout)
      and no_sleepers("sleep 136"), r.stdout)
tl = open(f"{ev}/timings.tsv").read()
check("T4 timings record 124 and 92", "\t124\t" in tl and "\t92\t" in tl)
stop_guard(ev, gp)
shutil.rmtree(t)
# ======================================================================= T5 disk gate
t, ci, ev, env = sandbox(gate_gib="0")
check("T5 disk gate passes with enough space", run([f"{LIB}/diskgate.sh", "g1"], env).returncode == 0)
r = run([f"{LIB}/diskgate.sh", "g2"], dict(env, START_MIN_FREE_GIB="100000"))
check("T5 disk gate below threshold -> 90 + STOP", r.returncode == 90 and os.path.exists(f"{ev}/STOP"))
check("T5 gate checkpoints recorded", open(f"{ev}/disk-gates.txt").read().count("root_avail_B=") == 2)
shutil.rmtree(t)
# ======================================================================= T5b lock gate
t, ci, ev, env = sandbox()
A = os.path.join(env["WS"], ".opp_env_workspace")
for v, c in (("26.05", "approved"), ("22.11", "helper")):
    os.makedirs(f"{A}/{v}")
    open(f"{A}/{v}/flake.lock", "w").write(c)
env.update(LOCK_SHA256=hashlib.sha256(b"approved").hexdigest(), HELPER_LOCK_SHA256=hashlib.sha256(b"helper").hexdigest())
open(f"{ev}/clean.log", "w").write("building...\n")
open(f"{ev}/dirty.log", "w").write("warning: updating lock file '/x/flake.lock'\n")
check("T5b lock gate: unchanged locks and clean logs -> PASS", run([f"{LIB}/lockcheck.sh", "p1", f"{ev}/clean.log"], env).returncode == 0)
check("T5b lock gate: lock-update message -> FAIL", run([f"{LIB}/lockcheck.sh", "p2", f"{ev}/dirty.log"], env).returncode == 1)
open(f"{A}/26.05/flake.lock", "w").write("changed")
check("T5b lock gate: changed lock -> FAIL", run([f"{LIB}/lockcheck.sh", "p3"], env).returncode == 1
      and "p3 result: FAIL" in open(f"{ev}/lock.txt").read())
shutil.rmtree(t)


# ======================================================================= T6 build-m2.sh preconditions (no fallback paths)
def m2_env():
    t, ci, ev, env = sandbox()
    ws, repo = env["WS"], env["REPO"]
    om, inet, s5 = f"{ws}/omnetpp-6.5.0", f"{ws}/inet-4.7.0", f"{ws}/simu5g-1.8.1"
    for d in (f"{om}/bin", f"{om}/lib", f"{inet}/src", f"{s5}/src", f"{repo}/src/nasctime/m2"):
        os.makedirs(d, exist_ok=True)
    open(f"{om}/Version", "w").write("omnetpp-6.5.0\n")
    open(f"{s5}/Version", "w").write("1.8.1\n")
    open(f"{inet}/src/libINET.so", "w").write("x")
    open(f"{om}/lib/liboppsim.so", "w").write("x")
    open(f"{om}/setenv", "w").write(f'echo "setenv sourced from $(cd "$(dirname "${{BASH_SOURCE[0]}}")" && pwd)" >> {ev}/m2trace.txt\n')
    open(f"{om}/bin/opp_makemake", "w").write(f'#!/bin/sh\necho "opp_makemake $*" >> {ev}/m2trace.txt\n')
    os.chmod(f"{om}/bin/opp_makemake", 0o755)
    fake = os.path.join(t, "fakebin")
    os.makedirs(fake)
    open(f"{fake}/make", "w").write(f'#!/bin/sh\necho "make $*" >> {ev}/m2trace.txt\ntouch libnasctime_m2.so\n')
    os.chmod(f"{fake}/make", 0o755)
    shutil.copy(os.path.join(REPO, "src/nasctime/m2/build.sh"), f"{repo}/src/nasctime/m2/build.sh")
    env.update(PATH=f"{om}/bin:{fake}:" + os.environ["PATH"], OMNETPP_ROOT=om, INET_ROOT=inet, SIMU5G_ROOT=s5,
               OMNETPP_VERSION="6.5.0", INET_VERSION="4.7.0", SIMU5G_VERSION="1.8.1")
    return t, ci, ev, env, repo, ws


BM2 = os.path.join(SESSION, "build-m2.sh")
t, ci, ev, env, repo, ws = m2_env()
r = run(["bash", BM2, repo, ws], env)
tr = open(f"{ev}/m2trace.txt").read() if os.path.exists(f"{ev}/m2trace.txt") else ""
check("T6 build-m2 runs the repository's build.sh against the workspace stack (release)", r.returncode == 0
      and f"setenv sourced from {ws}/omnetpp-6.5.0" in tr and f"-I{ws}/inet-4.7.0/src" in tr and "make MODE=release" in tr
      and "/root/stack" not in tr and os.path.exists(f"{repo}/src/nasctime/m2/libnasctime_m2.so"), r.stdout + r.stderr + tr)
for label, change in (("unset OMNETPP_ROOT", {"OMNETPP_ROOT": None}), ("wrong INET_ROOT", {"INET_ROOT": "/root/stack/inet-4.7.0"}),
                      ("wrong SIMU5G_ROOT", {"SIMU5G_ROOT": "/tmp/x"}), ("wrong version", {"INET_VERSION": "4.6.0"})):
    e = dict(env)
    for k, v in change.items():
        if v is None:
            e.pop(k, None)
        else:
            e[k] = v
    check(f"T6 precondition fails closed: {label} -> 3", run(["bash", BM2, repo, ws], e).returncode == 3)
bs = open(f"{repo}/src/nasctime/m2/build.sh").read()
open(f"{repo}/src/nasctime/m2/build.sh", "w").write(bs.replace("OMNETPP_ROOT=${OMNETPP_ROOT:-/root/stack/omnetpp-6.4.0}", "OMNETPP_ROOT=/root/stack/omnetpp-6.4.0"))
check("T6 build.sh that would ignore OMNETPP_ROOT -> 3", run(["bash", BM2, repo, ws], env).returncode == 3)
shutil.rmtree(t)


# ======================================================================= T7 validate.sh (binaries, linkage, runtime, RUNPATH classes)
def cc(args, cwd):
    subprocess.run(["gcc", *args], cwd=cwd, check=True, capture_output=True)


INTERP = subprocess.run(["bash", "-c", "readelf -l /bin/true | sed -n 's/.*interpreter: \\(.*\\)]/\\1/p'"], capture_output=True, text=True).stdout.strip()


def validate_env(variant=None):
    t, ci, ev, env, repo, ws = m2_env()
    om, inet, s5 = f"{ws}/omnetpp-6.5.0", f"{ws}/inet-4.7.0", f"{ws}/simu5g-1.8.1"
    b = os.path.join(t, "build")
    os.makedirs(b)
    code = 'Version: 6.5.0, build: synthetic' if variant != "badversion" else 'Version: 6.4.0'
    rc = 127 if variant == "oppv-exit" else 0
    open(f"{b}/v.c", "w").write(f'#include <stdio.h>\nint main(){{puts("OMNeT++ Discrete Event Simulation  {code}");return {rc};}}\n')
    open(f"{b}/l.c", "w").write("int f(void){return 1;}\n")
    open(f"{b}/dep.c", "w").write("int g(void){return 2;}\n")
    open(f"{b}/user.c", "w").write("int g(void); int h(void){return g();}\n")
    cc(["v.c", "-o", "opp"], b)
    cc(["-shared", "-fPIC", "l.c", "-o", "libl.so"], b)
    cc(["-shared", "-fPIC", "dep.c", "-o", "libdep.so"], b)
    cc(["-shared", "-fPIC", "user.c", "-L.", "-ldep", "-o", "libuser.so"], b)
    for x in ("opp_run", "opp_run_release", "opp_msgtool", "opp_nedtool", "opp_scavetool", "opp_eventlogtool"):
        shutil.copy(f"{b}/opp", f"{om}/bin/{x}")
    for x in ("opp_msgc", "opp_featuretool"):
        open(f"{om}/bin/{x}", "w").write("#!/bin/sh\n")
        os.chmod(f"{om}/bin/{x}", 0o755)
    for l in ("oppcommon", "opplayout", "oppeventlog", "oppscave", "oppnedxml", "oppsim", "oppenvir", "oppcmdenv", "oppqtenv"):
        shutil.copy(f"{b}/libl.so", f"{om}/lib/lib{l}.so")
    open(f"{om}/lib/liboppmain.a", "w").write("!<arch>\n")
    # TEST-ONLY: libc is resolved from an allowed project library directory (stands in for the /nix/store glibc)
    shutil.copy(os.path.realpath("/lib/x86_64-linux-gnu/libc.so.6"), f"{om}/lib/libc.so.6")
    shutil.copy(f"{b}/libl.so", f"{inet}/src/libINET.so")
    shutil.copy(f"{b}/libdep.so", f"{s5}/src/libdep.so")
    shutil.copy(f"{b}/libuser.so", f"{s5}/src/libsimu5g.so")
    shutil.copy(f"{b}/libl.so", f"{repo}/src/nasctime/m2/libnasctime_m2.so")
    open(f"{om}/Makefile.inc", "w").write("CXX = clang++\nCFLAGS_RELEASE = -O3 -DNDEBUG=1\nSYS_LIBS = -lstdc++ -ldl\nWITH_QTENV = yes\nSHARED_LIBS = yes\n")
    for mk in (f"{inet}/src/Makefile", f"{s5}/src/Makefile", f"{repo}/src/nasctime/m2/Makefile"):
        open(mk, "w").write("#\n# OMNeT++/OMNEST Makefile\n#\n#  opp_makemake --make-so -f --deep\n#\n")
    open(f"{inet}/.oppfeaturestate", "w").write('<featurestates>\n<feature id="A" enabled="true"/>\n<feature id="B" enabled="false"/>\n</featurestates>\n')
    os.makedirs(f"{inet}/src/inet")
    open(f"{inet}/src/inet/features.h", "w").write("#define X\n")
    fake = os.path.join(t, "fakebin")
    open(f"{fake}/patchelf", "w").write(f"#!/bin/sh\necho {INTERP}\n")
    os.chmod(f"{fake}/patchelf", 0o755)
    if variant == "unresolved":
        os.remove(f"{s5}/src/libdep.so")
    elif variant == "missing":
        os.remove(f"{inet}/src/libINET.so")
    elif variant == "debug":
        shutil.copy(f"{b}/libl.so", f"{om}/lib/liboppsim_dbg.so")
    elif variant == "libcxx-transitive":
        cc(["-shared", "-fPIC", "dep.c", "-Wl,-soname,libc++.so.1", "-o", "libc++.so.1"], b)
        open(f"{b}/u2.c", "w").write("int g(void); int h2(void){return g();}\n")
        cc(["-shared", "-fPIC", "u2.c", "-L.", "-l:libc++.so.1", "-o", "libmid.so"], b)
        shutil.copy(f"{b}/libc++.so.1", f"{s5}/src/libc++.so.1")
        shutil.copy(f"{b}/libmid.so", f"{s5}/src/libmid.so")
        open(f"{b}/top.c", "w").write("int h2(void); int top(void){return h2();}\n")
        cc(["-shared", "-fPIC", "top.c", "-L.", "-lmid", "-o", "libtop.so"], b)
        shutil.copy(f"{b}/libtop.so", f"{s5}/src/libsimu5g.so")
    elif variant == "libunwind-only":
        cc(["-shared", "-fPIC", "dep.c", "-Wl,-soname,libunwind.so.1", "-o", "libunwind.so.1"], b)
        open(f"{b}/u3.c", "w").write("int g(void); int h3(void){return g();}\n")
        cc(["-shared", "-fPIC", "u3.c", "-L.", "-l:libunwind.so.1", "-o", "libu3.so"], b)
        shutil.copy(f"{b}/libunwind.so.1", f"{inet}/src/libunwind.so.1")
        shutil.copy(f"{b}/libu3.so", f"{inet}/src/libINET.so")
    elif variant == "unexpected-runpath":
        # a library resolved through a non-store, non-project RUNPATH directory (like outputs/out/lib) must fail
        od = os.path.join(t, "outputs/out/lib")
        os.makedirs(od)
        cc(["-shared", "-fPIC", "dep.c", "-o", "libodep.so"], b)
        shutil.copy(f"{b}/libodep.so", f"{od}/libodep.so")
        open(f"{b}/u4.c", "w").write("int g(void); int h4(void){return g();}\n")
        cc(["-shared", "-fPIC", "u4.c", "-L.", "-lodep", f"-Wl,-rpath,{od}", "-o", "libu4.so"], b)
        shutil.copy(f"{b}/libu4.so", f"{repo}/src/nasctime/m2/libnasctime_m2.so")
    elif variant in ("runpath-relative", "runpath-absent", "runpath-existing-unused", "runpath-project"):
        rp = {"runpath-relative": ".", "runpath-absent": os.path.join(t, "outputs/out/lib"),
              "runpath-existing-unused": os.path.join(t, "writable"), "runpath-project": f"{om}/lib"}[variant]
        if variant == "runpath-existing-unused":
            os.makedirs(rp)
        cc(["-shared", "-fPIC", "l.c", f"-Wl,-rpath,{rp}", "-Wl,--enable-new-dtags", "-o", "librp.so"], b)
        shutil.copy(f"{b}/librp.so", f"{repo}/src/nasctime/m2/libnasctime_m2.so")
    elif variant == "host-libstdcxx":
        open(f"{b}/x.cc", "w").write("#include <string>\nstd::string s(){return std::string(40,'x');}\n")
        subprocess.run(["g++", "-shared", "-fPIC", "x.cc", "-o", "libx.so"], cwd=b, check=True, capture_output=True)
        shutil.copy(f"{b}/libx.so", f"{repo}/src/nasctime/m2/libnasctime_m2.so")
    return t, ci, ev, env, repo, ws


def vresult(ev):
    return dict(l.split(": ", 1) for l in open(f"{ev}/validate-result.txt").read().splitlines() if ": " in l)


VAL = os.path.join(SESSION, "validate.sh")
t, ci, ev, env, repo, ws = validate_env()
r = run(["bash", VAL, ev, ws, repo], env)
rows = open(f"{ev}/binaries.tsv").read().splitlines()
hdr, rows = rows[0].split("\t"), rows[1:]
elfrows = [x.split("\t") for x in rows if x.split("\t")[5] == "yes"]
vr = vresult(ev)
check("T7 validate PASS: 22 entries x 14 columns, 18 ELF resolved, all results PASS",
      r.returncode == 0 and len(hdr) == 14 and len(rows) == 22 and all(len(x.split("\t")) == 14 for x in rows) and len(elfrows) == 18
      and all(x[9] == "0" and x[10] == "none" for x in elfrows)
      and vr == {"binaries_result": "PASS", "oppv_result": "PASS", "linkage_result": "PASS", "runtime_result": "PASS", "validate_result": "PASS"},
      r.stdout + r.stderr + str(vr))
check("T7 build options include SYS_LIBS", "SYS_LIBS = -lstdc++ -ldl" in open(f"{ev}/build-options.txt").read())
check("T7 runtime-symbols evidence recorded", open(f"{ev}/runtime-symbols.txt").read().count("== ") == 6)
shutil.rmtree(t)
for variant, want in (("unresolved", {"linkage_result": "FAIL", "binaries_result": "PASS", "oppv_result": "PASS", "runtime_result": "NOT EVALUATED"}),
                      ("missing", {"binaries_result": "FAIL"}),
                      ("debug", {"binaries_result": "FAIL", "linkage_result": "PASS"}),
                      ("badversion", {"oppv_result": "FAIL", "binaries_result": "PASS"}),
                      ("oppv-exit", {"oppv_result": "FAIL", "binaries_result": "PASS", "linkage_result": "PASS"}),
                      ("libcxx-transitive", {"runtime_result": "FAIL", "linkage_result": "PASS"}),
                      ("host-libstdcxx", {"runtime_result": "FAIL", "linkage_result": "PASS"}),
                      ("unexpected-runpath", {"runtime_result": "FAIL", "linkage_result": "PASS"}),
                      ("runpath-relative", {"runtime_result": "PASS", "validate_result": "PASS"}),
                      ("runpath-absent", {"runtime_result": "PASS", "validate_result": "PASS"}),
                      ("runpath-project", {"runtime_result": "PASS", "validate_result": "PASS"}),
                      ("runpath-existing-unused", {"runtime_result": "FAIL", "linkage_result": "PASS"}),
                      ("libunwind-only", {"runtime_result": "PASS", "linkage_result": "PASS", "validate_result": "PASS"})):
    t, ci, ev, env, repo, ws = validate_env(variant)
    r = run(["bash", VAL, ev, ws, repo], env)
    vr = vresult(ev)
    obs = open(f"{ev}/runpath-observation-validate.txt").read()
    extra, want_ok = "", True
    if variant == "libcxx-transitive":
        extra = [x for x in open(f"{ev}/binaries.tsv").read().splitlines() if "libsimu5g" in x][0]
        want_ok = "libc++.so.1" in extra.split("\t")[10]
    elif variant == "unexpected-runpath":
        extra = [x for x in open(f"{ev}/binaries.tsv").read().splitlines() if "libnasctime_m2" in x][0] + obs
        want_ok = "outputs/out/lib/libodep.so" in extra.split("\t")[13] and "class=UNEXPECTED" in obs
    elif variant.startswith("runpath-"):
        want_ok = {"runpath-relative": "entry . exists=yes class=relative", "runpath-absent": "exists=no class=absent",
                   "runpath-existing-unused": "exists=yes class=UNEXPECTED", "runpath-project": None}[variant] in obs \
            if variant != "runpath-project" else "class=project" in obs
        extra = obs
    elif variant == "libunwind-only":
        extra = [x for x in open(f"{ev}/binaries.tsv").read().splitlines() if "libINET" in x][0]
        want_ok = "libunwind.so.1" in extra.split("\t")[11] and extra.split("\t")[10] == "none"
    elif variant == "unresolved":
        extra = open(f"{ev}/unresolved.txt").read()
        want_ok = "libdep.so" in extra
    check(f"T7 validate {variant} -> {want}", all(vr.get(k) == v for k, v in want.items()) and want_ok
          and ((r.returncode == 0) == (vr.get("validate_result") == "PASS")), f"{r.returncode} {vr} {extra}")
    shutil.rmtree(t)


# ======================================================================= T8 source-change classification
def manifest(root):
    lines = []
    for d, dirs, files in os.walk(root):
        rel = os.path.relpath(d, root)
        if rel.split(os.sep)[0] in ("ide", ".opp_env"):
            continue
        for f in files:
            rp = "./" + os.path.normpath(os.path.join(rel, f))
            lines.append(f"{hashlib.sha1(open(os.path.join(root, rp), 'rb').read()).hexdigest()}  {rp}\n")
    os.makedirs(f"{root}/.opp_env", exist_ok=True)
    open(f"{root}/.opp_env/postdownload.sha", "w").writelines(sorted(lines))


def w(root, rel, text):
    p = os.path.join(root, rel)
    os.makedirs(os.path.dirname(p), exist_ok=True)
    open(p, "w").write(text)


def src_env(variant):
    t, ci, ev, env = sandbox()
    roots = {k: os.path.join(env["WS"], f"{k}-x") for k in ("omnetpp", "inet", "simu5g")}
    for k, r in roots.items():
        w(r, "src/a.cc", "a\n")
        w(r, "Makefile", "m\n")
        w(r, "ide/x.so", "ide")
        manifest(r)
    repo = env["REPO"]
    w(repo, "src/nasctime/m2/x.cc", "x\n")
    w(repo, "src/nasctime/m2/.gitignore", "Makefile\nout/\n*.so\n")
    subprocess.run(["bash", "-c", f"cd {repo} && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm i"], check=True)
    w(roots["omnetpp"], "out/clang-release/a.o", "o")
    w(roots["omnetpp"], "lib/liboppsim.so", "so")
    w(roots["inet"], "src/inet/features.h", "f")
    w(roots["simu5g"], "Makefile", "regenerated\n")
    w(repo, "src/nasctime/m2/libnasctime_m2.so", "so")
    w(repo, "src/nasctime/m2/Makefile", "mk")
    if variant == "edit-source":
        w(roots["inet"], "src/a.cc", "edited\n")
    elif variant == "remove":
        os.remove(os.path.join(roots["simu5g"], "src/a.cc"))
    elif variant == "nasctime-tracked":
        w(repo, "src/nasctime/m2/x.cc", "edited\n")
    open(f"{ev}/probe.txt", "w").write("".join(f"{k}_root: {v}\n" for k, v in roots.items()))
    return t, env, ev


for variant, want in (("build-only", 0), ("edit-source", 1), ("remove", 1), ("nasctime-tracked", 1)):
    t, env, ev = src_env(variant)
    r = run([sys.executable, "-I", os.path.join(PYD, "srcchanges.py")], env)
    summ = open(f"{ev}/source-changes-summary.txt").read() if os.path.exists(f"{ev}/source-changes-summary.txt") else ""
    check(f"T8 source changes [{variant}] -> {'fail' if want else 'pass'}", (r.returncode != 0) == bool(want), r.stdout + r.stderr[-400:])
    if variant == "build-only":
        check("T8 regenerated Makefile classified build-generated, ignored outputs counted",
              "build-generated" in open(f"{ev}/source-changes.tsv").read() and "unexpected_upstream_source_changes: 0" in summ
              and "ignored_build_outputs_in_m2: 2" in summ, summ)
    shutil.rmtree(t)

# ======================================================================= T9 Nix store classifier
t = tempfile.mkdtemp()
src, dst = f"{t}/pi.json", f"{t}/sum.txt"
NS = os.path.join(PYD, "nixstore.py")
open(src, "w").write(json.dumps({"/nix/store/a-user-environment": {"ultimate": True}, "/nix/store/b-run_command-env": {"ultimate": True},
                                 "/nix/store/c-nixpkgs-source": {"ultimate": True}, "/nix/store/d-qtbase-6.11.0": {"narSize": 9}}))
subprocess.run([sys.executable, "-I", NS, src, dst, "ok"], check=True, capture_output=True)
s = open(dst).read()
check("T9 profile / devshell / source classified expected; no package builds", "expected-profile: user-environment" in s
      and "expected-devshell" in s and "expected-source" in s and "LOCAL-PACKAGE-BUILD" not in s, s)
open(src, "w").write(json.dumps({"/nix/store/e-qtbase-6.11.0": {"ultimate": True}, "/nix/store/f-omnetpp-6.5.0": {"ultimate": True}}))
subprocess.run([sys.executable, "-I", NS, src, dst, "ok"], check=True, capture_output=True)
s = open(dst).read()
check("T9 package build and framework build distinguished", "LOCAL-PACKAGE-BUILD: qtbase-6.11.0" in s and "FRAMEWORK-BUILD: omnetpp-6.5.0" in s, s)
subprocess.run([sys.executable, "-I", NS, src, dst, "failed"], check=True, capture_output=True)
check("T9 path-info failure -> NOT AVAILABLE", "NOT AVAILABLE" in open(dst).read())
shutil.rmtree(t)

# ======================================================================= T11 in-session link probe on this host (optional)
RPROBE = os.path.join(SESSION, "runtime-probe.sh")
RG = load("runtime_gates")
if not HOST_PROBE:
    print("NOT RUN T11 host link probe (host dependent; run with --host-probe on a host without libc++ development files)")
else:
    t = tempfile.mkdtemp(prefix="t1rp-")
    fake = os.path.join(t, "fakebin")
    os.makedirs(fake)
    open(f"{fake}/patchelf", "w").write(f"#!/bin/sh\necho {INTERP}\n")
    os.chmod(f"{fake}/patchelf", 0o755)
    r = run(["bash", RPROBE, f"{t}/out.txt", "local", f"{t}/w"], clean_env(PATH=f"{fake}:" + os.environ["PATH"]), timeout=180)
    pt = open(f"{t}/out.txt").read()
    check("T11 probe script runs, records search dirs, driver -L, three probes", r.returncode == 0 and "search-dirs libraries:" in pt
          and "driver-L -L" in pt and "probe default rc: 0" in pt and "probe stdcxx rc: 0" in pt, pt[-1500:])
    lines = pt.splitlines()
    check("T11 classification of this host is A or B, never INVALID", RG.classify(lines) in ("A", "B"), RG.classify(lines))
    ok, out = RG.gates(lines, "B")
    check("T11 libstdc++ of this host is not from /nix/store -> R-4 FAIL", "r4_result: FAIL" in out, out)
    shutil.rmtree(t)


# ======================================================================= T12 C-4 runtime gates (synthetic probe outputs)
def probe_text(libcxx_ok, std="/nix/store/chqq8mpmpyfi9kgsngya71akv5xicn03-gcc-15.2.0-lib/lib/libstdc++.so.6",
               cxx_path="/usr/lib/x86_64-linux-gnu/libc++.so", neg="ld.lld: error: unable to find library -lc++"):
    L = ["phase: x", "search-dirs libraries: =/nix/store/a:/usr/lib/x86_64-linux-gnu"]
    if libcxx_ok:
        L += ["probe libcxx rc: 0", f"probe libcxx trace: {cxx_path}", "probe libcxx trace: /usr/lib/x86_64-linux-gnu/libc++.so.1",
              "probe libcxx needed: libc++.so.1,libstdc++.so.6"]
    else:
        L += ["probe libcxx rc: 1", f"probe libcxx trace: {neg}"]
    for n in ("default", "stdcxx"):
        L += [f"probe {n} rc: 0", f"probe {n} needed: libstdc++.so.6,libm.so.6,libgcc_s.so.1,libc.so.6",
              f"probe {n} runpath: /home/runner/work/_temp/tier1/exec/outputs/out/lib:/nix/store/x-gcc-15.2.0-lib/lib",
              f"probe {n} resolved: \tlibstdc++.so.6 => {std} (0x0000)", f"probe {n} resolved: \tlibc.so.6 => /nix/store/g-glibc-2.42/lib/libc.so.6 (0x0)"]
    return "\n".join(L) + "\n"


for label, text, case, want3, want4 in (
        ("clean host (case B)", probe_text(False), "B", "PASS", "PASS"),
        ("libc++ linkable (case A before correction)", probe_text(True), "A", "FAIL", "PASS"),
        ("libstdc++ from the host", probe_text(False, std="/usr/lib/x86_64-linux-gnu/libstdc++.so.6"), "B", "PASS", "FAIL"),
        ("libc via outputs/out/lib RUNPATH", probe_text(False).replace("libc.so.6 => /nix/store/g-glibc-2.42/lib/libc.so.6",
                                                                       "libc.so.6 => /home/runner/work/_temp/tier1/exec/outputs/out/lib/libc.so.6"), "B", "PASS", "FAIL"),
        ("other link error (fail closed)", probe_text(False, neg="ld.lld: error: undefined symbol: main"), "INVALID", "FAIL", "PASS"),
        ("probe output missing", "phase: x\n", "INVALID", "FAIL", "FAIL")):
    lines = text.splitlines()
    ok, out = RG.gates(lines, "B")
    check(f"T12 runtime gates [{label}] -> case {case}, R-3 {want3}, R-4 {want4}",
          RG.classify(lines) == case and f"r3_result: {want3}" in out and f"r4_result: {want4}" in out, (RG.classify(lines), out))
t = tempfile.mkdtemp()
open(f"{t}/p.txt", "w").write(probe_text(False))
r = run([sys.executable, "-I", os.path.join(PYD, "runtime_gates.py"), "runpath", f"{t}/p.txt", "before", f"{t}/obs.txt"], clean_env())
check("T12 RUNPATH observation of probe binaries recorded (exists=no)", r.returncode == 0
      and open(f"{t}/obs.txt").read().count("outputs/out/lib exists=no") == 2, r.stdout)
r = run([sys.executable, "-I", os.path.join(PYD, "runtime_gates.py"), "case", f"{t}/p.txt"], clean_env())
check("T12 CLI: case B exit 0", r.returncode == 0 and r.stdout.strip() == "B")
open(f"{t}/p.txt", "w").write("probe libcxx rc: 2\nprobe libcxx trace: clang++: error: linker command failed\n")
r = run([sys.executable, "-I", os.path.join(PYD, "runtime_gates.py"), "case", f"{t}/p.txt"], clean_env())
check("T12 CLI: unexpected probe failure -> INVALID, exit 1", r.returncode == 1 and r.stdout.strip() == "INVALID")
shutil.rmtree(t)

# ======================================================================= T13 C-4 provenance (corrected R-1) regression suite
# REAL hosted evidence: the fixture is the runtime-probe-before.txt of E2b.3 job 134465683528 (see fixtures/README.md).
# MOCKED: filesystem trees (provenance.FS with a root) and dpkg databases (injected lookup function). Production calls
# provenance.main(), which always uses the real filesystem and the real `dpkg -S`.
PV = load("provenance")
FIXTURE = os.path.join(HERE, "fixtures", "e2b3-runtime-probe-before.txt")
check("T13 real E2b.3 fixture present and unmodified",
      hashlib.sha256(open(FIXTURE, "rb").read()).hexdigest() == "b45f58810ef7cd64749cd7d1b69971723a8e0255a6ca8e47e5ad6943db3265f2")
REAL = open(FIXTURE).read()
check("T13 real fixture contains the observed versioned-only trace",
      all(f"probe libcxx trace: {p}" in REAL for p in ("/lib/x86_64-linux-gnu/libc++.so.1", "/lib/x86_64-linux-gnu/libc++abi.so",
                                                        "/lib/x86_64-linux-gnu/libunwind.so")) and "probe libcxx trace: /lib/x86_64-linux-gnu/libc++.so\n" not in REAL)
check("T13 real fixture classifies as case A", RG.classify(REAL.splitlines()) == "A")


def mk(root, rel, content=None, link=None):
    p = os.path.join(root, rel.lstrip("/"))
    os.makedirs(os.path.dirname(p), exist_ok=True)
    if link is not None:
        os.symlink(link, p)
    else:
        open(p, "wb").write(content if isinstance(content, bytes) else content.encode())


ELF = b"\x7fELF" + b"\0" * 60


def ubuntu_tree(root, layout="script"):
    """MOCKED Ubuntu 22.04 merged-/usr layout of the LLVM 14 libc++ packages (lib -> usr/lib)."""
    os.makedirs(os.path.join(root, "usr/lib/x86_64-linux-gnu"))
    os.symlink("usr/lib", os.path.join(root, "lib"))
    d = "/usr/lib/x86_64-linux-gnu"
    mk(root, f"{d}/libc++.so.1.0", ELF)
    mk(root, f"{d}/libc++.so.1", link="libc++.so.1.0")
    mk(root, f"{d}/libc++abi.so.1.0", ELF)
    mk(root, f"{d}/libc++abi.so.1", link="libc++abi.so.1.0")
    mk(root, f"{d}/libunwind.so.1.0", ELF)
    mk(root, f"{d}/libunwind.so.1", link="libunwind.so.1.0")
    mk(root, f"{d}/libunwind.so", link="libunwind.so.1")
    if layout == "script":
        mk(root, f"{d}/libc++.so", "INPUT(libc++.so.1 -lunwind -lc++abi)\n")
        mk(root, f"{d}/libc++abi.so", link="libc++abi.so.1")
    elif layout == "llvm-dir":
        mk(root, "/usr/lib/llvm-14/lib/libc++.so", "INPUT(libc++.so.1 -lunwind -lc++abi)\n")
        mk(root, "/usr/lib/llvm-14/lib/libc++.so.1", link="../../x86_64-linux-gnu/libc++.so.1.0")
        mk(root, f"{d}/libc++.so", link="../llvm-14/lib/libc++.so")
        mk(root, f"{d}/libc++abi.so", link="libc++abi.so.1")
    elif layout == "symlink-elf":
        mk(root, f"{d}/libc++.so", link="libc++.so.1")
        mk(root, f"{d}/libc++abi.so", link="libc++abi.so.1")
    elif layout == "wrong-target":
        mk(root, f"{d}/libc++.so.2", ELF)
        mk(root, f"{d}/libc++.so", "INPUT(libc++.so.2 -lunwind -lc++abi)\n")
        mk(root, f"{d}/libc++abi.so", link="libc++abi.so.1")


UBUNTU_DPKG = {  # MOCKED dpkg database: Debian records the /usr spelling only
    "/usr/lib/x86_64-linux-gnu/libc++.so.1": "libc++1-14:amd64", "/usr/lib/x86_64-linux-gnu/libc++.so.1.0": "libc++1-14:amd64",
    "/usr/lib/x86_64-linux-gnu/libc++.so": "libc++-14-dev:amd64",
    "/usr/lib/x86_64-linux-gnu/libc++abi.so.1": "libc++abi1-14:amd64", "/usr/lib/x86_64-linux-gnu/libc++abi.so.1.0": "libc++abi1-14:amd64",
    "/usr/lib/x86_64-linux-gnu/libc++abi.so": "libc++abi-14-dev:amd64",
    "/usr/lib/x86_64-linux-gnu/libunwind.so": "libunwind-14-dev:amd64", "/usr/lib/x86_64-linux-gnu/libunwind.so.1": "libunwind-14:amd64",
}
LLVM_DIR_DPKG = dict(UBUNTU_DPKG, **{"/usr/lib/x86_64-linux-gnu/libc++.so": "libc++-dev:amd64",
                                     "/usr/lib/llvm-14/lib/libc++.so": "libc++-14-dev:amd64",
                                     "/usr/lib/llvm-14/lib/libc++.so.1": "libc++1-14:amd64"})


def r1(text, tree=None, db=None):
    t = tempfile.mkdtemp(prefix="r1-")
    root = ""
    if tree:
        root = os.path.join(t, "root")
        os.makedirs(root)
        ubuntu_tree(root, tree)
    else:
        root = os.path.join(t, "empty")     # MOCKED: an empty filesystem (no evidence at all)
        os.makedirs(root)
    db = db or {}
    ok, out, problems, cands = PV.analyse(text.splitlines(), PV.FS(root), lambda p: (p in db, f"{db[p]}: {p}\n" if p in db else ""))
    k = {}
    for l in out:
        if ": " in l:
            a, b = l.split(": ", 1)
            k.setdefault(a, b)
    shutil.rmtree(t)
    return ok, "\n".join(out), k, cands


ok, h, k, cands = r1(REAL, "script", UBUNTU_DPKG)
check("T13 real trace replay [script layout]: PASS, relationship verified, aliases resolved, runtime/dev owners separate",
      ok and k.get("r1_result") == "PASS" and k.get("selected_libcxx_runtime") == "/lib/x86_64-linux-gnu/libc++.so.1"
      and k.get("selected_libcxx_canonical") == "/usr/lib/x86_64-linux-gnu/libc++.so.1.0"
      and k.get("unversioned_linker_entry") == "/lib/x86_64-linux-gnu/libc++.so" and k.get("unversioned_entry_kind") == "linker-script"
      and k.get("entry_relationship", "").startswith("verified") and k.get("runtime_owners") == "libc++1-14:amd64"
      and k.get("development_owners") == "libc++-14-dev:amd64" and k.get("libcxxabi_development_owners") == "libc++abi-14-dev:amd64"
      and cands == ["libc++-14-dev:amd64", "libc++abi-14-dev:amd64"]
      and "/lib/x86_64-linux-gnu/libc++.so.1 -> miss" in h and "/usr/lib/x86_64-linux-gnu/libc++.so.1 -> hit" in h, h)
check("T13 libunwind recorded, never a candidate; runtime package never a candidate",
      "libunwind-14-dev" not in "".join(cands) and "libc++1-14" not in "".join(cands) and "libunwind_owners: libunwind-14-dev:amd64" in h, h)
REAL_R1_OUTPUT = h + "\n"
ok, h, k, cands = r1(REAL, "llvm-dir", LLVM_DIR_DPKG)
check("T13 real trace replay [llvm-dir layout]: both dev owners, runtime excluded",
      ok and k.get("unversioned_entry_final") == "/usr/lib/llvm-14/lib/libc++.so"
      and k.get("development_owners") == "libc++-14-dev:amd64, libc++-dev:amd64" and k.get("runtime_owners") == "libc++1-14:amd64"
      and set(cands) == {"libc++-14-dev:amd64", "libc++-dev:amd64", "libc++abi-14-dev:amd64"}, h)
ok, h, k, cands = r1(REAL, "symlink-elf", UBUNTU_DPKG)
check("T13 real trace replay [unversioned symlink -> runtime ELF]: dev owner = symlink owner only",
      ok and k.get("unversioned_entry_kind") == "elf" and k.get("development_owners") == "libc++-14-dev:amd64" and "libc++1-14:amd64" not in cands, h)
ok, h, k, cands = r1(REAL, None, {})
check("T13 real trace without filesystem/ownership evidence -> FAIL, no candidates", not ok and k.get("r1_result") == "FAIL" and not cands, h[-600:])
ok, h, k, cands = r1(REAL, "script", {})
check("T13 missing ownership -> FAIL", not ok and "ownership not established" in h and not cands, h[-500:])
db = dict(UBUNTU_DPKG, **{"/usr/lib/x86_64-linux-gnu/libc++.so": "libc++1-14:amd64"})
ok, h, k, cands = r1(REAL, "script", db)
check("T13 unversioned entry owned by the runtime package -> FAIL", not ok and not cands, h[-500:])
db = dict(UBUNTU_DPKG, **{"/usr/lib/x86_64-linux-gnu/libc++.so": "clang-14:amd64"})
ok, h, k, cands = r1(REAL, "script", db)
check("T13 unexpected development owner -> FAIL", not ok and "unexpected development owners" in h and not cands, h[-500:])
ok, h, k, cands = r1(REAL, "wrong-target", UBUNTU_DPKG)
check("T13 linker entry leads elsewhere (libc++.so.2) -> FAIL", not ok and k.get("entry_relationship") == "NOT verified", h[-500:])
store = REAL.replace("probe libcxx trace: /lib/x86_64-linux-gnu/libc++.so.1", "probe libcxx trace: /nix/store/zzz-libcxx-21/lib/libc++.so.1")
ok, h, k, cands = r1(store, "script", UBUNTU_DPKG)
check("T13 libc++ selected from /nix/store -> FAIL (fail closed)", not ok and not cands, h[-500:])
unrel = "\n".join(l for l in REAL.splitlines() if not l.startswith("probe libcxx trace: /lib/")) + "\nprobe libcxx trace: /usr/lib/x86_64-linux-gnu/libz.so\n"
ok, h, k, cands = r1(unrel, "script", UBUNTU_DPKG)
check("T13 unrelated host library only -> FAIL", not ok and "no libc++ library in the linker trace" in h
      and "libz.so" in k.get("unrelated_host_paths_in_trace", ""), h[-500:])
unv = REAL.replace("probe libcxx trace: /lib/x86_64-linux-gnu/libc++.so.1", "probe libcxx trace: /usr/lib/x86_64-linux-gnu/libc++.so")
ok, h, k, cands = r1(unv, "symlink-elf", UBUNTU_DPKG)
check("T13 unversioned entry traced directly -> PASS with entry = traced path", ok and k.get("unversioned_linker_entry") == "/usr/lib/x86_64-linux-gnu/libc++.so", h[-700:])
ok, h, k, cands = r1(REAL.replace("probe libcxx rc: 0", "probe libcxx rc: 1"), "script", UBUNTU_DPKG)
check("T13 libc++ probe rc != 0 -> FAIL", not ok, h[-300:])
t = tempfile.mkdtemp()
os.makedirs(f"{t}/root/usr/lib")
os.symlink("/etc", f"{t}/root/usr/lib/escape")
try:
    PV.FS(f"{t}/root").canon("/usr/lib/escape/passwd")
    escaped = True
except SystemExit:
    escaped = False
check("T13 FS refuses a path resolving outside the mocked root", not escaped)
shutil.rmtree(t)


# ======================================================================= T14 controlled removal (steps/hostfix.sh with shims)
def hostfix_env(sim_lines, removal_effect="exact"):
    t, ci, ev, env = sandbox()
    gp = start_guard(ev, env)
    inv = os.path.join(t, "inventory.tsv")
    base = {"bash": "5.1", "clang-14": "1:14.0", "libc++-14-dev": "1:14.0", "libc++abi-14-dev": "1:14.0", "libc++-dev": "1:14.0-55",
            "libc++abi-dev": "1:14.0-55", "libc++1-14": "1:14.0", "libunwind-14": "1:14.0", "zlib1g": "1.2"}
    open(inv, "w").write("".join(f"{p}\t{v}\tinstall ok installed\n" for p, v in sorted(base.items())))
    fb = os.path.join(t, "shims")
    os.makedirs(fb)
    open(f"{fb}/dpkg-query", "w").write(f'''#!/bin/bash
if [ "$1" = -W ] && [ "$2" = -f ] && [ "$3" = '${{Status}}' ]; then
  awk -F'\\t' -v p="$4" '$1==p {{print $3; f=1}} END {{exit f?0:1}}' "{inv}" | tr -d '\\n'; exit ${{PIPESTATUS[0]}}
fi
cat "{inv}"
''')
    extra = "" if removal_effect != "extra" else 'sed -i "s/^zlib1g\\t1.2\\tinstall ok installed/zlib1g\\t1.2\\tdeinstall ok config-files/" ' + repr(inv) + ';'
    open(f"{fb}/apt-get", "w").write(f'''#!/bin/bash
if [ "$1" = -s ]; then printf '%s\\n' {" ".join(repr(l) for l in sim_lines)}; exit 0; fi
while [ "$1" != -y ]; do shift; done; shift
for p in "$@"; do
  {extra}
  awk -F'\\t' -v OFS='\\t' -v p="$p" '$1==p && $3=="install ok installed" {{$3="deinstall ok config-files"}} {{print}}' "{inv}" > "{inv}.new" && mv "{inv}.new" "{inv}"
done
echo "Removing $*"
''')
    open(f"{fb}/sudo", "w").write('#!/bin/bash\nwhile [[ "$1" == *=* ]]; do export "$1"; shift; done\nexec "$@"\n')
    for x in ("dpkg-query", "apt-get", "sudo"):
        os.chmod(f"{fb}/{x}", 0o755)
    env = dict(env, PATH=f"{fb}:" + os.environ["PATH"])
    subprocess.run(["bash", "-c", f'"{fb}/dpkg-query" -W -f x | sort > "{ev}/host-packages-before.tsv"'], env=env, check=True)
    open(f"{ev}/host-libcxx.txt", "w").write("removal_candidate: libc++-14-dev:amd64\nremoval_candidate: libc++-dev:amd64\n"
                                             "removal_candidate: libc++abi-14-dev:amd64\nremoval_candidate: libc++abi-dev:amd64\nr1_result: PASS\n")
    return t, ci, ev, env, gp


HF = os.path.join(STEPS, "hostfix.sh")
GOOD_SIM = ["NOTE: This is only a simulation!", "Remv libc++-dev [1:14.0-55]", "Remv libc++-14-dev [1:14.0]",
            "Remv libc++abi-dev [1:14.0-55]", "Remv libc++abi-14-dev [1:14.0]"]
for label, sim, effect, want in (("exact transaction", GOOD_SIM, "exact", 0),
                                 ("unrelated removal (clang-14)", GOOD_SIM + ["Remv clang-14 [1:14.0]"], "exact", 1),
                                 ("install line", GOOD_SIM + ["Inst libfoo (1.0)"], "exact", 1),
                                 ("inventory changed beyond transaction", GOOD_SIM, "extra", 1)):
    t, ci, ev, env, gp = hostfix_env(sim, effect)
    r = run(["bash", HF], env, timeout=60)
    removed_any = os.path.exists(f"{ev}/apt-remove.txt")
    tx = open(f"{ev}/apt-remove-transaction.txt").read() if os.path.exists(f"{ev}/apt-remove-transaction.txt") else ""
    d = open(f"{ev}/host-packages.diff").read() if os.path.exists(f"{ev}/host-packages.diff") else ""
    good = (r.returncode == 0) == (want == 0)
    if label in ("unrelated removal (clang-14)", "install line"):
        good = good and not removed_any and "transaction_check: FAIL" in tx
    if label == "exact transaction":
        good = good and "r2_result: PASS" in d and "changed_packages: 4" in d and "removal: libc++-14-dev" in tx
    if label == "inventory changed beyond transaction":
        good = good and "r2_result: FAIL" in d
    check(f"T14 hostfix [{label}] -> {'pass' if want == 0 else 'reject'}", good, r.stdout[-700:] + r.stderr[-400:] + tx + d)
    stop_guard(ev, gp)
    shutil.rmtree(t)
t, ci, ev, env, gp = hostfix_env(GOOD_SIM)
open(f"{ev}/host-libcxx.txt", "w").write("removal_candidate: clang-14:amd64\n")
r = run(["bash", HF], env, timeout=60)
check("T14 hostfix rejects a non-libc++ owner before any apt call", r.returncode == 1 and not os.path.exists(f"{ev}/apt-remove-simulation.txt"), r.stdout)
stop_guard(ev, gp)
shutil.rmtree(t)
t, ci, ev, env, gp = hostfix_env(["NOTE: This is only a simulation!", "Remv libc++-dev [1:14.0-55~exp2]", "Remv libc++-14-dev [1:14.0.0-1ubuntu1.1]",
                                  "Remv libc++abi-dev [1:14.0-55~exp2]", "Remv libc++abi-14-dev [1:14.0.0-1ubuntu1.1]"])
open(f"{ev}/host-libcxx.txt", "w").write(REAL_R1_OUTPUT)
r = run(["bash", HF], env, timeout=60)
prop = open(f"{ev}/apt-remove-proposed.txt").read().split()
d = open(f"{ev}/host-packages.diff").read() if os.path.exists(f"{ev}/host-packages.diff") else ""
check("T14 hostfix consumes the provenance output of the real-trace replay: verified dev owners + installed metapackages",
      r.returncode == 0 and prop == ["libc++-14-dev", "libc++-dev", "libc++abi-14-dev", "libc++abi-dev"] and "r2_result: PASS" in d, r.stdout[-800:] + d)
stop_guard(ev, gp)
shutil.rmtree(t)

# ======================================================================= T15 C-5 SYS_LIBS ordered-token gate
SL = load("sys_libs")
VM = PINS["VM_SYS_LIBS"]
for label, sl, want in (("identical to the VM", VM, True),
                        ("whitespace-only difference (double space, tab)", VM.replace(" -ldl", "  -ldl").replace(" -lm", "\t-lm"), True),
                        ("tokens reordered", VM.replace("-ldl -lm", "-lm -ldl"), False),
                        ("extra token", VM + " -lz", False),
                        ("missing token", VM.replace(" -lelf", ""), False),
                        ("libstdc++ with different extras", "-lstdc++ -lpython3.13 -ldl -lm", False),
                        ("contains -lc++", VM.replace("-lstdc++", "-lc++"), False),
                        ("both runtimes", "-lc++ " + VM, False),
                        ("only -lstdc++fs (not the exact token)", VM.replace("-lstdc++", "-lstdc++fs"), False),
                        ("different elfutils store path", VM.replace("qhmqdg27", "aaaaaaaa"), False),
                        ("SYS_LIBS absent", None, False)):
    ok, out = SL.evaluate(sl, VM)
    check(f"T15 SYS_LIBS [{label}] -> {'PASS' if want else 'FAIL'}", ok == want and f"r5_result: {'PASS' if want else 'FAIL'}" in out, out)
t = tempfile.mkdtemp()
open(f"{t}/Makefile.inc", "w").write(f"CXX = ccache clang++\nSYS_LIBS = {VM.replace(' -ldl', '  -ldl')}\nLIBS = \n")
r = run([sys.executable, "-I", os.path.join(PYD, "sys_libs.py"), f"{t}/Makefile.inc", VM, f"{t}/out.txt"], clean_env())
s = open(f"{t}/out.txt").read()
check("T15 CLI on a Makefile.inc with the E2b.3-R1 double space -> PASS, exact string differs",
      r.returncode == 0 and "ordered_token_match_vm: yes" in s and "exact_string_match_vm: no" in s, s)
shutil.rmtree(t)

# ======================================================================= T16 trigger selection (decide.py, C3)
DC = load("decide")
t = tempfile.mkdtemp(prefix="t1dec-")
g = f"cd {t} && git -c user.name=t -c user.email=t@t"
subprocess.run(["bash", "-c", f"cd {t} && git init -q -b main && mkdir -p docs src/x simulations/m2/check ci/tier1 && echo a > docs/a.md && "
                f"echo s > src/x/s.cc && echo t > simulations/m2/check/t.py && echo n > simulations/m2/n.ned && echo r > README.md && "
                f"git add -A && {g.split('&&')[1]} commit -qm base"], check=True)
BASE = subprocess.run(["git", "-C", t, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def head_with(cmd):
    subprocess.run(["bash", "-c", f"cd {t} && git checkout -q -B h {BASE} && {cmd} && git add -A && "
                    f"git -c user.name=t -c user.email=t@t commit -qm h"], check=True, capture_output=True)
    return subprocess.run(["git", "-C", t, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip()


def ev_(action, head, draft=False, labels=(), label=None, changed=1, base=BASE):
    e = {"action": action, "pull_request": {"draft": draft, "labels": [{"name": n} for n in labels], "changed_files": changed,
                                             "base": {"sha": base}, "head": {"sha": head}}}
    if label:
        e["label"] = {"name": label}
    return e


H_DOC = head_with("echo b >> docs/a.md")
H_SRC = head_with("echo b >> src/x/s.cc")
H_REN_OUT = head_with("git mv src/x/s.cc docs/s.cc")          # relevant path renamed out of scope
H_DEL = head_with("git rm -q simulations/m2/check/t.py")      # relevant path deleted
H_NED = head_with("echo m >> simulations/m2/n.ned")
H_T1 = head_with("echo x > ci/tier1/new.txt")
for label, e, want in (("opened, docs only", ev_("opened", H_DOC), False),
                       ("opened, src change", ev_("opened", H_SRC), True),
                       ("synchronize, relevant file renamed out of scope (old path counts)", ev_("synchronize", H_REN_OUT), True),
                       ("synchronize, relevant file deleted", ev_("synchronize", H_DEL), True),
                       ("reopened, NED change", ev_("reopened", H_NED), True),
                       ("opened, ci/tier1 change", ev_("opened", H_T1), True),
                       ("draft with a relevant change, no label", ev_("opened", H_SRC, draft=True), False),
                       ("draft carrying the override label", ev_("synchronize", H_DOC, draft=True, labels=["tier1:run"]), True),
                       ("ready_for_review, docs only", ev_("ready_for_review", H_DOC), False),
                       ("labeled tier1:run on a docs-only draft", ev_("labeled", H_DOC, draft=True, labels=["tier1:run"], label="tier1:run"), True),
                       ("labeled with an unrelated label on a relevant PR", ev_("labeled", H_SRC, labels=["tier1:run", "docs"], label="docs"), False)):
    run_, reason = DC.decide(e, t)
    check(f"T16 decide [{label}] -> {'run' if want else 'skip'}", run_ == want, reason)
for label, e in (("head commit unavailable", ev_("synchronize", "f" * 40)),
                 ("base commit missing", ev_("opened", H_SRC, base=None)),
                 ("empty change set although GitHub reports changed files", ev_("opened", BASE, changed=3)),
                 ("unexpected action", ev_("closed", H_SRC)),
                 ("no pull_request in the event", {"action": "opened"})):
    try:
        DC.decide(e, t)
        raised = False
    except DC.Undetermined:
        raised = True
    check(f"T16 decide fails closed [{label}]", raised)
json.dump(ev_("opened", "f" * 40), open(f"{t}/event.json", "w"))
r = run([sys.executable, "-I", os.path.join(PYD, "decide.py"), f"{t}/event.json", t, f"{t}/out.txt"], clean_env())
check("T16 CLI: undetermined change set -> job fails, no output written", r.returncode == 1 and not os.path.exists(f"{t}/out.txt"), r.stdout)
json.dump(ev_("opened", H_SRC), open(f"{t}/event.json", "w"))
r = run([sys.executable, "-I", os.path.join(PYD, "decide.py"), f"{t}/event.json", t, f"{t}/out.txt"], clean_env())
check("T16 CLI: outputs run=true and a single-line reason", r.returncode == 0 and open(f"{t}/out.txt").read().startswith("run=true\nreason="))
shutil.rmtree(t)

# ======================================================================= T17 strict simulator audit shim (C1, C2)
BASEQ = ["-u", "Cmdenv", "-f", "m2s72s5.ini", "-c", "M2S72-E0vN-q0-one0-n2-f1", "-r", "0", "-q", "runconfig"]
A2V1Q = ["-u", "Cmdenv", "-f", "m2s72a2v.ini", "-c", "M2S72-E0vN-q0-one0-n2-f1_A2V1", "-r", "0", "-q", "runconfig"]


def audit_env(resolution="/nix/store/x-glibc/lib/libc.so.6"):
    """MOCKED: a real-OMNeT++ root (shell-script opp_run that echoes its arguments), a loader whose --list prints the
    given resolution, and a repository/suite-tmp layout. The shim itself is the production file."""
    t = tempfile.mkdtemp(prefix="t1aud-")
    real = f"{t}/omnetpp"
    os.makedirs(f"{real}/bin")
    os.makedirs(f"{real}/lib")
    open(f"{real}/setenv", "w").write(f'export PATH="{real}/bin:$PATH"\nexport REAL_SETENV_ARGS="$*"\n')
    open(f"{real}/bin/opp_run", "w").write('#!/bin/sh\nprintf "dump:%s\\n" "$*"\n[ "$*" = "-v" ] && exit 0\nexit ${FAKE_RC:-0}\n')
    os.chmod(f"{real}/bin/opp_run", 0o755)
    ld = f"{t}/ld.so"
    open(ld, "w").write(f'#!/bin/sh\n[ "$1" = --list ] || exit 2\nprintf "\\tlibc.so.6 => {resolution} (0x00007f)\\n"\n')
    os.chmod(ld, 0o755)
    repo, tmproot, audit = f"{t}/repo", f"{t}/suite-tmp", f"{t}/audit"
    for d in (f"{repo}/simulations/m2", f"{tmproot}/tmpab12/repo/simulations/m2", f"{audit}/bin", f"{t}/elsewhere"):
        os.makedirs(d)
    shutil.copy(os.path.join(WRAP, "opp_run-audit.sh"), f"{audit}/bin/opp_run")
    os.chmod(f"{audit}/bin/opp_run", 0o755)
    shutil.copy(os.path.join(WRAP, "setenv-audit.sh"), f"{audit}/setenv")
    log = f"{t}/audit.tsv"
    open(log, "w").write("seq\tutc\tdecision\tkind\tcwd\targv\texit\tdetail\n")
    sha = hashlib.sha256(open(f"{real}/bin/opp_run", "rb").read()).hexdigest()
    conf = (f"AUDIT_REAL={real}/bin/opp_run\nAUDIT_REAL_SHA256={sha}\nAUDIT_REAL_ROOT={real}\nAUDIT_INTERP={ld}\n"
            f"AUDIT_PROJECT_LIB={real}/lib\nAUDIT_REPO={repo}\nAUDIT_TMPROOT={tmproot}\nAUDIT_LOG={log}\n"
            f"AUDIT_RELATIVE_RUNPATH=.\nAUDIT_ABSENT_RUNPATH={t}/exec/outputs/out/lib\n")
    open(f"{audit}/audit.conf", "w").write(conf)
    return t, real, repo, tmproot, audit, log


def shim(audit, cwd, args, **kw):
    return subprocess.run([f"{audit}/bin/opp_run", *args], cwd=cwd, capture_output=True, text=True, env=clean_env(**kw), timeout=30)


t, real, repo, tmproot, audit, log = audit_env()
M2R, M2C = f"{repo}/simulations/m2", f"{tmproot}/tmpab12/repo/simulations/m2"
r = shim(audit, M2R, BASEQ)
check("T17 approved base query from the repository: forwarded, output byte-identical, nothing added",
      r.returncode == 0 and r.stdout == "dump:" + " ".join(BASEQ) + "\n" and r.stderr == "", r.stdout + r.stderr)
r = shim(audit, M2C, A2V1Q)
check("T17 approved A2-V1 query from a suite clone: forwarded", r.returncode == 0 and r.stdout.startswith("dump:-u Cmdenv -f m2s72a2v.ini"))
r = shim(audit, M2R, BASEQ, FAKE_RC="3")
check("T17 exit status of the real query is propagated", r.returncode == 3)
r = shim(audit, M2R, ["-v"])
check("T17 bare identity query forwarded", r.returncode == 0)
bad_vectors = {
    "simulation (no query)": ["-u", "Cmdenv", "-f", "m2s72a2v.ini", "-c", "M2S72-E0vN-q0-one0-n2-f1_A2V1", "-r", "0"],
    "query plus a library load": BASEQ + ["-l", "/x/libnasctime_m2.so"],
    "duplicate query": BASEQ + ["-q", "runconfig"],
    "duplicate mode": ["-u", "Cmdenv"] + BASEQ,
    "Qtenv instead of Cmdenv": ["-u", "Qtenv"] + BASEQ[2:],
    "other configuration": BASEQ[:5] + ["M2S72-E1"] + BASEQ[6:],
    "other run number": BASEQ[:7] + ["1"] + BASEQ[8:],
    "other query (sectioninheritance)": BASEQ[:9] + ["sectioninheritance"],
    "reordered arguments": BASEQ[2:4] + BASEQ[:2] + BASEQ[4:],
    "-v with extra argument": ["-v", "-x"],
    "no arguments": [],
    "separator spoof (one argument containing the joined vector)": ["\x1f".join(BASEQ)],
    "result directory option": BASEQ + ["--result-dir=/mnt/nasctime-results"],
}
for label, args in bad_vectors.items():
    r = shim(audit, M2R, args)
    check(f"T17 refused [{label}] -> 97, nothing forwarded", r.returncode == 97 and "dump:" not in r.stdout, r.stdout + r.stderr)
r = shim(audit, f"{t}/elsewhere", BASEQ)
check("T17 refused: working directory outside the approved ones", r.returncode == 97 and "working directory" in r.stderr)
os.makedirs(f"{tmproot}/a/b/repo/simulations/m2")
r = shim(audit, f"{tmproot}/a/b/repo/simulations/m2", BASEQ)
check("T17 refused: suite clone at an unexpected depth", r.returncode == 97)
open(f"{M2R}/libstdc++.so.6", "w").write("planted")
r = shim(audit, M2R, BASEQ)
check("T17 refused: shared library in the working directory reachable through relative RUNPATH '.'", r.returncode == 97
      and "relative RUNPATH" in r.stderr and "dump:" not in r.stdout, r.stderr)
os.remove(f"{M2R}/libstdc++.so.6")
os.makedirs(f"{t}/exec/outputs/out/lib")
r = shim(audit, M2R, BASEQ)
check("T17 refused: absent RUNPATH entry (outputs/out/lib) now exists", r.returncode == 97 and "now exists" in r.stderr, r.stderr)
shutil.rmtree(f"{t}/exec")
open(f"{real}/bin/opp_run", "a").write("# changed\n")
r = shim(audit, M2R, BASEQ)
check("T17 refused: real opp_run changed since validation", r.returncode == 97 and "changed since validation" in r.stderr)
logl = [l.split("\t") for l in open(log).read().splitlines()[1:]]
check("T17 every call logged with decision, kind, actual working directory and exit status",
      len(logl) == 4 + len(bad_vectors) + 5 and all(len(x) == 8 for x in logl)
      and [x[2] for x in logl[:4]] == ["FORWARDED"] * 4 and logl[0][4] == "<repo>/simulations/m2"
      and logl[1][4] == "<suite-tmp>/tmpab12/repo/simulations/m2" and logl[2][6] == "3"
      and all(x[2] == "REFUSED" and x[6] == "97" for x in logl[4:]), logl[:6])
check("T17 refusals leave the UNAUTHORISED marker", os.path.exists(f"{audit}/UNAUTHORISED"))
shutil.rmtree(t)
t, real, repo, tmproot, audit, log = audit_env(resolution="/usr/lib/x86_64-linux-gnu/libc.so.6")
r = shim(audit, f"{repo}/simulations/m2", BASEQ)
check("T17 refused: loader resolves a library outside /nix/store and the project library directory", r.returncode == 97
      and "unexpected resolution" in r.stderr, r.stderr)
shutil.rmtree(t)
t, real, repo, tmproot, audit, log = audit_env()
r = subprocess.run(["bash", "-c", f'source "{audit}/setenv" -f; echo "args=$REAL_SETENV_ARGS"; command -v opp_run'],
                   capture_output=True, text=True, env=clean_env())
check("T17 audit setenv sources the real setenv (arguments passed) and puts the shim first on PATH",
      "args=-f" in r.stdout and r.stdout.strip().endswith(f"{audit}/bin/opp_run"), r.stdout + r.stderr)
r = subprocess.run(["bash", "-c", f'source "{audit}/setenv" -f; cd "{repo}/simulations/m2"; opp_run {" ".join(BASEQ)}'],
                   capture_output=True, text=True, env=clean_env())
check("T17 a query issued the suite's way (source setenv; cd; opp_run ...) reaches the real binary only through the shim",
      r.returncode == 0 and r.stdout.startswith("dump:") and open(log).read().count("FORWARDED") == 1, r.stdout + r.stderr)
shutil.rmtree(t)

# ======================================================================= T18 wrapper-suite evaluation (wrapper_check.py)
# SYNTHETIC suite outputs and audit logs: these test the evaluation logic only and are never wrapper evidence.
WC = load("wrapper_check")
LINE = PINS["WRAPPER_EXPECTED_LINE"]
NAMES = [f"T-x-{i:02d}: synthetic test {i}" for i in range(21)]


def wc_env(variant="pass"):
    t = tempfile.mkdtemp(prefix="t1wc-")
    names = list(NAMES)
    out = [f"PASS  {n}" for n in names] + [LINE]
    setup = {"suite_setup": "PASS", "suite_exit": "0", "results_root_env": "<unset>", "vm_results_root_present_after": "no",
             "unauthorised_marker": "absent"}
    calls = [("FORWARDED", "runconfig-base", "<repo>/simulations/m2", " ".join(BASEQ), "0"),
             ("FORWARDED", "runconfig-a2v1", "<repo>/simulations/m2", " ".join(A2V1Q), "0"),
             ("FORWARDED", "runconfig-base", "<suite-tmp>/tmpq1/repo/simulations/m2", " ".join(BASEQ), "0"),
             ("FORWARDED", "runconfig-a2v1", "<suite-tmp>/tmpq1/repo/simulations/m2", " ".join(A2V1Q), "0")]
    before = "!! src/nasctime/m2/libnasctime_m2.so\n!! src/nasctime/m2/Makefile\n"
    after = before
    if variant == "20of21":
        out[3] = f"FAIL  {names[3]}: AssertionError: x"
        out[-1] = "A2-V1 wrapper tests: 20 / 21 PASS"
        setup["suite_exit"] = "1"
    elif variant == "fail-line-but-summary-ok":
        out.insert(5, f"FAIL  {names[5]}: AssertionError: y")
    elif variant == "summary-mismatch":
        out[-1] = "A2-V1 wrapper tests: 21 / 21 PASS (stub)"
    elif variant == "missing-tests":
        out = out[:18] + [LINE]
    elif variant == "refused-call":
        calls.append(("REFUSED", "unapproved", "<repo>/simulations/m2", "-u Cmdenv -f m2s72a2v.ini -c X -r 0", "97"))
        setup["unauthorised_marker"] = "present"
    elif variant == "unapproved-forwarded":
        calls.append(("FORWARDED", "runconfig-base", "/elsewhere", " ".join(BASEQ), "0"))
    elif variant == "no-real-query":
        calls = []
    elif variant == "tracked-change":
        after = before + " M simulations/m2/m2s72a2v.ini\n"
    elif variant == "new-untracked":
        after = before + "?? simulations/m2/stray.txt\n"
    elif variant == "new-ignored":
        after = before + "!! simulations/m2/results/\n"
    elif variant == "blocked":
        out[0] = f"FAIL  {names[0]}: G0-config runconfig of M2S72 failed"
        out[-1] = "A2-V1 wrapper tests: 20 / 21 PASS"
        setup["suite_exit"] = "1"
        calls[0] = calls[0][:4] + ("1",)
    elif variant == "source-discrepancy":
        out[1] = f"FAIL  {names[1]}: GATE FAIL G0-source A2-0s source text differs"
        out[-1] = "A2-V1 wrapper tests: 20 / 21 PASS"
        setup["suite_exit"] = "1"
    elif variant == "results-root":
        setup["vm_results_root_present_after"] = "yes"
    open(f"{t}/wrapper-suite.txt", "w").write("\n".join(out) + "\n")
    open(f"{t}/wrapper-setup.txt", "w").write("".join(f"{k}: {v}\n" for k, v in setup.items()))
    open(f"{t}/opp_run-audit.tsv", "w").write("seq\tutc\tdecision\tkind\tcwd\targv\texit\tdetail\n" + "".join(
        f"{i + 1}\t2026-01-01T00:00:00Z\t{d}\t{k}\t{c}\t{a}\t{x}\t{'hazards none' if d == 'FORWARDED' else 'refused'}\n"
        for i, (d, k, c, a, x) in enumerate(calls)))
    open(f"{t}/wrapper-git-status-before.txt", "w").write(before)
    open(f"{t}/wrapper-git-status-after.txt", "w").write(after)
    return t


for variant, want in (("pass", True), ("20of21", False), ("fail-line-but-summary-ok", False), ("summary-mismatch", False),
                      ("missing-tests", False), ("refused-call", False), ("unapproved-forwarded", False), ("no-real-query", False),
                      ("tracked-change", False), ("new-untracked", False), ("new-ignored", True), ("blocked", False),
                      ("source-discrepancy", False), ("results-root", False)):
    t = wc_env(variant)
    ok, res = WC.evaluate(t, LINE, 21, "0")
    rs = "\n".join(res)
    extra = True
    if variant == "pass":
        extra = "tests_passed: 21" in rs and "audit_forwarded_runconfig_base: 2" in rs and "REAL CONFIGURATION QUERIES + SYNTHETIC LIFECYCLE" in rs \
            and len(open(f"{t}/wrapper-results.tsv").read().splitlines()) == 22
    elif variant == "blocked":
        extra = "classification_vm_compatibility_blocked: yes" in rs
    elif variant == "source-discrepancy":
        extra = "classification_simu5g_source_discrepancy: yes" in rs and "classification_vm_compatibility_blocked: no" in rs
    elif variant == "new-ignored":
        extra = "repository_new_ignored: 1" in rs
    check(f"T18 wrapper evaluation [{variant}] -> {'PASS' if want else 'FAIL'}", ok == want and extra, rs)
    shutil.rmtree(t)
t = wc_env()
ok, res = WC.evaluate(t, LINE, 21, "124")
check("T18 guarded session timeout -> FAIL even with a complete suite output", not ok)
shutil.rmtree(t)


# ======================================================================= T19 run-suite.sh integration (MOCKED stack and suite)
# MOCKED: a compiled stand-in `opp_run`, a stand-in loader for --list, fake patchelf, and a stand-in suite file that
# issues the two configuration queries exactly the way the real suite does. The real suite is never modified.
def suite_env(fake_suite_body):
    t = tempfile.mkdtemp(prefix="t1rs-")
    real = f"{t}/ws/omnetpp-6.5.0"
    os.makedirs(f"{real}/bin")
    os.makedirs(f"{real}/lib")
    open(f"{t}/o.c", "w").write('#include <stdio.h>\nint main(int c,char**v){printf("config:");for(int i=1;i<c;i++)printf(" %s",v[i]);puts("");return 0;}\n')
    cc(["o.c", "-o", f"{real}/bin/opp_run"], t)
    open(f"{real}/setenv", "w").write(f'export PATH="{real}/bin:$PATH"\n')
    s5 = f"{t}/ws/simu5g-1.8.1"
    os.makedirs(f"{s5}/src/simu5g")
    repo = f"{t}/repo"
    os.makedirs(f"{repo}/simulations/m2/check")
    open(f"{repo}/simulations/m2/m2s72a2v1.sh", "w").write("# stand-in\n")
    open(f"{repo}/simulations/m2/check/test_m2s72a2v1_wrapper.py", "w").write(fake_suite_body)
    subprocess.run(["bash", "-c", f"cd {repo} && git init -q && git add -A && git -c user.name=t -c user.email=t@t commit -qm i"], check=True)
    ev = f"{t}/ev"
    os.makedirs(ev)
    sha = hashlib.sha256(open(f"{real}/bin/opp_run", "rb").read()).hexdigest()
    open(f"{ev}/binaries.tsv", "w").write("project\tkind\tpath\tbytes\tsha256\n" + f"omnetpp\texecutable\tomnetpp-6.5.0/bin/opp_run\t1\t{sha}\n")
    fb = f"{t}/fakebin"
    os.makedirs(fb)
    open(f"{fb}/ld.so", "w").write('#!/bin/sh\nprintf "\\tlibc.so.6 => /nix/store/x-glibc/lib/libc.so.6 (0x0)\\n"\n')
    open(f"{fb}/patchelf", "w").write(f"#!/bin/sh\necho {fb}/ld.so\n")
    for x in ("ld.so", "patchelf"):
        os.chmod(f"{fb}/{x}", 0o755)
    env = clean_env(PATH=f"{fb}:" + os.environ["PATH"], OMNETPP_ROOT=real, SIMU5G_ROOT=s5)
    return t, real, repo, ev, env


GOOD_SUITE = f'''import os, subprocess, sys, tempfile
R = os.environ["OMNETPP_ROOT"]; M2 = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
q = "source %s/setenv -f; cd %s; opp_run {" ".join(BASEQ)}" % (R, M2)
subprocess.run(q, shell=True, executable="/bin/bash", check=True, capture_output=True)
c = tempfile.mkdtemp(); os.makedirs(c + "/repo/simulations/m2")
q2 = "source %s/setenv -f; cd %s/repo/simulations/m2; opp_run {" ".join(A2V1Q)}" % (R, c)
subprocess.run(q2, shell=True, executable="/bin/bash", check=True, capture_output=True)
for i in range(21): print(f"PASS  T-s-{{i}}: stand-in")
print("{LINE}")
'''
t, real, repo, ev, env = suite_env(GOOD_SUITE)
r = run(["bash", os.path.join(WRAP, "run-suite.sh"), T1, repo, ev, f"{t}/w"], env, timeout=120)
ok, res = WC.evaluate(ev, LINE, 21, str(r.returncode))
aud = open(f"{ev}/opp_run-audit.tsv").read()
check("T19 run-suite: queries reach the real binary only through the shim, from the repository and a suite clone; PASS",
      r.returncode == 0 and ok and aud.count("FORWARDED") == 2 and "<suite-tmp>/" in aud and "<repo>/simulations/m2" in aud
      and "suite_setup: PASS" in open(f"{ev}/wrapper-setup.txt").read(), r.stdout + r.stderr + aud + "\n".join(res))
check("T19 run-suite: the suite's temporary clones live under the controlled work directory", os.path.isdir(f"{t}/w/tmp") and os.listdir(f"{t}/w/tmp"))
shutil.rmtree(t)
SIM_SUITE = GOOD_SUITE.replace('subprocess.run(q2,', 'subprocess.run(q2.replace("-q runconfig", ""),')
t, real, repo, ev, env = suite_env(SIM_SUITE)
r = run(["bash", os.path.join(WRAP, "run-suite.sh"), T1, repo, ev, f"{t}/w"], env, timeout=120)
ok, res = WC.evaluate(ev, LINE, 21, str(r.returncode))
check("T19 run-suite: a simulation-shaped call is refused and the suite fails", not ok and "REFUSED" in open(f"{ev}/opp_run-audit.tsv").read()
      and "unauthorised_marker: present" in open(f"{ev}/wrapper-setup.txt").read(), "\n".join(res))
shutil.rmtree(t)
DIRTY_SUITE = GOOD_SUITE + 'open(os.path.join(M2, "m2s72a2v1.sh"), "a").write("# modified\\n")\n'
t, real, repo, ev, env = suite_env(DIRTY_SUITE)
r = run(["bash", os.path.join(WRAP, "run-suite.sh"), T1, repo, ev, f"{t}/w"], env, timeout=120)
ok, res = WC.evaluate(ev, LINE, 21, str(r.returncode))
check("T19 run-suite: a tracked repository modification by the suite fails C-13", not ok and "tracked repository modifications" in "\n".join(res), "\n".join(res))
shutil.rmtree(t)
t, real, repo, ev, env = suite_env(GOOD_SUITE)
open(f"{ev}/binaries.tsv", "w").write("project\tkind\tpath\tbytes\tsha256\nomnetpp\texecutable\tomnetpp-6.5.0/bin/opp_run\t1\t" + "0" * 64 + "\n")
r = run(["bash", os.path.join(WRAP, "run-suite.sh"), T1, repo, ev, f"{t}/w"], env, timeout=120)
check("T19 run-suite: opp_run differing from the validated binary -> setup fails, suite not run",
      r.returncode == 3 and not os.path.exists(f"{ev}/wrapper-suite.txt"), r.stdout)
shutil.rmtree(t)
t, real, repo, ev, env = suite_env(GOOD_SUITE)
r = run(["bash", os.path.join(WRAP, "run-suite.sh"), T1, repo, ev, f"{t}/w"], dict(env, A2V1_RESULTS_ROOT="/mnt/nasctime-results"), timeout=120)
check("T19 run-suite: a results root in the session -> setup fails", r.returncode == 3, r.stdout)
shutil.rmtree(t)

# ======================================================================= T20 evaluation, publication and verdict (steps/evaluate, publish, final, conclude)
LSHA, HSHA = PINS["LOCK_SHA256"], PINS["HELPER_LOCK_SHA256"]
STD = "/nix/store/chqq8mpmpyfi9kgsngya71akv5xicn03-gcc-15.2.0-lib/lib/libstdc++.so.6"
REF = dict(x.split("=", 1) for x in PINS["WITH_REFERENCE"].split())
WF_IDS = ["checkout", "setup", "bootstrap", "verify", "runtime", "b_omnetpp", "b_inet", "b_simu5g", "b_nasctime", "validate",
          "srcchanges", "wrapper", "lockend", "measure"]


def good(ev, ci, now, case="A"):
    phases = ["before-realisation", "after-realisation", "after-probe", "after-runtime-probe-before", "after-runtime-probe-after",
              "after-omnetpp", "after-inet", "after-simu5g", "after-nasctime", "after-validation", "after-wrapper", "final"]
    stages = [("nix-install", 5), ("realise", 120), ("probe", 12), ("probe-runtime-before", 20), ("probe-runtime-after", 20),
              ("build-omnetpp", 400), ("build-inet", 1100), ("build-simu5g", 320), ("build-nasctime", 25), ("validate", 30), ("wrapper-suite", 300)]
    if case == "B":
        stages = [s for s in stages if s[0] != "probe-runtime-after"]
    tl, t = ["step\tseconds\texit\tstart_epoch\tend_epoch"], now - 2600
    for s, d in stages:
        tl.append(f"{s}\t{d}\t0\t{t}\t{t + d}")
        t += d + 5
    import datetime as dt
    disk = ["utc\tpath\tavail_B\tused_B\tmem_avail_kib"]
    for k in range(now - 2700, now + 10, 10):
        ts = dt.datetime.fromtimestamp(k, dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        disk.append(f"{ts}\t/\t{90_000_000_000 - (k - now + 2700) * 1_000_000}\t1\t{14_000_000 - (k % 7) * 1000}")
    bins = ["\t".join(["project", "kind", "path", "bytes", "sha256", "elf", "compiler_comment", "needed", "runpath", "unresolved",
                       "cxx_runtime_violation", "libunwind", "libstdcxx_resolved", "unexpected_resolution"])]
    for i in range(18):
        bins.append(f"p\tlibrary\tlib{i}.so\t100\t{'a' * 64}\tyes\tclang version 21.1.8\tlibstdc++.so.6\tRUNPATH=/x\t0\tnone\tnone\t{STD}\tnone")
    for i in range(4):
        bins.append(f"p\ttool\ttool{i}\t10\t{'b' * 64}\tno\t\t\t\tn/a\tn/a\tn/a\tn/a\tn/a")
    tests = [f"T-x-{i:02d}" for i in range(21)]
    files = {
        "identity.txt": "pr_head_sha: a\ntested_merge_sha: b\n",
        "runner.txt": "nproc: 4\nmem_total_kib: 16000000\nroot_avail_start_B: 92000000000\n",
        "nix.txt": "nix_version: nix (Nix) 2.34.4\nrequire-sigs = true\n",
        "opp_env.txt": f"opp_env_version: 0.36.2.261110\nopp_env_module: {os.path.realpath(ci)}/venv/lib/opp_env\n"
                       f"opp_env_main_sha256: {PINS['OPP_ENV_MAIN_SHA256']}\n",
        "release-assets.txt": "OMNETPP sha256: x match: yes\nassets_check: PASS\n",
        "probe.txt": "tool clang++: /x | clang version 21.1.8\ntool g++: /x | g++ (GCC) 15.2.0\ntool make: /x | GNU Make 4.2.1\n"
                     "tool python3: /x | Python 3.13.13\n" + "".join(f"configure.user {k}: {v}\n" for k, v in REF.items()) + "probe_result: PASS\n",
        "lock.txt": f"repository approved_26.05: {LSHA}\n" + "".join(f"{p} approved_26.05: {LSHA}\n{p} helper_22.11: {HSHA}\n{p} result: PASS\n" for p in phases),
        "lock-enforcement.txt": "write_protection 26.05: immutable (i)\nwrite_protection 22.11: immutable (i)\n",
        "flake-lock-check.txt": "flake_metadata_no_update_check: PASS\n", "workspace-admin-check.txt": "admin_check: PASS\n",
        "adaptations-summary.txt": "unexpected_adaptations: 0\nframework_build_outputs_after_download: 0\n",
        "postdownload-verify.txt": "".join(f"{p} sha1sum_check: PASS\n{p} files_added_after_download: 0\n" for p in ("omnetpp", "inet", "simu5g")),
        "source-identity.txt": "reference_manifest_comparison: NOT EVALUATED\n",
        "sizes.txt": "nix_store_bytes_final: 9\nroot_avail_final_B: 60000000000\n",
        "source-changes-summary.txt": "unexpected_upstream_source_changes: 0\nnascTime_tracked_source_changes: 0\n",
        "validate-result.txt": "binaries_result: PASS\noppv_result: PASS\nlinkage_result: PASS\nruntime_result: PASS\nvalidate_result: PASS\n",
        "identity-tools.txt": "debug_outputs_present: 0\n", "opp_run-version.txt": "Version: 6.5.0\nopp_run_v_exit: 0\n",
        "binaries.tsv": "\n".join(bins) + "\n", "timings.tsv": "\n".join(tl) + "\n", "disk.tsv": "\n".join(disk) + "\n",
        "build-options.txt": "CXX = clang++\n", "nix-store-summary.txt": "path_info: AVAILABLE\n", "runtime-symbols.txt": "== x\n",
        "unresolved.txt": "", "exec-checks.txt": "2026-01-01T00:00:00Z [before realise] ok\n",
        "runpath-observation.txt": "before probe default: non-store RUNPATH entry /w/tier1/exec/outputs/out/lib exists=no\n",
        "runpath-observation-validate.txt": "lib0.so: non-store RUNPATH entry . exists=yes class=relative\n"
                                            "lib0.so: non-store RUNPATH entry /w/omnetpp-6.5.0/lib exists=yes class=project\n",
        "host-cxx-packages-before.tsv": "libc++-14-dev\t1\tinstall ok installed\n",
        "runtime-probe-before.txt": "probe libcxx rc: 0\n", "c4-case.txt": f"c4_case: {case}\n",
        "runtime-gates.txt": f"c4_case: {case}\nnegative_libcxx_rc: 1\nnegative_libcxx_reason: ld.lld: error: unable to find library -lc++\nr3_result: PASS\n"
                             f"positive_default_result: PASS\npositive_stdcxx_result: PASS\npositive_default_libstdcxx: {STD}\nr4_result: PASS\n",
        "sys-libs.txt": "ordered_token_match_vm: yes\nexact_string_match_vm: no\ntokens_only_hosted: none\ntokens_only_vm: none\nr5_result: PASS\n",
        "adaptations.tsv": "x\n",
        "wrapper-setup.txt": "suite_setup: PASS\nsuite_exit: 0\n", "wrapper-suite.txt": "".join(f"PASS  {n}\n" for n in tests) + LINE + "\n",
        "opp_run-audit.tsv": "seq\tutc\tdecision\tkind\tcwd\targv\texit\tdetail\n1\tx\tFORWARDED\truncconfig-base\t<repo>/simulations/m2\tq\t0\thazards none\n",
        "wrapper-result.txt": "tests_total: 21\ntests_passed: 21\nsummary_line: " + LINE + "\naudit_forwarded: 30\naudit_refused: 0\n"
                              "classification_vm_compatibility_blocked: no\nclassification_simu5g_source_discrepancy: no\nwrapper_result: PASS\n",
        "wrapper-results.tsv": "result\ttest\n" + "".join(f"PASS\t{n}\n" for n in tests),
    }
    if case == "A":
        files.update({
            "host-libcxx.txt": "selected_libcxx_runtime: /lib/x86_64-linux-gnu/libc++.so.1\nselected_libcxx_canonical: /usr/lib/x86_64-linux-gnu/libc++.so.1.0\n"
                               "unversioned_linker_entry: /lib/x86_64-linux-gnu/libc++.so\nruntime_owners: libc++1-14:amd64\n"
                               "development_owners: libc++-14-dev:amd64\nr1_result: PASS\n",
            "apt-remove-proposed.txt": "libc++-14-dev\n", "apt-remove-simulation.txt": "Remv libc++-14-dev [1:14.0]\n",
            "apt-remove-transaction.txt": "removal: libc++-14-dev\nrejected_unrelated_removals: none\ninstall_or_purge_lines: 0\ntransaction_check: PASS\n",
            "apt-remove.txt": "Removing libc++-14-dev\n", "host-cxx-packages-after.tsv": "", "host-packages.diff": "changed_packages: 1\nr2_result: PASS\n",
            "runtime-probe-after.txt": "probe libcxx rc: 1\n"})
    for k, v in files.items():
        open(os.path.join(ev, k), "w").write(v)
    for p in ("omnetpp", "inet", "simu5g"):
        open(os.path.join(ev, f"build-{p}.log"), "w").write(f"Invoking build_{p} release:\ncompiling...\nDone build_{p} release\n")


def full(variant="pass", case="A"):
    t, ci, ev, env = sandbox()
    env = clean_env(RUNNER_TEMP=t, PATH=os.environ["PATH"])
    genv = dict(env, EV=ev, STOP_FREE_GIB="0", GUARD_INTERVAL_S="1")
    gp = start_guard(ev, genv)
    time.sleep(1.2)
    now = int(time.time())
    good(ev, ci, now, case)
    outcomes = {i: {"outcome": "success", "conclusion": "success", "outputs": {}} for i in WF_IDS}

    def edit(f, a, b):
        p = os.path.join(ev, f)
        data = open(p).read()
        assert a in data, (f, a)
        open(p, "w").write(data.replace(a, b))

    def skip(*ids):
        for s in ids:
            outcomes[s]["outcome"] = "skipped"

    def drop(*labels):
        tl = [l for l in open(f"{ev}/timings.tsv").read().splitlines() if not l.startswith(labels)]
        open(f"{ev}/timings.tsv", "w").write("\n".join(tl) + "\n")

    def rm(*fs):
        for f in fs:
            if os.path.exists(os.path.join(ev, f)):
                os.remove(os.path.join(ev, f))
    after_runtime = ("b_omnetpp", "b_inet", "b_simu5g", "b_nasctime", "validate", "srcchanges", "wrapper")
    build_files = ("sys-libs.txt", "binaries.tsv", "validate-result.txt", "identity-tools.txt", "build-options.txt", "opp_run-version.txt",
                   "runtime-symbols.txt", "runpath-observation-validate.txt", "source-changes-summary.txt", "build-omnetpp.log", "build-inet.log",
                   "build-simu5g.log", "wrapper-setup.txt", "wrapper-suite.txt", "opp_run-audit.tsv", "wrapper-result.txt", "wrapper-results.tsv")
    if variant == "provenance-fail":
        outcomes["runtime"]["outcome"] = "failure"
        skip(*after_runtime)
        edit("host-libcxx.txt", "r1_result: PASS", "r1_result: FAIL")
        open(f"{ev}/HYPOTHESIS_NOT_CONFIRMED", "w").write("no libc++ library in the linker trace\n")
        drop("probe-runtime-after", "build-", "validate", "wrapper")
        rm("apt-remove-proposed.txt", "apt-remove-simulation.txt", "apt-remove-transaction.txt", "apt-remove.txt", "host-cxx-packages-after.tsv",
           "host-packages.diff", "runtime-probe-after.txt", "runtime-gates.txt", *build_files)
    elif variant == "invalid-probe":
        outcomes["runtime"]["outcome"] = "failure"
        skip(*after_runtime)
        open(f"{ev}/c4-case.txt", "w").write("c4_case: INVALID\n")
        drop("probe-runtime-after", "build-", "validate", "wrapper")
        rm("host-libcxx.txt", "apt-remove-proposed.txt", "apt-remove-simulation.txt", "apt-remove-transaction.txt", "apt-remove.txt",
           "host-cxx-packages-after.tsv", "host-packages.diff", "runtime-probe-after.txt", "runtime-gates.txt", *build_files)
    elif variant == "transaction-rejected":
        outcomes["runtime"]["outcome"] = "failure"
        skip(*after_runtime)
        edit("apt-remove-transaction.txt", "transaction_check: PASS", "transaction_check: FAIL")
        drop("probe-runtime-after", "build-", "validate", "wrapper")
        rm("apt-remove.txt", "host-cxx-packages-after.tsv", "host-packages.diff", "runtime-probe-after.txt", "runtime-gates.txt", *build_files)
    elif variant == "sys-libs-fail":
        outcomes["b_omnetpp"]["outcome"] = "failure"
        skip("b_inet", "b_simu5g", "b_nasctime", "validate", "srcchanges", "wrapper")
        edit("sys-libs.txt", "r5_result: PASS", "r5_result: FAIL")
        drop("build-inet", "build-simu5g", "build-nasctime", "validate", "wrapper")
        rm(*[f for f in build_files if f not in ("sys-libs.txt", "build-omnetpp.log")])
    elif variant == "linkage-fail":
        outcomes["validate"]["outcome"] = "failure"
        skip("wrapper")
        drop("wrapper")
        edit("validate-result.txt", "linkage_result: PASS", "linkage_result: FAIL")
        edit("validate-result.txt", "runtime_result: PASS", "runtime_result: NOT EVALUATED")
        edit("binaries.tsv", f"RUNPATH=/x\t0\tnone\tnone\t{STD}\tnone\np\tlibrary\tlib1.so", f"RUNPATH=/x\t1\tnone\tnone\tabsent\tnone\np\tlibrary\tlib1.so")
        rm("wrapper-setup.txt", "wrapper-suite.txt", "opp_run-audit.tsv", "wrapper-result.txt", "wrapper-results.tsv")
    elif variant == "runtime-violation":
        outcomes["validate"]["outcome"] = "failure"
        skip("wrapper")
        drop("wrapper")
        edit("validate-result.txt", "runtime_result: PASS", "runtime_result: FAIL")
        edit("binaries.tsv", f"RUNPATH=/x\t0\tnone\tnone\t{STD}\tnone\np\tlibrary\tlib1.so", f"RUNPATH=/x\t0\tlibc++.so.1\tlibunwind.so.1\t{STD}\tnone\np\tlibrary\tlib1.so")
        rm("wrapper-setup.txt", "wrapper-suite.txt", "opp_run-audit.tsv", "wrapper-result.txt", "wrapper-results.tsv")
    elif variant == "runpath-unexpected":
        open(f"{ev}/runpath-observation-validate.txt", "a").write("lib0.so: non-store RUNPATH entry /tmp/w exists=yes class=UNEXPECTED\n")
    elif variant == "exec-check-fail":
        open(f"{ev}/exec-checks.txt", "a").write("2026-01-01T00:00:01Z [after validate] FAIL exec/outputs exists;\n")
    elif variant == "srcchanges-not-run":
        skip("srcchanges")
        rm("source-changes-summary.txt")
    elif variant == "wrapper-fail":
        outcomes["wrapper"]["outcome"] = "failure"
        edit("wrapper-result.txt", "wrapper_result: PASS", "wrapper_result: FAIL")
    elif variant == "wrapper-blocked":
        outcomes["wrapper"]["outcome"] = "failure"
        edit("wrapper-result.txt", "wrapper_result: PASS", "wrapper_result: FAIL")
        edit("wrapper-result.txt", "classification_vm_compatibility_blocked: no", "classification_vm_compatibility_blocked: yes (F-8; no patch applied)")
    elif variant == "wrapper-not-run":
        skip("wrapper")
        drop("wrapper")
        rm("wrapper-setup.txt", "wrapper-suite.txt", "opp_run-audit.tsv", "wrapper-result.txt", "wrapper-results.tsv")
    elif variant == "release-asset-mismatch":
        outcomes["bootstrap"]["outcome"] = "failure"
        edit("release-assets.txt", "assets_check: PASS", "assets_check: FAIL")
    elif variant == "stop":
        open(f"{ev}/STOP", "w").write("disk gate: synthetic\n")
    elif variant == "guard-dead":
        os.kill(gp, signal.SIGKILL)
        time.sleep(0.3)
    elif variant == "screening-fail":
        open(f"{ev}/identity.txt", "a").write("token: ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123\n")
    env["STEP_OUTCOMES"] = json.dumps(outcomes)
    re_ = run(["bash", os.path.join(STEPS, "evaluate.sh")], env)
    rp = run(["bash", os.path.join(STEPS, "publish.sh")], env)
    outcomes["evaluate"] = {"outcome": "success" if re_.returncode == 0 else "failure"}
    outcomes["publish"] = {"outcome": "success" if rp.returncode == 0 else "failure"}
    rf = run(["bash", os.path.join(STEPS, "final.sh")], dict(env, STEP_OUTCOMES=json.dumps(outcomes), PUBLISH_OUTCOME=outcomes["publish"]["outcome"],
                                                             GITHUB_STEP_SUMMARY=f"{t}/summary.md"))
    upload = "success" if rp.returncode == 0 and variant != "upload-fail" else ("failure" if variant == "upload-fail" else "skipped")
    rc_ = run(["bash", os.path.join(STEPS, "conclude.sh")], dict(env, UPLOAD_OUTCOME=upload))
    v = re.search(r"# Tier-1 full-stack validation: (.*)", rf.stdout)
    rows = dict(re.findall(r"^\| (C-\d+) \| .*? \| (PASS|FAIL|NOT EVALUATED) \|", rf.stdout, re.M))
    pub = sorted(os.listdir(f"{ci}/publish")) if os.path.isdir(f"{ci}/publish") else []
    if alive(gp):
        os.kill(gp, signal.SIGKILL)
    shutil.rmtree(t)
    return rf.returncode, (v.group(1) if v else None), rows, pub, re_, rp, rf, rc_


rc, v, rows, pub, re_, rp, rf, rc_ = full()
check("T20 all good (case A) -> TIER-1 PASS, C-1..C-15 all PASS, final and conclusion exit 0",
      rc == 0 and rc_.returncode == 0 and v == "TIER-1 PASS" and len(rows) == 15 and set(rows.values()) == {"PASS"},
      f"{rc} {v} {rows} {re_.stdout[-900:]} {rp.stdout[-300:]} {rf.stderr[-300:]}")
c4 = re.search(r"^\| C-4 \| .*$", rf.stdout, re.M).group(0) if "| C-4 |" in rf.stdout else ""
check("T20 C-4 detail reports the corrected R-1 fields (selected runtime, canonical, entry, runtime and development owners)",
      "selected=/lib/x86_64-linux-gnu/libc++.so.1" in c4 and "canonical=/usr/lib/x86_64-linux-gnu/libc++.so.1.0" in c4
      and "runtime_owners=libc++1-14:amd64" in c4 and "development_owners=libc++-14-dev:amd64" in c4 and "None" not in c4, c4)
check("T20 publication includes runtime, wrapper and audit evidence and the verdict",
      all(f in pub for f in ("verdict.md", "host-libcxx.txt", "runtime-gates.txt", "sys-libs.txt", "binaries.tsv", "wrapper-result.txt",
                             "wrapper-results.tsv", "opp_run-audit.tsv", "wrapper-suite.txt", "identity.txt", "c-rows.json")), pub)
rc, v, rows, pub, re_, rp, rf, rc_ = full(case="B")
check("T20 clean host (case B) -> TIER-1 PASS without removal evidence", rc == 0 and v == "TIER-1 PASS" and rows.get("C-4") == "PASS"
      and "host-packages.diff" not in pub, f"{v} {rows} {rf.stdout[-600:]}")
NE = "NOT EVALUATED"
for variant, want_v, expect in (
        ("provenance-fail", "TIER-1 FAIL", {"C-4": "FAIL", "C-5": NE, "C-6": NE, "C-10": NE, "C-12": NE, "C-13": NE, "C-15": "PASS"}),
        ("invalid-probe", "TIER-1 FAIL", {"C-4": "FAIL", "C-6": NE, "C-15": "PASS"}),
        ("transaction-rejected", "TIER-1 FAIL", {"C-4": "FAIL", "C-6": NE}),
        ("sys-libs-fail", "TIER-1 FAIL", {"C-5": "FAIL", "C-6": "PASS", "C-7": NE, "C-10": NE, "C-3": NE, "C-15": "PASS"}),
        ("linkage-fail", "TIER-1 FAIL", {"C-10": "PASS", "C-11": "FAIL", "C-12": NE, "C-13": NE}),
        ("runtime-violation", "TIER-1 FAIL", {"C-12": "FAIL", "C-11": "PASS"}),
        ("runpath-unexpected", "TIER-1 FAIL", {"C-12": "FAIL"}),
        ("exec-check-fail", "TIER-1 FAIL", {"C-12": "FAIL"}),
        ("srcchanges-not-run", "TIER-1 FAIL", {"C-3": NE}),
        ("wrapper-fail", "TIER-1 FAIL", {"C-13": "FAIL", "C-12": "PASS"}),
        ("wrapper-blocked", "TIER-1 BLOCKED (VM compatibility, F-8; no patch applied)", {"C-13": "FAIL"}),
        ("wrapper-not-run", "TIER-1 FAIL", {"C-13": NE}),
        ("release-asset-mismatch", "TIER-1 FAIL", {"C-1": "FAIL"}),
        ("screening-fail", "TIER-1 FAIL", {"C-15": "FAIL"}),
        ("stop", "STOP", {"C-14": "FAIL"}),
        ("guard-dead", "INFRASTRUCTURE FAILURE", {"C-14": "FAIL"})):
    rc, v, rows, pub, re_, rp, rf, rc_ = full(variant)
    bad = {k: (rows.get(k), w) for k, w in expect.items() if rows.get(k) != w}
    check(f"T20 {variant} -> {want_v}", v == want_v and not bad and rc != 0 and rc_.returncode != 0 and len(rows) == 15,
          f"{rc} {v} mismatches={bad} {rf.stdout[-500:]} {re_.stderr[-300:]}")
rc, v, rows, pub, re_, rp, rf, rc_ = full("upload-fail")
check("T20 artifact upload failure -> conclusion fails although the verdict is PASS", v == "TIER-1 PASS" and rc_.returncode != 0
      and "not published" in rc_.stdout, rc_.stdout)


# ======================================================================= T21 validate step: controlled directory, evidence and summary on failure
def fake_oe(ci):
    os.makedirs(f"{ci}/venv/bin", exist_ok=True)
    open(f"{ci}/venv/bin/opp_env", "w").write('#!/bin/bash\n# MOCKED opp_env: runs the -c command\nwhile [ "$1" != -c ]; do shift; done\n'
                                              'echo "cwd=$(pwd)" >> "$EV/fake-oe-cwd.txt"\nexec bash -c "$2"\n')
    os.chmod(f"{ci}/venv/bin/opp_env", 0o755)


t, ci, ev, env, repo, ws = validate_env("unresolved")
fake_oe(ci)
genv = dict(env, STOP_FREE_GIB="0", GUARD_INTERVAL_S="1")
gp = start_guard(ev, genv)
os.makedirs(f"{ws}/.opp_env_workspace/26.05")
os.makedirs(f"{ws}/.opp_env_workspace/22.11")
summ = os.path.join(t, "summary.md")
venv = {k: v for k, v in env.items() if k not in ("EV", "E2B", "WS", "LOCK_SHA256", "HELPER_LOCK_SHA256", "REPO", "T1_LIB")}
r = run(["bash", os.path.join(STEPS, "validate.sh")], dict(venv, GITHUB_STEP_SUMMARY=summ), timeout=180)
s = open(summ).read() if os.path.exists(summ) else ""
check("T21 failing validation keeps all evidence, prints screened unresolved names and RUNPATH classes, exits non-zero",
      r.returncode == 1 and "libdep.so" in s and "linkage_result: FAIL" in s and "guarded validate exit: 1" in s
      and os.path.exists(f"{ev}/build-options.txt") and os.path.exists(f"{ev}/opp_run-version.txt"), r.stdout[-800:] + s)
check("T21 the opp_env session ran in the controlled directory and the execution checks were recorded",
      open(f"{ev}/fake-oe-cwd.txt").read().strip() == f"cwd={ci}/exec" and "[before validate] ok" in open(f"{ev}/exec-checks.txt").read(),
      open(f"{ev}/exec-checks.txt").read())
open(f"{ci}/exec/stray.so", "w").write("x")
os.remove(f"{ev}/fake-oe-cwd.txt")
r = run(["bash", os.path.join(STEPS, "validate.sh")], dict(venv, GITHUB_STEP_SUMMARY=summ), timeout=180)
check("T21 a file in the controlled directory stops the session before it starts", r.returncode != 0 and not os.path.exists(f"{ev}/fake-oe-cwd.txt")
      and "controlled directory not empty" in open(f"{ev}/exec-checks.txt").read(), r.stdout[-400:])
os.remove(f"{ci}/exec/stray.so")
os.makedirs(f"{ws}/omnetpp-6.5.0/tools/linux.x86_64/lib")
r = run(["bash", os.path.join(STEPS, "validate.sh")], dict(venv, GITHUB_STEP_SUMMARY=summ), timeout=180)
check("T21 an absent RUNPATH directory that appears (tools/linux.x86_64/lib) stops the session", r.returncode != 0
      and "tools/linux.x86_64/lib exists" in open(f"{ev}/exec-checks.txt").read())
stop_guard(ev, gp)
shutil.rmtree(t)

shutil.rmtree(WORKDIR, ignore_errors=True)
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("FAILED:", *failed, sep="\n  ")
sys.exit(1 if failed else 0)
