#!/usr/bin/env python3
"""M2-B TSN AF offline configuration compiler, increment M2B-1 (docs/migration/m2b-scfg-interface.md, S-CFG/1).

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

Out of scope in M2B-1 (refused, never silently ignored): TAS gate lists, TSCAI, FRER, runtime observation, per-UE DRB
templates, VID-based classification, dynamic 5GC configuration.
"""
import json
import os
import re
import sys
import tempfile

SCHEMA = "nasctime-scfg/1"
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
    if not c.fields(spec, TOP, "specification"):
        raise SpecError(c.p)
    if spec.get("schema") != SCHEMA:
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
    return {"notes": notes, "n": n_ues, "profiles": profiles, "drbs": sorted(drbs, key=lambda x: x["drb_id"]), "qfi_drb": qfi_drb,
            "streams": norm}


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
    return "\n".join(out) + "\n"


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
