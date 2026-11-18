"""Synthetic M2S5-shaped evidence for the offline tests ONLY (never evidence of anything; no simulation):
  layout(out)       the exact 36-file run-0 layout of M2S5 (names from the R181c reference list plus 0.vci) with
                    structurally valid but EMPTY content (pcapng without packets, CSV headers only, empty result files);
                    the real reviewed oracle must evaluate such a run as FAIL (its non-vacuity conditions)
  n3_ppp_frame(...) a PPP-in-pcapng N3 frame as INET writes it (7e ff 03 0021, IPv4, UDP 31, GTP-U G-PDU with a
                    PDU-session container carrying the QFI, inner Ethernet frame, 2-byte FCS)
"""
import os
import struct

import synth

HERE = os.path.dirname(os.path.abspath(__file__))
REF = os.path.join(os.path.dirname(HERE), "ref-e3b-r181c-run0.sha256")


def names():
    n = [l.split("  ", 1)[1].strip() for l in open(REF) if l.strip()]
    return sorted(n + ["M2S5/M2S5/0.vci"])


CSV_HEADERS = {"syncIn.sync.csv": "event,seq,TSi,cf_in,Lup,cf1,rr\n", "syncOut.sync.csv": "event,seq,TSe,Res,cf2,rr\n",
               "engine.pdelay.csv": "event,msgType,seq,tA,tB,t,t1,t2,t3,t4,D,nrrNum,nrrDen\n"}


def layout(out):
    runs = os.path.join(out, "runs")
    for rel in names():
        p = os.path.join(runs, rel)
        os.makedirs(os.path.dirname(p), exist_ok=True)
        if rel.endswith(".pcapng"):
            open(p, "wb").write(synth.pcapng([]))
        elif rel.endswith(".csv"):
            open(p, "w").write(next((h for k, h in CSV_HEADERS.items() if rel.endswith(k)), "event,seq\n"))
        elif rel.endswith(".sca"):
            open(p, "w").write("version 3\nrun M2S5-0-x\nattr configname M2S5\nattr network M1Bridge\nattr repetition 0\n"
                               "attr seedset 0\n")
        else:
            open(p, "w").write("version 3\n")
    return runs


def ipv4(src, dst, payload, proto=17, ident=1, frag=0):
    hdr = struct.pack(">BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), ident, frag, 64, proto, 0, bytes(src), bytes(dst))
    return hdr + payload


def gtpu(inner, qfi=5, ext=True, pdu_type=0):
    """the two Simu5G GtpUserMsgSerializer forms: 0x34 with one PDU-session container (type 0 DL, 1 UL), or 0x30"""
    if ext:
        body = struct.pack(">HB", 0, 0) + bytes([0x85]) + bytes([1, pdu_type << 4, qfi & 0x3F, 0]) + inner
        return bytes([0x34, 0xFF]) + struct.pack(">H", len(body)) + struct.pack(">I", 1) + body
    return bytes([0x30, 0xFF]) + struct.pack(">H", len(inner)) + struct.pack(">I", 1) + inner


def udp(payload, sport=31, dport=31):
    return struct.pack(">HHHH", sport, dport, 8 + len(payload), 0) + payload


def inner_eth(dst="0aaa00000005", src="0aaa00000006", payload=b"\x10" * 46):
    return bytes.fromhex(dst) + bytes.fromhex(src) + struct.pack(">H", 0x88F7) + payload


def n3_ppp_frame(src=(10, 0, 0, 1), dst=(192, 168, 2, 1), inner=None, prefix=b"\x7e", trailer=b"\x00\x00", **kw):
    """INET PPP framing (7e ff 03 0021, 2-byte FCS); default: the observed hosted downlink pair UPF 10.0.0.1 -> gNB 192.168.2.1"""
    ip = ipv4(src, dst, udp(gtpu(inner if inner is not None else inner_eth(), **kw)))
    return prefix + b"\xff\x03\x00\x21" + ip + trailer


def pcapng_linktype(packets, linktype):
    data = synth.pcapng(packets)
    # rewrite the IDB link type (offset: SHB block length + 8)
    shb_len = struct.unpack_from("<I", data, 4)[0]
    return data[:shb_len + 8] + struct.pack("<H", linktype) + data[shb_len + 10:]
