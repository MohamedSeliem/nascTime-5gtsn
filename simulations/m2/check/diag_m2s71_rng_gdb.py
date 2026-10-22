# M2-S7.1 closure diagnostic (seed invariance): counts every random number drawn in a run by call site.
# gdb Python script; m2s71.sh seeds runs it as
#   gdb -batch -ex "python OUTF='<out>'" -ex "source diag_m2s71_rng_gdb.py" -ex run --args opp_run ...
# A breakpoint on each cMersenneTwister draw function records the three innermost non-OMNeT++ callers and
# continues (it never stops the run). Output: "<count> <callers>" lines, most frequent first.
import gdb
from collections import Counter

C = Counter()


class Draw(gdb.Breakpoint):
    def stop(self):
        f, names = gdb.newest_frame(), []
        for _ in range(10):
            if f is None:
                break
            names.append(f.name() or "?")
            f = f.older()
        user = [n for n in names if not n.startswith("omnetpp::")]
        C[" <- ".join(user[:3])] += 1
        return False


for m in ("doubleRand", "doubleRandNonz", "doubleRandIncl1", "intRand"):
    Draw("omnetpp::cMersenneTwister::" + m)


def report(ev):
    with open(OUTF, "w") as fh:   # noqa: F821 (set by the caller)
        for k, v in C.most_common():
            fh.write(f"{v} {k}\n")


gdb.events.exited.connect(report)
