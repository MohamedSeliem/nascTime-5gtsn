#!/usr/bin/env python3
"""M2-S7.2a Checkpoint 2 revision 2: complete acceptance campaign (review 2026-11-02 16:58; campaign plan
results/M2-S7.2a-cp2r2-campaign.md, declared before the runs).

    check_m2s72_cp2r2.py <OUT>        (m2s72.sh r2 writes <OUT>/cp2r2-check.txt)

Matrix (runs in <OUT>/runs):
  Block B     M2S72-B-<q0|qdu>-<ideal|Ca|Eall>-n<1|2|4>, seeds 0-4 (strict I-2 mandatory; N = 1 = I-5 references)
  I-4 stream  DS-TT 1 TT-clock noise draws, B-<opt>-Eall n2 vs n4, seeds 0-4
  Block H16   M2S72-H16-q0-Ca-n<2|4> (correctness: every Block H row, I-5, H-cov, I-2H; H-nv on n2 seed 0) and
              M2S72-H16-qdu-Ca-n2 (diagnostic: H-cov reported as "H-cov (diagnostic)"), seeds 0-4; strict I-2
              reported there as "I-2 strict (info)"
  EOR         per run and DS-TT, every GM Sync / Follow_Up (domain 0) is delivered to the DS-TT (eth[0]), or
              end-of-run (GM first bit + L_max > T_end, L_max = the largest GM-first-bit -> DS-TT-arrival latency of
              the gPTP frames delivered to that DS-TT in that run), or LOST; PASS iff LOST = 0 (identical rule for
              every configuration)
  controls    the eight Stage 4 controls (check_m2s72_b.PRED, 61b68d4) and the five I-2H controls
              (check_m2s72_i2h.PRED, e3b996f), predictions unchanged
Reported, not gated: per-run RLC PDU accounting of the loaded UE (inferred MAC deletions = gNB RLC PDUs handed to
MAC at t <= T_end - 4 ms that never reached the UE's RLC), case A / B coverage, residence and GM-drift distributions.
"""
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_b as B  # noqa: E402
import check_m2s72_i2h as I  # noqa: E402
sys.argv = _argv
import m2s72_runs as R  # noqa: E402

rows = B.rows
MS = 10 ** 9
INFO = I.INFO


def eor_rows(ev):
    run, T = ev.run, ev.T
    gm = {(f["type"], f["seq"]): f["start"] for f in run.gm if f["dir"] == 2 and f["type"] in (R.SYNC, R.FU) and f["dom"] == 0}
    out = {}
    for k in sorted(ev.views):
        v = ev.views[k]
        got = {(f["type"], f["seq"]): f["end"] for f in v.ds0 if f["dir"] == 1 and f["type"] in (R.SYNC, R.FU) and f["dom"] == 0}
        lat = [got[x] - gm[x] for x in got if x in gm]
        L = max(lat) if lat else None
        miss = sorted(x for x in gm if x not in got)
        eor = [x for x in miss if L is not None and gm[x] + L > T]
        lost = [x for x in miss if x not in eor]
        alien = sorted(x for x in got if x not in gm)
        out[k] = (len(got), eor, lost)
        B.add("EOR", f"{ev.cfg}-{ev.rep} DS-TT {k}", L is not None and not lost and not alien,
              f"GM Sync+Follow_Up {len(gm)}: delivered {len(got)}, end-of-run {len(eor)} {[('S' if t == 0 else 'F') + str(s) for t, s in eor]}, "
              f"LOST {len(lost)}{' ' + str(lost[:6]) if lost else ''}; L_max {L / 1e9 if L else None} ms" + (f"; not from the GM {alien[:4]}" if alien else ""))
    return out


def rlc_accounting(ev, k=1):
    """Loaded UE k: per DRB, gNB RLC TX PDUs handed to MAC vs UE RLC RX PDUs (UM, no ARQ); inferred deletions."""
    node = None
    for (mod, name) in ev.vec:
        m = re.search(r"gnb1\.cellularNic\.rlc-um-(\d+)-(\d+)\.tx$", mod)
        if m and name == "sentPduSize:vector" and int(m.group(1)) == 2049 + k:
            node = 2049 + k
    out = {}
    if node is None:
        return out
    for (mod, name), vals in ev.vec.items():
        m = re.search(rf"gnb1\.cellularNic\.rlc-um-{node}-(\d+)\.tx$", mod)
        if not (m and name == "sentPduSize:vector"):
            continue
        d = m.group(1)
        rx = ev.vec.get((f"{R.NET}.ue[{k}].cellularNic.nrRlc-um-1-{d}.rx", "receivedPacketFromLowerLayer:vector(packetBytes)"), [])
        tx_due = sum(1 for t, _ in vals if t + 4 * MS <= ev.T)
        out[d] = (len(vals), tx_due, len(rx), tx_due - len(rx))
    return out


def main():
    out = sys.argv[1]
    runs = os.path.join(out, "runs")
    summary, refs, cov_all, st_all, rlc_all, per_run = {}, {}, {}, {}, {}, {}

    def mark(name, start):
        fam = [r for r in rows[start:] if r[0] not in INFO]
        per_run[name] = (sum(r[2] == "PASS" for r in fam), sum(r[2] == "FAIL" for r in fam),
                         sorted({r[0] for r in fam if r[2] == "FAIL"}), {r[0]: r[2] for r in rows[start:] if r[0] in INFO})
    # Block B
    for opt in B.OPTS:
        for clk in B.CLKS:
            for n in (1,) + B.NS_B:
                cfg = f"M2S72-B-{opt}-{clk}-n{n}"
                for rep in B.REPS:
                    start = len(rows)
                    if not os.path.isdir(os.path.join(runs, cfg)):
                        B.add("RUN", f"{cfg}-{rep}", False, "run missing")
                        continue
                    ref = refs.get((opt, clk, rep))
                    ev, stats, _ = B.evaluate(runs, cfg, rep, ref=ref if n > 1 else None)
                    eor_rows(ev)
                    if n == 1:
                        refs[(opt, clk, rep)] = ev
                    summary[(cfg, rep)] = stats
                    mark(f"{cfg}-{rep}", start)
    # I-4 stream
    for opt in B.OPTS:
        for rep in B.REPS:
            B.i4_stream(runs, opt, rep)
    # Block H16
    for o, ns in (("q0", (2, 4)), ("qdu", (2,))):
        for n in ns:
            cfg = f"M2S72-H16-{o}-Ca-n{n}"
            for rep in B.REPS:
                start = len(rows)
                if not os.path.isdir(os.path.join(runs, cfg)):
                    B.add("RUN", f"{cfg}-{rep}", False, "run missing")
                    continue
                ev, stats, cov, st, fails, info = I.evaluate_h(runs, cfg, rep, refs[(o, "Ca", rep)], f"M2S72-H-{o}-Ca-n{n}")
                eor_rows(ev)
                summary[(cfg, rep)], cov_all[(cfg, rep)], st_all[(cfg, rep)] = stats, cov, st
                rlc_all[(cfg, rep)] = rlc_accounting(ev)
                if cfg == I.BASE and rep == 0:
                    c01 = cov[(0, 1)]
                    ok = st[1]["hold"] > 0 and st[1]["release"] > 0 and c01["dres"] > 0 and c01["nz"] > 0
                    B.add("H-nv", f"{cfg}-{rep}", ok, f"DS-TT 1 holds {st[1]['hold']}, releases {st[1]['release']}; pair (0,1) Res_0 != Res_1 on "
                          f"{c01['dres']} common Follow_Ups, non-zero GM-drift pair contributions {c01['nz']}")
                mark(f"{cfg}-{rep}", start)
    # controls
    c4 = B.stage4_controls(runs)
    ci, s_mid = I.controls(runs)
    # ---------------------------------------------------------------------------------------------------- report
    P = print
    P("M2-S7.2a Checkpoint 2 revision 2: complete acceptance campaign\n")
    for r in rows:
        P(" | ".join(r))
    by = Counter((r[0], r[2]) for r in rows)
    P("\nrows per family: " + ", ".join(f"{g} {by[(g, 'PASS')]} PASS / {by[(g, 'FAIL')]} FAIL" for g in sorted({r[0] for r in rows})))
    nf = sum(1 for r in rows if r[2] == "FAIL" and r[0] not in INFO)
    ng = sum(1 for r in rows if r[0] not in INFO)
    P(f"gate rows: {ng - nf} PASS, {nf} FAIL (information rows {', '.join(INFO)} reported, not gated)")
    P("\nper run: config-seed | gate rows PASS / FAIL | failing families | information rows")
    for name, (p, f, fam, info) in per_run.items():
        P(f"{name} | {p} / {f} | {fam if fam else '-'} | {info if info else '-'}")
    P("\nsame-Sync (A) / different-Sync (B) samples per pair, all seeds: config | pair | used / common | A | B | excluded")
    agg = defaultdict(Counter)
    for (cfg, rep), st in summary.items():
        for p_, x in st.items():
            a = agg[(cfg, p_)]
            for key in ("n", "A", "B", "common"):
                a[key] += x[key]
            for kk, vv in x["excluded"].items():
                a["x:" + kk] += vv
    for (cfg, p_), a in sorted(agg.items()):
        P(f"{cfg} | {p_} | {a['n']} / {a['common']} | {a['A']} ({100 * a['A'] / max(a['n'], 1):.2f} %) | {a['B']} ({100 * a['B'] / max(a['n'], 1):.2f} %) | "
          f"{ {k[2:]: v for k, v in a.items() if k.startswith('x:')} }")
    P("\nBlock H16 pair (0,1) per run: common FUs | Res_0 != Res_1 | Res_0 - Res_1 range (ns) | s2 differ | non-zero GM-drift | GM-drift range (ns)")
    for (cfg, rep), cov in sorted(cov_all.items()):
        c = cov[(0, 1)]
        P(f"{cfg}-{rep} | {c['com']} | {c['dres']} | {c['res_range']} | {c['ds2']} | {c['nz']} | {c['gm_range']}")
    P("\nBlock H16 DS-TT hold / release / held frames / expired / discarded / corrected / FIFO frames / deviations / end-of-run, per run")
    for (cfg, rep), st in sorted(st_all.items()):
        P(f"{cfg}-{rep} | " + "; ".join(f"DS-TT {k}: {s['hold']}/{s['release']}/{s['held_frames']}/{s['expired']}/{s['discarded']}/{s['corrected']}/"
                                        f"{s['port_frames']}/{s['fifo_dev']}/{len(s['end_of_run'])}" for k, s in sorted(st.items())))
    P("\nBlock H16 UE 1 RLC PDU accounting (inferred; MAC deletions are not recorded in these runs): config-seed | DRB: PDUs to MAC, due by T_end - 4 ms, "
      "received by the UE, due - received")
    for (cfg, rep), acc in sorted(rlc_all.items()):
        P(f"{cfg}-{rep} | " + "; ".join(f"DRB {d}: {a} / {b} / {c} / {e}" for d, (a, b, c, e) in sorted(acc.items())))
    nc = 0
    P("\nnegative controls (each must fail exactly its predicted gate families; predictions 61b68d4 / e3b996f):")
    for name, ok, fails, exp, mine in c4:
        nc += not ok
        P(f"{'PASS' if ok else 'FAIL'} | Stage 4 | {name} | failed {sorted(fails)}, predicted {sorted(exp)}")
    for name, ok, fails, exp, info, mine in ci:
        nc += not ok
        P(f"{'PASS' if ok else 'FAIL'} | I-2H | {name} | failed {sorted(fails)}, predicted {sorted(exp)} | information rows {info}")
    for name, ok, *rest in [(c[0], c[1], c[-1]) for c in c4] + [(c[0], c[1], c[-1]) for c in ci]:
        for r in rest[0]:
            if r[2] == "FAIL":
                P(f"      {name}: " + " | ".join(r)[:400])
    P(f"I-2H control mutations target Follow_Up {s_mid}")
    P(f"controls: {len(c4) + len(ci) - nc} PASS, {nc} FAIL")
    P("Checkpoint 2 revision 2 verdict: " + ("PASS" if nf == 0 and nc == 0 else "FAIL (stop and report)"))
    return 0 if nf == 0 and nc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
