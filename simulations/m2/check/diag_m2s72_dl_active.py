#!/usr/bin/env python3
"""M2-S7.2a E2 preparation (decision 2026-11-03 20:05, item 4): diagnostic for the unintended deactivation of a
backlogged DL connection (the LteSchedulerEnb.cc:403 mechanism, observed in UL; untested in DL).

    diag_m2s72_dl_active.py <runs dir> <config> [<config> ...]     -> stdout

Per run, per DL connection of each UE (gNB RLC UM TX entity rlc-um-<node>-<drb>, MAC connection lcid = drb):
  backlogged TTIs   TTIs t at whose start the replayed gNB RLC TX queue holds an SDU (arrived before t, its last PDU
                    not sent before t; the existing NR UM replay, check_m2s72_e0.replay_um)
  candidate TTIs    TTIs in which the DL scheduler considers the connection (QoSAwareScheduler "CID--->", LteMaxCI
                    "computed for cid" / "scheduling connection")
  DEACTIVATED       backlogged and not a candidate. Split by whether an SDU of that DRB arrived in [t - 1 ms, t)
                    (a new SDU re-notifies the connection), and whether the connection's last grant before t was
                    capped (granted = limit)
Observation only; a non-zero DEACTIVATED count is reported, never interpreted as loss.

Revision 2 (protocol rev. 2.1, decision 2026-11-03 22:35; the revision-1 fields above are unchanged): every
backlogged TTI is classified (classify()):
  served                candidate and granted > 0 bytes
  CAND-NOT-SERVED       candidate, no grant: legitimate scheduling ineligibility or non-selection (no free H-ARQ
                        process, CQI / codeword / band exclusions, quota, capacity). In Simu5G 1.8.0 these leave the
                        connection in the active set (QoSAwareScheduler logs "CID--->" for every active connection
                        before any eligibility test), so they never appear as "not a candidate"
  CONFIRMED-403         not a candidate, and ALL of: the connection was a candidate in the previous TTI t' and
                        received a CAPPED grant there (granted = limit > 0, QoSAwareScheduler); every TTI from t' + 1
                        to t is backlogged and not a candidate; no SDU of this DRB arrived at the gNB RLC in
                        [grant time at t', start of TTI t] (an arrival re-notifies the MAC and would re-activate the
                        connection). The backlog at t is then residual data that was queued when the capped grant
                        cleared the connection's active flag: the LteSchedulerEnb.cc:403 accounting defect
  UNEXPLAINED           not a candidate and not CONFIRMED-403 (includes: no preceding capped grant, a grant without
                        a limit (MaxCI), an arrival in the window, an arrival at exactly the grant or TTI-start time
                        (log order unavailable: ambiguous), backlog before the first activation). Fail closed
No interarrival-interval assumption is used: the classification is evaluated on every TTI of every run.
"""
import gzip
import os
import re
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_e0 as E  # noqa: E402
sys.argv = _argv
import m2s6_runs as RR  # noqa: E402
import m2s72_maclog as ML  # noqa: E402

S, MS = 10 ** 12, 10 ** 9
NET = "M2S72Bridge"
GNB = f"{NET}.gnb1.cellularNic.mac"
R_CID = r"MacCid\(nodeId=(\d+), lcid=(\d+)\)"


def dl_sched(path, net=NET, with_ps=False):
    gnb = f"{net}.gnb1.cellularNic.mac"
    cand, grants = defaultdict(set), defaultdict(list)       # tti -> {(node, lcid)}; (node, lcid) -> [(tti, granted, limit[, ps])]
    sec = None
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|", 2)
            if len(p) < 3 or p[1] != gnb or not p[0][:1].isdigit():
                continue
            msg = p[2]
            if "AmcPilotAuto" in msg or "LteAllocator" in msg or "pushFeedback" in msg:
                continue
            if "= DOWNLINK =" in msg:
                sec = "DL"
            elif "= UPLINK =" in msg:
                sec = "UL"
            elif "END DOWNLINK" in msg or "END UPLINK" in msg:
                sec = None
            if sec != "DL":
                continue
            tps = ML.t_ps(p[0])
            t = tps // MS
            m = re.search(r"(?:QoSAwareScheduler::CID--->|LteMaxCI::schedule computed for cid |LteMaxCI::schedule scheduling connection )" + R_CID, msg)
            if m:
                cand[t].add((int(m.group(1)), int(m.group(2))))
                continue
            m = re.search(r"QoSAwareScheduler::Grant cid=" + R_CID + r" limit=(\d+) granted=(\d+)B", msg)
            if m:
                grants[(int(m.group(1)), int(m.group(2)))].append((t, int(m.group(4)), int(m.group(3))) + ((tps,) if with_ps else ()))
                continue
            m = re.search(r"LteMaxCI::schedule granted (\d+) bytes to connection " + R_CID, msg)
            if m:
                grants[(int(m.group(2)), int(m.group(3)))].append((t, int(m.group(1)), None) + ((tps,) if with_ps else ()))
    return cand, grants


def analyse(runs, cfg, drop=None):
    """drop: (tti, node, drb) candidate removed in memory (self-test control only)"""
    V = RR.read_vectors(os.path.join(runs, cfg, cfg, "0.vec"))
    T = 12 * S
    cand, grants = dl_sched(os.path.join(runs, f"run-{cfg}.log.gz"))
    if drop is not None:
        cand[drop[0]].discard((drop[1], drop[2]))
    out = []
    for (mod, name), vals in sorted(V.items()):
        m = re.search(r"gnb1\.cellularNic\.rlc-um-(\d+)-(\d+)\.tx$", mod)
        if not (m and name == "receivedPacketFromUpperLayer:vector(packetBytes)"):
            continue
        node, drb = int(m.group(1)), int(m.group(2))
        sdus = [(t, int(float(v))) for t, v in vals if t <= T]
        pdus = [(t, int(float(v))) for t, v in V.get((mod, "sentPduSize:vector"), []) if t <= T]
        done, _, left = E.replay_um(sdus, pdus)
        # completion TTI per SDU (last PDU); queued SDUs never complete
        ev = sorted([(a // MS + 1, +1) for a, _ in sdus] + [(tl // MS + 1, -1) for _, _, tl in done])  # effective from the next TTI start
        arr_tti = {a // MS for a, _ in sdus}
        g = sorted(grants.get((node, drb), []))
        n_back = n_cand = 0
        deact = {"with_arrival": 0, "no_arrival": 0, "after_capped_grant": 0}
        first = []
        q, i, gi, last_g = 0, 0, 0, None
        for t in range(0, 12000):
            while i < len(ev) and ev[i][0] <= t:
                q += ev[i][1]
                i += 1
            while gi < len(g) and g[gi][0] < t:
                last_g = g[gi]
                gi += 1
            c = (node, drb) in cand.get(t, ())
            n_cand += c
            if q > 0:
                n_back += 1
                if not c:
                    deact["with_arrival" if (t - 1) in arr_tti else "no_arrival"] += 1
                    if last_g is not None and last_g[2] is not None and last_g[1] == last_g[2]:
                        deact["after_capped_grant"] += 1
                    if len(first) < 3:
                        first.append(t)
        out.append({"cfg": cfg, "node": node, "drb": drb, "sdus": len(sdus), "backlogged_ttis": n_back, "candidate_ttis": n_cand,
                    "deactivated": sum(deact[k] for k in ("with_arrival", "no_arrival")), **deact, "first_deactivated_ttis": first,
                    "capped_grants": sum(1 for _, gr, lim in g if lim is not None and gr == lim), "grants": len(g), "queued_end": len(left)})
    return out


def classify(backlogged, cand, grants, arrivals, n_tti=12000):
    """pure classification (module docstring, revision 2). backlogged / cand: sets of TTIs; grants: [(tti, granted,
    limit or None, grant time ps)]; arrivals: sorted SDU arrival times (ps). Returns counts and the first TTIs"""
    import bisect
    gby = {}
    for g in grants:
        gby.setdefault(g[0], []).append(g)
    out = {"served": 0, "cand_not_served": 0, "confirmed_403": 0, "unexplained": 0, "first_confirmed": [], "first_unexplained": [],
           "episodes_403": 0}
    ep_start, ep_ok, ep_g = None, False, None
    for t in range(n_tti):
        if t not in backlogged:
            ep_start = None
            continue
        if t in cand:
            ep_start = None
            if any(g[1] > 0 for g in gby.get(t, ())):
                out["served"] += 1
            else:
                out["cand_not_served"] += 1
            continue
        if ep_start is None:                                   # a new not-candidate episode starts at t
            ep_start = t
            prev = gby.get(t - 1, [])
            ep_g = prev[-1] if (t - 1) in cand and prev else None
            ep_ok = (ep_g is not None and ep_g[2] is not None and ep_g[1] > 0 and ep_g[1] == ep_g[2] and (t - 1) in backlogged)
            if ep_ok:
                out["episodes_403"] += 1
        conf = False
        if ep_ok:
            lo, hi = ep_g[3], t * MS                            # no arrival in [grant time, TTI-start] (inclusive: ambiguous order)
            conf = bisect.bisect_left(arrivals, lo) == bisect.bisect_right(arrivals, hi)
            if not conf:
                ep_ok = False                                  # once an arrival should have re-activated, the rest is unexplained
        k = "confirmed_403" if conf else "unexplained"
        out[k] += 1
        if len(out["first_" + ("confirmed" if conf else "unexplained")]) < 3:
            out["first_" + ("confirmed" if conf else "unexplained")].append(t)
    return out


def analyse2(runs, cfg, mut=None):
    """revision-2 classification per DL connection; mut (controls only): {"drop_cand": [(tti, node, drb)],
    "drop_arrivals": (node, drb, lo_ps, hi_ps)} applied in memory"""
    V = RR.read_vectors(os.path.join(runs, cfg, cfg, "0.vec"))
    T = 12 * S
    cand, grants = dl_sched(os.path.join(runs, f"run-{cfg}.log.gz"), with_ps=True)
    for t, nd, dr in (mut or {}).get("drop_cand", []):
        cand[t].discard((nd, dr))
    res = []
    for (mod, name), vals in sorted(V.items()):
        m = re.search(r"gnb1\.cellularNic\.rlc-um-(\d+)-(\d+)\.tx$", mod)
        if not (m and name == "receivedPacketFromUpperLayer:vector(packetBytes)"):
            continue
        node, drb = int(m.group(1)), int(m.group(2))
        sdus = [(t, int(float(v))) for t, v in vals if t <= T]
        pdus = [(t, int(float(v))) for t, v in V.get((mod, "sentPduSize:vector"), []) if t <= T]
        da = (mut or {}).get("drop_arrivals")
        done, _, left = E.replay_um(sdus, pdus)
        arrivals = sorted(a for a, _ in sdus)
        if da and da[0] == node and da[1] == drb:              # remove the arrival evidence only (classification input)
            arrivals = [a for a in arrivals if not (da[2] <= a <= da[3])]
        ev = sorted([(a // MS + 1, +1) for a, _ in sdus] + [(tl // MS + 1, -1) for _, _, tl in done])
        back, q, i = set(), 0, 0
        for t in range(12000):
            while i < len(ev) and ev[i][0] <= t:
                q += ev[i][1]
                i += 1
            if q > 0:
                back.add(t)
        c = {t for t, s in cand.items() if (node, drb) in s}
        r = classify(back, c, grants.get((node, drb), []), arrivals)
        r.update(cfg=cfg, node=node, drb=drb, backlogged_ttis=len(back))
        res.append(r)
    return res


def safeguard(res):
    """protocol rev. 2.1 safeguard: (affected, unexplained) over the connections of one run"""
    return sum(r["confirmed_403"] for r in res), sum(r["unexplained"] for r in res)


def selftest2(runs, cfg):
    """controls of the revision-2 classification (declared in protocol rev. 2.1 before any E2 run):
    SC-1 synthetic CONFIRMED; SC-2 synthetic arrival in the window -> UNEXPLAINED; SC-3 synthetic uncapped grant ->
    UNEXPLAINED; SC-4 synthetic candidate without grant -> CAND-NOT-SERVED (not a deactivation); SC-5 synthetic arrival
    exactly at the TTI start -> UNEXPLAINED (ambiguous); SC-6 synthetic not-candidate with no previous grant ->
    UNEXPLAINED; RC-1 real (E0 Q-d F = 2) unmodified -> 0 confirmed, 0 unexplained; RC-2 real, one candidate removed right
    after a capped grant (arrivals present) -> exactly 1 UNEXPLAINED; RC-3 real, the same TTI with the arrival evidence of
    (grant time, TTI start] removed -> exactly 1 CONFIRMED-403"""
    ok = []
    g = [(10, 7250, 7250, 10 * MS + 5)]
    def chk(label, r, want):
        good = all(r[k] == v for k, v in want.items())
        ok.append(good)
        print(f"{'PASS' if good else 'FAIL'} | {label} | {{{', '.join(f'{k}: {r[k]}' for k in want)}}} (expected {want})")
    back = set(range(10, 14))
    chk("SC-1 capped grant at 10, not candidate 11..13, no arrival", classify(back, {10}, g, [5 * MS]), {"confirmed_403": 3, "unexplained": 0, "served": 1})
    chk("SC-2 as SC-1 with an arrival at 11.5 ms", classify(back, {10}, g, [11 * MS + MS // 2]), {"confirmed_403": 1, "unexplained": 2})
    chk("SC-3 uncapped grant (MaxCI: no limit)", classify(back, {10}, [(10, 7250, None, 10 * MS + 5)], []), {"confirmed_403": 0, "unexplained": 3})
    chk("SC-4 candidate without a grant", classify({10, 11}, {10, 11}, [], []), {"cand_not_served": 2, "confirmed_403": 0, "unexplained": 0})
    chk("SC-5 arrival exactly at the start of TTI 12", classify(back, {10}, g, [12 * MS]), {"confirmed_403": 1, "unexplained": 2})
    chk("SC-6 not candidate, no preceding grant", classify({3, 4}, set(), [], []), {"confirmed_403": 0, "unexplained": 2})
    base = {(r["node"], r["drb"]): r for r in analyse2(runs, cfg)}
    s0 = safeguard(base.values())
    good = s0 == (0, 0)
    ok.append(good)
    print(f"{'PASS' if good else 'FAIL'} | RC-1 {cfg} unmodified: (confirmed, unexplained) = {s0} (expected (0, 0))")
    _, grants = dl_sched(os.path.join(runs, f"run-{cfg}.log.gz"), with_ps=True)
    node, drb = 2049, 1
    gc = next(x for x in grants[(node, drb)] if x[0] > 6000 and x[2] is not None and x[1] == x[2] and x[1] > 0)
    t = gc[0] + 1
    m2 = {(r["node"], r["drb"]): r for r in analyse2(runs, cfg, {"drop_cand": [(t, node, drb)]})}
    good = m2[(node, drb)]["unexplained"] == 1 and m2[(node, drb)]["confirmed_403"] == 0 and m2[(node, drb)]["first_unexplained"] == [t]
    ok.append(good)
    print(f"{'PASS' if good else 'FAIL'} | RC-2 candidate {node}-{drb} removed at TTI {t} after the capped grant at {gc[0]} ({gc[1]} B): "
          f"unexplained {m2[(node, drb)]['unexplained']}, confirmed {m2[(node, drb)]['confirmed_403']} (expected 1, 0)")
    m3 = {(r["node"], r["drb"]): r for r in analyse2(runs, cfg, {"drop_cand": [(t, node, drb)], "drop_arrivals": (node, drb, gc[3], t * MS)})}
    good = m3[(node, drb)]["confirmed_403"] == 1 and m3[(node, drb)]["unexplained"] == 0 and m3[(node, drb)]["first_confirmed"] == [t]
    ok.append(good)
    print(f"{'PASS' if good else 'FAIL'} | RC-3 as RC-2, arrival evidence in [{gc[3]}, {t * MS}] ps removed: confirmed "
          f"{m3[(node, drb)]['confirmed_403']}, unexplained {m3[(node, drb)]['unexplained']} (expected 1, 0)")
    print(f"classification controls: {sum(ok)} / {len(ok)} as declared")
    return all(ok)


def selftest(runs, cfg):
    """control: removing one candidate entry of a backlogged TTI must be reported as exactly one DEACTIVATED TTI"""
    base = {(r["node"], r["drb"]): r for r in analyse(runs, cfg)}
    node, drb = next(k for k, r in base.items() if r["backlogged_ttis"] > 0)
    V = RR.read_vectors(os.path.join(runs, cfg, cfg, "0.vec"))
    cand, _ = dl_sched(os.path.join(runs, f"run-{cfg}.log.gz"))
    t = sorted(tt for tt, c in cand.items() if (node, drb) in c and tt > 6000)[0]
    mut = {(r["node"], r["drb"]): r for r in analyse(runs, cfg, drop=(t, node, drb))}
    ok = mut[(node, drb)]["deactivated"] == base[(node, drb)]["deactivated"] + 1 and mut[(node, drb)]["first_deactivated_ttis"][:1] == [t] \
        and all(mut[k]["deactivated"] == base[k]["deactivated"] for k in base if k != (node, drb))
    print(f"{'PASS' if ok else 'FAIL'} | diagnostic self-test on {cfg}: candidate of {node}-{drb} removed at TTI {t} -> DEACTIVATED "
          f"{base[(node, drb)]['deactivated']} -> {mut[(node, drb)]['deactivated']} (first {mut[(node, drb)]['first_deactivated_ttis']})")
    return ok


def main():
    runs = sys.argv[1]
    if sys.argv[2] == "--selftest":
        sys.exit(0 if selftest(runs, sys.argv[3]) else 1)
    if sys.argv[2] == "--selftest2":
        sys.exit(0 if selftest2(runs, sys.argv[3]) else 1)
    if sys.argv[2] == "--classify":
        bad = 0
        print("revision-2 classification: config | node-DRB | backlogged TTIs | served | CAND-NOT-SERVED | CONFIRMED-403 "
              "(episodes) | UNEXPLAINED | first confirmed | first unexplained")
        for cfg in sys.argv[3:]:
            res = analyse2(runs, cfg)
            for r in res:
                print(f"{cfg} | {r['node']}-{r['drb']} | {r['backlogged_ttis']} | {r['served']} | {r['cand_not_served']} | "
                      f"{r['confirmed_403']} ({r['episodes_403']}) | {r['unexplained']} | {r['first_confirmed']} | {r['first_unexplained']}")
            a, u = safeguard(res)
            print(f"SAFEGUARD {cfg}: " + ("CLEAR" if (a, u) == (0, 0) else f"STOP (CONFIRMED-403 {a}, UNEXPLAINED {u})"))
            bad += (a, u) != (0, 0)
        sys.exit(1 if bad else 0)
    print("DL connection deactivation diagnostic: config | node-DRB | SDUs | backlogged TTIs | candidate TTIs | DEACTIVATED (backlogged, "
          "not candidate): total / with an arrival in the previous ms / without / after a capped grant | first such TTIs | "
          "grants (capped) | queued at T_end")
    for cfg in sys.argv[2:]:
        for r in analyse(runs, cfg):
            print(f"{r['cfg']} | {r['node']}-{r['drb']} | {r['sdus']} | {r['backlogged_ttis']} | {r['candidate_ttis']} | {r['deactivated']} / "
                  f"{r['with_arrival']} / {r['no_arrival']} / {r['after_capped_grant']} | {r['first_deactivated_ttis']} | {r['grants']} ({r['capped_grants']}) | "
                  f"{r['queued_end']}")


if __name__ == "__main__":
    main()
