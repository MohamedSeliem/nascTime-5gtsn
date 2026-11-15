#!/usr/bin/env python3
"""Stage 5 E0v N = 1 smoke preparation: contract tests between the S5-2 per-UE adapter (m2s72_peru_adapter.py, never
yet run on real output) and the accepted readers it calls. They catch, before the VM run, a renamed attribute, a
changed signature or a changed log text that would otherwise surface only as a crash or a silent NOT EVALUATED on
the first real run. Static / introspective only: no simulation, no raw output, no OMNeT++.

The S5-1 tests (test_m2s72s5.py) and S5-2 tests (test_m2s72s5_2.py) are unchanged and still cover the runner's
smoke lifecycle (stub simulator), the per-run checker and the per-UE metric logic."""
import inspect
import os
import re
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
_argv = sys.argv
sys.argv = [_argv[0]]
import check_m2s72_e0 as E  # noqa: E402
import gate_m2s71_p0 as G  # noqa: E402
sys.argv = _argv
import m2s72_maclog as ML  # noqa: E402
import m2s72_peru_adapter as A  # noqa: E402
import m2s72_runs as R  # noqa: E402

TESTS = []


def test(name):
    def deco(f):
        TESTS.append((name, f))
        return f
    return deco


def src(mod):
    return inspect.getsource(mod)


@test("contract: Run72 provides cfg, n, node_id (the adapter's UE identity), with the duplicate-node guard")
def _():
    s = inspect.getsource(R.Run72.__init__)
    for needle in ("self.cfg, self.rep = cfg, rep", "self.n = n", "self.node_id = {}", "duplicate NR MAC node ids"):
        assert needle in s, needle


@test("contract: Block B evaluation object exposes run, T, vec, E (per-slave evaluation) as the adapter reads them")
def _():
    import check_m2s72_b as B
    s = src(B)
    for needle in ("self.run = R.Run72(runs, cfg, rep)", "self.T = F1.t_end(self.run)", "self.vec = RR.read_vectors(self.run.vec_path)",
                   "self.views, self.E, self.m2 = {}, {}, {}"):
        assert needle in s, needle


@test("contract: E0 helpers used by the adapter exist with the expected signatures and return shapes")
def _():
    assert list(inspect.signature(E.replay_um).parameters) == ["sdus", "pdus"]
    assert "return done, None, list(queue)" in inspect.getsource(E.replay_um)
    assert list(inspect.signature(E.backlog).parameters)[:2] == ["q", "T"]
    bl = inspect.getsource(E.backlog)
    assert "q.sdus_h" in bl and "q.done" in bl
    assert list(inspect.signature(E.q8_rows).parameters) == ["name", "q"] and "return pairs" in inspect.getsource(E.q8_rows)
    assert E.T_COHORT == 10 * E.S and E.SYNC == 0 and E.FU == 8
    assert list(inspect.signature(G.deliveries).parameters) == ["done", "deliv", "rxpdus", "pdus", "sdus", "horizon"]
    d = inspect.getsource(G.deliveries)
    assert "return matched, unmatched, rest, [pdus[k] for k in gone]" in d and '"inflight"' in d


@test("contract: Q8 exposes st / ds_tx / ds_rx / n3_bad / map_bad / model_err; the strict 'exclusion' attribution "
      "applies only at N > 1, so at N = 1 the adapter's Q8 is exactly the E0 rule")
def _():
    s = src(E.Q8)
    for needle in ("self.st = st", "self.ds_tx = ", "self.ds_rx = ", "self.n3_bad = []", "self.map_bad = ", "self.model_err = None",
                   'if self.attr == "exclusion" and self.ev.run.n > 1:'):
        assert needle in s, needle
    assert "attr" in inspect.signature(E.Q8.__init__).parameters


@test("contract: the adapter's DL load sources are DrbReplay's, with UE k in place of UE 0 (same vectors, same rule)")
def _():
    dr = inspect.getsource(E.DrbReplay)
    ad = inspect.getsource(A.dl_load)
    for v in ('"receivedPacketFromUpperLayer:vector(packetBytes)"', '"sentPduSize:vector"',
              '"sentPacketToUpperLayer:vector(packetBytes)"', '"receivedPacketFromLowerLayer:vector(packetBytes)"'):
        assert v in dr and v in ad, v
    assert 'f"gnb1.cellularNic.rlc-um-{node}-{drb}.tx", f"ue[0].cellularNic.nrRlc-um-1-{drb}.rx"' in dr
    assert 'f"gnb1.cellularNic.rlc-um-{node}-1.tx", f"ue[{k}].cellularNic.nrRlc-um-1-1.rx"' in ad


@test("contract: the adapter's clock metrics are E0's (same fields and the same steady-state rule)")
def _():
    e0 = src(E)
    ad = inspect.getsource(A.clock)
    assert 'cal = [x["seq"] for x in E.fus if "skip" not in x and x.get("nrr_valid")]' in e0
    assert 'cal = [x["seq"] for x in Ek.fus if "skip" not in x and x.get("nrr_valid")]' in ad
    assert 'x["max_between"]' in e0 and 'x["max_between"]' in ad and 'Ek.iv[2:]' in ad


@test("contract: the adapter's H-ARQ regexes are the accepted parser's, and both match the exact Simu5G 1.8.1 "
      "texts (LteHarqBufferTx.cc:131 and :220, as printed with the runner's '%t|%M|' prefix)")
def _():
    assert A.R_INSERT.pattern == ML.R_INSERT.pattern and A.R_FB.pattern == ML.R_FB.pattern
    ins = "H-ARQ TX: new pdu (id 812 ) inserted into process 3 codeword id: 0 for node with id 2049"
    fb = "H-ARQ TX: feedback received for process 3 codeword 0 result is ACK"
    m = A.R_INSERT.search(ins)
    assert m and m.groups() == ("812", "3", "0", "2049")
    assert A.R_FB.search(fb).groups() == ("3", "0", "ACK")
    assert A.R_FB.search(fb.replace("ACK", "NACK")).groups()[2] == "NACK"
    # the RX-side and D2D texts are not TX lines and must not match
    assert not A.R_INSERT.search("H-ARQ RX: new PDU (id 5 ) inserted into process 2")
    assert not A.R_FB.search("H-ARQ MIRROR: feedback received for process 1 codeword 0 result is ACK")


@test("contract: the adapter's line split and module test are the accepted MacLog's ('<t>|<module>|<msg>', exact "
      "gNB MAC module path)")
def _():
    ml = inspect.getsource(ML.MacLog.__init__)
    ad = inspect.getsource(A.harq_events)
    assert 'p = line.rstrip("\\n").split("|", 2)' in ml and 'p = line.rstrip("\\n").split("|", 2)' in ad
    assert 'gnb="M2S72Bridge.gnb1.cellularNic.mac"' in inspect.signature(ML.MacLog.__init__).__str__().replace("'", '"')
    assert inspect.signature(A.harq_events).parameters["gnb"].default == "M2S72Bridge.gnb1.cellularNic.mac"


@test("decision record: S5_ENV_DECISION names the G0 closing commit 04657b4, and the G0 record is CLOSED")
def _():
    root = os.path.dirname(os.path.dirname(HERE))
    dec = open(os.path.join(HERE, "..", "results", "M2-S7.2a-s5-env-decision.md")).read()
    m = re.search(r"^S5_ENV_DECISION=\"([^\"]+)\"$", dec, re.M)
    assert m and "04657b4" in m.group(1) and "OMNeT++ 6.5.0" in m.group(1), m
    g0 = open(os.path.join(root, "results", "simu5g-1.8.1", "g0env", "G0-environment-equivalence-record.md")).read()
    assert "**Status: CLOSED.**" in g0


def main():
    ok = 0
    for name, f in TESTS:
        try:
            f()
            print(f"PASS | {name}")
            ok += 1
        except Exception as ex:
            import traceback
            print(f"FAIL | {name}: {type(ex).__name__}: {ex}\n{traceback.format_exc()[-600:]}")
    print(f"S5 smoke contract tests: {ok} / {len(TESTS)} PASS")
    return 0 if ok == len(TESTS) else 1


if __name__ == "__main__":
    sys.exit(main())
