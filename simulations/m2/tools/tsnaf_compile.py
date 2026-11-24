#!/usr/bin/env python3
"""M2-B TSN AF offline configuration compiler: M2B-1 (docs/migration/m2b-scfg-interface.md, S-CFG/1) and M2B-3
(docs/migration/m2b-3-tas-qbv.md, S-CFG/2 = S-CFG/1 + a required "tas" section).

Translates a TSN stream specification into the Simu5G 1.8.1 bearer configuration of the BearerConfigurator:
    *.bearerConfigurator.dlQfiRules   shared: DL classification (TSN stream -> QoS flow), no UE field
    *.bearerConfigurator.drbProfiles  shared: DRB profile catalogue
    *.bearerConfigurator.staticDrbs   per UE: DRBs, and the QoS flows (QFIs) each DRB carries
    *.bearerConfigurator.ulQfiRules   per UE: UL classification (TSN stream -> QoS flow)

    python3 -I -B tsnaf_compile.py validate <spec.json> --ues N
    python3 -I -B tsnaf_compile.py emit     <spec.json> --ues N [--out FILE]

Classification (S-CFG/1): by PCP, or by the gPTP-event class. The VID is validated stream metadata and is NOT part of
the generated predicate: streams with the same PCP in the same scope share one rule whatever their VIDs. Mapping them
to different QoS flows is refused as a conflict; mapping them to the same QoS flow is valid and reported as a note on
standard error.

Exit: 0 success; 1 invalid specification (one error line per problem, nothing written); 2 usage or I/O error.
With --out the file must not exist; it is written completely (temporary file, then rename) or not at all. Without
--out the result goes to standard output only after the whole compilation succeeded. No other file is read or written.

M2B-5 (docs/migration/m2b-5-common-epoch.md): with "tas": {"time_reference": "common-epoch", ...} every schedule is
anchored by base_time_ns (a TT time) instead of phase_ns; its gates become nasctime.m2.TtEpochGate (INET PeriodicGate
with the initial position taken from the translator's TT clock). Without time_reference, S-CFG/2 is unchanged.

S-CFG/2 (schema "nasctime-scfg/2") additionally emits the IEEE 802.1Qbv gate schedules of the translators' egress ports
as native INET parameters (Ieee8021qTimeAwareShaper / PeriodicGate) and the TT clock binding (TtGateClock and the
explicit transmissionGate clockModule binding); see check_tas() and emit_tas(). An S-CFG/1 specification compiles
exactly as before; the S-CFG/2 output begins with the S-CFG/1 output of the same bearer part.

Out of scope (refused, never silently ignored): TSCAI, FRER, runtime observation, per-UE DRB templates, VID-based
classification, dynamic 5GC configuration; in S-CFG/2 also gate lists of other bridges, other traffic-class counts
than 8, and hold/release (frame preemption) operations.
"""
import json
import os
import re
import sys
import tempfile

SCHEMA = "nasctime-scfg/1"
SCHEMA2 = "nasctime-scfg/2"
PCP_FILTER = 'expr(has(ieee8021qctag) && ieee8021qctag.pcp == {pcp})'
CLASS_FILTERS = {"gptp-event": "expr(has(GptpSync) || has(GptpFollowUp))"}   # untagged gPTP event messages
RLC_MODES = ("UM", "AM")
NAME = re.compile(r"^[a-z][a-z0-9-]{0,62}$")
MOD = re.compile(r"^[A-Za-z][A-Za-z0-9_]{0,62}$")

TOP = {"schema": True, "endpoints": True, "drb_profiles": False, "drbs": True, "qos_flows": True, "streams": True}
EP = {"side": True}
PROFILE = {"qosPriorityLevel": True, "packetDelayBudget": True}
DRB = {"drb_id": True, "default": False, "lcg": True, "rlc_mode": True, "profile": False}
FLOW = {"qfi": True, "drb_id": True}
STREAM = {"id": True, "direction": True, "source": True, "destination": True, "ues": True, "vid": False, "pcp": False,
          "class": False, "qfi": True}
TOP2 = dict(TOP, tas=True)
# S-CFG/2 TAS section
TAS = {"untagged_tc": True, "schedules": True, "time_reference": False}
SCHED = {"id": True, "translator": True, "port": True, "cycle_ns": True, "phase_ns": True, "entries": True}
# M2B-5: common-epoch schedules (opt-in, tas.time_reference = "common-epoch"): anchored by base_time_ns instead of phase_ns
TIME_REFS = ("relative-phase", "common-epoch")
SCHED_EPOCH = {"id": True, "translator": True, "port": True, "cycle_ns": True, "base_time_ns": False, "phase_ns": False,
               "entries": True}
MAX_BASE_NS = 9000000000000                            # 9000 s: base_time_ns * 1000 ps < 2^53 (exact as an INI double)
ENTRY = {"start_ns": True, "duration_ns": True, "open": True}
NTC = 8                                                # Ieee8021qTimeAwareShaper default number of traffic classes
# INET 4.7.0 PcpTrafficClassClassifier default mapping at 8 traffic classes (IEEE 802.1Q Table 8-5): PCP -> class
PCP_TO_TC = (1, 0, 2, 3, 4, 5, 6, 7)
PORTS = {"5gs": 0, "tsn": 1}                           # PassThroughTt (M2S72Bridge): eth[0] 5GS side, eth[1] TSN side
DS_K = re.compile(r"^ds-tt\[(0|[1-9][0-9]?)\]$")
MAX_CYCLE_NS, MIN_CYCLE_NS, MAX_ENTRIES = 1000000000, 1000, 256
QUEUE = "eth[{port}].macLayer.queue"


class SpecError(Exception):
    def __init__(self, problems):
        super().__init__("\n".join(problems))
        self.problems = problems


def _int(v):
    return isinstance(v, int) and not isinstance(v, bool)


def _str(v):
    return isinstance(v, str)


class Checker:
    def __init__(self):
        self.p = []

    def err(self, msg):
        self.p.append(msg)

    def fields(self, obj, allowed, where):
        if not isinstance(obj, dict):
            self.err(f"{where}: must be an object")
            return False
        for k in obj:
            if k not in allowed:
                self.err(f"{where}: unsupported field {k!r}")
        for k, req in allowed.items():
            if req and k not in obj:
                self.err(f"{where}: missing required field {k!r}")
        return True

    def rng(self, v, lo, hi, where):
        if not _int(v) or not lo <= v <= hi:
            self.err(f"{where}: {v!r} is not an integer in [{lo}, {hi}]")
            return False
        return True


def check(spec, n_ues):
    """validate the whole specification; return the normalised model or raise SpecError with every problem found"""
    c = Checker()
    if not _int(n_ues) or n_ues < 1 or n_ues > 64:
        raise SpecError([f"--ues: {n_ues!r} is not an integer in [1, 64]"])
    v2 = isinstance(spec, dict) and spec.get("schema") == SCHEMA2 and "tas" in spec
    if not c.fields(spec, TOP2 if v2 else TOP, "specification"):
        raise SpecError(c.p)
    if spec.get("schema") == SCHEMA2 and not v2:
        c.err(f"schema: {SCHEMA2!r} requires the 'tas' section (S-CFG/2 = S-CFG/1 + TAS); without TAS use {SCHEMA!r}")
    elif spec.get("schema") != SCHEMA and not v2:
        c.err(f"schema: {spec.get('schema')!r}, expected {SCHEMA!r}")

    eps = spec.get("endpoints", {})
    if not isinstance(eps, dict) or not eps:
        c.err("endpoints: must be a non-empty object")
        eps = {}
    sides = {}                                         # the validated endpoints: name -> side
    for name, ep in eps.items():
        if not MOD.match(name):
            c.err(f"endpoints.{name}: not a valid module name")
            continue
        if not c.fields(ep, EP, f"endpoints.{name}"):
            continue
        side = ep.get("side")
        if not _str(side) or side not in ("network", "ue"):
            c.err(f"endpoints.{name}.side: {side!r}, expected 'network' or 'ue'")
            continue
        sides[name] = side

    profiles = spec.get("drb_profiles", {})
    if not isinstance(profiles, dict):
        c.err("drb_profiles: must be an object")
        profiles = {}
    for name, pr in profiles.items():
        if not NAME.match(name):
            c.err(f"drb_profiles.{name}: profile name must match {NAME.pattern}")
        if c.fields(pr, PROFILE, f"drb_profiles.{name}"):
            c.rng(pr.get("qosPriorityLevel"), 1, 127, f"drb_profiles.{name}.qosPriorityLevel")
            c.rng(pr.get("packetDelayBudget"), 1, 100000, f"drb_profiles.{name}.packetDelayBudget")

    drbs = spec.get("drbs", [])
    if not isinstance(drbs, list) or not drbs:
        c.err("drbs: must be a non-empty list")
        drbs = []
    ids, defaults = {}, []
    for i, d in enumerate(drbs):
        w = f"drbs[{i}]"
        if not c.fields(d, DRB, w):
            continue
        if c.rng(d.get("drb_id"), 1, 32, f"{w}.drb_id"):
            if d["drb_id"] in ids:
                c.err(f"{w}.drb_id: duplicate DRB id {d['drb_id']}")
            ids[d["drb_id"]] = d
        if "default" in d and d["default"] is not True:
            c.err(f"{w}.default: only true is allowed (omit the field for a non-default DRB)")
        if d.get("default") is True:
            defaults.append(d.get("drb_id"))
        c.rng(d.get("lcg"), 0, 7, f"{w}.lcg")
        if d.get("rlc_mode") not in RLC_MODES:
            c.err(f"{w}.rlc_mode: {d.get('rlc_mode')!r}, expected one of {list(RLC_MODES)}")
        if "profile" in d and (not _str(d["profile"]) or d["profile"] not in profiles):
            c.err(f"{w}.profile: DRB profile {d['profile']!r} is not defined in drb_profiles")
    if drbs and len(defaults) != 1:
        c.err(f"drbs: exactly one default DRB is required, found {len(defaults)}")

    flows = spec.get("qos_flows", [])
    if not isinstance(flows, list):
        c.err("qos_flows: must be a list")
        flows = []
    qfi_drb = {}
    for i, f in enumerate(flows):
        w = f"qos_flows[{i}]"
        if not c.fields(f, FLOW, w):
            continue
        ok = c.rng(f.get("qfi"), 1, 63, f"{w}.qfi")
        if ok and f["qfi"] in qfi_drb:
            c.err(f"{w}.qfi: QoS flow {f['qfi']} is declared twice (a QFI maps to one DRB)")
        if not _int(f.get("drb_id")) or f.get("drb_id") not in ids:
            c.err(f"{w}.drb_id: DRB {f.get('drb_id')!r} is not defined in drbs")
        elif ids[f["drb_id"]].get("default") is True:
            c.err(f"{w}.drb_id: DRB {f['drb_id']} is the default DRB; QoS flows map to non-default DRBs in S-CFG/1")
        if ok:
            qfi_drb[f["qfi"]] = f.get("drb_id")

    streams = spec.get("streams", [])
    if not isinstance(streams, list) or not streams:
        c.err("streams: must be a non-empty list")
        streams = []
    seen_ids, dl_rules, ul_rules = set(), {}, {}      # dl: classifier -> (qfi, stream, vid); ul: (ue, classifier) -> ...
    vids = {}                                          # (scope, classifier) -> {vid: [stream ids]} for PCP classifiers
    norm = []
    for i, s in enumerate(streams):
        w = f"streams[{i}]"
        if not c.fields(s, STREAM, w):
            continue
        sid = s.get("id")
        if not _str(sid) or not NAME.match(sid):
            c.err(f"{w}.id: stream identity {sid!r} must be a string matching {NAME.pattern}")
            sid = None
        elif sid in seen_ids:
            c.err(f"{w}.id: duplicate stream identity {sid!r}")
        else:
            seen_ids.add(sid)
        w = f"stream {sid!r}" if sid is not None else w
        d = s.get("direction")
        if not _str(d) or d not in ("dl", "ul"):
            c.err(f"{w}.direction: {d!r}, expected 'dl' or 'ul'")
        src, dst = s.get("source"), s.get("destination")
        for role, ep in (("source", src), ("destination", dst)):
            if not _str(ep) or ep not in sides:
                c.err(f"{w}.{role}: unknown endpoint {ep!r}")
        if _str(d) and d in ("dl", "ul") and _str(src) and _str(dst) and src in sides and dst in sides:
            want = ("network", "ue") if d == "dl" else ("ue", "network")
            got = (sides[src], sides[dst])
            if got != want:
                c.err(f"{w}: a {d.upper()} stream runs from a {want[0]}-side to a {want[1]}-side endpoint; "
                      f"{src!r} is {got[0]}-side and {dst!r} is {got[1]}-side")
        ues = s.get("ues")
        if ues == "all":
            ue_set = list(range(n_ues))
        elif isinstance(ues, list) and ues and all(_int(u) for u in ues):
            bad = [u for u in ues if not 0 <= u < n_ues]
            if bad:
                c.err(f"{w}.ues: unknown UE index {bad} (the configuration has {n_ues} UE(s): 0 .. {n_ues - 1})")
            if len(set(ues)) != len(ues):
                c.err(f"{w}.ues: a UE index is listed twice")
            ue_set = sorted(set(u for u in ues if 0 <= u < n_ues))
        else:
            c.err(f"{w}.ues: must be \"all\" or a non-empty list of UE indices")
            ue_set = []
        has_pcp, has_cls = "pcp" in s, "class" in s
        if has_pcp == has_cls:
            c.err(f"{w}: exactly one classifier is required: 'pcp' (with 'vid') or 'class'")
            continue
        if has_pcp:
            if "vid" not in s:
                c.err(f"{w}.vid: a PCP-classified stream needs its VLAN ID")
            else:
                c.rng(s["vid"], 1, 4094, f"{w}.vid")
            if not c.rng(s["pcp"], 0, 7, f"{w}.pcp"):
                continue
            key = ("pcp", s["pcp"])
        else:
            if "vid" in s:
                c.err(f"{w}.vid: not allowed with 'class' (class streams are untagged in S-CFG/1)")
            if not _str(s["class"]) or s["class"] not in CLASS_FILTERS:
                c.err(f"{w}.class: {s['class']!r}, expected one of {sorted(CLASS_FILTERS)}")
                continue
            key = ("class", s["class"])
        q = s.get("qfi")
        if not c.rng(q, 1, 63, f"{w}.qfi"):
            continue
        if q not in qfi_drb:
            c.err(f"{w}.qfi: QoS flow {q} is not declared in qos_flows")
        vid = s.get("vid") if has_pcp and _int(s.get("vid")) and 1 <= s.get("vid") <= 4094 else None   # validated only
        if d == "dl":
            prev = dl_rules.get(key)
            if prev and prev[0] != q:
                c.err(f"{w}: conflicting DL classification: {key[0]} {key[1]} -> QFI {q}, but stream {prev[1]!r} "
                      f"maps it to QFI {prev[0]} (DL rules are shared by every UE){_vid_note(vid, prev[2])}")
            dl_rules.setdefault(key, (q, sid, vid))
            if vid is not None:
                vids.setdefault(("DL", key), {}).setdefault(vid, []).append(sid)
        elif d == "ul":
            for u in ue_set:
                prev = ul_rules.get((u, key))
                if prev and prev[0] != q:
                    c.err(f"{w}: conflicting UL classification for UE {u}: {key[0]} {key[1]} -> QFI {q}, but stream "
                          f"{prev[1]!r} maps it to QFI {prev[0]}{_vid_note(vid, prev[2])}")
                ul_rules.setdefault((u, key), (q, sid, vid))
                if vid is not None:
                    vids.setdefault((f"UL UE {u}", key), {}).setdefault(vid, []).append(sid)
        norm.append({"id": sid, "dir": d, "key": key, "qfi": q, "ues": ue_set})
    tas = check_tas(c, spec.get("tas"), n_ues, norm) if v2 else None
    if c.p:
        raise SpecError(c.p)
    notes = []
    for (scope, key), by_vid in vids.items():         # valid, but easy to misread as per-VLAN classification
        if len([v for v in by_vid if _int(v)]) > 1:
            q = (dl_rules[key] if scope == "DL" else ul_rules[(int(scope.rsplit(" ", 1)[1]), key)])[0]
            ids_ = ", ".join(f"{x!r} (VID {v})" for v in sorted(v for v in by_vid if _int(v)) for x in by_vid[v])
            notes.append(f"{scope}: streams {ids_} share one rule 'PCP {key[1]} -> QFI {q}'. The VID is not part of the "
                         f"classification predicate (S-CFG/1): every frame with PCP {key[1]}, on any VLAN, is "
                         f"classified to QFI {q}.")
    model = {"notes": notes, "n": n_ues, "profiles": profiles, "drbs": sorted(drbs, key=lambda x: x["drb_id"]),
             "qfi_drb": qfi_drb, "streams": norm}
    if tas is not None:
        model["tas"] = tas
    return model


def _targets(translator, n_ues):
    """the translators a schedule applies to: [(kind, index)] with kind 'nw' or 'ds'"""
    if translator == "nw-tt":
        return [("nw", 0)]
    if translator == "ds-tt":
        return [("ds", k) for k in range(n_ues)]
    m = DS_K.match(translator)
    return [("ds", int(m.group(1)))]


def _tname(t):
    return "nw-tt" if t[0] == "nw" else f"ds-tt[{t[1]}]"


def check_tas(c, tas, n_ues, streams):
    """S-CFG/2 'tas' section: validate; return the normalised schedules (every problem is reported through c)"""
    if not c.fields(tas, TAS, "tas"):
        return None
    utc = tas.get("untagged_tc")
    c.rng(utc, 0, NTC - 1, "tas.untagged_tc")
    tref = tas.get("time_reference", "relative-phase")
    if not _str(tref) or tref not in TIME_REFS:
        c.err(f"tas.time_reference: {tref!r}, expected one of {list(TIME_REFS)}")
        tref = None
    epoch = tref == "common-epoch"
    scheds = tas.get("schedules")
    if not isinstance(scheds, list) or not scheds:
        c.err("tas.schedules: must be a non-empty list")
        return None
    out, ids, owner = [], set(), {}                    # owner: (translator, port) -> schedule id
    for i, sc in enumerate(scheds):
        w = f"tas.schedules[{i}]"
        if not c.fields(sc, SCHED_EPOCH if epoch else SCHED, w):
            continue
        if epoch and "phase_ns" in sc:
            c.err(f"{w}: conflicting phase_ns and base_time_ns: a common-epoch schedule (tas.time_reference) is anchored "
                  f"by base_time_ns only")
        if epoch and "base_time_ns" not in sc:
            c.err(f"{w}: missing base_time_ns: common-epoch mode (tas.time_reference) requires a common base time")
        sid = sc.get("id")
        if not _str(sid) or not NAME.match(sid):
            c.err(f"{w}.id: schedule identity {sid!r} must be a string matching {NAME.pattern}")
            continue
        if sid in ids:
            c.err(f"{w}.id: duplicate schedule identity {sid!r}")
            continue
        ids.add(sid)
        w = f"tas schedule {sid!r}"
        tr = sc.get("translator")
        if not _str(tr) or not (tr in ("nw-tt", "ds-tt") or DS_K.match(tr)):
            c.err(f"{w}.translator: {tr!r}, expected 'nw-tt', 'ds-tt' (every DS-TT) or 'ds-tt[k]'")
            tr = None
        elif DS_K.match(tr) and int(DS_K.match(tr).group(1)) >= n_ues:
            c.err(f"{w}.translator: {tr!r} does not exist (the configuration has {n_ues} DS-TT(s): 0 .. {n_ues - 1})")
            tr = None
        port = sc.get("port")
        if not _str(port) or port not in PORTS:
            c.err(f"{w}.port: {port!r}, expected one of {sorted(PORTS)}")
            port = None
        cyc = sc.get("cycle_ns")
        cyc_ok = c.rng(cyc, MIN_CYCLE_NS, MAX_CYCLE_NS, f"{w}.cycle_ns")
        base_ok = phase_ok = False
        if epoch:
            if "base_time_ns" in sc:
                base_ok = c.rng(sc.get("base_time_ns"), 0, MAX_BASE_NS, f"{w}.base_time_ns")
        elif cyc_ok:
            phase_ok = c.rng(sc.get("phase_ns"), 0, cyc - 1, f"{w}.phase_ns")
        elif not _int(sc.get("phase_ns")) or sc.get("phase_ns") < 0:
            c.err(f"{w}.phase_ns: {sc.get('phase_ns')!r} is not a non-negative integer")
        ents = sc.get("entries")
        if not isinstance(ents, list) or not ents or len(ents) > MAX_ENTRIES:
            c.err(f"{w}.entries: must be a list of 1 .. {MAX_ENTRIES} gate-control entries")
            continue
        norm_e, end, ok = [], 0, True
        for j, e in enumerate(ents):
            we = f"{w}.entries[{j}]"
            if not c.fields(e, ENTRY, we):
                ok = False
                continue
            st, du, op = e.get("start_ns"), e.get("duration_ns"), e.get("open")
            good = c.rng(st, 0, MAX_CYCLE_NS, f"{we}.start_ns") & c.rng(du, 1, MAX_CYCLE_NS, f"{we}.duration_ns")
            if not isinstance(op, list) or not all(_int(x) and 0 <= x < NTC for x in op):
                c.err(f"{we}.open: {op!r} must be a list of traffic classes in [0, {NTC - 1}]")
                good = False
            elif len(set(op)) != len(op):
                c.err(f"{we}.open: a traffic class is listed twice")
                good = False
            if not good:
                ok = False
                continue
            if st < end:
                c.err(f"{we}: overlaps the previous entry (starts at {st} ns, the previous entry ends at {end} ns)")
                ok = False
            elif st > end:
                c.err(f"{we}: gap before the entry ({end} .. {st} ns is not covered)")
                ok = False
            end = st + du
            norm_e.append((st, du, frozenset(op)))
        if ok and cyc_ok and end != cyc:
            c.err(f"{w}.entries: the entries end at {end} ns, the cycle is {cyc} ns "
                  + ("(they extend beyond the cycle)" if end > cyc else "(gap at the end of the cycle)"))
            ok = False
        if ok and _int(utc) and 0 <= utc < NTC:
            shut = [j for j, (_, _, op) in enumerate(norm_e) if utc not in op]
            if shut:
                c.err(f"{w}: the untagged traffic class {utc} (gPTP) must be open in every entry; closed in entries {shut}")
                ok = False
        # a schedule whose anchor (phase_ns or base_time_ns) is missing or invalid was reported above; it is not normalised
        # (M2B-5: a missing phase_ns previously raised KeyError after its error had been recorded)
        if not ok or tr is None or port is None or not cyc_ok or (epoch and (not base_ok or "phase_ns" in sc)) \
                or (not epoch and not phase_ok):
            continue
        for t in _targets(tr, n_ues):
            prev = owner.get((t, port))
            if prev is not None:
                c.err(f"{w}: overlapping schedules: {prev!r} and {sid!r} both configure the gates of {_tname(t)} port {port}")
            owner.setdefault((t, port), sid)
        if epoch:
            out.append({"id": sid, "translator": tr, "port": port, "cycle": cyc, "phase": 0, "base": sc["base_time_ns"],
                        "entries": norm_e})
        else:
            out.append({"id": sid, "translator": tr, "port": port, "cycle": cyc, "phase": sc["phase_ns"], "entries": norm_e})
    if c.p:
        return None
    by_target = {(t, s["port"]): s for s in out for t in _targets(s["translator"], n_ues)}
    for st in streams:                                 # a scheduled egress port must let every stream through
        tc = PCP_TO_TC[st["key"][1]] if st["key"][0] == "pcp" else utc
        egress = ([(("ds", k), "tsn") for k in st["ues"]] + [(("nw", 0), "5gs")] if st["dir"] == "dl"
                  else [(("nw", 0), "tsn")] + [(("ds", k), "5gs") for k in st["ues"]])
        for target in egress:
            s = by_target.get(target)
            if s is not None and all(tc not in op for _, _, op in s["entries"]):
                c.err(f"stream {st['id']!r} (traffic class {tc}) is never transmitted at {_tname(target[0])} port "
                      f"{target[1]}: its gate is closed in every entry of tas schedule {s['id']!r}")
    return {"untagged_tc": utc, "schedules": out}


def gate_params(sched, tc):
    """native PeriodicGate parameters of traffic class tc: (initiallyOpen, [durations ns], offset ns). The durations
    alternate starting with the initial state and begin at a state change of tc (a rotation of the cycle), so that
    PeriodicGate's even-length alternation holds; offset = the schedule phase minus that rotation, modulo the cycle."""
    ents, cyc = sched["entries"], sched["cycle"]
    states = [tc in op for _, _, op in ents]
    if all(s == states[0] for s in states):
        return states[0], [], 0
    n = len(ents)
    r = next(j for j in range(n) if states[j] != states[j - 1])   # first entry that starts a new state (cyclic)
    runs = []
    for j in list(range(r, n)) + list(range(0, r)):
        if runs and runs[-1][0] == states[j]:
            runs[-1][1] += ents[j][1]
        else:
            runs.append([states[j], ents[j][1]])
    assert len(runs) % 2 == 0 and sum(d for _, d in runs) == cyc
    return states[r], [d for _, d in runs], (sched["phase"] - ents[r][0]) % cyc


def _prefix(t):
    return "*.nwTt" if t == "nw-tt" else "*.dsTt[*]" if t == "ds-tt" else "*.dsTt[" + DS_K.match(t).group(1) + "]"


def _order(t):
    return (0, -1) if t == "nw-tt" else (1, -1) if t == "ds-tt" else (1, int(DS_K.match(t).group(1)))


def emit_tas(tas):
    """the TAS lines: per translator the shaper, the TT gate clock and the explicit gate binding; then per schedule and
    traffic class the PeriodicGate parameters. Deterministic: translators nw-tt, ds-tt, ds-tt[k]; ports 5gs, tsn."""
    out = []
    for t in sorted({s["translator"] for s in tas["schedules"]}, key=_order):
        p = _prefix(t)
        out += [f"{p}.hasEgressTrafficShaping = true",
                f'{p}.clock.typename = "nasctime.m2.TtGateClock"',
                f'{p}.eth[*].macLayer.queue.transmissionGate[*].clockModule = "^.^.^.^.clock"',
                f"{p}.eth[*].macLayer.queue.classifier.defaultGateIndex = {tas['untagged_tc']}"]
    for s in sorted(tas["schedules"], key=lambda x: (_order(x["translator"]), PORTS[x["port"]])):
        q = f"{_prefix(s['translator'])}.{QUEUE.format(port=PORTS[s['port']])}"
        for tc in range(NTC):
            op, durs, off = gate_params(s, tc)
            g = f"{q}.transmissionGate[{tc}]"
            if s.get("base") is not None:              # M2B-5 common epoch: offset = list position when C_T = baseTime
                out += [f'{g}.typename = "nasctime.m2.TtEpochGate"', f"{g}.baseTime = {s['base']}ns"]
            out += [f"{g}.initiallyOpen = {'true' if op else 'false'}",
                    f"{g}.durations = [{', '.join(f'{d}ns' for d in durs)}]",
                    f"{g}.offset = {off}ns"]
    return "\n".join(out) + "\n"


def _vid_note(vid, prev_vid):
    if _int(vid) and _int(prev_vid) and vid != prev_vid:
        return (f"; the VID is not part of the classification predicate in S-CFG/1, so streams on VID {prev_vid} and "
                f"VID {vid} with the same PCP cannot be mapped to different QoS flows")
    return ""


def _filter(key):
    return PCP_FILTER.format(pcp=key[1]) if key[0] == "pcp" else CLASS_FILTERS[key[1]]


def _layout(key, items, template_size, opener="[", closer="]"):
    """one line when the per-UE template (or the shared list) has one element, else one element per line"""
    if template_size <= 1:
        return f"*.bearerConfigurator.{key} = {opener}" + ", ".join(items) + closer
    return f"*.bearerConfigurator.{key} = {opener}\n" + ",\n".join("    " + x for x in items) + f"\n    {closer}"


def emit(model):
    """the S-CFG text: shared keys first, then per-UE keys, in a fixed order; deterministic for a given input"""
    out = []
    dl, seen = [], set()
    for s in model["streams"]:                         # rule order = order of first appearance (lists are first-match)
        if s["dir"] == "dl" and s["key"] not in seen:
            seen.add(s["key"])
            dl.append(f'{{filter: "{_filter(s["key"])}", qfi: {s["qfi"]}}}')
    if dl:
        out.append(_layout("dlQfiRules", dl, len(dl)))
    pr = model["profiles"]
    if pr:
        items = [f'"{n}": {{qosPriorityLevel: {pr[n]["qosPriorityLevel"]}, packetDelayBudget: {pr[n]["packetDelayBudget"]}}}'
                 for n in sorted(pr)]
        out.append(_layout("drbProfiles", items, len(items), "{", "}"))
    template = []
    for d in model["drbs"]:
        qfis = sorted(q for q, did in model["qfi_drb"].items() if did == d["drb_id"])
        mid = "isDefault: true" if d.get("default") else f"mappedQfis: [{', '.join(map(str, qfis))}]"
        prof = f', profile: "{d["profile"]}"' if "profile" in d else ""
        template.append((f'{{coreNetwork: "5gc", ue: "ue[{{k}}]", drbId: {d["drb_id"]}, {mid}, lcg: {d["lcg"]}, '
                         f'rlcMode: "{d["rlc_mode"]}"{prof}}}'))
    drbs = [t.replace("{k}", str(k)) for k in range(model["n"]) for t in template]
    out.append(_layout("staticDrbs", drbs, len(template)))
    ul, per_ue = [], {}
    for k in range(model["n"]):
        seen = set()
        for s in model["streams"]:
            if s["dir"] == "ul" and k in s["ues"] and s["key"] not in seen:
                seen.add(s["key"])
                ul.append(f'{{ue: "ue[{k}]", filter: "{_filter(s["key"])}", qfi: {s["qfi"]}}}')
                per_ue[k] = per_ue.get(k, 0) + 1
    if ul:
        out.append(_layout("ulQfiRules", ul, max(per_ue.values())))
    text = "\n".join(out) + "\n"
    if model.get("tas") is not None:                  # S-CFG/2 only; an S-CFG/1 model has no "tas"
        text += emit_tas(model["tas"])
    return text


def compile_file(path, n_ues, with_notes=False):
    try:
        with open(path, encoding="utf-8") as fh:
            spec = json.load(fh, object_pairs_hook=_no_dup_keys)
    except SpecError:
        raise
    except (OSError, ValueError) as ex:
        raise SpecError([f"{path}: cannot read a JSON specification: {ex}"])
    model = check(spec, n_ues)
    return (emit(model), model["notes"]) if with_notes else emit(model)


def _no_dup_keys(pairs):
    d = {}
    for k, v in pairs:
        if k in d:
            raise SpecError([f"duplicate JSON key {k!r}"])
        d[k] = v
    return d


def main(argv):
    args = argv[1:]
    if len(args) < 4 or args[0] not in ("validate", "emit") or args[2] != "--ues":
        print(__doc__, file=sys.stderr)
        return 2
    mode, spec, out = args[0], args[1], None
    try:
        n = int(args[3])
    except ValueError:
        print(f"--ues: {args[3]!r} is not an integer", file=sys.stderr)
        return 2
    rest = args[4:]
    if rest:
        if mode != "emit" or len(rest) != 2 or rest[0] != "--out":
            print(__doc__, file=sys.stderr)
            return 2
        out = rest[1]
    try:
        text, notes = compile_file(spec, n, with_notes=True)
    except SpecError as ex:
        for p in ex.problems:
            print(f"error: {p}", file=sys.stderr)
        return 1
    for x in notes:
        print(f"note: {x}", file=sys.stderr)
    if mode == "validate":
        print(f"valid: {spec} at {n} UE(s)")
        return 0
    if out is None:
        sys.stdout.write(text)
        return 0
    if os.path.lexists(out):
        print(f"error: {out} exists; it is never overwritten", file=sys.stderr)
        return 2
    d = os.path.dirname(os.path.abspath(out))
    try:
        fd, tmp = tempfile.mkstemp(prefix=".tsnaf-", dir=d)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.link(tmp, out)                              # fails if out appeared meanwhile; never replaces a file
        os.unlink(tmp)
    except OSError as ex:
        try:
            os.unlink(tmp)
        except (OSError, UnboundLocalError):
            pass
        print(f"error: cannot write {out}: {ex}", file=sys.stderr)
        return 2
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
