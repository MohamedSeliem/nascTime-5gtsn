#!/usr/bin/env python3
"""M1-S2 checker: pass-through NW-TT and DS-TT vs S1.

Criteria (migration/m1-plan.md, S2):
  run          all seeds of Config S2 and seed 0 of Config S2-pcap finished
  regression   (recorded separately) Config S1 still bit-identical to S0 with the TT
               wiring present but switched off
  functional   per-flow sent/received counts equal S1 for every seed
  protocol     PCAP on both ports of each TT (seed 0): in each direction the sequence of
               frames leaving a TT is byte-identical to the sequence entering it
               (MACs, 802.1Q tag with VLAN 42 and PCP, payload, FCS); a frame still
               inside the TT at the time limit is allowed
               TT residence (end of reception -> end of transmission) equals the
               frame's serialization time at 1 Gb/s, i.e. zero processing delay
  experimental per-packet delay(S2) - delay(S1) is the same constant for every packet,
               seed and direction, equal to ONE extra store-and-forward hop of
               (130 B on the wire at 1 Gb/s = 1040 ns) + (10 m cable = 50 ns) = 1090 ns:
               the hop of the translator AFTER the 5G system. The hop of the translator
               BEFORE the 5G system is absorbed, because the 5G system releases frames
               on 1 ms slot boundaries (next criterion).
               (The first prediction, 2180 ns = both hops, was wrong; see results/S2.md.)
  slot         PCAP (seed 0): in each direction frames enter the 5G system at one fixed
               offset within the 1 ms slot, and leave it at one fixed offset plus whole
               multiples of 1136 ns (frames released in the same slot, sent back to back:
               130 B + 12 B inter-frame gap at 1 Gb/s); entry offset + 1090 ns stays
               inside the slot
  control      Config S2-pcap (fcsMode=computed, recorders on) gives the same delay
               samples as Config S2 for seed 0
Usage: check_s2.py <results dir containing S1/ and S2/>
"""
import glob
import os
import struct
import sys

import pandas as pd

RES = sys.argv[1] if len(sys.argv) > 1 else "results"
OUT = os.path.join(RES, "S2")
rows = []
HOP = 130 * 8 / 1e9 + 10 / 2e8          # 1090 ns: one 1 Gb/s store-and-forward hop + 10 m cable
EXPECTED_EXTRA = HOP                     # post-5GS translator only (see docstring)
SLOT = 1e-3                              # NR numerology 0 slot (Simu5G default)
TOL = 1e-9


def add(check, detail, ok):
    rows.append((check, detail, "PASS" if ok else "FAIL"))


def load(path, net):
    d = pd.read_csv(path, low_memory=False)
    d = d[d.run.notna()].copy()
    d["seed"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
    d["mod"] = d.module.str.replace(net + ".", "", regex=False)
    return d


s1 = load(os.path.join(RES, "S1", "seeds.csv"), "M1Bridge")
s2 = load(os.path.join(OUT, "seeds.csv"), "M1Bridge")
pc = load(os.path.join(OUT, "pcaprun.csv"), "M1Bridge")

# --- run --------------------------------------------------------------------------
seeds = sorted(int(x) for x in s2.seed.unique())
logs_ok = all("<!> Error" not in open(os.path.join(OUT, f)).read()
              for f in ("run-S2-seeds.log", "run-S2-pcap.log"))
add("run: S2 seeds + S2-pcap", f"S2 seeds {seeds}; S2-pcap seeds {sorted(int(x) for x in pc.seed.unique())}",
    seeds == sorted(int(x) for x in s1.seed.unique()) and len(seeds) > 0 and logs_ok)

# --- functional: counts -------------------------------------------------------------
SRC = ["talker.app[0].source", "talker.app[1].source", "listener.app[0].source", "listener.app[1].source"]
SNK = ["listener.app[2].sink", "talker.app[2].sink"]


def count(d, seed, mod):
    v = d[(d.seed == seed) & (d.type == "scalar") & (d["mod"] == mod) & (d.name == "packets:count")].value
    return int(float(v.iloc[0])) if len(v) == 1 else None


mism = [(s, m, count(s1, s, m), count(s2, s, m)) for s in seeds for m in SRC + SNK
        if count(s1, s, m) != count(s2, s, m) or count(s2, s, m) is None]
add("functional: per-flow counts == S1", f"{len(seeds)} seeds x {len(SRC + SNK)} counters; mismatches: {len(mism)}",
    not mism)

# --- experimental: per-packet extra delay -------------------------------------------


def vec(d, seed, mod):
    r = d[(d.seed == seed) & (d.type == "vector") & (d["mod"] == mod) & (d.name == "meanBitLifeTimePerPacket:vector")]
    return [float(x) for x in r.vecvalue.iloc[0].split()] if len(r) == 1 else None


diffs = {"UL": [], "DL": []}
len_mism = []
for s in seeds:
    for mod, direction in [("listener.app[2].sink", "UL"), ("talker.app[2].sink", "DL")]:
        a, b = vec(s1, s, mod), vec(s2, s, mod)
        if a is None or b is None or len(a) != len(b):
            len_mism.append((s, direction, None if a is None else len(a), None if b is None else len(b)))
            continue
        diffs[direction] += [y - x for x, y in zip(a, b)]
for direction, dd in diffs.items():
    ok = bool(dd) and all(abs(x - EXPECTED_EXTRA) <= TOL for x in dd) and not len_mism
    add(f"experimental: {direction} delay(S2) - delay(S1)",
        f"{len(dd)} packets; min {min(dd)*1e9:.3f} ns, max {max(dd)*1e9:.3f} ns; predicted {EXPECTED_EXTRA*1e9:.0f} ns"
        if dd else "no samples", ok)
if len_mism:
    add("experimental: sample counts S2 vs S1", f"mismatches: {len_mism[:5]}", False)

# --- control: S2-pcap equals S2 (seed 0) --------------------------------------------
ctrl = all(vec(pc, 0, m) == vec(s2, 0, m) and vec(pc, 0, m) is not None for m in SNK)
add("control: S2-pcap delays == S2 (seed 0)", "fcsMode=computed and PCAP recorders change no delay sample", ctrl)

# --- protocol: PCAP ------------------------------------------------------------------


def read_pcap(path):
    b = open(path, "rb").read()
    magic = struct.unpack("<I", b[:4])[0]
    scale = 1e-9 if magic == 0xA1B23C4D else 1e-6
    off, out = 24, []
    while off < len(b):
        sec, frac, incl, _ = struct.unpack("<IIII", b[off:off + 16])
        off += 16
        out.append((sec + frac * scale, b[off:off + incl]))
        off += incl
    return out


pdir = os.path.join(OUT, "pcaprun", "pcap")
P = {os.path.basename(f)[len("M1Bridge."):-len(".pcap")]: read_pcap(f)
     for f in glob.glob(os.path.join(pdir, "*.pcap"))}
need = ["dsTt.pcapRecorder[0]", "dsTt.pcapRecorder[1]", "nwTt.pcapRecorder[0]", "nwTt.pcapRecorder[1]"]
if not all(k in P for k in need):
    add("protocol: PCAP files present", f"found {sorted(P)}", False)
else:
    # Two stations only. The first frame recorded on dsTt's TSN-side port is talker's
    # first transmission (talker's app[0] starts at 0.1 s; listener's frames reach the
    # dsTt only after crossing the 5G system), so its source MAC is talker's.
    srcs1 = {f[6:12] for _, f in P["dsTt.pcapRecorder[1]"]}
    talker_mac = P["dsTt.pcapRecorder[1]"][0][1][6:12]
    add("protocol: stations seen at the TTs", f"talker MAC {talker_mac.hex(':')}, {len(srcs1)} source MACs on dsTt TSN port",
        len(srcs1) == 2)

    def split(frames, src):
        return [(t, f) for t, f in frames if f[6:12] == src]

    other = [m for m in srcs1 if m != talker_mac][0]
    cases = [  # (tt, direction, ingress port, egress port, source MAC)
        ("dsTt", "UL", "dsTt.pcapRecorder[1]", "dsTt.pcapRecorder[0]", talker_mac),
        ("dsTt", "DL", "dsTt.pcapRecorder[0]", "dsTt.pcapRecorder[1]", other),
        ("nwTt", "UL", "nwTt.pcapRecorder[0]", "nwTt.pcapRecorder[1]", talker_mac),
        ("nwTt", "DL", "nwTt.pcapRecorder[1]", "nwTt.pcapRecorder[0]", other),
    ]
    for tt, direction, pin, pout, src in cases:
        fin, fout = split(P[pin], src), split(P[pout], src)
        n = len(fout)
        same = n > 0 and len(fin) - n in (0, 1) and all(fin[i][1] == fout[i][1] for i in range(n))
        tags = all(f[12:14] == b"\x81\x00" and (int.from_bytes(f[14:16], "big") & 0xFFF) == 42 for _, f in fin)
        pcps = sorted({int.from_bytes(f[14:16], "big") >> 13 for _, f in fin})
        add(f"protocol: {tt} {direction} frames unchanged",
            f"in {len(fin)}, out {n}; byte-identical in order: {same}; all VLAN 42: {tags}; PCPs {pcps}",
            same and tags and pcps == [0, 5])
        # residence: end of reception at ingress -> end of transmission at egress
        res = [fout[i][0] - fin[i][0] for i in range(n)]
        ser = [len(fout[i][1]) for i in range(n)]
        exp = [(L + 8) * 8 / 1e9 for L in ser]          # +8 B preamble/SFD on the wire
        ok = n > 0 and all(abs(r - e) <= TOL for r, e in zip(res, exp))
        add(f"protocol: {tt} {direction} residence == serialization",
            f"{n} frames; residence {min(res)*1e9:.1f}..{max(res)*1e9:.1f} ns; expected {min(exp)*1e9:.0f} ns (zero processing delay)",
            ok)

    # slot alignment of the 5G system: entry = TT port 0 egress, exit = TT port 0 ingress
    def offs(frames):
        return sorted({round((t % SLOT) * 1e9) for t, _ in frames})
    for direction, kin, kout, src in [("UL", "dsTt.pcapRecorder[0]", "nwTt.pcapRecorder[0]", talker_mac),
                                      ("DL", "nwTt.pcapRecorder[0]", "dsTt.pcapRecorder[0]", other)]:
        # port 0 carries both directions; entry frames are the ones the TT transmits towards
        # the 5G system (source = the station behind the TT), exit frames the other ones
        fin, fout = split(P[kin], src), split(P[kout], src)
        oi, oo = offs(fin), offs(fout)
        # frames released in the same slot leave back to back on the 1 Gb/s N6/UE link:
        # spacing = 130 B + 12 B inter-frame gap = 1136 ns
        b2b = round((130 + 12) * 8)
        ok = (len(oi) == 1 and oi[0] + HOP * 1e9 < SLOT * 1e9 and len(oo) >= 1
              and all((o - oo[0]) % b2b == 0 for o in oo))
        add(f"slot: {direction} 5G system entry/exit offsets in 1 ms slot",
            f"entry {oi} ns, exit {oo} ns ({len(fin)}/{len(fout)} frames); exit = slot offset + k x {b2b} ns "
            f"(back-to-back); entry + {HOP*1e9:.0f} ns stays in slot", ok)

# --- print ---------------------------------------------------------------------------
w = max(len(r[0]) for r in rows)
for c, det, verdict in rows:
    print(f"{verdict:4}  {c:<{w}}  {det}")
print()
print("OVERALL:", "PASS" if all(r[2] == "PASS" for r in rows) else "FAIL")
for m in mism[:10]:
    print("  count mismatch (seed, module, S1, S2):", m)
