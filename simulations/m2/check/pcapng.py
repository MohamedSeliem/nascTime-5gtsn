"""Minimal pcapng reader (SHB / IDB with if_tsresol / EPB with epb_flags), as written by
INET 4.7's PcapngWriter. Timestamps are returned as integer picoseconds when the
interface resolution is 10^-n with n <= 12 (exact integer arithmetic, no floats)."""
import struct
import zlib

INBOUND, OUTBOUND = 1, 2


def read(path):
    """Returns a list of dicts: t_ps, dir (1 inbound, 2 outbound, 0 unknown), linktype, data."""
    with open(path, "rb") as f:
        buf = f.read()
    pos, endian, ifaces, out = 0, "<", [], []
    while pos < len(buf):
        btype = struct.unpack_from(endian + "I", buf, pos)[0]
        if btype == 0x0A0D0D0A:  # SHB: byte-order magic decides endianness
            magic = struct.unpack_from("<I", buf, pos + 8)[0]
            endian = "<" if magic == 0x1A2B3C4D else ">"
            ifaces = []
        blen = struct.unpack_from(endian + "I", buf, pos + 4)[0]
        body = buf[pos + 8: pos + blen - 4]
        if btype == 1:  # IDB
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
        elif btype == 6:  # EPB
            iface, th, tl, caplen, origlen = struct.unpack_from(endian + "IIIII", body, 0)
            data = body[20: 20 + caplen]
            if caplen != origlen:
                raise ValueError(f"{path}: truncated packet")
            flags, opos = 0, 20 + ((caplen + 3) & ~3)
            while opos + 4 <= len(body):
                code, olen = struct.unpack_from(endian + "HH", body, opos)
                if code == 0:
                    break
                if code == 2:
                    flags = struct.unpack_from(endian + "I", body, opos + 4)[0]
                opos += 4 + ((olen + 3) & ~3)
            linktype, mult = ifaces[iface]
            out.append({"t_ps": ((th << 32) | tl) * mult, "dir": flags & 3, "linktype": linktype, "data": data})
        pos += blen
    return out


def fnv1a64(data):
    h = 1469598103934665603
    for c in data:
        h = ((h ^ c) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def ethernet(data):
    """Parses an Ethernet frame captured with its FCS. Returns a dict or raises ValueError."""
    if len(data) < 64:
        raise ValueError("frame shorter than 64 B")
    fcs_ok = struct.unpack("<I", data[-4:])[0] == (zlib.crc32(data[:-4]) & 0xFFFFFFFF)
    dst, src = data[0:6].hex(), data[6:12].hex()
    etype, off, pcp, vid = struct.unpack(">H", data[12:14])[0], 14, -1, -1
    if etype == 0x8100:
        tci, etype = struct.unpack(">HH", data[14:18])
        pcp, vid, off = tci >> 13, tci & 0xFFF, 18
    payload = data[off:-4]
    return {"dst": dst, "src": src, "etherType": etype, "pcp": pcp, "vid": vid, "payload": payload,
            "fcs_ok": fcs_ok, "min_size": len(data) == 64}


def simtime_ps(s):
    """Exact conversion of an OMNeT++ simtime string (seconds, decimal) to integer ps."""
    s = s.strip()
    neg = s.startswith("-")
    if neg:
        s = s[1:]
    whole, _, frac = s.partition(".")
    if len(frac) > 12:
        raise ValueError(f"simtime {s} finer than 1 ps")
    v = int(whole or "0") * 10 ** 12 + int((frac + "0" * 12)[:12])
    return -v if neg else v
