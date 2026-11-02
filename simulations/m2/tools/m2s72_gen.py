#!/usr/bin/env python3
"""M2-S7.2a configuration generator (migration/m2-s7.2a-design.md rev. 2, 1.4 and D-2 (a)).

    m2s72_gen.py write              write simulations/m2/m2s72.ini
    m2s72_gen.py check              regenerate in memory; exit 1 unless byte-identical to the committed m2s72.ini
    m2s72_gen.py verify <opp_run..> also compare this generator's flattening of every source config with
                                    OMNeT++'s own effective configuration (opp_run -q runconfig), and check on
                                    OMNeT++'s resolution of m2s72.ini that no T0 config carries the static-listener
                                    settings and every non-T0 config does (rev. 2.1 A-1); exit 1 on any difference.
                                    The opp_run command line (without -c/-r/-q) follows "verify".

Input: simulations/m2/omnetpp.ini (which includes ../m1/omnetpp.ini), read as text. For every source config in
SOURCES, the generator
  1. resolves the config's sections in OMNeT++'s order (C3 linearization of "extends", then [General]) and
     lists every entry in lookup order (first match wins), with its raw value (${...} unexpanded);
  2. translates every entry with exactly one rule of RULES; an entry that matches no rule (unexpected) or
     several rules, a rule whose value condition fails, a value naming a per-UE module that no rule handles
     (untranslatable), a rule restricted to N = 1 in a source requested at N > 1, or a missing required
     setting (REQUIRED) stops the generator with an error and writes nothing;
  3. writes the abstract base [Config M2S72B-<src>] (the translated entries, in order) and, per requested N,
     the mixins M2S72N<N>-<src> (numUe, per-UE DRBs and UL rules, RNGs) and, for the D-4 sources,
     M2S72D4N<N>-<src> (DL start 0.3 s, provisional), plus the runnable F0/T0 configs.

Translations (design 1.3, 2.2, 3.3; D-3, D-4):
  *.dsTt.  -> *.dsTt[*].     *.talker. -> *.talker[*].     *.ue[0]. -> *.ue[*].     *.*Tt. -> *.nwTt. and *.dsTt[*].
  DS-TT k: engine clockIdentity 0x..d(k+1), every DS-TT ttId 2 + k (DS-TT 0 keeps the single-UE values);
  slave k: sink localAddress "talker[k]"; listener: DL flows to talker[0] as before, plus two DL flows per
  further UE k (apps 3 + 2(k-1) + c, c = 0 PCP 5, c = 1 PCP 0, settings of app[c]); per-UE staticDrbs and
  ulQfiRules (replicated from the UE 0 entries); clock RNGs: talker[k] oscillator -> RNG 2k, dsTt[k] TT
  clock -> RNG 2k+1 (k >= 1; the UE 0 clocks, GM and NW-TT keep RNG 1, so N = 1 is the M2-S6 mapping),
  num-rngs 2N, new RNG j seeded seed-j-mt = j00${repetition} (as M2-S6: seed-0-mt = ${repetition},
  seed-1-mt = 100${repetition}).
"""
import hashlib
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
INI = os.path.join(M2, "omnetpp.ini")
OUT = os.path.join(M2, "m2s72.ini")
NMAX = 8
NETWORK = "nasctime.simulations.m2.M2S72Bridge"

# source config -> (short name, N values generated). N > 1 only where every entry has an N > 1 translation.
SOURCES = {
    "M2S71-q0-idle": ("q0-idle", (1, 2, 4, 8)),
    "M2S71-qdu-idle": ("qdu-idle", (1, 2, 4, 8)),
    "M2S71-q0-load": ("q0-load", (1,)),
    "M2S6-C-a": ("C-a", (1,)),
    "M2S6-E-all": ("E-all", (1,)),
    # stage 4 (Block B, design 9): the S7.1 accuracy configs with the M2-S6 C-a clocks (GM +100 ppm, slave -100 ppm)
    "M2S71-q0-Ca": ("q0-Ca", (1, 2, 4)),
    "M2S71-qdu-Ca": ("qdu-Ca", (1, 2, 4)),
}
D4_SOURCES = ("M2S71-q0-idle", "M2S71-qdu-idle", "M2S71-q0-Ca", "M2S71-qdu-Ca")   # sources of non-T0 configs (D-4 timing)
# Block B (design 9): option -> (ideal-clock source, C-a source); clocks ideal / Ca / Eall (Eall = C-a source + the
# generated TT-clock mixin M2S72-TT-Eall); N = 2, 4 (correctness) and 1 (I-5 reference); seeds 0-4
B_OPTS = {"q0": ("M2S71-q0-idle", "M2S71-q0-Ca"), "qdu": ("M2S71-qdu-idle", "M2S71-qdu-Ca")}
B_N = (1, 2, 4)
B_REPS = "0..4"
# the E-all TT clocks: the sections of M2S6-E-all that are not those of M2S6-C-a (its own entries and M2S6-tt)
EALL_CFG, EALL_BASE = "M2S6-E-all", "M2S6-C-a"
# D-13: DS-TT k TT clock = M2-S6 E-all DS-TT (300 ns, -100 ppb, update phase 3 ms) + k x (100 ns, 50 ppb, 1 ms)
D13 = {"theta0": (300, 100, "ns"), "freqOffsetPpb": (-100, 50, ""), "updateOffset": (3, 1, "ms")}
F0 = {"q0": "M2S71-q0-idle", "qdu": "M2S71-qdu-idle"}  # option -> source (design 8.1: Q-0, Q-d (UM), idle)
F0_N = (1, 2, 4, 8)
LISTENER_APPS = 3          # idle base: app[0..1] DL sources, app[2] sink; extra DL apps start here
D4_SRC_OFFSET = "0.1s + 5ms * ancestorIndex(1)"
D4_OFFSET = "0.3s"         # D-4, provisional: every DL flow starts at 0.3 s (+ 5 ms for the PCP 0 flow, as in S7.1)

# settings that must be present (effective, i.e. first occurrence) in every source, with the value required
REQUIRED = {
    "*.dsTt.eth[1].trafficConditionerLayer.engine.clockIdentity": '"0x00000000000000d1"',
    "*.dsTt.eth[0].measurementLayer.ttId": "2",
    "*.dsTt.eth[1].measurementLayer.ttId": "2",
    "*.dsTt.eth[1].trafficConditionerLayer.syncOut.ttId": "2",
    "*.talker.app[2].io.localAddress": '"talker"',
    "*.listener.app[0..1].io.remoteAddress": '"talker"',
    "*.talker.app[0..1].io.remoteAddress": '"listener"',
    "*.bearerConfigurator.staticDrbs": None,
    "*.bearerConfigurator.ulQfiRules": None,
    "**.clock.oscillator.rng-0": "1",
    "num-rngs": "2",
    "*.upf.numPcapRecorders": "2",
    "*.upf.pcapRecorder[0].moduleNamePatterns": '"ppp[0]"',
    "*.upf.pcapRecorder[1].moduleNamePatterns": '"dnEth"',
    "*.ue[0].numPcapRecorders": "1",
    "*.hasPassThroughTts": "true",
    "sim-time-limit": None,
    "**.pcapRecorder[*].pcapFile": None,
    "*.ue[*].mobility.initialX": "450m + 30m * ancestorIndex(1)",
}
# Checkpoint 1 repair (design rev. 2.1, A-1): fixed listener MAC (outside INET's auto range 0A-AA-xx-xx-xx-xx) and a
# configuration-initialised UPF bridge entry (listener MAC, VID 42) -> dnEth, in every non-T0 config, never in T0
LISTENER_MAC = "0A-AB-00-00-00-01"
SL_VID = 42
SL_INTERFACE = "dnEth"
T0_FORBIDDEN = ("M2S72-SL", "M2S72-L", "M2S72-ev")   # T0 must inherit none of these (nor a D-4 or SL-control mixin)
# for every source with non-T0 configs (the F0 sources): the VLAN the static entry is scoped to
REQUIRED_NONT0 = {"**.app[0..1].tagger.vlanId": str(SL_VID)}
# settings the generated mixins set; a source that already sets them would be silently overridden: refused
ABSENT = (r"\*\.listener\.eth\[[0-9*]+\]\.address", r".*macTable\..*", r"\*\.listener\.\*\*?\.address")

REQUIRED_NGT1 = {   # additionally, for sources generated at N > 1
    "*.listener.numApps": str(LISTENER_APPS),
    "*.talker.numApps": str(LISTENER_APPS),
    "**.app[0..1].source.initialProductionOffset": D4_SRC_OFFSET,
}


class GenError(Exception):
    pass


# ---------------------------------------------------------------- ini parsing (raw text) -------------------------
class Entry:
    def __init__(self, key, value, raw, section, file, line):
        self.key, self.value, self.raw, self.section, self.file, self.line = key, value, raw, section, file, line


def strip_comment(s):
    q = False
    for i, ch in enumerate(s):
        if ch == '"':
            q = not q
        elif ch == "#" and not q:
            return s[:i]
    return s


def parse(path, sections=None, order=None):
    """Sections -> list of Entry, in file order; include is expanded in place (OMNeT++ semantics)."""
    if sections is None:
        sections, order = {}, []
    lines = open(path).read().split("\n")
    cur = "General"
    i = 0
    while i < len(lines):
        ln = lines[i]
        s = strip_comment(ln).rstrip()
        if not s.strip():
            i += 1
            continue
        if s.startswith("include "):
            parse(os.path.join(os.path.dirname(path), s.split(None, 1)[1].strip()), sections, order)
            i += 1
            continue
        if s.startswith("["):
            m = re.fullmatch(r"\[(?:Config )?([^\]]+)\]", s.strip())
            if not m:
                raise GenError(f"{path}:{i + 1}: bad section header {ln!r}")
            cur = m.group(1)
            if cur not in sections:
                sections[cur] = []
                order.append(cur)
            i += 1
            continue
        if ln[:1].isspace():
            raise GenError(f"{path}:{i + 1}: indented line outside an entry {ln!r}")
        raw = [ln]
        start = i
        # continuation: trailing backslash, or following indented lines
        while (strip_comment(raw[-1]).rstrip().endswith("\\") or
               (i + 1 < len(lines) and lines[i + 1][:1].isspace() and strip_comment(lines[i + 1]).strip())):
            i += 1
            raw.append(lines[i])
        i += 1
        text = "\n".join(raw)
        joined = " ".join(strip_comment(r).rstrip().rstrip("\\") for r in raw)
        if "=" not in joined:
            raise GenError(f"{path}:{start + 1}: not an entry {ln!r}")
        k, v = joined.split("=", 1)
        sections.setdefault(cur, [])
        if cur not in order:
            order.append(cur)
        sections[cur].append(Entry(k.strip(), " ".join(v.split()), text, cur, os.path.relpath(path, M2), start + 1))
    return sections, order


def extends_of(sections, name):
    for e in sections[name]:
        if e.key == "extends":
            return [x.strip() for x in e.value.split(",") if x.strip()]
    return []


def c3(sections, name, memo=None):
    memo = {} if memo is None else memo
    if name in memo:
        return memo[name]
    if name not in sections:
        raise GenError(f"unknown section {name}")
    parents = extends_of(sections, name)
    seqs = [list(c3(sections, p, memo)) for p in parents] + [list(parents)]
    out = [name]
    while any(seqs):
        for s in seqs:
            if not s:
                continue
            cand = s[0]
            if not any(cand in t[1:] for t in seqs):
                break
        else:
            raise GenError(f"inconsistent inheritance for {name}")
        out.append(cand)
        for t in seqs:
            if t and t[0] == cand:
                t.pop(0)
    memo[name] = out
    return out


def flatten(sections, cfg):
    lin = c3(sections, cfg)
    out = []
    for s in lin + ["General"]:
        out.extend(sections.get(s, []))
    return out


def expand(v, cfg):
    v = v.replace("${resultdir}", "results").replace("${configname}", cfg).replace("${repetition}", "0")
    if "${" in v:
        raise GenError(f"{cfg}: unsupported iteration/variable in value {v!r}")
    return v


# ---------------------------------------------------------------- translation rules -------------------------------
PER_UE_VALUE = re.compile(r'"talker"|dsTt|ue\[0\]|"talker\[')


def effective(entries):
    eff = {}
    for e in entries:
        eff.setdefault(e.key, e)
    return eff


def drbs_entries(value, what):
    items = re.findall(r"\{[^{}]*\}", value)
    if not items or not re.fullmatch(r"\[\s*(\{[^{}]*\}\s*,?\s*)+\]", value):
        raise GenError(f"{what}: cannot parse {value!r}")
    for it in items:
        if 'ue: "ue[0]"' not in it:
            raise GenError(f"{what}: entry without ue: \"ue[0]\": {it}")
    return items


def per_ue_list(key, value, n, multiline):
    items = drbs_entries(value, key)
    out = [it.replace('ue: "ue[0]"', f'ue: "ue[{k}]"') for k in range(n) for it in items]
    if multiline:
        return f"{key} = [\n" + ",\n".join("    " + x for x in out) + "\n    ]"
    return f"{key} = [" + ", ".join(out) + "]"


def listener_app(k, c):
    return LISTENER_APPS + 2 * (k - 1) + c


class Ctx:
    def __init__(self, cfg, ns):
        self.cfg, self.ns, self.ngt1 = cfg, ns, max(ns) > 1


def r_meta(e, x):
    return [f"# ({e.key} of [{e.section}] not carried: provenance only)"], None


def r_drop_network(e, x):
    return [f"# network = {e.value}  (replaced: network = {NETWORK})"], None


def r_drop_pass(e, x):
    if e.value != "true":
        raise GenError(f"{x.cfg}: *.hasPassThroughTts = {e.value}: M2S72Bridge always has the translators")
    return ["# *.hasPassThroughTts = true  (M2S72Bridge always has the translators)"], None


def r_to_mixin(e, x):
    return [f"# {e.key}  (per-UE, in M2S72N<N>-<src>)"], None


def r_clockid(e, x):
    if e.value != '"0x00000000000000d1"':
        raise GenError(f"{x.cfg}: unexpected DS-TT clockIdentity {e.value}")
    return [f'*.dsTt[{k}].eth[1].trafficConditionerLayer.engine.clockIdentity = "0x00000000000000d{k + 1:x}"'
            for k in range(NMAX)], None


def r_ttid(e, x):
    if e.value != "2":
        raise GenError(f"{x.cfg}: unexpected DS-TT ttId {e.key} = {e.value}")
    rest = e.key[len("*.dsTt."):]
    return [f"*.dsTt[{k}].{rest} = {2 + k}" for k in range(NMAX)], None


def r_sink(e, x):
    if e.value != '"talker"':
        raise GenError(f"{x.cfg}: unexpected {e.key} = {e.value}")
    return [f'*.talker[{k}].app[2].io.localAddress = "talker[{k}]"' for k in range(NMAX)], None


def r_lremote(e, x):
    if e.value != '"talker"':
        raise GenError(f"{x.cfg}: unexpected {e.key} = {e.value}")
    out = ['*.listener.app[0..1].io.remoteAddress = "talker[0]"']
    if x.ngt1:
        out += [f'*.listener.app[{listener_app(k, c)}].io.remoteAddress = "talker[{k}]"'
                for k in range(1, NMAX) for c in (0, 1)]
    return out, None


def r_appsel(e, x):
    m = re.fullmatch(r"\*\*\.app\[(0\.\.1|0|1)\]\.(.+)", e.key)
    sel = {"0..1": (0, 1), "0": (0,), "1": (1,)}[m.group(1)]
    rest = m.group(2)
    if PER_UE_VALUE.search(e.value):
        raise GenError(f"{x.cfg}: untranslatable value {e.key} = {e.value}")
    out = [e.raw]
    if x.ngt1:
        for k in range(1, NMAX):
            for c in sel:
                v = e.value
                if "ancestorIndex" in v:
                    if not rest.startswith("source.") or v.count("ancestorIndex(1)") != v.count("ancestorIndex"):
                        raise GenError(f"{x.cfg}: untranslatable ancestorIndex in {e.key} = {v}")
                    v = v.replace("ancestorIndex(1)", str(c))
                out.append(f"*.listener.app[{listener_app(k, c)}].{rest} = {v}")
    return out, None


def r_app3(e, x):
    if x.ngt1:
        raise GenError(f"{x.cfg}: {e.key}: load application app[3] has no N > 1 translation in stage 2")
    v = e.value
    if e.key == "*.listener.app[3].io.remoteAddress":
        if v != '"talker"':
            raise GenError(f"{x.cfg}: unexpected {e.key} = {v}")
        return ['*.listener.app[3].io.remoteAddress = "talker[0]"'], "N1"
    if PER_UE_VALUE.search(v):
        raise GenError(f"{x.cfg}: untranslatable value {e.key} = {v}")
    return [simple_line(e).replace("*.talker.", "*.talker[*].", 1)], "N1"


def r_oscrng(e, x):
    if e.value != "1":
        raise GenError(f"{x.cfg}: unexpected {e.key} = {e.value}")
    return [f"*.talker[{k}].clock.oscillator.rng-0 = {2 * k}" for k in range(1, NMAX)] + [e.raw], None


def r_ttrng(e, x):
    if e.value != "1":
        raise GenError(f"{x.cfg}: unexpected {e.key} = {e.value}")
    return ([f"*.dsTt[{k}].eth[1].trafficConditionerLayer.ttClock.rng-0 = {2 * k + 1}" for k in range(1, NMAX)]
            + [e.raw]), None


def r_dstt_ttparam(e, x):
    if x.ngt1 and getattr(x, "per_ds_tt", False):
        par = e.key.rsplit(".", 1)[1]
        if par not in D13:
            raise GenError(f"{x.cfg}: {e.key}: no D-13 per-DS-TT rule for {par}")
        base, step, unit = D13[par]
        if e.value != f"{base}{unit}":
            raise GenError(f"{x.cfg}: {e.key} = {e.value}, expected the D-13 DS-TT 0 value {base}{unit}")
        rest = e.key[len("*.dsTt."):]
        return [f"*.dsTt[{k}].{rest} = {base + step * k}{unit}" for k in range(NMAX)], None
    if x.ngt1:
        raise GenError(f"{x.cfg}: {e.key}: per-DS-TT TT-clock parameters (D-13) have no stage-2 translation for N > 1")
    return [simple_line(e).replace("*.dsTt.", "*.dsTt[*].", 1)], "N1"


def simple_line(e):
    lines = e.raw.split("\n")
    return "\n".join(lines)


def check_value(e, x):
    if PER_UE_VALUE.search(e.value):
        raise GenError(f"{x.cfg}: untranslatable value naming a per-UE module: {e.key} = {e.value} "
                       f"({e.file}:{e.line})")


IDENT = re.compile(r"(clockIdentity|ttId|[Aa]ddress|[Ii]dentity|macAddress)$")


def check_ident(e, x, allowed_values=()):
    """A per-UE identity or address setting must have its own per-UE rule; the generic vectorising rules
    (one value for every DS-TT / talker / UE) refuse it (design H-2)."""
    if IDENT.search(e.key) and e.value not in allowed_values:
        raise GenError(f"{x.cfg}: per-UE identity or address setting without a per-UE rule: {e.key} = {e.value} "
                       f"({e.file}:{e.line})")


def r_dstt(e, x):
    check_ident(e, x)
    check_value(e, x)
    return [simple_line(e).replace("*.dsTt.", "*.dsTt[*].", 1)], None


def r_talker(e, x):
    check_ident(e, x, allowed_values=('"listener"',))
    check_value(e, x)
    return [simple_line(e).replace("*.talker.", "*.talker[*].", 1)], None


def r_ue0(e, x):
    check_ident(e, x)
    check_value(e, x)
    return [simple_line(e).replace("*.ue[0].", "*.ue[*].", 1)], None


def r_anytt(e, x):
    check_ident(e, x)
    check_value(e, x)
    s = simple_line(e)
    return [s.replace("*.*Tt.", "*.nwTt.", 1), s.replace("*.*Tt.", "*.dsTt[*].", 1)], None


def r_keep(e, x):
    check_value(e, x)
    return [e.raw], None


KEEP_PREFIXES = ("*.nwTt.", "*.upf.", "*.gnb1.", "*.ue[*].", "*.configurator.", "*.channelControl.",
                 # modules of the M2 unit-test networks (M2S5ChainTest, M2S6InetBridgeTest, M2S4LinkTest):
                 # no such top-level module in M1Bridge or M2S72Bridge, kept unchanged (inert in both)
                 "*.gm.", "*.slave.", "*.tt*.", "*.st*.", "*.br*.")
GENERAL_OPTIONS = ("sim-time-limit", "output-scalar-file", "output-vector-file", "seed-set")

RULES = [
    ("meta", lambda k: k in ("description", "extends"), r_meta),
    ("network", lambda k: k == "network", r_drop_network),
    ("hasPassThroughTts", lambda k: k == "*.hasPassThroughTts", r_drop_pass),
    ("perUeList", lambda k: k in ("*.bearerConfigurator.staticDrbs", "*.bearerConfigurator.ulQfiRules"), r_to_mixin),
    ("dsTtClockId", lambda k: k == "*.dsTt.eth[1].trafficConditionerLayer.engine.clockIdentity", r_clockid),
    ("dsTtTtId", lambda k: re.fullmatch(r"\*\.dsTt\.eth\[[01]\]\.(measurementLayer|trafficConditionerLayer\.syncOut)\.ttId", k), r_ttid),
    ("sinkAddress", lambda k: k == "*.talker.app[2].io.localAddress", r_sink),
    ("listenerRemote", lambda k: k == "*.listener.app[0..1].io.remoteAddress", r_lremote),
    ("listenerNumApps", lambda k: k == "*.listener.numApps", r_keep),
    ("appSel", lambda k: re.fullmatch(r"\*\*\.app\[(0\.\.1|0|1)\]\..+", k), r_appsel),
    ("app3", lambda k: re.fullmatch(r"(\*\*|\*\.talker|\*\.listener)\.app\[3\]\..+", k), r_app3),
    ("oscRng", lambda k: k == "**.clock.oscillator.rng-0", r_oscrng),
    ("ttRng", lambda k: k == "**.trafficConditionerLayer.ttClock.rng-0", r_ttrng),
    ("dsTtTtParam", lambda k: re.fullmatch(r"\*\.dsTt\.eth\[1\]\.trafficConditionerLayer\.ttClock\.(theta0|freqOffsetPpb|updateOffset|driftPpbPerS|noiseSigma|tickLength|updateInterval)", k), r_dstt_ttparam),
    ("dsTt", lambda k: k.startswith("*.dsTt.") and not re.fullmatch(r"\*\.dsTt\.eth\[[01]\]\.(measurementLayer|trafficConditionerLayer\.syncOut)\.ttId", k)
     and k != "*.dsTt.eth[1].trafficConditionerLayer.engine.clockIdentity"
     and not re.fullmatch(r"\*\.dsTt\.eth\[1\]\.trafficConditionerLayer\.ttClock\.(theta0|freqOffsetPpb|updateOffset|driftPpbPerS|noiseSigma|tickLength|updateInterval)", k), r_dstt),
    ("talker", lambda k: k.startswith("*.talker.") and k not in ("*.talker.app[2].io.localAddress",)
     and not k.startswith("*.talker.app[3]."), r_talker),
    ("ue0", lambda k: k.startswith("*.ue[0]."), r_ue0),
    ("anyTt", lambda k: k.startswith("*.*Tt."), r_anytt),
    ("listener", lambda k: k.startswith("*.listener.") and k not in ("*.listener.numApps", "*.listener.app[0..1].io.remoteAddress")
     and not k.startswith("*.listener.app[3]."), r_keep),
    ("bearerGlobal", lambda k: k in ("*.bearerConfigurator.dlQfiRules", "*.bearerConfigurator.drbProfiles"), r_keep),
    ("modulesShared", lambda k: k.startswith(KEEP_PREFIXES), r_keep),
    ("starstar", lambda k: k.startswith("**.") and not re.fullmatch(r"\*\*\.app\[(0\.\.1|0|1|3)\]\..+", k)
     and k not in ("**.clock.oscillator.rng-0", "**.trafficConditionerLayer.ttClock.rng-0"), r_keep),
    ("general", lambda k: k in GENERAL_OPTIONS or re.fullmatch(r"seed-\d+-mt", k) or k == "num-rngs", r_keep),
]


def translate(cfg, ns, entries):
    x = Ctx(cfg, ns)
    eff = effective(entries)
    req = dict(REQUIRED)
    if x.ngt1:
        req.update(REQUIRED_NGT1)
    for k, v in req.items():
        if k not in eff:
            raise GenError(f"{cfg}: missing required setting {k}")
        if v is not None and eff[k].value != v:
            raise GenError(f"{cfg}: required setting {k} = {eff[k].value}, expected {v}")
    for e in entries:
        for pat in ABSENT:
            if re.fullmatch(pat, e.key):
                raise GenError(f"{cfg}: source sets {e.key} = {e.value} ({e.file}:{e.line}), which the generated "
                               f"static-listener mixin M2S72-SL owns")
    if cfg in D4_SOURCES:
        for k, v in REQUIRED_NONT0.items():
            if k not in eff:
                raise GenError(f"{cfg}: missing required setting {k} (VLAN of the static listener entry)")
            if eff[k].value != v:
                raise GenError(f"{cfg}: required setting {k} = {eff[k].value}, expected {v} (VLAN of the static listener entry)")
        other = {e.key: e.value for e in eff.values() if e.key.endswith("tagger.vlanId") and e.value != str(SL_VID)}
        if other:
            raise GenError(f"{cfg}: traffic on a VLAN other than {SL_VID}: {other}; the static listener entry covers VID {SL_VID} only")
    out, used = [], {}
    for e in entries:
        hits = [(n, f) for n, p, f in RULES if p(e.key)]
        if not hits:
            raise GenError(f"{cfg}: unexpected setting {e.key} = {e.value} ({e.file}:{e.line}, [{e.section}])")
        if len(hits) > 1:
            raise GenError(f"{cfg}: setting {e.key} matches several rules {[h[0] for h in hits]}")
        name, f = hits[0]
        lines, tag = f(e, x)
        used[name] = used.get(name, 0) + 1
        out.append((e, name, lines))
    return out, eff, used


# ---------------------------------------------------------------- output ------------------------------------------
def mixin_n(cfg, short, n, eff):
    s = [f"[Config M2S72N{n}-{short}]",
         f'description = "(mixin, generated) {short} at numUe = {n}: per-UE DRBs and UL rules, clock RNGs'
         + (', extra DL flows' if n > 1 else '') + '"',
         f"*.numUe = {n}",
         f"num-rngs = {2 * n}"]
    s += [f"seed-{j}-mt = {j}00${{repetition}}" for j in range(2, 2 * n)]   # as M2-S6: seed-1-mt = 100${repetition}
    if n > 1:
        s.append(f"*.listener.numApps = {LISTENER_APPS + 2 * (n - 1)}")
    for key in ("*.bearerConfigurator.staticDrbs", "*.bearerConfigurator.ulQfiRules"):
        e = eff[key]
        s.append(per_ue_list(key, e.value, n, "\n" in e.raw))
    return s


def mixin_d4(short, n):
    s = [f"[Config M2S72D4N{n}-{short}]",
         f'description = "(mixin, generated) D-4 (provisional): every DL flow to talker[k] starts at {D4_OFFSET} '
         f'(PCP 0 flow + 5 ms), numUe = {n}"',
         f"*.listener.app[0..1].source.initialProductionOffset = {D4_OFFSET} + 5ms * ancestorIndex(1)"]
    s += [f"*.listener.app[{listener_app(k, c)}].source.initialProductionOffset = {D4_OFFSET} + {5 * c}ms"
          for k in range(1, n) for c in (0, 1)]
    return s


FIXED = """\
[Config M2S72-L]
description = "(mixin) F0-6 learning recorders: UPF N3 (ppp[0]) and N6 (dnEth), every packet, first 128 bytes"
*.upf.numPcapRecorders = 4
*.upf.pcapRecorder[2].moduleNamePatterns = "ppp[0]"
*.upf.pcapRecorder[3].moduleNamePatterns = "dnEth"
*.upf.pcapRecorder[2..3].packetFilter = "*"
*.upf.pcapRecorder[2..3].snaplen = 128

[Config M2S72-ev]
description = "(mixin) F0-7 eventlog over [0, 0.5 s], INET log lines of the UPF MAC table only (run in non-express mode)"
record-eventlog = true
eventlog-file = ${resultdir}/${configname}/${repetition}.elog
eventlog-recording-intervals = ..0.5s
cmdenv-event-banners = false
*.upf.ethBridge.macTable.cmdenv-log-level = info
**.cmdenv-log-level = off

[Config M2S72-SL]
description = "(mixin) design rev. 2.1 A-1: fixed listener MAC and configuration-initialised UPF bridge entry (listener, VID 42) -> dnEth"
*.listener.eth[0].address = "%(mac)s"
*.upf.ethBridge.macTable.forwardingTable = [{address: "%(mac)s", vlan: %(vid)d, interface: "%(ifc)s"}]

# F0-6 negative controls (design rev. 2.1; Checkpoint 1 rev. 2): each replaces one element of M2S72-SL
[Config M2S72-SLN-missing]
description = "(mixin, control) no configured entry (fixed listener MAC kept)"
*.upf.ethBridge.macTable.forwardingTable = []

[Config M2S72-SLN-vlan]
description = "(mixin, control) configured entry on the wrong VLAN (43)"
*.upf.ethBridge.macTable.forwardingTable = [{address: "%(mac)s", vlan: 43, interface: "%(ifc)s"}]

[Config M2S72-SLN-age]
description = "(mixin, control) ageing time too short for the run (1 s): the configured entry (inserted at -1 s) is ignored"
*.upf.ethBridge.macTable.agingTime = 1s

[Config M2S72-SLN-port]
description = "(mixin, control) talker[1] uses the listener's MAC and sends its uplink flows to talker[0]: frames with the listener's source MAC and VID 42 enter on session 1 and move the entry"
*.talker[1].eth[0].address = "%(mac)s"
*.talker[1].app[0..1].io.remoteAddress = "talker[0]"
""" % {"mac": LISTENER_MAC, "vid": SL_VID, "ifc": SL_INTERFACE}
SL_CONTROLS = ("missing", "vlan", "age", "port")


def generate():
    sections, _ = parse(INI)
    src_hash = {p: hashlib.sha256(open(p, "rb").read()).hexdigest()
                for p in (INI, os.path.join(M2, "..", "m1", "omnetpp.ini"))}
    gen_hash = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()
    out = ["# GENERATED by simulations/m2/tools/m2s72_gen.py -- do not edit; regenerate with",
           "#   python3 tools/m2s72_gen.py write     (check: python3 tools/m2s72_gen.py check)",
           "# M2-S7.2a configurations (migration/m2-s7.2a-design.md rev. 2.1): F0 census and T0 equivalence (stages 1-3,",
           "# Checkpoint 1 rev. 2: static listener entry M2S72-SL in every non-T0 config, never in T0).",
           f"# generator sha256 {gen_hash}"]
    out += [f"# source sha256 {h}  {os.path.relpath(os.path.normpath(p), M2)}" for p, h in src_hash.items()]
    out += ["", "include omnetpp.ini", ""]
    summary = []
    for cfg, (short, ns) in SOURCES.items():
        if cfg not in sections:
            raise GenError(f"source config {cfg} not found")
        entries = flatten(sections, cfg)
        tr, eff, used = translate(cfg, ns, entries)
        summary.append((cfg, len(entries), used))
        out += ["#" + "-" * 100,
                f"# Abstract base: {cfg} flattened ({len(entries)} entries in OMNeT++ lookup order: "
                f"{' > '.join(c3(sections, cfg))} > General) and translated for {NETWORK}.",
                f"[Config M2S72B-{short}]",
                f'description = "(abstract, generated) {cfg} on M2S72Bridge"',
                f"network = {NETWORK}"]
        for e, name, lines in tr:
            out.append(f"# [{e.section}] {e.file}:{e.line} rule {name}")
            out += lines
        out.append("")
        for n in ns:
            out += mixin_n(cfg, short, n, eff) + [""]
            if cfg in D4_SOURCES:
                out += mixin_d4(short, n) + [""]
    out += ["#" + "-" * 100, FIXED]
    ext = {}    # generated runnable config -> its extends list (for the inheritance assertions below)
    out += ["#" + "-" * 100, "# T0: numUe = 1 with the source timing (design 8.1); never the static-listener mixin (rev. 2.1 A-1)"]
    for cfg, (short, ns) in SOURCES.items():
        ext[f"M2S72-T0-{short}"] = [f"M2S72N1-{short}", f"M2S72B-{short}"]
        out += [f"[Config M2S72-T0-{short}]", f'description = "T0: {cfg} on M2S72Bridge, numUe = 1"',
                f"extends = {', '.join(ext[f'M2S72-T0-{short}'])}", ""]
    out += ["#" + "-" * 100,
            "# F0 census (design 8.1): D-4 timing, learning recorders; twins -ev (eventlog, F0-7) and -norec (no",
            "# learning recorders: their non-perturbation)"]
    for o, cfg in F0.items():
        short = SOURCES[cfg][0]
        for n in F0_N:
            base = f"M2S72-F0-{o}-n{n}"
            ext[base] = ["M2S72-SL", "M2S72-L", f"M2S72D4N{n}-{short}", f"M2S72N{n}-{short}", f"M2S72B-{short}"]
            ext[base + "-ev"] = ["M2S72-ev", base]
            ext[base + "-norec"] = ["M2S72-SL", f"M2S72D4N{n}-{short}", f"M2S72N{n}-{short}", f"M2S72B-{short}"]
            out += [f"[Config {base}]", f'description = "F0 census: {cfg}, numUe = {n}, D-4 timing, static listener entry"',
                    f"extends = {', '.join(ext[base])}", "",
                    f"[Config {base}-ev]", f'description = "F0-7 twin: {base} with the eventlog over [0, 0.5 s]"',
                    f"extends = {', '.join(ext[base + '-ev'])}", "",
                    f"[Config {base}-norec]", f'description = "F0 twin: {base} without the learning recorders"',
                    f"extends = {', '.join(ext[base + '-norec'])}", ""]
    out += ["#" + "-" * 100,
            "# F0-6 negative controls (Checkpoint 1 rev. 2): the Q-0 N = 2 census with one element of M2S72-SL replaced",
            "# (the control mixin comes first, so it takes precedence); each with its eventlog twin"]
    for c in SL_CONTROLS:
        nm = f"M2S72-F0N-{c}"
        ext[nm] = [f"M2S72-SLN-{c}", "M2S72-F0-q0-n2"]
        ext[nm + "-ev"] = ["M2S72-ev", nm]
        out += [f"[Config {nm}]", f'description = "F0-6 negative control {c}"', f"extends = {', '.join(ext[nm])}", "",
                f"[Config {nm}-ev]", f'description = "eventlog twin of {nm}"', f"extends = {', '.join(ext[nm + '-ev'])}", ""]
    out += ["#" + "-" * 100, "# Stage 4, Block B (design 9): per-slave and cross-slave correctness; N = 2, 4 and the N = 1 I-5 reference;",
            "# every run carries M2S72-SL, the learning recorders and the eventlog (UPF MAC-table log; non-express mode)"]
    out += tt_eall_mixin(sections) + [""]
    for o, (src_i, src_c) in B_OPTS.items():
        for clk in ("ideal", "Ca", "Eall"):
            src = src_i if clk == "ideal" else src_c
            short = SOURCES[src][0]
            for n in B_N:
                nm = f"M2S72-B-{o}-{clk}-n{n}"
                ext[nm] = (["M2S72-TT-Eall"] if clk == "Eall" else []) + ["M2S72-SL", "M2S72-L", "M2S72-ev",
                                                                       f"M2S72D4N{n}-{short}", f"M2S72N{n}-{short}", f"M2S72B-{short}"]
                out += [f"[Config {nm}]", f'description = "Block B: {src}{" + E-all TT clocks" if clk == "Eall" else ""}, numUe = {n}"',
                        f"extends = {', '.join(ext[nm])}", ""]
    # Block B negative control (design 8.3 N-theta1): DS-TT 1 TT-clock offset + 1 us; the checker keeps the D-13 value
    ext["M2S72-BN-theta1"] = ["M2S72-BNX-theta1", "M2S72-B-q0-Eall-n4"]
    out += ["[Config M2S72-BNX-theta1]", 'description = "(mixin, control) DS-TT 1 TT-clock theta0 + 1 us"',
            f"*.dsTt[1].eth[1].trafficConditionerLayer.ttClock.theta0 = {D13['theta0'][0] + D13['theta0'][1] + 1000}ns", "",
            "[Config M2S72-BN-theta1]", 'description = "Block B negative control N-theta1 (q0, E-all, numUe = 4)"',
            f"extends = {', '.join(ext['M2S72-BN-theta1'])}", ""]
    check_inheritance(ext)
    return "\n".join(out).rstrip("\n") + "\n", summary


def tt_eall_mixin(sections):
    """M2S72-TT-Eall: the entries of the sections of M2S6-E-all that M2S6-C-a does not have (M2S6-E-all itself and
    M2S6-tt), in lookup order, translated with the same rules (every entry exactly one rule), the DS-TT TT-clock
    parameters per DS-TT by D-13."""
    own = [sec for sec in c3(sections, EALL_CFG) if sec not in c3(sections, EALL_BASE)]
    entries = [e for sec in own for e in sections[sec]]
    x = Ctx(EALL_CFG, (1, max(B_N)))
    x.per_ds_tt = True
    out = ["[Config M2S72-TT-Eall]",
           f'description = "(mixin, generated) {EALL_CFG} TT clocks (sections {", ".join(own)}); DS-TT k per D-13"']
    for e in entries:
        hits = [(n, f) for n, p, f in RULES if p(e.key)]
        if len(hits) != 1:
            raise GenError(f"{EALL_CFG} TT mixin: {e.key} matches {len(hits)} rules")
        name, f = hits[0]
        lines, _ = f(e, x)
        out.append(f"# [{e.section}] {e.file}:{e.line} rule {name}")
        out += lines
    return out


def closure(ext, name):
    """Every generated section a runnable config inherits from (its own extends, recursively)."""
    seen, todo = [], list(ext.get(name, []))
    while todo:
        x = todo.pop(0)
        if x not in seen:
            seen.append(x)
            todo += ext.get(x, [])
    return seen


def check_inheritance(ext):
    """rev. 2.1 A-1: every non-T0 runnable config inherits M2S72-SL; no T0 config inherits M2S72-SL, an SL
    control, the learning recorders, the eventlog mixin or a D-4 mixin."""
    for name in ext:
        cl = closure(ext, name)
        if name.startswith("M2S72-T0-"):
            bad = [x for x in cl if x in T0_FORBIDDEN or x.startswith("M2S72-SLN-") or x.startswith("M2S72D4")]
            if bad:
                raise GenError(f"{name}: T0 config inherits {bad}")
        elif "M2S72-SL" not in cl:
            raise GenError(f"{name}: non-T0 config does not inherit M2S72-SL")


def runconfig_entries(text):
    lines = text.split("\n")
    try:
        i = next(j for j, l in enumerate(lines) if l.startswith("Run 0:")) + 1
    except StopIteration:
        raise GenError("runconfig output without 'Run 0:'")
    ents = []
    for l in lines[i:]:
        if l.startswith("End.") or (not l.strip() and ents):
            break
        if l.startswith("\t"):
            ents.append(l[1:])
        elif ents:
            ents[-1] += " " + l
    out = []
    for s in ents:
        k, v = s.split("=", 1)
        out.append((k.strip(), " ".join(v.split())))
    return out


def verify_generated(cmd):
    """rev. 2.1 A-1, checked on OMNeT++'s own resolution of the generated file: every M2S72-T0-* config has no
    listener address and no UPF forwardingTable entry; every non-T0 runnable config has exactly the M2S72-SL values
    as its effective (first) entries (the F0-6 controls: their replaced element)."""
    text = open(OUT).read()
    names = re.findall(r"^\[Config (M2S72-(?:T0|F0|F0N|B|BN)-[^\]]+)\]", text, flags=re.M)
    sl = {"*.listener.eth[0].address": f'"{LISTENER_MAC}"',
          "*.upf.ethBridge.macTable.forwardingTable": f'[{{address: "{LISTENER_MAC}", vlan: {SL_VID}, interface: "{SL_INTERFACE}"}}]'}
    ctrl = {"missing": ("*.upf.ethBridge.macTable.forwardingTable", "[]"),
            "vlan": ("*.upf.ethBridge.macTable.forwardingTable", f'[{{address: "{LISTENER_MAC}", vlan: 43, interface: "{SL_INTERFACE}"}}]'),
            "age": ("*.upf.ethBridge.macTable.agingTime", "1s"), "port": ("*.talker[1].eth[0].address", f'"{LISTENER_MAC}"'),
            "port2": ("*.talker[1].app[0..1].io.remoteAddress", '"talker[0]"')}
    bad = 0
    for nm in names:
        res = subprocess.run(cmd + ["-f", "m2s72.ini", "-c", nm, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
        ents = runconfig_entries(res.stdout)
        eff = {}
        for k, v in ents:
            eff.setdefault(k, v)
        keys = [k for k, _ in ents]
        if nm.startswith("M2S72-T0-"):
            found = [k for k in keys if k in sl or "macTable" in k or re.fullmatch(r"\*\.listener\.eth\[.*\]\.address", k)]
            ok = not found
            msg = "no listener address, no MAC-table setting" if ok else f"INHERITS {found}"
        else:
            exp = dict(sl)
            m = re.match(r"M2S72-F0N-([a-z]+)", nm)
            if m:
                for c in (m.group(1), m.group(1) + "2"):
                    if c in ctrl:
                        k, v = ctrl[c]
                        exp[k] = v
            diff = {k: (eff.get(k), v) for k, v in exp.items() if eff.get(k) != v}
            ok = not diff
            msg = "effective static-listener settings as generated" if ok else f"DIFFERENT {diff}"
        bad += not ok
        print(f"{nm}: {msg}")
    return bad


def verify(cmd):
    sections, _ = parse(INI)
    bad = 0
    for cfg in SOURCES:
        mine = [(e.key, " ".join(expand(e.value, cfg).replace("\\", " ").split())) for e in flatten(sections, cfg)]
        res = subprocess.run(cmd + ["-c", cfg, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
        theirs = runconfig_entries(res.stdout)
        theirs = [(k, " ".join(v.replace("\\", " ").split())) for k, v in theirs]
        ok = mine == theirs
        print(f"{cfg}: generator {len(mine)} entries, OMNeT++ runconfig {len(theirs)} entries: "
              f"{'IDENTICAL (keys, values, order)' if ok else 'DIFFERENT'}")
        if not ok:
            bad += 1
            for j, (a, b) in enumerate(zip(mine, theirs)):
                if a != b:
                    print(f"   first difference at entry {j}: generator {a!r} vs runconfig {b!r}")
                    break
    return bad


def main():
    mode = sys.argv[1] if len(sys.argv) > 1 else "check"
    try:
        text, summary = generate()
    except GenError as ex:
        print(f"m2s72_gen: ERROR: {ex}", file=sys.stderr)
        return 2
    for cfg, n, used in summary:
        print(f"{cfg}: {n} entries; rules {dict(sorted(used.items()))}")
    if mode == "write":
        open(OUT, "w").write(text)
        print(f"wrote {OUT} sha256 {hashlib.sha256(text.encode()).hexdigest()}")
        return 0
    if mode == "check":
        cur = open(OUT).read() if os.path.exists(OUT) else None
        same = cur == text
        print(f"regenerated sha256 {hashlib.sha256(text.encode()).hexdigest()}; committed "
              f"{hashlib.sha256(cur.encode()).hexdigest() if cur is not None else 'absent'}: "
              f"{'IDENTICAL' if same else 'DIFFERENT'}")
        return 0 if same else 1
    if mode == "verify":
        b1 = verify(sys.argv[2:] + ["-f", "omnetpp.ini"] if "-f" not in sys.argv[2:] else sys.argv[2:])
        cmd = [x for i, x in enumerate(sys.argv[2:]) if not (x == "-f" or (i > 0 and sys.argv[2:][i - 1] == "-f"))]
        b2 = verify_generated(cmd)
        print(f"generated-config check (rev. 2.1 A-1): {'all as generated' if not b2 else str(b2) + ' DIFFERENT'}")
        return 1 if (b1 or b2) else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
