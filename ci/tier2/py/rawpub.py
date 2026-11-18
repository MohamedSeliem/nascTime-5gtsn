"""Raw-evidence publication (E-8, D-E3-3): copies the sealed raw simulation outputs and the tier-2 text records into a
publication directory and checks every file by type and content. A file is published only if it is one of the expected
raw outputs or an allow-listed record, and
  - every file: not an executable/shared object/archive (ELF, ar, gzip, zip magic), regular file, within the size cap;
  - text files (.sca .vec .vci .csv .log .txt .tsv .json .sha256, loader log): strict UTF-8, no NUL byte, and the
    tier-1 sensitive-content screen (ci/tier1/lib/screen.py) passes;
  - PCAP files: valid pcapng (section header magic, parsed completely by the repository's reader), every frame
    parsable, and the sensitive-content screen passes on all printable strings (>= 6 characters) extracted from the file;
      Ethernet captures (link type 1, every file except the N3 capture): every source MAC a locally administered unicast
        address (simulation-assigned), every destination such an address, the gPTP multicast 01-80-C2-00-00-0E or broadcast;
      the N3 capture of e3b (UPF ppp[0]) only (E3b-R1 policy, derived from the pinned Simu5G 1.8.1 / INET 4.7.0 sources;
        see ci/tier2/README.md): link type 204 (PPP with direction); PPP header 7e ff 03, protocol 0x0021 (IPv4) only, a
        2-byte FCS trailer; IPv4 0x45 (no options), consistent total length, UDP only; source an N3 PPP address
        (10.x.x.x/24), destination an N3 PPP address or the gNB's tunnel endpoint (192.168.x.x/24, downlink leaving the UPF
        only); at most two N3 addresses in one /24 and one gNB endpoint per file; fragments must reassemble completely; both
        UDP ports GTP-U ports (31, 2152), consistent UDP length; GTP-U G-PDU in one of the two Simu5G serialiser forms (flags
        0x30, or 0x34 with a single PDU-session container), consistent length; inner Ethernet frame >= 14 bytes under the
        MAC policy above. Every frame is examined: violations are counted per class with bounded examples (never stopping
        at the first), and any violation, an empty capture or an unsupported class fails the publication.
Passing a text regex alone never qualifies a binary file. Any failure removes the publication directory (fail closed).
The outputs are never rewritten.
usage: rawpub.py <experiment e3a|e3b> <raw> <records> <e3 dir> <out dir> <screen.py> <pcapng module dir> <limit_B> <report>"""
import os
import re
import shutil
import struct
import subprocess
import sys
import tempfile
from collections import defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
E3A_FILES = {"effective-config.txt", "run-M2S4U.log",
             "runs/M2S4U/M2S4U/0.sca", "runs/M2S4U/M2S4U/0.vec", "runs/M2S4U/M2S4U/0.vci",
             "runs/M2S4U/m2log/M2S4U-0/M2S4LinkTest.ttA.eth[1].trafficConditionerLayer.engine.pdelay.csv",
             "runs/M2S4U/m2log/M2S4U-0/M2S4LinkTest.ttB.eth[1].trafficConditionerLayer.engine.pdelay.csv",
             "runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttA.pcapRecorder[0].pcapng",
             "runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttB.pcapRecorder[0].pcapng"}
E3B_N3 = "runs/M2S5/pcap/M2S5-0/M1Bridge.upf.pcapRecorder[0].pcapng"
# N3 capture policy (E3b-R1). Every rule below is derived from the pinned sources (Simu5G 1.8.1, INET 4.7.0) and the
# reviewed configuration; see ci/tier2/README.md, "E3b-R1: N3 capture policy".
N3_LINKTYPE = 204                      # INET PcapRecorder: Protocol::ppp -> LINKTYPE_PPP_WITH_DIR (direction in the EPB flags)
PPP_HEADER = b"\x7e\xff\x03\x00\x21"  # INET PppHeader: flag 0x7e, address 0xff, control 0x03; protocol 0x0021 (IPv4) only
PPP_TRAILER_LEN = 2                    # INET PppTrailer: FCS-16 only (2 bytes; the closing flag is not serialised)
GTPU_PORTS = {31, 2152}                # Simu5G GtpUser localPort = tunnelPeerPort = 31 (default, not overridden); the reviewed
                                       # decoder also recognises 2152; both UDP ports must be in this set
GTPU_FLAGS = {0x30: "no-extension", 0x34: "pdu-session-container"}   # Simu5G GtpUserMsgSerializer: the only two forms
GTPU_G_PDU, GTPU_END_MARKER = 0xFF, 0xFE
N3_EXAMPLES = 5                        # bounded diagnostics: examples kept per violation class


def ip_str(a):
    return ".".join(str(x) for x in a)


def addr_class(a):
    """'n3' for the configurator's among-rule range of the gNB/UPF PPP link (10.x.x.x/24), 'node' for its hosts-rule range
    (192.168.x.x/24; the gNB's first IPv4 interface is its cellular NIC, whose address is the gNB's tunnel endpoint)"""
    if a[0] == 10:
        return "n3"
    if a[0] == 192 and a[1] == 168:
        return "node"
    return None


def raw_files(exp):
    """the exact publishable raw file set of the experiment and the path of its N3 (PPP) capture, if any"""
    if exp == "e3a":
        return set(E3A_FILES), None
    if exp == "e3b":
        names = [l.split("  ", 1)[1].strip() for l in open(os.path.join(HERE, "..", "ref-e3b-r181c-run0.sha256")) if "  " in l]
        return {"effective-config.txt", "run-M2S5.log", "runs/M2S5/M2S5/0.vci"} | {"runs/" + n for n in names}, E3B_N3
    raise SystemExit(f"rawpub: unknown experiment {exp!r}")
RECORD_RX = re.compile(r"^([\w.-]+\.(txt|tsv|json)|lddebug\.\d+)$")
TEXT_EXT = (".sca", ".vec", ".vci", ".csv", ".log", ".txt", ".tsv", ".json", ".sha256")
BAD_MAGIC = {b"\x7fELF": "ELF executable/shared object", b"!<arch>": "ar archive", b"\x1f\x8b": "gzip", b"PK\x03\x04": "zip"}
GPTP, BCAST = "0180c200000e", "ffffffffffff"


def local_unicast(mac):
    o = int(mac[:2], 16)
    return bool(o & 0x02) and not o & 0x01


def mac_policy(src, dst):
    if not local_unicast(src):
        return f"source MAC {src} is not a simulation-assigned (locally administered unicast) address"
    if not (local_unicast(dst) or dst in (GPTP, BCAST)):
        return f"destination MAC {dst} unexpected"
    return None


class N3Check:
    """Validates every frame of the N3 capture and collects bounded diagnostics per violation class (it never stops at the
    first problem). Accepted traffic class (the only one established from the sources): IPv4 / UDP / GTP-U G-PDU carrying
    an Ethernet frame of the Ethernet PDU session, in one of the two serialiser forms, between the UPF's N3 address and the
    gNB's tunnel endpoint (downlink, outbound at the UPF) or the gNB's N3 address and the UPF's (uplink)."""

    def __init__(self):
        self.cls, self.examples = defaultdict(int), defaultdict(list)
        self.pairs, self.forms, self.frags = defaultdict(int), defaultdict(int), defaultdict(dict)
        self.packets = self.accepted = 0
        self.addresses = set()

    def bad(self, cls, where, what):
        self.cls[cls] += 1
        if len(self.examples[cls]) < N3_EXAMPLES:
            self.examples[cls].append(f"{where}: {what}")

    def frame(self, i, p):
        self.packets += 1
        b, d = p["data"], p["dir"]
        if p["linktype"] != N3_LINKTYPE:
            return self.bad("link-type", f"packet {i}", f"link type {p['linktype']} (expected {N3_LINKTYPE}, PPP with direction)")
        if len(b) < len(PPP_HEADER) + 20 + PPP_TRAILER_LEN:
            return self.bad("truncated", f"packet {i}", f"{len(b)} bytes")
        if b[:3] != PPP_HEADER[:3]:
            return self.bad("ppp-framing", f"packet {i}", f"header {b[:3].hex()} (expected 7eff03)")
        if b[3:5] != PPP_HEADER[3:5]:
            return self.bad("ppp-protocol", f"packet {i}", f"protocol 0x{b[3:5].hex()} (only 0x0021 IPv4)")
        ip = b[len(PPP_HEADER):]
        if ip[0] >> 4 != 4 or ip[0] & 15 != 5:
            return self.bad("ipv4-header", f"packet {i}", f"version/IHL byte 0x{ip[0]:02x} (expected 0x45, no options)")
        tot = struct.unpack(">H", ip[2:4])[0]
        if tot < 20 or tot > len(ip):
            return self.bad("ipv4-length", f"packet {i}", f"total length {tot}, {len(ip)} bytes available")
        if len(ip) - tot != PPP_TRAILER_LEN:
            return self.bad("ppp-trailer", f"packet {i}", f"{len(ip) - tot} bytes after the datagram (expected the 2-byte FCS)")
        src, dst = tuple(ip[12:16]), tuple(ip[16:20])
        ok = True
        if ip[9] != 17:
            self.bad("ipv4-protocol", f"packet {i}", f"IP protocol {ip[9]} (only UDP 17)")
            ok = False
        if addr_class(src) != "n3":
            self.bad("address-source", f"packet {i}", f"source {ip_str(src)} is not an N3 PPP address (10.x.x.x/24)")
            ok = False
        dc = addr_class(dst)
        if dc is None:
            self.bad("address-destination", f"packet {i}", f"destination {ip_str(dst)} outside 10.x.x.x/24 and 192.168.x.x/24")
            ok = False
        elif dc == "node" and d != 2:
            self.bad("address-direction", f"packet {i}", f"{ip_str(src)} -> {ip_str(dst)} recorded with direction {d} "
                     "(a gNB tunnel endpoint is reached only by downlink leaving the UPF, direction 2)")
            ok = False
        if src == dst:
            self.bad("address-self", f"packet {i}", f"source equals destination {ip_str(src)}")
            ok = False
        if not ok:
            return None
        self.addresses |= {src, dst}
        self.pairs[(ip_str(src), ip_str(dst), d)] += 1
        ff = struct.unpack(">H", ip[6:8])[0]
        mf, fo = ff & 0x2000, (ff & 0x1FFF) * 8
        pl = ip[20:tot]
        if mf or fo:
            k = (src, dst, ip[4:6], d)
            if fo in self.frags[k]:
                return self.bad("ipv4-fragment", f"packet {i}", "duplicate fragment")
            self.frags[k][fo] = (i, pl)
            if not mf:
                self.frags[k]["end"] = fo + len(pl)
            return None
        return self.datagram(f"packet {i}", pl)

    def datagram(self, where, pl):
        if len(pl) < 8:
            return self.bad("udp-length", where, f"{len(pl)}-byte UDP datagram")
        sport, dport, ulen = struct.unpack(">HHH", pl[:6])
        if ulen != len(pl):
            return self.bad("udp-length", where, f"UDP length {ulen}, datagram {len(pl)}")
        if sport not in GTPU_PORTS or dport not in GTPU_PORTS:
            return self.bad("udp-ports", where, f"ports {sport} -> {dport} (both must be GTP-U ports {sorted(GTPU_PORTS)})")
        g = pl[8:]
        if len(g) < 8:
            return self.bad("gtpu-header", where, f"{len(g)}-byte GTP-U message")
        if g[0] not in GTPU_FLAGS:
            return self.bad("gtpu-header", where, f"flags 0x{g[0]:02x} (only 0x30 or 0x34)")
        if g[1] != GTPU_G_PDU:
            return self.bad("gtpu-message-type", where, "End Marker (254; not expected without handover)" if g[1] == GTPU_END_MARKER
                            else f"message type {g[1]}")
        if struct.unpack(">H", g[2:4])[0] != len(g) - 8:
            return self.bad("gtpu-length", where, f"length field {struct.unpack('>H', g[2:4])[0]}, {len(g) - 8} bytes follow")
        h = 8
        if g[0] == 0x34:
            # sequence 0, N-PDU 0, next 0x85; container: length 1, PDU type << 4 (0 DL, 1 UL), QFI, next none
            if len(g) < 16 or g[8:12] != b"\x00\x00\x00\x85" or g[12] != 1 or g[13] not in (0x00, 0x10) or g[14] & 0xC0 or g[15] != 0:
                return self.bad("gtpu-extension", where, f"optional fields/extension {g[8:16].hex()} (expected 00000085 01 00|10 qfi 00)")
            h = 16
        inner = g[h:]
        if len(inner) < 14:
            return self.bad("inner-frame", where, f"{len(inner)}-byte inner Ethernet frame")
        err = mac_policy(inner[6:12].hex(), inner[0:6].hex())   # Ethernet: destination, then source
        if err:
            return self.bad("inner-mac", where, err)
        self.accepted += 1
        self.forms[GTPU_FLAGS[g[0]]] += 1
        return None

    def finish(self):
        for k, d in self.frags.items():
            if "end" not in d:
                self.bad("ipv4-fragment", f"fragments of packet {min(v[0] for x, v in d.items() if x != 'end')}", "no last fragment")
                continue
            buf, pos, used = b"", 0, set()
            while pos < d["end"] and pos in d:
                used.add(pos)
                buf += d[pos][1]
                pos += len(d[pos][1])
            if pos != d["end"] or used != {x for x in d if x != "end"}:
                self.bad("ipv4-fragment", f"fragments of packet {d[min(x for x in d if x != 'end')][0]}", "do not reassemble completely")
            else:
                self.datagram(f"reassembled datagram of packet {d[0][0]}", buf)
        n3 = sorted(a for a in self.addresses if addr_class(a) == "n3")
        node = sorted(a for a in self.addresses if addr_class(a) == "node")
        if len(n3) > 2 or len({a[:3] for a in n3}) > 1:
            self.bad("address-set", "file", f"N3 addresses {[ip_str(a) for a in n3]} (at most the two ends of one 10.x.x.x/24 PPP link)")
        if len(node) > 1:
            self.bad("address-set", "file", f"gNB tunnel endpoints {[ip_str(a) for a in node]} (one gNB: at most one)")
        if self.packets == 0:
            self.bad("empty", "file", "no packets")

    def summary(self):
        out = [f"n3_packets: {self.packets}", f"n3_gpdu_accepted: {self.accepted}"]
        out += [f"n3_address_pair: {s} -> {d} direction {r}: {n}" for (s, d, r), n in sorted(self.pairs.items())]
        out += [f"n3_gtpu_form: {k}: {n}" for k, n in sorted(self.forms.items())]
        out += [f"n3_violation: {c}: {n}" for c, n in sorted(self.cls.items())]
        out += [f"n3_violation_example: {c}: {e}" for c in sorted(self.examples) for e in self.examples[c]]
        return out

    def problems(self):
        return [f"N3 {c}: {n} occurrence(s), e.g. {self.examples[c][0]}" for c, n in sorted(self.cls.items())]


def check_pcap(path, pcapng, n3=False):
    """returns (problems, summary lines); never stops at the first frame problem"""
    with open(path, "rb") as f:
        head = f.read(12)
    if len(head) < 12 or head[:4] != b"\x0a\x0d\x0d\x0a":
        return ["not a pcapng file"], []
    try:
        pk = pcapng.read(path)
    except Exception as e:  # noqa: BLE001
        return [f"pcapng parse failed: {type(e).__name__}"], []
    if n3:
        c = N3Check()
        for i, p in enumerate(pk):
            try:
                c.frame(i, p)
            except (IndexError, struct.error) as e:
                c.bad("malformed", f"packet {i}", type(e).__name__)
        c.finish()
        return c.problems(), c.summary()
    if not pk:
        return ["no packets"], []
    cls, ex = defaultdict(int), defaultdict(list)
    for i, p in enumerate(pk):
        if p["linktype"] != 1:
            k, msg = "link-type", f"packet {i}: link type {p['linktype']}"
        else:
            try:
                f = pcapng.ethernet(p["data"])
                err = mac_policy(f["src"], f["dst"])
                k, msg = ("mac", f"packet {i}: {err}") if err else (None, None)
            except ValueError as e:
                k, msg = "malformed", f"packet {i}: {e}"
        if k:
            cls[k] += 1
            if len(ex[k]) < N3_EXAMPLES:
                ex[k].append(msg)
    return [f"{k}: {n} packet(s), e.g. {ex[k][0]}" for k, n in sorted(cls.items())], []


def main(argv):
    if len(argv) != 10:
        raise SystemExit(__doc__)
    exp, raw, rec, e3, out, screen, pdir, limit, report = argv[1:10]
    RAW_FILES, N3 = raw_files(exp)
    limit = int(limit)
    sys.dont_write_bytecode = True   # never write into the reviewed checker directory
    sys.path.insert(0, pdir)
    import pcapng  # noqa: E402  (the repository's reviewed reader)
    lines, problems, diag = [], [], []
    if os.path.exists(out):
        shutil.rmtree(out)
    os.makedirs(out)
    present = sorted(os.path.relpath(os.path.join(d, f), raw) for d, _, fs in os.walk(raw) for f in fs) if os.path.isdir(raw) else []
    extra = sorted(set(present) - RAW_FILES)
    if extra:
        problems.append(f"unexpected raw files not published: {extra[:5]}")
    for rel in present:
        if rel in RAW_FILES:
            dst = os.path.join(out, "raw", rel)
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            shutil.copyfile(os.path.join(raw, rel), dst)
    for n in ("raw-manifest.sha256",):
        if os.path.isfile(os.path.join(e3, n)):
            shutil.copyfile(os.path.join(e3, n), os.path.join(out, n))
    os.makedirs(os.path.join(out, "records"))
    for n in sorted(os.listdir(rec)) if os.path.isdir(rec) else []:
        if RECORD_RX.match(n) and os.path.isfile(os.path.join(rec, n)):
            shutil.copyfile(os.path.join(rec, n), os.path.join(out, "records", n))
    files = sorted(os.path.relpath(os.path.join(d, f), out) for d, _, fs in os.walk(out) for f in fs)
    total, texts, strings_dir = 0, [], tempfile.mkdtemp(prefix="rawpub-strings-")
    for rel in files:
        p = os.path.join(out, rel)
        if os.path.islink(p) or not os.path.isfile(p):
            problems.append(f"{rel}: not a regular file")
            continue
        size = os.path.getsize(p)
        total += size
        with open(p, "rb") as f:
            head = f.read(8)
        kind = next((k for m, k in BAD_MAGIC.items() if head.startswith(m)), None)
        if kind:
            problems.append(f"{rel}: {kind} refused")
            continue
        base = os.path.basename(rel)
        if rel.endswith(".pcapng"):
            is_n3 = N3 is not None and rel == "raw/" + N3
            errs, summ = check_pcap(p, pcapng, n3=is_n3)
            diag += summ
            problems += [f"{rel}: {e}" for e in errs]   # all classes are reported; the strings are still screened
            data = open(p, "rb").read()
            sp = os.path.join(strings_dir, base.replace("[", "_").replace("]", "_") + ".strings.txt")
            open(sp, "w").write("\n".join(m.decode("ascii") for m in re.findall(rb"[\x20-\x7e]{6,}", data)) + "\n")
            texts.append(sp)
            lines.append(f"{rel}\t{size}\tpcapng\tchecked (" + ("N3 PPP/IPv4/UDP/GTP-U G-PDU policy, N3/gNB endpoint "
                         "addresses, inner Ethernet MAC policy" if is_n3 else "format, Ethernet frames, MAC policy") + ", extracted strings)")
        elif rel.endswith(TEXT_EXT) or base.startswith("lddebug."):
            data = open(p, "rb").read()
            if b"\0" in data:
                problems.append(f"{rel}: NUL byte in a text file")
                continue
            try:
                data.decode("utf-8", errors="strict")
            except UnicodeDecodeError:
                problems.append(f"{rel}: not UTF-8 text")
                continue
            texts.append(p)
            lines.append(f"{rel}\t{size}\ttext\tchecked (UTF-8, screen)")
        else:
            problems.append(f"{rel}: unclassified file type refused")
    if texts:
        r = subprocess.run([sys.executable, "-I", screen, *texts], capture_output=True, text=True)
        if r.returncode != 0:
            problems.append("sensitive-content screen matched: " + "; ".join(r.stdout.split("\n")[:6]))
    shutil.rmtree(strings_dir, ignore_errors=True)
    if total > limit:
        problems.append(f"publication {total} B exceeds {limit} B")
    ok = not problems and bool(present)
    rep = ["path\tbytes\ttype\tcheck"] + lines + [f"total_bytes: {total}", f"files: {len(files)}"]
    rep += diag
    rep += [f"problem: {p}" for p in problems]
    what = ("M2S4LinkTest (two simulated hosts, two translators)" if exp == "e3a" else
            "M1Bridge (simulated talker, listener, two translators, UE, gNB and UPF; N3 PPP/GTP-U capture)")
    rep += [f"content: synthetic simulation outputs of {what}, simulation records and loader/runner logs only" if ok
            else "content: NOT confirmed", f"rawpub_result: {'PASS' if ok else 'FAIL'}"]
    open(report, "w").write("\n".join(rep) + "\n")
    print("\n".join(rep[len(lines) + 1:]))
    if not ok:
        shutil.rmtree(out, ignore_errors=True)
        return 1
    import hashlib
    with open(os.path.join(out, "publication-manifest.sha256"), "w") as m:
        for rel in sorted(files):
            m.write(f"{hashlib.sha256(open(os.path.join(out, rel), 'rb').read()).hexdigest()}  ./{rel}\n")
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
