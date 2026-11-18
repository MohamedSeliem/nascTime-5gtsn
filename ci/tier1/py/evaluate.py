"""Tier-1 acceptance evaluation C-1 .. C-14 (C-15, evidence, is decided by final.py after publication).

Every row is PASS, FAIL or NOT EVALUATED (a prerequisite step did not run). NOT EVALUATED is never PASS: a TIER-1
PASS requires every row to be PASS. Inputs: the evidence directory ($EV), STEP_OUTCOMES (the workflow's steps context
as JSON) and the reviewed pins in the environment. Writes stage-resources.tsv, capacity.txt and c-rows.json.
"""
import datetime
import json
import os
import re

STEPS = ["setup", "bootstrap", "verify", "runtime", "b_omnetpp", "b_inet", "b_simu5g", "b_nasctime", "validate",
         "srcchanges", "wrapper", "lockend", "measure"]
ALLOWED_LABELS = {"nix-install", "realise", "probe", "probe-runtime-before", "probe-runtime-after", "build-omnetpp",
                  "build-inet", "build-simu5g", "build-nasctime", "validate", "wrapper-suite"}
SIM_RX = re.compile(r"Invoking (smoke_test|test)_|Running simulation|Setting up Cmdenv|Preparing for running configuration|Calling finish\(\)")
REF_KEYS = ["WITH_PYTHON", "WITH_QTENV", "WITH_OSG", "WITH_OSGEARTH", "WITH_NETBUILDER", "WITH_SCAVE_PYTHON_BINDINGS",
            "WITH_LIBXML", "WITH_PARSIM", "WITH_SYSTEMC", "WITH_BACKTRACE", "WITH_AKAROA"]


def evaluate(ev, env):
    def read(p):
        try:
            return open(os.path.join(ev, p)).read()
        except OSError:
            return ""

    def kv(t):
        d = {}
        for line in t.splitlines():
            if ": " in line:
                k, v = line.split(": ", 1)
                d.setdefault(k.strip(), v.strip())
        return d

    runner, nix, oe, probe = kv(read("runner.txt")), kv(read("nix.txt")), kv(read("opp_env.txt")), kv(read("probe.txt"))
    lock, adapt, guard = kv(read("lock.txt")), kv(read("adaptations-summary.txt")), kv(read("guard.txt"))
    flk, ver, sizes = kv(read("flake-lock-check.txt")), read("postdownload-verify.txt"), kv(read("sizes.txt"))
    src, vres, assets = kv(read("source-changes-summary.txt")), kv(read("validate-result.txt")), kv(read("release-assets.txt"))
    admin, case = kv(read("workspace-admin-check.txt")), kv(read("c4-case.txt")).get("c4_case", "")
    hl, rg, hd, tx, sl = (kv(read(f)) for f in ("host-libcxx.txt", "runtime-gates.txt", "host-packages.diff",
                                                "apt-remove-transaction.txt", "sys-libs.txt"))
    wr = kv(read("wrapper-result.txt"))
    timings = {}
    for l in read("timings.tsv").splitlines()[1:]:
        f = l.split("\t")
        if len(f) == 5 and f[1].lstrip("-").isdigit():
            timings[f[0]] = {"s": int(f[1]), "rc": f[2], "t0": int(f[3]), "t1": int(f[4])}
    outcomes = {k: v.get("outcome") for k, v in json.loads(env.get("STEP_OUTCOMES") or "{}").items()}

    def ran(*ids):
        return all(outcomes.get(s) in ("success", "failure") for s in ids)

    def ok(*ids):
        return all(outcomes.get(s) == "success" for s in ids)

    def pf(c):
        return "PASS" if c else "FAIL"

    def gated(ids, cond):
        return pf(cond) if ran(*ids) else "NOT EVALUATED"

    rows = []

    def row(i, what, result, detail=""):
        rows.append({"id": i, "criterion": what, "result": result, "detail": str(detail).replace("|", "/").replace("\n", " ")})

    def tool(t):
        return probe.get(f"tool {t}", "")

    # C-1 pins and identity
    ref = dict(x.split("=", 1) for x in env["WITH_REFERENCE"].split())
    c1 = {
        "steps": ok("setup", "bootstrap", "verify"),
        "nix": nix.get("nix_version") == "nix (Nix) " + env["NIX_VERSION"] and "require-sigs = true" in read("nix.txt").splitlines(),
        "opp_env": oe.get("opp_env_version") == env["OPP_ENV_PIN"] and oe.get("opp_env_main_sha256") == env["OPP_ENV_MAIN_SHA256"]
                   and oe.get("opp_env_module", "").startswith(os.path.realpath(env["VENV"]) + "/"),
        "release_assets": assets.get("assets_check") == "PASS",
        "toolchain": probe.get("probe_result") == "PASS" and env["EXPECT_CLANG"] in tool("clang++")
                     and env["EXPECT_GCC"] in tool("g++") and ("GNU Make " + env["EXPECT_MAKE"]) in tool("make")
                     and ("Python " + env["EXPECT_PYTHON"]) in tool("python3"),
        "configure.user": {k: probe.get("configure.user " + k) for k in REF_KEYS} == ref,
    }
    row("C-1", "pins and identity (Nix, opp_env, lock content, release assets, toolchain, configure.user)",
        pf(all(c1.values())) if ran("setup") else "NOT EVALUATED",
        "failed: " + (", ".join(k for k, v in c1.items() if not v) or "none"))
    # C-2 lock integrity
    phases = [l.split(" ")[0] for l in read("lock.txt").splitlines() if l.endswith((" result: PASS", " result: FAIL"))]
    need = {"before-realisation", "after-realisation", "after-probe", "final"}
    c2 = (all(lock.get(f"{p} result") == "PASS" for p in phases) and need <= set(phases)
          and lock.get("repository approved_26.05") == env["LOCK_SHA256"]
          and flk.get("flake_metadata_no_update_check") == "PASS" and admin.get("admin_check") == "PASS"
          and read("lock-enforcement.txt").count(": immutable") == 2 and outcomes.get("lockend") == "success")
    row("C-2", "lock integrity (both locks unchanged and write-protected at every gate; metadata; admin files)",
        pf(c2) if ran("setup") else "NOT EVALUATED", "; ".join(f"{p}={lock.get(p + ' result')}" for p in phases) or "no gates")
    # C-3 source integrity (before the build: manifests and recipe screening; after: build-change classification)
    pre = ver.count("sha1sum_check: PASS") == 3 and all(f"{p} files_added_after_download: 0" in ver for p in ("omnetpp", "inet", "simu5g")) \
        and adapt.get("unexpected_adaptations") == "0" and adapt.get("framework_build_outputs_after_download") == "0"
    if not ran("verify"):
        c3 = "NOT EVALUATED"
    elif not pre:
        c3 = "FAIL"
    elif ran("srcchanges"):
        c3 = pf(ok("srcchanges") and src.get("unexpected_upstream_source_changes") == "0" and src.get("nascTime_tracked_source_changes") == "0")
    else:
        c3 = "NOT EVALUATED"
    row("C-3", "source integrity (manifest verification, recipe-consistency screening, build-induced change classification)", c3,
        f"pre_build={'PASS' if pre else 'FAIL'} unexpected={src.get('unexpected_upstream_source_changes', 'n/a')} "
        f"nascTime_tracked={src.get('nascTime_tracked_source_changes', 'n/a')}")
    # C-4 host C++ runtime (case A: provenance + controlled removal + probes; case B: clean host, controls only)
    if not ran("runtime"):
        c4, d4 = "NOT EVALUATED", "runtime step did not run"
    elif case == "A":
        c4 = pf(hl.get("r1_result") == "PASS" and tx.get("transaction_check") == "PASS" and hd.get("r2_result") == "PASS"
                and rg.get("r3_result") == "PASS" and rg.get("r4_result") == "PASS" and ok("runtime"))
        removed = [l.split(": ", 1)[1] for l in read("apt-remove-transaction.txt").splitlines() if l.startswith("removal: ")]
        d4 = (f"case A; R-1={hl.get('r1_result')} selected={hl.get('selected_libcxx_runtime')} canonical={hl.get('selected_libcxx_canonical')} "
              f"entry={hl.get('unversioned_linker_entry')} runtime_owners={hl.get('runtime_owners')} development_owners={hl.get('development_owners')}; "
              f"R-2 transaction={tx.get('transaction_check')} inventory={hd.get('r2_result')} removed={removed}; "
              f"R-3={rg.get('r3_result')} R-4={rg.get('r4_result')} libstdc++={rg.get('positive_default_libstdcxx')}")
    elif case == "B":
        c4 = pf(rg.get("r3_result") == "PASS" and rg.get("r4_result") == "PASS" and ok("runtime") and not read("apt-remove.txt"))
        d4 = f"case B (clean host, nothing removed); R-3={rg.get('r3_result')} R-4={rg.get('r4_result')} libstdc++={rg.get('positive_default_libstdcxx')}"
    else:
        c4, d4 = "FAIL", f"case {case or 'undetermined'}: {read('HYPOTHESIS_NOT_CONFIRMED').strip() or 'runtime step failed'}"
    row("C-4", "host C++ runtime: no host libc++ reachable by the Nix toolchain; GNU libstdc++ from the pinned store", c4, d4)
    # C-5 SYS_LIBS
    row("C-5", "SYS_LIBS: -lstdc++ present, -lc++ absent, ordered tokens equal to the recovered VM reference",
        gated(["b_omnetpp"], sl.get("r5_result") == "PASS") if sl else "NOT EVALUATED",
        f"ordered_match={sl.get('ordered_token_match_vm')} exact_string={sl.get('exact_string_match_vm')} "
        f"only_hosted={sl.get('tokens_only_hosted')} only_vm={sl.get('tokens_only_vm')}")
    # C-6 .. C-9 builds
    for cid, step, label, what in (("C-6", "b_omnetpp", "build-omnetpp", "OMNeT++ 6.5.0 release build"),
                                   ("C-7", "b_inet", "build-inet", "INET 4.7.0 release build"),
                                   ("C-8", "b_simu5g", "build-simu5g", "Simu5G 1.8.1 release build"),
                                   ("C-9", "b_nasctime", "build-nasctime", "libnasctime_m2 release build")):
        t = timings.get(label)
        if t is None:
            row(cid, what, "NOT EVALUATED", f"not started (step {outcomes.get(step)})")
        else:
            row(cid, what, pf(t["rc"] == "0" and ran(step)), f"exit {t['rc']} after {t['s']} s; step {outcomes.get(step)}")
    # C-10 binaries and identity, C-11 linkage
    bins = [l.split("\t") for l in read("binaries.tsv").splitlines()[1:] if l]
    missing = [b[2] for b in bins if len(b) > 3 and b[3] == "MISSING"]
    elf = [b for b in bins if len(b) == 14 and b[5] == "yes"]
    unresolved = [b[2] for b in elf if b[9] != "0"]
    idt = kv(read("identity-tools.txt"))
    vexit = re.search(r"^opp_run_v_exit: (\d+)", read("opp_run-version.txt"), re.M)
    c10 = (vres.get("binaries_result") == "PASS" and vres.get("oppv_result") == "PASS" and len(bins) == 22 and not missing
           and idt.get("debug_outputs_present") == "0" and vexit is not None and vexit.group(1) == "0")
    row("C-10", "22 release binaries/libraries verified (presence, size, sha256, ELF metadata, no debug outputs); opp_run -v exit 0, 6.5.0",
        gated(["validate"], c10) if vres else "NOT EVALUATED",
        f"{len(bins)} checked, missing={missing or 'none'}, debug_outputs={idt.get('debug_outputs_present')}, opp_run_v_exit={vexit.group(1) if vexit else 'absent'}")
    row("C-11", "no unresolved dynamic dependencies (18 ELF files)",
        gated(["validate"], vres.get("linkage_result") == "PASS" and len(elf) >= 18 and not unresolved) if vres else "NOT EVALUATED",
        f"{len(elf)} ELF files; unresolved: {unresolved or 'none'}")
    # C-12 runtime and execution safety
    violations = [b[2] for b in elf if b[10] != "none"] + [f"{b[2]} resolves {b[13]}" for b in elf if b[13] != "none"]
    unw = [f"{b[2]}={b[11]}" for b in elf if b[11] != "none"]
    rp = read("runpath-observation-validate.txt").splitlines()
    rp_unexpected = sorted({l.split("non-store RUNPATH entry ", 1)[1] for l in rp if "class=UNEXPECTED" in l})
    rp_classes = sorted({re.sub(r"^.*non-store RUNPATH entry ", "", l) for l in rp})
    exec_fail = [l for l in read("exec-checks.txt").splitlines() if " FAIL" in l]
    if not vres or vres.get("runtime_result") == "NOT EVALUATED":
        c12 = "NOT EVALUATED"
    else:
        c12 = gated(["validate"], vres.get("runtime_result") == "PASS" and not violations and not rp_unexpected and not exec_fail)
    row("C-12", "single C++ runtime; every library from /nix/store or the project trees; RUNPATH classes; controlled working directory",
        c12, f"violations={violations or 'none'}; runpath={rp_classes or 'none'}; exec_check_failures={len(exec_fail)}; "
             f"libunwind (reported, not by itself a finding)={unw or 'none'}")
    # C-13 wrapper suite
    row("C-13", "A2-V1 wrapper suite 21/21 with the strict real-simulator audit (real configuration queries + synthetic lifecycle)",
        gated(["wrapper"], wr.get("wrapper_result") == "PASS") if wr else "NOT EVALUATED",
        f"passed={wr.get('tests_passed')}/{wr.get('tests_total')} summary='{wr.get('summary_line')}' forwarded={wr.get('audit_forwarded')} "
        f"refused={wr.get('audit_refused')} blocked={wr.get('classification_vm_compatibility_blocked')} "
        f"source_discrepancy={wr.get('classification_simu5g_source_discrepancy')}")
    # C-14 execution control and resources
    disk = []
    for l in read("disk.tsv").splitlines()[1:]:
        f = l.split("\t")
        if len(f) == 5 and f[1] == "/" and f[2].isdigit():
            ts = datetime.datetime.strptime(f[0], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=datetime.timezone.utc).timestamp()
            disk.append((ts, int(f[2]), int(f[4]) if f[4].isdigit() else None))
    stage_lines = ["stage\tseconds\texit\troot_avail_start_B\troot_avail_min_B\tpeak_additional_use_B\tmin_mem_avail_kib\tsamples"]
    stages_ok = True
    for label in ("realise", "probe", "probe-runtime-before", "probe-runtime-after", "build-omnetpp", "build-inet", "build-simu5g",
                  "build-nasctime", "validate", "wrapper-suite"):
        t = timings.get(label)
        if not t:
            continue
        w = [d for d in disk if t["t0"] - 15 <= d[0] <= t["t1"] + 15]
        if not w:
            stages_ok = False
            stage_lines.append(f"{label}\t{t['s']}\t{t['rc']}\t\t\t\t\t0")
            continue
        mems = [m for _, _, m in w if m is not None]
        lo = min(a for _, a, _ in w)
        stage_lines.append(f"{label}\t{t['s']}\t{t['rc']}\t{w[0][1]}\t{lo}\t{w[0][1] - lo}\t{min(mems) if mems else ''}\t{len(w)}")
    open(os.path.join(ev, "stage-resources.tsv"), "w").write("\n".join(stage_lines) + "\n")
    start = int(runner.get("root_avail_start_B", "0") or 0)
    peak_used = (start - min(a for _, a, _ in disk)) if disk and start else None
    mem_all = [m for _, _, m in disk if m is not None]
    final_free = int(sizes["root_avail_final_B"]) if sizes.get("root_avail_final_B", "").isdigit() else None
    stop, gfail = read("STOP").strip(), read("GUARD_FAILURE").strip()
    guard_ok = (not gfail and guard.get("guard_terminated") == "yes" and guard.get("liveness_checks_failed") == "0"
                and int(guard.get("liveness_checks_ok") or 0) >= 1)
    unauthorised = sorted(set(timings) - ALLOWED_LABELS)
    budget_hit = sorted(k for k, v in timings.items() if v["rc"] in ("124", "92"))
    sim_hits = [l for l in sorted(ALLOWED_LABELS) if SIM_RX.search(read(f"{l}.log"))]
    modes_ok = all(("Invoking build_%s debug" % p) not in read(f"build-{p}.log") for p in ("omnetpp", "inet", "simu5g"))
    c14 = (not stop and guard_ok and not unauthorised and not budget_hit and not sim_hits and modes_ok
           and stages_ok and peak_used is not None and bool(mem_all) and final_free is not None)
    row("C-14", "execution control (guard healthy, no STOP, within time budget, declared stages only, no simulation, release only) "
                "and resources recorded", pf(c14),
        stop or gfail or f"guard_ok={guard_ok} unauthorised={unauthorised or 'none'} budget_hit={budget_hit or 'none'} "
                         f"simulation_markers={sim_hits or 'none'} debug_mode={not modes_ok} peak_used_B={peak_used} "
                         f"min_mem_avail_kib={min(mem_all) if mem_all else None} final_free_B={final_free}")
    with open(os.path.join(ev, "capacity.txt"), "w") as f:
        f.write(f"root_free_start_B: {start}\npeak_used_B: {peak_used}\nroot_free_final_B: {final_free}\n"
                f"remaining_above_stop_threshold_B: {final_free - int(env['STOP_FREE_GIB']) * 1073741824 if final_free is not None else None}\n"
                f"min_mem_available_kib: {min(mem_all) if mem_all else None}\n"
                f"wall_seconds_by_guarded_stage: { {k: v['s'] for k, v in timings.items()} }\n")
    state = {"stop": bool(stop), "guard_failure": bool(gfail or not guard_ok),
             "blocked": wr.get("classification_vm_compatibility_blocked", "no").startswith("yes"), "rows": rows}
    open(os.path.join(ev, "c-rows.json"), "w").write(json.dumps(state, indent=1) + "\n")
    return state


if __name__ == "__main__":
    st = evaluate(os.environ["EV"], os.environ)
    for r in st["rows"]:
        print(f"{r['id']}: {r['result']}  {r['criterion']}  [{r['detail']}]")
    print(open(os.path.join(os.environ["EV"], "stage-resources.tsv")).read())
    print(open(os.path.join(os.environ["EV"], "capacity.txt")).read())
