#!/usr/bin/env python3
"""Effective-entry flattening check of m2s72.ini (G0-R1, 2026-11-15): version-independent companion of the accepted
`m2s72_gen.py verify`, which is unchanged and keeps its own verdicts.

Finding G0-R1. The accepted verify compares the generator's flattening (every entry of the inheritance chain, in
order) with `opp_run -q runconfig`. OMNeT++ 6.4.0 prints the whole chain, including shadowed entries (mixin
descriptions, `extends`, overridden keys); OMNeT++ 6.5.0 prints only the first, effective entry per key. On 6.5.0
the accepted verify therefore reports DIFFERENT for all nine source configurations although every effective entry
is equal. This check compares the effective lists, first entry per key in order, keys and values, on both sides, so
it holds on either output form and is as strict as the accepted check on everything OMNeT++ uses.

    m2s72_verify_eff.py check   <opp_run command...>   every source config: effective lists identical; also reports
                                                       the runconfig form seen (full chain / first per key)
    m2s72_verify_eff.py control <opp_run command...>   mutation controls: one changed effective value, one dropped
                                                       effective key and one reordered pair must each be DIFFERENT;
                                                       a changed shadowed entry must stay IDENTICAL (it is not used)

Reuses the accepted generator's parse / flatten / expand / runconfig_entries functions unchanged. Read-only.
"""
import os
import subprocess
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import m2s72_gen as G  # noqa: E402


def norm(v):
    return " ".join(v.replace("\\", " ").split())


def first_per_key(pairs):
    seen, out = set(), []
    for k, v in pairs:
        if k not in seen:
            seen.add(k)
            out.append((k, v))
    return out


def lists(cmd, cfg, sections):
    full = [(e.key, norm(G.expand(e.value, cfg))) for e in G.flatten(sections, cfg)]
    res = subprocess.run(cmd + ["-c", cfg, "-r", "0", "-q", "runconfig"], cwd=G.M2, capture_output=True, text=True)
    theirs = [(k, norm(v)) for k, v in G.runconfig_entries(res.stdout)]
    return full, theirs


def form(full, theirs):
    if theirs == full:
        return "full chain"
    if theirs == first_per_key(full):
        return "first per key"
    return "neither"


def check(cmd):
    sections, _ = G.parse(G.INI)
    bad = 0
    for cfg in G.SOURCES:
        if cfg in G.LOAD_VAR:
            continue
        full, theirs = lists(cmd, cfg, sections)
        a, b = first_per_key(full), first_per_key(theirs)
        ok = a == b
        bad += not ok
        print(f"{cfg}: effective entries generator {len(a)}, OMNeT++ {len(b)}: "
              f"{'IDENTICAL (keys, values, order)' if ok else 'DIFFERENT'}; runconfig form: {form(full, theirs)} "
              f"({len(theirs)} printed, chain {len(full)})")
        if not ok:
            for j, (x, y) in enumerate(zip(a, b)):
                if x != y:
                    print(f"   first difference at effective entry {j}: generator {x!r} vs runconfig {y!r}")
                    break
    print(f"effective-entry check: {'all IDENTICAL' if bad == 0 else f'{bad} DIFFERENT'}")
    return 1 if bad else 0


def control(cmd):
    sections, _ = G.parse(G.INI)
    cfg = next(c for c in G.SOURCES if c not in G.LOAD_VAR)
    full, theirs = lists(cmd, cfg, sections)
    b = first_per_key(theirs)
    a = first_per_key(full)
    res = []
    m = list(a)
    k, v = m[5]
    m[5] = (k, v + "1")
    res.append(("NC-value: one effective value changed", m != b))
    res.append(("NC-drop: one effective key dropped", a[:7] + a[8:] != b))
    m = list(a)
    m[3], m[4] = m[4], m[3]
    res.append(("NC-order: two effective entries swapped", m != b))
    keys = [x for x, _ in full]
    j = next(i for i, x in enumerate(keys) if x in keys[:i])         # first shadowed entry of the chain
    f2 = list(full)
    f2[j] = (f2[j][0], f2[j][1] + "-shadowed")
    res.append((f"PC-shadow: a shadowed entry changed ({full[j][0]}) is not an effective change", first_per_key(f2) == b))
    res.append(("baseline: unmutated effective lists identical", a == b))
    for nm, ok in res:
        print(f"{'PASS' if ok else 'FAIL'} | {cfg}: {nm}")
    print(f"effective-entry controls: {sum(ok for _, ok in res)} / {len(res)} PASS")
    return 0 if all(ok for _, ok in res) else 1


if __name__ == "__main__":
    if len(sys.argv) < 3 or sys.argv[1] not in ("check", "control"):
        print(__doc__)
        sys.exit(2)
    sys.exit((check if sys.argv[1] == "check" else control)(sys.argv[2:]))
