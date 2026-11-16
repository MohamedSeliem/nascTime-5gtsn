#!/usr/bin/env python3
"""Local tests of the A2-D2-F3 fixture extractor (m2s72_a21_fixture.py) and of the Phase 2 validator
(m2s72_a21_realchain.py), on SYNTHETIC sealed trees laid out as m2s72a2v1.sh writes them (seal over p0 / records / eval,
raw-output manifest with absolute paths, gzip log, .sca). The log is the labelled synthetic reconstruction of the first
chain (test_m2s72_a21.recon), written with OMNeT++ time stamps, a Cmdenv banner and other modules' lines.
No real run is read; no simulation. Every test checks that the sealed tree is bit-identical afterwards
(content, size, mode, mtime) and that nothing was written inside it."""
import ast
import gzip
import hashlib
import io
import os
import shutil
import subprocess
import sys
import tempfile
from contextlib import redirect_stderr, redirect_stdout

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
sys.dont_write_bytecode = True
import m2s72_a21_fixture as FX  # noqa: E402
import m2s72_a21_realchain as RC  # noqa: E402
import test_m2s72_a2 as TA  # noqa: E402
import test_m2s72_a21 as T  # noqa: E402

TESTS = []
CFG, RUN = FX.CFG, FX.RUN
BANNER = [b"OMNeT++ Discrete Event Simulation  (C) 1992-2025 OpenSim Ltd.\n", b"Version: 6.5.0, build: x, edition: Academic Public License\n",
          b"Setting up Cmdenv...\n", b"Preparing for running configuration " + CFG.encode() + b", run #0...\n"]


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def sha(b):
    return hashlib.sha256(b).hexdigest()


def recon_log():
    lines, node, truth = T.recon()
    body = [y for y in lines if T.A.SENTINEL_MOD not in y]
    out = list(BANNER)
    for y in body:
        out.append(y.encode())
        t = y.split("|", 1)[0]
        if "= END DOWNLINK =" in y:      # another module's line in the same TTI (RLC), kept by the extractor
            out.append(f"{t}|M2S72Bridge.gnb1.cellularNic.nrRlc.um|NrRlcUmTxEntity::rlcPduMake - send PDU size 1400 to lower layer\n".encode())
    out.append(b"<!> Simulation time limit reached -- at t=0.42s, event #99999\n")
    return out, node


def sca_text(node):
    s = [f"version 3\nrun {CFG}-0-20261116\n"]
    for k, v in sorted(node.items()):
        s.append(f"par M2S72Bridge.ue[{k}].cellularNic.nrMac macNodeId {v}\n")
        s.append(f"par M2S72Bridge.ue[{k}].cellularNic.mac macNodeId {1025 + k}\n")
    s.append("scalar M2S72Bridge.ue[1].cellularNic.nrMac harqErrorRateDl:mean 0.1\n")
    return "".join(s)


def write_seal(R):
    rels = []
    for sub in ("p0", "records", "eval"):
        for d, _, fs in os.walk(os.path.join(R, RUN, sub)):
            rels += [os.path.relpath(os.path.join(d, f), R) for f in fs]
    seal = os.path.join(R, f"{RUN}-evidence.sha256")
    with open(seal, "w") as fh:
        for r in sorted(rels):
            fh.write(f"{sha(open(os.path.join(R, r), 'rb').read())}  {r}\n")
    return sha(open(seal, "rb").read())


def write_manifest(R, paths):
    m = os.path.join(R, RUN, "records", f"{CFG}.manifest.sha256")
    with open(m, "w") as fh:
        for p in paths:
            b = open(p, "rb").read()
            fh.write(f"{sha(b)}  {len(b)}  {p}\n")


def tree(base, log=None, node=None, log_name=None):
    """a sealed A2-V1 tree; returns (R, seal sha256, source log bytes)"""
    if log is None:
        log, _ = recon_log()
    node = node or {0: 2049, 1: 2050}
    R = os.path.join(base, "results")
    run = os.path.join(R, RUN)
    for sub in ("p0", "records", "eval", f"runs/{CFG}/{CFG}"):
        os.makedirs(os.path.join(run, sub))
    raw = b"".join(log)
    lg = os.path.join(run, "runs", log_name or f"run-{CFG}.log.gz")
    with open(lg, "wb") as fh:
        fh.write(gzip.compress(raw, mtime=0))
    sca = os.path.join(run, "runs", CFG, CFG, "0.sca")
    open(sca, "w").write(sca_text(node))
    vec = os.path.join(run, "runs", CFG, CFG, "0.vec")
    open(vec, "w").write("version 3\n")
    write_manifest(R, [lg, sca, vec])
    open(os.path.join(run, "records", "wrapper-verdict.txt"), "w").write("LIFECYCLE COMPLETE; A2-V1 NOT ACCEPTED (synthetic)\n")
    open(os.path.join(run, "records", "steps.txt"), "w").write("synthetic\n")
    open(os.path.join(run, "eval", f"a2v1-{CFG}.txt"), "w").write("NOT ACCEPTED (synthetic)\n")
    open(os.path.join(run, "p0", "p0.txt"), "w").write("P0 (synthetic)\n")
    return R, write_seal(R), raw


def snapshot(R):
    out = {}
    for d, dirs, fs in os.walk(R):
        for x in fs + dirs:
            p = os.path.join(d, x)
            st = os.lstat(p)
            out[os.path.relpath(p, R)] = (st.st_mode, st.st_size, st.st_mtime_ns,
                                          sha(open(p, "rb").read()) if os.path.isfile(p) and not os.path.islink(p) else os.path.islink(p))
    return out


def ex(R, seal, out, *extra, hook=None):
    buf = io.StringIO()
    with redirect_stdout(buf), redirect_stderr(buf):
        rc = FX.run(["extract", "--results-root", R, "--seal-sha256", seal, "--out", out, *extra], _hook=hook)
    return rc, buf.getvalue()


def stopped(out, rc_want, rc, txt, token):
    assert rc == rc_want, (rc, txt[-800:])
    if rc_want != 10:
        f = open(os.path.join(out, "FAILED.txt")).read()
        assert f.startswith(f"exit {rc_want}") and token in f, (f, token)
        assert not os.path.exists(os.path.join(out, FX.FIX)) and not os.path.exists(os.path.join(out, FX.FIX + ".sha256"))
        assert not os.path.exists(os.path.join(out, FX.META)) and not os.path.exists(os.path.join(out, "SHA256SUMS"))
    else:
        assert token in txt, (txt, token)


def case(fn):
    """runs fn(base) in a fresh temporary directory, removed afterwards"""
    base = tempfile.mkdtemp()
    try:
        return fn(base)
    finally:
        for d, dirs, fs in os.walk(base):
            for x in dirs + fs:
                try:
                    os.chmod(os.path.join(d, x), 0o755, follow_symlinks=False)
                except (OSError, NotImplementedError):
                    pass
        shutil.rmtree(base)


def ms_of(line):
    p = line.split(b"|", 2)
    return FX.t_ps(p[0].decode()) // FX.MS if len(p) == 3 and p[0][:1].isdigit() else None


# ------------------------------------------------------------------------------------------------ happy path ----
@test("X-1 extraction on a faithful sealed tree: rc 0; the fixture is the byte-identical source prefix through the "
       "complete TTI of the first gNB main loop after 384 ms (385 ms), incl. banner and other modules' lines; the next "
       "source line is later; pin = sha256 of the fixture; SHA256SUMS verifies; metadata records sources, boundary and "
       "the declared facts; the sealed tree is bit-identical afterwards; a second extraction gives the same fixture sha256")
def _():
    def f(base):
        R, seal, raw = tree(base)
        before = snapshot(R)
        out = os.path.join(base, "out1")
        rc, txt = ex(R, seal, out)
        assert rc == 0, txt[-1500:]
        assert snapshot(R) == before
        assert sorted(os.listdir(out)) == sorted([FX.FIX, FX.FIX + ".sha256", FX.META, "steps.txt", "SHA256SUMS"])
        fx = gzip.decompress(open(os.path.join(out, FX.FIX), "rb").read())
        assert raw.startswith(fx) and fx.endswith(b"\n")
        rest = raw[len(fx):].split(b"\n", 1)[0] + b"\n"
        assert ms_of(rest) == 386, rest
        lines = fx.splitlines(keepends=True)
        assert lines[:4] == BANNER and max(m for m in map(ms_of, lines) if m is not None) == 385
        assert any(b"nrRlc" in y for y in lines) and any(b"nrMac" in y for y in lines)
        t385 = [y for y in lines if ms_of(y) == 385]
        assert any(FX.ML_END.encode() in y for y in t385) and any(b"feedback received" in y for y in t385)
        pin = open(os.path.join(out, FX.FIX + ".sha256")).read()
        assert pin == f"{sha(open(os.path.join(out, FX.FIX), 'rb').read())}  {FX.FIX}\n"
        r = subprocess.run(["sha256sum", "-c", "SHA256SUMS"], cwd=out, capture_output=True, text=True)
        assert r.returncode == 0, r.stdout + r.stderr
        import json
        m = json.load(open(os.path.join(out, FX.META)))
        assert m["cfg"] == CFG and m["node_ids"] == {"0": 2049, "1": 2050} and m["extraction"]["boundary_loop_ms"] == 385
        assert m["extraction"]["lines"] == len(lines) and m["extraction"]["decompressed_sha256"] == sha(fx)
        assert m["sources"]["seal_sha256"] == seal and m["sources"]["log"].endswith(f"run-{CFG}.log.gz")
        assert m["facts_found"]["recorded, not asserted"]["rtxAcid lines"] == 0
        assert "NOT ACCEPTED" in list(m["sources"]["wrapper_verdicts_read_only"].values())[0]
        rc2, txt2 = ex(R, seal, os.path.join(base, "out2"))
        assert rc2 == 0 and open(os.path.join(base, "out2", FX.FIX + ".sha256")).read() == pin
    case(f)


@test("X-2 Phase 2 on the X-1 output (SYNTHETIC reconstruction, labelled): m2s72_a21_realchain.validate gives R-1..R-10 "
      "PASS: frozen A-2 'NACK (PDU 54326) not among the candidates'; A-2.1 rows as declared (A2-4a/b PASS, A2-4c and A2-8 "
      "NOT EVALUATED); full INCOMPLETE, f1d-i VALID; 366 group resolved; 3 NACK -> rtx transitions; ACK 384; handle bound "
      "and retired; XA confirms every chain line; controls AS DECLARED or permitted NOT BUILDABLE. The CLI writes a fresh "
      "record (rc 0) and refuses an existing record dir and a tampered fixture (rc 3)")
def _():
    def f(base):
        R, seal, raw = tree(base)
        out = os.path.join(base, "out")
        assert ex(R, seal, out)[0] == 0
        root = TA.root()
        assert root, "SIMU5G sources needed for A2-0s"
        fx = RC.load_fixture(out)
        res, ctx = RC.validate(fx, root)
        bad = [r for r in res if r[1] != "PASS"]
        assert not bad and len(res) == 9, bad
        old = os.environ.get("SIMU5G_ROOT")
        os.environ["SIMU5G_ROOT"] = root
        try:
            buf = io.StringIO()
            with redirect_stdout(buf), redirect_stderr(buf):
                assert RC.main(["x", out, os.path.join(base, "rec")]) == 0
                assert RC.main(["x", out, os.path.join(base, "rec")]) == 3
                tam = os.path.join(base, "tampered")
                shutil.copytree(out, tam)
                with open(os.path.join(tam, FX.FIX), "ab") as fh:
                    fh.write(b"\0")
                assert RC.main(["x", tam, os.path.join(base, "rec2")]) == 3
            assert not os.path.exists(os.path.join(base, "rec2"))
            assert "ALL EXPECTATIONS MET" in buf.getvalue()
        finally:
            if old is None:
                os.environ.pop("SIMU5G_ROOT", None)
            else:
                os.environ["SIMU5G_ROOT"] = old
    case(f)


@test("X-3 the command line exactly as given to the VM (python3 -I -B, a separate process, cwd outside the tree): rc 0")
def _():
    def f(base):
        R, seal, raw = tree(base)
        r = subprocess.run([sys.executable, "-I", "-B", os.path.join(HERE, "m2s72_a21_fixture.py"), "extract",
                            "--results-root", R, "--seal-sha256", seal, "--out", os.path.join(base, "o")],
                           capture_output=True, text=True, cwd=base)
        assert r.returncode == 0 and "DONE fixture" in r.stdout, r.stdout[-800:] + r.stderr[-800:]
    case(f)


# --------------------------------------------------------------------------------------------- fail-closed ------
def expect_stop(rc_want, token, mut=None, reseal=False, extra=(), log=None, node=None, hook=None, out_fn=None, log_name=None):
    def f(base):
        if log is not None or node is not None or log_name is not None:
            R, seal, raw = tree(base, log=log, node=node, log_name=log_name)
        else:
            R, seal, raw = tree(base)
        if mut:
            mut(R)
            if reseal:
                seal = write_seal(R)
        before = snapshot(R)
        out = out_fn(base, R) if out_fn else os.path.join(base, "out")
        pre_out = snapshot(out) if os.path.exists(out) else None
        rc, txt = ex(R, seal, out, *extra, hook=hook and (lambda st: hook(st, R)))
        if hook is None:
            assert snapshot(R) == before, "the sealed tree changed"
        stopped(out, rc_want, rc, txt, token)
        if pre_out is not None:
            assert snapshot(out) == pre_out, "an existing output was touched"
    case(f)


@test("X-4 E-1: a seal sha256 other than the declared one -> exit 11, nothing extracted")
def _():
    def f(base):
        R, seal, raw = tree(base)
        before = snapshot(R)
        out = os.path.join(base, "out")
        rc, txt = ex(R, "0" * 64, out)
        stopped(out, 11, rc, txt, "E-1 seal sha256")
        assert snapshot(R) == before and not os.path.exists(os.path.join(out, FX.FIX + ".partial"))
    case(f)


@test("X-5 E-2: a sealed record changed after sealing -> 11; an unsealed file added under records -> 11; a seal path "
      "with '..' -> 11")
def _():
    expect_stop(11, "content differs", mut=lambda R: open(os.path.join(R, RUN, "eval", f"a2v1-{CFG}.txt"), "a").write("x"))
    expect_stop(11, "files not in the seal", mut=lambda R: open(os.path.join(R, RUN, "records", "late.txt"), "w").write("x"))

    def dotdot(R):
        s = os.path.join(R, f"{RUN}-evidence.sha256")
        txt = open(s).read().replace(f"{RUN}/p0/p0.txt", f"{RUN}/p0/../p0/p0.txt")
        open(s, "w").write(txt)

    def f(base):
        R, seal, raw = tree(base)
        dotdot(R)
        seal = sha(open(os.path.join(R, f"{RUN}-evidence.sha256"), "rb").read())
        out = os.path.join(base, "out")
        rc, txt = ex(R, seal, out)
        stopped(out, 11, rc, txt, "not a plain path")
    case(f)


@test("X-6 E-3: the log changed (one byte) -> 11; the manifest lists the log twice or not at all -> 11; a manifest "
      "path outside the run's runs/ -> 11; the log a symlink -> 11; another configuration's manifest -> 11")
def _():
    def flip(R):
        p = os.path.join(R, RUN, "runs", f"run-{CFG}.log.gz")
        b = bytearray(open(p, "rb").read())
        b[-5] ^= 1
        open(p, "wb").write(bytes(b))
    expect_stop(11, "size or content differs", mut=flip)
    man = lambda R: os.path.join(R, RUN, "records", f"{CFG}.manifest.sha256")  # noqa: E731

    def twice(R):
        ls = open(man(R)).read().splitlines(keepends=True)
        open(man(R), "w").write("".join(ls + ls[:1]))
    expect_stop(11, "run-" + CFG + ".log.gz and", mut=twice, reseal=True)

    def none_(R):
        ls = open(man(R)).read().splitlines(keepends=True)
        open(man(R), "w").write("".join(x for x in ls if ".log.gz" not in x))
    expect_stop(11, "names 0 run-", mut=none_, reseal=True)

    def outside(R):
        lg = os.path.join(R, RUN, "runs", f"run-{CFG}.log.gz")
        cp = os.path.join(os.path.dirname(R), f"run-{CFG}.log.gz")
        shutil.copy(lg, cp)
        txt = open(man(R)).read().replace(lg, cp)
        open(man(R), "w").write(txt)
    expect_stop(11, "outside", mut=outside, reseal=True)

    def link(R):
        lg = os.path.join(R, RUN, "runs", f"run-{CFG}.log.gz")
        real = os.path.join(R, RUN, "runs", "real.log.gz")
        os.rename(lg, real)
        os.symlink(real, lg)
    expect_stop(11, "not a regular file", mut=link)

    def other(R):
        os.rename(man(R), man(R).replace(CFG, CFG + "x"))
    expect_stop(11, "is not the declared", mut=other, reseal=True)


@test("X-7 E-4: a UE MAC node id other than the declared one -> 11")
def _():
    expect_stop(11, "E-4 UE MAC node ids", node={0: 2049, 1: 2051})


@test("X-8 E-0: an existing output directory -> 10 and it is left untouched; an output inside the results root -> 10 "
      "and nothing is created there; a malformed --seal-sha256 -> 10")
def _():
    def mk(base, R):
        o = os.path.join(base, "out")
        os.mkdir(o)
        open(os.path.join(o, "keep.txt"), "w").write("earlier")
        return o
    expect_stop(10, "exists", out_fn=mk)
    expect_stop(10, "inside the results root", out_fn=lambda base, R: os.path.join(R, "fixture-out"))

    def f(base):
        R, seal, raw = tree(base)
        out = os.path.join(base, "out")
        rc, txt = ex(R, seal.upper(), out)
        assert rc == 10 and not os.path.exists(out), txt
    case(f)


def log_variant(edit):
    log, node = recon_log()
    return edit(log)


@test("X-9 E-5: no gNB main-loop markers -> 12; the log ends before the boundary TTI (cut at 380 ms) -> 12; a time "
      "stamp going backwards -> 12; --max-bytes below the prefix -> 12; the boundary loop without its end marker -> 12; in "
      "every case no final fixture, the copied bytes keep the .partial name")
def _():
    expect_stop(12, "no gNB main loop starts", log=log_variant(lambda L: [y for y in L if b"ENB MAIN LOOP" not in y]))
    expect_stop(12, "the log ends before", log=log_variant(lambda L: [y for y in L if ms_of(y) is None or ms_of(y) <= 380]))

    def back(L):
        i = next(i for i, y in enumerate(L) if ms_of(y) == 370)
        return L[:i + 1] + [b"0.369|M2S72Bridge.gnb1.cellularNic.nrRlc.um|late line\n"] + L[i + 1:]
    expect_stop(12, "earlier than the previous", log=log_variant(back))
    expect_stop(12, "exceeds --max-bytes", extra=("--max-bytes", "1000"))
    expect_stop(12, "E-5", log=log_variant(lambda L: [y for y in L if not (ms_of(y) == 385 and FX.ML_END.encode() in y)]))


@test("X-10 E-6: declared facts absent -> 13: the unit lines print another handle; one retransmission missing; the "
      "chain's PDU on another process; no 'selected for retransmission' line")
def _():
    expect_stop(13, "F-3", log=log_variant(lambda L: [y.replace(b"PDU 54326 ", b"PDU 54327 ") for y in L]))

    def drop_rtx(L):
        return [y for y in L if not (ms_of(y) == 373 and b"(id 145933 ) extracted" in y)]
    expect_stop(13, "F-2", log=log_variant(drop_rtx))
    expect_stop(13, "F-5", log=log_variant(lambda L: [y for y in L if b"selected for retransmission" not in y]))
    expect_stop(13, "F-1", log=log_variant(lambda L: [y.replace(b"(id 145933 ) inserted into process 0", b"(id 145933 ) inserted into process 1") for y in L]))


@test("X-11 E-7: a sealed record or the log changed while the extraction ran -> 14; the fixture keeps its .partial name, "
      "no pin, no metadata, FAILED.txt says exit 14")
def _():
    def touch_record(stage, R):
        if stage == "before-reverify":
            open(os.path.join(R, RUN, "records", "steps.txt"), "a").write("late write\n")
    expect_stop(14, "E-7", hook=touch_record)

    def f(base):
        R, seal, raw = tree(base)
        out = os.path.join(base, "out")

        def h(stage):
            if stage == "before-reverify":
                p = os.path.join(R, RUN, "runs", CFG, CFG, "0.vec")
                open(p, "a").write("x")
        rc, txt = ex(R, seal, out, hook=h)
        stopped(out, 14, rc, txt, "E-7")
        assert os.path.exists(os.path.join(out, FX.FIX + ".partial"))
    case(f)


@test("X-13 Phase 2 fails closed: a fixture whose 'selected for retransmission' lines are removed (re-pinned) gives "
      "R-2 FAIL (A2-4a) and exit 1, never adjusted; T-real-first-chain on the fixture directory: all three files -> PASS, "
      "none -> PENDING (not PASS), two of three -> FAIL")
def _():
    import json

    def f(base):
        R, seal, raw = tree(base)
        out = os.path.join(base, "out")
        assert ex(R, seal, out)[0] == 0
        bad = os.path.join(base, "bad")
        shutil.copytree(out, bad)
        body = gzip.decompress(open(os.path.join(bad, FX.FIX), "rb").read()).splitlines(keepends=True)
        body = b"".join(y for y in body if b"selected for retransmission" not in y)
        open(os.path.join(bad, FX.FIX), "wb").write(gzip.compress(body, mtime=0))
        h = sha(open(os.path.join(bad, FX.FIX), "rb").read())
        open(os.path.join(bad, FX.FIX + ".sha256"), "w").write(f"{h}  {FX.FIX}\n")
        m = json.load(open(os.path.join(bad, FX.META)))
        m["fixture_sha256"] = h
        json.dump(m, open(os.path.join(bad, FX.META), "w"))
        res, ctx = RC.validate(RC.load_fixture(bad), TA.root())
        st = {r[0].split(" ")[0]: r[1] for r in res}
        assert st["R-2"] == "FAIL" and "A2-4a" in dict((r[0].split(" ")[0], r[2]) for r in res)["R-2"], res
        old = os.environ.get("SIMU5G_ROOT")
        os.environ["SIMU5G_ROOT"] = TA.root()
        try:
            with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
                assert RC.main(["x", bad, os.path.join(base, "rec")]) == 1
        finally:
            if old is None:
                os.environ.pop("SIMU5G_ROOT", None)
            else:
                os.environ["SIMU5G_ROOT"] = old
        treal = next(fn for n, fn in T.TESTS if n.startswith("T-real-first-chain"))
        old_fix = T.FIX
        try:
            T.FIX = os.path.join(out, FX.FIX)
            assert treal() is None
            empty = os.path.join(base, "empty")
            os.mkdir(empty)
            T.FIX = os.path.join(empty, FX.FIX)
            assert treal() == "PENDING"
            part = os.path.join(base, "part")
            shutil.copytree(out, part)
            os.remove(os.path.join(part, FX.META))
            T.FIX = os.path.join(part, FX.FIX)
            try:
                treal()
                raise RuntimeError("an incomplete fixture set was accepted")
            except AssertionError as e:
                assert "incomplete fixture set" in str(e)
        finally:
            T.FIX = old_fix
    case(f)


@test("X-14 boundary rationale (reconstruction): a cut right after the boundary loop's END marker drops that TTI's "
      "feedback events and makes A-2.1 fail spuriously (A2-2 'OPEN at the end in state WAIT'); the extractor's TTI-complete "
      "cut gives the declared rows")
def _():
    lines, node, truth = T.recon()
    body = [y for y in lines if T.A.SENTINEL_MOD not in y]
    arm, ia = False, None
    for i, y in enumerate(body):
        if T.A.ML_START in y and FX.t_ps(y.split("|")[0]) // FX.MS > 384:
            arm = True
        if arm and T.A.ML_END in y:
            ia = i
            break
    mid = body[:ia + 1] + [T.A.sentinel(T.A.t_end_of(body[:ia + 1]))]
    s_mid = T.st(T.ev21(mid, node, t0=0)[1])
    assert s_mid["A2-2"] == "FAIL", s_mid
    s_tti = T.st(T.ev21(T.cut_at(lines, 385), node, t0=0)[1])
    assert all(v == "PASS" for k, v in s_tti.items() if k not in ("A2-4c", "A2-8")), s_tti


@test("X-12 audit: the extractor imports only the Python standard library (nothing from the repository), never opens a "
      "file for writing outside its output directory (every write uses the output dir), and has no retry loop")
def _():
    src = open(os.path.join(HERE, "m2s72_a21_fixture.py")).read()
    tree_ = ast.parse(src)
    mods = set()
    for n in ast.walk(tree_):
        if isinstance(n, ast.Import):
            mods |= {a.name.split(".")[0] for a in n.names}
        elif isinstance(n, ast.ImportFrom):
            mods.add(n.module.split(".")[0])
    assert mods <= {"gzip", "hashlib", "json", "os", "platform", "re", "sys", "time", "argparse"}, mods
    writes = []
    for n in ast.walk(tree_):
        if isinstance(n, ast.Call) and getattr(n.func, "id", None) == "open" and len(n.args) >= 2:
            mode = n.args[1].value if isinstance(n.args[1], ast.Constant) else "?"
            if any(c in mode for c in "wxa+"):
                writes.append(ast.unparse(n.args[0]))
    assert writes and all("out" in w or w == "dst_partial" for w in writes), writes
    assert "os.rename(partial" in src and src.count("os.rename(") == 1 and "remove(" not in src and "rmtree" not in src
    assert "while" not in src and "retry" not in src.replace("no retry", "").replace("never retried", "").replace("Nothing was retried", "")


def main():
    only = sys.argv[1:]
    run = [(n, f) for n, f in TESTS if not only or any(n.startswith(o) for o in only)]
    fails = 0
    for name, f in run:
        try:
            f()
            print(f"PASS  {name}")
        except Exception as ex_:
            fails += 1
            import traceback
            traceback.print_exc()
            print(f"FAIL  {name}: {type(ex_).__name__}: {str(ex_)[:800]}")
    print(f"A-2.1 fixture-extractor tests: {len(run) - fails} / {len(run)} PASS, {fails} FAIL")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main())
