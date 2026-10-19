#!/usr/bin/env python3
"""M2-S6 checker (migration/m2-s6-design.md rev. 2, section 6.2): rows K (clocks), R (rate ratios), S
(slave reproduction), E (error decomposition and closure), P (Pdelay), T (TT clocks), H (hypotheses,
reported), W (network conditions, reported), X (statistics, reported), N (negative controls).

    check_m2s6.py <runs dir>      checks every M2-S6 config whose runs are present
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s6_runs as RR  # noqa: E402
import m2s6_clocks as MC  # noqa: E402
import inet_model as M  # noqa: E402

NS = RR.NS
rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def fmt_ps(p):
    return f"{p / NS:.3f} ns"


# ---------------------------------------------------------------------------------------
# rows K: clocks (O1) against every recorded sample
def gm_clocks(R):
    c = R.conf
    nc = MC.NodeClocks(c["gm"], c["end"], R.vecv(f"{R.gmn}.clock.oscillator", "driftRateChanged:vector"), R.gmn)
    MC.replay(nc)
    return nc


def recorded_steps(R):
    """[(t, new, ppm)] of the slave's setClockTime calls, from the recorded vectors (replay mode:
    gate D0d; stage A free-running clocks have none). new = last timeChanged value at that time."""
    comp = R.vecv(f"{R.sln}.clock", "oscillatorCompensationChanged:vector")[1:]
    tc = R.vecv(f"{R.sln}.clock", "timeChanged:vector")
    last = {}
    for t, v in tc:
        last[t] = v
    out = []
    for t, v in comp:
        out.append((t, M_ps(last[t]), float(v)))
    return out


def M_ps(v):
    """A recorded clock value (double of ps * 1e-12, %.17g) back to integer ps (exact: |v| < 2^53 ps)."""
    p = round(float(v) * 1e12)
    assert MC.dbl(p) == float(v), v
    return p


def slave_clocks(R, steps):
    c = R.conf
    nc = MC.NodeClocks(c["sl"], c["end"], R.vecv(f"{R.sln}.clock.oscillator", "driftRateChanged:vector"), R.sln)
    MC.replay(nc, steps)
    return nc


def k_rows(R, gnc, snc, tag):
    c = R.conf
    for nc, mod, emit_c, emit_u in ((gnc, R.gmn, True, False), (snc, R.sln, True, True)):
        for clk, sub, emit in ((nc.C, "clock", emit_c), (nc.U, "clock.underlyingClock", emit_u)):
            fixed, alt = MC.predicted_samples(nc, clk, emit)
            ok, n, bad = MC.compare_samples(R.vecv(f"{mod}.{sub}", "timeChanged:vector"), fixed, alt)
            add(f"K {tag}", f"{mod}.{sub} timeChanged: every recorded sample = O1 ({n} samples; "
                f"{len(nc.osc.changes)} oscillator changes, {sum(1 for s in nc.steps if s[4])} tick resets)", ok, str(bad) if not ok else "")
        ok, n, bad = MC.compare_drift(R.vecv(f"{mod}.clock.oscillator", "driftRateChanged:vector"), nc)
        o = c[("gm" if nc is gnc else "sl")]["osc"]
        if o["kind"] == "drift" and not o["rw"]:
            add(f"K {tag}", f"{mod} driftRateChanged = schedule ({n} values)", ok, "" if ok else str(bad))
        elif o["rw"]:
            # random walk (RandomDriftOscillator, driftRateChange = uniform(-b, b) every 12.345 ms): the values are
            # replayed from the recording; checked here: change times k x 12.345 ms and every step within [-b, b]
            v = [(t, float(x)) for t, x in R.vecv(f"{mod}.clock.oscillator", "driftRateChanged:vector")]
            ch = v[1:-1]
            times_ok = all(t == (i + 1) * RR.STAIR_DT for i, (t, x) in enumerate(ch)) and v[0] == (0, o["ppm"])
            steps = [b - a for (_, a), (_, b) in zip([v[0]] + ch[:-1], ch)]
            add(f"K {tag}", f"{mod} random-walk drift: {len(ch)} changes at k x 12.345 ms, every step within +-{o['rw']} ppm "
                f"(largest {max(abs(x) for x in steps):.6f} ppm); final drift {v[-1][1]:+.6f} ppm",
                times_ok and all(abs(x) <= o["rw"] * (1 + 1e-12) for x in steps) and len(ch) == 810)
        if nc.ties:
            add(f"K {tag}", f"{mod}: no drift change at the time of a step", False, f"{nc.ties} ties")
    # GM timestamps on the wire: POT = C_G(Sync TX first bit); Pdelay t2 = U_G(Req RX first bit), t3 = U_G(Resp TX first bit)
    sync = {f["seq"]: f for f in RR.C5.sel(R.gm, 2, RR.SYNC)}
    req = {f["seq"]: f for f in RR.C5.sel(R.gm, 1, RR.REQ, dom=None)}
    resp = {f["seq"]: f for f in RR.C5.sel(R.gm, 2, RR.RESP, dom=None)}
    q = [("C", f["start"]) for f in sync.values()] + [("U", f["start"]) for f in req.values()] + [("U", f["start"]) for f in resp.values()]
    attach_reads(gnc, q, R.vecv(f"{R.gmn}.clock.oscillator", "driftRateChanged:vector") if c["gm"]["osc"]["rw"] else None)
    nbad = n = 0
    for f in RR.C5.sel(R.gm, 2, RR.FU):
        g = f["g"]
        if g is None or g["seq"] not in sync:
            continue
        n += 1
        if M.inet_read_timestamp(*g["pot"]) != (gnc_read(gnc, "C", sync[g["seq"]]["start"]) // NS) * NS:
            nbad += 1
    np_ = npbad = 0
    for f in RR.C5.sel(R.gm, 2, RR.RESP, dom=None):
        if f["g"] and f["seq"] in req:
            np_ += 1
            if M.inet_read_timestamp(*f["g"]["ts"]) != (gnc_read(gnc, "U", req[f["seq"]]["start"]) // NS) * NS:
                npbad += 1
    for f in RR.C5.sel(R.gm, 2, RR.RFU, dom=None):
        if f["g"] and f["seq"] in resp:
            np_ += 1
            if M.inet_read_timestamp(*f["g"]["ts"]) != (gnc_read(gnc, "U", resp[f["seq"]]["start"]) // NS) * NS:
                npbad += 1
    add(f"K {tag}", f"GM POT on the wire = C_G(Sync first bit) ({n} Follow_Ups); Pdelay t2/t3 = U_G ({np_} values)",
        nbad == 0 and npbad == 0 and n > 0, f"{nbad} POT, {npbad} t2/t3 mismatches")
    # sign: positive ppm -> POT - s grows
    o = c["gm"]["osc"]
    if o["kind"] == "drift" and not o["stair"] and not o["rw"] and o["ppm"] != 0:
        pots = [(sync[f["g"]["seq"]]["start"], M.inet_read_timestamp(*f["g"]["pot"])) for f in RR.C5.sel(R.gm, 2, RR.FU)
                if f["g"] and f["g"]["seq"] in sync]
        d = (pots[-1][1] - pots[-1][0]) - (pots[0][1] - pots[0][0])
        add(f"K {tag}", f"sign: GM {o['ppm']:+g} ppm -> POT - s changes by {fmt_ps(d)} over the run", (d > 0) == (o["ppm"] > 0))


def gnc_read(nc, which, t):
    return nc.reads[(which, t)]


def attach_reads(nc, queries, drift_vec=None):
    """Fresh O1 pass over the node's drift schedule and steps, reading C or U at every (which, t) of
    `queries` in time order (a read at a step time is taken before the step: INET reads before it
    applies a Follow_Up)."""
    f = MC.NodeClocks(nc.nconf, nc.end, drift_vec, nc.name)
    ev = sorted(set(queries), key=lambda q: (q[1], q[0]))
    steps, si, out = list(nc.steps), 0, {}
    for which, t in ev:
        while si < len(steps) and steps[si][0] < t:
            st = steps[si]
            f.step(st[0], st[2], st[3], True)
            si += 1
        out[(which, t)] = f.read_C(t) if which == "C" else f.read_U(t)
    nc.reads = out
    return out


# ---------------------------------------------------------------------------------------
STAGE_A = ["M2S6U-A1", "M2S6U-A2", "M2S6U-A3", "M2S6U-A4", "M2S6U-A5"]


def main():
    runs = sys.argv[1]
    present = lambda cfg: os.path.isdir(os.path.join(runs, cfg))  # noqa: E731
    for cfg in STAGE_A:
        if not present(cfg):
            continue
        for rep in RR.CLOCKS[cfg]["reps"]:
            R = RR.Run(runs, cfg, rep)
            g = gm_clocks(R)
            s = slave_clocks(R, [])
            k_rows(R, g, s, f"{cfg}-{rep}")
    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {check}: {detail}" + (f" -- {extra}" if extra else ""))
    print(f"OVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
