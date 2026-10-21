"""M2-S7.1 gates P0, C0, Q0a and Q0b (migration/m2-s7.1-design.md rev. 3, sections 3.5, 4, 5).
Called by gate_m2s71.py gates <results/M2-S7.1> <results>.

P0  prefix equivalence:
    (i)  every config with a 10 s twin (runs-10s, seed 0): every PCAP record (bytes, direction, time),
         every log line and every vector value with time < 10 s identical to the 12 s run; same cohort
    (ii) M2-S6 C-a / B-p100 regenerated at the current code (runs-m2s6ref, seeds 0-4): PCAP/log hashes
         = the committed M2-S6 record first; then the 12 s Q-0 accuracy runs are identical to them below
         the M2-S6 5GS run length (5 s), with the same number of GM Syncs before 5 s (deviation D-1)
    excluded: scalars, statistics written at finish(), vector end markers, the 12 s runs' own extra
    vectors (only vectors present in both runs are compared)
C0  cohort boundary: cohort = GM-wire Syncs with transmission start < 10 s; every cohort Follow_Up
    found by sequenceId; size = the 10 s twin's GM Sync count
Q0a QFI of every gPTP frame on N3 (GTP-U PDU Session Container), per message class
Q0b RLC replay of the gPTP DRB(s) (UM, the M1 O-tail model): Q0b-1 slack rule, Q0b-2 deliveries,
    Q0b-3 Follow_Up classification against PCAP, Q0b-4 AM (NOT EVALUATED without a validated AM
    replay), Q0b-5 split-DRB counterfactual. Written to gate-Q0b.txt with the input hashes.
"""
import hashlib
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s71_lib as L  # noqa: E402
import pcapng  # noqa: E402

C5 = L.C5
S, MS = L.S, L.MS
NSX = L.NS
PHASE_RE = None


def sha(path):
    with open(path, "rb") as fh:
        return hashlib.sha256(fh.read()).hexdigest()


def run_dirs(root):
    return sorted(d for d in os.listdir(root) if d.startswith("M2S71-") and os.path.isdir(os.path.join(root, d))) if os.path.isdir(root) else []


def reps_of(root, cfg):
    d = os.path.join(root, cfg, "pcap")
    return sorted(int(x.rsplit("-", 1)[1]) for x in os.listdir(d)) if os.path.isdir(d) else []


# --- prefix comparison -------------------------------------------------------------------------
def pcap_prefix(path, t):
    return [(p["t_ps"], p["dir"], bytes(p["data"])) for p in pcapng.read(path) if p["t_ps"] < t]


def log_prefix(path, t):
    out = []
    seconds = ".measurementLayer." in os.path.basename(path)
    with open(path) as fh:
        head = fh.readline()
        for line in fh:
            f = line.split(",", 2)
            if len(f) < 2:
                continue
            v = f[1]
            # integer ps (M2-S4 and later logs) or decimal seconds (M2-S0 TtTimestampLayer logs)
            if v == "":
                continue    # rows without a time are written at the end of the run (e.g. "pending"): excluded
            # M2-S0/S1 measurementLayer logs write seconds; every later log writes integer ps
            tv = pcapng.simtime_ps(v) if seconds else (int(v) if v.isdigit() else None)
            if tv is None:
                raise ValueError(f"no time in {path}: {line[:60]}")
            if tv < t:
                out.append(line)
    return head, out


def vec_prefix(path, t):
    V = L.RR.read_vectors(path)
    return {k: [x for x in v if x[0] < t] for k, v in V.items()}


def tree_offset(pa, pb):
    """If two log prefixes differ only in the treeId column, by one constant, return that constant, else None.
    OMNeT++ draws message (tree) ids from a process-wide counter that is not reset between runs, so a run's ids
    depend on how many messages the earlier runs in the same process created (a 12 s run creates more than a 5 s
    one); a constant offset means the same messages were created in the same order."""
    (ha, ra), (hb, rb) = pa, pb
    if ha != hb or len(ra) != len(rb) or "treeId" not in ha.strip().split(","):
        return None
    k = ha.strip().split(",").index("treeId")
    offs = set()
    for x, y in zip(ra, rb):
        x, y = x.rstrip("\n").split(","), y.rstrip("\n").split(",")
        if x[:k] + x[k + 1:] != y[:k] + y[k + 1:]:
            return None
        if x[k] != y[k]:
            if not (x[k].isdigit() and y[k].isdigit()):
                return None
            offs.add(int(x[k]) - int(y[k]))
    return offs.pop() if len(offs) == 1 else (0 if not offs else None)


def prefix_equal(rootA, cfgA, repA, rootB, cfgB, repB, t, logs=True, tree_offsets=None):
    """(n compared, list of differences). With tree_offsets (a set), a log that differs only by a constant treeId
    offset (tree_offset) is not a difference; the offset is added to the set (the caller requires one per run)."""
    diffs, n = [], 0
    pa, pb = os.path.join(rootA, cfgA, "pcap", f"{cfgA}-{repA}"), os.path.join(rootB, cfgB, "pcap", f"{cfgB}-{repB}")
    fa, fb = set(os.listdir(pa)), set(os.listdir(pb))
    if fa != fb:
        diffs.append(f"PCAP sets differ: {sorted(fa ^ fb)[:3]}")
    for f in sorted(fa & fb):
        n += 1
        if pcap_prefix(os.path.join(pa, f), t) != pcap_prefix(os.path.join(pb, f), t):
            diffs.append(f"PCAP {f}")
    if logs:
        la, lb = os.path.join(rootA, cfgA, "m2log", f"{cfgA}-{repA}"), os.path.join(rootB, cfgB, "m2log", f"{cfgB}-{repB}")
        ga = {f for f in os.listdir(la) if not f.endswith(".monitor.csv")} if os.path.isdir(la) else set()
        gb = {f for f in os.listdir(lb) if not f.endswith(".monitor.csv")} if os.path.isdir(lb) else set()
        if ga != gb:
            diffs.append(f"log sets differ: {sorted(ga ^ gb)[:3]}")
        for f in sorted(ga & gb):
            n += 1
            xa, xb = log_prefix(os.path.join(la, f), t), log_prefix(os.path.join(lb, f), t)
            if xa != xb:
                off = tree_offset(xa, xb) if tree_offsets is not None else None
                if off is None:
                    diffs.append(f"log {f}")
                else:
                    tree_offsets.add(off)
        ma = [f for f in (os.listdir(la) if os.path.isdir(la) else []) if f.endswith(".monitor.csv")]
        mb = [f for f in (os.listdir(lb) if os.path.isdir(lb) else []) if f.endswith(".monitor.csv")]
        for f in sorted(set(ma) & set(mb)):
            n += 1
            if log_prefix(os.path.join(la, f), t) != log_prefix(os.path.join(lb, f), t):
                diffs.append(f"monitor log {f}")
    va = vec_prefix(os.path.join(rootA, cfgA, cfgA, f"{repA}.vec"), t)
    vb = vec_prefix(os.path.join(rootB, cfgB, cfgB, f"{repB}.vec"), t)
    common = set(va) & set(vb)
    for k in sorted(common):
        n += 1
        if va[k] != vb[k]:
            diffs.append(f"vector {k[0]} {k[1]}")
    return n, diffs, len(common), len(set(va) - set(vb)), len(set(vb) - set(va))


def gm_syncs_before(root, cfg, rep, t):
    fr = C5.frames(os.path.join(root, cfg, "pcap", f"{cfg}-{rep}", "M1Bridge.listener.pcapRecorder[0].pcapng"))
    return sorted(f["seq"] for f in C5.sel(fr, 2, L.SYNC) if f["start"] < t)


def ref_hashes(path):
    out = {}
    for line in open(path):
        h, p = line.split()
        out[p[2:]] = h
    return out


def p0(out, results, add):
    runs, twins = os.path.join(out, "runs"), os.path.join(out, "runs-10s")
    tw = run_dirs(twins)
    bad, ncmp, nvec, extra_v = [], 0, 0, 0
    for cfg in tw:
        n, diffs, nc, xa, xb = prefix_equal(runs, cfg, 0, twins, cfg, 0, 10 * S)
        ncmp += n
        nvec += nc
        if xb:
            diffs.append(f"{xb} vectors only in the 10 s twin")
        extra_v += xa
        c12, c10 = gm_syncs_before(runs, cfg, 0, 10 * S), gm_syncs_before(twins, cfg, 0, 10 * S)
        if c12 != c10:
            diffs.append(f"cohort {len(c12)} vs {len(c10)}")
        if diffs:
            bad.append((cfg, diffs[:3]))
    add("P0 (i) prefix equivalence 12 s vs 10 s", f"{len(tw)} configs (seed 0): {ncmp} PCAP/log/vector streams compared below 10 s, "
        f"{len(tw) - len(bad)} identical; vectors only in the 12 s run (end-of-run, excluded): {extra_v}", tw and not bad, str(bad[:3]))
    # (ii)
    r6 = ref_hashes(os.path.join(results, "M2-S6", "raw-outputs.sha256"))
    ref = os.path.join(out, "runs-m2s6ref")
    tot = same = 0
    for cfg in ("M2S6-C-a", "M2S6-B-p100"):
        for rep in range(5):
            for sub in ("pcap", "m2log"):
                d = os.path.join(ref, cfg, sub, f"{cfg}-{rep}")
                for f in sorted(os.listdir(d)):
                    k = f"{cfg}/{sub}/{cfg}-{rep}/{f}"
                    tot += 1
                    same += r6.get(k) == sha(os.path.join(d, f))
            want = sum(1 for k in r6 if k.startswith(f"{cfg}/pcap/{cfg}-{rep}/") or k.startswith(f"{cfg}/m2log/{cfg}-{rep}/"))
            tot += want - sum(1 for sub in ("pcap", "m2log") for _ in os.listdir(os.path.join(ref, cfg, sub, f"{cfg}-{rep}")))
    add("P0 (ii) regenerated M2-S6 C-a / B-p100 (seeds 0-4) = committed M2-S6 record", f"{same}/{tot} PCAP/log hashes identical",
        tot > 0 and same == tot)
    bad, shifted = [], []
    for mine, theirs in (("M2S71-q0-Ca", "M2S6-C-a"), ("M2S71-q0-Bp100", "M2S6-B-p100")):
        for rep in range(5):
            offs = set()
            n, diffs, nc, xa, xb = prefix_equal(runs, mine, rep, ref, theirs, rep, 5 * S, tree_offsets=offs)
            if len(offs) > 1:
                diffs.append(f"treeId offsets differ between logs: {sorted(offs)}")
            elif offs:
                shifted.append((mine, rep, offs.pop()))
            if xb:
                diffs.append(f"{xb} vectors only in M2-S6")
            if gm_syncs_before(runs, mine, rep, 5 * S) != gm_syncs_before(ref, theirs, rep, 5 * S):
                diffs.append("GM Syncs before 5 s differ")
            if diffs:
                bad.append((mine, rep, diffs[:3]))
    add("P0 (ii) Q-0 accuracy runs (12 s) vs M2-S6 below 5 s", f"M2S71-q0-Ca / -Bp100 seeds 0-4 identical to M2S6-C-a / -B-p100 below 5 s "
        "(every PCAP record, log line, common vector; same GM Syncs); attributed: in "
        f"{len(shifted)} runs the logs' treeId column differs by one constant per run {shifted} (process-wide message id "
        "counter, not reset between the runs of one process; every other column identical)", not bad, str(bad[:3]))


# --- C0 --------------------------------------------------------------------------------------------
def c0(out, add):
    runs, twins = os.path.join(out, "runs"), os.path.join(out, "runs-10s")
    bad, n = [], 0
    for cfg in run_dirs(runs):
        for rep in reps_of(runs, cfg):
            run = L.Run(runs, cfg, rep)
            if run.end < 10 * S:
                continue
            n += 1
            co = run.cohort()
            fu = run.gm_tx(L.FU)
            miss = [s for s in co if s not in fu]
            if miss:
                bad.append((cfg, rep, "FU missing", miss[:3]))
            if rep == 0 and os.path.isdir(os.path.join(twins, cfg)):
                tw = gm_syncs_before(twins, cfg, 0, 10 * S)
                if tw != co:
                    bad.append((cfg, rep, "twin", len(tw), len(co)))
    add("C0 cohort boundary", f"{n} runs: cohort = GM-wire Syncs starting before 10 s; every cohort Follow_Up on the GM wire; "
        "cohort = the 10 s twin's GM Syncs (seed 0)", n and not bad, str(bad[:3]))


# --- Q0a -------------------------------------------------------------------------------------------
def q0a(out, add, controls=False):
    runs = os.path.join(out, "runs")
    res = {}
    for cfg in run_dirs(runs):
        if "-N-" in cfg or "-T-" in cfg:
            continue
        opt = cfg.split("-")[1]
        if opt not in L.OPTIONS:
            continue
        want = L.QFI[opt]
        want = tuple(0 if w is None else w for w in want)
        cnt, badn = Counter(), 0
        for rep in reps_of(runs, cfg):
            path = os.path.join(runs, cfg, "pcap", f"{cfg}-{rep}", "M1Bridge.upf.pcapRecorder[0].pcapng")
            for direction, qfi, inner in C5.n3_inner(path):
                if direction != 2 or len(inner) < 15 or inner[12:14] != b"\x88\xf7":
                    continue
                t = inner[14] & 15
                if t not in (L.SYNC, L.FU):
                    continue
                cnt[(t, qfi)] += 1
                if qfi != (want[0] if t == L.SYNC else want[1]):
                    badn += 1
        res[cfg] = (cnt, badn)
    bad = {c: v for c, v in res.items() if v[1] or not v[0]}
    by_opt = defaultdict(Counter)
    for c, (cnt, _) in res.items():
        by_opt[c.split("-")[1]].update(cnt)
    add("Q0a QFI on N3 per message class", f"{len(res)} configs, all seeds: DL Sync/Follow_Up QFIs as configured "
        f"({'; '.join(f'{L.LABEL[o]}: ' + ', '.join(f'{(chr(83) if t == 0 else chr(70))}->{q} x{n}' for (t, q), n in sorted(c.items())) for o, c in sorted(by_opt.items()))})",
        res and not bad, str(list(bad.items())[:2]))
    return res


# --- Q0b -------------------------------------------------------------------------------------------
WINDOW = 50 * MS      # an RLC PDU / SDU is looked for at the UE up to 50 ms after it left the gNB RLC


AIR = 4 * MS     # observed RLC TX PDU -> UE RX PDU delays are 1..4 ms (slot-aligned; HARQ retransmissions reorder blocks)


def pdu_receptions(pdus, rxpdus):
    """Maximum matching of TX PDUs to RX PDUs of equal size received 0..AIR later (interval graph: earliest-first
    greedy per size is maximum). Not order-preserving, since HARQ retransmissions reorder transport blocks.
    Returns (set of received TX PDU indices, RX PDUs without a TX PDU)."""
    from collections import deque
    by = defaultdict(list)
    for k, (t, s) in enumerate(pdus):
        by[s].append((t, k))
    pend, got, orphan = defaultdict(deque), set(), []
    ptr = Counter()
    for t, s in rxpdus:
        lst, q = by[s], pend[s]
        while ptr[s] < len(lst) and lst[ptr[s]][0] <= t:
            q.append(lst[ptr[s]])
            ptr[s] += 1
        while q and q[0][0] < t - AIR:
            q.popleft()                                   # too old to be received any more: destroyed
        if q:
            got.add(q.popleft()[1])
        else:
            orphan.append((t, s))
    return got, orphan


def deliveries(done, deliv, rxpdus, pdus, sdus, horizon=None):
    """Replay of the UE side of one UM DRB (O-tail rule), independent of the run's own pairing:
      1. timing: every completed SDU not destroyed is delivered exactly 4 ms after its last PDU. SDUs of equal size
         completed in the same slot are interchangeable, so predicted and observed deliveries are compared as
         (time, size) multisets: every observed delivery must be predicted (no other timing);
      2. losses: TX PDUs are matched to RX PDUs (pdu_receptions); a TX PDU without one was destroyed, and an SDU is
         destroyed iff one of its own PDUs (L.pdu_owner) was. Within a (slot, size) class the undelivered SDUs are
         taken to be those with a destroyed PDU (they are interchangeable); an undelivered SDU without one is
         unexplained. Equal-size PDUs sent within AIR of each other are interchangeable too, so for the 1420 B
         data SDUs this attribution can be ambiguous; gPTP SDUs have unique sizes and are attributed exactly.
    Returns (matched [(arr, size, t_last, t_deliv)], unmatched [(arr, size, t_last, status)] with status True =
    destroyed (explained), "inflight" = predicted delivery after the horizon, False = unexplained; observed
    deliveries not predicted (plus RX PDUs without a TX PDU, size None); destroyed PDUs)."""
    got, orphan = pdu_receptions(pdus, rxpdus)
    own = L.pdu_owner(sdus, pdus)
    # a PDU without reception is destroyed only if its reception window closed before the horizon (else in flight)
    gone = [k for k in range(len(pdus)) if k not in got and (horizon is None or pdus[k][0] + AIR <= horizon)]
    lost_sdu = {own[k] for k in gone}
    obs = Counter(deliv)
    cls = defaultdict(list)
    for i, (a, size, tc) in enumerate(done):
        cls[(tc + 4 * MS, size)].append(i)
    matched, unmatched = [], []
    for p, idx in sorted(cls.items()):
        n_obs = min(obs[p], len(idx))
        obs[p] -= n_obs
        order = sorted(idx, key=lambda i: (i in lost_sdu, i))  # destroyed ones are the undelivered ones
        for i in order[:n_obs]:
            matched.append((done[i][0], done[i][1], done[i][2], p[0]))
        for i in order[n_obs:]:
            st = True if i in lost_sdu else ("inflight" if horizon is not None and p[0] > horizon else False)
            unmatched.append((done[i][0], done[i][1], done[i][2], st))
    matched.sort()
    rest = sorted(x for x, n in obs.items() for _ in range(n)) + [(t, None) for t, s in orphan]
    return matched, unmatched, rest, [pdus[k] for k in gone]


def q0b(out, add):
    runs = os.path.join(out, "runs")
    lines = []
    agg = defaultdict(lambda: Counter())
    notes = defaultdict(list)
    inputs = []
    delta_fu = Counter()
    fifo = []
    lag_bad = defaultdict(list)
    for cfg in run_dirs(runs):
        if "-T-" in cfg:
            continue
        opt = cfg.split("-")[1]
        if opt not in L.OPTIONS:
            continue
        ds, df, mode = L.OPTIONS[opt][:3]
        for rep in reps_of(runs, cfg):
            run = L.Run(runs, cfg, rep)
            inputs.append((cfg, rep, sha(run.R.vec_path)))
            if mode == "am":
                agg[cfg]["am_runs"] += 1
                continue
            for drb in sorted({ds, df}):
                d = L.rlc(run, opt, drb)
                done, slots, left = L.replay_um(d["sdus"], d["pdus"])
                c = agg[cfg]
                # Q0b-1
                for t, s in slots.items():
                    alloc = sum(s["pdus"]) + 2
                    demand = sum(r for r, _ in s["before"]) + 2 + 1
                    need = sum(r + (1 if fresh else 4) for r, fresh in s["before"]) + 2
                    if len(s["before"]) >= 2:
                        c["multi"] += 1
                        cut = bool(s["cut"])
                        c["cut"] += cut
                        if cut != (alloc < need):
                            c["slack_viol"] += 1
                            notes[cfg].append(("slack", rep, drb, t))
                        if alloc < demand:
                            c["demand_viol"] += 1
                    elif s["cut"] and s["before"][0][1]:
                        c["single_cut"] += 1
                # Q0b-2
                matched, unmatched, extra_rx, lostpdu = deliveries(done, d["deliv"], d["rxpdus"], d["pdus"], d["sdus"], run.end)
                c["sdus"] += len(d["sdus"])
                c["matched"] += len(matched)
                c["unmatched"] += sum(1 for u in unmatched if u[3] is True)
                c["inflight"] += sum(1 for u in unmatched if u[3] == "inflight")
                c["extra_rx"] += len(extra_rx)
                c["left"] += len(left)
                c["lostpdu"] += len(lostpdu)
                for a, size, tc, expl in unmatched:
                    if expl is False:                    # neither destroyed nor in flight, yet not delivered on time
                        c["unexplained"] += 1
                        notes[cfg].append(("unexplained", rep, drb, a))
                # Q0b-5
                if ds != df:
                    c["split_multi_gptp"] += sum(1 for s in slots.values()
                                                 if sum(1 for r, fr in s["before"]) >= 2)
                # Q0b-3: Follow_Ups (largest gPTP SDU size on the Follow_Up DRB)
                if drb == df:
                    gsz = sorted({sz for _, sz in d["sdus"]})
                    fusz = max(sz for sz in gsz if sz < 110)       # Follow_Up SDU (91/92 B); data frames are larger
                    cutarr = {a for s in slots.values() for a in s["cut"]}
                    fus = [(a, size, tc, t_rx) for a, size, tc, t_rx in matched if size == fusz]
                    ds0 = run.first(run.R.ds0, 1, L.FU)
                    port = os.path.join(run.R.ldir, "M1Bridge.dsTt.eth[0].measurementLayer.ingress.port.csv")
                    ends = sorted(pcapng.simtime_ps(x["t"]) for x in C5.read_csv(port) if x["event"] == "rx")
                    ds1 = run.first(run.R.ds1, 2, L.SYNC)
                    gmfu = sorted(run.gm_tx(L.FU).items(), key=lambda kv: kv[1]["start"])
                    # SDUs of size fusz on this DRB are the Follow_Ups, in GM order (the DRB is FIFO)
                    fu_sdus = [x for x in d["sdus"] if x[1] == fusz]
                    seq_of = {fu_sdus[i][0]: gmfu[i][0] for i in range(min(len(fu_sdus), len(gmfu)))}
                    for a, size, tc, t_rx in fus:
                        seq = seq_of.get(a)
                        if seq is None or seq not in ds0 or seq not in ds1:
                            continue
                        te = ds0[seq]["end"]
                        k = __import__("bisect").bisect_left(ends, te) - 1
                        prev = ends[k] if k >= 0 else -1
                        queued_end = prev + (ds0[seq]["L"] + 20) * 8 * NSX   # back-to-back after the previous frame (preamble + IFG 20 B)
                        delta_fu[("q" if te == queued_end else te - t_rx)] += 1
                        fifo.append((cfg, te - t_rx, te == queued_end))
                        c["fu_classified"] += 1
                        c["fu_cut"] += a in cutarr
                        lag_meas = ds0[seq]["end"] - ds1[seq]["start"]
                        agg[cfg]["_lags"] += 0
                        lag_bad[cfg].append((rep, seq, a in cutarr, t_rx, lag_meas))
    # the UE -> DS-TT link is a FIFO: a Follow_Up is received either c0 after its RLC delivery (one constant for all
    # Follow_Ups of all configs) or back to back after the previous frame; predicted lag = replayed delivery + that - TSe
    base = [k for k in delta_fu if k != "q"]
    dval = min(base) if base else None
    delta_ok = all(k == "q" or k == dval for k in delta_fu)
    bad3 = Counter(cfg for cfg, dl, q in fifo if not q and dl != dval)
    for cfg, c in sorted(agg.items()):
        if c["am_runs"]:
            lines.append(("Q0b-4 AM", cfg, None, f"{c['am_runs']} runs on RLC AM: NOT EVALUATED (no independently validated AM replay); "
                          "measured-only acceptance class"))
            continue
        ok1 = c["slack_viol"] == 0 and c["single_cut"] == 0
        lines.append(("Q0b-1 slack rule", cfg, ok1, f"{c['multi']} slots with >= 2 queued items, {c['cut']} cuts; cut iff grant < need "
                      f"(slack below the missing header bytes) in all: {c['slack_viol'] == 0}; single fresh SDU cut: {c['single_cut']}; "
                      f"slots granted less than the demand formula (resource-limited, reported): {c['demand_viol']}"))
        ok2 = c["unexplained"] == 0 and c["extra_rx"] == 0
        lines.append(("Q0b-2 replay", cfg, ok2, f"{c['sdus']} SDUs; predicted (time, size) deliveries = observed: {c['matched']} delivered "
                      f"exactly 4 ms after their last PDU; {c['unmatched']} lost, each with a PDU of its own never received ({c['lostpdu']} such "
                      f"PDUs); in flight at the end {c['inflight']}; "
                      f"unexplained {c['unexplained']}; observed but not predicted {c['extra_rx']}; left in the RLC at the end {c['left']}"))
        nq = sum(1 for cf, dl, q in fifo if cf == cfg and q)
        lines.append(("Q0b-3 Follow_Up classification", cfg, bad3[cfg] == 0 and c["fu_classified"] > 0,
                      f"{c['fu_classified']} Follow_Ups, {c['fu_cut']} cut (each completes only after the next SDU on its DRB); "
                      f"predicted lag = replayed RLC delivery + UE-to-DS-TT FIFO ({dval} ps unqueued, or back to back after the previous frame: "
                      f"{nq}) - TSe = PCAP lag for all but {bad3[cfg]}"))
        opt = cfg.split("-")[1]
        if L.OPTIONS[opt][0] != L.OPTIONS[opt][1]:
            lines.append(("Q0b-5 split counterfactual", cfg, c["cut"] == 0,
                          f"Sync and Follow_Up on separate DRBs: slots with >= 2 queued items {c['multi']}, cuts {c['cut']}"))
    return lines, inputs, lag_bad, dval


def gates(out, results, add):
    p0(out, results, add)
    c0(out, add)
    q0a(out, add)
    lines, inputs, lag_bad, dval = q0b(out, add)
    # gate-Q0b.txt is written before any Q2 statistic (design 4): rows, then the input hashes
    with open(os.path.join(out, "gate-Q0b.txt"), "w") as fh:
        npass = sum(1 for r in lines if r[2])
        nne = sum(1 for r in lines if r[2] is None)
        for row, cfg, ok, detail in lines:
            fh.write(f"[{'NOT EVALUATED' if ok is None else ('PASS' if ok else 'FAIL')}] {row} {cfg}: {detail}\n")
        nfail = sum(1 for r in lines if r[2] is False)
        fh.write(f"OVERALL: {'PASS' if nfail == 0 else 'FAIL'} ({npass} PASS, {nfail} FAIL, {nne} NOT EVALUATED)\n")
        fh.write(f"UE-to-DS-TT Follow_Up path delay (ps): {dval}\n")
        fh.write("inputs (config rep sha256 of the .vec):\n")
        for cfg, rep, h in inputs:
            fh.write(f"  {cfg} {rep} {h}\n")
    for row, cfg, ok, detail in lines:
        if ok is not None:
            add(f"{row} {cfg}", detail, ok)
