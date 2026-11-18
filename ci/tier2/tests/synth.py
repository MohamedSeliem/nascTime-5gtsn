"""Synthetic M2S4U-shaped evidence for the offline tests ONLY (never evidence of anything): pcapng captures, engine CSV
logs and a scalar file in the layout and formats read by check_m2s4.py's U1 evaluation, consistent with a 50 ns link."""
import os
import struct
import zlib

NS, FT, PROP = 1000, (72 + 8) * 8 * 1000, 50 * 1000
REQ, RESP, RFU = 2, 3, 10
GPTP = "0180c200000e"
MAC = {"ttA": "0aaa00000003", "ttB": "0aaa00000004"}
IDS = {"ttA": 0x0A, "ttB": 0x0B}
COUNTERS = ("lost", "multipleResp", "orphanFollowUp", "staleSeq", "notForUs", "lateDuplicateResp", "lateDuplicateFU",
            "lateAfterFault", "malformed", "republished", "loopback")


def eth(dst, src, payload, bad_fcs=False):
    f = bytes.fromhex(dst) + bytes.fromhex(src) + struct.pack(">H", 0x88F7) + payload
    fcs = zlib.crc32(f) & 0xFFFFFFFF
    return f + struct.pack("<I", fcs ^ (1 if bad_fcs else 0))


def gptp(mtype, spi, seq, ts=None, reqport=None):
    b = bytearray(54)
    b[0], b[1] = (1 << 4) | mtype, 2
    b[2:4] = struct.pack(">H", 54)
    b[20:28], b[28:30], b[30:32] = spi[0].to_bytes(8, "big"), spi[1].to_bytes(2, "big"), seq.to_bytes(2, "big")
    if ts is not None:
        s, n = divmod(ts // NS, 10 ** 9)
        b[34:40], b[40:44] = s.to_bytes(6, "big"), n.to_bytes(4, "big")
    if reqport:
        b[44:52], b[52:54] = reqport[0].to_bytes(8, "big"), reqport[1].to_bytes(2, "big")
    return bytes(b)


def _opt(code, val):
    return struct.pack("<HH", code, len(val)) + val + b"\0" * ((4 - len(val) % 4) % 4)


def _block(t, body):
    body += b"\0" * ((4 - len(body) % 4) % 4)
    n = 12 + len(body)
    return struct.pack("<II", t, n) + body + struct.pack("<I", n)


def pcapng(packets, shb_note=b""):
    """packets: list of (end_ps, dir, data)"""
    out = _block(0x0A0D0D0A, struct.pack("<IHHq", 0x1A2B3C4D, 1, 0, -1) + (_opt(4, shb_note) + _opt(0, b"") if shb_note else b""))
    out += _block(1, struct.pack("<HHI", 1, 0, 0) + _opt(9, b"\x0c") + _opt(0, b""))
    for t, d, data in packets:
        body = struct.pack("<IIIII", 0, t >> 32, t & 0xFFFFFFFF, len(data), len(data)) + data + b"\0" * ((4 - len(data) % 4) % 4)
        out += _block(6, body + _opt(2, struct.pack("<I", d)) + _opt(0, b""))
    return out


def make(out, n=30, variant=None):
    """Writes <out>/runs/M2S4U/... ; returns the list of written paths."""
    runs = os.path.join(out, "runs", "M2S4U")
    pdir, ldir, sdir = (os.path.join(runs, x) for x in ("pcap/M2S4U-0", "m2log/M2S4U-0", "M2S4U"))
    for d in (pdir, ldir, sdir):
        os.makedirs(d, exist_ok=True)
    cap = {"ttA": [], "ttB": []}
    log = {"ttA": [], "ttB": []}
    for X, Y, base in (("ttA", "ttB", 1_000_000_000), ("ttB", "ttA", 51_000_000_000)):
        idx, idy = IDS[X], IDS[Y]
        for k in range(n):
            t1 = base + k * 100_000_000_000
            t2, t3 = t1 + PROP, t1 + PROP + 10_000_000
            t4, t5 = t3 + PROP, t3 + FT + 96 * NS
            req = eth(GPTP, MAC[X], gptp(REQ, (idx, 1), k))
            resp = eth(GPTP, MAC[Y], gptp(RESP, (idy, 1), k, ts=t2, reqport=(idx, 1)))
            rfu = eth(GPTP, MAC[Y], gptp(RFU, (idy, 1), k, ts=t3, reqport=(idx, 1)))
            cap[X] += [(t1 + FT, 2, req), (t4 + FT, 1, resp), (t5 + PROP + FT, 1, rfu)]
            cap[Y] += [(t2 + FT, 1, req), (t3 + FT, 2, resp), (t5 + FT, 2, rfu)]
            log[X] += [{"event": "rx", "tA": t4, "tB": t4 + FT}, {"event": "rx", "tA": t5 + PROP, "tB": t5 + PROP + FT}]
            d = 50_000 + (1 if variant == "D-off-by-1" and X == "ttA" and k == 3 else 0)
            log[X].append({"event": "measure", "seq": k, "t1": t1, "t2": t2, "t3": t3, "t4": t4, "D": d})
            log[Y].append({"event": "rx", "tA": t2, "tB": t2 + FT})
    if variant == "republish":
        log["ttB"].append({"event": "republish", "seq": 2, "t1": 0, "t2": 0, "t3": 0, "t4": 0, "D": 50000})
    if variant == "unterminated":
        cap["ttA"].append((999_000_000_000, 1, eth(GPTP, MAC["ttB"], gptp(REQ, (0x0B, 1), 999))))
    paths = {}
    for X in ("ttA", "ttB"):
        p = os.path.join(pdir, f"M2S4LinkTest.{X}.pcapRecorder[0].pcapng")
        data = pcapng(sorted(cap[X], key=lambda c: c[0]))
        if variant == "truncated-pcap" and X == "ttB":
            data = data[:-30]
        if not (variant == "missing-pcap" and X == "ttA"):
            open(p, "wb").write(data)
        paths[f"pcap-{X}"] = p
        c = os.path.join(ldir, f"M2S4LinkTest.{X}.eth[1].trafficConditionerLayer.engine.pdelay.csv")
        if not (variant == "missing-csv" and X == "ttB"):
            with open(c, "w") as f:
                f.write("event,seq,t1,t2,t3,t4,D,tA,tB\n")
                for r in sorted(log[X], key=lambda r: r.get("tA", r.get("t4", 0))):
                    f.write(",".join(str(r.get(k, "")) for k in ("event", "seq", "t1", "t2", "t3", "t4", "D", "tA", "tB")) + "\n")
        paths[f"csv-{X}"] = c
    sca = os.path.join(sdir, "0.sca")
    lines = ["version 3", "run M2S4U-0-20260101-00:00:00-1", "attr configname M2S4U", "attr network M2S4LinkTest",
             "attr repetition 0", "attr seedset 0", "attr runnumber 0"]
    for X in ("ttA", "ttB"):
        for c in COUNTERS:
            v = 1 if (variant == "counter" and X == "ttA" and c == "lost") else 0
            lines.append(f"scalar M2S4LinkTest.{X}.eth[1].trafficConditionerLayer.engine {c} {v}")
        lines.append(f"scalar M2S4LinkTest.{X}.eth[1].trafficConditionerLayer.engine selfTestPassed "
                     f"{0 if variant == 'selftest' and X == 'ttB' else 1}")
    if variant != "missing-sca":
        open(sca, "w").write("\n".join(lines) + "\n")
    open(os.path.join(sdir, "0.vec"), "w").write("version 3\nvector 0 M2S4LinkTest.stA x ETV\n0\t1\t0\t1\n")
    open(os.path.join(sdir, "0.vci"), "w").write("version 3\nfile 1 1\n")
    paths["sca"] = sca
    return paths
