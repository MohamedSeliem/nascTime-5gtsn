#!/usr/bin/env python3
"""M2-S7.2a A2-V1: fail-closed helper of the single-run wrapper m2s72a2v1.sh (protocol
results/M2-S7.2a-a2d2-protocol-r1.md). No simulation. Every command prints one line and exits 0 only if its check
holds; anything missing or unreadable is a failure, never a pass.

    m2s72a2v1_gate.py pins <m2 dir>                       the reviewed configuration files are byte-identical to the pins
    m2s72a2v1_gate.py config-diff <base dump> <new dump>  the effective configuration differs from the baseline by
                                                          EXACTLY the declared lines (none missing, none extra)
    m2s72a2v1_gate.py size <path>...                      apparent bytes of the regular files under the paths
    m2s72a2v1_gate.py baseline-size <manifest> <path>...  baseline raw bytes: the manifest's sum, which must equal the
                                                          files on disk (same set, same sizes)
    m2s72a2v1_gate.py stack <baseline env file> <libsimu5g.so> <INET Version> <Simu5G Version>
                                                          the same Simu5G binary and versions as the baseline N = 2 smoke
    m2s72a2v1_gate.py source <SIMU5G_ROOT>                A2-0s: every Simu5G text A-2 relies on is in this tree
    m2s72a2v1_gate.py nc-baseline <rc> <a2v1 txt>         NC-V-baseline: rc 4 with V-0 FAIL and V-1 FAIL"""
import hashlib
import os
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True

BASE = "M2S72-E0vN-q0-one0-n2-f1"
CFG = "M2S72-E0vN-q0-one0-n2-f1_A2V1"
# the configuration reviewed in A2-D2 (commit 39a6434) and the accepted sources it includes (fbee202)
PINS = {"m2s72a2v.ini": "d55d57a8cf9f280c45e30ec392a4cdb8543725130158c7ae11bc89a12ef862ee",
        "m2s72s5.ini": "e563c489852db4cac7ad8562c97373e2379c8bd4029c7f1ebb9d2ace2ff96903",
        "m2s72.ini": "dfc8a7f7bb7cd1632c335c169cdbd3535e4e90a14b0d04882bb07b406aaf5505"}
# the runconfig difference declared in the design review §5.1, with both configuration names replaced by CFG
EXPECTED_ADDED = Counter([
    'description = "A2-V1 (A2-D2 proposal, not authorised): M2S72-E0vN-q0-one0-n2-f1 unchanged + M2S72A2V-ideal-nack-ue1; single run, seed 0"',
    "extends = M2S72A2V-ideal-nack-ue1, M2S72-E0vN-q0-one0-n2-f1",
    '*.gnb1.cellularNic.channelModelType = "IdealChannelModel"',
    '*.ue[*].cellularNic.nrChannelModelType = "IdealChannelModel"',
    "*.ue[1].cellularNic.nrChannelModel[*].perDl = 0.1",
    "*.ue[1].cellularNic.nrChannelModel[*].harqReduction = 1",
    "**.perDl = 0", "**.perUl = 0", "**.perD2D = 0", "num-rngs = 5", "seed-4-mt = 4000",
    "**.channelModel[*].rng-0 = 4", "**.nrChannelModel[*].rng-0 = 4"])
EXPECTED_REMOVED = Counter([
    'description = "E0v-N bracket: M2S71-q0-Ca-sus, one0, numUe = 2, DL factor 1, UL factor 1, HARQ16 (experimental control), MAC logs"',
    "extends = M2S72-MACLOG, M2S72S5-MACLOG-UE, M2S72LD-q0-Ca-L-one0-n2-f1, M2S72-HARQ16, M2S72-SL, M2S72-L, M2S72-ev, "
    "M2S72D4N2-q0-Ca-L, M2S72N2-q0-Ca-L, M2S72B-q0-Ca-L",
    "num-rngs = 4"])
NC_BASELINE_RC = 4


def sha256(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def pins(m2dir):
    bad = []
    for f, want in PINS.items():
        p = os.path.join(m2dir, f)
        got = sha256(p) if os.path.isfile(p) else "missing"
        if got != want:
            bad.append(f"{f} {got} (pinned {want})")
    return (not bad), ("pins OK: " + ", ".join(f"{f} {h[:12]}" for f, h in PINS.items())) if not bad else f"PIN MISMATCH {bad}"


def _dump_lines(path, name):
    """the run's entries of an 'opp_run -q runconfig' dump, configuration name normalised to CFG"""
    if not os.path.isfile(path):
        raise ValueError(f"{path}: missing")
    txt = open(path, errors="replace").read()
    if f"Config: {name}\n" not in txt or "End." not in txt:
        raise ValueError(f"{path}: not a complete runconfig dump of {name}")
    body = txt[txt.index(f"Config: {name}\n"):txt.rindex("End.")]
    return [x.strip().replace(CFG, "CFG").replace(BASE, "CFG") for x in body.split("\n") if x.strip()]


def config_diff(base_dump, new_dump):
    b, n = Counter(_dump_lines(base_dump, BASE)), Counter(_dump_lines(new_dump, CFG))
    # result paths and the config line differ only by the (normalised) name: equal after normalisation
    added, removed = n - b, b - n
    norm = lambda c: Counter({k.replace(CFG, "CFG").replace(BASE, "CFG"): v for k, v in c.items()})  # noqa: E731
    ea, er = norm(EXPECTED_ADDED), norm(EXPECTED_REMOVED)
    probs = []
    if added - ea:
        probs.append(f"undeclared added {sorted((added - ea).elements())[:5]}")
    if ea - added:
        probs.append(f"declared but absent {sorted((ea - added).elements())[:5]}")
    if removed - er:
        probs.append(f"undeclared removed {sorted((removed - er).elements())[:5]}")
    if er - removed:
        probs.append(f"declared removal absent {sorted((er - removed).elements())[:5]}")
    return (not probs), (f"config diff = the declared set exactly ({sum(added.values())} added, {sum(removed.values())} removed)"
                         if not probs else f"CONFIG DIFF {probs}")


def size(paths):
    import m2s72s5_lib as LIB
    return sum(os.path.getsize(f) for f in LIB.files_under(paths))


def baseline_size(manifest, paths):
    import m2s72s5_lib as LIB
    if not os.path.isfile(manifest):
        return False, f"BASELINE SIZE: manifest {manifest} missing", None
    rows = LIB.read_manifest(manifest)
    if not rows:
        return False, f"BASELINE SIZE: manifest {manifest} empty", None
    man = {os.path.abspath(p): int(s) for _, s, p in rows}
    disk = {f: os.path.getsize(f) for f in LIB.files_under(paths)}
    if not disk:
        return False, f"BASELINE SIZE: no files under {paths}", None
    if man != disk:
        miss, extra = sorted(set(man) - set(disk))[:3], sorted(set(disk) - set(man))[:3]
        diff = sorted(f for f in set(man) & set(disk) if man[f] != disk[f])[:3]
        return False, f"BASELINE SIZE: manifest and disk differ (missing {miss}, unlisted {extra}, size differs {diff})", None
    tot = sum(man.values())
    return True, f"baseline raw {tot} B in {len(man)} files (manifest = disk)", tot


def stack(env_file, lib, inet_version, simu5g_version):
    if not os.path.isfile(env_file):
        return False, f"STACK: baseline env record {env_file} missing"
    rec = {}
    for line in open(env_file, errors="replace"):
        k, _, v = line.partition(":")
        rec[k.strip()] = v.strip()
    now = {"libsimu5g_sha256": sha256(lib) if os.path.isfile(lib) else "missing",
           "inet_version_file": open(inet_version).read().strip() if os.path.isfile(inet_version) else "missing",
           "simu5g_version_file": open(simu5g_version).read().strip() if os.path.isfile(simu5g_version) else "missing"}
    bad = [f"{k}: now {v}, baseline {rec.get(k, 'absent')}" for k, v in now.items() if not rec.get(k) or rec.get(k) != v]
    return (not bad), ("same stack as the baseline N = 2 smoke: " + ", ".join(f"{k} {v[:16]}" for k, v in now.items())) if not bad \
        else f"STACK MISMATCH {bad}"


def source(root):
    import m2s72_a2 as A2
    r = A2.source_row(root)
    return r[2] == "PASS", f"{r[0]} {r[2]}: {r[3]}"


def nc_baseline(rc, txt):
    if int(rc) != NC_BASELINE_RC:
        return False, f"NC-V-BASELINE: rc {rc}, declared {NC_BASELINE_RC}"
    if not os.path.isfile(txt):
        return False, f"NC-V-BASELINE: {txt} missing"
    t = open(txt, errors="replace").read()
    rows = {ln.split("|")[1].strip(): ln.split("|")[0].strip() for ln in t.split("\n") if ln.count("|") >= 2 and ln.startswith("  ")}
    ok = rows.get("V-0") == "FAIL" and rows.get("V-1") == "FAIL"
    return ok, f"NC-V-baseline rc {rc}, V-0 {rows.get('V-0')}, V-1 {rows.get('V-1')}" + ("" if ok else " (declared V-0 FAIL, V-1 FAIL)")


def main(argv):
    try:
        cmd = argv[1]
        if cmd == "pins":
            ok, msg = pins(argv[2])
        elif cmd == "config-diff":
            ok, msg = config_diff(argv[2], argv[3])
        elif cmd == "size":
            print(size(argv[2:]))
            return 0
        elif cmd == "baseline-size":
            ok, msg, tot = baseline_size(argv[2], argv[3:])
            print(msg)
            if ok:
                print(tot)
            return 0 if ok else 1
        elif cmd == "stack":
            ok, msg = stack(*argv[2:6])
        elif cmd == "source":
            ok, msg = source(argv[2])
        elif cmd == "nc-baseline":
            ok, msg = nc_baseline(argv[2], argv[3])
        else:
            print(__doc__)
            return 2
    except Exception as ex:  # an unreadable input is a failed check, never a pass
        print(f"GATE ERROR ({argv[1:2]}): {type(ex).__name__}: {ex}")
        return 2
    print(msg)
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
