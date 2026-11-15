#!/usr/bin/env python3
"""M2-S7.2a Stage 5, increment S5-2: static RNG-stream audit of generated configurations (RD-3; addendum
results/M2-S7.2a-s5-2-addendum.md §2). No simulation: it reads OMNeT++'s own resolution of a configuration
(`opp_run -q runconfig`, effective entries) and computes, for every random-drawing module of M2S72Bridge, the
physical RNG and seed it uses, then checks the invariants below. The draw ACTIVITY (which modules really draw, how
often) is not static: it is the empirical part of the audit (addendum §2.5, TtSyncMonitorRngProbe), not run here.

OMNeT++ semantics implemented (6.5.0 sources, src/sim/crngmanager.cc, src/sim/cmersennetwister.cc,
src/common/patternmatcher.cc): a component's local RNG k maps to the physical RNG of the FIRST entry
`<pattern>.rng-k` whose pattern matches its full path (dotted-path, full-string, case-sensitive matching), else to
physical RNG k; physical RNG j is seeded with `seed-j-mt` if given, else with seed-set x num-rngs + j (so an
unseeded RNG's stream changes with num-rngs, i.e. with N). Simu5G's direct callers of getEnvir()->getRNG(0) (the
MAXCI tie-break LteScheduler.h:43, the QoS-PF / PF score jitter, the BLER-table constructor PhyPisaData.cc) bypass
every mapping and always use physical RNG 0.

    m2s72_rngaudit.py audit <ini> <cfg> [<cfg> ...] -- <opp_run command...>     per configuration: map + RA-1..RA-3
    m2s72_rngaudit.py pair  <ini> <cfgA> <cfgB> -- <opp_run command...>         RA-4: streams of the UEs of A in B
    m2s72_rngaudit.py isolation-mixin <N>                                       the proposed isolation entries (text)

Invariants (rows; FAIL / INFO are findings, not run verdicts: no run is evaluated here)
  RA-1  every physical RNG with a consumer has an explicit seed, and no two physical RNGs share a seed value
  RA-2  every clock module (oscillator, TT clock) uses a physical RNG with no non-clock consumer
  RA-3  INFO: physical RNGs shared by modules of two or more UEs (draw interleaving across UEs), and the
        consumers of physical RNG 0 (including the direct callers)
  RA-4  (pair A -> B, N_A < N_B) for every drawing module of UE k < N_A: same physical RNG, same seed, and no
        drawing module in B that A does not have on that RNG (INVARIANT); else its random realisation can change
        when UEs are added, whether or not they contend for the radio (COUPLED). Modules serving every UE (gNB MAC /
        PHY / channel model, scheduler tie-break) are MULTI-UE: their draw count depends on N by construction and
        no mapping can isolate them; constant-parameter sources are NO DRAWS (checked on their effective values)
"""
import os
import re
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
NET = "M2S72Bridge"
DIRECT = "(direct getRNG(0))"


# ------------------------------------------------------------------------------- OMNeT++ pattern matcher (port) ---
def _numrange(s, i, closing):
    """parseNumRange: s[i] is '[' or '{'; returns (lo, hi, index of the closing char) or None"""
    j = i + 1
    lo = hi = -1
    m = re.match(r"\d+", s[j:])
    if m:
        lo = int(m.group())
        j += len(m.group())
    if s[j:j + 2] != "..":
        return None
    j += 2
    m = re.match(r"\d+", s[j:])
    if m:
        hi = int(m.group())
        j += len(m.group())
    if j >= len(s) or s[j] != closing:
        return None
    return lo, hi, j


def tokenize(pat):
    """PatternMatcher::setPattern(pat, dottedpath=true, fullstring=true, casesensitive=true)"""
    toks = []
    i = 0
    while i < len(pat):
        c = pat[i]
        if c == "?":
            toks.append(("NONDOTCHAR",))
            i += 1
        elif c == "[" and toks and toks[-1][0] == "LIT" and _numrange(pat, i, "]"):
            lo, hi, j = _numrange(pat, i, "]")
            toks.append(("NUM", lo, hi))
            i = j                                         # the ']' starts the next literal (as in setPattern)
        elif c == "{":
            r = _numrange(pat, i, "}")
            if r:
                toks.append(("NUM", r[0], r[1]))
                i = r[2] + 1
            else:
                j = pat.index("}", i + 2 if pat[i + 1:i + 2] in ("^", "}") or pat[i + 1:i + 3] == "^}" else i + 1)
                body = pat[i + 1:j]
                neg = body.startswith("^")
                body = body[1:] if neg else body
                toks.append(("NEGSET" if neg else "SET", _set(body)))
                i = j + 1
        elif c == "*":
            if pat[i + 1:i + 2] == "*":
                toks.append(("ANYSEQ",))
                i += 2
            else:
                toks.append(("NONDOTSEQ",))
                i += 1
        else:
            # parseLiteralString: append characters up to ? { * ; a '[' that starts a numeric range "[lo..hi]" is
            # appended and ends the literal WITHOUT advancing, so that the next round reads it as NUM
            lit = ""
            while i < len(pat) and pat[i] not in "?{*":
                if pat[i] == "\\" and i + 1 < len(pat):
                    i += 1
                    lit += pat[i]
                else:
                    lit += pat[i]
                if pat[i] == "[" and _numrange(pat, i, "]"):
                    break
                i += 1
            toks.append(("LIT", lit))
    return toks


def _set(body):
    out = []
    k = 0
    while k < len(body):
        if k + 2 < len(body) and body[k + 1] == "-":
            out.append((body[k], body[k + 2]))
            k += 3
        else:
            out.append((body[k], body[k]))
            k += 1
    return out


def match(pat, path):
    toks = tokenize(pat)
    memo = {}

    def m(ti, si):
        key = (ti, si)
        if key in memo:
            return memo[key]
        if ti == len(toks):
            r = si == len(path)
        else:
            t = toks[ti]
            r = False
            if t[0] == "LIT":
                r = path.startswith(t[1], si) and m(ti + 1, si + len(t[1]))
            elif t[0] == "NONDOTCHAR":
                r = si < len(path) and path[si] != "." and m(ti + 1, si + 1)
            elif t[0] in ("SET", "NEGSET"):
                if si < len(path):
                    inside = any(a <= path[si] <= b for a, b in t[1])
                    r = (inside if t[0] == "SET" else not inside) and m(ti + 1, si + 1)
            elif t[0] == "NUM":
                mm = re.match(r"\d+", path[si:])           # the C++ matcher consumes the WHOLE digit run (no backtracking)
                if mm:
                    v, L = int(mm.group()), len(mm.group())
                    r = (t[1] < 0 or v >= t[1]) and (t[2] < 0 or v <= t[2]) and m(ti + 1, si + L)
            elif t[0] == "ANYSEQ":
                r = any(m(ti + 1, j) for j in range(si, len(path) + 1))
            elif t[0] == "NONDOTSEQ":
                j = si
                while True:
                    if m(ti + 1, j):
                        r = True
                        break
                    if j >= len(path) or path[j] == ".":
                        break
                    j += 1
        memo[key] = r
        return r
    return m(0, 0)


# -------------------------------------------------------------------------------------------- module inventory ---
# (module path relative to the network, class, draws according to the source reading; addendum §2.2)
def inventory(n):
    mods = [(f"{DIRECT}.scheduler-tiebreak", "direct", "MAXCI equal-score coin flip / QoS-PF and PF score jitter (gNB, every scheduled TTI with candidates)"),
            (f"{DIRECT}.bler-table", "direct", "PhyPisaData constructor (once, at start-up; independent of N)"),
            ("gnb1.cellularNic.mac", "gnb", "scheduler module (its own draws: none found; tie-breaks are direct)"),
            ("gnb1.cellularNic.phy", "gnb", "PhyEnb randomChannelIndex_ (initialisation)"),
            ("gnb1.cellularNic.channelModel[0]", "gnb-shared", "UL reception / fading / shadowing of EVERY UE (one module)"),
            ("listener.clock.oscillator", "clock", "GM clock oscillator (draws only with a random-drift oscillator)"),
            ("nwTt.eth[1].trafficConditionerLayer.ttClock", "clock", "NW-TT TT clock (draws only with a noisy TT clock)")]
    for j in range(2 * n + 1):
        mods.append((f"listener.app[{j}].source", "app", "constant production interval and length: no draw"))
    for k in range(n):
        mods += [(f"ue[{k}].cellularNic.nrMac", f"ue{k}", "random access (checkRAC): preamble, back-off"),
                 (f"ue[{k}].cellularNic.mac", f"ue{k}", "LTE-leg MAC random access (if the LTE leg is active)"),
                 (f"ue[{k}].cellularNic.nrPhy", f"ue{k}", "PHY (draws only through its channel model)"),
                 (f"ue[{k}].cellularNic.nrChannelModel[0]", f"ue{k}", "DL reception success, Jakes fading, shadowing of UE k's own frames"),
                 (f"ue[{k}].cellularNic.channelModel[0]", f"ue{k}", "LTE-leg channel model"),
                 (f"talker[{k}].clock.oscillator", "clock", f"slave {k} clock oscillator"),
                 (f"dsTt[{k}].eth[1].trafficConditionerLayer.ttClock", "clock", f"DS-TT {k} TT clock"),
                 (f"talker[{k}].app[0].source", "app", "constant production interval and length: no draw")]
    return mods


def is_clock(path):
    return path.endswith("clock.oscillator") or path.endswith("ttClock")


def owner_ue(cls):
    return int(cls[2:]) if cls.startswith("ue") else None


# ------------------------------------------------------------------------------------------------ the map -------
def seeds(entries, rep=0):
    eff = {}
    for k, v in entries:
        eff.setdefault(k, v)
    num = int(eff.get("num-rngs", "1"))
    ss = eff.get("seed-set", "${repetition}").replace("${repetition}", str(rep))
    ss = int(ss) if ss.lstrip("-").isdigit() else rep
    out = {}
    for j in range(num):
        v = eff.get(f"seed-{j}-mt")
        if v is None:
            out[j] = (ss * num + j, "auto")
        else:
            out[j] = (int(v.replace("${repetition}", str(rep))), "explicit")
    return num, out


def first_value(entries, full, suffix):
    """the value of the first entry '<pattern>.<suffix>' whose pattern matches the module's full path (None if none)"""
    for k, v in entries:
        if k.endswith("." + suffix) and match(k[:-len(suffix) - 1], full):
            return v.strip()
    return None


CONDITIONAL = ("trafficConditionerLayer.ttClock",)     # NED: 'ttClock: <default("")> like ITtClock if typename != ""'


def exists(entries, path):
    """modules whose existence depends on a typename (TtPtpPort.ned: the TT clock exists only with a typename)"""
    if path.endswith(CONDITIONAL):
        v = first_value(entries, f"{NET}.{path}", "typename")
        return v not in (None, '""', "")
    return True


def rng_map(entries, n, rep=0):
    """{module path: (physical RNG, the matching entry or 'default', class, note)} for the modules of the inventory
    at N = n that exist in this configuration"""
    rules = []
    for k, v in entries:
        m = re.fullmatch(r"(.*)\.rng-0", k)
        if m:
            rules.append((m.group(1), v.strip()))
    out = {}
    for path, cls, why in inventory(n):
        if path.startswith(DIRECT):
            out[path] = (0, "direct caller", cls, why)
            continue
        if not exists(entries, path):
            continue
        full = f"{NET}.{path}"
        if path.endswith("clock.oscillator"):
            ty = first_value(entries, full, "typename")
            why = f"{why}; oscillator typename {ty or '(NED default)'}"
        hit = next(((p, v) for p, v in rules if match(p, full)), None)
        if hit is None:
            out[path] = (0, "default (local 0 -> physical 0)", cls, why)
        else:
            v = hit[1]
            out[path] = (int(v) if v.isdigit() else f"UNRESOLVED {v}", f"{hit[0]}.rng-0 = {v}", cls, why)
    return out


RANDOM_FN = re.compile(r"\b(uniform|exponential|normal|truncnormal|lognormal|gamma_d|beta|erlang_k|chi_square|student_t|"
                       r"cauchy|triang|weibull|pareto_shifted|intuniform|intuniformexcl|bernoulli|binomial|geometric|"
                       r"negbinomial|poisson)\s*\(")


def app_draws(entries, path):
    """an application source draws only if one of its effective parameter values is a random expression"""
    full = f"{NET}.{path}"
    for k, v in entries:
        head, _, par = k.rpartition(".")
        if head and RANDOM_FN.search(v) and (match(head, full) or match(k, full + "." + par)):
            return True
    return False


def draws(mp_entry, entries=None, path=None):
    cls = mp_entry[2]
    if cls == "app":
        return entries is not None and app_draws(entries, path)
    return True                                    # every other module class has a call site (source reading)


def multi_ue(path, cls):
    """one module serving every UE: its own draw count and order depend on N whatever the mapping (the gNB MAC /
    PHY / channel model, and the scheduler tie-break / jitter); the BLER table is drawn once at start-up"""
    return cls in ("gnb", "gnb-shared") or path.endswith("scheduler-tiebreak")


def consumers(mp, entries=None):
    """physical RNG -> [(path, class)] of the modules that can draw from it"""
    by = {}
    for path, x in mp.items():
        if draws(x, entries, path):
            by.setdefault(x[0], []).append((path, x[2]))
    return by


def audit(entries, n, rep=0):
    num, sd = seeds(entries, rep)
    mp = rng_map(entries, n, rep)
    by = consumers(mp, entries)
    for j in by:
        if j not in sd and isinstance(j, int):
            sd[j] = (None, "missing")
    rows = []
    unres = [p for p, x in mp.items() if not isinstance(x[0], int)]
    out_of_range = [p for p, x in mp.items() if isinstance(x[0], int) and x[0] >= num]
    auto = sorted(j for j in by if isinstance(j, int) and j < num and sd[j][1] == "auto")
    vals = [sd[j][0] for j in sd]
    dup = sorted({v for v in vals if vals.count(v) > 1})
    ok = not auto and not dup and not unres and not out_of_range
    rows.append(("RA-1", "PASS" if ok else "FAIL",
                 f"num-rngs {num}; seeds {[(j, sd[j][0], sd[j][1]) for j in sorted(sd)]}; auto-seeded with consumers {auto}; "
                 f"duplicate seed values {dup}; unresolved maps {unres}; out of range {out_of_range}"))
    bad = []
    for path, (j, how, cls, why) in mp.items():
        if cls == "clock":
            others = [p for p, c in by.get(j, []) if c != "clock"]
            if others:
                bad.append((path, j, others[:4]))
    rows.append(("RA-2", "PASS" if not bad else "FAIL",
                 "every clock module on a physical RNG without non-clock consumers" if not bad else f"clock streams shared: {bad[:6]}"))
    shared = {}
    for j, cs in by.items():
        ues = sorted({owner_ue(c) for _, c in cs if owner_ue(c) is not None})
        if len(ues) >= 2:
            shared[j] = ues
    rows.append(("RA-3", "INFO", f"physical RNGs drawn by modules of >= 2 UEs: {shared or 'none'}; consumers of physical RNG 0: "
                 f"{sorted({c for _, c in by.get(0, [])})} ({len(by.get(0, []))} modules)"))
    return rows, mp, sd


def pair(entries_a, na, entries_b, nb, rep=0):
    """RA-4 for the modules present in A (every UE k < na and the shared modules)"""
    _, sda = seeds(entries_a, rep)
    _, sdb = seeds(entries_b, rep)
    ma, mb = rng_map(entries_a, na, rep), rng_map(entries_b, nb, rep)
    ca, cb = consumers(ma, entries_a), consumers(mb, entries_b)
    res = []
    for path, (ja, how, cls, why) in sorted(ma.items()):
        if not draws(ma[path], entries_a, path):
            res.append((path, cls, "NO DRAWS", ja, mb.get(path, (None,))[0], []))
            continue
        if path not in mb:
            res.append((path, cls, "ABSENT IN B", ja, None, []))
            continue
        jb = mb[path][0]
        if multi_ue(path, cls):
            res.append((path, cls, "MULTI-UE", ja, jb, []))
            continue
        same = ja == jb and isinstance(ja, int) and sda.get(ja, (None,))[0] == sdb.get(jb, (None,))[0]
        new = sorted({p for p, _ in cb.get(jb, [])} - {p for p, _ in ca.get(ja, [])}) if same else []
        status = "INVARIANT" if same and not new else "COUPLED"
        res.append((path, cls, status, ja, jb, new[:5] + (["..."] if len(new) > 5 else [])))
    return res


# ---------------------------------------------------------------------------- proposed control: isolation mixin --
ISO_BASE = 16          # physical RNGs 16 .. 16 + 7: UE k's NIC; 24: the gNB NIC (fixed for every N <= 8)
ISO_GNB = 24
ISO_NUM = 25


def isolation_mixin(n_max=8):
    """PROPOSED (addendum §2.4; not generated into any configuration until approved, decision S5-2-D1): every UE's
    NIC on its own physical RNG with an N-invariant index and seed, the gNB NIC on one more; num-rngs fixed to 25 at
    every N. It precedes the clock entries; it changes no clock stream. What it cannot isolate (direct RNG-0
    callers, the gNB's one channel model for all UEs) stays shared and is reported by RA-3 / RA-4."""
    lines = ["num-rngs = 25"]
    for j in range(2, ISO_NUM):                    # the generator's own seed scheme (seed-j-mt = j00${repetition}),
        lines.append(f"seed-{j}-mt = {j}00${{repetition}}")    # explicit for every index, so no seed depends on N
    for k in range(n_max):
        lines.append(f"*.ue[{k}].cellularNic.**.rng-0 = {ISO_BASE + k}")
    lines.append(f"*.gnb1.cellularNic.**.rng-0 = {ISO_GNB}")
    return lines


def with_mixin(entries, lines):
    """effective entries with the mixin's lines first (a mixin listed first in 'extends' takes precedence); the
    mixin's num-rngs and seeds replace the configuration's"""
    mix = [tuple(x.strip() for x in l.split("=", 1)) for l in lines]
    keys = {k for k, _ in mix}
    seedkeys = {k for k in keys if k.startswith("seed-") or k == "num-rngs"}
    return mix + [(k, v) for k, v in entries if k not in seedkeys]


# ---------------------------------------------------------------------------------------------- runconfig ------
def runconfig(ini, cfg, cmd):
    sys.path.insert(0, os.path.join(M2, "tools"))
    import m2s72_gen as G
    r = subprocess.run(cmd + ["-f", ini, "-c", cfg, "-r", "0", "-q", "runconfig"], cwd=M2, capture_output=True, text=True)
    ents = G.runconfig_entries(r.stdout)
    eff = {}
    for k, v in ents:
        eff.setdefault(k, v)
    n = int(eff.get("*.numUe", "1"))
    return ents, n


def main(argv):
    if len(argv) >= 3 and argv[1] == "isolation-mixin":
        print("\n".join(isolation_mixin(int(argv[2]))))
        return 0
    if len(argv) < 4 or argv[1] not in ("audit", "pair") or "--" not in argv:
        print(__doc__)
        return 2
    i = argv.index("--")
    ini, cfgs, cmd = argv[2], argv[3:i], argv[i + 1:]
    if argv[1] == "audit":
        fails = 0
        for cfg in cfgs:
            ents, n = runconfig(ini, cfg, cmd)
            for label, e in (("as configured", ents), ("with the proposed isolation mixin", with_mixin(ents, isolation_mixin(8)))):
                rows, mp, sd = audit(e, n)
                print(f"== {cfg} (N = {n}), {label}")
                for r in rows:
                    print(f"  {r[1]:<5} {r[0]}  {r[2]}")
                    fails += label == "as configured" and r[1] == "FAIL"
            print("  map (as configured):")
            for path, (j, how, cls, why) in rng_map(ents, n).items():
                print(f"    {path:<52} -> {j!s:>3}  [{how}]  {why}")
        return 1 if fails else 0
    a, b = cfgs
    ea, na = runconfig(ini, a, cmd)
    eb, nb = runconfig(ini, b, cmd)
    for label, xa, xb in (("as configured", ea, eb),
                          ("with the proposed isolation mixin", with_mixin(ea, isolation_mixin(8)), with_mixin(eb, isolation_mixin(8)))):
        res = pair(xa, na, xb, nb)
        cnt = {st: sum(1 for x in res if x[2] == st) for st in ("INVARIANT", "COUPLED", "MULTI-UE", "NO DRAWS", "ABSENT IN B")}
        print(f"== RA-4 {a} (N = {na}) -> {b} (N = {nb}), {label}: " + ", ".join(f"{v} {k}" for k, v in cnt.items()))
        for path, cls, st, ja, jb, new in res:
            print(f"  {st:<9} {path:<52} RNG {ja} -> {jb}" + (f"; new consumers {new}" if new else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
