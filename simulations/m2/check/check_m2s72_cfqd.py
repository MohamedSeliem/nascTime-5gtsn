#!/usr/bin/env python3
"""M2-S7.2a Q-d uplink scheduler counterfactual (decision 2026-11-03 14:01, Part A; hypothesis, fix and predictions:
results/M2-S7.2a-cfqd-predictions.md, committed before the runs).

    check_m2s72_cfqd.py <CF OUT> <E0 OUT>       -> stdout (m2s72.sh cfqd writes <CF OUT>/cfqd-check.txt)

<CF OUT>/runs holds M2S72-E0-q0-f1 and M2S72-E0-qdu-f1 run on the ISOLATED candidate-fix Simu5G build; <E0 OUT>/runs
holds the same configs on the accepted Simu5G 1.8.0 (the E0 record, re-used, not re-run).
  CF-1  regression: Q-0 (MaxCI, uncapped grants) on the candidate build reproduces E0 exactly (every output)
  CF-2  Q-d UL achieved = UL offered (+-1 %)
  CF-3  Q-d UL grant accounting: per BSR cycle granted <= reported + 4 B per grant TTI; total granted bytes = UE RLC
        PDU bytes +- 1 %
  CF-4  Q-d BSR reports and cycle lengths, UL grant TTIs, UL RB usage (ranges declared)
  CF-5  Q-d (candidate build): every E0 gate row (unchanged checker, gate scoping of the E0 protocol), DL achieved =
        offered (+-1 %), P(used) = 1, Sync residence p99 < 5.5 ms
  CF-6  UE UL backlog conservation (UE RLC TX replay): SDUs = completed + queued; gNB UL deliveries = completed minus
        those still in flight at T_end; UE queue at T_end < 0.5 MB
"""
import gzip
import hashlib
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_e0 as E  # noqa: E402
sys.argv = _argv
import diag_m2s72_qd_ul as D  # noqa: E402
import m2s6_runs as RR  # noqa: E402

S, MS = 10 ** 12, 10 ** 9
NET = "M2S72Bridge"
rows = E.rows
HDR = re.compile(r"^(run|attr|config|itervar|version) ")


def add(row, name, ok, detail):
    rows.append((row, name, "PASS" if ok else "FAIL", detail))


def norm_digest(path, roots, kind):
    h = hashlib.sha256()
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rb") as fh:
        if kind == "raw":
            for chunk in iter(lambda: fh.read(1 << 20), b""):
                h.update(chunk)
            return h.hexdigest()
        for line in fh:
            s = line.decode("utf-8", "replace")
            if kind in ("vec", "sca") and HDR.match(s):
                continue
            if kind == "elog" and s.startswith(("I ", "SB ", "SE ", "RA ", "RR ", "RF ", "GF ", "CF ", "EF ", "GD ", "MD ", "MDF ", "MF ", "CD ", "CDC ", "CDF ")):
                continue                                   # index / snapshot records (byte offsets move with the path length)
            for r in roots:
                s = s.replace(r, "<root>")
            h.update(s.encode())
    return h.hexdigest()


def regression(cf_runs, e0_runs, cfg):
    """every output of cfg in cf_runs equals the E0 one: PCAP / CSV byte for byte; .vec, .sca without the run header,
    result paths normalised; .elog without index / snapshot records, paths normalised; the MAC-log stdout without the
    OMNeT++ banner lines that carry paths; fingerprints equal"""
    def files(base):
        out = {}
        for r_, _, fs in os.walk(os.path.join(base, cfg)):
            for fn in fs:
                p = os.path.join(r_, fn)
                out[os.path.relpath(p, base)] = p
        return out
    a, b = files(e0_runs), files(cf_runs)
    probs, n = [], Counter()
    if set(a) != set(b):
        probs.append(f"file sets differ {sorted(set(a) ^ set(b))[:4]}")
    roots = [os.path.abspath(e0_runs), os.path.abspath(cf_runs)]
    for k in sorted(set(a) & set(b)):
        kind = "vec" if k.endswith(".vec") else "sca" if k.endswith(".sca") else "elog" if k.endswith(".elog") else "skip" if k.endswith(".vci") else "raw"
        if kind == "skip":
            n["vci excluded"] += 1
            continue
        if norm_digest(a[k], roots, kind) != norm_digest(b[k], roots, kind):
            probs.append(f"{k} differs")
        n[kind] += 1
    la, lb = os.path.join(e0_runs, f"run-{cfg}.log.gz"), os.path.join(cf_runs, f"run-{cfg}.log.gz")

    def logdig(p):
        h, fp = hashlib.sha256(), None
        with gzip.open(p, "rt", errors="replace") as fh:
            for line in fh:
                if "Fingerprint" in line:
                    m = re.search(r"calculated: (\S+),", line)
                    fp = m.group(1) if m else None
                if line[:1].isdigit() and "|" in line:     # the MAC / RLC log lines themselves
                    h.update(line.encode())
        return h.hexdigest(), fp
    (da, fa), (db, fb) = logdig(la), logdig(lb)
    if da != db:
        probs.append("MAC-log lines differ")
    if fa is None or fa != fb:
        probs.append(f"fingerprints {fa} vs {fb}")
    add("CF-1", f"{cfg} candidate build vs E0", not probs, f"{dict(n)} compared, MAC-log lines {'identical' if da == db else 'DIFFERENT'}, "
        f"fingerprints {fa} / {fb}" + ("" if not probs else "; DIFFERENT: " + "; ".join(probs[:5])))
    return not probs


def ul_measures(runs, cfg):
    V = RR.read_vectors(os.path.join(runs, cfg, cfg, "0.vec"))
    vec = lambda m, n: [(t, int(float(v))) for t, v in V.get((f"{NET}.{m}", n), [])]  # noqa: E731
    T = 12 * S
    sdu = vec("ue[0].cellularNic.nrRlc-um-1-1.tx", "receivedPacketFromUpperLayer:vector(packetBytes)")
    pdu = vec("ue[0].cellularNic.nrRlc-um-1-1.tx", "sentPduSize:vector")
    gdl = vec("gnb1.cellularNic.rlc-um-2049-1.rx", "sentPacketToUpperLayer:vector(packetBytes)")
    ev = D.ul_events(os.path.join(runs, f"run-{cfg}.log.gz"))
    cy = [c for c in D.cycles(ev, 0, 12000)]
    w = [c for c in cy if c["t"] >= 2000]
    win = lambda xs: [x for x in xs if 2 * S <= x[0] < 12 * S]  # noqa: E731
    ttis = [t for t in ev if 2000 <= t < 12000]
    done, _, left = E.replay_um([x for x in sdu if x[0] <= T], [x for x in pdu if x[0] <= T])
    m = {"ul_offered_Mbps": sum(1 for t in E.csv_frames(os.path.join(runs, cfg, "m2log", f"{cfg}-0", f"{NET}.talker[0].eth[0].measurementLayer.egress.csv")) if t >= 2 * S) * 1400 * 8 / 10 / 1e6,
         "ul_achieved_Mbps": sum(1 for t in E.csv_frames(os.path.join(runs, cfg, "m2log", f"{cfg}-0", f"{NET}.listener.eth[0].measurementLayer.ingress.csv")) if t >= 2 * S) * 1400 * 8 / 10 / 1e6,
         "bsr_reports": sum(1 for t in ttis if any(b > 0 for _, b in ev[t]["bsr"])), "rac": sum(ev[t]["rac"] for t in ttis),
         "cand_ttis": sum(1 for t in ttis if ev[t]["cand"]), "grant_ttis": sum(1 for t in ttis if ev[t]["grants"]),
         "grant_bytes": sum(x for t in ttis for x, _ in ev[t]["grants"]), "ue_rlc_pdu_bytes": sum(b for _, b in win(pdu)),
         "blocks": Counter(b for t in ttis for b in ev[t]["blocks"]),
         "cycle_len": Counter(c["len"] for c in w).most_common(3), "grant_ttis_per_cycle": Counter(c["grant_ttis"] for c in w).most_common(3),
         "over_grant_cycles": [c for c in cy if c["granted"] > c["reported"] + 4 * c["grant_ttis"]],
         "ue_sdus": len([x for x in sdu if x[0] <= T]), "ue_done": len(done), "ue_left": len(left),
         "ue_left_bytes": sum(q["size"] - q["sent"] for q in left), "gnb_ul_delivered": len([x for x in gdl if x[0] <= T]),
         "ue_done_last_10ms": sum(1 for _, _, t in done if t > T - 10 * MS)}
    return m


def main():
    cf, e0 = sys.argv[1], sys.argv[2]
    cfr, e0r = os.path.join(cf, "runs"), os.path.join(e0, "runs")
    P = print
    P("M2-S7.2a Q-d uplink scheduler counterfactual check (predictions results/M2-S7.2a-cfqd-predictions.md)\n")
    r1 = regression(cfr, e0r, "M2S72-E0-q0-f1")
    mq = {("orig", o): ul_measures(e0r, f"M2S72-E0-{o}-f1") for o in ("q0", "qdu")}
    mq.update({("cf", o): ul_measures(cfr, f"M2S72-E0-{o}-f1") for o in ("q0", "qdu")})
    c = mq[("cf", "qdu")]
    add("CF-2", "Q-d UL achieved vs offered (candidate build)", abs(c["ul_achieved_Mbps"] - c["ul_offered_Mbps"]) <= 0.01 * c["ul_offered_Mbps"],
        f"offered {c['ul_offered_Mbps']:.4f} Mb/s, achieved {c['ul_achieved_Mbps']:.4f} Mb/s (original build {mq[('orig', 'qdu')]['ul_achieved_Mbps']:.4f})")
    add("CF-3", "Q-d UL grant accounting (candidate build)",
        not c["over_grant_cycles"] and abs(c["grant_bytes"] - c["ue_rlc_pdu_bytes"]) <= 0.01 * c["ue_rlc_pdu_bytes"],
        f"cycles granted beyond reported + headers {len(c['over_grant_cycles'])} {c['over_grant_cycles'][:2]}; granted {c['grant_bytes']} B vs UE RLC PDU bytes {c['ue_rlc_pdu_bytes']} B")
    add("CF-4", "Q-d BSR, grants, UL RB use (candidate build)",
        50 <= c["bsr_reports"] <= 200 and 7000 <= c["grant_ttis"] <= 8700,
        f"BSR reports {c['bsr_reports']} (declared 50..200), RAC {c['rac']}, cycle length {c['cycle_len']}, grant TTIs {c['grant_ttis']} (declared 7000..8700), "
        f"grant TTIs per cycle {c['grant_ttis_per_cycle']}, UL blocks per grant {dict(c['blocks'])}")
    ok6 = (c["ue_sdus"] == c["ue_done"] + c["ue_left"] and 0 <= c["ue_done"] - c["gnb_ul_delivered"] <= c["ue_done_last_10ms"]
           and c["ue_left_bytes"] < 500000)
    add("CF-6", "Q-d UE UL backlog conservation (candidate build)", ok6,
        f"UE RLC SDUs {c['ue_sdus']} = completed {c['ue_done']} + queued {c['ue_left']} ({c['ue_left_bytes']} B); gNB UL deliveries {c['gnb_ul_delivered']} "
        f"(completed - delivered = {c['ue_done'] - c['gnb_ul_delivered']}, completed in the last 10 ms {c['ue_done_last_10ms']})")
    # CF-5: every E0 gate on the candidate-build Q-d and Q-0 runs (unchanged E0 checker)
    gate_rows = {}
    for o in ("qdu", "q0"):
        s0 = len(rows)
        ev, q, m, fails = E.evaluate(cfr, f"M2S72-E0-{o}-f1", o, 1, os.path.join(cfr, f"run-M2S72-E0-{o}-f1.log.gz"))
        fam = [r for r in rows[s0:] if r[0] not in E.INFO and r[2] in ("PASS", "FAIL")]
        gate_rows[o] = (sum(r[2] == "PASS" for r in fam), sum(r[2] == "FAIL" for r in fam), sorted({r[0] for r in fam if r[2] == "FAIL"}), m)
    p, f_, fam, m = gate_rows["qdu"]
    ok5 = f_ == 0 and abs(m["dl_achieved_rlc_Mbps"] - m["dl_offered_rlc_Mbps"]) <= 0.01 * m["dl_offered_rlc_Mbps"] and m["P_used_cohort"] == 1 \
        and m["res_p99_ms"] is not None and m["res_p99_ms"] < 5.5
    add("CF-5", "Q-d gates, DL and gPTP (candidate build)", ok5,
        f"E0 gate rows {p} PASS / {f_} FAIL {fam}; DL offered {m['dl_offered_rlc_Mbps']:.4f} achieved {m['dl_achieved_rlc_Mbps']:.4f} Mb/s; "
        f"P(used) {m['P_used_cohort']}; Sync residence p99 {m['res_p99_ms']} ms; max |e| {m['max_e_ns']} ns; Q8 {m['q8_frames']}")
    for r in rows:
        if r[0] in ("CF-1", "CF-2", "CF-3", "CF-4", "CF-5", "CF-6") or r[2] == "FAIL":
            P(" | ".join(r)[:1500])
    P(f"\nE0 gate rows on the candidate-build runs: Q-d {gate_rows['qdu'][:3]}, Q-0 {gate_rows['q0'][:3]}")
    P("\nUL measures: build / option | offered | achieved | BSR | RAC | candidate TTIs | grant TTIs | grant bytes | UE RLC PDU bytes | "
      "cycle length | UE queue at T_end (SDUs, B)")
    for (b, o), x in sorted(mq.items()):
        P(f"{b} / {o} | {x['ul_offered_Mbps']:.3f} | {x['ul_achieved_Mbps']:.3f} | {x['bsr_reports']} | {x['rac']} | {x['cand_ttis']} | {x['grant_ttis']} | "
          f"{x['grant_bytes']} | {x['ue_rlc_pdu_bytes']} | {x['cycle_len']} | {x['ue_left']}, {x['ue_left_bytes']}")
    P("\nDL / gPTP (candidate build) vs E0 (original build):")
    keys = ("dl_offered_rlc_Mbps", "dl_achieved_rlc_Mbps", "P_used_cohort", "res_p50_ms", "res_p99_ms", "lag_p99_ms", "max_e_ns", "update_gap_max_ms",
            "mac_harq_deletions", "mac_max_busy_harq", "mac_overflow", "backlog_end_bytes", "load_drb1_backlog_end_bytes")
    import csv
    orig = {r["run"]: r for r in csv.DictReader(open(os.path.join(e0, "e0-metrics.csv")))}
    for o in ("qdu", "q0"):
        m = gate_rows[o][3]
        P(f"  {o}: " + "; ".join(f"{k} {E.fmt(m.get(k))} (E0 {orig[f'M2S72-E0-{o}-f1-0'].get(k)})" for k in keys))
    nf = sum(1 for r in rows if r[0].startswith("CF-") and r[2] == "FAIL")
    P(f"\ncounterfactual rows: {6 - nf} PASS, {nf} FAIL")
    verdict = nf == 0
    P("Counterfactual verdict: " + ("hypothesis SUPPORTED (missing UL grants restored; accounting, timing and delivery gates hold)" if verdict
                                    else "NOT SUPPORTED as predicted (see FAIL rows; evidence preserved; stop)"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
