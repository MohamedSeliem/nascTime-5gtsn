#!/usr/bin/env python3
"""M2-S5 gate V0 (migration/m2-s5-design.md 6.0): survival of the TtSyncIngressTag, VALID and
INVALID, from the NW-TT ingress to the DS-TT egress, before DS-TT rejection is relied on.

Usage: gate_v0.py <M2-S5 runs dir> <config> [<config> ...]   (also imported by check_m2s5.py)

For every run: every Follow_Up the DS-TT transmits on eth[1] (PCAP) has exactly one audit row
at the DS-TT egress (same order); each audit row carries exactly one TtSyncIngressTag over the
whole Follow_Up chunk; matched by the M2-S0 frame id to the NW-TT ingress row that created
it, the tag content (VALID/INVALID, reason, ttId, sequenceId, TSi, Lup, rr_out, cf1) is
identical; at least one INVALID tag is observed; every NW-TT Follow_Up missing at the DS-TT
is listed (it can only be lost in the 5GS).
"""
import csv
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcapng  # noqa: E402


def read_csv(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def v0_run(runs, cfg, rep=0, network="M1Bridge", nw="nwTt", ds="dsTt"):
    ldir = os.path.join(runs, cfg, "m2log", f"{cfg}-{rep}")
    pdir = os.path.join(runs, cfg, "pcap", f"{cfg}-{rep}")
    nwlog = read_csv(os.path.join(ldir, f"{network}.{nw}.eth[1].trafficConditionerLayer.syncIn.sync.csv"))
    dslog = read_csv(os.path.join(ldir, f"{network}.{ds}.eth[1].trafficConditionerLayer.syncOut.sync.csv"))
    sent = {r["fuFrameId"]: r for r in nwlog if r["event"] in ("corrected", "invalid")}
    audit = [r for r in dslog if r["event"] == "audit"]
    fus_out = 0
    for p in pcapng.read(os.path.join(pdir, f"{network}.{ds}.pcapRecorder[1].pcapng")):
        f = pcapng.ethernet(p["data"])
        if p["dir"] == 2 and f["etherType"] == 0x88F7 and f["payload"] and f["payload"][0] & 15 == 8:
            fus_out += 1
    probs, n_inv, n_val = [], 0, 0
    if fus_out != len(audit):
        probs.append(f"{fus_out} Follow_Ups transmitted, {len(audit)} audit rows")
    seen = set()
    for r in audit:
        if r["tagValid"] == "":
            probs.append(f"seq {r['seq']} (frame {r['fuFrameId']}): no single whole tag ({r['note']})")
            continue
        s = sent.get(r["fuFrameId"])
        if s is None:
            probs.append(f"seq {r['seq']}: frame id {r['fuFrameId']} not created by the NW-TT")
            continue
        seen.add(r["fuFrameId"])
        valid = s["event"] == "corrected"
        exp = {"tagValid": "1" if valid else "0", "tagReason": "" if valid else s["note"], "tagTtId": "1", "tagSeq": s["seq"],
               "TSi": s["TSi"] if valid else "", "Lup": s["Lup"] if valid else "", "cfIn": s["cfOut"]}
        got = {k: r[k] for k in exp}
        if got != exp:
            probs.append(f"seq {r['seq']}: tag {got} != created {exp}")
        if valid:
            n_val += 1
        else:
            n_inv += 1
    missing = sorted(int(s["seq"]) for k, s in sent.items() if k not in seen)
    if n_inv == 0:
        probs.append("no INVALID tag observed")
    return not probs, {"followUps": fus_out, "valid": n_val, "invalid": n_inv, "lostIn5GS": missing,
                       "invalidReasons": sorted({s["note"] for s in sent.values() if s["event"] == "invalid"})}, probs


if __name__ == "__main__":
    runs = sys.argv[1]
    ok_all = True
    for cfg in sys.argv[2:]:
        ok, info, probs = v0_run(runs, cfg)
        ok_all &= ok
        print(f"{'PASS' if ok else 'FAIL'}  {cfg}#0: {info}" + ("" if ok else f"\n      {probs[:6]}"))
    print(f"\nV0: {'PASS' if ok_all else 'FAIL'}")
    sys.exit(0 if ok_all else 1)
