#!/usr/bin/env python3
"""M2-S7.2a Stage 5, increment S5-2: measurement-driven selection of the common E1 load factor f_E1 (plan rev. 1.1
RD-2; addendum results/M2-S7.2a-s5-2-addendum.md §5). Pure decision logic over per-run outcomes; no simulation, no
raw-output reading. Tested in test_m2s72s5_2.py.

Terms
  combination c   one E1 loaded group: (option, placement, N, HARQ)   e.g. ("q0", "sym", 4, 16)
  ladder          the declared candidate factors (plan rev. 1.1): 0.5, 0.8, 1, 1.25, 1.6, 2 (exact ns intervals)
  outcome         of one bracket run (seed 0) of c at factor f, from the per-UE evaluation (m2s72_peru.across):
                    'ok'         no loaded UE overloaded, no UE starved (ST-* / US-*), correctness gates PASS
                    'overloaded' at least one UE overloaded by the accepted definition (per UE), gates PASS
                    'starved'    no UE overloaded but some UE starved (a scheduler effect, not a capacity limit)
                    'invalid'    a correctness gate failed, a non-OK run outcome (SIM-ABORT / TIMEOUT / ERROR), or a
                                 per-UE class not evaluable: never a capacity result; the bracket stops for review
  bracket of c    f_lo = the largest ladder factor with outcome 'ok' below every non-'ok' factor; f_hi = the smallest
                  ladder factor with a non-'ok' outcome ('overloaded' or 'starved')

Procedure (per combination; one run at a time; seed 0, as E0 [A])
  B-1 start   at the declared start factor (default 1.0; with the approved HARQ5 economy, the HARQ16 f_lo of the same
              (option, placement, N))
  B-2 step    'ok' -> the next higher ladder factor; non-'ok' -> the next lower; stop when both a confirmed 'ok' f_lo
              and a non-'ok' f_hi adjacent on the ladder are known, plus ONE confirmation run above f_hi (E0 [A]
              escalation rule: "plus one above for confirmation") when f_hi is not the top of the ladder
  B-3 monotonicity   an 'ok' above a non-'ok' (or a confirmation run that is 'ok') is NON-MONOTONE: the bracket stops
              for review; no f_lo is reported
  B-4 edges   'ok' at the top of the ladder: f_lo = top, f_hi = None (capacity above the ladder: reported, not
              extrapolated); non-'ok' at the bottom: f_lo = None -> f_E1 cannot be chosen (STOP)
Selection
  S-1 f_E1 = the largest ladder factor <= (1 - m) x min_c f_lo(c), over every E1 loaded combination; m is a declared
      margin (proposed 0.20, a candidate, not a guarantee); a combination with f_lo = None or an unfinished bracket
      makes the selection impossible (STOP for review); nothing is extrapolated across N, option or HARQ
  S-2 sensitivity: f_E1 is also reported for m in {0.10, 0.20, 0.30}, with the binding combination
  S-3 the margin is validated, not assumed: every E1 loaded configuration is run at f_E1 with seeds 0-4 (V-1..V-4)
Verification (f_E1 entry gate of E1; per run, every UE)
  V-1 no UE overloaded (accepted definition, per UE)
  V-2 no starvation class holds for any UE (ST-dl, ST-ul, ST-gptp, US-dl, US-ul)
  V-3 every loaded UE: achieved >= (1 - SERVICE_TOL) x offered, DL and UL, over [t0, T)
  V-4 every correctness gate PASS (per-UE PU rows included)
  Any failure: E1 does not start; the failing (configuration, seed, UE, class) is reported for review. No automatic
  fallback to a lower factor (RD-2).
"""
LADDER = (0.5, 0.8, 1.0, 1.25, 1.6, 2.0)
OUTCOMES = ("ok", "overloaded", "starved", "invalid")
MARGINS = (0.10, 0.20, 0.30)
SERVICE_TOL = 0.01


def classify(across, gates_pass, run_outcome="OK"):
    """outcome of one bracket run from m2s72_peru.across() of that run"""
    if run_outcome != "OK" or not gates_pass:
        return "invalid"
    if across.get("overload_not_evaluable_ues"):
        return "invalid"
    if across.get("overloaded_ues"):
        return "overloaded"
    if any(across.get("starvation_ues", {}).values()):
        return "starved"
    return "ok"


class Bracket:
    """state of the saturation bracket of one combination over the ladder (B-1 .. B-4)"""

    def __init__(self, combo, start=1.0, ladder=LADDER):
        if start not in ladder:
            raise ValueError(f"start factor {start} not on the ladder {ladder}")
        self.combo, self.ladder, self.start = combo, tuple(ladder), start
        self.res = {}                       # factor -> outcome
        self.order = []
        self.stop = None                    # None while running; else 'bracketed' | 'top' | 'bottom' | 'non-monotone' | 'invalid'

    def record(self, f, outcome):
        if self.stop is not None:
            raise ValueError(f"{self.combo}: bracket already stopped ({self.stop})")
        if outcome not in OUTCOMES:
            raise ValueError(f"unknown outcome {outcome}")
        if f in self.res:
            raise ValueError(f"{self.combo}: factor {f} already run")
        if f != self.next_factor():
            raise ValueError(f"{self.combo}: factor {f} is not the next declared step ({self.next_factor()})")
        self.res[f] = outcome
        self.order.append(f)
        self._update()

    def _bad(self, o):
        return o in ("overloaded", "starved")

    def _update(self):
        if "invalid" in self.res.values():
            self.stop = "invalid"
            return
        oks = [f for f, o in self.res.items() if o == "ok"]
        bads = [f for f, o in self.res.items() if self._bad(o)]
        if oks and bads and max(oks) > min(bads):
            self.stop = "non-monotone"
            return
        L = self.ladder
        if oks and max(oks) == L[-1]:
            self.stop = "top"
            return
        if bads and min(bads) == L[0]:
            self.stop = "bottom"
            return
        if oks and bads:
            lo, hi = max(oks), min(bads)
            if L.index(hi) == L.index(lo) + 1:
                conf = L[L.index(hi) + 1] if L.index(hi) + 1 < len(L) else None
                if conf is None or conf in self.res:
                    self.stop = "bracketed"

    def next_factor(self):
        """the next factor to run (None when stopped)"""
        if self.stop is not None:
            return None
        if not self.res:
            return self.start
        L = self.ladder
        oks = [f for f, o in self.res.items() if o == "ok"]
        bads = [f for f, o in self.res.items() if self._bad(o)]
        if oks and bads:                                  # adjacent: the confirmation run above f_hi
            hi = min(bads)
            return L[L.index(hi) + 1]
        if bads:                                          # only non-ok so far: step down
            return L[L.index(min(bads)) - 1]
        return L[L.index(max(oks)) + 1]                   # only ok so far: step up

    def result(self):
        """(f_lo, f_hi, status); f_lo None when no capacity statement is possible"""
        oks = [f for f, o in self.res.items() if o == "ok"]
        bads = [f for f, o in self.res.items() if self._bad(o)]
        if self.stop in ("bracketed",):
            return max(oks), min(bads), "bracketed"
        if self.stop == "top":
            return max(oks), None, "above ladder (not extrapolated)"
        if self.stop == "bottom":
            return None, min(bads), "below ladder"
        return None, None, self.stop or "unfinished"


def select(brackets, margin=0.20, ladder=LADDER):
    """S-1: (f_E1, binding combination, reason) or (None, None, reason) when no common factor can be chosen"""
    los = {}
    for b in brackets:
        lo, hi, st = b.result()
        if lo is None:
            return None, b.combo, f"no f_lo for {b.combo}: {st}"
        los[b.combo] = lo
    if not los:
        return None, None, "no combination bracketed"
    bind = min(los, key=lambda c: (los[c], str(c)))
    limit = (1 - margin) * los[bind]
    cand = [f for f in ladder if f <= limit + 1e-12]
    if not cand:
        return None, bind, f"no ladder factor <= (1 - {margin}) x {los[bind]} = {limit:g}"
    return max(cand), bind, f"largest ladder factor <= (1 - {margin}) x {los[bind]} = {limit:g} (binding {bind})"


def sensitivity(brackets, ladder=LADDER):
    """S-2: f_E1 for every declared margin"""
    return {m: select(brackets, m, ladder) for m in MARGINS}


def verify_run(across, per_ue, gates_pass, run_outcome="OK", tol=SERVICE_TOL):
    """V-1 .. V-4 on one f_E1 verification run: list of (check, ok, detail)"""
    out = []
    out.append(("V-4", run_outcome == "OK" and gates_pass, f"run outcome {run_outcome}, gates {'PASS' if gates_pass else 'FAIL'}"))
    out.append(("V-1", not across.get("overloaded_ues") and not across.get("overload_not_evaluable_ues"),
                f"overloaded UEs {across.get('overloaded_ues')}, not evaluable {across.get('overload_not_evaluable_ues')}"))
    st = {c: u for c, u in across.get("starvation_ues", {}).items() if u}
    out.append(("V-2", not st, f"starvation {st}"))
    short = []
    for m in per_ue:
        for d in ("dl", "ul"):
            if m.get(f"loaded_{d}"):
                o, a = m.get(f"{d}_offered_bps"), m.get(f"{d}_achieved_bps")
                if o is None or a is None or a < (1 - tol) * o:
                    short.append((m["k"], d, o, a))
    out.append(("V-3", not short, f"loaded UEs below (1 - {tol}) x offered: {short}"))
    return out
