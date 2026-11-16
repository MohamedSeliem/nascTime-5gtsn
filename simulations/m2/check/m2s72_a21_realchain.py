#!/usr/bin/env python3
"""A2-D2-F3 Phase 2: targeted validation of A-2.1 (and the frozen A-2) on the REAL first-chain fixture.

    m2s72_a21_realchain.py <fixture dir> <fresh record dir>

<fixture dir> holds the three extractor outputs: a2v1-first-chain.log.gz, its .sha256 pin and a2v1-first-chain.meta.json.
SIMU5G_ROOT must name the Simu5G 1.8.1 tree (A2-0s reads the source texts). Writes only <record dir>, which must not
exist. Exit 0: every declared expectation R-1..R-10 met; 1: a deviation (reported, never adjusted); 3: inputs refused
(pin mismatch, missing file, SIMU5G_ROOT unset, record dir exists).

The fixture is a PREFIX of the sealed run (through the TTI after the chain's ACK): the window is the whole prefix
(t0 = 0); no .sca is used (the run's scalars are whole-run values and do not describe a prefix), so A2-8 is NOT
EVALUATED here. This validation is NOT an A2-V1 acceptance: a supplementary acceptance would also need A2-8 PASS on the
whole run, which is not evaluated in this stage. The A2-V1 verdict NOT ACCEPTED stands.
"""
import hashlib
import json
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import check_m2s72_a2 as C  # noqa: E402  (frozen)
import check_m2s72_a21 as CC  # noqa: E402
import m2s72_a2 as A2  # noqa: E402  (frozen)
import m2s72_a21 as A  # noqa: E402

MS = A.MS
FIX, META = "a2v1-first-chain.log.gz", "a2v1-first-chain.meta.json"
CHAIN = {"pid": 145933, "handle": 54326, "node": 2050, "p": 0, "tx_ms": [361, 367, 373, 379], "nack_ms": [366, 372, 378],
         "ack_ms": 384}
EXPECT_PASS = ("A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-6", "A2-7", "A2-9")
EXPECT = {**{k: ("PASS",) for k in EXPECT_PASS}, "A2-5": ("PASS", A.NX), "A2-4c": (A.NE,), "A2-8": (A.NE,)}
FROZEN_TOKEN = f"NACK (PDU {CHAIN['handle']}) not among the candidates"
NOTB_ALLOWED = {"NC-A21-scalar", "NC-F1-handle-foreign", "NC-F1-retired"}


class Refused(Exception):
    pass


def sha256(path):
    return hashlib.sha256(open(path, "rb").read()).hexdigest()


def load_fixture(d):
    fx, pin, meta = (os.path.join(d, x) for x in (FIX, FIX + ".sha256", META))
    for p in (fx, pin, meta):
        if not os.path.isfile(p):
            raise Refused(f"missing {p}")
    want = open(pin).read().split()
    if len(want) != 2 or want[1] != FIX:
        raise Refused(f"pin {pin} is not '<sha256>  {FIX}'")
    got = sha256(fx)
    m = json.load(open(meta))
    if got != want[0] or m.get("fixture_sha256") != got:
        raise Refused(f"fixture sha256 {got}; pin {want[0]}; metadata {m.get('fixture_sha256')}")
    node = {int(k): int(v) for k, v in m["node_ids"].items()}
    import m2s72_maclog as ML
    return {"path": fx, "sha256": got, "meta": m, "node": node, "cfg": m["cfg"], "nproc": C._nproc(m["cfg"]),
            "lines21": A.load(fx), "lines2": A2.load(fx), "grants": ML.MacLog(fx).grants}


def validate(fx, root):
    """returns (results, context): results = [(id, PASS / FAIL, detail)]"""
    out = []

    def rec(i, ok, detail):
        out.append((i, "PASS" if ok else "FAIL", detail))
    node, nproc, grants, t0 = fx["node"], fx["nproc"], fx["grants"], 0
    # R-1 frozen A-2: the original identifier-namespace failure
    f = C.evaluate(fx["lines2"], nproc, t0, node, grants, None, root)[1]
    fd = {r[0]: (r[2], r[3]) for r in f}
    rec("R-1 frozen A-2 reproduces the identifier mismatch", fd["A2-1"][0] == "FAIL" and FROZEN_TOKEN in fd["A2-1"][1],
        f"frozen A2-1 {fd['A2-1'][0]}: {fd['A2-1'][1][:300]}")
    res, rows, per, cov, extra, window = A.evaluate(fx["lines21"], nproc, t0, node, grants, None, root)
    st = {r[0]: r[2] for r in rows}
    det = {r[0]: r[3] for r in rows}
    dev = {k: (st.get(k), det.get(k, "")[:200]) for k, ok in EXPECT.items() if st.get(k) not in ok}
    rec("R-2 A-2.1 rows (A2-4a / A2-4b / A2-4c reported separately)", not dev,
        f"rows {st}; deviations {dev}" if dev else f"rows {st}")
    vf, vi = A.verdict(rows, "full"), A.verdict(rows, "f1d-i")
    rec("R-3 verdicts on the prefix", vf == ("A-2.1 INCOMPLETE", 4) and vi == ("A-2.1 VALID", 0),
        f"full {vf}; f1d-i {vi} (neither is an A2-V1 acceptance)")
    pid, h, nd = CHAIN["pid"], CHAIN["handle"], CHAIN["node"]
    nk = [x for x in res["fb"] if x.get("pid") == pid and x["res"] == "NACK"]
    ak = [x for x in res["fb"] if x.get("pid") == pid and x["res"] == "ACK"]
    ok4, d4 = False, "no NACK of the chain"
    if nk:
        g = next((g for g in res["groups"] if any(y["j"] == nk[0]["j"] for y in g["lines"])), None)
        others = [y for y in g["lines"] if y["j"] != nk[0]["j"]] if g else []
        closed = all(y["res"] != "ACK" or (res["pdus"][y["pid"]]["t_close"] // MS == CHAIN["nack_ms"][0]
                                           and res["pdus"][y["pid"]]["close_gi"] == y["gi"]) for y in others)
        ok4 = (nk[0]["t"] // MS == CHAIN["nack_ms"][0] and nk[0]["cls"] == "resolved-by-rtx" and nk[0]["owner"] == nd
               and nk[0].get("handle") == h and bool(others) and all(y["cls"] in A.UNIQUE and y["owner"] != nd for y in others)
               and closed)
        d4 = (f"366 group: NACK cls {nk[0]['cls']} owner {nk[0]['owner']} pid {nk[0].get('pid')} handle {nk[0].get('handle')}; "
              f"other lines {[(y['res'], y['cls'], y['owner'], y['pid']) for y in others]}; their ACKed units closed at that line: {closed}")
    rec("R-4 mixed feedback group at 366 ms resolved", ok4, d4)
    u = res["pdus"].get(pid, {})
    txs = [t // MS for t in u.get("txs", [])]
    nts = [x["t"] // MS for x in nk]
    trans = [(n, t) for n, t in zip(nts, txs[1:])]
    ok5 = (nts == CHAIN["nack_ms"] and [x["cls"] for x in nk] == ["resolved-by-rtx", "bound", "bound"]
           and all(x["owner"] == nd and x.get("handle") == h for x in nk) and txs == CHAIN["tx_ms"]
           and all(t - n == 1 for n, t in trans))
    rec("R-5 three NACK -> retransmission transitions", ok5,
        f"NACKs {[(x['t'] // MS, x['cls'], x.get('handle')) for x in nk]}; transmissions {txs}; NACK -> rtx {trans}")
    # the 384 ms group may hold another UE's ACK on the same process: the ACK line is then 'exchangeable' (same result,
    # same time, same process: neither A-2.1 nor the UE side can tell the two lines apart). Decisive: the lifecycle
    # closes with ACK at 384 ms after 4 transmissions; the line class is reported.
    ok6 = (len(ak) == 1 and ak[0]["t"] // MS == CHAIN["ack_ms"] and (ak[0]["cls"] in A.UNIQUE or ak[0]["cls"] == "exchangeable")
           and ak[0]["owner"] == nd and u.get("end") == "ack" and u.get("ntx") == 4 and u.get("t_close", 0) // MS == CHAIN["ack_ms"])
    rec("R-6 final ACK at 384 ms", ok6, f"ACK lines {[(x['t'] // MS, x['cls'], x['owner']) for x in ak]}; "
        f"PDU end {u.get('end')}, ntx {u.get('ntx')}, closed {u.get('t_close', 0) // MS} ms")
    hs = res["handles"].get(h)
    other_h = [k for k, v in res["handles"].items() if k != h and (v.get("lc") == pid or (isinstance(v.get("lc"), list) and pid in v["lc"]))]
    rec("R-7 lifecycle handle bound and retired", hs == {"st": "retired", "lc": pid} and not other_h,
        f"handle {h}: {hs}; other handles naming {pid}: {other_h}")
    # R-8 the unchanged UE-side reference (XA), line by line, for every line of the chain and of its 366 group
    import m2s72_harqx as H
    log = H.read_log(None, lines=fx["lines21"])
    log["t_last"] = res["t_end"]
    tr = H.truth(log, node)
    delta, xl, cens, probs = H.match_feedback(log, tr, None)
    js = sorted({x["j"] for x in nk + ak} | ({y["j"] for y in g["lines"]} if nk and g else set()))
    if delta is None or len(xl) != len(res["fb"]):
        rec("R-8 gNB attribution confirmed by XA line by line", False, f"reference unusable (delta {delta}, {len(xl)} vs {len(res['fb'])} lines)")
    else:
        # a UNIQUE A-2.1 line must be confirmed by the reference itself (reference set = {owner}); an exchangeable line
        # (same result, time and process as another UE's line) is confirmed as its group's node multiset
        bad, conf, grp = [], 0, 0
        for j in js:
            x = res["fb"][j]
            if x["cls"] in A.UNIQUE:
                if xl[j][3] == {x["owner"]}:
                    conf += 1
                else:
                    bad.append((j, x["t"] // MS, x["cls"], x["owner"], sorted(xl[j][3])))
            else:
                gg = next(g2 for g2 in res["groups"] if any(y["j"] == j for y in g2["lines"]))
                own_a = sorted(y["owner"] for y in gg["lines"])
                own_x = sorted(xl[y["j"]][2]["node"] for y in gg["lines"] if xl[y["j"]][2] is not None)
                if own_a == own_x and x["owner"] in xl[j][3]:
                    grp += 1
                else:
                    bad.append((j, x["t"] // MS, x["cls"], own_a, own_x))
        rec("R-8 gNB attribution confirmed by XA line by line", not bad and st.get("A2-7") == "PASS",
            f"{len(js)} chain lines: {conf} unique lines confirmed by the reference, {grp} exchangeable lines confirmed as "
            f"their group's node multiset; mismatches {bad}; A2-7 {st.get('A2-7')}")
    # R-10 controls (R-9 is the A2-4 split, reported in R-2)
    ctl, st0 = CC.controls(fx["lines21"], nproc, t0, node, grants, None, root)
    notas = [c for c in ctl if c[2] == "NOT AS DECLARED"]
    notb = [c for c in ctl if c[2] == CC.NOTB]
    unexpected_notb = [c[0] for c in notb if c[0].split(":")[0] not in NOTB_ALLOWED]
    built = [c for c in ctl if c[2] == "AS DECLARED"]
    rec("R-10 controls (each built on a passing baseline)", not notas and not unexpected_notb and len(built) >= 10,
        f"{len(built)} AS DECLARED, {len(notb)} NOT BUILDABLE ({[c[0].split(':')[0] for c in notb]}), "
        f"{len(notas)} NOT AS DECLARED {[c[0] for c in notas]}")
    return out, {"rows": rows, "frozen_rows": f, "controls": ctl, "res": res, "verdicts": (vf, vi)}


def main(argv):
    if len(argv) != 3:
        print(__doc__, file=sys.stderr)
        return 3
    fdir, rdir = argv[1], argv[2]
    root = os.environ.get("SIMU5G_ROOT")
    try:
        if not root or not os.path.isdir(root):
            raise Refused("SIMU5G_ROOT is not set to a directory (A2-0s needs the 1.8.1 sources)")
        if os.path.lexists(rdir):
            raise Refused(f"record dir {rdir} exists (never reused)")
        fx = load_fixture(fdir)
    except Refused as ex:
        print(f"REFUSED: {ex}", file=sys.stderr)
        return 3
    os.mkdir(rdir)
    out, ctx = validate(fx, root)
    p = os.path.join(rdir, "a21-real-first-chain.txt")
    with open(p, "x") as fh:
        fh.write(f"A2-D2-F3 Phase 2: A-2.1 targeted validation on the real first-chain fixture\n"
                 f"fixture {fx['path']} sha256 {fx['sha256']}; cfg {fx['cfg']}; nodes {fx['node']}; processes {fx['nproc']}; "
                 f"window t0 = 0 (whole prefix); no .sca (A2-8 NOT EVALUATED)\n{A.NOTE}\n"
                 "Not an A2-V1 acceptance; the A2-V1 verdict NOT ACCEPTED stands.\n\nEXPECTATIONS\n")
        for i, s, d in out:
            fh.write(f"  {s:<4} | {i} | {d}\n")
        fh.write("\nA-2.1 ROWS\n")
        for r in ctx["rows"]:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[3]}\n")
        fh.write("\nFROZEN A-2 ROWS (fbee202, unchanged)\n")
        for r in ctx["frozen_rows"]:
            fh.write(f"  {r[2]:<15} | {r[0]} | {r[3][:600]}\n")
        fh.write("\nCONTROLS\n")
        for c in ctx["controls"]:
            fh.write(f"  {c[2]:<16} | {c[0]} | observed {c[3]} | declared {c[4]}\n")
    fails = [i for i, s, _ in out if s != "PASS"]
    print(open(p).read())
    print(f"RESULT: {'ALL EXPECTATIONS MET' if not fails else 'DEVIATION: ' + ', '.join(fails)}  (record {p})")
    return 1 if fails else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
