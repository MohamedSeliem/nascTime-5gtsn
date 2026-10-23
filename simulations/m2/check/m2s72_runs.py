"""M2-S7.2a run access (migration/m2-s7.2a-design.md rev. 2, 4.4): the per-UE run adapter.

Network M2S72Bridge (ue[k], dsTt[k], talker[k], k = 0 .. numUe-1; one listener, nwTt, upf, gnb1). Every name
is resolved from the run's own files (PCAP file names, the .sca "par" lines), never assumed:
  - numUe from the dsTt[k] PCAP files (and checked against the talker[k] / ue[k] files);
  - UE k's NR MAC node id (its gNB RLC entities rlc-um-<id>-<drb>) from "par ...ue[k].cellularNic.nrMac macNodeId";
  - talker[k]'s and the listener's MAC addresses from their own transmitted frames.
The readers of the earlier checkers are reused unchanged (check_m2s5.frames / read_csv / scalars_all,
pcapng.read / ethernet / simtime_ps, m2s6_runs.read_vectors); this module adds:
  - Run72.ue_view(k): the attributes check_m2s5.Run provides, for the tuple (GM, NW-TT, DS-TT k, slave k);
  - n3_records(): every N3 GTP-U packet of a learning recorder (PCAP truncated at snaplen allowed), with
    direction, TEID, QFI and the inner Ethernet header;
  - dn_records(): every N6 (dnEth) frame of a learning recorder;
  - Eventlog: the parts of an OMNeT++ eventlog needed by F0-7 (module paths, events, method calls, sends).
"""
import os
import re
import struct
import sys
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0], "-", "-", "-", "-"]   # check_m2s5 / oracle_m2s3 read their arguments at import
import check_m2s5 as C5  # noqa: E402  (frames, sel, by_seq, read_csv, scalars_all; unchanged)
sys.argv = _argv
import pcapng  # noqa: E402

NET = "M2S72Bridge"
NS = 1000
SYNC, FU, REQ, RESP, RFU = 0, 8, 2, 3, 10
GPTP_DST = "0180c200000e"


# ---------------------------------------------------------------- PCAP (truncation allowed) ----------------------
def read_pcapng(path):
    """As pcapng.read, but a packet captured shorter than its original length (snaplen) is kept, with
    "orig" = original length. Returns dicts t_ps, dir, linktype, data, orig."""
    with open(path, "rb") as f:
        buf = f.read()
    pos, endian, ifaces, out = 0, "<", [], []
    while pos < len(buf):
        btype = struct.unpack_from(endian + "I", buf, pos)[0]
        if btype == 0x0A0D0D0A:
            magic = struct.unpack_from("<I", buf, pos + 8)[0]
            endian = "<" if magic == 0x1A2B3C4D else ">"
            ifaces = []
        blen = struct.unpack_from(endian + "I", buf, pos + 4)[0]
        body = buf[pos + 8: pos + blen - 4]
        if btype == 1:
            linktype = struct.unpack_from(endian + "H", body, 0)[0]
            tsresol, opos = 6, 8
            while opos + 4 <= len(body):
                code, olen = struct.unpack_from(endian + "HH", body, opos)
                if code == 0:
                    break
                if code == 9:
                    tsresol = body[opos + 4]
                opos += 4 + ((olen + 3) & ~3)
            if tsresol & 0x80 or tsresol > 12:
                raise ValueError(f"{path}: unsupported if_tsresol {tsresol:#x}")
            ifaces.append((linktype, 10 ** (12 - tsresol)))
        elif btype == 6:
            iface, th, tl, caplen, origlen = struct.unpack_from(endian + "IIIII", body, 0)
            data = body[20: 20 + caplen]
            flags, opos = 0, 20 + ((caplen + 3) & ~3)
            while opos + 4 <= len(body):
                code, olen = struct.unpack_from(endian + "HH", body, opos)
                if code == 0:
                    break
                if code == 2:
                    flags = struct.unpack_from(endian + "I", body, opos + 4)[0]
                opos += 4 + ((olen + 3) & ~3)
            linktype, mult = ifaces[iface]
            out.append({"t_ps": ((th << 32) | tl) * mult, "dir": flags & 3, "linktype": linktype, "data": data,
                        "orig": origlen})
        pos += blen
    return out


def eth_header(b):
    """dst, src, vid (0 untagged), etherType, pcp of an Ethernet frame (header only)."""
    if len(b) < 14:
        raise ValueError("short Ethernet header")
    dst, src = b[0:6].hex(), b[6:12].hex()
    et = struct.unpack(">H", b[12:14])[0]
    vid, pcp = 0, -1
    if et == 0x8100:
        if len(b) < 18:
            raise ValueError("short 802.1Q header")
        tci, et = struct.unpack(">HH", b[14:18])
        vid, pcp = tci & 0xFFF, tci >> 13
    return dst, src, vid, et, pcp


def n3_records(path):
    """Every N3 packet: dicts t, dir, teid, qfi, dst, src, vid, et, gtype (gPTP messageType or -1), frag."""
    out = []
    for i, p in enumerate(read_pcapng(path)):
        b = p["data"]
        off = 5 if b[1:3] == b"\xff\x03" else 3
        if struct.unpack(">H", b[off - 2: off])[0] != 0x0021:
            raise ValueError(f"{path}: record {i}: not PPP/IPv4")
        ip = b[off:]
        ihl = (ip[0] & 15) * 4
        ff = struct.unpack(">H", ip[6:8])[0]
        if ip[9] != 17:
            raise ValueError(f"{path}: record {i}: not UDP")
        r = {"i": i, "t": p["t_ps"], "dir": p["dir"], "frag": bool(ff & 0x3FFF)}
        if ff & 0x1FFF:          # non-first fragment: no GTP-U header
            r.update(teid=None, qfi=None, dst=None, src=None, vid=None, et=None, gtype=-1, gseq=-1)
            out.append(r)
            continue
        g = ip[ihl + 8:]
        flags, mtype = g[0], g[1]
        if mtype != 0xFF:
            raise ValueError(f"{path}: record {i}: GTP-U message type {mtype}")
        teid = struct.unpack(">I", g[4:8])[0]
        gl, qfi = 8, None
        if flags & 0x07:
            gl, nxt = 12, g[11]
            while nxt:
                el = g[gl] * 4
                if nxt == 0x85:   # PDU session container: QFI in the low 6 bits of its second octet
                    qfi = g[gl + 2] & 0x3F
                nxt = g[gl + el - 1]
                gl += el
        inner = g[gl:]
        dst, src, vid, et, pcp = eth_header(inner)
        gtype, gseq = -1, -1
        if et == 0x88F7:
            hdr = 18 if inner[12:14] == b"\x81\x00" else 14
            gtype = inner[hdr] & 15
            gseq = int.from_bytes(inner[hdr + 30: hdr + 32], "big")
        r.update(teid=teid, qfi=qfi, dst=dst, src=src, vid=vid, et=et, gtype=gtype, gseq=gseq)
        out.append(r)
    return out


def dn_records(path):
    out = []
    for i, p in enumerate(read_pcapng(path)):
        if p["linktype"] != 1:
            raise ValueError(f"{path}: record {i}: linktype {p['linktype']}")
        dst, src, vid, et, pcp = eth_header(p["data"])
        out.append({"i": i, "t": p["t_ps"], "dir": p["dir"], "dst": dst, "src": src, "vid": vid, "et": et})
    return out


def fmt_t(ps):
    """Exact simulation time in seconds (12 decimals)."""
    sign = "-" if ps < 0 else ""
    ps = abs(ps)
    return f"{sign}{ps // 10 ** 12}.{ps % 10 ** 12:012d} s"


def is_unicast(mac):
    return not (int(mac[0:2], 16) & 1)


# ---------------------------------------------------------------- .sca "par" lines --------------------------------
def pars(sca_path):
    out = {}
    with open(sca_path) as fh:
        for line in fh:
            if line.startswith("par "):
                p = line.rstrip("\n").split(" ", 3)
                out[(p[1], p[2])] = p[3]
    return out


# ---------------------------------------------------------------- run adapter --------------------------------------
class UeView:
    """The attributes of check_m2s5.Run for the tuple (GM, NW-TT, DS-TT k, slave k) of an M2S72Bridge run."""
    def __init__(self, run, k):
        self.k, self.run = k, run
        P = run.P
        self.net = NET
        self.gmn, self.nwn, self.dsn, self.sln = "listener", "nwTt", f"dsTt[{k}]", f"talker[{k}]"
        self.gm, self.nw1, self.nw0 = run.gm, run.nw1, run.nw0
        self.ds0, self.ds1 = C5.frames(P(f"dsTt[{k}]", 0)), C5.frames(P(f"dsTt[{k}]", 1))
        self.sl = C5.frames(P(f"talker[{k}]", 0))
        self.ue = C5.frames(P(f"ue[{k}]", 0))
        self.dn, self.n3path = run.dn, run.n3path
        self.station = f"{NET}.talker[{k}]"
        tc = os.path.join(run.ldir, f"{NET}.dsTt[{k}].eth[1].trafficConditionerLayer")
        self.nwlog, self.nweng = run.nwlog, run.nweng
        self.dslog = C5.read_csv(tc + ".syncOut.sync.csv")
        self.dseng = C5.read_csv(tc + ".engine.pdelay.csv")
        mon = tc + ".monitor.monitor.csv"
        self.monlog = C5.read_csv(mon) if os.path.exists(mon) else None
        self.nodeId = run.node_id[k]


class Run72:
    def __init__(self, runs, cfg, rep=0):
        self.cfg, self.rep = cfg, rep
        self.base = os.path.join(runs, cfg)
        self.pdir = os.path.join(self.base, "pcap", f"{cfg}-{rep}")
        self.ldir = os.path.join(self.base, "m2log", f"{cfg}-{rep}")
        self.sca_path = os.path.join(self.base, cfg, f"{rep}.sca")
        self.vec_path = os.path.join(self.base, cfg, f"{rep}.vec")
        self.elog_path = os.path.join(self.base, cfg, f"{rep}.elog")
        self.P = lambda n, i: os.path.join(self.pdir, f"{NET}.{n}.pcapRecorder[{i}].pcapng")  # noqa: E731
        files = os.listdir(self.pdir)
        idx = {}
        for kind in ("dsTt", "talker", "ue"):
            idx[kind] = sorted(int(m.group(1)) for f in files for m in [re.fullmatch(rf"{NET}\.{kind}\[(\d+)\]\.pcapRecorder\[0\]\.pcapng", f)] if m)
        n = len(idx["dsTt"])
        for kind, v in idx.items():
            if v != list(range(n)):
                raise ValueError(f"{cfg}: {kind} PCAP indices {v}, expected 0..{n - 1}")
        self.n = n
        self.gm = C5.frames(self.P("listener", 0))
        self.nw1, self.nw0 = C5.frames(self.P("nwTt", 1)), C5.frames(self.P("nwTt", 0))
        self.dn = C5.frames(self.P("upf", 1))
        self.n3path = self.P("upf", 0)
        self.learn_n3 = self.P("upf", 2) if os.path.exists(self.P("upf", 2)) else None
        self.learn_dn = self.P("upf", 3) if os.path.exists(self.P("upf", 3)) else None
        tc = os.path.join(self.ldir, f"{NET}.nwTt.eth[1].trafficConditionerLayer")
        self.nwlog = C5.read_csv(tc + ".syncIn.sync.csv")
        self.nweng = C5.read_csv(tc + ".engine.pdelay.csv")
        self.par = pars(self.sca_path)
        self.node_id = {}
        for k in range(n):
            v = self.par.get((f"{NET}.ue[{k}].cellularNic.nrMac", "macNodeId"))
            if v is None:
                raise ValueError(f"{cfg}: no nrMac macNodeId for ue[{k}]")
            self.node_id[k] = int(v)
        if len(set(self.node_id.values())) != n:
            raise ValueError(f"{cfg}: duplicate NR MAC node ids {self.node_id}")
        self._ues = {}

    def ue_view(self, k):
        if k not in self._ues:
            self._ues[k] = UeView(self, k)
        return self._ues[k]

    def mac_of(self, frames):
        """The source MAC of a station's transmitted frames (all must agree)."""
        s = {f["f"]["src"] for f in frames if f["dir"] == 2}
        if len(s) != 1:
            raise ValueError(f"{self.cfg}: station frames with source MACs {s}")
        return s.pop()


# ---------------------------------------------------------------- eventlog (F0-7) ----------------------------------
class Eventlog:
    """Module paths (MC lines), and per event: time (ps), module, message, and the ordered list of
    (kind, ...) items inside it: ("send", packet id, target module) for BS lines, ("call", from, to, method)
    for CMB lines. Only the recorded interval is present."""
    def __init__(self, path):
        self.mod = {}
        parent, name = {}, {}
        self.events = []
        self.by_n = {}
        cur = None
        with open(path) as fh:
            for line in fh:
                c = line[:3]
                if c.startswith("E #"):
                    p = line.split()
                    cur = {"n": int(p[2]), "t": pcapng.simtime_ps(p[4]), "m": int(p[6]), "ce": int(p[8]),
                           "msg": int(p[10]), "items": []}
                    self.events.append(cur)
                    self.by_n[cur["n"]] = cur
                elif c == "MC ":
                    p = line.split()
                    d = dict(zip(p[1::2], p[2::2]))
                    i = int(d["id"])
                    nm = d["n"]
                    if "ix" in d:
                        nm = f"{nm}[{d['ix']}]"
                    name[i] = nm
                    parent[i] = int(d["pid"]) if "pid" in d else None
                elif c == "BS " and cur is not None:
                    p = line.split()
                    d = dict(zip(p[1::2], p[2::2]))
                    cur["items"].append(("send", int(d["id"]), int(d["m"]) if "m" in d else -1))
                elif c == "CMB" and cur is not None:
                    p = line.split()
                    d = dict(zip(p[1::2], p[2::2]))
                    cur["items"].append(("call", int(d["sm"]), int(d["tm"]), d.get("m", "")))
        for i in name:
            parts, j = [], i
            while j is not None:
                parts.append(name[j])
                j = parent.get(j)
            self.mod[i] = ".".join(reversed(parts))

    def ids(self, pred):
        return {i for i, p in self.mod.items() if pred(p)}

    def origin(self, ev, stop):
        """Follow the cause-event chain of ev back to the first event whose module is in stop
        (a set of module ids); returns that event, or None if the chain leaves the recorded log."""
        seen = 0
        while ev is not None and seen < 10000:
            if ev["m"] in stop:
                return ev
            ev = self.by_n.get(ev["ce"])
            seen += 1
        return None

    def table_calls(self, table_path, methods):
        """[(event, method)] for every call into the module table_path with a method in methods."""
        tid = [i for i, p in self.mod.items() if p == table_path]
        if len(tid) != 1:
            raise ValueError(f"eventlog: module {table_path} found {len(tid)} times")
        tid = tid[0]
        return [(ev, it[3]) for ev in self.events for it in ev["items"] if it[0] == "call" and it[2] == tid and it[3] in methods]
