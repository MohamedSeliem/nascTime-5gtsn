#!/usr/bin/env python3
"""M2-S7.1 gates (migration/m2-s7.1-design.md rev. 3).

    gate_m2s71.py m0    <results/M2-S7.1> <results>   gate M0 (design 3.3)
    gate_m2s71.py gates <results/M2-S7.1> <results>   gates P0, C0, C1, Q0a, Q0b (design 4, 5)

M0, monitor non-perturbation:
  (a) with the monitor present, every PCAP and log (except the monitor's own) of M2S5 seeds 0-9,
      M2S5U-hold and M2S6-C-a seeds 0-9 is hash-identical to the committed M2-S5 / M2-S6 records;
  (b) Q-d (UM) idle with and without the monitor: every PCAP and log identical;
  (c) event fingerprints (OMNeT++ tplx: every event's time, module, message length and context):
      monitor present = absent for the four pairs above;
  (d) sensitivity (N-monitor): one TEST self-message changes the fingerprint while every PCAP stays
      identical, so (c) detects what (a)/(b) cannot.
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)

rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ref_hashes(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            h, p = line.split()
            out[p[2:] if p.startswith("./") else p] = h
    return out


def run_files(root, cfg, rep):
    """relative paths cfg/{pcap,m2log}/cfg-rep/<file> of a run's PCAP and logs (monitor log excluded)"""
    out = []
    for sub in ("pcap", "m2log"):
        d = os.path.join(root, cfg, sub, f"{cfg}-{rep}")
        if os.path.isdir(d):
            out += [os.path.join(cfg, sub, f"{cfg}-{rep}", f) for f in sorted(os.listdir(d)) if not f.endswith(".monitor.csv")]
    return out


def compare_ref(root, cfg, rep, ref, ref_cfg, ref_rep):
    """(n in the record, n identical, missing here, extra here)"""
    mine = {p.replace(f"{cfg}/", f"{ref_cfg}/", 1).replace(f"{cfg}-{rep}", f"{ref_cfg}-{ref_rep}"): p for p in run_files(root, cfg, rep)}
    want = {p for p in ref if p.startswith(f"{ref_cfg}/pcap/{ref_cfg}-{ref_rep}/") or p.startswith(f"{ref_cfg}/m2log/{ref_cfg}-{ref_rep}/")}
    same = sum(1 for k, p in mine.items() if k in want and ref[k] == sha(os.path.join(root, p)))
    return len(want), same, len(want - set(mine)), len(set(mine) - want)


def compare_runs(root, a, b, rep=0):
    fa, fb = run_files(root, a, rep), run_files(root, b, rep)
    ka = {p.replace(f"{a}/", "X/", 1).replace(f"{a}-{rep}", "X-0"): p for p in fa}
    kb = {p.replace(f"{b}/", "X/", 1).replace(f"{b}-{rep}", "X-0"): p for p in fb}
    same = sum(1 for k in ka if k in kb and sha(os.path.join(root, ka[k])) == sha(os.path.join(root, kb[k])))
    return len(ka), len(kb), same


def fingerprint(root, cfg):
    log = os.path.join(root, f"run-{cfg}.log")
    m = re.search(r"calculated: ([0-9a-f]{4}-[0-9a-f]{4}/\w+)", open(log).read()) if os.path.exists(log) else None
    return m.group(1) if m else None


def m0(out, results):
    r5 = ref_hashes(os.path.join(results, "M2-S5", "raw-outputs.sha256"))
    r6 = ref_hashes(os.path.join(results, "M2-S6", "raw-outputs.sha256"))
    root = os.path.join(out, "runs-m0")
    tot = same = miss = extra = 0
    for rep in range(10):
        n, s, m, e = compare_ref(root, "M2S71-M0-m2s5", rep, r5, "M2S5", rep)
        tot, same, miss, extra = tot + n, same + s, miss + m, extra + e
    add("M0 (a) monitor present, M2S5", f"M2S71-M0-m2s5 seeds 0-9: {same}/{tot} PCAP/log hashes identical to the M2-S5 record (M2S5 seeds 0-9)",
        same == tot and tot > 0 and not miss and not extra, f"missing {miss}, extra {extra}")
    n, s, m, e = compare_ref(root, "M2S71-M0-hold", 0, r5, "M2S5U-hold", 0)
    add("M0 (a) monitor present, M2S5U-hold", f"M2S71-M0-hold-0: {s}/{n} PCAP/log hashes identical to the M2-S5 record (M2S5U-hold-0)",
        s == n and n > 0 and not m and not e, f"missing {m}, extra {e}")
    tot = same = miss = extra = 0
    for rep in range(10):
        n, s, m, e = compare_ref(root, "M2S71-M0-Ca", rep, r6, "M2S6-C-a", rep)
        tot, same, miss, extra = tot + n, same + s, miss + m, extra + e
    add("M0 (a) monitor present, M2S6-C-a", f"M2S71-M0-Ca seeds 0-9: {same}/{tot} PCAP/log hashes identical to the M2-S6 record (M2S6-C-a seeds 0-9)",
        same == tot and tot > 0 and not miss and not extra, f"missing {miss}, extra {extra}")
    na, nb, s = compare_runs(root, "M2S71-qdu-idle", "M2S71-M0-qdu-off")
    add("M0 (b) Q-d (UM) idle", f"monitor present vs absent: {s} of {na}/{nb} PCAP/log files identical", na == nb == s and na > 0)
    mons = []
    for cfg, reps in (("M2S71-M0-m2s5", range(10)), ("M2S71-M0-hold", [0]), ("M2S71-M0-Ca", range(10)), ("M2S71-qdu-idle", [0])):
        for rep in reps:
            d = os.path.join(root, cfg, "m2log", f"{cfg}-{rep}")
            ml = [f for f in os.listdir(d) if f.endswith(".monitor.csv")] if os.path.isdir(d) else []
            mons.append(len(ml) == 1 and os.path.getsize(os.path.join(d, ml[0])) > 100)
    add("M0 monitor active", f"every monitor-present run wrote its monitor log ({sum(mons)}/{len(mons)})", all(mons) and mons)
    fpr = os.path.join(out, "runs-m0fp")
    for a, b in (("M2S5", "M2S71-M0-m2s5"), ("M2S5U-hold", "M2S71-M0-hold"), ("M2S6-C-a", "M2S71-M0-Ca"), ("M2S71-M0-qdu-off", "M2S71-qdu-idle")):
        fa, fb = fingerprint(fpr, a), fingerprint(fpr, b)
        add("M0 (c) event fingerprint", f"{a}-0 (no monitor) {fa} = {b}-0 (monitor) {fb}", fa is not None and fa == fb)
    fa, fn = fingerprint(fpr, "M2S5"), fingerprint(fpr, "M2S71-N-monitor")
    pa = [f for f in run_files(fpr, "M2S5", 0) if "/pcap/" in f]
    pb = {f.replace("M2S71-N-monitor", "M2S5"): f for f in run_files(fpr, "M2S71-N-monitor", 0) if "/pcap/" in f}
    psame = sum(1 for f in pa if f in pb and sha(os.path.join(fpr, f)) == sha(os.path.join(fpr, pb[f])))
    la = [f for f in run_files(fpr, "M2S5", 0) if "/m2log/" in f]
    lb = {f.replace("M2S71-N-monitor", "M2S5"): f for f in run_files(fpr, "M2S71-N-monitor", 0) if "/m2log/" in f}
    ldiff = sorted(os.path.basename(f) for f in la if f in lb and sha(os.path.join(fpr, f)) != sha(os.path.join(fpr, lb[f])))
    add("M0 (d) sensitivity, N-monitor", f"one TEST self-message: fingerprint {fn} != {fa}, while every PCAP stays identical ({psame}/{len(pa)}); "
        f"the logs that record packet tree ids differ ({len(ldiff)} of {len(la)}: the extra message shifts the ids)",
        fn is not None and fa is not None and fn != fa and psame == len(pa) == len(pb) and len(pa) > 0)


def report():
    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {check}: {detail}" + (f" -- {extra}" if extra else ""))
    print(f"OVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    return 0 if npass == len(rows) else 1


def main():
    mode, out, results = sys.argv[1:4]
    if mode == "m0":
        m0(out, results)
    elif mode == "gates":
        import gate_m2s71_p0 as P
        P.gates(out, results, add)
    else:
        raise SystemExit("unknown mode " + mode)
    return report()


if __name__ == "__main__":
    sys.exit(main())
