#!/usr/bin/env python3
"""M2-S0 checker: chunk-level TtTimestampTag across the Ethernet - 5G - Ethernet bridge.
Usage: check_m2s0.py <results/M2-S0>   (output of m2s0.sh)

Independent evidence: PCAP (pcapng, 1 ps resolution) at both stations, both ports of both
translators and N3; recorded statistics. The translators' own logs are only joined to
PCAP by payload identity (EtherType, PCP, VID, FNV-1a 64 of the payload bytes, which
the checker recomputes from the captured bytes). All times are integer picoseconds.

Ingress event (the timestamp definition under test): the translator's TSN-side port
(eth[1]) RX path, measurement-layer slot, in the same call in which that port's PHY
receiver emits receptionEnded (the PCAP inbound record: INET PcapRecorder default
receivingSignalNames) and pushes the frame up through PHY and MAC, i.e. at the end of
reception of the frame's last bit. (Corrected 2026-10-13: earlier text named the MAC
signal packetReceivedFromLower; values and verdicts are unaffected.) Expected relations, both exact (no tolerance):
  ingressTime == PCAP inbound time at TT eth[1]
  PCAP inbound time at TT eth[1] == PCAP outbound time at the sending station + 50 ns
  (cable 10 m at 2e8 m/s; PCAP records an outbound frame at transmissionEnded, the end of
  its transmission)
Recovery event: the opposite translator's eth[1] TX path, measurement-layer slot (above
the MAC queue), expected in the same event as the frame's reception on that
translator's 5G-side port eth[0] (PCAP inbound there).
"""
import csv
import os
import struct
import sys
from collections import Counter, defaultdict

import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcapng  # noqa: E402

OUT = sys.argv[1]
RUNS = os.path.join(OUT, "runs")
PS = 1
NS = 1000 * PS
MS = 1000 * 1000 * NS
S = 1000 * MS
END = 5 * S
PROP = 50 * NS
TT_ID = {"nwTt": 1, "dsTt": 2}
# direction: (TT_in, TT_out, source station, destination station)
DIRS = {"DL": ("nwTt", "dsTt", "listener", "talker"), "UL": ("dsTt", "nwTt", "talker", "listener")}
rows = []


def add(check, detail, ok, target=None):
    rows.append({"check": check, "detail": detail, "ok": bool(ok), "target": target})


def fmt_ns(ps):
    return f"{ps / NS:.3f} ns"


# ---------------------------------------------------------------------------------------
# loading
class Run:
    def __init__(self, config, rep=0):
        self.config, self.rep = config, rep
        base = os.path.join(RUNS, config)
        self.pdir = os.path.join(base, "pcap", f"{config}-{rep}")
        self.ldir = os.path.join(base, "m2log", f"{config}-{rep}")
        self._pcap = {}

    def pcap(self, node, idx=0):
        key = (node, idx)
        if key not in self._pcap:
            self._pcap[key] = pcapng.read(os.path.join(self.pdir, f"M1Bridge.{node}.pcapRecorder[{idx}].pcapng"))
        return self._pcap[key]

    def eth(self, node, idx, direction):
        """Ethernet frames of one PCAP file in one direction: list of (t_ps, key, frame dict, raw)."""
        res = []
        for p in self.pcap(node, idx):
            if p["dir"] != direction:
                continue
            f = pcapng.ethernet(p["data"])
            res.append((p["t_ps"], ident(f), f, p["data"]))
        return res

    def log(self, node, port, role):
        path = os.path.join(self.ldir, f"M1Bridge.{node}.eth[{port}].measurementLayer.{role}.csv")
        if not os.path.exists(path):
            return None
        with open(path) as fh:
            return [r for r in csv.DictReader(fh) if r["event"] != "selftest"]

    def selftest(self):
        out = []
        for name in sorted(os.listdir(self.ldir)) if os.path.isdir(self.ldir) else []:
            with open(os.path.join(self.ldir, name)) as fh:
                out += [(name, r["note"]) for r in csv.DictReader(fh) if r["event"] == "selftest"]
        return out


def ident(f):
    return (f["etherType"], f["pcp"], f["vid"], pcapng.fnv1a64(f["payload"]))


def lident(r):
    return (int(r["etherType"]), int(r["pcp"]), int(r["vid"]), r["payloadHash"])


def kind(key, f=None):
    if key[0] == 0x88F7:
        return "gptp-" + {0: "Sync", 2: "PdelayReq", 3: "PdelayResp", 8: "FollowUp", 10: "PdelayRespFollowUp"}.get(
            f["payload"][0] & 0x0F if f else -1, "other")
    return f"pcp{key[1]}" if key[1] >= 0 else "untagged"


_csv = {}


def stats(config):
    if config not in _csv:
        d = pd.read_csv(os.path.join(RUNS, config + ".csv"), low_memory=False)
        d = d[d.run.notna()].copy()
        d["rep"] = d.run.str.extract(r"-(\d+)-\d{8}-")[0].astype(int)
        d["mod"] = d.module.fillna("").str.replace("M1Bridge.", "", regex=False)
        _csv[config] = d
    return _csv[config]


def vec(config, rep, mod, name):
    d = stats(config)
    r = d[(d.type == "vector") & (d.rep == rep) & (d["mod"] == mod) & (d.name == name)]
    if len(r) != 1 or not isinstance(r.vectime.iloc[0], str):
        return []
    return list(zip(map(float, r.vectime.iloc[0].split()), map(float, r.vecvalue.iloc[0].split())))


def scalar(config, rep, mod, name):
    d = stats(config)
    r = d[(d.type == "scalar") & (d.rep == rep) & (d["mod"] == mod) & (d.name == name)].value
    return float(r.iloc[0]) if len(r) == 1 else float("nan")


# ---------------------------------------------------------------------------------------
# per-direction analysis of one run
def analyse(run, dname):
    tin, tout, src, dst = DIRS[dname]
    res = {"name": dname, "problems": defaultdict(list)}
    pin = run.eth(tin, 1, pcapng.INBOUND)       # TT_in TSN port reception = ingress event
    srcout = run.eth(src, 0, pcapng.OUTBOUND)   # sending station
    out0 = run.eth(tout, 0, pcapng.INBOUND)     # TT_out 5G-side port reception = recovery event
    out1 = run.eth(tout, 1, pcapng.OUTBOUND)    # TT_out TSN port transmission
    dstin = run.eth(dst, 0, pcapng.INBOUND)     # receiving station
    for name, lst in (("TT_in eth[1]", pin), ("source station", srcout), ("TT_out eth[0]", out0),
                      ("TT_out eth[1]", out1), ("destination station", dstin)):
        keys = [k for _, k, _, _ in lst]
        if len(keys) != len(set(keys)):
            res["problems"]["A1"].append(f"ambiguous identity in {name} PCAP")
        bad = [f for _, _, f, _ in lst if not f["fcs_ok"]]
        if bad:
            res["problems"]["A1"].append(f"{len(bad)} frames with bad FCS in {name} PCAP")
    P = {k: (t, f) for t, k, f, _ in pin}
    SRC = {k: t for t, k, _, _ in srcout}
    O0 = {k: t for t, k, _, _ in out0}
    O1 = {k: t for t, k, _, _ in out1}
    D = {k: t for t, k, _, _ in dstin}
    order = {k: i + 1 for i, (_, k, _, _) in enumerate(sorted(pin, key=lambda x: x[0]))}
    ing = run.log(tin, 1, "ingress") or []
    egr = run.log(tout, 1, "egress") or []
    T = {}
    for r in ing:
        k = lident(r)
        if k in T:
            res["problems"]["A1"].append("duplicate ingress log identity")
        T[k] = r
    E = {}
    for r in egr:
        k = lident(r)
        if k in E:
            res["problems"]["A1"].append("duplicate egress log identity")
        E[k] = r
    res.update(n_in=len(P), n_tag=sum(1 for r in ing if r["event"] == "tag"), n_pass=sum(1 for r in ing if r["event"] == "pass"),
               n_del=len(E), n_rec=sum(1 for r in egr if r["event"] == "recover"),
               ev_egress=Counter(r["event"] for r in egr), n_out1=len(O1), n_dst=len(D))
    # --- A1: tagging complete; delivered = observed at TT_out eth[0]; exact recovery
    if set(T) != set(P):
        res["problems"]["A1"].append(f"ingress log vs TT_in eth[1] PCAP: {len(set(T) - set(P))} extra, {len(set(P) - set(T))} missing")
    if res["n_pass"]:
        res["problems"]["A1"].append(f"{res['n_pass']} frames not tagged at ingress")
    if set(E) != set(O0):
        res["problems"]["A1"].append(f"egress log vs TT_out eth[0] PCAP: {len(set(E) - set(O0))} extra, {len(set(O0) - set(E))} missing")
    foreign = [k for k in E if k not in T]
    if foreign:
        res["problems"]["A1"].append(f"{len(foreign)} delivered frames never seen at ingress")
    perframe = {}
    for k, r in E.items():
        ok = {"A1": True, "A2": True, "A3": True, "A4": True}
        t_ = T.get(k)
        if r["event"] != "recover":
            ok["A1"] = False
            res["problems"]["A1"].append(f"egress event {r['event']}")
        elif t_ is None or t_["event"] != "tag" or (r["frameId"], r["ingressTime"], r["ingressTtId"]) != (t_["frameId"], t_["ingressTime"], t_["ingressTtId"]):
            ok["A1"] = False
            res["problems"]["A1"].append("recovered values differ from the values set at ingress")
        if r["event"] == "recover" and k in P and k in O0:
            ti = pcapng.simtime_ps(r["ingressTime"])
            te = pcapng.simtime_ps(r["t"])
            dev2 = ti - P[k][0]
            if dev2 != 0:
                ok["A2"] = False
                res["problems"]["A2"].append(dev2)
            if int(r["frameId"]) != order[k] or int(r["ingressTtId"]) != TT_ID[tin]:
                ok["A3"] = False
                res["problems"]["A3"].append("recovered frame id / translator id does not match the PCAP arrival ordinal / TT_in")
            if te != O0[k]:
                ok["A4"] = False
                res["problems"]["A4"].append(f"recovery event at {fmt_ns(te - O0[k])} from TT_out eth[0] reception")
            dev4 = (te - ti) - (O0[k] - P[k][0])
            if dev4 != 0:
                ok["A4"] = False
                res["problems"]["A4"].append(dev4)
            res.setdefault("residence", []).append(te - ti)
            if k in O1:
                res.setdefault("egress_tx", []).append(O1[k] - te)
        else:
            ok = {a: False for a in ok}
        perframe[k] = ok
    res["perframe"] = perframe
    # --- A2 on all tagged frames (also those not delivered) and the PCAP-PCAP relation
    for k, r in T.items():
        if r["event"] == "tag" and k in P:
            d = pcapng.simtime_ps(r["ingressTime"]) - P[k][0]
            if d:
                res["problems"]["A2"].append(d)
    rel = Counter((P[k][0] - SRC[k]) if k in SRC else None for k in P)
    res["pcap_rel"] = rel
    if set(rel) != {PROP}:
        res["problems"]["A2"].append(f"TT_in eth[1] reception - station transmission: {dict(rel)} ps")
    # --- A3 on all tagged frames: ids = arrival ordinal, consecutive, unique; TT id
    ids = [(order[k], int(r["frameId"]), int(r["ingressTtId"])) for k, r in T.items() if r["event"] == "tag" and k in order]
    bad3 = [x for x in ids if x[0] != x[1] or x[2] != TT_ID[tin]]
    if bad3:
        res["problems"]["A3"].append(f"{len(bad3)} of {len(ids)} ingress ids differ from the arrival ordinal (first: ordinal {bad3[0][0]} id {bad3[0][1]} tt {bad3[0][2]})")
    if len({x[1] for x in ids}) != len(ids):
        res["problems"]["A3"].append("duplicate frame ids at ingress")
    # --- loss accounting: tagged at ingress, never delivered to TT_out
    lost = [k for k in T if k not in E]
    late = [k for k in lost if P.get(k, (0,))[0] >= END - 100 * MS]
    leaked = [k for k in lost if k in O0 or k in O1 or k in D]
    res.update(lost=len(lost), lost_late=len(late), lost_early=len(lost) - len(late),
               lost_kinds=Counter(kind(k, P[k][1]) for k in lost if k in P))
    if leaked:
        res["problems"]["A1"].append(f"{len(leaked)} frames counted lost but seen downstream")
    # delivered frames continue unchanged: TT_out eth[1] and the destination station
    queued = [k for k in E if k not in O1]
    if any(k not in E for k in O1) or set(O1) != set(D):
        res["problems"]["A1"].append("TT_out eth[1] / destination station PCAP inconsistent with the egress log")
    res["queued_at_end"] = len(queued)
    res["kinds"] = Counter(kind(k, P[k][1]) for k in E if k in P)
    res["P"], res["E"], res["order"] = P, E, order
    for a in ("A2", "A3", "A4"):
        if not any(r["event"] == "recover" for r in egr):
            res["problems"][a].append("no recovered frame")
    return res


def verdicts(res):
    return {a: not res["problems"][a] for a in ("A1", "A2", "A3", "A4")}


def describe(res, a):
    p = res["problems"][a]
    nums = Counter(x for x in p if isinstance(x, int))
    txt = Counter(x for x in p if not isinstance(x, int))
    parts = [f"{v}x {k}" for k, v in txt.items()]
    if nums:
        parts.append("deviations " + ", ".join(f"{fmt_ns(k)} x{v}" for k, v in sorted(nums.items())))
    return "; ".join(parts) if parts else "none"


def summary(res):
    return (f"{res['name']}: {res['n_in']} received at TT_in, {res['n_tag']} tagged, {res['n_del']} delivered to TT_out "
            f"({res['n_rec']} recovered exactly), lost before delivery {res['lost']} "
            f"({res['lost_late']} entered in the last 100 ms; {res['lost_early']} earlier)")


# ---------------------------------------------------------------------------------------
# RLC replay (method of simulations/m1/check/check_o_tail.py): which SDUs were cut
def replay(sdus, pdus):
    """Returns (indices of SDUs cut, {SDU index: time its last byte left the TX RLC}, indices still queued)."""
    q, i, cut, done = [], 0, [], {}
    for t, s in pdus:
        while i < len(sdus) and sdus[i][0] <= t:
            q.append([i, int(sdus[i][1]), 0])
            i += 1
        if not q:
            return None
        h, s = q[0], int(s)
        if h[2] == 0:
            pay = h[1] if s == h[1] + 1 else s - 2
            if pay < h[1]:
                cut.append(h[0])
        else:
            pay = s - 4
        h[2] += pay
        if h[2] >= h[1]:
            q.pop(0)
            done[h[0]] = t
    left = [x[0] for x in q] + list(range(i, len(sdus)))
    return cut, done, left


def rlc_cuts(config, rep, res_by_dir):
    """Per TX RLC entity (direction, DRB): replay, and map SDUs to frames by their order on
    the DRB (FIFO from the TT_in TSN port to the TX RLC); the mapping is accepted only if
    SDU size - frame size is one constant for all SDUs."""
    d = stats(config)
    mods = sorted(set(d[(d.rep == rep) & d["mod"].str.contains("-um-") & d["mod"].str.endswith(".tx")]["mod"]))
    out = {}
    for m in mods:
        node = "DL" if m.startswith("gnb1.") else "UL"
        drb = int(m.split(".")[-2].rsplit("-", 1)[1])
        sdus = vec(config, rep, m, "receivedPacketFromUpperLayer:vector(packetBytes)")
        pdus = vec(config, rep, m, "sentPduSize:vector")
        r = replay(sdus, pdus)
        res = res_by_dir[node]
        on_drb = [k for k, _ in sorted(res["P"].items(), key=lambda x: x[1][0])
                  if (2 if k[1] == 5 else 1) == drb]
        sizes = Counter(int(s) - (len(res["P"][k][1]["payload"]) + (18 if k[1] >= 0 else 14))
                        for (t, s), k in zip(sdus, on_drb))
        if r is None or len(sizes) != 1 or len(sdus) > len(on_drb):
            out[(node, drb)] = {"ok": False, "why": f"replay/mapping inconsistent (size offsets {dict(sizes)})"}
            continue
        cut, done, left = r
        out[(node, drb)] = {"ok": True, "sdus": len(sdus), "cut": len(cut), "frames": [on_drb[j] for j in cut],
                            "hdr": next(iter(sizes)), "done": {on_drb[j]: t for j, t in done.items()},
                            "left": {on_drb[j] for j in left}, "mapped": set(on_drb[:len(sdus)])}
    return out


def attribute_losses(rd, rc):
    """Where each frame tagged at ingress but never delivered to TT_out was at the end."""
    out = {}
    for dname, r in rd.items():
        cat = Counter()
        for k in r["P"]:
            if k in r["E"]:
                continue
            drb = 2 if k[1] == 5 else 1
            v = rc.get((dname, drb))
            t_in = r["P"][k][0]
            if v is None or not v["ok"]:
                cat["unattributed"] += 1
            elif k not in v["mapped"]:
                cat["not yet at the TX RLC (entered in the last 10 ms)" if t_in >= END - 10 * MS else "never reached the TX RLC"] += 1
            elif k in v["left"]:
                cat["still in the TX RLC at the end"] += 1
            elif v["done"][k] * S >= END - 10 * MS:
                cat["left the TX RLC in the last 10 ms (in flight)"] += 1
            else:
                cat["left the TX RLC, never delivered (MAC/radio)"] += 1
        out[dname] = cat
    return out


LOST_MAC = "left the TX RLC, never delivered (MAC/radio)"
BENIGN = {"not yet at the TX RLC (entered in the last 10 ms)", "still in the TX RLC at the end",
          "left the TX RLC in the last 10 ms (in flight)"}


# ---------------------------------------------------------------------------------------
# evaluation
def evaluate(config, rep, tag=""):
    run = Run(config, rep)
    return run, {d: analyse(run, d) for d in DIRS}


def audit(run):
    tagged, frames = 0, 0
    for node in ("talker", "listener"):
        for role in ("ingress", "egress"):
            lg = run.log(node, 0, role)
            if lg is None:
                return None
            frames += len(lg)
            tagged += sum(1 for r in lg if r["note"] != "allLevelTags=0" or r["regions"] != "0")
    return frames, tagged


def audit_counts_match(run):
    ok = True
    for node in ("talker", "listener"):
        n_in = sum(1 for p in run.pcap(node) if p["dir"] == pcapng.INBOUND)
        n_out = sum(1 for p in run.pcap(node) if p["dir"] == pcapng.OUTBOUND)
        lin, lout = run.log(node, 0, "ingress"), run.log(node, 0, "egress")
        ok &= len(lin) == n_in and len(lout) >= n_out   # TX: frames still queued at the end are logged, not captured
    return ok


# ---- S: structure at the insertion points, and the self-test --------------------------
census, sig_ok, counts_ok = Counter(), True, True
for cfg in ("M2S0-probe", "M2S0-probe-frag", "M2S0-probe-load"):
    run = Run(cfg, 0)
    for node, port in (("nwTt", 1), ("dsTt", 1), ("talker", 0), ("listener", 0)):
        for role in ("ingress", "egress"):
            lg = run.log(node, port, role)
            for r in lg:
                sig_ok &= r["event"] == "probe" and r["note"] == "allLevelTags=0"
                s = r["signature"].split(": ", 1)[1]
                census[(f"{node}.eth[{port}] {'RX' if role == 'ingress' else 'TX'}",
                        r["signature"].split(" back=")[0], s)] += 1
            idx = 1 if node.endswith("Tt") else 0
            n_p = sum(1 for p in run.pcap(node, idx) if p["dir"] == (pcapng.INBOUND if role == "ingress" else pcapng.OUTBOUND))
            counts_ok &= (len(lg) == n_p) if role == "ingress" else (len(lg) >= n_p)
with open(os.path.join(OUT, "census.txt"), "w") as fh:
    fh.write("Chunk structure of every frame at the measurement-layer slots (M2S0-probe, -probe-frag, -probe-load, seed 0)\n")
    fh.write("count  slot  front offset  data-part chunks\n")
    for (slot, front, s), n in sorted(census.items()):
        fh.write(f"{n:6d}  {slot:20s} {front:9s} {s}\n")
kinds_seen = sorted({s for (_, _, s) in census})
add("S1 structure: every frame at every slot (translators' eth[1], stations' eth[0], RX and TX; base, N3 fragmentation, load) "
    "has the supported structure; no frame carries a tag in the probe runs",
    f"{sum(census.values())} frames, {len(kinds_seen)} distinct chunk structures (census.txt), RX data part starts after the "
    f"8 B PHY header (front offset 8 B), FCS chunk present in RX and TX, no EthernetPadding seen; probe frame counts = PCAP "
    f"counts at the same port: {counts_ok}", sig_ok and counts_ok and len(census) > 0)
st_rows = []
for cfg in ("M2S0-probe", "M2S0"):
    st_rows += Run(cfg, 0).selftest()
st_pass = sum(1 for _, n in st_rows if n.startswith("PASS"))
add("S2 self-test: structure check and tag round trip on synthetic frames (3 supported: tag covers payload, frame bytes "
    "unchanged, strip leaves no tag at any level; 7 unsupported: named error, processing stops with an error)",
    f"{st_pass}/{len(st_rows)} case runs PASS (10 cases x 2 processors x 2 runs)", st_pass == len(st_rows) == 40)

# ---- A1-A4 and A5 on M2S0 seeds 0-9 -----------------------------------------------------
agg = {d: Counter() for d in DIRS}
probs = {d: defaultdict(list) for d in DIRS}
cls = {d: defaultdict(lambda: [0, 0]) for d in DIRS}
cuts_total, cut_ok, cut_frames_n, rlc_problem = Counter(), True, 0, []
loss_cat = {d: Counter() for d in DIRS}
res_dirs, rel_all, res_range = {}, Counter(), {d: [] for d in DIRS}
for rep in range(10):
    run, rd = evaluate("M2S0", rep)
    res_dirs[rep] = rd
    for d, r in rd.items():
        for a in ("A1", "A2", "A3", "A4"):
            probs[d][a] += r["problems"][a]
        for f in ("n_in", "n_tag", "n_del", "n_rec", "lost", "lost_late", "lost_early", "queued_at_end"):
            agg[d][f] += r[f]
        rel_all.update(r["pcap_rel"])
        res_range[d] += r.get("residence", [])
        for k, ok in r["perframe"].items():
            c = kind(k, r["P"][k][1]) if k in r["P"] else "?"
            cls[d][c][0] += 1
            cls[d][c][1] += all(ok.values())
    rc = rlc_cuts("M2S0", rep, rd)
    for d, cat in attribute_losses(rd, rc).items():
        loss_cat[d].update(cat)
    for (d, drb), v in rc.items():
        if not v["ok"]:
            rlc_problem.append(f"seed {rep} {d} DRB {drb}: {v['why']}")
            continue
        cuts_total[(d, drb)] += v["cut"]
        for k in v["frames"]:
            if k in rd[d]["perframe"]:
                cut_frames_n += 1
                cut_ok &= all(rd[d]["perframe"][k].values())
for d in DIRS:
    a = agg[d]
    res_s = sorted(res_range[d])
    add(f"A1 recovery {d} (M2S0, seeds 0-9): every frame received at the TT_in TSN port is tagged once; every frame "
        "delivered to the opposite translator (= observed at its 5G-side port) is recovered with exactly the values set at "
        "ingress; frames lost before delivery counted separately",
        f"{a['n_in']} received, {a['n_tag']} tagged, {a['n_del']} delivered, {a['n_rec']} recovered exactly; not delivered "
        f"by the end of the run {a['lost']}: {dict(loss_cat[d])}; delivered but still queued at TT_out eth[1] at "
        f"the end: {a['queued_at_end']}; problems: {describe({'problems': probs[d]}, 'A1')}",
        not probs[d]["A1"] and a["n_rec"] == a["n_del"] > 0 and set(loss_cat[d]) <= BENIGN)
    add(f"A2 timestamp {d}: carried ingressTime = PCAP reception time at the TT_in TSN port, exactly (1 ps PCAP), for every "
        "tagged and every recovered frame",
        f"deviations: {describe({'problems': probs[d]}, 'A2')}", not probs[d]["A2"])
    add(f"A3 identity {d}: frame id = arrival ordinal at the TT_in TSN port (from PCAP), consecutive and unique, with the "
        "TT_in id; every recovered id belongs to the same frame",
        f"problems: {describe({'problems': probs[d]}, 'A3')}", not probs[d]["A3"])
    add(f"A4 residence {d}: recovery event = reception at TT_out's 5G-side port (PCAP) exactly; recovered residence "
        "(recovery - ingressTime) = PCAP(TT_out eth[0] in) - PCAP(TT_in eth[1] in) exactly",
        f"{len(res_s)} frames, residence {res_s[0] / MS:.6f} - {res_s[-1] / MS:.6f} ms; problems: "
        f"{describe({'problems': probs[d]}, 'A4')}" if res_s else "no frames", not probs[d]["A4"] and len(res_s) > 0)
add("A2b event boundary: PCAP reception at the TT_in TSN port - PCAP transmission at the sending station = 50 ns "
    "(propagation only) for every frame, both directions, seeds 0-9",
    f"differences: { {fmt_ns(k) if k is not None else 'not sent?': v for k, v in rel_all.items()} }", set(rel_all) == {PROP})
det5 = []
ok5 = True
for d in DIRS:
    det5.append(f"{d}: " + ", ".join(f"{c} {n}/{t}" for c, (t, n) in sorted(cls[d].items())))
    ok5 &= all(n == t and t > 0 for t, n in cls[d].values())
need = {"DL": {"pcp0", "pcp5", "gptp-Sync", "gptp-FollowUp", "gptp-PdelayResp", "gptp-PdelayRespFollowUp"},
        "UL": {"pcp0", "pcp5", "gptp-PdelayReq"}}
ok5 &= all(need[d] <= set(cls[d]) for d in DIRS)
add("A5 encapsulation/segmentation: A1-A4 hold per frame for every frame class (both DRBs: PCP 5 -> DRB 2, PCP 0 and gPTP "
    "-> DRB 1; every gPTP message type) and for every SDU the RLC replay identifies as cut and reassembled (seeds 0-9)",
    " | ".join(det5) + f" (frames passing A1-A4 / delivered) | RLC SDUs cut and reassembled: "
    f"{ {f'{d} DRB {b}': n for (d, b), n in sorted(cuts_total.items())} }, of which delivered {cut_frames_n}, all "
    f"passing A1-A4: {cut_ok}; replay problems: {rlc_problem or 'none'}",
    ok5 and cut_ok and cut_frames_n > 0 and not rlc_problem)


# ---- A6 fragmentation ---------------------------------------------------------------------
def n3_ipv4(run):
    """N3 (UPF ppp[0]) IPv4 packets: fragments, reassembled datagrams, unfragmented sizes."""
    frags, whole = defaultdict(int), []
    for p in run.pcap("upf", 0):
        b = p["data"]
        off = 5 if b[1:3] == b"\xff\x03" else 3
        if struct.unpack(">H", b[off - 2: off])[0] != 0x0021:
            continue
        ip = b[off:]
        ff = struct.unpack(">H", ip[6:8])[0]
        if (ff & 0x2000) or (ff & 0x1FFF):
            frags[(ip[12:16], ip[16:20], ip[4:6], ip[9])] += 1
        else:
            whole.append(struct.unpack(">H", ip[2:4])[0])
    return frags, whole


runf, rf = evaluate("M2S0-frag", 0)
rcf = rlc_cuts("M2S0-frag", 0, rf)
lf = attribute_losses(rf, rcf)
frags, whole = n3_ipv4(runf)
okf = all(verdicts(r)[a] for r in rf.values() for a in ("A1", "A2", "A3", "A4")) and all(r["n_rec"] > 0 for r in rf.values())
okf &= all(set(lf[d]) <= BENIGN for d in DIRS)
add("A6 byte fragmentation (M2S0-frag, N3 PPP MTU 128 B, seed 0): A1-A4 hold in both directions; N3 shows that every "
    "GTP-U datagram longer than the MTU was fragmented",
    " | ".join(summary(r) + f", not delivered: {dict(lf[d])}; A1-A4 {verdicts(r)}" for d, r in rf.items()) +
    f" | N3: {len(frags)} datagrams fragmented into {sum(frags.values())} fragments ({dict(Counter(frags.values()))} "
    f"fragments per datagram: count); {len(whole)} unfragmented, IPv4 total length {min(whole) if whole else '-'}-"
    f"{max(whole) if whole else '-'} B (<= 128 B: these are the gPTP frames)",
    okf and len(frags) > 0 and all(n >= 2 for n in frags.values()) and all(x <= 128 for x in whole))

# ---- A7 load ------------------------------------------------------------------------------
det7, ok7 = [], True
mac_lost = {}
for cfg in ("M2S0-load", "M2S0-load-harq16"):
    runl, rl = evaluate(cfg, 0)
    rcl = rlc_cuts(cfg, 0, rl)
    ll = attribute_losses(rl, rcl)
    mac_lost[cfg] = sum(ll[d][LOST_MAC] for d in DIRS)
    for d, r in rl.items():
        ok7 &= all(verdicts(r).values()) and r["n_rec"] > 0
        ok7 &= set(ll[d]) <= BENIGN | {LOST_MAC}
        det7.append(f"{cfg} " + summary(r) + f"; not delivered: {dict(ll[d])}; by class {dict(r['lost_kinds'])}; "
                    f"A1-A4 {verdicts(r)}")
add("A7 load (saturating PCP 0 background both directions, sources stop at 3 s, run to 5 s): every delivered frame passes "
    "A1-A4; frames not delivered are accounted for (RLC replay) and absent downstream, never delivered untagged or "
    "mis-tagged. 5 HARQ processes: frames lost after the TX RLC expected (L1); 16 HARQ processes: none",
    " | ".join(det7), ok7 and mac_lost["M2S0-load"] > 0 and mac_lost["M2S0-load-harq16"] == 0)


# ---- A8 wire unchanged, A9 no side effects -------------------------------------------------
def pcap_identical(a, b):
    da, db = Run(a, 0).pdir, Run(b, 0).pdir
    files = sorted(os.listdir(da))
    same = [f for f in files if os.path.exists(os.path.join(db, f)) and open(os.path.join(da, f), "rb").read() == open(os.path.join(db, f), "rb").read()]
    return files, same, sorted(os.listdir(db)) == files


def fcs_all_valid(cfg):
    run, n, bad = Run(cfg, 0), 0, 0
    for node, idx in (("talker", 0), ("listener", 0), ("nwTt", 0), ("nwTt", 1), ("dsTt", 0), ("dsTt", 1)):
        for p in run.pcap(node, idx):
            n += 1
            bad += not pcapng.ethernet(p["data"])["fcs_ok"]
    return n, bad


det8, ok8 = [], True
for a, b in (("M2S0", "M2S0-off"), ("M2S0-load", "M2S0-load-off")):
    files, same, sameset = pcap_identical(a, b)
    n, bad = fcs_all_valid(a)
    ok8 &= sameset and len(same) == len(files) == 7 and bad == 0
    det8.append(f"{a} vs {b}: {len(same)}/{len(files)} PCAP files byte-identical (stations, both translator ports, N3); "
                f"{n} Ethernet frames, FCS valid in {n - bad}")
add("A8 wire unchanged: PCAP files (frame bytes and ps timestamps; VLAN/PCP, EtherType, payload, N3 GTP-U incl. QFI) "
    "byte-identical with and without the tag layers", " | ".join(det8), ok8)


def stat_equal(a, b):
    da, db = stats(a), stats(b)
    da, db = da[da.rep == 0], db[db.rep == 0]
    ours = lambda m: ".measurementLayer" in m
    va = {(r.mod, r.name): (r.vectime, r.vecvalue) for r in da[da.type == "vector"].itertuples()}
    vb = {(r.mod, r.name): (r.vectime, r.vecvalue) for r in db[db.type == "vector"].itertuples()}
    sa = {(r.mod, r.name): r.value for r in da[da.type == "scalar"].itertuples() if not ours(r.mod)}
    sb = {(r.mod, r.name): r.value for r in db[db.type == "scalar"].itertuples() if not ours(r.mod)}
    vsame = sum(1 for k in va if k in vb and va[k] == vb[k])
    ssame = sum(1 for k in sa if k in sb and (sa[k] == sb[k] or (sa[k] != sa[k] and sb[k] != sb[k])))
    vours = sum(1 for k in va if ours(k[0]))
    return len(va), len(vb), vsame, len(sa), len(sb), ssame, vours


det9, ok9 = [], True
for a, b in (("M2S0", "M2S0-off"), ("M2S0-load", "M2S0-load-off")):
    nva, nvb, vs, nsa, nsb, ss, vo = stat_equal(a, b)
    ok9 &= nva == nvb == vs and nsa == nsb == ss and vo == 0 and nva > 0
    det9.append(f"{a} vs {b}: vectors {vs}/{nva} identical ({nvb} in control), scalars {ss}/{nsa} identical ({nsb} in "
                f"control; the tag layers' own scalars excluded)")
add("A9 no side effects: every recorded vector (application delays, gPTP, slave clock, per-DRB RLC/PDCP/MAC, ...) and "
    "scalar identical with and without the tag layers (seed 0)", " | ".join(det9), ok9)

# ---- A10 containment -----------------------------------------------------------------------
det10, ok10 = [], True
for cfg, reps in (("M2S0", range(10)), ("M2S0-frag", [0]), ("M2S0-load", [0]), ("M2S0-load-harq16", [0])):
    fr_, tg_ = 0, 0
    for rep in reps:
        run = Run(cfg, rep)
        a = audit(run)
        fr_ += a[0]
        tg_ += a[1]
        ok10 &= audit_counts_match(run)
        ok10 &= all(scalar(cfg, rep, f"{n}.eth[0].measurementLayer.{r}", "framesAuditTagged") == 0
                    for n in ("talker", "listener") for r in ("ingress", "egress"))
    ok10 &= tg_ == 0 and fr_ > 0
    det10.append(f"{cfg}: {fr_} frames audited at the stations, {tg_} with a tag")
add("A10 containment: no frame at either station (RX or TX) carries a TtTimestampTag at any chunk level; audit frame counts "
    "match the station PCAPs", " | ".join(det10), ok10)


# ---- negative controls -----------------------------------------------------------------------
def nc_rows(cfg):
    run, rd = evaluate(cfg, 0)
    out = {}
    for d, r in rd.items():
        for a, ok in verdicts(r).items():
            out[f"{a}-{d}"] = (ok, describe(r, a))
    a = audit(run)
    out["A10"] = (a[1] == 0, f"{a[1]} of {a[0]} station frames tagged")
    return out


NCS = {"M2S0-nc-noingress": {"A1-UL", "A2-UL", "A3-UL", "A4-UL"},
       "M2S0-nc-offset": {"A2-DL", "A4-DL"},
       "M2S0-nc-id": {"A3-DL"},
       "M2S0-nc-nostrip": {"A10"}}
for i, (cfg, target) in enumerate(NCS.items(), 1):
    r = nc_rows(cfg)
    failed = {k for k, (ok, _) in r.items() if not ok}
    info = "; ".join(f"{k}: {r[k][1]}" for k in sorted(failed))
    add(f"N{i} {cfg}: fails exactly {sorted(target)}", f"failed: {sorted(failed)} -- {info}", failed == target)

# ---- output -------------------------------------------------------------------------------
w = max(len(r["check"]) for r in rows)
for r in rows:
    print(f"{'PASS' if r['ok'] else 'FAIL':4}  {r['check']}")
    print(f"      {r['detail']}")
print()
print("OVERALL:", "PASS" if all(r["ok"] for r in rows) else "FAIL", f"({sum(r['ok'] for r in rows)}/{len(rows)})")
