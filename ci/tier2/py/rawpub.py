"""Raw-evidence publication (E-8, D-E3-3): copies the sealed raw simulation outputs and the tier-2 text records into a
publication directory and checks every file by type and content. A file is published only if it is one of the expected
raw outputs or an allow-listed record, and
  - every file: not an executable/shared object/archive (ELF, ar, gzip, zip magic), regular file, within the size cap;
  - text files (.sca .vec .vci .csv .log .txt .tsv .json .sha256, loader log): strict UTF-8, no NUL byte, and the
    tier-1 sensitive-content screen (ci/tier1/lib/screen.py) passes;
  - PCAP files: valid pcapng (section header magic, parsed completely by the repository's reader), Ethernet link type,
    every frame parsable, every source MAC a locally administered unicast address (simulation-assigned), every
    destination such an address, the gPTP multicast 01-80-C2-00-00-0E or broadcast, and the sensitive-content screen
    passes on all printable strings (>= 6 characters) extracted from the file.
Passing a text regex alone never qualifies a binary file. Any failure removes the publication directory (fail closed).
usage: rawpub.py <raw> <records> <e3 dir> <out dir> <screen.py> <pcapng module dir> <limit_B> <report>"""
import os
import re
import shutil
import subprocess
import sys
import tempfile

RAW_FILES = {"effective-config.txt", "run-M2S4U.log",
             "runs/M2S4U/M2S4U/0.sca", "runs/M2S4U/M2S4U/0.vec", "runs/M2S4U/M2S4U/0.vci",
             "runs/M2S4U/m2log/M2S4U-0/M2S4LinkTest.ttA.eth[1].trafficConditionerLayer.engine.pdelay.csv",
             "runs/M2S4U/m2log/M2S4U-0/M2S4LinkTest.ttB.eth[1].trafficConditionerLayer.engine.pdelay.csv",
             "runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttA.pcapRecorder[0].pcapng",
             "runs/M2S4U/pcap/M2S4U-0/M2S4LinkTest.ttB.pcapRecorder[0].pcapng"}
RECORD_RX = re.compile(r"^([\w.-]+\.(txt|tsv|json)|lddebug\.\d+)$")
TEXT_EXT = (".sca", ".vec", ".vci", ".csv", ".log", ".txt", ".tsv", ".json", ".sha256")
BAD_MAGIC = {b"\x7fELF": "ELF executable/shared object", b"!<arch>": "ar archive", b"\x1f\x8b": "gzip", b"PK\x03\x04": "zip"}
GPTP, BCAST = "0180c200000e", "ffffffffffff"


def local_unicast(mac):
    o = int(mac[:2], 16)
    return bool(o & 0x02) and not o & 0x01


def check_pcap(path, pcapng):
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
    for i, p in enumerate(pk):
        if p["linktype"] != 1:
            return f"packet {i}: link type {p['linktype']}"
        try:
            f = pcapng.ethernet(p["data"])
        except ValueError as e:
            return f"packet {i}: {e}"
        if not local_unicast(f["src"]):
            return f"packet {i}: source MAC {f['src']} is not a simulation-assigned (locally administered unicast) address"
        if not (local_unicast(f["dst"]) or f["dst"] in (GPTP, BCAST)):
            return f"packet {i}: destination MAC {f['dst']} unexpected"
    return None


def main(argv):
    if len(argv) != 9:
        raise SystemExit(__doc__)
    raw, rec, e3, out, screen, pdir, limit, report = argv[1:9]
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
            err = check_pcap(p, pcapng)
            if err:
                problems.append(f"{rel}: {err}")
                continue
            data = open(p, "rb").read()
            sp = os.path.join(strings_dir, base.replace("[", "_").replace("]", "_") + ".strings.txt")
            open(sp, "w").write("\n".join(m.decode("ascii") for m in re.findall(rb"[\x20-\x7e]{6,}", data)) + "\n")
            texts.append(sp)
            lines.append(f"{rel}\t{size}\tpcapng\tchecked (format, frames, MAC policy, extracted strings)")
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
    rep += ["content: synthetic simulation outputs of M2S4LinkTest (two simulated hosts, two translators), simulation "
            "records and loader/runner logs only" if ok else "content: NOT confirmed", f"rawpub_result: {'PASS' if ok else 'FAIL'}"]
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
