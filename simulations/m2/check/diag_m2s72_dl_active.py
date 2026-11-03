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


def dl_sched(path, net=NET):
    gnb = f"{net}.gnb1.cellularNic.mac"
    cand, grants = defaultdict(set), defaultdict(list)       # tti -> {(node, lcid)}; (node, lcid) -> [(tti, granted, limit)]
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
            t = ML.t_ps(p[0]) // MS
            m = re.search(r"(?:QoSAwareScheduler::CID--->|LteMaxCI::schedule computed for cid |LteMaxCI::schedule scheduling connection )" + R_CID, msg)
            if m:
                cand[t].add((int(m.group(1)), int(m.group(2))))
                continue
            m = re.search(r"QoSAwareScheduler::Grant cid=" + R_CID + r" limit=(\d+) granted=(\d+)B", msg)
            if m:
                grants[(int(m.group(1)), int(m.group(2)))].append((t, int(m.group(4)), int(m.group(3))))
                continue
            m = re.search(r"LteMaxCI::schedule granted (\d+) bytes to connection " + R_CID, msg)
            if m:
                grants[(int(m.group(2)), int(m.group(3)))].append((t, int(m.group(1)), None))
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
