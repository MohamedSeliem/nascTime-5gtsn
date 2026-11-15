#!/usr/bin/env python3
"""S5-2 tests: per-UE measurements (m2s72_peru), H-ARQ feedback attribution, the adapter's log parser, the E1
capacity-bracketing and selection logic (m2s72_e1sel), the static RNG audit (m2s72_rngaudit, incl. the
OMNeT++-PatternMatcher cross-check fixture) and the fail-closed refusals. Synthetic fixtures only; no simulation, no
raw output. Each negative control (NC-*) must be detected; each positive control (PC-*) must pass."""
import gzip
import os
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s72_e1sel as X  # noqa: E402
import m2s72_peru as P  # noqa: E402
import m2s72_peru_adapter as A  # noqa: E402
import m2s72_rngaudit as RA  # noqa: E402

S, MS, US = P.S, P.MS, P.US
INF = P.INF
TESTS = []


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


# ------------------------------------------------------------------------------------------------ fixtures -------
def flow(t0, T, iv, size):
    """(t, size) every iv ps in [t0, T)"""
    return [(t, size) for t in range(t0, T, iv)]


def obs(k, node, loaded=True, T=12 * S, t0=2 * S, dl_iv=MS, deliver=True, starve_window=None, grow=False, fates=None,
        res=5 * MS, lag=US):
    off = flow(0, T, dl_iv, 1400) if loaded else []
    dlv = [(t + 5 * MS, b) for t, b in off if t + 5 * MS < T] if deliver else []
    if starve_window is not None:
        a, b = starve_window
        dlv = [(t, x) for t, x in dlv if not (a <= t < b)]
    bl = [(t, (t // S) * 1000 if grow else 1400) for t in range(S // 2, T + 1, S // 2)]
    co = []
    for i, t in enumerate(range(0, 10 * S, 125 * MS)):
        f = (fates or {}).get(i, "used")
        co.append({"seq": i, "t_gm": t, "fate": f, "res": res if f == "used" else INF, "lag": lag if f == "used" else INF})
    return {"k": k, "node": node, "T": T, "t0": t0, "loaded_dl": loaded, "loaded_ul": False,
            "dl": {"offered": off, "delivered": dlv, "backlog": bl,
                   "accounting": {"predicted_observed": len(dlv), "destroyed": 0, "inflight": 0, "unexplained": 0,
                                  "observed_not_predicted": 0, "queued_end": 0}},
            "ul": None,
            "mac": {"grants": [(t, 1, 1400) for t, _ in off if t >= t0], "candidate_ttis": [t // MS for t, _ in off], "ineligible": None},
            "harq": {"processes": 16, "inserts": len([t for t, _ in off]), "feedback": 0, "nack": 0, "occupancy": None},
            "gptp": {"cohort": co}, "clock": {"max_e_ns": 12.0 + k, "update_gap_max_ps": 125 * MS, "updates": 80}}


# ------------------------------------------------------------------------------------------------ per-UE ---------
@test("per_ue: exact rates, service ratio, TTI share and gPTP figures on a synthetic loaded UE")
def _():
    m = P.per_ue(obs(0, 2049, dl_iv=MS))
    assert abs(m["dl_offered_bps"] - 1400 * 8 * 1000) < 1e-6, m["dl_offered_bps"]
    # delivered = offered shifted by 5 ms: [2 s, 12 s) still holds 10 000 deliveries (those of [1.995 s, 11.995 s))
    assert abs(m["dl_achieved_bps"] - 10000 * 1400 * 8 / 10) < 1e-6 and m["dl_service_ratio"] == 1.0, m["dl_achieved_bps"]
    o = obs(0, 2049)
    o["dl"]["delivered"] = o["dl"]["delivered"][:-100]               # 100 SDUs short
    assert abs(P.per_ue(o)["dl_service_ratio"] - 9900 / 10000) < 1e-12
    assert m["mac_dl_tti_share"] == 1.0 and m["mac_dl_candidate_not_granted_ttis"] == 0
    assert m["gptp_cohort_n"] == 80 and m["gptp_P_used"] == 1.0 and m["res_p99_ms"] == 5.0 and m["lag_p99_ms"] == US / MS
    assert m["deadline_res_gt_5p5ms"] == 0 and m["overloaded"] is False and m["starvation"]["holds"] == []


@test("per_ue: undelivered Syncs rank as +inf (never dropped) and count against the deadlines")
def _():
    m = P.per_ue(obs(1, 2050, fates={0: "censored", 1: "lost"}))
    assert m["res_max_ms"] == INF and m["gptp_fates"] == {"used": 78, "censored": 1, "lost": 1}
    assert m["deadline_res_gt_5p5ms"] == 2 and m["deadline_lag_gt_sync_interval"] == 2


@test("starvation: NC a 1 s DL window with load but no delivery is ST-dl; PC full service is none")
def _():
    m = P.per_ue(obs(0, 2049, starve_window=(5 * S, 6 * S + 10 * MS)))
    assert "ST-dl" in m["starvation"]["holds"], m["starvation"]
    assert P.per_ue(obs(0, 2049))["starvation"]["holds"] == []


@test("starvation: NC an unloaded UE whose Syncs are all censored in a 1 s window is ST-gptp")
def _():
    m = P.per_ue(obs(3, 2052, loaded=False, fates={i: "censored" for i in range(16, 24)}))
    assert m["starvation"]["holds"] == ["ST-gptp"], m["starvation"]


@test("starvation: NC service ratio below 0.5 is US-dl")
def _():
    o = obs(0, 2049)
    o["dl"]["delivered"] = o["dl"]["delivered"][::3]
    assert "US-dl" in P.per_ue(o)["starvation"]["holds"]


@test("overload per UE: growth AND achieved < offered (accepted rule); growth alone with full service is not; "
      "an unloaded UE is never overloaded; missing backlog is not evaluable")
def _():
    o = obs(0, 2049, grow=True)
    o["dl"]["delivered"] = o["dl"]["delivered"][:-100]
    assert P.per_ue(o)["overloaded"] is True                     # growth and 100 SDUs short
    o2 = obs(0, 2049, grow=True)                                  # growth, achieved == offered in the window
    assert P.per_ue(o2)["overloaded"] is False
    assert P.per_ue(obs(1, 2050, loaded=False, grow=True))["overloaded"] is False
    o3 = obs(0, 2049)
    del o3["dl"]["backlog"]
    assert P.per_ue(o3)["overloaded"] is None


@test("across: per-UE distribution (worst UE, spread with +inf), Jain index, classes; the aggregate is beside it")
def _():
    ms = [P.per_ue(obs(0, 2049)), P.per_ue(obs(1, 2050, fates={3: "lost"})), P.per_ue(obs(2, 2051, starve_window=(4 * S, 5 * S + 10 * MS)))]
    a = P.across(ms)
    # one lost Sync of 80 is more than 1 %: UE 1's p99 residence is +inf and it is the worst UE; the spread is +inf
    assert a["N"] == 3 and a["res_p99_ms"]["max"] == INF and a["res_p99_ms"]["worst_ue"] == 1 and a["res_p99_ms"]["spread"] == INF
    assert a["res_p99_ms"]["min"] == 5.0
    assert a["gptp_P_used"]["worst_ue"] == 1 and a["max_e_ns"]["worst_ue"] == 2
    assert a["starvation_ues"] == {"ST-dl": [2]}
    j = a["jain_dl_service_ratio_loaded"]
    r = [m["dl_service_ratio"] for m in ms]
    assert abs(j - sum(r) ** 2 / (3 * sum(x * x for x in r))) < 1e-12 and j < 1
    assert a["system_dl_offered_bps"] == sum(m["dl_offered_bps"] for m in ms)
    b = P.across([ms[0], P.per_ue(obs(1, 2050))])
    assert b["res_p99_ms"]["spread"] == 0 and b["jain_dl_service_ratio_loaded"] == 1


@test("jain: equal shares 1, one of N served 1/N, undefined for no or zero values")
def _():
    assert P.jain([1, 1, 1, 1]) == 1 and abs(P.jain([1, 0, 0, 0]) - 0.25) < 1e-12
    assert P.jain([]) is None and P.jain([0, 0]) is None


# ------------------------------------------------------------------------------------------ structural rows ------
def rowmap(rs):
    return {(r[0], r[1]): r[2] for r in rs}


@test("PU rows: PC a consistent 3-UE record set passes PU-1..5")
def _():
    o = [obs(k, 2049 + k) for k in range(3)]
    tot = {"dl_grant_bytes": sum(sum(b for _, _, b in x["mac"]["grants"]) for x in o), "harq_inserts": sum(x["harq"]["inserts"] for x in o)}
    rs = P.structural_rows(o, [0, 1, 2], {"a1a": 5, "a1b": 0, "ambiguous": 0, "orphan": 0, "reinsert": 0, "d_star_ps": 5 * MS}, tot)
    assert all(r[2] == "PASS" for r in rs), rs


@test("PU rows: NC missing UE, duplicate node, UNEXPLAINED fate, duplicate fate, destroyed SDU, ambiguous feedback, "
      "grant total mismatch: each fails its row")
def _():
    good = {"a1a": 5, "a1b": 0, "ambiguous": 0, "orphan": 0, "reinsert": 0, "d_star_ps": 5 * MS}
    o = [obs(k, 2049 + k) for k in range(3)]
    tot = {"dl_grant_bytes": sum(sum(b for _, _, b in x["mac"]["grants"]) for x in o), "harq_inserts": None}
    assert rowmap(P.structural_rows(o[:2], [0, 1, 2], good, tot))[("PU-1", "run")] == "FAIL"
    o2 = [obs(0, 2049), obs(1, 2049)]
    assert rowmap(P.structural_rows(o2, [0, 1], good, None))[("PU-1", "run")] == "FAIL"
    o3 = [obs(0, 2049, fates={5: "UNEXPLAINED"})]
    assert rowmap(P.structural_rows(o3, [0], good, None))[("PU-2", "UE 0")] == "FAIL"
    o4 = [obs(0, 2049)]
    o4[0]["gptp"]["cohort"].append(dict(o4[0]["gptp"]["cohort"][0]))
    assert rowmap(P.structural_rows(o4, [0], good, None))[("PU-2", "UE 0")] == "FAIL"
    o5 = [obs(0, 2049)]
    o5[0]["dl"]["accounting"]["destroyed"] = 1
    assert rowmap(P.structural_rows(o5, [0], good, None))[("PU-3", "UE 0")] == "FAIL"
    assert rowmap(P.structural_rows(o, [0, 1, 2], dict(good, ambiguous=1), tot))[("PU-4", "run")] == "FAIL"
    assert rowmap(P.structural_rows(o, [0, 1, 2], dict(good, reinsert=1), tot))[("PU-4", "run")] == "FAIL"
    assert rowmap(P.structural_rows(o, [0, 1, 2], good, dict(tot, dl_grant_bytes=tot["dl_grant_bytes"] + 1)))[("PU-5", "run")] == "FAIL"
    assert rowmap(P.structural_rows(o, [0, 1, 2], None, None))[("PU-4", "run")] == "NOT EVALUATED"


# ------------------------------------------------------------------------------------- H-ARQ attribution ----------
def ins(t, node, p, cw=0):
    return ("ins", t, node, p, cw)


def fb(t, p, res="ACK", cw=0):
    return ("fb", t, p, cw, res)


@test("A-1a: feedback of a process open in one UE only is attributed to it; per-UE counts and delays exact")
def _():
    ev = [ins(0, 2049, 0), ins(0, 2050, 1), fb(5 * MS, 0), fb(5 * MS, 1, "NACK"), ins(MS, 2049, 2), fb(6 * MS, 2)]
    per, s = P.attribute_feedback(ev, 16)
    assert s["a1a"] == 3 and s["ambiguous"] == s["orphan"] == 0 and s["d_star_ps"] == 5 * MS
    assert per[2049]["feedback"] == 2 and per[2050]["nack"] == 1 and per[2049]["delays_ps"] == [5 * MS, 5 * MS]


@test("A-1b: the same process id open in two UEs is resolved by the run's single A-1a delay d*")
def _():
    ev = [ins(0, 2049, 0), fb(5 * MS, 0),                          # A-1a, learns d* = 5 ms
          ins(10 * MS, 2049, 3), ins(11 * MS, 2050, 3), fb(15 * MS, 3), fb(16 * MS, 3)]
    per, s = P.attribute_feedback(ev, 16)
    assert s["a1b"] == 1 and s["a1a"] == 2 and s["ambiguous"] == 0, s     # the second becomes A-1a once the first closes
    assert per[2049]["feedback"] == 2 and per[2050]["feedback"] == 1


@test("NC A-1: both candidates exactly d* old -> AMBIGUOUS, per-UE occupancy withheld (NOT EVALUATED, never guessed)")
def _():
    ev = [ins(0, 2049, 0), fb(5 * MS, 0), ins(10 * MS, 2049, 3), ins(10 * MS, 2050, 3), fb(15 * MS, 3), fb(15 * MS, 3)]
    per, s = P.attribute_feedback(ev, 16)
    assert s["ambiguous"] == 2 and per[2049]["occupancy"] is None and per[2050]["occupancy"] is None


@test("NC A-1: a feedback without an open process is ORPHAN; an insert into an open process is RE-INSERT")
def _():
    per, s = P.attribute_feedback([ins(0, 2049, 0), fb(5 * MS, 0), fb(6 * MS, 0)], 16)
    assert s["orphan"] == 1 and per[2049]["occupancy"] is None
    per, s = P.attribute_feedback([ins(0, 2049, 0), ins(MS, 2049, 0), fb(5 * MS, 0)], 16)
    assert s["reinsert"] == 1 and per[2049]["occupancy"] is None


@test("occupancy: log order (insert then feedback in one TTI peaks above the start count) and carried through "
      "TTIs without events; all-busy TTIs counted at the configured process number")
def _():
    ev = [ins(0, 2049, 0), ins(0, 2049, 1), ins(MS, 2049, 2), ins(MS, 2049, 3), ins(MS, 2049, 4),
          fb(5 * MS, 0), ins(5 * MS + 1, 2049, 0), fb(6 * MS, 1)]
    per, s = P.attribute_feedback(ev, 5, (0, 8 * MS))
    oc = per[2049]["occupancy"]
    # TTI 0: 0 -> 2; TTI 1: 2 -> 5; TTIs 2..4: 5 (no event, carried); TTI 5: 5 -> 4 -> 5; TTI 6: 5 -> 4; TTI 7: 4
    assert oc["ttis"] == 8 and oc["busy_at_tti_start_hist"] == {0: 1, 2: 1, 5: 5, 4: 1}, oc
    assert oc["peak_within_tti_hist"] == {2: 1, 5: 6, 4: 1} and oc["max_peak"] == 5 and oc["ttis_all_busy_at_peak"] == 6, oc
    # log order: an insert before a feedback inside one TTI raises the peak above both the start and end counts
    per, s = P.attribute_feedback([ins(0, 2049, 0), ins(5 * MS, 2049, 1), fb(5 * MS, 0)], 16, (5 * MS, 6 * MS))
    oc = per[2049]["occupancy"]
    assert oc["busy_at_tti_start_hist"] == {1: 1} and oc["peak_within_tti_hist"] == {2: 1}, oc


# ------------------------------------------------------------------------------------- adapter log parser ---------
@test("adapter: harq_events reads the gNB MAC lines in log order, exact ps, other modules ignored")
def _():
    d = tempfile.mkdtemp()
    p = os.path.join(d, "run.log.gz")
    lines = ["1.000000000001|M2S72Bridge.gnb1.cellularNic.mac|H-ARQ TX: new pdu (id 7 ) inserted into process 3 codeword id: 0 for node with id 2050",
             "1.000000000001|M2S72Bridge.ue[0].cellularNic.nrMac|H-ARQ TX: feedback received for process 3 codeword 0 result is ACK",
             "1.005|M2S72Bridge.gnb1.cellularNic.mac|H-ARQ TX: feedback received for process 3 codeword 0 result is NACK",
             "not a log line"]
    with gzip.open(p, "wt") as fh:
        fh.write("\n".join(lines) + "\n")
    ev = A.harq_events(p)
    assert ev == [("ins", S + 1, 2050, 3, 0), ("fb", S + 5 * MS, 3, 0, "NACK")], ev
    assert A.t_ps("0.1") == S // 10 and A.t_ps("12") == 12 * S


# ------------------------------------------------------------------------------------- E1 bracketing --------------
def run_bracket(start, truth, combo=("q0", "sym", 4, 16)):
    """truth: factor -> outcome; drive the bracket to its stop and return it"""
    b = X.Bracket(combo, start)
    while b.next_factor() is not None:
        f = b.next_factor()
        b.record(f, truth[f])
    return b


T_ASC = {0.5: "ok", 0.8: "ok", 1.0: "ok", 1.25: "ok", 1.6: "overloaded", 2.0: "overloaded"}


@test("bracket: ascending from 1.0 -> 1.25 ok, 1.6 overloaded, confirmation 2.0 -> (1.25, 1.6); 4 runs")
def _():
    b = run_bracket(1.0, T_ASC)
    assert b.order == [1.0, 1.25, 1.6, 2.0] and b.result() == (1.25, 1.6, "bracketed"), (b.order, b.result())


@test("bracket: descending from an overloaded start, confirmation above f_hi already run; bottom and top edges")
def _():
    t = {0.5: "ok", 0.8: "starved", 1.0: "overloaded", 1.25: "overloaded", 1.6: "overloaded", 2.0: "overloaded"}
    b = run_bracket(1.0, t)
    assert b.order == [1.0, 0.8, 0.5] and b.result() == (0.5, 0.8, "bracketed"), (b.order, b.result())
    b = run_bracket(1.0, {f: "overloaded" for f in X.LADDER})
    assert b.result() == (None, 0.5, "below ladder")
    b = run_bracket(1.0, {f: "ok" for f in X.LADDER})
    assert b.result() == (2.0, None, "above ladder (not extrapolated)") and b.order == [1.0, 1.25, 1.6, 2.0]


@test("bracket: NC a confirmation run that is ok above an overloaded factor is NON-MONOTONE (no f_lo); "
      "an invalid run stops the bracket")
def _():
    t = {**T_ASC, 2.0: "ok"}
    b = run_bracket(1.0, t)
    assert b.stop == "non-monotone" and b.result()[0] is None
    t = {**T_ASC, 1.25: "invalid"}
    b = run_bracket(1.0, t)
    assert b.stop == "invalid" and b.result()[0] is None


@test("bracket: out-of-order or repeated factors are refused; HARQ5 economy start at the HARQ16 f_lo")
def _():
    b = X.Bracket(("q0", "sym", 4, 5), 1.25)
    for bad in (1.0, 2.0):
        try:
            b.record(bad, "ok")
            raise AssertionError("out-of-order factor accepted")
        except ValueError:
            pass
    b.record(1.25, "ok")
    try:
        b.record(1.25, "ok")
        raise AssertionError("repeated factor accepted")
    except ValueError:
        pass


@test("select: f_E1 = largest ladder factor <= (1 - m) x min f_lo; binding combination; sensitivity; STOP when "
      "a combination has no f_lo or no factor fits")
def _():
    b1 = run_bracket(1.0, T_ASC, ("q0", "sym", 4, 16))                         # f_lo 1.25
    b2 = run_bracket(1.0, {0.5: "ok", 0.8: "ok", 1.0: "ok", 1.25: "overloaded", 1.6: "overloaded", 2.0: "overloaded"},
                     ("qdu", "sym", 8, 16))                                    # f_lo 1.0
    f, bind, why = X.select([b1, b2], 0.20)
    assert f == 0.8 and bind == ("qdu", "sym", 8, 16), (f, bind, why)
    sens = X.sensitivity([b1, b2])
    assert sens[0.10][0] == 0.8 and sens[0.30][0] == 0.5, sens
    b3 = run_bracket(1.0, {f_: "overloaded" for f_ in X.LADDER}, ("q0", "one0", 8, 5))
    assert X.select([b1, b3])[0] is None
    b4 = run_bracket(1.0, {0.5: "ok", 0.8: "overloaded", 1.0: "overloaded", 1.25: "overloaded", 1.6: "x", 2.0: "x"}, ("q0", "one0", 2, 5))
    assert X.select([b4], 0.20) == (None, ("q0", "one0", 2, 5), "no ladder factor <= (1 - 0.2) x 0.5 = 0.4")


@test("classify and verify: outcome classes from across(); V-1..V-4 each detect their failure")
def _():
    ms = [P.per_ue(obs(0, 2049)), P.per_ue(obs(1, 2050))]
    a = P.across(ms)
    assert X.classify(a, True) == "ok" and X.classify(a, False) == "invalid" and X.classify(a, True, "SIM-ABORT") == "invalid"
    assert X.classify(dict(a, overloaded_ues=[1]), True) == "overloaded"
    assert X.classify(dict(a, starvation_ues={"ST-gptp": [1]}), True) == "starved"
    assert X.classify(dict(a, overload_not_evaluable_ues=[0]), True) == "invalid"
    short = obs(0, 2049)
    short["dl"]["delivered"] = short["dl"]["delivered"][:-200]       # 2 % short: V-3 must fail
    ms1 = [P.per_ue(short)]
    v = {c: ok for c, ok, _ in X.verify_run(P.across(ms1), ms1, True)}
    assert v["V-3"] is False and v["V-1"] is True, v
    ms2 = [P.per_ue(obs(0, 2049))]
    v = {c: ok for c, ok, _ in X.verify_run(P.across(ms2), ms2, True)}
    assert v == {"V-1": True, "V-2": True, "V-3": True, "V-4": True}, v
    v = {c: ok for c, ok, _ in X.verify_run(dict(P.across(ms2), overloaded_ues=[0]), ms2, False)}
    assert v["V-1"] is False and v["V-4"] is False


# ------------------------------------------------------------------------------------------- RNG audit -----------
@test("RNG audit: the Python matcher equals OMNeT++ 6.5.0's PatternMatcher on every row of the committed fixture")
def _():
    rows = open(os.path.join(HERE, "fixtures", "omnetpp-pattern-xcheck.tsv")).read().splitlines()
    assert len(rows) >= 4000
    bad = [r for r in rows if RA.match(*r.split("\t")[:2]) != (r.split("\t")[2] == "1")]
    assert not bad, bad[:5]
    assert sum(1 for r in rows if r.endswith("\t1")) > 200


def ents(*kv):
    return [tuple(x.split(" = ", 1)) for x in kv]


@test("RNG audit: seeds (explicit / auto = seed-set x num-rngs + j); first matching rng entry wins; unmapped -> 0")
def _():
    e = ents("*.numUe = 2", "num-rngs = 3", "seed-set = 4", "seed-0-mt = 7", "*.ue[0].cellularNic.**.rng-0 = 2",
             "*.ue[*].cellularNic.**.rng-0 = 1", "**.clock.oscillator.rng-0 = 1")
    num, sd = RA.seeds(e)
    assert num == 3 and sd[0] == (7, "explicit") and sd[1] == (4 * 3 + 1, "auto") and sd[2] == (14, "auto")
    mp = RA.rng_map(e, 2)
    assert mp["ue[0].cellularNic.nrMac"][0] == 2 and mp["ue[1].cellularNic.nrMac"][0] == 1
    assert mp["gnb1.cellularNic.channelModel[0]"][0] == 0 and mp["talker[1].clock.oscillator"][0] == 1


@test("RNG audit: NC an auto-seeded or duplicate-seeded RNG with consumers fails RA-1; NC a non-clock module on a "
      "clock RNG fails RA-2; a TT clock without typename does not exist")
def _():
    e = ents("*.numUe = 1", "num-rngs = 2", "seed-0-mt = 0", "**.clock.oscillator.rng-0 = 1")
    rows, mp, _ = RA.audit(e, 1)
    assert rows[0][1] == "FAIL" and "auto-seeded with consumers [1]" in rows[0][2]
    e = ents("*.numUe = 1", "num-rngs = 2", "seed-0-mt = 5", "seed-1-mt = 5", "**.clock.oscillator.rng-0 = 1")
    assert RA.audit(e, 1)[0][0][1] == "FAIL"
    e = ents("*.numUe = 1", "num-rngs = 2", "seed-0-mt = 0", "seed-1-mt = 1000", "**.clock.oscillator.rng-0 = 1",
             "*.ue[0].cellularNic.nrMac.rng-0 = 1")
    assert RA.audit(e, 1)[0][1][1] == "FAIL"
    assert "dsTt[0].eth[1].trafficConditionerLayer.ttClock" not in RA.rng_map(e, 1)
    e2 = e + [("*.dsTt[*].eth[1].trafficConditionerLayer.ttClock.typename", '"nasctime.m2.TtClock"')]
    assert "dsTt[0].eth[1].trafficConditionerLayer.ttClock" in RA.rng_map(e2, 1)


def cfg_n(n):
    e = [("*.numUe", str(n)), ("num-rngs", str(max(2, 2 * n))), ("seed-0-mt", "${repetition}"), ("seed-1-mt", "100${repetition}")]
    e += [(f"seed-{j}-mt", f"{j}00${{repetition}}") for j in range(2, 2 * n)]
    e += [(f"*.talker[{k}].clock.oscillator.rng-0", str(2 * k)) for k in range(1, 8)]
    e += [("**.clock.oscillator.rng-0", "1")]
    return e


@test("RNG audit RA-4: as configured, UE 0's NIC streams are COUPLED when UEs are added; with the isolation mixin "
      "they are INVARIANT; gNB modules are MULTI-UE; clocks INVARIANT")
def _():
    res = {p: st for p, c, st, *_ in RA.pair(cfg_n(1), 1, cfg_n(4), 4)}
    assert res["ue[0].cellularNic.nrChannelModel[0]"] == "COUPLED" and res["talker[0].clock.oscillator"] == "INVARIANT"
    assert res["gnb1.cellularNic.channelModel[0]"] == "MULTI-UE" and res["listener.app[0].source"] == "NO DRAWS"
    mix = RA.isolation_mixin(8)
    res = {p: st for p, c, st, *_ in RA.pair(RA.with_mixin(cfg_n(1), mix), 1, RA.with_mixin(cfg_n(4), mix), 4)}
    assert all(st in ("INVARIANT", "MULTI-UE", "NO DRAWS") for st in res.values()), res
    assert res["ue[0].cellularNic.nrChannelModel[0]"] == "INVARIANT"
    rows, _, _ = RA.audit(RA.with_mixin(cfg_n(4), mix), 4)
    assert rows[0][1] == "PASS" and "none" in rows[2][2]


@test("RNG audit: NC a source with a random parameter value is a drawing consumer (never assumed inert)")
def _():
    e = cfg_n(2) + [("*.listener.app[3].source.productionInterval", "exponential(1ms)")]
    mp = RA.rng_map(e, 2)
    assert RA.draws(mp["listener.app[3].source"], e, "listener.app[3].source") is True
    assert RA.draws(mp["listener.app[0].source"], e, "listener.app[0].source") is False


# ------------------------------------------------------------------------------------------- refusals -------------
@test("fail-closed: check_m2s72_s5n.py run refuses without S5N_ADAPTER_VALIDATED (before reading anything); "
      "check_m2s72_s5v.py still refuses E0v-N")
def _():
    env = dict(os.environ)
    env.pop("S5N_ADAPTER_VALIDATED", None)
    r = subprocess.run([sys.executable, os.path.join(HERE, "check_m2s72_s5n.py"), "run", "/nonexistent", "M2S72-E0vN-q0-sym-n4-f1", "/nonexistent"],
                       env=env, capture_output=True, text=True)
    assert r.returncode == 2 and "REFUSED" in r.stdout, (r.returncode, r.stdout[-300:], r.stderr[-300:])
    r = subprocess.run([sys.executable, os.path.join(HERE, "check_m2s72_s5v.py"), "run", "/nonexistent", "M2S72-E0vN-q0-sym-n4-f1", "/nonexistent"],
                       capture_output=True, text=True)
    assert r.returncode == 2 and "REFUSED" in r.stdout


def main():
    ok = 0
    for name, f in TESTS:
        try:
            f()
            print(f"PASS | {name}")
            ok += 1
        except Exception as ex:
            import traceback
            print(f"FAIL | {name}: {type(ex).__name__}: {ex}\n{traceback.format_exc()[-800:]}")
    print(f"S5-2 tests: {ok} / {len(TESTS)} PASS")
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
