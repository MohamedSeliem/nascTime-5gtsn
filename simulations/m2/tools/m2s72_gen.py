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
Checkpoint 2 rev. 2 (stage 4 corrective round, path heterogeneity): for the sources in LOAD_UE the S7.1 load
application app[3] is translated for N > 1 onto ONE UE L only (asymmetric load): talker[L] gets the talker side
(numApps 4, app[3]: UL load to the listener), the listener gets the DL side as its last app
(3 + 2(N - 1), remote talker[L]); every other talker keeps numApps 3. The DL load starts by D-4 at 0.3 s
(+ 500 us, the S7.1 offset relative to the base flows).
Stage 5 (E0 authorisation, review 2026-11-03 11:35): load-capable variants "<src>@L" of the sustained-load sources
(LOAD_VAR). Their base carries NO load: every app[3] entry is recorded (LOAD_REC) and the talker / listener numApps
are 3. The load is placed by generated load mixins M2S72LD-<short>-<placement>-n<N>-f<F>[-u<U>] (load_mixin):
placement one0 = L_tot on UE 0; sym = L_tot divided equally over the N UEs. Loaded UE k gets talker[k].app[3] (UL to
the listener, interval 0.25 ms * n_loaded / U, the source's UL offset) and the j-th loaded UE the listener app
3 + 2(N - 1) + j (DL to talker[k], interval 0.25 ms * n_loaded / F, D-4 start 0.3 s + 500 us). Every other app[3]
setting is the source's effective value; anything else fails closed (LOAD_REQ, exact-ns intervals, no foreign base
setting reaching a load app). M2S72-MACLOG: observation-only gNB MAC / RLC log capture (stdout, module-path prefix).
"""
import hashlib
import os
from fractions import Fraction
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
    # Checkpoint 2 rev. 2 (path heterogeneity): the S7.1 sustained-load accuracy configs, load on one UE only
    "M2S71-q0-Ca-sus": ("q0-Ca-sus", (2, 4)),
    "M2S71-qdu-Ca-sus": ("qdu-Ca-sus", (2, 4)),
    # Stage 5: load-capable variants (no load in the base; load mixins place it), N = 1, 2, 4, 8
    "M2S71-q0-Ca-sus@L": ("q0-Ca-L", (1, 2, 4, 8)),
    "M2S71-qdu-Ca-sus@L": ("qdu-Ca-L", (1, 2, 4, 8)),
}
LOAD_VAR = {"M2S71-q0-Ca-sus@L": "M2S71-q0-Ca-sus", "M2S71-qdu-Ca-sus@L": "M2S71-qdu-Ca-sus"}   # variant -> source config
# effective app[3] settings every load-variant source must have (fail closed: the load mixins scale these values)
LOAD_REQ = {"**.app[3].typename": '"EthernetSourceApp"', "**.app[3].source.packetLength": "1400B",
            "**.app[3].source.productionInterval": "0.25ms", "**.app[3].source.initialProductionOffset": "0.1s + 500us",
            "**.app[3].tagger.vlanId": "42", "**.app[3].tagger.pcp": "0",
            "*.talker.app[3].io.remoteAddress": '"listener"', "*.listener.app[3].io.remoteAddress": '"talker"'}
LOAD_BASE_NS = 250000      # L_tot interval per direction (0.25 ms), one 1400 B frame
LOAD_REC = {}              # variant -> [(side, rest, value)] of every app[3] entry, lookup order (side: both | talker | listener)
APPSEL_RESTS = {}          # variant -> {c: {rest}} of the base-flow entries **.app[c] (replicated to listener apps 3 + 2(k-1) + c)
PLACEMENTS = ("one0", "sym")
E0_FACTORS = (1, 2, 4, 8)  # E0: DL load factor on UE 0 at N = 1 (UL stays 1 x L_tot)
E0_TWIN = "q0"             # MAC-log non-perturbation twins M2S72-E0NL-q0-f<F> (same config without M2S72-MACLOG); the runner
                           # runs the one of the highest Q-0 factor executed
LOAD_UE = {"M2S71-q0-Ca-sus": 1, "M2S71-qdu-Ca-sus": 1}   # source -> the one UE carrying the load (N > 1)
LOAD_D4 = "0.3s + 500us"   # D-4 start of the DL load (S7.1: base + 500 us)
LOAD_LINES = {}            # source -> [(rest, value)] of the listener side of app[3], in lookup order
D4_SOURCES = ("M2S71-q0-idle", "M2S71-qdu-idle", "M2S71-q0-Ca", "M2S71-qdu-Ca", "M2S71-q0-Ca-sus", "M2S71-qdu-Ca-sus",
              "M2S71-q0-Ca-sus@L", "M2S71-qdu-Ca-sus@L")   # sources of non-T0 configs (D-4 timing)
# Block B (design 9): option -> (ideal-clock source, C-a source); clocks ideal / Ca / Eall (Eall = C-a source + the
# generated TT-clock mixin M2S72-TT-Eall); N = 2, 4 (correctness) and 1 (I-5 reference); seeds 0-4
B_OPTS = {"q0": ("M2S71-q0-idle", "M2S71-q0-Ca"), "qdu": ("M2S71-qdu-idle", "M2S71-qdu-Ca")}
B_N = (1, 2, 4)
B_REPS = "0..4"
H_N = (2, 4)               # Block H (Checkpoint 2 rev. 2)
# I-2H focused validation (review 2026-11-02 16:12): the existing M2S0-harq16 mixin as an EXPERIMENTAL CONTROL
# (removes the MAC PDU deletion of P1; not an operational recommendation), its own entries translated by RULES
HARQ16_SECTION = "M2S0-harq16"
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
        self.load_ue = LOAD_UE.get(cfg)
        self.load_var = cfg in LOAD_VAR


def src_of(cfg):
    """the source config of a SOURCES key (a load-capable variant "<src>@L" is its source)"""
    return LOAD_VAR.get(cfg, cfg)


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
    if getattr(x, "load_var", False):
        for c in sel:
            APPSEL_RESTS.setdefault(x.cfg, {}).setdefault(c, set()).add(rest)
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


def load_app(n):
    return LISTENER_APPS + 2 * (n - 1)


def r_app3(e, x):
    if getattr(x, "load_var", False):
        return r_app3_var(e, x)
    if x.ngt1 and getattr(x, "load_ue", None) is not None:
        return r_app3_asym(e, x)
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


def r_app3_asym(e, x):
    """Asymmetric load (LOAD_UE): talker side on talker[L] only; listener side recorded for the N mixins."""
    L, v = x.load_ue, e.value
    rest = re.fullmatch(r"(?:\*\*|\*\.talker|\*\.listener)\.app\[3\]\.(.+)", e.key).group(1)
    lines = LOAD_LINES.setdefault(x.cfg, [])
    if e.key == "*.listener.app[3].io.remoteAddress":
        if v != '"talker"':
            raise GenError(f"{x.cfg}: unexpected {e.key} = {v}")
        lines.append((rest, f'"talker[{L}]"'))
        return [f"# {e.key} = {v}  (listener side: app[3 + 2(N - 1)] -> talker[{L}], in M2S72N<N>-<src>)"], "LOAD"
    if e.key == "*.talker.app[3].io.remoteAddress":
        if v != '"listener"':
            raise GenError(f"{x.cfg}: unexpected {e.key} = {v}")
        return [f"*.talker[{L}].app[3].{rest} = {v}"], "LOAD"
    if PER_UE_VALUE.search(v) or "ancestorIndex" in v:
        raise GenError(f"{x.cfg}: untranslatable value {e.key} = {v}")
    if e.key.startswith("*.listener."):
        lines.append((rest, v))
        return [f"# {e.key} = {v}  (listener side, in M2S72N<N>-<src>)"], "LOAD"
    if e.key.startswith("*.talker."):
        return [f"*.talker[{L}].app[3].{rest} = {v}"], "LOAD"
    lines.append((rest, v))
    return [f"*.talker[{L}].app[3].{rest} = {v}"], "LOAD"


def r_app3_var(e, x):
    """Load-capable variant (LOAD_VAR): the base carries no load; the entry is recorded for the load mixins."""
    m = re.fullmatch(r"(\*\*|\*\.talker|\*\.listener)\.app\[3\]\.(.+)", e.key)
    side = {"**": "both", "*.talker": "talker", "*.listener": "listener"}[m.group(1)]
    rest, v = m.group(2), e.value
    if rest == "io.remoteAddress":
        if (side, v) not in (("talker", '"listener"'), ("listener", '"talker"')):
            raise GenError(f"{x.cfg}: unexpected {e.key} = {v}")
    elif PER_UE_VALUE.search(v) or "ancestorIndex" in v:
        raise GenError(f"{x.cfg}: untranslatable value {e.key} = {v}")
    LOAD_REC.setdefault(x.cfg, []).append((side, rest, v))
    return [f"# {e.key} = {v}  (load app: placed by the load mixins M2S72LD-*)"], "LOAD"


def r_lnumapps(e, x):
    if getattr(x, "load_var", False) and e.value == "4":
        return [f"# {e.key} = 4  (load-capable base: no load app; the load mixins set numApps)",
                f"*.listener.numApps = {LISTENER_APPS}"], "LOAD"
    return r_keep(e, x)


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
    # the effective entry (REQUIRED: 4) gives the load UE app[3]; later (overridden) entries translate generically
    if e.key == "*.talker.numApps" and x.ngt1 and getattr(x, "load_ue", None) is not None and e.value == "4":
        return [f"*.talker[{x.load_ue}].numApps = 4", f"*.talker[*].numApps = {LISTENER_APPS}"], "LOAD"
    if e.key == "*.talker.numApps" and getattr(x, "load_var", False) and e.value == "4":
        return [f"# {e.key} = 4  (load-capable base: no load app; the load mixins set numApps)",
                f"*.talker[*].numApps = {LISTENER_APPS}"], "LOAD"
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
    ("listenerNumApps", lambda k: k == "*.listener.numApps", r_lnumapps),
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
        if x.load_ue is not None or x.load_var:   # the load sources: app[3] on both stations
            req.update({"*.listener.numApps": "4", "*.talker.numApps": "4"})
            LOAD_LINES[cfg] = []
    if x.load_var:
        req.update({"*.listener.numApps": "4", "*.talker.numApps": "4"})
        req.update(LOAD_REQ)
        LOAD_REC[cfg] = []
        APPSEL_RESTS[cfg] = {}
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
    if n > 1 and cfg in LOAD_UE:
        s[1] = s[1][:-1] + f', DL load app[{load_app(n)}] -> talker[{LOAD_UE[cfg]}]"'
        s.append(f"*.listener.numApps = {load_app(n) + 1}")
        s += [f"*.listener.app[{load_app(n)}].{rest} = {v}" for rest, v in LOAD_LINES[cfg]]
    elif n > 1:
        s.append(f"*.listener.numApps = {LISTENER_APPS + 2 * (n - 1)}")
    for key in ("*.bearerConfigurator.staticDrbs", "*.bearerConfigurator.ulQfiRules"):
        e = eff[key]
        s.append(per_ue_list(key, e.value, n, "\n" in e.raw))
    return s


def mixin_d4(short, n, cfg=None):
    s = [f"[Config M2S72D4N{n}-{short}]",
         f'description = "(mixin, generated) D-4 (provisional): every DL flow to talker[k] starts at {D4_OFFSET} '
         f'(PCP 0 flow + 5 ms), numUe = {n}"',
         f"*.listener.app[0..1].source.initialProductionOffset = {D4_OFFSET} + 5ms * ancestorIndex(1)"]
    s += [f"*.listener.app[{listener_app(k, c)}].source.initialProductionOffset = {D4_OFFSET} + {5 * c}ms"
          for k in range(1, n) for c in (0, 1)]
    if cfg in LOAD_UE and n > 1:
        s.append(f"*.listener.app[{load_app(n)}].source.initialProductionOffset = {LOAD_D4}")
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
        src = src_of(cfg)
        if src not in sections:
            raise GenError(f"source config {src} not found")
        entries = flatten(sections, src)
        tr, eff, used = translate(cfg, ns, entries)
        summary.append((cfg, len(entries), used))
        var = (" as a load-capable variant (Stage 5: no load in the base; placed by the load mixins M2S72LD-*)"
               if cfg in LOAD_VAR else "")
        out += ["#" + "-" * 100,
                f"# Abstract base: {src} flattened ({len(entries)} entries in OMNeT++ lookup order: "
                f"{' > '.join(c3(sections, src))} > General) and translated for {NETWORK}{var}.",
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
                out += mixin_d4(short, n, cfg) + [""]
    out += ["#" + "-" * 100, FIXED]
    ext = {}    # generated runnable config -> its extends list (for the inheritance assertions below)
    out += ["#" + "-" * 100, "# T0: numUe = 1 with the source timing (design 8.1); never the static-listener mixin (rev. 2.1 A-1)"]
    for cfg, (short, ns) in SOURCES.items():
        if 1 not in ns or cfg in LOAD_VAR:   # T0 compares numUe = 1 with the source (not a load-capable variant)
            continue
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
    # Checkpoint 2 rev. 2: Block H (path heterogeneity): C-a clocks, S7.1 sustained load on UE 1 only, N = 2, 4
    out += ["#" + "-" * 100, "# Checkpoint 2 rev. 2, Block H (path heterogeneity): M2S71-<opt>-Ca-sus with the load on UE 1 only;",
            "# D-4 timing, M2S72-SL, learning recorders, eventlog"]
    for o in B_OPTS:
        src = f"M2S71-{o}-Ca-sus"
        short = SOURCES[src][0]
        for n in H_N:
            nm = f"M2S72-H-{o}-Ca-n{n}"
            ext[nm] = ["M2S72-SL", "M2S72-L", "M2S72-ev", f"M2S72D4N{n}-{short}", f"M2S72N{n}-{short}", f"M2S72B-{short}"]
            out += [f"[Config {nm}]", f'description = "Block H: {src}, load on UE {LOAD_UE[src]} only, numUe = {n}"',
                    f"extends = {', '.join(ext[nm])}", ""]
    # Checkpoint 2 rev. 2 control (I-4 own stream): DS-TT 2's TT clock draws from DS-TT 1's RNG 3 (shared stream)
    ext["M2S72-BN-rng"] = ["M2S72-BNX-rng", "M2S72-B-q0-Eall-n4"]
    out += ["[Config M2S72-BNX-rng]", 'description = "(mixin, control) DS-TT 2 TT clock on RNG 3, the stream of DS-TT 1 (shared stream)"',
            "*.dsTt[2].eth[1].trafficConditionerLayer.ttClock.rng-0 = 3", "",
            "[Config M2S72-BN-rng]", 'description = "I-4 own-stream negative control (q0, E-all, numUe = 4)"',
            f"extends = {', '.join(ext['M2S72-BN-rng'])}", ""]
    # I-2H focused validation (review 2026-11-02 16:12): Block H with HARQ16 (experimental control); Q-0 = correctness
    # configuration, Q-d (UM) = diagnostic comparison; I-2H negative controls on M2S72-H16-q0-Ca-n2
    out += ["#" + "-" * 100, "# I-2H focused validation: Block H + M2S72-HARQ16 (EXPERIMENTAL CONTROL: 16 HARQ processes, the existing",
            "# M2S0-harq16 mixin; not an operational recommendation); Q-0 correctness configuration, Q-d (UM) diagnostic"]
    out += section_mixin(sections, HARQ16_SECTION, "M2S72-HARQ16",
                         "(mixin, generated, EXPERIMENTAL CONTROL) M2S0-harq16: 16 HARQ processes at the gNB and every UE") + [""]
    for o in B_OPTS:
        src = f"M2S71-{o}-Ca-sus"
        short = SOURCES[src][0]
        for n in H_N:
            nm = f"M2S72-H16-{o}-Ca-n{n}"
            ext[nm] = ["M2S72-HARQ16", "M2S72-SL", "M2S72-L", "M2S72-ev", f"M2S72D4N{n}-{short}", f"M2S72N{n}-{short}", f"M2S72B-{short}"]
            out += [f"[Config {nm}]", f'description = "Block H + HARQ16 (experimental control): {src}, load on UE {LOAD_UE[src]} only, numUe = {n}"',
                    f"extends = {', '.join(ext[nm])}", ""]
    for c, line, desc in (("nohold", '*.dsTt[1].eth[1].trafficConditionerLayer.syncOut.egressTest = "noHold"', "DS-TT 1 hold disabled (TEST ONLY knob)"),
                          ("hto", "*.dsTt[1].eth[1].trafficConditionerLayer.syncOut.holdTimeout = 5us", "DS-TT 1 holdTimeout 5 us, below the 10.864 us Sync queue wait")):
        ext[f"M2S72-H16N-{c}"] = [f"M2S72-H16NX-{c}", "M2S72-H16-q0-Ca-n2"]
        out += [f"[Config M2S72-H16NX-{c}]", f'description = "(mixin, I-2H control) {desc}"', line, "",
                f"[Config M2S72-H16N-{c}]", f'description = "I-2H negative control: {desc}; M2S72-H16-q0-Ca-n2"',
                f"extends = {', '.join(ext[f'M2S72-H16N-{c}'])}", ""]
    out += e0_section(ext)
    check_inheritance(ext)
    return "\n".join(out).rstrip("\n") + "\n", summary


# ---------------------------------------------------------------- Stage 5: load placement, MAC log, E0 ------------
MACLOG = """\
[Config M2S72-MACLOG]
description = "(mixin, Stage 5, OBSERVATION ONLY) gNB MAC and RLC UM TX log lines and UE RLC UM RX log lines on stdout, prefix simulation time | context module path (non-express mode; non-perturbation proven per batch)"
*.gnb1.cellularNic.mac.cmdenv-log-level = info
*.gnb1.cellularNic.rlc-um-*.tx.cmdenv-log-level = info
*.ue[*].cellularNic.nrRlc-um-*.rx.cmdenv-log-level = info
cmdenv-log-prefix = "%t|%M|"
"""


def flabel(f):
    f = Fraction(str(f))
    if f <= 0:
        raise GenError(f"load factor {f} must be > 0")
    s = str(float(f)).rstrip("0").rstrip(".") if f.denominator != 1 else str(f.numerator)
    return s.replace(".", "p")


def load_interval(n_loaded, f):
    """0.25 ms * n_loaded / f as an exact ini quantity (integer ns; fail closed otherwise)"""
    v = Fraction(LOAD_BASE_NS * n_loaded) / Fraction(str(f))
    if v.denominator != 1:
        raise GenError(f"load interval 0.25 ms * {n_loaded} / {f} is not an integer number of ns")
    v = int(v)
    return f"{v // 1000}us" if v % 1000 == 0 else f"{v}ns"


def loaded_ues(placement, n):
    if placement not in PLACEMENTS:
        raise GenError(f"unknown load placement {placement!r} (known: {PLACEMENTS})")
    if not 1 <= n <= NMAX:
        raise GenError(f"numUe {n} outside 1..{NMAX}")
    if placement == "sym" and n == 1:
        raise GenError("placement sym at numUe = 1 is placement one0 (one name per configuration)")
    return [0] if placement == "one0" else list(range(n))


def load_name(short, placement, n, fdl, ful=1):
    return f"M2S72LD-{short}-{placement}-n{n}-f{flabel(fdl)}" + ("" if Fraction(str(ful)) == 1 else f"-u{flabel(ful)}")


def load_effective(cfg):
    """per side (talker, listener): {rest: value}, the first app[3] entry of that side or of both (lookup order)"""
    if cfg not in LOAD_VAR or cfg not in LOAD_REC:
        raise GenError(f"{cfg}: not a translated load-capable variant")
    eff = {"talker": {}, "listener": {}}
    for side, rest, v in LOAD_REC[cfg]:
        for sd in (("talker", "listener") if side == "both" else (side,)):
            eff[sd].setdefault(rest, v)
    for sd, d in eff.items():
        for need in ("typename", "source.productionInterval", "source.initialProductionOffset", "io.remoteAddress"):
            if need not in d:
                raise GenError(f"{cfg}: load app ({sd} side) without {need}")
        if d["source.productionInterval"] != "0.25ms":
            raise GenError(f"{cfg}: load app ({sd} side) productionInterval {d['source.productionInterval']}, expected 0.25ms")
    return eff


def load_spec(cfg, placement, n, fdl, ful=1):
    """expected effective values {(module, rest): value} of the load placement (also the verify_load reference)"""
    if n not in SOURCES[cfg][1]:
        raise GenError(f"{cfg}: numUe {n} not generated (N values {SOURCES[cfg][1]})")
    for f in (fdl, ful):
        if Fraction(str(f)) <= 0:
            raise GenError(f"load factor {f} must be > 0")
    ues = loaded_ues(placement, n)
    eff = load_effective(cfg)
    dl, ul = load_interval(len(ues), fdl), load_interval(len(ues), ful)
    spec = {}
    for k in ues:
        spec[(f"talker[{k}]", "numApps")] = "4"
        for rest, v in eff["talker"].items():
            spec[(f"talker[{k}].app[3]", rest)] = ul if rest == "source.productionInterval" else v
    for k in range(n):
        if k not in ues:
            spec[(f"talker[{k}]", "numApps")] = str(LISTENER_APPS)
    spec[("listener", "numApps")] = str(LISTENER_APPS + 2 * (n - 1) + len(ues))
    for j, k in enumerate(ues):
        la = LISTENER_APPS + 2 * (n - 1) + j
        for rest, v in eff["listener"].items():
            if rest == "source.productionInterval":
                v = dl
            elif rest == "source.initialProductionOffset":
                v = LOAD_D4
            elif rest == "io.remoteAddress":
                v = f'"talker[{k}]"'
            spec[(f"listener.app[{la}]", rest)] = v
        # a base-flow setting replicated to this listener app index (apps 3 + 2(k' - 1) + c) that the load does not set
        for kk in range(1, NMAX):
            for c in (0, 1):
                if listener_app(kk, c) == la:
                    foreign = APPSEL_RESTS.get(cfg, {}).get(c, set()) - set(eff["listener"])
                    if foreign:
                        raise GenError(f"{cfg}: base-flow settings {sorted(foreign)} of app[{c}] reach load app listener.app[{la}]")
    return spec, ues, dl, ul


def load_mixin(cfg, placement, n, fdl, ful=1):
    short = SOURCES[cfg][0]
    spec, ues, dl, ul = load_spec(cfg, placement, n, fdl, ful)
    nm = load_name(short, placement, n, fdl, ful)
    s = [f"[Config {nm}]",
         f'description = "(mixin, generated) S7.1 sustained load L_tot, placement {placement}, numUe = {n}: loaded UEs {ues}; '
         f'DL factor {flabel(fdl).replace("p", ".")} (per UE every {dl}), UL factor {flabel(ful).replace("p", ".")} (per UE every {ul})"']
    s += [f"*.{mod}.{rest} = {v}" for (mod, rest), v in spec.items() if rest == "numApps"]
    s += [f"*.{mod}.{rest} = {v}" for (mod, rest), v in spec.items() if rest != "numApps"]
    return nm, s


def e0_section(ext):
    out = ["#" + "-" * 100,
           "# Stage 5 E0 capacity calibration (authorisation 2026-11-03 11:35): N = 1, S7.1 sustained load on UE 0 with DL factor",
           "# 1, 2, 4, 8 (UL 1 x L_tot), Q-0 and Q-d (UM), HARQ16 (EXPERIMENTAL CONTROL), C-a, M2S72-SL, learning recorders, eventlog,",
           "# MAC log (M2S72-MACLOG; the E0NL twin is the same config without it: non-perturbation)", MACLOG]
    for o in B_OPTS:
        cfg = f"M2S71-{o}-Ca-sus@L"
        short = SOURCES[cfg][0]
        for f in E0_FACTORS:
            ld, lines = load_mixin(cfg, "one0", 1, f)
            out += lines + [""]
            nm = f"M2S72-E0-{o}-f{flabel(f)}"
            ext[nm] = ["M2S72-MACLOG", ld, "M2S72-HARQ16", "M2S72-SL", "M2S72-L", "M2S72-ev", f"M2S72D4N1-{short}",
                       f"M2S72N1-{short}", f"M2S72B-{short}"]
            out += [f"[Config {nm}]", f'description = "E0: {src_of(cfg)}, load on UE 0, DL factor {f}, numUe = 1, HARQ16 (experimental control), MAC log"',
                    f"extends = {', '.join(ext[nm])}", ""]
            if o == E0_TWIN:
                tw = f"M2S72-E0NL-{o}-f{flabel(f)}"
                ext[tw] = ext[nm][1:]
                out += [f"[Config {tw}]", f'description = "E0 MAC-log non-perturbation twin: {nm} without M2S72-MACLOG"',
                        f"extends = {', '.join(ext[tw])}", ""]
    return out


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


def section_mixin(sections, sec, name, desc):
    """[Config <name>]: the OWN entries of one source section (not its extends chain), each translated by exactly one
    rule of RULES (as M2S72-TT-Eall)."""
    x = Ctx(sec, (1, max(H_N)))
    out = [f"[Config {name}]", f'description = "{desc}"']
    for e in sections[sec]:
        hits = [(n, f) for n, p, f in RULES if p(e.key)]
        if len(hits) != 1:
            raise GenError(f"{sec} mixin: {e.key} matches {len(hits)} rules")
        rn, f = hits[0]
        lines, _ = f(e, x)
        out.append(f"# [{e.section}] {e.file}:{e.line} rule {rn}")
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
    names = re.findall(r"^\[Config (M2S72-(?:T0|F0|F0N|B|BN|H|H16|H16N|E0|E0NL)-[^\]]+)\]", text, flags=re.M)
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


def pat_re(p):
    """OMNeT++ ini key pattern -> regex over full parameter paths (** any, * no dot, ? one char, [a..b] / [*] index)"""
    out, i = "", 0
    while i < len(p):
        if p.startswith("**", i):
            out, i = out + ".*", i + 2
        elif p[i] == "*":
            out, i = out + "[^.]*", i + 1
        elif p[i] == "?":
            out, i = out + "[^.]", i + 1
        elif p[i] == "[":
            j = p.index("]", i)
            inner = p[i + 1:j]
            if inner == "*":
                out += r"\[\d+\]"
            elif ".." in inner:
                a, b = inner.split("..")
                out += r"\[(?:" + "|".join(str(v) for v in range(int(a or 0), int(b or 999) + 1)) + r")\]"
            else:
                out += re.escape(p[i:j + 1])
            i = j + 1
        elif p[i] == "{":
            raise GenError(f"pattern {p!r}: {{...}} ranges are not supported by this checker (fail closed)")
        else:
            out, i = out + re.escape(p[i]), i + 1
    return re.compile(out + r"\Z")


def first_match(ents, path):
    full = NETWORK.rsplit(".", 1)[1] + "." + path
    for k, v in ents:
        if "." in k and pat_re(k).match(full):
            return k, v
    return None, None


E0_EXPECT = {"gnb1.cellularNic.mac.harqProcesses": "16", "ue[0].cellularNic.nrMac.harqProcesses": "16",
             "listener.eth[0].address": f'"{LISTENER_MAC}"', "numUe": "1"}
MACLOG_KEYS = ("*.gnb1.cellularNic.mac.cmdenv-log-level", "*.gnb1.cellularNic.rlc-um-*.tx.cmdenv-log-level",
               "*.ue[*].cellularNic.nrRlc-um-*.rx.cmdenv-log-level", "cmdenv-log-prefix")


def verify_load_entries(nm, ents, cfg, placement, n, fdl, ful=1, maclog=True):
    """exact configuration check of one generated load config on OMNeT++'s own resolution (opp_run -q runconfig):
    every expected load value is the first match of its parameter path; no app setting outside the load set
    reaches a load app; HARQ16, the static listener MAC and numUe as generated; M2S72-MACLOG present iff maclog."""
    spec, ues, dl, ul = load_spec(cfg, placement, n, fdl, ful)
    probs = []
    for (mod, rest), v in spec.items():
        k, got = first_match(ents, f"{mod}.{rest}")
        if got != v:
            probs.append(f"{mod}.{rest}: effective {got!r} (from {k!r}), expected {v!r}")
    mods = {}
    for (mod, rest) in spec:
        m = re.fullmatch(r"(.+)\.app\[(\d+)\]", mod)
        if m:
            mods.setdefault((m.group(1), int(m.group(2))), set()).add(rest)
    net = NETWORK.rsplit(".", 1)[1]
    for k, v in ents:
        j = k.find(".app[")
        if j < 0:
            continue
        e = k.index("]", j)
        prefix, idx, suffix = k[:j], k[j + 5:e], k[e + 2:]
        for (owner, a), rests in mods.items():
            if pat_re(prefix).match(f"{net}.{owner}") and pat_re(f"x[{idx}]").match(f"x[{a}]") and suffix not in rests:
                probs.append(f"foreign setting {k} = {v} reaches load app {owner}.app[{a}]")
    for path, v in E0_EXPECT.items():
        if n != 1 and path == "numUe":
            continue
        k, got = first_match(ents, path)
        if got != v:
            probs.append(f"{path}: effective {got!r}, expected {v!r}")
    keys = {k for k, _ in ents}
    has = [x for x in MACLOG_KEYS if x in keys]
    if maclog and len(has) != len(MACLOG_KEYS):
        probs.append(f"M2S72-MACLOG incomplete: {has}")
    if not maclog and has:
        probs.append(f"M2S72-MACLOG present in a no-log twin: {has}")
    print(f"{nm}: {'exact load configuration (' + str(len(spec)) + ' values), ' + ('MAC log' if maclog else 'no MAC log') if not probs else 'DIFFERENT ' + str(probs[:6])}")
    return not probs


def verify_load(cmd):
    bad = 0
    got = {}
    for o in B_OPTS:
        cfg = f"M2S71-{o}-Ca-sus@L"
        for f in E0_FACTORS:
            names = [(f"M2S72-E0-{o}-f{flabel(f)}", True)]
            if o == E0_TWIN:
                names.append((f"M2S72-E0NL-{o}-f{flabel(f)}", False))
            for nm, ml in names:
                res = subprocess.run(cmd + ["-f", "m2s72.ini", "-c", nm, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
                ents = runconfig_entries(res.stdout)
                got[nm] = ents
                bad += not verify_load_entries(nm, ents, cfg, "one0", 1, f, 1, ml)
    o = E0_TWIN
    meta = ("description", "extends")
    for f in E0_FACTORS:
        na, nb = f"M2S72-E0-{o}-f{flabel(f)}", f"M2S72-E0NL-{o}-f{flabel(f)}"
        a = [(k, v.replace(na, "<config>")) for k, v in got[na] if k not in meta]     # ${configname} in result paths
        b = [(k, v.replace(nb, "<config>")) for k, v in got[nb] if k not in meta]
        extra = [x for x in a if x not in b]
        ok = [x for x in a if x[0] not in MACLOG_KEYS] == b and sorted(k for k, _ in extra) == sorted(MACLOG_KEYS)
        print(f"E0 twin {nb}: effective configuration = {na} without exactly the M2S72-MACLOG entries: {'yes' if ok else 'NO ' + str(extra[:6])}")
        bad += not ok
    return bad


PLACEMENT_MATRIX = [("one0", n, f, 1) for n in (1, 2, 4, 8) for f in (0.5, 1, 2, 4, 8)] + \
                   [("sym", n, f, 1) for n in (2, 4, 8) for f in (0.5, 1, 2, 4, 8)] + [("sym", 4, 2, 2), ("one0", 4, 2, 0.5)]


def verify_placements(cmd):
    """the load mixins of placements one0 / sym at every generated N and factor (not runnable configs of m2s72.ini;
    E1 / E2 need their own authorisation): each is written with a test config into a temporary ini that includes
    m2s72.ini and checked exactly on OMNeT++'s resolution (verify_load_entries)"""
    import tempfile
    bad = 0
    tmp = tempfile.mkdtemp(prefix="m2s72place-")
    try:
        for o in B_OPTS:
            cfg = f"M2S71-{o}-Ca-sus@L"
            short = SOURCES[cfg][0]
            for pl, n, f, u in PLACEMENT_MATRIX:
                ld, lines = load_mixin(cfg, pl, n, f, u)
                nm = "X" + ld
                text = "\n".join([f"include {OUT}", ""] + lines + ["", f"[Config {nm}]",
                                  f"extends = {ld}, M2S72-HARQ16, M2S72-SL, M2S72D4N{n}-{short}, M2S72N{n}-{short}, M2S72B-{short}", ""])
                path = os.path.join(tmp, "place.ini")
                open(path, "w").write(text)
                res = subprocess.run(cmd + ["-f", path, "-c", nm, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
                try:
                    ents = runconfig_entries(res.stdout)
                    ok = verify_load_entries(nm, ents, cfg, pl, n, f, u, maclog=False)
                except GenError as ex:
                    print(f"{nm}: ERROR {ex} {res.stderr[-300:]}")
                    ok = False
                bad += not ok
    finally:
        import shutil
        shutil.rmtree(tmp)
    return bad


def verify(cmd):
    sections, _ = parse(INI)
    bad = 0
    for cfg in SOURCES:
        if cfg in LOAD_VAR:       # the same source config as its plain entry
            continue
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
        b3 = verify_load(cmd)
        print(f"Stage 5 load-configuration check (exact): {'all as generated' if not b3 else str(b3) + ' DIFFERENT'}")
        b4 = verify_placements(cmd)
        print(f"Stage 5 placement check (one0 / sym mixins, {2 * len(PLACEMENT_MATRIX)} test configs, exact): "
              f"{'all as generated' if not b4 else str(b4) + ' DIFFERENT'}")
        return 1 if (b1 or b2 or b3 or b4) else 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main())
