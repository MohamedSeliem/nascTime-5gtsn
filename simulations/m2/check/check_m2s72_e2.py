#!/usr/bin/env python3
"""M2-S7.2a Stage 5 E2 (DL-only) configuration-level checker: PREPARATION ONLY (decision 2026-11-03 20:05, items 3-5).
Protocol, predictions and acceptance criteria: results/M2-S7.2a-e2-protocol.md (committed before any E2 run).

    check_m2s72_e2.py run <runs dir> <E2 config> [...]         E2 configuration rows of each run -> stdout
    check_m2s72_e2.py rebaseline <OUT> <E0 OUT>                  step-0 acceptance checkpoint (4 runs) -> stdout
    check_m2s72_e2.py controls <E0 OUT>                          the row controls, read-only on the E0 raw outputs

Rows of every E2 run (the E0 run-level gates are added for the N = 1 re-baseline by `rebaseline`):
  CFG-ident    the run's .sca records exactly the generated `extends` list of its configuration (m2s72_gen.e2_section)
  CFG-rate-DL  the DL load sources produce exactly the configured frames: at the listener egress, from 0.3005 s, every
               nominal-rounded interval (integer ns, exact ps), one stream per loaded UE (multiset of timestamps:
               n_loaded frames per slot); per load app (listener.app[LA_j] -> talker[k], fixed by the verified
               configuration) the source packet count equals the stream length; the sum equals the egress count;
               non-loaded UEs receive no load app
  NO-UL        no UL load exists: (a) no talker[k].app[3] configuration entry and no talker[k].app[3] statistic in the
               .sca; (b) 0 load frames (pcp 0, VLAN 42, 1400 B) at every talker[k] egress; (c) 0 load frames at the
               listener ingress
  DL-active (info)  diag_m2s72_dl_active per DL connection: backlogged TTIs in which the connection is not a scheduler
               candidate (reported; never interpreted as loss; never a gate)
Missing evidence (a file or statistic absent) makes a row FAIL ("missing evidence"), never a silent PASS.
"""
import csv
import importlib.util
import os
import re
import sys
import tempfile
from collections import Counter
from fractions import Fraction

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_e0 as E  # noqa: E402
import diag_m2s72_dl_active as D  # noqa: E402
sys.argv = _argv

_spec = importlib.util.spec_from_file_location("m2s72_gen", os.path.join(M2, "tools", "m2s72_gen.py"))
G = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(G)

S, MS, US, NS = 10 ** 12, 10 ** 9, 10 ** 6, 10 ** 3
NET = "M2S72Bridge"
T_END = 12 * S
DL_START = 300500 * MS // 1000
LOAD_LEN = 1400
PASS, FAIL, INFO = "PASS", "FAIL", "INFO"
rows = []
_generated = False


def gen():
    global _generated
    if not _generated:
        G.INI, G.M2, G.OUT = os.path.join(M2, "omnetpp.ini"), M2, os.path.join(M2, "m2s72.ini")
        text, _ = G.generate()
        _generated = text
    return _generated


def add(row, run, status, detail):
    rows.append((row, run, status, detail))
    print(f"{status} | {row} | {run} | {detail}")


def parse_cfg(cfg):
    m = re.fullmatch(r"M2S72-E2(H5)?-(q0|qdu)-(one0|sym)-n(\d+)-f([0-9p]+)", cfg)
    if not m:
        raise ValueError(f"{cfg}: not an E2 configuration name")
    f = Fraction(m.group(5).replace("p", "."))
    return {"h5": bool(m.group(1)), "opt": m.group(2), "pl": m.group(3), "n": int(m.group(4)), "f": f,
            "src": f"M2S71-{m.group(2)}-Ca-sus@L"}


def ini_ps(v):
    m = re.fullmatch(r"(\d+)(ns|us)", v)
    if not m:
        raise ValueError(f"interval {v!r}")
    return int(m.group(1)) * (NS if m.group(2) == "ns" else US)


def expected_streams(cfg):
    """{listener app index: (talker index, interval ps)} of the configuration, from the generator's own spec"""
    c = parse_cfg(cfg)
    gen()
    f = float(c["f"]) if c["f"].denominator != 1 else int(c["f"])
    spec, ues, dl, ul = G.load_spec(c["src"], c["pl"], c["n"], f, 0, nominal=True)
    if ul is not None:
        raise ValueError(f"{cfg}: E2 spec with UL load")
    out = {}
    for (mod, rest), v in spec.items():
        m = re.fullmatch(r"listener\.app\[(\d+)\]", mod)
        if m and rest == "io.remoteAddress":
            out[int(m.group(1))] = (int(re.fullmatch(r'"talker\[(\d+)\]"', v).group(1)), ini_ps(spec[(mod, "source.productionInterval")]))
    if sorted(t for t, _ in out.values()) != ues:
        raise ValueError(f"{cfg}: load apps {out} do not cover the loaded UEs {ues}")
    return out, ues


def stream(iv, T=T_END, start=DL_START):
    n = (T - start) // iv + 1 if T >= start else 0
    return [start + iv * i for i in range(n)]


def sca_lines(path):
    with open(path) as fh:
        return fh.read().split("\n")


def sca_scalar(lines, module, name):
    for line in lines:
        if line.startswith("scalar "):
            p = line.split(" ")
            if len(p) == 4 and p[1] == module and p[2] == name:
                return int(float(p[3]))
    return None


def sca_config(lines):
    """the run's configuration entries [(key, value)] in ini (first-match) order, as recorded in the .sca"""
    out = []
    for l in lines:
        if l.startswith("config "):
            p = l.split(" ", 2)
            out.append((p[1], p[2] if len(p) > 2 else ""))
    return out


def rate_rows(name, streams, egress_ts, sca, T=T_END):
    """CFG-rate-DL on explicit evidence: streams {app: (talker, iv)}, egress_ts the listener-egress load-frame times"""
    probs = []
    if egress_ts is None or sca is None:
        add("CFG-rate-DL", name, FAIL, "missing evidence (listener egress log or .sca)")
        return False
    exp = Counter()
    per_app = {}
    for a, (k, iv) in sorted(streams.items()):
        st = stream(iv, T)
        exp.update(st)
        per_app[a] = len(st)
        got = sca_scalar(sca, f"{NET}.listener.app[{a}].source", "packets:count")
        if got is None:
            probs.append(f"listener.app[{a}] (-> talker[{k}]): no source packets:count statistic")
        elif not (len(st) - 1 <= got <= len(st)):
            probs.append(f"listener.app[{a}] (-> talker[{k}]): {got} packets, expected {len(st) - 1}..{len(st)}")
    got = Counter(egress_ts)
    last = max(exp) if exp else None
    body_exp = Counter({t: c for t, c in exp.items() if t != last})
    body_got = Counter({t: c for t, c in got.items() if t != last})
    if body_got != body_exp:
        extra, miss = body_got - body_exp, body_exp - body_got
        probs.append(f"egress timestamps differ from the configured streams: {sum(extra.values())} unexpected (first "
                     f"{sorted(extra)[:2]}), {sum(miss.values())} missing (first {sorted(miss)[:2]})")
    if last is not None and not (0 <= got.get(last, 0) <= exp[last]):
        probs.append(f"last slot {last}: {got.get(last, 0)} frames, expected <= {exp[last]}")
    apps_total = sum(sca_scalar(sca, f"{NET}.listener.app[{a}].source", "packets:count") or 0 for a in streams)
    if apps_total != len(egress_ts):
        probs.append(f"load-app packets {apps_total} != listener egress load frames {len(egress_ts)}")
    ivs = sorted({iv for _, iv in streams.values()})
    add("CFG-rate-DL", name, PASS if not probs else FAIL,
        f"{len(streams)} DL load stream(s) to talker{sorted(k for k, _ in streams.values())}, every {[iv / US for iv in ivs]} us from "
        f"{DL_START / S} s, {len(egress_ts)} frames, exact" + ("" if not probs else "; FAIL " + "; ".join(probs)))
    return not probs


def noul_rows(name, n, talker_egress, listener_ingress, sca):
    """NO-UL on explicit evidence: talker_egress {k: load-frame times or None}, listener_ingress load-frame times"""
    probs = []
    if sca is None:
        probs.append("missing evidence: .sca")
    else:
        ents = sca_config(sca)
        cfgl = []
        for k, v in ents:                         # an entry whose module part can address talker[kk].app[3]
            j = k.find(".app[")
            if j < 0:
                continue
            e = k.index("]", j)
            if any(G.pat_re(k[:j]).match(f"{NET}.talker[{kk}]") for kk in range(n)) and G.pat_re(f"x[{k[j + 5:e]}]").match("x[3]"):
                cfgl.append(f"{k} = {v}")
        for kk in range(n):
            key, val = G.first_match(ents, f"talker[{kk}].numApps")
            if val != str(G.LISTENER_APPS):
                probs.append(f"talker[{kk}].numApps = {val!r} (from {key!r}), expected {G.LISTENER_APPS}")
        st = [l for l in sca if l.startswith(("scalar ", "statistic ")) and re.search(rf"{NET}\.talker\[\d+\]\.app\[3\]", l)]
        if cfgl:
            probs.append(f"{len(cfgl)} configuration entries can address a talker app[3] (first {cfgl[0][:90]!r})")
        if st:
            probs.append(f"{len(st)} talker[k].app[3] statistics (first {st[0][:90]!r})")
    for k in range(n):
        ts = talker_egress.get(k)
        if ts is None:
            probs.append(f"missing evidence: talker[{k}] egress log")
        elif ts:
            probs.append(f"talker[{k}]: {len(ts)} UL load frames at egress (first {ts[0] / S} s)")
    if listener_ingress is None:
        probs.append("missing evidence: listener ingress log")
    elif listener_ingress:
        probs.append(f"listener: {len(listener_ingress)} UL load frames at ingress")
    add("NO-UL", name, PASS if not probs else FAIL,
        f"no UL load app or statistic on talker[0..{n - 1}], 0 UL load frames at {n} talker egress and the listener ingress"
        + ("" if not probs else "; FAIL " + "; ".join(probs)))
    return not probs


def ident_row(name, cfg, sca):
    gen()
    ext = {}
    G.e2_section(ext)
    exp = ", ".join(ext.get(cfg, []))
    got = next((l.split(" ", 2)[2].strip('"') for l in (sca or []) if l.startswith("config extends ")), None)
    ok = bool(exp) and got == exp
    add("CFG-ident", name, PASS if ok else FAIL, f"extends = {got!r}" + ("" if ok else f"; expected {exp!r}"))
    return ok


def frames(path):
    return E.csv_frames(path) if os.path.exists(path) else None


def evidence(runs, cfg):
    ldir = os.path.join(runs, cfg, "m2log", f"{cfg}-0")
    sca_p = os.path.join(runs, cfg, cfg, "0.sca")
    sca = sca_lines(sca_p) if os.path.exists(sca_p) else None
    n = parse_cfg(cfg)["n"] if cfg.startswith("M2S72-E2") else 1
    return {"sca": sca,
            "egress": frames(os.path.join(ldir, f"{NET}.listener.eth[0].measurementLayer.egress.csv")),
            "lingress": frames(os.path.join(ldir, f"{NET}.listener.eth[0].measurementLayer.ingress.csv")),
            "talker": {k: frames(os.path.join(ldir, f"{NET}.talker[{k}].eth[0].measurementLayer.egress.csv")) for k in range(n)}}


def dl_active_rows(runs, cfg):
    try:
        res = D.analyse(runs, cfg)
    except Exception as ex:                      # reported, never a gate
        add("DL-active (info)", f"{cfg}-0", INFO, f"NOT EVALUATED ({type(ex).__name__}: {ex})")
        return None
    for r in res:
        add("DL-active (info)", f"{cfg}-0 {r['node']}-{r['drb']}", INFO,
            f"backlogged TTIs {r['backlogged_ttis']}, candidate TTIs {r['candidate_ttis']}, DEACTIVATED {r['deactivated']} "
            f"(with arrival {r['with_arrival']}, without {r['no_arrival']}, after a capped grant {r['after_capped_grant']}), "
            f"first {r['first_deactivated_ttis']}, grants {r['grants']} ({r['capped_grants']} capped)")
    return res


def run_rows(runs, cfg, diag=True):
    c = parse_cfg(cfg)
    name = f"{cfg}-0"
    ev = evidence(runs, cfg)
    streams, ues = expected_streams(cfg)
    ok = ident_row(name, cfg, ev["sca"])
    ok &= rate_rows(name, streams, ev["egress"], ev["sca"])
    ok &= noul_rows(name, c["n"], ev["talker"], ev["lingress"], ev["sca"])
    if diag:
        dl_active_rows(runs, cfg)
    return ok


# ------------------------------------------------------------------------------- step-0 re-baseline (4 runs) ----
RB_RUNS = [("q0", 1), ("qdu", 1), ("q0", 2), ("qdu", 2)]
RB_CAP_TOL = 0.01          # RB-3: achieved DL RLC throughput within 1 % (relative) of E0, same option and factor
RB_F1_SERVED = 0.99        # RB-3: F = 1 achieved >= 0.99 x offered


def e0_metrics(e0out):
    path = os.path.join(e0out, "..", "M2-S7.2a-e0r2", "e0-metrics.csv")
    with open(path) as fh:
        return {r["run"]: r for r in csv.DictReader(fh)}


def rebaseline(out, e0out):
    """acceptance checkpoint: RB-1 E0 run-level gates (CFG-rate replaced by CFG-rate-DL + NO-UL), RB-2 CFG rows,
    RB-3 DL capacity vs E0; RB-P* predictions reported (not acceptance rows), see the protocol"""
    runs = os.path.join(out, "runs")
    ref = e0_metrics(e0out)
    acc = True
    for opt, f in RB_RUNS:
        cfg = f"M2S72-E2-{opt}-one0-n1-f{f}"
        name = f"{cfg}-0"
        if not os.path.isdir(os.path.join(runs, cfg)):
            add("RB", name, FAIL, "missing evidence: run directory absent")
            acc = False
            continue
        rb2 = run_rows(runs, cfg)
        E.cfg_rate = lambda *a, **k: None          # E0's UL-loaded CFG-rate replaced by CFG-rate-DL + NO-UL above
        if f == 1:
            E.LOSS_FREE.add(cfg)                   # F0-1 gated at F = 1, as for E0 (protocol §4, RB-1)
        start = len(E.rows)
        ev, q, m, fails = E.evaluate(runs, cfg, opt, f, os.path.join(runs, f"run-{cfg}.log.gz"))
        for r in E.rows[start:]:
            print(f"  E0-gate | {r[2]} | {r[0]} | {r[1]} | {str(r[3])[:160]}")
        add("RB-1", name, PASS if not fails else FAIL, f"E0 run-level gates (E0 protocol §3 scoping): {len(E.rows) - start} rows, "
            f"failed {sorted(fails) if fails else 'none'}")
        add("RB-2", name, PASS if rb2 else FAIL, "CFG-ident, CFG-rate-DL and NO-UL")
        r = ref[f"M2S72-E0-{opt}-f{f}-0"]
        a, a0, off = m["dl_achieved_rlc_Mbps"], float(r["dl_achieved_rlc_Mbps"]), m["dl_offered_rlc_Mbps"]
        ok3 = abs(a - a0) / a0 <= RB_CAP_TOL and (f != 1 or a >= RB_F1_SERVED * off)
        add("RB-3", name, PASS if ok3 else FAIL, f"DL achieved {a:.4f} Mb/s vs E0 {a0:.4f} (tolerance {RB_CAP_TOL:.0%})"
            + (f"; offered {off:.4f}, served fraction {a / off:.4f} (>= {RB_F1_SERVED})" if f == 1 else ""))
        acc &= (not fails) and rb2 and ok3
        for k in ("censored_cohort_fraction", "res_p50_ms", "res_p99_ms", "max_e_ns", "holds", "mac_max_busy_harq", "ul_achieved_Mbps"):
            add("RB-P (info)", name, INFO, f"{k}: E2 {m.get(k, 'n/a')} | E0 {r.get(k)}")
    add("RB checkpoint", "step 0", PASS if acc else FAIL, "ACCEPTED: the sweep may be proposed" if acc
        else "NOT ACCEPTED: STOP, report, no further E2 run")
    return acc


# ---------------------------------------------------------------------------------------------- row controls ----
def controls(e0out):
    """read-only on E0 raw outputs (UL-loaded, N = 1) and synthetic evidence; every control's outcome is declared in
    the protocol §6 before any E2 run"""
    runs = os.path.join(e0out, "runs")
    res = []

    def ctl(label, fn, want):
        start = len(rows)
        fn()
        got = [r[2] for r in rows[start:] if r[0] in ("CFG-rate-DL", "NO-UL", "CFG-ident")]
        ok = bool(got) and all(g == want for g in got)
        res.append(ok)
        print(f"{'PASS' if ok else 'FAIL'} | control {label} | rows {got} (expected all {want})")

    for f in (1, 2):
        cfg = f"M2S72-E0-q0-f{f}"
        ev = evidence(runs, cfg)
        e2 = f"M2S72-E2-q0-one0-n1-f{f}"          # same DL load spec as E0 at N = 1 (exact factor)
        streams, _ = expected_streams(e2)
        if streams != {3: (0, 250 * US // f)}:
            raise SystemExit(f"control premise: {e2} streams {streams}")
        ctl(f"PC-rate-e0-f{f} (E0 DL source = E2 one0 n1 spec)", lambda: rate_rows(f"{cfg}-0", streams, ev["egress"], ev["sca"]), PASS)
        if f == 1:
            ctl("NC-rate-drop (one egress frame removed)", lambda: rate_rows(f"{cfg}-0 [mut]", streams, ev["egress"][:100] + ev["egress"][101:], ev["sca"]), FAIL)
            ctl("NC-rate-shift (one frame + 1 ps)", lambda: rate_rows(f"{cfg}-0 [mut]", streams, [t + (i == 500) for i, t in enumerate(ev["egress"])], ev["sca"]), FAIL)
            sca_m = [l.replace("packets:count 46799", "packets:count 46797") if "listener.app[3].source" in l else l for l in ev["sca"]]
            ctl("NC-rate-appcount (load-app statistic altered)", lambda: rate_rows(f"{cfg}-0 [mut]", streams, ev["egress"], sca_m), FAIL)
            ctl("NC-rate-noevidence (egress log absent)", lambda: rate_rows(f"{cfg}-0 [mut]", streams, None, ev["sca"]), FAIL)
            ctl("NC-noul-e0 (E0 has UL load)", lambda: noul_rows(f"{cfg}-0", 1, ev["talker"], ev["lingress"], ev["sca"]), FAIL)
            sca_f = [("config *.talker[0].numApps 3" if l == "config *.talker[0].numApps 4" else l)
                     for l in ev["sca"] if not re.search(r"talker\[[^\]]*\]\.app\[3\]", l)]
            if "config *.talker[0].numApps 3" not in sca_f:
                raise SystemExit("control premise: E0 .sca without the talker[0].numApps 4 entry")
            ctl("PC-noul-filtered (E0 evidence with every UL load frame, entry and statistic removed)",
                lambda: noul_rows(f"{cfg}-0 [filtered]", 1, {0: []}, [], sca_f), PASS)
            ctl("NC-noul-stat (one talker app[3] statistic only)",
                lambda: noul_rows(f"{cfg}-0 [mut]", 1, {0: []}, [], sca_f + [f"scalar {NET}.talker[0].app[3].source packets:count 1"]), FAIL)
            ctl("NC-noul-frame (one UL load frame at talker[0] egress)", lambda: noul_rows(f"{cfg}-0 [mut]", 1, {0: [ev['talker'][0][0]]}, [], sca_f), FAIL)
            ctl("NC-noul-numapps (talker[0].numApps 4 restored, nothing else)",
                lambda: noul_rows(f"{cfg}-0 [mut]", 1, {0: []}, [], [("config *.talker[0].numApps 4" if l == "config *.talker[0].numApps 3" else l) for l in sca_f]), FAIL)
            ctl("NC-noul-noevidence (talker[0] egress log absent)", lambda: noul_rows(f"{cfg}-0 [mut]", 1, {0: None}, [], sca_f), FAIL)
            ctl("NC-ident-e0 (E0 extends is not an E2 configuration)", lambda: ident_row(f"{cfg}-0", e2, ev["sca"]), FAIL)
    # synthetic multi-UE (no N > 1 loaded run exists): sym n4 factor 1.1, one0 n8 factor 1.3
    for cfg in ("M2S72-E2-qdu-sym-n4-f1p1", "M2S72-E2-q0-one0-n8-f1p3"):
        streams, ues = expected_streams(cfg)
        ts = sorted(t for _, iv in streams.values() for t in stream(iv))
        sca = [f"scalar {NET}.listener.app[{a}].source packets:count {len(stream(iv))}" for a, (k, iv) in streams.items()]
        ctl(f"PC-rate-synth {cfg} ({len(streams)} streams)", lambda: rate_rows(f"{cfg} [synthetic]", streams, ts, sca), PASS)
        if len(streams) > 1:
            k0 = min(streams)
            sca_m = [l for l in sca if f"app[{k0}]." not in l]
            ctl(f"NC-rate-synth-missing-stream {cfg}", lambda: rate_rows(f"{cfg} [mut]", streams, sorted(t for a, (_, iv) in streams.items() if a != k0 for t in stream(iv)), sca_m), FAIL)
            ctl(f"NC-rate-synth-doubled-stream {cfg}", lambda: rate_rows(f"{cfg} [mut]", streams, sorted(ts + stream(streams[k0][1])), sca), FAIL)
        ctl(f"PC-ident-synth {cfg}", lambda: ident_row(f"{cfg} [synthetic]", cfg, [f'config extends "{", ".join(_ext()[cfg])}"']), PASS)
    # the DL deactivation diagnostic's own self-test (E0 Q-d F = 2)
    ok = D.selftest(runs, "M2S72-E0-qdu-f2")
    res.append(ok)
    print(f"E2 row controls: {sum(res)} / {len(res)} as declared")
    return all(res)


def _ext():
    gen()
    ext = {}
    G.e2_section(ext)
    return ext


def main():
    mode = sys.argv[1]
    if mode == "run":
        ok = all([run_rows(sys.argv[2], c) for c in sys.argv[3:]])
        sys.exit(0 if ok else 1)
    if mode == "rebaseline":
        sys.exit(0 if rebaseline(sys.argv[2], sys.argv[3]) else 1)
    if mode == "controls":
        sys.exit(0 if controls(sys.argv[2]) else 1)
    print(__doc__)
    sys.exit(2)


if __name__ == "__main__":
    main()
