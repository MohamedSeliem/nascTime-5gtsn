#!/usr/bin/env python3
"""M2-S7.2a A2-D2: PROPOSED read-only evaluator of the single real-NACK validation run A2-V1 (design review
results/M2-S7.2a-a2d2-design-review.md). No simulation. A-2 is FROZEN at fbee202: this tool imports and calls it
(check_m2s72_a2.inputs / evaluate) unchanged and never re-implements or adjusts it.

    check_m2s72_a2v1.py v1 <runs> <cfg> <records dir> [--a2-json <a2-<cfg>.json from check_m2s72_a2.py a2>]
        rows V-0 .. V-8 (required), D-1 .. D-3 / S-1 .. S-3 (desirable, reported, never gate), the in-memory negative
        controls NC-V-* on this run, -> a2v1-<cfg>.txt / .json.
        Exit 0 ACCEPTED, 1 NOT ACCEPTED (a required row FAILS or a control is not as declared), 3 STOP: NO NACK (V-1),
        4 STOP: DESIGN NOT REALISED (V-0 or V-2), 2 evaluation error.

Design constants (declared before the run; the configuration M2S72A2V-ideal-nack-ue1 in m2s72a2v.ini): ue[1] DL
perDl 0.1 per attempt, harqReduction 1; ue[0] DL and every UL loss-free; maxHarqRtx 3 (Simu5G default).
Row definitions and the rationale: design review §6. A row this run cannot exercise is NOT EXERCISED, never PASS."""
import gzip
import json
import math
import os
import re
import sys
import tempfile
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import check_m2s72_a2 as C  # noqa: E402  (frozen at fbee202)
import m2s72_a2 as A2  # noqa: E402  (frozen at fbee202)
import m2s72_a2probe as PR  # noqa: E402

S, MS = A2.S, A2.MS
NET = PR.NET
NE, NX = "NOT EVALUATED", "NOT EXERCISED"
DESIGN = {"nack_ue": 1, "clean_ue": 0, "per_dl": 0.1, "harq_reduction": 1.0, "max_rtx": 3, "min_nack": 30}
REQUIRED = ("V-0", "V-1", "V-2", "V-3", "V-4", "V-5", "V-6", "V-7", "V-8")
REL_TOL = 1e-9
R_UE_FB = PR.R_UE_FB
R_FB = PR.R_FB
R_EXTRACT = PR.R_EXTRACT
R_URTX = PR.R_URTX
R_RTXACID = PR.R_RTXACID
ORD = {1: "1st", 2: "2nd", 3: "3rd", 4: "4th"}


# ------------------------------------------------------------------------------------------------ inputs --------
def raw_counts(path):
    """one pass over the full MAC log for the lines A2.load does not keep: UL H-ARQ TX feedback on the UEs (UL NACKs)"""
    c = Counter()
    if not path or not os.path.exists(path):
        return None
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.split("|", 2)
            if len(p) < 3 or not p[0][:1].isdigit():
                continue
            if PR.R_UE_MOD.match(p[1]):
                m = R_FB.search(p[2])
                if m:
                    c[f"UE UL H-ARQ TX feedback {m.group(3)}"] += 1
    return c


def sca_read(sca):
    """(par, scalar): {(module, name): value} from the run's .sca"""
    par, sc = {}, {}
    if not sca or not os.path.exists(sca):
        return par, sc
    for line in open(sca, errors="replace"):
        if line.startswith("par ") or line.startswith("scalar "):
            p = line.rstrip("\n").split(" ", 3)
            if len(p) == 4:
                (par if p[0] == "par" else sc)[(p[1], p[2])] = p[3].strip().strip('"')
    return par, sc


def _f(x):
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


# ------------------------------------------------------------------------------------------------- rows ---------
def v_rows(res, rows, per, cov, lines, node_id, sca, raw, d=DESIGN):
    """the A2-V1 rows on one evaluated run. res / rows / per / cov: the frozen A-2's outputs on this log"""
    st = {r[0]: r[2] for r in rows}
    det = {r[0]: r[3] for r in rows}
    par, sc = sca_read(sca)
    out = []
    kn, kc = d["nack_ue"], d["clean_ue"]
    nn, nc = (node_id or {}).get(kn), (node_id or {}).get(kc)

    def row(name, ok, detail, exercised=True, evaluable=True):
        out.append((name, NE if not evaluable else ("PASS" if ok and exercised else (NX if ok else "FAIL")), detail))

    # V-0: the run realised the declared channel configuration (its own parameter records)
    cm = lambda k: f"{NET}.ue[{k}].cellularNic.nrChannelModel[0]"  # noqa: E731
    g = f"{NET}.gnb1.cellularNic.channelModel[0]"
    want = {(cm(kn), "perDl"): d["per_dl"], (cm(kn), "harqReduction"): d["harq_reduction"], (cm(kc), "perDl"): 0.0,
            (cm(kn), "perUl"): 0.0, (cm(kc), "perUl"): 0.0, (g, "perUl"): 0.0, (g, "perDl"): 0.0}
    bad = [f"{m.split('.', 1)[1]} {n} = {par.get((m, n), 'absent')} (declared {v:g})" for (m, n), v in want.items()
           if _f(par.get((m, n))) is None or abs(_f(par.get((m, n))) - v) > 1e-12]
    bad += [f"{m.split('.', 1)[1]} typename = {par.get((m, 'typename'), 'absent')} (declared IdealChannelModel)"
            for m in (g, cm(kn), cm(kc)) if "IdealChannelModel" not in par.get((m, "typename"), "")]
    row("V-0", not bad, f"FAIL {bad}" if bad else "IdealChannelModel parameters as declared: " + ", ".join(
        f"{m.split('.', 1)[1].replace('.cellularNic', '')} {n} {par[(m, n)]}" for (m, n) in want), evaluable=bool(par))

    # V-1: Simu5G-generated DL NACKs exist (gNB feedback lines and gNB unit 'set for RTX' / discard lines)
    nack_lines = sum(1 for x in res["fb"] if x["res"] == "NACK")
    unit_rtx = sum(1 for x in lines if x.split("|", 2)[1:2] == [A2.GNB] and R_URTX.search(x))
    row("V-1", nack_lines >= d["min_nack"] and unit_rtx >= 1,
        f"gNB NACK feedback lines {nack_lines} (floor {d['min_nack']}), unit 'set for RTX' lines {unit_rtx}")

    # V-2: specificity: NACKs only where the design puts them (DL of the nack UE); none on the clean UE, none UL
    ue_fb = Counter()
    for x in lines:
        p = x.split("|", 2)
        if len(p) == 3:
            mu = PR.R_UE_MOD.match(p[1])
            m = R_UE_FB.search(p[2])
            if m and mu:
                ue_fb[(int(mu.group(1)), m.group(4))] += 1
            elif m and p[1] == A2.GNB:
                ue_fb[("gNB UL RX", m.group(4))] += 1
    pc = per.get(nc, {}) if nc is not None else {}
    probs = []
    if nc is None or not pc:
        probs.append(f"clean ue[{kc}] node unknown or without feedback")
    else:
        if pc.get("nack", 0) or pc.get("retransmissions", 0) or pc.get("discarded", 0):
            probs.append(f"clean ue[{kc}] (node {nc}): A-2 NACK {pc.get('nack')}, retransmissions {pc.get('retransmissions')}, "
                         f"discarded {pc.get('discarded')}")
    if ue_fb[(kc, "NACK")]:
        probs.append(f"clean ue[{kc}] sent {ue_fb[(kc, 'NACK')]} DL NACKs (UE side)")
    if ue_fb[("gNB UL RX", "NACK")]:
        probs.append(f"gNB UL H-ARQ RX sent {ue_fb[('gNB UL RX', 'NACK')]} NACKs")
    if raw is None:
        probs.append("full MAC log not read (UL H-ARQ TX feedback on the UEs unknown)")
    elif raw.get("UE UL H-ARQ TX feedback NACK"):
        probs.append(f"UE UL H-ARQ TX received {raw['UE UL H-ARQ TX feedback NACK']} NACKs")
    row("V-2", not probs, f"FAIL {probs}" if probs else
        f"clean ue[{kc}] (node {nc}): NACK 0, retransmissions 0; UE-side DL NACK ue[{kc}] 0; UL NACK 0 (gNB RX "
        f"{ue_fb[('gNB UL RX', 'ACK')]} ACK, UE TX {raw.get('UE UL H-ARQ TX feedback ACK', 0)} ACK)")

    # V-3: the frozen A-2 is VALID on real NACK output, with the NACK paths exercised (A2-4 PASS, not NOT EXERCISED)
    verdict, _ = A2.verdict(rows)
    need = ("A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4", "A2-6", "A2-7", "A2-8")
    notp = {k: st.get(k) for k in need if st.get(k) != "PASS"}
    if st.get("A2-5") not in ("PASS", NX):
        notp["A2-5"] = st.get("A2-5")
    row("V-3", verdict == "A-2 VALID" and not notp,
        f"A-2 verdict {verdict}; rows not as required {notp} " + "; ".join(f"{k}: {det[k][:160]}" for k in notp) if notp or
        verdict != "A-2 VALID" else f"A-2 VALID; {', '.join(f'{k} PASS' for k in need)}; A2-5 {st.get('A2-5')}")

    # V-4: retransmissions re-extract the same PDU id (raw extract lines, independently of A-2's state machine)
    ext = Counter()
    ext_node = {}
    for x in lines:
        p = x.split("|", 2)
        if len(p) == 3 and p[1] == A2.GNB:
            m = R_EXTRACT.search(p[2])
            if m:
                ext[int(m.group(1))] += 1
                ext_node.setdefault(int(m.group(1)), set()).add(int(m.group(4)))
    re_ids = {pid for pid, n in ext.items() if n >= 2}
    a2_re = {pid for pid, u in res["pdus"].items() if u["ntx"] >= 2}
    other = sorted(pid for pid in re_ids if ext_node[pid] != {nn})
    foreign = sorted(pid for pid in ext if pid not in res["pdus"])
    cnt = all(ext[p] == res["pdus"][p]["ntx"] for p in re_ids & set(res["pdus"]))
    row("V-4", re_ids == a2_re and not other and not foreign and cnt,
        f"PDU ids extracted twice or more: {len(re_ids)} (A-2: {len(a2_re)} PDUs with >= 2 transmissions); owned by "
        f"another node than ue[{kn}] {other[:3]}; extracted ids never inserted {foreign[:3]}; extract counts = A-2 "
        f"transmissions: {cnt}", exercised=bool(re_ids))

    # V-5: chain arithmetic and retransmission count of the nack UE, per PDU
    us = [u for u in res["pdus"].values() if u["node"] == nn]
    probs = []
    for u in us:
        seq = [r for _, r in u["fbs"]]
        k = len(seq) - (1 if u["end"] == "ack" else 0)
        if any(r != "NACK" for r in seq[:k]) or (u["end"] == "ack" and seq[-1:] != ["ACK"]):
            probs.append(f"PDU {u['pid']}: feedback {seq}, end {u['end']}")
        elif u["end"] == "ack" and u["ntx"] != len(seq):
            probs.append(f"PDU {u['pid']}: {u['ntx']} transmissions, {len(seq)} feedbacks, ACKed")
        elif u["end"] == "discard" and (u["ntx"] != d["max_rtx"] + 1 or len(seq) != u["ntx"]):
            probs.append(f"PDU {u['pid']}: discarded after {u['ntx']} transmissions, {len(seq)} feedbacks")
        elif u["end"] == "censored: awaiting retransmission" and len(seq) != u["ntx"]:
            probs.append(f"PDU {u['pid']}: awaiting retransmission with {u['ntx']} transmissions, {len(seq)} feedbacks")
    nk = sum(1 for u in us for _, r in u["fbs"] if r == "NACK")
    rtx = sum(u["ntx"] - 1 for u in us)
    disc = sum(1 for u in us if u["end"] == "discard")
    aw = sum(1 for u in us if u["end"] == "censored: awaiting retransmission")
    if nk != rtx + disc + aw:
        probs.append(f"NACKs {nk} != retransmissions {rtx} + discards {disc} + awaiting retransmission {aw}")
    hist = Counter(u["ntx"] for u in us if u["end"] == "ack")
    row("V-5", not probs, f"FAIL {probs[:4]}" if probs else
        f"ue[{kn}] (node {nn}): NACKs {nk} = retransmissions {rtx} + discards {disc} + awaiting retransmission {aw}; "
        f"ACKed PDUs by transmissions {dict(sorted(hist.items()))}", exercised=rtx > 0)

    # V-6: UE-side independent feedback reconstruction: the UE's own NACK lines = A-2's NACKs of that UE
    pn = per.get(nn, {})
    ue_n = ue_fb[(kn, "NACK")]
    dstar = res["d_star"] or 0
    tail = sum(1 for x in lines if x.split("|", 2)[1:2] == [f"{NET}.ue[{kn}].cellularNic.nrMac"] and R_UE_FB.search(x)
               and R_UE_FB.search(x).group(4) == "NACK" and PR.t_ps(x.split("|", 1)[0]) > res["t_end"] - dstar)
    a2n = pn.get("nack", 0)
    row("V-6", st.get("A2-7") == "PASS" and a2n <= ue_n <= a2n + tail,
        f"A2-7 {st.get('A2-7')}; ue[{kn}] UE-side NACK lines {ue_n}, A-2 NACKs {a2n} (UE-side lines in the last d* "
        f"{tail} may be unanswered at the end)", exercised=a2n > 0)

    # V-7: per-UE occupancy with NACKed units kept busy: confirmed by the reference (A2-7) and exercised
    lat = [int(k) for k in pn.get("harq_latency_ps", {})]
    long_ = sum(v for k, v in pn.get("harq_latency_ps", {}).items() if int(k) > dstar)
    row("V-7", st.get("A2-7") == "PASS",
        f"A2-7 {st.get('A2-7')}; ue[{kn}] ACKed PDUs busy longer than d* {dstar} ps (across >= 1 NACK): {long_}; "
        f"max busy {max(lat) if lat else None} ps; occupancy max peak {pn.get('occupancy', {}).get('max_peak')}",
        exercised=long_ > 0)

    # V-8: Simu5G's own per-UE statistics agree (A2-8) and show the NACKs on the nack UE only
    mk = lambda k: f"{NET}.ue[{k}].cellularNic.nrMac"  # noqa: E731
    en, ec = _f(sc.get((mk(kn), "harqErrorRateDl:mean"))), _f(sc.get((mk(kc), "harqErrorRateDl:mean")))
    row("V-8", st.get("A2-8") == "PASS" and en is not None and en > 0 and ec == 0,
        f"A2-8 {st.get('A2-8')}; Simu5G harqErrorRateDl:mean ue[{kn}] {en}, ue[{kc}] {ec}", evaluable=bool(sc))

    # desirable coverage (reported, never gates)
    cv = {name: n for name, n, _ in cov}
    out.append(("D-1", "PASS" if disc else NX, f"real discard after maxHarqRtx + 1 = {d['max_rtx'] + 1} transmissions: {disc} "
                f"(A2-2 {st.get('A2-2')}); not required (design review §6.3)"))
    out.append(("D-2", "PASS" if cv.get("mixed ACK / NACK groups") else NX,
                f"mixed ACK / NACK groups (same TTI and process, both UEs): {cv.get('mixed ACK / NACK groups', 0)}"))
    out.append(("D-3", "PASS" if hist and max(hist) >= 3 else NX, f"ACKed PDUs with >= 3 transmissions: "
                f"{sum(v for k, v in hist.items() if k >= 3)}"))
    # supplementary Simu5G statistics (exact identities; reported, never gate)
    att = Counter()
    for x in res["fb"]:
        if x["owner"] == nn:
            att[(x["ntx"], x["res"])] += 1
    bad, ok, ne = [], [], []
    for n in range(1, 5):
        tot = att[(n, "ACK")] + att[(n, "NACK")]
        rec = _f(sc.get((mk(kn), f"harqErrorRate_{ORD[n]}_Dl:mean")))
        if not tot:
            ne.append(f"attempt {n}: no feedback")
            continue
        val = att[(n, "NACK")] / tot
        (ok if rec is not None and abs(rec - val) <= REL_TOL * max(1, val) else bad).append(f"attempt {n}: Simu5G {rec}, A-2 {val:.12g}")
    out.append(("S-1", "FAIL" if bad else ("PASS" if ok else NE), f"per-attempt DL error rates of ue[{kn}]: "
                f"{'FAIL ' + str(bad) + '; ' if bad else ''}equal {ok}; {ne}"))
    acked = sum(1 for u in us if u["end"] == "ack")
    rec = _f(sc.get((mk(kn), "macPacketLossDl:mean")))
    val = disc / (acked + disc) if acked + disc else None
    out.append(("S-2", NE if val is None or rec is None else ("PASS" if abs(rec - val) <= REL_TOL * max(1, val) else "FAIL"),
                f"macPacketLossDl:mean of ue[{kn}]: Simu5G {rec}, A-2 discards / (ACKed + discards) {val}"))
    n1 = att[(1, "ACK")] + att[(1, "NACK")]
    if n1:
        q = att[(1, "NACK")] / n1
        z = abs(q - d["per_dl"]) / math.sqrt(d["per_dl"] * (1 - d["per_dl"]) / n1)
        out.append(("S-3", "PASS" if z <= 3.29 else "FAIL", f"first-attempt NACK fraction {q:.4f} over {n1} first transmissions "
                    f"vs declared perDl {d['per_dl']}: |z| {z:.2f} (bound 3.29, two-sided 0.1 %)"))
    else:
        out.append(("S-3", NE, "no first transmissions of the nack UE"))
    return out


def accept(vrows, ctl):
    s = {r[0]: r[1] for r in vrows}
    if s.get("V-0") != "PASS" or s.get("V-2") != "PASS":
        if s.get("V-1") != "PASS":
            return "STOP: NO NACK (V-1) AND DESIGN NOT REALISED", 4
        return "STOP: DESIGN NOT REALISED (V-0 / V-2)", 4
    if s.get("V-1") != "PASS":
        return "STOP: NO NACK (V-1)", 3
    if any(s.get(k) != "PASS" for k in REQUIRED) or any(c[2] != "AS DECLARED" for c in ctl if c[2] != "NOT BUILDABLE"):
        return "NOT ACCEPTED", 1
    return "ACCEPTED: real DL NACK / retransmission chains reconstructed by the frozen A-2", 0


# --------------------------------------------------------------------------------------------- controls ---------
def _first(lines, pred):
    return next((i for i, x in enumerate(lines) if pred(x)), None)


def controls(lines, nproc, t0, node_id, grants, sca, root, raw, d=DESIGN):
    """in-memory mutations of THIS run's real NACK evidence; each must make the declared row(s) FAIL. A mutation that
    changes nothing is reported MUTATION NOT APPLIED (never AS DECLARED)"""
    out = []
    nn, nc = node_id.get(d["nack_ue"]), node_id.get(d["clean_ue"])
    gnb = lambda x: x.split("|", 2)[1:2] == [A2.GNB]  # noqa: E731
    ue_mod = lambda k: f"{NET}.ue[{k}].cellularNic.nrMac"  # noqa: E731

    def run(ls, sca_=sca):
        res, rows, per, cov, extra, window = C.evaluate(ls, nproc, t0, node_id, grants, sca_, root)
        return {r[0]: r[1] for r in v_rows(res, rows, per, cov, ls, node_id, sca_, raw, d)}, {r[0]: r[2] for r in rows}

    def rec(name, ls, rows_fail, sca_=sca, why=""):
        if ls is None:
            out.append((name, "-", "NOT BUILDABLE", why or "no such evidence in this run"))
            return
        if sca_ == sca and ls == lines:
            out.append((name, "-", "MUTATION NOT APPLIED", "the mutated input equals the original"))
            return
        v, a = run(ls, sca_)
        got = {k: v.get(k, a.get(k)) for k in rows_fail}
        out.append((name, ", ".join(f"{k} {g}" for k, g in got.items()), "AS DECLARED" if all(g == "FAIL" for g in got.values())
                    else "NOT AS DECLARED", f"declared: {', '.join(k + ' FAIL' for k in rows_fail)}; {why}"))

    i = _first(lines, lambda x: gnb(x) and R_URTX.search(x))
    rec("NC-V-unitline: one real gNB 'set for RTX' unit line removed", None if i is None else lines[:i] + lines[i + 1:],
        ["A2-1"], why=f"line {i}")
    i = _first(lines, lambda x: gnb(x) and R_RTXACID.search(x) and int(R_RTXACID.search(x).group(2)) == nn)
    rec("NC-V-rtxacid: one real DL rtxAcid line names the clean UE", None if i is None or nc is None else
        lines[:i] + [lines[i].replace(f"User[{nn}]", f"User[{nc}]")] + lines[i + 1:], ["A2-4"], why=f"line {i}")
    seen, j = set(), None
    for k, x in enumerate(lines):
        m = gnb(x) and R_EXTRACT.search(x)
        if m:
            if m.group(1) in seen:
                j = k
                break
            seen.add(m.group(1))
    if j is not None:
        m = R_EXTRACT.search(lines[j])
        fresh = str(max(int(s) for s in seen) + 10 ** 6)
        mut = lines[:j] + [lines[j].replace(f"(id {m.group(1)} )", f"(id {fresh} )")] + lines[j + 1:]
    rec("NC-V-reextract: one real retransmission extracts another PDU id", None if j is None else mut, ["V-4"], why=f"line {j}")
    i = _first(lines, lambda x: x.split("|", 2)[1:2] == [ue_mod(d["nack_ue"])] and R_UE_FB.search(x)
               and R_UE_FB.search(x).group(4) == "NACK")
    rec("NC-V-uenack: one real UE-side NACK of the nack UE rewritten as ACK", None if i is None else
        lines[:i] + [lines[i].replace("result: NACK", "result: ACK")] + lines[i + 1:], ["A2-7", "V-6"], why=f"line {i}")
    i = _first(lines, lambda x: x.split("|", 2)[1:2] == [ue_mod(d["clean_ue"])] and R_UE_FB.search(x)
               and R_UE_FB.search(x).group(4) == "ACK")
    rec("NC-V-cleannack: one UE-side ACK of the clean UE rewritten as NACK", None if i is None else
        lines[:i] + [lines[i].replace("result: ACK", "result: NACK")] + lines[i + 1:], ["V-2"], why=f"line {i}")
    # sca: the declared perDl of the nack UE, and its per-attempt statistic
    for name, key, rows_fail in (("NC-V-config: the run's recorded perDl of the nack UE changed to 0.2", "perDl", ["V-0"]),
                                 ("NC-V-scalar: Simu5G harqErrorRateDl:mean of the nack UE perturbed", "harqErrorRateDl:mean", ["V-8"])):
        if not sca or not os.path.exists(sca):
            rec(name, None, rows_fail, why="no .sca")
            continue
        txt = open(sca, errors="replace").read().split("\n")
        mod = f"{NET}.ue[{d['nack_ue']}].cellularNic." + ("nrChannelModel[0]" if key == "perDl" else "nrMac")
        k = _first(txt, lambda x: x.split(" ")[1:3] == [mod, key])
        if k is None:
            rec(name, None, rows_fail, why=f"no {mod} {key} record")
            continue
        p = txt[k].split(" ", 3)
        txt[k] = " ".join(p[:3] + ["0.2" if key == "perDl" else repr(float(p[3]) + 0.001)])
        fd, tmp = tempfile.mkstemp(suffix=".sca")
        with os.fdopen(fd, "w") as fh:
            fh.write("\n".join(txt))
        try:
            rec(name, lines, rows_fail, sca_=tmp, why=f"{p[3]} -> {txt[k].split(' ')[3]}")
        finally:
            os.remove(tmp)
    return out


# ------------------------------------------------------------------------------------------------- CLI ----------
def v1(runs, cfg, recdir, a2_json=None, t0=2 * S):
    lines, grants, node_id, sca, root = C.inputs(runs, cfg)
    nproc = C._nproc(cfg)
    res, rows, per, cov, extra, window = C.evaluate(lines, nproc, t0, node_id, grants, sca, root)
    raw = raw_counts(os.path.join(runs, f"run-{cfg}.log.gz"))
    vr = v_rows(res, rows, per, cov, lines, node_id, sca, raw)
    same = None
    if a2_json:
        j = json.load(open(a2_json))
        same = [list(r) for r in rows] == [list(r) for r in j["rows"]]
        vr.insert(0, ("V-a2", "PASS" if same else "FAIL", f"in-process A-2 rows {'=' if same else '!='} the frozen CLI's {a2_json}"))
    s = {r[0]: r[1] for r in vr}
    ctl = controls(lines, nproc, t0, node_id or {}, grants, sca, root, raw) if s.get("V-1") == "PASS" and s.get("V-0") == "PASS" else []
    verdict, rc = accept(vr, ctl)
    if same is False:
        verdict, rc = "NOT ACCEPTED (in-process A-2 differs from the frozen CLI)", 1
    os.makedirs(recdir, exist_ok=True)
    p = os.path.join(recdir, f"a2v1-{cfg}.txt")
    with open(p, "w") as fh:
        fh.write(f"M2-S7.2a A2-V1 real-NACK validation of the frozen A-2 on {cfg} (design review M2-S7.2a-a2d2-design-review.md §6)\n")
        fh.write(f"design constants {DESIGN}; node ids {node_id}\n\nROWS (V-*: required; D-*, S-*: desirable, reported, never gate)\n")
        for r in vr:
            fh.write(f"  {r[1]:<15} | {r[0]} | {r[2]}\n")
        fh.write("\nNEGATIVE CONTROLS ON THIS RUN (in memory; raw outputs only read)\n")
        for c in ctl or [("(not run: V-0 / V-1 not PASS)", "-", "-", "-")]:
            fh.write(f"  {c[2]:<20} | {c[0]} | observed {c[1]} | {c[3]}\n")
        fh.write(f"\nA2-V1 verdict: {verdict}\n")
    with open(os.path.join(recdir, f"a2v1-{cfg}.json"), "w") as fh:
        json.dump({"config": cfg, "design": DESIGN, "rows": vr, "controls": ctl, "verdict": verdict,
                   "a2_rows": rows, "per_ue": C._clean(per), "coverage": cov}, fh, indent=1, sort_keys=True, default=str)
    C._durable([p, os.path.join(recdir, f"a2v1-{cfg}.json")])
    print(open(p).read().rstrip())
    return rc


def main(argv):
    try:
        a2j = None
        if "--a2-json" in argv:
            i = argv.index("--a2-json")
            a2j = argv[i + 1]
            argv = argv[:i] + argv[i + 2:]
        if len(argv) == 5 and argv[1] == "v1":
            return v1(argv[2], argv[3], argv[4], a2j)
    except Exception as ex:  # an evaluation error is never a verdict
        import traceback
        traceback.print_exc()
        print(f"EVALUATION ERROR: {type(ex).__name__}: {ex}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
