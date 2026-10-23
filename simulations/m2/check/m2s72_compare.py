"""M2-S7.2a exact run comparator (F0-7 / F0-9 twins and gate T0; migration/m2-s7.2a-design.md rev. 2, 8.1).

compare_runs(a, b, ...) compares every recorded output of two runs and returns a list of differences
(empty = identical):
  - PCAP: every pcapng file; without a substitution, byte for byte (whole file); with one (T0), record by
    record: timestamp (integer ps), direction, link type, original length and every captured byte;
  - nascTime logs (m2log/*.csv): without a substitution byte for byte; with one, row by row, column by column
    (recorded strings);
  - vectors (.vec): per (module path, vector name) the ordered (time, value) sequence as recorded strings
    (vector ids and event numbers are not compared: process-wide numbering, design X-2);
  - scalars (.sca): every scalar line and every statistic block (field, bin and attr lines) as recorded
    strings; run metadata (run, version, top-level attr, itervar, config, par lines) is not compared (X-3);
  - files are matched by their path relative to the run's pcap/m2log/result directories, with the config
    name removed and, for T0, the module path mapped (X-4); a file present in only one run is a difference.
No numeric tolerance; values are never parsed and re-rounded. exclude_columns (F0-9 only: {"treeId"}, design X-1)
names log columns not compared (by header name); every other cell is compared and the number of differing
excluded cells is reported.

T0 substitution (design 8.1: "allowed byte difference: only the slave's clockIdentity field, on an exact list of
fields"): the INET gPTP clockIdentity is std::hash of the Gptp module's full path, so it differs between
M1Bridge.talker.gptp and M2S72Bridge.talker[0].gptp (and the listener's, if non-zero). Allowed, and nothing
else: in gPTP frames on Ethernet links, the 8-byte clockIdentity of sourcePortIdentity (gPTP offset 20) and,
in Pdelay_Resp / Pdelay_Resp_Follow_Up, of requestingPortIdentity (offset 44), when it equals a reference
identity, replaced by the corresponding new identity, with the Ethernet FCS recomputed; in log cells, the same
identity in its logged text form, and the measurement layers' FNV-1a 64 hash of such a frame's Ethernet
payload (columns hash / txHash), recomputed from the substituted frame. A frame or cell that differs in any
other way is a difference.
"""
import os
import struct
import zlib

import m2s72_runs as R
import m2s6_runs as RR


def _files(run):
    out = {}
    for sub, d in (("pcap", run.pdir), ("m2log", run.ldir), ("res", os.path.join(run.base, run.cfg))):
        if not os.path.isdir(d):
            continue
        for f in sorted(os.listdir(d)):
            out[f"{sub}/{f}"] = os.path.join(d, f)
    return out


def read_sca(path, map_module=None):
    """Scalar and statistic content of a .sca file, metadata excluded: list of (kind, module, name, rest)."""
    out, in_stat = [], False
    with open(path) as fh:
        for line in fh:
            line = line.rstrip("\n")
            w = line.split(" ", 3)
            kind = w[0]
            if kind in ("scalar", "statistic"):
                in_stat = kind == "statistic"
                mod = map_module(w[1]) if map_module else w[1]
                out.append((kind, mod, w[2], w[3] if len(w) > 3 else ""))
            elif kind in ("field", "bin") or (kind == "attr" and in_stat):
                out.append((kind, "", "", line))
            elif kind in ("par", "config", "itervar", "run", "version", "attr", ""):
                in_stat = False if kind != "attr" else in_stat
                continue
            else:
                out.append(("unknown", "", "", line))
    return out


def _fnv(b):
    h = 1469598103934665603
    for c in b:
        h = ((h ^ c) * 1099511628211) & 0xFFFFFFFFFFFFFFFF
    return f"{h:016x}"


def _gptp_subst(data, subst):
    """Apply the T0 clockIdentity substitution to an Ethernet frame captured with FCS; returns new bytes."""
    if len(data) < 18 or data[0:6] != bytes.fromhex(R.GPTP_DST):
        return data
    off = 14
    et = struct.unpack(">H", data[12:14])[0]
    if et == 0x8100:
        off, et = 18, struct.unpack(">H", data[16:18])[0]
    if et != 0x88F7:
        return data
    b = bytearray(data)
    mtype = b[off] & 15
    changed = False
    fields = [off + 20] + ([off + 44] if mtype in (R.RESP, R.RFU) else [])
    for f in fields:
        cur = bytes(b[f:f + 8])
        if cur in subst:
            b[f:f + 8] = subst[cur]
            changed = True
    if changed:
        b[-4:] = struct.pack("<I", zlib.crc32(bytes(b[:-4])) & 0xFFFFFFFF)
    return bytes(b)


def _cmp_pcap(pa, pb, subst, stats):
    A, B = R.read_pcapng(pa), R.read_pcapng(pb)
    if len(A) != len(B):
        return f"{len(A)} vs {len(B)} records"
    for i, (x, y) in enumerate(zip(A, B)):
        if (x["t_ps"], x["dir"], x["linktype"], x["orig"]) != (y["t_ps"], y["dir"], y["linktype"], y["orig"]):
            return f"record {i}: t/dir/linktype/length {x['t_ps'], x['dir'], x['linktype'], x['orig']} vs {y['t_ps'], y['dir'], y['linktype'], y['orig']}"
        d = x["data"]
        if subst and x["linktype"] == 1:
            d2 = _gptp_subst(d, subst)
            if d2 != d:
                stats["frames_substituted"] = stats.get("frames_substituted", 0) + 1
            d = d2
        elif subst and any(k in d for k in subst):
            return f"record {i}: a reference clockIdentity inside a non-Ethernet record (substitution not supported)"
        if d != y["data"]:
            return f"record {i}: bytes differ"
    return None


def _cmp_csv(pa, pb, subst_txt, stats, exclude_columns=(), recon_keys=()):
    A = open(pa).read().split("\n")
    B = open(pb).read().split("\n")
    if len(A) != len(B):
        return f"{len(A)} vs {len(B)} lines"
    if A[0] != B[0]:
        return "header differs"
    excl = {j for j, c in enumerate(A[0].split(",")) if c in exclude_columns}
    for i, (x, y) in enumerate(zip(A, B)):
        if x == y:
            continue
        cx, cy = x.split(","), y.split(",")
        if len(cx) != len(cy):
            return f"line {i + 1}: column count"
        for j, (u, v) in enumerate(zip(cx, cy)):
            if u == v:
                continue
            if j in excl:
                stats["excluded_cells_differing"] = stats.get("excluded_cells_differing", 0) + 1
                continue
            if subst_txt and subst_txt.get(u) == v:
                stats["cells_substituted"] = stats.get("cells_substituted", 0) + 1
                if u in recon_keys:
                    stats["cells_reconstructed"] = stats.get("cells_reconstructed", 0) + 1
                continue
            return f"line {i + 1} column {j + 1}: {u!r} vs {v!r}"
    return None


def compare_runs(a, b, exclude_files=None, exclude_modules=None, map_name=None, map_module=None, subst=None,
                 exclude_columns=()):
    """a, b: objects with base, cfg, pdir, ldir (Run72 or the T0 reference run). map_name maps a file name of b to
    a's naming; map_module maps a module path of b to a's. subst: {ref 8-byte id: new 8-byte id} (a = reference)."""
    fa, fb = _files(a), _files(b)
    norm = lambda rel, run: rel.replace(run.cfg, "<cfg>")  # noqa: E731
    A = {norm(k, a): v for k, v in fa.items() if not (exclude_files and exclude_files(k))}
    B = {}
    for k, v in fb.items():
        if exclude_files and exclude_files(k):
            continue
        kk = norm(k, b)
        if map_name:
            kk = map_name(kk)
        B[kk] = v
    diffs, stats = [], {}
    hash_map, recon = {}, {}
    if subst:
        # the measurement-layer logs record the FNV-1a 64 hash of each frame's Ethernet payload; for a frame whose
        # bytes differ only by the substitution, the allowed log difference is exactly the recomputed hash
        real = {x: y for x, y in subst.items() if x != y}
        for k in sorted(set(A) & set(B)):
            if k.endswith(".pcapng") and real:
                for x in R.read_pcapng(A[k]):
                    if x["linktype"] != 1:
                        continue
                    d2 = _gptp_subst(x["data"], real)
                    if d2 != x["data"]:
                        off = 18 if x["data"][12:14] == b"\x81\x00" else 14
                        hash_map[_fnv(x["data"][off:-4])] = _fnv(d2[off:-4])
                        # a frame logged at enqueue but not yet transmitted at the end of the run is in no PCAP:
                        # candidates = the recorded frame with its sequenceId advanced by 1..4 (a log cell is
                        # accepted only if its reference hash equals one candidate's exactly, 64-bit FNV-1a)
                        for dlt in range(1, 5):
                            c = bytearray(x["data"])
                            sq = (int.from_bytes(c[off + 30: off + 32], "big") + dlt) & 0xFFFF
                            c[off + 30: off + 32] = sq.to_bytes(2, "big")
                            c2 = _gptp_subst(bytes(c), real)
                            recon[_fnv(bytes(c[off:-4]))] = _fnv(c2[off:-4])
    for k in sorted(set(A) | set(B)):
        if k.endswith(".vci") or k.endswith(".elog"):
            continue
        if k not in A or k not in B:
            diffs.append(f"{k}: only in {'reference' if k in A else 'compared'} run")
            continue
        pa, pb = A[k], B[k]
        if k.endswith(".pcapng"):
            if not subst:
                if open(pa, "rb").read() != open(pb, "rb").read():
                    diffs.append(f"{k}: bytes differ")
                continue
            r = _cmp_pcap(pa, pb, {x: y for x, y in subst.items() if x != y}, stats)
            if r:
                diffs.append(f"{k}: {r}")
        elif k.endswith(".csv"):
            if exclude_columns:
                r = _cmp_csv(pa, pb, {}, stats, exclude_columns)
                if r:
                    diffs.append(f"{k}: {r}")
                continue
            if not subst:
                if open(pa, "rb").read() != open(pb, "rb").read():
                    diffs.append(f"{k}: bytes differ")
                continue
            txt = dict(recon)
            txt.update(hash_map)
            for x, y in subst.items():
                if x != y:
                    for fmt in ("0x{:016x}", "{:016x}", "{:d}"):
                        txt[fmt.format(int.from_bytes(x, "big"))] = fmt.format(int.from_bytes(y, "big"))
            r = _cmp_csv(pa, pb, txt, stats, recon_keys=set(recon) - set(hash_map))
            if r:
                diffs.append(f"{k}: {r}")
        elif k.endswith(".vec"):
            va, vb = RR.read_vectors(pa), RR.read_vectors(pb)
            if map_module:
                vb = {(map_module(m), n): s for (m, n), s in vb.items()}
            if exclude_modules:
                va = {x: s for x, s in va.items() if not exclude_modules(x[0])}
                vb = {x: s for x, s in vb.items() if not exclude_modules(x[0])}
            if set(va) != set(vb):
                diffs.append(f"{k}: vector sets differ: {sorted(set(va) ^ set(vb))[:4]}")
            for x in sorted(set(va) & set(vb)):
                if va[x] != vb[x]:
                    diffs.append(f"{k}: vector {x} differs")
                    break
            stats["vectors"] = stats.get("vectors", 0) + len(va)
        elif k.endswith(".sca"):
            sa = read_sca(pa)
            sb = read_sca(pb, map_module)
            if exclude_modules:
                sa, sb = _drop_mods(sa, exclude_modules), _drop_mods(sb, exclude_modules)
            if sa != sb:
                j = next((i for i, (x, y) in enumerate(zip(sa, sb)) if x != y), min(len(sa), len(sb)))
                diffs.append(f"{k}: scalar content differs at item {j}: {sa[j] if j < len(sa) else None} vs {sb[j] if j < len(sb) else None}")
            stats["scalar_items"] = stats.get("scalar_items", 0) + len(sa)
        else:
            if open(pa, "rb").read() != open(pb, "rb").read():
                diffs.append(f"{k}: bytes differ")
    compare_runs.stats = stats
    compare_runs.nfiles = len(set(A) & set(B))
    return diffs


def _drop_mods(items, excl):
    out, skip = [], False
    for it in items:
        if it[0] in ("scalar", "statistic"):
            skip = excl(it[1])
        if not skip:
            out.append(it)
    return out
