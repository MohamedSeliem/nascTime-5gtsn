#!/usr/bin/env python3
"""M2-S4 checker: link-local gPTP Pdelay termination at the translators' TSN ports
(migration/m2-s4-design.md, revision 2).

Usage: check_m2s4.py <results/M2-S4> <results/M2-S1/runs> <results/M2-S1/raw-outputs.sha256>

Independent of the engine code: every expected value is computed from PCAP (pcapng, 1 ps:
start = end - (L + 8) * 8 ns at 1 Gb/s, M2-S1 C2) and from decoded frame bytes; the INET
slave is replayed with the M2-S3 model (inet_model.py, oracle_m2s3.py), which reproduces it
exactly. Integer ps, exact comparisons, no tolerance.

Rows:
  G0 passive transparency (hard gate); A0 provenance of the M2-S1 inputs;
  aggregated over the M2S4 runs: T1 no Pdelay in the 5GS, T2 every received Pdelay terminated,
    T3 frame format, T4 first-bit timestamps, L1 NW-TT link delay vs PCAP, L2 DS-TT responder
    and slave vs PCAP (+ slave replay), S1 Sync/Follow_Up untouched, S2 slave clock = INET
    slave fed the new pdelay (step 1 = -(Lup + Res1)), S3 offline composition readiness,
    F fault counters; L3 load/fragmentation;
  F-5GS-* fault cases at the GM; U1-U4 and F-unit-* in the unit topology;
  R1 M2-S1 per-frame rows on M2S4 runs, R2 application traffic and QoS mapping vs M2S1,
  L4 baseline comparison, W1 wire-mode report;
  N* negative controls: each fails exactly its declared rows, with the exact signature.
"""
import csv
import os
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import pcapng  # noqa: E402
import inet_model as M  # noqa: E402
import gate_m2s4 as G  # noqa: E402

OUT, RUNS1, HASHES1 = sys.argv[1:4]
RUNS = os.path.join(OUT, "runs")
_argv = sys.argv
sys.argv = [_argv[0], RUNS, HASHES1, "-", "-"]
import oracle_m2s3 as O  # noqa: E402  (reads sys.argv at import)
sys.argv = _argv
O.RUNS = RUNS

NS = 1000
L_REF = 50 * NS
GPTP_DST = "0180c200000e"
SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10
PDELAY = (REQ, RESP, RFU)
TN = {SYNC: "Sync", FU: "Follow_Up", REQ: "Pdelay_Req", RESP: "Pdelay_Resp", RFU: "Pdelay_Resp_Follow_Up"}
ID_NW, ID_DS, ID_A, ID_B = 0xA1, 0xD1, 0x0A, 0x0B
COUNTERS = ("lost", "multipleResp", "orphanFollowUp", "staleSeq", "notForUs", "lateDuplicateResp", "lateDuplicateFU",
            "lateAfterFault", "malformed", "republished", "loopback")
X72 = (72 + 8) * 8 * NS        # Pdelay frame time at 1 Gb/s
IFG = 96 * NS

rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def fmt(p):
    return f"{p / NS:.3f} ns"


def floor_ns(p):
    return (p // NS) * NS


def ps(s):
    return pcapng.simtime_ps(s) if s not in ("", None) else None


# ---------------------------------------------------------------------------------------
# data access
def frames(path, direction=None):
    out = []
    for p in pcapng.read(path):
        if direction is not None and p["dir"] != direction:
            continue
        d, L = p["data"], len(p["data"])
        f = pcapng.ethernet(d)
        r = {"end": p["t_ps"], "start": p["t_ps"] - (L + 8) * 8 * NS, "L": L, "dir": p["dir"], "f": f, "g": None,
             "pdelay": False, "mtype": -1, "key": (f["etherType"], f["pcp"], f["vid"], pcapng.fnv1a64(f["payload"]))}
        if f["dst"] == GPTP_DST and f["etherType"] == 0x88F7:
            b = f["payload"]
            r["mtype"] = b[0] & 15 if b else -1
            r["pdelay"] = r["mtype"] in PDELAY
            try:
                r["g"] = O.decode(b)
            except ValueError:
                r["g"] = None
        out.append(r)
    return out


def wire(t):
    return t[0] * 10 ** 12 + t[1] * NS


def by_seq(fr, mtype, spi=None, reqport=None):
    d = defaultdict(list)
    for f in fr:
        g = f["g"]
        if g and g["type"] == mtype and (spi is None or g["spi"] == spi) and (reqport is None or g.get("reqPort") == reqport):
            d[g["seq"]].append(f)
    return d


def read_csv(path):
    if not os.path.exists(path):
        return None
    with open(path) as fh:
        return list(csv.DictReader(fh))


def scalars(path, module_suffix):
    out = {}
    with open(path) as fh:
        for line in fh:
            if line.startswith("scalar "):
                p = line.split()
                if p[1].endswith(module_suffix):
                    out[p[2]] = float(p[3])
    return out


def n3_inner(path):
    """N3 (UPF ppp[0]): GTP-U inner Ethernet frames after IPv4 reassembly: [(dir, QFI, bytes)]."""
    frags, dgrams = defaultdict(dict), []
    for p in pcapng.read(path):
        b = p["data"]
        off = 5 if b[1:3] == b"\xff\x03" else 3
        if struct.unpack(">H", b[off - 2: off])[0] != 0x0021:
            continue
        ip = b[off:]
        ihl, tot = (ip[0] & 15) * 4, struct.unpack(">H", ip[2:4])[0]
        ff = struct.unpack(">H", ip[6:8])[0]
        mf, fo = ff & 0x2000, (ff & 0x1FFF) * 8
        pl = ip[ihl:tot]
        if mf or fo:
            k = (ip[12:16], ip[16:20], ip[4:6], ip[9], p["dir"])
            frags[k][fo] = pl
            if not mf:
                frags[k]["end"] = fo + len(pl)
        else:
            dgrams.append((p["dir"], ip[9], pl))
    for k, d in frags.items():
        if "end" not in d:
            continue
        buf, pos = b"", 0
        while pos < d["end"] and pos in d:
            buf += d[pos]
            pos += len(d[pos])
        if pos == d["end"]:
            dgrams.append((k[4], k[3], buf))
    out = []
    for direction, proto, pl in dgrams:
        if proto != 17 or struct.unpack(">H", pl[2:4])[0] != 2152:
            continue
        g = pl[8:]
        if g[1] != 0xFF:
            continue
        h, qfi = 8, None
        if g[0] & 0x07:
            h, nxt = 12, g[11]
            while nxt:
                ln = g[h] * 4
                ext = g[h:h + ln]
                if nxt == 0x85:
                    qfi = ext[2] & 0x3F
                nxt = ext[-1]
                h += ln
        out.append((direction, qfi, g[h:]))
    return out


def inner_type(fr):
    """(is gPTP to 01-80-C2-00-00-0E, messageType, pcp) of a raw inner Ethernet frame."""
    if len(fr) < 15:
        return False, -1, -1
    et, off, pcp = struct.unpack(">H", fr[12:14])[0], 14, -1
    if et == 0x8100:
        pcp = fr[14] >> 5
        et, off = struct.unpack(">H", fr[16:18])[0], 18
    if fr[0:6].hex() == GPTP_DST and et == 0x88F7 and len(fr) > off:
        return True, fr[off] & 15, pcp
    return False, -1, pcp


# ---------------------------------------------------------------------------------------
# INET-equivalent link-delay arithmetic (design 4.6), independent of the engine
def link_delay(t1, t2, t3, t4, prev=None):
    """prev = (t3p, t4p) of the previous completed exchange or None; returns (D, e_q63)."""
    e = 0 if prev is None else M.from_integer_ratio(t3 - prev[0], t4 - prev[1])
    return M.trunc_div2(M.mul_round(t4 - t1, e) - (t3 - t2)), e


# ---------------------------------------------------------------------------------------
class Run5GS:
    def __init__(self, cfg, rep):
        self.cfg, self.rep = cfg, rep
        pdir = os.path.join(RUNS, cfg, "pcap", f"{cfg}-{rep}")
        ldir = os.path.join(RUNS, cfg, "m2log", f"{cfg}-{rep}")
        P = lambda n, i: os.path.join(pdir, f"M1Bridge.{n}.pcapRecorder[{i}].pcapng")  # noqa: E731
        self.gm = frames(P("listener", 0))
        self.nw1, self.ds1 = frames(P("nwTt", 1)), frames(P("dsTt", 1))
        self.sl = frames(P("talker", 0))
        self.nw0, self.ds0 = frames(P("nwTt", 0)), frames(P("dsTt", 0))
        self.ue, self.dn = frames(P("ue[0]", 0)), frames(P("upf", 1))
        self.n3 = n3_inner(P("upf", 0))
        sel = lambda fr, d: [f for f in fr if f["dir"] == d]  # noqa: E731
        self.gm_out, self.gm_in = sel(self.gm, 2), sel(self.gm, 1)
        self.nw_in, self.nw_out = sel(self.nw1, 1), sel(self.nw1, 2)
        self.ds_out, self.ds_in = sel(self.ds1, 2), sel(self.ds1, 1)
        self.sl_in, self.sl_out = sel(self.sl, 1), sel(self.sl, 2)
        eng = lambda tt: os.path.join(ldir, f"M1Bridge.{tt}.eth[1].trafficConditionerLayer.engine.pdelay.csv")  # noqa: E731
        self.nw_log, self.ds_log = read_csv(eng("nwTt")), read_csv(eng("dsTt"))
        self.sca = os.path.join(RUNS, cfg, cfg, f"{rep}.sca")
        self.vec = os.path.join(RUNS, cfg, cfg, f"{rep}.vec")
        self.nw_sc = scalars(self.sca, "nwTt.eth[1].trafficConditionerLayer.engine")
        self.ds_sc = scalars(self.sca, "dsTt.eth[1].trafficConditionerLayer.engine")
        self.ldir = ldir


class Slave:
    """Adapter to the M2-S3 oracle's slave_events: the slave's own frames, and the sim-mode
    timestamps it received (GM Sync first bit; DS-TT responder first bits)."""
    def __init__(self, R):
        self.sl_in = [{"end": f["end"], "start": f["start"], "g": f["g"]} for f in R.sl_in if f["g"]]
        self.sl_out = [{"end": f["end"], "start": f["start"], "g": f["g"]} for f in R.sl_out if f["g"]]
        self.sim_pot = {s: v[0]["start"] for s, v in by_seq(R.gm_out, SYNC).items()}
        self.sim_t2 = {s: v[0]["start"] for s, v in by_seq(R.ds_in, REQ).items()}
        self.sim_t3 = {s: v[0]["start"] for s, v in by_seq(R.ds_out, RESP).items()}


def rx_rows(log):
    return [r for r in (log or []) if r["event"] not in ("tx", "txEnd", "measure", "lost", "noPrevious", "republish")]


# ---------------------------------------------------------------------------------------
def eval_5gs(cfg, rep, exp_fault=None, exclude=()):
    """Per-run rows for a 5GS run: {row: (ok, detail)} and data for signatures."""
    R = Run5GS(cfg, rep)
    res, data = {}, {"R": R}
    # ---- T1 no Pdelay frame in the 5GS
    cnt = Counter()
    for name, fr in (("NW-TT eth[0]", R.nw0), ("DS-TT eth[0]", R.ds0), ("UE eth[0]", R.ue), ("UPF dnEth", R.dn)):
        for f in fr:
            if f["pdelay"]:
                cnt[f"{name} {TN[f['mtype']]}"] += 1
            elif f["g"] and f["g"]["type"] in (SYNC, FU):
                cnt[f"(sync) {name}"] += 1
    for direction, qfi, inner in R.n3:
        isg, mt, _ = inner_type(inner)
        if isg and mt in PDELAY:
            cnt[f"N3 {TN[mt]}"] += 1
        elif isg:
            cnt["(sync) N3"] += 1
    bad = {k: v for k, v in cnt.items() if not k.startswith("(sync)")}
    data["T1"] = bad
    res["T1"] = (not bad, f"Pdelay frames in the 5GS: {bad or 0}; Sync/Follow_Up frames seen: "
                 f"{ {k[7:]: v for k, v in cnt.items() if k.startswith('(sync)')} }")
    # ---- T2 every Pdelay frame received at a TT eth[1] is terminated
    probs = []
    for name, fr, log, sc in (("NW-TT", R.nw_in, R.nw_log, R.nw_sc), ("DS-TT", R.ds_in, R.ds_log, R.ds_sc)):
        pc = Counter((f["start"], f["end"]) for f in fr if f["pdelay"])
        lg = Counter((int(r["tA"]), int(r["tB"])) for r in rx_rows(log))
        if pc != lg:
            probs.append(f"{name}: {sum(pc.values())} received, {sum(lg.values())} terminated")
        passed = {k: v for k, v in sc.items() if k.startswith("passed") and v}
        if passed:
            probs.append(f"{name}: engine passed {passed}")
    data["T2"] = probs
    res["T2"] = (not probs, f"problems: {probs or 'none'}")
    # ---- T3 frame format of every Pdelay frame sent on a TT eth[1] (= the engine's frames)
    probs, n = [], 0
    for name, fr, ident in (("NW-TT", R.nw_out, ID_NW), ("DS-TT", R.ds_out, ID_DS)):
        srcs = set()
        for f in fr:
            if not f["pdelay"]:
                continue
            n += 1
            g = f["g"]
            srcs.add(f["f"]["src"])
            if not (g and f["L"] == 72 and f["f"]["fcs_ok"] and f["f"]["vid"] == -1 and g["versionPTP"] == 2
                    and g["messageLength"] == 54 and g["domain"] == 0 and g["spi"] == (ident, 1)):
                probs.append(f"{name} {TN.get(f['mtype'])} seq {g and g['seq']}: format")
        if len(srcs) > 1:
            probs.append(f"{name}: several source MACs {srcs}")
    reqs = [f["g"]["seq"] for f in R.nw_out if f["pdelay"] and f["g"] and f["g"]["type"] == REQ]
    if any((b - a) % 65536 != 1 for a, b in zip(reqs, reqs[1:])):
        probs.append(f"NW-TT Pdelay_Req sequenceIds not consecutive: {reqs}")
    out_resp, out_rfu = by_seq(R.ds_out, RESP), by_seq(R.ds_out, RFU)
    last = R.ds1[-1]["end"]
    for f in R.ds_in:
        if f["pdelay"] and f["g"] and f["g"]["type"] == REQ:
            s, spi = f["g"]["seq"], f["g"]["spi"]
            ok = any(x["g"]["reqPort"] == spi for x in out_resp.get(s, [])) and any(x["g"]["reqPort"] == spi for x in out_rfu.get(s, []))
            if not ok and f["end"] < last:    # the slave's last request may be unanswered at the end of the run
                probs.append(f"DS-TT: no Resp/Resp_FU echoing slave Req seq {s}")
    data["T3"] = probs
    res["T3"] = (not probs, f"{n} engine frames; problems: {probs[:4] or 'none'}")
    # ---- T4 first-bit timestamps in the engine logs = PCAP
    probs = []
    for name, fr, log in (("NW-TT", R.nw_out, R.nw_log), ("DS-TT", R.ds_out, R.ds_log)):
        pc = Counter((f["start"], f["end"]) for f in fr if f["pdelay"])
        lg = Counter((int(r["tA"]), int(r["tB"])) for r in (log or [])
                     if (r["event"] == "tx" and r["msgType"] in ("3", "10")) or (r["event"] == "txEnd" and r["msgType"] == "2"))
        if pc != lg:
            probs.append(f"{name}: {sum(pc.values())} sent, {sum(lg.values())} logged with equal (start, end)")
        starts = {f["start"] for f in fr if f["pdelay"]}
        ended = {r["seq"] for r in log or [] if r["event"] == "txEnd"}   # PCAP records at the end of transmission
        for r in log or []:
            if r["event"] == "tx" and r["msgType"] == "2" and r["seq"] in ended and int(r["tA"]) not in starts:
                probs.append(f"{name}: Req seq {r['seq']} t1 not a PCAP first bit")
    data["T4"] = probs
    res["T4"] = (not probs, f"problems: {probs[:4] or 'none'}")
    # ---- L1 NW-TT requester vs PCAP (t1, t4 at NW-TT eth[1]; t2, t3 at the GM)
    probs, Ds, prev, pub = [], [], None, []
    o_req, i_resp, i_rfu = by_seq(R.nw_out, REQ), by_seq(R.nw_in, RESP), by_seq(R.nw_in, RFU)
    g_req, g_resp = by_seq(R.gm_in, REQ), by_seq(R.gm_out, RESP)
    measures = [r for r in (R.nw_log or []) if r["event"] in ("measure", "republish")]
    seqs = [int(r["seq"]) for r in measures if r["event"] == "measure"]
    if len(seqs) != len(set(seqs)) or any(r["event"] == "republish" for r in measures):
        probs.append(f"published more than once: {[(r['seq'], r['D']) for r in measures if r['event'] == 'republish']}")
    expected = sorted(s for s in o_req if s in i_resp and s in i_rfu and s not in exclude)
    if sorted(seqs) != expected:
        probs.append(f"published seqs {sorted(seqs)} != expected {expected}")
    for r in measures:
        if r["event"] != "measure":
            continue
        s = int(r["seq"])
        pub.append((s, int(r["D"])))
        try:
            t1, t4 = o_req[s][0]["start"], i_resp[s][0]["start"]
            t2, t3 = g_req[s][0]["start"], g_resp[s][0]["start"]
        except (KeyError, IndexError):
            probs.append(f"seq {s}: missing PCAP frame")
            continue
        D, e = link_delay(t1, t2, t3, t4, prev)
        prev = (t3, t4)
        Ds.append(int(r["D"]))
        lt = tuple(int(r[k]) for k in ("t1", "t2", "t3", "t4"))
        if lt != (t1, t2, t3, t4):
            probs.append(f"seq {s}: logged t1..t4 {lt} != PCAP {(t1, t2, t3, t4)}")
        if wire(i_resp[s][0]["g"]["ts"]) != floor_ns(t2) or wire(i_rfu[s][0]["g"]["ts"]) != floor_ns(t3):
            probs.append(f"seq {s}: wire t2/t3 != floor_ns(PCAP)")
        if int(r["D"]) != D or D != L_REF:
            probs.append(f"seq {s}: D logged {r['D']}, from PCAP {D}, reference {L_REF}")
        if seqs.index(s) > 0 and int(r["nrrNum"]) != int(r["nrrDen"]):
            probs.append(f"seq {s}: nRR {r['nrrNum']}/{r['nrrDen']}")
    data["L1"] = {"pub": pub, "o_req": o_req, "i_resp": i_resp, "i_rfu": i_rfu, "g_req": g_req, "g_resp": g_resp,
                  "measures": measures}
    res["L1"] = (not probs and len(Ds) > 0, f"{len(Ds)} exchanges, D {sorted(set(Ds)) or '-'} ps; problems: {probs[:4] or 'none'}")
    # ---- L2 DS-TT responder + slave vs PCAP, and slave replay
    probs = []
    s_req, d_req, d_resp, d_rfu, s_resp = (by_seq(R.sl_out, REQ), by_seq(R.ds_in, REQ), by_seq(R.ds_out, RESP),
                                           by_seq(R.ds_out, RFU), by_seq(R.sl_in, RESP))
    raw, prev = [], None
    rx2 = {int(r["seq"]): int(r["tA"]) for r in (R.ds_log or []) if r["event"] == "rx" and r["msgType"] == "2"}
    tx3 = {int(r["seq"]): int(r["tA"]) for r in (R.ds_log or []) if r["event"] == "tx" and r["msgType"] == "3"}
    for s in sorted(s_resp):
        if s not in d_rfu or s not in s_req or s not in d_req:
            continue
        t1, t2, t3, t4 = s_req[s][0]["start"], d_req[s][0]["start"], d_resp[s][0]["start"], s_resp[s][0]["start"]
        if rx2.get(s) != t2 or tx3.get(s) != t3:
            probs.append(f"seq {s}: engine t2/t3 {rx2.get(s)}/{tx3.get(s)} != PCAP {t2}/{t3}")
        if wire(d_resp[s][0]["g"]["ts"]) != floor_ns(t2) or wire(d_rfu[s][0]["g"]["ts"]) != floor_ns(t3):
            probs.append(f"seq {s}: wire t2/t3 != floor_ns(PCAP first bits)")
        D, e = link_delay(t1, t2, t3, t4, prev)
        prev = (t3, t4)
        raw.append(D)
        if D != L_REF:
            probs.append(f"seq {s}: slave raw D from PCAP {D}")
    V = O.read_vec(R.vec)
    pd_rec = [float(v) for t, v in V["pdelay"]]
    nrr_rec = [float(v) for t, v in V["nrr"]]
    if not pd_rec or any(v != O.dbl(L_REF) for v in pd_rec) or any(v != 1.0 for v in nrr_rec):
        probs.append(f"slave recorded pdelay {sorted(set(pd_rec))}, nRR {sorted(set(nrr_rec))}")
    M.STRICT_INET_ASSERTS = False   # release INET (NDEBUG): negative delays are accepted (N3b)
    msim = O.model(Slave(R), "sim")
    okc1, counts, mm = O.compare_recorded(None, msim, V)
    if not okc1:
        probs.append(f"slave replay (M2-S3 model) differs: {dict(mm)}")
    data["L2"] = {"pd_rec": pd_rec, "raw": raw, "d_rfu": d_rfu, "d_resp": d_resp}
    res["L2"] = (not probs and len(raw) > 0, f"{len(raw)} slave exchanges (raw D {sorted(set(raw)) or '-'} ps); slave "
                 f"pdelay samples {len(pd_rec)}; replay {counts}; problems: {probs[:4] or 'none'}")
    # ---- S1 Sync/Follow_Up untouched
    probs = []
    gm_s = [f["f"]["payload"] for f in R.gm_out if f["g"] and f["g"]["type"] in (SYNC, FU)]
    sl_s = [f["f"]["payload"] for f in R.sl_in if f["g"] and f["g"]["type"] in (SYNC, FU)]
    it = iter(gm_s)
    if not all(any(x == y for y in it) for x in sl_s):
        probs.append("slave Sync/Follow_Up not an in-order byte-identical subsequence of the GM's")
    if any(f["g"]["cf_raw"] != 0 for f in R.sl_in if f["g"] and f["g"]["type"] in (SYNC, FU)):
        probs.append("non-zero correctionField at the slave")
    res["S1"] = (not probs, f"{len(sl_s)} of {len(gm_s)} Sync/Follow_Up delivered byte-identical, correctionField 0; "
                 f"problems: {probs or 'none'}")
    # ---- S2 slave clock = INET slave with the new pdelay; step 1 = -(Lup + Res1)
    probs = []
    nw_sync, ds_sync, gm_sync = by_seq(R.nw_in, SYNC), by_seq(R.ds_out, SYNC), by_seq(R.gm_out, SYNC)
    res_k, lup_k = {}, {}
    for s in nw_sync:
        if s in ds_sync and s in gm_sync:
            res_k[s] = ds_sync[s][0]["start"] - nw_sync[s][0]["start"]    # first-bit residence
            lup_k[s] = nw_sync[s][0]["start"] - gm_sync[s][0]["start"]
    fu = msim.out["fu"]
    step1 = fu[0]["new"] - fu[0]["t"] if fu else None
    exp1 = -(lup_k[fu[0]["seq"]] + res_k[fu[0]["seq"]]) if fu else None
    if not okc1:
        probs.append("replay differs (L2)")
    if step1 is None or step1 != exp1:
        probs.append(f"error after step 1 {step1} != -(Lup + Res1) {exp1}")
    sample_t = sorted({O.ps(t) for t, v in V["clock"]})
    fs = msim.clk.steps[0][0] if msim.clk.steps else 0
    st = [t for t in sample_t if t > fs]
    rec_err = [v - t for v, t in zip(O.replay_at(msim.clk.steps, 0, st), st)]
    data["S2"] = {"step1": step1, "exp1": exp1, "maxerr": max(map(abs, rec_err)) if rec_err else None}
    res["S2"] = (not probs, f"error after step 1 {fmt(step1) if step1 is not None else '-'} (= -(Lup + Res1) "
                 f"{fmt(exp1) if exp1 is not None else '-'}); recorded max|error| after step 1 "
                 f"{fmt(max(map(abs, rec_err))) if rec_err else '-'} (NOT synchronized: no residence correction); "
                 f"problems: {probs or 'none'}")
    # ---- S3 offline: cf' = D_NWTT (measured) + Res, slave's OWN pdelay -> 0 ps
    probs = []
    meas = sorted((int(r["t"]), int(r["D"])) for r in (R.nw_log or []) if r["event"] == "measure")

    def cfp(f):
        s = f["g"]["seq"]
        t_in = nw_sync[s][0]["start"]
        d = [D for t, D in meas if t <= t_in]
        if not d:
            raise KeyError("no NW-TT measurement before this Sync")
        return d[-1] + res_k[s]
    try:
        m = O.model(Slave(R), "sim", cf_fn=cfp)
        aft = [x["new"] - x["t"] for x in m.out["fu"]]
        arr = [x["t2"] - x["ts"] for x in m.out["fu"]][1:]
        fs = m.clk.steps[0][0]
        st = [t for t in sample_t if t > fs]
        per = [v - t for v, t in zip(O.replay_at(m.clk.steps, 0, st), st)]
        if any(aft) or any(arr) or any(per):
            probs.append(f"max|error| after steps {max(map(abs, aft))}, arrivals {max(map(abs, arr)) if arr else 0}, "
                         f"periodic {max(map(abs, per)) if per else 0} ps")
        n_s3 = (len(aft), len(arr), len(per))
    except (KeyError, IndexError) as x:
        probs.append(f"not computable: {x}")
        n_s3 = (0, 0, 0)
    res["S3"] = (not probs, f"{n_s3[0]} steps, {n_s3[1]} Sync arrivals, {n_s3[2]} 1 ms samples at 0 ps; problems: {probs or 'none'}")
    # ---- F engine counters (fault outcome)
    got = {k: int(R.nw_sc.get(k, -1)) for k in COUNTERS}
    want = {k: (exp_fault or {}).get(k, 0) for k in COUNTERS}
    gotd = {k: int(R.ds_sc.get(k, -1)) for k in COUNTERS}
    okf = got == want and all(v == 0 for v in gotd.values()) and R.nw_sc.get("selfTestPassed") == 1 and R.ds_sc.get("selfTestPassed") == 1
    data["F"] = got
    res["F"] = (okf, f"NW-TT counters {({k: v for k, v in got.items() if v}) or 0} (expected {({k: v for k, v in want.items() if v}) or 0}); "
                f"DS-TT {({k: v for k, v in gotd.items() if v}) or 0}; self-tests {R.nw_sc.get('selfTestPassed')}/{R.ds_sc.get('selfTestPassed')}")
    return res, data


# ---------------------------------------------------------------------------------------
class RunUnit:
    def __init__(self, cfg):
        self.cfg = cfg
        pdir = os.path.join(RUNS, cfg, "pcap", f"{cfg}-0")
        ldir = os.path.join(RUNS, cfg, "m2log", f"{cfg}-0")
        self.fr = {t: frames(os.path.join(pdir, f"M2S4LinkTest.{t}.pcapRecorder[0].pcapng")) for t in ("ttA", "ttB")}
        self.log = {t: read_csv(os.path.join(ldir, f"M2S4LinkTest.{t}.eth[1].trafficConditionerLayer.engine.pdelay.csv")) for t in ("ttA", "ttB")}
        sca = os.path.join(RUNS, cfg, cfg, "0.sca")
        self.sc = {t: scalars(sca, f"{t}.eth[1].trafficConditionerLayer.engine") for t in ("ttA", "ttB")}
        self.vec = os.path.join(RUNS, cfg, cfg, "0.vec")


def eval_unit(cfg, ref_D, exp=None, exclude=None):
    """exp: {side: {counter: n}}; exclude: {side: set(seq)}."""
    U = RunUnit(cfg)
    res, data = {}, {"U": U}
    exp, exclude = exp or {}, exclude or {}
    probs_u, probs_t, probs_f, info = [], [], [], {}
    for X, Y, idx in (("ttA", "ttB", ID_A), ("ttB", "ttA", ID_B)):
        xo = [f for f in U.fr[X] if f["dir"] == 2]
        xi = [f for f in U.fr[X] if f["dir"] == 1]
        yo = [f for f in U.fr[Y] if f["dir"] == 2]
        yi = [f for f in U.fr[Y] if f["dir"] == 1]
        o_req = by_seq(xo, REQ, spi=(idx, 1))
        y_req = by_seq(yi, REQ, spi=(idx, 1))
        y_resp = by_seq(yo, RESP, reqport=(idx, 1))
        x_resp = by_seq(xi, RESP, reqport=(idx, 1))
        x_rfu = by_seq(xi, RFU, reqport=(idx, 1))
        meas = [r for r in U.log[X] if r["event"] in ("measure", "republish")]
        seqs = [int(r["seq"]) for r in meas if r["event"] == "measure"]
        if len(seqs) != len(set(seqs)) or any(r["event"] == "republish" for r in meas):
            probs_u.append(f"{X}: published more than once")
        expected = sorted(s for s in o_req if s in x_resp and s in x_rfu and s not in exclude.get(X, ()))
        if sorted(seqs) != expected:
            probs_u.append(f"{X}: published {len(seqs)} seqs, expected {len(expected)} (diff {sorted(set(seqs) ^ set(expected))[:6]})")
        prev, Ds, owd = None, [], set()
        for r in meas:
            s = int(r["seq"])
            t1, t2, t3, t4 = o_req[s][0]["start"], y_req[s][0]["start"], y_resp[s][0]["start"], x_resp[s][0]["start"]
            owd.add((t2 - t1, t4 - t3))
            D, e = link_delay(t1, t2, t3, t4, prev)
            prev = (t3, t4)
            Ds.append(int(r["D"]))
            if tuple(int(r[k]) for k in ("t1", "t2", "t3", "t4")) != (t1, t2, t3, t4):
                probs_u.append(f"{X} seq {s}: logged t1..t4 != PCAP")
            if int(r["D"]) != D or D != ref_D:
                probs_u.append(f"{X} seq {s}: D {r['D']} / PCAP {D} / reference {ref_D}")
        info[X] = (len(Ds), sorted(set(Ds)), sorted(owd))
        # termination accounting: every Pdelay frame received is in the engine log, except
        # frames the interface's FCS checker dropped (bad FCS in PCAP)
        pc = Counter((f["start"], f["end"]) for f in xi if f["pdelay"] and f["f"]["fcs_ok"])
        lg = Counter((int(r["tA"]), int(r["tB"])) for r in rx_rows(U.log[X]))
        if pc != lg:
            probs_t.append(f"{X}: {sum(pc.values())} received with valid FCS, {sum(lg.values())} terminated")
        got = {k: int(U.sc[X].get(k, -1)) for k in COUNTERS}
        want = {k: exp.get(X, {}).get(k, 0) for k in COUNTERS}
        if got != want:
            probs_f.append(f"{X}: {({k: v for k, v in got.items() if v}) or 0} expected {({k: v for k, v in want.items() if v}) or 0}")
        if U.sc[X].get("selfTestPassed") != 1:
            probs_f.append(f"{X}: self-test")
    data["info"] = info
    res["U"] = (not probs_u, f"{ {x: (n, d) for x, (n, d, o) in info.items()} } (exchanges, D ps); problems: {probs_u[:4] or 'none'}")
    res["TU"] = (not probs_t, f"problems: {probs_t or 'none'}")
    res["F"] = (not probs_f, f"problems: {probs_f or 'none'}")
    return res, data


# ---------------------------------------------------------------------------------------
def main():
    os.makedirs(OUT, exist_ok=True)
    # ---- G0
    okg, grows, totals = G.gate(RUNS1, RUNS)
    sens1, _ = G.compare_run(RUNS1, "M2S1", 0, RUNS, "M2S4-passive", 1)
    sens2, _ = G.compare_run(RUNS1, "M2S1", 0, RUNS, "M2S4", 0)
    add("G0", "hard gate: TtPdelayPort installed but passive (M2S4-passive, M2S1 seeds 0-9, frag, load, load-harq16) "
        "reproduces the M2S1 runs exactly: every .pcapng and per-frame log byte-identical, every vector line (event "
        "number, time, value) and scalar/statistic line identical, recorded parameters identical except the "
        "relocation of one ideal-channel object per translator, final event number identical; the comparison "
        "detects a different seed and the active configuration",
        okg and sens1 and sens2,
        f"{len(grows)} run pairs {'identical' if okg else [r for r in grows if not r[1]][:2]}; totals {totals}; "
        f"sensitivity: M2S1#0 vs passive#1 {len(sens1)} differences, vs M2S4#0 {len(sens2)} differences")
    # ---- A0 provenance of the M2-S1 inputs
    h = {}
    with open(HASHES1) as fh:
        for line in fh:
            d, n = line.rstrip("\n").split("  ", 1)
            h[os.path.normpath(os.path.join(RUNS1, n))] = d
    bad, n = [], 0
    for c1, _, reps in G.PAIRS:
        for r in reps:
            for sub in (f"pcap/{c1}-{r}", f"m2log/{c1}-{r}"):
                for name, path in G.files(os.path.join(RUNS1, c1, sub)).items():
                    n += 1
                    if h.get(os.path.normpath(path)) != G.sha(path):
                        bad.append(os.path.relpath(path, RUNS1))
    add("A0", "provenance: every M2-S1 PCAP and per-frame log used (G0, R2, L4) is hash-identical to M2-S1 "
        "raw-outputs.sha256 (56c8fb3)", not bad and n > 0, f"{n} files; mismatches: {bad[:3] or 'none'}")

    # ---- 5GS runs
    PRIMARY = [("M2S4", r) for r in range(10)] + [("M2S4-frag", 0), ("M2S4-load", 0), ("M2S4-load-harq16", 0)]
    FAULTS = {"M2S4-fault-dropResp": ({"lost": 1}, {2}),
              "M2S4-fault-dupResp": ({"multipleResp": 1, "lateAfterFault": 2}, {2}),
              "M2S4-fault-dupRespLate": ({"lateDuplicateResp": 1, "lateDuplicateFU": 1}, set()),
              "M2S4-fault-dupFU": ({"lateDuplicateFU": 1}, set()),
              "M2S4-fault-malformed": ({"malformed": 1, "orphanFollowUp": 1, "lost": 1}, {2})}
    ROWS5 = ("T1", "T2", "T3", "T4", "L1", "L2", "S1", "S2", "S3", "F")
    agg = defaultdict(list)
    keep = {}
    for cfg, rep in PRIMARY:
        res, data = eval_5gs(cfg, rep)
        keep[(cfg, rep)] = data
        for k in ROWS5:
            agg[k].append((f"{cfg}#{rep}", res[k]))
    for cfg, (expf, excl) in FAULTS.items():
        res, data = eval_5gs(cfg, 0, expf, excl)
        for k in ROWS5:
            agg[f"{k}-faults"].append((cfg, res[k]))
    desc = {
        "T1": "no Pdelay frame crosses the 5GS: 0 Pdelay_Req/Resp/Resp_Follow_Up at NW-TT eth[0], DS-TT eth[0], UE eth[0], UPF dnEth and N3 (GTP-U inner frames after IPv4 reassembly), both directions",
        "T2": "every Pdelay frame received at a TT eth[1] is terminated there: one engine row per PCAP frame with its PCAP first/last-bit times; nothing passed",
        "T3": "engine frame format (PCAP): L 72 B, valid FCS, untagged, one source MAC per port, versionPTP 2, messageLength 54, domain 0, sourcePortIdentity = configured; NW-TT Req sequenceIds consecutive; DS-TT answers each slave Req with Resp and Resp_FU echoing its sequenceId and requestingPortIdentity",
        "T4": "first-bit timestamps: every engine-sent frame's logged (start, end) = PCAP (end - (L+8)*8 ns, end)",
        "L1": "NW-TT measures its upstream link: logged t1, t4 = NW-TT eth[1] PCAP first bits, t2, t3 = GM PCAP first bits; wire t2/t3 = floor_ns; D = (nRR(t4-t1) - (t3-t2))/2 from PCAP = logged = 50 000 ps; nRR = 1/1; each sequenceId published once; published set = completed exchanges",
        "L2": "the slave measures only its link to DS-TT: engine t2/t3 = DS-TT PCAP first bits, wire = floor_ns; slave raw D from PCAP = 50 000 ps; slave pdelay = 50 000 ps every sample, nRR 1; the M2-S3 slave model reproduces the slave exactly",
        "S1": "Sync/Follow_Up untouched: in-order byte-identical subsequence GM -> slave; correctionField 0 (no residence correction)",
        "S2": "slave clock = INET slave fed the terminated pdelay: replay exact; error after step 1 = -(Lup + Res1) exactly (link delay correct, clock NOT synchronized)",
        "S3": "offline composition readiness (no correction applied): cf' = D_NWTT (measured) + Res with the slave's OWN pdelay gives 0 ps after every step, at every Sync arrival and every 1 ms sample",
        "F": "engine counters: all fault counters 0 on both ports; self-tests passed",
    }
    for k in ROWS5:
        lst = agg[k]
        bad_ = [(n_, d) for n_, (ok, d) in lst if not ok]
        add(k, desc[k] + " [M2S4 seeds 0-9, frag, load, load-harq16]", not bad_,
            ("; ".join(f"{n_}: {d}" for n_, d in bad_) or f"all {len(lst)} runs; e.g. {lst[0][0]}: {lst[0][1][1]}")[:1200])
    lf = [(n_, d) for n_, (ok, d) in agg["L1"] + agg["L2"] if "frag" in n_ or "load" in n_]
    add("L3", "robust to radio load and N3 fragmentation: L1 and L2 hold on M2S4-frag, M2S4-load, M2S4-load-harq16",
        all(ok for n_, (ok, d) in agg["L1"] + agg["L2"] if "frag" in n_ or "load" in n_),
        "; ".join(f"{n_}: {d[:110]}" for n_, d in lf))
    fault_desc = {"M2S4-fault-dropResp": "F1 (5GS) GM's Resp seq 2 dropped before transmission -> lost 1, seq 2 not published",
                  "M2S4-fault-dupResp": "F3 (5GS) Resp seq 2 duplicated before its Follow_Up -> multipleResp 1, seq 2 discarded; the INET GM sends a Resp_Follow_Up after each transmitted Resp, hence lateAfterFault 2",
                  "M2S4-fault-dupRespLate": "F3L (5GS) late duplicate Resp seq 2 -> lateDuplicateResp 1 (+ lateDuplicateFU 1: the GM's Follow_Up for the copy); published once, unchanged",
                  "M2S4-fault-dupFU": "F4 (5GS) duplicate Resp_FU seq 3 after completion -> lateDuplicateFU 1; value unchanged",
                  "M2S4-fault-malformed": "F9 (5GS) Resp seq 2 with versionPTP 1 -> malformed 1, orphanFollowUp 1, lost 1; frame not forwarded"}
    for cfg in FAULTS:
        okall = all(ok for k in ROWS5 for n_, (ok, d) in agg[f"{k}-faults"] if n_ == cfg)
        det = {k: d for k in ROWS5 for n_, (ok, d) in agg[f"{k}-faults"] if n_ == cfg and (k in ("F", "L1") or not ok)}
        add(f"F-5GS-{cfg[11:]}", fault_desc[cfg] + "; all other rows pass", okall, "; ".join(f"{k}: {v}" for k, v in det.items())[:800])

    # ---- unit topology
    UNIT = {"M2S4U": ("U1", L_REF, "unit topology, engine to engine, 50 ns: D = 50 000 ps at both requesters, = PCAP, nRR 1"),
            "M2S4U-73": ("U2", 73217, "non-integer-ns link 73.217 ns: D = 73 217 ps at both ends, = PCAP"),
            "M2S4U-asym": ("U3", 60000, "asymmetric link A->B 50 ns / B->A 70 ns: D = 60 000 ps at both ends, = PCAP"),
            "M2S4U-wrap": ("U4", L_REF, "sequenceId wrap: exchanges 65534, 65535, 0, 1 all valid")}
    for cfg, (name, ref, txt) in UNIT.items():
        res, data = eval_unit(cfg, ref)
        okall = all(ok for ok, d in res.values())
        extra = ""
        if cfg == "M2S4U-wrap":
            seqs = [int(r["seq"]) for r in data["U"].log["ttA"] if r["event"] == "measure"]
            okall &= seqs[:4] == [65534, 65535, 0, 1]
            extra = f"; ttA published seqs start {seqs[:4]}"
        ow = {x: o for x, (n_, d, o) in data["info"].items()}
        if cfg == "M2S4U-asym":
            okall &= ow["ttA"] == [(50000, 70000)] and ow["ttB"] == [(70000, 50000)]
            extra = ("; one-way delays from PCAP A->B 50 000 ps, B->A 70 000 ps; the peer-delay estimate 60 000 ps is wrong by "
                     "exactly +10 000 ps (A->B) and -10 000 ps (B->A): a LIMITATION of symmetric peer-delay estimation, "
                     "not a validation of one-way delay")
        else:
            extra += f"; one-way (t2-t1, t4-t3) {ow}"
        add(name, txt + "; termination accounting and counters as expected", okall,
            "; ".join(f"{k}: {d}" for k, (ok, d) in res.items())[:700] + extra)
    UF = {"M2S4U-F1": ({"ttA": {"lost": 1}}, {"ttA": {3}}, "F1 Resp 3 dropped (no Follow_Up follows an untransmitted Resp) -> lost 1"),
          "M2S4U-F2": ({"ttA": {"lost": 1}}, {"ttA": {4}}, "F2 Resp_FU 4 dropped -> lost 1"),
          "M2S4U-F3": ({"ttA": {"multipleResp": 1, "lateAfterFault": 1}}, {"ttA": {5}}, "F3 Resp 5 duplicated before its Follow_Up -> multipleResp 1, discarded, lateAfterFault 1"),
          "M2S4U-F3L": ({"ttA": {"lateDuplicateResp": 1}}, None, "F3L late duplicate Resp 6 (after its Follow_Up) -> lateDuplicateResp 1; published once, unchanged"),
          "M2S4U-F4": ({"ttA": {"lateDuplicateFU": 1}}, None, "F4 duplicate Resp_FU 7 after completion -> lateDuplicateFU 1; published once, unchanged"),
          "M2S4U-F5": ({"ttA": {"orphanFollowUp": 1}}, None, "F5 a Resp_FU 8 ahead of Resp 8 (reordering medium) -> orphanFollowUp 1; the exchange then completes"),
          "M2S4U-F6": ({"ttA": {"lost": 1, "staleSeq": 2}}, {"ttA": {9}}, "F6 Resp and Resp_FU 9 delayed beyond the next request -> staleSeq 2, lost 1"),
          # F7-F9: the injector replaces the Resp by a new packet below ttB's engine, so ttB (which sends a
          # Resp_Follow_Up only after its own Resp, by tree id) sends none: no orphan Follow_Up at ttA
          "M2S4U-F7": ({"ttA": {"staleSeq": 1, "lost": 1}}, {"ttA": {10}}, "F7 Resp 10 with sequenceId 999 -> staleSeq 1, lost 1"),
          "M2S4U-F8": ({"ttA": {"notForUs": 1, "lost": 1}}, {"ttA": {11}}, "F8 Resp 11 for another requester port -> notForUs 1, lost 1"),
          "M2S4U-F9a": ({"ttA": {"malformed": 1, "lost": 1}}, {"ttA": {12}}, "F9a Resp 12 versionPTP 1 -> malformed 1, lost 1"),
          "M2S4U-F9b": ({"ttA": {"malformed": 1, "lost": 1}}, {"ttA": {13}}, "F9b Resp 13 messageLength 50 -> malformed 1, lost 1"),
          "M2S4U-F9c": ({"ttA": {"malformed": 1, "lost": 1}}, {"ttA": {14}}, "F9c Resp 14 domainNumber 1 -> malformed 1, lost 1"),
          "M2S4U-F9d": ({"ttA": {"malformed": 1, "lost": 1}}, {"ttA": {15}}, "F9d Resp 15 truncated to 40 B -> malformed 1, lost 1"),
          "M2S4U-F10": ({"ttA": {"orphanFollowUp": 1, "lost": 1}}, {"ttA": {16}}, "F10 Resp 16 with an inverted FCS -> dropped by INET's FCS checker (never reaches the engine), orphanFollowUp 1, lost 1"),
          "M2S4U-F11": ({"ttA": {"lost": 5}}, {"ttA": {17, 18, 19, 20, 21}}, "F11 Resp 17-21 dropped -> lost 5; measuring flag 1 -> 0 -> 1"),
          "M2S4U-F12": ({"ttB": {"lateDuplicateResp": 1, "lateDuplicateFU": 1}}, None,
                        "F12 ttB's Req 22 duplicated: ttA answers both; ttA's first Resp_FU leaves before the second Resp, so ttB counts late duplicates (published once)")}
    for cfg, (e, x, txt) in UF.items():
        res, data = eval_unit(cfg, L_REF, e, x)
        okall = all(ok for ok, d in res.values())
        extra = ""
        U = data["U"]
        if cfg == "M2S4U-F10":
            bad_fcs = sum(1 for f in U.fr["ttA"] if f["dir"] == 1 and f["pdelay"] and not f["f"]["fcs_ok"])
            okall &= bad_fcs == 1
            extra = f"; inbound Pdelay frames with bad FCS at ttA (PCAP, independent CRC-32): {bad_fcs}"
        if cfg == "M2S4U-F11":
            mv, vid = [], None
            with open(U.vec) as fh:
                for line in fh:
                    if line.startswith("vector ") and "ttA.eth[1].trafficConditionerLayer.engine measuring" in line:
                        vid = line.split()[1]
                    elif vid is not None and line.startswith(vid + "\t"):
                        mv.append(int(float(line.split("\t")[3])))
            okall &= mv == [1, 0, 1]
            extra = f"; measuring flag sequence at ttA {mv} (false after the 4th consecutive loss > allowedLostResponses 3)"
        if cfg == "M2S4U-F12":
            okall &= int(U.sc["ttA"].get("reqAnswered", -1)) == int(U.sc["ttB"].get("reqSent", -2)) + 1
            extra = f"; ttA answered {int(U.sc['ttA'].get('reqAnswered', -1))} requests for ttB's {int(U.sc['ttB'].get('reqSent', -1))}"
        add(f"F-unit-{cfg[6:]}", txt + "; every other exchange exact", okall,
            "; ".join(f"{k}: {d}" for k, (ok, d) in res.items())[:600] + extra)

    # ---- R1: M2-S1 per-frame rows on the M2S4 runs (subset of C1-C5)
    probs, nfr, neng = [], 0, 0
    for cfg, rep in PRIMARY:
        R = keep[(cfg, rep)]["R"]
        for tin, tout, fin, fout in (("nwTt", "dsTt", R.nw_in, R.ds_out), ("dsTt", "nwTt", R.ds_in, R.nw_out)):
            ing = read_csv(os.path.join(R.ldir, f"M1Bridge.{tin}.eth[1].measurementLayer.ingress.port.csv"))
            eg = read_csv(os.path.join(R.ldir, f"M1Bridge.{tout}.eth[1].measurementLayer.egress.port.csv"))
            rx = [r for r in ing if r["event"] == "rx"]
            tx = [r for r in eg if r["event"] == "tx"]
            if [ps(r["tRxEnd"]) for r in rx] != [f["end"] for f in fin] or [r["hash"] for r in rx] != [f["key"][3] for f in fin]:
                probs.append(f"{cfg}#{rep} {tin} rx rows != PCAP")
            if [ps(r["tTxEnd"]) for r in tx] != [f["end"] for f in fout] or [r["txHash"] for r in tx] != [f["key"][3] for f in fout]:
                probs.append(f"{cfg}#{rep} {tout} tx rows != PCAP")
            pin = defaultdict(set)
            for f in fin:
                pin[f["key"]].add(f["end"])
            for r, f in zip(tx, fout):
                nfr += 1
                if r["tagged"] == "1":
                    k = (int(r["etherType"]), int(r["pcp"]), int(r["vid"]), r["hash"])
                    if ps(r["ingressTime"]) not in pin[k] or ps(r["residence"]) != f["end"] - ps(r["ingressTime"]):
                        probs.append(f"{cfg}#{rep} {tout} residence")
                else:
                    neng += 1
                    if not f["pdelay"]:
                        probs.append(f"{cfg}#{rep} {tout}: untagged non-Pdelay frame")
    add("R1", "M2-S1 per-frame rows on the M2S4 runs (subset of C1-C5): every frame received on a TT eth[1] has its "
        "ingress row (= PCAP time and hash), every frame sent has its egress row (= PCAP times and hashes); every tagged "
        "frame's ingress time = PCAP at TT_in and R = PCAP out - PCAP in; untagged egress rows are exactly the engine's "
        "Pdelay frames", not probs, f"{nfr} egress frames, {neng} engine frames; problems: {probs[:4] or 'none'}")

    # ---- R2: application traffic and QoS mapping vs M2S1
    probs, dl, ul, nflow, tail = [], [], [], 0, Counter()
    pairs = list(zip(PRIMARY, [("M2S1", r) for r in range(10)] + [("M2S1-frag", 0), ("M2S1-load", 0), ("M2S1-load-harq16", 0)]))
    for (cfg, rep), (c1, r1) in pairs:
        R = keep[(cfg, rep)]["R"]
        p1 = os.path.join(RUNS1, c1, "pcap", f"{c1}-{r1}")
        sl1 = frames(os.path.join(p1, "M1Bridge.talker.pcapRecorder[0].pcapng"))
        gm1 = frames(os.path.join(p1, "M1Bridge.listener.pcapRecorder[0].pcapng"))
        n31 = n3_inner(os.path.join(p1, "M1Bridge.upf.pcapRecorder[0].pcapng"))
        # per flow: the frames delivered in both runs arrive in the same order; a frame delivered in
        # only one run must have been still in flight at the end of the other (sent within that run's
        # largest latency of the flow before the end, 5 s)
        END = 5 * 10 ** 12
        for name, src4, dst4, src1, dst1 in (("talker in (DL)", R.gm, R.sl, gm1, sl1), ("listener in (UL)", R.sl, R.gm, sl1, gm1)):
            def flows(src, dst):
                tx = {}
                for f in src:
                    if f["dir"] == 2 and f["f"]["etherType"] != 0x88F7:
                        tx.setdefault(f["key"], f["end"])
                seq, lat = defaultdict(list), defaultdict(int)
                for f in dst:
                    if f["dir"] == 1 and f["f"]["etherType"] != 0x88F7:
                        fl = (f["f"]["pcp"], f["f"]["vid"])
                        seq[fl].append(f["key"])
                        if f["key"] in tx:
                            lat[fl] = max(lat[fl], f["end"] - tx[f["key"]])
                return tx, seq, lat
            tx4, s4, lat4 = flows(src4, dst4)
            tx1, s1, lat1 = flows(src1, dst1)
            for fl in set(s4) | set(s1):
                nflow += 1
                a4, a1 = s4.get(fl, []), s1.get(fl, [])
                c4 = [k for k in a4 if k in set(a1)]
                c1 = [k for k in a1 if k in set(a4)]
                only4 = [k for k in a4 if k not in set(a1)]
                only1 = [k for k in a1 if k not in set(a4)]
                inflight = all(tx1.get(k, 0) >= END - lat1[fl] for k in only4) and all(tx4.get(k, 0) >= END - lat4[fl] for k in only1)
                if c4 != c1 or not inflight:
                    probs.append(f"{cfg}#{rep} {name} flow {fl}: order equal {c4 == c1}, only-M2S4 {len(only4)}, "
                                 f"only-M2S1 {len(only1)}, all in flight at the end {inflight}")
                tail[name] += len(only4) + len(only1)
        for dirn, src4, dst4, src1, dst1 in (("DL", R.gm, R.sl, gm1, sl1), ("UL", R.sl, R.gm, sl1, gm1)):
            def lat(src, dst):
                tx = {f["key"][3]: f["end"] for f in src if f["dir"] == 2 and f["f"]["etherType"] != 0x88F7}
                return {f["key"][3]: f["end"] - tx[f["key"][3]] for f in dst
                        if f["dir"] == 1 and f["f"]["etherType"] != 0x88F7 and f["key"][3] in tx}
            l4, l1 = lat(src4, dst4), lat(src1, dst1)
            (dl if dirn == "DL" else ul).extend(l4[k] - l1[k] for k in l4 if k in l1)
        q4, q1 = defaultdict(set), defaultdict(set)
        for dst, n3 in ((q4, R.n3), (q1, n31)):
            for direction, qfi, inner in n3:
                isg, mt, pcp = inner_type(inner)
                dst[("gPTP" if isg else pcp, direction)].add(qfi)
        diff = [k for k in set(q4) | set(q1) if k[0] != "gPTP" and q4.get(k) != q1.get(k)]
        diff += [k for k in q4 if k[0] == "gPTP" and q4[k] - q1.get(k, set())]
        if diff:
            probs.append(f"{cfg}#{rep}: QFI mapping differs at {diff}: {dict(q4)} vs {dict(q1)}")
    ch_dl = sum(1 for x in dl if x)
    ch_ul = sum(1 for x in ul if x)
    add("R2", "application traffic and QoS mappings unchanged vs M2S1 (same seed/variant): the application frames "
        "(payload hashes) delivered in both runs arrive in the same order per flow at both stations, and any frame "
        "delivered in only one run was still in flight at the end of the other; same PCP -> QFI mapping on N3 per direction (gPTP "
        "keeps its QFI). End-to-end latencies are reported, not required equal (removing Pdelay from the 5GS can "
        "change RLC/MAC timing)", not probs,
        f"{nflow} flow sequences compared; frames delivered in only one run (in flight at the end of the other): {dict(tail)}; latency change per application frame (M2S4 - M2S1): DL {len(dl)} frames, "
        f"{ch_dl} changed{f' ({fmt(min(dl))} .. {fmt(max(dl))})' if ch_dl else ''}; UL {len(ul)} frames, {ch_ul} changed"
        f"{f' ({fmt(min(ul))} .. {fmt(max(ul))})' if ch_ul else ''}; problems: {probs[:3] or 'none'}")

    # ---- L4: baseline comparison (report)
    lines = []
    for (cfg, rep), (c1, r1) in [(("M2S4", r), ("M2S1", r)) for r in range(10)] + [(("M2S4-load", 0), ("M2S1-load", 0)), (("M2S4-load-harq16", 0), ("M2S1-load-harq16", 0))]:
        p1 = os.path.join(RUNS1, c1, "pcap", f"{c1}-{r1}")
        sl1 = frames(os.path.join(p1, "M1Bridge.talker.pcapRecorder[0].pcapng"))
        gm1 = frames(os.path.join(p1, "M1Bridge.listener.pcapRecorder[0].pcapng"))
        sreq, sresp = by_seq([f for f in sl1 if f["dir"] == 2], REQ), by_seq([f for f in sl1 if f["dir"] == 1], RESP)
        greq, gresp = by_seq([f for f in gm1 if f["dir"] == 1], REQ), by_seq([f for f in gm1 if f["dir"] == 2], RESP)
        old, prev = [], None
        for s in sorted(sresp):
            if s in greq and s in gresp:
                D, e = link_delay(sreq[s][0]["start"], greq[s][0]["start"], gresp[s][0]["start"], sresp[s][0]["start"], prev)
                prev = (gresp[s][0]["start"], sresp[s][0]["start"])
                old.append(D)
        new = keep[(cfg, rep)]["L2"]["raw"]
        lines.append((c1, r1, min(old), max(old), sorted(set(new)), keep[(cfg, rep)]["L2"]["pd_rec"][:1]))
    idle = [x for x in lines if x[0] == "M2S1"]
    add("L4", "comparison with the forwarded end-to-end Pdelay (report): slave raw link delay per exchange", True,
        f"M2S1 seeds 0-9 end-to-end {fmt(min(x[2] for x in idle))} .. {fmt(max(x[3] for x in idle))} -> M2S4 link-local "
        f"{sorted(set(v for x in idle for v in x[4]))} ps; " +
        "; ".join(f"{c}#{r} {fmt(a)} .. {fmt(b)} -> {n} ps" for c, r, a, b, n, p in lines if c != "M2S1"))

    # ---- W1 wire-mode report (sim vs serialized timestamps)
    wl = []
    for cfg, rep in [("M2S4", 0), ("M2S4-load", 0)]:
        d = keep[(cfg, rep)]["L1"]
        prev, devs, res_ = None, [], 0
        for s, D in d["pub"]:
            t1, t4 = d["o_req"][s][0]["start"], d["i_resp"][s][0]["start"]
            t2w, t3w = wire(d["i_resp"][s][0]["g"]["ts"]), wire(d["i_rfu"][s][0]["g"]["ts"])
            t2, t3 = d["g_req"][s][0]["start"], d["g_resp"][s][0]["start"]
            res_ += (t2 != t2w) + (t3 != t3w)
            Dw, _ = link_delay(t1, t2w, t3w, t4, prev)
            prev = (t3w, t4)
            devs.append(Dw - D)
        wl.append(f"{cfg}#{rep} NW-TT: sub-ns residues on t2/t3 {res_}, wire-mode D - D {sorted(set(devs))} ps")
    add("W1", "wire-mode report (report only): D the requester would compute from the serialized (ns-truncated) t2/t3",
        True, "; ".join(wl))

    # ---- negative controls (each must fail exactly its declared rows, with the exact signature)
    def run_rows(cfg, expf=None, excl=()):
        res, data = eval_5gs(cfg, 0, expf, excl)
        return {k for k in ROWS5 if not res[k][0]}, res, data

    def T(d, s):
        return (d["o_req"][s][0]["start"], d["g_req"][s][0]["start"], d["g_resp"][s][0]["start"], d["i_resp"][s][0]["start"])

    def nwtt_D_check(data, fn):
        out = [(s, D, fn(s, data["L1"])) for s, D in data["L1"]["pub"]]
        return len(out) > 0 and all(D == e for s, D, e in out), out

    nc = []
    # N1: forwarded (passive engine) -- also the old architecture
    failed, res, data = run_rows("M2S4-passive")
    R = data["R"]
    sreq, sresp = by_seq(R.sl_out, REQ), by_seq(R.sl_in, RESP)
    greq, gresp = by_seq(R.gm_in, REQ), by_seq(R.gm_out, RESP)
    raw1 = link_delay(sreq[0][0]["start"], greq[0][0]["start"], gresp[0][0]["start"], sresp[0][0]["start"])[0]
    pd = data["L2"]["pd_rec"]
    n_sl_pd = sum(1 for f in R.sl if f["pdelay"])
    sig = bool(data["T1"]) and bool(pd) and pd[0] == O.dbl(raw1) and not data["L1"]["pub"]
    nc.append(("N1", "Pdelay forwarded across the 5GS (M2S4-passive = the old architecture)", {"T1", "T2", "T3", "T4", "L1", "L2", "S2", "S3", "F"},
               failed, sig, f"Pdelay frames in the 5GS {data['T1']} (slave sent/received {n_sl_pd}); no NW-TT exchange; slave pdelay "
               f"first sample {pd[0] if pd else '-'} s = raw end-to-end exchange 0 from PCAP {fmt(raw1)}"))
    # N2a: pairing with the previous request
    failed, res, data = run_rows("M2S4-nc-pairing")
    ok_, out = nwtt_D_check(data, lambda s, d: link_delay(d["o_req"][s - 1][0]["start"], d["g_req"][s][0]["start"],
                                                          d["g_resp"][s][0]["start"], d["i_resp"][s][0]["start"])[0])
    sig = ok_ and 0 not in [s for s, D in data["L1"]["pub"]]
    nc.append(("N2a", "wrong requester pairing: t1 of the previous request", {"L1", "S3"}, failed, sig,
               f"D_k = ((t4_k - t1_k-1) - (t3_k - t2_k))/2 from PCAP for k >= 1: {sorted(set(D for s, D, e in out))} ps; no D_0"))
    # N3a: t4 at receptionEnded
    failed, res, data = run_rows("M2S4-nc-t4end")
    ok_, out = nwtt_D_check(data, lambda s, d: link_delay(T(d, s)[0], T(d, s)[1], T(d, s)[2], d["i_resp"][s][0]["end"])[0])
    nc.append(("N3a", "wrong PHY event at the requester: t4 at receptionEnded", {"L1", "S3"}, failed,
               ok_ and all(D == L_REF + X72 // 2 for s, D, e in out), f"D = 50 ns + 640/2 ns = {sorted(set(D for s, D, e in out))} ps"))
    # N3b: t3 at transmissionEnded at the DS-TT responder
    failed, res, data = run_rows("M2S4-nc-t3end")
    pd, rfu, resp = data["L2"]["pd_rec"], data["L2"]["d_rfu"], data["L2"]["d_resp"]
    sig = bool(pd) and all(v == O.dbl(L_REF - X72 // 2) for v in pd) and all(
        wire(rfu[s][0]["g"]["ts"]) == floor_ns(resp[s][0]["end"]) for s in rfu)
    nc.append(("N3b", "wrong PHY event at the responder: t3 at transmissionEnded", {"L2", "S2", "S3"}, failed, sig,
               f"slave pdelay every sample {sorted(set(pd))} s = (100 - 640)/2 ns (INET release build accepts it); DS-TT "
               f"Resp_FU t3 = floor_ns(Resp last bit)"))
    # N3c: both t1 and t4 at the last bit (discriminability control)
    failed, res, data = run_rows("M2S4-nc-t1t4end")
    d = data["L1"]
    sig = bool(d["pub"]) and all(D == L_REF for s, D in d["pub"]) and all(
        (int(r["t1"]), int(r["t4"])) == (d["o_req"][int(r["seq"])][0]["end"], d["i_resp"][int(r["seq"])][0]["end"])
        for r in d["measures"])
    nc.append(("N3c", "t1 and t4 both at the last bit (discriminability control: Req and Resp both 72 B)", {"L1"}, failed, sig,
               "D unchanged = 50 000 ps (the value cannot reveal it: X cancels); detected only because the logged t1/t4 "
               "equal the PCAP LAST bits"))
    # N5: units
    failed, res, data = run_rows("M2S4-nc-units")
    ok_, out = nwtt_D_check(data, lambda s, d: link_delay(T(d, s)[0], T(d, s)[1] // NS, T(d, s)[2] // NS, T(d, s)[3])[0])
    nc.append(("N5", "wrong timestamp units: wire ns numbers of t2/t3 used as ps", {"L1", "S3"}, failed, ok_,
               f"D = ((t4 - t1) - (floor(t3/ns) - floor(t2/ns)))/2 from PCAP: {sorted(set(D for s, D, e in out))} ps"))
    # N6a/b: formula
    failed, res, data = run_rows("M2S4-nc-nohalf")
    ok_, out = nwtt_D_check(data, lambda s, d: (T(d, s)[3] - T(d, s)[0]) - (T(d, s)[2] - T(d, s)[1]))
    nc.append(("N6a", "wrong formula: no division by 2", {"L1", "S3"}, failed, ok_ and all(D == 2 * L_REF for s, D, e in out),
               f"D = {sorted(set(D for s, D, e in out))} ps"))
    failed, res, data = run_rows("M2S4-nc-noturn")
    ok_, out = nwtt_D_check(data, lambda s, d: M.trunc_div2(T(d, s)[3] - T(d, s)[0]))
    nc.append(("N6b", "wrong formula: turnaround not subtracted", {"L1", "S3"}, failed, ok_,
               f"D = (t4 - t1)/2 from PCAP: {sorted(set(D for s, D, e in out))} ps"))
    # N4a: missing response not counted
    failed, res, data = run_rows("M2S4-nc-noTimeout", {"lost": 1}, {2})
    nc.append(("N4a", "missing response not detected (Resp 2 dropped, loss not counted)", {"F"}, failed,
               data["F"]["lost"] == 0, f"lost = {data['F']['lost']} (expected 1); D values exact"))
    # N4b: duplicate accepted (last one wins)
    failed, res, data = run_rows("M2S4-nc-acceptLast", {"multipleResp": 1, "lateAfterFault": 2}, {2})
    d = data["L1"]
    prev, sig_ok, vals = None, True, []
    for s, D in d["pub"]:
        i = 1 if s == 2 else 0
        t1, t2, t3, t4 = d["o_req"][s][0]["start"], d["g_req"][s][0]["start"], d["g_resp"][s][0]["start"], d["i_resp"][s][i]["start"]
        e_, _ = link_delay(t1, t2, t3, t4, prev)
        prev = (t3, t4)
        sig_ok &= e_ == D
        vals.append((s, D))
    t4dup = d["i_resp"][2][1]["start"] - d["i_resp"][2][0]["start"] if len(d["i_resp"].get(2, [])) == 2 else None
    nc.append(("N4b", "duplicate response accepted (last one wins)", {"F", "L1", "S3"}, failed, sig_ok and t4dup == X72 + IFG,
               f"seq 2 uses the duplicate's first bit (+{fmt(t4dup) if t4dup else '-'}); D from PCAP incl. the rate ratio it "
               f"induces in the next exchange: {vals}"))
    # N4c: late duplicate re-published
    failed, res, data = run_rows("M2S4-nc-republishLate", {"lateDuplicateResp": 1, "lateDuplicateFU": 1}, set())
    d = data["L1"]
    rep_rows = [r for r in d["measures"] if r["event"] == "republish"]
    sig = False
    if len(rep_rows) == 1 and rep_rows[0]["seq"] == "2" and len(d["i_resp"].get(2, [])) == 2:
        t1, t2, t3 = d["o_req"][2][0]["start"], d["g_req"][2][0]["start"], d["g_resp"][2][0]["start"]
        t4late = d["i_resp"][2][1]["start"]
        sig = int(rep_rows[0]["D"]) == M.trunc_div2((t4late - t1) - (t3 - t2))
    nc.append(("N4c", "late duplicate modifies a published measurement", {"F", "L1"}, failed, sig,
               f"seq 2 published twice; second value {rep_rows[0]['D'] if rep_rows else '-'} ps = ((t4'' - t1) - (t3 - t2))/2 "
               f"from PCAP (t4'' = the late copy's first bit)"))
    # N2b (unit): responder answers with the previous request's sequenceId
    res, data = eval_unit("M2S4U-nc-previousSeq", L_REF)
    U = data["U"]
    failed = {k for k, (ok, dd) in res.items() if not ok}
    nb = int(U.sc["ttB"].get("reqSent", 0))
    sig = int(U.sc["ttB"].get("published", -1)) == 0 and int(U.sc["ttB"].get("staleSeq", -1)) == 2 * (nb - 1) \
        and int(U.sc["ttB"].get("lost", -1)) == nb - 1 and int(U.sc["ttA"].get("published", 0)) > 0
    nc.append(("N2b", "wrong responder pairing (unit): ttA answers each request with the previous request's sequenceId",
               {"U", "F"}, failed, sig,
               f"ttB: {nb} requests, published 0, staleSeq {int(U.sc['ttB'].get('staleSeq', -1))}, lost "
               f"{int(U.sc['ttB'].get('lost', -1))}; ttA's own measurements unaffected"))
    for name, txt, expect, failed, sig, detail in nc:
        ok = failed == expect and sig
        add(name, f"{txt}: fails exactly {sorted(expect) or 'nothing'} with the exact signature", ok,
            f"failed {sorted(failed) or 'nothing'}; signature {'OK' if sig else 'WRONG'}: {detail}"[:900])

    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {check} {detail}")
        if extra:
            print(f"      {extra}")
    print(f"\nOVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
