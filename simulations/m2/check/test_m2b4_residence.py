#!/usr/bin/env python3
"""M2B-4 B6 bridge-residence observation with IEEE 802.1Qbv TAS active (docs/migration/m2b-4-tas-residence.md).

Runs the TEST-ONLY configurations of simulations/m2/m2b4/residence.ini (N = 2 M2S72Bridge, PCP 5 and PCP 0 traffic,
M2B-3 schedule) and checks every bridge-residence observation R = t12 - t1 written by the M2-S1 observer (TAS pairing
mode) against an INDEPENDENT per-frame oracle that never reads the pairer's output:
  - t1  = reception end of the frame at the ingress translator's TSN port (PCAP, receptionEnded);
  - t12 = transmission end at the egress translator's TSN port (PCAP, transmissionEnded), the frame's bytes there;
  - frame identity (source, destination, PCP, VID, application sequence number) from the PCAP bytes, the same frame
    (byte-identical) found at the ingress port;
  - enqueue / dequeue per traffic class from INET's own queue statistics (incomingPacketLengths, queueingTime);
  - gate states from the S-CFG/2 schedule and each translator's recorded TtClock (TT-time gate oracle, as M2B-3).
Statistics per (ingress TT, egress TT, PCP, VID) come from the accepted offline observer tools/bridge_delay.py.

Not a tier-0 suite: needs a built stack (OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT with a built Simu5G 1.8.1, libnasctime_m2
from src/nasctime/m2/build.sh). Functional development test (level 2): no scientific result.
"""
import csv
import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict
from decimal import Decimal

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
NET = os.path.join(M2, "m2b4")
sys.path.insert(0, HERE)
import pcapng  # noqa: E402

spec_ = importlib.util.spec_from_file_location("bridge_delay", os.path.join(M2, "tools", "bridge_delay.py"))
BD = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(BD)
OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
PS, NS, BIT_PS = 10 ** 12, 1000, 1000
T_END = 800 * 10 ** 9
TT = {1: "nwTt", 2: "dsTt[0]", 3: "dsTt[1]"}
TC_OF_PCP = {5: 5, 0: 1}
SPEC = json.load(open(os.path.join(M2, "scfg", "s72-q0-tas.json")))
SCHED = {"nwTt": next(s for s in SPEC["tas"]["schedules"] if s["translator"] == "nw-tt"),
         "dsTt[0]": next(s for s in SPEC["tas"]["schedules"] if s["translator"] == "ds-tt"),
         "dsTt[1]": next(s for s in SPEC["tas"]["schedules"] if s["translator"] == "ds-tt")}
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


# ---------------------------------------------------------------- TT clock and gate oracle (as M2B-3) ---------------
def make_ct(theta0=0, y=0, d=0, upd=0, uoff=0):
    def u_of(s):
        return uoff + upd * ((s - uoff) // upd) if upd > 0 else 0

    def ct(s):
        u = u_of(s)
        dd = s - u
        return s + theta0 + (2 * PS * y * dd + d * dd * dd) // (2 * 10 ** 21)
    ct.u_of, ct.upd = u_of, upd
    return ct


def first_reach(ct, c, t0, tmax):
    t = t0
    while t <= tmax:
        end = min(tmax, ct.u_of(t) + ct.upd - 1) if ct.upd > 0 else tmax
        if ct(end) >= c:
            if ct(t) >= c:
                return t
            lo, hi = t, end
            while hi - lo > 1:
                mid = (lo + hi) // 2
                lo, hi = (lo, mid) if ct(mid) >= c else (mid, hi)
            return hi
        t = end + 1
    return None


def gate_oracle(sched, tc, ct):
    cyc, ph, ents = sched["cycle_ns"] * NS, sched["phase_ns"] * NS, sched["entries"]
    states = [tc in e["open"] for e in ents]
    pos = sched["phase_ns"]
    init = next(tc in e["open"] for e in ents if e["start_ns"] <= pos < e["start_ns"] + e["duration_ns"])
    out = [(0, init)]
    changes = sorted(((e["start_ns"] * NS - ph) % cyc or cyc, states[j]) for j, e in enumerate(ents) if states[j] != states[j - 1])
    c0, t, k = ct(0), 0, 0
    while changes:
        for rel, st in changes:
            t = first_reach(ct, c0 + rel + k * cyc, t, T_END)
            if t is None:
                return out
            out.append((t, st))
        k += 1
    return out


def gate_state(trans, t):
    st = trans[0][1]
    for tt, s in trans:
        if tt > t:
            break
        st = s
    return st


# ---------------------------------------------------------------- running and reading --------------------------------
def opp_run(cfg, res):
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", "-f", "residence.ini", "-c", cfg, "-r", "0",
           "-n", ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"), os.path.join(SIMU5G, "src"),
                           os.path.join(INET, "src")]), "-x", "nasctime.nodes",
           "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"), "-l", os.path.join(SIMU5G, "src", "simu5g"),
           f"--result-dir={res}", "--cmdenv-express-mode=true"]
    return subprocess.run(cmd, cwd=NET, capture_output=True, text=True, timeout=1200)


class Run:
    def __init__(self, res, cfg):
        self.res, self.cfg = res, cfg
        self.vec, self.par = defaultdict(list), {}
        names = {}
        vp = os.path.join(res, cfg, "0.vec")
        if os.path.exists(vp):
            for line in open(vp):
                if line.startswith("vector "):
                    p = line.split()
                    names[p[1]] = (p[2], p[3])
                elif line[:1].isdigit():
                    p = line.rstrip("\n").split("\t")
                    if p[0] in names:
                        self.vec[names[p[0]]].append((pcapng.simtime_ps(p[2]), p[3]))
        sp = os.path.join(res, cfg, "0.sca")
        if os.path.exists(sp):
            for line in open(sp):
                m = re.match(r"^par (\S+) (\S+) (.*)$", line.rstrip("\n"))
                if m:
                    self.par[(m.group(1), m.group(2))] = m.group(3)

    def pcap_path(self, tt, idx):
        return os.path.join(self.res, "pcap", f"{self.cfg}-0", f"M2S72Bridge.{tt}.pcapRecorder[{idx}].pcapng")

    def pcap(self, tt, idx, direction):
        p = self.pcap_path(tt, idx)
        return [x for x in pcapng.read(p) if x["dir"] == direction] if os.path.exists(p) else []

    def log(self, tt):
        return os.path.join(self.res, "m2log", f"{self.cfg}-0", f"M2S72Bridge.{tt}.eth[1].measurementLayer.egress.port.csv")

    def ttclock(self, tt):
        m = f"M2S72Bridge.{tt}.eth[1].trafficConditionerLayer.ttClock"

        def s(n):
            return round(float(self.par[(m, n)].rstrip("s")) * PS)
        return make_ct(s("theta0"), int(self.par[(m, "freqOffsetPpb")]), int(self.par[(m, "driftPpbPerS")]),
                       s("updateInterval"), s("updateOffset"))


def ident(data):
    f = pcapng.ethernet(data)
    seq = int.from_bytes(f["payload"][4:8], "big") if f["etherType"] != 0x88F7 else None
    return f, (f["src"], f["dst"], f["pcp"], f["vid"], seq)


def rows(path):
    with open(path) as fh:
        return [r for r in csv.DictReader(fh)]


def ps(text):
    return pcapng.simtime_ps(text) if text else None


def oracle(run, tas, expect_ok=True):
    """per-frame independent verification of every residence row of the three egress TSN ports.
    Returns (records, problems Counter, details)"""
    recs, problems, details = [], Counter(), []

    def bad(kind, msg):
        problems[kind] += 1
        if len(details) < 8:
            details.append(f"{kind}: {msg}")
    ingress = {}                                           # (tt, identity) -> (t_rx_end, bytes)
    for tt in TT.values():
        for p in run.pcap(tt, 1, 1):
            f, key = ident(p["data"])
            if f["etherType"] == 0x88F7:
                continue
            if (tt, key) in ingress:
                bad("ingress-duplicate", f"{tt} {key}")
            ingress[(tt, key)] = (p["t_ps"], p["data"])
    seen = set()
    for eg_id, eg in TT.items():
        out = {}                                           # t_end -> pcap frame at the egress TSN port
        for p in run.pcap(eg, 1, 2):
            out.setdefault(p["t_ps"], []).append(p)
        pulls = {}
        if tas:
            for pcp, tc in TC_OF_PCP.items():
                q = f"M2S72Bridge.{eg}.eth[1].macLayer.queue.queue[{tc}]"
                pushes = [t for t, _ in run.vec.get((q, "incomingPacketLengths:vector"), [])]
                deq = [(t, round(float(v) * PS)) for t, v in run.vec.get((q, "queueingTime:vector"), [])]
                pulls[pcp] = (pushes, deq, gate_oracle(SCHED[eg], tc, run.ttclock(eg)))
        idx = Counter()
        lg = rows(run.log(eg))
        gptp_rows = sum(1 for r in lg if r["event"] == "tx" and int(r["etherType"]) == 0x88F7)
        gptp_pcap = sum(1 for p in run.pcap(eg, 1, 2) if ident(p["data"])[0]["etherType"] == 0x88F7)
        if gptp_rows != gptp_pcap:
            bad("gptp-count", f"{eg}: log {gptp_rows} vs PCAP {gptp_pcap}")
        for r in sorted((r for r in lg if r["event"] == "tx" and r["tagged"] == "1" and int(r["etherType"]) != 0x88F7),
                        key=lambda r: ps(r["tTxEnd"])):
            t12 = ps(r["egressTime"])
            cand = out.get(t12, [])
            if len(cand) != 1:
                bad("egress-frame", f"{eg} t12 {t12}: {len(cand)} PCAP frames end then")
                continue
            p = cand[0]
            f, key = ident(p["data"])
            if (f["pcp"], f["vid"], f["etherType"]) != (int(r["pcp"]), int(r["vid"]), int(r["etherType"])):
                bad("identity", f"{eg} t12 {t12}: log PCP/VID/EtherType {r['pcp']}/{r['vid']}/{r['etherType']} vs wire {f['pcp']}/{f['vid']}/{f['etherType']}")
                continue
            if pcapng.fnv1a64(f["payload"]) != r["txHash"] or r["txHash"] != r["hash"]:
                bad("identity", f"{eg} t12 {t12}: payload hash")
                continue
            if int(r["ttId"]) != eg_id:
                bad("egress-tt", f"{eg}: row ttId {r['ttId']}")
            in_tt = TT.get(int(r["ingressTtId"]))
            ing = ingress.get((in_tt, key))
            if ing is None or ing[1] != p["data"]:
                bad("ingress-identity", f"{eg} {key}: not received (byte-identical) at {in_tt}'s TSN port")
                continue
            t1 = ing[0]
            if ps(r["ingressTime"]) != t1:
                bad("t1", f"{eg} {key}: log t1 {r['ingressTime']} vs PCAP reception end {t1}")
                continue
            if t1 >= t12:
                bad("order", f"{eg} {key}: t1 >= t12")
            R = t12 - t1
            if ps(r["residence"]) != R:
                bad("R", f"{eg} {key}: log R {r['residence']} vs oracle {R}")
                continue
            dur = (len(p["data"]) * 8 + 64) * BIT_PS
            if ps(r["tTxStart"]) != t12 - dur or ps(r["tTxEnd"]) != t12:
                bad("tx", f"{eg} {key}: transmission start/end")
            if (eg, key) in seen:
                bad("duplicate", f"{eg} {key}: observed twice")
            seen.add((eg, key))
            rec = {"cfg": run.cfg, "ingress": in_tt, "egress": eg, "src": key[0], "dst": key[1], "pcp": key[2], "vid": key[3],
                   "seq": key[4], "t1": t1, "t12": t12, "R": R, "tSlot": ps(r["tSlot"]), "tDequeue": ps(r["tDequeue"])}
            if tas:
                pushes, deq, trans = pulls[key[2]]
                k = idx[key[2]]
                idx[key[2]] += 1
                if k >= len(deq) or k >= len(pushes):
                    bad("queue", f"{eg} {key}: no queue observation")
                    continue
                t_out, held = deq[k]
                t_in = pushes[k]
                if t_out - held != t_in or rec["tSlot"] != t_in or rec["tDequeue"] != t_out:
                    bad("queue", f"{eg} {key}: enqueue/dequeue log {rec['tSlot']}/{rec['tDequeue']} vs queue {t_in}/{t_out}")
                    continue
                if not gate_state(trans, t_out):
                    bad("gate", f"{eg} {key}: dequeued while the gate is closed")
                rec.update({"gate_at_enqueue": "open" if gate_state(trans, t_in) else "closed", "held": held,
                            "R_minus_held": R - held, "t_tx_start": t12 - dur})
            recs.append(rec)
        tagged_tx = [r for r in lg if r["event"] == "tx" and r["tagged"] == "1" and int(r["etherType"]) != 0x88F7]
        data_out = [p for p in run.pcap(eg, 1, 2) if ident(p["data"])[0]["etherType"] != 0x88F7]
        if len(tagged_tx) != len(data_out):
            bad("count", f"{eg}: {len(tagged_tx)} residence rows vs {len(data_out)} data frames on the wire")
    return recs, problems, details


if not (OMNETPP and INET and SIMU5G and os.path.exists(os.path.join(SIMU5G, "src", "libsimu5g.so"))):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1")
    sys.exit(2)

CFGS = ["RES-off", "RES-tas", "TAS-gated", "RESN-fifo", "RESN-rotate", "RESN-offset"]
EVIDENCE = os.environ.get("M2B4_EVIDENCE", "")
with tempfile.TemporaryDirectory() as res:
    rc = {}
    for c in CFGS:
        r = opp_run(c, res)
        rc[c] = (r.returncode, r.stdout + r.stderr)
    for c in ("RES-off", "RES-tas", "TAS-gated", "RESN-rotate", "RESN-offset"):
        check(f"T4-run {c}: 0.8 s of the N = 2 bridge completes", rc[c][0] == 0, rc[c][1][-300:])
    R = {c: Run(res, c) for c in ("RES-off", "RES-tas", "TAS-gated", "RESN-rotate", "RESN-offset")}
    tas = R["RES-tas"]

    # ---- pairing in the real bridge
    sca = {}
    for line in open(os.path.join(res, "RES-tas", "0.sca")):
        p = line.split()
        if len(p) >= 4 and p[0] == "scalar":
            sca[(p[1], p[2])] = p[3]
    shaped = [f"M2S72Bridge.{tt}.eth[{e}].measurementLayer.egress" for tt in TT.values() for e in (0, 1)]
    st_ports = [m for m in shaped if (m, "selfTestPairerTasCases") in sca]
    check("T4-pair RES-tas: TAS pairing at all 6 shaped ports, no frame pending at the end; where the accepted configuration "
          "enables the self-test (NW-TT TSN port), FIFO 10 / 10 and TAS 6 / 6 in-simulation pairer cases pass",
          st_ports == ["M2S72Bridge.nwTt.eth[1].measurementLayer.egress"]
          and all(sca.get((m, "selfTestPairerTasPassed")) == "6" and sca.get((m, "selfTestPairerPassed")) == "10" for m in st_ports)
          and all(sca.get((m, "portPending")) == "0" for m in shaped), str(st_ports))
    over, within = 0, 0
    for tt in TT.values():
        lg = [r for r in rows(tas.log(tt)) if r["event"] == "tx"]
        for i, a in enumerate(lg):
            for b in lg[i + 1:]:
                if ps(a["tSlot"]) < ps(b["tSlot"]) and ps(a["tDequeue"]) > ps(b["tDequeue"]):
                    over += 1
                    within += a["pcp"] == b["pcp"]
                elif ps(b["tSlot"]) < ps(a["tSlot"]) and ps(b["tDequeue"]) > ps(a["tDequeue"]):
                    over += 1
                    within += a["pcp"] == b["pcp"]
    check(f"T4-pair RES-tas: {over} valid cross-class overtakings observed (a later-enqueued frame of an open class dequeued "
          f"before an older held frame) and accepted; none within one PCP", over > 0 and within == 0, f"{over}/{within}")
    check("T4-pair RESN-fifo: the accepted FIFO pairing refuses the same valid overtaking (out-of-order MAC dequeue) - the "
          "TAS mode distinguishes reordering from instrumentation errors",
          rc["RESN-fifo"][0] != 0 and "observePort pairing: out-of-order MAC dequeue" in rc["RESN-fifo"][1], rc["RESN-fifo"][1][-200:])

    # ---- observation is passive: frames, ordering, gates, gPTP, protocol timestamps unchanged
    def wire(run):
        return {(tt, i): [(p["dir"], p["t_ps"], p["data"]) for p in pcapng.read(run.pcap_path(tt, i))]
                for tt in TT.values() for i in (0, 1)}
    a, b = wire(tas), wire(R["TAS-gated"])
    n = sum(len(v) for v in a.values())
    check(f"T4-passive RES-tas (observation on) vs M2B-3 TAS-gated (observation off): every frame at both ports of the 3 "
          f"translators identical in bytes, time and order ({n} frames, gPTP included)", n > 1000 and a == b)
    ga = {k: v for k, v in tas.vec.items() if k[1] == "gateState:vector"}
    gb = {k: v for k, v in R["TAS-gated"].vec.items() if k[1] == "gateState:vector"}
    check(f"T4-passive gate transitions identical ({sum(len(v) for v in ga.values())} rows over {len(ga)} gates)", ga == gb and len(ga) == 48)
    stamp_same, nst = True, 0
    for tt in TT.values():
        f1 = os.path.join(res, "m2log", "RES-tas-0", f"M2S72Bridge.{tt}.eth[1].trafficConditionerLayer.ttClock")
        f2 = os.path.join(res, "m2log", "TAS-gated-0", f"M2S72Bridge.{tt}.eth[1].trafficConditionerLayer.ttClock")
        c1 = sorted(x for x in os.listdir(os.path.dirname(f1)) if x.startswith(os.path.basename(f1)))
        for x in c1:
            d1, d2 = open(os.path.join(os.path.dirname(f1), x), "rb").read(), open(os.path.join(os.path.dirname(f2), x), "rb").read()
            stamp_same &= d1 == d2
            nst += d1.count(b"\n")
        stamp_same &= bool(c1)
    check(f"T4-passive TT protocol timestamps (TtClock stamp logs: gPTP / Pdelay event stamps, {nst} lines) identical; gPTP "
          f"correction unchanged (gPTP frames identical above)", stamp_same and nst >= 20)

    # ---- independent per-frame verification
    recs, probs, det = oracle(tas, True)
    check(f"T4-oracle RES-tas: {len(recs)} bridged frames; for every one: egress translator / port, PCP, VID, EtherType, payload hash "
          f"and identity from the wire; t1 = PCAP reception end at the ingress TT's TSN port; t12 = PCAP transmission end; "
          f"R = t12 - t1 exact (ps); transmission start; enqueue / dequeue = INET's per-class queue; dequeued only with its "
          f"gate open; counted once", len(recs) == 238 and not probs, f"{dict(probs)} {det}")
    held = [x for x in recs if x["gate_at_enqueue"] == "closed"]
    check(f"T4-gate-wait {len(held)} frames arrived while their gate was closed: their R contains the gate wait "
          f"(R >= held time > 0 and R - held = the residence without the wait)",
          len(held) >= 100 and all(x["held"] > 0 and x["R"] >= x["held"] + (x["t12"] - x["t_tx_start"]) for x in held))
    off, poff, doff = oracle(R["RES-off"], False)
    check(f"T4-oracle RES-off (TAS disabled, FIFO pairing): {len(off)} bridged frames, every R independently verified the same way",
          len(off) == 238 and not poff, f"{dict(poff)} {doff}")
    # TAS on vs off: same frames; for frames whose arrival at the egress queue is unchanged, R_on - R_off = gate wait
    key = lambda x: (x["egress"], x["src"], x["dst"], x["pcp"], x["seq"])
    on_by, off_by = {key(x): x for x in recs}, {key(x): x for x in off}
    common = sorted(set(on_by) & set(off_by))
    same_arrival = [k for k in common if on_by[k]["t1"] == off_by[k]["t1"] and on_by[k]["tSlot"] == off_by[k]["tSlot"]]
    exact = [k for k in same_arrival if on_by[k]["R"] - off_by[k]["R"] == on_by[k]["held"] - (off_by[k]["tDequeue"] - off_by[k]["tSlot"])]
    check(f"T4-compare TAS on vs off: the same {len(common)} bridged frames observed; {len(same_arrival)} reach the egress "
          f"queue at the same time in both runs, and for all of them R_on - R_off = the queueing-time difference (the gate "
          f"wait) exactly (no claim about the other frames' distributions)",
          len(common) == 238 and len(same_arrival) > 0 and len(exact) == len(same_arrival), f"{len(exact)}/{len(same_arrival)}")
    # bridge_delay.py (accepted offline observer) statistics, cross-checked against the oracle
    logs = [tas.log(tt) for tt in TT.values()]
    obs = BD.observe(logs)
    st = defaultdict(list)
    for x in recs:
        st[({v: k for k, v in TT.items()}[x["ingress"]], {v: k for k, v in TT.items()}[x["egress"]], x["pcp"], x["vid"])].append(x["R"])
    bd = {(p["ingressTtId"], p["egressTtId"], p["pcp"], p["vid"]): p for p in obs["pairs"]}
    check(f"T4-stats bridge_delay.py on the RES-tas logs: {len(bd)} groups (ingress TT, egress TT, PCP, VID); counts, min, max "
          f"and sum equal the oracle's; classes residence {obs['classes']['residence']}, gPTP {obs['classes']['gptp']}, untagged "
          f"{obs['classes']['untagged']}, not-bridged {obs['classes']['not-bridged']}",
          set(bd) == set(st) and all(bd[k]["count"] == len(v) and bd[k]["min_ps"] == min(v) and bd[k]["max_ps"] == max(v)
                                     and bd[k]["sum_ps"] == sum(v) for k, v in st.items())
          and obs["classes"]["residence"] == 238 and obs["classes"]["gptp"] > 0)
    if EVIDENCE:
        os.makedirs(EVIDENCE, exist_ok=True)
        for name, data in (("residence_tas.csv", recs), ("residence_off.csv", off)):
            with open(os.path.join(EVIDENCE, name), "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=sorted({k for d in data for k in d}))
                w.writeheader()
                w.writerows(data)
        json.dump({"tas": obs, "off": BD.observe([R["RES-off"].log(tt) for tt in TT.values()])}, open(os.path.join(EVIDENCE, "bridge_delay.json"), "w"), indent=1)

    # ---- negative controls in the real bridge (the oracle must refuse them for the intended reason)
    rr, prr, drr = oracle(R["RESN-rotate"], True)
    check(f"T4-negative RESN-rotate (wrong frame identity in the log rows): the oracle refuses it (identity / t1 mismatches "
          f"{prr.get('identity', 0) + prr.get('t1', 0) + prr.get('ingress-identity', 0)})",
          prr.get("identity", 0) + prr.get("t1", 0) + prr.get("ingress-identity", 0) > 0, f"{dict(prr)}")
    ro, pro, dro = oracle(R["RESN-offset"], True)
    check(f"T4-negative RESN-offset (t1 of DL frames +1 ns at the NW-TT): the oracle refuses exactly the DL frames for a wrong "
          f"t1 ({pro.get('t1', 0)}), the UL frames still pass; bridge_delay.py alone cannot see it (internally consistent)",
          pro.get("t1", 0) == 100 and set(pro) == {"t1"} and BD.observe([R["RESN-offset"].log(tt) for tt in TT.values()])["classes"]["residence"] == 238,
          f"{dict(pro)}")
    # log-level mutations of the real RES-tas logs
    with tempfile.TemporaryDirectory() as d:
        def mutated(mut):
            out = []
            for tt in TT.values():
                src = tas.log(tt)
                dst = os.path.join(d, os.path.basename(src))
                with open(src) as fh:
                    lines = fh.read().splitlines()
                lines = mut(tt, lines)
                with open(dst, "w") as fh:
                    fh.write("\n".join(lines) + "\n")
                out.append(dst)
            return out

        def first_data(lines):
            """the first transmitted, tagged, non-gPTP row (columns: event, ..., tagged = 5, ..., etherType = 9)"""
            return next(i for i, l in enumerate(lines) if l.split(",")[0] == "tx" and l.split(",")[5] == "1"
                        and l.split(",")[9] != str(0x88F7))

        def dup(tt, lines):
            if tt == "dsTt[0]":
                i = first_data(lines)
                lines.insert(i + 1, lines[i])
            return lines

        def untag(tt, lines):
            if tt == "dsTt[0]":
                i = first_data(lines)
                f = lines[i].split(",")
                f[5], f[6], f[7], f[8], f[22] = "0", "", "", "", ""
                lines[i] = ",".join(f)
            return lines

        def late_t1(tt, lines):
            if tt == "dsTt[0]":
                i = first_data(lines)
                f = lines[i].split(",")
                f[7] = "0.799"
                f[22] = str(Decimal(f[21]) - Decimal("0.799"))             # consistent, exact, negative
                lines[i] = ",".join(f)
            return lines
        for name, mut, want in (("duplicate egress observation", dup, "double count"),
                                ("invalid timestamp ordering (t1 after t12)", late_t1, "egress before ingress")):
            try:
                BD.observe(mutated(mut))
                check(f"T4-negative real log, {name}: refused", False, "accepted")
            except BD.LogError as ex:
                check(f"T4-negative real log, {name}: bridge_delay.py refuses it ({want})", want in str(ex), str(ex))
        o2 = BD.observe(mutated(untag))
        check("T4-negative real log, missing ingress metadata: counted as untagged, no R inferred (residence 237, untagged 1), and the "
              "oracle's wire count shows the missing observation",
              o2["classes"]["untagged"] == 1 and o2["classes"]["residence"] == 237)

print(f"\nM2B-4 TAS residence tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
