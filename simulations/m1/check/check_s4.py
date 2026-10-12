#!/usr/bin/env python3
"""M1-S4 checker: gPTP through the non-time-aware 5G bridge. Two separate parts:

  check_s4.py transport <results dir>   -- does gPTP get through, unchanged?
  check_s4.py clock     <results dir>   -- does the slave clock behave exactly as the
                                           gPTP model predicts from the measured path?
                                           (no accuracy claim; baseline recorded)

Setup (Config S4): grandmaster = listener (behind nwTt), slave = talker (behind dsTt),
both INET TsnDevices with ideal clocks; translators and 5G system not time-aware.
Message types: 0 Sync, 8 Follow_Up (GM -> slave, DL); 2 Pdelay_Req (slave -> GM, UL);
3 Pdelay_Resp, 10 Pdelay_Resp_Follow_Up (GM -> slave, DL).

Transport rows:
  T-run       S4 seeds 0..9 and S4-pcap seed 0 finished without errors
  T-delivery  (PCAP, seed 0) every gPTP message sent by one station is received by the
              other, same sequence IDs, no duplicates; only messages sent in the last
              60 ms may still be in flight
  T-transit   (PCAP, seed 0) every gPTP frame leaves the 5G system byte-identical to how
              it entered (translator 5G-side ports), and arrives at the far station
              byte-identical to how it was sent: correctionField stays 0 -- nothing on
              the path is time-aware
  T-qfi       (PCAP N3, seed 0) gPTP frames ride the default QoS flow (QFI 0): no rule
              matches them; PDU type matches the direction
  T-state     (seeds 0..9) the slave's gPTP state advances: one GM-rate-ratio update per
              Sync/Follow_Up pair after the first (38 for the 39 pairs sent at
              0.125..4.875 s) and one pdelay update per Pdelay exchange (5, at 0..4 s)
  T-drops     (seeds 0..9) no gPTP frame dropped as "not addressed to us" at either station
  T-traffic   (seeds 0..9) the S2 talker/listener flows still deliver: received >= sent - 3
  T-control   S4-pcap (PCAP, computed FCS/checksums) gives the same gPTP and clock samples
              as S4 (seed 0)
Clock rows (seed 0; times from PCAP at the stations: start of frame = capture time -
(captured length + 8 B preamble/SFD) x 8 ns at 1 Gb/s, validated by K-timestamps):
  K-timestamps  every Follow_Up's preciseOriginTimestamp = start of its Sync at the GM
  K-pdelay      the slave's pdelay samples = INET's estimator, (r * (t4 - t1) - (t3 - t2)) / 2
                smoothed with factor 0.1 (r = neighbor rate ratio from successive
                responses), computed from the PCAP times and the responder timestamps
  K-rateratio   the slave's GM rate ratio = difference of (originTimestamp + pdelay) over
                difference of Sync arrival times, for successive Syncs
  K-steps       the slave clock offset right after each Follow_Up = t1 + pdelay - ts +
                (tf - ts) x compensation in force (t1 Sync origin, ts Sync arrival, tf
                Follow_Up arrival): its error is entirely the uncompensated path
Also written: S4/clock-baseline.txt (offset, Sync one-way delay, pdelay; 10 seeds; no claim).
"""
import os
import struct
import sys
from collections import Counter

import pandas as pd

MODE, RES = sys.argv[1], (sys.argv[2] if len(sys.argv) > 2 else "results")
OUT = os.path.join(RES, "S4")
END = 5.0
NS = 1e-9
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(path):
    d = pd.read_csv(path, low_memory=False)
    d = d[d.run.notna()].copy()
    d["seed"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
    d["mod"] = d.module.fillna("").str.replace("M1Bridge.", "", regex=False)
    return d


def vec(d, seed, mod, name):
    r = d[(d.seed == seed) & (d.type == "vector") & (d["mod"] == mod) & (d.name == name)]
    if len(r) != 1 or not isinstance(r.vectime.iloc[0], str):
        return []
    return list(zip(map(float, r.vectime.iloc[0].split()), map(float, r.vecvalue.iloc[0].split())))


def scalar(d, seed, mod, name):
    r = d[(d.seed == seed) & (d.type == "scalar") & (d["mod"] == mod) & (d.name == name)].value
    return float(r.iloc[0]) if len(r) == 1 else float("nan")


def read_pcap(path):
    b = open(path, "rb").read()
    scale = 1e-9 if struct.unpack("<I", b[:4])[0] == 0xA1B23C4D else 1e-6
    off, out = 24, []
    while off < len(b):
        sec, frac, incl, _ = struct.unpack("<IIII", b[off:off + 16])
        off += 16
        out.append((sec + frac * scale, b[off:off + incl]))
        off += incl
    return out


def gptp(frames):
    out = []
    for t, f in frames:
        if f[12:14] != b"\x88\xf7":
            continue
        g = f[14:]
        out.append(dict(t=t, start=t - (len(f) + 8) * 8 * NS, type=g[0] & 0xF, seq=int.from_bytes(g[30:32], "big"),
                        ts=int.from_bytes(g[34:40], "big") + int.from_bytes(g[40:44], "big") * NS,
                        corr=int.from_bytes(g[8:16], "big", signed=True), src=f[6:12], raw=f))
    return out


PCAP = os.path.join(OUT, "pcaprun", "pcap")
pc = lambda n: os.path.join(PCAP, f"M1Bridge.{n}.pcap")
TYPES = {0: "Sync", 8: "Follow_Up", 2: "Pdelay_Req", 3: "Pdelay_Resp", 10: "Pdelay_Resp_Follow_Up"}
DL_TYPES, UL_TYPES = (0, 8, 3, 10), (2,)
s4 = load(os.path.join(OUT, "seeds.csv"))
pr = load(os.path.join(OUT, "pcaprun.csv"))
seeds = sorted(int(x) for x in s4.seed.unique())
L = gptp(read_pcap(pc("listener.pcapRecorder[0]")))
T = gptp(read_pcap(pc("talker.pcapRecorder[0]")))
GM = next(x["src"] for x in L if x["type"] == 0)
SL = next(x["src"] for x in T if x["type"] == 2)
sent_by = lambda lst, src, typ: {x["seq"]: x for x in lst if x["src"] == src and x["type"] == typ}

if MODE == "transport":
    logs = [os.path.join(OUT, f) for f in ("run-S4-seeds.log", "run-S4-pcap.log")]
    add("T-run: S4 seeds and S4-pcap", f"S4 seeds {seeds}; S4-pcap seed 0; no errors",
        len(seeds) > 0 and all("<!> Error" not in open(f).read() for f in logs))

    det, ok = [], True
    for typ in DL_TYPES + UL_TYPES:
        src, a, b = (GM, L, T) if typ in DL_TYPES else (SL, T, L)
        tx, rx = sent_by(a, src, typ), [x for x in b if x["src"] == src and x["type"] == typ]
        rxseq = [x["seq"] for x in rx]
        missing = [s for s, x in tx.items() if s not in rxseq]
        late_ok = all(tx[s]["start"] > END - 0.060 for s in missing)
        ok &= bool(tx) and late_ok and len(rxseq) == len(set(rxseq)) and set(rxseq) <= set(tx)
        det.append(f"{TYPES[typ]} {len(tx)} sent, {len(rx)} received, {len(missing)} in flight at 5 s")
    add("T-delivery: every gPTP message reaches the other station (PCAP, seed 0)", "; ".join(det), ok)

    ds = gptp(read_pcap(pc("dsTt.pcapRecorder[0]")))
    nw = gptp(read_pcap(pc("nwTt.pcapRecorder[0]")))
    det, ok = [], True
    for name, enter, leave, src, a_sta, b_sta in (("DL", nw, ds, GM, L, T), ("UL", ds, nw, SL, T, L)):
        fin = [x["raw"] for x in enter if x["src"] == src]
        fout = [x["raw"] for x in leave if x["src"] == src]
        sta_out = [x["raw"] for x in a_sta if x["src"] == src]
        sta_in = [x["raw"] for x in b_sta if x["src"] == src]
        n = len(fout)
        same5gs = n > 0 and 0 <= len(fin) - n <= 2 and fin[:n] == fout
        same_e2e = len(sta_in) > 0 and sta_out[:len(sta_in)] == sta_in
        corr0 = all(x["corr"] == 0 for x in a_sta + b_sta)
        ok &= same5gs and same_e2e and corr0
        det.append(f"{name}: {len(fin)} into the 5G system, {n} out, byte-identical {same5gs}; station to station "
                   f"byte-identical {same_e2e}")
    add("T-transit: gPTP frames cross the 5G system and translators unchanged (PCAP, seed 0)",
        "; ".join(det) + "; correctionField 0 everywhere", ok)

    # N3: GTP-U G-PDUs (PPP / IPv4 / UDP / GTP-U with PDU Session Container) carrying gPTP
    g = []
    for _, p in read_pcap(pc("upf.pcapRecorder[0]")):
        i = p.find(b"\x00\x21\x45")
        if i < 0:
            continue
        ip = p[i + 2:]
        ihl, tot = (ip[0] & 0xF) * 4, struct.unpack(">H", ip[2:4])[0]
        u = ip[ihl + 8:tot]
        if ip[9] != 17 or u[1] != 255 or not u[0] & 0x07:
            continue
        pos, nxt, ptype, qfi = 12, u[11], None, 0
        while nxt != 0:
            if nxt == 0x85:
                ptype, qfi = u[pos + 1] >> 4, u[pos + 2] & 0x3F
            pos += 4 * u[pos]
            nxt = u[pos - 1]
        if u[pos + 12:pos + 14] == b"\x88\xf7":
            g.append((ptype, qfi))
    qfis = Counter((("DL" if t == 0 else "UL" if t == 1 else str(t)), q) for t, q in g)
    add("T-qfi: gPTP frames on N3 ride the default QoS flow (PCAP, seed 0)",
        f"G-PDUs carrying gPTP by (direction, QFI): {dict(qfis)}",
        bool(qfis) and set(q for _, q in qfis) == {0} and {d for d, _ in qfis} == {"DL", "UL"})

    st = [(s, len(vec(s4, s, "talker.gptp", "gmRateRatio:vector")), len(vec(s4, s, "talker.gptp", "pdelay:vector")))
          for s in seeds]
    add("T-state: slave gPTP state advances (seeds 0..9)",
        f"(seed, GM rate ratio updates, pdelay updates): {st}",
        all(r == 38 and p == 5 for _, r, p in st))

    drops = [scalar(s4, s, f"{n}.gptp", "packetDropNotAddressedToUs:count") for s in seeds for n in ("talker", "listener")]
    add("T-drops: no gPTP frame dropped as not addressed to us (seeds 0..9)",
        f"drop counts {sorted(set(drops))}", all(x == 0 for x in drops))

    bad = []
    for s in seeds:
        for src, snk in (("talker", "listener"), ("listener", "talker")):
            sent = sum(scalar(s4, s, f"{src}.app[{i}].io", "packetSent:count") for i in (0, 1))
            recv = scalar(s4, s, f"{snk}.app[2].sink", "packets:count")
            if not recv >= sent - 3:
                bad.append((s, src, sent, recv))
    add("T-traffic: S2 talker/listener flows still delivered (seeds 0..9)",
        f"received >= sent - 3 for both directions in every seed; violations {bad}", not bad)

    names = [("talker.gptp", "gmRateRatio:vector"), ("talker.gptp", "pdelay:vector"),
             ("talker.gptp", "neighborRateRatio:vector"), ("talker.clock", "timeChanged:vector")]
    same = all(vec(pr, 0, m, n) == vec(s4, 0, m, n) and vec(s4, 0, m, n) for m, n in names)
    add("T-control: S4-pcap gPTP and clock samples == S4 (seed 0)", "PCAP recorders and computed FCS/checksums change nothing", same)

elif MODE == "clock":
    def at(v, t, strict):
        val = None
        for a, b in v:
            if (a < t - NS) if strict else (a <= t + NS):
                val = b
        return val

    syncL, fuL = sent_by(L, GM, 0), sent_by(L, GM, 8)
    syncT, fuT = sent_by(T, GM, 0), sent_by(T, GM, 8)
    e = [abs(fuL[s]["ts"] - syncL[s]["start"]) for s in syncL if s in fuL]
    add("K-timestamps: Follow_Up originTimestamp = Sync start at the GM",
        f"{len(e)} Syncs; max difference {max(e) / NS:.3f} ns", bool(e) and max(e) <= NS)

    pv = vec(pr, 0, "talker.gptp", "pdelay:vector")
    req, resp, rfu = sent_by(T, SL, 2), sent_by(T, GM, 3), sent_by(T, GM, 10)
    pred, raws, prev, p34, r = [], [], None, None, 1.0
    for s in sorted(rfu):
        t1, t2, t3, t4 = req[s]["start"], resp[s]["ts"], rfu[s]["ts"], resp[s]["start"]
        if p34:
            r = (t3 - p34[0]) / (t4 - p34[1])
        p34 = (t3, t4)
        raw = (r * (t4 - t1) - (t3 - t2)) / 2
        raws.append((raw, t2 - t1, t4 - t3))
        prev = raw if prev is None else 0.1 * raw + 0.9 * prev
        pred.append(prev)
    err = [abs(a - b) for a, (_, b) in zip(pred, pv)]
    add("K-pdelay: slave pdelay = estimator applied to the measured exchange",
        f"{len(pv)} samples, max error {max(err) / NS:.3f} ns; raw per exchange "
        + ", ".join(f"{x * 1e3:.3f} ms (UL {u * 1e3:.3f} / DL {dl * 1e3:.3f})" for x, u, dl in raws)
        + f"; smoothed final {pv[-1][1] * 1e3:.3f} ms",
        len(pv) == len(pred) > 0 and max(err) <= NS)

    gv = vec(pr, 0, "talker.gptp", "gmRateRatio:vector")
    cv = vec(pr, 0, "talker.clock", "oscillatorCompensationChanged:vector")
    tv = vec(pr, 0, "talker.clock", "timeChanged:vector")
    prevS, rerr, oerr, nsteps, ratios, dsync = None, [], [], 0, [], []
    for s in sorted(fuT):
        tf, ts, t1 = fuT[s]["t"], syncT[s]["start"], fuT[s]["ts"]
        pd_ = at(pv, tf, False) or 0.0
        dsync.append(ts - t1)
        if prevS:
            p = (t1 + pd_ - prevS[0]) / (ts - prevS[1])
            g = at(gv, tf, False)
            rerr.append(abs(p - g))
            ratios.append(g)
        prevS = (t1 + pd_, ts)
        off = (tf - ts) * (at(cv, tf, True) or 0.0) * 1e-6 + t1 + pd_ - ts
        smp = [b - a for a, b in tv if abs(a - tf) <= NS]
        if smp:
            nsteps += 1
            oerr.append(abs(smp[-1] - off))
    add("K-rateratio: GM rate ratio = from measured Sync arrivals",
        f"{len(rerr)} updates, max error {max(rerr):.2e}; ratio range {min(ratios):.6f}..{max(ratios):.6f} "
        f"({(min(ratios) - 1) * 1e6:+.0f}..{(max(ratios) - 1) * 1e6:+.0f} ppm with ideal clocks); "
        f"Sync one-way delay {min(dsync) * 1e3:.6f}..{max(dsync) * 1e3:.6f} ms",
        bool(rerr) and max(rerr) <= 1e-12)
    add("K-steps: slave clock offset after each Follow_Up = uncompensated-path prediction",
        f"{nsteps} of {len(fuT)} Follow_Ups checked, max error {max(oerr) / NS:.3f} ns",
        nsteps == len(fuT) and max(oerr) <= NS)

    # baseline, all seeds (no claim)
    lines = ["seed  |offset| max [ms]  mean |offset| t>=1s [ms]  offset at 5 s [ms]  pdelay final [ms]  rate ratio range [ppm]"]
    for s in seeds:
        tvv = [(a, b - a) for a, b in vec(s4, s, "talker.clock", "timeChanged:vector")]
        o = [x for _, x in tvv]
        o1 = [abs(x) for a, x in tvv if a >= 1.0]
        g = [x for _, x in vec(s4, s, "talker.gptp", "gmRateRatio:vector")]
        p = vec(s4, s, "talker.gptp", "pdelay:vector")
        lines.append(f"{s:<5} {max(map(abs, o)) * 1e3:<18.3f} {sum(o1) / len(o1) * 1e3:<26.3f} {o[-1] * 1e3:<19.3f} "
                     f"{p[-1][1] * 1e3:<18.3f} {(min(g) - 1) * 1e6:+.0f}..{(max(g) - 1) * 1e6:+.0f}")
    open(os.path.join(OUT, "clock-baseline.txt"), "w").write(
        "Slave clock (talker) vs grandmaster (listener), both ideal; offset = slave clock - simulation time,\n"
        "sampled every 1 ms and at every adjustment. Config S4, uncompensated 5G bridge. Recorded, no claim.\n"
        + "\n".join(lines) + "\n")

w = max(len(x[0]) for x in rows)
for c, d_, v in rows:
    print(f"{v:4}  {c:<{w}}  {d_}")
print()
print("OVERALL:", "PASS" if all(x[2] == "PASS" for x in rows) else "FAIL")
