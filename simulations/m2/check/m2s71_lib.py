"""M2-S7.1 run access and independent analyses (migration/m2-s7.1-design.md rev. 3).

Everything here is computed from recorded outputs: PCAP (stations, translator ports, N3), the RLC
statistics of the gNB TX and UE RX entities, the DS-TT corrector log and the slave's vectors. The
monitor's own log is compared with these values, never used as truth (Q3). Times are integer ps.

Definitions (design 3.5, 5):
  cohort     Syncs whose transmission starts on the GM wire (listener eth[0], outbound) before 10 s,
             with their Follow_Ups (same sequenceId) wherever and whenever they occur
  TSi        first bit of the Sync at the NW-TT eth[1] (inbound PCAP)
  TSe        first bit of the Sync at the DS-TT eth[1] (outbound PCAP)
  Res        TSe - TSi (M2-S5 definition)
  lag        Follow_Up reception end at the DS-TT eth[0] (inbound PCAP; the event in which TtSyncEgress
             first sees it) - TSe of its Sync; negative when the Follow_Up arrives before its Sync left
  used       the slave receives the Follow_Up while the last Sync it received has the same sequenceId
             (INET Gptp::processFollowUp, Gptp.cc:364)
"""
import os
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s6_runs as RR  # noqa: E402
C5 = RR.C5

NS, MS, S = 1000, 10 ** 9, 10 ** 12
SYNC, FU = 0, 8
T_COHORT = 10 * S
INF = float("inf")

# option -> (gPTP DRB for Sync, for Follow_Up, RLC mode, experimental, scheduler)
OPTIONS = {
    "q0": (1, 1, "um", False, "MAXCI"), "q0p": (1, 1, "um", False, "QOS_PF"),
    "qa": (4, 4, "um", False, "MAXCI"), "qb": (4, 4, "am", False, "MAXCI"),
    "qc": (4, 5, "um", True, "MAXCI"), "qc2": (4, 5, "am", True, "MAXCI"),
    "qdu": (4, 4, "um", False, "QOS_PF"), "qda": (4, 4, "am", False, "QOS_PF"),
    "qd2": (4, 5, "um", True, "QOS_PF"),
}
LABEL = {"q0": "Q-0", "q0p": "Q-0p", "qa": "Q-a", "qb": "Q-b", "qc": "Q-c", "qc2": "Q-c'", "qdu": "Q-d (UM)",
         "qda": "Q-d (AM)", "qd2": "Q-d'"}
QFI = {"q0": (None, None), "q0p": (None, None), "qa": (10, 10), "qb": (10, 10), "qc": (10, 11), "qc2": (10, 11),
       "qdu": (10, 10), "qda": (10, 10), "qd2": (10, 11)}


def parse_cfg(cfg):
    """M2S71-<opt>-<variant>[-h16] -> (opt, variant, harq)"""
    p = cfg.split("-")
    opt = p[1]
    rest = p[2:]
    h16 = rest[-1] == "h16"
    if h16:
        rest = rest[:-1]
    return opt, "-".join(rest), 16 if h16 else 5


def entity(opt, drb, side):
    mode = OPTIONS[opt][2] if drb != 1 else "um"
    return f"gnb1.cellularNic.rlc-{mode}-2049-{drb}.tx" if side == "tx" else f"ue[0].cellularNic.nrRlc-{mode}-1-{drb}.rx"


class Run:
    def __init__(self, root, cfg, rep):
        self.root, self.cfg, self.rep = root, cfg, rep
        self.R = C5.Run(root, cfg, rep)
        self.R.prepare()
        self.V = RR.read_vectors(self.R.vec_path)
        self.mon = C5.read_csv(os.path.join(self.R.ldir, "M1Bridge.dsTt.eth[1].trafficConditionerLayer.monitor.monitor.csv"))
        self.end = self.sim_end()

    def vec(self, mod, name):
        return self.V.get((f"M1Bridge.{mod}", name), [])

    def sim_end(self):
        for line in open(self.R.sca_path):
            if line.startswith("attr sim-time-limit") or line.startswith("config sim-time-limit"):
                v = line.split(None, 2)[2].strip().strip('"')
                return int(round(float(v.rstrip("s")) * S))
        raise ValueError("no sim-time-limit in " + self.R.sca_path)

    # --- PCAP views -------------------------------------------------------------------------
    def gm_tx(self, typ):
        return {f["seq"]: f for f in C5.sel(self.R.gm, 2, typ)}

    def first(self, fr, direction, typ):
        out = {}
        for f in C5.sel(fr, direction, typ):
            out.setdefault(f["seq"], f)
        return out

    def cohort(self, t=T_COHORT):
        """sequenceIds of the Syncs whose GM-wire transmission starts before t"""
        return sorted(s for s, f in self.gm_tx(SYNC).items() if f["start"] < t)


def ds_events(run):
    ev = defaultdict(list)
    for r in run.R.dslog:
        if r.get("seq", "") not in ("", None) and r.get("msgType") == "8":
            ev[int(r["seq"])].append(r["event"])
    return ev


def slave_use(run):
    """{seq: 'used' | 'ignored'} for every Follow_Up received by the slave, by INET's rule"""
    last_sync, out = None, {}
    for f in run.R.sl:
        if f["dir"] != 1 or f["type"] not in (SYNC, FU):
            continue
        if f["type"] == SYNC:
            last_sync = f["seq"]
        else:
            out.setdefault(f["seq"], "used" if f["seq"] == last_sync else "ignored")
    return out


# --- RLC replay (UM, NR SO framing: the M1 O-tail model, unchanged header rules) -------------
def replay_um(sdus, pdus):
    """sdus [(t, size)], pdus [(t, size)] of one TX entity. Returns (done [(arr, size, t_last_pdu)],
    slots {t: {...}}, left [queue items])."""
    queue, i, done, slots = [], 0, [], {}
    for t, s in pdus:
        while i < len(sdus) and sdus[i][0] <= t:
            queue.append({"arr": sdus[i][0], "size": int(sdus[i][1]), "sent": 0})
            i += 1
        sl = slots.setdefault(t, {"pdus": [], "before": [(q["size"] - q["sent"], q["sent"] == 0) for q in queue], "cut": []})
        s = int(s)
        if not queue:
            raise ValueError(f"PDU at {t} with an empty queue")
        h = queue[0]
        if h["sent"] == 0:
            pay = h["size"] if s == h["size"] + 1 else s - 2
            if pay < h["size"]:
                sl["cut"].append(h["arr"])
        else:
            pay = s - 4
        sl["pdus"].append(s)
        h["sent"] += pay
        if h["sent"] >= h["size"]:
            done.append((h["arr"], h["size"], t))
            queue.pop(0)
    while i < len(sdus):
        queue.append({"arr": sdus[i][0], "size": int(sdus[i][1]), "sent": 0})
        i += 1
    return done, slots, queue


def rlc(run, opt, drb):
    tx = entity(opt, drb, "tx")
    rx = entity(opt, drb, "rx")
    sdus = [(t, int(float(v))) for t, v in run.vec(tx, "receivedPacketFromUpperLayer:vector(packetBytes)")]
    pdus = [(t, int(float(v))) for t, v in run.vec(tx, "sentPduSize:vector")]
    dl = [(t, int(float(v))) for t, v in run.vec(rx, "sentPacketToUpperLayer:vector(packetBytes)")]
    rxpdu = [(t, int(float(v))) for t, v in run.vec(rx, "receivedPacketFromLowerLayer:vector(packetBytes)")]
    return {"tx": tx, "rx": rx, "sdus": sdus, "pdus": pdus, "deliv": dl, "rxpdus": rxpdu}


def pct(vals, q):
    """q-quantile (nearest rank, 0 < q <= 1) of a list that may contain +inf"""
    if not vals:
        return None
    v = sorted(vals)
    k = max(0, min(len(v) - 1, -(-int(q * 1000) * len(v) // 1000) - 1))
    return v[k]


def mean_ci(xs):
    """mean and 95 % t-interval half width over replications (seeds); inf-aware"""
    import math
    xs = list(xs)
    n = len(xs)
    if n == 0:
        return None, None
    if any(math.isinf(x) for x in xs):
        return INF, None
    m = sum(xs) / n
    if n < 2:
        return m, None
    sd = (sum((x - m) ** 2 for x in xs) / (n - 1)) ** 0.5
    t = {2: 12.706, 3: 4.303, 4: 3.182, 5: 2.776, 6: 2.571, 7: 2.447, 8: 2.365, 9: 2.306, 10: 2.262}.get(n, 1.96)
    return m, t * sd / n ** 0.5
