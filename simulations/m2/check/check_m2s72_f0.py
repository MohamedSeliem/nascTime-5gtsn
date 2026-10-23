#!/usr/bin/env python3
"""M2-S7.2a gate F0 (migration/m2-s7.2a-design.md rev. 2, 3.3 and 8.1): feasibility of several UEs in bridge mode.

    check_m2s72_f0.py <results/M2-S7.2a> [config regex]   -> prints the F0 record (m2s72.sh f0 writes f0-check.txt)

Runs (runs/<config>/..., m2s72.sh f0): M2S72-F0-<opt>-n<N> (census: D-4 timing, learning recorders), its twin
-ev (eventlog over [0, 0.5 s]) and its twin -norec (no learning recorders); opt q0 (Q-0) and qdu (Q-d (UM),
experimental comparison), N = 1, 2, 4, 8, seed 0, 12 s.

Rows (every value from PCAP, logs, vectors or the eventlog; integer ps; no tolerance):
  F0-1  every GM Sync / Follow_Up of the cohort (GM transmission <= T_end - 0.5 s) reaches every DS-TT eth[0]
        exactly once (no duplicate anywhere in the run); N3 carries exactly N downlink copies of each, one per
        session tunnel, with the option's QFI (Q-0: 0, Q-d (UM): 10)
  F0-2  every Follow_Up copy a DS-TT corrected carried a valid NW-TT tag identical to the NW-TT ingress log
        (tag TT id 1, tag sequence, TSi, Lup, rate ratio) and the NW-TT's correctionField (cfIn = NW-TT cfOut)
  F0-3  no gPTP frame upstream: none on N3 uplink, none out of any DS-TT eth[0], none on N6 towards the NW-TT
  F0-4  misdirected frames M_j = 0 for every session j (DL GTP-U packets on tunnel j whose inner destination is
        a unicast MAC other than talker[j]'s), exact count from the learning recorder on N3
  F0-5  per-UE RLC entities exactly the configured DRBs (gNB and UE side); every gPTP copy of tunnel k enters
        UE k's gPTP DRB at the gNB (Q-0: DRB 1, Q-d (UM): DRB 4) and no gPTP SDU enters another DRB
  F0-6  learning order, VLAN-aware (INET MacForwardingTable keys (VID, MAC)): for every key (MAC, VID) to which
        unicast is sent through the UPF bridge, lambda (first frame from that MAC with that VID at the bridge,
        from the opposite side) + d < tau (first unicast to it at the bridge) + d, strictly. Each key is VALID,
        MISORDERED (lambda >= tau), or MISSING (no learning frame at all); a mandatory key (talker[k], VID 42 for
        every k; listener, VID 42) without unicast traffic is MISSING-TRAFFIC. Only VALID passes.
  F0-7  eventlog twin: every output of -ev equals the census run's; fingerprints equal; the UPF-internal delays
        d (interface record -> MAC-table call) measured for every learning frame and first unicast in [0, 0.5 s],
        one value per direction, the same in every census run
  F0-8  UPF MAC-table agingTime > 20 s (the longest S7.2a run, H0)
  F0-9  (added at implementation, see results) learning recorders non-perturbing: every output of the census
        run except the two learning recorders' equals the -norec twin's, with one exclusion: the treeId column of
        the nascTime logs (design X-1: OMNeT++'s process-wide message tree counter; the recorders create packet
        copies); fingerprints equal
"""
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import m2s72_runs as R  # noqa: E402
import m2s72_compare as CMP  # noqa: E402
import m2s6_runs as RR  # noqa: E402

PS_S = 10 ** 12
VID = 42
QFI = {"q0": 0, "qdu": 10}
GPTP_DRB = {"q0": 1, "qdu": 4}
DRBS = {"q0": {1, 2}, "qdu": {1, 2, 4}}
# Sync and Follow_Up SDU sizes (B) at the gNB RLC entity of the gPTP DRB (receivedPacketFromUpperLayer), as recorded:
# 62 / 92 on DRB 1 (Q-0), 61 / 91 on DRB 4 (Q-d (UM)); the base flows' SDUs are 119 / 120 B. The classification is
# fail-safe: the count on the gPTP DRB must equal the tunnel's gPTP copies, and no SDU of any of these sizes may
# appear on another DRB.
GPTP_SDU = {"q0": {"62", "92"}, "qdu": {"61", "91"}}
GPTP_ANY = {"61", "62", "91", "92"}
COHORT_MARGIN = PS_S // 2
rows = []


def add(row, run, ok, detail):
    rows.append((row, run, "PASS" if ok else "FAIL", detail))


def info(row, run, detail):
    rows.append((row, run, "INFO", detail))


def t_end(run):
    with open(run.sca_path) as fh:
        for line in fh:
            if line.startswith("config sim-time-limit "):
                v = line.split()[2]
                m = re.fullmatch(r"(\d+)s", v)
                if not m:
                    raise ValueError(f"sim-time-limit {v}")
                return int(m.group(1)) * PS_S
    raise ValueError("no sim-time-limit")


def gptp_seq(fr):
    return fr["seq"]


# ---------------------------------------------------------------------------------------------------------------
def f01(run, opt, name):
    T = t_end(run)
    gm = [f for f in run.gm if f["dir"] == 2 and f["type"] in (R.SYNC, R.FU) and f["dom"] == 0]
    cohort = {(f["type"], f["seq"]) for f in gm if f["end"] <= T - COHORT_MARGIN}
    allgm = {(f["type"], f["seq"]) for f in gm}
    probs, tail = [], 0
    for k in range(run.n):
        u = run.ue_view(k)
        got = Counter((f["type"], f["seq"]) for f in u.ds0 if f["dir"] == 1 and f["type"] in (R.SYNC, R.FU) and f["dom"] == 0)
        miss = sorted(cohort - set(got))
        dup = sorted(x for x, c in got.items() if c > 1)
        alien = sorted(set(got) - allgm)
        tail += len(set(got) - cohort)
        if miss or dup or alien:
            probs.append(f"dsTt[{k}]: missing {miss[:4]}{'...' if len(miss) > 4 else ''} ({len(miss)}), "
                         f"duplicated {dup[:4]} ({len(dup)}), not from the GM {alien[:4]}")
    n3 = [r for r in R.n3_records(run.n3path) if r["dir"] == 2 and r["gtype"] in (R.SYNC, R.FU)]
    seqs = defaultdict(list)
    for r in n3:
        seqs[(r["gtype"], r["gseq"])].append(r)
    teids = sorted({r["teid"] for r in n3})
    if len(teids) != run.n:
        probs.append(f"N3: gPTP copies on {len(teids)} tunnels {teids}, expected {run.n}")
    badq = Counter(r["qfi"] for r in n3 if r["qfi"] != QFI[opt])
    if badq:
        probs.append(f"N3: copies with QFI {dict(badq)} (expected {QFI[opt]})")
    for key in sorted(cohort):
        c = seqs.get(key, [])
        if sorted(r["teid"] for r in c) != teids:
            probs.append(f"N3 {key}: copies on tunnels {sorted(r['teid'] for r in c)}")
            break
    nsync = sum(1 for x in cohort if x[0] == R.SYNC)
    nfu = len(cohort) - nsync
    add("F0-1", name, not probs,
        f"cohort {nsync} Sync + {nfu} Follow_Up (GM end <= T_end - 0.5 s) x {run.n} DS-TTs; N3 {len(n3)} DL gPTP copies "
        f"on tunnels {teids}, QFI {sorted({r['qfi'] for r in n3})}; tail deliveries outside the cohort {tail}"
        + ("; " + "; ".join(probs[:6]) if probs else ""))
    return teids


def f02(run, name):
    nw = {}
    for r in run.nwlog:
        if r["event"] == "corrected" and r["msgType"] == "8":
            if r["seq"] in nw:
                add("F0-2", name, False, f"NW-TT corrected Follow_Up {r['seq']} twice")
                return
            nw[r["seq"]] = r
    probs, n = [], 0
    for k in range(run.n):
        u = run.ue_view(k)
        for r in u.dslog:
            if r["msgType"] != "8":
                continue
            if r["event"] != "corrected":
                probs.append(f"dsTt[{k}] Follow_Up {r['seq']}: event {r['event']} {r['tagReason']} {r['note']}")
                continue
            n += 1
            w = nw.get(r["seq"])
            exp = None if w is None else {"tagValid": "1", "tagTtId": "1", "tagSeq": r["seq"], "TSi": w["TSi"],
                                          "Lup": w["Lup"], "rrOut": w["rrOut"], "cfIn": w["cfOut"]}
            if exp is None:
                probs.append(f"dsTt[{k}] Follow_Up {r['seq']}: no NW-TT entry")
                continue
            diff = {c: (r[c], v) for c, v in exp.items() if r[c] != v}
            if diff:
                probs.append(f"dsTt[{k}] Follow_Up {r['seq']}: {diff}")
    add("F0-2", name, not probs and n > 0,
        f"{n} corrected Follow_Up copies over {run.n} DS-TTs; NW-TT corrected {len(nw)}" + ("; " + "; ".join(probs[:5]) if probs else ""))


def f03(run, name):
    n3 = [r for r in R.n3_records(run.n3path) if r["dir"] == 1 and r["gtype"] >= 0]
    dsout = {k: sum(1 for f in run.ue_view(k).ds0 if f["dir"] == 2 and f["type"] >= 0) for k in range(run.n)}
    dnout = sum(1 for f in run.dn if f["dir"] == 2 and f["type"] >= 0)
    nwin = sum(1 for f in run.nw0 if f["dir"] == 1 and f["type"] >= 0)
    ok = not n3 and not any(dsout.values()) and dnout == 0 and nwin == 0
    add("F0-3", name, ok, f"gPTP on N3 uplink {len(n3)}; out of DS-TT eth[0] {dsout}; UPF dnEth out {dnout}; NW-TT eth[0] in {nwin}")


def macs(run):
    tk = {k: run.mac_of(run.ue_view(k).sl) for k in range(run.n)}
    lst = run.mac_of(run.gm)
    if len(set(tk.values()) | {lst}) != run.n + 1:
        raise ValueError(f"{run.cfg}: station MACs not distinct {tk} {lst}")
    return tk, lst


def sessions(run, n3, tk):
    """TEID of session k: the tunnel carrying talker[k]'s uplink frames (each TEID one talker, each talker one TEID)."""
    by = defaultdict(set)
    for r in n3:
        if r["dir"] == 1 and r["src"] is not None:
            by[r["src"]].add(r["teid"])
    teid, probs = {}, []
    for k, m in tk.items():
        if len(by.get(m, ())) != 1:
            probs.append(f"talker[{k}] uplink on tunnels {sorted(by.get(m, ()))}")
        else:
            teid[k] = next(iter(by[m]))
    if len(set(teid.values())) != len(teid):
        probs.append(f"tunnels shared {teid}")
    return teid, probs


run_listener = [None]


def f04(run, name, n3, tk, teid):
    rev = {t: k for k, t in teid.items()}
    M, unattr, frag = Counter(), 0, 0
    first, last, dests = {}, {}, Counter()
    for r in n3:
        if r["dir"] != 2:
            continue
        if r["teid"] is None:
            frag += 1
            continue
        k = rev.get(r["teid"])
        if k is None:
            unattr += 1
            continue
        if R.is_unicast(r["dst"]) and r["dst"] != tk[k]:
            M[k] += 1
            first.setdefault(k, r["t"])
            last[k] = r["t"]
            dests[who(r["dst"], tk, run_listener[0])] += 1
    ok = not M and unattr == 0 and frag == 0
    span = (R.fmt_t(min(first.values())), R.fmt_t(max(last.values()))) if first else None
    add("F0-4", name, ok, f"misdirected M_j {[M.get(k, 0) for k in range(run.n)]}, total {sum(M.values())}; inner destination "
        f"{dict(dests)}; first/last {span}; DL packets on unknown tunnels {unattr}; non-first fragments {frag}")
    return M


def f05(run, opt, name, teids_gptp, teid):
    V = RR.read_vectors(run.vec_path)
    T = t_end(run)
    gnb = defaultdict(set)
    uei = defaultdict(set)
    for (m, n) in V:
        g = re.fullmatch(rf"{R.NET}\.gnb1\.cellularNic\.rlc-um-(\d+)-(\d+)\.tx", m)
        if g:
            gnb[int(g.group(1))].add(int(g.group(2)))
        u = re.fullmatch(rf"{R.NET}\.ue\[(\d+)\]\.cellularNic\.nrRlc-um-1-(\d+)\.rx", m)
        if u:
            uei[int(u.group(1))].add(int(u.group(2)))
    probs = []
    ids = set(run.node_id.values())
    for nid in gnb:
        if nid not in ids:
            probs.append(f"gNB entities of unknown node {nid}")
    n3 = [r for r in R.n3_records(run.n3path) if r["dir"] == 2 and r["gtype"] >= 0]
    counts = []
    for k in range(run.n):
        nid = run.node_id[k]
        if gnb.get(nid) != DRBS[opt] or uei.get(k) != DRBS[opt]:
            probs.append(f"ue[{k}] (node {nid}): gNB DRBs {sorted(gnb.get(nid, ()))}, UE DRBs {sorted(uei.get(k, ()))}, "
                         f"expected {sorted(DRBS[opt])}")
            continue
        sd = {d: [t for t, v in V[(f"{R.NET}.gnb1.cellularNic.rlc-um-{nid}-{d}.tx", "receivedPacketFromUpperLayer:vector(packetBytes)")]
                  if v in (GPTP_SDU[opt] if d == GPTP_DRB[opt] else GPTP_ANY)] for d in DRBS[opt]}
        other = {d: len(v) for d, v in sd.items() if d != GPTP_DRB[opt] and v}
        if other:
            probs.append(f"ue[{k}]: gPTP-size SDUs on DRBs {other}")
        if k in teid:
            cop = sorted(r["t"] for r in n3 if r["teid"] == teid[k])
        else:
            cop = None
        got = sorted(sd[GPTP_DRB[opt]])
        if cop is None:
            probs.append(f"ue[{k}]: tunnel unknown")
            continue
        comp = [t for t in cop if t <= T - 10 ** 9]
        pairs_ok = len(got) >= len(comp) and all(0 <= g - c <= 10 ** 9 for c, g in zip(comp, got))
        if not pairs_ok or len(got) > len(cop):
            probs.append(f"ue[{k}]: {len(cop)} gPTP copies on N3, {len(got)} gPTP SDUs on DRB {GPTP_DRB[opt]}")
        counts.append(f"ue[{k}] node {nid}: {len(got)}/{len(cop)}")
    add("F0-5", name, not probs, f"DRBs {sorted(DRBS[opt])}, gPTP on DRB {GPTP_DRB[opt]}: SDUs/N3 copies {counts}"
        + ("; " + "; ".join(probs[:5]) if probs else ""))


def learning(run, n3, dn, tk, lst, teid):
    """Per key (MAC, VID): lambda (first learning frame at the bridge) and tau (first unicast to it at the bridge),
    with the port each came from. Times are interface record times (d added by the caller)."""
    keys = {}
    rev = {t: k for k, t in teid.items()}
    # unicast destinations through the bridge
    for r in dn:
        if r["dir"] == 1 and R.is_unicast(r["dst"]):
            keys.setdefault((r["dst"], r["vid"]), {"tau": r["t"], "tau_side": "dn", "tau_i": r["i"]})
    for r in n3:
        if r["dir"] == 1 and r["src"] is not None and R.is_unicast(r["dst"]):
            k = (r["dst"], r["vid"])
            if k not in keys or r["t"] < keys[k]["tau"]:
                keys[k] = {"tau": r["t"], "tau_side": "n3", "tau_i": r["i"]}
    for (mac, vid), v in keys.items():
        lam = None
        if v["tau_side"] == "dn":     # destination behind a session: learned from its uplink frames
            for r in n3:
                if r["dir"] == 1 and r["src"] == mac and r["vid"] == vid:
                    lam = r
                    break
            v["lam_side"] = "n3"
        else:                         # destination on N6: learned from frames arriving on dnEth
            for r in dn:
                if r["dir"] == 1 and r["src"] == mac and r["vid"] == vid:
                    lam = r
                    break
            v["lam_side"] = "dn"
        v["lam"] = None if lam is None else lam["t"]
        v["lam_i"] = None if lam is None else lam["i"]
        v["lam_port"] = None if lam is None else (rev.get(lam.get("teid")) if v["lam_side"] == "n3" else "dnEth")
    return keys


def who(mac, tk, lst):
    for k, m in tk.items():
        if m == mac:
            return f"talker[{k}]"
    return "listener" if mac == lst else f"unknown {mac}"


def f06(run, name, keys, tk, lst, d):
    out, bad = [], 0
    mand = [(m, VID) for m in tk.values()] + [(lst, VID)]
    for key in mand:
        if key not in keys:
            out.append(f"{who(key[0], tk, lst)} VID {key[1]}: MISSING-TRAFFIC (no unicast to it)")
            bad += 1
    for (mac, vid), v in sorted(keys.items(), key=lambda kv: kv[1]["tau"]):
        nm = who(mac, tk, lst)
        if nm.startswith("unknown"):
            out.append(f"{nm} VID {vid}: unicast to an unknown station")
            bad += 1
            continue
        side_tau = "UL" if v["tau_side"] == "n3" else "DL"
        side_lam = "UL" if v["lam_side"] == "n3" else "DL"
        if d is None or d.get(side_tau) is None or d.get(side_lam) is None:
            out.append(f"{nm} VID {vid}: NOT EVALUATED (UPF-internal delay d not established by F0-7)")
            bad += 1
            continue
        tau = v["tau"] + d[side_tau]
        if v["lam"] is None:
            cls = "MISSING"
        else:
            lam = v["lam"] + d[side_lam]
            port_ok = (v["lam_port"] == "dnEth") if nm == "listener" else (v["lam_port"] == int(nm[7:-1]))
            cls = "VALID" if lam < tau and port_ok else ("WRONG-PORT" if lam < tau else "MISORDERED")
        if cls != "VALID":
            bad += 1
        lam_s = "none" if v["lam"] is None else R.fmt_t(v["lam"] + d[side_lam])
        mrg = "" if v["lam"] is None else f", margin {R.fmt_t(tau - (v['lam'] + d[side_lam]))}"
        out.append(f"{nm} VID {vid}: {cls}: lambda {lam_s} ({'N3 tunnel of ' + str(v['lam_port']) if v['lam_side'] == 'n3' else 'dnEth'}), "
                   f"tau {R.fmt_t(tau)} ({'dnEth' if v['tau_side'] == 'dn' else 'N3'}){mrg}")
    add("F0-6", name, bad == 0, f"{len(keys)} unicast keys, {bad} not VALID: " + "; ".join(out))
    return bad


def measure_d(ev_run, n3, dn, keys):
    """UPF-internal delay per side from the eventlog: for every learning frame (lambda) and first unicast (tau)
    recorded inside the eventlog interval, the MAC-table call it causes (learn / lookup), traced back by the
    cause-event chain to the UPF interface event; d = call time - interface record time."""
    E = R.Eventlog(ev_run.elog_path)
    ppp = E.ids(lambda p: p.startswith(f"{R.NET}.upf.ppp[0]"))
    dne = E.ids(lambda p: p.startswith(f"{R.NET}.upf.dnEth"))
    end = max(e["t"] for e in E.events)
    calls = defaultdict(list)    # (side, origin time, method) -> [call time]
    for ev, m in E.table_calls(f"{R.NET}.upf.ethBridge.macTable",
                               {"learnUnicastAddressForwardingInterface", "getUnicastAddressForwardingInterface"}):
        o = E.origin(ev, ppp | dne)
        if o is None:
            continue
        side = "n3" if o["m"] in ppp else "dn"
        calls[(side, o["t"], m)].append(ev["t"])
    rec_times = Counter([("n3", r["t"]) for r in n3 if r["dir"] == 1] + [("dn", r["t"]) for r in dn if r["dir"] == 1])
    meas = {"UL": [], "DL": []}
    notes = []
    for (mac, vid), v in keys.items():
        for what, t, side, method in (("lambda", v["lam"], v["lam_side"], "learnUnicastAddressForwardingInterface"),
                                      ("tau", v["tau"], v["tau_side"], "getUnicastAddressForwardingInterface")):
            if t is None:
                continue
            if t > end:
                notes.append(f"{mac}/{vid} {what} at {R.fmt_t(t)} after the eventlog interval")
                continue
            if rec_times[(side, t)] != 1:
                notes.append(f"{mac}/{vid} {what}: {rec_times[(side, t)]} interface records at {R.fmt_t(t)} (ambiguous)")
                continue
            c = calls.get((side, t, method), [])
            if len(c) != 1:
                notes.append(f"{mac}/{vid} {what}: {len(c)} {method} calls traced to the record at {R.fmt_t(t)}")
                continue
            meas["UL" if side == "n3" else "DL"].append(c[0] - t)
    return meas, notes, end


def f07(census, ev, name, n3, dn, keys):
    same = CMP.compare_runs(census, ev, exclude_files=lambda rel: rel.endswith(".elog"))
    fp_c, fp_e = fingerprint(census), fingerprint(ev)
    meas, notes, end = measure_d(ev, n3, dn, keys)
    d = {}
    for side, v in meas.items():
        d[side] = v[0] if v and len(set(v)) == 1 else None
    ok = not same and fp_c is not None and fp_c == fp_e and all(d[s] is not None for s in d) and not notes
    add("F0-7", name, ok, f"census vs eventlog twin: {'identical' if not same else 'DIFFERENT: ' + '; '.join(same[:4])}; "
        f"fingerprints {fp_c} / {fp_e}; eventlog interval [0, {R.fmt_t(end)}]; d measured UL {sorted(Counter(meas['UL']).items())} "
        f"DL {sorted(Counter(meas['DL']).items())} (ps: count)" + ("; " + "; ".join(notes[:6]) if notes else ""))
    return d if ok else None, meas


def fingerprint(run):
    p = os.path.join(os.path.dirname(run.base), f"run-{run.cfg}.log")
    if not os.path.exists(p):
        return None
    m = re.search(r"Fingerprint mismatch! calculated: (\S+),", open(p, errors="replace").read())
    return m.group(1) if m else None


def f08(run, name):
    v = run.par.get((f"{R.NET}.upf.ethBridge.macTable", "agingTime"))
    m = re.fullmatch(r"(\d+(?:\.\d+)?)s", v or "")
    add("F0-8", name, bool(m) and float(m.group(1)) > 20, f"upf.ethBridge.macTable agingTime {v} (> 20 s required)")


def f09(census, norec, name):
    lr = lambda rel: re.search(r"upf\.pcapRecorder\[[23]\]", rel) is not None  # noqa: E731
    diff = CMP.compare_runs(census, norec, exclude_files=lr, exclude_modules=lambda m: re.search(r"\.upf\.pcapRecorder\[[23]\]", m) is not None,
                            exclude_columns=("treeId",))
    st = CMP.compare_runs.stats
    fp_c, fp_n = fingerprint(census), fingerprint(norec)
    add("F0-9", name, not diff and fp_c is not None and fp_c == fp_n,
        f"census vs -norec (learning recorders' outputs excluded; log column treeId excluded, X-1: "
        f"{st.get('excluded_cells_differing', 0)} treeId cells differ): {'identical' if not diff else 'DIFFERENT: ' + '; '.join(diff[:4])}; "
        f"{CMP.compare_runs.nfiles} files; fingerprints {fp_c} / {fp_n}")


# ---------------------------------------------------------------------------------------------------------------
def main():
    out = sys.argv[1]
    runs = os.path.join(out, "runs")
    summary = []
    dvals = defaultdict(set)
    for opt in ("q0", "qdu"):
        for n in (1, 2, 4, 8):
            name = f"M2S72-F0-{opt}-n{n}"
            if len(sys.argv) > 2 and not re.search(sys.argv[2], name):   # optional config filter (debugging)
                continue
            if not os.path.isdir(os.path.join(runs, name)):
                add("F0", name, False, "run missing")
                continue
            run = R.Run72(runs, name)
            if run.n != n:
                add("F0", name, False, f"run has {run.n} UEs")
                continue
            ev = R.Run72(runs, name + "-ev")
            norec = R.Run72(runs, name + "-norec")
            teids = f01(run, opt, name)
            f02(run, name)
            f03(run, name)
            n3 = R.n3_records(run.learn_n3)
            dn = R.dn_records(run.learn_dn)
            tk, lst = macs(run)
            run_listener[0] = lst
            teid, probs = sessions(run, n3, tk)
            if probs:
                add("F0-4", name, False, "sessions: " + "; ".join(probs))
            else:
                info("sessions", name, f"tunnel per UE {teid}; MACs talker {tk}, listener {lst}; NR MAC node ids {run.node_id}")
                f04(run, name, n3, tk, teid)
            f05(run, opt, name, teids, teid)
            keys = learning(run, n3, dn, tk, lst, teid)
            d, meas = f07(run, ev, name, n3, dn, keys)
            for s, v in meas.items():
                dvals[s] |= set(v)
            bad = f06(run, name, keys, tk, lst, d)
            f08(run, name)
            f09(run, norec, name)
            summary.append((name, bad))
    # F0-7 across runs: one value per direction over every census run
    add("F0-7", "all census runs", all(len(v) == 1 for v in dvals.values()) and len(dvals) == 2,
        f"d per direction over all census runs: { {s: sorted(v) for s, v in dvals.items()} } (ps)")
    print("M2-S7.2a gate F0 (design rev. 2, 3.3 and 8.1)\n")
    for r in rows:
        print(" | ".join(r))
    np = sum(1 for r in rows if r[2] == "PASS")
    nf = sum(1 for r in rows if r[2] == "FAIL")
    print(f"\nF0: {np} PASS, {nf} FAIL")
    print("F0 verdict: " + ("PASS" if nf == 0 else "FAIL (stop and report: design 8.1, M1 S5 rule; no fallback, D-4 timing unchanged)"))
    return 0 if nf == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
