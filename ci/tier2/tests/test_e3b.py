#!/usr/bin/env python3
"""Offline validation of the E3b additions to the shared tier-2 implementation (ci/tier2): M2S5 on M1Bridge, as corrected
by E3b-R1 (raw-publication policy for the N3 capture; experiment identity of the re-run).
No Nix, no opp_env, no network, no OMNeT++, no simulation. Three kinds of test input, labelled in every check name:
  [stand-in]   a stand-in script in place of opp_run (never a simulation);
  [synthetic]  synthetic files from tests/synth.py / tests/synth5.py (never evidence);
  [mock]       a mocked check_m2s5 module (tests the adapter's row mapping only; never the reviewed oracle);
  [reviewed]   the real, unmodified simulations/m2/check/check_m2s5.py with its full import chain.
usage: python3 -I ci/tier2/tests/test_e3b.py   (run test_tier2.py as well: the E3a regression suite)"""
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
WF = os.path.join(REPO, ".github", "workflows", "e3b-r1-publication.yml")
WF_E3B = os.path.join(REPO, ".github", "workflows", "e3b-bridge-functional.yml")
WF_E3A = os.path.join(REPO, ".github", "workflows", "e3a-functional-smoke.yml")
BASELINE = "290babba3d12942344a2153f9ea5ea54287df366"
E3A_PARENT = "f2215ad38169b86e4c0c7e0f220c14c82a78d603"
E3B_COMMIT = "4ed675976ac516aaf26dccf720e0b12fb671cf4a"   # the original E3b commit: the parent of E3b-R1
sys.path.insert(0, HERE)
import synth  # noqa: E402
import synth5  # noqa: E402

WORK = tempfile.mkdtemp(prefix="e3b-selftest-")
os.chdir(WORK)
results = []
TEST_VARS = ("TIER1_TEST_", "E2B3_TEST_", "A2V1_TEST_", "A2V1_STUB_")


def check(name, cond, detail=""):
    results.append((name, bool(cond)))
    print(("PASS " if cond else "FAIL ") + name + (f"  [{str(detail)[:900]}]" if detail and not cond else ""), flush=True)


def clean_env(**kw):
    e = {k: v for k, v in os.environ.items() if not k.startswith(TEST_VARS) and k not in ("A2V1_RESULTS_ROOT", "A2V1_COMMIT", "T2_EXPERIMENT")}
    e.update(kw)
    return e


def pins(path):
    d = {}
    for line in open(path):
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            d[k] = v[1:-1] if v[:1] == '"' and v[-1:] == '"' else v
    return d


def run(cmd, env, timeout=120, **kw):
    return subprocess.run(cmd, env=env, text=True, capture_output=True, timeout=timeout, **kw)


def git(repo, *a, **kw):
    return subprocess.run(["git", "-C", repo, "-c", "user.name=t", "-c", "user.email=t@t", *a], capture_output=True, text=True, **kw)


PB = pins(os.path.join(T2, "pins-e3b.env"))
PINS = {**pins(os.path.join(T1, "pins.env")), **PB}

# ======================================================================= B0 static checks and scope
WFT = open(WF).read()
check("B0 R1 workflow: push to wp-e3/e3b-r1-publication only; no pull_request / dispatch / schedule",
      "on:\n  push:\n    branches: [wp-e3/e3b-r1-publication]\n" in WFT and "pull_request" not in WFT and "workflow_dispatch" not in WFT
      and "schedule" not in WFT)
check("B0 workflow: T2_EXPERIMENT=e3b for the whole job, read-only token, no secrets, no caches, ubuntu-22.04, 120 min",
      "    env:\n      T2_EXPERIMENT: e3b\n" in WFT and "permissions:\n  contents: read\n" in WFT and "secrets." not in WFT
      and "actions/cache" not in WFT and "runs-on: ubuntu-22.04" in WFT and "timeout-minutes: 120" in WFT
      and "persist-credentials: false" in WFT)
check("B0 workflow: actions pinned by sha (same pins as E3a)", set(re.findall(r"uses: (\S+)", WFT)) == {
      "actions/checkout@3d3c42e5aac5ba805825da76410c181273ba90b1", "actions/upload-artifact@cf430e030ddbb5b0abf93d22962f4752f3646cd9"})
ids = re.findall(r"\n        id: (\w+)", WFT)
check("B0 workflow: same step sequence as the accepted E3a workflow",
      ids == re.findall(r"\n        id: (\w+)", open(WF_E3A).read()) and len(ids) == 27, ids)
check("B0 workflow: the simulation step runs only if every earlier step succeeded (no 'if')",
      "if:" not in WFT[WFT.index("id: sim\n"):WFT.index("id: seal\n")])
check("B0 R1 workflow: two artifacts, e3b-r1 names, 7-day retention, raw from $RUNNER_TEMP/e3b/publish-raw",
      "name: e3b-r1-diagnostics-run${{ github.run_id }}-${{ github.run_attempt }}" in WFT
      and "name: e3b-r1-raw-m2s5-run${{ github.run_id }}-${{ github.run_attempt }}" in WFT
      and "path: ${{ runner.temp }}/e3b/publish-raw/" in WFT and WFT.count("retention-days: 7") == 2)
check("B0 workflow: event values never interpolated into run scripts", not re.search(r"\n        run: [^\n]*\$\{\{", WFT))
E3AW = open(WF_E3A).read()
check("B0 E3a workflow untouched and its push trigger cannot run on the E3b branch",
      git(REPO, "diff", "--quiet", E3A_PARENT, "--", ".github/workflows/e3a-functional-smoke.yml").returncode == 0
      and "on:\n  push:\n    branches: [wp-e3/e3a-m2s4u-smoke]\n" in E3AW and "wp-e3/e3b" not in E3AW)
E3BW = open(WF_E3B).read()
check("B0 original E3b workflow untouched (vs 4ed6759) and its push trigger cannot run on the R1 branch",
      git(REPO, "diff", "--quiet", E3B_COMMIT, "--", ".github/workflows/e3b-bridge-functional.yml").returncode == 0
      and "on:\n  push:\n    branches: [wp-e3/e3b-m2s5-bridge]\n" in E3BW and "e3b-r1" not in E3BW)
check("B0 R1 workflow equals the E3b workflow apart from trigger, names, artifact names and the header comment",
      [l for l in WFT.splitlines() if not l.startswith("#")] ==
      [l.replace("e3b-bridge-functional", "e3b-r1-publication").replace("wp-e3/e3b-m2s5-bridge", "wp-e3/e3b-r1-publication")
        .replace("E3b - M2S5 5G-TSN bridge functional smoke (one authorised simulation)",
                 "E3b-R1 - M2S5 5G-TSN bridge functional smoke, publication correction (one authorised simulation)")
        .replace("name: E3b trigger", "name: E3b-R1 trigger").replace("name: E3b verdict", "name: E3b-R1 verdict")
        .replace("e3b-diagnostics-run", "e3b-r1-diagnostics-run").replace("e3b-raw-m2s5-run", "e3b-r1-raw-m2s5-run")
       for l in E3BW.splitlines() if not l.startswith("#")])
r = git(REPO, "diff", "--name-status", E3B_COMMIT)
changed = [line.split("\t") for line in r.stdout.splitlines()]
check("B0 diff against the original E3b commit: only ci/tier2/** and the added R1 workflow (working tree)",
      r.returncode == 0 and all(p.startswith("ci/tier2/") or (p == ".github/workflows/e3b-r1-publication.yml" and s == "A")
                                for s, p in changed), changed)
r = git(REPO, "diff", "--name-status", E3B_COMMIT, "--", "ci/tier2/session", "ci/tier2/steps/sim.sh", "ci/tier2/steps/oracle.sh",
        "ci/tier2/py/m2s5_oracle.py", "ci/tier2/py/u1_oracle.py", "ci/tier2/py/seal.py", "ci/tier2/ref-e3b-r181c-run0.sha256",
        "ci/tier2/pins-tier2.env")
check("B0 R1 leaves the simulation runner, the oracle adapters, sealing and the reference hashes unchanged (vs 4ed6759)",
      r.returncode == 0 and r.stdout == "", r.stdout)
r = git(REPO, "diff", "-U0", E3B_COMMIT, "--", "ci/tier2/pins-e3b.env")
chg = [l for l in r.stdout.splitlines() if l[:1] in "+-" and not l.startswith(("+++", "---")) and not l[1:].startswith("#")]
check("B0 R1 pin changes are identity only (branch, parent, workflow, frozen workflows, label); simulation and limit pins unchanged",
      {l[1:].split("=")[0] for l in chg} == {"EXP_BRANCH", "EXP_PARENT", "EXP_WORKFLOW", "EXP_FROZEN", "EXP_LABEL"}, chg)
r = git(REPO, "diff", "--name-status", BASELINE, "--", "ci/tier1", ".github/workflows/tier0-python.yml",
        ".github/workflows/tier1-full-stack.yml", "simulations", "src", "migration", "nix", "flake.nix", "flake.lock")
check("B0 tier-0, tier-1, sources, configurations, evaluators, migration evidence and Nix files unchanged vs the baseline",
      r.returncode == 0 and r.stdout == "", r.stdout[:300])
check("B0 E3a branch identity: the parent commit is the accepted E3a commit on the baseline",
      git(REPO, "rev-parse", f"{E3A_PARENT}^").stdout.strip() == BASELINE)
RS = open(os.path.join(SESSION, "run-sim.sh")).read()
check("B0 run-sim: fixed experiment table (e3a M2S4U, e3b M2S5, anything else refused) and the reviewed argument vector",
      "  e3a) CFG=M2S4U ;;\n  e3b) CFG=M2S5 ;;\n  *) die \"unknown experiment '$EXP'\" ;;" in RS
      and '-u Cmdenv -f omnetpp.ini -c "$CFG" --repeat=10 -r 0)' in RS
      and 'FULL=("$OPP" "${ARGV[@]}" --result-dir="$RESDIR" --cmdenv-express-mode=true)' in RS and 'RESDIR="$RAW/runs/$CFG"' in RS)
M2S5 = git(REPO, "show", f"{BASELINE}:simulations/m2/m2s5.sh").stdout
check("B0 the argument vector equals the reviewed simulations/m2/m2s5.sh run() at the baseline (apart from -c / -r values)",
      '-l "$NASCTIME/src/nasctime/m2/nasctime_m2" -l "$SIMU5G_ROOT/src/simu5g"' in M2S5
      and '-n "$NASCTIME/simulations:$NASCTIME/src:$SIMU5G_ROOT/src:$INET_ROOT/src" -x nasctime.nodes' in M2S5
      and '-u Cmdenv -f omnetpp.ini -c "$1" --repeat=10 -r "$2" --result-dir="$OUT/runs/$1"' in M2S5
      and "--cmdenv-express-mode=true" in M2S5, "baseline m2s5.sh not readable" if not M2S5 else "")
INI = git(REPO, "show", f"{BASELINE}:simulations/m2/omnetpp.ini").stdout
check("B0 the reviewed configuration M2S5 exists unchanged at the baseline and the network is M1Bridge",
      "[Config M2S5]\n" in INI and "network = nasctime.simulations.m1.M1Bridge" in git(REPO, "show", f"{BASELINE}:simulations/m1/omnetpp.ini").stdout + INI)
check("B0 pins: M2S5 run 0 of --repeat=10, 5 s, one run, approved limits, m2s5 oracle",
      PB["EXP_ID"] == "e3b" and PB["EXP_BRANCH"] == "wp-e3/e3b-r1-publication" and PB["EXP_PARENT"] == E3B_COMMIT
      and PB["EXP_LABEL"] == "E3b-R1" and PB["EXP_WORKFLOW"] == ".github/workflows/e3b-r1-publication.yml"
      and PB["EXP_BASELINE"] == BASELINE and PB["SIM_CONFIG"] == "M2S5" and PB["SIM_RUN"] == "0" and PB["SIM_REPEAT"] == "10"
      and PB["SIM_TIME_LIMIT"] == "5s" and PB["SIM_MAX_RUNS"] == "1" and PB["SIM_NETWORK"] == "nasctime.simulations.m1.M1Bridge"
      and PB["SIM_WALL_CAP_S"] == "600" and PB["SIM_WATCHDOG_LIMIT_B"] == "500000000" and PB["SIM_ACCEPT_LIMIT_B"] == "200000000"
      and PB["ORACLE"] == "m2s5"
      and PB["EXP_FROZEN"].split() == [".github/workflows/e3a-functional-smoke.yml", ".github/workflows/e3b-bridge-functional.yml"])
refm = git(REPO, "show", f"{BASELINE}:simulations/results/simu5g-1.8.1/out-r181c-m2/m2/M2-S5/raw-outputs.sha256").stdout
want = sorted(re.sub(r"  \./", "  ", line) for line in refm.splitlines() if "M2S5-0/" in line or "/M2S5/0." in line)
have = sorted(line for line in open(os.path.join(T2, "ref-e3b-r181c-run0.sha256")).read().splitlines() if line)
check("B0 E-9 reference list = the run-0 entries of the committed R181c (Simu5G 1.8.1) M2-S5 raw-outputs.sha256 (35 files)",
      have == want and len(have) == 35, f"{len(have)} vs {len(want)}")
check("B0 E-9 reference covers the expected M2S5 run-0 result layout (9 PCAP, 24 CSV, sca, vec)",
      sum(n.endswith(".pcapng") for n in synth5.names()) == 9 and sum(n.endswith(".csv") for n in synth5.names()) == 24
      and len(synth5.names()) == 36)
for d, _, fs in os.walk(T2):
    for f in fs:
        if f.endswith(".sh"):
            p = os.path.join(d, f)
            r = subprocess.run(["bash", "-n", p], capture_output=True, text=True)
            check(f"B0 bash -n {os.path.relpath(p, T2)}", r.returncode == 0, r.stderr)

# ======================================================================= B1 experiment-specific authorisation
for exp, extra, want_rc in (("e3c", {}, 3), ("", {}, 3)):
    t = tempfile.mkdtemp(prefix="e3bx-")
    r = run(["bash", os.path.join(STEPS, "identity.sh")], clean_env(RUNNER_TEMP=t, T2_EXPERIMENT=exp or "M2S5", **extra))
    check(f"B1 [stand-in] unknown experiment '{exp or 'M2S5'}' refused by lib/t2common.sh (exit 3, nothing created)",
          r.returncode == want_rc and not os.listdir(t), r.stdout + r.stderr)
    shutil.rmtree(t)


def tree_with_pins(**over):
    """a copy of ci/ with the given e3b pin values replaced (to prove the step refuses them)"""
    t = tempfile.mkdtemp(prefix="e3bpin-")
    shutil.copytree(os.path.join(REPO, "ci"), f"{t}/r/ci", ignore=shutil.ignore_patterns("__pycache__"))
    p = f"{t}/r/ci/tier2/pins-e3b.env"
    s = open(p).read()
    for k, v in over.items():
        s, n = re.subn(rf"^{k}=.*$", f"{k}={v}", s, flags=re.M)
        assert n == 1, k
    open(p, "w").write(s)
    os.makedirs(f"{t}/rt")
    return t


for label, over in (("configuration M2S4U", {"SIM_CONFIG": "M2S4U"}), ("configuration M2S5-frag", {"SIM_CONFIG": "M2S5-frag"}),
                    ("configuration M2S4", {"SIM_CONFIG": "M2S4"}), ("run 1", {"SIM_RUN": "1"}), ("two runs", {"SIM_MAX_RUNS": "2"}),
                    ("--repeat=1", {"SIM_REPEAT": "1"})):
    t = tree_with_pins(**over)
    r = run(["bash", f"{t}/r/ci/tier2/steps/sim.sh"], clean_env(RUNNER_TEMP=f"{t}/rt", T2_EXPERIMENT="e3b"))
    check(f"B1 [stand-in] e3b pins with {label} -> the simulation step refuses before anything is created",
          r.returncode == 1 and "do not authorise exactly M2S5 run 0" in r.stdout and not os.path.exists(f"{t}/rt/e3b/raw"),
          r.stdout[-300:] + r.stderr[-300:])
    shutil.rmtree(t)
t = tree_with_pins(EXP_ID="e3a")
r = run(["bash", f"{t}/r/ci/tier2/steps/identity.sh"], clean_env(RUNNER_TEMP=f"{t}/rt", T2_EXPERIMENT="e3b"))
check("B1 [stand-in] pins of another experiment loaded for e3b -> refused (exit 3)", r.returncode == 3, r.stdout)
shutil.rmtree(t)
for cfg in ("M2S4U", "M2S4", "M2S5-frag"):
    r = run([sys.executable, "-I", os.path.join(PYD, "evaluate_t2.py")], clean_env(
        T2_EXPERIMENT="e3b", SIM_CONFIG=cfg, EV="/x", REC="/x", RAW="/x", E3="/x", REPO=REPO, WS="/x"))
    check(f"B1 evaluator refuses SIM_CONFIG={cfg} for e3b", r.returncode != 0 and "does not authorise" in r.stderr, r.stderr[-200:])
r = run([sys.executable, "-I", os.path.join(PYD, "rawpub.py"), "e3c", *["/x"] * 6, "1", "/x/r"], clean_env())
check("B1 raw publisher refuses an unknown experiment", r.returncode != 0 and "unknown experiment" in r.stderr)

# ======================================================================= B2 trigger and commit identity (e3b rules)
t = tempfile.mkdtemp(prefix="e3bid-")
git(t, "init", "-q", "-b", "main")
for f in ("a.txt", "ci/tier1/x", "ci/tier2/x.sh", ".github/workflows/e3a-functional-smoke.yml", ".github/workflows/e3b-bridge-functional.yml"):
    os.makedirs(os.path.dirname(f"{t}/{f}") or t, exist_ok=True)
    open(f"{t}/{f}", "w").write("base\n")
git(t, "add", "-A")
git(t, "commit", "-qm", "baseline")
BASE = git(t, "rev-parse", "HEAD").stdout.strip()
open(f"{t}/ci/tier2/e3a.py", "w").write("e3a\n")
git(t, "add", "-A")
git(t, "commit", "-qm", "e3a")
PARENT = git(t, "rev-parse", "HEAD").stdout.strip()


def ident_commit(changes):
    git(t, "checkout", "-q", "-B", "e", PARENT)
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


IDENV = {k: PB[k] for k in ("EXP_BRANCH", "EXP_WORKFLOW", "EXP_SCOPE", "EXP_ALLOW_MODIFIED", "EXP_FROZEN")}
IDENV.update(GITHUB_EVENT_NAME="push", GITHUB_REF="refs/heads/wp-e3/e3b-r1-publication", GITHUB_RUN_ATTEMPT="1")
GOOD = [("add", PB["EXP_WORKFLOW"]), ("mod", "ci/tier2/x.sh"), ("add", "ci/tier2/py/new.py")]
for label, changes, over, want in (
        ("authorised push: workflow added, shared tier-2 files modified and added", GOOD, {}, 0),
        ("pull_request event", GOOD, {"GITHUB_EVENT_NAME": "pull_request"}, 1),
        ("the E3a branch", GOOD, {"GITHUB_REF": "refs/heads/wp-e3/e3a-m2s4u-smoke"}, 1),
        ("the original E3b branch", GOOD, {"GITHUB_REF": "refs/heads/wp-e3/e3b-m2s5-bridge"}, 1),
        ("frozen original E3b workflow modified", GOOD + [("mod", ".github/workflows/e3b-bridge-functional.yml")], {}, 1),
        ("second attempt", GOOD, {"GITHUB_RUN_ATTEMPT": "2"}, 1),
        ("frozen E3a workflow modified", GOOD + [("mod", ".github/workflows/e3a-functional-smoke.yml")], {}, 1),
        ("tier-1 file modified", GOOD + [("mod", "ci/tier1/x")], {}, 1),
        ("file outside the scope deleted", GOOD + [("del", "a.txt")], {}, 1),
        ("new file outside the scope", GOOD + [("add", "simulations/m2/new.ini")], {}, 1),
        ("R1 workflow missing", [("mod", "ci/tier2/x.sh")], {}, 1)):
    sha = ident_commit(changes)
    env = clean_env(**{**IDENV, "EXP_PARENT": PARENT, "EXP_BASELINE": BASE, "GITHUB_SHA": sha, **over})
    r = run([sys.executable, "-I", os.path.join(PYD, "identity.py"), t, f"{WORK}/id.txt"], env)
    check(f"B2 identity [{label}] -> {'PASS' if want == 0 else 'FAIL'}", r.returncode == want, r.stdout[-400:])
sha = ident_commit(GOOD)
r = run([sys.executable, "-I", os.path.join(PYD, "identity.py"), t, f"{WORK}/id.txt"],
        clean_env(**IDENV, EXP_PARENT=BASE, EXP_BASELINE=BASE, GITHUB_SHA=sha))
check("B2 identity: parent is not the authorised parent (the original E3b commit) -> FAIL", r.returncode == 1)
shutil.rmtree(t)

# ======================================================================= B3 runner for M2S5 and the monitoring paths (stand-in)
FAKE_OPP = r'''#!/bin/bash
# stand-in simulator for the offline tests (never a simulation)
echo "$*" >> "$FAKE_CALLS"
if [[ " $* " == *" -q runconfig"* ]]; then
  printf 'Config: M2S5\nRun 0: $repetition=0\n\tnetwork = nasctime.simulations.m1.M1Bridge\n\tsim-time-limit = 5s\n\tseed-set = 0\nEnd.\n'
  exit 0
fi
rd=""; for a in "$@"; do case $a in --result-dir=*) rd=${a#--result-dir=} ;; esac; done
mkdir -p "$rd"
echo "Preparing for running configuration M2S5, run #0..."
case "${FAKE_MODE:-ok}" in
  ok) echo data > "$rd/0.sca"; echo "<!> Simulation time limit reached -- at t=5s, event #10"; echo; echo "Calling finish() at end of Run #0..."; echo; echo "End."; exit 0 ;;
  short) exit 0 ;;
  slow) echo data > "$rd/0.sca"; sleep 4; touch "$FAKE_EV/ended"; exit 0 ;;
  hang) sleep 60; exit 0 ;;
  big) head -c 50000 /dev/zero > "$rd/big.bin"; sleep 60; exit 0 ;;
esac
'''


def sim_env(mode="ok", du=None):
    t = tempfile.mkdtemp(prefix="e3brs-")
    ws, repo = f"{t}/ws", f"{t}/repo"
    om, inet, s5 = f"{ws}/omnetpp-6.5.0", f"{ws}/inet-4.7.0", f"{ws}/simu5g-1.8.1"
    for d in (f"{om}/bin", f"{om}/lib", f"{inet}/src", f"{s5}/src", f"{repo}/simulations/m2", f"{repo}/src/nasctime/m2", f"{t}/fb", f"{t}/ev"):
        os.makedirs(d)
    open(f"{om}/bin/opp_run", "w").write(FAKE_OPP)
    os.chmod(f"{om}/bin/opp_run", 0o755)
    for f in (f"{inet}/src/libINET.so", f"{s5}/src/libsimu5g.so", f"{repo}/src/nasctime/m2/libnasctime_m2.so", f"{om}/lib/liboppsim.so"):
        open(f, "w").write("stand-in\n")
    open(f"{repo}/simulations/m2/omnetpp.ini", "w").write("[Config M2S5]\n")
    fb = f"{t}/fb"
    open(f"{fb}/ld.so", "w").write('#!/bin/sh\nprintf "\\tlibc.so.6 => /nix/store/x-glibc/lib/libc.so.6 (0x0)\\n"\n')
    open(f"{fb}/patchelf", "w").write(f"#!/bin/sh\necho {fb}/ld.so\n")
    shims = ["ld.so", "patchelf"]
    if du:
        open(f"{fb}/du", "w").write(du)
        shims.append("du")
    for x in shims:
        os.chmod(f"{fb}/{x}", 0o755)
    env = clean_env(PATH=f"{om}/bin:{fb}:" + os.environ["PATH"], OMNETPP_ROOT=om, INET_ROOT=inet, SIMU5G_ROOT=s5,
                    FAKE_MODE=mode, FAKE_CALLS=f"{t}/calls.txt", FAKE_EV=f"{t}/ev", REAL_DU=shutil.which("du"))
    return t, ws, repo, env


def rs(t, ws, repo, env, mode, exp="e3b", cap="600", limit="500000000", timeout=120):
    os.makedirs(f"{t}/raw", exist_ok=True)
    return run(["bash", os.path.join(SESSION, "run-sim.sh"), mode, exp, repo, ws, f"{t}/raw", f"{t}/rec", f"{t}/ev", cap, limit, "1", "5"],
               env, timeout=timeout)


def ctlkv(t):
    d = {}
    for line in open(f"{t}/rec/sim-control-sim.txt"):
        if ": " in line:
            k, v = line.rstrip("\n").split(": ", 1)
            d.setdefault(k, v)
    return d


t, ws, repo, env = sim_env()
r = rs(t, ws, repo, env, "preflight")
expected = [f"{ws}/omnetpp-6.5.0/bin/opp_run", "-l", f"{repo}/src/nasctime/m2/nasctime_m2", "-l", f"{ws}/simu5g-1.8.1/src/simu5g",
            "-n", f"{repo}/simulations:{repo}/src:{ws}/simu5g-1.8.1/src:{ws}/inet-4.7.0/src", "-x", "nasctime.nodes",
            "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", "M2S5", "--repeat=10", "-r", "0"]
nul = [x.decode() for x in open(f"{t}/rec/argv-preflight.nul", "rb").read().split(b"\0")[:-1]]
check("B3 [stand-in] e3b pre-flight: exact reviewed vector with -c M2S5 -q runconfig, configuration dump written",
      r.returncode == 0 and nul == expected + ["-q", "runconfig"] and "Config: M2S5" in open(f"{t}/raw/effective-config.txt").read(),
      r.stderr + str(nul))
r = rs(t, ws, repo, env, "sim")
argv = [x.decode() for x in open(f"{t}/rec/argv-sim.nul", "rb").read().split(b"\0")[:-1]]
c = ctlkv(t)
check("B3 [stand-in] e3b simulation: exactly one start, -c M2S5, result dir runs/M2S5, log run-M2S5.log, exit 0",
      r.returncode == 0 and argv == expected + [f"--result-dir={t}/raw/runs/M2S5", "--cmdenv-express-mode=true"]
      and os.path.exists(f"{t}/raw/run-M2S5.log") and open(f"{t}/calls.txt").read().count("--result-dir") == 1
      and c.get("experiment") == "e3b authorised_configuration: M2S5", r.stderr + str(c))
check("B3 [stand-in] immediate initial and final measurements numeric; unavailable maxima NOT MEASURED, never 0",
      c.get("initial_output_bytes", "").isdigit() and c.get("final_output_bytes", "").isdigit()
      and (c.get("in_run_samples") != "0" or (c.get("sampled_max_output_bytes") == "NOT MEASURED"
                                               and c.get("sampled_peak_vmhwm_kib") == "NOT MEASURED")), c)
wd = open(f"{t}/rec/watchdog.tsv").read().splitlines()
check("B3 [stand-in] watchdog record: header, initial row first, final row last",
      wd[0] == "utc\telapsed_s\tkind\toutput_bytes\tvmhwm_kib\tprocess_alive" and wd[1].split("\t")[2] == "initial"
      and wd[-1].split("\t")[2] == "final", wd)
shutil.rmtree(t)
t, ws, repo, env = sim_env()
assert rs(t, ws, repo, env, "preflight").returncode == 0
r = rs(t, ws, repo, env, "sim", exp="e3a")
check("B3 [stand-in] e3b pre-flight followed by an e3a simulation request -> -c M2S4U, never another configuration than the "
      "experiment's own (argument vector fixed per experiment)", "-c\0M2S4U" in open(f"{t}/rec/argv-sim.nul", "rb").read().decode()
      if os.path.exists(f"{t}/rec/argv-sim.nul") else r.returncode == 3)
shutil.rmtree(t)
t, ws, repo, env = sim_env()
for exp in ("e3c", "M2S5", ""):
    r = rs(t, ws, repo, env, "preflight", exp=exp)
    check(f"B3 [stand-in] run-sim refuses experiment '{exp}' (exit 3, nothing started)",
          r.returncode == 3 and "unknown experiment" in r.stderr and not os.path.exists(f"{t}/calls.txt"), r.stderr)
shutil.rmtree(t)

# short-lived process: ends before the first poll; monitoring must still be complete and numeric
t, ws, repo, env = sim_env("short")
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
r = rs(t, ws, repo, env, "sim")
c = ctlkv(t)
check("B3 [stand-in] short-lived process: normal completion (exit 0, not terminated), numeric initial and final values, "
      "sampled maxima numeric or NOT MEASURED", r.returncode == 0 and c.get("watchdog_terminated") == "no"
      and c.get("initial_output_bytes", "").isdigit() and c.get("final_output_bytes", "").isdigit()
      and all(c.get(k, "").isdigit() or c.get(k) == "NOT MEASURED" for k in ("sampled_max_output_bytes", "sampled_peak_vmhwm_kib"))
      and (c.get("in_run_samples") != "0" or c.get("sampled_max_output_bytes") == "NOT MEASURED"), c)
shutil.rmtree(t)
# a process running several polls: in-run samples counted, maxima numeric
t, ws, repo, env = sim_env("slow")
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
r = rs(t, ws, repo, env, "sim")
c = ctlkv(t)
check("B3 [stand-in] longer process: in-run samples > 0, sampled maximum and VmHWM numeric, normal completion",
      r.returncode == 0 and int(c.get("in_run_samples", "0")) >= 2 and c.get("sampled_max_output_bytes", "").isdigit()
      and c.get("sampled_peak_vmhwm_kib", "").isdigit() and c.get("watchdog_terminated") == "no", c)
shutil.rmtree(t)
# measurement failure while the process is alive -> terminate (initial sample and in-run samples)
DU_BAD = "#!/bin/sh\necho 'n/a'\n"
t, ws, repo, env = sim_env("hang", du=DU_BAD)
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
t0 = time.time()
r = rs(t, ws, repo, env, "sim")
c = ctlkv(t)
check("B3 [stand-in] non-numeric measurement while the simulation is alive -> terminated immediately (exit 4), evidence kept, "
      "reported as a monitoring failure", r.returncode == 4 and "non-numeric" in c.get("watchdog_terminated", "")
      and c.get("initial_output_bytes") == "NOT NUMERIC" and time.time() - t0 < 30 and os.path.exists(f"{t}/raw/run-M2S5.log"), c)
shutil.rmtree(t)
# du fails (empty output, error exit) only from the second call on: an in-run failure while alive -> terminated
DU_LATER = ('#!/bin/sh\nn=$(cat "$FAKE_EV/du.n" 2>/dev/null || echo 0); n=$((n+1)); echo $n > "$FAKE_EV/du.n"\n'
            '[ "$n" -le 1 ] && exec "$REAL_DU" "$@"\nexit 1\n')
t, ws, repo, env = sim_env("hang", du=DU_LATER)
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
os.remove(f"{t}/ev/du.n") if os.path.exists(f"{t}/ev/du.n") else None
r = rs(t, ws, repo, env, "sim")
c = ctlkv(t)
check("B3 [stand-in] measurement failure during the run (alive) -> terminated (exit 4), initial value numeric",
      r.returncode == 4 and "measurement failed" in c.get("watchdog_terminated", "") and c.get("initial_output_bytes", "").isdigit(), c)
shutil.rmtree(t)
# du fails only once the process has ended: not a monitoring failure while running, but the final value is reported non-numeric
DU_ENDED = '#!/bin/sh\n[ -e "$FAKE_EV/ended" ] && exit 1\nexec "$REAL_DU" "$@"\n'
t, ws, repo, env = sim_env("slow", du=DU_ENDED)
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
r = rs(t, ws, repo, env, "sim")
c = ctlkv(t)
check("B3 [stand-in] measurement failure after the process ended -> not terminated (normal completion), final value reported "
      "NOT NUMERIC (E-4 then fails)", r.returncode == 0 and c.get("watchdog_terminated") == "no"
      and c.get("final_output_bytes") == "NOT NUMERIC", c)
shutil.rmtree(t)
t, ws, repo, env = sim_env("big")
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
r = rs(t, ws, repo, env, "sim", limit="20000")
c = ctlkv(t)
check("B3 [stand-in] output above the emergency limit -> terminated (exit 4)",
      r.returncode == 4 and "exceeds the watchdog limit" in c.get("watchdog_terminated", ""), c)
shutil.rmtree(t)
t, ws, repo, env = sim_env("hang")
assert rs(t, ws, repo, dict(env, FAKE_MODE="ok"), "preflight").returncode == 0
r = rs(t, ws, repo, env, "sim", cap="2")
c = ctlkv(t)
check("B3 [stand-in] wall-time cap -> process group terminated (exit 4), sampled values numeric",
      r.returncode == 4 and "exceeds the cap" in c.get("watchdog_terminated", "") and c.get("sampled_max_output_bytes", "").isdigit(), c)
shutil.rmtree(t)

# ======================================================================= B4 the M2-S5 oracle adapter
ORA = os.path.join(PYD, "m2s5_oracle.py")


def oracle(raw, check_dir=CHECK):
    o = tempfile.mkdtemp(prefix="e3bo-")
    r = run([sys.executable, "-I", "-B", ORA, raw, check_dir, f"{o}/o.json", f"{o}/o.txt"], clean_env(), timeout=300)
    j = json.load(open(f"{o}/o.json")) if os.path.exists(f"{o}/o.json") else {}
    txt = open(f"{o}/o.txt").read() if os.path.exists(f"{o}/o.txt") else ""
    shutil.rmtree(o)
    return r, j, txt


t = tempfile.mkdtemp(prefix="e3bor-")
synth5.layout(f"{t}/raw")
r, j, txt = oracle(f"{t}/raw")
req = j.get("requirements", {})
check("B4 [reviewed][synthetic] full import chain of check_m2s5 (check_m2s4, pcapng, inet_model, oracle_m2s3, gate_m2s5, gate_v0) "
      "loads offline; main() not executed; per-run requirements found in the reviewed source; L_REF = 50 000 ps",
      j and all(v for k, v in req.items() if k not in ("checker_path", "L_REF_ps")) and req.get("L_REF_ps") == 50000
      and req.get("checker_path") == os.path.realpath(os.path.join(CHECK, "check_m2s5.py"))
      and not [p for p in j.get("problems", []) if "import" in p or "requirements" in p], j.get("problems"))
check("B4 [reviewed][synthetic] empty-traffic M2S5 layout: the reviewed oracle completes, every expected row is reported, and "
      "the result is FAIL through its own non-vacuity conditions (C1, C2, S1, S2, P1, P2)",
      r.returncode == 1 and j["result"] == "FAIL" and sorted(j["rows"]) == sorted(["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "S1", "S2", "P1", "P2"])
      and all(j["rows"][k]["result"] == "FAIL" for k in ("C1", "C2", "S1", "S2", "P1", "P2")), j.get("rows"))
check("B4 [reviewed][synthetic] partial and NOT EVALUATED reporting: C8 and P1 scope 'partial' with their evaluated and NOT "
      "EVALUATED parts; S3 NOT EVALUATED; the reviewed P1 text 'byte-identical to M2S4: False' explained as NOT EVALUATED",
      j["rows"]["C8"]["scope"] == "partial" and j["rows"]["P1"]["scope"] == "partial" and "S3" in j["not_evaluated"]
      and "row S3: NOT EVALUATED" in txt and "row C8 NOT EVALUATED:" in txt and "row P1 NOT EVALUATED:" in txt
      and "'engine log byte-identical to M2S4: False'" in txt and all(j["rows"][k]["scope"] == "full" for k in j["rows"] if k not in ("C8", "P1")))
check("B4 [reviewed][synthetic] exchange, delivery and sample counts reported (all 0 here)",
      sorted(j.get("counts", {})) == sorted(["gm_syncs", "gm_follow_ups", "slave_syncs", "slave_follow_ups", "n3_follow_ups",
                                             "nwtt_link_delay_exchanges", "slave_pdelay_samples", "slave_clock_samples",
                                             "slave_model_steps"]) and set(j["counts"].values()) <= {0, None}, j.get("counts"))
check("B4 [reviewed][synthetic] no file opened outside the raw directory, the checker directory and the Python runtime "
      "(no historical or private results)", j.get("files_opened_outside_raw_and_checker") == [], j.get("files_opened_outside_raw_and_checker"))
for label, mut in (("N3 PCAP missing", lambda raw: os.remove(f"{raw}/runs/M2S5/pcap/M2S5-0/M1Bridge.upf.pcapRecorder[0].pcapng")),
                   ("talker PCAP truncated", lambda raw: open(f"{raw}/runs/M2S5/pcap/M2S5-0/M1Bridge.talker.pcapRecorder[0].pcapng", "wb").write(b"\x0a\x0d\x0d\x0a\x10")),
                   ("NW-TT syncIn log missing", lambda raw: os.remove(next(os.path.join(d, f) for d, _, fs in os.walk(raw) for f in fs if f.endswith("syncIn.sync.csv")))),
                   ("scalar file missing", lambda raw: os.remove(f"{raw}/runs/M2S5/M2S5/0.sca")),
                   ("vector file malformed", lambda raw: open(f"{raw}/runs/M2S5/M2S5/0.vec", "w").write("vector 0 M1Bridge.talker.gptp pdelay:vector ETV\n0\tx\ty\n"))):
    shutil.rmtree(f"{t}/raw2", ignore_errors=True)
    shutil.copytree(f"{t}/raw", f"{t}/raw2")
    mut(f"{t}/raw2")
    r, j, txt = oracle(f"{t}/raw2")
    check(f"B4 [reviewed][synthetic] {label} -> FAIL (never PASS)", r.returncode == 1 and j.get("result") == "FAIL", (j.get("problems"), j.get("rows")))
check("B4 the reviewed checker directory received no bytecode", not os.path.exists(os.path.join(CHECK, "__pycache__")))

MOCK = '''"""MOCK of check_m2s5 for the adapter's offline row-mapping tests only (never the reviewed oracle)."""
import os
import sys
OUT, RUNS4, HASHES4 = sys.argv[1:4]
RUNS = os.path.join(OUT, "runs")
L_REF = @LREF@
SYNC, FU = 0, 8


class Run:
    def __init__(self, runs, cfg, rep):
        assert (cfg, rep) == ("M2S5", 0)
        self.gm, self.sl, self.n3path, self.lup_table_cache, self.V = [1, 2], [1], "n3", {1: 1}, {"pdelay": [1, 2, 3]}


class _Model:
    out = {"fu": [1, 2, 3, 4]}


class C4:
    @staticmethod
    def inner_type(b):
        return (True, FU)


def sel(rows, d, t):
    return rows


def n3_inner(p):
    return [(1, 5, b"x"), (1, 5, b"y")]


def clock_samples(v):
    return [1, 2, 3, 4, 5]


def rows_5gs(R, R4, exp_missing=0):
    # requirement texts the adapter looks for in the reviewed source, reproduced for the mock:
    # res["C1"] = (not probs and n > 0 and n3 > 0   len(fus) == n_sync_gm - exp_missing
    # len(m.out["fu"]) > 0 and not bad_samples and not nonzero   in5gs == 0   ok8 = audit == 0
    # if R4 is not None:   if R4 is not None:   @R4@
    assert R4 is None and exp_missing == 0
    res = {k: (True, "mock " + k) for k in @ROWS@}
    @EXTRA@
    res["_model"] = _Model()
    return res


def main():
    raise SystemExit("main executed")
'''
ROWS12 = '["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "S1", "S2", "P1", "P2"]'


def mock(rows=ROWS12, extra="pass", lref="50000", r4="if R4 is not None:"):
    d = tempfile.mkdtemp(prefix="e3bmock-")
    open(f"{d}/check_m2s5.py", "w").write(MOCK.replace("@ROWS@", rows).replace("@EXTRA@", extra).replace("@LREF@", lref).replace("@R4@", r4))
    return d


for label, kw, want, extra_cond in (
        ("all rows PASS -> PASS, scopes and counts mapped", {}, "PASS",
         lambda j: j["rows"]["C8"]["scope"] == "partial" and j["rows"]["C1"]["scope"] == "full" and j["counts"]["n3_follow_ups"] == 2
         and j["counts"]["slave_model_steps"] == 4 and j["counts"]["gm_syncs"] == 2),
        ("one row FAIL -> FAIL", {"extra": 'res["C4"] = (False, "mock C4 failed")'}, "FAIL", lambda j: j["rows"]["C4"]["result"] == "FAIL"),
        ("a partial row FAIL -> FAIL", {"extra": 'res["P1"] = (False, "mock")'}, "FAIL", lambda j: j["rows"]["P1"]["result"] == "FAIL"),
        ("unexpected extra row (S3 evaluated by a changed checker) -> FAIL", {"extra": 'res["S3"] = (True, "mock")'}, "FAIL",
         lambda j: any("unexpected row set" in p for p in j["problems"])),
        ("a row missing -> FAIL", {"rows": ROWS12.replace(', "P2"', "")}, "FAIL", lambda j: "P2" not in j["rows"]),
        ("reference link delay not 50 000 ps -> FAIL", {"lref": "50001"}, "FAIL", lambda j: any("requirements" in p for p in j["problems"])),
        ("baseline guards changed -> FAIL", {"r4": ""}, "FAIL", lambda j: not j["requirements"]["baseline_parts_guarded_by_R4"]),
        ("checker reads a file outside the raw and checker directories -> FAIL", {"extra": 'open("/etc/hostname").close()'}, "FAIL",
         lambda j: j["files_opened_outside_raw_and_checker"] == ["/etc/hostname"]),
        ("checker calls its own main() -> FAIL (trap)", {"extra": "main()"}, "FAIL", lambda j: any("main()" in p for p in j["problems"]))):
    d = mock(**kw)
    t2 = tempfile.mkdtemp(prefix="e3bmr-")
    os.makedirs(f"{t2}/raw/runs")
    r, j, txt = oracle(f"{t2}/raw", d)
    ok = j.get("result") == want and (r.returncode == 0) == (want == "PASS")
    try:
        ok = ok and extra_cond(j)
    except (KeyError, TypeError) as e:
        ok = False
        j["_err"] = repr(e)
    check(f"B4 [mock] adapter mapping: {label}", ok, (j.get("result"), j.get("problems"), j.get("_err")))
    shutil.rmtree(d)
    shutil.rmtree(t2)
shutil.rmtree(t)

# ======================================================================= B5 raw publication with the N3 PPP capture
RAWPUB = os.path.join(PYD, "rawpub.py")
N3 = "raw/runs/M2S5/pcap/M2S5-0/M1Bridge.upf.pcapRecorder[0].pcapng"
ETH_OK = synth.eth(synth.GPTP, "0aaa00000004", synth.gptp(2, (0x0B, 1), 1))


def n3_file(frames, linktype=204):
    """frames: bytes (downlink, recorded outbound at the UPF: direction 2) or (bytes, direction)"""
    items = [f if isinstance(f, tuple) else (f, 2) for f in frames]
    return synth5.pcapng_linktype([(10 ** 9 + i, d, f) for i, (f, d) in enumerate(items)], linktype)


def pub_fixture(t):
    raw = f"{t}/raw"
    synth5.layout(raw)
    for n in synth5.names():
        if n.endswith(".pcapng"):
            open(f"{raw}/runs/{n}", "wb").write(synth.pcapng([(10 ** 9, 1, ETH_OK)]))
    open(f"{t}/{N3}", "wb").write(n3_file([synth5.n3_ppp_frame()]))
    open(f"{raw}/run-M2S5.log", "w").write("Preparing for running configuration M2S5, run #0...\nEnd.\n")
    open(f"{raw}/effective-config.txt", "w").write("Config: M2S5\nRun 0: $repetition=0\nEnd.\n")
    os.makedirs(f"{t}/rec")
    open(f"{t}/rec/sim-control-sim.txt", "w").write("simulation_exit: 0\n")
    open(f"{t}/rec/lddebug.123", "w").write("     123:\tcalling init: /nix/store/x/libc.so.6\n")
    open(f"{t}/raw-manifest.sha256", "w").write("x  1  ./a\n")


def rawpub(mut=None, limit="250000000"):
    t = tempfile.mkdtemp(prefix="e3bpub-")
    pub_fixture(t)
    if mut:
        mut(t)
    r = run([sys.executable, "-I", RAWPUB, "e3b", f"{t}/raw", f"{t}/rec", t, f"{t}/pub", os.path.join(T1, "lib", "screen.py"), CHECK,
             limit, f"{t}/rep.txt"], clean_env())
    rep = open(f"{t}/rep.txt").read() if os.path.exists(f"{t}/rep.txt") else ""
    pub = sorted(os.path.relpath(os.path.join(d, f), f"{t}/pub") for d, _, fs in os.walk(f"{t}/pub") for f in fs) if os.path.isdir(f"{t}/pub") else None
    unchanged = all(open(os.path.join(t, "pub", p), "rb").read() == open(os.path.join(t, p), "rb").read()
                    for p in (pub or []) if p.startswith("raw/"))
    shutil.rmtree(t)
    return r, rep, pub, unchanged


def n3(*frames, linktype=204):
    def f(t):
        open(f"{t}/{N3}", "wb").write(n3_file(list(frames), linktype))
    return f


F = synth5
UPF, GNB_N3, GNB_EP = (10, 0, 0, 1), (10, 0, 0, 2), (192, 168, 2, 1)   # observed hosted pair: UPF 10.0.0.1 -> gNB 192.168.2.1
HDR, FCS = b"\x7e\xff\x03\x00\x21", b"\x00\x00"


def frame(src=UPF, dst=GNB_EP, udp_payload=None, proto=17, hdr=HDR, fcs=FCS, ident=1, frag=0, raw_ip=None):
    """an N3 PPP frame with full control over every layer"""
    if raw_ip is None:
        payload = udp_payload if udp_payload is not None else F.udp(F.gtpu(F.inner_eth()))
        raw_ip = F.ipv4(src, dst, payload, proto=proto, ident=ident, frag=frag)
    return hdr + raw_ip + fcs


def gtp_bytes(flags=0x34, mtype=0xFF, ext=b"\x00\x00\x00\x85\x01\x00\x05\x00", inner=None, length=None):
    inner = F.inner_eth() if inner is None else inner
    body = (ext if flags & 0x07 else b"") + inner
    return bytes([flags, mtype]) + (len(body) if length is None else length).to_bytes(2, "big") + b"\x00\x00\x00\x01" + body


def frag_frames(payload, split=104, src=UPF, dst=GNB_EP, gap=False):
    a, b = payload[:split], payload[split:]
    ip1 = F.ipv4(src, dst, b"", ident=7, frag=0x2000)
    ip1 = ip1[:2] + (20 + len(a)).to_bytes(2, "big") + ip1[4:] + a
    ip2 = F.ipv4(src, dst, b"", ident=7, frag=(split + (8 if gap else 0)) // 8)
    ip2 = ip2[:2] + (20 + len(b)).to_bytes(2, "big") + ip2[4:] + b
    return [frame(raw_ip=ip1), frame(raw_ip=ip2)]


frag_payload = F.udp(F.gtpu(F.inner_eth(payload=b"\x10" * 200)))
r, rep, pub, unchanged = rawpub()
check("B5 [synthetic] e3b publication: the 36 run files + log + configuration published unchanged; N3 checked under the R1 "
      "policy; the observed hosted pair 10.0.0.1 -> 192.168.2.1 (downlink, direction 2) is accepted and reported",
      r.returncode == 0 and "rawpub_result: PASS" in rep and len([p for p in pub if p.startswith("raw/")]) == 38 and unchanged
      and N3 in pub and "N3 PPP/IPv4/UDP/GTP-U G-PDU policy" in rep and "n3_address_pair: 10.0.0.1 -> 192.168.2.1 direction 2: 1" in rep
      and "n3_gpdu_accepted: 1" in rep and "n3_violation" not in rep, rep[-700:])
for label, mut, expect in (
        ("uplink reverse direction: gNB N3 address 10.0.0.2 -> UPF 10.0.0.1, inbound, UL PDU-session container",
         n3(frame(), (frame(GNB_N3, UPF, F.udp(F.gtpu(F.inner_eth(), pdu_type=1))), 1)),
         ["n3_address_pair: 10.0.0.2 -> 10.0.0.1 direction 1: 1", "n3_gpdu_accepted: 2"]),
        ("downlink to the gNB's N3 PPP address (interface-order variant)", n3(frame(UPF, GNB_N3)),
         ["n3_address_pair: 10.0.0.1 -> 10.0.0.2 direction 2: 1"]),
        ("G-PDU without extension header (serialiser form 0x30)", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth(), ext=False)))),
         ["n3_gtpu_form: no-extension: 1"]),
        ("both UDP ports 2152 (recognised by the reviewed decoder)", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth()), 2152, 2152))),
         ["n3_gpdu_accepted: 1"]),
        ("fragmented datagram reassembled", n3(*frag_frames(frag_payload)), ["n3_gpdu_accepted: 1", "n3_packets: 2"]),
        ("gPTP multicast and broadcast inner destinations", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth(dst=synth.GPTP)))),
                                                              frame(udp_payload=F.udp(F.gtpu(F.inner_eth(dst="ffffffffffff"))))),
         ["n3_gpdu_accepted: 2"]),
        ("a realistic mixed capture: 39 downlink G-PDUs and 5 uplink G-PDUs", n3(*([frame()] * 39 + [(frame(GNB_N3, UPF), 1)] * 5)),
         ["n3_packets: 44", "n3_gpdu_accepted: 44", "n3_address_pair: 10.0.0.1 -> 192.168.2.1 direction 2: 39",
          "n3_address_pair: 10.0.0.2 -> 10.0.0.1 direction 1: 5"])):
    r, rep, pub, _ = rawpub(mut)
    check(f"B5 [synthetic] N3 established class: {label} -> published",
          r.returncode == 0 and "rawpub_result: PASS" in rep and all(e in rep for e in expect) and "n3_violation" not in rep, rep[-700:])
EM = F.udp(gtp_bytes(flags=0x30, mtype=0xFE, inner=b""))
for label, mut, cls in (
        ("Ethernet link type on the N3 file", n3(frame(), linktype=1), "link-type"),
        ("plain PPP link type 9 (INET writes 204)", n3(frame(), linktype=9), "link-type"),
        ("PPP flag missing", n3(frame(hdr=b"\x00\xff\x03\x00\x21")), "ppp-framing"),
        ("address/control compressed", n3(b"\x7e\x00\x21" + frame()[5:]), "ppp-framing"),
        ("PPP protocol IPv6 (0x0057)", n3(frame(hdr=b"\x7e\xff\x03\x00\x57")), "ppp-protocol"),
        ("IP version 6 in an IPv4 frame", n3(frame()[:5] + b"\x65" + frame()[6:]), "ipv4-header"),
        ("IPv4 options (IHL 6)", n3(frame()[:5] + b"\x46" + frame()[6:]), "ipv4-header"),
        ("truncated packet", n3(frame()[:40]), "ipv4-length"),
        ("4-byte packet", n3(b"\x7e\xff\x03\x00"), "truncated"),
        ("no FCS trailer", n3(frame(fcs=b"")), "ppp-trailer"),
        ("3-byte trailer", n3(frame(fcs=b"\x00\x00\x7e")), "ppp-trailer"),
        ("trailing garbage", n3(frame(fcs=b"\x00" * 12)), "ppp-trailer"),
        ("reverse of the observed pair: gNB endpoint 192.168.2.1 as a source", n3((frame(GNB_EP, UPF), 1)), "address-source"),
        ("another private source 172.16.0.1", n3(frame((172, 16, 0, 1), GNB_EP)), "address-source"),
        ("source in 192.168/16 towards an N3 address", n3(frame((192, 168, 1, 1), UPF)), "address-source"),
        ("public destination 8.8.8.8", n3(frame(UPF, (8, 8, 8, 8))), "address-destination"),
        ("private destination outside both ranges (172.16.0.9)", n3(frame(UPF, (172, 16, 0, 9))), "address-destination"),
        ("gNB endpoint reached inbound (direction 1)", n3((frame(), 1)), "address-direction"),
        ("source equals destination", n3(frame(UPF, UPF)), "address-self"),
        ("three N3 addresses", n3(frame(UPF, GNB_N3), frame(UPF, (10, 0, 0, 3))), "address-set"),
        ("N3 addresses in two /24 subnets", n3(frame(UPF, GNB_EP), frame((10, 0, 1, 1), GNB_EP)), "address-set"),
        ("two gNB tunnel endpoints", n3(frame(UPF, GNB_EP), frame(UPF, (192, 168, 3, 1))), "address-set"),
        ("TCP instead of UDP", n3(frame(proto=6)), "ipv4-protocol"),
        ("ICMP", n3(frame(proto=1, udp_payload=b"\x03\x03" + b"\x00" * 30)), "ipv4-protocol"),
        ("UDP length inconsistent", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth()))[:4] + b"\x00\x09" + F.udp(F.gtpu(F.inner_eth()))[6:])), "udp-length"),
        ("UDP ports 53", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth()), 53, 53))), "udp-ports"),
        ("one UDP port not GTP-U (31 -> 53)", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth()), 31, 53))), "udp-ports"),
        ("GTP version 2 flags", n3(frame(udp_payload=F.udp(gtp_bytes(flags=0x54)))), "gtpu-header"),
        ("GTP-U sequence-number flag (0x32), not a Simu5G form", n3(frame(udp_payload=F.udp(gtp_bytes(flags=0x32, ext=b"\x00\x01\x00\x00")))), "gtpu-header"),
        ("GTP-U echo request", n3(frame(udp_payload=F.udp(gtp_bytes(mtype=0x01)))), "gtpu-message-type"),
        ("GTP-U End Marker", n3(frame(udp_payload=EM)), "gtpu-message-type"),
        ("GTP-U length inconsistent", n3(frame(udp_payload=F.udp(gtp_bytes(length=5)))), "gtpu-length"),
        ("second extension header chained", n3(frame(udp_payload=F.udp(gtp_bytes(ext=b"\x00\x00\x00\x85\x01\x00\x05\x40")))), "gtpu-extension"),
        ("extension of length 2", n3(frame(udp_payload=F.udp(gtp_bytes(ext=b"\x00\x00\x00\x85\x02\x00\x05\x00")))), "gtpu-extension"),
        ("unknown extension type", n3(frame(udp_payload=F.udp(gtp_bytes(ext=b"\x00\x00\x00\x40\x01\x00\x05\x00")))), "gtpu-extension"),
        ("truncated extension", n3(frame(udp_payload=F.udp(gtp_bytes(ext=b"\x00\x00\x00\x85", inner=b"")))), "gtpu-extension"),
        ("inner frame of 10 bytes", n3(frame(udp_payload=F.udp(F.gtpu(b"\x0a" * 10)))), "inner-frame"),
        ("inner frame with a real (globally administered) source MAC", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth(src="001122334455"))))), "inner-mac"),
        ("inner frame to an unexpected multicast", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth(dst="01005e000001"))))), "inner-mac"),
        ("incomplete fragment set", n3(frag_frames(frag_payload)[0]), "ipv4-fragment"),
        ("fragments with a gap", n3(*frag_frames(frag_payload, gap=True)), "ipv4-fragment"),
        ("empty N3 capture", n3(), "empty")):
    r, rep, pub, _ = rawpub(mut)
    check(f"B5 [synthetic] N3 refused [{label}] -> class '{cls}' reported, nothing left to upload",
          r.returncode == 1 and "rawpub_result: FAIL" in rep and pub is None and f"n3_violation: {cls}: " in rep, rep[-700:])
for label, mut, why in (
        ("PPP link type on an Ethernet capture", lambda t: open(f"{t}/raw/runs/M2S5/pcap/M2S5-0/M1Bridge.talker.pcapRecorder[0].pcapng", "wb")
         .write(F.pcapng_linktype([(10 ** 9, 1, frame())], 204)), "link type 204"),
        ("token inside the tunnelled payload", n3(frame(udp_payload=F.udp(F.gtpu(F.inner_eth(payload=b"ghp_ABCDEFGHIJKLMNOPQRSTUVWXYZ0123" + b"\x00" * 20))))), "screen matched"),
        ("unexpected extra raw file (another run)", lambda t: open(f"{t}/raw/runs/M2S5/M2S5/1.sca", "w").write("version 3\n"), "unexpected raw files"),
        ("an M2S4U-shaped raw file", lambda t: (os.makedirs(f"{t}/raw/runs/M2S4U/M2S4U"), open(f"{t}/raw/runs/M2S4U/M2S4U/0.sca", "w").write("x\n")), "unexpected raw files"),
        ("compiled library in the raw directory", lambda t: open(f"{t}/raw/runs/M2S5/M2S5/0.vci", "wb").write(b"\x7fELF\x02\x01\x01" + b"\0" * 40), "ELF")):
    r, rep, pub, _ = rawpub(mut)
    check(f"B5 [synthetic] raw publication refused [{label}] and nothing left to upload",
          r.returncode == 1 and "rawpub_result: FAIL" in rep and pub is None and why in rep, rep[-500:])


def many(t):
    frames = [frame()] + [frame((172, 16, 0, i), GNB_EP) for i in range(1, 9)] + [frame(udp_payload=EM), frame(proto=6), frame(fcs=b"")]
    n3(*frames)(t)
    open(f"{t}/raw/runs/M2S5/pcap/M2S5-0/M1Bridge.talker.pcapRecorder[0].pcapng", "wb").write(
        synth.pcapng([(10 ** 9 + i, 1, synth.eth(synth.GPTP, "001122334455", synth.gptp(2, (1, 1), 1))) for i in range(3)]))
    open(f"{t}/raw/runs/M2S5/M2S5/0.vci", "wb").write(b"\x7fELF\x02\x01\x01" + b"\0" * 40)


r, rep, pub, _ = rawpub(many)
ex = [l for l in rep.splitlines() if l.startswith("n3_violation_example: address-source:")]
check("B5 [synthetic] multiple simultaneous violations: every N3 frame is examined, every class counted (address-source 8, "
      "gtpu-message-type 1, ipv4-protocol 1, ppp-trailer 1), examples bounded to 5 per class, the valid frame still counted, and "
      "the Ethernet-capture MAC violations (3) and the ELF file reported in the same run",
      r.returncode == 1 and pub is None and "n3_packets: 12" in rep and "n3_gpdu_accepted: 1" in rep
      and "n3_violation: address-source: 8" in rep and "n3_violation: gtpu-message-type: 1" in rep
      and "n3_violation: ipv4-protocol: 1" in rep and "n3_violation: ppp-trailer: 1" in rep and len(ex) == 5
      and "M1Bridge.talker.pcapRecorder[0].pcapng: mac: 3 packet(s)" in rep and "ELF" in rep, rep[-1500:])

# sealing succeeds, then publication fails: the step exits 1, the raw evidence is left exactly as sealed, nothing is left to
# upload, and the content-check report (with the N3 class diagnostics) reaches the screened diagnostic publication
t = tempfile.mkdtemp(prefix="e3bsp-")
E3D = f"{t}/rt/e3b"
os.makedirs(f"{t}/rt/tier1/publish")
os.makedirs(E3D)
pub_fixture(E3D)
os.rename(f"{E3D}/rec", f"{E3D}/records")
n3(frame(), frame((172, 16, 0, 1), GNB_EP), frame(udp_payload=EM))(E3D)
rs_ = run([sys.executable, "-I", os.path.join(PYD, "seal.py"), "create", f"{E3D}/raw", f"{E3D}/raw-manifest.sha256", f"{E3D}/records/seal.txt"], clean_env())
r = run(["bash", os.path.join(STEPS, "rawpub.sh")], clean_env(RUNNER_TEMP=f"{t}/rt", T2_EXPERIMENT="e3b"))
rv = run([sys.executable, "-I", os.path.join(PYD, "seal.py"), "verify", f"{E3D}/raw", f"{E3D}/raw-manifest.sha256", f"{t}/v.txt"], clean_env())
dg = f"{t}/rt/tier1/publish/e3b-rawpub-check.txt"
dtxt = open(dg).read() if os.path.exists(dg) else ""
check("B5 [synthetic] successful sealing followed by a publication failure: rawpub step exit 1, raw evidence unchanged (seal "
      "verifies), nothing to upload, and the class diagnostics are in the screened diagnostic publication",
      rs_.returncode == 0 and r.returncode == 1 and rv.returncode == 0 and not os.path.exists(f"{E3D}/publish-raw")
      and "n3_violation: address-source: 1" in dtxt and "n3_violation: gtpu-message-type: 1" in dtxt and "rawpub_result: FAIL" in dtxt,
      r.stdout[-800:] + r.stderr[-300:])
for d, _, fs in os.walk(t):
    os.chmod(d, 0o755)
shutil.rmtree(t)

# ======================================================================= B6 evaluation E-1 .. E-9 and the verdict (synthetic records)
EVAL, FINAL, CONCLUDE = os.path.join(PYD, "evaluate_t2.py"), os.path.join(PYD, "final_t2.py"), os.path.join(STEPS, "conclude.sh")
WF_IDS = ["checkout", "t2identity", "setup", "bootstrap", "verify", "runtime", "b_omnetpp", "b_inet", "b_simu5g", "b_nasctime",
          "validate", "srcchanges", "sim", "seal", "oracle", "lockend", "t2lockend", "measure", "evaluate"]
LOG_OK = ("OMNeT++ Discrete Event Simulation  (C) 1992-2025 Andras Varga, OpenSim Ltd.\nSetting up Cmdenv...\n\n"
          "Preparing for running configuration M2S5, run #0...\nSetting up network \"nasctime.simulations.m1.M1Bridge\"...\n"
          "Running simulation...\n\n<!> Simulation time limit reached -- at t=5s, event #2345678\n\nCalling finish() at end of Run #0...\n\nEnd.\n")
ORACLE_PASS = {"result": "PASS", "rows": {k: {"result": "PASS", "detail": "synthetic", "scope": "partial" if k in ("C8", "P1") else "full"}
                                          for k in ["C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "S1", "S2", "P1", "P2"]},
               "partial": {"C8": {}, "P1": {}}, "not_evaluated": {"S3": "x"}, "counts": {"gm_syncs": 40}, "problems": [],
               "files_opened_outside_raw_and_checker": []}


def nulw(p, items):
    open(p, "wb").write(b"".join(x.encode() + b"\0" for x in items))


def full_state():
    t = tempfile.mkdtemp(prefix="e3bev-")
    ci, e3 = f"{t}/tier1", f"{t}/e3b"
    ev, rec, raw = f"{ci}/evidence", f"{e3}/records", f"{e3}/raw"
    ws = f"{ci}/ws"
    for d in (ev, rec, f"{ci}/publish"):
        os.makedirs(d)
    synth5.layout(raw)
    open(f"{raw}/run-M2S5.log", "w").write(LOG_OK)
    open(f"{raw}/effective-config.txt", "w").write("Config: M2S5\nRun 0: $repetition=0\n\tnetwork = nasctime.simulations.m1.M1Bridge\n"
                                                    "\tsim-time-limit = 5s\n\tseed-set = 0\nEnd.\n")
    rows = [{"id": f"C-{i}", "criterion": "x", "result": "PASS", "detail": ""} for i in range(1, 15)]
    rows[12]["result"] = "NOT EVALUATED"
    rows[13]["result"] = "FAIL"
    json.dump({"rows": rows}, open(f"{ev}/c-rows.json", "w"))
    shas = {"opp_run": "a" * 64, "libnasctime_m2.so": "b" * 64, "libsimu5g.so": "c" * 64, "libINET.so": "d" * 64}
    open(f"{ev}/binaries.tsv", "w").write("project\tkind\tpath\tbytes\tsha256\n" + "".join(f"p\tk\tx/{n}\t1\t{s}\n" for n, s in shas.items()))
    paths = {"opp_run": f"{ws}/omnetpp-6.5.0/bin/opp_run", "libnasctime_m2.so": f"{REPO}/src/nasctime/m2/libnasctime_m2.so",
             "libsimu5g.so": f"{ws}/simu5g-1.8.1/src/libsimu5g.so", "libINET.so": f"{ws}/inet-4.7.0/src/libINET.so"}
    open(f"{rec}/binary-identity-sim.tsv", "w").write("role\tpath\tsha256\tbytes\n" + "".join(f"{n}\t{paths[n]}\t{shas[n]}\t1\n" for n in shas))
    labels = ["nix-install", "realise", "probe", "probe-runtime-before", "probe-runtime-after", "build-omnetpp", "build-inet",
              "build-simu5g", "build-nasctime", "validate", "t2-runconfig", "t2-sim"]
    open(f"{ev}/timings.tsv", "w").write("step\tseconds\texit\tstart_epoch\tend_epoch\n" + "".join(f"{x}\t5\t0\t1\t6\n" for x in labels))
    open(f"{ev}/guard.txt", "w").write("guard_terminated: yes\nliveness_checks_ok: 30\nliveness_checks_failed: 0\n")
    open(f"{ev}/lock.txt", "w").write("".join(f"{p} result: PASS\n" for p in ("before-realisation", "after-t2-runconfig", "after-t2-sim", "final", "final-t2")))
    open(f"{ev}/exec-checks.txt", "w").write("x [before t2-sim] ok\n")
    open(f"{rec}/identity.txt", "w").write("head: abc\nidentity_result: PASS\n")
    open(f"{rec}/sim-control-preflight.txt", "w").write("preflight_exit: 0\n")
    open(f"{rec}/sim-control-sim.txt", "w").write("experiment: e3b authorised_configuration: M2S5\nsimulation_started: 1 pid=9\n"
                                                  "initial_output_bytes: 0\nsimulation_exit: 0\nwall_s: 21.400\n"
                                                  "final_output_bytes: 12800000\nin_run_samples: 20\nsampled_max_output_bytes: 12000000\n"
                                                  "sampled_peak_vmhwm_kib: 120000\nobserved_identity_captured: yes\nwatchdog_terminated: no\n")
    base = [paths["opp_run"], "-l", f"{REPO}/src/nasctime/m2/nasctime_m2", "-l", f"{ws}/simu5g-1.8.1/src/simu5g",
            "-n", f"{REPO}/simulations:{REPO}/src:{ws}/simu5g-1.8.1/src:{ws}/inet-4.7.0/src", "-x", "nasctime.nodes",
            "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", "M2S5", "--repeat=10", "-r", "0"]
    nulw(f"{rec}/argv-preflight.nul", base + ["-q", "runconfig"])
    sim = base + [f"--result-dir={raw}/runs/M2S5", "--cmdenv-express-mode=true"]
    nulw(f"{rec}/argv-sim.nul", sim)
    nulw(f"{rec}/observed-cmdline.nul", sim)
    cwd = os.path.realpath(f"{REPO}/simulations/m2")
    open(f"{rec}/observed-cwd.txt", "w").write(cwd + "\n")
    open(f"{rec}/cwd-preflight.txt", "w").write(f"cwd: {cwd}\n")
    for m in ("preflight", "sim"):
        open(f"{rec}/hazards-{m}.txt", "w").write("hazards: none\n")
    open(f"{rec}/lddebug.9", "w").write("".join(f"      9:\tcalling init: {p}\n" for p in (
        "/nix/store/x-glibc/lib/libc.so.6", f"{ws}/omnetpp-6.5.0/lib/liboppsim.so", paths["libnasctime_m2.so"],
        paths["libsimu5g.so"], paths["libINET.so"])))
    open(f"{rec}/sim.started", "w").close()
    json.dump(ORACLE_PASS, open(f"{rec}/oracle.json", "w"))   # synthetic oracle record (mapping tested in B4)
    open(f"{rec}/modified-during-sim.txt", "w").close()
    for x in ("before", "after", "final"):
        open(f"{rec}/git-status-{x}.txt", "w").write("!! src/nasctime/m2/libnasctime_m2.so\n")
    open(f"{rec}/seal.txt", "w").write("manifest_sha256: e\nfiles: 38\ntotal_bytes: 100\nseal_result: PASS\n")
    open(f"{rec}/seal-verify.txt", "w").write("verify_result: PASS\n")
    open(f"{rec}/rawpub-check.txt", "w").write("total_bytes: 100\nfiles: 60\nrawpub_result: PASS\n")
    env = clean_env(EV=ev, REC=rec, RAW=raw, E3=e3, CI=ci, REPO=REPO, WS=ws, **PINS, T2_EXPERIMENT="e3b",
                    STEP_OUTCOMES=json.dumps({i: {"outcome": "success"} for i in WF_IDS}),
                    PUBLISH_OUTCOME="success", T2PUBLISH_OUTCOME="success", RAWPUB_OUTCOME="success", GITHUB_STEP_SUMMARY=f"{t}/sum.md")
    return t, env


def evaluate(t, env, mut=None):
    if mut:
        mut(t, env)
    r1 = run([sys.executable, "-I", EVAL], env)
    r2 = run([sys.executable, "-I", FINAL], env)
    v = open(f"{env['E3']}/verdict.txt").read().strip() if os.path.exists(f"{env['E3']}/verdict.txt") else None
    fin = json.load(open(f"{env['REC']}/e-final.json")) if os.path.exists(f"{env['REC']}/e-final.json") else {"rows": []}
    return v, {x["id"]: x["result"] for x in fin["rows"]}, {x["id"]: x["detail"] for x in fin["rows"]}, r1, r2


t, env = full_state()
v, rows, det, r1, r2 = evaluate(t, env)
check("B6 [synthetic] complete e3b record set -> 'E3b PASS', E-1 .. E-8 PASS, E-9 INFORMATIONAL, final exit 0",
      v == "E3b PASS" and all(rows.get(f"E-{i}") == "PASS" for i in range(1, 9)) and rows.get("E-9") == "INFORMATIONAL" and r2.returncode == 0,
      f"{v} {rows} {r1.stdout[-1500:]} {r1.stderr[-500:]}")
facts = json.load(open(f"{env['REC']}/e-rows.json"))["facts"]
check("B6 [synthetic] E-9 compares all 35 R181c hashes per file (synthetic outputs -> DIFFERS), no whole-result claim",
      len(facts["reference"]) == 35 and set(facts["reference"].values()) == {"DIFFERS"} and "per file only" in
      next(r["criterion"] for r in json.load(open(f"{env['REC']}/e-rows.json"))["rows"] if r["id"] == "E-9"))
check("B6 [synthetic] E-6 detail reports partial rows (C8, P1) and NOT EVALUATED (S3) and the counts",
      "partially evaluated (baseline-dependent parts NOT EVALUATED): C8, P1" in det["E-6"] and "NOT EVALUATED: S3" in det["E-6"]
      and "gm_syncs=40" in det["E-6"], det.get("E-6"))
summ = open(f"{t}/sum.md").read()
check("B6 [synthetic] verdict file e3b-verdict.md and job summary carry the level-2 downlink classification",
      os.path.exists(f"{env['CI']}/publish/e3b-verdict.md")
      and "# E3b-R1: E3b hosted 5G-TSN bridge functional smoke (M2S5, run 0) - publication correction re-run: E3b PASS" in summ
      and "Level-2 hosted functional smoke evidence for the downlink 5G-TSN timing path" in summ and "NOT independent scientific validation" in summ)
shutil.rmtree(t)


def edit(path, a, b):
    def f(t, env):
        p = path.format(**env)
        s = open(p).read()
        assert a in s, (p, a)
        open(p, "w").write(s.replace(a, b))
    return f


def write(path, data):
    def f(t, env):
        open(path.format(**env), "w").write(data)
    return f


def remove(path):
    def f(t, env):
        os.remove(path.format(**env))
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


PF = "E3b PUBLICATION FAILURE (functional rows E-1 .. E-7 PASS; raw evidence sealed and verified, but not published)"
PF_SEAL = "E3b PUBLICATION FAILURE (functional rows E-1 .. E-7 PASS; raw evidence not sealed or not verified)"
CASES = [
    ("short-lived run: no in-run sample, maxima NOT MEASURED -> still PASS (initial and final numeric)",
     both(edit("{REC}/sim-control-sim.txt", "in_run_samples: 20", "in_run_samples: 0"),
          edit("{REC}/sim-control-sim.txt", "sampled_max_output_bytes: 12000000", "sampled_max_output_bytes: NOT MEASURED"),
          edit("{REC}/sim-control-sim.txt", "sampled_peak_vmhwm_kib: 120000", "sampled_peak_vmhwm_kib: NOT MEASURED")), "E3b PASS", {"E-4": "PASS"}),
    ("NOT MEASURED maximum with in-run samples counted", edit("{REC}/sim-control-sim.txt", "sampled_max_output_bytes: 12000000",
                                                             "sampled_max_output_bytes: NOT MEASURED"), "E3b FAIL", {"E-4": "FAIL"}),
    ("initial measurement non-numeric", edit("{REC}/sim-control-sim.txt", "initial_output_bytes: 0", "initial_output_bytes: NOT NUMERIC"),
     "E3b FAIL", {"E-4": "FAIL"}),
    ("final measurement non-numeric", edit("{REC}/sim-control-sim.txt", "final_output_bytes: 12800000", "final_output_bytes: NOT NUMERIC"),
     "E3b FAIL", {"E-4": "FAIL"}),
    ("final output above the emergency limit", edit("{REC}/sim-control-sim.txt", "final_output_bytes: 12800000", "final_output_bytes: 500000001"),
     "E3b FAIL", {"E-4": "FAIL"}),
    ("watchdog monitoring failure", edit("{REC}/sim-control-sim.txt", "watchdog_terminated: no",
                                         "watchdog_terminated: output measurement failed or non-numeric ('') while the simulation was running"),
     "E3b FAIL", {"E-4": "FAIL"}),
    ("simulation stopped at 3 s (another configuration's limit)", edit("{RAW}/run-M2S5.log", "at t=5s,", "at t=3s,"), "E3b FAIL", {"E-4": "FAIL"}),
    ("pre-flight shows M2S4LinkTest", edit("{RAW}/effective-config.txt", "nasctime.simulations.m1.M1Bridge", "nasctime.simulations.m2.M2S4LinkTest"),
     "E3b FAIL", {"E-2": "FAIL"}),
    ("pre-flight selects two runs", edit("{RAW}/effective-config.txt", "Run 0: $repetition=0\n", "Run 0: $repetition=0\nRun 1: $repetition=1\n"),
     "E3b FAIL", {"E-2": "FAIL"}),
    ("argument vector of M2S4U", lambda t, env: nulw(f"{env['REC']}/argv-sim.nul", [x.replace("M2S5", "M2S4U") for x in
     open(f"{env['REC']}/argv-sim.nul", "rb").read().decode().split("\0")[:-1]]), "E3b FAIL", {"E-2": "FAIL"}),
    ("an output of another run", write("{RAW}/runs/M2S5/M2S5/1.sca", "version 3\n"), "E3b FAIL", {"E-3": "FAIL", "E-5": "FAIL"}),
    ("N3 capture missing", remove("{RAW}/runs/M2S5/pcap/M2S5-0/M1Bridge.upf.pcapRecorder[0].pcapng"), "E3b FAIL", {"E-5": "FAIL"}),
    ("empty result file", write("{RAW}/runs/M2S5/M2S5/0.vec", ""), "E3b FAIL", {"E-5": "FAIL"}),
    ("scalar file of M2S4U", edit("{RAW}/runs/M2S5/M2S5/0.sca", "attr configname M2S5", "attr configname M2S4U"), "E3b FAIL", {"E-5": "FAIL"}),
    ("scalar file network M2S4LinkTest", edit("{RAW}/runs/M2S5/M2S5/0.sca", "attr network M1Bridge", "attr network M2S4LinkTest"),
     "E3b FAIL", {"E-5": "FAIL"}),
    ("oracle FAIL", edit("{REC}/oracle.json", '"result": "PASS", "rows"', '"result": "FAIL", "rows"'), "E3b FAIL", {"E-6": "FAIL"}),
    ("oracle record missing although the oracle ran", remove("{REC}/oracle.json"), "E3b FAIL", {"E-6": "FAIL"}),
    ("seal verification failed", edit("{REC}/seal-verify.txt", "PASS", "FAIL"), PF_SEAL, {"E-8": "FAIL"}),
    ("seal failed", edit("{REC}/seal.txt", "seal_result: PASS", "seal_result: FAIL"), PF_SEAL, {"E-8": "FAIL"}),
    ("sealing succeeded, then the raw publication was refused (the hosted E3b outcome)", setenv(RAWPUB_OUTCOME="failure"), PF, {"E-8": "FAIL"}),
    ("raw content check failed", edit("{REC}/rawpub-check.txt", "rawpub_result: PASS", "rawpub_result: FAIL"), PF, {"E-8": "FAIL"}),
    ("publication refused AND oracle FAIL -> functional FAIL", both(setenv(RAWPUB_OUTCOME="failure"),
     edit("{REC}/oracle.json", '"result": "PASS", "rows"', '"result": "FAIL", "rows"')), "E3b FAIL", {"E-6": "FAIL", "E-8": "FAIL"}),
    ("STOP", write("{EV}/STOP", "disk guard\n"), "STOP", {"E-3": "FAIL"}),
    ("guard failure -> infrastructure failure", write("{EV}/GUARD_FAILURE", "dead\n"), "INFRASTRUCTURE FAILURE", {"E-3": "FAIL"}),
    ("NED diagnostic in a failed simulation -> compatibility BLOCKED",
     both(edit("{REC}/sim-control-sim.txt", "simulation_exit: 0", "simulation_exit: 1"),
          write("{RAW}/run-M2S5.log", "Preparing for running configuration M2S5, run #0...\n<!> Error: no such module type 'Foo' -- in module (M1Bridge) (NED)\n")),
     "E3b BLOCKED (OMNeT++ 6.5.0 compatibility; no NED/INI patched)", {"E-4": "FAIL"}),
]
for label, mut, want_v, expect in CASES:
    t, env = full_state()
    v, rows, det, r1, r2 = evaluate(t, env, mut)
    bad = {k: (rows.get(k), w) for k, w in expect.items() if rows.get(k) != w}
    check(f"B6 [synthetic] {label} -> {want_v}", v == want_v and not bad and (r2.returncode == 0) == (want_v == "E3b PASS"),
          f"{v} mismatches={bad} {r1.stderr[-300:]}")
    shutil.rmtree(t)

# ======================================================================= B7 conclusion
for v, d, rw, want in (("E3b PASS", "success", "success", 0), ("E3b PASS", "success", "failure", 1), ("E3b PASS", "failure", "success", 1),
                       (PF, "success", "success", 1), ("E3b FAIL", "success", "success", 1), ("E3a PASS", "success", "success", 1),
                       (None, "success", "success", 1)):
    t = tempfile.mkdtemp(prefix="e3bcc-")
    os.makedirs(f"{t}/e3b")
    if v:
        open(f"{t}/e3b/verdict.txt", "w").write(v + "\n")
    r = run(["bash", CONCLUDE], clean_env(RUNNER_TEMP=t, T2_EXPERIMENT="e3b", UPLOAD_DIAG_OUTCOME=d, UPLOAD_RAW_OUTCOME=rw))
    check(f"B7 conclusion [verdict={v}, diagnostics={d}, raw={rw}] -> exit {want}", (r.returncode == 0) == (want == 0), r.stdout)
    shutil.rmtree(t)

check("B8 the whole suite wrote no bytecode into the reviewed checker directory", not os.path.exists(os.path.join(CHECK, "__pycache__")))
os.chdir(REPO)
shutil.rmtree(WORK, ignore_errors=True)
failed = [n for n, ok in results if not ok]
print(f"\n{len(results) - len(failed)}/{len(results)} checks passed")
if failed:
    print("FAILED:", *failed, sep="\n  ")
sys.exit(1 if failed else 0)
