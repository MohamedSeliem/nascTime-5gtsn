#!/usr/bin/env python3
"""M2-S7.2a work package A2 (DR-07a): checks of the full-contract H-ARQ diagnostic (protocol
results/M2-S7.2a-a2d-protocol.md). Read-only on raw outputs; never simulates; never writes the FGO registry.

    m2s72_a2d.py resolve <out dir> -- <opp_run command prefix ...>
        OMNeT++'s own resolution (-q runconfig; no network, no simulation) of the diagnostic, its twin, the accepted
        base and A2-V1, saved to <out dir>/runconfig-<cfg>.txt, then the checks of resolve-files; exit 0 / 1 / 2
    m2s72_a2d.py resolve-files <diag> <ref> <base> <a2v1>   (saved runconfig outputs)
        R-1 diagnostic vs twin: exactly the scheduler-logging entry differs
        R-2 twin vs accepted base: exactly the declared NACK-injection entries are added (num-rngs 4 -> 5), the rest
            of the effective entries identical in content and order
        R-3 twin vs A2-V1: exactly the perDl / harqReduction scope and value differ
        R-4 no other scheduler log-level entry; every accepted log-level entry of the base kept
    m2s72_a2d.py twin <runs> <records dir>
        the non-perturbation twin (DR-07a): T-1 the accepted E0 comparator (check_m2s72_e0.nonpert, unchanged) on every
        non-console output; T-2 the console logs identical once the diagnostic's mac.schedulerDl lines and the
        declared volatile Cmdenv lines are removed; T-3 scheduler lines present in the diagnostic, absent in the twin;
        the canaries NC-T1 .. NC-T4. Exit 0 non-perturbation shown; 1 not shown; 2 evaluation error
    m2s72_a2d.py coverage <a21 json> <records dir>
        the declared coverage minima (DR-07a) on the accepted A-2.1 record of the diagnostic (check_m2s72_a21.py a21
        ... --contract full): exit 0 a valid diagnostic; 5 NOT A VALID DIAGNOSTIC (a minimum unmet, A2-4c not
        exercised, wrong contract or configuration); 2 evaluation error. The A-2.1 verdict is reported verbatim and
        is never changed; the counters are diagnostic counters, never performance measurements
    m2s72_a2d.py plan <nascTime> <simu5g root> <inet root> <results root>
        the exact command of every step for the independent executor (prints only)
    m2s72_a2d.py smoke <out dir> <record json> -- <opp_run prefix with -l / -n / -x / -u ...>
        DEVELOPMENT-LEVEL NETWORK-INITIALIZATION SMOKE (step 162-R1; not V-6, not an experiment): the accepted base, the
        twin and the diagnostic, each built and initialized by the real stack and stopped at simulated time 0
        (--sim-time-limit=0s: only the t = 0 start-up events run), with OMNeT++'s unused-entry check after
        initialization and the channel models' parameters recorded as scalars. The extracted facts go to <record json>
        (paths normalised), then the checks of smoke-check
    m2s72_a2d.py smoke-check <record json>
        SM-1 every run rc 0, stopped at t = 0 by the limit, no error; SM-2 the unused-entry lists of twin and
        diagnostic equal the accepted base's and no A2 entry is reported unused (a consistency check only: it does NOT
        show that a setting was applied; that evidence is SM-3 / SM-4 / SM-5); SM-3 constructed types (eventlog
        module creation): IdealChannelModel at the gNB and at every UE's nrChannelModel in twin and diagnostic, none in
        the base, a schedulerDl submodule in all; SM-4 the assigned values at the constructed modules (perDl 0.3,
        harqReduction 1, perUl 0 at every UE; perDl / perUl 0 at the gNB); SM-5 no scheduler line in the twin
"""
import gzip
import hashlib
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

BASE = "M2S72-E0vN-q0-one0-n2-f1"
DIAG = BASE + "_A2D"
REF = BASE + "_A2DREF"
A2V1 = BASE + "_A2V1"
INI = "m2s72a2d.ini"
SCHED_KEY = "*.gnb1.cellularNic.mac.schedulerDl.cmdenv-log-level"
SCHED_VALUE = "info"
# the declared NACK-injection entries of M2S72A2D-nack-all, in order (value as OMNeT++ prints it)
NACK = [("*.gnb1.cellularNic.channelModelType", '"IdealChannelModel"'),
        ("*.ue[*].cellularNic.nrChannelModelType", '"IdealChannelModel"'),
        ("*.ue[*].cellularNic.nrChannelModel[*].perDl", "0.3"),
        ("*.ue[*].cellularNic.nrChannelModel[*].harqReduction", "1"),
        ("**.perDl", "0"), ("**.perUl", "0"), ("**.perD2D", "0"),
        ("num-rngs", "5"), ("seed-4-mt", "4000"),
        ("**.channelModel[*].rng-0", "4"), ("**.nrChannelModel[*].rng-0", "4")]
A2V1_SCOPE = {"*.ue[1].cellularNic.nrChannelModel[*].perDl": "0.1", "*.ue[1].cellularNic.nrChannelModel[*].harqReduction": "1"}
# DR-07a declared minimum counts (decision 17 Nov 2026): NACK chains on more than one UE, multi-NACK groups, at least
# one maxHarqRtx discard. "multi-NACK groups" read as at least one; nothing else is a threshold.
COV_MULTI = "multi-NACK groups (handle relations kept ambiguous)"
COV_DISCARD = "discard after maxHarqRtx + 1 transmissions"
COV_RTX = "retransmissions"
# features validated only synthetically before (S1 closure §5; DR-07d): a genuine occurrence is held for review
FIRST_GENUINE = (COV_MULTI, COV_DISCARD, "end-of-run censoring: awaiting retransmission (structural)",
                 "end-of-run censoring: awaiting resolution (structural)")
# Cmdenv lines that legitimately differ between two runs of one simulation (wall clock, run id); everything else must
# be equal. Declared from the OMNeT++ 6.5.0 Cmdenv output forms; an undeclared difference FAILS (fail closed)
VOLATILE = (re.compile(r"^Assigned runID="), re.compile(r"Elapsed:"), re.compile(r"^\s*Speed:"),
            re.compile(r"^\s*Messages:"), re.compile(r"^\s*\*\* Event #"))
SCHED_LINE = re.compile(r"^[^|]*\|[^|]*\.mac\.schedulerDl\|")
RTXACID = re.compile(r"LteSchedulerEnbDl::rtxAcid - Node \[")


class EvalError(Exception):
    pass


def _gen():
    spec = importlib.util.spec_from_file_location("m2s72_gen", os.path.join(M2, "tools", "m2s72_gen.py"))
    g = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(g)
    return g


# ------------------------------------------------------------------------------------------------- resolution ----
def entries(text, cfg):
    """effective (key, value) pairs in OMNeT++'s order, via the accepted generator's parser; description / extends
    dropped, the configuration's own name (expanded from ${configname} in output paths) normalised to <config>"""
    ents = _gen().runconfig_entries(text)
    if not ents:
        raise EvalError("no runconfig entries")
    return [(k, v.replace(cfg, "<config>")) for k, v in ents if k not in ("description", "extends")]


def first(pairs):
    d = {}
    for k, v in pairs:
        d.setdefault(k, v)
    return d


def check_resolution(diag, ref, base, a2v1):
    """R-1 .. R-4 on effective-entry lists; returns [(row, ok, detail)]"""
    out = []
    # R-1
    extra = [e for e in diag if e not in ref]
    missing = [e for e in ref if e not in diag]
    rest = [e for e in diag if e[0] != SCHED_KEY]
    out.append(("R-1", extra == [(SCHED_KEY, SCHED_VALUE)] and not missing and rest == ref,
                f"diagnostic vs twin: added {extra}, removed {missing}, the rest {'identical in order' if rest == ref else 'DIFFERENT'}"))
    # R-2
    nk = [k for k, _ in NACK]
    added = [e for e in ref if e[0] in nk]
    base_rest = [e for e in base if e[0] != "num-rngs"]
    ref_rest = [e for e in ref if e[0] not in nk]
    bn = first(base).get("num-rngs")
    out.append(("R-2", added == NACK and ref_rest == base_rest and bn == "4" and first(ref).get("num-rngs") == "5",
                f"twin vs base: NACK entries {'as declared' if added == NACK else added}; base num-rngs {bn} -> "
                f"{first(ref).get('num-rngs')}; other entries {'identical in order' if ref_rest == base_rest else 'DIFFERENT'}"))
    # R-3
    d_ref = {k: v for k, v in ref if k.startswith("*.ue[") and "nrChannelModel[*]" in k}
    d_a2v = {k: v for k, v in a2v1 if k.startswith("*.ue[") and "nrChannelModel[*]" in k}
    other_ref = [e for e in ref if not (e[0].startswith("*.ue[") and "nrChannelModel[*]" in e[0])]
    other_a2v = [e for e in a2v1 if not (e[0].startswith("*.ue[") and "nrChannelModel[*]" in e[0])]
    want_ref = {k: v for k, v in NACK if k.startswith("*.ue[") and "nrChannelModel[*]" in k}
    out.append(("R-3", d_a2v == A2V1_SCOPE and d_ref == want_ref and other_ref == other_a2v,
                f"twin vs A2-V1: A2-V1 {d_a2v}, twin {d_ref}; other entries {'identical' if other_ref == other_a2v else 'DIFFERENT'}"))
    # R-4
    sched = [e for e in diag if "scheduler" in e[0].lower() and e[0].endswith("cmdenv-log-level")]
    logs_base = [e for e in base if e[0].endswith("cmdenv-log-level") or e[0] == "cmdenv-log-prefix"]
    kept = all(e in diag and e in ref for e in logs_base)
    out.append(("R-4", sched == [(SCHED_KEY, SCHED_VALUE)] and kept and logs_base,
                f"scheduler log entries {sched}; {len(logs_base)} accepted log entries of the base {'kept' if kept else 'NOT kept'}"))
    return out


# ---------------------------------------------------------------------------------------------------- twin ------
def _lines(path):
    if not os.path.isfile(path):
        raise EvalError(f"{path} missing")
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", encoding="utf-8", errors="replace") as fh:
        return fh.read().splitlines()


def console_view(lines, cfg, drop_sched):
    """the console log as compared: the configuration name normalised, volatile Cmdenv lines removed, and (for the
    diagnostic) the lines of the mac.schedulerDl module removed; returns (view, scheduler lines, rtxAcid lines)"""
    view, ns, nr = [], 0, 0
    for s in lines:
        if SCHED_LINE.match(s):
            ns += 1
            nr += bool(RTXACID.search(s))
            if drop_sched:
                continue
        if any(p.search(s) for p in VOLATILE):
            continue
        view.append(s.replace(cfg, "<config>"))
    return view, ns, nr


def compare_console(runs, diag, ref, diag_log=None):
    a, nsa, nra = console_view(_lines(diag_log or os.path.join(runs, f"run-{diag}.log.gz")), diag, True)
    b, nsb, nrb = console_view(_lines(os.path.join(runs, f"run-{ref}.log.gz")), ref, True)
    same = a == b
    first_diff = None
    if not same:
        for i in range(max(len(a), len(b))):
            x = a[i] if i < len(a) else "<end>"
            y = b[i] if i < len(b) else "<end>"
            if x != y:
                first_diff = (i, x[:160], y[:160])
                break
    return same, first_diff, (nsa, nra), (nsb, nrb), len(a)


def twin(runs, recdir):
    import check_m2s72_e0 as E  # accepted, unchanged (the E0 / E0v non-perturbation comparator)
    for c in (DIAG, REF):
        if not os.path.isdir(os.path.join(runs, c)):
            raise EvalError(f"run directory of {c} missing")
    rows = []
    ok1, det1 = E.nonpert(runs, DIAG, REF)
    rows.append(("T-1", ok1, f"accepted E0 comparator (PCAP and per-frame logs byte for byte; .sca / .vec without run "
                             f"header; eventlog; fingerprints): {det1}"))
    same, fd, (nsa, nra), (nsb, nrb), n = compare_console(runs, DIAG, REF)
    rows.append(("T-2", same, f"console logs, {n} compared lines after removing the diagnostic's mac.schedulerDl lines "
                              f"and the declared volatile lines: {'IDENTICAL' if same else f'first difference {fd}'}"))
    rows.append(("T-3", nsa > 0 and nra > 0 and nsb == 0,
                 f"scheduler lines: diagnostic {nsa} ({nra} rtxAcid), twin {nsb} (must be 0)"))
    tmp = tempfile.mkdtemp(prefix="a2dtwin-")
    try:
        # NC-T1: one PCAP byte of the twin changed -> T-1 must detect it
        rel = None
        for r_, _, fs in os.walk(os.path.join(runs, REF)):
            for fn in sorted(fs):
                if fn.endswith((".pcap", ".pcapng")) and rel is None:
                    rel = os.path.join(r_, fn)
        if rel is None:
            raise EvalError("no PCAP in the twin for the canary")
        cp = os.path.join(tmp, "x.pcap")
        shutil.copy(rel, cp)
        with open(cp, "r+b") as fh:
            fh.seek(os.path.getsize(cp) // 2)
            c = fh.read(1)
            fh.seek(-1, 1)
            fh.write(bytes([c[0] ^ 1]))
        key = os.path.relpath(rel, os.path.join(runs, REF)).replace(REF, "<config>")
        cok, _ = E.nonpert(runs, DIAG, REF, mutate=(key, cp))
        rows.append(("NC-T1", not cok, f"PCAP byte flipped in a copy of the twin: detected {not cok}"))
        diag_lines = _lines(os.path.join(runs, f"run-{DIAG}.log.gz"))
        # NC-T2: a non-scheduler line inserted into a copy of the diagnostic log -> T-2 must detect it
        j = next((i for i, s in enumerate(diag_lines) if "|" in s and not SCHED_LINE.match(s)), None)
        if j is None:
            raise EvalError("no prefixed non-scheduler line in the diagnostic log for the canary")
        p2 = os.path.join(tmp, "nc2.log")
        open(p2, "w").write("\n".join(diag_lines[:j + 1] + [diag_lines[j] + " CANARY"] + diag_lines[j + 1:]) + "\n")
        s2, _, _, _, _ = compare_console(runs, DIAG, REF, diag_log=p2)
        rows.append(("NC-T2", not s2, f"one non-scheduler line added to a copy of the diagnostic log: detected {not s2}"))
        # NC-T3: one extra scheduler line -> a PERMITTED difference: T-2 must still be identical
        k = next((i for i, s in enumerate(diag_lines) if SCHED_LINE.match(s)), None)
        if k is None:      # no scheduler line at all: T-3 has already failed; these two canaries cannot be built
            rows.append(("NC-T3", False, "NOT BUILDABLE: the diagnostic log has no scheduler line"))
            rows.append(("NC-T4", False, "NOT BUILDABLE: the diagnostic log has no scheduler line"))
        else:
            p3 = os.path.join(tmp, "nc3.log")
            open(p3, "w").write("\n".join(diag_lines[:k + 1] + [diag_lines[k]] + diag_lines[k + 1:]) + "\n")
            s3, _, _, _, _ = compare_console(runs, DIAG, REF, diag_log=p3)
            rows.append(("NC-T3", s3 == same, f"one extra scheduler line in a copy of the diagnostic log is a permitted "
                                              f"difference: T-2 unchanged {s3 == same}"))
            # NC-T4: the diagnostic log without its scheduler lines -> T-3 must fail (diagnostic logging absent)
            p4 = os.path.join(tmp, "nc4.log")
            open(p4, "w").write("\n".join(s for s in diag_lines if not SCHED_LINE.match(s)) + "\n")
            _, _, (n4, r4), _, _ = compare_console(runs, DIAG, REF, diag_log=p4)
            rows.append(("NC-T4", n4 == 0 and r4 == 0, f"scheduler lines stripped from a copy: T-3 would see {n4} "
                                                        f"(diagnostic invalid)"))
    finally:
        shutil.rmtree(tmp)
    ok = all(r[1] for r in rows)
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"a2d-twin-{DIAG}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a A2 non-perturbation twin: {DIAG} (scheduler logging on) vs {REF} (off)\n")
        for r in rows:
            fh.write(f"  {'PASS' if r[1] else 'FAIL'} | {r[0]} | {r[2]}\n")
        fh.write(f"\nnon-perturbation: {'SHOWN' if ok else 'NOT SHOWN'}\n")
    print(open(p).read().rstrip())
    return 0 if ok else 1


# ------------------------------------------------------------------------------------------------ coverage ------
def coverage(a21_json, recdir):
    d = json.load(open(a21_json, encoding="utf-8"))
    for k in ("config", "contract", "rows", "coverage", "per_ue", "verdict"):
        if k not in d:
            raise EvalError(f"{a21_json}: {k} missing")
    rows = {r[0]: r[2] for r in d["rows"]}
    cov = {c[0]: c[1] for c in d["coverage"]}
    for name in (COV_MULTI, COV_DISCARD, COV_RTX):
        if name not in cov:
            raise EvalError(f"coverage item {name!r} missing (schema drift)")
    if "A2-4c" not in rows:
        raise EvalError("row A2-4c missing")
    nack_ues = sorted(str(n) for n, o in d["per_ue"].items() if int(o.get("nack", 0)) > 0)
    checks = [
        ("C-0", d["config"] == DIAG, f"configuration {d['config']} (must be {DIAG})"),
        ("C-1", d["contract"] == "full", f"contract {d['contract']} (must be full: A2-4c required)"),
        ("M-1", len(nack_ues) > 1, f"NACK chains on more than one UE: UEs with NACKs {nack_ues}"),
        ("M-2", cov[COV_MULTI] >= 1, f"multi-NACK groups {cov[COV_MULTI]} (at least one)"),
        ("M-3", cov[COV_DISCARD] >= 1, f"discards after maxHarqRtx {cov[COV_DISCARD]} (at least one)"),
        ("M-4", rows["A2-4c"] in ("PASS", "FAIL"), f"A2-4c exercised: {rows['A2-4c']} (NOT EVALUATED / NOT EXERCISED is not a diagnostic)"),
    ]
    valid = all(c[1] for c in checks)
    held = [n for n in FIRST_GENUINE if cov.get(n, 0) > 0]
    if rows["A2-4c"] in ("PASS", "FAIL"):
        held.append(f"A2-4c {rows['A2-4c']} on genuine scheduler evidence")
    out = {"schema": "m2s72-a2d-coverage/1", "config": d["config"], "a21_record_sha256": hashlib.sha256(open(a21_json, "rb").read()).hexdigest(),
           "checks": [list(c) for c in checks], "diagnostic_valid": valid,
           "a21_verdict_verbatim": d["verdict"], "a2_4c": rows["A2-4c"],
           "diagnostic_counters": {"nack_ues": nack_ues, COV_MULTI: cov[COV_MULTI], COV_DISCARD: cov[COV_DISCARD],
                                   COV_RTX: cov[COV_RTX]},
           "first_genuine_occurrence_held_for_review": held,
           "note": "diagnostic counters of a declared full-contract diagnostic; never performance measurements, never an "
                   "E0v-N result, never a change of any historical verdict (A2-V1 stays NOT ACCEPTED)"}
    os.makedirs(recdir, exist_ok=True)
    base = os.path.join(recdir, f"a2d-coverage-{d['config']}")
    json.dump(out, open(base + ".json", "w"), indent=1, sort_keys=True)
    with open(base + ".txt", "w") as fh:
        fh.write(f"M2-S7.2a A2 diagnostic coverage (DR-07a minima) of {d['config']}\n")
        for c in checks:
            fh.write(f"  {'PASS' if c[1] else 'FAIL'} | {c[0]} | {c[2]}\n")
        fh.write(f"\nA-2.1 verdict (verbatim, not changed here): {d['verdict']}\n")
        fh.write(f"first genuine occurrence (DR-07d; held for review): {held or 'none'}\n")
        fh.write(f"\ndiagnostic: {'VALID (minima met, A2-4c exercised)' if valid else 'NOT A VALID DIAGNOSTIC'}\n")
    print(open(base + ".txt").read().rstrip())
    return 0 if valid else 5


# ---------------------------------------------------------------------------------------------------- plan ------
def sim_argv(nascTime, simu5g, inet, cfg, result_dir):
    for p in (nascTime, simu5g, inet, result_dir):
        if not os.path.isabs(p):
            raise EvalError(f"{p}: absolute paths only")
    if cfg not in (DIAG, REF):
        raise EvalError(f"{cfg}: not an A2 diagnostic configuration")
    return ["opp_run", "-l", f"{nascTime}/src/nasctime/m2/nasctime_m2", "-l", f"{simu5g}/src/simu5g",
            "-n", f"{nascTime}/simulations:{nascTime}/src:{simu5g}/src:{inet}/src", "-x", "nasctime.nodes", "-u", "Cmdenv",
            "-f", INI, "-c", cfg, "--repeat=1", "-r", "0", f"--result-dir={result_dir}",
            "--cmdenv-express-mode=false", "--fingerprint=0000-0000/tplx"]


def plan(nascTime, simu5g, inet, root):
    runs = os.path.join(root, "runs")
    rec = os.path.join(root, "records")
    lines = [f"# A2 full-contract diagnostic (protocol results/M2-S7.2a-a2d-protocol.md); cd {nascTime}/simulations/m2"]
    for c in (DIAG, REF):
        lines.append(" ".join(sim_argv(nascTime, simu5g, inet, c, f"{runs}/{c}")) + f" 2>&1 | gzip -n -1 > {runs}/run-{c}.log.gz")
        lines.append(f"python3 -B check/m2s72s5_lib.py manifest {rec}/{c}.manifest.sha256 {runs}/{c} {runs}/run-{c}.log.gz")
    lines.append(f"python3 -B check/m2s72_a2d.py twin {runs} {rec}")
    lines.append(f"python3 -B check/check_m2s72_a21.py a21 {runs} {DIAG} {rec} --contract full")
    lines.append(f"python3 -B check/m2s72_a2d.py coverage {rec}/a21-{DIAG}.json {rec}")
    for c in (DIAG, REF):
        lines.append(f"python3 -B check/m2s72s5_lib.py verify-manifest {rec}/{c}.manifest.sha256")
    return lines


# --------------------------------------------------------------------------------------- initialization smoke ----
SMOKE_ARGS = ["--repeat=1", "-r", "0", "--cmdenv-express-mode=false", "--sim-time-limit=0s",
              "--unused-entry-check=warning", "--unused-entry-check-time=initialization",
              "--**.channelModel[*].param-record-as-scalar=true", "--**.nrChannelModel[*].param-record-as-scalar=true"]
UNUSED_HDR = re.compile(r"^<!> Warning: (\d+) configuration entries had no effect")
UNUSED_LINE = re.compile(r"^  (.+?) = (.*?)  -- (.+):(\d+)$")
STOP_T0 = re.compile(r"^<!> Simulation time limit reached -- at t=0s, event #(\d+)")


def parse_console(text):
    """(unused entries as sorted [key, value, file basename, line], header count, t=0 stop event number or None,
    error lines, scheduler lines)"""
    lines = text.splitlines()
    unused, count, stop, errs, sched = [], None, None, [], 0
    in_list = False
    for s in lines:
        m = UNUSED_HDR.match(s)
        if m:
            count, in_list = int(m.group(1)), True
            continue
        if in_list:
            u = UNUSED_LINE.match(s)
            if u:
                unused.append([u.group(1), u.group(2), os.path.basename(u.group(3)), int(u.group(4))])
                continue
            in_list = False
        m = STOP_T0.match(s)
        if m:
            stop = int(m.group(1))
        if s.startswith("<!> Error") or "cRuntimeError" in s:
            errs.append(s[:200])
        sched += bool(SCHED_LINE.match(s))
    return sorted(unused), count, stop, errs, sched


def parse_elog_types(path):
    """module full path -> NED type, from the eventlog's module-creation records (MC)"""
    mods = {}
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        for s in fh:
            if not s.startswith("MC "):
                continue
            f = s.split()
            kv = {f[i]: f[i + 1] for i in range(1, len(f) - 1, 2)}
            mods[kv["id"]] = (kv.get("pid"), kv["n"], kv["t"])
    out = {}
    for mid, (pid, n, t) in mods.items():
        path_, p = [n], pid
        while p in mods:
            path_.insert(0, mods[p][1])
            p = mods[p][0]
        out[".".join(path_)] = t
    return out


def parse_sca_par(path):
    """{module: {parameter: value}} from the .sca 'par' lines"""
    out = {}
    for s in open(path, encoding="utf-8", errors="replace"):
        if s.startswith("par "):
            f = s.split()
            if len(f) >= 4:
                out.setdefault(f[1], {})[f[2]] = " ".join(f[3:])
    return out


def smoke(out, record, cmd):
    facts = {"schema": "m2s72-a2d-smoke/1", "purpose": "development-level network-initialization smoke (not V-6, "
             "not an experiment): network built, initialized, stopped at simulated time 0", "args": SMOKE_ARGS, "runs": {}}
    for c in (BASE, REF, DIAG):
        rd = os.path.join(out, "runs", c)
        r = subprocess.run(cmd + ["-f", INI, "-c", c, f"--result-dir={rd}"] + SMOKE_ARGS, cwd=M2, capture_output=True,
                           text=True, timeout=900)
        text = r.stdout + r.stderr
        open(os.path.join(out, f"console-{c}.txt"), "w").write(text)
        unused, count, stop, errs, sched = parse_console(text)
        elog = sca = None
        for r_, _, fs in os.walk(rd):
            for fn in fs:
                if fn.endswith(".elog"):
                    elog = os.path.join(r_, fn)
                if fn.endswith(".sca"):
                    sca = os.path.join(r_, fn)
        types = parse_elog_types(elog) if elog else {}
        pars = parse_sca_par(sca) if sca else {}
        facts["runs"][c] = {
            "rc": r.returncode, "stopped_at_t0_event": stop, "errors": errs, "scheduler_lines": sched,
            "unused_count": count, "unused": unused,
            "types": {k: v for k, v in types.items() if re.search(r"(channelModel|nrChannelModel)\[\d+\]$|\.schedulerDl$", k)},
            "par": {m: v for m, v in pars.items() if re.search(r"(channelModel|nrChannelModel)\[\d+\]$", m)}}
    with open(record, "w") as fh:
        json.dump(facts, fh, indent=1, sort_keys=True)
    return smoke_check(record)


def smoke_check(record):
    d = json.load(open(record, encoding="utf-8"))
    if d.get("schema") != "m2s72-a2d-smoke/1" or set(d.get("runs", {})) != {BASE, REF, DIAG}:
        raise EvalError(f"{record}: not a complete smoke record")
    R = d["runs"]
    rows = []
    for c in (BASE, REF, DIAG):
        x = R[c]
        rows.append(("SM-1", x["rc"] == 0 and x["stopped_at_t0_event"] is not None and not x["errors"],
                     f"{c}: rc {x['rc']}, stopped at t = 0 after event #{x['stopped_at_t0_event']}, errors {x['errors'][:2]}"))
    a2keys = {k for k, _ in NACK} | {SCHED_KEY}
    for c in (REF, DIAG):
        same = R[c]["unused"] == R[BASE]["unused"] and R[c]["unused_count"] == R[BASE]["unused_count"]
        leak = sorted({u[0] for u in R[c]["unused"]} & a2keys)
        rows.append(("SM-2", same and not leak and R[BASE]["unused_count"] == len(R[BASE]["unused"]),
                     f"{c}: {R[c]['unused_count']} unused entries, {'identical to' if same else 'DIFFERENT from'} the base's "
                     f"{R[BASE]['unused_count']}; A2 entries reported unused {leak}"))
    for c in (BASE, REF, DIAG):
        t = R[c]["types"]
        gnb = {k: v for k, v in t.items() if ".gnb1." in k and k.endswith("channelModel[0]")}
        nr = {k: v for k, v in t.items() if re.search(r"\.ue\[\d+\]\.cellularNic\.nrChannelModel\[0\]$", k)}
        sch = [k for k, v in t.items() if k.endswith(".schedulerDl") and v.endswith("LteSchedulerEnbDl")]
        ideal = [k for k, v in t.items() if v.endswith(".IdealChannelModel")]
        if c == BASE:
            ok = not ideal and len(nr) == 2 and len(sch) == 1
        else:
            ok = (len(nr) == 2 and all(v.endswith(".IdealChannelModel") for v in nr.values()) and gnb
                  and all(v.endswith(".IdealChannelModel") for v in gnb.values()) and len(sch) == 1)
        rows.append(("SM-3", bool(ok), f"{c}: gNB {sorted(set(gnb.values()))}, UE nrChannelModel {sorted(set(nr.values()))}, "
                                       f"schedulerDl {len(sch)}"))
    for c in (REF, DIAG):
        p = R[c]["par"]
        ue = {m: v for m, v in p.items() if re.search(r"\.ue\[\d+\]\.cellularNic\.nrChannelModel\[0\]$", m)}
        gn = {m: v for m, v in p.items() if ".gnb1." in m}
        ok = (len(ue) == 2 and all(v.get("perDl") == "0.3" and v.get("harqReduction") == "1" and v.get("perUl") == "0" for v in ue.values())
              and gn and all(v.get("perDl") == "0" and v.get("perUl") == "0" for v in gn.values()))
        rows.append(("SM-4", bool(ok), f"{c}: UE nrChannelModel {sorted({(v.get('perDl'), v.get('harqReduction'), v.get('perUl')) for v in ue.values()})} "
                                       f"(perDl, harqReduction, perUl); gNB {sorted({(v.get('perDl'), v.get('perUl')) for v in gn.values()})}"))
    rows.append(("SM-5", R[REF]["scheduler_lines"] == 0,
                 f"scheduler lines up to t = 0: twin {R[REF]['scheduler_lines']} (must be 0), diagnostic {R[DIAG]['scheduler_lines']} (reported)"))
    for r in rows:
        print(f"{'PASS' if r[1] else 'FAIL'} | {r[0]} | {r[2]}")
    ok = all(r[1] for r in rows)
    print(f"A2 initialization smoke: {'AS DECLARED' if ok else 'NOT AS DECLARED'} (development level; not V-6)")
    return 0 if ok else 1


# ---------------------------------------------------------------------------------------------------- main ------
def main(argv):
    try:
        a = argv[1:]
        if a and a[0] == "resolve" and len(a) >= 4 and a[2] == "--":
            out, cmd = a[1], a[3:]
            os.makedirs(out, exist_ok=True)
            got = {}
            for c, ini in ((DIAG, INI), (REF, INI), (BASE, INI), (A2V1, "m2s72a2v.ini")):
                r = subprocess.run(cmd + ["-f", ini, "-c", c, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
                p = os.path.join(out, f"runconfig-{c}.txt")
                open(p, "w").write(r.stdout)
                if r.returncode != 0:
                    raise EvalError(f"runconfig of {c} rc {r.returncode}: {r.stderr[-300:]}")
                got[c] = p
            a = ["resolve-files", got[DIAG], got[REF], got[BASE], got[A2V1]]
        if len(a) == 5 and a[0] == "resolve-files":
            ents = [entries(open(p, encoding="utf-8").read(), c) for p, c in zip(a[1:], (DIAG, REF, BASE, A2V1))]
            res = check_resolution(*ents)
            for r in res:
                print(f"{'PASS' if r[1] else 'FAIL'} | {r[0]} | {r[2]}")
            ok = all(r[1] for r in res)
            print(f"A2 resolution: {'AS DECLARED' if ok else 'NOT AS DECLARED'}")
            return 0 if ok else 1
        if len(a) == 3 and a[0] == "twin":
            return twin(a[1], a[2])
        if len(a) == 3 and a[0] == "coverage":
            return coverage(a[1], a[2])
        if a and a[0] == "smoke" and len(a) >= 5 and a[3] == "--":
            os.makedirs(a[1], exist_ok=True)
            return smoke(a[1], a[2], a[4:])
        if len(a) == 2 and a[0] == "smoke-check":
            return smoke_check(a[1])
        if len(a) == 5 and a[0] == "plan":
            print("\n".join(plan(*a[1:])))
            return 0
    except Exception as ex:   # noqa: BLE001  (an evaluation that cannot complete is never a PASS)
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
