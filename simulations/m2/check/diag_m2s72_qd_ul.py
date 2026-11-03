#!/usr/bin/env python3
"""M2-S7.2a E0 revision 2, Part B: read-only localisation of the Q-d (UM) uplink starvation (decision 2026-11-03 13:27).

    diag_m2s72_qd_ul.py <E0 runs dir> [factor]      (default factor 1) -> stdout

Q-0 vs Q-d at N = 1, HARQ16, the given DL factor, from the existing E0 outputs only (vectors and the gNB MAC log).
Stages, in path order:
  1. UL offered: talker[0] egress load frames; UE RLC UM TX SDUs (admission) on DRB 1
  2. UE RLC UM TX PDUs = MAC requests (what the UE could send)
  3. BSR as seen by the gNB: UlBacklogRegistry reports (per LCG pseudo-connection), RAC successes
  4. gNB UL scheduling: per TTI whether the LCG connection is a candidate (QoS: "CID--->" line; MaxCI: "computed for
     cid"), grants (bytes, limit), blocks granted in sendGrants
  5. UL received at the listener
and, per BSR cycle (from one BSR report to the next), the grant bytes that followed it versus the bytes reported.
Prints the first stage at which Q-d differs from Q-0, with times. Observations only; the source-code reading that
explains them is in the report and is stated there as such.
"""
import gzip
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s6_runs as RR  # noqa: E402
import m2s72_maclog as ML  # noqa: E402

S, MS = 10 ** 12, 10 ** 9
NET = "M2S72Bridge"
GNB = f"{NET}.gnb1.cellularNic.mac"


def ul_events(path):
    """per TTI: candidate (the UL LCG connection considered by the scheduler), grants [(bytes, limit)], blocks granted,
    BSR reports [(lcid, bytes)], RAC successes"""
    ev = {}
    sec = None
    with gzip.open(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.rstrip("\n").split("|", 2)
            if len(p) < 3 or p[1] != GNB or not p[0][:1].isdigit():
                continue
            msg = p[2]
            if "AmcPilotAuto" in msg or "LteAllocator" in msg or "pushFeedback" in msg:
                continue
            t = ML.t_ps(p[0]) // MS
            if "= UPLINK =" in msg:
                sec = "UL"
            elif "= DOWNLINK =" in msg:
                sec = "DL"
            elif "END UPLINK" in msg or "END DOWNLINK" in msg:
                sec = None
            e = ev.setdefault(t, {"cand": 0, "grants": [], "blocks": [], "bsr": [], "rac": 0})
            m = re.search(r"UlBacklogRegistry: MacCid\(nodeId=\d+, lcid=(\d+)\) reports (\d+) bytes", msg)
            if m:
                e["bsr"].append((int(m.group(1)), int(m.group(2))))
                continue
            if "RAC SUCCESS" in msg:
                e["rac"] += 1
                continue
            if sec != "UL":
                continue
            if "QoSAwareScheduler::CID--->" in msg or "LteMaxCI::schedule computed for cid" in msg:
                e["cand"] += 1
            m = re.search(r"QoSAwareScheduler::Grant cid=\S+ lcid=\d+\) limit=(\d+) granted=(\d+)B", msg)
            if m:
                e["grants"].append((int(m.group(2)), int(m.group(1))))
            m = re.search(r"LteMaxCI::schedule granted (\d+) bytes", msg)
            if m and int(m.group(1)) > 0:
                e["grants"].append((int(m.group(1)), None))
            m = re.search(r"sendGrants Node\[\d+\] - (\d+) blocks to grant", msg)
            if m:
                e["blocks"].append(int(m.group(1)))
    return ev


def cycles(ev, t0, t1):
    """BSR cycles: from a TTI with a non-empty BSR report to the next; the grant bytes and granted TTIs that followed"""
    ts = sorted(t for t, e in ev.items() if any(b > 0 for _, b in e["bsr"]) and t0 <= t < t1)
    out = []
    for i, t in enumerate(ts):
        nxt = ts[i + 1] if i + 1 < len(ts) else t1
        rep = sum(b for _, b in ev[t]["bsr"])
        g = [(tt, sum(x for x, _ in ev[tt]["grants"])) for tt in range(t, nxt) if tt in ev and ev[tt]["grants"]]
        cand = sum(1 for tt in range(t, nxt) if tt in ev and ev[tt]["cand"])
        out.append({"t": t, "reported": rep, "grant_ttis": len(g), "granted": sum(b for _, b in g), "cand_ttis": cand, "len": nxt - t})
    return out


def main():
    runs = sys.argv[1]
    f = sys.argv[2] if len(sys.argv) > 2 else "1"
    P = print
    P(f"M2-S7.2a E0 revision 2, Part B: Q-0 vs Q-d uplink, N = 1, HARQ16, DL factor {f} (read-only, existing E0 outputs)\n")
    res = {}
    for o in ("q0", "qdu"):
        cfg = f"M2S72-E0-{o}-f{f}"
        V = RR.read_vectors(os.path.join(runs, cfg, cfg, "0.vec"))
        vec = lambda m, n: V.get((f"{NET}.{m}", n), [])  # noqa: E731
        sdu = vec("ue[0].cellularNic.nrRlc-um-1-1.tx", "receivedPacketFromUpperLayer:vector(packetBytes)")
        pdu = vec("ue[0].cellularNic.nrRlc-um-1-1.tx", "sentPduSize:vector")
        gnbrx = vec("gnb1.cellularNic.rlc-um-2049-1.rx", "sentPacketToUpperLayer:vector(packetBytes)")
        ev = ul_events(os.path.join(runs, f"run-{cfg}.log.gz"))
        win = lambda xs: [x for x in xs if 2 * S <= x[0] < 12 * S]  # noqa: E731
        ttis = [t for t in ev if 2000 <= t < 12000]
        r = {"ue_rlc_sdus": len(win(sdu)), "ue_rlc_sdu_bytes": sum(float(v) for _, v in win(sdu)),
             "ue_rlc_pdus": len(win(pdu)), "ue_rlc_pdu_bytes": sum(float(v) for _, v in win(pdu)),
             "gnb_rlc_ul_delivered": len(win(gnbrx)),
             "rac": sum(ev[t]["rac"] for t in ttis), "bsr_reports": sum(1 for t in ttis if any(b > 0 for _, b in ev[t]["bsr"])),
             "cand_ttis": sum(1 for t in ttis if ev[t]["cand"]), "grant_ttis": sum(1 for t in ttis if ev[t]["grants"]),
             "grant_bytes": sum(x for t in ttis for x, _ in ev[t]["grants"]),
             "grants_at_limit": sum(1 for t in ttis for x, lim in ev[t]["grants"] if lim is not None and x == lim),
             "grants_with_limit": sum(1 for t in ttis for x, lim in ev[t]["grants"] if lim is not None),
             "blocks": Counter(b for t in ttis for b in ev[t]["blocks"])}
        cy = cycles(ev, 0, 12000)
        r["cycles"] = cy
        r["first_ul"] = sorted(t for t, e in ev.items() if e["grants"] or e["bsr"] or e["rac"])[:1]
        res[o] = r
        P(f"== {cfg} (window [2 s, 12 s))")
        for k, v in r.items():
            if k != "cycles":
                P(f"   {k}: {v}")
        full = [c for c in cy if c["t"] >= 2000]
        P(f"   BSR cycles in window: {len(full)}; cycle length (TTIs) {Counter(c['len'] for c in full).most_common(4)}; "
          f"grant TTIs per cycle {Counter(c['grant_ttis'] for c in full).most_common(4)}; "
          f"candidate TTIs per cycle {Counter(c['cand_ttis'] for c in full).most_common(4)}")
        P("   first 4 BSR cycles: t (ms) | reported bytes | TTIs with a grant | granted bytes | TTIs as candidate | cycle length")
        for c in cy[:4]:
            P(f"      {c['t']} | {c['reported']} | {c['grant_ttis']} | {c['granted']} | {c['cand_ttis']} | {c['len']}")
    a, b = res["q0"], res["qdu"]
    P("\nstages in path order, Q-0 vs Q-d:")
    for k in ("ue_rlc_sdus", "ue_rlc_sdu_bytes", "rac", "bsr_reports", "cand_ttis", "grant_ttis", "grant_bytes", "ue_rlc_pdus", "gnb_rlc_ul_delivered"):
        P(f"   {k}: {a[k]} vs {b[k]}{'' if a[k] == b[k] else '   <-- differs'}")
    ca, cb = a["cycles"], b["cycles"]
    first = None
    for x, y in zip(ca, cb):
        if (x["t"], x["reported"]) != (y["t"], y["reported"]):
            first = ("BSR report", x, y)
            break
        if (x["grant_ttis"], x["granted"]) != (y["grant_ttis"], y["granted"]):
            first = ("grants after the same BSR report", x, y)
            break
    P(f"\nfirst divergence: {first[0] if first else 'none'}")
    if first:
        P(f"   Q-0: {first[1]}")
        P(f"   Q-d: {first[2]}")


if __name__ == "__main__":
    main()
