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
      the N3 capture of e3b (UPF ppp[0]) only: PPP link type (9, 50 or 204); every frame decoded exactly as the reviewed
        check_m2s5.n3_inner does (one prefix byte, optional ff03 address/control, protocol 0x0021 IPv4 only); IPv4 version 4,
        header length >= 20, total length within the frame and at most 3 trailing bytes (PPP FCS-16 and flag), source and
        destination in 10.0.0.0/8 (the configurator's gNB/UPF range 10.x.x.x/24); fragments must reassemble completely;
        UDP (17) with consistent length and port 2152 or 31; GTP-U version 1, PT=1, message type 0xFF (G-PDU), GTP length
        consistent, extension-header chain within bounds; inner Ethernet frame >= 14 bytes under the MAC policy above.
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
PPP_LINKTYPES = {9, 50, 204}
GTPU_PORTS = {2152, 31}


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


def in_10(a):
    return len(a) == 4 and a[0] == 10


def check_gtpu_udp(pl):
    """UDP datagram carrying a GTP-U G-PDU with an inner Ethernet frame under the MAC policy; None or the problem"""
    if len(pl) < 8:
        return "UDP header truncated"
    sport, dport, ulen = struct.unpack(">HHH", pl[:6])
    if ulen != len(pl):
        return f"UDP length {ulen} != datagram payload {len(pl)}"
    if not ({sport, dport} & GTPU_PORTS):
        return f"UDP ports {sport}/{dport} are not GTP-U ports"
    g = pl[8:]
    if len(g) < 8:
        return "GTP-U header truncated"
    if g[0] >> 5 != 1 or not g[0] & 0x10:
        return f"GTP-U flags 0x{g[0]:02x} (version 1, PT=1 required)"
    if g[1] != 0xFF:
        return f"GTP-U message type 0x{g[1]:02x} is not a G-PDU"
    glen = struct.unpack(">H", g[2:4])[0]
    if glen != len(g) - 8:
        return f"GTP-U length {glen} != {len(g) - 8}"
    h = 8
    if g[0] & 7:
        if len(g) < 12:
            return "GTP-U optional fields truncated"
        h, nxt = 12, g[11]
        while nxt:
            if h >= len(g) or g[h] == 0:
                return "GTP-U extension header chain malformed"
            ln = g[h] * 4
            if h + ln > len(g):
                return "GTP-U extension header truncated"
            nxt = g[h + ln - 1]
            h += ln
    inner = g[h:]
    if len(inner) < 14:
        return f"inner Ethernet frame of {len(inner)} bytes"
    return mac_policy(inner[6:12].hex(), inner[0:6].hex())   # Ethernet: destination, then source


def check_ppp_frame(b, frags, key_dir):
    """one N3 PPP frame decoded as check_m2s5.n3_inner does; returns (problem or None, [complete UDP payloads])"""
    if len(b) < 5:
        return "PPP frame truncated", []
    if b[0] not in (0x00, 0x01, 0x7E):
        return f"unexpected PPP prefix byte 0x{b[0]:02x}", []
    off = 5 if b[1:3] == b"\xff\x03" else 3
    if len(b) < off + 20:
        return "IPv4 header truncated", []
    if struct.unpack(">H", b[off - 2:off])[0] != 0x0021:
        return f"PPP protocol 0x{struct.unpack('>H', b[off - 2:off])[0]:04x} is not IPv4", []
    ip = b[off:]
    if ip[0] >> 4 != 4 or (ip[0] & 15) < 5:
        return f"not a valid IPv4 header (0x{ip[0]:02x})", []
    ihl, tot = (ip[0] & 15) * 4, struct.unpack(">H", ip[2:4])[0]
    if tot < ihl or tot > len(ip):
        return f"IPv4 total length {tot} inconsistent with frame ({len(ip)} bytes, header {ihl})", []
    if len(ip) - tot > 3:
        return f"{len(ip) - tot} trailing bytes after the IPv4 datagram", []
    if not (in_10(ip[12:16]) and in_10(ip[16:20])):
        return f"IPv4 addresses {'.'.join(map(str, ip[12:16]))} -> {'.'.join(map(str, ip[16:20]))} outside 10.0.0.0/8", []
    if ip[9] != 17:
        return f"IPv4 protocol {ip[9]} is not UDP", []
    ff = struct.unpack(">H", ip[6:8])[0]
    mf, fo = ff & 0x2000, (ff & 0x1FFF) * 8
    pl = ip[ihl:tot]
    if mf or fo:
        k = (ip[12:16], ip[16:20], ip[4:6], ip[9], key_dir)
        if fo in frags[k]:
            return "duplicate IPv4 fragment", []
        frags[k][fo] = pl
        if not mf:
            frags[k]["end"] = fo + len(pl)
        return None, []
    return None, [pl]


def check_n3(pk):
    frags, dgrams = defaultdict(dict), []
    for i, p in enumerate(pk):
        if p["linktype"] not in PPP_LINKTYPES:
            return f"packet {i}: link type {p['linktype']} is not PPP"
        err, d = check_ppp_frame(p["data"], frags, p["dir"])
        if err:
            return f"packet {i}: {err}"
        dgrams += d
    for k, d in frags.items():
        if "end" not in d:
            return "incomplete IPv4 fragment set (no last fragment)"
        buf, pos, used = b"", 0, set()
        while pos < d["end"] and pos in d:
            used.add(pos)
            buf += d[pos]
            pos += len(d[pos])
        if pos != d["end"] or used != {x for x in d if x != "end"}:
            return "IPv4 fragments do not reassemble completely"
        dgrams.append(buf)
    for j, pl in enumerate(dgrams):
        err = check_gtpu_udp(pl)
        if err:
            return f"datagram {j}: {err}"
    return None


def check_pcap(path, pcapng, n3=False):
    with open(path, "rb") as f:
        head = f.read(12)
    if len(head) < 12 or head[:4] != b"\x0a\x0d\x0d\x0a":
        return "not a pcapng file"
    try:
        pk = pcapng.read(path)
    except Exception as e:  # noqa: BLE001
        return f"pcapng parse failed: {type(e).__name__}"
    if not pk:
        return "no packets"
    if n3:
        try:
            return check_n3(pk)
        except (IndexError, struct.error) as e:
            return f"N3 frame not parsable: {type(e).__name__}"
    for i, p in enumerate(pk):
        if p["linktype"] != 1:
            return f"packet {i}: link type {p['linktype']}"
        try:
            f = pcapng.ethernet(p["data"])
        except ValueError as e:
            return f"packet {i}: {e}"
        err = mac_policy(f["src"], f["dst"])
        if err:
            return f"packet {i}: {err}"
    return None


def main(argv):
    if len(argv) != 10:
        raise SystemExit(__doc__)
    exp, raw, rec, e3, out, screen, pdir, limit, report = argv[1:10]
    RAW_FILES, N3 = raw_files(exp)
    limit = int(limit)
    sys.dont_write_bytecode = True   # never write into the reviewed checker directory
    sys.path.insert(0, pdir)
    import pcapng  # noqa: E402  (the repository's reviewed reader)
    lines, problems = [], []
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
            err = check_pcap(p, pcapng, n3=is_n3)
            if err:
                problems.append(f"{rel}: {err}")
                continue
            data = open(p, "rb").read()
            sp = os.path.join(strings_dir, base.replace("[", "_").replace("]", "_") + ".strings.txt")
            open(sp, "w").write("\n".join(m.decode("ascii") for m in re.findall(rb"[\x20-\x7e]{6,}", data)) + "\n")
            texts.append(sp)
            lines.append(f"{rel}\t{size}\tpcapng\tchecked (" + ("N3 PPP/IPv4/UDP/GTP-U framing, 10.0.0.0/8 addresses, inner "
                         "Ethernet MAC policy" if is_n3 else "format, Ethernet frames, MAC policy") + ", extracted strings)")
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
    rep += [f"problem: {p}" for p in problems]
    what = ("M2S4LinkTest (two simulated hosts, two translators)" if exp == "e3a" else
            "M1Bridge (simulated talker, listener, two translators, UE, gNB and UPF; N3 PPP/GTP-U capture)")
    rep += [f"content: synthetic simulation outputs of {what}, simulation records and loader/runner logs only" if ok
            else "content: NOT confirmed", f"rawpub_result: {'PASS' if ok else 'FAIL'}"]
    open(report, "w").write("\n".join(rep) + "\n")
    print("\n".join(rep[-6:]))
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
