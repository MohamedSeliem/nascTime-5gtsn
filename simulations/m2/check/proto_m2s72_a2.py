#!/usr/bin/env python3
"""PROTOTYPE (A-2 design review evidence; results/M2-S7.2a-a2-design-review.md §6.4). Not a checker: no CLI on runs,
no rows, never imported by a checker. It exists so the reviewer can reproduce the feasibility sweep that supports the
proposed rule A-2 (gNB-only unit-state attribution) against the source-faithful generator m2s72_harqfix.make(), whose
truth is known by construction.

A-2 in one paragraph (full specification in the design review §5): replay the gNB DL H-ARQ TX state per unit
(node, process, codeword) from the gNB lines alone: insert opens a unit (PDU id, node); every 'extracted' line is a
transmission (PDU id, node) and sets last_tx; at a feedback line the candidates are the awaiting units on that
(process, codeword) with the largest age, which must equal d*_tx; a NACK (or discard) is identified by the PDU id of
its own unit line inside the same feedback event; an ACK with one candidate is attributed; ACKs with k >= 2 candidates
form an exchangeable group, certified when no other event of a candidate node lies between its lines."""
import sys
from collections import Counter, defaultdict

sys.dont_write_bytecode = True
import m2s72_a2probe as PR  # noqa: E402

MS = PR.MS


def attribute(lines):
    """returns (per_line, hist, problems): per_line[j] for the j-th gNB feedback line = {kind: 'id' (NACK / discard by
    PDU id) | 'single' | 'group' (exchangeable ACKs), owner, group (candidate nodes), pid, age, ntx, res}.
    A group = the feedback lines with the same (t, process, codeword); groups of one feedback burst may interleave
    (other processes), so every open group is resolved as a whole when the burst ends (time advances, or a gNB insert /
    extract of the main loop): NACKs by PDU id first, then the remaining ACK lines against the remaining candidates
    (1:1 single, k:k exchangeable, else a problem)"""
    units, per_line, probs, hist = {}, [], [], []
    block, gi, groups = None, 0, {}

    def close(key, idx, t):
        hist.append((idx, t, key[0], -1))
        del units[key]

    def finalize_all():
        for key in sorted(groups, key=lambda k: groups[k]["first"]):
            finalize(groups[key])
        groups.clear()

    def finalize(grp):
        cands = list(grp["cands"])
        for j, idx, t, res, bk in grp["lines"]:
            if res == "NACK":
                k = next((k for k in cands if units[k]["pid"] == (bk or {}).get("pid")), None)
                if k is None:
                    probs.append(f"NACK at {t} not identified among the candidates")
                    continue
                cands.remove(k)
                u = units[k]
                per_line[j] = {"kind": "id", "owner": k[0], "group": grp["nodes"], "pid": u["pid"], "age": grp["age"], "ntx": u["ntx"], "res": res}
                if bk["kind"] == "discard":
                    close(k, idx, t)
                else:
                    u["st"] = "BUF"
        acks = [x for x in grp["lines"] if x[3] == "ACK"]
        if len(acks) != len(cands):
            probs.append(f"group at {grp['t']}: {len(acks)} ACK lines for {len(cands)} remaining candidates")
        kind = "single" if len(acks) == 1 else "group"
        for (j, idx, t, res, bk), k in zip(acks, cands):        # any bijection: exchangeable (certificate below)
            u = units[k]
            per_line[j] = {"kind": kind, "owner": k[0], "group": grp["nodes"], "pid": u["pid"], "age": grp["age"], "ntx": u["ntx"], "res": res}
            close(k, idx, t)

    for raw in lines:
        p_ = raw.rstrip("\n").split("|", 2)
        if len(p_) < 3 or p_[1] != PR.GNB:
            continue
        t, msg = PR.t_ps(p_[0]), p_[2]
        gi += 1
        if PR.T_START in msg:
            block = {"pid": None, "kind": "ack"}
            continue
        m = PR.R_URTX.search(msg) or PR.R_UDISC.search(msg)
        if m and block is not None:
            block.update(pid=int(m.group(3)), kind="rtx" if PR.R_URTX.search(msg) else "discard")
            continue
        m = PR.R_INSERT.search(msg)
        if m:
            finalize_all()
            pid, p, cw, n = (int(x) for x in m.groups())
            if (n, p, cw) in units:
                probs.append(f"insert into occupied unit {(n, p, cw)}")
            units[(n, p, cw)] = {"pid": pid, "st": "INS", "last_tx": None, "ntx": 0, "t_ins": t}
            hist.append((gi, t, n, +1))
            continue
        m = PR.R_EXTRACT.search(msg)
        if m:
            finalize_all()
            pid, p, cw, n = (int(x) for x in m.groups())
            u = units.get((n, p, cw))
            if u is None or u["pid"] != pid:
                probs.append(f"extract of PDU {pid} not in its unit")
                continue
            u.update(st="WAIT", last_tx=t, ntx=u["ntx"] + 1)
            continue
        m = PR.R_FB.search(msg)
        if m:
            p, cw, res = int(m.group(1)), int(m.group(2)), m.group(3)
            key = (t, p, cw)
            if groups and next(iter(groups))[0] != t:
                finalize_all()
            grp = groups.get(key)
            if grp is None:
                cand = [k for k, u in units.items() if k[1] == p and k[2] == cw and u["st"] == "WAIT"]
                if not cand:
                    probs.append(f"feedback without candidate at {t}")
                    per_line.append({"kind": None, "owner": None, "group": [], "pid": None})
                    block = None
                    continue
                amax = max(t - units[k]["last_tx"] for k in cand)
                top = sorted(k for k in cand if t - units[k]["last_tx"] == amax)
                grp = groups[key] = {"key": key, "t": t, "cands": top, "nodes": sorted({k[0] for k in top}), "age": amax,
                                     "lines": [], "first": gi}
            per_line.append(None)
            grp["lines"].append((len(per_line) - 1, gi, t, res, block))
            block = None
    finalize_all()
    per_line = [x if x is not None else {"kind": None, "owner": None, "group": [], "pid": None} for x in per_line]
    return per_line, hist, probs


def occupancy(hist, nodes, nproc, span):
    import m2s72_peru as P
    out = {}
    for n in nodes:
        ev = [(i, t, d) for i, t, nn, d in hist if nn == n]
        out[n] = P.occupancy_log_order(ev, nproc, span)
    return out


def truth_hist(lines, truth):
    """busy events from the generator's truth: +1 at the insert line, -1 at the feedback line that ends the PDU"""
    hist, gi, fbk = [], 0, 0
    for raw in lines:
        p_ = raw.rstrip("\n").split("|", 2)
        if len(p_) < 3 or p_[1] != PR.GNB:
            continue
        gi += 1
        t = PR.t_ps(p_[0])
        m = PR.R_INSERT.search(p_[2])
        if m:
            hist.append((gi, t, int(m.group(4)), +1))
            continue
        if PR.R_FB.search(p_[2]):
            x = truth[fbk]
            fbk += 1
            if x["outcome"] in ("ack", "discard"):
                hist.append((gi, t, x["node"], -1))
    return hist


def compare(lines, node, truth, nproc):
    """the prototype vs the generator truth: per line, per UE aggregates, per-UE occupancy"""
    per_line, hist, probs = attribute(lines)
    r = Counter()
    for a, x in zip(per_line, truth):
        if a["kind"] in ("id", "single"):
            r[f"{a['kind']} {'ok' if a['owner'] == x['node'] else 'WRONG'}"] += 1
        elif a["kind"] == "group":
            r[f"group {'ok' if x['node'] in a['group'] else 'WRONG'}"] += 1
        else:
            r["unattributed"] += 1
    agg_a, agg_t = defaultdict(Counter), defaultdict(Counter)
    for a, x in zip(per_line, truth):
        agg_t[x["node"]].update({"feedback": 1, "nack": x["res"] == "NACK", f"ntx{x['ntx']}": 1, "discard": x["outcome"] == "discard"})
        if a["owner"] is not None:
            agg_a[a["owner"]].update({"feedback": 1, "nack": a["res"] == "NACK", f"ntx{a['ntx']}": 1,
                                      "discard": a["res"] == "NACK" and False})
    for n in agg_t:
        agg_t[n].pop("discard", None)
    for n in agg_a:
        agg_a[n].pop("discard", None)
    tt = [PR.t_ps(x.split("|")[0]) // MS for x in lines]
    span = (min(tt), max(tt) + 1)
    occ_a = occupancy(hist, sorted(node.values()), nproc, span)
    occ_t = occupancy(truth_hist(lines, truth), sorted(node.values()), nproc, span)
    return {"lines": dict(r), "aggregates_equal": {n: dict(agg_a[n]) == dict(agg_t[n]) for n in agg_t},
            "occupancy_equal": occ_a == occ_t, "problems": probs[:3], "n_problems": len(probs),
            "ages": dict(Counter(a.get("age") for a in per_line if a["kind"]))}


def sweep(seed=20261116):
    import random
    import m2s72_harqfix as F
    import m2s72_peru as P
    rnd = random.Random(seed)
    out = []
    for n_ue in (2, 3, 4):
        for nproc in (16, 5):
            for fb_first in (True, False):
                for rate in (0.0, 0.002, 0.02, 0.05):
                    probs = [0.97] + [rnd.choice([0.05, 0.2, 0.5]) for _ in range(n_ue - 1)]
                    sched = lambda tti, pr=probs, sd=n_ue: [k for k, q in enumerate(pr) if random.Random(tti * 7919 + sd * 31 + k).random() < q]  # noqa: E731
                    pids = range(800, 800 + 3000)
                    nack = {(x, a) for x in pids for a in (1, 2, 3, 4) if rnd.random() < rate}
                    lines, node, truth = F.make(n_ue, 600, sched, nack=nack, nproc=nproc, fb_first=fb_first, ue_log=False)
                    c = compare(lines, node, truth, nproc)
                    ev = [x for x in lines if x.split("|")[1] == F.GNB]
                    import m2s72_harqx as H
                    e = H.read_log(None, lines=lines)["events"]
                    trace = []
                    P.attribute_feedback(e, nproc, None, trace=trace)
                    a1_wrong = sum(1 for (i, nn, cl), x in zip(trace, truth) if cl in ("a1a", "a1b") and nn != x["node"])
                    a1_unres = sum(1 for (i, nn, cl) in trace if nn is None)
                    out.append(((n_ue, nproc, fb_first, rate), sum(1 for x in truth if x["res"] == "NACK"), c, a1_wrong, a1_unres, len(truth)))
                    del ev
    return out


if __name__ == "__main__":
    bad = 0
    for key, nacks, c, a1w, a1u, nfb in sweep():
        ok = (not any("WRONG" in k for k in c["lines"]) and "unattributed" not in c["lines"] and all(c["aggregates_equal"].values())
              and c["occupancy_equal"] and c["n_problems"] == 0 and len(c["ages"]) == 1)
        bad += not ok
        print(f"{'OK ' if ok else 'BAD'} N={key[0]} HARQ={key[1]:>2} fb_first={key[2]!s:5} NACK rate={key[3]:<5} | feedback lines {nfb:>4}, "
              f"NACK {nacks:>3} | A-2: {c['lines']} aggregates equal {all(c['aggregates_equal'].values())} occupancy equal "
              f"{c['occupancy_equal']} d* {list(c['ages'])} | A-1: wrong {a1w}, unresolved {a1u}")
    print(f"prototype sweep: {48 - bad} / 48 scenarios exact")
    sys.exit(1 if bad else 0)
