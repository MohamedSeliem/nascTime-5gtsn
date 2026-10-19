"""M2-S6 TT clock model (migration/m2-s6-design.md rev. 2, 2.3): an independent re-statement of the A2
clock function and measurement, from the design's definitions (not from TtClock.cc).

    C_T(s) = s + theta0 + floor((2e12 * y * (s - u(s)) + D * (s - u(s))^2) / 2e21)     [ps; y ppb, D ppb/s]
    u(s)   = phi + U * floor((s - phi) / U)   (U = 0: u = 0)
    tau    = L * floor((C_T(s) + w) / L)

Timestamp kinds (TtClockAccess.h): 1 TSi, 2 TSe, 3 t1, 4 t2, 5 t3, 6 t4, 7 t1End, 8 t3End, 9 t4End.
"""
import csv
import os
from fractions import Fraction

KINDS = {1: "TSi", 2: "TSe", 3: "t1", 4: "t2", 5: "t3", 6: "t4", 7: "t1End", 8: "t3End", 9: "t4End"}
TEST_KINDS = (7, 8, 9)


def tt(theta0=0, y=0, D=0, U=0, phi=0, sigma=0, L=1):
    """TT clock parameters (ps, ppb, ppb/s, ps, ps, ps, ps)."""
    return {"theta0": theta0, "y": y, "D": D, "U": U, "phi": phi, "sigma": sigma, "L": L}


def last_update(p, s):
    if p["U"] == 0:
        return 0
    return p["phi"] + p["U"] * ((s - p["phi"]) // p["U"])


def osc_term(p, s):
    d = s - last_update(p, s)
    return (2 * 10 ** 12 * p["y"] * d + p["D"] * d * d) // (2 * 10 ** 21)


def clock(p, s):
    return s + p["theta0"] + osc_term(p, s)


def measure(p, s, w):
    return p["L"] * ((clock(p, s) + w) // p["L"])


def components(p, s, w):
    """tau - s = theta0 + theta_osc + w + q exactly (design 2.3)."""
    c = clock(p, s)
    tau = measure(p, s, w)
    return {"theta0": p["theta0"], "osc": c - s - p["theta0"], "w": w, "q": tau - (c + w)}


def read_log(path):
    if not os.path.exists(path):
        return []
    with open(path) as fh:
        return [{k: int(v) for k, v in r.items()} for r in csv.DictReader(fh)]


def ci95_std(values):
    """Sample standard deviation with an approximate 95 % interval (normal approximation of the
    sampling distribution of s: s * (1 +- 1.96 / sqrt(2 (n - 1))))."""
    n = len(values)
    if n < 3:
        return None
    m = sum(values) / n
    s = (sum((v - m) ** 2 for v in values) / (n - 1)) ** 0.5
    h = 1.96 / (2 * (n - 1)) ** 0.5
    return m, s, s * (1 - h), s * (1 + h), n


def frac(x):
    return Fraction(x)
