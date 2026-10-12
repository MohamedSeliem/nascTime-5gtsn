#!/usr/bin/env python3
"""M1-S3 checker: VLAN/PCP -> QFI -> DRB mapping, each direction separately.

Intended mapping (both directions): PCP 5 -> QFI 5 -> DRB 2; PCP 6 -> QFI 6 -> DRB 3;
PCP 0-4, 7 and untagged -> default QoS flow (QFI 0) -> default DRB 1.

Two separate observation points per direction:
  QFI  what the classifier decided: the QFI in the GTP-U PDU Session Container of
       every G-PDU on N3 (PCAP on the UPF's interface to the gNB). DL = UPF
       classification (dlQfiRules, PDU type 0); UL = the UE's classification
       (ulQfiRules), carried to the gNB in the SDAP header or, on a headerless DRB,
       implied by it and checked by the UE's SDAP against the classified QFI
       (Simu5G NrSdap), and forwarded by the gNB (PDU type 1).
  DRB  where the frame actually went: Simu5G creates one RLC entity per DRB, named
       ...-um-<node>-<drbId>; the size of every SDU it handled is recorded on both
       sides (UL: UE TX entity and gNB RX entity; DL: gNB TX and UE RX). Each flow has
       its own frame length, so each SDU size identifies its flow.

Rows that a run is judged on (key: meaning):
  Q-UL / Q-DL        every G-PDU of the direction carries the intended QFI for its
                     inner frame (identified by length, PCP read from its 802.1Q tag);
                     all 9 flows seen; PDU type matches the direction
  D-UL-tx / D-UL-rx / D-DL-tx / D-DL-rx
                     every flow's frames are on its intended DRB, and only there; all
                     9 flows seen; every SDU size maps to a flow
Main runs (Config S3, seeds 0..9; Config S3-pcap, seed 0) must pass all of them, plus:
  accounting     per seed, direction and flow: frames sent = SDUs entering the RLC
                 TX entities; SDUs leaving the RLC RX entities = frames received;
                 0 <= in flight in the RAN (TX - RX) <= 3
  sdap           SDU size - frame size is constant per DRB and is one byte larger on
                 the default DRB than on DRB 2 and 3: the SDAP header is present only
                 on the default DRB (single-QFI DRBs are headerless in Simu5G 1.8.0)
  transit        PCAP at the translators' 5G-side ports: in each direction every frame
                 leaves the 5G system byte-identical to how it entered (VLAN, PCP,
                 payload, FCS), per flow and in order; up to 3 per flow in flight
  control        S3-pcap (PCAP, computed FCS/checksums) gives the same delay samples
                 as S3 for seed 0
Negative controls (seed 0, with PCAP) must fail exactly the rows listed in NEG and pass
all others:
  S3-neg-absent  rules for absent VLAN 43 traffic: nothing fails, and every delay
                 sample is bit-identical to S3-pcap
  S3-mut-ul-swap UL rules swapped: Q-UL, D-UL-tx, D-UL-rx fail
  S3-mut-dl-swap DL rules swapped: Q-DL, D-DL-tx, D-DL-rx fail
  S3-mut-drb-swap QFI->DRB mapping swapped: the four D rows fail, Q rows pass
Under saturating load (Config S3-load: + a PCP 0 background flow on the default DRB,
seeds 0..4) the four D rows are repeated.
Also written (no pass/fail): per-flow delivery and delay, light and saturating load,
experimental.txt.

Usage: check_s3.py <results dir containing S3/>
"""
import glob
import math
import os
import struct
import sys
from collections import Counter, defaultdict

import pandas as pd

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = os.path.join(RES, "S3")

# flow -> (payload bytes, PCP or None for untagged); app[k] sends flow k
FLOWS = {f"pcp{p}": (100 + 20 * p, p) for p in range(8)}
FLOWS["untagged"] = (300, None)
APP = {f: i for i, f in enumerate(FLOWS)}
QFI = {f: (5 if pcp == 5 else 6 if pcp == 6 else 0) for f, (_, pcp) in FLOWS.items()}
DRB = {f: {0: 1, 5: 2, 6: 3}[q] for f, q in QFI.items()}
FRAME = {f: 14 + (4 if pcp is not None else 0) + pl for f, (pl, pcp) in FLOWS.items()}   # no FCS
SINKLEN = {f: pl + (4 if pcp is not None else 0) for f, (pl, pcp) in FLOWS.items()}      # sink packetLengths
D_ROWS = ["D-UL-tx", "D-UL-rx", "D-DL-tx", "D-DL-rx"]
NEG = {"S3-neg-absent": set(),
       "S3-mut-ul-swap": {"Q-UL", "D-UL-tx", "D-UL-rx"},
       "S3-mut-dl-swap": {"Q-DL", "D-DL-tx", "D-DL-rx"},
       "S3-mut-drb-swap": set(D_ROWS)}
# which RLC entity side records which direction
ENT = {"D-UL-tx": ("ue[0]", "tx"), "D-UL-rx": ("gnb1", "rx"),
       "D-DL-tx": ("gnb1", "tx"), "D-DL-rx": ("ue[0]", "rx")}
ENT_STAT = {"tx": "receivedPacketFromUpperLayer:vector(packetBytes)",
            "rx": "sentPacketToUpperLayer:vector(packetBytes)"}
rows = []


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(path):
    d = pd.read_csv(path, low_memory=False)
    d = d[d.run.notna()].copy()
    d["seed"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
    d["mod"] = d.module.fillna("").str.replace("M1Bridge.", "", regex=False)
    v = d[d.type == "vector"]
    idx = defaultdict(list)
    for s, m, n, x, t in zip(v.seed, v["mod"], v.name, v.vecvalue, v.vectime):
        idx[(s, n)].append((m, x, t))
    d.attrs["vec"] = idx
    return d


def vecs(d, seed, mod_pred, name, times=False):
    out = {}
    for m, x, t in d.attrs["vec"].get((seed, name), []):
        if mod_pred(m):
            x, t = (x, t) if isinstance(x, str) else ("", "")
            vals = [float(a) for a in x.split()]
            out[m] = list(zip([float(a) for a in t.split()], vals)) if times else vals
    return out


def flow_of_sdu(size):
    for f, L in FRAME.items():
        if L <= size <= L + 3:
            return f, int(size - L)
    return None, None


def drb_matrix(d, seed, key):
    """{drb: Counter(flow)}, unmapped sizes, {drb: set(offsets)} for one entity side."""
    node, side = ENT[key]
    pred = lambda m, node=node, side=side: m.startswith(node + ".cellularNic.") and "-um-" in m and m.endswith("." + side)
    mat, unmapped, offs = defaultdict(Counter), [], defaultdict(set)
    for m, vals in vecs(d, seed, pred, ENT_STAT[side]).items():
        drb = int(m.rsplit(".", 1)[0].rsplit("-", 1)[1])
        for v in vals:
            f, o = flow_of_sdu(int(v))
            if f is None:
                unmapped.append(int(v))
            else:
                mat[drb][f] += 1
                offs[drb].add(o)
    return mat, unmapped, offs


def judge_drb(mat, unmapped):
    seen = {f for c in mat.values() for f in c}
    wrong = [(drb, f, n) for drb, c in mat.items() for f, n in c.items() if DRB[f] != drb]
    ok = not wrong and not unmapped and seen == set(FLOWS)
    detail = "; ".join(f"DRB {drb}: " + ",".join(f for f in FLOWS if f in mat[drb]) for drb in sorted(mat))
    if wrong:
        detail += f" | WRONG DRB: {wrong[:4]}"
    if unmapped:
        detail += f" | unmapped sizes {sorted(set(unmapped))[:5]}"
    if seen != set(FLOWS):
        detail += f" | missing {sorted(set(FLOWS) - seen)}"
    return ok, detail


# --- PCAP --------------------------------------------------------------------------
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


def eth_flow(fr):
    """(flow, pcp, src MAC) of an Ethernet frame (with or without FCS)."""
    tagged = fr[12:14] == b"\x81\x00"
    pcp = (fr[14] >> 5) if tagged else None
    for f, L in FRAME.items():
        if (FLOWS[f][1] is not None) == tagged and len(fr) in (L, L + 4):
            return f, pcp, fr[6:12]
    return None, pcp, fr[6:12]


def n3_gpdus(path):
    """(pdu type, IP src, IP dst, QFI, inner frame) for every GTP-U G-PDU."""
    out = []
    for _, p in read_pcap(path):
        i = p.find(b"\x00\x21\x45")          # PPP protocol IPv4, then IPv4 version/IHL
        if i < 0:
            continue
        ip = p[i + 2:]
        ihl, tot = (ip[0] & 0xF) * 4, struct.unpack(">H", ip[2:4])[0]
        if ip[9] != 17:
            continue
        g = ip[ihl + 8:tot]
        flags, mtype = g[0], g[1]
        if mtype != 255:
            continue
        pos, ptype, qfi = 8, None, 0
        if flags & 0x07:
            nxt, pos = g[11], 12
            while nxt != 0:
                ln = 4 * g[pos]
                if nxt == 0x85:
                    ptype, qfi = g[pos + 1] >> 4, g[pos + 2] & 0x3F
                pos += ln
                nxt = g[pos - 1]
        out.append((ptype, ip[12:16], ip[16:20], qfi, g[pos:]))
    return out


def judge_qfi(gpdus):
    """Q-UL and Q-DL (ok, detail) from N3 G-PDUs."""
    res = {}
    upf_ips = {s for t, s, _, _, _ in gpdus if t == 0}
    for key, ptype in (("Q-UL", 1), ("Q-DL", 0)):
        got, bad, unknown, pcpbad, dirbad = defaultdict(Counter), [], 0, 0, 0
        for t, s, dst, q, fr in gpdus:
            if t != ptype:
                continue
            if (ptype == 0 and s not in upf_ips) or (ptype == 1 and dst not in upf_ips):
                dirbad += 1
            f, pcp, _ = eth_flow(fr)
            if f is None:
                unknown += 1
                continue
            if pcp != FLOWS[f][1]:
                pcpbad += 1
            got[f][q] += 1
            if q != QFI[f]:
                bad.append((f, q))
        ok = not bad and not unknown and not pcpbad and not dirbad and set(got) == set(FLOWS) and len(upf_ips) == 1
        qs = Counter((f, q) for f, c in got.items() for q in c)
        summ = "; ".join(f"QFI {q}: " + ",".join(f for f in FLOWS if (f, q) in qs) for q in sorted({q for _, q in qs}))
        n = sum(sum(c.values()) for c in got.values())
        det = f"{n} G-PDUs (PDU type {ptype}); {summ}"
        if bad:
            det += f" | WRONG QFI: {sorted(Counter(bad).items())[:4]}"
        if unknown or pcpbad or dirbad:
            det += f" | unknown inner frames {unknown}, PCP/length mismatch {pcpbad}, direction mismatch {dirbad}"
        res[key] = (ok, det)
    return res


def run_rows(d, seed, pcapdir):
    """All Q and D rows of one run: {key: (ok, detail)}."""
    r = {}
    if pcapdir:
        r.update(judge_qfi(n3_gpdus(os.path.join(pcapdir, "M1Bridge.upf.pcapRecorder[0].pcap"))))
    for key in D_ROWS:
        mat, unm, _ = drb_matrix(d, seed, key)
        r[key] = judge_drb(mat, unm)
    return r


def sink_samples(d, seed):
    out = {}
    for mod in ("listener.app[9].sink", "talker.app[9].sink"):
        x = d[(d.seed == seed) & (d.type == "vector") & (d["mod"] == mod)]
        out[mod] = {n: v for n, v in zip(x.name, x.vecvalue)}
    return out


# --- main runs: Config S3, all seeds -------------------------------------------------
s3 = load(os.path.join(OUT, "seeds.csv"))
seeds = sorted(int(x) for x in s3.seed.unique())
logs = sorted(glob.glob(os.path.join(OUT, "run-*.log")))
add("run: S3 seeds and seed-0 control/negative runs",
    f"S3 seeds {seeds}; {len(logs)} logs, no errors",
    len(seeds) > 0 and all("<!> Error" not in open(f).read() for f in logs))

for key in D_ROWS:
    results = [judge_drb(*drb_matrix(s3, s, key)[:2]) for s in seeds]
    add(f"DRB {key}: every flow on its intended DRB only ({len(seeds)} seeds)",
        results[0][1] + ("" if all(ok for ok, _ in results) else
                         f" | failing seeds {[s for s, (ok, _) in zip(seeds, results) if not ok]}"),
        all(ok for ok, _ in results))

# accounting
acc_bad, acc_n, inflight, at_end = [], 0, Counter(), [0]
END = 5.0                                     # sim-time-limit
for s in seeds:
    for dirn, src, snk, tx_key, rx_key in (("UL", "talker", "listener", "D-UL-tx", "D-UL-rx"),
                                           ("DL", "listener", "talker", "D-DL-tx", "D-DL-rx")):
        tx = sum((c for c in drb_matrix(s3, s, tx_key)[0].values()), Counter())
        rx = sum((c for c in drb_matrix(s3, s, rx_key)[0].values()), Counter())
        lens = vecs(s3, s, lambda m, snk=snk: m == f"{snk}.app[9].sink", "packetLengths:vector")
        recv = Counter()
        for v in lens.get(f"{snk}.app[9].sink", []):
            L = int(v) // 8
            recv.update(f for f in FLOWS if SINKLEN[f] == L)
        sent_v = vecs(s3, s, lambda m, src=src: m.startswith(src + ".app["), "packetSent:vector(packetBytes)", times=True)
        for f in FLOWS:
            # a frame generated at the very end of the run (t = 5 s) cannot have reached
            # the RLC yet; only frames sent at least 10 us before the end are accounted
            tv = sent_v.get(f"{src}.app[{APP[f]}].io", [])
            sent = sum(1 for t, _ in tv if t < END - 10e-6)
            at_end[0] += sum(1 for t, _ in tv if t >= END - 10e-6)
            acc_n += 1
            infl = tx[f] - rx[f]
            inflight[infl] += 1
            if sent != tx[f] or rx[f] != recv[f] or not 0 <= infl <= 3:
                acc_bad.append((s, dirn, f, sent, tx[f], rx[f], recv[f]))
add("functional: accounting sent = RLC TX in, RLC RX out = received, in flight 0..3",
    f"{acc_n} (seed, direction, flow) triples; in-flight distribution {dict(sorted(inflight.items()))}; "
    f"{at_end[0]} frames generated at t = 5 s not counted; "
    f"mismatches {len(acc_bad)}" + (f" e.g. {acc_bad[:3]}" if acc_bad else ""),
    not acc_bad)

# SDAP header presence, from SDU size offsets
offs = defaultdict(set)
for s in seeds:
    for key in D_ROWS:
        for drb, o in drb_matrix(s3, s, key)[2].items():
            offs[drb] |= o
ok = (all(len(o) == 1 for o in offs.values()) and set(offs) == {1, 2, 3}
      and min(offs[1]) == min(offs[2]) + 1 == min(offs[3]) + 1)
add("protocol: SDU size - frame size per DRB (SDAP header only on default DRB)",
    "; ".join(f"DRB {k}: {sorted(v)} B" for k, v in sorted(offs.items())), ok)

# --- Config S3-pcap, seed 0 ----------------------------------------------------------
ctl = {c: load(os.path.join(OUT, f"ctl-{c}.csv")) for c in ["S3-pcap"] + list(NEG)}
pdir = lambda c: os.path.join(OUT, "ctl", c, "pcap")
main = run_rows(ctl["S3-pcap"], 0, pdir("S3-pcap"))
for key in ("Q-UL", "Q-DL"):
    ok, det = main[key]
    add(f"QFI {key}: N3 G-PDUs carry the intended QFI (S3-pcap, seed 0)", det, ok)
for key in D_ROWS:
    ok, det = main[key]
    add(f"DRB {key} in S3-pcap (seed 0)", det, ok)

# transit through the 5G system, at the translators' 5G-side ports
ds = read_pcap(os.path.join(pdir("S3-pcap"), "M1Bridge.dsTt.pcapRecorder[0].pcap"))
nw = read_pcap(os.path.join(pdir("S3-pcap"), "M1Bridge.nwTt.pcapRecorder[0].pcap"))
talker_mac = ds[0][1][6:12]          # first frame of the run: talker's app[0] at 0.1 s
for dirn, enter, leave, src_is_talker in (("UL", ds, nw, True), ("DL", nw, ds, False)):
    per_in, per_out = defaultdict(list), defaultdict(list)
    for lst, per in ((enter, per_in), (leave, per_out)):
        for _, fr in lst:
            f, _, src = eth_flow(fr)
            if (src == talker_mac) == src_is_talker:
                per[f].append(fr)
    bad = [f for f in FLOWS if not per_out[f] or not 0 <= len(per_in[f]) - len(per_out[f]) <= 3
           or any(a != b for a, b in zip(per_in[f], per_out[f]))]
    tags = {f: sorted({(fr[14] >> 5, ((fr[14] & 0xF) << 8) | fr[15]) for fr in per_out[f]}) if FLOWS[f][1] is not None
            else "untagged" for f in FLOWS}
    tag_ok = all(tags[f] == ("untagged" if FLOWS[f][1] is None else [(FLOWS[f][1], 42)]) for f in FLOWS)
    add(f"protocol: {dirn} frames leave the 5G system byte-identical (PCP, VLAN 42, payload, FCS)",
        f"{sum(len(v) for v in per_out.values())} frames out, {sum(len(v) for v in per_in.values())} in; "
        f"flows failing: {bad or 'none'}; (PCP, VID) out as intended: {tag_ok}",
        not bad and None not in per_in and tag_ok)

# control: PCAP settings change nothing
a, b = sink_samples(s3, 0), sink_samples(ctl["S3-pcap"], 0)
add("control: S3-pcap delay samples == S3 (seed 0)",
    "fcsMode/checksumMode=computed and PCAP recorders change no sample", a == b and all(a.values()))

# --- negative controls ----------------------------------------------------------------
for c, expect_fail in NEG.items():
    r = run_rows(ctl[c], 0, pdir(c))
    failed = {k for k, (ok, _) in r.items() if not ok}
    extra = ""
    ok = failed == expect_fail
    if c == "S3-neg-absent":
        same = sink_samples(ctl[c], 0) == sink_samples(ctl["S3-pcap"], 0)
        ok = ok and same
        extra = f"; delay samples bit-identical to S3-pcap: {same}"
    details = " / ".join(f"{k}: {r[k][1].split(' | ')[-1] if not r[k][0] else 'pass'}" for k in sorted(failed)) or "no row fails"
    add(f"negative: {c} fails exactly {sorted(expect_fail) or 'nothing'}",
        f"failed {sorted(failed) or 'nothing'}{extra} | {details}", ok)

# --- experimental: per-flow delivery and delay (recorded, no pass/fail) --------------
def flow_table(d, sds, label):
    lines = [f"{label}, seeds {sds[0]}..{sds[-1]}; delay = meanBitLifeTimePerPacket at the sink, all packets pooled;",
             "CI = 1.96 sd / sqrt(n) (packets are not independent: indicative only); delivered = received / sent.",
             "dir  flow      DRB  sent    recv    delivered  mean [ms]  CI [ms]   p95 [ms]   max [ms]"]
    for dirn, src, snk in (("UL", "talker", "listener"), ("DL", "listener", "talker")):
        per, sent = defaultdict(list), Counter()
        for s in sds:
            m = f"{snk}.app[9].sink"
            L = vecs(d, s, lambda x, m=m: x == m, "packetLengths:vector").get(m, [])
            D = vecs(d, s, lambda x, m=m: x == m, "meanBitLifeTimePerPacket:vector").get(m, [])
            for l, dly in zip(L, D):
                for f in FLOWS:
                    if SINKLEN[f] == int(l) // 8:
                        per[f].append(dly)
            for f in FLOWS:
                tv = vecs(d, s, lambda x, f=f: x == f"{src}.app[{APP[f]}].io", "packetSent:vector(packetBytes)", times=True)
                sent[f] += sum(1 for t, _ in tv.get(f"{src}.app[{APP[f]}].io", []) if t < END - 10e-6)
        for f in FLOWS:
            x = sorted(per[f])
            n = len(x)
            mu = sum(x) / n
            sd = math.sqrt(sum((v - mu) ** 2 for v in x) / (n - 1))
            lines.append(f"{dirn:<4} {f:<9} {DRB[f]:<4} {sent[f]:<7} {n:<7} {n / sent[f]:<10.3f} {mu*1e3:<10.3f} "
                         f"{1.96*sd/math.sqrt(n)*1e3:<9.3f} {x[int(0.95 * (n - 1))]*1e3:<10.3f} {x[-1]*1e3:.3f}")
    return "\n".join(lines) + "\n"


text = flow_table(s3, seeds, "Config S3 (light load)")
# Config S3-load: the same flows plus the background flow app[10] (PCP 0, 1400 B)
ld = load(os.path.join(OUT, "load.csv"))
lseeds = sorted(int(x) for x in ld.seed.unique())
FLOWS["bg"], APP["bg"], QFI["bg"], DRB["bg"] = (1400, 0), 10, 0, 1
FRAME["bg"], SINKLEN["bg"] = 14 + 4 + 1400, 1400 + 4
for key in D_ROWS:
    res = [judge_drb(*drb_matrix(ld, s, key)[:2]) for s in lseeds]
    add(f"DRB {key} under saturating load (S3-load, {len(lseeds)} seeds)",
        res[0][1] + ("" if all(ok for ok, _ in res) else
                     f" | failing seeds {[s for s, (ok, _) in zip(lseeds, res) if not ok]}"),
        all(ok for ok, _ in res))
text += "\n" + flow_table(ld, lseeds, "Config S3-load (+ background flow 'bg': PCP 0, 1400 B every 0.25 ms, each direction)")
open(os.path.join(OUT, "experimental.txt"), "w").write(text)

# --- print ---------------------------------------------------------------------------
w = max(len(r[0]) for r in rows)
for c, det, verdict in rows:
    print(f"{verdict:4}  {c:<{w}}  {det}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
