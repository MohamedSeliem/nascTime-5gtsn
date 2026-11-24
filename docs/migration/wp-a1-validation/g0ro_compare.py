"""WP-A1 G0-RO comparison (runbook revision 4, section 7): the outputs of g0ro-run.sh against results recorded on the
D-2 reference environment (the reviewer's VM: OMNeT++ 6.5.0 / INET 4.7.0 / Simu5G 1.8.1, Python 3.13.13).

Each reference value carries its source class:
  R  a D-2 result recorded in a committed record (quoted below with its location)
  D  derived from R values by the accepted code at C (the derivation is stated)
  P  a declared protocol expectation that was executed on D-2 but whose result is NOT in a committed record:
     reported for information only; never part of the equivalence verdict
Sources:
  S1   simulations/m2/results/M2-S7.2a-a21-s1-closure.md (A2-V1-S1 CLOSED ACCEPTED, 17 Nov 2026): section 1 (window),
       section 2 S-5 / S-6 / S-7, section 3 (rows, per-node table, "129 handles, all retired")
  A2R  simulations/m2/results/M2-S7.2a-a2-design-review.md section 1 ("accepted; quoted, never reinterpreted"): N = 2
       XA-pre ... XA-5 PASS, XA-6 NOT EVALUATED, A-1a 9,718, A-1b 2,476, ambiguous 768, re-inserts 768, orphans 0,
       UE-side NACK / retransmitted PDU ids 0 / 0; N = 1 A-1a 11,697, orphan / ambiguous / re-insert 0; "neither run
       ... contains a DL NACK"
  PRO  simulations/m2/results/M2-S7.2a-s5-n2-protocol.md step C "Expected" (N = 1 XA positive control): declared only
Verdict: EQUIVALENT only if every R and D item passes. Any missing output is a FAIL. Raw-output identity is not claimed.

usage: python3 -I -B g0ro_compare.py <g0ro output dir>
"""
import json
import os
import sys

NE = "NOT EVALUATED"
A21_ROWS = ["A2-0", "A2-0s", "A2-1", "A2-2", "A2-3", "A2-4a", "A2-4b", "A2-4c", "A2-5", "A2-6", "A2-7", "A2-8", "A2-9"]
S1_ROWS = {r: (NE if r == "A2-4c" else "PASS") for r in A21_ROWS}
S1_PER = {"2049": dict(inserts=11702, transmissions=11702, feedback=11697, ack=11697, nack=0, discarded=0),
          "2050": dict(inserts=1265, transmissions=1409, feedback=1408, ack=1264, nack=144, discarded=0)}
CFG_V = "M2S72-E0vN-q0-one0-n2-f1_A2V1"

# Recorded coverage. Every field of the outputs that is NOT compared is listed here, with the reason.
OMITTED = [
    ("a21 per-UE lines_by_class; S1 totals 371 groups / 742 exchangeable lines / 40 resolved by retransmission / 15 bound",
     "recorded in S1 section 3, but the mapping from the JSON class keys to those totals is not verified; not compared"),
    ("A2-8 Simu5G scalar values (S1 section 4)", "input values from the .sca (byte-identical by the manifest); the A-2.1 "
     "side is implied by the compared counts and the A2-8 row status"),
    ("A2-7 confirmation details, per-UE occupancy equality, coverage section, d*, t_end", "only the row statuses are compared"),
    ("a21-controls observed / declared rows per control", "only exit code and counts are compared"),
    ("S1 S-1 (integrity) and S-2 (original A2-V1 rows V-0 ... V-2, check_m2s72_a2v1)", "integrity is DR-13-V; S-2's "
     "evaluator is not re-run by G0-RO"),
    ("run times", "not an equivalence criterion"),
    ("xa overlap census, truth / A-1 aggregates, d*_ps", "not recorded for the smokes"),
    ("N = 1 xa retransmitted_pdus", "not recorded for N = 1 (declared expectation only)"),
]

results = []


def item(iid, cls, ok, detail):
    results.append((iid, cls, "PASS" if ok else "FAIL", detail))


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
    item(f"{sub} exit code", "R", rc(g, sub) == want_rc, f"rc {rc(g, sub)}; S1 S-5 rc {want_rc}")
    item(f"{sub} verdict", "R", j.get("verdict") == want_verdict and j.get("contract") == contract,
         f"{j.get('verdict')!r} ({j.get('contract')}); S1 S-5 {want_verdict!r}")
    item(f"{sub} window", "R", j.get("window_ps") == [2000000000000, 12001000000000],
         f"{j.get('window_ps')}; S1 section 1 [2000000000000, 12001000000000)")
    st = statuses(j.get("rows", []))
    for r, want in S1_ROWS.items():
        item(f"{sub} row {r}", "R", st.get(r) == {want}, f"{sorted(st.get(r, []))}; S1 section 3 {want}")
    per = j.get("per_ue", {})
    for node, want in S1_PER.items():
        got = {k: per.get(node, {}).get(k) for k in want}
        item(f"{sub} node {node} accounting", "R", got == want, f"{got}; S1 section 3 {want}")
    h = j.get("handles", {})
    item(f"{sub} handles", "R", len(h) == 129 and all(v.get("st") == "retired" for v in h.values()),
         f"{len(h)} handles, states {sorted({v.get('st') for v in h.values()})}; S1 section 3: 129, all retired")
    item(f"{sub} unresolved", "R", j.get("unresolved") == [], f"{j.get('unresolved')}; S1 S-7 []")
    item(f"{sub} end states", "R", j.get("end_states") == {"censored: awaiting feedback": 6},
         f"{j.get('end_states')}; S1 S-7 {{'censored: awaiting feedback': 6}}")


def controls(g):
    j = load(os.path.join(g, "s1-controls", f"a21-controls-{CFG_V}.json"))
    c = j.get("controls", [])
    built = [x for x in c if x.get("status") != "NOT BUILDABLE"]
    item("s1-controls exit code", "R", rc(g, "s1-controls") == 0, f"rc {rc(g, 's1-controls')}; S1 S-6 rc 0")
    item("s1-controls counts", "R", len(c) == 22 and len(built) == 22 and all(x.get("status") == "AS DECLARED" for x in built),
         f"{sum(1 for x in built if x.get('status') == 'AS DECLARED')} / {len(built)} as declared, {len(c) - len(built)} "
         "not buildable; S1 S-6: 22 / 22, 0 not buildable")


def xa(g, sub, cfg, spec):
    """spec: list of (id, class, getter, wanted, source)"""
    j = load(os.path.join(g, sub, f"xa-{cfg}.json"))
    st = statuses(j.get("rows", []))
    rep = j.get("report") or {}
    s = rep.get("a1_summary") or {}
    for iid, cls, kind, key, want, src in spec:
        if kind == "rc":
            got = rc(g, sub)
        elif kind == "row":
            got = sorted(st.get(key, []))
            want = [want]
        elif kind == "a1":
            got = s.get(key)
        else:
            got = rep.get(key)
        item(f"{sub} {iid}", cls, got == want, f"{got}; {src} {want}")


def main(argv):
    if len(argv) != 2 or not os.path.isdir(argv[1]):
        print(__doc__)
        return 2
    g = argv[1]
    a21(g, "s1-full", "full", 4, "A-2.1 INCOMPLETE")
    a21(g, "s1-f1di", "f1d-i", 0, "A-2.1 VALID")
    controls(g)
    n2 = [(f"row XA-{x}", "R", "row", f"XA-{x}", "PASS", "A2R section 1") for x in ("pre", "0", "1", "2", "3", "4", "5")]
    n2 += [("row XA-6", "R", "row", "XA-6", NE, "A2R section 1"),
           ("exit code", "D", "rc", None, 0, "derived: xa returns 0 iff xa_ok (XA-pre ... XA-5 PASS, XA-6 NE because A-1 is not exact)"),
           ("A-1a", "R", "a1", "a1a", 9718, "A2R"), ("A-1b", "R", "a1", "a1b", 2476, "A2R"),
           ("ambiguous", "R", "a1", "ambiguous", 768, "A2R"), ("re-insert", "R", "a1", "reinsert", 768, "A2R"),
           ("orphan", "R", "a1", "orphan", 0, "A2R"), ("UE-sent NACK", "R", "rep", "nack_ue_sent", 0, "A2R"),
           ("retransmitted PDUs", "R", "rep", "retransmitted_pdus", 0, "A2R")]
    n1 = [("A-1a", "R", "a1", "a1a", 11697, "A2R"), ("ambiguous", "R", "a1", "ambiguous", 0, "A2R"),
          ("orphan", "R", "a1", "orphan", 0, "A2R"), ("re-insert", "R", "a1", "reinsert", 0, "A2R"),
          ("UE-sent NACK", "R", "rep", "nack_ue_sent", 0, "A2R ('neither run contains a DL NACK')"),
          ("A-1b", "P", "a1", "a1b", 0, "PRO step C (declared)"), ("delta", "P", "rep", "delta_ps", 1000000000, "PRO (declared)"),
          ("exit code", "P", "rc", None, 0, "PRO (declared)")]
    n1 += [(f"row XA-{x}", "P", "row", f"XA-{x}", "PASS", "PRO (declared)") for x in ("pre", "0", "1", "2", "3", "4", "5", "6")]
    xa(g, "xa-n2", "M2S72-E0vN-q0-one0-n2-f1", n2)
    xa(g, "xa-n1", "M2S72-E0v-q0-f1", n1)
    for iid, cls, st, d in results:
        print(f"{st if cls != 'P' else 'INFO-' + st:<9} | {cls} | {iid} | {d}")
    print("\nNot compared (coverage record):")
    for f, why in OMITTED:
        print(f"  - {f}: {why}")
    gating = [r for r in results if r[1] in ("R", "D")]
    bad = sum(1 for r in gating if r[2] != "PASS")
    info_bad = sum(1 for r in results if r[1] == "P" and r[2] != "PASS")
    print(f"\nG0-RO comparison: {len(gating) - bad} / {len(gating)} recorded (R) and derived (D) items PASS; "
          f"{info_bad} declared-only (P) items differ (information); {'EQUIVALENT' if not bad else 'NOT EQUIVALENT'}")
    return 0 if not bad else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
