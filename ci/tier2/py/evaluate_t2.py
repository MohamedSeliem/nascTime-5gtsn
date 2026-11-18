"""Tier-2 acceptance evaluation E-1 .. E-9 of the experiment selected by T2_EXPERIMENT (e3a: M2S4U, e3b: M2S5);
E-8 is completed by final_t2.py after publication.

Separate tier-2 execution-control evaluator: tier-1's own C-14 (which forbids any simulation) is NOT used and NOT
bypassed; tier-1 rows C-1 .. C-12 are taken unchanged from tier-1's evaluator as prerequisites (E-1). Every row is
PASS, FAIL or NOT EVALUATED; NOT EVALUATED is never PASS. Inputs: tier-1 evidence ($EV), the tier-2 records ($REC),
the sealed raw evidence ($RAW), STEP_OUTCOMES and the pins. Output: $REC/e-rows.json.
"""
import hashlib
import json
import os
import re

TIER1_LABELS = {"nix-install", "realise", "probe", "probe-runtime-before", "probe-runtime-after", "build-omnetpp",
                "build-inet", "build-simu5g", "build-nasctime", "validate"}
T2_LABELS = {"t2-runconfig", "t2-sim"}
SIM_RX = re.compile(r"Invoking (smoke_test|test)_|Running simulation|Setting up Cmdenv|Preparing for running configuration|Calling finish\(\)")
BLOCK_RX = re.compile(r"(\.ned\b|NED |ned-path|\.ini\b|ini file|[Uu]nknown parameter|[Nn]o such module type|module type .* not found|"
                      r"[Cc]onfiguration .* not found|[Uu]nknown configuration option|[Cc]annot assign parameter|[Cc]annot load library|"
                      r"undefined symbol|[Ii]ncompatible|[Ss]yntax error)")
E3A_FILES = ["M2S4U/M2S4U/0.sca", "M2S4U/M2S4U/0.vec", "M2S4U/M2S4U/0.vci",
             "M2S4U/m2log/M2S4U-0/M2S4LinkTest.ttA.eth[1].trafficConditionerLayer.engine.pdelay.csv",
             "M2S4U/m2log/M2S4U-0/M2S4LinkTest.ttB.eth[1].trafficConditionerLayer.engine.pdelay.csv",
             "M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttA.pcapRecorder[0].pcapng",
             "M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttB.pcapRecorder[0].pcapng"]
E3A_REF_KEYS = {E3A_FILES[3]: "REF_CSV_TTA", E3A_FILES[4]: "REF_CSV_TTB", E3A_FILES[5]: "REF_PCAP_TTA", E3A_FILES[6]: "REF_PCAP_TTB"}
# Per-experiment facts (fixed; the configuration of each experiment is also fixed in session/run-sim.sh and steps/sim.sh)
SPEC = {
    "e3a": {"config": "M2S4U", "branch": "wp-e3/e3a-m2s4u-smoke", "networks": ("nasctime.simulations.m2.M2S4LinkTest", "M2S4LinkTest"),
            "sca_network": "M2S4LinkTest", "oracle": "unmodified U1 oracle of check_m2s4.py (D = 50 000 ps at both requesters = "
            "PCAP-derived, logged t1..t4 = PCAP, every valid-FCS Pdelay frame terminated, all 11 counters 0, selfTestPassed 1) "
            "plus the adapter's non-vacuity guard", "ref_label": "historical OMNeT++ 6.4.0 reference hashes of the two engine "
            "logs and two PCAP files (identical in M2-S4, R181b, R181c)"},
    "e3b": {"config": "M2S5", "branch": "wp-e3/e3b-m2s5-bridge", "networks": ("nasctime.simulations.m1.M1Bridge", "M1Bridge"),
            "sca_network": "M1Bridge", "oracle": "unmodified reviewed M2-S5 oracle check_m2s5.rows_5gs(Run(RUNS, 'M2S5', 0), "
            "None, exp_missing=0): rows C1..C8, S1, S2, P1, P2 all PASS (C8 and P1 evaluated partially: their M2-S4-baseline "
            "parts are NOT EVALUATED; S3 NOT EVALUATED)", "ref_label": "historical R181c (Simu5G 1.8.1) reference hashes of "
            "all 35 run-0 output files of M2S5, compared per file"},
}


def expected_files(env):
    x = env.get("T2_EXPERIMENT", "e3a")
    if x == "e3a":
        return sorted(E3A_FILES)
    names = [l.split("  ", 1)[1].strip() for l in rd(os.path.join(env["REPO"], env["REF_FILE"])).splitlines() if "  " in l]
    return sorted(names + [f"{SPEC[x]['config']}/{SPEC[x]['config']}/0.vci"])


def reference(env):
    """{run-relative path: reference sha256} of the informational E-9 comparison"""
    if env.get("T2_EXPERIMENT", "e3a") == "e3a":
        return {p: env[k] for p, k in E3A_REF_KEYS.items()}
    ref = {}
    for l in rd(os.path.join(env["REPO"], env["REF_FILE"])).splitlines():
        if "  " in l:
            h, p = l.split("  ", 1)
            ref[p.strip()] = h.strip()
    return ref


def is_num(v):
    return isinstance(v, str) and v.isdigit()


def rd(p, binary=False):
    try:
        with open(p, "rb" if binary else "r", **({} if binary else {"errors": "replace"})) as f:
            return f.read()
    except OSError:
        return b"" if binary else ""


def kv(t):
    d = {}
    for line in t.splitlines():
        if ": " in line:
            k, v = line.split(": ", 1)
            d.setdefault(k.strip(), v.strip())
    return d


def sha(p):
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for b in iter(lambda: f.read(1 << 20), b""):
            h.update(b)
    return h.hexdigest()


def nul(p):
    b = rd(p, binary=True)
    return [x.decode("utf-8", "replace") for x in b.split(b"\0")[:-1]] if b else None


def expected_argv(repo, ws, cfg):
    om, inet, s5 = f"{ws}/omnetpp-6.5.0", f"{ws}/inet-4.7.0", f"{ws}/simu5g-1.8.1"
    base = [f"{om}/bin/opp_run", "-l", f"{repo}/src/nasctime/m2/nasctime_m2", "-l", f"{s5}/src/simu5g",
            "-n", f"{repo}/simulations:{repo}/src:{s5}/src:{inet}/src", "-x", "nasctime.nodes",
            "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", cfg, "--repeat=10", "-r", "0"]
    return base + ["-q", "runconfig"], base + ["--result-dir=", "--cmdenv-express-mode=true"]


def runconfig_facts(txt, cfg):
    runs = re.findall(r"^Run (\d+): (.*)$", txt, re.M)
    entries = {m.group(1).strip(): m.group(2).strip() for m in re.finditer(r"^\t([^\t=][^=]*?) = (.*)$", txt, re.M)}
    return {"has_config": f"Config: {cfg}\n" in txt, "complete": "End." in txt, "runs": runs,
            "network": entries.get("network"), "sim_time_limit": entries.get("sim-time-limit"), "seed_set": entries.get("seed-set")}


def log_facts(txt):
    lines = [l for l in txt.splitlines() if l.strip()]
    prep = [l for l in lines if l.startswith("Preparing for running configuration")]
    lim = re.findall(r"^<!> Simulation time limit reached -- at t=(\S+), event #(\d+)$", txt, re.M)
    return {"preparing": prep, "time_limit": lim, "finish": [l for l in lines if l.startswith("Calling finish() at end of Run #")],
            "last": lines[-1] if lines else "", "errors": [l for l in lines if l.startswith("<!> Error") or "<!> Error" in l],
            "fingerprint": [l for l in lines if "ingerprint" in l]}


def loaded_objects(rec):
    objs = []
    for f in sorted(os.listdir(rec)) if os.path.isdir(rec) else []:
        if f.startswith("lddebug"):
            objs += re.findall(r"calling init: (\S+)", rd(os.path.join(rec, f)))
    return sorted(set(objs))


def evaluate(env):
    EV, REC, RAW = env["EV"], env["REC"], env["RAW"]
    REPO, WS = env["REPO"], env["WS"]
    X = env.get("T2_EXPERIMENT", "e3a")
    if X not in SPEC or env.get("SIM_CONFIG") != SPEC[X]["config"]:
        raise SystemExit(f"evaluate_t2: experiment {X!r} does not authorise configuration {env.get('SIM_CONFIG')!r}")
    SP, CFG = SPEC[X], SPEC[X]["config"]
    EXPECTED_FILES = expected_files(env)
    outcomes = {k: v.get("outcome") for k, v in json.loads(env.get("STEP_OUTCOMES") or "{}").items()}

    def ran(*ids):
        return all(outcomes.get(s) in ("success", "failure") for s in ids)

    def pf(c):
        return "PASS" if c else "FAIL"
    rows, facts = [], {}

    def row(i, what, result, detail, mandatory=True):
        rows.append({"id": i, "criterion": what, "result": result, "mandatory": mandatory,
                     "detail": str(detail).replace("|", "/").replace("\n", " ")[:900]})

    # ---------------------------------------------------------------- E-1 prerequisites and authorised identity
    ident = kv(rd(f"{REC}/identity.txt"))
    try:
        crows = {r["id"]: r for r in json.load(open(f"{EV}/c-rows.json"))["rows"]}
    except (OSError, ValueError, KeyError):
        crows = {}
    need = [f"C-{i}" for i in range(1, 13)]
    cres = {c: crows.get(c, {}).get("result", "absent") for c in need}
    e1 = ident.get("identity_result") == "PASS" and all(v == "PASS" for v in cres.values())
    row("E-1", f"authorised trigger and commit (push of {SP['branch']}, attempt 1, one commit in the authorised scope on "
               "the authorised parent) and tier-1 prerequisites C-1 .. C-12 all PASS",
        pf(e1) if ran("t2identity") else "NOT EVALUATED",
        f"identity={ident.get('identity_result', 'absent')} head={ident.get('head')}; "
        + " ".join(f"{c}={v}" for c, v in cres.items()))

    # ---------------------------------------------------------------- E-2 configuration, run, binary identity
    pre = kv(rd(f"{REC}/sim-control-preflight.txt"))
    ecfg = rd(f"{RAW}/effective-config.txt")
    rc = runconfig_facts(ecfg, env["SIM_CONFIG"])
    exp_pre, exp_sim = expected_argv(REPO, WS, CFG)
    exp_sim[-2] = f"--result-dir={RAW}/runs/{CFG}"
    a_pre, a_sim, a_obs = nul(f"{REC}/argv-preflight.nul"), nul(f"{REC}/argv-sim.nul"), nul(f"{REC}/observed-cmdline.nul")
    cwd_exp = os.path.realpath(f"{REPO}/simulations/m2")  # the observed cwd is canonical
    cwd_obs = rd(f"{REC}/observed-cwd.txt").strip()
    cwd_pre = kv(rd(f"{REC}/cwd-preflight.txt")).get("cwd")
    bins = {}
    for l in rd(f"{EV}/binaries.tsv").splitlines()[1:]:
        f = l.split("\t")
        if len(f) > 4:
            bins[os.path.basename(f[2])] = f[4]
    ids = {}
    for l in rd(f"{REC}/binary-identity-sim.tsv").splitlines()[1:]:
        f = l.split("\t")
        if len(f) == 4:
            ids[f[0]] = (f[1], f[2])
    id_ok = set(ids) == {"opp_run", "libnasctime_m2.so", "libsimu5g.so", "libINET.so"} and all(
        bins.get(n) == s for n, (p, s) in ids.items())
    allow = ("/nix/store/", f"{WS}/omnetpp-6.5.0/lib/", f"{WS}/inet-4.7.0/src/", f"{WS}/simu5g-1.8.1/src/",
             f"{REPO}/src/nasctime/m2/")
    objs = loaded_objects(REC)
    must = {f"{REPO}/src/nasctime/m2/libnasctime_m2.so", f"{WS}/simu5g-1.8.1/src/libsimu5g.so", f"{WS}/inet-4.7.0/src/libINET.so"}
    lo_bad = [o for o in objs if not o.startswith(allow)]
    lo_ok = bool(objs) and not lo_bad and must <= {os.path.normpath(o) for o in objs}
    hz = all(kv(rd(f"{REC}/hazards-{m}.txt")).get("hazards") == "none" for m in ("preflight", "sim"))
    cfg_ok = (pre.get("preflight_exit") == "0" and rc["has_config"] and rc["complete"] and rc["runs"] == [("0", "$repetition=0")]
              and rc["network"] in SP["networks"]
              and rc["sim_time_limit"] == env["SIM_TIME_LIMIT"] and rc["seed_set"] == "0")
    e2 = {"configuration": cfg_ok, "argv_preflight": a_pre == exp_pre, "argv_sim": a_sim == exp_sim,
          "argv_observed": a_obs == exp_sim, "cwd": cwd_obs == cwd_exp and cwd_pre == cwd_exp,
          "binaries": id_ok, "loaded_objects": lo_ok, "hazards": hz}
    facts["effective_config_sha256"] = sha(f"{RAW}/effective-config.txt") if os.path.isfile(f"{RAW}/effective-config.txt") else None
    facts["runconfig"] = rc
    facts["loaded_objects"] = objs
    facts["binary_identity"] = ids
    row("E-2", f"configuration, run and binary identity: pre-flight runconfig of {CFG} selects exactly Run 0 ($repetition=0, "
               f"network {SP['networks'][0]}, sim-time-limit {env['SIM_TIME_LIMIT']}, seed-set 0); reviewed argument vector, observed process argv and "
               "working directory; simulator and libraries equal the C-10 validated binaries; loaded objects only from the "
               "store and project trees; no RUNPATH / working-directory hazard",
        (pf(all(e2.values())) if ran("sim") else "NOT EVALUATED"),
        "failed: " + (", ".join(k for k, v in e2.items() if not v) or "none")
        + f"; effective_config_sha256={facts['effective_config_sha256']}; runs={rc['runs']}; loaded_objects={len(objs)}"
        + (f"; outside={lo_bad[:3]}" if lo_bad else ""))

    # ---------------------------------------------------------------- E-3 exactly one simulation + execution control
    simctl = rd(f"{REC}/sim-control-sim.txt")
    log = rd(f"{RAW}/run-{CFG}.log")
    lf = log_facts(log)
    timings = {}
    for l in rd(f"{EV}/timings.tsv").splitlines()[1:]:
        f = l.split("\t")
        if len(f) == 5:
            timings.setdefault(f[0], []).append(f)
    labels = set(timings)
    other_runs = [p for p in (os.listdir(f"{RAW}/runs/{CFG}/{CFG}") if os.path.isdir(f"{RAW}/runs/{CFG}/{CFG}") else [])
                  if not p.startswith("0.")]
    guard = kv(rd(f"{EV}/guard.txt"))
    stop, gfail = rd(f"{EV}/STOP").strip(), rd(f"{EV}/GUARD_FAILURE").strip()
    guard_ok = (not gfail and guard.get("guard_terminated") == "yes" and guard.get("liveness_checks_failed") == "0"
                and int(guard.get("liveness_checks_ok") or 0) >= 1)
    budget = sorted(k for k, v in timings.items() for x in v if x[2] in ("124", "92"))
    sim_marks = [l for l in sorted(TIER1_LABELS | {"t2-runconfig"}) if SIM_RX.search(rd(f"{EV}/{l}.log"))]
    exec_fail = [l for l in rd(f"{EV}/exec-checks.txt").splitlines() if " FAIL" in l]
    e3 = {"one_start_record": simctl.count("simulation_started:") == 1 and os.path.exists(f"{REC}/sim.started"),
          "one_run_in_log": lf["preparing"] == [f"Preparing for running configuration {env['SIM_CONFIG']}, run #0..."],
          "no_other_run_outputs": not other_runs,
          "stage_labels": labels <= TIER1_LABELS | T2_LABELS and len(timings.get("t2-sim", [])) == 1
                          and len(timings.get("t2-runconfig", [])) == 1,
          "guard_healthy": guard_ok, "no_stop": not stop, "no_budget_breach": not budget,
          "no_simulation_outside_t2_sim": not sim_marks, "exec_checks": not exec_fail}
    row("E-3", f"exactly one simulation (one start record, one 'Preparing ... {CFG}, run #0', no other run outputs, one "
               "t2-sim stage) and healthy execution control (guard, no STOP, time budget, declared stages only, no "
               "simulation outside the authorised stage, controlled working directory)",
        pf(all(e3.values())) if ran("sim") else "NOT EVALUATED",
        "failed: " + (", ".join(k for k, v in e3.items() if not v) or "none")
        + f"; labels={sorted(labels - TIER1_LABELS)}; stop={stop or 'none'}; budget={budget or 'none'}; sim_markers={sim_marks or 'none'}")

    # ---------------------------------------------------------------- E-4 completion within the approved limits
    sc = kv(simctl)
    try:
        wall = float(sc.get("wall_s", "nan"))
    except ValueError:
        wall = float("nan")
    ib, fb, mb = sc.get("initial_output_bytes", ""), sc.get("final_output_bytes", ""), sc.get("sampled_max_output_bytes", "")
    nums = [int(v) for v in (ib, fb, mb) if is_num(v)]
    t2sim = timings.get("t2-sim", [[None, None, "absent"]])[0]
    e4 = {"exit_0": sc.get("simulation_exit") == "0" and t2sim[2] == "0",
          "time_limit_reached": len(lf["time_limit"]) == 1 and lf["time_limit"][0][0] == env["SIM_TIME_LIMIT"],
          "finish_called": lf["finish"] == ["Calling finish() at end of Run #0..."],
          "end": lf["last"] == "End.", "no_error_lines": not lf["errors"], "no_fingerprint": not lf["fingerprint"],
          "wall_within_cap": wall == wall and wall <= float(env["SIM_WALL_CAP_S"]),
          "watchdog_not_triggered": sc.get("watchdog_terminated") == "no",
          "initial_and_final_measurements_numeric": is_num(ib) and is_num(fb),
          "sampled_maximum_numeric_or_not_measured": is_num(mb) or (mb == "NOT MEASURED" and sc.get("in_run_samples") == "0"),
          "below_watchdog_limit": is_num(ib) and is_num(fb) and max(nums) <= int(env["SIM_WATCHDOG_LIMIT_B"])}
    facts["sim"] = {"wall_s": wall, "initial_output_bytes": ib or "absent", "final_output_bytes": fb or "absent",
                    "in_run_samples": sc.get("in_run_samples", "absent"), "sampled_max_output_bytes": mb or "absent",
                    "sampled_peak_vmhwm_kib": sc.get("sampled_peak_vmhwm_kib", "absent"),
                    "observed_identity_captured": sc.get("observed_identity_captured", "absent"),
                    "events": lf["time_limit"][0][1] if lf["time_limit"] else None}
    row("E-4", f"completion within the approved limits: exit 0; '<!> Simulation time limit reached -- at t={env['SIM_TIME_LIMIT']}'; "
               "finish() of Run #0; last line 'End.'; no error or fingerprint line; wall time <= 600 s; watchdog never triggered, "
               "initial and final output measurements numeric (an unavailable sampled maximum is reported NOT MEASURED, "
               "never 0), output <= 500 000 000 B",
        pf(all(e4.values())) if ran("sim") else "NOT EVALUATED",
        "failed: " + (", ".join(k for k, v in e4.items() if not v) or "none") + f"; {facts['sim']}")

    # ---------------------------------------------------------------- E-5 result files
    runs = f"{RAW}/runs"
    present = sorted(os.path.relpath(os.path.join(d, f), runs) for d, _, fs in os.walk(runs) for f in fs) if os.path.isdir(runs) else []
    sizes = {p: os.path.getsize(os.path.join(runs, p)) for p in present}
    total = sum(sizes.values())
    sca = rd(f"{runs}/{CFG}/{CFG}/0.sca")
    attrs = dict(re.findall(r"^attr (\S+) (.*)$", sca, re.M))
    e5 = {"exact_file_set": present == sorted(EXPECTED_FILES), "all_non_empty": all(sizes.get(p, 0) > 0 for p in EXPECTED_FILES),
          "sca_identity": attrs.get("configname") == env["SIM_CONFIG"] and attrs.get("repetition") == "0"
                          and attrs.get("seedset") == "0" and attrs.get("network", "").split(".")[-1] == SP["sca_network"],
          "run_log_and_config_present": bool(log) and bool(ecfg),
          "total_within_acceptance_limit": total <= int(env["SIM_ACCEPT_LIMIT_B"])}
    facts["outputs"] = {"files": sizes, "total_bytes": total}
    row("E-5", f"complete result files: exactly the {len(EXPECTED_FILES)} expected files of run 0, all non-empty; scalar-file "
               f"run identity (configname {CFG}, repetition 0, seedset 0, network {SP['sca_network']}); total <= 200 000 000 B",
        pf(all(e5.values())) if ran("sim") else "NOT EVALUATED",
        "failed: " + (", ".join(k for k, v in e5.items() if not v) or "none") + f"; files={len(present)} total_bytes={total}"
        + (f"; unexpected={sorted(set(present) - set(EXPECTED_FILES))[:4]} missing={sorted(set(EXPECTED_FILES) - set(present))[:4]}"
           if present != sorted(EXPECTED_FILES) else ""))

    # ---------------------------------------------------------------- E-6 the experiment's reviewed oracle (unchanged)
    try:
        orc = json.load(open(f"{REC}/oracle.json"))
    except (OSError, ValueError):
        orc = {}
    facts["oracle"] = orc
    if X == "e3a":
        det = (f"reviewed U/TU/F={orc.get('u1_reviewed', 'absent')}; " + "; ".join(
            f"{k}={v.get('result')}" for k, v in (orc.get("rows") or {}).items())
            + "; " + "; ".join(f"{s}: n={v.get('exchanges')} D={v.get('D_values_ps')} owd={v.get('one_way_ps')}"
                               for s, v in (orc.get("sides") or {}).items()))
    else:
        det = ("; ".join(f"{k}={v.get('result')}({v.get('scope')})" for k, v in (orc.get("rows") or {}).items())
               + "; partially evaluated (baseline-dependent parts NOT EVALUATED): " + ", ".join(orc.get("partial") or ["absent"])
               + "; NOT EVALUATED: " + ", ".join(orc.get("not_evaluated") or ["absent"])
               + "; counts: " + ", ".join(f"{k}={v}" for k, v in (orc.get("counts") or {}).items())
               + f"; files opened outside raw/checker: {orc.get('files_opened_outside_raw_and_checker', 'absent')}")
    row("E-6", SP["oracle"], (pf(orc.get("result") == "PASS") if orc else ("FAIL" if ran("oracle") else "NOT EVALUATED")),
        det + f"; problems={orc.get('problems') or 'none'}")

    # ---------------------------------------------------------------- E-7 repository, upstream and lock integrity
    mod = rd(f"{REC}/modified-during-sim.txt")
    gb, ga, gf = (rd(f"{REC}/git-status-{x}.txt") for x in ("before", "after", "final"))
    lock = rd(f"{EV}/lock.txt")
    e7 = {"no_file_modified_during_sim": os.path.isfile(f"{REC}/modified-during-sim.txt") and not mod.strip(),
          "git_status_unchanged": bool(os.path.isfile(f"{REC}/git-status-before.txt")) and gb == ga == gf,
          "no_tracked_change": not [l for l in gf.splitlines() if l[:2] not in ("??", "!!")],
          "locks_after_runconfig": "after-t2-runconfig result: PASS" in lock and "after-t2-runconfig result: FAIL" not in lock,
          "locks_after_sim": "after-t2-sim result: PASS" in lock and "after-t2-sim result: FAIL" not in lock,
          "locks_final_t2": "final-t2 result: PASS" in lock and "final-t2 result: FAIL" not in lock,
          "upstream_source_changes_C3": cres.get("C-3") == "PASS"}
    row("E-7", "no repository or upstream change: no file in the repository or the three project trees modified during the "
               "simulation; git status identical before, after and at evaluation; both locks unchanged before and after the "
               "pre-flight and the simulation and at the end; C-3 source integrity PASS",
        pf(all(e7.values())) if ran("sim") else "NOT EVALUATED",
        "failed: " + (", ".join(k for k, v in e7.items() if not v) or "none")
        + (f"; modified={mod.splitlines()[:3]}" if mod.strip() else ""))

    # ---------------------------------------------------------------- E-8 (part 1) sealing
    seal, ver = kv(rd(f"{REC}/seal.txt")), kv(rd(f"{REC}/seal-verify.txt"))
    facts["seal"] = {"manifest_sha256": seal.get("manifest_sha256"), "files": seal.get("files"), "total_bytes": seal.get("total_bytes")}
    row("E-8", "evidence: raw outputs sealed (SHA-256 manifest, read-only) before evaluation and verified unchanged after it; "
               "screened diagnostics and content-checked raw evidence prepared (completed by the verdict step; uploads checked "
               "by the conclusion)",
        pf(seal.get("seal_result") == "PASS" and ver.get("verify_result") == "PASS") if ran("seal") else "NOT EVALUATED",
        f"seal={seal.get('seal_result', 'absent')} manifest_sha256={seal.get('manifest_sha256')} files={seal.get('files')} "
        f"total_bytes={seal.get('total_bytes')}; verify_after_evaluation={ver.get('verify_result', 'absent')}")

    # ---------------------------------------------------------------- E-9 historical 6.4.0 reference (informational)
    cmp_ = {}
    for p, h in sorted(reference(env).items()):
        fp = os.path.join(runs, p)
        cmp_[p] = ("MISSING" if not os.path.isfile(fp) else "REPRODUCED" if sha(fp) == h else "DIFFERS")
    facts["reference"] = cmp_
    tally = {k: sum(1 for v in cmp_.values() if v == k) for k in ("REPRODUCED", "DIFFERS", "MISSING")}
    row("E-9", SP["ref_label"] + " - INFORMATIONAL, per file only (no whole-result equivalence claim), not an acceptance "
                                 "criterion", "INFORMATIONAL",
        f"{tally}; " + "; ".join(f"{os.path.basename(k)}: {v}" for k, v in cmp_.items()), mandatory=False)

    # ---------------------------------------------------------------- classification
    diag = rd(f"{REC}/runconfig-stderr.txt") + "\n" + log
    failed_exec = pre.get("preflight_exit") not in (None, "0") or (ran("sim") and sc.get("simulation_exit") not in (None, "0")
                                                                   and sc.get("watchdog_terminated") == "no")
    hits = [l.strip() for l in diag.splitlines() if ("rror" in l) and BLOCK_RX.search(l)]
    state = {"stop": bool(stop), "guard_failure": bool(gfail or (guard and not guard_ok)),
             "blocked": bool(failed_exec and hits), "blocked_diagnostics": hits[:5], "rows": rows, "facts": facts}
    os.makedirs(REC, exist_ok=True)
    json.dump(state, open(f"{REC}/e-rows.json", "w"), indent=1, default=str)
    return state


if __name__ == "__main__":
    st = evaluate(os.environ)
    for r in st["rows"]:
        print(f"{r['id']}: {r['result']}  {r['criterion'][:110]}  [{r['detail'][:500]}]")
