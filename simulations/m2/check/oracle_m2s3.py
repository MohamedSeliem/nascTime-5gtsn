#!/usr/bin/env python3
"""M2-S3 offline correction oracle (migration/m2-s2-design.md, revision 2, section 6).

Usage: oracle_m2s3.py <results/M2-S1/runs> <results/M2-S1/raw-outputs.sha256> <probe output> <out dir>

Reads the recorded M2-S1 runs (PCAP at the gPTP grandmaster `listener` eth[0], NW-TT eth[1],
DS-TT eth[1] and the slave `talker` eth[0]; the M2-S1 per-frame port logs; the slave's
recorded vectors). Modifies no packet and runs no simulation. Four separate parts:
  A  inputs, provenance, decoding of the recorded gPTP bytes, serialization rules
  B  timing identity D = Lup + Res + Ldn -- consistency of the measured intervals ONLY,
     not evidence that gPTP correction works
  C  an independent re-implementation of the INET 4.7.0 slave (inet_model.py), validated
     against the slave's recorded behaviour (sim and wire input modes)
  D  corrected-behaviour prediction with that model (ideal clocks, reference link delays,
     rr = 1), plus E negative controls with exact signatures
Integer picoseconds, exact comparisons, no tolerance.

Assumptions (explicit): GM, slave and TT clocks ideal (IdealOscillator; TTs on simulation
time), so GM time = 5G time = simulation time; rr = 1 is the ideal-clock baseline and does
not validate non-unit rate ratios; Lup = Ldn = 50 ns are reference values (cable
propagation), not the output of a Pdelay implementation.
"""
import csv
import hashlib
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcapng  # noqa: E402
import inet_model as M  # noqa: E402

RUNS, HASHES, PROBE, OUT = sys.argv[1:5]
NS = 1000
GPTP = 0x88F7
L_REF = 50 * NS                       # Lup_ref = Ldn_ref (reference values)
SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10
TNAME = {SYNC: "Sync", FU: "Follow_Up", REQ: "Pdelay_Req", RESP: "Pdelay_Resp", RFU: "Pdelay_Resp_Follow_Up"}
PRIMARY = [("M2S1", r) for r in range(10)] + [("M2S1-frag", 0), ("M2S1-load", 0), ("M2S1-load-harq16", 0)]
CONTROLS = [("M2S1-off", 0), ("M2S1-load-off", 0)]   # no TtTimestampLayer: rows A, C only
INJECTED_OFFSET = 1234567891          # ps; offline only (D2b), not a simulated scenario
NC_RR_PPM = 100.0                     # NC-e: rate ratio 1 + 1e-4

rows = []


def add(check, detail, ok, extra=""):
    rows.append((check, detail, bool(ok), extra))


def ps(s):
    return pcapng.simtime_ps(s) if s not in ("", None) else None


def be(b):
    return int.from_bytes(b, "big")


def sbe(b):
    return int.from_bytes(b, "big", signed=True)


def fmt(p):
    return f"{p / NS:.3f} ns"


def rng(vals):
    vals = list(vals)
    return f"{fmt(min(vals))} .. {fmt(max(vals))}" if vals else "n/a"


# ---------------------------------------------------------------------------------------
# A2 decoding (layout of INET 4.7.0 GptpPacketSerializer.cc writeGptpBase :102-117 and the
# per-message serializers; 1588/802.1AS field semantics not verified from the standards)
def decode(b):
    if len(b) < 34:
        raise ValueError("gPTP header shorter than 34 B")
    d = {"majorSdoId": b[0] >> 4, "type": b[0] & 15, "minorVersionPTP": b[1] >> 4, "versionPTP": b[1] & 15,
         "messageLength": be(b[2:4]), "domain": b[4], "minorSdoId": b[5], "flags": be(b[6:8]),
         "cf_raw": sbe(b[8:16]), "mts": be(b[16:20]), "spi": (be(b[20:28]), be(b[28:30])), "seq": be(b[30:32]),
         "control": b[32], "logInterval": sbe(b[33:34])}
    need = {SYNC: 44, FU: 76, REQ: 54, RESP: 54, RFU: 54}.get(d["type"])
    if need is None or len(b) < need:
        raise ValueError(f"type {d['type']}: {len(b)} B")

    def ts(o):
        return be(b[o:o + 6]), be(b[o + 6:o + 10])
    if d["type"] == FU:
        d["pot"] = ts(34)
        d["tlv"] = (be(b[44:46]), be(b[46:48]), be(b[48:51]), be(b[51:54]))
        d["csro"] = sbe(b[54:58])
        d["tlv_rest"] = b[58:76].hex()
    elif d["type"] in (RESP, RFU):
        d["ts"] = ts(34)
        d["reqPort"] = (be(b[44:52]), be(b[52:54]))
    return d


class Run:
    def __init__(self, cfg, rep):
        self.cfg, self.rep = cfg, rep
        self.base = os.path.join(RUNS, cfg)
        self.pdir = os.path.join(self.base, "pcap", f"{cfg}-{rep}")
        self.ldir = os.path.join(self.base, "m2log", f"{cfg}-{rep}")
        self.vec = os.path.join(self.base, cfg, f"{rep}.vec")
        self.files = []

    def pcap_path(self, node, idx):
        return os.path.join(self.pdir, f"M1Bridge.{node}.pcapRecorder[{idx}].pcapng")

    def gptp(self, node, idx, direction):
        path = self.pcap_path(node, idx)
        if path not in self.files:
            self.files.append(path)
        out = []
        for p in pcapng.read(path):
            if p["dir"] != direction:
                continue
            f = pcapng.ethernet(p["data"])
            if f["etherType"] != GPTP:
                continue
            L = len(p["data"])
            out.append({"end": p["t_ps"], "start": p["t_ps"] - (L + 8) * 8 * NS, "L": L, "payload": f["payload"],
                        "key": (GPTP, f["pcp"], f["vid"], pcapng.fnv1a64(f["payload"])), "g": decode(f["payload"]),
                        "fcs_ok": f["fcs_ok"]})
        return out

    def log(self, node, port, role, port_log):
        path = os.path.join(self.ldir, f"M1Bridge.{node}.eth[{port}].measurementLayer.{role}{'.port' if port_log else ''}.csv")
        self.files.append(path)
        with open(path) as fh:
            return [r for r in csv.DictReader(fh) if r["event"] != "selftest"]


def wire_ts(t):
    return M.inet_read_timestamp(*t)


def floor_ns(p):
    return (p // NS) * NS


# ---------------------------------------------------------------------------------------
def load(run, with_logs):
    R = run
    R.gm_out, R.gm_in = R.gptp("listener", 0, 2), R.gptp("listener", 0, 1)
    R.nw_in, R.nw_out = R.gptp("nwTt", 1, 1), R.gptp("nwTt", 1, 2)
    R.ds_out, R.ds_in = R.gptp("dsTt", 1, 2), R.gptp("dsTt", 1, 1)
    R.sl_in, R.sl_out = R.gptp("talker", 0, 1), R.gptp("talker", 0, 2)
    if with_logs:
        key = lambda r, h: (int(r["etherType"]), int(r["pcp"]), int(r["vid"]), r[h])  # noqa: E731
        R.l_ing = {key(r, "payloadHash"): r for r in R.log("nwTt", 1, "ingress", False) if r["event"] == "tag"}
        R.l_tx1 = {key(r, "hash"): r for r in R.log("dsTt", 1, "egress", True) if r["event"] == "tx"}
        R.l_tx0 = {key(r, "hash"): r for r in R.log("nwTt", 0, "egress", True) if r["event"] == "tx"}
        R.l_rx0 = {key(r, "hash"): r for r in R.log("dsTt", 0, "ingress", True) if r["event"] == "rx"}
    return R


def by_type_seq(frames, mtype):
    d = {}
    for f in frames:
        if f["g"]["type"] == mtype:
            k = f["g"]["seq"]
            if k in d:
                raise ValueError(f"duplicate {TNAME[mtype]} seq {k}")
            d[k] = f
    return d


# ---------------------------------------------------------------------------------------
# A1 provenance
def load_hashes():
    h = {}
    with open(HASHES) as fh:
        for line in fh:
            digest, name = line.rstrip("\n").split("  ", 1)
            h[os.path.normpath(os.path.join(RUNS, name))] = digest
    return h


def sha256(path):
    x = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            x.update(chunk)
    return x.hexdigest()


# ---------------------------------------------------------------------------------------
# recorded slave vectors (C1)
VEC_WANT = {("M1Bridge.talker.gptp", "pdelay:vector"): "pdelay", ("M1Bridge.talker.gptp", "gmRateRatio:vector"): "gm",
            ("M1Bridge.talker.gptp", "neighborRateRatio:vector"): "nrr",
            ("M1Bridge.talker.clock", "timeChanged:vector"): "clock",
            ("M1Bridge.talker.clock", "oscillatorCompensationChanged:vector"): "comp"}


def read_vec(path):
    ids, data = {}, {v: [] for v in VEC_WANT.values()}
    with open(path) as fh:
        for line in fh:
            c = line[:1]
            if c.isdigit():
                tab = line.find("\t")
                vid = line[:tab]
                if vid in ids:
                    p = line.rstrip("\n").split("\t")
                    data[ids[vid]].append((p[2], p[3]))
            elif line.startswith("vector "):
                p = line.split()
                k = (p[2], p[3])
                if k in VEC_WANT:
                    ids[p[1]] = VEC_WANT[k]
    return data


INVF = 1.0 / 1e12  # OMNeT++ SimTime::invfscale (simtime.cc:77-79)


def dbl(raw_ps):
    """SimTime::dbl() (simtime.h:346): raw * invfscale. Vector values of simtime signals are recorded as this
    double; the oracle compares the model's exact ps value converted the same way with the recorded double.
    For |raw| < 2^53 ps distinct ps values give distinct doubles, so double equality is ps equality here."""
    return raw_ps * INVF


# ---------------------------------------------------------------------------------------
def slave_events(R, mode, cf_fn=None):
    """Slave-side input events from the slave's own PCAP. mode 'wire': decoded wire fields only;
    mode 'sim': wire fields with the sub-ns residue restored from the GM's own event times
    (what the simulated slave saw: INET chunks are not serialized inside the simulation).
    cf_fn(followup frame) -> correctionField in ps replaces the recorded field (D, E)."""
    ev = []
    for f in R.sl_out:
        g = f["g"]
        if g["type"] == REQ:
            ev.append(("reqtx", f["end"], g["seq"], f["start"], g["spi"]))
    for f in R.sl_in:
        g = f["g"]
        if g["domain"] != 0:
            continue
        t, s = f["end"], g["seq"]
        if g["type"] == RESP:
            t2 = wire_ts(g["ts"]) if mode == "wire" else R.sim_t2[s]
            ev.append(("resprx", t, s, f["start"], t2, g["reqPort"]))
        elif g["type"] == RFU:
            t3 = wire_ts(g["ts"]) if mode == "wire" else R.sim_t3[s]
            ev.append(("rfurx", t, s, t3, g["reqPort"]))
        elif g["type"] == SYNC:
            ev.append(("syncrx", t, s, f["start"]))
        elif g["type"] == FU:
            pot = wire_ts(g["pot"]) if mode == "wire" else R.sim_pot[s]
            cf = M.inet_read_clock8(g["cf_raw"]) if cf_fn is None else cf_fn(f)
            ev.append(("furx", t, s, pot, cf))
    return ev


def model(R, mode="sim", cf_fn=None, pdelay_override=None, initial=0, pot_fn=None):
    ev = slave_events(R, mode, cf_fn)
    if pot_fn is not None:
        ev = [e if e[0] != "furx" else (e[0], e[1], e[2], pot_fn(e[2]), e[4]) for e in ev]
    return M.SlaveModel(initial_clock=initial, pdelay_override=pdelay_override).run(ev)


def replay_at(steps, initial, times):
    """Clock value at each time in `times` (sorted), applying the steps strictly before t."""
    c, i, out = M.Clock(initial), 0, []
    for t in times:
        while i < len(steps) and steps[i][0] < t:
            c.set(steps[i][0], steps[i][2], steps[i][3])
            i += 1
        out.append(c.at(t))
    return out


def compare_recorded(R, m, V):
    """C1: model outputs vs recorded vectors, exact. Returns (ok, detail, counts, mismatches)."""
    mm = Counter()
    rec_pd = [(ps(t), float(v)) for t, v in V["pdelay"]]
    rec_gm = [(ps(t), float(v)) for t, v in V["gm"]]
    rec_nrr = [(ps(t), float(v)) for t, v in V["nrr"]]
    rec_comp = [(ps(t), float(v)) for t, v in V["comp"]]
    steps = m.clk.steps
    mod_pd = [(t, dbl(v)) for t, v in m.out["pdelay"]]
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
    tc = [(ps(t), float(v)) for t, v in V["clock"]]
    step_at = {t: (o, n) for t, o, n, p in steps}
    c, i, seen, n_step_samples = M.Clock(), 0, Counter(), 0
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
        if v != dbl(exp):
            mm["clock sample"] += 1
    steps_sampled = sum(1 for t in step_at if seen[t] >= 1)
    if steps_sampled != len(steps):
        mm["steps without a recorded sample"] += len(steps) - steps_sampled
    counts = {"pdelay": len(rec_pd), "nRR": len(rec_nrr), "gm": len(rec_gm), "comp": len(rec_comp) - 1,
              "steps": len(steps), "clock samples": len(tc), "step samples": n_step_samples}
    return not mm, counts, mm


# ---------------------------------------------------------------------------------------
# C3: model-mutation controls. Each mutant changes one rule of the slave model; the C1
# comparison must detect it (exact mismatch on at least one run), except where a mutant is
# predicted, before running, to be indistinguishable on these runs (stated with the reason).
def _clock_set_origin_first(self, t, new, ppm):
    old = self.at(t)
    m = t - self.s0
    self.p = (self.p - self.e * m) % M.Q63   # accumulator advanced with the OLD compensation
    self.e = M.from_ppm(ppm)
    self.s0, self.C0 = t, new
    self.steps.append((t, old, new, ppm))


MUTANTS = {
    "smoothing products truncated (int(x*d)) instead of SimTime rounding floor(x*d + 0.5)":
        (("simtime_times_double", lambda x, d: int(float(x) * d)), None, None),
    "compensation changed after the origin move (accumulator advanced with the old compensation)":
        (None, _clock_set_origin_first, None),
    "neighborRateRatio not applied to t4 - t1":
        (("mul_round", lambda t, e: t), None, None),
    "rate ratios from a double quotient (fromDifferenceTo1(num/den - 1)) instead of the exact integer ratio":
        (("from_integer_ratio", lambda num, den: M._llround(-(float(num) / float(den) - 1.0) * float(M.Q63))), None, None),
    "Sync reception timestamp taken at the last bit (receptionEnded)":
        (None, None, "sync_end"),
    "Pdelay t1/t4 taken at the last bit":
        (None, None, "pdelay_end"),
}
# predicted undetectable on these runs: Pdelay_Req and Pdelay_Resp frames have the same length, so t4 - t1
# is unchanged, and t4 differences (neighborRateRatio) are unchanged
EXPECT_UNDETECTED = {"Pdelay t1/t4 taken at the last bit"}


def run_mutant(R, V, spec):
    fpatch, setpatch, evmode = spec
    saved_f, saved_set = None, M.Clock.set
    if fpatch:
        saved_f = getattr(M, fpatch[0])
        setattr(M, fpatch[0], fpatch[1])
    if setpatch:
        M.Clock.set = setpatch
    try:
        ev = slave_events(R, "sim")
        if evmode == "sync_end":
            ev = [e if e[0] != "syncrx" else (e[0], e[1], e[2], e[1]) for e in ev]
        elif evmode == "pdelay_end":
            ev = [(e[0], e[1], e[2], e[1], e[4]) if e[0] == "reqtx" else
                  (e[0], e[1], e[2], e[1], e[4], e[5]) if e[0] == "resprx" else e for e in ev]
        try:
            m = M.SlaveModel().run(ev)
            ok, _, mm = compare_recorded(R, m, V)
        except AssertionError as x:
            ok, mm = False, {"model assertion": str(x)}
    finally:
        if fpatch:
            setattr(M, fpatch[0], saved_f)
        M.Clock.set = saved_set
    return ok, mm


# ---------------------------------------------------------------------------------------
def main():
    hashes = load_hashes()
    os.makedirs(OUT, exist_ok=True)
    prov, prov_bad, vec_info = 0, [], []
    census = defaultdict(Counter)
    a2_bad, a3_bad, a4 = [], [], Counter()
    a4_bad = []
    b0_bad, b1_bad = [], []
    lup_vals, ldn_vals = Counter(), Counter()
    c1, c2 = [], []
    c3 = defaultdict(list)
    d1_bad, d1_info = [], Counter()
    lag = []
    d2_bad, d2b_bad, d2_info = [], [], Counter()
    d3 = {k: {"bad": [], "nz": 0, "n": 0, "maxloss": 0, "maxerr_step": 0, "maxerr_arr": 0, "maxerr_per": 0}
          for k in ("a 802.1AS floor", "b 802.1AS round", "c INET writeClock8")}
    d4 = []
    nc = {k: {"bad": [], "n": 0, "sig": Counter()} for k in ("NC-a", "NC-b", "NC-c", "NC-d", "NC-d2", "NC-e", "NC-f")}
    sync_rows = []
    res_all, res_subns = [], 0

    for cfg, rep in PRIMARY + CONTROLS:
        primary = (cfg, rep) in PRIMARY
        R = load(Run(cfg, rep), with_logs=primary)
        name = f"{cfg}#{rep}"

        # ---- A1 provenance
        for path in R.files:
            p = os.path.normpath(path)
            got = sha256(p)
            if hashes.get(p) != got:
                prov_bad.append(f"{name}: {os.path.relpath(p, RUNS)}")
            prov += 1
        vh = sha256(R.vec)
        vec_info.append((name, vh, hashes.get(os.path.normpath(R.vec)) == vh))

        # ---- A2 decoding census
        for where, fr in (("GM out", R.gm_out), ("GM in", R.gm_in), ("NW-TT in", R.nw_in), ("NW-TT out", R.nw_out),
                          ("DS-TT out", R.ds_out), ("DS-TT in", R.ds_in), ("slave in", R.sl_in),
                          ("slave out", R.sl_out)):
            for f in fr:
                g = f["g"]
                sig = (TNAME.get(g["type"], g["type"]), g["majorSdoId"], g["versionPTP"], g["minorVersionPTP"],
                       g["messageLength"], g["domain"], g["minorSdoId"], f"0x{g['flags']:04x}", g["control"],
                       g["logInterval"], g.get("tlv"), g.get("csro"))
                census[where][sig] += 1
                if g["versionPTP"] != 2 or g["domain"] != 0 or not f["fcs_ok"]:
                    a2_bad.append(f"{name} {where} {TNAME.get(g['type'])} seq {g['seq']}")
                if g["type"] == SYNC:
                    a4[f"Sync flags 0x{g['flags']:04x} ({where})"] += 1
                if g["type"] == FU and (g["tlv"][0] != 3 or g["csro"] != 0):
                    a2_bad.append(f"{name} {where} Follow_Up seq {g['seq']} TLV {g['tlv']} csro {g['csro']}")

        # ---- A3 payload identity along the path (no element on the path is time-aware today)
        def seqpay(fr):
            return [f["payload"] for f in fr]
        def subseq(a, b):  # b is an in-order subsequence of a; returns the number of elements of a missing in b
            it, n = iter(a), 0
            for x in b:
                for y in it:
                    if y == x:
                        break
                    n += 1
                else:
                    return None
            return n + sum(1 for _ in it)
        # cables: identical sequences; through the 5GS: in-order subsequence (messages may be lost in the 5GS)
        dl_lost = subseq(seqpay(R.nw_in), seqpay(R.ds_out))
        ul_lost = subseq(seqpay(R.ds_in), seqpay(R.nw_out))
        dl_ok = seqpay(R.gm_out) == seqpay(R.nw_in) and seqpay(R.ds_out) == seqpay(R.sl_in) and dl_lost is not None
        ul_ok = seqpay(R.sl_out) == seqpay(R.ds_in) and seqpay(R.nw_out) == seqpay(R.gm_in) and ul_lost is not None
        if dl_ok and ul_ok:
            for f in R.nw_in:
                if f["payload"] not in {x["payload"] for x in R.ds_out}:
                    a4[f"DL not delivered by the 5GS: {TNAME[f['g']['type']]} ({name})"] += 1
            a4["DL lost/undelivered in the 5GS"] += dl_lost
            a4["UL lost/undelivered in the 5GS"] += ul_lost
        a4["DL frames GM out"] += len(R.gm_out)
        a4["DL frames at slave"] += len(R.sl_in)
        a4["UL frames slave out"] += len(R.sl_out)
        a4["UL frames at GM"] += len(R.gm_in)
        if not (dl_ok and ul_ok):
            a3_bad.append(f"{name}: DL {dl_ok} UL {ul_ok}")

        # ---- A4 timestamp semantics, residues, correctionField
        gm_sync, gm_fu = by_type_seq(R.gm_out, SYNC), by_type_seq(R.gm_out, FU)
        gm_req, gm_resp, gm_rfu = by_type_seq(R.gm_in, REQ), by_type_seq(R.gm_out, RESP), by_type_seq(R.gm_out, RFU)
        R.sim_pot, R.sim_t2, R.sim_t3 = {}, {}, {}
        res_n = Counter()
        for s, fu in gm_fu.items():
            sim, wire = gm_sync[s]["start"], wire_ts(fu["g"]["pot"])
            if floor_ns(sim) != wire:
                a4_bad.append(f"{name} POT seq {s}: sim {sim} wire {wire}")
            R.sim_pot[s] = sim
            res_n["POT"] += 1
            res_n["POT residue"] += sim != wire
        for s, rp in gm_resp.items():
            sim, wire = gm_req[s]["start"], wire_ts(rp["g"]["ts"])
            if floor_ns(sim) != wire:
                a4_bad.append(f"{name} t2 seq {s}: sim {sim} wire {wire}")
            R.sim_t2[s] = sim
            res_n["t2"] += 1
            res_n["t2 residue"] += sim != wire
        for s, rf in gm_rfu.items():
            sim, wire = gm_resp[s]["start"], wire_ts(rf["g"]["ts"])
            if floor_ns(sim) != wire:
                a4_bad.append(f"{name} t3 seq {s}: sim {sim} wire {wire}")
            R.sim_t3[s] = sim
            res_n["t3"] += 1
            res_n["t3 residue"] += sim != wire
        for fr in (R.gm_out, R.gm_in, R.nw_in, R.nw_out, R.ds_out, R.ds_in, R.sl_in, R.sl_out):
            for f in fr:
                a4["frames"] += 1
                if f["g"]["cf_raw"] != 0:
                    a4_bad.append(f"{name} non-zero correctionField")
        for k, v in res_n.items():
            a4[k] += v
        residue_runs = res_n["POT residue"] + res_n["t2 residue"] + res_n["t3 residue"]
        # C2 prediction (independent of the model): wire and sim inputs give the same slave outputs iff the residues
        # cancel in every quantity the slave forms: t3 - t2 per exchange (pdelay), t3_k - t3_k-1 (neighborRateRatio),
        # POT (offset and gmRateRatio). Exchanges/Follow_Ups the slave actually uses (sequence ids seen at the slave).
        sl_rfu = [f["g"]["seq"] for f in R.sl_in if f["g"]["type"] == RFU]
        sl_fu_seq = [f["g"]["seq"] for f in R.sl_in if f["g"]["type"] == FU]
        r2 = {s: R.sim_t2[s] - wire_ts(gm_resp[s]["g"]["ts"]) for s in sl_rfu}
        r3 = {s: R.sim_t3[s] - wire_ts(gm_rfu[s]["g"]["ts"]) for s in sl_rfu}
        pred_dev = Counter()
        pred_dev["t3-t2 residue != 0"] = sum(1 for s in sl_rfu if r3[s] != r2[s])
        pred_dev["t3 residue changes between exchanges"] = sum(1 for a_, b_ in zip(sl_rfu, sl_rfu[1:]) if r3[a_] != r3[b_])
        pred_dev["POT residue != 0"] = sum(1 for s in sl_fu_seq if R.sim_pot[s] != wire_ts(gm_fu[s]["g"]["pot"]))

        # ---- C1 (sim mode) and C2 (wire mode)
        V = read_vec(R.vec)
        msim = model(R, "sim")
        ok, counts, mm = compare_recorded(R, msim, V)
        c1.append((name, ok, counts, mm, msim.out["ignored"], msim.out["sync_overwritten"]))
        mwire = model(R, "wire")
        okw, _, mmw = compare_recorded(R, mwire, V)
        dev = []
        if not okw:
            dpd = [w[1] - s_[1] for w, s_ in zip(mwire.out["pdelay"], msim.out["pdelay"]) if w != s_]
            dst = [w[2] - s_[2] for w, s_ in zip(mwire.clk.steps, msim.clk.steps) if w != s_]
            dev = (len(dpd), (min(dpd), max(dpd)) if dpd else None, len(dst), (min(dst), max(dst)) if dst else None)
        c2.append((name, residue_runs, okw, dict(mmw), dev, +pred_dev))

        # ---- C3 model-mutation controls
        for lab, spec in MUTANTS.items():
            okm, mmm = run_mutant(R, V, spec)
            c3[lab].append((name, okm, mmm))

        # ---- D4 current behaviour (recorded; through the C1-validated model at Sync arrivals)
        sample_times = sorted({ps(t) for t, v in V["clock"]})
        first_step = msim.clk.steps[0][0] if msim.clk.steps else None
        st_ = [t for t in sample_times if first_step is not None and t > first_step]
        rec_err = [v - t for v, t in zip(replay_at(msim.clk.steps, 0, st_), st_)]  # = recorded (C1)
        arr = [f["t2"] - f["ts"] for f in msim.out["fu"][1:]]
        aft = [f["new"] - f["t"] for f in msim.out["fu"]]
        d4.append((name, max(map(abs, rec_err)) if rec_err else None, max(map(abs, arr)) if arr else None,
                   max(map(abs, aft)) if aft else None, len(msim.out["fu"])))

        if not primary:
            continue

        # ---- per-Sync intervals: B0, B1
        nw_sync, ds_sync, sl_sync = by_type_seq(R.nw_in, SYNC), by_type_seq(R.ds_out, SYNC), by_type_seq(R.sl_in, SYNC)
        ds_fu = by_type_seq(R.ds_out, FU)
        for fr_a, fr_b, lab in ((R.gm_out, R.nw_in, "Lup"), (R.ds_out, R.sl_in, "Ldn"),
                                (R.sl_out, R.ds_in, "Ldn UL"), (R.nw_out, R.gm_in, "Lup UL")):
            for a, b in zip(fr_a, fr_b):
                d = b["start"] - a["start"]
                (lup_vals if lab.startswith("Lup") else ldn_vals)[d] += 1
                if d != L_REF or b["end"] - a["end"] != L_REF:
                    b0_bad.append(f"{name} {lab} {TNAME[a['g']['type']]} seq {a['g']['seq']}: {d}")
        S = {}
        for s, sl in sl_sync.items():
            gm, nw, ds = gm_sync[s], nw_sync[s], ds_sync[s]
            k = gm["key"]
            ing, tx1, tx0, rx0 = R.l_ing[k], R.l_tx1[k], R.l_tx0[k], R.l_rx0[k]
            t1, t12, t9 = ps(ing["ingressTime"]), ps(tx1["egressTime"]), ps(tx1["tSlot"])
            t5, t8 = ps(tx0["egressTime"]), ps(rx0["tRxEnd"])
            Xin, Xout = (nw["L"] + 8) * 8 * NS, (ds["L"] + 8) * 8 * NS
            if t1 != nw["end"] or t12 != ds["end"]:
                b1_bad.append(f"{name} seq {s}: log t1/t12 != PCAP")
            Res = (t12 - Xout) - (t1 - Xin)
            Lup, Ldn = nw["start"] - gm["start"], sl["start"] - ds["start"]
            D = sl["start"] - gm["start"]
            if D != Lup + Res + Ldn:
                b1_bad.append(f"{name} seq {s}: D {D} != {Lup} + {Res} + {Ldn}")
            # D1: Follow_Up at DS-TT (FIFO entry t9_FU) vs the Sync's final egress t12
            fk = ds_fu[s]["key"] if s in ds_fu else None
            fu_t9 = ps(R.l_tx1[fk]["tSlot"]) if fk in R.l_tx1 else None
            S[s] = {"seq": s, "gm_start": gm["start"], "pot_wire": wire_ts(gm_fu[s]["g"]["pot"]) if s in gm_fu else None,
                    "t1": t1, "t12": t12, "t9": t9, "t5": t5, "t8": t8, "Xin": Xin, "Xout": Xout, "Res": Res,
                    "B": t8 - t5, "Lup": Lup, "Ldn": Ldn, "D": D, "sl_start": sl["start"], "fu_t9": fu_t9}
            res_all.append(Res)
            res_subns += Res % NS != 0

        # ---- D1 association at the slave (domainNumber, sequenceId, sourcePortIdentity), one-to-one
        sl_fu = [f for f in R.sl_in if f["g"]["type"] == FU]
        used = set()
        for f in sl_fu:
            g = f["g"]
            m_ = [x for x in R.sl_in if x["g"]["type"] == SYNC and (x["g"]["domain"], x["g"]["seq"], x["g"]["spi"]) ==
                  (g["domain"], g["seq"], g["spi"])]
            if len(m_) != 1 or m_[0]["end"] >= f["start"] or g["seq"] in used:
                d1_bad.append(f"{name} FU seq {g['seq']}")
            used.add(g["seq"])
            d1_info["Follow_Ups at slave"] += 1
            s = S.get(g["seq"])
            if s is None or s["fu_t9"] is None:
                d1_bad.append(f"{name} FU seq {g['seq']}: no DS-TT record")
                continue
            if s["fu_t9"] < s["t12"]:
                d1_info["held (FU entered DS-TT FIFO before its Sync's final egress)"] += 1
            lag.append(s["fu_t9"] - s["t12"])
        d1_info["Syncs at slave"] += len(sl_sync)
        d1_info["model: Follow_Ups ignored by the slave"] += len([x for x in msim.out["ignored"] if x[0] == "fu"])
        d1_info["model: Sync overwritten before its Follow_Up"] += msim.out["sync_overwritten"]

        cfp = lambda f: L_REF + S[f["g"]["seq"]]["Res"]  # noqa: E731  cf' = Lup_ref + Res (ps, unserialized)

        def errs(m, initial=0):
            fu = m.out["fu"]
            aft = [f["new"] - f["t"] for f in fu]
            arr = [f["t2"] - f["ts"] for f in fu]
            fs = m.clk.steps[0][0]
            ts_ = [t for t in sample_times if t > fs]
            per = [v - t for v, t in zip(replay_at(m.clk.steps, initial, ts_), ts_)]
            return aft, arr, per

        # ---- D2 prediction
        for initial, bad in ((0, d2_bad), (INJECTED_OFFSET, d2b_bad)):
            m = model(R, "sim", cf_fn=cfp, pdelay_override=L_REF, initial=initial)
            aft, arr, per = errs(m, initial)
            fu = m.out["fu"]
            if any(aft) or any(arr[1:]) or any(per) or arr[0] != initial:
                bad.append(f"{name}: max|after step| {max(map(abs, aft))} max|arrival| {max(map(abs, arr[1:]))} "
                           f"max|periodic| {max(map(abs, per)) if per else 0}")
            if any(f["gm_e"] != 0 for f in fu) or any(v != 1.0 for t, v in m.out["gm"]) or \
                    any(p != 0.0 for t, o, n, p in m.clk.steps):
                bad.append(f"{name}: gmRateRatio/compensation not exactly 1/0")
            if [f["seq"] for f in fu] != [f["seq"] for f in msim.out["fu"]] or m.out["ignored"] != msim.out["ignored"]:
                bad.append(f"{name}: processed Follow_Up set differs from the recorded slave's")
            if initial == 0:
                d2_info["Follow_Ups (steps)"] += len(fu)
                d2_info["periodic samples after the first step"] += len(per)
                d2_info["Sync arrivals after the first step"] += len(arr) - 1

        # ---- D3 encodings (cf' encoded, decoded with INET readClock8; POT truncated to ns)
        enc = {"a 802.1AS floor": M.scaled_ns_floor, "b 802.1AS round": M.scaled_ns_round,
               "c INET writeClock8": M.inet_write_clock8}
        for lab, fn in enc.items():
            dec = lambda f, fn=fn: M.inet_read_clock8(fn(cfp(f)))  # noqa: E731
            m = model(R, "sim", cf_fn=dec, pdelay_override=L_REF, pot_fn=lambda s: S[s]["pot_wire"])
            aft, arr, per = errs(m)
            x = d3[lab]
            for i, f in enumerate(m.out["fu"]):
                s = S[f["seq"]]
                loss = (L_REF + s["Res"] - M.inet_read_clock8(fn(L_REF + s["Res"]))) + (s["gm_start"] - s["pot_wire"])
                x["n"] += 1
                x["nz"] += loss != 0
                x["maxloss"] = max(x["maxloss"], abs(loss))
                if f["src"] - f["ts"] != -loss:
                    x["bad"].append(f"{name} seq {f['seq']}: estimate error {f['src'] - f['ts']} != -loss {-loss}")
                if i == 0 and aft[0] != -loss:
                    x["bad"].append(f"{name}: error after step 1 {aft[0]} != -loss {-loss}")
                s["d3" + lab[0]] = loss
            x["maxerr_step"] = max(x["maxerr_step"], max(map(abs, aft)))
            x["maxerr_arr"] = max(x["maxerr_arr"], max(map(abs, arr[1:])))
            x["maxerr_per"] = max(x["maxerr_per"], max(map(abs, per)) if per else 0)

        # ---- E negative controls
        fu_order = [f["seq"] for f in msim.out["fu"]]
        prev = {fu_order[i]: fu_order[i - 1] for i in range(1, len(fu_order))}
        e_rr = M.from_ppm(NC_RR_PPM)
        ncdef = {
            "NC-a": dict(cf_fn=lambda f: S[f["g"]["seq"]]["Res"], pdelay_override=L_REF),
            "NC-b": dict(cf_fn=cfp, pdelay_override=None),
            "NC-c": dict(cf_fn=lambda f: L_REF + S[prev.get(f["g"]["seq"], f["g"]["seq"])]["Res"],
                         pdelay_override=L_REF),
            "NC-d": dict(cf_fn=lambda f: L_REF + (S[f["g"]["seq"]]["t9"] - S[f["g"]["seq"]]["Xout"])
                         - (S[f["g"]["seq"]]["t1"] - S[f["g"]["seq"]]["Xin"]), pdelay_override=L_REF),
            "NC-d2": dict(cf_fn=lambda f: L_REF + S[f["g"]["seq"]]["t12"] - (S[f["g"]["seq"]]["t1"] - S[f["g"]["seq"]]["Xin"]),
                          pdelay_override=L_REF),
            "NC-e": dict(cf_fn=lambda f: M.mul_round(L_REF + S[f["g"]["seq"]]["Res"], e_rr), pdelay_override=L_REF),
            "NC-f": dict(cf_fn=lambda f: L_REF + S[f["g"]["seq"]]["Res"] + S[f["g"]["seq"]]["B"], pdelay_override=L_REF),
        }
        for lab, kw in ncdef.items():
            m = model(R, "sim", **kw)
            aft, arr, per = errs(m)
            fu = m.out["fu"]
            s1 = S[fu[0]["seq"]]
            x = nc[lab]
            x["n"] += len(fu)
            for i, f in enumerate(fu):
                S[f["seq"]][lab] = aft[i]
            if lab == "NC-a":
                ok = all(e == -L_REF for e in aft)
                x["sig"].update(aft)
            elif lab == "NC-b":
                ok = aft[0] == fu[0]["pd"] - L_REF and all(e != 0 for e in aft)
                x["sig"][f"step 1: {fmt(aft[0])} = pdelay1 {fmt(fu[0]['pd'])} - 50 ns"] += 1
            elif lab == "NC-c":
                r1, r2 = S[fu[0]["seq"]]["Res"], S[fu[1]["seq"]]["Res"]
                ok = aft[0] == 0 and aft[1] == r1 - r2 and \
                    all(aft[i] != 0 for i in range(1, len(fu)) if S[fu[i]["seq"]]["Res"] != S[fu[i - 1]["seq"]]["Res"])
                x["sig"]["steps with Res_k != Res_k-1"] += sum(
                    1 for i in range(1, len(fu)) if S[fu[i]["seq"]]["Res"] != S[fu[i - 1]["seq"]]["Res"])
                x["sig"]["steps with non-zero error"] += sum(1 for e in aft if e)
            elif lab == "NC-d":
                ok = aft[0] == -(s1["t12"] - s1["t9"]) and all(e != 0 for e in aft)
                x["sig"][f"step 1: {fmt(aft[0])}"] += 1
            elif lab == "NC-d2":
                ok = all(aft[i] == S[f["seq"]]["Xout"] for i, f in enumerate(fu))
                x["sig"].update(aft)
            elif lab == "NC-e":
                base = L_REF + s1["Res"]
                ok = aft[0] == M.mul_round(base, e_rr) - base and all(e != 0 for e in aft)
                x["sig"][f"step 1: {fmt(aft[0])}"] += 1
            else:
                ok = aft[0] == s1["B"] and all(e != 0 for e in aft)
                x["sig"][f"step 1: {fmt(aft[0])}"] += 1
            if not ok:
                x["bad"].append(f"{name}: after-step errors {aft[:3]}...")
            # every control must fail the D2 criterion
            if not (any(aft) or any(arr[1:]) or any(per)):
                x["bad"].append(f"{name}: not detected by the D2 criterion")

        for s in sorted(S):
            r = S[s]
            r["run"] = name
            sync_rows.append(r)

    # ---------------------------------------------------------------------------------------
    # A5: serializer rules, Python encoders vs the real INET serializer (probe)
    a5_bad, a5_n = [], Counter()
    with open(PROBE) as fh:
        for line in fh:
            p = line.split()
            if p[0] == "cf":
                v, wire, back = int(p[1]), int(p[2], 16), int(p[3])
                wire = wire - (1 << 64) if wire >= 1 << 63 else wire
                ok = M.inet_write_clock8(v) == wire and M.inet_read_clock8(wire) == back
            elif p[0] == "cfraw":
                ok = M.inet_read_clock8(int(p[1])) == int(p[2])
            elif p[0] == "ts":
                v, wire, back = int(p[1]), p[2], int(p[3])
                s_, n_ = M.inet_write_timestamp(v)
                ok = f"{s_:012x}{n_:08x}" == wire and M.inet_read_timestamp(s_, n_) == back
            elif p[0] == "rr":
                v, x, back = float(p[1]), int(p[2]), float(p[3])
                ok = M.inet_csro(v) == x and M.inet_rr_from_csro(x) == back
            else:
                ok = False
            a5_n[p[0]] += 1
            if not ok:
                a5_bad.append(line.strip())

    # ---------------------------------------------------------------------------------------
    nprim = f"M2S1 seeds 0-9, M2S1-frag, M2S1-load, M2S1-load-harq16"
    add("A1", f"provenance: every PCAP and port log read is hash-identical to M2-S1 raw-outputs.sha256 (56c8fb3)",
        not prov_bad, f"{prov} files, mismatches: {prov_bad[:5] or 'none'}; the slave's .vec files (not byte-reproducible: run "
        f"attributes such as date and process id) are hashed in vec.sha256")
    add("A2", "decoding: every gPTP frame at GM, NW-TT eth[1], DS-TT eth[1] and slave decodes (34 B header + body, "
        "INET serializer layout); versionPTP 2, domain 0, FCS valid; Follow_Up TLV type 3, csro 0; flags recorded",
        not a2_bad, f"census in census.txt; Sync flags: {sorted((k, v) for k, v in a4.items() if k.startswith('Sync flags'))}; "
        f"problems: {a2_bad[:5] or 'none'}")
    add("A3", "payload transport: gPTP payload bytes identical on every cable (GM -> NW-TT eth[1], DS-TT eth[1] -> slave and "
        "UL); across the 5GS the delivered messages are an in-order, byte-identical subsequence of those entering it; no "
        "element on the path is time-aware",
        not a3_bad, f"{a4['DL frames GM out']} DL frames sent by the GM, {a4['DL frames at slave']} at the slave; "
        f"{a4['UL frames slave out']} UL sent, {a4['UL frames at GM']} at the GM; lost or still in flight at the end inside the 5GS: DL "
        f"{a4['DL lost/undelivered in the 5GS']} {sorted((k.split(': ', 1)[1], v) for k, v in a4.items() if k.startswith('DL not delivered'))}, "
        f"UL {a4['UL lost/undelivered in the 5GS']}; problems: {a3_bad or 'none'}")
    add("A4", "timestamp semantics: wire POT = floor_ns(GM Sync transmissionStarted), wire t2 = floor_ns(GM Pdelay_Req "
        "receptionStarted), wire t3 = floor_ns(GM Pdelay_Resp transmissionStarted); correctionField 0 on every frame",
        not a4_bad, f"POT {a4['POT']} (sub-ns residue on {a4['POT residue']}), t2 {a4['t2']} (residue on "
        f"{a4['t2 residue']}), t3 {a4['t3']} (residue on {a4['t3 residue']}); {a4['frames']} frames, correctionField 0; "
        f"problems: {a4_bad[:5] or 'none'}")
    add("A5", "serialization rules: the oracle's encoders/decoders equal INET 4.7.0's real GptpPacketSerializer "
        "(gptp_serializer_probe) on every synthetic vector: writeClock8 drops the sub-ns part, readClock8 decodes the "
        "2^-16 ns fraction (floor to ps), timestamps truncate to ns, csro = ceil((rr-1)*2^41)",
        not a5_bad and sum(a5_n.values()) > 0, f"vectors {dict(a5_n)}; mismatches: {a5_bad or 'none'}")
    add("B0", "reference link delays (cable propagation, NOT a Pdelay implementation): every gPTP frame GM -> NW-TT eth[1] "
        "and DS-TT eth[1] -> slave (and UL) starts and ends exactly 50 ns later",
        not b0_bad, f"Lup values {dict(lup_vals)}; Ldn values {dict(ldn_vals)} (ps); problems: {b0_bad[:5] or 'none'}")
    add("B1", "timing identity (consistency of the measured intervals ONLY, not evidence of gPTP correctness): for every "
        "DL Sync, D = slave Sync receptionStarted - GM Sync transmissionStarted = Lup + Res + Ldn exactly, "
        "Res = (t12 - X_out) - (t1 - X_in) from the M2-S1 logs (t1, t12 = PCAP)",
        not b1_bad, f"{len(res_all)} Syncs ({nprim}); Res {rng(res_all)}; Res with a sub-ns part: {res_subns}; "
        f"problems: {b1_bad[:5] or 'none'}")
    c1ok = all(x[1] for x in c1)
    tot = Counter()
    for x in c1:
        tot.update(x[2])
    add("C1", "independent INET-slave model, sim mode (wire fields + sub-ns residue restored from the GM's event times) "
        "reproduces every recorded slave value exactly: pdelay, neighborRateRatio, gmRateRatio, oscillator "
        "compensation, every talker.clock timeChanged sample (1 ms periodic and the old value at every step)",
        c1ok, f"{len(c1)} runs ({nprim}, M2S1-off, M2S1-load-off); totals {dict(tot)}; per run: "
        + "; ".join(f"{n} {'ok' if ok else dict(mm)}" for n, ok, c, mm, ig, so in c1))
    c2ok = all((not pd_) == okw for n, r, okw, mm, dev, pd_ in c2)
    add("C2", "wire mode (decoded fields only) deviates from the recording if and only if the run has a non-zero sub-ns "
        "residue that does not cancel in a quantity the slave forms (t3 - t2 per exchange, t3 between exchanges, "
        "POT); predicted from the decoded residues, independently of the model", c2ok,
        "; ".join(f"{n}: residues {r}, wire equal {okw}" + (f", deviating pdelay samples {dev[0]} (wire-sim {dev[1]} ps), "
                                                            f"steps {dev[2]} (new-value diff {dev[3]} ps)" if dev else "")
                  + (f", predicted deviation {dict(pd_)}" if pd_ else ", predicted: none") for n, r, okw, mm, dev, pd_ in c2))
    c3_bad, c3_txt = [], []
    for lab in MUTANTS:
        det = [n for n, okm, mmm in c3[lab] if not okm]
        expect = lab not in EXPECT_UNDETECTED
        if bool(det) != expect:
            c3_bad.append(lab)
        kinds = Counter()
        for n, okm, mmm in c3[lab]:
            kinds.update(k for k in mmm)
        c3_txt.append(f"[{lab}] detected on {len(det)}/{len(c3[lab])} runs"
                      + (f" ({dict(kinds)})" if det else " (predicted: not distinguishable on these runs)" if not expect else ""))
    add("C3", "model-mutation controls: each single-rule mutant of the slave model fails C1 on at least one run, "
        "except the one predicted (before running) to be indistinguishable on these runs", not c3_bad,
        "; ".join(c3_txt) + f"; unexpected: {c3_bad or 'none'}")
    add("D1", "association: every DL Follow_Up at the slave matches exactly one earlier Sync by (domainNumber, sequenceId, "
        "sourcePortIdentity); at DS-TT every Follow_Up enters the MAC FIFO after its Sync's final egress (hold count 0)",
        not d1_bad and d1_info["held (FU entered DS-TT FIFO before its Sync's final egress)"] == 0,
        f"{dict(d1_info)}; Follow_Up lag (FU FIFO entry - Sync t12) {rng(lag)}; problems: {d1_bad[:5] or 'none'}")
    add("D2", "prediction: cf' = Lup_ref + Res (ps, unserialized), slave pdelay = Ldn_ref: predicted slave clock error "
        "(model clock - GM time) is 0 ps exactly immediately after every step, at every Sync arrival after the first "
        "step and at every 1 ms sample time after the first step; gmRateRatio exactly 1, compensation 0",
        not d2_bad, f"{dict(d2_info)}; problems: {d2_bad[:3] or 'none'}")
    add("D2b", f"the same with the slave clock offset by {INJECTED_OFFSET} ps before the first step (offline only): the "
        f"error is the offset until the first step and 0 ps exactly from the first step on", not d2b_bad,
        f"problems: {d2b_bad[:3] or 'none'}")
    for lab, x in d3.items():
        add(f"D3{lab[0]}", f"encoding {lab[2:]}: cf' encoded and decoded with INET readClock8, POT truncated to ns; the "
            f"slave's GM-time estimate at every Sync is off by exactly the encoding loss, and the error after step 1 = "
            f"-loss", not x["bad"] and x["n"] > 0,
            ("NOT EXERCISED by these runs: the encoding loss is 0 on every Follow_Up (no sub-ns part in any Lup + Res or "
             "POT), so the row only confirms that the encodings are lossless here; " if x["nz"] == 0 else "") +
            f"{x['n']} Follow_Ups, non-zero loss on {x['nz']} (max {fmt(x['maxloss'])}); resulting max |error|: after "
            f"steps {fmt(x['maxerr_step'])}, at Sync arrivals {fmt(x['maxerr_arr'])}, periodic {fmt(x['maxerr_per'])} "
            f"(after step 1 the rate ratio follows INET's rule; reported, not a criterion); problems: {x['bad'][:3] or 'none'}")
    add("D4", "comparison (report only): current recorded slave error vs predicted corrected error (D2: 0 ps)", True,
        "; ".join(f"{n}: recorded max|error| after the first step {fmt(a) if a is not None else 'n/a'} (1 ms samples), "
                  f"{fmt(b) if b is not None else 'n/a'} at Sync arrivals, {fmt(c) if c is not None else 'n/a'} after steps"
                  for n, a, b, c, k in d4))
    expl = {"NC-a": "upstream link delay omitted (cf' = Res): error after every step = -50 ns",
            "NC-b": "correction with the forwarded Pdelay (slave keeps its own pdelay): error after step 1 = +(pdelay1 - 50 ns) (sign corrected, see M2-S3 deviations); non-zero after every step",
            "NC-c": "wrong association (Follow_Up k carries Res_k-1): error after step 2 = Res1 - Res2; non-zero wherever Res_k != Res_k-1",
            "NC-d": "MAC FIFO entry t9 used as last-bit egress: error after step 1 = -(t12 - t9) of Sync 1; non-zero after every step",
            "NC-d2": "mixed points (last-bit TSe, first-bit TSi): error after every step = +X_out of that Sync",
            "NC-e": "rate ratio 1 + 1e-4 applied with ideal clocks: error after step 1 = mulRound(Lup + Res1) - (Lup + Res1); non-zero after every step",
            "NC-f": "5GS block B added on top of Res: error after step 1 = +B1; non-zero after every step"}
    for lab, x in nc.items():
        sig = x["sig"]
        sigtxt = ", ".join(f"{fmt(k) if isinstance(k, int) else k}: {v}" for k, v in sorted(sig.items(), key=lambda kv: str(kv[0])))
        add(lab, expl[lab] + "; and the D2 criterion fails", not x["bad"] and x["n"] > 0,
            f"{x['n']} steps; signature: {sigtxt}; problems: {x['bad'][:3] or 'none'}")

    # ---- outputs
    with open(os.path.join(OUT, "census.txt"), "w") as fh:
        fh.write("# gPTP decode census per observation point: (type, majorSdoId, versionPTP, minorVersionPTP, "
                 "messageLength, domain, minorSdoId, flags, control, logMessageInterval, Follow_Up TLV (type, length, "
                 "organizationId, subType), csro): count\n")
        for where in sorted(census):
            for sig, n in sorted(census[where].items(), key=lambda kv: str(kv[0])):
                fh.write(f"{where}\t{sig}\t{n}\n")
    with open(os.path.join(OUT, "vec.sha256"), "w") as fh:
        for n, h, same in vec_info:
            fh.write(f"{h}  {n}  {'= committed M2-S1 hash' if same else '!= committed M2-S1 hash'}\n")
    cols = ["run", "seq", "gm_start", "pot_wire", "t1", "t12", "t9", "t5", "t8", "Xin", "Xout", "Lup", "Ldn", "Res", "B",
            "D", "sl_start", "fu_t9", "d3a", "d3b", "d3c", "NC-a", "NC-b", "NC-c", "NC-d", "NC-d2", "NC-e", "NC-f"]
    with open(os.path.join(OUT, "syncs.csv"), "w", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(cols + ["unit=ps"])
        for r in sync_rows:
            w.writerow([r.get(c, "") for c in cols])
    with open(os.path.join(OUT, "slave-model.txt"), "w") as fh:
        for n, ok, c, mm, ig, so in c1:
            fh.write(f"{n}\tC1 {'equal' if ok else dict(mm)}\t{c}\tignored {ig}\tsync overwritten {so}\n")

    npass = sum(1 for r in rows if r[2])
    for check, detail, ok, extra in rows:
        print(f"{'PASS' if ok else 'FAIL'}  {check} {detail}")
        if extra:
            print(f"      {extra}")
    print(f"\nOVERALL: {'PASS' if npass == len(rows) else 'FAIL'} ({npass}/{len(rows)})")
    return 0 if npass == len(rows) else 1


if __name__ == "__main__":
    sys.exit(main())
