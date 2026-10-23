#!/usr/bin/env python3
"""M2-S7.2a gate T0 (migration/m2-s7.2a-design.md rev. 2, 8.1): M2S72Bridge with numUe = 1 reproduces the
single-UE M1Bridge configurations, frame by frame.

    check_m2s72_t0.py <results/M2-S7.2a> <results dir of the committed records (simulations/m2/results)>

Pairs (m2s72.sh t0, seed 0): M2S72-T0-<s> (m2s72.ini) vs <source> (omnetpp.ini, run again on M1Bridge):
M2S71-q0-idle, M2S71-qdu-idle, M2S71-q0-load (12 s), M2S6-C-a, M2S6-E-all (their M2-S6 length).

Rows:
  T0-<s>   every output identical (m2s72_compare: every PCAP record's timestamp, direction, length and bytes;
           every log cell; every vector (time, value); every scalar and statistic), module paths mapped
           (M2S72Bridge.dsTt[0] = M1Bridge.dsTt, talker[0] = talker, other paths unchanged), with exactly one
           allowed byte difference: the INET gPTP clockIdentity (std::hash of the Gptp module path) in the
           sourcePortIdentity / requestingPortIdentity fields of gPTP frames, with the FCS recomputed, and its
           text form in logs. The identities are read from the runs (slave: its Pdelay_Req; GM: its Sync).
  T0-R-<s> the M1Bridge reference run reproduces the committed record (results/M2-S7.1 or M2-S6
           raw-outputs.sha256): every PCAP and log of repetition 0 has its committed hash
"""
import hashlib
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s72_runs as R  # noqa: E402
import m2s72_compare as CMP  # noqa: E402

T0 = [("q0-idle", "M2S71-q0-idle", "M2-S7.1", "runs/M2S71-q0-idle"),
      ("qdu-idle", "M2S71-qdu-idle", "M2-S7.1", "runs/M2S71-qdu-idle"),
      ("q0-load", "M2S71-q0-load", "M2-S7.1", "runs/M2S71-q0-load"),
      ("C-a", "M2S6-C-a", "M2-S6", "./M2S6-C-a"),
      ("E-all", "M2S6-E-all", "M2-S6", "./M2S6-E-all")]
rows = []


class RefRun:
    def __init__(self, runs, cfg, rep=0):
        self.cfg, self.rep = cfg, rep
        self.base = os.path.join(runs, cfg)
        self.pdir = os.path.join(self.base, "pcap", f"{cfg}-{rep}")
        self.ldir = os.path.join(self.base, "m2log", f"{cfg}-{rep}")


def map_path(s):
    s = s.replace("M2S72Bridge.", "M1Bridge.")
    s = s.replace("M1Bridge.dsTt[0].", "M1Bridge.dsTt.").replace("M1Bridge.talker[0].", "M1Bridge.talker.")
    return s


def gptp_id(path, mtype):
    ids = set()
    for p in R.read_pcapng(path):
        d = p["data"]
        if p["dir"] == 2 and d[0:6] == bytes.fromhex(R.GPTP_DST) and d[12:14] == b"\x88\xf7" and (d[14] & 15) == mtype:
            ids.add(bytes(d[14 + 20: 14 + 28]))
    if len(ids) != 1:
        raise ValueError(f"{path}: gPTP type {mtype} source clockIdentities {ids}")
    return ids.pop()


def main():
    out, recs = sys.argv[1], sys.argv[2]
    runs = os.path.join(out, "runs")
    for short, src, rec, recdir in T0:
        new_cfg = f"M2S72-T0-{short}"
        ref, new = RefRun(os.path.join(out, "ref"), src), RefRun(runs, new_cfg)
        if not (os.path.isdir(ref.pdir) and os.path.isdir(new.pdir)):
            rows.append((f"T0-{short}", "FAIL", "run missing"))
            continue
        P = lambda run, net, n: os.path.join(run.pdir, f"{net}.{n}.pcapRecorder[0].pcapng")  # noqa: E731
        ids = {"slave": (gptp_id(P(ref, "M1Bridge", "talker"), R.REQ), gptp_id(P(new, "M2S72Bridge", "talker[0]"), R.REQ)),
               "GM": (gptp_id(P(ref, "M1Bridge", "listener"), R.SYNC), gptp_id(P(new, "M2S72Bridge", "listener"), R.SYNC))}
        subst = {a: b for a, b in ids.values()}
        diffs = CMP.compare_runs(ref, new, map_name=map_path, map_module=map_path, subst=subst)
        st = CMP.compare_runs.stats
        idtxt = ", ".join(f"{k} {a.hex()} -> {b.hex()}" for k, (a, b) in ids.items())
        rows.append((f"T0-{short}", "PASS" if not diffs else "FAIL",
                     f"{new_cfg} vs {src}: {CMP.compare_runs.nfiles} files compared ({st.get('vectors', 0)} vectors, "
                     f"{st.get('scalar_items', 0)} scalar items); clockIdentity {idtxt}; frames with the identity substituted "
                     f"{st.get('frames_substituted', 0)}, log cells {st.get('cells_substituted', 0)} (of which payload hashes of frames "
                     f"not yet transmitted at the end of the run, reconstructed: {st.get('cells_reconstructed', 0)})"
                     + ("; DIFFERENCES: " + "; ".join(diffs[:8]) + (f" (+{len(diffs) - 8})" if len(diffs) > 8 else "") if diffs else "")))
        # the reference reproduces the committed record
        H = {}
        for line in open(os.path.join(recs, rec, "raw-outputs.sha256")):
            h, p = line.rstrip("\n").split("  ", 1)
            H[p] = h
        pre = f"{recdir}/"
        exp = {p[len(pre):]: h for p, h in H.items() if p.startswith(pre) and re.match(rf"(pcap|m2log)/{re.escape(src)}-0/", p[len(pre):])}
        bad, n = [], 0
        for rel, h in sorted(exp.items()):
            f = os.path.join(ref.base, rel)
            n += 1
            if not os.path.exists(f) or hashlib.sha256(open(f, "rb").read()).hexdigest() != h:
                bad.append(rel)
        have = sum(len(fs) for d in (ref.pdir, ref.ldir) for _, _, fs in os.walk(d))
        rows.append((f"T0-R-{short}", "PASS" if not bad and n == have and n > 0 else "FAIL",
                     f"{src} rerun vs results/{rec}/raw-outputs.sha256 ({recdir}, repetition 0): {n} committed PCAP/log hashes, "
                     f"{have} files in the rerun, {len(bad)} different" + (f": {bad[:4]}" if bad else "")))
    print("M2-S7.2a gate T0 (design rev. 2, 8.1)\n")
    for r in rows:
        print(" | ".join(r))
    nf = sum(1 for r in rows if r[1] == "FAIL")
    print(f"\nT0: {sum(1 for r in rows if r[1] == 'PASS')} PASS, {nf} FAIL")
    return 0 if nf == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
