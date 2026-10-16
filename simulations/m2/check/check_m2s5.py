#!/usr/bin/env python3
"""M2-S5 checker: online downlink two-step gPTP correction (migration/m2-s5-design.md rev. 2.1).

Usage: check_m2s5.py <results/M2-S5> <results/M2-S4/runs> <results/M2-S4/raw-outputs.sha256>

Independent of the corrector code. Every expected value comes from PCAP (pcapng, 1 ps; first
bit = end - (L + 8) * 8 bit times at the port rate) and decoded frame bytes:
  Lup_pcap  link delay of the latest NW-TT Pdelay exchange whose Resp_Follow_Up ended before
            the Follow_Up's reception ended at the NW-TT, with INET's arithmetic (M2-S4);
  Res_pcap  DS-TT eth[1] Sync first bit - NW-TT eth[1] Sync first bit;
the INET slave is replayed with the M2-S3 model (inet_model.py, unchanged), the corrector logs
are compared with these values, never used as truth. Integer ps, exact, no tolerance.
M2-S4 is the timing baseline (G1, S3, P1).
"""
import csv
import hashlib
import os
import shlex
import struct
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
OUT, RUNS4, HASHES4 = sys.argv[1:4]
RUNS = os.path.join(OUT, "runs")
_argv = sys.argv
sys.argv = [_argv[0], OUT, RUNS4, HASHES4]
import check_m2s4 as C4  # noqa: E402  (pure helpers: n3_inner, inner_type, link_delay, read_csv, scalars)
sys.argv = _argv
import pcapng  # noqa: E402
import inet_model as M  # noqa: E402
import oracle_m2s3 as O  # noqa: E402
import gate_m2s5 as G  # noqa: E402
import gate_v0 as V0  # noqa: E402

M.STRICT_INET_ASSERTS = False      # release INET (NDEBUG), as in M2-S4
NS = 1000
SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10
PDELAY = (REQ, RESP, RFU)
L_REF = 50 * NS
GPTP_DST = "0180c200000e"
rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def fmt(p):
    return f"{p / NS:.3f} ns"


# ---------------------------------------------------------------------------------------
# PCAP access
def frames(path, bit_ps=NS):
    out = []
    for i, p in enumerate(pcapng.read(path)):
        d, L = p["data"], len(p["data"])
        f = pcapng.ethernet(d)
        r = {"i": i, "end": p["t_ps"], "start": p["t_ps"] - (L + 8) * 8 * bit_ps, "L": L, "dir": p["dir"], "f": f, "raw": d,
             "g": None, "type": -1, "seq": -1, "dom": -1}
        if f["dst"] == GPTP_DST and f["etherType"] == 0x88F7 and f["payload"]:
            b = f["payload"]
            r["type"] = b[0] & 15
            if len(b) >= 32:
                r["seq"] = int.from_bytes(b[30:32], "big")
                r["dom"] = b[4]
            try:
                r["g"] = O.decode(b)
            except ValueError:
                r["g"] = None
        out.append(r)
    return out


def sel(fr, direction, *types, dom=0):
    return [f for f in fr if f["dir"] == direction and (not types or (f["type"] in types and (dom is None or f["dom"] == dom)))]


def by_seq(fr):
    d = defaultdict(list)
    for f in fr:
        d[f["seq"]].append(f)
    return d


def read_csv(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return list(csv.DictReader(fh))


def scalars_all(path):
    out = {}
    with open(path) as fh:
        for line in fh:
            if line.startswith("scalar "):
                p = shlex.split(line)
                try:
                    out[(p[1], p[2])] = float(p[3])
                except ValueError:
                    out[(p[1], p[2])] = float("nan")
    return out


def read_vec(path, station):
    want = {(f"{station}.gptp", "pdelay:vector"): "pdelay", (f"{station}.gptp", "gmRateRatio:vector"): "gm",
            (f"{station}.gptp", "neighborRateRatio:vector"): "nrr", (f"{station}.clock", "timeChanged:vector"): "clock",
            (f"{station}.clock", "oscillatorCompensationChanged:vector"): "comp"}
    ids, data = {}, {v: [] for v in want.values()}
    with open(path) as fh:
        for line in fh:
            if line[:1].isdigit():
                tab = line.find("\t")
                vid = line[:tab]
                if vid in ids:
                    p = line.rstrip("\n").split("\t")
                    data[ids[vid]].append((p[2], p[3]))
            elif line.startswith("vector "):
                p = line.split()
                if (p[2], p[3]) in want:
                    ids[p[1]] = want[(p[2], p[3])]
    return data


def vector(path, module, name):
    vid, out = None, []
    with open(path) as fh:
        for line in fh:
            if line.startswith("vector "):
                p = line.split()
                if p[2] == module and p[3] == name:
                    vid = p[1]
            elif vid is not None and line.startswith(vid + "\t"):
                p = line.rstrip("\n").split("\t")
                out.append((pcapng.simtime_ps(p[2]), float(p[3])))
    return out


def gmask(f):
    """Bytes of a gPTP frame with the correctionField and the FCS masked (for FU identity)."""
    b = bytearray(f["raw"])
    if f["type"] in (SYNC, FU) and len(b) >= 30:
        b[22:30] = b"\0" * 8
    b[-4:] = b"\0\0\0\0"
    return bytes(b)


# ---------------------------------------------------------------------------------------
class Run:
    """One run of the 5GS (network M1Bridge) or of the unit topology (M2S5ChainTest)."""
    def __init__(self, runs, cfg, rep=0, unit=False):
        self.cfg, self.rep, self.unit = cfg, rep, unit
        self.base = os.path.join(runs, cfg)
        pdir = os.path.join(self.base, "pcap", f"{cfg}-{rep}")
        self.ldir = os.path.join(self.base, "m2log", f"{cfg}-{rep}")
        self.sca_path = os.path.join(self.base, cfg, f"{rep}.sca")
        self.vec_path = os.path.join(self.base, cfg, f"{rep}.vec")
        if unit:
            net, self.gmn, self.nwn, self.dsn, self.sln = "M2S5ChainTest", "gm", "ttN", "ttD", "slave"
            P = lambda n, i: os.path.join(pdir, f"{net}.{n}.pcapRecorder[{i}].pcapng")  # noqa: E731
            self.gm = frames(P("gm", 0))
            self.nw1, self.nw0 = frames(P("ttN", 1)), frames(P("ttN", 0))
            self.ds0, self.ds1 = frames(P("ttD", 0)), frames(P("ttD", 1), bit_ps=10 * NS)
            self.sl = frames(P("slave", 0), bit_ps=10 * NS)
        else:
            net, self.gmn, self.nwn, self.dsn, self.sln = "M1Bridge", "listener", "nwTt", "dsTt", "talker"
            P = lambda n, i: os.path.join(pdir, f"{net}.{n}.pcapRecorder[{i}].pcapng")  # noqa: E731
            self.gm = frames(P("listener", 0))
            self.nw1, self.nw0 = frames(P("nwTt", 1)), frames(P("nwTt", 0))
            self.ds0, self.ds1 = frames(P("dsTt", 0)), frames(P("dsTt", 1))
            self.sl = frames(P("talker", 0))
            self.ue, self.dn = frames(P("ue[0]", 0)), frames(P("upf", 1))
            self.n3path = P("upf", 0)
        self.net = net
        self.station = f"{net}.{self.sln}"
        tc = lambda tt: os.path.join(self.ldir, f"{net}.{tt}.eth[1].trafficConditionerLayer")  # noqa: E731
        self.nwlog = read_csv(tc(self.nwn) + ".syncIn.sync.csv")
        self.dslog = read_csv(tc(self.dsn) + ".syncOut.sync.csv")
        self.nweng = read_csv(tc(self.nwn) + ".engine.pdelay.csv")
        self.nweng_path = tc(self.nwn) + ".engine.pdelay.csv"
        self.sc = scalars_all(self.sca_path)
        self.V = read_vec(self.vec_path, self.station)

    def s(self, mod, name, default=0):
        return self.sc.get((f"{self.net}.{mod}", name), default)

    def nwsc(self, name):
        return int(self.s(f"{self.nwn}.eth[1].trafficConditionerLayer.syncIn", name, 0))

    def dssc(self, name):
        return int(self.s(f"{self.dsn}.eth[1].trafficConditionerLayer.syncOut", name, 0))

    # PCAP-derived quantities -------------------------------------------------------------
    def lup_table(self):
        """[(publication time = Resp_FU last bit at NW-TT, D)] of the NW-TT's completed exchanges."""
        nwo, nwi = sel(self.nw1, 2, REQ, dom=None), sel(self.nw1, 1, RESP, RFU, dom=None)
        gmi, gmo = sel(self.gm, 1, REQ, dom=None), sel(self.gm, 2, RESP, dom=None)
        req, resp, rfu = by_seq(nwo), by_seq([f for f in nwi if f["type"] == RESP]), by_seq([f for f in nwi if f["type"] == RFU])
        greq, gresp = by_seq(gmi), by_seq(gmo)
        # the engine publishes only exchanges it completed: its log rows "measure" (seq); D from PCAP
        published = [int(r["seq"]) for r in self.nweng if r["event"] == "measure"]
        out, prev = [], None
        for s in published:
            t1, t2, t3, t4 = req[s][0]["start"], greq[s][0]["start"], gresp[s][0]["start"], resp[s][0]["start"]
            D, _ = C4.link_delay(t1, t2, t3, t4, prev)
            prev = (t3, t4)
            out.append((rfu[s][0]["end"], D, s))
        return out

    def lup_at(self, t):
        d = [D for te, D, s in self.lup_table_cache if te < t]
        return d[-1] if d else None

    def prepare(self):
        self.lup_table_cache = self.lup_table()
        self.nw_sync = by_seq(sel(self.nw1, 1, SYNC))
        self.nw_fu = by_seq(sel(self.nw1, 1, FU))
        self.ds_sync = by_seq(sel(self.ds1, 2, SYNC))
        self.gm_sync = by_seq(sel(self.gm, 2, SYNC))
        self.gm_fu = by_seq(sel(self.gm, 2, FU))
        return self


def n3_inner(path):
    """N3 (UPF ppp[0]): GTP-U inner Ethernet frames after IPv4 reassembly: [(dir, QFI, bytes)].
    Same as check_m2s4.n3_inner except the UDP port (see M2-S4 erratum row E1)."""
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
        # GTP-U on UDP: Simu5G 1.8.0 uses UDP port 31 (tunnelPeerPort), not 2152; identified by
        # port and by the GTP-U header (version 1, message type 0xFF G-PDU)
        if proto != 17 or len(pl) < 16 or struct.unpack(">H", pl[2:4])[0] not in (31, 2152) or pl[8] >> 5 != 1:
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



def fcs_drops(R):
    """frames dropped by each INET FCS checker (incoming - outgoing packet counts)"""
    out = {}
    for (mod, name), v in R.sc.items():
        if mod.endswith("fcsChecker") and name == "incomingPackets:count":
            d = int(v - R.sc.get((mod, "outgoingPackets:count"), v))
            if d:
                out[mod[len(R.net) + 1:]] = d
    return out


def enc(ps):
    return M.inet_write_clock8(ps)


# ---------------------------------------------------------------------------------------
# slave model adapter (M2-S3 model, unchanged)
class Slave:
    def __init__(self, R, cf_by_seq):
        self.sl_in = [{"end": f["end"], "start": f["start"], "g": f["g"]} for f in R.sl if f["dir"] == 1 and f["g"] and f["f"]["fcs_ok"]]
        self.sl_out = [{"end": f["end"], "start": f["start"], "g": f["g"]} for f in R.sl if f["dir"] == 2 and f["g"]]
        self.sim_pot = {s: v[0]["start"] for s, v in by_seq(sel(R.gm, 2, SYNC)).items()}
        # the slave's responder: the DS-TT engine (Pdelay terminated), or the GM when Pdelay is
        # forwarded end to end (N14): t2/t3 are the responder's own first bits
        if any(f["g"] and f["g"]["spi"][0] == 0xD1 for f in sel(R.ds1, 2, RESP, dom=None)) or R.unit:
            req_rx, resp_tx = sel(R.ds1, 1, REQ, dom=None), sel(R.ds1, 2, RESP, dom=None)
        else:
            req_rx, resp_tx = sel(R.gm, 1, REQ, dom=None), sel(R.gm, 2, RESP, dom=None)
        self.sim_t2 = {s: v[0]["start"] for s, v in by_seq(req_rx).items()}
        self.sim_t3 = {s: v[0]["start"] for s, v in by_seq(resp_tx).items()}
        self.cf = cf_by_seq


def cf_map(R):
    """cf (ps) of every Follow_Up the DS-TT let through, by sequenceId, from its log."""
    out = {}
    for r in R.dslog:
        if r["event"] in ("corrected", "forwardedInvalidTest"):
            out[int(r["seq"])] = int(r["cfOut"])
    return out


def model_run(R, cf=None, initial=0):
    cf = cf_map(R) if cf is None else cf
    sl = Slave(R, cf)
    return O.model(sl, "sim", cf_fn=lambda f: sl.cf.get(f["g"]["seq"], M.inet_read_clock8(f["g"]["cf_raw"])), initial=initial)


def compare_recorded(m, V, initial=0):
    """oracle_m2s3.compare_recorded with the slave clock's initial value as a parameter (the M2-S3
    version assumes 0; needed for the initial-offset run S4). Otherwise identical."""
    mm = Counter()
    rec_pd = [(O.ps(t), float(v)) for t, v in V["pdelay"]]
    rec_gm = [(O.ps(t), float(v)) for t, v in V["gm"]]
    rec_nrr = [(O.ps(t), float(v)) for t, v in V["nrr"]]
    rec_comp = [(O.ps(t), float(v)) for t, v in V["comp"]]
    steps = m.clk.steps
    mod_pd = [(t, O.dbl(v)) for t, v in m.out["pdelay"]]
    if rec_pd != mod_pd:
        mm["pdelay"] += 1 + sum(1 for a, b in zip(rec_pd, mod_pd) if a != b)
    if rec_gm != m.out["gm"]:
        mm["gmRateRatio"] += 1 + sum(1 for a, b in zip(rec_gm, m.out["gm"]) if a != b)
    if rec_nrr != m.out["nrr"]:
        mm["neighborRateRatio"] += 1 + sum(1 for a, b in zip(rec_nrr, m.out["nrr"]) if a != b)
    # oscillatorCompensationChanged: initial value 0 at t = 0, then one sample per step
    mod_comp = [(0, 0.0)] + [(t, p) for t, o, n, p in steps]
    if rec_comp != mod_comp:
        mm["compensation"] += 1 + sum(1 for a, b in zip(rec_comp, mod_comp) if a != b)
    # timeChanged: periodic samples (emitClockTimeInterval 1 ms) and the old value at every step
    # (SettableClock.cc:81); at a step time the samples are the old value, then the new value.
    tc = [(O.ps(t), float(v)) for t, v in V["clock"]]
    step_at = {t: (o, n) for t, o, n, p in steps}
    c, i, seen, n_step_samples = M.Clock(initial), 0, Counter(), 0
    for t, v in tc:
        while i < len(steps) and steps[i][0] < t:
            c.set(steps[i][0], steps[i][2], steps[i][3])
            i += 1
        k = seen[t]
        seen[t] += 1
        if t in step_at:
            n_step_samples += 1
            exp = step_at[t][0] if k == 0 else step_at[t][1]
            if k == 0 and c.at(t) != step_at[t][0]:
                mm["step old value vs replay"] += 1
        else:
            exp = c.at(t)
        if v != O.dbl(exp):
            mm["clock sample"] += 1
    steps_sampled = sum(1 for t in step_at if seen[t] >= 1)
    if steps_sampled != len(steps):
        mm["steps without a recorded sample"] += len(steps) - steps_sampled
    counts = {"pdelay": len(rec_pd), "nRR": len(rec_nrr), "gm": len(rec_gm), "comp": len(rec_comp) - 1,
              "steps": len(steps), "clock samples": len(tc), "step samples": n_step_samples}
    return not mm, counts, mm



def clock_samples(V):
    return [(pcapng.simtime_ps(t), float(v)) for t, v in V["clock"]]


# ---------------------------------------------------------------------------------------
# per-run rows
def rows_5gs(R, R4=None, exp_missing=0, offset=0):
    """Rows for one 5GS run with the correction on. R4: the M2-S4 counterpart (same seed)."""
    res = {}
    R.prepare()
    lup = R.lup_at
    # ---- C1: NW-TT rewrite on the wire, at every 5GS point
    probs, n = [], 0
    pts = [("NW-TT eth[0]", sel(R.nw0, 2, FU)), ("UE eth[0]", sel(R.ue, 2, FU)), ("UPF dnEth", sel(R.dn, 1, FU)),
           ("DS-TT eth[0]", sel(R.ds0, 1, FU))]
    corrected_nw = {int(r["seq"]) for r in R.nwlog if r["event"] == "corrected"}
    invalid_nw = {int(r["seq"]) for r in R.nwlog if r["event"] == "invalid"}
    for name, fr in pts:
        for f in fr:
            s = f["seq"]
            src = R.nw_fu.get(s)
            if not src or not f["g"]:
                probs.append(f"{name} FU {s}: no source")
                continue
            n += 1
            l = lup(src[0]["end"])
            if l is None and s in corrected_nw:
                probs.append(f"{name} FU {s}: corrected by the NW-TT but no NW-TT link-delay exchange in PCAP")
                continue
            exp = enc((M.inet_read_clock8(src[0]["g"]["cf_raw"])) + (l if s in corrected_nw else 0))
            same = gmask(f)[14:] == gmask(src[0])[14:]
            if f["g"]["cf_raw"] != exp or not same or not f["f"]["fcs_ok"] or f["L"] != 94:
                probs.append(f"{name} FU {s}: cf_raw {f['g']['cf_raw']} expected {exp} (Lup {l}), other bytes equal {same}, "
                             f"FCS {f['f']['fcs_ok']}")
    n3 = 0
    for direction, qfi, inner in n3_inner(R.n3path):
        isg, mt, _ = C4.inner_type(inner)
        if isg and mt == FU:
            n3 += 1
            s = int.from_bytes(inner[14 + 30:14 + 32], "big")
            src = R.nw_fu.get(s)
            if not src:
                continue
            cf_raw = int.from_bytes(inner[22:30], "big", signed=True)
            l = lup(src[0]["end"])
            if l is None:
                probs.append(f"N3 FU {s}: no NW-TT link-delay exchange")
                continue
            exp = enc(M.inet_read_clock8(src[0]["g"]["cf_raw"]) + (l if s in corrected_nw else 0))
            if cf_raw != exp:
                probs.append(f"N3 FU {s}: cf_raw {cf_raw} expected {exp}")
    res["C1"] = (not probs and n > 0 and n3 > 0, f"{n} Follow_Ups at 4 Ethernet points + {n3} on N3; problems: {probs[:3] or 'none'}")
    # ---- C2: DS-TT rewrite on the wire, at DS-TT eth[1] out and at the slave
    probs, n, delivered = [], 0, []
    for name, fr in (("DS-TT eth[1]", sel(R.ds1, 2, FU)), ("slave", sel(R.sl, 1, FU))):
        for f in fr:
            s = f["seq"]
            src, ns, ds = R.nw_fu.get(s), R.nw_sync.get(s), R.ds_sync.get(s)
            if not (src and ns and ds and f["g"]):
                probs.append(f"{name} FU {s}: Sync/FU not traceable")
                continue
            n += 1
            if name == "slave":
                delivered.append(s)
            res_k = ds[-1]["start"] - ns[0]["start"]
            l = lup(src[0]["end"])
            exp = enc(M.inet_read_clock8(src[0]["g"]["cf_raw"]) + l + res_k) if l is not None else None
            same = gmask(f)[14:] == gmask(src[0])[14:]
            if f["g"]["cf_raw"] != exp or not same or not f["f"]["fcs_ok"] or f["L"] != 94:
                probs.append(f"{name} FU {s}: cf_raw {f['g']['cf_raw']} expected {exp} (Lup {l}, Res {res_k}), equal {same}, FCS {f['f']['fcs_ok']}")
    res["C2"] = (not probs and n > 0, f"{n} Follow_Ups (DS-TT eth[1] + slave); problems: {probs[:3] or 'none'}")
    # ---- C3: logged simulation values = PCAP-derived values
    probs = []
    for r in R.nwlog:
        if r["event"] == "sync":
            s = int(r["seq"])
            if int(r["TSi"]) not in [f["start"] for f in R.nw_sync.get(s, [])]:
                probs.append(f"NW Sync {s}: TSi {r['TSi']} not a PCAP first bit")
        elif r["event"] == "corrected":
            s = int(r["seq"])
            src = R.nw_fu[s][0]
            l = lup(src["end"])
            if l is None:
                probs.append(f"NW FU {s}: corrected without a NW-TT link-delay exchange in PCAP")
                continue
            if int(r["Lup"]) != l or int(r["TSi"]) != R.nw_sync[s][-1]["start"] or int(r["cfOut"]) != int(r["cfIn"]) + l \
                    or r["rrIn"] != "1" or r["rrOut"] != "1":
                probs.append(f"NW FU {s}: logged Lup {r['Lup']} TSi {r['TSi']} cf {r['cfIn']}->{r['cfOut']} rr {r['rrIn']}/{r['rrOut']} "
                             f"vs PCAP Lup {l} TSi {R.nw_sync[s][-1]['start']}")
    for r in R.dslog:
        if r["event"] == "corrected":
            s = int(r["seq"])
            ds = R.ds_sync.get(s)
            tse, tsi = int(r["TSe"]), int(r["TSi"])
            if not ds or tse != ds[-1]["start"] or tsi != R.nw_sync[s][-1]["start"] or int(r["Res"]) != tse - tsi \
                    or int(r["cfOut"]) != int(r["cfIn"]) + tse - tsi or r["rrOut"] != "1":
                probs.append(f"DS FU {s}: logged TSe {tse} TSi {tsi} Res {r['Res']} cf {r['cfIn']}->{r['cfOut']} vs PCAP TSe "
                             f"{ds[-1]['start'] if ds else None}")
    res["C3"] = (not probs, f"problems: {probs[:3] or 'none'}")
    # ---- C4: Sync untouched
    probs = []
    gm_s = [f["f"]["payload"] for f in sel(R.gm, 2, SYNC)]
    it = iter(gm_s)
    sl_s = [f["f"]["payload"] for f in sel(R.sl, 1, SYNC)]
    if not all(any(x == y for y in it) for x in sl_s):
        probs.append("slave Syncs not an in-order byte-identical subsequence of the GM's")
    for name, fr in (("NW-TT eth[0]", R.nw0), ("UE", R.ue), ("dnEth", R.dn), ("DS-TT eth[0]", R.ds0), ("DS-TT eth[1]", R.ds1), ("slave", R.sl)):
        bad = [f["seq"] for f in fr if f["type"] == SYNC and f["g"] and f["g"]["cf_raw"] != 0]
        if bad:
            probs.append(f"{name}: Sync correctionField != 0 for {bad[:4]}")
    res["C4"] = (not probs, f"{len(sl_s)} of {len(gm_s)} Syncs delivered byte-identical, cf 0 everywhere; problems: {probs[:3] or 'none'}")
    # ---- C5: rate ratio (csro 0 on the wire; logged rr 1)
    bad = [(f["seq"]) for fr in (R.nw0, R.ds1, R.sl) for f in fr if f["type"] == FU and f["g"] and f["g"]["csro"] != 0]
    res["C5"] = (not bad, f"Follow_Up TLV csro 0 at NW-TT eth[0], DS-TT eth[1], slave; problems: {bad[:4] or 'none'}")
    # ---- C6: FCS
    bad = []
    for name, fr in (("GM", R.gm), ("NW1", R.nw1), ("NW0", R.nw0), ("UE", R.ue), ("dn", R.dn), ("DS0", R.ds0), ("DS1", R.ds1), ("slave", R.sl)):
        bad += [f"{name} {f['type']}/{f['seq']}" for f in fr if f["type"] in (SYNC, FU) and not f["f"]["fcs_ok"]]
    drops = fcs_drops(R)
    res["C6"] = (not bad and not drops, f"bad FCS {bad[:4] or 0}; INET FCS-checker drops {drops or 0}")
    # ---- C7: association and delivery at the slave
    probs = []
    seq = [(f["type"], f["seq"]) for f in R.sl if f["dir"] == 1 and f["type"] in (SYNC, FU) and f["dom"] == 0 and f["f"]["fcs_ok"]]
    for i, (t, s) in enumerate(seq):
        if t == FU and (i == 0 or seq[i - 1] != (SYNC, s)):
            probs.append(f"FU {s} not right after its Sync")
    fus = [s for t, s in seq if t == FU]
    if len(fus) != len(set(fus)):
        probs.append("a Follow_Up delivered twice")
    ds_corr = sorted(int(r["seq"]) for r in R.dslog if r["event"] == "corrected")
    if sorted(fus) != ds_corr:
        probs.append(f"delivered {len(fus)} != DS-TT corrected {len(ds_corr)}")
    n_sync_gm = len(sel(R.gm, 2, SYNC))
    res["C7"] = (not probs and len(fus) == n_sync_gm - exp_missing,
                 f"{len(fus)} Follow_Ups delivered, each right after its own Sync, once (GM Syncs {n_sync_gm}, expected missing "
                 f"{exp_missing}); problems: {probs[:3] or 'none'}")
    # ---- C8: tag containment and M2-S0 carriage
    audit = R.s(f"{R.sln}.eth[0].trafficConditionerLayer.audit", "framesWithSyncTag", -1)
    m2s0 = {k[1]: v for k, v in R.sc.items() if k[0] == f"{R.net}.{R.dsn}.eth[1].measurementLayer.egress"}
    ok8 = audit == 0
    detail8 = f"frames with a TtSyncIngressTag at the slave: {int(audit)}"
    if R4 is not None:
        m4 = {k[1]: v for k, v in R4.sc.items() if k[0] == f"{R4.net}.{R4.dsn}.eth[1].measurementLayer.egress"}
        names = ("framesRecovered", "framesInvalidTag", "framesUntaggedAtEgress", "framesStripped")
        same = all(m2s0.get(k) is not None and m2s0.get(k) == m4.get(k) for k in names)
        ok8 &= same and m2s0.get("framesInvalidTag", -1) == 0
        detail8 += (f"; DS-TT M2-S0 egress recovered/invalid/untagged {int(m2s0.get('framesRecovered', -1))}/"
                    f"{int(m2s0.get('framesInvalidTag', -1))}/{int(m2s0.get('framesUntaggedAtEgress', -1))} = M2S4: {same}")
    res["C8"] = (ok8, detail8)
    # ---- S1: slave replay
    m = model_run(R, initial=offset)
    okc1, counts, mm = compare_recorded(m, R.V, offset)
    res["S1"] = (okc1, f"replay {counts}; mismatches {dict(mm) or 0}")
    # ---- S2: zero error after the first step
    steps = m.clk.steps
    after = [x for x in m.out["fu"]][1 if offset else 0:]
    nonzero = [(x["seq"], x["diff"]) for x in after if x["diff"] != 0]
    samples = clock_samples(R.V)
    t0 = steps[0][0] if steps else None
    errs = [(t, v - O.dbl(t)) for t, v in samples if t0 is not None and t > t0]
    bad_samples = [(t, e) for t, e in errs if e != 0.0]
    comp_bad = [v for t, v in R.V["comp"] if float(v) != 0.0]
    gm_bad = [v for t, v in R.V["gm"] if float(v) != 1.0]
    first_err = (m.out["fu"][0]["new"] - m.out["fu"][0]["t"]) if m.out["fu"] else None
    res["S2"] = (okc1 and not nonzero and not bad_samples and not comp_bad and not gm_bad and len(m.out["fu"]) > 0,
                 f"{len(m.out['fu'])} steps, error after step 1: {fmt(first_err) if first_err is not None else '-'}; "
                 f"non-zero step corrections after step 1 {nonzero[:3] or 0}; recorded clock samples after step 1 with error != 0: "
                 f"{len(bad_samples)} of {len(errs)}; compensation != 0: {len(comp_bad)}; gmRateRatio != 1: {len(gm_bad)}")
    res["_model"] = m
    # ---- S3: online = offline oracle on the M2-S4 records
    if R4 is not None:
        R4.prepare()
        pred, same_n, diff = {}, 0, []
        for s, ds in R.ds_sync.items():
            a = (R.nw_sync.get(s, [{}])[0].get("start"), ds[-1]["start"], R.gm_sync.get(s, [{}])[0].get("start"))
            b = (R4.nw_sync.get(s, [{}])[0].get("start"), R4.ds_sync.get(s, [{}])[-1].get("start"), R4.gm_sync.get(s, [{}])[0].get("start"))
            if a == b and None not in a:
                same_n += 1
                d4 = R4.lup_at(R4.nw_fu[s][0]["end"]) or 0
                pred[s] = d4 + (b[1] - b[0])
            else:
                diff.append(s)
        logged = cf_map(R)
        mism = [(s, logged.get(s), v) for s, v in pred.items() if s in logged and logged[s] != v]
        # clock trace predicted offline from the M2-S4 records with cf' = D_NWTT + Res
        m4 = model_run(R4, cf=pred, initial=offset)
        st = [t for t, v in samples]
        pv = O.replay_at(m4.clk.steps, offset, st)
        trace_bad = sum(1 for (t, v), p in zip(samples, pv) if v != O.dbl(p))
        res["S3"] = (not mism and not diff and trace_bad == 0 and same_n > 0,
                     f"{same_n} Syncs with identical (TSi, TSe, POT) in M2S4 and M2S5 ({len(diff)} differ: {diff[:4]}); logged cf2 = "
                     f"M2-S4 prediction D_NWTT + Res for all ({len(mism)} mismatches {mism[:2]}); recorded clock trace = offline "
                     f"prediction at {len(st) - trace_bad} of {len(st)} samples")
    # ---- P1/P2: Pdelay preserved
    probs = []
    Ds = sorted({D for t, D, s in R.lup_table_cache})
    if Ds != [L_REF]:
        probs.append(f"NW-TT link delays from PCAP {Ds}")
    if R4 is not None:
        same = os.path.exists(R.nweng_path) and G.sha(R.nweng_path) == G.sha(R4.nweng_path)
        if not same:
            probs.append("NW-TT engine log differs from M2S4")
    res["P1"] = (not probs, f"NW-TT D from PCAP {Ds} ps; engine log byte-identical to M2S4: {R4 is not None and not probs}; "
                 f"problems: {probs or 'none'}")
    pd = [float(v) for t, v in R.V["pdelay"]]
    in5gs = sum(1 for fr in (R.nw0, R.ue, R.dn, R.ds0) for f in fr if f["type"] in PDELAY)
    in5gs += sum(1 for d, q, inner in n3_inner(R.n3path) if C4.inner_type(inner)[0] and C4.inner_type(inner)[1] in PDELAY)
    res["P2"] = (pd and all(v == O.dbl(L_REF) for v in pd) and in5gs == 0,
                 f"slave pdelay {sorted(set(pd))} s ({len(pd)} samples); Pdelay frames in the 5GS: {in5gs}")
    return res


# ---------------------------------------------------------------------------------------
# G1: baseline identity vs M2-S4
def g1(R, R4):
    """(ok, detail). Point by point, frames are matched in order by (direction, gPTP type,
    bytes with correctionField and FCS masked). Every frame must be present in both runs with
    the same bytes except the Follow_Up correctionField/FCS downstream of the NW-TT, and the
    same time, except frames explained by the slave's clock-driven Pdelay timing (F11):
    Pdelay frames on the slave link, frames the slave queued behind its own Pdelay_Req (and
    their copies further upstream, shifted by the same amount), and frames the DS-TT queued
    behind its Pdelay_Resp / Resp_Follow_Up."""
    pts = [("GM", R.gm, R4.gm), ("NW-TT eth[1]", R.nw1, R4.nw1), ("NW-TT eth[0]", R.nw0, R4.nw0), ("UE eth[0]", R.ue, R4.ue),
           ("UPF dnEth", R.dn, R4.dn), ("DS-TT eth[0]", R.ds0, R4.ds0), ("DS-TT eth[1]", R.ds1, R4.ds1), ("slave", R.sl, R4.sl)]
    upstream_of_rewrite = {"GM", "NW-TT eth[1]"}
    # frames queued behind a Pdelay frame at the slave (UL) or at the DS-TT (DL), in either run
    def queued_behind_pdelay(fr, direction, types):
        """frames transmitted back to back (gap <= 96 bit times at 1 Gb/s) after a Pdelay frame"""
        out, prev = set(), None
        for f in fr:
            if f["dir"] != direction:
                continue
            if prev is not None and prev["type"] in types and 0 <= f["start"] - prev["end"] <= 96 * NS:
                out.add((f["dir"], f["type"], hashlib.sha1(gmask(f)).hexdigest()))
            prev = f
        return out
    def queued_closure(fr, direction, types):
        """frames back to back behind a Pdelay frame, or behind such a frame (transitively)"""
        out, prev, chain = set(), None, False
        for f in fr:
            if f["dir"] != direction:
                continue
            back_to_back = prev is not None and 0 <= f["start"] - prev["end"] <= 96 * NS
            if back_to_back and (prev["type"] in types or chain) and f["type"] not in types:
                out.add((f["dir"], f["type"], hashlib.sha1(gmask(f)).hexdigest()))
                chain = True
            else:
                chain = False
            prev = f
        return out
    affected = set()
    for fr in (R.sl, R4.sl):
        affected |= queued_closure(fr, 2, (REQ,))
    for fr in (R.ds1, R4.ds1):
        affected |= queued_closure(fr, 2, (RESP, RFU))
    aff_ul = {(h) for d, t, h in affected}
    probs, counts, shifts = [], Counter(), defaultdict(set)
    for name, a, b in pts:
        ka, kb = defaultdict(list), defaultdict(list)
        for f in a:
            ka[(f["dir"], f["type"], hashlib.sha1(gmask(f)).hexdigest())].append(f)
        for f in b:
            kb[(f["dir"], f["type"], hashlib.sha1(gmask(f)).hexdigest())].append(f)
        slave_link = name in ("DS-TT eth[1]", "slave")
        for k in sorted(set(ka) | set(kb), key=repr):  # deterministic output order
            if len(ka[k]) != len(kb[k]):
                if slave_link and k[1] in PDELAY:
                    counts[f"{name}: Pdelay frames with different content (slave link, F11)"] += abs(len(ka[k]) - len(kb[k]))
                    continue
                probs.append(f"{name}: frame {k[:2]} count {len(ka[k])} vs {len(kb[k])}")
                continue
            for x, y in zip(ka[k], kb[k]):
                counts["frames"] += 1
                if x["raw"] != y["raw"]:
                    if not (k[1] == FU and name not in upstream_of_rewrite):
                        probs.append(f"{name}: bytes differ {k[:2]} seq {x['seq']}")
                if (x["end"], x["dir"]) != (y["end"], y["dir"]):
                    if slave_link and k[1] in PDELAY:
                        counts[f"{name}: Pdelay frame time (slave link, F11)"] += 1
                    elif k[2] in aff_ul:
                        counts[f"{name}: queued behind a slave-link Pdelay frame"] += 1
                        shifts[k[2]].add(x["end"] - y["end"])
                    else:
                        probs.append(f"{name}: time differs {k[:2]} seq {x['seq']} {y['end']} -> {x['end']}")
    # N3: same records (time, direction, length); reassembled inner frames equal except Follow_Up cf/FCS
    n3a, n3b = list(pcapng.read(R.n3path)), list(pcapng.read(R4.n3path))
    if [(x["t_ps"], x["dir"], len(x["data"])) for x in n3a] != [(x["t_ps"], x["dir"], len(x["data"])) for x in n3b]:
        probs.append("N3 record times/directions/lengths differ")
    counts["N3 records"] = len(n3a)
    counts["N3 records with different bytes (Follow_Up)"] = sum(1 for x, y in zip(n3a, n3b) if x["data"] != y["data"])
    def mask_inner(fr):
        b = bytearray(fr)
        isg, mt, _ = C4.inner_type(fr)
        if isg and mt == FU:
            b[22:30] = b"\0" * 8
            b[-4:] = b"\0" * 4
        return bytes(b)
    ia = [(d, q, mask_inner(f)) for d, q, f in n3_inner(R.n3path)]
    ib = [(d, q, mask_inner(f)) for d, q, f in n3_inner(R4.n3path)]
    if ia != ib or not ia:
        probs.append(f"N3 inner frames differ beyond Follow_Up cf/FCS ({len(ia)} vs {len(ib)})")
    counts["N3 inner frames"] = len(ia)
    nonconst = [h for h, v in shifts.items() if len(v) != 1]
    if nonconst:
        probs.append(f"{len(nonconst)} affected frames with a shift that changes along their path")
    return not probs, f"{counts['frames']} frames matched at 8 points + N3; explained differences {dict((k, v) for k, v in counts.items() if k != 'frames')}; " \
                      f"shifts {sorted({next(iter(v)) for v in shifts.values()})}; problems: {probs[:4] or 'none'}"


# ---------------------------------------------------------------------------------------
def main():
    os.makedirs(OUT, exist_ok=True)
    # ---- G0 on the final code (TtPtpPort passive), vs M2-S4 (and the unit base)
    okg, grows, totals = G.gate(RUNS, RUNS4)
    s1, s2 = G.sensitivity(RUNS, RUNS4)
    add("G0", "passive transparency on the final code: M2S5-passive (seeds 0-9, frag, load, load-harq16) = M2S4, and "
        "M2S5U-passive = M2S5U-base: PCAP, per-frame and Pdelay-engine logs, vectors, scalars, parameters (only the "
        "compound's typename and its 3 new parameters differ), final event numbers; sensitivity controls detect a "
        "different seed and variant", okg and s1 > 0 and s2 > 0,
        f"{sum(1 for r in grows if r[1])}/{len(grows)} run pairs identical; totals {totals}; sensitivity {s1}/{s2} differences"
        + ("" if okg else f"; {[r[:3] for r in grows if not r[1]][:2]}"))
    # ---- A0 provenance of the M2-S4 inputs
    h = {}
    with open(HASHES4) as fh:
        for line in fh:
            d, n = line.rstrip("\n").split("  ", 1)
            h[os.path.normpath(os.path.join(RUNS4, n))] = d
    bad, n = [], 0
    for c4, _, reps in G.PAIRS:
        for r in reps:
            for sub in (f"pcap/{c4}-{r}", f"m2log/{c4}-{r}"):
                for name, path in G.files(os.path.join(RUNS4, c4, sub)).items():
                    n += 1
                    if h.get(os.path.normpath(path)) != G.sha(path):
                        bad.append(os.path.relpath(path, RUNS4))
    add("A0", "provenance: every M2-S4 PCAP and log used (G0, G1, S3, P1) is hash-identical to M2-S4/raw-outputs.sha256",
        not bad and n > 0, f"{n} files; mismatches {bad[:3] or 'none'}")
    # ---- E1: erratum to M2-S4 T1 (its N3 parser looked for UDP port 2152; Simu5G 1.8.0 uses 31,
    # so its N3 sub-check found no GTP-U frame at all). Re-checked here on the M2-S4 runs.
    e1, tot = [], Counter()
    for c4, _, reps in G.PAIRS:
        for r in reps:
            p4 = os.path.join(RUNS4, c4, "pcap", f"{c4}-{r}", "M1Bridge.upf.pcapRecorder[0].pcapng")
            old = len(C4.n3_inner(p4))
            inner = n3_inner(p4)
            c = Counter(C4.inner_type(f)[1] for d, q, f in inner if C4.inner_type(f)[0])
            tot["GTP-U inner frames"] += len(inner)
            tot["Sync/Follow_Up"] += c[SYNC] + c[FU]
            tot["Pdelay"] += sum(c[t] for t in PDELAY)
            tot["frames found by the M2-S4 parser"] += old
            if sum(c[t] for t in PDELAY) or not (c[SYNC] and c[FU]):
                e1.append(f"{c4}#{r}: {dict(c)}")
    add("E1", "erratum, M2-S4 T1 (N3 part): the M2-S4 checker parsed GTP-U on UDP port 2152 and therefore found no N3 frame "
        "(the N3 sub-check was vacuous; the Ethernet points carried T1). Re-check with Simu5G's port 31 on the M2-S4 runs: no "
        "Pdelay frame inside any GTP-U tunnel, Sync/Follow_Up present", not e1 and tot["Sync/Follow_Up"] > 0,
        f"{dict(tot)}; problems {e1[:3] or 'none'}")
    # ---- V0 / V1
    vrows = []
    for cfg in ("M2S5-v0", "M2S5-v0-frag", "M2S5-v0-load"):
        ok, info, probs = V0.v0_run(RUNS, cfg)
        vrows.append((cfg, ok, info, probs))
    add("V1", "INVALID/VALID tag survival NW-TT -> DS-TT (gate V0 re-checked on the final code), idle / frag / load",
        all(r[1] for r in vrows), "; ".join(f"{c}: {i}" + ("" if ok else f" {p[:2]}") for c, ok, i, p in vrows))

    # ---- primary 5GS runs
    PRIMARY = [("M2S5", r, "M2S4", r) for r in range(10)] + [("M2S5-frag", 0, "M2S4-frag", 0), ("M2S5-load", 0, "M2S4-load", 0),
                                                            ("M2S5-load-harq16", 0, "M2S4-load-harq16", 0)]
    ROWS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "S1", "S2", "S3", "P1", "P2")
    agg = defaultdict(list)
    keep = {}
    g1rows = []
    for c5, r5, c4, r4 in PRIMARY:
        R = Run(RUNS, c5, r5)
        R4 = Run(RUNS4, c4, r4)
        miss = len(sel(R4.gm, 2, SYNC)) - len(sel(R4.sl, 1, FU))
        res = rows_5gs(R, R4, exp_missing=miss)
        keep[(c5, r5)] = (R, res)
        for k in ROWS:
            agg[k].append((f"{c5}#{r5}", res[k]))
        g1rows.append((f"{c5}#{r5}",) + g1(R, R4))
    desc = {
        "C1": "NW-TT rewrite on the wire: at NW-TT eth[0], UE eth[0], UPF dnEth, N3 (GTP-U inner) and DS-TT eth[0], every Follow_Up's correctionField = enc(cf_GM + Lup_pcap); all other bytes = the GM's; FCS valid; 94 B",
        "C2": "DS-TT rewrite on the wire: at DS-TT eth[1] and the slave, correctionField = enc(cf_GM + Lup_pcap + Res_pcap); all other bytes = the GM's; FCS valid; 94 B",
        "C3": "logged simulation values (ps) = PCAP: TSi, TSe = first bits, Lup = Lup_pcap, Res = TSe - TSi, cf1 = cf_in + Lup, cf2 = cf1 + Res, rr 1",
        "C4": "Syncs untouched: byte-identical GM -> slave (in order), correctionField 0 at every point",
        "C5": "rateRatio: Follow_Up TLV cumulativeScaledRateOffset 0 on the wire; logged rr_in = rr_out = 1 (not validated through the slave, F9)",
        "C6": "FCS: every Sync/Follow_Up valid at every point; INET FCS checkers drop nothing",
        "C7": "association and delivery: at the slave each Follow_Up right after its own Sync, once; delivered = DS-TT corrected; only the pairs M2-S4 also lost are missing",
        "C8": "containment: no TtSyncIngressTag reaches the slave; M2-S0 tag recovery at DS-TT eth[1] as in M2S4, invalid 0",
        "S1": "the M2-S3 slave model (unchanged), fed this run's PCAP and the DS-TT's cf (ps), reproduces every recorded slave value exactly",
        "S2": "slave clock error 0 ps exactly: every step correction 0, every recorded 1 ms / step sample after step 1 = GM time, compensation 0, gmRateRatio 1",
        "S3": "online = offline oracle: for every Sync with identical TSi/TSe/POT in M2S4 and M2S5, cf2 = D_NWTT + Res computed from the M2-S4 records; the recorded clock trace = the M2-S3 model's prediction from the M2-S4 records",
        "P1": "Pdelay preserved: NW-TT link delay from PCAP 50 000 ps every exchange; NW-TT Pdelay-engine log byte-identical to M2S4",
        "P2": "slave pdelay 50 000 ps every sample; no Pdelay frame in the 5GS",
    }
    for k in ROWS:
        lst = agg[k]
        bad_ = [(n_, d) for n_, (ok, d) in lst if not ok]
        add(k, desc[k] + " [M2S5 seeds 0-9, frag, load, load-harq16]", not bad_,
            ("; ".join(f"{n_}: {d}" for n_, d in bad_) or f"all {len(lst)} runs; e.g. {lst[0][0]}: {lst[0][1][1]}")[:1400])
    add("G1", "M2-S4 is the timing baseline: every frame at 8 points (GM, NW-TT eth[1]/eth[0], UE eth[0], UPF dnEth, DS-TT "
        "eth[0]/eth[1], slave) present with the same bytes (except Follow_Up correctionField/FCS downstream of the NW-TT) and "
        "the same time, except frames explained by the slave's clock-driven Pdelay timing (F11), each listed",
        all(ok for n_, ok, d in g1rows), "; ".join(f"{n_}: {d}" for n_, ok, d in g1rows if not ok)[:1400]
        or f"all {len(g1rows)} runs; e.g. {g1rows[0][0]}: {g1rows[0][2]}"[:1400])
    # S4 initial offset, S5 report
    R = Run(RUNS, "M2S5-offset", 0)
    off = pcapng.simtime_ps("0.001234567891")
    res = rows_5gs(R, None, exp_missing=0, offset=off)
    m = res["_model"]
    pre = [v - O.dbl(t) for t, v in clock_samples(R.V) if m.clk.steps and t < m.clk.steps[0][0]]
    add("S4", "initial slave offset 1.234567891 ms: error = the offset until step 1, 0 ps from step 1 on (replay exact)",
        res["S1"][0] and res["S2"][0] and pre and all(abs(e - O.dbl(off)) < 1e-15 for e in pre),
        f"{len(pre)} samples before step 1 at +{off} ps; {res['S2'][1]}")
    m4 = Run(RUNS4, "M2S4", 0)
    m4m = model_run(m4.prepare())
    add("S5", "report: slave error before (M2-S4) and after (M2-S5) the correction, seed 0", True,
        f"M2-S4: after step 1 {fmt(m4m.out['fu'][0]['new'] - m4m.out['fu'][0]['t'])}, max |error| after step 1 "
        f"{fmt(max(abs(x['new'] - x['t']) for x in m4m.out['fu']))}; M2-S5: 0 ps at every step and sample (S2)")

    # ---- fault cases (5GS)
    N = len(sel(keep[("M2S5", 0)][0].sl, 1, FU))
    FAULTS = {
        # name: (nw counters, ds counters, missing steps, description)
        "M2S5-FS1": ({}, {}, 1, "GM Sync 3 dropped: the INET GM sends no Follow_Up 3 either"),
        "M2S5-FS2": ({"syncWithoutFU": 1}, {}, 1, "GM Follow_Up 3 dropped"),
        "M2S5-FS3": ({"duplicateSync": 1, "ambiguousSync": 1, "duplicateFU": 1, "invalid": 2}, {"fuInvalidUpstream": 2}, 1,
                     "GM Sync 3 duplicated (the GM sends a Follow_Up per transmitted Sync: two Follow_Ups 3)"),
        "M2S5-FS4": ({"duplicateFU": 1, "invalid": 1}, {"fuInvalidUpstream": 1}, 0, "GM Follow_Up 3 duplicated"),
        "M2S5-FS5": ({"orphanFU": 1, "invalid": 1}, {"fuInvalidUpstream": 1}, 0, "a Follow_Up 3 ahead of Sync 3 (reordering)"),
        "M2S5-FS6": ({"syncWithoutFU": 1, "fuMismatch": 1, "invalid": 1}, {"fuInvalidUpstream": 1}, 1, "GM Follow_Up 3 after Sync 4"),
        "M2S5-FS7": ({}, {}, 0, "GM Follow_Up 3 delayed 50 ms"),
        "M2S5-FS8": ({"fuMismatch": 1, "syncWithoutFU": 1, "invalid": 1}, {"fuInvalidUpstream": 1}, 1, "GM Follow_Up 3 with sequenceId 1003"),
        "M2S5-FS9a": ({"malformedFU": 1, "syncWithoutFU": 1}, {}, 1, "GM Follow_Up 3 versionPTP 1 (class M: discarded at the NW-TT)"),
        "M2S5-FS9b": ({"malformedFU": 1, "syncWithoutFU": 1}, {}, 1, "GM Follow_Up 3 messageLength 70 (class M)"),
        "M2S5-FS9c": ({"unsupportedRepresentation": 1, "syncWithoutFU": 1}, {}, 1, "Follow_Up 3 as raw bytes at the NW-TT (class M)"),
        "M2S5-FS9d": ({"unsupportedRepresentation": 1, "syncWithoutFU": 1}, {}, 1, "Follow_Up 3 truncated at the NW-TT (class M)"),
        "M2S5-FS10": ({"otherDomain": 1}, {"otherDomain": 1}, 1, "GM Sync 3 rewritten to domain 1: passed unchanged and ignored by the domain-0 slave (the INET GM sends no Follow_Up for it: it ignores its own transmitted frame of another domain)"),
        "M2S5-FD1": ({}, {"fuNoSync": 1}, 1, "Sync 3 lost in the 5GS"),
        "M2S5-FD2": ({}, {}, 1, "Follow_Up 3 lost in the 5GS"),
        "M2S5-FD3": ({}, {"ambiguousSync": 1}, 1, "Sync 3 duplicated in the 5GS"),
        "M2S5-FD4": ({}, {"duplicateFU": 1}, 0, "Follow_Up 3 duplicated in the 5GS"),
        "M2S5-FD5": ({}, {"fuNoSync": 1}, 1, "Follow_Up 3 before Sync 3 at the DS-TT"),
        "M2S5-FD6": ({}, {"staleFU": 1}, 1, "Follow_Up 3 after Sync 4 at the DS-TT"),
        "M2S5-FD7": ({}, {"fuNoTag": 1}, 1, "TtSyncIngressTag removed from Follow_Up 3"),
        "M2S5-FD8": ({}, {"tagMismatch": 1}, 1, "tag sequenceId of Follow_Up 3 altered"),
        "M2S5-FD9": ({}, {"associationMismatch": 1}, 1, "tag Sync frame id of Follow_Up 3 altered"),
        "M2S5-FD10": ({}, {}, 0, "Follow_Up 3 delayed 50 ms in the 5GS"),
        "M2S5-lupLate": ({"noLinkDelay": 2, "invalid": 2}, {"fuInvalidUpstream": 2}, 2, "FL1: NW-TT link delay only from 0.3 s"),
        "M2S5-pdelayLoss": (None, None, None, "FL2: GM Pdelay_Resp 2-6 dropped"),
    }
    NWC = ("syncWithoutFU", "duplicateSync", "ambiguousSync", "fuMismatch", "noLinkDelay", "duplicateFU", "orphanFU", "malformedFU",
           "unsupportedRepresentation", "malformedSync", "otherDomain", "invalid")
    DSC = ("fuNoTag", "fuInvalidUpstream", "tagMismatch", "holds", "ambiguousSync", "duplicateFU", "associationMismatch", "staleFU",
           "fuNoSync", "fuHoldExpired", "malformedFU", "unsupportedRepresentation", "otherDomain")
    s6 = []
    for cfg, (enw, eds, miss, txt) in FAULTS.items():
        R = Run(RUNS, cfg, 0)
        R.prepare()
        got_nw = {k: R.nwsc(k) for k in NWC if R.nwsc(k)}
        got_ds = {k: R.dssc(k) for k in DSC if R.dssc(k)}
        extra = ""
        if enw is None:     # FL2: expected counts from the engine's measuring vector and the Follow_Up times
            mv = vector(R.sca_path.replace(".sca", ".vec"), f"M1Bridge.nwTt.eth[1].trafficConditionerLayer.engine", "measuring")
            def measuring_at(t):
                v = 0
                for tt, x in mv:
                    if tt < t:
                        v = int(x)
                return v
            nfu = [f for f in sel(R.nw1, 1, FU)]
            k = sum(1 for f in nfu if not measuring_at(f["end"]) or R.lup_at(f["end"]) is None)
            enw = {"noLinkDelay": k, "invalid": k}
            eds = {"fuInvalidUpstream": k}
            miss = k
            extra = f"; measuring vector {mv}; Follow_Ups while not measuring {k}"
        m = model_run(R)
        okc1, counts, mm = compare_recorded(m, R.V)
        steps = len(m.out["fu"])
        nonzero = [(x["seq"], x["diff"]) for x in m.out["fu"] if x["diff"] != 0]
        audit = R.s(f"{R.sln}.eth[0].trafficConditionerLayer.audit", "framesWithSyncTag", -1)
        # S6: error throughout every affected interval (between the steps around each missing Sync)
        st_t = [x["t"] for x in m.out["fu"]]
        stepped = {x["seq"] for x in m.out["fu"]}
        miss_seqs = sorted(s for s in R.gm_sync if s not in stepped)
        samples = clock_samples(R.V)
        intervals = []
        for s in miss_seqs:
            tg = R.gm_sync[s][0]["start"]
            a = max([t for t in st_t if t < tg], default=0)
            b = min([t for t in st_t if t > tg], default=None)
            inside = [(t, v - O.dbl(t)) for t, v in samples if a < t and (b is None or t < b)]
            arrivals = [f["start"] for f in sel(R.sl, 1, SYNC) if a < f["start"] and (b is None or f["start"] < b)]
            intervals.append((s, (b - a) if b else None, len(inside), max((abs(e) for t, e in inside), default=0.0), len(arrivals)))
        comp_nonzero = [v for t, v in R.V["comp"] if float(v) != 0.0]
        s6.append((cfg, intervals, comp_nonzero))
        ok = got_nw == enw and got_ds == eds and okc1 and not nonzero and steps == N - miss and audit == 0 \
            and all(i[3] == 0.0 for i in intervals) and not comp_nonzero
        add(f"F-{cfg[5:]}", f"{txt}: NW-TT {enw or 0}, DS-TT {eds or 0}, {N - miss} slave steps, every step exact, replay exact, "
            f"no tag at the slave", ok,
            f"NW {got_nw or 0}; DS {got_ds or 0}; steps {steps}; replay {okc1} {dict(mm) or ''}; non-zero corrections {nonzero[:2] or 0}; "
            f"audit {int(audit)}{extra}")
    # S6/S7 report (refinement R-3)
    det = []
    for cfg, iv, comp in s6:
        for s, dur, nsamp, mx, narr in iv:
            det.append(f"{cfg[5:]} Sync {s}: {fmt(dur) if dur else 'to end'} without a step, {nsamp} clock samples and {narr} Sync "
                       f"arrivals inside, max |error| {mx * 1e12:.0f} ps")
    add("S6", "synchronization under faults: slave error throughout every interval affected by a lost or discarded Sync/Follow_Up "
        "(every 1 ms sample and Sync arrival between the surrounding steps), compensation 0", all(all(i[3] == 0.0 for i in iv) and not c for _, iv, c in s6),
        f"{len(det)} affected intervals: " + "; ".join(det)[:1500])
    add("S7", "claim separation: the S6 result (0 ps between steps) holds only because both clocks are ideal (IdealOscillator, "
        "compensation 0, gmRateRatio 1); it says nothing about holdover with drifting clocks (not modelled, not claimed)", True, "")

    # ---- negative controls (5GS): each must fail exactly the declared rows (relative to its base
    # run), with the exact signature: the correctionField each delivered Follow_Up must carry,
    # computed from PCAP with the mistake applied (and the resulting slave error, from the model)
    R40 = Run(RUNS4, "M2S4", 0)
    X64 = (64 + 8) * 8 * NS          # 64-B Sync at 1 Gb/s
    e1 = M._llround(-(1.0001 - 1.0) * float(M.Q63))
    rr_out = 1.0 - float(e1) / float(1 << 63)
    e2 = M._llround(-(rr_out - 1.0) * float(M.Q63))

    def port_slot(R):
        """enqueue (slot) time of every Sync at DS-TT eth[1], from the M2-S1 port log, by tx start"""
        rows_ = read_csv(os.path.join(R.ldir, f"M1Bridge.{R.dsn}.eth[1].measurementLayer.egress.port.csv"))
        return {pcapng.simtime_ps(r["tTxStart"]): pcapng.simtime_ps(r["tSlot"]) for r in rows_ if r["event"] == "tx"}
    NC = {
        # name: (expected failed rows, base run, cf(R, seq, Lup, Res, prev Res) or None, description)
        "M2S5-nc-noLup": ({"C1", "C2", "C3", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: r, "cf = Res (Lup omitted): error -50 000 ps"),
        "M2S5-nc-lupTwice": ({"C1", "C2", "C3", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: 2 * l + r, "cf = 2 Lup + Res: error +50 000 ps"),
        "M2S5-nc-tseEnd": ({"C2", "C3", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: l + r + X64, "cf = Lup + Res + X (576 000 ps)"),
        "M2S5-nc-tsiEnd": ({"C2", "C3", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: l + r - X64, "cf = Lup + Res - X"),
        "M2S5-nc-bothEnd": ({"C3"}, "M2S5", lambda R, s, l, r, p: l + r, "cf unchanged (X cancels at equal rates); only the logged TSi/TSe differ from the PCAP first bits"),
        "M2S5-nc-prevSync": ({"C2", "C3", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: l + (p if p is not None else r), "cf = Lup + Res of the previous Sync"),
        "M2S5-nc-tseSlot": ({"C2", "C3", "S2", "S3"}, "M2S5", "slot", "cf = Lup + (Sync slot time - TSi)"),
        "M2S5-nc-noFcsDs": ({"C2", "C6", "C7", "S2"}, "M2S5", "noFcsDs", "DS-TT FCS stale: the slave's FCS checker drops every Follow_Up (S3 cannot see it: the ideal slave clock, never stepped, stays exact)"),
        "M2S5-nc-noFcsNw": ({"C1", "C2", "C6", "C7", "C8", "S2", "S3"}, "M2S5", "noFcsNw", "NW-TT FCS stale: the NW-TT node's FCS checker drops every Follow_Up"),
        "M2S5-nc-rr": ({"C1", "C2", "C3", "C5", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: M.mul_round(l, e1) + M.mul_round(r, e2), "cf = rr (x) Lup + rr_out (x) Res, rr = 1.0001"),
        "M2S5-nc-forwardInvalid": ({"C2", "C7", "S2", "S3"}, "M2S5-lupLate", lambda R, s, l, r, p: 0 if s in (0, 1) else l + r, "INVALID Follow_Ups 0 and 1 delivered with cf 0"),
        "M2S5-nc-syncCf": ({"C4"}, "M2S5", lambda R, s, l, r, p: l + r, "Follow_Ups correct; Sync cf = Lup: only the wire check C4 sees it, slave error 0"),
        "M2S5-nc-noStrip": ({"C8"}, "M2S5", lambda R, s, l, r, p: l + r, "Follow_Ups correct; the tag reaches the slave on every Follow_Up"),
        "M2S5-nc-fwdPdelay": ({"C1", "C2", "C3", "C8", "P1", "P2", "S2", "S3"}, "M2S5", lambda R, s, l, r, p: L_REF + r, "Pdelay forwarded end to end + reference 50 ns: cf = 50 ns + Res, the slave adds its end-to-end pdelay"),
    }
    base_failed = {}
    for base in ("M2S5", "M2S5-lupLate"):
        Rb = Run(RUNS, base, 0)
        rb = rows_5gs(Rb, R40, exp_missing=2 if base == "M2S5-lupLate" else 0)
        base_failed[base] = {k for k in ROWS if k in rb and not rb[k][0]}
    for cfg, (expect, base, cff, txt) in NC.items():
        R = Run(RUNS, cfg, 0)
        try:
            res = rows_5gs(R, R40, exp_missing=2 if base == "M2S5-lupLate" else 0)
        except Exception as x:   # noqa: BLE001 -- reported as a failed control
            add(f"N-{cfg[8:]}", txt, False, f"checker exception {type(x).__name__}: {x}")
            continue
        failed = {k for k in ROWS if k in res and not res[k][0]} - base_failed[base]
        m = res["_model"]
        d = [x["new"] - x["t"] for x in m.out["fu"]]
        R.prepare()
        sig_detail, sig = "", False
        if cff == "noFcsDs":
            drops = fcs_drops(R).get(f"{R.sln}.eth[0].macLayer.fcsChecker", 0)
            sig = len(m.out["fu"]) == 0 and drops == len(sel(R.ds1, 2, FU)) > 0
            sig_detail = f"slave FCS-checker drops {drops} = Follow_Ups sent {len(sel(R.ds1, 2, FU))}; slave steps {len(m.out['fu'])}"
        elif cff == "noFcsNw":
            drops = fcs_drops(R).get(f"{R.nwn}.ethernet.fcsChecker", 0)
            sig = len(m.out["fu"]) == 0 and len(sel(R.nw0, 2, FU)) == 0 and drops == len(sel(R.nw1, 1, FU)) > 0
            sig_detail = f"NW-TT node FCS-checker drops {drops} = Follow_Ups received; Follow_Ups in the 5GS {len(sel(R.nw0, 2, FU))}"
        else:
            slot = port_slot(R) if cff == "slot" else None
            n_ok, n_all, bad, prev = 0, 0, [], None
            for f in sel(R.sl, 1, FU):
                s = f["seq"]
                ns_, ds_ = R.nw_sync.get(s), R.ds_sync.get(s)
                if not (ns_ and ds_):
                    continue
                rk = ds_[-1]["start"] - ns_[0]["start"]
                l = R.lup_at(R.nw_fu[s][0]["end"]) if R.lup_table_cache else None
                if cff == "slot":
                    want = l + (slot[ds_[-1]["start"]] - ns_[0]["start"])
                else:
                    want = cff(R, s, l, rk, prev)
                prev = rk
                n_all += 1
                if f["g"]["cf_raw"] == enc(want):
                    n_ok += 1
                else:
                    bad.append((s, f["g"]["cf_raw"], enc(want)))
            sig = n_all > 0 and n_ok == n_all
            sig_detail = f"{n_ok}/{n_all} delivered Follow_Ups carry exactly the predicted cf {bad[:2] or ''}"
            if cfg == "M2S5-nc-syncCf":
                sync_cf = {f["g"]["cf_raw"] for f in sel(R.sl, 1, SYNC)}
                sig &= sync_cf == {enc(L_REF)} and not any(d)
                sig_detail += f"; Sync cf on the wire {sync_cf} (= enc(50 ns)); slave error {set(d)}"
            elif cfg == "M2S5-nc-noStrip":
                a = R.s(f"{R.sln}.eth[0].trafficConditionerLayer.audit", "framesWithSyncTag", -1)
                sig &= a == len(sel(R.sl, 1, FU)) and not any(d)
                sig_detail += f"; frames with a tag at the slave {int(a)}; slave error {set(d)}"
            elif cfg == "M2S5-nc-bothEnd":
                sig &= not any(d)
            elif cfg == "M2S5-nc-fwdPdelay":
                pd0 = m.out["fu"][0]["pd"]
                sreq, sresp = by_seq(sel(R.sl, 2, REQ, dom=None)), by_seq(sel(R.sl, 1, RESP, dom=None))
                greq, gresp = by_seq(sel(R.gm, 1, REQ, dom=None)), by_seq(sel(R.gm, 2, RESP, dom=None))
                raw0 = C4.link_delay(sreq[0][0]["start"], greq[0][0]["start"], gresp[0][0]["start"], sresp[0][0]["start"])[0]
                sig &= pd0 == raw0 and d[0] == raw0 - L_REF
                sig_detail += f"; slave pdelay at step 1 {fmt(pd0)} = raw end-to-end exchange 0 from PCAP; error after step 1 {fmt(d[0])} = pdelay - 50 ns"
        ok = failed == expect and sig
        add(f"N-{cfg[8:]}", f"{txt}: fails exactly {sorted(expect)} (beyond its base run {base})", ok,
            f"failed {sorted(failed)}; signature {'OK' if sig else 'WRONG'}: {sig_detail}; slave error after each step "
            f"{Counter(d).most_common(3)}"[:700])

    # ---- unit topology
    unit_rows(add)

    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {check} {detail}")
        if extra:
            print(f"      {extra}")
    print(f"\nOVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    return 0 if npass == len(rows) else 1


# ---------------------------------------------------------------------------------------
# unit topology: holds, rates, sub-ns
def replay_fifo(U):
    """Independent FIFO replay of the DS-TT eth[1] TX port (100 Mb/s) from PCAP arrivals:
    frames from the 5GS side arrive at their last bit at ttD eth[0] (inbound); the engine's
    Pdelay_Resp at the last bit of the slave's Pdelay_Req (ttD eth[1] inbound); its
    Resp_Follow_Up at the last bit of the Resp (ttD eth[1] outbound). Work-conserving single
    FIFO: start = max(arrival, previous last bit + 96 bit times)."""
    bit = 10 * NS
    out = [f for f in U.ds1 if f["dir"] == 2]
    arr = []
    for f in U.ds0:
        if f["dir"] == 1:
            arr.append((f["end"], 0, f))
    for f in U.ds1:
        if f["dir"] == 1 and f["type"] == REQ:
            arr.append((f["end"], 1, f))
    # identity: background by order; gPTP by (type, seq); Resp_FU arrival from the observed Resp
    resp_end = {f["seq"]: f["end"] for f in out if f["type"] == RESP}
    for s, e in resp_end.items():
        arr.append((e, 2, {"type": RFU, "seq": s}))
    arr.sort(key=lambda a: (a[0], a[1]))
    ident = lambda f, src: ("REQ->RESP", f["seq"]) if src == 1 else (("RFU", f["seq"]) if src == 2 else (f["type"], f["seq"] if f["type"] in (SYNC, FU) else None))  # noqa: E731
    obs = [((f["type"], f["seq"] if f["type"] in (SYNC, FU) else None) if f["type"] not in (RESP, RFU) else
            (("REQ->RESP" if f["type"] == RESP else "RFU"), f["seq"]), f) for f in out]
    return arr, obs, ident, bit


def fifo_check(U, dropped_keys=()):
    arr, obs, ident, bit = replay_fifo(U)
    want = [(ident(f, src), t) for t, src, f in arr if ident(f, src) not in dropped_keys]
    got = [(k, f) for k, f in obs]
    # order; frames still queued or in transmission at the end of the run are at the tail of the
    # replay and not in the PCAP
    tail = want[len(got):]
    last = got[-1][1]["start"] if got else 0
    order_ok = [k for k, t in want[:len(got)]] == [k for k, f in got] and all(t >= last for k, t in tail)
    devs = []
    prev_end = None
    n = 0
    for (k, t), (k2, f) in zip(want, got):
        start = t if prev_end is None else max(t, prev_end + 96 * bit)
        if k != k2:
            break
        n += 1
        if f["start"] != start:
            devs.append((k, f["start"] - start))
        prev_end = f["end"]
    return order_ok, n, devs, len(want) - len(tail), len(got)


def unit_rows(add):
    # H0: replay validity where no hold is possible
    U = Run(RUNS, "M2S5U-base", 0, unit=True)
    o, n, devs, nw, ng = fifo_check(U)
    add("H0", "FIFO-replay validity (unit base, no correction, no hold): replay from PCAP arrivals = observed DS-TT eth[1] order "
        "and first bits for every frame", o and not devs and n == ng == nw, f"{n} frames; order {o}; deviations {devs[:3] or 0}")
    held_counts = {}
    for cfg in ("M2S5U-hold", "M2S5U-subns", "M2S5U-nc-bothEnd", "M2S5U-expiry", "M2S5U-syncloss", "M2S5U-nc-noHold"):
        U = Run(RUNS, cfg, 0, unit=True)
        U.prepare()
        held = Counter(r["msgType"] for r in U.dslog if r["event"] == "held")
        holds = U.dssc("holds")
        held_counts[cfg] = (holds, dict(held))
        # discarded Follow_Ups never leave: remove them from the replay's expected sequence
        dropped = {(FU, int(r["seq"])) for r in U.dslog if r["event"] in ("fuHoldExpired", "fuNoSync", "staleFU")}
        dropped |= {(SYNC, int(r["seq"])) for r in U.dslog if r["event"] == "syncDroppedTest"}
        o, n, devs, nw, ng = fifo_check(U, dropped)
        m = model_run(U)
        okc1, counts, mm = compare_recorded(m, U.V)
        d = [x["new"] - x["t"] for x in m.out["fu"]]
        # unit C2: cf at ttD eth[1] and slave = enc(Lup + Res)
        probs = []
        for name, fr in (("ttD eth[1]", sel(U.ds1, 2, FU)), ("slave", sel(U.sl, 1, FU))):
            for f in fr:
                s = f["seq"]
                l = U.lup_at(U.nw_fu[s][0]["end"])
                rk = U.ds_sync[s][-1]["start"] - U.nw_sync[s][0]["start"]
                if f["g"]["cf_raw"] != enc(l + rk):
                    probs.append((name, s, f["g"]["cf_raw"], enc(l + rk)))
        audit = U.s("slave.eth[0].trafficConditionerLayer.audit", "framesWithSyncTag", -1)
        if cfg == "M2S5U-hold":
            ok = holds > 0 and held.get("3", 0) > 0 and held.get("-1", 0) > 0 and o and not devs and okc1 and not any(d) and not probs \
                and len(d) == len(sel(U.gm, 2, SYNC)) and audit == 0
            add("H1", "unit hold run: Follow_Ups held while their Sync is queued (count > 0) and corrected exactly (cf on the wire, "
                "slave replay, 0 ps)", holds > 0 and okc1 and not any(d) and not probs,
                f"holds {holds}; steps {len(d)}, all 0 ps: {not any(d)}; replay {okc1}; cf problems {probs[:2] or 0}")
            add("H2", "timing neutrality of the hold (independent FIFO replay from PCAP): observed DS-TT eth[1] order = arrival order "
                "(exact FIFO) and every first bit = replay, incl. held Follow_Ups, background frames and Pdelay frames", o and not devs and n == ng,
                f"{n} frames; held frames {dict(held)} (type -1: background, 3: Pdelay_Resp); deviations {devs[:3] or 0}")
            add("H2b", "Pdelay interleaving: DS-TT Pdelay_Resps injected during holds, transmitted in FIFO order; the slave's link "
                "delay stays exact", held.get("3", 0) > 0 and o and not devs and all(float(v) == O.dbl(L_REF) for t, v in U.V["pdelay"]),
                f"Pdelay_Resps held {held.get('3', 0)}; slave pdelay {sorted({float(v) for t, v in U.V['pdelay']})}")
        elif cfg == "M2S5U-subns":
            wire = [f["g"]["cf_raw"] for f in sel(U.sl, 1, FU)]
            logged = cf_map(U)
            trunc = all(enc(logged[f["seq"]]) == f["g"]["cf_raw"] for f in sel(U.sl, 1, FU))
            subns = sum(1 for v in logged.values() if v % NS)
            # wire-mode slave (reads the serialized ns): predicted deviation
            mw = model_run(U, cf={s: M.inet_read_clock8(enc(v)) for s, v in logged.items()})
            dw = [x["new"] - x["t"] for x in mw.out["fu"]]
            add("W1", "sub-ns correction values (unit, non-integer-ns links): the slave uses the ps value (replay exact, 0 ps); the "
                "wire carries trunc_ns(cf) << 16; a byte-reading slave would deviate by exactly the truncated residue",
                okc1 and not any(d) and trunc and subns > 0 and not probs and o and not devs,
                f"{subns} of {len(logged)} cf values with a sub-ns part; wire = trunc_ns: {trunc}; sim error 0: {not any(d)}; "
                f"wire-mode slave step corrections {sorted(set(dw))[:4]} ps; holds {holds}, FIFO exact {o and not devs}")
        elif cfg == "M2S5U-expiry":
            exp_ = U.dssc("fuHoldExpired")
            delivered = {f["seq"] for f in sel(U.sl, 1, FU)}
            expired = {int(r["seq"]) for r in U.dslog if r["event"] == "fuHoldExpired"}
            add("H3", "hold expiry (holdTimeout 5 us < queue waits): every held Follow_Up discarded, none reaches the slave; held "
                "frames released in order at expiry; each release deviation from the replay reported (not neutral by design)",
                exp_ == holds > 0 and not (delivered & expired) and o and okc1,
                f"holds {holds}, expired {exp_}; order kept {o}; frames held {sum(held.values())}; start deviations from the "
                f"replay {len(devs)} ({sorted({x for k, x in devs})[:4]} ps): the 5 us expiry released every held frame before "
                f"its FIFO turn, so no transmission time changed in this run")
        elif cfg == "M2S5U-syncloss":
            delivered = {f["seq"] for f in sel(U.sl, 1, FU)}
            add("H4", "Sync loss below the hold point (Sync 5, TEST ONLY): Follow_Up 5 held, discarded at hold expiry (10 ms), not "
                "delivered; release deviations reported", U.dssc("fuHoldExpired") == 1 and 5 not in delivered and o and okc1 and not any(d),
                f"fuHoldExpired {U.dssc('fuHoldExpired')}; FU 5 delivered {5 in delivered}; {sum(held.values())} frames held for "
                f"10 ms; the released burst starts {max((x for k, x in devs), default=0) / 1e6:.3f} us after the replay's "
                f"start ({len(devs)} burst start(s); the burst then follows back to back, FIFO order kept {o}); every other step "
                f"exact {not any(d)}; NOT timing-neutral (reported, by design)")
        elif cfg == "M2S5U-nc-noHold":
            base_holds = held_counts["M2S5U-hold"][0]
            add("N-noHold", "N13 (unit): a Follow_Up whose Sync is still queued discarded instead of held: signature: no hold, "
                "fuNoSync = the hold count of M2S5U-hold, slave steps = N - that count (H1 and the delivery rule C7 would fail)", holds == 0 and U.dssc("fuNoSync") == base_holds and len(d) == len(sel(U.gm, 2, SYNC)) - base_holds,
                f"fuNoSync {U.dssc('fuNoSync')} = M2S5U-hold holds {base_holds}; steps {len(d)}")
        elif cfg == "M2S5U-nc-bothEnd":
            xin, xout = (64 + 8) * 8 * NS, (64 + 8) * 8 * 10 * NS
            add("N-bothEnd-unit", "N4b (unit, 1 Gb/s in, 100 Mb/s out): TSi and TSe at the last bit: error = X_out - X_in at every "
                "step (does not cancel at different rates); the wire cf differs from enc(Lup + Res) (C2) and the error is non-zero (S2)", bool(d) and all(x == xout - xin for x in d) and probs,
                f"step corrections {sorted(set(d))} ps (X_out - X_in = {xout - xin})")
    add("H5", "scope: the neutrality result (H2) holds for one unlimited FIFO without shaping or preemption; no other queue model "
        "was tested", True, f"holds per run {held_counts}")


if __name__ == "__main__":
    sys.exit(main())
