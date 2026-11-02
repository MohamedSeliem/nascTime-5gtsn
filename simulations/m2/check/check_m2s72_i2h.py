#!/usr/bin/env python3
"""M2-S7.2a I-2H: hold/release correctness for loaded Block H (review 2026-11-02 16:12, Option B; definition:
migration/m2-s7.2a-p2-hold-investigation.md section 6). The strict I-2 (check_m2s72_f0.f02, unchanged) stays the test
for every idle configuration; on Block H it is reported separately as "I-2 strict (info)" and only I-2H governs
hold/release correctness.

    check_m2s72_i2h.py obs <runs dir> <cfg> <Block H config it equals>   I-2H on an observation record (P1/P2 scratch)
    check_m2s72_i2h.py focused <OUT>                                       I-2H focused validation (m2s72.sh i2h)

I-2H, per run and DS-TT k (DS-TT k egress log syncOut.sync.csv, NW-TT syncIn log, DS-TT k eth[1] gPTP PCAP, DS-TT k
eth[1] egress port log egress.port.csv; integer ps; no tolerance). PASS iff
  1 grammar     every domain-0 Follow_Up sequenceId has exactly the egress events [corrected] or [hold, release,
                corrected]; no event outside {syncSlot, syncTx, hold, release, held, corrected, otherDomain} (every
                discard reason, holdExpired, TEST events fail); #hold = #release; every 'held' frame lies inside a hold
                and the release note counts 1 + its held frames; one syncSlot and one syncTx per Sync, syncSlot <= syncTx
  2 trigger     held  <=>  t(syncSlot) <= t(FU at the hold point) < t(syncTx) of the same Sync; not held  <=>
                t(syncTx) <= t(FU at the hold point); any other case fails
  3 release     t(release) = t(syncTx) of the held Sync (zero-delay); 'corrected' logged at t(release); the corrected
                row references that Sync: same (domain, sourcePortIdentity, sequenceId) and syncFrameId
  4 tag         tag valid, TT id 1, tag sequenceId = own; TSi, Lup, rrOut, cfIn = the NW-TT corrected row
  5 correction  TSe = the Sync's first-bit stamp (A1: syncTx time; A2: the DS-TT TT-clock stamp of it);
                Res = TSe - TSi; cfOut = cfIn + rr_out (x) Res (INET fixed point); wire cf of the FU on eth[1] =
                writeClock8(cfOut)
  6 ordering    on eth[1] (PCAP) the Sync's first bit = t(syncTx), exactly one FU per Sync, FU first bit >= Sync last bit
  7 FIFO        port log: transmission order = MAC-queue entry order, every first bit = max(entry, previous last bit +
                96 bit times at 1 Gb/s) (M2-S5 H0/H2), every gPTP first bit of the PCAP = a port-log first bit (same
                count); held FU and frames released with it: entry = t(release), first bit = the no-hold FIFO first bit
                max(t(at the hold point), previous last bit + 96 bit times)
  8 accounting  counts of corrected / hold / release / held / expired / discarded reported; at T_end: a Sync queued but
                not transmitted, a hold not released, or a Follow_Up or Sync received on eth[0] without an egress event is
                accepted only within the last maximal frame time (1542 B incl. preamble and IFG = 12.336 us) before
                T_end, and listed as end-of-run; otherwise it fails
H-nv (non-vacuity, the selected Q-0 run M2S72-H16-q0-Ca-n2 seed 0): DS-TT 1 holds > 0 and releases > 0, and pair (0,1)
                has Res_0 != Res_1 on >= 1 common Follow_Up and >= 1 non-zero (r - rho_G)(Res_0 - Res_1)
"""
import csv
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_b as B  # noqa: E402  (Block B / H rows, unchanged oracles underneath)
sys.argv = _argv
import m2s72_runs as R  # noqa: E402
import m2s72_s6 as V  # noqa: E402
import clock_model as K  # noqa: E402
import inet_model as M  # noqa: E402

NS = 1000
IFG = 96 * NS                       # 96 bit times at 1 Gb/s (DS-TT eth[1])
MAXF = (1522 + 8 + 12) * 8 * NS     # largest frame + preamble/SFD + IFG
ALLOWED = {"syncSlot", "syncTx", "hold", "release", "held", "corrected", "otherDomain"}
rows = B.rows


def ps(s):
    a, _, b = s.partition(".")
    return int(a) * 10 ** 12 + int((b + "0" * 12)[:12])


def port_log(run, k):
    p = os.path.join(run.ldir, f"{R.NET}.dsTt[{k}].eth[1].measurementLayer.egress.port.csv")
    out = []
    for r in csv.DictReader(open(p)):
        if r["event"] == "tx":
            out.append({"slot": ps(r["tSlot"]), "start": ps(r["tTxStart"]), "end": ps(r["tTxEnd"]), "et": r["etherType"]})
    return out


def i2h(ev, k):
    """I-2H for DS-TT k of RunEval ev. Returns (ok, stats, problems)."""
    run, v, T = ev.run, ev.views[k], ev.T
    log = v.dslog
    probs = []
    ev_count = Counter(r["event"] for r in log)
    bad_ev = {e: c for e, c in ev_count.items() if e not in ALLOWED}
    if bad_ev:
        probs.append(f"events outside the hold/release grammar: {bad_ev}")
    sync_rows = defaultdict(lambda: defaultdict(list))
    fu_seq = defaultdict(list)
    held_open, hold_of, cur = {}, None, None
    held_counts = []
    for r in log:
        e = r["event"]
        if e in ("syncSlot", "syncTx"):
            sync_rows[int(r["seq"])][e].append(r)
        elif e in ("hold", "release", "corrected") or (r["msgType"] == "8" and e not in ("held", "otherDomain")):
            fu_seq[int(r["seq"])].append(r)
            if e == "hold":
                if cur is not None:
                    probs.append(f"hold of {r['seq']} while hold of {cur} active")
                cur, held_open[int(r["seq"])] = int(r["seq"]), []
            elif e == "release":
                if cur != int(r["seq"]):
                    probs.append(f"release of {r['seq']} without its hold")
                else:
                    n = 1 + len(held_open[cur])
                    if r["note"] != f"{n} frames":
                        probs.append(f"release of {cur}: note '{r['note']}', expected '{n} frames'")
                    held_counts.append(len(held_open[cur]))
                cur = None
        elif e == "held":
            if cur is None:
                probs.append(f"'held' frame at {r['t']} outside a hold")
            else:
                held_open[cur].append(int(r["t"]))
    nw = {int(r["seq"]): r for r in run.nwlog if r["event"] == "corrected" and r["msgType"] == "8"}
    tx = [f for f in v.ds1 if f["dir"] == 2]
    sy_tx = defaultdict(list)
    fu_tx = defaultdict(list)
    for f in tx:
        if f["g"] and f["dom"] == 0 and f["type"] == 0:
            sy_tx[f["g"]["seq"]].append(f)
        elif f["g"] and f["dom"] == 0 and f["type"] == 8:
            fu_tx[f["g"]["seq"]].append(f)
    stamp = {(r["kind"], r["s"]): r["tau"] for r in v.ttlog["ds"]} if v.ttlog else None
    pl = port_log(run, k)
    # 7 FIFO replay on the port log
    nd, prev_end, order_ok = 0, None, True
    for i, f in enumerate(pl):
        exp = f["slot"] if prev_end is None else max(f["slot"], prev_end + IFG)
        if exp != f["start"]:
            nd += 1
        if i and (f["slot"] < pl[i - 1]["slot"] or f["start"] <= pl[i - 1]["start"]):
            order_ok = False
        prev_end = f["end"]
    if nd or not order_ok:
        probs.append(f"egress FIFO replay: {nd} deviations, order = entry order {order_ok}")
    g_starts = sorted(f["start"] for f in tx)
    pl_g = sorted(f["start"] for f in pl if f["et"] == "35063")
    if g_starts != pl_g:
        probs.append(f"PCAP gPTP first bits ({len(g_starts)}) != port-log gPTP first bits ({len(pl_g)})")
    by_start = {f["start"]: i for i, f in enumerate(pl)}
    by_slot = defaultdict(list)
    for i, f in enumerate(pl):
        by_slot[f["slot"]].append(i)
    n_held = n_corr = 0
    end_run = []
    for s in sorted(set(fu_seq) | set(sync_rows)):
        sr = sync_rows.get(s, {})
        slots, txs = sr.get("syncSlot", []), sr.get("syncTx", [])
        evs = [r["event"] for r in fu_seq.get(s, [])]
        if len(slots) > 1 or len(txs) > 1:
            probs.append(f"seq {s}: {len(slots)} syncSlot, {len(txs)} syncTx")
            continue
        if slots and not txs:
            if int(slots[0]["t"]) >= T - MAXF and evs in ([], ["hold"]):
                end_run.append(f"Sync {s} queued at {slots[0]['t']} ps, not transmitted by T_end" + (" (FU held)" if evs else ""))
                continue
            probs.append(f"seq {s}: Sync queued, never transmitted, FU events {evs}")
            continue
        if not evs:
            continue                    # Sync transmitted; its FU never reached DS-TT k (accounted below, eth[0])
        if evs not in (["corrected"], ["hold", "release", "corrected"]):
            probs.append(f"seq {s}: FU events {evs}")
            continue
        if not slots:
            probs.append(f"seq {s}: FU without its Sync at the egress")
            continue
        t_slot, t_tx = int(slots[0]["t"]), int(txs[0]["t"])
        if t_slot > t_tx:
            probs.append(f"seq {s}: syncSlot after syncTx")
        held = evs[0] == "hold"
        rs = fu_seq[s]
        c = rs[-1]
        t_fu = int(rs[0]["t"])
        n_corr += 1
        n_held += held
        # 2 trigger
        if held and not (t_slot <= t_fu < t_tx):
            probs.append(f"seq {s}: held, but FU at {t_fu}, Sync queued {t_slot}, first bit {t_tx}")
        if not held and not (t_tx <= t_fu):
            probs.append(f"seq {s}: not held, but FU at {t_fu} before the Sync first bit {t_tx}")
        # 3 release and association
        if held:
            t_rel = int(rs[1]["t"])
            if t_rel != t_tx or int(c["t"]) != t_rel:
                probs.append(f"seq {s}: release {t_rel}, corrected {c['t']}, Sync first bit {t_tx}")
        st = txs[0]
        if (c["syncFrameId"] != st["syncFrameId"] or (c["domain"], c["srcClock"], c["srcPort"]) != (st["domain"], st["srcClock"], st["srcPort"])):
            probs.append(f"seq {s}: corrected row does not reference its transmitted Sync")
        # 4 tag = NW-TT
        n = nw.get(s)
        if (c["tagValid"] != "1" or c["tagTtId"] != "1" or int(c["tagSeq"]) != s or n is None or c["TSi"] != n["TSi"]
                or c["Lup"] != n["Lup"] or float(c["rrOut"]) != float(n["rrOut"]) or c["cfIn"] != n["cfOut"]):
            probs.append(f"seq {s}: tag / NW-TT identity")
        # 5 correction and wire
        TSi, TSe, Res, cfIn, cfOut = int(c["TSi"]), int(c["TSe"]), int(c["Res"]), int(c["cfIn"]), int(c["cfOut"])
        exp_tse = t_tx if stamp is None else stamp.get((2, t_tx))
        if TSe != exp_tse or Res != TSe - TSi or cfOut != cfIn + K.mul_round(TSe - TSi, K.from_double(float(c["rrOut"]))):
            probs.append(f"seq {s}: correction (TSe {TSe} vs {exp_tse}, Res {Res}, cfOut {cfOut})")
        S, F = sy_tx.get(s, []), fu_tx.get(s, [])
        if len(S) != 1 or len(F) != 1:
            probs.append(f"seq {s}: {len(S)} Sync / {len(F)} FU frames on eth[1]")
            continue
        S, F = S[0], F[0]
        if F["g"]["cf_raw"] != M.inet_write_clock8(cfOut):
            probs.append(f"seq {s}: wire cf")
        # 6 ordering
        if S["start"] != t_tx or F["start"] < S["end"]:
            probs.append(f"seq {s}: Sync first bit {S['start']} vs syncTx {t_tx}; FU first bit {F['start']} vs Sync last bit {S['end']}")
        # 7 no added hold delay
        if held:
            i = by_start.get(F["start"])
            ent = by_slot.get(t_rel, [])
            hn = held_open.get(s, [])
            if i is None or pl[i]["slot"] != t_rel or ent[:1] != [i] or len(ent) != 1 + len(hn):
                probs.append(f"seq {s}: released frames at {t_rel}: port-log entries {len(ent)}, expected FU + {len(hn)} held")
            else:
                for j, t_entry in zip(ent, [t_fu] + hn):
                    if pl[j]["start"] != max(t_entry, pl[j - 1]["end"] + IFG):
                        probs.append(f"seq {s}: released frame first bit {pl[j]['start']} != no-hold FIFO first bit")
    # 8 eth[0] arrivals without an egress event
    got = {(f["type"], f["g"]["seq"]): f for f in v.ds0 if f["dir"] == 1 and f["g"] and f["dom"] == 0 and f["type"] in (0, 8)}
    for (typ, s), f in sorted(got.items(), key=lambda x: x[1]["end"]):
        has = bool(sync_rows.get(s, {}).get("syncSlot")) if typ == 0 else bool(fu_seq.get(s))
        if not has:
            if f["end"] >= T - MAXF:
                end_run.append(f"{'Sync' if typ == 0 else 'FU'} {s} received at {f['end']} ps, no egress event by T_end")
            else:
                probs.append(f"{'Sync' if typ == 0 else 'FU'} {s} received on eth[0] at {f['end']} ps without an egress event")
    if ev_count["hold"] != ev_count["release"] and not any("(FU held)" in x for x in end_run):
        probs.append(f"#hold {ev_count['hold']} != #release {ev_count['release']}")
    stats = {"corrected": n_corr, "hold": ev_count["hold"], "release": ev_count["release"], "held_frames": ev_count["held"],
             "held_fu": n_held, "expired": ev_count["holdExpired"], "discarded": sum(c for e, c in bad_ev.items() if e != "holdExpired"),
             "port_frames": len(pl), "fifo_dev": nd, "end_of_run": end_run}
    return not probs, stats, probs


def i2h_rows(ev):
    out = {}
    for k in sorted(ev.views):
        ok, st, probs = i2h(ev, k)
        out[k] = st
        B.add("I-2H", f"{ev.cfg}-{ev.rep} DS-TT {k}", ok,
              f"FU corrected {st['corrected']} (held {st['held_fu']}); hold {st['hold']}, release {st['release']}, held frames {st['held_frames']}, "
              f"expired {st['expired']}, discarded {st['discarded']}; egress FIFO replay {st['port_frames']} frames, {st['fifo_dev']} deviations; "
              f"end-of-run {st['end_of_run'] if st['end_of_run'] else 'none'}" + (f"; FAIL {probs[:4]} ({len(probs)})" if probs else ""))
    return out


def relabel(start, cfg):
    """Block H: the strict I-2 is reported separately (information); Q-d H-cov is a diagnostic."""
    for i in range(start, len(rows)):
        r = rows[i]
        if r[0] == "I-2":
            rows[i] = ("I-2 strict (info)",) + r[1:]
        if r[0] == "H-cov" and "-qdu-" in cfg:
            rows[i] = ("H-cov (diagnostic)",) + r[1:]


INFO = ("I-2 strict (info)", "H-cov (diagnostic)")


def evaluate_h(runs, cfg, rep, ref, base):
    """Every Block H row (check_m2s72_b.evaluate), I-2H and H-cov, for config cfg evaluated as Block H config base."""
    B.BN_BASE[cfg] = base
    start = len(rows)
    T = B.F1.t_end(R.Run72(runs, cfg, rep))
    ev, stats, _ = B.evaluate(runs, cfg, rep, ref=ref, conf_fn=lambda k: V.CONF(base, k, T))
    cov = B.h_cov(ev, stats)
    st = i2h_rows(ev)
    relabel(start, base)
    fails = {r[0] for r in rows[start:] if r[2] == "FAIL" and r[0] not in INFO}
    info = {r[0]: r[2] for r in rows[start:] if r[0] in INFO}
    return ev, stats, cov, st, fails, info


# ------------------------------------------------------------------------------------------------ controls -------------
# declared before any run: results/M2-S7.2a-i2h-predictions.md (gate families; info rows reported separately)
PRED = {
    "NC-noHold": {"I-2H"},
    "NC-holdTimeout": {"I-2H"},
    "NC-release": {"I-2H"},
    "NC-syncFrameId": {"I-1", "I-2H"},
    "NC-txStart": {"I-2H"},
}
BASE = "M2S72-H16-q0-Ca-n2"
BASE_H = "M2S72-H-q0-Ca-n2"      # the Block H config BASE is evaluated as (clock configuration, option)


def copy_run(runs, cfg):
    tmp = tempfile.mkdtemp(prefix="m2s72i2h-")
    shutil.copytree(os.path.join(runs, cfg), os.path.join(tmp, cfg))
    return tmp


def mid_held(runs, cfg, k=1):
    run = R.Run72(runs, cfg, 0)
    holds = [r for r in run.ue_view(k).dslog if r["event"] == "hold"]
    return int(holds[len(holds) // 2]["seq"])


def mutate_dslog(tmp, cfg, k, pick, change):
    p = os.path.join(tmp, cfg, "m2log", f"{cfg}-0", f"{R.NET}.dsTt[{k}].eth[1].trafficConditionerLayer.syncOut.sync.csv")
    L = open(p).read().split("\n")
    h = L[0].split(",")
    idx = [i for i in range(1, len(L)) if L[i] and pick(dict(zip(h, L[i].split(","))))]
    if len(idx) != 1:
        raise ValueError(f"mutation target rows {len(idx)}")
    c = L[idx[0]].split(",")
    change(h, c)
    L[idx[0]] = ",".join(c)
    open(p, "w").write("\n".join(L))


def fmt_s(x):
    a, b = divmod(x, 10 ** 12)
    return f"{a}.{b:012d}".rstrip("0").rstrip(".") if b else str(a)


def mutate_txstart(tmp, cfg, k, seq):
    run = R.Run72(tmp, cfg, 0)
    v = run.ue_view(k)
    F = [f for f in v.ds1 if f["dir"] == 2 and f["type"] == 8 and f["g"] and f["g"]["seq"] == seq]
    p = os.path.join(tmp, cfg, "m2log", f"{cfg}-0", f"{R.NET}.dsTt[{k}].eth[1].measurementLayer.egress.port.csv")
    L = open(p).read().split("\n")
    h = L[0].split(",")
    j = h.index("tTxStart")
    idx = [i for i in range(1, len(L)) if L[i] and ps(L[i].split(",")[j]) == F[0]["start"]]
    if len(idx) != 1:
        raise ValueError(f"port-log target rows {len(idx)}")
    c = L[idx[0]].split(",")
    c[j] = fmt_s(ps(c[j]) + IFG)
    L[idx[0]] = ",".join(c)
    open(p, "w").write("\n".join(L))


def controls(runs):
    out = []
    s = mid_held(runs, BASE)

    def run_ctrl(name, fn):
        start = len(rows)
        try:
            fails, info = fn()
        except Exception as ex:
            fails, info = {f"EXCEPTION {type(ex).__name__}: {ex}"}, {}
        mine = rows[start:]
        del rows[start:]
        out.append((name, fails == PRED[name], fails, PRED[name], info, mine))

    def on_cfg(cfg):
        return lambda: evaluate_h(runs, cfg, 0, None, BASE_H)[4:]

    def on_copy(mut):
        def f():
            tmp = copy_run(runs, BASE)
            try:
                mut(tmp)
                return evaluate_h(tmp, BASE, 0, None, BASE_H)[4:]
            finally:
                shutil.rmtree(tmp)
        return f

    def rel(tmp):
        mutate_dslog(tmp, BASE, 1, lambda d: d["event"] == "release" and int(d["seq"]) == s,
                     lambda h, c: c.__setitem__(h.index("t"), str(int(c[h.index("t")]) + 1)))

    def sfid(tmp):
        mutate_dslog(tmp, BASE, 1, lambda d: d["event"] == "corrected" and int(d["seq"]) == s,
                     lambda h, c: c.__setitem__(h.index("syncFrameId"), str(int(c[h.index("syncFrameId")]) + 1)))
    run_ctrl("NC-noHold", on_cfg("M2S72-H16N-nohold"))
    run_ctrl("NC-holdTimeout", on_cfg("M2S72-H16N-hto"))
    run_ctrl("NC-release", on_copy(rel))
    run_ctrl("NC-syncFrameId", on_copy(sfid))
    run_ctrl("NC-txStart", on_copy(lambda tmp: mutate_txstart(tmp, BASE, 1, s)))
    return out, s


# ------------------------------------------------------------------------------------------------ main ------------------
def report(title, ctrl=None, extra=None):
    print(title + "\n")
    for r in rows:
        print(" | ".join(r))
    by = Counter((r[0], r[2]) for r in rows)
    print("\nrows per family: " + ", ".join(f"{g} {by[(g, 'PASS')]} PASS / {by[(g, 'FAIL')]} FAIL" for g in sorted({r[0] for r in rows})))
    nf = sum(1 for r in rows if r[2] == "FAIL" and r[0] not in INFO)
    print(f"gate rows: {sum(1 for r in rows if r[0] not in INFO) - nf} PASS, {nf} FAIL (information rows {', '.join(INFO)} excluded)")
    for x in extra or []:
        print(x)
    nc = 0
    if ctrl is not None:
        print("\nI-2H negative controls (gate families; predictions declared before the runs):")
        for name, ok, fails, exp, info, mine in ctrl:
            nc += not ok
            print(f"{'PASS' if ok else 'FAIL'} | {name} | failed {sorted(fails)}, predicted {sorted(exp)} | information rows {info}")
            for r in mine:
                if r[2] == "FAIL":
                    print("      " + " | ".join(r)[:500])
        print(f"controls: {len(ctrl) - nc} PASS, {nc} FAIL")
    return nf, nc


def main():
    mode = sys.argv[1]
    if mode == "obs":
        runs, cfg, base = sys.argv[2:5]
        ref = None
        ev, stats, cov, st, fails, info = evaluate_h(runs, cfg, 0, ref, base)
        nf, _ = report(f"I-2H on the observation record {cfg} (evaluated as {base}), seed 0")
        print(f"DS-TT 1: hold {st[1]['hold']}, release {st[1]['release']}, corrected {st[1]['corrected']}, held FUs {st[1]['held_fu']}, "
              f"FIFO replay {st[1]['port_frames']} frames / {st[1]['fifo_dev']} deviations")
        return 0 if nf == 0 else 1
    out = sys.argv[2]
    runs = os.path.join(out, "runs")
    refs = {}
    for o in B.OPTS:
        for rep in B.REPS:
            ev, _, _ = B.evaluate(runs, f"M2S72-B-{o}-Ca-n1", rep)
            refs[(o, rep)] = ev
    extra = []
    for o, ns in (("q0", (2, 4)), ("qdu", (2,))):
        for n in ns:
            cfg = f"M2S72-H16-{o}-Ca-n{n}"
            for rep in B.REPS:
                ev, stats, cov, st, fails, info = evaluate_h(runs, cfg, rep, refs[(o, rep)], f"M2S72-H-{o}-Ca-n{n}")
                c01 = cov[(0, 1)]
                extra.append(f"{cfg}-{rep}: DS-TT 1 hold {st[1]['hold']} release {st[1]['release']} corrected {st[1]['corrected']}; pair (0,1) "
                             f"common {c01['com']}, Res differ {c01['dres']}, s2 differ {c01['ds2']}, non-zero GM-drift {c01['nz']}, "
                             f"case A {c01['A']} / case B {c01['B']}; info {info}")
                if cfg == BASE and rep == 0:
                    ok = st[1]["hold"] > 0 and st[1]["release"] > 0 and c01["dres"] > 0 and c01["nz"] > 0
                    B.add("H-nv", f"{cfg}-{rep}", ok, f"DS-TT 1 holds {st[1]['hold']}, releases {st[1]['release']}; pair (0,1) Res_0 != Res_1 on "
                          f"{c01['dres']} common Follow_Ups, non-zero GM-drift pair contributions {c01['nz']}")
    ctrl, s = controls(runs)
    extra.append(f"control mutations target the Follow_Up {s} (the middle hold of DS-TT 1 in {BASE}-0)")
    nf, nc = report("M2-S7.2a I-2H focused validation (Block H + HARQ16 experimental control; I-2H; controls)", ctrl, extra)
    print("focused validation verdict: " + ("PASS" if nf == 0 and nc == 0 else "FAIL (stop and report)"))
    return 0 if nf == 0 and nc == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
