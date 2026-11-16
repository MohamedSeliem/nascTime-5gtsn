#!/usr/bin/env python3
"""M2-S7.2a Stage 5: DL H-ARQ attribution rule A-2.1 (gNB-only unit-state attribution, corrected for real NACKs), as
specified in results/M2-S7.2a-a2d2-f1-root-cause.md rev. 2 (decisions F1-a, F1-b, F1-c approved; F1-d option (i) for
supplementary post-hoc validation only). Read-only. A NEW version: the frozen A-2 (m2s72_a2.py, m2s72_a2probe.py,
check_m2s72_a2.py at fbee202) is unchanged and remains the record of every earlier result.

What A-2.1 changes, and only there (ACK-only paths are the frozen code paths):
  RC-1  a unit's NACK / discard line prints a HANDLE (cMessage id of the unit's Packet), not the MAC PDU id of the
        insert / extract lines (LteHarqUnitTx.cc:127, :142 vs LteHarqBufferTx.cc:131, :242). A-2.1 never compares the
        two. Handles are bound to PDU LIFECYCLES (MAC id, node, process, cw, insert time), never to reusable unit keys:
          B-1 bind only on a unique identification (single candidate; a resolved group with one RTX / DISC line)
          B-2 a bound handle may only appear in a group holding its lifecycle as a candidate
          B-3 one handle per lifecycle;  B-4 a retired handle (lifecycle ended) never reappears
          B-5 a handle never belongs to two lifecycles;  B-6 a new lifecycle on a reused key starts unbound
        (cMessage ids are monotonic in Cmdenv: cmessage.cc:44, :60; reuse only in Qtenv's privateDup)
        Groups whose remaining lines are mixed (NACK and ACK) or hold >= 2 NACKs are PENDING: each candidate is
        resolved by the first gNB main-loop event on its key: an extract of its own MAC id (retransmission: it was
        NACKed) or an insert (it was emptied: ACK or discard; LteHarqBufferTx.cc:122-123 forbids an insert into a
        busy unit). Counts close the group. Transitions are applied at the group's ORIGINAL line index and time.
        Simultaneous NACKs of several lifecycles keep their handle relations AMBIGUOUS (narrowed only by
        elimination); their lines are 'exchangeable-nack' (per-UE counts exact as a multiset, no unique claim).
  RC-2  the DL scheduler's node-identified lines (rtxAcid) are emitted by the submodule mac.schedulerDl and are absent
        when its log level is off (the runs' configuration). A2-4 is reported as three separate rows:
          A2-4a  gNB: per TTI and process, 'selected for retransmission' lines = retransmission extracts
          A2-4b  node identity of every retransmission from the receiving UE's own log (comparison only; XA data):
                 the i-th transmission of PDU X to node n is received by n's UE, in transmission order (no fixed
                 delay is assumed: reception after its transmission and before the next one of X)
          A2-4c  the original rule (scheduler rtxAcid naming node / process), verbatim; NOT EVALUATED when the log
                 holds no scheduler line (never PASS by absence)
  End of log (structural censoring, no empirical bound): a NACKed unit without retransmission, or a pending group,
        is censored only when no complete gNB main loop ("-----ENB MAIN LOOP -----" .. "--- END ENB MAIN LOOP ---",
        LteMacEnb.cc:767, :841) follows it in the log; otherwise it is UNRESOLVED -> A2-9 NOT EVALUATED -> INCOMPLETE.
        A log without main-loop markers never censors (fail-closed).
  F1-b  the P0 preconditions (A2-0) are computed by the same replay (one shared state machine), in the frozen format.

Rows: A2-0, A2-0s, A2-1, A2-2, A2-3, A2-4a, A2-4b, A2-4c, A2-5, A2-6, A2-7, A2-8 (as frozen, with censored lines and
the UEs they touch NOT EVALUATED instead of compared), A2-9 (resolution completeness: PASS / NOT EVALUATED).
Verdict: FAIL anywhere -> A-2.1 NOT VALID; a REQUIRED row neither PASS nor NOT EXERCISED -> A-2.1 INCOMPLETE.
Contracts: 'full' requires A2-4c; 'f1d-i' (supplementary post-hoc validation, decision F1-d (i)) reports it only."""
import gzip
import os
import re
import sys
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a2 as A2  # noqa: E402  (frozen; reused read-only: per_ue, grants_rows, source_row, sca_nodes, sentinel)
import m2s72_a2probe as PR  # noqa: E402  (frozen patterns)
import m2s72_peru as P  # noqa: E402

VERSION = "A-2.1"
S, MS = PR.S, PR.MS
GNB = PR.GNB
SCHED = GNB + ".schedulerDl"
NE, NX = "NOT EVALUATED", "NOT EXERCISED"
REL_TOL = 1e-9
ML_START, ML_END = "-----ENB MAIN LOOP -----", "--- END ENB MAIN LOOP ---"
KEYWORDS = A2.KEYWORDS + ("ENB MAIN LOOP",)
SENTINEL_MOD = A2.SENTINEL_MOD
UNIQUE = ("single", "bound", "resolved-by-rtx", "resolved-by-elimination")
REQUIRED = {"full": ("A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-4c", "A2-5", "A2-6", "A2-7", "A2-9"),
            "f1d-i": ("A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-5", "A2-6", "A2-7", "A2-9")}
NOTE = ("A-2.1 is a new version. Its rows gate only its own per-UE H-ARQ evaluation; they never replace, relabel or "
        "reclassify any accepted row or earlier result: the frozen A-2 results (fbee202), the recorded PU-4 FAIL of A-1 "
        "and the A2-V1 NOT ACCEPTED verdict stand unchanged.")


# ------------------------------------------------------------------------------------------------- input ---------
def load(path):
    """as the frozen A2.load, plus the main-loop markers (MAC) and any line of the scheduler submodule"""
    out, t_end = [], 0
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        for line in fh:
            p = line.split("|", 2)
            if len(p) < 3 or not p[0][:1].isdigit():
                continue
            t_end = max(t_end, PR.t_ps(p[0]))
            if p[1] == GNB:
                if any(k in p[2] for k in KEYWORDS):
                    out.append(line if line.endswith("\n") else line + "\n")
            elif p[1] == SCHED or (PR.R_UE_MOD.match(p[1]) and "H-ARQ RX" in p[2]):
                out.append(line if line.endswith("\n") else line + "\n")
    out.append(A2.sentinel(t_end))
    return out


sentinel = A2.sentinel
t_end_of = A2.t_end_of


# ------------------------------------------------------------------------------------------------ replay ---------
def replay(lines):
    """the A-2.1 state machine over the log lines (log order). Returns a result dict (keys at the end)."""
    units = {}                  # (node, p, cw) -> lifecycle dict (live unit)
    pdus = {}                   # MAC id -> lifecycle dict
    fb = []
    groups_done = []
    open_groups = {}
    pending = []                # groups awaiting resolution (deferred)
    finalized = set()
    burst_t = None
    viol = defaultdict(list)
    pviol = defaultdict(list)   # P0 preconditions (A2-0), shared replay (F1-b)
    busy = defaultdict(list)
    ages = Counter()
    rtx_ev = defaultdict(set)   # tti -> {(node, p, cw)} named by DL rtxAcid lines (any module)
    sched_lines = Counter()     # scheduler texts seen (A2-4c evidence)
    sel_ev = Counter()          # (tti, p) "selected for retransmission"
    rtx_x = Counter()           # (tti, p) retransmission extracts
    rtx_list = []               # (t, MAC id, node, p, cw, nth transmission)
    rtx_dir = None
    block = None
    nack_rtx_delay = []
    counts = Counter()
    handles = {}                # H -> {"st": bound | ambiguous | retired, "lc": MAC id | set}
    lc_handle = {}              # MAC id -> H
    loops = []                  # gi of the START line of every complete main loop
    ml_open = None
    t_end = 0
    gi = 0
    state = {"sel_without_rtx": []}

    def v(row, msg):
        viol[row].append(msg)

    def pv(row, msg):
        pviol[row].append(msg)

    # ---- handles (B-1 .. B-6) ------------------------------------------------------------------------------
    def lc_ended(pid):
        u = pdus.get(pid)
        return u is not None and u["end"] is not None

    def bind(h, pid, where):
        """bind handle h to lifecycle pid; False (and an A2-1 violation) on any rule violation"""
        if h is None:
            return True
        old = lc_handle.get(pid)
        if old is not None and old != h:
            v("A2-1", f"{where}: handle {h} identified as PDU {pid}'s, which already has handle {old} (B-3: one handle per lifecycle)")
            return False
        hs = handles.get(h)
        if hs is not None:
            if hs["st"] == "retired":
                v("A2-1", f"{where}: retired handle {h} (lifecycle {hs['lc']} ended) reappears for PDU {pid} (B-4)")
                return False
            if hs["st"] == "bound" and hs["lc"] != pid:
                v("A2-1", f"{where}: handle {h} is bound to PDU {hs['lc']}, here identified as PDU {pid}'s (B-5)")
                return False
            if hs["st"] == "ambiguous" and pid not in hs["lc"]:
                v("A2-1", f"{where}: handle {h} is ambiguous among PDUs {sorted(hs['lc'])}, here identified as PDU {pid}'s (B-5)")
                return False
        handles[h] = {"st": "retired" if lc_ended(pid) else "bound", "lc": pid}
        lc_handle[pid] = h
        return propagate(pid, h, where)

    def propagate(pid, h, where):
        ok = True
        changed = True
        while changed:
            changed = False
            for h2, hs in list(handles.items()):
                if hs["st"] != "ambiguous" or h2 == h:
                    continue
                taken = {x for x in hs["lc"] if lc_handle.get(x) not in (None, h2)}
                if taken:
                    hs["lc"] = hs["lc"] - taken
                    changed = True
                if not hs["lc"]:
                    v("A2-1", f"{where}: ambiguous handle {h2} has no lifecycle left (B-5)")
                    hs["st"] = "retired"
                    hs["lc"] = None
                    ok = False
                elif len(hs["lc"]) == 1:
                    (only,) = hs["lc"]
                    handles[h2] = {"st": "retired" if lc_ended(only) else "bound", "lc": only}
                    lc_handle[only] = h2
                    changed = True
        return ok

    def ambiguate(hs_list, pids, where):
        ok = True
        for h in hs_list:
            if h is None:
                continue
            cur = handles.get(h)
            if cur is None:
                handles[h] = {"st": "ambiguous", "lc": set(pids)}
            elif cur["st"] == "ambiguous":
                cur["lc"] = cur["lc"] & set(pids)
                if not cur["lc"]:
                    v("A2-1", f"{where}: ambiguous handle {h} is inconsistent with the NACKed PDUs {sorted(pids)} (B-5)")
                    ok = False
                elif len(cur["lc"]) == 1:
                    ok = bind(h, next(iter(cur["lc"])), where) and ok
            elif cur["st"] == "bound":
                if cur["lc"] not in pids:
                    v("A2-1", f"{where}: handle {h} bound to PDU {cur['lc']} appears for NACKed PDUs {sorted(pids)} (B-2)")
                    ok = False
            else:
                v("A2-1", f"{where}: retired handle {h} reappears (B-4)")
                ok = False
        return ok

    def retire(pid):
        h = lc_handle.get(pid)
        if h is not None and handles.get(h, {}).get("st") == "bound":
            handles[h]["st"] = "retired"

    # ---- lifecycle transitions at the ORIGINAL event (gi, t) -------------------------------------------------
    def close_unit(u, line, kind):
        u["end"], u["t_close"], u["close_gi"] = kind, line["t"], line["gi"]
        busy[u["node"]].append((line["gi"], line["t"], -1))
        retire(u["pid"])

    def assign(line, u, cls, age, ntx):
        line.update(cls=cls, owner=u["node"], pid=u["pid"], ntx=ntx, age=age, t_ins=u["t_ins"])

    def apply_nack(line, k, cls, g, ntx=None):
        """the line is a NACK (rtx or discard) of the live unit k; returns True if the unit was emptied"""
        u = units[k]
        assign(line, u, cls, g["age"], u["ntx"] if ntx is None else ntx)
        u["fbs"].append((line["t"], "NACK"))
        g["nacks"] += 1
        if line["block_kind"] == "discard":
            if line["maxrtx"] is None or line["ntx"] != line["maxrtx"] + 1:
                v("A2-2", f"t {line['t']}: PDU {u['pid']} discarded after {line['ntx']} transmissions (maxHarqRtx {line['maxrtx']})")
            del units[k]
            close_unit(u, line, "discard")
            return True
        u["st"], u["nack_t"], u["nack_gi"] = "BUF", line["t"], line["gi"]
        return False

    def ack_assign(g, acks, emptied):
        """ACK lines to emptied lifecycles (dicts, already out of `units` or about to be): single or exchangeable"""
        cls = "single" if len(acks) == 1 else "exchangeable"
        g["exchangeable"] = g["exchangeable"] or len(acks) >= 2
        if len(acks) >= 2:
            lo, hi = acks[0]["gi"], acks[-1]["gi"]
            inside = [(nd, e[0]) for nd in {u["node"] for u in emptied} for e in busy.get(nd, []) if e[2] > 0 and lo < e[0] < hi]
            if inside:
                v("A2-5", f"group t {g['t']} process {g['p']}: insert(s) of candidate nodes inside the group {inside[:3]} (not certified)")
        for x, u in zip(acks, sorted(emptied, key=lambda u: (u["node"], u["pid"]))):
            assign(x, u, cls, g["age"], g["ntx_at"].get(u["pid"], u["ntx"]))
            u["fbs"].append((x["t"], "ACK"))
            close_unit(u, x, "ack")
        g["acks"] += len(acks)

    def finalize(g):
        """steps 1-2 (design §7 / rev. 2 §3-§4): bound handles, counts; mixed remainder -> pending"""
        cands = list(g["cands"])
        g["ntx_at"] = {units[k]["pid"]: units[k]["ntx"] for k in cands}
        where = f"group t {g['t']} process {g['p']}"
        rest = []
        for line in g["lines"]:
            if line["res"] != "NACK":
                rest.append(line)
                continue
            h = line["handle"]
            hs = handles.get(h)
            if hs is None:
                rest.append(line)
                continue
            if hs["st"] == "retired":
                v("A2-1", f"{where}: retired handle {h} reappears (B-4)")
                line["cls"] = "unresolved"
                g["failed"] = True
                continue
            if hs["st"] == "bound":
                k = next((k for k in cands if units[k]["pid"] == hs["lc"]), None)
                if k is None:
                    v("A2-1", f"{where}: bound handle {h} (PDU {hs['lc']}) is not among the candidates (B-2)")
                    line["cls"] = "unresolved"
                    g["failed"] = True
                    continue
                cands.remove(k)
                apply_nack(line, k, "bound", g)
                continue
            inter = [k for k in cands if units[k]["pid"] in hs["lc"]]
            if not inter:
                v("A2-1", f"{where}: ambiguous handle {h} {sorted(hs['lc'])} has no candidate here (B-2)")
                line["cls"] = "unresolved"
                g["failed"] = True
                continue
            if len(inter) == 1:
                if bind(h, units[inter[0]]["pid"], where):
                    cands.remove(inter[0])
                    apply_nack(line, inter[0], "bound", g)
                else:
                    line["cls"] = "unresolved"
                    g["failed"] = True
                continue
            rest.append(line)
        if not rest:
            groups_done.append(g)
            return
        if len(rest) != len(cands):
            if all(x["res"] == "ACK" for x in rest):     # the frozen message, unchanged for ACK-only input
                v("A2-1", f"group t {g['t']} process {g['p']}: {len(rest)} ACK lines for {len(cands)} remaining candidates")
            else:
                v("A2-1", f"{where}: {len(rest)} remaining lines for {len(cands)} remaining candidates")
            for x in rest:
                x["cls"] = "unresolved"
            groups_done.append(g)
            return
        nacks = [x for x in rest if x["res"] == "NACK"]
        if len(cands) == 1:
            x, k = rest[0], cands[0]
            if x["res"] == "NACK":
                if bind(x["handle"], units[k]["pid"], where):
                    apply_nack(x, k, "single", g)
                else:
                    x["cls"] = "unresolved"
            else:
                u = units.pop(k)
                ack_assign(g, [x], [u])
            groups_done.append(g)
            return
        if not nacks:
            emptied = [units.pop(k) for k in sorted(cands, key=lambda k: (k[0], units[k]["pid"]))]
            ack_assign(g, rest, emptied)
            groups_done.append(g)
            return
        # PENDING: resolved later by each candidate's first main-loop event on its key
        g["pending"] = {"cands": list(cands), "lines": rest, "rtx": [], "emptied": []}
        for k in cands:
            units[k]["st"] = "PEND"
            units[k]["pend_g"] = g
        pending.append(g)
        n_r = sum(1 for x in rest if x["res"] == "NACK" and x["block_kind"] == "rtx")
        if n_r in (0, len(cands)):
            # counts close the group (rev. 2 §3): every candidate is emptied (no RTX line) or every candidate awaits a
            # retransmission (only RTX lines); nothing is left to resolve by later evidence
            pd = g["pending"]
            for k in sorted(cands, key=lambda k: (k[0], units[k]["pid"])):
                if n_r == 0:
                    pd["emptied"].append(units.pop(k))
                else:
                    units[k]["st"], units[k]["nack_t"], units[k]["nack_gi"] = "BUF", g["t"], rest[0]["gi"]
                    pd["rtx"].append(k)
            counts["groups closed by counts"] += 1
            finish_pending(g, f"{where} (closed by counts)")
            return
        counts["pending groups"] += 1

    def classify(k, outcome, t):
        """the first main-loop event on the key of a PEND unit: 'rtx' (extract of its own id) or 'emptied' (insert)"""
        u = units[k]
        g = u["pend_g"]
        pd = g["pending"]
        where = f"group t {g['t']} process {g['p']} (resolved at {t})"
        n_r = sum(1 for x in pd["lines"] if x["res"] == "NACK" and x["block_kind"] == "rtx")
        n_e = len(pd["lines"]) - n_r
        if outcome == "rtx":
            pd["rtx"].append(k)
            u["st"], u["nack_t"], u["nack_gi"] = "BUF", g["t"], pd["lines"][0]["gi"]
        else:
            pd["emptied"].append(units.pop(k))
        if len(pd["rtx"]) > n_r or len(pd["emptied"]) > n_e:
            v("A2-1", f"{where}: {len(pd['rtx'])} retransmitted / {len(pd['emptied'])} emptied candidates for {n_r} RTX and {n_e} "
                      f"ACK / discard lines")
            g["failed"] = True
        remaining = [c for c in pd["cands"] if c in units and units[c].get("pend_g") is g and units[c]["st"] == "PEND"]
        if g.get("failed"):
            for c in remaining:                          # outcome unknown; the group is already a FAIL (A2-1)
                units[c]["st"] = "PEND-FAILED"
            remaining = []
        else:
            if len(pd["rtx"]) == n_r:
                for c in remaining:
                    pd["emptied"].append(units.pop(c))
                remaining = []
            elif len(pd["emptied"]) == n_e:
                for c in remaining:
                    units[c]["st"], units[c]["nack_t"], units[c]["nack_gi"] = "BUF", g["t"], pd["lines"][0]["gi"]
                    pd["rtx"].append(c)
                remaining = []
        if remaining:
            return
        finish_pending(g, where)

    def finish_pending(g, where):
        pd = g["pending"]
        pending.remove(g)
        g["pending_done"] = True
        rtx_lines = [x for x in pd["lines"] if x["res"] == "NACK" and x["block_kind"] == "rtx"]
        disc_lines = [x for x in pd["lines"] if x["res"] == "NACK" and x["block_kind"] == "discard"]
        ack_lines = [x for x in pd["lines"] if x["res"] == "ACK"]
        if g.get("failed"):
            for x in pd["lines"]:
                x["cls"] = "unresolved"
            for u in pd["emptied"]:
                u["end"] = "unresolved: contradictory evidence"
            for c in pd["rtx"]:
                if c in units:
                    units[c].pop("pend_g", None)
            groups_done.append(g)
            return
        rtx_units = [units[c] for c in pd["rtx"]]
        for u in rtx_units:
            u.pop("pend_g", None)
        # RTX lines <-> retransmitted lifecycles
        if len(rtx_lines) == 1:
            x, u = rtx_lines[0], rtx_units[0]
            if bind(x["handle"], u["pid"], where):
                assign(x, u, "resolved-by-rtx", g["age"], g["ntx_at"][u["pid"]])
                u["fbs"].append((x["t"], "NACK"))
                g["nacks"] += 1
            else:
                x["cls"] = "unresolved"
        elif rtx_lines:
            pids = [u["pid"] for u in rtx_units]
            ambiguate([x["handle"] for x in rtx_lines], pids, where)
            for x, u in zip(rtx_lines, sorted(rtx_units, key=lambda u: (u["node"], u["pid"]))):
                assign(x, u, "exchangeable-nack", g["age"], g["ntx_at"][u["pid"]])
                x["owner_set"] = sorted(pids)
                u["fbs"].append((x["t"], "NACK"))
                g["nacks"] += 1
            g["multi_nack"] = len(rtx_lines)
            counts["multi-NACK groups"] += 1
        # DISC lines <-> emptied lifecycles: bound handles first, then eligibility (ntx = maxHarqRtx + 1)
        emptied = list(pd["emptied"])
        for x in list(disc_lines):
            hs = handles.get(x["handle"])
            if hs and hs["st"] in ("bound", "retired") and any(u["pid"] == hs["lc"] for u in emptied):
                u = next(u for u in emptied if u["pid"] == hs["lc"])
                emptied.remove(u)
                disc_lines.remove(x)
                assign(x, u, "bound", g["age"], g["ntx_at"][u["pid"]])
                u["fbs"].append((x["t"], "NACK"))
                g["nacks"] += 1
                close_unit(u, x, "discard")
        if disc_lines:
            mx = disc_lines[0]["maxrtx"]
            elig = [u for u in emptied if mx is not None and g["ntx_at"][u["pid"]] == mx + 1]
            if len(elig) != len(disc_lines):
                v("A2-1", f"{where}: {len(disc_lines)} discard line(s) for {len(elig)} eligible emptied lifecycles (UNRESOLVED discard)")
                for x in disc_lines + ack_lines:
                    x["cls"] = "unresolved"
                for u in emptied:
                    u["end"] = "unresolved: discard / ACK not separable"
                groups_done.append(g)
                return
            cls = "resolved-by-elimination" if len(elig) == 1 else "exchangeable"
            if len(elig) == 1:
                if not bind(disc_lines[0]["handle"], elig[0]["pid"], where):
                    disc_lines[0]["cls"] = "unresolved"
            else:
                ambiguate([x["handle"] for x in disc_lines], [u["pid"] for u in elig], where)
            for x, u in zip(disc_lines, sorted(elig, key=lambda u: (u["node"], u["pid"]))):
                emptied.remove(u)
                if x.get("cls") != "unresolved":
                    assign(x, u, cls, g["age"], g["ntx_at"][u["pid"]])
                u["fbs"].append((x["t"], "NACK"))
                g["nacks"] += 1
                close_unit(u, x, "discard")
        if len(ack_lines) != len(emptied):
            v("A2-1", f"{where}: {len(ack_lines)} ACK lines for {len(emptied)} emptied lifecycles")
            for x in ack_lines:
                x["cls"] = "unresolved"
        elif ack_lines:
            ack_assign(g, ack_lines, emptied)
        groups_done.append(g)

    def finalize_all():
        for key in sorted(open_groups, key=lambda key: open_groups[key]["first_gi"]):
            finalize(open_groups[key])
            finalized.add(key)
        open_groups.clear()

    def finalize_touching(unit_key):
        for key in sorted(open_groups, key=lambda key: open_groups[key]["first_gi"]):
            g = open_groups[key]
            if unit_key in g["cands"]:
                finalize(g)
                finalized.add(key)
                del open_groups[key]

    for raw in lines:
        p_ = raw.rstrip("\n").split("|", 2)
        if len(p_) < 3 or not p_[0][:1].isdigit():
            continue
        t = PR.t_ps(p_[0])
        t_end = max(t_end, t)
        mod, msg = p_[1], p_[2]
        if mod == SCHED or (mod == GNB and "LteSchedulerEnb" in msg):
            sched_lines[mod] += 1
            if PR.T_RTXS_START in msg:
                rtx_dir = None
                continue
            m = PR.R_RTXS_DIR.search(msg)
            if m:
                rtx_dir = m.group(2)
                continue
            m = PR.R_RTXACID.search(msg)
            if m and rtx_dir == "DL":
                rtx_ev[t // MS].add((int(m.group(2)), int(m.group(5)), int(m.group(3))))
            if mod == SCHED:
                continue
        if mod != GNB:
            continue
        gi += 1
        if burst_t is not None and t != burst_t:
            finalize_all()
            finalized.clear()
            burst_t = None
        if ML_START in msg:
            ml_open = gi
            continue
        if ML_END in msg:
            if ml_open is not None:
                loops.append(ml_open)
            ml_open = None
            continue
        if PR.T_DROPPED in msg or PR.T_NOTADDR in msg:
            v("A2-0", f"t {t}: out-of-scope text: {msg.strip()[:90]}")
            pv("P0-6", f"t {t}: {msg.strip()[:100]}")
            continue
        if "LteSchedulerEnb" in msg:
            continue
        m = PR.R_SELRTX.search(msg)
        if m:
            sel_ev[(t // MS, int(m.group(1)))] += 1
            continue
        if PR.T_START in msg:
            if block is not None:
                v("A2-1", f"t {t}: feedback event starts while the previous one (t {block['t']}) has no feedback line")
                pv("P0-1", f"t {t}: a block starts while the previous one (t {block['t']}) has no feedback line")
            block = {"t": t, "kind": None, "handle": None, "p": None, "cw": None, "n": 0, "maxrtx": None}
            continue
        if PR.T_UACK in msg:
            if block is None:
                v("A2-1", f"t {t}: unit ACK line outside a feedback event")
            else:
                block.update(kind="ack", n=block["n"] + 1)
            continue
        m = PR.R_URTX.search(msg) or PR.R_UDISC.search(msg)
        if m:
            kind = "rtx" if PR.R_URTX.search(msg) else "discard"
            mx = re.search(r"reached\) : (\d+)", msg)
            if block is None:
                v("A2-1", f"t {t}: unit {kind} line outside a feedback event")
            else:
                block.update(kind=kind, handle=int(m.group(3)), p=int(m.group(1)), cw=int(m.group(2)), n=block["n"] + 1,
                             maxrtx=int(mx.group(1)) if mx else None)
            continue
        m = PR.R_INSERT.search(msg)
        if m:
            counts["insert lines"] += 1
            pid, p, cw, node = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            finalize_touching((node, p, cw))
            key = (node, p, cw)
            if key in units and units[key]["st"] == "PEND":
                classify(key, "emptied", t)
            if key in units:
                v("A2-2", f"t {t}: insert of PDU {pid} into the occupied unit {key} (PDU {units[key]['pid']})")
                pv("P0-2", f"t {t}: insert of PDU {pid} into the occupied unit {key} (PDU {units[key]['pid']})")
                units[key]["end"] = "overwritten"
                del units[key]
            if pid in pdus:
                v("A2-2", f"t {t}: duplicate PDU id {pid}")
            u = {"pid": pid, "node": node, "p": p, "cw": cw, "st": "INS", "t_ins": t, "ins_gi": gi, "last_tx": None, "ntx": 0,
                 "txs": [], "fbs": [], "nack_t": None, "end": None}
            units[key] = u
            pdus[pid] = u
            busy[node].append((gi, t, +1))
            continue
        m = PR.R_EXTRACT.search(msg)
        if m:
            counts["extract lines"] += 1
            pid, p, cw, node = int(m.group(1)), int(m.group(2)), int(m.group(3)), int(m.group(4))
            finalize_touching((node, p, cw))
            key = (node, p, cw)
            u = units.get(key)
            if u is not None and u["st"] == "PEND":
                if u["pid"] == pid:
                    classify(key, "rtx", t)
                    u = units.get(key)
                else:
                    v("A2-2", f"t {t}: extract of PDU {pid} on the key {key} of pending PDU {u['pid']}")
                    pv("P0-2", f"t {t}: extract of PDU {pid} {key} without that PDU in the unit")
                    continue
            if u is None or u["pid"] != pid:
                v("A2-2", f"t {t}: transmission of PDU {pid} {key} that is not in that unit")
                pv("P0-2", f"t {t}: extract of PDU {pid} {key} without that PDU in the unit")
                continue
            if u["st"] == "INS":
                if t // MS != u["t_ins"] // MS:
                    v("A2-2", f"t {t}: first transmission of PDU {pid} not in its insert TTI")
                    pv("P0-2", f"t {t}: first extract of PDU {pid} not in its insert TTI")
            elif u["st"] == "BUF":
                counts["retransmissions"] += 1
                nack_rtx_delay.append(t - u["nack_t"])
                rtx_x[(t // MS, p)] += 1
                rtx_list.append((t, pid, node, p, cw, u["ntx"] + 1))
                if (node, p, cw) not in rtx_ev.get(t // MS, set()):
                    v("A2-4c", f"t {t}: retransmission of PDU {pid} {key} without a DL rtxAcid line naming node {node}, process {p}")
                if sel_ev[(t // MS, p)] < rtx_x[(t // MS, p)]:
                    v("A2-4a", f"t {t}: retransmission of PDU {pid} {key} without a 'selected for retransmission' line of process {p} in its TTI")
                    pv("P0-4a", f"t {t}: retransmission of PDU {pid} without 'selected for retransmission'")
            else:
                v("A2-2", f"t {t}: transmission of PDU {pid} while it awaits feedback")
                pv("P0-2", f"t {t}: extract of PDU {pid} in state {u['st']}")
            u.update(st="WAIT", last_tx=t, ntx=u["ntx"] + 1)
            u["txs"].append(t)
            continue
        m = PR.R_FB.search(msg)
        if m:
            p, cw, res = int(m.group(1)), int(m.group(2)), m.group(3)
            ok = (block is not None and block["t"] == t and block["n"] == 1 and
                  ((res == "ACK" and block["kind"] == "ack") or
                   (res == "NACK" and block["kind"] in ("rtx", "discard") and block["p"] == p and block["cw"] == cw)))
            if not ok:
                v("A2-1", f"t {t}: malformed feedback event for process {p} {res}: {block}")
                pv("P0-1", f"t {t}: feedback line process {p} {res} with block {block}")
            line = {"j": len(fb), "gi": gi, "t": t, "p": p, "cw": cw, "res": res, "cls": None, "owner": None, "pid": None,
                    "handle": (block or {}).get("handle"), "block_kind": (block or {}).get("kind"), "maxrtx": (block or {}).get("maxrtx")}
            fb.append(line)
            block = None
            key = (t, p, cw)
            if key in finalized:
                v("A2-5", f"t {t}: the feedback group of process {p} is split by a main-loop event (not certified)")
            g = open_groups.get(key)
            if g is None:
                cand = [k for k, u in units.items() if k[1] == p and k[2] == cw and u["st"] == "WAIT"]
                if not cand:
                    v("A2-1", f"t {t}: feedback for process {p} with no unit awaiting feedback")
                    pv("P0-3", f"t {t}: feedback process {p} with no awaiting unit")
                    line["cls"] = "unresolved"
                    burst_t = t
                    continue
                amax = max(t - units[k]["last_tx"] for k in cand)
                top = [k for k in cand if t - units[k]["last_tx"] == amax]
                g = open_groups[key] = {"t": t, "p": p, "cw": cw, "cands": top, "age": amax, "lines": [], "first_gi": gi,
                                        "nacks": 0, "acks": 0, "exchangeable": False}
                ages[amax] += 1
            g["lines"].append(line)
            burst_t = t
            continue
    finalize_all()
    d_star = next(iter(ages)) if len(ages) == 1 else None
    if len(ages) > 1:
        v("A2-3", f"several feedback ages from the last transmission: {dict(ages)}")
        pv("P0-3", f"several feedback ages from the last transmission: {dict(ages)}")
    # selections without a retransmission in their TTI and process
    for k_, n in sel_ev.items():
        if n > rtx_x.get(k_, 0):
            v("A2-4a", f"TTI {k_[0]} process {k_[1]}: {n} 'selected for retransmission' line(s), {rtx_x.get(k_, 0)} retransmission(s)")
            pv("P0-4a", f"TTI {k_[0]} process {k_[1]}: selection without retransmission")

    # ---- end of the log: structural censoring (no complete main loop after the event), else UNRESOLVED -------------
    def loop_after(gi_e):
        return any(s > gi_e for s in loops)

    unresolved = []
    cens = Counter()
    for g in list(pending):
        pd = g["pending"]
        last_gi = g["lines"][-1]["gi"]
        structural = bool(loops) and not loop_after(last_gi)
        kind = "censored: awaiting resolution" if structural else "unresolved: pending group at the end"
        for x in pd["lines"]:
            x["cls"] = "censored" if structural else "unresolved-pending"
        for c in pd["cands"]:
            if c in units and units[c].get("pend_g") is g:
                units[c]["end"] = kind
                units[c]["st"] = "PEND-END"
        for u in pd["emptied"]:
            u["end"] = kind
        g["censored_nodes"] = sorted({c[0] for c in pd["cands"]})
        groups_done.append(g)
        if not structural:
            unresolved.append(f"group t {g['t']} process {g['p']}: pending at the end ({'no main-loop markers in the log' if not loops else 'a complete main loop followed it'})")
    for k, u in list(units.items()):
        if u["end"] is not None:
            cens[u["end"]] += 1
            continue
        if u["st"] == "WAIT" and d_star is not None and u["last_tx"] + d_star > t_end:
            u["end"] = "censored: awaiting feedback"
        elif u["st"] == "INS" and u["t_ins"] // MS == t_end // MS:
            u["end"] = "censored: inserted in the last TTI"
        elif u["st"] == "BUF":
            if loops and not loop_after(u["nack_gi"]):
                u["end"] = "censored: awaiting retransmission"
            else:
                u["end"] = "unresolved: retransmission not observed"
                unresolved.append(f"PDU {u['pid']} {k}: NACKed at {u['nack_t']}, no retransmission although "
                                  f"{'no main-loop markers are in the log' if not loops else 'a complete main loop followed'}")
        else:
            u["end"] = f"OPEN at the end in state {u['st']}"
            v("A2-2", f"PDU {u['pid']} {k} open at the end of the log in state {u['st']} (t_end {t_end})")
            pv("P0-2" if u["st"] == "INS" else "P0-3", f"unit {k} PDU {u['pid']} open at the end in state {u['st']}")
        cens[u["end"]] += 1
    return {"fb": fb, "groups": groups_done, "pdus": pdus, "busy": dict(busy), "viol": dict(viol), "pviol": dict(pviol),
            "d_star": d_star, "ages": dict(ages), "t_end": t_end, "counts": dict(counts), "end_states": dict(cens),
            "nack_rtx_delays": nack_rtx_delay, "rtx_list": rtx_list, "sel_ev": dict(sel_ev), "sched_lines": dict(sched_lines),
            "handles": {h: {"st": hs["st"], "lc": sorted(hs["lc"]) if isinstance(hs["lc"], set) else hs["lc"]} for h, hs in handles.items()},
            "loops": len(loops), "unresolved": unresolved, "version": VERSION}


# ------------------------------------------------------------------------------------------- preconditions -------
def preconditions(res):
    """the frozen P0 report format (m2s72_a2probe.preconditions), computed by the shared A-2.1 replay (F1-b)"""
    v = {k: len(x) for k, x in res["pviol"].items()}
    nack = sum(1 for x in res["fb"] if x["res"] == "NACK")
    acks = sum(1 for x in res["fb"] if x["res"] == "ACK")
    nrtx = res["counts"].get("retransmissions", 0)
    groups = [g for g in res["groups"] if len(g["cands"]) >= 2]

    def st(k, exercised=True):
        return "FAILS" if v.get(k) else ("HOLDS" if exercised else "NOT EXERCISED")
    out = {
        "P0-1 feedback event structure": st("P0-1", acks + nack > 0) + ("" if nack else " (ACK blocks only; NACK blocks NOT EXERCISED)"),
        "P0-2 transmissions logged with id and node": st("P0-2", res["counts"].get("extract lines", 0) > 0)
        + ("" if nrtx else " (first transmissions only; retransmissions NOT EXERCISED)"),
        "P0-3 single feedback delay from the last transmission": st("P0-3", bool(res["ages"])),
    }
    if not nrtx and not res["sel_ev"]:
        out["P0-4 node-identified retransmission evidence"] = "NOT EXERCISED"
    else:
        out["P0-4a retransmission selection evidence"] = st("P0-4a", True)
        out["P0-4c scheduler node-identified evidence"] = ("NOT EVALUATED (no scheduler line in the log)" if not res["sched_lines"]
                                                           else ("FAILS" if res["viol"].get("A2-4c") else "HOLDS"))
    cert_bad = len(res["viol"].get("A2-5", []))
    out["P0-5 multi-candidate groups"] = ("HOLDS" if not cert_bad else "FAILS") if groups else "NOT EXERCISED"
    out["P0-6 out-of-scope texts absent"] = "FAILS" if v.get("P0-6") else "HOLDS"
    mixed = any(g["nacks"] for g in groups)
    if groups and not mixed:
        out["P0-5 multi-candidate groups"] += " (all-ACK groups only; groups with a NACK NOT EXERCISED)"
    return out


# --------------------------------------------------------------------------------------------- rows ---------------
def a24b_row(res, lines, node_id):
    """A2-4b: node identity of every retransmission, from the receiving UE's own log (XA's UE-side data; comparison only)"""
    if not res["rtx_list"]:
        return ("A2-4b", "run", NX, "no retransmission in this log")
    import m2s72_harqx as H
    log = H.read_log(None, lines=lines)
    if not log["ue_rx"]:
        return ("A2-4b", "run", NE, "no UE-side H-ARQ RX lines: the receiving UE cannot be confirmed")
    tr = H.truth(log, node_id)
    node2k = tr["node2k"]
    rx = defaultdict(list)                                   # MAC id -> [(t, k, p)] in log order
    last_line = defaultdict(int)                             # k -> time of its last H-ARQ RX line
    for k, evs in log["ue_rx"].items():
        for li, t, pid, p in evs:
            rx[pid].append((t, k, p))
            last_line[k] = max(last_line[k], t)
    for k, evs in log.get("ue_fb", {}).items():
        for e in evs:
            last_line[k] = max(last_line[k], e[1])
    bad, cens, ok = [], 0, 0
    rtx_pids = sorted({x[1] for x in res["rtx_list"]})
    for pid in rtx_pids:
        u = res["pdus"][pid]
        k = node2k.get(u["node"])
        if k is None:
            bad.append(f"PDU {pid}: node {u['node']} has no UE in the UE-side log")
            continue
        others = sorted({kk for t, kk, p in rx[pid] if kk != k})
        if others:
            bad.append(f"PDU {pid} (node {u['node']}) received by UE(s) {others}")
        mine = [(t, p) for t, kk, p in rx[pid] if kk == k]
        if any(p != u["p"] for t, p in mine):
            bad.append(f"PDU {pid}: UE {k} received it on another process")
        txs = u["txs"]
        for i, t_tx in enumerate(txs):
            nxt = txs[i + 1] if i + 1 < len(txs) else None
            got = [t for t, p in mine if t >= t_tx and (nxt is None or t < nxt)]
            if len(got) == 1:
                ok += i > 0
                continue
            if len(got) > 1:
                bad.append(f"PDU {pid} transmission {i + 1} at {t_tx}: {len(got)} receptions at UE {k}")
            elif nxt is None and last_line[k] < t_tx:
                cens += 1 if i > 0 else 0                   # no UE-k line after the last transmission: no opportunity seen
            else:
                bad.append(f"PDU {pid} transmission {i + 1} at {t_tx}: no reception at UE {k} before "
                           f"{'the next transmission' if nxt else 'its next UE-side line'}")
    if bad:
        return ("A2-4b", "run", "FAIL", f"FAIL {len(bad)}: {bad[:3]}")
    if cens:
        return ("A2-4b", "run", NE, f"{ok} retransmissions received by the right UE; {cens} without any later UE-side line (not confirmed)")
    return ("A2-4b", "run", "PASS", f"{ok} retransmissions of {len(rtx_pids)} PDUs received by their node's UE, in transmission order")


def a24c_row(res, sca=None):
    if not res["rtx_list"]:
        return ("A2-4c", "run", NX, "no retransmission in this log")
    if not res["sched_lines"]:
        why = scheduler_log_config(sca)
        return ("A2-4c", "run", NE, "no scheduler line in the log: node-identified scheduler evidence unavailable "
                                    f"(scheduler logging disabled by configuration{': ' + why if why else ''}); never PASS by absence")
    vv = res["viol"].get("A2-4c", [])
    if vv:
        return ("A2-4c", "run", "FAIL", f"FAIL {len(vv)}: {vv[:3]}")
    return ("A2-4c", "run", "PASS", f"{len(res['rtx_list'])} retransmissions, each named by a DL rtxAcid line (node, process)")


def scheduler_log_config(sca):
    """the run's own record of the log-level entries (.sca 'config' header lines), for the A2-4c reason; '' if absent"""
    if not sca or not os.path.exists(sca):
        return ""
    ent = []
    for line in open(sca, errors="replace"):
        if line.startswith("config ") and "cmdenv-log-level" in line:
            ent.append(line.strip()[7:])
        if line.startswith(("scalar ", "statistic ", "vector ")):
            break
    sched = [e for e in ent if "schedulerDl" in e]
    return "; ".join(sched or ent)[:300]


def a26_row(res, grants):
    cons = []
    nfb = len(res["fb"])
    attributed = sum(1 for x in res["fb"] if x["owner"] is not None)
    censored = sum(1 for x in res["fb"] if x["cls"] in ("censored", "unresolved-pending"))
    if attributed + censored != nfb:
        cons.append(f"attributed {attributed} of {nfb} feedback lines" + (f" (+ {censored} censored / pending)" if censored else ""))
    ends = Counter(u["end"] for u in res["pdus"].values())
    n_ins = res["counts"].get("insert lines", 0)
    if len(res["pdus"]) != n_ins:
        cons.append(f"PDUs {len(res['pdus'])} vs insert lines {n_ins}")
    closed = ends.get("ack", 0) + ends.get("discard", 0) + sum(v for k, v in ends.items() if k and (k.startswith("censored") or k.startswith("unresolved")))
    if closed != n_ins:
        cons.append(f"ACKed + discarded + censored = {closed} vs inserts {n_ins}")
    ntx = sum(u["ntx"] for u in res["pdus"].values())
    if ntx != res["counts"].get("extract lines", 0):
        cons.append(f"transmissions {ntx} vs extract lines {res['counts'].get('extract lines', 0)}")
    nfb_units = sum(len(u["fbs"]) for u in res["pdus"].values())
    if nfb_units != attributed:
        cons.append(f"unit feedbacks {nfb_units} vs attributed lines {attributed}")
    gb, gdet = A2.grants_rows(res, grants)
    if gb:
        cons += gb
    return ("A2-6", "run", "FAIL" if cons else ("PASS" if gb is not None else NE),
            (f"FAIL {cons[:4]}" if cons else f"lines {nfb} = attributed{f' + {censored} censored' if censored else ''}; inserts {n_ins} = ACKed {ends.get('ack', 0)} + discarded "
             f"{ends.get('discard', 0)} + censored {closed - ends.get('ack', 0) - ends.get('discard', 0)}; transmissions {ntx}; ") + f"grants: {gdet}")


def touched_nodes(res):
    """nodes whose per-UE counts are inexact: candidates of censored / unresolved pending groups"""
    out = set()
    for g in res["groups"]:
        out |= set(g.get("censored_nodes", []))
    return out


def xa_rows(res, lines, node_id, nproc, window, a2_per):
    """A2-7 as frozen, with the A-2.1 line classes; UEs touched by censored / pending groups NOT EVALUATED"""
    import m2s72_harqx as H
    log = H.read_log(None, lines=lines)
    log["t_last"] = res["t_end"]
    if not log["ue_rx"] and not log["ue_fb"]:
        return ("A2-7", "run", NE, "no UE-side H-ARQ RX lines in this log: the independent reference is unavailable"), None
    tr = H.truth(log, node_id)
    delta, xl, cens, probs = H.match_feedback(log, tr, None)
    ref_bad = tr["xa0"] + tr["xa1"][:3] + probs[:3] + tr["chain_bad"][:3] + ([f"codeword != 0: {tr['cw_other']}"] if tr["cw_other"] else [])
    if delta is None or ref_bad:
        return ("A2-7", "run", "FAIL", f"the reference itself is not valid (XA-0/1/2 problems {ref_bad[:3]}): A-2 cannot be confirmed"), None
    if len(xl) != len(res["fb"]):
        return ("A2-7", "run", "FAIL", f"{len(res['fb'])} A-2 feedback lines vs {len(xl)} in the reference"), None
    skip = touched_nodes(res)
    c, bad = Counter(), []
    for g in res["groups"]:
        idx = [x["j"] for x in g["lines"]]
        if any(x["cls"] in ("censored", "unresolved-pending") for x in g["lines"]):
            continue
        own_a = sorted(x["owner"] for x in g["lines"] if x["owner"] is not None)
        own_x = sorted(xl[j][2]["node"] for j in idx if xl[j][2] is not None)
        ref_amb = False
        for x, j in zip(g["lines"], idx):
            if x["cls"] in UNIQUE:
                if xl[j][3] == {x["owner"]}:
                    c[x["cls"]] += 1
                elif x["owner"] in xl[j][3]:
                    # the UE side cannot separate this line (two UEs answered the same process at the same time with the
                    # same result); A-2.1's unique resolution (handle / retransmission evidence) is then only CONSISTENT
                    # with the reference: it is checked as a group multiset below, never counted as confirmed
                    ref_amb = True
                    c[f"{x['cls']} (reference ambiguous: group multiset only)"] += 1
                else:
                    bad.append(f"line {j} ({x['cls']}): A-2 node {x['owner']}, reference {sorted(xl[j][3])}")
        if ref_amb and not (g["exchangeable"] or g.get("multi_nack")):
            if own_a != own_x:
                bad.append(f"group t {g['t']} process {g['p']}: A-2 nodes {own_a}, reference {own_x}")
        if g["exchangeable"] or g.get("multi_nack"):
            if own_a != own_x:
                bad.append(f"group t {g['t']} process {g['p']}: A-2 nodes {own_a}, reference {own_x}")
            else:
                c["exchangeable lines"] += len([x for x in g["lines"] if x["cls"] in ("exchangeable", "exchangeable-nack")])
    xs = defaultdict(lambda: {"feedback": 0, "nack": 0, "lat": Counter()})
    for x in tr["tf"]:
        if "t_g" in x and x["pid"] in tr["ins"]:
            d = xs[x["node"]]
            d["feedback"] += 1
            d["nack"] += x["res"] == "NACK"
            d["lat"][x["t_g"] - tr["ins"][x["pid"]]["t"]] += 1
    as_ = defaultdict(lambda: {"feedback": 0, "nack": 0, "lat": Counter()})
    for x in res["fb"]:
        if x["owner"] is not None:
            d = as_[x["owner"]]
            d["feedback"] += 1
            d["nack"] += x["res"] == "NACK"
            d["lat"][x["t"] - x["t_ins"]] += 1
    for n in sorted(set(xs) | set(as_)):
        if n in skip:
            continue
        if dict(xs[n]) != dict(as_[n]):
            bad.append(f"node {n}: per-UE feedback / NACK / latency differ (A-2 {as_[n]['feedback']} / {as_[n]['nack']}, reference "
                       f"{xs[n]['feedback']} / {xs[n]['nack']})")
    j_of = {i: j for j, (i, own, x, grp) in enumerate(xl)}
    ev = defaultdict(list)
    for g_ in tr["ins"].values():
        ev[g_["node"]].append((g_["idx"], g_["t"], +1))
    for x in tr["tf"]:
        if x.get("final") and "fb_idx" in x:
            j = j_of.get(x["fb_idx"])
            if x["res"] == "ACK" or (j is not None and res["fb"][j]["block_kind"] == "discard"):
                ev[x["node"]].append((x["fb_idx"], x["t_g"], -1))
    occ_x = {}
    for n, e in ev.items():
        try:
            occ_x[n] = P.occupancy_log_order(sorted(e), nproc, (window[0] // MS, window[1] // MS))
        except ValueError as ex:
            occ_x[n] = {"error": str(ex)}
    occ_eq = {n: (occ_x.get(n) == a2_per[n]["occupancy"]) for n in a2_per if n not in skip}
    if not all(occ_eq.values()):
        bad.append(f"per-UE occupancy differs from the reference: {occ_eq}")
    status = "FAIL" if bad else (NE if skip else "PASS")
    return ("A2-7", "run", status,
            f"reference XA (UE-side ownership, delta {delta} ps): lines confirmed {dict(c)}; per-UE feedback / NACK / latency equal "
            f"for {len([n for n in as_ if n not in skip])} UEs; per-UE occupancy equal {occ_eq}"
            + (f"; NOT EVALUATED for nodes {sorted(skip)} (censored / pending groups)" if skip else "")
            + (f"; FAIL {len(bad)}: {bad[:3]}" if bad else "")), {"confirmed": dict(c), "occupancy_equal": occ_eq, "skipped": sorted(skip)}


def scalar_row(res, sca):
    """A2-8 as frozen; UEs touched by censored / pending groups are NOT EVALUATED (their counts are inexact)"""
    sc = PR.scalars(sca)
    nodes = A2.sca_nodes(sca)
    if not sc or not nodes:
        return ("A2-8", "run", NE, f"no Simu5G per-UE H-ARQ scalars or no macNodeId records in {sca}"), None
    skip = touched_nodes(res)
    per = defaultdict(lambda: {"feedback": 0, "nack": 0, "ntx": []})
    for x in res["fb"]:
        if x["owner"] is not None:
            per[x["owner"]]["feedback"] += 1
            per[x["owner"]]["nack"] += x["res"] == "NACK"
    for u in res["pdus"].values():
        if u["end"] == "ack":
            per[u["node"]]["ntx"].append(u["ntx"])
    bad, done, ne = [], [], []
    for mod, n in sorted(nodes.items()):
        if n in skip:
            ne.append(f"{mod} (node {n}): censored / pending feedback (counts inexact)")
            continue
        s = sc.get(mod, {})
        d = per.get(n)
        if d is None or d["feedback"] == 0:
            ne.append(f"{mod} (node {n}): no feedback attributed")
            continue
        for name, val in (("harqErrorRateDl:mean", d["nack"] / d["feedback"]),
                          ("harqTxAttemptsDl:mean", (sum(d["ntx"]) / len(d["ntx"])) if d["ntx"] else None)):
            if name not in s or val is None:
                ne.append(f"{mod} {name} absent")
                continue
            try:
                rec = float(s[name])
            except ValueError:
                ne.append(f"{mod} {name} = {s[name]}")
                continue
            ok = abs(rec - val) <= REL_TOL * max(1.0, abs(val))
            (done if ok else bad).append(f"node {n} {name}: Simu5G {s[name]}, A-2 {val:.12g}")
    if bad:
        return ("A2-8", "run", "FAIL", f"FAIL {bad}; equal {done}"), None
    if skip & set(nodes.values()):
        return ("A2-8", "run", NE, f"not comparable: {ne}; equal {done}"), None
    if not done:
        return ("A2-8", "run", NE, f"nothing comparable: {ne}"), None
    return ("A2-8", "run", "PASS", f"equal {done}" + (f"; not comparable {ne}" if ne else "")), done


def rows_for(res, lines, nproc, window, node_id=None, grants=None, sca=None, simu5g_root=None):
    rows = []
    pre = preconditions(res)
    fails = {k: v for k, v in pre.items() if v.startswith("FAILS")}
    rows.append(("A2-0", "run", "FAIL" if fails or res["viol"].get("A2-0") else "PASS",
                 "; ".join(f"{k.split(' ')[0]} {v}" for k, v in pre.items()) + (f"; {res['viol'].get('A2-0', [])[:2]}" if res["viol"].get("A2-0") else "")))
    rows.append(A2.source_row(simu5g_root))
    cls = Counter(x["cls"] for x in res["fb"])

    def vr(row, okdetail, exercised=True):
        vv = res["viol"].get(row, [])
        if vv:
            return (row, "run", "FAIL", f"FAIL {len(vv)}: {vv[:3]}")
        return (row, "run", "PASS" if exercised else NX, okdetail)
    rows.append(vr("A2-1", f"feedback lines {len(res['fb'])}: {dict(cls)}"))
    rows.append(vr("A2-2", f"PDUs {len(res['pdus'])}; transmissions {res['counts'].get('extract lines', 0)}; end states "
                           f"{dict(Counter(u['end'] for u in res['pdus'].values()))}"))
    rows.append(vr("A2-3", f"d*_tx {res['d_star']} ps for every attributed line ({res['ages']})"))
    nrtx = res["counts"].get("retransmissions", 0)
    rows.append(vr("A2-4a", f"{nrtx} retransmissions, each with 'selected for retransmission' of its process in its TTI; "
                            f"selections {sum(res['sel_ev'].values())}", exercised=nrtx > 0 or bool(res["sel_ev"])))
    rows.append(a24b_row(res, lines, node_id))
    rows.append(a24c_row(res, sca))
    ex = [g for g in res["groups"] if g["exchangeable"]]
    rows.append(vr("A2-5", f"{len(ex)} exchangeable groups certified (sizes {dict(Counter(len(g['cands']) for g in ex))})", exercised=bool(ex)))
    rows.append(a26_row(res, grants))
    per = A2.per_ue(res, nproc, window)
    r7, x7 = xa_rows(res, lines, node_id, nproc, window, per)
    rows.append(r7)
    r8, x8 = scalar_row(res, sca)
    rows.append(r8)
    if res["unresolved"]:
        rows.append(("A2-9", "run", NE, f"{len(res['unresolved'])} unresolved (no contradiction, not censorable): {res['unresolved'][:3]}"))
    else:
        rows.append(("A2-9", "run", "PASS", f"every feedback line and lifecycle resolved or structurally censored "
                                            f"(end states {res['end_states']}; complete main loops {res['loops']})"))
    return rows, per, coverage(res, rows), {"preconditions": pre, "xa": x7, "scalars": x8}


SYNTH = {
    "NACK resolved: single candidate": "synthetic fixtures (gen21: T-sweep21, T-recon)",
    "NACK resolved: bound handle": "synthetic fixtures (gen21: T-recon, T-sweep21)",
    "NACK resolved by retransmission evidence (deferred)": "synthetic fixtures (gen21: T-recon, T-sweep21)",
    "multi-NACK groups (handle relations kept ambiguous)": "synthetic fixtures only (T-multinack)",
    "retransmissions": "synthetic fixtures (gen21)",
    "discard after maxHarqRtx + 1 transmissions": "synthetic fixtures only (T-sweep21, T-multinack)",
    "mixed ACK / NACK groups": "synthetic fixtures (gen21)",
    "exchangeable groups of 3 or more": "synthetic fixtures only (T-sweep21 N 3)",
    "exchangeable ACK groups (2 candidates)": "synthetic fixtures (gen21)",
    "end-of-run censoring: awaiting feedback": "synthetic fixtures (T-end)",
    "end-of-run censoring: inserted in the last TTI": "synthetic fixtures (T-end)",
    "end-of-run censoring: awaiting retransmission (structural)": "synthetic fixtures only (T-end)",
    "end-of-run censoring: awaiting resolution (structural)": "synthetic fixtures only (T-end)",
    "per-UE occupancy confirmed by the independent reference": "not confirmed on this run (A2-7 not PASS)",
}


def coverage(res, rows):
    st = {r[0]: r[2] for r in rows}
    ex = [g for g in res["groups"] if g["exchangeable"]]
    ends = Counter(u["end"] for u in res["pdus"].values())
    cls = Counter(x["cls"] for x in res["fb"] if x["res"] == "NACK")
    items = [
        ("single-candidate ACK attribution", sum(1 for x in res["fb"] if x["cls"] == "single" and x["res"] == "ACK")),
        ("exchangeable ACK groups (2 candidates)", sum(1 for g in ex if len(g["cands"]) == 2)),
        ("exchangeable groups of 3 or more", sum(1 for g in ex if len(g["cands"]) >= 3)),
        ("NACK resolved: single candidate", cls.get("single", 0)),
        ("NACK resolved: bound handle", cls.get("bound", 0)),
        ("NACK resolved by retransmission evidence (deferred)", cls.get("resolved-by-rtx", 0)),
        ("multi-NACK groups (handle relations kept ambiguous)", res["counts"].get("multi-NACK groups", 0)),
        ("retransmissions", res["counts"].get("retransmissions", 0)),
        ("discard after maxHarqRtx + 1 transmissions", ends.get("discard", 0)),
        ("mixed ACK / NACK groups", sum(1 for g in res["groups"] if g["nacks"] and g["acks"])),
        ("end-of-run censoring: awaiting feedback", ends.get("censored: awaiting feedback", 0)),
        ("end-of-run censoring: inserted in the last TTI", ends.get("censored: inserted in the last TTI", 0)),
        ("end-of-run censoring: awaiting retransmission (structural)", ends.get("censored: awaiting retransmission", 0)),
        ("end-of-run censoring: awaiting resolution (structural)", ends.get("censored: awaiting resolution", 0)),
        ("per-UE occupancy confirmed by the independent reference", len({u["node"] for u in res["pdus"].values()}) if st.get("A2-7") == "PASS" else 0),
        ("independent UE-side reference (A2-7)", 1 if st.get("A2-7") == "PASS" else 0),
        ("retransmission node identity from the UE side (A2-4b)", 1 if st.get("A2-4b") == "PASS" else 0),
        ("Simu5G per-UE statistics (A2-8)", 1 if st.get("A2-8") == "PASS" else 0),
    ]
    out = []
    for name, n in items:
        out.append((name, n, "EXERCISED by this input" if n else "NOT EXERCISED by this input -> " + SYNTH.get(name, "not evaluated")))
    return out


def verdict(rows, contract="full"):
    st = {r[0]: r[2] for r in rows}
    if any(s == "FAIL" for s in st.values()):
        return f"{VERSION} NOT VALID", 1
    if any(st.get(r) not in ("PASS", NX) for r in REQUIRED[contract]):
        return f"{VERSION} INCOMPLETE", 4
    return f"{VERSION} VALID", 0


def evaluate(lines, nproc, t0, node_id=None, grants=None, sca=None, root=None):
    res = replay(lines)
    window = (t0, (res["t_end"] // MS + 1) * MS)
    rows, per, cov, extra = rows_for(res, lines, nproc, window, node_id=node_id, grants=grants, sca=sca, simu5g_root=root)
    return res, rows, per, cov, extra, window
