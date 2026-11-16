#!/usr/bin/env python3
"""A2-D2-F3 Phase 1: fail-closed extraction of the REAL first-chain fixture from the sealed A2-V1 run.

    python3 -I -B m2s72_a21_fixture.py extract --results-root <R> --seal-sha256 <hex> --out <fresh dir> [--max-bytes N]

Reads only. Never writes, renames, chmods or deletes anything under <R>; writes only into <out>, which must not exist
and must not lie inside <R>. One attempt: no retry, no overwrite, no fallback. Python standard library only; this
file imports nothing from the repository, so it can be audited on its own.

Chain of custody (each step must pass before the next starts; any failure stops with a non-zero exit):
  E-0  preconditions: <R>/a2-nack-1 and its seal <R>/a2-nack-1-evidence.sha256 exist (regular files / directories,
       no symlinks); <out> does not exist, its parent does, and it is not inside <R>.                     (exit 10)
  E-1  the seal file's own sha256 equals --seal-sha256 (the value recorded when the run was sealed).          (exit 11)
  E-2  every seal entry verifies; the paths are relative, under a2-nack-1/, free of '..'; the files now present
       under a2-nack-1/{p0,records,eval} are exactly the sealed ones (nothing added, nothing missing).         (exit 11)
  E-3  the raw-output manifest is located FROM THE SEAL (exactly one a2-nack-1/records/*.manifest.sha256; its name
       gives the configuration, which must be the declared one); every manifest entry verifies (size, sha256),
       lies inside <R>/a2-nack-1/runs and is a regular file; the log is the one manifest entry named
       run-<cfg>.log.gz and the scalar file the one entry ending in .sca. No path is guessed.                  (exit 11)
  E-4  the UE MAC node ids (scalar 'par ... ue[k].cellularNic.nrMac macNodeId') equal the declared ones.      (exit 11)
  E-5  extraction: the decompressed log is copied byte for byte, in its order, from its first line up to (not
       including) the first time-stamped line later than the TTI of the BOUNDARY LOOP, the first gNB main loop
       ("-----ENB MAIN LOOP -----") starting after the final ACK (384 ms). That TTI must contain the loop's
       "--- END ENB MAIN LOOP ---". Nothing is filtered, reordered or rewritten: every module's lines are kept.
       The cut is at a TTI boundary (the way a simulated-time limit ends a log): the feedback events a TTI
       processes after its main loop stay with their TTI. Stops on: time stamps decreasing, no boundary loop
       before 384 + 10 ms, end of the log before the boundary, more than --max-bytes decompressed.            (exit 12)
  E-6  the declared facts of the chain are found, by literal gNB MAC text, in the fixture (§ FACTS below).    (exit 13)
  E-7  E-1..E-3 are repeated after the extraction and must give the same result (seal, records, manifest).    (exit 14)
Only then are the final names written: the fixture, its sha256 pin, the metadata and SHA256SUMS of <out>.
A stopped attempt leaves FAILED.txt (the exit code and the reason) and keeps whatever was written, under
non-final names (*.partial); it is never cleaned up and never retried by this tool.
"""
import gzip
import hashlib
import json
import os
import platform
import re
import sys
import time

VERSION = "A2-D2-F3 extractor 1"
RUN = "a2-nack-1"
CFG = "M2S72-E0vN-q0-one0-n2-f1_A2V1"
GNB = "M2S72Bridge.gnb1.cellularNic.mac"
SCHED = GNB + ".schedulerDl"
NET = "M2S72Bridge"
FACTS = {"mac_pdu": 145933, "handle": 54326, "node": 2050, "process": 0, "codeword": 0,
         "tx_ms": [361, 367, 373, 379], "nack_ms": [366, 372, 378], "ack_ms": 384,
         "node_ids": {0: 2049, 1: 2050}}
BOUNDARY_SLACK_MS = 10
MAX_BYTES = 256 * 2 ** 20
FIX = "a2v1-first-chain.log.gz"
META = "a2v1-first-chain.meta.json"
ML_START, ML_END = "-----ENB MAIN LOOP -----", "--- END ENB MAIN LOOP ---"
S, MS = 10 ** 12, 10 ** 9

R_SEAL = re.compile(r"^([0-9a-f]{64})  (.+)$")
R_MAN = re.compile(r"^([0-9a-f]{64})  (\d+)  (/.+)$")
R_PAR = re.compile(r"^par\s+(\S+)\s+macNodeId\s+(\S+)\s*$")
R_INSERT = re.compile(r"H-ARQ TX: new pdu \(id (\d+) \) inserted into process (\d+) codeword id: (\d+) for node with id (\d+)")
R_EXTRACT = re.compile(r"H-ARQ TX: pdu \(id (\d+) \) extracted from process (\d+) codeword (\d+) for node with id (\d+)")
R_URTX = re.compile(r"H-ARQ process\s+(\d+) Codeword (\d+) PDU (\d+) set for RTX")
R_UDISC = re.compile(r"H-ARQ process\s+(\d+) Codeword (\d+) PDU (\d+) discarded")
R_FB = re.compile(r"H-ARQ TX: feedback received for process (\d+) codeword (\d+) result is (ACK|NACK)")
R_SEL = re.compile(r"H-ARQ TX: process (\d+) has been selected for retransmission")
R_UERX = re.compile(r"H-ARQ RX: new PDU \(id (\d+) \) inserted into process (\d+)")


class Stop(Exception):
    def __init__(self, code, msg):
        super().__init__(msg)
        self.code = code


def t_ps(s):
    a, _, b = s.partition(".")
    if not a.isdigit() or (b and not b.isdigit()) or len(b) > 12:
        raise ValueError(s)
    return int(a) * S + int((b + "0" * 12)[:12])


def sha256_file(path):
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for blk in iter(lambda: fh.read(1 << 20), b""):
            h.update(blk)
    return h.hexdigest()


def inside(path, root):
    p, r = os.path.realpath(path), os.path.realpath(root)
    return p == r or p.startswith(r.rstrip(os.sep) + os.sep)


def regular(path):
    """a regular file reached without any symlink component below the results root"""
    return os.path.isfile(path) and not os.path.islink(path)


# --------------------------------------------------------------------------------------------- E-1 .. E-3 -------
def verify_sources(R, seal_sha, log):
    seal = os.path.join(R, f"{RUN}-evidence.sha256")
    if not regular(seal):
        raise Stop(11, f"seal {seal} is not a regular file")
    got = sha256_file(seal)
    if got != seal_sha:
        raise Stop(11, f"E-1 seal sha256 {got} != declared {seal_sha}")
    log(f"E-1 PASS seal {seal} sha256 {got}")
    entries = {}
    with open(seal, "r", encoding="utf-8", newline="") as fh:
        for n, line in enumerate(fh, 1):
            line = line.rstrip("\n")
            m = R_SEAL.match(line)
            if not m:
                raise Stop(11, f"E-2 seal line {n} is not '<sha256>  <path>': {line[:120]!r}")
            h, rel = m.groups()
            parts = rel.split("/")
            if rel.startswith("/") or ".." in parts or parts[0] != RUN or len(parts) < 3 or parts[1] not in ("p0", "records", "eval"):
                raise Stop(11, f"E-2 seal line {n}: path {rel!r} is not a plain path under {RUN}/{{p0,records,eval}}")
            if rel in entries:
                raise Stop(11, f"E-2 seal line {n}: duplicate path {rel}")
            entries[rel] = h
    if not entries:
        raise Stop(11, "E-2 the seal lists no file")
    bad = []
    for rel, h in sorted(entries.items()):
        p = os.path.join(R, rel)
        if not regular(p) or not inside(p, os.path.join(R, RUN)):
            bad.append(f"{rel}: missing, not regular or outside the run")
        elif sha256_file(p) != h:
            bad.append(f"{rel}: content differs")
    present = set()
    for sub in ("p0", "records", "eval"):
        top = os.path.join(R, RUN, sub)
        if os.path.islink(top):
            bad.append(f"{RUN}/{sub} is a symlink")
            continue
        for d, dirs, files in os.walk(top):
            for f in files + [x for x in dirs if os.path.islink(os.path.join(d, x))]:
                present.add(os.path.relpath(os.path.join(d, f), R).replace(os.sep, "/"))
    extra = sorted(present - set(entries))
    if extra:
        bad.append(f"files not in the seal: {extra[:5]}")
    if bad:
        raise Stop(11, f"E-2 seal does not verify: {bad[:5]}")
    log(f"E-2 PASS {len(entries)} sealed files verify; no unsealed file under {RUN}/{{p0,records,eval}}")
    mans = [r for r in entries if re.fullmatch(rf"{re.escape(RUN)}/records/[^/]+\.manifest\.sha256", r)]
    if len(mans) != 1:
        raise Stop(11, f"E-3 the seal lists {len(mans)} raw-output manifests (expected exactly 1): {mans}")
    cfg = os.path.basename(mans[0])[:-len(".manifest.sha256")]
    if cfg != CFG:
        raise Stop(11, f"E-3 manifest configuration {cfg!r} is not the declared {CFG!r}")
    man_path = os.path.join(R, mans[0])
    runs = os.path.join(R, RUN, "runs")
    rows, bad = [], []
    with open(man_path, "r", encoding="utf-8", newline="") as fh:
        for n, line in enumerate(fh, 1):
            m = R_MAN.match(line.rstrip("\n"))
            if not m:
                raise Stop(11, f"E-3 manifest line {n} is not '<sha256>  <size>  <absolute path>': {line[:120]!r}")
            rows.append((m.group(1), int(m.group(2)), m.group(3)))
    if not rows:
        raise Stop(11, "E-3 the manifest lists no file")
    for h, size, p in rows:
        if not inside(p, runs):
            bad.append(f"{p}: outside {runs}")
        elif not regular(p):
            bad.append(f"{p}: missing or not a regular file")
        elif os.path.getsize(p) != size or sha256_file(p) != h:
            bad.append(f"{p}: size or content differs")
    if bad:
        raise Stop(11, f"E-3 manifest does not verify: {bad[:5]}")
    logs = [r for r in rows if os.path.basename(r[2]) == f"run-{cfg}.log.gz"]
    scas = [r for r in rows if r[2].endswith(".sca")]
    if len(logs) != 1 or len(scas) != 1:
        raise Stop(11, f"E-3 the manifest names {len(logs)} run-{cfg}.log.gz and {len(scas)} .sca files (expected 1 and 1)")
    log(f"E-3 PASS manifest {mans[0]} ({len(rows)} raw files verify, all inside {runs}); log {logs[0][2]}; scalars {scas[0][2]}")
    verdicts = {}
    for rel in sorted(entries):
        if os.path.basename(rel) == "wrapper-verdict.txt":
            with open(os.path.join(R, rel), "r", encoding="utf-8", errors="replace") as fh:
                verdicts[rel] = fh.read().strip()[:500]
    return {"seal": seal, "seal_sha256": got, "seal_files": len(entries), "seal_entries": entries,
            "manifest": man_path, "manifest_sha256": entries[mans[0]], "manifest_rows": rows, "cfg": cfg,
            "log": logs[0][2], "log_sha256": logs[0][0], "log_bytes": logs[0][1],
            "sca": scas[0][2], "sca_sha256": scas[0][0], "wrapper_verdicts_read_only": verdicts}


def node_ids(sca, log):
    ids = {}
    with open(sca, "r", encoding="utf-8", errors="replace") as fh:
        for line in fh:
            m = R_PAR.match(line)
            if not m:
                continue
            km = re.fullmatch(rf"{re.escape(NET)}\.ue\[(\d+)\]\.cellularNic\.nrMac", m.group(1))
            if km:
                k = int(km.group(1))
                if k in ids:
                    raise Stop(11, f"E-4 two macNodeId lines for ue[{k}]")
                ids[k] = int(float(m.group(2)))
    if ids != FACTS["node_ids"]:
        raise Stop(11, f"E-4 UE MAC node ids {ids} != declared {FACTS['node_ids']}")
    log(f"E-4 PASS UE MAC node ids {ids}")
    return ids


# ---------------------------------------------------------------------------------------------------- E-5 -------
def extract(src, dst_partial, max_bytes, log):
    """copies the prefix byte for byte; returns the extraction record. Parsing is for the cut and the checks only."""
    ack_ps = FACTS["ack_ms"] * MS
    limit_ps = (FACTS["ack_ms"] + BOUNDARY_SLACK_MS) * MS
    raw = hashlib.sha256()
    n_lines = n_bytes = 0
    t_prev = -1
    loop_t = None            # TTI (ps) of the boundary loop
    loop_end_seen = False
    stop_line = None
    first = last = None
    obs = {"insert": [], "extract": [], "urtx": [], "udisc": [], "fb": [], "sel": [], "uerx": [],
           "ml_start": 0, "ml_end": 0, "sched_lines": 0, "rtxacid_lines": 0, "untimed_lines": 0, "modules": {}}
    open_loop = False
    with gzip.open(src, "rb") as fin, open(dst_partial, "xb") as raw_out, \
            gzip.GzipFile(filename="", mode="wb", fileobj=raw_out, mtime=0, compresslevel=9) as out:
        for b in fin:
            text = b.decode("utf-8", errors="replace").rstrip("\r\n")
            parts = text.split("|", 2)
            t = None
            if len(parts) == 3 and parts[0][:1].isdigit():
                try:
                    t = t_ps(parts[0])
                except ValueError:
                    raise Stop(12, f"E-5 line {n_lines + 1}: unparsable time stamp {parts[0][:40]!r}")
            if t is not None:
                if t < t_prev:
                    raise Stop(12, f"E-5 line {n_lines + 1}: time stamp {parts[0]} earlier than the previous one")
                t_prev = t
                if loop_t is not None and t > loop_t:
                    stop_line = text[:300]
                    break                                   # the first line after the boundary TTI: not copied
                if loop_t is None and t > limit_ps:
                    raise Stop(12, f"E-5 no gNB main loop starts in ({FACTS['ack_ms']}, {FACTS['ack_ms'] + BOUNDARY_SLACK_MS}] ms "
                                   f"(line {n_lines + 1} at {parts[0]}): no boundary, nothing extracted")
            n_bytes += len(b)
            if n_bytes > max_bytes:
                raise Stop(12, f"E-5 the prefix exceeds --max-bytes {max_bytes} (decompressed) before the boundary")
            out.write(b)
            raw.update(b)
            n_lines += 1
            first = first or text[:300]
            last = text[:300]
            if t is None:
                obs["untimed_lines"] += 1
                continue
            mod, msg = parts[1], parts[2]
            obs["modules"][mod] = obs["modules"].get(mod, 0) + 1
            ms = t // MS
            if mod == SCHED:
                obs["sched_lines"] += 1
                if "rtxAcid" in msg:
                    obs["rtxacid_lines"] += 1
            if R_UERX.search(msg):
                m = R_UERX.search(msg)
                obs["uerx"].append((mod, ms, int(m.group(1)), int(m.group(2))))
            if mod != GNB:
                continue
            if ML_START in msg:
                if open_loop:
                    raise Stop(12, f"E-5 line {n_lines}: a gNB main loop starts inside another one")
                open_loop = True
                obs["ml_start"] += 1
                if loop_t is None and t > ack_ps:
                    loop_t = t
            elif ML_END in msg:
                if not open_loop:
                    raise Stop(12, f"E-5 line {n_lines}: a gNB main loop ends without a start")
                open_loop = False
                obs["ml_end"] += 1
                if loop_t is not None and t == loop_t:
                    loop_end_seen = True
            for key, rx in (("insert", R_INSERT), ("extract", R_EXTRACT), ("urtx", R_URTX), ("udisc", R_UDISC),
                            ("fb", R_FB), ("sel", R_SEL)):
                m = rx.search(msg)
                if m:
                    obs[key].append((ms,) + tuple(x if x in ("ACK", "NACK") else int(x) for x in m.groups()))
        else:
            raise Stop(12, "E-5 the log ends before the boundary TTI is complete (no later time-stamped line)")
    if loop_t is None or not loop_end_seen or open_loop:
        raise Stop(12, f"E-5 the boundary loop is incomplete (start {loop_t}, end seen {loop_end_seen}, open {open_loop})")
    log(f"E-5 PASS {n_lines} lines / {n_bytes} B copied; boundary loop at {loop_t // MS} ms; cut before {stop_line[:80]!r}")
    return {"lines": n_lines, "bytes": n_bytes, "decompressed_sha256": raw.hexdigest(), "boundary_loop_ms": loop_t // MS,
            "boundary_rule": "up to (excluding) the first time-stamped line later than the TTI of the first gNB main loop "
                             f"starting after {FACTS['ack_ms']} ms; that TTI holds the loop's end marker",
            "first_line": first, "last_line": last, "first_excluded_line": stop_line, "obs": obs}


# ---------------------------------------------------------------------------------------------------- E-6 -------
def check_facts(obs, log):
    f, bad = FACTS, []
    pid, h, nd, p, cw = f["mac_pdu"], f["handle"], f["node"], f["process"], f["codeword"]
    ins = [x for x in obs["insert"] if x[1] == pid]
    if [(x[0], x[2], x[3], x[4]) for x in ins] != [(f["tx_ms"][0], p, cw, nd)]:
        bad.append(f"F-1 insert of MAC PDU {pid}: {ins} (declared one, at {f['tx_ms'][0]} ms, process {p}, codeword {cw}, node {nd})")
    ext = [x for x in obs["extract"] if x[1] == pid]
    if [x[0] for x in ext] != f["tx_ms"] or any((x[2], x[3], x[4]) != (p, cw, nd) for x in ext):
        bad.append(f"F-2 transmissions of MAC PDU {pid}: {ext} (declared at {f['tx_ms']} ms)")
    ur = [x for x in obs["urtx"] if x[3] == h]
    if [x[0] for x in ur] != f["nack_ms"] or any((x[1], x[2]) != (p, cw) for x in ur):
        bad.append(f"F-3 'PDU {h} set for RTX' lines: {ur} (declared at {f['nack_ms']} ms)")
    ud = [x for x in obs["udisc"] if x[3] == h]
    if ud:
        bad.append(f"F-3 'PDU {h} discarded' lines: {ud} (declared none)")
    for t in f["nack_ms"]:
        if not any(x[0] == t and (x[1], x[2], x[3]) == (p, cw, "NACK") for x in obs["fb"]):
            bad.append(f"F-4 no gNB NACK feedback on process {p} at {t} ms")
    if not any(x[0] == f["ack_ms"] and (x[1], x[2], x[3]) == (p, cw, "ACK") for x in obs["fb"]):
        bad.append(f"F-4 no gNB ACK feedback on process {p} at {f['ack_ms']} ms")
    for t in f["tx_ms"][1:]:
        if not any(x[0] == t and x[1] == p for x in obs["sel"]):
            bad.append(f"F-5 no 'process {p} has been selected for retransmission' at {t} ms")
    if obs["ml_start"] != obs["ml_end"] or obs["ml_start"] == 0:
        bad.append(f"F-6 gNB main-loop markers unbalanced or absent ({obs['ml_start']} / {obs['ml_end']})")
    if bad:
        raise Stop(13, "E-6 declared facts not found: " + " | ".join(bad))
    log("E-6 PASS declared facts F-1..F-6 found by literal gNB MAC text")
    return {"F-1": ins, "F-2": ext, "F-3": ur, "F-4": [x for x in obs["fb"] if x[1] == p and x[0] in f["nack_ms"] + [f["ack_ms"]]],
            "F-5": [x for x in obs["sel"] if x[1] == p and x[0] in f["tx_ms"][1:]],
            "F-6": (obs["ml_start"], obs["ml_end"]),
            "recorded, not asserted": {
                "scheduler-module lines (mac.schedulerDl)": obs["sched_lines"], "rtxAcid lines": obs["rtxacid_lines"],
                f"UE-side receptions of MAC PDU {pid}": [x for x in obs["uerx"] if x[2] == pid],
                f"insert / extract lines whose MAC id equals the handle {h}": [x for x in obs["insert"] + obs["extract"] if x[1] == h],
                "untimed lines": obs["untimed_lines"], "lines per module": obs["modules"]}}


# ---------------------------------------------------------------------------------------------------- main -------
def run(argv, _hook=None):
    """_hook(stage): test-only injection point (never set from the command line)"""
    import argparse
    ap = argparse.ArgumentParser(prog="m2s72_a21_fixture.py")
    sp = ap.add_subparsers(dest="cmd", required=True)
    ex = sp.add_parser("extract")
    ex.add_argument("--results-root", required=True)
    ex.add_argument("--seal-sha256", required=True)
    ex.add_argument("--out", required=True)
    ex.add_argument("--max-bytes", type=int, default=MAX_BYTES)
    a = ap.parse_args(argv)
    R, out = a.results_root, a.out
    if not re.fullmatch(r"[0-9a-f]{64}", a.seal_sha256):
        print("E-0 --seal-sha256 must be 64 lower-case hex digits (nothing written)", file=sys.stderr)
        return 10
    pre = []
    if not os.path.isdir(R) or os.path.islink(R):
        pre.append(f"results root {R} is not a directory")
    elif not os.path.isdir(os.path.join(R, RUN)) or os.path.islink(os.path.join(R, RUN)):
        pre.append(f"{R}/{RUN} is not a directory")
    if os.path.lexists(out):
        pre.append(f"output {out} exists (never reused, never overwritten)")
    elif not os.path.isdir(os.path.dirname(os.path.abspath(out))):
        pre.append(f"the parent of {out} does not exist")
    elif os.path.isdir(R) and inside(os.path.dirname(os.path.abspath(out)), R):
        pre.append(f"output {out} lies inside the results root {R}")
    if pre:
        print("E-0 STOP (nothing written): " + "; ".join(pre), file=sys.stderr)
        return 10
    os.mkdir(out)
    steps = open(os.path.join(out, "steps.txt"), "x", encoding="utf-8")

    def log(msg):
        line = f"{time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime())} {msg}"
        print(line)
        steps.write(line + "\n")
        steps.flush()
    log(f"{VERSION}; script sha256 {sha256_file(os.path.abspath(__file__))}; python {platform.python_version()}; "
        f"{platform.platform()}; results root {os.path.realpath(R)}; out {os.path.realpath(out)}")
    log(f"E-0 PASS preconditions; declared facts {json.dumps(FACTS, sort_keys=True)}")
    partial = os.path.join(out, FIX + ".partial")
    try:
        src = verify_sources(R, a.seal_sha256, log)
        ids = node_ids(src["sca"], log)
        if _hook:
            _hook("before-extract")
        ext = extract(src["log"], partial, a.max_bytes, log)
        facts = check_facts(ext.pop("obs"), log)
        if _hook:
            _hook("before-reverify")
        try:
            again = verify_sources(R, a.seal_sha256, lambda m: log(m.replace(" PASS", " PASS (again)", 1)))
        except Stop as st:
            raise Stop(14, f"E-7 after the extraction: {st}")
        same = all(src[k] == again[k] for k in ("seal_sha256", "seal_entries", "manifest_rows", "log", "log_sha256", "sca", "sca_sha256"))
        if not same:
            raise Stop(14, "E-7 the sources differ between before and after the extraction")
        log("E-7 PASS seal, records and manifest unchanged by the extraction")
    except Stop as st:
        code = st.code
        log(f"STOP exit {code}: {st}")
        with open(os.path.join(out, "FAILED.txt"), "x", encoding="utf-8") as fh:
            fh.write(f"exit {code}\n{st}\nNothing was retried or cleaned up; partial outputs keep the .partial name.\n")
        steps.close()
        return code
    os.rename(partial, os.path.join(out, FIX))
    fix_sha = sha256_file(os.path.join(out, FIX))
    with open(os.path.join(out, FIX + ".sha256"), "x", encoding="utf-8") as fh:
        fh.write(f"{fix_sha}  {FIX}\n")
    src.pop("seal_entries")
    meta = {"version": VERSION, "run": RUN, "cfg": src["cfg"], "node_ids": {str(k): v for k, v in ids.items()},
            "facts": FACTS, "fixture": FIX, "fixture_sha256": fix_sha, "extraction": ext, "facts_found": facts,
            "sources": {k: v for k, v in src.items() if k != "manifest_rows"}, "manifest_files": len(src["manifest_rows"]),
            "script_sha256": sha256_file(os.path.abspath(__file__)), "python": platform.python_version(),
            "utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())}
    with open(os.path.join(out, META), "x", encoding="utf-8") as fh:
        json.dump(meta, fh, indent=1, sort_keys=True, default=list)
        fh.write("\n")
    log(f"DONE fixture {FIX} sha256 {fix_sha}; {ext['lines']} lines; boundary loop {ext['boundary_loop_ms']} ms")
    steps.close()
    names = sorted(x for x in os.listdir(out) if x != "SHA256SUMS")
    with open(os.path.join(out, "SHA256SUMS"), "x", encoding="utf-8") as fh:
        for x in names:
            fh.write(f"{sha256_file(os.path.join(out, x))}  {x}\n")
    return 0


if __name__ == "__main__":
    sys.exit(run(sys.argv[1:]))
