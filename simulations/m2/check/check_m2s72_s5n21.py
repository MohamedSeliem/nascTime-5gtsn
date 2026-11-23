#!/usr/bin/env python3
"""WP-A1 CLI: the E0v-N per-run evaluation with A-2.1 as the per-UE H-ARQ source (design revision 2.1, 57a80ca).

    python3 -I -B check_m2s72_s5n21.py run         <runs> <cfg> <records dir> [--t0 <s>]
    python3 -I -B check_m2s72_s5n21.py hrq         <runs> <cfg> <records dir> [--t0 <s>] [--expect <file>]
    python3 -I -B check_m2s72_s5n21.py hrq-fixture <fixture dir> <records dir> [--expect <file>]
    python3 -I -B check_m2s72_s5n21.py controls    <runs> <cfg> <records dir> [--t0 <s>]

INCREMENT I-1: SKELETON ONLY. No mode is implemented yet (run, hrq: I-6 / I-7; hrq-fixture: I-6; controls: I-8).
Every invocation prints this text and exits 2 (REFUSED); nothing is read, evaluated or written. The file exists in I-1
so that the isolated-import handling (python3 -I) is tested on the CLI itself (T-imports-isolated).

Exit codes of the finished tool (design 4.8, 5.1): 0 PASS, 1 FAIL, 2 REFUSED / EVALUATION ERROR, 3 HELD FOR REVIEW,
4 INCOMPLETE; with --expect: 0 all expectations met, 5 EXPECTATION MISMATCH, 2 error.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
if HERE not in sys.path:
    sys.path.insert(0, HERE)
import m2s72_e0vn21 as W  # noqa: E402

MODES = ("run", "hrq", "hrq-fixture", "controls")


def main(argv):
    if len(argv) >= 2 and argv[1] in MODES:
        print(f"REFUSED: mode '{argv[1]}' is not implemented in increment I-1 (design revision 2.1, section 9)")
        return W.EXIT[W.V_REFUSED]
    print(__doc__)
    return W.EXIT[W.V_REFUSED]


if __name__ == "__main__":
    sys.exit(main(sys.argv))
