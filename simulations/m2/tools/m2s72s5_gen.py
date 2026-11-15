#!/usr/bin/env python3
"""M2-S7.2a Stage 5 on Simu5G 1.8.1 (S5-1): E0v configurations and the Q-0p option (plan rev. 1 §2.1, RD-1, RD-2, RD-4).

    python3 tools/m2s72s5_gen.py write | check            write / compare m2s72s5.ini
    python3 tools/m2s72s5_gen.py verify <opp_run args...>  every runnable m2s72s5.ini config exact on OMNeT++'s own
                                                           resolution (opp_run -q runconfig; no simulation)
    python3 tools/m2s72s5_gen.py diff <opp_run args...>    RD-4: generated-configuration differences of the option
                                                           comparisons, classified against each comparison's claim

Isolation from the accepted baseline:
  * tools/m2s72_gen.py (accepted) is imported unchanged; it must regenerate the committed m2s72.ini byte for byte
    (checked first; a difference stops this generator), and m2s72.ini is never written here.
  * m2s72s5.ini starts with "include m2s72.ini" and only ADDS sections; a name already defined there is refused,
    except the existing load mixins and the M2S72-MACLOG / M2S72-HARQ16 mixins, which are re-used by reference.
  * Q-0p (M2S71-q0p-Ca-sus, QOS_PF on the shared DRB 1 / 2, equal nasc-be profiles) is registered as a load-capable
    variant AFTER the accepted generator has run, translated with the accepted rules, and written here.

Configurations (all C-a, D-4 timing, M2S72-SL, learning recorders, eventlog window, seed set by the runner):
  M2S72-E0v-<q0|qdu>-f<1|2|4|8>    E0 [A] re-run on 1.8.1: the E0 chain of M2S72-E0-<o>-f<F> plus the UE MAC log
                                   (RD-1: UL H-ARQ evidence "the grant is not used"); verified equal to it otherwise
  M2S72-E0vNL-q0-f<F>              non-perturbation twin: the same config without M2S72-MACLOG and the UE MAC log
  M2S72-E0v-q0p-f<1|2>             E0v-p: Q-0p (P-4)
  M2S72-E0vH5-<q0|qdu>-f<1|2>      E0v-H5: Simu5G default 5 H-ARQ processes (no HARQ16 mixin) (RD-1)
  M2S72-E0vH5NL-q0-f1              H5 non-perturbation twin
  M2S72-E0vN[H5]-<q0|q0p|qdu>-<one0|sym>-n<N>-f<F>
                                   E0v-N saturation bracket (RD-2): every E1 option x placement x N x HARQ, UL factor =
                                   DL factor, F in E0VN_FACTORS (exact intervals only). Generated for review; the
                                   S5-1 runner refuses them (the per-UE N > 1 checker is the next increment, G-2)
"""
import hashlib
import importlib.util
import json
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
_spec = importlib.util.spec_from_file_location("m2s72_gen", os.path.join(HERE, "m2s72_gen.py"))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)
GenError = G.GenError
M2 = G.M2
OUT5 = os.path.join(M2, "m2s72s5.ini")

Q0P = "M2S71-q0p-Ca-sus@L"
QDU = "M2S71-qdu-Ca-sus@L"
# Q-de (decision D-1, approved 2026-11-15): Q-d's DRB mapping (gPTP DL rule -> QFI 10 -> DRB 4, UM, LCG 2) with the
# nasc-be profile on the gPTP DRB, i.e. Q-d minus exactly its gPTP priority. Its load source is Q-d's (identical traffic
# by construction: the same load mixins); its sections are derived from Q-d's generated sections (generate()).
OPTS5 = {"q0": "M2S71-q0-Ca-sus@L", "q0p": Q0P, "qdu": QDU, "qde": QDU}
SCHED = {"q0": None, "q0p": "QOS_PF", "qdu": "QOS_PF", "qde": "QOS_PF"}   # expected effective scheduler (None: default MAXCI)
E0VN_H5_OPTS = ("q0", "q0p", "qdu")           # Q-de is in E1 loaded HARQ16 only (D-1), so in the HARQ16 bracket only
E0V_FACTORS = (1, 2, 4, 8)
E0V_TWIN = "q0"
E0V_P_FACTORS = (1, 2)
E0V_H5_FACTORS = (1, 2)
E0V_H5_TWIN = ("q0", 1)
E0VN_FACTORS = (0.5, 0.8, 1, 1.25, 1.6, 2)
E0VN_PL = [("one0", n) for n in (1, 2, 4, 8)] + [("sym", n) for n in (2, 4, 8)]
UELOG = "M2S72S5-MACLOG-UE"
UELOG_KEY = "*.ue[*].cellularNic.nrMac.cmdenv-log-level"
UELOG_TEXT = f"""\
[Config {UELOG}]
description = "(mixin, Stage 5 S5-1, OBSERVATION ONLY) UE NR MAC log lines on stdout (UL H-ARQ evidence: the grant is not used); prefix and non-express mode from M2S72-MACLOG; non-perturbation shown by the NL twins"
{UELOG_KEY} = info
"""
COMMON = ["M2S72-SL", "M2S72-L", "M2S72-ev"]


def short_of(o):
    return {"q0": "q0-Ca-L", "q0p": "q0p-Ca-L", "qdu": "qdu-Ca-L", "qde": "qde-Ca-L"}[o]


def chain(o, n, ld, h16=True, logs=True):
    s = short_of(o)
    return ((["M2S72-MACLOG", UELOG] if logs else []) + [ld] + (["M2S72-HARQ16"] if h16 else []) + COMMON
            + [f"M2S72D4N{n}-{s}", f"M2S72N{n}-{s}", f"M2S72B-{s}"])


def e0vn_name(o, pl, n, f, h5):
    return f"M2S72-E0vN{'H5' if h5 else ''}-{o}-{pl}-n{n}-f{G.flabel(f)}"


def matrix():
    """runnable config -> (option, placement, N, DL factor, UL factor, HARQ16, logs, kind)"""
    m = {}
    for o in ("q0", "qdu"):
        for f in E0V_FACTORS:
            m[f"M2S72-E0v-{o}-f{G.flabel(f)}"] = (o, "one0", 1, f, 1, True, True, "core")
            if o == E0V_TWIN:
                m[f"M2S72-E0vNL-{o}-f{G.flabel(f)}"] = (o, "one0", 1, f, 1, True, False, "twin")
    for o in ("q0p", "qde"):
        for f in E0V_P_FACTORS:
            m[f"M2S72-E0v-{o}-f{G.flabel(f)}"] = (o, "one0", 1, f, 1, True, True, "p")
    for o in ("q0", "qdu"):
        for f in E0V_H5_FACTORS:
            m[f"M2S72-E0vH5-{o}-f{G.flabel(f)}"] = (o, "one0", 1, f, 1, False, True, "h5")
    o, f = E0V_H5_TWIN
    m[f"M2S72-E0vH5NL-{o}-f{G.flabel(f)}"] = (o, "one0", 1, f, 1, False, False, "h5twin")
    for o in OPTS5:
        for pl, n in E0VN_PL:
            for f in E0VN_FACTORS:
                for h5 in ((False, True) if o in E0VN_H5_OPTS else (False,)):
                    m[e0vn_name(o, pl, n, f, h5)] = (o, pl, n, f, f, not h5, True, "N")
    return m


def accepted_text():
    text, _ = G.generate()
    cur = open(G.OUT).read()
    if text != cur:
        raise GenError("the accepted generator does not regenerate the committed m2s72.ini byte for byte; m2s72s5.ini "
                       "is generated only on top of an unchanged m2s72.ini")
    return text


def register_q0p():
    G.LOAD_VAR[Q0P] = "M2S71-q0p-Ca-sus"
    G.D4_SOURCES = tuple(G.D4_SOURCES) + (Q0P,)
    G.SOURCES[Q0P] = ("q0p-Ca-L", (1, 2, 4, 8))


def generate():
    base = accepted_text()                   # also fills G.LOAD_REC / APPSEL_RESTS of the accepted variants
    have = set(re.findall(r"^\[Config ([^\]]+)\]", base, re.M))
    register_q0p()
    sections, _ = G.parse(G.INI)
    src = G.src_of(Q0P)
    if src not in sections:
        raise GenError(f"source config {src} not found")
    entries = G.flatten(sections, src)
    tr, eff, used = G.translate(Q0P, G.SOURCES[Q0P][1], entries)
    gen_hash = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    acc_hash = hashlib.sha256(open(os.path.join(HERE, "m2s72_gen.py"), "rb").read()).hexdigest()
    ini_hash = hashlib.sha256(base.encode()).hexdigest()
    out = ["# GENERATED by simulations/m2/tools/m2s72s5_gen.py -- do not edit; regenerate with",
           "#   python3 tools/m2s72s5_gen.py write     (check: python3 tools/m2s72s5_gen.py check)",
           "# M2-S7.2a Stage 5 on Simu5G 1.8.1, increment S5-1: E0v configurations and the Q-0p option",
           "# (simulations/m2/plans/M2-S7.2a-stage5-plan-1.8.1.md rev. 1 on plan/m2-s7.2a-stage5; protocol",
           "# results/M2-S7.2a-e0v-protocol.md). Adds sections only; m2s72.ini is included unchanged.",
           f"# generator sha256 {gen_hash}",
           f"# accepted generator tools/m2s72_gen.py sha256 {acc_hash}",
           f"# m2s72.ini sha256 {ini_hash}",
           "", "include m2s72.ini", ""]
    out += ["#" + "-" * 100,
            f"# Abstract base: {src} flattened ({len(entries)} entries in OMNeT++ lookup order: "
            f"{' > '.join(G.c3(sections, src))} > General) and translated for {G.NETWORK} as a load-capable variant",
            "# (Stage 5: no load in the base; placed by the load mixins M2S72LD-*), with the accepted rules.",
            f"[Config M2S72B-{short_of('q0p')}]",
            f'description = "(abstract, generated) {Q0P} on M2S72Bridge"',
            f"network = {G.NETWORK}"]
    for e, name, lines in tr:
        out.append(f"# [{e.section}] {e.file}:{e.line} rule {name}")
        out += lines
    out.append("")
    for n in G.SOURCES[Q0P][1]:
        out += G.mixin_n(Q0P, short_of("q0p"), n, eff) + [""]
        out += G.mixin_d4(short_of("q0p"), n, Q0P) + [""]
    out += qde_sections(base, have)
    out += ["#" + "-" * 100, UELOG_TEXT]
    ext, done = {}, set()
    mx = matrix()
    heads = {"core": "# E0v core [A -> 1.8.1]: the approved E0 matrix (N = 1, load on UE 0, DL factor 1, 2, 4, 8, UL 1 x L_tot, "
                     "HARQ16 experimental control, MAC log) + the UE MAC log; twins M2S72-E0vNL-q0-f<F> without both logs",
             "p": "# E0v-p (P-4, D-1): Q-0p and Q-de at DL factor 1, 2 (N = 1, UL 1 x L_tot, HARQ16)",
             "h5": "# E0v-H5 (RD-1): Simu5G default 5 H-ARQ processes (no HARQ16 mixin), DL factor 1, 2; twin M2S72-E0vH5NL-q0-f1",
             "N": "# E0v-N (RD-2): saturation bracket of every E1 combination with load; UL factor = DL factor; exact intervals only. "
                  "Generated for review; NOT runnable by the S5-1 runner (N > 1 per-UE checker: next increment)"}
    shown = set()
    for nm, (o, pl, n, f, ful, h16, logs, kind) in mx.items():
        k = "core" if kind in ("core", "twin") else "h5" if kind in ("h5", "h5twin") else kind
        if k not in shown:
            out += ["#" + "-" * 100, heads[k]]
            shown.add(k)
        cfg = OPTS5[o]
        ld, lines = G.load_mixin(cfg, pl, n, f, ful)
        if ld not in have and ld not in done:
            out += lines + [""]
            done.add(ld)
        if nm in have:
            raise GenError(f"{nm} already defined in m2s72.ini")
        ext[nm] = chain(o, n, ld, h16, logs)
        what = {"core": "E0v core", "twin": "E0v non-perturbation twin (no MAC logs)", "p": f"E0v-p ({'Q-0p' if o == 'q0p' else 'Q-de'})",
                "h5": "E0v-H5 (5 H-ARQ processes)", "h5twin": "E0v-H5 non-perturbation twin (no MAC logs)", "N": "E0v-N bracket"}[kind]
        desc = (f"{what}: {G.src_of(cfg)}{' with the nasc-be profile on the gPTP DRB (Q-de)' if o == 'qde' else ''}, {pl}, numUe = {n}, DL factor {f}, UL factor {ful}, "
                f"{'HARQ16 (experimental control)' if h16 else 'HARQ 5 (Simu5G default)'}{', MAC logs' if logs else ''}")
        out += [f"[Config {nm}]", f'description = "{desc}"', f"extends = {', '.join(ext[nm])}", ""]
    for name in (UELOG, f"M2S72B-{short_of('q0p')}", f"M2S72B-{short_of('qde')}"):
        if name in have:
            raise GenError(f"{name} already defined in m2s72.ini")
    G.check_inheritance(ext)
    return "\n".join(out).rstrip("\n") + "\n", used


QDE_NS = (1, 2, 4, 8)


def qde_sections(base, have):
    """Q-de sections derived from the accepted Q-d sections of m2s72.ini: the base and the D-4 mixins extend Q-d's;
    each per-N mixin is Q-d's text with ONLY the gPTP DRB's profile "nasc-gptp" replaced by "nasc-be" (exactly N
    substitutions, every other byte of the section unchanged; refused otherwise)"""
    s = short_of("qdu")
    q = short_of("qde")
    out = ["#" + "-" * 100,
           "# Q-de (decision D-1): Q-d's DRB mapping with the nasc-be profile on the gPTP DRB (Q-d minus exactly its gPTP",
           "# priority). Base and D-4 mixins extend Q-d's; each per-N mixin is Q-d's generated section with only the gPTP",
           "# DRB's profile changed (nasc-gptp -> nasc-be). Load: Q-d's load mixins (identical traffic).",
           f"[Config M2S72B-{q}]",
           f'description = "(abstract, generated) Q-de: {QDU} on M2S72Bridge, gPTP DRB with the nasc-be profile (per-N mixins)"',
           f"extends = M2S72B-{s}", ""]
    for n in QDE_NS:
        src = f"M2S72N{n}-{s}"
        m = re.search(rf"^\[Config {re.escape(src)}\]\n(.*?)(?=^\[Config |\Z)", base, re.M | re.S)
        if not m:
            raise GenError(f"{src} not found in m2s72.ini")
        body = m.group(1).rstrip("\n").split("\n")
        if not body[0].startswith("description = "):
            raise GenError(f"{src}: unexpected layout")
        new, k = [], 0
        for line in body[1:]:
            if 'profile: "nasc-gptp"' in line:
                if "drbId: 4" not in line or "mappedQfis: [10]" not in line:
                    raise GenError(f"{src}: nasc-gptp outside the gPTP DRB: {line.strip()}")
                line = line.replace('profile: "nasc-gptp"', 'profile: "nasc-be"')
                k += 1
            new.append(line)
        if k != n:
            raise GenError(f"{src}: {k} gPTP DRB profiles replaced, expected {n}")
        for name in (f"M2S72N{n}-{q}", f"M2S72D4N{n}-{q}"):
            if name in have:
                raise GenError(f"{name} already defined in m2s72.ini")
        out += [f"[Config M2S72N{n}-{q}]",
                f'description = "(mixin, generated) {q} at numUe = {n}: {src} with the gPTP DRB profile nasc-be ({n} replacement(s))"']
        out += new + [""]
        out += [f"[Config M2S72D4N{n}-{q}]", f'description = "(mixin, generated) D-4 of {q} at numUe = {n}: as M2S72D4N{n}-{s}"',
                f"extends = M2S72D4N{n}-{s}", ""]
    return out


# ------------------------------------------------------------------------------------------------ verification -----
def runconfig(cmd, ini, cfg):
    r = subprocess.run(cmd + ["-f", ini, "-c", cfg, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
    try:
        return G.runconfig_entries(r.stdout)
    except GenError as ex:
        raise GenError(f"{cfg}: {ex}; stderr {r.stderr[-400:]}")


def eff_value(ents, path):
    return G.first_match(ents, path)


def verify_entries(nm, ents, spec_args, h16, logs, o):
    """exact checks of one generated config on OMNeT++'s resolution"""
    cfg, pl, n, f, ful = spec_args
    spec, ues, dl, ul = G.load_spec(cfg, pl, n, f, ful)
    probs = []
    for (mod, rest), v in spec.items():
        k, got = eff_value(ents, f"{mod}.{rest}")
        if got != v:
            probs.append(f"{mod}.{rest}: effective {got!r} (from {k!r}), expected {v!r}")
    net = G.NETWORK.rsplit(".", 1)[1]
    mods = {}
    for (mod, rest) in spec:
        m = re.fullmatch(r"(.+)\.app\[(\d+)\]", mod)
        if m:
            mods.setdefault((m.group(1), int(m.group(2))), set()).add(rest)
    for k, v in ents:
        j = k.find(".app[")
        if j < 0:
            continue
        e = k.index("]", j)
        prefix, idx, suffix = k[:j], k[j + 5:e], k[e + 2:]
        for (owner, a), rests in mods.items():
            if G.pat_re(prefix).match(f"{net}.{owner}") and G.pat_re(f"x[{idx}]").match(f"x[{a}]") and suffix not in rests:
                probs.append(f"foreign setting {k} = {v} reaches load app {owner}.app[{a}]")
    for path, v in {"listener.eth[0].address": f'"{G.LISTENER_MAC}"', "numUe": str(n)}.items():
        k, got = eff_value(ents, path)
        if got != v:
            probs.append(f"{path}: effective {got!r}, expected {v!r}")
    for path in ["gnb1.cellularNic.mac.harqProcesses"] + [f"ue[{kk}].cellularNic.nrMac.harqProcesses" for kk in range(n)]:
        k, got = eff_value(ents, path)
        if (h16 and got != "16") or (not h16 and k is not None):
            probs.append(f"{path}: effective {got!r} (from {k!r}), expected {'16' if h16 else 'no setting (default 5)'}")
    for d in ("Dl", "Ul"):
        k, got = eff_value(ents, f"gnb1.cellularNic.mac.schedulingDiscipline{d}")
        want = None if SCHED[o] is None else f'"{SCHED[o]}"'
        if got != want:
            probs.append(f"schedulingDiscipline{d}: effective {got!r}, expected {want or 'no setting (default MAXCI)'}")
    keys = {k for k, _ in ents}
    logkeys = list(G.MACLOG_KEYS) + [UELOG_KEY]
    has = [x for x in logkeys if x in keys]
    if logs and has != logkeys:
        probs.append(f"MAC logs incomplete: {has}")
    if not logs and has:
        probs.append(f"MAC log entries in a no-log twin: {has}")
    return probs


def norm(ents, nm, drop=()):
    return [(k, v.replace(nm, "<config>")) for k, v in ents if k not in ("description", "extends") and k not in drop]


def first(pairs):
    """key -> value of the FIRST entry of each key (OMNeT++ ini lookup: the first matching entry wins)"""
    d = {}
    for k, v in pairs:
        d.setdefault(k, v)
    return d


def verify(cmd):
    mx = matrix()
    bad, got = 0, {}
    for nm, (o, pl, n, f, ful, h16, logs, kind) in mx.items():
        ents = runconfig(cmd, "m2s72s5.ini", nm)
        got[nm] = ents
        probs = verify_entries(nm, ents, (OPTS5[o], pl, n, f, ful), h16, logs, o)
        if probs:
            print(f"{nm}: DIFFERENT {probs[:6]}")
            bad += 1
        elif kind != "N":
            print(f"{nm}: exact ({o}, {pl}, numUe {n}, DL {f}, UL {ful}, {'HARQ16' if h16 else 'HARQ5'}, "
                  f"{'MAC logs' if logs else 'no MAC logs'}, scheduler {SCHED[o] or 'MAXCI (default)'})")
    print(f"E0v-N bracket: {sum(1 for v in mx.values() if v[-1] == 'N')} configs checked exactly (only differences are printed)")
    # E0v core = the approved E0 config + exactly the UE MAC log entry
    for o in ("q0", "qdu"):
        for f in E0V_FACTORS:
            a, b = f"M2S72-E0-{o}-f{G.flabel(f)}", f"M2S72-E0v-{o}-f{G.flabel(f)}"
            A = norm(runconfig(cmd, "m2s72.ini", a), a)
            Bv = norm(got[b], b)
            ok = [x for x in Bv if x[0] != UELOG_KEY] == A and [x for x in Bv if x[0] == UELOG_KEY] == [(UELOG_KEY, "info")]
            print(f"{b} = {a} (accepted E0 config) + exactly {UELOG_KEY} = info: {'yes' if ok else 'NO'}")
            bad += not ok
    # twins: the logged config without exactly the log entries
    pairs = [(f"M2S72-E0v-{E0V_TWIN}-f{G.flabel(f)}", f"M2S72-E0vNL-{E0V_TWIN}-f{G.flabel(f)}") for f in E0V_FACTORS]
    o, f = E0V_H5_TWIN
    pairs.append((f"M2S72-E0vH5-{o}-f{G.flabel(f)}", f"M2S72-E0vH5NL-{o}-f{G.flabel(f)}"))
    logkeys = set(G.MACLOG_KEYS) | {UELOG_KEY}
    for a, b in pairs:
        A, Bt = norm(got[a], a), norm(got[b], b)
        ok = [x for x in A if x[0] not in logkeys] == Bt and {x[0] for x in A if x not in Bt} == logkeys
        print(f"twin {b} = {a} without exactly the MAC-log entries: {'yes' if ok else 'NO'}")
        bad += not ok
    # H5 / H16 pairs: identical apart from the HARQ16 entries
    for o in ("q0", "qdu"):
        for f in E0V_H5_FACTORS:
            a, b = f"M2S72-E0v-{o}-f{G.flabel(f)}", f"M2S72-E0vH5-{o}-f{G.flabel(f)}"
            A, Bh = norm(got[a], a), norm(got[b], b)
            extra = [x for x in A if x not in Bh]
            ok = [x for x in A if "harqProcesses" not in x[0]] == Bh and extra and all("harqProcesses" in k for k, _ in extra)
            print(f"pair {a} / {b} identical apart from the HARQ16 entries: {'yes' if ok else 'NO ' + str(extra[:4])}")
            bad += not ok
    return bad


# ----------------------------------------------------------------------------------------- RD-4 option diff -------
def parse_list(v):
    """an OMNeT++ JSON-like value ([{key: value, ...}, ...] or {name: {...}}) -> Python object"""
    s = re.sub(r'([{,]\s*)([A-Za-z_][A-Za-z0-9_]*)\s*:', r'\1"\2":', v)
    return json.loads(s)


def drb_view(v):
    return {(d["ue"], d["drbId"]): d for d in parse_list(v)}


CLAIMS = {
    "scheduler": "only the MAC scheduling discipline differs (DRB profile annotations, read only by QoSAwareScheduler, may differ; "
                 "every DRB's mapping, RLC mode, LCG and every traffic / load setting equal)",
    "mapping": "only the gPTP DRB mapping differs (an added DL QFI rule and the DRB(s) it maps to); every added DRB has the profile of "
               "the default DRB (no priority difference); scheduler, traffic and load equal",
    "priority": "only the profile of the gPTP DRB differs (its priority); mapping, scheduler, traffic and load equal",
}


def classify_diff(claim, A, B):
    """differences of two resolved configurations (key -> value) and whether each is allowed by the claim"""
    keys = sorted(set(A) | set(B))
    diffs, bad = [], []
    for k in keys:
        a, b = A.get(k), B.get(k)
        if a == b:
            continue
        diffs.append((k, a, b))
        allowed = False
        if k.endswith("schedulingDisciplineDl") or k.endswith("schedulingDisciplineUl"):
            allowed = claim == "scheduler"
        elif k.endswith("bearerConfigurator.drbProfiles"):
            allowed = True        # definitions only; their USE is checked through staticDrbs below
        elif k.endswith("bearerConfigurator.staticDrbs"):
            da, db = drb_view(a or "[]"), drb_view(b or "[]")
            strip = lambda d: {x: y for x, y in d.items() if x != "profile"}   # noqa: E731
            same_ids = set(da) == set(db)
            if claim == "scheduler":
                allowed = same_ids and all(strip(da[i]) == strip(db[i]) for i in da)
            elif claim == "priority":
                changed = {i for i in da if da[i].get("profile") != db.get(i, {}).get("profile")}
                allowed = same_ids and all(strip(da[i]) == strip(db[i]) for i in da) and bool(changed) and \
                    all(10 in (da[i].get("mappedQfis") or []) for i in changed)
            elif claim == "mapping":
                common = set(da) & set(db)
                added = set(db) - set(da)
                default = {i: d for i, d in db.items() if d.get("isDefault")}
                prof = {i[0]: d.get("profile") for i, d in default.items()}
                allowed = set(da) <= set(db) and all(da[i] == db[i] for i in common) and bool(added) and \
                    all(db[i].get("profile") == prof.get(i[0]) for i in added)
        elif k.endswith("bearerConfigurator.dlQfiRules"):
            allowed = claim == "mapping"
        if not allowed:
            bad.append(k)
    return diffs, bad


def diff(cmd):
    """RD-4 / D-1: the generated (resolved) configurations of each option comparison, every difference printed and
    classified against the comparison's claim. Expected: q0 -> q0p scheduler only; q0p -> qde mapping only; qde -> qdu
    priority only; q0p -> qdu NOT mapping-only (mapping + priority: reported as such, never used as a mapping test)"""
    sets = [("N = 1, DL factor 1, HARQ16 (E0v core / E0v-p)", {o: f"M2S72-E0v-{o}-f1" for o in OPTS5}),
            ("sym, N = 4, factor 1, HARQ16 (E0v-N)", {o: e0vn_name(o, "sym", 4, 1, False) for o in OPTS5}),
            ("one0, N = 8, factor 1.25, HARQ16 (E0v-N)", {o: e0vn_name(o, "one0", 8, 1.25, False) for o in OPTS5})]
    plan = (("q0", "q0p", "scheduler", True), ("q0p", "qde", "mapping", True), ("qde", "qdu", "priority", True),
            ("q0p", "qdu", "mapping", False))
    bad = 0
    for label, names in sets:
        res = {o: first(norm(runconfig(cmd, "m2s72s5.ini", nm), nm)) for o, nm in names.items()}
        print(f"== {label}")
        for a, b, claim, expect in plan:
            diffs, nb = classify_diff(claim, res[a], res[b])
            verdict = "ISOLATED" if not nb else "NOT ISOLATED"
            print(f"   {a} -> {b}, claim '{claim}' ({CLAIMS[claim]}): {verdict} (expected {'ISOLATED' if expect else 'NOT ISOLATED'}); "
                  f"{len(diffs)} differing entries" + ("" if not nb else f"; not allowed by the claim: {nb}"))
            for k, va, vb in diffs:
                print(f"      {k}\n         {a}: {va}\n         {b}: {vb}")
            if (not nb) != expect:
                bad += 1
    return bad


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    try:
        text, used = generate()
    except GenError as ex:
        print(f"m2s72s5_gen: ERROR: {ex}", file=sys.stderr)
        return 2
    print(f"{Q0P}: rules {dict(sorted(used.items()))}")
    if mode == "write":
        open(OUT5, "w").write(text)
        print(f"wrote {OUT5} sha256 {hashlib.sha256(text.encode()).hexdigest()}")
        return 0
    if mode == "check":
        cur = open(OUT5).read() if os.path.exists(OUT5) else None
        same = cur == text
        print(f"regenerated sha256 {hashlib.sha256(text.encode()).hexdigest()}; committed "
              f"{hashlib.sha256(cur.encode()).hexdigest() if cur is not None else 'absent'}: {'IDENTICAL' if same else 'DIFFERENT'}")
        return 0 if same else 1
    if mode == "verify":
        b = verify(sys.argv[2:])
        print(f"m2s72s5.ini configuration check: {'all as generated' if not b else str(b) + ' DIFFERENT'}")
        return 1 if b else 0
    if mode == "diff":
        b = diff(sys.argv[2:])
        print(f"option comparisons (RD-4, D-1): {'every comparison as expected' if not b else str(b) + ' comparison(s) NOT as expected'}")
        return 1 if b else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
