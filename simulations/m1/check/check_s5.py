#!/usr/bin/env python3
"""M1-S5 checker: timing metadata across the Ethernet - 5G - Ethernet bridge.

Network: Config S4 (gPTP grandmaster = listener behind nwTt, slave = talker behind dsTt,
S2 application flows) with sequence-numbered application payload (INET ApplicationPacket:
4 B length + 4 B sequence number) and INET MeasurementLayers on both translators'
5G-side ports (Config S5). Three kinds of metadata are kept apart:

  WIRE   carried in the frame bytes                        -> PCAP, both translators
  CHUNK  INET tag attached to a payload chunk (the          -> sink statistics + PCAP
         application's CreationTimeTag)
  REGION INET packet-level region tag (MeasurementLayer      -> flow statistics
         flow tag + elapsed-time tag), simulation-only
  OBS    not carried at all, reconstructed by observation  -> PCAP

Rows:
  W-identity    (PCAP, seed 0) every frame leaving the 5G system carries the identity it
                entered with (application: source, PCP, sequence number; gPTP: source,
                message type, sequence ID), byte-identical, once, in sequence order per
                flow; frames still inside at the end are only ones that entered in the
                last 100 ms; cut-and-reassembled downlink SDUs (tail lag, see O-tail)
                included
  W-gptp        (PCAP, seed 0) gPTP timestamps unchanged and correctionField 0 at both
                ends: nothing on the path writes residence time into the frame (no
                transparent-clock correction)
  C-creation    (PCAP + sink, seed 0) every received application frame's CreationTimeTag
                is present and correct: sink lifetime = reception time - the time its
                source sent that sequence number
  R-ingress     (seeds 0..9) the MeasurementLayer region tags are present on every frame up
                to the last INET module before the 5G core/RAN (UPF bridge FCS inserter for
                DL, UE Ethernet FCS inserter for UL)
  R-egress      (seeds 0..9) no frame reaches the far translator's MeasurementLayer with the
                tags: 0 transit samples recorded while frames crossed
  O-transit     (PCAP, seed 0) per-frame 5G-system transit (translator egress -> far
                translator ingress) reconstructed for every frame that crossed, by identity
  controls      S5 without measurement layers = S4 (sink samples, seed 0); S5 = S5 without
                measurement layers; S5-pcap = S5
Usage: check_s5.py <results dir containing S4/ and S5/>
"""
import os
import struct
import sys
from collections import Counter, defaultdict

import pandas as pd

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = os.path.join(RES, "S5")
NS = 1e-9
END = 5.0
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


def vcount(d, seed, mod, name):
    return len(vec(d, seed, mod, name))


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


def ident(f):
    """identity carried in the frame bytes"""
    if f[12:14] == b"\x81\x00" and f[16:18] == b"\x86\xf0":
        return ("app", f[6:12].hex(), f[14] >> 5, int.from_bytes(f[22:26], "big"))
    if f[12:14] == b"\x88\xf7":
        return ("gptp", f[6:12].hex(), f[14] & 0xF, int.from_bytes(f[44:46], "big"))
    return ("other", f[6:12].hex(), f[12:14].hex(), None)


s5 = load(os.path.join(OUT, "seeds.csv"))
pr = load(os.path.join(OUT, "pcaprun.csv"))
nm = load(os.path.join(OUT, "nomeas.csv"))
s4 = load(os.path.join(RES, "S4", "seeds.csv"))
seeds = sorted(int(x) for x in s5.seed.unique())
PC = lambda n: os.path.join(OUT, "pcaprun", "pcap", f"M1Bridge.{n}.pcap")
ds, nw = read_pcap(PC("dsTt.pcapRecorder[0]")), read_pcap(PC("nwTt.pcapRecorder[0]"))
tk, ls = read_pcap(PC("talker.pcapRecorder[0]")), read_pcap(PC("listener.pcapRecorder[0]"))
GM = next(f[6:12].hex() for _, f in ls if ident(f)[0] == "gptp" and ident(f)[2] == 0)
SL = next(f[6:12].hex() for _, f in tk if ident(f)[0] == "gptp" and ident(f)[2] == 2)

logs = [os.path.join(OUT, f) for f in os.listdir(OUT) if f.startswith("run-") and f.endswith(".log")]
add("run: S5 seeds, S5-nomeas, S5-pcap", f"S5 seeds {seeds}; {len(logs)} logs; no errors",
    len(seeds) > 0 and all("<!> Error" not in open(f).read() for f in logs))

# ---- WIRE --------------------------------------------------------------------------------
# DL: enters at nwTt port 0 (frames from GM side), leaves at dsTt port 0; UL the reverse
transit = {}
det, ok_all = [], True
for name, enter, leave, src in (("DL", nw, ds, GM), ("UL", ds, nw, SL)):
    fin = {ident(f): (t, f) for t, f in enter if f[6:12].hex() == src}
    fout = [(t, f) for t, f in leave if f[6:12].hex() == src]
    keys = [ident(f) for _, f in fout]
    dup = len(keys) != len(set(keys))
    unknown = [k for k in keys if k not in fin or k[0] == "other"]
    changed = [k for t, f in fout for k in [ident(f)] if k in fin and fin[k][1] != f]
    order_bad = 0
    last = {}
    for k in keys:
        fl = k[:3]
        if fl in last and k[3] <= last[fl]:
            order_bad += 1
        last[fl] = k[3]
    missing = [k for k in fin if k not in set(keys)]
    late_only = all(fin[k][0] > END - 0.100 for k in missing)
    for t, f in fout:
        k = ident(f)
        if k in fin:
            t_in, f_in = fin[k]
            transit[(name, k)] = (t_in - (len(f_in) + 8) * 8 * NS, t)   # start of tx into 5GS, end of rx out of it
    kinds = Counter(k[0] for k in keys)
    ok = not dup and not unknown and not changed and not order_bad and late_only and bool(keys)
    ok_all &= ok
    det.append(f"{name}: {len(fin)} in ({dict(Counter(k[0] for k in fin))}), {len(fout)} out ({dict(kinds)}); "
               f"unknown {len(unknown)}, altered {len(changed)}, duplicated {dup}, out of order {order_bad}, "
               f"still inside {len(missing)} (all entered after {END - 0.1:.1f} s: {late_only})")

# cut-and-reassembled DL SDUs: replay of gNB DRB 1 RLC (method of check_o_tail.py)
sdus = vec(pr, 0, "gnb1.cellularNic.rlc-um-2049-1.tx", "receivedPacketFromUpperLayer:vector(packetBytes)")
pdus = vec(pr, 0, "gnb1.cellularNic.rlc-um-2049-1.tx", "sentPduSize:vector")
q, i, cut = [], 0, set()
for t, s in pdus:
    while i < len(sdus) and sdus[i][0] <= t:
        q.append([sdus[i][0], int(sdus[i][1]), 0])
        i += 1
    h, s = q[0], int(s)
    if h[2] == 0:
        pay = h[1] if s == h[1] + 1 else s - 2
        if pay < h[1]:
            cut.add(round(h[0], 9))
    else:
        pay = s - 4
    h[2] += pay
    if h[2] >= h[1]:
        q.pop(0)
# DRB 1 SDUs at the gNB are the DL frames on the default flow (gPTP and PCP 0), in order
dl_drb1 = [ident(f) for t, f in nw if f[6:12].hex() == GM and (ident(f)[0] == "gptp" or ident(f)[2] != 5)]
sdu_times = [round(t, 9) for t, _ in sdus]
cut_frames = {dl_drb1[j] for j, t in enumerate(sdu_times) if t in cut and j < len(dl_drb1)}
cut_arrived = sum(1 for k in cut_frames if ("DL", k) in transit)
add("W-identity: frames leave the 5G system with the identity and bytes they entered with (PCAP, seed 0)",
    " | ".join(det) + f" | DL SDUs cut and reassembled (tail lag): {len(cut)}, of which delivered intact {cut_arrived}",
    ok_all and cut_arrived > 0 and len(dl_drb1) == len(sdus))

gp = [(t, f) for t, f in tk + ls if ident(f)[0] == "gptp"]
corr = Counter(int.from_bytes(f[22:30], "big", signed=True) for _, f in gp)
add("W-gptp: gPTP timestamps unchanged, correctionField 0 at both stations: no residence time written",
    f"{len(gp)} gPTP frames at the stations; correctionField values {dict(corr)}; byte identity through the 5G "
    "system is part of W-identity",
    set(corr) == {0} and len(gp) > 0)

# ---- CHUNK: CreationTimeTag -------------------------------------------------------------------
sent_times = {}
for st, mac in (("talker", SL), ("listener", GM)):
    for app, pcp in ((0, 5), (1, 0)):
        for seq, (t, _) in enumerate(vec(pr, 0, f"{st}.app[{app}].io", "packetSent:vector(packetBytes)")):
            sent_times[(mac, pcp, seq)] = t
bad, n = [], 0
lifetimes = {}
for st, pc in (("talker", tk), ("listener", ls)):
    # PCAP timestamps have 1 ns resolution: match a sink sample to the frame received within 1 ns before it
    rx_at = [(t, f) for t, f in pc if ident(f)[0] == "app" and ident(f)[1] != (SL if st == "talker" else GM)]
    for t, life in vec(pr, 0, f"{st}.app[2].sink", "meanBitLifeTimePerPacket:vector"):
        f = next((g for tf, g in rx_at if -1e-12 <= t - tf < NS), None)
        k = ident(f) if f is not None else None
        if k is None or k[1:] not in sent_times:
            bad.append((st, t, "unmatched"))
            continue
        n += 1
        lifetimes[k] = (t, life)
        if abs(life - (t - sent_times[k[1:]])) > NS / 1000:
            bad.append((st, t, life, t - sent_times[k[1:]]))
recv = sum(scalar(pr, 0, f"{st}.app[2].sink", "packets:count") for st in ("talker", "listener"))
add("C-creation: the application's CreationTimeTag crosses the 5G system with the correct value (seed 0)",
    f"{n} of {int(recv)} received frames matched by sequence number; lifetime = reception - send time of that "
    f"sequence number for all: {not bad}{' ' + str(bad[:3]) if bad else ''}",
    n == recv and not bad and n > 0)

# ---- REGION: MeasurementLayer tags --------------------------------------------------------------
FL = "transit5gs:flowOutgoingPacketLengths:vector"
ri, re_ = [], []
for s in seeds:
    started = {d: vcount(s5, s, f"{tt}.eth[0].measurementLayer.measurementStarter", FL) for d, tt in (("DL", "nwTt"), ("UL", "dsTt"))}
    at_core = {"DL": vcount(s5, s, "upf.ethBridge.ethernet.fcsInserter", FL),
               "UL": vcount(s5, s, "ue[0].ethernet.fcsInserter", FL)}
    ri.append((s, started, at_core))
    rec = {d: vcount(s5, s, f"{tt}.eth[0].measurementLayer.measurementRecorder", "transit5gs:meanBitElapsedTimePerPacket:vector")
           for d, tt in (("DL", "dsTt"), ("UL", "nwTt"))}
    crossed = {d: scalar(s5, s, f"{tt}.eth[0].measurementLayer.measurementRecorder", "incomingPackets:count")
               for d, tt in (("DL", "dsTt"), ("UL", "nwTt"))}
    re_.append((s, rec, crossed))
add("R-ingress: MeasurementLayer region tags present up to the last INET module before the 5G core/RAN (seeds 0..9)",
    f"seed 0: tagged at translator {ri[0][1]}, still tagged at UPF bridge (DL) / UE Ethernet (UL) {ri[0][2]}; "
    f"equal in all seeds: {all(a == b for _, a, b in ri)}",
    all(a == b and min(a.values()) > 0 for _, a, b in ri))
add("R-egress: the region tags do not survive the 5G system (seeds 0..9)",
    f"seed 0: transit samples recorded at the far translator {re_[0][1]} while frames arrived {re_[0][2]}; "
    "zero in all seeds: " + str(all(sum(r.values()) == 0 for _, r, _ in re_)),
    all(sum(r.values()) == 0 and min(c.values()) > 0 for _, r, c in re_))

# ---- OBS: reconstruction -------------------------------------------------------------------------
per = defaultdict(list)
for (dirn, k), (t0, t1) in transit.items():
    per[(dirn, k[0] if k[0] == "gptp" else f"app pcp{k[2]}")].append(t1 - t0)
add("O-transit: per-frame 5G-system transit reconstructed from PCAP by identity (seed 0)",
    "; ".join(f"{d} {c}: {len(v)} frames, {min(v) * 1e3:.3f}..{max(v) * 1e3:.3f} ms" for (d, c), v in sorted(per.items())),
    len(transit) > 0)

# ---- controls ------------------------------------------------------------------------------------
SINKS = [("talker.app[2].sink", "meanBitLifeTimePerPacket:vector"), ("listener.app[2].sink", "meanBitLifeTimePerPacket:vector"),
         ("talker.gptp", "pdelay:vector"), ("talker.clock", "timeChanged:vector")]
c1 = all(vec(nm, 0, m, n) == vec(s4, 0, m, n) and vec(s4, 0, m, n) for m, n in SINKS)
c2 = all(vec(s5, 0, m, n) == vec(nm, 0, m, n) for m, n in SINKS)
c3 = all(vec(pr, 0, m, n) == vec(s5, 0, m, n) for m, n in SINKS)
add("controls: sequence-numbered payload, measurement layers and PCAP change no sample (seed 0)",
    f"S5-nomeas = S4: {c1}; S5 = S5-nomeas: {c2}; S5-pcap = S5: {c3} (delay, pdelay and slave-clock samples)",
    c1 and c2 and c3)

w = max(len(r[0]) for r in rows)
for c, d_, v in rows:
    print(f"{v:4}  {c:<{w}}  {d_}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
