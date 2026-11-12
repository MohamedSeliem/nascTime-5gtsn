#!/usr/bin/env python3
"""M2-R181c: M2-S5 on Simu5G 1.8.1 with the revised C8 (C8-v) and version-appropriate negative controls.
check_m2s5.py is NOT changed; this file imports it.

    check_v181c_m2s5.py full <M2-S5 dir> <M2-S4 runs> <M2-S4 raw-outputs.sha256>
        check_m2s5.main(), unchanged, with exactly one substitution: the C8 entry of rows_5gs() is replaced by C8-v
        (below). Every other row, the 14 historical controls (expected sets unchanged) and their signatures are computed
        by the unchanged code. Output in the historical format; the C8 row title is replaced by the C8-v title.
    check_v181c_m2s5.py c8demo <M2-S5 runs> <M2-S4 runs>
        C8-v on M2S5 seed 0 unmodified (must PASS) and under two in-memory mutations (each must FAIL its sub-row).
    check_v181c_m2s5.py controls <M2-S5 runs> <M2-S4 runs> <M2-R181c runs>
        the replacement controls N-tseSlot-v and N-noFcsNw-v (configs in m2s5r181c.ini), with their base runs.

C8-v -- what C8 validates (M2-S5 design §6.3 "Containment", M2-S0 design: tags are bridge-internal metadata):
the DS-TT eth[1] egress (towards the slave) carries two disjoint packet classes, and nothing else:
  F  FORWARDED frames: entered the bridge at NW-TT eth[1] (tagged there by the M2-S0 layer, frameId) and crossed the
     5GS. Each must reach DS-TT eth[1] egress with its valid M2-S0 tag (recovered, same frameId) and be stripped.
  L  LOCALLY GENERATED frames: the DS-TT Pdelay engine's Pdelay_Resp and Pdelay_Resp_Follow_Up to the slave (injected
     above the measurement layer; untagged by construction). Their number follows the slave's Pdelay_Req timing (a
     slave-clock property), so they are excluded from the cross-scenario comparison and checked on their own.
Sub-rows (all must hold):
  (a) containment: the slave's audit counts 0 frames with a TtSyncIngressTag (unchanged from C8);
  (b) every UNTAGGED egress frame is class L: its logged chunk signature is GptpPdelayResp / GptpPdelayRespFollowUp and
      it is one-to-one with a DS-TT engine "tx" of that message type at the same time (ps); invalid tags 0;
      recovered = stripped;
  (c) class L on its own (M2-S4 contract: one Resp and one Resp_FU per Pdelay_Req): engine tx Resp = tx Resp_FU =
      rx Pdelay_Req, each Resp_FU after its Resp;
  (d) class F conservation in the run: every frameId tagged at NW-TT eth[1] ingress is recovered at DS-TT eth[1] egress,
      or is a Pdelay frame terminated by the NW-TT engine (signature GptpPdelay*), or was tagged in the last 100 ms
      before the end of the run (still inside); nothing else;
  (e) class F cross-scenario (M2S4 of the same seed / variant): the recovered frameId set and the NW-TT-terminated set
      equal M2S4's.
"""
import csv
import glob
import os
import re
import sys
from collections import Counter

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
MODE = sys.argv[1]
if MODE == "full":
    OUT5, RUNS4, HASHES4 = sys.argv[2:5]
    sys.argv = [sys.argv[0], OUT5, RUNS4, HASHES4]
else:
    RUNS5, RUNS4 = sys.argv[2], sys.argv[3]
    R181C = sys.argv[4] if len(sys.argv) > 4 else None
    sys.argv = [sys.argv[0], os.path.dirname(RUNS5.rstrip("/")), RUNS4, "/dev/null"]
import check_m2s5 as C  # noqa: E402

W_END_PS = 100 * 10 ** 9
PS = lambda s: C.pcapng.simtime_ps(s)
C8V_TITLE = ("C8-v containment and M2-S0 carriage by packet class: no TtSyncIngressTag at the slave; every untagged DS-TT "
             "eth[1] egress frame is a DS-TT-generated Pdelay_Resp / Resp_FU (one-to-one with the engine), one Resp and one "
             "Resp_FU per Pdelay_Req; every forwarded frame tagged at NW-TT eth[1] recovered (or NW-TT-terminated Pdelay, "
             "or still inside); forwarded and terminated sets = M2S4")


def rd(path):
    with open(path) as fh:
        return list(csv.DictReader(fh))


def rd_engine(path):
    """A translator's Pdelay-engine log. It exists only when the engine terminates Pdelay (logFile is written by an
    active engine); with terminate = false (N-fwdPdelay) there is none: the engine then generates and terminates
    nothing, i.e. zero rows. (M2-R181c addendum 1: the first version raised on the absent file.)"""
    return rd(path) if os.path.exists(path) else []


def end_ps(R):
    with open(R.sca_path) as fh:
        for line in fh:
            if line.startswith("config sim-time-limit"):
                return PS(line.split()[2].rstrip("s"))
    return None


def port_slot(R):
    """copy of check_m2s5.main()'s local port_slot (not importable): Sync enqueue (slot) time by tx start, DS-TT eth[1]"""
    rows_ = C.read_csv(os.path.join(R.ldir, f"M1Bridge.{R.dsn}.eth[1].measurementLayer.egress.port.csv"))
    return {C.pcapng.simtime_ps(r["tTxStart"]): C.pcapng.simtime_ps(r["tSlot"]) for r in rows_ if r["event"] == "tx"}


def c8v_data(R, mutate=None):
    L = R.ldir
    eg = rd(os.path.join(L, f"M1Bridge.{R.dsn}.eth[1].measurementLayer.egress.csv"))
    ing = [r for r in rd(os.path.join(L, f"M1Bridge.{R.nwn}.eth[1].measurementLayer.ingress.csv")) if r["event"] == "tag"]
    eng = rd_engine(os.path.join(L, f"M1Bridge.{R.dsn}.eth[1].trafficConditionerLayer.engine.pdelay.csv"))
    nweng = rd_engine(os.path.join(L, f"M1Bridge.{R.nwn}.eth[1].trafficConditionerLayer.engine.pdelay.csv"))
    if mutate == "forwarded-untagged":          # one forwarded frame reaches the DS-TT egress without its tag
        i = next(i for i, r in enumerate(eg) if r["event"] == "recover" and "GptpSync" not in r["signature"])
        eg[i] = dict(eg[i], event="untagged", frameId="")
    elif mutate == "local-missing":             # one DS-TT Pdelay_Resp missing at the egress
        i = next(i for i, r in enumerate(eg) if r["event"] == "untagged" and "GptpPdelayResp(" in r["signature"])
        eg = eg[:i] + eg[i + 1:]
    return eg, ing, eng, nweng


def c8v(R, R4, mutate=None):
    eg, ing, eng, nweng = c8v_data(R, mutate)
    probs = []
    # (a)
    audit = R.s(f"{R.sln}.eth[0].trafficConditionerLayer.audit", "framesWithSyncTag", -1)
    if audit != 0:
        probs.append(f"(a) {int(audit)} frames with a TtSyncIngressTag at the slave")
    # (b)
    untag = [r for r in eg if r["event"] == "untagged"]
    kind = lambda sig: 3 if "GptpPdelayResp(" in sig else 10 if "GptpPdelayRespFollowUp(" in sig else None
    # one-to-one, in order per message type: egress enqueue time <= engine transmission start (tA) < enqueue + 1 ms
    txs = {mt: sorted(int(r["tA"]) for r in eng if r["event"] == "tx" and int(r["msgType"]) == mt) for mt in (3, 10)}
    egs = {mt: sorted(PS(r["t"]) for r in untag if kind(r["signature"]) == mt) for mt in (3, 10)}
    notlocal = [(r["t"], re.sub(r".*data=\d+B: ", "", r["signature"])[:60]) for r in untag if kind(r["signature"]) is None]
    unmatched_tx = 0
    for mt in (3, 10):
        e, t = egs[mt], txs[mt]
        good = sum(1 for x, y in zip(e, t) if x <= y < x + 10 ** 9)
        notlocal += [("untagged Pdelay frame without an engine transmission", mt)] * max(0, len(e) - good)
        unmatched_tx += max(0, len(t) - good)
    tx = Counter({(0, mt): len(v) for mt, v in txs.items()})
    sc = {k[1]: v for k, v in R.sc.items() if k[0] == f"{R.net}.{R.dsn}.eth[1].measurementLayer.egress"}
    if notlocal:
        probs.append(f"(b) untagged egress frames that are not DS-TT Pdelay responses: {len(notlocal)} {notlocal[:2]}")
    if unmatched_tx:
        probs.append(f"(b) engine transmissions without an untagged egress frame: {unmatched_tx}")
    if sc.get("framesInvalidTag", -1) != 0 or sc.get("framesRecovered") != sc.get("framesStripped"):
        probs.append(f"(b) invalid {sc.get('framesInvalidTag')}, recovered {sc.get('framesRecovered')} != stripped {sc.get('framesStripped')}")
    # (c)
    rx_req = sum(1 for r in eng if r["event"] == "rx" and r["msgType"] == "2")
    n3, n10 = sum(1 for k, v in tx.items() if k[1] == 3 for _ in range(v)), sum(1 for k, v in tx.items() if k[1] == 10 for _ in range(v))
    l3 = sum(1 for r in untag if kind(r["signature"]) == 3)
    l10 = sum(1 for r in untag if kind(r["signature"]) == 10)
    order = [kind(r["signature"]) for r in untag if kind(r["signature"])]
    pairs_ok = all(order[i] == 3 and order[i + 1] == 10 for i in range(0, len(order) - 1, 2)) and len(order) % 2 == 0
    if not (n3 == n10 == rx_req and l3 == n3 and l10 == n10 and pairs_ok):
        probs.append(f"(c) Pdelay_Req {rx_req}, engine Resp/Resp_FU {n3}/{n10}, at the egress {l3}/{l10}, Resp then Resp_FU: {pairs_ok}")
    # (d)
    rec = {r["frameId"] for r in eg if r["event"] == "recover"}
    term_sig = lambda r: re.search(r"GptpPdelay(Req|Resp|RespFollowUp)\(", r["signature"]) is not None
    nw_rx = sum(1 for r in nweng if r["event"] == "rx")
    T = end_ps(R)
    term, inside, lost = set(), [], []
    for r in ing:
        f = r["frameId"]
        if f in rec:
            continue
        if term_sig(r):
            term.add(f)
        elif T is not None and PS(r["t"]) >= T - W_END_PS:
            inside.append(f)
        else:
            lost.append((f, r["t"], re.sub(r".*data=\d+B: ", "", r["signature"])[:50]))
    if lost:
        probs.append(f"(d) forwarded frames neither recovered, terminated nor still inside: {len(lost)} {lost[:2]}")
    if len(term) != nw_rx:
        probs.append(f"(d) NW-TT-terminated Pdelay frames {len(term)} != NW-TT engine rx {nw_rx}")
    if rec - {r["frameId"] for r in ing}:
        probs.append(f"(d) recovered frameIds not tagged at NW-TT: {len(rec - {r['frameId'] for r in ing})}")
    # (e)
    if R4 is not None:
        eg4, ing4, _, _ = c8v_data(R4)
        rec4 = {r["frameId"] for r in eg4 if r["event"] == "recover"}
        term4 = {r["frameId"] for r in ing4 if r["frameId"] not in rec4 and term_sig(r)}
        if rec != rec4 or term != term4:
            probs.append(f"(e) vs M2S4: recovered {len(rec)} vs {len(rec4)} (only here {len(rec - rec4)}, only M2S4 {len(rec4 - rec)}); "
                         f"NW-TT-terminated {len(term)} vs {len(term4)}")
    detail = (f"slave tags {int(audit)}; egress recovered {len(rec)} / untagged {len(untag)} (DS-TT Pdelay Resp {l3} + Resp_FU {l10}, "
              f"Pdelay_Req {rx_req}) / invalid {int(sc.get('framesInvalidTag', -1))}; NW-TT tagged {len(ing)} = recovered {len(rec & {r['frameId'] for r in ing})}"
              f" + NW-TT-terminated {len(term)} + still inside {len(inside)}" + ("; = M2S4" if R4 is not None and not any(p.startswith("(e)") for p in probs) else "")
              + (f"; problems: {probs[:3]}" if probs else ""))
    return not probs, detail


def s3o(R, R4, offset):
    """S3 with the step-pair rule of compare_recorded() (S1): S3 (check_m2s5.rows_5gs) zips the recorded clock samples
    with one predicted value per sample time; at a step the slave records two samples at the same time (old value,
    then new value, SettableClock.cc:81), so S3 can only be applied to runs whose steps change nothing (initial
    offset 0). S3o: identical Sync identity and cf2 prediction (from the M2-S4 records, R4 with the same initial
    offset), and every recorded sample = the prediction, where at a predicted step time the first sample = old value
    and the second = new value."""
    R.prepare(); R4.prepare()
    pred, diff = {}, []
    for s, ds in R.ds_sync.items():
        a = (R.nw_sync.get(s, [{}])[0].get("start"), ds[-1]["start"], R.gm_sync.get(s, [{}])[0].get("start"))
        b = (R4.nw_sync.get(s, [{}])[0].get("start"), R4.ds_sync.get(s, [{}])[-1].get("start"), R4.gm_sync.get(s, [{}])[0].get("start"))
        if a == b and None not in a:
            pred[s] = (R4.lup_at(R4.nw_fu[s][0]["end"]) or 0) + (b[1] - b[0])
        else:
            diff.append(s)
    logged = C.cf_map(R)
    mism = [s for s, v in pred.items() if s in logged and logged[s] != v]
    m4 = C.model_run(R4, cf=pred, initial=offset)
    step_at = {t: (o, n) for t, o, n, p in m4.clk.steps}
    samples = C.clock_samples(R.V)
    pv = C.O.replay_at(m4.clk.steps, offset, [t for t, v in samples])
    seen, bad = Counter(), 0
    for (t, v), p in zip(samples, pv):
        k = seen[t]
        seen[t] += 1
        exp = (step_at[t][0] if k == 0 else step_at[t][1]) if t in step_at else p
        bad += v != C.O.dbl(exp)
    ok = not diff and not mism and bad == 0 and len(pred) > 0
    return ok, (f"{len(pred)} Syncs with identical (TSi, TSe, POT) in the M2-S4 reference ({len(diff)} differ); logged cf2 = "
                f"prediction ({len(mism)} mismatches); predicted steps {len(m4.clk.steps)}; recorded clock trace = prediction "
                f"(step-pair rule) at {len(samples) - bad} of {len(samples)} samples")


def patched_rows():
    orig = C.rows_5gs

    def rows_5gs(R, R4=None, exp_missing=0, offset=0):
        res = orig(R, R4, exp_missing=exp_missing, offset=offset)
        res["C8_hist"] = res["C8"]
        res["C8"] = c8v(R, R4)
        return res
    C.rows_5gs = rows_5gs


def full():
    import io
    import contextlib
    patched_rows()
    buf = io.StringIO()
    with contextlib.redirect_stdout(buf):
        rc = C.main()
    out = buf.getvalue().replace(
        "C8 containment: no TtSyncIngressTag reaches the slave; M2-S0 tag recovery at DS-TT eth[1] as in M2S4, invalid 0", C8V_TITLE)
    print("M2-R181c: check_m2s5.py (unchanged) with C8 replaced by C8-v (check_v181c_m2s5.py); all other rows and the 14 "
          "historical controls unchanged\n")
    print(out, end="")
    return rc


def c8demo():
    R = C.Run(RUNS5, "M2S5", 0)
    R4 = C.Run(RUNS4, "M2S4", 0)
    ok_all = True
    for mut, want in ((None, True), ("forwarded-untagged", False), ("local-missing", False)):
        ok, det = c8v(R, R4, mutate=mut)
        good = ok == want
        ok_all &= good
        print(f"{'PASS' if good else 'FAIL'}  C8-v on M2S5 seed 0, {'unmodified' if mut is None else 'mutation ' + mut}: "
              f"{'PASS' if ok else 'FAIL'} (required {'PASS' if want else 'FAIL'})\n      {det}")
    print(f"\nOVERALL: {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


def controls():
    """Replacement controls (m2s5r181c.ini). Same evaluation as check_m2s5.main()'s NC loop: rows_5gs (with C8-v) of the
    control run minus the failures of its base run must equal the expected set, and the signature must hold."""
    patched_rows()
    R40 = C.Run(RUNS4, "M2S4", 0)
    R4L = C.Run(RUNS4, "M2S4-load", 0)
    ROWS = ("C1", "C2", "C3", "C4", "C5", "C6", "C7", "C8", "S1", "S2", "S3", "P1", "P2")
    off = C.pcapng.simtime_ps("0.001234567891")
    ok_all = True

    def failed(R, R4, offset=0, exp_missing=0):
        res = C.rows_5gs(R, R4, exp_missing=exp_missing, offset=offset)
        return {k for k in ROWS if k in res and not res[k][0]}, res
    # N-tseSlot-v: under saturating load (the Sync queues at the DS-TT egress on 1.8.1)
    miss = len(C.sel(R4L.gm, 2, C.SYNC)) - len(C.sel(R4L.sl, 1, C.FU))
    fb, rb = failed(C.Run(RUNS5, "M2S5-load", 0), R4L, exp_missing=miss)
    R = C.Run(R181C, "M2S5R-nc-tseSlot-load", 0)
    fc, rc = failed(R, R4L, exp_missing=miss)
    slot = port_slot(R)
    queued, n_ok, n_all, bad = 0, 0, 0, []
    for f in C.sel(R.sl, 1, C.FU):
        s = f["seq"]
        ns_, ds_ = R.nw_sync.get(s), R.ds_sync.get(s)
        if not (ns_ and ds_):
            continue
        tse, tsl = ds_[-1]["start"], slot[ds_[-1]["start"]]
        queued += tse != tsl
        want = R.lup_at(R.nw_fu[s][0]["end"]) + (tsl - ns_[0]["start"])
        n_all += 1
        n_ok += f["g"]["cf_raw"] == C.enc(want)
    expect = {"C2", "C3", "S2", "S3"}
    sig = n_all > 0 and n_ok == n_all and queued > 0
    ok = fc - fb == expect and sig
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'}  N-tseSlot-v cf = Lup + (Sync slot time - TSi), under saturating load "
          f"(M2S5R-nc-tseSlot-load vs base M2S5-load): fails exactly {sorted(expect)} beyond its base\n"
          f"      failed {sorted(fc - fb)} (base fails {sorted(fb)}); signature {'OK' if sig else 'WRONG'}: {n_ok}/{n_all} delivered "
          f"Follow_Ups carry exactly the slot-time cf; Syncs that queued at the DS-TT egress (TSe != slot) {queued}; "
          f"S2: {rc['S2'][1][:160]}")
    # N-noFcsNw-v: with the initial slave offset (the slave clock must be stepped to become exact)
    R4O = C.Run(R181C, "M2S4R-offset", 0)   # M2-S4 reference with the same initial slave offset (m2s5r181c.ini)
    RB = C.Run(RUNS5, "M2S5-offset", 0)
    fb, rb = failed(RB, R4O, offset=off)
    R = C.Run(R181C, "M2S5R-nc-noFcsNw-offset", 0)
    fc, rc = failed(R, R4O, offset=off)
    # S3 replaced by S3o for this pair (S3's comparator cannot be applied to a run with a non-zero step, see s3o)
    ob, db = s3o(RB, R4O, off)
    oc, dc = s3o(R, R4O, off)
    fb = (fb - {"S3"}) | ({"S3o"} if not ob else set())
    fc = (fc - {"S3"}) | ({"S3o"} if not oc else set())
    rc["S3"], rb["S3"] = (oc, dc), (ob, db)
    m = rc["_model"]
    drops = C.fcs_drops(R).get(f"{R.nwn}.ethernet.fcsChecker", 0)
    sig = len(m.out["fu"]) == 0 and len(C.sel(R.nw0, 2, C.FU)) == 0 and drops == len(C.sel(R.nw1, 1, C.FU)) > 0
    pre = [v - C.O.dbl(t) for t, v in C.clock_samples(R.V)]
    expect = {"C1", "C2", "C6", "C7", "C8", "S2", "S3o"}
    ok = fc - fb == expect and sig and not fb
    ok_all &= ok
    print(f"{'PASS' if ok else 'FAIL'}  N-noFcsNw-v NW-TT FCS stale, with the initial slave offset 1.234567891 ms "
          f"(M2S5R-nc-noFcsNw-offset vs base M2S5-offset, M2-S4 reference M2S4R-offset): fails exactly {sorted(expect)} beyond its base\n"
          f"      failed {sorted(fc - fb)} (base fails {sorted(fb)}); signature {'OK' if sig else 'WRONG'}: NW-TT node FCS-checker "
          f"drops {drops} = Follow_Ups received; Follow_Ups in the 5GS {len(C.sel(R.nw0, 2, C.FU))}; slave steps {len(m.out['fu'])}; "
          f"slave clock error at the samples {sorted(set(round(e * 1e12) for e in pre))[:3]} ps; S3o: {rc['S3'][1][:220]}; base S3o: {rb['S3'][1][:220]}")
    print(f"\nOVERALL: {'PASS' if ok_all else 'FAIL'}")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit({"full": full, "c8demo": c8demo, "controls": controls}[MODE]())
