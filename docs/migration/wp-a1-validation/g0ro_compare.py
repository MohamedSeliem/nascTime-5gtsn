"""WP-A1 G0-RO comparison (runbook revision 3, section 4.3): the outputs of g0ro-run.sh against results recorded on the
D-2 reference environment (the reviewer's VM: OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, Python 3.13.13).

Every reference value below is quoted from a committed record of a D-2 execution:
  S1   simulations/m2/results/M2-S7.2a-a21-s1-closure.md (A2-V1-S1 CLOSED ACCEPTED, 17 Nov 2026): section 2 (S-5, S-6
       exit codes and verdicts), section 3 (rows, per-node accounting, 129 retired handles, unresolved [], end states)
  XA1  simulations/m2/results/M2-S7.2a-s5-n2-protocol.md, step C "Expected" (the N = 1 positive control, executed on
       the VM in the accepted N = 2 smoke stage): rc 0, XA-pre ... XA-6 PASS, A-1a 11 697 / A-1b 0 / ambiguous /
       orphan / re-insert 0, delta 1 000 000 000 ps
  XA2  the same protocol, acceptance rows N2-A1, N2-A4 ... N2-A6 and P-N2-4 (smoke accepted 16 Nov 2026 as "VALIDATED
       WITH A-1 LIMITATION"), and DR-07c (A-1 9 718 / 2 476 / 768 / 768 / 0): XA-pre ... XA-5 PASS, XA-6 NOT EVALUATED
       because A-1 is not exact, rc 0
Criteria: G0RO-V verdict identity (exit codes, verdicts, row statuses) and G0RO-C count identity (exact integers).
Raw-output identity is not claimed (as G0). Exit 0 only if every item passes; any missing output is a FAIL.

usage: python3 -I -B g0ro_compare.py <g0ro output dir>
"""
import json
import os
import sys

NE = "NOT EVALUATED"
A21_ROWS = ["A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-4c", "A2-5", "A2-6", "A2-7", "A2-8", "A2-9"]
S1_ROWS = {r: ("NOT EVALUATED" if r == "A2-4c" else "PASS") for r in A21_ROWS}                    # S1 section 3
S1_PER = {"2049": dict(inserts=11702, transmissions=11702, feedback=11697, ack=11697, nack=0, discarded=0),
          "2050": dict(inserts=1265, transmissions=1409, feedback=1408, ack=1264, nack=144, discarded=0)}  # S1 section 3
CFG_V = "M2S72-E0vN-q0-one0-n2-f1_A2V1"

results = []


def item(iid, ok, detail):
    results.append((iid, "PASS" if ok else "FAIL", detail))


def load(path):
    try:
        with open(path) as fh:
            return json.load(fh)
    except Exception as ex:                                          # a missing or unreadable output is a FAIL
        return {"__error__": f"{type(ex).__name__}: {ex}"}


def rc(g, name):
    try:
        return int(open(os.path.join(g, name + ".rc")).read().strip())
    except Exception:
        return None


def statuses(rows):
    out = {}
    for r in rows:
        out.setdefault(r[0], set()).add(r[2])
    return out


def a21(g, sub, contract, want_rc, want_verdict):
    j = load(os.path.join(g, sub, f"a21-{CFG_V}.json"))
    item(f"G0RO-V {sub} exit code", rc(g, sub) == want_rc, f"rc {rc(g, sub)}, D-2 {want_rc}")
    item(f"G0RO-V {sub} verdict", j.get("verdict") == want_verdict and j.get("contract") == contract,
         f"{j.get('verdict')!r} ({j.get('contract')}), D-2 {want_verdict!r}")
    st = statuses(j.get("rows", []))
    for r, want in S1_ROWS.items():
        item(f"G0RO-V {sub} row {r}", st.get(r) == {want}, f"{sorted(st.get(r, []))}, D-2 {want}")
    per = j.get("per_ue", {})
    for node, want in S1_PER.items():
        got = {k: per.get(node, {}).get(k) for k in want}
        item(f"G0RO-C {sub} node {node} accounting", got == want, f"{got}, D-2 {want}")
    h = j.get("handles", {})
    item(f"G0RO-C {sub} handles", len(h) == 129 and all(v.get("st") == "retired" for v in h.values()),
         f"{len(h)} handles, states {sorted({v.get('st') for v in h.values()})}; D-2 129 retired")
    item(f"G0RO-C {sub} unresolved", j.get("unresolved") == [], f"{j.get('unresolved')}, D-2 []")
    item(f"G0RO-C {sub} end states", j.get("end_states") == {"censored: awaiting feedback": 6},
         f"{j.get('end_states')}, D-2 {{'censored: awaiting feedback': 6}}")


def controls(g):
    j = load(os.path.join(g, "s1-controls", f"a21-controls-{CFG_V}.json"))
    c = j.get("controls", [])
    built = [x for x in c if x.get("status") != "NOT BUILDABLE"]
    item("G0RO-V s1-controls exit code", rc(g, "s1-controls") == 0, f"rc {rc(g, 's1-controls')}, D-2 0")
    item("G0RO-C s1-controls counts", len(built) == 22 and all(x.get("status") == "AS DECLARED" for x in built) and len(c) == 22,
         f"{sum(1 for x in built if x.get('status') == 'AS DECLARED')} / {len(built)} as declared, {len(c) - len(built)} not buildable; "
         "D-2 22 / 22, 0 not buildable")


def xa(g, sub, cfg, want_rows, want_a1, want_delta):
    j = load(os.path.join(g, sub, f"xa-{cfg}.json"))
    item(f"G0RO-V {sub} exit code", rc(g, sub) == 0, f"rc {rc(g, sub)}, D-2 0")
    st = statuses(j.get("rows", []))
    for r, want in want_rows.items():
        item(f"G0RO-V {sub} row {r}", st.get(r) == {want}, f"{sorted(st.get(r, []))}, D-2 {want}")
    s = (j.get("report") or {}).get("a1_summary") or {}
    got = {k: s.get(k) for k in want_a1}
    item(f"G0RO-C {sub} A-1 summary", got == want_a1, f"{got}, D-2 {want_a1}")
    if want_delta is not None:
        d = (j.get("report") or {}).get("delta_ps")
        item(f"G0RO-C {sub} delta", d == want_delta, f"{d}, D-2 {want_delta}")


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print(__doc__)
        return 2
    g = argv[1]
    a21(g, "s1-full", "full", 4, "A-2.1 INCOMPLETE")                                  # S1 S-5
    a21(g, "s1-f1di", "f1d-i", 0, "A-2.1 VALID")                                      # S1 S-5
    controls(g)                                                                      # S1 S-6
    xa(g, "xa-n1", "M2S72-E0v-q0-f1", {f"XA-{x}": "PASS" for x in ("pre", "0", "1", "2", "3", "4", "5", "6")},
       dict(a1a=11697, a1b=0, ambiguous=0, orphan=0, reinsert=0), 1000000000)       # XA1
    xa(g, "xa-n2", "M2S72-E0vN-q0-one0-n2-f1",
       {**{f"XA-{x}": "PASS" for x in ("pre", "0", "1", "2", "3", "4", "5")}, "XA-6": NE},
       dict(a1a=9718, a1b=2476, ambiguous=768, orphan=0, reinsert=768), None)        # XA2
    for iid, st, d in results:
        print(f"{st:<4} | {iid} | {d}")
    bad = sum(1 for r in results if r[1] != "PASS")
    print(f"\nG0-RO comparison: {len(results) - bad} / {len(results)} PASS; {'EQUIVALENT' if not bad else 'NOT EQUIVALENT'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
