"""M2-S7.2a Checkpoint 2 supplementary diagnostics (not gates; read-only on a cp2 record).

1. Per Block B run (N = 2, 4; all seeds): number of common Follow_Ups whose path-specific instants
   (DS-TT egress se, slave reception s2, update sF, residence se - si) differ between slaves.
2. E-all: DS-TT 1 TT-clock noise w at N = 2 vs N = 4 (same seed): equal at every common stamp instant and per
   update interval (U = 10 ms, phi = 4 ms, design D-13) -> DS-TT 1 draws from its own stream.
Usage: python3 diag_m2s72_cp2.py <cp2 OUT dir>
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_b as B  # noqa: E402
sys.argv = _argv


def instants(runs):
    print("1. per run: common Follow_Ups | Follow_Ups whose se / s2 / sF / Res differ between slaves")
    for opt in B.OPTS:
        for clk in B.CLKS:
            for n in B.NS_B:
                for rep in B.REPS:
                    cfg = f"M2S72-B-{opt}-{clk}-n{n}"
                    ev = B.RunEval(runs, cfg, rep)
                    T = {k: ev.series[k]["terms"] for k in ev.series}
                    com = sorted(set.intersection(*[set(t) for t in T.values()]))
                    d = lambda key: sum(1 for s in com if len({T[k][s]["f"][key] for k in T}) > 1)  # noqa: E731
                    print(f"{cfg}-{rep} | {len(com)} | se {d('se')} s2 {d('s2')} sF {d('sF')} Res {d('Res_s')}")


def noise(runs):
    U, phi = 10 * B.MS, 4 * B.MS
    print("\n2. E-all DS-TT 1 noise w, N = 2 vs N = 4 (same seed)")
    for opt in B.OPTS:
        for rep in B.REPS:
            p = lambda n: os.path.join(runs, f"M2S72-B-{opt}-Eall-n{n}", "m2log", f"M2S72-B-{opt}-Eall-n{n}-{rep}",  # noqa: E731
                                       "M2S72Bridge.dsTt[1].eth[1].trafficConditionerLayer.ttClock.ttclock.csv")
            w = [{int(r["s"]): int(r["w"]) for r in csv.DictReader(open(p(n)))} for n in (2, 4)]
            com = set(w[0]) & set(w[1])
            iv = [{}, {}]
            for x in (0, 1):
                for s, v in w[x].items():
                    iv[x].setdefault((s - phi) // U, set()).add(v)
            ci = set(iv[0]) & set(iv[1])
            print(f"{opt}-{rep} | common instants {len(com)}: equal w {sum(w[0][s] == w[1][s] for s in com)} | "
                  f"common update intervals {len(ci)}: equal {sum(iv[0][i] == iv[1][i] for i in ci)}")


if __name__ == "__main__":
    runs = os.path.join(sys.argv[1], "runs")
    instants(runs)
    noise(runs)
