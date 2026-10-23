#!/usr/bin/env python3
"""Canaries for the exact comparator m2s72_compare (used by F0-7, F0-9 and T0; design rev. 2, 7.1 method).

    test_m2s72_compare.py <results/M2-S7.2a> <census config>

Copies the census run to a temporary directory, applies one mutation at a time and compares the copy with the
original: every mutation of a recorded value must be flagged; the excluded items must not be.
  flagged:     PCAP timestamp +1 ps; one PCAP data bit; one log cell (+1 in the last digit) of a non-excluded
               column; one log row deleted; one vector value (last digit); one vector time (+1 ps); one scalar
               value; treeId changed together with a timestamp in the same row (exclusion does not mask)
  not flagged: treeId changed in every row (with exclude_columns = treeId, as F0-9); vector ids renumbered;
               run metadata (attr / config / par lines) changed
  T0 mode (substitution active, record-level comparison): PCAP timestamp, PCAP bit, log cell flagged; the
               unmodified copy not flagged
"""
import os
import re
import shutil
import struct
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s72_runs as R  # noqa: E402
import m2s72_compare as CMP  # noqa: E402


def epbs(buf):
    pos, out = 0, []
    while pos < len(buf):
        bt, bl = struct.unpack_from("<II", buf, pos)
        if bt == 6:
            out.append(pos)
        pos += bl
    return out


def mut_pcap_ts(p):
    b = bytearray(open(p, "rb").read())
    e = epbs(b)[len(epbs(b)) // 2]
    th, tl = struct.unpack_from("<II", b, e + 12)
    t = ((th << 32) | tl) + 1
    struct.pack_into("<II", b, e + 12, t >> 32, t & 0xFFFFFFFF)
    open(p, "wb").write(b)


def mut_pcap_bit(p):
    b = bytearray(open(p, "rb").read())
    e = epbs(b)[len(epbs(b)) // 2]
    b[e + 28 + 20] ^= 0x01
    open(p, "wb").write(b)


def last_digit_plus1(s):
    m = re.search(r"(\d)(\D*)$", s)
    d = (int(m.group(1)) + 1) % 10
    return s[:m.start(1)] + str(d) + m.group(2)


def mut_csv(p, col, also=None, every=False, delete=False):
    L = open(p).read().split("\n")
    h = L[0].split(",")
    j = h.index(col)
    full = [i for i in range(1, len(L)) if len(L[i].split(",")) == len(h) and L[i].split(",")[j]]
    rows = full if every else [full[len(full) // 2]]
    if delete:
        del L[len(L) // 2]
    else:
        for i in rows:
            c = L[i].split(",")
            if len(c) != len(h) or not c[j]:
                continue
            c[j] = str(int(c[j]) + 1) if c[j].lstrip("-").isdigit() else last_digit_plus1(c[j])
            if also:
                k = h.index(also)
                c[k] = last_digit_plus1(c[k]) if c[k] else "1"
            L[i] = ",".join(c)
    open(p, "w").write("\n".join(L))


def mut_vec(p, what):
    L = open(p).read().split("\n")
    if what == "ids":
        # renumber every vector id consistently (declaration and data lines)
        ids = {}
        for i, l in enumerate(L):
            if l.startswith("vector "):
                w = l.split(" ")
                ids[w[1]] = str(int(w[1]) + 100000)
                w[1] = ids[w[1]]
                L[i] = " ".join(w)
        for i, l in enumerate(L):
            if l[:1].isdigit():
                w = l.split("\t")
                if w[0] in ids:
                    w[0] = ids[w[0]]
                    L[i] = "\t".join(w)
    else:
        idx = [i for i, l in enumerate(L) if l[:1].isdigit()]
        i = idx[len(idx) // 2]
        w = L[i].split("\t")
        if what == "value":
            w[3] = last_digit_plus1(w[3])
        else:
            ps = R.pcapng.simtime_ps(w[2]) + 1
            w[2] = f"{ps // 10 ** 12}.{ps % 10 ** 12:012d}"
        L[i] = "\t".join(w)
    open(p, "w").write("\n".join(L))


def mut_sca(p, what):
    L = open(p).read().split("\n")
    if what == "meta":
        L = [("attr datetime 19700101-00:00:00" if l.startswith("attr datetime") else
              ("config sim-time-limit 99s" if l.startswith("config sim-time-limit") else
               (l + "x" if l.startswith("par ") and "macNodeId" not in l else l))) for l in L]
    else:
        idx = [i for i, l in enumerate(L) if l.startswith("scalar ") and re.fullmatch(r"-?\d+(\.\d+)?", l.split(" ")[3])]
        i = idx[len(idx) // 2]
        L[i] = last_digit_plus1(L[i])
    open(p, "w").write("\n".join(L))


def main():
    out, cfg = sys.argv[1], sys.argv[2]
    runs = os.path.join(out, "runs")
    base = R.Run72(runs, cfg)
    pc = os.path.join("pcap", f"{cfg}-0", f"{R.NET}.dsTt[0].pcapRecorder[1].pcapng")
    tk = os.path.join("pcap", f"{cfg}-0", f"{R.NET}.talker[0].pcapRecorder[0].pcapng")
    lg = os.path.join("m2log", f"{cfg}-0", f"{R.NET}.dsTt[0].eth[1].trafficConditionerLayer.syncOut.sync.csv")
    vec = os.path.join(cfg, "0.vec")
    sca = os.path.join(cfg, "0.sca")
    cases = [
        ("PCAP timestamp +1 ps (dsTt[0].eth[1])", lambda d: mut_pcap_ts(os.path.join(d, pc)), True, ()),
        ("PCAP one data bit (talker[0])", lambda d: mut_pcap_bit(os.path.join(d, tk)), True, ()),
        ("log cfOut +1 (DS-TT 0 egress log)", lambda d: mut_csv(os.path.join(d, lg), "cfOut"), True, ("treeId",)),
        ("log TSe +1 (DS-TT 0 egress log)", lambda d: mut_csv(os.path.join(d, lg), "TSe"), True, ("treeId",)),
        ("log row deleted", lambda d: mut_csv(os.path.join(d, lg), "t", delete=True), True, ("treeId",)),
        ("treeId and t of the same row changed", lambda d: mut_csv(os.path.join(d, lg), "treeId", also="t"), True, ("treeId",)),
        ("vector value, last digit", lambda d: mut_vec(os.path.join(d, vec), "value"), True, ()),
        ("vector time +1 ps", lambda d: mut_vec(os.path.join(d, vec), "time"), True, ()),
        ("scalar value, last digit", lambda d: mut_sca(os.path.join(d, sca), "value"), True, ()),
        ("treeId changed in every row (excluded column)", lambda d: mut_csv(os.path.join(d, lg), "treeId", every=True), False, ("treeId",)),
        ("treeId changed, without the exclusion", lambda d: mut_csv(os.path.join(d, lg), "treeId", every=True), True, ()),
        ("vector ids renumbered", lambda d: mut_vec(os.path.join(d, vec), "ids"), False, ()),
        ("run metadata (attr, config, par lines) changed", lambda d: mut_sca(os.path.join(d, sca), "meta"), False, ()),
        # T0 mode (record-by-record PCAP and cell-by-cell log comparison with a clockIdentity substitution)
        ("T0 mode: PCAP timestamp +1 ps", lambda d: mut_pcap_ts(os.path.join(d, pc)), True, "T0"),
        ("T0 mode: PCAP one data bit", lambda d: mut_pcap_bit(os.path.join(d, tk)), True, "T0"),
        ("T0 mode: log cfOut +1", lambda d: mut_csv(os.path.join(d, lg), "cfOut"), True, "T0"),
        ("T0 mode: unmodified copy", lambda d: None, False, "T0"),
    ]
    bad = 0
    for name, mut, expect, excl in cases:
        tmp = tempfile.mkdtemp(prefix="m2s72cmp-")
        try:
            dst = os.path.join(tmp, cfg)
            shutil.copytree(base.base, dst)
            mut(dst)
            other = R.Run72(tmp, cfg)
            if excl == "T0":
                diffs = CMP.compare_runs(base, other, subst={b"\xaa" * 8: b"\xbb" * 8})
            else:
                diffs = CMP.compare_runs(base, other, exclude_columns=excl)
            ok = bool(diffs) == expect
            bad += not ok
            print(f"{'PASS' if ok else 'FAIL'} | {name} | {'flagged' if diffs else 'not flagged'} (expected "
                  f"{'flagged' if expect else 'not flagged'}){': ' + diffs[0] if diffs else ''}")
        finally:
            shutil.rmtree(tmp)
    print(f"comparator canaries: {len(cases) - bad} PASS, {bad} FAIL")
    return 1 if bad else 0


if __name__ == "__main__":
    sys.exit(main())
