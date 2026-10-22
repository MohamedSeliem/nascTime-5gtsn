"""M2-S7.1 negative controls and Q3 bound variants (migration/m2-s7.1-design.md rev. 3, section 5).

Run controls (configs M2S71-N-*): each must fail exactly its intended rows, evaluated here with the
same functions as the primary rows. Checker controls (N-replay, N-cohortLate, N-cohortOffByOne,
N-postCohort, N-doubleCount, N-horizonShort): the row logic applied to deliberately wrong inputs
must fail. N-monitor is part of gate M0.
"""
import os
from collections import Counter

import m2s71_lib as L
import gate_m2s71_p0 as G

S, MS = L.S, L.MS
INF = L.INF


def lagvec(a):
    return {s: (a.lag[s], a.res[s], a.outcome[s]) for s in a.cohort_complete()}


def rows(out, add, Analysis, report):
    root = os.path.join(out, "runs")
    have = lambda c: os.path.isdir(os.path.join(root, c))  # noqa: E731

    # --- Q3 bound variants (must pass) and N-bound (must fail)
    import check_m2s71 as K
    for cfg in ("M2S71-qa-idle-B5", "M2S71-qa-idle-B6", "M2S71-q0-idle-B10"):
        if have(cfg):
            a = Analysis(root, cfg, 0)
            n, nf, bad = K.q3_rows([a])
            add(f"Q3 bound variant {cfg}", f"{n} corrected Follow_Ups, {nf} flagged; flags = offline Res > B", n and not bad, str(bad))
    if have("M2S71-N-bound"):
        a = Analysis(root, "M2S71-N-bound", 0)
        b = int(open(os.path.join(root, "M2S71-N-bound.bound")).read().strip().rstrip("ps"))
        mon = {int(r["seq"]): int(r["exceeded"]) for r in a.run.mon if r["event"] == "corrected" and r["exceeded"] != ""}
        flagged = {s for s, e in mon.items() if e}
        offline = {s for s in mon if a.res[s] != INF and a.res[s] > b}
        eq = {s for s in mon if a.res[s] == b}
        add("N-bound (>= instead of >): Q3 must fail", f"bound = an observed residence ({b} ps); flagged {len(flagged)} vs offline {len(offline)}; "
            f"the difference is exactly the Syncs with Res = B ({len(eq)})", flagged != offline and flagged - offline == eq and eq)

    # --- N-noRule: Q0a fails against the dedicated-DRB expectation; Q2 equals Q-0 exactly (paired seeds)
    if have("M2S71-N-noRule") and have("M2S71-q0-idle"):
        q = Counter()
        same, n = 0, 0
        for rep in G.reps_of(root, "M2S71-N-noRule"):
            path = os.path.join(root, "M2S71-N-noRule", "pcap", f"M2S71-N-noRule-{rep}", "M1Bridge.upf.pcapRecorder[0].pcapng")
            for d, qfi, inner in L.C5.n3_inner(path):
                if d == 2 and len(inner) > 14 and inner[12:14] == b"\x88\xf7":
                    q[qfi] += 1
            a, b = Analysis(root, "M2S71-N-noRule", rep), Analysis(root, "M2S71-q0-idle", rep)
            n += 1
            same += lagvec(a) == lagvec(b)
        add("N-noRule: Q0a must fail; Q2 must equal Q-0", f"gPTP QFIs on N3 {dict(q)} (a dedicated-DRB option needs 10); per-pair lag, "
            f"residence and outcome identical to Q-0 in {same}/{n} paired seeds", q and set(q) != {10} and same == n and n)

    # --- N-swap: Q0a must fail (QFIs exchanged); the other rows evaluate the run exactly as they do Q-c
    if have("M2S71-N-swap") and have("M2S71-qc-idle"):
        q = Counter()
        path = os.path.join(root, "M2S71-N-swap", "pcap", "M2S71-N-swap-0", "M1Bridge.upf.pcapRecorder[0].pcapng")
        for d, qfi, inner in L.C5.n3_inner(path):
            if d == 2 and len(inner) > 14 and inner[12:14] == b"\x88\xf7":
                q[(inner[14] & 15, qfi)] += 1
        a, b = Analysis(root, "M2S71-N-swap", 0), Analysis(root, "M2S71-qc-idle", 0)
        verdicts = {}
        for name, x in (("N-swap", a), ("Q-c", b)):
            saved = K.rows[:]
            del K.rows[:]
            for f in (K.q8_rows, K.q1_rows, K.c3_rows, K.q5_rows):
                f([x])
            K.q3_rows([x])
            verdicts[name] = {r[0].replace(" Q-c", ""): r[2] for r in K.rows}
            K.rows[:] = saved
        add("N-swap: Q0a must fail, the other rows unaffected", f"(type, QFI) on N3 {dict(q)} (configured: Sync 10, Follow_Up 11); "
            f"Q8/Q1/C-3/Q5 verdicts on the swapped run {verdicts['N-swap']} = on Q-c {verdicts['Q-c']}",
            q.get((0, 11)) and q.get((8, 10)) and not q.get((0, 10)) and verdicts["N-swap"] == verdicts["Q-c"])

    # --- hold positive control (M2S71-H-hold) and the repaired N-noHold (M2S71-H-noHold), seeds as run
    if have("M2S71-H-hold"):
        reps = G.reps_of(root, "M2S71-H-hold")
        res = [K.q5_run(Analysis(root, "M2S71-H-hold", r)) for r in reps]
        tot = Counter()
        for ok, c, det in res:
            tot.update(c)
        cls, nres, badres = Counter(), 0, []
        for r in reps:
            a = Analysis(root, "M2S71-H-hold", r)
            cls.update(a.outcome[s] for s in a.cohort_complete())
            for x in a.run.R.dslog:
                if x["event"] == "corrected" and int(x["seq"]) in a.res:
                    nres += 1
                    if int(x["Res"]) != a.res[int(x["seq"])]:
                        badres.append((r, int(x["seq"])))
        add("Q5 hold positive control (M2S71-H-hold)", f"{len(reps)} seeds: hold cases (Follow_Up arriving while its Sync is queued) "
            f"{tot['pred']}, holds recorded {tot['rec']}; Q5 exact in every run; residence written into the held Follow_Ups = PCAP "
            f"residence (gate wait included) in {nres - len(badres)}/{nres}; cohort outcomes {dict(cls)}",
            all(ok for ok, c, det in res) and tot["pred"] > 0 and cls.get("used", 0) == sum(cls.values()) and not badres and nres,
            str([d for ok, c, d in res if not ok][:3] + badres[:3]))
    if have("M2S71-H-noHold") and have("M2S71-H-hold"):
        reps = G.reps_of(root, "M2S71-H-noHold")
        res = [K.q5_run(Analysis(root, "M2S71-H-noHold", r)) for r in reps]
        tot = Counter()
        for ok, c, det in res:
            tot.update(c)
        cls = Counter()
        for r in reps:
            a = Analysis(root, "M2S71-H-noHold", r)
            cls.update(a.outcome[s] for s in a.cohort_complete())
        add("N-noHold (repaired, M2S71-H-noHold): Q5 must fail", f"{len(reps)} seeds: hold cases {tot['pred']}, holds recorded {tot['rec']}, "
            f"of the hold-case Follow_Ups discarded (fuNoSync, TEST noHold) {tot['pred_discarded']}; Q5 fails in "
            f"{sum(1 for ok, c, d in res if not ok)}/{len(res)} runs; cohort outcomes {dict(cls)}",
            tot["pred"] > 0 and tot["rec"] == 0 and all(not ok for ok, c, d in res) and tot["pred_discarded"] == tot["pred"])
    # --- the original N-noHold (Q-c idle): reported; no hold case can arise there, so it cannot exercise Q5
    if have("M2S71-N-noHold") and have("M2S71-qc-idle"):
        a, b = Analysis(root, "M2S71-N-noHold", 0), Analysis(root, "M2S71-qc-idle", 0)
        oka, ca, _ = K.q5_run(a)
        okb, cb, _ = K.q5_run(b)
        report.append(f"N-noHold, original scenario (M2S71-N-noHold = Q-c idle, seed 0), superseded by M2S71-H-noHold: hold cases {ca['pred']} "
                      f"(Q-c: {cb['pred']}), holds recorded {ca['rec']}, Follow_Ups arriving before their Sync {ca['early']} (Q-c: {cb['early']}); "
                      f"Q5 verdict {oka} (Q-c: {okb}). With no hold case, disabling the hold changes nothing: the scenario cannot exercise Q5.")

    # --- N-prio: Q-d (UM) under load with inverted priorities must lose the Q-d load expectation
    if have("M2S71-N-prio") and have("M2S71-qdu-load"):
        sa = K.summarize([Analysis(root, "M2S71-N-prio", r) for r in G.reps_of(root, "M2S71-N-prio")])
        sb = K.summarize([Analysis(root, "M2S71-qdu-load", r) for r in G.reps_of(root, "M2S71-qdu-load")])
        add("N-prio: the Q-d load expectation must fail", f"p99 residence under load {K.us(sa['p99_res'])} us inverted vs {K.us(sb['p99_res'])} us; "
            f"P(delivered) {K.fmt_ci(sa['p_deliv'], 'p')} vs {K.fmt_ci(sb['p_deliv'], 'p')}; p99 lag {K.us(sa['p99_lag'])} vs {K.us(sb['p99_lag'])} us",
            (sa["p99_res"], -(sa["p_deliv"][0] or 0)) > (sb["p99_res"], -(sb["p_deliv"][0] or 0)) or sa["p99_lag"] > sb["p99_lag"])

    # --- N-drop: discarding the slowest Follow_Ups must not improve p99 (+inf rule) and must fail eligibility
    if have("M2S71-N-drop") and have("M2S71-q0-idle"):
        a, b = Analysis(root, "M2S71-N-drop", 0), Analysis(root, "M2S71-q0-idle", 0)
        thr = open(os.path.join(root, "M2S71-N-drop.threshold")).read().strip()
        co = a.cohort_complete()
        cls = Counter(a.outcome[s] for s in co)
        pa = L.pct([a.lag[s] for s in co], 0.99)
        pb = L.pct([b.lag[s] for s in b.cohort_complete()], 0.99)
        pd = L.pct([a.lag[s] for s in co if a.lag[s] != INF], 0.99)
        add("N-drop: the +inf rule must not reward discarding slow pairs", f"threshold {thr}: cohort outcomes {dict(cls)}; p99 lag {K.us(pa)} us vs "
            f"Q-0 {K.us(pb)} us (delivered-only p99 would be {K.us(pd)} us: lower, i.e. what the rule prevents); not eligible (late pairs)",
            pa >= pb and cls.get("late", 0) > 0 and pd < pb)

    # --- checker controls
    if have("M2S71-q0-idle"):
        a = Analysis(root, "M2S71-q0-idle", 0)
        d = a.rlc[1]
        viol = 0
        for t, s in d["slots"].items():
            alloc = sum(s["pdus"]) + 2
            need = sum(r + (1 if fresh else 4) for r, fresh in s["before"]) + 2
            if len(s["before"]) >= 2 and alloc < need:     # the mutated ("fixed") demand would exceed the grant
                viol += 1
        add("N-replay: Q0b-1 with one RLC header per PDU in the demand must fail", f"Q-0 idle seed 0: {viol} slots where the grant is below "
            "the mutated demand (the real scheduler never grants less than its demand)", viol > 0)
    if have("M2S71-q0-load"):
        a = Analysis(root, "M2S71-q0-load", 0)
        late = sorted(s for s in a.gm_sync if s in a.ds0_f and a.ds0_f[s]["end"] < L.T_COHORT)
        add("N-cohortLate: C0 must fail", f"cohort from the Follow_Up's DS-TT arrival: {len(late)} pairs vs {len(a.cohort)} by the GM Sync",
            late != a.cohort)
        g = a.run.gm_tx(L.SYNC)
        obo = sorted(s for s, f in g.items() if f["start"] < L.T_COHORT + 125 * MS)
        add("N-cohortOffByOne: C0 must fail", f"boundary 10.125 s: {len(obo)} Syncs vs {len(a.cohort)}", obo != a.cohort)
        pop = set(a.cohort_complete()) | {s for s in a.post if s in a.complete}
        add("N-postCohort: C1 must fail", f"statistics over {len(pop)} pairs instead of the {len(a.cohort_complete())} cohort pairs",
            pop != set(a.cohort_complete()))
        s0 = a.cohort_complete()[0]
        cls = Counter(a.outcome[s] for s in a.cohort_complete())
        cls["lost"] += 1                                   # the same pair counted twice
        add("N-doubleCount: Q8 conservation must fail", f"complete cohort pairs {len(a.cohort_complete())} vs sum of classes {sum(cls.values())} "
            f"(pair {s0} counted twice)", sum(cls.values()) != len(a.cohort_complete()))
    r20 = os.path.join(out, "runs-20s")
    if os.path.isdir(r20):
        # every primary run with a 20 s twin (seed 0), re-evaluated at H = 10.001 s
        ch, per, inf_ok, n = Counter(), Counter(), True, 0
        for cfg in G.run_dirs(r20):
            if cfg not in G.run_dirs(root) or "-sus" in cfg:
                continue
            a = Analysis(root, cfg, 0, horizon=10 * S + 1 * MS)
            b = Analysis(r20, cfg, 0)
            n += 1
            for s in a.cohort_complete():
                if a.outcome[s] != b.outcome[s]:
                    ch[(a.outcome[s], b.outcome[s])] += 1
                    per[cfg] += 1
                    inf_ok = inf_ok and a.lag[s] == INF
        add("N-horizonShort: H0 must detect an insufficient horizon", f"{n} seed-0 runs evaluated at 10.001 s vs 20 s: {sum(ch.values())} cohort "
            f"pairs change class {dict(ch)} in {dict(per)}; each counted +inf at 10.001 s: {inf_ok} (the cohort's last Sync starts at 9.875 s, "
            "so only pairs still unresolved 126 ms later can change)", sum(ch.values()) > 0 and inf_ok)
