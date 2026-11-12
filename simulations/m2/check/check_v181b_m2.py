#!/usr/bin/env python3
"""M2-R181b version-appropriate rows for M2 (alongside, never replacing, the historical checkers).

    check_v181b_m2.py a7  <M2-S0 runs dir>  [--mutate]   A7-v  (M2S0-load, M2S0-load-harq16, seed 0)
    check_v181b_m2.py c10 <M2-S1 runs dir>  [--mutate]   C10-v (M2S1-load, M2S1-load-harq16, seed 0)
    check_v181b_m2.py r2b <M2-S4 runs dir>  [--mutate]   R2b-v (M2S4 vs M2S4-ctl-nopdelay, seeds 0-9 and load)

Independent of the historical checkers: reads only the PCAP files (pcapng.py).

A7-v / C10-v, delivery and conservation across the 5G system, per configuration and direction:
  enter = frames sent on the near translator's 5G-side port eth[0] (DL nwTt, UL dsTt; pcapRecorder[0], outbound),
  leave = frames received on the far translator's 5G-side port eth[0] (inbound).
  (1) every leaving frame is byte-identical to an entering frame (same bytes, matched per flow key and occurrence);
  (2) no frame leaves twice; per flow key (etherType, PCP, VID) the leaving order is the entering order;
  (3) conservation: entered = left + still inside at the end, and every frame still inside entered in the last
      W_END = 100 ms before the end of the run (5 s); nothing else is missing.
  For the 5-HARQ and the 16-HARQ configuration alike: the 1.8.0 rows required loss with 5 HARQ processes.
  Mutation: one leaving DL frame of the first configuration is removed -> (3) FAIL.

R2b-v, attribution of application-frame latency changes, M2S4 vs M2S4-ctl-nopdelay (same seed):
  (1) the same application frames are delivered in both runs (per direction);
  (2) every application frame arrives at its receiving station at exactly the same time in both runs;
  (3) every application frame leaves its sending station at exactly the same time in both runs, except a frame that
      in M2S4 starts transmission exactly one inter-frame gap (96 ns) after the end of the sending station's own
      Pdelay_Req (queued behind it); such a frame is listed with its shift.
  Mutation: one arrival in M2S4 seed 0 shifted by 1 ns -> (2) FAIL.
"""
import os
import sys
from collections import Counter, defaultdict

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pcapng  # noqa: E402

MODE, RUNS = sys.argv[1], sys.argv[2]
MUTATE = "--mutate" in sys.argv
PS_PER_BYTE = 8000
IFG_PS = 12 * PS_PER_BYTE
END_PS, W_END_PS = 5 * 10 ** 12, 100 * 10 ** 9
rows = []


def add(name, ok, det):
    rows.append(("PASS" if ok else "FAIL", name, det))


def frames(path):
    out, occ = [], Counter()
    for p in pcapng.read(path):
        f = pcapng.ethernet(p["data"])
        k = (f["etherType"], f["pcp"], f["vid"])
        h = pcapng.fnv1a64(f["payload"])
        occ[(k, h, p["dir"])] += 1
        mt = (f["payload"][0] & 15) if f["etherType"] == 0x88F7 and f["payload"] else None
        L = len(p["data"])
        out.append({"end": p["t_ps"], "start": p["t_ps"] - (L + 8) * PS_PER_BYTE, "dir": p["dir"], "flow": k,
                    "id": (k, h, occ[(k, h, p["dir"])]), "bytes": p["data"], "mt": mt, "et": f["etherType"]})
    return out


def conservation(cfgs, title):
    ok_all, det = True, []
    for ci, cfg in enumerate(cfgs):
        d = os.path.join(RUNS, cfg, "pcap", f"{cfg}-0")
        if not os.path.isdir(d):
            ok_all = False
            det.append(f"{cfg}: runs missing")
            continue
        nw = frames(os.path.join(d, "M1Bridge.nwTt.pcapRecorder[0].pcapng"))
        ds = frames(os.path.join(d, "M1Bridge.dsTt.pcapRecorder[0].pcapng"))
        for dirn, near, far in (("DL", nw, ds), ("UL", ds, nw)):
            ent = [f for f in near if f["dir"] == 2]
            lev = [f for f in far if f["dir"] == 1]
            if MUTATE and ci == 0 and dirn == "DL":
                lev = lev[:len(lev) // 2] + lev[len(lev) // 2 + 1:]
            ein = {f["id"]: f for f in ent}
            unknown = [f for f in lev if f["id"] not in ein]
            altered = [f for f in lev if f["id"] in ein and ein[f["id"]]["bytes"] != f["bytes"]]
            ids = [f["id"] for f in lev]
            dup = len(ids) - len(set(ids))
            pos = {f["id"]: i for i, f in enumerate(ent)}
            last, disorder = {}, 0
            for f in lev:
                if f["id"] in pos:
                    if f["flow"] in last and pos[f["id"]] < last[f["flow"]]:
                        disorder += 1
                    last[f["flow"]] = pos[f["id"]]
            left = set(ids)
            inside = [f for f in ent if f["id"] not in left]
            early = [f for f in inside if f["end"] < END_PS - W_END_PS]
            kinds = Counter(("gptp" if f["et"] == 0x88F7 else f"pcp{f['flow'][1]}") for f in inside)
            ok = not unknown and not altered and not dup and not disorder and not early and len(ent) == len(set(ids)) + len(inside)
            ok_all &= ok
            det.append(f"{cfg} {dirn}: entered {len(ent)}, left {len(lev)}, still inside at the end {len(inside)} "
                       f"{dict(kinds)} (entered before end - 100 ms: {len(early)}); unknown {len(unknown)}, altered {len(altered)}, "
                       f"duplicated {dup}, out of order {disorder}")
    add(title, ok_all, " | ".join(det))


def r2b():
    probs, ncmp, queued, shifted_ok = [], 0, [], 0
    pairs = [(("M2S4", r), ("M2S4-ctl-nopdelay", r)) for r in range(10)] + [(("M2S4-load", 0), ("M2S4-ctl-nopdelay-load", 0))]
    for (cfg, r), (cc, rc) in pairs:
        pa, pc = os.path.join(RUNS, cfg, "pcap", f"{cfg}-{r}"), os.path.join(RUNS, cc, "pcap", f"{cc}-{rc}")
        if not (os.path.isdir(pa) and os.path.isdir(pc)):
            probs.append(f"{cfg}#{r}: runs missing")
            continue
        st = {}
        for run, p in (("a", pa), ("c", pc)):
            st[run] = {n: frames(os.path.join(p, f"M1Bridge.{n}.pcapRecorder[0].pcapng")) for n in ("talker", "listener")}
        if MUTATE and r == 0:
            lst = st["a"]["listener"]
            i = next(i for i, f in enumerate(lst) if f["dir"] == 1 and f["et"] != 0x88F7)
            lst[i] = dict(lst[i], end=lst[i]["end"] + 1000)
        for dirn, snd, rcv in (("UL", "talker", "listener"), ("DL", "listener", "talker")):
            tx = {run: {f["id"]: f for f in st[run][snd] if f["dir"] == 2 and f["et"] != 0x88F7} for run in "ac"}
            rx = {run: {f["id"]: f for f in st[run][rcv] if f["dir"] == 1 and f["et"] != 0x88F7 and f["id"] in tx[run]} for run in "ac"}
            if set(rx["a"]) != set(rx["c"]):
                probs.append(f"{cfg}#{r} {dirn}: delivered sets differ ({len(rx['a'])} vs {len(rx['c'])})")
            ncmp += len(rx["a"])
            arr = [k for k in rx["a"] if k in rx["c"] and rx["a"][k]["end"] != rx["c"][k]["end"]]
            if arr:
                probs.append(f"{cfg}#{r} {dirn}: {len(arr)} arrival times differ")
            seq = [f for f in st["a"][snd] if f["dir"] == 2]
            behind = {seq[i]["id"] for i in range(1, len(seq)) if seq[i]["et"] != 0x88F7 and seq[i - 1]["mt"] == 2
                      and seq[i]["start"] - seq[i - 1]["end"] == IFG_PS}
            for k, f in tx["a"].items():
                if k in tx["c"] and f["end"] != tx["c"][k]["end"]:
                    if k in behind:
                        queued.append((cfg, r, dirn, round(f["end"] / 1e12, 9), (f["end"] - tx["c"][k]["end"]) // 1000))
                        shifted_ok += 1
                    else:
                        probs.append(f"{cfg}#{r} {dirn}: send time differs for a frame not queued behind a Pdelay_Req")
    add("R2b-v attribution (M2S4 vs M2S4-ctl-nopdelay, seeds 0-9 and load): same application frames delivered; every "
        "arrival time identical; send times identical except frames queued at their station's egress behind its own Pdelay_Req",
        not probs and ncmp > 0,
        f"{ncmp} application frames compared; send-time shifts, all behind the station's own Pdelay_Req: {len(queued)} "
        f"{dict(Counter(x[4] for x in queued)) or ''} ns "
        f"(config, seed, dir, send end s, shift ns: {queued[:12]}); problems: {probs[:4] or 'none'}")


if MODE == "a7":
    conservation(("M2S0-load", "M2S0-load-harq16"),
                 "A7-v load (M2S0-load, 5 and 16 HARQ processes, seed 0): every frame that leaves the 5G system is one that "
                 "entered it, byte-identical, once, in order per flow; every other frame entered in the last 100 ms (still inside)")
elif MODE == "c10":
    conservation(("M2S1-load", "M2S1-load-harq16"),
                 "C10-v load (M2S1-load, 5 and 16 HARQ processes, seed 0): every frame that leaves the 5G system is one that "
                 "entered it, byte-identical, once, in order per flow; every other frame entered in the last 100 ms (still inside)")
elif MODE == "r2b":
    r2b()
else:
    sys.exit(f"unknown mode {MODE}")
title = {"a7": "A7-v", "c10": "C10-v", "r2b": "R2b-v"}[MODE]
print(f"M2-R181b version-appropriate row {title}{' (MUTATION CONTROL)' if MUTATE else ''}")
for v, n, d in rows:
    print(f"{v:4}  {n}\n      {d}")
print(f"\nOVERALL: {'PASS' if all(r[0] == 'PASS' for r in rows) else 'FAIL'}")
