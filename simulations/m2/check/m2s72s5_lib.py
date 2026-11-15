#!/usr/bin/env python3
"""M2-S7.2a Stage 5 on Simu5G 1.8.1 (S5-1): per-run evidence lifecycle (plan rev. 1 §4, RD-5) and run-outcome
classification (G-4). Used by m2s72s5.sh; every function is also tested by test_m2s72s5.py.

    m2s72s5_lib.py classify <rc> <run log (.gz or plain)>          -> "OUTCOME<TAB>detail", exit 0
    m2s72s5_lib.py space <dir> <est run B> <est twin B>             -> required / free / verdict, exit 0 OK, 3 STOP
    m2s72s5_lib.py manifest <out file> <path> [<path> ...]          -> sha256 + size of every file (sorted), fsync'd
    m2s72s5_lib.py verify-manifest <manifest>                       -> every file present and equal, exit 0 / 1
    m2s72s5_lib.py retain <manifest> <run dir> [<run log>]          -> gzip -n every listed file in place, verify each
                                                                       decompresses to its manifest hash, exit 0 / 1
    m2s72s5_lib.py committed <repo> <path in repo> [...] -- <local file> [...]
                                                                    -> exit 0 iff every local file equals the blob of the
                                                                       same-index path in the repo's HEAD commit
    m2s72s5_lib.py durable <file> [...]                             -> fsync the files and their directories

Outcome classes (declared in the E0v protocol; Simu5G 1.8.1 source, tag v1.8.1):
  OK         rc 0 and no runtime error in the log
  SIM-ABORT  rc != 0 and the log carries one of the runtime errors that Simu5G 1.8.1 throws where 1.8.0 lost data
             silently: "macPduMake(): no free H-ARQ process for the [UL ]MAC PDU" (LteMacEnb.cc:586, LteMacUe.cc:676; the
             UE info line "no free H-ARQ process for the grant ..., the grant is not used" is NOT an abort) or "is marked inactive with"
             (LteSchedulerEnb.cc:472). The run is not a result; the batch stops; its outputs are kept (tier B)
  TIMEOUT    rc 124 (the runner's run-time limit)
  ERROR      any other rc != 0, or rc 0 with an "Error" / "<!> Error" line (fail closed)
"""
import gzip
import hashlib
import os
import re
import shutil
import subprocess
import sys

SIM_ABORT = (
    # the exact throw texts; NOT the UE info line "... no free H-ARQ process for the grant on carrier [..], the grant is
    # not used" (LteMacUe / NrMacUe::handleSelfMessage), which is normal 1.8.1 behaviour and is measured (RD-1)
    (re.compile(r"macPduMake\(\): no free H-ARQ process for the (?:UL )?MAC PDU"),
     "1.8.1 H-ARQ: MAC PDU without a free H-ARQ process (LteMacEnb.cc:586 / LteMacUe.cc:676)"),
    (re.compile(r"is marked inactive with \d+ bytes in its buffer"), "1.8.1 scheduler: connection inactive with data (LteSchedulerEnb.cc:472)"),
)
ERR_LINE = re.compile(r"^(<!> Error|Error)\b|cRuntimeError", re.M)
GB = 1 << 30
CHECKER_TMP = 1 * GB       # declared (plan rev. 1 §4.1): checker temporaries
MARGIN = 2 * GB            # declared margin


def _read(path, limit=None):
    op = gzip.open if path.endswith(".gz") else open
    with op(path, "rt", errors="replace") as fh:
        if limit is None:
            return fh.read()
        # runtime errors are printed at the end of the run: keep the head and the tail
        data = fh.read()
        return data if len(data) <= 2 * limit else data[:limit] + "\n...\n" + data[-limit:]


def _line_at(text, i):
    end = text.find("\n", i)
    return text[text.rfind("\n", 0, i) + 1:end if end >= 0 else len(text)].strip()[:300]


def classify(rc, log_text):
    """(outcome, detail) for one run: rc of the simulation process, full stdout/stderr text"""
    rc = int(rc)
    for pat, what in SIM_ABORT:
        m = pat.search(log_text)
        if m:
            end = log_text.find("\n", m.end())
            line = log_text[log_text.rfind("\n", 0, m.start()) + 1:end if end >= 0 else len(log_text)]
            if rc == 0:   # an abort text with rc 0 cannot be a completed run: fail closed
                return "ERROR", f"abort text with rc 0: {line.strip()[:300]}"
            return "SIM-ABORT", f"{what}: {line.strip()[:300]}"
    if rc == 124:
        return "TIMEOUT", "run-time limit reached (rc 124)"
    if rc != 0:
        m = ERR_LINE.search(log_text)
        return "ERROR", f"rc {rc}" + (f": {_line_at(log_text, m.start())}" if m else "")
    m = ERR_LINE.search(log_text)
    if m:
        return "ERROR", f"rc 0 with an error line: {_line_at(log_text, m.start())}"
    return "OK", "rc 0"


def space_rule(free_b, est_run_b, est_twin_b):
    """plan rev. 1 §4.1 per-run start rule: free >= 1.5 x run + twin + checker temporaries + margin"""
    req = int(1.5 * est_run_b) + int(est_twin_b) + CHECKER_TMP + MARGIN
    return free_b >= req, req


def sha256_file(path, gz=False):
    h = hashlib.sha256()
    op = gzip.open if gz else open
    with op(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def files_under(paths):
    out = []
    for p in paths:
        if os.path.isdir(p):
            for r, _, fs in os.walk(p):
                out += [os.path.join(r, f) for f in fs]
        elif os.path.exists(p):
            out.append(p)
        # a path that does not exist (e.g. no result directory after an early abort) contributes no file; the run log
        # always exists, and a manifest of nothing is refused below
    return sorted(set(os.path.abspath(x) for x in out))


def durable(paths):
    for p in paths:
        fd = os.open(p, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)
        d = os.open(os.path.dirname(os.path.abspath(p)), os.O_RDONLY)
        try:
            os.fsync(d)
        finally:
            os.close(d)


def manifest(out, paths):
    """sha256 and size of every file under paths; lines 'sha256  size  absolute path'; written and fsync'd before
    anything listed may be deleted. Returns the manifest's own sha256."""
    fs = files_under(paths)
    if not fs:
        raise ValueError("manifest of nothing")
    lines = [f"{sha256_file(f)}  {os.path.getsize(f)}  {f}" for f in fs]
    tmp = out + ".tmp"
    with open(tmp, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    os.replace(tmp, out)
    durable([out])
    return sha256_file(out), len(lines)


def read_manifest(path):
    out = []
    for line in open(path):
        h, size, p = line.rstrip("\n").split("  ", 2)
        out.append((h, int(size), p))
    return out


def verify_manifest(path):
    probs = []
    for h, size, p in read_manifest(path):
        if os.path.exists(p):
            if os.path.getsize(p) != size or sha256_file(p) != h:
                probs.append(f"{p}: content differs")
        elif os.path.exists(p + ".gz"):
            if sha256_file(p + ".gz", gz=True) != h:
                probs.append(f"{p}.gz: decompressed content differs")
        else:
            probs.append(f"{p}: missing")
    return not probs, probs


def retain(manifest_path):
    """tier B: gzip -n every manifest file in place (already .gz files are kept as they are), then check that every
    .gz decompresses to its manifest hash; the original is removed only after its .gz verified"""
    probs = []
    for h, _, p in read_manifest(manifest_path):
        if p.endswith(".gz"):
            if sha256_file(p) != h:
                probs.append(f"{p}: differs")
            continue
        g = p + ".gz"
        with open(p, "rb") as src, gzip.GzipFile(g, "wb", mtime=0) as dst:
            shutil.copyfileobj(src, dst, 1 << 20)
        durable([g])
        if sha256_file(g, gz=True) != h:
            probs.append(f"{g}: decompressed content differs; original kept")
            os.remove(g)
            continue
        os.remove(p)
    return not probs, probs


def committed(repo, pairs):
    """every (path in repo, local file): HEAD's blob of that path equals the local file byte for byte"""
    probs = []
    for rp, lf in pairs:
        r = subprocess.run(["git", "-C", repo, "cat-file", "-p", f"HEAD:{rp}"], capture_output=True)
        if r.returncode != 0:
            probs.append(f"{rp}: not in HEAD")
        elif r.stdout != open(lf, "rb").read():
            probs.append(f"{rp}: HEAD content differs from {lf}")
    return not probs, probs


def main(argv):
    cmd = argv[1]
    if cmd == "classify":
        o, d = classify(argv[2], _read(argv[3], limit=1 << 20))
        print(f"{o}\t{d}")
        return 0
    if cmd == "space":
        st = os.statvfs(argv[2])
        free = st.f_bavail * st.f_frsize
        ok, req = space_rule(free, int(argv[3]), int(argv[4]))
        print(f"free {free / GB:.2f} GB, required {req / GB:.2f} GB (1.5 x run {int(argv[3]) / GB:.2f} + twin "
              f"{int(argv[4]) / GB:.2f} + checker {CHECKER_TMP / GB:.0f} + margin {MARGIN / GB:.0f}): {'OK' if ok else 'STOP'}")
        return 0 if ok else 3
    if cmd == "manifest":
        h, n = manifest(argv[2], argv[3:])
        print(f"manifest {argv[2]}: {n} files, sha256 {h}")
        return 0
    if cmd == "verify-manifest":
        ok, probs = verify_manifest(argv[2])
        print("manifest verified" if ok else "MANIFEST MISMATCH: " + "; ".join(probs[:5]))
        return 0 if ok else 1
    if cmd == "retain":
        ok, probs = retain(argv[2])
        print("retained (gzip -n), every file verified against the manifest" if ok else "RETAIN FAILED: " + "; ".join(probs[:5]))
        return 0 if ok else 1
    if cmd == "committed":
        i = argv.index("--")
        rps, lfs = argv[3:i], argv[i + 1:]
        if len(rps) != len(lfs):
            print("committed: path lists differ in length")
            return 2
        ok, probs = committed(argv[2], list(zip(rps, lfs)))
        print("records committed (HEAD blobs equal the local records)" if ok else "NOT COMMITTED: " + "; ".join(probs[:5]))
        return 0 if ok else 1
    if cmd == "durable":
        durable(argv[2:])
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    sys.exit(main(sys.argv))
