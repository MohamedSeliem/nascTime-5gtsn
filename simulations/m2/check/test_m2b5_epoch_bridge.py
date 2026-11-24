#!/usr/bin/env python3
"""M2B-5 common-epoch TAS in the real N = 2 bridge (docs/migration/m2b-5-common-epoch.md).

Runs the TEST-ONLY configurations of simulations/m2/m2b5/epoch.ini (accepted M2S72Bridge, PCP 5 and PCP 0 traffic,
NW-TT and both DS-TTs with the same common-epoch schedule, M2-S1 observation with the M2B-4 TAS pairing) and checks:
  - every gate transition of the three TSN ports against the independent common-epoch oracle (check/m2b5_oracle.py:
    declared schedule of scfg/s72-q0-epoch.json, base time, the run's recorded TtClock parameters);
  - alignment: the three translators change their gates at the same TT times (base + k * cycle + boundary), at
    simulation times that differ when their TT clocks differ;
  - actual Ethernet traffic: per traffic class, frames enqueued while closed are held and every dequeue happens with
    the gate open (INET per-class queue statistics, PCAP);
  - M2B-4 residence observation preserved: every residence row against PCAP t1 / t12 (R exact in ps), counted once,
    bridge_delay.py statistics equal to the oracle's;
  - negative controls.
Not a tier-0 suite: needs a built stack (OMNETPP_ROOT, INET_ROOT, SIMU5G_ROOT with a built Simu5G 1.8.1, libnasctime_m2).
Functional development test (level 2): no latency or determinism claim.
"""
import csv
import importlib.util
import json
import os
import re
import subprocess
import sys
import tempfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
NET = os.path.join(M2, "m2b5")
sys.path.insert(0, HERE)
import m2b5_oracle as O  # noqa: E402
import pcapng  # noqa: E402

spec_ = importlib.util.spec_from_file_location("bridge_delay", os.path.join(M2, "tools", "bridge_delay.py"))
BD = importlib.util.module_from_spec(spec_)
spec_.loader.exec_module(BD)
OMNETPP, INET, SIMU5G = (os.environ.get(k, "") for k in ("OMNETPP_ROOT", "INET_ROOT", "SIMU5G_ROOT"))
PS, BIT_PS = 10 ** 12, 1000
T_END = 800 * 10 ** 9
TT = {1: "nwTt", 2: "dsTt[0]", 3: "dsTt[1]"}
TC_OF_PCP = {5: 5, 0: 1}
SPEC = json.load(open(os.path.join(M2, "scfg", "s72-q0-epoch.json")))
SCHED = {"nwTt": SPEC["tas"]["schedules"][0], "dsTt[0]": SPEC["tas"]["schedules"][1], "dsTt[1]": SPEC["tas"]["schedules"][1]}
PASS, FAIL = [], []


def check(name, cond, detail=""):
    (PASS if cond else FAIL).append(name)
    print(f"{'PASS' if cond else 'FAIL'}  {name}" + (f"  [{detail}]" if not cond and detail else ""))


def opp_run(cfg, res):
    cmd = [os.path.join(OMNETPP, "bin", "opp_run"), "-u", "Cmdenv", "-f", "epoch.ini", "-c", cfg, "-r", "0",
           "-n", ":".join([os.path.join(REPO, "simulations"), os.path.join(REPO, "src"), os.path.join(SIMU5G, "src"),
                           os.path.join(INET, "src")]), "-x", "nasctime.nodes",
           "-l", os.path.join(REPO, "src", "nasctime", "m2", "nasctime_m2"), "-l", os.path.join(SIMU5G, "src", "simu5g"),
           f"--result-dir={res}", "--cmdenv-express-mode=true"]
    return subprocess.run(cmd, cwd=NET, capture_output=True, text=True, timeout=1200)


class Run:
    def __init__(self, res, cfg):
        self.res, self.cfg = res, cfg
        self.vec, self.par, self.sca = defaultdict(list), {}, {}
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
                m = re.match(r"^(par|scalar) (\S+) (\S+) (.*)$", line.rstrip("\n"))
                if m:
                    (self.par if m.group(1) == "par" else self.sca)[(m.group(2), m.group(3))] = m.group(4)

    def ttclock(self, tt):
        m = f"M2S72Bridge.{tt}.eth[1].trafficConditionerLayer.ttClock"

        def s(n):
            return round(float(self.par[(m, n)].rstrip("s")) * PS)
        return O.make_ct(s("theta0"), int(self.par[(m, "freqOffsetPpb")]), int(self.par[(m, "driftPpbPerS")]),
                         s("updateInterval"), s("updateOffset"))

    def gate(self, tt, port, tc):
        return [(t, v == "1") for t, v in
                self.vec.get((f"M2S72Bridge.{tt}.eth[{port}].macLayer.queue.transmissionGate[{tc}]", "gateState:vector"), [])]

    def pcap(self, tt, idx, direction):
        p = os.path.join(self.res, "pcap", f"{self.cfg}-0", f"M2S72Bridge.{tt}.pcapRecorder[{idx}].pcapng")
        return [x for x in pcapng.read(p) if x["dir"] == direction] if os.path.exists(p) else []

    def log(self, tt):
        return os.path.join(self.res, "m2log", f"{self.cfg}-0", f"M2S72Bridge.{tt}.eth[1].measurementLayer.egress.port.csv")


def changes(run, tt, tc, base=None):
    s = SCHED[tt]
    return O.epoch_changes(s["entries"], s["cycle_ns"], s["base_time_ns"] if base is None else base, tc, run.ttclock(tt), T_END)


def ident(data):
    f = pcapng.ethernet(data)
    return f, (f["src"], f["dst"], f["pcp"], f["vid"], int.from_bytes(f["payload"][4:8], "big") if f["etherType"] != 0x88F7 else None)


def ps(text):
    return pcapng.simtime_ps(text) if text else None


def state_at(trans, t):
    st = trans[0][1]
    for tt, s in trans:
        if tt > t:
            break
        st = s
    return st


pending = []


def residence(run):
    """M2B-4 method: every residence row of the three egress TSN ports against PCAP t1 / t12, INET queues, gates"""
    recs, problems, details = [], Counter(), []
    pending.clear()

    def bad(kind, msg):
        problems[kind] += 1
        if len(details) < 6:
            details.append(f"{kind}: {msg}")
    ingress = {}
    for tt in TT.values():
        for p in run.pcap(tt, 1, 1):
            f, key = ident(p["data"])
            if f["etherType"] != 0x88F7:
                ingress[(tt, key)] = (p["t_ps"], p["data"])
    seen = set()
    for eg_id, eg in TT.items():
        out = defaultdict(list)
        for p in run.pcap(eg, 1, 2):
            out[p["t_ps"]].append(p)
        qs = {}
        for pcp, tc in TC_OF_PCP.items():
            q = f"M2S72Bridge.{eg}.eth[1].macLayer.queue.queue[{tc}]"
            qs[pcp] = ([t for t, _ in run.vec.get((q, "incomingPacketLengths:vector"), [])],
                       [(t, round(float(v) * PS)) for t, v in run.vec.get((q, "queueingTime:vector"), [])],
                       [(t, s) for t, s, _ in changes(run, eg, tc)])
        idx = Counter()
        with open(run.log(eg)) as fh:
            lg = list(csv.DictReader(fh))
        rows = sorted((r for r in lg if r["event"] == "tx" and r["tagged"] == "1" and int(r["etherType"]) != 0x88F7),
                      key=lambda r: ps(r["tTxEnd"]))
        for r in rows:
            t12 = ps(r["egressTime"])
            cand = out.get(t12, [])
            if len(cand) != 1:
                bad("egress-frame", f"{eg} {t12}")
                continue
            f, key = ident(cand[0]["data"])
            if (f["pcp"], f["vid"], f["etherType"]) != (int(r["pcp"]), int(r["vid"]), int(r["etherType"])) \
                    or pcapng.fnv1a64(f["payload"]) != r["txHash"]:
                bad("identity", f"{eg} {t12}")
                continue
            ing = ingress.get((TT.get(int(r["ingressTtId"])), key))
            if ing is None or ing[1] != cand[0]["data"]:
                bad("ingress-identity", f"{eg} {key}")
                continue
            if ps(r["ingressTime"]) != ing[0] or ps(r["residence"]) != t12 - ing[0] or ing[0] >= t12:
                bad("R", f"{eg} {key}")
                continue
            if (eg, key) in seen:
                bad("duplicate", f"{eg} {key}")
            seen.add((eg, key))
            pushes, deq, trans = qs[key[2]]
            k = idx[key[2]]
            idx[key[2]] += 1
            t_in, (t_out, held) = pushes[k], deq[k]
            if t_out - held != t_in or ps(r["tSlot"]) != t_in or ps(r["tDequeue"]) != t_out:
                bad("queue", f"{eg} {key}")
                continue
            if not state_at(trans, t_out):
                bad("gate", f"{eg} {key}: dequeued while closed")
            recs.append({"egress": eg, "key": key, "R": t12 - ing[0], "held": held, "closed_at_enqueue": not state_at(trans, t_in)})
        data_out = [p for p in run.pcap(eg, 1, 2) if ident(p["data"])[0]["etherType"] != 0x88F7]
        if len(rows) != len(data_out):
            bad("count", f"{eg}: {len(rows)} rows vs {len(data_out)} data frames")
        # frames not completely transmitted by the end of the run: M2-S1 'pending' rows (no R). Each must be explained:
        # (a) dequeued with its gate open, its transmission still running at the end; or (b) not dequeued because its
        # gate is closed at the end, or because the port is busy with a frame of kind (a)
        pend = [r for r in lg if r["event"] == "pending" and r["tagged"] == "1"]
        busy = any(ps(r["tDequeue"]) is not None for r in pend)
        for r in pend:
            pushes, deq, trans = qs[int(r["pcp"])]
            k = idx[int(r["pcp"])]
            idx[int(r["pcp"])] += 1
            tdq = ps(r["tDequeue"])
            ok = k < len(pushes) and ps(r["tSlot"]) == pushes[k]
            if tdq is not None:
                ok &= k < len(deq) and deq[k][0] == tdq and state_at(trans, tdq) and tdq + (int(r["payloadLen"]) + 22) * 8 * BIT_PS > T_END
                kind = "in transmission at the end"
            else:
                ok &= not state_at(trans, T_END) or busy
                kind = "held (gate closed at the end)" if not state_at(trans, T_END) else "queued behind a frame in transmission"
            if not ok:
                bad("pending", f"{eg}: pending frame not explained (gate / transmission at the end)")
            pending.append({"egress": eg, "pcp": int(r["pcp"]), "tSlot": ps(r["tSlot"]), "kind": kind})
        for pcp, (pushes, deq, _) in qs.items():
            if idx[pcp] != len(pushes):
                bad("count", f"{eg} PCP {pcp}: {len(pushes)} frames enqueued, {idx[pcp]} transmitted or pending")
    return recs, problems, details


if not (OMNETPP and INET and SIMU5G and os.path.exists(os.path.join(SIMU5G, "src", "libsimu5g.so"))):
    print("SKIP: OMNETPP_ROOT, INET_ROOT and SIMU5G_ROOT must name a built OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1")
    sys.exit(2)

CFGS = ["EPO-gated", "EPO-clocks", "EPON-base1ns", "EPON-unbound", "EPON-future"]
with tempfile.TemporaryDirectory() as res:
    rc = {c: opp_run(c, res) for c in CFGS}
    for c in ("EPO-gated", "EPO-clocks", "EPON-base1ns"):
        check(f"T5b-run {c}: 0.8 s of the N = 2 bridge completes", rc[c].returncode == 0, (rc[c].stdout + rc[c].stderr)[-300:])
    R = {c: Run(res, c) for c in ("EPO-gated", "EPO-clocks", "EPON-base1ns")}
    for cfg in ("EPO-gated", "EPO-clocks"):
        run = R[cfg]
        for tt in TT.values():
            for tc in (5, 1):
                exp = changes(run, tt, tc)
                got = run.gate(tt, 1, tc)
                check(f"T5b-gate {cfg} {tt} TSN port TC{tc}: {len(exp) - 1} transitions equal the common-epoch oracle (ps)",
                      got == [(t, s) for t, s, _ in exp] and len(exp) > 100, f"{len(got)}/{len(exp)}")
            check(f"T5b-gate {cfg} {tt}: the 6 other TSN-port gates and every 5GS-port gate stay open",
                  all(run.gate(tt, 1, tc) == [(0, True)] for tc in (0, 2, 3, 4, 6, 7)) and all(run.gate(tt, 0, tc) == [(0, True)] for tc in range(8)))
        # alignment: the same TT change times at the three translators (within the common range)
        cs = {tt: {(c, s) for t, s, c in changes(run, tt, 5)[1:] if 100 * 10 ** 9 <= c <= 700 * 10 ** 9} for tt in TT.values()}
        ts = {tt: [t for t, _, _ in changes(run, tt, 5)[1:]] for tt in TT.values()}
        check(f"T5b-align {cfg}: NW-TT, DS-TT[0] and DS-TT[1] change TC5 at the same TT times base + k * cycle + boundary "
              f"({len(cs['nwTt'])} changes in [0.1, 0.7] s TT time)",
              cs["nwTt"] == cs["dsTt[0]"] == cs["dsTt[1]"] and len(cs["nwTt"]) > 100
              and all((c % (10 * 10 ** 9)) in (0, 2 * 10 ** 9) for c, _ in cs["nwTt"]))
        if cfg == "EPO-clocks":
            check("T5b-align EPO-clocks: with different TT clocks those common TT times fall at different simulation times "
                  "(NW-TT theta0 1 ms, DS-TT[1] 3.3 ms; DS-TT[0] / DS-TT[1] +-200 ppm)",
                  ts["nwTt"][:20] != ts["dsTt[1]"][:20] and ts["dsTt[0]"][:20] != ts["dsTt[1]"][:20])
            ovd = {tt: sum(O.overdue_count(changes(run, tt, tc), run.ttclock(tt)) for tc in (5, 1)) for tt in TT.values()}
            check(f"T5b-steps EPO-clocks: gate changes jumped over by forward 5G time-update steps (oracle {ovd}) equal "
                  f"each TtGateClock's numOverdueClockEvents",
                  all(run.sca.get((f"M2S72Bridge.{tt}.clock", "numOverdueClockEvents")) == str(ovd[tt]) for tt in TT.values()),
                  str({tt: run.sca.get((f"M2S72Bridge.{tt}.clock", "numOverdueClockEvents")) for tt in TT.values()}))
        recs, probs, det = residence(run)
        held = [x for x in recs if x["closed_at_enqueue"]]
        check(f"T5b-traffic {cfg}: {len(recs)} bridged frames transmitted + {len(pending)} not completely transmitted at the end "
              f"({sorted(Counter(x['kind'] for x in pending).items())}; M2-S1 'pending', no R) = 238 enqueued; {len(held)} arrived while their gate was closed and were held; every "
              f"dequeue with its gate open (common-epoch oracle); M2B-4 residence: identity, t1 / t12 from PCAP, R exact, counted once",
              len(recs) + len(pending) == 238 and len(held) > 50 and not probs, f"{dict(probs)} {det}")
        check(f"T5b-traffic {cfg}: the held frames' R contains the gate wait (R > held time)", all(x["R"] > x["held"] for x in held))
        obs = BD.observe([run.log(tt) for tt in TT.values()])
        st = defaultdict(list)
        rid = {v: k for k, v in TT.items()}
        for x in recs:
            st[(None, rid[x["egress"]], x["key"][2], x["key"][3])].append(x["R"])
        bd_by = defaultdict(list)
        for p in obs["pairs"]:
            bd_by[(None, p["egressTtId"], p["pcp"], p["vid"])].append(p)
        check(f"T5b-stats {cfg}: bridge_delay.py (unchanged) groups {len(obs['pairs'])}; per egress TT / PCP / VID the counts and "
              f"sums equal the oracle's; classes {obs['classes']}",
              obs["classes"]["residence"] == len(recs) and all(sum(p["count"] for p in bd_by[k]) == len(v) and sum(p["sum_ps"] for p in bd_by[k]) == sum(v)
                                                       for k, v in st.items()))
    # ---- negatives
    for c, want in (("EPON-unbound", "no clock (clockModule is empty): a common-epoch gate must not run on simulation time"),
                    ("EPON-future", "is later than the TT clock at initialization")):
        out = rc[c].stdout + rc[c].stderr
        check(f"T5b-negative {c}: refused ({want!r})", rc[c].returncode != 0 and want in out, out[-300:])
    run = R["EPON-base1ns"]
    exp = changes(run, "dsTt[0]", 5)                       # the declared base 0
    got = run.gate("dsTt[0]", 1, 5)
    d = {a[0] - b[0] for a, b in zip(got, exp) if a[0] != b[0]}
    check("T5b-negative EPON-base1ns: a 1 ns base-time error at the DS-TT gates is detected by the oracle (every change 1 ns of "
          "TT time late = 1000 or 1001 ps)", got != [(t, s) for t, s, _ in exp] and d and d <= {1000, 1001}, str(sorted(d)[:3]))
    nw = R["EPON-base1ns"].gate("nwTt", 1, 5) == [(t, s) for t, s, _ in changes(R["EPON-base1ns"], "nwTt", 5)]
    check("T5b-negative EPON-base1ns: the NW-TT gates (correct base) still match - the error is located", nw)

hits = subprocess.run(["git", "-C", REPO, "grep", "-l", "TtEpochGate", "--", "simulations", "src"], capture_output=True, text=True).stdout.split()
allowed = {"simulations/m2/tools/tsnaf_compile.py", "simulations/m2/m2b5/s72-q0-epoch.scfg.ini", "simulations/m2/m2b5/epoch.ini",
           "simulations/m2/m2b5/EpochGateTest.ned", "simulations/m2/check/test_m2b5_epoch_gate.py", "simulations/m2/check/test_m2b5_epoch_bridge.py",
           "simulations/m2/check/test_tsnaf_compile_epoch.py", "simulations/m2/check/m2b5_oracle.py",
           "src/nasctime/m2/TtEpochGate.ned", "src/nasctime/m2/TtEpochGate.h", "src/nasctime/m2/TtEpochGate.cc",
           "simulations/m2/check/test_m2b2_ttgateclock.py"}          # its own default-off allowlist names these files
check("T5b-default-off TtEpochGate is referenced only by its own sources, the compiler, and the M2B-5 test files",
      set(hits) <= allowed, str(sorted(set(hits) - allowed)))

print(f"\nM2B-5 common-epoch bridge tests: {len(PASS)} / {len(PASS) + len(FAIL)} PASS, {len(FAIL)} FAIL")
sys.exit(1 if FAIL else 0)
