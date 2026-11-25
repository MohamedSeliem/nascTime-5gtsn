#!/usr/bin/env python3
"""M2-S7.2a Stage 5, work package A3: E0v-N batch protocol support (protocol results/M2-S7.2a-e0vn-protocol.md).

Pure planning and bookkeeping for the E0v-N saturation bracket and the f_E1 selection. No simulation, no raw-output
reading, no registry write, and S5N_ADAPTER_VALIDATED is never assigned here (it is only compared). The bracket state
machine and the selection rules are the accepted ones of m2s72_e1sel.py (S5-2, decf848), imported unchanged; the
configuration set is the accepted generator's (tools/m2s72s5_gen.py matrix(), kind "N"), imported unchanged.

    m2s72_e0vn_batch.py combos <h16|h5>
        the bracket combinations of the segment, in the declared order: "<key>\\t<first config>"
    m2s72_e0vn_batch.py configs <h16|h5>
        every configuration name of the segment (combinations x ladder), one per line
    m2s72_e0vn_batch.py pins <m2 dir>
        exit 0 iff m2s72.ini, m2s72s5.ini, the FGO registry and the WP-A1 wrapper equal their accepted sha256, and every
        E0v-N configuration of both segments is a [Config] section of m2s72s5.ini
    m2s72_e0vn_batch.py decisions <record file> <h16|h5|select>
        validates the maintainer's decision record (format nasctime-s5-e0vn-decisions/1, below) and its agreement with
        the environment (S5N_ADAPTER_VALIDATED, S5_ENV_DECISION, both compared, never set); exit 0 / 1 (refused)
    m2s72_e0vn_batch.py start <combo key> <D5: approved|not-approved> [<h16 bracket.tsv>]
        the declared start factor of a combination (B-1)
    m2s72_e0vn_batch.py next <bracket.tsv> <combo key> <start>
        "RUN <factor> <config>" or "DONE <status> <f_lo> <f_hi>" from the recorded outcomes (replayed through
        m2s72_e1sel.Bracket); a record that the state machine refuses is exit 2
    m2s72_e0vn_batch.py outcome <composed digest> <config> <wrapper rc> <simulation outcome>
        "<ok|overloaded|starved|invalid>\\t<reason>" (m2s72_e1sel.classify on the composed digest's performance.across);
        exit 2 when the digest is missing, malformed or for another configuration
    m2s72_e0vn_batch.py record <bracket.tsv> <combo key> <start> <factor> <outcome> <config> <wrapper rc> <digest sha256>
        appends one outcome after replaying the existing rows (only the next declared step is accepted); fsync'd
    m2s72_e0vn_batch.py cmd <nascTime> <simu5g root> <inet root> <config> <result dir>
        the exact simulation argument vector, NUL-separated (the runner executes exactly this)
    m2s72_e0vn_batch.py authorize <decision record> <signature> <allowed_signers>
        AG-1 (proposed): the record's detached SSH signature verifies (ssh-keygen -Y verify) for the principal
        wpa1-maintainer in the namespace nasctime-s5-e0vn-approval against an allowed_signers file holding exactly one
        key of that principal (obtained by the executor out of band); exit 0 / 1. A correctly formatted record without
        a valid signature is never accepted
    m2s72_e0vn_batch.py gate <production|test>
        production: exit 1 unless the authorization gate AG-1 has been approved by the maintainer (AUTH_GATE_APPROVAL,
        set only by a reviewed commit citing that approval). test: exit 0, labelled TEST (synthetic; never evidence)
    m2s72_e0vn_batch.py select <mode> <decision record> <signature> <allowed_signers> <h16 bracket.tsv>
                               <h5 bracket.tsv> <out record>
        authorize + gate + S-1 / S-2 over every combination of both segments; exit 0 with f_E1 chosen, 8 when the
        selection must stop, 1 / 2 when refused

Decision record (written and signed off by the maintainer; this tool only reads it):
    format=nasctime-s5-e0vn-decisions/1
    S5-2-D1=not-adopted          (the per-UE RNG isolation mixin; 'adopted' is refused: no such configurations exist)
    S5-2-D2=approved             (the adapter validation, on the basis of AC-5)
    S5-2-D3=approved             (starvation thresholds 1 s / 0.5, V-3 tolerance 0.01)
    S5-2-D4=approved             (f_lo as the bound, m = 0.20, sensitivity)
    S5-2-D5=approved|not-approved  (HARQ5 bracket start at the HARQ16 f_lo)
    S5-2-D6=approved             (gate scoping of E0v-N)
    adapter_validated=<the exact value of S5N_ADAPTER_VALIDATED>
    env_decision=<the exact value of S5_ENV_DECISION>
    ac5_record=<reference of the accepted V-N1 / V-N2 / V-V1 record>
    ac6_record=<reference of the S5-2-D2 decision>
    date=<YYYY-MM-DD>
Every key exactly once; no other key; blank lines and lines starting with '#' are ignored.
"""
import hashlib
import importlib.util
import json
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
import m2s72_e1sel as SEL  # noqa: E402  (accepted, unchanged)
import m2s72s5_lib as LIB  # noqa: E402  (accepted, unchanged)

_spec = importlib.util.spec_from_file_location("m2s72s5_gen", os.path.join(M2, "tools", "m2s72s5_gen.py"))
G5 = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G5)

# accepted identities (S5-1 / S5-2 / WP-A1 records); a mismatch refuses the batch
PINS = {
    "m2s72.ini": "dfc8a7f7bb7cd1632c335c169cdbd3535e4e90a14b0d04882bb07b406aaf5505",
    "m2s72s5.ini": "e563c489852db4cac7ad8562c97373e2379c8bd4029c7f1ebb9d2ace2ff96903",
    "check/m2s72_fgo_registry.json": "2bb539cd99bdd622e843cacc68a8ea9faa6989b925bca5ee701179e3a470b3ae",
    "check/check_m2s72_s5n21.py": "a80d84462e87b2571a20181054198ef40d5cd30cea09cfc215a6cfba7bb01285",
}
OPTION_ORDER = ("q0", "q0p", "qdu", "qde")
SEGMENTS = {"h16": True, "h5": False}          # segment -> HARQ16
DECISIONS_FORMAT = "nasctime-s5-e0vn-decisions/1"
DECISION_KEYS = {
    "S5-2-D1": ("not-adopted",), "S5-2-D2": ("approved",), "S5-2-D3": ("approved",), "S5-2-D4": ("approved",),
    "S5-2-D5": ("approved", "not-approved"), "S5-2-D6": ("approved",),
}
TEXT_KEYS = ("adapter_validated", "env_decision", "ac5_record", "ac6_record", "date")
# the wrapper rows of every E0v-N run (WP-A1 design 4.8, 4.9): run-level rows and per-UE rows for UE 0 .. N - 1
RUN_ROWS = ("MAP-UE", "C-0", "PU-4h")
PER_UE_ROWS = ("PU-4o", "A2-8u")
GATE_OK = ("PASS", "NX")
# AG-1, the authorization gate (PROPOSED in step 161-R1; consistent with WP-A1 gate A, runbook rev. 4 section 3):
# the decision record is a statement signed by the maintainer with ssh-keygen -Y sign; the principal is the WP-A1 one,
# the namespace is specific to this batch so that a WP-A1 approval can never be replayed as an E0v-N one.
AUTH_PRINCIPAL = "wpa1-maintainer"
AUTH_NAMESPACE = "nasctime-s5-e0vn-approval"
# None: AG-1 is not approved, so production execution is refused. Only a reviewed commit that cites the maintainer's
# approval record of AG-1 may set it (a non-empty reference string). Never set by a tool or a test.
AUTH_GATE_APPROVAL = None
MODES = ("production", "test")
TSV_HEADER = "combo\tstart\tfactor\toutcome\tconfig\twrapper_rc\tdigest_sha256"
EXIT_STOP = 8


class Refused(Exception):
    pass


# ------------------------------------------------------------------------------------------------ the batch set --
def combos(segment):
    """[(key, option, placement, N, harq16)] of a segment in the declared order, from the accepted generator"""
    if segment not in SEGMENTS:
        raise Refused(f"unknown segment {segment!r} (h16 | h5)")
    h16 = SEGMENTS[segment]
    have = {(v[0], v[1], v[2], v[5]) for v in G5.matrix().values() if v[7] == "N"}
    out = []
    for o in OPTION_ORDER:
        for pl, n in G5.E0VN_PL:
            if (o, pl, n, h16) in have:
                out.append((combo_key(o, pl, n, h16), o, pl, n, h16))
    return out


def combo_key(o, pl, n, h16):
    return f"{o}/{pl}/{n}/{16 if h16 else 5}"


def parse_key(key):
    m = re.fullmatch(r"(q0|q0p|qdu|qde)/(one0|sym)/(1|2|4|8)/(16|5)", key or "")
    if not m:
        raise Refused(f"malformed combination key {key!r}")
    return m.group(1), m.group(2), int(m.group(3)), m.group(4) == "16"


def config_of(key, f):
    o, pl, n, h16 = parse_key(key)
    if f not in SEL.LADDER:
        raise Refused(f"factor {f} is not on the ladder {SEL.LADDER}")
    name = G5.e0vn_name(o, pl, n, f, not h16)
    if name not in G5.matrix():
        raise Refused(f"{name} is not an accepted E0v-N configuration")
    return name


def parse_factor(s):
    for f in SEL.LADDER:
        if s in (str(f), G5.G.flabel(f), repr(f)):
            return f
    raise Refused(f"factor {s!r} is not on the ladder {SEL.LADDER}")


def all_configs(segment):
    return [config_of(k, f) for k, *_ in combos(segment) for f in SEL.LADDER]


# ---------------------------------------------------------------------------------------------------- pins -----
def sha256(path):
    return LIB.sha256_file(path)


def check_pins(m2dir):
    probs = []
    for rel, want in PINS.items():
        p = os.path.join(m2dir, rel)
        if not os.path.isfile(p):
            probs.append(f"{rel}: missing")
        elif sha256(p) != want:
            probs.append(f"{rel}: sha256 {sha256(p)} is not the accepted {want}")
    ini = os.path.join(m2dir, "m2s72s5.ini")
    if os.path.isfile(ini):
        sections = set(re.findall(r"^\[Config ([^\]]+)\]", open(ini, encoding="utf-8").read(), re.M))
        miss = [c for s in SEGMENTS for c in all_configs(s) if c not in sections]
        if miss:
            probs.append(f"{len(miss)} E0v-N configuration(s) not in m2s72s5.ini, e.g. {miss[:3]}")
    return probs


# ----------------------------------------------------------------------------------------------- decisions -----
def read_decisions(path):
    if not os.path.isfile(path):
        raise Refused(f"decision record {path} does not exist")
    kv, first = {}, None
    for i, raw in enumerate(open(path, encoding="utf-8").read().splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            raise Refused(f"{path}:{i}: not key=value")
        k, v = line.split("=", 1)
        k, v = k.strip(), v.strip()
        if first is None:
            first = (k, v)
            if (k, v) != ("format", DECISIONS_FORMAT):
                raise Refused(f"{path}: the first entry must be format={DECISIONS_FORMAT}")
            continue
        if k in kv:
            raise Refused(f"{path}:{i}: duplicate key {k}")
        if k not in DECISION_KEYS and k not in TEXT_KEYS:
            raise Refused(f"{path}:{i}: unknown key {k}")
        kv[k] = v
    if first is None:
        raise Refused(f"{path}: empty")
    miss = [k for k in list(DECISION_KEYS) + list(TEXT_KEYS) if k not in kv]
    if miss:
        raise Refused(f"{path}: missing {miss}")
    for k, allowed in DECISION_KEYS.items():
        if kv[k] not in allowed:
            if k == "S5-2-D1" and kv[k] == "adopted":
                raise Refused("S5-2-D1=adopted: the per-UE RNG isolation mixin is not part of the accepted E0v-N "
                              "configurations; a reviewed generator increment is required before this batch")
            raise Refused(f"{path}: {k}={kv[k]!r}; this batch requires {' or '.join(allowed)}")
    for k in TEXT_KEYS:
        if not kv[k]:
            raise Refused(f"{path}: {k} is empty")
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}", kv["date"]):
        raise Refused(f"{path}: date {kv['date']!r} is not YYYY-MM-DD")
    return kv


def check_decisions(path, segment, environ=None):
    """the record is valid, and the environment AGREES with it; nothing is set"""
    env = os.environ if environ is None else environ
    kv = read_decisions(path)
    if segment not in ("h16", "h5", "select"):
        raise Refused(f"unknown segment {segment!r}")
    av = env.get("S5N_ADAPTER_VALIDATED")
    if av is None or not av.strip():
        raise Refused("S5N_ADAPTER_VALIDATED is not set in the environment (decision S5-2-D2; this runner never sets it)")
    if av != kv["adapter_validated"]:
        raise Refused("S5N_ADAPTER_VALIDATED differs from adapter_validated of the decision record")
    if segment != "select":
        ed = env.get("S5_ENV_DECISION")
        if ed != kv["env_decision"]:
            raise Refused("S5_ENV_DECISION differs from env_decision of the decision record")
    return kv


def authorize(record, sig, allowed):
    """AG-1 signature check (form and environment are checked separately by check_decisions); returns the verifier's
    statement and the signer key fingerprint"""
    import shutil
    import subprocess
    for p, what in ((record, "decision record"), (sig, "signature"), (allowed, "allowed_signers")):
        if not p or not os.path.isfile(p):
            raise Refused(f"{what} {p!r} missing (AG-1: an unsigned record is never accepted)")
    lines = [ln for ln in open(allowed, encoding="utf-8").read().splitlines() if ln.strip() and not ln.lstrip().startswith("#")]
    if len(lines) != 1 or lines[0].split()[0] != AUTH_PRINCIPAL:
        raise Refused(f"allowed_signers must hold exactly one key, of the principal {AUTH_PRINCIPAL}")
    kg = shutil.which("ssh-keygen")
    if not kg:
        raise Refused("ssh-keygen not available: the signature cannot be verified")
    with open(record, "rb") as fh:
        r = subprocess.run([kg, "-Y", "verify", "-f", allowed, "-I", AUTH_PRINCIPAL, "-n", AUTH_NAMESPACE, "-s", sig],
                           stdin=fh, capture_output=True, text=True)
    if r.returncode != 0:
        raise Refused(f"the signature does not verify for {AUTH_PRINCIPAL} / {AUTH_NAMESPACE}: "
                      f"{(r.stderr or r.stdout).strip()[:200]}")
    key = " ".join(w for w in lines[0].split()[1:] if not w.startswith("namespaces="))
    fp = subprocess.run([kg, "-lf", "/dev/stdin"], input=key + "\n", capture_output=True, text=True).stdout.strip()
    return r.stdout.strip() or "Good signature", fp


def gate(mode):
    if mode not in MODES:
        raise Refused(f"mode {mode!r}: production or test")
    if mode == "production" and not AUTH_GATE_APPROVAL:
        raise Refused("production execution refused: the authorization gate AG-1 (signed decision record, principal "
                      f"{AUTH_PRINCIPAL}, namespace {AUTH_NAMESPACE}) is a proposal awaiting the maintainer's approval")
    return ("TEST MODE: synthetic execution; never evidence" if mode == "test"
            else f"production: AG-1 approved ({AUTH_GATE_APPROVAL})")


# ----------------------------------------------------------------------------------------- bracket records -----
def read_tsv(path):
    if not os.path.exists(path):
        return []
    lines = open(path, encoding="utf-8").read().splitlines()
    if not lines or lines[0] != TSV_HEADER:
        raise Refused(f"{path}: not a bracket record (header)")
    rows = []
    for i, ln in enumerate(lines[1:], 2):
        p = ln.split("\t")
        if len(p) != 7:
            raise Refused(f"{path}:{i}: {len(p)} fields, 7 expected")
        rows.append({"combo": p[0], "start": parse_factor(p[1]), "factor": parse_factor(p[2]), "outcome": p[3],
                     "config": p[4], "wrapper_rc": p[5], "digest": p[6]})
    return rows


def replay(rows, key, start):
    """the accepted state machine over the recorded rows of one combination; refuses an inconsistent record"""
    b = SEL.Bracket(key, start=start)
    for r in rows:
        if r["combo"] != key:
            continue
        if r["start"] != start:
            raise Refused(f"{key}: recorded start {r['start']} differs from the declared start {start}")
        if r["config"] != config_of(key, r["factor"]):
            raise Refused(f"{key}: recorded config {r['config']} is not the configuration of factor {r['factor']}")
        try:
            b.record(r["factor"], r["outcome"])
        except ValueError as ex:
            raise Refused(f"{key}: the recorded outcomes are not a valid bracket sequence: {ex}") from None
    return b


def key_of(cfg):
    m = re.fullmatch(r"M2S72-E0vN(H5)?-(q0|q0p|qdu|qde)-(one0|sym)-n(1|2|4|8)-f\w+", cfg or "")
    if not m:
        raise Refused(f"{cfg!r} is not an E0v-N configuration name")
    return f"{m.group(2)}/{m.group(3)}/{m.group(4)}/{5 if m.group(1) else 16}"


def start_factor(key, d5, h16_tsv=None):
    o, pl, n, h16 = parse_key(key)
    if h16 or d5 == "not-approved":
        return 1.0
    if d5 != "approved":
        raise Refused(f"S5-2-D5 value {d5!r}")
    if not h16_tsv:
        raise Refused("S5-2-D5 approved: the HARQ5 start needs the committed HARQ16 bracket record")
    k16 = combo_key(o, pl, n, True)
    b16 = replay(read_tsv(h16_tsv), k16, 1.0)
    lo, hi, st = b16.result()
    if lo is None:
        raise Refused(f"{k16}: no HARQ16 f_lo ({st}); the HARQ5 economy cannot start {key}")
    return lo


def classify_digest(path, cfg, wrapper_rc, sim_outcome):
    if sim_outcome != "OK":
        return "invalid", f"simulation outcome {sim_outcome}"
    if str(wrapper_rc) != "0":
        return "invalid", f"wrapper exit {wrapper_rc} (only PASS is a bracket result)"
    if not os.path.isfile(path):
        raise Refused(f"composed digest {path} missing")
    d = json.load(open(path, encoding="utf-8"))
    if d.get("schema") != "m2s72-s5n21-digest/1":
        raise Refused(f"{path}: schema {d.get('schema')!r}")
    if d.get("config") != cfg:
        raise Refused(f"{path}: digest of {d.get('config')!r}, not {cfg}")
    v = (d.get("correctness") or {}).get("verdict") or {}
    if v.get("status") != "PASS" or v.get("exit") != 0:
        raise Refused(f"{path}: verdict {v.get('status')!r} / exit {v.get('exit')!r} with wrapper rc 0")
    n = parse_key(key_of(cfg))[2]
    if d.get("numUe") != n:
        raise Refused(f"{path}: numUe {d.get('numUe')!r}, the configuration has N = {n}")
    want = {(r, "run") for r in RUN_ROWS} | {(r, f"UE {k}") for r in PER_UE_ROWS for k in range(n)}
    rows = (d.get("correctness") or {}).get("rows")
    if not isinstance(rows, list):
        raise Refused(f"{path}: correctness.rows missing")
    got = [(r.get("id"), r.get("subject")) for r in rows if isinstance(r, dict)]
    if len(got) != len(rows) or len(set(got)) != len(got) or set(got) != want:
        raise Refused(f"{path}: wrapper rows incomplete or unexpected: missing {sorted(want - set(got))}, "
                      f"unexpected {sorted(set(got) - want)}, duplicates {len(got) - len(set(got))}")
    bad = [(r["id"], r["subject"], r.get("status")) for r in rows if r.get("status") not in GATE_OK]
    if bad:
        raise Refused(f"{path}: verdict PASS with non-passing wrapper rows {bad}")
    per = (d.get("performance") or {}).get("per_ue")
    if not isinstance(per, list) or len(per) != n:
        raise Refused(f"{path}: performance.per_ue must have N = {n} entries")
    across = (d.get("performance") or {}).get("across")
    if not isinstance(across, dict):
        raise Refused(f"{path}: performance.across missing")
    for k in ("overloaded_ues", "overload_not_evaluable_ues", "starvation_ues"):
        if k not in across:
            raise Refused(f"{path}: performance.across.{k} missing")
    out = SEL.classify(across, True, "OK")
    why = (f"overloaded {across['overloaded_ues']}, not evaluable {across['overload_not_evaluable_ues']}, "
           f"starvation {dict((c, u) for c, u in across['starvation_ues'].items() if u)}")
    return out, why


def append_row(path, key, start, f, outcome, cfg, wrapper_rc, digest):
    rows = read_tsv(path)
    b = replay(rows, key, start)
    if outcome not in SEL.OUTCOMES:
        raise Refused(f"unknown outcome {outcome!r}")
    if cfg != config_of(key, f):
        raise Refused(f"{cfg} is not the configuration of {key} at factor {f}")
    if not re.fullmatch(r"[0-9a-f]{64}|-", digest):
        raise Refused(f"digest sha256 {digest!r}")
    try:
        b.record(f, outcome)
    except ValueError as ex:
        raise Refused(str(ex)) from None
    new = not os.path.exists(path)
    with open(path, "a", encoding="utf-8") as fh:
        if new:
            fh.write(TSV_HEADER + "\n")
        fh.write("\t".join([key, G5.G.flabel(start), G5.G.flabel(f), outcome, cfg, str(wrapper_rc), digest]) + "\n")
    LIB.durable([path])
    return b


def select(h16_tsv, h5_tsv, d5):
    """S-1 / S-2 over every combination of both segments; (record text, f_E1 or None). Every recorded start factor
    must be the declared one (B-1: 1.0, or the HARQ16 f_lo for HARQ5 when S5-2-D5 is approved)"""
    rows = {"h16": read_tsv(h16_tsv), "h5": read_tsv(h5_tsv)}
    brackets, lines = [], []
    for seg in ("h16", "h5"):
        for key, *_ in combos(seg):
            starts = {r["start"] for r in rows[seg] if r["combo"] == key}
            if not starts:
                raise Refused(f"{key}: no bracket record (every combination must be bracketed; nothing is inferred)")
            if len(starts) != 1:
                raise Refused(f"{key}: several start factors recorded")
            want = start_factor(key, d5, h16_tsv)
            if starts != {want}:
                raise Refused(f"{key}: recorded start {starts.pop()} is not the declared start {want} (S5-2-D5 {d5})")
            b = replay(rows[seg], key, want)
            if b.stop is None:
                raise Refused(f"{key}: bracket unfinished")
            lo, hi, st = b.result()
            lines.append(f"{key}\tstart {G5.G.flabel(b.start)}\truns {len(b.order)}\tf_lo {lo}\tf_hi {hi}\t{st}")
            brackets.append(b)
    keys = [b.combo for b in brackets]
    extra = sorted({r["combo"] for s in rows.values() for r in s} - set(keys))
    if extra:
        raise Refused(f"records for combinations outside the declared set: {extra}")
    sens = SEL.sensitivity(brackets)
    f, bind, why = SEL.select(brackets, 0.20)
    txt = ["M2-S7.2a E0v-N f_E1 selection (A3 protocol §6; m2s72_e1sel S-1 / S-2, unchanged)", "",
           f"inputs: {h16_tsv} sha256 {sha256(h16_tsv)}", f"        {h5_tsv} sha256 {sha256(h5_tsv)}", "",
           "brackets:"] + ["  " + x for x in lines] + ["", "sensitivity (S-2):"]
    for m, (fm, bm, wm) in sorted(sens.items()):
        txt.append(f"  m = {m:.2f}: f_E1 = {fm}  ({wm})")
    txt += ["", f"declared margin m = 0.20 (S5-2-D4): f_E1 = {f}", f"reason: {why}",
            "", "f_E1 is a candidate until the verification runs V-1 .. V-4 (protocol §6.3) pass; E1 does not start before"]
    return "\n".join(txt) + "\n", f


# --------------------------------------------------------------------------------------------- command -----
def sim_argv(nascTime, simu5g, inet, cfg, result_dir):
    if cfg not in G5.matrix() or G5.matrix()[cfg][7] != "N":
        raise Refused(f"{cfg} is not an E0v-N configuration")
    for p in (nascTime, simu5g, inet, result_dir):
        if not os.path.isabs(p):
            raise Refused(f"{p}: absolute paths only")
    return ["opp_run", "-l", f"{nascTime}/src/nasctime/m2/nasctime_m2", "-l", f"{simu5g}/src/simu5g",
            "-n", f"{nascTime}/simulations:{nascTime}/src:{simu5g}/src:{inet}/src", "-x", "nasctime.nodes", "-u", "Cmdenv",
            "-f", "m2s72s5.ini", "-c", cfg, "--repeat=1", "-r", "0", f"--result-dir={result_dir}",
            "--cmdenv-express-mode=false", "--fingerprint=0000-0000/tplx"]


# ------------------------------------------------------------------------------------------------- main -----
def main(argv):
    try:
        a = argv[1:]
        if len(a) == 2 and a[0] == "combos":
            for key, o, pl, n, h16 in combos(a[1]):
                print(f"{key}\t{config_of(key, 1.0)}")
            return 0
        if len(a) == 2 and a[0] == "configs":
            print("\n".join(all_configs(a[1])))
            return 0
        if len(a) == 2 and a[0] == "pins":
            probs = check_pins(a[1])
            for p in probs:
                print(f"PIN: {p}")
            print("pins: OK" if not probs else f"pins: REFUSED ({len(probs)})")
            return 0 if not probs else 1
        if len(a) == 3 and a[0] == "decisions":
            kv = check_decisions(a[1], a[2])
            print(f"decisions: OK (sha256 {sha256(a[1])}; S5-2-D5 {kv['S5-2-D5']}; ac5 {kv['ac5_record']}; "
                  f"ac6 {kv['ac6_record']})")
            return 0
        if a and a[0] == "start" and len(a) in (3, 4):
            print(G5.G.flabel(start_factor(a[1], a[2], a[3] if len(a) == 4 else None)))
            return 0
        if len(a) == 4 and a[0] == "next":
            b = replay(read_tsv(a[1]), a[2], parse_factor(a[3]))
            f = b.next_factor()
            if f is None:
                lo, hi, st = b.result()
                print(f"DONE\t{b.stop}\t{lo}\t{hi}\t{st}")
            else:
                print(f"RUN\t{G5.G.flabel(f)}\t{config_of(a[2], f)}")
            return 0
        if len(a) == 5 and a[0] == "outcome":
            o, why = classify_digest(a[1], a[2], a[3], a[4])
            print(f"{o}\t{why}")
            return 0
        if len(a) == 9 and a[0] == "record":
            b = append_row(a[1], a[2], parse_factor(a[3]), parse_factor(a[4]), a[5], a[6], a[7], a[8])
            print(f"recorded {a[2]} f {a[4]} {a[5]}; next {b.next_factor()}; stop {b.stop}")
            return 0
        if len(a) == 6 and a[0] == "cmd":
            sys.stdout.write("\0".join(sim_argv(*a[1:])) + "\0")
            return 0
        if len(a) == 4 and a[0] == "authorize":
            st, fp = authorize(a[1], a[2], a[3])
            print(f"authorization: {st}; signer key {fp}; record sha256 {sha256(a[1])}")
            return 0
        if len(a) == 2 and a[0] == "gate":
            print(gate(a[1]))
            return 0
        if len(a) == 8 and a[0] == "select":
            g = gate(a[1])
            kv = check_decisions(a[2], "select")
            st, fp = authorize(a[2], a[3], a[4])
            out = a[7]
            if os.path.lexists(out):
                raise Refused(f"{out} exists (records are never overwritten)")
            txt, f = select(a[5], a[6], kv["S5-2-D5"])
            txt = txt.replace("\nbrackets:", f"\ndecision record: {a[2]} sha256 {sha256(a[2])}\nauthorization: {st}; "
                              f"signer key {fp}\nmode: {g}\n\nbrackets:", 1)
            with open(out, "w", encoding="utf-8") as fh:
                fh.write(txt)
            LIB.durable([out])
            print(txt.rstrip())
            return 0 if f is not None else EXIT_STOP
    except Refused as ex:
        print(f"REFUSED: {ex}")
        return 2 if (argv[1:2] in (["next"], ["record"], ["outcome"], ["start"], ["cmd"])) else 1
    except Exception as ex:   # noqa: BLE001  (fail closed: never a result)
        print(f"ERROR {type(ex).__name__}: {ex}")
        return 2
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
