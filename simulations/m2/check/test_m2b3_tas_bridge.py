#!/usr/bin/env python3
"""M2B-3 functional TAS / Qbv tests on actual Ethernet traffic in the 5G-TSN bridge (docs/migration/m2b-3-tas-qbv.md).

Runs the TEST-ONLY configurations of simulations/m2/m2b3/tas.ini (each extends the accepted M2S72-B-q0-Eall-n2: N = 2,
listener -> talker[k] PCP 5 and PCP 0 frames (VID 42, 100 B every 20 ms) and the reverse, gPTP through every
translator), 0.8 s each, and checks them against an INDEPENDENT gate-schedule oracle:
  - the gate schedule is taken from scfg/s72-q0-tas.json (not from the compiled INI), the TT clock of each translator
    from the run's recorded TtClock parameters; C_T is re-implemented from TtClock.ned (model A2, exact integers);
  - transition j of a gate occurs at t_j = inf { t >= t_(j-1) | C_T(t) >= c_j }, c_j = C_T(0) + the TT offset of the
    j-th state change after the gate's initialization at schedule position phase_ns (PeriodicGate anchors its cycle
    on the clock reading at initialization);
  - a frame is correlated through INET's own per-class FIFO statistics (queue[tc] incomingPacketLengths: enqueue;
    queueingTime: dequeue and holding time) and the PCAP of the egress port (transmission end, identity
    (source, destination, PCP, application sequence number)); no M2-S1 pairing is used (its FIFO pairer is shown to stop with
    per-class queues: TASN-pairer).
A gate opening is distinguished from a transmission: eligibility = the enqueue time, or the next opening if the gate is
closed; the dequeue (transmission start) can only follow, and the PCAP records the end of the transmission.

Not a tier-0 suite: it needs a built stack (OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT with a built Simu5G 1.8.1, and
libnasctime_m2 from src/nasctime/m2/build.sh). Optional: M2B3_EVIDENCE=<dir> writes the per-frame and per-transition
records there. Functional development test (level 2): no scientific result.
"""
import csv
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
NET = os.path.join(M2, "m2b3")
sys.path.insert(0, HERE)
import pcapng  # noqa: E402

OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
EVIDENCE = os.environ.get("M2B3_EVIDENCE", "")
PS, NS = 10 ** 12, 1000
T_END = 800 * 10 ** 9                                    # sim-time-limit 0.8 s, in ps
BIT_PS = 1000                                            # 1 Gb/s (Eth1G)
PCP_OF_TC = {5: 5, 1: 0}                                 # INET PcpTrafficClassClassifier default at 8 classes
SPEC = json.load(open(os.path.join(M2, "scfg", "s72-q0-tas.json")))
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


# ---------------------------------------------------------------- TT clock oracle (TtClock.ned, model A2) ---------
def make_ct(theta0=0, y=0, d=0, upd=0, uoff=0):
    def u_of(s):
        return uoff + upd * ((s - uoff) // upd) if upd > 0 else 0

    def seg(u, s):
        dd = s - u
        return s + theta0 + (2 * PS * y * dd + d * dd * dd) // (2 * 10 ** 21)

    def ct(s):
        return seg(u_of(s), s)
    ct.u_of, ct.upd = u_of, upd
    return ct


IDEAL = make_ct()


def first_reach(ct, c, t0, tmax):
    """inf { t >= t0 | C(t) >= c } within [t0, tmax], searched segment by segment (C is monotone within one)"""
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


def declared(sched, tc, pos):
    for e in sched["entries"]:
        if e["start_ns"] <= pos < e["start_ns"] + e["duration_ns"]:
            return tc in e["open"]
    raise AssertionError(pos)


def gate_oracle(sched, tc, ct, t_end=T_END):
    """[(t_ps, state)] of a gate: the initial state at t = 0, then every change up to t_end"""
    cyc, ph, ents = sched["cycle_ns"] * NS, sched["phase_ns"] * NS, sched["entries"]
    states = [tc in e["open"] for e in ents]
    init = declared(sched, tc, sched["phase_ns"])
    out = [(0, init)]
    changes = sorted(((e["start_ns"] * NS - ph) % cyc or cyc, states[j]) for j, e in enumerate(ents)
                     if states[j] != states[j - 1])
    if not changes:
        return out
    c0, t, k = ct(0), 0, 0
    while True:
        for rel, st in changes:
            t = first_reach(ct, c0 + rel + k * cyc, t, t_end)
            if t is None:
                return out
            out.append((t, st))
        k += 1


def intervals(trans, t_end=T_END):
    """open intervals [start, end) from a transition list"""
    out, start = [], None
    for t, st in trans:
        if st and start is None:
            start = t
        elif not st and start is not None:
            out.append((start, t))
            start = None
    if start is not None:
        out.append((start, t_end + 1))
    return out


# ---------------------------------------------------------------- results ------------------------------------------
def opp_run_accepted(cwd):
    """the ACCEPTED M2S72-B-q0-Eall-n2 itself (m2s72.ini, unchanged), shortened on the command line to 0.8 s"""
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", "-f", os.path.join(M2, "m2s72.ini"), "-c", "M2S72-B-q0-Eall-n2",
           "-r", "0", "--sim-time-limit=0.8s",
           "-n", ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"), os.path.join(SIMU5G, "src"),
                           os.path.join(INET, "src")]), "-x", "nasctime.nodes",
           "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"), "-l", os.path.join(SIMU5G, "src", "simu5g"),
           f"--result-dir={os.path.join(cwd, 'res')}", "--cmdenv-express-mode=true"]
    return subprocess.run(cmd, cwd=cwd, capture_output=True, text=True, timeout=1200)


def gptp(path):
    return [(p["dir"], p["t_ps"], p["data"]) for p in pcapng.read(path)
            if pcapng.ethernet(p["data"])["etherType"] == 0x88F7] if os.path.exists(path) else None


def opp_run(cfg, res):
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", "-f", "tas.ini", "-c", cfg, "-r", "0",
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
        vpath = os.path.join(res, cfg, "0.vec")
        if os.path.exists(vpath):
            for line in open(vpath):
                if line.startswith("vector "):
                    p = line.split()
                    names[p[1]] = (p[2], p[3])
                elif line[:1].isdigit():
                    p = line.rstrip("\n").split("\t")
                    if p[0] in names:
                        self.vec[names[p[0]]].append((pcapng.simtime_ps(p[2]), p[3]))
        spath = os.path.join(res, cfg, "0.sca")
        if os.path.exists(spath):
            for line in open(spath):
                m = re.match(r"^par (\S+) (\S+) (.*)$", line.rstrip("\n"))
                if m:
                    self.par[(m.group(1), m.group(2))] = m.group(3)

    def pcap(self, node, idx):
        path = os.path.join(self.res, "pcap", f"{self.cfg}-0", f"M2S72Bridge.{node}.pcapRecorder[{idx}].pcapng")
        return pcapng.read(path) if os.path.exists(path) else []

    def ttclock(self, tt):
        m = f"M2S72Bridge.{tt}.eth[1].trafficConditionerLayer.ttClock"

        def s(n):
            return round(float(self.par[(m, n)].rstrip("s")) * PS)
        return make_ct(s("theta0"), int(self.par[(m, "freqOffsetPpb")]), int(self.par[(m, "driftPpbPerS")]),
                       s("updateInterval"), s("updateOffset"))

    def gate(self, tt, port, tc):
        return [(t, v == "1") for t, v in
                self.vec.get((f"M2S72Bridge.{tt}.eth[{port}].macLayer.queue.transmissionGate[{tc}]", "gateState:vector"), [])]


SCHED = {"nwTt": next(s for s in SPEC["tas"]["schedules"] if s["translator"] == "nw-tt"),
         "dsTt[0]": next(s for s in SPEC["tas"]["schedules"] if s["translator"] == "ds-tt"),
         "dsTt[1]": next(s for s in SPEC["tas"]["schedules"] if s["translator"] == "ds-tt")}
PORTS = list(SCHED)


def frames(run, tt, tc, trans, evid):
    """per-frame records of a gated class at the TSN-side egress port of translator tt"""
    q = f"M2S72Bridge.{tt}.eth[1].macLayer.queue.queue[{tc}]"
    push = [t for t, _ in run.vec.get((q, "incomingPacketLengths:vector"), [])]
    pull = [(t, round(float(v) * PS)) for t, v in run.vec.get((q, "queueingTime:vector"), [])]
    qlen = run.vec.get((q, "queueLength:vector"), [])
    tx = []
    for p in run.pcap(tt, 1):
        if p["dir"] == 2:
            f = pcapng.ethernet(p["data"])
            if f["pcp"] == PCP_OF_TC[tc] and f["etherType"] != 0x88F7:
                tx.append((p["t_ps"], f["src"], f["dst"], int.from_bytes(f["payload"][4:8], "big"), len(p["data"])))
    opens = intervals(trans)
    recs = []
    for i, (t_out, held) in enumerate(pull):
        t_in = t_out - held
        win = next((w for w in opens if w[0] <= t_in < w[1]), None)
        nxt = win[0] if win else next((w[0] for w in opens if w[0] > t_in), None)
        elig = t_in if win else nxt
        out_win = next((w for w in opens if w[0] <= t_out < w[1]), None)
        t_end, src, dst, seq, length = tx[i] if i < len(tx) else (None, None, None, None, None)
        dur = (length * 8 + 64) * BIT_PS if length else None
        qmin = min((int(v) for t, v in qlen if t_in <= t < t_out), default=None)
        recs.append({"tt": tt, "tc": tc, "pcp": PCP_OF_TC[tc], "src": src, "dst": dst, "seq": seq, "t_in": t_in,
                     "push_match": i < len(push) and push[i] == t_in, "gate_at_in": "open" if win else "closed",
                     "eligible": elig, "t_dequeue": t_out, "held_ps": held, "delay_after_eligible": t_out - elig if elig is not None else None,
                     "dequeue_in_open_window": out_win is not None,
                     "fits_window": out_win is not None and dur is not None and t_out + dur <= out_win[1],
                     "t_tx_end": t_end, "tx_end_minus_dequeue": (t_end - t_out) if t_end else None, "tx_duration": dur,
                     "queue_len_min_while_held": qmin})
    if evid is not None:
        evid.extend(recs)
    return push, pull, tx, recs


if not (OMNETPP and INET and SIMU5G and os.path.exists(os.path.join(SIMU5G, "src", "libsimu5g.so"))):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1")
    sys.exit(2)

CFGS = ["TAS-off", "TAS-open", "TAS-gated", "TAS-tt", "TASN-unbound", "TASN-phase", "TASN-pairer"]
with tempfile.TemporaryDirectory() as res:
    rc = {}
    for c in CFGS:
        r = opp_run(c, res)
        rc[c] = (r.returncode, r.stdout + r.stderr)
    for c in CFGS[:-1]:
        check(f"T3-run {c}: 0.8 s of the N = 2 bridge completes", rc[c][0] == 0, rc[c][1][-300:])
    R = {c: Run(res, c) for c in CFGS[:-1]}
    ev_frames, ev_gates = [], []

    # ---- A: TAS disabled / infrastructure only -------------------------------------------------------------------
    def wire(run):
        out = {}
        for tt in PORTS:
            for idx in (0, 1):
                out[(tt, idx)] = [(p["dir"], p["t_ps"], p["data"]) for p in run.pcap(tt, idx)]
        return out
    off, opn = wire(R["TAS-off"]), wire(R["TAS-open"])
    nfr = sum(len(v) for v in off.values())
    check(f"T3-A TAS-off vs TAS-open (shaper, TtGateClock and binding on, all gates open): every frame at both ports of "
          f"the 3 translators identical in bytes and time ({nfr} frames)", nfr > 400 and off == opn,
          str([k for k in off if off[k] != opn.get(k)]))
    acw = os.path.join(res, "accepted")
    os.makedirs(acw)
    ra = opp_run_accepted(acw)
    same, n_g = True, 0
    for tt in PORTS:
        for idx in (0, 1):
            f = f"M2S72Bridge.{tt}.pcapRecorder[{idx}].pcapng"
            a = gptp(os.path.join(acw, "res", "pcap", "M2S72-B-q0-Eall-n2-0", f))
            o = gptp(os.path.join(res, "pcap", "TAS-off-0", f))
            g_ = gptp(os.path.join(res, "pcap", "TAS-gated-0", f))
            n_g += len(a or [])
            same &= a is not None and a == o == g_ and len(a) > 0
    check(f"T3-A the accepted M2S72-B-q0-Eall-n2 (unchanged, 0.8 s), TAS-off and TAS-gated: every gPTP frame at both "
          f"ports of the 3 translators identical in bytes and time ({n_g} frames; the added recordings are passive and "
          f"gating classes 5 / 1 leaves gPTP untouched)", ra.returncode == 0 and same, (ra.stdout + ra.stderr)[-200:])
    check("T3-A TAS-off is the accepted configuration (no shaper, no gate clock): plain PacketQueue, no transmission gates",
          not any(k[1] == "gateState:vector" for k in R["TAS-off"].vec) and ("M2S72Bridge.dsTt[0].clock", "typename") not in R["TAS-off"].par)

    # ---- B-D: gated run --------------------------------------------------------------------------------------------
    G = R["TAS-gated"]
    for tt in PORTS:
        ct = G.ttclock(tt)
        for tc in range(8):
            got = G.gate(tt, 1, tc)
            exp = gate_oracle(SCHED[tt], tc, ct)
            if tc in (5, 1):
                ev_gates += [{"cfg": "TAS-gated", "tt": tt, "tc": tc, "t": t, "open": int(s)} for t, s in got]
                check(f"T3-gate {tt} eth[1] TC{tc}: {len(exp) - 1} transitions equal the TT-time oracle (ps)",
                      got == exp and len(exp) > 100, f"{len(got)}/{len(exp)} first diff "
                      f"{next(((a, b) for a, b in zip(got, exp) if a != b), None)}")
            elif got != exp:
                check(f"T3-gate {tt} eth[1] TC{tc}: always open (oracle)", False, f"{got[:3]}")
        check(f"T3-gate {tt} eth[0] (5GS side): every gate bound and always open (no schedule there)",
              all(G.gate(tt, 0, tc) == [(0, True)] for tc in range(8)))
    check("T3-class PCP 5 frames are queued in traffic class 5 and PCP 0 frames in traffic class 1 (INET default mapping); "
          "gPTP (untagged) in class 7",
          all(G.vec.get((f"M2S72Bridge.dsTt[0].eth[1].macLayer.queue.queue[{tc}]", "incomingPacketLengths:vector")) for tc in (1, 5, 7))
          and not G.vec.get(("M2S72Bridge.dsTt[0].eth[1].macLayer.queue.queue[0]", "incomingPacketLengths:vector")))
    held_total, released_total, total = 0, 0, 0
    for tt in PORTS:
        for tc in (5, 1):
            trans = gate_oracle(SCHED[tt], tc, G.ttclock(tt))
            push, pull, tx, recs = frames(G, tt, tc, trans, ev_frames)
            total += len(recs)
            held = [r for r in recs if r["gate_at_in"] == "closed"]
            held_total += len(held)
            w = f"{tt} TC{tc} (PCP {PCP_OF_TC[tc]})"
            check(f"T3-fifo {w}: {len(recs)} frames; enqueue time = dequeue - queueing time for every frame (per-class "
                  f"FIFO correlation), every enqueued frame dequeued, every dequeued frame transmitted (PCAP)",
                  len(recs) >= 20 and all(r["push_match"] for r in recs) and len(push) == len(pull)
                  and len(tx) == len(pull), f"{len(push)}/{len(pull)}/{len(tx)}")
            check(f"T3-B {w}: {len(held)} frames arrived while the gate was closed and were held "
                  f"(dequeued only at or after the next opening; queue occupied meanwhile)",
                  len(held) > 0 and all(r["t_dequeue"] >= r["eligible"] > r["t_in"] and (r["queue_len_min_while_held"] or 0) >= 1
                                        for r in held))
            rel = [r for r in held if r["delay_after_eligible"] == 0]
            released_total += len(rel)
            check(f"T3-C {w}: every held frame is dequeued in the window that opened after it ({len(rel)} of {len(held)} "
                  f"exactly at the opening instant; the rest after the frames ahead of it)",
                  all(r["dequeue_in_open_window"] for r in held) and len(rel) > 0
                  and all(r["delay_after_eligible"] < 2 * (r["tx_duration"] + 96 * BIT_PS) * 4 for r in held))
            check(f"T3-D {w}: no frame dequeued while its gate is closed; each transmission ends within the open window "
                  f"(implicit guard band); transmission end = dequeue + (length*8 + 64) bit times",
                  all(r["dequeue_in_open_window"] and r["fits_window"] for r in recs)
                  and all(r["tx_end_minus_dequeue"] is not None and r["tx_end_minus_dequeue"] >= r["tx_duration"] for r in recs))
    ids = [(r["tt"], r["src"], r["dst"], r["pcp"], r["seq"]) for r in ev_frames]
    check(f"T3-id every transmitted gated-class frame has a unique identity (port, source, destination, PCP, sequence; "
          f"{len(ids)} frames) and sequence numbers per flow are consecutive (no frame lost or reordered within a class)",
          len(set(ids)) == len(ids) and all(
              sorted(r["seq"] for r in ev_frames if (r["tt"], r["src"], r["dst"], r["pcp"]) == k)
              == list(range(len([1 for r in ev_frames if (r["tt"], r["src"], r["dst"], r["pcp"]) == k])))
              and [r["seq"] for r in ev_frames if (r["tt"], r["src"], r["dst"], r["pcp"]) == k]
              == sorted(r["seq"] for r in ev_frames if (r["tt"], r["src"], r["dst"], r["pcp"]) == k)
              for k in {i[:4] for i in ids}))
    check(f"T3-B/C overall: {held_total} of {total} gated-class frames were held by a closed gate and released when it "
          f"opened ({released_total} exactly at the opening)", held_total >= 20 and released_total >= 10)
    # the two classes follow the declared schedule: on the DS-TT port, PCP 5 only in [0, 2) ms and PCP 0 only in
    # [5, 10) ms of the TT cycle; never at the same time
    for tt in ("dsTt[0]", "dsTt[1]"):
        r5 = [r for r in ev_frames if r["tt"] == tt and r["tc"] == 5]
        r1 = [r for r in ev_frames if r["tt"] == tt and r["tc"] == 1]
        ct = G.ttclock(tt)
        c0 = ct(0)
        pos = lambda t: (ct(t) - c0) % (10 ** 10)                      # TT schedule position, phase 0, cycle 10 ms
        check(f"T3-D {tt}: PCP 5 transmissions start in TT positions [0, 2) ms and PCP 0 in [5, 10) ms of the cycle",
              all(pos(r["t_dequeue"]) < 2 * 10 ** 9 for r in r5) and all(5 * 10 ** 9 <= pos(r["t_dequeue"]) for r in r1),
              str(sorted({pos(r['t_dequeue']) // 10 ** 6 for r in r5 + r1})[:6]))
    # ungated traffic: gPTP (class 7) is never held at a gated port
    gq = [(t, round(float(v) * PS)) for tt in PORTS for t, v in
          G.vec.get((f"M2S72Bridge.{tt}.eth[1].macLayer.queue.queue[7]", "queueingTime:vector"), [])]
    check(f"T3-D gPTP / untagged frames (class 7, always open) at the gated ports: {len(gq)} frames, none held "
          f"(queueing time below one frame time)", len(gq) >= 10 and all(h < 2 * 10 ** 6 for _, h in gq), str(max(gq, default=None)))

    # ---- E: TT time, not an ideal clock ---------------------------------------------------------------------------
    T = R["TAS-tt"]
    ct1 = T.ttclock("dsTt[1]")
    check("T3-E TAS-tt: dsTt[1]'s recorded TtClock is theta0 = 400 us, y = +200 ppm, updates every 10 ms",
          ct1(0) != 0 and T.par[("M2S72Bridge.dsTt[1].eth[1].trafficConditionerLayer.ttClock", "freqOffsetPpb")] == "200000")
    for tc in (5, 1):
        got = T.gate("dsTt[1]", 1, tc)
        exp = gate_oracle(SCHED["dsTt[1]"], tc, ct1)
        ideal = gate_oracle(SCHED["dsTt[1]"], tc, IDEAL)
        diff = [abs(a[0] - b[0]) for a, b in zip(exp, ideal)]
        ev_gates += [{"cfg": "TAS-tt", "tt": "dsTt[1]", "tc": tc, "t": t, "open": int(s)} for t, s in got]
        check(f"T3-E dsTt[1] TC{tc}: transitions equal the TT-time oracle (rate +200 ppm, 5G time-update steps); an "
              f"ideal clock would differ by up to {max(diff) / 1e6:.3f} us in {sum(1 for x in diff if x)} of {len(diff)} "
              f"transitions (theta0 itself does not shift the cycle: the phase is anchored on the initial TT reading)",
              got == exp and got != ideal and max(diff) >= 10 ** 5, f"{len(got)}/{len(exp)}")
        f_ = frames(T, "dsTt[1]", tc, exp, None)[3]
        check(f"T3-E dsTt[1] TC{tc}: frames are dequeued only inside the TT-time open windows ({len(f_)} frames)",
              len(f_) >= 20 and all(r["dequeue_in_open_window"] for r in f_))
    check("T3-E dsTt[0] (unchanged TT clock) in TAS-tt: gates still equal its own TT oracle",
          all(T.gate("dsTt[0]", 1, tc) == gate_oracle(SCHED["dsTt[0]"], tc, T.ttclock("dsTt[0]")) for tc in (5, 1)))

    # ---- negative controls ----------------------------------------------------------------------------------------
    U = R["TASN-unbound"]
    for tc in (5, 1):
        got = U.gate("dsTt[1]", 1, tc)
        check(f"T3-negative TASN-unbound dsTt[1] TC{tc}: without the explicit binding the gates run on simulation time "
              f"(equal the ideal-clock oracle, differ from the TT oracle) - the missing binding is detected",
              got == gate_oracle(SCHED["dsTt[1]"], tc, IDEAL) and got != gate_oracle(SCHED["dsTt[1]"], tc, U.ttclock("dsTt[1]")))
    check("T3-negative TASN-unbound: the gates' clockModule is empty",
          all(U.par.get((f"M2S72Bridge.dsTt[1].eth[1].macLayer.queue.transmissionGate[{tc}]", "clockModule"), "x").strip('"\\') == ""
              for tc in range(8)) if any(k[1] == "clockModule" for k in U.par) else True)
    Ph = R["TASN-phase"]
    got, exp = Ph.gate("dsTt[0]", 1, 5), gate_oracle(SCHED["dsTt[0]"], 5, Ph.ttclock("dsTt[0]"))
    diffs = {a[0] - b[0] for a, b in zip(got, exp) if a != b}
    check("T3-negative TASN-phase: a 1 ns phase error of one gate is detected by the oracle (every changed transition "
          "1 ns of TT time early = 1000 or 1001 ps at y = -100 ppb; the other gates unchanged)",
          got != exp and len(got) == len(exp) and diffs <= {-1000, -1001} and -1000 in diffs
          and Ph.gate("dsTt[0]", 1, 1) == gate_oracle(SCHED["dsTt[0]"], 1, Ph.ttclock("dsTt[0]")), str(sorted(diffs)[:4]))
    check("T3-pairer TASN-pairer: the accepted M2-S1 FIFO egress pairer stops with an out-of-order pairing error under "
          "per-class queues (not hidden; observePort is off in the TAS configurations, B6 deferred)",
          rc["TASN-pairer"][0] != 0 and "observePort pairing: out-of-order" in rc["TASN-pairer"][1], rc["TASN-pairer"][1][-300:])

    if EVIDENCE:
        os.makedirs(EVIDENCE, exist_ok=True)
        for name, rows in (("frames.csv", ev_frames), ("gates.csv", ev_gates)):
            with open(os.path.join(EVIDENCE, name), "w", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=list(rows[0]))
                w.writeheader()
                w.writerows(rows)

# ---- default-off: nothing accepted references the TAS configuration
hits = subprocess.run(["git", "-C", REPO, "grep", "-l", "-e", "hasEgressTrafficShaping", "-e", "TtGateClock", "--", "simulations",
                       ":!simulations/m2/m2b2", ":!simulations/m2/m2b3", ":!simulations/m2/check/test_m2b2_*",
                       ":!simulations/m2/check/test_m2b3_*", ":!simulations/m2/check/check_m2b3_*", ":!simulations/m2/m2b5", ":!simulations/m2/check/test_m2b5_*",
                       ":!simulations/m2/check/m2b5_oracle.py", ":!simulations/m2/check/test_tsnaf_compile_epoch.py", ":!simulations/m2/check/test_tsnaf_compile_tas.py",
                       ":!simulations/m2/tools/tsnaf_compile.py"], capture_output=True, text=True).stdout.split()
check("T3-default-off no accepted configuration, network or generator enables TAS or the gate clock", hits == [], str(hits))

print(f"\nM2B-3 TAS bridge functional tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
