#!/usr/bin/env python3
"""M1-S2 addendum: controlled phase-offset test of the slot-alignment explanation.

S2 measured delay(S2) - delay(S1) = +1090 ns, one translator hop, and explained it:
the 5G system releases frames on slot boundaries, so the translator IN FRONT of the
5G system (1090 ns: 1040 ns store-and-forward + 50 ns cable) is absorbed as long as
the later arrival still makes the same slot. That explanation predicts where it must
break, and this test checks that prediction.

Every flow's frames are generated at one phase within the slot. Shifting all
generation times by a phase offset p (added to initialProductionOffset):
  1. Measure on S1 ALONE, per direction, the smallest p at which frames miss their
     slot ("cross"): below it, every delay sample equals delay(p=0) - p (same release
     instant); at it, they do not. Found by bisection to 1 ns on short runs.
     Call it p1.
  2. Prediction: S2's frames arrive 1090 ns later, so S2 crosses at p1 - 1090 ns.
     Hence delay(S2) - delay(S1) must be exactly 1090 ns for p < p1 - 1090 and for
     p >= p1 (both or neither cross), and must NOT be 1090 ns for
     p1 - 1090 <= p < p1 (only S2 crosses).
  3. Check it with full-length runs of S1 and S2 at four phases per direction, 1 ns
     either side of both predicted edges: p1-1091, p1-1089, p1-1, p1+1.

usage: s2_phase.py run <out dir>      (needs opp_run on PATH; see s2_phase_offset.sh)
       s2_phase.py check <out dir>
"""
import json
import os
import subprocess
import sys

HOP_NS = 1090
SINK = {"UL": "listener.app[2].sink", "DL": "talker.app[2].sink"}
OFFSET_KEY = "**.app[0..1].source.initialProductionOffset"
TOL = 1e-12          # s; delays are doubles of ps-resolution simulation times


def read_vec(path):
    """meanBitLifeTimePerPacket samples per sink, from an OMNeT++ .vec file."""
    ids, out = {}, {d: [] for d in SINK}
    for line in open(path):
        if line.startswith("vector "):
            parts = line.split()
            mod = parts[2].split(".", 1)[1]
            if parts[3] == "meanBitLifeTimePerPacket:vector":
                for d, m in SINK.items():
                    if mod == m:
                        ids[parts[1]] = d
        elif line[:1].isdigit():
            parts = line.split()
            if parts[0] in ids:
                out[ids[parts[0]]].append(float(parts[3]))
    return out


def run(env, config, phase_ns, simtime, out):
    rd = os.path.join(out, f"{config}-p{phase_ns}-{simtime}")
    vec = os.path.join(rd, config, "0.vec")
    if not os.path.exists(vec):
        cmd = ["opp_run", "-l", env["SIMU5G_ROOT"] + "/src/simu5g",
               "-n", f'{env["NASCTIME"]}/simulations:{env["NASCTIME"]}/src:{env["SIMU5G_ROOT"]}/src:{env["INET_ROOT"]}/src',
               "-x", "nasctime.nodes", "-u", "Cmdenv", "-f", "omnetpp.ini", "-c", config, "-r", "0",
               f"--result-dir={rd}", "--cmdenv-express-mode=true", f"--sim-time-limit={simtime}",
               f"--{OFFSET_KEY}=0.1s + 5ms * ancestorIndex(1) + {phase_ns}ns"]
        with open(os.path.join(out, "runs.log"), "a") as log:
            log.write(" ".join(cmd) + "\n")
            log.flush()
            r = subprocess.run(cmd, cwd=env["HERE"], stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
            if r.returncode != 0 or "<!> Error" in r.stdout:
                log.write(r.stdout)
                sys.exit(f"run failed: {config} phase {phase_ns}")
    return read_vec(vec)


def crossed(base, cur, phase_ns):
    """True unless every sample equals the phase-0 sample minus the phase."""
    if len(base) != len(cur) or not base:
        return True
    return any(abs((b - phase_ns * 1e-9) - c) > TOL for b, c in zip(base, cur))


def do_run(out):
    env = {k: os.environ[k] for k in ("SIMU5G_ROOT", "INET_ROOT", "NASCTIME", "HERE")}
    os.makedirs(out, exist_ok=True)
    short = "0.17s"     # frames generated at 0.100..0.165 s: 4 per flow
    base = run(env, "S1", 0, short, out)
    p1, probes = {}, {}
    for d in SINK:
        lo, hi = 0, 999_999
        probes[d] = []
        assert not crossed(base[d], run(env, "S1", lo, short, out)[d], lo)
        assert crossed(base[d], run(env, "S1", hi, short, out)[d], hi), f"{d}: no crossing below 1 ms"
        while hi - lo > 1:
            mid = (lo + hi) // 2
            c = crossed(base[d], run(env, "S1", mid, short, out)[d], mid)
            probes[d].append((mid, c))
            lo, hi = (lo, mid) if c else (mid, hi)
        p1[d] = hi
    points = {d: [p1[d] - HOP_NS - 1, p1[d] - HOP_NS + 1, p1[d] - 1, p1[d] + 1] for d in SINK}
    full = {}
    for d in SINK:
        for p in points[d]:
            for cfg in ("S1", "S2"):
                full[f"{cfg}:{d}:{p}"] = run(env, cfg, p, "5s", out)[d]
    json.dump({"p1_ns": p1, "points_ns": points, "probes": probes, "full": full},
              open(os.path.join(out, "phase.json"), "w"))


def do_check(out):
    j = json.load(open(os.path.join(out, "phase.json")))
    rows = []
    for d in SINK:
        p1 = j["p1_ns"][d]
        rows.append((f"{d}: S1 crossing phase p1 (bisection, 1 ns)",
                     f"p1 = {p1} ns: frames arriving {p1 + HOP_NS} ns or later after the slot start miss it "
                     f"(S1 arrival = generation + 1040 ns + 50 ns); {len(j['probes'][d])} probes", True))
        for p in j["points_ns"][d]:
            s1, s2 = j["full"][f"S1:{d}:{p}"], j["full"][f"S2:{d}:{p}"]
            only_s2 = p1 - HOP_NS <= p < p1
            n = min(len(s1), len(s2))
            sh = [(b - a) * 1e9 for a, b in zip(s1, s2)]
            at_hop = [abs(x - HOP_NS) <= 1e-3 for x in sh]
            if only_s2:
                ok = n > 0 and not any(at_hop)
                exp = "only S2 crosses: shift != 1090 ns for every packet"
            else:
                ok = n > 0 and len(s1) == len(s2) and all(at_hop)
                exp = ("neither crosses" if p < p1 else "both cross") + ": shift == 1090 ns for every packet"
            rng = f"{min(sh):.3f}..{max(sh):.3f} ns" if sh else "no samples"
            rows.append((f"{d}: p = {p} ns (p1{p - p1:+d})", f"{exp}; {n} packets, shift {rng}", ok))
    w = max(len(r[0]) for r in rows)
    for c, det, ok in rows:
        print(f"{'PASS' if ok else 'FAIL':4}  {c:<{w}}  {det}")
    print()
    print("OVERALL:", "PASS" if all(r[2] for r in rows) else "FAIL")


if __name__ == "__main__":
    {"run": do_run, "check": do_check}[sys.argv[1]](sys.argv[2])
