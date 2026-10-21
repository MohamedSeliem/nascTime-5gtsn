#!/usr/bin/env python3
"""M2-S7.1 checker (migration/m2-s7.1-design.md rev. 3).

    check_m2s71.py phase1 <results/M2-S7.1>   rows on the phase-1 runs, phase-1 selection, phase-2 options
    check_m2s71.py phase2 <results/M2-S7.1>   rows on the phase-2 runs, final selection
    check_m2s71.py final  <results/M2-S7.1>   everything present (phase 1 + 2, accuracy, controls)

Requires gate-P0.txt and gate-Q0b.txt (written by gate_m2s71.py gates) for the same raw outputs:
the Q2 statistics are refused otherwise (design 4, order rule). Independent of the monitor and the
corrector code; see m2s71_lib.py for the definitions. Integer ps. Rows: C1, H0, Q0c, Q1, Q2, Q3, Q4,
Q5, Q6, Q7, Q8, C-3, negative controls; the report holds the distributions and the selection (§7).
"""
import hashlib
import math
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s71_lib as L  # noqa: E402
import gate_m2s71_p0 as G  # noqa: E402

C5 = L.C5
S, MS, NS = L.S, L.MS, L.NS
INF = L.INF
rows, report = [], []
BETWEEN = {}      # accuracy config -> steady-state between-step max |e| (ps), from Q4
INVALID_EV = {"fuInvalidUpstream", "fuNoTag", "tagMismatch", "malformedFU", "unsupportedRepresentation", "associationMismatch",
              "ambiguousSync", "duplicateFU"}
LATE_EV = {"staleFU", "fuNoSync", "holdExpired", "dropLagTest"}
NONEXP = ("q0", "qa", "qb", "qdu", "qda")          # eligible for the recommendation (Q-0p is a reference only)
DEDICATED_NONEXP = ("qa", "qb", "qdu", "qda")
EXP = ("qc", "qc2", "qd2")


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def us(ps):
    return "inf" if ps == INF else ("-" if ps is None else f"{ps / 1e6:.3f}")


# --- per-run analysis --------------------------------------------------------------------------------
class Analysis:
    """cohort / post-cohort pair accounting (Q8), lag and residence (Q2), Q1, Q3, Q5, Q6, Q7 inputs"""

    def __init__(self, root, cfg, rep, horizon=None):
        self.cfg, self.rep = cfg, rep
        self.opt, self.variant, self.harq = L.parse_cfg(cfg)
        self.run = run = L.Run(root, cfg, rep)
        self.H = run.end if horizon is None else horizon
        R = run.R
        ds, df, mode = L.OPTIONS[self.opt][:3]
        self.mode = mode
        gs, gf = run.gm_tx(L.SYNC), run.gm_tx(L.FU)
        self.gm_sync, self.gm_fu = gs, gf
        self.cohort = [s for s in sorted(gs) if gs[s]["start"] < L.T_COHORT]
        self.post = [s for s in sorted(gs) if gs[s]["start"] >= L.T_COHORT]
        self.complete = {s for s in gs if s in gf}
        self.sync_only = sorted(s for s in gs if s not in gf)
        self.fu_only = sorted(s for s in gf if s not in gs)
        # PCAP views (times <= horizon)
        h = self.H
        lim = lambda d: {k: v for k, v in d.items() if v["end"] <= h}  # noqa: E731
        self.nw1 = lim(run.first(R.nw1, 1, L.SYNC))
        self.ds0_s, self.ds0_f = lim(run.first(R.ds0, 1, L.SYNC)), lim(run.first(R.ds0, 1, L.FU))
        self.ds1_s, self.ds1_f = lim(run.first(R.ds1, 2, L.SYNC)), lim(run.first(R.ds1, 2, L.FU))
        self.slave = self.slave_use()
        self.ev = defaultdict(list)
        for r in R.dslog:
            if r.get("seq", "") != "" and int(r["t"]) <= h:
                self.ev[(int(r["msgType"]), int(r["seq"]))].append(r["event"])
        # RLC (UM replay; AM: deliveries only)
        self.rlc = {}
        for drb in sorted({1, ds, df}):
            d = L.rlc(run, self.opt, drb)
            mode_d = "um" if drb == 1 else mode
            d["mode"] = mode_d
            if mode_d == "um":
                done, slots, left = L.replay_um([x for x in d["sdus"] if x[0] <= h], [x for x in d["pdus"] if x[0] <= h])
                matched, unmatched, extra, lostpdu = G.deliveries(done, [x for x in d["deliv"] if x[0] <= h],
                                                                  [x for x in d["rxpdus"] if x[0] <= h], [x for x in d["pdus"] if x[0] <= h],
                                                                  [x for x in d["sdus"] if x[0] <= h], h)
                d.update(done=done, slots=slots, left=left, matched=matched, unmatched=unmatched, lostpdu=lostpdu)
            self.rlc[drb] = d
        self.drb_of = {L.SYNC: ds, L.FU: df}
        self.map_sdus()
        self.classify()

    def compact(self):
        """free the raw inputs once the per-pair quantities exist (a phase check holds hundreds of runs): vectors,
        non-gPTP PCAP records and the per-SDU RLC lists (their size histograms and loss count are kept)"""
        run = self.run
        run.V = None
        for k, v in list(vars(run.R).items()):
            if isinstance(v, list) and v and isinstance(v[0], dict) and "type" in v[0]:
                setattr(run.R, k, [f for f in v if f["type"] in (L.SYNC, L.FU)])
        for d in self.rlc.values():
            d["sdu_sizes"] = Counter(sz for _, sz in d["sdus"])
            d["deliv_sizes"] = Counter(sz for _, sz in d["deliv"])
            d["n_lostpdu"] = len(d.get("lostpdu", []))
            for key in ("sdus", "pdus", "deliv", "rxpdus", "done", "slots", "matched", "unmatched", "lostpdu", "left"):
                d.pop(key, None)
        return self

    def slave_use(self):
        last_sync, out = None, {}
        for f in self.run.R.sl:
            if f["dir"] != 1 or f["type"] not in (L.SYNC, L.FU) or f["end"] > self.H:
                continue
            if f["type"] == L.SYNC:
                last_sync = f["seq"]
            else:
                out.setdefault(f["seq"], "used" if f["seq"] == last_sync else "ignored")
        return out

    def map_sdus(self):
        """gPTP SDUs on their DRB, in GM order (the DRB is FIFO; sizes: Sync < Follow_Up < 110 B < data)"""
        self.sdu_of = {}
        for typ in (L.SYNC, L.FU):
            d = self.rlc[self.drb_of[typ]]
            sizes = sorted({sz for _, sz in d["sdus"] if sz < 110})
            if not sizes:
                continue
            sz = sizes[0] if typ == L.SYNC else sizes[-1]
            if self.drb_of[L.SYNC] != self.drb_of[L.FU] and len(sizes) == 1:
                sz = sizes[0]
            sdus = [x for x in d["sdus"] if x[1] == sz]
            gm = sorted((self.gm_sync if typ == L.SYNC else self.gm_fu).items(), key=lambda kv: kv[1]["start"])
            for i, (seq, _) in enumerate(gm):
                if i < len(sdus):
                    self.sdu_of[(typ, seq)] = sdus[i]

    def frame_fate(self, typ, seq):
        """'delivered' (at the DS-TT eth[0]) | 'destroyed' (a PDU of its SDU never received) | 'held' (still in the
        TX RLC at the horizon) | 'missing' (not explained)"""
        at = (self.ds0_s if typ == L.SYNC else self.ds0_f)
        if seq in at:
            return "delivered"
        sdu = self.sdu_of.get((typ, seq))
        d = self.rlc[self.drb_of[typ]]
        if sdu is None:
            return "missing"
        if d["mode"] == "um":
            if any(q["arr"] == sdu[0] for q in d["left"]):
                return "held"
            st = {u[0]: u[3] for u in d["unmatched"]}.get(sdu[0])
            if st is True:
                return "destroyed"         # one of its own PDUs never received (Q0b replay)
            if st == "inflight":
                return "held"              # replayed delivery after the horizon
            dl = {m[0]: m[3] for m in d["matched"]}.get(sdu[0])
            if dl is not None and dl > self.H - 2 * MS:
                return "held"              # delivered by the RLC, still on the UE -> DS-TT path at the horizon
            return "missing"
        # AM: delivered later or still outstanding at the TX entity
        if sdu[0] > self.H - 10 * MS:
            return "held"
        return "missing"

    def classify(self):
        self.outcome, self.lag, self.res, self.fate = {}, {}, {}, {}
        for s in sorted(self.complete):
            ev = set(self.ev.get((8, s), []))
            use = self.slave.get(s)
            fs, ff = self.frame_fate(L.SYNC, s), self.frame_fate(L.FU, s)
            self.fate[s] = (fs, ff)
            if use == "used":
                o = "used"
            elif use == "ignored":
                o = "ignored"
            elif "destroyed" in (fs, ff):
                o = "lost"
            elif ev & INVALID_EV:
                o = "invalid"
            elif ev & LATE_EV:
                o = "late"
            elif "held" in (fs, ff) or "hold" in ev:
                o = "censored"
            else:
                o = "unexplained"
            self.outcome[s] = o
            # measurements (PCAP)
            if s in self.ds1_s and s in self.nw1:
                self.res[s] = self.ds1_s[s]["start"] - self.nw1[s]["start"]
            else:
                self.res[s] = INF
            if o == "used" and s in self.ds0_f and s in self.ds1_s:
                self.lag[s] = self.ds0_f[s]["end"] - self.ds1_s[s]["start"]
            else:
                self.lag[s] = INF

    def cohort_complete(self):
        return [s for s in self.cohort if s in self.complete]


# --- statistics -----------------------------------------------------------------------------------
def summarize(items):
    """items: [Analysis] of one (option, variant, harq), one per seed. Statistics over the cohort's complete
    pairs (C1), +inf rule (Q8); seeds are the replication unit for the CIs."""
    seeds = []
    pool_lag, pool_res, pool_lag_d = [], [], []
    for a in items:
        co = a.cohort_complete()
        lags = [a.lag[s] for s in co]
        ress = [a.res[s] for s in co]
        used = sum(1 for s in co if a.outcome[s] == "used")
        cen = sum(1 for s in co if a.outcome[s] == "censored")
        seeds.append({"rep": a.rep, "n": len(co), "p_deliv": used / len(co) if co else None, "p99_lag": L.pct(lags, 0.99),
                      "p99_res": L.pct(ress, 0.99), "p50_lag": L.pct(lags, 0.5), "censored": cen,
                      "classes": Counter(a.outcome[s] for s in co)})
        pool_lag += lags
        pool_res += ress
        pool_lag_d += [x for x in lags if x != INF]
    pd, pdh = L.mean_ci([x["p_deliv"] for x in seeds])
    ml, mlh = L.mean_ci([x["p99_lag"] for x in seeds])
    mr, mrh = L.mean_ci([x["p99_res"] for x in seeds])
    fin = sorted(x for x in pool_lag_d)
    return {"seeds": seeds, "p_deliv": (pd, pdh), "p99_lag_seed": (ml, mlh), "p99_res_seed": (mr, mrh),
            "p99_lag": L.pct(pool_lag, 0.99), "p99_res": L.pct(pool_res, 0.99), "p50_lag": L.pct(pool_lag, 0.5),
            "min_lag": fin[0] if fin else None, "max_lag": fin[-1] if fin else None, "p99_lag_deliv": L.pct(pool_lag_d, 0.99),
            "n": len(pool_lag), "censored": sum(x["censored"] for x in seeds),
            "classes": sum((x["classes"] for x in seeds), Counter())}


def fmt_ci(v, unit="us"):
    m, h = v
    if m is None:
        return "-"
    if m == INF:
        return "inf"
    if unit == "p":
        return f"{m:.4f}" + (f" ± {h:.4f}" if h is not None else "")
    return f"{m / 1e6:.3f}" + (f" ± {h / 1e6:.3f}" if h is not None else "") + " ms"


# --- rows ---------------------------------------------------------------------------------------------
def q8_rows(A):
    bad, tot = [], Counter()
    for a in A:
        for part, seqs in (("cohort", a.cohort), ("post", a.post)):
            comp = [s for s in seqs if s in a.complete]
            inc = [s for s in seqs if s not in a.complete]
            cls = Counter(a.outcome[s] for s in comp)
            tot.update({f"{part}:{k}": v for k, v in cls.items()})
            tot[f"{part}:incomplete"] += len(inc)
            if len(seqs) != len(comp) + len(inc) or sum(cls.values()) != len(comp):
                bad.append((a.cfg, a.rep, part, "conservation"))
            if part == "cohort" and cls.get("unexplained"):
                bad.append((a.cfg, a.rep, "unexplained", [s for s in comp if a.outcome[s] == "unexplained"][:4],
                            [a.fate[s] for s in comp if a.outcome[s] == "unexplained"][:2]))
        if a.fu_only:
            tot["fu_without_sync"] += len(a.fu_only)
    add("Q8 frame and pair accounting", f"{len(A)} runs: Syncs = complete pairs + incomplete events, complete pairs = sum of the outcome "
        f"classes, per run, cohort and post-cohort; no unexplained cohort pair; totals {dict(sorted(tot.items()))}", A and not bad, str(bad[:3]))


def q7_rows(A):
    ign = Counter()
    for a in A:
        n = sum(1 for s in a.cohort_complete() if a.outcome[s] == "ignored")
        ign[(a.opt, a.variant, a.harq)] += n
    bad = {k: v for k, v in ign.items() if v and k[0] in NONEXP + EXP}
    add("Q7 Follow_Ups ignored by the slave", f"cohort Follow_Ups that reached the slave after a newer Sync (Gptp.cc:364), per option x variant x "
        f"HARQ: {sum(ign.values())} in total" + (f"; non-zero: {dict(bad)}" if bad else ""), True, "reported; eligibility in the selection")
    return ign


def c3_rows(A):
    """fail-closed: every Follow_Up at the slave was corrected by the DS-TT (count) and follows its Sync"""
    bad = []
    for a in A:
        sl_fu = [f for f in a.run.R.sl if f["dir"] == 1 and f["type"] == L.FU and f["end"] <= a.H]
        corrected = sum(1 for r in a.run.R.dslog if r["event"] == "corrected" and int(r["t"]) <= a.H)
        orphan = [s for s, u in a.slave.items() if u == "ignored" and s not in a.ds1_s]
        if len(sl_fu) > corrected + 1 or orphan:
            bad.append((a.cfg, a.rep, len(sl_fu), corrected, orphan[:3]))
    add("C-3 fail-closed toward the slave", f"{len(A)} runs: every Follow_Up at the slave was corrected by the DS-TT, none without its Sync",
        A and not bad, str(bad[:3]))


def q1_rows(A):
    bad = []
    for a in A:
        ds, df = a.drb_of[L.SYNC], a.drb_of[L.FU]
        sizes = {drb: (d["sdu_sizes"], d["deliv_sizes"]) if "sdu_sizes" in d else
                 (Counter(sz for _, sz in d["sdus"]), Counter(sz for _, sz in d["deliv"])) for drb, d in a.rlc.items()}
        small = {drb: ({sz for sz in tx if sz < 110}, {sz for sz in rx if sz < 110}) for drb, (tx, rx) in sizes.items()}
        want = {1: set(), ds: set(), df: set()}
        if ds == 1:
            want[1] = {"S", "F"}
        else:
            want[ds] = {"S", "F"} if ds == df else {"S"}
            if df != ds:
                want[df] = {"F"}
        for drb, (tx, rx) in small.items():
            n = {len(tx), len(rx)}
            exp = len(want.get(drb, set()))
            if max(n) != exp or (exp == 0 and (tx or rx)):
                bad.append((a.cfg, a.rep, drb, sorted(tx), sorted(rx)))
    add("Q1 gPTP classes only on their DRBs (both RLC sides)", f"{len(A)} runs: Sync/Follow_Up SDUs (the sizes below 110 B) appear only on "
        "the DRBs of the option, at the gNB TX and the UE RX entity", A and not bad, str(bad[:3]))


def q3_rows(A):
    bad, n, nflag = [], 0, 0
    for a in A:
        bound = None
        for line in open(a.run.R.sca_path):
            if "monitor.residenceBound" in line:
                bound = line.split()[-1].strip('"')
                break
        bpath = os.path.join(a.run.root, a.cfg + ".bound")
        b = None
        if os.path.exists(bpath):
            b = int(open(bpath).read().strip().rstrip("ps"))
        elif bound:
            b = int(round(float(bound.rstrip("s").rstrip("m")) * (MS if bound.endswith("ms") else S)))
        if b is None:
            continue
        ge = "-N-bound" in a.cfg
        mon = {int(r["seq"]): int(r["exceeded"]) for r in a.run.mon if r["event"] == "corrected" and r["exceeded"] != ""}
        offline = {s for s in mon if a.res.get(s, INF) != INF and a.res[s] > b}
        flagged = {s for s, e in mon.items() if e == 1}
        n += len(mon)
        nflag += len(flagged)
        if flagged != offline:
            bad.append((a.cfg, a.rep, len(flagged), len(offline)) if not ge else (a.cfg, "N-bound"))
    return n, nflag, bad


def q5_rows(A):
    """Q5 per split option. Hold replay (M2-S5 R-2 method): a Follow_Up is held iff it reaches the DS-TT eth[0] after
    its Sync arrived there and before the Sync's transmission starts on eth[1] (the Sync is queued). A Follow_Up that
    arrives before its Sync reached the DS-TT is not a hold case: TtSyncEgress discards it (fuNoSync, fail-closed);
    those are counted and reported, and the slave must still never see a Follow_Up before its Sync."""
    per = defaultdict(lambda: {"n": 0, "pred": 0, "rec": 0, "early": 0, "nosync": 0, "bad": []})
    for a in A:
        if a.drb_of[L.SYNC] == a.drb_of[L.FU]:
            continue
        c = per[a.opt]
        c["n"] += 1
        pred = sorted(s for s in a.ds0_f if s in a.ds1_s and s in a.ds0_s
                      and a.ds0_s[s]["end"] <= a.ds0_f[s]["end"] < a.ds1_s[s]["start"])
        early = sorted(s for s in a.ds0_f if s in a.ds0_s and a.ds0_f[s]["end"] < a.ds0_s[s]["end"])
        rec = sorted(int(r["seq"]) for r in a.run.R.dslog if r["event"] == "hold" and int(r["t"]) <= a.H)
        nos = {int(r["seq"]) for r in a.run.R.dslog if r["event"] == "fuNoSync" and r.get("seq", "") != "" and int(r["t"]) <= a.H}
        c["pred"] += len(pred)
        c["rec"] += len(rec)
        c["early"] += len(early)
        c["nosync"] += sum(1 for s in early if s in nos)
        before, last = [], set()
        for f in a.run.R.sl:
            if f["dir"] == 1 and f["type"] == L.SYNC:
                last.add(f["seq"])
            if f["dir"] == 1 and f["type"] == L.FU and f["seq"] not in last:
                before.append(f["seq"])
        if pred != rec or before or any(s not in nos for s in early):
            c["bad"].append((a.cfg, a.rep, len(pred), len(rec), before[:3], [s for s in early if s not in nos][:3]))
    for o, c in sorted(per.items(), key=lambda kv: list(L.OPTIONS).index(kv[0])):
        add(f"Q5 order safety {L.LABEL[o]}", f"{c['n']} runs: no Follow_Up before its Sync at the slave; DS-TT holds {c['rec']} = replay "
            f"(Follow_Up arriving while its Sync is queued) {c['pred']}; Follow_Ups arriving before their Sync reached the DS-TT: "
            f"{c['early']}, each discarded fail-closed (fuNoSync: {c['nosync']}) - the hold does not cover them",
            not c["bad"], str(c["bad"][:3]))


def trace_counts(path):
    """M1 O-S3-1 trace parser (unchanged rules): per MAC module, MAC PDUs deleted without a HARQ process and the
    RLC PDUs inside them"""
    ev = defaultdict(Counter)
    last = {}
    for line in open(path, errors="replace"):
        m = re.match(r"([0-9.e-]+) (mac|nrMac) [^|]*\| (.*)", line)
        if not m:
            continue
        mod, msg = m.group(2), m.group(3)
        if "created PDU" in msg:
            last[mod] = int(re.search(r"containing (\d+) SDUs", msg).group(1))
        elif "no available process for this MAC PDU" in msg:
            ev[mod]["mac"] += 1
            ev[mod]["rlc"] += last[mod]
    return ev


def q6_rows(out, A):
    # (a) trace identity: deleted RLC PDUs = RLC PDU deficit (all DRBs, DL from the gNB "mac", UL from the UE "nrMac")
    troot = os.path.join(out, "runs-trace")
    det, ok = [], True
    for cfg in G.run_dirs(troot):
        tr = trace_counts(os.path.join(troot, f"run-{cfg}.log"))
        run = L.Run(troot, cfg, 0)
        defs = {}
        for side, (txn, rxn) in (("DL", ("gnb1.cellularNic.rlc-", "ue[0].cellularNic.nrRlc-")), ("UL", ("ue[0].cellularNic.nrRlc-", "gnb1.cellularNic.rlc-"))):
            txc = sum(len(v) for (m, n), v in run.V.items() if m.startswith("M1Bridge." + txn) and m.endswith(".tx") and n == "sentPduSize:vector")
            rxc = sum(len(v) for (m, n), v in run.V.items() if m.startswith("M1Bridge." + rxn) and m.endswith(".rx")
                      and n == "receivedPacketFromLowerLayer:vector(packetBytes)")
            defs[side] = txc - rxc
        good = defs["DL"] == tr["mac"]["rlc"] and defs["UL"] == tr["nrMac"]["rlc"]
        ok &= good
        det.append(f"{cfg}: deleted MAC PDUs DL {tr['mac']['mac']} / UL {tr['nrMac']['mac']}, RLC PDUs inside DL {tr['mac']['rlc']} / "
                   f"UL {tr['nrMac']['rlc']}, RLC PDU deficit DL {defs['DL']} / UL {defs['UL']}")
    add("Q6 (a) MAC discard model (seed-0 traces)", "; ".join(det), det and ok)
    # (b) per-DRB DL deficits and lost gPTP pairs, 5 vs 16 HARQ (paired seeds)
    agg = defaultdict(Counter)
    for a in A:
        k = (a.opt, a.variant)
        for drb, d in a.rlc.items():
            if d["mode"] == "um":
                agg[(k, a.harq)][f"drb{drb}"] += d["n_lostpdu"] if "n_lostpdu" in d else len(d["lostpdu"])
        agg[(k, a.harq)]["lost_pairs"] += sum(1 for s in a.cohort_complete() if a.outcome[s] == "lost")
    lines = []
    for (k, h), c in sorted(agg.items()):
        if h == 5:
            c16 = agg.get((k, 16), Counter())
            if c or c16:
                lines.append(f"{L.LABEL[k[0]]} {k[1]}: RLC PDUs lost DL {dict(c)} (5 HARQ) vs {dict(c16)} (16 HARQ)")
    report.append("Q6 HARQ pair (DL; reported, no delivery guarantee claimed):\n  " + "\n  ".join(lines))
    add("Q6 (b) HARQ pair reported", f"{len(lines)} option x variant pairs reported in the report (5 vs 16 HARQ processes)", True)


def q0c_rows(out, A):
    idx = {(a.opt, a.variant, a.harq, a.rep): a for a in A}
    bad, nn, att = [], 0, Counter()
    for (o, v, h, r), a0 in sorted(idx.items()):
        if o != "q0":
            continue
        ap = idx.get(("q0p", v, h, r))
        if ap is None:
            continue
        nn += 1
        for drb in (1, 2):
            d0, dp = L.rlc(L.VecRun(a0.run.R.vec_path), "q0", drb), L.rlc(L.VecRun(ap.run.R.vec_path), "q0p", drb)
            if [x for x in d0["sdus"]] != [x for x in dp["sdus"]]:
                bad.append((v, h, r, drb, "arrivals differ"))
                continue
            r0, rp = L.replay_um(d0["sdus"], d0["pdus"]), L.replay_um(dp["sdus"], dp["pdus"])
            c0 = {x[0]: x[2] for x in r0[0]}
            cp = {x[0]: x[2] for x in rp[0]}
            cut0 = {x for s in r0[1].values() for x in s["cut"]}
            cutp = {x for s in rp[1].values() for x in s["cut"]}
            m0 = G.deliveries(r0[0], d0["deliv"], d0["rxpdus"], d0["pdus"], d0["sdus"], a0.run.end)
            mp = G.deliveries(rp[0], dp["deliv"], dp["rxpdus"], dp["pdus"], dp["sdus"], ap.run.end)
            del0 = {x[0]: x[3] for x in m0[0]}
            delp = {x[0]: x[3] for x in mp[0]}
            for t, sz in d0["sdus"]:
                a_, b_ = del0.get(t), delp.get(t)
                if a_ == b_:
                    continue
                if (a_ is None) != (b_ is None):
                    lost = {x[0] for x in m0[1] if x[3] is True} | {x[0] for x in mp[1] if x[3] is True}
                    cause = "HARQ discard" if t in lost else ("end of run" if t > 11 * S else None)
                elif (t in cut0) != (t in cutp):
                    cause = "tail lag"
                else:
                    g0 = [x for x in d0["pdus"] if t <= x[0] <= max(c0.get(t, t), cp.get(t, t))]
                    gp = [x for x in dp["pdus"] if t <= x[0] <= max(c0.get(t, t), cp.get(t, t))]
                    cause = "scheduler" if g0 != gp else None
                if cause is None:
                    bad.append((v, h, r, drb, t, a_, b_))
                else:
                    att[cause] += 1
    add("Q0c QOS_PF reference (Q-0p vs Q-0, paired seeds)", f"{nn} pairs: per DRB 1/2 identical SDU arrivals; every delivery difference "
        f"attributed: {dict(att)}", nn and not bad, str(bad[:3]))


def q4_rows(out):
    """the full M2-S6 check stack (rows K/S/R/E[/T]) on the accuracy configs"""
    import m2s6_runs as RR
    for cfg in G.run_dirs(os.path.join(out, "runs")):
        if cfg.endswith("-Ca") or cfg.endswith("-Bp100") or cfg.endswith("-Ca-sus"):
            gm = RR.node(RR.C(100.0))
            sl = RR.node(RR.C(-100.0 if "-Ca" in cfg else 0.0))
            RR.CLOCKS[cfg] = RR.cfg(False, gm, sl, 12 * S, reps=G.reps_of(os.path.join(out, "runs"), cfg))
    import check_m2s6 as CK
    n0 = len(CK.rows)
    done = []
    global BETWEEN
    for cfg in sorted(k for k in RR.CLOCKS if k.startswith("M2S71-")):
        items = []
        for rep in RR.CLOCKS[cfg]["reps"]:
            rr = []
            E = CK.run_eval(os.path.join(out, "runs"), cfg, rep, rr)
            done.append((cfg, rep))
            if rr[0][3]:
                items.append((rep, E))
        if items:
            report.append("\n".join(CK.stats_lines(cfg, items)))
            # steady-state between-step max |e| (M2-S6 definition: calibrated intervals from step 3, after the first calibrated one)
            vals = []
            for rep, E in items:
                cal = [f["seq"] for f in E.fus if "skip" not in f and f["nrr_valid"]]
                vals += [abs(x["max_between"]) for x in E.iv[2:] if x["seq"] in cal and x["seq"] != cal[0] and x["max_between"] is not None]
            BETWEEN[cfg] = max(vals) if vals else INF
    new = CK.rows[n0:]
    by_cfg = defaultdict(lambda: [0, 0])
    for r in new:
        cfg = re.search(r"(M2S71-[\w-]+?)-\d+", r[0] + " " + r[1])
        c = cfg.group(1) if cfg else "?"
        by_cfg[c][0] += 1
        by_cfg[c][1] += bool(r[2])
    bad = [r for r in new if not r[2]]
    add("Q4 M2-S6 check stack on the accuracy configs", f"{len(done)} runs, {len(new)} rows (K, S, R, E), {sum(1 for r in new if r[2])} pass; "
        + "; ".join(f"{c}: {p}/{n}" for c, (n, p) in sorted(by_cfg.items())), new and not bad,
        "; ".join(f"{r[0]}: {r[1][:120]}" for r in bad[:3]))
    return {c: (n == p) for c, (n, p) in by_cfg.items()}


def h0_rows(out, A12, group_of):
    """outcome classes of cohort pairs at 12 s vs 20 s for every seed-0 run with a 20 s twin"""
    r20 = os.path.join(out, "runs-20s")
    changed, n, need = defaultdict(int), 0, set()
    by = {(a.cfg, a.rep): a for a in A12}
    for cfg in G.run_dirs(r20):
        for rep in G.reps_of(r20, cfg):
            a12 = by.get((cfg, rep))
            if a12 is None:
                continue
            a20 = Analysis(r20, cfg, rep)
            n += 1
            ch = [s for s in a12.cohort_complete() if a12.outcome[s] != a20.outcome.get(s)]
            if ch:
                changed[group_of(a12)] += len(ch)
    unresolved = [(a.cfg, a.rep) for a in A12 if any(a.outcome[s] == "censored" for s in a.cohort_complete())]
    missing = [x for x in unresolved if not os.path.isdir(os.path.join(r20, x[0]))]
    with open(os.path.join(out, "h0-extra.txt"), "w") as fh:
        for cfg, rep in missing:
            fh.write(f"{cfg} {rep}\n")
    add("H0 drain sufficiency", f"{n} runs compared at 12 s and 20 s; cohort pairs changing class: {sum(changed.values())} "
        f"(groups {dict(changed) if changed else 'none'}); runs with unresolved cohort pairs at 12 s: {len(unresolved)}, without a 20 s run: "
        f"{len(missing)} (listed in h0-extra.txt)", n and not missing, "horizon 12 s sufficient" if not changed else "groups moved to 20 s")
    return changed


# --- selection (design 7) -----------------------------------------------------------------------------------
def select(stats, eligible, conds, options):
    """stats[(opt, cond)] -> summary (5 HARQ). Returns (ranked admissible list, notes)."""
    notes = []
    q0 = {c: stats.get(("q0", c)) for c in conds}
    adm = []
    for o in options:
        if o == "q0" or not eligible.get(o, False):
            notes.append(f"{L.LABEL[o]}: not eligible" if o != "q0" else "Q-0: reference")
            continue
        s = {c: stats.get((o, c)) for c in conds}
        if any(v is None for v in s.values()):
            notes.append(f"{L.LABEL[o]}: missing conditions")
            continue
        di = s["idle"]["p99_lag"] - q0["idle"]["p99_lag"] if q0["idle"] else None
        dr = s["idle"]["p99_res"] - q0["idle"]["p99_res"] if q0["idle"] else None
        guard = di is not None and di <= MS and dr <= MS
        loads = [c for c in conds if c != "idle"]
        worse = [c for c in loads if s[c]["p99_lag"] > q0[c]["p99_lag"]]
        notes.append(f"{L.LABEL[o]}: idle difference vs Q-0: p99 lag {us(di)} us, p99 residence {us(dr)} us -> idle guard "
                     f"{'passed' if guard else 'FAILED'}; worse than Q-0 under {worse or 'no load condition'}")
        if guard and not worse:
            adm.append(o)

    def key(o):
        s = {c: stats[(o, c)] for c in conds}
        ld = tuple(s[c]["p99_lag"] for c in ("sus", "load") if c in conds)
        return (ld, s["idle"]["p99_lag"], max(s[c]["p99_res"] for c in conds if c != "idle") if len(conds) > 1 else 0,
                BETWEEN.get(f"M2S71-{o}-Ca", INF),
                0 if L.OPTIONS[o][2] == "um" else 1, len({L.OPTIONS[o][0], L.OPTIONS[o][1]}), 0 if L.OPTIONS[o][4] == "MAXCI" else 1)
    adm.sort(key=key)
    better = [o for o in adm if all(stats[(o, c)]["p99_lag"] < stats[("q0", c)]["p99_lag"] for c in conds if c != "idle")]
    return adm, better, notes


def load_all(out, which):
    root = os.path.join(out, "runs")
    A = []
    for cfg in G.run_dirs(root):
        if any(x in cfg for x in ("-N-", "-T-", "-M0-", "-B5", "-B6", "-B10")) or cfg.endswith(("-Ca", "-Bp100", "-Ca-sus")):
            continue
        opt, variant, harq = L.parse_cfg(cfg)
        if variant not in which:
            continue
        for rep in G.reps_of(root, cfg):
            A.append(Analysis(root, cfg, rep).compact())
    return A


def gate_ok(out):
    """the order rule: gate-Q0b.txt must exist and list the same inputs (vec hashes) as the runs present"""
    p = os.path.join(out, "gate-Q0b.txt")
    if not os.path.exists(p):
        return False, "gate-Q0b.txt missing"
    rec = {}
    for line in open(p):
        m = re.match(r"\s+(M2S71-\S+) (\d+) ([0-9a-f]{64})$", line)
        if m:
            rec[(m.group(1), int(m.group(2)))] = m.group(3)
    bad = []
    for (cfg, rep), h in rec.items():
        v = os.path.join(out, "runs", cfg, cfg, f"{rep}.vec")
        if not os.path.exists(v) or hashlib.sha256(open(v, "rb").read()).hexdigest() != h:
            bad.append((cfg, rep))
    return not bad and rec, f"{len(rec)} inputs recorded, {len(bad)} changed or missing"


def gate_rows(out):
    """per-option gate verdict from gate-P0.txt: a row naming a config (M2S71-<opt>-...) before its ':' belongs to that
    option, the others are common. NOT EVALUATED (Q0b-4, AM) is neither PASS nor FAIL: it puts the option in the
    measured-only class and does not block eligibility. Returns ({opt: all own rows pass}, common rows pass, OVERALL)."""
    p = os.path.join(out, "gate-P0.txt")
    if not os.path.exists(p):
        return {}, False, False
    own, common, overall = defaultdict(lambda: True), True, False
    for line in open(p):
        m = re.match(r"\[(PASS|FAIL|NOT EVALUATED)\] ([^:]*)", line)
        if not m:
            overall = overall or line.startswith("OVERALL: PASS")
            continue
        ok = m.group(1) != "FAIL"
        c = re.search(r"\b(M2S71-[A-Za-z0-9-]+)$", m.group(2).strip())
        if c and c.group(1).split("-")[1] in L.OPTIONS:
            o = c.group(1).split("-")[1]
            own[o] = own[o] and ok
        else:
            common = common and ok
    return {o: own[o] for o in L.OPTIONS}, common, overall


def main():
    mode, out = sys.argv[1:3]
    ok, why = gate_ok(out)
    add("order rule (design 4)", f"gate-Q0b.txt written before the statistics, for the same raw outputs: {why}", ok)
    if not ok:
        return finish(out, mode)
    which = {"phase1": ("idle", "load", "frag"), "phase2": ("sus",), "final": ("idle", "load", "frag", "sus")}[mode]
    A = load_all(out, which)
    # C1: the statistics' inputs are exactly the complete cohort pairs
    c1bad = [(a.cfg, a.rep) for a in A if set(a.cohort_complete()) != {s for s in a.lag if s in a.cohort}]
    add("C1 cohort use", f"{len(A)} runs: every primary statistic is computed over the complete cohort pairs only (post-cohort pairs: "
        f"{sum(len(a.post) for a in A)}, used only in Q8 and the secondary table)", A and not c1bad, str(c1bad[:3]))
    q8_rows(A)
    q7 = q7_rows(A)
    c3_rows(A)
    q1_rows(A)
    q5_rows(A)
    n, nf, bad = q3_rows(A)
    add("Q3 residence monitor = offline count", f"{n} corrected Follow_Ups in {len(A)} runs (bound 5.5 ms): {nf} flagged; monitor flags = "
        "offline Res > B from PCAP in every run", not bad, str(bad[:3]))
    if mode != "phase2":
        q0c_rows(out, [a for a in A if a.variant in ("idle", "load", "frag")])
        q6_rows(out, A)
        extra_rows(out)
    acc = q4_rows(out)
    # H0 groups: (variant, harq)
    group_of = lambda a: (a.variant, a.harq)  # noqa: E731
    changed = h0_rows(out, A, group_of)
    # statistics per (option, variant, harq)
    groups = defaultdict(list)
    for a in A:
        groups[(a.opt, a.variant, a.harq)].append(a)
    stats = {k: summarize(v) for k, v in groups.items()}
    report.append("Q2 distributions over the complete cohort pairs (+inf rule; seeds = replication unit)\n"
                  "option | variant | HARQ | seeds | pairs | P(delivered, used) mean ± 95% CI | p50 lag | p99 lag pooled | "
                  "p99 lag per seed (mean ± CI) | p99 lag (delivered only) | lag min..max (delivered) | p99 residence | censored | classes | acceptance")
    for (o, v, h), s in sorted(stats.items(), key=lambda kv: (list(L.OPTIONS).index(kv[0][0]), kv[0][1], kv[0][2])):
        acc_cls = "measured-only" if L.OPTIONS[o][2] == "am" else "exact-replay"
        report.append(f"{L.LABEL[o]}{' (EXPERIMENTAL)' if o in EXP else ''} | {v} | {h} | {len(s['seeds'])} | {s['n']} | "
                      f"{fmt_ci(s['p_deliv'], 'p')} | {us(s['p50_lag'])} us | {us(s['p99_lag'])} us | {fmt_ci(s['p99_lag_seed'])} | "
                      f"{us(s['p99_lag_deliv'])} us | {us(s['min_lag'])}..{us(s['max_lag'])} us | {us(s['p99_res'])} us | {s['censored']} | "
                      f"{dict(s['classes'])} | {acc_cls}")
    # eligibility
    rowok = lambda prefix: all(r[2] for r in rows if r[0].startswith(prefix))  # noqa: E731
    common = all(rowok(p) for p in ("C1", "Q8", "Q1", "H0"))            # design 7 step 1 (with P0, C0, Q0a, Q0b, Q4, Q7)
    gate_opt, gate_common, gate_pass = gate_rows(out)
    elig = {}
    for o in L.OPTIONS:
        ig = sum(v for k, v in q7.items() if k[0] == o)
        q4 = all(v for c, v in acc.items() if c.startswith(f"M2S71-{o}-")) and any(c.startswith(f"M2S71-{o}-") for c in acc)
        elig[o] = common and gate_common and gate_opt.get(o, False) and ig == 0 and q4
    report.append("Eligibility (design 7 step 1): " + ", ".join(f"{L.LABEL[o]} {'yes' if v else 'no'}" for o, v in elig.items())
                  + f" (gates P0/C0/Q0a/Q0b: rows common to all options {'PASS' if gate_common else 'not PASS'}; rows of each "
                  f"option's own configs: {', '.join(L.LABEL[o] + (' PASS' if v else ' not PASS') for o, v in gate_opt.items())}; "
                  f"whole record {'PASS' if gate_pass else 'not PASS'})")
    conds = ["idle", "load"] + (["sus"] if mode != "phase1" else [])
    st5 = {(o, c): stats[(o, c, 5)] for (o, c, h) in stats if h == 5 and c in conds}
    have = [o for o in NONEXP if all((o, c) in st5 for c in conds)]
    if mode != "phase2":
        adm, better, notes = select(st5, elig, ["idle", "load"], [o for o in NONEXP if all((o, c) in st5 for c in ("idle", "load"))])
        report.append("Phase-1 selection (idle + 0-3 s load; 5 HARQ):\n  " + "\n  ".join(notes)
                      + f"\n  admissible, ranked: {[L.LABEL[o] for o in adm]}; better than Q-0 under load: {[L.LABEL[o] for o in better]}")
        ded = [o for o in adm if o in DEDICATED_NONEXP]
        # experimental options ranked among themselves (for the phase-2 choice only)
        e_el = {o: common and sum(v for k, v in q7.items() if k[0] == o) == 0 for o in EXP}
        e_st = {k: v for k, v in st5.items() if k[0] in EXP}
        eadm, _, enotes = select({**st5}, {**e_el}, ["idle", "load"], ["q0"] + [o for o in EXP if all((o, c) in st5 for c in ("idle", "load"))])
        a_opt = ded[0] if ded else None
        b_opt = eadm[0] if eadm else ([o for o in EXP if (o, "load") in st5] or [None])[0]
        report.append(f"  phase-2 options: strongest non-experimental dedicated-DRB option {L.LABEL.get(a_opt, a_opt)}; strongest experimental "
                      f"{L.LABEL.get(b_opt, b_opt)} (experimental notes: {'; '.join(enotes)})")
        if mode == "phase1":
            with open(os.path.join(out, "phase2-options.txt"), "w") as fh:
                fh.write(f"{a_opt or 'qa'} {b_opt or 'qc'}\n")
    if mode != "phase1" and all(("q0", c) in st5 for c in conds):
        cand = [o for o in have if o != "q0"]
        adm, better, notes = select(st5, elig, conds, ["q0"] + cand)
        rec = better[0] if better else "q0"
        report.append("Final selection (idle, 0-3 s load, sustained load; 5 HARQ; only the tested candidates):\n  " + "\n  ".join(notes)
                      + f"\n  admissible, ranked: {[L.LABEL[o] for o in adm]}; better than Q-0 under every load condition: "
                      f"{[L.LABEL[o] for o in better]}\n  RECOMMENDED: {L.LABEL[rec]} ({'measured-only' if L.OPTIONS[rec][2] == 'am' else 'exact-replay'} "
                      "acceptance); not a claim of global optimality")
    return finish(out, mode)


def extra_rows(out):
    """Q3 bound variants and the negative controls (check_m2s71_controls.py)"""
    import check_m2s71_controls as NC
    NC.rows(out, add, Analysis, report)


def finish(out, mode):
    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"[{'PASS' if ok else 'FAIL'}] {check}: {detail}" + (f" -- {extra}" if extra else ""))
    print(f"OVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    with open(os.path.join(out, f"{mode}-report.txt"), "w") as fh:
        fh.write(f"M2-S7.1 report ({mode}); reported results, not gating\n\n" + "\n\n".join(report) + "\n")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
