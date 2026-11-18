"""C-4 case A controlled removal checks (E2b.3-R1 R-2).

  transaction <EV>  the simulated apt transaction (apt-remove-simulation.txt) may remove only libc++ / libc++abi
                    development packages (incl. the directly associated metapackages), must include every proposed
                    package (apt-remove-proposed.txt), and may install or purge nothing -> apt-remove-transaction.txt
  inventory <EV>    the before/after dpkg inventories may differ only in the removed packages, which must no longer be
                    installed -> host-packages.diff
"""
import os
import re
import sys

PAT = re.compile(r"^libc\+\+(abi)?(-[0-9]+)?-dev$")


def transaction(ev):
    sim = open(os.path.join(ev, "apt-remove-simulation.txt")).read().splitlines()
    proposed = [l.strip() for l in open(os.path.join(ev, "apt-remove-proposed.txt")) if l.strip()]
    remv = sorted({re.sub(r":amd64$", "", l.split()[1]) for l in sim if l.startswith("Remv ")})
    other = [l for l in sim if re.match(r"^(Inst|Purg) ", l)]
    bad = [p for p in remv if not PAT.match(p)]
    ok = bool(remv) and not bad and not other and set(proposed) <= set(remv)
    with open(os.path.join(ev, "apt-remove-transaction.txt"), "w") as f:
        f.write("".join(f"removal: {p}\n" for p in remv))
        f.write(f"rejected_unrelated_removals: {', '.join(bad) or 'none'}\n")
        f.write(f"install_or_purge_lines: {len(other)}\n")
        f.write(f"transaction_check: {'PASS' if ok else 'FAIL'}\n")
    print(open(os.path.join(ev, "apt-remove-transaction.txt")).read())
    return ok


def inventory(ev):
    def inv(p):
        d = {}
        for l in open(os.path.join(ev, p)):
            f = l.rstrip("\n").split("\t")
            if len(f) == 3:
                d[f[0]] = (f[1], f[2])
        return d
    before, after = inv("host-packages-before.tsv"), inv("host-packages-after.tsv")
    remv = {l.split(": ", 1)[1].strip() for l in open(os.path.join(ev, "apt-remove-transaction.txt")) if l.startswith("removal: ")}
    changed = sorted(p for p in set(before) | set(after) if before.get(p) != after.get(p))
    still = sorted(p for p in remv if after.get(p, ("", ""))[1] == "install ok installed")
    ok = set(changed) == remv and not still
    with open(os.path.join(ev, "host-packages.diff"), "w") as f:
        for p in changed:
            f.write(f"{p}\tbefore={before.get(p, ('absent', ''))}\tafter={after.get(p, ('absent', ''))}\n")
        f.write(f"changed_packages: {len(changed)}\nexpected_removals: {len(remv)}\nstill_installed: {', '.join(still) or 'none'}\n")
        f.write(f"r2_result: {'PASS' if ok else 'FAIL'}\n")
    print(open(os.path.join(ev, "host-packages.diff")).read())
    return ok


if __name__ == "__main__":
    if len(sys.argv) != 3 or sys.argv[1] not in ("transaction", "inventory"):
        raise SystemExit(__doc__)
    sys.exit(0 if (transaction if sys.argv[1] == "transaction" else inventory)(sys.argv[2]) else 1)
