#!/usr/bin/env python3
"""M2-S7.2a Stage 5, increment S5-2: per-run evaluation of N > 1 runs (E0v-N) with per-UE measurements.
Addendum: results/M2-S7.2a-s5-2-addendum.md. check_m2s72_s5v.py (N = 1) is unchanged and still refuses E0v-N.

    check_m2s72_s5n.py adapter-validate <runs> <cfg> <option> <dl UEs> <ul UEs> <records dir>
        READ-ONLY validation of the raw -> per-UE adapter on an existing N > 1 run (the CP2 rev. 2 outputs kept on
        the VM; no new simulation). <dl UEs> / <ul UEs>: the DECLARED loaded UEs, comma-separated, or 'none'.
        Writes adapter-validate-<cfg>.txt and adapter-validate-<cfg>.json; exit 0 only if every PU / AV row PASSes
        (NOT EVALUATED is not a pass), except PU-4 / PU-5 in a run without a gNB MAC log (the CP2 runs): part A only;
        those two rows remain gates of every E0v-N run
    check_m2s72_s5n.py run <runs> <cfg> <records dir>
        one E0v-N run: the accepted Block B / I-2H correctness rows at N, the per-UE Q8 rows, Q8-v, SG-403, MG-1, the
        PU rows, per-UE and across-UE measurements -> <cfg>.check.txt, <cfg>.digest.json. REFUSED (exit 2) unless
        S5N_ADAPTER_VALIDATED names the reviewed adapter validation record (decision S5-2-D2)

Gate scoping for E0v-N (declared in the addendum before any run):
  F0-1  reported as "F0-1 (info)" (no E0v-N configuration is declared loss-free: they bracket saturation)
  EOR   NOT APPLICABLE (bounded latency is not verified per UE in a bracket run; per-UE Q8 censoring governs)
  every other accepted Block B row (F0-2..F0-8, I-1..I-4, M2 / M3 / M3d / M4), I-2H, the per-UE Q8 rows (UE k, the
  strict exclusion attribution), Q8-v, SG-403, MG-1, PU-1..PU-5: gates
  every per-UE and across-UE measurement, starvation and overload class: performance (never a gate)
"""
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_s5v as S5V  # noqa: E402  (unchanged; brings check_m2s72_e0 / _b / _i2h)
sys.argv = _argv
import m2s72_peru as P  # noqa: E402
import m2s72_peru_adapter as A  # noqa: E402
import m2s72s5_lib as LIB  # noqa: E402

E = S5V.E
B = E.B
I = E.I
V = E.V
rows = E.rows


def ue_list(s):
    return [] if s == "none" else [int(x) for x in s.split(",")]


def evaluation(runs, cfg, opt, full):
    """the accepted Block B evaluation of the run at its N with C-a clocks (as E0's evaluate(), N generalised)"""
    run = E.R.Run72(runs, cfg, 0)
    n = run.n
    aopt = S5V.ANALYSIS_OPT[opt]
    base = f"M2S72-H-{aopt}-Ca-n{n}"          # clock configuration lookup only (m2s72_s6.CONF: option, C-a)
    B.BN_BASE[cfg] = base
    T = B.F1.t_end(run)
    ev, stats, _ = B.evaluate(runs, cfg, 0, ref=None, conf_fn=lambda k: V.CONF(base, k, T), full=full)
    return ev, aopt, base, n


def adapter_validate(runs, cfg, opt, dl, ul, recdir):
    start = len(rows)
    ev, aopt, base, n = evaluation(runs, cfg, opt, full=False)
    del rows[start:]
    loaded = {k: (k in dl, k in ul) for k in range(n)}
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    obs, totals, summ = A.observe(ev, mlp, aopt, loaded)
    q8 = [r for r in rows[start:] if r[0].startswith("Q8")]
    del rows[start:]
    vr = A.validate(obs, totals, summ, list(range(n)))
    ms = [P.per_ue(o) for o in obs]
    acr = P.across(ms)
    has_mlog = os.path.exists(mlp)
    # part A (every run): gPTP, RLC and clock evidence; part B (H-ARQ attribution PU-4, grant conservation PU-5) needs
    # the gNB MAC log, which the CP2 rev. 2 runs do not record: there PU-4 / PU-5 are NOT EVALUATED and stay gates of
    # every E0v-N run (which records the MAC log), so an incomplete attribution still fails that run
    def accepted(r):
        if r[2] == "PASS" or (r[0] == "PU-3" and r[2] == "NOT APPLICABLE"):
            return True
        return not has_mlog and r[0] in ("PU-4", "PU-5") and r[2] == "NOT EVALUATED"
    ok = all(accepted(r) for r in vr)
    part = "A and B" if has_mlog else "A only (no gNB MAC log in this run: PU-4 / PU-5 not evaluated)"
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"adapter-validate-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"S5-2 adapter validation on {cfg} (N = {n}, option {opt} analysed as {aopt}; declared DL load {dl}, UL load {ul})\n\n")
        for r in vr:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {r[3]}\n")
        fh.write("\nper-UE Q8 rows (accepted rules, UE k, strict exclusion attribution), reported:\n")
        for r in q8:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {str(r[3])[:300]}\n")
        fh.write(f"\nadapter validation, part {part}: {'PASS' if ok else 'NOT VALIDATED'}\n")
    pj = os.path.join(recdir, f"adapter-validate-{cfg}.json")
    with open(pj, "w") as fh:
        json.dump(S5V.clean({"config": cfg, "per_ue": ms, "across": acr, "harq_attribution": summ, "totals": totals}), fh, indent=1, sort_keys=True)
    LIB.durable([p, pj])
    print(open(p).read().rstrip())
    return 0 if ok else 1


def run_one(runs, cfg, recdir):
    if not os.environ.get("S5N_ADAPTER_VALIDATED"):
        print(f"{cfg}: REFUSED: the per-UE adapter is not validated on real N > 1 output (set S5N_ADAPTER_VALIDATED to "
              "the reviewed adapter-validation record; decision S5-2-D2)")
        return 2, None
    kind, o, h16, f, n_name = S5V.parse_name(cfg)
    if kind != "E0vN":
        print(f"{cfg}: not an E0v-N configuration (N = 1 runs: check_m2s72_s5v.py)")
        return 2, None
    placement = cfg.split("-")[3]
    start = len(rows)
    ev, aopt, base, n = evaluation(runs, cfg, o, full=True)
    if n != n_name:
        raise ValueError(f"{cfg}: numUe {n} in the run, {n_name} in the name")
    I.i2h_rows(ev)
    I.relabel(start, base)
    name = f"{cfg}-0"
    for i in range(start, len(rows)):
        if rows[i][0] == "F0-1":
            rows[i] = ("F0-1 (info)",) + rows[i][1:]
    E.add("EOR", name, E.NA, "E0v-N: bounded latency not verified per UE in a bracket run; per-UE Q8 censoring governs")
    loaded_set = [0] if placement == "one0" else list(range(n))
    loaded = {k: (k in loaded_set, k in loaded_set) for k in range(n)}
    mlp = os.path.join(runs, f"run-{cfg}.log.gz")
    obs, totals, summ = A.observe(ev, mlp, aopt, loaded, nproc=16 if h16 else 5)
    for r in A.validate(obs, totals, summ, list(range(n))):
        rows.append(r)
    mlog = E.ML.MacLog(mlp) if os.path.exists(mlp) else None
    log_text = S5V.read_log(mlp) if os.path.exists(mlp) else ""
    if mlog is None:
        rows.append(("Q8-v", name, E.NE, "no MAC log"))
    else:
        d = mlog.deletions()
        ab = [w for p_, w in LIB.SIM_ABORT if p_.search(log_text)]
        rows.append(("Q8-v", name, "PASS" if not d and not ab else "FAIL",
                     f"deletion lines {len(d)}, abort texts {ab} (no deletion line -> no fate can be attributed to one)"))
    S5V.sg403_row(name, runs, cfg)
    census, removed, ue_unused, occ = S5V.grammar(mlp) if os.path.exists(mlp) else ({}, {}, [], None)
    S5V.mg1_row(name, mlog, removed)
    mine = rows[start:]
    gate_fail = sorted({r[0] for r in mine if r[2] == "FAIL" and r[0] not in E.INFO})
    ne = sorted({r[0] for r in mine if r[2] == E.NE and r[0].startswith(("PU-", "AV-"))})
    ms = [P.per_ue(x) for x in obs]
    acr = P.across(ms)
    digest = {"config": cfg, "kind": kind, "option": o, "placement": placement, "numUe": n, "harq16": h16, "dl_factor": f,
              "correctness": {"gate_failures": gate_fail, "per_ue_not_evaluated": ne, "rows": len(mine)},
              "performance": {"per_ue": ms, "across": acr, "harq_attribution": summ, "totals": totals},
              "mac_grammar_census": [[c, t, v] for (c, t), v in sorted(census.items())]}
    os.makedirs(recdir, exist_ok=True)
    with open(os.path.join(recdir, f"{cfg}.check.txt"), "w") as fh:
        fh.write(f"M2-S7.2a S5-2 per-run check of {cfg} (N = {n}; accepted rows at N + per-UE Q8, Q8-v, SG-403, MG-1, PU / AV)\n\nCORRECTNESS (gates)\n")
        for r in mine:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[1]} | {str(r[3])[:400]}\n")
        verdict = "PASS" if not gate_fail and not ne else "FAIL " + " ".join(gate_fail + [f"NE:{x}" for x in ne])
        fh.write(f"\nper-run verdict: {verdict}\n\nPERFORMANCE (per-UE measurements, never gates): see the digest\n")
    with open(os.path.join(recdir, f"{cfg}.digest.json"), "w") as fh:
        json.dump(S5V.clean(digest), fh, indent=1, sort_keys=True)
    LIB.durable([os.path.join(recdir, f"{cfg}.check.txt"), os.path.join(recdir, f"{cfg}.digest.json")])
    print(f"{cfg}: {verdict}")
    return (0 if not gate_fail and not ne else 1), digest


def main(argv):
    try:
        if len(argv) == 8 and argv[1] == "adapter-validate":
            return adapter_validate(argv[2], argv[3], argv[4], ue_list(argv[5]), ue_list(argv[6]), argv[7])
        if len(argv) == 5 and argv[1] == "run":
            return run_one(argv[2], argv[3], argv[4])[0]
    except Exception as ex:                     # an evaluation that cannot complete is never a PASS
        import traceback
        print(f"EVALUATION ERROR {type(ex).__name__}: {ex}\n{traceback.format_exc()[-1500:]}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
