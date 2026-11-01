#!/usr/bin/env python3
"""M2-S7.2a gate F0, Checkpoint 1 revision 2 (migration/m2-s7.2a-design.md rev. 2.1, amendments A-1 .. A-6).

    check_m2s72_f0r2.py <results dir> [config regex]   -> prints the repaired F0 record (m2s72.sh f0 writes f0-check.txt)

The Checkpoint 1 checker (check_m2s72_f0.py) is not edited: F0-1, F0-2, F0-3, F0-5, F0-7 and F0-9 are its functions,
called unchanged. This module replaces F0-4, F0-6 and F0-8 by their rev. 2.1 forms and adds the F0-6 negative
controls. Runs: M2S72-F0-<opt>-n<N> (+ -ev, -norec), opt q0 / qdu, N = 1, 2, 4, 8 (every one with M2S72-SL), and
the controls M2S72-F0N-<c> (+ -ev).

F0-4 (rev. 2.1 A-5)  M_j = 0 for every session j (as Checkpoint 1), and exact forwarding conservation per (source,
      VID): every uplink unicast to the listener entering N3 on talker[k]'s tunnel leaves the bridge once on dnEth
      (k-th in, k-th out, delay in [0, 1 ms]) and on no tunnel; every downlink unicast to talker[k] entering on
      dnEth leaves once on talker[k]'s tunnel and on no other tunnel. Only frames entering in the last 1 ms of the
      run may be unpaired (in flight); a unicast to any other station fails.
F0-6 (rev. 2.1 A-2)  every unicast key (MAC, VID) through the UPF bridge is classified
        STATIC-VALID     configured (forwardingTable) and S1-S5 hold:
                         S1 the run's recorded par forwardingTable is exactly [(listener MAC, 42, dnEth)], with the
                            listener MAC observed in its transmitted frames and equal to the design value;
                         S2 eventlog twin (INET MacForwardingTable log): no "Adding entry" for the key, and its first
                            line is "Updating entry" on I_dn, the interface id of every entry learned from a frame
                            whose cause chain starts at upf.dnEth (exactly one value): the entry existed from
                            initialisation (entries are created only there or by "Adding entry");
                         S3 agingTime - 1 s > T_end (parameter entries are inserted at -1 s, INET 4.7.0);
                         S4 the uplink conservation of F0-4 for this key holds, with no copy on any tunnel;
                         S5 no frame with the key's source MAC and VID entered on a session tunnel
        DYNAMIC-VALID    not configured; lambda + d < tau + d strictly, learned on the destination's own port
        MISORDERED       not configured, lambda >= tau
        WRONG-PORT       learned or configured on another port (dynamic: lambda on another port; static: S2 shows
                         another interface, S4 forwarding onto a tunnel, or S5 frames from a session)
        MISSING          no learning frame and not configured; or configured without the S1/S2 evidence; or
                         configured but ignored by the table (S3)
        MISSING-TRAFFIC  a mandatory key with no unicast
        NOT EVALUATED    d (F0-7) or the eventlog twin unavailable
      PASS iff the listener (VID 42) is STATIC-VALID, every talker[k] (VID 42) is DYNAMIC-VALID, no other station
      receives unicast, and no configured entry other than (listener, 42, dnEth) exists.
F0-8 (rev. 2.1 A-4)  agingTime - 1 s > T_end, and no frame with the listener's source MAC and VID 42 entered on a
      session tunnel (such a frame would move the unprotected entry).
Negative controls (each must fail exactly its predicted rows, design rule; F0-9 not applicable, no -norec twin):
  M2S72-F0N-missing  no configured entry                          -> F0-4, F0-6
  M2S72-F0N-vlan     entry on VLAN 43                              -> F0-4, F0-6
  M2S72-F0N-age      agingTime 1 s                                 -> F0-4, F0-6, F0-8
  M2S72-F0N-port     talker[1] has the listener's MAC and sends its uplink flows to talker[0] (frames with the
                     listener's source MAC and VID 42 enter on session 1) -> F0-4, F0-6, F0-8
  mutation iface-par census q0-n2 with the recorded entry's interface changed in a copy of its .sca -> F0-6
  mutation iface-log census q0-n2 with the listener's VID-42 table-log interface id changed in a copy of its
                     eventlog twin                                 -> F0-6
"""
import os
import re
import shutil
import sys
import tempfile
from collections import Counter, defaultdict

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_m2s72_f0 as F1  # noqa: E402  (Checkpoint 1 rows, unchanged)
import m2s72_runs as R  # noqa: E402

LISTENER_MAC = "0aab00000001"
VID = 42
IFACE = "dnEth"
TABLE = f"{R.NET}.upf.ethBridge.macTable"
PAIR_MAX = 10 ** 9            # 1 ms
ANSI = re.compile(r"\x1b\[[0-9;]*m")
LOGRE = re.compile(r"(Adding entry|Updating entry|Ignoring manually configured entry), address = ([0-9A-F-]+), "
                   r"interfaceId = (\d+), vid = (\d+)")
rows = F1.rows
CONTROLS = {"missing": {"F0-4", "F0-6"}, "vlan": {"F0-4", "F0-6"}, "age": {"F0-4", "F0-6", "F0-8"},
            "port": {"F0-4", "F0-6", "F0-8"}}
MUTATIONS = {"iface-par": {"F0-6"}, "iface-log": {"F0-6"}}


def add(row, run, ok, detail):
    rows.append((row, run, "PASS" if ok else "FAIL", detail))


def mac_txt(m):
    return "-".join(m[i:i + 2] for i in range(0, 12, 2)).upper()


def macs(run):
    """talker[k] and listener MACs from their transmitted frames; duplicates allowed here (reported by F0-6)."""
    tk = {k: run.mac_of(run.ue_view(k).sl) for k in range(run.n)}
    return tk, run.mac_of(run.gm)


def static_entries(run):
    """S1 evidence: the recorded par forwardingTable of the UPF MAC table: [(mac, vid, interface)]."""
    v = run.par.get((TABLE, "forwardingTable"))
    if v is None:
        return None
    v = v.replace('\\"', '"')
    out = []
    for body in re.findall(r"\{([^{}]*)\}", v):
        kv = dict((a.strip(), b.strip().strip('"')) for a, b in (x.split(":", 1) for x in body.split(",")))
        out.append((kv.get("address", "").replace("-", "").lower(), int(kv.get("vlan", 0)), kv.get("interface")))
    return out


def table_log(elog):
    """INET MacForwardingTable log lines of the UPF table in the eventlog twin: [(t, kind, mac, ifId, vid, origin)],
    origin = 'dn' / 'n3' / None by the cause-event chain to upf.dnEth / upf.ppp[0]."""
    name, parent = {}, {}
    ev = {}
    lines = []
    cur, stack = None, []
    with open(elog, errors="replace") as fh:
        for line in fh:
            if line.startswith("E #"):
                p = line.split()
                cur = {"n": int(p[2]), "t": R.pcapng.simtime_ps(p[4]), "m": int(p[6]), "ce": int(p[8])}
                ev[cur["n"]] = cur
                stack = []
            elif line.startswith("MC "):
                p = line.split()
                d = dict(zip(p[1::2], p[2::2]))
                name[int(d["id"])] = d["n"]
                parent[int(d["id"])] = int(d["pid"]) if "pid" in d else None
            elif line.startswith("CMB"):
                p = line.split()
                d = dict(zip(p[1::2], p[2::2]))
                stack.append(int(d["tm"]))
            elif line.startswith("CME"):
                if stack:
                    stack.pop()
            elif line.startswith("- ") and cur is not None:
                lines.append((cur, stack[-1] if stack else cur["m"], ANSI.sub("", line[2:]).strip()))

    def path(i):
        s = []
        while i is not None:
            s.append(name[i])
            i = parent.get(i)
        return ".".join(reversed(s))
    paths = {i: path(i) for i in name}
    tid = [i for i, p in paths.items() if p == TABLE]
    if len(tid) != 1:
        raise ValueError(f"{elog}: {TABLE} found {len(tid)} times")
    dn = {i for i, p in paths.items() if p.startswith(f"{R.NET}.upf.dnEth")}
    n3 = {i for i, p in paths.items() if p.startswith(f"{R.NET}.upf.ppp[0]")}

    def origin(e):
        k = 0
        while e is not None and k < 10000:
            if e["m"] in dn:
                return "dn"
            if e["m"] in n3:
                return "n3"
            e = ev.get(e["ce"])
            k += 1
        return None
    out = []
    for e, m, txt in lines:
        if m != tid[0]:
            continue
        g = LOGRE.search(txt)
        if not g:
            continue
        out.append((e["t"], g.group(1).split()[0], g.group(2).replace("-", "").lower(), int(g.group(3)), int(g.group(4)), origin(e)))
    return out


def pair(ins, outs, T):
    """Order-preserving pairing of ingress and egress record times of one flow: (paired, unpaired-in-flight,
    problems)."""
    probs, i = [], 0
    for j, t in enumerate(ins):
        if i < len(outs):
            dlt = outs[i] - t
            if 0 <= dlt <= PAIR_MAX:
                i += 1
                continue
            probs.append(f"in #{j} at {R.fmt_t(t)}: egress #{i} at {R.fmt_t(outs[i])}")
            return i, 0, probs
        if t < T - PAIR_MAX:
            probs.append(f"in #{j} at {R.fmt_t(t)} never left the bridge")
            return i, 0, probs
    if i < len(outs):
        probs.append(f"{len(outs) - i} egress frames without ingress")
    return i, len(ins) - i, probs


def f04(run, name, n3, dn, tk, lst, teid, T):
    rev = {t: k for k, t in teid.items()}
    M, mis_dst = Counter(), Counter()
    probs, table = [], []
    for r in n3:
        if r["dir"] == 2 and r["teid"] is not None and r["teid"] in rev and R.is_unicast(r["dst"]):
            k = rev[r["teid"]]
            if r["dst"] != tk[k]:
                M[k] += 1
                mis_dst[r["dst"]] += 1
    stations = set(tk.values()) | {lst}
    others = Counter(r["dst"] for r in n3 + dn if r["dst"] is not None and R.is_unicast(r["dst"]) and r["dst"] not in stations)
    if others:
        probs.append(f"unicast to unknown stations {dict(others)}")
    # uplink: talker[k] -> listener, per VID
    ul_ok = True
    for k, m in sorted(tk.items()):
        vids = sorted({r["vid"] for r in n3 if r["dir"] == 1 and r["src"] == m and r["dst"] == lst})
        for v in vids:
            ins = [r["t"] for r in n3 if r["dir"] == 1 and r["src"] == m and r["dst"] == lst and r["vid"] == v and r["teid"] == teid.get(k)]
            outs = [r["t"] for r in dn if r["dir"] == 2 and r["src"] == m and r["dst"] == lst and r["vid"] == v]
            tun = [r for r in n3 if r["dir"] == 2 and r["src"] == m and r["dst"] == lst and r["vid"] == v]
            p, fl, pr = pair(ins, outs, T)
            if pr or tun:
                ul_ok = False
                probs.append(f"UL talker[{k}]->listener VID {v}: {pr[:1]} copies on tunnels {len(tun)}")
            table.append(f"UL t{k}/{v}: {len(ins)} in, {p} out on dnEth, {fl} in flight, {len(tun)} on tunnels")
    # downlink: listener -> talker[k], per VID
    for k, m in sorted(tk.items()):
        vids = sorted({r["vid"] for r in dn if r["dir"] == 1 and r["dst"] == m})
        for v in vids:
            ins = [r["t"] for r in dn if r["dir"] == 1 and r["dst"] == m and r["vid"] == v]
            outs = [r["t"] for r in n3 if r["dir"] == 2 and r["dst"] == m and r["vid"] == v and r["teid"] == teid.get(k)]
            wrong = [r for r in n3 if r["dir"] == 2 and r["dst"] == m and r["vid"] == v and r["teid"] != teid.get(k)]
            p, fl, pr = pair(ins, outs, T)
            if pr or wrong:
                probs.append(f"DL listener->talker[{k}] VID {v}: {pr[:1]} copies on other tunnels {len(wrong)}")
            table.append(f"DL t{k}/{v}: {len(ins)} in, {p} out on own tunnel, {fl} in flight, {len(wrong)} on other tunnels")
    ok = not M and not probs
    add("F0-4", name, ok, f"misdirected M_j {[M.get(k, 0) for k in range(run.n)]} (destinations "
        f"{ {mac_txt(d): c for d, c in mis_dst.items()} }); conservation per (source, VID): " + "; ".join(table)
        + ("; PROBLEMS: " + "; ".join(probs[:6]) if probs else ""))
    return ul_ok


def f06(run, name, keys, tk, lst, teid, d, tlog, n3, T, ul_ok):
    out, bad = [], 0
    ent = static_entries(run)
    age = run.par.get((TABLE, "agingTime"))
    am = re.fullmatch(r"(\d+(?:\.\d+)?)s", age or "")
    s3 = bool(am) and round(float(am.group(1)) * 10 ** 12) - 10 ** 12 > T
    dup = len(set(tk.values()) | {lst}) != run.n + 1
    if dup:
        out.append(f"station MACs not unique (talkers {tk}, listener {lst})")
        bad += 1
    if lst != LISTENER_MAC:
        out.append(f"listener MAC {mac_txt(lst)} is not the design value {mac_txt(LISTENER_MAC)}")
        bad += 1
    if ent is None:
        out.append("no recorded forwardingTable parameter")
        bad += 1
        ent = []
    extra = [e for e in ent if e != (lst, VID, IFACE)]
    if extra:
        out.append(f"configured entries other than (listener, {VID}, {IFACE}): {[(mac_txt(m), v, i) for m, v, i in extra]}")
        bad += 1
    configured = {(m, v) for m, v, i in ent}
    i_dn = sorted({ifid for t, kind, m, ifid, v, o in tlog if o == "dn"}) if tlog is not None else None
    n3_src_lst = sum(1 for r in n3 if r["dir"] == 1 and r["src"] == lst and r["vid"] == VID)
    rev = {t: k for k, t in teid.items()}
    for (mac, vid) in [(m, VID) for m in tk.values()] + [(lst, VID)]:
        if (mac, vid) not in keys:
            out.append(f"{F1.who(mac, tk, lst)} VID {vid}: MISSING-TRAFFIC")
            bad += 1
    for (mac, vid), v in sorted(keys.items(), key=lambda kv: kv[1]["tau"]):
        nm = "listener" if mac == lst else F1.who(mac, tk, lst)
        if nm.startswith("unknown"):
            out.append(f"{nm} VID {vid}: unicast to an unknown station")
            bad += 1
            continue
        if (mac, vid) in configured:
            ev = [] if tlog is None else [x for x in tlog if x[2] == mac and x[4] == vid]
            adding = [x for x in ev if x[1] == "Adding"]
            s1 = (mac, vid, IFACE) in ent and mac == LISTENER_MAC
            s2 = tlog is not None and i_dn is not None and len(i_dn) == 1 and bool(ev) and not adding and ev[0][1] == "Updating" and ev[0][3] == i_dn[0]
            s2_port = bool(ev) and i_dn is not None and len(i_dn) == 1 and any(x[3] != i_dn[0] for x in ev)
            s4 = ul_ok
            s5 = n3_src_lst == 0
            if tlog is None:
                cls = "NOT EVALUATED"
            elif s1 and s2 and s3 and s4 and s5:
                cls = "STATIC-VALID"
            elif s2_port or not s4 or not s5:
                cls = "WRONG-PORT"
            else:
                cls = "MISSING"
            first = "none" if not ev else f"{ev[0][1]} entry on interface {ev[0][3]} at {R.fmt_t(ev[0][0])}"
            detail = (f"S1 {'ok' if s1 else 'FAIL'} (recorded {[(mac_txt(m), vv, i) for m, vv, i in ent]}); S2 {'ok' if s2 else 'FAIL'} "
                      f"(I_dn {i_dn}, first table line {first}, 'Adding entry' lines {len(adding)}); S3 {'ok' if s3 else 'FAIL'} "
                      f"(agingTime {age}, T_end {R.fmt_t(T)}); S4 {'ok' if s4 else 'FAIL'}; S5 {'ok' if s5 else 'FAIL'} "
                      f"({n3_src_lst} frames from the listener MAC, VID {VID}, on session tunnels)")
            need = "STATIC-VALID" if nm == "listener" else "DYNAMIC-VALID"
            if cls != need:
                bad += 1
            out.append(f"{nm} VID {vid}: {cls} (configured; required {need}): {detail}")
            continue
        side_tau = "UL" if v["tau_side"] == "n3" else "DL"
        side_lam = "UL" if v["lam_side"] == "n3" else "DL"
        if d is None or d.get(side_tau) is None or d.get(side_lam) is None:
            cls, det = "NOT EVALUATED", "d not established by F0-7"
        elif v["lam"] is None:
            cls, det = "MISSING", "no learning frame"
        else:
            lam, tau = v["lam"] + d[side_lam], v["tau"] + d[side_tau]
            port_ok = (v["lam_port"] == "dnEth") if nm == "listener" else (nm.startswith("talker[") and v["lam_port"] == int(nm[7:-1]))
            cls = "DYNAMIC-VALID" if lam < tau and port_ok else ("WRONG-PORT" if lam < tau else "MISORDERED")
            det = (f"lambda {R.fmt_t(lam)} ({'N3 tunnel of ' + str(v['lam_port']) if v['lam_side'] == 'n3' else 'dnEth'}), "
                   f"tau {R.fmt_t(tau)}, margin {R.fmt_t(tau - lam)}")
        need = "STATIC-VALID" if nm == "listener" else "DYNAMIC-VALID"
        if cls != need:
            bad += 1
        out.append(f"{nm} VID {vid}: {cls} (required {need}): {det}")
    add("F0-6", name, bad == 0, f"{len(keys)} unicast keys, {bad} problems: " + "; ".join(out))


def f08(run, name, n3, lst, T):
    age = run.par.get((TABLE, "agingTime"))
    am = re.fullmatch(r"(\d+(?:\.\d+)?)s", age or "")
    ok_age = bool(am) and round(float(am.group(1)) * 10 ** 12) - 10 ** 12 > T
    mv = Counter(r["teid"] for r in n3 if r["dir"] == 1 and r["src"] == lst and r["vid"] == VID)
    add("F0-8", name, ok_age and not mv, f"agingTime {age}: agingTime - 1 s > T_end ({R.fmt_t(T)}) {'holds' if ok_age else 'VIOLATED'}; "
        f"frames with the listener's source MAC and VID {VID} entering on session tunnels: {dict(mv) if mv else 0}")


def evaluate(runs, name, opt, ev_name, norec_name=None, ev_root=None):
    """All rows for one run; returns the set of failing row ids."""
    start = len(rows)
    run = R.Run72(runs, name)
    ev = R.Run72(ev_root or runs, ev_name)
    T = F1.t_end(run)
    teids = F1.f01(run, opt, name)
    F1.f02(run, name)
    F1.f03(run, name)
    n3 = R.n3_records(run.learn_n3)
    dn = R.dn_records(run.learn_dn)
    tk, lst = macs(run)
    F1.run_listener[0] = lst
    teid, probs = F1.sessions(run, n3, tk)
    if probs:
        add("F0-4", name, False, "sessions: " + "; ".join(probs))
        ul_ok = False
    else:
        F1.info("sessions", name, f"tunnel per UE {teid}; MACs talker {tk}, listener {lst}; NR MAC node ids {run.node_id}")
        ul_ok = f04(run, name, n3, dn, tk, lst, teid, T)
    F1.f05(run, opt, name, teids, teid)
    keys = F1.learning(run, n3, dn, tk, lst, teid)
    d, meas = F1.f07(run, ev, name, n3, dn, keys)
    tlog = table_log(ev.elog_path) if os.path.exists(ev.elog_path) else None
    f06(run, name, keys, tk, lst, teid, d, tlog, n3, T, ul_ok)
    f08(run, name, n3, lst, T)
    if norec_name:
        F1.f09(run, R.Run72(runs, norec_name), name)
    return {r[0] for r in rows[start:] if r[2] == "FAIL"}, meas


def mutated(runs, base, what):
    """Copies of the census run and its eventlog twin with one S1 / S2 evidence item changed."""
    tmp = tempfile.mkdtemp(prefix="m2s72f0n-")
    for c in (base, base + "-ev"):
        shutil.copytree(os.path.join(runs, c), os.path.join(tmp, c))
        lg = os.path.join(runs, f"run-{c}.log")
        if os.path.exists(lg):
            shutil.copy(lg, os.path.join(tmp, f"run-{c}.log"))
    if what == "iface-par":
        p = os.path.join(tmp, base, base, "0.sca")
        L = open(p).read().split("\n")
        k = 0
        for i, line in enumerate(L):
            if line.startswith(f"par {TABLE} forwardingTable ") and 'interface: \\"dnEth\\"' in line:
                L[i] = line.replace('interface: \\"dnEth\\"', 'interface: \\"ppp[0]\\"')
                k += 1
        if k != 1:
            raise ValueError(f"mutation iface-par: {k} par lines changed")
        open(p, "w").write("\n".join(L))
    else:
        p = os.path.join(tmp, base + "-ev", base + "-ev", "0.elog")
        L = open(p, errors="replace").read().split("\n")
        k = 0
        for i, line in enumerate(L):
            if not line.startswith("- "):
                continue
            txt = ANSI.sub("", line)
            if mac_txt(LISTENER_MAC) in txt and "vid = 42" in txt and "interfaceId = " in txt:
                L[i] = re.sub(r"(interfaceId(?:\x1b\[0m)? = )(\d+)", lambda m: m.group(1) + str(int(m.group(2)) + 1), line)
                k += 1
        if k == 0:
            raise ValueError("mutation iface-log: no line changed")
        open(p, "w").write("\n".join(L))
    return tmp


def main():
    out = sys.argv[1]
    runs = os.path.join(out, "runs")
    filt = sys.argv[2] if len(sys.argv) > 2 else None
    dvals = defaultdict(set)
    census_rows = []
    for opt in ("q0", "qdu"):
        for n in (1, 2, 4, 8):
            name = f"M2S72-F0-{opt}-n{n}"
            if filt and not re.search(filt, name):
                continue
            if not os.path.isdir(os.path.join(runs, name)):
                add("F0", name, False, "run missing")
                continue
            start = len(rows)
            fails, meas = evaluate(runs, name, opt, name + "-ev", name + "-norec")
            for s, v in meas.items():
                dvals[s] |= set(v)
            census_rows += rows[start:]
    if not filt:
        r = ("F0-7", "all census runs", "PASS" if all(len(v) == 1 for v in dvals.values()) and len(dvals) == 2 else "FAIL",
             f"d per direction over all census runs: { {s: sorted(v) for s, v in dvals.items()} } (ps)")
        rows.append(r)
        census_rows.append(r)
    # negative controls
    ctrl_rows, ctrl = [], []
    for c, exp in CONTROLS.items():
        name = f"M2S72-F0N-{c}"
        if filt and not re.search(filt, name):
            continue
        start = len(rows)
        if not os.path.isdir(os.path.join(runs, name)):
            ctrl.append((name, False, "run missing", set(), exp))
            continue
        fails, _ = evaluate(runs, name, "q0", name + "-ev")
        ctrl_rows += rows[start:]
        ctrl.append((name, fails == exp, "", fails, exp))
    for m, exp in MUTATIONS.items():
        if filt and not re.search(filt, m):
            continue
        tmp = mutated(runs, "M2S72-F0-q0-n2", m)
        try:
            start = len(rows)
            fails, _ = evaluate(tmp, "M2S72-F0-q0-n2", "q0", "M2S72-F0-q0-n2-ev")
            for r in rows[start:]:
                ctrl_rows.append((r[0], f"mutation {m}: " + r[1], r[2], r[3]))
            del rows[start:]
            ctrl.append((f"mutation {m}", fails == exp, "", fails, exp))
        finally:
            shutil.rmtree(tmp)
    print("M2-S7.2a gate F0, Checkpoint 1 revision 2 (design rev. 2.1, A-1 .. A-6)\n")
    for r in census_rows:
        print(" | ".join(r))
    nf = sum(1 for r in census_rows if r[2] == "FAIL")
    print(f"\nF0: {sum(1 for r in census_rows if r[2] == 'PASS')} PASS, {nf} FAIL")
    print("\nF0-6 negative controls (each must fail exactly its predicted rows):")
    for r in ctrl_rows:
        print("   " + " | ".join(r))
    for name, ok, note, fails, exp in ctrl:
        print(f"{'PASS' if ok else 'FAIL'} | control {name} | failed rows {sorted(fails)}, predicted {sorted(exp)} {note}")
    nc = sum(1 for x in ctrl if not x[1])
    print(f"controls: {len(ctrl) - nc} PASS, {nc} FAIL")
    verdict = nf == 0 and nc == 0
    print("F0 verdict: " + ("PASS" if verdict else "FAIL (stop and report)"))
    return 0 if verdict else 1


if __name__ == "__main__":
    sys.exit(main())
