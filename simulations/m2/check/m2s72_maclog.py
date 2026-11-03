"""M2-S7.2a Stage 5: parser of the M2S72-MACLOG stdout capture (gNB MAC, gNB RLC UM TX, UE RLC UM RX log lines,
prefix "<simulation time>|<context module path>|"), gzip-compressed by m2s72.sh.

Every event class keeps its own identity (review 2026-11-03 item 7): scheduler grants (DL / UL, per connection),
MAC PDU creation, HARQ TX insertion, HARQ TX feedback (ACK / NACK), HARQ-process MAC PDU deletions
("no available process", LteMacEnb.cc:585), MAC buffer overflows (LteMacEnb.cc:702, LteMacBase.cc:335), MAC buffer
occupancy, RLC UM TX SDU arrivals / PDUs / drops, RLC UM RX deliveries / discards. A line of an observed module that
looks like loss ("drop", "discard", "full", "no available", "delet", "lost") but matches no known class is kept as
UNCLASSIFIED (the checker fails closed on it). Observation only: nothing here changes a run.
"""
import gzip
import re
from collections import Counter, defaultdict

S, MS = 10 ** 12, 10 ** 9


def t_ps(s):
    a, _, b = s.partition(".")
    return int(a) * S + int((b + "0" * 12)[:12])


R_CID = r"MacCid\(nodeId=(\d+), lcid=(\d+)\)"
R_GRANT_MAXCI = re.compile(r"LteMaxCI::schedule granted (\d+) bytes to connection " + R_CID)
R_GRANT_QOS = re.compile(r"QoSAwareScheduler::Grant cid=" + R_CID + r" limit=\S+ granted=(\d+)B")
R_PDU = re.compile(r"PDU Maker created PDU: \((\d+) B\).*containing (\d+) SDUs")
R_INSERT = re.compile(r"H-ARQ TX: new pdu \(id (\d+) \) inserted into process (\d+) codeword id: (\d+) for node with id (\d+)")
R_FB = re.compile(r"H-ARQ TX: feedback received for process (\d+) codeword (\d+) result is (ACK|NACK)")
R_BUF = re.compile(r"LteMacBuffers : Using buffer for " + R_CID + r", Space left in the Queue: (-?\d+)")
R_OVF = re.compile(r"LteMacBuffers : queue" + R_CID + r" is full - cannot buffer packet (\d+)")
R_OVF2 = re.compile(r"LteMacBuffers : Dropped packet: queue " + R_CID + r" is full")
R_RLC_SDU = re.compile(r"RlcUmTxEntity::handleSdu - Received SDU from upper layer, size (\d+)")
R_RLC_PDU = re.compile(r"NrRlcUmTxEntity::rlcPduMake - send PDU size (\d+) to lower layer")
R_RLC_DROP = re.compile(r"RlcUmTxEntity : Dropping packet (\S+) \(queue full\)")
R_RX_DELIV = re.compile(r"NrRlcUmRxEntity::toPdcp - deliver SDU of (\d+) bytes")
R_RX_DISC = re.compile(r"(Discard the PDU|discarding duplicate complete SDU|Discarding SN=)")
LOSSY = re.compile(r"(?i)(drop|discard|is full|no available|delet|lost)")
KNOWN_BENIGN = ("no process selected in H-ARQ buffer, nothing to do",)    # empty H-ARQ selection: not a loss
DL_BEGIN, DL_END = "= DOWNLINK =", "= END DOWNLINK ="
UL_BEGIN, UL_END = "= UPLINK =", "= END UPLINK ="


class MacLog:
    def __init__(self, path, gnb="M2S72Bridge.gnb1.cellularNic.mac", alias=None):
        """alias: {logged module name: full path} for captures made with a name-only prefix (%N, the P1 / P2
        observation twins); it must map every logged name, else the line is not classified"""
        self.path = path
        self.grants = []            # (t, dir, node, lcid, bytes)
        self.pdus = []              # dicts: t, bytes, sdus, deleted, proc, node, pid
        self.feedback = []          # (t, proc, result)
        self.overflow = []          # (t, node, lcid, kind)
        self.space = defaultdict(list)   # (node, lcid) -> [(t, space left)]
        self.rlc_tx = defaultdict(lambda: {"sdu": [], "pdu": [], "drop": []})   # module path -> lists of (t, size)
        self.rlc_rx = defaultdict(lambda: {"deliv": [], "disc": []})
        self.unclassified = []
        self.ttis = 0
        self.lines = Counter()
        self.fingerprint = None
        section, cur = None, None
        with gzip.open(path, "rt", errors="replace") as fh:
            for line in fh:
                if line.startswith("<!> Fingerprint"):
                    m = re.search(r"calculated: (\S+),", line)
                    self.fingerprint = m.group(1) if m else line.strip()
                    continue
                p = line.rstrip("\n").split("|", 2)
                if len(p) < 3 or not p[0][:1].isdigit():
                    continue
                t, mod, msg = t_ps(p[0]), p[1], p[2]
                if alias is not None:
                    mod = alias.get(mod, mod)
                if mod == gnb:
                    self.lines["mac"] += 1
                    if "AmcPilotAuto" in msg or "LteAllocator" in msg or "pushFeedback" in msg:
                        continue
                    if DL_BEGIN in msg:
                        section = "DL"
                    elif UL_BEGIN in msg:
                        section = "UL"
                    elif DL_END in msg or UL_END in msg:
                        section = None
                    if "ENB MAIN LOOP" in msg and "END" not in msg:
                        self.ttis += 1
                    m = R_GRANT_MAXCI.search(msg)
                    if m:
                        self.grants.append((t, section, int(m.group(2)), int(m.group(3)), int(m.group(1))))
                        continue
                    m = R_GRANT_QOS.search(msg)
                    if m:
                        self.grants.append((t, section, int(m.group(1)), int(m.group(2)), int(m.group(3))))
                        continue
                    if "START LteMacEnb::macPduMake" in msg:
                        cur = []
                        continue
                    if "END LteMacEnb::macPduMake" in msg:
                        cur = None
                        continue
                    m = R_PDU.search(msg)
                    if m:
                        d = {"t": t, "bytes": int(m.group(1)), "sdus": int(m.group(2)), "deleted": False, "proc": None, "node": None, "pid": None}
                        self.pdus.append(d)
                        if cur is not None:
                            cur.append(d)
                        continue
                    if "no available process for this MAC PDU" in msg:
                        if cur:
                            cur[-1]["deleted"] = True
                        else:
                            self.unclassified.append((t, mod, msg))
                        continue
                    m = R_INSERT.search(msg)
                    if m:
                        if cur:
                            cur[-1].update(pid=int(m.group(1)), proc=int(m.group(2)), node=int(m.group(4)))
                        else:
                            self.unclassified.append((t, mod, msg))
                        continue
                    m = R_FB.search(msg)
                    if m:
                        self.feedback.append((t, int(m.group(1)), m.group(3)))
                        continue
                    m = R_BUF.search(msg)
                    if m:
                        self.space[(int(m.group(1)), int(m.group(2)))].append((t, int(m.group(3))))
                        continue
                    m = R_OVF.search(msg) or R_OVF2.search(msg)
                    if m:
                        self.overflow.append((t, int(m.group(1)), int(m.group(2)), "queue full"))
                        continue
                    if LOSSY.search(msg) and not any(b in msg for b in KNOWN_BENIGN):
                        self.unclassified.append((t, mod, msg))
                elif ".rlc-um-" in mod and mod.endswith(".tx"):
                    self.lines["rlc-tx"] += 1
                    e = self.rlc_tx[mod]
                    m = R_RLC_SDU.search(msg)
                    if m:
                        e["sdu"].append((t, int(m.group(1))))
                        continue
                    m = R_RLC_PDU.search(msg)
                    if m:
                        e["pdu"].append((t, int(m.group(1))))
                        continue
                    m = R_RLC_DROP.search(msg)
                    if m:
                        e["drop"].append((t, m.group(1)))
                        continue
                    if LOSSY.search(msg):
                        self.unclassified.append((t, mod, msg))
                elif ".nrRlc-um-" in mod and mod.endswith(".rx"):
                    self.lines["rlc-rx"] += 1
                    e = self.rlc_rx[mod]
                    m = R_RX_DELIV.search(msg)
                    if m:
                        e["deliv"].append((t, int(m.group(1))))
                        continue
                    if R_RX_DISC.search(msg):
                        e["disc"].append((t, msg))
                        continue
                    if LOSSY.search(msg):
                        self.unclassified.append((t, mod, msg))
                else:
                    self.lines["other"] += 1

    # ------------------------------------------------------------------------------------------------- summaries
    def deletions(self, node=None):
        return [d for d in self.pdus if d["deleted"] and (node is None or d["node"] in (None, node))]

    def max_busy(self):
        """largest number of HARQ TX processes holding an unacknowledged PDU at once (insert -> its ACK / NACK feedback;
        valid at N = 1, where every DL process belongs to the one UE)"""
        ev = [(d["t"], 0, d["proc"]) for d in self.pdus if d["proc"] is not None] + [(t, 1, p) for t, p, _ in self.feedback]
        busy, best = set(), 0
        for t, kind, p in sorted(ev):
            if kind == 0:
                busy.add(p)
                best = max(best, len(busy))
            else:
                busy.discard(p)
        return best

    def grant_bytes(self, direction, node, lcid=None):
        return [(t, b) for t, d, n, l, b in self.grants if d == direction and n == node and (lcid is None or l == lcid)]

    def summary(self):
        fb = Counter(r for _, _, r in self.feedback)
        return {"ttis": self.ttis, "grants_dl": sum(1 for g in self.grants if g[1] == "DL"), "grants_ul": sum(1 for g in self.grants if g[1] == "UL"),
                "grants_nosection": sum(1 for g in self.grants if g[1] is None), "mac_pdus": len(self.pdus),
                "harq_inserts": sum(1 for d in self.pdus if d["proc"] is not None), "harq_deletions": len(self.deletions()),
                "ack": fb["ACK"], "nack": fb["NACK"], "overflow": len(self.overflow),
                "rlc_tx_drops": sum(len(e["drop"]) for e in self.rlc_tx.values()),
                "rlc_rx_discards": sum(len(e["disc"]) for e in self.rlc_rx.values()),
                "unclassified": len(self.unclassified), "max_busy_harq": self.max_busy(),
                "min_space": {k: min(s for _, s in v) for k, v in self.space.items()}}
