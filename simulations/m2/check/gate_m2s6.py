#!/usr/bin/env python3
"""M2-S6 gate D0 (migration/m2-s6-design.md rev. 2, section 6.1).

  D0b  RNG policy (num-rngs 2, RNG 0 pinned): M2S5 seeds 0-9 reproduced (every PCAP and log hash)
  N-rng the same without pinning: seed set 1 must differ (gate sensitivity)
  D0c  ConstantDriftOscillator 0 ppm / 1 ps on GM and slave = IdealOscillator (5GS seed 0, unit):
       every PCAP and log hash, and every slave clock / gPTP vector value
  D0d  tick-reset probe (M2S6U-Q10: 10 ns ticks, StepClockServo): O1 replay with the recorded steps
       reproduces every slave clock and raw-clock sample only when the K7 tick resets are modelled

    gate_m2s6.py <M2-S6 runs> <M2-S5 raw-outputs.sha256> <M2-S5 runs (vectors, for D0c)>
"""
import hashlib
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s6_runs as RR  # noqa: E402
import m2s6_clocks as MC  # noqa: E402
import check_m2s6 as CK  # noqa: E402

RUNS, H5, RUNS5 = sys.argv[1:4]
rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def ref_hashes():
    out = {}
    with open(H5) as fh:
        for line in fh:
            h, p = line.split()
            out[p[2:] if p.startswith("./") else p] = h
    return out


REF = ref_hashes()


def run_files(cfg, rep):
    """Relative paths (as in raw-outputs.sha256) of a run's PCAP and per-frame/engine logs."""
    out = []
    for sub in ("pcap", "m2log"):
        d = os.path.join(RUNS, cfg, sub, f"{cfg}-{rep}")
        if os.path.isdir(d):
            out += [os.path.join(cfg, sub, f"{cfg}-{rep}", f) for f in sorted(os.listdir(d))]
    return out


def compare(cfg, rep, ref_cfg, ref_rep):
    """(n compared, n identical, missing in ref, missing here)"""
    mine = {p.replace(f"{cfg}/", f"{ref_cfg}/", 1).replace(f"{cfg}-{rep}", f"{ref_cfg}-{ref_rep}"): p for p in run_files(cfg, rep)}
    ref = {p for p in REF if p.startswith(f"{ref_cfg}/pcap/{ref_cfg}-{ref_rep}/") or p.startswith(f"{ref_cfg}/m2log/{ref_cfg}-{ref_rep}/")}
    same = sum(1 for k, p in mine.items() if k in REF and REF[k] == sha(os.path.join(RUNS, p)))
    return len(ref), same, len(ref - set(mine)), len(set(mine) - ref)


def main():
    # D0b
    tot = same = miss = extra = 0
    for rep in range(10):
        n, s, m, e = compare("M2S6-d0-rng", rep, "M2S5", rep)
        tot, same, miss, extra = tot + n, same + s, miss + m, extra + e
    add("D0b RNG policy", f"M2S6-d0-rng seeds 0-9 (num-rngs 2, seed-0-mt pinned, oscillators on RNG 1): "
        f"{same}/{tot} PCAP/log hashes identical to M2S5 seeds 0-9", same == tot and tot > 0 and not miss and not extra,
        f"missing {miss}, extra {extra}")
    n, s, m, e = compare("M2S6-d0-rngUnpinned", 1, "M2S5", 1)
    add("N-rng sensitivity", f"M2S6-d0-rngUnpinned seed set 1 (RNG 0 not pinned): {n - s}/{n} PCAP/log hashes differ from M2S5-1 "
        "(the gate detects a changed RNG 0 stream)", s < n and n > 0)
    # D0c
    for cfg, ref, unit in (("M2S6-d0-osc0", "M2S5", False), ("M2S6U-d0-osc0", "M2S5U-hold", True)):
        n, s, m, e = compare(cfg, 0, ref, 0)
        add("D0c 0 ppm / 1 ps oscillator", f"{cfg}-0: {s}/{n} PCAP/log hashes identical to {ref}-0", s == n and n > 0 and not m and not e,
            f"missing {m}, extra {e}")
        net = "M2S5ChainTest" if unit else "M1Bridge"
        sl = "slave" if unit else "talker"
        a = RR.read_vectors(os.path.join(RUNS, cfg, cfg, "0.vec"))
        b = RR.read_vectors(os.path.join(RUNS5, ref, ref, "0.vec"))
        keys = [(f"{net}.{sl}.clock", "timeChanged:vector"), (f"{net}.{sl}.clock", "oscillatorCompensationChanged:vector"),
                (f"{net}.{sl}.gptp", "pdelay:vector"), (f"{net}.{sl}.gptp", "gmRateRatio:vector"),
                (f"{net}.{sl}.gptp", "neighborRateRatio:vector")]
        bad = [k[1] for k in keys if a.get(k) != b.get(k)]
        cnt = sum(len(b.get(k, [])) for k in keys)
        add("D0c 0 ppm / 1 ps oscillator", f"{cfg}-0: slave clock, compensation, pdelay, gmRateRatio, neighborRateRatio vectors "
            f"identical to {ref}-0 ({cnt} values)", not bad and cnt > 0, str(bad))
    # D0d
    R = RR.Run(RUNS, "M2S6U-Q10", 0)
    steps = CK.recorded_steps(R)
    snc = CK.slave_clocks(R, steps)
    gnc = CK.gm_clocks(R)
    resets = [s for s in snc.steps if s[4]]
    phases = [c[2] for c in snc.osc.changes if c[1] == "reset"]
    rows_before = len(CK.rows)
    CK.k_rows(R, gnc, snc, "M2S6U-Q10-0 (replay of the recorded steps)")
    k_ok = all(r[2] for r in CK.rows[rows_before:])
    add("D0d tick-reset probe", f"M2S6U-Q10-0 (10 ns, StepClockServo): O1 with K7 tick resets, replaying the {len(steps)} recorded steps, "
        f"reproduces every GM, slave and slave raw clock sample; {len(resets)} of {len(steps)} steps reset the tick phase "
        f"(elapsed phase {min(phases) if phases else 0}..{max(phases) if phases else 0} ps)", k_ok and len(resets) > 0,
        "; ".join(f"{r[1]}: {r[3]}" for r in CK.rows[rows_before:] if not r[2]))

    # without the reset model, the raw clock replay must fail (the effect is real and visible)
    class NoReset(MC.NodeClocks):
        def step(self, t, new_time, ppm, reset=True):
            return super().step(t, new_time, ppm, False)
    nr = NoReset(R.conf["sl"], R.conf["end"], None, R.sln)
    MC.replay(nr, steps)
    fixed, alt = MC.predicted_samples(nr, nr.U, True)
    ok_u, n_u, bad_u = MC.compare_samples(R.vecv(f"{R.sln}.clock.underlyingClock", "timeChanged:vector"), fixed, alt)
    add("D0d tick-reset probe", "the same replay WITHOUT tick resets does not reproduce the recorded raw-clock samples "
        f"(K7 is real; {len(bad_u)}+ mismatching sample times shown)", not ok_u, str(bad_u[:2]))
    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {check}: {detail}" + (f" -- {extra}" if extra else ""))
    print(f"OVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
