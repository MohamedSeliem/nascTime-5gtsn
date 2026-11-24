#!/usr/bin/env python3
"""M2B-4 unit tests of TtEgressPairer (FIFO and TAS modes), no simulation (docs/migration/m2b-4-tas-residence.md).

Builds simulations/m2/m2b4/pairer_test.cc together with the repository's src/nasctime/m2/TtEgressPairer.cc in a
temporary directory (outside the repository) against the OMNeT++ headers and liboppsim, runs it, and checks every
case line. Environment: OMNETPP_ROOT (OMNeT++ 6.5.0 built). Exit 0 all pass, 1 a failure, 2 environment missing.
"""
import os
import re
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.abspath(__file__))
M2 = os.path.dirname(HERE)
REPO = os.path.dirname(os.path.dirname(M2))
OMNETPP = os.environ.get("OMNETPP_ROOT", "")
if not OMNETPP or not os.path.isdir(os.path.join(OMNETPP, "include", "omnetpp")):
    print("SKIP: OMNETPP_ROOT must name a built OMNeT++ 6.5.0")
    sys.exit(2)
CXX = os.environ.get("CXX", "clang++")
with tempfile.TemporaryDirectory() as d:
    exe = os.path.join(d, "pairer_test")
    b = subprocess.run([CXX, "-std=c++17", "-O1", "-Wall", "-Werror", f"-I{OMNETPP}/include", f"-I{REPO}/src/nasctime/m2",
                        os.path.join(M2, "m2b4", "pairer_test.cc"), os.path.join(REPO, "src", "nasctime", "m2", "TtEgressPairer.cc"),
                        f"-L{OMNETPP}/lib", "-loppsim", "-loppcommon", f"-Wl,-rpath,{OMNETPP}/lib", "-o", exe],
                       capture_output=True, text=True)
    if b.returncode != 0:
        print(f"FAIL  build\n{b.stderr[-1500:]}")
        print("\nM2B-4 pairer unit tests: 0 / 1 PASS, 1 FAIL")
        sys.exit(1)
    r = subprocess.run([exe], capture_output=True, text=True)
lines = [l for l in r.stdout.splitlines() if l.startswith("CASE ")]
for l in lines:
    print(l.replace("CASE PASS", "PASS ").replace("CASE FAIL", "FAIL "))
passed = sum(1 for l in lines if l.startswith("CASE PASS"))
fifo = [l for l in lines if l.split()[2] == "fifo"]
tas = [l for l in lines if l.split()[2] == "tas"]
ok = r.returncode == 0 and passed == len(lines) and len(fifo) == 11 and len(tas) >= 20
summary = re.search(r"M2B-4 pairer unit cases: (\d+) / (\d+) PASS", r.stdout)
print(f"\nM2B-4 pairer unit tests: {passed} / {len(lines)} PASS, {len(lines) - passed} FAIL "
      f"(FIFO {len(fifo)}, TAS {len(tas)})")
sys.exit(0 if ok and summary else 1)
